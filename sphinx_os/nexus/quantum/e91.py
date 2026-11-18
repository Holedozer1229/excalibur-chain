"""e91.py — E91 Entanglement Handshake for Aetherion-Excalibur P2P.

Simulates the Ekert 1991 (E91) quantum key distribution protocol using
classical numpy state-vector simulation of Bell pairs.

Protocol steps:
    1. Generate N entangled Bell pairs |Φ+⟩ = (|00⟩ + |11⟩) / √2
    2. Alice and Bob each receive one qubit from every pair
    3. Both measure in randomly chosen bases (CHSH settings)
    4. Publicly reveal bases, keep results where bases match (sifting)
    5. Compute CHSH S parameter — if |S| > 2, entanglement is confirmed
    6. Remaining sifted bits form the shared secret key

The CHSH inequality is a Bell inequality test:
    S = E(a0,b0) + E(a0,b1) + E(a1,b0) - E(a1,b1)

Quantum mechanics predicts S = 2√2 ≈ 2.828 for |Φ+⟩.
Classical local hidden-variable theories are bounded by |S| ≤ 2.

A violation (|S| > 2) confirms quantum correlation and detects eavesdropping.
"""

from __future__ import annotations

import math
import random
import struct
from typing import Dict, List, Optional, Tuple

import numpy as np


# ── Quantum gate matrices ────────────────────────────────────────────────

# Pauli matrices
PAULI_X = np.array([[0, 1], [1, 0]], dtype=np.complex128)
PAULI_Y = np.array([[0, -1j], [1j, 0]], dtype=np.complex128)
PAULI_Z = np.array([[1, 0], [0, -1]], dtype=np.complex128)
IDENTITY = np.array([[1, 0], [0, 1]], dtype=np.complex128)

# Hadamard gate
HADAMARD = np.array([[1, 1], [1, -1]], dtype=np.complex128) / np.sqrt(2)

# CNOT gate (2-qubit)
CNOT = np.array([
    [1, 0, 0, 0],
    [0, 1, 0, 0],
    [0, 0, 0, 1],
    [0, 0, 1, 0],
], dtype=np.complex128)

# Rotation gates
def ry_gate(theta: float) -> np.ndarray:
    """RY rotation gate by angle theta."""
    c = math.cos(theta / 2)
    s = math.sin(theta / 2)
    return np.array([
        [c, -s],
        [s, c],
    ], dtype=np.complex128)


# ── Measurement bases for CHSH ───────────────────────────────────────────

# For |Φ+⟩ = (|00⟩ + |11⟩)/√2, the correlation is E(α,β) = cos(α - β).
# Optimal CHSH angles that give S = 2√2 ≈ 2.828:
#   Alice: a0 = 0,       a1 = π/2
#   Bob:   b0 = π/4,     b1 = -π/4
#
# S = E(a0,b0) + E(a0,b1) + E(a1,b0) - E(a1,b1)
#   = cos(-π/4) + cos(π/4) + cos(π/4) - cos(3π/4)
#   = √2/2 + √2/2 + √2/2 - (-√2/2) = 2√2

ALICE_ANGLE_0 = 0.0            # 0°
ALICE_ANGLE_1 = math.pi / 2    # 90°

BOB_ANGLE_0 = math.pi / 4      # 45°
BOB_ANGLE_1 = -math.pi / 4     # -45°

ALICE_ANGLES = [ALICE_ANGLE_0, ALICE_ANGLE_1]
BOB_ANGLES = [BOB_ANGLE_0, BOB_ANGLE_1]


