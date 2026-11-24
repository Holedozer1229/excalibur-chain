"""Two-node relay + reorg and Rosetta fee-rendering tests (Stage 3).

The relay/reorg scenario uses REAL proof of work on testnet
(min_bits 0x1f010000, ~2^16 hashes per block, a few seconds each under
the VM's current load) and REAL ChainState.submit_block validation —
no validate_block stubbing. Two ChainState instances in separate temp
dirs stand in for two nodes; "relay" is delivery of the validated
block records node-to-node, which is exactly what the P2P layer hands
submit_block after header validation. No live P2P sockets are opened:
spinning up two fork_node peers with real sockets is out of scope for
tonight's window, and the relay path under test (submit_block accept /
side-branch / reorg / duplicate / orphan) is the code the P2P layer
feeds.

Coinbase locks: the coinbases are hand-built (same shape as
make_coinbase_v2, whose lock choice is forced to OP_TRUE below
qlock_activation) so each branch pays a distinct PKH lock and the
branches are distinguishable by balance. validate_block only checks
coinbase lineage and value, never the coinbase lock, so this is valid
under the implemented consensus.

The Rosetta fee test below uses the stubbed-validation convention
already used by tests/test_utxo_index.py (validate_block patched) for
its fixture chain only — a real spend chain needs 100-block coinbase
maturity, which would mean mining ~100 blocks. The rendering it
checks is cross-tied to real consensus in the same test: the identical
spend bytes are run through validate_tx at a mature height and the
fees must match exactly.
"""
import os
import struct
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import genesis_fork
import secp256k1 as secp
from chainstate import ChainState
from genesis_fork import (bits_to_target, merkle_root, ser_header, sha256d,
                          subsidy, txid)
from rosetta.excal_rosetta import ExcalRosetta
from txscript import (lock_pkh_for_pubkey, parse_tx, ser_tx, sighash_all,
                      sign_pkh_input, txid_internal, validate_tx)

BITS = 0x1f010000  # testnet min_bits: ~2^16 hashes per block
NONCE_CAP = 5_000_000


def pub(priv):
    return secp.compress(secp.priv_to_pub(priv))


def _coinbase(height, lock, tag):
    """Coinbase paying `lock`, BIP34-style height push, lineage-valid."""
    from genesis_fork import push, ser_varint
    scriptsig = (push(struct.pack("<I", BITS)) + push(tag)
                 + push(struct.pack("<I", height)))
    tx = struct.pack("<I", 1)
    tx += b"\x01"
    tx += bytes(32) + struct.pack("<I", 0xffffffff)
    tx += ser_varint(len(scriptsig)) + scriptsig
    tx += struct.pack("<I", 0xffffffff)
    tx += b"\x01"
    tx += struct.pack("<Q", subsidy(height))
    tx += ser_varint(len(lock)) + lock
    tx += struct.pack("<I", 0)
    return tx


def _mine(prev_hash, prev_time, height, txs):
    """Find a nonce whose header hash meets the testnet target."""
    mk = merkle_root([txid(t) for t in txs])
    target = bits_to_target(BITS)
    prefix = (struct.pack("<I", 1) + bytes(prev_hash) + bytes(mk)
              + struct.pack("<II", prev_time, BITS))
    for nonce in range(NONCE_CAP):
        hh = sha256d(prefix + struct.pack("<I", nonce))
        if int.from_bytes(hh, "big") <= target:
            return {"version": 1, "prev": bytes(prev_hash),
                    "merkle": mk, "time": prev_time, "bits": BITS,
                    "nonce": nonce, "txs": list(txs)}
    raise AssertionError(f"no nonce found in {NONCE_CAP} tries")


def _relay(src_cs, dst_cs):
    """Deliver every non-genesis block of src's active chain to dst."""
    results = []
    for rec in src_cs._path_to(src_cs._tip_hash)[1:]:
        blk = {"version": rec["version"], "prev": rec["prev"],
               "merkle": rec["merkle"], "time": rec["time"],
               "bits": rec["bits"], "nonce": rec["nonce"],
               "txs": list(rec["txs"])}
        res = dst_cs.submit_block(blk)
        assert res["accepted"], res
        results.append(res)
    return results


