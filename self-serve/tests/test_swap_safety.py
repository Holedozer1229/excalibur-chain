#!/usr/bin/env python3
"""test_swap_safety.py — regression tests for the Taproot HTLC migration.

Tests cover:
  1. Timeout ordering invariant (BTC window >= EXCAL window + margin)
  2. Stale EXCAL refund height is refused
  3. Missing excal_refund_height is refused
  4. Lot normalization maps published field names
  5. Normalize does not invent ask_sats
  6. Unconfirmed EXCAL funding fails verify_excal_leg
  7. Wrong lock in EXCAL funding fails verify_excal_leg
  8. Good EXCAL leg passes verify_excal_leg

Run:
  python3 -m unittest tests.test_swap_safety -v
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import taker_htlc
import deliver_seed


def make_lot(exc_refund=62898, ask=21000):
    """Create a test lot with all required fields."""
    return taker_htlc.normalize_lot({
        "lot": "test", "label": "test", "tag": "TEST",
        "secret_hash": "aa" * 32, "funding_block": 42899,
        "funding_txid": "aa" * 32,
        "timeout": exc_refund, "lock": "04" + "11" * 20,
        "ask_sats": ask,
    })


class TimeoutOrderingTests(unittest.TestCase):
    """Tests for compute_btc_refund_height safety invariants."""

    def test_invariant_holds_by_construction(self):
        """BTC window >= EXCAL window + SAFETY_MARGIN_SECONDS."""
        lot = make_lot(exc_refund=62898)
        btc_tip = 900000
        excal_tip = 45000
        timeout = taker_htlc.compute_btc_refund_height(lot, btc_tip, excal_tip)
        btc_remaining_s = (timeout - btc_tip) * taker_htlc.BTC_BLOCK_SECONDS
        exc_remaining_s = (62898 - excal_tip) * taker_htlc.FORK_BLOCK_SECONDS
        self.assertGreaterEqual(
            btc_remaining_s,
            exc_remaining_s + taker_htlc.SAFETY_MARGIN_SECONDS)

    def test_stale_refund_refused(self):
        """EXCAL tip >= refund height -> SystemExit."""
        lot = make_lot(exc_refund=45000)
        with self.assertRaises(SystemExit):
            taker_htlc.compute_btc_refund_height(lot, 900000, 45000)

    def test_missing_refund_height_refused(self):
        """No excal_refund_height -> SystemExit."""
        lot = make_lot()
        del lot["excal_refund_height"]
        with self.assertRaises(SystemExit):
            taker_htlc.compute_btc_refund_height(lot, 900000, 45000)


class LotSchemaTests(unittest.TestCase):
    """Tests for normalize_lot field mapping."""

    def test_normalize_maps_published_fields(self):
        """timeout -> excal_refund_height, lock -> qhtlc_lock."""
        lot = taker_htlc.normalize_lot({"timeout": 62898, "lock": "04aa"})
        self.assertEqual(lot["excal_refund_height"], 62898)
        self.assertEqual(lot["qhtlc_lock"], "04aa")

    def test_normalize_does_not_invent_ask(self):
        """normalize_lot should not create ask_sats if absent."""
        lot = taker_htlc.normalize_lot({"timeout": 62898})
        self.assertIsNone(lot.get("ask_sats"))


class ExcalLegGateTests(unittest.TestCase):
    """Tests for verify_excal_leg — EXCAL fork leg verification."""

    def _gate(self, tx, tip, btc_tip):
        """Helper: set up mock fork_rpc and call verify_excal_leg."""
        deliver_seed.fork_rpc = lambda m, p=None: \
            {"getblockcount": tip, "getrawtransaction": tx}[m]
        deliver_seed.fetch_btc_tip_height = lambda: btc_tip
        lot = make_lot()
        return deliver_seed.verify_excal_leg(lot, btc_tip + 2000)

    def test_unconfirmed_funding_fails(self):
        """Funding tx with no blockhash -> ValueError."""
        with self.assertRaises(ValueError):
            self._gate({"blockhash": None}, 45000, 900000)

    def test_wrong_lock_fails(self):
        """Funding tx with wrong scriptPubKey -> ValueError."""
        # blockheight gives 17 confirmations so the lock check is what fires
        tx = {"blockhash": "x", "blockheight": 44983,
              "vout": [{"scriptpubkey": "ff", "value": 1}]}
        with self.assertRaises(ValueError):
            self._gate(tx, 45000, 900000)

    def test_good_leg_passes(self):
        """Valid funding tx with matching lock -> returns confirmations."""
        # blockheight = tip - 16 -> 17 confirmations >= 10 required.
        # Invariant: exc (62898-45000)*60 = 1,073,880s + 7,200s margin
        # <= btc window 2000*600 = 1,200,000s — holds.
        tx = {"blockhash": "x", "blockheight": 44984,
              "vout": [{"scriptpubkey": "04" + "11" * 20, "value": 1}]}
        info = self._gate(tx, 45000, 900000)
        self.assertEqual(info["confirmations"], 17)


if __name__ == "__main__":
    unittest.main()
