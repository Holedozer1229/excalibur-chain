#!/usr/bin/env python3
"""Deep dive into tau(28) = -703236000 and its connection to the Messerene pattern at pos 28."""

import hashlib
import sys
sys.path.insert(0, '.')

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58check(payload: bytes) -> str:
    chk = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    raw = payload + chk
    n = int.from_bytes(raw, 'big')
    encoded = ''
    while n > 0:
        n, r = divmod(n, 58)
        encoded = B58[r] + encoded
    return encoded

# Known correct tau values from OEIS A000594
tau_known = {
    1: 1, 2: -24, 3: 252, 4: -1472, 5: 4830, 6: -6048, 7: -16744,
    8: 84480, 9: -113643, 10: -115920, 11: 534612, 12: -370944,
    13: 116178, 14: 2429088, 15: -667896, 16: -1067832, 17: 1323480,
    18: -457644, 19: 5751360, 20: 1211664, 21: 276336, 22: 1441152,
    23: 2114700, 24: 1560336, 25: 262080, 26: 10266192, 27: -1018704,
    # tau(28) = tau(4)*tau(7) = -1472 * -16744 = 24647168 (multiplicative, gcd(4,7)=1)
    28: 24647168,
}

TAU_28 = tau_known[28]
ABS_TAU = abs(TAU_28)
GENESIS_NONCE = 2083236893
DLP_TARGET = 543854440
DLP_PRIME = 2083237931

print('=' * 78)
print('tau(28) = 24647168 — CORRECT VALUE (tau(4)*tau(7) = -1472 * -16744)')
print('=' * 78)
print()

print(f'tau(28) = {TAU_28}')
print(f'|tau(28)| = {ABS_TAU}')
print(f'hex: 0x{ABS_TAU:x}')
tau_32be = ABS_TAU.to_bytes(32, 'big')
print(f'32-byte big-endian: {tau_32be.hex()}')
print()

# Ramanujan congruence with correct values
def sigma_11(n):
    s = 0
    for d in range(1, n + 1):
        if n % d == 0:
            s += d ** 11
    return s

print('RAMANUJAN CONGRUENCE (correct tau values):')
print('tau(n) = sigma_11(n) mod 691')
print()
for n in range(1, 29):
    t = tau_known[n]
    s = sigma_11(n)
    t_mod = t % 691
    s_mod = s % 691
    match = t_mod == s_mod
    if n <= 10 or n == 28 or not match:
        print(f'  n={n}: tau={t:>15d}, sigma_11={s:>15d}, '
              f'tau%%691={t_mod:>3d}, sigma%%691={s_mod:>3d}, match={match}')

print()
print(f'tau(28) mod 691 = {TAU_28 % 691}')
print(f'sigma_11(28) mod 691 = {sigma_11(28) % 691}')
print()

# Factorization
print('FACTORIZATION:')
temp = ABS_TAU
factors = []
d = 2
while d * d <= temp:
    while temp % d == 0:
        factors.append(d)
        temp //= d
    d += 1
if temp > 1:
    factors.append(temp)
print(f'  {ABS_TAU} = {" x ".join(map(str, factors))}')
print(f'  Prime factors: {sorted(set(factors))}')
print()

# 58603 analysis
print('PRIME 58603:')
is_p = all(58603 % d != 0 for d in range(2, int(58603 ** 0.5) + 1))
print(f'  58603 is prime: {is_p}')
print(f'  58603 %% 691 = {58603 % 691}')
print(f'  58603 %% 28 = {58603 % 28}')
print(f'  58603 in hex: 0x{58603:x}')
print()

# Genesis nonce connection
print('GENESIS NONCE CONNECTION:')
print(f'  GENESIS_NONCE = {GENESIS_NONCE}')
print(f'  |tau(28)| = {ABS_TAU}')
print(f'  GENESIS_NONCE - |tau(28)| = {GENESIS_NONCE - ABS_TAU}')
print(f'  GENESIS_NONCE / |tau(28)| = {GENESIS_NONCE / ABS_TAU:.6f}')
print(f'  GENESIS_NONCE %% |tau(28)| = {GENESIS_NONCE % ABS_TAU}')
print()

