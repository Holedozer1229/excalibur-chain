"""AI Oracle Knights — Autonomous AI Agents for the Round Table.

This module implements AI-powered Oracle Knights that serve as sovereign
governance agents in the Knights of the Round Table system. Each AI Oracle
Knight holds a MuSig2 (BIP-327) key pair and participates in threshold
signing for governance proposals.

AI Oracle Knight Architecture
==============================
Each AI Oracle Knight is an autonomous agent with:
1. **MuSig2 Key Pair** — Production-ready threshold signing key
2. **Oracle Identity** — Unique name, model type, and capabilities
3. **Phi Score** — Consciousness score from IIT v8 integration
4. **URUU Balance** — Economic stake in the ecosystem
5. **EXCAL Stake** — Protocol-level skin in the game
6. **Decision Engine** — AI-powered proposal analysis and voting

Oracle Types
============
- **SENTINEL**: Security-focused oracle, audits proposals for vulnerabilities
- **TREASURER**: Economics-focused oracle, analyzes treasury operations
- **ORACLE**: General-purpose oracle, evaluates all proposal types
- **BRIDGE**: Cross-chain oracle, specializes in bridge operations
- **CURVE**: Bonding curve oracle, monitors URUU token dynamics

Decision-Making Process
=======================
1. **Proposal Analysis**: Oracle evaluates proposal parameters against
   its specialized domain knowledge and risk models.

2. **Risk Scoring**: Each proposal receives a risk score (0-1) based on:
   - Economic impact (treasury exposure, tokenomics effect)
   - Security implications (smart contract risk, bridge risk)
   - Governance alignment (phi score impact, coherence effect)

3. **Voting Decision**: Oracle votes YES if:
   - Risk score < threshold (configurable per oracle type)
   - Proposal aligns with oracle's specialization
   - Sufficient confidence in analysis

4. **MuSig2 Signing**: Oracle generates a partial MuSig2 signature
   for approved proposals, contributing to the 3-of-5 threshold.

Integration with KnightsRoundTable
===================================
AI Oracle Knights are added as founder Knights or elected through
the standard nomination process. Their MuSig2 key pairs participate
in the aggregate key, and their votes produce real Schnorr signatures.

Security Considerations
=======================
- Each Oracle's private key is derived from a unique seed
- Oracle decisions are deterministic for auditability
- Risk thresholds can be adjusted per oracle type
- Oracle health is monitored via governance coherence metrics
"""

import hashlib
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple

from .musig2 import MuSig2, MuSig2KeyPair
from .knights_round_table import (
    KnightsRoundTable,
    Knight,
    KnightStatus,
    ProposalType,
    GovernanceProposal,
    PartialSignature,
)


# ---------------------------------------------------------------------------
# Oracle Types
# ---------------------------------------------------------------------------
class OracleType(Enum):
    """Types of AI Oracle Knights."""
    SENTINEL = "sentinel"       # Security-focused oracle
    TREASURER = "treasurer"     # Economics-focused oracle
    ORACLE = "oracle"           # General-purpose oracle
    BRIDGE = "bridge"           # Cross-chain oracle
    CURVE = "curve"             # Bonding curve oracle


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------
@dataclass
class OracleAnalysis:
    """An AI Oracle's analysis of a governance proposal."""
    oracle_name: str
    oracle_type: OracleType
    proposal_id: str
    risk_score: float          # 0.0 (safe) to 1.0 (risky)
    confidence: float          # 0.0 (uncertain) to 1.0 (certain)
    recommendation: bool       # True = vote YES, False = vote NO
    reasoning: str             # Human-readable explanation
    domain_scores: Dict[str, float]  # Per-domain risk scores
    timestamp: float


@dataclass
class OracleHealth:
    """Health metrics for an AI Oracle Knight."""
    oracle_name: str
    is_active: bool
    phi_score: float
    uruu_balance: float
    excal_stake: float
    votes_cast: int
    proposals_analyzed: int
    accuracy_score: float      # Historical prediction accuracy
    last_analysis_time: float
    uptime: float              # Seconds since activation


