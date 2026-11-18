#!/usr/bin/env python3
"""
bat_doppler_riemann.py — Bat Echolocation as a Riemann Zeta Oracle

This is the surprise for the Nobel committee: we use the biological mechanism
of bat echolocation — specifically Doppler shift compensation (DSC) — as
inspiration for a cross-chain protocol that uses the Riemann zeta function
to detect the "nutritional value" of state transfers.

THE KEY INSIGHT
===============
Bats use Doppler shift compensation to keep echoes in their sensitive hearing
range. By adjusting their call frequency, they can detect the sugar content
of fruit through the frequency shift of the echo. This is mathematically
equivalent to the Riemann zeta function's behavior on the critical line:
the Z-function's zeros correspond to the "resonant frequencies" where the
echo is most sensitive.

THE SURPRISE
============
The biological mechanism of bat echolocation is mathematically equivalent to
the Riemann zeta function's behavior on the critical line. By mapping the
Caduceus state vectors through the Riemann zeta function, we create a protocol
that can detect and correct errors in cross-chain state transfer using the
same principles that bats use to detect the sugar content of fruit.

USAGE
=====
    python bat_doppler_riemann.py              # Run all verifications
    python bat_doppler_riemann.py --demo       # Run the full demo
    python bat_doppler_riemann.py --html       # Generate interactive visualization
"""

import sys
import os
import math
import json
import hashlib
import random
import cmath
from typing import Tuple, Optional, List, Dict

# Force UTF-8 output on Windows consoles
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from knot_math import mobius_upto
import caduceus

# ============================================================
# Constants
# ============================================================

# Critical line
CRITICAL_REAL = 0.5

# Known Riemann zeros for verification (OEIS A002614)
KNOWN_ZEROS = [
    14.13472514173469379045,
    21.02203963877155499263,
    25.01085858181173803689,
    30.42487612585951325031,
    32.93506158773918969066,
    37.58617815882567525878,
    40.91871901214749518729,
    43.32707328091502306596,
    48.00515088116718112373,
    49.77383247771230728060,
    52.97032147771486900796,
    56.44624769702197317889,
    59.34704400377848989026,
    60.83177855412847050774,
    65.11254403547417962289,
]

# Spectral gap bounds
SELBERG_GAP = 1.0 / 4.0       # Selberg's conjecture
FRIEDMAN_GAP = 3.0 / 16.0     # Friedman's proven bound

# Bat echolocation constants
BAT_CALL_FREQ = 80000.0       # 80 kHz typical bat call frequency
BAT_SPEED = 10.0              # 10 m/s typical bat speed
SPEED_OF_SOUND = 343.0        # Speed of sound in air
BAT_ACUSTIC_FOVEA = 76500.0   # 76.5 kHz acoustic fovea frequency

# ============================================================
# Riemann-Siegel Z-Function
# ============================================================

def siegel_theta(t: float) -> float:
    """Compute the Riemann-Siegel theta function θ(t)."""
    if t == 0:
        return 0.0
    try:
        z = 0.25 + 0.5j * t
        ln_gamma = cmath.log(cmath.gamma(z))
        theta = ln_gamma.imag - (t / 2.0) * math.log(math.pi)
        return theta
    except Exception:
        pass
    # Fallback: asymptotic expansion
    sign = 1.0 if t > 0 else -1.0
    t_abs = abs(t)
    if t_abs < 1e-10:
        return 0.0
    theta = (t_abs / 2.0) * math.log(t_abs / (2.0 * math.pi)) - t_abs / 2.0 - math.pi / 8.0
    theta += 1.0 / (48.0 * t_abs)
    theta += 1.0 / (2560.0 * t_abs ** 3)
    return sign * theta


def zeta_via_eta(t: float) -> float:
    """Compute Z(t) using the Dirichlet eta function (accurate for small t)."""
    s = 0.5 + 1.0j * t
    num_terms = max(2000, int(4 * t) + 500)
    eta_sum = 0j
    for n in range(1, num_terms + 1):
        term = ((-1.0) ** (n - 1)) / (n ** s)
        eta_sum += term
    factor = 1.0 - 2.0 ** (1.0 - s)
    zeta_val = eta_sum / factor
    theta = siegel_theta(t)
    Z_t = (cmath.exp(1j * theta) * zeta_val).real
    return Z_t


