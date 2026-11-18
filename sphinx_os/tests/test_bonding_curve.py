"""Tests for the Custom Bonding Curve module."""

import unittest
import math
import time
from sphinx_os.nexus.bonding_curve import (
    CustomBondingCurve,
    BondingCurveTrade,
    BondingCurveState,
)


class TestBondingCurvePrice(unittest.TestCase):
    """Test price calculation of the bonding curve."""
    
    def test_initial_price_is_near_min(self):
        """Price should start near minimum when supply is 0."""
        curve = CustomBondingCurve(min_price=0.01, max_price=10.0)
        price = curve.calculate_price(0)
        # At supply=0, sigmoid is close to 0 but not exactly 0
        # Price should be between min_price and (min_price + max_price)/4
        self.assertGreater(price, 0.01)
        self.assertLess(price, 2.5)
    
    def test_price_at_inflection_is_midpoint(self):
        """Price at inflection supply should be midpoint between min and max."""
        curve = CustomBondingCurve(
            min_price=0.01,
            max_price=10.0,
            inflection_supply=500000.0,
        )
        price = curve.calculate_price(500000.0)
        midpoint = (0.01 + 10.0) / 2
        self.assertAlmostEqual(price, midpoint, places=1)
    
    def test_price_increases_with_supply(self):
        """Price should increase as supply increases."""
        curve = CustomBondingCurve()
        price_low = curve.calculate_price(0)
        price_mid = curve.calculate_price(250000)
        price_high = curve.calculate_price(500000)
        
        self.assertLess(price_low, price_mid)
        self.assertLess(price_mid, price_high)
    
    def test_price_never_exceeds_max(self):
        """Price should never exceed maximum price."""
        curve = CustomBondingCurve(max_price=10.0)
        for supply in [0, 100000, 500000, 1000000, 10000000]:
            price = curve.calculate_price(supply)
            self.assertLessEqual(price, 10.0)
    
    def test_price_never_below_min(self):
        """Price should never be below minimum price."""
        curve = CustomBondingCurve(min_price=0.01)
        for supply in [0, 100000, 500000]:
            price = curve.calculate_price(supply)
            self.assertGreaterEqual(price, 0.01)
    
    def test_nexus_influence_modifies_price(self):
        """Nexus influence should modify the curve parameters."""
        curve = CustomBondingCurve()
        base_price = curve.calculate_price(250000)
        
        # Apply quantum entropy influence
        curve.apply_nexus_influence(quantum_entropy=1.0, phi_score=0.0)
        influenced_price = curve.calculate_price(250000)
        
        # Price should change due to influence
        self.assertNotAlmostEqual(base_price, influenced_price, places=4)


class TestBondingCurvePhase(unittest.TestCase):
    """Test phase detection of the bonding curve."""
    
    def test_initial_phase_is_early(self):
        """Initial phase should be 'early'."""
        curve = CustomBondingCurve(inflection_supply=500000.0)
        self.assertEqual(curve.get_phase(), "early")
    
    def test_phase_transitions_to_growth(self):
        """Phase should transition to 'growth' at 30% of inflection."""
        curve = CustomBondingCurve(inflection_supply=500000.0)
        curve.supply = 150001  # Just above 30%
        self.assertEqual(curve.get_phase(), "growth")
    
    def test_phase_transitions_to_mature(self):
        """Phase should transition to 'mature' at 70% of inflection."""
        curve = CustomBondingCurve(inflection_supply=500000.0)
        curve.supply = 350001  # Just above 70%
        self.assertEqual(curve.get_phase(), "mature")


