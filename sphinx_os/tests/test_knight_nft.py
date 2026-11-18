"""Tests for Knight NFTs with ZK Rarity Proofs."""

import hashlib
import unittest
from sphinx_os.nexus.knight_nft import (
    KnightNFTMinter,
    KnightNFT,
    RarityTier,
    ZKRarityProof,
    ZKRarityEngine,
    generate_knight_traits,
    generate_nft_description,
)
from sphinx_os.nexus.ai_oracle_knight import OracleType
from sphinx_os.nexus.knights_round_table import PROPHECY_SEED


class TestRarityTier(unittest.TestCase):
    """Test rarity tier enum."""

    def test_ordering(self):
        """Test rarity tiers are ordered correctly."""
        self.assertLess(RarityTier.COMMON, RarityTier.RARE)
        self.assertLess(RarityTier.RARE, RarityTier.EPIC)
        self.assertLess(RarityTier.EPIC, RarityTier.LEGENDARY)
        self.assertLess(RarityTier.LEGENDARY, RarityTier.MYTHICAL)
        self.assertLess(RarityTier.MYTHICAL, RarityTier.TRANSCENDENT)

    def test_string_representation(self):
        """Test string representation."""
        self.assertEqual(str(RarityTier.MYTHICAL), "MYTHICAL")
        self.assertEqual(str(RarityTier.LEGENDARY), "LEGENDARY")


class TestZKRarityEngine(unittest.TestCase):
    """Test ZK rarity proof engine."""

    def setUp(self):
        self.prophecy_commitment = hashlib.sha256(PROPHECY_SEED.encode()).digest()
        self.engine = ZKRarityEngine(self.prophecy_commitment)

    def test_rarity_seed_generation(self):
        """Test rarity seed is deterministic."""
        seed1 = self.engine.generate_rarity_seed(RarityTier.MYTHICAL, 0)
        seed2 = self.engine.generate_rarity_seed(RarityTier.MYTHICAL, 0)
        self.assertEqual(seed1, seed2)
        self.assertEqual(len(seed1), 32)

    def test_different_rarity_different_seed(self):
        """Test different rarity produces different seed."""
        s1 = self.engine.generate_rarity_seed(RarityTier.MYTHICAL, 0)
        s2 = self.engine.generate_rarity_seed(RarityTier.LEGENDARY, 0)
        self.assertNotEqual(s1, s2)

    def test_trait_hash_generation(self):
        """Test trait hash is deterministic."""
        traits = {"name": "Test", "power": 100}
        h1 = self.engine.generate_trait_hash(traits)
        h2 = self.engine.generate_trait_hash(traits)
        self.assertEqual(h1, h2)

    def test_proof_generation(self):
        """Test proof generation."""
        traits = {"name": "Test-Knight", "power_level": 75}
        proof = self.engine.generate_proof(
            RarityTier.MYTHICAL, 0, traits, 1234567890.0
        )
        self.assertIsInstance(proof, ZKRarityProof)
        self.assertEqual(proof.rarity_tier, "MYTHICAL")
        self.assertEqual(len(proof.proof_hash), 64)  # SHA-256 hex

    def test_proof_verification(self):
        """Test proof verification succeeds for valid proof."""
        traits = {"name": "Test-Knight", "power_level": 75}
        proof = self.engine.generate_proof(
            RarityTier.MYTHICAL, 0, traits, 1234567890.0
        )
        self.assertTrue(self.engine.verify_proof(proof, traits))

    def test_proof_verification_fails_for_wrong_traits(self):
        """Test proof verification fails for wrong traits."""
        traits = {"name": "Test-Knight", "power_level": 75}
        wrong_traits = {"name": "Wrong-Knight", "power_level": 50}
        proof = self.engine.generate_proof(
            RarityTier.MYTHICAL, 0, traits, 1234567890.0
        )
        self.assertFalse(self.engine.verify_proof(proof, wrong_traits))


class TestKnightTraits(unittest.TestCase):
    """Test knight trait generation."""

    def test_mythical_traits(self):
        """Test mythical knight traits."""
        traits = generate_knight_traits(
            "Test-Oracle", RarityTier.MYTHICAL,
            OracleType.SENTINEL, 0.85, 200.0, 2000.0,
        )
        self.assertEqual(traits["rarity"], "MYTHICAL")
        self.assertEqual(traits["power_level"], 75)
        self.assertEqual(traits["aura"], "ethereal")
        self.assertEqual(traits["oracle_type"], "sentinel")
        self.assertEqual(traits["element"], "fire")

    def test_legendary_traits(self):
        """Test legendary king traits."""
        traits = generate_knight_traits(
            "King-Arthur", RarityTier.LEGENDARY,
            phi_score=1.0, uruu_balance=999999.0, excal_stake=999999.0,
        )
        self.assertEqual(traits["rarity"], "LEGENDARY")
        self.assertEqual(traits["power_level"], 100)
        self.assertEqual(traits["aura"], "divine")
        self.assertEqual(traits["weapon"], "excalibur")

    def test_oracle_elements(self):
        """Test each oracle type has unique element."""
        elements = set()
        for otype in OracleType:
            traits = generate_knight_traits(
                f"Test-{otype.name}", RarityTier.MYTHICAL, otype,
            )
            elements.add(traits["element"])
        self.assertEqual(len(elements), 5)  # 5 unique elements


