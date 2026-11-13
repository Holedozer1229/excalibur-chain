"""Secure key storage for EXCAL wallet.

Private keys are encrypted at rest using AES-256-GCM, derived from a user
passphrase via scrypt (NIST-recommended KDF).  The encrypted blob is stored
as JSON alongside the salt, nonce, and scrypt parameters.

This module provides:
- `KeyStore.create()`: Create a new encrypted keystore from a passphrase.
- `KeyStore.load()`: Load and decrypt an existing keystore.
- `KeyStore.add_key()`: Add an encrypted key pair.
- `KeyStore.get_key()`: Retrieve a decrypted private key by address.
- `KeyStore.save()`: Re-encrypt and persist the keystore.
"""

import json
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.primitives import hashes


# scrypt parameters (NIST SP 800-132 compliant)
SCRYPT_N = 2**14  # CPU/memory cost
SCRYPT_R = 8      # Block size
SCRYPT_P = 1      # Parallelization
SCRYPT_DKLEN = 32 # Derived key length (256 bits for AES-256)


@dataclass
class EncryptedKeyEntry:
    """An encrypted key entry stored in the keystore."""
    address: str
    public_key: str
    private_key_encrypted: str  # base64(nonce || ciphertext || tag)
    salt: str                   # base64(salt bytes)
    label: str = ""
    created_at: float = 0.0


