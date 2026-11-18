#!/usr/bin/env python3
"""sign_and_sweep.py — Sign and sweep the Genesis Key (2083236893).

Uses the Bitcoin genesis block nonce as a secp256k1 private key to:
1. Derive the P2WPKH address
2. Fetch UTXOs from Blockstream API
3. Build a sweep transaction spending all UTXOs to a destination
4. Sign with BIP143 sighash + secp256k1
5. Broadcast to Bitcoin mainnet

Usage:
    python sign_and_sweep.py --to <address> [--dry-run] [--fee-rate <sats/vB>]

The genesis key:
    Private key: 2083236893 (0x7c2bac1d)
    P2WPKH: bc1q7u79m6fvv3mmlc8uprmapzk0jkdd8jp434w2uu
    P2PKH:  1PYGDk8ai95x1H86VGGd3iCwD91tjUdDti
"""
import sys
import os
import json
import struct
import hashlib
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'self-serve', 'vendor'))

from secp256k1 import priv_to_pub, compress, sign, der_encode
from btc_htlc import bech32_encode, hash160, push, sha256d

# ============================================================
# Genesis Key
# ============================================================

GENESIS_KEY = 2083236893
GENESIS_KEY_HEX = f"{GENESIS_KEY:064x}"

# Derive pubkey and address
_pub = priv_to_pub(GENESIS_KEY)
_COMP = compress(_pub)
_PUB_HASH = hash160(_COMP)
P2WPKH_ADDR = bech32_encode('bc', 0, _PUB_HASH)

print("=" * 70)
print("  GENESIS KEY SWEEPER")
print("=" * 70)
print(f"  Private key: {GENESIS_KEY} (0x{GENESIS_KEY:064x})")
print(f"  Compressed pubkey: {_COMP.hex()}")
print(f"  P2WPKH address: {P2WPKH_ADDR}")
print("=" * 70)

# ============================================================
# Helpers
# ============================================================

def h160(data: bytes) -> bytes:
    return hashlib.new('ripemd160', hashlib.sha256(data).digest()).digest()

def script_pubkey_for(addr: str) -> bytes:
    """Build scriptPubKey from a Bitcoin address."""
    if addr.startswith('bc1'):
        # Bech32 P2WPKH
        hrp, witver, prog = bech32_decode(addr)
        return bytes([0x00, len(prog)]) + prog
    elif addr.startswith('1') or addr.startswith('m') or addr.startswith('n'):
        # Legacy P2PKH
        pkh = base58_decode(addr)[1:]
        return bytes([0x76, 0xa9, 0x14]) + pkh + bytes([0x88, 0xac])
    elif addr.startswith('3'):
        # P2SH
        sph = base58_decode(addr)[1:]
        return bytes([0xa9, 0x14]) + sph + bytes([0x87])
    else:
        raise ValueError(f"Unknown address type: {addr}")

def base58_decode(s: str) -> bytes:
    alphabet = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
    n = 0
    for c in s:
        n = n * 58 + alphabet.index(c)
    result = n.to_bytes(len(s) + 1, 'big').lstrip(b'\x00') or b'\x00'
    for byte in s:
        if byte == '1':
            result = b'\x00' + result
        else:
            break
    return result

def bech32_decode(addr: str):
    """Decode bech32 address, return (hrp, witver, program)."""
    _BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
    addr = addr.lower()
    pos = addr.rfind("1")
    hrp, tail = addr[:pos], addr[pos + 1:]
    vals = [_BECH32.index(c) for c in tail]
    # polymod check
    gen = [0x3B6A57B2, 0x26508E6D, 0x1EA119FA, 0x3D4233DD, 0x2A1462B3]
    chk = 1
    for v in ([ord(c) >> 5 for c in hrp] + [0] + [ord(c) & 31 for c in hrp] + vals):
        b = chk >> 25
        chk = ((chk & 0x1FFFFFF) << 5) ^ v
        for i in range(5):
            if (b >> i) & 1:
                chk ^= gen[i]
    if chk != 1:
        raise ValueError("bad checksum")
    # convert bits
    data_vals = vals[1:-6]
    acc = val = 0
    bits = 0
    out = []
    for v in data_vals:
        val = (val << 5) | v
        bits += 5
        while bits >= 8:
            bits -= 8
            out.append((val >> bits) & 0xFF)
    return hrp, vals[0], bytes(out)

def varint(n: int) -> bytes:
    if n < 253:
        return bytes([n])
    elif n < 65536:
        return b'\xfd' + n.to_bytes(2, 'little')
    else:
        return b'\xfe' + n.to_bytes(4, 'little')

