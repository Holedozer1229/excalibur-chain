"""Aetherion's evidence-verification layer for EXCAL.

This package is deliberately outside consensus and has no wallet or payout API.
"""
from .core import (
    SCHEMA,
    AttestationError,
    canonical_json,
    digest,
    sign_attestation,
    verify_attestation,
)

__all__ = [
    "SCHEMA",
    "AttestationError",
    "canonical_json",
    "digest",
    "sign_attestation",
    "verify_attestation",
]
