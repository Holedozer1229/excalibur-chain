#!/usr/bin/env python3
"""
Unit tests for the Retrocausal Seed Tracer module.

Tests verify:
1. Genesis seed encoding and properties
2. Lambda matrix null space analysis
3. Inverse lambda transformation
4. Retrocausal tracing convergence
5. Genesis-to-sink correlation
6. Phase locking verification
7. Convenience functions
"""

import hashlib
import math
import unittest
from retrocausal_seed_tracer import (
    # Constants
    GENESIS_BLOCK_HASH,
    GENESIS_NONCE,
    GENESIS_TIMESTAMP,
    GENESIS_EMBEDDED_MESSAGE,
    GENESIS_COINBASE_VALUE,
    LAMBDA_MATRIX,
    PHASE_CONSTANT,
    # Data classes
    GenesisSeedState,
    RetrocausalTrace,
    SeedTraceResult,
    NullSpaceAnalysis,
    # Genesis seed encoding
    encode_genesis_seed,
    compute_byte_entropy,
    # Lambda matrix analysis
    compute_null_space,
    compute_singular_values,
    project_onto_null_space,
    retrocausal_source_component,
    # Inverse lambda transformation
    inverse_lambda_transform,
    # Retrocausal tracing
    trace_to_seed,
    # Genesis-to-sink correlation
    compute_genesis_correlation,
    # Phase locking
    verify_phase_locking,
    # Convenience functions
    trace_single_sink,
    verify_genesis_source,
)


class TestGenesisSeedEncoding(unittest.TestCase):
    """Test Genesis Block encoding as retrocausal seed state."""

    def test_encode_genesis_seed_returns_valid_state(self):
        """Test that encode_genesis_seed returns a valid GenesisSeedState."""
        seed = encode_genesis_seed()
        self.assertIsInstance(seed, GenesisSeedState)
        self.assertEqual(seed.block_hash, GENESIS_BLOCK_HASH)
        self.assertEqual(seed.nonce, GENESIS_NONCE)
        self.assertEqual(seed.timestamp, GENESIS_TIMESTAMP)
        self.assertEqual(seed.embedded_message, GENESIS_EMBEDDED_MESSAGE)
        self.assertEqual(seed.coinbase_value, GENESIS_COINBASE_VALUE)

    def test_genesis_state_vector_normalized(self):
        """Test that the Genesis state vector components are normalized."""
        seed = encode_genesis_seed()
        self.assertEqual(len(seed.state_vector), 3)
        # Nonce normalized by 2^32
        expected_nonce = GENESIS_NONCE / (2**32)
        self.assertAlmostEqual(seed.state_vector[0], expected_nonce, places=6)
        # Timestamp normalized by 10^9
        expected_timestamp = GENESIS_TIMESTAMP / 1e9
        self.assertAlmostEqual(seed.state_vector[1], expected_timestamp, places=6)
        # Coinbase normalized by 21,000,000
        expected_coinbase = GENESIS_COINBASE_VALUE / 21_000_000.0
        self.assertAlmostEqual(seed.state_vector[2], expected_coinbase, places=10)

    def test_genesis_hash_entropy_positive(self):
        """Test that the Genesis hash entropy is positive."""
        seed = encode_genesis_seed()
        self.assertGreater(seed.hash_entropy, 0)
        # SHA-256 hash should have high entropy
        self.assertGreater(seed.hash_entropy, 4.0)

    def test_genesis_nonce_bits(self):
        """Test that the nonce bits are computed correctly."""
        seed = encode_genesis_seed()
        expected_bits = GENESIS_NONCE.bit_length()
        self.assertEqual(seed.nonce_bits, expected_bits)
        # Genesis nonce is 2083236893, which has 31 bits
        self.assertEqual(seed.nonce_bits, 31)

    def test_genesis_seed_fingerprint(self):
        """Test that the seed fingerprint is a valid SHA-256 hash."""
        seed = encode_genesis_seed()
        self.assertEqual(len(seed.seed_fingerprint), 64)  # SHA-256 hex length
        # Verify it's the correct hash
        seed_data = f"{GENESIS_BLOCK_HASH}:{GENESIS_NONCE}:{GENESIS_TIMESTAMP}"
        expected = hashlib.sha256(seed_data.encode()).hexdigest()
        self.assertEqual(seed.seed_fingerprint, expected)

    def test_compute_byte_entropy_uniform(self):
        """Test entropy of uniform byte distribution."""
        # Uniform distribution of 256 bytes
        data = bytes(range(256))
        entropy = compute_byte_entropy(data)
        # Uniform distribution should have maximum entropy (8 bits)
        self.assertAlmostEqual(entropy, 8.0, places=5)

    def test_compute_byte_entropy_constant(self):
        """Test entropy of constant byte distribution."""
        data = bytes([42] * 100)
        entropy = compute_byte_entropy(data)
        # Constant distribution should have zero entropy
        self.assertAlmostEqual(entropy, 0.0, places=5)

    def test_compute_byte_entropy_empty(self):
        """Test entropy of empty data."""
        entropy = compute_byte_entropy(b'')
        self.assertEqual(entropy, 0.0)


