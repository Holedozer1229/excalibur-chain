"""Lock/witness-vector, activation-gate, maturity, timeout, replay and
fee tests for the EXCAL Rosetta / consensus implementation (Stage 3).

Every test runs the real implementation (txscript.validate_tx,
validate_block_txs, rosetta/construction.py, rosetta/knot_signer.py,
rosetta/trifold_signer.py, mempool.Mempool) — no mocks of consensus,
signing or validation. Trifold keys use height 2 (9 leaves, ~0.1s to
build); every test gets fresh keys and a fresh spent-leaf registry in a
temp dir so no test touches the live chain-data registry
(~/workspace/spent_leaves.jsonl) or the real fork chain.

KNOT note: the task brief says KNOT is "staged only, activation
proposed at 100000, NOT activated". The code under test says otherwise:
genesis_fork.py sets KNOT_ACTIVATION = 44520 with an "ACTIVATED
2026-11-16" comment (commit d1c72cd0), and self-serve/vendor/
genesis_fork.py still carries 100000. These tests assert the CODE's
behaviour (valid at/above 44520, rejected below) and do NOT change the
activation value — reconciling 44520 vs 100000 is a Lux decision, left
open in the Stage 3 report.
"""
import hashlib
import os
import struct
import tempfile
import unittest
from types import SimpleNamespace

import genesis_fork
import secp256k1 as secp
from genesis_fork import (HTLC_ACTIVATION, QHTLC_ACTIVATION,
                          BRIDGE_ACTIVATION, KNOT_ACTIVATION,
                          QDAY_ACTIVATION, subsidy)
from mempool import Mempool
from rosetta.construction import Construction
from rosetta.knot_signer import build_knot_signature
from rosetta.trifold_signer import ExcalTrifoldRosettaSigner
from spent_leaf_registry import SpentLeafRegistry
from trifold_lockbox import TrifoldKey
from txpq import sign_pqh_input
from txscript import (
    COINBASE_MATURITY, fusion_pqh_lock, htlc_descriptor,
    knot_lock_for_secret, lock_bridge, lock_bridge_for_pubkey,
    lock_htlc_for_descriptor, lock_knot_for_descriptor, lock_open,
    lock_pkh, lock_pkh_for_pubkey, lock_pqh_for_root, lock_qhtlc,
    lock_qhtlc_for_descriptor, lock_type, make_coinbase_v2, parse_tx,
    parse_qhtlc_witness, qhtlc_descriptor, ser_tx, sighash_all,
    sign_bridge_input, sign_htlc_claim, sign_htlc_refund, sign_input,
    sign_knot_input, sign_pkh_input, sign_qhtlc_claim, sign_qhtlc_refund,
    txid_internal, validate_block_txs, validate_tx)

# Height where every lock is active on every network (qlock 102, qday
# 25212, htlc 36010, qhtlc 40040, bridge 39200, knot 44520).
H_ALL = 46000
# KNOT fixture: small descriptor (N=1) so the fixed-point knot math is fast.
KNOT_P, KNOT_Q, KNOT_N, KNOT_EPS = 2, 3, 1, 2 ** 31
KNOT_TSTAR = 12345678901234567890123456789012345678


def pub(priv):
    return secp.compress(secp.priv_to_pub(priv))


def _tx(vins, vouts):
    return {"version": 1, "vin": vins, "vout": vouts, "locktime": 0}


def _vin(prev, idx, script=b""):
    return {"prev": prev, "idx": idx, "script": script, "seq": 0xffffffff}


def _utxo(txid, idx, value, lock, cb=False, cbh=0):
    return {(txid, idx): [(value, lock, cb, cbh)]}


def _fund(n):
    """Distinct fake funding outpoint per test."""
    return bytes([n]) * 32


