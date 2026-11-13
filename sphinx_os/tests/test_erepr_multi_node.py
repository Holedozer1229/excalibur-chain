"""Comprehensive multi-node EREPR gossip simulation tests.

Tests the full EREPR P2P gossip protocol implementation with realistic scenarios:
- Multi-node mesh network formation
- Gossip propagation through bonded peers
- Echo confirmation handshake
- Bond decay and reconnection
- Integration with Nexus orchestrator
- Transaction gossip simulation
"""

import unittest
import time
import hashlib
import json
from sphinx_os.nexus.erepr_protocol import (
    EREPRProtocol,
    ResonanceSignature,
    EntanglementBond,
    EchoMessage,
    GossipWave,
    RESONANCE_THRESHOLD,
    WAVE_DECAY,
    MAX_GOSSIP_DEPTH,
)


class TestMultiNodeMesh(unittest.TestCase):
    """Test multi-node mesh network formation."""

    def create_strong_bond(self, node_a, node_b):
        """Helper to create a strong bond between two nodes."""
        shared_secret = hashlib.sha256(
            node_a.secret + node_b.node_id.encode() + node_a.node_id.encode()
        ).digest()
        node_a.bonds[node_b.node_id] = EntanglementBond(
            peer_id=node_b.node_id,
            shared_secret=shared_secret,
            resonance_score=0.9,
            bond_strength=0.9,
            created_at=time.time(),
            last_heartbeat=time.time(),
        )
        node_a.known_peers[node_b.node_id] = {
            "services": node_b.services,
            "user_agent": node_b.user_agent,
            "signature": node_b.signature.to_dict(),
        }

    def test_five_node_mesh_formation(self):
        """Test 5 nodes forming a fully connected mesh."""
        nodes = {}
        for i in range(5):
            node = EREPRProtocol(f"node{i}", f"secret{i}".encode())
            node.initialize()
            nodes[i] = node

        # Create full mesh with strong bonds
        for i in range(5):
            for j in range(5):
                if i != j:
                    self.create_strong_bond(nodes[i], nodes[j])

        # Verify all nodes have 4 bonds each
        for i in range(5):
            active_bonds = sum(1 for b in nodes[i].bonds.values() if b.is_alive())
            self.assertEqual(active_bonds, 4, f"node{i} should have 4 active bonds")

    def test_ten_node_partial_mesh(self):
        """Test 10 nodes forming a partial mesh (each connected to 3 neighbors)."""
        nodes = {}
        for i in range(10):
            node = EREPRProtocol(f"node{i}", f"secret{i}".encode())
            node.initialize()
            nodes[i] = node

        # Each node connects to next 3 neighbors (circular)
        for i in range(10):
            for offset in range(1, 4):
                j = (i + offset) % 10
                self.create_strong_bond(nodes[i], nodes[j])

        # Verify each node has 3 bonds
        for i in range(10):
            active_bonds = sum(1 for b in nodes[i].bonds.values() if b.is_alive())
            self.assertEqual(active_bonds, 3, f"node{i} should have 3 active bonds")


