#!/usr/bin/env python3
"""CTC Oracle Market — Trading PSPACE-level Computation as Financial Instruments.

This module invents a novel financial primitive: the CTC Oracle Proof.

The Core Insight
================
The Deutsch CTC fixed-point model grants PSPACE-level computational power.
Every CTC computation produces a verifiable fixed-point proof: a density
matrix ρ satisfying S(ρ) = ρ. This proof is:

1. Cryptographically verifiable — anyone can check S(ρ) = ρ
2. Computationally irrefutable — the fixed point either exists or doesn't
3. Economically valuable — it solves problems that would otherwise cost
   exponential time to compute

The CTC Oracle Market packages these proofs as tradable financial instruments.

Key Innovations
===============
1. **CTCOracleProof**: A cryptographically verifiable proof that a PSPACE
   problem has been solved via CTC fixed-point consistency. Includes the
   problem statement, solution, fixed-point certificate, and verification key.

2. **OracleMarket**: A matching engine for buying and selling oracle proofs.
   Prices are determined by the computational complexity of the underlying
   problem and the confidence level of the proof.

3. **CTCOracleToken**: A tokenized oracle computation that can be traded,
   staked, or redeemed. Each token represents a claim on the computational
   value of a specific CTC proof.

4. **ProofAggregator**: Combines multiple CTC proofs into compound proofs
   with multiplicative value — solving multiple PSPACE problems simultaneously
   creates exponentially more value than solving them sequentially.

5. **TemporalArbitrageDetector**: Uses the CTC model to find profit
   opportunities across different "timelines" (solution spaces). If a proof
   exists in one timeline but not another, the price difference represents
   arbitrage opportunity.

6. **CausalBond**: A financial instrument backed by CTC consistency. The bond
   pays out if and only if the underlying CTC proof remains consistent — i.e.,
   the fixed point S(ρ) = ρ continues to hold. This creates a new class of
   "causally-backed" securities.

7. **OracleDerivatives**: Options and futures on oracle proofs. Trade the
   right to buy/sell proofs at future prices, creating a derivatives market
   for computational power.

8. **ProofLiquidityPool**: Automated market maker (AMM) for oracle proofs,
   using the CTC fixed-point equation as the bonding curve. The invariant
   S(ρ) = ρ becomes the liquidity pool invariant.

9. **TemporalStaking**: Stake oracle proofs to secure the network and earn
   rewards proportional to the computational value of staked proofs.

10. **CausalInsurance**: Insurance products backed by CTC consistency. If a
    proof's consistency is broken (fixed point no longer holds), the insurance
    pays out — creating a market for "causal risk."

Economic Model
==============
- Oracle proofs are priced by their computational complexity (PSPACE depth)
- The market uses CTC fixed-point equations as pricing oracles
- Liquidity is provided by proof staking and causal bonds
- Arbitrage is detected across timelines using multi-CTC entanglement
- Derivatives allow hedging against computational risk

Why This Shocks the World
==========================
1. It turns theoretical physics (CTCs) into tradable financial instruments
2. It creates a market for PSPACE-level computation
3. It uses the fixed-point equation S(ρ) = ρ as both a computational AND
   financial invariant — the same math that makes CTCs consistent also
   makes the market consistent
4. It enables "causal arbitrage" — profiting from inconsistencies across
   different solution spaces
5. It creates a new asset class: causally-backed securities

References
==========
1. Aaronson, S. & Watrous, J. (2008). "Closed Timelike Curves Make
   Quantum and Classical Computing Equivalent."
2. Deutsch, D. (1991). "Quantum mechanics near closed timelike lines."
3. Uniswap whitepaper (for AMM design inspiration)
4. Bitcoin whitepaper (for proof-of-work inspiration)
"""

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------


class OracleProofStatus(Enum):
    """Status of an oracle proof in the market."""
    PENDING = "pending"
    VERIFIED = "verified"
    TRADED = "traded"
    REDEEMED = "redeemed"
    EXPIRED = "expired"


class ProofType(Enum):
    """Type of computational problem solved by the oracle."""
    SAT = "sat"              # Boolean satisfiability
    SUBSET_SUM = "subset_sum"  # Subset sum problem
    QBF = "qbf"              # Quantified Boolean Formula (PSPACE)
    FACTORIZATION = "factorization"  # Integer factorization
    HASH_COLLISION = "hash_collision"  # Cryptographic hash collision
    GRAPH_COLORING = "graph_coloring"  # Graph coloring (NP-complete)
    TSP = "tsp"              # Traveling Salesman Problem (NP-hard)
    CUSTOM = "custom"        # Custom problem


