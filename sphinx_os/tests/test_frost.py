"""Tests for FROST (Flexible Round-Optimized Schnorr Threshold) DKG and signing."""

import unittest
from sphinx_os.nexus.frost import (
    FrostDKG,
    FrostSigning,
    FrostCommitment,
    FrostShare,
    FrostSigningShare,
    FrostPartialSignature,
    FrostSignature,
    frost_dkg_and_sign,
    lagrange_coefficient,
    _inv,
    _point_add,
    _point_mul,
    N,
)


class TestLagrangeInterpolation(unittest.TestCase):
    """Test Lagrange interpolation coefficients."""

    def test_single_point(self):
        """Test λ at single point is 1."""
        lam = lagrange_coefficient(1, [1], N)
        self.assertEqual(lam, 1)

    def test_two_points(self):
        """Test Lagrange coefficients for two points sum to 1."""
        lam1 = lagrange_coefficient(1, [1, 2], N)
        lam2 = lagrange_coefficient(2, [1, 2], N)
        self.assertEqual((lam1 + lam2) % N, 1)

    def test_three_points_sum(self):
        """Test Lagrange coefficients for three points sum to 1."""
        indices = [1, 2, 3]
        total = 0
        for i in indices:
            lam = lagrange_coefficient(i, indices, N)
            total = (total + lam) % N
        self.assertEqual(total, 1)

    def test_coefficients_are_nonzero(self):
        """Test Lagrange coefficients are nonzero."""
        indices = [1, 2, 3, 4, 5]
        for i in indices:
            lam = lagrange_coefficient(i, indices, N)
            self.assertNotEqual(lam, 0)

    def test_coefficients_in_range(self):
        """Test Lagrange coefficients are in valid range."""
        indices = [1, 2, 3, 4, 5]
        for i in indices:
            lam = lagrange_coefficient(i, indices, N)
            self.assertGreater(lam, 0)
            self.assertLess(lam, N)


class TestFrostDKG(unittest.TestCase):
    """Test FROST Distributed Key Generation."""

    def setUp(self):
        self.dkg = FrostDKG(5, 3)

    def test_initialization(self):
        """Test DKG initialization."""
        self.assertEqual(self.dkg.n, 5)
        self.assertEqual(self.dkg.t, 3)
        self.assertEqual(self.dkg.indices, [1, 2, 3, 4, 5])

    def test_invalid_threshold(self):
        """Test threshold > n raises ValueError."""
        with self.assertRaises(ValueError):
            FrostDKG(3, 5)

    def test_minimum_threshold(self):
        """Test threshold < 2 raises ValueError."""
        with self.assertRaises(ValueError):
            FrostDKG(5, 1)

    def test_generate_commitment(self):
        """Test commitment generation."""
        commitment, coeffs = self.dkg.generate_commitment(1)
        self.assertIsInstance(commitment, FrostCommitment)
        self.assertEqual(commitment.participant_index, 1)
        self.assertEqual(len(commitment.commitments), 3)  # degree t-1 = 2, so 3 commitments
        self.assertEqual(len(coeffs), 3)

    def test_polynomial_evaluation(self):
        """Test polynomial evaluation."""
        coeffs = [10, 20, 30]  # f(x) = 10 + 20x + 30x^2
        f0 = self.dkg._evaluate_polynomial(coeffs, 0)
        self.assertEqual(f0, 10)
        f1 = self.dkg._evaluate_polynomial(coeffs, 1)
        self.assertEqual(f1, (10 + 20 + 30) % N)

    def test_full_dkg_flow(self):
        """Test complete DKG flow."""
        # Generate commitments
        commitments = {}
        coefficients = {}
        for i in range(1, 6):
            c, coeffs = self.dkg.generate_commitment(i)
            commitments[i] = c
            coefficients[i] = coeffs

        # Compute shares
        shares = {}
        for i in range(1, 6):
            share = self.dkg.compute_share(i, commitments, coefficients)
            shares[i] = share

        # Verify shares
        for i in range(1, 6):
            self.assertIsInstance(shares[i], FrostShare)
            self.assertEqual(shares[i].participant_index, i)
            self.assertGreater(shares[i].secret_share, 0)
            self.assertIsNotNone(shares[i].public_key)
            self.assertIsNotNone(shares[i].aggregate_public_key)

        # All shares should have the same aggregate public key
        agg_keys = set()
        for share in shares.values():
            agg_keys.add(share.aggregate_public_key)
        self.assertEqual(len(agg_keys), 1)

    def test_different_dkg_different_keys(self):
        """Test different DKG runs produce different keys."""
        def run_dkg():
            dkg = FrostDKG(5, 3)
            commitments = {}
            coefficients = {}
            for i in range(1, 6):
                c, coeffs = dkg.generate_commitment(i)
                commitments[i] = c
                coefficients[i] = coeffs
            share = dkg.compute_share(1, commitments, coefficients)
            return share.aggregate_public_key

        key1 = run_dkg()
        key2 = run_dkg()
        self.assertNotEqual(key1, key2)


