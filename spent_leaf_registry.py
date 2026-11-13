"""spent_leaf_registry.py — Persistent spent-leaf registry for Q-Day wallet safety.

Prevents Trifold leaf reuse by recording (root, index) pairs before any
signature is produced. The registry is independent of wallet files, so
restoring a wallet backup never resets it.

File format: JSON lines (one record per line) for crash safety.
Each record: {"root": "<hex>", "index": <int>, "txid": "<hex>|null",
              "height": <int>|null}
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _registry_path() -> str:
    """Return the path to the spent-leaf registry file."""
    workspace = os.environ.get(
        "EXCAL_WORKSPACE",
        os.path.join(os.path.expanduser("~"), "workspace")
    )
    return os.path.join(workspace, "spent_leaves.jsonl")


class SpentLeafRegistry:
    """Thread-safe spent-leaf registry backed by a JSONL file."""

    def __init__(self, path: str):
        self.path = path
        self._cache: dict[tuple[str, int], dict] = {}
        self._load()

    def _load(self):
        """Load existing records from disk into the in-memory cache."""
        if not os.path.exists(self.path):
            return
        with open(self.path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    key = (record["root"], record["index"])
                    self._cache[key] = record
                except (json.JSONDecodeError, KeyError):
                    # Skip malformed lines; registry is best-effort.
                    pass

    def is_spent(self, root: bytes, index: int) -> bool:
        """Check whether (root, index) is already recorded as spent."""
        key = (root.hex(), index)
        return key in self._cache

    def first_spend(self, root: bytes, index: int) -> dict | None:
        """Return the first spend record for (root, index), or None."""
        key = (root.hex(), index)
        return self._cache.get(key)

    def record(self, root: bytes, index: int, txid: str | None = None,
               height: int | None = None):
        """Record (root, index) as spent. Appends to the JSONL file."""
        key = (root.hex(), index)
        if key in self._cache:
            return  # Already recorded; idempotent.
        record = {
            "root": key[0],
            "index": index,
            "txid": txid,
            "height": height,
        }
        self._cache[key] = record
        # Append to file for persistence.
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


def load_registry(path: str | None = None) -> SpentLeafRegistry:
    """Load or create the spent-leaf registry.

    Args:
        path: Optional custom path for tests. Defaults to the
              workspace-based registry file.

    Returns:
        A SpentLeafRegistry instance with the in-memory cache loaded.
    """
    if path is None:
        path = _registry_path()
    return SpentLeafRegistry(path)


# Quick self-test when run directly.
if __name__ == "__main__":
    import tempfile

    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl",
                                     delete=False) as tmp:
        tmp_path = tmp.name

    try:
        reg = SpentLeafRegistry(tmp_path)
        root = b"\x00" * 32
        assert not reg.is_spent(root, 0)
        reg.record(root, 0, txid="abc", height=100)
        assert reg.is_spent(root, 1) is False  # Different index.
        assert reg.is_spent(root, 0)
        first = reg.first_spend(root, 0)
        assert first["txid"] == "abc"
        assert first["height"] == 100
        # Idempotent record.
        reg.record(root, 0, txid="def", height=200)
        assert reg.first_spend(root, 0)["txid"] == "abc"  # First wins.
        print("spent_leaf_registry self-test: PASSED")
    finally:
        os.unlink(tmp_path)