def serialize_tx(tx: dict) -> bytes:
    """Serialize a Bitcoin transaction to bytes."""
    buf = b''
    # Version
    buf += struct.pack('<I', tx['version'])
    
    # Input count
    buf += varint(len(tx['vin']))
    
    # Inputs
    for vin in tx['vin']:
        buf += bytes.fromhex(vin['prev_txid'])[::-1]  # little-endian
        buf += struct.pack('<I', vin['prev_vout'])
        buf += varint(len(vin.get('scriptSig', b'')))
        buf += vin.get('scriptSig', b'')
        buf += struct.pack('<I', vin.get('sequence', 0xFFFFFFFF))
    
    # Witness marker and flag (for segwit)
    has_witness = any(vin.get('witness') for vin in tx['vin'])
    if has_witness:
        buf += b'\x00\x01'
    
    # Output count
    buf += varint(len(tx['vout']))
    
    # Outputs
    for vout in tx['vout']:
        buf += struct.pack('<Q', vout['value'])
        buf += varint(len(vout['scriptPubKey']))
        buf += vout['scriptPubKey']
    
    # Witness stack
    if has_witness:
        for vin in tx['vin']:
            witness = vin.get('witness', [])
            buf += varint(len(witness))
            for item in witness:
                buf += varint(len(item))
                buf += item
    
    # Locktime
    buf += struct.pack('<I', tx.get('locktime', 0))
    
    return buf

def txid_from(tx_bytes: bytes) -> str:
    """Compute txid from serialized transaction."""
    return sha256d(tx_bytes)[::-1].hex()

def wtxid_from(tx_bytes: bytes) -> str:
    """Compute wtxid from serialized transaction (includes witness)."""
    return sha256d(tx_bytes)[::-1].hex()

# ============================================================
# BIP143 Sighash for P2WPKH
# ============================================================

def bip143_p2wpkh_sighash(tx: dict, input_index: int, script_code: bytes,
                           spent_value: int, sighash_type: int = 1) -> bytes:
    """Compute BIP143 sighash for a P2WPKH input."""
    # HashPrevouts
    if sighash_type & 0x1f != 1:
        hash_prevouts = b'\x00' * 32
    else:
        hash_prevouts = sha256d(
            b''.join(
                bytes.fromhex(vin['prev_txid'])[::-1] +
                struct.pack('<I', vin['prev_vout'])
                for vin in tx['vin']
            )
        )
    
    # HashSequence
    if sighash_type & 0x1f not in (1, 3):
        hash_sequence = b'\x00' * 32
    else:
        hash_sequence = sha256d(
            b''.join(struct.pack('<I', vin.get('sequence', 0xFFFFFFFF)) for vin in tx['vin'])
        )
    
    # HashOutputs
    if sighash_type & 0x1f == 3:
        if input_index < len(tx['vout']):
            vout = tx['vout'][input_index]
            hash_outputs = sha256d(
                struct.pack('<Q', vout['value']) +
                varint(len(vout['scriptPubKey'])) +
                vout['scriptPubKey']
            )
        else:
            hash_outputs = b'\x00' * 32
    elif sighash_type & 0x1f != 1:
        hash_outputs = b'\x00' * 32
    else:
        hash_outputs = sha256d(
            b''.join(
                struct.pack('<Q', vout['value']) +
                varint(len(vout['scriptPubKey'])) +
                vout['scriptPubKey']
                for vout in tx['vout']
            )
        )
    
    # Script code
    n = tx['vin'][input_index]
    
    # Preimage
    preimage = (
        struct.pack('<I', tx['version']) +
        hash_prevouts +
        hash_sequence +
        bytes.fromhex(n['prev_txid'])[::-1] +
        struct.pack('<I', n['prev_vout']) +
        varint(len(script_code)) + script_code +
        struct.pack('<Q', spent_value) +
        struct.pack('<I', n.get('sequence', 0xFFFFFFFF)) +
        hash_outputs +
        struct.pack('<I', tx.get('locktime', 0)) +
        struct.pack('<I', sighash_type)
    )
    
    return sha256d(preimage)

# ============================================================
# Fetch UTXOs
# ============================================================