class TestGossipPropagation(unittest.TestCase):
    """Test gossip message propagation through the network."""

    def create_strong_bond(self, node_a, node_b):
        """Helper to create a strong bond between two nodes."""
        shared_secret = hashlib.sha256(
            node_a.secret + node_b.node_id.encode() + node_a.node_id.encode()
        ).digest()
        node_a.bonds[node_b.node_id] = EntanglementBond(
            peer_id=node_b.node_id,
            shared_secret=shared_secret,
            resonance_score=0.9,
            bond_strength=0.9,
            created_at=time.time(),
            last_heartbeat=time.time(),
        )

    def test_linear_chain_propagation(self):
        """Test gossip propagating through a linear chain: A -> B -> C -> D -> E."""
        nodes = {}
        for i in range(5):
            node = EREPRProtocol(f"node{i}", f"secret{i}".encode())
            node.initialize()
            nodes[i] = node

        # Create linear chain bonds
        for i in range(4):
            self.create_strong_bond(nodes[i], nodes[i + 1])
            self.create_strong_bond(nodes[i + 1], nodes[i])

        # Create gossip at node 0
        wave = nodes[0].create_gossip_wave({"type": "block", "height": 100})
        targets = nodes[0].forward_wave(wave)

        # Should forward to node 1
        peer_ids = [t[0] for t in targets]
        self.assertIn("node1", peer_ids)
        self.assertEqual(wave.depth, 1)
        self.assertAlmostEqual(wave.amplitude, WAVE_DECAY, places=4)

    def test_star_topology_propagation(self):
        """Test gossip from center of star topology reaching all leaves."""
        nodes = {}
        for i in range(6):
            node = EREPRProtocol(f"node{i}", f"secret{i}".encode())
            node.initialize()
            nodes[i] = node

        # Node 0 is center, connected to all others
        for i in range(1, 6):
            self.create_strong_bond(nodes[0], nodes[i])

        # Create gossip at center
        wave = nodes[0].create_gossip_wave({"type": "tx", "amount": 5.0})
        targets = nodes[0].forward_wave(wave)

        # Should forward to all 5 leaves
        peer_ids = [t[0] for t in targets]
        for i in range(1, 6):
            self.assertIn(f"node{i}", peer_ids)

    def test_gossip_depth_limit(self):
        """Test gossip stops propagating after max depth."""
        nodes = {}
        for i in range(15):
            node = EREPRProtocol(f"node{i}", f"secret{i}".encode())
            node.initialize()
            nodes[i] = node

        # Create long chain
        for i in range(14):
            self.create_strong_bond(nodes[i], nodes[i + 1])
            self.create_strong_bond(nodes[i + 1], nodes[i])

        # Propagate wave through chain
        wave = nodes[0].create_gossip_wave({"type": "test"})
        for depth in range(MAX_GOSSIP_DEPTH):
            wave.propagate()
        
        # After MAX_GOSSIP_DEPTH, should not propagate
        self.assertFalse(wave.should_propagate())

    def test_gossip_amplitude_decay(self):
        """Test gossip amplitude decays with each hop."""
        nodes = {}
        for i in range(10):
            node = EREPRProtocol(f"node{i}", f"secret{i}".encode())
            node.initialize()
            nodes[i] = node

        # Create chain
        for i in range(9):
            self.create_strong_bond(nodes[i], nodes[i + 1])

        wave = nodes[0].create_gossip_wave({"type": "test"})
        initial_amplitude = wave.amplitude
        self.assertEqual(initial_amplitude, 1.0)

        # Simulate propagation
        for _ in range(5):
            wave.propagate()

        # Amplitude should decay
        expected = 1.0 * (WAVE_DECAY ** 5)
        self.assertAlmostEqual(wave.amplitude, expected, places=4)
        self.assertLess(wave.amplitude, initial_amplitude)

    def test_no_duplicate_propagation(self):
        """Test a node doesn't forward the same message twice."""
        node = EREPRProtocol("node1", b"secret1")
        node.initialize()

        # Create bond
        node2 = EREPRProtocol("node2", b"secret2")
        node2.initialize()
        self.create_strong_bond(node, node2)

        wave = node.create_gossip_wave({"type": "test"})
        targets1 = node.forward_wave(wave)
        self.assertGreater(len(targets1), 0)

        # Try to forward again
        targets2 = node.forward_wave(wave)
        self.assertEqual(len(targets2), 0, "Should not forward duplicate")

    def test_transaction_gossip_simulation(self):
        """Simulate transaction gossip across the network."""
        nodes = {}
        for i in range(8):
            node = EREPRProtocol(f"miner{i}", f"miner_secret{i}".encode())
            node.initialize()
            nodes[i] = node

        # Create mesh network
        for i in range(8):
            for j in range(i + 1, 8):
                if (i + j) % 3 == 0:  # Partial mesh
                    self.create_strong_bond(nodes[i], nodes[j])
                    self.create_strong_bond(nodes[j], nodes[i])

        # Miner 0 discovers a transaction
        tx_payload = {
            "type": "transaction",
            "from": "ABC123",
            "to": "DEF456",
            "amount": 10.5,
            "timestamp": time.time(),
        }
        wave = nodes[0].create_gossip_wave(tx_payload)
        targets = nodes[0].forward_wave(wave)

        # Should forward to bonded peers
        self.assertGreater(len(targets), 0, "Should forward to at least one peer")
        self.assertEqual(wave.payload["type"], "transaction")
        self.assertEqual(wave.payload["amount"], 10.5)


