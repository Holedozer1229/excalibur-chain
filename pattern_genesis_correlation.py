#!/usr/bin/env python3
"""
Explore the relationship between the Messerene pattern and Bitcoin's genesis block.

Bitcoin genesis block key facts:
- Hash: 000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f
- Nonce: 2083236893
- Timestamp: 1231006505 (Sat Jan 03 2009 19:15:05 UTC)
- Merkle root: 4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b
- Coinbase: "The Times 03/Jan/2009 Chancellor on brink of second bailout for banks"
- Bits (difficulty): 486604799 (0x1d00ffff)
- Version: 1

Messerene pattern: A1B3C5D7E9F8D6C4B2A0E8F6D4C2B0A8E6F4D2C0B8A6E4D2C0B8A6E4D2C0
"""

import hashlib
import struct

# ============================================================
# Bitcoin Genesis Block Constants
# ============================================================

GENESIS_HASH = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
GENESIS_NONCE = 2083236893
GENESIS_TIMESTAMP = 1231006505
GENESIS_MERKLE = "4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b"
GENESIS_BITS = 486604799  # 0x1d00ffff
GENESIS_COINBASE_MSG = "The Times 03/Jan/2009 Chancellor on brink of second bailout for banks"
GENESIS_VERSION = 1

# The original Messerene pattern from messerene_operator.py
ORIGINAL_PATTERN = "A1B3C5D7E9F8D6C4B2A0E8F6D4C2B0A8E6F4D2C0B8A6E4D2C0B8A6E4D2C0"

def sha256d(data: bytes) -> bytes:
    """Double SHA-256 hash."""
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def pattern_to_bytes(pattern: str) -> bytes:
    """Convert hex pattern string to bytes."""
    return bytes.fromhex(pattern)

def derive_address(privkey_bytes: bytes) -> str:
    """Derive bc1 (P2WPKH) address from 32-byte private key."""
    from secp256k1 import G, N, multiply, compress
    priv = int.from_bytes(privkey_bytes, 'big') % N
    if priv == 0:
        return "invalid (zero private key)"
    pub = compress(multiply(priv, G))
    # P2WPKH: sha256(ripemd160(pub))
    import hashlib
    ripemd = hashlib.new('ripemd160', hashlib.sha256(pub).digest()).digest()
    witness = bytes([0]) + ripemd  # version 0 + hash
    # Bech32 encoding (simplified)
    # For brevity, just return the x-only pubkey hash
    return ripemd.hex()

def check_correlation(name: str, value, target_name: str, target_value):
    """Check if a derived value correlates with a genesis block value."""
    if isinstance(value, int) and isinstance(target_value, int):
        ratio = value / target_value if target_value != 0 else float('inf')
        diff = abs(value - target_value)
        print(f"  {name} vs {target_name}:")
        print(f"    Derived: {value}")
        print(f"    Target:  {target_value}")
        print(f"    Ratio:   {ratio:.6f}")
        print(f"    Diff:    {diff}")
        if ratio > 0.99 and ratio < 1.01:
            print(f"    *** CLOSE MATCH ({ratio:.4f}) ***")
        return ratio
    elif isinstance(value, str) and isinstance(target_value, str):
        if value == target_value:
            print(f"  *** EXACT MATCH: {name} == {target_name} ***")
            return 1.0
        # Check prefix match
        common = 0
        for a, b in zip(value, target_value):
            if a == b:
                common += 1
            else:
                break
        print(f"  {name} vs {target_name}:")
        print(f"    Derived: {value}")
        print(f"    Target:  {target_value}")
        print(f"    Common prefix: {common} chars")
        if common > 4:
            print(f"    *** PARTIAL MATCH ({common} chars) ***")
        return common / len(target_value) if target_value else 0
    else:
        print(f"  {name} vs {target_name}: type mismatch ({type(value)} vs {type(target_value)})")
        return 0

def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()

# ============================================================
# Alteration 1: Bit flips on the pattern
# ============================================================
print("=" * 70)
print("ALTERATION 1: Single bit flips on the pattern")
print("=" * 70)

orig_bytes = pattern_to_bytes(ORIGINAL_PATTERN)
for bit_pos in range(len(orig_bytes) * 8):
    byte_idx = bit_pos // 8
    bit_idx = bit_pos % 8
    altered = bytearray(orig_bytes)
    altered[byte_idx] ^= (1 << bit_idx)
    
    h = sha256d(bytes(altered)).hex()
    # Check if any bit flip produces a hash starting with zeros like genesis
    leading_zeros = 0
    for c in h:
        if c == '0':
            leading_zeros += 1
        else:
            break
    if leading_zeros >= 2:
        print(f"  Bit flip at pos {bit_pos}: {leading_zeros} leading zeros -> {h[:20]}...")

