#!/usr/bin/env python3
"""Unit tests for the Genesis BTC Collateral Loan module.

Tests cover:
- GenesisBTCProof creation, verification, and value computation
- GenesisCollateralVault sealing and consistency
- GenesisLoan creation, amortization, interest accrual, and repayment
- GenesisLoanEngine vault creation, loan creation, LTV enforcement
- Derivative creation on loans
- Liquidity pool deposits and borrows
- Multi-genesis vaults
- Loan summaries and engine statistics
"""

import time
import unittest

from sphinx_os.nexus.genesis_btc_loan import (
    GenesisBTCProof,
    GenesisCollateralVault,
    GenesisLoan,
    GenesisLoanDerivative,
    GenesisLoanPool,
    MultiGenesisVault,
    GenesisLoanEngine,
    LoanStatus,
    GENESIS_BLOCK_HASH,
    GENESIS_COINBASE_TX,
    GENESIS_NONCE,
    GENESIS_TIMESTAMP,
    GENESIS_COINBASE_VALUE,
)


class TestGenesisBTCProof(unittest.TestCase):
    """Tests for the GenesisBTCProof dataclass."""

    def test_default_genesis_proof(self):
        """Test that default proof matches Bitcoin Genesis Block."""
        proof = GenesisBTCProof(proof_id="test_1")
        self.assertEqual(proof.block_hash, GENESIS_BLOCK_HASH)
        self.assertEqual(proof.coinbase_tx, GENESIS_COINBASE_TX)
        self.assertEqual(proof.nonce, GENESIS_NONCE)
        self.assertEqual(proof.timestamp, GENESIS_TIMESTAMP)
        self.assertEqual(proof.coinbase_value, GENESIS_COINBASE_VALUE)

    def test_verify_true(self):
        """Test that a valid Genesis proof verifies."""
        proof = GenesisBTCProof(proof_id="test_1")
        self.assertTrue(proof.verify())

    def test_verify_false_tampered(self):
        """Test that a tampered proof fails verification."""
        proof = GenesisBTCProof(proof_id="test_1", block_hash="tampered_hash")
        self.assertFalse(proof.verify())

    def test_verification_key_computed(self):
        """Test that verification key is auto-computed."""
        proof = GenesisBTCProof(proof_id="test_1")
        self.assertGreater(len(proof.verification_key), 0)
        self.assertEqual(len(proof.verification_key), 64)  # SHA-256 hex

    def test_complexity_score_computed(self):
        """Test that complexity score is auto-computed."""
        proof = GenesisBTCProof(proof_id="test_1")
        self.assertGreater(proof.complexity_score, 0)

    def test_collateral_value(self):
        """Test collateral value computation."""
        proof = GenesisBTCProof(proof_id="test_1")
        value = proof.compute_collateral_value(btc_price_usd=100000.0)
        # Base: 50 * 100000 = 5,000,000
        # Multiplier: 10x = 50,000,000
        # Age bonus: ~17 years * 0.1 = 2.7x
        self.assertGreater(value, 50000000.0)

    def test_collateral_value_custom_price(self):
        """Test collateral value with custom BTC price."""
        proof = GenesisBTCProof(proof_id="test_1")
        value_low = proof.compute_collateral_value(btc_price_usd=1000.0)
        value_high = proof.compute_collateral_value(btc_price_usd=1000000.0)
        self.assertGreater(value_high, value_low)

    def test_custom_genesis_proof(self):
        """Test creating a custom genesis proof (e.g., Ethereum)."""
        proof = GenesisBTCProof(
            proof_id="eth_genesis",
            block_hash="d4e56740f876aef8c010b86a40d5f56745a118d0906a34e69aec8c0db1cb8fa3",
            coinbase_tx="0x0",
            nonce=0,
            timestamp=1438269973,
            embedded_message="Ethereum Genesis",
            coinbase_value=0.0,
        )
        self.assertFalse(proof.verify())  # Not Bitcoin genesis
        self.assertEqual(proof.coinbase_value, 0.0)


