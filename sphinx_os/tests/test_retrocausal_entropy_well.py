#!/usr/bin/env python3
"""
Unit tests for retrocausal inverse entropy well system.
"""

import math
import unittest
from retrocausal_entropy_well import (
    LAMBDA_MATRIX,
    PHASE_CONSTANT,
    matrix_vector_multiply,
    arctan2_phase_shift,
    shannon_entropy,
    inverse_entropy,
    entropy_well_gradient,
    lambda_transform,
    retrocausal_arctan2_transform,
    CausalSinkState,
    RetrocausalSignal,
    EntropyWellResult,
    compute_retrocausal_signal,
    compute_entropy_well,
    compute_cross_sink_correlation,
    CrossSinkCorrelation,
    compute_single_signal,
    apply_lambda_transform,
    apply_phase_shift,
)


class TestLambdaMatrix(unittest.TestCase):
    """Test the lambda matrix properties."""

    def test_lambda_matrix_shape(self):
        """Lambda matrix should be 3x3."""
        self.assertEqual(len(LAMBDA_MATRIX), 3)
        for row in LAMBDA_MATRIX:
            self.assertEqual(len(row), 3)

    def test_lambda_matrix_values(self):
        """Lambda matrix should have correct values."""
        self.assertEqual(LAMBDA_MATRIX, [[1, 1, 1], [1, 0, -1], [-1, -1, -1]])

    def test_row_0_is_sum(self):
        """Row 0 [1,1,1] should sum all components."""
        result = matrix_vector_multiply([LAMBDA_MATRIX[0]], [1, 2, 3])
        self.assertEqual(result, [6])  # 1+2+3 = 6

    def test_row_1_is_asymmetry(self):
        """Row 1 [1,0,-1] should compute first minus last."""
        result = matrix_vector_multiply([LAMBDA_MATRIX[1]], [5, 3, 2])
        self.assertEqual(result, [3])  # 5-2 = 3

    def test_row_2_is_negative_sum(self):
        """Row 2 [-1,-1,-1] should negate the sum."""
        result = matrix_vector_multiply([LAMBDA_MATRIX[2]], [1, 2, 3])
        self.assertEqual(result, [-6])  # -(1+2+3) = -6

    def test_energy_anti_energy_cancel(self):
        """Row 0 + Row 2 should equal zero for any input."""
        state = [1.5, 2.7, 3.9]
        full_result = matrix_vector_multiply(LAMBDA_MATRIX, state)
        # y_0 + y_2 should be 0
        equilibrium = full_result[0] + full_result[2]
        self.assertAlmostEqual(equilibrium, 0.0, places=10)

    def test_phase_constant_perturbation(self):
        """Phase constant should be slightly perturbed from 1/3."""
        self.assertAlmostEqual(PHASE_CONSTANT, 0.33333333326, places=11)
        self.assertNotEqual(PHASE_CONSTANT, 1.0 / 3)


class TestMatrixVectorMultiply(unittest.TestCase):
    """Test matrix-vector multiplication."""

    def test_identity_like(self):
        """Test basic multiplication."""
        matrix = [[1, 0], [0, 1]]
        vector = [3, 4]
        result = matrix_vector_multiply(matrix, vector)
        self.assertEqual(result, [3, 4])

    def test_3x3_multiply(self):
        """Test 3x3 matrix multiplication."""
        matrix = [[1, 1, 1], [1, 0, -1], [-1, -1, -1]]
        vector = [1, 2, 3]
        result = matrix_vector_multiply(matrix, vector)
        self.assertEqual(result, [6, -2, -6])

    def test_zero_vector(self):
        """Test with zero vector."""
        matrix = [[1, 1, 1], [1, 0, -1], [-1, -1, -1]]
        vector = [0, 0, 0]
        result = matrix_vector_multiply(matrix, vector)
        self.assertEqual(result, [0, 0, 0])