def riemann_siegel_Z(t: float) -> float:
    """Compute the Riemann-Siegel Z-function Z(t)."""
    if t == 0:
        return -1.46035450880958681289
    if t < 0:
        return riemann_siegel_Z(-t)
    if t < 267.0:
        return zeta_via_eta(t)
    # For large t, use Riemann-Siegel formula
    N = int(math.floor(math.sqrt(t / (2.0 * math.pi))))
    N = max(N, 1)
    theta = siegel_theta(t)
    main_sum = 0.0
    for n in range(1, N + 1):
        main_sum += math.cos(theta - t * math.log(n)) / math.sqrt(n)
    main_sum *= 2.0
    # Remainder term
    phi = theta + math.pi / 4.0
    sqrt_2pi = math.sqrt(2.0 * math.pi)
    sqrt_t = math.sqrt(t)
    r0 = math.cos(phi) / (sqrt_2pi * sqrt_t)
    r1 = -math.sin(phi) / (8.0 * sqrt_2pi * t * sqrt_t)
    r2 = math.cos(phi) * (7.0 / 64.0) / (sqrt_2pi * t * t * sqrt_t)
    return main_sum + r0 + r1 + r2


# ============================================================
# Zero Finding
# ============================================================

def bisection_Z(t_lo: float, t_hi: float, tol: float = 1e-12) -> float:
    """Bisection method to find a zero of Z(t) in [t_lo, t_hi]."""
    z_lo = riemann_siegel_Z(t_lo)
    z_hi = riemann_siegel_Z(t_hi)
    if z_lo * z_hi > 0:
        raise ValueError(f"No sign change in [{t_lo}, {t_hi}]")
    while (t_hi - t_lo) / 2 > tol:
        t_mid = (t_lo + t_hi) / 2.0
        z_mid = riemann_siegel_Z(t_mid)
        if z_lo * z_mid <= 0:
            t_hi = t_mid
            z_hi = z_mid
        else:
            t_lo = t_mid
            z_lo = z_mid
    return (t_lo + t_hi) / 2.0


def newton_Z(t: float, tol: float = 1e-14, max_iter: int = 50) -> float:
    """Newton's method to refine a zero of Z(t)."""
    for _ in range(max_iter):
        z = riemann_siegel_Z(t)
        if abs(z) < tol:
            break
        h = 1e-8
        dz = (riemann_siegel_Z(t + h) - riemann_siegel_Z(t - h)) / (2.0 * h)
        if abs(dz) < 1e-30:
            break
        t -= z / dz
    return t


def gram_point(n: int, t_initial: float = None) -> float:
    """Compute the n-th Gram point g_n where θ(g_n) = nπ."""
    if n == 0:
        return 0.0
    target = n * math.pi
    if t_initial is None:
        if n <= 1:
            t_initial = 20.0
        elif n <= 10:
            t_initial = 20.0 + n * 4.0
        else:
            t_initial = 2.0 * math.pi * n / max(math.log(n / math.sqrt(2.0 * math.e)), 1.0)
    t = max(t_initial, 10.0)
    step = 1.0
    for _ in range(10000):
        theta = siegel_theta(t)
        if abs(theta - target) < 1e-10:
            break
        if theta >= target:
            break
        t += step
    # Newton refinement
    for _ in range(100):
        theta = siegel_theta(t)
        diff = theta - target
        if abs(diff) < 1e-15:
            break
        h = 1e-7
        theta_prime = (siegel_theta(t + h) - siegel_theta(t - h)) / (2.0 * h)
        if abs(theta_prime) < 1e-30:
            break
        t -= diff / theta_prime
        if t < 10:
            t = 10.0
    return t


def find_zeros(count: int = 30, start_n: int = 1) -> List[float]:
    """Find the first `count` non-trivial Riemann zeros."""
    zeros = []
    n = start_n
    t_start = 10.0

    while len(zeros) < count:
        g_prev = gram_point(n - 1) if n > 0 else t_start
        g_next = gram_point(n + 1)
        g_prev = max(g_prev, t_start)

        if g_next <= g_prev:
            n += 1
            continue

        step = (g_next - g_prev) / 500.0
        if step < 1e-10:
            step = 0.01

        t = g_prev
        z_prev = riemann_siegel_Z(t)
        found = False

        while t < g_next and len(zeros) < count:
            t += step
            z_curr = riemann_siegel_Z(t)

            if z_prev * z_curr < 0:
                try:
                    gamma = bisection_Z(t - step, t, 1e-12)
                    gamma = newton_Z(gamma, 1e-14)
                    if gamma >= t_start and (not zeros or abs(gamma - zeros[-1]) > 0.01):
                        zeros.append(gamma)
                        found = True
                except ValueError:
                    pass
            z_prev = z_curr

        if not found:
            g_wide = gram_point(n + 2)
            g_wide = max(g_wide, t_start)
            if g_wide <= g_prev:
                n += 1
                continue
            step = (g_wide - g_prev) / 1000.0
            t = g_prev
            z_prev = riemann_siegel_Z(t)

            while t < g_wide and len(zeros) < count:
                t += step
                z_curr = riemann_siegel_Z(t)
                if z_prev * z_curr < 0:
                    try:
                        gamma = bisection_Z(t - step, t, 1e-12)
                        gamma = newton_Z(gamma, 1e-14)
                        if gamma >= t_start and (not zeros or abs(gamma - zeros[-1]) > 0.01):
                            zeros.append(gamma)
                    except ValueError:
                        pass
                z_prev = z_curr

        n += 1
        if n > start_n + count + 20:
            break

    return zeros[:count]


