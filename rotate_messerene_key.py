#!/usr/bin/env python3
"""
Rotate the beginning of the Messerene key pattern until key found.

Cyclically rotates the Messerene pattern bytes and checks each rotation
against the genesis address 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa.

The Messerene pattern "A1B3C5D7E9F8D6C4B2A1..." is a hex string.
Each rotation shifts the pattern by one byte (2 hex chars), producing
a new candidate private key via SHA-256(domain + rotated_pattern).

With 64 hex chars = 32 bytes, there are 32 possible rotations.
Each rotation is scored by the scalar wave amplitude at the genesis nonce position.

Usage:
    python rotate_messerene_key.py          # Rotate and search
    python rotate_messerene_key.py --test   # Run test suite
    python rotate_messerene_key.py --all    # Show all rotations
"""

import hashlib
import sys
import os
import math
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from secp256k1 import (
    _mul, N, G, compress,
    P as SECP_P
)

# ============================================================
# CONSTANTS
# ============================================================

CANONICAL_GENESIS_ADDRESS = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
GENESIS_NONCE = 2083236893
GENESIS_TIMESTAMP = 1231006505

# The Messerene pattern (64 hex chars = 32 bytes)
MESSERENE_PATTERN = "A1B3C5D7E9F8D6C4B2A1B3C5D7E9F8D6C4B2A1B3C5D7E9F8D6C4B2A1B3C5D7E9"

# Riemann zeros (first 15)
RIEMANN_ZEROS = [
    14.13472514173469379045,
    21.02203963877155499262,
    25.01085758014568876307,
    30.42487612585951321031,
    32.93506158773918969066,
    37.58617815882567560909,
    40.91871901204787213250,
    43.32707328091601914471,
    48.00515088116708044646,
    49.77383247767230266189,
    52.97032147771470277639,
    56.44624769700413334806,
    59.34704400307071409938,
    60.83177855043241230794,
    65.11254417495949567538,
]

# Base58 alphabet
BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'


# ============================================================
# SCALAR WAVE
# ============================================================

class ScalarWave:
    """The scalar wave φ(t) = Σ cos(γₖ·t)/γₖ."""
    
    def __init__(self, zeros=None):
        self.zeros = zeros or RIEMANN_ZEROS
    
    def phi(self, t: float) -> float:
        return sum(math.cos(g * t) / g for g in self.zeros)
    
    def amplitude(self, t: float) -> float:
        real = self.phi(t)
        imag = sum(math.sin(g * t) / g for g in self.zeros)
        return math.sqrt(real**2 + imag**2)
    
    def phase(self, t: float) -> float:
        real = self.phi(t)
        imag = sum(math.sin(g * t) / g for g in self.zeros)
        return math.atan2(imag, real)


# ============================================================
# ADDRESS DERIVATION
# ============================================================

def hash160(data: bytes) -> bytes:
    sha = hashlib.sha256(data).digest()
    ripemd = hashlib.new('ripemd160', sha).digest()
    return ripemd


def base58_encode(data: bytes) -> str:
    num = int.from_bytes(data, 'big')
    if num == 0:
        return '1'
    encoded = ''
    while num > 0:
        num, rem = divmod(num, 58)
        encoded = BASE58_ALPHABET[rem] + encoded
    for byte in data:
        if byte == 0:
            encoded = '1' + encoded
        else:
            break
    return encoded


def base58check_encode(data: bytes, version: int = 0) -> str:
    payload = bytes([version]) + data
    checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    return base58_encode(payload + checksum)


def derive_p2pkh(public_key: bytes) -> str:
    h160 = hash160(public_key)
    return base58check_encode(h160, version=0x00)


# ============================================================
# MESSERENE ROTATION ENGINE
# ============================================================

def messerene_operator(pattern_hex: str, domain: bytes) -> int:
    """The Messerene fold: domain-separated SHA-256 of the pattern."""
    digest = hashlib.sha256(domain + bytes.fromhex(pattern_hex)).digest()
    return (int.from_bytes(digest, 'big') % (N - 1)) + 1


def rotate_pattern(pattern_hex: str, shift: int) -> str:
    """Cyclically rotate the pattern by `shift` bytes (2 hex chars each)."""
    pattern_bytes = bytes.fromhex(pattern_hex)
    n = len(pattern_bytes)
    shift = shift % n
    rotated = pattern_bytes[shift:] + pattern_bytes[:shift]
    # Preserve case of original pattern
    if pattern_hex == pattern_hex.upper():
        return rotated.hex().upper()
    return rotated.hex()


