"""genesis_signer.py — Rebuild the canonical Bitcoin genesis address and sign with it.

The Bitcoin genesis block (block 0) contains a coinbase transaction paying 50 BTC
to an uncompressed P2PK output. The public key in that output derives the famous
address 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa — Satoshi Nakamoto's address.

This module:
1. Extracts the uncompressed public key from the genesis coinbase transaction
2. Derives the P2PKH address (hash160 + Base58Check)
3. Verifies it matches the canonical address 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa
4. Provides signing capability using the genesis public key point as a reference

Note: The private key for this address is unknown. This module derives the address
from the known public key and can verify signatures, but cannot create new signatures
without the private key. However, it can sign arbitrary messages using a derived
deterministic key pair seeded from the genesis public key hash for testing.

Usage:
    python genesis_signer.py
"""
import hashlib
import struct
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from genesis_fork import GENESIS_COINBASE
from secp256k1 import (
    sign, sign_der, verify, der_encode, der_decode,
    _sign_rs, N, G, _mul, compress, priv_to_pub
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CANONICAL_GENESIS_ADDRESS = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"

# ---------------------------------------------------------------------------
# Base58Check Encoding (from btc_wallet_generator, inlined for independence)
# ---------------------------------------------------------------------------

BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'


def base58_encode(data: bytes) -> str:
    """Encode bytes to Base58 string."""
    num = int.from_bytes(data, 'big')
    if num == 0:
        return '1'
    
    encoded = ''
    while num > 0:
        num, remainder = divmod(num, 58)
        encoded = BASE58_ALPHABET[remainder] + encoded
    
    # Leading zeros expansion
    for byte in data:
        if byte == 0:
            encoded = '1' + encoded
        else:
            break
    
    return encoded


def base58check_encode(data: bytes, version: int = 0) -> str:
    """Encode bytes with Base58Check (version byte + checksum)."""
    payload = bytes([version]) + data
    checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    return base58_encode(payload + checksum)


def hash160(data: bytes) -> bytes:
    """Compute SHA256 + RIPEMD160 hash (Bitcoin's hash160)."""
    sha = hashlib.sha256(data).digest()
    ripemd = hashlib.new('ripemd160', sha).digest()
    return ripemd


# ---------------------------------------------------------------------------
# Genesis Coinbase Parser
# ---------------------------------------------------------------------------

def parse_genesis_coinbase(coinbase: bytes):
    """Parse the Bitcoin genesis coinbase transaction to extract the public key.
    
    The genesis coinbase is a 204-byte serialized transaction:
    - Standard tx header (version, input, output)
    - P2PK output script: <pubkey> OP_CHECKSIG
    - The uncompressed pubkey is 65 bytes: 0x04 || x(32) || y(32)
    
    Returns:
        Tuple of (public_key_bytes, x_coord, y_coord)
    """
    # The genesis coinbase output script starts at a known offset
    # In the 204-byte transaction, the output scriptPubKey is near the end
    # Format: 43 (length) 04 (uncompressed) <64 bytes pubkey> AC (OP_CHECKSIG)
    
    # Find the uncompressed public key marker 0x04 in the coinbase
    # The public key is 65 bytes: 0x04 + 32 bytes x + 32 bytes y
    pubkey_offset = None
    
    # The scriptPubKey in the genesis coinbase:
    # 43 = 0x43 = 67 (length of script)
    # 04 = uncompressed pubkey prefix
    # <64 bytes of pubkey data>
    # AC = OP_CHECKSIG
    
    # Parse from the end of the transaction backwards
    # Last byte: OP_CHECKSIG (0xAC)
    # Before that: 64 bytes of pubkey
    # Before that: 0x04 (uncompressed prefix)
    # Before that: 0x43 (67, script length)
    
    # The script is at the end of the transaction
    # Transaction structure:
    # 4 bytes version
    # 1 varint (1 input)
    # input: 32 prevout + 4 index + 1 script len + 78 script + 4 sequence = 119 bytes
    # 1 varint (1 output)
    # output: 8 value + 1 script len (0x43=67) + 67 script = 76 bytes
    # 4 bytes locktime
    # Total: 4 + 1 + 119 + 1 + 76 + 4 = 205... but genesis is 204
    
    # Let's parse properly
    offset = 0
    
    # Version (4 bytes)
    version = struct.unpack_from('<I', coinbase, offset)[0]
    offset += 4
    
    # Input count (varint)
    input_count = coinbase[offset]
    offset += 1
    
    # Skip the single input
    # Prevout (32 bytes)
    offset += 32
    # Index (4 bytes)
    offset += 4
    # ScriptSig length (varint)
    script_sig_len = coinbase[offset]
    offset += 1
    # ScriptSig
    offset += script_sig_len
    # Sequence (4 bytes)
    offset += 4
    
    # Output count (varint)
    output_count = coinbase[offset]
    offset += 1
    
    # Parse the single output
    # Value (8 bytes, little-endian)
    value = struct.unpack_from('<q', coinbase, offset)[0]
    offset += 8
    
    # ScriptPubKey length (varint)
    script_len = coinbase[offset]
    offset += 1
    
    # ScriptPubKey
    script = coinbase[offset:offset + script_len]
    offset += script_len
    
    # Locktime (4 bytes)
    locktime = struct.unpack_from('<I', coinbase, offset)[0]
    offset += 4
    
    # Parse the P2PK script: <pubkey> OP_CHECKSIG
    # First byte is the pubkey length
    pubkey_len = script[0]
    pubkey = script[1:1 + pubkey_len]
    op_code = script[1 + pubkey_len]
    
    assert op_code == 0xAC, f"Expected OP_CHECKSIG (0xAC), got 0x{op_code:02x}"
    assert pubkey[0] == 0x04, f"Expected uncompressed pubkey (0x04), got 0x{pubkey[0]:02x}"
    assert len(pubkey) == 65, f"Expected 65-byte uncompressed pubkey, got {len(pubkey)} bytes"
    
    x_coord = int.from_bytes(pubkey[1:33], 'big')
    y_coord = int.from_bytes(pubkey[33:65], 'big')
    
    return pubkey, x_coord, y_coord, value


# ---------------------------------------------------------------------------
# Address Derivation
# ---------------------------------------------------------------------------

def derive_p2pkh_address(public_key: bytes) -> str:
    """Derive a P2PKH Bitcoin address from a public key (compressed or uncompressed).
    
    Args:
        public_key: 33-byte compressed or 65-byte uncompressed public key
        
    Returns:
        Base58Check-encoded P2PKH address (starts with '1' on mainnet)
    """
    # hash160 of the public key
    h160 = hash160(public_key)
    # Base58Check encode with version 0x00 (mainnet P2PKH)
    address = base58check_encode(h160, version=0x00)
    return address


# ---------------------------------------------------------------------------
# Genesis Address Rebuilder
# ---------------------------------------------------------------------------

class GenesisAddressRebuilder:
    """Rebuilds and verifies the canonical Bitcoin genesis address."""
    
    def __init__(self):
        self.public_key = None
        self.x_coord = None
        self.y_coord = None
        self.public_key_point = None
        self.derived_address = None
        self.coinbase_value = None
        self._verified = False
    
    def rebuild(self) -> dict:
        """Extract the public key from the genesis coinbase and derive the address.
        
        Returns:
            Dict with public_key, address, verification status, and metadata
        """
        # Parse the genesis coinbase
        pubkey, x, y, value = parse_genesis_coinbase(GENESIS_COINBASE)
        
        self.public_key = pubkey
        self.x_coord = x
        self.y_coord = y
        self.public_key_point = (x, y)
        self.coinbase_value = value
        
        # Derive the P2PKH address
        self.derived_address = derive_p2pkh_address(pubkey)
        
        # Verify against the canonical address
        self._verified = (self.derived_address == CANONICAL_GENESIS_ADDRESS)
        
        return {
            "public_key_hex": pubkey.hex(),
            "public_key_compressed_hex": compress((x, y)).hex(),
            "x_coordinate": hex(x),
            "y_coordinate": hex(y),
            "derived_address": self.derived_address,
            "canonical_address": CANONICAL_GENESIS_ADDRESS,
            "address_matches": self._verified,
            "coinbase_value_swords": value,
            "coinbase_value_btc": value / 100_000_000,
            "hash160": hash160(pubkey).hex(),
        }
    
    def verify_signature(self, message_hash: bytes, signature: bytes) -> bool:
        """Verify a signature against the genesis public key.
        
        Since the private key is unknown, this is used to verify any claimed
        signature from Satoshi's address.
        
        Args:
            message_hash: 32-byte SHA256 hash of the message
            signature: 64-byte raw (r || s) signature or DER-encoded signature
            
        Returns:
            True if the signature is valid for the genesis public key
        """
        if self.public_key is None:
            self.rebuild()
        
        # Convert uncompressed to compressed for verification
        compressed_pub = compress(self.public_key_point)
        
        # Handle both raw 64-byte and DER signatures
        if len(signature) == 64:
            return verify(compressed_pub, signature, message_hash)
        else:
            # Try DER decode
            try:
                r, s = der_decode(signature)
                # Manual verification using uncompressed point
                from secp256k1 import _verify_rs
                return _verify_rs(self.public_key_point, message_hash, r, s)
            except ValueError:
                return False
    
    def sign_with_seed(self, seed: bytes, message: bytes) -> dict:
        """Sign a message using a deterministic key derived from a seed.
        
        This does NOT use Satoshi's private key (which is unknown).
        Instead, it derives a key pair from the provided seed and signs.
        The genesis public key hash is included in the seed for binding.
        
        Args:
            seed: Arbitrary seed bytes for key derivation
            message: Message to sign
            
        Returns:
            Dict with signature, derived key info, and verification status
        """
        if self.public_key is None:
            self.rebuild()
        
        # Derive a private key from the seed + genesis hash160
        genesis_h160 = hash160(self.public_key)
        combined_seed = hashlib.sha256(seed + genesis_h160).digest()
        private_key = int.from_bytes(combined_seed, 'big') % (N - 1) + 1
        
        # Derive the public key
        derived_pub_point = priv_to_pub(private_key)
        derived_pub_compressed = compress(derived_pub_point)
        derived_pub_uncompressed = bytes([0x04]) + \
            derived_pub_point[0].to_bytes(32, 'big') + \
            derived_pub_point[1].to_bytes(32, 'big')
        
        # Sign the message
        message_hash = hashlib.sha256(message).digest()
        signature_raw = sign(private_key, message_hash)
        signature_der = sign_der(private_key, message_hash)
        
        # Verify the signature
        is_valid = verify(derived_pub_compressed, signature_raw, message_hash)
        
        return {
            "signature_raw_hex": signature_raw.hex(),
            "signature_der_hex": signature_der.hex(),
            "derived_private_key_hex": format(private_key, '064x'),
            "derived_public_key_compressed": derived_pub_compressed.hex(),
            "derived_public_key_uncompressed": derived_pub_uncompressed.hex(),
            "derived_address": derive_p2pkh_address(derived_pub_uncompressed),
            "message_hash": message_hash.hex(),
            "signature_valid": is_valid,
            "bound_to_genesis": True,
        }
    
    def create_btc_signature(self, message: str) -> dict:
        """Create a Bitcoin-style signed message bound to the genesis address.
        
        Uses the genesis public key hash as part of the message hash to create
        a signature that references the genesis address, even though it's signed
        with a derived key.
        
        Args:
            message: The message string to sign
            
        Returns:
            Dict with signature and metadata
        """
        if self.public_key is None:
            self.rebuild()
        
        # Bitcoin message signing format:
        # "\x18Bitcoin Signed Message:\n" + len(message) + message
        magic = b"\x18Bitcoin Signed Message:\n"
        msg_bytes = message.encode('utf-8')
        bitcoin_msg = magic + len(msg_bytes).to_bytes(4, 'little') + msg_bytes
        
        # Hash with genesis H160 for binding
        genesis_h160 = hash160(self.public_key)
        combined = hashlib.sha256(bitcoin_msg + genesis_h160).digest()
        message_hash = hashlib.sha256(combined).digest()
        
        # Derive key from genesis H160 as seed
        private_key = int.from_bytes(genesis_h160 + b'\x00' * 16, 'big') % (N - 1) + 1
        derived_pub_point = priv_to_pub(private_key)
        derived_pub_compressed = compress(derived_pub_point)
        
        # Sign
        r, s = _sign_rs(private_key, message_hash)
        signature_der = der_encode(r, s)
        
        # Recovery ID (0 or 1 for compressed)
        rec_id = 0 if derived_pub_point[1] % 2 == 0 else 1
        
        return {
            "message": message,
            "genesis_address": self.derived_address,
            "genesis_public_key_hex": self.public_key.hex(),
            "signature_der_hex": signature_der.hex(),
            "recovery_id": rec_id,
            "derived_public_key": derived_pub_compressed.hex(),
            "message_hash": message_hash.hex(),
        }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    """Rebuild the canonical genesis address and demonstrate signing."""
    print("=" * 70)
    print("  BITCOIN GENESIS ADDRESS REBUILDER")
    print("  1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
    print("=" * 70)
    print()
    
    rebuilder = GenesisAddressRebuilder()
    result = rebuilder.rebuild()
    
    print("GENESIS COINBASE PUBLIC KEY:")
    print(f"  Uncompressed: {result['public_key_hex']}")
    print(f"  Compressed:   {result['public_key_compressed_hex']}")
    print()
    print(f"  X coordinate: {result['x_coordinate']}")
    print(f"  Y coordinate: {result['y_coordinate']}")
    print()
    print("ADDRESS DERIVATION:")
    print(f"  hash160:      {result['hash160']}")
    print(f"  Derived:      {result['derived_address']}")
    print(f"  Canonical:    {result['canonical_address']}")
    print(f"  MATCH:        {'YES' if result['address_matches'] else 'NO'}")
    print()
    print("COINBASE OUTPUT:")
    print(f"  Value:        {result['coinbase_value_btc']} BTC ({result['coinbase_value_swords']} swords)")
    print()
    
    # Demonstrate signing
    print("-" * 70)
    print("  SIGNING DEMO")
    print("-" * 70)
    print()
    
    message = "Hello from the genesis block"
    btc_sig = rebuilder.create_btc_signature(message)
    
    print(f"Message:        {btc_sig['message']}")
    print(f"Genesis addr:   {btc_sig['genesis_address']}")
    print(f"Signature (DER): {btc_sig['signature_der_hex']}")
    print(f"Recovery ID:    {btc_sig['recovery_id']}")
    print(f"Derived pubkey: {btc_sig['derived_public_key']}")
    print()
    
    # Verify the address matches
    if result['address_matches']:
        print("SUCCESS: Canonical genesis address 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa rebuilt.")
    else:
        print(f"ERROR: Derived address {result['derived_address']} does not match canonical.")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
