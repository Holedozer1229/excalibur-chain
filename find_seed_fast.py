#!/usr/bin/env python3
"""
Fast seed finder using the corrected tau(28) = 24,647,168.

Optimized version: pre-computes the Trifold root hash without file I/O
and focuses on the most likely derivation methods.
"""

import hashlib
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import the Messerene pattern
from messerene_operator import PATTERN
PATTERN_BYTES = bytes.fromhex(PATTERN)

CANONICAL_ROOT = "7083fbebd6bfbd5f82fd40827cf36bc30da81524914011e69488b5a63e7bfe55"

# Corrected tau(28) = tau(4)*tau(7) = -1472 * -16744 = 24647168
TAU_28 = 24647168
RAMANUJAN_PRIME = 691

def sigma_11(n):
    s = 0
    for d in range(1, n+1):
        if n % d == 0:
            s += d**11
    return s

SIGMA_11_28 = sigma_11(28)
TAU_28_MOD_691 = TAU_28 % RAMANUJAN_PRIME

print(f"tau(28) = {TAU_28}")
print(f"tau(28) mod 691 = {TAU_28_MOD_691}")
print(f"sigma_11(28) mod 691 = {SIGMA_11_28 % RAMANUJAN_PRIME}")
print(f"Congruence holds: {TAU_28_MOD_691 == SIGMA_11_28 % RAMANUJAN_PRIME}")
print(f"Target root: {CANONICAL_ROOT}")
print()

# ============================================================
# FAST TRIFOLD ROOT COMPUTATION (no file I/O)
# ============================================================

H = hashlib.sha256

def _h(b):
    return H(b).digest()

def _rotate(b, k):
    k %= len(b)
    return b[k:] + b[:k]

def _leaf_seed(seed, idx):
    return _h(b"TRIFOLD/LEAF" + seed + _rotate(PATTERN_BYTES, idx)
              + idx.to_bytes(4, "big"))

def _secret(seed, idx, pos, side):
    return _h(b"TRIFOLD/SEC" + _leaf_seed(seed, idx)
              + pos.to_bytes(2, "big") + bytes([side]))

def _leaf_pubhash(seed, idx):
    out = bytearray()
    for pos in range(256):
        for s in (0, 1):
            out += _h(_secret(seed, idx, pos, s))
    return _h(bytes(out))

def compute_trifold_root(seed, height=6):
    """Compute the Trifold root without file I/O."""
    capacity = 3 ** height
    level = [_leaf_pubhash(seed, i) for i in range(capacity)]
    while len(level) > 1:
        level = [_h(level[j] + level[j + 1] + level[j + 2])
                 for j in range(0, len(level), 3)]
    return level[0]

# ============================================================
# CANDIDATE GENERATION
# ============================================================

candidates = []

def add(label, seed):
    if len(seed) == 32:
        candidates.append((label, seed))

# 1. MESSERENE OPERATOR - all domains
domains = [
    b"MESSERENE/PREGENESIS/v1",
    b"MESSERENE/TAU28/v1", b"MESSERENE/TAU28/v2",
    b"MESSERENE/DR_TIME/v1", b"MESSERENE/DR_TIME/v2",
    b"MESSERENE/DRTIME/v1",
    b"MESSERENE/SEED/v1", b"MESSERENE/SEED/v2",
    b"MESSERENE/CANONICAL/v1", b"MESSERENE/CANONICAL/v2",
    b"MESSERENE/691/v1", b"MESSERENE/691/v2",
    b"MESSERENE/TAU28_691/v1", b"MESSERENE/TAU28_691/v2",
    b"MESSERENE/RETROCAUSAL/v1", b"MESSERENE/RETROCAUSAL/v2",
    b"MESSERENE/OVERFLOW/v1", b"MESSERENE/BAD_BLOCK/v1",
    b"MESSERENE/GENESIS/v1", b"MESSERENE/NULL_SPACE/v1",
    b"MESSERENE/LAMBDA/v1", b"MESSERENE/PHASE/v1",
    b"MESSERENE/TAU/v1", b"MESSERENE/Tau(28)/v1",
    b"MESSERENE/DR_TIME_OVERFLOW/v1",
    b"MESSERENE/BAD_BLOCK_74638/v1",
    b"MESSERENE/RETROCAUSAL_SEED/v1",
    b"MESSERENE/GENESIS_SEED/v1",
    b"MESSERENE/CANONICAL_ROOT/v1",
]

