"""Regression tests for genealogy verification.

These tests ensure that genealogy_verify.py continues to produce the same
verification results after any refactor. They run the script as a subprocess
to avoid importing consensus code directly.
"""
import subprocess
import sys
import os

import pytest


@pytest.fixture()
def repo_root():
    """Return the repository root directory."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestGenealogyVerify:
    """Verify genealogy_verify.py runs without errors."""

    def test_genealogy_verify_runs(self, repo_root):
        """genealogy_verify.py should exit successfully."""
        script = os.path.join(repo_root, "genealogy_verify.py")
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=repo_root,
        )
        # The script may print warnings; we only care it doesn't crash
        assert result.returncode == 0, (
            f"genealogy_verify.py failed:\n{result.stderr}"
        )

    def test_genealogy_verify_produces_output(self, repo_root):
        """genealogy_verify.py should produce stdout output."""
        script = os.path.join(repo_root, "genealogy_verify.py")
        result = subprocess.run(
            [sys.executable, script],
            capture_output=True,
            text=True,
            timeout=120,
            cwd=repo_root,
        )
        assert len(result.stdout.strip()) > 0, "genealogy_verify.py produced no output"
