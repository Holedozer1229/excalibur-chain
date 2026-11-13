"""ledger.py — the wallet's view of the fork ledger.

Three sources, in preference order — the command always says which one
answered, because a balance from a snapshot is not a balance from a node:

  1. LIVE NODE RPC (fast, indexed): getutxos per lock + getblockcount.
     Only when the fork node answers on 127.0.0.1:9432.
  2. LIGHT SNAPSHOT (lightledger): a verified overlay snapshot
     (import_overlay checks SHA-256 + both Merkle roots). Balance and
     UTXOs come from the snapshot at its checkpoint height. Honest
     limit: the snapshot covers fork-created UTXOs only — the Bitcoin
     snapshot base (968698) is not built on this VM — and it is only
     as fresh as its checkpoint.
  3. LOCAL CHAIN SCAN (full, read-only): streams chaindata_fork/
     chain.jsonl, tracking only the wallet's watched locks, with an
     incremental cache (<datadir>/ledger_cache.json). The scan never
     writes to the chain dir and never truncates anything. Reorg-safe:
     on resume, the next record's prev must equal the cached tip hash,
     or the cache is discarded and the scan restarts from genesis.

Amounts are swords (1 EXCAL = 100,000,000). Coinbase maturity is 100
blocks (txscript.COINBASE_MATURITY).
"""
import http.client
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from txscript import parse_tx, txid_internal, COINBASE_MATURITY

WORKSPACE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHAIN_PATH = os.path.join(WORKSPACE, "chaindata_fork", "chain.jsonl")
LIGHT_LEDGER_DIR = os.path.join(WORKSPACE, "light-ledger")
DEFAULT_RPC_HOST = "127.0.0.1"
DEFAULT_RPC_PORT = 9432


class RpcError(Exception):
    pass


def _apply_record_txs(rec, watched, utxos, history):
    """Apply one block record's txs to a wallet UTXO map.
    rec: {"height", "txs": [hex, ...]}. watched: set of lock bytes.
    utxos: {(txid_hex, vout): {...}} mutated in place. history: list
    appended to. Shared by the local scan and the P2P apply path."""
    height = int(rec["height"])
    for n, raw_hex in enumerate(rec.get("txs", [])):
        try:
            raw = bytes.fromhex(raw_hex)
            t = parse_tx(raw)
        except ValueError:
            continue
        tid = txid_internal(raw).hex()
        if n > 0:  # spends
            for vin in t["vin"]:
                key = (vin["prev"].hex(), vin["idx"])
                if key in utxos:
                    spent = utxos.pop(key)
                    history.append({"txid": tid, "height": height,
                                    "kind": "spend",
                                    "value": -spent["value"],
                                    "lock": spent["lock"]})
        for j, vout in enumerate(t["vout"]):
            if bytes(vout["script"]) in watched:
                utxos[(tid, j)] = {
                    "lock": bytes(vout["script"]).hex(),
                    "value": int(vout["value"]),
                    "height": height,
                    "coinbase": n == 0,
                    "cb_h": height if n == 0 else 0}
                history.append({"txid": tid, "height": height,
                                "kind": "receive",
                                "value": int(vout["value"]),
                                "lock": bytes(vout["script"]).hex()})


class RpcClient:
    """Minimal JSON-RPC client for the fork node (stdlib http.client —
    curl to loopback is intercepted by the sandbox proxy; python
    http.client is the reliable path for local RPC)."""

    def __init__(self, host=DEFAULT_RPC_HOST, port=DEFAULT_RPC_PORT,
                 timeout=10):
        self.host, self.port, self.timeout = host, port, timeout

    def call(self, method, params=None):
        body = json.dumps({"method": method, "params": params or [],
                           "id": 1}).encode()
        conn = http.client.HTTPConnection(self.host, self.port,
                                         timeout=self.timeout)
        try:
            conn.request("POST", "/", body,
                         {"Content-Type": "application/json"})
            resp = conn.getresponse()
            raw = resp.read()
        except (OSError, http.client.HTTPException) as e:
            raise RpcError(f"RPC {method} failed: {e}")
        finally:
            conn.close()
        try:
            data = json.loads(raw.decode())
        except ValueError:
            raise RpcError(f"RPC {method}: non-JSON reply: {raw[:120]!r}")
        if data.get("error") is not None:
            raise RpcError(f"RPC {method}: {data['error']}")
        return data.get("result")

    def tip(self):
        height = self.call("getblockcount")
        best = self.call("getbestblockhash")
        return int(height), str(best)

    def getutxos(self, lock: bytes):
        """UTXOs paying to `lock`: [{txid, vout, value, mature, coinbase}]."""
        return self.call("getutxos", [lock.hex()])

    def ping(self):
        try:
            self.call("getblockcount")
            return True
        except RpcError:
            return False


