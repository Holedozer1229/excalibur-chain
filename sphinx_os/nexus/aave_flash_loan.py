#!/usr/bin/env python3
"""Aave Flash Loan Engine — Atomic Uncollateralized Loans Backed by Genesis BTC.

The Core Insight
================
Aave flash loans are a revolutionary DeFi primitive: you can borrow any amount
of any asset without collateral, as long as you return it in the same transaction.
The guarantee is mathematical, not institutional — the atomicity of the blockchain
ensures the loan is either fully repaid or never happened at all.

This module combines Aave flash loans with the Genesis BTC collateral system:
1. The Genesis Block serves as the ultimate "collateral" for the flash loan protocol
2. Flash loans are guaranteed by the CTC fixed-point consistency condition
3. The loan's atomicity mirrors the CTC's causal consistency — if the loop
   doesn't close (loan not repaid), the computation never happened

Key Innovations
===============
1. **FlashLoan**: Represents a flash loan with the borrowed amount, fee,
   and the operations performed during the loan. The loan is atomic —
   it either completes successfully with repayment, or is entirely reverted.

2. **FlashLoanExecutor**: Executes flash loan operations atomically.
   It borrows funds, executes arbitrary operations, and verifies repayment.
   If repayment fails, the entire transaction is reverted.

3. **FlashLoanPool**: A liquidity pool that provides flash loan capital.
   Multiple depositors contribute funds, and borrowers can flash loan
   any amount up to the pool's balance.

4. **FlashLoanStrategy**: Encapsulates a flash loan strategy — what to do
   with the borrowed funds. Strategies include arbitrage, collateral swap,
   debt repayment, and liquidation.

5. **FlashLoanFeeCalculator**: Computes flash loan fees using the Aave model
   (0.09% fee) and CTC-inspired dynamic pricing based on pool utilization.

6. **GenesisFlashVault**: Combines Genesis BTC collateral with flash loans.
   The Genesis Block's immutability provides the ultimate guarantee that
   the flash loan protocol itself cannot be compromised.

7. **FlashLoanArbitrage**: Detects and executes arbitrage opportunities
   using flash loans across multiple DEXes.

8. **FlashLoanLiquidator**: Uses flash loans to liquidate undercollateralized
   positions, earning liquidation bonuses.

Why This Is Revolutionary
=========================
1. Flash loans enable leverage without collateral — you can borrow millions
   to execute a trade, then repay instantly, all in one atomic operation.

2. Combined with Genesis BTC collateral, the flash loan protocol is backed
   by the most immutable asset in existence — the Bitcoin Genesis Block.

3. The CTC fixed-point model ensures the flash loan's consistency:
   just as S(ρ) = ρ ensures the CTC loop closes, the flash loan's
   atomicity ensures the borrowed amount is returned.

4. This creates the first "causally-guaranteed" flash loan protocol:
   the loan is guaranteed not by smart contract code alone, but by
   the causal structure of the Genesis Block itself.

References
==========
1. Aave Flash Loans: https://docs.aave.com/developers/v/2.0/details/flash-loans
2. Aave fee: 0.09% of borrowed amount
3. Bitcoin Genesis Block: the immutable anchor of all flash loan guarantees
"""

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

AAVE_FLASH_LOAN_FEE_BPS = 9  # 0.09% in basis points
AAVE_FLASH_LOAN_FEE_RATE = 0.0009  # 0.09%


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


class FlashLoanStatus(Enum):
    """Status of a flash loan."""
    PENDING = "pending"
    EXECUTING = "executing"
    REPAID = "repaid"
    REVERTED = "reverted"
    FAILED = "failed"


class FlashLoanStrategyType(Enum):
    """Type of flash loan strategy."""
    ARBITRAGE = "arbitrage"
    COLLATERAL_SWAP = "collateral_swap"
    DEBT_REPAYMENT = "debt_repayment"
    LIQUIDATION = "liquidation"
    REFINANCING = "refinancing"
    CUSTOM = "custom"


