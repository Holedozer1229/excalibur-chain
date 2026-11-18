#!/usr/bin/env python3
"""Tests for the Deutsch CTC Fixed-Point Solver module.

Tests cover:
1. DensityMatrix class operations
2. DeutschCTCSolver core fixed-point finding
3. 3-SAT solver
4. Subset sum solver
5. QBF solver (PSPACE-complete)
6. CTC verification
7. Complexity analysis
"""

import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sphinx_os.nexus.deutsch_ctc_solver import (
    DensityMatrix,
    DeutschCTCSolver,
    CTCSolution,
    ctc_solve_3sat,
    ctc_solve_subset_sum,
    ctc_solve_qbf,
    ctc_verify,
    analyze_ctc_power,
    _evaluate_clause,
    _evaluate_formula,
)


class TestDensityMatrix(unittest.TestCase):
    """Test the DensityMatrix class."""

    def test_uniform_distribution(self):
        """Uniform distribution has equal probability for all states."""
        dm = DensityMatrix.uniform(2)
        self.assertEqual(dm.num_bits, 2)
        self.assertEqual(len(dm.probabilities), 4)  # 2^2 = 4 states
        for state, prob in dm.probabilities.items():
            self.assertAlmostEqual(prob, 0.25)

    def test_uniform_entropy(self):
        """Uniform distribution has maximum entropy."""
        dm = DensityMatrix.uniform(3)
        # Entropy should be 3 bits for uniform over 8 states
        self.assertAlmostEqual(dm.entropy(), 3.0)

    def test_delta_distribution(self):
        """Delta distribution is concentrated on one state."""
        state = (1, 0, 1)
        dm = DensityMatrix.delta(state)
        self.assertEqual(dm.num_bits, 3)
        self.assertEqual(len(dm.probabilities), 1)
        self.assertAlmostEqual(dm.probabilities[state], 1.0)

    def test_delta_entropy(self):
        """Delta distribution has zero entropy."""
        dm = DensityMatrix.delta((1, 0, 1))
        self.assertAlmostEqual(dm.entropy(), 0.0)

    def test_most_likely(self):
        """Most likely returns the state with highest probability."""
        dm = DensityMatrix.delta((1, 0))
        state, prob = dm.most_likely()
        self.assertEqual(state, (1, 0))
        self.assertAlmostEqual(prob, 1.0)

    def test_copy(self):
        """Copy creates an independent copy."""
        dm = DensityMatrix.uniform(2)
        dm_copy = dm.copy()
        self.assertEqual(dm.probabilities, dm_copy.probabilities)
        dm_copy.probabilities[(0, 0)] = 0.99
        self.assertNotEqual(dm.probabilities, dm_copy.probabilities)


class TestDeutschCTCSolver(unittest.TestCase):
    """Test the DeutschCTCSolver class."""

    def test_identity_evolution(self):
        """Identity evolution: every state is a fixed point."""
        def identity(ctc_state, ce_state):
            return ctc_state, ce_state

        solver = DeutschCTCSolver(
            ctc_bits=2,
            ce_bits=1,
            evolution=identity,
            max_iterations=100,
            tolerance=1e-10,
        )

        rho = DensityMatrix.uniform(2)
        rho_final = solver.solve()

        # Identity should preserve the uniform distribution
        for state, prob in rho_final.probabilities.items():
            self.assertAlmostEqual(prob, 0.25, places=5)

    def test_constant_evolution(self):
        """Constant evolution: all states map to one fixed point."""
        target = (1, 0)

        def constant(ctc_state, ce_state):
            return target, ce_state

        solver = DeutschCTCSolver(
            ctc_bits=2,
            ce_bits=1,
            evolution=constant,
            max_iterations=100,
            tolerance=1e-10,
        )

        rho = DensityMatrix.uniform(2)
        rho_final = solver.solve()

        # After one iteration, all probability should be on target
        self.assertAlmostEqual(rho_final.probabilities[target], 1.0)

    def test_invalid_ctc_bits(self):
        """Invalid CTC bits should raise ValueError."""
        with self.assertRaises(ValueError):
            DeutschCTCSolver(
                ctc_bits=0,
                ce_bits=1,
                evolution=lambda c, e: (c, e),
            )

        with self.assertRaises(ValueError):
            DeutschCTCSolver(
                ctc_bits=21,
                ce_bits=1,
                evolution=lambda c, e: (c, e),
            )

    def test_solve_with_verification(self):
        """solve_with_verification returns CTCSolution."""
        def identity(ctc_state, ce_state):
            return ctc_state, ce_state

        solver = DeutschCTCSolver(
            ctc_bits=2,
            ce_bits=1,
            evolution=identity,
        )

        result = solver.solve_with_verification(lambda s: True)
        self.assertIsInstance(result, CTCSolution)
        self.assertEqual(result.ctc_bits, 2)
        self.assertEqual(result.ce_bits, 1)


