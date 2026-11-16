#!/usr/bin/env python3
"""Tests for EXCAL ↔ BTC bridge (HTLC lock + SkyNet offers)."""

import hashlib
import os
import shutil
import tempfile
import unittest

from sphinx_os.nexus.btc_bridge import (
    BtcBridge,
    BridgeOffer,
    btc_htlc_lock,
    build_btc_htlc_script,
    bech32_encode,
)


# Deterministic compressed test pubkeys (not used on mainnet)
CLAIM_PUB = bytes.fromhex(
    "02" + "11" * 32
)
REFUND_PUB = bytes.fromhex(
    "03" + "22" * 32
)


class TestBtcHtlcBuilders(unittest.TestCase):
    def test_script_and_address(self):
        secret_hash = hashlib.sha256(b"test-preimage-32-bytes-padded!!").digest()
        lock = btc_htlc_lock(CLAIM_PUB, REFUND_PUB, secret_hash, timeout_height=900000)
        self.assertTrue(lock["address"].startswith("bc1"))
        self.assertEqual(len(bytes.fromhex(lock["witness_script_hash"])), 32)
        script = build_btc_htlc_script(CLAIM_PUB, REFUND_PUB, secret_hash, 900000)
        self.assertEqual(script.hex(), lock["witness_script_hex"])

    def test_bech32_roundtrip_length(self):
        prog = hashlib.sha256(b"prog").digest()
        addr = bech32_encode("bc", 0, prog)
        self.assertTrue(addr.startswith("bc1q"))


class TestBtcBridge(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.bridge = BtcBridge(data_dir=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_create_offer(self):
        result = self.bridge.create_excal_to_btc_offer(
            excal_amount_swords=1 * 100_000_000,
            btc_amount_sats=10_000_000,
            excal_refund_address="0" * 40,
            btc_refund_address="bc1qtest",
            claim_pubkey=CLAIM_PUB,
            refund_pubkey=REFUND_PUB,
            btc_tip_height=850000,
            proposer_wallet="MYWALLET",
            proposer_host="10.0.0.5",
            proposer_port=9433,
        )
        self.assertIn("offer", result)
        self.assertEqual(result["offer"]["type"], "swap_offer")
        self.assertTrue(result["offer"]["btc_lock_address"].startswith("bc1"))
        self.assertTrue(result["secret_preimage"])
        self.assertNotEqual(result["secret_preimage"], result["offer"]["secret_hash"])

    def test_ingest_remote_offer(self):
        offer = BridgeOffer(
            swap_id="remote1",
            direction="excal_to_btc",
            excal_amount=100_000_000,
            btc_amount=10_000_000,
            secret_hash="aa" * 32,
            excal_refund_address="0" * 40,
            btc_refund_address="bc1q",
            proposer_wallet="THEM",
        )
        self.bridge.ingest_remote_offer(offer.to_dict())
        incoming = self.bridge.list_incoming_offers()
        self.assertEqual(len(incoming), 1)
        self.assertEqual(incoming[0]["swap_id"], "remote1")

    def test_lock_and_claim_flow(self):
        result = self.bridge.create_excal_to_btc_offer(
            excal_amount_swords=1 * 100_000_000,
            btc_amount_sats=10_000_000,
            excal_refund_address="0" * 40,
            # atomic_swap stores refund fields as hex for HtlcParameters
            btc_refund_address="00" * 20,
        )
        swap_id = result["offer"]["swap_id"]
        self.bridge.mark_excal_locked(swap_id, "excaltxid", 0)
        self.bridge.mark_btc_locked(swap_id, "btctxid", 0)
        claimed = self.bridge.mark_claimed(
            swap_id, "btc", "btcclaim", result["secret_preimage"]
        )
        self.assertIn(claimed["status"], ("btc_claimed", "completed", "excal_claimed"))


if __name__ == "__main__":
    unittest.main()
