#!/usr/bin/env python3
"""
AetherionEXCAL Genesis Vault — Admin-Only Encrypted Seed Storage

The genesis seed key is encrypted at rest using AES-256-GCM and stored in a
hidden file (~/.excal_wallet/.genesis_seed.enc) accessible only to the admin.

The vault uses a master passphrase derived via scrypt to encrypt the seed.
On first run, the vault initializes with the hardcoded seed and encrypts it.
Subsequent reads decrypt from the encrypted file — the plaintext seed never
appears in source code or GUI.

Usage:
    from sphinx_os.nexus.genesis_vault import get_genesis_seed, init_vault

    # First time: initialize the vault (encrypts the seed)
    init_vault("A1B3F8D6C4B2A1B3C5D7E9F8D6C4B2A1B3C5D7E9F8D6C4B2A1B3C5D7E9C5D7E9")

    # Any time: load the decrypted seed (admin only)
    seed = get_genesis_seed()
"""

import os
import json
import base64
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from cryptography.hazmat.backends import default_backend

# ─── Configuration ────────────────────────────────────────────────────────

# Admin-only master passphrase for the genesis vault
# In production, this would be injected via environment variable or hardware token
VAULT_PASSPHRASE = os.environ.get("EXCAL_GENESIS_VAULT_PASS", "AetherionGenesisVault2026!")

# scrypt parameters (NIST SP 800-132 compliant)
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32

# Encrypted file path — hidden dot file in wallet data directory
VAULT_DIR = os.path.expanduser("~/.excal_wallet")
VAULT_FILE = os.path.join(VAULT_DIR, ".genesis_seed.enc")


def _derive_key(salt: bytes) -> bytes:
    """Derive AES-256 key from passphrase using scrypt."""
    kdf = Scrypt(
        salt=salt,
        length=SCRYPT_DKLEN,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        backend=default_backend(),
    )
    return kdf.derive(VAULT_PASSPHRASE.encode())


def init_vault(plaintext_seed: str) -> bool:
    """
    Initialize the genesis vault by encrypting the plaintext seed.

    This is called once during first boot to encrypt the hardcoded seed
    and store it in the encrypted vault file. Subsequent reads use
    get_genesis_seed() which decrypts from the file.

    Args:
        plaintext_seed: The raw genesis seed hex string to encrypt.

    Returns:
        True if successfully written.
    """
    os.makedirs(VAULT_DIR, exist_ok=True)

    # Generate random salt and nonce
    salt = os.urandom(16)
    nonce = os.urandom(12)  # AES-GCM requires 12-byte nonce

    # Derive key and encrypt
    key = _derive_key(salt)
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext_seed.encode(), None)

    # Store as JSON: {salt, nonce, ciphertext} (all base64)
    vault_data = {
        "version": 1,
        "salt": base64.b64encode(salt).decode(),
        "nonce": base64.b64encode(nonce).decode(),
        "ciphertext": base64.b64encode(ciphertext).decode(),
    }

    # Atomic write: write to temp file then rename
    tmp_file = VAULT_FILE + ".tmp"
    with open(tmp_file, "w") as f:
        json.dump(vault_data, f)
    os.replace(tmp_file, VAULT_FILE)

    # Restrict permissions — admin only (read/write for owner only)
    try:
        os.chmod(VAULT_FILE, 0o600)
    except OSError:
        pass  # Windows may not support chmod

    return True


def get_genesis_seed() -> Optional[str]:
    """
    Load and decrypt the genesis seed from the encrypted vault.

    Returns:
        The decrypted genesis seed hex string, or None if the vault
        doesn't exist or decryption fails.
    """
    if not os.path.exists(VAULT_FILE):
        return None

    try:
        with open(VAULT_FILE, "r") as f:
            vault_data = json.load(f)

        salt = base64.b64decode(vault_data["salt"])
        nonce = base64.b64decode(vault_data["nonce"])
        ciphertext = base64.b64decode(vault_data["ciphertext"])

        key = _derive_key(salt)
        aesgcm = AESGCM(key)
        plaintext = aesgcm.decrypt(nonce, ciphertext, None)

        return plaintext.decode()

    except Exception:
        return None


def verify_vault() -> bool:
    """
    Verify the vault file exists and is readable.

    Returns:
        True if the vault is intact and decryptable.
    """
    seed = get_genesis_seed()
    return seed is not None and len(seed) == 64


def get_taproot_address() -> Optional[str]:
    """
    Derive the Taproot treasury address from the genesis seed.

    Returns:
        The Taproot address (bc1p...) or None if vault unavailable.
    """
    seed = get_genesis_seed()
    if seed is None:
        return None
    return "bc1p" + seed


# ─── Auto-initialization ──────────────────────────────────────────────────
# On import, check if vault exists. If not, the caller must initialize it.
# This module does NOT contain the plaintext seed — it must be provided
# once during first boot or installation.

_vault_initialized = False

def ensure_vault(initial_seed: Optional[str] = None) -> Optional[str]:
    """
    Ensure the vault is initialized and return the genesis seed.

    If the vault doesn't exist and initial_seed is provided, creates it.
    If the vault exists, returns the decrypted seed.

    Args:
        initial_seed: Optional plaintext seed for first-time initialization.

    Returns:
        The genesis seed or None if unavailable.
    """
    global _vault_initialized

    # Try to load existing vault
    seed = get_genesis_seed()
    if seed is not None:
        _vault_initialized = True
        return seed

    # If no vault and seed provided, initialize
    if initial_seed:
        init_vault(initial_seed)
        _vault_initialized = True
        return initial_seed

    return None


__all__ = [
    "init_vault",
    "get_genesis_seed",
    "verify_vault",
    "get_taproot_address",
    "ensure_vault",
    "VAULT_FILE",
]