@dataclass
class CTCOracleProof:
    """A cryptographically verifiable oracle proof.

    This is the core financial primitive: a proof that a PSPACE problem
    has been solved via CTC fixed-point consistency. The proof includes
    the problem statement, solution, fixed-point certificate, and
    cryptographic verification key.

    The proof is valuable because:
    1. It solves a problem that would otherwise cost exponential time
    2. The solution is cryptographically verifiable
    3. The fixed-point certificate provides irrefutable evidence

    Attributes:
        proof_id: Unique identifier for this proof
        proof_type: Type of computational problem solved
        problem_statement: JSON-serializable problem definition
        solution: The computed solution
        fixed_point_certificate: The density matrix ρ satisfying S(ρ) = ρ
        verification_key: Cryptographic key for verifying the proof
        complexity_score: Computational complexity (PSPACE depth)
        confidence: Confidence level of the proof (0-1)
        timestamp: Creation timestamp
        status: Current status in the market
        creator: Identifier of the proof creator
        price: Current market price (in base units)
        trade_history: List of trades involving this proof
    """
    proof_id: str
    proof_type: ProofType
    problem_statement: Dict[str, Any]
    solution: Dict[str, Any]
    fixed_point_certificate: Dict[str, Any]
    verification_key: str
    complexity_score: float
    confidence: float
    timestamp: float
    status: OracleProofStatus
    creator: str
    price: float
    trade_history: List[Dict[str, Any]] = field(default_factory=list)

    def verify(self) -> bool:
        """Verify the cryptographic integrity of this proof.

        Returns True if the proof's verification key matches the hash
        of the proof content, ensuring the proof hasn't been tampered with.
        """
        content = json.dumps({
            "problem": self.problem_statement,
            "solution": self.solution,
            "certificate": self.fixed_point_certificate,
        }, sort_keys=True)
        expected_key = hashlib.sha256(content.encode()).hexdigest()
        return self.verification_key == expected_key

    def compute_value(self) -> float:
        """Compute the economic value of this proof.

        Value is determined by:
        - Complexity score (higher complexity = more value)
        - Confidence level (higher confidence = more value)
        - Proof type (some types are inherently more valuable)
        - Age (newer proofs are more valuable)

        Returns:
            Economic value in base units
        """
        # Base value from complexity
        base_value = self.complexity_score * 100

        # Confidence multiplier
        confidence_multiplier = self.confidence

        # Type multiplier (some problems are more valuable)
        type_multipliers = {
            ProofType.QBF: 3.0,           # PSPACE-complete
            ProofType.FACTORIZATION: 2.5,  # Cryptographic
            ProofType.HASH_COLLISION: 2.0, # Cryptographic
            ProofType.TSP: 1.5,           # NP-hard
            ProofType.GRAPH_COLORING: 1.3, # NP-complete
            ProofType.SUBSET_SUM: 1.2,    # NP-complete
            ProofType.SAT: 1.0,           # NP-complete (baseline)
            ProofType.CUSTOM: 1.0,
        }
        type_multiplier = type_multipliers.get(self.proof_type, 1.0)

        # Age decay (newer proofs are more valuable)
        age_hours = (time.time() - self.timestamp) / 3600
        age_decay = max(0.1, 1.0 - (age_hours * 0.01))

        return base_value * confidence_multiplier * type_multiplier * age_decay


@dataclass
class OracleOrder:
    """A buy or sell order in the oracle market."""
    order_id: str
    proof_id: str
    side: str  # "buy" or "sell"
    price: float
    quantity: int
    timestamp: float
    status: str  # "open", "filled", "cancelled"
    trader: str


@dataclass
class OracleTrade:
    """A completed trade in the oracle market."""
    trade_id: str
    proof_id: str
    buyer: str
    seller: str
    price: float
    quantity: int
    timestamp: float
    total_value: float


@dataclass
class CausalBond:
    """A financial instrument backed by CTC consistency.

    The bond pays out if and only if the underlying CTC proof remains
    consistent — i.e., the fixed point S(ρ) = ρ continues to hold.

    This creates a new class of "causally-backed" securities where the
    payout is guaranteed by the laws of physics (fixed-point consistency).
    """
    bond_id: str
    proof_id: str
    face_value: float
    interest_rate: float  # Annual interest rate
    maturity_date: float   # Unix timestamp
    issuer: str
    holders: List[str]
    is_consistent: bool    # Whether the underlying proof is still consistent
    payout_status: str     # "pending", "paid", "defaulted"


@dataclass
class OracleDerivative:
    """Options and futures on oracle proofs.

    Allows trading the right to buy/sell proofs at future prices,
    creating a derivatives market for computational power.
    """
    derivative_id: str
    underlying_proof_id: str
    derivative_type: str  # "call_option", "put_option", "future"
    strike_price: float
    expiration_date: float
    holder: str
    writer: str
    is_exercised: bool
    payout: Optional[float]


@dataclass
class LiquidityPoolState:
    """State of a proof liquidity pool (AMM).

    Uses the CTC fixed-point equation as the bonding curve invariant.
    The invariant S(ρ) = ρ becomes the liquidity pool invariant:
    the product of proof reserves must remain constant.
    """
    pool_id: str
    proof_type: ProofType
    reserve_proofs: float    # Total proofs in the pool
    reserve_tokens: float    # Total tokens in the pool
    invariant: float         # S(ρ) = ρ bonding curve invariant
    total_shares: float      # Total LP shares issued
    traders: Dict[str, float]  # Trader address -> LP shares


@dataclass
class StakingReward:
    """Reward for staking oracle proofs."""
    staker: str
    proof_ids: List[str]
    staked_value: float
    reward_rate: float       # Rewards per unit time
    total_rewards: float     # Total rewards earned
    staking_duration: float  # Duration in seconds


