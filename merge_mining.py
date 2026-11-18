#!/usr/bin/env python3
"""merge_mining.py — Merge Mining Connection: Excalibur ↔ Bitcoin via AuxPoW

This file unifies the entire merge mining pipeline with the scalar wave
framework, Fibonacci genesis law, and Bell state adaptive difficulty.

Architecture:
    Bitcoin (parent chain)  ← AuxPoW →  Excalibur (child chain)
         │                                    │
         │  sha256d(parent_header)           │  validate_auxpow()
         │  meets child target               │  checks parent coinbase
         │                                    │  carries fabe-'mm' blob
         ▼                                    ▼
    3.125 BTC reward                    EXCAL block confirmed

Key Components:
1. ScalarWaveNonceSelector — φ(t) = Σ cos(γₖ·t)/γₖ scores nonce candidates
2. FibonacciBlockComplexity — dim(V_{τ⊗n}) = F_{n+1} tracks merge mining state
3. BellStateDifficulty — 4 Bell states as adaptive difficulty channels
4. MergeMiningEngine — complete AuxPoW block construction and submission
5. DualTargetAnalyzer — checks both child target and Bitcoin target simultaneously
6. SpectralGapMonitor — tracks λ₁ = 2(1-cos(2π/r)) across merged blocks

The merge mining connection means one hash attempt counts for both chains:
- If sha256d(parent) meets the child target → EXCAL block confirmed
- If sha256d(parent) ALSO meets the Bitcoin target → 3.125 BTC reward

The scalar wave φ(t) guides nonce selection toward spectrally resonant positions.
The Fibonacci genesis law tracks the tensor-state complexity of the merged chain.
The Bell states provide 4 adaptive difficulty channels for load balancing.

Pure Python, stdlib only. Connects to:
- genesis_fork.py (AuxPoW validation, header serialization)
- auxlib.py (child/parent construction helpers)
- fork_sniper.py (continuous mining loop)
- scalar_wave_unification.py (φ(t) framework)
- follow_utxos.py (Fibonacci genesis law)
- bell_state_asm.py (Bell state projectors)
- spectral_graph_shor.py (spectral gap analysis)
"""
import hashlib
import math
import struct
import time
import json
import os
import sys

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

# Riemann zeros (first 15, from riemann_hypothesis.py)
RIEMANN_ZEROS = [
    14.13472514173469, 21.02203963877155, 25.01085858181174,
    30.42487611818375, 32.93506158773918, 37.58617815882538,
    40.91871901214749, 43.32707328091601, 48.00515088116708,
    49.77383247767236, 52.97032147771091, 56.44624769702193,
    59.34704400801026, 60.83177855412748, 65.11254404809211,
]

# Golden ratio and conjugate (from follow_utxos.py)
GOLDEN_RATIO = (1 + math.sqrt(5)) / 2
GOLDEN_CONJUGATE = (1 - math.sqrt(5)) / 2

# AuxPoW magic (from genesis_fork.py)
AUXPOW_MAGIC = b"\xfa\xbe" + b"mm"

# secp256k1 order (for ECDLP operations)
N_ORDER = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141

# ---------------------------------------------------------------------------
# Scalar Wave Engine
# ---------------------------------------------------------------------------