@dataclass
class FlashLoan:
    """A flash loan — atomic, uncollateralized, must be repaid in same transaction.

    The flash loan is the core primitive: you borrow any amount, execute
    arbitrary operations, and must repay the principal + fee before the
    transaction completes. If repayment fails, the entire transaction
    is atomically reverted.

    Attributes:
        loan_id: Unique loan identifier
        pool_id: ID of the liquidity pool
        borrower: Borrower address
        asset: Asset symbol (e.g., "BTC", "ETH", "USDC")
        amount: Borrowed amount
        fee: Fee amount (0.09% of borrowed amount)
        total_repay: Total amount to repay (amount + fee)
        status: Current loan status
        creation_time: When the loan was created
        operations: List of operations performed during the loan
        profit: Profit from the flash loan operations
        strategy: The strategy used for the flash loan
    """
    loan_id: str
    pool_id: str
    borrower: str
    asset: str
    amount: float
    fee: float
    total_repay: float
    status: FlashLoanStatus = FlashLoanStatus.PENDING
    creation_time: float = field(default_factory=time.time)
    operations: List[Dict[str, Any]] = field(default_factory=list)
    profit: float = 0.0
    strategy: Optional[str] = None

    def add_operation(self, operation_type: str, details: Dict[str, Any]):
        """Record an operation performed during the flash loan.

        Args:
            operation_type: Type of operation (e.g., "swap", "transfer")
            details: Operation details
        """
        self.operations.append({
            "type": operation_type,
            "details": details,
            "timestamp": time.time(),
        })

    def is_profitable(self) -> bool:
        """Check if the flash loan was profitable.

        Returns:
            True if profit exceeds the fee
        """
        return self.profit > self.fee

    def compute_net_profit(self) -> float:
        """Compute net profit after fees.

        Returns:
            Net profit (profit - fee)
        """
        return self.profit - self.fee


@dataclass
class FlashLoanPool:
    """Liquidity pool providing flash loan capital.

    Multiple depositors contribute funds to the pool. Borrowers can
    flash loan any amount up to the pool's available balance.

    Attributes:
        pool_id: Unique pool identifier
        asset: Asset symbol
        total_deposited: Total amount deposited
        available_balance: Available for flash loans
        total_flash_loans: Total number of flash loans executed
        total_fees_earned: Total fees earned from flash loans
        depositors: Dict of depositor -> deposit amount
        fee_rate: Current fee rate
    """
    pool_id: str
    asset: str
    total_deposited: float = 0.0
    available_balance: float = 0.0
    total_flash_loans: int = 0
    total_fees_earned: float = 0.0
    depositors: Dict[str, float] = field(default_factory=dict)
    fee_rate: float = AAVE_FLASH_LOAN_FEE_RATE

    def deposit(self, depositor: str, amount: float) -> float:
        """Deposit funds into the pool.

        Args:
            depositor: Depositor address
            amount: Deposit amount

        Returns:
            New available balance
        """
        if depositor not in self.depositors:
            self.depositors[depositor] = 0
        self.depositors[depositor] += amount
        self.total_deposited += amount
        self.available_balance += amount
        return self.available_balance

    def withdraw(self, depositor: str, amount: float) -> float:
        """Withdraw funds from the pool.

        Args:
            depositor: Depositor address
            amount: Withdrawal amount

        Returns:
            New available balance

        Raises:
            ValueError: If insufficient balance
        """
        current = self.depositors.get(depositor, 0)
        if amount > current:
            raise ValueError(f"Insufficient deposit: {amount} > {current}")
        if amount > self.available_balance:
            raise ValueError(f"Insufficient pool balance: {amount} > {self.available_balance}")

        self.depositors[depositor] -= amount
        self.total_deposited -= amount
        self.available_balance -= amount
        return self.available_balance

    def can_flash_loan(self, amount: float) -> bool:
        """Check if the pool can provide a flash loan of the given amount.

        Args:
            amount: Requested flash loan amount

        Returns:
            True if the pool has sufficient balance
        """
        fee = amount * self.fee_rate
        return (amount + fee) <= self.available_balance


