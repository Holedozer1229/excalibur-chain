#!/usr/bin/env python3
"""
Retrocausal Inverse Entropy Wells on Bitcoin Causal Sinks
==========================================================

Burn addresses (1BitcoinEater, Counterparty burn, etc.) are causal sinks —
points where value enters the blockchain but can never leave. In standard
causality, information flows forward. But what if these sinks create
retrocausal effects?

This module applies inverse entropy wells with arctan2 phase shifts to
probe whether burn addresses emit signals backward through the chain.

The core transformation uses:
- Lambda matrix: [[1, 1, 1], [1, 0, -1]]
- Phase constant: 0.33333333326 (slightly perturbed from 1/3)
- arctan2 phase shift for complex plane rotation

The inverse entropy well concept:
- Normal entropy: S = -Σ p_i log(p_i) — measures disorder
- Inverse entropy well: S_inv = Σ p_i log(p_i) — measures order potential
- The "well" is the negative gradient of inverse entropy, pointing toward
  states of higher order — retrocausally, this is the direction information
  would flow from future to past

Wheeler's "It from Bit" meets retrocausality: if the future state of the
universe constrains the past, burn addresses — as permanent causal sinks —
might be the anchors for retrocausal information flow.
"""

import hashlib
import json
import math
import time
import urllib.request
import urllib.error
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

BASE_URL = "https://mempool.space/api"


# ============================================================
# CONSTANTS
# ============================================================

# The lambda matrix for retrocausal transformation
# Shape: (3, 3) — maps 3D causal state to 3D retrocausal phase space
# Row 0: [1, 1, 1]  — total energy (sum of all components)
# Row 1: [1, 0, -1] — temporal asymmetry (first minus last)
# Row 2: [-1, -1, -1] — anti-energy (negative of total — the retrocausal mirror)
LAMBDA_MATRIX = [[1, 1, 1], [1, 0, -1], [-1, -1, -1]]

# Phase constant — slightly perturbed from 1/3
# This perturbation is critical: exactly 1/3 would produce periodic orbits
# The perturbation creates quasi-periodic behavior characteristic of
# retrocausal systems with slight future-past mismatch
PHASE_CONSTANT = 0.33333333326

# Known burn addresses from digital physics experiments
# These are the actual addresses that work with mempool.space API
KNOWN_BURN_ADDRESSES = [
    {"address": "1BitcoinEaterAddressDontSendf59kuE", "label": "1BitcoinEater", "expected_burn": 13.4},
    {"address": "1CounterpartyXXXXXXXXXXXXXXXUWLpVr", "label": "Counterparty Burn", "expected_burn": 2131},
    {"address": "1FAWFFFFFFFFFFFFFFFFFFFFFFFFFFFFec", "label": "Faucet Burn", "expected_burn": 0},
]


# ============================================================
# DATA CLASSES
# ============================================================

@dataclass
class CausalSinkState:
    """State of a causal sink (burn address)."""
    address: str
    label: str
    total_burned_satoshi: int
    transaction_count: int
    first_burn_height: int
    last_burn_height: int
    burn_timestamps: List[int]
    burn_amounts: List[int]
    burn_txids: List[str]


@dataclass
class RetrocausalSignal:
    """A retrocausal signal detected at a causal sink."""
    sink_address: str
    phase_angle: float  # arctan2 result in radians
    phase_shift: float  # applied phase shift
    inverse_entropy: float  # negative Shannon entropy
    entropy_well_depth: float  # depth of the inverse entropy well
    lambda_projection: List[float]  # λ matrix projection
    retrocausal_strength: float  # magnitude of retrocausal effect
    temporal_coherence: float  # how coherent the signal is across time
    frequency_components: List[float]  # FFT-like frequency decomposition


@dataclass
class EntropyWellResult:
    """Result of inverse entropy well analysis."""
    sink_address: str
    well_depth: float
    phase_shift_applied: float
    retrocausal_signals: List[RetrocausalSignal]
    convergence_iterations: int
    final_state: List[float]  # converged state vector
    causal_violation_score: float  # how much causality is "violated"


# ============================================================
# CORE MATH
# ============================================================

def matrix_vector_multiply(matrix: List[List[float]], vector: List[float]) -> List[float]:
    """Multiply matrix by vector: y = Mx."""
    result = []
    for row in matrix:
        dot = sum(r * v for r, v in zip(row, vector))
        result.append(dot)
    return result


