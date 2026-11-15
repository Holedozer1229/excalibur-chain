"""broadcast.py — submit locally-built, locally-verified transactions.

Added 2026-11-14 at Lux's direction ("enable broadcasting",
scope: Fork + Bitcoin). This reverses the wallet's original
deliberate design (build/sign/verify only, never broadcast) — but
only in one narrow, gated place:

  * broadcast NEVER builds or signs anything. It takes a raw tx
    (from `wallet send --save` or `--tx HEX`) that was already built,
    signed and locally verified, and re-checks it before submitting.
  * broadcast NEVER runs without `--yes` on the CLI (an explicit,
    per-broadcast decision — the full spend-and-sign protocol still
    applies: a broadcast is a spend, and every spend needs Lux's
    explicit yes for that exact action).
  * broadcast NEVER invents a destination. Fork txs go to the fork
    node only (127.0.0.1:9432 `sendrawtransaction`); Bitcoin txs go
    to a Bitcoin Core node only (default 127.0.0.1:8332, HTTP Basic
    auth from env vars or a 0600 config file — never from chat, never
    logged).

Pre-flight checks, in order (any failure refuses, nothing is sent):
  1. the hex parses as a transaction;
  2. REPLAY: the tx's shape must match its network — a fork tx
     (every output is a 21-byte opcode-free lock) is refused on the
     Bitcoin path, and a Bitcoin tx (real scripts) is refused on the
     fork path. The two chains cannot replay each other's txs, and
     this module enforces that structurally before any network call;
  3. FORK: the tx is re-validated locally with the fork's own
     validate_tx against the UTXO view from the saved build (or a
     supplied view), at the current tip+1;
  4. DOUBLE-SPEND: every input is checked still-unspent right before
     submit (fork: node getutxos per input lock; Bitcoin: gettxout);
  5. BITCOIN: testmempoolaccept must allow the tx (an
     already-in-mempool result counts as allowed — idempotent);
  6. after submit, the returned txid must equal the locally computed
     txid, and the tx must be visible in the mempool — otherwise the
     broadcast is reported as UNVERIFIED, not as sent.

A record of every broadcast (txid, network, height, result — never
any key, password or raw tx) is appended to
<datadir>/broadcast_log.jsonl (0600).
"""
import base64
import http.client
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from txscript import (parse_tx, ser_tx, txid_display, txid_internal,
                      validate_tx, lock_type)
from .ledger import RpcClient, RpcError

DEFAULT_FORK_HOST = "127.0.0.1"
DEFAULT_FORK_PORT = 9432
DEFAULT_BTC_HOST = "127.0.0.1"
DEFAULT_BTC_PORT = 8332
MAX_TX_BYTES = 100_000  # fork mempool / Bitcoin standardness bound


class BroadcastError(Exception):
    pass


# ------------------------------------------------------------------ parsing
def parse_raw_tx(raw_hex):
    """(raw bytes, parsed dict, display txid, internal txid hex).

    Raises BroadcastError on bad hex, oversize tx, or unparsable tx."""
    try:
        raw = bytes.fromhex(raw_hex.strip())
    except (ValueError, AttributeError):
        raise BroadcastError("raw tx is not valid hex")
    if not raw:
        raise BroadcastError("raw tx is empty")
    if len(raw) > MAX_TX_BYTES:
        raise BroadcastError(
            f"raw tx is {len(raw)} bytes (limit {MAX_TX_BYTES})")
    try:
        parsed = parse_tx(raw)
    except ValueError as e:
        raise BroadcastError(f"raw tx does not parse: {e}")
    if parsed["version"] != 1:
        raise BroadcastError(
            f"unsupported tx version {parsed['version']} (want 1)")
    if parsed["locktime"] != 0:
        raise BroadcastError("locktime != 0 (unsupported by this wallet)")
    return raw, parsed, txid_display(raw), txid_internal(raw).hex()


def looks_like_fork_tx(parsed):
    """True when EVERY output is a fork lock (opcode-free, 21 bytes or
    the 1-byte OPEN lock). A Bitcoin tx's outputs are scripts, so this
    is False for any real Bitcoin tx."""
    outs = parsed["vout"]
    if not outs:
        return False
    return all(lock_type(bytes(o["script"])) is not None for o in outs)


def check_replay_safe(parsed, network):
    """Structural replay protection. Refuses a tx on the wrong chain
    before any network call. Returns 'fork' or 'bitcoin'."""
    is_fork = looks_like_fork_tx(parsed)
    if network == "fork" and not is_fork:
        raise BroadcastError(
            "REFUSED (replay): this tx has Bitcoin-style script "
            "outputs, not fork locks — it is not a fork tx and will "
            "not be submitted to the fork node")
    if network == "bitcoin" and is_fork:
        raise BroadcastError(
            "REFUSED (replay): this tx has fork lock outputs, not "
            "Bitcoin scripts — it is not a Bitcoin tx and will not "
            "be submitted to a Bitcoin node")
    return network


