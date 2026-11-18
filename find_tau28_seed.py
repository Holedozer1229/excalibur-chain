#!/usr/bin/env python3
"""Compute tau(28) and try it as the DR Time seed."""

import hashlib
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trifold_lockbox import TrifoldKey

BAD_BLOCK_HASH = "0000000000790ab3f22ec756ad43b6ab569abf0bddeb97c67a6f7b1470a7ec1c"
CANONICAL_ROOT = "7083fbebd6bfbd5f82fd40827cf36bc30da81524914011e69488b5a63e7bfe55"
bad_block_bytes = bytes.fromhex(BAD_BLOCK_HASH)

def sigma_11(n):
    """Sum of 11th powers of divisors of n."""
    if n == 0:
        return 0
    s = 0
    for d in range(1, n+1):
        if n % d == 0:
            s += d**11
    return s

def compute_tau(n):
    """Ramanujan tau function - use known values from OEIS A000594."""
    # Known values from OEIS A000594
    known_tau = {
        1: 1, 2: -24, 3: 252, 4: -1472, 5: 4830, 6: -6048, 7: -16744,
        8: 84480, 9: -113643, 10: -115920, 11: -301728, 12: 5741760,
        13: -3367680, 14: -9033696, 15: 78543072, 16: -221280576,
        17: -157530720, 18: 231528288, 19: 594643584, 20: -681276000,
        21: -994195008, 22: 1957555200, 23: -4264645248, 24: 1378273920,
        25: 1365457664, 26: 1207857360, 27: -1114077568,
        # tau(28) = tau(4)*tau(7) = -1472 * -16744 = 24647168 (multiplicative, gcd(4,7)=1)
        28: 24647168
    }
    if n in known_tau:
        return known_tau[n]
    # Fallback: compute via recurrence (not needed for n=28)
    return None

# tau(28) = tau(4)*tau(7) = -1472 * -16744 = 24647168 (multiplicative property, gcd(4,7)=1)
# The Ramanujan congruence tau(n) = sigma_11(n) mod 691 holds for ALL n, including n=28
t28 = 24647168
print(f"tau(28) = {t28} (computed from tau(4)*tau(7))")
print(f"|tau(28)| = {abs(t28)}")
print(f"hex: 0x{abs(t28):x}")

