"""End-to-end tests for the offline PCBE CLI (``python3 -m pcbe.cli``)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_cli(*args):
    return subprocess.run([sys.executable, "-m", "pcbe.cli", *args],
                          cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)


class CLITests(unittest.TestCase):
    def test_example_bundle_verifies_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "bundle.json"
            result = run_cli("example", "--out", str(bundle))
            self.assertEqual(result.returncode, 0, result.stderr)
            result = run_cli("verify", "--bundle", str(bundle), "--now", "1800000000")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["outcome"], "VALID")
            self.assertEqual(report["event_digest"],
                             "83e67afa323b48091c595af5b2c9494bc48a387e67e4c3d0bba141405cb6bf19")

    def test_tampered_bundle_exits_1_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "bundle.json"
            self.assertEqual(run_cli("example", "--out", str(bundle)).returncode, 0)
            data = json.loads(bundle.read_text(encoding="utf-8"))
            data["event"]["claims"]["invoice_total_minor"] = 99999
            bundle.write_text(json.dumps(data), encoding="utf-8")
            result = run_cli("verify", "--bundle", str(bundle), "--now", "1800000000")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["outcome"], "INVALID")

    def test_malformed_bundle_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "bundle.json"
            bundle.write_text("{not json", encoding="utf-8")
            result = run_cli("verify", "--bundle", str(bundle), "--now", "1800000000")
            self.assertEqual(result.returncode, 2)
            self.assertIn("invalid bundle", result.stderr)

    def test_missing_bundle_file_exits_2(self):
        result = run_cli("verify", "--bundle", "/tmp/does-not-exist-pcbe.json")
        self.assertEqual(result.returncode, 2)

    def test_verify_without_now_uses_wall_clock(self):
        # The fixed example is dated 2027-01-15, so at the real wall clock
        # it is not yet valid: the CLI must report INVALID, not crash.
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "bundle.json"
            self.assertEqual(run_cli("example", "--out", str(bundle)).returncode, 0)
            result = run_cli("verify", "--bundle", str(bundle))
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["outcome"], "INVALID")


if __name__ == "__main__":
    unittest.main()
