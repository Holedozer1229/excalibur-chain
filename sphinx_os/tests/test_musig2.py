"""Tests for MuSig2 (BIP-327) production threshold signing."""

import hashlib
import unittest
from sphinx_os.nexus.musig2 import (
    MuSig2,
    MuSig2KeyPair,
    MuSig2Nonce,
    MuSig2PartialSignature,
    MuSig2Signature,
    musig2_sign,
    musig2_verify,
    _inv,
    _point_add,
    _point_mul,
    _tagged_hash,
    _pubkey_to_xonly,
    _xonly_to_point,
    _challenge,
    P,
    N,
    G,
)


class TestFieldArithmetic(unittest.TestCase):
    """Test secp256k1 field arithmetic."""

    def test_inverse(self):
        """Test modular inverse."""
        for a in [1, 2, 3, 100, 123456789]:
            self.assertEqual((a * _inv(a, N)) % N, 1)

    def test_point_add_identity(self):
        """Test point addition with identity (None)."""
        self.assertIsNone(_point_add(None, None))
        self.assertEqual(_point_add(None, G), G)
        self.assertEqual(_point_add(G, None), G)

    def test_point_add_inverse(self):
        """Test P + (-P) = None."""
        neg_g = (G[0], (P - G[1]) % P)
        self.assertIsNone(_point_add(G, neg_g))

    def test_point_mul_identity(self):
        """Test 1*G = G."""
        self.assertEqual(_point_mul(1), G)

    def test_point_mul_zero(self):
        """Test 0*G = None (point at infinity)."""
        self.assertIsNone(_point_mul(0))

    def test_point_mul_order(self):
        """Test N*G = None (point at infinity)."""
        self.assertIsNone(_point_mul(N))

    def test_point_mul_associative(self):
        """Test (a+b)*G = a*G + b*G."""
        a, b = 12345, 67890
        lhs = _point_mul(a + b)
        rhs = _point_add(_point_mul(a), _point_mul(b))
        self.assertEqual(lhs, rhs)


class TestBIP340Utilities(unittest.TestCase):
    """Test BIP-340 Schnorr utilities."""

    def test_tagged_hash(self):
        """Test tagged hash produces deterministic output."""
        h1 = _tagged_hash("test", b"data")
        h2 = _tagged_hash("test", b"data")
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 32)

    def test_tagged_hash_different_tags(self):
        """Test different tags produce different hashes."""
        h1 = _tagged_hash("tag1", b"data")
        h2 = _tagged_hash("tag2", b"data")
        self.assertNotEqual(h1, h2)

    def test_pubkey_to_xonly(self):
        """Test x-only public key conversion."""
        xonly = _pubkey_to_xonly(G)
        self.assertEqual(len(xonly), 32)
        self.assertEqual(int.from_bytes(xonly, "big"), G[0])

    def test_xonly_to_point(self):
        """Test x-only to point recovery."""
        xonly = _pubkey_to_xonly(G)
        recovered = _xonly_to_point(int.from_bytes(xonly, "big"))
        self.assertEqual(recovered[0], G[0])
        # y should be even (BIP-340 convention)
        self.assertEqual(recovered[1] % 2, 0)

    def test_challenge_deterministic(self):
        """Test challenge computation is deterministic."""
        msg = b"test message"
        q_point = _xonly_to_point(int.from_bytes(b"\x01" * 32, "big"))
        r_point = _xonly_to_point(int.from_bytes(b"\x02" * 32, "big"))
        e1 = _challenge(r_point, q_point, msg)
        e2 = _challenge(r_point, q_point, msg)
        self.assertEqual(e1, e2)
        self.assertLess(e1, N)


