"""Canonical, signed, reproducible evidence attestations.

An attestation is a signed statement plus commitments to its inputs, method,
and evidence. Verification never treats an AI-generated claim as ground truth.
A trusted issuer key establishes who signed; deterministic recomputation and
evidence review establish whether the claim is supported.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
import time
from typing import Any, Mapping

SCHEMA = "aetherion.avta.v1"
RESULTS = {"verified", "rejected", "inconclusive", "disputed"}
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_NONCE = re.compile(r"^[0-9a-f]{32,128}$")
_REQUIRED = {
    "schema", "claim", "method", "inputs_sha256", "result",
    "evidence_sha256", "counterexample_sha256", "issued_at",
    "expires_at", "nonce", "issuer_id", "signature",
}


class AttestationError(ValueError):
    """Raised when an attestation cannot be safely canonicalized or signed."""


def _validate_json_value(value: Any, path: str = "$") -> None:
    # bool must be checked before int because bool subclasses int in Python.
    if value is None or isinstance(value, (bool, str, int)):
        return
    if isinstance(value, float):
        raise AttestationError(f"floating-point values are forbidden at {path}")
    if isinstance(value, list):
        for i, item in enumerate(value):
            _validate_json_value(item, f"{path}[{i}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise AttestationError(f"non-string object key at {path}")
            _validate_json_value(item, f"{path}.{key}")
        return
    raise AttestationError(f"unsupported JSON value at {path}: {type(value).__name__}")


def canonical_json(value: Any) -> bytes:
    """UTF-8 JSON with sorted keys; no floats, NaN, or non-JSON objects."""
    _validate_json_value(value)
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8", errors="strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise AttestationError(f"canonical JSON failure: {exc}") from exc


def digest(value: Any) -> str:
    """SHA-256 of the canonical JSON representation of value."""
    return hashlib.sha256(canonical_json(value)).hexdigest()


def _unsigned_payload(attestation: Mapping[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in attestation.items() if key != "signature"}


def sign_attestation(payload: Mapping[str, Any], private_key: Any) -> dict[str, Any]:
    """Sign a complete unsigned AVTA payload with an Ed25519 private key.

    The private key object must expose the cryptography Ed25519 .sign(bytes)
    method. Key custody is deliberately left to the calling application.
    """
    if "signature" in payload:
        raise AttestationError("payload must not contain a signature field")
    unsigned = dict(payload)
    _validate_unsigned(unsigned)
    try:
        signature = private_key.sign(canonical_json(unsigned))
    except Exception as exc:
        raise AttestationError(f"Ed25519 signing failed: {exc}") from exc
    signed = dict(unsigned)
    signed["signature"] = base64.b64encode(signature).decode("ascii")
    return signed


def _validate_unsigned(payload: Mapping[str, Any]) -> None:
    expected = _REQUIRED - {"signature"}
    if set(payload) != expected:
        missing = sorted(expected - set(payload))
        extra = sorted(set(payload) - expected)
        raise AttestationError(f"wrong payload fields; missing={missing}, extra={extra}")
    if payload["schema"] != SCHEMA:
        raise AttestationError("unsupported schema")
    if not isinstance(payload["claim"], str) or not payload["claim"].strip():
        raise AttestationError("claim must be a non-empty string")
    if len(payload["claim"].encode("utf-8")) > 4096:
        raise AttestationError("claim exceeds 4096 UTF-8 bytes")
    method = payload["method"]
    if not isinstance(method, dict) or set(method) != {"id", "version", "sha256"}:
        raise AttestationError("method must contain exactly id, version, sha256")
    for name in ("id", "version"):
        if not isinstance(method[name], str) or not method[name].strip():
            raise AttestationError(f"method.{name} must be non-empty")
    if not isinstance(method["sha256"], str) or not _HEX64.fullmatch(method["sha256"]):
        raise AttestationError("method.sha256 must be lowercase SHA-256 hex")
    for name in ("inputs_sha256", "evidence_sha256"):
        if not isinstance(payload[name], str) or not _HEX64.fullmatch(payload[name]):
            raise AttestationError(f"{name} must be lowercase SHA-256 hex")
    counter = payload["counterexample_sha256"]
    if counter is not None and (not isinstance(counter, str) or not _HEX64.fullmatch(counter)):
        raise AttestationError("counterexample_sha256 must be null or lowercase SHA-256 hex")
    if payload["result"] not in RESULTS:
        raise AttestationError("result must be one of: " + ", ".join(sorted(RESULTS)))
    for name in ("issued_at", "expires_at"):
        # Exact int excludes bool.
        if type(payload[name]) is not int or payload[name] < 0:
            raise AttestationError(f"{name} must be a non-negative integer Unix timestamp")
    if payload["expires_at"] <= payload["issued_at"]:
        raise AttestationError("expires_at must be later than issued_at")
    if not isinstance(payload["nonce"], str) or not _NONCE.fullmatch(payload["nonce"]):
        raise AttestationError("nonce must be 32-128 lowercase hex characters")
    if not isinstance(payload["issuer_id"], str) or not payload["issuer_id"].strip():
        raise AttestationError("issuer_id must be non-empty")


def verify_attestation(
    attestation: Mapping[str, Any],
    *,
    inputs: Any,
    evidence: Any,
    method_source: bytes,
    trusted_issuers: Mapping[str, bytes],
    counterexample: Any = None,
    now: int | None = None,
) -> dict[str, Any]:
    """Verify schema, commitments, time bounds, and a trusted Ed25519 signature.

    trusted_issuers maps issuer_id to the raw 32-byte Ed25519 public key.
    Missing trust is INCONCLUSIVE, not a successful verification.
    """
    checks: list[dict[str, str]] = []

    def check(name: str, ok: bool, detail: str) -> None:
        checks.append({"check": name, "status": "pass" if ok else "fail", "detail": detail})

    try:
        if not isinstance(attestation, Mapping) or set(attestation) != _REQUIRED:
            raise AttestationError("attestation fields do not match AVTA v1 schema")
        unsigned = _unsigned_payload(attestation)
        _validate_unsigned(unsigned)
        if not isinstance(method_source, bytes):
            raise AttestationError("method_source must be raw bytes")
        if not isinstance(attestation["signature"], str):
            raise AttestationError("signature must be base64 text")
        signature = base64.b64decode(attestation["signature"], validate=True)
        if len(signature) != 64:
            raise AttestationError("Ed25519 signature must be 64 bytes")
        check("schema", True, SCHEMA)
        check("method", hashlib.sha256(method_source).hexdigest() == unsigned["method"]["sha256"],
              "method source digest matches" if hashlib.sha256(method_source).hexdigest() == unsigned["method"]["sha256"] else "method source digest mismatch")
        in_ok = digest(inputs) == unsigned["inputs_sha256"]
        check("inputs", in_ok, "input commitment matches" if in_ok else "input commitment mismatch")
        ev_ok = digest(evidence) == unsigned["evidence_sha256"]
        check("evidence", ev_ok, "evidence commitment matches" if ev_ok else "evidence commitment mismatch")
        expected_counter = unsigned["counterexample_sha256"]
        if expected_counter is None:
            counter_ok = counterexample is None
        else:
            counter_ok = counterexample is not None and digest(counterexample) == expected_counter
        check("counterexample", counter_ok, "counterexample commitment matches" if counter_ok else "counterexample commitment mismatch")
        clock = int(time.time()) if now is None else now
        if type(clock) is not int or clock < 0:
            raise AttestationError("now must be a non-negative integer timestamp")
        time_ok = unsigned["issued_at"] <= clock < unsigned["expires_at"]
        check("time_window", time_ok, "attestation is within its validity window" if time_ok else "attestation is not currently valid")
        issuer_key = trusted_issuers.get(unsigned["issuer_id"])
        if issuer_key is None:
            check("issuer", False, "issuer key is not in the local trust registry")
            return {
                "status": "inconclusive",
                "reason": "untrusted_issuer",
                "checks": checks,
                "attestation_sha256": hashlib.sha256(canonical_json(dict(attestation))).hexdigest(),
                "claimed_result": unsigned["result"],
            }
        if not isinstance(issuer_key, bytes) or len(issuer_key) != 32:
            raise AttestationError("trusted issuer key must be 32 raw bytes")
        try:
            from cryptography.exceptions import InvalidSignature
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
            Ed25519PublicKey.from_public_bytes(issuer_key).verify(
                signature, canonical_json(unsigned)
            )
            sig_ok = True
        except ImportError:
            check("signature", False, "cryptography package unavailable")
            return {
                "status": "inconclusive",
                "reason": "crypto_dependency_unavailable",
                "checks": checks,
                "attestation_sha256": hashlib.sha256(canonical_json(dict(attestation))).hexdigest(),
                "claimed_result": unsigned["result"],
            }
        except InvalidSignature:
            sig_ok = False
        check("signature", sig_ok, "trusted Ed25519 signature valid" if sig_ok else "signature invalid")
        all_ok = all(item["status"] == "pass" for item in checks)
        return {
            "status": "valid" if all_ok else "invalid",
            "reason": None if all_ok else "one_or_more_checks_failed",
            "checks": checks,
            "attestation_sha256": hashlib.sha256(canonical_json(dict(attestation))).hexdigest(),
            "claimed_result": unsigned["result"],
        }
    except (AttestationError, TypeError, ValueError, KeyError, binascii.Error) as exc:
        checks.append({"check": "structure", "status": "fail", "detail": str(exc)})
        return {
            "status": "invalid",
            "reason": "malformed_attestation",
            "checks": checks,
            "attestation_sha256": None,
            "claimed_result": None,
        }
