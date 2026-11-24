"""Target-client acceptance tests for the custom Rosetta signature
types `trifold` and `excal_knot` (Stage 4).

Findings these tests pin down (verified 2026-11-23 against the real
rosetta-cli v0.10.4 binary and the rosetta-sdk-go asserter docs):

* The SDK defines exactly five SignatureType values (ecdsa,
  ecdsa_recovery, ed25519, schnorr_1, schnorr_poseidon) and the
  asserter exposes SignatureType validation that fails anything else
  with "not a supported SignatureType". The v0.10.4 binary carries the
  same failure strings ("signature type %s is invalid", "signing
  payload signature type %v is invalid", "cannot determine signature
  type for payload", "sign: unexpected Signature type while signing").
  A stock rosetta-cli / standard Rosetta client that validates
  construction payloads through the asserter therefore REJECTS a
  `trifold` or `excal_knot` signing payload, and its signer cannot
  produce either type — `check:construction` cannot be run end to end
  for PQH/QHTLC/KNOT inputs at all. Only a chain-aware client that
  implements the EXCAL signer (rosetta/trifold_signer.py,
  rosetta/knot_signer.py) can spend those locks.
* `check:data` never sees a signature type: blocks carry operations
  only, no signatures. The running full-range check:data (5,598 blocks
  passed, 0 failures at the time of writing) is therefore NO evidence
  about the custom types. What it does prove is that the
  /network/options advertisement itself passes asserter validation:
  `rosetta-cli utils:asserter-configuration` was run against the live
  server and succeeded, and the generated asserter config contains no
  signature-related key at all (pinned by
  test_asserter_config_cannot_allow_custom_signature_types).
* What the server does to stay consumable without mislabeling: the
  types are advertised in /network/options metadata.excal_extensions,
  and each custom signing payload carries metadata stating exactly
  what Signature.hex_bytes must contain — the full native scriptSig
  witness for trifold, the 56-byte preimage witness for excal_knot
  (whose hex_bytes is a correlation digest only and must NOT be
  signed). These tests assert that metadata and that combine enforces
  the exact type match (a witness submitted under the wrong type is
  rejected, never silently accepted).
"""
import hashlib
import json
import os
import tempfile
import unittest
from types import SimpleNamespace

import genesis_fork
import secp256k1 as secp
from genesis_fork import KNOT_ACTIVATION
from rosetta.construction import Construction
from rosetta.excal_rosetta import ExcalRosetta
from rosetta.knot_signer import build_knot_signature
from rosetta.trifold_signer import ExcalTrifoldRosettaSigner
from spent_leaf_registry import SpentLeafRegistry
from trifold_lockbox import TrifoldKey
from txscript import (
    knot_lock_for_secret, lock_pkh_for_pubkey, lock_pqh_for_root,
    lock_qhtlc_for_descriptor, qhtlc_descriptor, ser_tx, sighash_all,
    sign_knot_input, validate_tx)

# Height where every lock is active (qlock 102, qday 25212, htlc 36010,
# qhtlc 40040, bridge 39200, knot 44520).
H_ALL = 46000
KNOT_P, KNOT_Q, KNOT_N, KNOT_EPS = 2, 3, 1, 2 ** 31
KNOT_TSTAR = 12345678901234567890123456789012345678


def pub(priv):
    return secp.compress(secp.priv_to_pub(priv))


def _tx(vins, vouts):
    return {"version": 1, "vin": vins, "vout": vouts, "locktime": 0}


def _vin(prev, idx, script=b""):
    return {"prev": prev, "idx": idx, "script": script, "seq": 0xffffffff}


def _fund(n):
    return bytes([n]) * 32


