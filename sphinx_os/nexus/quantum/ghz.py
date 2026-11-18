"""ghz.py — GHZ Random Beacon for Aetherion-Excalibur Network Sync.

Simulates the Greenberger-Horne-Zeilinger (GHZ) random beacon protocol
using classical numpy state-vector simulation.

Protocol steps:
    1. Prepare an N-qubit GHZ state: |GHZ⟩ = (|00...0⟩ + |11...1⟩) / √2
    2. Each of N network participants receives one qubit
    3. All participants measure in the computational (Z) basis
    4. Due to entanglement, all measurements yield the same outcome:
       either all 0 or all 1, each with 50% probability
    5. This shared random bit is used for consensus, leader election, etc.

For longer beacons, repeat K times to generate K shared random bits.

The GHZ state is the maximal generalization of a Bell pair to N qubits.
While a Bell pair entangles 2 qubits, a GHZ state entangles all N qubits
into a single coherent superposition — measuring any subset collapses
the entire state.
"""

from __future__ import annotations

import math
import random
from typing import Dict, List, Optional, Tuple

import numpy as np


# ── Quantum gate matrices (shared with e91.py) ──────────────────────────

IDENTITY = np.array([[1, 0], [0, 1]], dtype=np.complex128)
HADAMARD = np.array([[1, 1], [1, -1]], dtype=np.complex128) / math.sqrt(2)


def _cnot_gate(num_qubits: int, control: int, target: int) -> np.ndarray:
    """Build a CNOT gate for num_qubits qubits.

    Args:
        num_qubits: Total number of qubits in the system.
        control: Control qubit index (0 = most significant).
        target: Target qubit index.

    Returns:
        2^n × 2^n unitary matrix for the CNOT operation.
    """
    dim = 2 ** num_qubits
    gate = np.zeros((dim, dim), dtype=np.complex128)

    for i in range(dim):
        control_bit = (i >> (num_qubits - 1 - control)) & 1
        if control_bit == 1:
            # Flip the target qubit
            target_mask = 1 << (num_qubits - 1 - target)
            j = i ^ target_mask
            gate[j, i] = 1
        else:
            gate[i, i] = 1

    return gate


def _hadamard_on_qubit(num_qubits: int, qubit: int) -> np.ndarray:
    """Build H⊗I⊗...⊗I with Hadamard on the specified qubit.

    Args:
        num_qubits: Total number of qubits.
        qubit: Qubit index to apply Hadamard on.

    Returns:
        2^n × 2^n unitary matrix.
    """
    dim = 2 ** num_qubits
    # Use Kronecker product
    matrices = [IDENTITY] * num_qubits
    matrices[qubit] = HADAMARD

    result = matrices[0]
    for m in matrices[1:]:
        result = np.kron(result, m)

    return result


