"""txpq.py — Q-Day witness codec for the Genesis Fork (staged package).

The PQH lock (0x02 + hash160(Trifold root)) is spent by a witness carrying
the full Trifold signature: the tree root, the one-time Lamport signature
for the spent leaf, and the ternary authentication path. Verification is
hash-only (trifold_lockbox.verify): no curve arithmetic exists anywhere
in the spend path, which is the entire point of Q-Day.

Witness layout (scriptSig bytes):
    root        32 bytes   Trifold tree root being revealed
    height       1 byte    ternary tree height (path length check)
    index        3 bytes   leaf index, big-endian
    ots_sig    256*32      revealed one-time secrets
    ots_pub    512*32      the leaf's full one-time public key
    path     2*height*32   sibling pairs, one pair per tree level
Total for height 6: 24,996 bytes.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trifold_lockbox import verify as _trifold_verify

FIXED = 32 + 1 + 3 + 256 * 32 + 512 * 32  # everything except the path


def encode_witness(root: bytes, sig: dict, height: int) -> bytes:
    if not isinstance(root, bytes) or len(root) != 32:
        raise ValueError("Trifold root must be 32 bytes")
    if (not isinstance(height, int) or isinstance(height, bool)
            or not 1 <= height <= 15):
        raise ValueError("Trifold height must be between 1 and 15")
    idx = sig.get("index") if isinstance(sig, dict) else None
    if (not isinstance(idx, int) or isinstance(idx, bool)
            or idx < 0 or idx >= min(3 ** height, 1 << 24)):
        raise ValueError("Trifold index does not fit the witness")
    ots_sig = sig.get("ots_sig")
    ots_pub = sig.get("ots_pub")
    path = sig.get("path")
    if (not isinstance(ots_sig, (list, tuple)) or len(ots_sig) != 256
            or any(not isinstance(x, bytes) or len(x) != 32 for x in ots_sig)):
        raise ValueError("Trifold Lamport signature has an invalid shape")
    if (not isinstance(ots_pub, (list, tuple)) or len(ots_pub) != 256
            or any(not isinstance(pair, (list, tuple)) or len(pair) != 2
                   or any(not isinstance(x, bytes) or len(x) != 32 for x in pair)
                   for pair in ots_pub)):
        raise ValueError("Trifold Lamport public key has an invalid shape")
    if (not isinstance(path, (list, tuple)) or len(path) != height
            or any(not isinstance(level, (list, tuple)) or len(level) != 2
                   or any(not isinstance(x, bytes) or len(x) != 32 for x in level)
                   for level in path)):
        raise ValueError("Trifold authentication path has an invalid shape")
    out = bytearray()
    out += root
    out.append(height)
    out += idx.to_bytes(3, "big")
    for x in ots_sig:
        out += x
    for a, b in ots_pub:
        out += a + b
    for sibs in path:
        for s in sibs:
            out += s
    return bytes(out)


def decode_witness(b: bytes):
    """Strict decode. Returns (root, sig_dict) or raises ValueError."""
    if not isinstance(b, bytes):
        raise ValueError("witness must be bytes")
    if len(b) < FIXED + 64:
        raise ValueError("witness too short")
    root = b[:32]
    height = b[32]
    if height == 0 or height > 15:
        raise ValueError("bad tree height")
    expect = FIXED + 2 * height * 32
    if len(b) != expect:
        raise ValueError(f"witness length {len(b)} != expected {expect}")
    idx = int.from_bytes(b[33:36], "big")
    if idx >= 3 ** height:
        raise ValueError("leaf index beyond tree capacity")
    p = 36
    ots_sig = []
    for _ in range(256):
        ots_sig.append(b[p:p + 32]); p += 32
    ots_pub = []
    for _ in range(256):
        ots_pub.append((b[p:p + 32], b[p + 32:p + 64])); p += 64
    path = []
    for _ in range(height):
        path.append([b[p:p + 32], b[p + 32:p + 64]]); p += 64
    return root, {"index": idx, "ots_sig": ots_sig,
                  "ots_pub": ots_pub, "path": path}


def trifold_verify(root: bytes, msg: bytes, sig: dict) -> bool:
    return _trifold_verify(root, msg, sig)


def sign_pqh_input(key, sighash: bytes, registry=None) -> bytes:
    """Wallet side: sign a tx sighash with the next Trifold leaf and
    encode the witness. The key's state counter advances — never reuse.

    Spent-leaf guard: atomically reserve (root, next_index) in the
    persistent registry, then persist the key counter before any secret
    preimage is emitted. A failure after reservation burns that leaf.
    Reused leaves fail without silently advancing to another index.

    registry: a SpentLeafRegistry, or None to use the chain-data
    registry (independent of any wallet file, so restoring a wallet
    backup never resets it). Tests may pass a registry backed by a
    temporary file.
    """
    from spent_leaf_registry import load_registry
    reg = registry if registry is not None else load_registry()
    idx = int(key.next_index)
    if not reg.reserve(key.root, idx, txid=None, height=None):
        first = reg.first_spend(key.root, idx)
        raise RuntimeError(
            f"spent leaf refused: root={key.root.hex()} index={idx} "
            f"already spent in tx {first.get('txid')} "
            f"at height {first.get('height')}")
    # The registry reservation and durable key counter both happen before
    # any secret preimage is emitted. A crash burns the leaf safely.
    sig = key.sign_reserved(sighash, idx)
    assert int(sig["index"]) == idx, "leaf advanced between check and sign"
    return encode_witness(key.root, sig, key.height)
