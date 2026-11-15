#!/usr/bin/env python3
"""
Unit tests for the BIP39 Pictographic Mapper.

Tests cover:
- BIP39 word list integrity
- Entropy ↔ mnemonic conversion
- Mnemonic validation and checksum
- PBKDF2 seed derivation
- Pictograph-to-BIP39 mapping
- Multiple mapping strategies
- BIP-32 HD derivation
- Closest word search
- Genesis entropy search
"""

import hashlib
import struct
import unittest

from sphinx_os.nexus.bip39_pictographic import (
    # Constants
    BIP39_WORDS,
    BIP39_INDEX,
    GENESIS_PICTOGRAPHS,
    GENESIS_LETTERS,
    GENESIS_GEMATRIA,
    GENESIS_HASH,
    GENESIS_NONCE,
    GENESIS_TIMESTAMP,
    PICTOGRAPH_TO_BIP39,
    PICTOGRAPH_ALTERNATIVES,
    # Data classes
    PictographMapping,
    PictographicMnemonic,
    # BIP39 core
    validate_bip39_mnemonic,
    bip39_entropy_to_mnemonic,
    bip39_mnemonic_to_entropy,
    bip39_mnemonic_to_seed,
    # Genesis mapper
    map_genesis_pictographs,
    find_closest_bip39_word,
    search_pictographic_entropy,
    # BIP-32
    pictographic_hd_path,
    # Convenience
    get_genesis_mnemonic,
    get_genesis_seed,
    check_pictograph_in_bip39,
    get_pictograph_word,
)


class TestBIP39WordList(unittest.TestCase):
    """Test the BIP39 word list integrity."""

    def test_word_count(self):
        self.assertEqual(len(BIP39_WORDS), 2048)

    def test_unique_words(self):
        self.assertEqual(len(set(BIP39_WORDS)), 2048)

    def test_index_completeness(self):
        self.assertEqual(len(BIP39_INDEX), 2048)

    def test_known_words(self):
        self.assertIn("abandon", BIP39_INDEX)
        self.assertIn("sword", BIP39_INDEX)
        self.assertIn("desert", BIP39_INDEX)
        self.assertIn("fire", BIP39_INDEX)
        self.assertIn("door", BIP39_INDEX)
        self.assertIn("satoshi", BIP39_INDEX)

    def test_word_indices(self):
        self.assertEqual(BIP39_INDEX["abandon"], 0)
        self.assertEqual(BIP39_INDEX["zoo"], 2047)

    def test_first_word(self):
        self.assertEqual(BIP39_WORDS[0], "abandon")

    def test_last_word(self):
        self.assertEqual(BIP39_WORDS[2047], "zoo")


class TestBIP39EntropyConversion(unittest.TestCase):
    """Test entropy ↔ mnemonic conversion."""

    def test_128_bit_entropy(self):
        """128-bit entropy → 12 words."""
        entropy = b'\x00' * 16
        mnemonic = bip39_entropy_to_mnemonic(entropy)
        words = mnemonic.split()
        self.assertEqual(len(words), 12)

    def test_256_bit_entropy(self):
        """256-bit entropy → 24 words."""
        entropy = b'\x00' * 32
        mnemonic = bip39_entropy_to_mnemonic(entropy)
        words = mnemonic.split()
        self.assertEqual(len(words), 24)

    def test_bip39_test_vector_128(self):
        """BIP39 published test vector: all-zero 128-bit entropy."""
        entropy = b'\x00' * 16
        mnemonic = bip39_entropy_to_mnemonic(entropy)
        # First word should be "abandon" (index 0)
        self.assertTrue(mnemonic.startswith("abandon"))

    def test_roundtrip_128(self):
        """Entropy → mnemonic → entropy roundtrip."""
        entropy = b'\x01' * 16
        mnemonic = bip39_entropy_to_mnemonic(entropy)
        recovered = bip39_mnemonic_to_entropy(mnemonic)
        self.assertEqual(recovered, entropy)

    def test_roundtrip_256(self):
        """Entropy → mnemonic → entropy roundtrip (256-bit)."""
        entropy = b'\xff' * 32
        mnemonic = bip39_entropy_to_mnemonic(entropy)
        recovered = bip39_mnemonic_to_entropy(mnemonic)
        self.assertEqual(recovered, entropy)

    def test_invalid_entropy_length(self):
        """Invalid entropy length should raise."""
        with self.assertRaises(ValueError):
            bip39_entropy_to_mnemonic(b'\x00' * 10)

    def test_invalid_mnemonic_word_count(self):
        """Invalid word count should raise."""
        with self.assertRaises(ValueError):
            bip39_mnemonic_to_entropy("abandon ability able about above")

    def test_invalid_word(self):
        """Non-BIP39 word should raise."""
        with self.assertRaises(ValueError):
            bip39_mnemonic_to_entropy("abandon ability able about above absent absorb abstract absurd abuse access accident notaword")

    def test_checksum_mismatch(self):
        """Wrong checksum should raise."""
        # Take a valid mnemonic and change the last word
        entropy = b'\x01' * 16
        mnemonic = bip39_entropy_to_mnemonic(entropy)
        words = mnemonic.split()
        words[-1] = "zoo"  # change last word
        bad_mnemonic = " ".join(words)
        with self.assertRaises(ValueError):
            bip39_mnemonic_to_entropy(bad_mnemonic)