class TestNFTDescription(unittest.TestCase):
    """Test NFT description generation."""

    def test_legendary_description(self):
        """Test legendary king description."""
        desc = generate_nft_description("King-Arthur", RarityTier.LEGENDARY)
        self.assertIn("Legendary King", desc)
        self.assertIn("Prophecy", desc)
        self.assertIn("Excalibur", desc)

    def test_oracle_description(self):
        """Test oracle knight description."""
        desc = generate_nft_description(
            "Sentinel-Alpha", RarityTier.MYTHICAL, OracleType.SENTINEL
        )
        self.assertIn("Mythical", desc)
        self.assertIn("MuSig2", desc)


class TestKnightNFTMinter(unittest.TestCase):
    """Test NFT minting engine."""

    def setUp(self):
        self.master_seed = hashlib.sha256(b"nft-test-seed").digest()
        self.minter = KnightNFTMinter(self.master_seed)

    def test_mint_full_collection(self):
        """Test minting the full collection of 13 NFTs."""
        nfts = self.minter.mint_full_collection()
        self.assertEqual(len(nfts), 13)

    def test_rarity_distribution(self):
        """Test rarity distribution: 12 Mythical + 1 Legendary."""
        nfts = self.minter.mint_full_collection()
        mythical = [n for n in nfts if n.rarity == RarityTier.MYTHICAL]
        legendary = [n for n in nfts if n.rarity == RarityTier.LEGENDARY]
        self.assertEqual(len(mythical), 12)
        self.assertEqual(len(legendary), 1)

    def test_king_is_13th(self):
        """Test the King is the 13th NFT."""
        nfts = self.minter.mint_full_collection()
        king = nfts[-1]
        self.assertEqual(king.rarity, RarityTier.LEGENDARY)
        self.assertIn("King", king.knight_name)

    def test_nft_has_zk_proof(self):
        """Test each NFT has a valid ZK proof."""
        nfts = self.minter.mint_full_collection()
        for nft in nfts:
            self.assertIsNotNone(nft.zk_proof)
            self.assertTrue(self.minter.zk_engine.verify_proof(nft.zk_proof, nft.traits))

    def test_nft_has_mint_hash(self):
        """Test each NFT has a mint hash."""
        nfts = self.minter.mint_full_collection()
        for nft in nfts:
            self.assertEqual(len(nft.mint_hash), 64)

    def test_unique_token_ids(self):
        """Test each NFT has a unique token ID."""
        nfts = self.minter.mint_full_collection()
        token_ids = [n.token_id for n in nfts]
        self.assertEqual(len(token_ids), len(set(token_ids)))

    def test_collection_summary(self):
        """Test collection summary."""
        nfts = self.minter.mint_full_collection()
        summary = self.minter.get_collection_summary()
        self.assertEqual(summary["total_minted"], 13)
        self.assertEqual(summary["rarity_distribution"]["MYTHICAL"], 12)
        self.assertEqual(summary["rarity_distribution"]["LEGENDARY"], 1)

    def test_nft_metadata(self):
        """Test NFT metadata retrieval."""
        nfts = self.minter.mint_full_collection()
        for nft in nfts:
            metadata = self.minter.get_nft_metadata(nft.token_id)
            self.assertIsNotNone(metadata)
            self.assertEqual(metadata["name"], nft.knight_name)
            self.assertEqual(metadata["rarity"], nft.rarity.name)

    def test_oracle_types_in_collection(self):
        """Test all 5 oracle types are represented."""
        nfts = self.minter.mint_full_collection()
        oracle_nfts = [n for n in nfts if n.oracle_type]
        types = set(n.oracle_type for n in oracle_nfts)
        self.assertEqual(len(types), 5)

    def test_king_traits(self):
        """Test King NFT has special traits."""
        nfts = self.minter.mint_full_collection()
        king = [n for n in nfts if n.rarity == RarityTier.LEGENDARY][0]
        self.assertEqual(king.traits["title"], "Sovereign King")
        self.assertEqual(king.traits["weapon"], "Excalibur")
        self.assertEqual(king.traits["prophecy_words"], 13)


if __name__ == "__main__":
    unittest.main()