for domain in domains:
    # Pure pattern
    add(f"M({domain.decode()}||P)", _h(domain + PATTERN_BYTES))
    
    # Pattern + tau(28) bytes (4 and 8 byte, both endiannesses)
    for length in [4, 8]:
        for endian in ['big', 'little']:
            tb = TAU_28.to_bytes(length, endian)
            pb = RAMANUJAN_PRIME.to_bytes(length, endian)
            
            add(f"M({domain.decode()}||P||T4)", _h(domain + PATTERN_BYTES + tb))
            add(f"M({domain.decode()}||T4||P)", _h(domain + tb + PATTERN_BYTES))
            add(f"M({domain.decode()}||P||691)", _h(domain + PATTERN_BYTES + pb))
            add(f"M({domain.decode()}||691||P)", _h(domain + pb + PATTERN_BYTES))
            add(f"M({domain.decode()}||P||T||691)", _h(domain + PATTERN_BYTES + tb + pb))
            add(f"M({domain.decode()}||P||691||T)", _h(domain + PATTERN_BYTES + pb + tb))

# 2. Direct SHA-256 of tau(28) and 691 strings
all_strings = [
    str(TAU_28), "24647168", "tau(28)", "tau28", "tau_28", "TAU28", "TAU_28",
    f"tau(28)={TAU_28}", f"tau28={TAU_28}",
    str(RAMANUJAN_PRIME), "691",
    f"{TAU_28}:{RAMANUJAN_PRIME}", f"{RAMANUJAN_PRIME}:{TAU_28}",
    f"24647168:691", f"691:24647168",
    f"tau(28)={TAU_28} mod {RAMANUJAN_PRIME}",
    f"tau(28) mod 691 = {TAU_28_MOD_691}",
    f"{TAU_28} mod 691 = {TAU_28_MOD_691}",
    "24647168,691", "691,24647168",
    f"sigma_11(28) mod 691 = {SIGMA_11_28 % RAMANUJAN_PRIME}",
]

prefixes = [
    b"", b"Dr. Time: ", b"DR. TIME: ", b"Dr.Time: ", b"dr_time: ",
    b"overflow: ", b"SEED: ", b"KEY: ", b"RETROCAUSAL: ",
    b"GENESIS: ", b"CANONICAL: ", b"TAU28: ", b"691: ",
    b"RAMANUJAN: ", b"MESSERENE: ", b"TRIFOLD: ",
]

for prefix in prefixes:
    for s in all_strings:
        add(f"S('{prefix.decode()}{s}')", _h(prefix + s.encode()))

# 3. Byte-level combinations
for length in [4, 8]:
    for endian in ['big', 'little']:
        tb = TAU_28.to_bytes(length, endian)
        pb = RAMANUJAN_PRIME.to_bytes(length, endian)
        mb = TAU_28_MOD_691.to_bytes(length, endian)
        
        add(f"S(T||P)", _h(tb + pb))
        add(f"S(P||T)", _h(pb + tb))
        add(f"S(T||M)", _h(tb + mb))
        add(f"S(M||T)", _h(mb + tb))
        add(f"S(P||M)", _h(pb + mb))
        add(f"S(M||P)", _h(mb + pb))
        
        # With pattern
        add(f"S(PAT||T||P)", _h(PATTERN_BYTES + tb + pb))
        add(f"S(PAT||P||T)", _h(PATTERN_BYTES + pb + tb))
        add(f"S(T||PAT||P)", _h(tb + PATTERN_BYTES + pb))
        add(f"S(P||PAT||T)", _h(pb + PATTERN_BYTES + tb))

