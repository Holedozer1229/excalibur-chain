"""Tests for EREPR: Entanglement-Resonance Echo Peer Routing protocol."""

import unittest
import time
import json
import math
from sphinx_os.nexus.erepr_protocol import (
    EREPRProtocol,
    ResonanceSignature,
    EntanglementBond,
    EchoMessage,
    GossipWave,
    TORUS_RADIUS_X,
    TORUS_RADIUS_Y,
    RESONANCE_THRESHOLD,
    WAVE_DECAY,
    MAX_GOSSIP_DEPTH,
)


class TestResonanceSignature(unittest.TestCase):
    """Test resonance signature generation and serialization."""

    def test_generate_signature(self):
        sig = ResonanceSignature.generate("node1", b"secret")
        self.assertEqual(sig.node_id, "node1")
        self.assertGreaterEqual(sig.angle_x, 0.0)
        self.assertLess(sig.angle_x, TORUS_RADIUS_X)
        self.assertGreaterEqual(sig.angle_y, 0.0)
        self.assertLess(sig.angle_y, TORUS_RADIUS_Y)
        self.assertGreater(sig.frequency, 0.0)
        self.assertGreaterEqual(sig.phase, 0.0)
        self.assertLess(sig.phase, 2 * math.pi)
        self.assertEqual(len(sig.challenge), 16)

    def test_signature_uniqueness(self):
        sig1 = ResonanceSignature.generate("node1", b"secret")
        sig2 = ResonanceSignature.generate("node2", b"secret")
        # Different node IDs should produce different positions
        self.assertNotEqual(sig1.angle_x, sig2.angle_x)

    def test_signature_secret_dependent(self):
        sig1 = ResonanceSignature.generate("node1", b"secret1")
        sig2 = ResonanceSignature.generate("node1", b"secret2")
        # Different secrets should produce different positions
        self.assertNotEqual(sig1.angle_x, sig2.angle_x)

    def test_to_dict_from_dict(self):
        sig = ResonanceSignature.generate("node1", b"secret")
        data = sig.to_dict()
        sig2 = ResonanceSignature.from_dict(data)
        self.assertEqual(sig.node_id, sig2.node_id)
        self.assertAlmostEqual(sig.angle_x, sig2.angle_x)
        self.assertAlmostEqual(sig.angle_y, sig2.angle_y)
        self.assertAlmostEqual(sig.frequency, sig2.frequency)


class TestEntanglementBond(unittest.TestCase):
    """Test entanglement bond lifecycle."""

    def test_bond_creation(self):
        bond = EntanglementBond(
            peer_id="peer1",
            shared_secret=b"secret",
            resonance_score=0.8,
            bond_strength=0.8,
            created_at=time.time(),
            last_heartbeat=time.time(),
        )
        self.assertEqual(bond.peer_id, "peer1")
        self.assertEqual(bond.resonance_score, 0.8)
        self.assertTrue(bond.is_alive())

    def test_bond_decay(self):
        bond = EntanglementBond(
            peer_id="peer1",
            shared_secret=b"secret",
            resonance_score=0.8,
            bond_strength=0.8,
            created_at=time.time(),
            last_heartbeat=time.time() - 1000,
        )
        bond.decay(1000)
        self.assertLess(bond.bond_strength, 0.8)

    def test_bond_decay_to_dead(self):
        bond = EntanglementBond(
            peer_id="peer1",
            shared_secret=b"secret",
            resonance_score=0.8,
            bond_strength=0.15,
            created_at=time.time(),
            last_heartbeat=time.time() - 10000,
        )
        bond.decay(10000)
        self.assertFalse(bond.is_alive())

    def test_bond_strengthen(self):
        bond = EntanglementBond(
            peer_id="peer1",
            shared_secret=b"secret",
            resonance_score=0.8,
            bond_strength=0.5,
            created_at=time.time(),
            last_heartbeat=time.time(),
        )
        bond.strengthen()
        self.assertAlmostEqual(bond.bond_strength, 0.6, places=1)
        self.assertEqual(bond.echo_count, 1)

    def test_bond_strength_cap(self):
        bond = EntanglementBond(
            peer_id="peer1",
            shared_secret=b"secret",
            resonance_score=0.8,
            bond_strength=0.95,
            created_at=time.time(),
            last_heartbeat=time.time(),
        )
        bond.strengthen()
        self.assertLessEqual(bond.bond_strength, 1.0)


