#!/usr/bin/env python3
"""
Exhaustive seed finder using the corrected tau(28) = 24,647,168.

The rebuild script says: "The seed for the canonical Trifold key is derived
from tau(28) and the Ramanujan prime 691, hidden in the sphinx_os nexus."

This script tries every conceivable combination of these two numbers to find
the 32-byte seed that produces root 7083fbeb... at height 6.
"""

import hashlib
import sys
import os
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trifold_lockbox import TrifoldKey

CANONICAL_ROOT = "7083fbebd6bfbd5f82fd40827cf36bc30da81524914011e69488b5a63e7bfe55"

# Corrected tau(28) = tau(4)*tau(7) = -1472 * -16744 = 24647168
TAU_28 = 24647168
RAMANUJAN_PRIME = 691

# The Messerene pattern
PATTERN = "A1B3C5D7E9F8D6C4B2A1B3C5D7E9F8D6C4B2A1B3C5D7E9F8D6C4B2A1B3C5D7E9"
PATTERN_BYTES = bytes.fromhex(PATTERN)

# sigma_11(28)
def sigma_11(n):
    s = 0
    for d in range(1, n+1):
        if n % d == 0:
            s += d**11
    return s

SIGMA_11_28 = sigma_11(28)
TAU_28_MOD_691 = TAU_28 % RAMANUJAN_PRIME  # Should equal SIGMA_11_28 % 691 = 580

print(f"tau(28) = {TAU_28}")
print(f"tau(28) mod 691 = {TAU_28_MOD_691}")
print(f"sigma_11(28) mod 691 = {SIGMA_11_28 % RAMANUJAN_PRIME}")
print(f"Congruence holds: {TAU_28_MOD_691 == SIGMA_11_28 % RAMANUJAN_PRIME}")
print(f"Target root: {CANONICAL_ROOT}")
print()

candidates = []

def add_candidate(label, seed):
    if len(seed) == 32:
        candidates.append((label, seed))

# ============================================================
# 1. MESSERENE OPERATOR STYLE (from messerene_operator.py)
# ============================================================
# The Messerene operator: k = (SHA256(domain || P_bytes) mod (n-1)) + 1
# But for Trifold, we need the raw 32-byte seed, not the modular reduction

# All possible Messerene domains with tau(28) and 691
domains = [
    b"MESSERENE/PREGENESIS/v1",
    b"MESSERENE/TAU28/v1",
    b"MESSERENE/TAU28/v2",
    b"MESSERENE/DR_TIME/v1",
    b"MESSERENE/DR_TIME/v2",
    b"MESSERENE/DRTIME/v1",
    b"MESSERENE/SEED/v1",
    b"MESSERENE/SEED/v2",
    b"MESSERENE/CANONICAL/v1",
    b"MESSERENE/CANONICAL/v2",
    b"MESSERENE/691/v1",
    b"MESSERENE/691/v2",
    b"MESSERENE/TAU28_691/v1",
    b"MESSERENE/TAU28_691/v2",
    b"MESSERENE/RETROCAUSAL/v1",
    b"MESSERENE/RETROCAUSAL/v2",
    b"MESSERENE/OVERFLOW/v1",
    b"MESSERENE/BAD_BLOCK/v1",
    b"MESSERENE/GENESIS/v1",
    b"MESSERENE/NULL_SPACE/v1",
    b"MESSERENE/LAMBDA/v1",
    b"MESSERENE/PHASE/v1",
    b"MESSERENE/TAU/v1",
    b"MESSERENE/Tau(28)/v1",
    b"MESSERENE/TAU28_OVERFLOW/v1",
    b"MESSERENE/DR_TIME_OVERFLOW/v1",
    b"MESSERENE/BAD_BLOCK_74638/v1",
    b"MESSERENE/RETROCAUSAL_SEED/v1",
    b"MESSERENE/GENESIS_SEED/v1",
    b"MESSERENE/CANONICAL_ROOT/v1",
]