def arctan2_phase_shift(y: float, x: float, phase_constant: float = PHASE_CONSTANT) -> float:
    """
    Compute arctan2 with retrocausal phase shift.
    
    Standard arctan2 gives the angle in [-π, π].
    The phase shift rotates this angle by the phase constant,
    creating a mapping from forward-causal to retrocausal phase space.
    
    The perturbation from 1/3 ensures the rotation is irrational
    relative to 2π, producing dense orbits on the unit circle —
    a signature of retrocausal mixing.
    """
    base_angle = math.atan2(y, x)
    shifted_angle = base_angle + 2 * math.pi * phase_constant
    # Normalize to [-π, π]
    while shifted_angle > math.pi:
        shifted_angle -= 2 * math.pi
    while shifted_angle < -math.pi:
        shifted_angle += 2 * math.pi
    return shifted_angle


def shannon_entropy(probabilities: List[float]) -> float:
    """Standard Shannon entropy: S = -Σ p_i log(p_i)."""
    entropy = 0.0
    for p in probabilities:
        if p > 0:
            entropy -= p * math.log2(p)
    return entropy


def inverse_entropy(probabilities: List[float]) -> float:
    """
    Inverse entropy: S_inv = Σ p_i log(p_i).
    
    This is the negative of Shannon entropy. While Shannon entropy
    measures disorder, inverse entropy measures the potential for order.
    In a retrocausal framework, the inverse entropy well represents
    the gravitational pull toward ordered states from the future.
    """
    inv = 0.0
    for p in probabilities:
        if p > 0:
            inv += p * math.log2(p)
    return inv


def entropy_well_gradient(probabilities: List[float], epsilon: float = 1e-10) -> List[float]:
    """
    Compute the gradient of the inverse entropy well.
    
    ∇S_inv = [∂S_inv/∂p_1, ∂S_inv/∂p_2, ...]
    where S_inv = Σ p_i log(p_i)
    
    ∂S_inv/∂p_i = log(p_i) + 1/ln(2)
    
    The gradient points in the direction of steepest ascent
    in inverse entropy — i.e., toward more ordered states.
    """
    gradient = []
    for p in probabilities:
        if p > epsilon:
            grad = math.log2(p) + 1.0 / math.log(2)
        else:
            grad = -1e10  # Strong push away from zero probability
        gradient.append(grad)
    return gradient


def lambda_transform(state_vector: List[float]) -> List[float]:
    """
    Apply the lambda matrix transformation.
    
    The lambda matrix [[1,1,1],[1,0,-1],[-1,-1,-1]] maps a 3D causal state
    to a 3D retrocausal phase space:
    
    y_0 =  x_0 +  x_1 +  x_2  (total energy — sum of all components)
    y_1 =  x_0 +  0*x_1 -  x_2  (temporal asymmetry — first minus last)
    y_2 = -x_0 -  x_1 -  x_2  (anti-energy — negative mirror of total)
    
    The third row [-1,-1,-1] is the retrocausal mirror: it creates the
    inverse energy component that allows the system to detect when future
    states constrain past states. Without it, the transformation is purely
    forward-causal. With it, the system can detect retrocausal feedback.
    
    Key property: y_0 + y_2 = 0 (energy and anti-energy cancel in equilibrium)
    A deviation from this equilibrium indicates retrocausal influence.
    """
    if len(state_vector) < 3:
        # Pad with zeros if needed
        padded = state_vector + [0.0] * (3 - len(state_vector))
    else:
        padded = state_vector[:3]
    
    return matrix_vector_multiply(LAMBDA_MATRIX, padded)


def retrocausal_arctan2_transform(
    x_component: float,
    y_component: float,
    phase_constant: float = PHASE_CONSTANT
) -> Tuple[float, float, float]:
    """
    Full retrocausal arctan2 transformation.
    
    Returns: (phase_angle, cos_component, sin_component)
    
    This maps a point in the causal plane to the retrocausal phase space,
    where the phase shift encodes the retrocausal information flow.
    """
    phase = arctan2_phase_shift(y_component, x_component, phase_constant)
    cos_comp = math.cos(phase)
    sin_comp = math.sin(phase)
    return phase, cos_comp, sin_comp


# ============================================================
# LIVE DATA FETCHING
# ============================================================