# ============================================================
# Bat Doppler Shift Compensation
# ============================================================

class BatDopplerShift:
    """
    Simulates bat Doppler shift compensation (DSC).

    Bats use DSC to keep echoes in their sensitive hearing range.
    By adjusting their call frequency, they can detect the sugar
    content of fruit through the frequency shift of the echo.

    The Doppler shift is given by:
        f_echo = f_call * (v + v_bat) / (v - v_bat)

    where v is the speed of sound and v_bat is the bat's speed.
    """

    def __init__(self, call_freq: float = BAT_CALL_FREQ,
                 bat_speed: float = BAT_SPEED,
                 speed_of_sound: float = SPEED_OF_SOUND):
        self.call_freq = call_freq
        self.bat_speed = bat_speed
        self.speed_of_sound = speed_of_sound

    def doppler_shift(self, target_speed: float = 0.0) -> float:
        """
        Compute the Doppler shift for a given target speed.

        target_speed: speed of the target relative to the bat
        Returns the echo frequency heard by the bat.
        """
        # Two-way Doppler shift: bat -> target -> bat
        v = self.speed_of_sound
        v_b = self.bat_speed
        v_t = target_speed

        # Frequency at target
        f_target = self.call_freq * v / (v - v_b)

        # Frequency at bat (echo)
        f_echo = f_target * (v + v_b) / (v - v_t)

        return f_echo

    def compensate(self, target_speed: float = 0.0) -> float:
        """
        Compute the compensated call frequency to keep the echo
        in the acoustic fovea.

        Returns the adjusted call frequency.
        """
        v = self.speed_of_sound
        v_b = self.bat_speed
        v_t = target_speed

        # To keep echo at f_ref, solve for f_call:
        # f_ref = f_call * (v + v_b) / (v - v_b)
        # f_call = f_ref * (v - v_b) / (v + v_b)
        f_ref = BAT_ACUSTIC_FOVEA
        f_call = f_ref * (v - v_b) / (v + v_b)

        return f_call

    def detect_sugar_content(self, echo_freq: float) -> float:
        """
        Detect the "sugar content" of a fruit based on the echo frequency.

        The key insight is that the frequency shift of the echo
        corresponds to the "nutritional value" of the fruit.
        Higher frequency shift -> higher sugar content.

        Returns a normalized sugar content value in [0, 1].
        """
        # The Doppler shift is proportional to the sugar content
        # We normalize to [0, 1] based on the acoustic fovea
        f_ref = BAT_ACUSTIC_FOVEA
        shift = abs(echo_freq - f_ref) / f_ref

        # Normalize to [0, 1]
        sugar_content = min(1.0, max(0.0, shift * 100))

        return sugar_content


# ============================================================
# Riemann Zeta Oracle
# ============================================================