class TestLambdaMatrixAnalysis(unittest.TestCase):
    """Test lambda matrix null space analysis."""

    def test_compute_null_space_dimension(self):
        """Test that the null space dimension is correct."""
        null_vectors, dimension = compute_null_space(LAMBDA_MATRIX)
        self.assertEqual(dimension, 1)
        self.assertEqual(len(null_vectors), 1)

    def test_null_vector_normalized(self):
        """Test that the null vector is normalized."""
        null_vectors, _ = compute_null_space(LAMBDA_MATRIX)
        null_vector = null_vectors[0]
        norm = math.sqrt(sum(v**2 for v in null_vector))
        self.assertAlmostEqual(norm, 1.0, places=6)

    def test_null_vector_satisfies_null_space(self):
        """Test that the null vector is in the null space of the lambda matrix."""
        null_vectors, _ = compute_null_space(LAMBDA_MATRIX)
        null_vector = null_vectors[0]
        
        # M * v should be zero
        result = [
            sum(LAMBDA_MATRIX[r][c] * null_vector[c] for c in range(3))
            for r in range(3)
        ]
        for val in result:
            self.assertAlmostEqual(val, 0.0, places=6)

    def test_null_vector_values(self):
        """Test the null vector has the expected values [1, -2, 1] normalized."""
        null_vectors, _ = compute_null_space(LAMBDA_MATRIX)
        null_vector = null_vectors[0]
        
        # Expected: [1, -2, 1] / sqrt(6)
        expected = [1/math.sqrt(6), -2/math.sqrt(6), 1/math.sqrt(6)]
        for actual, exp in zip(null_vector, expected):
            self.assertAlmostEqual(actual, exp, places=6)

    def test_singular_values(self):
        """Test that singular values are computed correctly."""
        sv = compute_singular_values(LAMBDA_MATRIX)
        self.assertEqual(len(sv), 3)
        # First two should be positive, third should be zero
        self.assertGreater(sv[0], 2.0)
        self.assertGreater(sv[1], 1.0)
        self.assertAlmostEqual(sv[2], 0.0, places=6)

    def test_singular_values_sum_of_squares(self):
        """Test that sum of squared singular values equals trace(M^T M)."""
        sv = compute_singular_values(LAMBDA_MATRIX)
        sum_sq = sum(v**2 for v in sv)
        # Trace of M^T M = sum of squared elements of M
        # M = [[1,1,1],[1,0,-1],[-1,-1,-1]]
        # Sum of squares = 1+1+1 + 1+0+1 + 1+1+1 = 8
        self.assertAlmostEqual(sum_sq, 8.0, places=5)

    def test_project_onto_null_space(self):
        """Test projection onto null space."""
        null_vectors, _ = compute_null_space(LAMBDA_MATRIX)
        null_vector = null_vectors[0]
        
        # Project the null vector onto itself should give 1.0
        proj = project_onto_null_space(null_vector, null_vector)
        self.assertAlmostEqual(proj, 1.0, places=6)
        
        # Project an orthogonal vector should give ~0
        # [1, 0, -1] is orthogonal to [1, -2, 1]
        orthogonal = [1.0, 0.0, -1.0]
        proj = project_onto_null_space(orthogonal, null_vector)
        self.assertAlmostEqual(proj, 0.0, places=6)

    def test_retrocausal_source_component(self):
        """Test extraction of retrocausal source component."""
        null_vectors, _ = compute_null_space(LAMBDA_MATRIX)
        null_vector = null_vectors[0]
        
        # The source component of the null vector should be the null vector
        source = retrocausal_source_component(null_vector, null_vector)
        for s, n in zip(source, null_vector):
            self.assertAlmostEqual(s, n, places=6)


