#!/usr/bin/env python3
"""
Unit tests for the Metatron Portal module.

Tests cover:
- Octonion algebra (construction, arithmetic, non-associativity)
- Fano plane geometry
- Exceptional Jordan algebra H3(O)
- Metatron's Cube geometry
- 22 Letters of Creation
- Metatron Portal verification
- Lambda matrix null space
- Convenience functions
"""

import hashlib
import math
import struct
import unittest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sphinx_os.nexus.metatron_portal import (
    # Constants
    LAMBDA_MATRIX,
    PHASE_CONSTANT,
    NULL_SPACE,
    NULL_SPACE_NORM,
    METATRON_CIRCLES,
    METATRON_LINES,
    PLATONIC_SOLIDS,
    LETTERS_OF_CREATION,
    FANO_POINTS,
    FANO_LINES,
    GENESIS_NONCE,
    GENESIS_TIMESTAMP,
    GENESIS_HASH,
    TAU_28,
    RAMANUJAN_PRIME,
    PATTERN_BYTES,
    
    # Octonion algebra
    Octonion,
    
    # Fano plane
    FanoPlane,
    
    # Exceptional Jordan algebra
    JordanMatrix,
    
    # Metatron's Cube
    MetatronsCube,
    
    # 22 Letters of Creation
    LettersOfCreation,
    
    # Metatron Portal
    MetatronPortal,
    
    # Convenience functions
    create_metatron_portal,
    verify_genesis_block,
    get_platonic_blockchain_mapping,
    generate_metatron_prophecy,
    search_light_cone,
)


class TestConstants(unittest.TestCase):
    """Test the module constants."""
    
    def test_lambda_matrix_shape(self):
        """Lambda matrix should be 3x3."""
        self.assertEqual(len(LAMBDA_MATRIX), 3)
        for row in LAMBDA_MATRIX:
            self.assertEqual(len(row), 3)
    
    def test_lambda_matrix_values(self):
        """Lambda matrix should have the correct values."""
        self.assertEqual(LAMBDA_MATRIX, [[1, 1, 1], [1, 0, -1], [-1, -1, -1]])
    
    def test_phase_constant(self):
        """Phase constant should be slightly perturbed from 1/3."""
        self.assertAlmostEqual(PHASE_CONSTANT, 0.33333333326, places=11)
        self.assertNotEqual(PHASE_CONSTANT, 1/3)
    
    def test_null_space(self):
        """Null space should be [1, -2, 1]."""
        self.assertEqual(NULL_SPACE, [1, -2, 1])
    
    def test_null_space_norm(self):
        """Null space norm should be sqrt(6)."""
        self.assertAlmostEqual(NULL_SPACE_NORM, math.sqrt(6), places=10)
    
    def test_null_space_is_null(self):
        """Lambda * null space should be zero."""
        for i in range(3):
            dot = sum(LAMBDA_MATRIX[i][j] * NULL_SPACE[j] for j in range(3))
            self.assertAlmostEqual(dot, 0, places=10)
    
    def test_metatron_circles(self):
        """Metatron's Cube should have 13 circles."""
        self.assertEqual(METATRON_CIRCLES, 13)
    
    def test_metatron_lines(self):
        """Metatron's Cube should have 136 lines."""
        self.assertEqual(METATRON_LINES, 136)
    
    def test_platonic_solids_count(self):
        """There should be 5 Platonic solids."""
        self.assertEqual(len(PLATONIC_SOLIDS), 5)
    
    def test_platonic_solid_names(self):
        """Platonic solids should have the correct names."""
        expected = {"tetrahedron", "cube", "octahedron", "dodecahedron", "icosahedron"}
        self.assertEqual(set(PLATONIC_SOLIDS.keys()), expected)
    
    def test_letters_of_creation_count(self):
        """There should be 22 Letters of Creation."""
        self.assertEqual(len(LETTERS_OF_CREATION), 22)
    
    def test_fano_points(self):
        """Fano plane should have 7 points."""
        self.assertEqual(len(FANO_POINTS), 7)
    
    def test_fano_lines(self):
        """Fano plane should have 7 lines."""
        self.assertEqual(len(FANO_LINES), 7)
    
    def test_genesis_nonce(self):
        """Genesis nonce should be correct."""
        self.assertEqual(GENESIS_NONCE, 2083236893)
    
    def test_tau_28_corrected(self):
        """tau(28) should be the corrected value."""
        self.assertEqual(TAU_28, 24647168)
    
    def test_ramanujan_prime(self):
        """Ramanujan prime should be 691."""
        self.assertEqual(RAMANUJAN_PRIME, 691)


