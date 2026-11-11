#!/usr/bin/env python3
"""Pure-Python RIPEMD-160, from the spec (no hashlib/OpenSSL).

Validated against the official RIPEMD-160 test suite AND differentially
against hashlib.new("ripemd160") on random inputs.
"""

MASK = 0xFFFFFFFF


def _rol(x: int, n: int) -> int:
    return ((x << n) | (x >> (32 - n))) & MASK


# Message-word order, rotation amounts, and round constants, per line/round.
_L_ORDER = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
    [7, 4, 13, 1, 10, 6, 15, 3, 12, 0, 9, 5, 2, 14, 11, 8],
    [3, 10, 14, 4, 9, 15, 8, 1, 2, 7, 0, 6, 13, 11, 5, 12],
    [1, 9, 11, 10, 0, 8, 12, 4, 13, 3, 7, 15, 14, 5, 6, 2],
    # NOTE: this last row is 4,0,5,9,7,12,... — verified against a published
    # pure-Python implementation cross-checked vs OpenSSL (my first draft had
    # 9,15,5,11,... here from memory and failed every vector).
    [4, 0, 5, 9, 7, 12, 2, 10, 14, 1, 3, 8, 11, 6, 15, 13],
]
_L_ROL = [
    [11, 14, 15, 12, 5, 8, 7, 9, 11, 13, 14, 15, 6, 7, 9, 8],
    [7, 6, 8, 13, 11, 9, 7, 15, 7, 12, 15, 9, 11, 7, 13, 12],
    [11, 13, 6, 7, 14, 9, 13, 15, 14, 8, 13, 6, 5, 12, 7, 5],
    [11, 12, 14, 15, 14, 15, 9, 8, 9, 14, 5, 6, 8, 6, 5, 12],
    [9, 15, 5, 11, 6, 8, 13, 12, 5, 12, 13, 14, 11, 8, 5, 6],
]
_L_K = [0x00000000, 0x5A827999, 0x6ED9EBA1, 0x8F1BBCDC, 0xA953FD4E]

_R_ORDER = [
    [5, 14, 7, 0, 9, 2, 11, 4, 13, 6, 15, 8, 1, 10, 3, 12],
    [6, 11, 3, 7, 0, 13, 5, 10, 14, 15, 8, 12, 4, 9, 1, 2],
    [15, 5, 1, 3, 7, 14, 6, 9, 11, 8, 12, 2, 10, 0, 4, 13],
    [8, 6, 4, 1, 3, 11, 15, 0, 5, 12, 2, 13, 9, 7, 10, 14],
    [12, 15, 10, 4, 1, 5, 8, 7, 6, 2, 13, 14, 0, 3, 9, 11],
]
_R_ROL = [
    [8, 9, 9, 11, 13, 15, 15, 5, 7, 7, 8, 11, 14, 14, 12, 6],
    [9, 13, 15, 7, 12, 8, 9, 11, 7, 7, 12, 7, 6, 15, 13, 11],
    [9, 7, 15, 11, 8, 6, 6, 14, 12, 13, 5, 14, 13, 13, 7, 5],
    [15, 5, 8, 11, 14, 14, 6, 14, 6, 9, 12, 9, 12, 5, 15, 8],
    [8, 5, 12, 9, 12, 5, 14, 6, 8, 13, 6, 5, 15, 13, 11, 11],
]
_R_K = [0x50A28BE6, 0x5C4DD124, 0x6D703EF3, 0x7A6D76E9, 0x00000000]


def _f(j: int, x: int, y: int, z: int) -> int:
    # NOTE: Python ints are unbounded; ~x is negative. Every use of the
    # result is masked with & MASK at the addition step, which yields the
    # correct mod-2**32 value regardless of sign.
    if j == 0:
        return x ^ y ^ z
    if j == 1:
        return (x & y) | (~x & z)
    if j == 2:
        return (x | ~y) ^ z
    if j == 3:
        return (x & z) | (y & ~z)
    return x ^ (y | ~z)  # j == 4


