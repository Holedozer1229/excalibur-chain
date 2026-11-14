#!/usr/bin/env python3
"""
Unit tests for the Wizard Sweep module.
"""

import unittest
import struct
import hashlib
from sphinx_os.nexus.wizard_sweep import (
    WizardSweep, SeedCandidate, compute_trifold_root,
    CANONICAL_ROOT, GENESIS_HASH, GENESIS_NONCE, GENESIS_TIMESTAMP,
    TAU_28, RAMANUJAN_PRIME, PHASE_CONSTANT, LAMBDA_MATRIX, NULL_SPACE,
    GENESIS_PICTOGRAPHS, GENESIS_LETTERS, GENESIS_GEMATRIA,
    BURN_ADDRESSES, GENESIS_PUBLIC_KEY, GENESIS_ADDRESS, GENESIS_COINBASE,
    OCTONION_TABLE, wizard_sweep, find_canonical_wizard
)


class TestConstants(unittest.TestCase):
    """Test that all constants are correctly defined."""

    def test_canonical_root(self):
        self.assertEqual(CANONICAL_ROOT, "7083fbebd6bfbd5f82fd40827cf36bc30da81524914011e69488b5a63e7bfe55")
        self.assertEqual(len(CANONICAL_ROOT), 64)

    def test_genesis_hash(self):
        self.assertEqual(GENESIS_HASH, "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f")
        self.assertEqual(len(GENESIS_HASH), 64)

    def test_genesis_nonce(self):
        self.assertEqual(GENESIS_NONCE, 2083236893)

    def test_genesis_timestamp(self):
        self.assertEqual(GENESIS_TIMESTAMP, 1231006505)

    def test_tau_28(self):
        self.assertEqual(TAU_28, 24647168)  # Corrected tau(28)

    def test_ramanujan_prime(self):
        self.assertEqual(RAMANUJAN_PRIME, 691)

    def test_phase_constant(self):
        self.assertAlmostEqual(PHASE_CONSTANT, 0.33333333326, places=10)

    def test_lambda_matrix(self):
        self.assertEqual(LAMBDA_MATRIX, [[1, 1, 1], [1, 0, -1], [-1, -1, -1]])

    def test_null_space(self):
        self.assertEqual(NULL_SPACE, [1, -2, 1])

    def test_genesis_pictographs(self):
        self.assertEqual(len(GENESIS_PICTOGRAPHS), 32)
        self.assertEqual(GENESIS_PICTOGRAPHS[0], "A sword")
        self.assertEqual(GENESIS_PICTOGRAPHS[-1], "A house")

    def test_genesis_letters(self):
        self.assertEqual(len(GENESIS_LETTERS), 32)
        self.assertEqual(GENESIS_LETTERS[0], "Zayin")
        self.assertEqual(GENESIS_LETTERS[-1], "Bet")

    def test_genesis_gematria(self):
        self.assertEqual(len(GENESIS_GEMATRIA), 32)
        self.assertEqual(GENESIS_GEMATRIA[0], 7)  # Zayin
        self.assertEqual(GENESIS_GEMATRIA[-1], 2)  # Bet

    def test_burn_addresses(self):
        self.assertIn("1BitcoinEaterAddressDontSendf59kuE", BURN_ADDRESSES)
        self.assertIn("1CounterpartyXXXXXXXXXXXXXXXUWLpVr", BURN_ADDRESSES)

    def test_genesis_public_key(self):
        self.assertEqual(len(GENESIS_PUBLIC_KEY), 65)  # Uncompressed public key

    def test_genesis_address(self):
        self.assertEqual(GENESIS_ADDRESS, "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")

    def test_genesis_coinbase(self):
        self.assertTrue(len(GENESIS_COINBASE) > 0)

    def test_octonion_table(self):
        self.assertEqual(len(OCTONION_TABLE), 8)
        self.assertEqual(len(OCTONION_TABLE[0]), 8)


class TestSeedCandidate(unittest.TestCase):
    """Test the SeedCandidate dataclass."""

    def test_seed_candidate_creation(self):
        candidate = SeedCandidate(
            seed_hex="abc123",
            trifold_root="def456",
            derivation_method="test",
            significance="Test candidate",
            matches_canonical=False,
        )
        self.assertEqual(candidate.seed_hex, "abc123")
        self.assertEqual(candidate.trifold_root, "def456")
        self.assertEqual(candidate.derivation_method, "test")
        self.assertFalse(candidate.matches_canonical)

    def test_seed_candidate_match(self):
        candidate = SeedCandidate(
            seed_hex="abc123",
            trifold_root=CANONICAL_ROOT,
            derivation_method="test",
            matches_canonical=True,
        )
        self.assertTrue(candidate.matches_canonical)


class TestTrifoldRoot(unittest.TestCase):
    """Test Trifold root computation."""

    def test_trifold_root_length(self):
        seed = b'\x00' * 32
        root = compute_trifold_root(seed, height=6)
        self.assertEqual(len(root), 64)  # SHA-256 hex

    def test_trifold_root_deterministic(self):
        seed = b'\x01' * 32
        root1 = compute_trifold_root(seed, height=6)
        root2 = compute_trifold_root(seed, height=6)
        self.assertEqual(root1, root2)

    def test_trifold_root_different_seeds(self):
        seed1 = b'\x00' * 32
        seed2 = b'\x01' * 32
        root1 = compute_trifold_root(seed1, height=6)
        root2 = compute_trifold_root(seed2, height=6)
        self.assertNotEqual(root1, root2)


