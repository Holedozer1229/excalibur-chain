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
    assert len(root) == 32
    out = bytearray()
    out += root
    out.append(height)
    out += sig["index"].to_bytes(3, "big")
    for x in sig["ots_sig"]:
        out += x
    for a, b in sig["ots_pub"]:
        out += a + b
    for sibs in sig["path"]:
        assert len(sibs) == 2
        for s in sibs:
            out += s
    return bytes(out)


def decode_witness(b: bytes):
    """Strict decode. Returns (root, sig_dict) or raises ValueError."""
    if len(b) < FIXED + 64:
        raise ValueError("witness too short")
    root = b[:32]
    height = b[32]
    if height == 0 or height > 16:
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

    Spent-leaf guard: before any signature is produced, the wallet
    checks the persistent spent-leaf registry for (root, next_index).
    If that pair is already spent, signing is refused with an explicit
    reason naming the pair and its first spend — the counter is NOT
    advanced and NO signature is produced, and the wallet does NOT
    silently skip to the next leaf. If the pair is fresh, it is recorded
    in the registry BEFORE the signature is returned, so a crash between
    signing and recording cannot reuse the leaf (the leaf is burned if
    signing itself then fails — the safe direction).

    registry: a SpentLeafRegistry, or None to use the chain-data
    registry (independent of any wallet file, so restoring a wallet
    backup never resets it). Tests may pass a registry backed by a
    temporary file.
    """
    from spent_leaf_registry import load_registry
    reg = registry if registry is not None else load_registry()
    idx = int(key.next_index)
    if reg.is_spent(key.root, idx):
        first = reg.first_spend(key.root, idx)
        raise RuntimeError(
            f"spent leaf refused: root={key.root.hex()} index={idx} "
            f"already spent in tx {first.get('txid')} "
            f"at height {first.get('height')}")
    # Record before signing: the leaf is spent from this moment on,
    # even if this process dies before the witness is used.
    reg.record(key.root, idx, txid=None, height=None)
    sig = key.sign(sighash)
    assert int(sig["index"]) == idx, "leaf advanced between check and sign"
    return encode_witness(key.root, sig, key.height)
