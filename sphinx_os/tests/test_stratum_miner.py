#!/usr/bin/env python3
"""
Tests for AetherionEXCAL External Stratum Miner (stratum_miner.py)

Covers: SHA-256d hashing, header serialization, difficulty bits,
Stratum messages, mining jobs, hashrate tracking, share statistics,
and integration scenarios.
"""
import hashlib
import json
import struct
import sys
import os
import time
import unittest
from unittest.mock import patch, MagicMock

# Add project root to path
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _ROOT)

from stratum_miner import (
    # Hashing
    sha256, sha256d, ser_header, header_hash,
    bits_to_target, target_to_bits, calculate_difficulty,
    merkle_root, txid,
    # Constants
    DIFF1, MAX_TARGET,
    # Stratum protocol
    StratumMethod, StratumMessage,
    # Mining
    MiningJob,
    # Statistics
    HashrateTracker, ShareStats,
)


class TestSHA256(unittest.TestCase):
    """Test SHA-256 hashing functions."""

    def test_sha256_empty(self):
        """SHA-256 of empty input."""
        result = sha256(b"")
        expected = hashlib.sha256(b"").digest()
        self.assertEqual(result, expected)
        self.assertEqual(len(result), 32)

    def test_sha256_known(self):
        """SHA-256 of known input."""
        result = sha256(b"hello")
        expected = hashlib.sha256(b"hello").digest()
        self.assertEqual(result, expected)

    def test_sha256d_empty(self):
        """Double SHA-256 of empty input."""
        result = sha256d(b"")
        expected = hashlib.sha256(hashlib.sha256(b"").digest()).digest()
        self.assertEqual(result, expected)
        self.assertEqual(len(result), 32)

    def test_sha256d_known(self):
        """Double SHA-256 of known input."""
        result = sha256d(b"hello")
        expected = hashlib.sha256(hashlib.sha256(b"hello").digest()).digest()
        self.assertEqual(result, expected)

    def test_sha256d_deterministic(self):
        """Same input always produces same output."""
        data = b"AetherionEXCAL"
        self.assertEqual(sha256d(data), sha256d(data))

    def test_sha256d_different_input(self):
        """Different inputs produce different outputs."""
        h1 = sha256d(b"test1")
        h2 = sha256d(b"test2")
        self.assertNotEqual(h1, h2)


class TestHeaderSerialization(unittest.TestCase):
    """Test block header serialization."""

    def test_ser_header_length(self):
        """Serialized header is exactly 80 bytes."""
        header = ser_header(
            version=1,
            prev=b"\x00" * 32,
            merkle=b"\x00" * 32,
            timestamp=1704067200,
            bits=0x1d00ffff,
            nonce=0
        )
        self.assertEqual(len(header), 80)

    def test_ser_header_version(self):
        """Version is packed as little-endian uint32."""
        header = ser_header(1, b"\x00" * 32, b"\x00" * 32, 0, 0, 0)
        version = struct.unpack("<I", header[:4])[0]
        self.assertEqual(version, 1)

    def test_ser_header_prev_hash(self):
        """Previous hash is included correctly."""
        prev = bytes(range(32))
        header = ser_header(1, prev, b"\x00" * 32, 0, 0, 0)
        self.assertEqual(header[4:36], prev)

    def test_ser_header_merkle(self):
        """Merkle root is included correctly."""
        merkle = bytes(range(32, 64))
        header = ser_header(1, b"\x00" * 32, merkle, 0, 0, 0)
        self.assertEqual(header[36:68], merkle)

    def test_ser_header_timestamp_bits_nonce(self):
        """Timestamp, bits, and nonce are packed correctly."""
        header = ser_header(1, b"\x00" * 32, b"\x00" * 32,
                           1704067200, 0x1d00ffff, 12345)
        t, bits, nonce = struct.unpack("<III", header[68:80])
        self.assertEqual(t, 1704067200)
        self.assertEqual(bits, 0x1d00ffff)
        self.assertEqual(nonce, 12345)

    def test_header_hash(self):
        """Header hash is computed correctly."""
        header = ser_header(1, b"\x00" * 32, b"\x00" * 32, 0, 0, 0)
        hv = header_hash(header)
        expected = int.from_bytes(sha256d(header), "big")
        self.assertEqual(hv, expected)

    def test_header_hash_changes_with_nonce(self):
        """Different nonces produce different header hashes."""
        h1 = ser_header(1, b"\x00" * 32, b"\x00" * 32, 0, 0, 0)
        h2 = ser_header(1, b"\x00" * 32, b"\x00" * 32, 0, 0, 1)
        self.assertNotEqual(header_hash(h1), header_hash(h2))