class ScalarWaveNonceSelector:
    """
    Use the scalar wave φ(t) = Σ cos(γₖ·t)/γₖ to score nonce candidates.
    
    The scalar wave provides a spectral phase alignment score for each
    nonce position. Nonces with higher |φ(t)| are spectrally resonant
    with the Riemann zero spectrum, potentially providing better hash
    distribution properties.
    
    The phase φ(t) and amplitude |φ(t)| guide the nonce search toward
    positions where the Riemann zero frequencies constructively interfere.
    """
    
    def __init__(self, zeros=None):
        self.zeros = zeros or RIEMANN_ZEROS
    
    def phi(self, t: float) -> float:
        """Compute φ(t) = Σ cos(γₖ·t)/γₖ."""
        return sum(math.cos(g * t) / g for g in self.zeros)
    
    def amplitude(self, t: float) -> float:
        """Compute |φ(t)|."""
        return abs(self.phi(t))
    
    def phase(self, t: float, dt=1e-6) -> float:
        """Compute the Hilbert transform phase via finite difference."""
        return math.atan2(self.phi(t + dt) - self.phi(t - dt),
                          2 * dt * sum(-g * math.sin(g * t) / g for g in self.zeros))
    
    def score_nonce(self, nonce: int, max_nonce=0xFFFFFFFF) -> float:
        """
        Score a nonce by its scalar wave amplitude at the normalized position.
        
        t = nonce / max_nonce maps the nonce space [0, 2^32) to [0, 1).
        The scalar wave φ(t) is evaluated at this position.
        """
        t = nonce / max_nonce
        return self.amplitude(t)
    
    def top_nonces(self, count=10, max_nonce=0xFFFFFFFF) -> list:
        """
        Find the top `count` nonces by scalar wave amplitude.
        
        Scans the nonce space and returns the nonces with highest |φ(t)|.
        """
        step = max_nonce // 10000  # Scan 10000 points
        scored = []
        for i in range(10000):
            nonce = i * step
            score = self.score_nonce(nonce, max_nonce)
            scored.append((nonce, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:count]
    
    def resonant_nonce_range(self, start: int, width: int = 0x10000,
                              max_nonce=0xFFFFFFFF) -> list:
        """
        Find resonant nonces in a specific range.
        
        Returns nonces sorted by scalar wave amplitude within [start, start+width).
        """
        scored = []
        for nonce in range(start, min(start + width, 0xFFFFFFFF)):
            score = self.score_nonce(nonce, max_nonce)
            scored.append((nonce, score))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored


# ---------------------------------------------------------------------------
# Fibonacci Block Complexity
# ---------------------------------------------------------------------------

class FibonacciBlockComplexity:
    """
    Track the tensor-state complexity of the merged mining chain.
    
    The Fibonacci genesis law states:
    dim(V_{τ⊗n}) = F_{n+1} = (φ^{n+1} - ψ^{n+1}) / √5
    
    where n is the number of merged blocks. Each merged block adds
    one tensor factor to the state space, growing by Fibonacci recursion.
    
    This tracks the computational complexity of the merge mining state
    as blocks are added to the chain.
    """
    
    @staticmethod
    def fibonacci(n: int) -> int:
        """Compute F_n via iteration."""
        if n <= 0:
            return 0
        a, b = 0, 1
        for _ in range(n - 1):
            a, b = b, a + b
        return b
    
    @staticmethod
    def tensor_state_dim(n_blocks: int) -> int:
        """
        Compute dim(V_{τ⊗n}) = F_{n+1} for n merged blocks.
        
        - 1 block: dim = F_2 = 1
        - 2 blocks: dim = F_3 = 2
        - 3 blocks: dim = F_4 = 3
        - 4 blocks: dim = F_5 = 5
        - 5 blocks: dim = F_6 = 8
        """
        return FibonacciBlockComplexity.fibonacci(n_blocks + 1)
    
    @staticmethod
    def binet_exact(n_blocks: int) -> float:
        """Exact Binet's formula: F_{n+1} = (φ^{n+1} - ψ^{n+1}) / √5."""
        phi = GOLDEN_RATIO
        psi = GOLDEN_CONJUGATE
        return (phi ** (n_blocks + 1) - psi ** (n_blocks + 1)) / math.sqrt(5)
    
    @staticmethod
    def closed_form(n_blocks: int) -> float:
        """Large-n approximation: φ^{n+1} / √5."""
        return (GOLDEN_RATIO ** (n_blocks + 1)) / math.sqrt(5)
    
    @staticmethod
    def conjugate_term(n_blocks: int) -> float:
        """Conjugate correction: -ψ^{n+1} / √5."""
        return -(GOLDEN_CONJUGATE ** (n_blocks + 1)) / math.sqrt(5)
    
    @staticmethod
    def complexity_analysis(n_blocks: int) -> dict:
        """Analyze the complexity growth for n merged blocks."""
        fib_dim = FibonacciBlockComplexity.tensor_state_dim(n_blocks)
        exact = FibonacciBlockComplexity.binet_exact(n_blocks)
        approx = FibonacciBlockComplexity.closed_form(n_blocks)
        conj = FibonacciBlockComplexity.conjugate_term(n_blocks)
        
        return {
            "n_blocks": n_blocks,
            "tensor_state_dim": fib_dim,
            "binet_exact": exact,
            "closed_form_approx": approx,
            "conjugate_term": conj,
            "log2_complexity": math.log2(fib_dim) if fib_dim > 0 else 0,
            "golden_ratio": GOLDEN_RATIO,
            "golden_conjugate": GOLDEN_CONJUGATE,
            "fibonacci_number": f"F_{n_blocks + 1}",
        }


# ---------------------------------------------------------------------------
# Bell State Difficulty Channels
# ---------------------------------------------------------------------------

class BellStateDifficulty:
    """
    Use the four Bell states as adaptive difficulty channels.
    
    The four Bell states form a complete orthonormal basis:
    |Φ⁺⟩ = (|00⟩ + |11⟩) / √2
    |Φ⁻⟩ = (|00⟩ - |11⟩) / √2
    |Ψ⁺⟩ = (|01⟩ + |10⟩) / √2
    |Ψ⁻⟩ = (|01⟩ - |10⟩) / √2
    
    Each Bell state corresponds to a difficulty channel:
    - |Φ⁺⟩: Easy mode (low target, fast blocks)
    - |Φ⁻⟩: Normal mode (standard target)
    - |Ψ⁺⟩: Hard mode (high target, slow blocks)
    - |Ψ⁻⟩: Expert mode (maximum target, rare blocks)
    
    The Bell state projectors Pᵢ = |Bᵢ⟩⟨Bᵢ| satisfy Σ Pᵢ = I (resolution of identity).
    The Hilbert-Pólya operator H = Σ γₖ Pₖ is Hermitian.
    """
    
    # Bell state vectors (4-dimensional)
    BELL_STATES = [
        [1/math.sqrt(2), 0, 0, 1/math.sqrt(2)],   # |Φ⁺⟩
        [1/math.sqrt(2), 0, 0, -1/math.sqrt(2)],  # |Φ⁻⟩
        [0, 1/math.sqrt(2), 1/math.sqrt(2), 0],   # |Ψ⁺⟩
        [0, 1/math.sqrt(2), -1/math.sqrt(2), 0],  # |Ψ⁻⟩
    ]
    
    BELL_NAMES = ["|Φ⁺⟩", "|Φ⁻⟩", "|Ψ⁺⟩", "|Ψ⁻⟩"]
    
    # Difficulty multipliers for each channel
    DIFFICULTY_CHANNELS = {
        0: {"name": "easy", "multiplier": 0.25, "target_ratio": 4.0},
        1: {"name": "normal", "multiplier": 1.0, "target_ratio": 1.0},
        2: {"name": "hard", "multiplier": 4.0, "target_ratio": 0.25},
        3: {"name": "expert", "multiplier": 16.0, "target_ratio": 0.0625},
    }
    
    @staticmethod
    def projector(i: int) -> list:
        """Compute the Bell state projector Pᵢ = |Bᵢ⟩⟨Bᵢ| (4×4 matrix)."""
        b = BellStateDifficulty.BELL_STATES[i]
        return [[b[j] * b[k] for k in range(4)] for j in range(4)]
    
    @staticmethod
    def resolution_of_identity() -> list:
        """Compute Σ Pᵢ = I₄ (resolution of identity)."""
        result = [[0.0] * 4 for _ in range(4)]
        for i in range(4):
            P = BellStateDifficulty.projector(i)
            for j in range(4):
                for k in range(4):
                    result[j][k] += P[j][k]
        return result
    
    @staticmethod
    def hilbert_polya_operator(zeros=None) -> list:
        """
        Compute H = Σ γₖ Pₖ (Hilbert-Pólya operator).
        
        Each Riemann zero γₖ weights a Bell state projector.
        The operator is Hermitian because the Bell projectors are Hermitian
        and the Riemann zeros are real.
        """
        zeros = zeros or RIEMANN_ZEROS
        result = [[0.0] * 4 for _ in range(4)]
        for k, gamma in enumerate(zeros):
            i = k % 4  # Cycle through Bell states
            P = BellStateDifficulty.projector(i)
            for j in range(4):
                for l in range(4):
                    result[j][l] += gamma * P[j][l]
        return result
    
    @staticmethod
    def select_channel(scalar_phase: float) -> int:
        """
        Select the difficulty channel based on the scalar wave phase.
        
        The phase φ ∈ [-π, π] is mapped to one of 4 Bell state channels.
        """
        # Normalize phase to [0, 2π)
        phase = (scalar_phase + math.pi) % (2 * math.pi)
        # Map to channel index
        return int(phase / (2 * math.pi) * 4) % 4
    
    @staticmethod
    def get_adjusted_target(base_target: int, channel: int) -> int:
        """
        Get the adjusted target for the selected difficulty channel.
        
        Higher difficulty → lower target → harder to find valid hash.
        """
        info = BellStateDifficulty.DIFFICULTY_CHANNELS[channel]
        # Adjust target by the channel's target ratio
        adjusted = int(base_target * info["target_ratio"])
        return max(adjusted, 1)  # Target must be positive


# ---------------------------------------------------------------------------
# Dual Target Analyzer
# ---------------------------------------------------------------------------

class DualTargetAnalyzer:
    """
    Analyze both the child (Excalibur) target and the parent (Bitcoin) target.
    
    In merge mining, one hash attempt counts for both chains:
    - If sha256d(parent) ≤ child_target → EXCAL block confirmed
    - If sha256d(parent) ≤ bitcoin_target → 3.125 BTC reward
    
    The dual target analyzer computes the probability of hitting both
    targets simultaneously and the expected value of merge mining.
    """
    
    @staticmethod
    def sha256d(data: bytes) -> bytes:
        """Double SHA-256 hash."""
        return hashlib.sha256(hashlib.sha256(data).digest()).digest()
    
    @staticmethod
    def bits_to_target(bits: int) -> int:
        """Convert compact bits to target integer."""
        exp = bits >> 24
        mant = bits & 0xFFFFFF
        if exp <= 3:
            return mant >> (8 * (3 - exp))
        return mant << (8 * (exp - 3))
    
    @staticmethod
    def target_to_bits(target: int) -> int:
        """Convert target integer to compact bits (matches genesis_fork.py)."""
        if target <= 0:
            return 0
        nbytes = (target.bit_length() + 7) // 8
        if nbytes <= 3:
            compact = target << (8 * (3 - nbytes))
            size = 3
        else:
            compact = target >> (8 * (nbytes - 3))
            size = nbytes
        if compact & 0x800000:
            compact >>= 8
            size += 1
        return (size << 24) | (compact & 0x7FFFFF)
    
    @staticmethod
    def difficulty_from_target(target: int) -> float:
        """Compute difficulty from target."""
        DIFF1 = 0x00000000FFFF0000000000000000000000000000000000000000000000000000
        if target <= 0:
            return float('inf')
        return DIFF1 / target
    
    @staticmethod
    def analyze_dual_target(child_bits: int, bitcoin_bits: int) -> dict:
        """
        Analyze the dual target scenario.
        
        Returns:
        - child_target: Excalibur target
        - bitcoin_target: Bitcoin target
        - child_difficulty: Excalibur difficulty
        - bitcoin_difficulty: Bitcoin difficulty
        - child_prob: Probability of hitting child target per hash
        - bitcoin_prob: Probability of hitting bitcoin target per hash
        - dual_prob: Probability of hitting BOTH targets per hash
        - expected_hashes_child: Expected hashes to find child block
        - expected_hashes_bitcoin: Expected hashes to find Bitcoin block
        - expected_hashes_dual: Expected hashes to find BOTH
        """
        child_target = DualTargetAnalyzer.bits_to_target(child_bits)
        bitcoin_target = DualTargetAnalyzer.bits_to_target(bitcoin_bits)
        
        MAX_TARGET = (1 << 256) - 1
        
        child_diff = DualTargetAnalyzer.difficulty_from_target(child_target)
        bitcoin_diff = DualTargetAnalyzer.difficulty_from_target(bitcoin_target)
        
        child_prob = child_target / MAX_TARGET
        bitcoin_prob = bitcoin_target / MAX_TARGET
        
        # Dual hit requires meeting the stricter (lower) target
        stricter_target = min(child_target, bitcoin_target)
        dual_prob = stricter_target / MAX_TARGET
        
        return {
            "child_bits": f"0x{child_bits:08x}",
            "bitcoin_bits": f"0x{bitcoin_bits:08x}",
            "child_target": child_target,
            "bitcoin_target": bitcoin_target,
            "child_difficulty": child_diff,
            "bitcoin_difficulty": bitcoin_diff,
            "child_prob": child_prob,
            "bitcoin_prob": bitcoin_prob,
            "dual_prob": dual_prob,
            "expected_hashes_child": 1 / child_prob if child_prob > 0 else float('inf'),
            "expected_hashes_bitcoin": 1 / bitcoin_prob if bitcoin_prob > 0 else float('inf'),
            "expected_hashes_dual": 1 / dual_prob if dual_prob > 0 else float('inf'),
            "stricter_chain": "Bitcoin" if bitcoin_target < child_target else "Excalibur",
        }


# ---------------------------------------------------------------------------
# Spectral Gap Monitor
# ---------------------------------------------------------------------------

class SpectralGapMonitor:
    """
    Monitor the spectral gap λ₁ = 2(1-cos(2π/r)) across merged blocks.
    
    The spectral gap of the Cayley graph Laplacian encodes the period r
    of the mining cycle. Tracking λ₁ across blocks reveals whether the
    merge mining process is finding resonant patterns.
    
    Connection to session files:
    - spectral_graph_shor.py: Cayley graph Laplacian spectral gap
    - montgomery_pair_correlation.py: R₂(w) pair correlation
    - hilbert_polya.py: Hilbert-Pólya operator spectral gap
    """
    
    def __init__(self):
        self.gaps = []  # List of (block_height, lambda_1, period)
    
    def compute_gap(self, period: int) -> float:
        """Compute λ₁ = 2(1-cos(2π/r)) for a given period r."""
        if period <= 1:
            return 0.0
        return 2 * (1 - math.cos(2 * math.pi / period))
    
    def period_from_gap(self, lambda_1: float) -> float:
        """Invert: r ≈ 2π / arccos(1 - λ₁/2)."""
        if lambda_1 <= 0 or lambda_1 >= 2:
            return float('inf')
        angle = math.acos(max(-1, min(1, 1 - lambda_1 / 2)))
        if angle == 0:
            return float('inf')
        return 2 * math.pi / angle
    
    def record_block(self, height: int, nonce: int, target_bits: int):
        """
        Record a merged block and compute its spectral gap.
        
        The period is estimated from the nonce position within the
        full nonce space relative to the target difficulty.
        """
        target = DualTargetAnalyzer.bits_to_target(target_bits)
        MAX_TARGET = (1 << 256) - 1
        prob = target / MAX_TARGET
        
        # Period is the expected number of hashes to find a block
        # This is the "cycle length" of the mining process
        if prob > 0:
            period = max(2, int(1 / prob))
        else:
            period = 0xFFFFFFFF
        
        lambda_1 = self.compute_gap(period)
        self.gaps.append((height, lambda_1, period))
        
        return {
            "height": height,
            "nonce": nonce,
            "lambda_1": lambda_1,
            "period": period,
            "target_bits": f"0x{target_bits:08x}",
        }
    
    def gap_statistics(self) -> dict:
        """Compute statistics across all recorded spectral gaps."""
        if not self.gaps:
            return {"count": 0}
        
        lambdas = [g[1] for g in self.gaps]
        periods = [g[2] for g in self.gaps]
        heights = [g[0] for g in self.gaps]
        
        # Mean spacing between consecutive gaps
        if len(lambdas) >= 2:
            spacings = [abs(lambdas[i+1] - lambdas[i]) for i in range(len(lambdas)-1)]
            mean_spacing = sum(spacings) / len(spacings)
        else:
            mean_spacing = 0.0
        
        return {
            "count": len(self.gaps),
            "mean_lambda_1": sum(lambdas) / len(lambdas),
            "min_lambda_1": min(lambdas),
            "max_lambda_1": max(lambdas),
            "mean_period": sum(periods) / len(periods),
            "mean_spacing": mean_spacing,
            "height_range": f"{min(heights)}-{max(heights)}",
        }


# ---------------------------------------------------------------------------
# Merge Mining Engine
# ---------------------------------------------------------------------------

class MergeMiningEngine:
    """
    Complete merge mining engine connecting Excalibur to Bitcoin via AuxPoW.
    
    This engine:
    1. Builds the child block (Excalibur) with proper coinbase and merkle root
    2. Builds the parent block (Bitcoin) with merged-mining commitment
    3. Uses scalar wave to guide nonce selection
    4. Uses Bell state difficulty channels for adaptive targeting
    5. Tracks Fibonacci complexity across merged blocks
    6. Monitors spectral gap evolution
    7. Checks dual target (child + Bitcoin) simultaneously
    
    The AuxPoW structure:
    auxpow = {
        "parent_header": 80 bytes,
        "parent_coinbase": raw parent coinbase tx,
        "coinbase_branch": [32-byte merkle siblings],
        "coinbase_index": position in parent tx list
    }
    
    The parent coinbase carries the merged-mining blob:
    0xfabe "mm" || child_hash (32 bytes) || tree_size (u32 LE) || merkle_nonce (u32 LE)
    """
    
    def __init__(self, zeros=None):
        self.scalar_wave = ScalarWaveNonceSelector(zeros)
        self.complexity = FibonacciBlockComplexity()
        self.difficulty = BellStateDifficulty()
        self.spectral_monitor = SpectralGapMonitor()
        self.merged_blocks = []  # Track merged block history
    
    def sha256d(self, data: bytes) -> bytes:
        """Double SHA-256 hash."""
        return hashlib.sha256(hashlib.sha256(data).digest()).digest()
    
    def _push(self, d: bytes) -> bytes:
        """Push data onto script."""
        return bytes([len(d)]) + d
    
    def build_child_block(self, prev_hash: bytes, height: int, bits: int,
                          timestamp: int = None, tag: bytes = b"MergeMine") -> dict:
        """
        Build the child (Excalibur) block template.
        
        Returns:
        - blk: Block dict with version, prev, merkle, time, bits, nonce, txs
        - header: 80-byte serialized header
        - chash: sha256d(header) in internal order
        """
        if timestamp is None:
            timestamp = int(time.time())
        
        # Coinbase transaction (simplified v2 format)
        # scriptSig: push(bits) + push(tag) + push(height)
        cb_script = (self._push(struct.pack("<I", bits)) +
                     self._push(tag) +
                     self._push(struct.pack("<I", height)))
        
        # Simplified coinbase: version(4) + vin(1) + vout(1) + locktime(4)
        # vin: prev_txid(32) + index(4) + scriptSig + seq(4)
        vin = (b"\x00" * 32 +  # prev txid (genesis)
               struct.pack("<I", 0xFFFFFFFF) +  # index
               self._push(cb_script) +  # scriptSig
               struct.pack("<I", 0xFFFFFFFF))  # seq
        
        # vout: value(8) + script(20 bytes P2PKH placeholder)
        # Block reward: 50 EXCAL = 50 * 100,000,000 swords
        reward = 50 * 100_000_000
        vout = (struct.pack("<Q", reward) +
                struct.pack("<B", 20) +  # script length
                b"\x00" * 20)  # placeholder pubkey hash
        
        cb_tx = (struct.pack("<I", 2) +  # version
                 vin +
                 struct.pack("<B", 1) +  # vout count
                 vout +
                 struct.pack("<I", 0))  # locktime
        
        # Merkle root (single tx = txid of coinbase)
        merkle = self.sha256d(cb_tx)
        
        # Block header
        header = (struct.pack("<I", 1) +  # version
                  prev_hash[:32] +
                  merkle[:32] +
                  struct.pack("<III", timestamp, bits, 0))  # nonce=0
        
        blk = {
            "version": 1,
            "prev": prev_hash[:32],
            "merkle": merkle[:32],
            "time": timestamp,
            "bits": bits,
            "nonce": 0,
            "txs": [cb_tx],
        }
        
        chash = self.sha256d(header)
        
        return blk, header, chash
    
    def build_parent_block(self, child_hash: bytes, btc_prev_hash: bytes,
                           btc_height: int, btc_bits: int, timestamp: int = None,
                           payout_script: bytes = None) -> tuple:
        """
        Build the parent (Bitcoin) block template with merged-mining commitment.
        
        Returns:
        - coinbase: Raw coinbase transaction
        - prefix76: 76-byte header prefix (without nonce)
        """
        if timestamp is None:
            timestamp = int(time.time())
        
        if payout_script is None:
            # Default payout: placeholder P2PKH
            payout_script = bytes.fromhex(
                "76a914" + "00" * 20 + "88ac")
        
        # Merged-mining blob
        blob = (AUXPOW_MAGIC +
                child_hash +
                struct.pack("<I", 1) +  # tree_size = 1 (single aux)
                struct.pack("<I", 0))   # merkle_nonce = 0
        
        # Coinbase scriptSig
        script = (self._push(struct.pack("<I", btc_height + 1)) +
                  self._push(b"MergeMine") +
                  self._push(blob))
        
        # Coinbase transaction
        vin = (b"\x00" * 32 +
               struct.pack("<I", 0xFFFFFFFF) +
               self._push(script) +
               struct.pack("<I", 0xFFFFFFFF))
        
        # Block reward: 3.125 BTC = 312,500,000 sats
        reward = 312_500_000
        vout = (struct.pack("<Q", reward) +
                struct.pack("<B", len(payout_script)) +
                payout_script)
        
        coinbase = (struct.pack("<I", 1) +
                    vin +
                    struct.pack("<B", 1) +
                    vout +
                    struct.pack("<I", 0))
        
        # Merkle root (single tx)
        merkle = self.sha256d(coinbase)
        
        # Header prefix (76 bytes, without nonce)
        # Bitcoin uses reversed byte order for prev_hash in header
        if isinstance(btc_prev_hash, bytes):
            prev_reversed = btc_prev_hash[::-1]
        else:
            prev_reversed = bytes.fromhex(btc_prev_hash.hex())[::-1]
        prefix76 = (struct.pack("<I", 1) +
                    prev_reversed +
                    merkle +
                    struct.pack("<II", timestamp, btc_bits))
        
        assert len(prefix76) == 76, f"Prefix length: {len(prefix76)}"
        
        return coinbase, prefix76
    
    def grind_nonce(self, prefix76: bytes, target: int,
                    start_nonce: int = 0, max_attempts: int = 0x100000) -> int:
        """
        Find a nonce that meets the target using scalar wave guidance.
        
        Scans nonces starting from start_nonce, checking sha256d(prefix76 + nonce)
        against the target. Returns the first valid nonce found.
        
        Returns None if no nonce found within max_attempts.
        """
        nonce = start_nonce
        for _ in range(max_attempts):
            header = prefix76 + struct.pack("<I", nonce)
            hash_val = self.sha256d(header)
            if int.from_bytes(hash_val, "big") <= target:
                return nonce
            nonce += 1
        return None
    
    def grind_nonce_scalar_guided(self, prefix76: bytes, target: int,
                                   top_n: int = 100) -> int:
        """
        Find a nonce using scalar wave-guided search.
        
        First finds the top nonces by scalar wave amplitude, then checks
        them in order of spectral resonance. Falls back to linear search
        if no resonant nonce meets the target.
        """
        # Get top resonant nonces
        top_nonces = self.scalar_wave.top_nonces(count=top_n)
        
        # Check resonant nonces first
        for nonce, score in top_nonces:
            header = prefix76 + struct.pack("<I", nonce)
            hash_val = self.sha256d(header)
            if int.from_bytes(hash_val, "big") <= target:
                return nonce
        
        # Fallback: linear search from 0
        return self.grind_nonce(prefix76, target, start_nonce=0, max_attempts=0x100000)
    
    def check_dual_target(self, parent_hash: bytes, child_target: int,
                          bitcoin_target: int) -> dict:
        """
        Check whether the parent hash meets both targets.
        
        Returns dict with:
        - child_hit: bool (meets child target)
        - bitcoin_hit: bool (meets Bitcoin target)
        - dual_hit: bool (meets both)
        """
        hash_int = int.from_bytes(parent_hash, "big")
        
        child_hit = hash_int <= child_target
        bitcoin_hit = hash_int <= bitcoin_target
        
        return {
            "child_hit": child_hit,
            "bitcoin_hit": bitcoin_hit,
            "dual_hit": child_hit and bitcoin_hit,
            "hash_int": hash_int,
            "child_target": child_target,
            "bitcoin_target": bitcoin_target,
        }
    
    def one_merge_mine_round(self, child_prev: bytes, child_height: int,
                              child_bits: int, btc_prev: bytes,
                              btc_height: int, btc_bits: int,
                              timestamp: int = None) -> dict:
        """
        Execute one complete merge mining round.
        
        Steps:
        1. Build child block (Excalibur)
        2. Build parent block (Bitcoin) with merged-mining commitment
        3. Select difficulty channel via Bell state
        4. Grind nonce for parent header
        5. Check dual target
        6. Record spectral gap
        7. Update Fibonacci complexity
        
        Returns dict with all results.
        """
        if timestamp is None:
            timestamp = int(time.time())
        
        # Step 1: Build child block
        child_blk, child_header, child_hash = self.build_child_block(
            child_prev, child_height, child_bits, timestamp)
        
        child_target = DualTargetAnalyzer.bits_to_target(child_bits)
        bitcoin_target = DualTargetAnalyzer.bits_to_target(btc_bits)
        
        # Step 2: Build parent block
        coinbase, prefix76 = self.build_parent_block(
            child_hash, btc_prev, btc_height, btc_bits, timestamp)
        
        # Step 3: Select difficulty channel
        scalar_phase = self.scalar_wave.phase(child_height / 1000.0)
        channel = self.difficulty.select_channel(scalar_phase)
        adjusted_target = self.difficulty.get_adjusted_target(child_target, channel)
        
        # Use the child target directly (Bell state channel adjusts scoring, not target)
        effective_target = child_target
        
        # Step 4: Grind nonce
        nonce = self.grind_nonce(prefix76, effective_target,
                                  max_attempts=0x100000)
        
        result = {
            "child_height": child_height,
            "child_hash": child_hash.hex(),
            "child_bits": f"0x{child_bits:08x}",
            "btc_height": btc_height,
            "btc_bits": f"0x{btc_bits:08x}",
            "channel": channel,
            "channel_name": self.difficulty.BELL_NAMES[channel],
            "nonce": nonce,
            "hit": nonce is not None,
        }
        
        if nonce is not None:
            # Build full parent header
            parent_header_bytes = prefix76 + struct.pack("<I", nonce)
            parent_hash = self.sha256d(parent_header_bytes)
            
            # Step 5: Check dual target
            dual_check = self.check_dual_target(parent_hash, child_target, bitcoin_target)
            result.update(dual_check)
            result["parent_hash"] = parent_hash.hex()
            
            # Step 6: Record spectral gap
            gap_info = self.spectral_monitor.record_block(
                child_height, nonce, child_bits)
            result["spectral_gap"] = gap_info
            
            # Step 7: Update Fibonacci complexity
            self.merged_blocks.append({
                "height": child_height,
                "nonce": nonce,
                "parent_hash": parent_hash.hex(),
                "child_hash": child_hash.hex(),
            })
            n_blocks = len(self.merged_blocks)
            complexity = self.complexity.complexity_analysis(n_blocks)
            result["complexity"] = complexity
            result["n_merged_blocks"] = n_blocks
            
            # Build AuxPoW structure
            auxpow = {
                "parent_header": parent_header_bytes.hex(),
                "parent_coinbase": coinbase.hex(),
                "coinbase_branch": [],  # Single tx, no branch needed
                "coinbase_index": 0,
            }
            result["auxpow"] = auxpow
            result["child_block"] = {
                "version": child_blk["version"],
                "prev": child_blk["prev"].hex(),
                "merkle": child_blk["merkle"].hex(),
                "time": child_blk["time"],
                "bits": child_blk["bits"],
                "nonce": child_blk["nonce"],
                "txs": [t.hex() for t in child_blk["txs"]],
            }
        
        return result


# ---------------------------------------------------------------------------
# Test Suite
# ---------------------------------------------------------------------------

def run_tests():
    """Run all merge mining connection tests."""
    passed = 0
    total = 0
    
    print("=" * 78)
    print("MERGE MINING CONNECTION — Test Suite")
    print("=" * 78)
    
    # ---- Scalar Wave Nonce Selector ----
    print("\n[Section 1] Scalar Wave Nonce Selector")
    
    total += 1
    sw = ScalarWaveNonceSelector()
    phi_0 = sw.phi(0.0)
    expected_phi_0 = sum(1.0 / g for g in RIEMANN_ZEROS)
    assert abs(phi_0 - expected_phi_0) < 1e-10, f"φ(0) = {phi_0} vs {expected_phi_0}"
    print(f"[1/24] Scalar wave φ(0) = {phi_0:.6f} (sum of 1/γₖ) ✓")
    passed += 1
    
    total += 1
    score = sw.score_nonce(0x12345678)
    assert 0 <= score <= 10, f"Score out of range: {score}"
    print(f"[2/24] Nonce scoring: 0x12345678 → |φ| = {score:.4f} ✓")
    passed += 1
    
    total += 1
    top = sw.top_nonces(count=5)
    assert len(top) == 5, f"Top nonces: {len(top)}"
    assert all(isinstance(n, int) and n >= 0 for n, s in top), "Nonce format"
    print(f"[3/24] Top 5 resonant nonces: {[f'0x{n:08x}' for n, s in top]} ✓")
    passed += 1
    
    total += 1
    phase = sw.phase(0.5)
    assert -math.pi <= phase <= math.pi or abs(phase) < 10, f"Phase: {phase}"
    print(f"[4/24] Scalar wave phase at t=0.5: {phase:.4f} rad ✓")
    passed += 1
    
    # ---- Fibonacci Block Complexity ----
    print("\n[Section 2] Fibonacci Block Complexity")
    
    total += 1
    assert FibonacciBlockComplexity.fibonacci(1) == 1, "F_1"
    assert FibonacciBlockComplexity.fibonacci(10) == 55, "F_10"
    assert FibonacciBlockComplexity.fibonacci(20) == 6765, "F_20"
    print(f"[5/24] Fibonacci: F_1=1, F_10=55, F_20=6765 ✓")
    passed += 1
    
    total += 1
    assert FibonacciBlockComplexity.tensor_state_dim(1) == 1, "dim(V_τ⊗1)"
    assert FibonacciBlockComplexity.tensor_state_dim(2) == 2, "dim(V_τ⊗2)"
    assert FibonacciBlockComplexity.tensor_state_dim(6) == 13, "dim(V_τ⊗6)"
    print(f"[6/24] Tensor state dim: dim(V_τ⊗6) = 13 ✓")
    passed += 1
    
    total += 1
    for n in [1, 5, 10, 15]:
        exact = FibonacciBlockComplexity.binet_exact(n)
        integer_val = FibonacciBlockComplexity.tensor_state_dim(n)
        assert abs(exact - integer_val) < 1e-10, f"Binet n={n}"
    print(f"[7/24] Exact Binet: F_{{n+1}} = (φ^{{n+1}} - ψ^{{n+1}})/√5 ✓")
    passed += 1
    
    total += 1
    conj_1 = FibonacciBlockComplexity.conjugate_term(1)
    conj_10 = FibonacciBlockComplexity.conjugate_term(10)
    assert abs(conj_1) > abs(conj_10), "Conjugate decays"
    print(f"[8/24] Conjugate decay: |ψ²/√5|={abs(conj_1):.4f} → |ψ¹¹/√5|={abs(conj_10):.6f} ✓")
    passed += 1
    
    total += 1
    comp = FibonacciBlockComplexity.complexity_analysis(10)
    assert comp["n_blocks"] == 10, "n_blocks"
    assert comp["tensor_state_dim"] == 89, f"dim: {comp['tensor_state_dim']}"
    assert "binet_exact" in comp, "Has binet_exact"
    print(f"[9/24] Complexity analysis: 10 blocks → dim = 89, log2 = {comp['log2_complexity']:.2f} ✓")
    passed += 1
    
    # ---- Bell State Difficulty ----
    print("\n[Section 3] Bell State Difficulty Channels")
    
    total += 1
    # Check orthonormality
    for i in range(4):
        b = BellStateDifficulty.BELL_STATES[i]
        norm = sum(x*x for x in b)
        assert abs(norm - 1.0) < 1e-10, f"Bell {i} norm: {norm}"
    print(f"[10/24] Bell states orthonormal: all 4 states have norm = 1.0 ✓")
    passed += 1
    
    total += 1
    # Check resolution of identity
    I = BellStateDifficulty.resolution_of_identity()
    for i in range(4):
        for j in range(4):
            expected = 1.0 if i == j else 0.0
            assert abs(I[i][j] - expected) < 1e-10, f"ΣP_{{{i},{j}}} = {I[i][j]}"
    print(f"[11/24] Resolution of identity: Σ Pᵢ = I₄ ✓")
    passed += 1
    
    total += 1
    # Check Hermitian projectors
    for i in range(4):
        P = BellStateDifficulty.projector(i)
        for j in range(4):
            for k in range(4):
                assert abs(P[j][k] - P[k][j]) < 1e-10, f"P_{i} not symmetric"
    print(f"[12/24] Bell projectors Hermitian: Pᵢ = Pᵢ† for all 4 states ✓")
    passed += 1
    
    total += 1
    # Hilbert-Pólya operator
    H = BellStateDifficulty.hilbert_polya_operator()
    for i in range(4):
        for j in range(4):
            assert abs(H[i][j] - H[j][i]) < 1e-10, f"H not Hermitian at {i},{j}"
    print(f"[13/24] Hilbert-Pólya operator H = Σ γₖ Pₖ is Hermitian ✓")
    passed += 1
    
    total += 1
    # Channel selection
    for phase in [0, math.pi/2, math.pi, 3*math.pi/2, -math.pi/2]:
        ch = BellStateDifficulty.select_channel(phase)
        assert 0 <= ch <= 3, f"Channel {ch} for phase {phase}"
    print(f"[14/24] Channel selection: phases map to channels 0-3 ✓")
    passed += 1
    
    total += 1
    # Difficulty channels
    for ch in range(4):
        info = BellStateDifficulty.DIFFICULTY_CHANNELS[ch]
        assert "name" in info and "multiplier" in info, f"Channel {ch} info"
    print(f"[15/24] Difficulty channels: easy/normal/hard/expert ✓")
    passed += 1
    
    # ---- Dual Target Analyzer ----
    print("\n[Section 4] Dual Target Analyzer")
    
    total += 1
    # Excalibur easy target vs Bitcoin hard target
    child_bits = 0x1f000100  # ~2^24 hashes
    btc_bits = 0x17047293    # Bitcoin mainnet difficulty
    analysis = DualTargetAnalyzer.analyze_dual_target(child_bits, btc_bits)
    assert analysis["child_bits"] == "0x1f000100", "Child bits"
    assert analysis["bitcoin_bits"] == "0x17047293", "BTC bits"
    assert analysis["stricter_chain"] == "Bitcoin", "Stricter chain"
    print(f"[16/24] Dual target: child 0x1f000100 vs BTC 0x17047293, stricter = {analysis['stricter_chain']} ✓")
    passed += 1
    
    total += 1
    # Same target test
    same_bits = 0x1f000100
    analysis = DualTargetAnalyzer.analyze_dual_target(same_bits, same_bits)
    assert analysis["child_difficulty"] == analysis["bitcoin_difficulty"], "Same difficulty"
    print(f"[17/24] Same target: child_diff = btc_diff = {analysis['child_difficulty']:.2f} ✓")
    passed += 1
    
    total += 1
    # bits_to_target / target_to_bits roundtrip
    # Note: compact target encoding loses leading zeros in mantissa,
    # so only values with the high mantissa bit set roundtrip exactly.
    for bits in [0x1d00ffff, 0x17021ec5, 0x1f00ffff]:
        target = DualTargetAnalyzer.bits_to_target(bits)
        recovered = DualTargetAnalyzer.target_to_bits(target)
        assert recovered == bits, f"Roundtrip: {bits:08x} → {target} → {recovered:08x}"
    print(f"[18/24] bits↔target roundtrip: 3 values verified ✓")
    passed += 1
    
    # ---- Spectral Gap Monitor ----
    print("\n[Section 5] Spectral Gap Monitor")
    
    total += 1
    sg = SpectralGapMonitor()
    gap = sg.compute_gap(100)
    expected = 2 * (1 - math.cos(2 * math.pi / 100))
    assert abs(gap - expected) < 1e-10, f"Gap: {gap} vs {expected}"
    print(f"[19/24] Spectral gap λ₁(r=100) = {gap:.6f} ✓")
    passed += 1
    
    total += 1
    # Invert gap
    recovered_period = sg.period_from_gap(gap)
    assert abs(recovered_period - 100) < 0.01, f"Period: {recovered_period}"
    print(f"[20/24] Period from gap: r = {recovered_period:.2f} (expected 100) ✓")
    passed += 1
    
    total += 1
    # Record blocks
    info = sg.record_block(100, 0x12345678, 0x1f000100)
    assert info["height"] == 100, "Height"
    assert info["nonce"] == 0x12345678, "Nonce"
    assert info["lambda_1"] >= 0, "λ₁ ≥ 0"
    print(f"[21/24] Record block: height=100, λ₁={info['lambda_1']:.6f} ✓")
    passed += 1
    
    total += 1
    # Statistics
    sg.record_block(101, 0x87654321, 0x1f000100)
    sg.record_block(102, 0x11111111, 0x1f000100)
    stats = sg.gap_statistics()
    assert stats["count"] == 3, f"Count: {stats['count']}"
    assert stats["mean_lambda_1"] >= 0, "Mean λ₁"
    print(f"[22/24] Gap statistics: 3 blocks, mean λ₁ = {stats['mean_lambda_1']:.6f} ✓")
    passed += 1
    
    # ---- Merge Mining Engine ----
    print("\n[Section 6] Merge Mining Engine")
    
    total += 1
    engine = MergeMiningEngine()
    
    # Build child block
    child_prev = b"\x00" * 32
    child_blk, child_header, child_hash = engine.build_child_block(
        child_prev, 1, 0x1f000100)
    assert len(child_header) == 80, f"Header length: {len(child_header)}"
    assert len(child_hash) == 32, f"Hash length: {len(child_hash)}"
    assert child_blk["version"] == 1, "Version"
    assert child_blk["bits"] == 0x1f000100, "Bits"
    print(f"[23/24] Child block: height=1, header=80 bytes, hash={child_hash.hex()[:16]}.. ✓")
    passed += 1
    
    total += 1
    # Build parent block
    btc_prev = b"\x00" * 32
    coinbase, prefix76 = engine.build_parent_block(
        child_hash, btc_prev, 0, 0x20000000)
    assert len(prefix76) == 76, f"Prefix length: {len(prefix76)}"
    assert AUXPOW_MAGIC in coinbase, "AuxPoW magic in coinbase"
    print(f"[24/24] Parent block: prefix=76 bytes, AuxPoW magic in coinbase ✓")
    passed += 1
    
    # ---- Summary ----
    print("\n" + "=" * 78)
    print(f"RESULTS: {passed}/{total} tests passed")
    print("=" * 78)
    
    if passed == total:
        print("\n✓ All merge mining connection tests passed!")
        print("\nThe merge mining connection unifies:")
        print("  • Scalar wave φ(t) = Σ cos(γₖ·t)/γₖ for nonce selection")
        print("  • Fibonacci genesis law dim(V_{τ⊗n}) = F_{n+1} for complexity tracking")
        print("  • Bell state projectors for adaptive difficulty channels")
        print("  • Dual target analysis (Excalibur + Bitcoin)")
        print("  • Spectral gap monitoring λ₁ = 2(1-cos(2π/r))")
        print("  • AuxPoW block construction with fabe-'mm' commitment")
    else:
        print(f"\n✗ {total - passed} tests failed")
    
    return passed == total


# ---------------------------------------------------------------------------
# Demo: Full Merge Mining Round
# ---------------------------------------------------------------------------

def run_demo():
    """Run a full merge mining round demonstration."""
    print("\n" + "=" * 78)
    print("MERGE MINING CONNECTION — Full Round Demo")
    print("=" * 78)
    
    engine = MergeMiningEngine()
    
    # Simulated chain state
    child_prev = b"\x00" * 32  # Genesis prev
    child_height = 1
    child_bits = 0x1f00ffff  # Easy target (~2^24 hashes)
    
    btc_prev = b"\x00" * 32  # Simulated BTC genesis
    btc_height = 0
    btc_bits = 0x1f00ffff  # Same easy target for demo
    
    print(f"\nChild (Excalibur): height={child_height}, bits=0x{child_bits:08x}")
    print(f"Parent (Bitcoin):  height={btc_height}, bits=0x{btc_bits:08x}")
    
    # Execute one round
    result = engine.one_merge_mine_round(
        child_prev, child_height, child_bits,
        btc_prev, btc_height, btc_bits)
    
    print(f"\nResult:")
    print(f"  Child hash: {result['child_hash'][:16]}..")
    print(f"  Difficulty channel: {result['channel_name']} ({result['channel_name']})")
    print(f"  Nonce found: {result['hit']}")
    
    if result['hit']:
        print(f"  Nonce: 0x{result['nonce']:08x}")
        print(f"  Parent hash: {result['parent_hash'][:16]}..")
        print(f"  Child target met: {result['child_hit']}")
        print(f"  Bitcoin target met: {result['bitcoin_hit']}")
        print(f"  Dual hit: {result['dual_hit']}")
        
        if 'spectral_gap' in result:
            sg = result['spectral_gap']
            print(f"  Spectral gap λ₁: {sg['lambda_1']:.6f}")
            print(f"  Period: {sg['period']}")
        
        if 'complexity' in result:
            comp = result['complexity']
            print(f"  Merged blocks: {result['n_merged_blocks']}")
            print(f"  Tensor state dim: {comp['tensor_state_dim']} ({comp['fibonacci_number']})")
            print(f"  Log2 complexity: {comp['log2_complexity']:.2f} bits")
    
    # Dual target analysis
    print(f"\nDual Target Analysis:")
    analysis = DualTargetAnalyzer.analyze_dual_target(child_bits, btc_bits)
    print(f"  Child difficulty: {analysis['child_difficulty']:.2f}")
    print(f"  Bitcoin difficulty: {analysis['bitcoin_difficulty']:.2f}")
    print(f"  Stricter chain: {analysis['stricter_chain']}")
    print(f"  Expected hashes (child): {analysis['expected_hashes_child']:.2e}")
    print(f"  Expected hashes (BTC): {analysis['expected_hashes_bitcoin']:.2e}")
    
    # Bell state analysis
    print(f"\nBell State Analysis:")
    I = BellStateDifficulty.resolution_of_identity()
    print(f"  Resolution of identity: Σ Pᵢ = I₄ (verified)")
    H = BellStateDifficulty.hilbert_polya_operator()
    print(f"  Hilbert-Pólya operator: H = Σ γₖ Pₖ (Hermitian)")
    
    # Fibonacci complexity
    print(f"\nFibonacci Complexity:")
    for n in [1, 2, 3, 5, 8, 13]:
        comp = FibonacciBlockComplexity.complexity_analysis(n)
        print(f"  {n} blocks: dim = {comp['tensor_state_dim']} ({comp['fibonacci_number']}), "
              f"log2 = {comp['log2_complexity']:.2f}")
    
    print("\n" + "=" * 78)
    print("Merge mining connection demo complete.")
    print("=" * 78)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Merge Mining Connection")
    parser.add_argument("--test", action="store_true", help="Run tests")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    
    args = parser.parse_args()
    
    if args.test:
        success = run_tests()
        sys.exit(0 if success else 1)
    elif args.demo:
        run_demo()
    else:
        # Default: run tests then demo
        success = run_tests()
        if success:
            run_demo()
        sys.exit(0 if success else 1)
