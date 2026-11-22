#!/usr/bin/env python3
"""Tests for EXCAL ↔ BTC bridge (HTLC lock + SkyNet offers)."""

import hashlib
import os
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch

from sphinx_os.nexus.btc_bridge import (
    BITCOIN_GENESIS_HASHES,
    BtcBridge,
    BitcoinCoreRPC,
    BridgeOffer,
    bitcoin_network_params,
    btc_htlc_lock,
    build_btc_htlc_script,
    estimate_htlc_spend_vsize,
    bech32_encode,
    sign_htlc_spend,
)


# Deterministic compressed test pubkeys (not used on mainnet)
CLAIM_PUB = bytes.fromhex(
    "02" + "11" * 32
)
REFUND_PUB = bytes.fromhex(
    "03" + "22" * 32
)


class TestBtcHtlcBuilders(unittest.TestCase):
    def test_script_and_address(self):
        secret_hash = hashlib.sha256(b"test-preimage-32-bytes-padded!!").digest()
        lock = btc_htlc_lock(CLAIM_PUB, REFUND_PUB, secret_hash, timeout_height=900000)
        self.assertTrue(lock["address"].startswith("bc1"))
        self.assertEqual(len(bytes.fromhex(lock["witness_script_hash"])), 32)
        script = build_btc_htlc_script(CLAIM_PUB, REFUND_PUB, secret_hash, 900000)
        self.assertEqual(script.hex(), lock["witness_script_hex"])

    def test_bech32_roundtrip_length(self):
        prog = hashlib.sha256(b"prog").digest()
        addr = bech32_encode("bc", 0, prog)
        self.assertTrue(addr.startswith("bc1q"))

    def test_signed_claim_and_refund_transactions(self):
        import secp256k1 as secp
        import struct
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import ec, utils

        private_key = (1).to_bytes(32, "big")
        claim_pubkey = secp.compress(secp.priv_to_pub(1))
        refund_pubkey = secp.compress(secp.priv_to_pub(2))
        preimage = b"p" * 32
        lock = btc_htlc_lock(
            claim_pubkey,
            refund_pubkey,
            hashlib.sha256(preimage).digest(),
            timeout_height=900_000,
        )
        witness_script = bytes.fromhex(lock["witness_script_hex"])
        destination_script = b"\x00\x14" + b"\x33" * 20

        claim_raw, claim_txid, _ = sign_htlc_spend(
            txid="ab" * 32,
            vout=1,
            amount_sats=1_000_000,
            destination_script=destination_script,
            witness_script=witness_script,
            private_key=private_key,
            expected_pubkey=claim_pubkey,
            fee_sats=200,
            secret_preimage=preimage,
        )
        refund_raw, refund_txid, _ = sign_htlc_spend(
            txid="ab" * 32,
            vout=1,
            amount_sats=1_000_000,
            destination_script=destination_script,
            witness_script=witness_script,
            private_key=(2).to_bytes(32, "big"),
            expected_pubkey=refund_pubkey,
            fee_sats=200,
            refund_height=900_000,
        )

        self.assertNotEqual(claim_txid, refund_txid)
        self.assertIn(preimage, bytes.fromhex(claim_raw))
        self.assertIn(witness_script, bytes.fromhex(refund_raw))
        raw = bytes.fromhex(claim_raw)
        outpoint = bytes.fromhex("ab" * 32)[::-1] + struct.pack("<I", 1)
        sequence = 0xFFFFFFFD
        output = (
            struct.pack("<Q", 1_000_000 - 200)
            + bytes([len(destination_script)])
            + destination_script
        )
        preimage_to_sign = (
            struct.pack("<I", 2)
            + hashlib.sha256(hashlib.sha256(outpoint).digest()).digest()
            + hashlib.sha256(hashlib.sha256(struct.pack("<I", sequence)).digest()).digest()
            + outpoint
            + bytes([len(witness_script)])
            + witness_script
            + struct.pack("<Q", 1_000_000)
            + struct.pack("<I", sequence)
            + hashlib.sha256(hashlib.sha256(output).digest()).digest()
            + struct.pack("<I", 0)
            + struct.pack("<I", 1)
        )
        digest = hashlib.sha256(hashlib.sha256(preimage_to_sign).digest()).digest()

        def compact_size(data, offset):
            size = data[offset]
            if size < 253:
                return size, offset + 1
            if size == 253:
                return int.from_bytes(data[offset + 1:offset + 3], "little"), offset + 3
            self.fail("Unexpected long CompactSize in test transaction")

        offset = 6
        input_count, offset = compact_size(raw, offset)
        self.assertEqual(input_count, 1)
        offset += 36
        script_sig_size, offset = compact_size(raw, offset)
        offset += script_sig_size + 4
        output_count, offset = compact_size(raw, offset)
        self.assertEqual(output_count, 1)
        offset += 8
        script_size, offset = compact_size(raw, offset)
        offset += script_size
        witness_count, offset = compact_size(raw, offset)
        self.assertEqual(witness_count, 4)
        signature_size, offset = compact_size(raw, offset)
        signature = raw[offset:offset + signature_size]
        ec.derive_private_key(1, ec.SECP256K1()).public_key().verify(
            signature[:-1],
            digest,
            ec.ECDSA(utils.Prehashed(hashes.SHA256())),
        )
        self.assertGreater(
            estimate_htlc_spend_vsize(witness_script, destination_script, True), 0
        )
        with self.assertRaises(ValueError):
            sign_htlc_spend(
                txid="ab" * 32,
                vout=1,
                amount_sats=1_000_000,
                destination_script=destination_script,
                witness_script=witness_script,
                private_key=private_key,
                expected_pubkey=refund_pubkey,
                fee_sats=200,
                secret_preimage=preimage,
            )