# DLP field
print('DLP FIELD:')
print(f'  2^|tau(28)| mod p = {pow(2, ABS_TAU, DLP_PRIME)}')
print(f'  Does 2^|tau(28)| mod p = DLP_TARGET? {pow(2, ABS_TAU, DLP_PRIME) == DLP_TARGET}')
print()

# secp256k1 derivation
print('SECP256K1 DERIVATION from |tau(28)|:')
from secp256k1 import _mul, compress

pub = _mul(ABS_TAU)
comp = compress(pub)
print(f'  Compressed pubkey: {comp.hex()}')

h = hashlib.sha256(comp).digest()
ripemd = hashlib.new('ripemd160', h).digest()
print(f'  RIPEMD160: {ripemd.hex()}')

# Bech32
def bech32_encode(hrp, data):
    charset = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l'
    def polymod(values):
        c = 1
        for v in values:
            c0 = c >> 25
            c = ((c & 0x1ffffff) << 5) ^ v
            for i in range(5):
                if (c >> (4 - i)) & 1:
                    c ^= 0x3b6a57b2 >> (5 - i)
        return c ^ 1
    def expand(hrp):
        return [ord(x) >> 5 for x in hrp] + [0] + [ord(x) & 31 for x in hrp]
    def encode_iter(data):
        res = []
        datum = 0
        bitcount = 0
        for d in data:
            datum = (datum << 8) | d
            bitcount += 8
            while bitcount >= 5:
                bitcount -= 5
                res.append(datum >> bitcount)
            datum &= (1 << bitcount) - 1
        if bitcount > 0:
            res.append(datum)
        return res
    values = expand(hrp) + encode_iter(data) + [0, 0, 0, 0, 0, 0]
    pm = polymod(values)
    res = hrp + '1'
    for i in range(6):
        res += charset[(pm >> (5 * (5 - i))) & 31]
    return res

bech32_addr = bech32_encode('bc', [0] + list(ripemd))
print(f'  P2WPKH: {bech32_addr}')

version = b'\x00'
p2pkh = version + ripemd
print(f'  P2PKH: 1' + b58check(p2pkh))
print()

# Messerene pattern completion
print('MESSERENE PATTERN COMPLETION:')
pattern = 'A1B3C5D7E9F8D6C4B2A0E8F6D4C2B0A8E6F4D2C0B8A6E4D2C0B8A6E4D2C0'
pattern_bytes = bytes.fromhex(pattern)
print(f'  Pattern (30 bytes): {pattern}')
print(f'  Pos 28: 0x{pattern_bytes[28]:02x} (D2)')
print(f'  Pos 29: 0x{pattern_bytes[29]:02x} (C0)')
print()

tau_bytes = ABS_TAU.to_bytes(4, 'big')
print(f'  |tau(28)| bytes: {tau_bytes.hex()}')
print()

N_secp = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

# All completion options
options = [
    ('tau[:2] replace pos 28-29', pattern_bytes[:28] + tau_bytes[:2]),
    ('tau[2:] replace pos 28-29', pattern_bytes[:28] + tau_bytes[2:]),
    ('tau[:2] append', pattern_bytes + tau_bytes[:2]),
    ('tau[2:] append', pattern_bytes + tau_bytes[2:]),
    ('genesis nonce replace', pattern_bytes[:28] + GENESIS_NONCE.to_bytes(4, 'big')),
    ('tau XOR nonce replace', pattern_bytes[:28] + (ABS_TAU ^ GENESIS_NONCE).to_bytes(4, 'big')),
]

for label, completed in options:
    print(f'  {label}:')
    print(f'    {completed.hex()}')
    priv = int.from_bytes(completed, 'big')
    if 0 < priv < N_secp:
        pub = _mul(priv)
        comp = compress(pub)
        h = hashlib.sha256(comp).digest()
        ripemd = hashlib.new('ripemd160', h).digest()
        addr = bech32_encode('bc', [0] + list(ripemd))
        print(f'    P2WPKH: {addr}')
    else:
        print(f'    Invalid private key (out of range)')
    print()

# Hash relationships
print('SHA256 OF COMPLETED PATTERNS:')
for label, completed in options:
    h = hashlib.sha256(completed).hexdigest()
    print(f'  {label}: {h[:24]}...')

print()
print('=' * 78)
