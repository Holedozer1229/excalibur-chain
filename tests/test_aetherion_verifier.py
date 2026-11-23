import hashlib
import unittest

from aetherion_verifier import (
    SCHEMA, AttestationError, canonical_json, digest,
    sign_attestation, verify_attestation,
)
from aetherion_verifier.excal_observer import ObserverError, _loopback_url


class CanonicalEncodingTests(unittest.TestCase):
    def test_key_order_is_stable(self):
        self.assertEqual(canonical_json({"b": 2, "a": 1}),
                         canonical_json({"a": 1, "b": 2}))

    def test_float_is_rejected(self):
        with self.assertRaises(AttestationError):
            canonical_json({"measurement": 0.1})

    def test_digest_is_sha256_of_canonical_json(self):
        self.assertEqual(digest({"x": 1}),
                         hashlib.sha256(b'{"x":1}').hexdigest())


class AttestationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
            from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        except ImportError:
            raise unittest.SkipTest("cryptography is not installed")
        cls.private_key = Ed25519PrivateKey.generate()
        cls.public_key = cls.private_key.public_key().public_bytes(
            Encoding.Raw, PublicFormat.Raw
        )

    def setUp(self):
        self.inputs = {"height": 77, "network": "excal"}
        self.evidence = {"tip_hash": "ab" * 32}
        self.method_source = b"def verify_tip(height, block): return height == block['height']\n"
        self.payload = {
            "schema": SCHEMA,
            "claim": "block record height matches reported height",
            "method": {
                "id": "tip-height-check",
                "version": "1",
                "sha256": hashlib.sha256(self.method_source).hexdigest(),
            },
            "inputs_sha256": digest(self.inputs),
            "result": "verified",
            "evidence_sha256": digest(self.evidence),
            "counterexample_sha256": None,
            "issued_at": 100,
            "expires_at": 200,
            "nonce": "01" * 16,
            "issuer_id": "test-observer",
        }
        self.signed = sign_attestation(self.payload, self.private_key)

    def verify(self, **overrides):
        args = dict(
            inputs=self.inputs, evidence=self.evidence,
            method_source=self.method_source,
            trusted_issuers={"test-observer": self.public_key}, now=150,
        )
        args.update(overrides)
        return verify_attestation(self.signed, **args)

    def test_valid_signature_and_commitments(self):
        self.assertEqual(self.verify()["status"], "valid")

    def test_tampered_inputs_fail(self):
        self.assertEqual(self.verify(inputs={"height": 78})["status"], "invalid")

    def test_tampered_method_fails(self):
        self.assertEqual(self.verify(method_source=b"changed")["status"], "invalid")

    def test_untrusted_issuer_is_inconclusive(self):
        result = self.verify(trusted_issuers={})
        self.assertEqual(result["status"], "inconclusive")
        self.assertEqual(result["reason"], "untrusted_issuer")

    def test_expired_attestation_fails(self):
        self.assertEqual(self.verify(now=200)["status"], "invalid")

    def test_tampered_signature_fails(self):
        self.signed["signature"] = "AA==" * 21 + "AA=="
        self.assertEqual(self.verify()["status"], "invalid")

    def test_claimed_result_is_not_rewritten(self):
        self.assertEqual(self.verify()["claimed_result"], "verified")


class ObserverSafetyTests(unittest.TestCase):
    def test_loopback_allowed(self):
        self.assertEqual(_loopback_url("http://127.0.0.1:9432"), "http://127.0.0.1:9432")

    def test_public_host_rejected(self):
        with self.assertRaises(ObserverError):
            _loopback_url("http://example.com:9432")

    def test_https_not_accepted_by_current_node_adapter(self):
        with self.assertRaises(ObserverError):
            _loopback_url("https://127.0.0.1:9432")


if __name__ == "__main__":
    unittest.main()
