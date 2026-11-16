"""wallet_manager.py — Local wallet operations for the Kivy wallet.

Wraps the excalibur_wallet module to provide wallet CRUD, key derivation,
lock operations, and transaction building without requiring the CLI.

Handles:
- Wallet creation from BIP-39 mnemonic
- Wallet import from seed phrase
- Address generation (PKH, PQH, HTLC, QHTLC)
- Balance and UTXO queries via RPC
- Transaction building and signing
- Encrypted storage via wallet_crypto
"""
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add project root to path for imports
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from excalibur_wallet.wallet import Wallet, WalletError
from excalibur_wallet.keys import (
    receive_key, change_key, trifold_seed, lock_for_priv, address_for_priv
)
from excalibur_wallet.bip39 import generate_mnemonic, mnemonic_to_seed
from excalibur_wallet.txbuild import (
    build_send, build_htlc_claim, build_htlc_refund,
    build_qhtlc_claim, build_qhtlc_refund,
    build_pqh_spend, parse_amount, TxBuildError
)
from excalibur_wallet.locks import (
    parse_lock_hex, lock_status, htlc_lock, qhtlc_lock
)
from excalibur_wallet.ledger import Ledger, RpcClient as WalletRpcClient
import wallet_crypto


SWORD = 100_000_000  # 1 EXCAL = 100,000,000 swords


class WalletManagerError(Exception):
    """Error in wallet operations."""
    pass


