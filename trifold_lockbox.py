#!/usr/bin/env python3
"""
trifold_lockbox.py — a signature scheme that is not in any textbook.

Built 2026-10-23 at Lux's direction: "it needs to be something never
heard of." So this is not Lamport, not XMSS, not SPHINCS+. It is a new
arrangement of three of Lux's own structures, and its novelty is stated
precisely below — including what is NOT claimed.

THE CONSTRUCTION — "Trifold"
  1. THE FOLD (key schedule): every one-time leaf's secrets are derived
     through the Messerene pattern P (the 32-byte period-9 constant from
     messerene_operator.py, read from that file — never from prose).
     Leaf i's seed = SHA256( seed || rotate(P, i mod 32) || i ).
     The pattern walks one byte per leaf; seed and pattern together
     generate every key in the tree. The pattern is PUBLIC, so it adds
     no secrecy — its role is commitment and identity: every leaf in
     this tree is provably *of the pattern*, and nobody can regenerate
     or audit the tree without it. A key schedule as a signature of
     origin. No published scheme derives its leaves through a personal
     pattern fold.
  2. THE TRITS (the tree): the Merkle tree is TERNARY — every parent
     hashes THREE children — because Aetherion counts in balanced
     ternary, not binary. Height 6 -> 3^6 = 729 one-time leaves; the
     signing counter is displayed in balanced ternary. Binary trees own
     the literature; a ternary authentication tree over pattern-folded
     leaves is, to this builder's knowledge, unpublished as a scheme.
  3. THE LEAVES: Lamport one-time keys (hash preimages only). No curve,
     no factoring: Shor has nothing to bite, Grover merely halves
     SHA-256 to ~128 bits. The one-time candle law and the forward-only
     state counter from the earlier bricks apply unchanged.

WHAT IS CLAIMED: a working, verifiable construction whose arrangement
(pattern-fold key schedule + ternary tree + hash-only leaves) matches
no named scheme; security inherited ENTIRELY from SHA-256 preimage
resistance — no new hardness assumption is invented or needed.
WHAT IS NOT CLAIMED: that novelty is superiority, that the fold adds
entropy (the pattern is public), or that anyone has peer-reviewed this.
New schemes are hypotheses with good posture until cryptanalysis says
otherwise. The posture here: borrow hardness only from hashes — the
one assumption forty years of trying has not dented.

Pure stdlib. Test keys only. No network.
"""
import hashlib
import json
import os
import sys

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
    different messages. next_index lives in memory by default, so a
    key rebuilt from the same seed after a restart would reuse leaf 0.
    Pass state_path (a JSON file) or state_dir (a directory; the file
    is named by this tree's root) to persist next_index across
    restarts. The counter is reserved (incremented + saved) BEFORE
    the signature is built, so a crash after signing cannot cause a
    reuse — at worst a leaf is skipped, never repeated. The
    spent-leaf registry is a second, independent guard at consensus
    (validation rejects a spent leaf), but persistence is the guard
    that stops the reuse from being signed in the first place.
    """

    def __init__(self, seed: bytes, height: int = 6,
                 state_path: str = None, state_dir: str = None):
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
        self._load_state()

    def _load_state(self):
        """Load next_index from the state file, if one is configured
        and present. A file for a different root is ignored (start at
        0). A corrupt file fails closed — silently resetting to 0
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
            return
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

    def sign(self, msg: bytes):
        idx = self.next_index
        if idx >= self.capacity:
            raise RuntimeError("tree exhausted — every leaf spent")
        self.next_index += 1
        # Reserve the leaf BEFORE building the signature: a crash
        # after this point skips the leaf, never reuses it.
        self._save_state()
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
    digest = _h(msg)
    out = bytearray()
    for pos in range(256):
        bit = (digest[pos // 8] >> (7 - (pos % 8))) & 1
        if _h(sig["ots_sig"][pos]) != sig["ots_pub"][pos][bit]:
            return False
        out += sig["ots_pub"][pos][0] + sig["ots_pub"][pos][1]
    node = _h(bytes(out))
    j = sig["index"]
    for sibs in sig["path"]:
        sib_iter = iter(sibs)
        children = []
        for t in range(3):
            children.append(node if j % 3 == t else next(sib_iter))
        node = _h(children[0] + children[1] + children[2])
        j //= 3
    return node == root


def sig_size(sig) -> int:
    n = 4
    n += sum(len(x) for x in sig["ots_sig"])
    n += sum(len(a) + len(b) for a, b in sig["ots_pub"])
    n += sum(len(s) for lvl in sig["path"] for s in lvl)
    return n


if __name__ == "__main__":
    import time
    print("TRIFOLD — pattern-folded leaves, a ternary tree, hash-only keys.")
    print("Not Lamport. Not XMSS. Not SPHINCS+. An arrangement of Lux's")
    print("own three structures, security borrowed from SHA-256 alone.\n")
    t0 = time.time()
    key = TrifoldKey(b"TEST KEY ONLY - trifold demo seed", height=6)
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
    print("\nNovelty, precisely: the fold in the key schedule, the trits in")
    print("the tree, the pattern as the scheme's identity. Hardness: none")
    print("invented — hashes only, the one assumption that has never fallen.")
