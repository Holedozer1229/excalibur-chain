#!/usr/bin/env python3
"""Phase Omega — the Excalibur fork countersigns itself.

Every block produced by the chain's standing producers (the merge-mining
sniper via fork_child.py, the built-in CPU miners in excalibur.py, and
the stratum shim) carries one extra coinbase push:

    push(b"OMEGA1" || epoch:uint16be || trifold_signature)

The signature is a Trifold (hash-only, ternary Merkle, 729 leaves per
epoch) signature over the parent block's raw 80-byte header. Block N's
coinbase therefore countersigns block N-1, and the chain of signatures
runs unbroken alongside the chain of hashes. Verification needs only
the epoch root (published in epochs.json and in the excalibur-chain
repo) and trifold_lockbox.verify — no secret, no trusted party.

Leaf discipline is the security: a Trifold leaf is a one-time key, so
leaf indices are allocated under an flock by this module alone, are
never reused (state is persisted BEFORE the signature leaves the
lock), and are cached per parent header so competing templates for
the same parent share one signature instead of burning two leaves.
Epochs rotate at leaf 720 of 729; the ledger records every root.

omega_blob() never raises: on any error it returns None and the
producer builds a plain block. Block production never depends on the
signer being healthy.
"""
import fcntl
import hashlib
import json
import os
import struct
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import trifold_lockbox as tl