class WitnessVectorTests(unittest.TestCase):
    def setUp(self):
        genesis_fork.use_network("testnet")
        self.addCleanup(genesis_fork.use_network, "testnet")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.reg = SpentLeafRegistry(os.path.join(self.tmp.name, "reg.json"))
        self._key_n = 0

    def _trifold(self, seed_byte):
        self._key_n += 1
        return TrifoldKey(bytes([seed_byte]) * 32, height=2,
                          state_path=os.path.join(
                              self.tmp.name, f"key{self._key_n}.json"))

    def _pkh_spend(self, fund, priv, value=10000, out_value=9000,
                   out_lock=None, height=H_ALL, network="fork"):
        """Signed PKH spend; returns (raw, utxo)."""
        lock = lock_pkh_for_pubkey(pub(priv))
        t = _tx([_vin(fund, 0)],
                [{"value": out_value,
                  "script": out_lock if out_lock is not None
                  else lock_pkh_for_pubkey(pub(priv + 100))}])
        t["vin"][0]["script"] = sign_pkh_input(t, 0, lock, priv)
        return ser_tx(t), _utxo(fund, 0, value, lock)

    def test_pkh_spend_valid_compressed_and_uncompressed(self):
        # Compressed and uncompressed are DIFFERENT PKH locks: the lock
        # commits to hash160 of the presented form. The uncompressed
        # case therefore funds a lock built from the uncompressed pubkey
        # (this form-split is exactly what the bridge lock fixes).
        for compressed in (True, False):
            fund = _fund(0xA1 if compressed else 0xA2)
            pt = secp.priv_to_pub(1)
            if compressed:
                lock_pub = pub(1)
            else:
                lock_pub = (b"\x04" + pt[0].to_bytes(32, "big")
                            + pt[1].to_bytes(32, "big"))
            from txscript import hash160
            lock = lock_pkh(hash160(lock_pub))
            t = _tx([_vin(fund, 0)],
                    [{"value": 9000, "script": lock_pkh_for_pubkey(pub(2))}])
            t["vin"][0]["script"] = sign_pkh_input(
                t, 0, lock, 1, compressed=compressed)
            ok, reason, fee = validate_tx(
                ser_tx(t), _utxo(fund, 0, 10000, lock), H_ALL,
                spent_pairs=set(), network="fork")
            self.assertTrue(ok, reason)
            self.assertEqual(fee, 1000)

    def test_open_spend_valid_and_nonempty_scriptsig_rejected(self):
        fund = _fund(0xA3)
        t = _tx([_vin(fund, 0)],
                [{"value": 9000, "script": lock_pkh_for_pubkey(pub(2))}])
        ok, reason, fee = validate_tx(
            ser_tx(t), _utxo(fund, 0, 10000, lock_open()), H_ALL,
            spent_pairs=set(), network="fork")
        self.assertTrue(ok, reason)
        self.assertEqual(fee, 1000)
        t["vin"][0]["script"] = b"\x01\x02"
        ok, reason, _ = validate_tx(
            ser_tx(t), _utxo(fund, 0, 10000, lock_open()), H_ALL,
            spent_pairs=set(), network="fork")
        self.assertFalse(ok)
        self.assertIn("anyone-spend takes empty scriptSig", reason)

    def test_pqh_spend_valid(self):
        key = self._trifold(0x07)
        lock = lock_pqh_for_root(key.root)
        fund = _fund(0xA4)
        t = _tx([_vin(fund, 0)],
                [{"value": 9000, "script": lock_pkh_for_pubkey(pub(2))}])
        wit = sign_pqh_input(key, sighash_all(t, 0, lock), registry=self.reg)
        t["vin"][0]["script"] = wit
        ok, reason, fee = validate_tx(
            ser_tx(t), _utxo(fund, 0, 10000, lock), H_ALL,
            spent_pairs=set(), network="fork")
        self.assertTrue(ok, reason)
        self.assertEqual(fee, 1000)

    def test_pqh_spend_wrong_root_rejected(self):
        key = self._trifold(0x07)
        lock = lock_pqh_for_root(key.root)
        wrong_lock = lock_pqh_for_root(b"\x99" * 32)
        fund = _fund(0xA5)
        t = _tx([_vin(fund, 0)],
                [{"value": 9000, "script": lock_pkh_for_pubkey(pub(2))}])
        wit = sign_pqh_input(key, sighash_all(t, 0, lock), registry=self.reg)
        t["vin"][0]["script"] = wit
        ok, reason, _ = validate_tx(
            ser_tx(t), _utxo(fund, 0, 10000, wrong_lock), H_ALL,
            spent_pairs=set(), network="fork")
        self.assertFalse(ok)
        self.assertIn("PQH root does not match lock", reason)

    def test_pkh_spend_bad_signature_rejected(self):
        fund = _fund(0xA6)
        lock = lock_pkh_for_pubkey(pub(1))
        t = _tx([_vin(fund, 0)],
                [{"value": 9000, "script": lock_pkh_for_pubkey(pub(2))}])
        # Sign with the wrong key: the pubkey still matches the lock
        # only if we present priv 1's key — so sign with priv 2 but
        # present priv 1's pubkey by hand: build the witness manually.
        h = sighash_all(t, 0, lock)
        sig = secp.sign(2, h)
        t["vin"][0]["script"] = pub(1) + sig + bytes([1])
        ok, reason, _ = validate_tx(
            ser_tx(t), _utxo(fund, 0, 10000, lock), H_ALL,
            spent_pairs=set(), network="fork")
        self.assertFalse(ok)
        self.assertIn("bad PKH signature", reason)

    def test_htlc_claim_and_refund_valid(self):
        secret = bytes(range(32))
        desc = htlc_descriptor(hashlib.sha256(secret).digest(), pub(8),
                               pub(9), 46100)
        lock = lock_htlc_for_descriptor(desc)
        fund = _fund(0xA7)
        t = _tx([_vin(fund, 0)],
                [{"value": 9000, "script": lock_pkh_for_pubkey(pub(10))}])
        t["vin"][0]["script"] = sign_htlc_claim(t, 0, lock, 8, secret, desc)
        ok, reason, fee = validate_tx(
            ser_tx(t), _utxo(fund, 0, 10000, lock), H_ALL,
            spent_pairs=set(), network="fork")
        self.assertTrue(ok, reason)
        self.assertEqual(fee, 1000)
        # Claim works before the timeout too (only refund is gated).
        t2 = _tx([_vin(fund, 0)],
                 [{"value": 9000, "script": lock_pkh_for_pubkey(pub(10))}])
        t2["vin"][0]["script"] = sign_htlc_claim(t2, 0, lock, 8, secret, desc)
        ok, reason, _ = validate_tx(
            ser_tx(t2), _utxo(fund, 0, 10000, lock), 46099,
            spent_pairs=set(), network="fork")
        self.assertTrue(ok, reason)
        t3 = _tx([_vin(fund, 0)],
                 [{"value": 9000, "script": lock_pkh_for_pubkey(pub(10))}])
        t3["vin"][0]["script"] = sign_htlc_refund(t3, 0, lock, 9, desc)
        ok, reason, _ = validate_tx(
            ser_tx(t3), _utxo(fund, 0, 10000, lock), 46100,
            spent_pairs=set(), network="fork")
        self.assertTrue(ok, reason)

    def test_htlc_refund_before_timeout_and_wrong_secret_rejected(self):
        secret = bytes([7]) * 32
        desc = htlc_descriptor(hashlib.sha256(secret).digest(), pub(8),
                               pub(9), 46100)
        lock = lock_htlc_for_descriptor(desc)
        fund = _fund(0xA8)
        t = _tx([_vin(fund, 0)],
                [{"value": 9000, "script": lock_pkh_for_pubkey(pub(10))}])
        t["vin"][0]["script"] = sign_htlc_refund(t, 0, lock, 9, desc)
        ok, reason, _ = validate_tx(
            ser_tx(t), _utxo(fund, 0, 10000, lock), 46099,
            spent_pairs=set(), network="fork")
        self.assertFalse(ok)
        self.assertIn("HTLC refund before timeout", reason)
        # Wrong secret: same-length tamper inside the claim witness.
        t2 = _tx([_vin(fund, 0)],
                 [{"value": 9000, "script": lock_pkh_for_pubkey(pub(10))}])
        wit = bytearray(sign_htlc_claim(t2, 0, lock, 8, secret, desc))
        wit[99:131] = b"\x00" * 32
        t2["vin"][0]["script"] = bytes(wit)
        ok, reason, _ = validate_tx(
            ser_tx(t2), _utxo(fund, 0, 10000, lock), H_ALL,
            spent_pairs=set(), network="fork")
        self.assertFalse(ok)
        self.assertIn("HTLC secret mismatch", reason)
        # Refund attempted with the claim key.
        t3 = _tx([_vin(fund, 0)],
                 [{"value": 9000, "script": lock_pkh_for_pubkey(pub(10))}])
        wit3 = bytearray(sign_htlc_refund(t3, 0, lock, 9, desc))
        wit3[1:34] = pub(8)  # swap in the claim pubkey, keep refund sig
        t3["vin"][0]["script"] = bytes(wit3)
        ok, reason, _ = validate_tx(
            ser_tx(t3), _utxo(fund, 0, 10000, lock), 46100,
            spent_pairs=set(), network="fork")
        self.assertFalse(ok)
        self.assertIn("HTLC refund key mismatch", reason)

    def test_qhtlc_claim_and_refund_valid(self):
        claim_key = self._trifold(0x11)
        refund_key = self._trifold(0x22)
        secret = bytes(range(32))
        desc = qhtlc_descriptor(hashlib.sha256(secret).digest(),
                                claim_key.root, refund_key.root, 46100)
        lock = lock_qhtlc_for_descriptor(desc)
        fund = _fund(0xA9)
        t = _tx([_vin(fund, 0)],
                [{"value": 9000, "script": lock_pkh_for_pubkey(pub(3))}])
        t["vin"][0]["script"] = sign_qhtlc_claim(
            t, 0, lock, claim_key, secret, desc, registry=self.reg)
        ok, reason, fee = validate_tx(
            ser_tx(t), _utxo(fund, 0, 10000, lock), H_ALL,
            spent_pairs=set(), network="fork")
        self.assertTrue(ok, reason)
        self.assertEqual(fee, 1000)
        t2 = _tx([_vin(fund, 0)],
                 [{"value": 9000, "script": lock_pkh_for_pubkey(pub(3))}])
        t2["vin"][0]["script"] = sign_qhtlc_refund(
            t2, 0, lock, refund_key, desc, registry=self.reg)
        ok, reason, _ = validate_tx(
            ser_tx(t2), _utxo(fund, 0, 10000, lock), 46100,
            spent_pairs=set(), network="fork")
        self.assertTrue(ok, reason)

    def test_qhtlc_refund_before_timeout_and_same_root_rejected(self):
        claim_key = self._trifold(0x11)
        refund_key = self._trifold(0x22)
        secret = bytes(range(32))
        desc = qhtlc_descriptor(hashlib.sha256(secret).digest(),
                                claim_key.root, refund_key.root, 46100)
        lock = lock_qhtlc_for_descriptor(desc)
        fund = _fund(0xAA)
        t = _tx([_vin(fund, 0)],
                [{"value": 9000, "script": lock_pkh_for_pubkey(pub(3))}])
        t["vin"][0]["script"] = sign_qhtlc_refund(
            t, 0, lock, refund_key, desc, registry=self.reg)
        ok, reason, _ = validate_tx(
            ser_tx(t), _utxo(fund, 0, 10000, lock), 46099,
            spent_pairs=set(), network="fork")
        self.assertFalse(ok)
        self.assertIn("QHTLC refund before timeout", reason)
        # Wrong secret: tamper the secret bytes inside the claim witness.
        t2 = _tx([_vin(fund, 0)],
                 [{"value": 9000, "script": lock_pkh_for_pubkey(pub(3))}])
        wit = bytearray(sign_qhtlc_claim(
            t2, 0, lock, claim_key, secret, desc, registry=self.reg))
        # Claim witness: mode | trifold-wit | secret(32) | desc(100).
        wit[-132:-100] = b"\x00" * 32
        t2["vin"][0]["script"] = bytes(wit)
        ok, reason, _ = validate_tx(
            ser_tx(t2), _utxo(fund, 0, 10000, lock), H_ALL,
            spent_pairs=set(), network="fork")
        self.assertFalse(ok)
        self.assertIn("QHTLC secret mismatch", reason)
        # Same-root descriptor is a self-lock, not a swap.
        same = qhtlc_descriptor(hashlib.sha256(secret).digest(),
                                claim_key.root, claim_key.root, 46100)
        same_lock = lock_qhtlc_for_descriptor(same)
        fund2 = _fund(0xAB)
        t3 = _tx([_vin(fund2, 0)],
                 [{"value": 9000, "script": lock_pkh_for_pubkey(pub(3))}])
        t3["vin"][0]["script"] = sign_qhtlc_claim(
            t3, 0, same_lock, claim_key, secret, same, registry=self.reg)
        ok, reason, _ = validate_tx(
            ser_tx(t3), _utxo(fund2, 0, 10000, same_lock), H_ALL,
            spent_pairs=set(), network="fork")
        self.assertFalse(ok)
        self.assertIn("claim and refund roots must differ", reason)

    def test_bridge_spend_valid_both_presentations(self):
        # One lock, two presentations of the same key: compressed and
        # uncompressed witnesses must both pass (the form-split fix).
        lock = lock_bridge_for_pubkey(pub(5))
        self.assertEqual(lock, lock_bridge(pub(5)[1:]))
        for compressed in (True, False):
            fund = _fund(0xAC if compressed else 0xAD)
            t = _tx([_vin(fund, 0)],
                    [{"value": 9000, "script": lock_pkh_for_pubkey(pub(6))}])
            t["vin"][0]["script"] = sign_bridge_input(
                t, 0, lock, 5, compressed=compressed)
            ok, reason, fee = validate_tx(
                ser_tx(t), _utxo(fund, 0, 10000, lock), H_ALL,
                spent_pairs=set(), network="fork")
            self.assertTrue(ok, reason)
            self.assertEqual(fee, 1000)

    def test_bridge_wrong_key_rejected_at_validation(self):
        lock = lock_bridge_for_pubkey(pub(5))
        fund = _fund(0xAF)
        t = _tx([_vin(fund, 0)],
                [{"value": 9000, "script": lock_pkh_for_pubkey(pub(6))}])
        # Hand-build a witness for key 6 against key 5's lock.
        h = sighash_all(t, 0, lock)
        sig = secp.sign(6, h)
        t["vin"][0]["script"] = pub(6) + sig + bytes([1])
        ok, reason, _ = validate_tx(
            ser_tx(t), _utxo(fund, 0, 10000, lock), H_ALL,
            spent_pairs=set(), network="fork")
        self.assertFalse(ok)
        self.assertIn("pubkey x does not match bridge lock", reason)

    def test_knot_spend_valid_and_wrong_t_star_rejected(self):
        lock, desc, _ = knot_lock_for_secret(
            KNOT_P, KNOT_Q, KNOT_N, KNOT_EPS, KNOT_TSTAR)
        fund = _fund(0xB0)
        t = _tx([_vin(fund, 0)],
                [{"value": 9000, "script": lock_pkh_for_pubkey(pub(4))}])
        t["vin"][0]["script"] = sign_knot_input(t, 0, lock, KNOT_TSTAR, desc)
        ok, reason, fee = validate_tx(
            ser_tx(t), _utxo(fund, 0, 10000, lock), H_ALL,
            spent_pairs=set(), network="fork")
        self.assertTrue(ok, reason)
        self.assertEqual(fee, 1000)
        # Tamper t_star: the recomputed knot point no longer matches.
        t2 = _tx([_vin(fund, 0)],
                 [{"value": 9000, "script": lock_pkh_for_pubkey(pub(4))}])
        wit = bytearray(sign_knot_input(t2, 0, lock, KNOT_TSTAR, desc))
        wit[0] ^= 0x01
        t2["vin"][0]["script"] = bytes(wit)
        ok, reason, _ = validate_tx(
            ser_tx(t2), _utxo(fund, 0, 10000, lock), H_ALL,
            spent_pairs=set(), network="fork")
        self.assertFalse(ok)
        self.assertIn("KNOT point mismatch", reason)

    def test_p2pk_grandfathered_spend_valid(self):
        # Legacy P2PK inputs stay spendable after Q-Lock activation.
        fund = _fund(0xB1)
        lock = b"\x21" + pub(1) + b"\xac"
        self.assertEqual(lock_type(lock), "p2pk")
        t = _tx([_vin(fund, 0)],
                [{"value": 9000, "script": lock_pkh_for_pubkey(pub(2))}])
        t["vin"][0]["script"] = sign_input(t, 0, lock, 1)
        ok, reason, fee = validate_tx(
            ser_tx(t), _utxo(fund, 0, 10000, lock), H_ALL,
            spent_pairs=set(), network="fork")
        self.assertTrue(ok, reason)
        self.assertEqual(fee, 1000)

    def test_dust_output_and_overspend_rejected(self):
        fund = _fund(0xB2)
        lock = lock_pkh_for_pubkey(pub(1))
        t = _tx([_vin(fund, 0)],
                [{"value": 100, "script": lock_pkh_for_pubkey(pub(2))}])
        t["vin"][0]["script"] = sign_pkh_input(t, 0, lock, 1)
        ok, reason, _ = validate_tx(
            ser_tx(t), _utxo(fund, 0, 10000, lock), H_ALL,
            spent_pairs=set(), network="fork")
        self.assertFalse(ok)
        self.assertIn("dust", reason)
        t2 = _tx([_vin(fund, 0)],
                 [{"value": 11000, "script": lock_pkh_for_pubkey(pub(2))}])
        t2["vin"][0]["script"] = sign_pkh_input(t2, 0, lock, 1)
        ok, reason, _ = validate_tx(
            ser_tx(t2), _utxo(fund, 0, 10000, lock), H_ALL,
            spent_pairs=set(), network="fork")
        self.assertFalse(ok)
        self.assertIn("outputs exceed inputs", reason)

    def test_duplicate_input_rejected(self):
        fund = _fund(0xB3)
        lock = lock_pkh_for_pubkey(pub(1))
        t = _tx([_vin(fund, 0), _vin(fund, 0)],
                [{"value": 9000, "script": lock_pkh_for_pubkey(pub(2))}])
        t["vin"][0]["script"] = sign_pkh_input(t, 0, lock, 1)
        t["vin"][1]["script"] = sign_pkh_input(t, 1, lock, 1)
        ok, reason, _ = validate_tx(
            ser_tx(t), _utxo(fund, 0, 10000, lock), H_ALL,
            spent_pairs=set(), network="fork")
        self.assertFalse(ok)
        self.assertIn("duplicate input", reason)