class TwoNodeRelayReorgTests(unittest.TestCase):
    def setUp(self):
        genesis_fork.use_network("testnet")
        self.addCleanup(genesis_fork.use_network, "testnet")
        self.tmp_a = tempfile.TemporaryDirectory()
        self.tmp_b = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_a.cleanup)
        self.addCleanup(self.tmp_b.cleanup)
        self.node_a = ChainState(self.tmp_a.name, net="testnet").load()
        self.node_b = ChainState(self.tmp_b.name, net="testnet").load()
        self.genesis = self.node_a.index[self.node_a._tip_hash]
        self.lock_a = lock_pkh_for_pubkey(pub(11))
        self.lock_b = lock_pkh_for_pubkey(pub(12))

    def _mine_on(self, node, prev_hash, prev_time, height, lock, tag):
        cb = _coinbase(height, lock, tag)
        blk = _mine(prev_hash, prev_time, height, [cb])
        res = node.submit_block(blk)
        self.assertTrue(res["accepted"], res)
        return blk, res, cb

    def test_relay_then_rival_branch_reorgs_both_nodes(self):
        gtime = self.genesis["time"]
        ghash = self.genesis["hash"]
        # Node A mines two blocks and relays them to B.
        tip_hash = ghash
        blk_a1, _, cb_a1 = self._mine_on(
            self.node_a, tip_hash, gtime + 60, 1, self.lock_a, b"Excalibur-A1")
        tip_hash = bytes.fromhex(self.node_a.tip()["hash"])
        blk_a2, _, cb_a2 = self._mine_on(
            self.node_a, tip_hash, gtime + 120, 2, self.lock_a, b"Excalibur-A2")
        self.assertEqual(self.node_a.tip()["height"], 2)
        _relay(self.node_a, self.node_b)
        self.assertEqual(self.node_b.tip()["height"], 2)
        self.assertEqual(self.node_b.tip()["hash"],
                         self.node_a.tip()["hash"])
        # Node B mines a rival branch from genesis (distinct coinbase
        # locks/tags). The first two rival blocks are side branches on
        # both nodes; the third outweighs A's chain and reorgs it.
        from chainstate import _header_hash
        rival = []
        prev_hash, prev_time = ghash, gtime
        for h, tag in ((1, b"Excalibur-R1"), (2, b"Excalibur-R2"),
                       (3, b"Excalibur-R3")):
            cb = _coinbase(h, self.lock_b, tag)
            blk = _mine(prev_hash, prev_time + 60, h, [cb])
            res = self.node_b.submit_block(blk)
            self.assertTrue(res["accepted"], res)
            rival.append((blk, res, cb))
            prev_hash = _header_hash(blk)
            prev_time = blk["time"]
        self.assertEqual(self.node_b.tip()["height"], 3)
        # Deliver the rival branch to A one block at a time.
        events = []
        for blk, _res, _cb in rival:
            res = self.node_a.submit_block(blk)
            self.assertTrue(res["accepted"], res)
            events.append(res)
        self.assertIsNone(events[0]["event"])  # side branch
        self.assertIsNone(events[1]["event"])  # side branch (equal work)
        event = events[2]["event"]
        self.assertIsNotNone(event)
        self.assertEqual(event["height"], 3)
        self.assertEqual([r["height"] for r in event["removed"]], [1, 2])
        self.assertEqual([r["height"] for r in event["added"]], [1, 2, 3])
        self.assertEqual(self.node_a.tip()["height"], 3)
        self.assertEqual(self.node_a.tip()["hash"],
                         self.node_b.tip()["hash"])
        # The UTXO set follows the new tip: A's coinbases are gone,
        # the rival coinbases are the only outputs.
        view1 = self.node_a.utxo_at(1)
        self.assertEqual(
            {(k, e) for k, rows in view1.items() for e in rows},
            {((txid_internal(rival[0][2]), 0),
              (subsidy(1), self.lock_b, True, 1))})
        self.assertEqual(self.node_a.utxo_at(2),
                         self._replay(self.node_a, 2))
        # Balances via Rosetta follow the new tip too.
        app = ExcalRosetta(self.node_a, network="testnet")
        net = {"network_identifier": {"blockchain": "excal",
                                      "network": "testnet"}}
        for lock, want in ((self.lock_a, "0"),
                           (self.lock_b, str(3 * subsidy(1)))):
            status, body = app.handle("/account/balance", dict(
                net, account_identifier={"address": "lock:" + lock.hex()}))
            self.assertEqual(status, 200, body)
            self.assertEqual(body["balances"][0]["value"], want)
        # /block 1 now renders the rival coinbase, not A's.
        status, body = app.handle("/block", dict(
            net, block_identifier={"index": 1}))
        self.assertEqual(status, 200, body)
        self.assertEqual(
            body["block"]["transactions"][0]["transaction_identifier"]["hash"],
            txid_internal(rival[0][2])[::-1].hex())
        # The reorged-away coinbase is no longer found at height 1.
        status, body = app.handle("/block/transaction", dict(
            net, block_identifier={"index": 1},
            transaction_identifier={"hash":
                                    txid_internal(cb_a1)[::-1].hex()}))
        self.assertEqual(status, 500)
        self.assertEqual(body["code"], 3)
        # Relay robustness: duplicate delivery and orphans are refused.
        dup = self.node_a.submit_block(rival[2][0])
        self.assertFalse(dup["accepted"])
        self.assertEqual(dup["reason"], "duplicate block")
        orphan = dict(rival[0][0], prev=bytes.fromhex("99" * 32))
        bad = self.node_a.submit_block(orphan)
        self.assertFalse(bad["accepted"])
        self.assertEqual(bad["reason"], "orphan: unknown prev")
        # The reorg survives a reload: the persisted chain is the rival.
        fresh = ChainState(self.tmp_a.name, net="testnet").load()
        self.assertEqual(fresh.tip(), self.node_a.tip())
        self.assertEqual(fresh.utxo_at(3), self.node_a.utxo_at(3))

    def _replay(self, node, height):
        from txscript import build_utxo
        path = node._path_to(node._tip_hash)[:height + 1]
        return build_utxo([{"txs": rec["txs"]} for rec in path])


