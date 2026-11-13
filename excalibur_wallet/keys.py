"""keys.py — deterministic key and address derivation for the wallet.

Derivation (documented, deterministic, HMAC-based — NOT BIP32):
  priv(domain, index) = HMAC-SHA512(seed, domain || BE32(index))[0:32]
                        mod (N-1) + 1
  domains: "excalibur/wallet/v1/receive", ".../change", ".../trifold"

This is deliberately NOT BIP32: the fork has no registered BIP44 coin
type, and a simple audited HMAC derivation is the honest choice for a
first wallet. A BIP32 path is a future upgrade; it would change every
address, so it must be a deliberate migration, never silent.

Addresses are the fork's native form: the PKH lock itself, hex-encoded
(42 chars: '00' + hash160(pubkey)), exactly as node_rpc.getpkhaddress
returns. There is no base58/bech32 address format on this fork.

Key material never leaves this module except as bytes passed to the
signing functions; nothing here prints a key.
"""
import hashlib
import hmac
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import secp256k1 as secp
from txscript import hash160, lock_pkh_for_pubkey

DOMAIN_RECEIVE = b"excalibur/wallet/v1/receive"
DOMAIN_CHANGE = b"excalibur/wallet/v1/change"
DOMAIN_TRIFOLD = b"excalibur/wallet/v1/trifold"


def derive_priv(seed: bytes, domain: bytes, index: int) -> int:
    """Deterministic private key scalar for (domain, index)."""
    if not (0 <= index < 2**31):
        raise ValueError("index out of range")
    d = hmac.new(seed, domain + struct.pack(">I", index),
                 hashlib.sha512).digest()
    return int.from_bytes(d[:32], "big") % (secp.N - 1) + 1


def priv_to_pub_compressed(priv: int) -> bytes:
    return secp.compress(secp.priv_to_pub(priv))


def lock_for_priv(priv: int) -> bytes:
    """The 21-byte PKH lock for a private key."""
    return lock_pkh_for_pubkey(priv_to_pub_compressed(priv))


def address_for_priv(priv: int) -> str:
    """The wallet address: the PKH lock hex (42 chars)."""
    return lock_for_priv(priv).hex()


def receive_key(seed: bytes, index: int) -> int:
    return derive_priv(seed, DOMAIN_RECEIVE, index)


def change_key(seed: bytes, index: int) -> int:
    return derive_priv(seed, DOMAIN_CHANGE, index)


def trifold_seed(seed: bytes) -> bytes:
    """32-byte seed for the wallet's Trifold (PQH/QHTLC) key.

    Derived from the master seed, so a mnemonic restore rebuilds the
    same Trifold root. The Trifold leaf counter is persisted separately
    (state file in the wallet datadir) and the chain's spent-leaf
    registry is the second guard — a restore never resets either."""
    return hmac.new(seed, DOMAIN_TRIFOLD, hashlib.sha512).digest()[:32]


def random_priv() -> int:
    """A fresh random private key scalar (for one-off keys, not the wallet)."""
    while True:
        d = int.from_bytes(os.urandom(32), "big")
        if 1 <= d < secp.N:
            return d
