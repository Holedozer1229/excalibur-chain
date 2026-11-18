"""Tests for AI Oracle Knights — Autonomous AI governance agents."""

import hashlib
import unittest
from sphinx_os.nexus.ai_oracle_knight import (
    AIOracleKnight,
    OracleCouncil,
    OracleType,
    OracleAnalysis,
    OracleHealth,
)
from sphinx_os.nexus.knights_round_table import (
    KnightsRoundTable,
    ProposalType,
    GovernanceProposal,
    VoteStatus,
)


class TestAIOracleKnight(unittest.TestCase):
    """Test AI Oracle Knight creation and analysis."""

    def setUp(self):
        self.seed = hashlib.sha256(b"oracle-test-seed").digest()
        self.oracle = AIOracleKnight(
            name="Test-Oracle",
            oracle_type=OracleType.ORACLE,
            seed=self.seed,
            participant_index=0,
            phi_score=0.8,
            uruu_balance=200.0,
            excal_stake=2000.0,
        )

    def test_oracle_creation(self):
        """Test oracle is created with correct attributes."""
        self.assertEqual(self.oracle.name, "Test-Oracle")
        self.assertEqual(self.oracle.oracle_type, OracleType.ORACLE)
        self.assertEqual(self.oracle.phi_score, 0.8)
        self.assertEqual(self.oracle.uruu_balance, 200.0)
        self.assertEqual(self.oracle.excal_stake, 2000.0)

    def test_musig2_key_pair(self):
        """Test oracle has a valid MuSig2 key pair."""
        self.assertIsNotNone(self.oracle.key_pair)
        self.assertEqual(len(self.oracle.key_pair.xonly_pubkey), 32)
        self.assertGreater(self.oracle.key_pair.secret_key, 0)

    def test_risk_threshold(self):
        """Test risk threshold is set based on oracle type."""
        sentinel = AIOracleKnight("S", OracleType.SENTINEL, self.seed, 0)
        self.assertEqual(sentinel.risk_threshold, 0.3)

        treasurer = AIOracleKnight("T", OracleType.TREASURER, self.seed, 0)
        self.assertEqual(treasurer.risk_threshold, 0.4)

    def test_health_report(self):
        """Test health report contains correct data."""
        health = self.oracle.get_health()
        self.assertIsInstance(health, OracleHealth)
        self.assertEqual(health.oracle_name, "Test-Oracle")
        self.assertTrue(health.is_active)
        self.assertEqual(health.phi_score, 0.8)
        self.assertEqual(health.votes_cast, 0)

    def test_analysis_summary_empty(self):
        """Test analysis summary when no analyses performed."""
        summary = self.oracle.get_analysis_summary()
        self.assertEqual(summary["total"], 0)

    def test_record_prediction(self):
        """Test prediction accuracy tracking."""
        self.oracle.record_prediction(True)
        self.oracle.record_prediction(False)
        self.oracle.record_prediction(True)
        health = self.oracle.get_health()
        self.assertAlmostEqual(health.accuracy_score, 2/3, places=2)


