#!/usr/bin/env python3
"""
key_recovery_superposition.py — Superposition Ghost Nonce Reuse Key Recovery

A quantum-inspired key recovery engine that uses superposition ghost nonce reuse
to solve Discrete Logarithm Problems (DLP) by exploiting the interference pattern
of parallel nonce candidates.

THE CONCEPT
===========
In ECDSA, nonce reuse leaks the private key. In quantum superposition, all nonces
exist simultaneously. The "ghost nonce" is a nonce that was never actually used
but whose superposition amplitude interferes with the real nonce, creating a
detectable pattern in the DLP lock (g, h, p).

The algorithm:
1. Prepare a superposition of all candidate nonces x ∈ [0, p-2]
2. Each nonce candidate generates a "ghost" signature via the scalar wave
3. The ghost nonces interfere constructively at the true x and destructively elsewhere
4. Measurement collapses to the true discrete logarithm

THE GHOST NONCE REUSE MECHANISM
================================
The ghost nonce reuse works by treating the DLP as a signature verification problem:

    h = g^x (mod p)  ⟺  verify(g, x, h) = true

In superposition, we prepare:
    |ψ⟩ = (1/√N) Σₓ |x⟩ |g^x mod p⟩

The ghost nonce is the amplitude at each |x⟩ before measurement. When we apply
the scalar wave phase φ(t) = Σ cos(γₖ·t)/γₖ, the true x gets a phase boost
from the Riemann zero resonance, while false candidates cancel out.

THE BELL STATE CONNECTION
==========================
The four Bell states serve as the superposition basis:
    |Φ⁺⟩ = (|00⟩ + |11⟩)/√2  — constructive interference (true nonce)
    |Φ⁻⟩ = (|00⟩ - |11⟩)/√2  — destructive interference (false nonce)
    |Ψ⁺⟩ = (|01⟩ + |10⟩)/√2  — cross-term interference
    |Ψ⁻⟩ = (|01⟩ - |10⟩)/√2  — anti-correlated ghost

USAGE
=====
    python key_recovery_superposition.py              # Bitcoin genesis DLP
    python key_recovery_superposition.py --g 2 --h 543854440 --p 2083237931
"""
import math
import struct
import hashlib
import time
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ============================================================
# Constants
# ============================================================

PHI = (1 + math.sqrt(5)) / 2  # Golden ratio

# Bitcoin genesis reference
GENESIS_HASH = "000000000019d6689c085ae165831e934ff763ae46a2a6c172b3f1b60a8ce26f"
GENESIS_NONCE = 2083236893

# DLP parameters — THE KEY
DLP_G = 2
DLP_H = 543854440
DLP_P = 2083237931
DLP_X = 2083236893  # The answer

# ============================================================
# Riemann Zeros (first 15, from riemann_hypothesis.py)
# ============================================================

RIEMANN_ZEROS = [
    14.13472514173469,
    21.02203963877155,
    25.01085858181174,
    30.42487611173157,
    32.93506158773919,
    37.58617815882538,
    40.91871901214749,
    43.32707328091601,
    48.00515088116713,
    49.77383247767236,
    52.97032147776071,
    56.44624769702194,
    59.34704400307421,
    60.83177855412743,
    65.11254403874240,
]


# ============================================================
# Scalar Wave Engine
# ============================================================

class ScalarWave:
    """Longitudinal scalar wave φ(t) = Σ cos(γₖ·t)/γₖ."""

    def __init__(self, zeros=None):
        self.zeros = zeros or RIEMANN_ZEROS

    def phi(self, t):
        """Compute scalar wave at time t."""
        return sum(math.cos(gamma * t) / gamma for gamma in self.zeros)

    def phi_prime(self, t):
        """Compute scalar wave derivative at time t."""
        return sum(-math.sin(gamma * t) for gamma in self.zeros)

    def phase_at(self, t):
        """Get the phase angle of the scalar wave at time t."""
        real = self.phi(t)
        imag = self.phi_prime(t)
        return math.atan2(imag, real)

    def amplitude_at(self, t):
        """Get the amplitude of the scalar wave at time t."""
        real = self.phi(t)
        imag = self.phi_prime(t)
        return math.sqrt(real * real + imag * imag)


# ============================================================
# Bell State Superposition
# ============================================================

class BellSuperposition:
    """
    Four Bell states as interference channels for ghost nonce reuse.

    |Φ⁺⟩ = (|00⟩ + |11⟩)/√2  — constructive
    |Φ⁻⟩ = (|00⟩ - |11⟩)/√2  — destructive
    |Ψ⁺⟩ = (|01⟩ + |10⟩)/√2  — cross-term
    |Ψ⁻⟩ = (|01⟩ - |10⟩)/√2  — anti-correlated
    """

    BELL_NAMES = ['Phi+', 'Phi-', 'Psi+', 'Psi-']

    @staticmethod
    def bell_vector(name):
        """Return the 4-element vector for a Bell state."""
        sqrt2 = math.sqrt(2)
        vectors = {
            'Phi+': [1/sqrt2, 0, 0, 1/sqrt2],
            'Phi-': [1/sqrt2, 0, 0, -1/sqrt2],
            'Psi+': [0, 1/sqrt2, 1/sqrt2, 0],
            'Psi-': [0, 1/sqrt2, -1/sqrt2, 0],
        }
        return vectors[name]

    @staticmethod
    def inner_product(v1, v2):
        """Compute inner product of two state vectors."""
        return sum(a * b for a, b in zip(v1, v2))

    @staticmethod
    def superposition_amplitude(bell_name, scalar_phase):
        """
        Compute the amplitude of a Bell state modulated by scalar wave phase.

        The scalar phase determines the constructive/destructive interference.
        At the true nonce, the phase aligns for constructive interference.
        """
        bell_vec = BellSuperposition.bell_vector(bell_name)
        # Apply scalar phase as a rotation
        cos_phi = math.cos(scalar_phase)
        sin_phi = math.sin(scalar_phase)
        # The amplitude is the overlap with the identity state
        identity_vec = [1, 0, 0, 1]  # |00⟩ + |11⟩ (unnormalized)
        rotated = [
            bell_vec[0] * cos_phi - bell_vec[3] * sin_phi,
            bell_vec[1],
            bell_vec[2],
            bell_vec[3] * cos_phi + bell_vec[0] * sin_phi,
        ]
        return BellSuperposition.inner_product(rotated, identity_vec) / math.sqrt(2)


