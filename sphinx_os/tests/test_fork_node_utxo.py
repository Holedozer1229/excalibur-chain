import json
import os
import tempfile
import unittest
from unittest.mock import patch

import genesis_fork as gf
from fork_node import ChainStore
import txscript


def genesis_record():
    gf.use_network("fork")
    header = gf.genesis_for("fork")
    block_hash = gf.sha256d(gf.ser_header(
        header["version"], header["prev"], header["merkle"], header["time"],
        header["bits"], header["nonce"]))
    return {
        "height": 0,
        "version": header["version"],
        "prev": header["prev"].hex(),
        "merkle": header["merkle"].hex(),
        "time": header["time"],
        "bits": header["bits"],
        "nonce": header["nonce"],
        "hash": block_hash.hex(),
        "txs": [],
    }


class TestForkNodeUtxoReplay(unittest.TestCase):
    def setUp(self):
        previous = next(name for name, params in gf.NETWORKS.items()
                        if params is gf.network())
        self.addCleanup(gf.use_network, previous)

    def _store(self, directory, record):
        path = os.path.join(directory, "chain.jsonl")
        with open(path, "w", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
        return ChainStore(path)

    def test_block_bytes_normalizes_auxpow_hex_fields(self):
        record = genesis_record()
        record["auxpow"] = {
            "parent_header": "01" * 80,
            "parent_coinbase": "02aabb",
            "coinbase_branch": ["03" * 32],
            "coinbase_index": 0,
        }

        block = ChainStore._block_bytes(record)

        self.assertEqual(block["auxpow"]["parent_header"], bytes.fromhex("01" * 80))
        self.assertEqual(block["auxpow"]["parent_coinbase"], bytes.fromhex("02aabb"))
        self.assertEqual(block["auxpow"]["coinbase_branch"], [bytes.fromhex("03" * 32)])
        self.assertEqual(block["auxpow"]["coinbase_index"], 0)

    def test_valid_fork_genesis_builds_complete_empty_utxo_set(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory, genesis_record())
            self.assertTrue(store.utxo_complete, store.utxo_error)
            self.assertEqual(store.utxo, {})
            self.assertEqual(store.getwalletutxos([]), {
                "complete": True, "utxos": [],
            })

    def test_bad_history_keeps_balance_and_spending_disabled(self):
        record = genesis_record()
        record["merkle"] = "00" * 32
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory, record)
            self.assertFalse(store.utxo_complete)
            self.assertIn("header hash mismatch", store.utxo_error)
            self.assertFalse(store.getwalletutxos([])["complete"])
            with self.assertRaisesRegex(RuntimeError, "complete validated UTXO"):
                store.sendrawtransaction("00")

    def test_load_uses_tip_ancestry_when_snapshot_contains_side_branches(self):
        genesis = genesis_record()
        stale_height_one = dict(
            genesis, height=1, hash="aa" * 32, prev=genesis["hash"], time=1
        )
        active_height_one = dict(
            genesis, height=1, hash="bb" * 32, prev=genesis["hash"], time=2
        )
        active_height_two = dict(
            genesis, height=2, hash="cc" * 32,
            prev=active_height_one["hash"], time=3,
        )
        stale_height_two = dict(
            genesis, height=2, hash="dd" * 32,
            prev=stale_height_one["hash"], time=4,
        )

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "chain.jsonl")
            with open(path, "w", encoding="utf-8") as chain_file:
                for record in (
                    genesis, stale_height_one, active_height_one,
                    active_height_two, stale_height_two,
                ):
                    chain_file.write(json.dumps(record) + "\n")

            with patch.object(ChainStore, "_rebuild_utxo", lambda _store: None):
                store = ChainStore(path)

        self.assertEqual(store.tip_height, 2)
        self.assertEqual(store.tip_hash, active_height_two["hash"])
        self.assertEqual(store.by_height[1]["hash"], active_height_one["hash"])
        self.assertEqual(store.by_height[2]["hash"], active_height_two["hash"])
        self.assertIn(stale_height_one["hash"], store.by_hash)
        self.assertIn(stale_height_two["hash"], store.by_hash)

    def test_lock_utxos_report_maturity_and_pending_spends(self):
        with tempfile.TemporaryDirectory() as directory:
            store = self._store(directory, genesis_record())
            lock = txscript.lock_pkh(bytes.fromhex("91" * 20))
            outpoint = (bytes.fromhex("82" * 32), 0)
            entry = (500, lock, True, 0)
            store.utxo[outpoint] = [entry]
            store.mempool_view = {outpoint: [entry]}
            store.tip_height = 98
            row = store.getutxos(lock.hex())[0]
            self.assertFalse(row["mature"])
            self.assertFalse(row["pending_spend"])
            self.assertFalse(row["spendable"])

            store.tip_height = 99
            store.mempool_view = {}
            row = store.getutxos(lock.hex())[0]
            self.assertTrue(row["mature"])
            self.assertTrue(row["pending_spend"])
            self.assertFalse(row["spendable"])


if __name__ == "__main__":
    unittest.main()
