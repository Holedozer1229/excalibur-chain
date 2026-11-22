#!/usr/bin/env python3
"""sweep_wallet.py — Universal Bitcoin wallet sweeper.

Sweep all UTXOs from any address to a destination address.
Supports P2PKH (legacy) and P2WPKH (Bech32) input types.

Features:
- Dry-run mode (build + sign without broadcasting)
- Explicit confirmation before broadcast
- Automatic fee estimation
- Change output when sweep amount is significant
- UTXO fetching via Blockstream API

Usage:
    # Dry run (safe, no broadcast)
    python sweep_wallet.py --privkey <hex> --to <address> --dry-run

    # Sweep with confirmation
    python sweep_wallet.py --privkey <hex> --to <address>

    # Custom fee rate
    python sweep_wallet.py --privkey <hex> --to <address> --fee-rate 20

    # BIP38 encrypted key
    python sweep_wallet.py --bip38 <6P...> --passphrase <text> --to <address>

Safety:
- Default is dry-run unless --broadcast flag is set
- Never auto-broadcasts without explicit --broadcast
- Validates private key range before use
- Shows full transaction details before confirmation
"""
import sys
import os
import json
import struct
import hashlib
import argparse
import urllib.request
import urllib.error

# ============================================================
# secp256k1 (from secp256k1.py)
# ============================================================

P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
Gx = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
Gy = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8
G = (Gx, Gy)


def _inv(a, m):
    return pow(a, m - 2, m)


def _add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2:
        if (y1 + y2) % P == 0:
            return None
        lam = (3 * x1 * x1) * _inv(2 * y1, P) % P
    else:
        lam = (y2 - y1) * _inv(x2 - x1, P) % P
    x3 = (lam * lam - x1 - x2) % P
    return (x3, (lam * (x1 - x3) - y1) % P)


def _mul(k, pt=G):
    if k == 0:
        return None
    r = None
    r2 = pt
    for i in range(k.bit_length() - 1, -1, -1):
        if (k >> i) & 1:
            r = _add(r, r2)
            r2 = _add(r2, r2)
        else:
            r2 = _add(r, r2)
            r = _add(r, r)
    return r


def point_to_compressed(pt):
    x, y = pt
    return bytes([0x02 | (y & 1)]) + x.to_bytes(32, "big")


def point_to_uncompressed(pt):
    x, y = pt
    return b"\x04" + x.to_bytes(32, "big") + y.to_bytes(32, "big")


# ============================================================
# Hashing
# ============================================================


def sha256(data):
    return hashlib.sha256(data).digest()


def sha256d(data):
    return sha256(sha256(data))


def ripemd160(data):
    return hashlib.new("ripemd160", data).digest()


def hash160(data):
    return ripemd160(sha256(data))


# ============================================================
# Base58
# ============================================================

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def base58encode(data):
    num = int.from_bytes(data, "big")
    encoded = ""
    while num > 0:
        num, rem = divmod(num, 58)
        encoded = _B58[rem] + encoded
    for b in data:
        if b == 0:
            encoded = "1" + encoded
        else:
            break
    return encoded


