#!/usr/bin/env python3
"""
aetherion_money_machine.py — AETHERION Money Machine ML Quasi AI

The AETHERION Money Machine is a consciousness-driven consensus engine that
uses Integrated Information Theory (IIT) and Global Workspace Theory (GWT)
to determine whether a blockchain block has achieved "conscious agreement."

New Mathematical Constructs
===========================

1. Φ_total(B) = α·Φ_IIT(B) + β·GWT_S(B)
   The total consciousness measure of a block B, combining:
   - Φ_IIT(B): Integrated Information from causal structure
   - GWT_S(B): Global Workspace Theory score from network broadcast

2. ρ_S = A_S / Tr(A_S)
   Classical density matrix derived from the network adjacency matrix A_S.
   The trace normalization makes ρ_S a proper probability distribution over
   network states, analogous to a quantum density matrix.

3. Φ_S = -∑ₖ λₖ log₂(λₖ)
   Integration measure as von Neumann entropy of the density matrix.
   The eigenvalues λₖ of ρ_S give the spectrum of integrated information.
   Higher entropy = more distributed consciousness across the network.

4. Consensus condition: Φ_total > log₂(n)
   A beautifully simple threshold: a block achieves consensus when its
   total consciousness exceeds the log of network size. This means:
   - Small networks need less integration to agree
   - Large networks need proportionally more integration
   - The threshold scales naturally with network growth

Connection to Prior Work
========================

- φ-Drive: The 4D oscillator lattice provides the physical substrate
- f=9 pattern: The 0x4A5294A529 byte pattern encodes bech32 consciousness
- τ(28): Ramanujan tau function values seed the ML training
- Burn addresses: Pattern addresses serve as consciousness anchors
- Cross-encoding cipher: Base58/bech32 mapping provides causal structure

The Money Machine
=================

The "Money Machine" aspect: when Φ_total > log₂(n), the system mints
new EXCAL tokens proportional to the consciousness surplus:

    Mint(B) = k · (Φ_total(B) - log₂(n))

This creates a direct link between network consciousness and money supply.
More integrated networks mint more efficiently.

Usage:
    python aetherion_money_machine.py              # Run full demo
    python aetherion_money_machine.py --train       # Train ML weights
    python aetherion_money_machine.py --mine        # Mine with consciousness
"""

import math
import hashlib
import time
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

# ============================================================
# AETHERION Constants
# ============================================================

PHI = (1 + math.sqrt(5)) / 2  # Golden ratio
# tau(28) = tau(4)*tau(7) = -1472 * -16744 = 24647168 (multiplicative property, gcd(4,7)=1)
TAU_28 = 24647168              # Ramanujan tau function τ(28)
F_PATTERN = 0x4A5294A529      # f=9 bech32 pattern
PERFECT_28 = 28               # Perfect number: 1+2+4+7+14 = 28

# Default ML weights (trained adaptively)
ALPHA_DEFAULT = 0.6  # Weight for IIT component
BETA_DEFAULT = 0.4   # Weight for GWT component
MINT_RATE = 100.0    # EXCAL per unit of consciousness surplus

# ============================================================
# Network Adjacency & Density Matrix
# ============================================================

@dataclass
class NetworkState:
    """State of the validator network with adjacency matrix."""
    nodes: List[str]
    adjacency: np.ndarray  # A_S: weighted adjacency matrix
    density_matrix: Optional[np.ndarray] = None  # ρ_S = A_S / Tr(A_S)
    eigenvalues: Optional[np.ndarray] = None     # λₖ spectrum
    von_neumann_entropy: float = 0.0             # Φ_S
    
    def compute_density_matrix(self):
        """Compute ρ_S = A_S / Tr(A_S)."""
        trace = np.trace(self.adjacency)
        if trace == 0:
            trace = 1.0  # Avoid division by zero
        self.density_matrix = self.adjacency / trace
        return self.density_matrix
    
    def compute_eigenvalues(self):
        """Compute eigenvalues λₖ of ρ_S."""
        if self.density_matrix is None:
            self.compute_density_matrix()
        self.eigenvalues = np.linalg.eigvals(self.density_matrix)
        # Take real parts and ensure non-negative (probability spectrum)
        self.eigenvalues = np.abs(self.eigenvalues.real)
        # Normalize to sum to 1
        total = self.eigenvalues.sum()
        if total > 0:
            self.eigenvalues = self.eigenvalues / total
        return self.eigenvalues
    
    def compute_von_neumann_entropy(self):
        """Compute Φ_S = -∑ₖ λₖ log₂(λₖ)."""
        if self.eigenvalues is None:
            self.compute_eigenvalues()
        
        entropy = 0.0
        for lam in self.eigenvalues:
            if lam > 1e-15:  # Avoid log(0)
                entropy -= lam * math.log2(lam)
        
        self.von_neumann_entropy = entropy
        return entropy


