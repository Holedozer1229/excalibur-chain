#!/usr/bin/env python3
"""Native EXCAL Rosetta Data API adapter.

Reads the live ChainState object; it does not maintain a second ledger and
never mutates consensus state. Account identifiers preserve the exact native
locking script as "lock:<script hex>" so PKH, PQH, HTLC, QHTLC, BRIDGE and
other script forms are not collapsed into an ECDSA address.
"""
import argparse
import json
import os
import sys
import threading
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from txscript import parse_tx, txid_internal
from rosetta.construction import Construction

BLOCKCHAIN = "excal"
CURRENCY = {"symbol": "EXCAL", "decimals": 8}
CURRENCIES = {"mainnet": CURRENCY, "fork": CURRENCY,
              "testnet": {"symbol": "tEXCAL", "decimals": 8}}
NETWORK = "mainnet"
NETWORK_ID = {"blockchain": BLOCKCHAIN, "network": NETWORK}
ERRORS = [
    {"code": 1, "message": "invalid network identifier", "retriable": False},
    {"code": 2, "message": "block not found", "retriable": False},
    {"code": 3, "message": "transaction not found", "retriable": False},
    {"code": 4, "message": "invalid account identifier", "retriable": False},
    {"code": 5, "message": "historical balance lookup unsupported", "retriable": False},
    {"code": 6, "message": "construction or consensus validation failed", "retriable": False},
    {"code": 7, "message": "invalid request", "retriable": False},
]
ERROR_BY_CODE = {e["code"]: e for e in ERRORS}


def _display_hash(raw_hash):
    if isinstance(raw_hash, bytes):
        return raw_hash[::-1].hex()
    value = str(raw_hash)
    try:
        return bytes.fromhex(value)[::-1].hex()
    except ValueError:
        return value


def _script_account(script):
    return "lock:" + bytes(script).hex()


def _coinbase(tx):
    if len(tx["vin"]) != 1:
        return False
    vin = tx["vin"][0]
    return vin["prev"] == bytes(32) and vin["idx"] == 0xffffffff


def _outpoint(txid_wire, vout):
    return (bytes(txid_wire), int(vout))


