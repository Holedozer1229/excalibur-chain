"""Consensus-format PQH wallet key and transaction helpers."""

import hashlib
import secrets
from decimal import Decimal, InvalidOperation

import txscript
import txpq
from genesis_fork import SWORD
from trifold_lockbox import TrifoldKey

DEFAULT_FEE_SWORDS = 1_000


def hash160(data: bytes) -> bytes:
    sha = hashlib.sha256(data).digest()
    try:
        import hashlib as _hashlib
        return _hashlib.new("ripemd160", sha).digest()
    except ValueError as exc:
        raise RuntimeError("RIPEMD-160 is unavailable in this Python build") from exc


def create_pqh_key(seed: bytes | None = None, state_dir: str | None = None):
    """Create a Trifold key and its consensus PQH address."""
    seed = seed or secrets.token_bytes(32)
    if len(seed) != 32:
        raise ValueError("wallet seed must be exactly 32 bytes")
    key = TrifoldKey(seed, height=6, state_dir=state_dir)
    address = hash160(key.root).hex().upper()
    return {
        "private_key": seed.hex(),
        "public_key": key.root.hex(),
        "address": address,
    }


def address_lock(address: str) -> bytes:
    if not isinstance(address, str) or len(address) != 40:
        raise ValueError("EXCAL PQH address must be 40 hexadecimal characters")
    try:
        payload = bytes.fromhex(address)
    except ValueError as exc:
        raise ValueError("EXCAL PQH address must be hexadecimal") from exc
    if address != address.upper():
        raise ValueError("EXCAL PQH address must use uppercase hexadecimal")
    return txscript.lock_pqh(payload)


def amount_to_swords(amount) -> int:
    try:
        value = Decimal(str(amount))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("amount must be a decimal number") from exc
    if not value.is_finite() or value <= 0:
        raise ValueError("amount must be positive and finite")
    swords = value * SWORD
    if swords != swords.to_integral_value():
        raise ValueError("amount supports at most 8 decimal places")
    return int(swords)


def balance_from_utxos(utxos: list[dict]) -> Decimal:
    return Decimal(sum(int(utxo["value"]) for utxo in utxos)) / SWORD


def build_pqh_transaction(seed: bytes | None, address: str | None,
                          utxos: list[dict], recipient: str, amount,
                          state_dir: str, registry_path: str,
                          fee_swords: int = DEFAULT_FEE_SWORDS,
                          keys: list[dict] | None = None) -> bytes:
    """Build, sign, and locally validate a spend from wallet PQH UTXOs.

    ``keys`` may contain multiple ``{"seed", "address"}`` entries; the
    legacy seed/address parameters remain for single-key callers.
    """
    recipient_lock = address_lock(recipient)
    amount_swords = amount_to_swords(amount)
    if not isinstance(fee_swords, int) or fee_swords < 0:
        raise ValueError("fee must be a non-negative integer number of swords")

    key_specs = keys or [{"seed": seed, "address": address}]
    if not key_specs:
        raise ValueError("wallet has no PQH signing keys")
    keys_by_lock = {}
    for spec in key_specs:
        key_seed, key_address = spec.get("seed"), spec.get("address")
        if not isinstance(key_seed, bytes) or len(key_seed) != 32:
            raise ValueError("wallet seed must be exactly 32 bytes")
        address_lock(key_address)
        key = TrifoldKey(key_seed, height=6, state_dir=state_dir)
        if hash160(key.root).hex().upper() != key_address:
            raise ValueError("wallet seed does not match its address")
        lock = txscript.lock_pqh_for_root(key.root)
        if lock in keys_by_lock:
            raise ValueError("duplicate wallet signing key")
        keys_by_lock[lock] = key

    candidates = []
    seen = set()
    tip_heights = set()
    for item in utxos:
        if not isinstance(item, dict):
            raise ValueError("node returned a malformed wallet UTXO")
        try:
            raw_vout = item["vout"]
            raw_value = item["value"]
            raw_height = item["height"]
            raw_tip_height = item["tip_height"]
            if any(isinstance(value, bool) for value in (
                    raw_vout, raw_value, raw_height, raw_tip_height)):
                raise ValueError
            txid = bytes.fromhex(item["txid"])
            vout = int(raw_vout)
            value = int(raw_value)
            script = bytes.fromhex(item["script"])
            height = int(raw_height)
            tip_height = int(raw_tip_height)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("node returned a malformed wallet UTXO") from exc
        if (len(txid) != 32 or vout < 0 or value < 0 or len(script) != 21
                or height < 0 or tip_height < height):
            raise ValueError("node returned an invalid wallet UTXO")
        if not isinstance(item.get("coinbase"), bool):
            raise ValueError("node returned an invalid wallet UTXO maturity flag")
        pending_spend = item.get("pending_spend", False)
        if not isinstance(pending_spend, bool):
            raise ValueError("node returned an invalid pending-spend flag")
        outpoint = (txid, vout)
        if outpoint in seen:
            raise ValueError("node returned a duplicate wallet UTXO")
        seen.add(outpoint)
        key = keys_by_lock.get(script)
        if key is None:
            continue
        if pending_spend:
            continue
        if item.get("coinbase") and (
                tip_height + 1 - height < txscript.COINBASE_MATURITY):
            continue
        candidates.append((item, key, txid, vout, value, script))
        tip_heights.add(tip_height)
    if len(tip_heights) > 1:
        raise ValueError("node returned UTXOs from different chain tips")
    if not candidates:
        raise ValueError("insufficient confirmed balance for amount and network fee")

    selected = []
    total = 0
    for candidate in sorted(candidates, key=lambda row: -row[4]):
        selected.append(candidate)
        total += candidate[4]
        if total >= amount_swords + fee_swords:
            break
    if total < amount_swords + fee_swords:
        raise ValueError("insufficient confirmed balance for amount and network fee")

    change_key = selected[0][1]
    outputs = [{"value": amount_swords, "script": recipient_lock}]
    change = total - amount_swords - fee_swords
    if change:
        outputs.append({
            "value": change,
            "script": txscript.lock_pqh_for_root(change_key.root),
        })
    tx = {
        "version": 1,
        "vin": [
            {
                "prev": txid,
                "idx": vout,
                "script": b"",
                "seq": 0xFFFFFFFF,
            }
            for _item, _key, txid, vout, _value, _script in selected
        ],
        "vout": outputs,
        "locktime": 0,
    }
    registry = None
    if registry_path:
        from spent_leaf_registry import load_registry
        registry = load_registry(registry_path)
    utxo_view = {}
    for index, (item, key, txid, vout, value, script) in enumerate(selected):
        tx["vin"][index]["script"] = txpq.sign_pqh_input(
            key,
            txscript.sighash_all(tx, index, script),
            registry=registry,
        )
        utxo_view[(txid, vout)] = [(
            value, script, bool(item.get("coinbase", False)),
            int(item["height"]),
        )]
    raw = txscript.ser_tx(tx)
    validation_height = next(iter(tip_heights)) + 1
    valid, reason, actual_fee = txscript.validate_tx(
        raw, utxo_view, validation_height,
    )
    if not valid:
        raise ValueError(f"locally built transaction failed validation: {reason}")
    if actual_fee != total - sum(output["value"] for output in outputs):
        raise ValueError("locally validated transaction fee does not match")
    return raw