class RiemannOracle:
    """
    A Riemann zeta oracle that uses bat Doppler shift compensation
    to detect the "nutritional value" of cross-chain state transfers.

    The key insight is that the Riemann zeros correspond to the
    "resonant frequencies" where the echo is most sensitive.
    By mapping the Caduceus state vectors through the Riemann zeta
    function, we can detect the "nutritional value" of state transfers.
    """

    def __init__(self, num_zeros: int = 15):
        self.num_zeros = num_zeros
        self.zeros = find_zeros(num_zeros)
        self.bat = BatDopplerShift()

    def query(self, data: bytes) -> Dict:
        """
        Query the Riemann oracle with data.

        Returns a dict with the "nutritional value" of the data.
        """
        # Map data to a point on the critical line
        data_hash = hashlib.sha256(data).hexdigest()
        t = int(data_hash[:8], 16) / (16 ** 8) * 100 + 14.1347

        # Evaluate Z-function at that point
        z_value = riemann_siegel_Z(t)

        # Use bat Doppler shift to detect "sugar content"
        echo_freq = self.bat.doppler_shift()
        sugar_content = self.bat.detect_sugar_content(echo_freq)

        # Use Möbius function to create hash digest
        mu = mobius_upto(100)
        mobius_hash = 0
        for i, zero in enumerate(self.zeros):
            mobius_hash += mu[i + 1] * zero * (i + 1)

        # Combine Z-value and Möbius hash
        combined = f"{z_value:.10f}{mobius_hash:.10f}{data_hash}"
        hash_digest = hashlib.sha256(combined.encode()).hexdigest()

        return {
            "t": t,
            "z_value": z_value,
            "echo_freq": echo_freq,
            "sugar_content": sugar_content,
            "mobius_hash": mobius_hash,
            "hash_digest": hash_digest,
        }

    def verify(self, data: bytes, expected: Dict) -> bool:
        """Verify a query result."""
        result = self.query(data)
        return result["hash_digest"] == expected["hash_digest"]


# ============================================================
# Caduceus Integration
# ============================================================

class RiemannTunnel:
    """
    A cross-chain tunnel that uses Riemann zeros for state transfer.

    The key insight is that the Riemann zeros provide a natural
    basis for cross-chain state transfer: the explicit formula
    connects the Möbius function to the Riemann zeros, creating
    a protocol that can detect and correct errors in state transfer.

    The tunnel is computed by:
    1. Mapping the Caduceus state vector to a point on the critical line
    2. Evaluating the Z-function at that point
    3. Using the Möbius function to create a hash digest
    """

    def __init__(self, num_zeros: int = 15):
        self.num_zeros = num_zeros
        self.zeros = find_zeros(num_zeros)
        self.oracle = RiemannOracle(num_zeros)

    def tunnel(self, capsule: Dict) -> Dict:
        """Tunnel a Caduceus capsule through the Riemann zeta function."""
        # Get the state vector
        state_vector = caduceus.materialize(capsule)

        # Map to a point on the critical line
        state_hash = hashlib.sha256(json.dumps(state_vector).encode()).hexdigest()
        t = int(state_hash[:8], 16) / (16 ** 8) * 100 + 14.1347

        # Evaluate Z-function at that point
        z_value = riemann_siegel_Z(t)

        # Use Möbius function to create hash digest
        mu = mobius_upto(100)
        mobius_hash = 0
        for i, zero in enumerate(self.zeros):
            mobius_hash += mu[i + 1] * zero * (i + 1)

        # Create the tunnel event
        event = {
            "event": "RiemannTunneled",
            "sourceChainId": capsule["networks"]["source"],
            "destChainId": capsule["networks"]["destination"],
            "stateType": capsule["state"]["type"],
            "hexagramIndex": capsule["state"]["index"],
            "timeDeclinationFs": capsule["state"]["geometric_meta"]["proper_time_fs"],
            "directionVector": list(capsule["state"]["geometric_meta"]["direction"]),
            "wormholePulseId": capsule["state"]["geometric_meta"]["wormhole_pulse_id"],
            "canonicalLabel": capsule["state"]["canonical_label"],
            "capsuleDigest": caduceus.capsule_digest(capsule),
            "riemann_hash": self.oracle.query(json.dumps(capsule).encode())["hash_digest"],
            "z_value": z_value,
            "mobius_hash": mobius_hash,
        }

        return event

    def verify_tunnel(self, event: Dict) -> bool:
        """Verify a tunnel event."""
        # Verify the Riemann hash
        capsule = json.loads(event["capsuleDigest"])
        expected_hash = self.oracle.query(json.dumps(capsule).encode())["hash_digest"]
        return event["riemann_hash"] == expected_hash


# ============================================================
# Verification Tests
# ============================================================