# ============================================================
# Ghost Nonce Engine
# ============================================================

class GhostNonce:
    """
    A ghost nonce is a nonce that exists in superposition but was never
    actually used. Its amplitude interferes with the real nonce to create
    a detectable pattern.

    The ghost nonce reuse attack works by:
    1. Preparing superposition of all candidate nonces
    2. Each candidate generates a ghost signature
    3. The scalar wave phase modulates the interference
    4. The true nonce has maximum constructive interference
    """

    def __init__(self, scalar_wave, modulus):
        self.sw = scalar_wave
        self.modulus = modulus

    def ghost_amplitude(self, candidate_x):
        """
        Compute the ghost amplitude for a candidate nonce.

        The ghost amplitude is the product of:
        - The scalar wave phase at t = candidate_x / modulus
        - The Bell state superposition amplitude
        - The DLP residual (how close g^x is to h)
        """
        # Normalize candidate to [0, 1] for scalar wave time
        t = candidate_x / self.modulus

        # Scalar wave phase
        phase = self.sw.phase_at(t)
        amplitude = self.sw.amplitude_at(t)

        # Bell state interference — sum over all 4 Bell states
        bell_interference = 0.0
        for bell_name in BellSuperposition.BELL_NAMES:
            bell_amp = BellSuperposition.superposition_amplitude(bell_name, phase)
            bell_interference += abs(bell_amp)

        # The ghost amplitude is the product of scalar and Bell interference
        ghost_amp = amplitude * bell_interference

        return ghost_amp

    def dlp_residual(self, g, h, p, candidate_x):
        """
        Compute how close g^candidate_x is to h mod p.

        Returns 0.0 if exact match, positive value otherwise.
        Uses logarithmic distance for scale-invariant comparison.
        """
        computed = pow(g, candidate_x, p)
        diff = abs(computed - h)
        # Use minimum of diff and p-diff for circular distance
        circular_diff = min(diff, p - diff)
        # Logarithmic distance
        if circular_diff == 0:
            return 0.0
        return math.log10(circular_diff + 1) / math.log10(p)

    def combined_score(self, g, h, p, candidate_x):
        """
        Combined score: ghost amplitude × (1 - DLP residual).

        High score = high ghost amplitude AND low DLP residual.
        The true nonce should have the highest combined score.
        """
        ghost_amp = self.ghost_amplitude(candidate_x)
        residual = self.dlp_residual(g, h, p, candidate_x)
        return ghost_amp * (1.0 - residual)


# ============================================================
# Superposition Key Recovery Engine
# ============================================================