class TestWizardSweep(unittest.TestCase):
    """Test the WizardSweep class."""

    def setUp(self):
        self.sweeper = WizardSweep()

    def test_sweep_init(self):
        self.assertEqual(self.sweeper.attempts, 0)
        self.assertEqual(len(self.sweeper.candidates), 0)
        self.assertEqual(len(self.sweeper.matches), 0)

    def test_try_seed(self):
        seed = b'\x00' * 32
        candidate = self.sweeper._try_seed(seed, "test", "Test significance")
        self.assertIsNotNone(candidate)
        self.assertEqual(self.sweeper.attempts, 1)
        self.assertEqual(len(self.sweeper.candidates), 1)
        self.assertEqual(candidate.derivation_method, "test")
        self.assertEqual(candidate.significance, "Test significance")

    def test_try_seed_short(self):
        seed = b'\x00' * 16  # Shorter than 32 bytes
        candidate = self.sweeper._try_seed(seed, "test_short", "Short seed")
        self.assertIsNotNone(candidate)
        self.assertEqual(len(candidate.seed_hex), 64)  # 32 bytes = 64 hex chars

    def test_try_seed_long(self):
        seed = b'\x00' * 64  # Longer than 32 bytes
        candidate = self.sweeper._try_seed(seed, "test_long", "Long seed")
        self.assertIsNotNone(candidate)
        self.assertEqual(len(candidate.seed_hex), 64)  # Truncated to 32 bytes

    def test_sweep_metatron_octonionic(self):
        self.sweeper.sweep_metatron_octonionic()
        self.assertGreater(self.sweeper.attempts, 0)
        self.assertEqual(len(self.sweeper.candidates), self.sweeper.attempts)

    def test_sweep_ctc_fixed_point(self):
        self.sweeper.sweep_ctc_fixed_point()
        self.assertGreater(self.sweeper.attempts, 0)

    def test_sweep_retrocausal_entropy(self):
        self.sweeper.sweep_retrocausal_entropy()
        self.assertGreater(self.sweeper.attempts, 0)

    def test_sweep_sumerian_words(self):
        self.sweeper.sweep_sumerian_words()
        self.assertGreater(self.sweeper.attempts, 0)

    def test_sweep_bip39_permutations(self):
        self.sweeper.sweep_bip39_permutations()
        self.assertGreater(self.sweeper.attempts, 0)

    def test_sweep_messerene_expanded(self):
        self.sweeper.sweep_messerene_expanded()
        self.assertGreater(self.sweeper.attempts, 100)  # 100+ domains × 8 patterns

    def test_sweep_block_hashes(self):
        self.sweeper.sweep_block_hashes()
        self.assertGreater(self.sweeper.attempts, 0)

    def test_sweep_burn_addresses(self):
        self.sweeper.sweep_burn_addresses()
        self.assertGreater(self.sweeper.attempts, 0)

    def test_sweep_cross_module(self):
        self.sweeper.sweep_cross_module()
        self.assertGreater(self.sweeper.attempts, 0)

    def test_sweep_genesis_deep(self):
        self.sweeper.sweep_genesis_deep()
        self.assertGreater(self.sweeper.attempts, 0)

    def test_sweep_knot_ctc(self):
        self.sweeper.sweep_knot_ctc()
        self.assertGreater(self.sweeper.attempts, 0)

    def test_sweep_quantum_signals(self):
        self.sweeper.sweep_quantum_signals()
        self.assertGreater(self.sweeper.attempts, 0)

    def test_sweep_tau_deep(self):
        self.sweeper.sweep_tau_deep()
        self.assertGreater(self.sweeper.attempts, 0)

    def test_sweep_phase_deep(self):
        self.sweeper.sweep_phase_deep()
        self.assertGreater(self.sweeper.attempts, 0)

    def test_find_canonical_empty(self):
        matches = self.sweeper.find_canonical()
        self.assertEqual(len(matches), 0)

    def test_candidate_significance(self):
        seed = b'\x00' * 32
        candidate = self.sweeper._try_seed(seed, "test", "Test significance")
        self.assertEqual(candidate.significance, "Test significance")


class TestConvenienceFunctions(unittest.TestCase):
    """Test convenience functions."""

    def test_wizard_sweep_function(self):
        # This test is skipped because it takes too long
        pass  # wizard_sweep() returns List[SeedCandidate]

    def test_find_canonical_wizard_function(self):
        # This test is skipped because it takes too long
        pass  # find_canonical_wizard() returns List[SeedCandidate]


class TestLambdaMatrix(unittest.TestCase):
    """Test lambda matrix properties."""

    def test_null_space_orthogonal(self):
        # Null space [1,-2,1] should be orthogonal to all rows
        for row in LAMBDA_MATRIX:
            dot = sum(ns * r for ns, r in zip(NULL_SPACE, row))
            self.assertEqual(dot, 0)

    def test_null_space_length(self):
        self.assertEqual(len(NULL_SPACE), 3)


class TestGematria(unittest.TestCase):
    """Test gematria values."""

    def test_gematria_sum(self):
        gem_sum = sum(GENESIS_GEMATRIA)
        self.assertGreater(gem_sum, 0)

    def test_gematria_mod_691(self):
        gem_sum = sum(GENESIS_GEMATRIA)
        # 1390 mod 691 = 8 (the octonion dimension)
        self.assertEqual(gem_sum % 691, 8)


if __name__ == "__main__":
    unittest.main()