class TestMuSig2KeyGeneration(unittest.TestCase):
    """Test MuSig2 key pair generation."""

    def setUp(self):
        self.musig = MuSig2()

    def test_generate_key_pair(self):
        """Test key pair generation."""
        key = self.musig.generate_key_pair(0)
        self.assertIsInstance(key, MuSig2KeyPair)
        self.assertGreater(key.secret_key, 0)
        self.assertLess(key.secret_key, N)
        self.assertEqual(len(key.xonly_pubkey), 32)
        self.assertEqual(key.participant_index, 0)

    def test_generate_key_from_seed(self):
        """Test deterministic key generation from seed."""
        seed = b"deterministic seed"
        key1 = self.musig.generate_key_from_seed(seed, 0)
        key2 = self.musig.generate_key_from_seed(seed, 0)
        self.assertEqual(key1.secret_key, key2.secret_key)
        self.assertEqual(key1.xonly_pubkey, key2.xonly_pubkey)

    def test_different_seeds_different_keys(self):
        """Test different seeds produce different keys."""
        key1 = self.musig.generate_key_from_seed(b"seed1", 0)
        key2 = self.musig.generate_key_from_seed(b"seed2", 0)
        self.assertNotEqual(key1.secret_key, key2.secret_key)

    def test_different_indices_different_keys(self):
        """Test different indices produce different keys."""
        key1 = self.musig.generate_key_from_seed(b"seed", 0)
        key2 = self.musig.generate_key_from_seed(b"seed", 1)
        self.assertNotEqual(key1.secret_key, key2.secret_key)

    def test_public_key_is_correct(self):
        """Test public key is secret * G."""
        sk = 12345
        key = self.musig.generate_key_pair(0, sk)
        expected = _point_mul(sk)
        self.assertEqual(key.public_key, expected)


class TestMuSig2KeyAggregation(unittest.TestCase):
    """Test MuSig2 key aggregation."""

    def setUp(self):
        self.musig = MuSig2()
        self.keys = [
            self.musig.generate_key_from_seed(b"key", i)
            for i in range(5)
        ]

    def test_aggregate_two_keys(self):
        """Test aggregation of two keys."""
        agg_point, agg_xonly = self.musig.aggregate_public_keys(self.keys[:2])
        self.assertIsNotNone(agg_point)
        self.assertEqual(len(agg_xonly), 32)

    def test_aggregate_all_keys(self):
        """Test aggregation of all 5 keys."""
        agg_point, agg_xonly = self.musig.aggregate_public_keys(self.keys)
        self.assertIsNotNone(agg_point)
        self.assertEqual(len(agg_xonly), 32)

    def test_aggregate_is_deterministic(self):
        """Test aggregation is deterministic."""
        _, agg1 = self.musig.aggregate_public_keys(self.keys)
        _, agg2 = self.musig.aggregate_public_keys(self.keys)
        self.assertEqual(agg1, agg2)

    def test_aggregate_order_independent(self):
        """Test aggregation is order-independent (sorted by index)."""
        import random
        shuffled = list(self.keys)
        random.shuffle(shuffled)
        _, agg1 = self.musig.aggregate_public_keys(self.keys)
        _, agg2 = self.musig.aggregate_public_keys(shuffled)
        self.assertEqual(agg1, agg2)

    def test_empty_keys_raises(self):
        """Test empty key list raises ValueError."""
        with self.assertRaises(ValueError):
            self.musig.aggregate_public_keys([])


class TestMuSig2NonceGeneration(unittest.TestCase):
    """Test MuSig2 nonce generation."""

    def setUp(self):
        self.musig = MuSig2()
        self.keys = [
            self.musig.generate_key_from_seed(b"key", i)
            for i in range(3)
        ]
        self.agg_point, self.agg_xonly = self.musig.aggregate_public_keys(self.keys)
        self.message = b"test message for signing"

    def test_nonce_generation(self):
        """Test nonce generation."""
        nonce = self.musig.generate_nonce(self.keys[0], self.agg_xonly, self.message)
        self.assertIsInstance(nonce, MuSig2Nonce)
        self.assertEqual(nonce.participant_index, 0)
        self.assertIsNotNone(nonce.nonce_point)
        self.assertGreater(nonce.nonce_secret, 0)

    def test_nonce_is_deterministic_with_seed(self):
        """Test nonce is deterministic with same seed."""
        seed = b"nonce seed"
        n1 = self.musig.generate_nonce(self.keys[0], self.agg_xonly, self.message, seed)
        n2 = self.musig.generate_nonce(self.keys[0], self.agg_xonly, self.message, seed)
        self.assertEqual(n1.nonce_secret, n2.nonce_secret)

    def test_nonce_differs_without_seed(self):
        """Test nonce differs without seed (random)."""
        n1 = self.musig.generate_nonce(self.keys[0], self.agg_xonly, self.message)
        n2 = self.musig.generate_nonce(self.keys[0], self.agg_xonly, self.message)
        self.assertNotEqual(n1.nonce_secret, n2.nonce_secret)

    def test_aggregate_nonces(self):
        """Test nonce aggregation."""
        nonces = [
            self.musig.generate_nonce(k, self.agg_xonly, self.message, b"seed")
            for k in self.keys
        ]
        agg = self.musig.aggregate_nonces(nonces)
        self.assertIsNotNone(agg)


