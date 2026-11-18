#!/usr/bin/env python3
"""Unit tests for wormhole_live_connector.py — Cross-chain wormhole bridge to live chains."""

import hashlib
import json
import time
import unittest
from unittest.mock import patch, MagicMock

from sphinx_os.nexus.wormhole_live_connector import (
    WormholeChain,
    WormholeEventStatus,
    WormholeProof,
    ChainAnchor,
    WormholeToken,
    CrossChainWormhole,
    ChainConnector,
    EVMChainClient,
    WormholeAnchorContract,
    WormholeLiveConnector,
    create_wormhole_connector,
    get_chain_connectors,
    scan_btc_burns,
    create_wormhole_proof,
)


class TestWormholeChain(unittest.TestCase):
    """Test WormholeChain enum."""

    def test_chain_values(self):
        self.assertEqual(WormholeChain.BTC.value, "bitcoin")
        self.assertEqual(WormholeChain.ETH.value, "ethereum")
        self.assertEqual(WormholeChain.BSC.value, "bsc")
        self.assertEqual(WormholeChain.ARBITRUM.value, "arbitrum")
        self.assertEqual(WormholeChain.OPTIMISM.value, "optimism")

    def test_chain_count(self):
        self.assertEqual(len(WormholeChain), 5)


class TestWormholeEventStatus(unittest.TestCase):
    """Test WormholeEventStatus enum."""

    def test_status_values(self):
        self.assertEqual(WormholeEventStatus.PENDING.value, "pending")
        self.assertEqual(WormholeEventStatus.BTC_BURNED.value, "btc_burned")
        self.assertEqual(WormholeEventStatus.WORMHOLE_OPENED.value, "wormhole_opened")
        self.assertEqual(WormholeEventStatus.ANCHORED.value, "anchored")
        self.assertEqual(WormholeEventStatus.TOKEN_MINTED.value, "token_minted")
        self.assertEqual(WormholeEventStatus.VERIFIED.value, "verified")
        self.assertEqual(WormholeEventStatus.FAILED.value, "failed")


class TestWormholeProof(unittest.TestCase):
    """Test WormholeProof dataclass."""

    def test_create_proof(self):
        proof = WormholeProof(
            burn_txid="abc123",
            burn_address="1BitcoinEaterAddressDontSendf59kuE",
            burn_amount_sats=100000,
            wormhole_hash="hash123",
            anchor_data="data",
        )
        self.assertEqual(proof.burn_txid, "abc123")
        self.assertEqual(proof.burn_amount_sats, 100000)
        self.assertIsInstance(proof.timestamp, float)

    def test_proof_timestamp_default(self):
        proof = WormholeProof(
            burn_txid="tx1",
            burn_address="addr1",
            burn_amount_sats=100,
            wormhole_hash="h1",
            anchor_data="d1",
        )
        self.assertGreater(proof.timestamp, 0)


class TestChainAnchor(unittest.TestCase):
    """Test ChainAnchor dataclass."""

    def test_create_anchor(self):
        anchor = ChainAnchor(
            chain=WormholeChain.ETH,
            tx_hash="0xabc",
            block_number=100,
            contract_address="0x123",
            status=WormholeEventStatus.ANCHORED,
        )
        self.assertEqual(anchor.chain, WormholeChain.ETH)
        self.assertEqual(anchor.block_number, 100)
        self.assertEqual(anchor.status, WormholeEventStatus.ANCHORED)


class TestWormholeToken(unittest.TestCase):
    """Test WormholeToken dataclass."""

    def test_create_token(self):
        token = WormholeToken(
            chain=WormholeChain.BSC,
            token_address="0x456",
            amount=1000,
            recipient="0x789",
            burn_txid="tx1",
            mint_tx_hash="0xdef",
        )
        self.assertEqual(token.chain, WormholeChain.BSC)
        self.assertEqual(token.amount, 1000)


class TestCrossChainWormhole(unittest.TestCase):
    """Test CrossChainWormhole dataclass."""

    def test_create_wormhole(self):
        proof = WormholeProof(
            burn_txid="tx1",
            burn_address="addr1",
            burn_amount_sats=100,
            wormhole_hash="h1",
            anchor_data="d1",
        )
        wh = CrossChainWormhole(
            wormhole_id="wh1",
            proof=proof,
        )
        self.assertEqual(wh.wormhole_id, "wh1")
        self.assertEqual(wh.status, WormholeEventStatus.PENDING)
        self.assertEqual(len(wh.anchors), 0)
        self.assertEqual(len(wh.tokens), 0)


