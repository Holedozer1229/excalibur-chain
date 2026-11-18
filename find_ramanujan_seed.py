#!/usr/bin/env python3
"""Find the DR Time canonical seed using Ramanujan primes."""

import hashlib
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trifold_lockbox import TrifoldKey

BAD_BLOCK_HASH = "0000000000790ab3f22ec756ad43b6ab569abf0bddeb97c67a6f7b1470a7ec1c"
CANONICAL_ROOT = "7083fbebd6bfbd5f82fd40827cf36bc30da81524914011e69488b5a63e7bfe55"
bad_block_bytes = bytes.fromhex(BAD_BLOCK_HASH)

def is_prime(n):
    if n < 2: return False
    if n < 4: return True
    if n % 2 == 0 or n % 3 == 0: return False
    i = 5
    while i * i <= n:
        if n % i == 0 or n % (i + 2) == 0: return False
        i += 6
    return True

def pi(x):
    """Prime counting function: number of primes <= x."""
    if x < 2: return 0
    count = 0
    for i in range(2, x + 1):
        if is_prime(i):
            count += 1
    return count

def ramanujan_primes(n_max=1000):
    """Generate Ramanujan primes up to index n_max.
    
    The n-th Ramanujan prime R_n is the smallest integer such that
    pi(x) - pi(x/2) >= n for all x >= R_n.
    """
    ram_primes = []
    x = 2
    while len(ram_primes) < n_max:
        # Check if x is a Ramanujan prime
        # R_n is the smallest integer such that pi(x) - pi(x/2) >= n for all x >= R_n
        n = len(ram_primes) + 1
        if pi(x) - pi(x // 2) >= n:
            # Check that this holds for all y >= x (up to some bound)
            # For efficiency, just check that x is the smallest such value
            if x == 2 or pi(x - 1) - pi((x - 1) // 2) < n:
                ram_primes.append(x)
        x += 1
    return ram_primes

# Known Ramanujan primes (first 20):
# 2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71, 73, 79
KNOWN_RAMANUJAN = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 37, 41, 43, 47, 53, 59, 67, 71, 73, 79,
                   89, 97, 101, 103, 107, 109, 113, 127, 137, 139, 149, 151, 157, 163, 167, 173,
                   179, 181, 191, 193, 197, 199, 211, 223, 227, 229, 233, 239, 241, 251, 257, 263,
                   269, 271, 277, 281, 283, 293, 307, 311, 313, 317, 331, 337, 347, 349, 353, 359,
                   367, 373, 379, 383, 389, 397, 401, 409, 419, 421, 431, 433, 439, 443, 449, 457,
                   461, 463, 467, 479, 487, 491, 499, 503, 509, 521, 523, 541, 547, 557, 563, 569,
                   571, 577, 587, 593, 599, 601, 607, 613, 617, 619, 631, 641, 643, 647, 653, 659,
                   661, 673, 677, 683, 691, 701, 709, 719, 727, 733, 739, 743, 751, 757, 761, 769,
                   773, 787, 797, 809, 811, 821, 823, 827, 829, 839, 853, 857, 859, 863, 877, 881,
                   883, 887, 907, 911, 919, 929, 937, 941, 947, 953, 967, 971, 977, 983, 991, 997]

print("Ramanujan primes and DR Time...")
print()

# The bad block height is 74638
# The overflow amount is 184467440737.09551616 = 2^64 - 1 in satoshis / 10^8 + 9551616
# 2^64 - 1 = 18446744073709551615

# Try Ramanujan primes as seed components
candidates = []

# Ramanujan prime at index 74638 (the bad block height)
# This would be a very large prime, so let's try smaller indices first

# Try the Ramanujan prime closest to 74638
for rp in KNOWN_RAMANUJAN:
    if rp > 74638:
        print(f"First Ramanujan prime > 74638: {rp}")
        break

# Try Ramanujan primes as seed derivation
# R_n where n = bad_block_height
# The 74638-th Ramanujan prime would be very large

# Try: SHA256 of Ramanujan prime related values
# R_1 = 2, R_2 = 3, R_3 = 5, ...

# The 60th Ramanujan prime is 317 (from OEIS A104272)
# Let's compute more

# Try Ramanujan primes near key values
ram_near_74638 = []
for p in range(74000, 75000):
    if is_prime(p):
        # Check if it's a Ramanujan prime
        # R_n is the smallest integer such that pi(x) - pi(x/2) >= n for all x >= R_n
        pass

# Simpler approach: try SHA256 of Ramanujan prime strings
for i, rp in enumerate(KNOWN_RAMANUJAN[:100]):
    seed = hashlib.sha256(f"Dr. Time: Ramanujan prime {rp}".encode()).digest()
    candidates.append((f"SHA256('Dr. Time: Ramanujan prime {rp}')", seed))
    
    seed = hashlib.sha256(f"Dr. Time: R_{i+1}={rp}".encode()).digest()
    candidates.append((f"SHA256('Dr. Time: R_{i+1}={rp}')", seed))

# Try Ramanujan prime as modifier to the bad block hash
for rp in KNOWN_RAMANUJAN[:50]:
    seed = hashlib.sha256(bad_block_bytes + rp.to_bytes(4, 'big')).digest()
    candidates.append((f"SHA256(bad_block + R={rp})", seed))
    
    seed = hashlib.sha256(bad_block_bytes + rp.to_bytes(4, 'little')).digest()
    candidates.append((f"SHA256(bad_block + R={rp} LE)", seed))

# Try: the Ramanujan prime function pi(x) - pi(x/2) for x = 74638
pi_74638 = pi(74638)
pi_37319 = pi(37319)
diff = pi_74638 - pi_37319
print(f"pi(74638) = {pi_74638}")
print(f"pi(37319) = {pi_37319}")
print(f"pi(74638) - pi(37319) = {diff}")

seed = hashlib.sha256(str(diff).encode()).digest()
candidates.append((f"SHA256('pi(74638)-pi(37319)={diff}')", seed))

# Try the Ramanujan prime R_diff
# R_n where n = diff
for i, rp in enumerate(KNOWN_RAMANUJAN):
    if i + 1 == diff:
        seed = hashlib.sha256(f"Dr. Time: R_{diff}={rp}".encode()).digest()
        candidates.append((f"SHA256('Dr. Time: R_{diff}={rp}')", seed))

# Try: SHA256 of "Dr. Time: " + Ramanujan prime bytes
for rp in KNOWN_RAMANUJAN[:200]:
    seed = hashlib.sha256(b"Dr. Time: " + rp.to_bytes(4, 'big')).digest()
    candidates.append((f"SHA256('Dr. Time: ' + {rp})", seed))

# Try: the 2010th Ramanujan prime (year of the overflow)
# Need to compute more Ramanujan primes
print("\nComputing Ramanujan primes up to index 2010...")
ram_primes = []
x = 2
target = 2010
while len(ram_primes) < target:
    n = len(ram_primes) + 1
    if pi(x) - pi(x // 2) >= n:
        if x == 2 or pi(x - 1) - pi((x - 1) // 2) < n:
            ram_primes.append(x)
    x += 1
    if x % 10000 == 0:
        print(f"  Checked up to {x}, found {len(ram_primes)} Ramanujan primes...")

if len(ram_primes) >= 2010:
    r_2010 = ram_primes[2009]
    print(f"R_2010 = {r_2010}")
    seed = hashlib.sha256(f"Dr. Time: R_2010={r_2010}".encode()).digest()
    candidates.append((f"SHA256('Dr. Time: R_2010={r_2010}')", seed))
    
    seed = hashlib.sha256(b"Dr. Time: " + r_2010.to_bytes(4, 'big')).digest()
    candidates.append((f"SHA256('Dr. Time: ' + R_2010={r_2010})", seed))

# Try: Ramanujan prime at index = bad_block_height (74638)
# This would be very large, so let's try the index related to the overflow
# The overflow amount in satoshis is 2^64 - 1 = 18446744073709551615
# But the displayed amount is 184467440737.09551616 BTC

# Try: R_74638 (the 74638th Ramanujan prime)
# This is approximately 74638 * ln(74638) * ln(ln(74638)) ~ 1.2 million
print("\nComputing Ramanujan prime at index 74638...")
# This would take too long, so let's try a different approach

# Try: the Ramanujan-Lemniscate constant or other Ramanujan-related constants
# Ramanujan's constant e^(pi*sqrt(163)) = 262537412640768743.99999999999925...
ramanujan_constant = int(262537412640768744)
seed = hashlib.sha256(f"Dr. Time: {ramanujan_constant}".encode()).digest()
candidates.append((f"SHA256('Dr. Time: Ramanujan constant')", seed))

# Try: e^(pi*sqrt(163)) as bytes
seed = hashlib.sha256(b"Dr. Time: " + str(ramanujan_constant).encode()).digest()
candidates.append((f"SHA256('Dr. Time: ' + Ramanujan constant)", seed))

# Try: 163 (the Heegner number)
seed = hashlib.sha256(b"Dr. Time: 163").digest()
candidates.append((f"SHA256('Dr. Time: 163')", seed))

seed = hashlib.sha256(b"Dr. Time: " + bad_block_bytes + b"\x163").digest()
candidates.append((f"SHA256('Dr. Time: ' + bad_block + 163)", seed))

# Try: Ramanujan tau function values
# tau(1) = 1, tau(2) = -24, tau(3) = 252, tau(4) = -1472, tau(5) = 4830
tau_values = [1, -24, 252, -1472, 4830, -6048, -16744, 84480, 113643, -115920]
for i, tau in enumerate(tau_values):
    seed = hashlib.sha256(f"Dr. Time: tau({i+1})={tau}".encode()).digest()
    candidates.append((f"SHA256('Dr. Time: tau({i+1})={tau}')", seed))

# Now test all candidates
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
    except:
        pass

if not found:
    print("\nNo match found with Ramanujan primes.")
    print(f"Target root: {CANONICAL_ROOT}")