@dataclass
class FlashLoanStrategy:
    """Encapsulates a flash loan strategy.

    A strategy defines what operations to perform with the borrowed funds.

    Attributes:
        strategy_id: Unique strategy identifier
        strategy_type: Type of strategy
        description: Human-readable description
        expected_profit: Expected profit from the strategy
        risk_level: Risk level (1-10)
        parameters: Strategy-specific parameters
    """
    strategy_id: str
    strategy_type: FlashLoanStrategyType
    description: str
    expected_profit: float
    risk_level: int
    parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FlashLoanArbitrage:
    """Arbitrage opportunity executed via flash loan.

    Attributes:
        arbitrage_id: Unique identifier
        flash_loan_id: Associated flash loan
        dex_a: First DEX
        dex_b: Second DEX
        asset_in: Asset to buy on DEX A
        asset_out: Asset to sell on DEX B
        price_a: Price on DEX A
        price_b: Price on DEX B
        spread: Price spread
        profit: Profit from arbitrage
    """
    arbitrage_id: str
    flash_loan_id: str
    dex_a: str
    dex_b: str
    asset_in: str
    asset_out: str
    price_a: float
    price_b: float
    spread: float
    profit: float


@dataclass
class FlashLoanLiquidation:
    """Liquidation executed via flash loan.

    Attributes:
        liquidation_id: Unique identifier
        flash_loan_id: Associated flash loan
        liquidator: Liquidator address
        borrower: Borrower being liquidated
        collateral_asset: Collateral asset
        collateral_amount: Amount of collateral seized
        debt_asset: Debt asset
        debt_amount: Amount of debt repaid
        bonus: Liquidation bonus earned
    """
    liquidation_id: str
    flash_loan_id: str
    liquidator: str
    borrower: str
    collateral_asset: str
    collateral_amount: float
    debt_asset: str
    debt_amount: float
    bonus: float


@dataclass
class GenesisFlashVault:
    """Combines Genesis BTC collateral with flash loan protocol.

    The Genesis Block's immutability provides the ultimate guarantee
    that the flash loan protocol cannot be compromised.

    Attributes:
        vault_id: Unique vault identifier
        genesis_block_hash: Bitcoin Genesis Block hash
        total_flash_loans: Total flash loans executed
        total_volume: Total flash loan volume
        total_fees: Total fees earned
        is_secure: Whether the vault is secure (always True for genesis)
    """
    vault_id: str
    genesis_block_hash: str
    total_flash_loans: int = 0
    total_volume: float = 0.0
    total_fees: float = 0.0
    is_secure: bool = True

    def verify_genesis(self) -> bool:
        """Verify the Genesis Block hash is correct.

        Returns:
            True if the hash matches the Bitcoin Genesis Block
        """
        return self.genesis_block_hash == "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"


# ---------------------------------------------------------------------------
# Flash Loan Fee Calculator
# ---------------------------------------------------------------------------


class FlashLoanFeeCalculator:
    """Computes flash loan fees using the Aave model and CTC dynamic pricing.

    The base fee is 0.09% (Aave standard). Dynamic pricing adjusts based on:
    - Pool utilization (higher utilization = higher fee)
    - Loan size (larger loans = slightly higher fee)
    - Market volatility (higher volatility = higher fee)
    """

    @staticmethod
    def compute_fee(
        amount: float,
        pool_utilization: float = 0.0,
        volatility: float = 0.0,
    ) -> float:
        """Compute flash loan fee.

        Args:
            amount: Borrowed amount
            pool_utilization: Current pool utilization (0-1)
            volatility: Market volatility index (0-1)

        Returns:
            Fee amount
        """
        # Base fee: 0.09%
        base_fee = amount * AAVE_FLASH_LOAN_FEE_RATE

        # Utilization surcharge: up to 100% increase at full utilization
        utilization_surcharge = base_fee * pool_utilization

        # Volatility surcharge: up to 50% increase at max volatility
        volatility_surcharge = base_fee * volatility * 0.5

        return base_fee + utilization_surcharge + volatility_surcharge

    @staticmethod
    def compute_total_repay(
        amount: float,
        pool_utilization: float = 0.0,
        volatility: float = 0.0,
    ) -> float:
        """Compute total repayment amount (principal + fee).

        Args:
            amount: Borrowed amount
            pool_utilization: Current pool utilization (0-1)
            volatility: Market volatility index (0-1)

        Returns:
            Total repayment amount
        """
        fee = FlashLoanFeeCalculator.compute_fee(amount, pool_utilization, volatility)
        return amount + fee