class ActivationGateTests(unittest.TestCase):
    """Boundary tests: every lock is non-standard the block before its
    activation height and valid at it. Funding is a grandfathered P2PK
    UTXO (spendable at every height on every network)."""

    def setUp(self):
        genesis_fork.use_network("testnet")
        self.addCleanup(genesis_fork.use_network, "testnet")

    def _create_output_tx(self, out_lock, height, network):
        fund = _fund(0xC0)
        p2pk = b"\x21" + pub(1) + b"\xac"
        t = _tx([_vin(fund, 0)],
                [{"value": 9000, "script": out_lock}])
        t["vin"][0]["script"] = sign_input(t, 0, p2pk, 1)
        return validate_tx(ser_tx(t), _utxo(fund, 0, 10000, p2pk),
                           height, spent_pairs=set(), network=network)

    def test_pkh_output_boundary_mainnet_102(self):
        lock = lock_pkh_for_pubkey(pub(2))
        ok, reason, _ = self._create_output_tx(lock, 101, "mainnet")
        self.assertFalse(ok, "PKH output must be non-standard pre-qlock")
        self.assertIn("non-standard scriptPubKey", reason)
        ok, reason, _ = self._create_output_tx(lock, 102, "mainnet")
        self.assertTrue(ok, reason)

    def test_pqh_output_boundary_25212(self):
        lock = lock_pqh_for_root(b"\x33" * 32)
        ok, reason, _ = self._create_output_tx(lock, QDAY_ACTIVATION - 1,
                                               "fork")
        self.assertFalse(ok)
        self.assertIn("non-standard scriptPubKey", reason)
        ok, reason, _ = self._create_output_tx(lock, QDAY_ACTIVATION, "fork")
        self.assertTrue(ok, reason)

    def test_htlc_output_boundary_36010(self):
        lock = lock_htlc_for_descriptor(htlc_descriptor(
            b"\x44" * 32, pub(8), pub(9), 99999))
        ok, reason, _ = self._create_output_tx(lock, HTLC_ACTIVATION - 1,
                                               "fork")
        self.assertFalse(ok)
        self.assertIn("non-standard scriptPubKey", reason)
        ok, reason, _ = self._create_output_tx(lock, HTLC_ACTIVATION, "fork")
        self.assertTrue(ok, reason)

    def test_qhtlc_output_boundary_40040(self):
        lock = lock_qhtlc_for_descriptor(qhtlc_descriptor(
            b"\x44" * 32, b"\x55" * 32, b"\x66" * 32, 99999))
        ok, reason, _ = self._create_output_tx(lock, QHTLC_ACTIVATION - 1,
                                               "fork")
        self.assertFalse(ok)
        self.assertIn("non-standard scriptPubKey", reason)
        ok, reason, _ = self._create_output_tx(lock, QHTLC_ACTIVATION,
                                               "fork")
        self.assertTrue(ok, reason)

    def test_bridge_output_boundary_39200(self):
        lock = lock_bridge(pub(1)[1:])
        ok, reason, _ = self._create_output_tx(lock, BRIDGE_ACTIVATION - 1,
                                               "fork")
        self.assertFalse(ok)
        self.assertIn("non-standard scriptPubKey", reason)
        ok, reason, _ = self._create_output_tx(lock, BRIDGE_ACTIVATION,
                                               "fork")
        self.assertTrue(ok, reason)

    def test_knot_output_boundary_44520(self):
        # Asserts the CODE's activation (44520), not the 100000 proposal
        # in the task brief — see module docstring.
        lock, _, _ = knot_lock_for_secret(
            KNOT_P, KNOT_Q, KNOT_N, KNOT_EPS, KNOT_TSTAR)
        ok, reason, _ = self._create_output_tx(lock, KNOT_ACTIVATION - 1,
                                               "fork")
        self.assertFalse(ok)
        self.assertIn("non-standard scriptPubKey", reason)
        ok, reason, _ = self._create_output_tx(lock, KNOT_ACTIVATION, "fork")
        self.assertTrue(ok, reason)

    def test_legacy_p2pk_output_retired_after_qlock_but_spend_survives(self):
        p2pk = b"\x21" + pub(2) + b"\xac"
        # Pre-activation mainnet: creating a P2PK output is still legal.
        ok, reason, _ = self._create_output_tx(p2pk, 50, "mainnet")
        self.assertTrue(ok, reason)
        # Post-activation mainnet: creating one is retired.
        ok, reason, _ = self._create_output_tx(p2pk, 200, "mainnet")
        self.assertFalse(ok)
        self.assertIn("legacy lock retired", reason)
        # But spending an existing P2PK UTXO still works post-activation.
        fund = _fund(0xC1)
        t = _tx([_vin(fund, 0)],
                [{"value": 9000, "script": lock_pkh_for_pubkey(pub(2))}])
        t["vin"][0]["script"] = sign_input(t, 0, p2pk, 2)
        ok, reason, _ = validate_tx(
            ser_tx(t), _utxo(fund, 0, 10000, p2pk), 200,
            spent_pairs=set(), network="mainnet")
        self.assertTrue(ok, reason)


