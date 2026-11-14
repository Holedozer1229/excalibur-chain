#!/usr/bin/env python3
"""
Unit tests for BIP39 Genesis Seed Hunter
==========================================

Tests cover:
- BIP39 core functions (entropy↔mnemonic conversion, validation, seed derivation)
- SeedCandidate dataclass
- BIP39SeedHunter class initialization and methods
- All 14 hunting methods
- Checksum completion method
- Summary generation
"""

import unittest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sphinx_os.nexus.bip39_seed_hunter import (
    BIP39SeedHunter,
    SeedCandidate,
    bip39_entropy_to_mnemonic,
    bip39_mnemonic_to_entropy,
    validate_bip39,
    bip39_mnemonic_to_seed,
    BIP39_WORDS,
    BIP39_INDEX,
    GENESIS_GEMATRIA,
    GENESIS_LETTERS,
    GENESIS_PICTOGRAPHS,
    GENESIS_HASH,
    GENESIS_NONCE,
    GENESIS_TIMESTAMP,
    TAU_28,
    RAMANUJAN_PRIME,
    LAMBDA_MATRIX,
    NULL_SPACE,
)


class TestBIP39Core(unittest.TestCase):
    """Test BIP39 core functions."""
    
    def test_word_list_size(self):
        """BIP39 word list has exactly 2048 words."""
        self.assertEqual(len(BIP39_WORDS), 2048)
    
    def test_word_list_unique(self):
        """All BIP39 words are unique."""
        self.assertEqual(len(set(BIP39_WORDS)), 2048)
    
    def test_word_index_mapping(self):
        """BIP39_INDEX maps each word to its correct index."""
        for i, word in enumerate(BIP39_WORDS):
            self.assertEqual(BIP39_INDEX[word], i)
    
    def test_entropy_to_mnemonic_12_words(self):
        """16 bytes entropy produces 12-word mnemonic."""
        entropy = b'\x00' * 16
        mnemonic = bip39_entropy_to_mnemonic(entropy)
        words = mnemonic.split()
        self.assertEqual(len(words), 12)
    
    def test_entropy_to_mnemonic_24_words(self):
        """32 bytes entropy produces 24-word mnemonic."""
        entropy = b'\x00' * 32
        mnemonic = bip39_entropy_to_mnemonic(entropy)
        words = mnemonic.split()
        self.assertEqual(len(words), 24)
    
    def test_entropy_to_mnemonic_roundtrip(self):
        """Entropy → mnemonic → entropy roundtrip preserves data."""
        import hashlib
        entropy = hashlib.sha256(b'test').digest()
        mnemonic = bip39_entropy_to_mnemonic(entropy)
        recovered = bip39_mnemonic_to_entropy(mnemonic)
        self.assertEqual(entropy, recovered)
    
    def test_entropy_to_mnemonic_deterministic(self):
        """Same entropy always produces the same mnemonic."""
        entropy = b'\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f\x10'
        m1 = bip39_entropy_to_mnemonic(entropy)
        m2 = bip39_entropy_to_mnemonic(entropy)
        self.assertEqual(m1, m2)
    
    def test_invalid_entropy_length(self):
        """Invalid entropy length raises ValueError."""
        with self.assertRaises(ValueError):
            bip39_entropy_to_mnemonic(b'\x00' * 10)
    
    def test_mnemonic_to_entropy_invalid_word(self):
        """Invalid word in mnemonic raises ValueError."""
        with self.assertRaises(ValueError):
            bip39_mnemonic_to_entropy("abandon ability able about above absent absorb abstract absurd abuse access accident")
    
    def test_mnemonic_to_entropy_wrong_word_count(self):
        """Wrong word count raises ValueError."""
        with self.assertRaises(ValueError):
            bip39_mnemonic_to_entropy("abandon ability able")
    
    def test_validate_bip39_valid(self):
        """Valid mnemonic passes validation."""
        entropy = b'\x00' * 16
        mnemonic = bip39_entropy_to_mnemonic(entropy)
        self.assertTrue(validate_bip39(mnemonic))
    
    def test_validate_bip39_invalid(self):
        """Invalid mnemonic fails validation."""
        # "abandon abandon...about" is actually a valid test vector, so use truly random words
        # that won't pass the checksum
        invalid = "abandon ability able about above absent absorb abstract absurd abuse access accident"
        self.assertFalse(validate_bip39(invalid))
    
    def test_mnemonic_to_seed(self):
        """Seed derivation produces 64 bytes."""
        entropy = b'\x00' * 16
        mnemonic = bip39_entropy_to_mnemonic(entropy)
        seed = bip39_mnemonic_to_seed(mnemonic)
        self.assertEqual(len(seed), 64)
    
    def test_mnemonic_to_seed_deterministic(self):
        """Same mnemonic produces same seed."""
        entropy = b'\x01' * 16
        mnemonic = bip39_entropy_to_mnemonic(entropy)
        s1 = bip39_mnemonic_to_seed(mnemonic)
        s2 = bip39_mnemonic_to_seed(mnemonic)
        self.assertEqual(s1, s2)
    
    def test_mnemonic_to_seed_with_passphrase(self):
        """Different passphrase produces different seed."""
        entropy = b'\x01' * 16
        mnemonic = bip39_entropy_to_mnemonic(entropy)
        s1 = bip39_mnemonic_to_seed(mnemonic, "")
        s2 = bip39_mnemonic_to_seed(mnemonic, "passphrase")
        self.assertNotEqual(s1, s2)


