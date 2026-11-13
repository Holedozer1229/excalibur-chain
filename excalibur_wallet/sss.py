"""sss.py — Shamir's Secret Sharing for wallet seed backup.

The "sss" in Lux's build order, read as Shamir's Secret Sharing:
a wallet seed splits into n shares; any k of them rebuild it, and
k-1 shares reveal nothing. Shares are for paper/metal backup in
separate places — one share alone is useless.

Construction: standard Shamir over GF(2^8) (the AES field,
polynomial x^8 + x^4 + x^3 + x + 1, generator 3). Each byte of the
secret gets its own random degree-(k-1) polynomial; a share is the
evaluation of every byte-polynomial at the share's x-coordinate.
Coefficients come from os.urandom — never from a counter or a
timestamp.

Share encoding: hex of (x_byte || share_bytes). x is 1..n (never 0).
A share reveals its x in the clear; that is by design (x is not
secret — the polynomial is).

Security notes, stated plainly:
  * This is backup, not encryption: anyone holding k shares holds
    the seed. Store shares like keys — separate places, no photos
    in the cloud, no chat messages.
  * Recombining on a compromised machine exposes the seed. Combine
    only on the machine that will hold the wallet, then clear the
    shares from its memory (this module zeroes nothing itself — the
    caller must not persist the recombined seed outside the wallet
    file).
  * GF(256) arithmetic here is a compact, tested implementation
    (exponent/log tables built from the field definition at import).
    It is NOT a toy: the test suite reconstructs from every 3-of-5
    subset and asserts 2 shares do not reconstruct.
"""
import os

# GF(2^8), poly 0x11b, generator 3.
_EXP = [0] * 512
_LOG = [0] * 256


def _init_tables():
    # Generator 3 (x+1): 2 has order 51 in the AES field, NOT 255 —
    # building the table by doubling would only cover 51 elements and
    # silently corrupt every multiply/divide. 3 is primitive here.
    x = 1
    for i in range(255):
        _EXP[i] = x
        _LOG[x] = i
        x2 = x << 1
        if x2 & 0x100:
            x2 ^= 0x11B
        x = x2 ^ x  # multiply by 3
    for i in range(255, 512):
        _EXP[i] = _EXP[i - 255]


_init_tables()


def _gf_mul(a, b):
    if a == 0 or b == 0:
        return 0
    return _EXP[_LOG[a] + _LOG[b]]


def _gf_div(a, b):
    if b == 0:
        raise ZeroDivisionError("GF(256) division by zero")
    if a == 0:
        return 0
    return _EXP[(_LOG[a] - _LOG[b]) % 255]


def _eval_poly(coeffs, x):
    """Horner evaluation over GF(256). coeffs[0] is the constant term."""
    result = 0
    for c in reversed(coeffs):
        result = _gf_mul(result, x) ^ c
    return result


def split(secret: bytes, n: int, k: int):
    """Split `secret` into n shares with threshold k.
    Returns [(x, share_bytes)] with x in 1..n. Raises on bad params."""
    if not (2 <= k <= n <= 255):
        raise ValueError("need 2 <= k <= n <= 255")
    if not secret:
        raise ValueError("secret must not be empty")
    polys = []
    for byte in secret:
        coeffs = [byte] + [b for b in os.urandom(k - 1)]
        polys.append(coeffs)
    shares = []
    for x in range(1, n + 1):
        y = bytes(_eval_poly(coeffs, x) for coeffs in polys)
        shares.append((x, y))
    return shares


def combine(shares):
    """Rebuild the secret from >= k shares [(x, share_bytes)].
    Uses Lagrange interpolation at x=0. Raises on duplicate x,
    mismatched lengths, or x == 0."""
    if len(shares) < 2:
        raise ValueError("need at least 2 shares to combine")
    xs = [x for x, _ in shares]
    if len(set(xs)) != len(xs):
        raise ValueError("duplicate share x-coordinate")
    if any(x == 0 for x in xs):
        raise ValueError("share x-coordinate must not be 0")
    length = len(shares[0][1])
    if any(len(y) != length for _, y in shares):
        raise ValueError("shares have mismatched lengths")
    out = bytearray()
    for pos in range(length):
        acc = 0
        for i, (xi, yi) in enumerate(shares):
            # Lagrange basis at 0: prod_{j!=i} x_j / (x_j - xi)
            num = den = 1
            for j, (xj, _) in enumerate(shares):
                if i == j:
                    continue
                num = _gf_mul(num, xj)
                den = _gf_mul(den, xj ^ xi)
            acc ^= _gf_mul(yi[pos], _gf_div(num, den))
        out.append(acc)
    return bytes(out)


def encode_share(x: int, share: bytes) -> str:
    """Share -> hex string (x byte + share bytes)."""
    return (bytes([x]) + share).hex()


def decode_share(s: str):
    """Hex string -> (x, share_bytes)."""
    raw = bytes.fromhex(s.strip())
    if len(raw) < 2:
        raise ValueError("share too short")
    return raw[0], raw[1:]
