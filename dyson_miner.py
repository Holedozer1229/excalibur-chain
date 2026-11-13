#!/usr/bin/env python3
"""
dyson_miner.py — Quantum Gravity Miner: Valknut Dial v9 + Dyson Sphere Equilibrium

Python port of the TypeScript Quantum Gravity Miner with Spectral Lattice Correlation.

Synthesizes:
 • Riemann zeta spectral gaps (Δtₙ)
 • Quaternion 1/2 prime resonator lattice (quantum gaps ΔEₙ)
 • R₉₀ rotational symmetry
 • Valknut dial v9: spectral cube, Berry flow, quantum-Fibonacci, Dyson equilibrium
 • Dyson Sphere relativistic pressure balance factor

Usage:
    from dyson_miner import dyson_miner, start_dyson_evolution, stop_dyson_evolution

    # Mine a block with Valknut v9 filter
    result = dyson_miner.mine("block_header_data", max_attempts=50000)

    # Get Valknut candidates
    candidates = dyson_miner.generate_valknut_candidates("seed", n=30)

    # Get state snapshot
    state = dyson_miner.get_state()

    # Start/stop background lattice evolution
    start_dyson_evolution()
    stop_dyson_evolution()
"""

import hashlib
import math
import os
import random
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple


# ─── Prime Generation (Miller-Rabin) ─────────────────────────────────────────


def is_prime_mr(n: int) -> bool:
    """Miller-Rabin primality test."""
    if n < 2:
        return False
    if n == 2 or n == 3:
        return True
    if n % 2 == 0:
        return False

    d = n - 1
    s = 0
    while d % 2 == 0:
        d //= 2
        s += 1

    for _ in range(5):
        a = 2 + random.randint(0, n - 3)
        x = pow(a, d, n)
        if x == 1 or x == n - 1:
            continue
        cont = False
        for _ in range(s - 1):
            x = pow(x, 2, n)
            if x == n - 1:
                cont = True
                break
        if not cont:
            return False
    return True


def generate_primes(n: int) -> List[int]:
    """Generate the first n primes using Miller-Rabin."""
    primes = []
    num = 2
    while len(primes) < n:
        if is_prime_mr(num):
            primes.append(num)
        num += 1
    return primes


# ─── Riemann Zeta Zeros (Approximate) ────────────────────────────────────────

KNOWN_ZEROS = [
    14.134725141734693, 21.022039638771554, 25.010857580145688,
    30.424876125859513, 32.935061587739189, 37.586178158825671,
    40.918719012147495, 43.327073280914999, 48.005150881167159,
    49.773832477672302,
]


def zeta_zero_approx(n: int) -> float:
    """Approximate the n-th non-trivial Riemann zeta zero."""
    if n <= len(KNOWN_ZEROS):
        return KNOWN_ZEROS[n - 1]
    term = (n - 11 / 8) / math.e
    w = math.log(term) - math.log(math.log(term))
    return 2 * math.pi * (n - 11 / 8) / w


def spectral_gaps(n_zeros: int = 28) -> List[float]:
    """Compute gaps between consecutive Riemann zeta zeros."""
    zeros = [zeta_zero_approx(i + 1) for i in range(n_zeros + 1)]
    return [zeros[i + 1] - zeros[i] for i in range(n_zeros)]


# ─── Quaternion Algebra ───────────────────────────────────────────────────────

Quaternion = Dict[str, float]


def qadd(p: Quaternion, q: Quaternion) -> Quaternion:
    """Add two quaternions."""
    return {
        "a": p["a"] + q["a"],
        "b": p["b"] + q["b"],
        "c": p["c"] + q["c"],
        "d": p["d"] + q["d"],
    }


def qmul(p: Quaternion, q: Quaternion) -> Quaternion:
    """Multiply two quaternions."""
    return {
        "a": p["a"] * q["a"] - p["b"] * q["b"] - p["c"] * q["c"] - p["d"] * q["d"],
        "b": p["a"] * q["b"] + p["b"] * q["a"] + p["c"] * q["d"] - p["d"] * q["c"],
        "c": p["a"] * q["c"] - p["b"] * q["d"] + p["c"] * q["a"] + p["d"] * q["b"],
        "d": p["a"] * q["d"] + p["b"] * q["c"] - p["c"] * q["b"] + p["d"] * q["a"],
    }


