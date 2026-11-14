#!/usr/bin/env python3
"""CTC Oracle Market Demo — Trading PSPACE-level Computation as Financial Instruments.

This demo showcases the CTC Oracle Market, a novel financial primitive that
packages Deutsch CTC fixed-point computations as tradable, verifiable assets.

Run this script to see the full demo:
    python demo_ctc_oracle_market.py
"""

from sphinx_os.nexus.ctc_oracle_market import run_oracle_market_demo


if __name__ == "__main__":
    run_oracle_market_demo()
