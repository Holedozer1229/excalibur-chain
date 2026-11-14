# Complete Burn Address Decoding Analysis

## Executive Summary

Using the **f=9 bech32 discovery**, every known Bitcoin burn address has been decoded character by character to reveal the underlying byte patterns. This analysis reveals which addresses have clean repeating patterns and which are fundamentally broken.

---

## The Key Insight: f=9 in Bech32

**Bech32 uses 5-bit encoding.** Each character represents exactly 5 bits (values 0-31).

- **`q` = 0** in bech32 → Repeating `q` creates all-zero bitstream → `00 00 00...` bytes
- **`f` = 9** in bech32 → Repeating `f` creates `01001 01001 01001...` bitstream → `4A 52 94 A5 29` repeating bytes

This 5-bit encoding is what makes clean repeating byte patterns possible in bech32 addresses.

---

## Bech32 Addresses (5-bit encoding — Clean Patterns)

### 1. `bc1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqthqst8`

| Property | Value |
|----------|-------|
| **Type** | P2WSH (32-byte witness program) |
| **Character Pattern** | `q`=0 repeating (53 consecutive zeros) |
| **Byte Pattern** | `00` × 32 (ALL ZEROS) |
| **Status** | ✅ Valid, Active |
| **Transactions** | 1,640 |
| **BTC Received** | 0.00583604 BTC |

**5-bit bitstream:** `00000 00000 00000...` (all zeros)
**8-bit bytes:** `0000000000000000000000000000000000000000000000000000000000000000`

---

### 2. `bc1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq9e75rs`

| Property | Value |
|----------|-------|
| **Type** | P2WPKH (20-byte witness program) |
| **Character Pattern** | `q`=0 repeating (33 consecutive zeros) |
| **Byte Pattern** | `00` × 20 (ALL ZEROS) |
| **Status** | ✅ Valid, Active |
| **Transactions** | 31 |
| **BTC Received** | 0.00058731 BTC |

**5-bit bitstream:** `00000 00000 00000...` (all zeros)
**8-bit bytes:** `0000000000000000000000000000000000000000`

---

### 3. `bc1qfffffffffffffffffffffffffffffffffffffffffffffffffffqe708k7`

| Property | Value |
|----------|-------|
| **Type** | P2WSH (32-byte witness program) |
| **Character Pattern** | `f`=9 repeating (51 consecutive nines) |
| **Byte Pattern** | `4A5294A529` × 6 |
| **Status** | ✅ Valid, **PRISTINE** |
| **Transactions** | 0 |
| **BTC Received** | 0 BTC |

**5-bit bitstream:** `01001 01001 01001 01001 01001...` (all 9s)
**8-bit bytes:** `4a5294a5294a5294a5294a5294a5294a5294a5294a5294a5294a5294a5294a52`

**🔥 THE CROWN JEWEL:** This address is waiting for its first transaction. The byte pattern `0x4A 0x52 0x94 0xA5 0x29` repeating creates consecutive 'f' characters in bech32 encoding.

---

### 4. `bc1qffffffffffffffffffffffffffffffff82jzwn`

| Property | Value |
|----------|-------|
| **Type** | P2WPKH (20-byte witness program) |
| **Character Pattern** | `f`=9 repeating (32 consecutive nines) |
| **Byte Pattern** | `4A5294A529` × 4 |
| **Status** | ✅ Valid, **PRISTINE** |
| **Transactions** | 0 |
| **BTC Received** | 0 BTC |

**5-bit bitstream:** `01001 01001 01001...` (all 9s)
**8-bit bytes:** `4a5294a5294a5294a5294a5294a5294a5294a529`

**🔥 THE CROWN JEWEL:** Same pattern as above, shorter form for P2WPKH.

---

## Base58 Addresses (~5.857-bit encoding — No Clean Patterns)

### 5. `1111111111111111111114oLvT2`