class NetworkIsolationTests(unittest.TestCase):
    """Regression: validate_tx must not follow the process-global network
    selection (the known Stage-3 open item: validate_tx and knot_signer
    read process-global activations). With the global flipped to "fork"
    (qlock 0), a mainnet validation at height 50 must still retire
    legacy outputs and reject PKH creation."""

    def setUp(self):
        genesis_fork.use_network("fork")
        self.addCleanup(genesis_fork.use_network, "testnet")
        self.assertEqual(genesis_fork.qlock_activation(), 0)

    def _create_output_tx(self, out_lock, height, network):
        fund = _fund(0xC2)
        p2pk = b"\x21" + pub(1) + b"\xac"
        t = _tx([_vin(fund, 0)],
                [{"value": 9000, "script": out_lock}])
        t["vin"][0]["script"] = sign_input(t, 0, p2pk, 1)
        return validate_tx(ser_tx(t), _utxo(fund, 0, 10000, p2pk),
                           height, spent_pairs=set(), network=network)

    def test_validate_tx_network_param_ignores_flipped_global(self):
        pkh = lock_pkh_for_pubkey(pub(2))
        ok, _, _ = self._create_output_tx(pkh, 50, "fork")
        self.assertTrue(ok, "fork qlock is 0: PKH valid at height 50")
        ok, reason, _ = self._create_output_tx(pkh, 50, "mainnet")
        self.assertFalse(ok, "mainnet qlock is 102: PKH invalid at 50")
        self.assertIn("non-standard scriptPubKey", reason)
        ok, reason, _ = self._create_output_tx(pkh, 50, "testnet")
        self.assertFalse(ok)
        # Legacy behaviour preserved: no network -> process-global (fork).
        ok, _, _ = self._create_output_tx(pkh, 50, None)
        self.assertTrue(ok)

    def test_cross_network_replay_fails_both_directions(self):
        # Same raw bytes: a PKH-creating tx valid on fork at height 50
        # is invalid on mainnet (PKH not yet active there).
        pkh = lock_pkh_for_pubkey(pub(2))
        fund = _fund(0xC3)
        p2pk = b"\x21" + pub(1) + b"\xac"
        t = _tx([_vin(fund, 0)], [{"value": 9000, "script": pkh}])
        t["vin"][0]["script"] = sign_input(t, 0, p2pk, 1)
        raw = ser_tx(t)
        utxo = _utxo(fund, 0, 10000, p2pk)
        ok, _, _ = validate_tx(raw, utxo, 50, spent_pairs=set(),
                               network="fork")
        self.assertTrue(ok)
        ok, reason, _ = validate_tx(raw, utxo, 50, spent_pairs=set(),
                                    network="mainnet")
        self.assertFalse(ok)
        self.assertIn("non-standard scriptPubKey", reason)
        # Reverse: a legacy P2PK-creating tx valid on mainnet at height
        # 50 is invalid on fork (legacy outputs retired from height 0).
        t2 = _tx([_vin(fund, 0)],
                 [{"value": 9000, "script": b"\x21" + pub(2) + b"\xac"}])
        t2["vin"][0]["script"] = sign_input(t2, 0, p2pk, 1)
        raw2 = ser_tx(t2)
        ok, _, _ = validate_tx(raw2, utxo, 50, spent_pairs=set(),
                               network="mainnet")
        self.assertTrue(ok)
        ok, reason, _ = validate_tx(raw2, utxo, 50, spent_pairs=set(),
                                    network="fork")
        self.assertFalse(ok)
        self.assertIn("legacy lock retired", reason)

    def test_knot_signer_network_param_ignores_flipped_global(self):
        lock, desc, _ = knot_lock_for_secret(
            KNOT_P, KNOT_Q, KNOT_N, KNOT_EPS, KNOT_TSTAR)
        fund = _fund(0xC4)
        t = _tx([_vin(fund, 0)],
                [{"value": 9000, "script": lock_pkh_for_pubkey(pub(4))}])
        unsigned = ser_tx(t).hex()
        # Below activation on either network (both share 44520 today).
        with self.assertRaisesRegex(Exception, "not activated"):
            build_knot_signature(unsigned, 0, lock.hex(),
                                 KNOT_TSTAR.to_bytes(16, "big").hex(),
                                 desc.hex(), KNOT_ACTIVATION - 1,
                                 network="mainnet")
        result = build_knot_signature(
            unsigned, 0, lock.hex(),
            KNOT_TSTAR.to_bytes(16, "big").hex(), desc.hex(),
            KNOT_ACTIVATION, network="mainnet")
        self.assertEqual(result["signature_type"], "excal_knot")
        self.assertEqual(len(bytes.fromhex(result["hex_bytes"])), 56)


