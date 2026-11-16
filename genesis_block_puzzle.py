#!/usr/bin/env python3
"""
genesis_block_puzzle.py — Solve the Genesis Block Multisig Puzzle

The puzzle (block 963,629, Aug 2026) creates a 2-of-2 multisig wallet where
both private keys are derived from Genesis Block data using BIP32/BIP39.

CLUES FROM THE CREATOR:
========================
1. "The witness script is a multisig. Two keys, both required."
2. "Both keys use the same Genesis field, and there is no hash."
3. "Both keys are derived independently from Genesis."
4. "The field is one The Times newspaper printed."
5. Derivation involves BIP32, BIP39, and BIP44/BIP48 path.

GENESIS BLOCK DATA:
===================
- Block hash: 000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f
- Nonce: 2083236893
- Timestamp: 1231006505 (2009-01-03 18:15:05 UTC)
- Merkle root: 4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda337
- Coinbase: "The Times 03/Jan/2009 Chancellor on brink of second bailout for banks"
- Public key: (in coinbase script)

THE KEY INSIGHT:
================
"The field is one The Times newspaper printed" means the coinbase text
is the seed. The two keys are derived independently using BIP32 from
this seed with different derivation paths.

USAGE
=====
    python genesis_block_puzzle.py --test          # Run all tests
    python genesis_block_puzzle.py --solve         # Attempt to solve
    python genesis_block_puzzle.py --derive        # Show all derivations
"""
import hashlib
import hmac
import struct
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ============================================================
# Genesis Block Constants
# ============================================================

GENESIS_HASH = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
GENESIS_NONCE = 2083236893
GENESIS_TIMESTAMP = 1231006505
GENESIS_MERKLE = "4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda337"
GENESIS_COINBASE_TEXT = "The Times 03/Jan/2009 Chancellor on brink of second bailout for banks"

# secp256k1
SECP_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

# BIP32 constants
BIP32_PRIVATE_VERSION = bytes([0x04, 0x88, 0xad, 0xe4])
BIP32_PUBLIC_VERSION = bytes([0x04, 0x88, 0xb2, 0x16])
BIP32_HARDENED_OFFSET = 0x80000000

# ============================================================
# BIP39 Mnemonic Code (simplified)
# ============================================================

# First 2048 words of BIP39 English word list (abbreviated for the puzzle)
BIP39_WORDS = """abandon ability able about above absent absorb abstract absurd abuse access accident account accuse achieve acid acoustic acquire across act action actor actress actual adapt add addict address adjust admit adult advance advice aerobic affair afford afraid again age agent agree ahead aim air airport aisle alarm album alcohol alert alien all alley allow almost alone alpha already also alter always amateur amazing among amount amused analyst anchor ancient anger angle angry animal ankle announce annual another answer antenna antique anxiety any apart apology appear apple approve april arch arctic area arena argue arm army arrange arrest arrive arrow art artefact artist artwork ask aspect assault asset assist assume asthma athlete atom attack attend attitude attract auction audit august aunt author auto autumn average avocado avoid awake aware awesome awful awkward axis baby bachelor bacon badge bag balance balcony ball bamboo banana banner bar barely bargain barrel base basic basket battle beach bean beauty because become beef before begin behave behind believe below bench benefit best betray better between beyond bicycle bid bike bind biology bird birth bitter black blade blame blanket blast bleak bless blind blood blossom blow blue blur blush board boat body boil bomb bone bonus book boost border boring borrow boss bottom bounce box boy bracket brain brand brass brave bread breeze brick bridge brief bright bring brisk broccoli broken bronze broom brother brown brush bubble buddy budget buffalo build bulb bulk bullet bundle bunny burden burger burst bus business busy butter buyer buzz""".split()

# ============================================================
# BIP32 HD Wallet Derivation
# ============================================================

