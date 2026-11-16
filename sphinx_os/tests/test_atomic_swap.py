#!/usr/bin/env python3
"""test_atomic_swap.py — Tests for the EXCAL ↔ BTC Atomic Swap Protocol.

Tests cover:
1. Swap creation and validation
2. Secret preimage generation and hash lock
3. State machine transitions (INIT → EXCAL_LOCKED → BTC_LOCKED → COMPLETED)
4. EXCAL and BTC locking
5. Claiming on both chains
6. Refunding on both chains
7. Preimage verification
8. Persistence (save/load)
9. Error cases (wrong state, bad preimage, insufficient funds)
10. Health reporting
11. Full integration flow (complete swap lifecycle)
"""
import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sphinx_os.nexus.atomic_swap import (
    AtomicSwapProtocol,
    AtomicSwap,
    AtomicSwapError,
    SwapStatus,
    SwapDirection,
    HtlcParameters,
    EXCAL_REFUND_BLOCKS,
    BTC_REFUND_BLOCKS,
    MIN_EXCAL_SWAP,
    MIN_BTC_SWAP,
)


class TestSwapCreation(unittest.TestCase):
    """Test atomic swap creation."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.protocol = AtomicSwapProtocol(data_dir=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_create_swap_excal_to_btc(self):
        """Create an EXCAL → BTC swap."""
        swap = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=10 * 100_000_000,  # 10 EXCAL
            btc_amount=50_000_000,  # 0.5 BTC
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        self.assertEqual(swap.status, SwapStatus.INIT)
        self.assertEqual(swap.direction, SwapDirection.EXCAL_TO_BTC)
        self.assertEqual(swap.excal_amount, 10 * 100_000_000)
        self.assertEqual(swap.btc_amount, 50_000_000)
        self.assertIsNotNone(swap.secret_preimage)
        self.assertEqual(len(swap.secret_hash), 32)

    def test_create_swap_btc_to_excal(self):
        """Create a BTC → EXCAL swap."""
        swap = self.protocol.create_swap(
            direction=SwapDirection.BTC_TO_EXCAL,
            excal_amount=10 * 100_000_000,
            btc_amount=50_000_000,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        self.assertEqual(swap.direction, SwapDirection.BTC_TO_EXCAL)

    def test_create_swap_generates_secret(self):
        """Swap generates a 32-byte secret preimage."""
        swap = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        self.assertEqual(len(swap.secret_preimage), 32)
        import hashlib
        computed = hashlib.sha256(swap.secret_preimage).digest()
        self.assertEqual(computed, swap.secret_hash)

    def test_create_swap_unique_id(self):
        """Each swap gets a unique ID."""
        swap1 = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        swap2 = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        self.assertNotEqual(swap1.swap_id, swap2.swap_id)

    def test_create_swap_insufficient_excal(self):
        """Reject swap with EXCAL amount below minimum."""
        with self.assertRaises(AtomicSwapError):
            self.protocol.create_swap(
                direction=SwapDirection.EXCAL_TO_BTC,
                excal_amount=MIN_EXCAL_SWAP - 1,
                btc_amount=MIN_BTC_SWAP,
                excal_refund_address="0" * 40,
                btc_refund_address="0" * 40,
            )

    def test_create_swap_insufficient_btc(self):
        """Reject swap with BTC amount below minimum."""
        with self.assertRaises(AtomicSwapError):
            self.protocol.create_swap(
                direction=SwapDirection.EXCAL_TO_BTC,
                excal_amount=MIN_EXCAL_SWAP,
                btc_amount=MIN_BTC_SWAP - 1,
                excal_refund_address="0" * 40,
                btc_refund_address="0" * 40,
            )

    def test_create_swap_missing_excal_address(self):
        """Reject swap without EXCAL refund address."""
        with self.assertRaises(AtomicSwapError):
            self.protocol.create_swap(
                direction=SwapDirection.EXCAL_TO_BTC,
                excal_amount=MIN_EXCAL_SWAP,
                btc_amount=MIN_BTC_SWAP,
                excal_refund_address="",
                btc_refund_address="0" * 40,
            )

    def test_create_swap_missing_btc_address(self):
        """Reject swap without BTC refund address."""
        with self.assertRaises(AtomicSwapError):
            self.protocol.create_swap(
                direction=SwapDirection.EXCAL_TO_BTC,
                excal_amount=MIN_EXCAL_SWAP,
                btc_amount=MIN_BTC_SWAP,
                excal_refund_address="0" * 40,
                btc_refund_address="",
            )

    def test_create_swap_default_claim_address(self):
        """Claim address defaults to refund address."""
        swap = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="aaa" * 13,
            btc_refund_address="bbb" * 13,
        )
        self.assertEqual(swap.excal_claim_address, swap.excal_refund_address)
        self.assertEqual(swap.btc_claim_address, swap.btc_refund_address)

    def test_create_swap_custom_timelocks(self):
        """Custom timelocks are respected."""
        swap = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
            excal_timeout=200,
            btc_timeout=150,
        )
        self.assertEqual(swap.excal_timeout_blocks, 200)
        self.assertEqual(swap.btc_timeout_blocks, 150)


class TestStateTransitions(unittest.TestCase):
    """Test state machine transitions."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.protocol = AtomicSwapProtocol(data_dir=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_init_to_excal_locked(self):
        """INIT → EXCAL_LOCKED transition."""
        swap = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        result = self.protocol.lock_excal(
            swap.swap_id, "txid123", 0, b"\x03" + b"\x00" * 20
        )
        self.assertEqual(result.status, SwapStatus.EXCAL_LOCKED)
        self.assertIsNotNone(result.excal_htlc)
        self.assertEqual(result.excal_htlc.funding_txid, "txid123")

    def test_excal_locked_to_btc_locked(self):
        """EXCAL_LOCKED → BTC_LOCKED transition."""
        swap = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        self.protocol.lock_excal(swap.swap_id, "txid1", 0, b"\x03" + b"\x00" * 20)
        result = self.protocol.lock_btc(swap.swap_id, "txid2", 0, b"\x03" + b"\x00" * 20)
        self.assertEqual(result.status, SwapStatus.BTC_LOCKED)
        self.assertIsNotNone(result.btc_htlc)

    def test_cannot_lock_btc_before_excal(self):
        """BTC cannot be locked before EXCAL."""
        swap = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        with self.assertRaises(AtomicSwapError):
            self.protocol.lock_btc(swap.swap_id, "txid", 0, b"\x03" + b"\x00" * 20)

    def test_cannot_lock_excal_twice(self):
        """EXCAL cannot be locked twice."""
        swap = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        self.protocol.lock_excal(swap.swap_id, "txid1", 0, b"\x03" + b"\x00" * 20)
        with self.assertRaises(AtomicSwapError):
            self.protocol.lock_excal(swap.swap_id, "txid2", 0, b"\x03" + b"\x00" * 20)

    def test_full_claim_flow(self):
        """Full flow: INIT → EXCAL_LOCKED → BTC_LOCKED → EXCAL_CLAIMED → COMPLETED."""
        swap = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        self.protocol.lock_excal(swap.swap_id, "txid1", 0, b"\x03" + b"\x00" * 20)
        self.protocol.lock_btc(swap.swap_id, "txid2", 0, b"\x03" + b"\x00" * 20)
        
        # Claim BTC first
        result = self.protocol.claim_btc(
            swap.swap_id, swap.secret_preimage, "claim_btc_txid"
        )
        self.assertEqual(result.status, SwapStatus.BTC_CLAIMED)
        
        # Then claim EXCAL → COMPLETED
        result = self.protocol.claim_excal(
            swap.swap_id, swap.secret_preimage, "claim_excal_txid"
        )
        self.assertEqual(result.status, SwapStatus.COMPLETED)

    def test_refund_excal(self):
        """Refund EXCAL after timelock."""
        swap = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        self.protocol.lock_excal(swap.swap_id, "txid1", 0, b"\x03" + b"\x00" * 20)
        result = self.protocol.refund_excal(swap.swap_id, "refund_txid")
        self.assertEqual(result.status, SwapStatus.REFUND_EXCAL)

    def test_refund_btc(self):
        """Refund BTC after timelock."""
        swap = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        self.protocol.lock_excal(swap.swap_id, "txid1", 0, b"\x03" + b"\x00" * 20)
        self.protocol.lock_btc(swap.swap_id, "txid2", 0, b"\x03" + b"\x00" * 20)
        result = self.protocol.refund_btc(swap.swap_id, "refund_txid")
        self.assertEqual(result.status, SwapStatus.REFUND_BTC)


