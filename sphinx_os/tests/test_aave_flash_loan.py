#!/usr/bin/env python3
"""Unit tests for the Aave Flash Loan Engine module.

Tests cover:
- FlashLoan creation, operations, profitability
- FlashLoanPool deposits, withdrawals, flash loan availability
- FlashLoanFeeCalculator fee computation
- FlashLoanExecutor execution, arbitrage, liquidation
- GenesisFlashVault verification
- Failed flash loan atomic revert
"""

import time
import unittest

from sphinx_os.nexus.aave_flash_loan import (
    FlashLoan,
    FlashLoanPool,
    FlashLoanStrategy,
    FlashLoanArbitrage,
    FlashLoanLiquidation,
    GenesisFlashVault,
    FlashLoanFeeCalculator,
    FlashLoanExecutor,
    FlashLoanStatus,
    FlashLoanStrategyType,
    AAVE_FLASH_LOAN_FEE_RATE,
)


class TestFlashLoan(unittest.TestCase):
    """Tests for the FlashLoan dataclass."""

    def setUp(self):
        """Create a flash loan for testing."""
        self.loan = FlashLoan(
            loan_id="flash_1",
            pool_id="pool_1",
            borrower="alice",
            asset="BTC",
            amount=100.0,
            fee=0.09,
            total_repay=100.09,
        )

    def test_loan_creation(self):
        """Test flash loan creation."""
        self.assertEqual(self.loan.amount, 100.0)
        self.assertEqual(self.loan.fee, 0.09)
        self.assertEqual(self.loan.total_repay, 100.09)
        self.assertEqual(self.loan.status, FlashLoanStatus.PENDING)

    def test_add_operation(self):
        """Test adding operations."""
        self.loan.add_operation("swap", {"dex": "Uniswap", "amount": 1.0})
        self.assertEqual(len(self.loan.operations), 1)
        self.assertEqual(self.loan.operations[0]["type"], "swap")

    def test_is_profitable(self):
        """Test profitability check."""
        self.loan.profit = 1.0
        self.assertTrue(self.loan.is_profitable())

    def test_is_not_profitable(self):
        """Test not profitable when profit < fee."""
        self.loan.profit = 0.01
        self.assertFalse(self.loan.is_profitable())

    def test_compute_net_profit(self):
        """Test net profit computation."""
        self.loan.profit = 1.0
        net = self.loan.compute_net_profit()
        self.assertAlmostEqual(net, 1.0 - 0.09)


class TestFlashLoanPool(unittest.TestCase):
    """Tests for the FlashLoanPool dataclass."""

    def setUp(self):
        """Create a pool for testing."""
        self.pool = FlashLoanPool(pool_id="test_pool", asset="BTC")

    def test_deposit(self):
        """Test depositing funds."""
        balance = self.pool.deposit("alice", 100.0)
        self.assertEqual(balance, 100.0)
        self.assertEqual(self.pool.total_deposited, 100.0)
        self.assertEqual(self.pool.available_balance, 100.0)

    def test_multiple_deposits(self):
        """Test multiple depositors."""
        self.pool.deposit("alice", 100.0)
        self.pool.deposit("bob", 200.0)
        self.assertEqual(self.pool.total_deposited, 300.0)
        self.assertEqual(len(self.pool.depositors), 2)

    def test_withdraw(self):
        """Test withdrawing funds."""
        self.pool.deposit("alice", 100.0)
        balance = self.pool.withdraw("alice", 30.0)
        self.assertEqual(balance, 70.0)
        self.assertEqual(self.pool.depositors["alice"], 70.0)

    def test_withdraw_insufficient(self):
        """Test withdrawal fails with insufficient balance."""
        self.pool.deposit("alice", 100.0)
        with self.assertRaises(ValueError):
            self.pool.withdraw("alice", 200.0)

    def test_can_flash_loan(self):
        """Test flash loan availability check."""
        self.pool.deposit("alice", 100.0)
        self.assertTrue(self.pool.can_flash_loan(50.0))
        self.assertFalse(self.pool.can_flash_loan(200.0))

    def test_fee_rate_default(self):
        """Test default fee rate."""
        self.assertEqual(self.pool.fee_rate, AAVE_FLASH_LOAN_FEE_RATE)


class TestFlashLoanFeeCalculator(unittest.TestCase):
    """Tests for the FlashLoanFeeCalculator class."""

    def test_base_fee(self):
        """Test base fee computation."""
        fee = FlashLoanFeeCalculator.compute_fee(1000.0)
        expected = 1000.0 * AAVE_FLASH_LOAN_FEE_RATE
        self.assertAlmostEqual(fee, expected)

    def test_fee_with_utilization(self):
        """Test fee with utilization surcharge."""
        fee = FlashLoanFeeCalculator.compute_fee(1000.0, pool_utilization=0.5)
        base = 1000.0 * AAVE_FLASH_LOAN_FEE_RATE
        self.assertGreater(fee, base)

    def test_fee_with_volatility(self):
        """Test fee with volatility surcharge."""
        fee = FlashLoanFeeCalculator.compute_fee(1000.0, volatility=0.5)
        base = 1000.0 * AAVE_FLASH_LOAN_FEE_RATE
        self.assertGreater(fee, base)

    def test_total_repay(self):
        """Test total repayment computation."""
        total = FlashLoanFeeCalculator.compute_total_repay(1000.0)
        fee = FlashLoanFeeCalculator.compute_fee(1000.0)
        self.assertAlmostEqual(total, 1000.0 + fee)