class TestSeedCandidate(unittest.TestCase):
    """Test SeedCandidate dataclass."""
    
    def test_candidate_creation(self):
        """SeedCandidate can be created with required fields."""
        c = SeedCandidate(
            mnemonic="test mnemonic here",
            entropy_hex="00000000000000000000000000000000",
            seed_hex="0" * 128,
            derivation_method="test",
            word_count=12,
        )
        self.assertEqual(c.word_count, 12)
        self.assertEqual(c.derivation_method, "test")
    
    def test_candidate_default_fields(self):
        """Default fields are empty list and empty string."""
        c = SeedCandidate(
            mnemonic="test",
            entropy_hex="00",
            seed_hex="00",
            derivation_method="test",
            word_count=12,
        )
        self.assertEqual(c.pictograph_indices, [])
        self.assertEqual(c.significance, "")


class TestBIP39SeedHunter(unittest.TestCase):
    """Test BIP39SeedHunter class."""
    
    def setUp(self):
        """Create a fresh hunter for each test."""
        self.hunter = BIP39SeedHunter()
    
    def test_initial_state(self):
        """Hunter starts with empty state."""
        self.assertEqual(self.hunter.found, [])
        self.assertEqual(self.hunter.attempts, 0)
        self.assertEqual(self.hunter.methods_tried, set())
    
    def test_hunt_gematria_entropy(self):
        """Gematria entropy method runs without error."""
        self.hunter.hunt_gematria_entropy()
        self.assertIn("gematria_entropy", self.hunter.methods_tried)
        self.assertGreater(self.hunter.attempts, 0)
    
    def test_hunt_letter_entropy(self):
        """Letter entropy method runs without error."""
        self.hunter.hunt_letter_entropy()
        self.assertIn("letter_entropy", self.hunter.methods_tried)
    
    def test_hunt_pictograph_hash(self):
        """Pictograph hash method runs without error."""
        self.hunter.hunt_pictograph_hash()
        self.assertIn("pictograph_hash", self.hunter.methods_tried)
    
    def test_hunt_lambda_transform(self):
        """Lambda transform method runs without error."""
        self.hunter.hunt_lambda_transform()
        self.assertIn("lambda_transform", self.hunter.methods_tried)
    
    def test_hunt_retrocausal_phase(self):
        """Retrocausal phase method runs without error."""
        self.hunter.hunt_retrocausal_phase()
        self.assertIn("retrocausal_phase", self.hunter.methods_tried)
    
    def test_hunt_genesis_data_combinations(self):
        """Genesis data combinations method runs without error."""
        self.hunter.hunt_genesis_data_combinations()
        self.assertIn("genesis_data_combinations", self.hunter.methods_tried)
    
    def test_hunt_tau691_entropy(self):
        """tau(28)/691 entropy method runs without error."""
        self.hunter.hunt_tau691_entropy()
        self.assertIn("tau691_entropy", self.hunter.methods_tried)
    
    def test_hunt_messerene_pattern(self):
        """Messerene pattern method runs without error."""
        self.hunter.hunt_messerene_pattern()
        self.assertIn("messerene_pattern", self.hunter.methods_tried)
    
    def test_hunt_null_space_entropy(self):
        """Null space entropy method runs without error."""
        self.hunter.hunt_null_space_entropy()
        self.assertIn("null_space_entropy", self.hunter.methods_tried)
    
    def test_hunt_checksum_completion(self):
        """Checksum completion method runs without error."""
        self.hunter.hunt_checksum_completion()
        self.assertIn("checksum_completion", self.hunter.methods_tried)
    
    def test_hunt_hmac_derivations(self):
        """HMAC derivations method runs without error."""
        self.hunter.hunt_hmac_derivations()
        self.assertIn("hmac_derivations", self.hunter.methods_tried)
    
    def test_hunt_subset_permutations(self):
        """Subset permutations method runs without error."""
        self.hunter.hunt_subset_permutations()
        self.assertIn("subset_permutations", self.hunter.methods_tried)
    
    def test_hunt_reversed_entropy(self):
        """Reversed entropy method runs without error."""
        self.hunter.hunt_reversed_entropy()
        self.assertIn("reversed_entropy", self.hunter.methods_tried)
    
    def test_hunt_bip39_index_entropy(self):
        """BIP39 index entropy method runs without error."""
        self.hunter.hunt_bip39_index_entropy()
        self.assertIn("bip39_index_entropy", self.hunter.methods_tried)
    
    def test_hunt_all(self):
        """All methods run without error."""
        found = self.hunter.hunt_all()
        self.assertEqual(len(found), len(self.hunter.found))
        self.assertEqual(len(self.hunter.methods_tried), 14)
        self.assertGreater(self.hunter.attempts, 0)
    
    def test_hunt_finds_candidates(self):
        """Hunter finds at least some candidates."""
        found = self.hunter.hunt_all()
        self.assertGreater(len(found), 0)
    
    def test_candidate_mnemonic_valid(self):
        """All found candidates have valid mnemonics."""
        found = self.hunter.hunt_all()
        for c in found:
            self.assertTrue(validate_bip39(c.mnemonic), f"Invalid mnemonic: {c.mnemonic}")
    
    def test_candidate_word_count(self):
        """All candidates have valid word counts."""
        found = self.hunter.hunt_all()
        for c in found:
            self.assertIn(c.word_count, (12, 24))
    
    def test_candidate_seed_length(self):
        """All candidates have 64-byte seeds."""
        found = self.hunter.hunt_all()
        for c in found:
            self.assertEqual(len(c.seed_hex), 128)  # 64 bytes = 128 hex chars
    
    def test_get_summary(self):
        """Summary contains expected fields."""
        self.hunter.hunt_all()
        summary = self.hunter.get_summary()
        self.assertIn('total_attempts', summary)
        self.assertIn('methods_tried', summary)
        self.assertIn('methods_list', summary)
        self.assertIn('seeds_found', summary)
        self.assertIn('found_candidates', summary)
    
    def test_summary_counts_match(self):
        """Summary counts match actual data."""
        self.hunter.hunt_all()
        summary = self.hunter.get_summary()
        self.assertEqual(summary['seeds_found'], len(self.hunter.found))
        self.assertEqual(summary['methods_tried'], 14)