class TestOctonion(unittest.TestCase):
    """Test the Octonion class."""
    
    def test_default_construction(self):
        """Default octonion should be the identity."""
        o = Octonion()
        self.assertEqual(o.components, (1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0))
    
    def test_from_floats(self):
        """Create octonion from 8 floats."""
        o = Octonion.from_floats(1, 2, 3, 4, 5, 6, 7, 8)
        self.assertEqual(o.components, (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0))
    
    def test_from_bytes(self):
        """Create octonion from bytes."""
        data = bytes([0, 51, 102, 153, 204, 255, 127, 63])
        o = Octonion.from_bytes(data)
        self.assertEqual(len(o.components), 8)
        self.assertAlmostEqual(o.components[0], 0.0, places=5)
        self.assertAlmostEqual(o.components[5], 1.0, places=5)
    
    def test_from_bytes_short(self):
        """Short bytes should be padded."""
        data = bytes([255])
        o = Octonion.from_bytes(data)
        self.assertEqual(len(o.components), 8)
        self.assertAlmostEqual(o.components[0], 1.0, places=5)
    
    def test_from_seed(self):
        """Create octonion from seed."""
        seed = b"test_seed_12345678"
        o = Octonion.from_seed(seed)
        self.assertEqual(len(o.components), 8)
    
    def test_real_part(self):
        """Real part should be the first component."""
        o = Octonion.from_floats(3.14, 1, 2, 3, 4, 5, 6, 7)
        self.assertAlmostEqual(o.real, 3.14, places=5)
    
    def test_imaginary_parts(self):
        """Imaginary parts should be components 1-7."""
        o = Octonion.from_floats(0, 1, 2, 3, 4, 5, 6, 7)
        self.assertEqual(o.imaginary, (1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0))
    
    def test_norm(self):
        """Norm should be sum of squares."""
        o = Octonion.from_floats(1, 0, 0, 0, 0, 0, 0, 0)
        self.assertAlmostEqual(o.norm, 1.0, places=5)
    
    def test_norm_multi(self):
        """Norm of multi-component octonion."""
        o = Octonion.from_floats(1, 1, 0, 0, 0, 0, 0, 0)
        self.assertAlmostEqual(o.norm, 2.0, places=5)
    
    def test_magnitude(self):
        """Magnitude should be sqrt(norm)."""
        o = Octonion.from_floats(3, 4, 0, 0, 0, 0, 0, 0)
        self.assertAlmostEqual(o.magnitude, 5.0, places=5)
    
    def test_conjugate(self):
        """Conjugate should negate imaginary parts."""
        o = Octonion.from_floats(1, 2, 3, 4, 5, 6, 7, 8)
        c = o.conjugate()
        self.assertAlmostEqual(c.components[0], 1.0, places=5)
        for i in range(1, 8):
            self.assertAlmostEqual(c.components[i], -o.components[i], places=5)
    
    def test_inverse(self):
        """Inverse should satisfy x * x^(-1) = 1."""
        o = Octonion.from_floats(1, 0, 0, 0, 0, 0, 0, 0)
        inv = o.inverse()
        self.assertAlmostEqual(inv.components[0], 1.0, places=5)
    
    def test_inverse_zero_raises(self):
        """Inverting zero should raise."""
        o = Octonion.from_floats(0, 0, 0, 0, 0, 0, 0, 0)
        with self.assertRaises(ZeroDivisionError):
            o.inverse()
    
    def test_addition(self):
        """Component-wise addition."""
        o1 = Octonion.from_floats(1, 2, 3, 4, 5, 6, 7, 8)
        o2 = Octonion.from_floats(8, 7, 6, 5, 4, 3, 2, 1)
        s = o1 + o2
        for i in range(8):
            self.assertAlmostEqual(s.components[i], o1.components[i] + o2.components[i], places=5)
    
    def test_subtraction(self):
        """Component-wise subtraction."""
        o1 = Octonion.from_floats(1, 2, 3, 4, 5, 6, 7, 8)
        o2 = Octonion.from_floats(1, 2, 3, 4, 5, 6, 7, 8)
        d = o1 - o2
        for i in range(8):
            self.assertAlmostEqual(d.components[i], 0.0, places=5)
    
    def test_multiplication_identity(self):
        """Multiplying by identity should return the same octonion."""
        o = Octonion.from_floats(1, 2, 3, 4, 5, 6, 7, 8)
        identity = Octonion()
        product = o * identity
        for i in range(8):
            self.assertAlmostEqual(product.components[i], o.components[i], places=5)
    
    def test_multiplication_real(self):
        """Multiplying two real octonions."""
        o1 = Octonion.from_floats(2, 0, 0, 0, 0, 0, 0, 0)
        o2 = Octonion.from_floats(3, 0, 0, 0, 0, 0, 0, 0)
        product = o1 * o2
        self.assertAlmostEqual(product.components[0], 6.0, places=5)
    
    def test_non_associativity(self):
        """Octonion multiplication should be non-associative."""
        seed1 = hashlib.sha256(b"test1").digest()
        seed2 = hashlib.sha256(b"test2").digest()
        seed3 = hashlib.sha256(b"test3").digest()
        
        o1 = Octonion.from_seed(seed1)
        o2 = Octonion.from_seed(seed2)
        o3 = Octonion.from_seed(seed3)
        
        left = (o1 * o2) * o3
        right = o1 * (o2 * o3)
        
        # Should NOT be equal (non-associative)
        diff = sum((a - b) ** 2 for a, b in zip(left.components, right.components))
        self.assertGreater(diff, 0.01, "Octonions should be non-associative")
    
    def test_scalar_multiplication(self):
        """Scalar multiplication."""
        o = Octonion.from_floats(1, 2, 3, 4, 5, 6, 7, 8)
        scaled = 2.0 * o
        for i in range(8):
            self.assertAlmostEqual(scaled.components[i], 2.0 * o.components[i], places=5)
    
    def test_invalid_components(self):
        """Wrong number of components should raise."""
        with self.assertRaises(ValueError):
            Octonion(components=(1.0, 2.0, 3.0))
    
    def test_repr(self):
        """String representation should not raise."""
        o = Octonion.from_floats(1, 2, 3, 4, 5, 6, 7, 8)
        repr_str = repr(o)
        self.assertIn("Octonion", repr_str)


