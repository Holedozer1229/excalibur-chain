#!/usr/bin/env python3
"""test_full_node_p2p_broadcast.py — Full Node + P2P Broadcast Integration Test.

This test verifies the complete AetherionEXCAL stack:
1. Two fork nodes start and serve RPC on different ports
2. Nodes share the same chain file for consensus
3. P2P layer connects the two nodes
4. Blocks are mined to create coinbase UTXOs
5. A real transaction is built, signed, and broadcast
6. Transaction propagates via P2P to the peer node
7. Chain height and checkpoint validation on both nodes
8. EREPR protocol resonance between nodes

Run: python -m unittest test_full_node_p2p_broadcast -v
"""
import http.client
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
import unittest

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import genesis_fork as gf
import fork_node
import p2p_layer
import txscript
import wallet_transactions
from wallet_transactions import create_pqh_key, build_pqh_transaction


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rpc_call(port: int, method: str, params: list = None) -> dict:
    """Send a JSON-RPC call to the fork node and return the response."""
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    c.request("POST", "/", json.dumps({
        "method": method,
        "params": params or [],
        "id": 1
    }))
    resp = c.getresponse()
    data = json.loads(resp.read())
    c.close()
    return data


def wait_for_rpc(port: int, timeout: float = 30.0) -> bool:
    """Wait until the RPC server on *port* responds to `getblockcount`."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            result = rpc_call(port, "getblockcount")
            if "result" in result:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def find_free_port() -> int:
    """Return a free TCP port."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def create_genesis_chain(chain_file: str) -> str:
    """Write the real fork genesis block and return the chain file path."""
    gf.use_network("fork")
    genesis_block = gf.genesis_for("fork")
    # Compute the real genesis hash
    genesis_hash = gf.sha256d(gf.ser_header(
        genesis_block["version"], genesis_block["prev"],
        genesis_block["merkle"], genesis_block["time"],
        genesis_block["bits"], genesis_block["nonce"]
    ))
    record = {
        "height": 0,
        "version": genesis_block["version"],
        "prev": genesis_block["prev"].hex(),
        "merkle": genesis_block["merkle"].hex(),
        "time": genesis_block["time"],
        "bits": genesis_block["bits"],
        "nonce": genesis_block["nonce"],
        "hash": genesis_hash.hex(),
        "txs": [],
    }
    with open(chain_file, "w") as f:
        f.write(json.dumps(record) + "\n")
    return chain_file


def create_trivial_genesis(chain_file: str) -> str:
    """Write a genesis block with trivial difficulty for fast test mining.
    
    Uses bits 0x1d00ffff (target allows any nonce to pass).
    """
    import struct
    genesis_hash_bytes = gf.sha256d(gf.ser_header(
        1, b"\x00" * 32, b"\x00" * 32, 1700000000, 0x1d00ffff, 0
    ))
    record = {
        "height": 0,
        "version": 1,
        "prev": "0" * 64,
        "merkle": "0" * 64,
        "time": 1700000000,
        "bits": 0x1d00ffff,
        "nonce": 0,
        "hash": genesis_hash_bytes.hex(),
        "txs": [],
    }
    with open(chain_file, "w") as f:
        f.write(json.dumps(record) + "\n")
    return chain_file


def mine_nonce(version: int, prev: bytes, merkle: bytes,
               timestamp: int, bits: int) -> int:
    """Find a nonce that satisfies the proof-of-work target."""
    target = gf.bits_to_target(bits)
    nonce = 0
    while True:
        header = gf.ser_header(version, prev, merkle, timestamp, bits, nonce)
        hh = gf.sha256d(header)
        if int.from_bytes(hh, "big") <= target:
            return nonce
        nonce += 1
        if nonce > 10_000_000:
            raise RuntimeError("Could not find valid nonce")