def fetch_utxos(address: str):
    """Fetch UTXOs from Blockstream API."""
    try:
        result = subprocess.run(
            ['curl.exe', '-s', f'https://blockstream.info/api/address/{address}/utxo'],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            print(f"Failed to fetch UTXOs: {result.stderr}")
            return []
        data = json.loads(result.stdout)
        utxos = []
        for u in data:
            utxos.append({
                'txid': u['txid'],
                'vout': u['vout'],
                'value': u['value'],
                'status': u.get('status', {})
            })
        return utxos
    except Exception as e:
        print(f"Error fetching UTXOs: {e}")
        return []

# ============================================================
# Build and Sign Sweep Transaction
# ============================================================

def build_sweep_tx(utxos: list, to_address: str, fee_rate: int = 10,
                   change_address: str = None):
    """Build a sweep transaction spending all UTXOs."""
    change_address = change_address or P2WPKH_ADDR
    
    total_input = sum(u['value'] for u in utxos)
    
    # Estimate size: P2WPKH input ~68 vB, output ~31 vB
    # For single input, single output (no change): ~110 vB
    # For single input, two outputs: ~142 vB
    est_size = 10 + len(utxos) * 68 + 2 * 31 + 10  # rough estimate
    fee = max(1000, est_size * fee_rate)
    
    change = total_input - fee
    
    to_script = script_pubkey_for(to_address)
    change_script = script_pubkey_for(change_address)
    
    tx = {
        'version': 2,
        'vin': [],
        'vout': [
            {
                'value': total_input - fee if change <= 546 else total_input - fee,
                'scriptPubKey': to_script
            }
        ],
        'locktime': 0
    }
    
    # If sending to_address, add the output
    # For sweep: send all to to_address, or send to_address + change
    if change > 546:
        tx['vout'] = [
            {'value': total_input - fee, 'scriptPubKey': to_script}
        ]
        # If to_address == change_address, just one output
        if to_address != change_address:
            tx['vout'].append({
                'value': change,
                'scriptPubKey': change_script
            })
    else:
        # All goes to destination (fee absorbs the change)
        tx['vout'] = [
            {'value': total_input - fee, 'scriptPubKey': to_script}
        ]
    
    for u in utxos:
        tx['vin'].append({
            'prev_txid': u['txid'],
            'prev_vout': u['vout'],
            'scriptSig': b'',
            'sequence': 0xFFFFFFFF,
            'witness': []
        })
    
    return tx, total_input, fee

def sign_sweep_tx(tx: dict, utxos: list, priv_key: int = GENESIS_KEY):
    """Sign all inputs of the sweep transaction."""
    # scriptCode for P2WPKH: OP_DUP OP_HASH160 <H160(pub)> OP_EQUALVERIFY OP_CHECKSIG
    script_code = bytes([0x76, 0xa9, 0x14]) + _PUB_HASH + bytes([0x88, 0xac])
    
    for i, vin in enumerate(tx['vin']):
        spent_value = utxos[i]['value']
        
        # Compute BIP143 sighash
        sighash = bip143_p2wpkh_sighash(tx, i, script_code, spent_value)
        
        # Sign with secp256k1
        r, s = sign(priv_key, sighash)
        sig = der_encode(r, s) + bytes([0x01])  # SIGHASH_ALL
        
        # Witness stack: [signature, compressed_pubkey]
        vin['witness'] = [sig, _COMP]
    
    return tx

def broadcast_tx(tx_hex: str):
    """Broadcast transaction via Blockstream API."""
    try:
        result = subprocess.run(
            ['curl.exe', '-s', '-d', tx_hex, 'https://blockstream.info/api/tx'],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and not result.stdout.startswith('{'):
            print(f"Broadcasted! TXID: {result.stdout.strip()}")
            return True, result.stdout.strip()
        else:
            print(f"Broadcast failed: {result.stdout}")
            return False, result.stdout
    except Exception as e:
        print(f"Broadcast error: {e}")
        return False, str(e)

# ============================================================
# Main
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='Sweep the Genesis Key')
    parser.add_argument('--to', required=True, help='Destination BTC address')
    parser.add_argument('--dry-run', action='store_true', help='Build and sign but do not broadcast')
    parser.add_argument('--fee-rate', type=int, default=10, help='Fee rate in sats/vB (default: 10)')
    args = parser.parse_args()
    
    # Fetch UTXOs
    print(f"\nFetching UTXOs for {P2WPKH_ADDR}...")
    utxos = fetch_utxos(P2WPKH_ADDR)
    
    if not utxos:
        print("No UTXOs found. The genesis key address has no BTC to sweep.")
        print(f"\nTo send BTC to this address:")
        print(f"  P2WPKH: {P2WPKH_ADDR}")
        print(f"  P2PKH:  1PYGDk8ai95x1H86VGGd3iCwD91tjUdDti")
        return
    
    total = sum(u['value'] for u in utxos) / 100_000_000
    print(f"Found {len(utxos)} UTXO(s): {total:.8f} BTC")
    
    # Build sweep transaction
    print(f"\nBuilding sweep transaction...")
    print(f"  To: {args.to}")
    print(f"  Fee rate: {args.fee_rate} sats/vB")
    
    tx, total_input, fee = build_sweep_tx(utxos, args.to, args.fee_rate)
    
    print(f"  Total input: {total_input / 100_000_000:.8f} BTC")
    print(f"  Fee: {fee / 100_000_000:.8f} BTC ({fee} sats)")
    
    for i, vout in enumerate(tx['vout']):
        print(f"  Output {i}: {vout['value'] / 100_000_000:.8f} BTC")
    
    # Sign
    print("\nSigning with genesis key...")
    tx = sign_sweep_tx(tx, utxos)
    
    # Serialize
    tx_bytes = serialize_tx(tx)
    tx_hex = tx_bytes.hex()
    wtxid = wtxid_from(tx_bytes)
    
    print(f"\n  Signed TX hex: {tx_hex[:64]}...")
    print(f"  WTXID: {wtxid}")
    print(f"  Size: {len(tx_bytes)} bytes")
    
    if args.dry_run:
        print("\n  [DRY RUN] Transaction built and signed but not broadcast.")
        print(f"  Full hex:\n{tx_hex}")
        return
    
    # Broadcast
    print("\nBroadcasting...")
    success, result = broadcast_tx(tx_hex)
    if success:
        print(f"\n  SUCCESS! Genesis key swept to {args.to}")
        print(f"  TXID: {result}")
    else:
        print(f"\n  FAILED: {result}")

if __name__ == "__main__":
    main()