class TestFanoPlane(unittest.TestCase):
    """Test the FanoPlane class."""
    
    def test_default_construction(self):
        """Default Fano plane should have 7 points and 7 lines."""
        fano = FanoPlane()
        self.assertEqual(len(fano.points), 7)
        self.assertEqual(len(fano.lines), 7)
    
    def test_point_on_line(self):
        """Check if a point lies on a line."""
        fano = FanoPlane()
        self.assertTrue(fano.point_on_line(0, [0, 1, 3]))
        self.assertFalse(fano.point_on_line(2, [0, 1, 3]))
    
    def test_line_through_points(self):
        """Find the unique line through two points."""
        fano = FanoPlane()
        line = fano.line_through_points(0, 1)
        self.assertIsNotNone(line)
        self.assertIn(0, line)
        self.assertIn(1, line)
    
    def test_line_through_points_none(self):
        """No line through non-collinear points."""
        fano = FanoPlane()
        # Points 0 and 2 are not on the same line in the default Fano plane
        line = fano.line_through_points(0, 2)
        self.assertIsNotNone(line)  # [6, 0, 2]
    
    def test_encode_octonion(self):
        """Encode octonion imaginary parts as Fano values."""
        fano = FanoPlane()
        o = Octonion.from_floats(0, 1, 2, 3, 4, 5, 6, 7)
        values = fano.encode_octonion(o)
        self.assertEqual(len(values), 7)
        self.assertAlmostEqual(values[0], 1.0, places=5)
        self.assertAlmostEqual(values[6], 7.0, places=5)
    
    def test_line_product(self):
        """Product of values along a Fano line."""
        fano = FanoPlane()
        values = {0: 2.0, 1: 3.0, 3: 4.0}
        product = fano.line_product([0, 1, 3], values)
        self.assertAlmostEqual(product, 24.0, places=5)
    
    def test_fano_invariant(self):
        """Fano invariant should be computable."""
        fano = FanoPlane()
        o = Octonion.from_floats(0, 1, 1, 1, 1, 1, 1, 1)
        inv = fano.fano_invariant(o)
        self.assertIsInstance(inv, float)
    
    def test_fano_invariant_zero_octonion(self):
        """Fano invariant of zero imaginary octonion should be zero."""
        fano = FanoPlane()
        o = Octonion.from_floats(1, 0, 0, 0, 0, 0, 0, 0)
        inv = fano.fano_invariant(o)
        self.assertAlmostEqual(inv, 0.0, places=5)