class RosettaFeeRenderingTests(unittest.TestCase):
    """Rosetta /block fee reporting from historical prevouts.

    Fixture chain built with validate_block stubbed (the convention in
    tests/test_utxo_index.py): block 2 spends block 1's coinbase, which
    real consensus would reject as immature — this fixture therefore
    proves only the RENDERING path. The fee numbers are cross-checked
    against real consensus (validate_tx at a mature height) for the
    identical spend bytes in the same test.
    """

    def setUp(self):
        genesis_fork.use_network("testnet")
        self.addCleanup(genesis_fork.use_network, "testnet")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cs = ChainState(self.tmp.name, net="testnet").load()
        self.genesis = self.cs.index[self.cs._tip_hash]
        self.lock_a = lock_pkh_for_pubkey(pub(1))
        self.lock_b = lock_pkh_for_pubkey(pub(2))
        self.lock_c = lock_pkh_for_pubkey(pub(3))

    def _coinbase(self, value, lock=b"\xff"):
        return ser_tx({
            "version": 1,
            "vin": [{"prev": bytes(32), "idx": 0xffffffff,
                     "script": b"", "seq": 0xffffffff}],
            "vout": [{"value": value, "script": lock}],
            "locktime": 0})

    def _spend(self, prev_txid, prev_idx, value, in_lock, priv, out_lock,
               fee=1000):
        t = {"version": 1,
             "vin": [{"prev": prev_txid, "idx": prev_idx,
                      "script": b"", "seq": 0xffffffff}],
             "vout": [{"value": value - fee, "script": out_lock}],
             "locktime": 0}
        t["vin"][0]["script"] = sign_pkh_input(t, 0, in_lock, priv)
        return ser_tx(t)

    def _submit(self, txs, height):
        import chainstate
        blk = {"version": 1, "prev": self.cs.index[self.cs._tip_hash]["hash"],
               "merkle": merkle_root([txid(t) for t in txs]),
               "time": self.genesis["time"] + 60 * height,
               "bits": self.genesis["bits"], "nonce": height, "txs": txs}
        with patch.object(chainstate, "validate_block", return_value=None):
            res = self.cs.submit_block(blk)
        self.assertTrue(res["accepted"], res)
        return blk

    def test_block_fees_from_historical_prevouts_match_consensus(self):
        cb1 = self._coinbase(subsidy(1), self.lock_a)
        self._submit([cb1], 1)
        spend1 = self._spend(txid_internal(cb1), 0, subsidy(1),
                             self.lock_a, 1, self.lock_b, fee=1000)
        cb2 = self._coinbase(subsidy(2), self.lock_b)
        self._submit([cb2, spend1], 2)
        spend2 = self._spend(txid_internal(spend1), 0, subsidy(1) - 1000,
                             self.lock_b, 2, self.lock_c, fee=1500)
        cb3 = self._coinbase(subsidy(3), self.lock_c)
        self._submit([cb3, spend2], 3)
        self.assertEqual(self.cs.tip()["height"], 3)
        app = ExcalRosetta(self.cs, network="testnet")
        net = {"network_identifier": {"blockchain": "excal",
                                      "network": "testnet"}}
        # Block 1 is coinbase-only: fee zero.
        status, body = app.handle("/block", dict(
            net, block_identifier={"index": 1}))
        self.assertEqual(status, 200, body)
        self.assertEqual(
            body["block"]["transactions"][0]["metadata"]["fee"], "0")
        # Block 2's spend: fee from block 1's coinbase prevout.
        status, body = app.handle("/block", dict(
            net, block_identifier={"index": 2}))
        self.assertEqual(status, 200, body)
        spend_tx = [t for t in body["block"]["transactions"]
                    if t["transaction_identifier"]["hash"]
                    == txid_internal(spend1)[::-1].hex()][0]
        self.assertEqual(spend_tx["metadata"]["fee"], "1000")
        self.assertEqual(spend_tx["operations"][0]["amount"]["value"],
                         "-" + str(subsidy(1)))
        # Block 3's spend: fee from block 2's non-coinbase prevout.
        status, body = app.handle("/block", dict(
            net, block_identifier={"index": 3}))
        self.assertEqual(status, 200, body)
        spend_tx = [t for t in body["block"]["transactions"]
                    if t["transaction_identifier"]["hash"]
                    == txid_internal(spend2)[::-1].hex()][0]
        self.assertEqual(spend_tx["metadata"]["fee"], "1500")
        # Same bytes through real consensus at a mature height: the
        # fees must agree exactly with what Rosetta rendered.
        ok, reason, fee = validate_tx(
            spend1, {(txid_internal(cb1), 0):
                     [(subsidy(1), self.lock_a, True, 1)]},
            102, spent_pairs=set(), network="testnet")
        self.assertTrue(ok, reason)
        self.assertEqual(fee, 1000)
        ok, reason, fee = validate_tx(
            spend2, {(txid_internal(spend1), 0):
                     [(subsidy(1) - 1000, self.lock_b, False, 2)]},
            102, spent_pairs=set(), network="testnet")
        self.assertTrue(ok, reason)
        self.assertEqual(fee, 1500)
        # Balances follow the spends: at height 3 LOCK_B holds only the
        # block-2 coinbase (spend2 consumed spend1's LOCK_B output, not
        # the coinbase), and LOCK_A is empty (its only output was spent
        # in block 2). At height 2 LOCK_B held the coinbase plus the
        # spend1 output.
        status, body = app.handle("/account/balance", dict(
            net, account_identifier={"address": "lock:" + self.lock_b.hex()},
            block_identifier={"index": 3}))
        self.assertEqual(status, 200, body)
        self.assertEqual(body["balances"][0]["value"], str(subsidy(2)))
        status, body = app.handle("/account/balance", dict(
            net, account_identifier={"address": "lock:" + self.lock_a.hex()},
            block_identifier={"index": 3}))
        self.assertEqual(status, 200, body)
        self.assertEqual(body["balances"][0]["value"], "0")
        status, body = app.handle("/account/balance", dict(
            net, account_identifier={"address": "lock:" + self.lock_b.hex()},
            block_identifier={"index": 2}))
        self.assertEqual(status, 200, body)
        self.assertEqual(body["balances"][0]["value"],
                         str(subsidy(1) - 1000 + subsidy(2)))


if __name__ == "__main__":
    unittest.main()
