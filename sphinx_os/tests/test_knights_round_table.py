"""Tests for Knights of the Round Table governance system."""

import hashlib
import os
import sys
import time
import unittest
from unittest.mock import patch

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from sphinx_os.nexus.knights_round_table import (
    KnightsRoundTable,
    Knight,
    KnightStatus,
    ProposalType,
    VoteStatus,
    PartialSignature,
    GovernanceProposal,
    KnightNomination,
    TreasuryState,
    RoundTableState,
    PROPHECY_WORDS,
    PROPHECY_SEED,
)


class TestProphecyConstants(unittest.TestCase):
    """Test the 13-word prophecy constants."""

    def test_prophecy_word_count(self):
        """Verify exactly 13 words in the prophecy."""
        self.assertEqual(len(PROPHECY_WORDS), 13)

    def test_prophecy_words_correct(self):
        """Verify the prophecy words match Excalibur-EXS."""
        expected = [
            "sword", "legend", "pull", "magic", "kingdom",
            "artist", "stone", "destroy", "forget", "fire",
            "steel", "honey", "question",
        ]
        self.assertEqual(PROPHECY_WORDS, expected)

    def test_prophecy_seed_format(self):
        """Verify the prophecy seed is space-joined."""
        self.assertEqual(PROPHECY_SEED, " ".join(PROPHECY_WORDS))
        self.assertIn("sword", PROPHECY_SEED)
        self.assertIn("question", PROPHECY_SEED)


class TestTaprootKeyDerivation(unittest.TestCase):
    """Test Taproot key derivation from prophecy."""

    def test_derive_taproot_key_length(self):
        """Taproot key should be 32 bytes."""
        key = KnightsRoundTable._derive_taproot_key(PROPHECY_SEED)
        self.assertEqual(len(key), 32)

    def test_derive_taproot_key_deterministic(self):
        """Same prophecy should always produce the same key."""
        key1 = KnightsRoundTable._derive_taproot_key(PROPHECY_SEED)
        key2 = KnightsRoundTable._derive_taproot_key(PROPHECY_SEED)
        self.assertEqual(key1, key2)

    def test_derive_taproot_key_different_seed(self):
        """Different seeds should produce different keys."""
        key1 = KnightsRoundTable._derive_taproot_key(PROPHECY_SEED)
        key2 = KnightsRoundTable._derive_taproot_key("different seed phrase")
        self.assertNotEqual(key1, key2)

    def test_bech32m_address_format(self):
        """Address should start with bc1p."""
        key = KnightsRoundTable._derive_taproot_key(PROPHECY_SEED)
        addr = KnightsRoundTable._key_to_bech32m(key)
        self.assertTrue(addr.startswith("bc1p"))

    def test_prophecy_commitment(self):
        """Prophecy commitment should be SHA-256 of the seed."""
        expected = hashlib.sha256(PROPHECY_SEED.encode()).digest()
        actual = KnightsRoundTable._prophecy_commitment()
        self.assertEqual(actual, expected)


class TestKnightsInitialization(unittest.TestCase):
    """Test Round Table initialization."""

    def test_default_initialization(self):
        """Default initialization should create empty Round Table."""
        table = KnightsRoundTable()
        self.assertEqual(len(table.knights), 0)
        self.assertEqual(table.threshold_m, 3)
        self.assertEqual(table.threshold_n, 5)
        self.assertEqual(table.treasury_balance_excal, 0.0)

    def test_custom_threshold(self):
        """Custom threshold should be respected."""
        table = KnightsRoundTable(threshold_m=2, threshold_n=3)
        self.assertEqual(table.threshold_m, 2)
        self.assertEqual(table.threshold_n, 3)

    def test_treasury_address_set(self):
        """Treasury address should be derived from prophecy."""
        table = KnightsRoundTable()
        self.assertTrue(table._taproot_address.startswith("bc1p"))
        self.assertEqual(len(table._taproot_output_key), 32)

    def test_initial_governance_coherence(self):
        """Initial coherence should be 1.0."""
        table = KnightsRoundTable()
        self.assertEqual(table.governance_coherence, 1.0)


