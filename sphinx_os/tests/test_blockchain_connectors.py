#!/usr/bin/env python3
"""Tests for blockchain connectors and on-chain bridge.

This module tests the real blockchain connectivity layer:
- Bitcoin connector via mempool.space API
- Ethereum connector via JSON-RPC
- EXCAL connector via local P2P
- Monero connector via daemon RPC
- Connector pool management
- On-chain bridge operations
"""

import json
import time
import unittest
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sphinx_os.nexus.blockchain_connectors import (
    NetworkType,
    TransactionStatus,
    BroadcastResult,
    BalanceResult,
    FeeEstimate,
    TransactionInfo,
    BlockchainConnector,
    BitcoinConnector,
    EthereumConnector,
    EXCALConnector,
    MoneroConnector,
    ConnectorPool,
    create_bitcoin_connector,
    create_ethereum_connector,
    create_excal_connector,
    create_monero_connector,
    create_multi_chain_pool,
)
from sphinx_os.nexus.on_chain_bridge import (
    BridgeStatus,
    BridgeOperation,
    BridgeTransaction,
    ProofAnchor,
    CollateralLock,
    FlashLoanExecution,
    ProofAnchoringService,
    CollateralLockService,
    FlashLoanExecutor,
    OnChainBridge,
    create_on_chain_bridge,
)


class TestNetworkType(unittest.TestCase):
    """Test network type enum."""

    def test_bitcoin_networks(self):
        """Test Bitcoin network types."""
        self.assertEqual(NetworkType.BTC_MAINNET.value, "bitcoin_mainnet")
        self.assertEqual(NetworkType.BTC_TESTNET.value, "bitcoin_testnet")
        self.assertEqual(NetworkType.BTC_SIGNET.value, "bitcoin_signet")

    def test_ethereum_networks(self):
        """Test Ethereum network types."""
        self.assertEqual(NetworkType.ETH_MAINNET.value, "ethereum_mainnet")
        self.assertEqual(NetworkType.ETH_SEPOLIA.value, "ethereum_sepolia")

    def test_excal_networks(self):
        """Test EXCAL network types."""
        self.assertEqual(NetworkType.EXCAL_MAINNET.value, "excal_mainnet")
        self.assertEqual(NetworkType.EXCAL_TESTNET.value, "excal_testnet")

    def test_monero_networks(self):
        """Test Monero network types."""
        self.assertEqual(NetworkType.XMR_MAINNET.value, "monero_mainnet")


class TestTransactionStatus(unittest.TestCase):
    """Test transaction status enum."""

    def test_statuses(self):
        """Test all transaction statuses."""
        self.assertEqual(TransactionStatus.PENDING.value, "pending")
        self.assertEqual(TransactionStatus.CONFIRMED.value, "confirmed")
        self.assertEqual(TransactionStatus.FAILED.value, "failed")


class TestDataStructures(unittest.TestCase):
    """Test data structure classes."""

    def test_broadcast_result(self):
        """Test BroadcastResult creation."""
        result = BroadcastResult(
            success=True,
            tx_id="abc123",
            network="bitcoin_mainnet"
        )
        self.assertTrue(result.success)
        self.assertEqual(result.tx_id, "abc123")
        self.assertEqual(result.network, "bitcoin_mainnet")
        self.assertEqual(result.confirmations, 0)
        self.assertIsInstance(result.timestamp, float)

    def test_broadcast_result_failure(self):
        """Test failed BroadcastResult."""
        result = BroadcastResult(
            success=False,
            error="Connection refused",
            network="ethereum_mainnet"
        )
        self.assertFalse(result.success)
        self.assertEqual(result.error, "Connection refused")

    def test_balance_result(self):
        """Test BalanceResult creation."""
        result = BalanceResult(
            address="1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
            confirmed_balance=5000000000,  # 50 BTC in sats
            unconfirmed_balance=0,
            total_received=5000000000,
            total_sent=0,
            tx_count=1,
            network="bitcoin_mainnet"
        )
        self.assertEqual(result.confirmed_balance, 5000000000)
        self.assertEqual(result.tx_count, 1)

    def test_fee_estimate(self):
        """Test FeeEstimate creation."""
        estimate = FeeEstimate(
            economy=1,
            standard=10,
            priority=5,
            unit="sats/vB",
            network="bitcoin_mainnet"
        )
        self.assertEqual(estimate.economy, 1)
        self.assertEqual(estimate.standard, 10)
        self.assertEqual(estimate.unit, "sats/vB")

    def test_transaction_info(self):
        """Test TransactionInfo creation."""
        info = TransactionInfo(
            tx_id="abc123",
            status=TransactionStatus.CONFIRMED,
            block_height=800000,
            confirmations=6,
            fee=1000,
            network="bitcoin_mainnet"
        )
        self.assertEqual(info.block_height, 800000)
        self.assertEqual(info.confirmations, 6)


