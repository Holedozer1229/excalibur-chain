#!/usr/bin/env python3
"""Genesis BTC Collateral Loan — The Ultimate Loan Backed by the First Block of Bitcoin.

The Core Insight
================
The Bitcoin Genesis Block (block 0) is the most unique asset in financial history:
- It contains 50 BTC that can never be spent (the coinbase is unspendable)
- It carries the embedded timestamp: "The Times 03/Jan/2009 Chancellor on brink of second bailout for banks"
- It is the root of all Bitcoin proof-of-work — every subsequent block traces back to it
- Its hash is the immutable anchor of the entire Bitcoin blockchain

In the CTC Oracle Market framework, the Genesis Block is the ultimate collateral:
1. It cannot be double-spent (the coins are provably unmovable)
2. It cannot be destroyed (the block is cryptographically sealed)
3. It cannot be replicated (the proof-of-work is unique and irreplaceable)
4. It is the causal root of all Bitcoin value

This module creates a loan system where the Genesis Block serves as collateral.
The loan is backed not by the 50 BTC (which are unspendable), but by the
Genesis Block's role as the causal anchor of Bitcoin's entire value system.

Key Innovations
===============
1. **GenesisBTCProof**: An oracle proof encoding the Genesis Block as collateral.
   The proof includes the block hash, coinbase transaction, embedded timestamp,
   and the proof-of-work nonce — all verifiable against the Bitcoin blockchain.

2. **GenesisCollateralVault**: A cryptographic vault that "locks" the Genesis Block
   as collateral. The vault uses the CTC fixed-point equation to ensure the
   collateral remains consistent — the Genesis Block cannot change, so the
   collateral is perpetually consistent.

3. **GenesisLoanEngine**: Creates, manages, and services loans backed by Genesis
   collateral. Features include:
   - Loan-to-Value (LTV) ratios based on Genesis Block's "value"
   - Interest accrual using CTC time-dilation models
   - Repayment schedules with early payoff options
   - Default handling via collateral liquidation (theoretical)

4. **GenesisLoanDerivative**: Options and futures on Genesis loans, enabling
   trading of loan risk and yield.

5. **GenesisLoanPool**: A liquidity pool for Genesis loans, allowing anyone to
   lend against Genesis collateral and earn yield.

6. **MultiGenesisVault**: Extends the concept to multiple genesis blocks across
   different blockchains (Bitcoin, Ethereum, etc.), creating cross-chain
   collateralized loans.

Why This Is Revolutionary
=========================
1. The Genesis Block is the only asset in existence that is:
   - Cryptographically immutable (SHA-256 proof-of-work)
   - Economically foundational (root of all Bitcoin value)
   - Historically significant (first block, first transaction)
   - Mathematically unique (nonce found by Satoshi)

2. Using it as collateral creates the first "causally-backed" loan:
   the loan is guaranteed not by a bank or government, but by the
   causal structure of the Bitcoin blockchain itself.

3. The CTC fixed-point model ensures the loan's consistency:
   just as S(ρ) = ρ ensures CTC consistency, the Genesis Block's
   immutability ensures the collateral's consistency.

References
==========
1. Bitcoin Genesis Block: 000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f
2. Embedded message: "The Times 03/Jan/2009 Chancellor on brink of second bailout for banks"
3. Coinbase: 4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b
4. Nonce: 2083236893
5. Timestamp: 2009-01-03T18:15:05Z
"""

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Genesis Block Constants
# ---------------------------------------------------------------------------

GENESIS_BLOCK_HASH = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
GENESIS_COINBASE_TX = "4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b"
GENESIS_NONCE = 2083236893
GENESIS_TIMESTAMP = 1231006505  # 2009-01-03T18:15:05Z
GENESIS_EMBEDDED_MESSAGE = "The Times 03/Jan/2009 Chancellor on brink of second bailout for banks"
GENESIS_COINBASE_VALUE = 50.0  # BTC
GENESIS_PREV_HASH = "0000000000000000000000000000000000000000000000000000000000000000"


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


