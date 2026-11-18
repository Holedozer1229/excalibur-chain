#!/usr/bin/env python3
"""Unit tests for the CTC Oracle Market module.

Tests cover:
- CTCOracleProof creation, verification, and value computation
- OracleMarket order matching and trade execution
- CausalBond creation and management
- OracleDerivative creation
- LiquidityPool AMM swaps
- ProofAggregator compound proofs
- ProofFactory proof creation
- Staking rewards
- CausalInsurance policies
- Arbitrage detection
- Market statistics and depth
"""

import hashlib
import json
import math
import time
import unittest

from sphinx_os.nexus.ctc_oracle_market import (
    CTCOracleProof,
    OracleProofStatus,
    ProofType,
    OracleOrder,
    OracleTrade,
    CausalBond,
    OracleDerivative,
    LiquidityPoolState,
    StakingReward,
    CausalInsurance,
    ArbitrageOpportunity,
    OracleMarket,
    ProofAggregator,
    ProofFactory,
)


class TestCTCOracleProof(unittest.TestCase):
    """Tests for the CTCOracleProof dataclass."""

    def setUp(self):
        """Create a sample oracle proof for testing."""
        self.problem = {"type": "3sat", "clauses": [[1, 2, 3], [-1, -2, 4]]}
        self.solution = {1: True, 2: False, 3: True, 4: True}
        self.certificate = {"fixed_point": self.solution, "consistency_check": True}

        content = json.dumps({
            "problem": self.problem,
            "solution": self.solution,
            "certificate": self.certificate,
        }, sort_keys=True)
        self.verification_key = hashlib.sha256(content.encode()).hexdigest()

        self.proof = CTCOracleProof(
            proof_id="test_1",
            proof_type=ProofType.SAT,
            problem_statement=self.problem,
            solution=self.solution,
            fixed_point_certificate=self.certificate,
            verification_key=self.verification_key,
            complexity_score=20.0,
            confidence=1.0,
            timestamp=time.time(),
            status=OracleProofStatus.VERIFIED,
            creator="test_user",
            price=100.0,
        )

    def test_proof_verification(self):
        """Test that a valid proof verifies correctly."""
        self.assertTrue(self.proof.verify())

    def test_proof_verification_tampered(self):
        """Test that a tampered proof fails verification."""
        self.proof.verification_key = "tampered_key"
        self.assertFalse(self.proof.verify())

    def test_proof_value_computation(self):
        """Test that proof value is computed correctly."""
        value = self.proof.compute_value()
        # Base value = complexity * 100 = 20 * 100 = 2000
        # Confidence multiplier = 1.0
        # Type multiplier for SAT = 1.0
        # Age decay ~ 1.0 (just created)
        self.assertGreater(value, 0)
        self.assertLessEqual(value, 2000.0)

    def test_proof_value_qbf_multiplier(self):
        """Test that QBF proofs have higher value multiplier."""
        qbf_proof = CTCOracleProof(
            proof_id="qbf_1",
            proof_type=ProofType.QBF,
            problem_statement={"type": "qbf"},
            solution={},
            fixed_point_certificate={},
            verification_key="key",
            complexity_score=20.0,
            confidence=1.0,
            timestamp=time.time(),
            status=OracleProofStatus.VERIFIED,
            creator="test",
            price=0.0,
        )
        # QBF multiplier is 3.0, so value should be ~3x SAT
        qbf_value = qbf_proof.compute_value()
        self.assertGreater(qbf_value, self.proof.compute_value())

    def test_proof_status(self):
        """Test proof status enum."""
        self.assertEqual(self.proof.status, OracleProofStatus.VERIFIED)

    def test_proof_trade_history(self):
        """Test that trade history is recorded."""
        self.proof.trade_history.append({
            "trade_id": "trade_1",
            "buyer": "alice",
            "seller": "bob",
            "price": 100.0,
        })
        self.assertEqual(len(self.proof.trade_history), 1)
        self.assertEqual(self.proof.trade_history[0]["buyer"], "alice")