class TestBitcoinConnector(unittest.TestCase):
    """Test Bitcoin connector."""

    def test_init_mainnet(self):
        """Test Bitcoin connector initialization for mainnet."""
        connector = BitcoinConnector(NetworkType.BTC_MAINNET)
        self.assertEqual(connector.base_url, "https://mempool.space/api")
        self.assertFalse(connector.is_connected())

    def test_init_testnet(self):
        """Test Bitcoin connector initialization for testnet."""
        connector = BitcoinConnector(NetworkType.BTC_TESTNET)
        self.assertEqual(connector.base_url, "https://mempool.space/testnet/api")

    def test_init_signet(self):
        """Test Bitcoin connector initialization for signet."""
        connector = BitcoinConnector(NetworkType.BTC_SIGNET)
        self.assertEqual(connector.base_url, "https://mempool.space/signet/api")

    @patch('urllib.request.urlopen')
    def test_connect_success(self, mock_urlopen):
        """Test successful connection."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"height": 800000}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        connector = BitcoinConnector()
        result = connector.connect()
        self.assertTrue(result)
        self.assertTrue(connector.is_connected())

    @patch('urllib.request.urlopen')
    def test_connect_failure(self, mock_urlopen):
        """Test connection failure."""
        mock_urlopen.side_effect = Exception("Connection refused")

        connector = BitcoinConnector()
        result = connector.connect()
        self.assertFalse(result)
        self.assertFalse(connector.is_connected())

    def test_disconnect(self):
        """Test disconnect."""
        connector = BitcoinConnector()
        connector._connected = True
        connector.disconnect()
        self.assertFalse(connector.is_connected())

    @patch('urllib.request.urlopen')
    def test_get_balance(self, mock_urlopen):
        """Test balance query."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "chainStats": {
                "fundedTxoSum": 5000000000,
                "spentTxSum": 0,
                "txCount": 1
            },
            "mempoolStats": {
                "fundedTxoSum": 0,
                "spentTxSum": 0
            }
        }).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        connector = BitcoinConnector()
        result = connector.get_balance("1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa")
        self.assertEqual(result.confirmed_balance, 5000000000)
        self.assertEqual(result.tx_count, 1)

    @patch('urllib.request.urlopen')
    def test_get_block_height(self, mock_urlopen):
        """Test block height query."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"height": 800000}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        connector = BitcoinConnector()
        height = connector.get_block_height()
        self.assertEqual(height, 800000)

    @patch('urllib.request.urlopen')
    def test_estimate_fee(self, mock_urlopen):
        """Test fee estimation."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({
            "minimumFee": 1,
            "fastestFee": 20,
            "halfHourFee": 10
        }).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        connector = BitcoinConnector()
        fees = connector.estimate_fee()
        self.assertEqual(fees.economy, 1)
        self.assertEqual(fees.standard, 20)
        self.assertEqual(fees.unit, "sats/vB")


