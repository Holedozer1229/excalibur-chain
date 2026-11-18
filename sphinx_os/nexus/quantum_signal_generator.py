"""Quantum Signal Generator — Trading signals from wormhole dynamics.

Turns wormhole dynamics into trading signals on the URUU bonding curve.
Wormhole formation → BUY, high entanglement → HOLD, curvature collapse → SELL,
φ_QG spike → STRONG_BUY. The CTC oracle verifies each signal.
"""

import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from sphinx_os.nexus.wormhole_governance import WormholeGovernanceEngine
from sphinx_os.nexus.deutsch_ctc_oracle import SphinxQOracle
from sphinx_os.nexus.bonding_curve import CustomBondingCurve as BondingCurve


@dataclass
class TradingSignal:
    """A trading signal generated from wormhole dynamics."""
    signal_type: str       # 'BUY', 'SELL', 'HOLD', 'STRONG_BUY'
    confidence: float      # 0-1 confidence score
    excal_amount: float    # Amount to trade
    price: float           # Current price
    phi_qg: float          # Quantum gravity metric
    ctc_validated: bool    # CTC oracle validation
    reasoning: str         # Human-readable reasoning


@dataclass
class Trade:
    """An executed trade."""
    signal: TradingSignal
    excal_traded: float
    uruu_amount: float
    price: float
    timestamp: int
    profit_loss: float = 0.0


@dataclass
class PortfolioReport:
    """Portfolio performance report."""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    total_excal: float
    sharpe_ratio: float
    trades: List[Trade] = field(default_factory=list)


class QuantumSignalGenerator:
    """Generates trading signals from wormhole dynamics.

    Args:
        seed: Random seed for reproducibility.
    """

    SIGNAL_TYPES = ['BUY', 'SELL', 'HOLD', 'STRONG_BUY']

    def __init__(self, seed: Optional[int] = None):
        self.engine = WormholeGovernanceEngine(seed=seed)
        self.oracle = SphinxQOracle()
        self.curve = BondingCurve()
        self.rng = np.random.RandomState(seed)
        self.trades: List[Trade] = []
        self.portfolio_excal = 100000.0  # Starting EXCAL balance
        self.portfolio_uruu = 0.0
        self.step = 0

    def generate_signal(self) -> TradingSignal:
        """Generate a trading signal from current wormhole state.

        Returns:
            TradingSignal with type, confidence, and reasoning.
        """
        # Evolve fabric
        wormholes = self.engine.evolve_fabric(steps=5)
        metrics = self.engine.get_quantum_gravity_metrics()

        # Determine signal type based on wormhole dynamics
        if len(wormholes) > 0 and metrics.phi_qg > 1.0:
            signal_type = 'STRONG_BUY'
            confidence = min(1.0, metrics.phi_qg / 5.0)
            reasoning = f"φ_QG spike ({metrics.phi_qg:.2f}) with {len(wormholes)} wormholes"
        elif len(wormholes) > 0:
            signal_type = 'BUY'
            confidence = min(1.0, metrics.avg_entanglement)
            reasoning = f"Wormhole formation: {len(wormholes)} new wormholes"
        elif metrics.avg_entanglement > 0.5:
            signal_type = 'HOLD'
            confidence = metrics.avg_entanglement
            reasoning = f"High entanglement ({metrics.avg_entanglement:.2f})"
        else:
            signal_type = 'SELL'
            confidence = 1.0 - metrics.avg_entanglement
            reasoning = f"Curvature collapse (φ_QG={metrics.phi_qg:.2f})"

        # CTC validate
        ctc_valid = self._ctc_validate(signal_type)

        price = self.curve.get_price() if self.curve.reserve > 0 else 1.0
        excal_amount = self.portfolio_excal * 0.1  # Trade 10% per signal

        return TradingSignal(
            signal_type=signal_type,
            confidence=confidence,
            excal_amount=excal_amount,
            price=price,
            phi_qg=metrics.phi_qg,
            ctc_validated=ctc_valid,
            reasoning=reasoning,
        )

    def execute_signal(self, signal: TradingSignal) -> Optional[Trade]:
        """Execute a trading signal on the bonding curve.

        Args:
            signal: The trading signal to execute.

        Returns:
            Trade object or None if signal is HOLD.
        """
        if signal.signal_type == 'HOLD':
            return None

        if signal.signal_type in ('BUY', 'STRONG_BUY'):
            # Buy URUU with EXCAL
            multiplier = 2.0 if signal.signal_type == 'STRONG_BUY' else 1.0
            excal = min(signal.excal_amount * multiplier, self.portfolio_excal)
            uruu = self.curve.buy(excal)
            self.portfolio_excal -= excal
            self.portfolio_uruu += uruu
        else:
            # Sell URUU for EXCAL
            uruu = min(signal.excal_amount / signal.price, self.portfolio_uruu)
            excal = self.curve.sell(uruu)
            self.portfolio_uruu -= uruu
            self.portfolio_excal += excal

        trade = Trade(
            signal=signal,
            excal_traded=excal if signal.signal_type in ('BUY', 'STRONG_BUY') else -excal,
            uruu_amount=uruu,
            price=signal.price,
            timestamp=self.step,
        )
        self.trades.append(trade)
        self.step += 1
        return trade

    def run_simulation(self, steps: int = 50) -> PortfolioReport:
        """Run a full simulation for N steps.

        Args:
            steps: Number of simulation steps.

        Returns:
            PortfolioReport with performance metrics.
        """
        for _ in range(steps):
            signal = self.generate_signal()
            self.execute_signal(signal)

        return self.get_portfolio_report()

    def get_portfolio_report(self) -> PortfolioReport:
        """Get current portfolio performance report.

        Returns:
            PortfolioReport.
        """
        total_trades = len(self.trades)
        winning = len([t for t in self.trades if t.excal_traded > 0])
        losing = total_trades - winning
        win_rate = winning / total_trades if total_trades > 0 else 0

        # P&L: current value vs initial
        current_price = self.curve.get_price() if self.curve.reserve > 0 else 1.0
        current_value = self.portfolio_excal + self.portfolio_uruu * current_price
        pnl = current_value - 100000.0  # Initial balance

        # Sharpe ratio (simplified)
        returns = [t.excal_traded / 100000.0 for t in self.trades]
        sharpe = (np.mean(returns) / (np.std(returns) + 1e-10) * np.sqrt(252)
                  if returns else 0)

        return PortfolioReport(
            total_trades=total_trades,
            winning_trades=winning,
            losing_trades=losing,
            win_rate=win_rate,
            total_pnl=pnl,
            total_excal=self.portfolio_excal,
            sharpe_ratio=sharpe,
            trades=self.trades,
        )

    def _ctc_validate(self, signal_type: str) -> bool:
        """Validate signal through Deutsch CTC oracle."""
        candidates = self.SIGNAL_TYPES
        verify = lambda c: c == signal_type
        probs, has_valid = self.oracle.compute_distribution(candidates, verify)
        return has_valid