class TestBIP39Validation(unittest.TestCase):
    """Test mnemonic validation."""

    def test_valid_mnemonic(self):
        """Valid mnemonic should pass."""
        entropy = b'\x01' * 16
        mnemonic = bip39_entropy_to_mnemonic(entropy)
        self.assertTrue(validate_bip39_mnemonic(mnemonic))

    def test_invalid_mnemonic(self):
        """Invalid mnemonic should fail."""
        self.assertFalse(validate_bip39_mnemonic("not a valid mnemonic phrase at all"))

    def test_wrong_checksum(self):
        """Wrong checksum should fail validation."""
        # "about" is the wrong last word for this entropy
        self.assertFalse(validate_bip39_mnemonic("abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon wrong"))


class TestBIP39SeedDerivation(unittest.TestCase):
    """Test PBKDF2 seed derivation."""

    def test_seed_length(self):
        """Seed should be 64 bytes."""
        entropy = b'\x01' * 16
        mnemonic = bip39_entropy_to_mnemonic(entropy)
        seed = bip39_mnemonic_to_seed(mnemonic)
        self.assertEqual(len(seed), 64)

    def test_deterministic(self):
        """Same mnemonic → same seed."""
        entropy = b'\x01' * 16
        mnemonic = bip39_entropy_to_mnemonic(entropy)
        seed1 = bip39_mnemonic_to_seed(mnemonic)
        seed2 = bip39_mnemonic_to_seed(mnemonic)
        self.assertEqual(seed1, seed2)

    def test_passphrase_changes_seed(self):
        """Different passphrase → different seed."""
        entropy = b'\x01' * 16
        mnemonic = bip39_entropy_to_mnemonic(entropy)
        seed1 = bip39_mnemonic_to_seed(mnemonic, "")
        seed2 = bip39_mnemonic_to_seed(mnemonic, "passphrase")
        self.assertNotEqual(seed1, seed2)

    def test_seed_always_produces_64_bytes(self):
        """PBKDF2 produces 64 bytes for any input string."""
        # bip39_mnemonic_to_seed runs PBKDF2 on any string
        seed = bip39_mnemonic_to_seed("any string at all")
        self.assertEqual(len(seed), 64)


class TestPictographMapping(unittest.TestCase):
    """Test pictograph-to-BIP39 mapping."""

    def test_genesis_pictograph_count(self):
        self.assertEqual(len(GENESIS_PICTOGRAPHS), 32)

    def test_genesis_letter_count(self):
        self.assertEqual(len(GENESIS_LETTERS), 32)

    def test_genesis_gematria_count(self):
        self.assertEqual(len(GENESIS_GEMATRIA), 32)

    def test_direct_mapping_sword(self):
        self.assertEqual(get_pictograph_word("A sword"), "sword")

    def test_direct_mapping_fire(self):
        self.assertEqual(get_pictograph_word("Fire"), "fire")

    def test_direct_mapping_door(self):
        self.assertEqual(get_pictograph_word("A door"), "door")

    def test_direct_mapping_hand(self):
        self.assertEqual(get_pictograph_word("A hand"), "hand")

    def test_direct_mapping_head(self):
        self.assertEqual(get_pictograph_word("A head"), "head")

    def test_direct_mapping_fish(self):
        self.assertEqual(get_pictograph_word("A fish"), "fish")

    def test_direct_mapping_water(self):
        self.assertEqual(get_pictograph_word("Water"), "water")

    def test_direct_mapping_house(self):
        self.assertEqual(get_pictograph_word("A house"), "home")

    def test_direct_mapping_window(self):
        self.assertEqual(get_pictograph_word("A window"), "window")

    def test_direct_mapping_palm(self):
        self.assertEqual(get_pictograph_word("A palm"), "palm")

    def test_check_pictograph_in_bip39(self):
        self.assertTrue(check_pictograph_in_bip39("A sword"))
        self.assertTrue(check_pictograph_in_bip39("Fire"))
        self.assertTrue(check_pictograph_in_bip39("A door"))

    def test_pictograph_mapping_class(self):
        mapping = PictographMapping(
            pictograph="A sword",
            hebrew_letter="Zayin",
            gematria=7,
            direct_match="sword",
            direct_index=BIP39_INDEX["sword"],
        )
        best = mapping.best_match()
        self.assertEqual(best[0], "sword")
        self.assertEqual(best[1], BIP39_INDEX["sword"])

    def test_pictograph_mapping_fallback(self):
        """Test fallback to alternatives then hash."""
        mapping = PictographMapping(
            pictograph="Unknown",
            hebrew_letter="",
            gematria=0,
        )
        # No direct match, no alternatives — should return hash
        pict_hash = hashlib.sha256("Unknown".encode()).digest()
        hash_index = int.from_bytes(pict_hash[:4], 'big') % 2048
        mapping.hash_match = BIP39_WORDS[hash_index]
        mapping.hash_index = hash_index
        best = mapping.best_match()
        self.assertEqual(best[0], BIP39_WORDS[hash_index])