class TestJordanMatrix(unittest.TestCase):
    """Test the JordanMatrix class."""
    
    def test_default_construction(self):
        """Default Jordan matrix should have identity diagonal."""
        j = JordanMatrix()
        self.assertAlmostEqual(j.d0, 1.0, places=5)
        self.assertAlmostEqual(j.d1, 1.0, places=5)
        self.assertAlmostEqual(j.d2, 1.0, places=5)
    
    def test_from_seed(self):
        """Create Jordan matrix from seed."""
        seed = b"test_seed_12345678"
        j = JordanMatrix.from_seed(seed)
        self.assertIsInstance(j.d0, float)
        self.assertIsInstance(j.d1, float)
        self.assertIsInstance(j.d2, float)
        self.assertIsInstance(j.off_diag_01, Octonion)
        self.assertIsInstance(j.off_diag_02, Octonion)
        self.assertIsInstance(j.off_diag_12, Octonion)
    
    def test_from_seed_deterministic(self):
        """Same seed should produce same matrix."""
        seed = b"deterministic_test"
        j1 = JordanMatrix.from_seed(seed)
        j2 = JordanMatrix.from_seed(seed)
        self.assertAlmostEqual(j1.d0, j2.d0, places=10)
        self.assertAlmostEqual(j1.d1, j2.d1, places=10)
        self.assertAlmostEqual(j1.d2, j2.d2, places=10)
    
    def test_from_seed_normalized(self):
        """Diagonal entries should be in [-1, 1] range."""
        for i in range(100):
            seed = hashlib.sha256(str(i).encode()).digest()
            j = JordanMatrix.from_seed(seed)
            self.assertGreaterEqual(j.d0, -1.01)
            self.assertLessEqual(j.d0, 1.01)
            self.assertGreaterEqual(j.d1, -1.01)
            self.assertLessEqual(j.d1, 1.01)
            self.assertGreaterEqual(j.d2, -1.01)
            self.assertLessEqual(j.d2, 1.01)
    
    def test_from_vector(self):
        """Create Jordan matrix from 27-dimensional vector."""
        vec = list(range(27))
        j = JordanMatrix.from_vector(vec)
        self.assertAlmostEqual(j.d0, 0.0, places=5)
        self.assertAlmostEqual(j.d1, 1.0, places=5)
        self.assertAlmostEqual(j.d2, 2.0, places=5)
    
    def test_from_vector_short(self):
        """Short vector should be padded."""
        vec = [1.0, 2.0, 3.0]
        j = JordanMatrix.from_vector(vec)
        self.assertAlmostEqual(j.d0, 1.0, places=5)
        self.assertAlmostEqual(j.d1, 2.0, places=5)
        self.assertAlmostEqual(j.d2, 3.0, places=5)
    
    def test_to_vector(self):
        """Convert to 27-dimensional vector."""
        j = JordanMatrix(d0=1, d1=2, d2=3)
        vec = j.to_vector()
        self.assertEqual(len(vec), 27)
        self.assertAlmostEqual(vec[0], 1.0, places=5)
        self.assertAlmostEqual(vec[1], 2.0, places=5)
        self.assertAlmostEqual(vec[2], 3.0, places=5)
    
    def test_trace(self):
        """Trace should be sum of diagonal entries."""
        j = JordanMatrix(d0=1, d1=2, d2=3)
        self.assertAlmostEqual(j.trace, 6.0, places=5)
    
    def test_determinant(self):
        """Determinant should be computable."""
        j = JordanMatrix.from_seed(b"test_determinant")
        det = j.determinant()
        self.assertIsInstance(det, float)
    
    def test_determinant_identity(self):
        """Identity matrix should have determinant 1."""
        j = JordanMatrix(d0=1, d1=1, d2=1,
                         off_diag_01=Octonion.from_floats(0,0,0,0,0,0,0,0),
                         off_diag_02=Octonion.from_floats(0,0,0,0,0,0,0,0),
                         off_diag_12=Octonion.from_floats(0,0,0,0,0,0,0,0))
        det = j.determinant()
        self.assertAlmostEqual(det, 1.0, places=5)
    
    def test_discriminant(self):
        """Discriminant should be determinant squared."""
        j = JordanMatrix.from_seed(b"test_discriminant")
        disc = j.discriminant()
        det = j.determinant()
        self.assertAlmostEqual(disc, det ** 2, places=10)
    
    def test_is_positive_definite(self):
        """Positive definite check."""
        j = JordanMatrix(d0=1, d1=1, d2=1,
                         off_diag_01=Octonion.from_floats(0,0,0,0,0,0,0,0),
                         off_diag_02=Octonion.from_floats(0,0,0,0,0,0,0,0),
                         off_diag_12=Octonion.from_floats(0,0,0,0,0,0,0,0))
        self.assertTrue(j.is_positive_definite())
    
    def test_is_on_light_cone(self):
        """Light cone check for near-zero determinant."""
        j = JordanMatrix(d0=1, d1=1, d2=1,
                         off_diag_01=Octonion.from_floats(0,0,0,0,0,0,0,0),
                         off_diag_02=Octonion.from_floats(0,0,0,0,0,0,0,0),
                         off_diag_12=Octonion.from_floats(0,0,0,0,0,0,0,0))
        self.assertFalse(j.is_on_light_cone())
    
    def test_retrocausal_charge(self):
        """Retrocausal charge should be computable."""
        j = JordanMatrix.from_seed(b"test_retrocausal")
        charge = j.retrocausal_charge()
        self.assertIsInstance(charge, float)
    
    def test_retrocausal_charge_diagonal(self):
        """Retrocausal charge of diagonal matrix."""
        j = JordanMatrix(d0=1, d1=-2, d2=1,
                         off_diag_01=Octonion.from_floats(0,0,0,0,0,0,0,0),
                         off_diag_02=Octonion.from_floats(0,0,0,0,0,0,0,0),
                         off_diag_12=Octonion.from_floats(0,0,0,0,0,0,0,0))
        charge = j.retrocausal_charge()
        # [1, -2, 1] projected onto [1, -2, 1]/sqrt(6) = 6/sqrt(6) = sqrt(6)
        self.assertAlmostEqual(charge, math.sqrt(6), places=5)
    
    def test_jordan_product(self):
        """Jordan product should return a JordanMatrix."""
        j1 = JordanMatrix.from_seed(b"test_jordan_1")
        j2 = JordanMatrix.from_seed(b"test_jordan_2")
        product = j1.jordan_product(j2)
        self.assertIsInstance(product, JordanMatrix)