class CoinbaseMaturityTests(unittest.TestCase):
    def setUp(self):
        genesis_fork.use_network("testnet")
        self.addCleanup(genesis_fork.use_network, "testnet")

    def _spend_coinbase(self, cb_height, spend_height):
        fund = _fund(0xD0)
        lock = lock_pkh_for_pubkey(pub(1))
        t = _tx([_vin(fund, 0)],
                [{"value": 9000, "script": lock_pkh_for_pubkey(pub(2))}])
        t["vin"][0]["script"] = sign_pkh_input(t, 0, lock, 1)
        return validate_tx(ser_tx(t),
                           _utxo(fund, 0, 10000, lock, cb=True, cbh=cb_height),
                           spend_height, spent_pairs=set(), network="fork")

    def test_coinbase_spend_matures_at_exactly_100_blocks(self):
        ok, reason, _ = self._spend_coinbase(1000, 1099)
        self.assertFalse(ok)
        self.assertIn("coinbase immature", reason)
        ok, reason, fee = self._spend_coinbase(1000, 1100)
        self.assertTrue(ok, reason)
        self.assertEqual(fee, 1000)

    def test_construction_metadata_rejects_immature_tip_coinbase(self):
        # Mirrors the live server behaviour: /construction/metadata
        # refuses a tip coinbase as an input until it matures.
        prev = bytes.fromhex("dd" * 32)
        coin = prev[::-1].hex() + ":0"
        lock = lock_pkh_for_pubkey(pub(1))
        out_lock = lock_pkh_for_pubkey(pub(2))
        cs = SimpleNamespace(
            utxo={(prev, 0): [(10000, lock, True, 50000)]},
            tip=lambda: {"height": 50000, "hash": bytes(32)})
        builder = Construction(cs, network="fork")
        body = {"options": {
            "inputs": [{"coin": coin, "value": 10000, "lock": lock.hex()}],
            "outputs": [{"value": 9000, "lock": out_lock.hex()}],
            "fee": 1000}}
        with self.assertRaisesRegex(ValueError, "coinbase input immature"):
            builder.handle("/construction/metadata", body)
        # Exactly 100 blocks later the same coinbase is spendable.
        cs.utxo = {(prev, 0): [(10000, lock, True, 49901)]}
        result = builder.handle("/construction/metadata", body)
        self.assertEqual(result["metadata"]["fee"], 1000)
        self.assertEqual(result["metadata"]["network_height"], 50001)