class TestDifficultyBits(unittest.TestCase):
    """Test compact difficulty bits conversion."""

    def test_bits_to_target_min_difficulty(self):
        """Min difficulty bits (0x1d00ffff) conversion."""
        target = bits_to_target(0x1d00ffff)
        # 0x1d00ffff = exp=29, mant=0x00ffff
        # target = 0x00ffff << (8 * (29 - 3)) = 0x00ffff << 208
        expected = 0x00ffff << 208
        self.assertEqual(target, expected)

    def test_bits_to_target_exp_le_3(self):
        """Bits with exp <= 3 use right shift."""
        # 0x030000ff = exp=3, mant=0x0000ff
        # target = 0x0000ff >> (8 * (3 - 3)) = 0x0000ff
        target = bits_to_target(0x030000ff)
        self.assertEqual(target, 0xFF)

    def test_bits_to_target_exp_1(self):
        """Bits with exp=1."""
        # 0x010000ff = exp=1, mant=0x0000ff
        # target = 0x0000ff >> (8 * (3 - 1)) = 0x0000ff >> 16 = 0
        target = bits_to_target(0x010000ff)
        self.assertEqual(target, 0)

    def test_target_to_bits_roundtrip(self):
        """target_to_bits(bits_to_target(x)) == x for standard values."""
        for bits in [0x1d00ffff, 0x1d00abcd, 0x1c00ffff, 0x1b00ffff]:
            target = bits_to_target(bits)
            recovered = target_to_bits(target)
            self.assertEqual(recovered, bits,
                           f"Roundtrip failed for {bits:#010x}")

    def test_target_to_bits_zero(self):
        """Zero target returns 0."""
        self.assertEqual(target_to_bits(0), 0)

    def test_target_to_bits_negative(self):
        """Negative target returns 0."""
        self.assertEqual(target_to_bits(-1), 0)

    def test_calculate_difficulty_min(self):
        """Difficulty at min target is 1."""
        target = bits_to_target(0x1d00ffff)
        diff = calculate_difficulty(target)
        self.assertAlmostEqual(diff, 1.0, places=6)

    def test_calculate_difficulty_higher(self):
        """Higher difficulty has lower target."""
        target = bits_to_target(0x1d00ffff) // 2
        diff = calculate_difficulty(target)
        self.assertGreater(diff, 1.0)

    def test_diff1_constant(self):
        """DIFF1 constant is correct."""
        expected = 0x00000000FFFF0000000000000000000000000000000000000000000000000000
        self.assertEqual(DIFF1, expected)

    def test_max_target(self):
        """MAX_TARGET is 2^256 - 1."""
        self.assertEqual(MAX_TARGET, (1 << 256) - 1)


class TestMerkleRoot(unittest.TestCase):
    """Test merkle root computation."""

    def test_single_txid(self):
        """Single txid returns itself as root."""
        txid_bytes = b"\xab" * 32
        root = merkle_root([txid_bytes])
        self.assertEqual(root, txid_bytes)

    def test_two_txids(self):
        """Two txids produce correct merkle root."""
        t1 = b"\xaa" * 32
        t2 = b"\xbb" * 32
        root = merkle_root([t1, t2])
        expected = sha256d(t1 + t2)
        self.assertEqual(root, expected)

    def test_three_txids(self):
        """Three txids — third is duplicated."""
        t1 = b"\x01" * 32
        t2 = b"\x02" * 32
        t3 = b"\x03" * 32
        root = merkle_root([t1, t2, t3])
        # Level 1: sha256d(t1+t2), sha256d(t3+t3)
        l1 = sha256d(t1 + t2)
        l2 = sha256d(t3 + t3)
        expected = sha256d(l1 + l2)
        self.assertEqual(root, expected)

    def test_empty_list(self):
        """Empty list returns zero bytes."""
        root = merkle_root([])
        self.assertEqual(root, bytes(32))

    def test_txid_function(self):
        """txid() computes double SHA-256."""
        raw = b"test transaction"
        result = txid(raw)
        expected = sha256d(raw)
        self.assertEqual(result, expected)


