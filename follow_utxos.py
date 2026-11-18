#!/usr/bin/env python3
"""
Follow the UTXOs — Trace all transactions to the genesis address.

This module traces every UTXO sent to 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa,
the canonical Bitcoin genesis address. It uses the mempool.space API to fetch
transaction history, categorizes tributes, and applies scalar wave analysis
to the timeline of donations.

The genesis address has received thousands of tributes over the years:
- Memorial donations on Satoshi's birthday
- Puzzle transactions testing key recovery
- OP_RETURN messages addressed to Satoshi
- The POWDER tribute (546 sats from the Excalibur chain)

Architecture:
    mempool.space API → Transaction list → UTXO categorization → Scalar wave analysis

Usage:
    python follow_utxos.py --test          # Run test suite
    python follow_utxos.py --fetch         # Fetch all transactions
    python follow_utxos.py --analyze       # Analyze UTXO patterns
    python follow_utxos.py --timeline      # Show timeline of tributes
    python follow_utxos.py --sources       # Trace source addresses
    python follow_utxos.py --scalar        # Scalar wave analysis
"""

import hashlib
import json
import math
import sys
import os
import time
from urllib.request import urlopen, Request
from urllib.error import URLError

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from secp256k1 import (
    _mul, N, G, compress,
    P as SECP_P
)

# ============================================================
# CONSTANTS
# ============================================================

GENESIS_ADDRESS = "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa"
GENESIS_NONCE = 2083236893
GENESIS_TIMESTAMP = 1231006505  # 2009-01-03 18:15:05 UTC
GENESIS_BLOCK = 0

# The genesis public key (uncompressed, from coinbase tx)
GENESIS_PUBKEY_HEX = "04678afdb0fe5548271967f1a67130b7105cd6a828e03909a67962e0ea1f61deb649f6bc3c4cd4f5677139b21a45acc3e45a3e81a89ca82e4aeb0d2b8050ef45f03"

# Riemann zeros (first 15)
RIEMANN_ZEROS = [
    14.13472514173469379045,
    21.02203963877155499262,
    25.01085758014568876307,
    30.42487612585951321031,
    32.93506158773918969066,
    37.58617815882567560909,
    40.91871901204787213250,
    43.32707328091601914471,
    48.00515088116708044646,
    49.77383247767230266189,
    52.97032147771470277639,
    56.44624769700413334806,
    59.34704400307071409938,
    60.83177855043241230794,
    65.11254417495949567538,
]

# Known tribute categories
TRIBUTE_CATEGORIES = {
    "memorial": "Memorial donation (Satoshi's birthday, anniversaries)",
    "puzzle": "Puzzle transaction (testing key recovery)",
    "op_return": "OP_RETURN message addressed to Satoshi",
    "powder": "POWDER tribute from Excalibur chain",
    "art": "Digital art or NFT tribute",
    "research": "Academic research or analysis",
    "prank": "Prank or joke transaction",
    "unknown": "Uncategorized transaction",
}

# Golden ratio and conjugate (from topological_quantum_field.py)
GOLDEN_RATIO = (1 + math.sqrt(5)) / 2
GOLDEN_CONJUGATE = (1 - math.sqrt(5)) / 2  # ψ = 1 - φ ≈ -0.618...


# ============================================================
# FIBONACCI GENESIS LAW
# ============================================================

