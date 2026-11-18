#!/usr/bin/env python3
"""Hash-based one-time signatures authenticated by a ternary Merkle tree.

Each leaf is a Lamport one-time signature key. A custom SHA-256 key
derivation includes a public pattern constant, and a ternary Merkle tree
authenticates the leaf. The pattern adds no secret entropy. This is a
custom parameterization of established hash-based components, not a
formally specified or peer-reviewed signature scheme; the code makes no
claim of a security proof.

Leaves must never sign different messages. Signing therefore requires a
persistent, process-locked counter, and wallet transaction signing also
reserves each root/index pair in a durable registry. Consensus validators
must carry the spent-pair set across the full chain.

Pure stdlib. Test keys only. No network.
"""
import hashlib
import json
import os
import sys
from file_locks import exclusive_file_lock, fsync_directory

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from messerene_operator import PATTERN  # canonical source, never prose

P_BYTES = bytes.fromhex(PATTERN)
H = hashlib.sha256


def _h(b: bytes) -> bytes:
    return H(b).digest()


def _rotate(b: bytes, k: int) -> bytes:
    k %= len(b)
    return b[k:] + b[:k]


def _leaf_seed(seed: bytes, idx: int) -> bytes:
    return _h(b"TRIFOLD/LEAF" + seed + _rotate(P_BYTES, idx)
              + idx.to_bytes(4, "big"))


def _secret(seed: bytes, idx: int, pos: int, side: int) -> bytes:
    return _h(b"TRIFOLD/SEC" + _leaf_seed(seed, idx)
              + pos.to_bytes(2, "big") + bytes([side]))


def _leaf_pubhash(seed: bytes, idx: int) -> bytes:
    out = bytearray()
    for pos in range(256):
        for s in (0, 1):
            out += _h(_secret(seed, idx, pos, s))
    return _h(bytes(out))


def to_balanced_ternary(n: int) -> str:
    if n == 0:
        return "0"
    digits = []
    while n:
        r = n % 3
        if r == 2:
            digits.append("T")  # -1
            n = n // 3 + 1
        else:
            digits.append(str(r))
            n //= 3
    return "".join(reversed(digits))