# ------------------------------------------------------------- fork path
def _view_from_inputs(inputs):
    """{(txid_bytes, vout): [(value, lock, is_cb, cb_h)]} for
    validate_tx. inputs: [{txid, vout, value, lock, coinbase, cb_h}]."""
    view = {}
    for u in inputs:
        key = (bytes.fromhex(u["txid"]), int(u["vout"]))
        view.setdefault(key, []).append(
            (int(u["value"]), bytes.fromhex(u["lock"]),
             bool(u.get("coinbase", False)), int(u.get("cb_h", 0))))
    return view


def check_inputs_unspent_fork(inputs, rpc):
    """Every input must still be an unspent UTXO on the fork node.
    Raises BroadcastError naming the first spent/missing input."""
    for u in inputs:
        rows = rpc.getutxos(bytes.fromhex(u["lock"]))
        if not any(r["txid"] == u["txid"] and int(r["vout"]) == int(u["vout"])
                   for r in rows):
            raise BroadcastError(
                f"DOUBLE-SPEND REFUSED: input {u['txid']}:{u['vout']} "
                f"is already spent or unknown to the node — the tx "
                f"was built on a stale UTXO set; rebuild it")


def broadcast_fork(raw_hex, rpc=None, inputs=None, height=None,
                   dry_run=False):
    """Submit a fork tx. inputs (optional, from the saved build) let
    this re-validate locally and check inputs unspent. Returns
    {"network", "txid", "txid_internal", "mempool": bool,
     "dry_run": bool, "fee": int}."""
    raw, parsed, txid, txid_int = parse_raw_tx(raw_hex)
    check_replay_safe(parsed, "fork")
    rpc = rpc or RpcClient(DEFAULT_FORK_HOST, DEFAULT_FORK_PORT)
    if height is None:
        # No saved height (raw --tx): need the live tip. If the node
        # is down this refuses here — fail closed, before any submit.
        try:
            height, _th = rpc.tip()
            height += 1
        except RpcError as e:
            raise BroadcastError(f"fork node unreachable: {e}")
    # A saved build carries its validated_at_height: re-validate at
    # that height (the node is the final arbiter at submit time, and
    # the unspent check below still needs the node up).
    if inputs:
        view = _view_from_inputs(inputs)
        ok, reason, fee = validate_tx(raw, view, height)
        if not ok:
            raise BroadcastError(
                f"local re-validation failed at height {height}: {reason}")
        try:
            check_inputs_unspent_fork(inputs, rpc)
        except RpcError as e:
            raise BroadcastError(f"unspent check failed: {e}")
    else:
        fee = None
    if dry_run:
        return {"network": "fork", "txid": txid,
                "txid_internal": txid_int, "mempool": False,
                "dry_run": True, "fee": fee,
                "note": "dry run — validated, NOT submitted"}
    try:
        returned = rpc.call("sendrawtransaction", [raw.hex()])
    except RpcError as e:
        raise BroadcastError(f"fork node rejected the tx: {e}")
    if str(returned) != txid_int:
        raise BroadcastError(
            f"node returned txid {returned}, local txid is {txid_int} "
            f"(display {txid}) — broadcast UNVERIFIED, do not assume "
            f"it is in the mempool")
    try:
        mempool = rpc.call("getrawmempool")
    except RpcError:
        mempool = []
    in_mempool = txid_int in mempool or txid in mempool
    if not in_mempool:
        raise BroadcastError(
            f"node accepted tx {txid} but it is not visible in the "
            f"mempool — broadcast UNVERIFIED, check the node log")
    return {"network": "fork", "txid": txid, "txid_internal": txid_int,
            "mempool": True, "dry_run": False, "fee": fee}


# ---------------------------------------------------------- bitcoin path
class BitcoinRpcClient:
    """Minimal authenticated JSON-RPC client for Bitcoin Core
    (stdlib http.client). Credentials never leave this object and are
    never logged."""

    def __init__(self, host=DEFAULT_BTC_HOST, port=DEFAULT_BTC_PORT,
                 user=None, password=None, timeout=30):
        if user is None or password is None:
            raise BroadcastError(
                "Bitcoin RPC needs credentials: set "
                "EXCAL_BTC_RPC_USER / EXCAL_BTC_RPC_PASSWORD, or pass "
                "--btc-rpc-config <0600 bitcoin.conf> (rpcuser= / "
                "rpcpassword= lines)")
        self.host, self.port, self.timeout = host, port, timeout
        creds = base64.b64encode(f"{user}:{password}".encode()).decode()
        self._auth = f"Basic {creds}"

    def call(self, method, params=None):
        body = json.dumps({"method": method, "params": params or [],
                           "jsonrpc": "2.0", "id": "excalibur-broadcast"
                           }).encode()
        conn = http.client.HTTPConnection(self.host, self.port,
                                         timeout=self.timeout)
        try:
            conn.request("POST", "/", body,
                         {"Content-Type": "application/json",
                          "Authorization": self._auth})
            resp = conn.getresponse()
            raw = resp.read()
        except (OSError, http.client.HTTPException) as e:
            raise BroadcastError(f"Bitcoin RPC {method} failed: {e}")
        finally:
            conn.close()
        try:
            data = json.loads(raw.decode())
        except ValueError:
            raise BroadcastError(
                f"Bitcoin RPC {method}: non-JSON reply: {raw[:120]!r}")
        if data.get("error") is not None:
            raise BroadcastError(
                f"Bitcoin RPC {method}: {data['error']}")
        return data.get("result")

    def tip(self):
        return int(self.call("getblockcount"))

    def gettxout(self, txid, vout):
        """UTXO dict, or None when spent / unknown."""
        return self.call("gettxout", [txid, int(vout), True])