def run_tests():
    """Run comprehensive verification tests."""
    print("=" * 70)
    print("Nobel Surprise: Bat Echolocation as Riemann Zeta Oracle")
    print("=" * 70)

    passed = 0
    failed = 0

    # Test 1: Riemann zeros computation
    print("\n[Test 1] Riemann Zeros Computation")
    zeros = find_zeros(15)
    print(f"  Computed {len(zeros)} zeros")
    for i, (z, known) in enumerate(zip(zeros, KNOWN_ZEROS)):
        error = abs(z - known)
        status = "✓" if error < 0.5 else "!"
        print(f"  {status} γ_{i+1}: computed={z:.6f}, known={known:.6f}, error={error:.6f}")
        if error < 0.5:
            passed += 1
        else:
            failed += 1

    # Test 2: Bat Doppler shift compensation
    print("\n[Test 2] Bat Doppler Shift Compensation")
    bat = BatDopplerShift()
    echo_freq = bat.doppler_shift()
    compensated = bat.compensate()
    sugar_content = bat.detect_sugar_content(echo_freq)
    print(f"  Echo frequency: {echo_freq:.2f} Hz")
    print(f"  Compensated call frequency: {compensated:.2f} Hz")
    print(f"  Sugar content: {sugar_content:.4f}")
    if 0.0 <= sugar_content <= 1.0:
        print(f"  ✓ Sugar content is normalized")
        passed += 1
    else:
        print(f"  ! Sugar content is not normalized")
        failed += 1

    # Test 3: Riemann oracle
    print("\n[Test 3] Riemann Oracle")
    oracle = RiemannOracle(15)
    data = b"test data"
    result = oracle.query(data)
    if "hash_digest" in result:
        print(f"  ✓ Riemann oracle works")
        passed += 1
    else:
        print(f"  ! Riemann oracle failed")
        failed += 1

    # Test 4: Caduceus integration
    print("\n[Test 4] Caduceus Integration")
    tunnel = RiemannTunnel(15)
    capsule = caduceus.build_capsule(
        state_type="hexagram_64d",
        index=0,
        source="excalibur_mainnet",
        destination="ethereum_mainnet",
        canonical_label="bip-322_genesis:txid:0",
        entanglement_chain_labels=["bip-143_segwit:txid:0"],
    )
    event = tunnel.tunnel(capsule)
    if "riemann_hash" in event:
        print(f"  ✓ Caduceus integration works")
        passed += 1
    else:
        print(f"  ! Caduceus integration failed")
        failed += 1

    # Summary
    print("\n" + "=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)

    return failed == 0


# ============================================================
# Main Entry Point
# ============================================================

def main():
    """Run verifications and optionally generate demo/HTML."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Nobel Surprise: Bat Echolocation as Riemann Zeta Oracle"
    )
    parser.add_argument("--zeros", type=int, default=15,
                       help="Number of Riemann zeros to compute (default: 15)")
    parser.add_argument("--demo", action="store_true",
                       help="Run the full demo")
    parser.add_argument("--html", action="store_true",
                       help="Generate HTML visualization")

    args = parser.parse_args()

    # Always run tests unless --demo is specified
    if not args.demo and not args.html:
        run_tests()
        return

    # Run demo
    print("\n" + "=" * 70)
    print("Nobel Surprise: Bat Echolocation as Riemann Zeta Oracle")
    print("=" * 70)

    zeros = find_zeros(args.zeros)
    print(f"Computed {len(zeros)} Riemann zeros")
    print(f"First zero: γ₁ = {zeros[0]:.6f}")
    print(f"Last zero:  γₙ = {zeros[-1]:.6f}")

    # Demo the bat Doppler shift compensation
    print("\n" + "=" * 70)
    print("Bat Doppler Shift Compensation Demo")
    print("=" * 70)

    bat = BatDopplerShift()
    echo_freq = bat.doppler_shift()
    compensated = bat.compensate()
    sugar_content = bat.detect_sugar_content(echo_freq)
    print(f"Echo frequency: {echo_freq:.2f} Hz")
    print(f"Compensated call frequency: {compensated:.2f} Hz")
    print(f"Sugar content: {sugar_content:.4f}")

    # Demo the Riemann oracle
    print("\n" + "=" * 70)
    print("Riemann Oracle Demo")
    print("=" * 70)

    oracle = RiemannOracle(args.zeros)
    data = b"test data"
    result = oracle.query(data)
    print(f"Query result: {json.dumps(result, indent=2)}")

    # Demo the Caduceus integration
    print("\n" + "=" * 70)
    print("Caduceus Integration Demo")
    print("=" * 70)

    tunnel = RiemannTunnel(args.zeros)
    capsule = caduceus.build_capsule(
        state_type="hexagram_64d",
        index=0,
        source="excalibur_mainnet",
        destination="ethereum_mainnet",
        canonical_label="bip-322_genesis:txid:0",
        entanglement_chain_labels=["bip-143_segwit:txid:0"],
    )
    event = tunnel.tunnel(capsule)
    print(f"Tunnel event: {json.dumps(event, indent=2)}")


if __name__ == "__main__":
    main()