def qnorm(q: Quaternion) -> float:
    """Compute the norm of a quaternion."""
    return math.sqrt(q["a"] ** 2 + q["b"] ** 2 + q["c"] ** 2 + q["d"] ** 2)


def from_axis_angle(axis: Tuple[float, float, float], angle: float) -> Quaternion:
    """Create a quaternion from axis-angle representation."""
    norm = math.sqrt(axis[0] ** 2 + axis[1] ** 2 + axis[2] ** 2)
    if norm < 1e-10:
        return {"a": 1, "b": 0, "c": 0, "d": 0}
    x, y, z = (v / norm for v in axis)
    h = angle / 2
    s = math.sin(h)
    return {"a": math.cos(h), "b": x * s, "c": y * s, "d": z * s}


# ─── R₉₀ Rotation (90° about z-axis) ────────────────────────────────────────


def rotate_pos(pos: Tuple[float, float, float]) -> Tuple[float, float, float]:
    """Rotate position by 90° about z-axis."""
    return (-pos[0], pos[1], pos[2])


# ─── Prime Resonator ─────────────────────────────────────────────────────────

PrimeResonator = Dict[str, Any]


def make_prime_resonator(
    prime: int, gap: float, pos: Tuple[float, float, float]
) -> PrimeResonator:
    """Create a prime resonator with given parameters."""
    frequency = math.log(prime) * gap
    axis: Tuple[float, float, float] = (1 / math.sqrt(3), 1 / math.sqrt(3), 1 / math.sqrt(3))
    state = from_axis_angle(axis, frequency)
    energy = math.sqrt(math.log(prime) ** 2 + (math.pi / 2) ** 2) * gap
    return {
        "prime": prime,
        "spectralGap": gap,
        "pos": pos,
        "frequency": frequency,
        "state": state,
        "energy": energy,
    }


def evolve_resonator(
    r: PrimeResonator, dt: float, coupling: Quaternion
) -> PrimeResonator:
    """Evolve a resonator's state over time dt with given coupling."""
    cn = qnorm(coupling)
    if cn > 0:
        axis: Tuple[float, float, float] = (
            coupling["b"] / cn,
            coupling["c"] / cn,
            coupling["d"] / cn,
        )
        evolution = from_axis_angle(axis, cn * dt)
        return {
            **r,
            "state": qmul(evolution, r["state"]),
            "frequency": r["frequency"] + 0.01 * (cn - 1) * dt,
        }
    return r


# ─── Golden-Ratio Spiral Positions ───────────────────────────────────────────


def golden_positions(n: int) -> List[Tuple[float, float, float]]:
    """Generate n positions on a golden-ratio spiral."""
    phi = (1 + math.sqrt(5)) / 2
    positions = []
    for i in range(n):
        scale = 10.0 / (i + 1)
        pos = (
            phi * i * math.cos(2 * math.pi * phi * i) * scale,
            phi * i * math.sin(2 * math.pi * phi * i) * scale,
            phi * i * math.sin(2 * math.pi * phi ** 2 * i) * scale,
        )
        positions.append(pos)
    return positions


# ─── Resonator Lattice ────────────────────────────────────────────────────────

ResonatorLattice = Dict[str, Any]


def build_coupling(
    positions: List[Tuple[float, float, float]], primes: List[int]
) -> Dict[str, Quaternion]:
    """Build coupling map between resonator pairs."""
    coup = {}
    n = len(positions)
    for i in range(n):
        for j in range(i + 1, n):
            xi, yi, zi = positions[i]
            xj, yj, zj = positions[j]
            dx = xj - xi
            dy = yj - yi
            dz = zj - zi
            dist = math.sqrt(dx ** 2 + dy ** 2 + dz ** 2)
            if dist < 1e-10:
                continue
            strength = math.log(primes[j]) / math.log(primes[i]) / dist
            coup[f"{i},{j}"] = {
                "a": 0,
                "b": strength * dx / dist,
                "c": strength * dy / dist,
                "d": strength * dz / dist,
            }
    return coup