class TestGenesisCollateralVault(unittest.TestCase):
    """Tests for the GenesisCollateralVault dataclass."""

    def setUp(self):
        """Create a vault for testing."""
        self.proof = GenesisBTCProof(proof_id="vault_proof_1")
        self.vault = GenesisCollateralVault(vault_id="vault_1", genesis_proof=self.proof)

    def test_vault_creation(self):
        """Test vault creation."""
        self.assertEqual(self.vault.vault_id, "vault_1")
        self.assertTrue(self.vault.is_locked)
        self.assertEqual(self.vault.total_loans, 0)
        self.assertEqual(self.vault.total_borrowed, 0.0)

    def test_seal_intact(self):
        """Test that vault seal is intact."""
        self.assertTrue(self.vault.verify_seal())

    def test_seal_hash_computed(self):
        """Test that seal hash is auto-computed."""
        self.assertGreater(len(self.vault.lock_hash), 0)
        self.assertEqual(len(self.vault.lock_hash), 64)

    def test_collateral_consistency(self):
        """Test that collateral is consistent."""
        self.assertTrue(self.vault.collateral_consistency())

    def test_collateral_consistency_tampered(self):
        """Test consistency fails with tampered proof."""
        self.proof.block_hash = "tampered"
        self.assertFalse(self.vault.collateral_consistency())


class TestGenesisLoan(unittest.TestCase):
    """Tests for the GenesisLoan dataclass."""

    def setUp(self):
        """Create a loan for testing."""
        self.loan = GenesisLoan(
            loan_id="loan_1",
            vault_id="vault_1",
            borrower="alice",
            principal=100000.0,
            interest_rate=0.06,
            term_months=12,
            ltv_ratio=0.1,
        )

    def test_loan_creation(self):
        """Test loan creation."""
        self.assertEqual(self.loan.borrower, "alice")
        self.assertEqual(self.loan.principal, 100000.0)
        self.assertEqual(self.loan.interest_rate, 0.06)
        self.assertEqual(self.loan.status, LoanStatus.ACTIVE)

    def test_maturity_time(self):
        """Test that maturity time is computed."""
        self.assertGreater(self.loan.maturity_time, self.loan.creation_time)

    def test_monthly_payment(self):
        """Test monthly payment computation."""
        payment = self.loan.compute_monthly_payment()
        # At 6% APR for 12 months, payment should be ~$8,606
        self.assertGreater(payment, 8000)
        self.assertLess(payment, 9000)

    def test_monthly_payment_zero_rate(self):
        """Test monthly payment with zero interest."""
        loan = GenesisLoan(
            loan_id="loan_zero",
            vault_id="vault_1",
            borrower="bob",
            principal=12000.0,
            interest_rate=0.0,
            term_months=12,
            ltv_ratio=0.05,
        )
        self.assertAlmostEqual(loan.compute_monthly_payment(), 1000.0)

    def test_interest_accrual(self):
        """Test interest accrual over time."""
        future_time = time.time() + (30 * 24 * 3600)  # 30 days
        self.loan.accrue_interest(future_time)
        # 30 days at 6% APR on $100k = ~$493
        self.assertGreater(self.loan.accrued_interest, 400)
        self.assertLess(self.loan.accrued_interest, 600)

    def test_repayment(self):
        """Test making a repayment."""
        payment = self.loan.compute_monthly_payment()
        repayment = self.loan.make_repayment(payment)
        self.assertEqual(repayment["amount"], payment)
        self.assertGreater(self.loan.total_repaid, 0)
        self.assertEqual(len(self.loan.repayments), 1)

    def test_remaining_balance(self):
        """Test remaining balance computation."""
        self.assertAlmostEqual(self.loan.remaining_balance(), self.loan.principal, places=0)

    def test_remaining_balance_after_repayment(self):
        """Test remaining balance decreases after repayment."""
        payment = self.loan.compute_monthly_payment()
        self.loan.make_repayment(payment)
        remaining = self.loan.remaining_balance()
        self.assertLess(remaining, self.loan.principal)

    def test_full_repayment_status(self):
        """Test that loan status changes to REPAID after full repayment."""
        self.loan.total_repaid = self.loan.principal + 100  # Simulate full repayment
        self.loan.accrued_interest = 0
        # One more repayment triggers status change
        self.loan.make_repayment(1.0)
        self.assertEqual(self.loan.status, LoanStatus.REPAID)


