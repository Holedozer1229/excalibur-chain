import json
import os
import tempfile
import threading
import unittest

import genesis_fork as gf
import trifold_lockbox
from spent_leaf_registry import SpentLeafRegistry
import txpq
import txscript


class TestTrifoldStateSafety(unittest.TestCase):
    def test_shared_state_allocates_unique_leaves_across_key_instances(self):
        seed = bytes.fromhex("31" * 32)
        with tempfile.TemporaryDirectory() as directory:
            state_path = os.path.join(directory, "state.json")
            keys = [
                trifold_lockbox.TrifoldKey(seed, height=1, state_path=state_path)
                for _ in range(2)
            ]
            barrier = threading.Barrier(2)
            signatures = [None, None]
            errors = []

            def sign(slot):
                try:
                    barrier.wait()
                    signatures[slot] = keys[slot].sign(f"message-{slot}".encode())
                except Exception as exc:  # collected for an assertion in the test thread
                    errors.append(exc)

            threads = [threading.Thread(target=sign, args=(i,)) for i in range(2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertEqual(errors, [])
            self.assertEqual({sig["index"] for sig in signatures}, {0, 1})
            self.assertTrue(all(
                trifold_lockbox.verify(keys[0].root, f"message-{i}".encode(), signatures[i])
                for i in range(2)
            ))
            with open(state_path, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["next_index"], 2)

    def test_signing_without_persistent_state_fails_closed(self):
        key = trifold_lockbox.TrifoldKey(bytes.fromhex("42" * 32), height=1)
        with self.assertRaisesRegex(RuntimeError, "persistent state_path"):
            key.sign(b"message")

    def test_tree_height_fits_three_byte_witness_index(self):
        with self.assertRaisesRegex(ValueError, "between 1 and 10"):
            trifold_lockbox.TrifoldKey(bytes.fromhex("42" * 32), height=16)

    def test_verifier_rejects_malformed_signature_shapes(self):
        key = trifold_lockbox.TrifoldKey(bytes.fromhex("53" * 32), height=1)
        self.assertFalse(trifold_lockbox.verify(key.root, b"message", {}))
        self.assertFalse(trifold_lockbox.verify(key.root, b"message", {
            "index": 0, "ots_sig": [], "ots_pub": [], "path": [],
        }))
        with self.assertRaisesRegex(ValueError, "Lamport signature"):
            txpq.encode_witness(key.root, {"index": 0}, height=1)
        with self.assertRaisesRegex(ValueError, "must be bytes"):
            txpq.decode_witness(None)

    def test_registry_reservation_is_shared_between_instances(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "spent.jsonl")
            first = SpentLeafRegistry(path)
            second = SpentLeafRegistry(path)
            root = bytes.fromhex("64" * 32)
            self.assertTrue(first.reserve(root, 7))
            self.assertFalse(second.reserve(root, 7))
            self.assertEqual(second.first_spend(root, 7)["index"], 7)
            self.assertEqual(second.as_set(), {(root, 7)})

    def test_block_validation_requires_chain_wide_spent_state(self):
        ok, reason, _fee = txscript.validate_block_txs(
            [], {}, 1, gf.subsidy(1), spent_pairs=None)
        self.assertFalse(ok)
        self.assertIn("spent-leaf state", reason)

    def test_same_leaf_is_rejected_in_a_later_block(self):
        old_network = next(name for name, params in gf.NETWORKS.items()
                           if params is gf.network())
        self.addCleanup(gf.use_network, old_network)
        gf.use_network("fork")
        key = trifold_lockbox.TrifoldKey(bytes.fromhex("75" * 32), height=1)
        lock = txscript.lock_pqh_for_root(key.root)
        spent_pairs = set()

        def make_spend(prev_txid, height):
            tx = {
                "version": 1,
                "vin": [{"prev": prev_txid, "idx": 0, "script": b"",
                         "seq": 0xFFFFFFFF}],
                "vout": [{"value": 90, "script": lock}],
                "locktime": 0,
            }
            sighash = txscript.sighash_all(tx, 0, lock)
            signature = key._sign_reserved(sighash, 0)
            tx["vin"][0]["script"] = txpq.encode_witness(
                key.root, signature, key.height)
            raw = txscript.ser_tx(tx)
            coinbase = gf.make_coinbase(height, gf.network()["min_bits"],
                                        f"test-{height}".encode(), fees=10)
            return raw, coinbase

        for n, height in enumerate((gf.qday_activation(),
                                    gf.qday_activation() + 1), 1):
            prev = bytes([n]) * 32
            raw, coinbase = make_spend(prev, height)
            utxo = {(prev, 0): [(100, lock, False, 0)]}
            ok, reason, _fee = txscript.validate_block_txs(
                [coinbase, raw], utxo, height, gf.subsidy(height),
                spent_pairs=spent_pairs)
            if height == 1:
                self.assertTrue(ok, reason)
            else:
                self.assertFalse(ok)
                self.assertIn("spent leaf already used", reason)


if __name__ == "__main__":
    unittest.main()