class TestInverseLambdaTransform(unittest.TestCase):
    """Test the inverse lambda transformation."""

    def test_inverse_of_forward_transform(self):
        """Test that inverse(lambda(x)) recovers x for valid inputs."""
        # Start with a known state
        state = [0.5, 0.3, 0.2]
        
        # Forward transform
        lambda_proj = [
            sum(LAMBDA_MATRIX[r][c] * state[c] for c in range(3))
            for r in range(3)
        ]
        
        # Inverse transform
        recovered = inverse_lambda_transform(lambda_proj)
        self.assertIsNotNone(recovered)
        
        # The recovered state should have the same lambda projection
        recovered_proj = [
            sum(LAMBDA_MATRIX[r][c] * recovered[c] for c in range(3))
            for r in range(3)
        ]
        for orig, rec in zip(lambda_proj, recovered_proj):
            self.assertAlmostEqual(orig, rec, places=6)

    def test_inverse_consistency(self):
        """Test that inverse enforces y₀ + y₂ = 0 consistency."""
        # Create an inconsistent projection
        inconsistent = [1.0, 0.5, -0.8]  # y₀ + y₂ = 0.2 ≠ 0
        
        result = inverse_lambda_transform(inconsistent)
        self.assertIsNotNone(result)
        
        # The result should produce a consistent projection
        proj = [
            sum(LAMBDA_MATRIX[r][c] * result[c] for c in range(3))
            for r in range(3)
        ]
        self.assertAlmostEqual(proj[0] + proj[2], 0.0, places=6)

    def test_inverse_too_short(self):
        """Test that inverse returns None for too-short input."""
        result = inverse_lambda_transform([1.0])
        self.assertIsNone(result)

    def test_inverse_zero(self):
        """Test that inverse of zero is zero."""
        result = inverse_lambda_transform([0.0, 0.0, 0.0])
        self.assertIsNotNone(result)
        for val in result:
            self.assertAlmostEqual(val, 0.0, places=6)


class TestRetrocausalTracing(unittest.TestCase):
    """Test retrocausal tracing to the Genesis seed."""

    def setUp(self):
        """Set up test fixtures."""
        self.genesis_seed = encode_genesis_seed()

    def test_trace_from_seed_converges_immediately(self):
        """Test that tracing from the seed itself converges immediately."""
        result = trace_to_seed(
            self.genesis_seed.state_vector,
            self.genesis_seed,
        )
        self.assertTrue(result.trace_success)
        self.assertAlmostEqual(result.final_distance, 0.0, places=10)
        self.assertEqual(result.convergence_step, 0)

    def test_trace_converges_to_seed(self):
        """Test that tracing from a random state converges to the seed."""
        # Start from a state far from the seed
        random_state = [0.1, 0.5, 0.9]
        
        result = trace_to_seed(
            random_state,
            self.genesis_seed,
            max_steps=500,
            learning_rate=0.1,
        )
        self.assertTrue(result.trace_success)
        self.assertLess(result.final_distance, 1e-10)

    def test_trace_path_monotonically_decreases(self):
        """Test that the trace path distance monotonically decreases."""
        random_state = [0.1, 0.5, 0.9]
        
        result = trace_to_seed(
            random_state,
            self.genesis_seed,
            max_steps=100,
            learning_rate=0.1,
        )
        
        # Check that distance decreases over the first few steps
        for i in range(1, min(10, len(result.trace_path))):
            prev_dist = result.trace_path[i-1].distance_to_seed
            curr_dist = result.trace_path[i].distance_to_seed
            self.assertLessEqual(curr_dist, prev_dist + 1e-10)

    def test_trace_result_has_valid_path(self):
        """Test that the trace result has a valid path."""
        random_state = [0.1, 0.5, 0.9]
        
        result = trace_to_seed(
            random_state,
            self.genesis_seed,
            max_steps=50,
            learning_rate=0.1,
        )
        
        self.assertGreater(len(result.trace_path), 0)
        for trace in result.trace_path:
            self.assertEqual(len(trace.state_vector), 3)
            self.assertEqual(len(trace.lambda_projection), 3)
            self.assertGreaterEqual(trace.distance_to_seed, 0)

    def test_trace_preserves_null_space_component(self):
        """Test that the null space component is approximately preserved."""
        null_vectors, _ = compute_null_space(LAMBDA_MATRIX)
        null_vector = null_vectors[0]
        
        # Start from a state with a known null space component
        state = list(self.genesis_seed.state_vector)
        initial_null_comp = project_onto_null_space(state, null_vector)
        
        result = trace_to_seed(
            state,
            self.genesis_seed,
            max_steps=10,
            learning_rate=0.1,
        )
        
        # The null space component should be close to the initial value
        final_null_comp = result.trace_path[-1].null_space_component
        # Since we're tracing TO the seed, the null comp should approach the seed's null comp
        seed_null_comp = project_onto_null_space(self.genesis_seed.state_vector, null_vector)
        self.assertAlmostEqual(final_null_comp, seed_null_comp, places=2)

    def test_trace_phase_winding(self):
        """Test that phase winding is computed."""
        random_state = [0.1, 0.5, 0.9]
        
        result = trace_to_seed(
            random_state,
            self.genesis_seed,
            max_steps=100,
            learning_rate=0.1,
        )
        
        # Phase winding should be a finite number
        self.assertLess(abs(result.phase_winding_number), 10)


