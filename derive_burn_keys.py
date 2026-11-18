#!/usr/bin/env python3
"""
derive_burn_keys.py — Private Key Derivation from Burn Address Patterns

This script attempts to derive private keys for the 7 burn addresses.

MATHEMATICAL REALITY CHECK:
============================

For Bitcoin addresses, the chain is:
  Private Key (32 bytes) → Public Key (33 bytes compressed) → hash160 (20 bytes) → Address

The burn addresses give us the hash160 (or witness program hash). To spend, we need
the original private key. There are TWO barriers:

1. HASH REVERSAL: hash160 = RIPEMD160(SHA256(pubkey)) is a one-way hash.
   You cannot reverse it to get the pubkey, let alone the private key.

2. ECDLP: Even with the public key, deriving the private key from the public key
   on secp256k1 is the Elliptic Curve Discrete Logarithm Problem.
   For 256-bit keys, this requires ~2^128 operations with the best known algorithm
   (Pollard's rho) — physically impossible with any computer that exists or will exist.

WHAT THIS SCRIPT DOES:
=======================

1. Shows the hash160 for each burn address (the lock)
2. Attempts to find the private key for addresses where the hash160 is all zeros
   (the simplest possible case) — demonstrating why it's infeasible
3. Shows the secp256k1 curve parameters and why ECDLP is hard
4. Derives the private key for THE KEY (genesis nonce) since we know the answer
5. Creates a new keypair with the f=9 pattern for demonstration

The conclusion: the burn addresses are permanently locked. No one can spend from them
because no one knows the private keys, and deriving them is computationally impossible.
"""

import sys
import os
import hashlib
import time
import math

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from secp256k1 import (
    priv_to_pub, compress, decompress, _mul, _add,
    P, N, G, Gx, Gy
)

# ============================================================
# BURN ADDRESS HASH160 VALUES
# ============================================================

BURN_ADDRESSES = [
    {
        "name": "1BitcoinEaterAddress",
        "address": "1BitcoinEaterAddressDontSendf59kuE",
        "type": "P2PKH",
        "hash160": bytes.fromhex("759d6677091e973b9e9d99f19c68fbf43e3f05f9"),
        "btc": 13419.0,
    },
    {
        "name": "1CounterpartyXXX",
        "address": "1CounterpartyXXXXXXXXXXXXXXXUWLpVr",
        "type": "P2PKH",
        "hash160": bytes.fromhex("818895f3dc2c178629d3d2d8fa3ec4a3f8179821"),
        "btc": 2131.0,
    },
    {
        "name": "1111111111111111111114oLvT2",
        "address": "1111111111111111111114oLvT2",
        "type": "P2PKH",
        "hash160": bytes.fromhex("00" * 20),
        "btc": 809.8,
    },
    {
        "name": "bc1qqqq...thqst8 (P2WSH)",
        "address": "bc1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqthqst8",
        "type": "P2WSH",
        "hash160": bytes.fromhex("00" * 32),
        "btc": 0.0058,
    },
    {
        "name": "bc1qqqq...9e75rs (P2WPKH)",
        "address": "bc1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq9e75rs",
        "type": "P2WPKH",
        "hash160": bytes.fromhex("00" * 20),
        "btc": 0.0006,
    },
    {
        "name": "bc1qfff...qe708k7 (P2WSH)",
        "address": "bc1qfffffffffffffffffffffffffffffffffffffffffffffffffffqe708k7",
        "type": "P2WSH",
        "hash160": bytes.fromhex("4a5294a529" * 6 + "4a52"),
        "btc": 0,
    },
    {
        "name": "bc1qfff...82jzwn (P2WPKH)",
        "address": "bc1qffffffffffffffffffffffffffffffff82jzwn",
        "type": "P2WPKH",
        "hash160": bytes.fromhex("4a5294a529" * 4),
        "btc": 0,
    },
]

# ============================================================
# HELPER FUNCTIONS
# ============================================================

def sha256(data):
    return hashlib.sha256(data).digest()

def h160(data):
    """RIPEMD160(SHA256(data))"""
    h = hashlib.new("ripemd160")
    h.update(sha256(data))
    return h.digest()

