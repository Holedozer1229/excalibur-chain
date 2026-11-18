#!/usr/bin/env python3
"""Try 691 (Ramanujan's famous prime) as the DR Time seed component."""

import hashlib
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trifold_lockbox import TrifoldKey

BAD_BLOCK_HASH = "0000000000790ab3f22ec756ad43b6ab569abf0bddeb97c67a6f7b1470a7ec1c"
CANONICAL_ROOT = "7083fbebd6bfbd5f82fd40827cf36bc30da81524914011e69488b5a63e7bfe55"
bad_block_bytes = bytes.fromhex(BAD_BLOCK_HASH)

# 691 is the famous Ramanujan prime
# tau(n) = sigma_11(n) mod 691 for all n
# It's the smallest prime divisor of tau(25)

print("Ramanujan's prime 691 and DR Time...")
print()

def sigma_11(n):
    s = 0
    for d in range(1, n+1):
        if n % d == 0:
            s += d**11
    return s

# Compute values first
# tau(28) = tau(4)*tau(7) = -1472 * -16744 = 24647168 (multiplicative property, gcd(4,7)=1)
s11_28 = sigma_11(28)
s11_28_mod = s11_28 % 691
t28_mod = (24647168) % 691  # Correct tau(28) mod 691
s11_25 = sigma_11(25)

print(f"sigma_11(28) = {s11_28}")
print(f"sigma_11(28) mod 691 = {s11_28_mod}")
print(f"tau(28) = 24647168 (corrected: tau(4)*tau(7))")
print(f"tau(28) mod 691 = {t28_mod}")
print(f"Match: {s11_28_mod == t28_mod}")
print(f"sigma_11(25) = {s11_25}")
print(f"sigma_11(25) mod 691 = {s11_25 % 691}")
print(f"tau(25) = 1365457664")
print(f"tau(25) mod 691 = {1365457664 % 691}")
print()

candidates = [
    ("SHA256('Dr. Time: 691')", hashlib.sha256(b"Dr. Time: 691").digest()),
    ("SHA256('Dr. Time: Ramanujan 691')", hashlib.sha256(b"Dr. Time: Ramanujan 691").digest()),
    ("SHA256('Dr. Time: tau mod 691')", hashlib.sha256(b"Dr. Time: tau mod 691").digest()),
    ("SHA256('Dr. Time: tau(n) = sigma_11(n) mod 691')", hashlib.sha256(b"Dr. Time: tau(n) = sigma_11(n) mod 691").digest()),
    ("SHA256('Dr. Time: ' + 691_bytes_4BE)", hashlib.sha256(b"Dr. Time: " + (691).to_bytes(4, 'big')).digest()),
    ("SHA256('Dr. Time: ' + 691_bytes_4LE)", hashlib.sha256(b"Dr. Time: " + (691).to_bytes(4, 'little')).digest()),
    ("SHA256('Dr. Time: ' + 691_bytes_32BE)", hashlib.sha256(b"Dr. Time: " + (691).to_bytes(32, 'big')).digest()),
    ("SHA256('Dr. Time: ' + 691_bytes_32LE)", hashlib.sha256(b"Dr. Time: " + (691).to_bytes(32, 'little')).digest()),
    ("SHA256('Dr. Time: ' + bad_block + 691_4BE)", hashlib.sha256(b"Dr. Time: " + bad_block_bytes + (691).to_bytes(4, 'big')).digest()),
    ("SHA256('Dr. Time: ' + bad_block + 691_4LE)", hashlib.sha256(b"Dr. Time: " + bad_block_bytes + (691).to_bytes(4, 'little')).digest()),
    ("SHA256(bad_block + 691_4BE)", hashlib.sha256(bad_block_bytes + (691).to_bytes(4, 'big')).digest()),
    ("SHA256(bad_block + 691_4LE)", hashlib.sha256(bad_block_bytes + (691).to_bytes(4, 'little')).digest()),
    ("SHA256(691_bytes_32BE)", hashlib.sha256((691).to_bytes(32, 'big')).digest()),
    ("SHA256(691_bytes_32LE)", hashlib.sha256((691).to_bytes(32, 'little')).digest()),
    ("SHA256('691')", hashlib.sha256(b"691").digest()),
    ("SHA256('Ramanujan 691')", hashlib.sha256(b"Ramanujan 691").digest()),
    ("SHA256('tau mod 691')", hashlib.sha256(b"tau mod 691").digest()),
    ("SHA256('Dr. Time: tau(28) mod 691')", hashlib.sha256(b"Dr. Time: tau(28) mod 691").digest()),
    ("SHA256('Dr. Time: tau(28) mod 691 = {})".format(t28_mod), hashlib.sha256("Dr. Time: tau(28) mod 691 = {}".format(t28_mod).encode()).digest()),
    ("SHA256('Dr. Time: {}')".format(t28_mod), hashlib.sha256("Dr. Time: {}".format(t28_mod).encode()).digest()),
    ("SHA256('Dr. Time: sigma_11(28) mod 691 = {})".format(s11_28_mod), hashlib.sha256("Dr. Time: sigma_11(28) mod 691 = {}".format(s11_28_mod).encode()).digest()),
    ("SHA256('Dr. Time: {}')".format(s11_28_mod), hashlib.sha256("Dr. Time: {}".format(s11_28_mod).encode()).digest()),
    ("SHA256('Dr. Time: ' + s11_28_mod_bytes)", hashlib.sha256(b"Dr. Time: " + (s11_28_mod).to_bytes(4, 'big')).digest()),
    ("SHA256('Dr. Time: ' + bad_block + s11_28_mod)", hashlib.sha256(b"Dr. Time: " + bad_block_bytes + (s11_28_mod).to_bytes(4, 'big')).digest()),
]

found = False
for label, seed in candidates:
    try:
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            tmp = f.name
        key = TrifoldKey(seed, height=6, state_path=tmp)
        if key.root.hex() == CANONICAL_ROOT:
            print(f"MATCH: {label}")
            print(f"  Seed: {seed.hex()}")
            print(f"  Root: {key.root.hex()}")
            found = True
        os.unlink(tmp)
    except Exception as e:
        pass

if not found:
    print("No match found with 691.")
    print(f"Target root: {CANONICAL_ROOT}")
    print()
    print("Roots generated:")
    for label, seed in candidates:
        try:
            with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
                tmp = f.name
            key = TrifoldKey(seed, height=6, state_path=tmp)
            print(f"  {label}: {key.root.hex()[:16]}...")
            os.unlink(tmp)
        except:
            pass