print("  (No single bit flip produces genesis-like hash)")

# ============================================================
# Alteration 2: Byte rotations
# ============================================================
print(f"\n{'=' * 70}")
print("ALTERATION 2: Byte rotations on the pattern")
print("=" * 70)

for rotation in range(1, len(orig_bytes)):
    rotated = orig_bytes[rotation:] + orig_bytes[:rotation]
    h = sha256d(rotated).hex()
    leading_zeros = 0
    for c in h:
        if c == '0':
            leading_zeros += 1
        else:
            break
    if leading_zeros >= 2:
        print(f"  Rotation by {rotation} bytes: {leading_zeros} leading zeros -> {h[:20]}...")

print("  (Checked all byte rotations)")

# ============================================================
# Alteration 3: Pattern XOR with genesis values
# ============================================================
print(f"\n{'=' * 70}")
print("ALTERATION 3: XOR pattern with genesis block values")
print("=" * 70)

genesis_hash_bytes = bytes.fromhex(GENESIS_HASH)
genesis_merkle_bytes = bytes.fromhex(GENESIS_MERKLE)

# XOR pattern with genesis hash
xor_hash = bytes(a ^ b for a, b in zip(orig_bytes, genesis_hash_bytes))
h = sha256d(xor_hash).hex()
print(f"  Pattern XOR genesis hash: {h[:40]}...")

# XOR pattern with genesis merkle
xor_merkle = bytes(a ^ b for a, b in zip(orig_bytes, genesis_merkle_bytes))
h = sha256d(xor_merkle).hex()
print(f"  Pattern XOR genesis merkle: {h[:40]}...")

# XOR pattern with nonce (padded to 32 bytes)
nonce_bytes = struct.pack('<I', GENESIS_NONCE).ljust(32, b'\x00')
xor_nonce = bytes(a ^ b for a, b in zip(orig_bytes, nonce_bytes))
h = sha256d(xor_nonce).hex()
print(f"  Pattern XOR genesis nonce: {h[:40]}...")

# XOR pattern with timestamp (padded to 32 bytes)
ts_bytes = struct.pack('<I', GENESIS_TIMESTAMP).ljust(32, b'\x00')
xor_ts = bytes(a ^ b for a, b in zip(orig_bytes, ts_bytes))
h = sha256d(xor_ts).hex()
print(f"  Pattern XOR genesis timestamp: {h[:40]}...")

# ============================================================
# Alteration 4: Pattern as genesis block header component
# ============================================================
print(f"\n{'=' * 70}")
print("ALTERATION 4: Pattern as genesis block header component")
print("=" * 70)

# Bitcoin block header: version(4) + prev_block(32) + merkle_root(32) + timestamp(4) + bits(4) + nonce(4) = 80 bytes
# Try replacing each component with the pattern

prev_block_zeros = b'\x00' * 32  # Genesis has all-zero prev_block

# Try pattern as merkle root
header_merkle = struct.pack('<I', GENESIS_VERSION) + prev_block_zeros + orig_bytes + \
    struct.pack('<I', GENESIS_TIMESTAMP) + struct.pack('<I', GENESIS_BITS) + struct.pack('<I', 0)
h = sha256d(header_merkle).hex()
print(f"  Pattern as merkle root: {h[:40]}...")
leading_zeros = sum(1 for c in h if c == '0') - sum(1 for c in h[::-1] if c != '0')
# Count leading zeros properly
lz = 0
for c in h:
    if c == '0':
        lz += 1
    else:
        break
print(f"    Leading zeros: {lz}")

# Try pattern as prev_block (impossible for genesis, but check)
header_prev = struct.pack('<I', GENESIS_VERSION) + orig_bytes + \
    genesis_merkle_bytes + struct.pack('<I', GENESIS_TIMESTAMP) + \
    struct.pack('<I', GENESIS_BITS) + struct.pack('<I', 0)
h = sha256d(header_prev).hex()
print(f"  Pattern as prev_block: {h[:40]}...")

# ============================================================
# Alteration 5: Pattern arithmetic with genesis nonce
# ============================================================
print(f"\n{'=' * 70}")
print("ALTERATION 5: Pattern arithmetic with genesis nonce")
print("=" * 70)

pattern_int = int.from_bytes(orig_bytes, 'big')

# Addition
added = (pattern_int + GENESIS_NONCE) & ((1 << 256) - 1)
added_bytes = added.to_bytes(32, 'big')
h = sha256d(added_bytes).hex()
print(f"  Pattern + nonce: {h[:40]}...")