class TestPreimageVerification(unittest.TestCase):
    """Test secret preimage verification."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.protocol = AtomicSwapProtocol(data_dir=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_correct_preimage_verifies(self):
        """Correct preimage verifies."""
        swap = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        self.assertTrue(
            self.protocol.verify_preimage(swap.swap_id, swap.secret_preimage)
        )

    def test_wrong_preimage_fails(self):
        """Wrong preimage fails verification."""
        swap = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        wrong = b"\x00" * 32
        self.assertFalse(self.protocol.verify_preimage(swap.swap_id, wrong))

    def test_claim_rejects_wrong_preimage(self):
        """Claim rejects wrong preimage."""
        swap = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        self.protocol.lock_excal(swap.swap_id, "txid1", 0, b"\x03" + b"\x00" * 20)
        self.protocol.lock_btc(swap.swap_id, "txid2", 0, b"\x03" + b"\x00" * 20)
        wrong = b"\xff" * 32
        with self.assertRaises(AtomicSwapError):
            self.protocol.claim_btc(swap.swap_id, wrong, "claim_txid")


class TestPersistence(unittest.TestCase):
    """Test swap persistence."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_swap_persists_and_loads(self):
        """Swap persists to disk and reloads."""
        protocol1 = AtomicSwapProtocol(data_dir=self.tmpdir)
        swap = protocol1.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        swap_id = swap.swap_id
        
        # Reload
        protocol2 = AtomicSwapProtocol(data_dir=self.tmpdir)
        loaded = protocol2.get_swap(swap_id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.swap_id, swap_id)
        self.assertEqual(loaded.excal_amount, MIN_EXCAL_SWAP)
        self.assertEqual(loaded.btc_amount, MIN_BTC_SWAP)


