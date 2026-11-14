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
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from excal_wallet import (
    WalletBackend,
    format_balance,
    generate_keypair,
    validate_address,
    sign_transaction,
)


class TestAddressValidation(unittest.TestCase):
    """Test address validation in EXCAL wallet."""

    def test_valid_addresses(self):
        """Valid 40-char uppercase hex PQH addresses should pass."""
        self.assertTrue(validate_address("A1B2C3D4E5F6A7B2C3D4" * 2))
        self.assertTrue(validate_address("0" * 40))
        self.assertTrue(validate_address("F" * 40))

    def test_invalid_length(self):
        """Wrong length should fail."""
        self.assertFalse(validate_address("SHORT"))
        self.assertFalse(validate_address("A" * 42))
        self.assertFalse(validate_address(""))

    def test_invalid_chars(self):
        """Non-hex characters should fail."""
        self.assertFalse(validate_address("A" * 38 + "GG"))
        self.assertFalse(validate_address("INVALID!@#$%^&*()"))

    def test_lowercase_rejected(self):
        """Lowercase should be rejected."""
        self.assertFalse(validate_address("a" * 40))

    def test_none_input(self):
        """None should return False."""
        self.assertFalse(validate_address(None))


class TestAddressGeneration(unittest.TestCase):
    """Test address generation."""

    def test_generated_address_valid(self):
        """Generated addresses should pass validation."""
        kp = generate_keypair()
        self.assertTrue(validate_address(kp["address"]))
        from wallet_transactions import address_lock
        import txscript
        self.assertEqual(
            address_lock(kp["address"]),
            txscript.lock_pqh(bytes.fromhex(kp["address"])),
        )


class TestTransactionValidation(unittest.TestCase):
    """Test transaction signing."""

    def test_signature_format(self):
        """Signature should be 64-char hex."""
        with self.assertRaises(RuntimeError):
            sign_transaction("key", {"from": "A", "to": "B", "amount": 1.0})

    def test_excal_balance_uses_eight_sword_decimals(self):
        self.assertEqual(format_balance("1.00000001"), "1.00000001")


class TestWalletBackend(unittest.TestCase):
    def setUp(self):
        self.backend = WalletBackend()
        self.address = "AA" * 20
        self.entry = SimpleNamespace(
            address=self.address,
            public_key="11" * 32,
            label="Main",
        )

        class FakeKeyStore:
            def get_key(self, address, passphrase):
                return "01" * 32

            def add_transaction(self, transaction):
                self.transaction = transaction

            def save(self, path):
                pass

        self.keystore = FakeKeyStore()
        self.keystore.keys = [self.entry]
        self.backend.keystore = self.keystore
        self.backend._passphrase = "test passphrase"
        self.tempdir = tempfile.TemporaryDirectory()
        self.backend.keystore_path = Path(self.tempdir.name) / "keystore.json"
        self.utxo = {
            "txid": "22" * 32,
            "vout": 0,
            "value": 500_000_000,
            "script": bytes.fromhex("02" + "AA" * 20).hex(),
            "coinbase": False,
            "height": 1,
            "tip_height": 100,
            "mature": True,
            "pending_spend": False,
            "spendable": True,
        }

    def tearDown(self):
        self.tempdir.cleanup()

    def test_create_wallet_never_overwrites_existing_keystore(self):
        self.backend.keystore_path.parent.mkdir(parents=True, exist_ok=True)
        self.backend.keystore_path.write_text("existing wallet")
        with patch("excal_wallet.KeyStore.create") as create:
            with self.assertRaises(FileExistsError):
                self.backend.create_wallet("test passphrase")
        create.assert_not_called()
        self.assertEqual(
            self.backend.keystore_path.read_text(), "existing wallet")

    def test_balance_uses_complete_node_utxos_for_all_wallet_addresses(self):
        self.backend._rpc = lambda method, params: {
            "complete": True,
            "utxos": [self.utxo],
        }
        self.assertEqual(self.backend.get_balance(), 5.0)

    def test_incomplete_node_state_is_not_reported_as_zero_balance(self):
        self.backend._rpc = lambda method, params: {
            "complete": False,
            "utxos": [],
            "error": "validated UTXO state unavailable",
        }
        with self.assertRaisesRegex(RuntimeError, "validated UTXO state unavailable"):
            self.backend.get_balance()

    def test_demo_address_wallet_is_rejected_for_on_chain_balance(self):
        self.keystore.keys[0].address = "A" * 20
        with self.assertRaisesRegex(RuntimeError, "demo-format keys"):
            self.backend.get_balance()

    def test_send_uses_exact_amount_and_broadcasts_consensus_transaction(self):
        import txscript

        raw_tx = b"consensus transaction"
        expected_txid = txscript.txid_display(raw_tx)
        with patch.object(
                self.backend, "_rpc",
                side_effect=[
                    {"complete": True, "utxos": [self.utxo]},
                    expected_txid,
                ]) as rpc, patch(
                    "excal_wallet.build_pqh_transaction",
                    return_value=raw_tx,
                ) as build:
            result = self.backend.send_transaction(
                "BB" * 20, "0.00000001")

        self.assertEqual(result["tx_id"], expected_txid)
        self.assertEqual(result["status"], "node_accepted_unconfirmed")
        self.assertEqual(build.call_args.kwargs["amount"], "0.00000001")
        self.assertEqual(len(build.call_args.kwargs["keys"]), 1)
        self.assertEqual(
            rpc.call_args_list[-1].args,
            ("sendrawtransaction", [raw_tx.hex()]),
        )


if __name__ == "__main__":
    unittest.main()
