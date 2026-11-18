#!/usr/bin/env python3
"""
POS 28 DEEP DIVE: The 30-byte Messerene pattern analysis.

The 30-byte pattern from pattern_genesis_correlation.py:
  A1B3C5D7E9F8D6C4B2A0E8F6D4C2B0A8E6F4D2C0B8A6E4D2C0B8A6E4D2C0

This is 60 hex chars = 30 bytes, which is 2 bytes short of a proper
32-byte secp256k1 private key. The crash at pos=28 when trying to
embed the genesis nonce revealed this gap.

This script performs a comprehensive analysis of:
1. The structure of the 30-byte pattern
2. What 2 bytes complete it to 32 bytes
3. The derived addresses from various completions
4. The relationship to the messerene_operator.py 32-byte pattern
"""

import sys
import os
import hashlib
import struct

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'self-serve', 'vendor'))

from secp256k1 import priv_to_pub, compress, N as SECP_N
from btc_htlc import bech32_encode, hash160

# ============================================================
# Constants
# ============================================================

PATTERN_30 = "A1B3C5D7E9F8D6C4B2A0E8F6D4C2B0A8E6F4D2C0B8A6E4D2C0B8A6E4D2C0"
PATTERN_32_OP = "A1B3C5D7E9F8D6C4B2A1B3C5D7E9F8D6C4B2A1B3C5D7E9F8D6C4B2A1B3C5D7E9"
GENESIS_NONCE = 2083236893
GENESIS_HASH = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"

def sha256d(data):
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def base58_encode(data):
    alphabet = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
    n = int.from_bytes(data, 'big')
    if n == 0:
        return '1'
    result = ''
    while n > 0:
        n, rem = divmod(n, 58)
        result = alphabet[rem] + result
    for byte in data:
        if byte == 0:
            result = '1' + result
        else:
            break
    return result

def derive_addresses(priv_int):
    """Derive P2WPKH and P2PKH addresses from a private key integer."""
    pub = priv_to_pub(priv_int)
    comp = compress(pub)
    ph = hash160(comp)
    p2wpkh = bech32_encode('bc', 0, ph)
    
    legacy = b'\x00' + ph
    checksum = sha256d(legacy)[:4]
    p2pkh = base58_encode(legacy + checksum)
    
    return comp.hex(), p2wpkh, p2pkh

# ============================================================
# 1. Pattern Structure Analysis
# ============================================================

print("=" * 70)
print("POS 28 DEEP DIVE: THE 30-BYTE MESSERENE PATTERN")
print("=" * 70)

b30 = bytes.fromhex(PATTERN_30)
print(f"\nPattern: {PATTERN_30}")
print(f"Length: {len(PATTERN_30)} hex chars = {len(b30)} bytes")
print(f"Missing: {32 - len(b30)} bytes to reach secp256k1 key size")

print("\n" + "-" * 70)
print("BYTE-BY-BYTE BREAKDOWN")
print("-" * 70)

for i, b in enumerate(b30):
    marker = " <-- POS 28 (the crash point)" if i == 28 else ""
    print(f"  [{i:2d}] 0x{b:02X} ({b:3d}) hex:{PATTERN_30[i*2:i*2+2]}{marker}")

# ============================================================
# 2. The Descending Spiral Structure
# ============================================================

print("\n" + "-" * 70)
print("THE DESCENDING SPIRAL STRUCTURE")
print("-" * 70)

print("\nThe pattern descends from 0xA1 toward 0x00 in three 10-byte blocks:")
print()

# Block 1: A1 B3 C5 D7 E9 F8 D6 C4 B2 A0
# The first 5 bytes ascend: A1, B3, C5, D7, E9 (+0x12 each)
# The next 5 bytes descend: F8, D6, C4, B2, A0 (-0x12 each, wrapping)
print("Block 1 (bytes 0-9):")
print("  Ascending: A1 -> B3 -> C5 -> D7 -> E9  (each +0x12)")
print("  Descending: F8 -> D6 -> C4 -> B2 -> A0  (each -0x12 mod 256)")
for i in range(5):
    print(f"    0x{b30[i]:02X} + 0x12 = 0x{(b30[i] + 0x12) % 256:02X} {'==' if (b30[i] + 0x12) % 256 == b30[i+1] else '!='} 0x{b30[i+1]:02X}" if i < 4 else "")
