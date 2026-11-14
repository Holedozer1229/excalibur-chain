"""BTC Burn Collector — Full pipeline: burn → wormhole → EXCAL → BTC swap.

Unifies the full pipeline: BTC burn detection → quantum wormhole mapping →
EXCAL collection on bonding curve → quantum atomic swap back to BTC.
"""

import hashlib
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np

from sphinx_os.nexus.btc_burn_wormhole import BTCBurnWormhole, BurnTransaction, BurnWormholeEvent
from sphinx_os.nexus.quantum_atomic_swap import QuantumAtomicSwap, AtomicSwap
from sphinx_os.nexus.deutsch_ctc_oracle import SphinxQOracle


@dataclass
class CollectionResult:
    """Result of a single burn collection."""
    burn: BurnTransaction
    wormhole_event: BurnWormholeEvent
    excal_collected: float
    swap: Optional[AtomicSwap]
    btc_reclaimed: float
    ctc_validated: bool
    error: Optional[str] = None


@dataclass
class CollectionReport:
    """Summary report of burn collection run."""
    total_burns: int
    successful_collections: int
    total_btc_burned: float
    total_excal_collected: float
    total_btc_reclaimed: float
    avg_entanglement: float
    avg_phi_qg: float
    results: List[CollectionResult] = field(default_factory=list)