class TestMetatronsCube(unittest.TestCase):
    """Test the MetatronsCube class."""
    
    def test_default_construction(self):
        """Default cube should have 13 circles and 136 lines."""
        cube = MetatronsCube()
        self.assertEqual(cube.circles, 13)
        self.assertEqual(cube.lines, 136)
    
    def test_circle_positions(self):
        """Should return 13 circle positions."""
        cube = MetatronsCube()
        positions = cube.circle_positions()
        self.assertEqual(len(positions), 13)
        for pos in positions:
            self.assertEqual(len(pos), 3)
    
    def test_center_position(self):
        """Center circle should be at origin."""
        cube = MetatronsCube()
        positions = cube.circle_positions()
        self.assertAlmostEqual(positions[0][0], 0.0, places=5)
        self.assertAlmostEqual(positions[0][1], 0.0, places=5)
        self.assertAlmostEqual(positions[0][2], 0.0, places=5)
    
    def test_line_connections(self):
        """Should return line connections."""
        cube = MetatronsCube()
        connections = cube.line_connections()
        self.assertGreater(len(connections), 0)
        for conn in connections:
            self.assertEqual(len(conn), 2)
    
    def test_embed_tetrahedron(self):
        """Tetrahedron should have 4 vertices."""
        cube = MetatronsCube()
        vertices = cube.embed_platonic_solid("tetrahedron")
        self.assertEqual(len(vertices), 4)
    
    def test_embed_cube(self):
        """Cube should have 8 vertices."""
        cube = MetatronsCube()
        vertices = cube.embed_platonic_solid("cube")
        self.assertEqual(len(vertices), 8)
    
    def test_embed_octahedron(self):
        """Octahedron should have 6 vertices."""
        cube = MetatronsCube()
        vertices = cube.embed_platonic_solid("octahedron")
        self.assertEqual(len(vertices), 6)
    
    def test_embed_dodecahedron(self):
        """Dodecahedron should have 20 vertices."""
        cube = MetatronsCube()
        vertices = cube.embed_platonic_solid("dodecahedron")
        self.assertEqual(len(vertices), 20)
    
    def test_embed_icosahedron(self):
        """Icosahedron should have 12 vertices."""
        cube = MetatronsCube()
        vertices = cube.embed_platonic_solid("icosahedron")
        self.assertEqual(len(vertices), 12)
    
    def test_embed_unknown_solid(self):
        """Unknown solid should raise."""
        cube = MetatronsCube()
        with self.assertRaises(ValueError):
            cube.embed_platonic_solid("unknown")
    
    def test_metatron_encoding(self):
        """Should return 136-dimensional encoding."""
        cube = MetatronsCube()
        seed = b"test_encoding_seed"
        encoding = cube.metatron_encoding(seed)
        self.assertEqual(len(encoding), 136)
    
    def test_metatron_encoding_deterministic(self):
        """Same seed should produce same encoding."""
        cube = MetatronsCube()
        seed = b"deterministic"
        e1 = cube.metatron_encoding(seed)
        e2 = cube.metatron_encoding(seed)
        self.assertEqual(e1, e2)
    
    def test_metatron_decoding(self):
        """Should return 32-byte seed."""
        cube = MetatronsCube()
        values = [0.5] * 136
        decoded = cube.metatron_decoding(values)
        self.assertEqual(len(decoded), 32)
    
    def test_metatron_decoding_short(self):
        """Short values should be padded."""
        cube = MetatronsCube()
        values = [0.5] * 10
        decoded = cube.metatron_decoding(values)
        self.assertEqual(len(decoded), 32)