class TestStratumMethod(unittest.TestCase):
    """Test Stratum method enum."""

    def test_subscribe(self):
        self.assertEqual(StratumMethod.SUBSCRIBE.value, "mining.subscribe")

    def test_authorize(self):
        self.assertEqual(StratumMethod.AUTHORIZE.value, "mining.authorize")

    def test_set_difficulty(self):
        self.assertEqual(StratumMethod.SET_DIFFICULTY.value,
                        "mining.set_difficulty")

    def test_notify(self):
        self.assertEqual(StratumMethod.NOTIFY.value, "mining.notify")

    def test_submit(self):
        self.assertEqual(StratumMethod.SUBMIT.value, "mining.submit")

    def test_extranonce_subscribe(self):
        self.assertEqual(StratumMethod.EXTRANONCE_SUBSCRIBE.value,
                        "mining.extranonce.subscribe")


class TestStratumMessage(unittest.TestCase):
    """Test Stratum JSON-RPC message serialization."""

    def test_request_to_json(self):
        """Request message serializes correctly."""
        msg = StratumMessage(
            method="mining.subscribe",
            params=[],
            msg_id=1
        )
        data = json.loads(msg.to_json())
        self.assertEqual(data["id"], 1)
        self.assertEqual(data["method"], "mining.subscribe")
        self.assertEqual(data["params"], [])

    def test_response_to_json(self):
        """Response message serializes correctly."""
        msg = StratumMessage(
            method="",
            result=True,
            msg_id=1
        )
        data = json.loads(msg.to_json())
        self.assertEqual(data["id"], 1)
        self.assertEqual(data["result"], True)
        self.assertIsNone(data["error"])

    def test_error_response_to_json(self):
        """Error response serializes correctly."""
        msg = StratumMessage(
            method="",
            result=False,
            error=[23, "low difficulty share"],
            msg_id=5
        )
        data = json.loads(msg.to_json())
        self.assertEqual(data["id"], 5)
        self.assertFalse(data["result"])
        self.assertEqual(data["error"], [23, "low difficulty share"])

    def test_notification_to_json(self):
        """Notification (no id) serializes correctly."""
        msg = StratumMessage(
            method="mining.notify",
            params=["job1", "prev", "cb1", "cb2", [], "01", "1d00ffff",
                    "65a0b0c0", True]
        )
        data = json.loads(msg.to_json())
        self.assertIsNone(data["id"])
        self.assertEqual(data["method"], "mining.notify")
        self.assertEqual(len(data["params"]), 9)

    def test_from_json_request(self):
        """Parse a request message."""
        json_str = '{"id": 1, "method": "mining.subscribe", "params": []}'
        msg = StratumMessage.from_json(json_str)
        self.assertEqual(msg.msg_id, 1)
        self.assertEqual(msg.method, "mining.subscribe")
        self.assertEqual(msg.params, [])

    def test_from_json_response(self):
        """Parse a response message."""
        json_str = '{"id": 1, "result": true, "error": null}'
        msg = StratumMessage.from_json(json_str)
        self.assertEqual(msg.msg_id, 1)
        self.assertTrue(msg.result)
        self.assertIsNone(msg.error)

    def test_from_json_notification(self):
        """Parse a notification message."""
        json_str = '{"id": null, "method": "mining.set_difficulty", ' \
                   '"params": [1.0]}'
        msg = StratumMessage.from_json(json_str)
        self.assertIsNone(msg.msg_id)
        self.assertEqual(msg.method, "mining.set_difficulty")
        self.assertEqual(msg.params, [1.0])