class TestGenesisFlashVault(unittest.TestCase):
    """Tests for the GenesisFlashVault dataclass."""

    def test_verify_genesis_true(self):
        """Test Genesis verification with correct hash."""
        vault = GenesisFlashVault(
            vault_id="v1",
            genesis_block_hash="000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f",
        )
        self.assertTrue(vault.verify_genesis())

    def test_verify_genesis_false(self):
        """Test Genesis verification with wrong hash."""
        vault = GenesisFlashVault(
            vault_id="v1",
            genesis_block_hash="0000000000000000000000000000000000000000000000000000000000000000",
        )
        self.assertFalse(vault.verify_genesis())

    def test_vault_secure(self):
        """Test vault is always secure."""
        vault = GenesisFlashVault(vault_id="v1", genesis_block_hash="any")
        self.assertTrue(vault.is_secure)


class TestFlashLoanExecutor(unittest.TestCase):
    """Tests for the FlashLoanExecutor class."""

    def setUp(self):
        """Create a pool and executor for testing."""
        self.pool = FlashLoanPool(pool_id="exec_pool", asset="BTC")
        self.pool.deposit("whale", 1000.0)
        self.executor = FlashLoanExecutor(self.pool)

    def test_successful_flash_loan(self):
        """Test successful flash loan execution."""
        def callback(loan):
            loan.add_operation("test", {"action": "do_something"})
            return True

        loan = self.executor.execute_flash_loan("alice", 100.0, callback)
        self.assertEqual(loan.status, FlashLoanStatus.REPAID)
        self.assertEqual(loan.amount, 100.0)
        self.assertGreater(loan.fee, 0)

    def test_failed_flash_loan(self):
        """Test failed flash loan triggers revert."""
        def callback(loan):
            return False

        with self.assertRaises(RuntimeError):
            self.executor.execute_flash_loan("alice", 100.0, callback)

    def test_insufficient_balance(self):
        """Test flash loan fails with insufficient balance."""
        def callback(loan):
            return True

        with self.assertRaises(ValueError):
            self.executor.execute_flash_loan("alice", 2000.0, callback)

    def test_arbitrage_profitable(self):
        """Test profitable arbitrage."""
        arb = self.executor.execute_arbitrage(
            borrower="trader",
            amount=100.0,
            dex_a="Uniswap",
            dex_b="SushiSwap",
            asset="BTC",
            price_a=50000.0,
            price_b=51000.0,
        )
        self.assertGreater(arb.profit, 0)

    def test_arbitrage_not_profitable(self):
        """Test unprofitable arbitrage is reverted."""
        arb = self.executor.execute_arbitrage(
            borrower="trader",
            amount=100.0,
            dex_a="Uniswap",
            dex_b="SushiSwap",
            asset="BTC",
            price_a=50000.0,
            price_b=49000.0,
        )
        self.assertEqual(arb.profit, 0.0)

    def test_liquidation(self):
        """Test liquidation execution."""
        liq = self.executor.execute_liquidation(
            liquidator="liquidator_1",
            amount=10.0,
            borrower="bob",
            collateral_asset="ETH",
            collateral_amount=20.0,
            debt_asset="USDC",
            debt_amount=10000.0,
            bonus_rate=0.05,
        )
        self.assertEqual(liq.liquidator, "liquidator_1")
        self.assertEqual(liq.collateral_amount, 20.0)
        self.assertEqual(liq.bonus, 500.0)  # 5% of 10000

    def test_executor_stats(self):
        """Test executor statistics."""
        def callback(loan):
            return True

        self.executor.execute_flash_loan("alice", 100.0, callback)
        stats = self.executor.get_executor_stats()
        self.assertEqual(stats["total_flash_loans"], 1)
        self.assertEqual(stats["repaid"], 1)

    def test_pool_fees_accumulate(self):
        """Test that pool fees accumulate from flash loans."""
        initial_fees = self.pool.total_fees_earned

        def callback(loan):
            return True

        self.executor.execute_flash_loan("alice", 100.0, callback)
        self.assertGreater(self.pool.total_fees_earned, initial_fees)


class TestFlashLoanStrategy(unittest.TestCase):
    """Tests for the FlashLoanStrategy dataclass."""

    def test_strategy_creation(self):
        """Test strategy creation."""
        strategy = FlashLoanStrategy(
            strategy_id="strat_1",
            strategy_type=FlashLoanStrategyType.ARBITRAGE,
            description="DEX arbitrage",
            expected_profit=100.0,
            risk_level=3,
        )
        self.assertEqual(strategy.strategy_type, FlashLoanStrategyType.ARBITRAGE)
        self.assertEqual(strategy.risk_level, 3)


class TestFlashLoanArbitrage(unittest.TestCase):
    """Tests for the FlashLoanArbitrage dataclass."""

    def test_arbitrage_creation(self):
        """Test arbitrage creation."""
        arb = FlashLoanArbitrage(
            arbitrage_id="arb_1",
            flash_loan_id="flash_1",
            dex_a="Uniswap",
            dex_b="SushiSwap",
            asset_in="BTC",
            asset_out="BTC",
            price_a=50000.0,
            price_b=50500.0,
            spread=500.0,
            profit=100.0,
        )
        self.assertEqual(arb.spread, 500.0)
        self.assertEqual(arb.profit, 100.0)


class TestFlashLoanLiquidation(unittest.TestCase):
    """Tests for the FlashLoanLiquidation dataclass."""

    def test_liquidation_creation(self):
        """Test liquidation creation."""
        liq = FlashLoanLiquidation(
            liquidation_id="liq_1",
            flash_loan_id="flash_1",
            liquidator="liquidator_1",
            borrower="bob",
            collateral_asset="ETH",
            collateral_amount=20.0,
            debt_asset="USDC",
            debt_amount=10000.0,
            bonus=500.0,
        )
        self.assertEqual(liq.collateral_amount, 20.0)
        self.assertEqual(liq.bonus, 500.0)


if __name__ == "__main__":
    unittest.main()
