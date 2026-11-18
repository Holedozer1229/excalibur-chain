#!/usr/bin/env python3
"""Decode all burn addresses character by character to reveal byte patterns.

Using the f=9 discovery, we can decode any address to see what byte patterns
the character sequences represent. For bech32, each char = 5-bit value.
For Base58, each char = value in Base58 alphabet.
"""

import hashlib

# ---------------------------------------------------------------- Base58 decoding
BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'


def base58_decode_bytes(s: str) -> bytes:
    """Decode a Base58 string to raw bytes (no checksum validation)."""
    num = 0
    for c in s:
        num = num * 58 + BASE58_ALPHABET.index(c)
    # Convert to bytes (big-endian)
    byte_list = []
    while num:
        num, rem = divmod(num, 256)
        byte_list.append(rem)
    byte_list.reverse()
    # Leading '1' characters = leading zero bytes
    leading_ones = len(s) - len(s.lstrip('1'))
    return b'\x00' * leading_ones + bytes(byte_list)


def decode_base58_address(addr: str) -> dict:
    """Decode a Base58Check address to its components."""
    raw = base58_decode_bytes(addr)
    if len(raw) < 5:
        return {"error": f"Too short: {len(raw)} bytes"}
    version = raw[0]
    payload = raw[1:-4]
    checksum_provided = raw[-4:]
    checksum_expected = hashlib.sha256(hashlib.sha256(bytes([version]) + payload).digest()).digest()[:4]
    valid = checksum_provided == checksum_expected
    return {
        "version": version,
        "version_hex": f"0x{version:02x}",
        "payload_hex": payload.hex(),
        "payload_len": len(payload),
        "checksum_provided": checksum_provided.hex(),
        "checksum_expected": checksum_expected.hex(),
        "valid_checksum": valid,
        "raw_bytes": raw,
        "raw_hex": raw.hex(),
    }


# ---------------------------------------------------------------- Bech32 decoding (from btc_htlc.py)
_BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"


def _polymod(vals):
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in vals:
        b = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            if (b >> i) & 1:
                chk ^= gen[i]
    return chk


def _hrp_expand(hrp):
    return [ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp]


def _convertbits(data, frm, to, pad=True):
    val = 0
    bits = 0
    out = []
    maxv = (1 << to) - 1
    for v in data:
        val = (val << frm) | v
        bits += frm
        while bits >= to:
            bits -= to
            out.append((val >> bits) & maxv)
    if pad:
        if bits:
            out.append((val << (to - bits)) & maxv)
    elif bits >= frm or ((val << (to - bits)) & maxv):
        return None
    return out


def bech32_decode(addr: str):
    """Return (hrp, witver, program, char_values); raises on bad checksum."""
    addr = addr.lower()
    pos = addr.rfind("1")
    if pos < 1 or pos + 7 > len(addr):
        raise ValueError("bad bech32 address")
    hrp, tail = addr[:pos], addr[pos + 1:]
    vals = [_BECH32.index(c) for c in tail]
    if _polymod(_hrp_expand(hrp) + vals) != 1:
        raise ValueError("bad bech32 checksum")
    prog = _convertbits(vals[1:-6], 5, 8, False)
    if prog is None:
        raise ValueError("bad bech32 program bits")
    return hrp, vals[0], bytes(prog), vals


# ---------------------------------------------------------------- All burn addresses
BURN_ADDRESSES = [
    # Legacy Base58
    "1CounterpartyXXXXXXXXXXXXXXXUWLpVr",
    "1111111111111111111114oLvT2",
    "1BitcoinEaterAddressDontSendf59kuE",
    "1EaterXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
    "1BurnBurnBurnBurnBurnBurnBurnBurnXb",
    # Bech32 'q' pattern (all-zero witness)
    "bc1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqthqst8",
    "bc1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq9e75rs",
    # Bech32 'f' pattern (f=9)
    "bc1qfffffffffffffffffffffffffffffffffffffffffffffffffffqe708k7",
    "bc1qffffffffffffffffffffffffffffffff82jzwn",
]