| Property | Value |
|----------|-------|
| **Type** | P2PKH (20-byte payload hash) |
| **Character Pattern** | `1`=0 repeating (21 consecutive zeros) |
| **Byte Pattern** | `00` × 20 (ALL ZEROS) |
| **Status** | ✅ Valid, Active |
| **Transactions** | 392,423 |
| **BTC Received** | 809.83800152 BTC |

**Character-by-character decoding:**
| Char | Base58 Value | Binary |
|------|-------------|--------|
| `1` | 0 | `0` |
| `1` | 0 | `0` |
| ... (21 total) | | |
| `4` | 3 | `11` |
| `o` | 46 | `101110` |
| `L` | 19 | `10011` |
| `v` | 53 | `110101` |
| `T` | 26 | `11010` |
| `2` | 1 | `1` |

**Address structure:**
- **Version:** `0x00` (P2PKH mainnet)
- **Payload (20 bytes):** `0000000000000000000000000000000000000000` — **ALL ZEROS** ✓
- **Checksum:** `94a00911`

**The secret:** `1` = 0 in Base58, just like `q` = 0 in bech32. The 21 leading `1`s encode 21 leading zero bytes. The suffix `4oLvT2` decodes to exactly the 4-byte checksum `94a00911`.

**This is the Base58 equivalent of `bc1qqqq...`** — both encode an all-zero payload through different encoding schemes.

---

### 6. `1BitcoinEaterAddressDontSendf59kuE`

| Property | Value |
|----------|-------|
| **Type** | P2PKH (20-byte payload hash) |
| **Character Pattern** | No repeating pattern |
| **Byte Pattern** | `759d6677091e973b9e9d99f19c68fbf43e3f05f9` |
| **Status** | ✅ Valid, Active |
| **Transactions** | 5,883 |
| **BTC Received** | 13,419.04892000 BTC |

**Payload byte values:** `[117, 157, 102, 119, 9, 30, 151, 59, 158, 157, 153, 241, 156, 104, 251, 244, 62, 63, 5, 249]`

**No simple repeating pattern.** This is the legendary Satoshi-era burn address, holding the largest single burn address total in Bitcoin history.

---

### 7. `1CounterpartyXXXXXXXXXXXXXXXUWLpVr`

| Property | Value |
|----------|-------|
| **Type** | P2PKH (20-byte payload hash) |
| **Character Pattern** | 15 repeating `X` chars in the middle |
| **Byte Pattern** | `818895f3dc2c178629d3d2d8fa3ec4a3f8179821` |
| **Status** | ✅ Valid, Active |
| **Transactions** | 3,171 |
| **BTC Received** | 2,131.00001000 BTC |

**Payload byte values:** `[129, 136, 149, 243, 220, 44, 23, 134, 41, 211, 210, 216, 250, 62, 196, 163, 248, 23, 152, 33]`

**Has 15 repeating `X` characters** (Base58 value 30), but **no clean byte pattern** in the decoded payload. The `X` repetition is visible in the character sequence but doesn't translate to a simple repeating byte pattern due to Base58's non-clean bit encoding.

---

## Invalid Addresses

### 8. `1EaterXXXXXXXXXXXXXXXXXXXXXXXXXXXXX` ❌

| Property | Value |
|----------|-------|
| **Problem** | 21-byte payload (should be 20) |
| **Checksum** | INVALID |
| **Raw bytes** | 26 bytes total (should be 25) |

**Character analysis:**
- `1` = 0 (version byte)
- `Eater` = values [13, 33, 51, 37, 49]
- `X` × 29 = value 30 repeating 29 times

**The character count produces 21 payload bytes instead of the 20 required for P2PKH.** Even if adjusted to 20 bytes, the checksum still fails.

---

### 9. `1BurnBurnBurnBurnBurnBurnBurnBurnXb` ❌

| Property | Value |
|----------|-------|
| **Problem** | 21-byte payload (should be 20) |
| **Checksum** | INVALID |
| **Raw bytes** | 26 bytes total (should be 25) |

