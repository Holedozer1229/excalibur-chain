import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey, Ed25519PublicKey)

from pcbe.bundle import bundle_from_json
from pcbe.core import (
    ATTESTATION_DOMAIN, EVENT_DOMAIN, PROTOCOL, VERSION, ReplayRegistry,
    PCBEError, attachments_merkle_root, attestation_message, canonical_cbor,
    decode_canonical_cbor, event_digest, event_payload, evidence_digest,
    merkle_proof, verify_event, verify_merkle_proof,
)
from pcbe.make_vectors import build_vectors

VECTORS_PATH = Path(__file__).resolve().parent.parent / "pcbe" / "test_vectors.json"
REPO_ROOT = Path(__file__).resolve().parent.parent


def build_fixture(now=1_800_000_000):
    """Shared valid invoice-approval fixture (TEST KEY bytes(range(1, 33)))."""
    private = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
    public = private.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw)
    policy = {
        "policy_id": "invoice-approval-v1",
        "version": 1,
        "network": "excal-testnet",
        "genesis_hash": b"g" * 32,
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
    event = {
        "protocol": PROTOCOL,
        "version": VERSION,
        "network": {"network": "excal-testnet", "genesis_hash": b"g" * 32},
        "event_id": b"e" * 32,
        "event_type": "invoice.approved/v1",
        "subject_commitment": b"s" * 32,
        "claims": {"invoice_total_minor": 12500, "currency": "USD"},
        "evidence": [],
        "policy_id": policy["policy_id"],
        "issued_at": now - 60,
        "expires_at": now + 600,
        "nonce": b"n" * 32,
        "predecessors": [],
        "attachments_root": None,
    }
    return {"now": now, "private": private, "public": public,
            "policy": policy, "trust": trust, "event": event}


def sign_event(event, private, key_id, role, policy_version):
    digest = event_digest(event)
    message = attestation_message(digest, key_id, role, policy_version)
    return {
        "key_id": key_id,
        "role": role,
        "policy_version": policy_version,
        "signature": private.sign(message),
    }


class PCBETests(unittest.TestCase):
    def setUp(self):
        fixture = build_fixture()
        self.now = fixture["now"]
        self.private = fixture["private"]
        self.public = fixture["public"]
        self.policy = fixture["policy"]
        self.trust = fixture["trust"]
        self.event = fixture["event"]
        self.event["signatures"] = [self.signature("seller-key-1", "seller")]

    def signature(self, key_id, role):
        return sign_event(self.event, self.private, key_id, role,
                          self.policy["version"])

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


class CBORDecoderTests(unittest.TestCase):
    def test_round_trip(self):
        values = [0, 23, 24, 255, 256, 65535, 65536, 2**32, 2**64 - 1,
                  -1, -24, -25, -256, -2**64, "", "a", "invoice.approved/v1",
                  b"", b"\x00\xff", [], [1, "two", b"three"], {},
                  {"b": 1, "a": 2},
                  {"claims": {"invoice_total_minor": 12500, "currency": "USD"}},
                  None, True, False]
        for value in values:
            with self.subTest(value=repr(value)):
                self.assertEqual(decode_canonical_cbor(canonical_cbor(value)), value)

    def test_rejects_non_canonical_encodings(self):
        for raw in ("1817", "1900ff", "1b0000000000000000", "5f", "9fff",
                    "c0", "f93c00", "fb3ff8000000000000", "00ff", "a2616201616102"):
            with self.subTest(raw=raw):
                with self.assertRaises(PCBEError):
                    decode_canonical_cbor(bytes.fromhex(raw))

    def test_rejects_truncated_and_wrong_key_type(self):
        with self.assertRaises(PCBEError):
            decode_canonical_cbor(bytes.fromhex("8201"))
        with self.assertRaises(PCBEError):
            decode_canonical_cbor(bytes.fromhex("a10102"))


class MerkleProofTests(unittest.TestCase):
    def leaves(self, count=5):
        return [evidence_digest("text/plain", bytes([65 + i])) for i in range(count)]

    def test_proof_verifies_for_each_leaf(self):
        leaves = self.leaves()
        root = attachments_merkle_root(leaves)
        for i, leaf in enumerate(leaves):
            with self.subTest(index=i):
                self.assertTrue(verify_merkle_proof(leaf, merkle_proof(leaves, i), root))

    def test_tampered_leaf_or_sibling_fails(self):
        leaves = self.leaves(3)
        root = attachments_merkle_root(leaves)
        proof = merkle_proof(leaves, 1)
        self.assertFalse(verify_merkle_proof(b"x" * 32, proof, root))
        tampered = [dict(step) for step in proof]
        tampered[0]["sibling"] = b"y" * 32
        self.assertFalse(verify_merkle_proof(leaves[1], tampered, root))

    def test_single_leaf_proof_is_empty(self):
        leaf = evidence_digest("text/plain", b"only")
        self.assertEqual(merkle_proof([leaf], 0), [])
        self.assertTrue(verify_merkle_proof(leaf, [], attachments_merkle_root([leaf])))

    def test_proof_index_out_of_range(self):
        with self.assertRaises(PCBEError):
            merkle_proof([b"a" * 32], 1)
        with self.assertRaises(PCBEError):
            merkle_proof([], 0)


class PCBEVerifierExtensionTests(unittest.TestCase):
    def setUp(self):
        fixture = build_fixture()
        self.now = fixture["now"]
        self.private = fixture["private"]
        self.policy = fixture["policy"]
        self.trust = fixture["trust"]
        self.event = fixture["event"]
        self.event["signatures"] = [
            sign_event(self.event, self.private, "seller-key-1", "seller",
                       self.policy["version"])]

    def verify(self, event=None, policy=None, trust=None, replay=None, **kwargs):
        kwargs.setdefault("revocation_updated_at", self.now)
        kwargs.setdefault("now", self.now)
        return verify_event(
            self.event if event is None else event,
            self.policy if policy is None else policy,
            self.trust if trust is None else trust,
            replay=ReplayRegistry() if replay is None else replay,
            **kwargs)

    def resign(self, event):
        event["signatures"] = [
            sign_event(event, self.private, "seller-key-1", "seller",
                       self.policy["version"])]

    def test_policy_pinned_network_must_match(self):
        # The matching policy pin is exercised by every VALID test; a policy
        # pinned to another network or genesis rejects the same event.
        wrong_network = dict(self.policy, network="excal-mainnet")
        self.assertEqual(self.verify(policy=wrong_network)["outcome"], "INVALID")
        wrong_genesis = dict(self.policy, genesis_hash=b"h" * 32)
        self.assertEqual(self.verify(policy=wrong_genesis)["outcome"], "INVALID")

    def test_replay_is_scoped_by_genesis_hash(self):
        registry = ReplayRegistry()
        self.assertEqual(self.verify(replay=registry)["outcome"], "VALID")
        # Same nonce on another genesis is a different replay scope, so it
        # verifies under a policy pinned to that genesis.
        other = dict(self.event)
        other["network"] = {"network": "excal-testnet", "genesis_hash": b"h" * 32}
        self.resign(other)
        other_policy = dict(self.policy, genesis_hash=b"h" * 32)
        result = self.verify(other, policy=other_policy, replay=registry)
        self.assertEqual(result["outcome"], "VALID")

    def test_predecessor_list_is_unverifiable_without_resolver(self):
        # No predecessor resolver is configured in v1: any non-empty
        # predecessor list is UNVERIFIABLE, even when the claimed digest
        # matches a known prior event.
        pred = dict(self.event)
        pred["event_id"] = b"p" * 32
        pred_digest = event_digest(pred)
        changed = dict(self.event)
        changed["predecessors"] = [{"event_id": b"p" * 32, "digest": pred_digest}]
        self.resign(changed)
        result = self.verify(changed)
        self.assertEqual(result["outcome"], "UNVERIFIABLE")
        self.assertIn("predecessor resolver", result["reason"])

    def test_unknown_predecessor_is_unverifiable(self):
        changed = dict(self.event)
        changed["predecessors"] = [{"event_id": b"p" * 32, "digest": b"d" * 32}]
        self.resign(changed)
        result = self.verify(changed)
        self.assertEqual(result["outcome"], "UNVERIFIABLE")

    def test_predecessor_mismatch_is_unverifiable(self):
        changed = dict(self.event)
        changed["predecessors"] = [{"event_id": b"p" * 32, "digest": b"d" * 32}]
        self.resign(changed)
        result = self.verify(changed)
        self.assertEqual(result["outcome"], "UNVERIFIABLE")

    def test_dispute_overrides_valid_but_not_invalid(self):
        result = self.verify(dispute_open=True)
        self.assertEqual(result["outcome"], "DISPUTED")
        changed = dict(self.event)
        changed["claims"] = {"invoice_total_minor": 99999, "currency": "USD"}
        result = self.verify(changed, dispute_open=True)
        self.assertEqual(result["outcome"], "INVALID")

    def test_duplicate_signer_key_is_invalid(self):
        changed = dict(self.event)
        changed["signatures"] = [self.event["signatures"][0],
                                 self.event["signatures"][0]]
        self.assertEqual(self.verify(changed)["outcome"], "INVALID")

    def test_signature_policy_version_mismatch_is_invalid(self):
        changed = dict(self.event)
        changed["signatures"] = [dict(self.event["signatures"][0], policy_version=99)]
        self.assertEqual(self.verify(changed)["outcome"], "INVALID")

    def test_expired_signing_key_is_invalid(self):
        trust = {"seller-key-1": dict(self.trust["seller-key-1"],
                                      expires_at=self.now)}
        self.assertEqual(self.verify(trust=trust)["outcome"], "INVALID")

    def test_not_yet_valid_event_is_invalid(self):
        changed = dict(self.event)
        changed["issued_at"] = self.now + 10
        changed["expires_at"] = self.now + 700
        self.resign(changed)
        self.assertEqual(self.verify(changed)["outcome"], "INVALID")

    def test_validity_interval_over_policy_max_is_invalid(self):
        policy = dict(self.policy, max_ttl=60)
        self.assertEqual(self.verify(policy=policy)["outcome"], "INVALID")

    def test_future_revocation_snapshot_is_unverifiable(self):
        result = verify_event(self.event, self.policy, self.trust,
                              replay=ReplayRegistry(), now=self.now,
                              revocation_updated_at=self.now + 60)
        self.assertEqual(result["outcome"], "UNVERIFIABLE")

    def test_unknown_trust_key_is_unverifiable(self):
        changed = dict(self.event)
        changed["signatures"] = [dict(self.event["signatures"][0],
                                      key_id="no-such-key")]
        self.assertEqual(self.verify(changed)["outcome"], "UNVERIFIABLE")

    def test_malformed_trust_entry_fails_closed(self):
        bad_roles = {"seller-key-1": dict(self.trust["seller-key-1"], roles="seller")}
        self.assertEqual(self.verify(trust=bad_roles)["outcome"], "UNVERIFIABLE")
        bad_time = {"seller-key-1": dict(self.trust["seller-key-1"],
                                         not_before="soon")}
        self.assertEqual(self.verify(trust=bad_time)["outcome"], "UNVERIFIABLE")
        bad_key = {"seller-key-1": dict(self.trust["seller-key-1"],
                                        public_key=b"short")}
        self.assertEqual(self.verify(trust=bad_key)["outcome"], "UNVERIFIABLE")

    def test_malformed_policy_or_trust_store_fails_closed(self):
        self.assertEqual(self.verify(policy=["not", "a", "mapping"])["outcome"],
                         "UNVERIFIABLE")
        self.assertEqual(self.verify(trust=["not", "a", "mapping"])["outcome"],
                         "UNVERIFIABLE")
        self.assertEqual(self.verify(policy={
            "policy_id": "invoice-approval-v1",
            "network": "excal-testnet", "genesis_hash": b"g" * 32})
            ["outcome"], "UNVERIFIABLE")
        self.assertEqual(self.verify(now="not-a-time")["outcome"], "UNVERIFIABLE")

    def test_distinct_organizations_policy(self):
        buyer_private = Ed25519PrivateKey.from_private_bytes(bytes(range(33, 65)))
        buyer_public = buyer_private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw)
        policy = dict(self.policy, required_roles=["seller", "buyer"],
                      distinct_organizations=True)
        trust_same_org = dict(self.trust)
        trust_same_org["buyer-key-1"] = {
            "public_key": buyer_public, "roles": ["buyer"],
            "org_id": "seller-inc", "not_before": self.now - 100,
            "expires_at": self.now + 1000, "revoked": False,
        }
        event = dict(self.event)
        event["signatures"] = [
            sign_event(event, self.private, "seller-key-1", "seller", 1),
            sign_event(event, buyer_private, "buyer-key-1", "buyer", 1),
        ]
        result = self.verify(event, policy=policy, trust=trust_same_org)
        self.assertEqual(result["outcome"], "INVALID")
        trust_distinct = dict(trust_same_org)
        trust_distinct["buyer-key-1"] = dict(trust_same_org["buyer-key-1"],
                                             org_id="buyer-corp")
        result = self.verify(event, policy=policy, trust=trust_distinct)
        self.assertEqual(result["outcome"], "VALID")