class TestHtlcParameters(unittest.TestCase):
    """Test HTLC parameter generation."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.protocol = AtomicSwapProtocol(data_dir=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_htlc_parameters(self):
        """Get HTLC parameters for a swap."""
        swap = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=10 * 100_000_000,
            btc_amount=50_000_000,
            excal_refund_address="aaa" * 13,
            btc_refund_address="bbb" * 13,
        )
        params = self.protocol.get_htlc_parameters(swap)
        self.assertEqual(params["swap_id"], swap.swap_id)
        self.assertEqual(params["secret_hash"], swap.secret_hash.hex())
        self.assertEqual(params["excal"]["amount"], 10 * 100_000_000)
        self.assertEqual(params["btc"]["amount"], 50_000_000)


class TestSwapSummary(unittest.TestCase):
    """Test swap summary generation."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.protocol = AtomicSwapProtocol(data_dir=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_summary(self):
        """Get human-readable summary."""
        swap = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=10 * 100_000_000,
            btc_amount=50_000_000,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        summary = self.protocol.get_swap_summary(swap.swap_id)
        self.assertEqual(summary["status"], "init")
        self.assertEqual(summary["direction"], "excal_to_btc")
        self.assertIn("10.00000000 EXCAL", summary["excal_amount"])
        self.assertIn("0.50000000 BTC", summary["btc_amount"])

    def test_summary_not_found(self):
        """Summary raises for non-existent swap."""
        with self.assertRaises(AtomicSwapError):
            self.protocol.get_swap_summary("nonexistent")