class TestGenesisLoanDerivative(unittest.TestCase):
    """Tests for the GenesisLoanDerivative dataclass."""

    def test_derivative_creation(self):
        """Test derivative creation."""
        deriv = GenesisLoanDerivative(
            derivative_id="deriv_1",
            underlying_loan_id="loan_1",
            derivative_type="call",
            strike_price=0.05,
            expiration_time=time.time() + (180 * 24 * 3600),
            holder="alice",
            writer="bob",
        )
        self.assertEqual(deriv.derivative_type, "call")
        self.assertFalse(deriv.is_exercised)
        self.assertIsNone(deriv.payout)


class TestGenesisLoanPool(unittest.TestCase):
    """Tests for the GenesisLoanPool dataclass."""

    def test_pool_creation(self):
        """Test pool creation."""
        pool = GenesisLoanPool(pool_id="pool_1")
        self.assertEqual(pool.total_deposited, 0.0)
        self.assertEqual(pool.total_lent, 0.0)
        self.assertEqual(pool.average_rate, 0.05)


class TestMultiGenesisVault(unittest.TestCase):
    """Tests for the MultiGenesisVault dataclass."""

    def test_multi_vault_creation(self):
        """Test multi-genesis vault creation."""
        proof1 = GenesisBTCProof(proof_id="btc_genesis")
        proof2 = GenesisBTCProof(
            proof_id="eth_genesis",
            block_hash="d4e56740f876aef8c010b86a40d5f56745a118d0906a34e69aec8c0db1cb8fa3",
            coinbase_value=0.0,
        )
        vault = MultiGenesisVault(vault_id="multi_1", genesis_proofs=[proof1, proof2])
        self.assertEqual(len(vault.genesis_proofs), 2)
        self.assertGreater(vault.combined_value, 0)
        self.assertGreater(len(vault.lock_hash), 0)