class TestConstants(unittest.TestCase):
    """Test that constants are correct."""
    
    def test_genesis_hash(self):
        """Genesis hash is correct."""
        self.assertEqual(GENESIS_HASH, "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f")
    
    def test_genesis_nonce(self):
        """Genesis nonce is correct."""
        self.assertEqual(GENESIS_NONCE, 2083236893)
    
    def test_genesis_timestamp(self):
        """Genesis timestamp is correct."""
        self.assertEqual(GENESIS_TIMESTAMP, 1231006505)
    
    def test_tau_28_corrected(self):
        """tau(28) is the corrected value."""
        self.assertEqual(TAU_28, 24647168)
    
    def test_tau_28_mod_691(self):
        """tau(28) mod 691 = 580 (Ramanujan congruence)."""
        self.assertEqual(TAU_28 % RAMANUJAN_PRIME, 580)
    
    def test_ramanujan_prime(self):
        """Ramanujan prime is 691."""
        self.assertEqual(RAMANUJAN_PRIME, 691)
    
    def test_lambda_matrix_shape(self):
        """Lambda matrix is 3x3."""
        self.assertEqual(len(LAMBDA_MATRIX), 3)
        for row in LAMBDA_MATRIX:
            self.assertEqual(len(row), 3)
    
    def test_lambda_matrix_values(self):
        """Lambda matrix has correct values."""
        self.assertEqual(LAMBDA_MATRIX, [[1, 1, 1], [1, 0, -1], [-1, -1, -1]])
    
    def test_null_space(self):
        """Null space is [1, -2, 1]."""
        self.assertEqual(NULL_SPACE, [1, -2, 1])
    
    def test_null_space_orthogonal(self):
        """Null space is orthogonal to all lambda rows."""
        for row in LAMBDA_MATRIX:
            dot = sum(n * r for n, r in zip(NULL_SPACE, row))
            self.assertEqual(dot, 0)
    
    def test_genesis_pictographs_count(self):
        """32 pictographs from Genesis block."""
        self.assertEqual(len(GENESIS_PICTOGRAPHS), 32)
    
    def test_genesis_letters_count(self):
        """32 Hebrew letters."""
        self.assertEqual(len(GENESIS_LETTERS), 32)
    
    def test_genesis_gematria_count(self):
        """32 gematria values."""
        self.assertEqual(len(GENESIS_GEMATRIA), 32)
    
    def test_gematria_sum(self):
        """Gematria sum is 1390."""
        self.assertEqual(sum(GENESIS_GEMATRIA), 1390)
    
    def test_gematria_sum_mod_691(self):
        """Gematria sum mod 691 = 8 (octonion dimension)."""
        self.assertEqual(sum(GENESIS_GEMATRIA) % 691, 8)


if __name__ == "__main__":
    unittest.main()