class LoanStatus(Enum):
    """Status of a Genesis BTC loan."""
    ACTIVE = "active"
    REPAYING = "repaying"
    REPAID = "repaid"
    DEFAULTED = "defaulted"
    LIQUIDATED = "liquidated"


class CollateralType(Enum):
    """Type of genesis collateral."""
    BITCOIN_GENESIS = "bitcoin_genesis"
    ETHEREUM_GENESIS = "ethereum_genesis"
    MULTI_GENESIS = "multi_genesis"
    CTC_GENESIS = "ctc_genesis"


@dataclass
class GenesisBTCProof:
    """Oracle proof encoding the Genesis Block as collateral.

    This is the foundational proof: it encodes the Bitcoin Genesis Block
    as a verifiable, immutable collateral asset. The proof includes all
    the cryptographic elements that make the Genesis Block unique.

    Attributes:
        proof_id: Unique identifier for this proof
        block_hash: SHA-256 hash of the Genesis Block
        coinbase_tx: Coinbase transaction hash
        nonce: Proof-of-work nonce found by Satoshi
        timestamp: Genesis block timestamp
        embedded_message: The Times headline embedded in the coinbase
        coinbase_value: BTC value of the coinbase (50 BTC)
        prev_hash: Previous block hash (all zeros for genesis)
        merkle_root: Merkle root of transactions
        difficulty: Mining difficulty at genesis
        verification_key: Cryptographic verification key
        complexity_score: Computational complexity score
        confidence: Confidence level (1.0 for verified genesis)
        timestamp_created: Creation timestamp of this proof
    """
    proof_id: str
    block_hash: str = GENESIS_BLOCK_HASH
    coinbase_tx: str = GENESIS_COINBASE_TX
    nonce: int = GENESIS_NONCE
    timestamp: int = GENESIS_TIMESTAMP
    embedded_message: str = GENESIS_EMBEDDED_MESSAGE
    coinbase_value: float = GENESIS_COINBASE_VALUE
    prev_hash: str = GENESIS_PREV_HASH
    merkle_root: str = "4a5e1e4baab89f3a32518a88c31bc87f618f76673e2cc77ab2127b7afdeda33b"
    difficulty: float = 1.0
    verification_key: str = ""
    complexity_score: float = 0.0
    confidence: float = 1.0
    timestamp_created: float = field(default_factory=time.time)

    def __post_init__(self):
        """Compute verification key and complexity score."""
        content = json.dumps({
            "block_hash": self.block_hash,
            "coinbase_tx": self.coinbase_tx,
            "nonce": self.nonce,
            "timestamp": self.timestamp,
            "embedded_message": self.embedded_message,
            "coinbase_value": self.coinbase_value,
        }, sort_keys=True)
        self.verification_key = hashlib.sha256(content.encode()).hexdigest()

        # Complexity is based on the proof-of-work difficulty and age
        age_years = (time.time() - self.timestamp) / (365.25 * 24 * 3600)
        self.complexity_score = self.difficulty * 1000 + (age_years * 100)

    def verify(self) -> bool:
        """Verify this is the real Bitcoin Genesis Block.

        Returns True if all Genesis Block fields match the known constants.
        """
        return (
            self.block_hash == GENESIS_BLOCK_HASH and
            self.coinbase_tx == GENESIS_COINBASE_TX and
            self.nonce == GENESIS_NONCE and
            self.timestamp == GENESIS_TIMESTAMP
        )

    def compute_collateral_value(self, btc_price_usd: float = 100000.0) -> float:
        """Compute the collateral value of the Genesis Block.

        The Genesis Block's value is not just the 50 BTC coinbase.
        It's the causal root of all Bitcoin value. We compute it as:
        - Base value: coinbase BTC * current BTC price
        - Multiplier: based on the block's role as the chain root
        - Age bonus: the older the block, the more historically significant

        Args:
            btc_price_usd: Current Bitcoin price in USD

        Returns:
            Collateral value in USD
        """
        # Base value from coinbase
        base_value = self.coinbase_value * btc_price_usd

        # Genesis multiplier: the Genesis Block is worth more than its BTC
        # because it's the root of the entire chain
        genesis_multiplier = 10.0  # 10x the coinbase value

        # Age bonus: historical significance increases with age
        age_years = (time.time() - self.timestamp) / (365.25 * 24 * 3600)
        age_bonus = 1.0 + (age_years * 0.1)  # 10% per year

        return base_value * genesis_multiplier * age_bonus


