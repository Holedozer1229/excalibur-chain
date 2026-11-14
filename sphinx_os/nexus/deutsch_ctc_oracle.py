"""Deutsch CTC Oracle — Candidate-based stationary distribution for governance.

This module implements a Deutsch-style Closed Timelike Curve (CTC) oracle that
uses a finite candidate list and a verifier to compute a stationary distribution
over valid fixed points.  Unlike the Möbius spiral trajectory (which is a 1D
curve without a validity rule), this approach provides the structure needed for
a non-tautological oracle:

1. **Candidate List** — A finite set of possible answers (e.g., governance
   outcomes, proposal interpretations).
2. **Verifier** — A function that checks whether a candidate satisfies the
   required constraints (e.g., risk thresholds, economic viability).
3. **Stationary Distribution** — Under the simple map F(c)=c for valid
   candidates and "advance to the next candidate" otherwise, the oracle
   returns a uniform distribution over valid fixed points.

When valid candidates exist, the distribution concentrates on those fixed
points.  If none pass verification, the cyclic map still has a stationary
distribution, but it doesn't certify an answer.

Integration with SphinxQ
========================
The SphinxQ oracle uses this Deutsch CTC distribution to evaluate governance
proposals.  It generates candidate answers (e.g., risk scores, voting decisions)
and verifies them against domain-specific constraints.  The resulting
distribution provides a quantum-inspired consensus mechanism that goes beyond
simple majority voting.

Security Considerations
=======================
- The verifier must be deterministic for reproducibility
- Candidate generation should be bounded to prevent infinite loops
- The stationary distribution is uniform over valid candidates, providing
  no bias toward any particular outcome
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------
@dataclass
class DeutschCTCResult:
    """Result of a Deutsch CTC oracle computation."""
    probabilities: Dict[str, float]  # Candidate -> probability
    has_valid_fixed_points: bool     # True if any candidates pass verification
    valid_candidates: List[str]      # Candidates that pass verification
    total_candidates: int            # Total number of candidates evaluated
    stationary_distribution: List[float]  # Ordered probability vector
    reasoning: str                   # Human-readable explanation


# ---------------------------------------------------------------------------
# Core Deutsch CTC Distribution
# ---------------------------------------------------------------------------
def deutsch_ctc_distribution(
    candidates: List[str],
    verify: Callable[[str], bool],
) -> Tuple[Dict[str, float], bool]:
    """Compute the Deutsch-style CTC stationary distribution.

    Under the simple map F(c)=c for valid candidates and "advance to the next
    candidate" otherwise, this returns a stationary distribution over the
    candidate space.

    Args:
        candidates: Finite list of candidate answers (may contain duplicates).
        verify: Function that returns True if a candidate is valid.

    Returns:
        Tuple of (probability_dict, has_valid_fixed_points).

    Raises:
        ValueError: If candidate list is empty.
    """
    # Preserve order, remove duplicates
    states = list(dict.fromkeys(candidates))

    if not states:
        raise ValueError("Candidate list is empty.")

    valid = [candidate for candidate in states if verify(candidate)]
    support = valid or states

    probabilities = {
        candidate: (1.0 / len(support) if candidate in support else 0.0)
        for candidate in states
    }

    return probabilities, bool(valid)


# ---------------------------------------------------------------------------
# SphinxQ Oracle
# ---------------------------------------------------------------------------
class SphinxQOracle:
    """SphinxQ oracle using Deutsch CTC distribution for governance decisions.

    The oracle generates candidate answers for a given query and uses the
    Deutsch CTC distribution to find stationary fixed points.  This provides
    a quantum-inspired consensus mechanism that goes beyond simple majority
    voting.

    The verifier defines what makes an answer valid — without it, the oracle
    would be tautological.  The verifier typically encodes domain-specific
    constraints such as risk thresholds, economic viability, or security
    requirements.
    """

    def __init__(
        self,
        name: str = "SphinxQ",
        candidate_generator: Optional[Callable[[Any], List[str]]] = None,
        default_verify: Optional[Callable[[str, Any], bool]] = None,
    ):
        """Initialize the SphinxQ oracle.

        Args:
            name: Oracle identifier.
            candidate_generator: Function that generates candidates from a query.
            default_verify: Default verifier function for candidates.
        """
        self.name = name
        self._candidate_generator = candidate_generator or self._default_candidate_generator
        self._default_verify = default_verify or self._default_verify_fn
        self._query_count = 0
        self._valid_query_count = 0

    def respond(
        self,
        query: Any,
        verify: Optional[Callable[[str, Any], bool]] = None,
    ) -> DeutschCTCResult:
        """Process a query using Deutsch CTC distribution.

        Args:
            query: The question or proposal to evaluate.
            verify: Optional custom verifier; falls back to default.

        Returns:
            DeutschCTCResult with the stationary distribution.
        """
        self._query_count += 1
        verifier = verify or self._default_verify

        # Generate candidates
        candidates = self._candidate_generator(query)

        # Bind query to verifier for deutsch_ctc_distribution
        def verify_with_query(candidate: str) -> bool:
            return verifier(candidate, query)

        # Compute distribution
        probabilities, has_valid = deutsch_ctc_distribution(candidates, verify_with_query)

        if has_valid:
            self._valid_query_count += 1

        # Build result
        valid_candidates = [c for c, p in probabilities.items() if p > 0 and has_valid]
        stationary = [probabilities[c] for c in probabilities.keys()]

        reasoning = self._generate_reasoning(
            candidates, probabilities, has_valid, valid_candidates
        )

        return DeutschCTCResult(
            probabilities=probabilities,
            has_valid_fixed_points=has_valid,
            valid_candidates=valid_candidates,
            total_candidates=len(candidates),
            stationary_distribution=stationary,
            reasoning=reasoning,
        )

    @staticmethod
    def _default_candidate_generator(query: Any) -> List[str]:
        """Default candidate generator for simple queries.

        Args:
            query: The query to generate candidates for.

        Returns:
            List of candidate answers.
        """
        if isinstance(query, dict):
            # For governance proposals, generate standard outcomes
            return ["APPROVE", "REJECT", "AMEND", "DEFER"]
        elif isinstance(query, (int, float)):
            # For numeric queries, generate nearby values
            base = int(query)
            return [str(base - 1), str(base), str(base + 1)]
        else:
            # For string queries, generate simple yes/no
            return ["YES", "NO"]

    @staticmethod
    def _default_verify_fn(candidate: str, query: Any) -> bool:
        """Default verifier that accepts all candidates.

        WARNING: This default verifier makes the oracle tautological.
        Always provide a custom verifier for meaningful results.

        Args:
            candidate: The candidate to verify.
            query: The original query.

        Returns:
            True (accepts all candidates by default).
        """
        return True

    @staticmethod
    def _generate_reasoning(
        candidates: List[str],
        probabilities: Dict[str, float],
        has_valid: bool,
        valid_candidates: List[str],
    ) -> str:
        """Generate human-readable reasoning for the result.

        Args:
            candidates: All candidates evaluated.
            probabilities: Probability distribution.
            has_valid: Whether valid fixed points exist.
            valid_candidates: List of valid candidates.

        Returns:
            Reasoning string.
        """
        if has_valid:
            support_size = len(valid_candidates)
            prob_per_candidate = 1.0 / support_size if support_size > 0 else 0.0
            return (
                f"CTC fixed point found: {support_size} valid candidate(s) "
                f"with uniform probability {prob_per_candidate:.4f} each. "
                f"Valid: {', '.join(valid_candidates)}"
            )
        else:
            return (
                f"No valid fixed points among {len(candidates)} candidates. "
                f"Stationary distribution is uniform over all candidates, "
                f"but does not certify an answer."
            )

    def get_stats(self) -> Dict[str, Any]:
        """Get oracle statistics.

        Returns:
            Dictionary with query counts and validity rate.
        """
        return {
            "name": self.name,
            "total_queries": self._query_count,
            "valid_queries": self._valid_query_count,
            "validity_rate": (
                self._valid_query_count / self._query_count
                if self._query_count > 0
                else 0.0
            ),
        }
