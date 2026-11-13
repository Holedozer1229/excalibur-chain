"""Tests for the zkSync Bridge module."""

import unittest
import time
from sphinx_os.nexus.zksync_bridge import (
    ZkSyncBridge,
    BridgeTransaction,
    BridgeStatus,
    BridgeDirection,
    BridgePool,
    BridgeState,
)


class TestZkSyncBridgeInit(unittest.TestCase):
    """Test bridge initialization."""
    
    def test_default_parameters(self):
        """Bridge should initialize with default parameters."""
        bridge = ZkSyncBridge()
        
        self.assertEqual(bridge.bridge_fee_rate, 0.001)
        self.assertEqual(bridge.required_confirmations, 12)
        self.assertEqual(bridge.min_deposit, 1.0)
        self.assertEqual(bridge.max_deposit, 100000.0)
    
    def test_custom_parameters(self):
        """Bridge should accept custom parameters."""
        bridge = ZkSyncBridge(
            bridge_fee_rate=0.002,
            required_confirmations=6,
            min_deposit=0.5,
            max_deposit=50000.0,
        )
        
        self.assertEqual(bridge.bridge_fee_rate, 0.002)
        self.assertEqual(bridge.required_confirmations, 6)
        self.assertEqual(bridge.min_deposit, 0.5)
        self.assertEqual(bridge.max_deposit, 50000.0)
    
    def test_initial_pools(self):
        """Bridge should initialize with 4 pools."""
        bridge = ZkSyncBridge()
        
        self.assertEqual(len(bridge.pools), 4)
        self.assertIn("EXCAL_EXCAL", bridge.pools)
        self.assertIn("wEXCAL_zkSync", bridge.pools)
        self.assertIn("URUU_EXCAL", bridge.pools)
        self.assertIn("URUU_zkSync", bridge.pools)
    
    def test_initial_state(self):
        """Bridge should start with zero volume and transactions."""
        bridge = ZkSyncBridge()
        
        self.assertEqual(bridge.total_volume, 0.0)
        self.assertEqual(bridge.total_transactions, 0)
        self.assertEqual(len(bridge.transactions), 0)


class TestZkSyncBridgeDeposit(unittest.TestCase):
    """Test deposit operations (EXCAL -> zkSync)."""
    
    def test_initiate_deposit(self):
        """Should be able to initiate a deposit."""
        bridge = ZkSyncBridge()
        tx = bridge.initiate_deposit(
            token_symbol="EXCAL",
            amount=100.0,
            sender_address="A1B2C3D4E5F6A7B8C9D0",
            receiver_address="0x1234567890ABCDEF",
        )
        
        self.assertIsInstance(tx, BridgeTransaction)
        self.assertEqual(tx.direction, BridgeDirection.EXCAL_TO_ZKSYNC)
        self.assertEqual(tx.token_symbol, "EXCAL")
        self.assertEqual(tx.amount, 100.0)
        self.assertEqual(tx.status, BridgeStatus.PENDING)
    
    def test_deposit_fee_calculated(self):
        """Deposit should calculate fee."""
        bridge = ZkSyncBridge(bridge_fee_rate=0.001)
        tx = bridge.initiate_deposit(
            token_symbol="EXCAL",
            amount=100.0,
            sender_address="A1B2C3D4E5F6A7B8C9D0",
            receiver_address="0x1234567890ABCDEF",
        )
        
        expected_fee = 100.0 * 0.001
        self.assertAlmostEqual(tx.fee, expected_fee)
    
    def test_deposit_raises_on_min_amount(self):
        """Deposit below minimum should raise ValueError."""
        bridge = ZkSyncBridge(min_deposit=1.0)
        with self.assertRaises(ValueError):
            bridge.initiate_deposit(
                token_symbol="EXCAL",
                amount=0.5,
                sender_address="A1B2C3D4E5F6A7B8C9D0",
                receiver_address="0x1234567890ABCDEF",
            )
    
    def test_deposit_raises_on_max_amount(self):
        """Deposit above maximum should raise ValueError."""
        bridge = ZkSyncBridge(max_deposit=100.0)
        with self.assertRaises(ValueError):
            bridge.initiate_deposit(
                token_symbol="EXCAL",
                amount=200.0,
                sender_address="A1B2C3D4E5F6A7B8C9D0",
                receiver_address="0x1234567890ABCDEF",
            )
    
    def test_deposit_locks_tokens(self):
        """Deposit should lock tokens in source pool."""
        bridge = ZkSyncBridge()
        bridge.pools["EXCAL_EXCAL"].balance = 1000.0
        
        bridge.initiate_deposit(
            token_symbol="EXCAL",
            amount=100.0,
            sender_address="A1B2C3D4E5F6A7B8C9D0",
            receiver_address="0x1234567890ABCDEF",
        )
        
        self.assertEqual(bridge.pools["EXCAL_EXCAL"].locked, 100.0)
    
    def test_multiple_deposits(self):
        """Should support multiple deposits."""
        bridge = ZkSyncBridge()
        
        tx1 = bridge.initiate_deposit("EXCAL", 100.0, "ADDR1", "ADDR2")
        tx2 = bridge.initiate_deposit("URUU", 200.0, "ADDR3", "ADDR4")
        
        self.assertEqual(len(bridge.transactions), 2)
        self.assertNotEqual(tx1.tx_id, tx2.tx_id)