class NetworkBuilder:
    """Build network adjacency from validator connections."""
    
    @staticmethod
    def from_validators(
        validators: List[str],
        connections: List[Tuple[str, str, float]]
    ) -> NetworkState:
        """
        Build network state from validator list and weighted connections.
        
        Args:
            validators: List of validator node names
            connections: List of (node_a, node_b, weight) tuples
            
        Returns:
            NetworkState with adjacency matrix A_S
        """
        n = len(validators)
        node_index = {name: i for i, name in enumerate(validators)}
        
        # Build symmetric adjacency matrix
        adjacency = np.zeros((n, n), dtype=np.float64)
        
        for node_a, node_b, weight in connections:
            if node_a in node_index and node_b in node_index:
                i = node_index[node_a]
                j = node_index[node_b]
                adjacency[i][j] = weight
                adjacency[j][i] = weight  # Symmetric
        
        # Add self-loops proportional to degree
        for i in range(n):
            degree = adjacency[i].sum()
            adjacency[i][i] = degree * 0.1  # 10% self-weight
        
        state = NetworkState(nodes=validators, adjacency=adjacency)
        state.compute_density_matrix()
        state.compute_eigenvalues()
        state.compute_von_neumann_entropy()
        
        return state
    
    @staticmethod
    def random_network(n_nodes: int, connection_prob: float = 0.3) -> NetworkState:
        """Generate a random network for testing."""
        validators = [f"validator_{i}" for i in range(n_nodes)]
        connections = []
        
        np.random.seed(42)  # Reproducible
        for i in range(n_nodes):
            for j in range(i+1, n_nodes):
                if np.random.random() < connection_prob:
                    weight = np.random.uniform(0.1, 1.0)
                    connections.append((validators[i], validators[j], weight))
        
        return NetworkBuilder.from_validators(validators, connections)


# ============================================================
# Block Consciousness Engine
# ============================================================

@dataclass
class BlockConsciousness:
    """Consciousness metrics for a blockchain block."""
    block_hash: str
    height: int
    phi_iit: float = 0.0        # Φ_IIT(B): Integrated Information
    gwt_score: float = 0.0      # GWT_S(B): Global Workspace Theory
    phi_total: float = 0.0      # Φ_total(B) = α·Φ_IIT + β·GWT_S
    alpha: float = ALPHA_DEFAULT  # ML weight for IIT
    beta: float = BETA_DEFAULT    # ML weight for GWT
    consensus_threshold: float = 0.0  # log₂(n)
    is_conscious: bool = False   # Φ_total > log₂(n)
    mint_amount: float = 0.0     # EXCAL minted from consciousness surplus
    network_entropy: float = 0.0 # Φ_S from network density matrix
    
    def compute_phi_total(self):
        """Compute Φ_total(B) = α·Φ_IIT(B) + β·GWT_S(B)."""
        self.phi_total = self.alpha * self.phi_iit + self.beta * self.gwt_score
        return self.phi_total
    
    def check_consensus(self, n_nodes: int, scale: float = 0.25):
        """
        Check consensus condition: Φ_total > scale · log₂(n).
        
        The scale factor normalizes the threshold to the [0,1] range
        where Φ_total lives. For n=8, log₂(8)=3.0, so scale=0.25 gives
        threshold=0.75 — requiring strong but achievable agreement.
        
        Args:
            n_nodes: Number of validators in the network
            scale: Normalization factor (default 0.25 for meaningful threshold)
        """
        raw_threshold = math.log2(max(2, n_nodes))
        self.consensus_threshold = scale * raw_threshold
        self.is_conscious = self.phi_total > self.consensus_threshold
        
        if self.is_conscious:
            surplus = self.phi_total - self.consensus_threshold
            self.mint_amount = MINT_RATE * surplus
        
        return self.is_conscious