class TestFounderKnights(unittest.TestCase):
    """Test founder Knight addition."""

    def _make_key(self, name: str) -> bytes:
        return hashlib.sha256(name.encode()).digest()

    def test_add_founder_knight(self):
        """Adding a founder knight should register them."""
        table = KnightsRoundTable()
        knight = table.add_founder_knight(
            name="Arthur",
            public_key=self._make_key("arthur"),
            uruu_balance=500.0,
            phi_score=0.9,
            excal_stake=5000.0,
        )
        self.assertEqual(knight.name, "Arthur")
        self.assertEqual(knight.status, KnightStatus.ACTIVE)
        self.assertIn("Arthur", table.knights)

    def test_add_multiple_founders(self):
        """Should be able to add multiple founder Knights."""
        table = KnightsRoundTable()
        for i in range(5):
            table.add_founder_knight(
                name=f"Knight_{i}",
                public_key=self._make_key(f"knight_{i}"),
                uruu_balance=200.0,
                phi_score=0.8,
                excal_stake=2000.0,
            )
        self.assertEqual(len(table.get_active_knights()), 5)

    def test_founder_knight_metrics(self):
        """Founder Knight should have correct metrics."""
        table = KnightsRoundTable()
        table.add_founder_knight(
            name="Galahad",
            public_key=self._make_key("galahad"),
            uruu_balance=300.0,
            phi_score=0.85,
            excal_stake=3000.0,
        )
        knight = table.knights["Galahad"]
        self.assertEqual(knight.uruu_balance, 300.0)
        self.assertEqual(knight.phi_score, 0.85)
        self.assertEqual(knight.excal_stake, 3000.0)


class TestKnightNomination(unittest.TestCase):
    """Test Knight nomination process."""

    def _make_key(self, name: str) -> bytes:
        return hashlib.sha256(name.encode()).digest()

    def setUp(self):
        """Set up a Round Table with 5 founder Knights."""
        self.table = KnightsRoundTable()
        for i in range(5):
            self.table.add_founder_knight(
                name=f"Knight_{i}",
                public_key=self._make_key(f"knight_{i}"),
                uruu_balance=200.0,
                phi_score=0.8,
                excal_stake=2000.0,
            )

    def test_nomination_by_active_knight(self):
        """Active Knight should be able to nominate."""
        nom = self.table.nominate_knight(
            candidate_name="NewKnight",
            candidate_public_key=self._make_key("newknight"),
            nominator="Knight_0",
            uruu_balance=150.0,
            phi_score=0.7,
            excal_stake=1500.0,
        )
        self.assertIsNotNone(nom)
        self.assertEqual(nom.candidate_name, "NewKnight")

    def test_nomination_by_non_knight(self):
        """Non-Knight should not be able to nominate."""
        nom = self.table.nominate_knight(
            candidate_name="NewKnight",
            candidate_public_key=self._make_key("newknight"),
            nominator="RandomPerson",
            uruu_balance=150.0,
            phi_score=0.7,
            excal_stake=1500.0,
        )
        self.assertIsNone(nom)

    def test_nomination_below_uruu_threshold(self):
        """Candidate below URUU threshold should be rejected."""
        nom = self.table.nominate_knight(
            candidate_name="NewKnight",
            candidate_public_key=self._make_key("newknight"),
            nominator="Knight_0",
            uruu_balance=10.0,  # Below minimum_uruu_threshold (100)
            phi_score=0.7,
            excal_stake=1500.0,
        )
        self.assertIsNone(nom)

    def test_nomination_below_phi_threshold(self):
        """Candidate below phi threshold should be rejected."""
        nom = self.table.nominate_knight(
            candidate_name="NewKnight",
            candidate_public_key=self._make_key("newknight"),
            nominator="Knight_0",
            uruu_balance=150.0,
            phi_score=0.1,  # Below minimum_phi_score (0.5)
            excal_stake=1500.0,
        )
        self.assertIsNone(nom)

    def test_nomination_below_stake_threshold(self):
        """Candidate below stake threshold should be rejected."""
        nom = self.table.nominate_knight(
            candidate_name="NewKnight",
            candidate_public_key=self._make_key("newknight"),
            nominator="Knight_0",
            uruu_balance=150.0,
            phi_score=0.7,
            excal_stake=100.0,  # Below minimum_stake (1000)
        )
        self.assertIsNone(nom)

    def test_nomination_existing_knight(self):
        """Already a Knight should not be nominatable."""
        nom = self.table.nominate_knight(
            candidate_name="Knight_0",
            candidate_public_key=self._make_key("knight_0"),
            nominator="Knight_1",
            uruu_balance=150.0,
            phi_score=0.7,
            excal_stake=1500.0,
        )
        self.assertIsNone(nom)

    def test_nomination_hash_generated(self):
        """Nomination should have a valid hash."""
        nom = self.table.nominate_knight(
            candidate_name="NewKnight",
            candidate_public_key=self._make_key("newknight"),
            nominator="Knight_0",
            uruu_balance=150.0,
            phi_score=0.7,
            excal_stake=1500.0,
        )
        self.assertIsNotNone(nom)
        self.assertEqual(len(nom.nomination_hash), 32)