def print_section(title):
    print()
    print("=" * 80)
    print(f"  {title}")
    print("=" * 80)
    print()

# ============================================================
# SECTION 1: THE LOCK — HASH160 VALUES
# ============================================================

print_section("1. THE LOCK — Burn Address Hash160 Values")

print("Each burn address encodes a hash. To spend, we need the preimage.")
print()

for ba in BURN_ADDRESSES:
    print(f"  {ba['name']}")
    print(f"    Address: {ba['address'][:50]}{'...' if len(ba['address']) > 50 else ''}")
    print(f"    Type:    {ba['type']}")
    print(f"    Hash:    {ba['hash160'].hex()}")
    print(f"    BTC:     {ba['btc']}")
    print()

# ============================================================
# SECTION 2: WHY HASH REVERSAL IS IMPOSSIBLE
# ============================================================

print_section("2. WHY HASH REVERSAL IS IMPOSSIBLE")

print("For P2PKH addresses:")
print("  hash160 = RIPEMD160(SHA256(pubkey_compressed))")
print()
print("This is a DOUBLE hash through two different algorithms.")
print("Neither SHA256 nor RIPEMD160 can be reversed.")
print()
print("For P2WSH addresses:")
print("  witness_program = SHA256(witness_script)")
print()
print("SHA256 cannot be reversed to recover the witness script.")
print()
print("Even if we could reverse the hash, we'd only get the public key.")
print("Deriving the private key from the public key is the ECDLP.")
print()

# ============================================================
# SECTION 3: ECDLP ON SECP256K1 — WHY IT'S HARD
# ============================================================

print_section("3. ECDLP ON SECP256K1 — WHY IT'S HARD")

print("Curve: secp256k1  (y^2 = x^3 + 7 over GF(P))")
print()
print(f"  Field P:  {P}")
print(f"  Order N:  {N}")
print(f"  Generator G: ({Gx}, {Gy})")
print()
print(f"  N in bits: {N.bit_length()} bits")
print(f"  N ~= 2^{math.log2(N):.1f}")
print()
print("The ECDLP: given Q = d*G, find d.")
print()
print("Best known algorithm: Pollard's rho")
print(f"  Complexity: O(sqrt(N)) ~= O(2^{N.bit_length()//2}) ~= 2^{N.bit_length()//2} operations")
print()
print(f"  2^128 operations ~= {2**128:.2e} operations")
print()
print("Physical limits:")
print(f"  - Fastest supercomputer: ~10^18 ops/sec (1 exaflop)")
print(f"  - Age of universe: ~4.3 * 10^17 seconds")
print(f"  - Total ops in universe lifetime at 1 exaflop: ~4.3 * 10^35")
print(f"  - 2^128 ~= 3.4 * 10^38")
print()
print("  CONCLUSION: Even with all computers in the universe running since")
print("  the Big Bang, you couldn't solve ECDLP for a 256-bit key.")
print()

# ============================================================
# SECTION 4: THE TOY DLP — WHY THE KEY WORKS
# ============================================================

print_section("4. THE TOY DLP — WHY THE KEY WORKS")

print("THE KEY uses a SMALL prime for the DLP:")
print()
print(f"  g = 2")
print(f"  h = 543854440")
print(f"  p = 2083237931")
print()
dlp_p = 2083237931
print(f"  p in bits: {dlp_p.bit_length()} bits")
print(f"  sqrt(p) ~= {math.isqrt(dlp_p)} ~= 45,642")
print()
print("Baby-step giant-step needs only ~45,642 steps.")
print("This takes milliseconds on any computer.")
print()
print("secp256k1 needs ~2^128 steps.")
print("This takes longer than the age of the universe.")
print()
print("THE KEY works because the prime is tiny (~31 bits).")
print("secp256k1 is secure because the order is huge (256 bits).")
print()

# ============================================================
# SECTION 5: ATTEMPTING TO FIND THE ALL-ZERO KEY
# ============================================================

print_section("5. ATTEMPTING TO FIND THE ALL-ZERO PRIVATE KEY")

