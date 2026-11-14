"""EXCAL Liquidity Pool — Creates EXCAL-URUU liquidity from accumulated funds.

Seeds the bonding curve reserve, establishes trading pairs, and monitors
pool health with liquidity scores.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from sphinx_os.nexus.bonding_curve import CustomBondingCurve as BondingCurve


@dataclass
class PoolStats:
    """Liquidity pool statistics."""
    excal_reserve: float
    uruu_supply: float
    price_excal_per_uruu: float
    liquidity_score: float
    total_trades: int
    total_volume: float


@dataclass
class PoolTrade:
    """A trade executed in the pool."""
    amount: float
    direction: str  # 'BUY' or 'SELL'
    price: float
    excal_traded: float
    uruu_traded: float


class EXCALLiquidityPool:
    """EXCAL-URUU liquidity pool.

    Args:
        seed: Random seed for reproducibility.
    """

    def __init__(self, seed: Optional[int] = None):
        self.curve = BondingCurve()
        self.rng = np.random.RandomState(seed)
        self.trades: List[PoolTrade] = []
        self.excal_reserve = 0.0
        self.uruu_supply = 0.0

    def create_pool(self, excal_amount: float, btc_amount: float) -> PoolStats:
        """Create and seed the liquidity pool.

        Args:
            excal_amount: EXCAL to seed the reserve.
            btc_amount: BTC value backing the pool.

        Returns:
            PoolStats with initial state.
        """
        self.excal_reserve = excal_amount
        self.curve.add_liquidity(excal_amount)

        # Initial URUU supply based on BTC value
        self.uruu_supply = btc_amount * 300000  # ~300K URUU per BTC

        return self.get_stats()

    def trade(self, amount: float, direction: str) -> Optional[PoolTrade]:
        """Execute a trade in the pool.

        Args:
            amount: Amount to trade.
            direction: 'BUY' (EXCAL→URUU) or 'SELL' (URUU→EXCAL).

        Returns:
            PoolTrade or None if insufficient funds.
        """
        if direction == 'BUY':
            if amount > self.excal_reserve:
                return None
            uruu = self.curve.buy(amount)
            self.excal_reserve -= amount
            self.uruu_supply += uruu
            trade = PoolTrade(
                amount=amount, direction='BUY',
                price=amount / uruu if uruu > 0 else 0,
                excal_traded=amount, uruu_traded=uruu,
            )
        else:
            if amount > self.uruu_supply:
                return None
            excal = self.curve.sell(amount)
            self.uruu_supply -= amount
            self.excal_reserve += excal
            trade = PoolTrade(
                amount=amount, direction='SELL',
                price=excal / amount if amount > 0 else 0,
                excal_traded=excal, uruu_traded=amount,
            )

        self.trades.append(trade)
        return trade

    def get_price(self) -> float:
        """Get current EXCAL/URUU price."""
        if self.uruu_supply > 0:
            return self.excal_reserve / self.uruu_supply
        return self.curve.get_price()

    def get_liquidity_score(self) -> float:
        """Compute liquidity health score (0-1).

        Returns:
            Liquidity score.
        """
        # Score based on reserve size and trade volume
        reserve_score = min(1.0, self.excal_reserve / 1_000_000)
        volume_score = min(1.0, len(self.trades) / 100)
        return (reserve_score * 0.7 + volume_score * 0.3)

    def get_stats(self) -> PoolStats:
        """Get current pool statistics.

        Returns:
            PoolStats.
        """
        return PoolStats(
            excal_reserve=self.excal_reserve,
            uruu_supply=self.uruu_supply,
            price_excal_per_uruu=self.get_price(),
            liquidity_score=self.get_liquidity_score(),
            total_trades=len(self.trades),
            total_volume=sum(t.excal_traded for t in self.trades),
        )

    def rebalance(self, target_ratio: float = 1.0) -> Dict[str, float]:
        """Rebalance pool to target EXCAL/URUU ratio.

        Args:
            target_ratio: Target EXCAL/URUU ratio.

        Returns:
            Dict with rebalance actions.
        """
        current_ratio = self.excal_reserve / self.uruu_supply if self.uruu_supply > 0 else float('inf')

        if abs(current_ratio - target_ratio) < 0.01:
            return {'action': 'no_change', 'current_ratio': current_ratio}

        return {
            'action': 'rebalance_needed',
            'current_ratio': current_ratio,
            'target_ratio': target_ratio,
            'excal_reserve': self.excal_reserve,
            'uruu_supply': self.uruu_supply,
        }