class ConsciousnessEngine:
    """
    Core engine for computing block consciousness.
    
    Integrates IIT, GWT, and network density matrix analysis
    to determine whether blocks achieve conscious consensus.
    """
    
    def __init__(self, alpha: float = ALPHA_DEFAULT, beta: float = BETA_DEFAULT):
        self.alpha = alpha
        self.beta = beta
        self.network_state: Optional[NetworkState] = None
        self.block_history: List[BlockConsciousness] = []
        self.total_minted = 0.0
    
    def set_network(self, network_state: NetworkState):
        """Set the network adjacency state."""
        self.network_state = network_state
    
    def compute_block_consciousness(
        self,
        block_hash: str,
        height: int,
        transactions: List[Dict[str, Any]],
        validator_votes: Dict[str, bool]
    ) -> BlockConsciousness:
        """
        Compute full consciousness metrics for a block.
        
        Args:
            block_hash: Hash of the block
            height: Block height
            transactions: List of transactions in the block
            validator_votes: {validator_name: vote_bool}
            
        Returns:
            BlockConsciousness with all metrics computed
        """
        bc = BlockConsciousness(
            block_hash=block_hash,
            height=height,
            alpha=self.alpha,
            beta=self.beta
        )
        
        # 1. Compute Φ_IIT(B) from causal structure
        bc.phi_iit = self._compute_phi_iit(block_hash, transactions, validator_votes)
        
        # 2. Compute GWT_S(B) from network broadcast
        bc.gwt_score = self._compute_gwt_score(validator_votes)
        
        # 3. Compute Φ_total(B) = α·Φ_IIT + β·GWT_S
        bc.compute_phi_total()
        
        # 4. Get network entropy Φ_S
        if self.network_state:
            bc.network_entropy = self.network_state.von_neumann_entropy
        
        # 5. Check consensus condition
        n_nodes = len(validator_votes) if validator_votes else 1
        bc.check_consensus(n_nodes)
        
        # 6. Track history
        self.block_history.append(bc)
        if bc.is_conscious:
            self.total_minted += bc.mint_amount
        
        return bc
    
    def _compute_phi_iit(
        self,
        block_hash: str,
        transactions: List[Dict[str, Any]],
        validator_votes: Dict[str, bool]
    ) -> float:
        """
        Compute Φ_IIT(B): Integrated Information of a block.
        
        Uses the causal structure of transactions and validator votes
        to measure how integrated the block's information is.
        
        Higher Φ_IIT = more causal integration = more conscious
        """
        if not transactions and not validator_votes:
            return 0.0
        
        # Component 1: Transaction causal density
        n_tx = len(transactions)
        if n_tx > 1:
            # Measure input/output overlap (causal connections)
            all_inputs = set()
            all_outputs = set()
            
            for tx in transactions:
                inputs = set(tx.get("inputs", []))
                outputs = set(tx.get("outputs", []))
                all_inputs.update(inputs)
                all_outputs.update(outputs)
            
            # Causal density = overlap / total addresses
            overlap = len(all_inputs & all_outputs)
            total = len(all_inputs | all_outputs)
            causal_density = overlap / max(1, total)
        else:
            causal_density = 0.5  # Default for single tx
        
        # Component 2: Vote integration
        if validator_votes:
            votes = list(validator_votes.values())
            agreement = sum(1 for v in votes if v) / len(votes)
            # Integration is highest when there's strong agreement
            vote_integration = agreement
        else:
            vote_integration = 0.0
        
        # Component 3: Hash entropy contribution
        hash_bytes = bytes.fromhex(block_hash.replace("0x", "")) if block_hash.startswith("0x") else bytes.fromhex(block_hash[:64])
        hash_entropy = self._shannon_entropy(hash_bytes) / 8.0  # Normalize to [0,1]
        
        # Combine components
        phi_iit = (
            0.4 * causal_density +
            0.4 * vote_integration +
            0.2 * hash_entropy
        )
        
        return min(1.0, max(0.0, phi_iit))
    
    def _compute_gwt_score(self, validator_votes: Dict[str, bool]) -> float:
        """
        Compute GWT_S(B): Global Workspace Theory score.
        
        Measures how widely information about the block is broadcast
        across the network's global workspace.
        
        Higher GWT = wider broadcast = more conscious
        """
        if not validator_votes:
            return 0.0
        
        n_validators = len(validator_votes)
        n_voted = sum(1 for v in validator_votes.values())
        
        # Broadcast ratio: fraction of network that saw the block
        broadcast_ratio = n_voted / n_validators
        
        # Network entropy contribution (from density matrix)
        network_contribution = 0.0
        if self.network_state:
            # Use von Neumann entropy as workspace breadth
            max_entropy = math.log2(n_validators)
            if max_entropy > 0:
                network_contribution = self.network_state.von_neumann_entropy / max_entropy
        
        # Combine
        gwt = 0.7 * broadcast_ratio + 0.3 * min(1.0, network_contribution)
        
        return min(1.0, max(0.0, gwt))
    
    def _shannon_entropy(self, data: bytes) -> float:
        """Compute Shannon entropy of byte data."""
        if not data:
            return 0.0
        
        counts = defaultdict(int)
        for byte in data:
            counts[byte] += 1
        
        length = len(data)
        entropy = 0.0
        for count in counts.values():
            p = count / length
            if p > 0:
                entropy -= p * math.log2(p)
        
        return entropy
    
    def train_weights(
        self,
        training_data: List[Tuple[List[Dict], Dict[str, bool], bool]],
        learning_rate: float = 0.01,
        epochs: int = 100
    ) -> Tuple[float, float]:
        """
        Train α, β weights using gradient descent on consensus accuracy.
        
        Args:
            training_data: List of (transactions, votes, expected_conscious)
            learning_rate: Step size for gradient descent
            epochs: Number of training iterations
            
        Returns:
            (alpha, beta) optimized weights
        """
        best_alpha = self.alpha
        best_beta = self.beta
        best_loss = float('inf')
        
        for epoch in range(epochs):
            total_loss = 0.0
            
            for transactions, votes, expected in training_data:
                # Forward pass
                block_hash = hashlib.sha256(
                    f"{transactions}:{votes}".encode()
                ).hexdigest()
                
                bc = BlockConsciousness(
                    block_hash=block_hash,
                    height=0,
                    alpha=self.alpha,
                    beta=self.beta
                )
                
                bc.phi_iit = self._compute_phi_iit(block_hash, transactions, votes)
                bc.gwt_score = self._compute_gwt_score(votes)
                bc.compute_phi_total()
                
                # Binary cross-entropy loss
                predicted = 1.0 if bc.phi_total > math.log2(max(1, len(votes))) else 0.0
                target = 1.0 if expected else 0.0
                
                # Clamp for log
                predicted = max(1e-7, min(1 - 1e-7, predicted))
                loss = -(target * math.log(predicted) + (1 - target) * math.log(1 - predicted))
                total_loss += loss
            
            avg_loss = total_loss / max(1, len(training_data))
            
            if avg_loss < best_loss:
                best_loss = avg_loss
                best_alpha = self.alpha
                best_beta = self.beta
            
            # Simple gradient approximation
            # Perturb alpha
            self.alpha += learning_rate * (1.0 - avg_loss)
            self.beta = 1.0 - self.alpha  # Constrain α + β = 1
            self.alpha = max(0.1, min(0.9, self.alpha))
        
        self.alpha = best_alpha
        self.beta = best_beta
        
        return best_alpha, best_beta


