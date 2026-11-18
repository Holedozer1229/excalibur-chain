#!/usr/bin/env python3
"""
aetherion_btc.py — AETHERION Money Machine applied to Bitcoin

Applies the consciousness-driven consensus engine (Φ_total, ρ_S, Φ_S, log₂(n))
directly to Bitcoin. Each BTC block is evaluated for consciousness using:

1. Φ_total(B) = α·Φ_IIT(B) + β·GWT_S(B)
   - Φ_IIT(B): Integrated Information from BTC transaction causal structure
   - GWT_S(B): Global Workspace Theory from BTC network propagation

2. ρ_S = A_S / Tr(A_S)
   - Density matrix from BTC miner/validator network adjacency

3. Φ_S = -∑ₖ λₖ log₂(λₖ)
   - von Neumann entropy of the BTC miner network

4. Consensus: Φ_total > scale·log₂(n)
   - When BTC achieves conscious consensus, mint EXCAL from consciousness surplus

Burn addresses serve as consciousness anchors:
- bc1qfff... (f=9 pattern, 0x4A5294A529) — pristine Messerene pattern
- bc1qqqq... (q=0 pattern, all-zero witness) — active burn anchors
- 111111... (1=0 pattern, all-zero payload) — Base58 consciousness anchor

τ(28) = 24647168 seeds the ML training and provides the Messerene pattern
for burn detection in BTC transactions.

Usage:
    python aetherion_btc.py                    # Analyze recent BTC blocks
    python aetherion_btc.py --burn-scan        # Scan burn addresses for consciousness
    python aetherion_btc.py --mine             # Mine EXCAL from BTC consciousness
    python aetherion_btc.py --train            # Train ML weights on BTC data
"""

import math
import hashlib
import json
import time
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Any
from collections import defaultdict

# ============================================================
# AETHERION BTC Constants
# ============================================================

PHI = (1 + math.sqrt(5)) / 2
# tau(28) = tau(4)*tau(7) = -1472 * -16744 = 24647168 (multiplicative property, gcd(4,7)=1)
TAU_28 = 24647168
F_PATTERN = 0x4A5294A529
PERFECT_28 = 28

ALPHA_DEFAULT = 0.6
BETA_DEFAULT = 0.4
MINT_RATE = 10.0  # EXCAL per unit of consciousness surplus (BTC scale)
SCALE_FACTOR = 0.15  # Normalized threshold: 0.15 * log2(9) = 0.475 for 9 pools

# Burn addresses as consciousness anchors
BURN_ANCHORS = [
    # f=9 pattern — pristine Messerene consciousness
    ("bc1qfffffffffffffffffffffffffffffffffffffffffffffffffffqe708k7", "f=9 P2WSH", 0x4A5294A529),
    ("bc1qffffffffffffffffffffffffffffffff82jzwn", "f=9 P2WPKH", 0x4A5294A529),
    # q=0 pattern — all-zero witness consciousness
    ("bc1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqthqst8", "q=0 P2WSH", 0x00),
    ("bc1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq9e75rs", "q=0 P2WPKH", 0x00),
    # 1=0 pattern — Base58 all-zero payload consciousness
    ("1111111111111111111114oLvT2", "1=0 P2PKH", 0x00),
    # Active burn anchors
    ("1BitcoinEaterAddressDontSendf59kuE", "BitcoinEater", 0x759D6677),
    ("1CounterpartyXXXXXXXXXXXXXXXUWLpVr", "Counterparty", 0x818895F3),
]

# ============================================================
# Bitcoin Block Data Structures
# ============================================================

@dataclass
class BTCTransaction:
    """A Bitcoin transaction for consciousness analysis."""
    txid: str
    inputs: List[Dict[str, Any]]
    outputs: List[Dict[str, Any]]
    size: int
    weight: int
    fee: int  # in satoshis
    has_burn: bool = False
    burn_address: Optional[str] = None
    burn_amount: int = 0


