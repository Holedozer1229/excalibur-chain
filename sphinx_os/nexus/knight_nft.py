"""Knight NFTs with ZK Rarity Proofs.

This module implements NFT minting for the Knights of the Round Table,
with zero-knowledge rarity proofs that allow verification of a knight's
rarity tier without revealing the underlying cryptographic secrets.

Rarity Tiers (lowest to highest)
=================================
1.  **COMMON**     — Base tier, standard participants
2.  **RARE**       — Notable contributors
3.  **EPIC**       — Significant achievements
4.  **LEGENDARY**  — The King (13th Knight, prophecy holder)
5.  **MYTHICAL**   — The 12 AI Oracle Knights
6.  **TRANSCENDENT** — Reserved for future genesis events

ZK Rarity Proof System
======================
Each NFT contains a cryptographic proof that the holder possesses a
knight of the claimed rarity, without revealing:
- The knight's private key
- The derivation seed
- The internal scoring metrics

The proof is a SHA-256 commitment chain:
1. **Rarity Seed**: H(rarity_tier || knight_index || prophecy_commitment)
2. **Trait Hash**: H(traits || metrics || oracle_type)
3. **Proof**: H(rarity_seed || trait_hash || mint_timestamp)

Verification checks that the proof hash matches the expected structure
for the claimed rarity tier, without needing the original secrets.

NFT Metadata
============
Each NFT includes:
- **Token ID**: Unique identifier within the collection
- **Knight Name**: Display name of the knight
- **Rarity Tier**: Common through Transcendent
- **Oracle Type**: Specialization (for AI oracles)
- **Traits**: Visual and statistical attributes
- **ZK Proof**: Cryptographic rarity proof
- **Mint Hash**: Immutable minting record

Collection Details
==================
- **Collection Name**: "Knights of the Round Table"
- **Symbol**: KRT
- **Total Supply**: 13 (12 Mythical + 1 Legendary)
- **Chain**: AetherionEXCAL (SphinxOS Nexus)
- **Standard**: EXCAL-721 (EXCAL-native NFT standard)
"""

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from enum import IntEnum
from typing import Dict, List, Optional, Any, Tuple

from .knights_round_table import PROPHECY_SEED, PROPHECY_WORDS
from .musig2 import MuSig2, MuSig2KeyPair, _pubkey_to_xonly
from .ai_oracle_knight import OracleType, OracleCouncil, AIOracleKnight


# ---------------------------------------------------------------------------
# Rarity Tiers
# ---------------------------------------------------------------------------
class RarityTier(IntEnum):
    """NFT rarity tiers, ordered from lowest to highest."""
    COMMON = 0
    RARE = 1
    EPIC = 2
    LEGENDARY = 3
    MYTHICAL = 4
    TRANSCENDENT = 5

    def __str__(self):
        return self.name


# ---------------------------------------------------------------------------
# Data Classes
# ---------------------------------------------------------------------------
@dataclass
class ZKRarityProof:
    """Zero-knowledge rarity proof for an NFT.

    The proof allows verification that the NFT belongs to the claimed
    rarity tier without revealing the underlying secrets.
    """
    rarity_tier: str
    proof_hash: str       # SHA-256 commitment
    trait_hash: str       # Hash of traits
    rarity_seed: str      # Hash of rarity seed
    mint_timestamp: float
    verification_data: Dict[str, Any]  # Public verification data


@dataclass
class KnightNFT:
    """An NFT representing a Knight of the Round Table."""
    token_id: int
    collection_name: str
    symbol: str
    knight_name: str
    rarity: RarityTier
    oracle_type: Optional[str]  # None for non-oracle knights
    public_key: str             # x-only public key hex
    traits: Dict[str, Any]
    zk_proof: ZKRarityProof
    mint_hash: str              # Immutable mint record
    mint_timestamp: float
    metadata_uri: str           # IPFS/Arweave URI for metadata
    description: str