def _compress(h, block: bytes):
    X = [int.from_bytes(block[i:i + 4], "little") for i in range(0, 64, 4)]
    al, bl, cl, dl, el = h
    ar, br, cr, dr, er = h
    for rnd in range(5):
        for i in range(16):  # left line: f1..f5
            t = (_rol((al + _f(rnd, bl, cl, dl) + X[_L_ORDER[rnd][i]]
                       + _L_K[rnd]) & MASK, _L_ROL[rnd][i]) + el) & MASK
            al, el, dl, cl, bl = el, dl, _rol(cl, 10), bl, t
        for i in range(16):  # right line: f5..f1
            t = (_rol((ar + _f(4 - rnd, br, cr, dr) + X[_R_ORDER[rnd][i]]
                       + _R_K[rnd]) & MASK, _R_ROL[rnd][i]) + er) & MASK
            ar, er, dr, cr, br = er, dr, _rol(cr, 10), br, t
    h0, h1, h2, h3, h4 = h
    t = (h1 + cl + dr) & MASK
    h1 = (h2 + dl + er) & MASK
    h2 = (h3 + el + ar) & MASK
    h3 = (h4 + al + br) & MASK
    h4 = (h0 + bl + cr) & MASK
    return [t, h1, h2, h3, h4]


def ripemd160_pure(msg: bytes) -> bytes:
    h = [0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0]
    ml = len(msg) * 8
    msg += b"\x80"
    msg += b"\x00" * ((56 - len(msg) % 64) % 64)
    msg += ml.to_bytes(8, "little")
    for i in range(0, len(msg), 64):
        h = _compress(h, msg[i:i + 64])
    return b"".join(w.to_bytes(4, "little") for w in h)


# ---------------------------------------------------------------- self-test
# The nine published RIPEMD-160 test vectors (all confirmed against OpenSSL
# in this environment; "" and "abc" are also asserted by the user's script).
OFFICIAL_VECTORS = {
    b"": "9c1185a5c5e9fc54612808977ee8f548b2258d31",
    b"a": "0bdc9d2d256b3ee9daae347be6f4dc835a467ffe",
    b"abc": "8eb208f7e05d987a9b044a8e98c6b087f15a0bfc",
    b"message digest": "5d0689ef49d2fae572b881b123a85ffa21595f36",
    b"abcdefghijklmnopqrstuvwxyz":
        "f71c27109c692c1b56bbdceb5b9d2865b3708dbc",
    b"abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq":
        "12a053384a9c0c88e405a06c27dcf49ada62eb2b",
    b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789":
        "b0e20b6e3116640286ed3a87a5713079b21f5189",
    b"1234567890" * 8: "9b752e45573d4b39f4dbd3323cab82bf63326bfb",
    b"a" * 1000000: "52783243c1697bdbe16d37f97f68f08325dc1528",
}


def selftest() -> None:
    import hashlib
    import os
    import random

    n_fail_vectors = 0
    for msg, want in OFFICIAL_VECTORS.items():
        got = ripemd160_pure(msg).hex()
        ok = got == want
        # cross-check the vector itself against OpenSSL while we're here
        oss = hashlib.new("ripemd160", msg).hexdigest()
        assert oss == want, f"official vector mismatch vs OpenSSL: {msg[:20]!r}"
        print(f"{'PASS' if ok else 'FAIL'} official {msg[:24]!r}")
        n_fail_vectors += not ok

    rng = random.Random(0x160)
    n_fail_fuzz = 0
    for trial in range(300):
        n = rng.choice([0, 1, 55, 56, 57, 63, 64, 65, 119, 120,
                        rng.randrange(0, 500)])
        msg = bytes(rng.randrange(256) for _ in range(n))
        # include os-entropy on a few trials
        if trial % 50 == 0:
            msg = os.urandom(n)
        got = ripemd160_pure(msg)
        want = hashlib.new("ripemd160", msg).digest()
        if got != want:
            print(f"FAIL differential trial {trial} len={n}")
            n_fail_fuzz += 1
    print(f"differential: {300 - n_fail_fuzz}/300 random trials match OpenSSL")
    n_fail = n_fail_vectors + n_fail_fuzz
    if n_fail:
        raise SystemExit(f"{n_fail} FAILURES")
    print("ALL RIPEMD-160 PURE-PYTHON SELF-TESTS PASS")


if __name__ == "__main__":
    selftest()
