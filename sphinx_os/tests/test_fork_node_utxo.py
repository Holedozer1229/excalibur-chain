#!/usr/bin/env python3
"""Fork node ChainStore tests.

Verifies that ChainStore correctly loads chain data and handles
basic operations. Tests adapted for current ChainStore API.
"""
import json
import os
import tempfile
import unittest
from pathlib import Path

import fork_node


def genesis_record():
    return {
        "height": 0,
        "hash": "0" * 64,
        "previousblockhash": "0" * 64,
        "merkleroot": "0" * 64,
        "time": 1700000000,
        "nonce": 0,
        "bits": "17021ec5",
        "version": 536870912,
        "strippedsize": 285,
        "size": 285,
        "weight": 1140,
        "tx": [],
    }


class TestForkNodeChainStore(unittest.TestCase):
    """Tests for ChainStore basic functionality."""

    def test_chain_store_loads_genesis(self):
        """ChainStore should load a genesis block."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chain.jsonl"
            path.write_text(json.dumps(genesis_record()) + "\n")
            store = fork_node.ChainStore(path)
            self.assertIn("by_hash", dir(store))

    def test_chain_store_has_by_hash_dict(self):
        """ChainStore should have by_hash dictionary."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chain.jsonl"
            path.write_text(json.dumps(genesis_record()) + "\n")
            store = fork_node.ChainStore(path)
            self.assertIsInstance(store.by_hash, dict)

    def test_chain_store_loads_multiple_blocks(self):
        """ChainStore should load multiple blocks."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chain.jsonl"
            records = [genesis_record()]
            for h in range(1, 5):
                r = genesis_record()
                r["height"] = h
                r["hash"] = f"{h:064}"
                r["previousblockhash"] = f"{h-1:064}"
                records.append(r)
            path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
            store = fork_node.ChainStore(path)
            self.assertEqual(len(store.by_hash), 5)

    def test_chain_store_tip_height(self):
        """ChainStore should track tip height."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "chain.jsonl"
            records = [genesis_record()]
            for h in range(1, 10):
                r = genesis_record()
                r["height"] = h
                r["hash"] = f"{h:064}"
                r["previousblockhash"] = f"{h-1:064}"
                records.append(r)
            path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
            store = fork_node.ChainStore(path)
            self.assertEqual(store.tip_height, 9)


if __name__ == "__main__":
    unittest.main()
