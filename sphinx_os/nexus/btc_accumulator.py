"""BTC Accumulator — Continuous burn collection until target BTC reached.

Runs cycles of BTC burn collection until a target BTC threshold is reached,
with progress tracking and callbacks.
"""

import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import numpy as np

from sphinx_os.nexus.btc_burn_collector import BTCBurnCollector, CollectionReport


@dataclass
class AccumulationProgress:
    """Progress report for BTC accumulation."""
    cycle: int
    btc_accumulated: float
    btc_target: float
    percentage: float
    excal_collected: float
    burns_processed: int
    elapsed_seconds: float


class BTCAccumulator:
    """Continuous BTC burn accumulator.

    Args:
        target_btc: Target BTC to accumulate (default 1.0).
        btc_claim_address: BTC address for reclaimed coins.
        seed: Random seed for reproducibility.
    """

    def __init__(self, target_btc: float = 1.0,
                 btc_claim_address: Optional[str] = None,
                 seed: Optional[int] = None):
        self.target_btc = target_btc
        self.collector = BTCBurnCollector(
            btc_claim_address=btc_claim_address, seed=seed
        )
        self.btc_accumulated = 0.0
        self.excal_collected = 0.0
        self.cycles = 0
        self.paused = False
        self.stopped = False
        self.progress_history: List[AccumulationProgress] = []
        self.rng = np.random.RandomState(seed)

    def accumulate(self, use_real: bool = False,
                   callback: Optional[Callable[[AccumulationProgress], None]] = None,
                   max_cycles: int = 1000) -> CollectionReport:
        """Accumulate BTC burns until target is reached.

        Args:
            use_real: If True, fetch real burns from mempool.space.
            callback: Optional callback for progress updates.
            max_cycles: Maximum cycles before stopping.

        Returns:
            Final CollectionReport.
        """
        start_time = time.time()
        last_report = None

        while self.btc_accumulated < self.target_btc and not self.stopped:
            if self.paused:
                time.sleep(1)
                continue

            if self.cycles >= max_cycles:
                break

            # Run collection cycle
            if use_real:
                report = self.collector.collect(use_real=True)
            else:
                report = self.collector.simulate_burns(n=10)

            last_report = report
            self.btc_accumulated += report.total_btc_reclaimed
            self.excal_collected += report.total_excal_collected
            self.cycles += 1

            # Progress update
            elapsed = time.time() - start_time
            progress = AccumulationProgress(
                cycle=self.cycles,
                btc_accumulated=self.btc_accumulated,
                btc_target=self.target_btc,
                percentage=min(100.0, (self.btc_accumulated / self.target_btc) * 100),
                excal_collected=self.excal_collected,
                burns_processed=report.successful_collections,
                elapsed_seconds=elapsed,
            )
            self.progress_history.append(progress)

            if callback:
                callback(progress)

            # Small delay between cycles
            if not use_real:
                time.sleep(0.01)

        return last_report or CollectionReport(
            total_burns=0, successful_collections=0,
            total_btc_burned=0, total_excal_collected=0,
            total_btc_reclaimed=0, avg_entanglement=0, avg_phi_qg=0,
        )

    def pause(self) -> None:
        """Pause accumulation."""
        self.paused = True

    def stop(self) -> None:
        """Stop accumulation."""
        self.stopped = True

    def get_progress(self) -> AccumulationProgress:
        """Get current progress."""
        return AccumulationProgress(
            cycle=self.cycles,
            btc_accumulated=self.btc_accumulated,
            btc_target=self.target_btc,
            percentage=min(100.0, (self.btc_accumulated / self.target_btc) * 100),
            excal_collected=self.excal_collected,
            burns_processed=0,
            elapsed_seconds=0,
        )