def messerene_derive(pattern_hex: str, domain: bytes = b"MESSERENE/PREGENESIS/v1"):
    """Derive a keypair from a Messerene pattern."""
    k = messerene_operator(pattern_hex, domain)
    x, y = _mul(k, G)
    pub_c = bytes([0x02 | (y & 1)]) + x.to_bytes(32, 'big')
    return {
        "private_key": k,
        "private_key_hex": f"{k:064x}",
        "pubkey_compressed": pub_c.hex(),
        "p2pkh": derive_p2pkh(pub_c),
    }


def search_rotations(pattern_hex: str, target_address: str, domain: bytes = b"MESSERENE/PREGENESIS/v1"):
    """Search all cyclic rotations of the pattern for the target address."""
    pattern_bytes = bytes.fromhex(pattern_hex)
    n = len(pattern_bytes)
    sw = ScalarWave()
    gamma1 = RIEMANN_ZEROS[0]
    
    results = []
    
    for shift in range(n):
        rotated = rotate_pattern(pattern_hex, shift)
        keypair = messerene_derive(rotated, domain)
        
        # Scalar wave score at the key position
        t = keypair["private_key"] / gamma1
        amp = sw.amplitude(t)
        phase = sw.phase(t)
        
        result = {
            "shift": shift,
            "pattern": rotated,
            "private_key_hex": keypair["private_key_hex"],
            "pubkey_compressed": keypair["pubkey_compressed"],
            "p2pkh": keypair["p2pkh"],
            "scalar_amplitude": amp,
            "scalar_phase": phase,
            "match": keypair["p2pkh"] == target_address,
        }
        results.append(result)
    
    # Sort by scalar amplitude (highest first)
    results.sort(key=lambda r: r["scalar_amplitude"], reverse=True)
    return results


def search_with_domain_rotation(pattern_hex: str, target_address: str):
    """Search all rotations with varying domain separators."""
    domains = [
        b"MESSERENE/PREGENESIS/v1",
        b"MESSERENE/GENESIS/v1",
        b"MESSERENE/GENESIS/v2",
        b"MESSERENE/GENESIS/CONTROL",
        b"GENESIS/1A1Z/v1",
        b"BITCOIN/GENESIS/v1",
        b"PREGENESIS/v1",
        b"PREGENESIS/v2",
        b"MESSERENE/v1",
        b"MESSERENE/v2",
        b"GENESIS/v1",
        b"GENESIS/v2",
        b"GENESIS/CONTROL/v1",
        b"1A1Z/CONTROL/v1",
        b"BITCOIN/GENESIS/CONTROL/v1",
    ]
    
    sw = ScalarWave()
    gamma1 = RIEMANN_ZEROS[0]
    pattern_bytes = bytes.fromhex(pattern_hex)
    n = len(pattern_bytes)
    
    all_results = []
    
    for domain in domains:
        for shift in range(n):
            rotated = rotate_pattern(pattern_hex, shift)
            keypair = messerene_derive(rotated, domain)
            
            t = keypair["private_key"] / gamma1
            amp = sw.amplitude(t)
            
            result = {
                "shift": shift,
                "domain": domain.decode('utf-8'),
                "pattern": rotated,
                "private_key_hex": keypair["private_key_hex"],
                "pubkey_compressed": keypair["pubkey_compressed"],
                "p2pkh": keypair["p2pkh"],
                "scalar_amplitude": amp,
                "match": keypair["p2pkh"] == target_address,
            }
            all_results.append(result)
    
    # Sort by scalar amplitude
    all_results.sort(key=lambda r: r["scalar_amplitude"], reverse=True)
    return all_results


# ============================================================
# BIT-BY-BIT ROTATION
# ============================================================