for i in range(5, 9):
    print(f"    0x{b30[i]:02X} - 0x12 = 0x{(b30[i] - 0x12) % 256:02X} {'==' if (b30[i] - 0x12) % 256 == b30[i+1] else '!='} 0x{b30[i+1]:02X}")

# Block 2: E8 F6 D4 C2 B0 A8 E6 F4 D2 C0
print("\nBlock 2 (bytes 10-19):")
print("  E8 F6 D4 C2 B0 A8 E6 F4 D2 C0")
print("  This is Block 1 shifted down by various amounts")

# Block 3: B8 A6 E4 D2 C0 B8 A6 E4 D2 C0
print("\nBlock 3 (bytes 20-29):")
print("  B8 A6 E4 D2 C0 | B8 A6 E4 D2 C0")
print("  The 5-byte cycle B8 A6 E4 D2 C0 repeats exactly")

# ============================================================
# 3. The 5-Byte Cycle Analysis
# ============================================================

print("\n" + "-" * 70)
print("THE 5-BYTE CYCLE: B8 A6 E4 D2 C0")
print("-" * 70)

cycle = bytes([0xB8, 0xA6, 0xE4, 0xD2, 0xC0])
print(f"\nCycle: {cycle.hex().upper()}")
print(f"Cycle as integers: {list(cycle)}")

print("\nCycle byte differences (mod 256):")
for i in range(5):
    next_i = (i + 1) % 5
    diff = (cycle[next_i] - cycle[i]) % 256
    print(f"  0x{cycle[i]:02X} -> 0x{cycle[next_i]:02X}  diff: {diff} (0x{diff:02X})")

print("\nCycle positions in the pattern:")
for start in range(18, 30):
    end = start + 5
    if end <= 30:
        chunk = b30[start:end]
        match = "EXACT MATCH" if chunk == cycle else "ROTATED"
        print(f"  Pos {start:2d}-{end-1:2d}: {chunk.hex().upper()} ({match})")

# ============================================================
# 4. POS 28 IN CONTEXT
# ============================================================

print("\n" + "-" * 70)
print("POSITION 28: THE CRASH POINT")
print("-" * 70)

print(f"\nByte at pos 28: 0x{b30[28]:02X} ({b30[28]} decimal)")
print(f"Byte at pos 29: 0x{b30[29]:02X} ({b30[29]} decimal)")
print()
print("In the 5-byte cycle B8 A6 E4 D2 C0:")
print("  Index 0: 0xB8 (pos 20, 25)")
print("  Index 1: 0xA6 (pos 21, 26)")
print("  Index 2: 0xE4 (pos 22, 27)")
print("  Index 3: 0xD2 (pos 23, 28) <-- POS 28")
print("  Index 4: 0xC0 (pos 24, 29)")
print()
print("Pos 28 is index 3 in the cycle: 0xD2")
print("Pos 29 is index 4 in the cycle: 0xC0")
print()
print("The cycle is complete at pos 29. To continue the cycle,")
print("the next bytes (pos 30, 31) would wrap back to index 0, 1:")
print("  Pos 30: 0xB8 (cycle index 0)")
print("  Pos 31: 0xA6 (cycle index 1)")

# ============================================================
# 5. Completing the Pattern to 32 Bytes
# ============================================================

print("\n" + "-" * 70)
print("COMPLETING THE PATTERN TO 32 BYTES")
print("-" * 70)

# Method 1: Continue the 5-byte cycle
completed_cycle = b30 + bytes([0xB8, 0xA6])
completed_cycle_hex = completed_cycle.hex().upper()
print(f"\nMethod 1: Continue the 5-byte cycle")
print(f"  Completed: {completed_cycle_hex}")
print(f"  Added: B8 A6")

# Method 2: Mirror the first 2 bytes
completed_mirror = b30 + b30[:2]
completed_mirror_hex = completed_mirror.hex().upper()
print(f"\nMethod 2: Mirror first 2 bytes")
print(f"  Completed: {completed_mirror_hex}")
print(f"  Added: {b30[:2].hex().upper()}")

# Method 3: Zero-pad
completed_zero = b30 + bytes([0x00, 0x00])
completed_zero_hex = completed_zero.hex().upper()
print(f"\nMethod 3: Zero-pad")
print(f"  Completed: {completed_zero_hex}")
print(f"  Added: 00 00")