class ExcalRosetta:
    """Rosetta Data API backed by a live ChainState instance."""

    def __init__(self, chainstate, network=NETWORK, mempool=None, node=None):
        self.cs = chainstate
        self.mempool = mempool
        self.node = node
        self.currency = CURRENCIES.get(network, CURRENCY)
        self.construction = Construction(chainstate, mempool, node, self.currency,
                                         self._historical_output)
        self.network = network
        self.network_id = {"blockchain": BLOCKCHAIN, "network": network}
        self.lock = threading.RLock()
        self._output_index = {}
        self._indexed_height = -1
        self._indexed_tip_hash = None

    def _ensure_output_index(self):
        """Incrementally index canonical outputs; rebuild after a reorg."""
        tip_height, tip_hash = self._tip()
        if self._indexed_height >= 0:
            indexed_record = self._record(self._indexed_height)
            if indexed_record is None or indexed_record["hash"] != self._indexed_tip_hash:
                self._output_index.clear()
                self._indexed_height = -1
        for height in range(self._indexed_height + 1, tip_height + 1):
            rec = self._record(height)
            if rec is None:
                raise ValueError("missing canonical block while indexing height " + str(height))
            for raw in rec.get("txs", []):
                tx = parse_tx(raw)
                txid = txid_internal(raw)
                for n, out in enumerate(tx["vout"]):
                    self._output_index[(txid, n)] = out
        self._indexed_height = tip_height
        self._indexed_tip_hash = tip_hash

    def _historical_output(self, outpoint):
        self._ensure_output_index()
        return self._output_index.get((bytes(outpoint[0]), int(outpoint[1])))

    def _mempool_transaction(self, raw):
        tx = parse_tx(raw)
        txid = txid_internal(raw)[::-1].hex()
        ops = []
        input_refs = []
        total_in = 0
        total_out = sum(int(out["value"]) for out in tx["vout"])
        for vin in tx["vin"]:
            key = (vin["prev"], int(vin["idx"]))
            rows = self.cs.utxo.get(key)
            if not rows:
                raise ValueError("mempool input prevout unavailable")
            value, lock, _cb, _cbh = rows[0]
            total_in += int(value)
            idx = len(ops)
            input_refs.append({"index": idx})
            ops.append({
                "operation_identifier": {"index": idx},
                "type": "transfer", "status": "success",
                "account": {"address": _script_account(lock)},
                "amount": {"value": str(-int(value)), "currency": self.currency},
                "coin_change": {"coin_identifier": {"identifier": vin["prev"][::-1].hex() + ":" + str(vin["idx"])},
                                "coin_action": "coin_spent"},
            })
        for n, out in enumerate(tx["vout"]):
            idx = len(ops)
            ops.append({
                "operation_identifier": {"index": idx},
                "type": "transfer", "status": "success",
                "account": {"address": _script_account(out["script"])},
                "amount": {"value": str(int(out["value"])), "currency": self.currency},
                "related_operations": input_refs,
                "coin_change": {"coin_identifier": {"identifier": txid + ":" + str(n)},
                                "coin_action": "coin_created"},
            })
        fee = total_in - total_out
        if fee < 0:
            raise ValueError("mempool outputs exceed resolved input value")
        return {"transaction_identifier": {"hash": txid}, "operations": ops,
                "metadata": {"raw_transaction": raw.hex(),
                             "input_count": len(tx["vin"]),
                             "output_count": len(tx["vout"]),
                             "fee": str(fee)}}

    def _error(self, code, message=None):
        e = dict(ERROR_BY_CODE[code])
        if message:
            e["message"] = str(message)[:256]
        return e

    def _check_network(self, body):
        if body.get("network_identifier") != self.network_id:
            return self._error(1)
        return None

    def _tip(self):
        tip = self.cs.tip()
        return int(tip["height"]), tip["hash"]

    def _record(self, height):
        rec = self.cs.by_height.get(int(height))
        if rec is None:
            return None
        return rec

    def _record_identifier(self, rec):
        return {"index": int(rec["height"]), "hash": _display_hash(rec["hash"])}

    def _block(self, height):
        rec = self._record(height)
        if rec is None:
            return None
        prev = self._record(height - 1) if int(height) > 0 else None
        parent = (self._record_identifier(prev) if prev is not None
                  else self._record_identifier(rec))
        raws = rec.get("txs", [])
        # Index canonical outputs once and incrementally as the chain grows.
        self._ensure_output_index()
        outputs = self._output_index
        transactions = []
        for raw in raws:
            t = parse_tx(raw)
            tid = txid_internal(raw)
            tx_hash = tid[::-1].hex()
            ops = []
            total_in = 0
            total_out = sum(int(out["value"]) for out in t["vout"])
            fee = 0
            if _coinbase(t):
                for n, out in enumerate(t["vout"]):
                    ops.append({
                        "operation_identifier": {"index": len(ops)},
                        "type": "coinbase", "status": "success",
                        "account": {"address": _script_account(out["script"])},
                        "amount": {"value": str(int(out["value"])), "currency": self.currency},
                        "coin_change": {"coin_identifier": {"identifier": tx_hash + ":" + str(n)},
                                        "coin_action": "coin_created"},
                    })
            else:
                for vin in t["vin"]:
                    prevout = outputs.get((vin["prev"], int(vin["idx"])))
                    if prevout is None:
                        # A missing historical prevout must never be disguised
                        # as a known account or silently assigned to a user.
                        raise ValueError("canonical input prevout unavailable at height " + str(height))
                    n = len(ops)
                    ops.append({
                        "operation_identifier": {"index": n},
                        "type": "transfer", "status": "success",
                        "account": {"address": _script_account(prevout["script"])},
                        "amount": {"value": str(-int(prevout["value"])), "currency": self.currency},
                        "coin_change": {"coin_identifier": {"identifier": vin["prev"][::-1].hex() + ":" + str(vin["idx"])},
                                        "coin_action": "coin_spent"},
                    })
                fee = total_in - total_out
                if fee < 0:
                    raise ValueError("transaction outputs exceed resolved input value")
                input_indices = [{"index": i} for i in range(len(ops))]
                for n, out in enumerate(t["vout"]):
                    idx = len(ops)
                    op = {
                        "operation_identifier": {"index": idx},
                        "type": "transfer", "status": "success",
                        "account": {"address": _script_account(out["script"])},
                        "amount": {"value": str(int(out["value"])), "currency": self.currency},
                        "coin_change": {"coin_identifier": {"identifier": tx_hash + ":" + str(n)},
                                        "coin_action": "coin_created"},
                    }
                    if input_indices:
                        op["related_operations"] = input_indices
                    ops.append(op)
            transactions.append({
                "transaction_identifier": {"hash": tx_hash},
                "operations": ops,
                "metadata": {"lock_time": int(t["locktime"]), "version": int(t["version"]),
                             "fee": str(fee)},
            })
        timestamp = int(rec.get("time", 0)) * 1000
        return {
            "block_identifier": self._record_identifier(rec),
            "parent_block_identifier": parent,
            "timestamp": timestamp,
            "transactions": transactions,
            "metadata": {"bits": int(rec.get("bits", 0)), "nonce": int(rec.get("nonce", 0)),
                         "version": int(rec.get("version", 0))},
        }

    def handle(self, path, body):
        if path == "/network/list":
            return 200, {"network_identifiers": [self.network_id]}
        if path == "/network/options":
            err = self._check_network(body)
            if err:
                return 500, err
            return 200, {
                "version": {"rosetta_version": "1.4.13", "node_version": "EXCAL-native",
                            "middleware_version": "excal-rosetta/1.0.0"},
                "allow": {"operation_statuses": [{"status": "success", "successful": True},
                                                  {"status": "failure", "successful": False}],
                          "operation_types": ["coinbase", "transfer", "input", "output", "fee"],
                          "errors": ERRORS, "historical_balance_lookup": False,
                          "call_methods": [], "balance_exemptions": []},
                "metadata": {"excal_extensions": {
                    "trifold_signature_type": "trifold",
                    "knot_signature_type": "excal_knot",
                    "witness_encoding": "native scriptSig hex"}},
            }
        err = self._check_network(body)
        if err:
            return 500, err
        if path == "/network/status":
            with self.lock:
                height, block_hash = self._tip()
                current = self._block(height)
                genesis = self._record(0)
                if current is None or genesis is None:
                    return 500, self._error(2, "chainstate has no complete genesis/tip")
                peers = []
                if self.node is not None and getattr(self.node, "peermgr", None):
                    for _session, address in self.node.peermgr.peers:
                        peer = f"{address[0]}:{address[1]}"
                        peers.append({"peer_id": peer, "metadata": {"address": peer}})
                return 200, {
                    "current_block_identifier": current["block_identifier"],
                    "current_block_timestamp": current["timestamp"],
                    "genesis_block_identifier": self._record_identifier(genesis),
                    "peers": peers,
                }
        if path == "/block":
            ident = body.get("block_identifier") or {}
            with self.lock:
                height = ident.get("index")
                if height is None and ident.get("hash"):
                    wanted = ident["hash"].lower()
                    height = next((h for h, r in self.cs.by_height.items()
                                   if _display_hash(r["hash"]) == wanted), None)
                if height is None:
                    height = self._tip()[0]
                block = self._block(int(height))
                if block is None:
                    return 500, self._error(2)
                if ident.get("hash") and block["block_identifier"]["hash"] != ident["hash"].lower():
                    return 500, self._error(2)
                return 200, {"block": block}
        if path == "/block/transaction":
            ident = body.get("block_identifier") or {}
            txid = (body.get("transaction_identifier") or {}).get("hash")
            if not txid:
                return 500, self._error(7, "transaction_identifier.hash required")
            with self.lock:
                height = ident.get("index")
                if height is None and ident.get("hash"):
                    height = next((h for h, r in self.cs.by_height.items()
                                   if _display_hash(r["hash"]) == ident["hash"].lower()), None)
                if height is None:
                    return 500, self._error(2)
                block = self._block(int(height))
                if block is None:
                    return 500, self._error(2)
                for tx in block["transactions"]:
                    if tx["transaction_identifier"]["hash"] == txid.lower():
                        return 200, {"transaction": tx}
                return 500, self._error(3)
        if path == "/account/balance":
            account = body.get("account_identifier") or {}
            address = account.get("address", "")
            if not isinstance(address, str) or not address.startswith("lock:"):
                return 500, self._error(4, "address must be lock:<exact locking-script hex>")
            try:
                script = bytes.fromhex(address[5:])
            except ValueError:
                return 500, self._error(4, "locking script is not valid hex")
            if not script:
                return 500, self._error(4, "empty locking script")
            with self.lock:
                height, block_hash = self._tip()
                requested = body.get("block_identifier")
                if requested:
                    if requested.get("index", height) != height:
                        return 500, self._error(5)
                    if requested.get("hash") and requested["hash"].lower() != _display_hash(block_hash):
                        return 500, self._error(5)
                total = 0
                count = 0
                finder = getattr(self.cs.utxo, "find_by_spk", None)
                if callable(finder):
                    matches = finder(script)
                else:
                    matches = []
                    for key, entries in self.cs.utxo.items():
                        if isinstance(entries, tuple):
                            entries = [entries]
                        for entry in entries:
                            if bytes(entry[1]) == script:
                                matches.append((key, entry))
                for _key, entry in matches:
                    total += int(entry[0])
                    count += 1
                return 200, {
                    "block_identifier": {"index": height, "hash": _display_hash(block_hash)},
                    "balances": [{"value": str(total), "currency": self.currency}],
                    "metadata": {"utxo_count": count},
                }
        if path == "/mempool":
            if self.mempool is None:
                return 500, self._error(7, "live mempool is not connected")
            with self.lock:
                ids = [{"hash": txid_internal(raw)[::-1].hex()}
                       for raw in self.mempool.txs.values()]
            return 200, {"transaction_identifiers": ids}
        if path == "/mempool/transaction":
            if self.mempool is None:
                return 500, self._error(7, "live mempool is not connected")
            wanted = (body.get("transaction_identifier") or {}).get("hash", "").lower()
            with self.lock:
                raw = next((raw for raw in self.mempool.txs.values()
                            if txid_internal(raw)[::-1].hex() == wanted), None)
                if raw is None:
                    return 500, self._error(3)
                return 200, {"transaction": self._mempool_transaction(raw)}
        if path.startswith("/construction/"):
            try:
                return 200, self.construction.handle(path, body)
            except KeyError as exc:
                return 404, self._error(7, str(exc))
            except Exception as exc:
                return 500, self._error(6, str(exc))
        return 404, self._error(7, "unknown endpoint")


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            if self.path == "/health":
                try:
                    height, block_hash = app._tip()
                    self._reply(200, {"ok": True, "height": height,
                                      "block_hash": _display_hash(block_hash)})
                except Exception as exc:
                    self._reply(503, {"ok": False, "error": str(exc)[:200]})
            else:
                self._reply(404, {"error": "not found"})

        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 2_000_000:
                    raise ValueError("invalid Content-Length")
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(body, dict):
                    raise ValueError("request body must be a JSON object")
                status, result = app.handle(self.path, body)
                self._reply(status, result)
            except Exception as exc:
                self._reply(500, app._error(7, str(exc)))

        def _reply(self, status, obj):
            raw = json.dumps(obj, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)

    return Handler


def serve(chainstate, host="127.0.0.1", port=8070, network=NETWORK, mempool=None, node=None):
    app = ExcalRosetta(chainstate, network=network, mempool=mempool, node=node)
    server = ThreadingHTTPServer((host, int(port)), make_handler(app))
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="EXCAL Rosetta Data API")
    parser.add_argument("--data-dir", required=True, help="EXCAL ChainState data directory")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8070)
    parser.add_argument("--network", default=NETWORK, choices=["mainnet", "testnet", "fork"])
    args = parser.parse_args()
    from chainstate import ChainState
    cs = ChainState(args.data_dir).load()
    serve(cs, args.host, args.port, args.network)


if __name__ == "__main__":
    main()