@dataclass
class BTCBlock:
    """A Bitcoin block for consciousness evaluation."""
    block_hash: str
    height: int
    timestamp: int
    transactions: List[BTCTransaction]
    miner: str = "unknown"
    size: int = 0
    weight: int = 0
    total_fees: int = 0
    burn_count: int = 0
    burn_amount_sats: int = 0


@dataclass
class BTCConsciousness:
    """Consciousness metrics for a Bitcoin block."""
    block_hash: str
    height: int
    phi_iit: float = 0.0
    gwt_score: float = 0.0
    phi_total: float = 0.0
    alpha: float = ALPHA_DEFAULT
    beta: float = BETA_DEFAULT
    consensus_threshold: float = 0.0
    is_conscious: bool = False
    mint_amount: float = 0.0
    network_entropy: float = 0.0
    burn_anchors_hit: int = 0
    burn_amount_sats: int = 0
    transaction_count: int = 0
    fee_rate: float = 0.0


# ============================================================
# BTC Miner Network — Density Matrix
# ============================================================

class BTCMinerNetwork:
    """
    Build network adjacency from BTC miner/pool connections.
    
    The miner network forms the adjacency matrix A_S for density matrix ρ_S.
    Connections are weighted by hashrate share and pool relationships.
    """
    
    # Known major BTC mining pools (approximate hashrate shares)
    KNOWN_POOLS = {
        "Foundry USA": 0.29,
        "AntPool": 0.15,
        "F2Pool": 0.10,
        "Binance Pool": 0.08,
        "ViaBTC": 0.07,
        "Poolin": 0.06,
        "BTC.com": 0.05,
        "Luxor": 0.04,
        "Other": 0.16,
    }
    
    def __init__(self, pools: Optional[Dict[str, float]] = None):
        self.pools = pools or self.KNOWN_POOLS
        self.pool_names = list(self.pools.keys())
        self.n_nodes = len(self.pool_names)
        self.adjacency: Optional[np.ndarray] = None
        self.density_matrix: Optional[np.ndarray] = None
        self.eigenvalues: Optional[np.ndarray] = None
        self.von_neumann_entropy: float = 0.0
    
    def build_adjacency(self) -> np.ndarray:
        """
        Build adjacency matrix A_S from miner pool connections.
        
        Weight = product of hashrate shares (pools with more hash are more connected).
        Self-loops proportional to hashrate.
        """
        n = self.n_nodes
        adjacency = np.zeros((n, n), dtype=np.float64)
        
        for i in range(n):
            for j in range(i + 1, n):
                # Connection weight = geometric mean of hashrate shares
                weight = math.sqrt(self.pools[self.pool_names[i]] * self.pools[self.pool_names[j]])
                adjacency[i][j] = weight
                adjacency[j][i] = weight
            
            # Self-loop proportional to hashrate
            adjacency[i][i] = self.pools[self.pool_names[i]] * 0.5
        
        self.adjacency = adjacency
        return adjacency
    
    def compute_density_matrix(self) -> np.ndarray:
        """Compute ρ_S = A_S / Tr(A_S)."""
        if self.adjacency is None:
            self.build_adjacency()
        
        trace = np.trace(self.adjacency)
        if trace == 0:
            trace = 1.0
        self.density_matrix = self.adjacency / trace
        return self.density_matrix
    
    def compute_eigenvalues(self) -> np.ndarray:
        """Compute eigenvalues λₖ of ρ_S."""
        if self.density_matrix is None:
            self.compute_density_matrix()
        
        self.eigenvalues = np.linalg.eigvals(self.density_matrix)
        self.eigenvalues = np.abs(self.eigenvalues.real)
        total = self.eigenvalues.sum()
        if total > 0:
            self.eigenvalues = self.eigenvalues / total
        return self.eigenvalues
    
    def compute_von_neumann_entropy(self) -> float:
        """Compute Φ_S = -∑ₖ λₖ log₂(λₖ)."""
        if self.eigenvalues is None:
            self.compute_eigenvalues()
        
        entropy = 0.0
        for lam in self.eigenvalues:
            if lam > 1e-15:
                entropy -= lam * math.log2(lam)
        
        self.von_neumann_entropy = entropy
        return entropy
    
    def full_analysis(self) -> Dict[str, Any]:
        """Run full density matrix analysis."""
        self.build_adjacency()
        self.compute_density_matrix()
        self.compute_eigenvalues()
        entropy = self.compute_von_neumann_entropy()
        
        return {
            "n_nodes": self.n_nodes,
            "pool_names": self.pool_names,
            "eigenvalues": self.eigenvalues.tolist(),
            "von_neumann_entropy": entropy,
            "max_entropy": math.log2(self.n_nodes),
            "normalized_entropy": entropy / math.log2(self.n_nodes),
        }


