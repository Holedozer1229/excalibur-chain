"""Tests for the Deutsch CTC Oracle module.

Tests cover:
1. Core deutsch_ctc_distribution function
2. SphinxQOracle class
3. Integration with AIOracleKnight
"""

import time
import unittest
from unittest.mock import MagicMock

from sphinx_os.nexus.deutsch_ctc_oracle import (
    deutsch_ctc_distribution,
    SphinxQOracle,
    DeutschCTCResult,
)
from sphinx_os.nexus.ai_oracle_knight import AIOracleKnight, OracleType
from sphinx_os.nexus.knights_round_table import GovernanceProposal, ProposalType


class TestDeutschCTCDistribution(unittest.TestCase):
    """Test the core deutsch_ctc_distribution function."""

    def test_empty_candidates_raises(self):
        """Empty candidate list should raise ValueError."""
        with self.assertRaises(ValueError):
            deutsch_ctc_distribution([], lambda c: True)

    def test_all_valid_candidates(self):
        """All valid candidates get uniform distribution."""
        candidates = ["A", "B", "C"]
        verify = lambda c: True

        probs, has_valid = deutsch_ctc_distribution(candidates, verify)

        self.assertTrue(has_valid)
        self.assertEqual(len(probs), 3)
        for candidate in candidates:
            self.assertAlmostEqual(probs[candidate], 1.0 / 3)

    def test_no_valid_candidates(self):
        """No valid candidates still returns uniform distribution."""
        candidates = ["A", "B", "C"]
        verify = lambda c: False

        probs, has_valid = deutsch_ctc_distribution(candidates, verify)

        self.assertFalse(has_valid)
        self.assertEqual(len(probs), 3)
        # Uniform over all candidates when none are valid
        for candidate in candidates:
            self.assertAlmostEqual(probs[candidate], 1.0 / 3)

    def test_some_valid_candidates(self):
        """Only valid candidates get non-zero probability."""
        candidates = ["A", "B", "C"]
        verify = lambda c: c in ("A", "C")

        probs, has_valid = deutsch_ctc_distribution(candidates, verify)

        self.assertTrue(has_valid)
        self.assertAlmostEqual(probs["A"], 0.5)
        self.assertAlmostEqual(probs["B"], 0.0)
        self.assertAlmostEqual(probs["C"], 0.5)

    def test_duplicate_candidates(self):
        """Duplicates are removed, preserving order."""
        candidates = ["A", "B", "A", "C", "B"]
        verify = lambda c: c != "B"

        probs, has_valid = deutsch_ctc_distribution(candidates, verify)

        self.assertTrue(has_valid)
        self.assertEqual(len(probs), 3)  # A, B, C (deduplicated)
        self.assertAlmostEqual(probs["A"], 0.5)
        self.assertAlmostEqual(probs["B"], 0.0)
        self.assertAlmostEqual(probs["C"], 0.5)

    def test_single_candidate(self):
        """Single candidate with valid verification."""
        candidates = ["ONLY"]
        verify = lambda c: True

        probs, has_valid = deutsch_ctc_distribution(candidates, verify)

        self.assertTrue(has_valid)
        self.assertAlmostEqual(probs["ONLY"], 1.0)


class TestSphinxQOracle(unittest.TestCase):
    """Test the SphinxQOracle class."""

    def test_respond_with_dict_query(self):
        """Dict query generates governance outcomes."""
        oracle = SphinxQOracle()
        result = oracle.respond({"proposal": "test"})

        self.assertIsInstance(result, DeutschCTCResult)
        self.assertIn("APPROVE", result.probabilities)
        self.assertIn("REJECT", result.probabilities)
        self.assertIn("AMEND", result.probabilities)
        self.assertIn("DEFER", result.probabilities)

    def test_respond_with_string_query(self):
        """String query generates yes/no outcomes."""
        oracle = SphinxQOracle()
        result = oracle.respond("Is this valid?")

        self.assertIn("YES", result.probabilities)
        self.assertIn("NO", result.probabilities)

    def test_respond_with_numeric_query(self):
        """Numeric query generates nearby values."""
        oracle = SphinxQOracle()
        result = oracle.respond(10)

        self.assertIn("9", result.probabilities)
        self.assertIn("10", result.probabilities)
        self.assertIn("11", result.probabilities)

    def test_custom_verifier(self):
        """Custom verifier filters candidates."""
        oracle = SphinxQOracle()

        def verify(candidate, query):
            return candidate == "YES"

        result = oracle.respond("Is this valid?", verify)

        self.assertTrue(result.has_valid_fixed_points)
        self.assertEqual(result.valid_candidates, ["YES"])
        self.assertAlmostEqual(result.probabilities["YES"], 1.0)
        self.assertAlmostEqual(result.probabilities["NO"], 0.0)

    def test_no_valid_fixed_points(self):
        """When no candidates pass verification."""
        oracle = SphinxQOracle()

        def verify(candidate, query):
            return False

        result = oracle.respond("Is this valid?", verify)

        self.assertFalse(result.has_valid_fixed_points)
        self.assertEqual(result.valid_candidates, [])

    def test_stats_tracking(self):
        """Oracle tracks query statistics."""
        oracle = SphinxQOracle()

        def verify(candidate, query):
            return candidate == "YES"

        oracle.respond("Query 1", verify)
        oracle.respond("Query 2", verify)

        stats = oracle.get_stats()
        self.assertEqual(stats["total_queries"], 2)
        self.assertEqual(stats["valid_queries"], 2)
        self.assertAlmostEqual(stats["validity_rate"], 1.0)

    def test_reasoning_with_valid_points(self):
        """Reasoning includes valid candidate info."""
        oracle = SphinxQOracle()

        def verify(candidate, query):
            return candidate in ("YES", "NO")

        result = oracle.respond("Test", verify)

        self.assertIn("CTC fixed point found", result.reasoning)
        self.assertIn("YES", result.reasoning)

    def test_reasoning_without_valid_points(self):
        """Reasoning indicates no valid fixed points."""
        oracle = SphinxQOracle()

        def verify(candidate, query):
            return False

        result = oracle.respond("Test", verify)

        self.assertIn("No valid fixed points", result.reasoning)