class Ledger:
    """Wallet ledger: UTXOs + history for a set of watched locks."""

    def __init__(self, datadir, chain_path=CHAIN_PATH,
                 rpc: RpcClient = None):
        self.datadir = os.path.abspath(datadir)
        self.chain_path = chain_path
        self.rpc = rpc or RpcClient()
        self.cache_path = os.path.join(self.datadir, "ledger_cache.json")
        self._cache = None

    # ------------------------------------------------------------ cache
    def _load_cache(self):
        if self._cache is not None:
            return self._cache
        try:
            with open(self.cache_path) as f:
                c = json.load(f)
            if isinstance(c, dict) and c.get("format") == "excalibur-ledger-cache-v1":
                self._cache = c
                return c
        except (OSError, ValueError):
            pass
        self._cache = {"format": "excalibur-ledger-cache-v1",
                       "scanned_bytes": 0, "tip_height": -1,
                       "tip_hash": None, "utxos": {}, "history": []}
        return self._cache

    def _save_cache(self):
        os.makedirs(self.datadir, exist_ok=True)
        tmp = self.cache_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self._cache, f)
        os.replace(tmp, self.cache_path)

    # ------------------------------------------------------------ RPC path
    def balance_via_rpc(self, locks):
        """(balances, tip) from the live node. balances: {lock_hex:
        {"mature": swords, "immature": swords, "utxos": [...]}}.
        Raises RpcError when the node is unreachable."""
        tip_height, tip_hash = self.rpc.tip()
        out = {}
        for lock in locks:
            rows = self.rpc.getutxos(lock)
            mature = immature = 0
            utxos = []
            for r in rows:
                if r["mature"]:
                    mature += int(r["value"])
                else:
                    immature += int(r["value"])
                utxos.append({"txid": r["txid"], "vout": int(r["vout"]),
                              "value": int(r["value"]),
                              "mature": bool(r["mature"]),
                              "coinbase": bool(r["coinbase"])})
            out[lock.hex()] = {"mature": mature, "immature": immature,
                               "utxos": utxos}
        return out, (tip_height, tip_hash)

    # ------------------------------------------------------------ snapshot
    def load_snapshot(self, snapshot_path, manifest):
        """Verified overlay snapshot (lightledger.import_overlay):
        returns (overlay, spent). Raises ValueError on any mismatch."""
        import lightledger
        return lightledger.import_overlay(snapshot_path, manifest)

    def balance_from_overlay(self, overlay, locks):
        """Balances for watched locks from a verified overlay dict."""
        out = {}
        for lock in locks:
            rows = []
            for key, entries in overlay.items():
                for e in entries:
                    if bytes(e[1]) == bytes(lock):
                        rows.append({"txid": key[0].hex(), "vout": key[1],
                                     "value": int(e[0]), "mature": True,
                                     "coinbase": bool(e[2]),
                                     "cb_height": int(e[3])})
            total = sum(r["value"] for r in rows)
            out[lock.hex()] = {"mature": total, "immature": 0,
                               "utxos": rows}
        return out

    # ------------------------------------------------------------ local scan
    def sync_local(self, watched_locks, progress=None):
        """Incremental read-only scan of chain.jsonl for watched locks.

        Returns {"scanned_records": n, "new_records": n, "tip_height": h,
        "tip_hash": hex, "source": "local-chain-scan", "rescan": bool}.
        The cache is updated atomically at the end."""
        cache = self._load_cache()
        watched = {bytes(lk) for lk in watched_locks}
        utxos = {}  # (txid_hex, vout) -> {lock, value, height, coinbase, cb_h}
        for lock_hex, rows in cache.get("utxos", {}).items():
            for r in rows:
                utxos[(r["txid"], r["vout"])] = {
                    "lock": lock_hex, "value": r["value"],
                    "height": r["height"], "coinbase": r["coinbase"],
                    "cb_h": r["cb_h"]}
        history = list(cache.get("history", []))
        offset = int(cache.get("scanned_bytes", 0))
        tip_height = int(cache.get("tip_height", -1))
        tip_hash = cache.get("tip_hash")
        rescan = False
        if offset > 0 and not os.path.exists(self.chain_path):
            raise FileNotFoundError(f"chain file missing: {self.chain_path}")
        total = os.path.getsize(self.chain_path) if os.path.exists(self.chain_path) else 0
        if offset > total:  # chain file shrank (should not happen): rescan
            offset, tip_height, tip_hash = 0, -1, None
            utxos, history = {}, []
            rescan = True
        scanned = new = 0
        with open(self.chain_path, "rb") as f:
            if offset:
                f.seek(offset)
                # Continuity: the next record's prev must be our tip.
                pos = f.tell()
                line = f.readline()
                if line.strip():
                    try:
                        first = json.loads(line.decode())
                        if first.get("prev") != tip_hash:
                            rescan = True
                    except ValueError:
                        rescan = True
                if rescan:
                    f.seek(0)
                    offset, tip_height, tip_hash = 0, -1, None
                    utxos, history = {}, []
                else:
                    f.seek(pos)
            while True:
                line = f.readline()
                if not line:
                    break
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line.decode())
                except ValueError:
                    break  # corrupt tail: stop, keep what we have
                scanned += 1
                height = int(rec["height"])
                if height > tip_height:
                    new += 1
                    tip_height, tip_hash = height, rec["hash"]
                # Same-height records (a side branch appended after the
                # tip) do not move the tip: the tip is the highest
                # record, last one wins on ties.
                _apply_record_txs(rec, watched, utxos, history)
                if progress and scanned % 5000 == 0:
                    progress(scanned, height)
                offset = f.tell()
        # Write the cache back, grouped by lock.
        grouped = {}
        for (txid, vout), u in utxos.items():
            grouped.setdefault(u["lock"], []).append({
                "txid": txid, "vout": vout, "value": u["value"],
                "height": u["height"], "coinbase": u["coinbase"],
                "cb_h": u["cb_h"]})
        cache["scanned_bytes"] = offset
        cache["tip_height"] = tip_height
        cache["tip_hash"] = tip_hash
        cache["utxos"] = grouped
        cache["history"] = history[-5000:]  # bounded: last 5000 events
        self._save_cache()
        return {"scanned_records": scanned, "new_records": new,
                "tip_height": tip_height, "tip_hash": tip_hash,
                "source": "local-chain-scan", "rescan": rescan}

    def apply_blocks(self, blocks, start_height, watched_locks):
        """Apply P2P-fetched blocks (wire dicts, forward order) to the
        ledger cache. blocks must already be header+merkle-verified by
        p2p_sync. start_height is the height of blocks[0].
        Returns {"applied": n, "tip_height": h, "tip_hash": hex}."""
        from genesis_fork import ser_header, sha256d
        cache = self._load_cache()
        watched = {bytes(lk) for lk in watched_locks}
        utxos = {}
        for lock_hex, rows in cache.get("utxos", {}).items():
            for r in rows:
                utxos[(r["txid"], r["vout"])] = {
                    "lock": lock_hex, "value": r["value"],
                    "height": r["height"], "coinbase": r["coinbase"],
                    "cb_h": r["cb_h"]}
        history = list(cache.get("history", []))
        tip_height, tip_hash = int(cache.get("tip_height", -1)), None
        for i, blk in enumerate(blocks):
            height = start_height + i
            hh = sha256d(ser_header(
                blk["version"], bytes.fromhex(blk["prev"]),
                bytes.fromhex(blk["merkle"]), blk["time"], blk["bits"],
                blk["nonce"])).hex()
            _apply_record_txs({"height": height, "txs": blk["txs"]},
                              watched, utxos, history)
            tip_height, tip_hash = height, hh
        grouped = {}
        for (txid, vout), u in utxos.items():
            grouped.setdefault(u["lock"], []).append({
                "txid": txid, "vout": vout, "value": u["value"],
                "height": u["height"], "coinbase": u["coinbase"],
                "cb_h": u["cb_h"]})
        cache["tip_height"] = tip_height
        cache["tip_hash"] = tip_hash
        cache["utxos"] = grouped
        # Dedupe history: a block applied twice (P2P then local scan)
        # must not double-count its events. UTXOs are keyed and already
        # idempotent; history is not.
        seen, deduped = set(), []
        for ev in history:
            k = (ev["txid"], ev["height"], ev["kind"], ev["value"],
                 ev["lock"])
            if k not in seen:
                seen.add(k)
                deduped.append(ev)
        cache["history"] = deduped[-5000:]
        self._save_cache()
        return {"applied": len(blocks), "tip_height": tip_height,
                "tip_hash": tip_hash}

    # ------------------------------------------------------------ views
    def cached_utxos(self, lock=None):
        """UTXOs from the local-scan cache: [{txid, vout, value, height,
        coinbase, cb_h, mature}] (mature at the cached tip)."""
        cache = self._load_cache()
        tip = int(cache.get("tip_height", -1))
        out = []
        groups = cache.get("utxos", {})
        locks = [lock.hex()] if lock is not None else list(groups)
        for lh in locks:
            for r in groups.get(lh, []):
                mature = (not r["coinbase"]
                          or tip + 1 - r["cb_h"] >= COINBASE_MATURITY)
                out.append({"txid": r["txid"], "vout": r["vout"],
                            "value": r["value"], "height": r["height"],
                            "coinbase": r["coinbase"], "cb_h": r["cb_h"],
                            "mature": mature, "lock": lh})
        return out

    def cached_balance(self):
        cache = self._load_cache()
        tip = int(cache.get("tip_height", -1))
        mature = immature = 0
        for r in self.cached_utxos():
            if r["mature"]:
                mature += r["value"]
            else:
                immature += r["value"]
        return {"mature": mature, "immature": immature,
                "tip_height": tip, "tip_hash": cache.get("tip_hash"),
                "source": "local-chain-scan"}

    def cached_history(self):
        return list(self._load_cache().get("history", []))

    def utxo_view(self, height):
        """{(txid_bytes, vout): [(value, lock, is_cb, cb_h)]} for
        validate_tx at `height` — from the local-scan cache."""
        view = {}
        for r in self.cached_utxos():
            key = (bytes.fromhex(r["txid"]), r["vout"])
            view.setdefault(key, []).append(
                (r["value"], bytes.fromhex(r["lock"]),
                 r["coinbase"], r["cb_h"]))
        return view