class TestOracleMarket(unittest.TestCase):
    """Tests for the OracleMarket trading engine."""

    def setUp(self):
        """Create a market and sample proofs."""
        self.market = OracleMarket(fee_rate=0.001)

        self.problem = {"type": "3sat", "clauses": [[1, 2, 3]]}
        self.solution = {1: True}
        self.certificate = {"fixed_point": self.solution}

        content = json.dumps({
            "problem": self.problem,
            "solution": self.solution,
            "certificate": self.certificate,
        }, sort_keys=True)
        self.vk = hashlib.sha256(content.encode()).hexdigest()

        self.proof = CTCOracleProof(
            proof_id="market_proof_1",
            proof_type=ProofType.SAT,
            problem_statement=self.problem,
            solution=self.solution,
            fixed_point_certificate=self.certificate,
            verification_key=self.vk,
            complexity_score=10.0,
            confidence=1.0,
            timestamp=time.time(),
            status=OracleProofStatus.VERIFIED,
            creator="alice",
            price=100.0,
        )
        self.market.register_proof(self.proof)

    def test_register_proof(self):
        """Test proof registration."""
        self.assertIn("market_proof_1", self.market.proofs)
        self.assertEqual(len(self.market.proofs), 1)

    def test_place_order(self):
        """Test order placement."""
        order = OracleOrder(
            order_id="order_1",
            proof_id="market_proof_1",
            side="buy",
            price=50.0,
            quantity=1,
            timestamp=time.time(),
            status="open",
            trader="bob",
        )
        self.market.place_order(order)
        self.assertIn("order_1", self.market.orders)

    def test_order_matching(self):
        """Test that buy and sell orders are matched."""
        sell_order = OracleOrder(
            order_id="sell_1",
            proof_id="market_proof_1",
            side="sell",
            price=45.0,
            quantity=1,
            timestamp=time.time(),
            status="open",
            trader="alice",
        )
        buy_order = OracleOrder(
            order_id="buy_1",
            proof_id="market_proof_1",
            side="buy",
            price=50.0,
            quantity=1,
            timestamp=time.time(),
            status="open",
            trader="bob",
        )
        self.market.place_order(sell_order)
        self.market.place_order(buy_order)

        # Should have executed a trade
        self.assertEqual(len(self.market.trades), 1)
        trade = self.market.trades[0]
        self.assertEqual(trade.buyer, "bob")
        self.assertEqual(trade.seller, "alice")
        self.assertAlmostEqual(trade.price, 47.5)  # Average of 45 and 50

    def test_trade_fee(self):
        """Test that trading fees are deducted."""
        sell_order = OracleOrder(
            order_id="sell_1",
            proof_id="market_proof_1",
            side="sell",
            price=100.0,
            quantity=1,
            timestamp=time.time(),
            status="open",
            trader="alice",
        )
        buy_order = OracleOrder(
            order_id="buy_1",
            proof_id="market_proof_1",
            side="buy",
            price=100.0,
            quantity=1,
            timestamp=time.time(),
            status="open",
            trader="bob",
        )
        self.market.place_order(sell_order)
        self.market.place_order(buy_order)

        trade = self.market.trades[0]
        expected_value = 100.0 * (1 - 0.001)  # 100 - 0.1% fee
        self.assertAlmostEqual(trade.total_value, expected_value)

    def test_create_causal_bond(self):
        """Test causal bond creation."""
        bond = self.market.create_causal_bond(
            proof_id="market_proof_1",
            face_value=1000.0,
            interest_rate=0.05,
            maturity_years=1.0,
            issuer="alice",
        )
        self.assertEqual(bond.face_value, 1000.0)
        self.assertEqual(bond.interest_rate, 0.05)
        self.assertTrue(bond.is_consistent)
        self.assertIn(bond.bond_id, self.market.bonds)

    def test_create_derivative(self):
        """Test derivative creation."""
        deriv = self.market.create_derivative(
            proof_id="market_proof_1",
            derivative_type="call_option",
            strike_price=100.0,
            expiration_days=30,
            holder="bob",
            writer="alice",
        )
        self.assertEqual(deriv.derivative_type, "call_option")
        self.assertEqual(deriv.strike_price, 100.0)
        self.assertFalse(deriv.is_exercised)
        self.assertIn(deriv.derivative_id, self.market.derivatives)

    def test_create_liquidity_pool(self):
        """Test liquidity pool creation."""
        pool = self.market.create_liquidity_pool(
            proof_type=ProofType.SAT,
            initial_proofs=10.0,
            initial_tokens=1000.0,
        )
        self.assertEqual(pool.invariant, 10000.0)  # 10 * 1000
        self.assertIn(pool.pool_id, self.market.liquidity_pools)

    def test_swap_in_pool(self):
        """Test AMM swap in liquidity pool."""
        pool = self.market.create_liquidity_pool(
            proof_type=ProofType.SAT,
            initial_proofs=10.0,
            initial_tokens=1000.0,
        )
        amount_out = self.market.swap_in_pool(pool.pool_id, 1.0, "trader")
        self.assertGreater(amount_out, 0)
        # After swap, reserves should change
        self.assertGreater(pool.reserve_proofs, 10.0)
        self.assertLess(pool.reserve_tokens, 1000.0)

    def test_swap_invalid_pool(self):
        """Test swap with invalid pool ID."""
        with self.assertRaises(ValueError):
            self.market.swap_in_pool("nonexistent", 1.0, "trader")

    def test_stake_proofs(self):
        """Test proof staking."""
        staking = self.market.stake_proofs(
            ["market_proof_1"],
            "alice",
        )
        self.assertEqual(staking.staker, "alice")
        self.assertGreater(staking.staked_value, 0)
        self.assertGreater(staking.reward_rate, 0)
        self.assertIn("alice", self.market.staking_positions)

    def test_create_insurance(self):
        """Test causal insurance creation."""
        insurance = self.market.create_insurance(
            proof_id="market_proof_1",
            coverage_amount=500.0,
            insured_party="bob",
            insurer="alice",
        )
        self.assertEqual(insurance.coverage_amount, 500.0)
        self.assertTrue(insurance.is_active)
        self.assertFalse(insurance.has_claims)
        self.assertIn(insurance.policy_id, self.market.insurance_policies)

    def test_detect_arbitrage(self):
        """Test arbitrage detection."""
        arb = self.market.detect_arbitrage(
            proof_id="market_proof_1",
            timeline_a_price=45.0,
            timeline_b_price=50.0,
            transaction_cost=0.001,
        )
        self.assertIsNotNone(arb)
        self.assertEqual(arb.spread, 5.0)
        self.assertGreater(arb.expected_profit, 0)

    def test_no_arbitrage(self):
        """Test that no arbitrage is detected when prices are equal."""
        arb = self.market.detect_arbitrage(
            proof_id="market_proof_1",
            timeline_a_price=50.0,
            timeline_b_price=50.0,
            transaction_cost=0.001,
        )
        self.assertIsNone(arb)

    def test_market_stats(self):
        """Test market statistics."""
        stats = self.market.get_market_stats()
        self.assertEqual(stats["total_proofs"], 1)
        self.assertEqual(stats["total_bonds"], 0)
        self.assertEqual(stats["total_derivatives"], 0)

    def test_market_depth(self):
        """Test market depth (order book)."""
        order = OracleOrder(
            order_id="depth_order",
            proof_id="market_proof_1",
            side="buy",
            price=50.0,
            quantity=1,
            timestamp=time.time(),
            status="open",
            trader="bob",
        )
        self.market.place_order(order)
        depth = self.market.get_market_depth("market_proof_1")
        self.assertEqual(len(depth["bids"]), 1)
        self.assertEqual(len(depth["asks"]), 0)


