"""Command-line verifier for AVTA envelopes exported by external systems.

The trusted issuer registry is local operator configuration. Public keys are
lowercase hex-encoded raw Ed25519 public keys (32 bytes); no private key is
read or stored by this command.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from .core import verify_attestation

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def _read_json(path: str) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot read JSON file {path}: {exc}") from exc


def _trusted_issuers(path: str) -> dict[str, bytes]:
    raw = _read_json(path)
    if not isinstance(raw, dict):
        raise ValueError("trusted issuer registry must be a JSON object")
    result: dict[str, bytes] = {}
    for issuer, encoded in raw.items():
        if not isinstance(issuer, str) or not issuer.strip():
            raise ValueError("issuer IDs must be non-empty strings")
        if not isinstance(encoded, str) or not _HEX64.fullmatch(encoded):
            raise ValueError(f"public key for {issuer!r} must be 64 lowercase hex characters")
        result[issuer] = bytes.fromhex(encoded)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify a signed AVTA v1 envelope exported by Aetherion or another observer"
    )
    parser.add_argument("--attestation", required=True, help="signed AVTA envelope JSON")
    parser.add_argument("--inputs", required=True, help="committed inputs JSON")
    parser.add_argument("--evidence", required=True, help="committed evidence JSON")
    parser.add_argument("--method-source", required=True, help="exact method source bytes used by issuer")
    parser.add_argument("--trusted-issuers", required=True, help="local JSON map: issuer_id -> raw Ed25519 public key hex")
    parser.add_argument("--counterexample", help="optional committed counterexample JSON")
    parser.add_argument("--now", type=int, help="override Unix time for deterministic tests")
    args = parser.parse_args()

    try:
        attestation = _read_json(args.attestation)
        inputs = _read_json(args.inputs)
        evidence = _read_json(args.evidence)
        counterexample = _read_json(args.counterexample) if args.counterexample else None
        method_source = Path(args.method_source).read_bytes()
        trusted = _trusted_issuers(args.trusted_issuers)
        result = verify_attestation(
            attestation,
            inputs=inputs,
            evidence=evidence,
            method_source=method_source,
            trusted_issuers=trusted,
            counterexample=counterexample,
            now=args.now,
        )
    except (OSError, ValueError) as exc:
        parser.exit(2, f"AVTA input error: {exc}\n")

    print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
    return 0 if result["status"] == "valid" else 1


if __name__ == "__main__":
    raise SystemExit(main())
