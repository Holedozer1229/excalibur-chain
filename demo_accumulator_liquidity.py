#!/usr/bin/env python3
"""demo_accumulator_liquidity.py — Accumulate burns then create liquidity pool.

Accumulates BTC burns to a target, creates EXCAL liquidity pool, trades.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sphinx_os.nexus.btc_accumulator import BTCAccumulator
from sphinx_os.nexus.excal_liquidity_pool import EXCALLiquidityPool


def on_progress(progress):
    if progress.cycle % 5 == 0:
        print(f"  Cycle {progress.cycle}: {progress.btc_accumulated:.6f} BTC "
              f"({progress.percentage:.1f}%)")


def main():
    print("\n" + "="*60)
    print("  ACCUMULATOR + LIQUIDITY POOL DEMO")
    print("="*60 + "\n")

    # Accumulate
    print("Accumulating BTC burns...")
    acc = BTCAccumulator(target_btc=0.001, seed=42)
    report = acc.accumulate(use_real=False, callback=on_progress, max_cycles=50)

    prog = acc.get_progress()
    print(f"\nAccumulated: {prog.btc_accumulated:.6f} BTC in {prog.cycle} cycles")
    print(f"EXCAL collected: {prog.excal_collected:.2f}")

    # Create liquidity pool
    print("\nCreating liquidity pool...")
    pool = EXCALLiquidityPool(seed=42)
    stats = pool.create_pool(excal_amount=prog.excal_collected,
                             btc_amount=prog.btc_accumulated)
    print(f"EXCAL reserve: {stats.excal_reserve:.2f}")
    print(f"URUU supply: {stats.uruu_supply:.0f}")
    print(f"Price: {stats.price_excal_per_uruu:.4f} EXCAL/URUU")

    # Sample trades
    print("\nExecuting sample trades...")
    for i in range(5):
        trade = pool.trade(1000, 'BUY')
        if trade:
            print(f"  BUY: {trade.excal_traded:.0f} EXCAL → {trade.uruu_traded:.2f} URUU")

    final = pool.get_stats()
    print(f"\nFinal liquidity score: {final.liquidity_score:.2f}")


if __name__ == "__main__":
    main()