class TestBitcoinCoreRPC(unittest.TestCase):
    def setUp(self):
        self.rpc = BitcoinCoreRPC.__new__(BitcoinCoreRPC)
        self.rpc.call = Mock()
        self.rpc.network = "main"

    def test_network_params_match_configured_bitcoin_network(self):
        expected = {
            "main": ("bc", 0x80),
            "test": ("tb", 0xEF),
            "signet": ("tb", 0xEF),
            "regtest": ("bcrt", 0xEF),
        }
        for network, params in expected.items():
            with self.subTest(network=network), patch.dict(
                os.environ, {"AETHERION_BTC_NETWORK": network}
            ):
                self.assertEqual(bitcoin_network_params(), params)

    def test_get_tip_requires_expected_network(self):
        self.rpc.call.side_effect = [
            {"chain": "main"},
            BITCOIN_GENESIS_HASHES["main"],
            850_000,
        ]
        with patch.dict(os.environ, {"AETHERION_BTC_NETWORK": "main"}):
            self.assertEqual(self.rpc.get_tip_height(), 850_000)

    def test_mainnet_requires_canonical_genesis_hash(self):
        self.rpc.call.side_effect = [
            {"chain": "main"},
            "00" * 32,
        ]
        with patch.dict(os.environ, {"AETHERION_BTC_NETWORK": "main"}):
            with self.assertRaisesRegex(RuntimeError, "genesis hash"):
                self.rpc._check_network()

    def test_node_configuration_selects_network_without_environment_mutation(self):
        config = {
            "rpc_url": "https://node.example:8332",
            "network": "signet",
            "wallet": "test wallet",
            "rpc_user": "rpc-user",
            "rpc_password": "session-only",
        }
        with patch.object(BitcoinCoreRPC, "_load_auth", return_value="auth"):
            rpc = BitcoinCoreRPC(config=config)
        self.assertEqual(rpc.network, "signet")
        self.assertEqual(rpc.url, "https://node.example:8332")
        self.assertEqual(
            rpc.wallet_url,
            "https://node.example:8332/wallet/test%20wallet",
        )
        self.assertEqual(os.environ.get("AETHERION_BTC_NETWORK"), None)

    def test_canonical_genesis_hashes_are_configured_for_supported_networks(self):
        self.assertEqual(set(BITCOIN_GENESIS_HASHES), {"main", "test", "signet", "regtest"})
        self.assertEqual(
            BITCOIN_GENESIS_HASHES["main"],
            "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f",
        )

    def test_prepare_funding_returns_exact_wallet_fee(self):
        self.rpc._check_network = Mock()
        self.rpc.call_wallet = Mock(return_value={"psbt": "unsigned", "fee": 0.00001234})
        prepared = self.rpc.prepare_funding("bc1qtest", 100_000_000)
        self.assertEqual(prepared["psbt"], "unsigned")
        self.assertEqual(prepared["fee_sats"], 1234)
        self.rpc.call_wallet.assert_called_once_with(
            "walletcreatefundedpsbt",
            [[], [{"bc1qtest": 1.0}], 0, {"lockUnspents": False}, True],
        )

    def test_broadcast_funding_requires_one_exact_htlc_output(self):
        txid = "cd" * 32
        self.rpc._check_network = Mock()
        self.rpc.call_wallet = Mock(side_effect=[
            {"psbt": "signed", "complete": True},
            {"hex": "signed-transaction", "complete": True},
        ])
        self.rpc.call = Mock(side_effect=[
            {
                "txid": txid,
                "vout": [
                    {"n": 0, "scriptPubKey": {"hex": "0014" + "11" * 20}, "value": 0.1},
                    {"n": 1, "scriptPubKey": {"hex": "0020" + "22" * 32}, "value": 1.0},
                ],
            },
            txid,
        ])
        result = self.rpc.broadcast_funding(
            "unsigned", "0020" + "22" * 32, 100_000_000
        )
        self.assertEqual(result, {"txid": txid, "vout": 1})
        self.assertEqual(
            [call.args[0] for call in self.rpc.call.call_args_list],
            ["decoderawtransaction", "sendrawtransaction"],
        )

    def test_funding_requires_confirmed_exact_script_and_amount(self):
        self.rpc.call.side_effect = [
            {"chain": "main"},
            BITCOIN_GENESIS_HASHES["main"],
            {
                "txid": "ab" * 32,
                "confirmations": 2,
                "vout": [
                    {"scriptPubKey": {"hex": "0014" + "11" * 20}, "value": 0.1},
                    {"scriptPubKey": {"hex": "0020" + "22" * 32}, "value": 0.1},
                ],
            },
        ]
        with patch.dict(os.environ, {"AETHERION_BTC_NETWORK": "main"}):
            result = self.rpc.verify_funding(
                "ab" * 32, 1, "0020" + "22" * 32, 10_000_000
            )
        self.assertEqual(result["confirmations"], 2)

    def test_funding_rejects_unconfirmed_or_mismatched_output(self):
        for transaction, error in (
            ({
                "txid": "ab" * 32,
                "confirmations": 0,
                "vout": [{"scriptPubKey": {"hex": "0020" + "22" * 32}, "value": 0.1}],
            }, "not confirmed"),
            ({
                "txid": "ab" * 32,
                "confirmations": 1,
                "vout": [{"scriptPubKey": {"hex": "0014" + "11" * 20}, "value": 0.1}],
            }, "does not match"),
        ):
            self.rpc.call.side_effect = [
                {"chain": "main"}, BITCOIN_GENESIS_HASHES["main"], transaction
            ]
            with self.subTest(error=error), patch.dict(
                os.environ, {"AETHERION_BTC_NETWORK": "main"}
            ):
                with self.assertRaisesRegex(RuntimeError, error):
                    self.rpc.verify_funding(
                        "ab" * 32, 0, "0020" + "22" * 32, 10_000_000
                    )

    def test_claim_spend_requires_matching_outpoint_and_preimage(self):
        preimage = b"secret"
        script = b"htlc-script"
        self.rpc.call.side_effect = [
            {"chain": "main"},
            BITCOIN_GENESIS_HASHES["main"],
            {
                "txid": "cd" * 32,
                "confirmations": 1,
                "vin": [{
                    "txid": "ab" * 32,
                    "vout": 2,
                    "txinwitness": ["aa", preimage.hex(), "01", script.hex()],
                }],
            },
        ]
        with patch.dict(os.environ, {"AETHERION_BTC_NETWORK": "main"}):
            result = self.rpc.verify_spend(
                "cd" * 32,
                "ab" * 32,
                2,
                witness_script=script,
                secret_hash=hashlib.sha256(preimage).digest(),
            )
        self.assertEqual(result["txid"], "cd" * 32)

    def test_refund_spend_requires_timelock_and_refund_branch(self):
        script = b"htlc-script"
        self.rpc.call.side_effect = [
            {"chain": "main"},
            BITCOIN_GENESIS_HASHES["main"],
            {
                "txid": "cd" * 32,
                "confirmations": 1,
                "locktime": 900_000,
                "blockhash": "ef" * 32,
                "vin": [{
                    "txid": "ab" * 32,
                    "vout": 2,
                    "sequence": 0xFFFFFFFE,
                    "txinwitness": ["aa", "", script.hex()],
                }],
            },
            {"height": 900_010},
        ]
        with patch.dict(os.environ, {"AETHERION_BTC_NETWORK": "main"}):
            self.rpc.verify_spend(
                "cd" * 32,
                "ab" * 32,
                2,
                witness_script=script,
                refund_height=900_000,
            )