class Test3SAT(unittest.TestCase):
    """Test the 3-SAT solver."""

    def test_simple_satisfiable(self):
        """Simple satisfiable 3-SAT."""
        clauses = [(1, 2, 3)]
        sol = ctc_solve_3sat(clauses)
        self.assertTrue(sol.is_consistent)
        self.assertTrue(ctc_verify(sol, '3sat', clauses))

    def test_multiple_clauses(self):
        """Multiple clauses with solution."""
        clauses = [(1, 2, 3), (-1, -2, 4), (2, -3, -4)]
        sol = ctc_solve_3sat(clauses)
        self.assertTrue(sol.is_consistent)
        self.assertTrue(ctc_verify(sol, '3sat', clauses))

    def test_unsatisfiable(self):
        """Unsatisfiable formula raises ValueError."""
        clauses = [(1,), (-1,)]
        with self.assertRaises(ValueError):
            ctc_solve_3sat(clauses)

    def test_empty_clauses(self):
        """Empty clause list raises ValueError."""
        with self.assertRaises(ValueError):
            ctc_solve_3sat([])

    def test_single_variable(self):
        """Single variable satisfiable."""
        clauses = [(1,)]
        sol = ctc_solve_3sat(clauses)
        self.assertTrue(sol.solution[0])  # x1 must be True

    def test_solution_structure(self):
        """Solution has correct structure."""
        clauses = [(1, 2), (-1, 3)]
        sol = ctc_solve_3sat(clauses)
        self.assertIsInstance(sol, CTCSolution)
        self.assertIsInstance(sol.solution, dict)
        self.assertIsInstance(sol.probability, float)
        self.assertIsInstance(sol.is_consistent, bool)
        self.assertIsInstance(sol.reasoning, str)


class TestSubsetSum(unittest.TestCase):
    """Test the subset sum solver."""

    def test_simple_subset(self):
        """Simple subset sum."""
        numbers = [1, 2, 3]
        target = 3
        sol = ctc_solve_subset_sum(numbers, target)
        self.assertTrue(sol.is_consistent)
        self.assertTrue(ctc_verify(sol, 'subset_sum', (numbers, target)))

    def test_larger_subset(self):
        """Larger subset sum problem."""
        numbers = [3, 7, 2, 5, 9, 1]
        target = 15
        sol = ctc_solve_subset_sum(numbers, target)
        self.assertTrue(sol.is_consistent)
        self.assertTrue(ctc_verify(sol, 'subset_sum', (numbers, target)))

    def test_no_solution(self):
        """No subset sums to target."""
        numbers = [2, 4, 6]
        target = 5
        with self.assertRaises(ValueError):
            ctc_solve_subset_sum(numbers, target)

    def test_empty_numbers(self):
        """Empty number list raises ValueError."""
        with self.assertRaises(ValueError):
            ctc_solve_subset_sum([], 0)

    def test_single_element(self):
        """Single element subset."""
        numbers = [5]
        target = 5
        sol = ctc_solve_subset_sum(numbers, target)
        self.assertTrue(sol.solution[0])


