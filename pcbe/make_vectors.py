"""Generate the published PCBE v1 test vectors (``pcbe/test_vectors.json``).

Deterministic: fixed test key, fixed timestamps, fixed event fields. A
second implementation must reproduce every digest, CBOR encoding and
verification outcome here. Run ``python3 -m pcbe.make_vectors`` to
regenerate the file after any intentional vector change.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

from .bundle import _to_jsonable
from .core import (
    attachments_merkle_root,
    attestation_message,
    canonical_cbor,
    event_digest,
    event_payload,
    evidence_digest,
    merkle_proof,
)
from .example import EXAMPLE_NOW, build_example

VECTORS_PATH = Path(__file__).with_name("test_vectors.json")


def _cbor_cases() -> list[dict[str, str]]:
    values = [
        0, 23, 24, 255, 256, 65535, 65536, 2**32, 2**64 - 1,
        -1, -24, -25, -256, -2**64,
        "", "a", "invoice.approved/v1",
        b"", b"\x00\xff",
        [], [1, "two", b"three"],
        {}, {"b": 1, "a": 2},
        {"claims": {"invoice_total_minor": 12500, "currency": "USD"}},
        None, True, False,
    ]
    return [{"json": _to_jsonable(v), "cbor_hex": canonical_cbor(v).hex()}
            for v in values]


def _cbor_rejected() -> list[str]:
    # Non-shortest encodings, indefinite lengths, tags, floats, trailing bytes.
    return [
        "1817",        # 23 encoded with a one-byte argument (must be 0x17)
        "1900ff",      # 255 encoded with a two-byte argument (must be 0x18ff)
        "1b0000000000000000",  # 0 encoded with an eight-byte argument
        "5f",          # indefinite-length map
        "9fff",        # indefinite-length array
        "c0",          # tag 0
        "f93c00",      # half-precision float
        "fb3ff8000000000000",  # double float
        "00ff",        # trailing byte after a complete value
        "a2616201616102",  # map keys out of order: {"b": 1, "a": 2} is not canonical
    ]


def _merkle_section() -> dict[str, object]:
    leaves = [evidence_digest("text/plain", chunk) for chunk in (b"alpha", b"beta", b"gamma")]
    root = attachments_merkle_root(leaves)
    proofs = []
    for index in range(len(leaves)):
        proof = merkle_proof(leaves, index)
        proofs.append({
            "index": index,
            "steps": [{"sibling_hex": step["sibling"].hex(),
                       "sibling_is_left": step["sibling_is_left"]} for step in proof],
        })
    return {
        "leaves_hex": [leaf.hex() for leaf in leaves],
        "root_hex": root.hex(),
        "proofs": proofs,
        # Reordering the leaves must change the root.
        "reordered_root_hex": attachments_merkle_root(list(reversed(leaves))).hex(),
    }


def _verify_cases(example: dict) -> list[dict[str, object]]:
    def bundle_with(mutate) -> dict:
        bundle = copy.deepcopy(example)
        mutate(bundle)
        return bundle

    def set_claims(bundle, total: int) -> None:
        bundle["event"]["claims"]["invoice_total_minor"] = total

    cases: list[dict[str, object]] = []
    cases.append({"name": "valid", "bundle": _to_jsonable(copy.deepcopy(example)),
                  "now": EXAMPLE_NOW, "expected_outcome": "VALID"})
    cases.append({"name": "tampered-claim",
                  "bundle": _to_jsonable(bundle_with(lambda b: set_claims(b, 12501))),
                  "now": EXAMPLE_NOW, "expected_outcome": "INVALID"})
    cases.append({"name": "wrong-network",
                  "bundle": _to_jsonable(bundle_with(
                      lambda b: b["event"]["network"].update({"network": "excal-mainnet"}))),
                  "now": EXAMPLE_NOW, "expected_outcome": "INVALID"})
    cases.append({"name": "expired",
                  "bundle": _to_jsonable(bundle_with(
                      lambda b: b["event"].update({"expires_at": EXAMPLE_NOW}))),
                  "now": EXAMPLE_NOW, "expected_outcome": "EXPIRED"})
    cases.append({"name": "revoked",
                  "bundle": _to_jsonable(bundle_with(
                      lambda b: b["trust"]["seller-key-1"].update({"revoked": True}))),
                  "now": EXAMPLE_NOW, "expected_outcome": "REVOKED"})
    cases.append({"name": "missing-role",
                  "bundle": _to_jsonable(bundle_with(
                      lambda b: b["event"].update({"signatures": []}))),
                  "now": EXAMPLE_NOW, "expected_outcome": "INCOMPLETE"})
    cases.append({"name": "disputed",
                  "bundle": _to_jsonable(bundle_with(
                      lambda b: b.update({"dispute_open": True}))),
                  "now": EXAMPLE_NOW, "expected_outcome": "DISPUTED"})

    def duplicate_nonce(bundle) -> None:
        bundle["replay_seen"] = [[bundle["event"]["network"]["genesis_hash"],
                                  bundle["event"]["nonce"]]]
    cases.append({"name": "duplicate-nonce",
                  "bundle": _to_jsonable(bundle_with(duplicate_nonce)),
                  "now": EXAMPLE_NOW, "expected_outcome": "INVALID"})

    def unknown_predecessor(bundle) -> None:
        bundle["event"]["predecessors"] = [
            {"event_id": b"p" * 32, "digest": b"d" * 32}]
    cases.append({"name": "unknown-predecessor",
                  "bundle": _to_jsonable(bundle_with(unknown_predecessor)),
                  "now": EXAMPLE_NOW, "expected_outcome": "UNVERIFIABLE"})

    def mismatched_predecessor(bundle) -> None:
        bundle["event"]["predecessors"] = [
            {"event_id": b"p" * 32, "digest": b"d" * 32}]
        bundle["predecessor_digests"] = {b"p" * 32: b"x" * 32}
    cases.append({"name": "predecessor-mismatch",
                  "bundle": _to_jsonable(bundle_with(mismatched_predecessor)),
                  "now": EXAMPLE_NOW, "expected_outcome": "INVALID"})
    return cases


def build_vectors() -> dict[str, object]:
    example = build_example(EXAMPLE_NOW)
    event = example["event"]
    payload = event_payload(event)
    digest = event_digest(event)
    signature = event["signatures"][0]
    return {
        "format": "excal-pcbe-test-vectors-v1",
        "note": ("TEST KEYS ONLY. The Ed25519 key is the public test vector "
                 "bytes(range(1, 33)); it must never attest a real event. "
                 "A VALID outcome here proves integrity, origin under the "
                 "test key and protocol conditions only, not that any "
                 "real-world statement is true."),
        "cbor": _cbor_cases(),
        "cbor_rejected": _cbor_rejected(),
        "evidence": [
            {"media_type": "application/pdf",
             "bytes_hex": b"example invoice INV-1001 bytes".hex(),
             "digest_hex": evidence_digest(
                 "application/pdf", b"example invoice INV-1001 bytes").hex()},
            {"media_type": "text/plain",
             "bytes_hex": b"example delivery note DL-77 bytes".hex(),
             "digest_hex": evidence_digest(
                 "text/plain", b"example delivery note DL-77 bytes").hex()},
        ],
        "merkle": _merkle_section(),
        "event": _to_jsonable(event),
        "event_payload_cbor_hex": canonical_cbor(payload).hex(),
        "event_digest_hex": digest.hex(),
        "attestation": {
            "key_id": signature["key_id"],
            "role": signature["role"],
            "policy_version": signature["policy_version"],
            "message_hex": attestation_message(
                digest, signature["key_id"], signature["role"],
                signature["policy_version"]).hex(),
            "signature_hex": signature["signature"].hex(),
            "public_key_hex": example["trust"]["seller-key-1"]["public_key"].hex(),
        },
        "verify_cases": _verify_cases(example),
    }


def main() -> None:
    vectors = build_vectors()
    VECTORS_PATH.write_text(json.dumps(vectors, sort_keys=True, indent=2) + "\n",
                            encoding="utf-8")
    print(f"wrote {VECTORS_PATH} ({len(vectors['verify_cases'])} verify cases)")


if __name__ == "__main__":
    main()