class TestMiningJob(unittest.TestCase):
    """Test mining job creation and verification."""

    def setUp(self):
        """Create a test mining job."""
        self.job = MiningJob(
            job_id="test-job-1",
            prev_hash=b"\x00" * 32,
            coinbase_1=b"\x00" * 100,
            coinbase_2=b"\x00" * 50,
            merkle_branches=[],
            version=1,
            bits=0x1d00ffff,
            ntime=1704067200,
            height=1,
            target=bits_to_target(0x1d00ffff),
            share_target=bits_to_target(0x1d00ffff),
            parent_time=1704067199
        )

    def test_job_id(self):
        """Job ID is preserved."""
        self.assertEqual(self.job.job_id, "test-job-1")

    def test_rebuild_header_length(self):
        """Rebuilt header is 80 bytes."""
        header = self.job.rebuild_header(
            b"\x00\x00\x00\x01", b"\x00\x00\x00\x01",
            1704067200, 0
        )
        self.assertEqual(len(header), 80)

    def test_rebuild_header_includes_prev_hash(self):
        """Rebuilt header includes the previous hash."""
        header = self.job.rebuild_header(
            b"\x00\x00\x00\x01", b"\x00\x00\x00\x01",
            1704067200, 0
        )
        self.assertEqual(header[4:36], b"\x00" * 32)

    def test_rebuild_header_version(self):
        """Rebuilt header has correct version."""
        header = self.job.rebuild_header(
            b"\x00\x00\x00\x01", b"\x00\x00\x00\x01",
            1704067200, 0
        )
        version = struct.unpack("<I", header[:4])[0]
        self.assertEqual(version, 1)

    def test_verify_solution(self):
        """Verify solution returns tuple of two booleans."""
        is_share, is_block = self.job.verify_solution(
            b"\x00\x00\x00\x01", b"\x00\x00\x00\x01",
            1704067200, 0
        )
        self.assertIsInstance(is_share, bool)
        self.assertIsInstance(is_block, bool)

    def test_verify_solution_block_implies_share(self):
        """If a solution is a block, it must also be a valid share."""
        is_share, is_block = self.job.verify_solution(
            b"\x00\x00\x00\x01", b"\x00\x00\x00\x01",
            1704067200, 0
        )
        if is_block:
            self.assertTrue(is_share)

    def test_difficulty(self):
        """Difficulty calculation."""
        diff = self.job.difficulty()
        self.assertAlmostEqual(diff, 1.0, places=6)

    def test_share_difficulty(self):
        """Share difficulty calculation."""
        share_diff = self.job.share_difficulty()
        self.assertAlmostEqual(share_diff, 1.0, places=6)

    def test_different_nonce_different_header(self):
        """Different nonces produce different headers."""
        h1 = self.job.rebuild_header(
            b"\x00\x00\x00\x01", b"\x00\x00\x00\x01",
            1704067200, 0
        )
        h2 = self.job.rebuild_header(
            b"\x00\x00\x00\x01", b"\x00\x00\x00\x01",
            1704067200, 1
        )
        self.assertNotEqual(h1, h2)

    def test_different_extranonce_different_header(self):
        """Different extranonces produce different headers."""
        h1 = self.job.rebuild_header(
            b"\x00\x00\x00\x01", b"\x00\x00\x00\x01",
            1704067200, 0
        )
        h2 = self.job.rebuild_header(
            b"\x00\x00\x00\x02", b"\x00\x00\x00\x01",
            1704067200, 0
        )
        self.assertNotEqual(h1, h2)

    def test_higher_difficulty_job(self):
        """Job with higher difficulty has lower target."""
        high_diff_target = bits_to_target(0x1d00ffff) // 10
        high_job = MiningJob(
            job_id="high-diff",
            prev_hash=b"\x00" * 32,
            coinbase_1=b"\x00" * 100,
            coinbase_2=b"\x00" * 50,
            merkle_branches=[],
            version=1,
            bits=0x1d00ffff,
            ntime=1704067200,
            height=1,
            target=high_diff_target,
            share_target=high_diff_target,
            parent_time=1704067199
        )
        self.assertGreater(high_job.difficulty(), self.job.difficulty())


