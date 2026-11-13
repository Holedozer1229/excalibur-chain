"""zkSync Era Bridge for EXCAL-URUU Cross-Chain Integration.

Provides bridge functionality between EXCAL blockchain and zkSync Era for:
- Depositing EXCAL from EXCAL chain to zkSync Era as wrapped EXCAL (wEXCAL)
- Withdrawing wEXCAL from zkSync Era back to EXCAL chain
- Bridging URUU tokens between chains
- Monitoring bridge liquidity and health
- Generating bridge proofs for zkSync Era verification

The bridge uses a lock-and-mint mechanism:
1. Deposit: Lock tokens on source chain, mint wrapped tokens on destination
2. Withdraw: Burn wrapped tokens on source, unlock original tokens on destination

Integration with SphinxOS Nexus:
- Bridge transactions are recorded in the conscious consensus engine
- Bridge fees are collected by the self-organizing treasury
- Bridge health metrics influence Nexus coherence
"""

import time
import hashlib
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum


class BridgeStatus(Enum):
    """Status of a bridge transaction."""
    PENDING = "pending"
    CONFIRMING = "confirming"
    COMPLETED = "completed"
    FAILED = "failed"
    REVERTED = "reverted"


class BridgeDirection(Enum):
    """Direction of bridge transfer."""
    EXCAL_TO_ZKSYNC = "excal_to_zksync"
    ZKSYNC_TO_EXCAL = "zksync_to_excal"


@dataclass
class BridgeTransaction:
    """Record of a bridge transaction."""
    tx_id: str
    timestamp: float
    direction: BridgeDirection
    token_symbol: str  # 'EXCAL', 'URUU', 'wEXCAL'
    amount: float
    sender_address: str
    receiver_address: str
    status: BridgeStatus
    source_tx_hash: Optional[str] = None
    destination_tx_hash: Optional[str] = None
    proof: Optional[str] = None
    fee: float = 0.0
    confirmations: int = 0
    required_confirmations: int = 12


@dataclass
class BridgePool:
    """Liquidity pool for a token on a specific chain."""
    token_symbol: str
    chain: str  # 'EXCAL' or 'zkSync'
    balance: float
    locked: float
    total_deposited: float
    total_withdrawn: float


@dataclass
class BridgeState:
    """Current state of the bridge."""
    total_volume: float
    total_transactions: int
    pending_transactions: int
    pools: List[BridgePool]
    health_score: float  # 0-1, higher is healthier
    average_confirmation_time: float  # seconds