class TestHealthReport(unittest.TestCase):
    """Test health reporting."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.protocol = AtomicSwapProtocol(data_dir=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_empty_health(self):
        """Health report with no swaps."""
        report = self.protocol.health_report()
        self.assertEqual(report["component"], "AtomicSwapProtocol")
        self.assertEqual(report["total_swaps"], 0)
        self.assertEqual(report["active_swaps"], 0)

    def test_health_with_swaps(self):
        """Health report counts swaps by status."""
        self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        swap2 = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        self.protocol.lock_excal(swap2.swap_id, "txid", 0, b"\x03" + b"\x00" * 20)
        
        report = self.protocol.health_report()
        self.assertEqual(report["total_swaps"], 2)
        self.assertEqual(report["active_swaps"], 2)


class TestListSwaps(unittest.TestCase):
    """Test listing and filtering swaps."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.protocol = AtomicSwapProtocol(data_dir=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_list_all_swaps(self):
        """List all swaps."""
        self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        self.protocol.create_swap(
            direction=SwapDirection.BTC_TO_EXCAL,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        swaps = self.protocol.list_swaps()
        self.assertEqual(len(swaps), 2)

    def test_list_by_status(self):
        """Filter swaps by status."""
        swap1 = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        self.protocol.lock_excal(swap1.swap_id, "txid", 0, b"\x03" + b"\x00" * 20)
        
        init_swaps = self.protocol.list_swaps(SwapStatus.INIT)
        locked_swaps = self.protocol.list_swaps(SwapStatus.EXCAL_LOCKED)
        self.assertEqual(len(init_swaps), 1)
        self.assertEqual(len(locked_swaps), 1)


class TestEventLog(unittest.TestCase):
    """Test event logging."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.protocol = AtomicSwapProtocol(data_dir=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_events_recorded(self):
        """Events are recorded during state transitions."""
        swap = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        self.protocol.lock_excal(swap.swap_id, "txid1", 0, b"\x03" + b"\x00" * 20)
        self.protocol.lock_btc(swap.swap_id, "txid2", 0, b"\x03" + b"\x00" * 20)
        
        swap = self.protocol.get_swap(swap.swap_id)
        self.assertGreaterEqual(len(swap.events), 3)
        event_types = [e["type"] for e in swap.events]
        self.assertIn("swap_created", event_types)
        self.assertIn("excal_locked", event_types)
        self.assertIn("btc_locked", event_types)


class TestIntegration(unittest.TestCase):
    """Full integration tests."""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.protocol = AtomicSwapProtocol(data_dir=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_complete_swap_lifecycle(self):
        """Full swap: create → lock EXCAL → lock BTC → claim both → complete."""
        swap = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=10 * 100_000_000,
            btc_amount=50_000_000,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        
        # Lock EXCAL (swap object IS updated in-place since it's the same reference)
        self.protocol.lock_excal(swap.swap_id, "excal_txid", 0, b"\x03" + b"\x00" * 20)
        swap = self.protocol.get_swap(swap.swap_id)
        self.assertEqual(swap.status, SwapStatus.EXCAL_LOCKED)
        
        # Lock BTC
        self.protocol.lock_btc(swap.swap_id, "btc_txid", 0, b"\x03" + b"\x00" * 20)
        
        # Claim BTC
        self.protocol.claim_btc(swap.swap_id, swap.secret_preimage, "claim_btc")
        
        # Claim EXCAL → COMPLETED
        self.protocol.claim_excal(swap.swap_id, swap.secret_preimage, "claim_excal")
        
        final = self.protocol.get_swap(swap.swap_id)
        self.assertEqual(final.status, SwapStatus.COMPLETED)
        self.assertEqual(len(final.events), 5)

    def test_refund_path(self):
        """Swap fails: lock EXCAL → refund EXCAL."""
        swap = self.protocol.create_swap(
            direction=SwapDirection.EXCAL_TO_BTC,
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            excal_refund_address="0" * 40,
            btc_refund_address="0" * 40,
        )
        self.protocol.lock_excal(swap.swap_id, "txid", 0, b"\x03" + b"\x00" * 20)
        self.protocol.refund_excal(swap.swap_id, "refund_txid")
        
        final = self.protocol.get_swap(swap.swap_id)
        self.assertEqual(final.status, SwapStatus.REFUND_EXCAL)


if __name__ == "__main__":
    unittest.main()