for domain in domains:
    # Pure pattern
    seed = hashlib.sha256(domain + PATTERN_BYTES).digest()
    add_candidate(f"MESSERENE({domain.decode()} || pattern)", seed)
    
    # Pattern + tau(28) bytes
    for length in [4, 8]:
        for endian in ['big', 'little']:
            tau_bytes = TAU_28.to_bytes(length, endian)
            seed = hashlib.sha256(domain + PATTERN_BYTES + tau_bytes).digest()
            add_candidate(f"MESSERENE({domain.decode()} || pattern || tau28_{length}{endian[0].upper()})", seed)
            
            seed = hashlib.sha256(domain + tau_bytes + PATTERN_BYTES).digest()
            add_candidate(f"MESSERENE({domain.decode()} || tau28_{length}{endian[0].upper()} || pattern)", seed)
    
    # Pattern + 691 bytes
    for length in [4, 8]:
        for endian in ['big', 'little']:
            p_bytes = RAMANUJAN_PRIME.to_bytes(length, endian)
            seed = hashlib.sha256(domain + PATTERN_BYTES + p_bytes).digest()
            add_candidate(f"MESSERENE({domain.decode()} || pattern || 691_{length}{endian[0].upper()})", seed)
            
            seed = hashlib.sha256(domain + p_bytes + PATTERN_BYTES).digest()
            add_candidate(f"MESSERENE({domain.decode()} || 691_{length}{endian[0].upper()} || pattern)", seed)
    
    # Pattern + tau(28) + 691
    for length in [4, 8]:
        for endian in ['big', 'little']:
            tau_bytes = TAU_28.to_bytes(length, endian)
            p_bytes = RAMANUJAN_PRIME.to_bytes(length, endian)
            seed = hashlib.sha256(domain + PATTERN_BYTES + tau_bytes + p_bytes).digest()
            add_candidate(f"MESSERENE({domain.decode()} || pattern || tau28 || 691)", seed)
            
            seed = hashlib.sha256(domain + PATTERN_BYTES + p_bytes + tau_bytes).digest()
            add_candidate(f"MESSERENE({domain.decode()} || pattern || 691 || tau28)", seed)

# ============================================================
# 2. DIRECT SHA-256 OF TAU(28) AND 691
# ============================================================

# All string representations
tau_strings = [
    str(TAU_28),
    str(abs(TAU_28)),
    f"tau(28)={TAU_28}",
    f"tau28={TAU_28}",
    f"tau(28)={abs(TAU_28)}",
    f"TAU28={TAU_28}",
    f"TAU_28={TAU_28}",
    f"24647168",
    f"tau(28)",
    f"tau28",
    f"tau_28",
    f"TAU28",
    f"TAU_28",
    f"Ramanujan tau(28)",
    f"Ramanujan tau 28",
    f"tau(28)={TAU_28} mod {RAMANUJAN_PRIME}",
    f"tau28={TAU_28} mod 691",
    f"tau(28) mod 691 = {TAU_28_MOD_691}",
    f"sigma_11(28) mod 691 = {SIGMA_11_28 % RAMANUJAN_PRIME}",
    f"{TAU_28} mod 691 = {TAU_28_MOD_691}",
]

prime_strings = [
    str(RAMANUJAN_PRIME),
    "691",
    "Ramanujan prime",
    "RamanujanPrime",
    "RAMANUJAN_PRIME",
    f"prime={RAMANUJAN_PRIME}",
]

# Combined strings
combined_strings = [
    f"{TAU_28}:{RAMANUJAN_PRIME}",
    f"{abs(TAU_28)}:{RAMANUJAN_PRIME}",
    f"{RAMANUJAN_PRIME}:{TAU_28}",
    f"{RAMANUJAN_PRIME}:{abs(TAU_28)}",
    f"tau(28)=691",
    f"tau28=691",
    f"691:tau(28)",
    f"691:tau28",
    f"tau(28) and 691",
    f"tau28 and 691",
    f"24647168 and 691",
    f"24647168:691",
    f"691:24647168",
    f"tau(28)=24647168,691",
    f"tau(28)=24647168,691",
    f"24647168,691",
    f"691,24647168",
]

all_strings = tau_strings + prime_strings + combined_strings

# All prefixes
prefixes = [
    b"",
    b"Dr. Time: ",
    b"DR. TIME: ",
    b"Dr.Time: ",
    b"dr_time: ",
    b"overflow: ",
    b"SEED: ",
    b"KEY: ",
    b"RETROCAUSAL: ",
    b"GENESIS: ",
    b"CANONICAL: ",
    b"TAU28: ",
    b"691: ",
    b"RAMANUJAN: ",
    b"MESSERENE: ",
    b"TRIFOLD: ",
    b"EXCAL: ",
    b"BTC: ",
    b"BAD_BLOCK: ",
]

for prefix in prefixes:
    for s in all_strings:
        seed = hashlib.sha256(prefix + s.encode()).digest()
        add_candidate(f"SHA256('{prefix.decode()}{s}')", seed)

# ============================================================
# 3. BYTE-LEVEL COMBINATIONS
# ============================================================