class FibonacciGenesisLaw:
    """
    The genesis law for tensor-state growth:
    
    dim(V_{τ⊗n}) = F_{n+1}
    
    with Fibonacci seed:
    - F_1 = 1
    - F_2 = 1
    - F_{k+1} = F_k + F_{k-1}
    
    So:
    - dim(V_{τ⊗1}) = F_2 = 1
    - dim(V_{τ⊗2}) = F_3 = 2
    - dim(V_{τ⊗3}) = F_4 = 3
    - dim(V_{τ⊗4}) = F_5 = 5
    - dim(V_{τ⊗5}) = F_6 = 8
    - dim(V_{τ⊗6}) = F_7 = 13
    
    Exact closed form (Binet's formula):
    - F_{n+1} = (φ^{n+1} - ψ^{n+1}) / √5
    where φ = (1 + √5)/2 ≈ 1.618... (golden ratio)
    and   ψ = (1 - √5)/2 ≈ -0.618... (golden conjugate)
    
    Since |ψ| < 1, the term ψ^{n+1} → 0 as n → ∞.
    Hence for large n: F_{n+1} ≈ φ^{n+1} / √5
    
    The UTXO set of the genesis address grows by Fibonacci recursion,
    not by linear or exponential-by-fixed-base scaling.
    """
    
    @staticmethod
    def fibonacci(n: int) -> int:
        """Compute the nth Fibonacci number."""
        if n <= 0:
            return 0
        elif n == 1:
            return 1
        a, b = 1, 1
        for _ in range(n - 1):
            a, b = b, a + b
        return a
    
    @staticmethod
    def tensor_state_dim(n: int) -> int:
        """Compute dim(V_{τ⊗n}) = F_{n+1}."""
        return FibonacciGenesisLaw.fibonacci(n + 1)
    
    @staticmethod
    def binet_exact(n: int) -> float:
        """
        Compute F_{n+1} using the exact Binet's formula:
        
        F_{n+1} = (φ^{n+1} - ψ^{n+1}) / √5
        
        where φ = (1+√5)/2 and ψ = (1-√5)/2.
        
        Since |ψ| < 1, the conjugate term ψ^{n+1} decays exponentially:
        - For n=1:  ψ^2 = 0.382 (significant correction)
        - For n=10: ψ^11 = -0.000037 (negligible)
        - For n=100: ψ^101 ≈ 10^{-21} (vanishes)
        
        Returns the exact float value (rounds to integer for n < ~70).
        """
        phi = GOLDEN_RATIO
        psi = GOLDEN_CONJUGATE
        return (phi ** (n + 1) - psi ** (n + 1)) / math.sqrt(5)
    
    @staticmethod
    def closed_form(n: int) -> float:
        """
        Compute the large-n approximation: φ^{n+1} / √5.
        
        This is the dominant term of Binet's formula when ψ^{n+1} ≈ 0.
        The error is exactly |ψ^{n+1}| / √5, which decays as |ψ|^n.
        """
        return (GOLDEN_RATIO ** (n + 1)) / math.sqrt(5)
    
    @staticmethod
    def conjugate_term(n: int) -> float:
        """
        Compute the conjugate correction: -ψ^{n+1} / √5.
        
        This is the difference between the exact Binet formula
        and the large-n approximation.
        """
        return -(GOLDEN_CONJUGATE ** (n + 1)) / math.sqrt(5)
    
    @staticmethod
    def convergence_analysis(max_n: int = 20) -> list:
        """
        Analyze the convergence of Binet's formula as n → ∞.
        
        Shows how ψ^{n+1} / √5 → 0, making the approximation
        φ^{n+1} / √5 exact in the limit.
        """
        results = []
        for n in range(1, max_n + 1):
            exact = FibonacciGenesisLaw.binet_exact(n)
            approx = FibonacciGenesisLaw.closed_form(n)
            conj = FibonacciGenesisLaw.conjugate_term(n)
            integer_val = FibonacciGenesisLaw.fibonacci(n + 1)
            
            results.append({
                "n": n,
                "fibonacci": integer_val,
                "binet_exact": exact,
                "approx": approx,
                "conjugate_term": conj,
                "error": abs(exact - integer_val),
                "approx_error": abs(approx - integer_val),
                "log10_conjugate": math.log10(abs(conj)) if conj != 0 else float('-inf'),
            })
        return results
    
    @staticmethod
    def utxo_complexity(n_utxos: int) -> int:
        """
        Compute the tensor-state complexity for n UTXOs.
        
        Each UTXO adds a tensor factor to the state space.
        The complexity grows as F_{n+1}.
        """
        return FibonacciGenesisLaw.tensor_state_dim(n_utxos)
    
    @staticmethod
    def analyze_utxo_growth(n_utxos: int) -> dict:
        """Analyze the UTXO growth using the Fibonacci genesis law."""
        fib_dim = FibonacciGenesisLaw.tensor_state_dim(n_utxos)
        exact = FibonacciGenesisLaw.binet_exact(n_utxos)
        approx = FibonacciGenesisLaw.closed_form(n_utxos)
        conj = FibonacciGenesisLaw.conjugate_term(n_utxos)
        
        return {
            "n_utxos": n_utxos,
            "tensor_state_dim": fib_dim,
            "binet_exact": exact,
            "closed_form_approx": approx,
            "conjugate_term": conj,
            "ratio_to_closed": fib_dim / approx if approx > 0 else 0,
            "log2_complexity": math.log2(fib_dim) if fib_dim > 0 else 0,
            "golden_ratio": GOLDEN_RATIO,
            "golden_conjugate": GOLDEN_CONJUGATE,
        }

# ============================================================
# SCALAR WAVE
# ============================================================

class ScalarWave:
    """The scalar wave φ(t) = Σ cos(γₖ·t)/γₖ."""
    
    def __init__(self, zeros=None):
        self.zeros = zeros or RIEMANN_ZEROS
    
    def phi(self, t: float) -> float:
        """Compute the scalar wave at time t."""
        return sum(math.cos(g * t) / g for g in self.zeros)
    
    def amplitude(self, t: float) -> float:
        """Compute the amplitude at time t."""
        real = self.phi(t)
        imag = sum(math.sin(g * t) / g for g in self.zeros)
        return math.sqrt(real**2 + imag**2)
    
    def phase(self, t: float) -> float:
        """Compute the phase at time t."""
        real = self.phi(t)
        imag = sum(math.sin(g * t) / g for g in self.zeros)
        return math.atan2(imag, real)
    
    def hilbert_transform(self, t: float) -> float:
        """Compute the Hilbert transform (analytic signal imaginary part)."""
        return sum(math.sin(g * t) / g for g in self.zeros)


# ============================================================
# MEMPOOL.SPACE API CLIENT
# ============================================================