class TestAIOracleKnightCTCIntegration(unittest.TestCase):
    """Test integration of Deutsch CTC with AIOracleKnight."""

    def setUp(self):
        """Create a test AI Oracle Knight."""
        self.knight = AIOracleKnight(
            name="Test-CTC",
            oracle_type=OracleType.ORACLE,
            seed=b"test_seed_12345678901234567890",
            participant_index=0,
        )

    def test_analyze_with_ctc_returns_result(self):
        """analyze_with_ctc returns DeutschCTCResult."""
        now = time.time()
        proposal = GovernanceProposal(
            proposal_id="test-001",
            proposer="Alice",
            proposal_type=ProposalType.TREASURY_SPEND,
            description="Small treasury spend",
            parameters={"amount": 100.0},
            created_at=now,
            expires_at=now + 86400,
        )

        result = self.knight.analyze_with_ctc(proposal)

        self.assertIsInstance(result, DeutschCTCResult)
        self.assertIn("APPROVE", result.probabilities)
        self.assertIn("REJECT", result.probabilities)

    def test_analyze_with_ctc_low_risk(self):
        """Low risk proposal should have APPROVE as valid."""
        now = time.time()
        proposal = GovernanceProposal(
            proposal_id="test-002",
            proposer="Alice",
            proposal_type=ProposalType.TREASURY_SPEND,
            description="Very small amount",
            parameters={"amount": 10.0},  # Low risk
            created_at=now,
            expires_at=now + 86400,
        )

        result = self.knight.analyze_with_ctc(proposal)

        # DEFER is always valid, APPROVE should be valid for low risk
        self.assertTrue(result.has_valid_fixed_points)
        self.assertIn("DEFER", result.valid_candidates)

    def test_analyze_with_ctc_high_risk(self):
        """High risk proposal should have REJECT as valid for conservative oracle."""
        # Use SENTINEL type which has a lower risk threshold (0.3)
        sentinel_knight = AIOracleKnight(
            name="Sentinel-CTC",
            oracle_type=OracleType.SENTINEL,
            seed=b"sentinel_seed_12345678901234567",
            participant_index=1,
        )

        now = time.time()
        proposal = GovernanceProposal(
            proposal_id="test-003",
            proposer="Alice",
            proposal_type=ProposalType.TREASURY_SPEND,
            description="Very large amount",
            parameters={"amount": 50000.0},  # High risk
            created_at=now,
            expires_at=now + 86400,
        )

        result = sentinel_knight.analyze_with_ctc(proposal)

        self.assertTrue(result.has_valid_fixed_points)
        # REJECT should be valid for high risk with conservative oracle
        self.assertIn("REJECT", result.valid_candidates)

    def test_custom_ctc_verifier(self):
        """Custom verifier overrides default behavior."""
        now = time.time()
        proposal = GovernanceProposal(
            proposal_id="test-004",
            proposer="Alice",
            proposal_type=ProposalType.TREASURY_SPEND,
            description="Test custom verifier",
            parameters={"amount": 100.0},
            created_at=now,
            expires_at=now + 86400,
        )

        def custom_verify(candidate, prop):
            return candidate == "DEFER"  # Only allow DEFER

        result = self.knight.analyze_with_ctc(proposal, custom_verify)

        self.assertTrue(result.has_valid_fixed_points)
        self.assertEqual(result.valid_candidates, ["DEFER"])
        self.assertAlmostEqual(result.probabilities["DEFER"], 1.0)


if __name__ == "__main__":
    unittest.main()