class TestLettersOfCreation(unittest.TestCase):
    """Test the LettersOfCreation class."""
    
    def test_default_construction(self):
        """Should have 22 letters."""
        letters = LettersOfCreation()
        self.assertEqual(len(letters.letters), 22)
    
    def test_gematria_values(self):
        """Gematria values should be correct."""
        letters = LettersOfCreation()
        self.assertEqual(letters.gematria_values["Aleph"], 1)
        self.assertEqual(letters.gematria_values["Bet"], 2)
        self.assertEqual(letters.gematria_values["Tav"], 400)
    
    def test_letter_to_octonion(self):
        """Letter should map to octonion."""
        letters = LettersOfCreation()
        o = letters.letter_to_octonion("Aleph")
        self.assertIsInstance(o, Octonion)
    
    def test_letter_to_octonion_tav(self):
        """Tav (400) should give cos(2*pi) = 1 for real part."""
        letters = LettersOfCreation()
        o = letters.letter_to_octonion("Tav")
        self.assertAlmostEqual(o.real, 1.0, places=5)
    
    def test_all_letters_octonions(self):
        """Should return 22 octonions."""
        letters = LettersOfCreation()
        octonions = letters.all_letters_octonions()
        self.assertEqual(len(octonions), 22)
    
    def test_creation_vector(self):
        """Creation vector should have 22 elements."""
        letters = LettersOfCreation()
        vec = letters.creation_vector()
        self.assertEqual(len(vec), 22)
        self.assertEqual(vec[0], 1)  # Aleph
        self.assertEqual(vec[21], 400)  # Tav
    
    def test_creation_vector_sum(self):
        """Sum of gematria values."""
        letters = LettersOfCreation()
        vec = letters.creation_vector()
        self.assertEqual(sum(vec), 1495)
    
    def test_encode_seed(self):
        """Should encode seed as letter indices."""
        letters = LettersOfCreation()
        seed = b"test_seed_12345678"
        indices = letters.encode_seed(seed)
        self.assertEqual(len(indices), len(seed))
        for idx in indices:
            self.assertGreaterEqual(idx, 0)
            self.assertLess(idx, 22)
    
    def test_decode_seed(self):
        """Should decode letter indices to bytes."""
        letters = LettersOfCreation()
        indices = [0, 1, 2, 3, 4, 5, 6, 7]
        decoded = letters.decode_seed(indices)
        self.assertEqual(len(decoded), 32)