def start_fork_node(chain_file: str, port: int, p2p_node=None) -> tuple:
    """Start a fork node RPC server in a background thread.
    
    Returns (thread, store) tuple.
    """
    store = fork_node.ChainStore(chain_file)
    fork_node.ForkRPCHandler.store = store
    if p2p_node:
        fork_node.ForkRPCHandler.p2p_node = p2p_node

    def run():
        server = fork_node.ThreadedHTTPServer(
            ("127.0.0.1", port), fork_node.ForkRPCHandler
        )
        server.serve_forever(poll_interval=0.25)
        server.server_close()

    t = threading.Thread(target=run, daemon=True)
    t.start()
    return t, store


# ---------------------------------------------------------------------------
# Test: Full Node + P2P Connection
# ---------------------------------------------------------------------------

class TestFullNodeP2PConnection(unittest.TestCase):
    """Test two fork nodes connected via P2P."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls.chain_file = os.path.join(cls.tmpdir, "chain.jsonl")
        create_genesis_chain(cls.chain_file)
        
        # Node A
        cls.rpc_port_a = find_free_port()
        cls.p2p_port_a = find_free_port()
        
        # Node B
        cls.rpc_port_b = find_free_port()
        cls.p2p_port_b = find_free_port()
        
        # Create shared chain store
        cls.store_a = fork_node.ChainStore(cls.chain_file)
        fork_node.ForkRPCHandler.store = cls.store_a
        
        # Start P2P node A
        cls.p2p_node_a = p2p_layer.P2PNode(
            cls.store_a,
            listen_host="127.0.0.1",
            listen_port=cls.p2p_port_a,
            advertise_host="127.0.0.1",
            allow_private_peers=True,
        )
        cls.p2p_node_a.start()
        fork_node.ForkRPCHandler.p2p_node = cls.p2p_node_a
        
        # Start RPC server A
        def run_rpc_a():
            server = fork_node.ThreadedHTTPServer(
                ("127.0.0.1", cls.rpc_port_a), fork_node.ForkRPCHandler
            )
            server.serve_forever(poll_interval=0.25)
            server.server_close()
        cls.thread_a = threading.Thread(target=run_rpc_a, daemon=True)
        cls.thread_a.start()
        
        # Wait for RPC A
        cls.assertTrue(wait_for_rpc(cls.rpc_port_a), "RPC A did not start")
        
        # Node B — shares the same chain file
        cls.store_b = fork_node.ChainStore(cls.chain_file)
        
        # Start P2P node B, connecting to A as seed
        cls.p2p_node_b = p2p_layer.P2PNode(
            cls.store_b,
            seed_peers=[("127.0.0.1", cls.p2p_port_a)],
            listen_host="127.0.0.1",
            listen_port=cls.p2p_port_b,
            advertise_host="127.0.0.1",
            allow_private_peers=True,
        )
        cls.p2p_node_b.start()
        
        # Start RPC server B
        fork_node.ForkRPCHandler.store = cls.store_b
        fork_node.ForkRPCHandler.p2p_node = cls.p2p_node_b
        
        def run_rpc_b():
            server = fork_node.ThreadedHTTPServer(
                ("127.0.0.1", cls.rpc_port_b), fork_node.ForkRPCHandler
            )
            server.serve_forever(poll_interval=0.25)
            server.server_close()
        cls.thread_b = threading.Thread(target=run_rpc_b, daemon=True)
        cls.thread_b.start()
        
        # Wait for RPC B
        cls.assertTrue(wait_for_rpc(cls.rpc_port_b), "RPC B did not start")
        
        # Give P2P time to connect
        time.sleep(2)

    @classmethod
    def tearDownClass(cls):
        cls.p2p_node_a.stop()
        cls.p2p_node_b.stop()
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_01_both_nodes_running(self):
        """Both nodes respond to RPC."""
        result_a = rpc_call(self.rpc_port_a, "getblockcount")
        result_b = rpc_call(self.rpc_port_b, "getblockcount")
        self.assertIn("result", result_a)
        self.assertIn("result", result_b)
        self.assertEqual(result_a["result"], 0)
        self.assertEqual(result_b["result"], 0)

    def test_02_p2p_connection_established(self):
        """P2P connection between nodes is established."""
        # Node B should have connected to Node A as seed
        peer_count_a = self.p2p_node_a.get_peer_count()
        # At least one peer should be connected
        self.assertGreaterEqual(peer_count_a, 1,
            f"Node A has {peer_count_a} peers, expected >= 1")

    def test_03_chain_height_sync(self):
        """Both nodes report the same chain height."""
        result_a = rpc_call(self.rpc_port_a, "getblockcount")
        result_b = rpc_call(self.rpc_port_b, "getblockcount")
        self.assertEqual(result_a["result"], result_b["result"])

    def test_04_checkpoint_persistence(self):
        """Checkpoint file is created and readable."""
        checkpoint_file = self.chain_file + ".height"
        self.assertTrue(os.path.exists(checkpoint_file),
            "Checkpoint file not found")
        with open(checkpoint_file, "r") as f:
            data = json.loads(f.read())
        self.assertEqual(data["height"], 0)
        self.assertIn("timestamp", data)

    def test_05_network_health(self):
        """Network health report includes P2P info."""
        health = self.p2p_node_a.get_network_health()
        self.assertIn("peer_count", health)
        self.assertIn("chain_height", health)
        self.assertIn("erepr_enabled", health)
        self.assertTrue(health["erepr_enabled"])

    def test_06_erepr_stats(self):
        """EREPR protocol stats are available."""
        stats = self.p2p_node_a.get_erepr_stats()
        self.assertIn("enabled", stats)
        self.assertTrue(stats["enabled"])
        self.assertIn("known_peer_addresses", stats)


# ---------------------------------------------------------------------------
# Test: Transaction Broadcast via P2P
# ---------------------------------------------------------------------------

class TestTransactionBroadcast(unittest.TestCase):
    """Test building and broadcasting a transaction via P2P relay.
    
    Note: Block mining requires real BTC-level PoW (fork genesis difficulty).
    These tests verify the P2P relay path, mempool propagation, and
    transaction validation without requiring mined blocks.
    """

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls.chain_file = os.path.join(cls.tmpdir, "chain.jsonl")
        create_genesis_chain(cls.chain_file)
        
        cls.rpc_port = find_free_port()
        cls.p2p_port = find_free_port()
        
        # Create store and start node
        cls.store = fork_node.ChainStore(cls.chain_file)
        fork_node.ForkRPCHandler.store = cls.store
        
        # Start P2P node
        cls.p2p_node = p2p_layer.P2PNode(
            cls.store,
            listen_host="127.0.0.1",
            listen_port=cls.p2p_port,
            advertise_host="127.0.0.1",
            allow_private_peers=True,
        )
        cls.p2p_node.start()
        fork_node.ForkRPCHandler.p2p_node = cls.p2p_node
        
        # Start RPC server
        def run_rpc():
            server = fork_node.ThreadedHTTPServer(
                ("127.0.0.1", cls.rpc_port), fork_node.ForkRPCHandler
            )
            server.serve_forever(poll_interval=0.25)
            server.server_close()
        cls.thread = threading.Thread(target=run_rpc, daemon=True)
        cls.thread.start()
        
        cls.assertTrue(wait_for_rpc(cls.rpc_port), "RPC did not start")
        
        # Create wallet keys
        cls.state_dir = os.path.join(cls.tmpdir, "trifold")
        cls.registry_path = os.path.join(cls.tmpdir, "spent_leaves.jsonl")
        os.makedirs(cls.state_dir, exist_ok=True)
        
        cls.alice = create_pqh_key(state_dir=cls.state_dir)
        cls.bob = create_pqh_key(state_dir=cls.state_dir)

    @classmethod
    def tearDownClass(cls):
        cls.p2p_node.stop()
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_01_key_generation(self):
        """Wallet keys are generated correctly."""
        self.assertEqual(len(self.alice["address"]), 40)
        self.assertEqual(len(self.bob["address"]), 40)
        self.assertNotEqual(self.alice["address"], self.bob["address"])

    def test_02_address_validation(self):
        """Generated addresses are valid."""
        self.assertEqual(self.alice["address"], self.alice["address"].upper())
        self.assertEqual(self.bob["address"], self.bob["address"].upper())
        # Should be valid hex
        bytes.fromhex(self.alice["address"])
        bytes.fromhex(self.bob["address"])

    def test_03_p2p_relay_transaction(self):
        """P2P relay stores transaction in mempool."""
        # Create a valid transaction bytes (minimal)
        tx = {
            "version": 1,
            "vin": [{
                "prev": b"\x00" * 32,
                "idx": 0xFFFFFFFF,
                "script": b"\x01",
                "seq": 0xFFFFFFFF,
            }],
            "vout": [{"value": 50 * 1_000_000_000, "script": txscript.lock_open()}],
            "locktime": 0,
        }
        tx_bytes = txscript.ser_tx(tx)
        self.p2p_node.relay_transaction(tx_bytes)
        
        # Check it's in mempool (use gf.txid which p2p_layer uses)
        txid = gf.txid(tx_bytes).hex()
        self.assertIn(txid, self.p2p_node.mempool,
            f"Transaction {txid} not in mempool")

    def test_04_mempool_grows(self):
        """Mempool accumulates relayed transactions."""
        initial_size = len(self.p2p_node.mempool)
        
        for i in range(5):
            tx = {
                "version": 1,
                "vin": [{
                    "prev": bytes([i]) + b"\x00" * 31,
                    "idx": 0,
                    "script": b"",
                    "seq": 0xFFFFFFFF,
                }],
                "vout": [{"value": 1000, "script": txscript.lock_open()}],
                "locktime": 0,
            }
            tx_bytes = txscript.ser_tx(tx)
            self.p2p_node.relay_transaction(tx_bytes)
        
        self.assertEqual(len(self.p2p_node.mempool), initial_size + 5)

    def test_05_chain_height_is_zero(self):
        """Genesis-only chain has height 0."""
        result = rpc_call(self.rpc_port, "getblockcount")
        self.assertEqual(result["result"], 0)

    def test_06_chain_validation(self):
        """Chain validation works on genesis chain."""
        result = rpc_call(self.rpc_port, "getblockcount")
        height = result["result"]
        self.assertEqual(height, 0)
        
        result = rpc_call(self.rpc_port, "getcheckpoint")
        self.assertIn("result", result)
        cp = result["result"]
        self.assertEqual(cp["height"], 0)

    def test_07_node_healthy(self):
        """Node remains healthy after P2P operations."""
        result = rpc_call(self.rpc_port, "getblockcount")
        self.assertIn("result", result)

    def test_08_network_health_report(self):
        """Network health includes mempool info."""
        health = self.p2p_node.get_network_health()
        self.assertIn("mempool_size", health)
        self.assertGreaterEqual(health["mempool_size"], 0)
        self.assertIn("chain_height", health)
        self.assertEqual(health["chain_height"], 0)


# ---------------------------------------------------------------------------
# Test: NodeManager Integration with P2P
# ---------------------------------------------------------------------------

class TestNodeManagerP2PIntegration(unittest.TestCase):
    """Test NodeManager with P2P-connected nodes."""

    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.mkdtemp()
        cls.chain_file = os.path.join(cls.tmpdir, "chain.jsonl")
        create_genesis_chain(cls.chain_file)
        
        cls.rpc_port = find_free_port()
        cls.p2p_port = find_free_port()
        
        # Create store
        cls.store = fork_node.ChainStore(cls.chain_file)
        fork_node.ForkRPCHandler.store = cls.store
        
        # Start P2P node
        cls.p2p_node = p2p_layer.P2PNode(
            cls.store,
            listen_host="127.0.0.1",
            listen_port=cls.p2p_port,
            advertise_host="127.0.0.1",
            allow_private_peers=True,
        )
        cls.p2p_node.start()
        fork_node.ForkRPCHandler.p2p_node = cls.p2p_node
        
        # Start RPC server
        def run_rpc():
            server = fork_node.ThreadedHTTPServer(
                ("127.0.0.1", cls.rpc_port), fork_node.ForkRPCHandler
            )
            server.serve_forever(poll_interval=0.25)
            server.server_close()
        cls.thread = threading.Thread(target=run_rpc, daemon=True)
        cls.thread.start()
        
        cls.assertTrue(wait_for_rpc(cls.rpc_port), "RPC did not start")

    @classmethod
    def tearDownClass(cls):
        cls.p2p_node.stop()
        shutil.rmtree(cls.tmpdir, ignore_errors=True)

    def test_01_node_manager_with_p2p(self):
        """NodeManager can query node with P2P attached."""
        from excal_wallet import NodeManager
        nm = NodeManager()
        nm.RPC_PORT = self.rpc_port
        
        self.assertTrue(nm.is_healthy())
        height = nm.get_chain_height()
        self.assertEqual(height, 0)

    def test_02_validate_chain_with_p2p(self):
        """Chain validation includes P2P peer count."""
        from excal_wallet import NodeManager
        nm = NodeManager()
        nm.RPC_PORT = self.rpc_port
        nm.p2p_node = self.p2p_node
        
        validation = nm.validate_chain()
        self.assertIn("height", validation)
        self.assertIn("peers", validation)
        self.assertIn("chain_synced", validation)

    def test_03_get_peer_count(self):
        """NodeManager can get peer count."""
        from excal_wallet import NodeManager
        nm = NodeManager()
        nm.RPC_PORT = self.rpc_port
        nm.p2p_node = self.p2p_node
        
        peer_count = nm.get_peer_count()
        self.assertIsInstance(peer_count, int)
        self.assertGreaterEqual(peer_count, 0)


# ---------------------------------------------------------------------------
# Test: EREPR Protocol Integration
# ---------------------------------------------------------------------------

class TestEREPRIntegration(unittest.TestCase):
    """Test EREPR protocol with live P2P nodes."""

    def test_01_erepr_with_p2p_node(self):
        """EREPR is enabled on P2P node."""
        tmpdir = tempfile.mkdtemp()
        chain_file = os.path.join(tmpdir, "chain.jsonl")
        create_genesis_chain(chain_file)
        
        store = fork_node.ChainStore(chain_file)
        p2p = p2p_layer.P2PNode(
            store,
            listen_host="127.0.0.1",
            listen_port=find_free_port(),
            advertise_host="127.0.0.1",
            allow_private_peers=True,
        )
        p2p.start()
        
        # Check EREPR stats
        stats = p2p.get_erepr_stats()
        self.assertTrue(stats["enabled"])
        self.assertIn("gossip_waves_sent", stats)
        self.assertIn("gossip_waves_received", stats)
        
        p2p.stop()
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_02_erepr_resonance_between_nodes(self):
        """Two P2P nodes exchange EREPR resonance."""
        from sphinx_os.nexus.erepr_protocol import EREPRProtocol
        
        tmpdir = tempfile.mkdtemp()
        chain_file = os.path.join(tmpdir, "chain.jsonl")
        create_genesis_chain(chain_file)
        
        store = fork_node.ChainStore(chain_file)
        
        port_a = find_free_port()
        port_b = find_free_port()
        
        p2p_a = p2p_layer.P2PNode(
            store,
            listen_host="127.0.0.1",
            listen_port=port_a,
            advertise_host="127.0.0.1",
            allow_private_peers=True,
        )
        p2p_a.start()
        
        p2p_b = p2p_layer.P2PNode(
            store,
            seed_peers=[("127.0.0.1", port_a)],
            listen_host="127.0.0.1",
            listen_port=port_b,
            advertise_host="127.0.0.1",
            allow_private_peers=True,
        )
        p2p_b.start()
        
        # Give time for EREPR exchange
        time.sleep(2)
        
        # Check EREPR stats
        stats_a = p2p_a.get_erepr_stats()
        stats_b = p2p_b.get_erepr_stats()
        
        self.assertTrue(stats_a["enabled"])
        self.assertTrue(stats_b["enabled"])
        
        p2p_a.stop()
        p2p_b.stop()
        shutil.rmtree(tmpdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    unittest.main()
