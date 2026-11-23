"""EXCAL Proof-Carrying Business Events v1 reference verifier.

Application-layer only. This module does not interact with consensus, wallets,
transaction signing, or payment authorization. It implements a deliberately
small deterministic-CBOR profile and Ed25519 attestations.
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Mapping

try:
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
except ImportError:  # Verification fails closed when the optional dependency is absent.
    InvalidSignature = Exception
    Ed25519PublicKey = None


PROTOCOL = "excal.pcbe"
VERSION = 1
EVENT_DOMAIN = b"EXCAL-PCBE-EVENT-v1"
EVIDENCE_DOMAIN = b"EXCAL-PCBE-EVIDENCE-v1"
ATTESTATION_DOMAIN = b"EXCAL-PCBE-ATTESTATION-v1"
REPORT_DOMAIN = b"EXCAL-PCBE-REPORT-v1"
OUTCOMES = {"VALID", "INVALID", "INCOMPLETE", "EXPIRED", "REVOKED",
            "DISPUTED", "UNVERIFIABLE"}
EVENT_FIELDS = {
    "protocol", "version", "network", "event_id", "event_type",
    "subject_commitment", "claims", "evidence", "policy_id", "issued_at",
    "expires_at", "nonce", "predecessors", "attachments_root",
}
SIGNATURE_FIELDS = {"key_id", "role", "policy_version", "signature"}


class PCBEError(ValueError):
    """Malformed or unsupported PCBE input."""


def _head(major: int, value: int) -> bytes:
    if value < 0:
        raise PCBEError("negative CBOR length")
    prefix = major << 5
    if value < 24:
        return bytes([prefix | value])
    if value <= 0xFF:
        return bytes([prefix | 24, value])
    if value <= 0xFFFF:
        return bytes([prefix | 25]) + value.to_bytes(2, "big")
    if value <= 0xFFFFFFFF:
        return bytes([prefix | 26]) + value.to_bytes(4, "big")
    if value <= 0xFFFFFFFFFFFFFFFF:
        return bytes([prefix | 27]) + value.to_bytes(8, "big")
    raise PCBEError("integer outside deterministic CBOR uint64 range")


def canonical_cbor(value: Any) -> bytes:
    """Encode the supported data model using RFC 8949 deterministic ordering.

    Supported values: null, bool, signed integers, byte/text strings, arrays,
    and maps with text-string keys. Floats, tags, indefinite lengths and
    non-text map keys are intentionally unsupported.
    """
    if value is None:
        return b"\xf6"
    if value is False:
        return b"\xf4"
    if value is True:
        return b"\xf5"
    if isinstance(value, int) and not isinstance(value, bool):
        if value >= 0:
            return _head(0, value)
        return _head(1, -1 - value)
    if isinstance(value, bytes):
        return _head(2, len(value)) + value
    if isinstance(value, str):
        raw = value.encode("utf-8", "strict")
        return _head(3, len(raw)) + raw
    if isinstance(value, (list, tuple)):
        return _head(4, len(value)) + b"".join(canonical_cbor(v) for v in value)
    if isinstance(value, Mapping):
        if any(not isinstance(k, str) for k in value):
            raise PCBEError("CBOR map keys must be text strings")
        pairs = [(canonical_cbor(k), canonical_cbor(v)) for k, v in value.items()]
        pairs.sort(key=lambda pair: (len(pair[0]), pair[0]))
        return _head(5, len(pairs)) + b"".join(k + v for k, v in pairs)
    raise PCBEError("unsupported CBOR value type: " + type(value).__name__)


def evidence_digest(media_type: str, exact_bytes: bytes) -> bytes:
    if not isinstance(media_type, str) or not media_type:
        raise PCBEError("evidence media_type is required")
    if not isinstance(exact_bytes, bytes):
        raise PCBEError("evidence must be exact bytes")
    # CBOR array removes the ambiguity in concatenating variable-length fields.
    return hashlib.sha256(EVIDENCE_DOMAIN + canonical_cbor([media_type, exact_bytes])).digest()


def attachments_merkle_root(digests: list[bytes]) -> bytes | None:
    """Merkle profile: ordered leaves, 0x00 leaf prefix, 0x01 node prefix;
    an unpaired final node is promoted unchanged (not duplicated).
    """
    if not digests:
        return None
    if any(not isinstance(d, bytes) or len(d) != 32 for d in digests):
        raise PCBEError("each evidence digest must be exactly 32 bytes")
    level = [hashlib.sha256(b"\x00" + d).digest() for d in digests]
    while len(level) > 1:
        nxt = []
        for i in range(0, len(level), 2):
            if i + 1 == len(level):
                nxt.append(level[i])
            else:
                nxt.append(hashlib.sha256(b"\x01" + level[i] + level[i + 1]).digest())
        level = nxt
    return level[0]


def event_payload(event: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(event, Mapping):
        raise PCBEError("event must be a map")
    payload = {k: v for k, v in event.items() if k != "signatures"}
    if set(payload) != EVENT_FIELDS:
        missing = sorted(EVENT_FIELDS - set(payload))
        extra = sorted(set(payload) - EVENT_FIELDS)
        raise PCBEError(f"event fields mismatch; missing={missing}, extra={extra}")
    if (payload["protocol"] != PROTOCOL or not isinstance(payload["version"], int)
            or isinstance(payload["version"], bool) or payload["version"] != VERSION):
        raise PCBEError("unsupported PCBE protocol or version")
    network = payload["network"]
    if not isinstance(network, dict) or not isinstance(network.get("network"), str):
        raise PCBEError("network identifier is malformed")
    if not isinstance(network.get("genesis_hash"), bytes) or len(network["genesis_hash"]) != 32:
        raise PCBEError("network genesis_hash must be 32 bytes")
    for name in ("event_id", "subject_commitment", "nonce"):
        if not isinstance(payload[name], bytes) or len(payload[name]) != 32:
            raise PCBEError(f"{name} must be exactly 32 bytes")
    for name in ("event_type", "policy_id"):
        if not isinstance(payload[name], str) or not payload[name]:
            raise PCBEError(f"{name} is required")
    if not isinstance(payload["claims"], dict):
        raise PCBEError("claims must be a map")
    if not isinstance(payload["evidence"], list):
        raise PCBEError("evidence must be an array")
    for item in payload["evidence"]:
        if not isinstance(item, dict) or set(item) != {"digest", "media_type", "source"}:
            raise PCBEError("each evidence item needs digest, media_type and source")
        if not isinstance(item["digest"], bytes) or len(item["digest"]) != 32:
            raise PCBEError("evidence digest must be 32 bytes")
        if not all(isinstance(item[k], str) and item[k] for k in ("media_type", "source")):
            raise PCBEError("evidence media_type and source are required")
    for name in ("issued_at", "expires_at"):
        if not isinstance(payload[name], int) or isinstance(payload[name], bool):
            raise PCBEError(f"{name} must be an integer Unix timestamp")
    if payload["expires_at"] <= payload["issued_at"]:
        raise PCBEError("expires_at must be later than issued_at")
    if not isinstance(payload["predecessors"], list):
        raise PCBEError("predecessors must be an array")
    for pred in payload["predecessors"]:
        if (not isinstance(pred, dict) or set(pred) != {"event_id", "digest"}
                or any(not isinstance(pred[k], bytes) or len(pred[k]) != 32
                       for k in ("event_id", "digest"))):
            raise PCBEError("predecessor requires 32-byte event_id and digest")
    root = payload["attachments_root"]
    if root is not None and (not isinstance(root, bytes) or len(root) != 32):
        raise PCBEError("attachments_root must be null or 32 bytes")
    expected_root = attachments_merkle_root([x["digest"] for x in payload["evidence"]])
    if root != expected_root:
        raise PCBEError("attachments_root does not match ordered evidence digests")
    # This also rejects floats, tags, non-text map keys and unsupported objects.
    canonical_cbor(payload)
    return payload


def event_digest(event: Mapping[str, Any]) -> bytes:
    return hashlib.sha256(EVENT_DOMAIN + canonical_cbor(event_payload(event))).digest()


def attestation_message(digest: bytes, key_id: str, role: str,
                        policy_version: int) -> bytes:
    if not isinstance(digest, bytes) or len(digest) != 32:
        raise PCBEError("event digest must be 32 bytes")
    return ATTESTATION_DOMAIN + canonical_cbor(
        [digest, role, key_id, policy_version, "EXCAL-PCBE-v1"]
    )


@dataclass
class ReplayRegistry:
    """In-memory replay guard for a single verifier process.

    Production deployments must replace this with durable, atomic storage
    scoped by network and issuer policy.
    """
    seen: set[tuple[bytes, bytes]] = field(default_factory=set)

    def contains(self, genesis_hash: bytes, nonce: bytes) -> bool:
        return (genesis_hash, nonce) in self.seen

    def record(self, genesis_hash: bytes, nonce: bytes) -> None:
        self.seen.add((genesis_hash, nonce))


def verify_event(event: Mapping[str, Any], policy: Mapping[str, Any],
                 trust_store: Mapping[str, Mapping[str, Any]],
                 replay: ReplayRegistry | None = None,
                 now: int | None = None,
                 dispute_open: bool = False,
                 revocation_updated_at: int | None = None) -> dict[str, Any]:
    """Verify envelope, Ed25519 role attestations and configured policy.

    Trust entries contain public_key (32 raw bytes), roles (iterable), org_id,
    not_before, expires_at and revoked. Policy contains policy_id, version,
    required_roles, optional max_ttl and distinct_organizations.
    """
    checked: list[str] = []
    signature_results: list[dict[str, Any]] = []
    outcome = "UNVERIFIABLE"
    reason = "verification not completed"
    timestamp = int(time.time()) if now is None else int(now)
    try:
        payload = event_payload(event)
        checked.extend(["schema", "deterministic_cbor", "attachments_root"])
        digest = hashlib.sha256(EVENT_DOMAIN + canonical_cbor(payload)).digest()
        if replay is None:
            outcome, reason = "UNVERIFIABLE", "replay registry is unavailable"
            raise _StopVerification()
        if policy.get("policy_id") != payload["policy_id"]:
            raise PCBEError("policy identifier mismatch")
        if (not isinstance(policy.get("version"), int)
                or isinstance(policy.get("version"), bool)):
            raise PCBEError("policy version unavailable")
        if timestamp < payload["issued_at"]:
            raise PCBEError("event is not yet valid")
        if timestamp >= payload["expires_at"]:
            outcome, reason = "EXPIRED", "event validity interval has ended"
            raise _StopVerification()
        max_ttl = policy.get("max_ttl")
        if max_ttl is not None and payload["expires_at"] - payload["issued_at"] > int(max_ttl):
            raise PCBEError("event validity interval exceeds policy maximum")
        checked.extend(["network", "event_validity", "policy"])
        genesis = payload["network"]["genesis_hash"]
        if replay is not None and replay.contains(genesis, payload["nonce"]):
            raise PCBEError("duplicate event nonce")
        signatures = event.get("signatures")
        if not isinstance(signatures, list):
            raise PCBEError("signatures must be an array")
        required = policy.get("required_roles")
        if not isinstance(required, list) or not required or any(not isinstance(x, str) for x in required):
            raise PCBEError("policy required_roles is unavailable")
        if Ed25519PublicKey is None:
            outcome, reason = "UNVERIFIABLE", "cryptography Ed25519 support is unavailable"
            raise _StopVerification()
        valid_roles: set[str] = set()
        valid_orgs_by_role: dict[str, set[str]] = {}
        seen_keys: set[str] = set()
        revoked_seen = False
        for item in signatures:
            if not isinstance(item, dict) or set(item) != SIGNATURE_FIELDS:
                raise PCBEError("malformed detached signature record")
            key_id, role = item["key_id"], item["role"]
            if not isinstance(key_id, str) or not isinstance(role, str):
                raise PCBEError("signature key_id and role must be strings")
            if key_id in seen_keys:
                raise PCBEError("duplicate signer key")
            seen_keys.add(key_id)
            trust = trust_store.get(key_id)
            if trust is None:
                outcome, reason = "UNVERIFIABLE", f"unknown trust key: {key_id}"
                raise _StopVerification()
            if trust.get("revoked", False):
                revoked_seen = True
                signature_results.append({"key_id": key_id, "role": role, "valid": False, "reason": "revoked"})
                continue
            if timestamp < int(trust.get("not_before", 0)) or timestamp >= int(trust.get("expires_at", 2**63 - 1)):
                raise PCBEError("signing key outside validity interval")
            authorized_roles = trust.get("roles")
            if not isinstance(authorized_roles, (list, tuple, set)) or any(
                    not isinstance(r, str) for r in authorized_roles):
                outcome, reason = "UNVERIFIABLE", "trust entry role data is malformed"
                raise _StopVerification()
            if role not in set(authorized_roles):
                raise PCBEError("signer is not authorized for declared role")
            if item["policy_version"] != policy["version"]:
                raise PCBEError("signature policy version mismatch")
            sig = item["signature"]
            if not isinstance(sig, bytes) or len(sig) != 64:
                raise PCBEError("Ed25519 signature must be exactly 64 bytes")
            public_key = trust.get("public_key")
            if not isinstance(public_key, bytes) or len(public_key) != 32:
                outcome, reason = "UNVERIFIABLE", "trust entry has no valid Ed25519 public key"
                raise _StopVerification()
            try:
                Ed25519PublicKey.from_public_bytes(public_key).verify(
                    sig, attestation_message(digest, key_id, role, policy["version"]))
            except InvalidSignature:
                raise PCBEError("invalid Ed25519 signature")
            valid_roles.add(role)
            valid_orgs_by_role.setdefault(role, set()).add(
                str(trust.get("org_id", key_id)))
            signature_results.append({"key_id": key_id, "role": role, "valid": True})
        checked.extend(["issuer_authority", "ed25519_signatures"])
        missing = sorted(set(required) - valid_roles)
        if revoked_seen:
            outcome, reason = "REVOKED", "one or more supplied signer keys are revoked"
        elif missing:
            outcome, reason = "INCOMPLETE", "missing required roles: " + ", ".join(missing)
        elif policy.get("distinct_organizations", False):
            role_orgs = []
            for role in required:
                matching = valid_orgs_by_role.get(role, set())
                if not matching:
                    outcome, reason = "INCOMPLETE", f"no organization attested role {role}"
                    raise _StopVerification()
                role_orgs.append(next(iter(matching)))
            if len(set(role_orgs)) != len(role_orgs):
                raise PCBEError("required roles are not held by distinct organizations")
            outcome, reason = "VALID", "all required roles and distinct-organization policy checks passed"
        else:
            outcome, reason = "VALID", "all required role signatures and policy checks passed"
        if revocation_updated_at is None:
            outcome, reason = "UNVERIFIABLE", "revocation snapshot freshness is unknown"
        elif int(revocation_updated_at) > timestamp:
            outcome, reason = "UNVERIFIABLE", "revocation snapshot timestamp is in the future"
        elif timestamp - int(revocation_updated_at) > int(policy.get("max_revocation_age", 86400)):
            outcome, reason = "UNVERIFIABLE", "revocation snapshot is stale"
        if dispute_open:
            outcome, reason = "DISPUTED", "an open dispute is registered for this event"
        if outcome == "VALID" and replay is not None:
            replay.record(genesis, payload["nonce"])
        checked.extend(["revocation_freshness", "replay_protection", "dispute_status"])
    except _StopVerification:
        pass
    except PCBEError as exc:
        if outcome not in ("EXPIRED", "REVOKED", "UNVERIFIABLE"):
            outcome = "INVALID"
        reason = str(exc)
    report = {
        "protocol": PROTOCOL,
        "version": VERSION,
        "outcome": outcome,
        "reason": reason,
        "event_digest": (digest.hex() if "digest" in locals() else None),
        "policy_id": policy.get("policy_id") if isinstance(policy, Mapping) else None,
        "policy_version": policy.get("version") if isinstance(policy, Mapping) else None,
        "verifier": "excal-pcbe-python-reference/1",
        "checked": checked,
        "signature_results": signature_results,
    }
    report["report_digest"] = hashlib.sha256(
        REPORT_DOMAIN + canonical_cbor(report)
    ).hexdigest()
    return report


class _StopVerification(Exception):
    """Internal control flow for a completed non-VALID outcome."""
