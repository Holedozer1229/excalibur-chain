#!/usr/bin/env python3
"""Find valid Base58 burn addresses with repeating character patterns.

The decoder revealed:
- 1EaterXXX... has 21-byte payload (should be 20) - INVALID checksum
- 1BurnBurn... has 21-byte payload (should be 20) - INVALID checksum
- 1111111111111111111114oLvT2 has 20-byte all-zero payload - VALID

The key insight: in Base58, each character adds log2(58) ≈ 5.857 bits.
A valid P2PKH address needs: 1 version byte + 20 hash bytes + 4 checksum = 25 bytes total.
The Base58 string length determines how many bits we have, which determines
how many bytes we get after decoding.

For the 'X' repeating pattern (X = value 30 in Base58):
- 'X' in Base58 alphabet index 30
- Repeating X's create a specific bit pattern

Let's find the correct number of X's to get a valid 20-byte payload.
"""

import hashlib

BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'


def base58_encode(data: bytes) -> str:
    """Encode bytes to Base58Check."""
    num = int.from_bytes(data, 'big')
    encoded = ''
    while num > 0:
        num, rem = divmod(num, 58)
        encoded = BASE58_ALPHABET[rem] + encoded
    # Leading zeros
    for byte in data:
        if byte == 0:
            encoded = '1' + encoded
        else:
            break
    return encoded


def base58check_encode(version: int, payload: bytes) -> str:
    """Encode to Base58Check address."""
    data = bytes([version]) + payload
    checksum = hashlib.sha256(hashlib.sha256(data).digest()).digest()[:4]
    return base58_encode(data + checksum)


def base58_decode_bytes(s: str) -> bytes:
    """Decode a Base58 string to raw bytes."""
    num = 0
    for c in s:
        num = num * 58 + BASE58_ALPHABET.index(c)
    byte_list = []
    while num:
        num, rem = divmod(num, 256)
        byte_list.append(rem)
    byte_list.reverse()
    leading_ones = len(s) - len(s.lstrip('1'))
    return b'\x00' * leading_ones + bytes(byte_list)


def try_pattern(prefix: str, repeat_char: str, repeat_counts: list, suffix: str = "") -> list:
    """Try different repeat counts to find valid Base58Check addresses."""
    results = []
    for count in repeat_counts:
        addr = prefix + repeat_char * count + suffix
        raw = base58_decode_bytes(addr)
        if len(raw) >= 5:
            version = raw[0]
            payload = raw[1:-4]
            checksum_provided = raw[-4:]
            checksum_expected = hashlib.sha256(hashlib.sha256(bytes([version]) + payload).digest()).digest()[:4]
            valid = checksum_provided == checksum_expected
            results.append({
                "address": addr,
                "length": len(addr),
                "raw_bytes": len(raw),
                "payload_bytes": len(payload),
                "payload_hex": payload.hex(),
                "valid": valid,
                "version": version,
            })
    return results


# ---------------------------------------------------------------- Analysis
print("=" * 80)
print("FINDING VALID BASE58 BURN ADDRESSES WITH REPEATING PATTERNS")
print("=" * 80)

# The problem with 1EaterXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
print("\n1. ANALYZING 1EaterXXX...")
print("-" * 40)
eater = "1EaterXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
raw = base58_decode_bytes(eater)
print(f"  Address length: {len(eater)} chars")
print(f"  Decoded bytes: {len(raw)}")
print(f"  Payload bytes: {len(raw[1:-4])} (should be 20 for P2PKH)")
print(f"  The 'X' repeat gives us {len(raw[1:-4])} payload bytes - one too many!")

# Try to find the right number of X's after "1Eater"
print("\n2. SEARCHING FOR VALID '1Eater' + X PATTERN")
print("-" * 40)
for x_count in range(15, 35):
    addr = f"1Eater{'X' * x_count}"
    raw = base58_decode_bytes(addr)
    if len(raw) >= 5:
        version = raw[0]
        payload = raw[1:-4]
        checksum_provided = raw[-4:]
        checksum_expected = hashlib.sha256(hashlib.sha256(bytes([version]) + payload).digest()).digest()[:4]
        valid = checksum_provided == checksum_expected
        if len(payload) == 20:
            marker = " <-- 20-byte payload!" if len(payload) == 20 else ""
            valid_marker = " [VALID CHECKSUM!]" if valid else " [invalid checksum]"
            print(f"  X*{x_count:2d}: {addr} -> {len(raw)} bytes, payload={len(payload)}{marker}{valid_marker}")

# Try all single repeating chars after "1"
print("\n3. SEARCHING FOR ALL REPEATING-CHAR PATTERNS (1 + char*N)")
print("-" * 40)
print("Looking for addresses like 1XXXX... or 1BBBB... with valid checksums\n")