OMEGA_DIR = os.environ.get(
    "OMEGA_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "omega"))
MAGIC = b"OMEGA1"
TREE_HEIGHT = 6
CAPACITY = 3 ** TREE_HEIGHT          # 729 leaves per epoch
ROTATE_AT = 720                      # rotate with 9 leaves to spare
SIG_BYTES = 4 + 256 * 32 + 256 * 64 + (TREE_HEIGHT * 2) * 32   # 24,964
BLOB_BYTES = len(MAGIC) + 2 + SIG_BYTES                        # 24,972


# ------------------------------------------------------------ state io
def _path(name):
    return os.path.join(OMEGA_DIR, name)


def _load_json(name, default=None):
    try:
        with open(_path(name)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _save_json(name, obj, mode=None):
    tmp = _path(name + ".tmp")
    with open(tmp, "w") as f:
        json.dump(obj, f)
    if mode is not None:
        os.chmod(tmp, mode)
    os.replace(tmp, _path(name))


def _ledger():
    return _load_json("epochs.json", [])


def _state(epoch):
    return _load_json(f"epoch_{epoch}.json")


# ------------------------------------------------------------ key mgmt
def _create_epoch(epoch):
    """Generate a fresh epoch key, cache its (public) tree, record the
    root in the ledger. Caller must hold the lock."""
    seed = os.urandom(32)
    key = tl.TrifoldKey(seed, TREE_HEIGHT)
    tree = [[h.hex() for h in lvl] for lvl in key._tree]
    _save_json(f"epoch_{epoch}_tree.json", tree)
    _save_json(f"epoch_{epoch}.json",
               {"seed_hex": seed.hex(), "root_hex": key.root.hex(),
                "next_index": 0}, mode=0o600)
    led = _ledger()
    led.append({"epoch": epoch, "root_hex": key.root.hex(),
                "created": int(time.time()), "capacity": CAPACITY})
    _save_json("epochs.json", led)
    return key.root


def _load_key(epoch):
    """Rebuild a signing key from the cached tree (no keygen cost)."""
    st = _state(epoch)
    tree = _load_json(f"epoch_{epoch}_tree.json")
    key = tl.TrifoldKey.__new__(tl.TrifoldKey)
    key.seed = bytes.fromhex(st["seed_hex"])
    key.height = TREE_HEIGHT
    key.capacity = CAPACITY
    key.next_index = st["next_index"]
    key._tree = [[bytes.fromhex(h) for h in lvl] for lvl in tree]
    key.root = key._tree[-1][0]
    assert key.root.hex() == st["root_hex"]
    return key, st


# ------------------------------------------------------------ sig codec
def _serialize(sig):
    out = [struct.pack(">I", sig["index"])]
    out += sig["ots_sig"]
    for a, b in sig["ots_pub"]:
        out.append(a)
        out.append(b)
    for lvl in sig["path"]:
        out += lvl
    blob = b"".join(out)
    assert len(blob) == SIG_BYTES, len(blob)
    return blob


def parse_blob(blob):
    """blob -> (epoch, sig dict). Raises ValueError on malformed input."""
    if len(blob) != BLOB_BYTES or not blob.startswith(MAGIC):
        raise ValueError("not an Omega blob")
    epoch = struct.unpack_from(">H", blob, len(MAGIC))[0]
    raw = blob[len(MAGIC) + 2:]
    pos = 0
    index = struct.unpack_from(">I", raw, pos)[0]
    pos += 4
    ots_sig = []
    for _ in range(256):
        ots_sig.append(raw[pos:pos + 32])
        pos += 32
    ots_pub = []
    for _ in range(256):
        ots_pub.append((raw[pos:pos + 32], raw[pos + 32:pos + 64]))
        pos += 64
    path = []
    for _ in range(TREE_HEIGHT):
        path.append([raw[pos:pos + 32], raw[pos + 32:pos + 64]])
        pos += 64
    assert pos == len(raw)
    return epoch, {"index": index, "ots_sig": ots_sig,
                   "ots_pub": ots_pub, "path": path}


def verify_blob(root, msg, blob):
    try:
        _epoch, sig = parse_blob(blob)
        return tl.verify(root, msg, sig)
    except Exception:
        return False


def root_for_epoch(epoch):
    for entry in _ledger():
        if entry["epoch"] == epoch:
            return bytes.fromhex(entry["root_hex"])
    return None


# ------------------------------------------------------------ signing
def omega_blob(parent_header):
    """Trifold signature blob over the 80-byte parent header, or None.

    Cached per parent: the same parent always yields the same blob, so
    competing producers/templates share one leaf. Never raises.
    """
    try:
        if len(parent_header) != 80:
            return None
        os.makedirs(_path("sigs"), exist_ok=True)
        # Cache key: the parent's block hash — sha256d(header) hex in
        # the chain records' internal order.
        cache = _path("sigs/" + hashlib.sha256(
            hashlib.sha256(parent_header).digest()).digest().hex() + ".bin")
        if os.path.exists(cache):
            with open(cache, "rb") as f:
                blob = f.read()
            if len(blob) == BLOB_BYTES:
                return blob
        with open(_path("omega.lock"), "a") as lockf:
            fcntl.flock(lockf, fcntl.LOCK_EX)
            if os.path.exists(cache):
                with open(cache, "rb") as f:
                    blob = f.read()
                if len(blob) == BLOB_BYTES:
                    return blob
            led = _ledger()
            if not led:
                _create_epoch(1)
                led = _ledger()
            epoch = led[-1]["epoch"]
            st = _state(epoch)
            if st["next_index"] >= ROTATE_AT:
                epoch += 1
                _create_epoch(epoch)
                st = _state(epoch)
            key, st = _load_key(epoch)
            sig = key.sign(parent_header)
            # Persist the spent leaf BEFORE the signature leaves the
            # lock: a crash from here can burn a leaf, never reuse one.
            st["next_index"] = sig["index"] + 1
            _save_json(f"epoch_{epoch}.json", st, mode=0o600)
            blob = MAGIC + struct.pack(">H", epoch) + _serialize(sig)
            with open(cache, "wb") as f:
                f.write(blob)
            return blob
    except Exception:
        return None


# ------------------------------------------------------------ cli
def _status():
    led = _ledger()
    if not led:
        print("Omega: no epochs yet (first producer call creates epoch 1)")
        return
    for e in led:
        st = _state(e["epoch"])
        print(f"epoch {e['epoch']}: root {e['root_hex'][:32]}... "
              f"next_index {st['next_index']}/{CAPACITY} "
              f"created {e['created']}")


def _selftest():
    import genesis_fork as gf
    import txscript
    gf.use_network("fork")
    parent = bytes(range(80))          # stand-in header, shaped like one
    blob = omega_blob(parent)
    assert blob is not None and len(blob) == BLOB_BYTES, "blob failed"
    assert omega_blob(parent) == blob, "cache did not return same blob"
    epoch, sig = parse_blob(blob)
    root = root_for_epoch(epoch)
    assert tl.verify(root, parent, sig), "verify failed"
    assert not tl.verify(root, bytes([parent[0] ^ 1]) + parent[1:], sig), \
        "tampered parent verified!"
    # A coinbase carrying the blob must pass the (fixed) lineage check.
    cb = txscript.make_coinbase_v2(25999, 0x1E00F05B, b"Excalibur", 0,
                                   None, extra_pushes=[blob])
    assert gf.check_coinbase_lineage(cb, 0x1E00F05B), "lineage failed"
    assert verify_blob(root, parent, blob)
    print(f"SELFTEST PASS — epoch {epoch} leaf {sig['index']}, "
          f"blob {len(blob)} bytes, lineage + verify + tamper all correct")


if __name__ == "__main__":
    os.makedirs(OMEGA_DIR, exist_ok=True)
    if "--selftest" in sys.argv:
        _selftest()
    else:
        _status()