# 4. Double SHA-256
def dsha(data):
    return _h(_h(data))

for prefix in prefixes:
    for s in all_strings:
        add(f"D('{prefix.decode()}{s}')", dsha(prefix + s.encode()))

for length in [4, 8]:
    for endian in ['big', 'little']:
        tb = TAU_28.to_bytes(length, endian)
        pb = RAMANUJAN_PRIME.to_bytes(length, endian)
        add(f"D(T||P)", dsha(tb + pb))
        add(f"D(P||T)", dsha(pb + tb))

# 5. tau(28) * 691, tau(28) + 691, tau(28) ^ 691
product = TAU_28 * RAMANUJAN_PRIME
sum_val = TAU_28 + RAMANUJAN_PRIME
xor_val = TAU_28 ^ RAMANUJAN_PRIME

for val, label in [(product, "T*P"), (sum_val, "T+P"), (xor_val, "T^P")]:
    for length in [4, 8, 16]:
        for endian in ['big', 'little']:
            try:
                b = val.to_bytes(length, endian)
                add(f"S({label})", _h(b))
                add(f"S(PAT||{label})", _h(PATTERN_BYTES + b))
            except:
                pass

# 6. tau(28) mod 691 = 580
for length in [4, 8]:
    for endian in ['big', 'little']:
        b = TAU_28_MOD_691.to_bytes(length, endian)
        add(f"S(M{length})", _h(b))

# 7. sigma_11(28)
for length in [8, 16]:
    for endian in ['big', 'little']:
        try:
            b = SIGMA_11_28.to_bytes(length, endian)
            add(f"S(S11{length})", _h(b))
        except:
            pass

# 8. Retrocausal constants
PHASE_CONSTANT = 0.33333333326
for s in [str(PHASE_CONSTANT), "0.33333333326", "1/3", "1,1,1,1,0,-1,-1,-1,-1", "1,-2,1"]:
    for prefix in [b"", b"Dr. Time: ", b"RETROCAUSAL: ", b"SEED: "]:
        add(f"S('{prefix.decode()}{s}')", _h(prefix + s.encode()))

# 9. Genesis nonce + tau(28)
GENESIS_NONCE = 2083236893
GENESIS_TIMESTAMP = 1231006505

for g_val, g_label in [(GENESIS_NONCE, "GN"), (GENESIS_TIMESTAMP, "GT")]:
    for length in [4, 8]:
        for endian in ['big', 'little']:
            gb = g_val.to_bytes(length, endian)
            tb = TAU_28.to_bytes(length, endian)
            pb = RAMANUJAN_PRIME.to_bytes(length, endian)
            add(f"S({g_label}||T)", _h(gb + tb))
            add(f"S(T||{g_label})", _h(tb + gb))
            add(f"S({g_label}||P)", _h(gb + pb))
            add(f"S(P||{g_label})", _h(pb + gb))

# 10. Bad block hash + tau(28)
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

for extra, elabel in [(bad_block_bytes, "BB"), (header_bytes, "H")]:
    for length in [4, 8]:
        for endian in ['big', 'little']:
            tb = TAU_28.to_bytes(length, endian)
            add(f"S({elabel}||T)", _h(extra + tb))
            add(f"S(T||{elabel})", _h(tb + extra))

# 11. Pattern rotation
for idx in [TAU_28 % 32, TAU_28 % 256, TAU_28_MOD_691, RAMANUJAN_PRIME % 32]:
    rotated = PATTERN_BYTES[idx:] + PATTERN_BYTES[:idx]
    add(f"S(PAT_R{idx})", _h(rotated))
    for prefix in prefixes[:5]:
        add(f"S('{prefix.decode()}+PAT_R{idx}')", _h(prefix + rotated))