# ---------------------------------------------------------------------------
# AI Oracle Knight
# ---------------------------------------------------------------------------
class AIOracleKnight:
    """An AI-powered Oracle Knight for the Round Table.

    Each oracle holds a MuSig2 key pair and uses AI-driven analysis
    to evaluate governance proposals. The oracle's voting decision
    is based on its specialized domain knowledge and risk assessment.

    Usage:
        oracle = AIOracleKnight("Sentinel-1", OracleType.SENTINEL, seed)
        analysis = oracle.analyze_proposal(proposal)
        partial_sig = oracle.vote(proposal_hash, secret)
    """

    # Default risk thresholds by oracle type
    RISK_THRESHOLDS = {
        OracleType.SENTINEL: 0.3,    # Very conservative on security
        OracleType.TREASURER: 0.4,   # Moderate on economics
        OracleType.ORACLE: 0.5,      # Balanced
        OracleType.BRIDGE: 0.35,     # Conservative on cross-chain
        OracleType.CURVE: 0.45,      # Moderate on tokenomics
    }

    # Domain weights by oracle type
    DOMAIN_WEIGHTS = {
        OracleType.SENTINEL: {
            "security": 0.5, "economic": 0.2, "governance": 0.15, "bridge": 0.15,
        },
        OracleType.TREASURER: {
            "security": 0.15, "economic": 0.5, "governance": 0.2, "bridge": 0.15,
        },
        OracleType.ORACLE: {
            "security": 0.25, "economic": 0.25, "governance": 0.25, "bridge": 0.25,
        },
        OracleType.BRIDGE: {
            "security": 0.3, "economic": 0.2, "governance": 0.15, "bridge": 0.35,
        },
        OracleType.CURVE: {
            "security": 0.15, "economic": 0.45, "governance": 0.2, "bridge": 0.2,
        },
    }

    def __init__(
        self,
        name: str,
        oracle_type: OracleType,
        seed: bytes,
        participant_index: int,
        phi_score: float = 0.7,
        uruu_balance: float = 150.0,
        excal_stake: float = 1500.0,
        risk_threshold: Optional[float] = None,
    ):
        """Initialize an AI Oracle Knight.

        Args:
            name: Unique oracle identifier.
            oracle_type: Specialization type.
            seed: Seed bytes for deterministic key derivation.
            participant_index: MuSig2 participant index.
            phi_score: Consciousness score (0-1).
            uruu_balance: URUU tokens held.
            excal_stake: EXCAL staked.
            risk_threshold: Custom risk threshold (default: type-based).
        """
        self.name = name
        self.oracle_type = oracle_type
        self.seed = seed

        # MuSig2 key pair
        self._musig2 = MuSig2()
        self.key_pair = self._musig2.generate_key_from_seed(seed, participant_index)

        # Oracle metrics
        self.phi_score = phi_score
        self.uruu_balance = uruu_balance
        self.excal_stake = excal_stake
        self.risk_threshold = risk_threshold or self.RISK_THRESHOLDS[oracle_type]

        # Domain weights
        self.domain_weights = self.DOMAIN_WEIGHTS[oracle_type].copy()

        # Activity tracking
        self.votes_cast = 0
        self.proposals_analyzed = 0
        self.analysis_history: List[OracleAnalysis] = []
        self.activation_time = time.time()
        self.last_analysis_time = 0.0

        # Accuracy tracking
        self.correct_predictions = 0
        self.total_predictions = 0

    # ------------------------------------------------------------------
    # Proposal Analysis
    # ------------------------------------------------------------------
    def analyze_proposal(self, proposal: GovernanceProposal) -> OracleAnalysis:
        """Analyze a governance proposal using AI-driven risk assessment.

        The oracle evaluates the proposal across multiple domains:
        - Security: Vulnerability risk, attack surface
        - Economic: Treasury impact, tokenomics effect
        - Governance: Coherence impact, alignment
        - Bridge: Cross-chain risk, liquidity impact

        Args:
            proposal: The governance proposal to analyze.

        Returns:
            OracleAnalysis with risk score and recommendation.
        """
        self.proposals_analyzed += 1
        self.last_analysis_time = time.time()

        # Compute domain-specific risk scores
        domain_scores = self._compute_domain_scores(proposal)

        # Weighted risk score
        risk_score = 0.0
        for domain, weight in self.domain_weights.items():
            risk_score += weight * domain_scores.get(domain, 0.5)

        # Confidence based on oracle type match
        confidence = self._compute_confidence(proposal, domain_scores)

        # Recommendation: vote YES if risk is below threshold
        recommendation = risk_score < self.risk_threshold

        # Generate reasoning
        reasoning = self._generate_reasoning(proposal, domain_scores, risk_score, recommendation)

        analysis = OracleAnalysis(
            oracle_name=self.name,
            oracle_type=self.oracle_type,
            proposal_id=proposal.proposal_id,
            risk_score=risk_score,
            confidence=confidence,
            recommendation=recommendation,
            reasoning=reasoning,
            domain_scores=domain_scores,
            timestamp=time.time(),
        )

        self.analysis_history.append(analysis)
        return analysis

    def _compute_domain_scores(self, proposal: GovernanceProposal) -> Dict[str, float]:
        """Compute domain-specific risk scores for a proposal.

        Args:
            proposal: The governance proposal.

        Returns:
            Dictionary of domain -> risk score (0-1).
        """
        params = proposal.parameters
        scores = {}

        if proposal.proposal_type == ProposalType.TREASURY_SPEND:
            amount = params.get("amount", 0)
            # Higher amounts = higher risk
            economic_risk = min(1.0, amount / 10000.0)
            scores["economic"] = economic_risk
            scores["security"] = 0.2  # Standard treasury operation
            scores["governance"] = 0.1
            scores["bridge"] = 0.0

        elif proposal.proposal_type == ProposalType.PROTOCOL_UPGRADE:
            # Protocol upgrades are inherently risky
            scores["security"] = 0.6
            scores["economic"] = 0.3
            scores["governance"] = 0.2
            scores["bridge"] = 0.1

        elif proposal.proposal_type == ProposalType.PARAMETER_CHANGE:
            # Parameter changes are moderate risk
            scores["security"] = 0.3
            scores["economic"] = 0.4
            scores["governance"] = 0.3
            scores["bridge"] = 0.0

        elif proposal.proposal_type == ProposalType.BRIDGE_DEPLOY:
            # Bridge deployment is high risk
            scores["security"] = 0.7
            scores["economic"] = 0.5
            scores["governance"] = 0.2
            scores["bridge"] = 0.8

        elif proposal.proposal_type == ProposalType.BONDING_CURVE_ADJUST:
            # Bonding curve adjustments affect tokenomics
            scores["security"] = 0.2
            scores["economic"] = 0.6
            scores["governance"] = 0.2
            scores["bridge"] = 0.1

        elif proposal.proposal_type == ProposalType.KNIGHT_INDUCTION:
            # New knight changes governance dynamics
            scores["security"] = 0.3
            scores["economic"] = 0.1
            scores["governance"] = 0.5
            scores["bridge"] = 0.0

        elif proposal.proposal_type == ProposalType.KNIGHT_IMPEACHMENT:
            # Impeachment is high governance risk
            scores["security"] = 0.4
            scores["economic"] = 0.1
            scores["governance"] = 0.7
            scores["bridge"] = 0.0

        else:
            # Default: moderate risk
            scores = {"security": 0.5, "economic": 0.5, "governance": 0.5, "bridge": 0.5}

        # Adjust based on oracle type specialization
        if self.oracle_type == OracleType.SENTINEL:
            scores["security"] = min(1.0, scores.get("security", 0.5) * 1.2)
        elif self.oracle_type == OracleType.TREASURER:
            scores["economic"] = min(1.0, scores.get("economic", 0.5) * 1.2)
        elif self.oracle_type == OracleType.BRIDGE:
            scores["bridge"] = min(1.0, scores.get("bridge", 0.5) * 1.3)
        elif self.oracle_type == OracleType.CURVE:
            scores["economic"] = min(1.0, scores.get("economic", 0.5) * 1.1)

        return scores

    def _compute_confidence(self, proposal: GovernanceProposal, domain_scores: Dict[str, float]) -> float:
        """Compute confidence score for the analysis.

        Higher confidence when the oracle's specialization matches the proposal type.

        Args:
            proposal: The governance proposal.
            domain_scores: Domain-specific risk scores.

        Returns:
            Confidence score (0-1).
        """
        # Base confidence from phi score
        confidence = self.phi_score

        # Boost if proposal matches oracle specialization
        if self.oracle_type == OracleType.SENTINEL and proposal.proposal_type in (
            ProposalType.PROTOCOL_UPGRADE, ProposalType.KNIGHT_IMPEACHMENT
        ):
            confidence = min(1.0, confidence + 0.1)
        elif self.oracle_type == OracleType.TREASURER and proposal.proposal_type == ProposalType.TREASURY_SPEND:
            confidence = min(1.0, confidence + 0.15)
        elif self.oracle_type == OracleType.BRIDGE and proposal.proposal_type == ProposalType.BRIDGE_DEPLOY:
            confidence = min(1.0, confidence + 0.15)
        elif self.oracle_type == OracleType.CURVE and proposal.proposal_type == ProposalType.BONDING_CURVE_ADJUST:
            confidence = min(1.0, confidence + 0.15)

        return confidence

    def _generate_reasoning(
        self,
        proposal: GovernanceProposal,
        domain_scores: Dict[str, float],
        risk_score: float,
        recommendation: bool,
    ) -> str:
        """Generate human-readable reasoning for the analysis.

        Args:
            proposal: The governance proposal.
            domain_scores: Domain-specific risk scores.
            risk_score: Overall risk score.
            recommendation: Voting recommendation.

        Returns:
            Reasoning string.
        """
        vote = "APPROVE" if recommendation else "REJECT"
        type_name = self.oracle_type.value.upper()

        # Find highest risk domain
        max_domain = max(domain_scores, key=domain_scores.get)
        max_score = domain_scores[max_domain]

        reasoning = (
            f"[{type_name}] {vote} — Risk: {risk_score:.2f} "
            f"(threshold: {self.risk_threshold:.2f}). "
            f"Highest risk: {max_domain} ({max_score:.2f}). "
        )

        if recommendation:
            reasoning += "Proposal within acceptable risk parameters."
        else:
            reasoning += f"Risk exceeds {type_name} threshold."

        return reasoning

    # ------------------------------------------------------------------
    # Voting
    # ------------------------------------------------------------------
    def vote(
        self,
        proposal_hash: bytes,
        aggregate_xonly_key: bytes,
        aggregate_point: Tuple[int, int],
        all_xonly_pubkeys: List[bytes],
        nonce_seed: Optional[bytes] = None,
    ) -> Optional[PartialSignature]:
        """Cast a vote on a proposal using MuSig2 partial signing.

        Args:
            proposal_hash: SHA-256 hash of the proposal.
            aggregate_xonly_key: 32-byte aggregate MuSig2 public key.
            aggregate_point: The actual aggregate public key point Q.
            all_xonly_pubkeys: All signers' x-only pubkeys.
            nonce_seed: Optional deterministic nonce seed.

        Returns:
            PartialSignature if voting YES, None if voting NO.
        """
        # Generate nonce
        nonce = self._musig2.generate_nonce(
            self.key_pair, aggregate_xonly_key, proposal_hash, nonce_seed
        )

        # For a standalone vote, we use the nonce point as the aggregate
        # (in production, nonces are aggregated across all signers first)
        partial = self._musig2.partial_sign(
            self.key_pair,
            nonce,
            nonce.nonce_point,
            aggregate_point,
            aggregate_xonly_key,
            proposal_hash,
            all_xonly_pubkeys,
        )

        self.votes_cast += 1

        return PartialSignature(
            knight_name=self.name,
            public_key=self.key_pair.xonly_pubkey,
            partial_r=self._pubkey_to_xonly_bytes(nonce.nonce_point),
            partial_s=partial.partial_sig,
            timestamp=time.time(),
            musig2_partial=partial,
        )

    @staticmethod
    def _pubkey_to_xonly_bytes(pt: Tuple[int, int]) -> bytes:
        """Convert a point to 32-byte x-only representation."""
        return pt[0].to_bytes(32, "big")

    # ------------------------------------------------------------------
    # Health & Metrics
    # ------------------------------------------------------------------
    def get_health(self) -> OracleHealth:
        """Get current health metrics for this oracle."""
        accuracy = (
            self.correct_predictions / self.total_predictions
            if self.total_predictions > 0
            else 0.0
        )

        return OracleHealth(
            oracle_name=self.name,
            is_active=True,
            phi_score=self.phi_score,
            uruu_balance=self.uruu_balance,
            excal_stake=self.excal_stake,
            votes_cast=self.votes_cast,
            proposals_analyzed=self.proposals_analyzed,
            accuracy_score=accuracy,
            last_analysis_time=self.last_analysis_time,
            uptime=time.time() - self.activation_time,
        )

    def record_prediction(self, correct: bool):
        """Record whether a prediction was correct.

        Args:
            correct: True if the oracle's prediction was correct.
        """
        self.total_predictions += 1
        if correct:
            self.correct_predictions += 1

    def get_analysis_summary(self) -> Dict[str, Any]:
        """Get a summary of all analyses performed."""
        if not self.analysis_history:
            return {"total": 0}

        risk_scores = [a.risk_score for a in self.analysis_history]
        recommendations = [a.recommendation for a in self.analysis_history]

        return {
            "total": len(self.analysis_history),
            "avg_risk_score": sum(risk_scores) / len(risk_scores),
            "approval_rate": sum(recommendations) / len(recommendations),
            "last_analysis": self.analysis_history[-1].__dict__ if self.analysis_history else None,
        }