class TestPictographicMnemonic(unittest.TestCase):
    """Test the full pictographic mnemonic builder."""

    def test_direct_strategy(self):
        pm = map_genesis_pictographs("direct")
        self.assertEqual(len(pm.mnemonic_words), 32)
        self.assertTrue(pm.mnemonic_string)
        self.assertEqual(len(pm.mappings), 32)

    def test_hash_strategy(self):
        pm = map_genesis_pictographs("hash")
        self.assertEqual(len(pm.mnemonic_words), 32)

    def test_gematria_strategy(self):
        pm = map_genesis_pictographs("gematria")
        self.assertEqual(len(pm.mnemonic_words), 32)

    def test_byte_strategy(self):
        pm = map_genesis_pictographs("byte")
        self.assertEqual(len(pm.mnemonic_words), 32)

    def test_direct_first_word(self):
        """First pictograph 'A sword' should map to 'sword'."""
        pm = map_genesis_pictographs("direct")
        self.assertEqual(pm.mnemonic_words[0], "sword")

    def test_direct_fire_word(self):
        """Fourth pictograph 'Fire' should map to 'fire'."""
        pm = map_genesis_pictographs("direct")
        self.assertEqual(pm.mnemonic_words[3], "fire")

    def test_12_word_subset(self):
        pm = map_genesis_pictographs("direct")
        mnemonic_12 = pm.get_12_word_mnemonic()
        self.assertEqual(len(mnemonic_12.split()), 12)

    def test_24_word_subset(self):
        pm = map_genesis_pictographs("direct")
        mnemonic_24 = pm.get_24_word_mnemonic()
        self.assertEqual(len(mnemonic_24.split()), 24)

    def test_analysis(self):
        pm = map_genesis_pictographs("direct")
        analysis = pm.analyze()
        self.assertEqual(analysis["total_pictographs"], 32)
        self.assertIn("direct_bip39_matches", analysis)
        self.assertIn("mnemonic_string", analysis)
        self.assertIn("is_valid_bip39", analysis)

    def test_direct_has_matches(self):
        """Direct strategy should have some BIP39 matches."""
        pm = map_genesis_pictographs("direct")
        analysis = pm.analyze()
        self.assertGreater(analysis["direct_bip39_matches"], 0)

    def test_derive_seed(self):
        """Seed derivation should produce 64 bytes."""
        pm = map_genesis_pictographs("direct")
        # Use a valid 12-word subset for seed derivation
        mnemonic_12 = pm.get_12_word_mnemonic()
        # This may fail checksum, but derive_seed should still work
        # for any string (PBKDF2 doesn't care about checksum)
        seed = bip39_mnemonic_to_seed(mnemonic_12)
        self.assertEqual(len(seed), 64)


class TestClosestWordSearch(unittest.TestCase):
    """Test the closest BIP39 word finder."""

    def test_exact_match_sword(self):
        word, idx, score = find_closest_bip39_word("A sword")
        self.assertEqual(word, "sword")
        self.assertEqual(score, 1.0)

    def test_exact_match_fire(self):
        word, idx, score = find_closest_bip39_word("Fire")
        self.assertEqual(word, "fire")
        self.assertEqual(score, 1.0)

    def test_exact_match_door(self):
        word, idx, score = find_closest_bip39_word("A door")
        self.assertEqual(word, "door")
        self.assertEqual(score, 1.0)

    def test_returns_valid_word(self):
        word, idx, score = find_closest_bip39_word("A coiled body")
        self.assertIn(word, BIP39_INDEX)
        self.assertEqual(idx, BIP39_INDEX[word])

    def test_score_range(self):
        word, idx, score = find_closest_bip39_word("A courtyard")
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)