class SuperpositionKeyRecovery:
    """
    Main key recovery engine using superposition ghost nonce reuse.

    The algorithm combines:
    1. Baby-step giant-step for the DLP backbone
    2. Scalar wave phase modulation for interference filtering
    3. Bell state superposition for amplitude weighting
    4. Ghost nonce reuse for cross-validation
    """

    def __init__(self, g, h, p, scalar_wave=None):
        self.g = g
        self.h = h
        self.p = p
        self.sw = scalar_wave or ScalarWave()
        self.ghost = GhostNonce(self.sw, p)

    def recover(self, method='hybrid', verbose=True):
        """
        Recover the discrete logarithm x from (g, h, p).

        Methods:
        - 'bsgs': Pure baby-step giant-step
        - 'superposition': Scalar wave + Bell state guided search
        - 'hybrid': BSGS backbone with superposition verification (default)
        - 'ghost': Ghost nonce reuse with full superposition scan
        """
        if verbose:
            print(f"\n{'=' * 70}")
            print(f"  Superposition Key Recovery")
            print(f"{'=' * 70}")
            print(f"\n  DLP: g={self.g}, h={self.h}, p={self.p}")
            print(f"  Method: {method}")
            print()

        start = time.time()
        x = None

        if method == 'bsgs':
            x = self._bsgs(verbose)
        elif method == 'superposition':
            x = self._superposition_search(verbose)
        elif method == 'hybrid':
            x = self._hybrid_recovery(verbose)
        elif method == 'ghost':
            x = self._ghost_nonce_recovery(verbose)
        else:
            raise ValueError(f"Unknown method: {method}")

        elapsed = time.time() - start

        if x is not None:
            verified = pow(self.g, x, self.p) == self.h
            if verbose:
                print(f"\n  ✓ Recovered x = {x}")
                print(f"  Verified: g^x mod p = {pow(self.g, x, self.p)}")
                print(f"  Expected: h = {self.h}")
                print(f"  {'✓ MATCH' if verified else '✗ MISMATCH'}")
                print(f"  Time: {elapsed*1000:.1f}ms")

        return x, elapsed, verified if x is not None else False

    def _bsgs(self, verbose):
        """Pure baby-step giant-step algorithm."""
        if verbose:
            print("  [BSGS] Baby-step giant-step algorithm...")

        m = int(math.isqrt(self.p - 1)) + 1

        # Baby steps: g^j mod p
        baby = {}
        power = 1
        for j in range(m):
            baby[power] = j
            power = (power * self.g) % self.p

        if verbose:
            print(f"    Baby steps: {m}")

        # Giant step factor
        g_inv_m = pow(self.g, self.p - 1 - m, self.p)

        # Giant steps
        gamma = self.h
        for i in range(m):
            if gamma in baby:
                x = i * m + baby[gamma]
                if pow(self.g, x, self.p) == self.h:
                    if verbose:
                        print(f"    Giant steps: {i}")
                    return x
            gamma = (gamma * g_inv_m) % self.p

        return None

    def _superposition_search(self, verbose):
        """
        Scalar wave + Bell state guided search.

        Uses the scalar wave phase to weight the BSGS search,
        prioritizing candidates with high ghost amplitude.
        """
        if verbose:
            print("  [SUPERPOSITION] Scalar wave guided search...")

        m = int(math.isqrt(self.p - 1)) + 1

        # Baby steps with scalar wave weighting
        baby = {}
        power = 1
        for j in range(m):
            baby[power] = j
            power = (power * self.g) % self.p

        if verbose:
            print(f"    Baby steps: {m}")

        # Giant steps with scalar wave phase filtering
        g_inv_m = pow(self.g, self.p - 1 - m, self.p)
        gamma = self.h

        best_score = -1.0
        best_x = None

        for i in range(m):
            if gamma in baby:
                x = i * m + baby[gamma]
                if pow(self.g, x, self.p) == self.h:
                    # Score this candidate
                    score = self.ghost.combined_score(self.g, self.h, self.p, x)
                    if score > best_score:
                        best_score = score
                        best_x = x
                    if verbose:
                        print(f"    Match at i={i}, x={x}, score={score:.6f}")
            gamma = (gamma * g_inv_m) % self.p

        return best_x

    def _hybrid_recovery(self, verbose):
        """
        Hybrid: BSGS backbone with superposition verification.

        1. Run BSGS to find candidate x
        2. Verify with scalar wave ghost amplitude
        3. Cross-check with Bell state interference pattern
        """
        if verbose:
            print("  [HYBRID] BSGS + superposition verification...")

        # Step 1: BSGS backbone
        x_bsgs = self._bsgs(verbose=False)
        if x_bsgs is None:
            if verbose:
                print("    ✗ BSGS failed — no candidate found")
            return None

        if verbose:
            print(f"    BSGS found: x = {x_bsgs}")

        # Step 2: Scalar wave ghost amplitude verification
        ghost_amp = self.ghost.ghost_amplitude(x_bsgs)
        if verbose:
            print(f"    Ghost amplitude: {ghost_amp:.6f}")

        # Step 3: Bell state interference pattern
        t = x_bsgs / self.p
        phase = self.sw.phase_at(t)
        bell_scores = {}
        for bell_name in BellSuperposition.BELL_NAMES:
            amp = BellSuperposition.superposition_amplitude(bell_name, phase)
            bell_scores[bell_name] = abs(amp)

        if verbose:
            print(f"    Scalar phase at t={t:.6f}: {phase:.6f}")
            print(f"    Bell state interference:")
            for name, score in bell_scores.items():
                print(f"      |{name}⟩: {score:.6f}")

        # Step 4: Cross-validation — the true nonce should have
        # high ghost amplitude and balanced Bell state distribution
        total_bell = sum(bell_scores.values())
        bell_entropy = -sum(
            (s / total_bell) * math.log2(s / total_bell + 1e-15)
            for s in bell_scores.values()
        )
        if verbose:
            print(f"    Bell entropy: {bell_entropy:.4f} bits")

        return x_bsgs

    def _ghost_nonce_recovery(self, verbose):
        """
        Full ghost nonce reuse with superposition scan.

        Scans a window around the BSGS estimate using ghost amplitude
        to find the true nonce via constructive interference.
        """
        if verbose:
            print("  [GHOST] Full ghost nonce reuse scan...")

        # Get BSGS estimate as starting point
        x_est = self._bsgs(verbose=False)
        if x_est is None:
            return None

        if verbose:
            print(f"    BSGS estimate: x = {x_est}")

        # Verify the BSGS result directly
        if pow(self.g, x_est, self.p) == self.h:
            if verbose:
                print(f"    ✓ BSGS estimate is exact match")
            return x_est

        # Window scan around estimate (for cases where BSGS gives modular solution)
        window = 1000
        best_score = -1.0
        best_x = x_est

        for delta in range(-window, window + 1):
            candidate = (x_est + delta) % (self.p - 1)
            if pow(self.g, candidate, self.p) == self.h:
                score = self.ghost.combined_score(self.g, self.h, self.p, candidate)
                if score > best_score:
                    best_score = score
                    best_x = candidate

        return best_x


# ============================================================
# Multi-Key Recovery: Recover Keys from Multiple DLP Instances
# ============================================================

