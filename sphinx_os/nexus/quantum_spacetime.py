"""Quantum-Spacetime Fabric: Simulates quantum states coupled with spacetime curvature."""

import numpy as np
from typing import Dict, List, Optional, Any


class QuantumSpacetimeFabric:
    """A quantum state simulator coupled with a discrete spacetime curvature model.
    
    The fabric maintains:
    - A quantum state vector (density matrix) for entanglement tracking
    - A discrete spacetime grid with curvature tensor
    - Wormhole nodes that connect distant regions of the grid
    """
    
    def __init__(
        self,
        num_qubits: int = 4,
        grid_size: int = 16,
        wormhole_threshold: float = 0.3,
    ):
        self.num_qubits = num_qubits
        self.grid_size = grid_size
        self.wormhole_threshold = wormhole_threshold
        
        # Quantum state: start in |00...0>
        dim = 2 ** num_qubits
        self.state_vector = np.zeros(dim, dtype=np.complex128)
        self.state_vector[0] = 1.0
        
        # Density matrix: |ψ><ψ|
        self.density_matrix = np.outer(self.state_vector, self.state_vector.conj())
        
        # Spacetime grid: curvature tensor (simplified as 2D scalar field)
        self.curvature = np.zeros((grid_size, grid_size), dtype=np.float64)
        
        # Wormhole nodes: pairs of grid coordinates connected by wormholes
        self.wormhole_nodes: List[tuple] = []
        
        # Step counter
        self.step_count = 0
        
    def apply_quantum_gate(self, gate: np.ndarray, qubits: List[int]):
        """Apply a quantum gate to the specified qubits.
        
        Args:
            gate: The unitary matrix of the gate.
            qubits: List of qubit indices to apply the gate to.
        """
        # Build full operator by tensoring with identity on non-target qubits
        full_op = self._build_full_operator(gate, qubits)
        
        # Apply: |ψ'> = U|ψ>
        self.state_vector = full_op @ self.state_vector
        # Update density matrix
        self.density_matrix = np.outer(self.state_vector, self.state_vector.conj())
        
        # Update curvature based on gate application
        self._update_curvature_from_gate(gate, qubits)
        
    def _build_full_operator(self, gate: np.ndarray, qubits: List[int]) -> np.ndarray:
        """Build the full operator matrix for a gate acting on specific qubits."""
        dim = 2 ** self.num_qubits
        
        if len(qubits) == 1:
            # Single qubit gate
            q = qubits[0]
            I = np.eye(2, dtype=np.complex128)
            ops = [gate if i == q else I for i in range(self.num_qubits)]
            # Tensor product in reverse order (qubit 0 is last in Kronecker)
            full_op = ops[-1]
            for op in reversed(ops[:-1]):
                full_op = np.kron(op, full_op)
            return full_op
        
        # Multi-qubit gate (simplified: only support adjacent qubits for now)
        # For simplicity, apply as single-qubit gates if gate is 2x2
        if gate.shape == (2, 2):
            full_op = np.eye(dim, dtype=np.complex128)
            for q in qubits:
                single_op = self._build_full_operator(gate, [q])
                full_op = single_op @ full_op
            return full_op
        
        # General case: just apply gate directly if dimensions match
        if gate.shape == (dim, dim):
            return gate
        
        # Fallback: identity
        return np.eye(dim, dtype=np.complex128)
    
    def _update_curvature_from_gate(self, gate: np.ndarray, qubits: List[int]):
        """Update spacetime curvature based on quantum gate application."""
        # Compute the trace of the gate as a curvature perturbation
        gate_trace = np.abs(np.trace(gate))
        
        # Perturb curvature at random grid points near the center
        center = self.grid_size // 2
        for _ in range(len(qubits)):
            x = (center + np.random.randint(-3, 4)) % self.grid_size
            y = (center + np.random.randint(-3, 4)) % self.grid_size
            self.curvature[x, y] += gate_trace * 0.01
        
    def compute_entanglement_entropy(self) -> float:
        """Compute the von Neumann entanglement entropy of the first qubit."""
        # Partial trace over all qubits except the first
        dim = 2 ** self.num_qubits
        # Reshape density matrix to isolate first qubit
        rho = self.density_matrix.reshape(2, dim // 2, 2, dim // 2)
        # Partial trace: trace out qubits 1..n
        rho_reduced = np.trace(rho, axis1=1, axis2=3)
        
        # Eigenvalues of reduced density matrix
        eigenvalues = np.linalg.eigvalsh(rho_reduced)
        eigenvalues = eigenvalues[eigenvalues > 1e-12]  # Filter numerical noise
        
        # Von Neumann entropy: -Tr(ρ log₂ ρ)
        entropy = -np.sum(eigenvalues * np.log2(eigenvalues))
        return float(entropy)
    
    def compute_quantum_purity(self) -> float:
        """Compute the purity of the quantum state: Tr(ρ²)."""
        purity = np.real(np.trace(self.density_matrix @ self.density_matrix))
        return float(purity)
    
    def evolve_curvature(self, dt: float = 0.01):
        """Evolve the spacetime curvature using a simplified wave equation."""
        new_curvature = self.curvature.copy()
        
        # Discrete Laplacian
        laplacian = np.zeros_like(self.curvature)
        for i in range(1, self.grid_size - 1):
            for j in range(1, self.grid_size - 1):
                laplacian[i, j] = (
                    self.curvature[i + 1, j] + self.curvature[i - 1, j]
                    + self.curvature[i, j + 1] + self.curvature[i, j - 1]
                    - 4.0 * self.curvature[i, j]
                )
        
        # Wave equation: ∂²φ/∂t² = c²∇²φ (simplified Euler integration)
        new_curvature += dt * dt * laplacian - 0.001 * self.curvature  # Damping
        
        self.curvature = new_curvature
        
    def detect_wormholes(self):
        """Detect wormhole candidates based on curvature threshold."""
        self.wormhole_nodes.clear()
        
        # Find regions where curvature exceeds threshold
        high_curvature = np.abs(self.curvature) > self.wormhole_threshold
        
        # Find connected components of high-curvature regions
        indices = np.argwhere(high_curvature)
        if len(indices) > 1:
            # Pair distant high-curvature points as wormhole endpoints
            self.wormhole_nodes = [
                (int(indices[0][0]), int(indices[0][1])),
                (int(indices[-1][0]), int(indices[-1][1])),
            ]
    
    def unified_step(self) -> Dict[str, Any]:
        """Perform one unified step: evolve quantum state and spacetime curvature.
        
        Returns:
            Dictionary with metrics from this step.
        """
        self.step_count += 1
        
        # Evolve curvature
        self.evolve_curvature()
        
        # Detect wormholes
        self.detect_wormholes()
        
        # Compute metrics
        entanglement_entropy = self.compute_entanglement_entropy()
        curvature_rms = float(np.sqrt(np.mean(self.curvature ** 2)))
        quantum_purity = self.compute_quantum_purity()
        
        return {
            "step": self.step_count,
            "entanglement_entropy": entanglement_entropy,
            "curvature_rms": curvature_rms,
            "quantum_purity": quantum_purity,
            "wormhole_count": len(self.wormhole_nodes),
        }
    
    def get_state(self) -> Dict[str, Any]:
        """Get the current state of the fabric."""
        return {
            "num_qubits": self.num_qubits,
            "grid_size": self.grid_size,
            "step_count": self.step_count,
            "entanglement_entropy": self.compute_entanglement_entropy(),
            "curvature_rms": float(np.sqrt(np.mean(self.curvature ** 2))),
            "quantum_purity": self.compute_quantum_purity(),
            "wormhole_nodes": self.wormhole_nodes,
        }