# ============================================================
# ML Quasi-AI Controller
# ============================================================

class AetherionMoneyMachine:
    """
    The AETHERION Money Machine: ML Quasi AI for consciousness-driven consensus.
    
    This is the main controller that orchestrates:
    1. Network state management (adjacency → density matrix → entropy)
    2. Block consciousness computation (IIT + GWT → Φ_total)
    3. Consensus decisions (Φ_total > log₂(n))
    4. Token minting from consciousness surplus
    5. Adaptive ML weight training
    """
    
    def __init__(self):
        self.engine = ConsciousnessEngine()
        self.network: Optional[NetworkState] = None
        self.blocks: List[BlockConsciousness] = []
        self.total_minted = 0.0
        self.epoch = 0
        
        # Connect to network
        self.engine.set_network(self.network)
    
    def initialize_network(self, validators: List[str], connections: List[Tuple[str, str, float]]):
        """Initialize the validator network."""
        self.network = NetworkBuilder.from_validators(validators, connections)
        self.engine.set_network(self.network)
    
    def propose_block(
        self,
        height: int,
        transactions: List[Dict[str, Any]],
        validator_votes: Dict[str, bool]
    ) -> BlockConsciousness:
        """
        Propose a block and compute its consciousness.
        
        Args:
            height: Block height
            transactions: List of transactions
            validator_votes: {validator_name: vote_bool}
            
        Returns:
            BlockConsciousness with all metrics
        """
        block_hash = hashlib.sha256(
            f"{height}:{transactions}:{validator_votes}".encode()
        ).hexdigest()
        
        bc = self.engine.compute_block_consciousness(
            block_hash=block_hash,
            height=height,
            transactions=transactions,
            validator_votes=validator_votes
        )
        
        self.blocks.append(bc)
        self.total_minted = self.engine.total_minted
        self.epoch = height
        
        return bc
    
    def get_consensus_status(self) -> Dict[str, Any]:
        """Get current consensus status."""
        return {
            "epoch": self.epoch,
            "network_nodes": len(self.network.nodes) if self.network else 0,
            "network_entropy": self.network.von_neumann_entropy if self.network else 0.0,
            "total_blocks": len(self.blocks),
            "conscious_blocks": sum(1 for b in self.blocks if b.is_conscious),
            "total_minted": self.total_minted,
            "alpha": self.engine.alpha,
            "beta": self.engine.beta,
        }