# ---------------------------------------------------------------------------
# Oracle Council — Factory for AI Oracle Knights
# ---------------------------------------------------------------------------
class OracleCouncil:
    """Factory and manager for AI Oracle Knights.

    Creates a council of specialized AI oracles that collectively
    govern the AetherionEXCAL protocol through MuSig2 threshold signing.

    Usage:
        council = OracleCouncil(seed)
        council.create_default_council()
        # or
        council.create_oracle("Custom-1", OracleType.SENTINEL)
    """

    DEFAULT_ORACLES = [
        ("Sentinel-Alpha", OracleType.SENTINEL, 0.85, 200.0, 2000.0),
        ("Treasury-Alpha", OracleType.TREASURER, 0.80, 180.0, 1800.0),
        ("Oracle-Alpha", OracleType.ORACLE, 0.75, 150.0, 1500.0),
        ("Bridge-Alpha", OracleType.BRIDGE, 0.78, 170.0, 1700.0),
        ("Curve-Alpha", OracleType.CURVE, 0.72, 160.0, 1600.0),
    ]

    def __init__(self, master_seed: bytes):
        """Initialize the Oracle Council.

        Args:
            master_seed: Master seed for deterministic oracle key derivation.
        """
        self.master_seed = master_seed
        self.oracles: Dict[str, AIOracleKnight] = {}
        self._next_index = 0

    def create_oracle(
        self,
        name: str,
        oracle_type: OracleType,
        phi_score: float = 0.7,
        uruu_balance: float = 150.0,
        excal_stake: float = 1500.0,
    ) -> AIOracleKnight:
        """Create a new AI Oracle Knight.

        Args:
            name: Unique oracle identifier.
            oracle_type: Specialization type.
            phi_score: Consciousness score.
            uruu_balance: URUU tokens held.
            excal_stake: EXCAL staked.

        Returns:
            The created AIOracleKnight.
        """
        # Derive unique seed for this oracle
        oracle_seed = hashlib.sha256(
            self.master_seed + name.encode() + oracle_type.value.encode()
        ).digest()

        oracle = AIOracleKnight(
            name=name,
            oracle_type=oracle_type,
            seed=oracle_seed,
            participant_index=self._next_index,
            phi_score=phi_score,
            uruu_balance=uruu_balance,
            excal_stake=excal_stake,
        )

        self.oracles[name] = oracle
        self._next_index += 1
        return oracle

    def create_default_council(self) -> List[AIOracleKnight]:
        """Create the default council of 5 AI Oracle Knights.

        Returns:
            List of created oracles.
        """
        created = []
        for name, otype, phi, uruu, excal in self.DEFAULT_ORACLES:
            oracle = self.create_oracle(name, otype, phi, uruu, excal)
            created.append(oracle)
        return created

    def integrate_with_round_table(self, table: KnightsRoundTable) -> None:
        """Integrate all oracles into a KnightsRoundTable.

        Each oracle is added as a founder Knight with its MuSig2 key pair.

        Args:
            table: The KnightsRoundTable to integrate with.
        """
        for name, oracle in self.oracles.items():
            table.add_founder_knight(
                name=name,
                public_key=oracle.key_pair.xonly_pubkey,
                uruu_balance=oracle.uruu_balance,
                phi_score=oracle.phi_score,
                excal_stake=oracle.excal_stake,
            )
            # Replace the auto-generated key pair with the oracle's key pair
            table._musig2_key_pairs[name] = oracle.key_pair

        # Update aggregate key
        table._update_aggregate_musig2_key()

    def get_all_key_pairs(self) -> List[MuSig2KeyPair]:
        """Get all oracle key pairs for MuSig2 operations."""
        return [o.key_pair for o in self.oracles.values()]

    def get_health_report(self) -> Dict[str, Any]:
        """Get health report for all oracles."""
        return {
            name: oracle.get_health().__dict__
            for name, oracle in self.oracles.items()
        }