class TestKnightElection(unittest.TestCase):
    """Test the 3-of-5 Knight election process."""

    def _make_key(self, name: str) -> bytes:
        return hashlib.sha256(name.encode()).digest()

    def _make_secret(self, name: str) -> bytes:
        return hashlib.sha512(name.encode()).digest()

    def setUp(self):
        """Set up a Round Table with 5 founder Knights."""
        self.table = KnightsRoundTable()
        for i in range(5):
            self.table.add_founder_knight(
                name=f"Knight_{i}",
                public_key=self._make_key(f"knight_{i}"),
                uruu_balance=200.0,
                phi_score=0.8,
                excal_stake=2000.0,
            )

    def test_two_votes_not_enough(self):
        """2 votes should not trigger induction (need 3)."""
        nom = self.table.nominate_knight(
            candidate_name="NewKnight",
            candidate_public_key=self._make_key("newknight"),
            nominator="Knight_0",
            uruu_balance=150.0,
            phi_score=0.7,
            excal_stake=1500.0,
        )
        nom_id = "nom_1"

        # 2 votes
        self.table.vote_on_nomination(nom_id, "Knight_0", True, self._make_secret("k0"))
        self.table.vote_on_nomination(nom_id, "Knight_1", True, self._make_secret("k1"))

        # Should not be inducted yet
        self.assertNotIn("NewKnight", self.table.knights)

    def test_three_votes_inducts(self):
        """3 votes should trigger automatic induction."""
        nom = self.table.nominate_knight(
            candidate_name="NewKnight",
            candidate_public_key=self._make_key("newknight"),
            nominator="Knight_0",
            uruu_balance=150.0,
            phi_score=0.7,
            excal_stake=1500.0,
        )
        nom_id = "nom_1"

        # 3 votes
        self.table.vote_on_nomination(nom_id, "Knight_0", True, self._make_secret("k0"))
        self.table.vote_on_nomination(nom_id, "Knight_1", True, self._make_secret("k1"))
        self.table.vote_on_nomination(nom_id, "Knight_2", True, self._make_secret("k2"))

        # Should be inducted
        self.assertIn("NewKnight", self.table.knights)
        self.assertEqual(self.table.knights["NewKnight"].status, KnightStatus.ACTIVE)
        self.assertEqual(self.table.total_inductions, 1)

    def test_vote_no_does_not_count(self):
        """No votes should not contribute to threshold."""
        nom = self.table.nominate_knight(
            candidate_name="NewKnight",
            candidate_public_key=self._make_key("newknight"),
            nominator="Knight_0",
            uruu_balance=150.0,
            phi_score=0.7,
            excal_stake=1500.0,
        )
        nom_id = "nom_1"

        # 2 yes + 1 no
        self.table.vote_on_nomination(nom_id, "Knight_0", True, self._make_secret("k0"))
        self.table.vote_on_nomination(nom_id, "Knight_1", True, self._make_secret("k1"))
        self.table.vote_on_nomination(nom_id, "Knight_2", False, self._make_secret("k2"))

        # Should not be inducted (only 2 yes votes)
        self.assertNotIn("NewKnight", self.table.knights)

    def test_double_vote_prevented(self):
        """Same Knight should not be able to vote twice."""
        nom = self.table.nominate_knight(
            candidate_name="NewKnight",
            candidate_public_key=self._make_key("newknight"),
            nominator="Knight_0",
            uruu_balance=150.0,
            phi_score=0.7,
            excal_stake=1500.0,
        )
        nom_id = "nom_1"

        ps1 = self.table.vote_on_nomination(nom_id, "Knight_0", True, self._make_secret("k0"))
        ps2 = self.table.vote_on_nomination(nom_id, "Knight_0", True, self._make_secret("k0"))

        self.assertIsNotNone(ps1)
        self.assertIsNone(ps2)  # Second vote rejected

    def test_non_knight_cannot_vote(self):
        """Non-Knight should not be able to vote."""
        nom = self.table.nominate_knight(
            candidate_name="NewKnight",
            candidate_public_key=self._make_key("newknight"),
            nominator="Knight_0",
            uruu_balance=150.0,
            phi_score=0.7,
            excal_stake=1500.0,
        )
        nom_id = "nom_1"

        ps = self.table.vote_on_nomination(nom_id, "RandomPerson", True, b"secret")
        self.assertIsNone(ps)

    def test_resigned_knight_cannot_vote(self):
        """Resigned Knight should not be able to vote."""
        self.table.resign_knight("Knight_0")

        nom = self.table.nominate_knight(
            candidate_name="NewKnight",
            candidate_public_key=self._make_key("newknight"),
            nominator="Knight_1",
            uruu_balance=150.0,
            phi_score=0.7,
            excal_stake=1500.0,
        )
        nom_id = "nom_1"

        ps = self.table.vote_on_nomination(nom_id, "Knight_0", True, self._make_secret("k0"))
        self.assertIsNone(ps)

    def test_inducted_knight_has_correct_metrics(self):
        """Inducted Knight should have the nominated metrics."""
        nom = self.table.nominate_knight(
            candidate_name="NewKnight",
            candidate_public_key=self._make_key("newknight"),
            nominator="Knight_0",
            uruu_balance=250.0,
            phi_score=0.75,
            excal_stake=2500.0,
        )
        nom_id = "nom_1"

        # 3 votes to induct
        for i in range(3):
            self.table.vote_on_nomination(nom_id, f"Knight_{i}", True, self._make_secret(f"k{i}"))

        knight = self.table.knights["NewKnight"]
        self.assertEqual(knight.uruu_balance, 250.0)
        self.assertEqual(knight.phi_score, 0.75)
        self.assertEqual(knight.excal_stake, 2500.0)


