#!/usr/bin/env python3
"""knot_wallet.py — KNOT lock transaction builder (test-chain only).

Builds and validates KNOT lock and spend transactions for the Möbius
torus-knot lock (type 0x06). This module is the wallet-side counterpart
to txscript.py's KNOT validation: it creates the lock, computes the
commitment from the secret t_star, and builds the witness.

The KNOT lock is STAGED at height 100000, not activated on the live
fork. These transactions are validated at height KNOT_ACTIVATION and
are NOT broadcastable on the live fork until activation.

API:
    build_knot_lock_tx(funding_utxos, funding_priv, amount,
                       p, q, n_terms, eps_u32, t_star, fee)
        -> {raw, txid, lock, descriptor, commitment, t_star,
            validated_at_height}

    build_knot_spend_test(lock_prev, lock_idx, lock_value, lock,
                          descriptor, t_star, dest_lock, fee)
        -> {raw, txid, validated_at_height}

Pure Python, stdlib only. Connects to:
    - knot_math.py (deterministic fixed-point knot point computation)
    - txscript.py (KNOT descriptor, witness, validation)
    - genesis_fork.py (KNOT activation height)
"""
import os
import sys
import hashlib
import struct

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

import secp256k1 as secp
from genesis_fork import SWORD, knot_activation
from txscript import (ser_tx, parse_tx, validate_tx, sighash_all,
                      SIGHASH_ALL, lock_type, hash160,
                      sign_pkh_input, sign_knot_input,
                      lock_pkh_for_pubkey, lock_knot_for_descriptor,
                      knot_descriptor, knot_lock_for_secret,
                      parse_knot_witness, KNOT_WITNESS_LEN)
import knot_math


def txid_internal(raw: bytes) -> bytes:
    """Transaction ID in internal byte order (SHA256d)."""
    return hashlib.sha256(hashlib.sha256(raw).digest()).digest()


def priv_to_pub_compressed(priv: int) -> bytes:
    """Private key -> compressed public key bytes (33 bytes)."""
    pt = secp.priv_to_pub(priv)
    return secp.compress(pt)


def _est_fee(n_in, n_out):
    """Estimate transaction fee in swords."""
    return (10 + 139 * n_in + 30 * n_out)


def _view_from_utxos(utxos):
    """{(txid_bytes, vout): [(value, lock, is_cb, cb_h)]} for validate_tx."""
    view = {}
    for u in utxos:
        prev_raw = u.get("prev") or u.get("txid")
        if isinstance(prev_raw, str):
            prev = bytes.fromhex(prev_raw)
        else:
            prev = prev_raw
        idx = u.get("idx") or u.get("vout", 0)
        lock = u.get("lock")
        if isinstance(lock, str):
            lock = bytes.fromhex(lock)
        key = (prev, idx)
        view[key] = [(u["value"], lock, False, 0)]
    return view


def _build_tx(vin, vout):
    """Build a raw transaction dict."""
    return {
        "version": 1,
        "vin": vin,
        "vout": vout,
        "locktime": 0,
    }