class TestBondingCurveBuy(unittest.TestCase):
    """Test buying URUU tokens with EXCAL."""
    
    def test_buy_returns_positive_amount(self):
        """Buying should return positive URUU amount."""
        curve = CustomBondingCurve(initial_reserve=1000.0)
        uruu_amount, price, fee = curve.calculate_buy_output(100.0)
        
        self.assertGreater(uruu_amount, 0)
        self.assertGreater(price, 0)
        self.assertGreaterEqual(fee, 0)
    
    def test_buy_updates_supply_and_reserve(self):
        """Buying should increase supply and reserve."""
        curve = CustomBondingCurve(initial_reserve=1000.0)
        initial_supply = curve.supply
        initial_reserve = curve.reserve
        
        trade = curve.buy(100.0, "A1B2C3D4E5F6A7B8C9D0")
        
        self.assertGreater(curve.supply, initial_supply)
        self.assertGreater(curve.reserve, initial_reserve)
    
    def test_buy_creates_trade_record(self):
        """Buying should create a trade record."""
        curve = CustomBondingCurve()
        trade = curve.buy(100.0, "A1B2C3D4E5F6A7B8C9D0")
        
        self.assertEqual(trade.trade_type, "buy")
        self.assertEqual(trade.amount_in, 100.0)
        self.assertGreater(trade.amount_out, 0)
        self.assertEqual(trade.trader_address, "A1B2C3D4E5F6A7B8C9D0")
    
    def test_buy_raises_on_zero_amount(self):
        """Buying zero should raise ValueError."""
        curve = CustomBondingCurve()
        with self.assertRaises(ValueError):
            curve.buy(0, "A1B2C3D4E5F6A7B8C9D0")
    
    def test_buy_raises_on_negative_amount(self):
        """Buying negative should raise ValueError."""
        curve = CustomBondingCurve()
        with self.assertRaises(ValueError):
            curve.buy(-100, "A1B2C3D4E5F6A7B8C9D0")
    
    def test_buy_raises_on_insufficient_reserve(self):
        """Buying more than reserve should raise ValueError."""
        curve = CustomBondingCurve(initial_reserve=100.0)
        with self.assertRaises(ValueError):
            curve.buy(1000.0, "A1B2C3D4E5F6A7B8C9D0")
    
    def test_buy_raises_on_max_supply(self):
        """Buying when max supply reached should raise ValueError."""
        curve = CustomBondingCurve(max_supply=1000.0)
        curve.supply = 1000.0  # Already at max
        with self.assertRaises(ValueError):
            curve.buy(100.0, "A1B2C3D4E5F6A7B8C9D0")
    
    def test_multiple_buys_increase_price(self):
        """Multiple buys should gradually increase price."""
        curve = CustomBondingCurve(initial_reserve=10000.0)
        
        prices = []
        for _ in range(5):
            _, price, _ = curve.calculate_buy_output(100.0)
            prices.append(price)
            curve.buy(100.0, "A1B2C3D4E5F6A7B8C9D0")
        
        # Prices should be non-decreasing
        for i in range(1, len(prices)):
            self.assertGreaterEqual(prices[i], prices[i-1] * 0.99)  # Allow small tolerance


class TestBondingCurveSell(unittest.TestCase):
    """Test selling URUU tokens for EXCAL."""
    
    def test_sell_after_buy(self):
        """Should be able to sell after buying."""
        curve = CustomBondingCurve(initial_reserve=1000.0)
        
        # Buy some URUU
        buy_trade = curve.buy(100.0, "A1B2C3D4E5F6A7B8C9D0")
        uruu_bought = buy_trade.amount_out
        
        # Sell half
        sell_trade = curve.sell(uruu_bought / 2, "A1B2C3D4E5F6A7B8C9D0")
        
        self.assertEqual(sell_trade.trade_type, "sell")
        self.assertGreater(sell_trade.amount_out, 0)
    
    def test_sell_raises_on_insufficient_supply(self):
        """Selling more than supply should raise ValueError."""
        curve = CustomBondingCurve()
        with self.assertRaises(ValueError):
            curve.sell(100.0, "A1B2C3D4E5F6A7B8C9D0")
    
    def test_sell_raises_on_zero_amount(self):
        """Selling zero should raise ValueError."""
        curve = CustomBondingCurve()
        curve.supply = 1000.0
        with self.assertRaises(ValueError):
            curve.sell(0, "A1B2C3D4E5F6A7B8C9D0")
    
    def test_sell_reduces_supply(self):
        """Selling should reduce supply."""
        curve = CustomBondingCurve(initial_reserve=1000.0)
        curve.buy(100.0, "A1B2C3D4E5F6A7B8C9D0")
        initial_supply = curve.supply
        
        curve.sell(50.0, "A1B2C3D4E5F6A7B8C9D0")
        
        self.assertLess(curve.supply, initial_supply)