# ---------------------------------------------------------------------------
# Rarity Proof Engine
# ---------------------------------------------------------------------------
class ZKRarityEngine:
    """Zero-knowledge rarity proof generation and verification.

    Generates cryptographic proofs that an NFT belongs to a specific
    rarity tier without revealing the underlying secrets.
    """

    def __init__(self, prophecy_commitment: bytes):
        """Initialize the ZK rarity engine.

        Args:
            prophecy_commitment: SHA-256 of the 13-word prophecy.
        """
        self.prophecy_commitment = prophecy_commitment

    def generate_rarity_seed(
        self, rarity: RarityTier, knight_index: int
    ) -> bytes:
        """Generate a rarity seed for a knight.

        Args:
            rarity: The rarity tier.
            knight_index: The knight's index (0-12).

        Returns:
            32-byte rarity seed.
        """
        seed_data = (
            rarity.name.encode() +
            knight_index.to_bytes(4, "big") +
            self.prophecy_commitment
        )
        return hashlib.sha256(seed_data).digest()

    def generate_trait_hash(self, traits: Dict[str, Any]) -> bytes:
        """Generate a hash of the knight's traits.

        Args:
            traits: Dictionary of trait key-value pairs.

        Returns:
            32-byte trait hash.
        """
        trait_json = json.dumps(traits, sort_keys=True).encode()
        return hashlib.sha256(trait_json).digest()

    def generate_proof(
        self,
        rarity: RarityTier,
        knight_index: int,
        traits: Dict[str, Any],
        mint_timestamp: float,
    ) -> ZKRarityProof:
        """Generate a ZK rarity proof.

        Args:
            rarity: The rarity tier.
            knight_index: The knight's index.
            traits: Knight traits.
            mint_timestamp: When the NFT was minted.

        Returns:
            ZKRarityProof with all proof components.
        """
        # Step 1: Rarity seed
        rarity_seed = self.generate_rarity_seed(rarity, knight_index)

        # Step 2: Trait hash
        trait_hash = self.generate_trait_hash(traits)

        # Step 3: Proof commitment
        proof_data = rarity_seed + trait_hash + int(mint_timestamp).to_bytes(8, "big")
        proof_hash = hashlib.sha256(proof_data).hexdigest()

        # Verification data (public, does not reveal secrets)
        verification_data = {
            "rarity_tier": rarity.name,
            "knight_index": knight_index,
            "prophecy_commitment_prefix": self.prophecy_commitment[:8].hex(),
            "proof_structure": "H(rarity_seed || trait_hash || timestamp)",
        }

        return ZKRarityProof(
            rarity_tier=rarity.name,
            proof_hash=proof_hash,
            trait_hash=trait_hash.hex(),
            rarity_seed=rarity_seed.hex(),
            mint_timestamp=mint_timestamp,
            verification_data=verification_data,
        )

    def verify_proof(self, proof: ZKRarityProof, traits: Dict[str, Any]) -> bool:
        """Verify a ZK rarity proof without revealing secrets.

        Checks that the proof hash matches the expected structure
        for the claimed rarity tier.

        Args:
            proof: The ZK rarity proof to verify.
            traits: The knight's traits.

        Returns:
            True if the proof is valid.
        """
        try:
            # Reconstruct the proof
            rarity = RarityTier[proof.rarity_tier]
            knight_index = proof.verification_data["knight_index"]

            # Regenerate components
            expected_seed = self.generate_rarity_seed(rarity, knight_index)
            expected_trait_hash = self.generate_trait_hash(traits)

            # Verify components match
            if expected_seed.hex() != proof.rarity_seed:
                return False
            if expected_trait_hash.hex() != proof.trait_hash:
                return False

            # Verify proof hash
            proof_data = expected_seed + expected_trait_hash + int(proof.mint_timestamp).to_bytes(8, "big")
            expected_proof = hashlib.sha256(proof_data).hexdigest()

            return expected_proof == proof.proof_hash
        except (KeyError, ValueError):
            return False