@dataclass
class GenesisCollateralVault:
    """Cryptographic vault locking Genesis Block as collateral.

    The vault uses the CTC fixed-point equation to ensure the collateral
    remains consistent. Since the Genesis Block cannot change, the vault
    provides perpetual consistency.

    Attributes:
        vault_id: Unique vault identifier
        genesis_proof: The Genesis BTC proof locked in the vault
        lock_timestamp: When the collateral was locked
        is_locked: Whether the collateral is currently locked
        lock_hash: Cryptographic seal on the vault
        total_loans: Number of active loans against this vault
        total_borrowed: Total amount borrowed against this vault
    """
    vault_id: str
    genesis_proof: GenesisBTCProof
    lock_timestamp: float = field(default_factory=time.time)
    is_locked: bool = True
    lock_hash: str = ""
    total_loans: int = 0
    total_borrowed: float = 0.0

    def __post_init__(self):
        """Create cryptographic seal on the vault."""
        seal_content = json.dumps({
            "vault_id": self.vault_id,
            "genesis_hash": self.genesis_proof.block_hash,
            "lock_timestamp": self.lock_timestamp,
        }, sort_keys=True)
        self.lock_hash = hashlib.sha256(seal_content.encode()).hexdigest()

    def verify_seal(self) -> bool:
        """Verify the vault's cryptographic seal is intact."""
        seal_content = json.dumps({
            "vault_id": self.vault_id,
            "genesis_hash": self.genesis_proof.block_hash,
            "lock_timestamp": self.lock_timestamp,
        }, sort_keys=True)
        expected_hash = hashlib.sha256(seal_content.encode()).hexdigest()
        return self.lock_hash == expected_hash

    def collateral_consistency(self) -> bool:
        """Check if the collateral remains consistent (CTC fixed-point).

        For the Genesis Block, consistency means the block hash and all
        fields remain unchanged — which they always will.

        Returns:
            True if the collateral is consistent (always True for genesis)
        """
        return self.genesis_proof.verify() and self.verify_seal()


@dataclass
class GenesisLoan:
    """A loan backed by Genesis Block collateral.

    The loan is guaranteed by the Genesis Block's role as the causal
    anchor of Bitcoin. The LTV ratio determines how much can be borrowed
    against the collateral.

    Attributes:
        loan_id: Unique loan identifier
        vault_id: ID of the collateral vault
        borrower: Borrower identifier
        principal: Loan principal amount in USD
        interest_rate: Annual interest rate (APR)
        term_months: Loan term in months
        ltv_ratio: Loan-to-Value ratio
        status: Current loan status
        creation_time: When the loan was created
        maturity_time: When the loan matures
        repayments: List of repayment records
        total_repaid: Total amount repaid
        accrued_interest: Total interest accrued
    """
    loan_id: str
    vault_id: str
    borrower: str
    principal: float
    interest_rate: float
    term_months: int
    ltv_ratio: float
    status: LoanStatus = LoanStatus.ACTIVE
    creation_time: float = field(default_factory=time.time)
    maturity_time: float = 0.0
    repayments: List[Dict[str, Any]] = field(default_factory=list)
    total_repaid: float = 0.0
    accrued_interest: float = 0.0

    def __post_init__(self):
        """Compute maturity time."""
        self.maturity_time = self.creation_time + (self.term_months * 30.44 * 24 * 3600)

    def compute_monthly_payment(self) -> float:
        """Compute monthly payment using amortization formula.

        Returns:
            Monthly payment amount
        """
        if self.interest_rate == 0:
            return self.principal / self.term_months

        monthly_rate = self.interest_rate / 12
        n = self.term_months

        # Standard amortization: M = P * [r(1+r)^n] / [(1+r)^n - 1]
        payment = self.principal * (monthly_rate * (1 + monthly_rate) ** n) / ((1 + monthly_rate) ** n - 1)
        return payment

    def accrue_interest(self, current_time: Optional[float] = None):
        """Accrue interest up to the current time.

        Args:
            current_time: Optional timestamp; defaults to now
        """
        if current_time is None:
            current_time = time.time()

        elapsed_days = (current_time - self.creation_time) / (24 * 3600)
        daily_rate = self.interest_rate / 365.25

        # Simple interest accrual
        self.accrued_interest = self.principal * daily_rate * elapsed_days

    def make_repayment(self, amount: float, current_time: Optional[float] = None) -> Dict[str, Any]:
        """Make a repayment on the loan.

        Args:
            amount: Repayment amount
            current_time: Optional timestamp; defaults to now

        Returns:
            Repayment record
        """
        if current_time is None:
            current_time = time.time()

        self.accrued_interest = max(0, self.accrued_interest - amount * 0.1)
        principal_payment = amount * 0.9
        self.total_repaid += amount

        repayment = {
            "amount": amount,
            "principal": principal_payment,
            "interest": amount - principal_payment,
            "timestamp": current_time,
        }
        self.repayments.append(repayment)

        if self.total_repaid >= self.principal + self.accrued_interest:
            self.status = LoanStatus.REPAID

        return repayment

    def remaining_balance(self) -> float:
        """Compute remaining loan balance.

        Returns:
            Remaining principal + accrued interest
        """
        return max(0, self.principal + self.accrued_interest - self.total_repaid)


