"""Regression tests for ChainState.submit_block control flow.

Regression: commit d6edd2e7 ("reject deep reorgs before persisting
candidate blocks") moved the persist/index step out of the best-chain
branch but left the tip-advance block at an indentation with no
enclosing block, so chainstate.py did not even import (IndentationError
at the apply_block_txs line). The Rosetta standalone server could not
load any ChainState until this was fixed.

These tests stub only PoW/consensus validation (validate_block): they
cover submit_block's own control flow — best-chain tip advance vs.
side-branch handling — not consensus correctness.
"""
import os
import tempfile
import unittest
from unittest.mock import patch

import chainstate
from chainstate import ChainState
from genesis_fork import merkle_root, subsidy, txid
from spent_leaf_registry import SpentLeafRegistry, pair_key
from txscript import ser_tx


def _coinbase(value):
    return ser_tx({
        "version": 1,
        "vin": [{"prev": bytes(32), "idx": 0xffffffff,
                 "script": b"", "seq": 0xffffffff}],
        "vout": [{"value": value, "script": b"\xff"}],
        "locktime": 0})


class ChainStateSubmitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cs = ChainState(self.tmp.name, net="testnet").load()
        self.assertEqual(self.cs.tip()["height"], 0)
        self.genesis = self.cs.index[self.cs._tip_hash]

    def _block(self, nonce):
        cb = _coinbase(subsidy(1))
        return {"version": 1, "prev": self.genesis["hash"],
                "merkle": merkle_root([txid(cb)]),
                "time": self.genesis["time"] + 60,
                "bits": self.genesis["bits"], "nonce": nonce, "txs": [cb]}

    def test_best_chain_block_advances_tip(self):
        with patch.object(chainstate, "validate_block", return_value=None):
            result = self.cs.submit_block(self._block(1))
        self.assertTrue(result["accepted"], result)
        self.assertEqual(result["event"]["height"], 1)
        self.assertEqual(self.cs.tip()["height"], 1)

    def test_side_branch_block_leaves_tip_untouched(self):
        with patch.object(chainstate, "validate_block", return_value=None):
            first = self.cs.submit_block(self._block(1))
            self.assertTrue(first["accepted"], first)
            rival = self.cs.submit_block(self._block(2))
        self.assertTrue(rival["accepted"], rival)
        self.assertIsNone(rival["event"])
        self.assertEqual(rival["reason"], "side branch")
        self.assertEqual(self.cs.tip()["height"], 1)


class SpentLeafRegistryTests(unittest.TestCase):
    """Regression: chainstate.py imports pair_key and calls
    SpentLeafRegistry.replace_with, but neither existed in
    spent_leaf_registry.py, so importing ChainState failed."""

    def test_pair_key_format_round_trips_through_chainstate_parsing(self):
        key = pair_key(bytes.fromhex("ab" * 32), 7)
        self.assertEqual(key, "ab" * 32 + ":7")
        root_hex, idx = key.rsplit(":", 1)
        self.assertEqual((root_hex, int(idx)), ("ab" * 32, 7))

    def test_replace_with_rebuilds_registry_from_chain_refs(self):
        with tempfile.TemporaryDirectory() as d:
            reg = SpentLeafRegistry(os.path.join(d, "spent.json"))
            root = bytes.fromhex("11" * 32)
            reg.record(root, 0, txid="old", height=1)
            self.assertTrue(reg.is_spent(root, 0))
            refs = {pair_key(bytes.fromhex("22" * 32), 3):
                    {"txid": "new", "height": 5}}
            reg.replace_with(refs)
            self.assertFalse(reg.is_spent(root, 0))
            self.assertTrue(reg.is_spent(bytes.fromhex("22" * 32), 3))
            self.assertEqual(reg.first_spend(bytes.fromhex("22" * 32), 3)["txid"], "new")
            # Reload from disk: the replacement persisted.
            reg2 = SpentLeafRegistry(os.path.join(d, "spent.json"))
            self.assertTrue(reg2.is_spent(bytes.fromhex("22" * 32), 3))
            self.assertFalse(reg2.is_spent(root, 0))

    def test_replace_with_rejects_malformed_refs_without_touching_disk(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "spent.json")
            reg = SpentLeafRegistry(path)
            root = bytes.fromhex("33" * 32)
            reg.record(root, 0, txid="keep", height=2)
            with self.assertRaises(ValueError):
                reg.replace_with({"not-a-key": {"txid": "x", "height": 1}})
            self.assertTrue(reg.is_spent(root, 0))
            self.assertEqual(reg.first_spend(root, 0)["txid"], "keep")

    def test_legacy_pair_key_map_loads(self):
        # The live chaindata registry is a single JSON object mapping
        # pair_key -> {"txid", "height"}; the loader must accept it
        # instead of failing closed as corrupt.
        import json
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "spent.json")
            legacy = {pair_key(bytes.fromhex("44" * 32), 2):
                      {"txid": "abc", "height": 9}}
            with open(path, "w", encoding="utf-8") as f:
                f.write(json.dumps(legacy) + "\n")
            reg = SpentLeafRegistry(path)
            self.assertTrue(reg.is_spent(bytes.fromhex("44" * 32), 2))
            self.assertEqual(reg.first_spend(bytes.fromhex("44" * 32), 2)["txid"], "abc")


if __name__ == "__main__":
    unittest.main()
