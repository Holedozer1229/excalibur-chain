#!/usr/bin/env python3
"""test_skynet_beacon.py — Tests for the SkyNet Node Beacon service.

Tests cover:
1. Beacon initialization and node ID persistence
2. Peer registration and discovery
3. HTTP endpoints (health, peers, stats, register, unregister)
4. UDP multicast and broadcast handling
5. Heartbeat and prune functionality
6. Central server registration
7. Integration scenarios
"""
import json
import os
import socket
import struct
import sys
import tempfile
import threading
import time
import unittest
from http.server import HTTPServer
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from skynet_beacon import (
    SkyNetBeacon,
    BeaconHandler,
    DEFAULT_PORT,
    DEFAULT_MULTICAST_PORT,
    DEFAULT_MULTICAST_GROUP,
    DEFAULT_BROADCAST_PORT,
    PEER_TTL,
    HEARTBEAT_INTERVAL,
)


class TestSkyNetBeaconInit(unittest.TestCase):
    """Test beacon initialization."""
    
    def test_beacon_creates_node_id(self):
        """Beacon creates a unique node ID."""
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["_TEST_WALLET_DIR"] = tmp
            beacon = SkyNetBeacon(port=9435)
            self.assertTrue(beacon._node_id)
            self.assertEqual(len(beacon._node_id), 36)  # UUID format
    
    def test_beacon_persists_node_id(self):
        """Node ID is persisted and reused."""
        with tempfile.TemporaryDirectory() as tmp:
            state_file = Path(tmp) / "beacon_state.json"
            # First creation
            with patch("skynet_beacon.BEACON_STATE_PATH", state_file):
                with patch("skynet_beacon.BEACON_DB_PATH", Path(tmp) / "test.db"):
                    beacon1 = SkyNetBeacon(port=9435)
                    node_id = beacon1._node_id
            # Second creation should reuse
            with patch("skynet_beacon.BEACON_STATE_PATH", state_file):
                with patch("skynet_beacon.BEACON_DB_PATH", Path(tmp) / "test.db"):
                    beacon2 = SkyNetBeacon(port=9435)
                    self.assertEqual(beacon2._node_id, node_id)
    
    def test_beacon_gets_local_ip(self):
        """Beacon detects local IP address."""
        beacon = SkyNetBeacon(port=9435)
        ip = beacon._host
        self.assertTrue(ip.startswith("127.") or ip.startswith("192.") or ip.startswith("10."))
    
    def test_beacon_default_ports(self):
        """Default ports are set correctly."""
        beacon = SkyNetBeacon()
        self.assertEqual(beacon.port, DEFAULT_PORT)
        self.assertEqual(beacon.p2p_port, 9433)


class TestPeerRegistration(unittest.TestCase):
    """Test peer registration and discovery."""
    
    def setUp(self):
        self.beacon = SkyNetBeacon(port=9435)
    
    def test_register_peer(self):
        """Register a peer."""
        self.beacon._register_peer("test-node", "192.168.1.100", 9433)
        self.assertIn("test-node", self.beacon._peers)
        peer = self.beacon._peers["test-node"]
        self.assertEqual(peer["host"], "192.168.1.100")
        self.assertEqual(peer["port"], 9433)
    
    def test_register_peer_auto_id(self):
        """Auto-generate node ID from host:port."""
        self.beacon._register_peer("", "192.168.1.100", 9433)
        # Should have created a hash-based ID
        ids = [k for k in self.beacon._peers.keys() if k != self.beacon._node_id]
        self.assertTrue(len(ids) > 0)
    
    def test_get_peers(self):
        """Get peers returns registered peers."""
        self.beacon._register_peer("node1", "192.168.1.100", 9433)
        self.beacon._register_peer("node2", "192.168.1.101", 9433)
        peers = self.beacon.get_peers(limit=8)
        self.assertGreaterEqual(len(peers), 2)
    
    def test_get_peers_limit(self):
        """Peer limit is respected."""
        for i in range(10):
            self.beacon._register_peer(f"node{i}", f"192.168.1.{i}", 9433)
        peers = self.beacon.get_peers(limit=3)
        self.assertLessEqual(len(peers), 3)
    
    def test_register_self(self):
        """Beacon registers itself."""
        self.beacon._register_self()
        self.assertIn(self.beacon._node_id, self.beacon._peers)


class TestBeaconStats(unittest.TestCase):
    """Test beacon statistics."""
    
    def setUp(self):
        self.beacon = SkyNetBeacon(port=9435)
    
    def test_stats_returns_dict(self):
        """Stats returns a dictionary."""
        stats = self.beacon.get_stats()
        self.assertIsInstance(stats, dict)
    
    def test_stats_has_required_fields(self):
        """Stats contains all required fields."""
        stats = self.beacon.get_stats()
        self.assertIn("node_id", stats)
        self.assertIn("host", stats)
        self.assertIn("p2p_port", stats)
        self.assertIn("beacon_port", stats)
        self.assertIn("peers_registered", stats)
        self.assertIn("peers_active", stats)
        self.assertIn("running", stats)
    
    def test_stats_peer_count(self):
        """Stats reflects peer count."""
        self.beacon._register_peer("node1", "192.168.1.100", 9433)
        stats = self.beacon.get_stats()
        self.assertGreaterEqual(stats["peers_registered"], 1)