class ConstructionCombineTests(unittest.TestCase):
    """End-to-end Construction flow for PKH and KNOT, proving combine
    enforces the network-aware gates (the validate_tx fix) rather than
    the process-global ones."""

    def setUp(self):
        genesis_fork.use_network("fork")
        self.addCleanup(genesis_fork.use_network, "testnet")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def _builder(self, utxo, tip_height, network="fork"):
        cs = SimpleNamespace(
            utxo=utxo, tip=lambda: {"height": tip_height, "hash": bytes(32)})
        return Construction(cs, network=network), cs

    def _run_flow(self, builder, coin, in_value, in_lock, in_type,
                  out_value, out_lock, out_type, fee):
        opts = builder.handle("/construction/preprocess", {"operations": [
            {"type": "input", "coin_change": {"coin_identifier": {"identifier": coin}},
             "account": {"address": "lock:" + in_lock.hex()},
             "amount": {"value": str(-in_value),
                        "currency": {"symbol": "EXCAL", "decimals": 8}}},
            {"type": "output", "account": {"address": "lock:" + out_lock.hex()},
             "amount": {"value": str(out_value),
                        "currency": {"symbol": "EXCAL", "decimals": 8}}},
            {"type": "fee", "amount": {"value": str(-fee),
                                       "currency": {"symbol": "EXCAL", "decimals": 8}}}]})
        md = builder.handle("/construction/metadata", {"options": opts["options"]})
        payloads = builder.handle("/construction/payloads", {"metadata": md["metadata"]})
        return md, payloads

    def test_pkh_full_flow_combine_returns_fee(self):
        prev = bytes.fromhex("e1" * 32)
        coin = prev[::-1].hex() + ":0"
        lock = lock_pkh_for_pubkey(pub(1))
        out_lock = lock_pkh_for_pubkey(pub(2))
        builder, _ = self._builder(
            {(prev, 0): [(10000, lock, False, 0)]}, 45999)
        md, payloads = self._run_flow(
            builder, coin, 10000, lock, "pkh", 9000, out_lock, "pkh", 1000)
        self.assertEqual(len(payloads["payloads"]), 1)
        self.assertEqual(payloads["payloads"][0]["signature_type"], "ecdsa")
        digest = payloads["payloads"][0]["hex_bytes"]
        sig = secp.sign(1, bytes.fromhex(digest))
        result = builder.handle("/construction/combine", {
            "unsigned_transaction": payloads["unsigned_transaction"],
            "signatures": [{"signing_payload": {"hex_bytes": digest},
                            "signature_type": "ecdsa",
                            "hex_bytes": sig.hex(),
                            "public_key": {"hex_bytes": pub(1).hex()}}]})
        self.assertEqual(result["fee"], "1000")
        raw = bytes.fromhex(result["signed_transaction"])
        ok, reason, fee = validate_tx(
            raw, {(prev, 0): [(10000, lock, False, 0)]}, H_ALL,
            spent_pairs=set(), network="fork")
        self.assertTrue(ok, reason)
        self.assertEqual(fee, 1000)

    def test_knot_combine_rejects_pre_activation_and_accepts_at_activation(self):
        # NOTE: /construction/metadata and /construction/payloads already
        # refuse a KNOT input below activation ("knot not active"), so
        # the pre-activation combine check is reached only with a
        # hand-built unsigned tx that bypasses those endpoints — that is
        # exactly what this test does, proving combine enforces the gate
        # itself (defense in depth) instead of trusting its callers.
        lock, desc, _ = knot_lock_for_secret(
            KNOT_P, KNOT_Q, KNOT_N, KNOT_EPS, KNOT_TSTAR)
        out_lock = lock_pkh_for_pubkey(pub(2))
        prev = bytes.fromhex("e2" * 32)
        coin = prev[::-1].hex() + ":0"

        def _unsigned_and_witness():
            tx = _tx([_vin(prev, 0)],
                     [{"value": 9000, "script": out_lock}])
            wit = sign_knot_input(tx, 0, lock, KNOT_TSTAR, desc)
            return ser_tx(tx).hex(), sighash_all(tx, 0, lock).hex(), wit

        # Below activation: combine must reject via consensus validation.
        builder, _ = self._builder(
            {(prev, 0): [(10000, lock, False, 0)]}, KNOT_ACTIVATION - 2)
        unsigned, digest, wit = _unsigned_and_witness()
        with self.assertRaisesRegex(ValueError, "consensus rejected"):
            builder.handle("/construction/combine", {
                "unsigned_transaction": unsigned,
                "signatures": [{"signing_payload": {"hex_bytes": digest},
                                "signature_type": "excal_knot",
                                "hex_bytes": wit.hex()}]})
        # At activation the identical combine succeeds.
        builder2, _ = self._builder(
            {(prev, 0): [(10000, lock, False, 0)]}, KNOT_ACTIVATION - 1)
        unsigned2, digest2, wit2 = _unsigned_and_witness()
        result = builder2.handle("/construction/combine", {
            "unsigned_transaction": unsigned2,
            "signatures": [{"signing_payload": {"hex_bytes": digest2},
                            "signature_type": "excal_knot",
                            "hex_bytes": wit2.hex()}]})
        self.assertEqual(result["fee"], "1000")

    def test_knot_metadata_refuses_pre_activation_input(self):
        # The gate fires even earlier, at metadata time.
        lock, _, _ = knot_lock_for_secret(
            KNOT_P, KNOT_Q, KNOT_N, KNOT_EPS, KNOT_TSTAR)
        out_lock = lock_pkh_for_pubkey(pub(2))
        prev = bytes.fromhex("e2" * 32)
        coin = prev[::-1].hex() + ":0"
        builder, _ = self._builder(
            {(prev, 0): [(10000, lock, False, 0)]}, KNOT_ACTIVATION - 2)
        with self.assertRaisesRegex(ValueError, "knot not active"):
            builder.handle("/construction/metadata", {"options": {
                "inputs": [{"coin": coin, "value": 10000,
                            "lock": lock.hex()}],
                "outputs": [{"value": 9000, "lock": out_lock.hex()}],
                "fee": 1000}})

    def test_trifold_signer_refuses_early_qhtlc_refund_without_burning_leaf(self):
        refund_key = TrifoldKey(bytes([0x22]) * 32, height=2,
                                state_path=os.path.join(self.tmp.name, "rk.json"))
        claim_key = TrifoldKey(bytes([0x11]) * 32, height=2,
                               state_path=os.path.join(self.tmp.name, "ck.json"))
        reg = SpentLeafRegistry(os.path.join(self.tmp.name, "reg.json"))
        secret = bytes(range(32))
        desc = qhtlc_descriptor(hashlib.sha256(secret).digest(),
                                claim_key.root, refund_key.root, 46100)
        lock = lock_qhtlc_for_descriptor(desc)
        fund = _fund(0xE3)
        t = _tx([_vin(fund, 0)],
                [{"value": 9000, "script": lock_pkh_for_pubkey(pub(3))}])
        unsigned = ser_tx(t).hex()
        wallet = SimpleNamespace(trifold_key=lambda: refund_key)
        signer = ExcalTrifoldRosettaSigner(wallet, registry=reg)
        before = refund_key.next_index
        with self.assertRaisesRegex(Exception, "timeout has not matured"):
            signer.sign_payload(unsigned, 0, lock.hex(),
                                "trifold-qhtlc", mode="refund",
                                descriptor_hex=desc.hex(), spend_height=46099)
        self.assertEqual(refund_key.next_index, before,
                         "early refund must not burn a Trifold leaf")
        result = signer.sign_payload(
            unsigned, 0, lock.hex(), "trifold-qhtlc", mode="refund",
            descriptor_hex=desc.hex(), spend_height=46100)
        self.assertEqual(result["signature_type"], "trifold")
        self.assertEqual(refund_key.next_index, before + 1)


