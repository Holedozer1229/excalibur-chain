"""Rosetta construction helpers for native EXCAL transactions.

Initial safe scope: PKH inputs and OPEN/anyone inputs. PQH, HTLC, QHTLC,
Bridge, KNOT and legacy P2PK are rejected until their exact signing flows
are represented and covered by vectors. No fallback signing is permitted.
"""
import json

import secp256k1 as secp
from txscript import (
    parse_tx, ser_tx, txid_internal, sighash_all, hash160, lock_type,
    validate_tx, SIGHASH_ALL,
)

CURRENCY = {"symbol": "EXCAL", "decimals": 8}
SUPPORTED_INPUTS = {"pkh", "open", "anyone"}


def _err(code, message):
    return {"code": code, "message": str(message)[:256], "retriable": False}


def _coin_id(value):
    if not isinstance(value, str) or ":" not in value:
        raise ValueError("coin_identifier.identifier must be display_txid:vout")
    txid, vout = value.rsplit(":", 1)
    if len(txid) != 64:
        raise ValueError("coin id txid must be 32-byte display-order hex")
    raw = bytes.fromhex(txid)[::-1]
    n = int(vout)
    if n < 0 or n > 0xffffffff:
        raise ValueError("vout out of range")
    return raw, n


def _account_lock(account):
    address = (account or {}).get("address", "")
    if not isinstance(address, str) or not address.startswith("lock:"):
        raise ValueError("account address must be lock:<scriptPubKey hex>")
    script = bytes.fromhex(address[5:])
    if not script or lock_type(script) is None:
        raise ValueError("unknown or empty EXCAL locking script")
    return script


def _amount(op):
    amount = op.get("amount") or {}
    if amount.get("currency") != CURRENCY:
        raise ValueError("operation currency must be EXCAL with 8 decimals")
    return int(amount["value"])


def _entry(utxo, key):
    entries = utxo.get(key)
    if not entries:
        raise ValueError("input UTXO not found or already spent")
    return entries[0]