class TestEthereumConnector(unittest.TestCase):
    """Test Ethereum connector."""

    def test_init_mainnet(self):
        """Test Ethereum connector initialization."""
        connector = EthereumConnector(NetworkType.ETH_MAINNET)
        self.assertTrue(connector.rpc_url.startswith("https://"))
        self.assertFalse(connector.is_connected())

    @patch.object(EthereumConnector, '_http_post')
    def test_connect_success(self, mock_post):
        """Test successful connection."""
        mock_post.return_value = {"result": "0x0b0d00"}

        connector = EthereumConnector()
        result = connector.connect()
        self.assertTrue(result)
        self.assertTrue(connector.is_connected())

    @patch.object(EthereumConnector, '_http_post')
    def test_get_balance(self, mock_post):
        """Test balance query."""
        mock_post.return_value = {"result": "0x1bc16d674ec80000"}  # 2 ETH in wei

        connector = EthereumConnector()
        result = connector.get_balance("0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb")
        self.assertGreater(result.confirmed_balance, 0)

    @patch.object(EthereumConnector, '_http_post')
    def test_broadcast_transaction(self, mock_post):
        """Test transaction broadcast."""
        mock_post.return_value = {"result": "0xabc123"}

        connector = EthereumConnector()
        result = connector.broadcast_transaction("0x02f8...")
        self.assertTrue(result.success)
        self.assertEqual(result.tx_id, "0xabc123")

    @patch.object(EthereumConnector, '_http_post')
    def test_get_block_height(self, mock_post):
        """Test block height query."""
        mock_post.return_value = {"result": "0x0b0d00"}  # 724224

        connector = EthereumConnector()
        height = connector.get_block_height()
        self.assertEqual(height, 724224)


class TestEXCALConnector(unittest.TestCase):
    """Test EXCAL connector."""

    def test_init(self):
        """Test EXCAL connector initialization."""
        connector = EXCALConnector()
        self.assertEqual(connector.node_host, "127.0.0.1")
        self.assertEqual(connector.node_port, 8333)
        self.assertFalse(connector.is_connected())

    @patch('urllib.request.urlopen')
    def test_connect_success(self, mock_urlopen):
        """Test successful connection."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"height": 100}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        connector = EXCALConnector()
        result = connector.connect()
        self.assertTrue(result)

    @patch('urllib.request.urlopen')
    def test_connect_failure(self, mock_urlopen):
        """Test connection failure (no node running)."""
        mock_urlopen.side_effect = Exception("Connection refused")

        connector = EXCALConnector()
        result = connector.connect()
        self.assertFalse(result)


class TestMoneroConnector(unittest.TestCase):
    """Test Monero connector."""

    def test_init(self):
        """Test Monero connector initialization."""
        connector = MoneroConnector()
        self.assertEqual(connector.daemon_host, "127.0.0.1")
        self.assertEqual(connector.daemon_port, 18081)


class TestConnectorPool(unittest.TestCase):
    """Test connector pool."""

    def test_add_connector(self):
        """Test adding connector to pool."""
        pool = ConnectorPool()
        connector = BitcoinConnector()
        pool.add_connector(connector)
        self.assertIn(NetworkType.BTC_MAINNET.value, pool.connectors)

    def test_get_connector(self):
        """Test getting connector from pool."""
        pool = ConnectorPool()
        connector = BitcoinConnector()
        pool.add_connector(connector)

        retrieved = pool.get_connector(NetworkType.BTC_MAINNET)
        self.assertEqual(retrieved, connector)

    def test_get_missing_connector(self):
        """Test getting missing connector."""
        pool = ConnectorPool()
        retrieved = pool.get_connector(NetworkType.ETH_MAINNET)
        self.assertIsNone(retrieved)

    def test_disconnect_all(self):
        """Test disconnecting all connectors."""
        pool = ConnectorPool()
        btc = BitcoinConnector()
        btc._connected = True
        pool.add_connector(btc)

        pool.disconnect_all()
        self.assertFalse(btc.is_connected())


class TestConvenienceFunctions(unittest.TestCase):
    """Test convenience factory functions."""

    @patch('urllib.request.urlopen')
    def test_create_bitcoin_connector(self, mock_urlopen):
        """Test Bitcoin connector factory."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"height": 800000}).encode()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        connector = create_bitcoin_connector()
        self.assertIsInstance(connector, BitcoinConnector)
        self.assertTrue(connector.is_connected())

    @patch.object(EthereumConnector, '_http_post')
    def test_create_ethereum_connector(self, mock_post):
        """Test Ethereum connector factory."""
        mock_post.return_value = {"result": "0x0b0d00"}

        connector = create_ethereum_connector()
        self.assertIsInstance(connector, EthereumConnector)
        self.assertTrue(connector.is_connected())


