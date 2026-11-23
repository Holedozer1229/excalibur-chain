"""Unit tests for BTC-EXCAL atomic swaps in AetherionEXCAL wallet and fork node.
"""

import hashlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

# Ensure root directory is on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from excal_wallet import WalletBackend
from sphinx_os.nexus.atomic_swap import MIN_EXCAL_SWAP, MIN_BTC_SWAP
from sphinx_os.nexus.btc_bridge import BtcBridge
from fork_node import ChainStore
import secp256k1


class TestAtomicSwapIntegration(unittest.TestCase):
    """Integration test suite for BTC-EXCAL atomic swaps."""

    COUNTERPARTY_EXCAL = "0123456789abcdef0123456789abcdef01234567"
    COUNTERPARTY_BTC = "bc1qtestcounterpartyaddress00000000000000000"

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.keystore_file = Path(self.temp_dir.name) / "test_keystore.json"
        
        # Initialize wallet backend with test keystore
        self.backend = WalletBackend(profile="default")
        self.backend.keystore_path = self.keystore_file
        self.backend.create_wallet("TestPassword123!")
        self.backend.btc_bridge = BtcBridge(data_dir=self.temp_dir.name)

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

    def test_bitcoin_node_settings_save_without_persisting_rpc_password(self):
        config_path = Path(self.temp_dir.name) / "bitcoin-node.json"
        self.backend.btc_rpc_config_path = config_path
        password = "test-rpc-password-not-for-disk"
        self.backend.save_btc_rpc_config({
            "rpc_url": "http://127.0.0.1:8332",
            "network": "regtest",
            "wallet": "test wallet",
            "cookie_file": "",
            "rpc_user": "rpc-user",
            "rpc_password": password,
        })
        saved = config_path.read_text(encoding="utf-8")
        self.assertNotIn(password, saved)
        self.assertEqual(self.backend.btc_rpc_config["rpc_password"], password)
        self.assertEqual(self.backend.btc_rpc_config["network"], "regtest")

    def test_wallet_create_and_list_swap(self):
        """Test creating an atomic swap offer through WalletBackend."""
        excal_addr = self.backend.get_address()
        btc_addr = self.backend.get_btc_address()

        offer = self.backend.create_atomic_swap(
            direction="excal_to_btc",
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            initiator_address=excal_addr,
            participant_address=self.COUNTERPARTY_EXCAL,
            participant_btc_address=self.COUNTERPARTY_BTC,
        )

        self.assertIn("swap_id", offer)
        self.assertIn("btc_htlc_address", offer)
        self.assertEqual(offer["btc_htlc_address"], "")
        self.assertFalse(offer["btc_htlc_ready"])
        self.assertIn("secret_hash", offer)
        self.assertEqual(offer["excal_refund_address"], excal_addr)
        self.assertEqual(offer["btc_refund_address"], self.COUNTERPARTY_BTC)
        self.assertEqual(offer["btc_claim_address"], btc_addr)

        # Offers without counterparty key material must not advertise a fake BTC lock.
        swaps = self.backend.list_atomic_swaps()
        self.assertGreaterEqual(len(swaps), 1)
        matching = [s for s in swaps if s["swap_id"] == offer["swap_id"]]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["status"], "init")

    def test_btc_lock_requires_a_constructed_htlc(self):
        offer = self.backend.create_atomic_swap(
            direction="excal_to_btc",
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            participant_address=self.COUNTERPARTY_EXCAL,
            participant_btc_address=self.COUNTERPARTY_BTC,
        )
        with patch("excal_wallet.BitcoinCoreRPC") as rpc:
            with self.assertRaisesRegex(RuntimeError, "BTC HTLC script is missing"):
                self.backend.lock_atomic_swap_btc(offer["swap_id"], "a" * 64)
            rpc.assert_not_called()

    def test_build_bitcoin_htlc_from_real_pubkeys_and_tip(self):
        counterparty_pubkey = secp256k1.compress(secp256k1.priv_to_pub(7)).hex()
        offer = self.backend.create_atomic_swap(
            direction="excal_to_btc",
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            participant_address=self.COUNTERPARTY_EXCAL,
            participant_btc_address=self.COUNTERPARTY_BTC,
            participant_btc_pubkey=counterparty_pubkey,
            btc_tip_height=850_000,
        )

        self.assertTrue(offer["btc_htlc_ready"])
        self.assertTrue(offer["btc_htlc_address"].startswith("bc1q"))
        self.assertEqual(offer["btc_timeout"], 850_100)
        witness_script = bytes.fromhex(offer["btc_witness_script_hex"])
        self.assertEqual(
            offer["btc_script_pubkey_hex"],
            "0020" + hashlib.sha256(witness_script).hexdigest(),
        )
        self.assertEqual(
            offer["btc_witness_script_hash"],
            hashlib.sha256(witness_script).hexdigest(),
        )

    def test_invalid_quantum_htlc_parameters_are_rejected(self):
        with self.assertRaises(ValueError):
            self.backend.create_atomic_swap(
                direction="excal_to_btc",
                excal_amount=MIN_EXCAL_SWAP,
                btc_amount=MIN_BTC_SWAP,
                participant_address=self.COUNTERPARTY_EXCAL,
                participant_btc_address=self.COUNTERPARTY_BTC,
                secret_hex="00",
            )
        with self.assertRaises(ValueError):
            self.backend.create_atomic_swap(
                direction="excal_to_btc",
                excal_amount=MIN_EXCAL_SWAP,
                btc_amount=MIN_BTC_SWAP,
                participant_address=self.COUNTERPARTY_EXCAL,
                participant_btc_address=self.COUNTERPARTY_BTC,
                participant_btc_pubkey="02" + "00" * 32,
                btc_tip_height=850_000,
            )

    def test_full_swap_lifecycle_claim(self):
        """Test full atomic swap flow: Init -> Lock EXCAL -> Lock BTC -> Claim."""
        offer = self.backend.create_atomic_swap(
            direction="excal_to_btc",
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            participant_address=self.COUNTERPARTY_EXCAL,
            participant_btc_address=self.COUNTERPARTY_BTC,
            participant_btc_pubkey=secp256k1.compress(secp256k1.priv_to_pub(13)).hex(),
            btc_tip_height=850_000,
        )
        swap_id = offer["swap_id"]

        # Lock EXCAL
        s1 = self.backend.lock_atomic_swap_excal(swap_id, "excal_tx_hash_11111111111111111111111111111111")
        self.assertEqual(s1["status"], "excal_locked")

        # Lock BTC only after Bitcoin Core confirms the expected HTLC output.
        with patch("excal_wallet.BitcoinCoreRPC") as rpc:
            rpc.return_value.verify_funding.return_value = {
                "txid": "a" * 64, "vout": 1, "confirmations": 2
            }
            s2 = self.backend.lock_atomic_swap_btc(
                swap_id, "a" * 64, funding_vout=1
            )
        self.assertEqual(s2["status"], "btc_locked")
        self.assertEqual(s2["btc_lock_tx"], "a" * 64)

        # Record each chain claim separately after broadcasting its transaction.
        secret = offer.get("secret")
        self.assertIsNotNone(secret)
        with patch("excal_wallet.BitcoinCoreRPC") as rpc:
            s3 = self.backend.claim_atomic_swap(
                swap_id, secret, chain="btc", claim_txid="a" * 64
            )
            rpc.return_value.verify_spend.assert_called_once()
        self.assertEqual(s3["status"], "btc_claimed")
        s3 = self.backend.claim_atomic_swap(
            swap_id, secret, chain="excal", claim_txid="b" * 64
        )
        self.assertEqual(s3["status"], "completed")

    def test_btc_to_excal_lock_and_claim_order(self):
        counterparty_pubkey = secp256k1.compress(secp256k1.priv_to_pub(11)).hex()
        offer = self.backend.create_atomic_swap(
            direction="btc_to_excal",
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            participant_address=self.COUNTERPARTY_EXCAL,
            participant_btc_address=self.COUNTERPARTY_BTC,
            participant_btc_pubkey=counterparty_pubkey,
            btc_tip_height=850_000,
        )
        self.assertEqual(offer["btc_refund_address"], self.backend.get_btc_address())
        self.assertEqual(offer["btc_claim_address"], self.COUNTERPARTY_BTC)
        self.assertEqual(offer["excal_refund_address"], self.COUNTERPARTY_EXCAL)
        self.assertEqual(offer["excal_claim_address"], self.backend.get_address())
        self.assertEqual(offer["btc_timeout"], 850_288)
        self.assertEqual(offer["btc_claim_pubkey"], counterparty_pubkey)
        private_hex = self.backend.keystore.get_private_key(self.backend.get_address())
        own_pubkey = secp256k1.compress(
            secp256k1.priv_to_pub(int.from_bytes(bytes.fromhex(private_hex), "big"))
        ).hex()
        self.assertEqual(offer["btc_refund_pubkey"], own_pubkey)
        swap_id = offer["swap_id"]

        with patch("excal_wallet.BitcoinCoreRPC") as rpc:
            rpc.return_value.verify_funding.return_value = {
                "txid": "d" * 64, "vout": 0, "confirmations": 1
            }
            btc_locked = self.backend.lock_atomic_swap_btc(swap_id, "d" * 64)
        self.assertEqual(btc_locked["status"], "btc_locked")
        excal_locked = self.backend.lock_atomic_swap_excal(swap_id, "e" * 64)
        self.assertEqual(excal_locked["status"], "btc_locked")
        restored_bridge = BtcBridge(data_dir=self.temp_dir.name)
        restored_swap = restored_bridge.protocol.get_swap(swap_id)
        self.assertEqual(restored_swap.btc_htlc.funding_txid, "d" * 64)
        self.assertEqual(restored_swap.excal_htlc.funding_txid, "e" * 64)
        self.assertEqual(
            restored_swap.metadata["btc_lock"]["address"],
            offer["btc_htlc_address"],
        )
        self.backend.btc_bridge = restored_bridge

        with patch("excal_wallet.BitcoinCoreRPC") as rpc:
            btc_claimed = self.backend.claim_atomic_swap(
                swap_id, offer["secret"], chain="btc", claim_txid="f" * 64
            )
            rpc.return_value.verify_spend.assert_called_once()
        self.assertEqual(btc_claimed["status"], "btc_claimed")
        completed = self.backend.claim_atomic_swap(
            swap_id, offer["secret"], chain="excal", claim_txid="1" * 64
        )
        self.assertEqual(completed["status"], "completed")

    def test_swap_refund_lifecycle(self):
        """Test atomic swap refund after timelock expires."""
        offer = self.backend.create_atomic_swap(
            direction="excal_to_btc",
            excal_amount=MIN_EXCAL_SWAP,
            btc_amount=MIN_BTC_SWAP,
            participant_address=self.COUNTERPARTY_EXCAL,
            participant_btc_address=self.COUNTERPARTY_BTC,
        )
        swap_id = offer["swap_id"]
        # Lock EXCAL first as required by protocol
        self.backend.lock_atomic_swap_excal(swap_id, "excal_lock_tx_hash")

        # Record the already-broadcast EXCAL refund transaction.
        refunded = self.backend.refund_atomic_swap(
            swap_id,
            chain="excal",
            refund_txid="c" * 64,
        )
        self.assertEqual(refunded["status"], "refund_excal")

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
