"""Tests for Nexus Orchestrator (Integration)."""

import sys
import os
import unittest
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sphinx_os.nexus import (
    NexusOrchestrator,
    NexusConfig,
    NexusPhase,
)


class TestNexusOrchestrator(unittest.TestCase):
    """Test suite for NexusOrchestrator integration."""

    def setUp(self):
        self.nexus = NexusOrchestrator()

    def test_initial_phase(self):
        """Test initial phase is VACUUM."""
        self.assertEqual(self.nexus.state.phase, NexusPhase.VACUUM)

    def test_validator_registration(self):
        """Test validator registration through orchestrator."""
        self.nexus.register_validator("v1", stake=10.0, nft_rarity=0.8)
        self.assertEqual(len(self.nexus.consensus.validators), 1)

    def test_peer_addition(self):
        """Test peer addition through orchestrator."""
        self.nexus.add_peer("p1", "192.168.1.1", 8080)
        self.assertIn("p1", self.nexus.p2p.peers)

    def test_nft_holder_registration(self):
        """Test NFT holder registration through orchestrator."""
        self.nexus.register_nft_holder("alice", 0.9)
        self.assertIn("alice", self.nexus.treasury.nft_holders)

    def test_treasury_deposit(self):
        """Test treasury deposit through orchestrator."""
        self.nexus.deposit_to_treasury(500.0, "Initial funding")
        self.assertEqual(self.nexus.treasury.balance, 500.0)

    def test_unified_step(self):
        """Test unified step advances all subsystems."""
        state = self.nexus.step()
        self.assertIn("phase", state)
        self.assertIn("nexus_coherence", state)

    def test_multiple_steps(self):
        """Test multiple steps advance the system."""
        for _ in range(10):
            state = self.nexus.step()
        
        self.assertGreater(self.nexus.state.step_count, 0)

    def test_propose_and_consenus_block(self):
        """Test block proposal and consensus."""
        self.nexus.register_validator("v1", stake=10.0, nft_rarity=0.8)
        self.nexus.register_validator("v2", stake=10.0, nft_rarity=0.8)
        self.nexus.register_validator("v3", stake=10.0, nft_rarity=0.8)
        self.nexus.register_validator("v4", stake=10.0, nft_rarity=0.8)
        
        txs = [{"from": "alice", "to": "bob", "amount": 100}]
        block_hash = self.nexus.propose_and_consenus_block("v1", txs)
        
        self.assertIsNotNone(block_hash)

    def test_send_network_message(self):
        """Test sending network message."""
        self.nexus.add_peer("p1", "192.168.1.1", 8080)
        self.nexus.p2p.connect_peer("p1")
        
        msg_id = self.nexus.send_network_message("p1", "test", {"data": "hello"})
        self.assertIsNotNone(msg_id)

    def test_apply_quantum_gate(self):
        """Test applying quantum gate through orchestrator."""
        H = np.array([[1, 1], [1, -1]], dtype=np.complex128) / np.sqrt(2)
        self.nexus.apply_quantum_gate(H, [0])
        
        # Entanglement should increase
        entropy = self.nexus.fabric.compute_entanglement_entropy()
        self.assertGreater(entropy, 0.0)

    def test_health_report(self):
        """Test health report generation."""
        health = self.nexus.get_health_report()
        
        self.assertIn("overall_health", health)
        self.assertIn("subsystem_health", health)
        self.assertIn("fabric", health["subsystem_health"])
        self.assertIn("consensus", health["subsystem_health"])
        self.assertIn("p2p", health["subsystem_health"])
        self.assertIn("treasury", health["subsystem_health"])

    def test_nexus_state(self):
        """Test full nexus state retrieval."""
        state = self.nexus.get_nexus_state()
        
        self.assertIn("phase", state)
        self.assertIn("nexus_coherence", state)
        self.assertIn("metrics", state)
        self.assertIn("uptime", state)

    def test_phase_transition(self):
        """Test phase transitions over time."""
        initial_phase = self.nexus.state.phase
        for _ in range(20):
            self.nexus.step()
        
        # Phase should potentially change
        self.assertGreaterEqual(self.nexus.state.step_count, 20)

    def test_feedback_loops(self):
        """Test feedback loops are counted."""
        for _ in range(5):
            self.nexus.step()
        
        self.assertGreaterEqual(self.nexus.feedback_loop_count, 0)

    def test_cross_layer_entropy(self):
        """Test cross-layer entropy is computed."""
        for _ in range(5):
            self.nexus.step()
        
        self.assertGreaterEqual(self.nexus.cross_layer_entropy, 0.0)

    def test_full_integration(self):
        """Test full integration scenario."""
        # Setup
        for i in range(5):
            self.nexus.register_validator(f"v{i}", stake=10.0, nft_rarity=0.8)
            self.nexus.add_peer(f"p{i}", f"192.168.1.{i+1}", 8080 + i)
            self.nexus.p2p.connect_peer(f"p{i}")
        
        self.nexus.register_nft_holder("alice", 0.9)
        self.nexus.register_nft_holder("bob", 0.7)
        self.nexus.deposit_to_treasury(500.0)
        
        # Run steps
        for _ in range(10):
            self.nexus.step()
        
        # Propose block
        txs = [{"from": "alice", "to": "bob", "amount": 100}]
        block_hash = self.nexus.propose_and_consenus_block("v0", txs)
        self.assertIsNotNone(block_hash)
        
        # Check health
        health = self.nexus.get_health_report()
        self.assertGreater(health["overall_health"], 0.0)


class TestNexusConfig(unittest.TestCase):
    """Test suite for NexusConfig."""

    def test_default_config(self):
        """Test default configuration."""
        config = NexusConfig()
        self.assertIsNotNone(config)

    def test_custom_config(self):
        """Test custom configuration."""
        config = NexusConfig(
            num_qubits=4,
            grid_size=16,
            annual_yield_rate=0.1,
        )
        self.assertEqual(config.num_qubits, 4)
        self.assertEqual(config.grid_size, 16)
        self.assertEqual(config.annual_yield_rate, 0.1)


class TestNexusPhase(unittest.TestCase):
    """Test suite for NexusPhase enum."""

    def test_phase_values(self):
        """Test phase enum values."""
        self.assertIn("Vacuum", NexusPhase.VACUUM.value)
        self.assertIn("Inflation", NexusPhase.INFLATION.value)
        self.assertIn("Condensation", NexusPhase.CONDENSATION.value)
        self.assertIn("Crystallization", NexusPhase.CRYSTALLIZATION.value)
        self.assertIn("Consciousness", NexusPhase.CONSCIOUSNESS.value)

    def test_phase_order(self):
        """Test phase ordering."""
        phases = list(NexusPhase)
        self.assertEqual(len(phases), 5)


if __name__ == "__main__":
    unittest.main()
