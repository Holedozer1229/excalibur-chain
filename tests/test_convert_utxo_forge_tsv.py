"""Tests for the UTXO TSV -> snapshot-v2 format adapter."""
import hashlib
import json
import os
import struct
import subprocess
import sys
import tempfile
import unittest


SCRIPT = os.path.join(os.path.dirname(__file__), "..", "scripts",
                      "convert_utxo_forge_tsv.py")
HEADER = "txid\tvout\tvalue_sats\theight\tcoinbase\tscript_type\taddress\tscript_pub_key\n"


class ConverterTests(unittest.TestCase):
    def test_converts_txid_script_and_coinbase_lineage(self):
        with tempfile.TemporaryDirectory() as td:
            archive = os.path.join(td, "source.zst")
            tsv = os.path.join(td, "source.tsv")
            manifest = os.path.join(td, "manifest.json")
            output = os.path.join(td, "snapshot.dat")
            with open(archive, "wb") as f:
                f.write(b"immutable-source-archive")
            txid = "11" * 32
            with open(tsv, "w", encoding="utf-8") as f:
                f.write(HEADER)
                f.write(f"{txid}\t2\t5000000000\t900000\t1\tp2pkh\t\t76a914\n")
            with open(manifest, "w", encoding="utf-8") as f:
                json.dump({
                    "height": 968698,
                    "block_hash": "ab" * 32,
                    "row_count": 1,
                    "sha256": hashlib.sha256(open(archive, "rb").read()).hexdigest()
                }, f)
            subprocess.run([
                sys.executable, SCRIPT, tsv, output,
                "--source-archive", archive,
                "--height", "968698",
                "--block-hash", "ab" * 32,
                "--manifest", manifest
            ], check=True, capture_output=True, text=True)
            with open(output, "rb") as f:
                raw = f.read()
            magic, version, height, count = struct.unpack("<IIIQ", raw[:20])
            self.assertEqual((magic, version, height, count),
                             (0x45425346, 2, 968698, 1))
            self.assertEqual(raw[20:52], bytes.fromhex(txid)[::-1])
            self.assertEqual(struct.unpack("<IQ", raw[52:64]), (2, 5000000000))
            self.assertEqual(raw[64], 1)  # one-byte script length
            self.assertEqual(raw[65:68], bytes.fromhex("76a914"))
            self.assertEqual(raw[68:70], bytes([1, 1]))
            self.assertEqual(struct.unpack("<I", raw[70:74])[0], 900000)

    def test_rejects_wrong_anchor_height(self):
        with tempfile.TemporaryDirectory() as td:
            archive = os.path.join(td, "source.zst")
            tsv = os.path.join(td, "source.tsv")
            manifest = os.path.join(td, "manifest.json")
            with open(archive, "wb") as f:
                f.write(b"x")
            with open(tsv, "w", encoding="utf-8") as f:
                f.write(HEADER)
            with open(manifest, "w", encoding="utf-8") as f:
                json.dump({"height": 968697, "block_hash": "ab" * 32,
                           "row_count": 0, "sha256": hashlib.sha256(b"x").hexdigest()}, f)
            result = subprocess.run([
                sys.executable, SCRIPT, tsv, os.path.join(td, "out.dat"),
                "--source-archive", archive, "--height", "968697",
                "--block-hash", "ab" * 32, "--manifest", manifest
            ], capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
