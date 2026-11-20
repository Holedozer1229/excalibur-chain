"""Unit tests for BTC-EXCAL atomic swaps in AetherionEXCAL wallet and fork node.
"""

import os
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure root directory is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from excal_wallet import WalletBackend
from sphinx_os.nexus.atomic_swap import SwapDirection, SwapStatus, MIN_EXCAL_SWAP, MIN_BTC_SWAP
from sphinx_os.nexus.btc_bridge import private_key_to_btc_address, private_key_to_wif
from fork_node import ChainStore


class TestAtomicSwapIntegration(unittest.TestCase):
    """Integration test suite for BTC-EXCAL atomic swaps."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.keystore_file = Path(self.temp_dir.name) / "test_keystore.json"
        
        # Initialize wallet backend with test keystore
        self.backend = WalletBackend(profile="default")
        self.backend.keystore_path = self.keystore_file
        self.backend.create_wallet("TestPassword123!")

    def tearDown(self):
        self.backend.close()
        self.temp_dir.cleanup()

    def test_derived_bitcoin_address(self):
        """Test native SegWit Bitcoin address derivation from wallet seed."""
        btc_addr = self.backend.get_btc_address()
        self.assertIsNotNone(btc_addr)
        self.assertTrue(btc_addr.startswith("bc1q"), f"Expected bc1q SegWit address, got {btc_addr}")
        self.assertEqual(len(btc_addr), 42)

        btc_wif = self.backend.get_btc_wif()
        self.assertIsNotNone(btc_wif)
        self.assertTrue(btc_wif.startswith(("K", "L")), f"Expected compressed mainnet WIF, got {btc_wif}")

    def test_wallet_create_and_list_swap(self):
        """Test creating an atomic swap offer through WalletBackend."""
        excal_addr = self.backend.get_address()
        btc_addr = self.backend.get_btc_address()

        offer = self.backend.create_atomic_swap(
            direction="excal_to_btc",
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            initiator_address=excal_addr,
            participant_btc_address="bc1qtestcounterpartyaddress00000000000000000",
        )

        self.assertIn("swap_id", offer)
        self.assertIn("btc_htlc_address", offer)
        self.assertTrue(offer["btc_htlc_address"].startswith("bc1q"))
        self.assertIn("secret_hash", offer)

        # List swaps
        swaps = self.backend.list_atomic_swaps()
        self.assertGreaterEqual(len(swaps), 1)
        matching = [s for s in swaps if s["swap_id"] == offer["swap_id"]]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["status"], "init")

    def test_full_swap_lifecycle_claim(self):
        """Test full atomic swap flow: Init -> Lock EXCAL -> Lock BTC -> Claim."""
        offer = self.backend.create_atomic_swap(
            direction="excal_to_btc",
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
        )
        swap_id = offer["swap_id"]

        # Lock EXCAL
        s1 = self.backend.lock_atomic_swap_excal(swap_id, "excal_tx_hash_11111111111111111111111111111111")
        self.assertEqual(s1["status"], "excal_locked")

        # Lock BTC
        s2 = self.backend.lock_atomic_swap_btc(swap_id, "btc_tx_hash_22222222222222222222222222222222")
        self.assertEqual(s2["status"], "btc_locked")

        # Claim with secret preimage
        secret = offer.get("secret")
        self.assertIsNotNone(secret)
        s3 = self.backend.claim_atomic_swap(swap_id, secret)
        self.assertEqual(s3["status"], "completed")

    def test_swap_refund_lifecycle(self):
        """Test atomic swap refund after timelock expires."""
        offer = self.backend.create_atomic_swap(
            direction="excal_to_btc",
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
        )
        swap_id = offer["swap_id"]
        initiator = self.backend.get_address()

        # Lock EXCAL first as required by protocol
        self.backend.lock_atomic_swap_excal(swap_id, "excal_lock_tx_hash")

        # Refund after block timeout
        refunded = self.backend.refund_atomic_swap(
            swap_id,
            caller_address=initiator,
            current_block=offer.get("timeout_block", 1000) + 1000,
        )
        self.assertEqual(refunded["status"], "refunded")

    def test_node_chainstore_atomic_swap_rpc_methods(self):
        """Test ChainStore methods that power fork node RPC."""
        chain_path = Path(self.temp_dir.name) / "test_chain.jsonl"
        store = ChainStore(str(chain_path))

        # Health
        health = store.get_atomic_swap_health()
        self.assertTrue(health["healthy"])

        # Create
        swap = store.create_atomic_swap(
            direction="excal_to_btc",
            excal_amount=MIN_EXCAL_SWAP * 2,
            btc_amount=MIN_BTC_SWAP * 2,
            initiator_address="0123456789abcdef0123456789abcdef01234567",
        )
        self.assertIn("swap_id", swap)
        sid = swap["swap_id"]

        # Get
        retrieved = store.get_atomic_swap(sid)
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved["swap_id"], sid)

        # List
        all_swaps = store.list_atomic_swaps()
        self.assertGreaterEqual(len(all_swaps), 1)


if __name__ == "__main__":
    unittest.main()
