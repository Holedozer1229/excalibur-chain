"""Regression tests for strict Bitcoin snapshot v2 import."""
import hashlib
import os
import struct
import tempfile
import unittest

from utxodb import SnapshotDB, UtxoSet, _sha256d_file, build_snapshot_db


MAGIC = 0x45425346


def varint(n):
    if n < 0xfd:
        return bytes([n])
    if n <= 0xffff:
        return b"\\xfd" + struct.pack("<H", n)
    if n <= 0xffffffff:
        return b"\\xfe" + struct.pack("<I", n)
    return b"\\xff" + struct.pack("<Q", n)


def snapshot_bytes(height=968698, version=2, trailing=b""):
    # Spendable coinbase output, followed by an unspendable ordinary output.
    rows = [
        (b"\\x11" * 32, 0, 5_000_000_000, b"\\x51", 1, 1, 900000),
        (b"\\x22" * 32, 1, 1234, b"\\x6a", 0, 0, 0),
    ]
    out = bytearray(struct.pack("<IIIQ", MAGIC, version, height, len(rows)))
    for txid, vout, value, script, spendable, is_cb, cb_h in rows:
        out += txid + struct.pack("<IQ", vout, value)
        out += varint(len(script)) + script
        out += bytes([spendable, is_cb]) + struct.pack("<I", cb_h)
    return bytes(out) + trailing


class SnapshotV2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dat = os.path.join(self.tmp.name, "snapshot.dat")
        self.db = os.path.join(self.tmp.name, "utxo.db")

    def tearDown(self):
        self.tmp.cleanup()

    def write_snapshot(self, raw):
        with open(self.dat, "wb") as f:
            f.write(raw)
        return _sha256d_file(self.dat)

    def test_import_preserves_coinbase_and_filters_unspendable(self):
        digest = self.write_snapshot(snapshot_bytes())
        count, total = build_snapshot_db(
            self.dat, self.db, digest, 968698, log=lambda _msg: None)
        self.assertEqual(count, 2)
        self.assertEqual(total, 5_000_001_234)

        snap = SnapshotDB(self.db)
        try:
            spendable_count, spendable_total = snap.stats()
            self.assertEqual((spendable_count, spendable_total),
                             (1, 5_000_000_000))
            key = (b"\\x11" * 32, 0)
            self.assertEqual(snap.get(key), [(5_000_000_000, b"\\x51", 1, 900000)])
            self.assertIsNone(snap.get((b"\\x22" * 32, 1)))
            self.assertEqual(len(snap.find_by_spk(b"\\x51")), 1)
            self.assertEqual(snap.find_by_spk(b"\\x6a"), [])
            self.assertEqual(len(list(UtxoSet(snapshot=snap).items())), 1)
        finally:
            snap.close()

    def test_embedded_height_must_match_expected_anchor(self):
        digest = self.write_snapshot(snapshot_bytes(height=968697))
        with self.assertRaisesRegex(ValueError, "height mismatch"):
            build_snapshot_db(
                self.dat, self.db, digest, 968698, log=lambda _msg: None)

    def test_v1_rejected_because_coinbase_lineage_is_missing(self):
        digest = self.write_snapshot(snapshot_bytes(version=1))
        with self.assertRaisesRegex(ValueError, "v2 required"):
            build_snapshot_db(
                self.dat, self.db, digest, 968698, log=lambda _msg: None)

    def test_trailing_bytes_rejected(self):
        digest = self.write_snapshot(snapshot_bytes(trailing=b"junk"))
        with self.assertRaisesRegex(ValueError, "trailing bytes"):
            build_snapshot_db(
                self.dat, self.db, digest, 968698, log=lambda _msg: None)


if __name__ == "__main__":
    unittest.main()