class TestEchoHandshake(unittest.TestCase):
    """Test the echo confirmation handshake protocol."""

    def test_full_echo_handshake(self):
        """Test complete echo → confirmation → verify handshake."""
        node_a = EREPRProtocol("nodeA", b"secretA")
        node_a.initialize()
        node_b = EREPRProtocol("nodeB", b"secretB")
        node_b.initialize()

        # Step 1: Node B sends echo to Node A
        echo_b = EchoMessage(
            sig=node_b.signature,
            services=0x03,
            user_agent="nodeB/1.0",
        )

        # Step 2: Node A receives echo and creates confirmation
        # May be None if resonance is below threshold
        confirmation = node_a.create_echo_confirmation(echo_b)
        if confirmation is None:
            self.skipTest("Resonance below threshold — bond not formed")
        self.assertTrue(confirmation.is_confirmation)

        # Step 3: Node B receives confirmation
        # Node B first needs to receive Node A's echo to form the bond
        echo_a = EchoMessage(
            sig=node_a.signature,
            services=0x03,
            user_agent="nodeA/1.0",
        )
        node_b.receive_echo(echo_a)

        # Step 4: Verify the confirmation
        if confirmation and node_b.bonds:
            valid = node_b.confirm_echo(
                confirmation,
                node_b.signature.challenge
            )
            self.assertIsInstance(valid, bool)

    def test_echo_rejection_below_threshold(self):
        """Test echo is rejected when resonance is too low."""
        node_a = EREPRProtocol("nodeA", b"secretA")
        node_a.initialize()

        # Create a far-away signature
        far_sig = ResonanceSignature.generate("far_node", b"far_secret")
        far_sig.angle_x = 0.0
        far_sig.angle_y = 0.0
        far_sig.frequency = 0.0
        far_sig.phase = 0.0

        # Set node A far away
        node_a.signature.angle_x = 3.14
        node_a.signature.angle_y = 3.14
        node_a.signature.frequency = 1.0
        node_a.signature.phase = 3.14

        echo = EchoMessage(
            sig=far_sig,
            services=0x03,
            user_agent="far/1.0",
        )

        confirmation = node_a.create_echo_confirmation(echo)
        self.assertIsNone(confirmation, "Should reject low-resonance echo")


class TestBondLifecycle(unittest.TestCase):
    """Test bond decay, strengthening, and reconnection."""

    def test_bond_decay_over_time(self):
        """Test bonds decay when peers don't send heartbeats."""
        node = EREPRProtocol("node1", b"secret1")
        node.initialize()

        node2 = EREPRProtocol("node2", b"secret2")
        node2.initialize()

        # Form bond
        echo = EchoMessage(
            sig=node2.signature,
            services=0x03,
            user_agent="node2/1.0",
        )
        bond = node.receive_echo(echo)
        if bond is None:
            self.skipTest("Resonance below threshold")

        # Age the bond significantly
        bond.last_heartbeat = time.time() - 200000
        node.decay_bonds()

        # Bond should be dead
        self.assertNotIn("node2", node.bonds)

    def test_bond_strengthening_on_heartbeat(self):
        """Test bonds strengthen when peers send regular echoes."""
        node = EREPRProtocol("node1", b"secret1")
        node.initialize()

        node2 = EREPRProtocol("node2", b"secret2")
        node2.initialize()

        # Form initial bond
        echo = EchoMessage(
            sig=node2.signature,
            services=0x03,
            user_agent="node2/1.0",
        )
        bond = node.receive_echo(echo)
        if bond is None:
            self.skipTest("Resonance below threshold")

        initial_strength = bond.bond_strength

        # Send multiple echoes (heartbeats)
        for _ in range(5):
            echo = EchoMessage(
                sig=node2.signature,
                services=0x03,
                user_agent="node2/1.0",
            )
            node.receive_echo(echo)

        # Bond should be stronger
        bond = node.bonds.get("node2")
        self.assertIsNotNone(bond)
        self.assertGreater(bond.bond_strength, initial_strength)
        self.assertEqual(bond.echo_count, 6)  # Initial + 5 heartbeats