# tau(28) as bytes in various formats
tau_byte_formats = []
for length in [4, 8, 16, 32]:
    for endian in ['big', 'little']:
        try:
            b = TAU_28.to_bytes(length, endian)
            tau_byte_formats.append((b, f"tau28_{length}{endian[0].upper()}"))
        except:
            pass

# 691 as bytes
prime_byte_formats = []
for length in [4, 8, 16, 32]:
    for endian in ['big', 'little']:
        try:
            b = RAMANUJAN_PRIME.to_bytes(length, endian)
            prime_byte_formats.append((b, f"691_{length}{endian[0].upper()}"))
        except:
            pass

# tau(28) mod 691 = 580 as bytes
mod_byte_formats = []
for length in [4, 8, 16, 32]:
    for endian in ['big', 'little']:
        try:
            b = TAU_28_MOD_691.to_bytes(length, endian)
            mod_byte_formats.append((b, f"tau28_mod691_{length}{endian[0].upper()}"))
        except:
            pass

# All byte combinations
for tb, tl in tau_byte_formats:
    for pb, pl in prime_byte_formats:
        # tau || prime
        seed = hashlib.sha256(tb + pb).digest()
        add_candidate(f"SHA256({tl} || {pl})", seed)
        
        # prime || tau
        seed = hashlib.sha256(pb + tb).digest()
        add_candidate(f"SHA256({pl} || {tl})", seed)

for tb, tl in tau_byte_formats:
    for mb, ml in mod_byte_formats:
        seed = hashlib.sha256(tb + mb).digest()
        add_candidate(f"SHA256({tl} || {ml})", seed)
        
        seed = hashlib.sha256(mb + tb).digest()
        add_candidate(f"SHA256({ml} || {tl})", seed)

# ============================================================
# 4. MESSERENE PATTERN + TAU(28) + 691
# ============================================================

for tb, tl in tau_byte_formats:
    for pb, pl in prime_byte_formats:
        # pattern || tau || prime
        seed = hashlib.sha256(PATTERN_BYTES + tb + pb).digest()
        add_candidate(f"SHA256(pattern || {tl} || {pl})", seed)
        
        # pattern || prime || tau
        seed = hashlib.sha256(PATTERN_BYTES + pb + tb).digest()
        add_candidate(f"SHA256(pattern || {pl} || {tl})", seed)
        
        # tau || pattern || prime
        seed = hashlib.sha256(tb + PATTERN_BYTES + pb).digest()
        add_candidate(f"SHA256({tl} || pattern || {pl})", seed)
        
        # prime || pattern || tau
        seed = hashlib.sha256(pb + PATTERN_BYTES + tb).digest()
        add_candidate(f"SHA256({pl} || pattern || {tl})", seed)

# ============================================================
# 5. DOUBLE SHA-256 (Bitcoin-style)
# ============================================================

def double_sha256(data):
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

for prefix in prefixes:
    for s in all_strings:
        seed = double_sha256(prefix + s.encode())
        add_candidate(f"DSHA256('{prefix.decode()}{s}')", seed)

for tb, tl in tau_byte_formats:
    for pb, pl in prime_byte_formats:
        seed = double_sha256(tb + pb)
        add_candidate(f"DSHA256({tl} || {pl})", seed)
        
        seed = double_sha256(pb + tb)
        add_candidate(f"DSHA256({pl} || {tl})", seed)

# ============================================================
# 6. TAU(28) AS SEED DIRECTLY (padded to 32 bytes)
# ============================================================

for length in [4, 8]:
    for endian in ['big', 'little']:
        try:
            b = TAU_28.to_bytes(length, endian)
            seed = b.ljust(32, b'\x00')  # Zero-pad to 32 bytes
            add_candidate(f"tau28_{length}{endian[0].upper()}_padded", seed)
            
            seed = b'\x00' * (32 - length) + b  # Prepend zeros
            add_candidate(f"tau28_{length}{endian[0].upper()}_prepended", seed)
        except:
            pass

# ============================================================
# 7. 691 AS SEED DIRECTLY (padded to 32 bytes)
# ============================================================

for length in [4, 8]:
    for endian in ['big', 'little']:
        try:
            b = RAMANUJAN_PRIME.to_bytes(length, endian)
            seed = b.ljust(32, b'\x00')
            add_candidate(f"691_{length}{endian[0].upper()}_padded", seed)
            
            seed = b'\x00' * (32 - length) + b
            add_candidate(f"691_{length}{endian[0].upper()}_prepended", seed)
        except:
            pass

