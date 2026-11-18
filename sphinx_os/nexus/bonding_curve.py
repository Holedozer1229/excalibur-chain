"""Custom Bonding Curve for URUU Token on zkSync Era.

Implements a sigmoid (S-curve) bonding curve for the URUU token that bridges
EXCAL blockchain with zkSync Era. The curve provides:

- Fair price discovery with three phases:
  1. Slow initial growth (early adopters)
  2. Accelerated middle phase (main adoption)
  3. Stabilization near price ceiling (maturity)

- Reserve-backed liquidity: users buy URUU with EXCAL, and the reserve
  holds EXCAL to pay sellers when URUU is burned.

- Integration with SphinxOS Nexus: the curve parameters can be influenced
  by quantum spacetime fabric metrics and conscious consensus scores.

Mathematical Model:
    Price P(s) = a + (b - a) / (1 + e^(-k * (s - s0)))
    
    Where:
    - a: minimum price (floor)
    - b: maximum price (ceiling)
    - k: steepness factor
    - s0: inflection point (supply at midpoint)
    - s: current token supply

Reserve Ratio:
    The reserve holds EXCAL tokens. When buying URUU:
    - User sends EXCAL to reserve
    - New URUU tokens are minted based on curve price
    
    When selling URUU:
    - URUU tokens are burned
    - EXCAL is returned from reserve based on curve price
"""

import math
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple


@dataclass
class BondingCurveTrade:
    """Record of a trade on the bonding curve."""
    trade_id: str
    timestamp: float
    trade_type: str  # 'buy' or 'sell'
    amount_in: float  # EXCAL amount
    amount_out: float  # URUU amount
    price: float  # URUU price in EXCAL
    supply_after: float  # URUU supply after trade
    reserve_after: float  # EXCAL reserve after trade
    trader_address: str


@dataclass
class BondingCurveState:
    """Current state of the bonding curve."""
    supply: float  # Total URUU supply
    reserve: float  # EXCAL reserve
    current_price: float  # Current URUU price in EXCAL
    total_volume: float  # Total trading volume in EXCAL
    total_trades: int  # Number of trades executed
    phase: str  # 'early', 'growth', 'mature'


