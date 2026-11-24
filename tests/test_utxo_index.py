"""Regression tests for the persistent per-height UTXO index.

The index is a per-block delta log ((height, spent, created)) derived
during the ChainState replay; ChainState.utxo_at(height) rebuilds the
UTXO set at any canonical height from it without replaying the chain.
Tests cover: delta-apply equivalence with apply_block_txs, utxo_at
correctness vs the replay path in both walk directions, tip advance,
reorg rebuild, the on-disk binary format (round-trip, corruption,
staleness), and the Rosetta fast path with fallback.
"""
import json
import os
import tempfile
import unittest
from unittest.mock import patch

import chainstate
import utxo_index
from chainstate import ChainState
from genesis_fork import merkle_root, subsidy, txid
from rosetta.excal_rosetta import ExcalRosetta
from txscript import (apply_block_txs, apply_block_txs_delta, build_utxo,
                      ser_tx, txid_internal)

LOCK_A = b"\x00" + b"\xaa" * 20
LOCK_B = b"\x00" + b"\xbb" * 20
LOCK_C = b"\x00" + b"\xcc" * 20


def _coinbase(value, lock=b"\xff"):
    return ser_tx({
        "version": 1,
        "vin": [{"prev": bytes(32), "idx": 0xffffffff,
                 "script": b"", "seq": 0xffffffff}],
        "vout": [{"value": value, "script": lock}],
        "locktime": 0})


def _spend(prev_txid, prev_idx, value, lock, fee=1000):
    return ser_tx({
        "version": 1,
        "vin": [{"prev": prev_txid, "idx": prev_idx,
                 "script": b"", "seq": 0xffffffff}],
        "vout": [{"value": value - fee, "script": lock}],
        "locktime": 0})


class DeltaApplyTests(unittest.TestCase):
    def test_delta_apply_matches_plain_apply(self):
        cb1 = _coinbase(50000, LOCK_A)
        cb2 = _coinbase(50000, LOCK_B)
        spend = _spend(txid_internal(cb1), 0, 50000, LOCK_C)
        txs = [cb2, spend]
        # The view starts holding cb1:0, which the spend consumes.
        view_plain = {(txid_internal(cb1), 0): [(50000, LOCK_A, False, 0)]}
        view_delta = {(txid_internal(cb1), 0): [(50000, LOCK_A, False, 0)]}
        apply_block_txs(txs, view_plain, 5)
        spent, created = apply_block_txs_delta(txs, view_delta, 5)
        self.assertEqual(view_plain, view_delta)
        # The spend consumed cb1:0 (recorded with its row); the block
        # created the cb2 output and the spend output.
        self.assertEqual(len(spent), 1)
        self.assertEqual(spent[0][0], (txid_internal(cb1), 0))
        self.assertEqual(spent[0][1], (50000, LOCK_A, False, 0))
        self.assertEqual(len(created), 2)
        self.assertEqual(created[0][1], (50000, LOCK_B, True, 5))
        self.assertEqual(created[1][1], (49000, LOCK_C, False, 5))

    def test_delta_round_trips_through_binary_format(self):
        deltas = [
            (0, (), (((bytes.fromhex("11" * 32), 0),
                      (50000, LOCK_A, True, 0)),)),
            (1, (((bytes.fromhex("11" * 32), 0),
                  (50000, LOCK_A, True, 0)),),
             (((bytes.fromhex("22" * 32), 0),
               (49000, LOCK_B, False, 1)),)),
        ]
        raw = utxo_index.serialize_deltas(deltas)
        self.assertEqual(utxo_index.parse_deltas(raw), deltas)

    def test_binary_format_rejects_corruption(self):
        deltas = [(0, (), (((bytes.fromhex("11" * 32), 0),
                             (50000, LOCK_A, True, 0)),))]
        raw = bytearray(utxo_index.serialize_deltas(deltas))
        for mutated in (raw[:5] + b"\x00" + raw[6:],  # bad magic
                        raw[:-3],                      # truncated
                        raw + b"\x00"):                # trailing bytes
            with self.assertRaises(ValueError):
                utxo_index.parse_deltas(bytes(mutated))