class TestBondingCurveState(unittest.TestCase):
    """Test state retrieval of the bonding curve."""
    
    def test_get_state_returns_correct_type(self):
        """get_state should return BondingCurveState."""
        curve = CustomBondingCurve()
        state = curve.get_state()
        
        self.assertIsInstance(state, BondingCurveState)
        self.assertEqual(state.phase, "early")
        self.assertEqual(state.supply, 0.0)
        self.assertEqual(state.reserve, 1000.0)
    
    def test_state_reflects_trades(self):
        """State should reflect completed trades."""
        curve = CustomBondingCurve()
        curve.buy(100.0, "A1B2C3D4E5F6A7B8C9D0")
        
        state = curve.get_state()
        self.assertGreater(state.supply, 0)
        self.assertEqual(state.total_trades, 1)
        self.assertGreater(state.total_volume, 0)


class TestBondingCurveTradeHistory(unittest.TestCase):
    """Test trade history retrieval."""
    
    def test_empty_history(self):
        """New curve should have empty history."""
        curve = CustomBondingCurve()
        history = curve.get_trade_history()
        self.assertEqual(len(history), 0)
    
    def test_history_records_trades(self):
        """History should record trades."""
        curve = CustomBondingCurve()
        curve.buy(100.0, "A1B2C3D4E5F6A7B8C9D0")
        curve.buy(200.0, "B1B2C3D4E5F6A7B8C9D0")
        
        history = curve.get_trade_history()
        self.assertEqual(len(history), 2)
    
    def test_history_is_reversed(self):
        """History should be most recent first."""
        curve = CustomBondingCurve()
        curve.buy(100.0, "A1B2C3D4E5F6A7B8C9D0")
        time.sleep(0.01)
        curve.buy(200.0, "B1B2C3D4E5F6A7B8C9D0")
        
        history = curve.get_trade_history()
        self.assertGreater(history[0].timestamp, history[1].timestamp)
    
    def test_history_limit(self):
        """History should respect limit."""
        curve = CustomBondingCurve()
        for i in range(10):
            curve.buy(10.0, f"ADDR{i:020d}")
        
        history = curve.get_trade_history(limit=5)
        self.assertEqual(len(history), 5)


class TestBondingCurvePriceImpact(unittest.TestCase):
    """Test price impact calculation."""
    
    def test_small_trade_low_impact(self):
        """Small trades should have low price impact."""
        curve = CustomBondingCurve(initial_reserve=10000.0)
        impact = curve.get_price_impact(10.0, is_buy=True)
        
        self.assertIn("current_price", impact)
        self.assertIn("price_impact_pct", impact)
        self.assertLess(abs(impact["price_impact_pct"]), 5.0)  # Less than 5%
    
    def test_large_trade_high_impact(self):
        """Large trades should have higher price impact."""
        curve = CustomBondingCurve(initial_reserve=1000.0)
        impact = curve.get_price_impact(500.0, is_buy=True)
        
        self.assertGreater(abs(impact["price_impact_pct"]), 0.1)  # More than 0.1%
    
    def test_sell_impact_is_negative(self):
        """Sell impact should generally be negative."""
        curve = CustomBondingCurve(initial_reserve=1000.0)
        curve.buy(200.0, "A1B2C3D4E5F6A7B8C9D0")
        
        impact = curve.get_price_impact(100.0, is_buy=False)
        self.assertLess(impact["price_impact_pct"], 0)


class TestBondingCurveFee(unittest.TestCase):
    """Test fee calculation."""
    
    def test_fee_is_calculated(self):
        """Fee should be calculated based on fee rate."""
        curve = CustomBondingCurve(fee_rate=0.003)
        _, _, fee = curve.calculate_buy_output(100.0)
        
        expected_fee = 100.0 * 0.003
        self.assertAlmostEqual(fee, expected_fee, places=4)
    
    def test_custom_fee_rate(self):
        """Custom fee rate should be respected."""
        curve = CustomBondingCurve(fee_rate=0.01)
        _, _, fee = curve.calculate_buy_output(100.0)
        
        expected_fee = 100.0 * 0.01
        self.assertAlmostEqual(fee, expected_fee, places=4)


if __name__ == "__main__":
    unittest.main()