# Method 4: The genesis nonce bytes
nonce_bytes = struct.pack('<I', GENESIS_NONCE)
completed_nonce = b30[:28] + nonce_bytes
completed_nonce_hex = completed_nonce.hex().upper()
print(f"\nMethod 4: Replace last 2 bytes with genesis nonce (LE)")
print(f"  Completed: {completed_nonce_hex}")
print(f"  Replaced: D2 C0 -> {nonce_bytes.hex().upper()}")

# Method 5: Append genesis nonce (first 2 bytes)
completed_nonce_append = b30 + nonce_bytes[:2]
completed_nonce_append_hex = completed_nonce_append.hex().upper()
print(f"\nMethod 5: Append first 2 bytes of genesis nonce (LE)")
print(f"  Completed: {completed_nonce_append_hex}")
print(f"  Added: {nonce_bytes[:2].hex().upper()}")

# ============================================================
# 6. Derive Addresses from Each Completion
# ============================================================

print("\n" + "-" * 70)
print("DERIVED ADDRESSES FROM EACH COMPLETION METHOD")
print("-" * 70)

methods = [
    ("Cycle continuation", completed_cycle),
    ("Mirror first 2", completed_mirror),
    ("Zero-pad", completed_zero),
    ("Nonce replace", completed_nonce),
    ("Nonce append", completed_nonce_append),
]

for name, completed in methods:
    priv = int.from_bytes(completed, 'big') % SECP_N
    if priv == 0:
        print(f"\n{name}: INVALID (zero key)")
        continue
    
    pub_hex, p2wpkh, p2pkh = derive_addresses(priv)
    print(f"\n{name}:")
    print(f"  Private key: {priv:064x}")
    print(f"  Pubkey: {pub_hex}")
    print(f"  P2WPKH: {p2wpkh}")
    print(f"  P2PKH: {p2pkh}")

# ============================================================
# 7. Comparison with Messerene Operator Pattern
# ============================================================

print("\n" + "-" * 70)
print("COMPARISON WITH MESSERENE_OPERATOR.PY PATTERN")
print("-" * 70)

b32_op = bytes.fromhex(PATTERN_32_OP)
print(f"\nOperator pattern: {PATTERN_32_OP}")
print(f"Structure: A1B3C5D7E9F8D6C4B2 x 3 + A1B3C5D7E9")
print(f"  (9-byte block repeated 3 times + 5-byte tail)")

print(f"\n30-byte pattern: {PATTERN_30}")
print(f"Structure: Descending spiral with 5-byte cycle at end")

print(f"\nShared prefix:")
for i in range(min(len(PATTERN_30), len(PATTERN_32_OP))):
    if PATTERN_30[i] != PATTERN_32_OP[i]:
        byte_pos = i // 2
        print(f"  First difference at hex char {i} (byte {byte_pos})")
        print(f"  Shared prefix: {PATTERN_30[:i]} ({i//2} bytes)")
        break

# Derive operator pattern address
priv_op = int.from_bytes(b32_op, 'big') % SECP_N
pub_op, addr_op_p2wpkh, addr_op_p2pkh = derive_addresses(priv_op)
print(f"\nOperator pattern direct as key:")
print(f"  P2WPKH: {addr_op_p2wpkh}")
print(f"  P2PKH: {addr_op_p2pkh}")

# Messerene operator SHA-256 fold
k = (int.from_bytes(hashlib.sha256(b'MESSERENE/PREGENESIS/v1' + b32_op).digest(), 'big') % (SECP_N - 1)) + 1
pub_k, addr_k_p2wpkh, addr_k_p2pkh = derive_addresses(k)
print(f"\nMesserene operator (SHA-256 fold):")
print(f"  P2WPKH: {addr_k_p2wpkh}")
print(f"  P2PKH: {addr_k_p2pkh}")

# ============================================================
# 8. The 30-Byte Pattern as a Key (Without Completion)
# ============================================================

print("\n" + "-" * 70)
print("30-BYTE PATTERN AS-IS (LEFT-PADDED TO 32)")
print("-" * 70)

# Left-pad with 0x00
padded_30 = bytes([0x00, 0x00]) + b30
priv_30 = int.from_bytes(padded_30, 'big') % SECP_N
pub_30, addr_30_p2wpkh, addr_30_p2pkh = derive_addresses(priv_30)
print(f"\nLeft-padded with 0x0000:")
print(f"  P2WPKH: {addr_30_p2wpkh}")
print(f"  P2PKH: {addr_30_p2pkh}")