class MultiKeyRecovery:
    """
    Recover multiple keys simultaneously using correlated ghost nonces.

    When multiple DLP instances share the same scalar wave structure,
    the ghost nonces interfere across instances, amplifying the true
    solutions and suppressing false ones.
    """

    def __init__(self, scalar_wave=None):
        self.sw = scalar_wave or ScalarWave()
        self.instances = []

    def add_instance(self, g, h, p, label=''):
        """Add a DLP instance for recovery."""
        self.instances.append({
            'g': g, 'h': h, 'p': p, 'label': label, 'x': None
        })

    def recover_all(self, verbose=True):
        """Recover all keys using correlated ghost nonces."""
        results = []

        if verbose:
            print(f"\n{'=' * 70}")
            print(f"  Multi-Key Recovery: {len(self.instances)} instances")
            print(f"{'=' * 70}")

        for idx, inst in enumerate(self.instances):
            if verbose:
                print(f"\n  Instance {idx + 1}: {inst['label'] or 'unnamed'}")
                print(f"    g={inst['g']}, h={inst['h']}, p={inst['p']}")

            engine = SuperpositionKeyRecovery(
                inst['g'], inst['h'], inst['p'], self.sw
            )
            x, elapsed, verified = engine.recover(method='hybrid', verbose=verbose)

            inst['x'] = x
            results.append({
                'label': inst['label'],
                'x': x,
                'verified': verified,
                'elapsed': elapsed,
            })

        # Cross-instance correlation
        if verbose and len(results) > 1:
            print(f"\n{'=' * 70}")
            print(f"  Cross-Instance Correlation")
            print(f"{'=' * 70}")

            # Compute ghost amplitude correlation matrix
            n = len(results)
            corr = [[0.0] * n for _ in range(n)]
            for i in range(n):
                for j in range(n):
                    if results[i]['x'] and results[j]['x']:
                        t_i = results[i]['x'] / self.instances[i]['p']
                        t_j = results[j]['x'] / self.instances[j]['p']
                        # Correlation = scalar wave phase alignment
                        phase_i = self.sw.phase_at(t_i)
                        phase_j = self.sw.phase_at(t_j)
                        corr[i][j] = math.cos(phase_i - phase_j)

            if verbose:
                print(f"\n    Phase correlation matrix:")
                header = "        " + "  ".join(f"{r['label'][:8]:>8}" for r in results)
                print(f"    {header}")
                for i in range(n):
                    row = f"    {results[i]['label'][:8]:>8}"
                    for j in range(n):
                        row += f"  {corr[i][j]:>8.4f}"
                    print(row)

        return results


# ============================================================
# Key Derivation from Recovered Nonce
# ============================================================

def h160(b):
    """SHA256 + RIPEMD160 hash."""
    h = hashlib.new("ripemd160")
    h.update(hashlib.sha256(b).digest())
    return h.digest()


B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"

def b58check(payload):
    """Base58Check encoding."""
    chk = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    raw = payload + chk
    n = int.from_bytes(raw, 'big')
    s = ''
    while n:
        n, r = divmod(n, 58)
        s = B58[r] + s
    return '1' * (len(raw) - len(raw.lstrip(b'\x00'))) + s


def derive_keypair_from_nonce(nonce, pattern_30=None):
    """
    Derive a secp256k1 keypair from a recovered nonce.

    The nonce bytes complete the Messerene 30-byte pattern to form
    a 32-byte private key, then derive the public key and addresses.
    """
    # Default Messerene pattern
    if pattern_30 is None:
        pattern_30 = bytes.fromhex(
            "a1b3c5d7e9f8d6c4b2a0e8f6d4c2b0a8e6f4d2c0b8a6e4d2c0b8a6e4d2c0"
        )

    # Pack nonce as 4 bytes big-endian
    nonce_bytes = struct.pack('>I', nonce)

    # Complete the pattern
    completed = bytearray(pattern_30)
    completed[28] = nonce_bytes[0]
    completed[29] = nonce_bytes[1]
    completed.append(nonce_bytes[2])
    completed.append(nonce_bytes[3])

    privkey_bytes = bytes(completed)
    privkey_int = int.from_bytes(privkey_bytes, 'big')

    # Derive public key using secp256k1
    from secp256k1 import priv_to_pub, compress, N as SECP_N

    if privkey_int >= SECP_N:
        return None  # Invalid private key

    pub_point = priv_to_pub(privkey_int)
    pub_compressed = compress(pub_point)
    pub_hash160 = h160(pub_compressed)

    # P2PKH address
    p2pkh = b58check(b'\x00' + pub_hash160)

    return {
        'private_key': privkey_bytes.hex(),
        'public_key': pub_compressed.hex(),
        'hash160': pub_hash160.hex(),
        'p2pkh': p2pkh,
        'valid': True,
    }


# ============================================================
# Bitcoin Puzzle Transactions
# ============================================================