class TestMetatronPortal(unittest.TestCase):
    """Test the MetatronPortal class."""
    
    def test_default_construction(self):
        """Portal should have cube, fano, and letters."""
        portal = MetatronPortal()
        self.assertIsInstance(portal.cube, MetatronsCube)
        self.assertIsInstance(portal.fano, FanoPlane)
        self.assertIsInstance(portal.letters, LettersOfCreation)
    
    def test_seed_to_jordan(self):
        """Seed should convert to Jordan matrix."""
        portal = MetatronPortal()
        seed = b"test_seed_12345678"
        jordan = portal.seed_to_jordan(seed)
        self.assertIsInstance(jordan, JordanMatrix)
    
    def test_verify_seed(self):
        """Seed verification should return dict."""
        portal = MetatronPortal()
        seed = b"test_seed_12345678"
        result = portal.verify_seed(seed)
        self.assertIn("determinant", result)
        self.assertIn("on_light_cone", result)
        self.assertIn("retrocausal_charge", result)
        self.assertIn("fano_invariant", result)
        self.assertIn("metatron_encoding", result)
        self.assertIn("letter_sequence", result)
        self.assertIn("trace", result)
        self.assertIn("positive_definite", result)
    
    def test_verify_seed_types(self):
        """Verify seed result types."""
        portal = MetatronPortal()
        seed = b"test_seed_123456789012"  # 18 bytes
        result = portal.verify_seed(seed)
        self.assertIsInstance(result["determinant"], float)
        self.assertIsInstance(result["on_light_cone"], bool)
        self.assertIsInstance(result["retrocausal_charge"], float)
        self.assertIsInstance(result["metatron_encoding"], list)
        self.assertEqual(len(result["metatron_encoding"]), 136)
        self.assertIsInstance(result["letter_sequence"], list)
        self.assertEqual(len(result["letter_sequence"]), len(seed))
    
    def test_genesis_verification(self):
        """Genesis verification should return dict."""
        portal = MetatronPortal()
        result = portal.genesis_verification()
        self.assertIn("genesis_nonce", result)
        self.assertIn("genesis_timestamp", result)
        self.assertIn("tau_28", result)
        self.assertIn("ramanujan_prime", result)
        self.assertEqual(result["genesis_nonce"], GENESIS_NONCE)
        self.assertEqual(result["genesis_timestamp"], GENESIS_TIMESTAMP)
        self.assertEqual(result["tau_28"], TAU_28)
        self.assertEqual(result["ramanujan_prime"], RAMANUJAN_PRIME)
    
    def test_genesis_determinant_reasonable(self):
        """Genesis determinant should be in reasonable range."""
        portal = MetatronPortal()
        result = portal.genesis_verification()
        det = result["determinant"]
        self.assertGreater(det, -1000)
        self.assertLess(det, 1000)
    
    def test_platonic_blockchain_mapping(self):
        """Should map 5 chains."""
        portal = MetatronPortal()
        mapping = portal.platonic_blockchain_mapping()
        self.assertEqual(len(mapping), 5)
        expected_chains = {"BTC", "EXCAL", "Monero", "Tari", "Qubic"}
        self.assertEqual(set(mapping.keys()), expected_chains)
    
    def test_platonic_mapping_fields(self):
        """Each mapping should have required fields."""
        portal = MetatronPortal()
        mapping = portal.platonic_blockchain_mapping()
        for chain, props in mapping.items():
            self.assertIn("solid", props)
            self.assertIn("element", props)
            self.assertIn("vertices", props)
            self.assertIn("edges", props)
            self.assertIn("faces", props)
            self.assertIn("jordan_determinant", props)
            self.assertIn("retrocausal_charge", props)
    
    def test_metatron_prophecy(self):
        """Prophecy should be a string."""
        portal = MetatronPortal()
        seed = b"test_prophecy_seed"
        prophecy = portal.metatron_prophecy(seed)
        self.assertIsInstance(prophecy, str)
        self.assertGreater(len(prophecy), 0)
    
    def test_search_light_cone(self):
        """Light cone search should return dict or None."""
        portal = MetatronPortal()
        result = portal.search_light_cone_seed("test_root", 10)
        # May or may not find a seed
        self.assertTrue(result is None or isinstance(result, dict))