def build_knot_lock_tx(funding_utxos, funding_priv, amount,
                       p, q, n_terms, eps_u32, t_star, fee=1000):
    """Build a KNOT lock funding transaction.

    Creates a transaction that spends from PKH-funded UTXOs and creates
    a KNOT-locked output. The secret t_star is used to compute the
    commitment H = SHA256(knot_point_bytes || t_star_bytes).

    Args:
        funding_utxos: List of {txid, idx, value, lock} dicts (PKH locks).
        funding_priv: Private key for the funding UTXOs.
        amount: Amount to lock in the KNOT output (in swords).
        p, q: Torus knot windings (coprime, 1..255).
        n_terms: Number of Möbius terms (1..1000).
        eps_u32: Modulation depth as uint32 (0 < eps_u32 < 2^32).
        t_star: Secret knot parameter (0 <= t_star < 2^128).
        fee: Transaction fee in swords.

    Returns:
        Dict with raw, txid, lock, descriptor, commitment, t_star,
        validated_at_height.

    Raises:
        ValueError: If parameters are invalid.
        RuntimeError: If validation fails.
    """
    # Validate t_star range
    if not (0 <= t_star < (1 << 128)):
        raise ValueError(f"t_star must be in [0, 2^128), got {t_star}")

    # Compute the KNOT lock from the secret t_star
    lock, descriptor, commitment = knot_lock_for_secret(
        p, q, n_terms, eps_u32, t_star)

    # Calculate change
    total_in = sum(u["value"] for u in funding_utxos)
    change = total_in - amount - fee
    if change < 0:
        raise ValueError(
            f"insufficient funds: {total_in} < {amount} + {fee}")

    # Build funding inputs (PKH signed)
    vin = []
    for u in funding_utxos:
        prev_raw = u.get("prev") or u.get("txid")
        if isinstance(prev_raw, str):
            prev = bytes.fromhex(prev_raw)
        else:
            prev = prev_raw
        idx = u.get("idx") or u.get("vout", 0)
        vin.append({
            "prev": prev,
            "idx": idx,
            "script": b"",  # Will be signed below
            "seq": 0xFFFFFFFF,
        })

    # Build outputs: KNOT lock + change (if any)
    vout = [{
        "value": amount,
        "script": lock,
    }]
    if change >= 1000:  # Dust threshold
        pub = priv_to_pub_compressed(funding_priv)
        change_lock = lock_pkh_for_pubkey(pub)
        vout.append({
            "value": change,
            "script": change_lock,
        })

    # Build the transaction
    tx = _build_tx(vin, vout)

    # Sign the funding inputs
    for i, u in enumerate(funding_utxos):
        lock_hex = u["lock"] if isinstance(u["lock"], str) else u["lock"].hex()
        lock_bytes = bytes.fromhex(lock_hex) if isinstance(u["lock"], str) else u["lock"]
        tx["vin"][i]["script"] = sign_pkh_input(tx, i, lock_bytes, funding_priv)

    # Serialize
    raw = ser_tx(tx)

    # Validate at KNOT activation height
    act = knot_activation()
    view = _view_from_utxos(funding_utxos)
    ok, reason, validated_fee = validate_tx(raw, view, act)
    if not ok:
        raise RuntimeError(f"KNOT lock tx validation failed: {reason}")

    # Recompute fee from actual size if change exists
    actual_fee = _est_fee(len(funding_utxos), len(vout))
    if len(vout) == 2 and change >= 1000:
        # Adjust change for actual fee
        pass  # Fee estimate is close enough for test-chain

    return {
        "raw": raw,
        "txid": txid_internal(raw).hex(),
        "lock": lock,
        "descriptor": descriptor,
        "commitment": commitment,
        "t_star": t_star,
        "validated_at_height": act,
        "fee": validated_fee,
        "p": p,
        "q": q,
        "n_terms": n_terms,
        "eps_u32": eps_u32,
    }


def build_knot_spend_tx(lock_prev, lock_idx, lock_value, lock,
                        descriptor, t_star, dest_lock, fee=1000):
    """Build a KNOT spend transaction.

    Spends a KNOT-locked UTXO by revealing the secret t_star parameter.
    The witness is t_star (16 bytes) || descriptor (40 bytes) = 56 bytes.

    Args:
        lock_prev: Previous transaction ID (bytes or hex string).
        lock_idx: Output index of the KNOT lock.
        lock_value: Value of the KNOT-locked UTXO (in swords).
        lock: The KNOT lock script (21 bytes: 0x06 + hash160(descriptor)).
        descriptor: The 40-byte KNOT descriptor.
        t_star: The secret knot parameter (reveals the lock).
        dest_lock: Destination lock script for the output.
        fee: Transaction fee in swords.

    Returns:
        Dict with raw, txid, validated_at_height.

    Raises:
        ValueError: If parameters are invalid.
        RuntimeError: If validation fails.
    """
    # Convert lock_prev to bytes if hex string
    if isinstance(lock_prev, str):
        lock_prev = bytes.fromhex(lock_prev)

    # Build the transaction
    change = lock_value - fee
    if change < 0:
        raise ValueError(
            f"insufficient value: {lock_value} < fee {fee}")

    vin = [{
        "prev": lock_prev,
        "idx": lock_idx,
        "script": b"",  # Will be signed below
        "seq": 0xFFFFFFFF,
    }]

    vout = [{
        "value": lock_value - fee,
        "script": dest_lock,
    }]

    tx = _build_tx(vin, vout)

    # Sign with KNOT witness: t_star (16 bytes) || descriptor (40 bytes)
    tx["vin"][0]["script"] = sign_knot_input(tx, 0, lock, t_star, descriptor)

    # Serialize
    raw = ser_tx(tx)

    # Validate at KNOT activation height
    act = knot_activation()
    view = {(lock_prev, lock_idx): [(lock_value, lock, False, 0)]}
    ok, reason, validated_fee = validate_tx(raw, view, act)
    if not ok:
        raise RuntimeError(f"KNOT spend tx validation failed: {reason}")

    return {
        "raw": raw,
        "txid": txid_internal(raw).hex(),
        "validated_at_height": act,
        "fee": validated_fee,
    }