class TrifoldKey:
    """Stateful. The counter climbs in trits and never rolls back.

    One-time-leaf persistence: a Lamport leaf must never sign two
    different messages. Signing requires state_path (a JSON file) or
    state_dir (a directory; the file is named by this tree's root).
    The counter is reserved (incremented + saved) BEFORE
    the signature is built, so a crash after signing cannot cause a
    reuse — at worst a leaf is skipped, never repeated. The
    wallet spent-leaf registry and chain-wide consensus set provide
    independent guards against reuse after a wallet restore or rollback.
    """

    def __init__(self, seed: bytes, height: int = 6,
                 state_path: str = None, state_dir: str = None):
        if not isinstance(seed, bytes) or len(seed) != 32:
            raise ValueError("Trifold seed must be exactly 32 bytes")
        if (not isinstance(height, int) or isinstance(height, bool)
                or not 1 <= height <= 10):
            raise ValueError("Trifold key generation height must be between 1 and 10")
        self.seed = seed
        self.height = height
        self.capacity = 3 ** height
        self.next_index = 0
        level = [_leaf_pubhash(seed, i) for i in range(self.capacity)]
        self._tree = [level]
        while len(level) > 1:
            level = [_h(level[j] + level[j + 1] + level[j + 2])
                     for j in range(0, len(level), 3)]
            self._tree.append(level)
        self.root = self._tree[-1][0]
        self.state_path = state_path
        if self.state_path is None and state_dir is not None:
            self.state_path = os.path.join(
                state_dir, "trifold_state_" + self.root.hex() + ".json")
        if self.state_path is not None:
            self.state_path = os.path.normcase(os.path.abspath(self.state_path))
        self._load_state()

    def _load_state(self):
        """Load next_index when a configured state file is present.
        A file for a different root or a corrupt file fails closed —
        silently resetting to 0
        could reuse a leaf."""
        if not self.state_path or not os.path.exists(self.state_path):
            return
        with open(self.state_path) as f:
            try:
                st = json.load(f)
            except Exception as e:
                raise ValueError(
                    f"corrupt Trifold state file {self.state_path}: {e}")
        if st.get("root") != self.root.hex():
            raise ValueError(
                f"Trifold state file {self.state_path} belongs to a different root (root mismatch)")
        n = st.get("next_index")
        if not isinstance(n, int) or isinstance(n, bool) \
                or n < 0 or n > self.capacity:
            raise ValueError(
                f"corrupt Trifold state file {self.state_path}: "
                f"bad next_index {n!r}")
        self.next_index = n

    def _save_state(self):
        """Atomically persist next_index (tmp + fsync + replace)."""
        if not self.state_path:
            return
        d = os.path.dirname(self.state_path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = self.state_path + ".tmp"
        with open(tmp, "w") as f:
            json.dump({"root": self.root.hex(),
                       "next_index": int(self.next_index)}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.state_path)
        fsync_directory(d or os.path.dirname(self.state_path))

    def _reserve_index(self):
        """Reserve one leaf under the state lock."""
        if self.state_path is None:
            raise RuntimeError("Trifold signing requires a persistent state_path")
        with exclusive_file_lock(self.state_path + ".lock"):
            return self._read_and_reserve_locked()

    def sign(self, msg: bytes):
        """Reserve and use one leaf, requiring durable shared state.

        In-memory-only signing is deliberately disabled: reconstructing a
        key from the seed would otherwise reset its one-time counter.
        """
        if self.state_path is None:
            raise RuntimeError("Trifold signing requires a persistent state_path")
        with exclusive_file_lock(self.state_path + ".lock"):
            idx = self._read_and_reserve_locked()
        return self._sign_reserved(msg, idx)

    def sign_reserved(self, msg: bytes, expected_index: int):
        """Persist a specific leaf reservation, refusing stale counters."""
        if self.state_path is None:
            raise RuntimeError("Trifold signing requires a persistent state_path")
        if (not isinstance(expected_index, int) or isinstance(expected_index, bool)
                or expected_index < 0 or expected_index >= self.capacity):
            raise ValueError("reserved Trifold index is out of range")
        with exclusive_file_lock(self.state_path + ".lock"):
            current = self.next_index
            if os.path.exists(self.state_path):
                with open(self.state_path, "r", encoding="utf-8") as f:
                    try:
                        st = json.load(f)
                    except Exception as exc:
                        raise ValueError(
                            f"corrupt Trifold state file {self.state_path}: {exc}") from exc
                if st.get("root") != self.root.hex():
                    raise ValueError(
                        f"Trifold state file {self.state_path} belongs to a different root")
                stored = st.get("next_index")
                if (not isinstance(stored, int) or isinstance(stored, bool)
                        or stored < 0 or stored > self.capacity):
                    raise ValueError("corrupt Trifold state counter")
                current = max(current, stored)
            if expected_index != current:
                raise RuntimeError(
                    f"Trifold leaf reservation is stale: expected {current}, "
                    f"reserved {expected_index}")
            self.next_index = current + 1
            self._save_state()
        return self._sign_reserved(msg, expected_index)

    def _read_and_reserve_locked(self):
        """Read and advance the counter while the state lock is held."""
        idx = self.next_index
        if os.path.exists(self.state_path):
            with open(self.state_path, "r", encoding="utf-8") as f:
                try:
                    st = json.load(f)
                except Exception as exc:
                    raise ValueError(
                        f"corrupt Trifold state file {self.state_path}: {exc}") from exc
            if st.get("root") != self.root.hex():
                raise ValueError(
                    f"Trifold state file {self.state_path} belongs to a different root")
            stored = st.get("next_index")
            if (not isinstance(stored, int) or isinstance(stored, bool)
                    or stored < 0 or stored > self.capacity):
                raise ValueError(
                    f"corrupt Trifold state file {self.state_path}: "
                    f"bad next_index {stored!r}")
            idx = max(idx, stored)
        if idx >= self.capacity:
            raise RuntimeError("tree exhausted — every leaf spent")
        self.next_index = idx + 1
        self._save_state()
        return idx

    def _sign_reserved(self, msg: bytes, idx: int):
        """Build a signature only for a leaf reserved by an external allocator.

        Used by omega_sign, which holds its epoch lock and durably advances
        the epoch counter before calling this method.
        """
        if (not isinstance(idx, int) or isinstance(idx, bool)
                or idx < 0 or idx >= self.capacity):
            raise ValueError("reserved Trifold index is out of range")
        if not isinstance(msg, bytes):
            raise TypeError("Trifold message must be bytes")
        digest = _h(msg)
        ots_sig, ots_pub = [], []
        for pos in range(256):
            bit = (digest[pos // 8] >> (7 - (pos % 8))) & 1
            ots_sig.append(_secret(self.seed, idx, pos, bit))
            ots_pub.append((_h(_secret(self.seed, idx, pos, 0)),
                            _h(_secret(self.seed, idx, pos, 1))))
        path = []  # two siblings per level in a ternary tree
        j = idx
        for lvl in range(self.height):
            base = (j // 3) * 3
            sibs = [self._tree[lvl][base + t] for t in range(3)
                    if base + t != j]
            path.append(sibs)
            j //= 3
        return {"index": idx, "ots_sig": ots_sig, "ots_pub": ots_pub,
                "path": path}


def verify(root: bytes, msg: bytes, sig) -> bool:
    try:
        if not isinstance(root, bytes) or len(root) != 32:
            return False
        if not isinstance(msg, bytes) or not isinstance(sig, dict):
            return False
        idx = sig["index"]
        ots_sig = sig["ots_sig"]
        ots_pub = sig["ots_pub"]
        path = sig["path"]
        if (not isinstance(idx, int) or isinstance(idx, bool)
                or not isinstance(path, (list, tuple))
                or not 1 <= len(path) <= 15
                or idx < 0 or idx >= 3 ** len(path)):
            return False
        if (not isinstance(ots_sig, (list, tuple)) or len(ots_sig) != 256
                or not isinstance(ots_pub, (list, tuple))
                or len(ots_pub) != 256):
            return False
        if any(not isinstance(x, bytes) or len(x) != 32 for x in ots_sig):
            return False
        if any(not isinstance(pair, (list, tuple)) or len(pair) != 2
               or any(not isinstance(x, bytes) or len(x) != 32 for x in pair)
               for pair in ots_pub):
            return False
        if any(not isinstance(level, (list, tuple)) or len(level) != 2
               or any(not isinstance(x, bytes) or len(x) != 32 for x in level)
               for level in path):
            return False
        digest = _h(msg)
        out = bytearray()
        for pos in range(256):
            bit = (digest[pos // 8] >> (7 - (pos % 8))) & 1
            if _h(ots_sig[pos]) != ots_pub[pos][bit]:
                return False
            out += ots_pub[pos][0] + ots_pub[pos][1]
        node = _h(bytes(out))
        j = idx
        for sibs in path:
            sib_iter = iter(sibs)
            children = []
            for t in range(3):
                children.append(node if j % 3 == t else next(sib_iter))
            node = _h(children[0] + children[1] + children[2])
            j //= 3
        return node == root
    except (KeyError, TypeError, ValueError, OverflowError, IndexError, StopIteration):
        return False


def sig_size(sig) -> int:
    n = 4
    n += sum(len(x) for x in sig["ots_sig"])
    n += sum(len(a) + len(b) for a, b in sig["ots_pub"])
    n += sum(len(s) for lvl in sig["path"] for s in lvl)
    return n


def _demo(key, t0):
    t1 = time.time()
    print(f"ternary height 6 -> {key.capacity} leaves | build {t1 - t0:.1f}s")
    print(f"root: {key.root.hex()[:40]}…")
    print(f"pattern in the schedule: {PATTERN[:36]}… (period-9, canonical)\n")
    for m in (b"trifold transfer #1", b"trifold transfer #2"):
        s = key.sign(m)
        print(f"leaf {s['index']} (balanced ternary "
              f"{to_balanced_ternary(s['index'])}): verify vs root -> "
              f"{verify(key.root, m, s)} | size {sig_size(s)} bytes")
        if m.endswith(b"#1"):
            first = (m, s)
    print(f"tampered message -> {verify(key.root, first[0] + b'!', first[1])}")
    print(f"counter now at leaf {key.next_index} "
          f"(ternary {to_balanced_ternary(key.next_index)}) — forward only.")
    print("\nThe public pattern adds no entropy. One-time leaf state must")
    print("never be reused; hash-based construction is not peer reviewed.")


if __name__ == "__main__":
    import time
    import tempfile

    print("TRIFOLD: Lamport one-time leaves in a ternary Merkle tree.")
    print("Custom hash-based parameterization; no formal security proof.\n")
    started = time.time()
    with tempfile.TemporaryDirectory() as state_dir:
        key = TrifoldKey(
            hashlib.sha256(b"TEST KEY ONLY - trifold demo seed").digest(),
            height=6, state_dir=state_dir)
        _demo(key, started)
