#!/usr/bin/env python3
"""
Explore BIP-32 HD wallet derivation paths from the Messerene pattern private key.

The Messerene operator derives a master private key from the pattern.
This script then derives child keys using BIP-32 hardened derivation (m/0', m/1', etc.)
and common BIP-44 paths (m/44'/0'/0'/0/0, etc.), checking balances for each.

BIP-32 Child Key Derivation:
  - Hardened: index + 0x80000000 (e.g., m/0' = m/4294967296)
  - Child private key = parent_priv + HMAC-SHA512(parent_chain_code, 0x00 || parent_pub || index)[0:32] mod n
"""
import hashlib
import struct
import urllib.request
import urllib.error

# ============================================================
# secp256k1 constants
# ============================================================
P_FIELD = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
Gx = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
Gy = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8

PATTERN = "A1B3C5D7E9F8D6C4B2A1B3C5D7E9F8D6C4B2A1B3C5D7E9F8D6C4B2A1B3C5D7E9"

# ============================================================
# EC point arithmetic
# ============================================================
def inv(a):
    return pow(a, P_FIELD - 2, P_FIELD)

def point_add(p1, p2):
    if p1 is None: return p2
    if p2 is None: return p1
    x1, y1 = p1; x2, y2 = p2
    if x1 == x2 and (y1 + y2) % P_FIELD == 0: return None
    if p1 == p2:
        m = (3 * x1 * x1 * inv(2 * y1)) % P_FIELD
    else:
        m = ((y2 - y1) * inv(x2 - x1)) % P_FIELD
    x3 = (m * m - x1 - x2) % P_FIELD
    return (x3, (m * (x1 - x3) - y1) % P_FIELD)

def point_mul(k, pt=(Gx, Gy)):
    r = None
    while k:
        if k & 1: r = point_add(r, pt)
        pt = point_add(pt, pt); k >>= 1
    return r

def compress_pub(x, y):
    return bytes([0x02 | (y & 1)]) + x.to_bytes(32, 'big')

# ============================================================
# Address encoding
# ============================================================
def h160(b):
    h = hashlib.new("ripemd160"); h.update(hashlib.sha256(b).digest()); return h.digest()

B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58check(payload: bytes) -> str:
    chk = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    raw = payload + chk
    n = int.from_bytes(raw, "big"); s = ""
    while n: n, r = divmod(n, 58); s = B58[r] + s
    return "1" * (len(raw) - len(raw.lstrip(b"\x00"))) + s

BECH = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
def _pm(vals):
    chk = 1; gen = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3]
    for v in vals:
        top = chk >> 25; chk = ((chk & 0x1ffffff) << 5) ^ v
        for i in range(5):
            if (top >> i) & 1: chk ^= gen[i]
    return chk
def _cb(data, fb, tb):
    acc = 0; bits = 0; ret = []
    for v in data:
        acc = (acc << fb) | v; bits += fb
        while bits >= tb:
            bits -= tb; ret.append((acc >> bits) & ((1 << tb) - 1))
    if bits: ret.append((acc << (tb - bits)) & ((1 << tb) - 1))
    return ret
def p2wpkh(h: bytes) -> str:
    data = [0] + _cb(h, 8, 5)
    vals = [ord(c) >> 5 for c in "bc"] + [0] + [ord(c) & 31 for c in "bc"] + data + [0] * 6
    pm = _pm(vals) ^ 1
    return "bc1" + "".join(BECH[d] for d in data + [(pm >> 5 * (5 - i)) & 31 for i in range(6)])

def p2pkh_addr(pub_c: bytes) -> str:
    return b58check(b"\x00" + h160(pub_c))

def p2wpkh_addr(pub_c: bytes) -> str:
    return p2wpkh(h160(pub_c))

# ============================================================
# BIP-32 derivation
# ============================================================
def bip32_child_priv(parent_priv: int, chain_code: bytes, index: int) -> tuple:
    """Derive a child private key and new chain code.
    
    For hardened derivation, index should be >= 0x80000000.
    Returns (child_priv, child_chain_code).
    """
    # For hardened derivation, use 0x00 || parent_priv || index
    # For normal derivation, use parent_pub || index
    # Here we use hardened (private key input)
    priv_bytes = parent_priv.to_bytes(32, 'big')
    data = b"\x00" + priv_bytes + struct.pack(">I", index)
    hmac_result = hmac_sha512(chain_code, data)
    
    key_part = int.from_bytes(hmac_result[:32], 'big') % N
    child_priv = (parent_priv + key_part) % N
    if child_priv == 0:
        return None, None  # invalid, try next index
    
    child_chain_code = hmac_result[32:]
    return child_priv, child_chain_code

