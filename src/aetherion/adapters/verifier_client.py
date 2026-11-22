"""verifier_client.py — subprocess wrapper for genealogy_verify.py.

Runs genealogy_verify.py as a subprocess so the adapter never imports
consensus code directly. Parses stdout for verification results.
"""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Any


class VerifierError(Exception):
    """Raised when genealogy verification fails."""


class VerifierClient:
    """Runs genealogy_verify.py as a subprocess and parses output.

    Usage:
        client = VerifierClient()
        result = client.verify()
        print(result["status"])  # "ok" or "error"
    """

    def __init__(self, timeout: int = 120) -> None:
        self.timeout = timeout
        # Locate genealogy_verify.py relative to this file
        self._script = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
                os.path.abspath(__file__)
            )))),
            "genealogy_verify.py",
        )

    def verify(self) -> dict[str, Any]:
        """Run genealogy_verify.py and return structured results.

        Returns:
            {
                "status": "ok" | "error" | "timeout",
                "output": str,           # stdout
                "errors": str,           # stderr
                "returncode": int | None,
            }
        """
        if not os.path.exists(self._script):
            return {
                "status": "error",
                "output": "",
                "errors": f"genealogy_verify.py not found at {self._script}",
                "returncode": None,
            }

        try:
            result = subprocess.run(
                [sys.executable, self._script],
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            status = "ok" if result.returncode == 0 else "error"
            return {
                "status": status,
                "output": result.stdout,
                "errors": result.stderr,
                "returncode": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {
                "status": "timeout",
                "output": "",
                "errors": f"Verification timed out after {self.timeout}s",
                "returncode": None,
            }

    def is_chain_valid(self) -> bool:
        """Return True if the chain passes genealogy verification."""
        result = self.verify()
        return result["status"] == "ok"