def show_char_values(addr: str):
    """Show the 5-bit or Base58 value of each character."""
    if addr.startswith("bc1"):
        # Bech32 - show 5-bit values
        tail = addr.lower().split("1", 1)[1]
        vals = [_BECH32.index(c) for c in tail]
        return [v for v in vals]
    else:
        # Base58 - show Base58 values
        return [BASE58_ALPHABET.index(c) for c in addr]


def analyze_pattern(raw_bytes: bytes) -> str:
    """Check if bytes have a repeating pattern."""
    for period in range(1, 10):
        pattern = raw_bytes[:period]
        if all(raw_bytes[i] == pattern[i % period] for i in range(len(raw_bytes))):
            return f"REPEATING: {pattern.hex()} x{len(raw_bytes) // period}"
    return "no simple repeat"


# ---------------------------------------------------------------- Main
print("=" * 80)
print("BURN ADDRESS DECODER — Revealing byte patterns behind each address")
print("=" * 80)

for addr in BURN_ADDRESSES:
    print(f"\n{'=' * 80}")
    print(f"Address: {addr}")
    print(f"{'=' * 80}")

    # Show character values
    char_vals = show_char_values(addr)
    print(f"\nCharacter values: {char_vals[:20]}{'...' if len(char_vals) > 20 else ''}")

    # Count consecutive same values
    if len(char_vals) > 1:
        runs = []
        current = char_vals[0]
        count = 1
        for v in char_vals[1:]:
            if v == current:
                count += 1
            else:
                runs.append((current, count))
                current = v
                count = 1
        runs.append((current, count))
        print(f"Value runs: {runs}")

    if addr.startswith("bc1"):
        # Bech32 address
        try:
            hrp, witver, program, vals = bech32_decode(addr)
            print(f"\n[OK] Valid bech32 checksum")
            print(f"  HRP: {hrp}")
            print(f"  Witness version: {witver}")
            print(f"  Witness program ({len(program)} bytes): {program.hex()}")
            print(f"  Pattern: {analyze_pattern(program)}")
            # Show the 5-bit bitstream
            bits = ""
            for v in vals[:-6]:  # exclude checksum
                bits += f"{v:05b}"
            print(f"  5-bit bitstream (first 100 bits): {bits[:100]}...")
            print(f"  8-bit bytes from bitstream: {program.hex()}")
        except ValueError as e:
            print(f"\n[FAIL] Invalid bech32: {e}")
    else:
        # Base58 address
        result = decode_base58_address(addr)
        if "error" in result:
            print(f"\n[FAIL] {result['error']}")
            continue

        version_label = 'P2PKH' if result['version'] == 0 else ('P2SH' if result['version'] == 5 else 'Unknown')
        print(f"\n  Version byte: {result['version_hex']} ({version_label})")
        print(f"  Payload hash ({result['payload_len']} bytes): {result['payload_hex']}")
        print(f"  Checksum provided: {result['checksum_provided']}")
        print(f"  Checksum expected: {result['checksum_expected']}")
        if result['valid_checksum']:
            print(f"  [OK] Valid checksum")
        else:
            print(f"  [FAIL] INVALID CHECKSUM")
        print(f"  Full raw bytes: {result['raw_hex']}")
        print(f"  Payload pattern: {analyze_pattern(result['payload_hex'].decode('hex') if hasattr(result['payload_hex'], 'decode') else bytes.fromhex(result['payload_hex']))}")

        # Show the byte values of the payload
        payload_bytes = bytes.fromhex(result['payload_hex'])
        print(f"  Payload byte values: {list(payload_bytes[:20])}{'...' if len(payload_bytes) > 20 else ''}")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print("\nThe f=9 pattern in bech32:")
print("  Byte pattern 0x4A 0x52 0x94 0xA5 0x29 repeating")
print("  Creates bitstream: 01001 01001 01001... (all 9s in 5-bit)")
print("  Which encodes to consecutive 'f' characters in bech32")
print("\nFor Base58 addresses, the character patterns do NOT create")
print("simple repeating byte patterns like bech32 does.")
print("Base58 uses 6-bit-ish encoding where each char = value 0-57,")
print("so 'X' repeating in 1EaterXXX... or 1BurnBurn... creates")
print("a different kind of pattern in the underlying bytes.")