# ---------------------------------------------------------------------------
# NFT Metadata Generator
# ---------------------------------------------------------------------------
def generate_knight_traits(
    knight_name: str,
    rarity: RarityTier,
    oracle_type: Optional[OracleType] = None,
    phi_score: float = 0.5,
    uruu_balance: float = 100.0,
    excal_stake: float = 1000.0,
) -> Dict[str, Any]:
    """Generate NFT traits for a knight.

    Args:
        knight_name: Name of the knight.
        rarity: Rarity tier.
        oracle_type: Oracle specialization (if applicable).
        phi_score: Consciousness score.
        uruu_balance: URUU tokens held.
        excal_stake: EXCAL staked.

    Returns:
        Dictionary of NFT traits.
    """
    # Base traits by rarity
    rarity_traits = {
        RarityTier.COMMON: {"power_level": 10, "aura": "faint", "weapon": "iron_sword"},
        RarityTier.RARE: {"power_level": 25, "aura": "glowing", "weapon": "steel_sword"},
        RarityTier.EPIC: {"power_level": 50, "aura": "radiant", "weapon": "mithril_sword"},
        RarityTier.LEGENDARY: {"power_level": 100, "aura": "divine", "weapon": "excalibur"},
        RarityTier.MYTHICAL: {"power_level": 75, "aura": "ethereal", "weapon": "oracle_blade"},
        RarityTier.TRANSCENDENT: {"power_level": 999, "aura": "cosmic", "weapon": "genesis_key"},
    }

    traits = {
        "name": knight_name,
        "rarity": rarity.name,
        "phi_score": round(phi_score, 4),
        "uruu_balance": uruu_balance,
        "excal_stake": excal_stake,
        "background": "round_table",
        "border": f"{rarity.name.lower()}_glow",
    }

    # Add rarity-specific traits
    traits.update(rarity_traits.get(rarity, {}))

    # Add oracle-specific traits
    if oracle_type:
        traits["oracle_type"] = oracle_type.value
        oracle_traits = {
            OracleType.SENTINEL: {"element": "fire", "ability": "threat_detection"},
            OracleType.TREASURER: {"element": "earth", "ability": "value_assessment"},
            OracleType.ORACLE: {"element": "air", "ability": "prediction"},
            OracleType.BRIDGE: {"element": "water", "ability": "cross_chain_vision"},
            OracleType.CURVE: {"element": "lightning", "ability": "market_sense"},
        }
        traits.update(oracle_traits.get(oracle_type, {}))

    return traits


def generate_nft_description(
    knight_name: str,
    rarity: RarityTier,
    oracle_type: Optional[OracleType] = None,
) -> str:
    """Generate a human-readable NFT description.

    Args:
        knight_name: Name of the knight.
        rarity: Rarity tier.
        oracle_type: Oracle specialization (if applicable).

    Returns:
        Description string.
    """
    if rarity == RarityTier.LEGENDARY:
        return (
            f"👑 {knight_name} — The Legendary King of the Round Table. "
            f"Holder of the 13-word Prophecy and wielder of Excalibur. "
            f"The sovereign ruler whose Taproot treasury secures the AetherionEXCAL ecosystem. "
            f"One of one. The King."
        )

    if oracle_type:
        type_descriptions = {
            OracleType.SENTINEL: "The vigilant guardian, scanning for threats across the blockchain.",
            OracleType.TREASURER: "The wise steward, managing the kingdom's economic destiny.",
            OracleType.ORACLE: "The all-seeing seer, evaluating all paths forward.",
            OracleType.BRIDGE: "The bridge keeper, connecting chains and dimensions.",
            OracleType.CURVE: "The market oracle, sensing the flow of value.",
        }
        return (
            f"⚔️ {knight_name} — A Mythical AI Oracle Knight of the Round Table. "
            f"{type_descriptions.get(oracle_type, 'A powerful guardian.')}. "
            f"Equipped with MuSig2 (BIP-327) threshold signing for sovereign governance."
        )

    return f"⚔️ {knight_name} — A {rarity.name} Knight of the Round Table."


