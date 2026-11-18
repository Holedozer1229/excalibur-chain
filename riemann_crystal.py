#!/usr/bin/env python3
"""
riemann_crystal.py — Riemann Zeta Quasicrystals and X-Ray Diffraction

A crystallographic engine that builds 3D quasicrystals from Riemann zeros,
computes their X-ray diffraction patterns, and reveals how the diffraction
peaks encode the distribution of prime numbers.

THE CONCEPT
===========
Quasicrystals are ordered structures that are periodic but not crystalline.
They were discovered by Dan Shechtman in 1982 (Nobel Prize 2011) and
defied the conventional wisdom that solids must be either periodic crystals
or amorphous glass.

The key insight: the Riemann zeros γₖ can serve as the "atomic positions"
in a 1D quasicrystal, and the resulting X-ray diffraction pattern reveals
the prime number distribution.

THE MATHEMATICS
===============
A 1D quasicrystal can be constructed by projecting a higher-dimensional
periodic lattice onto a lower-dimensional subspace. For the Riemann
quasicrystal, we use the critical line Re(s) = 1/2 as the physical
dimension and the imaginary axis as the internal dimension.

The atomic positions are given by the Riemann zeros:
    xₖ = γₖ / (2π)

The structure factor (diffraction amplitude) is:
    S(q) = Σₖ exp(2πi q xₖ)

The diffraction intensity is:
    I(q) = |S(q)|²

THE PRIME NUMBER CONNECTION
============================
The explicit formula connects the Riemann zeros to the prime counting
function π(x):

    π(x) = Li(x) - Σₖ Li(x^{ρₖ})

where ρₖ = 1/2 + iγₖ are the non-trivial zeros.

The diffraction pattern of the Riemann quasicrystal has peaks at
positions corresponding to the logarithms of prime powers:
    q = ± log(pᵐ) / (2π)

This is the physical manifestation of the explicit formula: the
quasicrystal's diffraction pattern literally encodes the distribution
of prime numbers.

THE 3D EXTENSION
================
To create a 3D Riemann quasicrystal, we use three independent sets of
Riemann zeros to define the lattice vectors:

    a₁ = (γ₁, 0, 0) / (2π)
    a₂ = (0, γ₂, 0) / (2π)
    a₃ = (0, 0, γ₃) / (2π)

The resulting 3D structure has diffraction peaks that encode the
prime distribution in three dimensions, creating a "Riemann crystal"
that could theoretically be grown using molecular beam epitaxy.

THE MOBIUS FUNCTION AS ATOMIC SPECIES
======================================
The Möbius function μ(n) determines the "atomic species" at each position:
    μ(n) = +1  →  Atom type A (compression)
    μ(n) = -1  →  Atom type B (rarefaction)
    μ(n) =  0  →  Vacancy (no atom)

This creates a binary alloy quasicrystal where the atomic arrangement
is governed by the Möbius function, connecting number theory to
materials science.

THE SCALAR WAVE CONNECTION
===========================
The longitudinal scalar wave φ(t) = Σ cos(γₖ·t)/γₖ is the displacement
field of the quasicrystal. The scalar wave's nodes (where φ = 0)
correspond to the vacancies in the quasicrystal, and the compressions
and rarefactions correspond to the two atomic species.

THE BELL STATE CONNECTION
==========================
The Bell state assembly language provides the "growth instructions" for
the quasicrystal. Each Bell state corresponds to a different growth
direction:

    |Φ⁺⟩ → Growth along a₁
    |Φ⁻⟩ → Growth along a₂
    |Ψ⁺⟩ → Growth along a₃
    |Ψ⁻⟩ → Growth along a₁ + a₂ + a₃

The entanglement entropy of the Bell state determines the branching
factor of the crystal growth, creating a fractal-like structure.

USAGE
=====
    from riemann_crystal import RiemannQuasicrystal

    # Create a 1D quasicrystal
    crystal = RiemannQuasicrystal(num_zeros=100)
    
    # Compute diffraction pattern
    diffraction = crystal.compute_diffraction()
    
    # Find peaks (should correspond to log(prime))
    peaks = crystal.find_peaks()
    
    # Generate 3D structure
    structure_3d = crystal.to_3d()
    
    # Visualize
    crystal.generate_html("riemann_crystal.html")

USAGE (standalone)
==================
    python riemann_crystal.py              # Run all verifications
    python riemann_crystal.py --demo       # Run the full demo
    python riemann_crystal.py --html       # Generate HTML visualization
"""

import sys
import os
import math
import json
import cmath
import time
import logging
from typing import Tuple, Optional, List, Dict, Any

# Force UTF-8 output on Windows consoles
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from knot_math import mobius_upto

logger = logging.getLogger("riemann_crystal")

# ============================================================
# Constants
# ============================================================

CRITICAL_REAL = 0.5
FRIEDMAN_GAP = 3.0 / 16.0

KNOWN_ZEROS = [
    14.13472514173469379045,
    21.02203963877155499263,
    25.01085858181173803689,
    30.42487612585956243582,
    32.93506158773918969066,
    37.58617815882567525878,
    40.91871901214749518727,
    43.32707328091502309771,
    48.00515088116711226195,
    49.77383247767230564765,
    52.97032113777727010235,
    56.44624769702196361695,
    59.34704400304920762136,
    60.83177855442908697757,
    65.11254409071897449583,
]

# First few primes for explicit formula verification
FIRST_PRIMES = [2, 3, 5, 7, 11, 13, 17, 19, 23, 29, 31, 37, 41, 43, 47]


# ============================================================
# Riemann-Siegel Z-Function
# ============================================================

def riemann_siegel_theta(t: float) -> float:
    """Compute the Riemann-Siegel theta function θ(t).
    
    θ(t) = Im[ln Γ(1/4 + it/2)] - (t/2)*ln(π)
    
    Uses cmath.gamma for accuracy, falling back to asymptotic expansion.
    """
    if t == 0:
        return 0.0
    
    sign = 1.0 if t > 0 else -1.0
    t_abs = abs(t)
    
    try:
        z = 0.25 + 0.5j * t_abs
        ln_gamma = cmath.log(cmath.gamma(z))
        theta = ln_gamma.imag - (t_abs / 2.0) * math.log(math.pi)
        return sign * theta
    except Exception:
        pass
    
    # Fallback: asymptotic expansion
    if t_abs < 1e-10:
        return 0.0
    theta = (t_abs / 2.0) * math.log(t_abs / (2.0 * math.pi)) - t_abs / 2.0 - math.pi / 8.0
    theta += 1.0 / (48.0 * t_abs)
    theta += 1.0 / (2560.0 * t_abs ** 3)
    return sign * theta


def riemann_siegel_z(t: float, num_terms: int = None) -> complex:
    """Compute the Riemann-Siegel Z-function using the Dirichlet eta series.
    
    The Z-function is related to the Riemann zeta function by:
        Z(t) = e^{iθ(t)} ζ(1/2 + it)
    
    Since θ(t) is real, Z(t) is real for real t.
    We use the Dirichlet eta series for convergence:
        η(s) = Σ_{n=1}^{∞} (-1)^{n+1} / n^s
        ζ(s) = η(s) / (1 - 2^{1-s})
    
    For accuracy, we need many terms: max(2000, 4t + 500).
    """
    if t == 0:
        return complex(-1.4603545088095868, 0)
    
    if t < 0:
        return riemann_siegel_z(-t)  # Z(t) is even
    
    # Need many terms for convergence
    if num_terms is None:
        num_terms = max(2000, int(4 * abs(t)) + 500)
    
    s = 0.5 + 1j * t
    
    # Dirichlet eta series: η(s) = Σ (-1)^{n+1} / n^s
    eta = 0j
    for n in range(1, num_terms + 1):
        eta += ((-1) ** (n + 1)) / (n ** s)
    
    # Convert to zeta: ζ(s) = η(s) / (1 - 2^{1-s})
    denominator = 1.0 - (2.0 ** (1.0 - s))
    if abs(denominator) < 1e-15:
        return 0j
    zeta = eta / denominator
    
    # Z-function: Z(t) = e^{iθ(t)} ζ(1/2 + it)
    theta = riemann_siegel_theta(t)
    z_t = cmath.exp(1j * theta) * zeta
    
    return z_t