class TestGenesisEntropySearch(unittest.TestCase):
    """Test the Genesis entropy search."""

    def test_search_returns_dict(self):
        result = search_pictographic_entropy()
        self.assertIsInstance(result, dict)

    def test_search_has_mnemonic_12(self):
        result = search_pictographic_entropy()
        self.assertIn("mnemonic_12_words", result)
        self.assertEqual(len(result["mnemonic_12_words"].split()), 12)

    def test_search_has_mnemonic_24(self):
        result = search_pictographic_entropy()
        self.assertIn("mnemonic_24_words", result)
        self.assertEqual(len(result["mnemonic_24_words"].split()), 24)

    def test_search_has_entropy(self):
        result = search_pictographic_entropy()
        self.assertIn("genesis_entropy_hex", result)
        self.assertEqual(len(result["genesis_entropy_hex"]), 64)  # 32 bytes hex

    def test_mnemonic_is_valid(self):
        """The entropy-derived mnemonics should be valid BIP39."""
        result = search_pictographic_entropy()
        self.assertTrue(validate_bip39_mnemonic(result["mnemonic_12_words"]))
        self.assertTrue(validate_bip39_mnemonic(result["mnemonic_24_words"]))


class TestBIP32Derivation(unittest.TestCase):
    """Test BIP-32 HD derivation from pictographic seed."""

    def test_hd_path_returns_dict(self):
        seed = b'\x01' * 64
        result = pictographic_hd_path(seed)
        self.assertIsInstance(result, dict)

    def test_hd_path_has_fields(self):
        seed = b'\x01' * 64
        result = pictographic_hd_path(seed)
        self.assertIn("path", result)
        self.assertIn("private_key_hex", result)
        self.assertIn("chain_code_hex", result)

    def test_hd_path_default(self):
        seed = b'\x01' * 64
        result = pictographic_hd_path(seed)
        self.assertEqual(result["path"], "m/44'/0'/0'/0/0")

    def test_hd_path_custom(self):
        seed = b'\x01' * 64
        result = pictographic_hd_path(seed, "m/49'/0'/0'/0/0")
        self.assertEqual(result["path"], "m/49'/0'/0'/0/0")

    def test_hd_private_key_length(self):
        seed = b'\x01' * 64
        result = pictographic_hd_path(seed)
        self.assertEqual(len(result["private_key_hex"]), 64)  # 32 bytes hex

    def test_hd_deterministic(self):
        seed = b'\x01' * 64
        result1 = pictographic_hd_path(seed)
        result2 = pictographic_hd_path(seed)
        self.assertEqual(result1["private_key_hex"], result2["private_key_hex"])


class TestConvenienceFunctions(unittest.TestCase):
    """Test the convenience wrapper functions."""

    def test_get_genesis_mnemonic(self):
        mnemonic = get_genesis_mnemonic("direct")
        self.assertIsInstance(mnemonic, str)
        self.assertEqual(len(mnemonic.split()), 32)

    def test_get_genesis_seed(self):
        seed = get_genesis_seed("direct")
        self.assertIsInstance(seed, bytes)
        self.assertEqual(len(seed), 64)

    def test_check_pictograph_in_bip39_true(self):
        self.assertTrue(check_pictograph_in_bip39("A sword"))

    def test_check_pictograph_in_bip39_false(self):
        self.assertFalse(check_pictograph_in_bip39("Nonexistent pictograph"))

    def test_get_pictograph_word_found(self):
        self.assertEqual(get_pictograph_word("A sword"), "sword")

    def test_get_pictograph_word_none(self):
        self.assertIsNone(get_pictograph_word("Nonexistent"))


class TestConstants(unittest.TestCase):
    """Test the constant data."""

    def test_genesis_hash(self):
        self.assertEqual(GENESIS_HASH, "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f")

    def test_genesis_nonce(self):
        self.assertEqual(GENESIS_NONCE, 2083236893)

    def test_genesis_timestamp(self):
        self.assertEqual(GENESIS_TIMESTAMP, 1231006505)

    def test_pictograph_to_bip39_mapping(self):
        self.assertIn("A sword", PICTOGRAPH_TO_BIP39)
        self.assertIn("Fire", PICTOGRAPH_TO_BIP39)
        self.assertIn("A door", PICTOGRAPH_TO_BIP39)

    def test_pictograph_alternatives(self):
        self.assertIn("A courtyard", PICTOGRAPH_ALTERNATIVES)
        self.assertIn("A shepherd's crook", PICTOGRAPH_ALTERNATIVES)

    def test_gematria_sum(self):
        """The gematria sum should be 1390."""
        self.assertEqual(sum(GENESIS_GEMATRIA), 1390)

    def test_gematria_mod_691(self):
        """1390 mod 691 = 8 (octonion dimension)."""
        self.assertEqual(sum(GENESIS_GEMATRIA) % 691, 8)


if __name__ == "__main__":
    unittest.main()