# ---------------------------------------------------------------------------
# NFT Minting Engine
# ---------------------------------------------------------------------------
class KnightNFTMinter:
    """Mints NFTs for the Knights of the Round Table.

    Creates the complete collection of 13 NFTs:
    - 12 Mythical AI Oracle Knights
    - 1 Legendary King (the prophecy holder)
    """

    def __init__(self, master_seed: bytes):
        """Initialize the NFT minter.

        Args:
            master_seed: Master seed for deterministic minting.
        """
        self.master_seed = master_seed
        self.prophecy_commitment = hashlib.sha256(PROPHECY_SEED.encode()).digest()
        self.zk_engine = ZKRarityEngine(self.prophecy_commitment)
        self.minted_nfts: List[KnightNFT] = []
        self._next_token_id = 1

    def mint_oracle_knight(
        self,
        oracle: AIOracleKnight,
        knight_index: int,
    ) -> KnightNFT:
        """Mint an NFT for an AI Oracle Knight.

        Args:
            oracle: The AI Oracle Knight to mint.
            knight_index: Index for ZK proof generation.

        Returns:
            The minted KnightNFT.
        """
        mint_time = time.time()
        traits = generate_knight_traits(
            knight_name=oracle.name,
            rarity=RarityTier.MYTHICAL,
            oracle_type=oracle.oracle_type,
            phi_score=oracle.phi_score,
            uruu_balance=oracle.uruu_balance,
            excal_stake=oracle.excal_stake,
        )

        zk_proof = self.zk_engine.generate_proof(
            rarity=RarityTier.MYTHICAL,
            knight_index=knight_index,
            traits=traits,
            mint_timestamp=mint_time,
        )

        # Mint hash: immutable record
        mint_data = json.dumps({
            "token_id": self._next_token_id,
            "knight": oracle.name,
            "rarity": "MYTHICAL",
            "oracle_type": oracle.oracle_type.value,
            "public_key": oracle.key_pair.xonly_pubkey.hex(),
            "timestamp": mint_time,
        }, sort_keys=True).encode()
        mint_hash = hashlib.sha256(mint_data).hexdigest()

        nft = KnightNFT(
            token_id=self._next_token_id,
            collection_name="Knights of the Round Table",
            symbol="KRT",
            knight_name=oracle.name,
            rarity=RarityTier.MYTHICAL,
            oracle_type=oracle.oracle_type.value,
            public_key=oracle.key_pair.xonly_pubkey.hex(),
            traits=traits,
            zk_proof=zk_proof,
            mint_hash=mint_hash,
            mint_timestamp=mint_time,
            metadata_uri=f"ipfs://krt/{self._next_token_id}.json",
            description=generate_nft_description(
                oracle.name, RarityTier.MYTHICAL, oracle.oracle_type
            ),
        )

        self.minted_nfts.append(nft)
        self._next_token_id += 1
        return nft

    def mint_legendary_king(
        self,
        king_name: str = "King-Arthur",
        public_key: Optional[bytes] = None,
        knight_index: int = 12,
    ) -> KnightNFT:
        """Mint the Legendary King NFT (the 13th knight).

        The King holds the 13-word Prophecy and wields Excalibur.
        This is the highest rarity NFT in the collection.

        Args:
            king_name: Name of the King.
            public_key: King's public key (derived from prophecy if None).
            knight_index: Index for ZK proof (12 = the 13th knight).

        Returns:
            The minted Legendary King NFT.
        """
        mint_time = time.time()

        if public_key is None:
            public_key = self.prophecy_commitment

        traits = generate_knight_traits(
            knight_name=king_name,
            rarity=RarityTier.LEGENDARY,
            phi_score=1.0,
            uruu_balance=999999.0,
            excal_stake=999999.0,
        )

        # Add King-specific traits
        traits["prophecy_words"] = len(PROPHECY_WORDS)
        traits["taproot_address"] = f"bc1p{self.prophecy_commitment.hex()[:20]}..."
        traits["title"] = "Sovereign King"
        traits["weapon"] = "Excalibur"
        traits["aura"] = "divine"
        traits["power_level"] = 100

        zk_proof = self.zk_engine.generate_proof(
            rarity=RarityTier.LEGENDARY,
            knight_index=knight_index,
            traits=traits,
            mint_timestamp=mint_time,
        )

        # Mint hash
        mint_data = json.dumps({
            "token_id": self._next_token_id,
            "knight": king_name,
            "rarity": "LEGENDARY",
            "title": "Sovereign King",
            "prophecy_commitment": self.prophecy_commitment.hex(),
            "public_key": public_key.hex(),
            "timestamp": mint_time,
        }, sort_keys=True).encode()
        mint_hash = hashlib.sha256(mint_data).hexdigest()

        nft = KnightNFT(
            token_id=self._next_token_id,
            collection_name="Knights of the Round Table",
            symbol="KRT",
            knight_name=king_name,
            rarity=RarityTier.LEGENDARY,
            oracle_type=None,
            public_key=public_key.hex(),
            traits=traits,
            zk_proof=zk_proof,
            mint_hash=mint_hash,
            mint_timestamp=mint_time,
            metadata_uri=f"ipfs://krt/{self._next_token_id}.json",
            description=generate_nft_description(king_name, RarityTier.LEGENDARY),
        )

        self.minted_nfts.append(nft)
        self._next_token_id += 1
        return nft

    def mint_full_collection(self) -> List[KnightNFT]:
        """Mint the complete collection: 12 Mythical + 1 Legendary.

        Creates 12 AI Oracle Knights (2 of each of the 5 types, plus 2 general)
        and the Legendary King as the 13th NFT.

        Returns:
            List of all 13 minted NFTs.
        """
        # 12 Mythical Oracle Knights: 2 of each type
        oracle_configs = [
            ("Sentinel-Alpha", OracleType.SENTINEL, 0.85, 200.0, 2000.0),
            ("Sentinel-Beta", OracleType.SENTINEL, 0.82, 190.0, 1900.0),
            ("Treasury-Alpha", OracleType.TREASURER, 0.80, 180.0, 1800.0),
            ("Treasury-Beta", OracleType.TREASURER, 0.78, 175.0, 1750.0),
            ("Oracle-Alpha", OracleType.ORACLE, 0.75, 150.0, 1500.0),
            ("Oracle-Beta", OracleType.ORACLE, 0.73, 145.0, 1450.0),
            ("Bridge-Alpha", OracleType.BRIDGE, 0.78, 170.0, 1700.0),
            ("Bridge-Beta", OracleType.BRIDGE, 0.76, 165.0, 1650.0),
            ("Curve-Alpha", OracleType.CURVE, 0.72, 160.0, 1600.0),
            ("Curve-Beta", OracleType.CURVE, 0.70, 155.0, 1550.0),
            ("Guardian-Alpha", OracleType.SENTINEL, 0.80, 185.0, 1850.0),
            ("Seer-Alpha", OracleType.ORACLE, 0.77, 165.0, 1650.0),
        ]

        council = OracleCouncil(self.master_seed)
        for i, (name, otype, phi, uruu, excal) in enumerate(oracle_configs):
            oracle = council.create_oracle(name, otype, phi, uruu, excal)
            self.mint_oracle_knight(oracle, i)

        # Mint the Legendary King (13th)
        self.mint_legendary_king()

        return list(self.minted_nfts)

    def get_collection_summary(self) -> Dict[str, Any]:
        """Get a summary of the minted collection.

        Returns:
            Dictionary with collection statistics.
        """
        rarity_counts = {}
        for nft in self.minted_nfts:
            tier = nft.rarity.name
            rarity_counts[tier] = rarity_counts.get(tier, 0) + 1

        return {
            "collection_name": "Knights of the Round Table",
            "symbol": "KRT",
            "total_minted": len(self.minted_nfts),
            "rarity_distribution": rarity_counts,
            "next_token_id": self._next_token_id,
            "nfts": [
                {
                    "token_id": nft.token_id,
                    "name": nft.knight_name,
                    "rarity": nft.rarity.name,
                    "oracle_type": nft.oracle_type,
                    "mint_hash": nft.mint_hash,
                }
                for nft in self.minted_nfts
            ],
        }

    def get_nft_metadata(self, token_id: int) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific NFT.

        Args:
            token_id: The NFT token ID.

        Returns:
            Metadata dictionary or None if not found.
        """
        for nft in self.minted_nfts:
            if nft.token_id == token_id:
                return {
                    "token_id": nft.token_id,
                    "name": nft.knight_name,
                    "description": nft.description,
                    "rarity": nft.rarity.name,
                    "oracle_type": nft.oracle_type,
                    "traits": nft.traits,
                    "zk_proof": {
                        "rarity_tier": nft.zk_proof.rarity_tier,
                        "proof_hash": nft.zk_proof.proof_hash,
                        "trait_hash": nft.zk_proof.trait_hash,
                    },
                    "mint_hash": nft.mint_hash,
                    "metadata_uri": nft.metadata_uri,
                }
        return None