class TestGenesisCorrelation(unittest.TestCase):
    """Test Genesis-to-sink correlation computation."""

    def setUp(self):
        """Set up test fixtures."""
        self.genesis_seed = encode_genesis_seed()

    def test_correlation_with_self(self):
        """Test that correlation with self is 1.0."""
        corr = compute_genesis_correlation(
            self.genesis_seed,
            self.genesis_seed.state_vector,
        )
        self.assertAlmostEqual(corr, 1.0, places=6)

    def test_correlation_range(self):
        """Test that correlation is in [-1, 1]."""
        random_state = [0.1, 0.5, 0.9]
        corr = compute_genesis_correlation(self.genesis_seed, random_state)
        self.assertGreaterEqual(corr, -1.0)
        self.assertLessEqual(corr, 1.0)

    def test_correlation_with_orthogonal_state(self):
        """Test correlation with a state orthogonal to the seed."""
        # A state that's very different from the seed
        orthogonal_state = [1.0, 0.0, 0.0]
        corr = compute_genesis_correlation(self.genesis_seed, orthogonal_state)
        # Should be negative or near zero
        self.assertLess(corr, 0.5)


class TestPhaseLocking(unittest.TestCase):
    """Test phase locking verification."""

    def setUp(self):
        """Set up test fixtures."""
        self.genesis_seed = encode_genesis_seed()

    def test_phase_locking_with_self(self):
        """Test that phase locking with self gives zero difference."""
        phase_diff, is_locked = verify_phase_locking(
            self.genesis_seed,
            self.genesis_seed.state_vector,
        )
        self.assertAlmostEqual(phase_diff, 0.0, places=6)
        self.assertTrue(is_locked)

    def test_phase_difference_range(self):
        """Test that phase difference is in [-π, π]."""
        random_state = [0.1, 0.5, 0.9]
        phase_diff, _ = verify_phase_locking(self.genesis_seed, random_state)
        self.assertGreaterEqual(phase_diff, -math.pi)
        self.assertLessEqual(phase_diff, math.pi)

    def test_phase_locking_threshold(self):
        """Test that phase locking threshold works."""
        # A state very close to the seed should be phase-locked
        close_state = [
            self.genesis_seed.state_vector[0] + 0.001,
            self.genesis_seed.state_vector[1] + 0.001,
            self.genesis_seed.state_vector[2] + 0.001,
        ]
        _, is_locked = verify_phase_locking(self.genesis_seed, close_state)
        self.assertTrue(is_locked)


class TestConvenienceFunctions(unittest.TestCase):
    """Test convenience functions."""

    def test_trace_single_sink(self):
        """Test tracing a single sink."""
        result = trace_single_sink(
            burned_satoshi=int(13.4 * 1e8),
            last_height=900000,
            tx_count=500,
        )
        self.assertIsInstance(result, SeedTraceResult)
        # With default params (max_steps=200, lr=0.05), trace should converge
        self.assertTrue(result.trace_success)
        self.assertLess(result.final_distance, 1e-10)

    def test_verify_genesis_source(self):
        """Test verifying the Genesis source."""
        result = verify_genesis_source([0.1, 0.5, 0.9])
        self.assertIn('genesis_correlation', result)
        self.assertIn('phase_difference', result)
        self.assertIn('phase_locked', result)
        self.assertIn('trace_success', result)
        self.assertIn('final_distance', result)
        self.assertIn('null_space_alignment', result)

    def test_verify_genesis_source_with_seed(self):
        """Test verifying the Genesis source with the seed state."""
        genesis_seed = encode_genesis_seed()
        result = verify_genesis_source(genesis_seed.state_vector)
        self.assertTrue(result['phase_locked'])
        self.assertTrue(result['trace_success'])


class TestConstants(unittest.TestCase):
    """Test that constants are correctly defined."""

    def test_genesis_block_hash(self):
        """Test the Genesis block hash."""
        self.assertEqual(GENESIS_BLOCK_HASH, "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f")

    def test_genesis_nonce(self):
        """Test the Genesis nonce."""
        self.assertEqual(GENESIS_NONCE, 2083236893)

    def test_genesis_timestamp(self):
        """Test the Genesis timestamp."""
        self.assertEqual(GENESIS_TIMESTAMP, 1231006505)

    def test_lambda_matrix_shape(self):
        """Test the lambda matrix shape."""
        self.assertEqual(len(LAMBDA_MATRIX), 3)
        for row in LAMBDA_MATRIX:
            self.assertEqual(len(row), 3)

    def test_lambda_matrix_values(self):
        """Test the lambda matrix values."""
        self.assertEqual(LAMBDA_MATRIX, [[1, 1, 1], [1, 0, -1], [-1, -1, -1]])

    def test_phase_constant(self):
        """Test the phase constant."""
        self.assertAlmostEqual(PHASE_CONSTANT, 0.33333333326, places=11)


if __name__ == '__main__':
    unittest.main()