class TestProofAggregator(unittest.TestCase):
    """Tests for the ProofAggregator class."""

    def setUp(self):
        """Create sample proofs for aggregation."""
        self.aggregator = ProofAggregator()

        # Create two proofs
        content1 = json.dumps({"problem": "p1", "solution": "s1", "certificate": "c1"}, sort_keys=True)
        vk1 = hashlib.sha256(content1.encode()).hexdigest()

        self.proof1 = CTCOracleProof(
            proof_id="agg_1",
            proof_type=ProofType.SAT,
            problem_statement={"type": "sat"},
            solution={"x": True},
            fixed_point_certificate={"fp": True},
            verification_key=vk1,
            complexity_score=10.0,
            confidence=1.0,
            timestamp=time.time(),
            status=OracleProofStatus.VERIFIED,
            creator="alice",
            price=0.0,
        )

        content2 = json.dumps({"problem": "p2", "solution": "s2", "certificate": "c2"}, sort_keys=True)
        vk2 = hashlib.sha256(content2.encode()).hexdigest()

        self.proof2 = CTCOracleProof(
            proof_id="agg_2",
            proof_type=ProofType.FACTORIZATION,
            problem_statement={"type": "factor"},
            solution={"factors": [3, 5]},
            fixed_point_certificate={"fp": True},
            verification_key=vk2,
            complexity_score=20.0,
            confidence=1.0,
            timestamp=time.time(),
            status=OracleProofStatus.VERIFIED,
            creator="bob",
            price=0.0,
        )

    def test_aggregate_proofs(self):
        """Test proof aggregation."""
        compound = self.aggregator.aggregate([self.proof1, self.proof2])
        self.assertEqual(compound.complexity_score, 30.0)  # 10 + 20
        self.assertEqual(compound.confidence, 1.0)  # 1.0 * 1.0
        self.assertTrue(compound.verify())

    def test_aggregate_empty(self):
        """Test that aggregating empty list raises error."""
        with self.assertRaises(ValueError):
            self.aggregator.aggregate([])

    def test_compound_proof_stored(self):
        """Test that compound proof is stored."""
        compound = self.aggregator.aggregate([self.proof1, self.proof2])
        self.assertIn(compound.proof_id, self.aggregator.compound_proofs)

    def test_entanglement_entropy(self):
        """Test entanglement entropy calculation."""
        compound = self.aggregator.aggregate([self.proof1, self.proof2])
        entanglement = compound.solution["entanglement_certificate"]
        expected_entropy = math.log2(2)  # 2 proofs
        self.assertAlmostEqual(entanglement["entanglement_entropy"], expected_entropy)


