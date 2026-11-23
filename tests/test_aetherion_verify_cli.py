import json
import tempfile
import unittest
from pathlib import Path

from aetherion_verifier.verify_cli import _trusted_issuers


class VerifyCliTests(unittest.TestCase):
    def test_reads_raw_ed25519_public_key_hex(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "issuers.json"
            path.write_text(json.dumps({"auditor-1": "ab" * 32}), encoding="utf-8")
            self.assertEqual(_trusted_issuers(str(path))["auditor-1"], bytes.fromhex("ab" * 32))

    def test_rejects_malformed_public_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "issuers.json"
            path.write_text(json.dumps({"auditor-1": "not-a-key"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                _trusted_issuers(str(path))


if __name__ == "__main__":
    unittest.main()