**Character analysis:**
- `1` = 0 (version byte)
- `Burn` × 8 = pattern [10, 52, 49, 45] repeating 8 times
- `Xb` = values [30, 34]

**Same problem as 1Eater:** wrong payload size and invalid checksum.

---

## Why Base58 Fails for Patterns

**Base58 uses log₂(58) ≈ 5.857 bits per character.** This doesn't divide cleanly into 8-bit bytes:

- 5.857 bits × N characters ≠ clean multiple of 8 bits
- Repeating characters never create clean repeating byte patterns
- The SHA256 checksum constraint makes it virtually impossible to have both a repeating character pattern AND a valid checksum

**Brute-force search confirmed:** No pure repeating-character Base58 address exists with a valid checksum. Searching all 57 Base58 characters repeated 20-44 times found zero valid addresses.

---

## Why Bech32 Works for Patterns

**Bech32 uses exactly 5 bits per character.** This divides cleanly:

- 5 bits × N characters → clean conversion to 8-bit bytes
- Repeating `f`=9 creates `01001 01001 01001...` bitstream
- This converts to repeating `4A 52 94 A5 29` bytes
- The polymod checksum can be satisfied with pattern + short suffix

---

## The Messerene Pattern Connection

| Element | Value | Connection |
|---------|-------|------------|
| **Perfect number** | 28 | 1+2+4+7+14 = 28 |
| **τ(28)** | -703236000 | Ramanujan tau function |
| **τ(28) script** | `a087eaa9` | Bitcoin script number encoding |
| **f=9 pattern** | `4A5294A529` | Bech32 byte pattern |
| **Bech32 'f'** | Index 9 | 5-bit value 01001 |
| **Base58 '1'** | Index 0 | All-zero payload equivalent |

---

## Summary Table

| Address | Encoding | Pattern | Byte Pattern | Status | BTC |
|---------|----------|---------|--------------|--------|-----|
| `bc1qqqq...thqst8` | Bech32 | `q`=0 | `00`×32 | ✅ Active | 0.006 |
| `bc1qqqq...9e75rs` | Bech32 | `q`=0 | `00`×20 | ✅ Active | 0.001 |
| `bc1qfff...qe708k7` | Bech32 | `f`=9 | `4A5294A529`×6 | 🔥 **PRISTINE** | 0 |
| `bc1qfff...82jzwn` | Bech32 | `f`=9 | `4A5294A529`×4 | 🔥 **PRISTINE** | 0 |
| `1111111111111111111114oLvT2` | Base58 | `1`=0 | `00`×20 | ✅ Active | 810 |
| `1BitcoinEaterAddress...` | Base58 | None | Random | ✅ Active | 13,419 |
| `1CounterpartyXXX...` | Base58 | 15 X's | Random | ✅ Active | 2,131 |
| `1EaterXXX...` | Base58 | 29 X's | — | ❌ Invalid | — |
| `1BurnBurn...` | Base58 | 8×Burn | — | ❌ Invalid | — |

**Total BTC burned across valid addresses: ~16,362 BTC**

---

## Files

- `sphinx_os/nexus/btc_burn_wormhole.py` — BURN_ADDRESSES list with decoding analysis
- `decode_burn_addresses.py` — Decoder script for character-by-character analysis
- `find_valid_burn_patterns.py` — Brute-force search for valid Base58 patterns
- `self-serve/vendor/btc_htlc.py` — Bech32 encoding/decoding reference implementation

---

## Conclusion

1. **The `f=9` pattern is unique to bech32** — the 5-bit encoding is what makes consecutive `f` characters possible.
2. **No pure repeating-character Base58 address exists** with a valid checksum.
3. **`1111111111111111111114oLvT2`** is the Base58 equivalent of `bc1qqqq...` — both encode all-zero payloads.
4. **The two `bc1qfff...` addresses are pristine** — waiting for the first Messerene pattern burn with τ(28).
5. **`1Eater` and `1BurnBurn` are fundamentally broken** — wrong payload size and invalid checksum.