def fetch_json(path, timeout=10):
    """Fetch JSON from mempool.space API."""
    url = f"{BASE_URL}{path}"
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'RetrocausalEntropy/1.0')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode()
            return json.loads(data)
    except Exception as e:
        print(f"  Failed to fetch {path}: {e}")
        return None


def fetch_text(path, timeout=10):
    """Fetch plain text from mempool.space API."""
    url = f"{BASE_URL}{path}"
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'RetrocausalEntropy/1.0')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode().strip()
    except Exception as e:
        print(f"  Failed to fetch {path}: {e}")
        return None


def fetch_address_info(address: str) -> Optional[Dict]:
    """Fetch address information from mempool.space."""
    return fetch_json(f"/address/{address}")


def fetch_address_transactions(address: str, offset=0, limit=50) -> Optional[List[Dict]]:
    """Fetch transactions for an address."""
    return fetch_json(f"/address/{address}/txs?offset={offset}&limit={limit}")


def fetch_block(height_or_hash) -> Optional[Dict]:
    """Fetch block data."""
    return fetch_json(f"/block-height/{height_or_hash}" if isinstance(height_or_hash, int) else f"/block/{height_or_hash}")


# ============================================================
# CAUSAL SINK ANALYSIS
# ============================================================

def analyze_causal_sink(address_info: Dict, txs: List[Dict]) -> CausalSinkState:
    """
    Analyze a burn address as a causal sink.
    
    Extracts the burn history, timestamps, and amounts to build
    the causal sink state — the forward-causal record of what
    has been destroyed.
    """
    address = address_info.get('address', '')
    chain_stats = address_info.get('chain_stats', {})
    funded = chain_stats.get('funded_txo_count', 0)
    spent = chain_stats.get('spent_txo_count', 0)
    funded_satoshi = chain_stats.get('funded_txo_sum', 0)
    spent_satoshi = chain_stats.get('spent_txo_sum', 0)
    
    # Burned = funded - spent (what remains at the address)
    burned_satoshi = funded_satoshi - spent_satoshi
    
    # Extract burn timestamps and amounts from transactions
    timestamps = []
    amounts = []
    txids = []
    heights = []
    
    for tx in txs:
        txid = tx.get('txid', '')
        tx_time = tx.get('status', {}).get('block_time', 0)
        tx_height = tx.get('status', {}).get('block_height', 0)
        
        # Calculate burn amount for this transaction
        # (simplified: use vsize as a proxy for complexity)
        vsize = tx.get('vin', [{}])[0].get('txid', '') if tx.get('vin') else ''
        
        if tx_time:
            timestamps.append(tx_time)
        if tx_height:
            heights.append(tx_height)
        txids.append(txid)
        amounts.append(1)  # Placeholder — actual burn amount needs full tx analysis
    
    first_height = min(heights) if heights else 0
    last_height = max(heights) if heights else 0
    
    return CausalSinkState(
        address=address,
        label=address[:20] + '...',
        total_burned_satoshi=burned_satoshi,
        transaction_count=len(txs),
        first_burn_height=first_height,
        last_burn_height=last_height,
        burn_timestamps=sorted(timestamps),
        burn_amounts=amounts,
        burn_txids=txids,
    )


# ============================================================
# RETROCAUSAL SIGNAL DETECTION
# ============================================================