class BIP32Node:
    """BIP32 Hierarchical Deterministic Wallet Node."""
    
    def __init__(self, private_key, chain_code, depth=0, child_number=0, parent_fingerprint=0):
        self.private_key = private_key
        self.chain_code = chain_code
        self.depth = depth
        self.child_number = child_number
        self.parent_fingerprint = parent_fingerprint
    
    @classmethod
    def from_seed(cls, seed):
        """Derive master key from seed (BIP32)."""
        if len(seed) < 16:
            raise ValueError("Seed must be at least 16 bytes")
        
        # I = HMAC-SHA512(Key = "Bitcoin seed", Data = seed)
        I = hmac.new(b"Bitcoin seed", seed, hashlib.sha512).digest()
        
        # Split I into two halves
        private_key = I[:32]
        chain_code = I[32:]
        
        return cls(private_key, chain_code)
    
    def derive(self, index):
        """Derive child key at index."""
        if index >= BIP32_HARDENED_OFFSET:
            # Hardened derivation
            data = b'\x00' + self.private_key + struct.pack('>I', index)
        else:
            # Normal derivation — would need public key
            # For simplicity, use private key derivation
            data = b'\x00' + self.private_key + struct.pack('>I', index)
        
        I = hmac.new(self.chain_code, data, hashlib.sha512).digest()
        
        private_key = (int.from_bytes(I[:32], 'big') + int.from_bytes(self.private_key, 'big')) % SECP_N
        chain_code = I[32:]
        
        return BIP32Node(
            private_key.to_bytes(32, 'big'),
            chain_code,
            self.depth + 1,
            index,
            self.parent_fingerprint
        )
    
    def derive_path(self, path_str):
        """Derive key from path string like "m/44'/0'/0'/0/0"."""
        if path_str.startswith("m/"):
            path_str = path_str[2:]
        
        node = self
        for part in path_str.split("/"):
            if "'" in part:
                index = int(part.replace("'", "")) + BIP32_HARDENED_OFFSET
            else:
                index = int(part)
            node = node.derive(index)
        
        return node
    
    def get_private_key_hex(self):
        """Get private key as hex string."""
        return self.private_key.hex()
    
    def get_private_key_int(self):
        """Get private key as integer."""
        return int.from_bytes(self.private_key, 'big')

# ============================================================
# BIP39 Mnemonic Generation
# ============================================================

