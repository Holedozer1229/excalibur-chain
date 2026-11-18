#!/usr/bin/env python3
"""Demo: Deutsch CTC Fixed-Point Solver - PSPACE Computational Power.

This script demonstrates how Deutsch-style Closed Timelike Curves (CTCs)
achieve PSPACE-level computational power through fixed-point consistency.

The core idea: if CTCs existed, the consistency condition S(ρ) = ρ would
require Nature to solve PSPACE-complete problems to maintain causal
consistency across time.

Run:
    python demo_deutsch_ctc.py
"""

import sys
import os
import io

# Fix encoding for Windows console
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sphinx_os.nexus.deutsch_ctc_solver import (
    DeutschCTCSolver,
    DensityMatrix,
    CTCSolution,
    ctc_solve_3sat,
    ctc_solve_subset_sum,
    ctc_solve_qbf,
    ctc_verify,
    analyze_ctc_power,
)


def demo_3sat():
    """Demonstrate solving 3-SAT via CTC fixed-point consistency."""
    print("\n" + "=" * 70)
    print("1. 3-SAT via Deutsch CTC Fixed Point")
    print("=" * 70)

    # Example: (x1 | x2 | x3) & (~x1 | ~x2 | x4) & (x2 | ~x3 | ~x4)
    clauses = [(1, 2, 3), (-1, -2, 4), (2, -3, -4)]
    print(f"\nProblem: 3-SAT with {len(clauses)} clauses")
    print(f"Clauses: {clauses}")

    sol = ctc_solve_3sat(clauses)
    print(f"\nSolution found:")
    for var, val in sorted(sol.solution.items()):
        print(f"  x{var + 1} = {val}")

    consistent_str = "[PASS] Satisfied" if sol.is_consistent else "[FAIL] Failed"
    verified_str = "[PASS] Correct" if ctc_verify(sol, '3sat', clauses) else "[FAIL] Incorrect"
    print(f"\nCTC Consistency: {consistent_str}")
    print(f"Verification: {verified_str}")
    print(f"CTC bits used: {sol.ctc_bits}")
    print(f"\nReasoning: {sol.reasoning}")

    # Demonstrate unsatisfiable case
    print("\n--- Unsatisfiable Example ---")
    unsat_clauses = [(1,), (-1,)]  # x1 & ~x1 -- impossible
    print(f"Clauses: {unsat_clauses}")
    try:
        ctc_solve_3sat(unsat_clauses)
        print("ERROR: Should have raised ValueError")
    except ValueError as e:
        print(f"[PASS] Correctly detected unsatisfiable: {e}")


def demo_subset_sum():
    """Demonstrate solving subset sum via CTC fixed-point consistency."""
    print("\n" + "=" * 70)
    print("2. Subset Sum via Deutsch CTC Fixed Point")
    print("=" * 70)

    numbers = [3, 7, 2, 5, 9, 1]
    target = 15
    print(f"\nProblem: Find subset of {numbers} that sums to {target}")

    sol = ctc_solve_subset_sum(numbers, target)
    selected = [numbers[i] for i in range(len(numbers)) if sol.solution.get(i, False)]
    print(f"\nSolution: {selected}")
    print(f"Sum: {sum(selected)}")

    consistent_str = "[PASS] Satisfied" if sol.is_consistent else "[FAIL] Failed"
    verified_str = "[PASS] Correct" if ctc_verify(sol, 'subset_sum', (numbers, target)) else "[FAIL] Incorrect"
    print(f"\nCTC Consistency: {consistent_str}")
    print(f"Verification: {verified_str}")
    print(f"CTC bits used: {sol.ctc_bits}")
    print(f"\nReasoning: {sol.reasoning}")

    # Demonstrate impossible case
    print("\n--- Impossible Example ---")
    impossible_numbers = [2, 4, 6]
    impossible_target = 5  # Odd target with even numbers
    print(f"Numbers: {impossible_numbers}, Target: {impossible_target}")
    try:
        ctc_solve_subset_sum(impossible_numbers, impossible_target)
        print("ERROR: Should have raised ValueError")
    except ValueError as e:
        print(f"[PASS] Correctly detected impossible: {e}")


