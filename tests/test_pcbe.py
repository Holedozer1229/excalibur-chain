import hashlib
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from pcbe.core import (
    ATTESTATION_DOMAIN, EVENT_DOMAIN, PROTOCOL, VERSION, ReplayRegistry,
    PCBEError, attachments_merkle_root, attestation_message, canonical_cbor,
    event_digest, evidence_digest, verify_event,
)


class PCBETests(unittest.TestCase):
    def setUp(self):
        self.now = 1_800_000_000
        self.private = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
        self.public = self.private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)
        self.policy = {
            "policy_id": "invoice-approval-v1",
            "version": 1,
            "network": "excal-testnet",
            "genesis_hash": b"g" * 32,
            "required_roles": ["seller"],
            "max_ttl": 3600,
            "max_revocation_age": 3600,
        }
        self.trust = {
            "seller-key-1": {
                "public_key": self.public,
                "roles": ["seller"],
                "org_id": "seller-inc",
                "not_before": self.now - 100,
                "expires_at": self.now + 1000,
                "revoked": False,
            }
        }
        self.event = {
            "protocol": PROTOCOL,
            "version": VERSION,
            "network": {"network": "excal-testnet", "genesis_hash": b"g" * 32},
            "event_id": b"e" * 32,
            "event_type": "invoice.approved/v1",
            "subject_commitment": b"s" * 32,
            "claims": {"invoice_total_minor": 12500, "currency": "USD"},
            "evidence": [],
            "policy_id": self.policy["policy_id"],
            "issued_at": self.now - 60,
            "expires_at": self.now + 600,
            "nonce": b"n" * 32,
            "predecessors": [],
            "attachments_root": None,
        }
        self.event["signatures"] = [self.signature("seller-key-1", "seller")]

    def signature(self, key_id, role):
        digest = event_digest(self.event)
        message = attestation_message(digest, key_id, role, self.policy["version"])
        return {
            "key_id": key_id,
            "role": role,
            "policy_version": self.policy["version"],
            "signature": self.private.sign(message),
        }

    def verify(self, event=None, replay=None, **kwargs):
        return verify_event(
            self.event if event is None else event,
            self.policy, self.trust,
            replay=ReplayRegistry() if replay is None else replay,
            now=self.now, revocation_updated_at=self.now, **kwargs)

    def test_deterministic_cbor_integer_and_map_order(self):
        self.assertEqual(canonical_cbor(23), bytes.fromhex("17"))
        self.assertEqual(canonical_cbor(24), bytes.fromhex("1818"))
        self.assertEqual(canonical_cbor({"b": 1, "a": 2}),
                         canonical_cbor({"a": 2, "b": 1}))

    def test_cbor_rejects_floats_and_non_text_keys(self):
        with self.assertRaises(PCBEError):
            canonical_cbor(1.5)
        with self.assertRaises(PCBEError):
            canonical_cbor({1: "not permitted"})

    def test_evidence_digest_and_merkle_root_are_deterministic(self):
        a = evidence_digest("text/plain", b"alpha")
        b = evidence_digest("text/plain", b"beta")
        self.assertEqual(len(a), 32)
        self.assertEqual(attachments_merkle_root([a, b]),
                         attachments_merkle_root([a, b]))
        self.assertNotEqual(attachments_merkle_root([a, b]),
                            attachments_merkle_root([b, a]))

    def test_valid_role_signature(self):
        result = self.verify()
        self.assertEqual(result["outcome"], "VALID")

    def test_event_mutation_invalidates_signature(self):
        changed = dict(self.event)
        changed["claims"] = {"invoice_total_minor": 12501, "currency": "USD"}
        self.assertEqual(self.verify(changed)["outcome"], "INVALID")

    def test_role_substitution_is_rejected(self):
        changed = dict(self.event)
        changed["signatures"] = [dict(self.event["signatures"][0], role="buyer")]
        self.assertEqual(self.verify(changed)["outcome"], "INVALID")

    def test_duplicate_nonce_is_rejected_after_first_valid_use(self):
        registry = ReplayRegistry()
        self.assertEqual(self.verify(replay=registry)["outcome"], "VALID")
        self.assertEqual(self.verify(replay=registry)["outcome"], "INVALID")

    def test_missing_replay_registry_is_unverifiable(self):
        result = verify_event(self.event, self.policy, self.trust,
                              now=self.now, revocation_updated_at=self.now)
        self.assertEqual(result["outcome"], "UNVERIFIABLE")

    def test_expired_event_is_explicit(self):
        changed = dict(self.event)
        changed["expires_at"] = self.now
        changed["signatures"] = []
        self.assertEqual(self.verify(changed)["outcome"], "EXPIRED")

    def test_revoked_key_is_explicit(self):
        trust = {"seller-key-1": dict(self.trust["seller-key-1"], revoked=True)}
        result = verify_event(self.event, self.policy, trust,
                              replay=ReplayRegistry(), now=self.now,
                              revocation_updated_at=self.now)
        self.assertEqual(result["outcome"], "REVOKED")

    def test_stale_revocation_snapshot_fails_closed(self):
        result = verify_event(self.event, self.policy, self.trust,
                              replay=ReplayRegistry(), now=self.now,
                              revocation_updated_at=self.now - 7200)
        self.assertEqual(result["outcome"], "UNVERIFIABLE")

    def test_missing_required_role_is_incomplete(self):
        changed = dict(self.event)
        changed["signatures"] = []
        self.assertEqual(self.verify(changed)["outcome"], "INCOMPLETE")

    def test_report_digest_is_stable(self):
        a = self.verify()
        b = self.verify()
        self.assertEqual(a["report_digest"], b["report_digest"])


if __name__ == "__main__":
    unittest.main()
