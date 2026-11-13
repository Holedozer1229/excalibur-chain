"""wallet.py — the encrypted wallet file.

Two wallet kinds, one file format:
  * "mnemonic": BIP39 mnemonic -> seed -> deterministic receive/change
    keys (keys.py) + a Trifold key for PQH/QHTLC (lazy-built).
  * "legacy": an imported single-key node wallet ({"priv","pub"} as
    node_rpc.load_wallet_key writes) — same file, same encryption,
    one address. Lets Lux point the wallet at his existing miner key.

At rest the file is wallet_crypto's envelope (AES-256-CTR + HMAC,
PBKDF2-HMAC-SHA256 600k iterations — the live, NIST-tested module).
The passphrase comes from getpass or a 0600 keyfile; it is never
printed, never logged, and never written to disk by this module.

Plaintext (inside the envelope):
  {"format": "excalibur-wallet-v1", "network": "fork",
   "kind": "mnemonic"|"legacy", "mnemonic": str | null,
   "seed_hex": str | null, "legacy_priv": hex | null,
   "legacy_pub": hex | null,
   "next_receive": int, "next_change": int,
   "created": iso8601, "locks": [ ... HTLC/QHTLC descriptors ... ]}

The mnemonic and seed live in memory only while the wallet is open.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import wallet_crypto
from .bip39 import generate_mnemonic, mnemonic_to_seed
from .keys import (receive_key, change_key, trifold_seed, lock_for_priv,
                  address_for_priv)
from txscript import lock_pkh_for_pubkey

FORMAT = "excalibur-wallet-v1"


class WalletError(Exception):
    pass


class Wallet:
    def __init__(self, datadir, network="fork"):
        self.datadir = os.path.abspath(datadir)
        self.network = network
        self.path = os.path.join(self.datadir, "wallet.json")
        self._data = None          # plaintext dict (in memory only)
        self._seed = None          # bytes, mnemonic wallets only
        self._trifold = None       # lazy TrifoldKey

    # ------------------------------------------------------------ create
    @classmethod
    def create(cls, datadir, passphrase: bytes, words: int = 12,
               network="fork", mnemonic: str = None):
        """Create a new wallet. Returns (wallet, mnemonic).

        The mnemonic is returned to the caller ONCE (the CLI shows it
        to the user for backup). It is never written to any log by
        this module. Refuses to overwrite an existing wallet file."""
        w = cls(datadir, network)
        if os.path.exists(w.path):
            raise WalletError(f"wallet already exists: {w.path} "
                              f"(use load, or delete it explicitly)")
        if mnemonic is None:
            mnemonic = generate_mnemonic(128 if words == 12 else 256)
        seed = mnemonic_to_seed(mnemonic)
        w._data = {"format": FORMAT, "network": network, "kind": "mnemonic",
                   "mnemonic": mnemonic, "seed_hex": seed.hex(),
                   "legacy_priv": None, "legacy_pub": None,
                   "next_receive": 0, "next_change": 0,
                   "created": _now_iso(), "locks": []}
        w._seed = seed
        w._save(passphrase)
        return w, mnemonic

    @classmethod
    def create_from_seed(cls, datadir, passphrase: bytes, seed: bytes,
                         network="fork"):
        """Create a wallet from raw seed bytes (SSS restore path).
        The mnemonic is not recoverable from a seed, so this wallet
        stores seed_hex with mnemonic=None — keys derive identically,
        but there is no word backup to show. Refuses to overwrite."""
        w = cls(datadir, network)
        if os.path.exists(w.path):
            raise WalletError(f"wallet already exists: {w.path}")
        if len(seed) != 64:
            raise WalletError("seed must be 64 bytes (BIP39 seed)")
        w._data = {"format": FORMAT, "network": network, "kind": "mnemonic",
                   "mnemonic": None, "seed_hex": seed.hex(),
                   "legacy_priv": None, "legacy_pub": None,
                   "next_receive": 0, "next_change": 0,
                   "created": _now_iso(), "locks": []}
        w._seed = seed
        w._save(passphrase)
        return w

    @classmethod
    def import_legacy(cls, datadir, passphrase: bytes, priv_hex: str,
                      pub_hex: str, network="fork"):
        """Import a single-key node wallet (priv/pub hex) as a wallet."""
        w = cls(datadir, network)
        if os.path.exists(w.path):
            raise WalletError(f"wallet already exists: {w.path}")
        w._data = {"format": FORMAT, "network": network, "kind": "legacy",
                   "mnemonic": None, "seed_hex": None,
                   "legacy_priv": priv_hex, "legacy_pub": pub_hex,
                   "next_receive": 0, "next_change": 0,
                   "created": _now_iso(), "locks": []}
        w._save(passphrase)
        return w

    @classmethod
    def load(cls, datadir, passphrase: bytes, network="fork"):
        """Open an existing wallet. Raises WalletError on a wrong
        passphrase (the HMAC tag fails) or a corrupt file."""
        w = cls(datadir, network)
        if not os.path.exists(w.path):
            raise WalletError(f"no wallet at {w.path} (create one first)")
        with open(w.path) as f:
            blob = json.load(f)
        try:
            if wallet_crypto.is_encrypted_wallet(blob):
                pt = wallet_crypto.decrypt_bytes(blob, passphrase)
                data = json.loads(pt.decode())
            else:
                data = blob
        except ValueError as e:
            raise WalletError(f"cannot open wallet: {e}")
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            raise WalletError("not an excalibur wallet file")
        w._data = data
        if data.get("kind") == "mnemonic" and data.get("seed_hex"):
            w._seed = bytes.fromhex(data["seed_hex"])
        return w

    # ------------------------------------------------------------ persist
    def _save(self, passphrase: bytes):
        os.makedirs(self.datadir, exist_ok=True)
        blob = wallet_crypto.encrypt_bytes(
            json.dumps(self._data).encode(), passphrase)
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(blob, f)
        os.chmod(tmp, 0o600)
        os.replace(tmp, self.path)

    def save(self, passphrase: bytes):
        """Persist counter/lock changes. The caller holds the passphrase
        (the CLI keeps it for the duration of one command only)."""
        self._save(passphrase)

    # ------------------------------------------------------------ views
    @property
    def kind(self):
        return self._data["kind"]

    @property
    def is_encrypted(self):
        try:
            with open(self.path) as f:
                return wallet_crypto.is_encrypted_wallet(json.load(f))
        except (OSError, ValueError):
            return False

    def receive_priv(self, index: int) -> int:
        if self.kind == "legacy":
            return int(self._data["legacy_priv"], 16)
        return receive_key(self._seed, index)

    def change_priv(self, index: int) -> int:
        if self.kind == "legacy":
            return int(self._data["legacy_priv"], 16)
        return change_key(self._seed, index)

    def receive_address(self, index: int = None) -> str:
        """Address (PKH lock hex) for a receive index; default is the
        next unused index. Does NOT advance the counter — `fresh_receive`
        does that."""
        if index is None:
            index = self._data["next_receive"]
        return address_for_priv(self.receive_priv(index))

    def fresh_receive(self, passphrase: bytes):
        """A fresh receive address: returns (index, address) and advances
        the counter (persisted). Legacy wallets return the single address
        and do not advance."""
        idx = self._data["next_receive"]
        addr = self.receive_address(idx)
        if self.kind == "mnemonic":
            self._data["next_receive"] = idx + 1
            self._save(passphrase)
        return idx, addr

    def change_address(self, index: int = None) -> str:
        if index is None:
            index = self._data["next_change"]
        return address_for_priv(self.change_priv(index))

    def next_change(self, passphrase: bytes):
        """A fresh change address: returns (index, address), advances."""
        idx = self._data["next_change"]
        addr = self.change_address(idx)
        if self.kind == "mnemonic":
            self._data["next_change"] = idx + 1
            self._save(passphrase)
        return idx, addr

    def all_receive_locks(self):
        """All receive locks derived so far (used by the ledger scan)."""
        locks = []
        if self.kind == "legacy":
            return [bytes.fromhex(self._data["legacy_pub"])
                    and lock_pkh_for_pubkey(
                        bytes.fromhex(self._data["legacy_pub"]))]
        for i in range(self._data["next_receive"]):
            locks.append(bytes.fromhex(self.receive_address(i)))
        return locks

    def all_change_locks(self):
        if self.kind == "legacy":
            return []
        return [bytes.fromhex(self.change_address(i))
                for i in range(self._data["next_change"])]

    def watched_locks(self):
        """Every lock the ledger should track for this wallet."""
        seen = []
        for lk in self.all_receive_locks() + self.all_change_locks():
            if lk not in seen:
                seen.append(lk)
        return seen

    # ------------------------------------------------------------ trifold
    def trifold_key(self):
        """The wallet's Trifold (PQH/QHTLC) key, built lazily.

        Building the ternary tree (729 leaves) takes a few seconds;
        the key is cached for the process lifetime. The leaf counter
        persists in <datadir>/trifold_state.json and the chain's
        spent-leaf registry is the second guard — a mnemonic restore
        rebuilds the same root but never resets either counter."""
        if self.kind != "mnemonic":
            raise WalletError("legacy wallets have no Trifold key "
                              "(import a mnemonic wallet for PQH)")
        if self._trifold is None:
            from trifold_lockbox import TrifoldKey
            state_path = os.path.join(self.datadir, "trifold_state.json")
            self._trifold = TrifoldKey(
                trifold_seed(self._seed), height=6, state_path=state_path)
        return self._trifold

    def pqh_lock(self) -> bytes:
        """The wallet's PQH receive lock: 0x02 + hash160(Trifold root)."""
        from txscript import lock_pqh_for_root
        return lock_pqh_for_root(self.trifold_key().root)

    def pqh_address(self) -> str:
        return self.pqh_lock().hex()

    # ------------------------------------------------------------ locks book
    def record_lock(self, entry: dict, passphrase: bytes):
        """Remember a lock the wallet created (HTLC/QHTLC descriptor) so
        its spend can be built later. entry: {kind, lock, descriptor, ...}"""
        self._data.setdefault("locks", []).append(entry)
        self._save(passphrase)

    def find_lock(self, lock_hex: str):
        for e in self._data.get("locks", []):
            if e.get("lock") == lock_hex:
                return e
        return None


def _now_iso():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")