class ReplayProtectionTests(unittest.TestCase):
    def setUp(self):
        genesis_fork.use_network("testnet")
        self.addCleanup(genesis_fork.use_network, "testnet")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.reg = SpentLeafRegistry(os.path.join(self.tmp.name, "reg.json"))
        self._key_n = 0

    def _trifold(self, seed_byte):
        self._key_n += 1
        return TrifoldKey(bytes([seed_byte]) * 32, height=2,
                          state_path=os.path.join(
                              self.tmp.name, f"key{self._key_n}.json"))

    def test_pqh_same_tx_replayed_against_shared_spent_set(self):
        key = self._trifold(0x07)
        lock = lock_pqh_for_root(key.root)
        fund = _fund(0xF0)
        t = _tx([_vin(fund, 0)],
                [{"value": 9000, "script": lock_pkh_for_pubkey(pub(2))}])
        t["vin"][0]["script"] = sign_pqh_input(
            key, sighash_all(t, 0, lock), registry=self.reg)
        raw = ser_tx(t)
        utxo = _utxo(fund, 0, 10000, lock)
        spent = set()
        ok, reason, _ = validate_tx(raw, utxo, H_ALL, spent_pairs=spent,
                                    network="fork")
        self.assertTrue(ok, reason)
        # Same bytes, same chain state: the leaf is spent now.
        ok, reason, _ = validate_tx(raw, utxo, H_ALL, spent_pairs=spent,
                                    network="fork")
        self.assertFalse(ok)
        self.assertIn("spent leaf already used", reason)

    def test_qhtlc_leaf_cannot_replay_as_pqh_spend(self):
        # The spent-leaf set is shared across lock types: a leaf spent
        # by a QHTLC claim can never be replayed as a PQH spend.
        claim_key = self._trifold(0x11)
        refund_key = self._trifold(0x22)
        secret = bytes(range(32))
        desc = qhtlc_descriptor(hashlib.sha256(secret).digest(),
                                claim_key.root, refund_key.root, 46100)
        qlock = lock_qhtlc_for_descriptor(desc)
        fund_q = _fund(0xF1)
        t = _tx([_vin(fund_q, 0)],
                [{"value": 9000, "script": lock_pkh_for_pubkey(pub(3))}])
        t["vin"][0]["script"] = sign_qhtlc_claim(
            t, 0, qlock, claim_key, secret, desc, registry=self.reg)
        spent = set()
        ok, reason, _ = validate_tx(
            ser_tx(t), _utxo(fund_q, 0, 10000, qlock), H_ALL,
            spent_pairs=spent, network="fork")
        self.assertTrue(ok, reason)
        self.assertEqual(len(spent), 1)
        # Fresh key object, same seed: next_index resets to 0, same root,
        # same leaf — the PQH spend must still be refused by the chain set.
        key2 = TrifoldKey(bytes([0x11]) * 32, height=2,
                          state_path=os.path.join(self.tmp.name, "key2b.json"))
        self.assertEqual(key2.root, claim_key.root)
        self.assertEqual(key2.next_index, 0)
        reg2 = SpentLeafRegistry(os.path.join(self.tmp.name, "reg2.json"))
        plock = lock_pqh_for_root(key2.root)
        fund_p = _fund(0xF2)
        t2 = _tx([_vin(fund_p, 0)],
                 [{"value": 9000, "script": lock_pkh_for_pubkey(pub(3))}])
        t2["vin"][0]["script"] = sign_pqh_input(
            key2, sighash_all(t2, 0, plock), registry=reg2)
        ok, reason, _ = validate_tx(
            ser_tx(t2), _utxo(fund_p, 0, 10000, plock), H_ALL,
            spent_pairs=spent, network="fork")
        self.assertFalse(ok)
        self.assertIn("spent leaf already used", reason)

    def test_mempool_rejects_replay_and_conflicting_spend(self):
        pool = Mempool(os.path.join(self.tmp.name, "mempool.json"),
                       chain_spent_pairs=set())
        fund = _fund(0xF3)
        lock = lock_pkh_for_pubkey(pub(1))
        utxo = _utxo(fund, 0, 10000, lock)
        t = _tx([_vin(fund, 0)],
                [{"value": 9000, "script": lock_pkh_for_pubkey(pub(2))}])
        t["vin"][0]["script"] = sign_pkh_input(t, 0, lock, 1)
        raw = ser_tx(t)
        ok, reason = pool.add(raw, utxo, H_ALL)
        self.assertTrue(ok, reason)
        ok, reason = pool.add(raw, utxo, H_ALL)
        self.assertFalse(ok)
        self.assertIn("already in mempool", reason)
        # A different tx spending the same UTXO: BIP-369, no RBF.
        t2 = _tx([_vin(fund, 0)],
                 [{"value": 8000, "script": lock_pkh_for_pubkey(pub(2))}])
        t2["vin"][0]["script"] = sign_pkh_input(t2, 0, lock, 1)
        ok, reason = pool.add(ser_tx(t2), utxo, H_ALL)
        self.assertFalse(ok)
        self.assertIn("conflicting tx already in mempool", reason)

    def test_mempool_rejects_tx_reusing_chain_spent_leaf(self):
        # A PQH tx whose leaf is already spent on-chain is refused at
        # admission, not just at block validation.
        key = self._trifold(0x07)
        lock = lock_pqh_for_root(key.root)
        fund = _fund(0xF4)
        t = _tx([_vin(fund, 0)],
                [{"value": 9000, "script": lock_pkh_for_pubkey(pub(2))}])
        t["vin"][0]["script"] = sign_pqh_input(
            key, sighash_all(t, 0, lock), registry=self.reg)
        raw = ser_tx(t)
        utxo = _utxo(fund, 0, 10000, lock)
        chain_spent = set()
        ok, _, _ = validate_tx(raw, utxo, H_ALL, spent_pairs=chain_spent,
                               network="fork")
        self.assertTrue(ok)
        pool = Mempool(os.path.join(self.tmp.name, "mempool2.json"),
                       chain_spent_pairs=chain_spent)
        ok, reason = pool.add(raw, utxo, H_ALL)
        self.assertFalse(ok)
        self.assertIn("spent leaf already used", reason)


