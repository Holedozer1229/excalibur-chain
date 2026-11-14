"""Quantum Spacetime Fabric — Simulates quantum gates as spacetime curvature.

This module models a quantum spacetime fabric where quantum gate operations
create curvature in a simulated manifold. Entanglement entropy between qubit
pairs is tracked, and when entanglement exceeds a threshold, a "wormhole"
is detected — representing a causal connection between distant points in
the fabric.

Key concepts:
- Quantum gates (H, T, S, X) are mapped to curvature tensors
- Entanglement entropy measures the correlation between qubit pairs
- Wormhole formation occurs when entropy exceeds a threshold
- φ_QG (phi quantum gravity) metric captures conscious consensus strength
"""

import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------

@dataclass
class WormholeEvent:
    """A detected wormhole in the quantum spacetime fabric."""
    endpoint_a: int          # Qubit index A
    endpoint_b: int          # Qubit index B
    entanglement_entropy: float  # Entropy at formation
    formation_step: int      # Simulation step when formed
    curvature: float         # Local curvature at formation
    closed: bool = False     # Whether the wormhole has closed


@dataclass
class QuantumGravityMetrics:
    """Quantum gravity metrics for the fabric state."""
    phi_qg: float            # Quantum gravity conscious consensus metric
    total_curvature: float   # Integrated curvature scalar
    avg_entanglement: float  # Average entanglement entropy
    wormhole_count: int      # Number of active wormholes
    fabric_dimension: int    # Effective dimension of the fabric


# ---------------------------------------------------------------------------
# Quantum Spacetime Fabric
# ---------------------------------------------------------------------------

