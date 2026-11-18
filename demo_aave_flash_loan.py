#!/usr/bin/env python3
"""Aave Flash Loan Demo — Atomic Uncollateralized Loans Backed by Genesis BTC.

This demo showcases the Aave Flash Loan Engine, where flash loans are
guaranteed by the atomicity of the Genesis Block.

Run this script to see the full demo:
    python demo_aave_flash_loan.py
"""

from sphinx_os.nexus.aave_flash_loan import run_aave_flash_loan_demo


if __name__ == "__main__":
    run_aave_flash_loan_demo()