# ============================================================
# 8. TAU(28) * 691 AND TAU(28) + 691
# ============================================================

product = TAU_28 * RAMANUJAN_PRIME
sum_val = TAU_28 + RAMANUJAN_PRIME
xor_val = TAU_28 ^ RAMANUJAN_PRIME

for val, label in [(product, "tau28*691"), (sum_val, "tau28+691"), (xor_val, "tau28^691")]:
    for length in [4, 8, 16, 32]:
        for endian in ['big', 'little']:
            try:
                b = val.to_bytes(length, endian)
                seed = hashlib.sha256(b).digest()
                add_candidate(f"SHA256({label}_{length}{endian[0].upper()})", seed)
                
                seed = hashlib.sha256(PATTERN_BYTES + b).digest()
                add_candidate(f"SHA256(pattern || {label}_{length}{endian[0].upper()})", seed)
            except:
                pass

# ============================================================
# 9. TAU(28) MOD 691 = 580 AS THE KEY
# ============================================================

for length in [4, 8, 32]:
    for endian in ['big', 'little']:
        try:
            b = TAU_28_MOD_691.to_bytes(length, endian)
            seed = hashlib.sha256(b).digest()
            add_candidate(f"SHA256(tau28_mod691_{length}{endian[0].upper()})", seed)
        except:
            pass

# ============================================================
# 10. SIGMA_11(28) AS SEED
# ============================================================

for length in [8, 16, 32]:
    for endian in ['big', 'little']:
        try:
            b = SIGMA_11_28.to_bytes(length, endian)
            seed = hashlib.sha256(b).digest()
            add_candidate(f"SHA256(sigma11_28_{length}{endian[0].upper()})", seed)
        except:
            pass

# ============================================================
# 11. THE NUMBER 24647168 AS HEX
# ============================================================

hex_tau = f"{TAU_28:x}"  # "1770d00"
hex_prime = f"{RAMANUJAN_PRIME:x}"  # "2b3"

for h in [hex_tau, hex_prime, f"{hex_tau}{hex_prime}", f"{hex_prime}{hex_tau}"]:
    try:
        b = bytes.fromhex(h)
        seed = hashlib.sha256(b).digest()
        add_candidate(f"SHA256(hex({h}))", seed)
        
        seed = hashlib.sha256(PATTERN_BYTES + b).digest()
        add_candidate(f"SHA256(pattern || hex({h}))", seed)
    except:
        pass

# ============================================================
# 12. RETROCAUSAL CONSTANTS
# ============================================================

PHASE_CONSTANT = 0.33333333326
LAMBDA_STR = "1,1,1,1,0,-1,-1,-1,-1"
NULL_STR = "1,-2,1"

for s in [str(PHASE_CONSTANT), "0.33333333326", "1/3", LAMBDA_STR, NULL_STR]:
    for prefix in [b"", b"Dr. Time: ", b"RETROCAUSAL: ", b"SEED: "]:
        seed = hashlib.sha256(prefix + s.encode()).digest()
        add_candidate(f"SHA256('{prefix.decode()}{s}')", seed)

# ============================================================
# 13. GENESIS NONCE + TAU(28) + 691
# ============================================================

GENESIS_NONCE = 2083236893
GENESIS_TIMESTAMP = 1231006505

for g_val, g_label in [(GENESIS_NONCE, "genesis_nonce"), (GENESIS_TIMESTAMP, "genesis_ts")]:
    for length in [4, 8]:
        for endian in ['big', 'little']:
            try:
                g_bytes = g_val.to_bytes(length, endian)
                for tb, tl in tau_byte_formats[:4]:  # Just 4-byte formats
                    seed = hashlib.sha256(g_bytes + tb).digest()
                    add_candidate(f"SHA256({g_label} || {tl})", seed)
                    
                    seed = hashlib.sha256(tb + g_bytes).digest()
                    add_candidate(f"SHA256({tl} || {g_label})", seed)
            except:
                pass

# ============================================================
# 14. BAD BLOCK + TAU(28) + 691
# ============================================================

BAD_BLOCK_HASH = "0000000000790ab3f22ec756ad43b6ab569abf0bddeb97c67a6f7b1470a7ec1c"
bad_block_bytes = bytes.fromhex(BAD_BLOCK_HASH)

HEADER_HEX = (
    "01000000"
    "846e2b968653ef0a25a92c12e8884d76919907df8e3079e66568600000000000"
    "5eecb6808d6de56a05211483d86fc6c7d17cda46c3388dd0c8139e4114ba8e61"
    "751e684c0e80001c"
    "cf2fae01"
)
header_bytes = bytes.fromhex(HEADER_HEX)