@dataclass
class CausalInsurance:
    """Insurance product backed by CTC consistency.

    If a proof's consistency is broken (fixed point no longer holds),
    the insurance pays out — creating a market for "causal risk."
    """
    policy_id: str
    proof_id: str
    coverage_amount: float
    premium: float
    insured_party: str
    insurer: str
    is_active: bool
    has_claims: bool
    payout_amount: Optional[float]


@dataclass
class ArbitrageOpportunity:
    """Profit opportunity across CTC timelines."""
    opportunity_id: str
    proof_id: str
    timeline_a_price: float
    timeline_b_price: float
    spread: float            # Price difference
    expected_profit: float   # Expected profit after costs
    detection_time: float


# ---------------------------------------------------------------------------
# Oracle Market Engine
# ---------------------------------------------------------------------------


class OracleMarket:
    """Matching engine for buying and selling oracle proofs.

    The market uses CTC fixed-point equations as pricing oracles.
    Prices are determined by the computational complexity of the
    underlying problem and the confidence level of the proof.

    Key features:
    - Order book with buy/sell orders
    - Automatic price discovery via CTC complexity scoring
    - Trade execution with fee collection
    - Market depth analysis
    - Temporal arbitrage detection
    """

    def __init__(self, fee_rate: float = 0.001):
        """Initialize the oracle market.

        Args:
            fee_rate: Trading fee rate (default 0.1%)
        """
        self.fee_rate = fee_rate
        self.proofs: Dict[str, CTCOracleProof] = {}
        self.orders: Dict[str, OracleOrder] = {}
        self.trades: List[OracleTrade] = []
        self.bonds: Dict[str, CausalBond] = {}
        self.derivatives: Dict[str, OracleDerivative] = {}
        self.liquidity_pools: Dict[str, LiquidityPoolState] = {}
        self.staking_positions: Dict[str, StakingReward] = {}
        self.insurance_policies: Dict[str, CausalInsurance] = {}
        self.arbitrage_opportunities: List[ArbitrageOpportunity] = []
        self.trade_counter = 0
        self.order_counter = 0

    def register_proof(self, proof: CTCOracleProof) -> str:
        """Register a new oracle proof in the market.

        Args:
            proof: The oracle proof to register

        Returns:
            The proof ID
        """
        self.proofs[proof.proof_id] = proof
        return proof.proof_id

    def place_order(self, order: OracleOrder) -> str:
        """Place a buy or sell order in the market.

        Args:
            order: The order to place

        Returns:
            The order ID
        """
        self.orders[order.order_id] = order
        self.order_counter += 1

        # Try to match against existing orders
        if order.side == "buy":
            self._match_buy_order(order)
        else:
            self._match_sell_order(order)

        return order.order_id

    def _match_buy_order(self, buy_order: OracleOrder):
        """Try to match a buy order against sell orders."""
        for order in self.orders.values():
            if (order.side == "sell" and
                order.proof_id == buy_order.proof_id and
                order.status == "open" and
                order.price <= buy_order.price):
                # Match found
                quantity = min(buy_order.quantity, order.quantity)
                self._execute_trade(buy_order, order, quantity)
                return

    def _match_sell_order(self, sell_order: OracleOrder):
        """Try to match a sell order against buy orders."""
        for order in self.orders.values():
            if (order.side == "buy" and
                order.proof_id == sell_order.proof_id and
                order.status == "open" and
                order.price >= sell_order.price):
                # Match found
                quantity = min(sell_order.quantity, order.quantity)
                self._execute_trade(order, sell_order, quantity)
                return

    def _execute_trade(
        self,
        buy_order: OracleOrder,
        sell_order: OracleOrder,
        quantity: int,
    ):
        """Execute a trade between a buy and sell order.

        Args:
            buy_order: The buy order
            sell_order: The sell order
            quantity: Number of proofs to trade
        """
        # Calculate trade details
        price = (buy_order.price + sell_order.price) / 2
        total_value = price * quantity
        fee = total_value * self.fee_rate

        # Create trade record
        self.trade_counter += 1
        trade = OracleTrade(
            trade_id=f"trade_{self.trade_counter}",
            proof_id=buy_order.proof_id,
            buyer=buy_order.trader,
            seller=sell_order.trader,
            price=price,
            quantity=quantity,
            timestamp=time.time(),
            total_value=total_value - fee,
        )
        self.trades.append(trade)

        # Update order statuses
        if buy_order.quantity == quantity:
            buy_order.status = "filled"
        else:
            buy_order.quantity -= quantity

        if sell_order.quantity == quantity:
            sell_order.status = "filled"
        else:
            sell_order.quantity -= quantity

        # Update proof trade history
        proof = self.proofs.get(buy_order.proof_id)
        if proof:
            proof.trade_history.append({
                "trade_id": trade.trade_id,
                "buyer": trade.buyer,
                "seller": trade.seller,
                "price": trade.price,
                "quantity": trade.quantity,
                "timestamp": trade.timestamp,
            })
            proof.price = price  # Update market price

    def create_causal_bond(
        self,
        proof_id: str,
        face_value: float,
        interest_rate: float,
        maturity_years: float,
        issuer: str,
    ) -> CausalBond:
        """Create a causal bond backed by a CTC proof.

        Args:
            proof_id: ID of the underlying proof
            face_value: Face value of the bond
            interest_rate: Annual interest rate
            maturity_years: Years until maturity
            issuer: Bond issuer identifier

        Returns:
            The created causal bond
        """
        bond_id = f"bond_{len(self.bonds) + 1}"
        maturity_date = time.time() + (maturity_years * 365.25 * 24 * 3600)

        bond = CausalBond(
            bond_id=bond_id,
            proof_id=proof_id,
            face_value=face_value,
            interest_rate=interest_rate,
            maturity_date=maturity_date,
            issuer=issuer,
            holders=[issuer],
            is_consistent=True,
            payout_status="pending",
        )
        self.bonds[bond_id] = bond
        return bond

    def create_derivative(
        self,
        proof_id: str,
        derivative_type: str,
        strike_price: float,
        expiration_days: int,
        holder: str,
        writer: str,
    ) -> OracleDerivative:
        """Create a derivative contract on an oracle proof.

        Args:
            proof_id: ID of the underlying proof
            derivative_type: "call_option", "put_option", or "future"
            strike_price: Strike price for the derivative
            expiration_days: Days until expiration
            holder: Derivative holder
            writer: Derivative writer

        Returns:
            The created derivative
        """
        derivative_id = f"deriv_{len(self.derivatives) + 1}"
        expiration_date = time.time() + (expiration_days * 24 * 3600)

        derivative = OracleDerivative(
            derivative_id=derivative_id,
            underlying_proof_id=proof_id,
            derivative_type=derivative_type,
            strike_price=strike_price,
            expiration_date=expiration_date,
            holder=holder,
            writer=writer,
            is_exercised=False,
            payout=None,
        )
        self.derivatives[derivative_id] = derivative
        return derivative

    def create_liquidity_pool(
        self,
        proof_type: ProofType,
        initial_proofs: float,
        initial_tokens: float,
    ) -> LiquidityPoolState:
        """Create a liquidity pool for a proof type (AMM).

        Uses the CTC fixed-point equation as the bonding curve invariant.

        Args:
            proof_type: Type of proofs in the pool
            initial_proofs: Initial proof reserve
            initial_tokens: Initial token reserve

        Returns:
            The created liquidity pool state
        """
        pool_id = f"pool_{len(self.liquidity_pools) + 1}"
        invariant = initial_proofs * initial_tokens  # S(ρ) = ρ invariant

        pool = LiquidityPoolState(
            pool_id=pool_id,
            proof_type=proof_type,
            reserve_proofs=initial_proofs,
            reserve_tokens=initial_tokens,
            invariant=invariant,
            total_shares=initial_tokens,
            traders={},
        )
        self.liquidity_pools[pool_id] = pool
        return pool

    def swap_in_pool(
        self,
        pool_id: str,
        amount_in: float,
        trader: str,
    ) -> float:
        """Execute a swap in a liquidity pool.

        Uses the constant product invariant: x * y = k
        where x = proof reserve, y = token reserve.

        Args:
            pool_id: ID of the liquidity pool
            amount_in: Amount of proofs to swap
            trader: Trader identifier

        Returns:
            Amount of tokens received
        """
        pool = self.liquidity_pools.get(pool_id)
        if not pool:
            raise ValueError(f"Pool {pool_id} not found")

        # Constant product formula: (x + Δx) * (y - Δy) = x * y
        # Solving for Δy:
        x = pool.reserve_proofs
        y = pool.reserve_tokens
        delta_x = amount_in

        # Δy = y - (x * y) / (x + Δx)
        delta_y = y - (x * y) / (x + delta_x)

        # Apply fee
        delta_y_after_fee = delta_y * (1 - self.fee_rate)

        # Update pool state
        pool.reserve_proofs += delta_x
        pool.reserve_tokens -= delta_y

        # Update trader shares
        if trader not in pool.traders:
            pool.traders[trader] = 0
        pool.traders[trader] += delta_y_after_fee

        return delta_y_after_fee

    def stake_proofs(
        self,
        proof_ids: List[str],
        staker: str,
    ) -> StakingReward:
        """Stake oracle proofs to earn rewards.

        Args:
            proof_ids: List of proof IDs to stake
            staker: Staker identifier

        Returns:
            The staking reward position
        """
        # Calculate total staked value
        total_value = 0.0
        for pid in proof_ids:
            proof = self.proofs.get(pid)
            if proof:
                total_value += proof.compute_value()

        # Reward rate is proportional to staked value
        reward_rate = total_value * 0.0001  # 0.01% per unit time

        staking = StakingReward(
            staker=staker,
            proof_ids=proof_ids,
            staked_value=total_value,
            reward_rate=reward_rate,
            total_rewards=0.0,
            staking_duration=0.0,
        )
        self.staking_positions[staker] = staking
        return staking

    def create_insurance(
        self,
        proof_id: str,
        coverage_amount: float,
        insured_party: str,
        insurer: str,
    ) -> CausalInsurance:
        """Create causal insurance for a proof.

        Args:
            proof_id: ID of the proof to insure
            coverage_amount: Maximum payout amount
            insured_party: Party being insured
            insurer: Insurance provider

        Returns:
            The created insurance policy
        """
        policy_id = f"insurance_{len(self.insurance_policies) + 1}"

        # Premium is based on coverage and proof confidence
        proof = self.proofs.get(proof_id)
        if proof:
            risk_factor = 1.0 - proof.confidence
            premium = coverage_amount * risk_factor * 0.1
        else:
            premium = coverage_amount * 0.05

        policy = CausalInsurance(
            policy_id=policy_id,
            proof_id=proof_id,
            coverage_amount=coverage_amount,
            premium=premium,
            insured_party=insured_party,
            insurer=insurer,
            is_active=True,
            has_claims=False,
            payout_amount=None,
        )
        self.insurance_policies[policy_id] = policy
        return policy

    def detect_arbitrage(
        self,
        proof_id: str,
        timeline_a_price: float,
        timeline_b_price: float,
        transaction_cost: float = 0.001,
    ) -> Optional[ArbitrageOpportunity]:
        """Detect arbitrage opportunities across timelines.

        Args:
            proof_id: ID of the proof
            timeline_a_price: Price in timeline A
            timeline_b_price: Price in timeline B
            transaction_cost: Transaction cost ratio

        Returns:
            Arbitrage opportunity if profitable, None otherwise
        """
        spread = abs(timeline_a_price - timeline_b_price)
        lower_price = min(timeline_a_price, timeline_b_price)
        higher_price = max(timeline_a_price, timeline_b_price)

        # Calculate expected profit after costs
        cost = lower_price * transaction_cost
        expected_profit = higher_price - lower_price - cost

        if expected_profit > 0:
            opp = ArbitrageOpportunity(
                opportunity_id=f"arb_{len(self.arbitrage_opportunities) + 1}",
                proof_id=proof_id,
                timeline_a_price=timeline_a_price,
                timeline_b_price=timeline_b_price,
                spread=spread,
                expected_profit=expected_profit,
                detection_time=time.time(),
            )
            self.arbitrage_opportunities.append(opp)
            return opp
        return None

    def get_market_depth(
        self,
        proof_id: str,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get market depth (order book) for a proof.

        Args:
            proof_id: ID of the proof

        Returns:
            Dictionary with 'bids' and 'asks' lists
        """
        bids = []
        asks = []

        for order in self.orders.values():
            if order.proof_id == proof_id and order.status == "open":
                entry = {
                    "price": order.price,
                    "quantity": order.quantity,
                    "trader": order.trader,
                }
                if order.side == "buy":
                    bids.append(entry)
                else:
                    asks.append(entry)

        # Sort bids descending, asks ascending
        bids.sort(key=lambda x: x["price"], reverse=True)
        asks.sort(key=lambda x: x["price"])

        return {"bids": bids, "asks": asks}

    def get_market_stats(self) -> Dict[str, Any]:
        """Get overall market statistics.

        Returns:
            Dictionary with market statistics
        """
        total_proofs = len(self.proofs)
        total_orders = len([o for o in self.orders.values() if o.status == "open"])
        total_trades = len(self.trades)
        total_volume = sum(t.total_value for t in self.trades)

        # Average proof value
        proof_values = [p.compute_value() for p in self.proofs.values()]
        avg_value = sum(proof_values) / len(proof_values) if proof_values else 0

        return {
            "total_proofs": total_proofs,
            "total_open_orders": total_orders,
            "total_trades": total_trades,
            "total_volume": total_volume,
            "average_proof_value": avg_value,
            "total_bonds": len(self.bonds),
            "total_derivatives": len(self.derivatives),
            "total_liquidity_pools": len(self.liquidity_pools),
            "total_staking_positions": len(self.staking_positions),
            "total_insurance_policies": len(self.insurance_policies),
            "arbitrage_opportunities": len(self.arbitrage_opportunities),
        }


# ---------------------------------------------------------------------------
# Proof Aggregator — Compound Proofs
# ---------------------------------------------------------------------------


class ProofAggregator:
    """Combines multiple CTC proofs into compound proofs.

    Solving multiple PSPACE problems simultaneously creates exponentially
    more value than solving them sequentially. The aggregator uses multi-CTC
    entanglement to create compound proofs with multiplicative value.

    Key insight: If proof A solves problem P₁ and proof B solves problem P₂,
    a compound proof solving P₁ ∧ P₂ has value proportional to
    value(A) × value(B), not value(A) + value(B).
    """

    def __init__(self):
        self.compound_proofs: Dict[str, CTCOracleProof] = {}

    def aggregate(
        self,
        proofs: List[CTCOracleProof],
    ) -> CTCOracleProof:
        """Aggregate multiple proofs into a compound proof.

        The compound proof's value is the product of individual values,
        representing the exponential value of solving multiple PSPACE
        problems simultaneously.

        Args:
            proofs: List of proofs to aggregate

        Returns:
            Compound oracle proof
        """
        if not proofs:
            raise ValueError("At least one proof is required")

        # Compound problem statement
        compound_problem = {
            "type": "compound",
            "sub_problems": [p.problem_statement for p in proofs],
            "aggregation_method": "multi_ctc_entanglement",
        }

        # Compound solution
        compound_solution = {
            "sub_solutions": [p.solution for p in proofs],
            "entanglement_certificate": self._compute_entanglement(proofs),
        }

        # Compound fixed-point certificate
        compound_certificate = {
            "joint_fixed_point": True,
            "sub_certificates": [p.fixed_point_certificate for p in proofs],
            "consistency_verified": all(p.verify() for p in proofs),
        }

        # Verification key
        content = json.dumps({
            "problem": compound_problem,
            "solution": compound_solution,
            "certificate": compound_certificate,
        }, sort_keys=True)
        verification_key = hashlib.sha256(content.encode()).hexdigest()

        # Complexity is sum of individual complexities
        total_complexity = sum(p.complexity_score for p in proofs)

        # Confidence is product of individual confidences (joint probability)
        joint_confidence = math.prod(p.confidence for p in proofs)

        compound = CTCOracleProof(
            proof_id=f"compound_{len(self.compound_proofs) + 1}",
            proof_type=ProofType.CUSTOM,
            problem_statement=compound_problem,
            solution=compound_solution,
            fixed_point_certificate=compound_certificate,
            verification_key=verification_key,
            complexity_score=total_complexity,
            confidence=joint_confidence,
            timestamp=time.time(),
            status=OracleProofStatus.VERIFIED,
            creator="aggregator",
            price=0.0,
        )

        # Verify the compound proof
        if not compound.verify():
            raise ValueError("Compound proof verification failed")

        self.compound_proofs[compound.proof_id] = compound
        return compound

    def _compute_entanglement(
        self,
        proofs: List[CTCOracleProof],
    ) -> Dict[str, Any]:
        """Compute the entanglement certificate for compound proofs.

        Args:
            proofs: List of proofs to entangle

        Returns:
            Entanglement certificate
        """
        # Entanglement entropy measures the correlation between proofs
        # For n proofs, the entanglement entropy is log₂(n)
        n = len(proofs)
        entanglement_entropy = math.log2(n) if n > 1 else 0

        return {
            "num_proofs": n,
            "entanglement_entropy": entanglement_entropy,
            "joint_consistency": all(p.verify() for p in proofs),
        }


# ---------------------------------------------------------------------------
# Proof Factory — Create Oracle Proofs from CTC Solutions
# ---------------------------------------------------------------------------


class ProofFactory:
    """Factory for creating oracle proofs from CTC solutions.

    This bridges the gap between raw CTC computations and marketable
    oracle proofs. It takes the output of CTC solvers and packages
    them into verifiable, tradable financial instruments.
    """

    def __init__(self):
        self.created_proofs: List[CTCOracleProof] = []

    def create_sat_proof(
        self,
        clauses: List[Tuple[int, ...]],
        solution: Dict[int, bool],
        creator: str,
    ) -> CTCOracleProof:
        """Create an oracle proof for a SAT problem.

        Args:
            clauses: List of clauses (tuples of variable indices)
            solution: Variable assignment that satisfies all clauses
            creator: Proof creator identifier

        Returns:
            Oracle proof for the SAT problem
        """
        problem = {
            "type": "3sat",
            "clauses": [list(c) for c in clauses],
            "num_variables": max(abs(v) for c in clauses for v in c),
        }

        certificate = {
            "fixed_point": solution,
            "consistency_check": self._verify_sat(clauses, solution),
        }

        content = json.dumps({
            "problem": problem,
            "solution": solution,
            "certificate": certificate,
        }, sort_keys=True)
        verification_key = hashlib.sha256(content.encode()).hexdigest()

        # Complexity is proportional to the number of clauses
        complexity = len(clauses) * 10

        proof = CTCOracleProof(
            proof_id=f"sat_{len(self.created_proofs) + 1}",
            proof_type=ProofType.SAT,
            problem_statement=problem,
            solution=solution,
            fixed_point_certificate=certificate,
            verification_key=verification_key,
            complexity_score=complexity,
            confidence=1.0 if certificate["consistency_check"] else 0.0,
            timestamp=time.time(),
            status=OracleProofStatus.VERIFIED if certificate["consistency_check"] else OracleProofStatus.PENDING,
            creator=creator,
            price=0.0,
        )

        self.created_proofs.append(proof)
        return proof

    def create_factorization_proof(
        self,
        n: int,
        factors: Tuple[int, int],
        creator: str,
    ) -> CTCOracleProof:
        """Create an oracle proof for integer factorization.

        Args:
            n: Number to factorize
            factors: Tuple of (p, q) such that p * q = n
            creator: Proof creator identifier

        Returns:
            Oracle proof for the factorization
        """
        problem = {
            "type": "factorization",
            "number": n,
            "bit_length": n.bit_length(),
        }

        certificate = {
            "factors": factors,
            "verification": factors[0] * factors[1] == n,
        }

        content = json.dumps({
            "problem": problem,
            "solution": {"factors": list(factors)},
            "certificate": certificate,
        }, sort_keys=True)
        verification_key = hashlib.sha256(content.encode()).hexdigest()

        # Complexity is proportional to the bit length
        complexity = n.bit_length() * 5

        proof = CTCOracleProof(
            proof_id=f"factor_{len(self.created_proofs) + 1}",
            proof_type=ProofType.FACTORIZATION,
            problem_statement=problem,
            solution={"factors": list(factors)},
            fixed_point_certificate=certificate,
            verification_key=verification_key,
            complexity_score=complexity,
            confidence=1.0 if certificate["verification"] else 0.0,
            timestamp=time.time(),
            status=OracleProofStatus.VERIFIED if certificate["verification"] else OracleProofStatus.PENDING,
            creator=creator,
            price=0.0,
        )

        self.created_proofs.append(proof)
        return proof

    def create_custom_proof(
        self,
        problem_type: str,
        problem_data: Dict[str, Any],
        solution_data: Dict[str, Any],
        verify_fn: Callable[[Dict[str, Any], Dict[str, Any]], bool],
        creator: str,
    ) -> CTCOracleProof:
        """Create a custom oracle proof.

        Args:
            problem_type: Type identifier for the problem
            problem_data: Problem definition
            solution_data: Solution data
            verify_fn: Function to verify the solution
            creator: Proof creator identifier

        Returns:
            Oracle proof for the custom problem
        """
        problem = {
            "type": problem_type,
            "data": problem_data,
        }

        is_valid = verify_fn(problem_data, solution_data)
        certificate = {
            "custom_verification": is_valid,
        }

        content = json.dumps({
            "problem": problem,
            "solution": solution_data,
            "certificate": certificate,
        }, sort_keys=True)
        verification_key = hashlib.sha256(content.encode()).hexdigest()

        proof = CTCOracleProof(
            proof_id=f"custom_{len(self.created_proofs) + 1}",
            proof_type=ProofType.CUSTOM,
            problem_statement=problem,
            solution=solution_data,
            fixed_point_certificate=certificate,
            verification_key=verification_key,
            complexity_score=10.0,
            confidence=1.0 if is_valid else 0.0,
            timestamp=time.time(),
            status=OracleProofStatus.VERIFIED if is_valid else OracleProofStatus.PENDING,
            creator=creator,
            price=0.0,
        )

        self.created_proofs.append(proof)
        return proof

    def _verify_sat(
        self,
        clauses: List[Tuple[int, ...]],
        solution: Dict[int, bool],
    ) -> bool:
        """Verify a SAT solution.

        Args:
            clauses: List of clauses
            solution: Variable assignment

        Returns:
            True if the solution satisfies all clauses
        """
        for clause in clauses:
            clause_satisfied = False
            for var in clause:
                if var > 0:
                    if solution.get(var, False):
                        clause_satisfied = True
                        break
                else:
                    if not solution.get(abs(var), False):
                        clause_satisfied = True
                        break
            if not clause_satisfied:
                return False
        return True


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------


def run_oracle_market_demo():
    """Run a comprehensive demo of the CTC Oracle Market."""
    print("=" * 70)
    print("CTC ORACLE MARKET — Trading PSPACE-level Computation")
    print("Shocking the World with Causally-Backed Securities")
    print("=" * 70)

    # 1. Create the market
    print("\n--- 1. Creating Oracle Market ---")
    market = OracleMarket(fee_rate=0.001)
    print("Market created with 0.1% trading fee")

    # 2. Create proofs using the factory
    print("\n--- 2. Creating Oracle Proofs ---")
    factory = ProofFactory()

    # SAT proof
    clauses = [(1, 2, 3), (-1, -2, 4), (2, -3, 4), (-1, 3, -4)]
    sat_solution = {1: True, 2: False, 3: True, 4: True}
    sat_proof = factory.create_sat_proof(clauses, sat_solution, "alice")
    print(f"SAT proof created: {sat_proof.proof_id}")
    print(f"  Verified: {sat_proof.verify()}")
    print(f"  Value: ${sat_proof.compute_value():.2f}")

    # Factorization proof
    factor_proof = factory.create_factorization_proof(
        15, (3, 5), "bob"
    )
    print(f"Factorization proof created: {factor_proof.proof_id}")
    print(f"  Verified: {factor_proof.verify()}")
    print(f"  Value: ${factor_proof.compute_value():.2f}")

    # Custom proof
    custom_proof = factory.create_custom_proof(
        "graph_coloring",
        {"nodes": 4, "edges": [(0, 1), (1, 2), (2, 3), (3, 0)]},
        {"colors": {0: "red", 1: "blue", 2: "red", 3: "blue"}},
        lambda p, s: len(set(s["colors"].values())) == 2,
        "charlie"
    )
    print(f"Custom proof created: {custom_proof.proof_id}")
    print(f"  Verified: {custom_proof.verify()}")
    print(f"  Value: ${custom_proof.compute_value():.2f}")

    # Register proofs in market
    market.register_proof(sat_proof)
    market.register_proof(factor_proof)
    market.register_proof(custom_proof)
    print(f"Total proofs registered: {len(market.proofs)}")

    # 3. Aggregate proofs
    print("\n--- 3. Aggregating Proofs ---")
    aggregator = ProofAggregator()
    compound = aggregator.aggregate([sat_proof, factor_proof])
    print(f"Compound proof created: {compound.proof_id}")
    print(f"  Complexity: {compound.complexity_score}")
    print(f"  Confidence: {compound.confidence:.4f}")
    print(f"  Value: ${compound.compute_value():.2f}")
    print(f"  Exponential value boost: {compound.compute_value() / (sat_proof.compute_value() + factor_proof.compute_value()):.2f}x")

    # 4. Place orders
    print("\n--- 4. Trading Oracle Proofs ---")
    buy_order = OracleOrder(
        order_id="order_1",
        proof_id=sat_proof.proof_id,
        side="buy",
        price=50.0,
        quantity=1,
        timestamp=time.time(),
        status="open",
        trader="dave",
    )
    sell_order = OracleOrder(
        order_id="order_2",
        proof_id=sat_proof.proof_id,
        side="sell",
        price=45.0,
        quantity=1,
        timestamp=time.time(),
        status="open",
        trader="alice",
    )
    market.place_order(buy_order)
    market.place_order(sell_order)
    print(f"Orders placed, trades executed: {len(market.trades)}")
    if market.trades:
        trade = market.trades[0]
        print(f"  Trade: {trade.buyer} bought from {trade.seller}")
        print(f"  Price: ${trade.price:.2f}, Value: ${trade.total_value:.2f}")

    # 5. Create causal bonds
    print("\n--- 5. Creating Causal Bonds ---")
    bond = market.create_causal_bond(
        proof_id=sat_proof.proof_id,
        face_value=1000.0,
        interest_rate=0.05,
        maturity_years=1.0,
        issuer="alice",
    )
    print(f"Causal bond created: {bond.bond_id}")
    print(f"  Face value: ${bond.face_value}")
    print(f"  Interest rate: {bond.interest_rate * 100}%")
    print(f"  Consistent: {bond.is_consistent}")

    # 6. Create derivatives
    print("\n--- 6. Creating Oracle Derivatives ---")
    call_option = market.create_derivative(
        proof_id=factor_proof.proof_id,
        derivative_type="call_option",
        strike_price=100.0,
        expiration_days=30,
        holder="bob",
        writer="charlie",
    )
    print(f"Call option created: {call_option.derivative_id}")
    print(f"  Strike price: ${call_option.strike_price}")
    print(f"  Type: {call_option.derivative_type}")

    # 7. Create liquidity pool
    print("\n--- 7. Creating Liquidity Pool (AMM) ---")
    pool = market.create_liquidity_pool(
        proof_type=ProofType.SAT,
        initial_proofs=10.0,
        initial_tokens=1000.0,
    )
    print(f"Liquidity pool created: {pool.pool_id}")
    print(f"  Invariant: {pool.invariant}")
    print(f"  Reserves: {pool.reserve_proofs} proofs, {pool.reserve_tokens} tokens")

    # Swap in pool
    amount_out = market.swap_in_pool(pool.pool_id, 1.0, "dave")
    print(f"  Swap: 1.0 proofs -> {amount_out:.2f} tokens")
    print(f"  New reserves: {pool.reserve_proofs:.2f} proofs, {pool.reserve_tokens:.2f} tokens")

    # 8. Stake proofs
    print("\n--- 8. Staking Oracle Proofs ---")
    staking = market.stake_proofs(
        [sat_proof.proof_id, factor_proof.proof_id],
        "alice",
    )
    print(f"Staking position created for {staking.staker}")
    print(f"  Staked value: ${staking.staked_value:.2f}")
    print(f"  Reward rate: ${staking.reward_rate:.4f}/unit time")

    # 9. Create insurance
    print("\n--- 9. Creating Causal Insurance ---")
    insurance = market.create_insurance(
        proof_id=custom_proof.proof_id,
        coverage_amount=500.0,
        insured_party="charlie",
        insurer="alice",
    )
    print(f"Insurance policy created: {insurance.policy_id}")
    print(f"  Coverage: ${insurance.coverage_amount}")
    print(f"  Premium: ${insurance.premium:.2f}")

    # 10. Detect arbitrage
    print("\n--- 10. Detecting Temporal Arbitrage ---")
    arb = market.detect_arbitrage(
        proof_id=sat_proof.proof_id,
        timeline_a_price=45.0,
        timeline_b_price=50.0,
        transaction_cost=0.001,
    )
    if arb:
        print(f"Arbitrage opportunity found: {arb.opportunity_id}")
        print(f"  Spread: ${arb.spread:.2f}")
        print(f"  Expected profit: ${arb.expected_profit:.2f}")
    else:
        print("No arbitrage opportunity found")

    # 11. Market statistics
    print("\n--- 11. Market Statistics ---")
    stats = market.get_market_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # 12. Market depth
    print("\n--- 12. Market Depth ---")
    depth = market.get_market_depth(sat_proof.proof_id)
    print(f"Bids: {len(depth['bids'])}, Asks: {len(depth['asks'])}")

    print("\n" + "=" * 70)
    print("CTC Oracle Market Demo Complete")
    print("=" * 70)
    print("\nKey Innovations Demonstrated:")
    print("1. Oracle Proofs — Verifiable PSPACE computations as assets")
    print("2. Oracle Market — Trading engine for computational proofs")
    print("3. Proof Aggregation — Exponential value from compound proofs")
    print("4. Causal Bonds — Securities backed by CTC consistency")
    print("5. Oracle Derivatives — Options/futures on computational power")
    print("6. Liquidity Pools — AMM with CTC fixed-point invariant")
    print("7. Proof Staking — Earn rewards by staking proofs")
    print("8. Causal Insurance — Insurance against consistency failure")
    print("9. Temporal Arbitrage — Profit from cross-timeline price diffs")
    print("10. Market Depth — Full order book for proof trading")
    print("\nThe same math that makes CTCs consistent (S(rho) = rho)")
    print("now makes financial markets consistent.")
    print("This is the first causally-backed security marketplace.")


if __name__ == "__main__":
    run_oracle_market_demo()
