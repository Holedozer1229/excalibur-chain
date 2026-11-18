"""Pirate Burn Claim — Capture value from anyone's Bitcoin burns.

Scans the mempool for Bitcoin burns and claims the scarcity value they create
via EXCAL minting on the bonding curve. Every burn TXID is a deterministic seed
that derives a "treasure chest" wallet — the first to detect and claim wins.
"""

import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from sphinx_os.nexus.btc_burn_wormhole import BTCBurnWormhole, BurnTransaction, BURN_ADDRESSES
from sphinx_os.nexus.deutsch_ctc_oracle import SphinxQOracle
from sphinx_os.nexus.bonding_curve import CustomBondingCurve as BondingCurve


@dataclass
class PirateClaim:
    """A pirate burn claim."""
    burn: BurnTransaction
    wormhole_wallet_address: str
    excal_minted: float
    ctc_validated: bool
    claim_txid: str


@dataclass
class PirateSummary:
    """Summary of pirate burn claims."""
    total_burns_scanned: int
    total_claims: int
    total_excal_minted: float
    ctc_success_rate: float
    claims: List[PirateClaim] = field(default_factory=list)


class PirateBurnClaim:
    """Pirate burn claim engine for capturing burn scarcity value.

    Args:
        collection_address: BTC address for the collection wallet.
        seed: Random seed for reproducibility.
    """

    def __init__(self, collection_address: Optional[str] = None,
                 seed: Optional[int] = None):
        self.burn_monitor = BTCBurnWormhole(seed=seed)
        self.oracle = SphinxQOracle()
        self.curve = BondingCurve()
        self.collection_address = collection_address or "1PirateClaimXXXXXXXXXXXXXXXX"
        self.claims: List[PirateClaim] = []
        self.rng = np.random.RandomState(seed)

    def scan_mempool(self) -> List[BurnTransaction]:
        """Scan mempool for burn transactions.

        Returns:
            List of burn transactions found.
        """
        return self.burn_monitor.fetch_burns()

    def derive_wormhole_wallet(self, txid: str) -> str:
        """Derive a deterministic wormhole wallet from a burn TXID.

        The same TXID always produces the same wallet address.

        Args:
            txid: Burn transaction ID.

        Returns:
            Derived wallet address.
        """
        seed = hashlib.sha256(txid.encode()).digest()
        pub_hash = hashlib.sha256(seed + b'wormhole').digest()
        ripemd = hashlib.new('ripemd160', pub_hash).digest()

        # Base58Check encode
        BASE58 = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
        version = bytes([0x00])
        checksum = hashlib.sha256(hashlib.sha256(version + ripemd).digest()).digest()[:4]
        payload = version + ripemd + checksum

        num = int.from_bytes(payload, 'big')
        result = []
        while num > 0:
            num, rem = divmod(num, 58)
            result.append(BASE58[rem])
        for b in payload:
            if b == 0:
                result.append('1')
            else:
                break

        return ''.join(reversed(result))

    def claim_burn(self, burn: BurnTransaction) -> Optional[PirateClaim]:
        """Claim value from a burn transaction.

        Args:
            burn: The burn transaction to claim.

        Returns:
            PirateClaim or None if claim failed.
        """
        # Derive wormhole wallet
        wallet_address = self.derive_wormhole_wallet(burn.txid)

        # Mint EXCAL from burn proof (1000 EXCAL per sat)
        excal_minted = burn.amount_sats * 1000.0
        self.curve.add_liquidity(excal_minted)

        # CTC validate
        candidates = ["CLAIM", "SKIP"]
        verify = lambda c: c == "CLAIM" and burn.amount_btc > 0
        probs, has_valid = self.oracle.compute_distribution(candidates, verify)

        # Generate claim TXID
        claim_txid = hashlib.sha256(
            f"pirate_claim_{burn.txid}_{wallet_address}".encode()
        ).hexdigest()

        claim = PirateClaim(
            burn=burn,
            wormhole_wallet_address=wallet_address,
            excal_minted=excal_minted,
            ctc_validated=has_valid,
            claim_txid=claim_txid,
        )
        self.claims.append(claim)
        return claim

    def get_summary(self) -> PirateSummary:
        """Get summary of all claims.

        Returns:
            PirateSummary.
        """
        ctc_valid = len([c for c in self.claims if c.ctc_validated])
        return PirateSummary(
            total_burns_scanned=len(self.claims),
            total_claims=len(self.claims),
            total_excal_minted=sum(c.excal_minted for c in self.claims),
            ctc_success_rate=ctc_valid / len(self.claims) if self.claims else 0,
            claims=self.claims,
        )
