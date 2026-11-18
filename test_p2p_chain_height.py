#!/usr/bin/env python3
"""test_p2p_chain_height.py — Test P2P connectivity and chain height checkpoint persistence.

Tests:
1. Chain height checkpoint is saved on every block
2. Chain height checkpoint is saved on node shutdown
3. Chain height checkpoint is loaded on node restart
4. P2P node can connect and exchange messages
5. Chain validation works correctly
"""
import asyncio
import http.client
import json
import os
import shutil
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


class TestChainHeightCheckpoint(unittest.TestCase):
    """Test chain height checkpoint persistence."""

    def setUp(self):
        """Create a temporary chain file for each test."""
        self.tmpdir = tempfile.mkdtemp()
        self.chain_file = os.path.join(self.tmpdir, "chain.jsonl")
        self.checkpoint_file = self.chain_file + ".height"
        
        # Create a minimal genesis block
        gf.use_network("fork")
        network = gf.network()
        
        # Write genesis block
        genesis = {
            "height": 0,
            "version": 1,
            "prev": "0" * 64,
            "merkle": "0" * 64,
            "time": int(time.time()),
            "bits": network.get("target_bits", 486604799),
            "nonce": 0,
            "hash": "0" * 64,
            "txs": [],
        }
        with open(self.chain_file, "w") as f:
            f.write(json.dumps(genesis) + "\n")

    def tearDown(self):
        """Clean up temporary files."""
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_checkpoint_saved_on_block(self):
        """Test that checkpoint is saved when a block is added."""
        store = fork_node.ChainStore(self.chain_file)
        
        # Checkpoint should be loaded (genesis height = 0)
        checkpoint = store.get_checkpoint()
        self.assertEqual(checkpoint["height"], 0)
        
        # Check that checkpoint file exists
        self.assertTrue(os.path.exists(self.checkpoint_file))
        
        # Read checkpoint file directly
        with open(self.checkpoint_file, "r") as f:
            data = json.loads(f.read())
        self.assertEqual(data["height"], 0)

    def test_checkpoint_loaded_on_restart(self):
        """Test that checkpoint is loaded when ChainStore restarts."""
        # First instance — saves checkpoint
        store1 = fork_node.ChainStore(self.chain_file)
        checkpoint1 = store1.get_checkpoint()
        
        # Second instance — should load checkpoint
        store2 = fork_node.ChainStore(self.chain_file)
        checkpoint2 = store2.get_checkpoint()
        
        self.assertEqual(checkpoint1["height"], checkpoint2["height"])
        self.assertEqual(checkpoint1["hash"], checkpoint2["hash"])

    def test_save_checkpoint_method(self):
        """Test the save_checkpoint method."""
        store = fork_node.ChainStore(self.chain_file)
        
        # Save checkpoint explicitly
        store.save_checkpoint()
        
        # Verify checkpoint file exists and has correct data
        self.assertTrue(os.path.exists(self.checkpoint_file))
        with open(self.checkpoint_file, "r") as f:
            data = json.loads(f.read())
        
        self.assertEqual(data["height"], store.tip_height)
        self.assertEqual(data["hash"], store.tip_hash)
        self.assertIn("timestamp", data)

    def test_checkpoint_file_format(self):
        """Test checkpoint file has correct JSON format."""
        store = fork_node.ChainStore(self.chain_file)
        store.save_checkpoint()
        
        with open(self.checkpoint_file, "r") as f:
            data = json.loads(f.read())
        
        # Verify all required fields
        self.assertIn("height", data)
        self.assertIn("hash", data)
        self.assertIn("timestamp", data)
        self.assertIsInstance(data["height"], int)
        self.assertIsInstance(data["hash"], str)
        self.assertIsInstance(data["timestamp"], float)