class FeeReconciliationTests(unittest.TestCase):
    def setUp(self):
        genesis_fork.use_network("testnet")
        self.addCleanup(genesis_fork.use_network, "testnet")

    def _pkh_spend(self, fund, priv, value, out_value):
        lock = lock_pkh_for_pubkey(pub(priv))
        t = _tx([_vin(fund, 0)],
                [{"value": out_value, "script": lock_pkh_for_pubkey(pub(99))}])
        t["vin"][0]["script"] = sign_pkh_input(t, 0, lock, priv)
        return ser_tx(t), _utxo(fund, 0, value, lock)

    def test_validate_block_txs_fees_reconcile_exactly(self):
        spend1, u1 = self._pkh_spend(_fund(0x11), 1, 10000, 9000)
        spend2, u2 = self._pkh_spend(_fund(0x12), 2, 20000, 18500)
        utxo = dict(u1)
        utxo.update(u2)
        fees = 1000 + 1500
        cb = make_coinbase_v2(H_ALL, 0x1f010000, b"Excalibur", fees=fees)
        ok, reason, total = validate_block_txs(
            [cb, spend1, spend2], utxo, H_ALL, subsidy(H_ALL),
            spent_pairs=set(), network="fork")
        self.assertTrue(ok, reason)
        self.assertEqual(total, 2500)

    def test_validate_block_txs_rejects_wrong_coinbase_value(self):
        spend1, u1 = self._pkh_spend(_fund(0x13), 1, 10000, 9000)
        cb = make_coinbase_v2(H_ALL, 0x1f010000, b"Excalibur", fees=0)
        ok, reason, _ = validate_block_txs(
            [cb, spend1], u1, H_ALL, subsidy(H_ALL),
            spent_pairs=set(), network="fork")
        self.assertFalse(ok)
        self.assertIn("coinbase value != subsidy + fees", reason)

    def test_validate_block_txs_rejects_duplicate_txid_and_missing_state(self):
        spend1, u1 = self._pkh_spend(_fund(0x14), 1, 10000, 9000)
        cb = make_coinbase_v2(H_ALL, 0x1f010000, b"Excalibur", fees=1000)
        ok, reason, _ = validate_block_txs(
            [cb, spend1, spend1], u1, H_ALL, subsidy(H_ALL),
            spent_pairs=set(), network="fork")
        self.assertFalse(ok)
        self.assertIn("duplicate txid in block", reason)
        ok, reason, _ = validate_block_txs(
            [cb, spend1], u1, H_ALL, subsidy(H_ALL), spent_pairs=None,
            network="fork")
        self.assertFalse(ok)
        self.assertIn("consensus spent-leaf state is required", reason)

    def test_fusion_lock_required_at_50000_and_satisfied(self):
        spend1, u1 = self._pkh_spend(_fund(0x15), 1, 10000, 9000)
        cb = make_coinbase_v2(50000, 0x1f010000, b"Excalibur", fees=1000)
        ok, reason, _ = validate_block_txs(
            [cb, spend1], u1, 50000, subsidy(50000),
            spent_pairs=set(), network="fork")
        self.assertFalse(ok)
        self.assertIn("missing Golden Stone fusion lock at 50000", reason)
        # Same block with a 1 EXCAL fusion-lock output satisfies it.
        fund = _fund(0x16)
        lock = lock_pkh_for_pubkey(pub(3))
        t = _tx([_vin(fund, 0)],
                [{"value": 100_000_000, "script": fusion_pqh_lock()}])
        t["vin"][0]["script"] = sign_pkh_input(t, 0, lock, 3)
        fusion_spend = ser_tx(t)
        utxo = dict(u1)
        utxo.update(_utxo(fund, 0, 101_000_000, lock))
        cb2 = make_coinbase_v2(50000, 0x1f010000, b"Excalibur",
                               fees=1000 + 1_000_000)
        ok, reason, total = validate_block_txs(
            [cb2, spend1, fusion_spend], utxo, 50000, subsidy(50000),
            spent_pairs=set(), network="fork")
        self.assertTrue(ok, reason)
        self.assertEqual(total, 1000 + 1_000_000)

    def test_construction_parse_fee_reconciles_from_historical_prevout(self):
        prev = bytes.fromhex("16" * 32)
        lock = lock_pkh_for_pubkey(pub(1))
        dest = lock_pkh_for_pubkey(pub(2))
        t = _tx([_vin(prev, 2)],
                [{"value": 9000, "script": dest}])
        t["vin"][0]["script"] = sign_pkh_input(t, 0, lock, 1)
        raw = ser_tx(t)
        cs = SimpleNamespace(utxo={}, tip=lambda: {"height": 12,
                                                   "hash": bytes(32)})
        lookup = lambda key: {"value": 10000, "script": lock} \
            if key == (prev, 2) else None
        builder = Construction(cs, output_lookup=lookup)
        parsed = builder.handle("/construction/parse",
                                {"transaction": raw.hex()})
        self.assertEqual(parsed["metadata"]["fee"], "1000")
        self.assertEqual(parsed["operations"][0]["amount"]["value"], "-10000")


if __name__ == "__main__":
    unittest.main()
