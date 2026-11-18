#!/usr/bin/env python3
"""demo_wallet_btc_collector.py — Wallet-based BTC burn collector.

Generates a wallet, fetches real burns, collects EXCAL, swaps to BTC.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sphinx_os.nexus.btc_wallet_generator import BTCWalletGenerator
from sphinx_os.nexus.btc_burn_collector import BTCBurnCollector


def main():
    print("\n" + "="*60)
    print("  WALLET BTC COLLECTOR DEMO")
    print("="*60 + "\n")

    # Generate wallet
    gen = BTCWalletGenerator(seed=42)
    wallet = gen.generate_wallet()
    print(f"BTC Address: {wallet.address}")
    print(f"Mnemonic: {wallet.mnemonic}\n")

    # Collect burns
    collector = BTCBurnCollector(btc_claim_address=wallet.address, seed=42)
    report = collector.simulate_burns(n=15)

    print(f"Burns processed: {report.total_burns}")
    print(f"EXCAL collected: {report.total_excal_collected:.2f}")
    print(f"BTC reclaimed to {wallet.address}: {report.total_btc_reclaimed:.6f}")


if __name__ == "__main__":
    main()