class TestArctan2PhaseShift(unittest.TestCase):
    """Test arctan2 phase shift computation."""

    def test_phase_shift_range(self):
        """Phase shift should be in [-pi, pi]."""
        for y in [-10, -1, 0, 1, 10]:
            for x in [-10, -1, 0, 1, 10]:
                if x == 0 and y == 0:
                    continue
                result = arctan2_phase_shift(y, x)
                self.assertGreaterEqual(result, -math.pi)
                self.assertLessEqual(result, math.pi)

    def test_phase_shift_applied(self):
        """Phase shift should rotate by 2*pi*PHASE_CONSTANT."""
        base = math.atan2(1, 1)  # pi/4
        shifted = arctan2_phase_shift(1, 1)
        expected = base + 2 * math.pi * PHASE_CONSTANT
        # Normalize expected
        while expected > math.pi:
            expected -= 2 * math.pi
        while expected < -math.pi:
            expected += 2 * math.pi
        self.assertAlmostEqual(shifted, expected, places=10)

    def test_zero_zero(self):
        """arctan2(0,0) should handle gracefully."""
        result = arctan2_phase_shift(0, 0)
        self.assertIsInstance(result, float)


class TestEntropyFunctions(unittest.TestCase):
    """Test entropy computation functions."""

    def test_shannon_uniform(self):
        """Uniform distribution should have max entropy."""
        probs = [0.25, 0.25, 0.25, 0.25]
        entropy = shannon_entropy(probs)
        self.assertAlmostEqual(entropy, 2.0, places=10)  # log2(4) = 2

    def test_shannon_deterministic(self):
        """Deterministic distribution should have zero entropy."""
        probs = [1.0, 0.0, 0.0]
        entropy = shannon_entropy(probs)
        self.assertAlmostEqual(entropy, 0.0, places=10)

    def test_inverse_entropy_negative(self):
        """Inverse entropy should be negative of Shannon entropy."""
        probs = [0.5, 0.5]
        shannon = shannon_entropy(probs)
        inv = inverse_entropy(probs)
        self.assertAlmostEqual(inv, -shannon, places=10)

    def test_entropy_gradient(self):
        """Gradient should have same length as input."""
        probs = [0.3, 0.3, 0.4]
        gradient = entropy_well_gradient(probs)
        self.assertEqual(len(gradient), len(probs))

    def test_entropy_gradient_sign(self):
        """Gradient at p=0.5 should be positive (1/ln(2))."""
        probs = [0.5]
        gradient = entropy_well_gradient(probs)
        # log2(0.5) + 1/ln(2) = -1 + 1.4427 = 0.4427
        self.assertGreater(gradient[0], 0)


class TestLambdaTransform(unittest.TestCase):
    """Test lambda transformation."""

    def test_3d_output(self):
        """Lambda transform should produce 3D output."""
        result = lambda_transform([1, 2, 3])
        self.assertEqual(len(result), 3)

    def test_energy_anti_energy_property(self):
        """y_0 + y_2 should equal 0."""
        result = lambda_transform([1.5, 2.7, 3.9])
        self.assertAlmostEqual(result[0] + result[2], 0.0, places=10)

    def test_padding_short_vector(self):
        """Short vectors should be padded with zeros."""
        result = lambda_transform([1, 2])
        # Should treat as [1, 2, 0]
        expected = lambda_transform([1, 2, 0])
        self.assertEqual(result, expected)

    def test_known_values(self):
        """Test with known values."""
        result = lambda_transform([1, 2, 3])
        self.assertEqual(result[0], 6)   # 1+2+3
        self.assertEqual(result[1], -2)  # 1-3
        self.assertEqual(result[2], -6)  # -(1+2+3)


class TestRetrocausalArctan2Transform(unittest.TestCase):
    """Test full arctan2 transformation."""

    def test_returns_tuple(self):
        """Should return (phase, cos, sin) tuple."""
        result = retrocausal_arctan2_transform(1, 1)
        self.assertEqual(len(result), 3)
        phase, cos_c, sin_c = result
        self.assertIsInstance(phase, float)
        self.assertIsInstance(cos_c, float)
        self.assertIsInstance(sin_c, float)

    def test_cos_sin_consistency(self):
        """cos^2 + sin^2 should equal 1."""
        phase, cos_c, sin_c = retrocausal_arctan2_transform(3, 4)
        self.assertAlmostEqual(cos_c ** 2 + sin_c ** 2, 1.0, places=10)


