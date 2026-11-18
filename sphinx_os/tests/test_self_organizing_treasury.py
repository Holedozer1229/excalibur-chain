"""Tests for Self-Organizing Treasury."""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sphinx_os.nexus import SelfOrganizingTreasury


class TestSelfOrganizingTreasury(unittest.TestCase):
    """Test suite for SelfOrganizingTreasury."""

    def setUp(self):
        self.treasury = SelfOrganizingTreasury()
        self.treasury.register_nft_holder("alice", 0.9)
        self.treasury.register_nft_holder("bob", 0.7)

    def test_nft_holder_registration(self):
        """Test NFT holder registration."""
        self.assertEqual(len(self.treasury.nft_holders), 2)
        self.assertIn("alice", self.treasury.nft_holders)
        self.assertEqual(self.treasury.nft_holders["alice"].rarity, 0.9)

    def test_fee_collection_transfer(self):
        """Test fee collection for transfer type."""
        split = self.treasury.collect_fee(100.0, "transfer")
        
        self.assertAlmostEqual(split["treasury"], 50.0)
        self.assertAlmostEqual(split["operator"], 20.0)
        self.assertAlmostEqual(split["rewards"], 30.0)

    def test_fee_collection_nft_mint(self):
        """Test fee collection for NFT mint type."""
        split = self.treasury.collect_fee(100.0, "nft_mint")
        
        self.assertAlmostEqual(split["treasury"], 30.0)
        self.assertAlmostEqual(split["operator"], 20.0)
        self.assertAlmostEqual(split["rewards"], 50.0)

    def test_fee_collection_bridge(self):
        """Test fee collection for bridge type."""
        split = self.treasury.collect_fee(100.0, "bridge")
        
        self.assertAlmostEqual(split["treasury"], 70.0)
        self.assertAlmostEqual(split["operator"], 15.0)
        self.assertAlmostEqual(split["rewards"], 15.0)

    def test_balance_update(self):
        """Test balance increases after fee collection."""
        initial_balance = self.treasury.balance
        self.treasury.collect_fee(100.0, "transfer")
        self.assertGreater(self.treasury.balance, initial_balance)

    def test_reward_distribution(self):
        """Test rewards are distributed proportionally."""
        self.treasury.collect_fee(100.0, "transfer")
        
        alice_rewards = self.treasury.nft_holders["alice"].rewards_earned
        bob_rewards = self.treasury.nft_holders["bob"].rewards_earned
        
        # Alice has higher rarity, should get more
        self.assertGreater(alice_rewards, bob_rewards)
        self.assertAlmostEqual(alice_rewards + bob_rewards, 30.0)

    def test_yield_computation(self):
        """Test yield computation."""
        self.treasury.deposit(1000.0)
        yield_amount = self.treasury.compute_yield(dt_years=1/365)
        
        self.assertGreater(yield_amount, 0.0)
        self.assertAlmostEqual(self.treasury.balance, 1000.0 + yield_amount)

    def test_yield_zero_balance(self):
        """Test yield is zero with no balance."""
        yield_amount = self.treasury.compute_yield(dt_years=1/365)
        self.assertEqual(yield_amount, 0.0)

    def test_deposit(self):
        """Test deposit increases balance."""
        self.treasury.deposit(500.0, "Initial funding")
        self.assertEqual(self.treasury.balance, 500.0)

    def test_withdrawal(self):
        """Test successful withdrawal."""
        self.treasury.deposit(500.0)
        result = self.treasury.withdraw(200.0, "recipient")
        
        self.assertTrue(result)
        self.assertEqual(self.treasury.balance, 300.0)

    def test_withdrawal_insufficient_funds(self):
        """Test withdrawal fails with insufficient funds."""
        self.treasury.deposit(100.0)
        result = self.treasury.withdraw(200.0, "recipient")
        
        self.assertFalse(result)
        self.assertEqual(self.treasury.balance, 100.0)

    def test_governance_power(self):
        """Test governance power distribution."""
        power = self.treasury.get_governance_power()
        
        self.assertEqual(len(power), 2)
        self.assertGreater(power["alice"], power["bob"])
        self.assertAlmostEqual(sum(power.values()), 1.0)

    def test_auto_deployment_bridge(self):
        """Test auto-deployment of bridge."""
        self.treasury.deposit(2000.0)  # Above threshold
        deployments = self.treasury.check_deployments()
        
        self.assertGreater(len(deployments), 0)
        self.assertEqual(deployments[0].deployment_type, "bridge")

    def test_auto_deployment_oracle(self):
        """Test auto-deployment of oracle."""
        self.treasury.register_nft_holder("charlie", 0.5)
        self.treasury.deposit(2000.0)
        
        # First deploy bridge
        self.treasury.check_deployments()
        # Then deploy oracle
        self.treasury.deposit(500.0)
        deployments = self.treasury.check_deployments()
        
        # Should have deployed oracle
        oracle_deployed = any(d.deployment_type == "oracle" for d in self.treasury.deployments)
        self.assertTrue(oracle_deployed)

    def test_treasury_state(self):
        """Test treasury state retrieval."""
        state = self.treasury.get_treasury_state()
        
        self.assertIn("balance", state)
        self.assertIn("total_collected", state)
        self.assertIn("nft_holders", state)
        self.assertIn("deployments", state)
        self.assertIn("governance_power", state)

    def test_step(self):
        """Test treasury step."""
        self.treasury.deposit(1000.0)
        self.treasury.step()
        
        # Balance should increase due to yield (small amount for 1 day)
        # Note: check_deployments may reduce balance if threshold is met
        self.assertGreater(self.treasury.balance, 0.0)
        self.assertEqual(self.treasury.step_count, 1)

    def test_transaction_log(self):
        """Test transaction logging."""
        self.treasury.deposit(100.0)
        self.treasury.collect_fee(50.0, "transfer")
        
        self.assertEqual(len(self.treasury.transaction_log), 2)


if __name__ == "__main__":
    unittest.main()