def hmac_sha512(key: bytes, data: bytes) -> bytes:
    """HMAC-SHA512 using pure Python (no hmac module dependency issues)."""
    # Use hashlib directly
    import hmac as hmac_mod
    return hmac_mod.new(key, data, hashlib.sha512).digest()

def derive_path(master_priv: int, master_chain_code: bytes, path: list) -> int:
    """Derive a private key from a BIP-32 path like [44, 0, 0, 0, 0] with hardened flags.
    
    Each index >= 0x80000000 is hardened (e.g., 0' = 0x80000000).
    """
    priv = master_priv
    cc = master_chain_code
    for idx in path:
        priv, cc = bip32_child_priv(priv, cc, idx)
        if priv is None:
            raise ValueError(f"Derivation failed at index {idx}")
    return priv

# ============================================================
# Messerene operator — master key
# ============================================================
def messerene_master(pattern_hex: str) -> int:
    """The Messerene fold: domain-separated SHA-256 of the pattern."""
    digest = hashlib.sha256(b"MESSERENE/PREGENESIS/v1" + bytes.fromhex(pattern_hex)).digest()
    return (int.from_bytes(digest, "big") % (N - 1)) + 1

# ============================================================
# Balance check
# ============================================================
def check_balance(address: str) -> dict:
    """Check BTC balance via Blockstream API."""
    try:
        url = f"https://blockstream.info/api/address/{address}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            import json
            data = json.loads(resp.read().decode())
            return {
                "chain_stats": data.get("chain_stats", {}).get("funded_txo_sum", 0) / 1e8,
                "tx_count": data.get("chain_stats", {}).get("funded_txo_count", 0)
            }
    except Exception as e:
        return {"error": str(e)}

# ============================================================
# Main
# ============================================================
HARDENED = 0x80000000