class TestZkSyncBridgeWithdrawal(unittest.TestCase):
    """Test withdrawal operations (zkSync -> EXCAL)."""
    
    def test_initiate_withdrawal(self):
        """Should be able to initiate a withdrawal."""
        bridge = ZkSyncBridge()
        bridge.pools["URUU_zkSync"].balance = 1000.0
        
        tx = bridge.initiate_withdrawal(
            token_symbol="URUU",
            amount=100.0,
            sender_address="0x1234567890ABCDEF",
            receiver_address="A1B2C3D4E5F6A7B8C9D0",
        )
        
        self.assertIsInstance(tx, BridgeTransaction)
        self.assertEqual(tx.direction, BridgeDirection.ZKSYNC_TO_EXCAL)
        self.assertEqual(tx.token_symbol, "URUU")
        self.assertEqual(tx.status, BridgeStatus.PENDING)
    
    def test_withdrawal_raises_on_min_amount(self):
        """Withdrawal below minimum should raise ValueError."""
        bridge = ZkSyncBridge(min_deposit=1.0)
        with self.assertRaises(ValueError):
            bridge.initiate_withdrawal(
                token_symbol="URUU",
                amount=0.5,
                sender_address="0x1234567890ABCDEF",
                receiver_address="A1B2C3D4E5F6A7B8C9D0",
            )


class TestZkSyncBridgeConfirmation(unittest.TestCase):
    """Test transaction confirmation."""
    
    def test_confirm_transaction(self):
        """Should be able to add confirmations."""
        bridge = ZkSyncBridge(required_confirmations=6)
        tx = bridge.initiate_deposit(
            "EXCAL", 100.0, "ADDR1", "ADDR2"
        )
        
        bridge.confirm_transaction(tx.tx_id, 3)
        
        self.assertEqual(bridge.transactions[tx.tx_id].confirmations, 3)
        self.assertEqual(bridge.transactions[tx.tx_id].status, BridgeStatus.CONFIRMING)
    
    def test_confirm_completes_transaction(self):
        """Sufficient confirmations should complete transaction."""
        bridge = ZkSyncBridge(required_confirmations=6)
        tx = bridge.initiate_deposit(
            "EXCAL", 100.0, "ADDR1", "ADDR2"
        )
        
        bridge.confirm_transaction(tx.tx_id, 6)
        
        self.assertEqual(bridge.transactions[tx.tx_id].status, BridgeStatus.COMPLETED)
        self.assertIsNotNone(bridge.transactions[tx.tx_id].proof)
    
    def test_confirm_raises_on_unknown_tx(self):
        """Confirming unknown transaction should raise ValueError."""
        bridge = ZkSyncBridge()
        with self.assertRaises(ValueError):
            bridge.confirm_transaction("unknown_tx", 1)
    
    def test_confirm_with_hash(self):
        """Should store transaction hash."""
        bridge = ZkSyncBridge()
        tx = bridge.initiate_deposit("EXCAL", 100.0, "ADDR1", "ADDR2")
        
        bridge.confirm_transaction(tx.tx_id, 1, "0xabcd1234")
        
        self.assertEqual(bridge.transactions[tx.tx_id].destination_tx_hash, "0xabcd1234")


class TestZkSyncBridgeProof(unittest.TestCase):
    """Test bridge proof generation."""
    
    def test_proof_is_generated(self):
        """Completed transaction should have proof."""
        bridge = ZkSyncBridge(required_confirmations=1)
        tx = bridge.initiate_deposit("EXCAL", 100.0, "ADDR1", "ADDR2")
        bridge.confirm_transaction(tx.tx_id, 1)
        
        tx = bridge.transactions[tx.tx_id]
        self.assertIsNotNone(tx.proof)
        self.assertTrue(tx.proof.startswith("0x"))
    
    def test_proof_is_unique(self):
        """Different transactions should have different proofs."""
        bridge = ZkSyncBridge(required_confirmations=1)
        
        tx1 = bridge.initiate_deposit("EXCAL", 100.0, "ADDR1", "ADDR2")
        bridge.confirm_transaction(tx1.tx_id, 1)
        
        tx2 = bridge.initiate_deposit("EXCAL", 200.0, "ADDR3", "ADDR4")
        bridge.confirm_transaction(tx2.tx_id, 1)
        
        self.assertNotEqual(
            bridge.transactions[tx1.tx_id].proof,
            bridge.transactions[tx2.tx_id].proof,
        )


