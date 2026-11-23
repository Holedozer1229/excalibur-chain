"""Deterministic reproducible PCBE example bundle.

TEST KEYS ONLY. The private key below is the public test vector
``bytes(range(1, 33))``; it must never attest a real business event.
The example exists so a second implementation can reproduce byte-identical
digests and the same VALID outcome from the published vectors.
"""
from __future__ import annotations

from typing import Any

from .core import (
    PROTOCOL,
    VERSION,
    attachments_merkle_root,
    attestation_message,
    event_digest,
    evidence_digest,
)
from .bundle import BUNDLE_FORMAT

TEST_PRIVATE_KEY = bytes(range(1, 33))
EXAMPLE_NOW = 1_800_000_000
EXAMPLE_GENESIS = b"g" * 32


def build_example(now: int = EXAMPLE_NOW) -> dict[str, Any]:
    """Build the fixed invoice-approval example bundle for ``now``."""
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError as exc:
        raise RuntimeError(
            "the 'cryptography' package is required to sign the example bundle"
        ) from exc
    private = Ed25519PrivateKey.from_private_bytes(TEST_PRIVATE_KEY)
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    policy = {
        "policy_id": "invoice-approval-v1",
        "version": 1,
        "network": "excal-testnet",
        "genesis_hash": EXAMPLE_GENESIS,
        "required_roles": ["seller"],
        "max_ttl": 3600,
        "max_revocation_age": 3600,
    }
    trust = {
        "seller-key-1": {
            "public_key": public,
            "roles": ["seller"],
            "org_id": "seller-inc",
            "not_before": now - 100,
            "expires_at": now + 1000,
            "revoked": False,
        }
    }
    digests = [
        evidence_digest("application/pdf", b"example invoice INV-1001 bytes"),
        evidence_digest("text/plain", b"example delivery note DL-77 bytes"),
    ]
    event = {
        "protocol": PROTOCOL,
        "version": VERSION,
        "network": {"network": "excal-testnet", "genesis_hash": EXAMPLE_GENESIS},
        "event_id": b"e" * 32,
        "event_type": "invoice.approved/v1",
        "subject_commitment": b"s" * 32,
        "claims": {"invoice_total_minor": 12500, "currency": "USD"},
        "evidence": [
            {"digest": digests[0], "media_type": "application/pdf",
             "source": "example-seller-erp"},
            {"digest": digests[1], "media_type": "text/plain",
             "source": "example-carrier-pod"},
        ],
        "policy_id": policy["policy_id"],
        "issued_at": now - 60,
        "expires_at": now + 600,
        "nonce": b"n" * 32,
        "predecessors": [],
        "attachments_root": attachments_merkle_root(digests),
    }
    digest = event_digest(event)
    message = attestation_message(digest, "seller-key-1", "seller", policy["version"])
    event["signatures"] = [{
        "key_id": "seller-key-1",
        "role": "seller",
        "policy_version": policy["version"],
        "signature": private.sign(message),
    }]
    return {
        "format": BUNDLE_FORMAT,
        "event": event,
        "policy": policy,
        "trust": trust,
        "revocation_updated_at": now,
        "dispute_open": False,
        "replay_seen": [],
    }