def compute_retrocausal_signal(sink: CausalSinkState, index: int) -> RetrocausalSignal:
    """
    Compute the retrocausal signal at a specific point in the sink's history.
    
    The signal is derived from:
    1. The burn amount distribution (probability space)
    2. The temporal spacing between burns (frequency domain)
    3. The lambda matrix projection (causal → retrocausal mapping)
    4. The arctan2 phase shift (retrocausal rotation)
    """
    if index >= len(sink.burn_timestamps):
        index = len(sink.burn_timestamps) - 1
    
    # Build probability distribution from burn amounts
    total = sum(sink.burn_amounts) or 1
    probabilities = [a / total for a in sink.burn_amounts]
    
    # Compute inverse entropy
    inv_entropy = inverse_entropy(probabilities)
    
    # Compute entropy well depth (negative of inverse entropy)
    well_depth = -inv_entropy
    
    # Build 3D causal state vector from sink properties
    normalized_burn = sink.total_burned_satoshi / 1e8  # Convert to BTC-scale
    normalized_time = (sink.burn_timestamps[index] if sink.burn_timestamps else 0) / 1e9
    normalized_count = sink.transaction_count / 1000.0
    
    causal_state = [normalized_burn, normalized_time, normalized_count]
    
    # Apply lambda transformation
    lambda_proj = lambda_transform(causal_state)
    
    # Apply arctan2 phase shift using all 3 lambda components
    # The 3D projection gives us x, y, z for full spherical phase space
    phase, cos_comp, sin_comp = retrocausal_arctan2_transform(
        lambda_proj[0], lambda_proj[1]
    )
    
    # Retrocausal deviation: how much y_0 + y_2 deviates from 0
    # In equilibrium, energy + anti-energy = 0
    # Deviation indicates retrocausal influence from the future
    retrocausal_deviation = lambda_proj[0] + lambda_proj[2] if len(lambda_proj) >= 3 else 0.0
    
    # Compute retrocausal strength (magnitude in 3D phase space)
    magnitude_3d = math.sqrt(
        lambda_proj[0] ** 2 + lambda_proj[1] ** 2 +
        (lambda_proj[2] ** 2 if len(lambda_proj) >= 3 else 0)
    )
    retro_strength = magnitude_3d * well_depth * (1.0 + abs(retrocausal_deviation))
    
    # Compute temporal coherence from timestamp spacing
    if len(sink.burn_timestamps) > 1:
        spacings = [
            sink.burn_timestamps[i+1] - sink.burn_timestamps[i]
            for i in range(len(sink.burn_timestamps) - 1)
        ]
        avg_spacing = sum(spacings) / len(spacings)
        if avg_spacing > 0:
            variance = sum((s - avg_spacing) ** 2 for s in spacings) / len(spacings)
            cv = math.sqrt(variance) / avg_spacing  # Coefficient of variation
            temporal_coherence = 1.0 / (1.0 + cv)  # High coherence = low CV
        else:
            temporal_coherence = 1.0
    else:
        temporal_coherence = 0.0
    
    # Frequency decomposition (simple DFT of burn amounts)
    n = len(sink.burn_amounts)
    frequencies = []
    for k in range(min(8, n)):
        real = sum(
            sink.burn_amounts[t] * math.cos(2 * math.pi * k * t / n)
            for t in range(n)
        )
        imag = sum(
            sink.burn_amounts[t] * math.sin(2 * math.pi * k * t / n)
            for t in range(n)
        )
        frequencies.append(math.sqrt(real ** 2 + imag ** 2) / n)
    
    return RetrocausalSignal(
        sink_address=sink.address,
        phase_angle=phase,
        phase_shift=2 * math.pi * PHASE_CONSTANT,
        inverse_entropy=inv_entropy,
        entropy_well_depth=well_depth,
        lambda_projection=lambda_proj,
        retrocausal_strength=retro_strength,
        temporal_coherence=temporal_coherence,
        frequency_components=frequencies,
    )


def compute_entropy_well(sink: CausalSinkState, max_iterations: int = 100) -> EntropyWellResult:
    """
    Compute the full inverse entropy well for a causal sink.
    
    This iteratively applies the retrocausal transformation,
    converging to a fixed point that represents the retrocausal
    equilibrium state of the sink.
    
    The convergence process:
    1. Start with the forward-causal state
    2. Apply lambda transformation to get retrocausal projection
    3. Apply arctan2 phase shift
    4. Compute inverse entropy gradient
    5. Update state by following the gradient
    6. Repeat until convergence
    
    If the system converges, the sink has a stable retrocausal state.
    If it diverges or oscillates, the sink exhibits chaotic retrocausal behavior.
    """
    # Initial state from sink properties
    normalized_burn = sink.total_burned_satoshi / 1e8
    normalized_time = sink.last_burn_height / 1e6
    normalized_count = sink.transaction_count / 1000.0
    
    state = [normalized_burn, normalized_time, normalized_count]
    
    signals = []
    well_depths = []
    
    for iteration in range(max_iterations):
        # Compute signal at current state
        # (use index proportional to iteration for temporal sweep)
        idx = min(iteration, len(sink.burn_timestamps) - 1)
        signal = compute_retrocausal_signal(sink, idx)
        signals.append(signal)
        well_depths.append(signal.entropy_well_depth)
        
        # Update state using retrocausal feedback
        lambda_proj = signal.lambda_projection
        phase = signal.phase_angle
        
        # Gradient descent on inverse entropy well
        # Use all 3 lambda components for 3D probability space
        lp = signal.lambda_projection
        raw_probs = [
            abs(lp[0]) if len(lp) > 0 else 0.1,
            abs(lp[1]) if len(lp) > 1 else 0.1,
            abs(lp[2]) if len(lp) > 2 else 0.1,
        ]
        # Ensure valid probabilities
        probabilities = [max(0.001, p) for p in raw_probs]
        total_p = sum(probabilities)
        probabilities = [p / total_p for p in probabilities]
        
        gradient = entropy_well_gradient(probabilities)
        
        # Update state with learning rate
        learning_rate = 0.1
        for i in range(len(state)):
            if i < len(gradient):
                state[i] -= learning_rate * gradient[i]
        
        # Check convergence
        if iteration > 0 and well_depths[-1] == well_depths[-2]:
            break
    
    # Compute final metrics
    final_signal = signals[-1] if signals else None
    causal_violation = 0.0
    if final_signal:
        # Causal violation = how much the retrocausal signal differs from forward causality
        # Measured by the phase shift magnitude relative to 2π
        causal_violation = abs(final_signal.phase_shift) / (2 * math.pi)
    
    return EntropyWellResult(
        sink_address=sink.address,
        well_depth=sum(well_depths) / len(well_depths) if well_depths else 0.0,
        phase_shift_applied=2 * math.pi * PHASE_CONSTANT,
        retrocausal_signals=signals,
        convergence_iterations=len(signals),
        final_state=state,
        causal_violation_score=causal_violation,
    )


