"""Tests for Conscious Consensus Engine."""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sphinx_os.nexus import ConsciousConsensusEngine


class TestConsciousConsensusEngine(unittest.TestCase):
    """Test suite for ConsciousConsensusEngine."""

    def setUp(self):
        self.engine = ConsciousConsensusEngine()
        # Register 5 validators
        for i in range(5):
            self.engine.register_validator(f"validator_{i}", stake=10.0, nft_rarity=0.8)

    def test_validator_registration(self):
        """Test validators are registered correctly."""
        self.assertEqual(len(self.engine.validators), 5)
        self.assertIn("validator_0", self.engine.validators)
        self.assertEqual(self.engine.validators["validator_0"].stake, 10.0)

    def test_propose_block(self):
        """Test block proposal."""
        txs = [{"from": "alice", "to": "bob", "amount": 100}]
        candidate = self.engine.propose_block("validator_0", txs)
        
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate.height, 1)
        self.assertEqual(candidate.proposer, "validator_0")
        self.assertEqual(len(candidate.transactions), 1)

    def test_propose_block_invalid_proposer(self):
        """Test block proposal fails for unknown proposer."""
        txs = [{"from": "alice", "to": "bob", "amount": 100}]
        candidate = self.engine.propose_block("unknown", txs)
        
        self.assertIsNone(candidate)

    def test_phi_score_computation(self):
        """Test φ score is computed."""
        txs = [{"from": "alice", "to": "bob", "amount": 100}]
        candidate = self.engine.propose_block("validator_0", txs)
        
        self.assertGreater(candidate.phi_score, 0.0)
        self.assertLessEqual(candidate.phi_score, 1.0)

    def test_voting(self):
        """Test voting on a block."""
        txs = [{"from": "alice", "to": "bob", "amount": 100}]
        candidate = self.engine.propose_block("validator_0", txs)
        
        # Vote with all validators
        for i in range(1, 5):
            self.engine.vote(f"validator_{i}", candidate.block_hash, True)
        
        self.assertEqual(candidate.votes_for, 4)
        self.assertEqual(candidate.votes_against, 0)

    def test_block_finalization(self):
        """Test block finalization with supermajority."""
        txs = [{"from": "alice", "to": "bob", "amount": 100}]
        candidate = self.engine.propose_block("validator_0", txs)
        
        # Vote with all validators
        for i in range(1, 5):
            self.engine.vote(f"validator_{i}", candidate.block_hash, True)
        
        # Should be finalized (4/5 = 80% > 66%)
        self.assertTrue(candidate.is_finalized)
        self.assertEqual(len(self.engine.finalized_blocks), 1)

    def test_vote_invalid_validator(self):
        """Test voting with invalid validator is ignored."""
        txs = [{"from": "alice", "to": "bob", "amount": 100}]
        candidate = self.engine.propose_block("validator_0", txs)
        
        initial_votes = candidate.votes_for
        self.engine.vote("unknown", candidate.block_hash, True)
        self.assertEqual(candidate.votes_for, initial_votes)

    def test_vote_invalid_block(self):
        """Test voting on non-existent block is ignored."""
        self.engine.vote("validator_1", "nonexistent", True)
        # Should not raise

    def test_stats_tracking(self):
        """Test statistics are tracked."""
        txs = [{"from": "alice", "to": "bob", "amount": 100}]
        self.engine.propose_block("validator_0", txs)
        
        self.assertEqual(self.engine.stats["blocks_proposed"], 1)

    def test_get_state(self):
        """Test get_state returns all fields."""
        state = self.engine.get_state()
        
        self.assertIn("current_height", state)
        self.assertIn("validators", state)
        self.assertIn("phi_tau", state)
        self.assertIn("phi_gwt", state)
        self.assertIn("phi_icp", state)
        self.assertIn("phi_fano", state)
        self.assertIn("phi_qg", state)
        self.assertIn("stats", state)

    def test_multiple_blocks(self):
        """Test multiple block proposals and finalization."""
        for i in range(3):
            txs = [{"from": "alice", "to": "bob", "amount": 100 * (i + 1)}]
            candidate = self.engine.propose_block("validator_0", txs)
            
            for j in range(1, 5):
                self.engine.vote(f"validator_{j}", candidate.block_hash, True)
        
        self.assertEqual(self.engine.current_height, 3)
        self.assertEqual(len(self.engine.finalized_blocks), 3)

    def test_chain_growth(self):
        """Test chain grows with finalized blocks."""
        txs = [{"from": "alice", "to": "bob", "amount": 100}]
        candidate = self.engine.propose_block("validator_0", txs)
        
        for i in range(1, 5):
            self.engine.vote(f"validator_{i}", candidate.block_hash, True)
        
        self.assertEqual(len(self.engine.chain), 1)


if __name__ == "__main__":
    unittest.main()