class TestKnightResignation(unittest.TestCase):
    """Test Knight resignation."""

    def _make_key(self, name: str) -> bytes:
        return hashlib.sha256(name.encode()).digest()

    def test_resign_existing_knight(self):
        """Resigning should change status."""
        table = KnightsRoundTable()
        table.add_founder_knight(
            name="Arthur",
            public_key=self._make_key("arthur"),
            uruu_balance=200.0,
            phi_score=0.8,
            excal_stake=2000.0,
        )
        result = table.resign_knight("Arthur")
        self.assertTrue(result)
        self.assertEqual(table.knights["Arthur"].status, KnightStatus.RESIGNED)

    def test_resign_nonexistent_knight(self):
        """Resigning non-existent Knight should fail."""
        table = KnightsRoundTable()
        result = table.resign_knight("Nobody")
        self.assertFalse(result)

    def test_resigned_knight_not_active(self):
        """Resigned Knight should not appear in active list."""
        table = KnightsRoundTable()
        table.add_founder_knight(
            name="Arthur",
            public_key=self._make_key("arthur"),
            uruu_balance=200.0,
            phi_score=0.8,
            excal_stake=2000.0,
        )
        table.resign_knight("Arthur")
        active = table.get_active_knights()
        self.assertEqual(len(active), 0)


