"""EXCAL lock-aware Rosetta Construction API.

No wallet secrets are held here. External signers return native scriptSig
witnesses; this adapter assembles them, checks every lock and runs the exact
EXCAL consensus validator before returning or broadcasting a transaction.
Trifold and KNOT use explicit EXCAL extension signature types.
"""
import hashlib
import secp256k1 as secp
from txpq import decode_witness
from txscript import (
    parse_tx, ser_tx, txid_internal, sighash_all, hash160, lock_type,
    validate_tx, SIGHASH_ALL, COINBASE_MATURITY, parse_htlc_descriptor,
    parse_qhtlc_descriptor, parse_qhtlc_witness, parse_knot_witness,
    lock_htlc_for_descriptor, lock_qhtlc_for_descriptor,
    lock_knot_for_descriptor, lock_pqh_for_root, sign_knot_input,
)
from genesis_fork import (qlock_activation, qday_activation, htlc_activation,
                          qhtlc_activation, bridge_activation, knot_activation)

CURRENCY = {"symbol": "EXCAL", "decimals": 8}
TRIFOLD = "trifold"
KNOT = "excal_knot"
LOCKS = {"pkh", "open", "pqh", "htlc", "qhtlc", "bridge", "knot", "p2pk", "anyone"}


def coin_key(value):
    txid, sep, n = str(value).rpartition(":")
    if not sep or len(txid) != 64:
        raise ValueError("coin id must be display_txid:vout")
    return bytes.fromhex(txid)[::-1], int(n)


def lock_from_account(account):
    addr = (account or {}).get("address", "")
    if not isinstance(addr, str) or not addr.startswith("lock:"):
        raise ValueError("account must use lock:<script hex>")
    lock = bytes.fromhex(addr[5:])
    if lock_type(lock) not in LOCKS:
        raise ValueError("unknown EXCAL lock")
    return lock


def amount(op):
    a = op.get("amount") or {}
    if a.get("currency") != CURRENCY:
        raise ValueError("currency must be EXCAL (8 decimals)")
    return int(a["value"])


def active(lt, height):
    gates = {"pkh": qlock_activation(), "open": qlock_activation(),
             "pqh": qday_activation(), "htlc": htlc_activation(),
             "qhtlc": qhtlc_activation(), "bridge": bridge_activation(),
             "knot": knot_activation()}
    if lt in gates and height < gates[lt]:
        raise ValueError(f"{lt} not active at height {height}")
    if lt in ("p2pk", "anyone") and height >= qlock_activation():
        raise ValueError(f"legacy {lt} is retired")
    