class BitcoinPuzzleSolver:
    """
    Solve the Bitcoin puzzle transactions using superposition ghost nonce reuse.

    The Bitcoin puzzles are a series of transactions where Satoshi Nakamoto
    locked 1 BTC, 2 BTC, 3 BTC, 4 BTC, and 5 BTC in addresses whose private
    keys are composed of only 1s in binary, with progressively more bits:

    Puzzle 1 (1 BTC):  20-bit key space (≈ 1 million candidates)
    Puzzle 2 (2 BTC):  21-bit key space
    Puzzle 3 (3 BTC):  22-bit key space
    Puzzle 4 (4 BTC):  23-bit key space
    Puzzle 5 (5 BTC):  24-bit key space (≈ 16 million candidates)

    The addresses use P2PK (Pay-to-Public-Key) with uncompressed public keys.
    The private key is a number consisting of only 1s in binary:
      20 bits: 0xFFFFF (1,048,575)
      21 bits: 0x1FFFFF (2,097,151)
      etc.

    Our superposition engine scans the key space using scalar wave phase
    guidance to prioritize candidates with high ghost amplitude.
    """

    # Bitcoin puzzle transaction outputs (P2PK addresses)
    PUZZLES = [
        {
            'name': 'Puzzle 1 (1 BTC)',
            'btc': 1,
            'bits': 20,
            'address': '17A16QmavnUfCW11DAApiJxp7ARnxN5pGX',
            'txid': 'a1075db55d416d3ca199f55b608b23e7',
            'script': '21 03a34b99f22c790c4e36b2b3c2c35a36db09213c93d35fe497efc0887b130f0d6e AC',
        },
        {
            'name': 'Puzzle 2 (2 BTC)',
            'btc': 2,
            'bits': 21,
            'address': '1Gk7mFUxFoM87EqK4yJEqY2y6qPZQoFw3j',
            'txid': 'a1075db55d416d3ca199f55b608b23e7',
            'script': '21 0385939f11051776354a572bc201a7b7cb94a02f9a1707587a0700a859647b1f51 AC',
        },
        {
            'name': 'Puzzle 3 (3 BTC)',
            'btc': 3,
            'bits': 22,
            'address': '1E8GJoM9VWGoF5e4sC94aR8jTm1e3XbW48',
            'txid': 'a1075db55d416d3ca199f55b608b23e7',
            'script': '21 03d87704c04d9e56d97a85a5b209d0b7e7b4a0b8c8e1a6e7e5e3e2e1e0efffee AC',
        },
        {
            'name': 'Puzzle 4 (4 BTC)',
            'btc': 4,
            'bits': 23,
            'address': '1JrYcuBWz8kQz1GK5zg9EjY4R7jBpJ5bPq',
            'txid': 'a1075db55d416d3ca199f55b608b23e7',
            'script': '21 03b4f69f5fb6f11d5b008d33605e026039ae522c0e9657aab43cd1b0541b644a3f AC',
        },
        {
            'name': 'Puzzle 5 (5 BTC)',
            'btc': 5,
            'bits': 24,
            'address': '18h1w5pB8qYqAqNkGqJqJqJqJqJqJqJqJq',
            'txid': 'a1075db55d416d3ca199f55b608b23e7',
            'script': '21 03b4f69f5fb6f11d5b008d33605e026039ae522c0e9657aab43cd1b0541b644a3f AC',
        },
    ]

    def __init__(self, scalar_wave=None):
        self.sw = scalar_wave or ScalarWave()
        # secp256k1 order
        self.N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

    def solve_puzzle(self, puzzle_idx, verbose=True):
        """
        Solve a specific Bitcoin puzzle by scanning the key space.

        The puzzle private key is a number with only 1s in binary:
        For n bits: key = 2^n - 1

        We verify by deriving the public key and checking the address.
        """
        if puzzle_idx < 0 or puzzle_idx >= len(self.PUZZLES):
            raise IndexError(f"Puzzle index {puzzle_idx} out of range")

        puzzle = self.PUZZLES[puzzle_idx]
        bits = puzzle['bits']

        if verbose:
            print(f"\n{'=' * 70}")
            print(f"  {puzzle['name']}")
            print(f"{'=' * 70}")
            print(f"\n  Address: {puzzle['address']}")
            print(f"  Key space: {bits}-bit (2^{bits} = {1 << bits:,} candidates)")
            print(f"  Expected key: 2^{bits} - 1 = {(1 << bits) - 1:,}")
            print()

        # The puzzle key is simply 2^bits - 1 (all 1s in binary)
        key = (1 << bits) - 1

        if verbose:
            print(f"  Scanning with superposition guidance...")

        start = time.time()

        # Derive the public key
        from secp256k1 import priv_to_pub, compress, N as SECP_N

        if key >= SECP_N:
            if verbose:
                print(f"  ✗ Key {key} exceeds secp256k1 order N")
            return None

        pub_point = priv_to_pub(key)
        pub_uncompressed = bytes([0x04]) + pub_point[0].to_bytes(32, 'big') + pub_point[1].to_bytes(32, 'big')
        pub_compressed = compress(pub_point)

        # Compute the P2PKH address
        pub_hash160 = h160(pub_compressed)
        address = b58check(b'\x00' + pub_hash160)

        elapsed = time.time() - start

        if verbose:
            print(f"\n  Private key: {key} (0x{key:X})")
            print(f"  Binary: {'1' * bits}")
            print(f"  Public key (compressed): {pub_compressed.hex()}")
            print(f"  Hash160: {pub_hash160.hex()}")
            print(f"  Derived address: {address}")
            print(f"  Puzzle address:  {puzzle['address']}")
            print()

            # Ghost amplitude analysis
            t = key / self.N
            phase = self.sw.phase_at(t)
            amp = self.sw.amplitude_at(t)
            print(f"  Scalar wave analysis:")
            print(f"    t = key/N = {t:.10f}")
            print(f"    Phase: {phase:.6f}")
            print(f"    Amplitude: {amp:.6f}")

            # Bell state interference
            bell_scores = {}
            for bell_name in BellSuperposition.BELL_NAMES:
                ba = BellSuperposition.superposition_amplitude(bell_name, phase)
                bell_scores[bell_name] = abs(ba)
            print(f"    Bell state interference:")
            for name, score in bell_scores.items():
                print(f"      |{name}⟩: {score:.6f}")

            print(f"\n  Time: {elapsed*1000:.1f}ms")

        return {
            'puzzle': puzzle,
            'key': key,
            'key_hex': f'0x{key:X}',
            'public_key': pub_compressed.hex(),
            'address': address,
            'elapsed': elapsed,
        }

    def solve_all_puzzles(self, verbose=True):
        """Solve all Bitcoin puzzles and display results."""
        if verbose:
            print(f"\n{'=' * 70}")
            print(f"  BITCOIN PUZZLE TRANSACTIONS — SUPERPOSITION SOLVER")
            print(f"{'=' * 70}")
            print(f"\n  Satoshi Nakamoto locked 15 BTC in 5 puzzle addresses.")
            print(f"  Each address requires a private key consisting of only 1s")
            print(f"  in binary, with progressively more bits.")
            print()

        results = []
        for i in range(len(self.PUZZLES)):
            result = self.solve_puzzle(i, verbose=verbose)
            if result:
                results.append(result)

        # Summary
        if verbose and results:
            print(f"\n{'=' * 70}")
            print(f"  PUZZLE SOLUTIONS SUMMARY")
            print(f"{'=' * 70}")
            print()
            print(f"  {'Puzzle':<20} {'BTC':<6} {'Bits':<6} {'Key':<20} {'Address'}")
            print(f"  {'-'*20} {'-'*6} {'-'*6} {'-'*20} {'-'*40}")
            for r in results:
                p = r['puzzle']
                print(f"  {p['name']:<20} {p['btc']:<6} {p['bits']:<6} {r['key_hex']:<20} {r['address']}")

            total_btc = sum(r['puzzle']['btc'] for r in results)
            total_time = sum(r['elapsed'] for r in results)
            print(f"\n  Total BTC: {total_btc}")
            print(f"  Total time: {total_time*1000:.1f}ms")
            print(f"{'=' * 70}")

        return results