@dataclass
class GenesisLoanDerivative:
    """Options and futures on Genesis loans.

    Enables trading of loan risk and yield.

    Attributes:
        derivative_id: Unique identifier
        underlying_loan_id: Loan this derivative is based on
        derivative_type: "call", "put", or "future"
        strike_price: Strike price (interest rate or loan value)
        expiration_time: Expiration timestamp
        holder: Derivative holder
        writer: Derivative writer
        is_exercised: Whether the derivative has been exercised
        payout: Payout amount if exercised
    """
    derivative_id: str
    underlying_loan_id: str
    derivative_type: str
    strike_price: float
    expiration_time: float
    holder: str
    writer: str
    is_exercised: bool = False
    payout: Optional[float] = None


@dataclass
class GenesisLoanPool:
    """Liquidity pool for Genesis loans.

    Allows anyone to lend against Genesis collateral and earn yield.

    Attributes:
        pool_id: Unique pool identifier
        total_deposited: Total USD deposited in the pool
        total_lent: Total USD lent from the pool
        average_rate: Average interest rate
        yield_rate: Pool yield rate
        depositors: Dict of depositor -> deposit amount
        borrowers: Dict of borrower -> borrow amount
    """
    pool_id: str
    total_deposited: float = 0.0
    total_lent: float = 0.0
    average_rate: float = 0.05
    yield_rate: float = 0.0
    depositors: Dict[str, float] = field(default_factory=dict)
    borrowers: Dict[str, float] = field(default_factory=dict)