class TestChainConnector(unittest.TestCase):
    """Test ChainConnector dataclass."""

    def test_create_connector(self):
        conn = ChainConnector(
            chain=WormholeChain.ETH,
            rpc_url="https://eth.llamarpc.com",
            chain_id=1,
        )
        self.assertFalse(conn.connected)
        self.assertEqual(conn.block_height, 0)


class TestEVMChainClient(unittest.TestCase):
    """Test EVMChainClient RPC methods."""

    def test_init(self):
        client = EVMChainClient("https://example.com/rpc", 1)
        self.assertEqual(client.rpc_url, "https://example.com/rpc")
        self.assertEqual(client.chain_id, 1)

    @patch('urllib.request.urlopen')
    def test_get_block_number(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "jsonrpc": "2.0", "result": "0x123456", "id": 1
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = lambda s, *a: None
        mock_urlopen.return_value = mock_response

        client = EVMChainClient("https://example.com", 1, timeout=5)
        block = client.get_block_number()
        self.assertEqual(block, 0x123456)

    @patch('urllib.request.urlopen')
    def test_get_balance(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "jsonrpc": "2.0", "result": "0x10000000000000000", "id": 1
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = lambda s, *a: None
        mock_urlopen.return_value = mock_response

        client = EVMChainClient("https://example.com", 1)
        balance = client.get_balance("0x1234567890123456789012345678901234567890")
        self.assertEqual(balance, 0x10000000000000000)

    @patch('urllib.request.urlopen')
    def test_get_gas_price(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "jsonrpc": "2.0", "result": "0x4A817C800", "id": 1
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = lambda s, *a: None
        mock_urlopen.return_value = mock_response

        client = EVMChainClient("https://example.com", 1)
        gas = client.get_gas_price()
        self.assertEqual(gas, 0x4A817C800)

    def test_get_gas_price_fallback(self):
        client = EVMChainClient("https://invalid.example.com", 1, timeout=1)
        gas = client.get_gas_price()
        self.assertEqual(gas, 20_000_000_000)

    @patch('urllib.request.urlopen')
    def test_is_connected_true(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "jsonrpc": "2.0", "result": "0x100", "id": 1
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = lambda s, *a: None
        mock_urlopen.return_value = mock_response

        client = EVMChainClient("https://example.com", 1)
        self.assertTrue(client.is_connected())

    def test_is_connected_false(self):
        client = EVMChainClient("https://invalid.example.com", 1, timeout=1)
        self.assertFalse(client.is_connected())

    @patch('urllib.request.urlopen')
    def test_send_raw_transaction(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "jsonrpc": "2.0", "result": "0xabc123", "id": 1
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = lambda s, *a: None
        mock_urlopen.return_value = mock_response

        client = EVMChainClient("https://example.com", 1)
        tx_hash = client.send_raw_transaction("0xrawtx")
        self.assertEqual(tx_hash, "0xabc123")

    @patch('urllib.request.urlopen')
    def test_get_code(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "jsonrpc": "2.0", "result": "0x60806040", "id": 1
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = lambda s, *a: None
        mock_urlopen.return_value = mock_response

        client = EVMChainClient("https://example.com", 1)
        code = client.get_code("0x123")
        self.assertEqual(code, "0x60806040")

    def test_estimate_gas_fallback(self):
        client = EVMChainClient("https://invalid.example.com", 1, timeout=1)
        gas = client.estimate_gas("0x123", "0xdata")
        self.assertEqual(gas, 21000)


class TestWormholeAnchorContract(unittest.TestCase):
    """Test WormholeAnchorContract encoding methods."""

    def setUp(self):
        self.client = EVMChainClient("https://example.com", 1)
        self.contract = WormholeAnchorContract("0x" + "11" * 20, self.client)

    def test_encode_anchor_call(self):
        data = self.contract.encode_anchor_call(
            "a" * 64, 100000, "b" * 64, b"test_data"
        )
        self.assertTrue(data.startswith("0x"))
        self.assertGreater(len(data), 10)

    def test_encode_anchor_call_short_txid(self):
        data = self.contract.encode_anchor_call(
            "short_txid", 100000, "b" * 64, b"test_data"
        )
        self.assertTrue(data.startswith("0x"))

    def test_encode_mint_call(self):
        data = self.contract.encode_mint_call(
            "0x" + "22" * 20, 1000, "a" * 64
        )
        self.assertTrue(data.startswith("0x"))
        self.assertGreater(len(data), 10)

    def test_encode_mint_call_short_txid(self):
        data = self.contract.encode_mint_call(
            "0x" + "22" * 20, 1000, "short"
        )
        self.assertTrue(data.startswith("0x"))

    @patch('urllib.request.urlopen')
    def test_check_contract_deployed_true(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "jsonrpc": "2.0", "result": "0x6080", "id": 1
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = lambda s, *a: None
        mock_urlopen.return_value = mock_response

        self.assertTrue(self.contract.check_contract_deployed())

    @patch('urllib.request.urlopen')
    def test_check_contract_deployed_false(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "jsonrpc": "2.0", "result": "0x", "id": 1
        }).encode()
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = lambda s, *a: None
        mock_urlopen.return_value = mock_response

        self.assertFalse(self.contract.check_contract_deployed())

    def test_abi_defined(self):
        self.assertGreater(len(WormholeAnchorContract.ANCHOR_ABI), 0)


class TestWormholeLiveConnector(unittest.TestCase):
    """Test WormholeLiveConnector main class."""

    def test_init(self):
        connector = WormholeLiveConnector()
        self.assertEqual(len(connector.clients), 4)  # ETH, BSC, Arbitrum, Optimism
        self.assertEqual(len(connector.connectors), 4)
        self.assertEqual(len(connector.contracts), 4)

    def test_init_custom_contract(self):
        addr = "0x" + "aa" * 20
        connector = WormholeLiveConnector(addr)
        self.assertEqual(connector.anchor_contract_address, addr)

    def test_chain_ids(self):
        self.assertEqual(WormholeLiveConnector.CHAIN_IDS[WormholeChain.ETH], 1)
        self.assertEqual(WormholeLiveConnector.CHAIN_IDS[WormholeChain.BSC], 56)
        self.assertEqual(WormholeLiveConnector.CHAIN_IDS[WormholeChain.ARBITRUM], 42161)
        self.assertEqual(WormholeLiveConnector.CHAIN_IDS[WormholeChain.OPTIMISM], 10)

    def test_burn_addresses(self):
        self.assertGreater(len(WormholeLiveConnector.BURN_ADDRESSES), 0)

    def test_create_wormhole_proof(self):
        connector = WormholeLiveConnector()
        proof = connector.create_wormhole_proof(
            "abc123", "1BitcoinEaterAddressDontSendf59kuE", 100000
        )
        self.assertEqual(proof.burn_txid, "abc123")
        self.assertEqual(proof.burn_amount_sats, 100000)
        self.assertEqual(len(proof.wormhole_hash), 64)  # SHA-256 hex

    def test_proof_hash_deterministic(self):
        connector = WormholeLiveConnector()
        proof1 = connector.create_wormhole_proof("tx1", "addr1", 100)
        proof2 = connector.create_wormhole_proof("tx1", "addr1", 100)
        self.assertEqual(proof1.wormhole_hash, proof2.wormhole_hash)

    def test_proof_hash_different(self):
        connector = WormholeLiveConnector()
        proof1 = connector.create_wormhole_proof("tx1", "addr1", 100)
        proof2 = connector.create_wormhole_proof("tx2", "addr1", 100)
        self.assertNotEqual(proof1.wormhole_hash, proof2.wormhole_hash)

    def test_proof_anchor_data(self):
        connector = WormholeLiveConnector()
        proof = connector.create_wormhole_proof("tx1", "addr1", 100)
        data = json.loads(proof.anchor_data)
        self.assertEqual(data['txid'], "tx1")
        self.assertEqual(data['amount'], 100)
        self.assertEqual(data['chain'], 'bitcoin')

    def test_process_burn_no_chains(self):
        connector = WormholeLiveConnector()
        burn = {
            'txid': 'abc123',
            'address': '1BitcoinEaterAddressDontSendf59kuE',
            'amount_sats': 100000,
        }
        wormhole = connector.process_burn(burn)
        self.assertIsNotNone(wormhole)
        self.assertEqual(len(wormhole.wormhole_id), 16)
        self.assertIsNotNone(wormhole.proof)

    def test_process_burn_stores_wormhole(self):
        connector = WormholeLiveConnector()
        burn = {
            'txid': 'abc123',
            'address': '1BitcoinEaterAddressDontSendf59kuE',
            'amount_sats': 100000,
        }
        wormhole = connector.process_burn(burn)
        stored = connector.get_wormhole(wormhole.wormhole_id)
        self.assertEqual(stored, wormhole)

    def test_get_wormhole_not_found(self):
        connector = WormholeLiveConnector()
        result = connector.get_wormhole("nonexistent")
        self.assertIsNone(result)

    def test_get_all_wormholes(self):
        connector = WormholeLiveConnector()
        burn = {
            'txid': 'abc123',
            'address': '1BitcoinEaterAddressDontSendf59kuE',
            'amount_sats': 100000,
        }
        connector.process_burn(burn)
        all_wh = connector.get_all_wormholes()
        self.assertEqual(len(all_wh), 1)

    def test_verify_wormhole_not_found(self):
        connector = WormholeLiveConnector()
        result = connector.verify_wormhole("nonexistent")
        self.assertFalse(result)

    def test_verify_wormhole_no_anchors(self):
        connector = WormholeLiveConnector()
        burn = {
            'txid': 'abc123',
            'address': '1BitcoinEaterAddressDontSendf59kuE',
            'amount_sats': 100000,
        }
        wormhole = connector.process_burn(burn)
        # No anchors, so verification should fail
        result = connector.verify_wormhole(wormhole.wormhole_id)
        self.assertFalse(result)

    def test_get_chain_status(self):
        connector = WormholeLiveConnector()
        status = connector.get_chain_status()
        self.assertIn("ethereum", status)
        self.assertIn("bsc", status)
        self.assertIn("arbitrum", status)
        self.assertIn("optimism", status)

    def test_fetch_btc_burns_empty(self):
        connector = WormholeLiveConnector()
        # With invalid addresses, should return empty
        burns = connector.fetch_btc_burns(["1InvalidAddress"], limit=1)
        self.assertIsInstance(burns, list)

    def test_burn_txids_dedup(self):
        connector = WormholeLiveConnector()
        connector.burn_txids_seen.add("seen_tx")
        burns = connector.fetch_btc_burns(limit=1)
        for burn in burns:
            self.assertNotEqual(burn['txid'], "seen_tx")

    @patch.object(WormholeLiveConnector, 'fetch_btc_burns')
    def test_scan_and_process(self, mock_fetch):
        mock_fetch.return_value = [{
            'txid': 'abc123',
            'address': '1BitcoinEaterAddressDontSendf59kuE',
            'amount_sats': 100000,
        }]
        connector = WormholeLiveConnector()
        wormholes = connector.scan_and_process(limit=1)
        self.assertEqual(len(wormholes), 1)


class TestConnectAllChains(unittest.TestCase):
    """Test chain connection methods."""

    def test_connect_all_chains_returns_dict(self):
        connector = WormholeLiveConnector()
        results = connector.connect_all_chains()
        self.assertIsInstance(results, dict)
        self.assertEqual(len(results), 4)

    def test_connect_all_chains_updates_connectors(self):
        connector = WormholeLiveConnector()
        connector.connect_all_chains()
        for chain, conn in connector.connectors.items():
            self.assertIsInstance(conn.connected, bool)


class TestConvenienceFunctions(unittest.TestCase):
    """Test convenience functions."""

    def test_create_wormhole_proof_function(self):
        proof = create_wormhole_proof("tx1", "addr1", 100)
        self.assertIsInstance(proof, WormholeProof)
        self.assertEqual(proof.burn_txid, "tx1")

    def test_scan_btc_burns_function(self):
        burns = scan_btc_burns(limit=1)
        self.assertIsInstance(burns, list)

    def test_get_chain_connectors(self):
        connectors = get_chain_connectors()
        self.assertEqual(len(connectors), 4)
        for chain, conn in connectors.items():
            self.assertIsInstance(conn, ChainConnector)


if __name__ == '__main__':
    unittest.main()