class TestProofFactory(unittest.TestCase):
    """Tests for the ProofFactory class."""

    def setUp(self):
        self.factory = ProofFactory()

    def test_create_sat_proof(self):
        """Test SAT proof creation."""
        clauses = [(1, 2, 3), (-1, -2, 4)]
        solution = {1: True, 2: False, 3: True, 4: True}
        proof = self.factory.create_sat_proof(clauses, solution, "alice")

        self.assertEqual(proof.proof_type, ProofType.SAT)
        self.assertTrue(proof.verify())
        self.assertEqual(proof.status, OracleProofStatus.VERIFIED)

    def test_create_sat_proof_invalid(self):
        """Test SAT proof with invalid solution."""
        clauses = [(1, 2, 3), (-1, -2, 4)]
        solution = {1: False, 2: False, 3: False, 4: False}  # Doesn't satisfy
        proof = self.factory.create_sat_proof(clauses, solution, "alice")

        self.assertEqual(proof.status, OracleProofStatus.PENDING)
        self.assertEqual(proof.confidence, 0.0)

    def test_create_factorization_proof(self):
        """Test factorization proof creation."""
        proof = self.factory.create_factorization_proof(15, (3, 5), "bob")

        self.assertEqual(proof.proof_type, ProofType.FACTORIZATION)
        self.assertTrue(proof.verify())
        self.assertEqual(proof.status, OracleProofStatus.VERIFIED)

    def test_create_factorization_proof_invalid(self):
        """Test factorization proof with wrong factors."""
        proof = self.factory.create_factorization_proof(15, (3, 4), "bob")

        self.assertEqual(proof.status, OracleProofStatus.PENDING)
        self.assertEqual(proof.confidence, 0.0)

    def test_create_custom_proof(self):
        """Test custom proof creation."""
        proof = self.factory.create_custom_proof(
            "graph_coloring",
            {"nodes": 4},
            {"colors": {0: "red", 1: "blue"}},
            lambda p, s: True,
            "charlie",
        )

        self.assertEqual(proof.proof_type, ProofType.CUSTOM)
        self.assertTrue(proof.verify())
        self.assertEqual(proof.status, OracleProofStatus.VERIFIED)

    def test_factory_tracks_proofs(self):
        """Test that factory tracks created proofs."""
        self.factory.create_sat_proof([(1, 2)], {1: True}, "alice")
        self.factory.create_factorization_proof(15, (3, 5), "bob")
        self.assertEqual(len(self.factory.created_proofs), 2)