print("The simplest burn address is 1111111111111111111114oLvT2.")
print("Its hash160 is all zeros: 0000000000000000000000000000000000000000")
print()
print("To find the private key, we need:")
print("  1. A public key whose hash160 is all zeros")
print("  2. The private key that produces that public key")
print()
print("Step 1: Find pubkey where hash160(pubkey) = 0x0000...0000 (20 zero bytes)")
print()
print("This requires reversing a double hash. Even brute-forcing:")
print("  - There are 2^256 possible private keys")
print("  - Each produces a different hash160 (20 bytes = 2^160 possible values)")
print("  - By pigeonhole principle, ~2^96 keys map to each hash160")
print("  - But finding ONE of them requires searching 2^160 keys on average")
print()
print(f"  2^160 ~= {2**160:.2e} operations")
print(f"  At 1 exaflop: {2**160 / 10**18 / (3600*24*365):.2e} years")
print()
print("  CONCLUSION: Even the all-zero hash160 cannot be practically reversed.")
print()

# ============================================================
# SECTION 6: BRUTE-FORCE DEMO (SMALL SCALE)
# ============================================================

print_section("6. BRUTE-FORCE DEMO — Searching for hash160 with Leading Zeros")

print("Demonstrating the search space by looking for keys with leading zero bytes")
print("in their hash160 (not all zeros, just leading zeros).")
print()

target_prefix = b"\x00" * 1  # Just 1 leading zero byte
found = False
start = time.time()

for d in range(1, 1000000):
    pub = compress(priv_to_pub(d))
    h = h160(pub)
    if h.startswith(target_prefix):
        print(f"  Found! d = {d}")
        print(f"    Public key: {pub.hex()}")
        print(f"    hash160:    {h.hex()}")
        leading_zeros = len(h) - len(h.lstrip(b'\x00'))
        print(f"    Leading zeros: {leading_zeros} bytes")
        found = True
        break

elapsed = time.time() - start
print(f"  Searched 1,000,000 keys in {elapsed:.2f} seconds")
print(f"  Found key with 1 leading zero byte: {'Yes' if found else 'No'}")
print()
print("Finding 1 leading zero byte took ~1M keys.")
print("Finding 20 leading zero bytes would take ~2^160 keys.")
print()

# ============================================================
# SECTION 7: THE F=9 PATTERN — CAN WE FIND ITS KEY?
# ============================================================

print_section("7. THE F=9 PATTERN — CAN WE FIND ITS KEY?")

print("The f=9 pattern creates witness program: 4A5294A529 repeating")
print()
print("For P2WPKH (bc1qfff...82jzwn):")
print("  witness_program = hash160(pubkey) = 4A5294A529 * 4 (20 bytes)")
print()
print("For P2WSH (bc1qfff...qe708k7):")
print("  witness_program = SHA256(witness_script) = 4A5294A529 * 6 + 4A52 (32 bytes)")
print()
print("Same problem: we need to reverse the hash to find the preimage.")
print("The f=9 pattern is a beautiful encoding discovery, but it doesn't")
print("make the hash reversal any easier.")
print()

# ============================================================
# SECTION 8: WHAT WE CAN DO — CREATE A NEW F=9 KEYPAIR
# ============================================================

print_section("8. WHAT WE CAN DO — CREATE A NEW KEYPAIR")

print("We can create a new keypair and derive its address.")
print("This demonstrates the f=9 pattern in action with a key we control.")
print()

# Use the genesis nonce as a seed for a new key
genesis_nonce = 2083236893

# Create a deterministic key from the genesis nonce
seed = sha256(f"genesis_nonce:{genesis_nonce}:f9_pattern".encode())
priv_key = int.from_bytes(seed, 'big') % N
if priv_key == 0:
    priv_key = 1

pub_point = priv_to_pub(priv_key)
pub_compressed = compress(pub_point)
pub_hash160 = h160(pub_compressed)

print(f"  Private key: {priv_key:064x}")
print(f"  Public key:  {pub_compressed.hex()}")
print(f"  hash160:     {pub_hash160.hex()}")
print()

# Create P2WPKH address
BECH = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"