class GHZBeacon:
    """Simulated GHZ random beacon for network-wide shared randomness.

    Uses numpy to simulate the quantum state evolution of N-qubit
    GHZ states. In production, this would execute the OpenQASM 3
    circuit (ghz_beacon.qasm) on actual quantum hardware.

    Attributes:
        num_participants: Number of qubits in the GHZ state (= network nodes).
        num_rounds: Number of repeated GHZ rounds to generate multiple bits.
    """

    def __init__(
        self,
        num_participants: int = 8,
        num_rounds: int = 16,
        seed: Optional[int] = None,
    ):
        if num_participants < 2:
            raise ValueError("GHZ state requires at least 2 participants")
        if num_participants > 20:
            raise ValueError(
                "Simulation limited to 20 qubits (use actual hardware for more)"
            )

        self.num_participants = num_participants
        self.num_rounds = num_rounds
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)

        # Results storage
        self.beacon_bits: List[int] = []
        self.participant_results: List[List[int]] = []  # per-round results
        self.consistency_checks: List[bool] = []

    def _prepare_ghz_state(self) -> np.ndarray:
        """Prepare an N-qubit GHZ state: (|00...0⟩ + |11...1⟩) / √2.

        Circuit:
            1. Start with |00...0⟩
            2. Apply Hadamard to qubit 0
            3. Apply CNOT from qubit 0 to each remaining qubit

        Returns:
            2^n element state vector for the GHZ state.
        """
        n = self.num_participants
        dim = 2 ** n

        # Initial state |00...0⟩
        state = np.zeros(dim, dtype=np.complex128)
        state[0] = 1.0

        # Apply Hadamard to qubit 0
        h_gate = _hadamard_on_qubit(n, 0)
        state = h_gate @ state

        # Apply CNOT from qubit 0 to each other qubit
        for target in range(1, n):
            cnot = _cnot_gate(n, control=0, target=target)
            state = cnot @ state

        return state

    def _measure_ghz_state(self, state: np.ndarray) -> List[int]:
        """Measure all qubits in the GHZ state in the Z basis.

        For a perfect GHZ state, all measurements will yield the same
        outcome: either all 0s or all 1s.

        Args:
            state: 2^n element state vector of the GHZ state.

        Returns:
            List of n measurement outcomes (all should be identical).
        """
        probs = np.abs(state) ** 2
        total = probs.sum()
        probs = probs / total

        # Sample outcome
        outcome = self.np_rng.choice(2 ** self.num_participants, p=probs)

        # Decode to individual qubit results
        results = []
        for i in range(self.num_participants):
            bit = (outcome >> (self.num_participants - 1 - i)) & 1
            results.append(int(bit))

        return results

    def _verify_consistency(self, results: List[int]) -> bool:
        """Verify all participants measured the same outcome.

        In a perfect GHZ state, all Z-basis measurements agree.
        """
        if not results:
            return False
        first = results[0]
        return all(r == first for r in results)

    def generate_beacon(self) -> List[int]:
        """Generate a multi-round GHZ random beacon.

        Repeats the GHZ protocol num_rounds times to produce a
        shared random bit string.

        Returns:
            List of random bits (one per round).
        """
        self.beacon_bits.clear()
        self.participant_results.clear()
        self.consistency_checks.clear()

        for _ in range(self.num_rounds):
            # Prepare GHZ state
            state = self._prepare_ghz_state()

            # All participants measure
            results = self._measure_ghz_state(state)

            # Verify consistency
            consistent = self._verify_consistency(results)
            self.consistency_checks.append(consistent)

            # Store results
            self.participant_results.append(results)

            # The beacon bit is the first participant's result
            # (all should be the same in a perfect GHZ state)
            self.beacon_bits.append(results[0])

        return list(self.beacon_bits)

    def generate_single_bit(self) -> int:
        """Generate a single shared random bit via one GHZ round.

        Returns:
            A single random bit (0 or 1).
        """
        bits = self.generate_beacon()
        return bits[0] if bits else 0

    def get_beacon_bytes(self) -> bytes:
        """Convert beacon bits to bytes.

        Returns:
            Bytes representation of the beacon bits.
        """
        if not self.beacon_bits:
            self.generate_beacon()

        # Pad to multiple of 8
        bits = list(self.beacon_bits)
        while len(bits) % 8 != 0:
            bits.append(0)

        result = bytearray()
        for i in range(0, len(bits), 8):
            byte = 0
            for j in range(8):
                byte = (byte << 1) | bits[i + j]
            result.append(byte)

        return bytes(result)

    def compute_entropy(self) -> float:
        """Compute the Shannon entropy of the beacon bits.

        For a fair random beacon, entropy should be close to 1.0 bit.

        Returns:
            Entropy in bits per symbol.
        """
        if not self.beacon_bits:
            return 0.0

        n = len(self.beacon_bits)
        ones = sum(self.beacon_bits)
        zeros = n - ones

        p0 = zeros / n
        p1 = ones / n

        entropy = 0.0
        if p0 > 0:
            entropy -= p0 * math.log2(p0)
        if p1 > 0:
            entropy -= p1 * math.log2(p1)

        return entropy

    def get_stats(self) -> Dict[str, object]:
        """Return statistics about the beacon."""
        entropy = self.compute_entropy() if self.beacon_bits else 0.0
        consistency_rate = (
            sum(self.consistency_checks) / len(self.consistency_checks)
            if self.consistency_checks
            else 0.0
        )

        return {
            "num_participants": self.num_participants,
            "num_rounds": self.num_rounds,
            "beacon_bits_generated": len(self.beacon_bits),
            "beacon_bits": list(self.beacon_bits),
            "beacon_hex": self.get_beacon_bytes().hex() if self.beacon_bits else None,
            "entropy_bits": entropy,
            "consistency_rate": consistency_rate,
            "all_consistent": all(self.consistency_checks) if self.consistency_checks else True,
        }