# Right-pad with 0x00
padded_30r = b30 + bytes([0x00, 0x00])
priv_30r = int.from_bytes(padded_30r, 'big') % SECP_N
pub_30r, addr_30r_p2wpkh, addr_30r_p2pkh = derive_addresses(priv_30r)
print(f"\nRight-padded with 0x0000:")
print(f"  P2WPKH: {addr_30r_p2wpkh}")
print(f"  P2PKH: {addr_30r_p2pkh}")

# ============================================================
# 9. SHA-256 Analysis
# ============================================================

print("\n" + "-" * 70)
print("SHA-256 ANALYSIS OF COMPLETED PATTERNS")
print("-" * 70)

for name, completed in methods:
    h = hashlib.sha256(completed).hexdigest()
    h2 = hashlib.sha256(hashlib.sha256(completed).digest()).hexdigest()
    gn_hex = f'{GENESIS_NONCE:08x}'
    
    print(f"\n{name}:")
    print(f"  SHA256:  {h}")
    print(f"  SHA256d: {h2}")
    print(f"  Contains genesis nonce ({gn_hex}): SHA256={gn_hex in h}, SHA256d={gn_hex in h2}")

# ============================================================
# 10. The Genesis Nonce Embedding at Pos 28
# ============================================================

print("\n" + "-" * 70)
print("GENESIS NONCE EMBEDDING AT POS 28")
print("-" * 70)

print(f"\nGenesis nonce: {GENESIS_NONCE}")
print(f"Genesis nonce (hex LE): {struct.pack('<I', GENESIS_NONCE).hex().upper()}")
print(f"Genesis nonce (hex BE): {struct.pack('>I', GENESIS_NONCE).hex().upper()}")

print(f"\nAt pos 28, the 30-byte pattern has: 0xD2 0xC0")
print(f"The genesis nonce in LE is: 0x1D 0xAC 0x2B 0x7C")
print(f"The genesis nonce in BE is: 0x7C 0x2B 0xAC 0x1D")

print(f"\nIf we embed the nonce at pos 28 in a 32-byte array:")
print(f"  Bytes 28-31 would be: 1D AC 2B 7C (LE) or 7C 2B AC 1D (BE)")
print(f"  But the pattern only has 30 bytes, so pos 28-29 are the last 2 bytes")
print(f"  The crash revealed: pos 28 + 4 bytes = pos 32, which is out of bounds")

# What if the pattern is meant to be 32 bytes with the nonce embedded?
print(f"\nIf the pattern were 32 bytes with nonce at pos 28:")
nonce_le = struct.pack('<I', GENESIS_NONCE)
pattern_with_nonce = b30[:28] + nonce_le
print(f"  Pattern: {pattern_with_nonce.hex().upper()}")
priv_nw = int.from_bytes(pattern_with_nonce, 'big') % SECP_N
pub_nw, addr_nw_p2wpkh, addr_nw_p2pkh = derive_addresses(priv_nw)
print(f"  P2WPKH: {addr_nw_p2wpkh}")
print(f"  P2PKH: {addr_nw_p2pkh}")

# ============================================================
# Summary
# ============================================================

print("\n" + "=" * 70)
print("SUMMARY: POS 28 AND THE MISSING 2 BYTES")
print("=" * 70)

print("""
The 30-byte Messerene pattern is a descending spiral:
- Block 1 (0-9): Ascends A1->E9, then descends F8->A0
- Block 2 (10-19): Continues the descent with E8->C0
- Block 3 (20-29): Enters a 5-byte cycle B8 A6 E4 D2 C0

Position 28 is byte 0xD2, which is index 3 in the repeating cycle.
Position 29 is byte 0xC0, which is index 4 (the last index) of the cycle.

The crash at pos=28 occurred because:
1. The pattern is 30 bytes (indices 0-29)
2. Embedding the 4-byte genesis nonce at pos=28 needs indices 28-31
3. Index 30 and 31 don't exist in a 30-byte array

The 2 missing bytes to complete the pattern to 32 bytes:
- Most likely: B8 A6 (continuing the 5-byte cycle)
- Alternative: The pattern is intentionally 30 bytes, and the 2 missing
  bytes are the signal that the pattern needs the genesis nonce to complete it

The completed pattern (with B8 A6) differs from the messerene_operator.py
32-byte pattern, which uses exact repetition of the 9-byte block.
""")