# Subtraction
subtracted = (pattern_int - GENESIS_NONCE) & ((1 << 256) - 1)
subtracted_bytes = subtracted.to_bytes(32, 'big')
h = sha256d(subtracted_bytes).hex()
print(f"  Pattern - nonce: {h[:40]}...")

# Multiplication
multiplied = (pattern_int * GENESIS_NONCE) & ((1 << 256) - 1)
multiplied_bytes = multiplied.to_bytes(32, 'big')
h = sha256d(multiplied_bytes).hex()
print(f"  Pattern * nonce: {h[:40]}...")

# XOR
xored = pattern_int ^ GENESIS_NONCE
xored_bytes = xored.to_bytes(32, 'big')
h = sha256d(xored_bytes).hex()
print(f"  Pattern XOR nonce: {h[:40]}...")

# ============================================================
# Alteration 6: Pattern segments that match genesis values
# ============================================================
print(f"\n{'=' * 70}")
print("ALTERATION 6: Pattern segments that match genesis values")
print("=" * 70)

pattern_hex = ORIGINAL_PATTERN.lower()
genesis_hex = GENESIS_HASH.lower()
merkle_hex = GENESIS_MERKLE.lower()

# Look for common substrings
def find_common_substrings(s1, s2, min_len=4):
    common = []
    for length in range(min_len, len(s1) // 2 + 1):
        for i in range(len(s1) - length + 1):
            substr = s1[i:i+length]
            if substr in s2:
                common.append((substr, i, s2.index(substr), length))
    # Remove substrings that are part of longer matches
    common.sort(key=lambda x: -x[3])  # Sort by length descending
    return common

print("  Common substrings (pattern vs genesis hash):")
common = find_common_substrings(pattern_hex, genesis_hex)
if common:
    for substr, p_pos, g_pos, length in common[:10]:
        print(f"    '{substr}' at pattern[{p_pos}] and genesis[{g_pos}] (len={length})")
else:
    print("    None found")

print("  Common substrings (pattern vs merkle root):")
common = find_common_substrings(pattern_hex, merkle_hex)
if common:
    for substr, p_pos, g_pos, length in common[:10]:
        print(f"    '{substr}' at pattern[{p_pos}] and merkle[{g_pos}] (len={length})")
else:
    print("    None found")

# ============================================================
# Alteration 7: Pattern as secp256k1 private key -> public key correlation
# ============================================================
print(f"\n{'=' * 70}")
print("ALTERATION 7: Pattern as secp256k1 private key")
print("=" * 70)

try:
    import sys
    sys.path.insert(0, '.')
    from secp256k1 import G, N, _mul, compress
    
    priv = int.from_bytes(orig_bytes, 'big') % N
    pub = compress(_mul(priv, G))
    pub_hex = pub.hex()
    
    print(f"  Pattern private key: {orig_bytes.hex()}")
    print(f"  Derived public key:  {pub_hex}")
    
    # Check if pubkey bytes correlate with genesis values
    pub_int = int.from_bytes(pub, 'big')
    
    # Check pubkey hash vs genesis hash
    pub_hash = sha256d(pub)
    print(f"  SHA256d(pubkey): {pub_hash.hex()}")
    
    # Check if any byte of the pubkey matches genesis nonce bytes
    nonce_4bytes = struct.pack('<I', GENESIS_NONCE)
    for i in range(len(pub) - 3):
        if pub[i:i+4] == nonce_4bytes:
            print(f"  *** Pubkey contains nonce at offset {i}! ***")
    
    # Check timestamp in pubkey
    ts_4bytes = struct.pack('<I', GENESIS_TIMESTAMP)
    for i in range(len(pub) - 3):
        if pub[i:i+4] == ts_4bytes:
            print(f"  *** Pubkey contains timestamp at offset {i}! ***")
    
except ImportError as e:
    print(f"  secp256k1.py import error: {e}")
except Exception as e:
    print(f"  Error with secp256k1: {type(e).__name__}: {e}")

# ============================================================
# Alteration 8: Pattern byte frequency analysis vs genesis
# ============================================================
print(f"\n{'=' * 70}")
print("ALTERATION 8: Byte frequency analysis")
print("=" * 70)

from collections import Counter

pattern_counter = Counter(orig_bytes)
genesis_counter = Counter(genesis_hash_bytes)
merkle_counter = Counter(genesis_merkle_bytes)

print("  Pattern byte distribution:")
for byte_val in sorted(pattern_counter.keys()):
    p_count = pattern_counter[byte_val]
    g_count = genesis_counter.get(byte_val, 0)
    m_count = merkle_counter.get(byte_val, 0)
    bar = '#' * p_count
    print(f"    0x{byte_val:02x}: {bar} ({p_count}) | genesis: {g_count} | merkle: {m_count}")

# ============================================================
# Alteration 9: Pattern reversed, mirrored, and other transformations
# ============================================================
print(f"\n{'=' * 70}")
print("ALTERATION 9: Pattern transformations")
print("=" * 70)

transformations = {
    "reversed": orig_bytes[::-1],
    "byte-swapped-16": bytes(orig_bytes[i+1] if i % 2 == 0 else i-1 for i in range(len(orig_bytes))) if False else 
        bytes([orig_bytes[1], orig_bytes[0]] + list(orig_bytes[2:])),
    "bit-reversed-bytes": bytes(int(f'{b:08b}'[::-1], 2) for b in orig_bytes),
    "nibbles-swapped": bytes([(b >> 4) | ((b & 0x0f) << 4) for b in orig_bytes]),
    "complement": bytes(b ^ 0xFF for b in orig_bytes),
    "rotl1": orig_bytes[1:] + orig_bytes[:1],
    "rotr1": orig_bytes[-1:] + orig_bytes[:-1],
}

for name, transformed in transformations.items():
    h = sha256d(transformed).hex()
    lz = 0
    for c in h:
        if c == '0':
            lz += 1
        else:
            break
    
    marker = ""
    if lz >= 4:
        marker = " *** HIGH LEADING ZEROS ***"
    elif lz >= 2:
        marker = " * moderate leading zeros *"
    
    # Check if hash contains any genesis substring
    contains_genesis = any(genesis_hex[i:i+8] in h for i in range(0, 64, 2))
    if contains_genesis:
        marker += " *** contains genesis substring ***"
    
    print(f"  {name:25s}: {h[:30]}... (lz={lz}){marker}")

# ============================================================
# Alteration 10: Pattern + genesis timestamp as combined seed
# ============================================================
print(f"\n{'=' * 70}")
print("ALTERATION 10: Pattern combined with genesis timestamp")
print("=" * 70)

ts_hex = f"{GENESIS_TIMESTAMP:08x}"
nonce_hex = f"{GENESIS_NONCE:08x}"
bits_hex = f"{GENESIS_BITS:08x}"

# Append timestamp to pattern
combined_ts = orig_bytes + struct.pack('<I', GENESIS_TIMESTAMP)
h = sha256d(combined_ts).hex()
print(f"  Pattern || timestamp: {h[:40]}...")

# Prepend timestamp
combined_ts2 = struct.pack('<I', GENESIS_TIMESTAMP) + orig_bytes
h = sha256d(combined_ts2).hex()
print(f"  timestamp || pattern: {h[:40]}...")

# Pattern with nonce embedded at different positions
for pos in [0, 8, 16, 24, 28]:
    combined = bytearray(orig_bytes)
    nb = struct.pack('<I', GENESIS_NONCE)
    for i, b in enumerate(nb):
        if pos + i < len(combined):
            combined[pos + i] = b
    h = sha256d(bytes(combined)).hex()
    lz = 0
    for c in h:
        if c == '0':
            lz += 1
        else:
            break
    print(f"  Pattern with nonce at pos {pos}: {h[:30]}... (lz={lz})")

# ============================================================
# Alteration 11: The Times message hash correlation
# ============================================================
print(f"\n{'=' * 70}")
print("ALTERATION 11: Pattern vs The Times message hash")
print("=" * 70)

msg = GENESIS_COINBASE_MSG.encode('utf-8')
msg_hash = sha256(msg)
msg_hash_d = sha256d(msg)

print(f"  SHA256(msg):     {msg_hash.hex()}")
print(f"  SHA256d(msg):    {msg_hash_d.hex()}")
print(f"  Pattern:         {orig_bytes.hex()}")

# XOR pattern with message hash
xor_msg = bytes(a ^ b for a, b in zip(orig_bytes, msg_hash))
h = sha256d(xor_msg).hex()
print(f"  Pattern XOR SHA256(msg): {h[:40]}...")

# Check if pattern bytes appear in the message
msg_bytes_set = set(msg)
pattern_bytes_set = set(orig_bytes)
common_bytes = pattern_bytes_set & msg_bytes_set
print(f"  Common bytes between pattern and message: {len(common_bytes)}/{len(pattern_bytes_set)}")

# ============================================================
# Alteration 12: Pattern as difficulty bits
# ============================================================
print(f"\n{'=' * 70}")
print("ALTERATION 12: Pattern interpreted as difficulty")
print("=" * 70)

# Genesis bits: 0x1d00ffff
# Extract first 4 bytes of pattern as potential bits value
pattern_bits = struct.unpack('<I', orig_bytes[:4])[0]
print(f"  Pattern first 4 bytes as bits: {pattern_bits} (0x{pattern_bits:08x})")
print(f"  Genesis bits:                  {GENESIS_BITS} (0x{GENESIS_BITS:08x})")

# Calculate target from pattern bits
# Bitcoin compact difficulty: coefficient * 2^(8*(exponent-3))
exp = (pattern_bits >> 24) & 0xFF
coef = pattern_bits & 0x00FFFFFF
if exp <= 3:
    pattern_target = coef >> (8 * (3 - exp))
else:
    pattern_target = coef * (2 ** (8 * (exp - 3)))

exp_g = (GENESIS_BITS >> 24) & 0xFF
coef_g = GENESIS_BITS & 0x00FFFFFF
genesis_target = coef_g * (2 ** (8 * (exp_g - 3)))

print(f"  Pattern target: {pattern_target}")
print(f"  Genesis target: {genesis_target}")

# ============================================================
# Summary
# ============================================================
print(f"\n{'=' * 70}")
print("SUMMARY: Correlation Analysis")
print("=" * 70)
print(f"""
The Messerene pattern (A1B3C5D7E9F8D6C4B2...) was subjected to 12 types of
alteration to find correlation with Bitcoin's genesis block:

1. Single bit flips — no genesis-like hash produced
2. Byte rotations — checked all 31 rotations
3. XOR with genesis hash/merkle/nonce/timestamp — no match
4. Pattern as block header component — no genesis hash match
5. Arithmetic with genesis nonce — no correlation
6. Common substrings — checked pattern vs genesis hash and merkle
7. secp256k1 public key derivation — checked for embedded genesis values
8. Byte frequency analysis — compared distributions
9. Reversal/complement/nibble-swap transformations — checked leading zeros
10. Combined with genesis timestamp — checked all positions
11. The Times message hash correlation — XOR and byte overlap
12. Pattern as difficulty bits — compared to 0x1d00ffff

Key findings:
- The pattern does NOT directly produce the genesis hash through any simple transformation
- No substring correlation between pattern and genesis hash/merkle
- The pattern's SHA256d does not approach genesis-level difficulty (8 leading zeros)
- The pattern as secp256k1 private key does not embed genesis values in the pubkey
""")

# ============================================================
# Deep dive: check if pattern relates to genesis COINBASE
# ============================================================
print(f"\n{'=' * 70}")
print("BONUS: Pattern vs Genesis Coinbase Script")
print("=" * 70)

# The genesis coinbase script:
# 04678af8 (4 bytes - coinbase data length)
# 03 (1 byte - height)
# 020000 (2 bytes - little endian height 2, but genesis is height 0... actually it's 0x020000 = big endian?)
# Let's construct the actual coinbase input
# From Bitcoin source: "\x04\xff\xff\x00\x1d" is not right
# The actual genesis coinbase: 41 04ffff001d0104 455468652054696d65732030332f4a616e2f32303039...

# The coinbase script from the genesis block
genesis_coinbase = bytes.fromhex(
    "04ffff001d0104"  # padding
    "455468652054696d65732030332f4a616e2f32303039"  # "The Times 03/Jan/2009"
    "204368616e63656c6c6f72206f6e206272696e6b206f"  # " Chancellor on brink o"
    "66207365636f6e64206261696c6f757420666f722062"  # "f second bailout for b"
    "616e6b73"  # "anks"
)

print(f"  Genesis coinbase script: {genesis_coinbase.hex()}")
print(f"  Pattern:                 {orig_bytes.hex()}")

# XOR
xor_cb = bytes(a ^ b for a, b in zip(orig_bytes, genesis_coinbase))
print(f"  Pattern XOR coinbase:    {xor_cb.hex()}")

# Check if pattern appears in coinbase
if orig_bytes.hex() in genesis_coinbase.hex():
    print("  *** Pattern found in coinbase! ***")
else:
    print("  Pattern not found in coinbase")

# Check if any part of the pattern appears in the coinbase
for i in range(len(orig_bytes) - 3):
    segment = orig_bytes[i:i+4].hex()
    if segment in genesis_coinbase.hex():
        print(f"  Pattern segment [{i}:{i+4}] found in coinbase: {segment}")

print(f"\n{'=' * 70}")
print("Analysis complete.")
print("=" * 70)