def generate_t_star():
    """Generate a cryptographically secure random t_star.

    Returns a 128-bit random integer suitable as a KNOT secret parameter.
    """
    return int.from_bytes(os.urandom(16), "big") % (1 << 128)


def verify_knot_commitment(p, q, n_terms, eps_u32, t_star, commitment):
    """Verify that a t_star produces the expected commitment.

    Returns True if the commitment matches, False otherwise.
    """
    h = knot_math.knot_commitment(p, q, n_terms, eps_u32, t_star)
    return h == commitment


def compute_knot_point(p, q, n_terms, eps_u32, t_star):
    """Compute the knot point at t_star and return as (x, y, z) Q64 integers."""
    return knot_math.knot_point(p, q, n_terms, eps_u32, t_star)


def knot_point_to_bytes(p, q, n_terms, eps_u32, t_star):
    """Compute the canonical 48-byte knot point encoding."""
    return knot_math.knot_point_bytes(p, q, n_terms, eps_u32, t_star)


# ------------------------------------------------------------------ CLI demo

def demo():
    """Demonstrate a complete KNOT lock and spend cycle."""
    print("=" * 60)
    print("KNOT Lock — Möbius Torus-Knot Transaction Builder")
    print("=" * 60)
    print()

    # Parameters
    p, q = 2, 3  # (2,3) torus knot (trefoil)
    n_terms = 10  # 10 Möbius terms
    eps_u32 = 0x80000000  # eps = 0.5
    t_star = generate_t_star()

    print(f"Knot parameters:")
    print(f"  p = {p}, q = {q} (trefoil knot)")
    print(f"  N = {n_terms} Möbius terms")
    print(f"  eps = {eps_u32 / 2**32:.4f}")
    print(f"  t_star = {t_star} (0x{t_star:032x})")
    print()

    # Compute commitment
    commitment = knot_math.knot_commitment(p, q, n_terms, eps_u32, t_star)
    print(f"Commitment H = {commitment.hex()}")

    # Compute knot point
    x, y, z = knot_math.knot_point(p, q, n_terms, eps_u32, t_star)
    print(f"Knot point (Q64):")
    print(f"  x = {x / 2**64:.6f}")
    print(f"  y = {y / 2**64:.6f}")
    print(f"  z = {z / 2**64:.6f}")
    print()

    # Build descriptor and lock
    descriptor = knot_descriptor(p, q, n_terms, eps_u32, commitment)
    lock = lock_knot_for_descriptor(descriptor)
    print(f"Descriptor: {descriptor.hex()}")
    print(f"KNOT lock:  {lock.hex()}")
    print()

    # Build funding transaction
    priv = 0x12345678
    pub = priv_to_pub_compressed(priv)
    funding_lock = lock_pkh_for_pubkey(pub)

    funding_utxos = [{
        "txid": "a" * 64,
        "idx": 0,
        "value": 5 * SWORD,
        "lock": funding_lock,
    }]

    print("Building KNOT lock transaction...")
    res = build_knot_lock_tx(funding_utxos, priv, 1 * SWORD,
                             p, q, n_terms, eps_u32, t_star, 1000)
    print(f"  TXID: {res['txid']}")
    print(f"  Lock: {res['lock'].hex()}")
    print(f"  Validated at height: {res['validated_at_height']}")
    print()

    # Build spend transaction
    lock_prev = txid_internal(res["raw"])
    dest_lock = lock_pkh_for_pubkey(
        priv_to_pub_compressed(0x87654321))

    print("Building KNOT spend transaction...")
    res2 = build_knot_spend_tx(
        lock_prev, 0, 1 * SWORD, res["lock"], res["descriptor"],
        t_star, dest_lock, 1000)
    print(f"  TXID: {res2['txid']}")
    print(f"  Validated at height: {res2['validated_at_height']}")
    print()

    # Verify commitment
    ok = verify_knot_commitment(p, q, n_terms, eps_u32, t_star, commitment)
    print(f"Commitment verification: {'✓' if ok else '✗'}")
    print()

    # Activation status
    act = knot_activation()
    print(f"KNOT activation height: {act}")
    print(f"Status: {'ACTIVE' if act <= 44515 else 'STAGED (not yet active)'}")
    print()
    print("=" * 60)
    print("KNOT lock cycle complete!")
    print("=" * 60)


if __name__ == "__main__":
    demo()