def demo_qbf():
    """Demonstrate solving QBF (PSPACE-complete) via CTC fixed-point."""
    print("\n" + "=" * 70)
    print("3. QBF via Deutsch CTC Fixed Point (PSPACE-complete)")
    print("=" * 70)

    # Example: Ex x1 For x2 (x1 | x2) & (~x1 | ~x2)
    clauses = [(1, 2), (-1, -2)]
    quantifiers = ['E', 'A']  # Ex x1 For x2
    print(f"\nProblem: QBF with {len(clauses)} clauses")
    print(f"Clauses: {clauses}")
    print(f"Quantifiers: Ex x1 For x2")

    sol = ctc_solve_qbf(clauses, quantifiers)
    print(f"\nResult: {'TRUE' if sol.probability > 0 else 'FALSE'}")
    print(f"Solution: {sol.solution}")
    print(f"CTC bits used: {sol.ctc_bits}")
    print(f"\nReasoning: {sol.reasoning}")

    # Another example: Ex x1 For x2 (x1 | x2)
    print("\n--- Another QBF Example ---")
    clauses2 = [(1, 2)]
    quantifiers2 = ['E', 'A']  # Ex x1 For x2
    print(f"Clauses: {clauses2}")
    print(f"Quantifiers: Ex x1 For x2")

    sol2 = ctc_solve_qbf(clauses2, quantifiers2)
    print(f"Result: {'TRUE' if sol2.probability > 0 else 'FALSE'}")
    print(f"Solution: {sol2.solution}")

    # Deeper QBF: Ex x1 For x2 Ex x3 (x1 | x2 | x3)
    print("\n--- Deeper QBF Example ---")
    clauses3 = [(1, 2, 3)]
    quantifiers3 = ['E', 'A', 'E']  # Ex x1 For x2 Ex x3
    print(f"Clauses: {clauses3}")
    print(f"Quantifiers: Ex x1 For x2 Ex x3")

    sol3 = ctc_solve_qbf(clauses3, quantifiers3)
    print(f"Result: {'TRUE' if sol3.probability > 0 else 'FALSE'}")
    print(f"Solution: {sol3.solution}")


def demo_solver_class():
    """Demonstrate the DeutschCTCSolver class directly."""
    print("\n" + "=" * 70)
    print("4. DeutschCTCSolver Class - Direct Usage")
    print("=" * 70)

    def rotation_evolution(ctc_state, ce_state):
        """Simple rotation: advance by 1, wrapping around."""
        n = len(ctc_state)
        idx = sum(b << (n - 1 - i) for i, b in enumerate(ctc_state))
        next_idx = (idx + 1) % (2 ** n)
        next_state = tuple((next_idx >> (n - 1 - i)) & 1 for i in range(n))
        return next_state, ce_state

    print("\nExample: 2-bit CTC with rotation evolution")
    solver = DeutschCTCSolver(
        ctc_bits=2,
        ce_bits=1,
        evolution=rotation_evolution,
        max_iterations=100,
        tolerance=1e-10,
    )

    # Start with uniform distribution
    rho = DensityMatrix.uniform(2)
    print(f"Initial distribution entropy: {rho.entropy():.4f} bits")

    # Solve for fixed point
    rho_final = solver.solve()
    state, prob = rho_final.most_likely()
    print(f"Fixed point state: {state}")
    print(f"Fixed point probability: {prob:.6f}")
    print(f"Final distribution entropy: {rho_final.entropy():.4f} bits")

    # Demonstrate density matrix operations
    print("\n--- Density Matrix Operations ---")
    delta = DensityMatrix.delta((1, 0, 1))
    print(f"Delta distribution on (1,0,1): entropy = {delta.entropy():.4f} bits")

    uniform = DensityMatrix.uniform(3)
    print(f"Uniform distribution on 3 bits: entropy = {uniform.entropy():.4f} bits")
    print(f"Number of states: {len(uniform.probabilities)}")


def demo_complexity_analysis():
    """Display the complexity analysis of Deutsch CTCs."""
    print("\n" + "=" * 70)
    print("5. Complexity Analysis - PSPACE Power")
    print("=" * 70)

    analysis = analyze_ctc_power()
    print(f"\nComplexity Class: {analysis['complexity_class']}")
    print(f"Classical + CTC: {analysis['classical_with_ctc']}")
    print(f"Quantum + CTC: {analysis['quantum_with_ctc']}")

    print(f"\nKey Insight:")
    print(f"  {analysis['key_insight']}")

    print(f"\nProblems Solvable:")
    for problem in analysis['problems_solvable']:
        print(f"  - {problem}")

    print(f"\nPhysical Plausibility:")
    print(f"  {analysis['physical_plausibility']}")

    print(f"\nBrouwer's Guarantee:")
    print(f"  {analysis['brouwer_guarantee']}")


def main():
    """Run all demonstrations."""
    print("=" * 70)
    print("Deutsch CTC Fixed-Point Solver - PSPACE Computational Power")
    print("=" * 70)
    print("\nThis demo shows how Deutsch-style Closed Timelike Curves achieve")
    print("PSPACE-level computational power through fixed-point consistency.")
    print("\nThe consistency condition S(rho) = rho requires finding a self-consistent")
    print("state -- equivalent to solving PSPACE-complete problems.")

    demo_3sat()
    demo_subset_sum()
    demo_qbf()
    demo_solver_class()
    demo_complexity_analysis()

    print("\n" + "=" * 70)
    print("Demo Complete")
    print("=" * 70)
    print("\nThe Deutsch CTC model demonstrates that if closed timelike curves")
    print("existed, they would grant PSPACE-level computational power -- enough")
    print("to solve 3-SAT, subset sum, QBF, and other hard problems instantly.")
    print("\nThis is both a remarkable theoretical result and an argument against")
    print("the physical existence of Deutsch-style CTCs in our universe.")


if __name__ == "__main__":
    main()