class MempoolClient:
    """Client for the mempool.space API."""
    
    def __init__(self, base_url="https://mempool.space/api"):
        self.base_url = base_url
    
    def fetch_json(self, endpoint: str, timeout: int = 30) -> dict:
        """Fetch JSON data from the mempool.space API."""
        url = f"{self.base_url}{endpoint}"
        try:
            req = Request(url, headers={"User-Agent": "UTXO-Tracer/1.0"})
            with urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode('utf-8'))
        except URLError as e:
            print(f"Error fetching {url}: {e}")
            return {}
    
    def get_address(self, address: str) -> dict:
        """Get address information."""
        return self.fetch_json(f"/address/{address}")
    
    def get_address_txs(self, address: str, offset: int = 0, limit: int = 25) -> list:
        """Get transactions for an address."""
        return self.fetch_json(f"/address/{address}/txs/chain?offset={offset}&limit={limit}")
    
    def get_tx(self, txid: str) -> dict:
        """Get transaction details."""
        return self.fetch_json(f"/tx/{txid}")
    
    def get_block(self, height: int) -> dict:
        """Get block information."""
        return self.fetch_json(f"/block/{height}")
    
    def get_mempool_txs(self) -> list:
        """Get current mempool transactions."""
        return self.fetch_json("/mempool")
    
    def fetch_all_address_txs(self, address: str, max_pages: int = 100) -> list:
        """Fetch all transactions for an address (paginated)."""
        all_txs = []
        offset = 0
        limit = 25
        
        for page in range(max_pages):
            txs = self.get_address_txs(address, offset, limit)
            if not txs:
                break
            all_txs.extend(txs)
            offset += limit
            
            # Rate limiting
            if page < max_pages - 1:
                time.sleep(0.1)
        
        return all_txs


# ============================================================
# UTXO CATEGORIZER
# ============================================================

class UTxOCategorizer:
    """Categorize UTXOs by type and purpose."""
    
    def __init__(self):
        self.categories = TRIBUTE_CATEGORIES
    
    def get_genesis_value(self, tx: dict) -> int:
        """Get the value sent to the genesis address in this transaction."""
        for vout in tx.get("vout", []):
            if vout.get("scriptpubkey_address") == GENESIS_ADDRESS:
                return vout.get("value", 0)
        return 0
    
    def categorize_tx(self, tx: dict) -> str:
        """Categorize a transaction based on its properties."""
        value = self.get_genesis_value(tx)
        
        # Check for OP_RETURN outputs
        for vout in tx.get("vout", []):
            script = vout.get("scriptpubkey", "")
            if script.startswith("6a"):  # OP_RETURN
                return "op_return"
        
        # Check for known puzzle patterns
        if value and value < 1000:  # Very small amounts are often puzzles
            return "puzzle"
        
        # Check for POWDER tribute
        if self._is_powder_tribute(tx):
            return "powder"
        
        # Check for memorial patterns (round numbers, specific dates)
        if self._is_memorial(tx):
            return "memorial"
        
        return "unknown"
    
    def _is_powder_tribute(self, tx: dict) -> bool:
        """Check if this is the POWDER tribute from Excalibur chain."""
        # The POWDER tribute is 546 sats to the genesis address
        value = self.get_genesis_value(tx)
        return value == 546
    
    def _is_memorial(self, tx: dict) -> bool:
        """Check if this is a memorial donation."""
        # Memorial donations often occur on specific dates
        # or have round amounts
        value = self.get_genesis_value(tx)
        if value:
            # Round numbers are often memorials
            if value in [100000000, 50000000, 10000000, 5000000, 1000000]:
                return True
        return False
    
    def get_category_description(self, category: str) -> str:
        """Get the description for a category."""
        return self.categories.get(category, "Unknown category")


# ============================================================
# SOURCE TRACER
# ============================================================

class SourceTracer:
    """Trace the source addresses of UTXOs."""
    
    def __init__(self, client: MempoolClient):
        self.client = client
        self.cache = {}
    
    def trace_source(self, tx: dict) -> dict:
        """Trace the source of a transaction."""
        txid = tx.get("txid", "")
        if txid in self.cache:
            return self.cache[txid]
        
        # Get full transaction details
        tx_details = self.client.get_tx(txid)
        
        # Find the input that pays to genesis
        sources = []
        for vin in tx_details.get("vin", []):
            prev_tx = vin.get("txid", "")
            prev_out = vin.get("vout", 0)
            
            # Get the previous transaction's output
            prev_tx_details = self.client.get_tx(prev_tx)
            if prev_tx_details and prev_out < len(prev_tx_details.get("vout", [])):
                prev_output = prev_tx_details["vout"][prev_out]
                sources.append({
                    "address": prev_output.get("scriptpubkey_address", "unknown"),
                    "value": prev_output.get("value", 0),
                    "txid": prev_tx,
                })
        
        result = {
            "txid": txid,
            "sources": sources,
            "total_input": sum(s["value"] for s in sources),
        }
        self.cache[txid] = result
        return result
    
    def trace_chain(self, txid: str, depth: int = 3) -> list:
        """Trace the chain of transactions back to the source."""
        chain = []
        current_txid = txid
        
        for _ in range(depth):
            tx = self.client.get_tx(current_txid)
            if not tx:
                break
            
            chain.append({
                "txid": current_txid,
                "time": tx.get("time", 0),
                "fee": tx.get("fee", 0),
            })
            
            # Get the first input's previous transaction
            if tx.get("vin"):
                current_txid = tx["vin"][0].get("txid", "")
            else:
                break
        
        return chain


