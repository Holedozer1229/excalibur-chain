#!/usr/bin/env python3
"""test_postgres_p2p.py — Tests for the persistent P2P database."""
import os
import shutil
import sqlite3
import tempfile
import time
import unittest

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from nexus.postgres_p2p import P2PDatabase, get_db


class TestP2PDatabase(unittest.TestCase):
    """Test the persistent P2P database."""
    
    def setUp(self):
        """Create a temporary database for each test."""
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test_p2p.db")
        self.db = P2PDatabase(self.db_path)
    
    def tearDown(self):
        """Clean up temporary database."""
        shutil.rmtree(self.tmpdir, ignore_errors=True)
    
    def test_tables_created(self):
        """Test that all tables are created on initialization."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        expected = [
            "blocks", "chain_checkpoint", "erepr_resonances",
            "known_addresses", "peers", "sqlite_sequence", "transactions",
        ]
        self.assertEqual(tables, expected)
    
    def test_add_peer(self):
        """Test adding a peer."""
        peer = self.db.add_peer(
            node_id="test-node-1",
            host="192.168.1.100",
            port=9433,
            services=0x01,
            user_agent="/AetherionEXCAL:1.0/",
            version=70016,
        )
        
        self.assertEqual(peer["node_id"], "test-node-1")
        self.assertEqual(peer["host"], "192.168.1.100")
        self.assertEqual(peer["port"], 9433)
        self.assertEqual(peer["services"], 0x01)
    
    def test_get_peer(self):
        """Test getting a peer by node_id."""
        self.db.add_peer("test-node-2", "192.168.1.101", 9433)
        peer = self.db.get_peer("test-node-2")
        
        self.assertIsNotNone(peer)
        self.assertEqual(peer["node_id"], "test-node-2")
    
    def test_get_peer_not_found(self):
        """Test getting a non-existent peer."""
        peer = self.db.get_peer("non-existent")
        self.assertIsNone(peer)
    
    def test_get_peers(self):
        """Test getting multiple peers."""
        self.db.add_peer("node-1", "192.168.1.1", 9433)
        self.db.add_peer("node-2", "192.168.1.2", 9433)
        self.db.add_peer("node-3", "192.168.1.3", 9433)
        
        peers = self.db.get_peers(limit=10)
        self.assertEqual(len(peers), 3)
    
    def test_update_peer_status(self):
        """Test updating peer connection status."""
        self.db.add_peer("node-1", "192.168.1.1", 9433)
        self.db.update_peer_status("node-1", connected=True, reputation=75.0)
        
        peer = self.db.get_peer("node-1")
        self.assertEqual(peer["connected"], 1)
        self.assertEqual(peer["reputation"], 75.0)
    
    def test_ban_peer(self):
        """Test banning a peer."""
        self.db.add_peer("bad-node", "192.168.1.100", 9433)
        self.db.ban_peer("bad-node")
        
        peer = self.db.get_peer("bad-node")
        self.assertEqual(peer["banned"], 1)
    
    def test_get_seed_peers(self):
        """Test getting seed peers for connection."""
        self.db.add_peer("node-1", "192.168.1.1", 9433)
        self.db.add_peer("node-2", "192.168.1.2", 9433)
        self.db.ban_peer("node-1")  # Banned peers should not be returned
        
        seeds = self.db.get_seed_peers(count=5)
        self.assertEqual(len(seeds), 1)
        self.assertEqual(seeds[0], ("192.168.1.2", 9433))
    
    def test_add_transaction(self):
        """Test adding a transaction."""
        txid = "abc123def456"
        tx_bytes = b"\x00\x01\x02\x03"
        
        added = self.db.add_transaction(txid, tx_bytes, "node-1")
        self.assertTrue(added)
    
    def test_transaction_deduplication(self):
        """Test that duplicate transactions are rejected."""
        txid = "abc123def456"
        tx_bytes = b"\x00\x01\x02\x03"
        
        self.db.add_transaction(txid, tx_bytes, "node-1")
        added = self.db.add_transaction(txid, tx_bytes, "node-2")
        self.assertFalse(added)
    
    def test_get_transaction(self):
        """Test getting a transaction by ID."""
        txid = "abc123def456"
        tx_bytes = b"\x00\x01\x02\x03"
        
        self.db.add_transaction(txid, tx_bytes, "node-1")
        tx = self.db.get_transaction(txid)
        
        self.assertIsNotNone(tx)
        self.assertEqual(tx["txid"], txid)
        self.assertEqual(tx["tx_bytes"], tx_bytes)
    
    def test_get_mempool(self):
        """Test getting pending transactions from mempool."""
        self.db.add_transaction("tx1", b"\x01", "node-1")
        self.db.add_transaction("tx2", b"\x02", "node-1")
        
        mempool = self.db.get_mempool(limit=10)
        self.assertEqual(len(mempool), 2)
    
    def test_mark_confirmed(self):
        """Test marking a transaction as confirmed."""
        self.db.add_transaction("tx1", b"\x01", "node-1")
        self.db.mark_confirmed("tx1", 100)
        
        tx = self.db.get_transaction("tx1")
        self.assertEqual(tx["confirmed"], 1)
        self.assertEqual(tx["block_height"], 100)
        self.assertEqual(tx["status"], "confirmed")
    
    def test_tx_exists(self):
        """Test checking if a transaction exists."""
        self.db.add_transaction("tx1", b"\x01", "node-1")
        
        self.assertTrue(self.db.tx_exists("tx1"))
        self.assertFalse(self.db.tx_exists("non-existent"))
    
    def test_add_block(self):
        """Test adding a block header."""
        added = self.db.add_block(
            block_hash="block123",
            header_bytes=b"\x00" * 80,
            height=100,
            prev_hash="prev123",
            timestamp=1000000000,
            bits=486604799,
            nonce=12345,
            received_from="node-1",
        )
        self.assertTrue(added)
    
    def test_block_deduplication(self):
        """Test that duplicate blocks are rejected."""
        self.db.add_block(
            "block123", b"\x00" * 80, 100, "prev123",
            1000000000, 486604799, 12345,
        )
        added = self.db.add_block(
            "block123", b"\x00" * 80, 100, "prev123",
            1000000000, 486604799, 12345,
        )
        self.assertFalse(added)
    
    def test_get_block(self):
        """Test getting a block by hash."""
        self.db.add_block(
            "block123", b"\x00" * 80, 100, "prev123",
            1000000000, 486604799, 12345,
        )
        block = self.db.get_block("block123")
        
        self.assertIsNotNone(block)
        self.assertEqual(block["block_hash"], "block123")
        self.assertEqual(block["height"], 100)
    
    def test_get_block_at_height(self):
        """Test getting a block by height."""
        self.db.add_block(
            "block123", b"\x00" * 80, 100, "prev123",
            1000000000, 486604799, 12345,
        )
        block = self.db.get_block_at_height(100)
        
        self.assertIsNotNone(block)
        self.assertEqual(block["block_hash"], "block123")
    
    def test_get_tip_height(self):
        """Test getting the highest block height."""
        self.db.add_block(
            "block1", b"\x00" * 80, 50, "prev1",
            1000000000, 486604799, 12345,
        )
        self.db.add_block(
            "block2", b"\x00" * 80, 100, "prev2",
            1000000000, 486604799, 12345,
        )
        
        tip = self.db.get_tip_height()
        self.assertEqual(tip, 100)
    
    def test_mark_validated(self):
        """Test marking a block as validated."""
        self.db.add_block(
            "block123", b"\x00" * 80, 100, "prev123",
            1000000000, 486604799, 12345,
        )
        self.db.mark_validated("block123")
        
        block = self.db.get_block("block123")
        self.assertEqual(block["validated"], 1)
    
    def test_add_resonance(self):
        """Test adding an EREPR resonance."""
        added = self.db.add_resonance(
            resonance_id="res123",
            phase=3.14,
            amplitude=1.0,
            origin_node_id="node-1",
            sequence=1,
            hops=0,
        )
        self.assertTrue(added)
    
    def test_resonance_deduplication(self):
        """Test that duplicate resonances are rejected."""
        self.db.add_resonance("res123", 3.14, 1.0)
        added = self.db.add_resonance("res123", 3.14, 1.0)
        self.assertFalse(added)
    
    def test_add_known_address(self):
        """Test adding a known address."""
        self.db.add_known_address("192.168.1.100", 9433, 0x01)
        
        addrs = self.db.get_known_addresses(limit=10)
        self.assertEqual(len(addrs), 1)
        self.assertEqual(addrs[0], ("192.168.1.100", 9433, 0x01))
    
    def test_save_checkpoint(self):
        """Test saving chain checkpoint."""
        self.db.save_checkpoint(100, "block123hash")
        
        checkpoint = self.db.get_checkpoint()
        self.assertEqual(checkpoint["tip_height"], 100)
        self.assertEqual(checkpoint["tip_hash"], "block123hash")
    
    def test_get_checkpoint_default(self):
        """Test getting default checkpoint."""
        checkpoint = self.db.get_checkpoint()
        self.assertIn("tip_height", checkpoint)
        self.assertIn("tip_hash", checkpoint)
    
    def test_get_stats(self):
        """Test getting database statistics."""
        self.db.add_peer("node-1", "192.168.1.1", 9433)
        self.db.add_transaction("tx1", b"\x01", "node-1")
        
        stats = self.db.get_stats()
        
        self.assertEqual(stats["peers_total"], 1)
        self.assertEqual(stats["transactions_pending"], 1)
        self.assertIn("blocks_total", stats)
        self.assertIn("erepr_resonances", stats)
        self.assertIn("known_addresses", stats)
    
    def test_persistence(self):
        """Test that data persists across database instances."""
        self.db.add_peer("node-1", "192.168.1.1", 9433)
        self.db.add_transaction("tx1", b"\x01", "node-1")
        
        # Create a new database instance pointing to the same file
        db2 = P2PDatabase(self.db_path)
        
        peer = db2.get_peer("node-1")
        self.assertIsNotNone(peer)
        
        tx = db2.get_transaction("tx1")
        self.assertIsNotNone(tx)


class TestGetDb(unittest.TestCase):
    """Test the global get_db function."""
    
    def test_get_db_returns_same_instance(self):
        """Test that get_db returns the same instance."""
        # Reset global state
        import sphinx_os.nexus.postgres_p2p as p2p_module
        p2p_module._default_db = None
        
        db1 = get_db()
        db2 = get_db()
        
        self.assertIs(db1, db2)
        
        # Clean up
        p2p_module._default_db = None


if __name__ == "__main__":
    unittest.main()