class TestBtcBridge(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.bridge = BtcBridge(data_dir=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def test_create_offer(self):
        result = self.bridge.create_excal_to_btc_offer(
            excal_amount_swords=1 * 100_000_000,
            btc_amount_sats=10_000_000,
            excal_refund_address="0" * 40,
            btc_refund_address="bc1qtest",
            claim_pubkey=CLAIM_PUB,
            refund_pubkey=REFUND_PUB,
            btc_tip_height=850000,
            proposer_wallet="MYWALLET",
            proposer_host="10.0.0.5",
            proposer_port=9433,
        )
        self.assertIn("offer", result)
        self.assertEqual(result["offer"]["type"], "swap_offer")
        self.assertTrue(result["offer"]["btc_lock_address"].startswith("bc1"))
        self.assertTrue(result["secret_preimage"])
        self.assertNotEqual(result["secret_preimage"], result["offer"]["secret_hash"])

    def test_ingest_remote_offer(self):
        offer = BridgeOffer(
            swap_id="remote1",
            direction="excal_to_btc",
            excal_amount=100_000_000,
            btc_amount=10_000_000,
            secret_hash="aa" * 32,
            excal_refund_address="0" * 40,
            btc_refund_address="bc1q",
            proposer_wallet="THEM",
        )
        self.bridge.ingest_remote_offer(offer.to_dict())
        incoming = self.bridge.list_incoming_offers()
        self.assertEqual(len(incoming), 1)
        self.assertEqual(incoming[0]["swap_id"], "remote1")

    def test_lock_and_claim_flow(self):
        result = self.bridge.create_excal_to_btc_offer(
            excal_amount_swords=1 * 100_000_000,
            btc_amount_sats=10_000_000,
            excal_refund_address="0" * 40,
            # atomic_swap stores refund fields as hex for HtlcParameters
            btc_refund_address="00" * 20,
        )
        swap_id = result["offer"]["swap_id"]
        self.bridge.mark_excal_locked(swap_id, "excaltxid", 0)
        self.bridge.mark_btc_locked(swap_id, "btctxid", 0)
        claimed = self.bridge.mark_claimed(
            swap_id, "btc", "btcclaim", result["secret_preimage"]
        )
        self.assertIn(claimed["status"], ("btc_claimed", "completed", "excal_claimed"))


if __name__ == "__main__":
    unittest.main()