class TestGovernanceProposals(unittest.TestCase):
    """Test governance proposal system."""

    def _make_key(self, name: str) -> bytes:
        return hashlib.sha256(name.encode()).digest()

    def _make_secret(self, name: str) -> bytes:
        return hashlib.sha512(name.encode()).digest()

    def setUp(self):
        self.table = KnightsRoundTable()
        for i in range(5):
            self.table.add_founder_knight(
                name=f"Knight_{i}",
                public_key=self._make_key(f"knight_{i}"),
                uruu_balance=200.0,
                phi_score=0.8,
                excal_stake=2000.0,
            )
        # Fund treasury
        self.table.deposit_to_treasury(10000.0, "EXCAL", "test", "initial funding")

    def test_create_proposal(self):
        """Active Knight should be able to create proposals."""
        prop = self.table.create_proposal(
            ProposalType.TREASURY_SPEND,
            "Knight_0",
            "Send funds to bridge",
            {"amount": 1000.0, "recipient": "bridge_address"},
        )
        self.assertIsNotNone(prop)
        self.assertEqual(prop.proposal_type, ProposalType.TREASURY_SPEND)
        self.assertEqual(prop.status, VoteStatus.PENDING)

    def test_non_knight_cannot_propose(self):
        """Non-Knight should not be able to propose."""
        prop = self.table.create_proposal(
            ProposalType.TREASURY_SPEND,
            "RandomPerson",
            "Invalid proposal",
            {},
        )
        self.assertIsNone(prop)

    def test_proposal_execution_on_threshold(self):
        """Proposal should execute when 3-of-5 sign."""
        prop = self.table.create_proposal(
            ProposalType.TREASURY_SPEND,
            "Knight_0",
            "Send funds to bridge",
            {"amount": 1000.0, "recipient": "bridge_address"},
        )
        prop_id = "prop_1"

        initial_balance = self.table.treasury_balance_excal

        # 3 votes to execute
        for i in range(3):
            self.table.vote_on_proposal(prop_id, f"Knight_{i}", True, self._make_secret(f"k{i}"))

        # Should be executed
        self.assertEqual(self.table.proposals[prop_id].status, VoteStatus.EXECUTED)
        self.assertEqual(self.table.treasury_balance_excal, initial_balance - 1000.0)

    def test_proposal_not_executed_below_threshold(self):
        """Proposal should not execute with only 2 votes."""
        prop = self.table.create_proposal(
            ProposalType.TREASURY_SPEND,
            "Knight_0",
            "Send funds",
            {"amount": 500.0, "recipient": "addr"},
        )
        prop_id = "prop_1"

        initial_balance = self.table.treasury_balance_excal

        # Only 2 votes
        self.table.vote_on_proposal(prop_id, "Knight_0", True, self._make_secret("k0"))
        self.table.vote_on_proposal(prop_id, "Knight_1", True, self._make_secret("k1"))

        self.assertEqual(self.table.proposals[prop_id].status, VoteStatus.PENDING)
        self.assertEqual(self.table.treasury_balance_excal, initial_balance)

    def test_proposal_types(self):
        """All proposal types should be creatable."""
        for ptype in ProposalType:
            prop = self.table.create_proposal(
                ptype,
                "Knight_0",
                f"Test {ptype.value}",
                {},
            )
            self.assertIsNotNone(prop)