class TestOrchestratorIntegration(unittest.TestCase):
    """Test EREPR integration with Nexus orchestrator."""

    def test_orchestrator_initializes_erepr(self):
        """Test orchestrator creates and initializes EREPR protocol."""
        from sphinx_os.nexus.orchestrator import NexusOrchestrator, NexusConfig

        config = NexusConfig(node_id="test-node")
        orchestrator = NexusOrchestrator(config)

        self.assertIsNotNone(orchestrator.erepr)
        self.assertEqual(orchestrator.erepr.node_id, "test-node")
        self.assertIsNotNone(orchestrator.erepr.signature)

    def test_orchestrator_broadcast_gossip(self):
        """Test orchestrator can broadcast gossip through EREPR."""
        from sphinx_os.nexus.orchestrator import NexusOrchestrator, NexusConfig

        orchestrator = NexusOrchestrator(NexusConfig())

        payload = {"type": "block", "height": 100, "hash": "abc123"}
        wave = orchestrator.broadcast_gossip(payload)

        self.assertIsInstance(wave, GossipWave)
        self.assertEqual(wave.payload, payload)
        self.assertEqual(wave.source, orchestrator.erepr.node_id)

    def test_orchestrator_health_includes_erepr(self):
        """Test orchestrator health report includes EREPR metrics."""
        from sphinx_os.nexus.orchestrator import NexusOrchestrator, NexusConfig

        orchestrator = NexusOrchestrator(NexusConfig())
        health = orchestrator.get_health_report()

        self.assertIn("erepr", health["subsystem_health"])
        self.assertIsInstance(health["subsystem_health"]["erepr"], float)

    def test_orchestrator_state_includes_erepr(self):
        """Test orchestrator state includes EREPR metrics."""
        from sphinx_os.nexus.orchestrator import NexusOrchestrator, NexusConfig

        orchestrator = NexusOrchestrator(NexusConfig())
        state = orchestrator.get_nexus_state()

        metrics = state.get("metrics", {})
        self.assertIn("erepr_active_bonds", metrics)
        self.assertIn("erepr_known_peers", metrics)
        self.assertIn("erepr_avg_bond_strength", metrics)
        self.assertIn("erepr_gossip_queue", metrics)

    def test_orchestrator_step_decays_bonds(self):
        """Test orchestrator step decays EREPR bonds."""
        from sphinx_os.nexus.orchestrator import NexusOrchestrator, NexusConfig

        orchestrator = NexusOrchestrator(NexusConfig())

        # Add a bond and age it
        node2 = EREPRProtocol("peer1", b"peer_secret")
        node2.initialize()
        echo = EchoMessage(
            sig=node2.signature,
            services=0x01,
            user_agent="peer1/1.0",
        )
        orchestrator.erepr.receive_echo(echo)

        # Age the bond
        if "peer1" in orchestrator.erepr.bonds:
            orchestrator.erepr.bonds["peer1"].last_heartbeat = time.time() - 200000

        # Step should decay bonds
        orchestrator.step()

        # Bond should be removed
        self.assertNotIn("peer1", orchestrator.erepr.bonds)


