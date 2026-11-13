"""Consensus-format PQH wallet key and transaction helpers."""

import hashlib
import secrets
from decimal import Decimal, InvalidOperation

import txscript
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


def build_pqh_transaction(seed: bytes, address: str, utxos: list[dict],
                          recipient: str, amount, state_dir: str,
                          registry_path: str,
                          fee_swords: int = DEFAULT_FEE_SWORDS) -> bytes:
    """Build and sign a transaction using the wallet's confirmed PQH UTXOs.

    The node remains responsible for consensus validation and broadcast.
    """
    recipient_lock = address_lock(recipient)
    address_lock(address)
    amount_swords = amount_to_swords(amount)
    if not isinstance(fee_swords, int) or fee_swords < 0:
        raise ValueError("fee must be a non-negative integer number of swords")

    key = TrifoldKey(seed, height=6, state_dir=state_dir)
    expected_address = hash160(key.root).hex().upper()
    if key.root.hex() != key.root.hex() or expected_address != address:
        raise ValueError("wallet seed does not match the selected address")

    selected = []
    total = 0
    for item in utxos:
        if bytes.fromhex(item["script"]) != txscript.lock_pqh_for_root(key.root):
            continue
        if item.get("coinbase") and int(item["height"]) + txscript.COINBASE_MATURITY > int(item["tip_height"]):
            continue
        selected.append(item)
        total += int(item["value"])
        if total >= amount_swords + fee_swords:
            break
    if total < amount_swords + fee_swords:
        raise ValueError("insufficient confirmed balance for amount and network fee")

    outputs = [{"value": amount_swords, "script": recipient_lock}]
    change = total - amount_swords - fee_swords
    if change:
        outputs.append({
            "value": change,
            "script": txscript.lock_pqh_for_root(key.root),
        })
    tx = {
        "version": 1,
        "vin": [
            {
                "prev": bytes.fromhex(item["txid"]),
                "idx": int(item["vout"]),
                "script": b"",
                "seq": 0xFFFFFFFF,
            }
            for item in selected
        ],
        "vout": outputs,
        "locktime": 0,
    }
    registry = None
    if registry_path:
        from spent_leaf_registry import load_registry
        registry = load_registry(registry_path)
    for index, item in enumerate(selected):
        tx["vin"][index]["script"] = __import__("txpq").sign_pqh_input(
            key,
            txscript.sighash_all(tx, index, bytes.fromhex(item["script"])),
            registry=registry,
        )
    return txscript.ser_tx(tx)