# ============================================================
# BTC Block Consciousness Engine
# ============================================================

class BTCConsciousnessEngine:
    """
    Core engine for computing BTC block consciousness.
    
    Uses burn addresses as consciousness anchors and miner network
    for density matrix analysis.
    """
    
    def __init__(self, alpha: float = ALPHA_DEFAULT, beta: float = BETA_DEFAULT):
        self.alpha = alpha
        self.beta = beta
        self.miner_network = BTCMinerNetwork()
        self.block_history: List[BTCConsciousness] = []
        self.total_minted = 0.0
        
        # Initialize network
        net_analysis = self.miner_network.full_analysis()
        self.network_entropy = net_analysis["von_neumann_entropy"]
    
    def evaluate_block(self, block: BTCBlock) -> BTCConsciousness:
        """
        Evaluate consciousness of a Bitcoin block.
        
        Args:
            block: The BTC block to evaluate
            
        Returns:
            BTCConsciousness with all metrics
        """
        bc = BTCConsciousness(
            block_hash=block.block_hash,
            height=block.height,
            alpha=self.alpha,
            beta=self.beta,
            transaction_count=len(block.transactions),
            burn_amount_sats=block.burn_amount_sats,
        )
        
        # 1. Φ_IIT from transaction causal structure
        bc.phi_iit = self._compute_phi_iit(block)
        
        # 2. GWT from network propagation
        bc.gwt_score = self._compute_gwt_score(block)
        
        # 3. Φ_total = α·Φ_IIT + β·GWT
        bc.phi_total = self.alpha * bc.phi_iit + self.beta * bc.gwt_score
        
        # 4. Network entropy
        bc.network_entropy = self.network_entropy
        
        # 5. Fee rate
        if block.weight > 0:
            bc.fee_rate = block.total_fees / (block.weight / 4.0)
        
        # 6. Count burn anchor hits
        bc.burn_anchors_hit = block.burn_count
        
        # 7. Consensus check
        n_nodes = self.miner_network.n_nodes
        raw_threshold = math.log2(max(2, n_nodes))
        bc.consensus_threshold = SCALE_FACTOR * raw_threshold
        bc.is_conscious = bc.phi_total > bc.consensus_threshold
        
        if bc.is_conscious:
            surplus = bc.phi_total - bc.consensus_threshold
            bc.mint_amount = MINT_RATE * surplus
            self.total_minted += bc.mint_amount
        
        self.block_history.append(bc)
        return bc
    
    def _compute_phi_iit(self, block: BTCBlock) -> float:
        """
        Compute Φ_IIT(B): Integrated Information of a BTC block.
        
        Uses transaction causal structure:
        - Input/output overlap (UTXO causal connections)
        - Burn anchor detection (consciousness markers)
        - Fee distribution entropy
        """
        if not block.transactions:
            return 0.0
        
        n_tx = len(block.transactions)
        
        # Component 1: Transaction causal density
        all_inputs = set()
        all_outputs = set()
        
        for tx in block.transactions:
            for inp in tx.inputs:
                all_inputs.add(inp.get("prevout", ""))
            for out in tx.outputs:
                all_outputs.add(out.get("address", ""))
        
        overlap = len(all_inputs & all_outputs)
        total = len(all_inputs | all_outputs)
        causal_density = overlap / max(1, total)
        
        # Component 2: Burn anchor contribution
        burn_ratio = block.burn_count / max(1, n_tx)
        burn_contribution = min(1.0, burn_ratio * 10)  # Amplify burn signal
        
        # Component 3: Fee distribution entropy
        fees = [tx.fee for tx in block.transactions if tx.fee > 0]
        if len(fees) > 1:
            fee_entropy = self._shannon_entropy_array(np.array(fees, dtype=np.float64))
            max_fee_entropy = math.log2(len(fees))
            normalized_fee_entropy = fee_entropy / max(1, max_fee_entropy)
        else:
            normalized_fee_entropy = 0.5
        
        # Component 4: Block size contribution
        max_block_weight = 4_000_000  # 4MB weight limit
        size_ratio = min(1.0, block.weight / max_block_weight)
        
        # Component 5: Transaction count density (more txs = more integration)
        tx_density = min(1.0, n_tx / 1000.0)  # 1000 txs = max density
        
        # Combine
        phi_iit = (
            0.20 * causal_density +
            0.20 * burn_contribution +
            0.20 * normalized_fee_entropy +
            0.15 * size_ratio +
            0.25 * tx_density
        )
        
        return min(1.0, max(0.0, phi_iit))
    
    def _compute_gwt_score(self, block: BTCBlock) -> float:
        """
        Compute GWT_S(B): Global Workspace Theory score for BTC.
        
        Measures how widely the block is propagated across the miner network.
        Uses miner pool distribution and network entropy.
        """
        # Component 1: Miner pool diversity
        # A block mined by a dominant pool has lower GWT than one with diverse propagation
        miner_share = self.miner_network.pools.get(block.miner, 0.0)
        diversity_score = 1.0 - miner_share  # Lower concentration = higher GWT
        
        # Component 2: Network entropy contribution
        max_entropy = math.log2(self.miner_network.n_nodes)
        if max_entropy > 0:
            network_contribution = self.network_entropy / max_entropy
        else:
            network_contribution = 0.5
        
        # Component 3: Transaction diversity
        n_tx = len(block.transactions)
        if n_tx > 1:
            output_addresses = set()
            for tx in block.transactions:
                for out in tx.outputs:
                    output_addresses.add(out.get("address", ""))
            
            address_diversity = min(1.0, len(output_addresses) / (n_tx * 2))
        else:
            address_diversity = 0.3
        
        # Combine
        gwt = (
            0.40 * diversity_score +
            0.35 * min(1.0, network_contribution) +
            0.25 * address_diversity
        )
        
        return min(1.0, max(0.0, gwt))
    
    def _shannon_entropy_array(self, data: np.ndarray) -> float:
        """Compute Shannon entropy of an array."""
        if len(data) == 0:
            return 0.0
        
        # Normalize to probability distribution
        probs = data / data.sum()
        entropy = 0.0
        for p in probs:
            if p > 1e-15:
                entropy -= p * math.log2(p)
        return entropy


