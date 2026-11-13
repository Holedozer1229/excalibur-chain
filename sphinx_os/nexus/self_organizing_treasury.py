"""Self-Organizing Treasury: Autonomous treasury management with NFT-based governance."""

import time
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


@dataclass
class NFTHolder:
    """An NFT holder with governance rights."""
    name: str
    rarity: float  # 0-1, higher = more governance power
    tokens_staked: float = 0.0
    rewards_earned: float = 0.0


@dataclass
class FeeSplit:
    """Result of a fee collection."""
    total: float
    treasury: float
    operator: float
    rewards: float


@dataclass
class Deployment:
    """An auto-deployed chain or bridge."""
    name: str
    deployment_type: str  # 'bridge', 'chain', 'oracle'
    deployed_at: float
    status: str = "active"
    cost: float = 0.0


class SelfOrganizingTreasury:
    """Treasury that self-funds through fees and auto-deploys infrastructure.
    
    The treasury:
    - Collects transaction fees and splits them among stakeholders
    - Computes yield for NFT holders based on rarity and time
    - Auto-deploys bridges and chains when conditions are met
    - Manages NFT-based governance
    """
    
    def __init__(
        self,
        fee_split_treasury: float = 0.5,
        fee_split_operator: float = 0.2,
        fee_split_rewards: float = 0.3,
        annual_yield_rate: float = 0.05,  # 5% APY
        deployment_threshold: float = 1000.0,
    ):
        self.nft_holders: Dict[str, NFTHolder] = {}
        self.balance: float = 0.0
        self.total_collected: float = 0.0
        self.total_distributed: float = 0.0
        self.deployments: List[Deployment] = []
        
        # Fee split ratios
        self.fee_split_treasury = fee_split_treasury
        self.fee_split_operator = fee_split_operator
        self.fee_split_rewards = fee_split_rewards
        
        # Yield parameters
        self.annual_yield_rate = annual_yield_rate
        self.deployment_threshold = deployment_threshold
        
        # Transaction log
        self.transaction_log: List[Dict[str, Any]] = []
        
        # Step counter
        self.step_count: int = 0
        self.start_time: float = time.time()
        
    def register_nft_holder(self, name: str, rarity: float):
        """Register an NFT holder with governance rights.
        
        Args:
            name: Holder identifier.
            rarity: NFT rarity score (0-1).
        """
        self.nft_holders[name] = NFTHolder(name=name, rarity=rarity)
    
    def collect_fee(self, amount: float, tx_type: str = "transfer") -> Dict[str, float]:
        """Collect a transaction fee and split it.
        
        Args:
            amount: Fee amount.
            tx_type: Type of transaction (affects split ratios).
            
        Returns:
            Dictionary with split amounts.
        """
        # Adjust split based on transaction type
        treasury_ratio = self.fee_split_treasury
        operator_ratio = self.fee_split_operator
        rewards_ratio = self.fee_split_rewards
        
        if tx_type == "nft_mint":
            # NFT mints give more to rewards
            treasury_ratio = 0.3
            operator_ratio = 0.2
            rewards_ratio = 0.5
        elif tx_type == "bridge":
            # Bridge fees go more to treasury for deployment
            treasury_ratio = 0.7
            operator_ratio = 0.15
            rewards_ratio = 0.15
        
        treasury_amount = amount * treasury_ratio
        operator_amount = amount * operator_ratio
        rewards_amount = amount * rewards_ratio
        
        # Add to balance
        self.balance += treasury_amount
        self.total_collected += amount
        
        # Distribute rewards proportionally to NFT holders
        self._distribute_rewards(rewards_amount)
        
        # Log transaction
        self.transaction_log.append({
            "type": tx_type,
            "amount": amount,
            "treasury": treasury_amount,
            "operator": operator_amount,
            "rewards": rewards_amount,
            "timestamp": time.time(),
        })
        
        return {
            "treasury": treasury_amount,
            "operator": operator_amount,
            "rewards": rewards_amount,
        }
    
    def _distribute_rewards(self, amount: float):
        """Distribute rewards to NFT holders based on rarity.
        
        Args:
            amount: Total rewards to distribute.
        """
        if not self.nft_holders:
            return
        
        total_rarity = sum(h.rarity for h in self.nft_holders.values())
        if total_rarity == 0:
            return
        
        for holder in self.nft_holders.values():
            share = (holder.rarity / total_rarity) * amount
            holder.rewards_earned += share
            self.total_distributed += share
    
    def compute_yield(self, dt_years: float = 1.0 / 365.0) -> float:
        """Compute yield for the treasury over a time period.
        
        Args:
            dt_years: Time period in years.
            
        Returns:
            Yield amount in SKYNT.
        """
        if self.balance <= 0:
            return 0.0
        
        # Compound interest: A = P * (1 + r)^t
        yield_amount = self.balance * ((1 + self.annual_yield_rate) ** dt_years - 1)
        
        # Add yield to balance
        self.balance += yield_amount
        
        return yield_amount
    
    def check_deployments(self) -> List[Deployment]:
        """Check if conditions are met for auto-deployment.
        
        Returns:
            List of newly deployed infrastructure.
        """
        new_deployments = []
        
        # Deploy bridge if balance exceeds threshold
        if self.balance >= self.deployment_threshold:
            # Check if we already have a bridge
            has_bridge = any(d.deployment_type == "bridge" for d in self.deployments)
            
            if not has_bridge:
                cost = self.deployment_threshold * 0.5
                if self.balance >= cost:
                    self.balance -= cost
                    deployment = Deployment(
                        name="skynt-bridge-1",
                        deployment_type="bridge",
                        deployed_at=time.time(),
                        cost=cost,
                    )
                    self.deployments.append(deployment)
                    new_deployments.append(deployment)
        
        # Deploy oracle if we have enough NFT holders
        if len(self.nft_holders) >= 3 and self.balance >= self.deployment_threshold * 0.3:
            has_oracle = any(d.deployment_type == "oracle" for d in self.deployments)
            
            if not has_oracle:
                cost = self.deployment_threshold * 0.1
                if self.balance >= cost:
                    self.balance -= cost
                    deployment = Deployment(
                        name="skynt-oracle-1",
                        deployment_type="oracle",
                        deployed_at=time.time(),
                        cost=cost,
                    )
                    self.deployments.append(deployment)
                    new_deployments.append(deployment)
        
        return new_deployments
    
    def deposit(self, amount: float, description: str = ""):
        """Deposit funds into the treasury.
        
        Args:
            amount: Amount to deposit.
            description: Optional description.
        """
        self.balance += amount
        self.transaction_log.append({
            "type": "deposit",
            "amount": amount,
            "description": description,
            "timestamp": time.time(),
        })
    
    def withdraw(self, amount: float, recipient: str) -> bool:
        """Withdraw funds from the treasury.
        
        Args:
            amount: Amount to withdraw.
            recipient: Recipient identifier.
            
        Returns:
            True if withdrawal succeeded.
        """
        if amount > self.balance:
            return False
        
        self.balance -= amount
        self.transaction_log.append({
            "type": "withdrawal",
            "amount": amount,
            "recipient": recipient,
            "timestamp": time.time(),
        })
        
        return True
    
    def get_governance_power(self) -> Dict[str, float]:
        """Get governance power distribution among NFT holders.
        
        Returns:
            Dictionary mapping holder names to their governance power.
        """
        total_rarity = sum(h.rarity for h in self.nft_holders.values())
        
        if total_rarity == 0:
            return {name: 0.0 for name in self.nft_holders}
        
        return {
            name: holder.rarity / total_rarity
            for name, holder in self.nft_holders.items()
        }
    
    def get_treasury_state(self) -> Dict[str, Any]:
        """Get the current state of the treasury."""
        return {
            "balance": self.balance,
            "total_collected": self.total_collected,
            "total_distributed": self.total_distributed,
            "nft_holders": len(self.nft_holders),
            "deployments": len(self.deployments),
            "transactions": len(self.transaction_log),
            "governance_power": self.get_governance_power(),
            "uptime": time.time() - self.start_time,
        }
    
    def step(self):
        """Perform one treasury step: compute yield and check deployments."""
        self.step_count += 1
        
        # Compute daily yield
        dt = 1.0 / 365.0  # 1 day
        self.compute_yield(dt)
        
        # Check for auto-deployments
        self.check_deployments()