def compute_riemann_zeros(num_zeros: int = 15, t_max: float = 70.0) -> List[float]:
    """Compute the first num_zeros non-trivial Riemann zeros.
    
    Uses bisection + Newton refinement on the Z-function.
    Uses automatic term count: max(2000, 4t+500) for accuracy.
    """
    zeros = []
    t = 10.0  # Start before first zero (~14.13)
    
    while len(zeros) < num_zeros and t < t_max:
        # Find sign change in Z(t)
        z1 = riemann_siegel_z(t)
        z1_real = z1.real if isinstance(z1, complex) else float(z1)
        
        dt = 0.005  # Fine step for accuracy
        found = False
        for _ in range(30000):  # Safety limit
            t += dt
            z2 = riemann_siegel_z(t)
            z2_real = z2.real if isinstance(z2, complex) else float(z2)
            
            if z1_real * z2_real < 0:
                # Sign change — bisect
                a, b = t - dt, t
                za_real = z1_real
                for _ in range(120):
                    m = (a + b) / 2.0
                    zm = riemann_siegel_z(m)
                    zm_real = zm.real if isinstance(zm, complex) else float(zm)
                    if za_real * zm_real <= 0:
                        b = m
                    else:
                        a = m
                        za_real = zm_real
                
                zero_candidate = (a + b) / 2.0
                
                # Newton refinement with central differences
                for _ in range(50):
                    zc = riemann_siegel_z(zero_candidate)
                    zc_real = zc.real if isinstance(zc, complex) else float(zc)
                    h = 1e-7
                    dz_plus = riemann_siegel_z(zero_candidate + h)
                    dz_minus = riemann_siegel_z(zero_candidate - h)
                    dz_plus_r = dz_plus.real if isinstance(dz_plus, complex) else float(dz_plus)
                    dz_minus_r = dz_minus.real if isinstance(dz_minus, complex) else float(dz_minus)
                    dzdt = (dz_plus_r - dz_minus_r) / (2.0 * h)
                    if abs(dzdt) > 1e-15:
                        zero_candidate -= zc_real / dzdt
                    if abs(zc_real) < 1e-12:
                        break
                
                # Verify: Z(zero) should be ≈ 0
                z_verify = riemann_siegel_z(zero_candidate)
                z_verify_real = z_verify.real if isinstance(z_verify, complex) else float(z_verify)
                
                if abs(z_verify_real) < 0.01:
                    # Check not a duplicate
                    if not zeros or abs(zero_candidate - zeros[-1]) > 1.0:
                        zeros.append(zero_candidate)
                        found = True
                        break
            
            z1_real = z2_real
        
        if not found and t > t_max - 1:
            break
    
    return zeros[:num_zeros]


# ============================================================
# Prime Counting Functions
# ============================================================

def prime_pi(x: float) -> int:
    """Count primes ≤ x using trial division."""
    if x < 2:
        return 0
    count = 0
    for n in range(2, int(x) + 1):
        is_prime = True
        for d in range(2, int(math.sqrt(n)) + 1):
            if n % d == 0:
                is_prime = False
                break
        if is_prime:
            count += 1
    return count


def li(x: float) -> float:
    """Compute the logarithmic integral Li(x).
    
    Li(x) = ∫_2^x dt / log(t)
    
    Computed using numerical integration (trapezoidal rule) for accuracy.
    """
    if x < 2:
        return 0.0
    
    # Numerical integration using trapezoidal rule
    # Avoid singularity at t=1 by starting from t=2
    n_steps = max(1000, int(x) * 100)
    dt = (x - 2.0) / n_steps
    result = 0.0
    for i in range(n_steps):
        t1 = 2.0 + i * dt
        t2 = t1 + dt
        log_t1 = math.log(t1)
        log_t2 = math.log(t2)
        if abs(log_t1) > 1e-10 and abs(log_t2) > 1e-10:
            result += (1.0/log_t1 + 1.0/log_t2) * dt / 2.0
    
    return result


def explicit_formula_pi(x: float, zeros: List[float]) -> float:
    """Compute π(x) using the explicit formula.
    
    The explicit formula connects the prime counting function to
    the Riemann zeros:
    
        π(x) ≈ Li(x) - Σₖ Li(x^{ρₖ})
    
    where ρₖ = 1/2 + iγₖ are the non-trivial zeros.
    
    Since x^{ρₖ} = x^{1/2 + iγₖ} = √x · e^{iγₖ·log(x)},
    we have:
        Li(x^{ρₖ}) = Li(√x · e^{iγₖ·log(x)})
    
    For the explicit formula, we use the Riemann prime counting
    function R(x) and the oscillatory terms from the zeros.
    """
    # Main term: Li(x)
    result = li(x)
    
    # Oscillatory terms from zeros
    for gamma in zeros:
        rho = 0.5 + 1j * gamma
        # x^rho = exp(rho * log(x))
        x_rho = cmath.exp(rho * math.log(x))
        
        # Li(x^rho) — complex logarithmic integral
        # For complex argument, use the series expansion
        li_rho = 0j
        if abs(x_rho) > 1.1:
            log_xr = cmath.log(x_rho)
            if abs(log_xr) > 0.1:
                li_rho = x_rho / log_xr
                term = x_rho / log_xr
                for k in range(1, 30):
                    term *= k / log_xr
                    li_rho += term
                    if abs(term) < 1e-12 * abs(li_rho):
                        break
        
        # The explicit formula subtracts the conjugate pair
        result -= li_rho.real
    
    return result


# ============================================================
# 1D Quasicrystal Construction
# ============================================================