def calc_freq_gaps(resonators: List[PrimeResonator]) -> List[float]:
    """Calculate frequency gaps from sorted resonator frequencies."""
    freqs = sorted(r["frequency"] for r in resonators)
    return [freqs[i + 1] - freqs[i] for i in range(len(freqs) - 1)]


def normalize(arr: List[float]) -> List[float]:
    """Normalize array to zero mean, unit variance."""
    if len(arr) < 2:
        return arr
    m = sum(arr) / len(arr)
    s = math.sqrt(sum((x - m) ** 2 for x in arr) / len(arr)) or 1
    return [(x - m) / s for x in arr]


def pearson(x: List[float], y: List[float]) -> float:
    """Compute Pearson correlation coefficient."""
    n = min(len(x), len(y))
    if n < 2:
        return 0
    sx = sy = sxy = sx2 = sy2 = 0.0
    for i in range(n):
        sx += x[i]
        sy += y[i]
        sxy += x[i] * y[i]
        sx2 += x[i] ** 2
        sy2 += y[i] ** 2
    den = math.sqrt((n * sx2 - sx ** 2) * (n * sy2 - sy ** 2))
    return (n * sxy - sx * sy) / den if den != 0 else 0


def correlate(lattice_gaps: List[float], spec_gaps: List[float]) -> float:
    """Correlate lattice gaps with spectral gaps."""
    m = min(len(lattice_gaps), len(spec_gaps))
    if m < 2:
        return 0
    return pearson(normalize(lattice_gaps[:m]), normalize(spec_gaps[:m]))


def build_resonator_lattice(
    primes: List[int], spec_gaps: List[float]
) -> ResonatorLattice:
    """Build the full resonator lattice with correlations."""
    n = min(len(primes), len(spec_gaps))
    positions = golden_positions(n)
    rot_positions = [rotate_pos(p) for p in positions]

    resonators = [
        make_prime_resonator(p, spec_gaps[i % len(spec_gaps)], positions[i])
        for i, p in enumerate(primes[:n])
    ]
    resonators_rot = [
        make_prime_resonator(p, spec_gaps[i % len(spec_gaps)], rot_positions[i])
        for i, p in enumerate(primes[:n])
    ]

    coupling = build_coupling(positions, primes)
    coupling_rot = build_coupling(rot_positions, primes)

    freq_gaps = calc_freq_gaps(resonators)
    freq_gaps_rot = calc_freq_gaps(resonators_rot)

    return {
        "primes": primes,
        "specGaps": spec_gaps,
        "resonators": resonators,
        "resonatorsRot": resonators_rot,
        "coupling": coupling,
        "couplingRot": coupling_rot,
        "freqGaps": freq_gaps,
        "freqGapsRot": freq_gaps_rot,
        "corr": correlate(freq_gaps, spec_gaps),
        "corrRot": correlate(freq_gaps_rot, spec_gaps),
    }


def evolve_lattice(
    lattice: ResonatorLattice, dt: float = 0.01, steps: int = 30
) -> List[float]:
    """Evolve lattice over multiple steps and return correlation history."""
    resonators = list(lattice["resonators"])
    corrs: List[float] = []
    for _ in range(steps):
        resonators = [
            evolve_resonator(
                r,
                dt,
                sum(
                    (
                        lattice["coupling"].get(f"{min(i, j)},{max(i, j)}")
                        for j in range(len(resonators))
                        if i != j
                    ),
                    {"a": 0, "b": 0, "c": 0, "d": 0},
                ),
            )
            for i, r in enumerate(resonators)
        ]
        gaps = calc_freq_gaps(resonators)
        corrs.append(correlate(gaps, lattice["specGaps"]))
    return corrs


# ─── Valknut v9 Components ────────────────────────────────────────────────────


def sha256_hex(data: str) -> str:
    """Compute SHA-256 hash as hex string."""
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def zeta_like(data: str) -> float:
    """Compute zeta-like value from data hash."""
    h = sha256_hex(data)
    return int(h[:8], 16) / 2**32


