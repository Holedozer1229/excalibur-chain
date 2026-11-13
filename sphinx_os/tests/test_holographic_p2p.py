"""Tests for Holographic P2P Layer."""

import sys
import os
import unittest
import json
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sphinx_os.nexus import HolographicP2PLayer, MessagePriority


class TestHolographicP2PLayer(unittest.TestCase):
    """Test suite for HolographicP2PLayer."""

    def setUp(self):
        self.p2p = HolographicP2PLayer()
        # Add 5 peers
        for i in range(5):
            self.p2p.add_peer(f"peer_{i}", f"192.168.1.{i+1}", 8080 + i)
            self.p2p.connect_peer(f"peer_{i}")

    def test_peer_addition(self):
        """Test peers are added correctly."""
        self.assertEqual(len(self.p2p.peers), 5)
        self.assertIn("peer_0", self.p2p.peers)

    def test_peer_connection(self):
        """Test peer connection status."""
        peer = self.p2p.peers["peer_0"]
        self.assertTrue(peer.connected)

    def test_active_peers(self):
        """Test active peer count."""
        active = self.p2p.get_active_peers()
        self.assertEqual(len(active), 5)

    def test_send_message(self):
        """Test sending a message."""
        msg_id = self.p2p.send_message("peer_0", "test", {"data": "hello"})
        self.assertIsNotNone(msg_id)
        self.assertGreater(len(msg_id), 0)

    def test_message_priority(self):
        """Test message priority levels."""
        self.assertEqual(MessagePriority.CRITICAL, 0)
        self.assertEqual(MessagePriority.HIGH, 1)
        self.assertEqual(MessagePriority.NORMAL, 2)
        self.assertEqual(MessagePriority.LOW, 3)

    def test_encryption(self):
        """Test message encryption/decryption."""
        msg_id = self.p2p.send_message("peer_0", "encrypted", {"secret": "data"}, encrypt=True)
        self.assertIsNotNone(msg_id)

    def test_gossip_protocol(self):
        """Test gossip protocol propagation."""
        msg_id = self.p2p.send_message("peer_0", "gossip", {"data": "spread"}, gossip=True)
        self.assertIsNotNone(msg_id)

    def test_network_coherence(self):
        """Test network coherence calculation."""
        self.p2p.update_network_coherence()
        self.assertGreaterEqual(self.p2p.network_coherence, 0.0)
        self.assertLessEqual(self.p2p.network_coherence, 1.0)

    def test_get_network_state(self):
        """Test network state retrieval."""
        state = self.p2p.get_network_state()
        self.assertIn("active_peers", state)
        self.assertIn("network_coherence", state)
        self.assertIn("messages_sent", state)
        self.assertEqual(state["active_peers"], 5)

    def test_topology_export_json(self):
        """Test topology export in JSON format."""
        topology_json = self.p2p.export_topology("json")
        data = json.loads(topology_json)
        self.assertIn("nodes", data)
        self.assertIn("edges", data)

    def test_topology_export_graphml(self):
        """Test topology export in GraphML format."""
        topology_graphml = self.p2p.export_topology("graphml")
        self.assertIn("graphml", topology_graphml.lower())

    def test_disconnect_peer(self):
        """Test peer disconnection."""
        self.p2p.disconnect_peer("peer_0")
        peer = self.p2p.peers["peer_0"]
        self.assertFalse(peer.connected)

    def test_path_finding(self):
        """Test path finding between peers using internal method."""
        path = self.p2p._find_entanglement_path("peer_0", "peer_4")
        self.assertIsNotNone(path)
        self.assertIn("peer_0", path)
        self.assertIn("peer_4", path)

    def test_bandwidth_tracking(self):
        """Test bandwidth tracking."""
        self.p2p.send_message("peer_0", "test", {"data": "x" * 100})
        peer = self.p2p.peers["peer_0"]
        self.assertGreater(peer.bandwidth_bytes, 0)


if __name__ == "__main__":
    unittest.main()