class BTCBurnCollector:
    """Full BTC burn collection pipeline.

    Args:
        burn_addresses: List of burn addresses to monitor.
        btc_claim_address: BTC address for reclaimed coins.
        seed: Random seed for reproducibility.
    """

    def __init__(self, burn_addresses: Optional[List[str]] = None,
                 btc_claim_address: Optional[str] = None,
                 seed: Optional[int] = None):
        self.burn_wormhole = BTCBurnWormhole(burn_addresses, seed=seed)
        self.atomic_swap = QuantumAtomicSwap(seed=seed)
        self.oracle = SphinxQOracle()
        self.btc_claim_address = btc_claim_address or "1ClaimAddressXXXXXXXXXXXXXXXXX"
        self.results: List[CollectionResult] = []
        self.rng = np.random.RandomState(seed)

    def collect(self, use_real: bool = False) -> CollectionReport:
        """Run the full collection pipeline.

        Args:
            use_real: If True, fetch real burns from mempool.space.

        Returns:
            CollectionReport with summary.
        """
        # Fetch burns
        if use_real:
            burns = self.burn_wormhole.fetch_burns()
        else:
            burns = self._generate_simulated_burns(10)

        self.results = []
        entanglements = []
        phi_qgs = []

        for burn in burns:
            try:
                # Map to wormhole
                event = self.burn_wormhole.map_to_wormhole(burn)
                if event is None:
                    self.results.append(CollectionResult(
                        burn=burn, wormhole_event=None, excal_collected=0,
                        swap=None, btc_reclaimed=0, ctc_validated=False,
                        error="No wormhole formed"
                    ))
                    continue

                # Collect EXCAL
                excal = self.burn_wormhole.collect_excal(event)

                # CTC validate
                ctc_valid = self._ctc_validate(burn, event)

                # Atomic swap back to BTC
                seed_bytes = hashlib.sha256(burn.txid.encode()).digest()
                swap = self.atomic_swap.create_swap(
                    excal_amount=excal,
                    btc_amount=burn.amount_btc,
                    seed_bytes=seed_bytes,
                    claim_address=self.btc_claim_address,
                )
                success, msg = self.atomic_swap.execute_swap(swap.swap_id)

                btc_reclaimed = burn.amount_btc if success else 0

                self.results.append(CollectionResult(
                    burn=burn,
                    wormhole_event=event,
                    excal_collected=excal,
                    swap=swap if success else None,
                    btc_reclaimed=btc_reclaimed,
                    ctc_validated=ctc_valid,
                ))

                entanglements.append(event.wormhole.entanglement_entropy)
                metrics = self.burn_wormhole.fabric.get_quantum_gravity_metrics()
                phi_qgs.append(metrics.phi_qg)

            except Exception as e:
                self.results.append(CollectionResult(
                    burn=burn, wormhole_event=None, excal_collected=0,
                    swap=None, btc_reclaimed=0, ctc_validated=False,
                    error=str(e)
                ))

        successful = [r for r in self.results if r.error is None]
        return CollectionReport(
            total_burns=len(burns),
            successful_collections=len(successful),
            total_btc_burned=sum(r.burn.amount_btc for r in self.results),
            total_excal_collected=sum(r.excal_collected for r in self.results),
            total_btc_reclaimed=sum(r.btc_reclaimed for r in self.results),
            avg_entanglement=np.mean(entanglements) if entanglements else 0,
            avg_phi_qg=np.mean(phi_qgs) if phi_qgs else 0,
            results=self.results,
        )

    def simulate_burns(self, n: int = 10) -> CollectionReport:
        """Run with simulated burns.

        Args:
            n: Number of simulated burns.

        Returns:
            CollectionReport.
        """
        burns = self._generate_simulated_burns(n)
        self.results = []
        entanglements = []
        phi_qgs = []

        for burn in burns:
            event = self.burn_wormhole.map_to_wormhole(burn)
            if event is None:
                continue
            excal = self.burn_wormhole.collect_excal(event)
            ctc_valid = self._ctc_validate(burn, event)

            seed_bytes = hashlib.sha256(burn.txid.encode()).digest()
            swap = self.atomic_swap.create_swap(
                excal_amount=excal, btc_amount=burn.amount_btc,
                seed_bytes=seed_bytes, claim_address=self.btc_claim_address,
            )
            success, _ = self.atomic_swap.execute_swap(swap.swap_id)

            self.results.append(CollectionResult(
                burn=burn, wormhole_event=event, excal_collected=excal,
                swap=swap if success else None,
                btc_reclaimed=burn.amount_btc if success else 0,
                ctc_validated=ctc_valid,
            ))
            entanglements.append(event.wormhole.entanglement_entropy)
            metrics = self.burn_wormhole.fabric.get_quantum_gravity_metrics()
            phi_qgs.append(metrics.phi_qg)

        successful = [r for r in self.results if r.error is None]
        return CollectionReport(
            total_burns=len(burns),
            successful_collections=len(successful),
            total_btc_burned=sum(r.burn.amount_btc for r in self.results),
            total_excal_collected=sum(r.excal_collected for r in self.results),
            total_btc_reclaimed=sum(r.btc_reclaimed for r in self.results),
            avg_entanglement=np.mean(entanglements) if entanglements else 0,
            avg_phi_qg=np.mean(phi_qgs) if phi_qgs else 0,
            results=self.results,
        )

    def get_report(self) -> CollectionReport:
        """Get report from last collection run."""
        successful = [r for r in self.results if r.error is None]
        return CollectionReport(
            total_burns=len(self.results),
            successful_collections=len(successful),
            total_btc_burned=sum(r.burn.amount_btc for r in self.results),
            total_excal_collected=sum(r.excal_collected for r in self.results),
            total_btc_reclaimed=sum(r.btc_reclaimed for r in self.results),
            avg_entanglement=0,
            avg_phi_qg=0,
            results=self.results,
        )

    def _ctc_validate(self, burn: BurnTransaction,
                      event: BurnWormholeEvent) -> bool:
        """Validate burn through Deutsch CTC oracle."""
        candidates = ["VALID", "INVALID"]
        verify = lambda c: c == "VALID" and burn.amount_btc > 0
        probs, has_valid = self.oracle.compute_distribution(candidates, verify)
        return has_valid

    def _generate_simulated_burns(self, n: int) -> List[BurnTransaction]:
        """Generate simulated burn transactions for testing."""
        burns = []
        for i in range(n):
            txid = hashlib.sha256(f"sim_burn_{i}".encode()).hexdigest()
            sats = self.rng.randint(1000, 100000)
            burns.append(BurnTransaction(
                txid=txid,
                address=self.burn_wormhole.burn_addresses[i % len(self.burn_wormhole.burn_addresses)],
                amount_btc=sats / 100_000_000,
                amount_sats=sats,
            ))
        return burns