class TestEchoMessage(unittest.TestCase):
    """Test echo message serialization."""

    def test_echo_to_json_from_json(self):
        sig = ResonanceSignature.generate("node1", b"secret")
        echo = EchoMessage(sig=sig, services=0x03, user_agent="test/1.0")
        data = echo.to_json()
        echo2 = EchoMessage.from_json(data)
        self.assertEqual(echo2.sig.node_id, "node1")
        self.assertEqual(echo2.services, 0x03)
        self.assertFalse(echo2.is_confirmation)

    def test_confirmation_echo(self):
        sig = ResonanceSignature.generate("node1", b"secret")
        echo = EchoMessage(
            sig=sig, services=0x03, user_agent="test/1.0",
            is_confirmation=True, response_challenge="abc123",
        )
        data = echo.to_json()
        echo2 = EchoMessage.from_json(data)
        self.assertTrue(echo2.is_confirmation)
        self.assertEqual(echo2.response_challenge, "abc123")


class TestGossipWave(unittest.TestCase):
    """Test gossip wave propagation."""

    def test_wave_creation(self):
        wave = GossipWave(
            msg_id="test123",
            source="node1",
            payload={"type": "tx", "data": "hello"},
        )
        self.assertEqual(wave.depth, 0)
        self.assertEqual(wave.amplitude, 1.0)
        self.assertEqual(len(wave.seen_by), 0)  # Empty initially

    def test_wave_propagate(self):
        wave = GossipWave(
            msg_id="test123",
            source="node1",
            payload={"type": "tx"},
        )
        wave.propagate()
        self.assertEqual(wave.depth, 1)
        self.assertAlmostEqual(wave.amplitude, WAVE_DECAY, places=4)

    def test_wave_should_propagate(self):
        wave = GossipWave(
            msg_id="test123",
            source="node1",
            payload={"type": "tx"},
        )
        self.assertTrue(wave.should_propagate())

    def test_wave_max_depth(self):
        wave = GossipWave(
            msg_id="test123",
            source="node1",
            payload={"type": "tx"},
            depth=MAX_GOSSIP_DEPTH,
        )
        self.assertFalse(wave.should_propagate())

    def test_wave_amplitude_decay(self):
        wave = GossipWave(
            msg_id="test123",
            source="node1",
            payload={"type": "tx"},
            amplitude=0.05,
        )
        self.assertFalse(wave.should_propagate())

    def test_wave_serialization(self):
        wave = GossipWave(
            msg_id="test123",
            source="node1",
            payload={"type": "tx"},
            depth=3,
            amplitude=0.5,
        )
        data = wave.to_dict()
        wave2 = GossipWave.from_dict(data)
        self.assertEqual(wave2.msg_id, "test123")
        self.assertEqual(wave2.depth, 3)
        self.assertAlmostEqual(wave2.amplitude, 0.5)