def thue_morse_phase(data: str) -> float:
    """Compute Thue-Morse phase from data."""
    raw = data.encode("utf-8")[:257]
    cum = 0
    for b in raw:
        cum = (cum + bin(b).count("1")) % 2
    return ((cum * 2 * math.pi) % (2 * math.pi)) / (2 * math.pi)


def geom_curv_at_fib(data: str, fib: int) -> float:
    """Compute geometric curvature at Fibonacci index."""
    h = sha256_hex(f"{data}{fib}")
    return int(h[:4], 16) / 65535


def dyson_factor(data: str) -> float:
    """
    Dyson Sphere Equilibrium Factor.
    Computes dimensionless Dyson equilibrium from block data using
    the exact relativistic thin shell pressure formula.
    Returns [0, 2] centered at 1 for perfect equilibrium.
    """
    h = sha256_hex(data)
    M_sun = (int(h[:4], 16) / 65535) * 10
    R_sun = (int(h[4:8], 16) / 65535) * 20
    rho_gcm3 = (int(h[8:12], 16) / 65535) * 100

    M_kg = M_sun * 1.989e30
    R_m = R_sun * 6.957e8
    rho_kgm3 = rho_gcm3 * 1000.0

    G = 6.6743e-11
    rho_c = 1000.0

    denom = 2.0 * (R_m - 2.0 * G * M_kg) * (1.0 + rho_kgm3 / rho_c)
    if denom <= 0 or abs(denom) < 1e-30:
        return 2.0

    P_t = (G * M_kg * rho_kgm3 * R_m) / denom
    P_ref = 1e10
    dyson = math.tanh(P_t / P_ref) * 2.0
    return max(0, min(2, dyson))


def xi_valknut_v9(data: str) -> float:
    """
    Compute Valknut v9 xi score for block data.
    xi = (spectral_cube + berry_flow + quantum_fibonacci + dyson_equilibrium) / 4
    Valid mining candidate: |xi - 1| < 0.016
    """
    hbar = 1.0545718e-34
    gamma = 1.0
    m = 1.0
    v_eff = 1.0

    spec_cube = zeta_like(data) ** 3
    berry = thue_morse_phase(data)
    fibs = [1, 2, 3, 5, 8, 13, 21]
    geom_sum = sum(geom_curv_at_fib(data, f) for f in fibs)
    q_fib = max(0, min(2, (hbar / (gamma * m * v_eff)) * geom_sum))
    dyson = dyson_factor(data)
    return (spec_cube + berry + q_fib + dyson) / 4.0


# ─── Quantum Spectral Correlator ──────────────────────────────────────────────


