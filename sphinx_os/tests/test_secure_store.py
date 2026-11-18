"""Tests for the secure key storage module."""

import os
import json
import tempfile
import unittest
from sphinx_os.secure_store import KeyStore


class TestKeyStore(unittest.TestCase):
    """Test cases for the KeyStore encrypted storage."""

    def setUp(self):
        """Create a temporary directory for test keystores."""
        self.tmpdir = tempfile.mkdtemp()
        self.keystore_path = os.path.join(self.tmpdir, "test_keystore.json")
        self.passphrase = "test_passphrase_123"

    def tearDown(self):
        """Clean up temporary files."""
        if os.path.exists(self.keystore_path):
            os.remove(self.keystore_path)
        os.rmdir(self.tmpdir)

    def test_create_keystore(self):
        """Test creating a new keystore."""
        ks = KeyStore.create(self.passphrase, self.keystore_path)
        self.assertTrue(os.path.exists(self.keystore_path))
        self.assertEqual(ks.get_key_count(), 0)
        self.assertEqual(ks.get_balance(), 0.0)

    def test_create_short_passphrase(self):
        """Test that short passphrase is rejected."""
        with self.assertRaises(ValueError):
            KeyStore.create("ab", self.keystore_path)

    def test_add_and_retrieve_key(self):
        """Test adding a key and retrieving the private key."""
        ks = KeyStore.create(self.passphrase, self.keystore_path)
        ks.add_key(
            private_key="deadbeef0123456789abcdef",
            public_key="pub1234567890abcdef",
            address="ADDR1234567890ABCDEF",
            label="Test Key",
        )
        ks.save(self.keystore_path)

        self.assertEqual(ks.get_key_count(), 1)
        pk = ks.get_private_key("ADDR1234567890ABCDEF")
        self.assertEqual(pk, "deadbeef0123456789abcdef")

    def test_key_not_stored_in_plaintext(self):
        """Test that private keys are NOT stored in plaintext on disk."""
        ks = KeyStore.create(self.passphrase, self.keystore_path)
        private_key = "super_secret_private_key_12345"
        ks.add_key(
            private_key=private_key,
            public_key="pub_key_12345",
            address="ADDR00000000000000000000",
        )
        ks.save(self.keystore_path)

        # Read the raw file and check the private key is not in plaintext
        with open(self.keystore_path, "r") as f:
            raw_content = f.read()

        self.assertNotIn(private_key, raw_content)

    def test_load_keystore(self):
        """Test loading an existing keystore."""
        # Create and save
        ks1 = KeyStore.create(self.passphrase, self.keystore_path)
        ks1.add_key(
            private_key="private_key_abc123",
            public_key="public_key_abc123",
            address="ADDRABC123000000000000",
        )
        ks1.set_balance(100.5)
        ks1.save(self.keystore_path)

        # Load
        ks2 = KeyStore.load(self.keystore_path, self.passphrase)
        self.assertEqual(ks2.get_key_count(), 1)
        self.assertEqual(ks2.get_balance(), 100.5)
        self.assertEqual(ks2.get_private_key("ADDRABC123000000000000"), "private_key_abc123")

    def test_wrong_passphrase(self):
        """Test that wrong passphrase raises ValueError."""
        ks = KeyStore.create(self.passphrase, self.keystore_path)
        ks.add_key(
            private_key="some_private_key",
            public_key="some_public_key",
            address="ADDRWRONG00000000000000",
        )
        ks.save(self.keystore_path)

        with self.assertRaises(ValueError):
            KeyStore.load(self.keystore_path, "wrong_passphrase")

    def test_load_nonexistent_file(self):
        """Test loading a nonexistent file raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError):
            KeyStore.load("/nonexistent/path.json", self.passphrase)

    def test_multiple_keys(self):
        """Test adding multiple keys."""
        ks = KeyStore.create(self.passphrase, self.keystore_path)
        for i in range(5):
            ks.add_key(
                private_key=f"private_key_{i}",
                public_key=f"public_key_{i}",
                address=f"ADDR{i:018X}",
                label=f"Key {i}",
            )
        ks.save(self.keystore_path)

        self.assertEqual(ks.get_key_count(), 5)
        for i in range(5):
            pk = ks.get_private_key(f"ADDR{i:018X}")
            self.assertEqual(pk, f"private_key_{i}")

    def test_get_address(self):
        """Test getting address by index."""
        ks = KeyStore.create(self.passphrase, self.keystore_path)
        ks.add_key("pk1", "pub1", "ADDR11111111111111111111")
        ks.add_key("pk2", "pub2", "ADDR22222222222222222222")

        self.assertEqual(ks.get_address(0), "ADDR11111111111111111111")
        self.assertEqual(ks.get_address(1), "ADDR22222222222222222222")
        self.assertIsNone(ks.get_address(2))

    def test_get_all_addresses(self):
        """Test getting all addresses."""
        ks = KeyStore.create(self.passphrase, self.keystore_path)
        ks.add_key("pk1", "pub1", "ADDR11111111111111111111")
        ks.add_key("pk2", "pub2", "ADDR22222222222222222222")

        addresses = ks.get_all_addresses()
        self.assertEqual(len(addresses), 2)
        self.assertIn("ADDR11111111111111111111", addresses)
        self.assertIn("ADDR22222222222222222222", addresses)

    def test_balance_operations(self):
        """Test balance get/set."""
        ks = KeyStore.create(self.passphrase, self.keystore_path)
        self.assertEqual(ks.get_balance(), 0.0)
        ks.set_balance(500.0)
        self.assertEqual(ks.get_balance(), 500.0)

    def test_transactions(self):
        """Test transaction history."""
        ks = KeyStore.create(self.passphrase, self.keystore_path)
        tx = {"tx_id": "abc123", "amount": 10.0, "to": "ADDR123"}
        ks.add_transaction(tx)
        txs = ks.get_transactions()
        self.assertEqual(len(txs), 1)
        self.assertEqual(txs[0]["tx_id"], "abc123")

    def test_get_entries_no_private_keys(self):
        """Test that get_entries does not expose private keys."""
        ks = KeyStore.create(self.passphrase, self.keystore_path)
        ks.add_key(
            private_key="secret_key_here",
            public_key="public_key_here",
            address="ADDRENTRY00000000000000",
        )
        entries = ks.get_entries()
        self.assertEqual(len(entries), 1)
        self.assertNotIn("private_key", entries[0])
        self.assertEqual(entries[0]["address"], "ADDRENTRY00000000000000")

    def test_save_and_reload_preserves_keys(self):
        """Test that save and reload preserves all keys."""
        ks = KeyStore.create(self.passphrase, self.keystore_path)
        ks.add_key("pk_secret_1", "pub1", "ADDRSAVE11111111111111")
        ks.add_key("pk_secret_2", "pub2", "ADDRSAVE22222222222222")
        ks.set_balance(999.99)
        ks.save(self.keystore_path)

        ks2 = KeyStore.load(self.keystore_path, self.passphrase)
        self.assertEqual(ks2.get_key_count(), 2)
        self.assertEqual(ks2.get_balance(), 999.99)
        self.assertEqual(ks2.get_private_key("ADDRSAVE11111111111111"), "pk_secret_1")
        self.assertEqual(ks2.get_private_key("ADDRSAVE22222222222222"), "pk_secret_2")

    def test_get_public_key(self):
        """Test retrieving public key by address."""
        ks = KeyStore.create(self.passphrase, self.keystore_path)
        ks.add_key("pk", "my_public_key_value", "ADDRPUB0000000000000000")
        self.assertEqual(ks.get_public_key("ADDRPUB0000000000000000"), "my_public_key_value")
        self.assertIsNone(ks.get_public_key("NONEXISTENT"))

    def test_keystore_file_format(self):
        """Test that the keystore file has the expected JSON structure."""
        ks = KeyStore.create(self.passphrase, self.keystore_path)
        ks.add_key("pk", "pub", "ADDRFMT0000000000000000")
        ks.save(self.keystore_path)

        with open(self.keystore_path, "r") as f:
            data = json.load(f)

        self.assertIn("version", data)
        self.assertIn("keys", data)
        self.assertIn("balance", data)
        self.assertIn("transactions", data)
        self.assertEqual(data["version"], 1)


if __name__ == "__main__":
    unittest.main()