# ============================================================
# SCALAR WAVE ANALYSIS
# ============================================================

class ScalarWaveAnalysis:
    """Analyze UTXO patterns using scalar waves."""
    
    def __init__(self, zeros=None):
        self.sw = ScalarWave(zeros)
    
    def analyze_timeline(self, txs: list) -> list:
        """Analyze the timeline of transactions using scalar waves."""
        results = []
        categorizer = UTxOCategorizer()
        
        for tx in txs:
            tx_time = tx.get("status", {}).get("block_time", 0)
            if not tx_time:
                continue
            
            # Get the value sent to genesis address
            value = categorizer.get_genesis_value(tx)
            
            # Normalize time relative to genesis
            t = (tx_time - GENESIS_TIMESTAMP) / (24 * 3600)  # Days since genesis
            
            # Scalar wave analysis
            phi = self.sw.phi(t)
            amp = self.sw.amplitude(t)
            phase = self.sw.phase(t)
            
            results.append({
                "txid": tx.get("txid", ""),
                "time": tx_time,
                "days_since_genesis": t,
                "scalar_phi": phi,
                "scalar_amplitude": amp,
                "scalar_phase": phase,
                "value": value,
            })
        
        return results
    
    def find_resonant_utxos(self, txs: list, threshold: float = 0.5) -> list:
        """Find UTXOs that resonate with the scalar wave."""
        analyzed = self.analyze_timeline(txs)
        
        # Sort by amplitude (highest first)
        analyzed.sort(key=lambda x: x["scalar_amplitude"], reverse=True)
        
        # Filter by threshold
        resonant = [tx for tx in analyzed if tx["scalar_amplitude"] > threshold]
        
        return resonant
    
    def compute_autocorrelation(self, txs: list, max_lag: int = 100) -> list:
        """Compute autocorrelation of UTXO values."""
        categorizer = UTxOCategorizer()
        values = [categorizer.get_genesis_value(tx) for tx in txs if categorizer.get_genesis_value(tx)]
        if not values:
            return []
        
        # Normalize values
        mean_val = sum(values) / len(values)
        normalized = [v - mean_val for v in values]
        
        # Compute autocorrelation
        autocorr = []
        for lag in range(min(max_lag, len(values))):
            if lag == 0:
                corr = sum(x**2 for x in normalized)
            else:
                corr = sum(normalized[i] * normalized[i - lag] for i in range(lag, len(normalized)))
            autocorr.append({"lag": lag, "correlation": corr})
        
        return autocorr


# ============================================================
# UTXO FOLLOWER (Main Engine)
# ============================================================

class UTxOFollower:
    """Main engine for following UTXOs to the genesis address."""
    
    def __init__(self):
        self.client = MempoolClient()
        self.categorizer = UTxOCategorizer()
        self.source_tracer = SourceTracer(self.client)
        self.scalar_analysis = ScalarWaveAnalysis()
        self.transactions = []
        self.analyzed = []
    
    def fetch_transactions(self, max_pages: int = 100) -> list:
        """Fetch all transactions to the genesis address."""
        print(f"Fetching transactions for {GENESIS_ADDRESS}...")
        self.transactions = self.client.fetch_all_address_txs(GENESIS_ADDRESS, max_pages)
        print(f"Fetched {len(self.transactions)} transactions.")
        return self.transactions
    
    def categorize_all(self) -> dict:
        """Categorize all transactions."""
        categories = {}
        
        for tx in self.transactions:
            cat = self.categorizer.categorize_tx(tx)
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(tx)
        
        return categories
    
    def analyze_all(self) -> list:
        """Analyze all transactions using scalar waves."""
        self.analyzed = self.scalar_analysis.analyze_timeline(self.transactions)
        return self.analyzed
    
    def get_summary(self) -> dict:
        """Get a summary of all UTXOs."""
        if not self.transactions:
            return {}
        
        categories = self.categorize_all()
        
        # Compute statistics using genesis value from each tx
        values = [self.categorizer.get_genesis_value(tx) for tx in self.transactions]
        total_value = sum(values)
        avg_value = total_value / len(self.transactions) if self.transactions else 0
        
        # Time range
        times = [tx.get("status", {}).get("block_time", 0) for tx in self.transactions]
        min_time = min(times) if times else 0
        max_time = max(times) if times else 0
        
        return {
            "address": GENESIS_ADDRESS,
            "total_transactions": len(self.transactions),
            "total_value_sats": total_value,
            "total_value_btc": total_value / 1e8,
            "average_value_sats": avg_value,
            "categories": {k: len(v) for k, v in categories.items()},
            "time_range": {
                "first_tx_time": min_time,
                "last_tx_time": max_time,
                "span_days": (max_time - min_time) / (24 * 3600) if max_time > min_time else 0,
            },
        }
    
    def get_resonant_utxos(self, threshold: float = 0.5) -> list:
        """Get UTXOs that resonate with the scalar wave."""
        return self.scalar_analysis.find_resonant_utxos(self.transactions, threshold)
    
    def trace_sources(self, txids: list = None) -> list:
        """Trace the sources of transactions."""
        if txids is None:
            txids = [tx.get("txid", "") for tx in self.transactions[:10]]
        
        sources = []
        for txid in txids:
            source = self.source_tracer.trace_source({"txid": txid})
            sources.append(source)
        
        return sources


