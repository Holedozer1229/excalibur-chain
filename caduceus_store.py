"""caduceus_store.py — High-Concurrency Storage Adapter for BIP-369 CADUCEUS State Tunnels.

Provides:
1. CaduceusJSONStore: Lightweight file-backed JSON store (default for dev/local).
2. CaduceusSQLiteStore: High-concurrency enterprise adapter with SQLite WAL (Write-Ahead Logging).
3. migrate_json_to_sqlite: Migration tool to convert caduceus_store.json into SQLite WAL database.
4. get_caduceus_store(): Factory function that selects backend based on CADUCEUS_STORAGE_BACKEND env var.

Author: Travis Dale Jones
"""

import json
import os
import sqlite3
import time
from typing import Dict, List, Optional, Any, Union


DEFAULT_JSON_PATH = "caduceus_store.json"
DEFAULT_SQLITE_PATH = "caduceus_store.db"


class CaduceusJSONStore:
    """Lightweight file-backed JSON store for Caduceus capsules and tunnels."""

    def __init__(self, filepath: str = DEFAULT_JSON_PATH):
        self.filepath = filepath
        self._cache = {
            "version": "1.0.0",
            "capsules": {},
            "state_tunnels": {},
            "audit_log": [],
        }
        self.load()

    def load(self) -> None:
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    self._cache = json.load(f)
            except Exception:
                pass

    def save(self) -> None:
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(self._cache, f, indent=2)

    def store_capsule(self, digest: str, canon: str, payload: Dict[str, Any],
                      status: str = "verified", block_height: Optional[int] = None) -> None:
        self._cache["capsules"][digest] = {
            "digest": digest,
            "canon": canon,
            "payload": payload,
            "status": status,
            "block_height": block_height,
            "created_at": time.time(),
        }
        self._log_audit("store_capsule", digest)
        self.save()

    def get_capsule(self, digest: str) -> Optional[Dict[str, Any]]:
        return self._cache["capsules"].get(digest)

    def list_capsules(self) -> List[Dict[str, Any]]:
        return list(self._cache["capsules"].values())

    def store_tunnel(self, tunnel_id: str, source_hexagram: int, target_hexagram: int,
                     resonance: float, status: str = "active") -> None:
        self._cache["state_tunnels"][tunnel_id] = {
            "tunnel_id": tunnel_id,
            "source_hexagram": source_hexagram,
            "target_hexagram": target_hexagram,
            "resonance": resonance,
            "status": status,
            "updated_at": time.time(),
        }
        self._log_audit("store_tunnel", tunnel_id)
        self.save()

    def get_tunnel(self, tunnel_id: str) -> Optional[Dict[str, Any]]:
        return self._cache["state_tunnels"].get(tunnel_id)

    def list_tunnels(self) -> List[Dict[str, Any]]:
        return list(self._cache["state_tunnels"].values())

    def _log_audit(self, action: str, entity_id: str) -> None:
        self._cache["audit_log"].append({
            "action": action,
            "entity_id": entity_id,
            "timestamp": time.time(),
        })


from contextlib import contextmanager