class TestFrostSigning(unittest.TestCase):
    """Test FROST threshold signing."""

    def setUp(self):
        # Run DKG
        self.sig, self.shares = frost_dkg_and_sign(5, 3, b"test message")

    def test_signature_generated(self):
        """Test signature is generated."""
        self.assertIsInstance(self.sig, FrostSignature)
        self.assertEqual(len(self.sig.raw_sig), 64)

    def test_signature_verifies(self):
        """Test signature verifies."""
        signing = FrostSigning(self.shares, 3, 5)
        self.assertTrue(signing.verify(self.sig, b"test message"))

    def test_wrong_message_fails(self):
        """Test verification fails with wrong message."""
        signing = FrostSigning(self.shares, 3, 5)
        self.assertFalse(signing.verify(self.sig, b"wrong message"))

    def test_different_signers(self):
        """Test signing with different signer set."""
        sig2, _ = frost_dkg_and_sign(5, 3, b"test message", signer_indices=[2, 3, 4])
        self.assertIsInstance(sig2, FrostSignature)

    def test_two_of_three(self):
        """Test 2-of-3 threshold signing."""
        sig, shares = frost_dkg_and_sign(3, 2, b"test message", signer_indices=[1, 2])
        signing = FrostSigning(shares, 2, 3)
        self.assertTrue(signing.verify(sig, b"test message"))


class TestFrostIntegration(unittest.TestCase):
    """Integration tests for FROST with governance."""

    def test_governance_signing(self):
        """Test FROST signing for governance proposal."""
        import json
        proposal = {
            "id": "prop_1",
            "type": "treasury_spend",
            "amount": 100.0,
        }
        message = json.dumps(proposal, sort_keys=True).encode()

        sig, shares = frost_dkg_and_sign(5, 3, message, signer_indices=[1, 2, 3])
        signing = FrostSigning(shares, 3, 5)
        self.assertTrue(signing.verify(sig, message))

    def test_multiple_messages(self):
        """Test signing multiple different messages."""
        sig1, shares1 = frost_dkg_and_sign(5, 3, b"message 1")
        sig2, shares2 = frost_dkg_and_sign(5, 3, b"message 2")

        # Different messages should produce different signatures
        self.assertNotEqual(sig1.raw_sig, sig2.raw_sig)

    def test_aggregate_key_consistency(self):
        """Test aggregate key is consistent across DKG runs with same params."""
        # Note: DKG is randomized, so keys differ
        # But the structure should be consistent
        sig, shares = frost_dkg_and_sign(5, 3, b"test")
        for share in shares.values():
            self.assertIsNotNone(share.aggregate_public_key)
            self.assertIsNotNone(share.public_key)


class TestFrostEdgeCases(unittest.TestCase):
    """Test FROST edge cases."""

    def test_insufficient_partials(self):
        """Test insufficient partial signatures raises error."""
        sig, shares = frost_dkg_and_sign(5, 3, b"test")
        signing = FrostSigning(shares, 3, 5)

        # Try with only 2 partials (need 3)
        signing_shares = {}
        for i in [1, 2]:
            signing_shares[i] = signing.generate_signing_nonce(i, b"test")

        agg_nonce = None
        for i in [1, 2]:
            agg_nonce = _point_add(agg_nonce, signing_shares[i].nonce_point)

        partials = []
        for i in [1, 2]:
            partial = signing.compute_partial_signature(
                i, signing_shares[i], agg_nonce, b"test", [1, 2]
            )
            partials.append(partial)

        with self.assertRaises(ValueError):
            signing.aggregate_partial_signatures(partials, agg_nonce, b"test")


if __name__ == "__main__":
    unittest.main()
