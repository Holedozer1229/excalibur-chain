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
from file_locks import exclusive_file_lock, fsync_directory

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
        self.path = os.path.normcase(os.path.abspath(path))
        self._cache: dict[tuple[str, int], dict] = {}
        self._load()

    def _load(self):
        """Load existing records from disk into the in-memory cache."""
        with exclusive_file_lock(self.path + ".lock"):
            self._refresh_locked()

    def _refresh_locked(self):
        """Reload under the process lock; malformed history fails closed."""
        cache = {}
        if os.path.exists(self.path):
            with open(self.path, "r", encoding="utf-8") as f:
                for line_number, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        record = json.loads(line)
                        root = record["root"]
                        index = record["index"]
                        if (not isinstance(root, str) or len(root) != 64
                                or not isinstance(index, int)
                                or isinstance(index, bool) or index < 0):
                            raise ValueError("invalid root or index")
                        decoded_root = bytes.fromhex(root)
                        if len(decoded_root) != 32:
                            raise ValueError("root must decode to 32 bytes")
                        root = decoded_root.hex()
                    except (json.JSONDecodeError, KeyError, TypeError,
                            ValueError) as exc:
                        raise ValueError(
                            f"corrupt spent-leaf registry at line "
                            f"{line_number}: {exc}") from exc
                    record["root"] = root
                    cache.setdefault((root, index), record)
        self._cache = cache

    def is_spent(self, root: bytes, index: int) -> bool:
        """Check whether (root, index) is already recorded as spent."""
        self._validate_pair(root, index)
        with exclusive_file_lock(self.path + ".lock"):
            self._refresh_locked()
            return (root.hex(), index) in self._cache

    def first_spend(self, root: bytes, index: int) -> dict | None:
        """Return the first spend record for (root, index), or None."""
        self._validate_pair(root, index)
        with exclusive_file_lock(self.path + ".lock"):
            self._refresh_locked()
            return self._cache.get((root.hex(), index))

    def as_set(self):
        """Snapshot all reserved pairs in validate_tx's byte-tuple format."""
        with exclusive_file_lock(self.path + ".lock"):
            self._refresh_locked()
            return {(bytes.fromhex(root), index)
                    for root, index in self._cache}

    @staticmethod
    def _validate_pair(root, index):
        if not isinstance(root, bytes) or len(root) != 32:
            raise ValueError("Trifold root must be 32 bytes")
        if not isinstance(index, int) or isinstance(index, bool) or index < 0:
            raise ValueError("Trifold leaf index must be a non-negative integer")

    def reserve(self, root: bytes, index: int, txid: str | None = None,
                height: int | None = None) -> bool:
        """Atomically reserve a leaf across threads and wallet processes.

        Returns False when another operation already reserved this pair.
        A corrupt registry or an I/O failure raises, so callers never sign
        when they cannot establish that the leaf is fresh.
        """
        self._validate_pair(root, index)
        key = (root.hex(), index)
        with exclusive_file_lock(self.path + ".lock"):
            self._refresh_locked()
            if key in self._cache:
                return False
            record = {"root": key[0], "index": index,
                      "txid": txid, "height": height}
            directory = os.path.dirname(os.path.abspath(self.path))
            os.makedirs(directory, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record) + "\n")
                f.flush()
                os.fsync(f.fileno())
            fsync_directory(directory)
            self._cache[key] = record
            return True

    def record(self, root: bytes, index: int, txid: str | None = None,
               height: int | None = None):
        """Idempotently record a pair; use reserve() when signing."""
        self.reserve(root, index, txid=txid, height=height)


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
