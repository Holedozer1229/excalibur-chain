#!/usr/bin/env python3
"""
THE MESSERENE OPERATOR  (invented 2026-10-20, at Lux's direction: "Invent the operator")

Purpose: the missing map between Lux's patterned key and a keypair.
The pattern carries the structure (alphabet A-E, ascending odds / descending
evens, Mersenne-prime separators). The operator is the fold from that
pattern to secp256k1.

DEFINITION
  Pattern P: 64 hex chars = 32 (letter, digit) pairs, block "A1B3C5D7E9F8D6C4B2" x3 + "A1B3C5D7E9".

  Main derivation (the pre-genesis fold):
      k  = ( int( SHA-256( "MESSERENE/PREGENESIS/v1" || P_bytes ) ) mod (n-1) ) + 1
      K  = k * G                         (the generated genesis point)

  Selector sub-derivations (echoing the commitment's P=1, Q=2, R=0):
      k_s = ( int( SHA-256( "MESSERENE/SEL=" || byte(s) || P_bytes ) ) mod (n-1) ) + 1
      h_s = SHA-256( k_s as 32-byte big-endian )[:8 bytes hex]   <- a commitment
            triple whose preimages are KNOWN by construction (the pattern).

Properties: deterministic (same pattern -> same keypair, every time),
domain-separated (this fold collides with no other use of the pattern),
and verifiable (anyone holding the pattern can recompute every output).

LANE: this operator generates a NEW genesis keypair from the pattern
(e.g. for a chain whose block 0 does not exist yet). It does not, and no
invented operator can, recover Bitcoin's genesis private key.
Pure stdlib.
"""
import hashlib

P_FIELD = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
Gx = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
Gy = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8

PATTERN = "A1B3C5D7E9F8D6C4B2A1B3C5D7E9F8D6C4B2A1B3C5D7E9F8D6C4B2A1B3C5D7E9"

def inv(a): return pow(a, P_FIELD - 2, P_FIELD)
def add(p1, p2):
    if p1 is None: return p2
    if p2 is None: return p1
    x1, y1 = p1; x2, y2 = p2
    if x1 == x2 and (y1 + y2) % P_FIELD == 0: return None
    m = ((3 * x1 * x1) * inv(2 * y1)) % P_FIELD if p1 == p2 else ((y2 - y1) * inv(x2 - x1)) % P_FIELD
    x3 = (m * m - x1 - x2) % P_FIELD
    return (x3, (m * (x1 - x3) - y1) % P_FIELD)
def mul(k, pt=(Gx, Gy)):
    r = None
    while k:
        if k & 1: r = add(r, pt)
        pt = add(pt, pt); k >>= 1
    return r

def h160(b):
    h = hashlib.new("ripemd160"); h.update(hashlib.sha256(b).digest()); return h.digest()
B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58check(payload: bytes) -> str:
    chk = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    raw = payload + chk
    n = int.from_bytes(raw, "big"); s = ""
    while n: n, r = divmod(n, 58); s = B58[r] + s
    return "1" * (len(raw) - len(raw.lstrip(b"\x00"))) + s
BECH = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
def _pm(vals):
    chk = 1; gen = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    for v in vals:
        top = chk >> 25; chk = ((chk & 0x1ffffff) << 5) ^ v
        for i in range(5):
            if (top >> i) & 1: chk ^= gen[i]
    return chk
def _cb(data, fb, tb):
    acc = 0; bits = 0; ret = []
    for v in data:
        acc = (acc << fb) | v; bits += fb
        while bits >= tb:
            bits -= tb; ret.append((acc >> bits) & ((1 << tb) - 1))
    if bits: ret.append((acc << (tb - bits)) & ((1 << tb) - 1))
    return ret
def p2wpkh(h: bytes) -> str:
    data = [0] + _cb(h, 8, 5)
    vals = [ord(c) >> 5 for c in "bc"] + [0] + [ord(c) & 31 for c in "bc"] + data + [0] * 6
    pm = _pm(vals) ^ 1
    return "bc1" + "".join(BECH[d] for d in data + [(pm >> 5 * (5 - i)) & 31 for i in range(6)])

# ---------------- the operator ----------------
def messerene(pattern_hex: str, domain: bytes) -> int:
    """The fold: domain-separated SHA-256 of the pattern, mapped into [1, n-1]."""
    digest = hashlib.sha256(domain + bytes.fromhex(pattern_hex)).digest()
    return (int.from_bytes(digest, "big") % (N - 1)) + 1

def derive(pattern_hex: str):
    k = messerene(pattern_hex, b"MESSERENE/PREGENESIS/v1")
    x, y = mul(k)
    pub_c = bytes([0x02 | (y & 1)]) + x.to_bytes(32, "big")
    return k, pub_c

if __name__ == "__main__":
    k, pub_c = derive(PATTERN)
    k2, pub_c2 = derive(PATTERN)   # determinism check
    print("Pattern:        0x" + PATTERN)
    print("Operator:       k = (SHA256('MESSERENE/PREGENESIS/v1' || P) mod (n-1)) + 1 ;  K = k*G")
    print("Deterministic: ", (k, pub_c) == (k2, pub_c2))
    print()
    print("GENERATED GENESIS KEYPAIR (from the pattern, by the operator)")
    print("  private key:  %064x" % k)
    print("  WIF:          " + b58check(b"\x80" + k.to_bytes(32, "big") + b"\x01"))
    print("  pubkey (c):   " + pub_c.hex())
    print("  P2PKH:        " + b58check(b"\x00" + h160(pub_c)))
    print("  P2WPKH:       " + p2wpkh(h160(pub_c)))
    print()
    print("SELECTOR SUB-DERIVATIONS -> a commitment triple with KNOWN preimages")
    for name, s in (("P", 1), ("Q", 2), ("R", 0)):
        ks = messerene(PATTERN, b"MESSERENE/SEL=" + bytes([s]))
        hs = hashlib.sha256(ks.to_bytes(32, "big")).hexdigest()[:16]
        print(f"  sel {name}={s}: k_s = {ks:064x}  ->  h{name.lower()} = {hs}")
    print()
    print("Verify any line above by rerunning: same pattern in, same values out.")