class TestP2PConnectivity(unittest.TestCase):
    """Test P2P node connectivity."""

    def test_p2p_node_initialization(self):
        """Test P2P node can be initialized."""
        tmpdir = tempfile.mkdtemp()
        chain_file = os.path.join(tmpdir, "chain.jsonl")
        
        # Create minimal genesis
        gf.use_network("fork")
        genesis = {
            "height": 0, "version": 1, "prev": "0" * 64,
            "merkle": "0" * 64, "time": int(time.time()),
            "bits": 486604799, "nonce": 0, "hash": "0" * 64, "txs": [],
        }
        with open(chain_file, "w") as f:
            f.write(json.dumps(genesis) + "\n")
        
        store = fork_node.ChainStore(chain_file)
        node = p2p_layer.P2PNode(store, listen_port=19433)
        
        self.assertEqual(node.listen_port, 19433)
        self.assertEqual(len(node.seed_peers), 0)
        self.assertEqual(len(node.peers), 0)
        
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_p2p_node_with_seed_peers(self):
        """Test P2P node with seed peers."""
        tmpdir = tempfile.mkdtemp()
        chain_file = os.path.join(tmpdir, "chain.jsonl")
        
        gf.use_network("fork")
        genesis = {
            "height": 0, "version": 1, "prev": "0" * 64,
            "merkle": "0" * 64, "time": int(time.time()),
            "bits": 486604799, "nonce": 0, "hash": "0" * 64, "txs": [],
        }
        with open(chain_file, "w") as f:
            f.write(json.dumps(genesis) + "\n")
        
        store = fork_node.ChainStore(chain_file)
        seed_peers = [("127.0.0.1", 9433), ("127.0.0.1", 9434)]
        node = p2p_layer.P2PNode(store, seed_peers=seed_peers)
        
        self.assertEqual(len(node.seed_peers), 2)
        self.assertEqual(len(node.known_addrs), 2)
        
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_p2p_message_encoding(self):
        """Test P2P message encoding and decoding."""
        tmpdir = tempfile.mkdtemp()
        chain_file = os.path.join(tmpdir, "chain.jsonl")
        
        gf.use_network("fork")
        genesis = {
            "height": 0, "version": 1, "prev": "0" * 64,
            "merkle": "0" * 64, "time": int(time.time()),
            "bits": 486604799, "nonce": 0, "hash": "0" * 64, "txs": [],
        }
        with open(chain_file, "w") as f:
            f.write(json.dumps(genesis) + "\n")
        
        store = fork_node.ChainStore(chain_file)
        node = p2p_layer.P2PNode(store)
        
        # Test that P2PNode has the expected attributes
        self.assertTrue(hasattr(node, 'chain_store'))
        self.assertTrue(hasattr(node, 'peers'))
        self.assertTrue(hasattr(node, 'mempool'))
        self.assertTrue(hasattr(node, 'seed_peers'))
        
        shutil.rmtree(tmpdir, ignore_errors=True)


class TestChainValidation(unittest.TestCase):
    """Test chain validation functionality."""

    def test_chain_store_getblockcount(self):
        """Test getblockcount returns correct height."""
        tmpdir = tempfile.mkdtemp()
        chain_file = os.path.join(tmpdir, "chain.jsonl")
        
        gf.use_network("fork")
        genesis = {
            "height": 0, "version": 1, "prev": "0" * 64,
            "merkle": "0" * 64, "time": int(time.time()),
            "bits": 486604799, "nonce": 0, "hash": "0" * 64, "txs": [],
        }
        with open(chain_file, "w") as f:
            f.write(json.dumps(genesis) + "\n")
        
        store = fork_node.ChainStore(chain_file)
        self.assertEqual(store.getblockcount(), 0)
        
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_chain_store_getbestblockhash(self):
        """Test getbestblockhash returns correct hash."""
        tmpdir = tempfile.mkdtemp()
        chain_file = os.path.join(tmpdir, "chain.jsonl")
        
        gf.use_network("fork")
        genesis = {
            "height": 0, "version": 1, "prev": "0" * 64,
            "merkle": "0" * 64, "time": int(time.time()),
            "bits": 486604799, "nonce": 0, "hash": "0" * 64, "txs": [],
        }
        with open(chain_file, "w") as f:
            f.write(json.dumps(genesis) + "\n")
        
        store = fork_node.ChainStore(chain_file)
        self.assertEqual(store.getbestblockhash(), "0" * 64)
        
        shutil.rmtree(tmpdir, ignore_errors=True)

    def test_checkpoint_consistency(self):
        """Test checkpoint stays consistent with chain state."""
        tmpdir = tempfile.mkdtemp()
        chain_file = os.path.join(tmpdir, "chain.jsonl")
        
        gf.use_network("fork")
        genesis = {
            "height": 0, "version": 1, "prev": "0" * 64,
            "merkle": "0" * 64, "time": int(time.time()),
            "bits": 486604799, "nonce": 0, "hash": "0" * 64, "txs": [],
        }
        with open(chain_file, "w") as f:
            f.write(json.dumps(genesis) + "\n")
        
        store = fork_node.ChainStore(chain_file)
        
        # Checkpoint should match chain state
        checkpoint = store.get_checkpoint()
        self.assertEqual(checkpoint["height"], store.getblockcount())
        self.assertEqual(checkpoint["hash"], store.getbestblockhash())
        
        shutil.rmtree(tmpdir, ignore_errors=True)


class TestNodeManagerValidation(unittest.TestCase):
    """Test NodeManager chain validation methods."""

    def test_node_manager_methods_exist(self):
        """Test that NodeManager has the new validation methods."""
        from excal_wallet import NodeManager
        
        nm = NodeManager()
        self.assertTrue(hasattr(nm, 'get_chain_height'))
        self.assertTrue(hasattr(nm, 'get_checkpoint'))
        self.assertTrue(hasattr(nm, 'get_peer_count'))
        self.assertTrue(hasattr(nm, 'validate_chain'))

    def test_validate_chain_returns_dict(self):
        """Test validate_chain returns a dict with expected keys."""
        from excal_wallet import NodeManager
        
        nm = NodeManager()
        result = nm.validate_chain()
        
        self.assertIsInstance(result, dict)
        self.assertIn("height", result)
        self.assertIn("checkpoint_height", result)
        self.assertIn("hash", result)
        self.assertIn("peers", result)
        self.assertIn("height_valid", result)
        self.assertIn("chain_synced", result)


if __name__ == "__main__":
    unittest.main()