class UtxoAtTests(unittest.TestCase):
    """Small real ChainState (testnet, validation stubbed) with spends."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cs = ChainState(self.tmp.name, net="testnet").load()
        self.genesis = self.cs.index[self.cs._tip_hash]
        self._tip = self.genesis
        self.blocks = []  # accepted records, height order
        self._submit_block([_coinbase(subsidy(1), LOCK_A)])          # h1
        cb1_txid = txid_internal(self.blocks[0]["txs"][0])
        self._submit_block([_coinbase(subsidy(2), LOCK_B),
                            _spend(cb1_txid, 0, subsidy(1), LOCK_C)])  # h2
        cb2_txid = txid_internal(self.blocks[1]["txs"][0])
        spend_out = txid_internal(self.blocks[1]["txs"][1])
        self._submit_block([_coinbase(subsidy(3), LOCK_A),
                            _spend(cb2_txid, 0, subsidy(2), LOCK_C),
                            _spend(spend_out, 0, subsidy(1) - 1000,
                                   LOCK_B)])                            # h3
        self.assertEqual(self.cs.tip()["height"], 3)

    def _submit_block(self, txs):
        height = self._tip["height"] + 1
        blk = {"version": 1, "prev": self._tip["hash"],
               "merkle": merkle_root([txid(t) for t in txs]),
               "time": self._tip["time"] + 60,
               "bits": self._tip["bits"], "nonce": height, "txs": txs}
        with patch.object(chainstate, "validate_block", return_value=None):
            result = self.cs.submit_block(blk)
        self.assertTrue(result["accepted"], result)
        self._tip = self.cs.index[self.cs._tip_hash]
        self.blocks.append(self._tip)
        return result

    def _replay(self, height):
        path = self.cs._path_to(self.cs._tip_hash)[:height + 1]
        return build_utxo([{"txs": rec["txs"]} for rec in path])

    def test_utxo_at_matches_replay_every_height(self):
        for h in range(0, 4):
            self.assertEqual(self.cs.utxo_at(h), self._replay(h),
                             f"height {h}")

    def test_utxo_at_matches_fork_utxo(self):
        for h in range(0, 4):
            rec = self.cs._path_to(self.cs._tip_hash)[h]
            self.assertEqual(self.cs.utxo_at(h),
                             self.cs._fork_utxo(rec["hash"]),
                             f"height {h}")

    def test_utxo_at_both_walk_directions(self):
        # Force the backward (undo-from-tip) walk, then the forward walk.
        for threshold in (0, 10 ** 9):
            with patch.object(chainstate, "_UTXO_FORWARD_THRESHOLD",
                              threshold):
                for h in range(0, 4):
                    self.assertEqual(self.cs.utxo_at(h), self._replay(h),
                                     f"threshold {threshold} height {h}")
            # Regression: the backward walk must not mutate the live tip
            # set (a shallow dict.copy() shares the row lists, and undo
            # pops/inserts into them — this silently corrupted the tip).
            self.assertEqual(self.cs.utxo, self._replay(3))

    def test_utxo_at_accepts_canonical_hash_rejects_other(self):
        rec = self.cs._path_to(self.cs._tip_hash)[2]
        self.assertEqual(self.cs.utxo_at(2, rec["hash"]), self._replay(2))
        with self.assertRaises(ValueError):
            self.cs.utxo_at(2, bytes.fromhex("99" * 32))
        with self.assertRaises(ValueError):
            self.cs.utxo_at(4)
        with self.assertRaises(ValueError):
            self.cs.utxo_at(-1)

    def test_utxo_at_does_not_alias_tip(self):
        view = self.cs.utxo_at(3)
        key = next(iter(view))
        del view[key]
        view[(bytes.fromhex("ff" * 32), 9)] = [(1, b"\xff", False, 0)]
        self.assertEqual(self.cs.utxo_at(3), self._replay(3))
        self.assertEqual(self.cs.utxo, self._replay(3))

    def test_tip_advance_extends_index(self):
        cb3_txid = txid_internal(self.blocks[2]["txs"][0])
        self._submit_block([_coinbase(subsidy(4), LOCK_B),
                            _spend(cb3_txid, 0, subsidy(3), LOCK_C)])
        self.assertEqual(self.cs.tip()["height"], 4)
        for h in range(0, 5):
            self.assertEqual(self.cs.utxo_at(h), self._replay(h),
                             f"height {h}")

    def test_reorg_rebuilds_index(self):
        # Rival branch at height 1 (side branch) grown to 4 blocks: it
        # outweighs the 3-block active chain, so the tip reorgs onto it
        # and the old heights 1-3 are unwound.
        rival_cb = _coinbase(subsidy(1), LOCK_B)
        rival = {"version": 1, "prev": self.genesis["hash"],
                 "merkle": merkle_root([txid(rival_cb)]),
                 "time": self.genesis["time"] + 60,
                 "bits": self.genesis["bits"], "nonce": 99,
                 "txs": [rival_cb]}
        with patch.object(chainstate, "validate_block", return_value=None):
            result = self.cs.submit_block(rival)
        self.assertTrue(result["accepted"], result)
        self.assertIsNone(result["event"])  # side branch, tip untouched
        self.assertEqual(self.cs.tip()["height"], 3)
        prev_hash = chainstate._header_hash(rival)
        event = None
        for h in (2, 3, 4):
            blk = {"version": 1, "prev": prev_hash,
                   "merkle": merkle_root(
                       [txid(_coinbase(subsidy(h), LOCK_A))]),
                   "time": self.genesis["time"] + 60 * h,
                   "bits": self.genesis["bits"], "nonce": 100 + h,
                   "txs": [_coinbase(subsidy(h), LOCK_A)]}
            with patch.object(chainstate, "validate_block",
                              return_value=None):
                result = self.cs.submit_block(blk)
            self.assertTrue(result["accepted"], result)
            prev_hash = chainstate._header_hash(blk)
            event = result["event"]
        self.assertIsNotNone(event)
        self.assertEqual(event["height"], 4)
        self.assertEqual(self.cs.tip()["height"], 4)
        # The new active chain is genesis -> rival -> ...: every height
        # must reflect the rival branch, verified against a fresh replay.
        for h in range(0, 5):
            self.assertEqual(self.cs.utxo_at(h), self._replay(h),
                             f"height {h} after reorg")
        # Height 1 no longer pays LOCK_A (old block) but LOCK_B (rival).
        view1 = self.cs.utxo_at(1)
        scripts = {e[1] for rows in view1.values() for e in rows}
        self.assertIn(LOCK_B, scripts)
        self.assertNotIn(LOCK_A, scripts)

    def test_persisted_index_survives_reload(self):
        paths = utxo_index.index_paths(self.tmp.name)
        self.assertTrue(os.path.exists(paths["deltas"]))
        with open(paths["manifest"], encoding="utf-8") as f:
            manifest = json.load(f)
        self.assertEqual(manifest["tip_height"], 3)
        self.assertEqual(manifest["tip_hash"], self.cs.tip()["hash"])
        fresh = ChainState(self.tmp.name, net="testnet").load()
        self.assertEqual(fresh._utxo_deltas, self.cs._utxo_deltas)
        for h in range(0, 4):
            self.assertEqual(fresh.utxo_at(h), self._replay(h))

    def test_corrupt_disk_index_rebuilt_from_replay(self):
        paths = utxo_index.index_paths(self.tmp.name)
        with open(paths["deltas"], "r+b") as f:
            f.seek(20)
            f.write(b"\xff")
        fresh = ChainState(self.tmp.name, net="testnet").load()
        for h in range(0, 4):
            self.assertEqual(fresh.utxo_at(h), self._replay(h))
        # The reload rewrote a valid disk index (sha256 matches again).
        self.assertIsNotNone(
            utxo_index.read_index(self.tmp.name, 3,
                                  bytes.fromhex(fresh.tip()["hash"])))


class RosettaFastPathTests(unittest.TestCase):
    def test_block_render_uses_utxo_at_not_replay(self):
        with tempfile.TemporaryDirectory() as d:
            cs = ChainState(d, net="testnet").load()
            genesis = cs.index[cs._tip_hash]
            cb = _coinbase(subsidy(1), LOCK_A)
            blk = {"version": 1, "prev": genesis["hash"],
                   "merkle": merkle_root([txid(cb)]),
                   "time": genesis["time"] + 60,
                   "bits": genesis["bits"], "nonce": 1, "txs": [cb]}
            with patch.object(chainstate, "validate_block",
                              return_value=None):
                self.assertTrue(cs.submit_block(blk)["accepted"])
            calls = []
            orig = cs._fork_utxo
            cs._fork_utxo = lambda h: (calls.append(h), orig(h))[1]
            app = ExcalRosetta(cs, network="mainnet")
            block = app._block(1)
            self.assertEqual(
                block["transactions"][0]["operations"][0]["amount"]["value"],
                str(subsidy(1)))
            self.assertEqual(calls, [])  # fast path: no full-chain replay
            # Balances agree with the replay path.
            net = {"network_identifier": {"blockchain": "excal",
                                          "network": "mainnet"}}
            status, body = app.handle("/account/balance", dict(
                net, account_identifier={"address": "lock:" + LOCK_A.hex()},
                block_identifier={"index": 1}))
            self.assertEqual(status, 200)
            self.assertEqual(body["balances"][0]["value"], str(subsidy(1)))

    def test_rosetta_falls_back_when_fast_path_fails(self):
        from types import SimpleNamespace
        lock = LOCK_A
        cb = _coinbase(50000, lock)
        ghash = bytes.fromhex("11" * 32)
        b1hash = bytes.fromhex("22" * 32)
        genesis = {"height": 0, "hash": ghash, "time": 100,
                   "version": 1, "bits": 0x1f000100, "nonce": 0, "txs": []}
        block1 = {"height": 1, "hash": b1hash, "prev": ghash,
                  "time": 160, "version": 1, "bits": 0x1f000100,
                  "nonce": 1, "txs": [cb]}
        calls = []
        cs = SimpleNamespace(
            by_height={0: genesis, 1: block1}, utxo={},
            tip=lambda: {"height": 1, "hash": b1hash})
        cs._fork_utxo = lambda h: (calls.append(h),
                                   {(txid_internal(cb), 0):
                                    [(50000, lock, True, 1)]})[1]
        def _broken_utxo_at(h, bh=None):
            raise ValueError("index unavailable")
        cs.utxo_at = _broken_utxo_at
        app = ExcalRosetta(cs, network="mainnet")
        block = app._block(1)
        self.assertEqual(
            block["transactions"][0]["operations"][0]["amount"]["value"],
            "50000")
        self.assertEqual(len(calls), 1)  # fell back to the replay hook


if __name__ == "__main__":
    unittest.main()