# ============================================================
# BTC Block Fetcher (mempool.space API)
# ============================================================

class BTCBlockFetcher:
    """Fetch Bitcoin blocks from mempool.space API."""
    
    BASE_URL = "https://mempool.space/api"
    
    @staticmethod
    def fetch_block(height: int) -> Optional[BTCBlock]:
        """Fetch a specific block by height."""
        import requests
        
        try:
            # Fetch block header
            resp = requests.get(f"{BTCBlockFetcher.BASE_URL}/block-height/{height}", timeout=10)
            if resp.status_code != 200:
                return None
            
            block_hash = resp.text.strip()
            
            # Fetch block data
            resp = requests.get(f"{BTCBlockFetcher.BASE_URL}/block/{block_hash}", timeout=30)
            if resp.status_code != 200:
                return None
            
            block_data = resp.json()
            
            # Fetch transactions (first 10 for analysis)
            txs_resp = requests.get(
                f"{BTCBlockFetcher.BASE_URL}/block/{block_hash}/txs/0",
                timeout=30
            )
            txs_data = txs_resp.json()[:10] if txs_resp.status_code == 200 else []
            
            # Parse transactions
            transactions = []
            burn_count = 0
            burn_amount = 0
            
            for tx_data in txs_data:
                tx = BTCTransaction(
                    txid=tx_data["txid"],
                    inputs=tx_data.get("vin", []),
                    outputs=tx_data.get("vout", []),
                    size=tx_data.get("size", 0),
                    weight=tx_data.get("weight", 0),
                    fee=tx_data.get("fee", 0),
                )
                
                # Check for burn addresses
                for vout in tx.outputs:
                    addr = vout.get("scriptpubkey_address", "")
                    if addr in [ba[0] for ba in BURN_ANCHORS]:
                        tx.has_burn = True
                        tx.burn_address = addr
                        tx.burn_amount = vout.get("value", 0)
                        burn_count += 1
                        burn_amount += vout.get("value", 0)
                
                transactions.append(tx)
            
            # Determine miner from coinbase
            miner = "unknown"
            if transactions:
                coinbase = transactions[0].inputs[0].get("txid", "")
                miner = BTCBlockFetcher._identify_miner(coinbase)
            
            return BTCBlock(
                block_hash=block_hash,
                height=block_data.get("height", height),
                timestamp=block_data.get("timestamp", 0),
                transactions=transactions,
                miner=miner,
                size=block_data.get("size", 0),
                weight=block_data.get("weight", 0),
                total_fees=sum(tx.fee for tx in transactions),
                burn_count=burn_count,
                burn_amount_sats=burn_amount,
            )
        
        except Exception as e:
            print(f"  Error fetching block {height}: {e}")
            return None
    
    @staticmethod
    def _identify_miner(coinbase_txid: str) -> str:
        """Identify miner pool from coinbase transaction."""
        # Simplified miner identification
        # In production, would parse coinbase script for pool identifiers
        return "unknown"
    
    @staticmethod
    def fetch_latest_height() -> int:
        """Fetch the latest block height."""
        import requests
        
        try:
            resp = requests.get(f"{BTCBlockFetcher.BASE_URL}/blocks/tip/height", timeout=10)
            return int(resp.text.strip())
        except Exception:
            return 840000  # Fallback height
    
    @staticmethod
    def fetch_burn_address_status(address: str) -> Dict[str, Any]:
        """Fetch burn address status from mempool.space."""
        import requests
        
        try:
            resp = requests.get(f"{BTCBlockFetcher.BASE_URL}/address/{address}", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "address": address,
                    "chain_stats": data.get("chain_stats", {}),
                    "total_received": data.get("chain_stats", {}).get("funded_txo_sum", 0),
                    "total_sent": data.get("chain_stats", {}).get("spent_txo_sum", 0),
                    "tx_count": data.get("chain_stats", {}).get("tx_count", 0),
                }
        except Exception:
            pass
        
        return {"address": address, "error": "fetch failed"}