class TestUDPHandling(unittest.TestCase):
    """Test UDP message handling."""
    
    def setUp(self):
        self.beacon = SkyNetBeacon(port=9435)
    
    def test_handle_register_message(self):
        """Handle register UDP message."""
        msg = json.dumps({
            "type": "register",
            "node_id": "test-node",
            "host": "192.168.1.100",
            "port": 9433,
        }).encode("utf-8")
        
        mock_sock = MagicMock()
        self.beacon._handle_udp_message(msg, ("192.168.1.100", 12345), mock_sock)
        
        self.assertIn("test-node", self.beacon._peers)
        # Should have sent response
        mock_sock.sendto.assert_called_once()
    
    def test_handle_heartbeat_message(self):
        """Handle heartbeat UDP message."""
        self.beacon._register_peer("node1", "192.168.1.100", 9433)
        old_seen = self.beacon._peers["node1"]["last_seen"]
        time.sleep(0.01)
        
        msg = json.dumps({
            "type": "heartbeat",
            "node_id": "node1",
        }).encode("utf-8")
        
        mock_sock = MagicMock()
        self.beacon._handle_udp_message(msg, ("192.168.1.100", 12345), mock_sock)
        
        new_seen = self.beacon._peers["node1"]["last_seen"]
        self.assertGreater(new_seen, old_seen)
    
    def test_handle_unregister_message(self):
        """Handle unregister UDP message."""
        self.beacon._register_peer("node1", "192.168.1.100", 9433)
        
        msg = json.dumps({
            "type": "unregister",
            "node_id": "node1",
        }).encode("utf-8")
        
        mock_sock = MagicMock()
        self.beacon._handle_udp_message(msg, ("192.168.1.100", 12345), mock_sock)
        
        self.assertNotIn("node1", self.beacon._peers)
    
    def test_handle_invalid_message(self):
        """Invalid messages are ignored."""
        mock_sock = MagicMock()
        self.beacon._handle_udp_message(b"invalid json", ("192.168.1.100", 12345), mock_sock)
        # Should not crash


class TestPruneStale(unittest.TestCase):
    """Test stale peer pruning."""
    
    def setUp(self):
        self.beacon = SkyNetBeacon(port=9435)
    
    def test_prune_removes_stale(self):
        """Stale peers are removed."""
        self.beacon._register_peer("stale-node", "192.168.1.100", 9433)
        # Manually set last_seen to old
        self.beacon._peers["stale-node"]["last_seen"] = time.time() - PEER_TTL - 100
        self.beacon.prune_stale_peers()
        self.assertNotIn("stale-node", self.beacon._peers)
    
    def test_prune_keeps_active(self):
        """Active peers are kept."""
        self.beacon._register_peer("active-node", "192.168.1.100", 9433)
        self.beacon.prune_stale_peers()
        self.assertIn("active-node", self.beacon._peers)


class TestBroadcastHeartbeat(unittest.TestCase):
    """Test heartbeat broadcasting."""
    
    def setUp(self):
        self.beacon = SkyNetBeacon(port=9435)
    
    def test_broadcast_does_not_crash(self):
        """Broadcast heartbeat doesn't crash."""
        try:
            self.beacon._broadcast_heartbeat()
        except Exception as e:
            self.fail(f"Broadcast crashed: {e}")


class TestIntegration(unittest.TestCase):
    """Integration tests for the beacon."""
    
    def test_beacon_start_stop(self):
        """Beacon starts and stops cleanly."""
        beacon = SkyNetBeacon(port=9445)
        beacon.start()
        time.sleep(0.5)
        self.assertTrue(beacon._running)
        beacon.stop()
        self.assertFalse(beacon._running)
    
    def test_two_beacons_discover_each_other(self):
        """Two beacons can discover each other via UDP."""
        b1 = SkyNetBeacon(port=9446, p2p_port=9433)
        b2 = SkyNetBeacon(port=9447, p2p_port=9434)
        
        b1.start()
        b2.start()
        time.sleep(0.5)
        
        # Simulate b2 registering with b1
        msg = json.dumps({
            "type": "register",
            "node_id": b2._node_id,
            "host": "127.0.0.1",
            "port": 9434,
        }).encode("utf-8")
        
        mock_sock = MagicMock()
        b1._handle_udp_message(msg, ("127.0.0.1", 9447), mock_sock)
        
        self.assertIn(b2._node_id, b1._peers)
        
        b1.stop()
        b2.stop()


if __name__ == "__main__":
    unittest.main()
