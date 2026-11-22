"""Tests for the adapter layer.

Verifies that NodeClient, VerifierClient, and StatusAPI work correctly
without importing consensus code directly.
"""
import unittest
from unittest.mock import patch, MagicMock


class TestNodeClient(unittest.TestCase):
    """Test NodeClient without a running node."""

    def test_node_client_error_on_connection_refused(self):
        """NodeClient should raise NodeClientError when node is down."""
        from src.aetherion.adapters.node_client import NodeClient, NodeClientError

        client = NodeClient("http://127.0.0.1:19999", timeout=1)
        with self.assertRaises(NodeClientError):
            client.call("getblockcount")

    def test_node_client_convenience_methods(self):
        """Convenience methods should delegate to call()."""
        from src.aetherion.adapters.node_client import NodeClient

        client = NodeClient("http://127.0.0.1:19999", timeout=1)
        # All convenience methods should raise NodeClientError, not AttributeError
        with self.assertRaises(Exception):
            client.get_block_count()
        with self.assertRaises(Exception):
            client.get_best_block_hash()
        with self.assertRaises(Exception):
            client.get_peer_info()


class TestVerifierClient(unittest.TestCase):
    """Test VerifierClient."""

    def test_verifier_client_finds_script(self):
        """VerifierClient should locate genealogy_verify.py."""
        from src.aetherion.adapters.verifier_client import VerifierClient

        client = VerifierClient()
        # Script path should exist
        import os
        self.assertTrue(os.path.exists(client._script))

    def test_verifier_client_returns_dict(self):
        """verify() should return a dict with expected keys."""
        from src.aetherion.adapters.verifier_client import VerifierClient

        client = VerifierClient(timeout=120)
        result = client.verify()
        self.assertIn("status", result)
        self.assertIn("output", result)
        self.assertIn("errors", result)
        self.assertIn("returncode", result)

    def test_is_chain_valid_returns_bool(self):
        """is_chain_valid() should return a boolean."""
        from src.aetherion.adapters.verifier_client import VerifierClient

        client = VerifierClient(timeout=120)
        result = client.is_chain_valid()
        self.assertIsInstance(result, bool)


class TestStatusAPI(unittest.TestCase):
    """Test StatusAPI."""

    def test_status_api_builds_status(self):
        """_build_status should return a dict with expected schema."""
        from src.aetherion.adapters.status_api import StatusAPI

        mock_client = MagicMock()
        mock_client.get_block_count.return_value = 100
        mock_client.get_best_block_hash.return_value = "abc123"
        mock_client.get_peer_info.return_value = [{"addr": "1.2.3.4:9433"}]

        api = StatusAPI(mock_client)
        status = api._build_status()

        self.assertEqual(status["network"], "excalibur")
        self.assertTrue(status["online"])
        self.assertEqual(status["height"], 100)
        self.assertEqual(status["tip_hash"], "abc123")
        self.assertEqual(status["peer_count"], 1)
        self.assertEqual(status["sync_status"], "synced")

    def test_status_api_handles_errors(self):
        """_build_status should handle node errors gracefully."""
        from src.aetherion.adapters.status_api import StatusAPI

        mock_client = MagicMock()
        mock_client.get_block_count.side_effect = Exception("node down")

        api = StatusAPI(mock_client)
        status = api._build_status()

        self.assertEqual(status["network"], "excalibur")
        self.assertFalse(status["online"])
        self.assertEqual(status["sync_status"], "disconnected")


if __name__ == "__main__":
    unittest.main()
