"""Tests that load the published vectors and reproduce every value.

A second implementation must reproduce these digests, encodings and
outcomes exactly; these tests pin them from the checked-in file.
"""
import json
import unittest
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from pcbe.bundle import bundle_from_json
from pcbe.core import (
    PCBEError, ReplayRegistry, attachments_merkle_root, attestation_message,
    canonical_cbor, decode_canonical_cbor, event_digest, event_payload,
    evidence_digest, verify_event, verify_merkle_proof,
)
from pcbe.make_vectors import build_vectors

VECTORS_PATH = Path(__file__).resolve().parent.parent / "pcbe" / "test_vectors.json"


def _decode(value):
    """Decode the $bytes markers used in the vectors file."""
    if isinstance(value, dict):
        if set(value) == {"$bytes"}:
            return bytes.fromhex(value["$bytes"])
        return {k: _decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode(v) for v in value]
    return value


class VectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vectors = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))

    def test_vectors_are_reproducible(self):
        self.assertEqual(build_vectors(), self.vectors)

    def test_cbor_vectors(self):
        for case in self.vectors["cbor"]:
            value = _decode(case["json"])
            with self.subTest(value=repr(value)):
                self.assertEqual(canonical_cbor(value).hex(), case["cbor_hex"])
                self.assertEqual(decode_canonical_cbor(bytes.fromhex(case["cbor_hex"])),
                                 value)

    def test_cbor_rejected_vectors(self):
        for raw in self.vectors["cbor_rejected"]:
            with self.subTest(raw=raw):
                with self.assertRaises(PCBEError):
                    decode_canonical_cbor(bytes.fromhex(raw))

    def test_evidence_vectors(self):
        for item in self.vectors["evidence"]:
            self.assertEqual(
                evidence_digest(item["media_type"], bytes.fromhex(item["bytes_hex"])).hex(),
                item["digest_hex"])

    def test_merkle_vectors(self):
        merkle = self.vectors["merkle"]
        leaves = [bytes.fromhex(x) for x in merkle["leaves_hex"]]
        root = bytes.fromhex(merkle["root_hex"])
        self.assertEqual(attachments_merkle_root(leaves), root)
        self.assertNotEqual(bytes.fromhex(merkle["reordered_root_hex"]), root)
        for proof in merkle["proofs"]:
            steps = [{"sibling": bytes.fromhex(s["sibling_hex"]),
                      "sibling_is_left": s["sibling_is_left"]}
                     for s in proof["steps"]]
            self.assertTrue(verify_merkle_proof(leaves[proof["index"]], steps, root))

    def test_event_and_attestation_vectors(self):
        event = _decode(self.vectors["event"])
        self.assertEqual(canonical_cbor(event_payload(event)).hex(),
                         self.vectors["event_payload_cbor_hex"])
        digest = event_digest(event)
        self.assertEqual(digest.hex(), self.vectors["event_digest_hex"])
        att = self.vectors["attestation"]
        message = attestation_message(digest, att["key_id"], att["role"],
                                      att["policy_version"])
        self.assertEqual(message.hex(), att["message_hex"])
        public = Ed25519PublicKey.from_public_bytes(bytes.fromhex(att["public_key_hex"]))
        public.verify(bytes.fromhex(att["signature_hex"]), message)

    def test_verify_cases(self):
        for case in self.vectors["verify_cases"]:
            with self.subTest(case=case["name"]):
                bundle = bundle_from_json(json.dumps(case["bundle"]))
                replay = ReplayRegistry()
                for genesis, nonce in bundle.get("replay_seen", []):
                    replay.record(genesis, nonce)
                report = verify_event(
                    bundle["event"], bundle["policy"], bundle["trust"],
                    replay=replay, now=case["now"],
                    dispute_open=bundle.get("dispute_open", False),
                    revocation_updated_at=bundle.get("revocation_updated_at"),
                    expected_network=bundle.get("expected_network"),
                    predecessor_digests=bundle.get("predecessor_digests"))
                self.assertEqual(report["outcome"], case["expected_outcome"])


if __name__ == "__main__":
    unittest.main()