for char_idx, char in enumerate(BASE58_ALPHABET):
    if char == '1':  # Skip '1' as it's the version byte indicator
        continue
    
    for count in range(20, 45):
        addr = "1" + char * count
        raw = base58_decode_bytes(addr)
        if len(raw) >= 25:  # 1 version + 20 payload + 4 checksum = 25
            version = raw[0]
            if version != 0:  # Must be P2PKH
                continue
            payload = raw[1:-4]
            if len(payload) != 20:
                continue
            checksum_provided = raw[-4:]
            checksum_expected = hashlib.sha256(hashlib.sha256(bytes([version]) + payload).digest()).digest()[:4]
            if checksum_provided == checksum_expected:
                print(f"  FOUND VALID: {addr}")
                print(f"    Payload: {payload.hex()}")
                # Check for repeating pattern in payload
                for period in range(1, 6):
                    pattern = payload[:period]
                    if all(payload[i] == pattern[i % period] for i in range(len(payload))):
                        print(f"    Pattern: {pattern.hex()} repeating x{len(payload)//period}")
                        break

# Try the "Burn" pattern specifically
print("\n4. ANALYZING 'Burn' REPEATING PATTERN")
print("-" * 40)
print("  'Burn' in Base58 values:")
for c in "Burn":
    print(f"    {c} = {BASE58_ALPHABET.index(c)}")

# Try different numbers of "Burn" repeats
for burn_count in range(1, 10):
    prefix = "1" + "Burn" * burn_count
    # Try adding X's at the end
    for x_count in range(0, 10):
        addr = prefix + "X" * x_count
        raw = base58_decode_bytes(addr)
        if len(raw) >= 25:
            version = raw[0]
            if version != 0:
                continue
            payload = raw[1:-4]
            if len(payload) == 20:
                checksum_provided = raw[-4:]
                checksum_expected = hashlib.sha256(hashlib.sha256(bytes([version]) + payload).digest()).digest()[:4]
                valid = checksum_provided == checksum_expected
                if valid:
                    print(f"  VALID: {addr}")
                    print(f"    Payload: {payload.hex()}")

# The real question: can we find a valid address with a meaningful repeating pattern?
print("\n5. THE KEY INSIGHT: Base58 vs Bech32")
print("-" * 40)
print("""
In bech32, f=9 works because:
  - Each char = exactly 5 bits
  - Repeating 9s = repeating 01001 bit pattern
  - This cleanly converts to repeating 0x4A5294A529 bytes

In Base58, it's different:
  - Each char = log2(58) ~ 5.857 bits (not a clean divisor of 8)
  - Repeating chars don't create clean byte patterns
  - The checksum constraint makes it even harder

However, we CAN create valid Base58 addresses with repeating patterns
by brute-forcing the right combination of prefix + repeat count + suffix.
""")

# Find all valid vanity burn addresses with simple patterns
print("\n6. BRUTE FORCE: Finding all valid 1XXX... patterns")
print("-" * 40)
found = []
for x_count in range(20, 40):
    addr = "1" + "X" * x_count
    raw = base58_decode_bytes(addr)
    if len(raw) == 25:  # 1 + 20 + 4
        version = raw[0]
        payload = raw[1:-4]
        checksum_provided = raw[-4:]
        checksum_expected = hashlib.sha256(hashlib.sha256(bytes([version]) + payload).digest()).digest()[:4]
        if checksum_provided == checksum_expected:
            found.append(addr)
            print(f"  VALID: {addr}")
            print(f"    Payload: {payload.hex()}")

if not found:
    print("  No valid 1XXX... addresses found with pure X repeat")
    print("  The checksum constraint prevents pure repeating patterns in Base58")

print("\n" + "=" * 80)
print("CONCLUSION")
print("=" * 80)
print("""
1. 1EaterXXX... and 1BurnBurn... are INVALID because:
   - The character count gives 21 payload bytes instead of 20
   - The checksum doesn't match

2. In Base58, pure repeating character patterns almost never produce
   valid checksums due to the mathematical constraints.

3. The bech32 system is superior for pattern-based addresses because:
   - 5-bit encoding creates clean repeating byte patterns
   - The polymod checksum can be satisfied with pattern + short suffix

4. The valid pattern addresses are:
   - bc1qqqq... (q=0, all-zero witness)
   - bc1qfff... (f=9, 0x4A5294A529 pattern)
   - 1111111111111111111114oLvT2 (all-zero hash, but not pure repeat)

5. For 1Eater/1BurnBurn to be valid, they would need different
   character counts or suffixes to get exactly 20 payload bytes
   with a valid checksum.
""")