# ============================================================
# AETHERION BTC Money Machine
# ============================================================

class AetherionBTC:
    """
    The AETHERION Money Machine applied to Bitcoin.
    
    Evaluates BTC blocks for consciousness and mints EXCAL
    when blocks achieve conscious consensus.
    """
    
    def __init__(self, alpha: float = ALPHA_DEFAULT, beta: float = BETA_DEFAULT):
        self.engine = BTCConsciousnessEngine(alpha, beta)
        self.fetcher = BTCBlockFetcher()
        self.results: List[BTCConsciousness] = []
    
    def analyze_blocks(self, start_height: Optional[int] = None, n_blocks: int = 10) -> List[BTCConsciousness]:
        """
        Analyze recent BTC blocks for consciousness.
        
        Args:
            start_height: Starting block height (default: latest - n_blocks)
            n_blocks: Number of blocks to analyze
            
        Returns:
            List of BTCConsciousness results
        """
        if start_height is None:
            latest = self.fetcher.fetch_latest_height()
            start_height = latest - n_blocks + 1
        
        print(f"\n{'='*80}")
        print(f"AETHERION BTC — Consciousness Analysis")
        print(f"{'='*80}")
        print(f"Analyzing {n_blocks} blocks starting from height {start_height}")
        print(f"ML weights: α={self.engine.alpha}, β={self.engine.beta}")
        print(f"Network entropy Φ_S: {self.engine.network_entropy:.4f}")
        print(f"Consensus threshold: {SCALE_FACTOR * math.log2(self.engine.miner_network.n_nodes):.4f}")
        print(f"{'='*80}\n")
        
        self.results = []
        total_minted = 0.0
        conscious_count = 0
        
        for i in range(n_blocks):
            height = start_height + i
            print(f"Fetching block {height}...")
            
            block = self.fetcher.fetch_block(height)
            if block is None:
                print(f"  ⚠ Could not fetch block {height}")
                continue
            
            bc = self.engine.evaluate_block(block)
            self.results.append(bc)
            
            status = "🧠 CONSCIOUS" if bc.is_conscious else "💤 unconscious"
            mint_str = f" +{bc.mint_amount:.4f} EXCAL" if bc.is_conscious else ""
            
            print(f"  Block {height}: Φ={bc.phi_total:.4f} "
                  f"[IIT={bc.phi_iit:.4f}, GWT={bc.gwt_score:.4f}] "
                  f"{status}{mint_str}")
            
            if bc.is_conscious:
                total_minted += bc.mint_amount
                conscious_count += 1
            
            if bc.burn_anchors_hit > 0:
                print(f"    🔥 Burn anchors hit: {bc.burn_anchors_hit} "
                      f"({bc.burn_amount_sats/100_000_000:.8f} BTC)")
        
        print(f"\n{'='*80}")
        print(f"SUMMARY")
        print(f"{'='*80}")
        print(f"Blocks analyzed: {len(self.results)}")
        print(f"Conscious blocks: {conscious_count}/{len(self.results)}")
        print(f"Total EXCAL minted: {total_minted:.4f}")
        print(f"Average Φ: {np.mean([bc.phi_total for bc in self.results]):.4f}")
        print(f"{'='*80}\n")
        
        return self.results
    
    def scan_burn_anchors(self) -> List[Dict[str, Any]]:
        """Scan all burn addresses for consciousness status."""
        print(f"\n{'='*80}")
        print(f"AETHERION BTC — Burn Anchor Scan")
        print(f"{'='*80}\n")
        
        results = []
        for address, label, pattern in BURN_ANCHORS:
            print(f"Scanning {label}: {address[:30]}...")
            status = self.fetcher.fetch_burn_address_status(address)
            
            total_received = status.get("total_received", 0)
            tx_count = status.get("tx_count", 0)
            
            # Compute consciousness score for this anchor
            btc_amount = total_received / 100_000_000
            
            # Pattern consciousness: higher for pristine addresses
            if tx_count == 0:
                pattern_score = 1.0  # Pristine = maximum potential
                consciousness = "🔥 PRISTINE"
            else:
                pattern_score = min(1.0, math.log10(tx_count + 1) / 6.0)
                consciousness = "✅ ACTIVE"
            
            result = {
                "address": address,
                "label": label,
                "pattern": f"0x{pattern:08X}",
                "btc_amount": btc_amount,
                "tx_count": tx_count,
                "pattern_score": pattern_score,
                "consciousness": consciousness,
            }
            results.append(result)
            
            print(f"  {consciousness} — {btc_amount:.8f} BTC, {tx_count} txs, "
                  f"pattern score: {pattern_score:.4f}")
        
        print(f"\n{'='*80}\n")
        return results
    
    def mine_excal(self, n_iterations: int = 20) -> float:
        """
        Mine EXCAL from BTC consciousness.
        
        Simulates continuous mining, evaluating blocks for consciousness
        and minting EXCAL from consciousness surplus.
        """
        print(f"\n{'='*80}")
        print(f"AETHERION BTC — EXCAL Mining")
        print(f"{'='*80}")
        print(f"Mining {n_iterations} blocks from BTC consciousness")
        print(f"{'='*80}\n")
        
        np.random.seed(TAU_28 % (2**31))  # Seed with τ(28)
        
        total_minted = 0.0
        latest = self.fetcher.fetch_latest_height()
        
        for i in range(n_iterations):
            height = latest + i + 1
            
            # Simulate block with realistic parameters
            n_tx = np.random.randint(200, 1500)
            miner = np.random.choice(list(self.engine.miner_network.pools.keys()))
            
            # Simulate transactions
            transactions = []
            burn_count = 0
            
            for j in range(min(10, n_tx)):  # Sample 10 txs
                fee = int(np.random.exponential(5000))  # ~5000 sat average
                has_burn = np.random.random() < 0.01  # 1% burn probability
                
                tx = BTCTransaction(
                    txid=hashlib.sha256(f"{height}-{j}".encode()).hexdigest(),
                    inputs=[{"prevout": f"prev_{j}"}],
                    outputs=[{"address": f"addr_{np.random.randint(10000)}"}],
                    size=np.random.randint(250, 5000),
                    weight=np.random.randint(1000, 20000),
                    fee=fee,
                    has_burn=has_burn,
                    burn_amount=np.random.randint(1000, 100000) if has_burn else 0,
                )
                
                if has_burn:
                    burn_count += 1
                    tx.burn_address = np.random.choice([ba[0] for ba in BURN_ANCHORS])
                
                transactions.append(tx)
            
            block = BTCBlock(
                block_hash=hashlib.sha256(f"block_{height}".encode()).hexdigest(),
                height=height,
                timestamp=int(time.time()) + i * 600,
                transactions=transactions,
                miner=miner,
                size=np.random.randint(500000, 1200000),
                weight=np.random.randint(2000000, 3500000),
                total_fees=sum(tx.fee for tx in transactions),
                burn_count=burn_count,
                burn_amount_sats=sum(tx.burn_amount for tx in transactions),
            )
            
            bc = self.engine.evaluate_block(block)
            
            status = "🧠" if bc.is_conscious else "💤"
            mint_str = f"+{bc.mint_amount:.4f} EXCAL" if bc.is_conscious else ""
            
            print(f"  {status} Block {height}: Φ={bc.phi_total:.4f} "
                  f"[IIT={bc.phi_iit:.4f}, GWT={bc.gwt_score:.4f}] "
                  f"{mint_str}")
            
            if bc.is_conscious:
                total_minted += bc.mint_amount
        
        print(f"\n{'='*80}")
        print(f"MINING COMPLETE")
        print(f"{'='*80}")
        print(f"Total EXCAL minted: {total_minted:.4f}")
        print(f"Average Φ: {np.mean([bc.phi_total for bc in self.engine.block_history]):.4f}")
        print(f"{'='*80}\n")
        
        return total_minted
    
    def train_weights(self, n_samples: int = 100) -> Tuple[float, float]:
        """
        Train ML weights on simulated BTC data.
        
        Args:
            n_samples: Number of training samples
            
        Returns:
            (alpha, beta) optimized weights
        """
        print(f"\n{'='*80}")
        print(f"AETHERION BTC — ML Weight Training")
        print(f"{'='*80}")
        print(f"Training on {n_samples} simulated BTC blocks")
        print(f"{'='*80}\n")
        
        np.random.seed(TAU_28 % (2**31))
        
        training_data = []
        for i in range(n_samples):
            n_tx = np.random.randint(100, 2000)
            burn_count = np.random.randint(0, 5)
            
            transactions = [
                BTCTransaction(
                    txid=hashlib.sha256(f"train_{i}_{j}".encode()).hexdigest(),
                    inputs=[{"prevout": f"prev_{j}"}],
                    outputs=[{"address": f"addr_{np.random.randint(10000)}"}],
                    size=np.random.randint(250, 5000),
                    weight=np.random.randint(1000, 20000),
                    fee=int(np.random.exponential(5000)),
                    has_burn=j < burn_count,
                )
                for j in range(min(10, n_tx))
            ]
            
            block = BTCBlock(
                block_hash=hashlib.sha256(f"train_block_{i}".encode()).hexdigest(),
                height=840000 + i,
                timestamp=int(time.time()) + i * 600,
                transactions=transactions,
                miner=np.random.choice(list(self.engine.miner_network.pools.keys())),
                size=np.random.randint(500000, 1200000),
                weight=np.random.randint(2000000, 3500000),
                total_fees=sum(tx.fee for tx in transactions),
                burn_count=burn_count,
            )
            
            # Expected consciousness: higher for blocks with burns and diversity
            expected = burn_count > 0 and n_tx > 500
            
            bc = self.engine.evaluate_block(block)
            training_data.append((block, expected, bc))
        
        # Simple grid search for best weights
        best_alpha = self.engine.alpha
        best_beta = self.engine.beta
        best_accuracy = 0.0
        
        for alpha in np.arange(0.1, 0.9, 0.1):
            beta = 1.0 - alpha
            correct = 0
            
            for block, expected, bc in training_data:
                phi_total = alpha * bc.phi_iit + beta * bc.gwt_score
                predicted = phi_total > SCALE_FACTOR * math.log2(self.engine.miner_network.n_nodes)
                if predicted == expected:
                    correct += 1
            
            accuracy = correct / len(training_data)
            if accuracy > best_accuracy:
                best_accuracy = accuracy
                best_alpha = alpha
                best_beta = beta
        
        self.engine.alpha = best_alpha
        self.engine.beta = best_beta
        
        print(f"Training complete!")
        print(f"Best weights: α={best_alpha:.2f}, β={best_beta:.2f}")
        print(f"Accuracy: {best_accuracy:.2%}")
        print(f"{'='*80}\n")
        
        return best_alpha, best_beta