class TestOracleProposalAnalysis(unittest.TestCase):
    """Test AI Oracle proposal analysis."""

    def setUp(self):
        self.seed = hashlib.sha256(b"analysis-test").digest()
        self.table = KnightsRoundTable()
        for i in range(5):
            self.table.add_founder_knight(
                name=f"Knight_{i}",
                public_key=hashlib.sha256(f"k{i}".encode()).digest(),
                uruu_balance=200.0,
                phi_score=0.8,
                excal_stake=2000.0,
            )

        self.oracle = AIOracleKnight(
            name="Test-Oracle",
            oracle_type=OracleType.TREASURER,
            seed=self.seed,
            participant_index=5,
            phi_score=0.8,
        )

    def _create_proposal(self, ptype, params):
        """Helper to create a proposal."""
        return self.table.create_proposal(
            proposal_type=ptype,
            proposer="Knight_0",
            description="Test proposal",
            parameters=params,
        )

    def test_treasury_spend_analysis(self):
        """Test treasury spend proposal analysis."""
        proposal = self._create_proposal(
            ProposalType.TREASURY_SPEND,
            {"amount": 100.0, "recipient": "bc1qtest"},
        )
        analysis = self.oracle.analyze_proposal(proposal)
        self.assertIsInstance(analysis, OracleAnalysis)
        self.assertGreater(analysis.risk_score, 0)
        self.assertLess(analysis.risk_score, 1)
        self.assertIsInstance(analysis.recommendation, bool)

    def test_small_amount_approved(self):
        """Test small treasury spend is approved."""
        proposal = self._create_proposal(
            ProposalType.TREASURY_SPEND,
            {"amount": 10.0, "recipient": "bc1qtest"},
        )
        analysis = self.oracle.analyze_proposal(proposal)
        self.assertTrue(analysis.recommendation)

    def test_large_amount_rejected(self):
        """Test large treasury spend is rejected."""
        proposal = self._create_proposal(
            ProposalType.TREASURY_SPEND,
            {"amount": 50000.0, "recipient": "bc1qtest"},
        )
        analysis = self.oracle.analyze_proposal(proposal)
        self.assertFalse(analysis.recommendation)

    def test_bridge_deploy_high_risk(self):
        """Test bridge deployment is high risk."""
        proposal = self._create_proposal(
            ProposalType.BRIDGE_DEPLOY,
            {"target": "ethereum"},
        )
        analysis = self.oracle.analyze_proposal(proposal)
        self.assertGreater(analysis.risk_score, 0.3)

    def test_domain_scores_present(self):
        """Test domain scores are computed."""
        proposal = self._create_proposal(
            ProposalType.TREASURY_SPEND,
            {"amount": 100.0, "recipient": "bc1qtest"},
        )
        analysis = self.oracle.analyze_proposal(proposal)
        self.assertIn("security", analysis.domain_scores)
        self.assertIn("economic", analysis.domain_scores)
        self.assertIn("governance", analysis.domain_scores)
        self.assertIn("bridge", analysis.domain_scores)

    def test_reasoning_generated(self):
        """Test reasoning string is generated."""
        proposal = self._create_proposal(
            ProposalType.TREASURY_SPEND,
            {"amount": 100.0, "recipient": "bc1qtest"},
        )
        analysis = self.oracle.analyze_proposal(proposal)
        self.assertGreater(len(analysis.reasoning), 0)
        self.assertIn("TREASURER", analysis.reasoning)

    def test_confidence_based_on_phi(self):
        """Test confidence is based on phi score."""
        proposal = self._create_proposal(
            ProposalType.TREASURY_SPEND,
            {"amount": 100.0, "recipient": "bc1qtest"},
        )
        analysis = self.oracle.analyze_proposal(proposal)
        self.assertGreaterEqual(analysis.confidence, self.oracle.phi_score)

    def test_analysis_history_tracked(self):
        """Test analyses are tracked in history."""
        proposal = self._create_proposal(
            ProposalType.TREASURY_SPEND,
            {"amount": 100.0, "recipient": "bc1qtest"},
        )
        self.oracle.analyze_proposal(proposal)
        self.oracle.analyze_proposal(proposal)
        self.assertEqual(self.oracle.proposals_analyzed, 2)
        self.assertEqual(len(self.oracle.analysis_history), 2)


class TestOracleTypes(unittest.TestCase):
    """Test different oracle type specializations."""

    def setUp(self):
        self.seed = hashlib.sha256(b"type-test").digest()

    def test_sentinel_conservative(self):
        """Test sentinel oracle is conservative on security."""
        oracle = AIOracleKnight("S", OracleType.SENTINEL, self.seed, 0)
        self.assertEqual(oracle.risk_threshold, 0.3)
        self.assertGreater(oracle.domain_weights["security"], 0.4)

    def test_treasurer_economic_focus(self):
        """Test treasurer oracle focuses on economics."""
        oracle = AIOracleKnight("T", OracleType.TREASURER, self.seed, 0)
        self.assertEqual(oracle.risk_threshold, 0.4)
        self.assertGreater(oracle.domain_weights["economic"], 0.4)

    def test_bridge_cross_chain_focus(self):
        """Test bridge oracle focuses on cross-chain risk."""
        oracle = AIOracleKnight("B", OracleType.BRIDGE, self.seed, 0)
        self.assertEqual(oracle.risk_threshold, 0.35)
        self.assertGreater(oracle.domain_weights["bridge"], 0.3)

    def test_curve_tokenomics_focus(self):
        """Test curve oracle focuses on tokenomics."""
        oracle = AIOracleKnight("C", OracleType.CURVE, self.seed, 0)
        self.assertEqual(oracle.risk_threshold, 0.45)
        self.assertGreater(oracle.domain_weights["economic"], 0.4)


