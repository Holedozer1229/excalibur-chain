import unittest

from node_config import resolve_p2p_host


class P2PBindPolicyTests(unittest.TestCase):
    def test_fork_network_is_public_by_default(self):
        self.assertEqual(resolve_p2p_host("fork"), "0.0.0.0")

    def test_non_fork_networks_remain_loopback_by_default(self):
        self.assertEqual(resolve_p2p_host("mainnet"), "127.0.0.1")
        self.assertEqual(resolve_p2p_host("testnet"), "127.0.0.1")

    def test_explicit_override_is_respected(self):
        self.assertEqual(resolve_p2p_host("fork", "127.0.0.1"), "127.0.0.1")
        self.assertEqual(resolve_p2p_host("testnet", "0.0.0.0"), "0.0.0.0")

    def test_empty_override_is_rejected(self):
        with self.assertRaises(ValueError):
            resolve_p2p_host("fork", "   ")


if __name__ == "__main__":
    unittest.main()
