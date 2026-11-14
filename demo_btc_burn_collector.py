#!/usr/bin/env python3
"""demo_btc_burn_collector.py — BTC burn collector with real mempool data.

Fetches real BTC burns from mempool.space and runs the full pipeline.
Usage: python demo_btc_burn_collector.py [--real]
"""
import argparse
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sphinx_os.nexus.btc_burn_collector import BTCBurnCollector


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--real', action='store_true', help='Fetch real burns')
    args = parser.parse_args()

    print("\n" + "="*60)
    print("  BTC BURN COLLECTOR DEMO")
    print("="*60 + "\n")

    collector = BTCBurnCollector(seed=42)

    if args.real:
        print("Fetching real BTC burns from mempool.space...\n")
        report = collector.collect(use_real=True)
    else:
        print("Running simulated burns...\n")
        report = collector.simulate_burns(n=15)

    print(f"Burns processed: {report.total_burns}")
    print(f"Successful: {report.successful_collections}")
    print(f"Total BTC burned: {report.total_btc_burned:.6f}")
    print(f"Total EXCAL collected: {report.total_excal_collected:.2f}")
    print(f"Total BTC reclaimed: {report.total_btc_reclaimed:.6f}")
    print(f"Avg entanglement: {report.avg_entanglement:.4f}")
    print(f"Avg φ_QG: {report.avg_phi_qg:.4f}")


if __name__ == "__main__":
    main()
