#!/usr/bin/env python3
"""Genesis BTC Collateral Loan Demo — Borrowing Against the First Block of Bitcoin.

This demo showcases the Genesis BTC Collateral Loan system, where the
Bitcoin Genesis Block serves as the ultimate collateral for loans.

Run this script to see the full demo:
    python demo_genesis_btc_loan.py
"""

from sphinx_os.nexus.genesis_btc_loan import run_genesis_loan_demo


if __name__ == "__main__":
    run_genesis_loan_demo()