class TestZkSyncBridgeState(unittest.TestCase):
    """Test bridge state retrieval."""
    
    def test_get_state(self):
        """Should return BridgeState."""
        bridge = ZkSyncBridge()
        state = bridge.get_state()
        
        self.assertIsInstance(state, BridgeState)
        self.assertEqual(state.total_volume, 0.0)
        self.assertEqual(state.total_transactions, 0)
        self.assertEqual(state.pending_transactions, 0)
    
    def test_state_reflects_completed_tx(self):
        """State should reflect completed transactions."""
        bridge = ZkSyncBridge(required_confirmations=1)
        tx = bridge.initiate_deposit("EXCAL", 100.0, "ADDR1", "ADDR2")
        bridge.confirm_transaction(tx.tx_id, 1)
        
        state = bridge.get_state()
        self.assertEqual(state.total_transactions, 1)
        self.assertEqual(state.total_volume, 100.0)
        self.assertEqual(state.pending_transactions, 0)
    
    def test_health_score_initial(self):
        """Initial health score should be 1.0."""
        bridge = ZkSyncBridge()
        state = bridge.get_state()
        
        self.assertEqual(state.health_score, 1.0)


class TestZkSyncBridgePool(unittest.TestCase):
    """Test bridge pool operations."""
    
    def test_get_pool_balance(self):
        """Should return pool balance."""
        bridge = ZkSyncBridge()
        bridge.add_liquidity("EXCAL", "EXCAL", 1000.0)
        
        balance = bridge.get_pool_balance("EXCAL", "EXCAL")
        self.assertEqual(balance, 1000.0)
    
    def test_add_liquidity(self):
        """Should be able to add liquidity."""
        bridge = ZkSyncBridge()
        bridge.add_liquidity("URUU", "zkSync", 500.0)
        
        self.assertEqual(bridge.pools["URUU_zkSync"].balance, 500.0)
    
    def test_remove_liquidity(self):
        """Should be able to remove liquidity."""
        bridge = ZkSyncBridge()
        bridge.add_liquidity("EXCAL", "EXCAL", 1000.0)
        
        result = bridge.remove_liquidity("EXCAL", "EXCAL", 300.0)
        
        self.assertTrue(result)
        self.assertEqual(bridge.pools["EXCAL_EXCAL"].balance, 700.0)
    
    def test_remove_liquidity_insufficient(self):
        """Removing more than balance should fail."""
        bridge = ZkSyncBridge()
        bridge.add_liquidity("EXCAL", "EXCAL", 100.0)
        
        result = bridge.remove_liquidity("EXCAL", "EXCAL", 200.0)
        
        self.assertFalse(result)
        self.assertEqual(bridge.pools["EXCAL_EXCAL"].balance, 100.0)


class TestZkSyncBridgePending(unittest.TestCase):
    """Test pending transaction retrieval."""
    
    def test_pending_transactions(self):
        """Should return pending transactions."""
        bridge = ZkSyncBridge()
        bridge.initiate_deposit("EXCAL", 100.0, "ADDR1", "ADDR2")
        bridge.initiate_deposit("URUU", 200.0, "ADDR3", "ADDR4")
        
        pending = bridge.get_pending_transactions()
        self.assertEqual(len(pending), 2)
    
    def test_completed_not_pending(self):
        """Completed transactions should not be pending."""
        bridge = ZkSyncBridge(required_confirmations=1)
        tx = bridge.initiate_deposit("EXCAL", 100.0, "ADDR1", "ADDR2")
        bridge.confirm_transaction(tx.tx_id, 1)
        
        pending = bridge.get_pending_transactions()
        self.assertEqual(len(pending), 0)


class TestZkSyncBridgeFee(unittest.TestCase):
    """Test bridge fee calculation."""
    
    def test_get_bridge_fee(self):
        """Should calculate fee correctly."""
        bridge = ZkSyncBridge(bridge_fee_rate=0.001)
        
        fee = bridge.get_bridge_fee(1000.0)
        self.assertEqual(fee, 1.0)
    
    def test_custom_fee_rate(self):
        """Custom fee rate should be used."""
        bridge = ZkSyncBridge(bridge_fee_rate=0.005)
        
        fee = bridge.get_bridge_fee(1000.0)
        self.assertEqual(fee, 5.0)


class TestZkSyncBridgeCallback(unittest.TestCase):
    """Test bridge completion callback."""
    
    def test_callback_on_complete(self):
        """Callback should be called on completion."""
        bridge = ZkSyncBridge(required_confirmations=1)
        callback_called = []
        
        def on_complete(tx):
            callback_called.append(tx)
        
        bridge.on_bridge_complete = on_complete
        
        tx = bridge.initiate_deposit("EXCAL", 100.0, "ADDR1", "ADDR2")
        bridge.confirm_transaction(tx.tx_id, 1)
        
        self.assertEqual(len(callback_called), 1)
        self.assertEqual(callback_called[0].tx_id, tx.tx_id)


if __name__ == "__main__":
    unittest.main()
