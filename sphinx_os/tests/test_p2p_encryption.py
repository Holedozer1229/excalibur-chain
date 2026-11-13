"""Tests for AES-256-GCM encryption in the Holographic P2P layer."""

import json
import unittest
from sphinx_os.nexus import HolographicP2PLayer


class TestP2PEncryption(unittest.TestCase):
    """Test cases for AES-256-GCM encryption in the P2P layer."""

    def setUp(self):
        """Create a fresh P2P layer for each test."""
        self.p2p = HolographicP2PLayer()
        self.p2p.add_peer("alice", "192.168.1.1", 8080)
        self.p2p.add_peer("bob", "192.168.1.2", 8081)
        self.p2p.connect_peer("alice")
        self.p2p.connect_peer("bob")
        self.p2p.set_encryption_key()

    def test_encrypt_decrypt_roundtrip(self):
        """Test that encryption and decryption are inverse operations."""
        payload = {"from": "alice", "to": "bob", "amount": 100}
        ct, key_b64 = self.p2p._encrypt_payload(payload)
        decrypted = self.p2p._decrypt_payload(ct, key_b64)
        self.assertEqual(decrypted, payload)

    def test_encrypted_payload_is_not_plaintext(self):
        """Test that encrypted output does not contain the plaintext."""
        payload = {"secret": "super_secret_data_12345"}
        ct, key_b64 = self.p2p._encrypt_payload(payload)
        self.assertNotIn("super_secret_data_12345", ct)

    def test_different_ciphertext_for_same_payload(self):
        """Test that encrypting the same payload twice produces different ciphertext (nonce)."""
        payload = {"data": "same_data"}
        ct1, key1 = self.p2p._encrypt_payload(payload)
        ct2, key2 = self.p2p._encrypt_payload(payload)
        # Same key, but different nonce → different ciphertext
        self.assertNotEqual(ct1, ct2)

    def test_wrong_key_fails(self):
        """Test that decrypting with the wrong key raises an error."""
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        import os
        import base64

        payload = {"data": "test"}
        ct, key_b64 = self.p2p._encrypt_payload(payload)

        # Try with a different key
        wrong_key = os.urandom(32)
        wrong_key_b64 = base64.b64encode(wrong_key).decode()

        with self.assertRaises(Exception):
            self.p2p._decrypt_payload(ct, wrong_key_b64)

    def test_tampered_ciphertext_fails(self):
        """Test that tampered ciphertext is rejected (authentication failure)."""
        import base64

        payload = {"data": "test"}
        ct, key_b64 = self.p2p._encrypt_payload(payload)

        # Tamper with the ciphertext
        ct_bytes = base64.b64decode(ct)
        tampered = ct_bytes[:-1] + bytes([(ct_bytes[-1] + 1) % 256])
        tampered_b64 = base64.b64encode(tampered).decode()

        with self.assertRaises(Exception):
            self.p2p._decrypt_payload(tampered_b64, key_b64)

    def test_encrypted_message_sending(self):
        """Test sending an encrypted message through the P2P layer."""
        msg_id = self.p2p.send_message(
            source="alice",
            msg_type="tx",
            payload={"amount": 50},
            destination="bob",
            encrypt=True,
        )
        self.assertIsNotNone(msg_id)
        msg = self.p2p.get_message(msg_id)
        self.assertTrue(msg.encrypted)
        self.assertIn("_encrypted", msg.payload)

    def test_set_random_key(self):
        """Test that set_encryption_key generates a random key when none provided."""
        p2p = HolographicP2PLayer()
        p2p.set_encryption_key()
        self.assertIsNotNone(p2p._encryption_key)
        self.assertEqual(len(p2p._encryption_key), 32)  # 256 bits

    def test_set_custom_key(self):
        """Test setting a custom 32-byte key."""
        import os
        custom_key = os.urandom(32)
        self.p2p.set_encryption_key(custom_key)
        self.assertEqual(self.p2p._encryption_key, custom_key)

    def test_encryption_enabled_flag(self):
        """Test that encryption_enabled reflects key state."""
        p2p = HolographicP2PLayer()
        state = p2p.get_network_state()
        self.assertFalse(state["encryption_enabled"])

        p2p.set_encryption_key()
        state = p2p.get_network_state()
        self.assertTrue(state["encryption_enabled"])

    def test_complex_payload(self):
        """Test encrypting a complex nested payload."""
        payload = {
            "tx_id": "abc123",
            "from": "ADDR11111111111111111111",
            "to": "ADDR22222222222222222222",
            "amount": 123.456,
            "type": "transfer",
            "metadata": {
                "nested": {"deep": True},
                "list": [1, 2, 3],
            },
        }
        ct, key_b64 = self.p2p._encrypt_payload(payload)
        decrypted = self.p2p._decrypt_payload(ct, key_b64)
        self.assertEqual(decrypted, payload)


if __name__ == "__main__":
    unittest.main()