def _decode_vectors(value):
    """Decode the $bytes markers used in the published vectors file."""
    if isinstance(value, dict):
        if set(value) == {"$bytes"}:
            return bytes.fromhex(value["$bytes"])
        return {k: _decode_vectors(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode_vectors(v) for v in value]
    return value


class VectorTests(unittest.TestCase):
    """Pin every published vector by independent recomputation."""

    @classmethod
    def setUpClass(cls):
        cls.vectors = json.loads(VECTORS_PATH.read_text(encoding="utf-8"))

    def test_vectors_are_reproducible(self):
        self.assertEqual(build_vectors(), self.vectors)

    def test_cbor_vectors(self):
        for case in self.vectors["cbor"]:
            value = _decode_vectors(case["json"])
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
        event = _decode_vectors(self.vectors["event"])
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
                    revocation_updated_at=bundle.get("revocation_updated_at"))
                self.assertEqual(report["outcome"], case["expected_outcome"])


def _run_cli(*args):
    return subprocess.run([sys.executable, "-m", "pcbe.cli", *args],
                          cwd=REPO_ROOT, capture_output=True, text=True, timeout=120)


class CLITests(unittest.TestCase):
    """End-to-end tests for the offline PCBE CLI (``python3 -m pcbe.cli``)."""

    def test_example_bundle_verifies_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "bundle.json"
            result = _run_cli("example", "--out", str(bundle))
            self.assertEqual(result.returncode, 0, result.stderr)
            result = _run_cli("verify", "--bundle", str(bundle), "--now", "1800000000")
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["outcome"], "VALID")
            self.assertEqual(report["event_digest"],
                             "83e67afa323b48091c595af5b2c9494bc48a387e67e4c3d0bba141405cb6bf19")

    def test_tampered_bundle_exits_1_invalid(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "bundle.json"
            self.assertEqual(_run_cli("example", "--out", str(bundle)).returncode, 0)
            data = json.loads(bundle.read_text(encoding="utf-8"))
            data["event"]["claims"]["invoice_total_minor"] = 99999
            bundle.write_text(json.dumps(data), encoding="utf-8")
            result = _run_cli("verify", "--bundle", str(bundle), "--now", "1800000000")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["outcome"], "INVALID")

    def test_malformed_bundle_exits_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "bundle.json"
            bundle.write_text("{not json", encoding="utf-8")
            result = _run_cli("verify", "--bundle", str(bundle), "--now", "1800000000")
            self.assertEqual(result.returncode, 2)
            self.assertIn("invalid bundle", result.stderr)

    def test_missing_bundle_file_exits_2(self):
        result = _run_cli("verify", "--bundle", "/tmp/does-not-exist-pcbe.json")
        self.assertEqual(result.returncode, 2)

    def test_verify_without_now_uses_wall_clock(self):
        # The fixed example is dated 2027-01-15, so at the real wall clock
        # it is not yet valid: the CLI must report INVALID, not crash.
        with tempfile.TemporaryDirectory() as tmp:
            bundle = Path(tmp) / "bundle.json"
            self.assertEqual(_run_cli("example", "--out", str(bundle)).returncode, 0)
            result = _run_cli("verify", "--bundle", str(bundle))
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout)["outcome"], "INVALID")


if __name__ == "__main__":
    unittest.main()