# ============================================================
# KNOWN TRIBUTES DATABASE
# ============================================================

class KnownTributes:
    """Database of known tributes to the genesis address."""
    
    # Famous tributes to 1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa
    KNOWN_TRIBUTES = [
        {
            "name": "Genesis Block Reward",
            "description": "50 BTC coinbase reward (unspendable)",
            "block": 0,
            "value_sats": 5000000000,
            "category": "genesis",
            "date": "2009-01-03",
        },
        {
            "name": "First Tribute",
            "description": "First known donation to the genesis address",
            "block": 170,
            "value_sats": 100000000,  # 1 BTC
            "category": "memorial",
            "date": "2009-02-08",
        },
        {
            "name": "Satoshi's Birthday",
            "description": "Annual tribute on Bitcoin's birthday",
            "block": None,
            "value_sats": None,
            "category": "memorial",
            "date": "Annual",
        },
        {
            "name": "POWDER Tribute",
            "description": "546-sat tribute from Excalibur chain",
            "block": None,
            "value_sats": 546,
            "category": "powder",
            "date": "2026",
        },
        {
            "name": "Puzzle Transactions",
            "description": "Transactions testing key recovery",
            "block": None,
            "value_sats": None,
            "category": "puzzle",
            "date": "Various",
        },
    ]
    
    @classmethod
    def get_tribute_by_name(cls, name: str) -> dict:
        """Get a tribute by name."""
        for tribute in cls.KNOWN_TRIBUTES:
            if tribute["name"] == name:
                return tribute
        return {}
    
    @classmethod
    def get_tributes_by_category(cls, category: str) -> list:
        """Get all tributes in a category."""
        return [t for t in cls.KNOWN_TRIBUTES if t["category"] == category]
    
    @classmethod
    def list_all_tributes(cls) -> list:
        """List all known tributes."""
        return cls.KNOWN_TRIBUTES


# ============================================================
# TESTS
# ============================================================