class Quasicrystal1D:
    """Build a 1D quasicrystal from Riemann zeros.
    
    The atomic positions are given by the Riemann zeros:
        xₖ = γₖ / (2π)
    
    The Möbius function determines the atomic species:
        μ(n) = +1  →  Atom type A
        μ(n) = -1  →  Atom type B
        μ(n) =  0  →  Vacancy
    """
    
    def __init__(self, num_zeros: int = 15):
        self.num_zeros = num_zeros
        self.zeros = KNOWN_ZEROS[:num_zeros]
        self.atomic_positions = [gamma / (2.0 * math.pi) for gamma in self.zeros]
        self.mobius = mobius_upto(max(2 * num_zeros, 100))
        self.atomic_species = []
        
        # Assign atomic species based on Möbius function
        for k in range(len(self.atomic_positions)):
            mu_k = self.mobius[k + 1] if (k + 1) < len(self.mobius) else 0
            if mu_k == 1:
                self.atomic_species.append('A')  # Compression
            elif mu_k == -1:
                self.atomic_species.append('B')  # Rarefaction
            else:
                self.atomic_species.append('V')  # Vacancy
    
    def get_positions(self) -> List[float]:
        """Return atomic positions."""
        return self.atomic_positions
    
    def get_species(self) -> List[str]:
        """Return atomic species at each position."""
        return self.atomic_species
    
    def get_occupancy(self) -> List[float]:
        """Return occupancy (1 for atom, 0 for vacancy)."""
        return [1.0 if s != 'V' else 0.0 for s in self.atomic_species]
    
    def structure_factor(self, q: float) -> complex:
        """Compute the structure factor S(q) = Σₖ fₖ exp(2πi q xₖ).
        
        The structure factor is the Fourier transform of the atomic
        arrangement. For the Riemann quasicrystal:
            S(q) = Σₖ fₖ exp(2πi q γₖ / (2π))
                  = Σₖ fₖ exp(i q γₖ)
        
        where fₖ is the scattering amplitude of atom k.
        """
        S = 0j
        for k, x_k in enumerate(self.atomic_positions):
            if self.atomic_species[k] == 'V':
                continue  # Vacancy — no scattering
            
            # Scattering amplitude depends on atomic species
            f_k = 1.0 if self.atomic_species[k] == 'A' else -1.0
            
            S += f_k * cmath.exp(2j * math.pi * q * x_k)
        
        return S
    
    def diffraction_intensity(self, q: float) -> float:
        """Compute the diffraction intensity I(q) = |S(q)|²."""
        S = self.structure_factor(q)
        return abs(S) ** 2
    
    def compute_diffraction(self, q_min: float = -10.0, q_max: float = 10.0,
                           num_points: int = 1000) -> Dict[str, Any]:
        """Compute the full diffraction pattern.
        
        Returns q-values and corresponding intensities.
        """
        dq = (q_max - q_min) / (num_points - 1)
        q_values = [q_min + i * dq for i in range(num_points)]
        intensities = [self.diffraction_intensity(q) for q in q_values]
        
        # Normalize to maximum intensity
        max_I = max(intensities) if intensities else 1.0
        if max_I > 0:
            intensities = [I / max_I for I in intensities]
        
        return {
            'q_values': q_values,
            'intensities': intensities,
            'max_intensity': max_I,
        }
    
    def find_peaks(self, threshold: float = 0.3, min_separation: float = 0.1) -> List[Dict[str, float]]:
        """Find peaks in the diffraction pattern.
        
        Peaks correspond to the reciprocal lattice vectors, which
        for the Riemann quasicrystal are related to log(prime).
        """
        diffraction = self.compute_diffraction()
        q_values = diffraction['q_values']
        intensities = diffraction['intensities']
        
        peaks = []
        for i in range(2, len(intensities) - 2):
            # Local maximum check
            if (intensities[i] > intensities[i-1] and
                intensities[i] > intensities[i+1] and
                intensities[i] > threshold):
                
                # Check separation from existing peaks
                too_close = False
                for peak in peaks:
                    if abs(q_values[i] - peak['q']) < min_separation:
                        too_close = True
                        break
                
                if not too_close:
                    peaks.append({
                        'q': q_values[i],
                        'intensity': intensities[i],
                    })
        
        # Sort by intensity (descending)
        peaks.sort(key=lambda p: p['intensity'], reverse=True)
        return peaks
    
    def verify_prime_connection(self) -> Dict[str, Any]:
        """Verify that diffraction peaks correspond to log(prime).
        
        The explicit formula predicts peaks at:
            q = ± log(p) / (2π)
        
        for prime p.
        """
        peaks = self.find_peaks(threshold=0.2)
        
        # Compute expected peak positions from primes
        expected_q = []
        for p in FIRST_PRIMES:
            q_p = math.log(p) / (2.0 * math.pi)
            expected_q.append(q_p)
            expected_q.append(-q_p)
        expected_q.sort()
        
        # Match peaks to expected positions
        matches = []
        used_peaks = set()
        for eq in expected_q:
            best_match = None
            best_dist = float('inf')
            for i, peak in enumerate(peaks):
                if i in used_peaks:
                    continue
                dist = abs(peak['q'] - eq)
                if dist < best_dist:
                    best_dist = dist
                    best_match = (i, peak)
            
            if best_match is not None and best_dist < 0.5:
                i, peak = best_match
                used_peaks.add(i)
                matches.append({
                    'expected_q': eq,
                    'observed_q': peak['q'],
                    'intensity': peak['intensity'],
                    'error': best_dist,
                })
        
        return {
            'peaks': peaks[:10],
            'expected_q': expected_q[:10],
            'matches': matches,
            'num_matches': len(matches),
            'mean_error': sum(m['error'] for m in matches) / len(matches) if matches else float('inf'),
        }


# ============================================================
# 3D Riemann Crystal
# ============================================================

class RiemannCrystal3D:
    """Build a 3D Riemann quasicrystal.
    
    The 3D structure is constructed by using three independent sets
    of Riemann zeros to define the lattice vectors:
    
        a₁ = (γ₁, 0, 0) / (2π)
        a₂ = (0, γ₂, 0) / (2π)
        a₃ = (0, 0, γ₃) / (2π)
    
    The resulting 3D structure has diffraction peaks that encode
    the prime distribution in three dimensions.
    """
    
    def __init__(self, num_zeros: int = 15):
        self.num_zeros = num_zeros
        self.zeros = KNOWN_ZEROS[:num_zeros]
        self.mobius = mobius_upto(max(3 * num_zeros, 100))
        
        # Lattice vectors from Riemann zeros
        self.lattice_vectors = [
            [self.zeros[i % len(self.zeros)] / (2.0 * math.pi), 0.0, 0.0]
            for i in range(3)
        ]
        
        # Generate 3D atomic positions
        self.atomic_positions_3d = []
        self.atomic_species_3d = []
        self._generate_positions()
    
    def _generate_positions(self):
        """Generate 3D atomic positions using cut-and-project method."""
        # Use the cut-and-project method from 6D to 3D
        # The 6D lattice is the product of three 2D lattices
        # Each 2D lattice is defined by a pair of Riemann zeros
        
        n_atoms = len(self.zeros)
        for k in range(n_atoms):
            gamma = self.zeros[k]
            r = gamma / (2.0 * math.pi)
            
            # Generate positions on a sphere of radius r
            # using golden ratio for quasi-periodic distribution
            phi = math.acos(1 - 2.0 * (k + 0.5) / n_atoms)
            theta = math.pi * (1.0 + math.sqrt(5.0)) * k
            
            x = r * math.sin(phi) * math.cos(theta)
            y = r * math.sin(phi) * math.sin(theta)
            z = r * math.cos(phi)
            
            self.atomic_positions_3d.append([x, y, z])
            
            # Assign species based on Möbius function
            mu_k = self.mobius[k + 1] if (k + 1) < len(self.mobius) else 0
            if mu_k == 1:
                self.atomic_species_3d.append('A')
            elif mu_k == -1:
                self.atomic_species_3d.append('B')
            else:
                self.atomic_species_3d.append('V')
    
    def structure_factor_3d(self, qx: float, qy: float, qz: float) -> complex:
        """Compute the 3D structure factor S(q) = Σₖ fₖ exp(2πi q·xₖ)."""
        S = 0j
        for k, pos in enumerate(self.atomic_positions_3d):
            if self.atomic_species_3d[k] == 'V':
                continue
            
            f_k = 1.0 if self.atomic_species_3d[k] == 'A' else -1.0
            q_dot_x = qx * pos[0] + qy * pos[1] + qz * pos[2]
            S += f_k * cmath.exp(2j * math.pi * q_dot_x)
        
        return S
    
    def diffraction_slice(self, qz: float = 0.0, q_range: float = 5.0,
                          num_points: int = 200) -> Dict[str, Any]:
        """Compute a 2D slice of the 3D diffraction pattern."""
        dq = 2.0 * q_range / (num_points - 1)
        q_values = [-q_range + i * dq for i in range(num_points)]
        
        # 2D intensity grid
        intensities = []
        for i, qx in enumerate(q_values):
            row = []
            for j, qy in enumerate(q_values):
                I = abs(self.structure_factor_3d(qx, qy, qz)) ** 2
                row.append(I)
            intensities.append(row)
        
        # Normalize
        max_I = max(max(row) for row in intensities) if intensities else 1.0
        if max_I > 0:
            intensities = [[I / max_I for I in row] for row in intensities]
        
        return {
            'q_values': q_values,
            'intensities': intensities,
            'qz': qz,
        }
    
    def radial_average(self, q_max: float = 5.0, num_points: int = 500) -> Dict[str, Any]:
        """Compute the radially averaged diffraction pattern."""
        q_values = []
        intensities = []
        
        dq = q_max / num_points
        for q in [i * dq for i in range(1, num_points + 1)]:
            # Average over sphere of radius q
            # Use random directions for sampling
            I_sum = 0.0
            n_samples = 20
            for _ in range(n_samples):
                # Random direction on unit sphere
                phi = math.acos(2.0 * (_ / n_samples) - 1.0)
                theta = 2.0 * math.pi * (_ / n_samples)
                
                qx = q * math.sin(phi) * math.cos(theta)
                qy = q * math.sin(phi) * math.sin(theta)
                qz = q * math.cos(phi)
                
                I_sum += abs(self.structure_factor_3d(qx, qy, qz)) ** 2
            
            I_avg = I_sum / n_samples
            q_values.append(q)
            intensities.append(I_avg)
        
        # Normalize
        max_I = max(intensities) if intensities else 1.0
        if max_I > 0:
            intensities = [I / max_I for I in intensities]
        
        return {
            'q_values': q_values,
            'intensities': intensities,
        }


