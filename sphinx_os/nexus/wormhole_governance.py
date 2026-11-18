"""Wormhole Governance — Entropy-weighted CTC governance engine.

Unifies quantum spacetime fabric, Deutsch CTC oracle, and holographic P2P
routing. When wormholes form in simulated spacetime, they create CTC causal
loops that drive governance decisions. Entanglement entropy between wormhole
endpoints weights the candidate probability distribution.
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from sphinx_os.nexus.quantum_spacetime import QuantumSpacetimeFabric, WormholeEvent, QuantumGravityMetrics
from sphinx_os.nexus.deutsch_ctc_oracle import deutsch_ctc_distribution, DeutschCTCResult, SphinxQOracle


@dataclass
class GovernanceDecision:
    """Result of a governance decision."""
    winner: str
    probability: float
    all_probabilities: Dict[str, float]
    has_valid_fixed_points: bool
    phi_qg: float
    wormhole_count: int
    reasoning: str


class WormholeGovernanceEngine:
    """Governance engine using entropy-weighted CTC distribution.

    Instead of uniform probability over valid candidates, each candidate's
    probability is proportional to its entanglement entropy weight from
    the wormhole structure.

    Args:
        num_qubits: Qubits in the fabric.
        seed: Random seed.
    """

    def __init__(self, num_qubits: int = 16, seed: Optional[int] = None):
        self.fabric = QuantumSpacetimeFabric(num_qubits=num_qubits, seed=seed)
        self.oracle = SphinxQOracle()
        self.seed = seed

    def evolve_fabric(self, steps: int = 10) -> List[WormholeEvent]:
        """Evolve the quantum spacetime fabric.

        Args:
            steps: Number of evolution steps.

        Returns:
            List of newly formed wormholes.
        """
        return self.fabric.evolve(steps)

    def govern(self, candidates: List[str],
               verify_fn: Callable[[str], bool],
               evolve_steps: int = 10) -> GovernanceDecision:
        """Make a governance decision using entropy-weighted CTC.

        Args:
            candidates: List of candidate outcomes.
            verify_fn: Verification function for candidates.
            evolve_steps: Fabric evolution steps before decision.

        Returns:
            GovernanceDecision with winner and probabilities.
        """
        # Evolve fabric to create wormhole structure
        wormholes = self.evolve_fabric(evolve_steps)

        # Compute entropy weights for candidates
        weights = self._compute_entropy_weights(candidates, wormholes)

        # Run Deutsch CTC distribution
        probs, has_valid = deutsch_ctc_distribution(candidates, verify_fn)

        # Apply entropy weighting to valid candidates
        valid_candidates = [c for c in candidates if verify_fn(c)]
        if valid_candidates and weights:
            total_weight = sum(weights.get(c, 1.0) for c in valid_candidates)
            if total_weight > 0:
                for c in valid_candidates:
                    w = weights.get(c, 1.0)
                    probs[c] = (w / total_weight) if c in valid_candidates else 0.0

        # Select winner (highest probability)
        if probs:
            winner = max(probs, key=probs.get)
        else:
            winner = candidates[0] if candidates else "NONE"

        metrics = self.fabric.get_quantum_gravity_metrics()

        return GovernanceDecision(
            winner=winner,
            probability=probs.get(winner, 0.0),
            all_probabilities=probs,
            has_valid_fixed_points=has_valid,
            phi_qg=metrics.phi_qg,
            wormhole_count=metrics.wormhole_count,
            reasoning=f"Winner '{winner}' selected via entropy-weighted CTC "
                      f"(φ_QG={metrics.phi_qg:.4f}, {metrics.wormhole_count} wormholes)",
        )

    def _compute_entropy_weights(self, candidates: List[str],
                                  wormholes: List[WormholeEvent]) -> Dict[str, float]:
        """Compute entropy-based weights for candidates.

        Maps each candidate to a wormhole's entanglement entropy.

        Args:
            candidates: Candidate list.
            wormholes: Active wormhole events.

        Returns:
            Dict of candidate -> entropy weight.
        """
        weights = {}
        for i, candidate in enumerate(candidates):
            if wormholes:
                # Map candidate to a wormhole by index
                wh = wormholes[i % len(wormholes)]
                weights[candidate] = wh.entanglement_entropy + 1e-10
            else:
                # Uniform weight if no wormholes
                weights[candidate] = 1.0
        return weights

    def quantum_consensus(self, candidates: List[str],
                          verify_fn: Callable[[str], bool],
                          rounds: int = 3) -> GovernanceDecision:
        """Run multiple governance rounds for consensus.

        Args:
            candidates: Candidate list.
            verify_fn: Verification function.
            rounds: Number of governance rounds.

        Returns:
            Final GovernanceDecision.
        """
        decision = None
        for _ in range(rounds):
            decision = self.govern(candidates, verify_fn)
        return decision

    def get_quantum_gravity_metrics(self) -> QuantumGravityMetrics:
        """Get current quantum gravity metrics."""
        return self.fabric.get_quantum_gravity_metrics()
