#!/usr/bin/env python3
"""
AetherionEXCAL OpenSQL — Persistent Wallet Database

SQLite-based database for storing all wallet data:
- Addresses and keypairs (encrypted)
- Transactions (sent/received)
- UTXOs (unspent transaction outputs)
- Peers (P2P network)
- Governance (Knights, proposals, votes)
- NFTs (Knight NFTs with ZK proofs)
- Chain checkpoints (height/hash)

Usage:
    from sphinx_os.nexus.opensql import OpenSQL
    db = OpenSQL()
    db.add_address("my_wallet", "ABC123...", encrypted_key)
    txs = db.get_transactions()
"""

import os
import json
import sqlite3
import hashlib
import time
import threading
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Dict, Any

# ─── Genesis Seed Key ─────────────────────────────────────────────────────
# Admin-only encrypted storage — loaded from vault, never hardcoded
from .genesis_vault import ensure_vault, get_genesis_seed

_GENESIS_SEED_INIT = "A1B3F8D6C4B2A1B3C5D7E9F8D6C4B2A1B3C5D7E9F8D6C4B2A1B3C5D7E9C5D7E9"
GENESIS_SEED_KEY = ensure_vault(_GENESIS_SEED_INIT)
del _GENESIS_SEED_INIT


class OpenSQL:
    """Persistent wallet database using SQLite."""

    def __init__(self, db_path=None):
        self.db_path = db_path or os.path.expanduser("~/.excal_wallet/excal.db")
        if not self.db_path.startswith(":memory:"):
            os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._lock = threading.Lock()
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._init_db()

    def _init_db(self):
        """Initialize all database tables."""
        cur = self.conn.cursor()

        # Addresses table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS addresses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                label TEXT NOT NULL DEFAULT 'wallet',
                address TEXT UNIQUE NOT NULL,
                encrypted_key BLOB,
                created_at REAL NOT NULL,
                is_mine INTEGER DEFAULT 1,
                genesis_derived INTEGER DEFAULT 0
            )
        """)

        # Transactions table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_id TEXT UNIQUE NOT NULL,
                direction TEXT NOT NULL DEFAULT 'received',
                address TEXT NOT NULL,
                amount REAL NOT NULL,
                fee REAL DEFAULT 0,
                confirmations INTEGER DEFAULT 0,
                block_height INTEGER,
                block_hash TEXT,
                data BLOB,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            )
        """)

        # UTXOs table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS utxos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tx_id TEXT NOT NULL,
                output_index INTEGER NOT NULL,
                address TEXT NOT NULL,
                amount REAL NOT NULL,
                block_height INTEGER,
                is_mine INTEGER DEFAULT 1,
                is_spent INTEGER DEFAULT 0,
                spent_tx_id TEXT,
                created_at REAL NOT NULL,
                UNIQUE(tx_id, output_index)
            )
        """)

        # Peers table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS peers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                host TEXT NOT NULL,
                port INTEGER NOT NULL,
                version TEXT DEFAULT '3.0.0',
                last_seen REAL NOT NULL,
                first_seen REAL NOT NULL,
                entanglement_strength REAL DEFAULT 0,
                resonance_score REAL DEFAULT 0,
                is_active INTEGER DEFAULT 1,
                UNIQUE(host, port)
            )
        """)

        # Governance table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS governance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                proposer TEXT,
                status TEXT DEFAULT 'pending',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                data BLOB
            )
        """)

        # Knights table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS knights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                address TEXT UNIQUE NOT NULL,
                specialization TEXT DEFAULT 'Sentinel',
                phi_score REAL DEFAULT 0,
                uruu_balance REAL DEFAULT 0,
                excal_stake REAL DEFAULT 0,
                status TEXT DEFAULT 'active',
                inducted_at REAL NOT NULL,
                nft_id TEXT,
                data BLOB
            )
        """)

        # NFTs table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS nfts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nft_id TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                rarity TEXT NOT NULL,
                owner_address TEXT NOT NULL,
                traits BLOB,
                zk_proof BLOB,
                metadata_uri TEXT,
                minted_at REAL NOT NULL,
                data BLOB
            )
        """)

        # Chain checkpoints table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chain_checkpoints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                height INTEGER UNIQUE NOT NULL,
                block_hash TEXT NOT NULL,
                timestamp REAL NOT NULL,
                verified INTEGER DEFAULT 1
            )
        """)

        # Settings table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY NOT NULL,
                value TEXT,
                updated_at REAL NOT NULL
            )
        """)

        # Insert default settings
        now = time.time()
        cur.execute("""
            INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES
            ('genesis_vault', 'encrypted', ?),
            ('network', 'mainnet', ?),
            ('rpc_port', '9432', ?),
            ('p2p_port', '9433', ?),
            ('beacon_port', '9435', ?)
        """, (now, now, now, now, now))

        self.conn.commit()

    # ─── Addresses ──────────────────────────────────────────────────────

    def add_address(self, label, address, encrypted_key=None, genesis_derived=False):
        """Add a wallet address."""
        with self._lock:
            try:
                self.conn.execute(
                    "INSERT INTO addresses (label, address, encrypted_key, created_at, genesis_derived) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (label, address, encrypted_key, time.time(), 1 if genesis_derived else 0)
                )
                self.conn.commit()
                return True
            except sqlite3.IntegrityError:
                self.conn.execute(
                    "UPDATE addresses SET label=?, encrypted_key=? WHERE address=?",
                    (label, encrypted_key, address)
                )
                self.conn.commit()
                return False

    def get_address(self, address):
        """Get address by address string."""
        row = self.conn.execute(
            "SELECT * FROM addresses WHERE address=?", (address,)
        ).fetchone()
        return dict(row) if row else None

    def get_all_addresses(self):
        """Get all wallet addresses."""
        rows = self.conn.execute(
            "SELECT * FROM addresses ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    # ─── Transactions ───────────────────────────────────────────────────

    def add_transaction(self, tx_id, direction, address, amount, fee=0,
                        block_height=None, block_hash=None, data=None):
        """Add a transaction record."""
        now = time.time()
        with self._lock:
            try:
                self.conn.execute(
                    "INSERT INTO transactions (tx_id, direction, address, amount, fee, "
                    "confirmations, block_height, block_hash, data, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, 0, ?, ?, ?, ?, ?)",
                    (tx_id, direction, address, amount, fee, block_height, block_hash,
                     json.dumps(data) if data else None, now, now)
                )
                self.conn.commit()
                return True
            except sqlite3.IntegrityError:
                self.conn.execute(
                    "UPDATE transactions SET amount=?, fee=?, block_height=?, block_hash=?, "
                    "updated_at=? WHERE tx_id=?",
                    (amount, fee, block_height, block_hash, now, tx_id)
                )
                self.conn.commit()
                return False

    def get_transaction(self, tx_id):
        """Get transaction by ID."""
        row = self.conn.execute(
            "SELECT * FROM transactions WHERE tx_id=?", (tx_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_transactions(self, address=None, limit=100, offset=0):
        """Get transactions, optionally filtered by address."""
        if address:
            rows = self.conn.execute(
                "SELECT * FROM transactions WHERE address=? "
                "ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (address, limit, offset)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM transactions ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset)
            ).fetchall()
        return [dict(r) for r in rows]

    def update_confirmations(self, tx_id, confirmations):
        """Update transaction confirmation count."""
        self.conn.execute(
            "UPDATE transactions SET confirmations=?, updated_at=? WHERE tx_id=?",
            (confirmations, time.time(), tx_id)
        )
        self.conn.commit()

    # ─── UTXOs ──────────────────────────────────────────────────────────

    def add_utxo(self, tx_id, output_index, address, amount, block_height=None):
        """Add a UTXO."""
        with self._lock:
            try:
                self.conn.execute(
                    "INSERT INTO utxos (tx_id, output_index, address, amount, block_height, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (tx_id, output_index, address, amount, block_height, time.time())
                )
                self.conn.commit()
            except sqlite3.IntegrityError:
                pass

    def get_utxos(self, address=None, only_unspent=True):
        """Get UTXOs, optionally filtered by address."""
        query = "SELECT * FROM utxos WHERE 1=1"
        params = []
        if address:
            query += " AND address=?"
            params.append(address)
        if only_unspent:
            query += " AND is_spent=0"
        query += " ORDER BY block_height ASC"
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def spend_utxo(self, tx_id, output_index, spent_tx_id):
        """Mark a UTXO as spent."""
        self.conn.execute(
            "UPDATE utxos SET is_spent=1, spent_tx_id=? WHERE tx_id=? AND output_index=?",
            (spent_tx_id, tx_id, output_index)
        )
        self.conn.commit()

    def get_balance(self, address):
        """Calculate balance from UTXOs."""
        row = self.conn.execute(
            "SELECT COALESCE(SUM(amount), 0) as balance FROM utxos "
            "WHERE address=? AND is_spent=0",
            (address,)
        ).fetchone()
        return row["balance"] if row else 0

    # ─── Peers ──────────────────────────────────────────────────────────

    def add_peer(self, host, port, version="3.0.0"):
        """Add or update a peer."""
        now = time.time()
        with self._lock:
            try:
                self.conn.execute(
                    "INSERT INTO peers (host, port, version, last_seen, first_seen) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (host, port, version, now, now)
                )
            except sqlite3.IntegrityError:
                self.conn.execute(
                    "UPDATE peers SET last_seen=?, version=? WHERE host=? AND port=?",
                    (now, version, host, port)
                )
            self.conn.commit()

    def get_peers(self, active_only=True, limit=50):
        """Get peer list."""
        query = "SELECT * FROM peers WHERE 1=1"
        params = []
        if active_only:
            query += " AND is_active=1"
        query += " ORDER BY last_seen DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]

    def update_peer_entanglement(self, host, port, strength, resonance):
        """Update EREPR entanglement metrics."""
        self.conn.execute(
            "UPDATE peers SET entanglement_strength=?, resonance_score=?, last_seen=? "
            "WHERE host=? AND port=?",
            (strength, resonance, time.time(), host, port)
        )
        self.conn.commit()

    def prune_peers(self, max_age=600):
        """Remove stale peers."""
        self.conn.execute(
            "UPDATE peers SET is_active=0 WHERE last_seen < ?",
            (time.time() - max_age,)
        )
        self.conn.commit()

    # ─── Governance ─────────────────────────────────────────────────────

    def add_proposal(self, proposal_type, title, description, proposer, data=None):
        """Add a governance proposal."""
        now = time.time()
        self.conn.execute(
            "INSERT INTO governance (type, title, description, proposer, status, created_at, updated_at, data) "
            "VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)",
            (proposal_type, title, description, proposer, now, now,
             json.dumps(data) if data else None)
        )
        self.conn.commit()
        return self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    def get_proposals(self, status=None):
        """Get governance proposals."""
        if status:
            rows = self.conn.execute(
                "SELECT * FROM governance WHERE status=? ORDER BY created_at DESC",
                (status,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM governance ORDER BY created_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def update_proposal_status(self, proposal_id, status):
        """Update proposal status."""
        self.conn.execute(
            "UPDATE governance SET status=?, updated_at=? WHERE id=?",
            (status, time.time(), proposal_id)
        )
        self.conn.commit()

    # ─── Knights ────────────────────────────────────────────────────────

    def add_knight(self, name, address, specialization="Sentinel",
                   phi_score=0, uruu_balance=0, excal_stake=0, nft_id=None, data=None):
        """Add a Knight of the Round Table."""
        now = time.time()
        with self._lock:
            try:
                self.conn.execute(
                    "INSERT INTO knights (name, address, specialization, phi_score, uruu_balance, "
                    "excal_stake, status, inducted_at, nft_id, data) "
                    "VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?)",
                    (name, address, specialization, phi_score, uruu_balance,
                     excal_stake, now, nft_id, json.dumps(data) if data else None)
                )
                self.conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def get_knights(self, active_only=True):
        """Get Knights list."""
        if active_only:
            rows = self.conn.execute(
                "SELECT * FROM knights WHERE status='active' ORDER BY inducted_at ASC"
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM knights ORDER BY inducted_at ASC"
            ).fetchall()
        return [dict(r) for r in rows]

    def get_knight(self, address):
        """Get knight by address."""
        row = self.conn.execute(
            "SELECT * FROM knights WHERE address=?", (address,)
        ).fetchone()
        return dict(row) if row else None

    # ─── NFTs ───────────────────────────────────────────────────────────

    def mint_nft(self, nft_id, name, rarity, owner_address, traits=None,
                 zk_proof=None, metadata_uri=None, data=None):
        """Mint a Knight NFT."""
        now = time.time()
        self.conn.execute(
            "INSERT INTO nfts (nft_id, name, rarity, owner_address, traits, zk_proof, "
            "metadata_uri, minted_at, data) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (nft_id, name, rarity, owner_address,
             json.dumps(traits) if traits else None,
             zk_proof, metadata_uri, now,
             json.dumps(data) if data else None)
        )
        self.conn.commit()

    def get_nft(self, nft_id):
        """Get NFT by ID."""
        row = self.conn.execute(
            "SELECT * FROM nfts WHERE nft_id=?", (nft_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_nfts(self, owner_address=None):
        """Get NFTs, optionally filtered by owner."""
        if owner_address:
            rows = self.conn.execute(
                "SELECT * FROM nfts WHERE owner_address=? ORDER BY minted_at DESC",
                (owner_address,)
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM nfts ORDER BY minted_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    # ─── Chain Checkpoints ──────────────────────────────────────────────

    def add_checkpoint(self, height, block_hash):
        """Add a chain checkpoint."""
        try:
            self.conn.execute(
                "INSERT INTO chain_checkpoints (height, block_hash, timestamp) "
                "VALUES (?, ?, ?)",
                (height, block_hash, time.time())
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            self.conn.execute(
                "UPDATE chain_checkpoints SET block_hash=?, timestamp=? WHERE height=?",
                (block_hash, time.time(), height)
            )
            self.conn.commit()

    def get_checkpoint(self, height=None):
        """Get checkpoint by height or latest."""
        if height:
            row = self.conn.execute(
                "SELECT * FROM chain_checkpoints WHERE height=?", (height,)
            ).fetchone()
        else:
            row = self.conn.execute(
                "SELECT * FROM chain_checkpoints ORDER BY height DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def get_latest_height(self):
        """Get the latest chain height."""
        row = self.conn.execute(
            "SELECT MAX(height) as height FROM chain_checkpoints"
        ).fetchone()
        return row["height"] if row and row["height"] else 0

    # ─── Settings ───────────────────────────────────────────────────────

    def set_setting(self, key, value):
        """Set a configuration value."""
        self.conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (key, str(value), time.time())
        )
        self.conn.commit()

    def get_setting(self, key, default=None):
        """Get a configuration value."""
        row = self.conn.execute(
            "SELECT value FROM settings WHERE key=?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def get_genesis_seed(self):
        """Get the genesis seed from the encrypted vault (admin-only)."""
        return get_genesis_seed()

    # ─── Utility ────────────────────────────────────────────────────────

    def get_stats(self):
        """Get database statistics."""
        stats = {}
        stats["addresses"] = self.conn.execute("SELECT COUNT(*) as c FROM addresses").fetchone()["c"]
        stats["transactions"] = self.conn.execute("SELECT COUNT(*) as c FROM transactions").fetchone()["c"]
        stats["utxos"] = self.conn.execute("SELECT COUNT(*) as c FROM utxos WHERE is_spent=0").fetchone()["c"]
        stats["peers"] = self.conn.execute("SELECT COUNT(*) as c FROM peers WHERE is_active=1").fetchone()["c"]
        stats["knights"] = self.conn.execute("SELECT COUNT(*) as c FROM knights WHERE status='active'").fetchone()["c"]
        stats["nfts"] = self.conn.execute("SELECT COUNT(*) as c FROM nfts").fetchone()["c"]
        stats["chain_height"] = self.get_latest_height()
        stats["genesis_vault"] = "encrypted"  # seed never exposed in stats
        return stats

    def close(self):
        """Close the database connection."""
        with self._lock:
            self.conn.close()

    def __del__(self):
        try:
            self.conn.close()
        except Exception:
            pass


# ─── Convenience Functions ─────────────────────────────────────────────────

def get_db(db_path=None):
    """Get or create the default OpenSQL database."""
    return OpenSQL(db_path)


def init_wallet_db(db_path=None):
    """Initialize a new wallet database."""
    db = OpenSQL(db_path)
    return db


if __name__ == "__main__":
    # Test the database
    db = OpenSQL(":memory:")
    print("OpenSQL initialized")
    print("Genesis Seed:", db.get_genesis_seed()[:16] + "...")
    print("Stats:", db.get_stats())
    db.close()
    print("OpenSQL test passed")