class TestCausalSinkState(unittest.TestCase):
    """Test causal sink state creation."""

    def test_create_sink(self):
        """Should create valid sink state."""
        sink = CausalSinkState(
            address="test",
            label="Test Sink",
            total_burned_satoshi=100000000,
            transaction_count=10,
            first_burn_height=100,
            last_burn_height=200,
            burn_timestamps=[1000, 2000, 3000],
            burn_amounts=[1, 1, 1],
            burn_txids=["tx1", "tx2", "tx3"],
        )
        self.assertEqual(sink.address, "test")
        self.assertEqual(sink.total_burned_satoshi, 100000000)


class TestComputeRetrocausalSignal(unittest.TestCase):
    """Test retrocausal signal computation."""

    def setUp(self):
        """Create a test sink."""
        self.sink = CausalSinkState(
            address="test_sink",
            label="Test",
            total_burned_satoshi=500000000,  # 5 BTC
            transaction_count=20,
            first_burn_height=100,
            last_burn_height=200,
            burn_timestamps=[1000 + i * 100 for i in range(20)],
            burn_amounts=[1] * 20,
            burn_txids=[f"tx{i}" for i in range(20)],
        )

    def test_signal_creation(self):
        """Should create valid signal."""
        signal = compute_retrocausal_signal(self.sink, 0)
        self.assertIsInstance(signal, RetrocausalSignal)
        self.assertEqual(signal.sink_address, "test_sink")

    def test_signal_has_3d_lambda(self):
        """Signal lambda projection should be 3D."""
        signal = compute_retrocausal_signal(self.sink, 0)
        self.assertEqual(len(signal.lambda_projection), 3)

    def test_signal_energy_equilibrium(self):
        """Signal lambda should have energy-anti-energy equilibrium."""
        signal = compute_retrocausal_signal(self.sink, 0)
        lp = signal.lambda_projection
        self.assertAlmostEqual(lp[0] + lp[2], 0.0, places=10)

    def test_signal_phase_in_range(self):
        """Signal phase should be in [-pi, pi]."""
        signal = compute_retrocausal_signal(self.sink, 0)
        self.assertGreaterEqual(signal.phase_angle, -math.pi)
        self.assertLessEqual(signal.phase_angle, math.pi)

    def test_signal_temporal_coherence(self):
        """Regular timestamps should have high coherence."""
        signal = compute_retrocausal_signal(self.sink, 0)
        # Uniform spacing gives CV=0, coherence = 1/(1+0) = 1
        self.assertAlmostEqual(signal.temporal_coherence, 1.0, places=6)

    def test_signal_frequency_components(self):
        """Should compute frequency components."""
        signal = compute_retrocausal_signal(self.sink, 0)
        self.assertGreater(len(signal.frequency_components), 0)
        # DC component should be 1.0 for uniform amounts
        self.assertAlmostEqual(signal.frequency_components[0], 1.0, places=6)


class TestComputeEntropyWell(unittest.TestCase):
    """Test entropy well computation."""

    def setUp(self):
        """Create a test sink."""
        self.sink = CausalSinkState(
            address="well_test",
            label="Well Test",
            total_burned_satoshi=100000000,
            transaction_count=10,
            first_burn_height=50,
            last_burn_height=150,
            burn_timestamps=[1000 + i * 600 for i in range(10)],
            burn_amounts=[1] * 10,
            burn_txids=[f"tx{i}" for i in range(10)],
        )

    def test_well_convergence(self):
        """Entropy well should converge."""
        result = compute_entropy_well(self.sink, max_iterations=50)
        self.assertIsInstance(result, EntropyWellResult)
        self.assertGreater(result.convergence_iterations, 0)

    def test_well_depth_positive(self):
        """Well depth should be positive."""
        result = compute_entropy_well(self.sink, max_iterations=20)
        self.assertGreater(result.well_depth, 0)

    def test_causal_violation_score(self):
        """Causal violation should equal phase constant."""
        result = compute_entropy_well(self.sink, max_iterations=20)
        self.assertAlmostEqual(
            result.causal_violation_score,
            PHASE_CONSTANT,
            places=6
        )

    def test_phase_shift_applied(self):
        """Phase shift should be 2*pi*PHASE_CONSTANT."""
        result = compute_entropy_well(self.sink, max_iterations=20)
        expected = 2 * math.pi * PHASE_CONSTANT
        self.assertAlmostEqual(result.phase_shift_applied, expected, places=10)