class TestOracleCouncil(unittest.TestCase):
    """Test Oracle Council factory and management."""

    def setUp(self):
        self.master_seed = hashlib.sha256(b"council-master").digest()
        self.council = OracleCouncil(self.master_seed)

    def test_create_oracle(self):
        """Test creating a single oracle."""
        oracle = self.council.create_oracle("Custom-1", OracleType.SENTINEL)
        self.assertIn("Custom-1", self.council.oracles)
        self.assertEqual(oracle.oracle_type, OracleType.SENTINEL)

    def test_create_default_council(self):
        """Test creating the default council of 5 oracles."""
        oracles = self.council.create_default_council()
        self.assertEqual(len(oracles), 5)
        self.assertEqual(len(self.council.oracles), 5)

    def test_default_oracle_types(self):
        """Test default council has all oracle types."""
        self.council.create_default_council()
        types = {o.oracle_type for o in self.council.oracles.values()}
        self.assertEqual(len(types), 5)

    def test_get_key_pairs(self):
        """Test getting all key pairs."""
        self.council.create_default_council()
        keys = self.council.get_all_key_pairs()
        self.assertEqual(len(keys), 5)

    def test_health_report(self):
        """Test health report for all oracles."""
        self.council.create_default_council()
        report = self.council.get_health_report()
        self.assertEqual(len(report), 5)

    def test_integrate_with_round_table(self):
        """Test integrating oracles with KnightsRoundTable."""
        self.council.create_default_council()
        table = KnightsRoundTable()
        self.council.integrate_with_round_table(table)

        # Check all oracles are added as knights
        for name in self.council.oracles:
            self.assertIn(name, table.knights)

        # Check aggregate key is computed
        self.assertIsNotNone(table.get_aggregate_musig2_key())


class TestOracleVoting(unittest.TestCase):
    """Test oracle voting with MuSig2."""

    def setUp(self):
        self.master_seed = hashlib.sha256(b"voting-test").digest()
        self.council = OracleCouncil(self.master_seed)
        self.council.create_default_council()

        self.table = KnightsRoundTable()
        self.council.integrate_with_round_table(self.table)

    def test_oracle_can_vote(self):
        """Test oracle can cast a vote."""
        oracle = self.council.oracles["Sentinel-Alpha"]
        agg_key = self.table.get_aggregate_musig2_key()
        agg_point = self.table._aggregate_musig2_point
        all_xonly = [
            self.table._musig2_key_pairs[n].xonly_pubkey
            for n in self.table.get_active_knight_names()
        ]

        proposal_hash = hashlib.sha256(b"test proposal").digest()
        ps = oracle.vote(proposal_hash, agg_key, agg_point, all_xonly, b"nonce-seed")

        self.assertIsNotNone(ps)
        self.assertEqual(ps.knight_name, "Sentinel-Alpha")
        self.assertEqual(len(ps.partial_r), 32)

    def test_multiple_oracles_vote(self):
        """Test multiple oracles can vote."""
        agg_key = self.table.get_aggregate_musig2_key()
        agg_point = self.table._aggregate_musig2_point
        all_xonly = [
            self.table._musig2_key_pairs[n].xonly_pubkey
            for n in self.table.get_active_knight_names()
        ]
        proposal_hash = hashlib.sha256(b"test proposal").digest()

        partials = []
        for i, (name, oracle) in enumerate(self.council.oracles.items()):
            ps = oracle.vote(proposal_hash, agg_key, agg_point, all_xonly, f"seed{i}".encode())
            if ps:
                partials.append(ps)

        # At least some oracles should vote
        self.assertGreater(len(partials), 0)


if __name__ == "__main__":
    unittest.main()