# Try tau(28) as seed
candidates = [
    ("SHA256('Dr. Time: tau(28)')", hashlib.sha256(b"Dr. Time: tau(28)").digest()),
    ("SHA256('Dr. Time: tau(28)=24647168')", hashlib.sha256(b"Dr. Time: tau(28)=24647168").digest()),
    ("SHA256('Dr. Time: 24647168')", hashlib.sha256(b"Dr. Time: 24647168").digest()),
    # Also try the old wrong value in case the seed was derived from it
    ("SHA256('Dr. Time: tau(28)=-703236000')", hashlib.sha256(b"Dr. Time: tau(28)=-703236000").digest()),
    ("SHA256('Dr. Time: -703236000')", hashlib.sha256(b"Dr. Time: -703236000").digest()),
    ("SHA256('Dr. Time: 703236000')", hashlib.sha256(b"Dr. Time: 703236000").digest()),
    ("SHA256('Dr. Time: ' + tau28_bytes_4BE)", hashlib.sha256(b"Dr. Time: " + abs(t28).to_bytes(4, 'big')).digest()),
    ("SHA256('Dr. Time: ' + tau28_bytes_4LE)", hashlib.sha256(b"Dr. Time: " + abs(t28).to_bytes(4, 'little')).digest()),
    ("SHA256('Dr. Time: ' + tau28_bytes_8BE)", hashlib.sha256(b"Dr. Time: " + abs(t28).to_bytes(8, 'big')).digest()),
    ("SHA256('Dr. Time: ' + tau28_bytes_8LE)", hashlib.sha256(b"Dr. Time: " + abs(t28).to_bytes(8, 'little')).digest()),
    ("SHA256('Dr. Time: ' + tau28_bytes_32BE)", hashlib.sha256(b"Dr. Time: " + abs(t28).to_bytes(32, 'big')).digest()),
    ("SHA256('Dr. Time: ' + tau28_bytes_32LE)", hashlib.sha256(b"Dr. Time: " + abs(t28).to_bytes(32, 'little')).digest()),
    ("SHA256('Dr. Time: ' + bad_block + tau28_4BE)", hashlib.sha256(b"Dr. Time: " + bad_block_bytes + abs(t28).to_bytes(4, 'big')).digest()),
    ("SHA256('Dr. Time: ' + bad_block + tau28_4LE)", hashlib.sha256(b"Dr. Time: " + bad_block_bytes + abs(t28).to_bytes(4, 'little')).digest()),
    ("SHA256(tau28_bytes_32BE)", hashlib.sha256(abs(t28).to_bytes(32, 'big')).digest()),
    ("SHA256(tau28_bytes_32LE)", hashlib.sha256(abs(t28).to_bytes(32, 'little')).digest()),
    ("SHA256(tau28_str)", hashlib.sha256(str(t28).encode()).digest()),
    ("SHA256(|tau28|_str)", hashlib.sha256(str(abs(t28)).encode()).digest()),
    ("SHA256('tau(28)')", hashlib.sha256(b"tau(28)").digest()),
    ("SHA256('tau28')", hashlib.sha256(b"tau28").digest()),
    ("SHA256('Dr. Time: tau28')", hashlib.sha256(b"Dr. Time: tau28").digest()),
    ("SHA256('Dr. Time: Ramanujan tau(28)')", hashlib.sha256(b"Dr. Time: Ramanujan tau(28)").digest()),
    ("SHA256('Dr. Time: Ramanujan tau 28')", hashlib.sha256(b"Dr. Time: Ramanujan tau 28").digest()),
    ("SHA256('Dr. Time: tau_28')", hashlib.sha256(b"Dr. Time: tau_28").digest()),
    ("SHA256('Dr. Time: tau_28=24647168')", hashlib.sha256(b"Dr. Time: tau_28=24647168").digest()),
    ("SHA256('Dr. Time: tau(28)=24647168')", hashlib.sha256(b"Dr. Time: tau(28)=24647168").digest()),
    ("SHA256('Dr. Time: |tau(28)|=24647168')", hashlib.sha256(b"Dr. Time: |tau(28)|=24647168").digest()),
    # Also try the old wrong value in case the seed was derived from it
    ("SHA256('Dr. Time: tau_28=-703236000')", hashlib.sha256(b"Dr. Time: tau_28=-703236000").digest()),
    ("SHA256('Dr. Time: tau(28)=-703236000')", hashlib.sha256(b"Dr. Time: tau(28)=-703236000").digest()),
    ("SHA256('Dr. Time: tau(28)=703236000')", hashlib.sha256(b"Dr. Time: tau(28)=703236000").digest()),
    ("SHA256('Dr. Time: |tau(28)|=703236000')", hashlib.sha256(b"Dr. Time: |tau(28)|=703236000").digest()),
    # Try with the actual tau(28) signed value as 4 bytes
    ("SHA256('Dr. Time: ' + tau28_signed_4)", hashlib.sha256(b"Dr. Time: " + t28.to_bytes(4, 'big', signed=True)).digest()),
    ("SHA256('Dr. Time: ' + tau28_signed_4LE)", hashlib.sha256(b"Dr. Time: " + t28.to_bytes(4, 'little', signed=True)).digest()),
    # Try bad_block + tau(28) variations
    ("SHA256(bad_block + tau28_4BE)", hashlib.sha256(bad_block_bytes + abs(t28).to_bytes(4, 'big')).digest()),
    ("SHA256(bad_block + tau28_4LE)", hashlib.sha256(bad_block_bytes + abs(t28).to_bytes(4, 'little')).digest()),
    ("SHA256(bad_block + tau28_signed_4)", hashlib.sha256(bad_block_bytes + t28.to_bytes(4, 'big', signed=True)).digest()),
]

found = False
for label, seed in candidates:
    try:
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            tmp = f.name
        key = TrifoldKey(seed, height=6, state_path=tmp)
        if key.root.hex() == CANONICAL_ROOT:
            print(f"\nMATCH: {label}")
            print(f"  Seed: {seed.hex()}")
            print(f"  Root: {key.root.hex()}")
            found = True
        os.unlink(tmp)
    except Exception as e:
        pass

if not found:
    print("\nNo match found with tau(28).")
    print(f"Target root: {CANONICAL_ROOT}")
    
    # Print all roots for debugging
    print("\nRoots generated:")
    for label, seed in candidates:
        try:
            with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
                tmp = f.name
            key = TrifoldKey(seed, height=6, state_path=tmp)
            print(f"  {label}: {key.root.hex()[:16]}...")
            os.unlink(tmp)
        except:
            pass