class Construction:
    def __init__(self, chainstate, mempool=None):
        self.cs = chainstate
        self.mempool = mempool

    def handle(self, path, body):
        height = int(self.cs.tip()["height"]) + 1
        if path == "/construction/derive":
            pk = bytes.fromhex(body["public_key"]["hex_bytes"])
            if len(pk) not in (33, 65):
                raise ValueError("public key must be compressed or uncompressed secp256k1")
            if len(pk) == 65:
                pk = bytes([2 | (pk[64] & 1)]) + pk[1:33]
            if pk[0] not in (2, 3) or secp.decompress(pk) is None:
                raise ValueError("invalid secp256k1 public key")
            return {"account_identifier": {"address": "lock:" + (b"\x00" + hash160(pk)).hex()}}

        if path == "/construction/preprocess":
            operations = body.get("operations") or []
            inputs, outputs, required = [], [], []
            total_in = total_out = 0
            for op in operations:
                typ = op.get("type")
                if typ == "INPUT":
                    coin = (op.get("coin_change") or {}).get("coin_identifier", {}).get("identifier")
                    if not coin:
                        raise ValueError("INPUT operation requires coin_change.coin_identifier")
                    lock = _account_lock(op.get("account"))
                    lt = lock_type(lock)
                    if lt not in SUPPORTED_INPUTS:
                        raise ValueError("unsupported input lock type: " + str(lt))
                    value = _amount(op)
                    if value >= 0:
                        raise ValueError("INPUT amount must be negative")
                    inputs.append({"coin": coin, "account": op["account"]["address"],
                                   "value": -value, "lock": lock.hex(), "lock_type": lt})
                    total_in += -value
                    if lt == "pkh":
                        required.append(op["account"])
                elif typ == "OUTPUT":
                    lock = _account_lock(op.get("account"))
                    if lock_type(lock) not in ("pkh", "open", "anyone"):
                        raise ValueError("unsupported output lock type: " + str(lock_type(lock)))
                    value = _amount(op)
                    if value <= 0:
                        raise ValueError("OUTPUT amount must be positive")
                    outputs.append({"account": op["account"]["address"],
                                    "value": value, "lock": lock.hex()})
                    total_out += value
                elif typ == "FEE":
                    if _amount(op) >= 0:
                        raise ValueError("FEE amount must be negative")
                else:
                    raise ValueError("unsupported operation type: " + str(typ))
            if not inputs or not outputs:
                raise ValueError("at least one INPUT and one OUTPUT are required")
            if total_out >= total_in:
                raise ValueError("outputs must be less than inputs; fee must be positive")
            return {"options": {"inputs": inputs, "outputs": outputs,
                                "fee": total_in - total_out},
                    "required_public_keys": required}

        if path == "/construction/metadata":
            options = body.get("options") or {}
            checked = []
            for item in options.get("inputs", []):
                key = _coin_id(item["coin"])
                entry = _entry(self.cs.utxo, key)
                value, script, is_cb, cb_h = entry
                if int(value) != int(item["value"]) or bytes(script).hex() != item["lock"]:
                    raise ValueError("input metadata does not match live UTXO")
                if is_cb and (height < int(cb_h) or height - int(cb_h) < 100):
                    raise ValueError("coinbase input is immature")
                if lock_type(bytes(script)) not in SUPPORTED_INPUTS:
                    raise ValueError("input lock is not enabled for this Rosetta construction version")
                checked.append({"coin": item["coin"], "value": int(value),
                                "lock": bytes(script).hex(),
                                "lock_type": lock_type(bytes(script))})
            if not checked:
                raise ValueError("no inputs")
            return {"metadata": {"inputs": checked,
                                 "outputs": options.get("outputs", []),
                                 "fee": int(options["fee"]),
                                 "network_height": height}}

        if path == "/construction/payloads":
            metadata = body.get("metadata") or {}
            inputs = metadata.get("inputs") or []
            outputs = metadata.get("outputs") or []
            if not inputs or not outputs:
                raise ValueError("metadata must include inputs and outputs")
            vin = []
            for item in inputs:
                prev, idx = _coin_id(item["coin"])
                vin.append({"prev": prev, "idx": idx, "script": b"",
                            "seq": 0xffffffff})
            vout = []
            for item in outputs:
                lock = bytes.fromhex(item["lock"])
                if lock_type(lock) not in ("pkh", "open", "anyone"):
                    raise ValueError("unsupported output lock")
                vout.append({"value": int(item["value"]), "script": lock})
            tx = {"version": 1, "vin": vin, "vout": vout, "locktime": 0}
            unsigned = ser_tx(tx)
            payloads, required = [], []
            for i, item in enumerate(inputs):
                lock = bytes.fromhex(item["lock"])
                lt = lock_type(lock)
                if lt == "pkh":
                    digest = sighash_all(tx, i, lock)
                    payloads.append({
                        "account_identifier": {"address": "lock:" + lock.hex()},
                        "hex_bytes": digest.hex(),
                        "signature_type": "ecdsa",
                    })
                    required.append({"address": "lock:" + lock.hex()})
                elif lt in ("open", "anyone"):
                    continue
                else:
                    raise ValueError("unsupported input lock type: " + str(lt))
            return {"unsigned_transaction": unsigned.hex(),
                    "payloads": payloads,
                    "metadata": {"required_public_keys": required}}

        if path == "/construction/combine":
            raw = bytes.fromhex(body["unsigned_transaction"])
            tx = parse_tx(raw)
            if any(v["script"] for v in tx["vin"]):
                raise ValueError("unsigned transaction already contains scriptSigs")
            metadata = body.get("metadata") or {}
            inputs = metadata.get("inputs") or []
            if len(inputs) != len(tx["vin"]):
                raise ValueError("metadata input count mismatch")
            sigs = body.get("signatures") or []
            by_payload = {}
            for item in sigs:
                payload = item.get("signing_payload") or {}
                by_payload[payload.get("hex_bytes", "").lower()] = item
            for i, item in enumerate(inputs):
                lock = bytes.fromhex(item["lock"])
                lt = lock_type(lock)
                if lt in ("open", "anyone"):
                    continue
                if lt != "pkh":
                    raise ValueError("unsupported input lock type: " + str(lt))
                digest = sighash_all(tx, i, lock)
                sig_item = by_payload.get(digest.hex())
                if not sig_item:
                    raise ValueError("missing signature for input " + str(i))
                pub = bytes.fromhex(sig_item["public_key"]["hex_bytes"])
                sig = bytes.fromhex(sig_item["hex_bytes"])
                if len(pub) == 65 and pub[0] == 4:
                    pub = bytes([2 | (pub[64] & 1)]) + pub[1:33]
                if len(pub) != 33 or pub[0] not in (2, 3):
                    raise ValueError("invalid compressed secp256k1 public key")
                if hash160(pub) != lock[1:]:
                    raise ValueError("public key does not match PKH lock")
                if len(sig) != 64 or not secp.verify(pub, sig, digest):
                    raise ValueError("invalid EXCAL ECDSA signature")
                tx["vin"][i]["script"] = pub + sig + bytes([SIGHASH_ALL])
            signed = ser_tx(tx)
            ok, reason, _fee = validate_tx(signed, self.cs.utxo, height)
            if not ok:
                raise ValueError("consensus validation rejected transaction: " + reason)
            return {"signed_transaction": signed.hex()}

        if path == "/construction/parse":
            raw = bytes.fromhex(body["transaction"])
            tx = parse_tx(raw)
            operations = []
            for i, vin in enumerate(tx["vin"]):
                key = (vin["prev"], vin["idx"])
                entries = self.cs.utxo.get(key)
                if not entries:
                    raise ValueError("cannot resolve input prevout " + str(i))
                value, lock, _cb, _cbh = entries[0]
                operations.append({
                    "operation_identifier": {"index": len(operations)},
                    "type": "INPUT", "account": {"address": "lock:" + bytes(lock).hex()},
                    "amount": {"value": str(-int(value)), "currency": CURRENCY},
                    "coin_change": {"coin_identifier": {"identifier": vin["prev"][::-1].hex() + ":" + str(vin["idx"])},
                                    "coin_action": "coin_spent"},
                })
            for out in tx["vout"]:
                operations.append({
                    "operation_identifier": {"index": len(operations)},
                    "type": "OUTPUT", "account": {"address": "lock:" + bytes(out["script"]).hex()},
                    "amount": {"value": str(int(out["value"])), "currency": CURRENCY},
                })
            return {"operations": operations, "account_identifier_signers": []}

        if path == "/construction/hash":
            raw = bytes.fromhex(body["signed_transaction"])
            parse_tx(raw)
            return {"transaction_identifier": {"hash": txid_internal(raw)[::-1].hex()}}

        if path == "/construction/submit":
            if self.mempool is None:
                raise ValueError("live mempool is not connected to Rosetta")
            raw = bytes.fromhex(body["signed_transaction"])
            ok, reason = self.mempool.add(raw, self.cs.utxo, height)
            if not ok:
                raise ValueError("mempool rejected transaction: " + reason)
            return {"transaction_identifier": {"hash": txid_internal(raw)[::-1].hex()}}

        raise KeyError("unknown construction endpoint")