class TestHashrateTracker(unittest.TestCase):
    """Test hashrate tracking and reporting."""

    def test_initial_hashrate(self):
        """Initial hashrate is 0."""
        tracker = HashrateTracker()
        self.assertEqual(tracker.current_hashrate(), 0.0)

    def test_record_hashes(self):
        """Recording hashes increases total."""
        tracker = HashrateTracker()
        tracker.record_hashes(1000)
        self.assertEqual(tracker.total_hashes, 1000)

    def test_record_multiple_batches(self):
        """Multiple batches accumulate."""
        tracker = HashrateTracker()
        tracker.record_hashes(1000)
        tracker.record_hashes(500)
        self.assertEqual(tracker.total_hashes, 1500)

    def test_current_hashrate_after_record(self):
        """Hashrate is calculated from recent samples."""
        tracker = HashrateTracker()
        tracker.record_hashes(1000)
        time.sleep(0.2)  # Ensure elapsed > 0.1s threshold
        hr = tracker.current_hashrate()
        self.assertGreater(hr, 0)

    def test_average_hashrate(self):
        """Average hashrate since start."""
        tracker = HashrateTracker()
        tracker.record_hashes(1000)
        time.sleep(0.2)  # Ensure elapsed > 0.1s threshold
        avg = tracker.average_hashrate()
        self.assertGreater(avg, 0)

    def test_format_hashrate_low(self):
        """Low hashrate formatted as H/s."""
        tracker = HashrateTracker()
        formatted = tracker.format_hashrate(500)
        self.assertIn("H/s", formatted)

    def test_format_hashrate_kilohash(self):
        """Kilohash range formatted as KH/s."""
        tracker = HashrateTracker()
        formatted = tracker.format_hashrate(5000)
        self.assertIn("KH/s", formatted)

    def test_format_hashrate_megahash(self):
        """Megahash range formatted as MH/s."""
        tracker = HashrateTracker()
        formatted = tracker.format_hashrate(5_000_000)
        self.assertIn("MH/s", formatted)

    def test_format_hashrate_gigahash(self):
        """Gigahash range formatted as GH/s."""
        tracker = HashrateTracker()
        formatted = tracker.format_hashrate(5_000_000_000)
        self.assertIn("GH/s", formatted)

    def test_cleanup_old_samples(self):
        """Old samples are cleaned up."""
        tracker = HashrateTracker(window_seconds=1)
        tracker.record_hashes(1000)
        time.sleep(1.1)
        tracker.record_hashes(100)
        # Old sample should be cleaned
        tracker._cleanup(time.time())
        self.assertEqual(len(tracker.hashrate_samples), 1)


class TestShareStats(unittest.TestCase):
    """Test share statistics tracking."""

    def test_initial_stats(self):
        """Initial stats are all zero."""
        stats = ShareStats()
        self.assertEqual(stats.accepted, 0)
        self.assertEqual(stats.rejected, 0)
        self.assertEqual(stats.blocks, 0)
        self.assertEqual(stats.stale, 0)

    def test_increment_accepted(self):
        """Accepted counter increments."""
        stats = ShareStats()
        stats.accepted += 1
        self.assertEqual(stats.accepted, 1)

    def test_increment_rejected(self):
        """Rejected counter increments."""
        stats = ShareStats()
        stats.rejected += 1
        self.assertEqual(stats.rejected, 1)

    def test_increment_blocks(self):
        """Blocks counter increments."""
        stats = ShareStats()
        stats.blocks += 1
        self.assertEqual(stats.blocks, 1)

    def test_to_dict(self):
        """to_dict returns correct structure."""
        stats = ShareStats(accepted=10, rejected=2, blocks=1, stale=0)
        d = stats.to_dict()
        self.assertEqual(d["accepted"], 10)
        self.assertEqual(d["rejected"], 2)
        self.assertEqual(d["blocks"], 1)
        self.assertEqual(d["total"], 13)

    def test_total_calculation(self):
        """Total is sum of accepted, rejected, and blocks."""
        stats = ShareStats(accepted=5, rejected=3, blocks=1)
        d = stats.to_dict()
        self.assertEqual(d["total"], 9)


class TestWordSwap(unittest.TestCase):
    """Test word-swap for Stratum protocol."""
    def test_wordswap_32_bytes(self):
        """Word-swap of 32 bytes reverses each 4-byte group."""
        from stratum_miner import StratumServer
        data = bytes(range(32))
        swapped = StratumServer._wordswap(data)
        # First 4 bytes should be reversed
        self.assertEqual(swapped[0], data[3])
        self.assertEqual(swapped[1], data[2])
        self.assertEqual(swapped[2], data[1])
        self.assertEqual(swapped[3], data[0])

    def test_wordswap_double_swap_identity(self):
        """Double word-swap returns original."""
        from stratum_miner import StratumServer
        data = bytes(range(32))
        swapped = StratumServer._wordswap(data)
        double_swapped = StratumServer._wordswap(swapped)
        self.assertEqual(double_swapped, data)