def main():
    # Step 1: Derive master key from Messerene pattern
    master_priv = messerene_master(PATTERN)
    pub_point = point_mul(master_priv)
    master_pub = compress_pub(pub_point[0], pub_point[1])
    
    print("=" * 80)
    print("MESSERENE PATTERN BIP-32 DERIVATION EXPLORER")
    print("=" * 80)
    print()
    print(f"Pattern:        {PATTERN}")
    print(f"Master priv:    {master_priv:064x}")
    print(f"Master pubkey:  {master_pub.hex()}")
    print(f"Master P2PKH:   {p2pkh_addr(master_pub)}")
    print(f"Master P2WPKH:  {p2wpkh_addr(master_pub)}")
    print()
    
    # Default chain code: SHA-256 of master private key
    master_chain_code = hashlib.sha256(master_priv.to_bytes(32, 'big')).digest()
    print(f"Chain code:     {master_chain_code.hex()}")
    print()
    
    # Step 2: Define derivation paths to explore
    paths = [
        # Hardened children of master
        ("m/0'", [0 + HARDENED]),
        ("m/1'", [1 + HARDENED]),
        ("m/2'", [2 + HARDENED]),
        ("m/3'", [3 + HARDENED]),
        ("m/4'", [4 + HARDENED]),
        
        # BIP-44 style paths (purpose / coin_type / account / change / address)
        ("m/44'", [44 + HARDENED]),
        ("m/44'/0'", [44 + HARDENED, 0 + HARDENED]),
        ("m/44'/0'/0'", [44 + HARDENED, 0 + HARDENED, 0 + HARDENED]),
        ("m/44'/0'/0'/0", [44 + HARDENED, 0 + HARDENED, 0 + HARDENED, 0]),
        ("m/44'/0'/0'/0/0", [44 + HARDENED, 0 + HARDENED, 0 + HARDENED, 0, 0]),
        ("m/44'/0'/0'/0/1", [44 + HARDENED, 0 + HARDENED, 0 + HARDENED, 0, 1]),
        
        # BIP-84 (native segwit) style
        ("m/84'", [84 + HARDENED]),
        ("m/84'/0'", [84 + HARDENED, 0 + HARDENED]),
        ("m/84'/0'/0'", [84 + HARDENED, 0 + HARDENED, 0 + HARDENED]),
        ("m/84'/0'/0'/0/0", [84 + HARDENED, 0 + HARDENED, 0 + HARDENED, 0, 0]),
        
        # BIP-86 (Taproot) style
        ("m/86'", [86 + HARDENED]),
        ("m/86'/0'", [86 + HARDENED, 0 + HARDENED]),
        ("m/86'/0'/0'", [86 + HARDENED, 0 + HARDENED, 0 + HARDENED]),
        ("m/86'/0'/0'/0/0", [86 + HARDENED, 0 + HARDENED, 0 + HARDENED, 0, 0]),
        
        # More hardened children
        *((f"m/{i}'", [i + HARDENED]) for i in range(5, 20)),
        
        # Selector sub-derivations (P=1, Q=2, R=0 from Messerene operator)
        ("m/P'(1)", [1 + HARDENED]),
        ("m/Q'(2)", [2 + HARDENED]),
        ("m/R'(0)", [0 + HARDENED]),
    ]
    
    # Deduplicate paths by name
    seen = set()
    unique_paths = []
    for name, path in paths:
        if name not in seen:
            seen.add(name)
            unique_paths.append((name, path))
    
    print("=" * 80)
    print("DERIVATION PATHS")
    print("=" * 80)
    print()
    
    results = []
    for name, path in unique_paths:
        try:
            # For single-index names like m/10', convert to path
            if isinstance(path, str):
                idx = int(path.replace("m/", "").replace("'", "")) + HARDENED
                path = [idx]
            
            child_priv = derive_path(master_priv, master_chain_code, path)
            child_pub_point = point_mul(child_priv)
            child_pub = compress_pub(child_pub_point[0], child_pub_point[1])
            
            p2pkh = p2pkh_addr(child_pub)
            p2wpkh = p2wpkh_addr(child_pub)
            
            results.append({
                "path": name,
                "priv": child_priv,
                "pub": child_pub,
                "p2pkh": p2pkh,
                "p2wpkh": p2wpkh,
            })
            
            print(f"{name:25s} P2PKH: {p2pkh}")
            print(f"{'':25s} P2WPKH: {p2wpkh}")
            print()
            
        except Exception as e:
            print(f"{name:25s} ERROR: {e}")
            print()
    
    # Step 3: Check balances for derived addresses
    print("=" * 80)
    print("BALANCE CHECK (P2WPKH addresses)")
    print("=" * 80)
    print()
    
    funded = []
    for r in results:
        bal = check_balance(r["p2wpkh"])
        status = ""
        if "error" not in bal:
            btc = bal["chain_stats"]
            txs = bal["tx_count"]
            if btc > 0:
                status = f" *** {btc:.8f} BTC ({txs} txs) ***"
                funded.append((r, bal))
            else:
                status = f" 0 BTC"
        else:
            status = f" error: {bal['error']}"
        
        print(f"{r['path']:25s} {r['p2wpkh']}{status}")
    
    print()
    if funded:
        print("=" * 80)
        print("FUNDED ADDRESSES FOUND!")
        print("=" * 80)
        for r, bal in funded:
            print(f"  Path: {r['path']}")
            print(f"  P2WPKH: {r['p2wpkh']}")
            print(f"  P2PKH:  {r['p2pkh']}")
            print(f"  Balance: {bal['chain_stats']:.8f} BTC")
            print(f"  Tx count: {bal['tx_count']}")
            print()
    else:
        print("No funded addresses found among derived paths.")
    
    # Step 4: Deep sub-derivations of m/0' (m/0'/0 through m/0'/99)
    print()
    print("=" * 80)
    print("DEEP SUB-DERIVATIONS OF m/0' (m/0'/0 through m/0'/99)")
    print("=" * 80)
    print()
    
    # Derive m/0' first
    m0_priv, m0_cc = bip32_child_priv(master_priv, master_chain_code, 0 + HARDENED)
    m0_pub_point = point_mul(m0_priv)
    m0_pub = compress_pub(m0_pub_point[0], m0_pub_point[1])
    print(f"m/0' P2WPKH: {p2wpkh_addr(m0_pub)}")
    print()
    
    funded_m0 = []
    for i in range(100):
        child_priv, child_cc = bip32_child_priv(m0_priv, m0_cc, i + HARDENED)
        child_pub_point = point_mul(child_priv)
        child_pub = compress_pub(child_pub_point[0], child_pub_point[1])
        p2wpkh = p2wpkh_addr(child_pub)
        
        bal = check_balance(p2wpkh)
        status = ""
        if "error" not in bal:
            btc = bal["chain_stats"]
            txs = bal["tx_count"]
            if btc > 0:
                status = f" *** {btc:.8f} BTC ({txs} txs) ***"
                funded_m0.append((f"m/0'/{i}'", p2wpkh, btc, txs))
        
        if status:
            print(f"m/0'/{i}'  {p2wpkh}{status}")
    
    if funded_m0:
        print()
        print("FUNDED under m/0':")
        for path, addr, btc, txs in funded_m0:
            print(f"  {path}: {btc:.8f} BTC ({txs} txs)")
    else:
        print("  (all 100 sub-derivations of m/0' are empty)")
    
    # Step 5: Try alternative chain codes
    print()
    print("=" * 80)
    print("ALTERNATIVE CHAIN CODES")
    print("=" * 80)
    print()
    
    alt_chain_codes = {
        "SHA256(master_priv)": hashlib.sha256(master_priv.to_bytes(32, 'big')).digest(),
        "SHA256(pattern)": hashlib.sha256(bytes.fromhex(PATTERN)).digest(),
        "SHA256(domain || pattern)": hashlib.sha256(b"MESSERENE/PREGENESIS/v1" + bytes.fromhex(PATTERN)).digest(),
        "SHA256(master_pub)": hashlib.sha256(master_pub).digest(),
        "Zero chain code": b'\x00' * 32,
        "HMAC-SHA512(master_priv)[:32]": hmac_sha512(master_priv.to_bytes(32, 'big'), b"")[:32],
    }
    
    for cc_name, cc in alt_chain_codes.items():
        print(f"\nChain code: {cc_name}")
        print(f"  Value: {cc.hex()}")
        
        # Derive m/0' with this chain code
        alt_m0_priv, alt_m0_cc = bip32_child_priv(master_priv, cc, 0 + HARDENED)
        alt_m0_pub_point = point_mul(alt_m0_priv)
        alt_m0_pub = compress_pub(alt_m0_pub_point[0], alt_m0_pub_point[1])
        alt_m0_p2wpkh = p2wpkh_addr(alt_m0_pub)
        
        bal = check_balance(alt_m0_p2wpkh)
        if "error" not in bal:
            btc = bal["chain_stats"]
            txs = bal["tx_count"]
            marker = f" *** {btc:.8f} BTC ({txs} txs) ***" if btc > 0 else ""
            print(f"  m/0' P2WPKH: {alt_m0_p2wpkh}{marker}")
            
            # Also check first 5 sub-derivations
            for i in range(5):
                child_priv, child_cc = bip32_child_priv(alt_m0_priv, alt_m0_cc, i + HARDENED)
                child_pub_point = point_mul(child_priv)
                child_pub = compress_pub(child_pub_point[0], child_pub_point[1])
                child_p2wpkh = p2wpkh_addr(child_pub)
                child_bal = check_balance(child_p2wpkh)
                if "error" not in child_bal and child_bal["chain_stats"] > 0:
                    print(f"  m/0'/{i}' P2WPKH: {child_p2wpkh} *** {child_bal['chain_stats']:.8f} BTC ***")
        else:
            print(f"  Error: {bal['error']}")
    
    # Also check the master key itself
    print()
    print("=" * 80)
    print("MASTER KEY BALANCE")
    print("=" * 80)
    master_p2wpkh = p2wpkh_addr(master_pub)
    master_p2pkh = p2pkh_addr(master_pub)
    bal = check_balance(master_p2wpkh)
    print(f"Master P2WPKH: {master_p2wpkh}")
    if "error" not in bal:
        print(f"  Balance: {bal['chain_stats']:.8f} BTC ({bal['tx_count']} txs)")
    else:
        print(f"  Error: {bal['error']}")
    
    bal2 = check_balance(master_p2pkh)
    print(f"Master P2PKH:  {master_p2pkh}")
    if "error" not in bal2:
        print(f"  Balance: {bal2['chain_stats']:.8f} BTC ({bal2['tx_count']} txs)")
    else:
        print(f"  Error: {bal2['error']}")

if __name__ == "__main__":
    main()