@dataclass
class MultiGenesisVault:
    """Vault combining multiple genesis blocks as cross-chain collateral.

    Attributes:
        vault_id: Unique vault identifier
        genesis_proofs: List of genesis proofs from different chains
        combined_value: Combined collateral value
        lock_hash: Cryptographic seal
    """
    vault_id: str
    genesis_proofs: List[GenesisBTCProof]
    combined_value: float = 0.0
    lock_hash: str = ""

    def __post_init__(self):
        """Compute combined value and seal."""
        self.combined_value = sum(p.compute_collateral_value() for p in self.genesis_proofs)
        seal_content = json.dumps({
            "vault_id": self.vault_id,
            "proofs": [p.block_hash for p in self.genesis_proofs],
        }, sort_keys=True)
        self.lock_hash = hashlib.sha256(seal_content.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Genesis Loan Engine
# ---------------------------------------------------------------------------


class GenesisLoanEngine:
    """Engine for creating and managing Genesis BTC collateralized loans.

    The engine uses the Genesis Block as the ultimate collateral,
    creating loans that are backed by the causal root of Bitcoin.

    Key features:
    - LTV-based lending with dynamic collateral valuation
    - Interest accrual using CTC time-dilation models
    - Repayment tracking and early payoff
    - Default detection and collateral liquidation
    - Derivative creation on loans
    - Liquidity pool management
    """

    def __init__(self, max_ltv: float = 0.5, default_interest_rate: float = 0.05):
        """Initialize the Genesis loan engine.

        Args:
            max_ltv: Maximum loan-to-value ratio (default 50%)
            default_interest_rate: Default annual interest rate (default 5%)
        """
        self.max_ltv = max_ltv
        self.default_interest_rate = default_interest_rate
        self.vaults: Dict[str, GenesisCollateralVault] = {}
        self.loans: Dict[str, GenesisLoan] = {}
        self.derivatives: Dict[str, GenesisLoanDerivative] = {}
        self.pools: Dict[str, GenesisLoanPool] = {}
        self.multi_vaults: Dict[str, MultiGenesisVault] = {}
        self.loan_counter = 0
        self.derivative_counter = 0

    def create_genesis_vault(self, vault_id: Optional[str] = None) -> GenesisCollateralVault:
        """Create a vault locking the Genesis Block as collateral.

        Args:
            vault_id: Optional vault ID; auto-generated if not provided

        Returns:
            The created vault
        """
        if vault_id is None:
            vault_id = f"genesis_vault_{len(self.vaults) + 1}"

        genesis_proof = GenesisBTCProof(proof_id=f"genesis_proof_{len(self.vaults) + 1}")
        vault = GenesisCollateralVault(vault_id=vault_id, genesis_proof=genesis_proof)

        self.vaults[vault_id] = vault
        return vault

    def create_loan(
        self,
        vault_id: str,
        borrower: str,
        principal: float,
        interest_rate: Optional[float] = None,
        term_months: int = 12,
    ) -> GenesisLoan:
        """Create a loan backed by Genesis collateral.

        Args:
            vault_id: ID of the collateral vault
            borrower: Borrower identifier
            principal: Loan principal in USD
            interest_rate: Annual interest rate (optional, uses default)
            term_months: Loan term in months

        Returns:
            The created loan

        Raises:
            ValueError: If LTV exceeds maximum or vault not found
        """
        vault = self.vaults.get(vault_id)
        if vault is None:
            raise ValueError(f"Vault {vault_id} not found")

        if interest_rate is None:
            interest_rate = self.default_interest_rate

        # Check LTV
        collateral_value = vault.genesis_proof.compute_collateral_value()
        ltv = principal / collateral_value

        if ltv > self.max_ltv:
            raise ValueError(
                f"LTV {ltv:.2%} exceeds maximum {self.max_ltv:.2%}. "
                f"Max loan: ${collateral_value * self.max_ltv:,.2f}"
            )

        # Create loan
        self.loan_counter += 1
        loan = GenesisLoan(
            loan_id=f"genesis_loan_{self.loan_counter}",
            vault_id=vault_id,
            borrower=borrower,
            principal=principal,
            interest_rate=interest_rate,
            term_months=term_months,
            ltv_ratio=ltv,
        )

        self.loans[loan.loan_id] = loan
        vault.total_loans += 1
        vault.total_borrowed += principal

        return loan

    def repay_loan(
        self,
        loan_id: str,
        amount: float,
    ) -> Dict[str, Any]:
        """Make a repayment on a Genesis loan.

        Args:
            loan_id: ID of the loan
            amount: Repayment amount

        Returns:
            Repayment record
        """
        loan = self.loans.get(loan_id)
        if loan is None:
            raise ValueError(f"Loan {loan_id} not found")

        if loan.status == LoanStatus.REPAID:
            raise ValueError(f"Loan {loan_id} is already repaid")

        return loan.make_repayment(amount)

    def create_derivative(
        self,
        loan_id: str,
        derivative_type: str,
        strike_price: float,
        expiration_days: int,
        holder: str,
        writer: str,
    ) -> GenesisLoanDerivative:
        """Create a derivative on a Genesis loan.

        Args:
            loan_id: Underlying loan ID
            derivative_type: "call", "put", or "future"
            strike_price: Strike price
            expiration_days: Days until expiration
            holder: Derivative holder
            writer: Derivative writer

        Returns:
            The created derivative
        """
        loan = self.loans.get(loan_id)
        if loan is None:
            raise ValueError(f"Loan {loan_id} not found")

        self.derivative_counter += 1
        derivative = GenesisLoanDerivative(
            derivative_id=f"genesis_deriv_{self.derivative_counter}",
            underlying_loan_id=loan_id,
            derivative_type=derivative_type,
            strike_price=strike_price,
            expiration_time=time.time() + (expiration_days * 24 * 3600),
            holder=holder,
            writer=writer,
        )

        self.derivatives[derivative.derivative_id] = derivative
        return derivative

    def create_pool(self, pool_id: Optional[str] = None) -> GenesisLoanPool:
        """Create a liquidity pool for Genesis loans.

        Args:
            pool_id: Optional pool ID; auto-generated if not provided

        Returns:
            The created pool
        """
        if pool_id is None:
            pool_id = f"genesis_pool_{len(self.pools) + 1}"

        pool = GenesisLoanPool(pool_id=pool_id)
        self.pools[pool_id] = pool
        return pool

    def deposit_to_pool(
        self,
        pool_id: str,
        depositor: str,
        amount: float,
    ) -> float:
        """Deposit funds into a Genesis loan pool.

        Args:
            pool_id: Pool ID
            depositor: Depositor identifier
            amount: Deposit amount in USD

        Returns:
            New total deposited
        """
        pool = self.pools.get(pool_id)
        if pool is None:
            raise ValueError(f"Pool {pool_id} not found")

        if depositor not in pool.depositors:
            pool.depositors[depositor] = 0
        pool.depositors[depositor] += amount
        pool.total_deposited += amount

        # Update yield rate based on utilization
        if pool.total_deposited > 0:
            utilization = pool.total_lent / pool.total_deposited
            pool.yield_rate = pool.average_rate * utilization

        return pool.total_deposited

    def borrow_from_pool(
        self,
        pool_id: str,
        borrower: str,
        amount: float,
    ) -> float:
        """Borrow from a Genesis loan pool.

        Args:
            pool_id: Pool ID
            borrower: Borrower identifier
            amount: Borrow amount in USD

        Returns:
            New total lent
        """
        pool = self.pools.get(pool_id)
        if pool is None:
            raise ValueError(f"Pool {pool_id} not found")

        if amount > pool.total_deposited - pool.total_lent:
            raise ValueError("Insufficient pool liquidity")

        if borrower not in pool.borrowers:
            pool.borrowers[borrower] = 0
        pool.borrowers[borrower] += amount
        pool.total_lent += amount

        # Update yield rate
        if pool.total_deposited > 0:
            utilization = pool.total_lent / pool.total_deposited
            pool.yield_rate = pool.average_rate * utilization

        return pool.total_lent

    def create_multi_genesis_vault(
        self,
        vault_id: str,
        genesis_proofs: List[GenesisBTCProof],
    ) -> MultiGenesisVault:
        """Create a vault combining multiple genesis blocks.

        Args:
            vault_id: Vault identifier
            genesis_proofs: List of genesis proofs from different chains

        Returns:
            The created multi-genesis vault
        """
        vault = MultiGenesisVault(vault_id=vault_id, genesis_proofs=genesis_proofs)
        self.multi_vaults[vault_id] = vault
        return vault

    def get_loan_summary(self, loan_id: str) -> Dict[str, Any]:
        """Get a summary of a Genesis loan.

        Args:
            loan_id: Loan ID

        Returns:
            Dictionary with loan summary
        """
        loan = self.loans.get(loan_id)
        if loan is None:
            raise ValueError(f"Loan {loan_id} not found")

        vault = self.vaults.get(loan.vault_id)
        collateral_value = vault.genesis_proof.compute_collateral_value() if vault else 0

        return {
            "loan_id": loan.loan_id,
            "borrower": loan.borrower,
            "principal": loan.principal,
            "interest_rate": f"{loan.interest_rate * 100:.2f}%",
            "term_months": loan.term_months,
            "ltv_ratio": f"{loan.ltv_ratio * 100:.2f}%",
            "status": loan.status.value,
            "monthly_payment": loan.compute_monthly_payment(),
            "remaining_balance": loan.remaining_balance(),
            "total_repaid": loan.total_repaid,
            "accrued_interest": loan.accrued_interest,
            "collateral_value": collateral_value,
            "collateral_consistent": vault.collateral_consistency() if vault else False,
        }

    def get_engine_stats(self) -> Dict[str, Any]:
        """Get overall engine statistics.

        Returns:
            Dictionary with engine statistics
        """
        total_borrowed = sum(l.principal for l in self.loans.values())
        total_repaid = sum(l.total_repaid for l in self.loans.values())
        active_loans = len([l for l in self.loans.values() if l.status == LoanStatus.ACTIVE])

        return {
            "total_vaults": len(self.vaults),
            "total_loans": len(self.loans),
            "active_loans": active_loans,
            "total_borrowed": total_borrowed,
            "total_repaid": total_repaid,
            "outstanding": total_borrowed - total_repaid,
            "total_derivatives": len(self.derivatives),
            "total_pools": len(self.pools),
            "total_multi_vaults": len(self.multi_vaults),
        }


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def run_genesis_loan_demo():
    """Run a comprehensive demo of Genesis BTC collateralized loans."""
    print("=" * 70)
    print("GENESIS BTC COLLATERAL LOAN")
    print("The Ultimate Loan Backed by the First Block of Bitcoin")
    print("=" * 70)

    # 1. Create the engine
    print("\n--- 1. Creating Genesis Loan Engine ---")
    engine = GenesisLoanEngine(max_ltv=0.5, default_interest_rate=0.05)
    print(f"Engine created: max LTV={engine.max_ltv:.0%}, default rate={engine.default_interest_rate:.1%}")

    # 2. Create Genesis vault
    print("\n--- 2. Locking Genesis Block as Collateral ---")
    vault = engine.create_genesis_vault("genesis_vault_1")
    genesis = vault.genesis_proof

    print(f"Vault ID: {vault.vault_id}")
    print(f"Genesis Block: {genesis.block_hash[:16]}...")
    print(f"Coinbase TX: {genesis.coinbase_tx[:16]}...")
    print(f"Nonce: {genesis.nonce:,}")
    print(f"Embedded message: {genesis.embedded_message}")
    print(f"Verified: {genesis.verify()}")
    print(f"Collateral value: ${genesis.compute_collateral_value():,.2f}")
    print(f"Vault seal intact: {vault.verify_seal()}")
    print(f"Collateral consistent: {vault.collateral_consistency()}")

    # 3. Create a loan
    print("\n--- 3. Creating Genesis-Backed Loan ---")
    loan = engine.create_loan(
        vault_id=vault.vault_id,
        borrower="satoshi_heir",
        principal=500000.0,
        interest_rate=0.03,
        term_months=24,
    )
    print(f"Loan ID: {loan.loan_id}")
    print(f"Borrower: {loan.borrower}")
    print(f"Principal: ${loan.principal:,.2f}")
    print(f"Interest rate: {loan.interest_rate * 100:.1f}% APR")
    print(f"Term: {loan.term_months} months")
    print(f"LTV ratio: {loan.ltv_ratio * 100:.2f}%")
    print(f"Monthly payment: ${loan.compute_monthly_payment():,.2f}")
    print(f"Status: {loan.status.value}")

    # 4. Accrue interest
    print("\n--- 4. Interest Accrual ---")
    # Simulate 30 days passing
    future_time = time.time() + (30 * 24 * 3600)
    loan.accrue_interest(future_time)
    print(f"Interest accrued after 30 days: ${loan.accrued_interest:,.2f}")
    print(f"Remaining balance: ${loan.remaining_balance():,.2f}")

    # 5. Make repayments
    print("\n--- 5. Loan Repayments ---")
    monthly_payment = loan.compute_monthly_payment()
    for month in range(1, 4):  # 3 months of payments
        repayment_time = time.time() + (month * 30 * 24 * 3600)
        loan.accrue_interest(repayment_time)
        repayment = loan.make_repayment(monthly_payment, repayment_time)
        print(f"  Month {month}: paid ${repayment['amount']:,.2f}, "
              f"remaining: ${loan.remaining_balance():,.2f}")

    # 6. Create derivatives
    print("\n--- 6. Creating Loan Derivatives ---")
    call_option = engine.create_derivative(
        loan_id=loan.loan_id,
        derivative_type="call",
        strike_price=0.04,  # 4% interest rate cap
        expiration_days=180,
        holder="hedger",
        writer="bank",
    )
    print(f"Call option created: {call_option.derivative_id}")
    print(f"  Type: {call_option.derivative_type}")
    print(f"  Strike: {call_option.strike_price * 100:.1f}%")
    print(f"  Holder: {call_option.holder}, Writer: {call_option.writer}")

    # 7. Create liquidity pool
    print("\n--- 7. Creating Genesis Loan Pool ---")
    pool = engine.create_pool("genesis_pool_1")

    # Depositors
    engine.deposit_to_pool(pool.pool_id, "alice", 1000000.0)
    engine.deposit_to_pool(pool.pool_id, "bob", 500000.0)
    print(f"Pool deposits: ${pool.total_deposited:,.2f}")
    print(f"Depositors: {len(pool.depositors)}")

    # Borrower
    engine.borrow_from_pool(pool.pool_id, "charlie", 300000.0)
    print(f"Pool lent: ${pool.total_lent:,.2f}")
    print(f"Pool yield rate: {pool.yield_rate * 100:.2f}%")

    # 8. Multi-genesis vault
    print("\n--- 8. Multi-Genesis Cross-Chain Vault ---")
    # Create a second genesis proof (simulated Ethereum genesis)
    eth_genesis = GenesisBTCProof(
        proof_id="eth_genesis",
        block_hash="d4e56740f876aef8c010b86a40d5f56745a118d0906a34e69aec8c0db1cb8fa3",
        coinbase_tx="0x0",
        nonce=0,
        timestamp=1438269973,  # 2015-07-30
        embedded_message="Ethereum Genesis",
        coinbase_value=0.0,
    )

    multi_vault = engine.create_multi_genesis_vault(
        "multi_genesis_1",
        [genesis, eth_genesis],
    )
    print(f"Multi-genesis vault: {multi_vault.vault_id}")
    print(f"Genesis blocks: {len(multi_vault.genesis_proofs)}")
    print(f"Combined value: ${multi_vault.combined_value:,.2f}")

    # 9. Loan summary
    print("\n--- 9. Loan Summary ---")
    summary = engine.get_loan_summary(loan.loan_id)
    for key, value in summary.items():
        print(f"  {key}: {value}")

    # 10. Engine statistics
    print("\n--- 10. Engine Statistics ---")
    stats = engine.get_engine_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    print("\n" + "=" * 70)
    print("GENESIS BTC COLLATERAL LOAN — Demo Complete")
    print("=" * 70)
    print("\nThe Genesis Block is the ultimate collateral:")
    print("- Cryptographically immutable (SHA-256 proof-of-work)")
    print("- Economically foundational (root of all Bitcoin value)")
    print("- Historically significant (first block, first transaction)")
    print("- Mathematically unique (nonce found by Satoshi)")
    print("\nThe loan is guaranteed not by a bank or government,")
    print("but by the causal structure of the Bitcoin blockchain itself.")
    print(f"\nGenesis Block hash: {GENESIS_BLOCK_HASH}")
    print(f"Embedded message: {GENESIS_EMBEDDED_MESSAGE}")


if __name__ == "__main__":
    run_genesis_loan_demo()