class Construction:
    def __init__(self, chainstate, mempool=None, node=None):
        self.cs, self.mempool, self.node = chainstate, mempool, node

    def _input(self, coin):
        key = coin_key(coin)
        rows = self.cs.utxo.get(key)
        if not rows:
            raise ValueError("input UTXO unavailable or spent")
        value, lock, cb, cbh = rows[0]
        return {"coin": coin, "key": key, "value": int(value),
                "lock": bytes(lock), "type": lock_type(bytes(lock)),
                "coinbase": bool(cb), "cb_height": int(cbh)}

    def handle(self, path, body):
        height = int(self.cs.tip()["height"]) + 1
        if path == "/construction/derive":
            md = body.get("metadata") or {}
            if md.get("lock_hex"):
                lock = bytes.fromhex(md["lock_hex"])
                if lock_type(lock) not in LOCKS: raise ValueError("unknown lock")
            elif md.get("lock_type") == "pqh":
                lock = lock_pqh_for_root(bytes.fromhex(md["root"]))
            else:
                pub = bytes.fromhex(body["public_key"]["hex_bytes"])
                if len(pub) == 65 and pub[0] == 4:
                    pub = bytes([2 | (pub[64] & 1)]) + pub[1:33]
                if len(pub) != 33 or pub[0] not in (2, 3) or secp.decompress(pub) is None:
                    raise ValueError("invalid secp256k1 public key")
                lock = b"\x00" + hash160(pub)
            return {"account_identifier": {"address": "lock:" + lock.hex()}}

        if path == "/construction/preprocess":
            ins, outs, total_in, total_out, fee_op = [], [], 0, 0, 0
            for op in body.get("operations") or []:
                typ = op.get("type")
                if typ == "input":
                    coin = (op.get("coin_change") or {}).get("coin_identifier", {}).get("identifier")
                    live = self._input(coin)
                    if lock_from_account(op.get("account")) != live["lock"]:
                        raise ValueError("input account does not match UTXO lock")
                    if amount(op) != -live["value"]:
                        raise ValueError("input amount must equal negative UTXO value")
                    ins.append({"coin": coin, "value": live["value"],
                                "lock": live["lock"].hex(), "lock_type": live["type"]})
                    total_in += live["value"]
                elif typ == "output":
                    lock = lock_from_account(op.get("account"))
                    val = amount(op)
                    if val <= 0: raise ValueError("output must be positive")
                    outs.append({"value": val, "lock": lock.hex(), "lock_type": lock_type(lock)})
                    total_out += val
                elif typ == "fee":
                    v = amount(op)
                    if v >= 0: raise ValueError("fee must be negative")
                    fee_op += -v
                else:
                    raise ValueError("unsupported operation " + str(typ))
            if not ins or not outs or total_out >= total_in:
                raise ValueError("need inputs, outputs and positive fee")
            fee = total_in - total_out
            if fee_op and fee_op != fee: raise ValueError("fee operation does not reconcile")
            return {"options": {"inputs": ins, "outputs": outs, "fee": fee},
                    "required_public_keys": [],
                    "metadata": {"lock_types": sorted({x["lock_type"] for x in ins})}}

        if path == "/construction/metadata":
            opts = body.get("options") or {}
            ins, seen = [], set()
            for item in opts.get("inputs", []):
                live = self._input(item["coin"])
                if live["key"] in seen: raise ValueError("duplicate input")
                seen.add(live["key"])
                if live["value"] != int(item["value"]) or live["lock"].hex() != item["lock"]:
                    raise ValueError("UTXO changed after preprocess")
                if live["coinbase"] and height - live["cb_height"] < COINBASE_MATURITY:
                    raise ValueError("coinbase input immature")
                active(live["type"], height)
                ins.append({**item, "lock_type": live["type"],
                            "coinbase": live["coinbase"], "cb_height": live["cb_height"]})
            outs = opts.get("outputs") or []
            for out in outs:
                out_lock = bytes.fromhex(out["lock"])
                out_type = lock_type(out_lock)
                if out_type not in LOCKS: raise ValueError("unknown output lock")
                active(out_type, height)
            if sum(x["value"] for x in ins) - sum(int(x["value"]) for x in outs) != int(opts["fee"]):
                raise ValueError("input/output/fee values do not reconcile")
            return {"metadata": {"inputs": ins, "outputs": outs,
                                 "fee": int(opts["fee"]), "network_height": height}}

        if path == "/construction/payloads":
            md = body.get("metadata") or {}
            tx = {"version": 1, "vin": [], "vout": [], "locktime": 0}
            inputs = md.get("inputs", [])
            outputs = md.get("outputs", [])
            if not inputs or not outputs: raise ValueError("metadata requires inputs and outputs")
            total_in = 0
            for x in inputs:
                live = self._input(x["coin"])
                if live["lock"].hex() != x["lock"] or live["type"] != x["lock_type"]:
                    raise ValueError("UTXO lock/type changed")
                if live["value"] != int(x["value"]): raise ValueError("UTXO value changed")
                if live["coinbase"] and height - live["cb_height"] < COINBASE_MATURITY:
                    raise ValueError("coinbase input immature")
                active(live["type"], height)
                total_in += live["value"]
                tx["vin"].append({"prev": live["key"][0], "idx": live["key"][1],
                                  "script": b"", "seq": 0xffffffff})
            total_out = 0
            for x in outputs:
                lock = bytes.fromhex(x["lock"])
                lt = lock_type(lock)
                if lt not in LOCKS or lt != x.get("lock_type"):
                    raise ValueError("unknown output lock or lock type mismatch")
                active(lt, height)
                value = int(x["value"])
                if value <= 0: raise ValueError("output value must be positive")
                total_out += value
                tx["vout"].append({"value": value, "script": lock})
            if total_in - total_out != int(md.get("fee", -1)) or int(md.get("fee", 0)) <= 0:
                raise ValueError("input/output/fee values do not reconcile")
            payloads = []
            for i, x in enumerate(md["inputs"]):
                lock, lt = bytes.fromhex(x["lock"]), x["lock_type"]
                if lt in ("open", "anyone"): continue
                st = TRIFOLD if lt in ("pqh", "qhtlc") else KNOT if lt == "knot" else "ecdsa"
                payloads.append({"account_identifier": {"address": "lock:" + lock.hex()},
                    "hex_bytes": sighash_all(tx, i, lock).hex(), "signature_type": st})
            return {"unsigned_transaction": ser_tx(tx).hex(), "payloads": payloads}

        if path == "/construction/combine":
            tx = parse_tx(bytes.fromhex(body["unsigned_transaction"]))
            if any(v["script"] for v in tx["vin"]): raise ValueError("transaction is not unsigned")
            live_inputs = [self._input(v["prev"][::-1].hex()+":"+str(v["idx"])) for v in tx["vin"]]
            sigmap = {}
            for s in body.get("signatures") or []:
                p = s.get("signing_payload") or {}
                k = (p.get("hex_bytes", "").lower(), s.get("signature_type"))
                if k in sigmap: raise ValueError("duplicate signature")
                sigmap[k] = s
            for i, live in enumerate(live_inputs):
                lock, lt = live["lock"], live["type"]
                if lt in ("open", "anyone"): continue
                digest = sighash_all(tx, i, lock).hex()
                if lt in ("pqh", "qhtlc"):
                    s = sigmap.get((digest, TRIFOLD))
                    if not s: raise ValueError(f"input {i}: missing Trifold witness")
                    wit = bytes.fromhex(s["hex_bytes"])
                    if lt == "pqh":
                        root, _ = decode_witness(wit)
                        if hash160(root) != lock[1:]: raise ValueError("PQH root mismatch")
                    else:
                        mode, root, _sig, secret, desc = parse_qhtlc_witness(wit)
                        d = parse_qhtlc_descriptor(desc)
                        if lock_qhtlc_for_descriptor(desc) != lock: raise ValueError("QHTLC descriptor mismatch")
                        if mode == 1 and hashlib.sha256(secret).digest() != d["secret_hash"]:
                            raise ValueError("QHTLC secret mismatch")
                    tx["vin"][i]["script"] = wit
                    continue
                if lt == "knot":
                    s = sigmap.get((digest, KNOT))
                    if not s: raise ValueError(f"input {i}: missing KNOT witness")
                    tstar, desc = parse_knot_witness(bytes.fromhex(s["hex_bytes"]))
                    if lock_knot_for_descriptor(desc) != lock: raise ValueError("KNOT descriptor mismatch")
                    tx["vin"][i]["script"] = sign_knot_input(tx, i, lock, tstar, desc)
                    continue
                s = sigmap.get((digest, "ecdsa"))
                if not s: raise ValueError(f"input {i}: missing ECDSA signature")
                sig = bytes.fromhex(s["hex_bytes"])
                pub = bytes.fromhex(s["public_key"]["hex_bytes"]) if s.get("public_key") else b""
                if len(sig) != 64: raise ValueError("ECDSA signature must be 64-byte compact")
                if lt in ("pkh", "bridge"):
                    pub_wire = pub
                    if len(pub_wire) == 65 and pub_wire[0] == 4:
                        pub_verify = bytes([2 | (pub_wire[64] & 1)]) + pub_wire[1:33]
                        point = secp.decompress(pub_verify)
                        supplied = (int.from_bytes(pub_wire[1:33], "big"),
                                    int.from_bytes(pub_wire[33:65], "big"))
                        if point != supplied: raise ValueError("invalid uncompressed public key point")
                    elif len(pub_wire) == 33 and pub_wire[0] in (2,3):
                        pub_verify = pub_wire
                    else:
                        raise ValueError("invalid secp256k1 public key")
                    if lt == "pkh" and hash160(pub_wire) != lock[1:]:
                        raise ValueError("PKH key mismatch")
                    if lt == "bridge" and pub_wire[1:33] != lock[1:]:
                        raise ValueError("BRIDGE x mismatch")
                    if not secp.verify(pub_verify, sig, bytes.fromhex(digest)):
                        raise ValueError("ECDSA invalid")
                    tx["vin"][i]["script"] = pub_wire + sig + bytes([SIGHASH_ALL])
                elif lt == "htlc":
                    m = s.get("metadata") or {}
                    desc = bytes.fromhex(m["descriptor"])
                    d = parse_htlc_descriptor(desc)
                    if lock_htlc_for_descriptor(desc) != lock: raise ValueError("HTLC descriptor mismatch")
                    mode = m.get("mode")
                    secret = bytes.fromhex(m["secret"]) if m.get("secret") else None
                    if len(pub) == 65 and pub[0] == 4: pub = bytes([2 | (pub[64]&1)]) + pub[1:33]
                    if len(pub) != 33 or not secp.verify(pub, sig, bytes.fromhex(digest)): raise ValueError("HTLC signature invalid")
                    if mode == "claim" and pub == d["claim_pubkey"] and len(secret or b"")==32 and hashlib.sha256(secret).digest()==d["secret_hash"]:
                        tx["vin"][i]["script"] = b"\x01"+pub+sig+bytes([SIGHASH_ALL])+secret+desc
                    elif mode == "refund" and pub == d["refund_pubkey"]:
                        tx["vin"][i]["script"] = b"\x02"+pub+sig+bytes([SIGHASH_ALL])+desc
                    else: raise ValueError("HTLC mode/key/secret mismatch")
                elif lt == "p2pk":
                    tx["vin"][i]["script"] = bytes([65])+sig+bytes([SIGHASH_ALL])
                else: raise ValueError("unsupported input lock " + str(lt))
            raw = ser_tx(tx)
            chain_pairs = getattr(self.cs, "spent_pqh_pairs", None)
            if self.mempool is not None and self.mempool.chain_spent_pairs is not None:
                chain_pairs = self.mempool.chain_spent_pairs
            spent = set(chain_pairs) if chain_pairs is not None else set()
            ok, reason, fee = validate_tx(raw, self.cs.utxo, height, spent_pairs=spent)
            if not ok: raise ValueError("EXCAL consensus rejected tx: " + reason)
            return {"signed_transaction": raw.hex(),
                    "transaction_identifier": {"hash": txid_internal(raw)[::-1].hex()},
                    "fee": str(fee)}

        if path == "/construction/parse":
            tx = parse_tx(bytes.fromhex(body["transaction"]))
            ops = []
            for vin in tx["vin"]:
                live = self._input(vin["prev"][::-1].hex()+":"+str(vin["idx"]))
                ops.append({"operation_identifier":{"index":len(ops)},"type":"input",
                    "account":{"address":"lock:"+live["lock"].hex()},
                    "amount":{"value":str(-live["value"]),"currency":CURRENCY},
                    "coin_change":{"coin_identifier":{"identifier":live["coin"]},"coin_action":"coin_spent"},
                    "metadata":{"lock_type":live["type"],"witness_hex":vin["script"].hex()}})
            for out in tx["vout"]:
                lock=bytes(out["script"])
                ops.append({"operation_identifier":{"index":len(ops)},"type":"output",
                    "account":{"address":"lock:"+lock.hex()},
                    "amount":{"value":str(int(out["value"])),"currency":CURRENCY},
                    "metadata":{"lock_type":lock_type(lock)}})
            return {"operations":ops,"account_identifier_signers":[]}
        if path == "/construction/hash":
            raw=bytes.fromhex(body["signed_transaction"]); parse_tx(raw)
            return {"transaction_identifier":{"hash":txid_internal(raw)[::-1].hex()}}
        if path == "/construction/submit":
            raw=bytes.fromhex(body["signed_transaction"]); parse_tx(raw)
            if self.node is None: raise ValueError("broadcast requires embedded live Node")
            node_txid=self.node.dispatch("sendrawtransaction",[raw.hex()])
            return {"transaction_identifier":{"hash":txid_internal(raw)[::-1].hex()},
                    "metadata":{"node_txid_internal":node_txid,"broadcast":True}}
        raise KeyError("unknown construction endpoint")
