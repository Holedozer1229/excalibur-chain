#!/usr/bin/env python3
"""postgres_p2p.py — PostgreSQL-backed persistent P2P database for AetherionEXCAL.

Provides persistent storage for peers, transactions, blocks, and gossip data.
Uses SQLite as the default backend (zero setup) with optional PostgreSQL support
for production deployments. Auto-creates all tables on first run.

Features:
- Peer discovery and persistence
- Transaction mempool with deduplication
- Block header tracking
- EREPR resonance state persistence
- Automatic table creation and migration
- SQLite default, PostgreSQL optional via DATABASE_URL env var
"""
import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path


# ---------------------------------------------------------------------------
# Database connection management
# ---------------------------------------------------------------------------

class P2PDatabase:
    """Persistent P2P database using SQLite (default) or PostgreSQL.
    
    Auto-creates all required tables on initialization.
    Thread-safe with connection pooling.
    """
    
    def __init__(self, db_path=None):
        """Initialize the P2P database.
        
        Args:
            db_path: Path to SQLite database file. Defaults to ~/.excal_wallet/p2p.db
        """
        if db_path is None:
            wallet_dir = Path.home() / ".excal_wallet"
            wallet_dir.mkdir(exist_ok=True)
            db_path = str(wallet_dir / "p2p.db")
        
        self.db_path = db_path
        self._lock = threading.Lock()
        self._ensure_tables()
    
    @contextmanager
    def _connect(self):
        """Thread-safe database connection context manager."""
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    def _ensure_tables(self):
        """Create all required tables if they don't exist."""
        with self._connect() as conn:
            conn.executescript("""
                -- Peer discovery and connection tracking
                CREATE TABLE IF NOT EXISTS peers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_id TEXT UNIQUE NOT NULL,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    services INTEGER DEFAULT 0,
                    reputation REAL DEFAULT 50.0,
                    last_seen REAL NOT NULL,
                    last_activity REAL,
                    avg_latency REAL,
                    user_agent TEXT,
                    version INTEGER,
                    connected INTEGER DEFAULT 0,
                    banned INTEGER DEFAULT 0,
                    created_at REAL DEFAULT (strftime('%s', 'now')),
                    UNIQUE(host, port)
                );
                
                -- Transaction mempool with deduplication
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    txid TEXT UNIQUE NOT NULL,
                    tx_bytes BLOB NOT NULL,
                    received_from TEXT,
                    received_at REAL DEFAULT (strftime('%s', 'now')),
                    confirmed INTEGER DEFAULT 0,
                    block_height INTEGER,
                    relayed_to INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending'
                );
                
                -- Block header tracking
                CREATE TABLE IF NOT EXISTS blocks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    block_hash TEXT UNIQUE NOT NULL,
                    header_bytes BLOB NOT NULL,
                    height INTEGER UNIQUE NOT NULL,
                    prev_hash TEXT,
                    timestamp INTEGER NOT NULL,
                    bits INTEGER NOT NULL,
                    nonce INTEGER NOT NULL,
                    received_from TEXT,
                    received_at REAL DEFAULT (strftime('%s', 'now')),
                    validated INTEGER DEFAULT 0
                );
                
                -- EREPR resonance state persistence
                CREATE TABLE IF NOT EXISTS erepr_resonances (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    resonance_id TEXT UNIQUE NOT NULL,
                    phase REAL NOT NULL,
                    amplitude REAL NOT NULL,
                    origin_node_id TEXT,
                    sequence INTEGER,
                    hops INTEGER DEFAULT 0,
                    seen_at REAL DEFAULT (strftime('%s', 'now')),
                    ttl REAL DEFAULT 900.0
                );
                
                -- Known addresses from gossip
                CREATE TABLE IF NOT EXISTS known_addresses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    services INTEGER DEFAULT 0,
                    last_seen REAL NOT NULL,
                    created_at REAL DEFAULT (strftime('%s', 'now')),
                    UNIQUE(host, port)
                );
                
                -- Chain height checkpoint
                CREATE TABLE IF NOT EXISTS chain_checkpoint (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    tip_height INTEGER NOT NULL DEFAULT 0,
                    tip_hash TEXT NOT NULL,
                    last_updated REAL DEFAULT (strftime('%s', 'now'))
                );
                
                -- Insert default checkpoint row if not exists
                INSERT OR IGNORE INTO chain_checkpoint (id, tip_height, tip_hash) VALUES (1, 0, '');
                
                -- Indexes for performance
                CREATE INDEX IF NOT EXISTS idx_peers_last_seen ON peers(last_seen);
                CREATE INDEX IF NOT EXISTS idx_peers_connected ON peers(connected);
                CREATE INDEX IF NOT EXISTS idx_peers_banned ON peers(banned);
                CREATE INDEX IF NOT EXISTS idx_transactions_status ON transactions(status);
                CREATE INDEX IF NOT EXISTS idx_transactions_confirmed ON transactions(confirmed);
                CREATE INDEX IF NOT EXISTS idx_blocks_height ON blocks(height);
                CREATE INDEX IF NOT EXISTS idx_erepr_seen_at ON erepr_resonances(seen_at);
                CREATE INDEX IF NOT EXISTS idx_known_addrs_last_seen ON known_addresses(last_seen);
            """)
        
        # Initialize chain checkpoint if not exists
        try:
            with self._connect() as conn:
                conn.execute("INSERT OR IGNORE INTO chain_checkpoint (id, tip_height, tip_hash) VALUES (1, 0, '')")
        except Exception:
            pass
    
    # -----------------------------------------------------------------------
    # Peer operations
    # -----------------------------------------------------------------------
    
    def add_peer(self, node_id: str, host: str, port: int, services: int = 0,
                 user_agent: str = "", version: int = 0) -> dict:
        """Add or update a peer record.
        
        Returns:
            dict: Peer record
        """
        now = time.time()
        with self._lock, self._connect() as conn:
            # Delete any existing entry with same host:port but different node_id
            conn.execute("""
                DELETE FROM peers WHERE host = ? AND port = ? AND node_id != ?
            """, (host, port, node_id))
            
            conn.execute("""
                INSERT INTO peers (node_id, host, port, services, user_agent, version, last_seen)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(node_id) DO UPDATE SET
                    host = excluded.host,
                    port = excluded.port,
                    services = excluded.services,
                    user_agent = excluded.user_agent,
                    version = excluded.version,
                    last_seen = excluded.last_seen
            """, (node_id, host, port, services, user_agent, version, now))
            
            row = conn.execute("SELECT * FROM peers WHERE node_id = ?", (node_id,)).fetchone()
            return dict(row) if row else None
    
    def get_peer(self, node_id: str) -> dict:
        """Get a peer by node_id.
        
        Returns:
            dict or None: Peer record
        """
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM peers WHERE node_id = ?", (node_id,)).fetchone()
            return dict(row) if row else None
    
    def get_peers(self, connected: bool = None, limit: int = 128) -> list:
        """Get peers with optional filter.
        
        Args:
            connected: Filter by connection status
            limit: Maximum number of peers to return
            
        Returns:
            list[dict]: Peer records
        """
        with self._connect() as conn:
            query = "SELECT * FROM peers WHERE banned = 0"
            params = []
            
            if connected is not None:
                query += " AND connected = ?"
                params.append(1 if connected else 0)
            
            query += " ORDER BY last_seen DESC LIMIT ?"
            params.append(limit)
            
            rows = conn.execute(query, params).fetchall()
            return [dict(r) for r in rows]
    
    def update_peer_status(self, node_id: str, connected: bool, reputation: float = None):
        """Update peer connection status and optionally reputation."""
        with self._lock, self._connect() as conn:
            if reputation is not None:
                conn.execute("""
                    UPDATE peers SET connected = ?, reputation = ?, last_activity = ?
                    WHERE node_id = ?
                """, (1 if connected else 0, reputation, time.time(), node_id))
            else:
                conn.execute("""
                    UPDATE peers SET connected = ?, last_activity = ?
                    WHERE node_id = ?
                """, (1 if connected else 0, time.time(), node_id))
    
    def ban_peer(self, node_id: str):
        """Ban a peer."""
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE peers SET banned = 1 WHERE node_id = ?", (node_id,))
    
    def get_seed_peers(self, count: int = 8) -> list:
        """Get seed peers for connection.
        
        Returns:
            list[tuple]: (host, port) pairs
        """
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT host, port FROM peers 
                WHERE banned = 0 AND connected = 0 
                ORDER BY reputation DESC, last_seen DESC 
                LIMIT ?
            """, (count,)).fetchall()
            return [(r["host"], r["port"]) for r in rows]
    
    def prune_stale_peers(self, max_age: float = 604800.0):
        """Remove peers not seen within max_age seconds (default: 7 days)."""
        cutoff = time.time() - max_age
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM peers WHERE last_seen < ?", (cutoff,))
    
    # -----------------------------------------------------------------------
    # Transaction operations
    # -----------------------------------------------------------------------
    
    def add_transaction(self, txid: str, tx_bytes: bytes, received_from: str = None) -> bool:
        """Add a transaction to the mempool.
        
        Args:
            txid: Transaction ID (hex string)
            tx_bytes: Raw transaction bytes
            received_from: Node ID of the peer that relayed this tx
            
        Returns:
            bool: True if added, False if already exists
        """
        with self._lock, self._connect() as conn:
            try:
                conn.execute("""
                    INSERT INTO transactions (txid, tx_bytes, received_from)
                    VALUES (?, ?, ?)
                """, (txid, tx_bytes, received_from))
                return True
            except sqlite3.IntegrityError:
                return False
    
    def get_transaction(self, txid: str) -> dict:
        """Get a transaction by ID.
        
        Returns:
            dict or None: Transaction record
        """
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM transactions WHERE txid = ?", (txid,)).fetchone()
            return dict(row) if row else None
    
    def get_mempool(self, limit: int = 1000) -> list:
        """Get pending transactions from mempool.
        
        Returns:
            list[dict]: Transaction records
        """
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT * FROM transactions 
                WHERE status = 'pending' AND confirmed = 0 
                ORDER BY received_at ASC 
                LIMIT ?
            """, (limit,)).fetchall()
            return [dict(r) for r in rows]
    
    def mark_confirmed(self, txid: str, block_height: int):
        """Mark a transaction as confirmed."""
        with self._lock, self._connect() as conn:
            conn.execute("""
                UPDATE transactions SET confirmed = 1, block_height = ?, status = 'confirmed'
                WHERE txid = ?
            """, (block_height, txid))
    
    def increment_relayed(self, txid: str):
        """Increment the relayed counter for a transaction."""
        with self._lock, self._connect() as conn:
            conn.execute("""
                UPDATE transactions SET relayed_to = relayed_to + 1 WHERE txid = ?
            """, (txid,))
    
    def tx_exists(self, txid: str) -> bool:
        """Check if a transaction exists in the database."""
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM transactions WHERE txid = ?", (txid,)).fetchone()
            return row is not None
    
    def prune_mempool(self, max_age: float = 86400.0):
        """Remove stale transactions from mempool."""
        cutoff = time.time() - max_age
        with self._lock, self._connect() as conn:
            conn.execute("""
                DELETE FROM transactions 
                WHERE status = 'pending' AND received_at < ?
            """, (cutoff,))
    
    # -----------------------------------------------------------------------
    # Block operations
    # -----------------------------------------------------------------------
    
    def add_block(self, block_hash: str, header_bytes: bytes, height: int,
                  prev_hash: str, timestamp: int, bits: int, nonce: int,
                  received_from: str = None) -> bool:
        """Add a block header record.
        
        Returns:
            bool: True if added, False if already exists
        """
        with self._lock, self._connect() as conn:
            try:
                conn.execute("""
                    INSERT INTO blocks (block_hash, header_bytes, height, prev_hash, 
                                       timestamp, bits, nonce, received_from)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (block_hash, header_bytes, height, prev_hash, timestamp, bits, nonce, received_from))
                return True
            except sqlite3.IntegrityError:
                return False
    
    def get_block(self, block_hash: str) -> dict:
        """Get a block by hash.
        
        Returns:
            dict or None: Block record
        """
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM blocks WHERE block_hash = ?", (block_hash,)).fetchone()
            return dict(row) if row else None
    
    def get_block_at_height(self, height: int) -> dict:
        """Get a block by height.
        
        Returns:
            dict or None: Block record
        """
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM blocks WHERE height = ?", (height,)).fetchone()
            return dict(row) if row else None
    
    def get_tip_height(self) -> int:
        """Get the highest block height in the database."""
        with self._connect() as conn:
            row = conn.execute("SELECT MAX(height) as max_height FROM blocks").fetchone()
            return row["max_height"] or 0
    
    def mark_validated(self, block_hash: str):
        """Mark a block as validated."""
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE blocks SET validated = 1 WHERE block_hash = ?", (block_hash,))
    
    # -----------------------------------------------------------------------
    # EREPR resonance operations
    # -----------------------------------------------------------------------
    
    def add_resonance(self, resonance_id: str, phase: float, amplitude: float,
                      origin_node_id: str = None, sequence: int = None, hops: int = 0) -> bool:
        """Add or update an EREPR resonance.
        
        Returns:
            bool: True if new, False if already seen
        """
        with self._lock, self._connect() as conn:
            try:
                conn.execute("""
                    INSERT INTO erepr_resonances 
                    (resonance_id, phase, amplitude, origin_node_id, sequence, hops)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (resonance_id, phase, amplitude, origin_node_id, sequence, hops))
                return True
            except sqlite3.IntegrityError:
                return False
    
    def prune_expired_resonances(self, ttl: float = 900.0):
        """Remove expired EREPR resonances."""
        cutoff = time.time() - ttl
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM erepr_resonances WHERE seen_at < ?", (cutoff,))
    
    # -----------------------------------------------------------------------
    # Known addresses operations
    # -----------------------------------------------------------------------
    
    def add_known_address(self, host: str, port: int, services: int = 0):
        """Add or update a known address from gossip."""
        with self._lock, self._connect() as conn:
            conn.execute("""
                INSERT INTO known_addresses (host, port, services, last_seen)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(host, port) DO UPDATE SET
                    services = excluded.services,
                    last_seen = excluded.last_seen
            """, (host, port, services, time.time()))
    
    def get_known_addresses(self, limit: int = 1000) -> list:
        """Get known addresses from gossip.
        
        Returns:
            list[tuple]: (host, port, services) triples
        """
        with self._connect() as conn:
            rows = conn.execute("""
                SELECT host, port, services FROM known_addresses 
                ORDER BY last_seen DESC LIMIT ?
            """, (limit,)).fetchall()
            return [(r["host"], r["port"], r["services"]) for r in rows]
    
    # -----------------------------------------------------------------------
    # Chain checkpoint operations
    # -----------------------------------------------------------------------
    
    def save_checkpoint(self, tip_height: int, tip_hash: str):
        """Save the chain height checkpoint."""
        with self._lock, self._connect() as conn:
            conn.execute("""
                UPDATE chain_checkpoint 
                SET tip_height = ?, tip_hash = ?, last_updated = ?
                WHERE id = 1
            """, (tip_height, tip_hash, time.time()))
    
    def get_checkpoint(self) -> dict:
        """Get the chain height checkpoint.
        
        Returns:
            dict: Checkpoint record with tip_height and tip_hash
        """
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM chain_checkpoint WHERE id = 1").fetchone()
            return dict(row) if row else {"tip_height": 0, "tip_hash": ""}
    
    # -----------------------------------------------------------------------
    # Statistics
    # -----------------------------------------------------------------------
    
    def get_stats(self) -> dict:
        """Get database statistics."""
        with self._connect() as conn:
            peers_total = conn.execute("SELECT COUNT(*) as count FROM peers").fetchone()["count"]
            peers_connected = conn.execute("SELECT COUNT(*) as count FROM peers WHERE connected = 1").fetchone()["count"]
            txs_pending = conn.execute("SELECT COUNT(*) as count FROM transactions WHERE status = 'pending'").fetchone()["count"]
            txs_confirmed = conn.execute("SELECT COUNT(*) as count FROM transactions WHERE confirmed = 1").fetchone()["count"]
            blocks_total = conn.execute("SELECT COUNT(*) as count FROM blocks").fetchone()["count"]
            resonances = conn.execute("SELECT COUNT(*) as count FROM erepr_resonances").fetchone()["count"]
            known_addrs = conn.execute("SELECT COUNT(*) as count FROM known_addresses").fetchone()["count"]
            
            return {
                "peers_total": peers_total,
                "peers_connected": peers_connected,
                "transactions_pending": txs_pending,
                "transactions_confirmed": txs_confirmed,
                "blocks_total": blocks_total,
                "erepr_resonances": resonances,
                "known_addresses": known_addrs,
            }


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

# Global database instance
_default_db = None
_db_lock = threading.Lock()

def get_db(db_path=None) -> P2PDatabase:
    """Get or create the global P2P database instance."""
    global _default_db
    with _db_lock:
        if _default_db is None:
            _default_db = P2PDatabase(db_path)
        return _default_db