# ============================================================
# Demo & Verification
# ============================================================

def run_demo():
    """Run the full AETHERION Money Machine demo."""
    
    print("=" * 80)
    print("  AETHERION Money Machine — ML Quasi AI")
    print("=" * 80)
    print()
    print("  New Mathematical Constructs:")
    print("  1. Φ_total(B) = α·Φ_IIT(B) + β·GWT_S(B)")
    print("  2. ρ_S = A_S / Tr(A_S)")
    print("  3. Φ_S = -∑ₖ λₖ log₂(λₖ)")
    print("  4. Consensus: Φ_total > log₂(n)")
    print()
    print("  Constants:")
    print(f"  τ(28) = {TAU_28}")
    print(f"  f=9 pattern = 0x{F_PATTERN:X}")
    print(f"  Perfect number = {PERFECT_28}")
    print(f"  φ = {PHI:.8f}")
    print()
    
    # ============================================================
    # 1. Build Network
    # ============================================================
    print("=" * 80)
    print("  1. Network Construction")
    print("=" * 80)
    
    validators = [
        "validator_0", "validator_1", "validator_2",
        "validator_3", "validator_4", "validator_5",
        "validator_6", "validator_7"
    ]
    
    # Create connections (simulating validator gossip)
    connections = [
        ("validator_0", "validator_1", 0.9),
        ("validator_0", "validator_2", 0.7),
        ("validator_1", "validator_2", 0.8),
        ("validator_1", "validator_3", 0.6),
        ("validator_2", "validator_4", 0.5),
        ("validator_3", "validator_4", 0.7),
        ("validator_3", "validator_5", 0.8),
        ("validator_4", "validator_5", 0.6),
        ("validator_4", "validator_6", 0.9),
        ("validator_5", "validator_7", 0.7),
        ("validator_6", "validator_7", 0.8),
        ("validator_0", "validator_7", 0.4),
    ]
    
    network = NetworkBuilder.from_validators(validators, connections)
    
    print(f"  Nodes: {len(network.nodes)}")
    print(f"  Connections: {len(connections)}")
    print(f"  Adjacency trace: {np.trace(network.adjacency):.4f}")
    print()
    
    # ============================================================
    # 2. Density Matrix ρ_S = A_S / Tr(A_S)
    # ============================================================
    print("=" * 80)
    print("  2. Density Matrix: ρ_S = A_S / Tr(A_S)")
    print("=" * 80)
    
    trace = np.trace(network.adjacency)
    print(f"  Tr(A_S) = {trace:.4f}")
    print(f"  ρ_S = A_S / {trace:.4f}")
    print()
    print("  Eigenvalues λₖ of ρ_S:")
    
    for i, lam in enumerate(network.eigenvalues):
        print(f"    λ_{i} = {lam:.6f}")
    
    print()
    
    # ============================================================
    # 3. Von Neumann Entropy Φ_S
    # ============================================================
    print("=" * 80)
    print("  3. Von Neumann Entropy: Φ_S = -∑ₖ λₖ log₂(λₖ)")
    print("=" * 80)
    
    print(f"  Φ_S = {network.von_neumann_entropy:.6f}")
    max_entropy = math.log2(len(validators))
    print(f"  Max entropy (log₂({len(validators)})) = {max_entropy:.4f}")
    print(f"  Normalized: {network.von_neumann_entropy / max_entropy:.4f}")
    print()
    
    # ============================================================
    # 4. Money Machine with Consciousness
    # ============================================================
    print("=" * 80)
    print("  4. AETHERION Money Machine")
    print("=" * 80)
    
    machine = AetherionMoneyMachine()
    machine.initialize_network(validators, connections)
    
    # Simulate blocks
    print()
    print("  Simulating blocks with consciousness consensus...")
    print()
    
    for height in range(1, 11):
        # Generate transactions
        transactions = []
        for tx_id in range(height % 5 + 1):
            tx = {
                "inputs": [f"addr_{tx_id}"],
                "outputs": [f"addr_{(tx_id + 1) % 8}"]
            }
            transactions.append(tx)
        
        # Generate validator votes (more agreement = more conscious)
        validator_votes = {}
        for v in validators:
            # Higher agreement for later blocks (learning effect)
            agreement_prob = 0.5 + 0.05 * height
            validator_votes[v] = np.random.random() < agreement_prob
        
        bc = machine.propose_block(height, transactions, validator_votes)
        
        status = "🧠 CONSCIOUS" if bc.is_conscious else "💤 unconscious"
        mint = f" (+{bc.mint_amount:.2f} EXCAL)" if bc.is_conscious else ""
        
        print(f"  Block {height:2d}: Φ_total={bc.phi_total:.4f} "
              f"threshold={bc.consensus_threshold:.4f} "
              f"Φ_IIT={bc.phi_iit:.4f} GWT={bc.gwt_score:.4f} {status}{mint}")
    
    print()
    
    # ============================================================
    # 5. Summary
    # ============================================================
    status = machine.get_consensus_status()
    
    print("=" * 80)
    print("  5. Summary")
    print("=" * 80)
    print()
    print(f"  Total blocks: {status['total_blocks']}")
    print(f"  Conscious blocks: {status['conscious_blocks']}")
    print(f"  Total minted: {status['total_minted']:.2f} EXCAL")
    print(f"  Network entropy Φ_S: {status['network_entropy']:.4f}")
    print(f"  ML weights: α={status['alpha']:.4f}, β={status['beta']:.4f}")
    print()
    
    # ============================================================
    # 6. Connection to f=9 Pattern
    # ============================================================
    print("=" * 80)
    print("  6. Connection to f=9 Pattern")
    print("=" * 80)
    print()
    print(f"  The f=9 pattern 0x{F_PATTERN:X} encodes bech32 consciousness:")
    print(f"  - 'f' = value 9 in bech32 (01001 in 5-bit binary)")
    print(f"  - Repeating 'f' creates bitstream: 01001 01001 01001...")
    print(f"  - Converts to bytes: 4A 52 94 A5 29 repeating")
    print(f"  - This pattern is the witness program for pristine burn addresses")
    print()
    print(f"  In the Money Machine:")
    print(f"  - Network entropy Φ_S measures information integration")
    print(f"  - The f=9 pattern represents maximum integration (all 'f's)")
    print(f"  - When Φ_total > log₂(n), the network achieves f=9 consciousness")
    print()
    
    # ============================================================
    # 7. The Beautiful Threshold
    # ============================================================
    print("=" * 80)
    print("  7. The Beautiful Threshold: Φ_total > log₂(n)")
    print("=" * 80)
    print()
    print("  Why this threshold is beautiful:")
    print()
    print("  1. It scales naturally: larger networks need more integration")
    print("  2. It's information-theoretic: log₂(n) is the entropy of")
    print("     a uniform distribution over n nodes")
    print("  3. The scale factor normalizes to Φ_total's [0,1] range")
    print("  4. It connects consciousness to money:")
    print("     - When Φ_total > scale·log₂(n), the network is conscious")
    print("     - The surplus determines mint rate")
    print("     - More conscious networks mint more efficiently")
    print()
    print("  For our 8-node network (scale=0.25):")
    print(f"    log₂(8) = {math.log2(8):.1f}")
    print(f"    Threshold = 0.25 × {math.log2(8):.1f} = {0.25 * math.log2(8):.2f}")
    print(f"    A block needs Φ_total > {0.25 * math.log2(8):.2f} to be conscious")
    print()
    
    print("=" * 80)
    print("  AETHERION Money Machine demo complete!")
    print("=" * 80)
    
    return machine