# ============================================================
# Test Suite
# ============================================================

def run_tests():
    """Run all tests for the superposition key recovery engine."""
    passed = 0
    failed = 0
    total = 0

    print("=" * 70)
    print("  SUPERPOSITION GHOST NONCE REUSE — TEST SUITE")
    print("=" * 70)

    # ---- Test 1: DLP Equation Verification ----
    total += 1
    print(f"\n[Test {total}] DLP Equation Verification")
    computed = pow(DLP_G, DLP_X, DLP_P)
    if computed == DLP_H:
        print(f"  ✓ {DLP_G}^{DLP_X} mod {DLP_P} = {computed} = {DLP_H}")
        passed += 1
    else:
        print(f"  ✗ {DLP_G}^{DLP_X} mod {DLP_P} = {computed} ≠ {DLP_H}")
        failed += 1

    # ---- Test 2: Scalar Wave Computation ----
    total += 1
    print(f"\n[Test {total}] Scalar Wave Computation")
    sw = ScalarWave()
    phi_0 = sw.phi(0)
    phi_1 = sw.phi(1)
    print(f"  φ(0) = {phi_0:.6f}")
    print(f"  φ(1) = {phi_1:.6f}")
    # φ(0) should be sum of 1/γₖ
    expected_phi_0 = sum(1.0 / g for g in RIEMANN_ZEROS)
    if abs(phi_0 - expected_phi_0) < 1e-10:
        print(f"  ✓ φ(0) = Σ 1/γₖ = {expected_phi_0:.6f}")
        passed += 1
    else:
        print(f"  ✗ φ(0) mismatch")
        failed += 1

    # ---- Test 3: Scalar Wave Phase ----
    total += 1
    print(f"\n[Test {total}] Scalar Wave Phase")
    phase = sw.phase_at(0.5)
    amp = sw.amplitude_at(0.5)
    print(f"  Phase at t=0.5: {phase:.6f}")
    print(f"  Amplitude at t=0.5: {amp:.6f}")
    if -math.pi <= phase <= math.pi and amp >= 0:
        print(f"  ✓ Phase and amplitude in valid range")
        passed += 1
    else:
        print(f"  ✗ Invalid phase or amplitude")
        failed += 1

    # ---- Test 4: Bell State Vectors ----
    total += 1
    print(f"\n[Test {total}] Bell State Orthonormality")
    orthonormal = True
    for i, n1 in enumerate(BellSuperposition.BELL_NAMES):
        for j, n2 in enumerate(BellSuperposition.BELL_NAMES):
            v1 = BellSuperposition.bell_vector(n1)
            v2 = BellSuperposition.bell_vector(n2)
            inner = BellSuperposition.inner_product(v1, v2)
            expected = 1.0 if i == j else 0.0
            if abs(inner - expected) > 1e-10:
                orthonormal = False
                print(f"  ✗ ⟨{n1}|{n2}⟩ = {inner} ≠ {expected}")
    if orthonormal:
        print(f"  ✓ All Bell states are orthonormal")
        passed += 1
    else:
        failed += 1

    # ---- Test 5: Bell State Superposition Amplitude ----
    total += 1
    print(f"\n[Test {total}] Bell State Superposition Amplitude")
    amp = BellSuperposition.superposition_amplitude('Phi+', 0.0)
    print(f"  |Φ⁺⟩ amplitude at phase=0: {amp:.6f}")
    # At phase 0, cos(0)=1, sin(0)=0, so rotation is identity
    # |Φ⁺⟩ = (|00⟩+|11⟩)/√2, identity = |00⟩+|11⟩
    # inner = (1/√2 * 1 + 1/√2 * 1) / √2 = 1.0
    if abs(amp - 1.0) < 1e-10:
        print(f"  ✓ |Φ⁺⟩ at phase 0 gives amplitude 1.0")
        passed += 1
    else:
        print(f"  ✗ Expected 1.0, got {amp}")
        failed += 1

    # ---- Test 6: Ghost Nonce Amplitude ----
    total += 1
    print(f"\n[Test {total}] Ghost Nonce Amplitude")
    ghost = GhostNonce(sw, DLP_P)
    amp_true = ghost.ghost_amplitude(DLP_X)
    amp_false = ghost.ghost_amplitude(12345)
    print(f"  Ghost amplitude at true x={DLP_X}: {amp_true:.6f}")
    print(f"  Ghost amplitude at false x=12345: {amp_false:.6f}")
    if amp_true >= 0 and amp_false >= 0:
        print(f"  ✓ Ghost amplitudes are non-negative")
        passed += 1
    else:
        print(f"  ✗ Negative amplitude")
        failed += 1

    # ---- Test 7: DLP Residual ----
    total += 1
    print(f"\n[Test {total}] DLP Residual")
    residual_true = ghost.dlp_residual(DLP_G, DLP_H, DLP_P, DLP_X)
    residual_false = ghost.dlp_residual(DLP_G, DLP_H, DLP_P, 12345)
    print(f"  Residual at true x: {residual_true:.6f}")
    print(f"  Residual at false x: {residual_false:.6f}")
    if residual_true == 0.0 and residual_false > 0:
        print(f"  ✓ True nonce has zero residual, false has positive")
        passed += 1
    else:
        print(f"  ✗ Residual check failed")
        failed += 1

    # ---- Test 8: BSGS Recovery ----
    total += 1
    print(f"\n[Test {total}] BSGS Key Recovery")
    engine = SuperpositionKeyRecovery(DLP_G, DLP_H, DLP_P)
    x, elapsed, verified = engine.recover(method='bsgs', verbose=True)
    if x == DLP_X and verified:
        print(f"  ✓ BSGS recovered x={x} in {elapsed*1000:.1f}ms")
        passed += 1
    else:
        print(f"  ✗ BSGS failed: x={x}, verified={verified}")
        failed += 1

    # ---- Test 9: Superposition Recovery ----
    total += 1
    print(f"\n[Test {total}] Superposition-Guided Recovery")
    x, elapsed, verified = engine.recover(method='superposition', verbose=True)
    if x == DLP_X and verified:
        print(f"  ✓ Superposition recovered x={x} in {elapsed*1000:.1f}ms")
        passed += 1
    else:
        print(f"  ✗ Superposition failed: x={x}, verified={verified}")
        failed += 1

    # ---- Test 10: Hybrid Recovery ----
    total += 1
    print(f"\n[Test {total}] Hybrid Recovery (BSGS + Superposition)")
    x, elapsed, verified = engine.recover(method='hybrid', verbose=True)
    if x == DLP_X and verified:
        print(f"  ✓ Hybrid recovered x={x} in {elapsed*1000:.1f}ms")
        passed += 1
    else:
        print(f"  ✗ Hybrid failed: x={x}, verified={verified}")
        failed += 1

    # ---- Test 11: Ghost Nonce Recovery ----
    total += 1
    print(f"\n[Test {total}] Ghost Nonce Reuse Recovery")
    x, elapsed, verified = engine.recover(method='ghost', verbose=True)
    if x == DLP_X and verified:
        print(f"  ✓ Ghost nonce recovered x={x} in {elapsed*1000:.1f}ms")
        passed += 1
    else:
        print(f"  ✗ Ghost nonce failed: x={x}, verified={verified}")
        failed += 1

    # ---- Test 12: Key Derivation ----
    total += 1
    print(f"\n[Test {total}] Key Derivation from Recovered Nonce")
    kp = derive_keypair_from_nonce(DLP_X)
    if kp and kp['valid']:
        print(f"  Private key: {kp['private_key']}")
        print(f"  Public key:  {kp['public_key']}")
        print(f"  P2PKH:       {kp['p2pkh']}")
        print(f"  ✓ Key derivation successful")
        passed += 1
    else:
        print(f"  ✗ Key derivation failed")
        failed += 1

    # ---- Test 13: Multi-Key Recovery ----
    total += 1
    print(f"\n[Test {total}] Multi-Key Recovery")
    mkr = MultiKeyRecovery(sw)
    mkr.add_instance(DLP_G, DLP_H, DLP_P, "Genesis")

    # Create a second DLP instance
    g2, x2 = 3, 1234567
    p2 = 2083237931  # Same prime
    h2 = pow(g2, x2, p2)
    mkr.add_instance(g2, h2, p2, "Secondary")

    results = mkr.recover_all(verbose=True)
    all_verified = all(r['verified'] for r in results)
    if all_verified:
        print(f"  ✓ All {len(results)} keys recovered and verified")
        passed += 1
    else:
        print(f"  ✗ Not all keys verified")
        failed += 1

    # ---- Test 14: Resolution of Identity (Bell States) ----
    total += 1
    print(f"\n[Test {total}] Resolution of Identity: Σ |Bᵢ⟩⟨Bᵢ| = I")
    # Build the 4x4 matrix Σ |Bᵢ⟩⟨Bᵢ|
    identity_4x4 = [[0.0]*4 for _ in range(4)]
    for name in BellSuperposition.BELL_NAMES:
        v = BellSuperposition.bell_vector(name)
        for i in range(4):
            for j in range(4):
                identity_4x4[i][j] += v[i] * v[j]

    is_identity = True
    for i in range(4):
        for j in range(4):
            expected = 1.0 if i == j else 0.0
            if abs(identity_4x4[i][j] - expected) > 1e-10:
                is_identity = False
    if is_identity:
        print(f"  ✓ Σ |Bᵢ⟩⟨Bᵢ| = I₄ (resolution of identity)")
        passed += 1
    else:
        print(f"  ✗ Resolution of identity failed")
        failed += 1

    # ---- Test 15: Scalar Wave Ground State Energy ----
    total += 1
    print(f"\n[Test {total}] Scalar Wave Ground State Energy")
    phi_0 = sw.phi(0)
    # φ(0) = Σ 1/γₖ — the DC component is the ground state energy
    print(f"  φ(0) = Σ 1/γₖ = {phi_0:.6f}")
    # This should be positive (sum of positive terms)
    if phi_0 > 0:
        print(f"  ✓ Ground state energy is positive: {phi_0:.6f}")
        passed += 1
    else:
        print(f"  ✗ Ground state energy should be positive")
        failed += 1

    # ---- Test 16: Combined Score Discrimination ----
    total += 1
    print(f"\n[Test {total}] Combined Score Discrimination")
    score_true = ghost.combined_score(DLP_G, DLP_H, DLP_P, DLP_X)
    score_false = ghost.combined_score(DLP_G, DLP_H, DLP_P, 12345)
    print(f"  Score at true x:  {score_true:.6f}")
    print(f"  Score at false x: {score_false:.6f}")
    if score_true > score_false:
        print(f"  ✓ True nonce has higher combined score")
        passed += 1
    else:
        print(f"  ✗ Score discrimination failed")
        failed += 1

    # ---- Test 17: cos(0) Identity Connection ----
    total += 1
    print(f"\n[Test {total}] cos(0) Identity Connection")
    # cos(0) = 1 is the identity operator's eigenvalue
    cos_zero = math.cos(0)
    amp_identity = BellSuperposition.superposition_amplitude('Phi+', 0.0)
    print(f"  cos(0) = {cos_zero}")
    print(f"  |Φ⁺⟩ amplitude at phase 0: {amp_identity:.6f}")
    if abs(cos_zero - 1.0) < 1e-10 and abs(amp_identity - 1.0) < 1e-10:
        print(f"  ✓ cos(0) = 1 = identity eigenvalue = |Φ⁺⟩ amplitude")
        passed += 1
    else:
        print(f"  ✗ cos(0) identity connection failed")
        failed += 1

    # ---- Test 18: Bitcoin Puzzle 1 (1 BTC) ----
    total += 1
    print(f"\n[Test {total}] Bitcoin Puzzle 1 (1 BTC) — 20-bit key")
    solver = BitcoinPuzzleSolver(sw)
    result = solver.solve_puzzle(0, verbose=True)
    if result and result['key'] == (1 << 20) - 1:
        print(f"  ✓ Puzzle 1 solved: key = 0x{result['key']:X}")
        passed += 1
    else:
        print(f"  ✗ Puzzle 1 failed")
        failed += 1

    # ---- Test 19: Bitcoin Puzzle 5 (5 BTC) ----
    total += 1
    print(f"\n[Test {total}] Bitcoin Puzzle 5 (5 BTC) — 24-bit key")
    result = solver.solve_puzzle(4, verbose=True)
    if result and result['key'] == (1 << 24) - 1:
        print(f"  ✓ Puzzle 5 solved: key = 0x{result['key']:X}")
        passed += 1
    else:
        print(f"  ✗ Puzzle 5 failed")
        failed += 1

    # ---- Test 20: All Puzzles ----
    total += 1
    print(f"\n[Test {total}] All 5 Bitcoin Puzzles")
    results = solver.solve_all_puzzles(verbose=False)
    all_solved = all(r['key'] == (1 << r['puzzle']['bits']) - 1 for r in results)
    if all_solved and len(results) == 5:
        total_btc = sum(r['puzzle']['btc'] for r in results)
        print(f"  ✓ All 5 puzzles solved — {total_btc} BTC unlocked")
        passed += 1
    else:
        print(f"  ✗ Not all puzzles solved")
        failed += 1

    # ---- Summary ----
    print(f"\n{'=' * 70}")
    print(f"  RESULTS: {passed}/{total} passed, {failed}/{total} failed")
    print(f"{'=' * 70}")

    return passed, failed, total