class TestGenesisLoanEngine(unittest.TestCase):
    """Tests for the GenesisLoanEngine class."""

    def setUp(self):
        """Create an engine for testing."""
        self.engine = GenesisLoanEngine(max_ltv=0.5, default_interest_rate=0.05)

    def test_create_vault(self):
        """Test vault creation."""
        vault = self.engine.create_genesis_vault("test_vault")
        self.assertIn("test_vault", self.engine.vaults)
        self.assertTrue(vault.collateral_consistency())

    def test_create_loan(self):
        """Test loan creation."""
        vault = self.engine.create_genesis_vault("loan_vault")
        loan = self.engine.create_loan(
            vault_id=vault.vault_id,
            borrower="alice",
            principal=100000.0,
            term_months=12,
        )
        self.assertIn(loan.loan_id, self.engine.loans)
        self.assertEqual(loan.borrower, "alice")
        self.assertEqual(vault.total_loans, 1)

    def test_loan_ltv_exceeded(self):
        """Test that LTV limit is enforced."""
        vault = self.engine.create_genesis_vault("ltv_vault")
        # Try to borrow more than 50% of collateral value
        collateral_value = vault.genesis_proof.compute_collateral_value()
        with self.assertRaises(ValueError):
            self.engine.create_loan(
                vault_id=vault.vault_id,
                borrower="whale",
                principal=collateral_value * 10,  # Way too much
                term_months=12,
            )

    def test_loan_vault_not_found(self):
        """Test that loan creation fails for missing vault."""
        with self.assertRaises(ValueError):
            self.engine.create_loan(
                vault_id="nonexistent",
                borrower="alice",
                principal=100000.0,
            )

    def test_repay_loan(self):
        """Test loan repayment via engine."""
        vault = self.engine.create_genesis_vault("repay_vault")
        loan = self.engine.create_loan(
            vault_id=vault.vault_id,
            borrower="alice",
            principal=100000.0,
            term_months=12,
        )
        repayment = self.engine.repay_loan(loan.loan_id, 5000.0)
        self.assertEqual(repayment["amount"], 5000.0)

    def test_repay_loan_not_found(self):
        """Test repayment fails for missing loan."""
        with self.assertRaises(ValueError):
            self.engine.repay_loan("nonexistent", 1000.0)

    def test_create_derivative(self):
        """Test derivative creation."""
        vault = self.engine.create_genesis_vault("deriv_vault")
        loan = self.engine.create_loan(
            vault_id=vault.vault_id,
            borrower="alice",
            principal=100000.0,
        )
        deriv = self.engine.create_derivative(
            loan_id=loan.loan_id,
            derivative_type="call",
            strike_price=0.04,
            expiration_days=180,
            holder="hedger",
            writer="bank",
        )
        self.assertIn(deriv.derivative_id, self.engine.derivatives)
        self.assertEqual(deriv.derivative_type, "call")

    def test_create_pool(self):
        """Test pool creation."""
        pool = self.engine.create_pool("test_pool")
        self.assertIn("test_pool", self.engine.pools)

    def test_deposit_to_pool(self):
        """Test depositing to pool."""
        pool = self.engine.create_pool("deposit_pool")
        total = self.engine.deposit_to_pool(pool.pool_id, "alice", 100000.0)
        self.assertEqual(total, 100000.0)
        self.assertEqual(pool.depositors["alice"], 100000.0)

    def test_borrow_from_pool(self):
        """Test borrowing from pool."""
        pool = self.engine.create_pool("borrow_pool")
        self.engine.deposit_to_pool(pool.pool_id, "alice", 100000.0)
        total = self.engine.borrow_from_pool(pool.pool_id, "bob", 50000.0)
        self.assertEqual(total, 50000.0)
        self.assertEqual(pool.borrowers["bob"], 50000.0)

    def test_borrow_insufficient_liquidity(self):
        """Test borrowing fails with insufficient liquidity."""
        pool = self.engine.create_pool("dry_pool")
        self.engine.deposit_to_pool(pool.pool_id, "alice", 1000.0)
        with self.assertRaises(ValueError):
            self.engine.borrow_from_pool(pool.pool_id, "bob", 5000.0)

    def test_multi_genesis_vault(self):
        """Test multi-genesis vault creation."""
        proof1 = GenesisBTCProof(proof_id="btc")
        proof2 = GenesisBTCProof(
            proof_id="eth",
            block_hash="d4e56740f876aef8c010b86a40d5f56745a118d0906a34e69aec8c0db1cb8fa3",
            coinbase_value=0.0,
        )
        vault = self.engine.create_multi_genesis_vault("multi_1", [proof1, proof2])
        self.assertIn("multi_1", self.engine.multi_vaults)

    def test_loan_summary(self):
        """Test loan summary retrieval."""
        vault = self.engine.create_genesis_vault("summary_vault")
        loan = self.engine.create_loan(
            vault_id=vault.vault_id,
            borrower="alice",
            principal=100000.0,
        )
        summary = self.engine.get_loan_summary(loan.loan_id)
        self.assertEqual(summary["loan_id"], loan.loan_id)
        self.assertEqual(summary["borrower"], "alice")
        self.assertTrue(summary["collateral_consistent"])

    def test_engine_stats(self):
        """Test engine statistics."""
        vault = self.engine.create_genesis_vault("stats_vault")
        self.engine.create_loan(
            vault_id=vault.vault_id,
            borrower="alice",
            principal=100000.0,
        )
        stats = self.engine.get_engine_stats()
        self.assertEqual(stats["total_vaults"], 1)
        self.assertEqual(stats["total_loans"], 1)
        self.assertEqual(stats["active_loans"], 1)
        self.assertEqual(stats["total_borrowed"], 100000.0)


if __name__ == "__main__":
    unittest.main()