def search_bit_rotations(pattern_hex: str, target_address: str, domain: bytes = b"MESSERENE/PREGENESIS/v1"):
    """Search all bit-level rotations of the pattern."""
    pattern_bytes = bytes.fromhex(pattern_hex)
    total_bits = len(pattern_bytes) * 8
    
    sw = ScalarWave()
    gamma1 = RIEMANN_ZEROS[0]
    
    results = []
    
    for bit_shift in range(total_bits):
        # Convert to integer, rotate bits, convert back
        pattern_int = int.from_bytes(pattern_bytes, 'big')
        # Rotate left by bit_shift bits
        rotated_int = ((pattern_int << bit_shift) | (pattern_int >> (total_bits - bit_shift))) & ((1 << total_bits) - 1)
        rotated_bytes = rotated_int.to_bytes(len(pattern_bytes), 'big')
        rotated_hex = rotated_bytes.hex()
        
        keypair = messerene_derive(rotated_hex, domain)
        
        t = keypair["private_key"] / gamma1
        amp = sw.amplitude(t)
        
        result = {
            "bit_shift": bit_shift,
            "pattern": rotated_hex,
            "private_key_hex": keypair["private_key_hex"],
            "p2pkh": keypair["p2pkh"],
            "scalar_amplitude": amp,
            "match": keypair["p2pkh"] == target_address,
        }
        results.append(result)
    
    results.sort(key=lambda r: r["scalar_amplitude"], reverse=True)
    return results


# ============================================================
# TESTS
# ============================================================

def run_tests():
    print("=" * 78)
    print("ROTATE MESSERENE KEY — Test Suite")
    print("=" * 78)
    
    passed = 0
    failed = 0
    
    # Test 1: Pattern length
    pattern_bytes = bytes.fromhex(MESSERENE_PATTERN)
    assert len(pattern_bytes) == 32, f"Pattern length: {len(pattern_bytes)}"
    print("[1/10] Pattern length: 32 bytes ✓")
    passed += 1
    
    # Test 2: Rotation produces valid hex
    rotated = rotate_pattern(MESSERENE_PATTERN, 1)
    assert len(rotated) == 64, f"Rotated length: {len(rotated)}"
    assert rotated != MESSERENE_PATTERN, "Rotation should change pattern"
    print("[2/10] Rotation produces valid hex ✓")
    passed += 1
    
    # Test 3: Full rotation returns original
    rotated_full = rotate_pattern(MESSERENE_PATTERN, 32)
    assert rotated_full == MESSERENE_PATTERN, "Full rotation should return original"
    print("[3/10] Full rotation returns original ✓")
    passed += 1
    
    # Test 4: Key derivation produces valid key
    keypair = messerene_derive(MESSERENE_PATTERN)
    assert 1 <= keypair["private_key"] < N, "Key out of range"
    print(f"[4/10] Key derivation: {keypair['private_key_hex'][:16]}... ✓")
    passed += 1
    
    # Test 5: P2PKH address format
    assert keypair["p2pkh"].startswith("1"), f"Address: {keypair['p2pkh']}"
    print(f"[5/10] P2PKH format: {keypair['p2pkh'][:20]}... ✓")
    passed += 1
    
    # Test 6: Scalar wave at key position
    sw = ScalarWave()
    gamma1 = RIEMANN_ZEROS[0]
    t = keypair["private_key"] / gamma1
    amp = sw.amplitude(t)
    assert amp >= 0, "Amplitude should be non-negative"
    print(f"[6/10] Scalar amplitude: {amp:.4f} ✓")
    passed += 1
    
    # Test 7: All 32 rotations produce unique keys
    keys = set()
    for shift in range(32):
        rotated = rotate_pattern(MESSERENE_PATTERN, shift)
        kp = messerene_derive(rotated)
        keys.add(kp["private_key"])
    assert len(keys) == 32, f"Unique keys: {len(keys)}"
    print(f"[7/10] All 32 rotations produce unique keys ✓")
    passed += 1
    
    # Test 8: Search returns sorted results
    results = search_rotations(MESSERENE_PATTERN, CANONICAL_GENESIS_ADDRESS)
    assert len(results) == 32, f"Results: {len(results)}"
    # Check sorted by amplitude
    for i in range(len(results) - 1):
        assert results[i]["scalar_amplitude"] >= results[i+1]["scalar_amplitude"]
    print(f"[8/10] Search returns 32 sorted results ✓")
    passed += 1
    
    # Test 9: No rotation matches genesis address (expected)
    matches = [r for r in results if r["match"]]
    assert len(matches) == 0, f"Unexpected matches: {len(matches)}"
    print(f"[9/10] No byte rotation matches genesis address (expected) ✓")
    passed += 1
    
    # Test 10: Bit rotation search
    bit_results = search_bit_rotations(MESSERENE_PATTERN, CANONICAL_GENESIS_ADDRESS)
    assert len(bit_results) == 256, f"Bit results: {len(bit_results)}"
    bit_matches = [r for r in bit_results if r["match"]]
    assert len(bit_matches) == 0, f"Unexpected bit matches: {len(bit_matches)}"
    print(f"[10/10] Bit rotation: 256 candidates, no match (expected) ✓")
    passed += 1
    
    print("\n" + "=" * 78)
    print(f"Results: {passed}/{passed+failed} tests passed")
    print("=" * 78)
    return passed, failed