class E91Handshake:
    """Simulated E91 quantum key distribution handshake.

    Uses numpy to simulate the quantum state evolution of entangled
    Bell pairs. In production, this would execute the OpenQASM 3
    circuit (e91_handshake.qasm) on actual quantum hardware.

    Attributes:
        num_pairs: Number of Bell pairs to generate per handshake round.
        key_length: Target length of the extracted key in bits.
        chsh_threshold: Minimum |S| value to accept the key (default 2.0).
    """

    def __init__(
        self,
        num_pairs: int = 64,
        key_length: int = 32,
        chsh_threshold: float = 2.0,
        seed: Optional[int] = None,
    ):
        self.num_pairs = num_pairs
        self.key_length = key_length
        self.chsh_threshold = chsh_threshold
        self.rng = random.Random(seed)
        self.np_rng = np.random.default_rng(seed)

        # Results storage
        self.alice_results: List[int] = []
        self.bob_results: List[int] = []
        self.alice_bases: List[int] = []
        self.bob_bases: List[int] = []
        self.shared_key: Optional[bytes] = None
        self.chsh_value: Optional[float] = None
        self.entanglement_verified: bool = False

    def _generate_bell_pair(self) -> np.ndarray:
        """Generate a Bell pair |Φ+⟩ = (|00⟩ + |11⟩) / √2.

        Starts with |00⟩, applies H⊗I then CNOT.

        Returns:
            4-element state vector for the two-qubit Bell state.
        """
        # Initial state |00⟩
        state = np.array([1, 0, 0, 0], dtype=np.complex128)

        # Apply Hadamard to qubit 0: H⊗I
        h_tensor_i = np.kron(HADAMARD, IDENTITY)
        state = h_tensor_i @ state

        # Apply CNOT (control=qubit 0, target=qubit 1)
        state = CNOT @ state

        return state

    def _measure_bell_pair(
        self,
        state: np.ndarray,
        alice_angle: float,
        bob_angle: float,
    ) -> Tuple[int, int]:
        """Measure a Bell pair in rotated bases.

        For |Φ+⟩ = (|00⟩ + |11⟩)/√2, the correlation is E(α,β) = cos(α - β).
        The joint probability of outcomes (a, b) is:

            P(a=b | α, β) = (1 + cos(α - β)) / 2 = cos²((α - β)/2)
            P(a≠b | α, β) = (1 - cos(α - β)) / 2 = sin²((α - β)/2)

        Args:
            state: 4-element state vector of the Bell pair (unused; we use
                   the analytical formula for |Φ+⟩).
            alice_angle: Alice's measurement basis angle α.
            bob_angle: Bob's measurement basis angle β.

        Returns:
            (alice_result, bob_result) — each 0 or 1.
        """
        # Correlation E(α,β) = cos(α - β)
        # P(same) = (1 + E) / 2
        corr = math.cos(alice_angle - bob_angle)
        p_same = (1.0 + corr) / 2.0

        # Sample whether outcomes are same or different
        same = self.np_rng.random() < p_same

        # Alice's result is random (50/50 for |Φ+⟩)
        alice_result = int(self.np_rng.random() < 0.5)

        # Bob's result depends on whether they're the same
        if same:
            bob_result = alice_result
        else:
            bob_result = 1 - alice_result

        return alice_result, bob_result

    def run(self) -> Tuple[Optional[bytes], float]:
        """Execute one full E91 handshake round.

        Generates Bell pairs, performs measurements, runs CHSH test,
        and extracts the shared secret key.

        Returns:
            (shared_key, chsh_value) — key is None if CHSH test fails.

        Raises:
            ValueError: If not enough pairs for the desired key length.
        """
        self.alice_results.clear()
        self.bob_results.clear()
        self.alice_bases.clear()
        self.bob_bases.clear()
        self.shared_key = None
        self.chsh_value = None
        self.entanglement_verified = False

        # ── Step 1: Generate and measure Bell pairs ──
        for _ in range(self.num_pairs):
            # Generate entangled pair
            state = self._generate_bell_pair()

            # Randomly choose measurement bases
            alice_basis = self.rng.randint(0, 1)
            bob_basis = self.rng.randint(0, 1)

            alice_angle = ALICE_ANGLES[alice_basis]
            bob_angle = BOB_ANGLES[bob_basis]

            # Measure
            a_result, b_result = self._measure_bell_pair(
                state, alice_angle, bob_angle
            )

            self.alice_bases.append(alice_basis)
            self.bob_bases.append(bob_basis)
            self.alice_results.append(a_result)
            self.bob_results.append(b_result)

        # ── Step 2: Compute CHSH parameter ──
        chsh = self._compute_chsh()
        self.chsh_value = chsh

        # ── Step 3: Verify entanglement ──
        if abs(chsh) > self.chsh_threshold:
            self.entanglement_verified = True
        else:
            # Eavesdropping suspected or noise too high
            return None, chsh

        # ── Step 4: Extract shared key from sifted bits ──
        # Use pairs where both used basis 0 (correlated measurements)
        key_bits = []
        for i in range(self.num_pairs):
            if self.alice_bases[i] == 0 and self.bob_bases[i] == 0:
                key_bits.append(self.alice_results[i])

        # Trim or pad to desired key length
        if len(key_bits) < self.key_length:
            # Not enough sifted bits — use all matching-basis pairs
            for i in range(self.num_pairs):
                if self.alice_bases[i] == self.bob_bases[i]:
                    key_bits.append(self.alice_results[i])
                if len(key_bits) >= self.key_length:
                    break

        key_bits = key_bits[:self.key_length]

        # Convert bits to bytes
        key_bytes = self._bits_to_bytes(key_bits)
        self.shared_key = key_bytes

        return key_bytes, chsh

    def _compute_chsh(self) -> float:
        """Compute the CHSH S parameter from measurement data.

        S = E(a0,b0) + E(a0,b1) + E(a1,b0) - E(a1,b1)

        where E(a,b) = P(same|a,b) - P(different|a,b)

        Returns:
            CHSH S value. For perfect Bell pairs, S ≈ 2√2 ≈ 2.828.
        """
        # Collect correlations for each basis combination
        correlations: Dict[Tuple[int, int], List[int]] = {}

        for i in range(self.num_pairs):
            key = (self.alice_bases[i], self.bob_bases[i])
            same = 1 if self.alice_results[i] == self.bob_results[i] else 0
            correlations.setdefault(key, []).append(same)

        def E(a: int, b: int) -> float:
            """Correlation function for basis pair (a, b)."""
            samples = correlations.get((a, b), [])
            if not samples:
                return 0.0
            p_same = sum(samples) / len(samples)
            return 2 * p_same - 1  # P(same) - P(diff)

        S = E(0, 0) + E(0, 1) + E(1, 0) - E(1, 1)
        return S

    def _bits_to_bytes(self, bits: List[int]) -> bytes:
        """Convert a list of bits to bytes.

        Pads with zeros if the bit count is not a multiple of 8.
        """
        # Pad to multiple of 8
        while len(bits) % 8 != 0:
            bits.append(0)

        result = bytearray()
        for i in range(0, len(bits), 8):
            byte = 0
            for j in range(8):
                byte = (byte << 1) | bits[i + j]
            result.append(byte)

        return bytes(result)

    def get_stats(self) -> Dict[str, object]:
        """Return statistics about the last handshake round."""
        return {
            "num_pairs": self.num_pairs,
            "alice_results_count": len(self.alice_results),
            "bob_results_count": len(self.bob_results),
            "chsh_value": self.chsh_value,
            "entanglement_verified": self.entanglement_verified,
            "key_length_bits": len(self.shared_key) * 8 if self.shared_key else 0,
            "key_hex": self.shared_key.hex() if self.shared_key else None,
        }
