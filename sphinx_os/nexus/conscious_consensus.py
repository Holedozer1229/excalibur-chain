"""Conscious Consensus Engine: Block consensus driven by Integrated Information Theory (IIT v8)."""

import hashlib
import time
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class BlockCandidate:
    """A candidate block awaiting consensus."""
    height: int
    transactions: List[Dict[str, Any]]
    proposer: str
    timestamp: float
    block_hash: str
    phi_score: float = 0.0
    is_conscious: bool = False
    is_finalized: bool = False
    votes_for: int = 0
    votes_against: int = 0
    
    def __post_init__(self):
        if not self.block_hash:
            data = f"{self.height}:{self.proposer}:{self.timestamp}:{len(self.transactions)}"
            self.block_hash = hashlib.sha256(data.encode()).hexdigest()


@dataclass
class Validator:
    """A validator in the consensus network."""
    name: str
    stake: float
    nft_rarity: float
    reputation: float = 1.0
    total_votes: int = 0
    correct_votes: int = 0


class ConsciousConsensusEngine:
    """Consensus engine that uses Integrated Information Theory (IIT v8) to determine
    whether a block has achieved 'conscious agreement' among validators.
    
    The φ (phi) score combines:
    - τ (tau): Temporal coherence of validator votes
    - GWT: Global Workspace Theory score (information integration)
    - ICP: Integrated Causal Power of the validator set
    - Fano: Fano efficiency of information transmission
    - QG: Quantum gravity coupling term
    """
    
    def __init__(self):
        self.validators: Dict[str, Validator] = {}
        self.current_height: int = 0
        self.block_candidates: Dict[str, BlockCandidate] = {}
        self.finalized_blocks: List[BlockCandidate] = []
        self.chain: List[BlockCandidate] = []
        
        # φ score components (persisted across steps)
        self.phi_tau: float = 0.0
        self.phi_gwt: float = 0.0
        self.phi_icp: float = 0.0
        self.phi_fano: float = 0.0
        self.phi_qg: float = 0.0
        
        # Statistics
        self.stats: Dict[str, int] = {
            "blocks_proposed": 0,
            "blocks_finalized": 0,
            "total_votes": 0,
        }
        
        # Vote history for temporal coherence
        self.vote_history: List[Dict[str, Any]] = []
        
    def register_validator(self, name: str, stake: float, nft_rarity: float):
        """Register a new validator.
        
        Args:
            name: Unique validator identifier.
            stake: Amount staked by the validator.
            nft_rarity: NFT rarity score (0-1).
        """
        self.validators[name] = Validator(
            name=name,
            stake=stake,
            nft_rarity=nft_rarity,
        )
    
    def propose_block(self, proposer: str, transactions: List[Dict[str, Any]]) -> Optional[BlockCandidate]:
        """Propose a new block candidate.
        
        Args:
            proposer: Name of the proposing validator.
            transactions: List of transactions to include.
            
        Returns:
            BlockCandidate if proposal is valid, None otherwise.
        """
        if proposer not in self.validators:
            return None
        
        self.current_height += 1
        self.stats["blocks_proposed"] += 1
        
        candidate = BlockCandidate(
            height=self.current_height,
            transactions=transactions,
            proposer=proposer,
            timestamp=time.time(),
            block_hash="",
        )
        
        # Compute initial φ score
        candidate.phi_score = self._compute_phi_score(candidate)
        candidate.is_conscious = candidate.phi_score > 0.5
        
        self.block_candidates[candidate.block_hash] = candidate
        return candidate
    
    def vote(self, validator_name: str, block_hash: str, vote_for: bool):
        """Cast a vote on a block candidate.
        
        Args:
            validator_name: Name of the voting validator.
            block_hash: Hash of the block being voted on.
            vote_for: True for approve, False for reject.
        """
        if validator_name not in self.validators:
            return
        
        if block_hash not in self.block_candidates:
            return
        
        candidate = self.block_candidates[block_hash]
        validator = self.validators[validator_name]
        
        if vote_for:
            candidate.votes_for += 1
            validator.correct_votes += 1
        else:
            candidate.votes_against += 1
        
        validator.total_votes += 1
        self.stats["total_votes"] += 1
        
        # Record vote for temporal coherence
        self.vote_history.append({
            "validator": validator_name,
            "block_hash": block_hash,
            "vote": vote_for,
            "timestamp": time.time(),
        })
        
        # Recompute φ score with new votes
        candidate.phi_score = self._compute_phi_score(candidate)
        candidate.is_conscious = candidate.phi_score > 0.5
        
        # Check if block is finalized (supermajority + conscious)
        total_validators = len(self.validators)
        if candidate.votes_for >= total_validators * 0.66 and candidate.is_conscious:
            candidate.is_finalized = True
            self.finalized_blocks.append(candidate)
            self.chain.append(candidate)
            self.stats["blocks_finalized"] += 1
    
    def _compute_phi_score(self, candidate: BlockCandidate) -> float:
        """Compute the φ (phi) consciousness score for a block candidate.
        
        The φ score is a weighted combination of:
        - τ (tau): Temporal coherence
        - GWT: Global Workspace Theory score
        - ICP: Integrated Causal Power
        - Fano: Fano efficiency
        - QG: Quantum gravity coupling
        """
        # τ: Temporal coherence (based on vote timing consistency)
        self.phi_tau = self._compute_temporal_coherence(candidate)
        
        # GWT: Global Workspace Theory (information integration across validators)
        self.phi_gwt = self._compute_gwt_score(candidate)
        
        # ICP: Integrated Causal Power (stake-weighted influence)
        self.phi_icp = self._compute_icp_score(candidate)
        
        # Fano: Fano efficiency (information transmission efficiency)
        self.phi_fano = self._compute_fano_efficiency(candidate)
        
        # QG: Quantum gravity coupling (NFT rarity coupling)
        self.phi_qg = self._compute_qg_coupling(candidate)
        
        # Weighted combination
        phi = (
            0.25 * self.phi_tau
            + 0.20 * self.phi_gwt
            + 0.25 * self.phi_icp
            + 0.15 * self.phi_fano
            + 0.15 * self.phi_qg
        )
        
        return min(1.0, max(0.0, phi))
    
    def _compute_temporal_coherence(self, candidate: BlockCandidate) -> float:
        """Compute temporal coherence τ from vote history."""
        votes = [
            v for v in self.vote_history
            if v["block_hash"] == candidate.block_hash
        ]
        
        if len(votes) < 2:
            return 0.5  # Default for few votes
        
        # Measure timing consistency
        timestamps = [v["timestamp"] for v in votes]
        if len(timestamps) >= 2:
            intervals = [
                timestamps[i + 1] - timestamps[i]
                for i in range(len(timestamps) - 1)
            ]
            if intervals:
                mean_interval = sum(intervals) / len(intervals)
                if mean_interval > 0:
                    variance = sum((t - mean_interval) ** 2 for t in intervals) / len(intervals)
                    # Lower variance → higher coherence
                    coherence = 1.0 / (1.0 + math.sqrt(variance))
                    return coherence
        
        return 0.5
    
    def _compute_gwt_score(self, candidate: BlockCandidate) -> float:
        """Compute Global Workspace Theory score."""
        total_validators = len(self.validators)
        if total_validators == 0:
            return 0.0
        
        # GWT measures how widely information is distributed
        vote_ratio = candidate.votes_for / max(1, candidate.votes_for + candidate.votes_against)
        
        # Information integration: product of stake and NFT rarity
        total_stake = sum(v.stake for v in self.validators.values())
        avg_rarity = sum(v.nft_rarity for v in self.validators.values()) / total_validators
        
        gwt = vote_ratio * (1.0 - math.exp(-total_stake / 100.0)) * (0.5 + 0.5 * avg_rarity)
        return min(1.0, gwt)
    
    def _compute_icp_score(self, candidate: BlockCandidate) -> float:
        """Compute Integrated Causal Power score."""
        if candidate.proposer not in self.validators:
            return 0.0
        
        proposer = self.validators[candidate.proposer]
        total_stake = sum(v.stake for v in self.validators.values())
        
        if total_stake == 0:
            return 0.0
        
        # ICP = stake-weighted reputation × NFT rarity
        stake_weight = proposer.stake / total_stake
        icp = stake_weight * proposer.reputation * (0.5 + 0.5 * proposer.nft_rarity)
        
        # Boost if votes are coming in
        vote_boost = min(1.0, candidate.votes_for / max(1, len(self.validators)))
        icp = 0.5 * icp + 0.5 * vote_boost
        
        return min(1.0, icp)
    
    def _compute_fano_efficiency(self, candidate: BlockCandidate) -> float:
        """Compute Fano efficiency of information transmission."""
        total_votes = candidate.votes_for + candidate.votes_against
        if total_votes == 0:
            return 0.5
        
        # Fano efficiency: how efficiently votes convey information
        p_agree = candidate.votes_for / total_votes
        p_disagree = candidate.votes_against / total_votes
        
        # Shannon entropy of vote distribution
        entropy = 0.0
        if p_agree > 0:
            entropy -= p_agree * math.log2(p_agree)
        if p_disagree > 0:
            entropy -= p_disagree * math.log2(p_disagree)
        
        # Fano efficiency: 1 - normalized entropy (higher = more decisive)
        max_entropy = 1.0  # Binary vote
        fano = 1.0 - (entropy / max_entropy) if max_entropy > 0 else 0.5
        
        return fano
    
    def _compute_qg_coupling(self, candidate: BlockCandidate) -> float:
        """Compute quantum gravity coupling term."""
        if not self.validators:
            return 0.5
        
        # QG coupling: average NFT rarity × stake concentration
        avg_rarity = sum(v.nft_rarity for v in self.validators.values()) / len(self.validators)
        total_stake = sum(v.stake for v in self.validators.values())
        
        # Stake concentration (Gini-like measure)
        stakes = [v.stake for v in self.validators.values()]
        if total_stake > 0 and len(stakes) > 1:
            mean_stake = total_stake / len(stakes)
            concentration = 1.0 - (mean_stake / max(stakes)) if max(stakes) > 0 else 0.0
        else:
            concentration = 0.5
        
        qg = 0.5 * avg_rarity + 0.5 * (1.0 - concentration)
        return min(1.0, qg)
    
    def get_state(self) -> Dict[str, Any]:
        """Get the current state of the consensus engine."""
        return {
            "current_height": self.current_height,
            "validators": len(self.validators),
            "candidates": len(self.block_candidates),
            "finalized_blocks": len(self.finalized_blocks),
            "chain_length": len(self.chain),
            "phi_tau": self.phi_tau,
            "phi_gwt": self.phi_gwt,
            "phi_icp": self.phi_icp,
            "phi_fano": self.phi_fano,
            "phi_qg": self.phi_qg,
            "stats": self.stats.copy(),
        }