class CaduceusSQLiteStore:
    """Enterprise-grade SQLite store configured with Write-Ahead Logging (WAL)."""

    def __init__(self, db_path: str = DEFAULT_SQLITE_PATH):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        conn.execute("PRAGMA busy_timeout = 5000;")
        conn.execute("PRAGMA foreign_keys = ON;")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS caduceus_capsules (
                    digest TEXT PRIMARY KEY,
                    canon TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'verified',
                    block_height INTEGER,
                    created_at REAL NOT NULL
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS caduceus_tunnels (
                    tunnel_id TEXT PRIMARY KEY,
                    source_hexagram INTEGER NOT NULL,
                    target_hexagram INTEGER NOT NULL,
                    resonance REAL NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    updated_at REAL NOT NULL
                );
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS caduceus_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    action TEXT NOT NULL,
                    entity_id TEXT NOT NULL,
                    timestamp REAL NOT NULL
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_capsules_canon ON caduceus_capsules(canon);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_capsules_status ON caduceus_capsules(status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_tunnels_status ON caduceus_tunnels(status);")

    def store_capsule(self, digest: str, canon: str, payload: Dict[str, Any],
                      status: str = "verified", block_height: Optional[int] = None) -> None:
        now = time.time()
        payload_str = json.dumps(payload)
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO caduceus_capsules 
                (digest, canon, payload, status, block_height, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (digest, canon, payload_str, status, block_height, now))
            conn.execute("""
                INSERT INTO caduceus_audit_log (action, entity_id, timestamp)
                VALUES (?, ?, ?)
            """, ("store_capsule", digest, now))

    def get_capsule(self, digest: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM caduceus_capsules WHERE digest = ?", (digest,))
            row = cur.fetchone()
            if not row:
                return None
            return {
                "digest": row["digest"],
                "canon": row["canon"],
                "payload": json.loads(row["payload"]),
                "status": row["status"],
                "block_height": row["block_height"],
                "created_at": row["created_at"],
            }

    def list_capsules(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM caduceus_capsules ORDER BY created_at DESC")
            results = []
            for row in cur.fetchall():
                results.append({
                    "digest": row["digest"],
                    "canon": row["canon"],
                    "payload": json.loads(row["payload"]),
                    "status": row["status"],
                    "block_height": row["block_height"],
                    "created_at": row["created_at"],
                })
            return results

    def store_tunnel(self, tunnel_id: str, source_hexagram: int, target_hexagram: int,
                     resonance: float, status: str = "active") -> None:
        now = time.time()
        with self._connect() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO caduceus_tunnels
                (tunnel_id, source_hexagram, target_hexagram, resonance, status, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (tunnel_id, source_hexagram, target_hexagram, resonance, status, now))
            conn.execute("""
                INSERT INTO caduceus_audit_log (action, entity_id, timestamp)
                VALUES (?, ?, ?)
            """, ("store_tunnel", tunnel_id, now))

    def get_tunnel(self, tunnel_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM caduceus_tunnels WHERE tunnel_id = ?", (tunnel_id,))
            row = cur.fetchone()
            if not row:
                return None
            return {
                "tunnel_id": row["tunnel_id"],
                "source_hexagram": row["source_hexagram"],
                "target_hexagram": row["target_hexagram"],
                "resonance": row["resonance"],
                "status": row["status"],
                "updated_at": row["updated_at"],
            }

    def list_tunnels(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM caduceus_tunnels ORDER BY updated_at DESC")
            return [
                {
                    "tunnel_id": row["tunnel_id"],
                    "source_hexagram": row["source_hexagram"],
                    "target_hexagram": row["target_hexagram"],
                    "resonance": row["resonance"],
                    "status": row["status"],
                    "updated_at": row["updated_at"],
                }
                for row in cur.fetchall()
            ]

    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            cur = conn.execute("SELECT * FROM caduceus_audit_log ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cur.fetchall()]


def migrate_json_to_sqlite(json_path: str = DEFAULT_JSON_PATH,
                           sqlite_path: str = DEFAULT_SQLITE_PATH) -> int:
    """Migrate an existing caduceus_store.json file into the SQLite WAL database.
    
    Returns:
        Total number of records migrated.
    """
    if not os.path.exists(json_path):
        return 0

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    sqlite_store = CaduceusSQLiteStore(sqlite_path)
    migrated_count = 0

    # Migrate capsules
    capsules = data.get("capsules", {})
    for digest, c in capsules.items():
        sqlite_store.store_capsule(
            digest=digest,
            canon=c.get("canon", "default"),
            payload=c.get("payload", {}),
            status=c.get("status", "verified"),
            block_height=c.get("block_height"),
        )
        migrated_count += 1

    # Migrate tunnels
    tunnels = data.get("state_tunnels", {})
    for tunnel_id, t in tunnels.items():
        sqlite_store.store_tunnel(
            tunnel_id=tunnel_id,
            source_hexagram=t.get("source_hexagram", 0),
            target_hexagram=t.get("target_hexagram", 0),
            resonance=t.get("resonance", 1.0),
            status=t.get("status", "active"),
        )
        migrated_count += 1

    return migrated_count


def get_caduceus_store(backend: Optional[str] = None) -> Union[CaduceusSQLiteStore, CaduceusJSONStore]:
    """Factory function returning the appropriate Caduceus storage adapter."""
    selected = (backend or os.environ.get("CADUCEUS_STORAGE_BACKEND", "sqlite")).lower()
    if selected in ("sqlite", "wal", "db"):
        return CaduceusSQLiteStore()
    return CaduceusJSONStore()