class TestMuSig2PartialSigning(unittest.TestCase):
    """Test MuSig2 partial signature computation."""

    def setUp(self):
        self.musig = MuSig2()
        self.keys = [
            self.musig.generate_key_from_seed(b"key", i)
            for i in range(3)
        ]
        self.agg_point, self.agg_xonly = self.musig.aggregate_public_keys(self.keys)
        self.message = b"test message"
        self.all_xonly = [k.xonly_pubkey for k in self.keys]

        # Generate nonces with deterministic seeds
        self.nonces = [
            self.musig.generate_nonce(k, self.agg_xonly, self.message, f"seed{i}".encode())
            for i, k in enumerate(self.keys)
        ]
        self.agg_nonce = self.musig.aggregate_nonces(self.nonces)

    def test_partial_signature(self):
        """Test partial signature computation."""
        partial = self.musig.partial_sign(
            self.keys[0], self.nonces[0], self.agg_nonce,
            self.agg_point, self.agg_xonly, self.message, self.all_xonly,
        )
        self.assertIsInstance(partial, MuSig2PartialSignature)
        self.assertEqual(partial.participant_index, 0)
        self.assertGreater(partial.partial_sig, 0)

    def test_all_partials(self):
        """Test partial signatures for all participants."""
        partials = [
            self.musig.partial_sign(
                k, n, self.agg_nonce, self.agg_point, self.agg_xonly, self.message, self.all_xonly
            )
            for k, n in zip(self.keys, self.nonces)
        ]
        self.assertEqual(len(partials), 3)


class TestMuSig2FullSigning(unittest.TestCase):
    """Test complete MuSig2 signing flow."""

    def setUp(self):
        self.musig = MuSig2()
        self.keys = [
            self.musig.generate_key_from_seed(b"key", i)
            for i in range(5)
        ]
        self.message = b"AetherionEXCAL governance proposal #1"

    def test_full_signing_flow(self):
        """Test complete signing flow: key agg, nonce, partial, aggregate, verify."""
        # Aggregate keys
        agg_point, agg_xonly = self.musig.aggregate_public_keys(self.keys)

        # Generate nonces
        nonces = [
            self.musig.generate_nonce(k, agg_xonly, self.message, f"seed{i}".encode())
            for i, k in enumerate(self.keys)
        ]

        # Aggregate nonces
        agg_nonce = self.musig.aggregate_nonces(nonces)

        # Collect x-only pubkeys
        all_xonly = [k.xonly_pubkey for k in self.keys]

        # Compute partial signatures
        partials = [
            self.musig.partial_sign(k, n, agg_nonce, agg_point, agg_xonly, self.message, all_xonly)
            for k, n in zip(self.keys, nonces)
        ]

        # Aggregate signatures
        sig = self.musig.aggregate_signatures(partials, agg_nonce, self.message, agg_xonly)

        # Verify
        self.assertTrue(self.musig.verify(sig, agg_xonly, self.message))

    def test_signature_is_64_bytes(self):
        """Test signature is 64 bytes (BIP-340 format)."""
        sig = musig2_sign(self.keys, self.message)
        self.assertEqual(len(sig.raw_sig), 64)

    def test_verify_raw_signature(self):
        """Test raw signature verification."""
        sig = musig2_sign(self.keys, self.message)
        self.assertTrue(musig2_verify(sig.raw_sig, self.keys, self.message))

    def test_wrong_message_fails(self):
        """Test verification fails with wrong message."""
        sig = musig2_sign(self.keys, self.message)
        self.assertFalse(musig2_verify(sig.raw_sig, self.keys, b"wrong message"))

    def test_threshold_signing_3_of_5(self):
        """Test 3-of-5 threshold signing."""
        sig = musig2_sign(self.keys, self.message, signer_indices=[0, 1, 2])
        self.assertTrue(musig2_verify(sig.raw_sig, self.keys, self.message, [0, 1, 2]))

    def test_different_signer_sets_different_sig(self):
        """Test different signer sets produce different signatures."""
        sig1 = musig2_sign(self.keys, self.message, signer_indices=[0, 1, 2])
        sig2 = musig2_sign(self.keys, self.message, signer_indices=[2, 3, 4])
        self.assertNotEqual(sig1.raw_sig, sig2.raw_sig)

    def test_single_signer(self):
        """Test single signer works."""
        sig = musig2_sign(self.keys, self.message, signer_indices=[0])
        # Verify using the musig2 instance directly with the aggregate key
        musig = MuSig2()
        single_keys = [k for k in self.keys if k.participant_index in [0]]
        _, agg_xonly = musig.aggregate_public_keys(single_keys)
        self.assertTrue(musig.verify_raw(sig.raw_sig, agg_xonly, self.message))

    def test_all_signers(self):
        """Test all 5 signers."""
        sig = musig2_sign(self.keys, self.message)
        self.assertTrue(musig2_verify(sig.raw_sig, self.keys, self.message))