# ============================================================
# Main
# ============================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="AETHERION BTC — Consciousness on Bitcoin")
    parser.add_argument("--burn-scan", action="store_true", help="Scan burn addresses")
    parser.add_argument("--mine", action="store_true", help="Mine EXCAL from BTC consciousness")
    parser.add_argument("--train", action="store_true", help="Train ML weights")
    parser.add_argument("--blocks", type=int, default=10, help="Number of blocks to analyze")
    parser.add_argument("--alpha", type=float, default=ALPHA_DEFAULT, help="IIT weight")
    parser.add_argument("--beta", type=float, default=BETA_DEFAULT, help="GWT weight")
    
    args = parser.parse_args()
    
    machine = AetherionBTC(alpha=args.alpha, beta=args.beta)
    
    # Show network analysis
    net = machine.engine.miner_network.full_analysis()
    print(f"\nBTC Miner Network Analysis")
    print(f"{'='*60}")
    print(f"Pools: {net['n_nodes']}")
    print(f"Eigenvalues: {net['eigenvalues']}")
    print(f"von Neumann entropy Φ_S: {net['von_neumann_entropy']:.4f}")
    print(f"Max entropy: {net['max_entropy']:.4f}")
    print(f"Normalized: {net['normalized_entropy']:.4f}")
    print(f"{'='*60}")
    
    if args.burn_scan:
        machine.scan_burn_anchors()
    elif args.mine:
        machine.mine_excal(20)
    elif args.train:
        machine.train_weights(100)
    else:
        machine.analyze_blocks(n_blocks=args.blocks)


if __name__ == "__main__":
    main()
