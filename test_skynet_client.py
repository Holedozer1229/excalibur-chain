#!/usr/bin/env python3
"""Tests for SkyNet wallet client + beacon mesh."""

import json
import os
import tempfile
import threading
import time
import unittest
from http.server import HTTPServer

from skynet_beacon import PeerDatabase, BeaconHTTPHandler
from skynet_client import SkyNetClient


class TestSkyNetClient(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = PeerDatabase(db_path=os.path.join(self.tmp.name, "beacon.db"))

        class _FakeBeacon:
            start_time = time.time()

        BeaconHTTPHandler.peer_db = self.db
        BeaconHTTPHandler.beacon = _FakeBeacon()
        self.httpd = HTTPServer(("127.0.0.1", 0), BeaconHTTPHandler)
        self.port = self.httpd.server_address[1]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

        self.client = SkyNetClient(
            beacon_host="127.0.0.1",
            beacon_port=self.port,
            p2p_port=19433,
            wallet_address="TESTWALLETADDR12345",
            central_servers=[],
            advertise_host="127.0.0.1",
        )

    def tearDown(self):
        self.client.stop()
        self.httpd.shutdown()
        self.db.close()
        self.tmp.cleanup()

    def test_register_and_discover(self):
        self.assertTrue(self.client.register())
        peers = self.client.fetch_peers()
        self.assertTrue(any(p["port"] == 19433 for p in peers))
        status = self.client.status()
        self.assertTrue(status["beacon_healthy"])

    def test_heartbeat_returns_peers(self):
        self.client.register()
        peers = self.client.heartbeat()
        self.assertIsInstance(peers, list)

    def test_broadcast_and_fetch_swap_offer(self):
        offer = {
            "swap_id": "swap-test-1",
            "direction": "excal_to_btc",
            "secret_hash": "ab" * 32,
            "excal_amount": 100_000_000,
            "btc_amount": 10_000_000,
        }
        self.assertTrue(self.client.broadcast_swap_offer(offer))
        # New client instance to clear seen set
        other = SkyNetClient(
            beacon_host="127.0.0.1",
            beacon_port=self.port,
            p2p_port=19434,
            central_servers=[],
            advertise_host="127.0.0.1",
        )
        found = other.fetch_swap_offers()
        self.assertTrue(any(o.get("swap_id") == "swap-test-1" for o in found))

    def test_seed_peers_excludes_self(self):
        self.db.add_peer("10.0.0.9", 9433, wallet="PEER1")
        self.client.register()
        self.client.fetch_peers()
        seeds = self.client.seed_peers()
        self.assertTrue(any(s[0] == "10.0.0.9" for s in seeds))
        self.assertFalse(any(s[0] == "127.0.0.1" and s[1] == 19433 for s in seeds))


if __name__ == "__main__":
    unittest.main()