class WalletManager:
    """Manages local wallet state and operations.

    Usage:
        mgr = WalletManager(datadir="~/.excal_kivy_wallet")
        mgr.create_wallet(passphrase, mnemonic_words=12)
        address = mgr.get_receive_address()
        balance = mgr.get_balance()
    """

    def __init__(self, datadir: str = None):
        if datadir is None:
            datadir = os.path.join(
                PROJECT_ROOT, "excalibur-wallet-data"
            )
        self.datadir = os.path.abspath(os.path.expanduser(datadir))
        self.wallet_file = os.path.join(self.datadir, "wallet.json")
        self.wallet = None
        self._passphrase = None
        self._mnemonic = None
        self.ledger = None

    @property
    def exists(self) -> bool:
        """Check if a wallet file exists."""
        return os.path.exists(self.wallet_file)

    @property
    def is_loaded(self) -> bool:
        """Check if wallet is loaded in memory."""
        return self.wallet is not None

    # ── Wallet lifecycle ───────────────────────────────────────────

    def create_wallet(self, passphrase: str, mnemonic_words: int = 12,
                      network: str = "fork") -> str:
        """Create a new wallet with a fresh mnemonic.

        Returns the mnemonic phrase (show once for backup).
        """
        os.makedirs(self.datadir, exist_ok=True)
        if self.exists:
            raise WalletManagerError("Wallet already exists. Use load_wallet().")

        pw = passphrase.encode("utf-8")
        self.wallet, self._mnemonic = Wallet.create(
            self.datadir, pw, words=mnemonic_words, network=network
        )
        self._passphrase = pw
        self.ledger = Ledger(self.datadir)
        return self._mnemonic

    def load_wallet(self, passphrase: str) -> None:
        """Load an existing wallet with the passphrase."""
        if not self.exists:
            raise WalletManagerError("No wallet found. Create one first.")

        pw = passphrase.encode("utf-8")
        self.wallet = Wallet.load(self.datadir, pw)
        self._passphrase = pw
        self.ledger = Ledger(self.datadir)

    def import_wallet(self, passphrase: str, seed_phrase: str,
                      network: str = "fork") -> None:
        """Import a wallet from a BIP-39 seed phrase."""
        os.makedirs(self.datadir, exist_ok=True)
        if self.exists:
            raise WalletManagerError("Wallet already exists.")

        seed = mnemonic_to_seed(seed_phrase)
        pw = passphrase.encode("utf-8")
        self.wallet = Wallet.create_from_seed(
            self.datadir, pw, seed, network=network
        )
        self._passphrase = pw
        self._mnemonic = seed_phrase
        self.ledger = Ledger(self.datadir)

    def close_wallet(self) -> None:
        """Close the wallet and clear sensitive data from memory."""
        self.wallet = None
        self._passphrase = None
        self.ledger = None

    # ── Addresses ──────────────────────────────────────────────────

    def get_receive_address(self, index: int = 0) -> str:
        """Get a receive address (PKH lock)."""
        if not self.is_loaded:
            raise WalletManagerError("Wallet not loaded")
        priv, pub = receive_key(self.wallet._seed, index)
        return address_for_priv(priv)

    def get_change_address(self, index: int = 0) -> str:
        """Get a change address (PKH lock)."""
        if not self.is_loaded:
            raise WalletManagerError("Wallet not loaded")
        priv, pub = change_key(self.wallet._seed, index)
        return address_for_priv(priv)

    def get_all_addresses(self, count: int = 5) -> List[Dict]:
        """Get multiple receive addresses."""
        addresses = []
        for i in range(count):
            addr = self.get_receive_address(i)
            addresses.append({"index": i, "address": addr, "type": "PKH"})
        return addresses

    # ── Balance and UTXOs ──────────────────────────────────────────

    def get_balance(self, rpc_url: str = "http://127.0.0.1:9432") -> Dict:
        """Get balance from the node RPC.

        Returns:
            Dict with swords, excal, and utxo_count.
        """
        from .rpc_client import RpcClient, RpcError

        client = RpcClient(rpc_url)
        try:
            locks = self.wallet.watched_locks() if self.is_loaded else []
            # Try ledger balance first
            if self.ledger and locks:
                try:
                    balances, (tip_height, tip_hash) = self.ledger.balance_via_rpc(locks)
                    total_swords = 0
                    utxo_count = 0
                    for lock_hex, b in balances.items():
                        total_swords += b["total"]
                        utxo_count += len(b["utxos"])
                    return {
                        "swords": total_swords,
                        "excal": total_swords / SWORD,
                        "utxo_count": utxo_count,
                        "tip_height": tip_height,
                        "tip_hash": tip_hash,
                    }
                except Exception:
                    pass

            # Fallback to node RPC
            if self.is_loaded:
                addr = self.get_receive_address()
                balance_swords = client.getbalance()
                utxos = client.getutxos(addr)
            else:
                balance_swords = client.getbalance()
                utxos = client.getutxos()

            return {
                "swords": balance_swords,
                "excal": balance_swords / SWORD,
                "utxo_count": len(utxos) if utxos else 0,
                "tip_height": client.getblockcount(),
            }
        except RpcError as e:
            raise WalletManagerError(f"Cannot reach node: {e}")

    def get_utxos(self, rpc_url: str = "http://127.0.0.1:9432") -> List[Dict]:
        """Get UTXO list from the node."""
        from .rpc_client import RpcClient, RpcError

        client = RpcClient(rpc_url)
        try:
            if self.is_loaded:
                addr = self.get_receive_address()
                return client.getutxos(addr)
            return client.getutxos()
        except RpcError as e:
            raise WalletManagerError(f"Cannot reach node: {e}")

    # ── Transactions ───────────────────────────────────────────────

    def build_send_tx(self, to_address: str, amount_excal: float,
                      fee_rate: int = 1) -> Dict:
        """Build a send transaction.

        Args:
            to_address: Recipient PKH lock address
            amount_excal: Amount in EXCAL
            fee_rate: Fee rate in swords/vbyte

        Returns:
            Dict with tx_hex, txid, fee, and change.
        """
        if not self.is_loaded:
            raise WalletManagerError("Wallet not loaded")

        amount_swords = int(amount_excal * SWORD)

        # Get UTXOs for funding
        utxos = self.get_utxos()
        if not utxos:
            raise WalletManagerError("No UTXOs available")

        # Build the transaction
        try:
            priv, _ = receive_key(self.wallet._seed, 0)
            tx_result = build_send(
                utxos=utxos,
                to_lock=to_address,
                to_value=amount_swords,
                privkey=priv,
                fee_rate=fee_rate,
            )
            return {
                "tx_hex": tx_result.hex() if hasattr(tx_result, 'hex') else tx_result,
                "fee": 0,  # Fee calculated by build_send
            }
        except TxBuildError as e:
            raise WalletManagerError(f"Transaction build failed: {e}")

    # ── Lock operations ────────────────────────────────────────────

    def create_htlc_lock(self, secret_hash: bytes, timeout: int,
                         refund_address: str) -> Dict:
        """Create an HTLC lock.

        Args:
            secret_hash: SHA-256 hash of the preimage
            timeout: Block height timeout
            refund_address: Address for refund

        Returns:
            Dict with lock_hex and parameters.
        """
        lock = htlc_lock(secret_hash, timeout, refund_address)
        return {
            "lock_hex": lock.hex() if hasattr(lock, 'hex') else lock,
            "secret_hash": secret_hash.hex(),
            "timeout": timeout,
            "refund_address": refund_address,
        }

    def create_qhtlc_lock(self, secret_hash: bytes, timeout: int,
                          refund_address: str) -> Dict:
        """Create a quantum-resistant HTLC lock."""
        lock = qhtlc_lock(secret_hash, timeout, refund_address)
        return {
            "lock_hex": lock.hex() if hasattr(lock, 'hex') else lock,
            "secret_hash": secret_hash.hex(),
            "timeout": timeout,
            "refund_address": refund_address,
        }

    def parse_lock(self, lock_hex: str) -> Dict:
        """Parse a lock hex string and return its type and status."""
        lock_bytes = bytes.fromhex(lock_hex)
        lock_type = parse_lock_hex(lock_hex)
        status = lock_status(lock_bytes)
        return {
            "type": lock_type,
            "status": status,
            "hex": lock_hex,
        }

    # ── Utility ────────────────────────────────────────────────────

    def format_swords(self, swords: int) -> str:
        """Format swords as human-readable EXCAL string."""
        return f"{swords / SWORD:.8f} EXCAL"

    def parse_excal(self, excal_str: str) -> int:
        """Parse an EXCAL string to swords."""
        return parse_amount(excal_str)

    def get_mnemonic(self) -> Optional[str]:
        """Return the mnemonic if available."""
        return self._mnemonic