class TestMuSig2EdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def setUp(self):
        self.musig = MuSig2()

    def test_invalid_signature_length(self):
        """Test verification rejects invalid signature length."""
        keys = [self.musig.generate_key_from_seed(b"key", i) for i in range(2)]
        _, agg_xonly = self.musig.aggregate_public_keys(keys)
        self.assertFalse(self.musig.verify_raw(b"short", agg_xonly, b"msg"))

    def test_invalid_pubkey_length(self):
        """Test verification rejects invalid pubkey length."""
        self.assertFalse(self.musig.verify_raw(b"\x00" * 64, b"short", b"msg"))

    def test_scaling_factor_in_range(self):
        """Test scaling factors are in valid range."""
        keys = [self.musig.generate_key_from_seed(b"key", i) for i in range(3)]
        all_xonly = [k.xonly_pubkey for k in keys]
        for i, k in enumerate(keys):
            a_i = self.musig._compute_scaling_factor(i, k.xonly_pubkey, all_xonly)
            self.assertGreater(a_i, 0)
            self.assertLess(a_i, N)


class TestMuSig2Integration(unittest.TestCase):
    """Integration tests for MuSig2 with governance."""

    def test_governance_proposal_signing(self):
        """Test signing a governance proposal hash."""
        musig = MuSig2()
        keys = [
            musig.generate_key_from_seed(b"knights", i)
            for i in range(5)
        ]

        # Simulate a governance proposal
        proposal = {
            "id": "prop_1",
            "type": "treasury_spend",
            "amount": 100.0,
            "recipient": "bc1qtest",
        }
        import json
        proposal_data = json.dumps(proposal, sort_keys=True).encode()
        proposal_hash = hashlib.sha256(proposal_data).digest()

        # 3-of-5 sign
        sig = musig2_sign(keys, proposal_hash, signer_indices=[0, 1, 2])
        self.assertTrue(musig2_verify(sig.raw_sig, keys, proposal_hash, [0, 1, 2]))

    def test_treasury_withdrawal_signing(self):
        """Test signing a treasury withdrawal."""
        musig = MuSig2()
        keys = [
            musig.generate_key_from_seed(b"treasury", i)
            for i in range(5)
        ]

        withdrawal = b"withdraw:50:bc1qrecipient"
        sig = musig2_sign(keys, withdrawal, signer_indices=[1, 2, 3])
        self.assertTrue(musig2_verify(sig.raw_sig, keys, withdrawal, [1, 2, 3]))


if __name__ == "__main__":
    unittest.main()
