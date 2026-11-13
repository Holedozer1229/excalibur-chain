#!/usr/bin/env python3
"""Tests for excal_wallet.py address validation and transaction logic.

Covers:
- Address validation in GUI wallet
- Transaction validation (amount, address)
- Key generation
"""

import unittest
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from excal_wallet import (
    generate_address,
    generate_keypair,
    validate_address,
    sha256_hex,
    sign_transaction,
)


class TestAddressValidation(unittest.TestCase):
    """Test address validation in EXCAL wallet."""

    def test_valid_addresses(self):
        """Valid 20-char uppercase hex addresses should pass."""
        self.assertTrue(validate_address("A1B2C3D4E5F6A7B2C3D4"))
        self.assertTrue(validate_address("00000000000000000000"))
        self.assertTrue(validate_address("FFFFFFFFFFFFFFFFFFFF"))

    def test_invalid_length(self):
        """Wrong length should fail."""
        self.assertFalse(validate_address("SHORT"))
        self.assertFalse(validate_address("TOOLONGADDRESS1234567890"))
        self.assertFalse(validate_address(""))

    def test_invalid_chars(self):
        """Non-hex characters should fail."""
        self.assertFalse(validate_address("A1B2C3D4E5F6A7B2C3GG"))
        self.assertFalse(validate_address("INVALID!@#$%^&*()"))

    def test_lowercase_rejected(self):
        """Lowercase should be rejected."""
        self.assertFalse(validate_address("a1b2c3d4e5f6a7b2c3d4"))

    def test_none_input(self):
        """None should return False."""
        self.assertFalse(validate_address(None))


class TestAddressGeneration(unittest.TestCase):
    """Test address generation."""

    def test_generated_address_valid(self):
        """Generated addresses should pass validation."""
        addr = generate_address("test")
        self.assertTrue(validate_address(addr))

    def test_keypair_address_valid(self):
        """Key pair address should pass validation."""
        kp = generate_keypair()
        self.assertTrue(validate_address(kp["address"]))


class TestTransactionValidation(unittest.TestCase):
    """Test transaction signing."""

    def test_signature_format(self):
        """Signature should be 64-char hex."""
        sig = sign_transaction("key", {"from": "A", "to": "B", "amount": 1.0})
        self.assertEqual(len(sig), 64)
        int(sig, 16)  # Should not raise


if __name__ == "__main__":
    unittest.main()