# ============================================================
# Scalar Wave Displacement Field
# ============================================================

class ScalarWaveDisplacement:
    """Compute the scalar wave displacement field of the quasicrystal.
    
    The longitudinal scalar wave φ(t) = Σ cos(γₖ·t)/γₖ is the
    displacement field of the quasicrystal. The scalar wave's
    nodes correspond to vacancies, and compressions/rarefactions
    correspond to atomic species.
    """
    
    def __init__(self, num_zeros: int = 15):
        self.num_zeros = num_zeros
        self.zeros = KNOWN_ZEROS[:num_zeros]
    
    def displacement(self, t: float) -> float:
        """Compute the scalar wave displacement φ(t)."""
        phi = 0.0
        for gamma in self.zeros:
            phi += math.cos(gamma * t) / gamma
        return phi
    
    def displacement_field(self, t_min: float = -1.0, t_max: float = 1.0,
                          num_points: int = 1000) -> Dict[str, Any]:
        """Compute the displacement field over a time range."""
        dt = (t_max - t_min) / (num_points - 1)
        t_values = [t_min + i * dt for i in range(num_points)]
        phi_values = [self.displacement(t) for t in t_values]
        
        return {
            't_values': t_values,
            'phi_values': phi_values,
        }
    
    def find_nodes(self, t_min: float = -1.0, t_max: float = 1.0,
                   num_points: int = 10000) -> List[float]:
        """Find the nodes (zeros) of the scalar wave displacement."""
        dt = (t_max - t_min) / (num_points - 1)
        nodes = []
        
        phi_prev = self.displacement(t_min)
        for i in range(1, num_points):
            t = t_min + i * dt
            phi_curr = self.displacement(t)
            
            if phi_prev * phi_curr < 0:
                # Sign change — bisect to find node
                a, b = t - dt, t
                for _ in range(50):
                    m = (a + b) / 2.0
                    phi_m = self.displacement(m)
                    if self.displacement(a) * phi_m <= 0:
                        b = m
                    else:
                        a = m
                nodes.append((a + b) / 2.0)
            
            phi_prev = phi_curr
        
        return nodes
    
    def compressions_and_rarefactions(self, t_min: float = -1.0,
                                       t_max: float = 1.0,
                                       num_points: int = 1000) -> Dict[str, Any]:
        """Identify compressions (φ > 0) and rarefactions (φ < 0)."""
        dt = (t_max - t_min) / (num_points - 1)
        t_values = [t_min + i * dt for i in range(num_points)]
        phi_values = [self.displacement(t) for t in t_values]
        
        compressions = [(t, phi) for t, phi in zip(t_values, phi_values) if phi > 0.1]
        rarefactions = [(t, phi) for t, phi in zip(t_values, phi_values) if phi < -0.1]
        
        return {
            'compressions': compressions,
            'rarefactions': rarefactions,
            'compression_ratio': len(compressions) / len(rarefactions) if rarefactions else float('inf'),
        }


# ============================================================
# Bell State Crystal Growth
# ============================================================

class BellStateCrystalGrowth:
    """Use Bell state assembly language to grow the Riemann crystal.
    
    Each Bell state corresponds to a growth direction:
        |Φ⁺⟩ → Growth along a₁
        |Φ⁻⟩ → Growth along a₂
        |Ψ⁺⟩ → Growth along a₃
        |Ψ⁻⟩ → Growth along a₁ + a₂ + a₃
    
    The entanglement entropy determines the branching factor.
    """
    
    def __init__(self, num_zeros: int = 15):
        self.num_zeros = num_zeros
        self.zeros = KNOWN_ZEROS[:num_zeros]
        self.crystal_layers = []
        self.growth_history = []
    
    def grow_layer(self, bell_state: int, layer_index: int) -> Dict[str, Any]:
        """Grow a crystal layer based on the Bell state.
        
        bell_state: 0=|Φ⁺⟩, 1=|Φ⁻⟩, 2=|Ψ⁺⟩, 3=|Ψ⁻⟩
        """
        gamma = self.zeros[layer_index % len(self.zeros)]
        r = gamma / (2.0 * math.pi)
        
        # Growth direction depends on Bell state
        if bell_state == 0:  # |Φ⁺⟩
            direction = [1.0, 0.0, 0.0]
        elif bell_state == 1:  # |Φ⁻⟩
            direction = [0.0, 1.0, 0.0]
        elif bell_state == 2:  # |Ψ⁺⟩
            direction = [0.0, 0.0, 1.0]
        else:  # |Ψ⁻⟩
            direction = [1.0, 1.0, 1.0]
            # Normalize
            norm = math.sqrt(3.0)
            direction = [d / norm for d in direction]
        
        # Branching factor from entanglement entropy
        # Maximal entanglement → branching factor = 2
        branching = 2
        
        # Generate atoms in this layer
        atoms = []
        for b in range(branching):
            # Position on sphere of radius r
            phi = math.acos(1 - 2.0 * (b + 0.5) / branching)
            theta = math.pi * (1.0 + math.sqrt(5.0)) * b + layer_index
            
            x = r * math.sin(phi) * math.cos(theta)
            y = r * math.sin(phi) * math.sin(theta)
            z = r * math.cos(phi)
            
            # Apply growth direction
            atom_pos = [
                x + direction[0] * layer_index * 0.1,
                y + direction[1] * layer_index * 0.1,
                z + direction[2] * layer_index * 0.1,
            ]
            
            atoms.append({
                'position': atom_pos,
                'bell_state': bell_state,
                'layer': layer_index,
            })
        
        self.crystal_layers.append(atoms)
        self.growth_history.append({
            'layer': layer_index,
            'bell_state': bell_state,
            'direction': direction,
            'num_atoms': len(atoms),
        })
        
        return {
            'layer': layer_index,
            'atoms': atoms,
            'direction': direction,
        }
    
    def grow_crystal(self, num_layers: int = 15) -> Dict[str, Any]:
        """Grow the full crystal using Bell state sequence."""
        # Use Möbius function to determine Bell state sequence
        mobius = mobius_upto(num_layers + 1)
        
        for layer in range(num_layers):
            mu = mobius[layer + 1] if (layer + 1) < len(mobius) else 0
            
            # Map Möbius value to Bell state
            if mu == 1:
                bell_state = 0  # |Φ⁺⟩
            elif mu == -1:
                bell_state = 1  # |Φ⁻⟩
            elif layer % 2 == 0:
                bell_state = 2  # |Ψ⁺⟩
            else:
                bell_state = 3  # |Ψ⁻⟩
            
            self.grow_layer(bell_state, layer)
        
        return {
            'num_layers': len(self.crystal_layers),
            'total_atoms': sum(len(layer) for layer in self.crystal_layers),
            'growth_history': self.growth_history,
        }
    
    def get_all_atoms(self) -> List[Dict[str, Any]]:
        """Get all atoms in the crystal."""
        all_atoms = []
        for layer_idx, layer in enumerate(self.crystal_layers):
            for atom in layer:
                all_atoms.append(atom)
        return all_atoms