class TestQBF(unittest.TestCase):
    """Test the QBF solver (PSPACE-complete)."""

    def test_simple_existential(self):
        """Simple existential QBF."""
        clauses = [(1,)]
        quantifiers = ['E']  # ∃x1 (x1)
        sol = ctc_solve_qbf(clauses, quantifiers)
        self.assertTrue(sol.probability > 0)  # TRUE

    def test_existential_universal_true(self):
        """∃x1 ∀x2 (x1 ∨ x2) — TRUE."""
        clauses = [(1, 2)]
        quantifiers = ['E', 'A']
        sol = ctc_solve_qbf(clauses, quantifiers)
        self.assertTrue(sol.probability > 0)  # TRUE: x1=True works

    def test_existential_universal_false(self):
        """∃x1 ∀x2 (x1 ∨ x2) ∧ (¬x1 ∨ ¬x2) — FALSE."""
        clauses = [(1, 2), (-1, -2)]
        quantifiers = ['E', 'A']
        sol = ctc_solve_qbf(clauses, quantifiers)
        self.assertTrue(sol.probability == 0)  # FALSE

    def test_all_universal(self):
        """∀x1 (x1 ∨ ¬x1) — TRUE (tautology)."""
        clauses = [(1, -1)]
        quantifiers = ['A']
        sol = ctc_solve_qbf(clauses, quantifiers)
        self.assertTrue(sol.probability > 0)  # TRUE

    def test_deeper_quantifiers(self):
        """Deeper quantifier alternation."""
        clauses = [(1, 2, 3)]
        quantifiers = ['E', 'A', 'E']  # ∃x1 ∀x2 ∃x3
        sol = ctc_solve_qbf(clauses, quantifiers)
        self.assertIsInstance(sol, CTCSolution)
        self.assertTrue(sol.is_consistent)

    def test_solution_structure(self):
        """QBF solution has correct structure."""
        clauses = [(1, 2)]
        quantifiers = ['E', 'A']
        sol = ctc_solve_qbf(clauses, quantifiers)
        self.assertIsInstance(sol, CTCSolution)
        self.assertIsInstance(sol.solution, dict)
        self.assertIsInstance(sol.reasoning, str)


class TestEvaluateHelpers(unittest.TestCase):
    """Test the clause and formula evaluation helpers."""

    def test_clause_satisfied(self):
        """Clause is satisfied if any literal is true."""
        clause = (1, -2, 3)
        assignment = (1, 0, 0)  # x1=True, x2=False, x3=False
        self.assertTrue(_evaluate_clause(clause, assignment))

    def test_clause_not_satisfied(self):
        """Clause is not satisfied if all literals are false."""
        clause = (1, 2, 3)
        assignment = (0, 0, 0)  # All false
        self.assertFalse(_evaluate_clause(clause, assignment))

    def test_formula_satisfied(self):
        """Formula is satisfied if all clauses are satisfied."""
        clauses = [(1, 2), (-1, 2)]
        assignment = (0, 1)  # x1=False, x2=True
        self.assertTrue(_evaluate_formula(clauses, assignment))

    def test_formula_not_satisfied(self):
        """Formula is not satisfied if any clause is not satisfied."""
        clauses = [(1, 2), (1, -2)]
        assignment = (0, 0)  # x1=False, x2=False
        self.assertFalse(_evaluate_formula(clauses, assignment))


class TestCTCVerify(unittest.TestCase):
    """Test the CTC verification function."""

    def test_verify_3sat(self):
        """Verify a 3-SAT solution."""
        clauses = [(1, 2, 3)]
        sol = ctc_solve_3sat(clauses)
        self.assertTrue(ctc_verify(sol, '3sat', clauses))

    def test_verify_subset_sum(self):
        """Verify a subset sum solution."""
        numbers = [1, 2, 3]
        target = 3
        sol = ctc_solve_subset_sum(numbers, target)
        self.assertTrue(ctc_verify(sol, 'subset_sum', (numbers, target)))

    def test_verify_unknown_type(self):
        """Unknown problem type raises ValueError."""
        sol = CTCSolution(
            solution={},
            probability=1.0,
            is_consistent=True,
            num_iterations=1,
            ctc_bits=1,
            ce_bits=1,
            reasoning="test",
        )
        with self.assertRaises(ValueError):
            ctc_verify(sol, 'unknown', None)


class TestComplexityAnalysis(unittest.TestCase):
    """Test the complexity analysis function."""

    def test_analysis_structure(self):
        """Analysis returns expected structure."""
        analysis = analyze_ctc_power()
        self.assertIn('complexity_class', analysis)
        self.assertIn('classical_with_ctc', analysis)
        self.assertIn('quantum_with_ctc', analysis)
        self.assertIn('key_insight', analysis)
        self.assertIn('problems_solvable', analysis)

    def test_analysis_values(self):
        """Analysis returns correct values."""
        analysis = analyze_ctc_power()
        self.assertEqual(analysis['complexity_class'], 'PSPACE')
        self.assertEqual(analysis['classical_with_ctc'], 'PCTC = PSPACE')
        self.assertEqual(analysis['quantum_with_ctc'], 'BQPCTC = PSPACE')
        self.assertIsInstance(analysis['problems_solvable'], list)
        self.assertTrue(len(analysis['problems_solvable']) > 0)


if __name__ == "__main__":
    unittest.main()
