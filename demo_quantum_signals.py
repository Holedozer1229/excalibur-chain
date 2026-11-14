#!/usr/bin/env python3
"""demo_quantum_signals.py — Live demo of quantum signal generation.

Runs a 50-step simulation showing BUY/SELL/HOLD signals with CTC validation.
"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sphinx_os.nexus.quantum_signal_generator import QuantumSignalGenerator


def main():
    print("\n" + "="*60)
    print("  QUANTUM SIGNAL GENERATOR DEMO")
    print("="*60 + "\n")

    gen = QuantumSignalGenerator(seed=42)
    report = gen.run_simulation(steps=50)

    print(f"Total trades: {report.total_trades}")
    print(f"Win rate: {report.win_rate:.1%}")
    print(f"P&L: {report.total_pnl:+.2f} EXCAL")
    print(f"Sharpe ratio: {report.sharpe_ratio:.2f}")
    print(f"Final EXCAL: {report.total_excal:.2f}")

    print("\nSample signals:")
    for trade in report.trades[:5]:
        s = trade.signal
        print(f"  {s.signal_type:12s} conf={s.confidence:.2f} "
              f"CTC={'✓' if s.ctc_validated else '✗'} {s.reasoning}")


if __name__ == "__main__":
    main()
