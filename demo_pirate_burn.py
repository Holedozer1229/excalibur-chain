#!/usr/bin/env python3
"""demo_pirate_burn.py — Pirate burn claim demo.

Scans real Bitcoin burns and claims scarcity value.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sphinx_os.nexus.pirate_burn_claim import PirateBurnClaim
from sphinx_os.nexus.btc_burn_wormhole import BurnTransaction
import hashlib


def main():
    print("\n" + "="*60)
    print("  PIRATE BURN CLAIM DEMO")
    print("="*60 + "\n")

    pirate = PirateBurnClaim(seed=42)

    # Generate simulated burns for demo
    burns = []
    for i in range(10):
        txid = hashlib.sha256(f"pirate_burn_{i}".encode()).hexdigest()
        sats = 50000 + i * 10000
        burns.append(BurnTransaction(
            txid=txid, address="1CounterpartyXXXXXXXXXXXXXXXUWLpVr",
            amount_btc=sats / 100_000_000, amount_sats=sats,
        ))

    for burn in burns:
        claim = pirate.claim_burn(burn)
        if claim:
            print(f"  Claimed: {burn.amount_btc:.6f} BTC → "
                  f"{claim.excal_minted:.0f} EXCAL "
                  f"CTC={'✓' if claim.ctc_validated else '✗'}")

    summary = pirate.get_summary()
    print(f"\nTotal claims: {summary.total_claims}")
    print(f"Total EXCAL minted: {summary.total_excal_minted:.0f}")
    print(f"CTC success rate: {summary.ctc_success_rate:.0%}")


if __name__ == "__main__":
    main()