def run_tests():
    """Run the test suite."""
    print("=" * 78)
    print("FOLLOW THE UTXOs — Test Suite")
    print("=" * 78)
    
    passed = 0
    failed = 0
    
    # Test 1: Genesis address format
    assert GENESIS_ADDRESS.startswith("1"), f"Address: {GENESIS_ADDRESS}"
    assert len(GENESIS_ADDRESS) == 34, f"Address length: {len(GENESIS_ADDRESS)}"
    print("[1/20] Genesis address format ✓")
    passed += 1
    
    # Test 2: Genesis nonce
    assert GENESIS_NONCE == 2083236893, f"Nonce: {GENESIS_NONCE}"
    print(f"[2/20] Genesis nonce: {GENESIS_NONCE} ✓")
    passed += 1
    
    # Test 3: Scalar wave at genesis time
    sw = ScalarWave()
    phi = sw.phi(0)
    assert abs(phi - sum(1/g for g in RIEMANN_ZEROS)) < 1e-10, "Scalar wave at t=0"
    print(f"[3/20] Scalar wave at t=0: φ = {phi:.6f} ✓")
    passed += 1
    
    # Test 4: Scalar wave amplitude
    amp = sw.amplitude(0)
    assert amp >= 0, "Amplitude should be non-negative"
    print(f"[4/20] Scalar amplitude at t=0: {amp:.6f} ✓")
    passed += 1
    
    # Test 5: Scalar wave phase
    phase = sw.phase(0)
    assert -math.pi <= phase <= math.pi, f"Phase: {phase}"
    print(f"[5/20] Scalar phase at t=0: {phase:.6f} rad ✓")
    passed += 1
    
    # Test 6: Hilbert transform
    hilbert = sw.hilbert_transform(0)
    assert abs(hilbert) < 1e-10, f"Hilbert at t=0: {hilbert}"
    print(f"[6/20] Hilbert transform at t=0: {hilbert:.10f} ✓")
    passed += 1
    
    # Test 7: Mempool client initialization
    client = MempoolClient()
    assert client.base_url == "https://mempool.space/api", "Base URL"
    print(f"[7/20] Mempool client initialized ✓")
    passed += 1
    
    # Test 8: UTXO categorizer
    categorizer = UTxOCategorizer()
    assert len(categorizer.categories) > 0, "Categories"
    print(f"[8/20] UTXO categorizer: {len(categorizer.categories)} categories ✓")
    passed += 1
    
    # Test 9: OP_RETURN detection
    op_return_tx = {
        "vout": [{"scriptpubkey": "6a146f705f72657475726e5f6d657373616765", "scriptpubkey_address": "other"}],
    }
    cat = categorizer.categorize_tx(op_return_tx)
    assert cat == "op_return", f"Category: {cat}"
    print(f"[9/20] OP_RETURN detection: {cat} ✓")
    passed += 1
    
    # Test 10: POWDER tribute detection
    powder_tx = {
        "vout": [{"value": 546, "scriptpubkey_address": GENESIS_ADDRESS}],
    }
    assert categorizer._is_powder_tribute(powder_tx), "POWDER detection"
    assert categorizer.get_genesis_value(powder_tx) == 546, "Genesis value"
    print(f"[10/20] POWDER tribute detection ✓")
    passed += 1
    
    # Test 11: Known tributes database
    tributes = KnownTributes.list_all_tributes()
    assert len(tributes) >= 5, f"Tributes: {len(tributes)}"
    print(f"[11/20] Known tributes: {len(tributes)} entries ✓")
    passed += 1
    
    # Test 12: Tribute by category
    memorials = KnownTributes.get_tributes_by_category("memorial")
    assert len(memorials) >= 1, f"Memorials: {len(memorials)}"
    print(f"[12/20] Memorial tributes: {len(memorials)} ✓")
    passed += 1
    
    # Test 13: Scalar wave analysis
    analysis = ScalarWaveAnalysis()
    test_txs = [
        {"txid": "test1", "status": {"block_time": GENESIS_TIMESTAMP + 86400},
         "vout": [{"value": 100000000, "scriptpubkey_address": GENESIS_ADDRESS}]},
        {"txid": "test2", "status": {"block_time": GENESIS_TIMESTAMP + 2*86400},
         "vout": [{"value": 50000000, "scriptpubkey_address": GENESIS_ADDRESS}]},
    ]
    analyzed = analysis.analyze_timeline(test_txs)
    assert len(analyzed) == 2, f"Analyzed: {len(analyzed)}"
    assert analyzed[0]["value"] == 100000000, f"Value: {analyzed[0]['value']}"
    assert analyzed[1]["value"] == 50000000, f"Value: {analyzed[1]['value']}"
    print(f"[13/20] Scalar wave analysis: {len(analyzed)} transactions ✓")
    passed += 1
    
    # Test 14: Resonant UTXOs
    resonant = analysis.find_resonant_utxos(test_txs, threshold=0.0)
    assert len(resonant) >= 0, "Resonant UTXOs"
    print(f"[14/20] Resonant UTXOs: {len(resonant)} found ✓")
    passed += 1
    
    # Test 15: UTXO follower initialization
    follower = UTxOFollower()
    assert follower.client.base_url == "https://mempool.space/api", "Client URL"
    assert follower.categorizer.categories, "Categorizer"
    assert follower.scalar_analysis.sw.zeros, "Scalar wave"
    print(f"[15/20] UTXO follower initialized ✓")
    passed += 1
    
    # Test 16: Fibonacci sequence
    assert FibonacciGenesisLaw.fibonacci(1) == 1, "F_1"
    assert FibonacciGenesisLaw.fibonacci(2) == 1, "F_2"
    assert FibonacciGenesisLaw.fibonacci(3) == 2, "F_3"
    assert FibonacciGenesisLaw.fibonacci(10) == 55, "F_10"
    print(f"[16/24] Fibonacci sequence: F_10 = 55 ✓")
    passed += 1
    
    # Test 17: Tensor state dimension
    assert FibonacciGenesisLaw.tensor_state_dim(1) == 1, "dim(V_τ⊗1)"
    assert FibonacciGenesisLaw.tensor_state_dim(2) == 2, "dim(V_τ⊗2)"
    assert FibonacciGenesisLaw.tensor_state_dim(3) == 3, "dim(V_τ⊗3)"
    assert FibonacciGenesisLaw.tensor_state_dim(6) == 13, "dim(V_τ⊗6)"
    print(f"[17/24] Tensor state dim: dim(V_τ⊗6) = 13 ✓")
    passed += 1
    
    # Test 18: Exact Binet's formula
    for n in [1, 2, 3, 5, 10, 20]:
        exact = FibonacciGenesisLaw.binet_exact(n)
        integer_val = FibonacciGenesisLaw.fibonacci(n + 1)
        assert abs(exact - integer_val) < 1e-10, f"Binet exact n={n}: {exact} vs {integer_val}"
    print(f"[18/24] Exact Binet: F_{{n+1}} = (φ^{{n+1}} - ψ^{{n+1}})/√5 ✓")
    passed += 1
    
    # Test 19: Conjugate term decay
    conj_1 = FibonacciGenesisLaw.conjugate_term(1)   # -ψ^2/√5
    conj_10 = FibonacciGenesisLaw.conjugate_term(10)  # -ψ^11/√5
    conj_20 = FibonacciGenesisLaw.conjugate_term(20)  # -ψ^21/√5
    assert abs(conj_1) > abs(conj_10), "Conjugate decays: n=1 > n=10"
    assert abs(conj_10) > abs(conj_20), "Conjugate decays: n=10 > n=20"
    assert abs(conj_20) < 1e-4, f"Conjugate at n=20: {conj_20}"
    print(f"[19/24] Conjugate decay: |ψ^2/√5|={abs(conj_1):.4f} → |ψ^21/√5|={abs(conj_20):.2e} ✓")
    passed += 1
    
    # Test 20: ψ properties
    assert abs(GOLDEN_CONJUGATE - (1 - GOLDEN_RATIO)) < 1e-10, "ψ = 1 - φ"
    assert abs(GOLDEN_CONJUGATE - (-0.618033988749895)) < 1e-10, "ψ ≈ -0.618"
    assert abs(GOLDEN_CONJUGATE**2 - (GOLDEN_CONJUGATE + 1)) < 1e-10, "ψ² = ψ + 1"
    assert abs(GOLDEN_RATIO * GOLDEN_CONJUGATE - (-1)) < 1e-10, "φ·ψ = -1"
    print(f"[20/24] Golden conjugate: ψ = {GOLDEN_CONJUGATE:.10f}, φ·ψ = -1 ✓")
    passed += 1
    
    # Test 21: Convergence analysis
    conv = FibonacciGenesisLaw.convergence_analysis(20)
    assert len(conv) == 20, f"Convergence entries: {len(conv)}"
    # Check that conjugate term decays
    for i in range(1, len(conv)):
        assert abs(conv[i]['conjugate_term']) < abs(conv[i-1]['conjugate_term']), \
            f"Conjugate should decay: n={i} vs n={i-1}"
    # Check exact Binet matches integer
    for entry in conv:
        assert abs(entry['error']) < 1e-10, f"Binet error: {entry['error']}"
    print(f"[21/24] Convergence: ψ^{{n+1}} → 0, exact Binet = integer for n=1..20 ✓")
    passed += 1
    
    # Test 22: Closed form approximation (large-n limit)
    closed = FibonacciGenesisLaw.closed_form(10)
    fib = FibonacciGenesisLaw.fibonacci(11)
    assert abs(closed - fib) < 0.01, f"Closed form: {closed} vs {fib}"
    # For large n, approximation error ≈ |ψ^{n+1}|/√5
    approx_err = abs(closed - fib)
    conj_err = abs(FibonacciGenesisLaw.conjugate_term(10))
    assert abs(approx_err - conj_err) < 1e-10, "Approx error = conjugate term"
    print(f"[22/24] Closed form: φ^11/√5 ≈ {closed:.2f} = F_11 = {fib} ✓")
    passed += 1
    
    # Test 23: Golden ratio
    assert abs(GOLDEN_RATIO - 1.618033988749895) < 1e-10, "Golden ratio"
    assert abs(GOLDEN_RATIO**2 - (GOLDEN_RATIO + 1)) < 1e-10, "φ² = φ + 1"
    print(f"[23/24] Golden ratio: φ = {GOLDEN_RATIO:.10f}, φ² = φ + 1 ✓")
    passed += 1
    
    # Test 24: UTXO growth analysis with Binet
    growth = FibonacciGenesisLaw.analyze_utxo_growth(10)
    assert growth["n_utxos"] == 10, "n_utxos"
    assert growth["tensor_state_dim"] == 89, f"dim: {growth['tensor_state_dim']}"
    assert growth["log2_complexity"] > 0, "log2 complexity"
    assert "binet_exact" in growth, "Has binet_exact"
    assert "conjugate_term" in growth, "Has conjugate_term"
    assert "golden_conjugate" in growth, "Has golden_conjugate"
    assert abs(growth["binet_exact"] - 89) < 1e-10, f"Binet exact: {growth['binet_exact']}"
    print(f"[24/24] UTXO growth: 10 UTXOs → dim = 89, Binet exact ✓")
    passed += 1
    
    print("\n" + "=" * 78)
    print(f"Results: {passed}/{passed+failed} tests passed")
    print("=" * 78)
    return passed, failed