def base58decode(s):
    num = 0
    for ch in s:
        num = num * 58 + _B58.index(ch)
    hbytes = num.to_bytes((num.bit_length() + 7) // 8 or 1, "big")
    for ch in s:
        if ch == "1":
            hbytes = b"\x00" + hbytes
        else:
            break
    return hbytes


def base58check_encode(payload):
    checksum = sha256d(payload)[:4]
    return base58encode(payload + checksum)


def base58check_decode(s):
    data = base58decode(s)
    payload, checksum = data[:-4], data[-4:]
    expected = sha256d(payload)[:4]
    if checksum != expected:
        raise ValueError("Base58Check checksum mismatch")
    return payload


# ============================================================
# Bech32
# ============================================================


def bech32_encode(hrp, data):
    charset = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"

    def bech32_polymod(values):
        GEN = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
        chk = 1
        for v in values:
            top = chk >> 25
            chk = ((chk & 0x1FFFFFF) << 5) ^ v
            for i in range(5):
                if (top >> i) & 1:
                    chk ^= GEN[i]
        return chk

    def expand_hrp(hrp):
        ret = [ord(c) >> 5 for c in hrp]
        ret.append(0)
        ret.extend([ord(c) & 31 for c in hrp])
        return ret

    bits = 0
    bitcount = 0
    five_bit_groups = []
    for byte in data:
        bits = (bits << 8) | byte
        bitcount += 8
        while bitcount >= 5:
            bitcount -= 5
            five_bit_groups.append((bits >> bitcount) & 0x1F)

    values = expand_hrp(hrp) + five_bit_groups + [0] * 6
    checksum = bech32_polymod(values) ^ 1
    checksum_chars = [charset[(checksum >> 5 * (5 - i)) & 31] for i in range(6)]
    data_chars = [charset[d] for d in five_bit_groups]
    return hrp + "1" + "".join(data_chars + checksum_chars)


def bech32_decode(addr):
    """Decode bech32 address, return (hrp, witver, program)."""
    charset = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
    addr = addr.lower()
    pos = addr.rfind("1")
    hrp, tail = addr[:pos], addr[pos + 1 :]
    vals = [charset.index(c) for c in tail]

    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in ([ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp] + vals):
        b = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            if (b >> i) & 1:
                chk ^= gen[i]
    if chk != 1:
        raise ValueError("Bad Bech32 checksum")

    data_vals = vals[1:-6]
    val = 0
    bits = 0
    out = []
    for v in data_vals:
        val = (val << 5) | v
        bits += 5
        while bits >= 8:
            bits -= 8
            out.append((val >> bits) & 0xFF)
    return hrp, vals[0], bytes(out)


# ============================================================
# Address utilities
# ============================================================


def p2pkh_address(pubkey_bytes):
    h = hash160(pubkey_bytes)
    payload = b"\x00" + h
    return base58check_encode(payload)


def p2wpkh_address(pubkey_bytes):
    h = hash160(pubkey_bytes)
    return bech32_encode("bc", h)


def script_pubkey_for(addr):
    """Build scriptPubKey from a Bitcoin address."""
    if addr.startswith("bc1"):
        hrp, witver, prog = bech32_decode(addr)
        return bytes([witver, len(prog)]) + prog
    elif addr.startswith("1") or addr.startswith("m") or addr.startswith("n"):
        decoded = base58check_decode(addr)
        pkh = decoded[1:]  # skip version byte
        return bytes([0x76, 0xA9, 0x14]) + pkh + bytes([0x88, 0xAC])
    elif addr.startswith("3"):
        decoded = base58check_decode(addr)
        sph = decoded[1:]
        return bytes([0xA9, 0x14]) + sph + bytes([0x87])
    else:
        raise ValueError(f"Unknown address type: {addr[:4]}...")


def detect_address_type(addr):
    """Detect whether an address is P2PKH, P2WPKH, P2TR, or P2SH."""
    if addr.startswith("bc1q"):
        return "p2wpkh"
    elif addr.startswith("bc1p"):
        return "p2tr"
    elif addr.startswith("1") or addr.startswith("m") or addr.startswith("n"):
        return "p2pkh"
    elif addr.startswith("3"):
        return "p2sh"
    else:
        return "unknown"


# ============================================================
# ECDSA signing
# ============================================================


def sign_ecdsa(priv_int, message_hash):
    """Sign a message hash with secp256k1 ECDSA (deterministic-like)."""
    import random

    # Simple ECDSA signing (for sweep purposes)
    # In production, use RFC 6979 for deterministic k
    for _ in range(100):
        k = random.SystemRandom().randrange(1, N)
        k_point = _mul(k)
        r = k_point[0] % N
        if r == 0:
            continue

        s = (_inv(k, N) * (message_hash.int_from_bytes(32, "big") + r * priv_int)) % N
        if s == 0:
            continue

        # Low S normalization
        if s > N // 2:
            s = N - s

        return r, s
    raise ValueError("Failed to generate signature")


def der_encode_int(n):
    """DER encode an integer."""
    if n == 0:
        return b"\x00"
    hex_n = format(n, "x")
    if len(hex_n) % 2:
        hex_n = "0" + hex_n
    b = bytes.fromhex(hex_n)
    if b[0] & 0x80:
        b = b"\x00" + b
    return b


def der_encode_signature(r, s):
    """DER encode an ECDSA signature."""
    r_bytes = der_encode_int(r)
    s_bytes = der_encode_int(s)
    sig = (
        b"\x30"
        + bytes([0x02 + len(r_bytes) + 0x02 + len(s_bytes) + 4])
        + b"\x02"
        + bytes([len(r_bytes)])
        + r_bytes
        + b"\x02"
        + bytes([len(s_bytes)])
        + s_bytes
    )
    return sig


# ============================================================
# Transaction serialization
# ============================================================


def varint(n):
    if n < 253:
        return bytes([n])
    elif n < 65536:
        return b"\xFD" + n.to_bytes(2, "little")
    elif n < 4294967296:
        return b"\xFE" + n.to_bytes(4, "little")
    else:
        return b"\xFF" + n.to_bytes(8, "little")


def serialize_tx(tx):
    """Serialize a Bitcoin transaction to bytes."""
    buf = b""
    buf += struct.pack("<I", tx["version"])

    # Inputs
    buf += varint(len(tx["vin"]))
    for vin in tx["vin"]:
        buf += bytes.fromhex(vin["prevout_txid"])[::-1]
        buf += struct.pack("<I", vin["prevout_vout"])
        buf += varint(len(vin.get("scriptSig", b"")))
        buf += vin.get("scriptSig", b"")
        buf += struct.pack("<I", vin.get("sequence", 0xFFFFFFFF))

    # Witness marker/flag
    has_witness = any(vin.get("witness") for vin in tx["vin"])
    if has_witness:
        buf += b"\x00\x01"

    # Outputs
    buf += varint(len(tx["vout"]))
    for vout in tx["vout"]:
        buf += struct.pack("<Q", vout["value"])
        buf += varint(len(vout["scriptPubKey"]))
        buf += vout["scriptPubKey"]

    # Witness stack
    if has_witness:
        for vin in tx["vin"]:
            witness = vin.get("witness", [])
            buf += varint(len(witness))
            for item in witness:
                buf += varint(len(item))
                buf += item

    # Locktime
    buf += struct.pack("<I", tx.get("locktime", 0))
    return buf


# ============================================================
# BIP143 Sighash
# ============================================================


def bip143_sighash(tx, input_index, script_code, value, sighash_type=1):
    """Compute BIP143 sighash for P2WPKH."""
    if sighash_type & 0x1F != 1:
        hash_prevouts = b"\x00" * 32
    else:
        hash_prevouts = sha256d(
            b"".join(
                bytes.fromhex(vin["prevout_txid"])[::-1]
                + struct.pack("<I", vin["prevout_vout"])
                for vin in tx["vin"]
            )
        )

    if sighash_type & 0x1F not in (1, 3):
        hash_sequence = b"\x00" * 32
    else:
        hash_sequence = sha256d(
            b"".join(
                struct.pack("<I", vin.get("sequence", 0xFFFFFFFF)) for vin in tx["vin"]
            )
        )

    if sighash_type & 0x1F == 3:
        if input_index < len(tx["vout"]):
            vout = tx["vout"][input_index]
            hash_outputs = sha256d(
                struct.pack("<Q", vout["value"])
                + varint(len(vout["scriptPubKey"]))
                + vout["scriptPubKey"]
            )
        else:
            hash_outputs = b"\x00" * 32
    elif sighash_type & 0x1F != 1:
        hash_outputs = b"\x00" * 32
    else:
        hash_outputs = sha256d(
            b"".join(
                struct.pack("<Q", vout["value"])
                + varint(len(vout["scriptPubKey"]))
                + vout["scriptPubKey"]
                for vout in tx["vout"]
            )
        )

    n = tx["vin"][input_index]
    preimage = (
        struct.pack("<I", tx["version"])
        + hash_prevouts
        + hash_sequence
        + bytes.fromhex(n["prevout_txid"])[::-1]
        + struct.pack("<I", n["prevout_vout"])
        + varint(len(script_code))
        + script_code
        + struct.pack("<Q", value)
        + struct.pack("<I", n.get("sequence", 0xFFFFFFFF))
        + hash_outputs
        + struct.pack("<I", tx.get("locktime", 0))
        + struct.pack("<I", sighash_type)
    )
    return sha256d(preimage)


# ============================================================
# UTXO fetching
# ============================================================


def fetch_utxos(address):
    """Fetch UTXOs from Blockstream API."""
    url = f"https://blockstream.info/api/address/{address}/utxo"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "sweep-wallet/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        utxos = []
        for u in data:
            utxos.append(
                {
                    "txid": u["txid"],
                    "vout": u["vout"],
                    "value": u["value"],
                    "status": u.get("status", {}),
                }
            )
        return utxos
    except Exception as e:
        print(f"Error fetching UTXOs: {e}")
        return []


def fetch_address_info(address):
    """Fetch address balance info from Blockstream API."""
    url = f"https://blockstream.info/api/address/{address}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "sweep-wallet/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        print(f"Error fetching address info: {e}")
        return None


# ============================================================
# Transaction building
# ============================================================


def build_sweep_tx(utxos, to_address, fee_rate=10, from_address=None):
    """Build a sweep transaction spending all UTXOs.

    Returns (tx, total_input, fee, change).
    """
    total_input = sum(u["value"] for u in utxos)

    # Estimate virtual size
    # P2WPKH input: ~68 vB, P2PKH input: ~141 vB
    # P2WPKH output: ~31 vB, P2PKH output: ~34 vB
    # Base overhead: ~10 vB
    input_type = detect_address_type(from_address) if from_address else "p2wpkh"
    output_type = detect_address_type(to_address)

    if input_type == "p2wpkh":
        input_vb = 68
    else:
        input_vb = 141

    if output_type == "p2wpkh":
        output_vb = 31
    elif output_type == "p2tr":
        output_vb = 43  # P2TR outputs are 43 bytes
    elif output_type == "p2sh":
        output_vb = 32
    else:
        output_vb = 34

    # Estimate with one output (destination only)
    est_size_1out = 10 + len(utxos) * input_vb + 1 * output_vb + 10
    fee_1out = max(1000, est_size_1out * fee_rate)

    # Estimate with two outputs (destination + change)
    est_size_2out = 10 + len(utxos) * input_vb + 2 * output_vb + 10
    fee_2out = max(1000, est_size_2out * fee_rate)

    # Determine if change output is needed
    dust_limit = 546  # satoshis
    change_amount = total_input - fee_2out

    to_script = script_pubkey_for(to_address)

    tx = {"version": 2, "vin": [], "vout": [], "locktime": 0}

    # Add inputs
    for u in utxos:
        tx["vin"].append(
            {
                "prevout_txid": u["txid"],
                "prevout_vout": u["vout"],
                "scriptSig": b"",
                "sequence": 0xFFFFFFFF,
                "witness": [],
                "value": u["value"],
            }
        )

    if change_amount > dust_limit and from_address and from_address != to_address:
        # Two outputs: destination + change
        change_script = script_pubkey_for(from_address)
        dest_value = total_input - fee_2out
        tx["vout"] = [
            {"value": dest_value, "scriptPubKey": to_script},
            {"value": change_amount, "scriptPubKey": change_script},
        ]
        return tx, total_input, fee_2out, change_amount
    else:
        # One output: all to destination (fee absorbs any change)
        dest_value = total_input - fee_1out
        tx["vout"] = [{"value": dest_value, "scriptPubKey": to_script}]
        return tx, total_input, fee_1out, 0


def sign_sweep_tx(tx, priv_int, from_address):
    """Sign all inputs of the sweep transaction."""
    pub = _mul(priv_int)
    pub_comp = point_to_compressed(pub)
    h160_comp = hash160(pub_comp)

    # scriptCode for P2WPKH: OP_DUP OP_HASH160 <H160(pub)> OP_EQUALVERIFY OP_CHECKSIG
    script_code = bytes([0x76, 0xA9, 0x14]) + h160_comp + bytes([0x88, 0xAC])

    input_type = detect_address_type(from_address)

    for i, vin in enumerate(tx["vin"]):
        spent_value = vin["value"]

        if input_type == "p2wpkh":
            # BIP143 sighash for P2WPKH
            sighash = bip143_sighash(tx, i, script_code, spent_value)
            sighash_int = int.from_bytes(sighash, "big")
            r, s = sign_ecdsa(priv_int, sighash)
            sig = der_encode_signature(r, s) + bytes([0x01])  # SIGHASH_ALL
            vin["witness"] = [sig, pub_comp]
        else:
            # Legacy P2PKH — use legacy sighash
            # For simplicity, build the legacy sighash
            sighash = legacy_sighash_all(tx, i, script_code)
            sighash_int = int.from_bytes(sighash, "big")
            r, s = sign_ecdsa(priv_int, sighash)
            sig = der_encode_signature(r, s) + bytes([0x01])
            vin["scriptSig"] = varint(len(sig) + len(pub_comp)) + sig + varint(len(pub_comp)) + pub_comp

    return tx


def legacy_sighash_all(tx, input_index, script_code):
    """Compute legacy SIGHASH_ALL for P2PKH."""
    buf = struct.pack("<I", tx["version"])

    # Inputs (with scriptCode at input_index)
    buf += varint(len(tx["vin"]))
    for i, vin in enumerate(tx["vin"]):
        buf += bytes.fromhex(vin["prevout_txid"])[::-1]
        buf += struct.pack("<I", vin["prevout_vout"])
        if i == input_index:
            buf += varint(len(script_code)) + script_code
        else:
            buf += varint(0)
        buf += struct.pack("<I", vin.get("sequence", 0xFFFFFFFF))

    # Outputs
    buf += varint(len(tx["vout"]))
    for vout in tx["vout"]:
        buf += struct.pack("<Q", vout["value"])
        buf += varint(len(vout["scriptPubKey"]))
        buf += vout["scriptPubKey"]

    buf += struct.pack("<I", tx.get("locktime", 0))
    buf += struct.pack("<I", 1)  # SIGHASH_ALL

    return sha256d(buf)


# ============================================================
# Broadcasting
# ============================================================


def broadcast_tx(tx_hex):
    """Broadcast transaction via Blockstream API."""
    url = "https://blockstream.info/api/tx"
    try:
        data = tx_hex.encode("utf-8")
        req = urllib.request.Request(
            url, data=data, headers={"User-Agent": "sweep-wallet/1.0", "Content-Type": "text/plain"}
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = resp.read().decode().strip()
        if resp.status == 200:
            return True, result
        else:
            return False, result
    except urllib.error.HTTPError as e:
        body = e.read().decode() if hasattr(e, "read") else str(e)
        return False, f"HTTP {e.code}: {body}"
    except Exception as e:
        return False, str(e)


# ============================================================
# Key derivation
# ============================================================


def derive_addresses(priv_int):
    """Derive all address forms from a private key."""
    pub = _mul(priv_int)
    pub_comp = point_to_compressed(pub)
    pub_uncomp = point_to_uncompressed(pub)

    p2wpkh = p2wpkh_address(pub_comp)
    p2pkh_comp = p2pkh_address(pub_comp)
    p2pkh_uncomp = p2pkh_address(pub_uncomp)

    return {
        "priv": priv_int,
        "pub_comp": pub_comp,
        "pub_uncomp": pub_uncomp,
        "p2wpkh": p2wpkh,
        "p2pkh_comp": p2pkh_comp,
        "p2pkh_uncomp": p2pkh_uncomp,
    }


def find_matching_address(priv_int, target_address):
    """Check if the private key corresponds to the target address."""
    addrs = derive_addresses(priv_int)
    if (
        target_address == addrs["p2wpkh"]
        or target_address == addrs["p2pkh_comp"]
        or target_address == addrs["p2pkh_uncomp"]
    ):
        return target_address
    return None


# ============================================================
# BIP38 support (optional)
# ============================================================


def decode_bip38(bip38_str, passphrase):
    """Decode BIP38 encrypted key using bip38.py module."""
    try:
        from bip38 import decode as bip38_decode

        priv_int, compressed = bip38_decode(bip38_str, passphrase)
        return priv_int
    except ImportError:
        print("Error: bip38.py not found. Install it or use --privkey instead.")
        return None
    except Exception as e:
        print(f"BIP38 decode error: {e}")
        return None


# ============================================================
# Main
# ============================================================


def main():
    parser = argparse.ArgumentParser(
        description="Sweep all UTXOs from a Bitcoin address to a destination"
    )
    parser.add_argument(
        "--privkey",
        help="Private key in hex (64 chars)",
    )
    parser.add_argument(
        "--bip38",
        help="BIP38 encrypted private key (starts with 6P or 2E)",
    )
    parser.add_argument(
        "--passphrase",
        help="Passphrase for BIP38 decryption",
    )
    parser.add_argument(
        "--to",
        required=True,
        help="Destination Bitcoin address",
    )
    parser.add_argument(
        "--from",
        help="Source address (auto-detected from privkey if omitted)",
    )
    parser.add_argument(
        "--fee-rate",
        type=int,
        default=10,
        help="Fee rate in sats/vB (default: 10)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and sign but do NOT broadcast",
    )
    parser.add_argument(
        "--broadcast",
        action="store_true",
        help="Broadcast after confirmation (default: no broadcast)",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Skip confirmation prompt (use with caution)",
    )

    args = parser.parse_args()

    # Validate key input
    if not args.privkey and not args.bip38:
        print("Error: --privkey or --bip38 is required")
        sys.exit(1)

    if args.bip38 and not args.passphrase:
        print("Error: --passphrase is required for BIP38 keys")
        sys.exit(1)

    # Get private key
    if args.bip38:
        priv_int = decode_bip38(args.bip38, args.passphrase)
        if priv_int is None:
            sys.exit(1)
    else:
        priv_hex = args.privkey
        if priv_hex.startswith("0x"):
            priv_hex = priv_hex[2:]
        if len(priv_hex) < 64:
            priv_hex = priv_hex.zfill(64)
        priv_int = int(priv_hex, 16)

    if not (1 <= priv_int < N):
        print("Error: invalid private key (must be 1..N-1)")
        sys.exit(1)

    # Derive addresses
    addrs = derive_addresses(priv_int)
    print("=" * 70)
    print("  SWEEP WALLET")
    print("=" * 70)
    print(f"  P2WPKH (Bech32):  {addrs['p2wpkh']}")
    print(f"  P2PKH (compressed): {addrs['p2pkh_comp']}")
    print(f"  P2PKH (uncompressed): {addrs['p2pkh_uncomp']}")
    print()

    # Determine source address
    from_addr = args.from_ if hasattr(args, "from_") else getattr(args, "from", None)
    if not from_addr:
        # Default to P2WPKH
        from_addr = addrs["p2wpkh"]
        print(f"  Using default source: {from_addr} (P2WPKH)")
        print(f"  Use --from <addr> to specify a different source")
    print()

    # Fetch UTXOs
    print(f"  Fetching UTXOs for {from_addr}...")
    utxos = fetch_utxos(from_addr)

    if not utxos:
        print("  No UTXOs found. Nothing to sweep.")
        print()
        print("  To receive coins at this address:")
        print(f"    P2WPKH: {addrs['p2wpkh']}")
        print(f"    P2PKH:  {addrs['p2pkh_comp']}")
        return

    total = sum(u["value"] for u in utxos)
    print(f"  Found {len(utxos)} UTXO(s): {total / 100_000_000:.8f} BTC")
    print()

    # Build transaction
    print(f"  Building sweep transaction...")
    print(f"    To: {args.to}")
    print(f"    Fee rate: {args.fee_rate} sats/vB")

    tx, total_input, fee, change = build_sweep_tx(
        utxos, args.to, args.fee_rate, from_addr
    )

    print(f"    Total input: {total_input / 100_000_000:.8f} BTC")
    print(f"    Fee: {fee / 100_000_000:.8f} BTC ({fee} sats)")
    for i, vout in enumerate(tx["vout"]):
        label = "Destination" if i == 0 else "Change"
        print(f"    {label}: {vout['value'] / 100_000_000:.8f} BTC")
    if change > 0:
        print(f"    Change: {change / 100_000_000:.8f} BTC")
    print()

    # Sign
    print("  Signing transaction...")
    tx = sign_sweep_tx(tx, priv_int, from_addr)

    # Serialize
    tx_bytes = serialize_tx(tx)
    tx_hex = tx_bytes.hex()
    wtxid = sha256d(tx_bytes)[::-1].hex()

    print(f"  Signed! WTXID: {wtxid}")
    print(f"  Size: {len(tx_bytes)} bytes")
    print()

    if args.dry_run:
        print("  [DRY RUN] Transaction built and signed but not broadcast.")
        print(f"  Full hex:\n{tx_hex}")
        return

    # Confirmation
    if not args.broadcast:
        print("  [SAFE MODE] Use --broadcast to broadcast, or --dry-run to test.")
        print(f"  Full hex:\n{tx_hex}")
        return

    if not args.yes:
        print()
        print("=" * 70)
        print("  CONFIRMATION REQUIRED")
        print("=" * 70)
        print(f"  Sweep {total_input / 100_000_000:.8f} BTC from {from_addr}")
        print(f"  To: {args.to}")
        print(f"  Fee: {fee / 100_000_000:.8f} BTC")
        if change > 0:
            print(f"  Change: {change / 100_000_000:.8f} BTC to {from_addr}")
        print()
        confirm = input("  Type YES to broadcast: ")
        if confirm.strip() != "YES":
            print("  Aborted.")
            return

    # Broadcast
    print()
    print("  Broadcasting...")
    success, result = broadcast_tx(tx_hex)
    if success:
        print(f"  SUCCESS! TXID: {result}")
        print(f"  Swept {total_input / 100_000_000:.8f} BTC to {args.to}")
    else:
        print(f"  FAILED: {result}")
        print(f"  Transaction hex saved for manual broadcast:")
        print(f"  {tx_hex}")


if __name__ == "__main__":
    main()
