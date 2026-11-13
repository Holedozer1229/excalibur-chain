"""locks.py — lock constructors for every live lock type, plus the
KNOT refusal.

Live locks (fork network, activation heights from genesis_fork.py):
  PKH    0x00 + hash160(pubkey)      active since 0 (fork) / 102 (mainnet)
  OPEN   0xff                        anyone-spend, active since lockbox
  PQH    0x02 + hash160(Trifold root)  Q-Day 25212
  HTLC   0x03 + hash160(descriptor)    36010
  QHTLC  0x04 + hash160(descriptor)    40040
  BRIDGE 0x05 + x-coordinate           39200
  KNOT   0x06 + hash160(descriptor)    100000 — STAGED, NOT ACTIVATED

The wallet REFUSES to create a KNOT output for the live fork at any
height below KNOT_ACTIVATION (validate_tx would reject it as
non-standard, so building one would only produce a dead tx). KNOT
builds are available only as explicitly-labelled test-chain builds
via knot_wallet (validated at height KNOT_ACTIVATION, never broadcast
on the live fork). That refusal is a feature, not a gap.
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from genesis_fork import (qday_activation, htlc_activation,
                          qhtlc_activation, bridge_activation,
                          knot_activation)
from txscript import (lock_pkh, lock_pkh_for_pubkey, lock_open,
                      lock_pqh, lock_pqh_for_root,
                      lock_htlc, lock_htlc_for_descriptor,
                      htlc_descriptor, parse_htlc_descriptor,
                      lock_qhtlc, lock_qhtlc_for_descriptor,
                      qhtlc_descriptor, parse_qhtlc_descriptor,
                      lock_bridge, lock_bridge_for_pubkey,
                      lock_type, hash160)
import secp256k1 as secp


class KnotRefused(Exception):
    """Raised when a KNOT output is requested for the live fork."""


LOCKS = [
    ("pkh", 0x00, "PKH — hash160(pubkey), quantum-safe at rest",
     lambda: 0),
    ("open", 0xFF, "OPEN — anyone-spend (no key)", lambda: 0),
    ("pqh", 0x02, "PQH — hash160(Trifold root), hash-only spend",
     qday_activation),
    ("htlc", 0x03, "HTLC — hash+time lock, ECDSA claim/refund",
     htlc_activation),
    ("qhtlc", 0x04, "QHTLC — hash-only HTLC, Trifold claim/refund",
     qhtlc_activation),
    ("bridge", 0x05, "BRIDGE — x-coordinate lock (form bridge)",
     bridge_activation),
    ("knot", 0x06, "KNOT — torus-knot point commitment (STAGED)",
     knot_activation),
]


def lock_status(tip_height: int):
    """[{type, version, activation, active, note}] at `tip_height`."""
    out = []
    for name, ver, note, act in LOCKS:
        a = act()
        out.append({"type": name, "version": ver, "activation": a,
                    "active": tip_height >= a, "note": note})
    return out


def parse_lock_hex(s: str) -> bytes:
    """Parse a lock from hex. Accepts PKH lock hex (42 chars) or a bare
    40-hex hash160 (treated as PKH). Raises ValueError on anything else."""
    s = str(s).strip().lower()
    if s.startswith("0x"):
        s = s[2:]
    try:
        raw = bytes.fromhex(s)
    except ValueError:
        raise ValueError("lock must be hex")
    if len(raw) == 21 and lock_type(raw) is not None:
        return raw
    if len(raw) == 20:
        return lock_pkh(raw)
    if raw == b"\xff":
        return raw
    raise ValueError(f"not a recognized lock: {s[:44]}")


def pkh_lock_for_pubkey(pub_compressed: bytes) -> bytes:
    return lock_pkh_for_pubkey(pub_compressed)


def open_lock() -> bytes:
    return lock_open()


def pqh_lock_for_root(root: bytes) -> bytes:
    return lock_pqh_for_root(root)


def htlc_lock(secret: bytes, claim_pub: bytes, refund_pub: bytes,
              timeout: int):
    """Build an HTLC lock from its parameters. Returns
    (lock, descriptor). The secret itself is never stored here — the
    caller keeps it (or its hash) as it would a key."""
    secret_hash = hashlib.sha256(secret).digest()
    desc = htlc_descriptor(secret_hash, claim_pub, refund_pub, timeout)
    return lock_htlc_for_descriptor(desc), desc


def qhtlc_lock(secret: bytes, claim_root: bytes, refund_root: bytes,
               timeout: int):
    """Build a QHTLC lock. Returns (lock, descriptor)."""
    if claim_root == refund_root:
        raise ValueError("QHTLC claim and refund roots must differ")
    secret_hash = hashlib.sha256(secret).digest()
    desc = qhtlc_descriptor(secret_hash, claim_root, refund_root, timeout)
    return lock_qhtlc_for_descriptor(desc), desc


def bridge_lock_for_pubkey(pub) -> bytes:
    return lock_bridge_for_pubkey(pub)


def knot_lock_refuse(tip_height: int):
    """The KNOT refusal: raise unless the live tip is at/above the
    staged activation (it is not — activation is 100000, tip ~44.5k).
    Test-chain KNOT builds go through knot_wallet directly, never here."""
    act = knot_activation()
    if tip_height >= act:
        return
    raise KnotRefused(
        f"KNOT lock refused: activation is staged at height "
        f"{act}, live tip is {tip_height}. KNOT outputs "
        f"are non-standard on the live fork today and would be rejected "
        f"by every node. Test-chain KNOT builds are available via "
        f"`wallet knot lock` (validated at height {act}, "
        f"never broadcast on the live fork). Activation moves only on "
        f"Lux's word.")