class TestDataClasses(unittest.TestCase):
    """Tests for dataclass structures."""

    def test_oracle_order(self):
        """Test OracleOrder creation."""
        order = OracleOrder(
            order_id="o1",
            proof_id="p1",
            side="buy",
            price=100.0,
            quantity=1,
            timestamp=time.time(),
            status="open",
            trader="alice",
        )
        self.assertEqual(order.side, "buy")
        self.assertEqual(order.price, 100.0)

    def test_oracle_trade(self):
        """Test OracleTrade creation."""
        trade = OracleTrade(
            trade_id="t1",
            proof_id="p1",
            buyer="alice",
            seller="bob",
            price=100.0,
            quantity=1,
            timestamp=time.time(),
            total_value=99.9,
        )
        self.assertEqual(trade.buyer, "alice")
        self.assertAlmostEqual(trade.total_value, 99.9)

    def test_causal_bond(self):
        """Test CausalBond creation."""
        bond = CausalBond(
            bond_id="b1",
            proof_id="p1",
            face_value=1000.0,
            interest_rate=0.05,
            maturity_date=time.time() + 365 * 24 * 3600,
            issuer="alice",
            holders=["alice"],
            is_consistent=True,
            payout_status="pending",
        )
        self.assertTrue(bond.is_consistent)
        self.assertEqual(bond.payout_status, "pending")

    def test_oracle_derivative(self):
        """Test OracleDerivative creation."""
        deriv = OracleDerivative(
            derivative_id="d1",
            underlying_proof_id="p1",
            derivative_type="call_option",
            strike_price=100.0,
            expiration_date=time.time() + 30 * 24 * 3600,
            holder="alice",
            writer="bob",
            is_exercised=False,
            payout=None,
        )
        self.assertFalse(deriv.is_exercised)
        self.assertIsNone(deriv.payout)

    def test_liquidity_pool_state(self):
        """Test LiquidityPoolState creation."""
        pool = LiquidityPoolState(
            pool_id="pool_1",
            proof_type=ProofType.SAT,
            reserve_proofs=10.0,
            reserve_tokens=1000.0,
            invariant=10000.0,
            total_shares=1000.0,
            traders={},
        )
        self.assertEqual(pool.invariant, 10000.0)

    def test_staking_reward(self):
        """Test StakingReward creation."""
        staking = StakingReward(
            staker="alice",
            proof_ids=["p1", "p2"],
            staked_value=500.0,
            reward_rate=0.05,
            total_rewards=0.0,
            staking_duration=0.0,
        )
        self.assertEqual(staking.staker, "alice")
        self.assertEqual(len(staking.proof_ids), 2)

    def test_causal_insurance(self):
        """Test CausalInsurance creation."""
        insurance = CausalInsurance(
            policy_id="ins_1",
            proof_id="p1",
            coverage_amount=500.0,
            premium=50.0,
            insured_party="alice",
            insurer="bob",
            is_active=True,
            has_claims=False,
            payout_amount=None,
        )
        self.assertTrue(insurance.is_active)
        self.assertFalse(insurance.has_claims)

    def test_arbitrage_opportunity(self):
        """Test ArbitrageOpportunity creation."""
        arb = ArbitrageOpportunity(
            opportunity_id="arb_1",
            proof_id="p1",
            timeline_a_price=45.0,
            timeline_b_price=50.0,
            spread=5.0,
            expected_profit=4.95,
            detection_time=time.time(),
        )
        self.assertEqual(arb.spread, 5.0)
        self.assertGreater(arb.expected_profit, 0)


class TestProofType(unittest.TestCase):
    """Tests for ProofType enum."""

    def test_proof_types(self):
        """Test all proof types exist."""
        self.assertEqual(ProofType.SAT.value, "sat")
        self.assertEqual(ProofType.QBF.value, "qbf")
        self.assertEqual(ProofType.FACTORIZATION.value, "factorization")
        self.assertEqual(ProofType.HASH_COLLISION.value, "hash_collision")
        self.assertEqual(ProofType.GRAPH_COLORING.value, "graph_coloring")
        self.assertEqual(ProofType.TSP.value, "tsp")
        self.assertEqual(ProofType.CUSTOM.value, "custom")


class TestOracleProofStatus(unittest.TestCase):
    """Tests for OracleProofStatus enum."""

    def test_statuses(self):
        """Test all proof statuses exist."""
        self.assertEqual(OracleProofStatus.PENDING.value, "pending")
        self.assertEqual(OracleProofStatus.VERIFIED.value, "verified")
        self.assertEqual(OracleProofStatus.TRADED.value, "traded")
        self.assertEqual(OracleProofStatus.REDEEMED.value, "redeemed")
        self.assertEqual(OracleProofStatus.EXPIRED.value, "expired")


if __name__ == "__main__":
    unittest.main()