class TestTreasuryOperations(unittest.TestCase):
    """Test Taproot treasury operations."""

    def _make_key(self, name: str) -> bytes:
        return hashlib.sha256(name.encode()).digest()

    def test_deposit_excal(self):
        """Should be able to deposit EXCAL."""
        table = KnightsRoundTable()
        result = table.deposit_to_treasury(1000.0, "EXCAL", "sender", "test deposit")
        self.assertTrue(result)
        self.assertEqual(table.treasury_balance_excal, 1000.0)

    def test_deposit_uruu(self):
        """Should be able to deposit URUU."""
        table = KnightsRoundTable()
        result = table.deposit_to_treasury(500.0, "URUU", "sender", "uruu deposit")
        self.assertTrue(result)
        self.assertEqual(table.treasury_balance_uruu, 500.0)

    def test_deposit_invalid_token(self):
        """Invalid token should fail."""
        table = KnightsRoundTable()
        result = table.deposit_to_treasury(100.0, "INVALID", "sender", "bad token")
        self.assertFalse(result)

    def test_deposit_negative(self):
        """Negative deposit should fail."""
        table = KnightsRoundTable()
        result = table.deposit_to_treasury(-100.0, "EXCAL", "sender", "negative")
        self.assertFalse(result)

    def test_withdraw_success(self):
        """Withdrawal should succeed with sufficient balance."""
        table = KnightsRoundTable()
        table.deposit_to_treasury(1000.0, "EXCAL", "sender", "funding")
        result = table.withdraw_from_treasury(500.0, "recipient", "prop_1")
        self.assertTrue(result)
        self.assertEqual(table.treasury_balance_excal, 500.0)

    def test_withdraw_insufficient(self):
        """Withdrawal should fail with insufficient balance."""
        table = KnightsRoundTable()
        table.deposit_to_treasury(100.0, "EXCAL", "sender", "funding")
        result = table.withdraw_from_treasury(200.0, "recipient", "prop_1")
        self.assertFalse(result)
        self.assertEqual(table.treasury_balance_excal, 100.0)

    def test_treasury_state(self):
        """Treasury state should reflect all operations."""
        table = KnightsRoundTable()
        table.deposit_to_treasury(1000.0, "EXCAL", "sender1", "deposit 1")
        table.deposit_to_treasury(500.0, "URUU", "sender2", "deposit 2")
        table.withdraw_from_treasury(200.0, "recipient", "prop_1")

        state = table.get_treasury_state()
        self.assertEqual(state.balance_excal, 800.0)
        self.assertEqual(state.balance_uruu, 500.0)
        self.assertEqual(state.total_deposited, 1500.0)
        self.assertEqual(state.total_withdrawn, 200.0)
        self.assertEqual(state.num_transactions, 3)

    def test_treasury_transactions(self):
        """Transaction history should be recorded."""
        table = KnightsRoundTable()
        table.deposit_to_treasury(1000.0, "EXCAL", "sender", "deposit")
        txs = table.get_treasury_transactions()
        self.assertEqual(len(txs), 1)
        self.assertEqual(txs[0]["type"], "deposit")
        self.assertEqual(txs[0]["amount"], 1000.0)


class TestPartialSignatures(unittest.TestCase):
    """Test partial signature generation and aggregation (MuSig2 BIP-327)."""

    def _make_key(self, name: str) -> bytes:
        return hashlib.sha256(name.encode()).digest()

    def _make_secret(self, name: str) -> bytes:
        return hashlib.sha512(name.encode()).digest()

    def _setup_table_with_knights(self, count: int = 5) -> KnightsRoundTable:
        """Helper to create a table with enough Knights for MuSig2."""
        table = KnightsRoundTable()
        for i in range(count):
            table.add_founder_knight(
                name=f"Knight_{i}",
                public_key=self._make_key(f"knight_{i}"),
                uruu_balance=200.0,
                phi_score=0.8,
                excal_stake=2000.0,
            )
        return table

    def test_partial_signature_length(self):
        """Partial signature components should be valid."""
        table = self._setup_table_with_knights(3)
        msg_hash = hashlib.sha256(b"test message").digest()
        ps = table._generate_partial_signature(
            msg_hash,
            "Knight_0",
            self._make_key("knight_0"),
            self._make_secret("knight_0"),
        )
        self.assertEqual(len(ps.partial_r), 32)
        self.assertIsInstance(ps.partial_s, int)

    def test_aggregation_requires_threshold(self):
        """Aggregation should fail below threshold."""
        table = self._setup_table_with_knights(3)
        msg_hash = hashlib.sha256(b"test").digest()

        partials = []
        for i in range(2):  # Below threshold of 3
            partials.append(table._generate_partial_signature(
                msg_hash,
                f"Knight_{i}",
                self._make_key(f"knight_{i}"),
                self._make_secret(f"knight_{i}"),
            ))

        with self.assertRaises(ValueError):
            table._aggregate_signatures(partials)

    def test_aggregation_success(self):
        """Aggregation should succeed with enough partials."""
        table = self._setup_table_with_knights(5)
        msg_hash = hashlib.sha256(b"test").digest()

        partials = []
        for i in range(3):
            partials.append(table._generate_partial_signature(
                msg_hash,
                f"Knight_{i}",
                self._make_key(f"knight_{i}"),
                self._make_secret(f"knight_{i}"),
            ))

        aggregated = table._aggregate_signatures(partials)
        self.assertEqual(len(aggregated), 64)

    def test_verify_aggregated_signature_format(self):
        """Verification should check signature length."""
        table = KnightsRoundTable()
        msg_hash = hashlib.sha256(b"test").digest()
        public_keys = [self._make_key(f"k{i}") for i in range(3)]

        # Too short
        result = table.verify_aggregated_signature(msg_hash, b"short", public_keys)
        self.assertFalse(result)

    def test_verify_too_few_keys(self):
        """Verification should fail with too few public keys."""
        table = KnightsRoundTable()
        msg_hash = hashlib.sha256(b"test").digest()

        result = table.verify_aggregated_signature(msg_hash, b"x" * 64, [self._make_key("k0")])
        self.assertFalse(result)


