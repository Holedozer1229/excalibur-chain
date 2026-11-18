#!/usr/bin/env python3
"""
p_mod4_key_derivation.py — Build keys using primes where -p ≡ 3 (mod 4)

The condition -p ≡ 3 (mod 4) means p ≡ 1 (mod 4).
These primes have special properties:
1. They can be written as a sum of two squares: p = a² + b² (Fermat)
2. They split in the Gaussian integers Z[i]
3. (-1/p) = 1 (quadratic residue of -1)

The hypothesis: the sum-of-squares decomposition of p ≡ 1 (mod 4) primes
can generate candidate private keys for burn addresses.

Connection to prior work:
- 691 ≡ 3 (mod 4), so -691 ≡ 1 (mod 4) — NOT in our set
- But 691 is the modulus in τ(n) ≡ σ₁₁(n) mod 691
- Primes p ≡ 1 (mod 4) near 691 or related to τ(28) = 24647168 may yield keys
"""

import sys
import os
import hashlib
from typing import List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from secp256k1 import priv_to_pub, compress, N as SECP_N


# ============================================================
# PRIME UTILITIES
# ============================================================

def is_prime(n: int) -> bool:
    """Miller-Rabin primality test."""
    if n < 2:
        return False
    if n < 4:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    d = n - 1
    r = 0
    while d % 2 == 0:
        d //= 2
        r += 1
    for a in [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37]:
        if a >= n:
            break
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        for _ in range(r - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                break
        else:
            return False
    return True


def sum_of_two_squares(p: int) -> Tuple[int, int]:
    """
    Find a, b such that p = a² + b² for p ≡ 1 (mod 4).
    Uses Cornacchia's algorithm:
    1. Find r such that r² ≡ -1 (mod p)
    2. Run Euclidean algorithm on (p, r) until remainder < √p
    3. Check if the resulting pair satisfies a² + b² = p
    """
    if p == 2:
        return (1, 1)
    
    # Step 1: Find r such that r² ≡ -1 (mod p)
    # For p ≡ 1 (mod 4), -1 is a quadratic residue.
    # Find a quadratic non-residue g, then r = g^((p-1)/4) mod p
    r = None
    for g in range(2, p):
        if pow(g, (p - 1) // 2, p) == p - 1:  # g is a quadratic non-residue
            r = pow(g, (p - 1) // 4, p)
            break
    
    if r is None:
        return (0, 0)
    
    # Verify: r² ≡ -1 (mod p)
    assert (r * r) % p == p - 1, f"r² mod p = {(r*r)%p}, expected {p-1}"
    
    # Step 2: Run Euclidean algorithm on (p, r)
    # Stop when remainder first drops below √p
    limit = int(p ** 0.5)
    
    a, b = p, r
    while b > limit:
        a, b = b, a % b
    
    # Now b ≤ √p. Check if a² + b² = p
    # a is the remainder just above √p, b is the one at or below √p
    if a * a + b * b == p:
        return (max(a, b), min(a, b))
    
    # If not, try one more step of Euclidean
    c = a % b
    if b * b + c * c == p:
        return (max(b, c), min(b, c))
    
    # Fallback: brute force for small primes
    for a_try in range(1, int(p ** 0.5) + 1):
        rem = p - a_try * a_try
        b_try = int(rem ** 0.5)
        if b_try * b_try == rem:
            return (a_try, b_try)
    
    return (0, 0)


def primes_mod4_1(limit: int) -> List[int]:
    """Return all primes p ≤ limit where p ≡ 1 (mod 4)."""
    result = []
    for p in range(5, limit + 1, 4):
        if is_prime(p):
            result.append(p)
    return result


# ============================================================
# THE 7 BURN ADDRESSES
# ============================================================

BURN_ADDRESSES = [
    ("1CounterpartyXXXXXXXXXXXXXXXUWLpVr", "818895f3dc2c178629d3d2d8fa3ec4a3f8179821", "Counterparty"),
    ("1111111111111111111114oLvT2", "0000000000000000000000000000000000000000", "All-zero P2PKH"),
    ("1BitcoinEaterAddressDontSendf59kuE", "759d6677091e973b9e9d99f19c68fbf43e3f05f9", "BitcoinEater"),
    ("bc1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqthqst8", "0000000000000000000000000000000000000000000000000000000000000000", "P2WSH all-zeros"),
    ("bc1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq9e75rs", "0000000000000000000000000000000000000000", "P2WPKH all-zeros"),
    ("bc1qfffffffffffffffffffffffffffffffffffffffffffffffffffqe708k7", "4a5294a5294a5294a5294a5294a5294a5294a5294a5294a5294a5294a5294a52", "P2WSH f-pattern"),
    ("bc1qffffffffffffffffffffffffffffffff82jzwn", "4a5294a5294a5294a5294a5294a5294a5294a529", "P2WPKH f-pattern"),
]


def hash160_pubkey(pubkey_bytes: bytes) -> bytes:
    """Compute hash160 (RIPEMD160(SHA256(pubkey)))."""
    sha = hashlib.sha256(pubkey_bytes).digest()
    try:
        return hashlib.new('ripemd160', sha).digest()
    except ValueError:
        return b'\x00' * 20


# ============================================================
# KEY DERIVATION STRATEGIES
# ============================================================

def derive_candidates_from_prime(p: int, a: int, b: int, hash160_bytes: bytes) -> List[Tuple[str, int]]:
    """
    Derive candidate private keys from a p ≡ 1 (mod 4) prime and its sum-of-squares decomposition.
    """
    candidates = []
    h160_int = int.from_bytes(hash160_bytes, 'big')
    
    # Strategy 1: p itself as private key
    if 0 < p < SECP_N:
        candidates.append((f"p={p}", p))
    
    # Strategy 2: a and b from sum of squares
    if 0 < a < SECP_N:
        candidates.append((f"a={a} (from {p}={a}²+{b}²)", a))
    if 0 < b < SECP_N:
        candidates.append((f"b={b} (from {p}={a}²+{b}²)", b))
    
    # Strategy 3: a*b mod N
    ab_mod = (a * b) % SECP_N
    if 0 < ab_mod < SECP_N:
        candidates.append((f"a*b mod N ({p}={a}²+{b}²)", ab_mod))
    
    # Strategy 4: a² mod N, b² mod N
    a2_mod = (a * a) % SECP_N
    if 0 < a2_mod < SECP_N:
        candidates.append((f"a² mod N ({p})", a2_mod))
    b2_mod = (b * b) % SECP_N
    if 0 < b2_mod < SECP_N:
        candidates.append((f"b² mod N ({p})", b2_mod))
    
    # Strategy 5: Gaussian integer combinations with hash160 bytes
    for byte_val in hash160_bytes[:10]:
        if byte_val > 0:
            for combo in [a + byte_val, b + byte_val, a * byte_val, b * byte_val]:
                pk = combo % SECP_N
                if 0 < pk < SECP_N:
                    candidates.append((f"{p}={a}²+{b}² combined with byte {byte_val}", pk))
    
    # Strategy 6: p combined with τ(28) = 24647168 (tau(4)*tau(7))
    tau_28 = 24647168
    for combo in [p + tau_28, p * abs(tau_28), a + tau_28, b + tau_28]:
        pk = combo % SECP_N
        if 0 < pk < SECP_N:
            candidates.append((f"{p} combined with τ(28)", pk))
    
    # Strategy 7: p combined with 691
    for combo in [p * 691, p + 691, a * 691, b * 691]:
        pk = combo % SECP_N
        if 0 < pk < SECP_N:
            candidates.append((f"{p} combined with 691", pk))
    
    # Strategy 8: p combined with f=9 pattern (0x4A5294A529)
    f_pattern = 0x4A5294A529
    for combo in [p * f_pattern, p + f_pattern, a * f_pattern, b * f_pattern]:
        pk = combo % SECP_N
        if 0 < pk < SECP_N:
            candidates.append((f"{p} combined with f=9 pattern", pk))
    
    # Strategy 9: hash160 mod p, then use as seed
    h160_mod_p = h160_int % p
    if 0 < h160_mod_p < SECP_N:
        candidates.append((f"hash160 mod {p}", h160_mod_p))
    
    # Strategy 10: Gaussian integer norm combinations
    for i in range(min(10, len(hash160_bytes))):
        c = hash160_bytes[i]
        d = hash160_bytes[min(i+1, len(hash160_bytes)-1)]
        real = a * c - b * d
        pk = real % SECP_N
        if 0 < pk < SECP_N:
            candidates.append((f"Gaussian ({p}) × hash160[{i}]", pk))
        imag = a * d + b * c
        pk = imag % SECP_N
        if 0 < pk < SECP_N:
            candidates.append((f"Gaussian imag ({p}) × hash160[{i}]", pk))
    
    return candidates


# ============================================================
# SPECIAL PRIMES RELATED TO OUR PATTERNS
# ============================================================

def get_special_primes() -> List[int]:
    """
    Get primes p ≡ 1 (mod 4) that are related to our patterns.
    """
    special = set()
    
    # 1. Primes near 691
    for p in range(680, 710):
        if is_prime(p) and p % 4 == 1:
            special.add(p)
    
    # 2. Primes that divide σ₁₁(n) for small n
    for n in range(1, 100):
        s11 = sum(d**11 for d in range(1, n+1) if n % d == 0)
        for p in range(5, min(10000, s11), 4):
            if is_prime(p) and s11 % p == 0:
                special.add(p)
    
    # 3. Primes near 28 (perfect number)
    for p in range(20, 40):
        if is_prime(p) and p % 4 == 1:
            special.add(p)
    
    # 4. Small p ≡ 1 mod 4
    for p in [5, 13, 17, 29, 37, 41, 53, 61, 73, 89, 97, 101, 109, 113]:
        special.add(p)
    
    # 5. Primes where p-1 divides τ(28) absolute value
    tau_28_abs = 24647168
    for p in range(5, 10000, 4):
        if is_prime(p) and tau_28_abs % (p - 1) == 0:
            special.add(p)
    
    return sorted(special)


# ============================================================
# MAIN
# ============================================================

print("=" * 80)
print("  -p ≡ 3 (mod 4) — Key Derivation from p ≡ 1 (mod 4) Primes")
print("=" * 80)
print()
print("  Mathematical background:")
print("  - Primes p ≡ 1 (mod 4) can be written as a² + b² (Fermat)")
print("  - They split in Gaussian integers Z[i]")
print("  - (-1/p) = 1 (quadratic residue)")
print("  - 691 ≡ 3 (mod 4), so it's NOT in our set — it's the OTHER type")
print()

# Show 691's status
print(f"  691 mod 4 = {691 % 4}  (NOT ≡ 1, so 691 is the 'other' prime type)")
print(f"  -691 mod 4 = {(-691) % 4}  (≡ 1, so -691 fits our condition)")
print()

# List special primes
special_primes = get_special_primes()
print(f"  Special primes p ≡ 1 (mod 4): {len(special_primes)} found")
print(f"  First 20: {special_primes[:20]}")
print()

# Show sum of squares for some key primes
print("  Sum of squares decomposition:")
for p in special_primes[:20]:
    a, b = sum_of_two_squares(p)
    if a > 0 and b > 0:
        print(f"    {p} = {a}² + {b}² = {a*a} + {b*b}")
print()

# Now derive and test candidates
total_candidates = 0
total_checks = 0
matches_found = 0

for addr, hash160_hex, desc in BURN_ADDRESSES:
    print("=" * 80)
    print(f"  {desc}: {addr[:50]}...")
    print(f"  Hash160: {hash160_hex}")
    print("=" * 80)
    
    target_hash160 = bytes.fromhex(hash160_hex)
    
    all_candidates = []
    
    # Use special primes
    for p in special_primes:
        a, b = sum_of_two_squares(p)
        if a > 0 and b > 0:
            candidates = derive_candidates_from_prime(p, a, b, target_hash160)
            all_candidates.extend(candidates)
    
    # Also use all small p ≡ 1 (mod 4)
    small_primes = primes_mod4_1(1000)
    for p in small_primes:
        if p not in special_primes:
            a, b = sum_of_two_squares(p)
            if a > 0 and b > 0:
                candidates = derive_candidates_from_prime(p, a, b, target_hash160)
                all_candidates.extend(candidates)
    
    # Deduplicate
    seen = set()
    unique_candidates = []
    for name, pk in all_candidates:
        if pk not in seen:
            seen.add(pk)
            unique_candidates.append((name, pk))
    
    print(f"  Total candidates: {len(unique_candidates)}")
    total_candidates += len(unique_candidates)
    
    match_count = 0
    checked = 0
    
    for name, candidate_pk in unique_candidates:
        checked += 1
        total_checks += 1
        
        try:
            pubkey_point = priv_to_pub(candidate_pk)
            pubkey_compressed = compress(pubkey_point)
            h160 = hash160_pubkey(pubkey_compressed)
            
            if h160 == target_hash160:
                match_count += 1
                matches_found += 1
                print(f"  *** MATCH: {name} ***")
                print(f"    PK: {candidate_pk} ({candidate_pk:064x})")
                print(f"    Pub: {pubkey_compressed.hex()}")
                print(f"    H160: {h160.hex()}")
        except Exception:
            pass
    
    # Progress
    if checked % 5000 == 0:
        print(f"  Checked {checked}/{len(unique_candidates)}...")
    
    if match_count == 0:
        print(f"  No matches after {checked} checks")
    else:
        print(f"  FOUND {match_count} match(es)!")
    print()

print("=" * 80)
print("  SUMMARY")
print("=" * 80)
print(f"  Total candidates: {total_candidates}")
print(f"  Total checks: {total_checks}")
print(f"  Matches: {matches_found}")
print()

if matches_found == 0:
    print("  No private keys derived from p ≡ 1 (mod 4) primes match any burn address.")
    print("  The sum-of-squares decomposition does not derive spending keys.")
else:
    print(f"  FOUND {matches_found} match(es)!")

print()
print("=" * 80)