class ZkSyncBridge:
    """Bridge between EXCAL blockchain and zkSync Era.
    
    Manages cross-chain token transfers using lock-and-mint mechanism.
    Integrates with SphinxOS Nexus for consensus and treasury management.
    """
    
    def __init__(
        self,
        bridge_fee_rate: float = 0.001,  # 0.1% bridge fee
        required_confirmations: int = 12,
        min_deposit: float = 1.0,
        max_deposit: float = 100000.0,
        zksync_rpc_url: str = "https://mainnet.era.zksync.io",
        excal_chain_id: int = 1,
        zksync_chain_id: int = 324,
    ):
        # Bridge parameters
        self.bridge_fee_rate = bridge_fee_rate
        self.required_confirmations = required_confirmations
        self.min_deposit = min_deposit
        self.max_deposit = max_deposit
        
        # Chain configuration
        self.zksync_rpc_url = zksync_rpc_url
        self.excal_chain_id = excal_chain_id
        self.zksync_chain_id = zksync_chain_id
        
        # Liquidity pools
        self.pools: Dict[str, BridgePool] = {
            "EXCAL_EXCAL": BridgePool("EXCAL", "EXCAL", 0, 0, 0, 0),
            "wEXCAL_zkSync": BridgePool("wEXCAL", "zkSync", 0, 0, 0, 0),
            "URUU_EXCAL": BridgePool("URUU", "EXCAL", 0, 0, 0, 0),
            "URUU_zkSync": BridgePool("URUU", "zkSync", 0, 0, 0, 0),
        }
        
        # Transaction tracking
        self.transactions: Dict[str, BridgeTransaction] = {}
        self.total_volume = 0.0
        self.total_transactions = 0
        self.start_time = time.time()
        
        # Health metrics
        self.success_rate = 1.0
        self.average_confirmation_time = 600.0  # 10 minutes default
        
        # Nexus integration callbacks
        self.on_bridge_complete = None  # Callback for completed bridges
    
    def _generate_tx_id(self, token_symbol: str, amount: float, sender_address: str) -> str:
        """Generate a unique transaction ID.
        
        Args:
            token_symbol: Token symbol.
            amount: Transaction amount.
            sender_address: Sender address.
            
        Returns:
            Unique transaction ID string.
        """
        import random
        data = f"{token_symbol}:{amount}:{sender_address}:{time.time()}:{random.randint(0, 999999)}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]
    
    def initiate_deposit(
        self,
        token_symbol: str,
        amount: float,
        sender_address: str,
        receiver_address: str,
        source_chain: str = "EXCAL",
    ) -> BridgeTransaction:
        """Initiate a deposit from EXCAL to zkSync Era.
        
        Args:
            token_symbol: Token to bridge (EXCAL or URUU).
            amount: Amount to bridge.
            sender_address: Sender address on source chain.
            receiver_address: Receiver address on destination chain.
            source_chain: Source chain (default: EXCAL).
            
        Returns:
            BridgeTransaction record.
        """
        # Validate amount
        if amount < self.min_deposit:
            raise ValueError(f"Minimum deposit is {self.min_deposit} {token_symbol}")
        if amount > self.max_deposit:
            raise ValueError(f"Maximum deposit is {self.max_deposit} {token_symbol}")
        
        # Calculate fee
        fee = amount * self.bridge_fee_rate
        
        # Generate transaction ID
        tx_id = self._generate_tx_id(token_symbol, amount, sender_address)
        
        # Create transaction record
        tx = BridgeTransaction(
            tx_id=tx_id,
            timestamp=time.time(),
            direction=BridgeDirection.EXCAL_TO_ZKSYNC,
            token_symbol=token_symbol,
            amount=amount,
            sender_address=sender_address,
            receiver_address=receiver_address,
            status=BridgeStatus.PENDING,
            fee=fee,
            required_confirmations=self.required_confirmations,
        )
        
        self.transactions[tx_id] = tx
        
        # Lock tokens in source pool
        pool_key = f"{token_symbol}_{source_chain}"
        if pool_key in self.pools:
            self.pools[pool_key].locked += amount
        
        return tx
    
    def initiate_withdrawal(
        self,
        token_symbol: str,
        amount: float,
        sender_address: str,
        receiver_address: str,
        source_chain: str = "zkSync",
    ) -> BridgeTransaction:
        """Initiate a withdrawal from zkSync Era to EXCAL.
        
        Args:
            token_symbol: Token to bridge (wEXCAL or URUU).
            amount: Amount to bridge.
            sender_address: Sender address on source chain.
            receiver_address: Receiver address on destination chain.
            source_chain: Source chain (default: zkSync).
            
        Returns:
            BridgeTransaction record.
        """
        # Validate amount
        if amount < self.min_deposit:
            raise ValueError(f"Minimum withdrawal is {self.min_deposit} {token_symbol}")
        if amount > self.max_deposit:
            raise ValueError(f"Maximum withdrawal is {self.max_deposit} {token_symbol}")
        
        # Calculate fee
        fee = amount * self.bridge_fee_rate
        
        # Generate transaction ID
        tx_id = self._generate_tx_id(token_symbol, amount, sender_address)
        
        # Create transaction record
        tx = BridgeTransaction(
            tx_id=tx_id,
            timestamp=time.time(),
            direction=BridgeDirection.ZKSYNC_TO_EXCAL,
            token_symbol=token_symbol,
            amount=amount,
            sender_address=sender_address,
            receiver_address=receiver_address,
            status=BridgeStatus.PENDING,
            fee=fee,
            required_confirmations=self.required_confirmations,
        )
        
        self.transactions[tx_id] = tx
        
        # Burn tokens in source pool
        pool_key = f"{token_symbol}_{source_chain}"
        if pool_key in self.pools:
            self.pools[pool_key].balance -= amount
            self.pools[pool_key].total_withdrawn += amount
        
        return tx
    
    def confirm_transaction(self, tx_id: str, confirmations: int, tx_hash: Optional[str] = None):
        """Add confirmations to a bridge transaction.
        
        Args:
            tx_id: Transaction ID to confirm.
            confirmations: Number of new confirmations.
            tx_hash: Optional transaction hash on destination chain.
        """
        if tx_id not in self.transactions:
            raise ValueError(f"Transaction {tx_id} not found")
        
        tx = self.transactions[tx_id]
        tx.confirmations += confirmations
        if tx_hash:
            tx.destination_tx_hash = tx_hash
        
        # Update status based on confirmations
        if tx.confirmations >= tx.required_confirmations:
            tx.status = BridgeStatus.COMPLETED
            self._complete_transaction(tx)
        elif tx.confirmations > 0:
            tx.status = BridgeStatus.CONFIRMING
    
    def _complete_transaction(self, tx: BridgeTransaction):
        """Complete a bridge transaction and update pools.
        
        Args:
            tx: Completed transaction.
        """
        # Update pools based on direction
        if tx.direction == BridgeDirection.EXCAL_TO_ZKSYNC:
            # Unlock from source, mint on destination
            source_pool_key = f"{tx.token_symbol}_EXCAL"
            dest_pool_key = f"{tx.token_symbol}_zkSync"
            
            if source_pool_key in self.pools:
                self.pools[source_pool_key].locked -= tx.amount
                self.pools[source_pool_key].total_deposited += tx.amount
            
            if dest_pool_key in self.pools:
                self.pools[dest_pool_key].balance += tx.amount
                self.pools[dest_pool_key].total_deposited += tx.amount
                
        else:  # ZKSYNC_TO_EXCAL
            # Burn on source, unlock on destination
            source_pool_key = f"{tx.token_symbol}_zkSync"
            dest_pool_key = f"{tx.token_symbol}_EXCAL"
            
            if source_pool_key in self.pools:
                self.pools[source_pool_key].total_withdrawn += tx.amount
            
            if dest_pool_key in self.pools:
                self.pools[dest_pool_key].balance += tx.amount
                self.pools[dest_pool_key].total_withdrawn += tx.amount
        
        # Update statistics
        self.total_volume += tx.amount
        self.total_transactions += 1
        
        # Generate proof
        tx.proof = self._generate_bridge_proof(tx)
        
        # Call callback if set
        if self.on_bridge_complete:
            self.on_bridge_complete(tx)
    
    def _generate_bridge_proof(self, tx: BridgeTransaction) -> str:
        """Generate a cryptographic proof for the bridge transaction.
        
        Args:
            tx: Bridge transaction.
            
        Returns:
            Hex-encoded proof string.
        """
        # Create proof data
        proof_data = {
            "tx_id": tx.tx_id,
            "amount": tx.amount,
            "token": tx.token_symbol,
            "sender": tx.sender_address,
            "receiver": tx.receiver_address,
            "direction": tx.direction.value,
            "timestamp": tx.timestamp,
            "source_chain": self.excal_chain_id if tx.direction == BridgeDirection.EXCAL_TO_ZKSYNC else self.zksync_chain_id,
            "dest_chain": self.zksync_chain_id if tx.direction == BridgeDirection.EXCAL_TO_ZKSYNC else self.excal_chain_id,
        }
        
        # Generate proof hash
        proof_json = json.dumps(proof_data, sort_keys=True)
        proof_hash = hashlib.sha256(proof_json.encode()).hexdigest()
        
        return f"0x{proof_hash}"
    
    def get_transaction(self, tx_id: str) -> Optional[BridgeTransaction]:
        """Get a bridge transaction by ID.
        
        Args:
            tx_id: Transaction ID.
            
        Returns:
            BridgeTransaction or None if not found.
        """
        return self.transactions.get(tx_id)
    
    def get_pending_transactions(self) -> List[BridgeTransaction]:
        """Get all pending bridge transactions.
        
        Returns:
            List of pending transactions.
        """
        return [
            tx for tx in self.transactions.values()
            if tx.status in (BridgeStatus.PENDING, BridgeStatus.CONFIRMING)
        ]
    
    def get_pool_balance(self, token_symbol: str, chain: str) -> float:
        """Get the balance of a token pool.
        
        Args:
            token_symbol: Token symbol.
            chain: Chain name ('EXCAL' or 'zkSync').
            
        Returns:
            Pool balance.
        """
        pool_key = f"{token_symbol}_{chain}"
        if pool_key in self.pools:
            return self.pools[pool_key].balance
        return 0.0
    
    def get_state(self) -> BridgeState:
        """Get current state of the bridge.
        
        Returns:
            BridgeState with current metrics.
        """
        pending = sum(
            1 for tx in self.transactions.values()
            if tx.status in (BridgeStatus.PENDING, BridgeStatus.CONFIRMING)
        )
        
        # Calculate health score based on success rate and liquidity
        completed = sum(
            1 for tx in self.transactions.values()
            if tx.status == BridgeStatus.COMPLETED
        )
        total = len(self.transactions)
        success_rate = completed / total if total > 0 else 1.0
        
        # Health is weighted average of success rate and liquidity adequacy
        liquidity_score = 1.0
        for pool in self.pools.values():
            if pool.total_deposited > 0 and pool.balance < pool.total_deposited * 0.1:
                liquidity_score *= 0.8  # Penalize low liquidity
        
        health_score = (success_rate * 0.7) + (liquidity_score * 0.3)
        
        return BridgeState(
            total_volume=self.total_volume,
            total_transactions=self.total_transactions,
            pending_transactions=pending,
            pools=list(self.pools.values()),
            health_score=health_score,
            average_confirmation_time=self.average_confirmation_time,
        )
    
    def get_bridge_fee(self, amount: float) -> float:
        """Calculate the bridge fee for a given amount.
        
        Args:
            amount: Transaction amount.
            
        Returns:
            Fee amount.
        """
        return amount * self.bridge_fee_rate
    
    def add_liquidity(self, token_symbol: str, chain: str, amount: float):
        """Add liquidity to a bridge pool.
        
        Args:
            token_symbol: Token symbol.
            chain: Chain name.
            amount: Amount to add.
        """
        pool_key = f"{token_symbol}_{chain}"
        if pool_key in self.pools:
            self.pools[pool_key].balance += amount
    
    def remove_liquidity(self, token_symbol: str, chain: str, amount: float) -> bool:
        """Remove liquidity from a bridge pool.
        
        Args:
            token_symbol: Token symbol.
            chain: Chain name.
            amount: Amount to remove.
            
        Returns:
            True if successful, False if insufficient balance.
        """
        pool_key = f"{token_symbol}_{chain}"
        if pool_key in self.pools:
            pool = self.pools[pool_key]
            if pool.balance >= amount:
                pool.balance -= amount
                return True
        return False
