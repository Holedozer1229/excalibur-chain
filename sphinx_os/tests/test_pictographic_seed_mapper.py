#!/usr/bin/env python3
"""
Unit tests for the Pictographic Seed Mapper.
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sphinx_os.nexus.pictographic_seed_mapper import (
    PictographicSeedMapper,
    SeedCandidate,
    compute_trifold_root,
    CANONICAL_ROOT,
    GENESIS_HASH,
    GENESIS_NONCE,
    GENESIS_TIMESTAMP,
    TAU_28,
    RAMANUJAN_PRIME,
    GENESIS_PICTOGRAPHS,
    GENESIS_LETTERS,
    GENESIS_GEMATRIA,
    LAMBDA_MATRIX,
    NULL_SPACE,
    BIP39_WORDS,
    BIP39_INDEX,
    PICTOGRAPH_TO_BIP39,
    LETTER_POSITION,
    map_pictographic_seed,
    find_canonical_seed,
    get_pictograph_indices,
)


class TestConstants(unittest.TestCase):
    """Test the constants are correct."""

    def test_canonical_root_length(self):
        self.assertEqual(len(CANONICAL_ROOT), 64)

    def test_genesis_hash(self):
        self.assertEqual(GENESIS_HASH, "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f")

    def test_genesis_nonce(self):
        self.assertEqual(GENESIS_NONCE, 2083236893)

    def test_genesis_timestamp(self):
        self.assertEqual(GENESIS_TIMESTAMP, 1231006505)

    def test_tau_28_corrected(self):
        self.assertEqual(TAU_28, 24647168)

    def test_ramanujan_prime(self):
        self.assertEqual(RAMANUJAN_PRIME, 691)

    def test_pictograph_count(self):
        self.assertEqual(len(GENESIS_PICTOGRAPHS), 32)

    def test_letter_count(self):
        self.assertEqual(len(GENESIS_LETTERS), 32)

    def test_gematria_count(self):
        self.assertEqual(len(GENESIS_GEMATRIA), 32)

    def test_lambda_matrix_shape(self):
        self.assertEqual(len(LAMBDA_MATRIX), 3)
        for row in LAMBDA_MATRIX:
            self.assertEqual(len(row), 3)

    def test_null_space(self):
        self.assertEqual(NULL_SPACE, [1, -2, 1])

    def test_bip39_word_count(self):
        self.assertEqual(len(BIP39_WORDS), 2048)

    def test_bip39_index(self):
        self.assertEqual(len(BIP39_INDEX), 2048)
        self.assertEqual(BIP39_INDEX["abandon"], 0)
        self.assertEqual(BIP39_INDEX["zoo"], 2047)

    def test_pictograph_mapping(self):
        self.assertIn("A sword", PICTOGRAPH_TO_BIP39)
        self.assertEqual(PICTOGRAPH_TO_BIP39["A sword"], "sword")

    def test_letter_positions(self):
        self.assertEqual(LETTER_POSITION["Aleph"], 0)
        self.assertEqual(LETTER_POSITION["Tav"], 19)
        # 20 letters defined (Tet and Ayin don't appear in the Genesis block)
        self.assertEqual(len(LETTER_POSITION), 20)


class TestTrifoldRoot(unittest.TestCase):
    """Test the Trifold root computation."""

    def test_root_length(self):
        seed = b'\x00' * 32
        root = compute_trifold_root(seed, height=2)
        self.assertEqual(len(root), 64)

    def test_root_deterministic(self):
        seed = b'\x01' * 32
        root1 = compute_trifold_root(seed, height=2)
        root2 = compute_trifold_root(seed, height=2)
        self.assertEqual(root1, root2)

    def test_root_different_seeds(self):
        seed1 = b'\x00' * 32
        seed2 = b'\x01' * 32
        root1 = compute_trifold_root(seed1, height=2)
        root2 = compute_trifold_root(seed2, height=2)
        self.assertNotEqual(root1, root2)

    def test_root_different_heights(self):
        seed = b'\x01' * 32
        root2 = compute_trifold_root(seed, height=2)
        root3 = compute_trifold_root(seed, height=3)
        self.assertNotEqual(root2, root3)


class TestSeedCandidate(unittest.TestCase):
    """Test the SeedCandidate dataclass."""

    def test_candidate_creation(self):
        candidate = SeedCandidate(
            seed_hex="0" * 64,
            trifold_root="0" * 64,
            derivation_method="test",
            indices=[0] * 32,
            mnemonic_words=["abandon"] * 24,
        )
        self.assertEqual(candidate.derivation_method, "test")
        self.assertFalse(candidate.matches_canonical)

    def test_candidate_match(self):
        candidate = SeedCandidate(
            seed_hex="0" * 64,
            trifold_root=CANONICAL_ROOT,
            derivation_method="test",
            indices=[0] * 32,
            mnemonic_words=["abandon"] * 24,
            matches_canonical=True,
        )
        self.assertTrue(candidate.matches_canonical)


class TestPictographicMapper(unittest.TestCase):
    """Test the PictographicSeedMapper class."""

    def test_mapper_initialization(self):
        mapper = PictographicSeedMapper()
        self.assertEqual(len(mapper.candidates), 0)
        self.assertEqual(mapper.attempts, 0)

    def test_direct_bip39(self):
        mapper = PictographicSeedMapper()
        mapper.map_direct_bip39()
        self.assertEqual(len(mapper.candidates), 1)
        self.assertEqual(mapper.attempts, 1)
        self.assertEqual(len(mapper.candidates[0].indices), 32)

    def test_gematria_mod2048(self):
        mapper = PictographicSeedMapper()
        mapper.map_gematria_mod2048()
        self.assertEqual(len(mapper.candidates), 1)
        # Gematria values mod 2048
        expected = [g % 2048 for g in GENESIS_GEMATRIA]
        self.assertEqual(mapper.candidates[0].indices, expected)

    def test_letter_position_tau(self):
        mapper = PictographicSeedMapper()
        mapper.map_letter_position_tau()
        self.assertEqual(len(mapper.candidates), 1)
        self.assertEqual(len(mapper.candidates[0].indices), 32)

    def test_lambda_transform(self):
        mapper = PictographicSeedMapper()
        mapper.map_lambda_transform()
        self.assertEqual(len(mapper.candidates), 1)
        self.assertEqual(len(mapper.candidates[0].indices), 32)

    def test_retrocausal_phase(self):
        mapper = PictographicSeedMapper()
        mapper.map_retrocausal_phase()
        self.assertEqual(len(mapper.candidates), 1)

    def test_messerene_operator(self):
        mapper = PictographicSeedMapper()
        mapper.map_messerene_operator()
        self.assertEqual(len(mapper.candidates), 1)

    def test_null_space_projection(self):
        mapper = PictographicSeedMapper()
        mapper.map_null_space_projection()
        self.assertEqual(len(mapper.candidates), 1)

    def test_sha256_pictograph(self):
        mapper = PictographicSeedMapper()
        mapper.map_sha256_pictograph()
        self.assertEqual(len(mapper.candidates), 1)

    def test_combined_entropy(self):
        mapper = PictographicSeedMapper()
        mapper.map_combined_entropy()
        self.assertEqual(len(mapper.candidates), 1)

    def test_tau691_hmac(self):
        mapper = PictographicSeedMapper()
        mapper.map_tau691_hmac()
        self.assertEqual(len(mapper.candidates), 1)

    def test_genesis_nonce_entropy(self):
        mapper = PictographicSeedMapper()
        mapper.map_genesis_nonce_entropy()
        self.assertEqual(len(mapper.candidates), 1)

    def test_find_canonical_no_match(self):
        mapper = PictographicSeedMapper()
        mapper.map_direct_bip39()
        result = mapper.find_canonical()
        self.assertIsNone(result)

    def test_candidate_properties(self):
        mapper = PictographicSeedMapper()
        mapper.map_direct_bip39()
        c = mapper.candidates[0]
        self.assertEqual(len(c.seed_hex), 64)
        self.assertEqual(len(c.trifold_root), 64)
        self.assertEqual(len(c.mnemonic_words), 24)


class TestConvenienceFunctions(unittest.TestCase):
    """Test the convenience functions."""

    def test_get_pictograph_indices_direct(self):
        indices = get_pictograph_indices("direct")
        self.assertEqual(len(indices), 32)

    def test_get_pictograph_indices_gematria(self):
        indices = get_pictograph_indices("gematria")
        self.assertEqual(len(indices), 32)

    def test_get_pictograph_indices_invalid(self):
        with self.assertRaises(ValueError):
            get_pictograph_indices("invalid_method")


class TestLambdaMatrix(unittest.TestCase):
    """Test the lambda matrix properties."""

    def test_null_space_orthogonal(self):
        """Verify null space is orthogonal to all rows."""
        for row in LAMBDA_MATRIX:
            dot = sum(n * r for n, r in zip(NULL_SPACE, row))
            self.assertEqual(dot, 0)

    def test_lambda_transform_zero(self):
        """Applying lambda to null space gives zero."""
        result = []
        for row in LAMBDA_MATRIX:
            val = sum(r * n for r, n in zip(row, NULL_SPACE))
            result.append(val)
        self.assertEqual(result, [0, 0, 0])


class TestGematria(unittest.TestCase):
    """Test gematria values."""

    def test_gematria_sum(self):
        self.assertEqual(sum(GENESIS_GEMATRIA), 1390)

    def test_gematria_mod_691(self):
        self.assertEqual(sum(GENESIS_GEMATRIA) % 691, 8)

    def test_gematria_values(self):
        # First few values
        self.assertEqual(GENESIS_GEMATRIA[0], 7)   # Zayin
        self.assertEqual(GENESIS_GEMATRIA[1], 3)   # Gimel
        self.assertEqual(GENESIS_GEMATRIA[2], 8)   # Het


if __name__ == "__main__":
    unittest.main()