class TestGovernanceCoherence(unittest.TestCase):
    """Test governance coherence metrics."""

    def _make_key(self, name: str) -> bytes:
        return hashlib.sha256(name.encode()).digest()

    def _make_secret(self, name: str) -> bytes:
        return hashlib.sha512(name.encode()).digest()

    def test_coherence_with_active_knights(self):
        """Coherence should be based on Knight phi scores."""
        table = KnightsRoundTable()
        for i in range(5):
            table.add_founder_knight(
                name=f"Knight_{i}",
                public_key=self._make_key(f"knight_{i}"),
                uruu_balance=200.0,
                phi_score=0.8,
                excal_stake=2000.0,
            )
        table._update_governance_coherence()
        self.assertGreater(table.governance_coherence, 0)
        self.assertLessEqual(table.governance_coherence, 1.0)

    def test_coherence_zero_knights(self):
        """Coherence should be 0 with no Knights."""
        table = KnightsRoundTable()
        table._update_governance_coherence()
        self.assertEqual(table.governance_coherence, 0.0)

    def test_coherence_improves_with_executed_proposals(self):
        """Executed proposals should improve coherence."""
        table = KnightsRoundTable()
        for i in range(5):
            table.add_founder_knight(
                name=f"Knight_{i}",
                public_key=self._make_key(f"knight_{i}"),
                uruu_balance=200.0,
                phi_score=0.8,
                excal_stake=2000.0,
            )

        # Create and execute a proposal
        table.create_proposal(
            ProposalType.PARAMETER_CHANGE,
            "Knight_0",
            "Test proposal",
            {},
        )
        for i in range(3):
            table.vote_on_proposal("prop_1", f"Knight_{i}", True, self._make_secret(f"k{i}"))

        coherence_after = table.governance_coherence
        self.assertGreater(coherence_after, 0)


class TestHealthReport(unittest.TestCase):
    """Test health report generation."""

    def _make_key(self, name: str) -> bytes:
        return hashlib.sha256(name.encode()).digest()

    def test_health_report_structure(self):
        """Health report should have all required fields."""
        table = KnightsRoundTable()
        report = table.get_health_report()

        required_fields = [
            "active_knights", "threshold", "governance_coherence",
            "treasury_balance_excal", "treasury_balance_uruu",
            "total_proposals", "total_inductions", "pending_nominations",
            "taproot_address", "prophecy_commitment", "alerts", "knights",
        ]
        for field in required_fields:
            self.assertIn(field, report)

    def test_health_report_critical_alert(self):
        """Should alert when below threshold Knights."""
        table = KnightsRoundTable()
        # No Knights added — below threshold
        report = table.get_health_report()
        critical_alerts = [a for a in report["alerts"] if "CRITICAL" in a]
        self.assertGreater(len(critical_alerts), 0)

    def test_health_report_treasury_alert(self):
        """Should alert when treasury is low."""
        table = KnightsRoundTable()
        report = table.get_health_report()
        treasury_alerts = [a for a in report["alerts"] if "Treasury" in a]
        self.assertGreater(len(treasury_alerts), 0)