class TestBridgeStatus(unittest.TestCase):
    """Test bridge status enum."""

    def test_statuses(self):
        """Test all bridge statuses."""
        self.assertEqual(BridgeStatus.PENDING.value, "pending")
        self.assertEqual(BridgeStatus.CONFIRMED.value, "confirmed")
        self.assertEqual(BridgeStatus.FAILED.value, "failed")


class TestBridgeOperation(unittest.TestCase):
    """Test bridge operation enum."""

    def test_operations(self):
        """Test all bridge operations."""
        self.assertEqual(BridgeOperation.PROOF_ANCHOR.value, "proof_anchor")
        self.assertEqual(BridgeOperation.COLLATERAL_LOCK.value, "collateral_lock")
        self.assertEqual(BridgeOperation.FLASH_LOAN.value, "flash_loan")


class TestBridgeDataStructures(unittest.TestCase):
    """Test bridge data structures."""

    def test_bridge_transaction(self):
        """Test BridgeTransaction creation."""
        tx = BridgeTransaction(
            bridge_id="bridge123",
            operation=BridgeOperation.PROOF_ANCHOR,
            simulation_id="sim123",
            network="bitcoin_mainnet"
        )
        self.assertEqual(tx.bridge_id, "bridge123")
        self.assertEqual(tx.status, BridgeStatus.PENDING)
        self.assertIsInstance(tx.created_at, float)

    def test_proof_anchor(self):
        """Test ProofAnchor creation."""
        anchor = ProofAnchor(
            proof_id="proof123",
            anchor_tx_id="tx123",
            anchor_block=800000,
            proof_hash="abc123",
            network="bitcoin_mainnet"
        )
        self.assertEqual(anchor.proof_id, "proof123")
        self.assertEqual(anchor.anchor_block, 800000)

    def test_collateral_lock(self):
        """Test CollateralLock creation."""
        lock = CollateralLock(
            lock_id="lock123",
            tx_id="tx123",
            amount=1.0,
            asset="BTC",
            lock_script="3J98t1WpEZ73CNmQviecrnyiWrnqRhWNLy",
            unlock_condition="loan_repayment",
            network="bitcoin_mainnet"
        )
        self.assertEqual(lock.amount, 1.0)
        self.assertEqual(lock.asset, "BTC")

    def test_flash_loan_execution(self):
        """Test FlashLoanExecution creation."""
        execution = FlashLoanExecution(
            execution_id="exec123",
            loan_tx_id="tx123",
            repay_tx_id="tx456",
            amount=100.0,
            fee=0.09,
            asset="0x...",
            network="ethereum_mainnet",
            success=True
        )
        self.assertEqual(execution.amount, 100.0)
        self.assertTrue(execution.success)