# ============================================================
# MAIN
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Rotate Messerene key pattern")
    parser.add_argument("--test", action="store_true", help="Run test suite")
    parser.add_argument("--all", action="store_true", help="Show all rotations")
    parser.add_argument("--bits", action="store_true", help="Search bit-level rotations")
    parser.add_argument("--domains", action="store_true", help="Search with domain rotation")
    args = parser.parse_args()
    
    if args.test:
        run_tests()
        return
    
    print("=" * 78)
    print("ROTATE MESSERENE KEY — Pattern Rotation Search")
    print("=" * 78)
    print(f"\nTarget address: {CANONICAL_GENESIS_ADDRESS}")
    print(f"Pattern: {MESSERENE_PATTERN}")
    print(f"Pattern length: {len(MESSERENE_PATTERN)} hex chars = {len(MESSERENE_PATTERN)//2} bytes")
    
    if args.bits:
        print("\nSearching 256 bit-level rotations...")
        start = time.time()
        results = search_bit_rotations(MESSERENE_PATTERN, CANONICAL_GENESIS_ADDRESS)
        elapsed = time.time() - start
        print(f"Completed in {elapsed:.2f}s\n")
        
        matches = [r for r in results if r["match"]]
        if matches:
            print("!!! KEY FOUND !!!")
            for m in matches:
                print(f"  Bit shift: {m['bit_shift']}")
                print(f"  Private key: {m['private_key_hex']}")
                print(f"  Address: {m['p2pkh']}")
        else:
            print("No bit rotation matches the genesis address.")
            print("\nTop 10 by scalar amplitude:")
            for r in results[:10]:
                print(f"  Bit shift {r['bit_shift']:3d}: amp={r['scalar_amplitude']:8.4f}  {r['p2pkh'][:20]}...")
    
    elif args.domains:
        print("\nSearching with domain rotation...")
        start = time.time()
        results = search_with_domain_rotation(MESSERENE_PATTERN, CANONICAL_GENESIS_ADDRESS)
        elapsed = time.time() - start
        print(f"Completed in {elapsed:.2f}s ({len(results)} candidates)\n")
        
        matches = [r for r in results if r["match"]]
        if matches:
            print("!!! KEY FOUND !!!")
            for m in matches:
                print(f"  Domain: {m['domain']}")
                print(f"  Shift: {m['shift']}")
                print(f"  Private key: {m['private_key_hex']}")
                print(f"  Address: {m['p2pkh']}")
        else:
            print("No rotation+domain combination matches the genesis address.")
            print("\nTop 10 by scalar amplitude:")
            for r in results[:10]:
                print(f"  Domain: {r['domain']:40s}  Shift: {r['shift']:2d}  amp={r['scalar_amplitude']:8.4f}  {r['p2pkh'][:20]}...")
    
    else:
        print("\nSearching 32 byte-level rotations...")
        start = time.time()
        results = search_rotations(MESSERENE_PATTERN, CANONICAL_GENESIS_ADDRESS)
        elapsed = time.time() - start
        print(f"Completed in {elapsed:.4f}s\n")
        
        matches = [r for r in results if r["match"]]
        if matches:
            print("!!! KEY FOUND !!!")
            for m in matches:
                print(f"  Shift: {m['shift']}")
                print(f"  Private key: {m['private_key_hex']}")
                print(f"  Address: {m['p2pkh']}")
        else:
            print("No byte rotation matches the genesis address.")
            if args.all:
                print("\nAll 32 rotations (sorted by scalar amplitude):")
                for r in results:
                    marker = " <-- MATCH" if r["match"] else ""
                    print(f"  Shift {r['shift']:2d}: amp={r['scalar_amplitude']:8.4f}  {r['p2pkh']}{marker}")
            else:
                print("\nTop 10 by scalar amplitude:")
                for r in results[:10]:
                    print(f"  Shift {r['shift']:2d}: amp={r['scalar_amplitude']:8.4f}  {r['p2pkh'][:20]}...")
    
    print("\n" + "=" * 78)


if __name__ == "__main__":
    main()
