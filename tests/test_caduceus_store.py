"""Unit tests for caduceus_store.py — SQLite WAL migration and high-concurrency adapters."""

import os
import tempfile
import unittest
from caduceus_store import (
    CaduceusJSONStore,
    CaduceusSQLiteStore,
    migrate_json_to_sqlite,
    get_caduceus_store,
)


class TestCaduceusStores(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.json_file = os.path.join(self.temp_dir.name, "test_caduceus.json")
        self.db_file = os.path.join(self.temp_dir.name, "test_caduceus.db")

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_json_store_operations(self):
        store = CaduceusJSONStore(self.json_file)
        store.store_capsule(
            digest="abc123digest",
            canon="caduceus_64d",
            payload={"source": "btc", "target": "excal"},
            status="verified",
            block_height=100,
        )
        capsule = store.get_capsule("abc123digest")
        self.assertIsNotNone(capsule)
        self.assertEqual(capsule["canon"], "caduceus_64d")
        self.assertEqual(capsule["block_height"], 100)

        store.store_tunnel("tun-001", 1, 64, 0.99)
        tunnel = store.get_tunnel("tun-001")
        self.assertIsNotNone(tunnel)
        self.assertEqual(tunnel["source_hexagram"], 1)

    def test_sqlite_wal_store_operations(self):
        store = CaduceusSQLiteStore(self.db_file)
        
        # Verify WAL mode
        with store._connect() as conn:
            mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
            self.assertEqual(mode.lower(), "wal")

        # Store and retrieve capsule
        store.store_capsule(
            digest="digest_sqlite_001",
            canon="caduceus_256d",
            payload={"txid": "deadbeef", "val": 500},
            status="confirmed",
            block_height=200,
        )
        capsule = store.get_capsule("digest_sqlite_001")
        self.assertIsNotNone(capsule)
        self.assertEqual(capsule["status"], "confirmed")
        self.assertEqual(capsule["payload"]["val"], 500)

        # Store and retrieve tunnel
        store.store_tunnel("tun-sqlite-1", 7, 49, 0.95)
        tunnel = store.get_tunnel("tun-sqlite-1")
        self.assertIsNotNone(tunnel)
        self.assertEqual(tunnel["target_hexagram"], 49)

        # Audit log entries
        audit = store.get_audit_log(10)
        self.assertGreaterEqual(len(audit), 2)

    def test_migration_from_json_to_sqlite(self):
        # 1. Populate JSON store
        json_store = CaduceusJSONStore(self.json_file)
        for i in range(5):
            json_store.store_capsule(
                digest=f"digest_{i}",
                canon="caduceus_64d",
                payload={"index": i},
                status="verified",
            )
            json_store.store_tunnel(
                tunnel_id=f"tunnel_{i}",
                source_hexagram=i,
                target_hexagram=i + 1,
                resonance=0.9,
            )

        # 2. Run migration
        migrated = migrate_json_to_sqlite(self.json_file, self.db_file)
        self.assertEqual(migrated, 10)  # 5 capsules + 5 tunnels

        # 3. Verify in SQLite
        sqlite_store = CaduceusSQLiteStore(self.db_file)
        capsules = sqlite_store.list_capsules()
        self.assertEqual(len(capsules), 5)
        tunnels = sqlite_store.list_tunnels()
        self.assertEqual(len(tunnels), 5)


if __name__ == "__main__":
    unittest.main()