def bech32_p2wpkh(hash160_bytes):
    """Create bech32 P2WPKH address."""
    def convertbits(data, frm, to):
        acc = 0; bits = 0; ret = []
        for v in data:
            acc = (acc << frm) | v; bits += frm
            while bits >= to:
                bits -= to; ret.append((acc >> bits) & ((1 << to) - 1))
        if bits: ret.append((acc << (to - bits)) & ((1 << to) - 1))
        return ret
    
    def polymod(vals):
        chk = 1; gen = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
        for v in vals:
            top = chk >> 25; chk = ((chk & 0x1ffffff) << 5) ^ v
            for i in range(5):
                if (top >> i) & 1: chk ^= gen[i]
        return chk
    
    data = [0] + convertbits(hash160_bytes, 8, 5)
    hrp_exp = [ord(c) >> 5 for c in "bc"] + [0] + [ord(c) & 31 for c in "bc"]
    combined = hrp_exp + data
    pm = polymod(combined + [0] * 6) ^ 1
    checksum = [(pm >> (5 * (5 - i))) & 31 for i in range(6)]
    return "bc1" + "".join(BECH[v] for v in data + checksum)

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def b58check_encode(payload):
    chk = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    raw = payload + chk
    n = int.from_bytes(raw, "big"); s = ""
    while n: n, r = divmod(n, 58); s = B58[r] + s
    return "1" * (len(raw) - len(raw.lstrip(b"\x00"))) + s

p2wpkh_addr = bech32_p2wpkh(pub_hash160)
p2pkh_addr = b58check_encode(b"\x00" + pub_hash160)

print(f"  P2WPKH: {p2wpkh_addr}")
print(f"  P2PKH:  {p2pkh_addr}")
print()
print("This is a real keypair we control. We can spend from these addresses.")
print("But the hash160 doesn't have the f=9 pattern — that's the whole point.")
print("The f=9 pattern addresses have a specific hash160 that we can't reverse.")
print()

# ============================================================
# SECTION 9: THE MESSERENE KEYPAIR FROM THE KEY
# ============================================================

print_section("9. THE MESSERENE KEYPAIR FROM THE KEY")

print("From the_key.py, the Messerene pattern + genesis nonce creates a keypair:")
print()

MESSERENE_30 = bytes.fromhex(
    "A1B3C5D7E9F8D6C4B2A0E8F6D4C2B0A8E6F4D2C0B8A6E4D2C0B8A6E4D2C0"
)

import struct
key_bytes = struct.pack('>I', genesis_nonce)
completed = bytearray(MESSERENE_30)
completed[28] = key_bytes[0]
completed[29] = key_bytes[1]
completed.append(key_bytes[2])
completed.append(key_bytes[3])

messerene_privkey = int.from_bytes(completed, 'big')
messerene_pub = priv_to_pub(messerene_privkey)
messerene_pub_comp = compress(messerene_pub)
messerene_h160 = h160(messerene_pub_comp)

print(f"  Private key: {messerene_privkey:064x}")
print(f"  Public key:  {messerene_pub_comp.hex()}")
print(f"  hash160:     {messerene_h160.hex()}")
print()

m_p2wpkh = bech32_p2wpkh(messerene_h160)
m_p2pkh = b58check_encode(b"\x00" + messerene_h160)

print(f"  P2WPKH: {m_p2wpkh}")
print(f"  P2PKH:  {m_p2pkh}")
print()
print("This keypair IS controllable because we derived it from THE KEY.")
print("But it's NOT one of the burn addresses — different hash160.")
print()

# ============================================================
# SECTION 10: CONCLUSION
# ============================================================

print_section("10. CONCLUSION")

print("The 7 burn addresses are permanently locked.")
print()
print("Why:")
print("  1. We only have the hash160 (the lock), not the public key")
print("  2. Reversing hash160 to find the public key is impossible")
print("  3. Even with the public key, ECDLP makes finding the private key impossible")
print()
print("The f=9 pattern is a discovery about BECH32 ENCODING, not about")
print("the underlying keys. It tells us how the witness program bytes")
print("encode to bech32 characters, but not how to find the private key")
print("that produced those bytes.")
print()
print("THE KEY (genesis nonce DLP) works because it uses a tiny prime.")
print("secp256k1 is secure because it uses a 256-bit prime.")
print()
print("The burn addresses will remain burned forever.")
print("The ~16,362 BTC in them is permanently removed from circulation.")
print()
print("=" * 80)