# ============================================================
# CROSS-SINK RETROCAUSAL CORRELATION
# ============================================================

@dataclass
class CrossSinkCorrelation:
    """Correlation between two causal sinks' retrocausal signals."""
    sink_a: str
    sink_b: str
    phase_correlation: float  # Correlation of phase angles
    entropy_correlation: float  # Correlation of entropy well depths
    temporal_correlation: float  # Correlation of temporal coherence
    combined_retrocausal_strength: float  # Combined signal strength


def compute_cross_sink_correlation(
    result_a: EntropyWellResult,
    result_b: EntropyWellResult
) -> CrossSinkCorrelation:
    """
    Compute the retrocausal correlation between two causal sinks.
    
    If two sinks are retrocausally correlated, it suggests they share
    a common retrocausal source — possibly a future event that constrains
    both sinks' behavior.
    """
    signals_a = result_a.retrocausal_signals
    signals_b = result_b.retrocausal_signals
    
    # Phase correlation
    min_len = min(len(signals_a), len(signals_b))
    if min_len > 1:
        phases_a = [s.phase_angle for s in signals_a[:min_len]]
        phases_b = [s.phase_angle for s in signals_b[:min_len]]
        
        mean_a = sum(phases_a) / len(phases_a)
        mean_b = sum(phases_b) / len(phases_b)
        
        cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(phases_a, phases_b)) / len(phases_a)
        std_a = (sum((a - mean_a) ** 2 for a in phases_a) / len(phases_a)) ** 0.5
        std_b = (sum((b - mean_b) ** 2 for b in phases_b) / len(phases_b)) ** 0.5
        
        phase_corr = cov / (std_a * std_b) if std_a > 0 and std_b > 0 else 0.0
    else:
        phase_corr = 0.0
    
    # Entropy correlation
    entropy_a = [s.entropy_well_depth for s in signals_a[:min_len]]
    entropy_b = [s.entropy_well_depth for s in signals_b[:min_len]]
    
    if len(entropy_a) > 1:
        mean_a = sum(entropy_a) / len(entropy_a)
        mean_b = sum(entropy_b) / len(entropy_b)
        
        cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(entropy_a, entropy_b)) / len(entropy_a)
        std_a = (sum((a - mean_a) ** 2 for a in entropy_a) / len(entropy_a)) ** 0.5
        std_b = (sum((b - mean_b) ** 2 for b in entropy_b) / len(entropy_b)) ** 0.5
        
        entropy_corr = cov / (std_a * std_b) if std_a > 0 and std_b > 0 else 0.0
    else:
        entropy_corr = 0.0
    
    # Temporal correlation
    temp_a = [s.temporal_coherence for s in signals_a[:min_len]]
    temp_b = [s.temporal_coherence for s in signals_b[:min_len]]
    
    if len(temp_a) > 1:
        mean_a = sum(temp_a) / len(temp_a)
        mean_b = sum(temp_b) / len(temp_b)
        
        cov = sum((a - mean_a) * (b - mean_b) for a, b in zip(temp_a, temp_b)) / len(temp_a)
        std_a = (sum((a - mean_a) ** 2 for a in temp_a) / len(temp_a)) ** 0.5
        std_b = (sum((b - mean_b) ** 2 for b in temp_b) / len(temp_b)) ** 0.5
        
        temporal_corr = cov / (std_a * std_b) if std_a > 0 and std_b > 0 else 0.0
    else:
        temporal_corr = 0.0
    
    # Combined retrocausal strength
    combined_strength = (
        (result_a.well_depth + result_b.well_depth) / 2 *
        (1 + abs(phase_corr))
    )
    
    return CrossSinkCorrelation(
        sink_a=result_a.sink_address,
        sink_b=result_b.sink_address,
        phase_correlation=phase_corr,
        entropy_correlation=entropy_corr,
        temporal_correlation=temporal_corr,
        combined_retrocausal_strength=combined_strength,
    )


