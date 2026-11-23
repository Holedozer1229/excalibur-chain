"""JSON diagnostic form for PCBE v1 bundles.

An evidence bundle is a JSON document that carries an event, its policy,
a pinned trust snapshot, replay state and verification context. Bytes are
encoded as ``{"$bytes": "<lowercase hex>"}`` so the JSON form is exact and
reversible; the signed bytes are always the deterministic CBOR form, never
this JSON text.

Bundle format ``excal-pcbe-bundle-v1``::

    {
      "format": "excal-pcbe-bundle-v1",
      "event": {...},                  # required; bytes as {"$bytes": hex}
      "policy": {...},                 # required
      "trust": {"key-id": {...}},      # required; public_key as {"$bytes": hex}
      "revocation_updated_at": 1800000000,
      "dispute_open": false,
      "replay_seen": [["<genesis hex>", "<nonce hex>"], ...]
    }

Only the listed top-level keys are accepted. Unknown keys, non-hex bytes,
or malformed markers fail closed with PCBEError. No business payload is
ever written to EXCAL by this module.
"""
from __future__ import annotations

import json
from typing import Any, Mapping

from .core import PCBEError

BUNDLE_FORMAT = "excal-pcbe-bundle-v1"
_BUNDLE_KEYS = {
    "format", "event", "policy", "trust", "revocation_updated_at",
    "dispute_open", "replay_seen",
}
_TRUST_KEYS = {"public_key", "roles", "org_id", "not_before", "expires_at", "revoked"}


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"$bytes": value.hex()}
    if isinstance(value, Mapping):
        # Byte-string map keys become hex strings.
        return {(k.hex() if isinstance(k, bytes) else k): _to_jsonable(v)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise PCBEError("value is not JSON-encodable in a PCBE bundle: " + type(value).__name__)


def _from_jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        if set(value) == {"$bytes"}:
            raw = value["$bytes"]
            if not isinstance(raw, str):
                raise PCBEError("byte marker must hold a hex string")
            try:
                decoded = bytes.fromhex(raw)
            except ValueError:
                raise PCBEError("byte marker is not valid hex")
            if decoded.hex() != raw:
                raise PCBEError("byte marker hex must be lowercase without prefix")
            return decoded
        return {k: _from_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_from_jsonable(v) for v in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise PCBEError("value is not a valid PCBE bundle value: " + type(value).__name__)


def event_to_jsonable(event: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(event, Mapping):
        raise PCBEError("event must be a map")
    return _to_jsonable(dict(event))


def event_from_jsonable(value: Any) -> dict[str, Any]:
    event = _from_jsonable(value)
    if not isinstance(event, dict):
        raise PCBEError("event must be a map")
    return event


def bundle_to_json(bundle: Mapping[str, Any]) -> str:
    """Serialize a bundle mapping to canonical JSON text (sorted keys)."""
    if not isinstance(bundle, Mapping):
        raise PCBEError("bundle must be a map")
    if set(bundle) - _BUNDLE_KEYS:
        raise PCBEError("bundle has unknown top-level keys: "
                        + ", ".join(sorted(set(bundle) - _BUNDLE_KEYS)))
    return json.dumps(_to_jsonable(dict(bundle)), sort_keys=True, indent=2) + "\n"


def bundle_from_json(text: str) -> dict[str, Any]:
    """Parse and strictly validate bundle JSON text into plain Python values."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PCBEError("bundle is not valid JSON: " + str(exc))
    if not isinstance(raw, dict):
        raise PCBEError("bundle must be a JSON object")
    if set(raw) - _BUNDLE_KEYS:
        raise PCBEError("bundle has unknown top-level keys: "
                        + ", ".join(sorted(set(raw) - _BUNDLE_KEYS)))
    if raw.get("format") != BUNDLE_FORMAT:
        raise PCBEError("unsupported bundle format: " + repr(raw.get("format")))
    bundle = _from_jsonable(raw)
    for name in ("event", "policy", "trust"):
        if name not in bundle:
            raise PCBEError(f"bundle is missing required section: {name}")
        if not isinstance(bundle[name], dict):
            raise PCBEError(f"bundle section {name} must be an object")
    for key_id, entry in bundle["trust"].items():
        if not isinstance(entry, dict) or set(entry) - _TRUST_KEYS:
            raise PCBEError(f"trust entry {key_id!r} is malformed")
    if "replay_seen" in bundle:
        seen = bundle["replay_seen"]
        if not isinstance(seen, list) or any(
                not isinstance(pair, list) or len(pair) != 2
                or not all(isinstance(x, bytes) and len(x) == 32 for x in pair)
                for pair in seen):
            raise PCBEError("replay_seen must be a list of [genesis_hash, nonce] byte pairs")
    if "dispute_open" in bundle and not isinstance(bundle["dispute_open"], bool):
        raise PCBEError("dispute_open must be a boolean")
    if "revocation_updated_at" in bundle:
        value = bundle["revocation_updated_at"]
        if value is not None and (not isinstance(value, int) or isinstance(value, bool)):
            raise PCBEError("revocation_updated_at must be an integer or null")
    return bundle
