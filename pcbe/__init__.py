"""EXCAL Proof-Carrying Business Events (PCBE) v1.

Application-layer only: deterministic CBOR envelopes, domain-separated
SHA-256 commitments, evidence Merkle proofs and Ed25519 role attestations.
This package never touches EXCAL consensus, wallets, transaction signing
or payment authorization. A VALID outcome proves integrity, origin under a
key and protocol conditions; it does not prove a real-world statement true.
"""
from __future__ import annotations

from .core import (
    ATTESTATION_DOMAIN,
    EVENT_DOMAIN,
    EVIDENCE_DOMAIN,
    OUTCOMES,
    PROTOCOL,
    REPORT_DOMAIN,
    VERSION,
    PCBEError,
    ReplayRegistry,
    attachments_merkle_root,
    attestation_message,
    canonical_cbor,
    decode_canonical_cbor,
    event_digest,
    event_payload,
    evidence_digest,
    merkle_proof,
    verify_event,
    verify_merkle_proof,
)

__version__ = "1"
__all__ = [
    "ATTESTATION_DOMAIN",
    "EVENT_DOMAIN",
    "EVIDENCE_DOMAIN",
    "OUTCOMES",
    "PROTOCOL",
    "REPORT_DOMAIN",
    "VERSION",
    "PCBEError",
    "ReplayRegistry",
    "attachments_merkle_root",
    "attestation_message",
    "canonical_cbor",
    "decode_canonical_cbor",
    "event_digest",
    "event_payload",
    "evidence_digest",
    "merkle_proof",
    "verify_event",
    "verify_merkle_proof",
    "__version__",
]
