import hashlib
import os
import struct
import tempfile
import unittest

from utxodb import MAGIC, SnapshotDB, UtxoSet, build_snapshot_db


def varint(n):
    if n < 0xfd:
        return bytes([n])
    if n <= 0xffff:
        return b"\xfd" + struct.pack("<H", n)
    if n <= 0xffffffff:
        return b"\xfe" + struct.pack("<I", n)
    return b"\xff" + struct.pack("<Q", n)


def record(txid, vout, value, script, flags, coinbase_height):
    return (txid + struct.pack("<I", vout) + struct.pack("<Q", value)
            + varint(len(script)) + script + bytes([flags])
            + struct.pack("<I", coinbase_height))


def snapshot_bytes(height=968698, version=2, records=None, suffix=b""):
    records = records or []
    return (struct.pack("<IIIQ", MAGIC, version, height, len(records))
            + b"".join(records) + suffix)


def sha256d(data):
    return hashlib.sha256(hashlib.sha256(data).digest()).hexdigest()


class SnapshotV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dat = os.path.join(self.tmp.name, "snapshot.dat")
        self.db_path = os.path.join(self.tmp.name, "utxo.db")

    def write_snapshot(self, data):
        with open(self.dat, "wb") as f:
            f.write(data)
        return sha256d(data)

    def build(self, data, expected_height=968698):
        digest = self.write_snapshot(data)
        return build_snapshot_db(self.dat, self.db_path, digest,
                                  expected_height, log=lambda _msg: None)

    def test_coinbase_provenance_and_spendability_are_preserved(self):
        cb_txid = bytes.fromhex("11" * 32)
        unspendable_txid = bytes.fromhex("22" * 32)
        lock = b"\x51"
        data = snapshot_bytes(records=[
            record(cb_txid, 0, 5_000_000_000, lock, 0b11, 968600),
            record(unspendable_txid, 1, 1_000, b"\x6a", 0b00, 0),
        ])
        self.build(data)

        snap = SnapshotDB(self.db_path)
        self.addCleanup(snap.close)
        self.assertEqual(snap.get((cb_txid, 0)),
                         [(5_000_000_000, lock, 1, 968600)])
        self.assertIsNone(snap.get((unspendable_txid, 1)))
        self.assertEqual(snap.get_any((unspendable_txid, 1)),
                         (1_000, b"\x6a", 0, 0, 0))
        self.assertEqual(snap.stats(), (1, 5_000_000_000))
        self.assertEqual(snap.stats_all(), (2, 5_000_001_000))
        self.assertEqual(len(snap.find_by_spk(b"\x6a")), 0)

        view = UtxoSet(snapshot=snap)
        self.assertNotIn((unspendable_txid, 1), view)
        with self.assertRaisesRegex(AssertionError, "duplicate output"):
            view.setdefault((unspendable_txid, 1), [(1, b"\x51", False, 0)])

    def test_embedded_height_must_match_metadata_height(self):
        data = snapshot_bytes(height=968697)
        with self.assertRaisesRegex(ValueError, "height mismatch"):
            self.build(data, expected_height=968698)
        self.assertFalse(os.path.exists(self.db_path))

    def test_v1_is_rejected_because_coinbase_metadata_is_missing(self):
        data = snapshot_bytes(version=1)
        with self.assertRaisesRegex(ValueError, "v2 required"):
            self.build(data)

    def test_reserved_flag_bits_are_rejected(self):
        data = snapshot_bytes(records=[
            record(b"\x33" * 32, 0, 1, b"\x51", 0b100, 0),
        ])
        with self.assertRaisesRegex(ValueError, "reserved snapshot flags"):
            self.build(data)

    def test_non_coinbase_record_cannot_claim_coinbase_height(self):
        data = snapshot_bytes(records=[
            record(b"\x44" * 32, 0, 1, b"\x51", 0b01, 1),
        ])
        with self.assertRaisesRegex(ValueError, "non-coinbase"):
            self.build(data)

    def test_coinbase_height_cannot_exceed_snapshot_height(self):
        data = snapshot_bytes(records=[
            record(b"\x55" * 32, 0, 1, b"\x51", 0b11, 968699),
        ])
        with self.assertRaisesRegex(ValueError, "above snapshot height"):
            self.build(data)

    def test_truncated_record_and_trailing_bytes_are_rejected(self):
        truncated = snapshot_bytes(records=[
            record(b"\x66" * 32, 0, 1, b"\x51", 0b01, 0)[:-2],
        ])
        with self.assertRaisesRegex(ValueError, "truncated snapshot"):
            self.build(truncated)

        trailing = snapshot_bytes(suffix=b"\x00")
        with self.assertRaisesRegex(ValueError, "trailing bytes"):
            self.build(trailing)

    def test_failed_rebuild_does_not_destroy_existing_database(self):
        good = snapshot_bytes(records=[
            record(b"\x77" * 32, 0, 1, b"\x51", 0b01, 0),
        ])
        self.build(good)
        with open(self.db_path, "rb") as f:
            original = f.read()

        bad = snapshot_bytes(version=1)
        digest = self.write_snapshot(bad)
        with self.assertRaisesRegex(ValueError, "v2 required"):
            build_snapshot_db(self.dat, self.db_path, digest, 968698,
                              log=lambda _msg: None)
        with open(self.db_path, "rb") as f:
            self.assertEqual(f.read(), original)


if __name__ == "__main__":
    unittest.main()