class QuantumGravityMinerV9:
    """
    Quantum Gravity Miner with Spectral Lattice Correlation.

    Manages the resonator lattice, computes correlations, and mines
    blocks using the Valknut v9 filter.
    """

    def __init__(self, n_modes: int = 28):
        self.n_modes = n_modes
        self.primes = generate_primes(n_modes)
        self.spec_gaps = spectral_gaps(n_modes)
        self.lattice = build_resonator_lattice(self.primes, self.spec_gaps)
        self.eigenvalues = self._approx_eigenvalues()
        self.quantum_gaps = self._calc_quantum_gaps()
        self.final_corr_orig = 0.0
        self.final_corr_rot = 0.0
        self.epoch = 0
        self.xi_tolerance = 0.016
        self.last_update = time.time()

    def _approx_eigenvalues(self) -> List[float]:
        """Approximate eigenvalues from resonator energies and couplings."""
        ev = []
        for i in range(self.n_modes):
            r = self.lattice["resonators"][i]
            coup_sum = sum(
                qnorm(self.lattice["coupling"][f"{min(i, j)},{max(i, j)}"])
                for j in range(self.n_modes)
                if i != j
                and f"{min(i, j)},{max(i, j)}" in self.lattice["coupling"]
            )
            ev.append(r["energy"] + 0.5 * coup_sum)
        return sorted(ev)

    def _calc_quantum_gaps(self) -> List[float]:
        """Calculate quantum gaps from sorted eigenvalues."""
        return [
            self.eigenvalues[i + 1] - self.eigenvalues[i]
            for i in range(len(self.eigenvalues) - 1)
        ]

    def evolve(self, dt: float = 0.01, steps: int = 20) -> None:
        """Evolve the lattice once per epoch — updates correlations."""
        orig_corrs = evolve_lattice(self.lattice, dt, steps)
        self.final_corr_orig = orig_corrs[-1] if orig_corrs else 0

        # Rotate lattice evolution
        rot_lattice = {
            **self.lattice,
            "resonators": self.lattice["resonatorsRot"],
            "coupling": self.lattice["couplingRot"],
        }
        rot_corrs = evolve_lattice(rot_lattice, dt, steps)
        self.final_corr_rot = rot_corrs[-1] if rot_corrs else 0

        self.epoch += 1
        self.last_update = time.time()

    @property
    def chain_correlation(self) -> float:
        """Compute chain correlation product (quality signal)."""
        m = min(len(self.quantum_gaps), len(self.spec_gaps))
        qn = normalize(self.quantum_gaps[:m])
        zn = normalize(self.spec_gaps[:m])
        q_zeta = pearson(qn, zn)
        return q_zeta * self.lattice["corr"] * self.final_corr_orig

    @property
    def hash_rate_boost(self) -> float:
        """Hash rate boost multiplier from Dyson equilibrium (1.0 = baseline)."""
        cc = abs(self.chain_correlation)
        return 1.0 + cc * 4.5

    def generate_valknut_candidates(
        self, seed: str, n: int = 30
    ) -> List[Dict[str, Any]]:
        """Generate Valknut candidates from quantum gaps."""
        candidates = []
        for i in range(min(n, len(self.quantum_gaps))):
            gap = self.quantum_gaps[i]
            offset = int(abs(gap) * 1e6) % 1_000_000 - 500_000
            data = f"{seed}:{i}:{offset}:{self.epoch}"
            xi = xi_valknut_v9(data)
            df = dyson_factor(data)
            berry = thue_morse_phase(data)
            candidates.append(
                {
                    "index": i + 1,
                    "offset": offset,
                    "xi": xi,
                    "gap": gap,
                    "passes_filter": abs(xi - 1.0) <= self.xi_tolerance,
                    "hash_rate_boost": self.hash_rate_boost,
                    "dyson_equilibrium": df,
                    "berry_phase": berry,
                }
            )
        candidates.sort(key=lambda c: abs(c["xi"] - 1))
        return candidates

    def mine(
        self, block_data: str, max_attempts: int = 50_000
    ) -> Dict[str, Any]:
        """
        Mine with Valknut v9 filter — finds nonce where xi is near equilibrium.

        Returns a dict with mining result details.
        """
        best_xi = 0.0
        best_nonce: Optional[int] = None
        best_hash: Optional[str] = None

        for nonce in range(max_attempts):
            data = f"{block_data}:{nonce}:{self.epoch}"
            xi = xi_valknut_v9(data)
            passes = abs(xi - 1.0) <= self.xi_tolerance

            if passes:
                df = dyson_factor(data)
                berry = thue_morse_phase(data)
                spec = zeta_like(data) ** 3
                block_hash = sha256_hex(data)

                return {
                    "nonce": nonce,
                    "block_hash": block_hash,
                    "xi": xi,
                    "dyson_factor": df,
                    "berry_phase": berry,
                    "spec_cube": spec,
                    "quantum_fib": xi - (spec + berry + df) / 4 + xi / 4,
                    "valknut_pass": True,
                    "attempts": nonce + 1,
                    "hash_rate_boost": self.hash_rate_boost,
                    "chain_correlation": self.chain_correlation,
                }

            if best_nonce is None or abs(xi - 1.0) < abs(best_xi - 1.0):
                best_xi = xi
                best_nonce = nonce
                best_hash = sha256_hex(data)

        # No valid nonce found — return best attempt
        data = f"{block_data}:{best_nonce}:{self.epoch}"
        return {
            "nonce": None,
            "block_hash": None,
            "xi": best_xi,
            "dyson_factor": dyson_factor(data),
            "berry_phase": thue_morse_phase(data),
            "spec_cube": zeta_like(data) ** 3,
            "quantum_fib": 0,
            "valknut_pass": False,
            "attempts": max_attempts,
            "hash_rate_boost": self.hash_rate_boost,
            "chain_correlation": self.chain_correlation,
        }

    def get_state(self) -> Dict[str, Any]:
        """Get current miner state snapshot."""
        candidates = self.generate_valknut_candidates("skynt-state", 30)
        pass_count = sum(1 for c in candidates if c["passes_filter"])
        avg_dyson = sum(c["dyson_equilibrium"] for c in candidates) / len(candidates)

        return {
            "primes": self.primes[:10],
            "spec_gaps": self.spec_gaps[:10],
            "lattice_corr": self.lattice["corr"],
            "lattice_corr_rot": self.lattice["corrRot"],
            "quantum_gaps": self.quantum_gaps[:10],
            "chain_correlation": self.chain_correlation,
            "final_corr_orig": self.final_corr_orig,
            "final_corr_rot": self.final_corr_rot,
            "eigenvalues": self.eigenvalues[:10],
            "valknut_pass_rate": pass_count / len(candidates),
            "hash_rate_boost": self.hash_rate_boost,
            "dyson_equilibrium": avg_dyson,
            "xi_tolerance": self.xi_tolerance,
            "epoch": self.epoch,
            "last_update": self.last_update,
        }