class TestCrossSinkCorrelation(unittest.TestCase):
    """Test cross-sink correlation computation."""

    def setUp(self):
        """Create two test sinks."""
        self.sink_a = CausalSinkState(
            address="sink_a",
            label="Sink A",
            total_burned_satoshi=100000000,
            transaction_count=10,
            first_burn_height=50,
            last_burn_height=150,
            burn_timestamps=[1000 + i * 600 for i in range(10)],
            burn_amounts=[1] * 10,
            burn_txids=[f"tx{i}" for i in range(10)],
        )
        self.sink_b = CausalSinkState(
            address="sink_b",
            label="Sink B",
            total_burned_satoshi=200000000,
            transaction_count=10,
            first_burn_height=60,
            last_burn_height=160,
            burn_timestamps=[1100 + i * 600 for i in range(10)],
            burn_amounts=[1] * 10,
            burn_txids=[f"tx{i}" for i in range(10)],
        )

    def test_correlation_computation(self):
        """Should compute valid correlation."""
        result_a = compute_entropy_well(self.sink_a, max_iterations=10)
        result_b = compute_entropy_well(self.sink_b, max_iterations=10)
        corr = compute_cross_sink_correlation(result_a, result_b)
        self.assertIsInstance(corr, CrossSinkCorrelation)

    def test_correlation_in_range(self):
        """Correlation values should be in [-1, 1]."""
        result_a = compute_entropy_well(self.sink_a, max_iterations=10)
        result_b = compute_entropy_well(self.sink_b, max_iterations=10)
        corr = compute_cross_sink_correlation(result_a, result_b)
        self.assertGreaterEqual(corr.phase_correlation, -1.0)
        self.assertLessEqual(corr.phase_correlation, 1.0)
        self.assertGreaterEqual(corr.entropy_correlation, -1.0)
        self.assertLessEqual(corr.entropy_correlation, 1.0)


class TestConvenienceFunctions(unittest.TestCase):
    """Test convenience wrapper functions."""

    def test_compute_single_signal(self):
        """Should compute signal from raw data."""
        signal = compute_single_signal(
            burn_satoshi=100000000,
            burn_count=5,
            last_height=100,
            timestamps=[1000, 2000, 3000, 4000, 5000],
        )
        self.assertIsInstance(signal, RetrocausalSignal)

    def test_apply_lambda_transform(self):
        """Should apply lambda transformation."""
        result = apply_lambda_transform([1, 2, 3])
        self.assertEqual(result, [6, -2, -6])

    def test_apply_phase_shift(self):
        """Should apply phase shift."""
        result = apply_phase_shift(1, 1)
        self.assertIsInstance(result, float)
        self.assertGreaterEqual(result, -math.pi)
        self.assertLessEqual(result, math.pi)


class TestRetrocausalProperties(unittest.TestCase):
    """Test key retrocausal mathematical properties."""

    def test_lambda_preserves_equilibrium(self):
        """Lambda transform should always give y_0 + y_2 = 0."""
        for _ in range(100):
            import random
            state = [random.uniform(-10, 10) for _ in range(3)]
            result = lambda_transform(state)
            self.assertAlmostEqual(result[0] + result[2], 0.0, places=10)

    def test_phase_shift_is_deterministic(self):
        """Same input should give same output."""
        result1 = arctan2_phase_shift(3, 4)
        result2 = arctan2_phase_shift(3, 4)
        self.assertEqual(result1, result2)

    def test_entropy_well_depth_is_shannon(self):
        """Well depth should equal Shannon entropy for uniform dist."""
        probs = [0.5, 0.5]
        well = -inverse_entropy(probs)
        shannon = shannon_entropy(probs)
        self.assertAlmostEqual(well, shannon, places=10)


if __name__ == '__main__':
    unittest.main()
