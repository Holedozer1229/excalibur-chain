#!/usr/bin/env python3
"""
BIP39 Genesis Seed Hunter
==========================

Exhaustively searches for valid BIP39 mnemonics hidden in the Bitcoin Genesis block.

The core insight: a valid BIP39 mnemonic must pass the checksum. For 12 words,
the first 11 words determine 128 bits of entropy, and the 12th word must encode
the first 4 bits of SHA-256(entropy). This means only 1 in 16 random 12-word
sequences is valid.

This hunter tries every conceivable derivation method from the Genesis block:
1. Gematria values as entropy bytes
2. Hebrew letter indices as entropy
3. Pictograph hash combinations
4. Lambda matrix transformations on gematria
5. Retrocausal phase-shifted entropy
6. All subsets and permutations of the 32 pictographs
7. Domain-separated SHA-256 of all Genesis data combinations
8. The Messerene operator pattern applied to BIP39 indices
9. tau(28) and 691-derived entropy
10. Brute-force checksum completion for near-misses

The goal: find if Satoshi encoded a valid BIP39 mnemonic in the Genesis block.
"""

import hashlib
import hmac
import struct
import itertools
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set

# ============================================================
# CONSTANTS
# ============================================================

GENESIS_HASH = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
GENESIS_NONCE = 2083236893
GENESIS_TIMESTAMP = 1231006505
TAU_28 = 24647168  # Corrected tau(28)
RAMANUJAN_PRIME = 691

# The 32 pictographs from the Genesis block's Sumerian decoding
GENESIS_PICTOGRAPHS = [
    "A sword",           # Zayin (7)
    "A camel",           # Gimel (3)
    "A courtyard",       # Het (8)
    "Fire",              # Shin (300)
    "A door",            # Dalet (4)
    "A courtyard",       # Het (8)
    "A staff",           # Samekh (60)
    "A head",            # Resh (200)
    "A door",            # Dalet (4)
    "A hand",            # Yod (10)
    "A head",            # Resh (200)
    "A fish",            # Nun (50)
    "A shepherd's crook", # Lamed (30)
    "Water",             # Mem (40)
    "A fish",            # Nun (50)
    "A fish",            # Nun (50)
    "A shepherd's crook", # Lamed (30)
    "A courtyard",       # Het (8)
    "A house",           # Bet (2)
    "A hand",            # Yod (10)
    "A camel",           # Gimel (3)
    "A hand",            # Yod (10)
    "A coiled body",     # Qof (100)
    "A palm",            # Kaf (20)
    "A camel",           # Gimel (3)
    "A coiled body",     # Qof (100)
    "A window",          # He (5)
    "A shepherd's crook", # Lamed (30)
    "A window",          # He (5)
    "A courtyard",       # Het (8)
    "A shepherd's crook", # Lamed (30)
    "A house",           # Bet (2)
]

GENESIS_LETTERS = [
    "Zayin", "Gimel", "Het", "Shin", "Dalet", "Het", "Samekh", "Resh",
    "Dalet", "Yod", "Resh", "Nun", "Lamed", "Mem", "Nun", "Nun",
    "Lamed", "Het", "Bet", "Yod", "Gimel", "Yod", "Qof", "Kaf",
    "Gimel", "Qof", "He", "Lamed", "He", "Het", "Lamed", "Bet",
]

GENESIS_GEMATRIA = [7, 3, 8, 300, 4, 8, 60, 200, 4, 10, 200, 50, 30, 40, 50, 50,
                    30, 8, 2, 10, 3, 10, 100, 20, 3, 100, 5, 30, 5, 8, 30, 2]

# Lambda matrix from retrocausal entropy well
LAMBDA_MATRIX = [[1, 1, 1], [1, 0, -1], [-1, -1, -1]]
NULL_SPACE = [1, -2, 1]  # Null vector of lambda matrix

# BIP39 word list — reuse the already-loaded list from bip39_pictographic
# to avoid re-reading files (which fails in PyInstaller bundles).
try:
    from sphinx_os.nexus.bip39_pictographic import BIP39_WORDS as _BIP39_WORDS
    BIP39_WORDS = _BIP39_WORDS