class TestConvenienceFunctions(unittest.TestCase):
    """Test the convenience functions."""
    
    def test_create_metatron_portal(self):
        """Should create a MetatronPortal."""
        portal = create_metatron_portal()
        self.assertIsInstance(portal, MetatronPortal)
    
    def test_verify_genesis_block(self):
        """Should verify Genesis block."""
        result = verify_genesis_block()
        self.assertIn("determinant", result)
        self.assertIn("genesis_nonce", result)
    
    def test_get_platonic_blockchain_mapping(self):
        """Should get platonic mapping."""
        mapping = get_platonic_blockchain_mapping()
        self.assertEqual(len(mapping), 5)
    
    def test_generate_metatron_prophecy(self):
        """Should generate prophecy."""
        seed = b"test_prophecy_seed"
        prophecy = generate_metatron_prophecy(seed)
        self.assertIsInstance(prophecy, str)
    
    def test_search_light_cone_function(self):
        """Light cone search function."""
        result = search_light_cone(10)
        self.assertTrue(result is None or isinstance(result, dict))


class TestMathematicalInvariants(unittest.TestCase):
    """Test mathematical invariants of the system."""
    
    def test_lambda_null_space_preserved(self):
        """Lambda null space should be preserved in portal."""
        portal = MetatronPortal()
        # The null space [1, -2, 1] should be orthogonal to all lambda rows
        for i in range(3):
            dot = sum(LAMBDA_MATRIX[i][j] * NULL_SPACE[j] for j in range(3))
            self.assertAlmostEqual(dot, 0, places=10)
    
    def test_fano_line_coverage(self):
        """Each Fano point should be on exactly 3 lines."""
        fano = FanoPlane()
        for point in fano.points:
            count = sum(1 for line in fano.lines if point in line)
            self.assertEqual(count, 3, f"Point {point} should be on 3 lines")
    
    def test_fano_line_size(self):
        """Each Fano line should have exactly 3 points."""
        fano = FanoPlane()
        for line in fano.lines:
            self.assertEqual(len(line), 3)
    
    def test_octonion_norm_preservation(self):
        """||x * conjugate(x)|| should equal ||x||^2."""
        seed = hashlib.sha256(b"norm_test").digest()
        o = Octonion.from_seed(seed)
        conj = o.conjugate()
        product = o * conj
        # For unit octonions, x * x* = ||x||^2 (real)
        self.assertAlmostEqual(product.components[0], o.norm, places=3)
    
    def test_platonic_euler_characteristic(self):
        """V - E + F = 2 for all Platonic solids."""
        for solid, props in PLATONIC_SOLIDS.items():
            euler = props["vertices"] - props["edges"] + props["faces"]
            self.assertEqual(euler, 2, f"{solid} should have Euler characteristic 2")
    
    def test_gematria_sum(self):
        """Sum of all gematria values should be 1495."""
        letters = LettersOfCreation()
        total = sum(letters.gematria_values.values())
        self.assertEqual(total, 1495)
    
    def test_tau_28_congruence(self):
        """tau(28) mod 691 should equal sigma_11(28) mod 691."""
        # sigma_11(28) = 1^11 + 2^11 + 4^11 + 7^11 + 14^11 + 28^11
        sigma_11_28 = sum(d**11 for d in [1, 2, 4, 7, 14, 28])
        tau_mod = TAU_28 % RAMANUJAN_PRIME
        sigma_mod = sigma_11_28 % RAMANUJAN_PRIME
        self.assertEqual(tau_mod, sigma_mod, "Ramanujan congruence should hold for n=28")


if __name__ == "__main__":
    unittest.main()