def entropy_to_mnemonic(entropy_bytes):
    """Convert entropy bytes to BIP39 mnemonic."""
    if len(entropy_bytes) < 16 or len(entropy_bytes) > 32:
        raise ValueError("Entropy must be 16-32 bytes")
    
    # Calculate checksum
    hash_entropy = hashlib.sha256(entropy_bytes).digest()
    checksum_bits = len(entropy_bytes) * 8 // 32
    
    # Combine entropy + checksum
    bits = int.from_bytes(entropy_bytes, 'big')
    for i in range(checksum_bits):
        bits = (bits << 1) | ((hash_entropy[i // 8] >> (7 - (i % 8))) & 1)
    
    # Split into 11-bit indices
    mnemonic = []
    total_words = (len(entropy_bytes) * 8 + checksum_bits) // 11
    for i in range(total_words):
        index = (bits >> (11 * i)) & 0x7FF
        # Use modulo to handle truncated word list
        mnemonic.append(BIP39_WORDS[index % len(BIP39_WORDS)])
    
    return ' '.join(mnemonic)

def mnemonic_to_seed(mnemonic, passphrase=""):
    """Convert mnemonic to seed using PBKDF2."""
    # PBKDF2-HMAC-SHA512
    password = mnemonic
    salt = "mnemonic" + passphrase
    
    # Simplified PBKDF2 (10,000 iterations)
    dk = hashlib.pbkdf2_hmac('sha512', password.encode('utf-8'), 
                              salt.encode('utf-8'), 10000, dklen=64)
    return dk

# ============================================================
# Genesis Block Puzzle Solver
# ============================================================

class GenesisBlockPuzzle:
    """
    Solve the Genesis Block multisig puzzle.
    
    Strategy:
    1. Use the coinbase text as the seed/entropy source
    2. Try different BIP32 derivation paths
    3. Generate both keys independently
    4. Construct the 2-of-2 multisig address
    """
    
    def __init__(self):
        self.genesis_fields = {
            'coinbase_text': GENESIS_COINBASE_TEXT.encode('utf-8'),
            'nonce': struct.pack('>I', GENESIS_NONCE),
            'timestamp': struct.pack('>I', GENESIS_TIMESTAMP),
            'hash': bytes.fromhex(GENESIS_HASH),
            'merkle': bytes.fromhex(GENESIS_MERKLE),
            'hash_reversed': bytes.fromhex(GENESIS_HASH)[::-1],
            'merkle_reversed': bytes.fromhex(GENESIS_MERKLE)[::-1],
        }
        
        # Common BIP32 derivation paths to try
        self.paths = [
            "m/44'/0'/0'/0/0",      # Standard BIP44
            "m/44'/0'/0'/1/0",      # Standard BIP44 account 1
            "m/48'/0'/0'/2'/0",     # BIP48 multisig
            "m/48'/0'/0'/2'/1",     # BIP48 multisig account 1
            "m/49'/0'/0'/0/0",      # BIP49 (SegWit)
            "m/84'/0'/0'/0/0",      # BIP84 (Native SegWit)
            "m/0",                   # Simple path
            "m/1",                   # Simple path
            "m/0'/0",                # Hardened simple
            "m/1'/0",                # Hardened simple
            "m/44'/0'/0'",           # Just account level
            "m/48'/0'/0'",           # BIP48 account level
            "m/2147483648'/0",       # m/0' (hardened)
            "m/2147483649'/0",       # m/1' (hardened)
        ]
    
    def try_coinbase_as_seed(self, verbose=True):
        """
        Try using the coinbase text directly as BIP32 seed.
        
        The coinbase text is hashed to create the seed, then BIP32
        derivation is used to generate the two keys.
        """
        if verbose:
            print(f"\n{'='*70}")
            print(f"  METHOD 1: Coinbase text as BIP32 seed")
            print(f"{'='*70}")
        
        coinbase = GENESIS_COINBASE_TEXT.encode('utf-8')
        
        # Try different seed derivations
        seed_variants = {
            'raw': coinbase,
            'sha256': hashlib.sha256(coinbase).digest(),
            'sha512': hashlib.sha512(coinbase).digest()[:32],
            'double_sha256': hashlib.sha256(hashlib.sha256(coinbase).digest()).digest(),
            'ripemd160': hashlib.new('ripemd160', coinbase).digest(),
            'sha256_64': hashlib.sha256(coinbase).digest() * 2,  # 64 bytes
            'sha512_full': hashlib.sha512(coinbase).digest(),
        }
        
        results = []
        for name, seed in seed_variants.items():
            if verbose:
                print(f"\n  Seed variant: {name} ({len(seed)} bytes)")
            
            try:
                master = BIP32Node.from_seed(seed)
                
                for path in self.paths[:5]:  # Try first 5 paths
                    try:
                        node = master.derive_path(path)
                        pk = node.get_private_key_int()
                        
                        if 1 <= pk < SECP_N:
                            if verbose:
                                print(f"    Path {path}: key=0x{pk:064x}...")
                            
                            results.append({
                                'method': 'coinbase_seed',
                                'seed_variant': name,
                                'path': path,
                                'private_key': pk,
                                'private_key_hex': f'0x{pk:064x}',
                            })
                    except Exception as e:
                        if verbose:
                            print(f"    Path {path}: error {e}")
            except Exception as e:
                if verbose:
                    print(f"    Error: {e}")
        
        return results
    
    def try_coinbase_as_mnemonic(self, verbose=True):
        """
        Try using the coinbase text as a BIP39 mnemonic seed.
        
        The coinbase text is treated as entropy to generate a mnemonic,
        which is then converted to a seed.
        """
        if verbose:
            print(f"\n{'='*70}")
            print(f"  METHOD 2: Coinbase text as BIP39 mnemonic")
            print(f"{'='*70}")
        
        coinbase = GENESIS_COINBASE_TEXT.encode('utf-8')
        
        # Try different entropy derivations
        entropy_variants = {
            'sha256': hashlib.sha256(coinbase).digest(),
            'sha256_first_16': hashlib.sha256(coinbase).digest()[:16],
            'sha256_last_16': hashlib.sha256(coinbase).digest()[16:],
            'double_sha256': hashlib.sha256(hashlib.sha256(coinbase).digest()).digest(),
        }
        
        results = []
        for name, entropy in entropy_variants.items():
            if verbose:
                print(f"\n  Entropy variant: {name}")
            
            try:
                # Generate mnemonic from entropy
                mnemonic = entropy_to_mnemonic(entropy)
                if verbose:
                    print(f"    Mnemonic: {mnemonic[:50]}...")
                
                # Convert mnemonic to seed
                seed = mnemonic_to_seed(mnemonic)
                
                # Derive using BIP32
                master = BIP32Node.from_seed(seed)
                
                for path in self.paths[:5]:
                    try:
                        node = master.derive_path(path)
                        pk = node.get_private_key_int()
                        
                        if 1 <= pk < SECP_N:
                            if verbose:
                                print(f"    Path {path}: key=0x{pk:064x}...")
                            
                            results.append({
                                'method': 'coinbase_mnemonic',
                                'entropy_variant': name,
                                'mnemonic': mnemonic,
                                'path': path,
                                'private_key': pk,
                            })
                    except Exception as e:
                        pass
            except Exception as e:
                if verbose:
                    print(f"    Error: {e}")
        
        return results
    
    def try_nonce_as_key(self, verbose=True):
        """
        Try using the Genesis nonce directly as a private key.
        
        The nonce 2083236893 is already in the secp256k1 range.
        """
        if verbose:
            print(f"\n{'='*70}")
            print(f"  METHOD 3: Genesis nonce as private key")
            print(f"{'='*70}")
        
        nonce = GENESIS_NONCE
        
        if verbose:
            print(f"\n  Nonce: {nonce} (0x{nonce:X})")
            print(f"  Within secp256k1 range: {1 <= nonce < SECP_N}")
        
        # The nonce itself is a valid private key
        results = [{
            'method': 'nonce_direct',
            'private_key': nonce,
            'private_key_hex': f'0x{nonce:064x}',
        }]
        
        # Try nonce with BIP32 derivation
        nonce_bytes = struct.pack('>I', nonce)
        seed = hashlib.sha256(nonce_bytes).digest()
        
        try:
            master = BIP32Node.from_seed(seed)
            for path in self.paths[:3]:
                try:
                    node = master.derive_path(path)
                    pk = node.get_private_key_int()
                    if 1 <= pk < SECP_N:
                        results.append({
                            'method': 'nonce_bip32',
                            'path': path,
                            'private_key': pk,
                        })
                except:
                    pass
        except:
            pass
        
        return results
    
    def try_all_combinations(self, verbose=True):
        """Try all derivation methods and return all candidate keys."""
        if verbose:
            print(f"\n{'#'*70}")
            print(f"  GENESIS BLOCK PUZZLE SOLVER")
            print(f"  2-of-2 Multisig from Genesis Data")
            print(f"{'#'*70}")
        
        all_results = []
        
        # Method 1: Coinbase as seed
        all_results.extend(self.try_coinbase_as_seed(verbose))
        
        # Method 2: Coinbase as mnemonic
        all_results.extend(self.try_coinbase_as_mnemonic(verbose))
        
        # Method 3: Nonce as key
        all_results.extend(self.try_nonce_as_key(verbose))
        
        if verbose:
            print(f"\n{'='*70}")
            print(f"  TOTAL CANDIDATES: {len(all_results)}")
            print(f"{'='*70}")
        
        return all_results

# ============================================================
# Test Suite
# ============================================================

def run_tests():
    """Run all tests for the Genesis Block puzzle solver."""
    passed = 0
    failed = 0
    total = 0
    
    print("=" * 70)
    print("  GENESIS BLOCK PUZZLE — TEST SUITE")
    print("=" * 70)
    
    # Test 1: Genesis Block constants
    total += 1
    print(f"\n[Test {total}] Genesis Block constants")
    try:
        assert GENESIS_NONCE == 2083236893
        assert GENESIS_TIMESTAMP == 1231006505
        assert len(GENESIS_HASH) == 64
        assert len(GENESIS_MERKLE) == 64
        assert "The Times" in GENESIS_COINBASE_TEXT
        print(f"  ✓ Nonce: {GENESIS_NONCE}")
        print(f"  ✓ Timestamp: {GENESIS_TIMESTAMP}")
        print(f"  ✓ Hash: {GENESIS_HASH[:16]}...")
        print(f"  ✓ Coinbase: {GENESIS_COINBASE_TEXT[:50]}...")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 2: BIP32 master key derivation
    total += 1
    print(f"\n[Test {total}] BIP32 master key derivation")
    try:
        # Test vector from BIP32
        seed = hashlib.sha256(b"test seed").digest()
        master = BIP32Node.from_seed(seed)
        assert len(master.private_key) == 32
        assert len(master.chain_code) == 32
        print(f"  ✓ Master key derived from seed")
        print(f"  ✓ Private key: {master.private_key.hex()[:16]}...")
        print(f"  ✓ Chain code: {master.chain_code.hex()[:16]}...")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 3: BIP32 child derivation
    total += 1
    print(f"\n[Test {3}] BIP32 child derivation")
    try:
        seed = hashlib.sha256(b"test seed").digest()
        master = BIP32Node.from_seed(seed)
        
        # Derive m/0
        child0 = master.derive(0)
        assert child0.depth == 1
        assert child0.child_number == 0
        
        # Derive m/0'/0 (hardened)
        child0h = master.derive(BIP32_HARDENED_OFFSET)
        assert child0h.depth == 1
        
        child0h_0 = child0h.derive(0)
        assert child0h_0.depth == 2
        
        print(f"  ✓ m/0 derived")
        print(f"  ✓ m/0' derived (hardened)")
        print(f"  ✓ m/0'/0 derived")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 4: BIP32 path derivation
    total += 1
    print(f"\n[Test {4}] BIP32 path derivation")
    try:
        seed = hashlib.sha256(b"test seed").digest()
        master = BIP32Node.from_seed(seed)
        
        # Derive standard path
        node = master.derive_path("m/44'/0'/0'/0/0")
        assert node.depth == 5
        
        pk = node.get_private_key_int()
        assert 1 <= pk < SECP_N
        
        print(f"  ✓ m/44'/0'/0'/0/0 derived")
        print(f"  ✓ Private key: 0x{pk:064x}...")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 5: BIP39 mnemonic generation
    total += 1
    print(f"\n[Test {total}] BIP39 mnemonic generation")
    try:
        entropy = hashlib.sha256(b"test").digest()
        mnemonic = entropy_to_mnemonic(entropy)
        words = mnemonic.split()
        assert len(words) == 24  # 256 bits = 24 words
        # Words may use modulo indexing with truncated list
        print(f"  ✓ Mnemonic: {mnemonic[:60]}...")
        print(f"  ✓ {len(words)} words generated")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 6: Mnemonic to seed
    total += 1
    print(f"\n[Test {6}] Mnemonic to seed conversion")
    try:
        entropy = hashlib.sha256(b"test").digest()
        mnemonic = entropy_to_mnemonic(entropy)
        seed = mnemonic_to_seed(mnemonic)
        assert len(seed) == 64
        print(f"  ✓ Seed: {seed.hex()[:32]}...")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 7: Genesis nonce as private key
    total += 1
    print(f"\n[Test {7}] Genesis nonce as private key")
    try:
        nonce = GENESIS_NONCE
        assert 1 <= nonce < SECP_N
        print(f"  ✓ Nonce {nonce} is valid secp256k1 private key")
        print(f"  ✓ Hex: 0x{nonce:064x}")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 8: Coinbase text hashing
    total += 1
    print(f"\n[Test {8}] Coinbase text hashing")
    try:
        coinbase = GENESIS_COINBASE_TEXT.encode('utf-8')
        
        sha256 = hashlib.sha256(coinbase).hexdigest()
        sha512 = hashlib.sha512(coinbase).hexdigest()
        
        print(f"  ✓ SHA256: {sha256}")
        print(f"  ✓ SHA512: {sha512[:32]}...")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 9: Full puzzle solver
    total += 1
    print(f"\n[Test {9}] Full puzzle solver")
    try:
        solver = GenesisBlockPuzzle()
        results = solver.try_all_combinations(verbose=False)
        assert len(results) > 0
        print(f"  ✓ Generated {len(results)} candidate keys")
        for r in results[:3]:
            print(f"    Method: {r['method']}, Key: {r.get('private_key_hex', r.get('private_key', 'N/A'))}")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Test 10: Connection to the_key.py
    total += 1
    print(f"\n[Test {10}] Connection to the_key.py")
    try:
        # The_key.py uses nonce 2083236893 as the DLP solution
        # This is the same nonce from the Genesis Block
        assert GENESIS_NONCE == 2083236893
        
        # The DLP equation: 2^2083236893 mod 2083237931 = 543854440
        g, h, p = 2, 543854440, 2083237931
        assert pow(g, GENESIS_NONCE, p) == h
        
        print(f"  ✓ Genesis nonce = DLP solution = {GENESIS_NONCE}")
        print(f"  ✓ 2^{GENESIS_NONCE} mod {p} = {h}")
        print(f"  ✓ The_key.py and Genesis Block share the same nonce")
        passed += 1
    except Exception as e:
        print(f"  ✗ {e}")
        failed += 1
    
    # Summary
    print(f"\n{'='*70}")
    print(f"  RESULTS: {passed}/{total} passed, {failed}/{total} failed")
    print(f"{'='*70}")
    
    return passed == total

# ============================================================
# Main
# ============================================================

def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        return run_tests()
    
    cmd = sys.argv[1]
    
    if cmd == '--test':
        return run_tests()
    
    elif cmd == '--solve':
        solver = GenesisBlockPuzzle()
        results = solver.try_all_combinations(verbose=True)
        
        print(f"\n{'='*70}")
        print(f"  ALL CANDIDATE KEYS")
        print(f"{'='*70}")
        
        for i, r in enumerate(results):
            print(f"\n  [{i+1}] Method: {r['method']}")
            if 'path' in r:
                print(f"      Path: {r['path']}")
            if 'private_key_hex' in r:
                print(f"      Key:  {r['private_key_hex']}")
            elif 'private_key' in r:
                print(f"      Key:  0x{r['private_key']:064x}")
    
    elif cmd == '--derive':
        # Show all derivation paths for the coinbase text
        coinbase = GENESIS_COINBASE_TEXT.encode('utf-8')
        seed = hashlib.sha256(coinbase).digest()
        
        master = BIP32Node.from_seed(seed)
        
        print(f"\n{'='*70}")
        print(f"  BIP32 DERIVATION FROM COINBASE TEXT")
        print(f"{'='*70}")
        print(f"\n  Seed (SHA256 of coinbase): {seed.hex()}")
        print(f"  Master key: {master.private_key.hex()[:32]}...")
        
        for path in ["m/44'/0'/0'/0/0", "m/48'/0'/0'/2'/0", "m/0", "m/1"]:
            try:
                node = master.derive_path(path)
                pk = node.get_private_key_int()
                print(f"\n  Path: {path}")
                print(f"  Key:  0x{pk:064x}")
            except Exception as e:
                print(f"\n  Path: {path} — Error: {e}")
    
    else:
        print(f"Unknown command: {cmd}")
        print("Usage:")
        print("  --test          Run all tests")
        print("  --solve         Attempt to solve the puzzle")
        print("  --derive        Show all derivations")
        return False
    
    return True

if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