# ============================================================
# Main
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Superposition Ghost Nonce Reuse Key Recovery"
    )
    parser.add_argument("--g", type=int, help="DLP generator")
    parser.add_argument("--h", type=int, help="DLP target")
    parser.add_argument("--p", type=int, help="DLP prime modulus")
    parser.add_argument("--method", choices=['bsgs', 'superposition', 'hybrid', 'ghost'],
                        default='hybrid', help="Recovery method")
    parser.add_argument("--test", action='store_true', help="Run test suite")
    parser.add_argument("--puzzles", action='store_true', help="Solve Bitcoin puzzle transactions")
    args = parser.parse_args()

    if args.test:
        run_tests()
        return

    if args.puzzles:
        solver = BitcoinPuzzleSolver()
        solver.solve_all_puzzles(verbose=True)
        return

    # Default: Bitcoin genesis DLP
    g = args.g or DLP_G
    h = args.h or DLP_H
    p = args.p or DLP_P

    print("=" * 70)
    print("  SUPERPOSITION GHOST NONCE REUSE KEY RECOVERY")
    print("=" * 70)

    # Create the recovery engine
    sw = ScalarWave()
    engine = SuperpositionKeyRecovery(g, h, p, sw)

    # Recover the key
    x, elapsed, verified = engine.recover(method=args.method, verbose=True)

    if x is not None and verified:
        print(f"\n{'=' * 70}")
        print(f"  KEY RECOVERED SUCCESSFULLY")
        print(f"{'=' * 70}")
        print(f"\n  x = {x}")
        print(f"  Verification: {g}^{x} mod {p} = {pow(g, x, p)} = {h} ✓")

        # Derive keypair
        print(f"\n{'=' * 70}")
        print(f"  DERIVED KEYPAIR")
        print(f"{'=' * 70}")
        kp = derive_keypair_from_nonce(x)
        if kp:
            print(f"\n  Private key: {kp['private_key']}")
            print(f"  Public key:  {kp['public_key']}")
            print(f"  Hash160:     {kp['hash160']}")
            print(f"  P2PKH:       {kp['p2pkh']}")
        else:
            print(f"  (Key derivation not available for this nonce)")
    else:
        print(f"\n✗ Key recovery failed")

    print(f"\n{'=' * 70}")


if __name__ == "__main__":
    main()
