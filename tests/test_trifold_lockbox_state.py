"""Regression tests for Trifold persistent one-time-leaf reservations."""
import json
import multiprocessing
import os
import tempfile
import unittest

from trifold_lockbox import TrifoldKey


def _reserve_in_child(path, root_hex, capacity, queue):
    # Avoid constructing the expensive Merkle tree: exercise the actual
    # persisted reservation path with a minimal TrifoldKey instance.
    key = object.__new__(TrifoldKey)
    key.state_path = path
    key.root = bytes.fromhex(root_hex)
    key.capacity = capacity
    key.next_index = 0
    try:
        queue.put(("ok", key._reserve_index()))
    except Exception as exc:
        queue.put(("error", repr(exc)))


class TrifoldStateTests(unittest.TestCase):
    def test_root_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state.json")
            with open(path, "w") as f:
                json.dump({"root": "11" * 32, "next_index": 9}, f)
            key = object.__new__(TrifoldKey)
            key.state_path = path
            key.root = bytes.fromhex("22" * 32)
            key.capacity = 27
            key.next_index = 0
            with self.assertRaisesRegex(ValueError, "root mismatch"):
                key._load_state()

    def test_concurrent_processes_reserve_distinct_indices(self):
        # fcntl is POSIX; the production deployment is Linux.
        if os.name != "posix":
            self.skipTest("POSIX file locking is required")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state.json")
            root_hex = "ab" * 32
            count = 12
            ctx = multiprocessing.get_context("fork")
            queue = ctx.Queue()
            workers = [
                ctx.Process(
                    target=_reserve_in_child,
                    args=(path, root_hex, 100, queue),
                )
                for _ in range(count)
            ]
            for worker in workers:
                worker.start()
            results = [queue.get(timeout=20) for _ in workers]
            for worker in workers:
                worker.join(timeout=20)
                self.assertEqual(worker.exitcode, 0)
            self.assertTrue(all(status == "ok" for status, _ in results))
            indices = [value for _, value in results]
            self.assertEqual(sorted(indices), list(range(count)))
            with open(path) as f:
                state = json.load(f)
            self.assertEqual(state["root"], root_hex)
            self.assertEqual(state["next_index"], count)

    def test_corrupt_state_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "state.json")
            with open(path, "w") as f:
                f.write("{not-json")
            key = object.__new__(TrifoldKey)
            key.state_path = path
            key.root = bytes.fromhex("33" * 32)
            key.capacity = 27
            key.next_index = 0
            with self.assertRaisesRegex(ValueError, "corrupt Trifold state"):
                key._reserve_index()


if __name__ == "__main__":
    unittest.main(verbosity=2)