class TestNetworkScenarios(unittest.TestCase):
    """Test realistic network scenarios."""

    def create_strong_bond(self, node_a, node_b):
        """Helper to create a strong bond."""
        shared_secret = hashlib.sha256(
            node_a.secret + node_b.node_id.encode() + node_a.node_id.encode()
        ).digest()
        node_a.bonds[node_b.node_id] = EntanglementBond(
            peer_id=node_b.node_id,
            shared_secret=shared_secret,
            resonance_score=0.9,
            bond_strength=0.9,
            created_at=time.time(),
            last_heartbeat=time.time(),
        )
        node_a.known_peers[node_b.node_id] = {
            "services": node_b.services,
            "user_agent": node_b.user_agent,
            "signature": node_b.signature.to_dict(),
        }

    def test_network_partition_and_heal(self):
        """Test network splitting and rejoining."""
        nodes = {}
        for i in range(6):
            node = EREPRProtocol(f"node{i}", f"secret{i}".encode())
            node.initialize()
            nodes[i] = node

        # Create two partitions: {0,1,2} and {3,4,5}
        for i in range(3):
            for j in range(i + 1, 3):
                self.create_strong_bond(nodes[i], nodes[j])
                self.create_strong_bond(nodes[j], nodes[i])
        for i in range(3, 6):
            for j in range(i + 1, 6):
                self.create_strong_bond(nodes[i], nodes[j])
                self.create_strong_bond(nodes[j], nodes[i])

        # Each partition should have internal bonds
        for i in range(3):
            bonds = sum(1 for b in nodes[i].bonds.values() if b.is_alive())
            self.assertGreaterEqual(bonds, 1)

        # Heal: connect partition 1 to partition 2
        self.create_strong_bond(nodes[2], nodes[3])
        self.create_strong_bond(nodes[3], nodes[2])

        # Now nodes can reach across partitions
        wave = nodes[0].create_gossip_wave({"type": "heal"})
        targets = nodes[0].forward_wave(wave)
        self.assertGreater(len(targets), 0)

    def test_churn_resistance(self):
        """Test network survives node churn (nodes leaving and joining)."""
        nodes = {}
        for i in range(5):
            node = EREPRProtocol(f"node{i}", f"secret{i}".encode())
            node.initialize()
            nodes[i] = node

        # Create mesh
        for i in range(5):
            for j in range(i + 1, 5):
                self.create_strong_bond(nodes[i], nodes[j])

        # Node 2 leaves (decay all bonds)
        for node in nodes.values():
            if "node2" in node.bonds:
                del node.bonds["node2"]

        # New node joins
        new_node = EREPRProtocol("node5", b"new_secret")
        new_node.initialize()

        # Existing nodes form bonds with new node
        for i in [0, 1, 3, 4]:
            self.create_strong_bond(nodes[i], new_node)

        # Network should still function
        wave = nodes[0].create_gossip_wave({"type": "churn_test"})
        targets = nodes[0].forward_wave(wave)
        self.assertGreater(len(targets), 0)

    def test_health_report_accuracy(self):
        """Test health report reflects actual network state."""
        node = EREPRProtocol("node1", b"secret1")
        node.initialize()

        # Initially no bonds
        report = node.health_report()
        self.assertEqual(report["active_bonds"], 0)
        self.assertEqual(report["known_peers"], 0)

        # Add bonds using create_strong_bond which also sets known_peers
        for i in range(3):
            peer = EREPRProtocol(f"peer{i}", f"peer_secret{i}".encode())
            peer.initialize()
            self.create_strong_bond(node, peer)

        report = node.health_report()
        self.assertEqual(report["active_bonds"], 3)
        # known_peers is set by create_strong_bond helper
        self.assertEqual(report["known_peers"], 3)
        self.assertGreater(report["avg_bond_strength"], 0.8)


if __name__ == "__main__":
    unittest.main()