def load_btc_credentials(config_path=None):
    """(user, password) from env vars, else a bitcoin.conf file.
    Env wins. Raises BroadcastError when neither is available."""
    user = os.environ.get("EXCAL_BTC_RPC_USER")
    password = os.environ.get("EXCAL_BTC_RPC_PASSWORD")
    if user and password:
        return user, password
    path = config_path
    if path is None:
        cand = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "bitcoin", "data",
            "bitcoin.conf")
        path = cand if os.path.isfile(cand) else None
    if path is None:
        raise BroadcastError(
            "no Bitcoin RPC credentials: set EXCAL_BTC_RPC_USER / "
            "EXCAL_BTC_RPC_PASSWORD, or pass --btc-rpc-config "
            "<bitcoin.conf>")
    user = password = None
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line.startswith("rpcuser="):
                user = line.split("=", 1)[1].strip()
            elif line.startswith("rpcpassword="):
                password = line.split("=", 1)[1].strip()
    if not user or not password:
        raise BroadcastError(
            f"no rpcuser=/rpcpassword= in {path}")
    return user, password


def check_inputs_unspent_bitcoin(parsed, btc_rpc):
    """Every input must still be unspent on the Bitcoin node
    (gettxout returns a result). Raises BroadcastError otherwise."""
    for vin in parsed["vin"]:
        txid = vin["prev"][::-1].hex()
        if btc_rpc.gettxout(txid, int(vin["idx"])) is None:
            raise BroadcastError(
                f"DOUBLE-SPEND REFUSED: input {txid}:{vin['idx']} is "
                f"already spent or unknown to the Bitcoin node — "
                f"rebuild the tx on a fresh UTXO set")


def broadcast_bitcoin(raw_hex, btc_rpc=None, host=DEFAULT_BTC_HOST,
                      port=DEFAULT_BTC_PORT, config_path=None,
                      dry_run=False):
    """Submit a Bitcoin tx: testmempoolaccept first, then
    sendrawtransaction, then mempool verification. Returns the same
    result shape as broadcast_fork."""
    raw, parsed, txid, txid_int = parse_raw_tx(raw_hex)
    check_replay_safe(parsed, "bitcoin")
    if btc_rpc is None:
        user, password = load_btc_credentials(config_path)
        btc_rpc = BitcoinRpcClient(host, port, user, password)
    try:
        check_inputs_unspent_bitcoin(parsed, btc_rpc)
    except BroadcastError:
        raise
    except Exception as e:
        raise BroadcastError(f"Bitcoin unspent check failed: {e}")
    try:
        res = btc_rpc.call("testmempoolaccept", [raw.hex()])
    except BroadcastError as e:
        raise BroadcastError(f"testmempoolaccept failed: {e}")
    entry = res[0] if isinstance(res, list) and res else {}
    if not entry.get("allowed"):
        reason = entry.get("reject-reason", "unknown")
        if reason == "txn-already-in-mempool":
            return {"network": "bitcoin", "txid": txid,
                    "txid_internal": txid_int, "mempool": True,
                    "dry_run": dry_run, "fee": entry.get("fees", {})
                    .get("base") if isinstance(entry.get("fees"), dict)
                    else None,
                    "note": "already in mempool — nothing new submitted"}
        raise BroadcastError(
            f"Bitcoin node refuses the tx (testmempoolaccept): {reason}")
    if dry_run:
        return {"network": "bitcoin", "txid": txid,
                "txid_internal": txid_int, "mempool": False,
                "dry_run": True, "fee": None,
                "note": "dry run — testmempoolaccept OK, NOT submitted"}
    returned = btc_rpc.call("sendrawtransaction", [raw.hex()])
    if str(returned) != txid:
        raise BroadcastError(
            f"node returned txid {returned}, local txid is {txid} — "
            f"broadcast UNVERIFIED, do not assume it is in the mempool")
    entry = btc_rpc.call("getmempoolentry", [txid])
    if not entry:
        raise BroadcastError(
            f"node accepted tx {txid} but getmempoolentry is empty — "
            f"broadcast UNVERIFIED, check the node log")
    return {"network": "bitcoin", "txid": txid,
            "txid_internal": txid_int, "mempool": True,
            "dry_run": False, "fee": None}


# ------------------------------------------------------------------ log
def append_broadcast_log(datadir, record):
    """Append one broadcast record (no keys, no passwords, no raw tx).
    File is created 0600."""
    os.makedirs(datadir, exist_ok=True)
    path = os.path.join(datadir, "broadcast_log.jsonl")
    with open(path, "a") as f:
        f.write(json.dumps(record) + "\n")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path