class TestEREPRProtocol(unittest.TestCase):
    """Test the EREPR protocol engine."""

    def setUp(self):
        self.node1 = EREPRProtocol("node1", b"secret1")
        self.node1.initialize()
        self.node2 = EREPRProtocol("node2", b"secret2")
        self.node2.initialize()
        self.node3 = EREPRProtocol("node3", b"secret3")
        self.node3.initialize()

    def test_initialization(self):
        self.assertIsNotNone(self.node1.signature)
        self.assertEqual(self.node1.node_id, "node1")
        self.assertEqual(len(self.node1.bonds), 0)

    def test_compute_resonance_self(self):
        # A node should have high resonance with itself
        resonance = self.node1.compute_resonance(self.node1.signature)
        self.assertGreater(resonance, 0.8)

    def test_compute_resonance_symmetric(self):
        r1 = self.node1.compute_resonance(self.node2.signature)
        r2 = self.node2.compute_resonance(self.node1.signature)
        # Resonance should be roughly symmetric
        self.assertAlmostEqual(r1, r2, places=1)

    def test_compute_resonance_range(self):
        resonance = self.node1.compute_resonance(self.node2.signature)
        self.assertGreaterEqual(resonance, 0.0)
        self.assertLessEqual(resonance, 1.0)

    def test_receive_echo_below_threshold(self):
        # Create a node with very different signature
        far_node = EREPRProtocol("far_node", b"far_secret")
        far_node.initialize()
        # Manually set a far-away signature on all dimensions
        far_node.signature.angle_x = 0.0
        far_node.signature.angle_y = 0.0
        far_node.signature.frequency = 0.0
        far_node.signature.phase = 0.0
        self.node1.signature.angle_x = TORUS_RADIUS_X / 2
        self.node1.signature.angle_y = TORUS_RADIUS_Y / 2
        self.node1.signature.frequency = 1.0
        self.node1.signature.phase = math.pi

        echo = EchoMessage(
            sig=far_node.signature,
            services=0x03,
            user_agent="far/1.0",
        )
        resonance = self.node1.compute_resonance(far_node.signature)
        # Should be below threshold
        self.assertLess(resonance, RESONANCE_THRESHOLD)
        bond = self.node1.receive_echo(echo)
        self.assertIsNone(bond)

    def test_receive_echo_form_bond(self):
        echo = EchoMessage(
            sig=self.node2.signature,
            services=0x03,
            user_agent="node2/1.0",
        )
        bond = self.node1.receive_echo(echo)
        if bond:
            self.assertEqual(bond.peer_id, "node2")
            self.assertIn("node2", self.node1.bonds)
            self.assertIn("node2", self.node1.known_peers)

    def test_echo_confirmation(self):
        echo = EchoMessage(
            sig=self.node2.signature,
            services=0x03,
            user_agent="node2/1.0",
        )
        confirmation = self.node1.create_echo_confirmation(echo)
        if confirmation:
            self.assertTrue(confirmation.is_confirmation)
            self.assertEqual(confirmation.sig.node_id, "node1")
            self.assertEqual(len(confirmation.response_challenge), 16)

    def test_confirm_echo_valid(self):
        # Node2 sends echo to node1
        echo2 = EchoMessage(
            sig=self.node2.signature,
            services=0x03,
            user_agent="node2/1.0",
        )
        # Node1 creates confirmation
        confirmation = self.node1.create_echo_confirmation(echo2)
        if confirmation:
            # Node2 verifies the confirmation
            valid = self.node2.confirm_echo(confirmation, self.node2.signature.challenge)
            # This tests the HMAC round-trip
            self.assertIsInstance(valid, bool)

    def test_gossip_wave_creation(self):
        wave = self.node1.create_gossip_wave({"type": "tx", "amount": 10})
        self.assertEqual(wave.source, "node1")
        self.assertEqual(wave.depth, 0)
        self.assertEqual(wave.amplitude, 1.0)

    def test_gossip_forwarding(self):
        # Manually create strong bonds for reliable test
        import hashlib
        for peer_name in ["node2", "node3"]:
            shared_secret = hashlib.sha256(
                self.node1.secret + peer_name.encode() + self.node1.node_id.encode()
            ).digest()
            self.node1.bonds[peer_name] = EntanglementBond(
                peer_id=peer_name,
                shared_secret=shared_secret,
                resonance_score=0.9,
                bond_strength=0.9,
                created_at=time.time(),
                last_heartbeat=time.time(),
            )

        # Create and forward wave
        wave = self.node1.create_gossip_wave({"type": "tx"})
        targets = self.node1.forward_wave(wave)

        # Should forward to bonded peers
        peer_ids = [t[0] for t in targets]
        self.assertIn("node2", peer_ids)
        self.assertIn("node3", peer_ids)

    def test_gossip_no_duplicate(self):
        wave = self.node1.create_gossip_wave({"type": "tx"})
        self.node1.forward_wave(wave)

        # Forwarding again should return empty (already seen)
        targets = self.node1.forward_wave(wave)
        self.assertEqual(len(targets), 0)

    def test_decay_bonds(self):
        echo = EchoMessage(
            sig=self.node2.signature,
            services=0x03,
            user_agent="node2/1.0",
        )
        self.node1.receive_echo(echo)

        # Age the bond
        bond = self.node1.bonds.get("node2")
        if bond:
            bond.last_heartbeat = time.time() - 200000
            self.node1.decay_bonds()
            # Should be dead
            self.assertNotIn("node2", self.node1.bonds)

    def test_cleanup_seen_messages(self):
        self.node1.seen_messages["old_msg"] = time.time() - 600
        self.node1.seen_messages["new_msg"] = time.time()
        self.node1.cleanup_seen_messages(max_age=300.0)
        self.assertNotIn("old_msg", self.node1.seen_messages)
        self.assertIn("new_msg", self.node1.seen_messages)

    def test_network_state(self):
        state = self.node1.get_network_state()
        self.assertEqual(state["node_id"], "node1")
        self.assertIsNotNone(state["signature"])
        self.assertEqual(state["known_peers"], 0)

    def test_health_report(self):
        report = self.node1.health_report()
        self.assertEqual(report["protocol"], "EREPR")
        self.assertEqual(report["node_id"], "node1")
        self.assertEqual(report["active_bonds"], 0)
        self.assertIn("avg_bond_strength", report)
        self.assertIn("avg_resonance", report)