class TestProofAnchoringService(unittest.TestCase):
    """Test proof anchoring service."""

    def test_init(self):
        """Test service initialization."""
        connector = BitcoinConnector()
        service = ProofAnchoringService(connector)
        self.assertEqual(service.btc_connector, connector)
        self.assertEqual(len(service._anchors), 0)

    def test_get_missing_anchor(self):
        """Test getting missing anchor."""
        connector = BitcoinConnector()
        service = ProofAnchoringService(connector)
        anchor = service.get_anchor("nonexistent")
        self.assertIsNone(anchor)

    def test_verify_missing_anchor(self):
        """Test verifying missing anchor."""
        connector = BitcoinConnector()
        service = ProofAnchoringService(connector)
        result = service.verify_anchor("nonexistent", {"data": "test"})
        self.assertFalse(result)


class TestCollateralLockService(unittest.TestCase):
    """Test collateral lock service."""

    def test_init(self):
        """Test service initialization."""
        connector = BitcoinConnector()
        service = CollateralLockService(connector)
        self.assertEqual(service.btc_connector, connector)
        self.assertEqual(len(service._locks), 0)

    def test_get_missing_lock(self):
        """Test getting missing lock."""
        connector = BitcoinConnector()
        service = CollateralLockService(connector)
        lock = service.get_lock("nonexistent")
        self.assertIsNone(lock)

    def test_get_locked_balance_empty(self):
        """Test locked balance when empty."""
        connector = BitcoinConnector()
        service = CollateralLockService(connector)
        balance = service.get_locked_balance()
        self.assertEqual(balance, 0.0)


class TestFlashLoanExecutor(unittest.TestCase):
    """Test flash loan executor."""

    def test_init(self):
        """Test executor initialization."""
        connector = EthereumConnector()
        executor = FlashLoanExecutor(connector)
        self.assertEqual(executor.eth_connector, connector)
        self.assertEqual(len(executor._executions), 0)

    def test_get_missing_execution(self):
        """Test getting missing execution."""
        connector = EthereumConnector()
        executor = FlashLoanExecutor(connector)
        execution = executor.get_execution("nonexistent")
        self.assertIsNone(execution)


class TestOnChainBridge(unittest.TestCase):
    """Test on-chain bridge."""

    def test_create_bridge_transaction(self):
        """Test creating bridge transaction."""
        pool = ConnectorPool()
        pool.add_connector(BitcoinConnector())
        pool.add_connector(EthereumConnector())

        bridge = OnChainBridge(pool)
        tx = bridge.create_bridge_transaction(
            BridgeOperation.PROOF_ANCHOR,
            "sim123",
            {"data": "test"},
            "bitcoin_mainnet"
        )
        self.assertIsNotNone(tx.bridge_id)
        self.assertEqual(tx.operation, BridgeOperation.PROOF_ANCHOR)
        self.assertEqual(tx.status, BridgeStatus.PENDING)

    def test_get_missing_transaction(self):
        """Test getting missing transaction."""
        pool = ConnectorPool()
        pool.add_connector(BitcoinConnector())
        pool.add_connector(EthereumConnector())

        bridge = OnChainBridge(pool)
        tx = bridge.get_transaction("nonexistent")
        self.assertIsNone(tx)

    def test_get_all_transactions_empty(self):
        """Test getting all transactions when empty."""
        pool = ConnectorPool()
        pool.add_connector(BitcoinConnector())
        pool.add_connector(EthereumConnector())

        bridge = OnChainBridge(pool)
        txs = bridge.get_all_transactions()
        self.assertEqual(len(txs), 0)

    def test_get_all_transactions(self):
        """Test getting all transactions."""
        pool = ConnectorPool()
        pool.add_connector(BitcoinConnector())
        pool.add_connector(EthereumConnector())

        bridge = OnChainBridge(pool)
        bridge.create_bridge_transaction(
            BridgeOperation.PROOF_ANCHOR,
            "sim1",
            {},
            "bitcoin_mainnet"
        )
        bridge.create_bridge_transaction(
            BridgeOperation.FLASH_LOAN,
            "sim2",
            {},
            "ethereum_mainnet"
        )

        txs = bridge.get_all_transactions()
        self.assertEqual(len(txs), 2)


if __name__ == '__main__':
    unittest.main()