class TestDifficultyStrategy(unittest.TestCase):
    """Test difficulty adjustment strategy."""

    def test_bits_to_target_and_back(self):
        """Full roundtrip for various difficulty values."""
        test_bits = [
            0x1d00ffff,  # Bitcoin min difficulty
            0x1d00abcd,
            0x1c00ffff,
            0x1b00ffff,
            0x1a00ffff,
        ]
        for bits in test_bits:
            target = bits_to_target(bits)
            recovered = target_to_bits(target)
            self.assertEqual(recovered, bits,
                           f"Roundtrip failed for {bits:#010x}")

    def test_target_always_positive(self):
        """bits_to_target always returns positive for valid bits (exp >= 4)."""
        # Only test bits with exp >= 4; exp <= 3 can produce 0 target
        for exp in range(4, 20):
            bits = (exp << 24) | 0x0000ff
            target = bits_to_target(bits)
            self.assertGreater(target, 0, f"Target should be > 0 for bits={bits:#010x}")

    def test_difficulty_increases_as_target_decreases(self):
        """Higher difficulty means lower target."""
        t1 = bits_to_target(0x1d00ffff)
        t2 = bits_to_target(0x1d00ffff) // 2
        d1 = calculate_difficulty(t1)
        d2 = calculate_difficulty(t2)
        self.assertGreater(d2, d1)


class TestIntegration(unittest.TestCase):
    """Integration tests for mining flow."""

    def test_full_mining_job_flow(self):
        """Create job, rebuild header, verify solution."""
        job = MiningJob(
            job_id="integration-test",
            prev_hash=b"\xaa" * 32,
            coinbase_1=b"\x00" * 100,
            coinbase_2=b"\x00" * 50,
            merkle_branches=[],
            version=1,
            bits=0x1d00ffff,
            ntime=1704067200,
            height=100,
            target=bits_to_target(0x1d00ffff),
            share_target=bits_to_target(0x1d00ffff),
            parent_time=1704067199
        )

        # Rebuild header
        header = job.rebuild_header(
            b"\x00\x00\x00\x01", b"\x00\x00\x00\x01",
            1704067200, 42
        )
        self.assertEqual(len(header), 80)

        # Verify solution
        is_share, is_block = job.verify_solution(
            b"\x00\x00\x00\x01", b"\x00\x00\x00\x01",
            1704067200, 42
        )
        self.assertIsInstance(is_share, bool)
        self.assertIsInstance(is_block, bool)

    def test_hashrate_tracking_with_mining(self):
        """Hashrate tracker records mining hashes."""
        tracker = HashrateTracker()

        # Simulate mining batches
        for _ in range(10):
            tracker.record_hashes(1000)

        self.assertEqual(tracker.total_hashes, 10000)
        self.assertGreater(tracker.current_hashrate(), 0)

    def test_share_stats_tracking(self):
        """Share stats track mining results."""
        stats = ShareStats()

        # Simulate mining results
        stats.accepted += 5
        stats.rejected += 1
        stats.blocks += 1

        d = stats.to_dict()
        self.assertEqual(d["accepted"], 5)
        self.assertEqual(d["rejected"], 1)
        self.assertEqual(d["blocks"], 1)
        self.assertEqual(d["total"], 7)

    def test_stratum_message_roundtrip(self):
        """Message can be serialized and deserialized."""
        original = StratumMessage(
            method="mining.notify",
            params=["job1", "prev_hash_hex", "cb1", "cb2", [],
                    "00000001", "1d00ffff", "65a0b0c0", True],
            msg_id=None
        )

        json_str = original.to_json()
        parsed = StratumMessage.from_json(json_str)

        self.assertEqual(parsed.method, "mining.notify")
        self.assertEqual(len(parsed.params), 9)
        self.assertEqual(parsed.params[0], "job1")

    def test_merkle_root_for_coinbase_only(self):
        """Merkle root with single coinbase tx."""
        coinbase = b"\x00" * 200  # Simulated coinbase tx
        root = merkle_root([txid(coinbase)])
        self.assertEqual(root, txid(coinbase))
        self.assertEqual(len(root), 32)


if __name__ == "__main__":
    unittest.main()