class CustomSignatureTypeTests(unittest.TestCase):
    def setUp(self):
        genesis_fork.use_network("fork")
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

    def _builder(self, utxo, tip_height, network="fork"):
        cs = SimpleNamespace(
            utxo=utxo, tip=lambda: {"height": tip_height, "hash": bytes(32)})
        return Construction(cs, network=network), cs

    def _run_flow(self, builder, coin, in_value, in_lock,
                  out_value, out_lock, fee):
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

    def test_pqh_payload_advertises_trifold_with_witness_metadata(self):
        key = self._trifold(0x31)
        lock = lock_pqh_for_root(key.root)
        prev = _fund(0xB1)
        coin = prev[::-1].hex() + ":0"
        builder, _ = self._builder(
            {(prev, 0): [(10000, lock, False, 0)]}, H_ALL - 1)
        _, payloads = self._run_flow(
            builder, coin, 10000, lock, 9000, lock_pkh_for_pubkey(pub(2)), 1000)
        self.assertEqual(len(payloads["payloads"]), 1)
        p = payloads["payloads"][0]
        self.assertEqual(p["signature_type"], "trifold")
        self.assertEqual(len(bytes.fromhex(p["hex_bytes"])), 32)
        md = p.get("metadata") or {}
        self.assertEqual(md.get("excal_signature_scheme"), "trifold")
        self.assertIn("complete native scriptSig witness", md.get("witness", ""))
        self.assertIn("sighash digest", md.get("signed_bytes", ""))

    def test_qhtlc_payload_advertises_trifold(self):
        claim_key = self._trifold(0x32)
        refund_key = self._trifold(0x33)
        secret = bytes(range(32))
        desc = qhtlc_descriptor(hashlib.sha256(secret).digest(),
                                claim_key.root, refund_key.root, 46100)
        lock = lock_qhtlc_for_descriptor(desc)
        prev = _fund(0xB2)
        coin = prev[::-1].hex() + ":0"
        builder, _ = self._builder(
            {(prev, 0): [(10000, lock, False, 0)]}, H_ALL - 1)
        _, payloads = self._run_flow(
            builder, coin, 10000, lock, 9000, lock_pkh_for_pubkey(pub(2)), 1000)
        self.assertEqual(len(payloads["payloads"]), 1)
        p = payloads["payloads"][0]
        self.assertEqual(p["signature_type"], "trifold")
        self.assertEqual((p.get("metadata") or {}).get("excal_signature_scheme"),
                         "trifold")

    def test_knot_payload_advertises_excal_knot_and_marks_digest_unsigned(self):
        lock, desc, _ = knot_lock_for_secret(
            KNOT_P, KNOT_Q, KNOT_N, KNOT_EPS, KNOT_TSTAR)
        prev = _fund(0xB3)
        coin = prev[::-1].hex() + ":0"
        builder, _ = self._builder(
            {(prev, 0): [(10000, lock, False, 0)]}, KNOT_ACTIVATION - 1)
        _, payloads = self._run_flow(
            builder, coin, 10000, lock, 9000, lock_pkh_for_pubkey(pub(2)), 1000)
        self.assertEqual(len(payloads["payloads"]), 1)
        p = payloads["payloads"][0]
        self.assertEqual(p["signature_type"], "excal_knot")
        md = p.get("metadata") or {}
        self.assertEqual(md.get("excal_signature_scheme"), "excal_knot")
        self.assertIn("do NOT sign", md.get("signed_bytes", ""))
        self.assertIn("56-byte", md.get("witness", ""))

    def test_combine_rejects_wrong_signature_type_for_custom_locks(self):
        # PQH input, witness submitted as ecdsa: must be refused, not
        # reinterpreted.
        key = self._trifold(0x34)
        lock = lock_pqh_for_root(key.root)
        prev = _fund(0xB4)
        coin = prev[::-1].hex() + ":0"
        builder, _ = self._builder(
            {(prev, 0): [(10000, lock, False, 0)]}, H_ALL - 1)
        _, payloads = self._run_flow(
            builder, coin, 10000, lock, 9000, lock_pkh_for_pubkey(pub(2)), 1000)
        digest = payloads["payloads"][0]["hex_bytes"]
        with self.assertRaisesRegex(ValueError, "missing Trifold witness"):
            builder.handle("/construction/combine", {
                "unsigned_transaction": payloads["unsigned_transaction"],
                "signatures": [{"signing_payload": {"hex_bytes": digest},
                                "signature_type": "ecdsa",
                                "hex_bytes": "00" * 64,
                                "public_key": {"hex_bytes": pub(1).hex()}}]})
        # Same digest, real Trifold witness, wrong type label: refused.
        wallet = SimpleNamespace(trifold_key=lambda: key)
        signer = ExcalTrifoldRosettaSigner(wallet, registry=self.reg)
        sig = signer.sign_payload(payloads["unsigned_transaction"], 0,
                                  lock.hex(), "trifold-pqh")
        mislabeled = dict(sig, signature_type="excal_knot")
        with self.assertRaisesRegex(ValueError, "missing Trifold witness"):
            builder.handle("/construction/combine", {
                "unsigned_transaction": payloads["unsigned_transaction"],
                "signatures": [mislabeled]})
        # KNOT input, witness submitted as ecdsa: refused.
        klock, kdesc, _ = knot_lock_for_secret(
            KNOT_P, KNOT_Q, KNOT_N, KNOT_EPS, KNOT_TSTAR)
        kprev = _fund(0xB5)
        kcoin = kprev[::-1].hex() + ":0"
        kbuilder, _ = self._builder(
            {(kprev, 0): [(10000, klock, False, 0)]}, KNOT_ACTIVATION - 1)
        _, kpayloads = self._run_flow(
            kbuilder, kcoin, 10000, klock, 9000, lock_pkh_for_pubkey(pub(2)), 1000)
        kdigest = kpayloads["payloads"][0]["hex_bytes"]
        with self.assertRaisesRegex(ValueError, "missing KNOT witness"):
            kbuilder.handle("/construction/combine", {
                "unsigned_transaction": kpayloads["unsigned_transaction"],
                "signatures": [{"signing_payload": {"hex_bytes": kdigest},
                                "signature_type": "ecdsa",
                                "hex_bytes": "00" * 64,
                                "public_key": {"hex_bytes": pub(1).hex()}}]})

    def test_combine_accepts_trifold_witness_end_to_end(self):
        key = self._trifold(0x36)
        lock = lock_pqh_for_root(key.root)
        prev = _fund(0xB6)
        coin = prev[::-1].hex() + ":0"
        utxo = {(prev, 0): [(10000, lock, False, 0)]}
        builder, _ = self._builder(utxo, H_ALL - 1)
        _, payloads = self._run_flow(
            builder, coin, 10000, lock, 9000, lock_pkh_for_pubkey(pub(2)), 1000)
        wallet = SimpleNamespace(trifold_key=lambda: key)
        signer = ExcalTrifoldRosettaSigner(wallet, registry=self.reg)
        sig = signer.sign_payload(payloads["unsigned_transaction"], 0,
                                  lock.hex(), "trifold-pqh")
        self.assertEqual(sig["signature_type"], "trifold")
        result = builder.handle("/construction/combine", {
            "unsigned_transaction": payloads["unsigned_transaction"],
            "signatures": [sig]})
        self.assertEqual(result["fee"], "1000")
        ok, reason, _ = validate_tx(
            bytes.fromhex(result["signed_transaction"]), utxo, H_ALL,
            spent_pairs=set(), network="fork")
        self.assertTrue(ok, reason)

    def test_combine_accepts_knot_witness_end_to_end(self):
        lock, desc, _ = knot_lock_for_secret(
            KNOT_P, KNOT_Q, KNOT_N, KNOT_EPS, KNOT_TSTAR)
        prev = _fund(0xB7)
        coin = prev[::-1].hex() + ":0"
        utxo = {(prev, 0): [(10000, lock, False, 0)]}
        builder, _ = self._builder(utxo, KNOT_ACTIVATION - 1)
        _, payloads = self._run_flow(
            builder, coin, 10000, lock, 9000, lock_pkh_for_pubkey(pub(2)), 1000)
        sig = build_knot_signature(
            payloads["unsigned_transaction"], 0, lock.hex(),
            KNOT_TSTAR.to_bytes(16, "big").hex(), desc.hex(),
            KNOT_ACTIVATION, network="fork")
        self.assertEqual(sig["signature_type"], "excal_knot")
        self.assertEqual(len(bytes.fromhex(sig["hex_bytes"])), 56)
        result = builder.handle("/construction/combine", {
            "unsigned_transaction": payloads["unsigned_transaction"],
            "signatures": [sig]})
        self.assertEqual(result["fee"], "1000")

    def test_network_options_advertises_extension_types(self):
        ghash = bytes.fromhex("11" * 32)
        b1hash = bytes.fromhex("22" * 32)
        genesis = {"height": 0, "hash": ghash, "time": 100,
                   "version": 1, "bits": 0x1f000100, "nonce": 0, "txs": []}
        block1 = {"height": 1, "hash": b1hash, "prev": ghash,
                  "time": 160, "version": 1, "bits": 0x1f000100,
                  "nonce": 1, "txs": []}
        cs = SimpleNamespace(
            by_height={0: genesis, 1: block1}, utxo={},
            tip=lambda: {"height": 1, "hash": b1hash})
        app = ExcalRosetta(cs, network="mainnet")
        status, body = app.handle("/network/options", {
            "network_identifier": {"blockchain": "excal", "network": "mainnet"}})
        self.assertEqual(status, 200)
        ext = body["metadata"]["excal_extensions"]
        self.assertEqual(ext["trifold_signature_type"], "trifold")
        self.assertEqual(ext["knot_signature_type"], "excal_knot")
        self.assertEqual(ext["witness_encoding"], "native scriptSig hex")

    def test_asserter_config_cannot_allow_custom_signature_types(self):
        # The asserter configuration generated from the live server has
        # no signature-related field at all: the asserter cannot allow
        # or deny signature types, it only knows its five built-in
        # values. check:data passing therefore says nothing about
        # trifold/excal_knot; this test pins that fact so nobody later
        # claims check:data as custom-type coverage.
        path = os.path.join(os.path.dirname(__file__), "..",
                            "coinbase", "rosetta-cli", "mainnet-asserter.json")
        with open(path) as fh:
            cfg = json.load(fh)

        def keys(obj):
            if isinstance(obj, dict):
                for k, v in obj.items():
                    yield k
                    yield from keys(v)
            elif isinstance(obj, list):
                for v in obj:
                    yield from keys(v)

        sig_keys = [k for k in keys(cfg) if "signature" in str(k).lower()]
        self.assertEqual(sig_keys, [])
        self.assertEqual(sorted(cfg.keys()), [
            "allowed_errors", "allowed_operation_statuses",
            "allowed_operation_types", "allowed_timestamp_start_index",
            "genesis_block_identifier", "network_identifier"])


if __name__ == "__main__":
    unittest.main()