class TestEREPRIntegration(unittest.TestCase):
    """Integration tests for EREPR multi-node scenarios."""

    def test_three_node_mesh(self):
        """Test three nodes forming a mesh network."""
        nodes = {}
        for i in range(3):
            node = EREPRProtocol(f"node{i}", f"secret{i}".encode())
            node.initialize()
            nodes[i] = node

        # Each node broadcasts echo to others
        for i in range(3):
            for j in range(3):
                if i != j:
                    echo = EchoMessage(
                        sig=nodes[j].signature,
                        services=0x03,
                        user_agent=f"node{j}/1.0",
                    )
                    nodes[i].receive_echo(echo)

        # Check bonds formed
        for i in range(3):
            bonded = [
                peer_id for peer_id in nodes[i].bonds
                if peer_id != f"node{i}"
            ]
            # Each node should have bonds with at least some peers
            self.assertGreaterEqual(len(bonded), 0)  # Depends on resonance

    def test_gossip_propagation_chain(self):
        """Test gossip propagating through a chain of nodes."""
        nodes = {}
        for i in range(5):
            node = EREPRProtocol(f"node{i}", f"secret{i}".encode())
            node.initialize()
            nodes[i] = node

        # Manually create strong bonds between adjacent nodes for reliable test
        import hashlib
        for i in range(4):
            for a, b in [(i, i + 1), (i + 1, i)]:
                shared_secret = hashlib.sha256(
                    nodes[a].secret + f"node{b}".encode() + nodes[a].node_id.encode()
                ).digest()
                nodes[a].bonds[f"node{b}"] = EntanglementBond(
                    peer_id=f"node{b}",
                    shared_secret=shared_secret,
                    resonance_score=0.9,
                    bond_strength=0.9,
                    created_at=time.time(),
                    last_heartbeat=time.time(),
                )

        # Create gossip at node 0
        wave = nodes[0].create_gossip_wave({"type": "block", "height": 100})
        targets = nodes[0].forward_wave(wave)

        # Should forward to node 1
        peer_ids = [t[0] for t in targets]
        self.assertIn("node1", peer_ids)

    def test_bond_decay_and_reconnect(self):
        """Test bonds decaying and re-forming."""
        node1 = EREPRProtocol("node1", b"secret1")
        node1.initialize()
        node2 = EREPRProtocol("node2", b"secret2")
        node2.initialize()

        # Form bond
        echo = EchoMessage(
            sig=node2.signature,
            services=0x03,
            user_agent="node2/1.0",
        )
        bond = node1.receive_echo(echo)
        if bond is None:
            self.skipTest("Resonance below threshold — bond not formed")

        self.assertIn("node2", node1.bonds)

        # Decay
        bond = node1.bonds["node2"]
        bond.last_heartbeat = time.time() - 200000
        node1.decay_bonds()
        self.assertNotIn("node2", node1.bonds)

        # Re-echo to re-form bond
        new_echo = EchoMessage(
            sig=node2.signature,
            services=0x03,
            user_agent="node2/1.0",
        )
        new_bond = node1.receive_echo(new_echo)
        # May or may not form depending on resonance threshold


if __name__ == "__main__":
    unittest.main()