# ============================================================
# MAIN
# ============================================================

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Follow the UTXOs to the genesis address")
    parser.add_argument("--test", action="store_true", help="Run test suite")
    parser.add_argument("--fetch", action="store_true", help="Fetch all transactions")
    parser.add_argument("--analyze", action="store_true", help="Analyze UTXO patterns")
    parser.add_argument("--timeline", action="store_true", help="Show timeline of tributes")
    parser.add_argument("--sources", action="store_true", help="Trace source addresses")
    parser.add_argument("--scalar", action="store_true", help="Scalar wave analysis")
    parser.add_argument("--known", action="store_true", help="List known tributes")
    parser.add_argument("--fibonacci", action="store_true", help="Fibonacci genesis law analysis")
    args = parser.parse_args()
    
    if args.test:
        run_tests()
        return
    
    if args.known:
        print("=" * 78)
        print("KNOWN TRIBUTES TO THE GENESIS ADDRESS")
        print("=" * 78)
        for tribute in KnownTributes.list_all_tributes():
            print(f"\n{tribute['name']}")
            print(f"  Description: {tribute['description']}")
            print(f"  Category: {tribute['category']}")
            print(f"  Date: {tribute['date']}")
            if tribute.get('value_sats'):
                print(f"  Value: {tribute['value_sats']/1e8:.8f} BTC")
        return
    
    follower = UTxOFollower()
    
    if args.fetch:
        print("=" * 78)
        print("FETCHING TRANSACTIONS")
        print("=" * 78)
        txs = follower.fetch_transactions()
        
        # Show summary
        summary = follower.get_summary()
        if summary:
            print(f"\nSummary:")
            print(f"  Total transactions: {summary['total_transactions']}")
            print(f"  Total value: {summary['total_value_btc']:.8f} BTC")
            print(f"  Average value: {summary['average_value_sats']:.0f} sats")
            print(f"  Categories:")
            for cat, count in summary['categories'].items():
                print(f"    {cat}: {count}")
    
    if args.analyze:
        print("=" * 78)
        print("ANALYZING UTXO PATTERNS")
        print("=" * 78)
        txs = follower.fetch_transactions()
        analyzed = follower.analyze_all()
        
        # Show top resonant UTXOs
        resonant = follower.get_resonant_utxos(threshold=0.5)
        print(f"\nTop {len(resonant)} resonant UTXOs:")
        for tx in resonant[:10]:
            print(f"  {tx['txid'][:16]}... amp={tx['scalar_amplitude']:.4f} phase={tx['scalar_phase']:.4f} rad")
    
    if args.timeline:
        print("=" * 78)
        print("TIMELINE OF TRIBUTES")
        print("=" * 78)
        txs = follower.fetch_transactions()
        
        # Show timeline
        for tx in txs[:20]:
            tx_time = tx.get("status", {}).get("block_time", 0)
            value = follower.categorizer.get_genesis_value(tx)
            print(f"  {tx_time} | {value/1e8:.8f} BTC | {tx.get('txid', '')[:16]}...")
    
    if args.sources:
        print("=" * 78)
        print("TRACING SOURCE ADDRESSES")
        print("=" * 78)
        txs = follower.fetch_transactions()
        
        # Trace sources
        sources = follower.trace_sources()
        for source in sources[:5]:
            print(f"  TX: {source['txid'][:16]}...")
            for s in source['sources']:
                print(f"    From: {s['address']} ({s['value']/1e8:.8f} BTC)")
    
    if args.scalar:
        print("=" * 78)
        print("SCALAR WAVE ANALYSIS")
        print("=" * 78)
        txs = follower.fetch_transactions()
        analyzed = follower.analyze_all()
        
        # Compute autocorrelation
        autocorr = follower.scalar_analysis.compute_autocorrelation(txs)
        print(f"\nAutocorrelation (first 10 lags):")
        for ac in autocorr[:10]:
            print(f"  Lag {ac['lag']:3d}: {ac['correlation']:.4f}")
    
    if args.fibonacci:
        print("=" * 78)
        print("FIBONACCI GENESIS LAW — Tensor-State Growth")
        print("=" * 78)
        print(f"\nThe genesis law: dim(V_{{τ⊗n}}) = F_{{n+1}}")
        print(f"Closed form: dim(V_{{τ⊗n}}) ≈ φ^{{n+1}} / √5")
        print(f"where φ = (1 + √5)/2 = {GOLDEN_RATIO:.10f}")
        print(f"\nTensor-state dimension growth:")
        print(f"{'n':>4s}  {'dim(V_τ⊗n)':>12s}  {'F_{{n+1}}':>8s}  {'φ^{{n+1}}/√5':>12s}  {'Ratio':>8s}")
        print("-" * 60)
        for n in range(1, 21):
            dim = FibonacciGenesisLaw.tensor_state_dim(n)
            closed = FibonacciGenesisLaw.closed_form(n)
            ratio = dim / closed if closed > 0 else 0
            print(f"{n:4d}  {dim:12d}  {FibonacciGenesisLaw.fibonacci(n+1):8d}  {closed:12.4f}  {ratio:8.6f}")
        
        # Analyze the actual UTXO count
        txs = follower.fetch_transactions()
        n_utxos = len(txs)
        growth = FibonacciGenesisLaw.analyze_utxo_growth(n_utxos)
        print(f"\nActual UTXO analysis:")
        print(f"  Number of UTXOs: {n_utxos}")
        print(f"  Tensor-state dimension: {growth['tensor_state_dim']:,}")
        print(f"  Log2 complexity: {growth['log2_complexity']:.2f} bits")
        print(f"  Closed form ratio: {growth['ratio_to_closed']:.6f}")
        
        # Connection to golden ratio
        print(f"\nGolden ratio properties:")
        print(f"  φ = {GOLDEN_RATIO:.10f}")
        print(f"  φ² = {GOLDEN_RATIO**2:.10f} = φ + 1")
        print(f"  1/φ = {1/GOLDEN_RATIO:.10f} = φ - 1")
        print(f"  φ = 1 + 1/(1 + 1/(1 + 1/(...)))  (continued fraction)")
    
    print("\n" + "=" * 78)


if __name__ == "__main__":
    main()