except ImportError:
    # Fallback: load from file (development mode only)
    import os as _os
    _here = _os.path.dirname(_os.path.abspath(__file__))
    _file_path = _os.path.join(_here, '..', '..', 'excalibur_wallet', 'bip39_english.txt')
    with open(_file_path) as _f:
        BIP39_WORDS = [w.strip() for w in _f if w.strip()]
    del _os, _here, _file_path, _f

assert len(BIP39_WORDS) == 2048
BIP39_INDEX = {w: i for i, w in enumerate(BIP39_WORDS)}


# ============================================================
# BIP39 Core Functions
# ============================================================

def bip39_entropy_to_mnemonic(entropy: bytes) -> str:
    """Convert entropy bytes to BIP39 mnemonic string."""
    if len(entropy) not in (16, 20, 24, 28, 32):
        raise ValueError(f"Entropy must be 16-32 bytes, got {len(entropy)}")
    
    ent_bits = len(entropy) * 8
    cs_bits = ent_bits // 32
    h = hashlib.sha256(entropy).digest()
    
    data = int.from_bytes(entropy, 'big') << cs_bits
    data |= h[0] >> (8 - cs_bits)
    
    total = ent_bits + cs_bits
    words = []
    for i in range(total // 11):
        shift = total - 11 * (i + 1)
        words.append(BIP39_WORDS[(data >> shift) & 0x7FF])
    
    return " ".join(words)


def bip39_mnemonic_to_entropy(mnemonic: str) -> bytes:
    """Convert BIP39 mnemonic string back to entropy bytes."""
    parts = mnemonic.strip().split()
    word_count = len(parts)
    
    if word_count not in (12, 15, 18, 21, 24):
        raise ValueError(f"Mnemonic must be 12, 15, 18, 21, or 24 words, got {word_count}")
    
    data = 0
    for w in parts:
        if w not in BIP39_INDEX:
            raise ValueError(f"Not a BIP39 word: {w!r}")
        data = (data << 11) | BIP39_INDEX[w]
    
    total_bits = word_count * 11
    cs_bits = total_bits // 33
    ent_bits = total_bits - cs_bits
    
    entropy = (data >> cs_bits).to_bytes(ent_bits // 8, 'big')
    checksum = data & ((1 << cs_bits) - 1)
    
    h = hashlib.sha256(entropy).digest()
    expected_cs = h[0] >> (8 - cs_bits)
    
    if checksum != expected_cs:
        raise ValueError("Mnemonic checksum mismatch")
    
    return entropy


def validate_bip39(mnemonic: str) -> bool:
    """Validate a BIP39 mnemonic."""
    try:
        bip39_mnemonic_to_entropy(mnemonic)
        return True
    except (ValueError, TypeError):
        return False


def bip39_mnemonic_to_seed(mnemonic: str, passphrase: str = "") -> bytes:
    """Derive BIP39 seed from mnemonic."""
    mnemonic = mnemonic.strip()
    salt = ("mnemonic" + passphrase).encode('utf-8')
    return hashlib.pbkdf2_hmac('sha512', mnemonic.encode('utf-8'), salt, 2048, 64)


# ============================================================
# Seed Hunter
# ============================================================

@dataclass
class SeedCandidate:
    """A candidate BIP39 seed found by the hunter."""
    mnemonic: str
    entropy_hex: str
    seed_hex: str
    derivation_method: str
    word_count: int
    pictograph_indices: List[int] = field(default_factory=list)
    significance: str = ""


class BIP39SeedHunter:
    """
    Exhaustively searches for valid BIP39 mnemonics hidden in the
    Bitcoin Genesis block using every conceivable derivation method.
    """
    
    def __init__(self):
        self.found: List[SeedCandidate] = []
        self.attempts = 0
        self.methods_tried: Set[str] = set()
    
    def _try_entropy(self, entropy: bytes, method: str, 
                     pict_indices: List[int] = None, significance: str = "") -> bool:
        """Try converting entropy to mnemonic and validate."""
        self.attempts += 1
        
        # Try 16 bytes (12-word mnemonic)
        if len(entropy) >= 16:
            for start in range(0, len(entropy) - 15, 1):
                ent_16 = entropy[start:start + 16]
                mnemonic = bip39_entropy_to_mnemonic(ent_16)
                if validate_bip39(mnemonic):
                    seed = bip39_mnemonic_to_seed(mnemonic)
                    candidate = SeedCandidate(
                        mnemonic=mnemonic,
                        entropy_hex=ent_16.hex(),
                        seed_hex=seed.hex(),
                        derivation_method=f"{method}[offset={start}]",
                        word_count=12,
                        pictograph_indices=pict_indices or [],
                        significance=significance,
                    )
                    self.found.append(candidate)
                    return True
        
        # Try 32 bytes (24-word mnemonic)
        if len(entropy) >= 32:
            ent_32 = entropy[:32]
            mnemonic = bip39_entropy_to_mnemonic(ent_32)
            if validate_bip39(mnemonic):
                seed = bip39_mnemonic_to_seed(mnemonic)
                candidate = SeedCandidate(
                    mnemonic=mnemonic,
                    entropy_hex=ent_32.hex(),
                    seed_hex=seed.hex(),
                    derivation_method=method,
                    word_count=24,
                    pictograph_indices=pict_indices or [],
                    significance=significance,
                )
                self.found.append(candidate)
                return True
        
        return False
    
    def hunt_gematria_entropy(self):
        """Method 1: Gematria values as entropy bytes."""
        self.methods_tried.add("gematria_entropy")
        
        # Pack gematria values into bytes
        gem_bytes = b''
        for g in GENESIS_GEMATRIA:
            gem_bytes += g.to_bytes(2, 'big')
        
        # Try as-is (64 bytes, take first 16/32)
        self._try_entropy(gem_bytes[:16], "gematria_direct_16", 
                         significance="Gematria values as 16-byte entropy")
        self._try_entropy(gem_bytes[:32], "gematria_direct_32",
                         significance="Gematria values as 32-byte entropy")
        
        # Try mod 256 for each
        mod_bytes = bytes(g % 256 for g in GENESIS_GEMATRIA)
        self._try_entropy(mod_bytes[:16], "gematria_mod256_16",
                         significance="Gematria mod 256 as entropy")
        self._try_entropy(mod_bytes[:32], "gematria_mod256_32",
                         significance="Gematria mod 256 as 32-byte entropy")
        
        # Try reversed
        self._try_entropy(gem_bytes[:16][::-1], "gematria_reversed_16",
                         significance="Reversed gematria bytes")
        self._try_entropy(gem_bytes[:32][::-1], "gematria_reversed_32",
                         significance="Reversed gematria 32 bytes")
    
    def hunt_letter_entropy(self):
        """Method 2: Hebrew letter indices as entropy."""
        self.methods_tried.add("letter_entropy")
        
        # Letter indices (A=0, B=1, ... but Hebrew letters have specific positions)
        letter_order = {
            "Aleph": 0, "Bet": 1, "Gimel": 2, "Dalet": 3, "He": 4,
            "Vav": 5, "Zayin": 6, "Het": 7, "Tet": 8, "Yod": 9,
            "Kaf": 10, "Lamed": 11, "Mem": 12, "Nun": 13, "Samekh": 14,
            "Ayin": 15, "Qof": 16, "Resh": 17, "Shin": 18, "Tav": 19,
        }
        
        indices = [letter_order.get(l, 0) for l in GENESIS_LETTERS]
        idx_bytes = bytes(indices)
        
        self._try_entropy(idx_bytes[:16], "letter_index_16",
                         significance="Hebrew letter indices as entropy")
        self._try_entropy(idx_bytes[:32], "letter_index_32",
                         significance="Hebrew letter indices as 32-byte entropy")
        
        # Reversed
        self._try_entropy(idx_bytes[:16][::-1], "letter_reversed_16",
                         significance="Reversed letter indices")
    
    def hunt_pictograph_hash(self):
        """Method 3: SHA-256 of each pictograph, combined."""
        self.methods_tried.add("pictograph_hash")
        
        # Hash each pictograph and concatenate
        combined = b''
        for pict in GENESIS_PICTOGRAPHS:
            h = hashlib.sha256(pict.encode()).digest()
            combined += h[:4]  # First 4 bytes of each hash
        
        self._try_entropy(combined[:16], "pict_hash_4byte_16",
                         significance="4-byte hash per pictograph")
        self._try_entropy(combined[:32], "pict_hash_4byte_32",
                         significance="4-byte hash per pictograph, 32 bytes")
        
        # Full hash concatenation
        full_combined = b''
        for pict in GENESIS_PICTOGRAPHS:
            full_combined += hashlib.sha256(pict.encode()).digest()
        
        self._try_entropy(full_combined[:16], "pict_full_hash_16",
                         significance="Full SHA-256 per pictograph")
        self._try_entropy(full_combined[:32], "pict_full_hash_32",
                         significance="Full SHA-256 per pictograph, 32 bytes")
    
    def hunt_lambda_transform(self):
        """Method 4: Lambda matrix transformation on gematria triples."""
        self.methods_tried.add("lambda_transform")
        
        # Group gematria into triples and apply lambda matrix
        result = []
        for i in range(0, len(GENESIS_GEMATRIA) - 2, 3):
            triple = GENESIS_GEMATRIA[i:i+3]
            # Apply lambda matrix: y = L * x
            y0 = LAMBDA_MATRIX[0][0]*triple[0] + LAMBDA_MATRIX[0][1]*triple[1] + LAMBDA_MATRIX[0][2]*triple[2]
            y1 = LAMBDA_MATRIX[1][0]*triple[0] + LAMBDA_MATRIX[1][1]*triple[1] + LAMBDA_MATRIX[1][2]*triple[2]
            y2 = LAMBDA_MATRIX[2][0]*triple[0] + LAMBDA_MATRIX[2][1]*triple[1] + LAMBDA_MATRIX[2][2]*triple[2]
            result.extend([y0, y1, y2])
        
        # Convert to bytes (abs value mod 256)
        lam_bytes = bytes(abs(r) % 256 for r in result)
        
        self._try_entropy(lam_bytes[:16], "lambda_transform_16",
                         significance="Lambda matrix on gematria triples")
        self._try_entropy(lam_bytes[:32], "lambda_transform_32",
                         significance="Lambda matrix on gematria triples, 32 bytes")
    
    def hunt_retrocausal_phase(self):
        """Method 5: Retrocausal phase-shifted entropy."""
        self.methods_tried.add("retrocausal_phase")
        
        # Phase constant from retrocausal entropy well
        phase = 0.33333333326
        
        # Apply phase shift to gematria values
        import math
        shifted = []
        for g in GENESIS_GEMATRIA:
            s = int(g * math.atan2(phase, 1 - phase)) % 256
            shifted.append(s)
        
        phase_bytes = bytes(shifted)
        self._try_entropy(phase_bytes[:16], "retrocausal_phase_16",
                         significance="Retrocausal arctan2 phase shift on gematria")
        self._try_entropy(phase_bytes[:32], "retrocausal_phase_32",
                         significance="Retrocausal phase shift, 32 bytes")
    
    def hunt_genesis_data_combinations(self):
        """Method 6: All SHA-256 combinations of Genesis data."""
        self.methods_tried.add("genesis_data_combinations")
        
        # Various combinations of Genesis block data
        combos = [
            (GENESIS_HASH.encode(), "hash_only"),
            (struct.pack('>I', GENESIS_NONCE), "nonce_only"),
            (struct.pack('>I', GENESIS_TIMESTAMP), "timestamp_only"),
            (GENESIS_HASH.encode() + struct.pack('>I', GENESIS_NONCE), "hash+nonce"),
            (GENESIS_HASH.encode() + struct.pack('>I', GENESIS_TIMESTAMP), "hash+timestamp"),
            (struct.pack('>I', GENESIS_NONCE) + struct.pack('>I', GENESIS_TIMESTAMP), "nonce+timestamp"),
            (GENESIS_HASH.encode() + struct.pack('>I', GENESIS_NONCE) + struct.pack('>I', GENESIS_TIMESTAMP), "all_three"),
            (struct.pack('>I', GENESIS_NONCE)[::-1], "nonce_le"),
            (struct.pack('>I', GENESIS_TIMESTAMP)[::-1], "timestamp_le"),
        ]
        
        for data, name in combos:
            h = hashlib.sha256(data).digest()
            self._try_entropy(h[:16], f"genesis_{name}_16",
                             significance=f"SHA-256({name}) as entropy")
            self._try_entropy(h, f"genesis_{name}_32",
                             significance=f"SHA-256({name}) as 32-byte entropy")
            
            # Double hash
            h2 = hashlib.sha256(h).digest()
            self._try_entropy(h2[:16], f"genesis_{name}_double_16",
                             significance=f"Double SHA-256({name})")
            self._try_entropy(h2, f"genesis_{name}_double_32",
                             significance=f"Double SHA-256({name}), 32 bytes")
    
    def hunt_tau691_entropy(self):
        """Method 7: tau(28) and Ramanujan prime 691-derived entropy."""
        self.methods_tried.add("tau691_entropy")
        
        # tau(28) = 24647168, 691
        tau_bytes = TAU_28.to_bytes(8, 'big')
        prime_bytes = RAMANUJAN_PRIME.to_bytes(4, 'big')
        
        combined = tau_bytes + prime_bytes
        self._try_entropy(combined[:16], "tau691_combined_16",
                         significance=f"tau(28)={TAU_28} + 691 as entropy")
        
        # Hash of tau(28) and 691
        h = hashlib.sha256(combined).digest()
        self._try_entropy(h[:16], "tau691_hash_16",
                         significance="SHA-256(tau(28)+691)")
        self._try_entropy(h, "tau691_hash_32",
                         significance="SHA-256(tau(28)+691), 32 bytes")
        
        # tau(28) mod 691
        mod_val = TAU_28 % RAMANUJAN_PRIME  # Should be 580
        mod_bytes = mod_val.to_bytes(4, 'big')
        self._try_entropy(mod_bytes + tau_bytes[:12], "tau691_mod_16",
                         significance=f"tau(28) mod 691 = {mod_val}")
        
        # tau(28) * 691
        product = TAU_28 * RAMANUJAN_PRIME
        prod_bytes = product.to_bytes(12, 'big')
        self._try_entropy(prod_bytes[:16], "tau691_product_16",
                         significance=f"tau(28) * 691 = {product}")
    
    def hunt_messerene_pattern(self):
        """Method 8: Messerene operator pattern on BIP39 indices."""
        self.methods_tried.add("messerene_pattern")
        
        # The Messerene pattern: A1B3C5D7E9F8D6C4B2...
        # Apply to gematria values to get BIP39 indices
        pattern_indices = []
        for i, g in enumerate(GENESIS_GEMATRIA):
            # Messerene-style: interleave high and low bits
            idx = (g * (i + 1)) % 2048
            pattern_indices.append(idx)
        
        # Convert indices to bytes
        idx_bytes = b''
        for idx in pattern_indices:
            idx_bytes += idx.to_bytes(2, 'big')
        
        self._try_entropy(idx_bytes[:16], "messerene_16",
                         significance="Messerene pattern on gematria")
        self._try_entropy(idx_bytes[:32], "messerene_32",
                         significance="Messerene pattern, 32 bytes")
    
    def hunt_null_space_entropy(self):
        """Method 9: Null space [1,-2,1] projection on gematria."""
        self.methods_tried.add("null_space_entropy")
        
        # Project gematria triples onto null space [1, -2, 1]
        projections = []
        for i in range(0, len(GENESIS_GEMATRIA) - 2, 3):
            triple = GENESIS_GEMATRIA[i:i+3]
            proj = NULL_SPACE[0]*triple[0] + NULL_SPACE[1]*triple[1] + NULL_SPACE[2]*triple[2]
            projections.append(abs(proj))
        
        proj_bytes = b''
        for p in projections:
            proj_bytes += p.to_bytes(4, 'big')
        
        self._try_entropy(proj_bytes[:16], "null_space_16",
                         significance="Null space [1,-2,1] projection")
        self._try_entropy(proj_bytes[:32], "null_space_32",
                         significance="Null space projection, 32 bytes")
    
    def hunt_checksum_completion(self):
        """Method 10: Brute-force checksum completion for near-misses."""
        self.methods_tried.add("checksum_completion")
        
        # For each possible 11-word prefix from pictograph-derived words,
        # try all 16 possible checksum values for the 12th word
        # This is the key method: it finds valid mnemonics where the
        # first 11 words are derived from Genesis data
        
        # Get all BIP39 words that map to pictographs
        pict_words = set()
        for pict in GENESIS_PICTOGRAPHS:
            # Direct mapping
            key_words = pict.lower().replace("a ", "").replace("an ", "").replace("the ", "").split()
            for kw in key_words:
                for w in BIP39_WORDS:
                    if kw == w or kw in w or w in kw:
                        pict_words.add(w)
        
        # Also add gematria-derived words
        for g in GENESIS_GEMATRIA:
            idx = g % 2048
            pict_words.add(BIP39_WORDS[idx])
        
        # Try all 11-word combinations from pict_words (limited search)
        # This is expensive, so we limit to top candidates
        pict_word_list = sorted(pict_words, key=lambda w: BIP39_INDEX[w])
        
        # Try the first 11 pictograph-derived words as a prefix
        for start_idx in range(0, len(pict_word_list) - 10):
            prefix_words = pict_word_list[start_idx:start_idx + 11]
            
            # Build entropy from first 11 words
            data = 0
            for w in prefix_words:
                data = (data << 11) | BIP39_INDEX[w]
            
            # Extract 128-bit entropy
            entropy_128 = (data >> 3).to_bytes(16, 'big')
            
            # Compute checksum
            h = hashlib.sha256(entropy_128).digest()
            cs_bits = h[0] >> 4  # 4-bit checksum for 128-bit entropy
            
            # The 12th word index is the last 4 bits of entropy + checksum
            last_4_bits = (data & 0x7) << 4  # Last 4 bits of 11th word's remaining bits
            word_12_idx = last_4_bits | cs_bits
            
            if word_12_idx < 2048:
                word_12 = BIP39_WORDS[word_12_idx]
                mnemonic = " ".join(prefix_words + [word_12])
                
                if validate_bip39(mnemonic):
                    seed = bip39_mnemonic_to_seed(mnemonic)
                    candidate = SeedCandidate(
                        mnemonic=mnemonic,
                        entropy_hex=entropy_128.hex(),
                        seed_hex=seed.hex(),
                        derivation_method="checksum_completion",
                        word_count=12,
                        pictograph_indices=list(range(start_idx, start_idx + 11)),
                        significance=f"11 pictograph words + computed checksum → {word_12}",
                    )
                    self.found.append(candidate)
    
    def hunt_hmac_derivations(self):
        """Method 11: HMAC-SHA256 derivations from all Genesis data."""
        self.methods_tried.add("hmac_derivations")
        
        keys = [
            b'Bitcoin', b'genesis', b'satoshi', b'block0',
            b'tau28', b'691', b'ramanujan', b'pictograph',
            b'bip39', b'seed', b'lambda', b'nullspace',
            GENESIS_HASH.encode(),
        ]
        
        messages = [
            struct.pack('>I', GENESIS_NONCE),
            struct.pack('>I', GENESIS_TIMESTAMP),
            bytes(g % 256 for g in GENESIS_GEMATRIA[:32]),
            bytes(g % 256 for g in GENESIS_GEMATRIA),
        ]
        
        for key in keys:
            for msg in messages:
                h = hmac.new(key, msg, hashlib.sha256).digest()
                self._try_entropy(h[:16], f"hmac_{key[:8].decode('ascii', errors='replace')}_16",
                                 significance=f"HMAC-SHA256({key[:8]})")
                self._try_entropy(h, f"hmac_{key[:8].decode('ascii', errors='replace')}_32",
                                 significance=f"HMAC-SHA256({key[:8]}), 32 bytes")
    
    def hunt_subset_permutations(self):
        """Method 12: Subsets of 12/24 pictographs in different orders."""
        self.methods_tried.add("subset_permutations")
        
        # Try all combinations of 12 pictographs from 32
        # C(32,12) = 225,792,864 — too many, so sample strategically
        
        # Try consecutive subsets of 12
        for start in range(0, 32 - 11):
            subset = GENESIS_PICTOGRAPHS[start:start + 12]
            
            # Hash the subset
            combined = b''
            for pict in subset:
                combined += hashlib.sha256(pict.encode()).digest()[:4]
            
            self._try_entropy(combined[:16], f"subset_{start}_16",
                             pict_indices=list(range(start, start + 12)),
                             significance=f"Consecutive pictographs {start}-{start+11}")
        
        # Try every 3rd pictograph (12 total)
        every_3rd = GENESIS_PICTOGRAPHS[::3][:12]
        combined = b''
        for pict in every_3rd:
            combined += hashlib.sha256(pict.encode()).digest()[:4]
        self._try_entropy(combined[:16], "every_3rd_16",
                         pict_indices=list(range(0, 36, 3)),
                         significance="Every 3rd pictograph")
        
        # Try every 2nd pictograph (16 total, take 12)
        every_2nd = GENESIS_PICTOGRAPHS[::2][:12]
        combined = b''
        for pict in every_2nd:
            combined += hashlib.sha256(pict.encode()).digest()[:4]
        self._try_entropy(combined[:16], "every_2nd_16",
                         pict_indices=list(range(0, 24, 2)),
                         significance="Every 2nd pictograph")
    
    def hunt_reversed_entropy(self):
        """Method 13: Reversed entropy from all methods."""
        self.methods_tried.add("reversed_entropy")
        
        # For each method that produced entropy, try the reversed version
        gem_bytes = b''
        for g in GENESIS_GEMATRIA:
            gem_bytes += g.to_bytes(2, 'big')
        
        self._try_entropy(gem_bytes[:16][::-1], "reversed_gem_16",
                         significance="Reversed gematria entropy")
        self._try_entropy(gem_bytes[:32][::-1], "reversed_gem_32",
                         significance="Reversed gematria 32 bytes")
        
        # Reversed letter indices
        letter_order = {
            "Aleph": 0, "Bet": 1, "Gimel": 2, "Dalet": 3, "He": 4,
            "Vav": 5, "Zayin": 6, "Het": 7, "Tet": 8, "Yod": 9,
            "Kaf": 10, "Lamed": 11, "Mem": 12, "Nun": 13, "Samekh": 14,
            "Ayin": 15, "Qof": 16, "Resh": 17, "Shin": 18, "Tav": 19,
        }
        indices = bytes([letter_order.get(l, 0) for l in GENESIS_LETTERS])
        self._try_entropy(indices[:16][::-1], "reversed_letter_16",
                         significance="Reversed letter indices")
    
    def hunt_bip39_index_entropy(self):
        """Method 14: BIP39 word indices as entropy."""
        self.methods_tried.add("bip39_index_entropy")
        
        # Use gematria mod 2048 as BIP39 indices, then pack as 11-bit values
        indices = [g % 2048 for g in GENESIS_GEMATRIA]
        
        # Pack 12 indices into 128+4 = 132 bits
        data_12 = 0
        for idx in indices[:12]:
            data_12 = (data_12 << 11) | idx
        
        # Extract 128-bit entropy
        entropy_128 = (data_12 >> 4).to_bytes(16, 'big')
        
        # Check if this entropy produces a valid mnemonic
        mnemonic = bip39_entropy_to_mnemonic(entropy_128)
        if validate_bip39(mnemonic):
            seed = bip39_mnemonic_to_seed(mnemonic)
            candidate = SeedCandidate(
                mnemonic=mnemonic,
                entropy_hex=entropy_128.hex(),
                seed_hex=seed.hex(),
                derivation_method="bip39_index_direct",
                word_count=12,
                pictograph_indices=list(range(12)),
                significance="Gematria mod 2048 as BIP39 indices",
            )
            self.found.append(candidate)
        
        # Also try 24 indices
        data_24 = 0
        for idx in indices[:24]:
            data_24 = (data_24 << 11) | idx
        
        entropy_256 = (data_24 >> 8).to_bytes(32, 'big')
        mnemonic_24 = bip39_entropy_to_mnemonic(entropy_256)
        if validate_bip39(mnemonic_24):
            seed = bip39_mnemonic_to_seed(mnemonic_24)
            candidate = SeedCandidate(
                mnemonic=mnemonic_24,
                entropy_hex=entropy_256.hex(),
                seed_hex=seed.hex(),
                derivation_method="bip39_index_24",
                word_count=24,
                pictograph_indices=list(range(24)),
                significance="Gematria mod 2048 as 24 BIP39 indices",
            )
            self.found.append(candidate)
    
    def hunt_all(self):
        """Run all hunting methods."""
        self.hunt_gematria_entropy()
        self.hunt_letter_entropy()
        self.hunt_pictograph_hash()
        self.hunt_lambda_transform()
        self.hunt_retrocausal_phase()
        self.hunt_genesis_data_combinations()
        self.hunt_tau691_entropy()
        self.hunt_messerene_pattern()
        self.hunt_null_space_entropy()
        self.hunt_checksum_completion()
        self.hunt_hmac_derivations()
        self.hunt_subset_permutations()
        self.hunt_reversed_entropy()
        self.hunt_bip39_index_entropy()
        
        return self.found
    
    def get_summary(self) -> Dict:
        """Get a summary of the hunt results."""
        return {
            "total_attempts": self.attempts,
            "methods_tried": len(self.methods_tried),
            "methods_list": sorted(self.methods_tried),
            "seeds_found": len(self.found),
            "found_candidates": [
                {
                    "mnemonic": c.mnemonic[:80] + "..." if len(c.mnemonic) > 80 else c.mnemonic,
                    "derivation": c.derivation_method,
                    "word_count": c.word_count,
                    "significance": c.significance,
                    "seed_hex": c.seed_hex[:32] + "...",
                }
                for c in self.found
            ],
        }


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    print("=" * 80)
    print("BIP39 GENESIS SEED HUNTER")
    print("Searching for valid BIP39 mnemonics in the Bitcoin Genesis block")
    print("=" * 80)
    print()
    
    hunter = BIP39SeedHunter()
    found = hunter.hunt_all()
    
    summary = hunter.get_summary()
    
    print(f"Total attempts: {summary['total_attempts']}")
    print(f"Methods tried: {summary['methods_tried']}")
    print(f"Seeds found: {summary['seeds_found']}")
    print()
    
    if found:
        print("FOUND VALID BIP39 MNEMONICS:")
        print("-" * 80)
        for i, candidate in enumerate(found):
            print(f"\nCandidate {i + 1}:")
            print(f"  Method: {candidate.derivation_method}")
            print(f"  Words: {candidate.word_count}")
            print(f"  Mnemonic: {candidate.mnemonic}")
            print(f"  Entropy: {candidate.entropy_hex}")
            print(f"  Seed: {candidate.seed_hex}")
            print(f"  Significance: {candidate.significance}")
    else:
        print("No valid BIP39 mnemonics found in the Genesis block.")
        print()
        print("This means either:")
        print("1. No BIP39 mnemonic was intentionally encoded in the Genesis block")
        print("2. The encoding method is more complex than any tried here")
        print("3. The mnemonic uses a non-standard BIP39 word list or derivation")
    
    print()
    print("=" * 80)
    print(f"Hunt complete: {summary['total_attempts']} attempts, {summary['seeds_found']} found")
    print("=" * 80)