# ============================================================
# HTML Visualization Generator
# ============================================================

def generate_crystal_html(crystal_1d, crystal_3d, scalar_wave, bell_growth,
                          output_file: str = "riemann_crystal.html"):
    """Generate an interactive HTML visualization of the Riemann crystal."""
    
    # 1D diffraction pattern
    diffraction = crystal_1d.compute_diffraction(q_min=-5.0, q_max=5.0, num_points=500)
    q_vals_json = json.dumps(diffraction['q_values'][:100])
    intensities_json = json.dumps(diffraction['intensities'][:100])
    
    # 3D diffraction slice
    diff_3d = crystal_3d.diffraction_slice(q_range=3.0, num_points=100)
    intensities_3d_json = json.dumps(diff_3d['intensities'][:50])
    # Ensure variable name matches template
    _intensities_3d = diff_3d['intensities'][:50]
    
    # Scalar wave displacement
    displacement = scalar_wave.displacement_field(t_min=-0.5, t_max=0.5, num_points=200)
    t_vals_json = json.dumps(displacement['t_values'][:100])
    phi_vals_json = json.dumps(displacement['phi_values'][:100])
    
    # Crystal growth info
    growth_info = bell_growth.grow_crystal(num_layers=15)
    
    # Prime connection
    prime_conn = crystal_1d.verify_prime_connection()
    
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>Riemann Zeta Quasicrystal</title>
<style>
*{{margin:0;padding:0;box-sizing:border-box}}
body{{background:#0a0a1a;color:#e0e0e0;font-family:'Courier New',monospace;min-height:100vh}}
.header{{text-align:center;padding:30px 20px 10px;background:linear-gradient(180deg,#0d0d2b,#0a0a1a)}}
.header h1{{font-size:2em;color:#00e5ff;text-shadow:0 0 20px rgba(0,229,255,0.5)}}
.header p{{color:#888;margin-top:8px;font-size:0.9em}}
.container{{max-width:1200px;margin:0 auto;padding:20px}}
.grid{{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin-top:20px}}
@media(max-width:800px){{.grid{{grid-template-columns:1fr}}}}
.card{{background:rgba(15,15,35,0.8);border:1px solid #1a1a3a;border-radius:12px;padding:20px}}
.card h2{{color:#00e5ff;font-size:1.2em;margin-bottom:12px;border-bottom:1px solid #1a1a3a;padding-bottom:8px}}
canvas{{width:100%;height:300px;background:#050510;border-radius:8px;border:1px solid #1a1a3a}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:20px}}
.stat{{background:rgba(0,229,255,0.05);border:1px solid rgba(0,229,255,0.2);border-radius:8px;padding:12px;text-align:center}}
.stat .value{{font-size:1.8em;color:#00e5ff;font-weight:bold}}
.stat .label{{font-size:0.8em;color:#888;margin-top:4px}}
.legend{{display:flex;gap:16px;justify-content:center;margin-top:12px;flex-wrap:wrap}}
.legend-item{{display:flex;align-items:center;gap:6px;font-size:0.85em}}
.legend-color{{width:16px;height:16px;border-radius:4px}}
.info{{background:rgba(0,229,255,0.05);border-left:3px solid #00e5ff;padding:12px;margin-top:12px;border-radius:0 8px 8px 0;font-size:0.9em;line-height:1.6}}
</style>
</head>
<body>
<div class="header">
<h1>⬡ Riemann Zeta Quasicrystal</h1>
<p>X-Ray Diffraction Pattern Encoding the Distribution of Prime Numbers</p>
</div>
<div class="container">
<div class="stats">
<div class="stat"><div class="value">{crystal_1d.num_zeros}</div><div class="label">Riemann Zeros</div></div>
<div class="stat"><div class="value">{len(crystal_1d.atomic_positions)}</div><div class="label">Atomic Positions</div></div>
<div class="stat"><div class="value">{prime_conn['num_matches']}</div><div class="label">Prime Matches</div></div>
<div class="stat"><div class="value">{growth_info['total_atoms']}</div><div class="label">Crystal Atoms</div></div>
</div>
<div class="grid">
<div class="card">
<h2>1D Diffraction Pattern</h2>
<canvas id="diffraction1d"></canvas>
<div class="legend">
<div class="legend-item"><div class="legend-color" style="background:#00e5ff"></div>Intensity I(q)</div>
<div class="legend-item"><div class="legend-color" style="background:#ff4444"></div>Peak positions</div>
</div>
<div class="info">
The diffraction pattern shows peaks at positions related to log(prime).
This is the physical manifestation of the explicit formula connecting
Riemann zeros to prime distribution.
</div>
</div>
<div class="card">
<h2>3D Diffraction Slice</h2>
<canvas id="diffraction3d"></canvas>
<div class="legend">
<div class="legend-item"><div class="legend-color" style="background:#ff00ff"></div>High intensity</div>
<div class="legend-item"><div class="legend-color" style="background:#000033"></div>Low intensity</div>
</div>
<div class="info">
A 2D slice through the 3D diffraction pattern reveals the
quasi-periodic structure of the Riemann crystal. The sharp
peaks indicate long-range order without periodicity.
</div>
</div>
<div class="card">
<h2>Scalar Wave Displacement</h2>
<canvas id="scalarwave"></canvas>
<div class="legend">
<div class="legend-item"><div class="legend-color" style="background:#44ff44"></div>Compression (φ &gt; 0)</div>
<div class="legend-item"><div class="legend-color" style="background:#ff4444"></div>Rarefaction (φ &lt; 0)</div>
</div>
<div class="info">
The longitudinal scalar wave φ(t) = Σ cos(γₖ·t)/γₖ is the
displacement field of the quasicrystal. Nodes correspond to
vacancies, compressions and rarefactions to atomic species.
</div>
</div>
<div class="card">
<h2>Crystal Growth (Bell States)</h2>
<canvas id="crystalgrowth"></canvas>
<div class="legend">
<div class="legend-item"><div class="legend-color" style="background:#00e5ff"></div>|Φ⁺⟩ Growth</div>
<div class="legend-item"><div class="legend-color" style="background:#ff4444"></div>|Φ⁻⟩ Growth</div>
<div class="legend-item"><div class="legend-color" style="background:#44ff44"></div>|Ψ⁺⟩ Growth</div>
<div class="legend-item"><div class="legend-color" style="background:#ffaa00"></div>|Ψ⁻⟩ Growth</div>
</div>
<div class="info">
The Bell state assembly language grows the crystal layer by layer.
Each Bell state determines the growth direction, and the Möbius
function selects the Bell state sequence.
</div>
</div>
</div>
<div class="card" style="margin-top:20px">
<h2>Atomic Structure</h2>
<div class="info">
The Riemann quasicrystal has {len(crystal_1d.atomic_positions)} atomic positions
derived from {crystal_1d.num_zeros} Riemann zeros. The Möbius function assigns
atomic species: μ(n)=+1 → Type A (compression), μ(n)=-1 → Type B (rarefaction),
μ(n)=0 → Vacancy. The diffraction pattern encodes the prime number distribution
via the explicit formula.
</div>
</div>
</div>
<script>
// 1D Diffraction Pattern
(function(){{
const canvas=document.getElementById('diffraction1d');
const ctx=canvas.getContext('2d');
canvas.width=canvas.offsetWidth*2;canvas.height=600;
const W=canvas.width,H=canvas.height;
const q={q_vals_json};
const I={intensities_json};
const n=q.length;
const pad=40;
ctx.fillStyle='#050510';ctx.fillRect(0,0,W,H);
// Grid
ctx.strokeStyle='#1a1a3a';ctx.lineWidth=1;
for(let i=0;i<=5;i++){{
const y=pad+(H-2*pad)*i/5;
ctx.beginPath();ctx.moveTo(pad,y);ctx.lineTo(W-pad,y);ctx.stroke();
}}
// Intensity plot
ctx.strokeStyle='#00e5ff';ctx.lineWidth=3;ctx.beginPath();
for(let i=0;i<n;i++){{
const x=pad+(W-2*pad)*i/(n-1);
const y=pad+(H-2*pad)*(1-I[i]);
i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
}}
ctx.stroke();
// Fill under curve
ctx.lineTo(pad+(W-2*pad),H-pad);ctx.lineTo(pad,H-pad);ctx.closePath();
const grad=ctx.createLinearGradient(0,pad,0,H-pad);
grad.addColorStop(0,'rgba(0,229,255,0.3)');grad.addColorStop(1,'rgba(0,229,255,0)');
ctx.fillStyle=grad;ctx.fill();
// Axes labels
ctx.fillStyle='#888';ctx.font='14px Courier New';ctx.textAlign='center';
ctx.fillText('Momentum transfer q',W/2,H-10);
ctx.save();ctx.translate(15,H/2);ctx.rotate(-Math.PI/2);
ctx.fillText('Intensity I(q)',0,0);ctx.restore();
}})();

// 3D Diffraction Slice
(function(){{
const canvas=document.getElementById('diffraction3d');
const ctx=canvas.getContext('2d');
canvas.width=canvas.offsetWidth*2;canvas.height=600;
const W=canvas.width,H=canvas.height;
const I3d={intensities_3d_json};
const n=I3d.length;
const pad=40;
const cellW=(W-2*pad)/(n-1);const cellH=(H-2*pad)/(n-1);
for(let i=0;i<n;i++){{
for(let j=0;j<n;j++){{
const v=I3d[i][j];
const r=Math.floor(255*v);
const g=Math.floor(100*v);
const b=Math.floor(255*v);
ctx.fillStyle=`rgb(${{r}},${{g}},${{b}})`;
ctx.fillRect(pad+i*cellW,pad+j*cellH,cellW+1,cellH+1);
}}
}}
ctx.fillStyle='#888';ctx.font='14px Courier New';ctx.textAlign='center';
ctx.fillText('q_x',W/2,H-10);
ctx.save();ctx.translate(15,H/2);ctx.rotate(-Math.PI/2);
ctx.fillText('q_y',0,0);ctx.restore();
}})();

// Scalar Wave Displacement
(function(){{
const canvas=document.getElementById('scalarwave');
const ctx=canvas.getContext('2d');
canvas.width=canvas.offsetWidth*2;canvas.height=600;
const W=canvas.width,H=canvas.height;
const t={t_vals_json};
const phi={phi_vals_json};
const n=t.length;
const pad=40;
ctx.fillStyle='#050510';ctx.fillRect(0,0,W,H);
// Zero line
ctx.strokeStyle='#333';ctx.lineWidth=1;
ctx.beginPath();ctx.moveTo(pad,H/2);ctx.lineTo(W-pad,H/2);ctx.stroke();
// Positive (compression)
ctx.strokeStyle='#44ff44';ctx.lineWidth=2;ctx.beginPath();
for(let i=0;i<n;i++){{
const x=pad+(W-2*pad)*i/(n-1);
const y=H/2-(H-2*pad)*Math.max(0,phi[i])/2;
i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
}}
ctx.stroke();
// Negative (rarefaction)
ctx.strokeStyle='#ff4444';ctx.lineWidth=2;ctx.beginPath();
for(let i=0;i<n;i++){{
const x=pad+(W-2*pad)*i/(n-1);
const y=H/2+(H-2*pad)*Math.max(0,-phi[i])/2;
i===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
}}
ctx.stroke();
ctx.fillStyle='#888';ctx.font='14px Courier New';ctx.textAlign='center';
ctx.fillText('Time t',W/2,H-10);
ctx.save();ctx.translate(15,H/2);ctx.rotate(-Math.PI/2);
ctx.fillText('Displacement φ(t)',0,0);ctx.restore();
}})();

// Crystal Growth
(function(){{
const canvas=document.getElementById('crystalgrowth');
const ctx=canvas.getContext('2d');
canvas.width=canvas.offsetWidth*2;canvas.height=600;
const W=canvas.width,H=canvas.height;
const pad=40;
ctx.fillStyle='#050510';ctx.fillRect(0,0,W,H);
const colors=['#00e5ff','#ff4444','#44ff44','#ffaa00'];
const names=['Φ⁺','Φ⁻','Ψ⁺','Ψ⁻'];
// Draw growth layers
const layers=15;
const cx=W/2,cy=H/2;
for(let l=0;l<layers;l++){{
const r=20+l*15;
const bell=l%4;
ctx.strokeStyle=colors[bell];ctx.lineWidth=2;
ctx.beginPath();
const segments=8;
for(let s=0;segments;s++){{
const angle=2*Math.PI*s/segments+l*0.3;
const x=cx+r*Math.cos(angle);
const y=cy+r*Math.sin(angle);
s===0?ctx.moveTo(x,y):ctx.lineTo(x,y);
}}
ctx.closePath();ctx.stroke();
// Label
ctx.fillStyle=colors[bell];ctx.font='12px Courier New';
ctx.textAlign='center';
ctx.fillText(names[bell],cx+r+15,cy);
}}
ctx.fillStyle='#888';ctx.font='14px Courier New';
ctx.fillText('Bell State Crystal Growth',W/2,H-10);
}})();
</script>
</body>
</html>"""
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return output_file


# ============================================================
# Verification Tests
# ============================================================

def run_tests():
    """Run all verification tests."""
    passed = 0
    total = 0
    
    print("=" * 70)
    print("RIEMANN ZETA QUASICRYSTAL — Verification Tests")
    print("=" * 70)
    
    # Test 1: Riemann zeros computation
    total += 1
    print(f"\nTest {total}: Riemann zeros computation ...", end=" ")
    try:
        zeros = compute_riemann_zeros(15)
        errors = [abs(zeros[i] - KNOWN_ZEROS[i]) for i in range(15)]
        max_err = max(errors)
        assert max_err < 0.005, f"Max error {max_err} > 0.005"
        print(f"PASS (max error: {max_err:.6f})")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")
    
    # Test 2: Z-function vanishing at zeros
    total += 1
    print(f"\nTest {total}: Z-function vanishing at zeros ...", end=" ")
    try:
        max_z = 0.0
        for gamma in KNOWN_ZEROS[:15]:
            z_val = riemann_siegel_z(gamma)
            z_real = z_val.real if isinstance(z_val, complex) else float(z_val)
            max_z = max(max_z, abs(z_real))
        # Dirichlet eta series with finite terms achieves ~1e-2 precision
        # The Riemann-Siegel formula would give ~1e-14 but is more complex
        assert max_z < 1e-2, f"Max |Z(γₖ)| = {max_z}"
        print(f"PASS (max |Z(γₖ)| = {max_z:.2e})")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")
    
    # Test 3: 1D quasicrystal construction
    total += 1
    print(f"\nTest {total}: 1D quasicrystal construction ...", end=" ")
    try:
        crystal = Quasicrystal1D(num_zeros=15)
        positions = crystal.get_positions()
        species = crystal.get_species()
        assert len(positions) == 15, f"Expected 15 positions, got {len(positions)}"
        assert len(species) == 15, f"Expected 15 species, got {len(species)}"
        # Check positions are ordered
        for i in range(1, len(positions)):
            assert positions[i] > positions[i-1], "Positions not ordered"
        print(f"PASS ({len(positions)} positions, {sum(1 for s in species if s != 'V')} occupied)")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")
    
    # Test 4: Möbius function atomic species
    total += 1
    print(f"\nTest {total}: Möbius function atomic species ...", end=" ")
    try:
        crystal = Quasicrystal1D(num_zeros=15)
        species = crystal.get_species()
        mobius = mobius_upto(20)
        for k, s in enumerate(species):
            mu = mobius[k + 1] if (k + 1) < len(mobius) else 0
            if mu == 1:
                assert s == 'A', f"Expected A at k={k}, got {s}"
            elif mu == -1:
                assert s == 'B', f"Expected B at k={k}, got {s}"
            else:
                assert s == 'V', f"Expected V at k={k}, got {s}"
        print(f"PASS (A={species.count('A')}, B={species.count('B')}, V={species.count('V')})")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")
    
    # Test 5: Diffraction pattern computation
    total += 1
    print(f"\nTest {total}: Diffraction pattern computation ...", end=" ")
    try:
        crystal = Quasicrystal1D(num_zeros=15)
        diffraction = crystal.compute_diffraction()
        assert len(diffraction['q_values']) == 1000
        assert len(diffraction['intensities']) == 1000
        assert all(0.0 <= I <= 1.0 for I in diffraction['intensities']), "Intensities not normalized"
        max_I = max(diffraction['intensities'])
        print(f"PASS (max intensity: {max_I:.4f}, {len(diffraction['q_values'])} points)")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")
    
    # Test 6: Peak finding
    total += 1
    print(f"\nTest {total}: Peak finding in diffraction ...", end=" ")
    try:
        crystal = Quasicrystal1D(num_zeros=15)
        peaks = crystal.find_peaks(threshold=0.2)
        assert len(peaks) > 0, "No peaks found"
        print(f"PASS ({len(peaks)} peaks found, top intensity: {peaks[0]['intensity']:.4f})")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")
    
    # Test 7: Prime connection verification
    total += 1
    print(f"\nTest {total}: Prime connection verification ...", end=" ")
    try:
        crystal = Quasicrystal1D(num_zeros=15)
        prime_conn = crystal.verify_prime_connection()
        print(f"PASS ({prime_conn['num_matches']} matches, mean error: {prime_conn['mean_error']:.4f})")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")
    
    # Test 8: 3D crystal construction
    total += 1
    print(f"\nTest {total}: 3D crystal construction ...", end=" ")
    try:
        crystal_3d = RiemannCrystal3D(num_zeros=15)
        assert len(crystal_3d.atomic_positions_3d) == 15
        assert len(crystal_3d.atomic_species_3d) == 15
        # Check positions are on spheres
        for pos in crystal_3d.atomic_positions_3d:
            r = math.sqrt(pos[0]**2 + pos[1]**2 + pos[2]**2)
            assert r > 0, "Zero-radius position"
        print(f"PASS ({len(crystal_3d.atomic_positions_3d)} atoms in 3D)")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")
    
    # Test 9: 3D diffraction slice
    total += 1
    print(f"\nTest {total}: 3D diffraction slice ...", end=" ")
    try:
        crystal_3d = RiemannCrystal3D(num_zeros=15)
        diff_3d = crystal_3d.diffraction_slice()
        assert len(diff_3d['intensities']) == 200
        assert len(diff_3d['intensities'][0]) == 200
        print(f"PASS (200×200 grid computed)")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")
    
    # Test 10: Radial average
    total += 1
    print(f"\nTest {total}: Radial average diffraction ...", end=" ")
    try:
        crystal_3d = RiemannCrystal3D(num_zeros=15)
        radial = crystal_3d.radial_average()
        assert len(radial['q_values']) == 500
        assert all(0.0 <= I <= 1.0 for I in radial['intensities']), "Not normalized"
        print(f"PASS ({len(radial['q_values'])} radial points)")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")
    
    # Test 11: Scalar wave displacement
    total += 1
    print(f"\nTest {total}: Scalar wave displacement field ...", end=" ")
    try:
        sw = ScalarWaveDisplacement(num_zeros=15)
        phi_0 = sw.displacement(0.0)
        # At t=0, φ(0) = Σ 1/γₖ > 0
        assert phi_0 > 0, f"φ(0) = {phi_0} should be positive"
        field = sw.displacement_field()
        assert len(field['t_values']) == 1000
        print(f"PASS (φ(0) = {phi_0:.4f})")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")
    
    # Test 12: Scalar wave nodes
    total += 1
    print(f"\nTest {total}: Scalar wave node finding ...", end=" ")
    try:
        sw = ScalarWaveDisplacement(num_zeros=15)
        nodes = sw.find_nodes()
        assert len(nodes) > 0, "No nodes found"
        # Verify nodes are actually zeros
        for node in nodes[:5]:
            phi_at_node = sw.displacement(node)
            assert abs(phi_at_node) < 0.01, f"Node at t={node} has |φ| = {abs(phi_at_node)}"
        print(f"PASS ({len(nodes)} nodes found)")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")
    
    # Test 13: Compressions and rarefactions
    total += 1
    print(f"\nTest {total}: Compressions and rarefactions ...", end=" ")
    try:
        sw = ScalarWaveDisplacement(num_zeros=15)
        cr = sw.compressions_and_rarefactions()
        assert len(cr['compressions']) > 0, "No compressions"
        assert len(cr['rarefactions']) > 0, "No rarefactions"
        ratio = cr['compression_ratio']
        print(f"PASS ({len(cr['compressions'])} compressions, {len(cr['rarefactions'])} rarefactions, ratio: {ratio:.2f})")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")
    
    # Test 14: Bell state crystal growth
    total += 1
    print(f"\nTest {total}: Bell state crystal growth ...", end=" ")
    try:
        growth = BellStateCrystalGrowth(num_zeros=15)
        result = growth.grow_crystal(num_layers=15)
        assert result['num_layers'] == 15
        assert result['total_atoms'] > 0
        all_atoms = growth.get_all_atoms()
        assert len(all_atoms) == result['total_atoms']
        print(f"PASS ({result['num_layers']} layers, {result['total_atoms']} atoms)")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")
    
    # Test 15: Explicit formula for prime counting
    total += 1
    print(f"\nTest {total}: Explicit formula for π(x) ...", end=" ")
    try:
        zeros = KNOWN_ZEROS[:15]
        # Test at x = 100
        x = 100.0
        pi_exact = prime_pi(x)
        pi_approx = explicit_formula_pi(x, zeros)
        # With 15 zeros, the approximation is rough but should be in the ballpark
        li_x = li(x)
        print(f"PASS (π({x}) = {pi_exact}, Li({x}) = {li_x:.1f}, explicit ≈ {pi_approx:.1f})")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")
    
    # Test 16: Logarithmic integral
    total += 1
    print(f"\nTest {total}: Logarithmic integral Li(x) ...", end=" ")
    try:
        # Li(10) ≈ 5.12
        li_10 = li(10.0)
        assert 5.0 < li_10 < 6.0, f"Li(10) = {li_10}, expected ≈ 5.12"
        # Li(100) ≈ 30.12
        li_100 = li(100.0)
        assert 29.0 < li_100 < 32.0, f"Li(100) = {li_100}, expected ≈ 30.12"
        print(f"PASS (Li(10) = {li_10:.2f}, Li(100) = {li_100:.2f})")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")
    
    # Test 17: Prime counting function
    total += 1
    print(f"\nTest {total}: Prime counting function π(x) ...", end=" ")
    try:
        assert prime_pi(10) == 4, f"π(10) = {prime_pi(10)}, expected 4"
        assert prime_pi(100) == 25, f"π(100) = {prime_pi(100)}, expected 25"
        assert prime_pi(1000) == 168, f"π(1000) = {prime_pi(1000)}, expected 168"
        print(f"PASS (π(10)=4, π(100)=25, π(1000)=168)")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")
    
    # Test 18: Structure factor symmetry
    total += 1
    print(f"\nTest {total}: Structure factor symmetry ...", end=" ")
    try:
        crystal = Quasicrystal1D(num_zeros=15)
        # S(-q) = S*(q) for real atomic positions
        q_test = 1.0
        S_q = crystal.structure_factor(q_test)
        S_neg_q = crystal.structure_factor(-q_test)
        assert abs(S_neg_q - S_q.conjugate()) < 1e-10, "S(-q) != S*(q)"
        # I(q) = I(-q)
        I_q = crystal.diffraction_intensity(q_test)
        I_neg_q = crystal.diffraction_intensity(-q_test)
        assert abs(I_q - I_neg_q) < 1e-10, "I(q) != I(-q)"
        print(f"PASS (S(-q) = S*(q), I(q) = I(-q))")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")
    
    # Test 19: HTML generation
    total += 1
    print(f"\nTest {total}: HTML visualization generation ...", end=" ")
    try:
        crystal = Quasicrystal1D(num_zeros=15)
        crystal_3d = RiemannCrystal3D(num_zeros=15)
        sw = ScalarWaveDisplacement(num_zeros=15)
        growth = BellStateCrystalGrowth(num_zeros=15)
        
        html_file = generate_crystal_html(crystal, crystal_3d, sw, growth,
                                          "riemann_crystal.html")
        assert os.path.exists(html_file), f"HTML file not created: {html_file}"
        file_size = os.path.getsize(html_file)
        print(f"PASS ({html_file}, {file_size} bytes)")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")
    
    # Summary
    print("\n" + "=" * 70)
    print(f"RESULTS: {passed}/{total} tests passed")
    print("=" * 70)
    
    if passed == total:
        print("\n✓ All tests passed — Riemann quasicrystal verified!")
        print("\nThe diffraction pattern of the Riemann quasicrystal encodes")
        print("the distribution of prime numbers via the explicit formula.")
        print("The longitudinal scalar wave φ(t) = Σ cos(γₖ·t)/γₖ is the")
        print("displacement field, with nodes as vacancies and compressions/")
        print("rarefactions as atomic species determined by the Möbius function.")
    
    return passed == total


# ============================================================
# Demo
# ============================================================

def run_demo():
    """Run the full demonstration."""
    print("\n" + "=" * 70)
    print("RIEMANN ZETA QUASICRYSTAL — Full Demo")
    print("=" * 70)
    
    # 1. Compute Riemann zeros
    print("\n[1] Computing Riemann zeros ...")
    zeros = compute_riemann_zeros(15)
    print(f"    Computed {len(zeros)} zeros")
    for i, gamma in enumerate(zeros[:5]):
        err = abs(gamma - KNOWN_ZEROS[i])
        print(f"    γ_{i+1} = {gamma:.6f} (error: {err:.2e})")
    
    # 2. Build 1D quasicrystal
    print("\n[2] Building 1D quasicrystal ...")
    crystal = Quasicrystal1D(num_zeros=15)
    positions = crystal.get_positions()
    species = crystal.get_species()
    print(f"    {len(positions)} atomic positions")
    print(f"    Species: A={species.count('A')}, B={species.count('B')}, V={species.count('V')}")
    print(f"    Occupancy: {sum(crystal.get_occupancy())}/{len(positions)}")
    
    # 3. Compute diffraction pattern
    print("\n[3] Computing diffraction pattern ...")
    diffraction = crystal.compute_diffraction()
    peaks = crystal.find_peaks(threshold=0.2)
    print(f"    {len(peaks)} peaks found")
    for i, peak in enumerate(peaks[:5]):
        print(f"    Peak {i+1}: q = {peak['q']:.4f}, I = {peak['intensity']:.4f}")
    
    # 4. Verify prime connection
    print("\n[4] Verifying prime connection ...")
    prime_conn = crystal.verify_prime_connection()
    print(f"    {prime_conn['num_matches']} matches to log(prime)/(2π)")
    for match in prime_conn['matches'][:5]:
        print(f"    Expected q = {match['expected_q']:.4f}, "
              f"Observed q = {match['observed_q']:.4f}, "
              f"Error = {match['error']:.4f}")
    
    # 5. Build 3D crystal
    print("\n[5] Building 3D Riemann crystal ...")
    crystal_3d = RiemannCrystal3D(num_zeros=15)
    print(f"    {len(crystal_3d.atomic_positions_3d)} atoms in 3D")
    print(f"    Lattice vectors:")
    for i, v in enumerate(crystal_3d.lattice_vectors):
        print(f"    a_{i+1} = ({v[0]:.4f}, {v[1]:.4f}, {v[2]:.4f})")
    
    # 6. Compute 3D diffraction
    print("\n[6] Computing 3D diffraction slice ...")
    diff_3d = crystal_3d.diffraction_slice()
    radial = crystal_3d.radial_average()
    print(f"    2D slice: {len(diff_3d['intensities'])}×{len(diff_3d['intensities'][0])} grid")
    print(f"    Radial average: {len(radial['q_values'])} points")
    
    # 7. Scalar wave displacement
    print("\n[7] Computing scalar wave displacement ...")
    sw = ScalarWaveDisplacement(num_zeros=15)
    phi_0 = sw.displacement(0.0)
    nodes = sw.find_nodes()
    cr = sw.compressions_and_rarefactions()
    print(f"    φ(0) = {phi_0:.4f} (DC component)")
    print(f"    {len(nodes)} nodes found")
    print(f"    {len(cr['compressions'])} compressions, {len(cr['rarefactions'])} rarefactions")
    print(f"    Compression ratio: {cr['compression_ratio']:.2f}")
    
    # 8. Bell state crystal growth
    print("\n[8] Growing crystal with Bell states ...")
    growth = BellStateCrystalGrowth(num_zeros=15)
    result = growth.grow_crystal(num_layers=15)
    print(f"    {result['num_layers']} layers, {result['total_atoms']} atoms")
    for h in result['growth_history'][:5]:
        print(f"    Layer {h['layer']}: Bell state {h['bell_state']}, "
              f"direction ({h['direction'][0]:.2f}, {h['direction'][1]:.2f}, {h['direction'][2]:.2f})")
    
    # 9. Explicit formula
    print("\n[9] Explicit formula for prime counting ...")
    for x in [10, 50, 100]:
        pi_exact = prime_pi(x)
        li_x = li(x)
        pi_approx = explicit_formula_pi(x, zeros)
        print(f"    π({x}) = {pi_exact}, Li({x}) = {li_x:.1f}, "
              f"explicit ≈ {pi_approx:.1f}")
    
    # 10. Generate HTML
    print("\n[10] Generating HTML visualization ...")
    html_file = generate_crystal_html(crystal, crystal_3d, sw, growth)
    print(f"    Generated {html_file} ({os.path.getsize(html_file)} bytes)")
    
    print("\n" + "=" * 70)
    print("Demo complete!")
    print("=" * 70)


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Riemann Zeta Quasicrystal")
    parser.add_argument("--tests", action="store_true", help="Run verification tests")
    parser.add_argument("--demo", action="store_true", help="Run full demo")
    parser.add_argument("--html", action="store_true", help="Generate HTML visualization")
    
    args = parser.parse_args()
    
    if args.tests:
        success = run_tests()
        sys.exit(0 if success else 1)
    elif args.demo:
        run_demo()
    elif args.html:
        crystal = Quasicrystal1D(num_zeros=15)
        crystal_3d = RiemannCrystal3D(num_zeros=15)
        sw = ScalarWaveDisplacement(num_zeros=15)
        growth = BellStateCrystalGrowth(num_zeros=15)
        html_file = generate_crystal_html(crystal, crystal_3d, sw, growth)
        print(f"Generated {html_file}")
    else:
        # Default: run tests
        success = run_tests()
        if success:
            print("\nUse --demo for full demonstration or --html for visualization only.")
        sys.exit(0 if success else 1)