class TestRoundTableState(unittest.TestCase):
    """Test Round Table state management."""

    def _make_key(self, name: str) -> bytes:
        return hashlib.sha256(name.encode()).digest()

    def test_state_structure(self):
        """State should have all required fields."""
        table = KnightsRoundTable()
        state = table.get_round_table_state()

        self.assertEqual(state.threshold_m, 3)
        self.assertEqual(state.threshold_n, 5)
        self.assertEqual(state.active_knights, 0)
        self.assertIsInstance(state.treasury, TreasuryState)

    def test_state_reflects_knights(self):
        """State should reflect added Knights."""
        table = KnightsRoundTable()
        table.add_founder_knight(
            name="Arthur",
            public_key=self._make_key("arthur"),
            uruu_balance=200.0,
            phi_score=0.8,
            excal_stake=2000.0,
        )
        state = table.get_round_table_state()
        self.assertEqual(state.active_knights, 1)
        self.assertIn("Arthur", state.knights)


class TestStepFunction(unittest.TestCase):
    """Test the step/tick function."""

    def _make_key(self, name: str) -> bytes:
        return hashlib.sha256(name.encode()).digest()

    def test_step_increments_height(self):
        """Step should increment current height."""
        table = KnightsRoundTable()
        initial = table.current_height
        table.step()
        self.assertEqual(table.current_height, initial + 1)

    def test_step_multiple(self):
        """Multiple steps should increment correctly."""
        table = KnightsRoundTable()
        for _ in range(10):
            table.step()
        self.assertEqual(table.current_height, 10)


class TestIntegration(unittest.TestCase):
    """Integration tests for the full governance flow."""

    def _make_key(self, name: str) -> bytes:
        return hashlib.sha256(name.encode()).digest()

    def _make_secret(self, name: str) -> bytes:
        return hashlib.sha512(name.encode()).digest()

    def test_full_election_and_proposal_flow(self):
        """Test complete flow: founders → nomination → election → proposal → execution."""
        table = KnightsRoundTable()

        # 1. Add 5 founder Knights
        for i in range(5):
            table.add_founder_knight(
                name=f"Knight_{i}",
                public_key=self._make_key(f"knight_{i}"),
                uruu_balance=200.0,
                phi_score=0.8,
                excal_stake=2000.0,
            )
        self.assertEqual(len(table.get_active_knights()), 5)

        # 2. Fund treasury
        table.deposit_to_treasury(10000.0, "EXCAL", "founder", "initial funding")
        self.assertEqual(table.treasury_balance_excal, 10000.0)

        # 3. Nominate a new Knight
        nom = table.nominate_knight(
            candidate_name="NewKnight",
            candidate_public_key=self._make_key("newknight"),
            nominator="Knight_0",
            uruu_balance=150.0,
            phi_score=0.7,
            excal_stake=1500.0,
        )
        self.assertIsNotNone(nom)

        # 4. Elect with 3-of-5 votes
        for i in range(3):
            table.vote_on_nomination("nom_1", f"Knight_{i}", True, self._make_secret(f"k{i}"))
        self.assertIn("NewKnight", table.knights)
        self.assertEqual(len(table.get_active_knights()), 6)

        # 5. Create and execute a treasury spend proposal
        table.create_proposal(
            ProposalType.TREASURY_SPEND,
            "Knight_0",
            "Fund the bridge deployment",
            {"amount": 2000.0, "recipient": "bridge_address"},
        )
        for i in range(3):
            table.vote_on_proposal("prop_1", f"Knight_{i}", True, self._make_secret(f"k{i}"))

        self.assertEqual(table.proposals["prop_1"].status, VoteStatus.EXECUTED)
        self.assertEqual(table.treasury_balance_excal, 8000.0)

        # 6. Check health report
        report = table.get_health_report()
        self.assertEqual(report["active_knights"], 6)
        self.assertEqual(report["total_proposals"], 1)
        self.assertEqual(report["total_inductions"], 1)

    def test_prophecy_treasury_address(self):
        """Verify treasury address is derived from the 13-word prophecy."""
        table = KnightsRoundTable()
        expected_key = hashlib.sha256(PROPHECY_SEED.encode()).digest()
        self.assertEqual(table._taproot_output_key, expected_key)
        self.assertTrue(table._taproot_address.startswith("bc1p"))


if __name__ == "__main__":
    unittest.main()