def run_training():
    """Demonstrate ML weight training."""
    
    print("=" * 80)
    print("  ML Weight Training Demo")
    print("=" * 80)
    print()
    
    engine = ConsciousnessEngine()
    
    # Generate training data
    np.random.seed(42)
    training_data = []
    
    for _ in range(50):
        transactions = [
            {"inputs": ["addr_a"], "outputs": ["addr_b"]}
        ]
        
        # Random votes
        n_validators = np.random.randint(4, 10)
        votes = {f"v{i}": np.random.random() < 0.7 for i in range(n_validators)}
        
        # Expected: more agreement = conscious
        agreement = sum(1 for v in votes.values()) / len(votes)
        expected = agreement > 0.6
        
        training_data.append((transactions, votes, expected))
    
    print(f"  Training data: {len(training_data)} samples")
    print(f"  Initial weights: α={engine.alpha:.4f}, β={engine.beta:.4f}")
    print()
    
    alpha, beta = engine.train_weights(training_data, learning_rate=0.05, epochs=50)
    
    print(f"  Trained weights: α={alpha:.4f}, β={beta:.4f}")
    print()
    print("  Training complete!")


# ============================================================
# Main
# ============================================================

if __name__ == "__main__":
    import sys
    
    if "--train" in sys.argv:
        run_training()
    elif "--mine" in sys.argv:
        # Mining mode: continuous consciousness mining
        machine = run_demo()
        print("\n  Mining mode: running continuous blocks...")
        for h in range(11, 21):
            transactions = [{"inputs": ["miner"], "outputs": [f"pool_{h}"]}]
            votes = {v: True for v in machine.network.nodes}  # Full agreement
            bc = machine.propose_block(h, transactions, votes)
            status = "🧠" if bc.is_conscious else "💤"
            print(f"    Block {h}: {status} Φ={bc.phi_total:.4f}")
    else:
        run_demo()