# ─── Singleton + Background Evolution ────────────────────────────────────────

dyson_miner = QuantumGravityMinerV9(28)

_evolution_handle: Optional[threading.Timer] = None
_evolution_lock = threading.Lock()


def _evolution_loop() -> None:
    """Internal evolution loop callback."""
    global _evolution_handle
    try:
        dyson_miner.evolve(0.01, 20)
        ds = dyson_miner.get_state()
        print(
            f"[DysonSphere] Epoch {ds['epoch']} — "
            f"chainCorr={ds['chain_correlation']:.4f} "
            f"boost={ds['hash_rate_boost']:.2f}x"
        )
        # Schedule next evolution
        with _evolution_lock:
            _evolution_handle = threading.Timer(60.0, _evolution_loop)
            _evolution_handle.daemon = True
            _evolution_handle.start()
    except Exception as e:
        print(f"[DysonSphere] Evolution error: {e}", file=sys.stderr)


def start_dyson_evolution() -> None:
    """Start background lattice evolution (every 60 seconds)."""
    global _evolution_handle
    with _evolution_lock:
        if _evolution_handle is not None:
            return
        dyson_miner.evolve(0.01, 20)
        _evolution_handle = threading.Timer(60.0, _evolution_loop)
        _evolution_handle.daemon = True
        _evolution_handle.start()


def stop_dyson_evolution() -> None:
    """Stop background lattice evolution."""
    global _evolution_handle
    with _evolution_lock:
        if _evolution_handle is not None:
            _evolution_handle.cancel()
            _evolution_handle = None


def is_dyson_evolution_running() -> bool:
    """Check if background evolution is running."""
    return _evolution_handle is not None


# ─── CLI Entry Point ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    print("=== Dyson Sphere Miner v9 ===")
    print()

    # Show initial state
    state = dyson_miner.get_state()
    print(f"Chain correlation: {state['chain_correlation']:.6f}")
    print(f"Hash rate boost: {state['hash_rate_boost']:.2f}x")
    print(f"Dyson equilibrium: {state['dyson_equilibrium']:.4f}")
    print(f"Valknut pass rate: {state['valknut_pass_rate']:.2%}")
    print()

    # Mine a test block
    print("Mining test block...")
    result = dyson_miner.mine("test-block-header", max_attempts=10_000)
    print(json.dumps(result, indent=2))
    print()

    # Show candidates
    candidates = dyson_miner.generate_valknut_candidates("test-seed", n=10)
    print("Top 10 Valknut candidates:")
    for c in candidates:
        status = "✓" if c["passes_filter"] else " "
        print(
            f"  {status} #{c['index']}: xi={c['xi']:.6f} "
            f"dyson={c['dyson_equilibrium']:.4f} "
            f"berry={c['berry_phase']:.4f}"
        )