class QuantumSpacetimeFabric:
    """Simulates a quantum spacetime fabric where gates create curvature.

    The fabric is a grid of qubits. Each gate operation modifies the local
    curvature tensor. Entanglement between qubit pairs is tracked, and
    wormholes form when entanglement exceeds a threshold.

    Args:
        num_qubits: Number of qubits in the fabric (default 16).
        wormhole_threshold: Entanglement entropy threshold for wormhole
            formation (default 0.6).
        seed: Random seed for reproducibility.
    """

    # Gate-to-curvature mapping
    GATE_CURVATURE = {
        'H': 0.5,    # Hadamard — moderate curvature
        'T': 0.25,   # T-gate — gentle curvature
        'S': 0.35,   # S-gate — mild curvature
        'X': 0.75,   # Pauli-X — strong curvature
    }

    def __init__(self, num_qubits: int = 16, wormhole_threshold: float = 0.6,
                 seed: Optional[int] = None):
        self.num_qubits = num_qubits
        self.wormhole_threshold = wormhole_threshold
        self.rng = np.random.RandomState(seed)

        # State vectors for each qubit (Bloch sphere representation)
        self.states = np.array([
            [1.0, 0.0, 0.0]  # |0⟩ for each qubit
            for _ in range(num_qubits)
        ], dtype=np.float64)

        # Curvature tensor (num_qubits x num_qubits)
        self.curvature = np.zeros((num_qubits, num_qubits), dtype=np.float64)

        # Entanglement matrix (num_qubits x num_qubits)
        self.entanglement = np.zeros((num_qubits, num_qubits), dtype=np.float64)

        # Wormhole events
        self.wormholes: List[WormholeEvent] = []
        self.active_wormholes: List[WormholeEvent] = []

        # Simulation step counter
        self.step = 0

    def apply_gate(self, gate: str, qubit: int) -> float:
        """Apply a quantum gate to a qubit, creating local curvature.

        Args:
            gate: Gate type ('H', 'T', 'S', 'X').
            qubit: Qubit index.

        Returns:
            Curvature value created by the gate.
        """
        curvature_val = self.GATE_CURVATURE.get(gate, 0.5)

        # Update qubit state (simplified Bloch sphere rotation)
        angle = curvature_val * np.pi
        state = self.states[qubit]

        # Rotate state vector
        cos_a, sin_a = np.cos(angle), np.sin(angle)
        new_state = np.array([
            state[0] * cos_a - state[1] * sin_a,
            state[0] * sin_a + state[1] * cos_a,
            state[2] * cos_a
        ])
        self.states[qubit] = new_state / (np.linalg.norm(new_state) + 1e-10)

        # Update local curvature
        self.curvature[qubit, qubit] += curvature_val

        # Create entanglement with random neighbor
        neighbor = self.rng.randint(0, self.num_qubits)
        if neighbor != qubit:
            entropy = self._compute_entanglement(qubit, neighbor)
            self.entanglement[qubit, neighbor] = entropy
            self.entanglement[neighbor, qubit] = entropy

        self.step += 1
        return curvature_val

    def evolve(self, num_steps: int = 10) -> List[WormholeEvent]:
        """Evolve the fabric for a number of steps.

        Args:
            num_steps: Number of evolution steps.

        Returns:
            List of newly formed wormhole events.
        """
        new_wormholes = []
        gates = list(self.GATE_CURVATURE.keys())

        for _ in range(num_steps):
            gate = self.rng.choice(gates)
            qubit = self.rng.randint(0, self.num_qubits)
            self.apply_gate(gate, qubit)

        # Check for wormhole formation
        new_wormholes = self.detect_wormholes()
        self.active_wormholes.extend(new_wormholes)
        self.wormholes.extend(new_wormholes)

        return new_wormholes

    def _compute_entanglement(self, a: int, b: int) -> float:
        """Compute entanglement entropy between two qubits.

        Uses the von Neumann entropy of the reduced density matrix
        (simplified as Bloch sphere distance-based entropy).

        Args:
            a: First qubit index.
            b: Second qubit index.

        Returns:
            Entanglement entropy (0 to 1).
        """
        # Distance-based entanglement proxy
        dist = np.linalg.norm(self.states[a] - self.states[b])
        # Map distance to entropy (closer states = higher entanglement)
        entropy = max(0.0, 1.0 - dist / np.sqrt(3))
        # Add randomness from curvature
        entropy += self.curvature[a, b] * 0.1
        return min(1.0, max(0.0, entropy))

    def get_entanglement_entropy(self, a: int, b: int) -> float:
        """Get the entanglement entropy between two qubits.

        Args:
            a: First qubit index.
            b: Second qubit index.

        Returns:
            Entanglement entropy value.
        """
        return self.entanglement[a, b]

    def detect_wormholes(self) -> List[WormholeEvent]:
        """Detect wormhole formation where entanglement exceeds threshold.

        Returns:
            List of newly formed WormholeEvent objects.
        """
        new_wormholes = []

        for i in range(self.num_qubits):
            for j in range(i + 1, self.num_qubits):
                entropy = self.entanglement[i, j]
                if entropy >= self.wormhole_threshold:
                    # Check if this wormhole already exists
                    exists = any(
                        wh.endpoint_a == i and wh.endpoint_b == j
                        for wh in self.wormholes
                    )
                    if not exists:
                        wh = WormholeEvent(
                            endpoint_a=i,
                            endpoint_b=j,
                            entanglement_entropy=entropy,
                            formation_step=self.step,
                            curvature=self.curvature[i, i] + self.curvature[j, j],
                        )
                        new_wormholes.append(wh)

        return new_wormholes

    def get_curvature(self) -> np.ndarray:
        """Get the current curvature tensor.

        Returns:
            Curvature tensor (num_qubits x num_qubits).
        """
        return self.curvature.copy()

    def get_quantum_gravity_metrics(self) -> QuantumGravityMetrics:
        """Compute quantum gravity metrics for the current fabric state.

        Returns:
            QuantumGravityMetrics with φ_QG, curvature, entanglement, etc.
        """
        # φ_QG: weighted average of entanglement × curvature
        ent_sum = np.sum(self.entanglement)
        curv_sum = np.sum(np.diag(self.curvature))
        phi_qg = ent_sum * curv_sum / (self.num_qubits + 1e-10)

        # Average entanglement
        avg_ent = np.mean(self.entanglement)

        # Active wormhole count
        active = len([wh for wh in self.active_wormholes if not wh.closed])

        return QuantumGravityMetrics(
            phi_qg=phi_qg,
            total_curvature=float(curv_sum),
            avg_entanglement=float(avg_ent),
            wormhole_count=active,
            fabric_dimension=self.num_qubits,
        )

    def close_wormhole(self, index: int) -> bool:
        """Close a wormhole by index.

        Args:
            index: Index in active_wormholes list.

        Returns:
            True if wormhole was closed, False if not found.
        """
        if 0 <= index < len(self.active_wormholes):
            self.active_wormholes[index].closed = True
            return True
        return False

    def reset(self) -> None:
        """Reset the fabric to initial state."""
        self.states = np.array([
            [1.0, 0.0, 0.0] for _ in range(self.num_qubits)
        ], dtype=np.float64)
        self.curvature = np.zeros((self.num_qubits, self.num_qubits), dtype=np.float64)
        self.entanglement = np.zeros((self.num_qubits, self.num_qubits), dtype=np.float64)
        self.wormholes = []
        self.active_wormholes = []
        self.step = 0