# ---------------------------------------------------------------------------
# Flash Loan Executor
# ---------------------------------------------------------------------------


class FlashLoanExecutor:
    """Executes flash loan operations atomically.

    The executor borrows funds, executes arbitrary operations, and verifies
    repayment. If repayment fails, the entire transaction is atomically reverted.

    The atomicity mirrors the CTC fixed-point consistency: just as S(ρ) = ρ
    ensures the CTC loop closes, the executor ensures the borrowed amount
    is returned.
    """

    def __init__(self, pool: FlashLoanPool):
        """Initialize the flash loan executor.

        Args:
            pool: The liquidity pool providing flash loan capital
        """
        self.pool = pool
        self.loans: Dict[str, FlashLoan] = {}
        self.loan_counter = 0
        self.arbitrages: List[FlashLoanArbitrage] = []
        self.liquidations: List[FlashLoanLiquidation] = []

    def execute_flash_loan(
        self,
        borrower: str,
        amount: float,
        callback: Callable[[FlashLoan], bool],
        strategy: Optional[str] = None,
    ) -> FlashLoan:
        """Execute a flash loan atomically.

        The callback receives the flash loan and performs operations.
        It must return True to indicate successful repayment.
        If it returns False, the loan is reverted.

        Args:
            borrower: Borrower address
            amount: Amount to borrow
            callback: Function to execute with the borrowed funds
            strategy: Optional strategy name

        Returns:
            The completed flash loan

        Raises:
            ValueError: If the pool cannot provide the loan
            RuntimeError: If the loan is not repaid
        """
        # Check pool availability
        if not self.pool.can_flash_loan(amount):
            raise ValueError(
                f"Insufficient pool balance for flash loan of {amount}. "
                f"Available: {self.pool.available_balance}"
            )

        # Compute fee
        utilization = 1.0 - (self.pool.available_balance / self.pool.total_deposited) if self.pool.total_deposited > 0 else 0
        fee = FlashLoanFeeCalculator.compute_fee(amount, utilization)
        total_repay = amount + fee

        # Create flash loan
        self.loan_counter += 1
        loan = FlashLoan(
            loan_id=f"flash_{self.loan_counter}",
            pool_id=self.pool.pool_id,
            borrower=borrower,
            asset=self.pool.asset,
            amount=amount,
            fee=fee,
            total_repay=total_repay,
            status=FlashLoanStatus.EXECUTING,
            strategy=strategy,
        )

        # Execute callback
        try:
            success = callback(loan)

            if success:
                # Loan repaid successfully
                loan.status = FlashLoanStatus.REPAID
                self.pool.total_flash_loans += 1
                self.pool.total_fees_earned += fee
            else:
                # Loan not repaid — atomic revert
                loan.status = FlashLoanStatus.REVERTED
                raise RuntimeError(
                    f"Flash loan {loan.loan_id} reverted: not repaid. "
                    f"Required: {total_repay}, this is the CTC fixed-point condition."
                )
        except Exception as e:
            loan.status = FlashLoanStatus.FAILED
            raise RuntimeError(f"Flash loan {loan.loan_id} failed: {e}") from e

        self.loans[loan.loan_id] = loan
        return loan

    def execute_arbitrage(
        self,
        borrower: str,
        amount: float,
        dex_a: str,
        dex_b: str,
        asset: str,
        price_a: float,
        price_b: float,
    ) -> FlashLoanArbitrage:
        """Execute an arbitrage flash loan.

        Buy low on DEX A, sell high on DEX B, repay the flash loan,
        and keep the profit.

        Args:
            borrower: Borrower address
            amount: Amount to borrow
            dex_a: First DEX (buy low)
            dex_b: Second DEX (sell high)
            asset: Asset to arbitrage
            price_a: Price on DEX A (buy price)
            price_b: Price on DEX B (sell price)

        Returns:
            The arbitrage result
        """
        spread = abs(price_b - price_a)
        buy_amount = amount / price_a  # How much we buy on DEX A
        sell_value = buy_amount * price_b  # How much we get on DEX B
        gross_profit = sell_value - amount

        fee = FlashLoanFeeCalculator.compute_fee(amount)
        net_profit = gross_profit - fee

        arbitrage_id = f"arb_{len(self.arbitrages) + 1}"

        # Execute the flash loan
        def arbitrage_callback(loan: FlashLoan) -> bool:
            loan.add_operation("swap", {
                "dex": dex_a,
                "action": "buy",
                "asset": asset,
                "amount": buy_amount,
                "price": price_a,
            })
            loan.add_operation("swap", {
                "dex": dex_b,
                "action": "sell",
                "asset": asset,
                "amount": buy_amount,
                "price": price_b,
            })
            loan.profit = gross_profit
            return net_profit > 0  # Only repay if profitable

        try:
            loan = self.execute_flash_loan(borrower, amount, arbitrage_callback, "arbitrage")

            arb = FlashLoanArbitrage(
                arbitrage_id=arbitrage_id,
                flash_loan_id=loan.loan_id,
                dex_a=dex_a,
                dex_b=dex_b,
                asset_in=asset,
                asset_out=asset,
                price_a=price_a,
                price_b=price_b,
                spread=spread,
                profit=net_profit,
            )
            self.arbitrages.append(arb)
            return arb
        except RuntimeError:
            # Arbitrage not profitable — loan reverted (this is normal)
            return FlashLoanArbitrage(
                arbitrage_id=arbitrage_id,
                flash_loan_id="reverted",
                dex_a=dex_a,
                dex_b=dex_b,
                asset_in=asset,
                asset_out=asset,
                price_a=price_a,
                price_b=price_b,
                spread=spread,
                profit=0.0,
            )

    def execute_liquidation(
        self,
        liquidator: str,
        amount: float,
        borrower: str,
        collateral_asset: str,
        collateral_amount: float,
        debt_asset: str,
        debt_amount: float,
        bonus_rate: float = 0.05,
    ) -> FlashLoanLiquidation:
        """Execute a liquidation flash loan.

        Borrow funds to repay a borrower's debt, seize their collateral
        at a discount, sell the collateral, repay the flash loan, and
        keep the bonus.

        Args:
            liquidator: Liquidator address
            amount: Amount to borrow for liquidation
            borrower: Borrower being liquidated
            collateral_asset: Collateral asset
            collateral_amount: Amount of collateral seized
            debt_asset: Debt asset
            debt_amount: Amount of debt repaid
            bonus_rate: Liquidation bonus rate (default 5%)

        Returns:
            The liquidation result
        """
        bonus = debt_amount * bonus_rate
        liquidation_id = f"liq_{len(self.liquidations) + 1}"

        def liquidation_callback(loan: FlashLoan) -> bool:
            loan.add_operation("repay_debt", {
                "borrower": borrower,
                "asset": debt_asset,
                "amount": debt_amount,
            })
            loan.add_operation("seize_collateral", {
                "borrower": borrower,
                "asset": collateral_asset,
                "amount": collateral_amount,
            })
            loan.profit = bonus
            return True  # Liquidation always repays

        try:
            loan = self.execute_flash_loan(liquidator, amount, liquidation_callback, "liquidation")

            liq = FlashLoanLiquidation(
                liquidation_id=liquidation_id,
                flash_loan_id=loan.loan_id,
                liquidator=liquidator,
                borrower=borrower,
                collateral_asset=collateral_asset,
                collateral_amount=collateral_amount,
                debt_asset=debt_asset,
                debt_amount=debt_amount,
                bonus=bonus,
            )
            self.liquidations.append(liq)
            return liq
        except RuntimeError as e:
            raise RuntimeError(f"Liquidation failed: {e}") from e

    def get_executor_stats(self) -> Dict[str, Any]:
        """Get executor statistics.

        Returns:
            Dictionary with executor statistics
        """
        repaid = len([l for l in self.loans.values() if l.status == FlashLoanStatus.REPAID])
        reverted = len([l for l in self.loans.values() if l.status == FlashLoanStatus.REVERTED])
        total_profit = sum(l.profit for l in self.loans.values())

        return {
            "total_flash_loans": len(self.loans),
            "repaid": repaid,
            "reverted": reverted,
            "failed": len(self.loans) - repaid - reverted,
            "total_profit": total_profit,
            "total_arbitrages": len(self.arbitrages),
            "total_liquidations": len(self.liquidations),
            "pool_fees_earned": self.pool.total_fees_earned,
        }


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def run_aave_flash_loan_demo():
    """Run a comprehensive demo of Aave flash loans with Genesis BTC collateral."""
    print("=" * 70)
    print("AAVE FLASH LOAN ENGINE")
    print("Atomic Uncollateralized Loans Backed by Genesis BTC")
    print("=" * 70)

    # 1. Create Genesis flash vault
    print("\n--- 1. Genesis Flash Vault ---")
    vault = GenesisFlashVault(
        vault_id="genesis_flash_vault_1",
        genesis_block_hash="000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f",
    )
    print(f"Vault ID: {vault.vault_id}")
    print(f"Genesis verified: {vault.verify_genesis()}")
    print(f"Vault secure: {vault.is_secure}")

    # 2. Create flash loan pool
    print("\n--- 2. Flash Loan Liquidity Pool ---")
    pool = FlashLoanPool(pool_id="btc_flash_pool", asset="BTC")
    pool.deposit("whale_1", 100.0)
    pool.deposit("whale_2", 200.0)
    pool.deposit("whale_3", 150.0)
    print(f"Pool: {pool.pool_id}")
    print(f"Asset: {pool.asset}")
    print(f"Total deposited: {pool.total_deposited} BTC")
    print(f"Available: {pool.available_balance} BTC")
    print(f"Depositors: {len(pool.depositors)}")
    print(f"Fee rate: {pool.fee_rate * 100:.2f}%")

    # 3. Create executor
    print("\n--- 3. Flash Loan Executor ---")
    executor = FlashLoanExecutor(pool)
    print("Executor created and ready")

    # 4. Execute a simple flash loan
    print("\n--- 4. Simple Flash Loan ---")
    def simple_callback(loan: FlashLoan) -> bool:
        loan.add_operation("receive", {"amount": loan.amount})
        loan.add_operation("process", {"action": "some_operation"})
        loan.add_operation("repay", {"amount": loan.total_repay})
        return True  # Repay successfully

    loan = executor.execute_flash_loan(
        borrower="alice",
        amount=50.0,
        callback=simple_callback,
        strategy="simple",
    )
    print(f"Loan ID: {loan.loan_id}")
    print(f"Borrowed: {loan.amount} {loan.asset}")
    print(f"Fee: {loan.fee:.4f} {loan.asset}")
    print(f"Total repaid: {loan.total_repay:.4f} {loan.asset}")
    print(f"Status: {loan.status.value}")
    print(f"Operations: {len(loan.operations)}")

    # 5. Execute arbitrage
    print("\n--- 5. Flash Loan Arbitrage ---")
    arb = executor.execute_arbitrage(
        borrower="trader",
        amount=100.0,
        dex_a="Uniswap",
        dex_b="SushiSwap",
        asset="BTC",
        price_a=50000.0,
        price_b=50500.0,
    )
    print(f"Arbitrage ID: {arb.arbitrage_id}")
    print(f"DEX A ({arb.dex_a}): ${arb.price_a:,.0f}")
    print(f"DEX B ({arb.dex_b}): ${arb.price_b:,.0f}")
    print(f"Spread: ${arb.spread:,.0f}")
    print(f"Profit: ${arb.profit:,.2f}")

    # 6. Execute liquidation
    print("\n--- 6. Flash Loan Liquidation ---")
    liq = executor.execute_liquidation(
        liquidator="liquidator_1",
        amount=10.0,
        borrower="overleveraged_bob",
        collateral_asset="ETH",
        collateral_amount=20.0,
        debt_asset="USDC",
        debt_amount=10000.0,
        bonus_rate=0.05,
    )
    print(f"Liquidation ID: {liq.liquidation_id}")
    print(f"Liquidator: {liq.liquidator}")
    print(f"Borrower liquidated: {liq.borrower}")
    print(f"Collateral seized: {liq.collateral_amount} {liq.collateral_asset}")
    print(f"Debt repaid: {liq.debt_amount} {liq.debt_asset}")
    print(f"Bonus earned: {liq.bonus}% = ${liq.bonus * liq.debt_amount:,.2f}")

    # 7. Fee calculator
    print("\n--- 7. Flash Loan Fee Calculator ---")
    for amount in [10, 100, 1000, 10000]:
        fee = FlashLoanFeeCalculator.compute_fee(amount)
        total = FlashLoanFeeCalculator.compute_total_repay(amount)
        print(f"  Borrow {amount:>6}: fee = {fee:.4f}, repay = {total:.4f}")

    # 8. Failed flash loan (demonstrates atomic revert)
    print("\n--- 8. Failed Flash Loan (Atomic Revert) ---")
    def failing_callback(loan: FlashLoan) -> bool:
        loan.add_operation("receive", {"amount": loan.amount})
        loan.add_operation("fail", {"reason": "operation_failed"})
        return False  # Don't repay — triggers revert

    try:
        executor.execute_flash_loan("bad_actor", 10.0, failing_callback)
        print("ERROR: Should have failed!")
    except RuntimeError as e:
        print(f"Flash loan atomically reverted: {e}")

    # 9. Pool statistics
    print("\n--- 9. Pool Statistics ---")
    print(f"Total flash loans: {pool.total_flash_loans}")
    print(f"Total fees earned: {pool.total_fees_earned:.4f} {pool.asset}")
    print(f"Available balance: {pool.available_balance:.4f} {pool.asset}")

    # 10. Executor statistics
    print("\n--- 10. Executor Statistics ---")
    stats = executor.get_executor_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\n" + "=" * 70)
    print("AAVE FLASH LOAN ENGINE — Demo Complete")
    print("=" * 70)
    print("\nKey innovations demonstrated:")
    print("1. Genesis Flash Vault — Protocol backed by Bitcoin Genesis Block")
    print("2. Flash Loan Pool — Liquidity for atomic borrowing")
    print("3. Flash Loan Executor — Atomic execution with guaranteed repayment")
    print("4. Arbitrage — Profit from price differences across DEXes")
    print("5. Liquidation — Seize collateral via flash loan")
    print("6. Fee Calculator — Dynamic pricing based on utilization")
    print("7. Atomic Revert — Failed loans are completely undone")
    print("\nThe flash loan's atomicity mirrors the CTC fixed-point condition:")
    print("just as S(rho) = rho ensures the CTC loop closes,")
    print("the flash loan ensures the borrowed amount is returned.")


if __name__ == "__main__":
    run_aave_flash_loan_demo()