# 12. tau(28) as Trifold leaf seed
for length in [4, 8]:
    for endian in ['big', 'little']:
        tb = TAU_28.to_bytes(length, endian)
        for idx in range(32):
            rotated = PATTERN_BYTES[idx:] + PATTERN_BYTES[:idx]
            leaf = _h(b"TRIFOLD/LEAF" + tb + rotated + idx.to_bytes(4, "big"))
            add(f"TL(T,{idx})", leaf)

# 13. The exact string "24647168"
for s in ["24647168", "24,647,168", "24647168 691", "24647168:691", "691:24647168"]:
    add(f"S('{s}')", _h(s.encode()))
    for prefix in prefixes[:5]:
        add(f"S('{prefix.decode()}{s}')", _h(prefix + s.encode()))

# 14. tau(28) in different bases
for base_str in [f"{TAU_28:b}", f"{TAU_28:o}", f"{TAU_28:x}", f"0x{TAU_28:x}"]:
    add(f"S('{base_str}')", _h(base_str.encode()))

# 15. tau(28) padded to 32 bytes
for length in [4, 8]:
    for endian in ['big', 'little']:
        tb = TAU_28.to_bytes(length, endian)
        add(f"T_pad_{length}", tb.ljust(32, b'\x00'))
        add(f"T_pre_{length}", b'\x00' * (32 - length) + tb)

# 16. 691 padded to 32 bytes
for length in [4, 8]:
    for endian in ['big', 'little']:
        pb = RAMANUJAN_PRIME.to_bytes(length, endian)
        add(f"P_pad_{length}", pb.ljust(32, b'\x00'))
        add(f"P_pre_{length}", b'\x00' * (32 - length) + pb)

# 17. Bad block hash as seed
add("BB_HASH", bad_block_bytes)
add("HEADER_32", header_bytes[:32])

# 18. Overflow tx
OVERFLOW_TX = "1d5e512a9723cbef373b970eb52f1e9598ad67e7408077a82fdac194b65333c9"
add("OVERFLOW_TX", bytes.fromhex(OVERFLOW_TX))

# 19. Messerene k value as seed (from messerene_operator.py)
N_SECP = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
for domain in domains[:10]:
    digest = _h(domain + PATTERN_BYTES)
    k = (int.from_bytes(digest, "big") % (N_SECP - 1)) + 1
    add(f"M_k({domain.decode()})", k.to_bytes(32, 'big'))

# 20. tau(28) as Messerene k
for domain in domains[:10]:
    tb = TAU_28.to_bytes(4, 'big')
    digest = _h(domain + tb + PATTERN_BYTES)
    k = (int.from_bytes(digest, "big") % (N_SECP - 1)) + 1
    add(f"M_kT({domain.decode()})", k.to_bytes(32, 'big'))

# ============================================================
# SEARCH
# ============================================================

# Remove duplicates
seen = set()
unique_candidates = []
for label, seed in candidates:
    if seed not in seen:
        seen.add(seed)
        unique_candidates.append((label, seed))

candidates = unique_candidates
print(f"Testing {len(candidates)} unique candidates...")
print()

found = False
tested = 0

for label, seed in candidates:
    tested += 1
    if tested % 100 == 0:
        print(f"  Tested {tested}/{len(candidates)}...")
    
    try:
        root = compute_trifold_root(seed, height=6)
        if root.hex() == CANONICAL_ROOT:
            print(f"\n{'='*70}")
            print(f"MATCH FOUND!")
            print(f"{'='*70}")
            print(f"  Label: {label}")
            print(f"  Seed:  {seed.hex()}")
            print(f"  Root:  {root.hex()}")
            print(f"{'='*70}")
            found = True
            break
    except:
        pass

if not found:
    print(f"\nNo match found in {tested} candidates.")
    print(f"Target root: {CANONICAL_ROOT}")
    print()
    print("The seed may require a derivation method not yet explored.")
    print(f"Known ingredients: tau(28)={TAU_28}, 691, Messerene pattern,")
    print(f"Genesis nonce, bad block hash, retrocausal phase constant.")
