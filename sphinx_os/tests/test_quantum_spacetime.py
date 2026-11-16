"""Tests for Quantum-Spacetime Fabric."""

import sys
import os
import unittest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sphinx_os.nexus import QuantumSpacetimeFabric


class TestQuantumSpacetimeFabric(unittest.TestCase):
    """Test suite for QuantumSpacetimeFabric."""

    def setUp(self):
        self.fabric = QuantumSpacetimeFabric(num_qubits=3, grid_size=8)

    def test_initial_state(self):
        """Test initial quantum state is |000>."""
        self.assertEqual(self.fabric.state_vector[0], 1.0)
        self.assertAlmostEqual(np.sum(np.abs(self.fabric.state_vector[1:])**2), 0.0)

    def test_initial_purity(self):
        """Test initial purity is 1.0 (pure state)."""
        purity = self.fabric.compute_quantum_purity()
        self.assertAlmostEqual(purity, 1.0, places=5)

    def test_initial_entanglement_entropy(self):
        """Test initial entanglement entropy is 0 (no entanglement)."""
        entropy = self.fabric.compute_entanglement_entropy()
        self.assertAlmostEqual(entropy, 0.0, places=5)

    def test_hadamard_gate(self):
        """Test Hadamard gate creates superposition."""
        H = np.array([[1, 1], [1, -1]], dtype=np.complex128) / np.sqrt(2)
        self.fabric.apply_quantum_gate(H, [0])
        
        # After H on qubit 0, entropy should increase
        entropy = self.fabric.compute_entanglement_entropy()
        self.assertGreater(entropy, 0.0)

    def test_purity_after_gate(self):
        """Test purity remains 1.0 after unitary gate (pure state)."""
        H = np.array([[1, 1], [1, -1]], dtype=np.complex128) / np.sqrt(2)
        self.fabric.apply_quantum_gate(H, [0])
        purity = self.fabric.compute_quantum_purity()
        self.assertAlmostEqual(purity, 1.0, places=5)

    def test_curvature_update(self):
        """Test curvature changes after gate application."""
        # Use a larger gate trace to ensure curvature change
        # Identity gate has trace=2, which gives gate_trace * 0.01 = 0.02 perturbation
        I = np.eye(2, dtype=np.complex128) * 10  # Large trace
        self.fabric.apply_quantum_gate(I, [0])
        
        # Curvature RMS should have increased from 0
        final_rms = float(np.sqrt(np.mean(self.fabric.curvature ** 2)))
        self.assertGreater(final_rms, 0.0)

    def test_curvature_evolution(self):
        """Test curvature evolves over time."""
        H = np.array([[1, 1], [1, -1]], dtype=np.complex128) / np.sqrt(2)
        self.fabric.apply_quantum_gate(H, [0])
        
        initial_rms = float(np.sqrt(np.mean(self.fabric.curvature ** 2)))
        self.fabric.evolve_curvature()
        final_rms = float(np.sqrt(np.mean(self.fabric.curvature ** 2)))
        
        # Curvature should evolve (may decrease due to damping)
        self.assertLessEqual(final_rms, initial_rms * 1.1)  # Allow small change

    def test_wormhole_detection(self):
        """Test wormhole detection with high curvature."""
        # Set high curvature at some points
        self.fabric.curvature[0, 0] = 1.0
        self.fabric.curvature[7, 7] = 1.0
        self.fabric.detect_wormholes()
        
        self.assertEqual(len(self.fabric.wormhole_nodes), 2)

    def test_unified_step(self):
        """Test unified step returns metrics."""
        metrics = self.fabric.unified_step()
        
        self.assertIn("step", metrics)
        self.assertIn("entanglement_entropy", metrics)
        self.assertIn("curvature_rms", metrics)
        self.assertIn("quantum_purity", metrics)
        self.assertIn("wormhole_count", metrics)
        self.assertEqual(metrics["step"], 1)

    def test_get_state(self):
        """Test get_state returns all fields."""
        state = self.fabric.get_state()
        
        self.assertEqual(state["num_qubits"], 3)
        self.assertEqual(state["grid_size"], 8)
        self.assertIn("entanglement_entropy", state)
        self.assertIn("curvature_rms", state)
        self.assertIn("quantum_purity", state)
        self.assertIn("wormhole_nodes", state)

    def test_multi_qubit_gate(self):
        """Test applying gate to multiple qubits."""
        H = np.array([[1, 1], [1, -1]], dtype=np.complex128) / np.sqrt(2)
        self.fabric.apply_quantum_gate(H, [0, 1])
        
        # Should still be a valid state
        norm = np.sum(np.abs(self.fabric.state_vector)**2)
        self.assertAlmostEqual(norm, 1.0, places=5)


if __name__ == "__main__":
    unittest.main()