class KeyStore:
    """Encrypted keystore backed by AES-256-GCM + scrypt KDF.

    The keystore file contains:
    - version: schema version
    - keys: list of encrypted key entries
    - balance: wallet balance (plaintext, not secret)
    - transactions: transaction history (plaintext metadata)
    - created_at: wallet creation timestamp
    """

    VERSION = 1

    def __init__(self):
        self._keys: List[EncryptedKeyEntry] = []
        self._balance: float = 0.0
        self._transactions: List[Dict[str, Any]] = []
        self._created_at: float = time.time()
        self._passphrase: Optional[str] = None
        self._kdf: Optional[Scrypt] = None
        self._salt: Optional[bytes] = None

    # ------------------------------------------------------------------
    # Creation / Loading
    # ------------------------------------------------------------------

    @classmethod
    def create(cls, passphrase: str, path: str) -> "KeyStore":
        """Create a new encrypted keystore.

        Args:
            passphrase: User passphrase (>= 8 characters recommended).
            path: File path to save the keystore.

        Returns:
            New KeyStore instance, saved to disk.
        """
        if len(passphrase) < 4:
            raise ValueError("Passphrase must be at least 4 characters")

        ks = cls()
        ks._passphrase = passphrase
        ks._salt = os.urandom(16)
        ks._kdf = Scrypt(
            salt=ks._salt,
            length=SCRYPT_DKLEN,
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
        )
        ks._save_to_disk(path)
        return ks

    @classmethod
    def load(cls, path: str, passphrase: str) -> "KeyStore":
        """Load and decrypt an existing keystore.

        Args:
            path: File path to the keystore.
            passphrase: User passphrase used to encrypt the keystore.

        Returns:
            Decrypted KeyStore instance.

        Raises:
            FileNotFoundError: If the keystore file does not exist.
            ValueError: If the passphrase is incorrect.
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"Keystore not found: {path}")

        with open(path, "r") as f:
            data = json.load(f)

        ks = cls()
        ks._passphrase = passphrase
        ks._balance = data.get("balance", 0.0)
        ks._transactions = data.get("transactions", [])
        ks._created_at = data.get("created_at", time.time())

        # Re-derive key using stored salts per entry
        for entry_data in data.get("keys", []):
            entry_salt = entry_data["salt_bytes"]  # base64 encoded
            import base64
            salt_bytes = base64.b64decode(entry_salt)
            kdf = Scrypt(
                salt=salt_bytes,
                length=SCRYPT_DKLEN,
                n=SCRYPT_N,
                r=SCRYPT_R,
                p=SCRYPT_P,
            )
            key = kdf.derive(passphrase.encode("utf-8"))
            aesgcm = AESGCM(key)

            ct = base64.b64decode(entry_data["private_key_encrypted"])
            try:
                nonce = ct[:12]
                ct_only = ct[12:]
                plaintext = aesgcm.decrypt(nonce, ct_only, None)
                # Verify decryption succeeded
                plaintext.decode("utf-8")
            except Exception:
                raise ValueError("Incorrect passphrase")

            entry = EncryptedKeyEntry(
                address=entry_data["address"],
                public_key=entry_data["public_key"],
                private_key_encrypted=entry_data["private_key_encrypted"],
                salt=entry_salt,
                label=entry_data.get("label", ""),
                created_at=entry_data.get("created_at", 0.0),
            )
            ks._keys.append(entry)

        ks._salt = base64.b64decode(ks._keys[0].salt) if ks._keys else os.urandom(16)
        ks._kdf = Scrypt(
            salt=ks._salt,
            length=SCRYPT_DKLEN,
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
        )
        return ks

    # ------------------------------------------------------------------
    # Key management
    # ------------------------------------------------------------------

    def _derive_key(self, salt: bytes) -> bytes:
        """Derive an AES-256 key from the passphrase using scrypt."""
        if self._passphrase is None:
            raise RuntimeError("Keystore not unlocked")
        kdf = Scrypt(
            salt=salt,
            length=SCRYPT_DKLEN,
            n=SCRYPT_N,
            r=SCRYPT_R,
            p=SCRYPT_P,
        )
        return kdf.derive(self._passphrase.encode("utf-8"))

    def add_key(self, private_key: str, public_key: str, address: str, label: str = "") -> EncryptedKeyEntry:
        """Encrypt and store a new key pair.

        Args:
            private_key: Raw private key hex string.
            public_key: Raw public key hex string.
            address: Wallet address.
            label: Optional label for the key.

        Returns:
            The encrypted key entry.
        """
        import base64
        salt = os.urandom(16)
        key = self._derive_key(salt)
        aesgcm = AESGCM(key)
        nonce = os.urandom(12)
        ct = aesgcm.encrypt(nonce, private_key.encode("utf-8"), None)
        # Store nonce + ciphertext+tag together
        encrypted_blob = nonce + ct

        entry = EncryptedKeyEntry(
            address=address,
            public_key=public_key,
            private_key_encrypted=base64.b64encode(encrypted_blob).decode(),
            salt=base64.b64encode(salt).decode(),
            label=label or f"Key #{len(self._keys) + 1}",
            created_at=time.time(),
        )
        self._keys.append(entry)
        return entry

    def get_private_key(self, address: str) -> Optional[str]:
        """Decrypt and return the private key for a given address.

        Args:
            address: Wallet address.

        Returns:
            Decrypted private key hex string, or None if not found.
        """
        import base64
        for entry in self._keys:
            if entry.address == address:
                salt = base64.b64decode(entry.salt)
                key = self._derive_key(salt)
                aesgcm = AESGCM(key)
                blob = base64.b64decode(entry.private_key_encrypted)
                nonce = blob[:12]
                ct = blob[12:]
                plaintext = aesgcm.decrypt(nonce, ct, None)
                return plaintext.decode("utf-8")
        return None

    def get_address(self, index: int = 0) -> Optional[str]:
        """Get the address at the given index."""
        if 0 <= index < len(self._keys):
            return self._keys[index].address
        return None

    def get_public_key(self, address: str) -> Optional[str]:
        """Get the public key for a given address."""
        for entry in self._keys:
            if entry.address == address:
                return entry.public_key
        return None

    def get_all_addresses(self) -> List[str]:
        """Get all addresses in the keystore."""
        return [entry.address for entry in self._keys]

    @property
    def keys(self) -> List[EncryptedKeyEntry]:
        """Return the list of encrypted key entries (read-only view)."""
        return list(self._keys)

    def get_key(self, address: str, passphrase: str) -> Optional[str]:
        """Decrypt and return the private key for a given address.

        This is a convenience method that accepts an explicit passphrase
        parameter for callers that don't have the keystore unlocked.

        Args:
            address: Wallet address.
            passphrase: User passphrase for decryption.

        Returns:
            Decrypted private key hex string, or None if not found.
        """
        # If already unlocked, use the stored passphrase
        if self._passphrase is not None:
            return self.get_private_key(address)
        # Otherwise, derive key inline
        import base64
        for entry in self._keys:
            if entry.address == address:
                salt = base64.b64decode(entry.salt)
                kdf = Scrypt(
                    salt=salt,
                    length=SCRYPT_DKLEN,
                    n=SCRYPT_N,
                    r=SCRYPT_R,
                    p=SCRYPT_P,
                )
                key = kdf.derive(passphrase.encode("utf-8"))
                aesgcm = AESGCM(key)
                blob = base64.b64decode(entry.private_key_encrypted)
                nonce = blob[:12]
                ct = blob[12:]
                plaintext = aesgcm.decrypt(nonce, ct, None)
                return plaintext.decode("utf-8")
        return None

    def get_key_count(self) -> int:
        """Get the number of keys in the keystore."""
        return len(self._keys)

    def get_entries(self) -> List[Dict[str, Any]]:
        """Get all key entries (without decrypted private keys)."""
        return [
            {
                "address": entry.address,
                "public_key": entry.public_key,
                "label": entry.label,
                "created_at": entry.created_at,
            }
            for entry in self._keys
        ]

    # ------------------------------------------------------------------
    # Balance & transactions
    # ------------------------------------------------------------------

    def get_balance(self) -> float:
        """Get the wallet balance."""
        return self._balance

    def set_balance(self, amount: float):
        """Set the wallet balance."""
        self._balance = amount

    def add_transaction(self, tx: Dict[str, Any]):
        """Add a transaction to the history."""
        self._transactions.append(tx)

    def get_transactions(self) -> List[Dict[str, Any]]:
        """Get the transaction history."""
        return list(self._transactions)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_to_disk(self, path: str):
        """Save the keystore to disk."""
        import base64
        data = {
            "version": self.VERSION,
            "keys": [
                {
                    "address": entry.address,
                    "public_key": entry.public_key,
                    "private_key_encrypted": entry.private_key_encrypted,
                    "salt_bytes": entry.salt,
                    "label": entry.label,
                    "created_at": entry.created_at,
                }
                for entry in self._keys
            ],
            "balance": self._balance,
            "transactions": self._transactions,
            "created_at": self._created_at,
        }
        dir_name = os.path.dirname(path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def save(self, path: str):
        """Re-encrypt and save the keystore to disk.

        Args:
            path: File path to save the keystore.
        """
        # Re-encrypt all keys with current passphrase
        import base64
        new_keys = []
        for entry in self._keys:
            salt = os.urandom(16)
            key = self._derive_key(salt)
            aesgcm = AESGCM(key)
            # Decrypt with old salt, re-encrypt with new salt
            old_salt = base64.b64decode(entry.salt)
            old_key = self._derive_key(old_salt)
            old_aesgcm = AESGCM(old_key)
            blob = base64.b64decode(entry.private_key_encrypted)
            old_nonce = blob[:12]
            old_ct = blob[12:]
            plaintext = old_aesgcm.decrypt(old_nonce, old_ct, None)
            # Re-encrypt
            nonce = os.urandom(12)
            new_ct = aesgcm.encrypt(nonce, plaintext, None)
            new_blob = nonce + new_ct
            new_entry = EncryptedKeyEntry(
                address=entry.address,
                public_key=entry.public_key,
                private_key_encrypted=base64.b64encode(new_blob).decode(),
                salt=base64.b64encode(salt).decode(),
                label=entry.label,
                created_at=entry.created_at,
            )
            new_keys.append(new_entry)
        self._keys = new_keys
        self._save_to_disk(path)