class CustomBondingCurve:
    """Sigmoid bonding curve for URUU token with EXCAL reserve.
    
    The curve follows a sigmoid (S-shape) pattern:
    - Early phase: slow price increase, rewarding early adopters
    - Growth phase: accelerated price increase during main adoption
    - Mature phase: price stabilizes near ceiling
    
    Parameters can be dynamically adjusted based on Nexus metrics:
    - Quantum entanglement entropy can influence steepness
    - Conscious consensus phi score can shift inflection point
    """
    
    def __init__(
        self,
        min_price: float = 0.01,  # Minimum URUU price in EXCAL
        max_price: float = 10.0,  # Maximum URUU price in EXCAL
        steepness: float = 0.1,  # Curve steepness factor
        inflection_supply: float = 500000.0,  # Supply at price midpoint
        initial_reserve: float = 1000.0,  # Initial EXCAL reserve
        max_supply: float = 1000000.0,  # Maximum URUU supply
        fee_rate: float = 0.003,  # Trading fee (0.3%)
    ):
        # Curve parameters
        self.min_price = min_price
        self.max_price = max_price
        self.steepness = steepness
        self.inflection_supply = inflection_supply
        
        # Reserve and supply
        self.reserve = initial_reserve
        self.supply = 0.0
        self.max_supply = max_supply
        self.initial_reserve = initial_reserve
        
        # Trading parameters
        self.fee_rate = fee_rate
        
        # Statistics
        self.total_volume = 0.0
        self.total_trades = 0
        self.trades: List[BondingCurveTrade] = []
        self.start_time = time.time()
        
        # Nexus integration metrics
        self.quantum_entropy_influence = 0.0
        self.phi_score_influence = 0.0
    
    def calculate_price(self, supply: Optional[float] = None) -> float:
        """Calculate the current price based on supply using sigmoid curve.
        
        Args:
            supply: Supply level to calculate price for. If None, uses current supply.
            
        Returns:
            Current price in EXCAL per URUU.
        """
        s = supply if supply is not None else self.supply
        
        # Apply Nexus influences
        effective_steepness = self.steepness * (1 + self.quantum_entropy_influence)
        effective_inflection = self.inflection_supply * (1 - self.phi_score_influence * 0.1)
        
        # Sigmoid function: P(s) = a + (b - a) / (1 + e^(-k * (s - s0)))
        a = self.min_price
        b = self.max_price
        k = effective_steepness / 10000.0  # Normalize steepness
        s0 = effective_inflection
        
        exponent = -k * (s - s0)
        # Clamp exponent to prevent overflow
        exponent = max(-500, min(500, exponent))
        
        sigmoid_value = 1.0 / (1.0 + math.exp(exponent))
        price = a + (b - a) * sigmoid_value
        
        return price
    
    def get_phase(self) -> str:
        """Determine the current phase of the bonding curve.
        
        Returns:
            'early', 'growth', or 'mature' based on supply level.
        """
        if self.supply < self.inflection_supply * 0.3:
            return "early"
        elif self.supply < self.inflection_supply * 0.7:
            return "growth"
        else:
            return "mature"
    
    def calculate_buy_output(self, amount_in: float) -> Tuple[float, float, float]:
        """Calculate how much URUU can be bought with EXCAL.
        
        Uses numerical integration to find the exact amount of URUU that
        corresponds to the given EXCAL input, considering the curve's
        changing price.
        
        Args:
            amount_in: Amount of EXCAL to spend.
            
        Returns:
            Tuple of (uruu_amount, price, fee).
        """
        if amount_in <= 0:
            raise ValueError("Amount in must be positive")
        
        # Calculate fee
        fee = amount_in * self.fee_rate
        amount_after_fee = amount_in - fee
        
        # Check if we have enough reserve
        if amount_after_fee > self.reserve * 0.95:  # Keep 5% reserve buffer
            raise ValueError("Insufficient reserve for this trade")
        
        # Check max supply
        if self.supply >= self.max_supply:
            raise ValueError("Maximum URUU supply reached")
        
        # Numerical integration to find URUU amount
        # We integrate the inverse of the price curve
        current_supply = self.supply
        remaining_excal = amount_after_fee
        uruu_amount = 0.0
        
        # Use small steps for accuracy
        step_size = 100.0  # URUU steps
        
        while remaining_excal > 0.01 and (current_supply + uruu_amount) < self.max_supply:
            step = min(step_size, self.max_supply - (current_supply + uruu_amount))
            price = self.calculate_price(current_supply + uruu_amount)
            cost = price * step
            
            if cost <= remaining_excal:
                uruu_amount += step
                remaining_excal -= cost
            else:
                # Partial step
                uruu_amount += remaining_excal / price
                remaining_excal = 0
        
        # Calculate average price
        avg_price = amount_after_fee / uruu_amount if uruu_amount > 0 else self.calculate_price()
        
        return uruu_amount, avg_price, fee
    
    def calculate_sell_output(self, amount_in: float) -> Tuple[float, float, float]:
        """Calculate how much EXCAL can be received for selling URUU.
        
        Args:
            amount_in: Amount of URUU to sell (burn).
            
        Returns:
            Tuple of (excal_amount, price, fee).
        """
        if amount_in <= 0:
            raise ValueError("Amount in must be positive")
        
        if amount_in > self.supply:
            raise ValueError("Insufficient URUU supply")
        
        # Calculate fee
        fee_on_output = 0  # Fee will be calculated on output
        
        # Numerical integration to find EXCAL amount
        current_supply = self.supply
        uruu_remaining = amount_in
        excal_amount = 0.0
        
        step_size = 100.0
        
        while uruu_remaining > 0.01 and current_supply > 0:
            step = min(step_size, uruu_remaining, current_supply)
            price = self.calculate_price(current_supply)
            revenue = price * step
            
            if revenue <= self.reserve * 0.95:  # Keep 5% reserve buffer
                excal_amount += revenue
                uruu_remaining -= step
                current_supply -= step
            else:
                # Partial step due to reserve constraint
                max_revenue = self.reserve * 0.95
                excal_amount += max_revenue
                uruu_remaining -= max_revenue / price
                current_supply -= max_revenue / price
                break
        
        # Calculate fee on output
        fee = excal_amount * self.fee_rate
        excal_after_fee = excal_amount - fee
        
        # Calculate average price
        avg_price = excal_amount / amount_in if amount_in > 0 else self.calculate_price()
        
        return excal_after_fee, avg_price, fee
    
    def buy(self, amount_in: float, trader_address: str) -> BondingCurveTrade:
        """Execute a buy trade: EXCAL -> URUU.
        
        Args:
            amount_in: Amount of EXCAL to spend.
            trader_address: Address of the trader.
            
        Returns:
            Trade record.
        """
        uruu_amount, price, fee = self.calculate_buy_output(amount_in)
        
        # Update state
        self.supply += uruu_amount
        self.reserve += (amount_in - fee)  # Fee goes to treasury
        self.total_volume += amount_in
        self.total_trades += 1
        
        # Create trade record
        trade = BondingCurveTrade(
            trade_id=f"buy_{self.total_trades}",
            timestamp=time.time(),
            trade_type="buy",
            amount_in=amount_in,
            amount_out=uruu_amount,
            price=price,
            supply_after=self.supply,
            reserve_after=self.reserve,
            trader_address=trader_address,
        )
        
        self.trades.append(trade)
        return trade
    
    def sell(self, amount_in: float, trader_address: str) -> BondingCurveTrade:
        """Execute a sell trade: URUU -> EXCAL.
        
        Args:
            amount_in: Amount of URUU to sell (burn).
            trader_address: Address of the trader.
            
        Returns:
            Trade record.
        """
        excal_amount, price, fee = self.calculate_sell_output(amount_in)
        
        # Update state
        self.supply -= amount_in
        self.reserve -= (excal_amount + fee)  # Fee goes to treasury
        self.total_volume += excal_amount
        self.total_trades += 1
        
        # Create trade record
        trade = BondingCurveTrade(
            trade_id=f"sell_{self.total_trades}",
            timestamp=time.time(),
            trade_type="sell",
            amount_in=amount_in,
            amount_out=excal_amount,
            price=price,
            supply_after=self.supply,
            reserve_after=self.reserve,
            trader_address=trader_address,
        )
        
        self.trades.append(trade)
        return trade
    
    def apply_nexus_influence(self, quantum_entropy: float, phi_score: float):
        """Apply influence from Nexus quantum spacetime and consensus metrics.
        
        Args:
            quantum_entropy: Entanglement entropy from quantum fabric (0-1).
            phi_score: Conscious consensus phi score (0-1).
        """
        # Quantum entropy influences steepness (higher entropy = steeper curve)
        self.quantum_entropy_influence = quantum_entropy * 0.2  # Max 20% increase
        
        # Phi score influences inflection point (higher phi = earlier inflection)
        self.phi_score_influence = phi_score * 0.1  # Max 10% shift
    
    def get_state(self) -> BondingCurveState:
        """Get current state of the bonding curve.
        
        Returns:
            BondingCurveState with current metrics.
        """
        return BondingCurveState(
            supply=self.supply,
            reserve=self.reserve,
            current_price=self.calculate_price(),
            total_volume=self.total_volume,
            total_trades=self.total_trades,
            phase=self.get_phase(),
        )
    
    def get_trade_history(self, limit: int = 100) -> List[BondingCurveTrade]:
        """Get recent trade history.
        
        Args:
            limit: Maximum number of trades to return.
            
        Returns:
            List of recent trades, most recent first.
        """
        return list(reversed(self.trades[-limit:]))
    
    def get_price_impact(self, amount: float, is_buy: bool = True) -> Dict[str, float]:
        """Calculate the price impact of a potential trade.
        
        Args:
            amount: Trade amount.
            is_buy: True for buy, False for sell.
            
        Returns:
            Dictionary with price impact metrics.
        """
        current_price = self.calculate_price()
        
        if is_buy:
            try:
                _, avg_price, _ = self.calculate_buy_output(amount)
                new_price = self.calculate_price(self.supply + amount)
            except (ValueError, ZeroDivisionError):
                return {
                    "current_price": current_price,
                    "new_price": self.max_price,
                    "price_impact_pct": 100.0,
                    "slippage_pct": 100.0,
                }
        else:
            try:
                _, avg_price, _ = self.calculate_sell_output(amount)
                new_price = self.calculate_price(max(0, self.supply - amount))
            except (ValueError, ZeroDivisionError):
                return {
                    "current_price": current_price,
                    "new_price": self.min_price,
                    "price_impact_pct": -100.0,
                    "slippage_pct": 100.0,
                }
        
        price_impact = ((new_price - current_price) / current_price) * 100
        slippage = ((avg_price - current_price) / current_price) * 100 if current_price > 0 else 0
        
        return {
            "current_price": current_price,
            "new_price": new_price,
            "avg_price": avg_price,
            "price_impact_pct": price_impact,
            "slippage_pct": slippage,
        }