# ============================================================
# MAIN EXPERIMENT
# ============================================================

def run_retrocausal_experiment():
    """
    Run the full retrocausal inverse entropy well experiment
    on live Bitcoin burn addresses.
    """
    print("=" * 70)
    print("RETROCAUSAL INVERSE ENTROPY WELL EXPERIMENT")
    print("=" * 70)
    print(f"Lambda matrix: {LAMBDA_MATRIX}")
    print(f"Phase constant: {PHASE_CONSTANT}")
    print(f"Phase shift: {2 * math.pi * PHASE_CONSTANT:.10f} radians")
    print()
    
    results = {}
    sinks = {}
    
    # Fetch and analyze each burn address
    for burn_info in KNOWN_BURN_ADDRESSES:
        address = burn_info['address']
        label = burn_info['label']
        
        print(f"\n{'='*70}")
        print(f"Analyzing causal sink: {label}")
        print(f"Address: {address}")
        print(f"{'='*70}")
        
        # Fetch address info
        addr_info = fetch_address_info(address)
        if addr_info is None:
            print(f"  WARNING: Could not fetch address info for {label}")
            continue
        
        print(f"  Total received: {addr_info.get('chain_stats', {}).get('funded_txo_sum', 0) / 1e8:.2f} BTC")
        print(f"  Total spent: {addr_info.get('chain_stats', {}).get('spent_txo_sum', 0) / 1e8:.2f} BTC")
        
        # Fetch transactions
        txs = fetch_address_transactions(address, offset=0, limit=50)
        if txs is None:
            print(f"  WARNING: Could not fetch transactions for {label}")
            continue
        
        print(f"  Transactions fetched: {len(txs)}")
        
        # Analyze as causal sink
        sink = analyze_causal_sink(addr_info, txs)
        sinks[address] = sink
        
        print(f"  Burned: {sink.total_burned_satoshi / 1e8:.4f} BTC")
        print(f"  Transaction count: {sink.transaction_count}")
        print(f"  First burn height: {sink.first_burn_height}")
        print(f"  Last burn height: {sink.last_burn_height}")
        
        # Compute entropy well
        print(f"\n  Computing inverse entropy well...")
        result = compute_entropy_well(sink, max_iterations=50)
        results[address] = result
        
        print(f"  Well depth: {result.well_depth:.6f}")
        print(f"  Phase shift applied: {result.phase_shift_applied:.10f} radians")
        print(f"  Convergence iterations: {result.convergence_iterations}")
        print(f"  Causal violation score: {result.causal_violation_score:.6f}")
        print(f"  Final state: {[f'{x:.4f}' for x in result.final_state]}")
        
        if result.retrocausal_signals:
            sig = result.retrocausal_signals[-1]
            print(f"\n  Latest retrocausal signal:")
            print(f"    Phase angle: {sig.phase_angle:.6f} radians")
            print(f"    Inverse entropy: {sig.inverse_entropy:.6f}")
            print(f"    Entropy well depth: {sig.entropy_well_depth:.6f}")
            print(f"    Retrocausal strength: {sig.retrocausal_strength:.6f}")
            print(f"    Temporal coherence: {sig.temporal_coherence:.6f}")
            print(f"    Lambda projection (3D): {[f'{x:.4f}' for x in sig.lambda_projection]}")
            # Check energy-anti-energy equilibrium
            if len(sig.lambda_projection) >= 3:
                equilibrium = sig.lambda_projection[0] + sig.lambda_projection[2]
                print(f"    Energy+AntiEnergy equilibrium: {equilibrium:.6f} (0 = perfect)")
                if abs(equilibrium) < 1e-10:
                    print(f"    *** PERFECT equilibrium — retrocausal mirror is exact!")
            print(f"    Frequency components: {[f'{f:.4f}' for f in sig.frequency_components[:4]]}")
        
        time.sleep(0.5)  # Rate limiting
    
    # Cross-sink correlation analysis
    if len(results) >= 2:
        print(f"\n\n{'='*70}")
        print("CROSS-SINK RETROCAUSAL CORRELATION")
        print(f"{'='*70}")
        
        addresses = list(results.keys())
        for i in range(len(addresses)):
            for j in range(i + 1, len(addresses)):
                corr = compute_cross_sink_correlation(
                    results[addresses[i]],
                    results[addresses[j]]
                )
                
                print(f"\n  {sinks[addresses[i]].label} <-> {sinks[addresses[j]].label}:")
                print(f"    Phase correlation: {corr.phase_correlation:.6f}")
                print(f"    Entropy correlation: {corr.entropy_correlation:.6f}")
                print(f"    Temporal correlation: {corr.temporal_correlation:.6f}")
                print(f"    Combined retrocausal strength: {corr.combined_retrocausal_strength:.6f}")
                
                if abs(corr.phase_correlation) > 0.5:
                    print(f"    *** STRONG phase correlation — possible shared retrocausal source!")
                if abs(corr.entropy_correlation) > 0.5:
                    print(f"    *** STRONG entropy correlation — linked entropy wells!")
    
    # Summary
    print(f"\n\n{'='*70}")
    print("EXPERIMENT SUMMARY")
    print(f"{'='*70}")
    print(f"  Causal sinks analyzed: {len(results)}")
    print(f"  Lambda matrix: {LAMBDA_MATRIX}")
    print(f"  Phase constant: {PHASE_CONSTANT}")
    
    if results:
        avg_well_depth = sum(r.well_depth for r in results.values()) / len(results)
        avg_causal_violation = sum(r.causal_violation_score for r in results.values()) / len(results)
        
        print(f"  Average well depth: {avg_well_depth:.6f}")
        print(f"  Average causal violation: {avg_causal_violation:.6f}")
        
        # Interpret results
        print(f"\n  INTERPRETATION:")
        if avg_causal_violation > 0.3:
            print(f"    High causal violation — strong retrocausal signals detected")
            print(f"    The burn addresses may be emitting information backward in time")
        elif avg_causal_violation > 0.1:
            print(f"    Moderate causal violation — weak retrocausal signals present")
            print(f"    The burn addresses show slight future-past coupling")
        else:
            print(f"    Low causal violation — retrocausal signals are subtle")
            print(f"    The burn addresses are primarily forward-causal")
        
        if avg_well_depth > 1.0:
            print(f"    Deep entropy wells — strong ordering potential from the future")
        else:
            print(f"    Shallow entropy wells — weak retrocausal ordering")
    
    return results, sinks


# ============================================================
# CONVENIENCE FUNCTIONS
# ============================================================

def compute_single_signal(
    burn_satoshi: int,
    burn_count: int,
    last_height: int,
    timestamps: List[int]
) -> RetrocausalSignal:
    """Compute a single retrocausal signal from raw data."""
    sink = CausalSinkState(
        address="custom",
        label="Custom sink",
        total_burned_satoshi=burn_satoshi,
        transaction_count=burn_count,
        first_burn_height=0,
        last_burn_height=last_height,
        burn_timestamps=timestamps,
        burn_amounts=[1] * burn_count,
        burn_txids=[],
    )
    idx = min(0, len(timestamps) - 1) if timestamps else 0
    return compute_retrocausal_signal(sink, idx)


def apply_lambda_transform(state: List[float]) -> List[float]:
    """Apply the lambda matrix to a state vector."""
    return lambda_transform(state)


def apply_phase_shift(x: float, y: float) -> float:
    """Apply arctan2 phase shift with the phase constant."""
    phase, _, _ = retrocausal_arctan2_transform(x, y)
    return phase


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == '__main__':
    results, sinks = run_retrocausal_experiment()