for extra, elabel in [(bad_block_bytes, "bad_block"), (header_bytes, "header")]:
    for tb, tl in tau_byte_formats[:4]:
        seed = hashlib.sha256(extra + tb).digest()
        add_candidate(f"SHA256({elabel} || {tl})", seed)
        
        seed = hashlib.sha256(tb + extra).digest()
        add_candidate(f"SHA256({tl} || {elabel})", seed)

# ============================================================
# 15. TAU(28) WITH MESSERENE PATTERN ROTATION (from trifold_lockbox.py)
# ============================================================

# The trifold uses: _rotate(P_BYTES, idx) for leaf seeds
# Try tau(28) as the index
for idx in [TAU_28 % 32, TAU_28 % 256, TAU_28_MOD_691, RAMANUJAN_PRIME % 32]:
    rotated = PATTERN_BYTES[idx:] + PATTERN_BYTES[:idx]
    seed = hashlib.sha256(rotated).digest()
    add_candidate(f"SHA256(pattern_rotated_{idx})", seed)
    
    for prefix in prefixes[:5]:
        seed = hashlib.sha256(prefix + rotated).digest()
        add_candidate(f"SHA256('{prefix.decode()}' + pattern_rotated_{idx})", seed)

# ============================================================
# 16. TAU(28) AS TRIFOLD LEAF SEED
# ============================================================

# The trifold leaf seed is: SHA256("TRIFOLD/LEAF" + seed + rotate(P_BYTES, idx) + idx.to_bytes(4, "big"))
# Try tau(28) as the seed component
for tb, tl in tau_byte_formats[:4]:
    for idx in range(32):
        rotated = PATTERN_BYTES[idx:] + PATTERN_BYTES[:idx]
        leaf = hashlib.sha256(b"TRIFOLD/LEAF" + tb + rotated + idx.to_bytes(4, "big")).digest()
        add_candidate(f"TRIFOLD_LEAF({tl}, idx={idx})", leaf)

# ============================================================
# 17. THE EXACT STRING "24647168"
# ============================================================

for s in ["24647168", "24,647,168", "24647168 691", "24647168:691", "691:24647168"]:
    seed = hashlib.sha256(s.encode()).digest()
    add_candidate(f"SHA256('{s}')", seed)
    
    for prefix in prefixes[:5]:
        seed = hashlib.sha256(prefix + s.encode()).digest()
        add_candidate(f"SHA256('{prefix.decode()}{s}')", seed)

# ============================================================
# 18. TAU(28) IN DIFFERENT BASES
# ============================================================

for base_str in [
    f"{TAU_28:b}",  # binary
    f"{TAU_28:o}",  # octal
    f"{TAU_28:x}",  # hex
    f"0x{TAU_28:x}",
    f"0b{TAU_28:b}",
    f"0o{TAU_28:o}",
]:
    seed = hashlib.sha256(base_str.encode()).digest()
    add_candidate(f"SHA256('{base_str}')", seed)

# ============================================================
# SEARCH
# ============================================================

print(f"Testing {len(candidates)} candidates against root {CANONICAL_ROOT[:16]}...")
print()

found = False
tested = 0
tmp = None

for label, seed in candidates:
    tested += 1
    if tested % 10000 == 0:
        print(f"  Tested {tested}/{len(candidates)}...")
    
    try:
        if len(seed) != 32:
            continue
        
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            tmp = f.name
        
        key = TrifoldKey(seed, height=6, state_path=tmp)
        if key.root.hex() == CANONICAL_ROOT:
            print(f"\n{'='*70}")
            print(f"MATCH FOUND!")
            print(f"{'='*70}")
            print(f"  Label: {label}")
            print(f"  Seed:  {seed.hex()}")
            print(f"  Root:  {key.root.hex()}")
            print(f"{'='*70}")
            found = True
            break
        
        os.unlink(tmp)
        tmp = None
    except Exception as e:
        if tmp and os.path.exists(tmp):
            os.unlink(tmp)
            tmp = None
        pass

if not found:
    print(f"\nNo match found in {tested} candidates.")
    print(f"Target root: {CANONICAL_ROOT}")
    print()
    print("The seed may require a derivation method not yet explored.")
    print(f"Known ingredients: tau(28)={TAU_28}, 691, Messerene pattern,")
    print(f"Genesis nonce, bad block hash, retrocausal phase constant.")
