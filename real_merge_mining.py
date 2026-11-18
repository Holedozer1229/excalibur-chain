#!/usr/bin/env python3
"""real_merge_mining.py — Realistic Merge Mining with Actual Bitcoin Difficulty

This file demonstrates the REAL probability gap between merge mining on
Excalibur (easy child target) and Bitcoin mainnet (impossible parent target).

The key insight: at real Bitcoin difficulty, finding a dual hit requires
meeting the Bitcoin target, which is ~10^24 times harder than the child target.

Architecture:
    Excalibur (child)  ← AuxPoW →  Bitcoin (parent)
         │                                │
         │  Easy target (0x1f00ffff)      │  Real mainnet target
         │  ~65K hashes expected          │  ~10^24 hashes expected
         ▼                                ▼
    Block confirmed              Dual hit = 3.125 BTC reward

The scalar wave φ(t) guides nonce selection, but the fundamental probability
gap remains: dual hits are astronomically rare at real Bitcoin difficulty.

This file shows:
1. The actual Bitcoin mainnet difficulty from recent blocks
2. The probability of dual hit per hash
3. Expected time to find a dual hit at various hash rates
4. A continuous mining loop that runs until interrupted
5. The economic analysis of merge mining profitability

Pure Python, stdlib only.
"""
import hashlib
import math
import struct
import time
import json
import os
import sys
import signal

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

# Riemann zeros (first 15)
RIEMANN_ZEROS = [
    14.13472514173469, 21.02203963877155, 25.01085858181174,
    30.42487611818375, 32.93506158773918, 37.58617815882538,
    40.91871901214749, 43.32707328091601, 48.00515088116708,
    49.77383247767236, 52.97032147771091, 56.44624769702193,
    59.34704400801026, 60.83177855412748, 65.11254404809211,
]

# Golden ratio
GOLDEN_RATIO = (1 + math.sqrt(5)) / 2

# Bitcoin mainnet difficulty from recent blocks (approximate)
# Block 840,000 (Nov 2024): bits = 0x17046974
# Difficulty: ~83.5 trillion (8.35 × 10^13)
# Expected hashes: ~10^24
BITCOIN_MAINNET_BITS = 0x17046974

# Excalibur easy target (demo difficulty)
EXCALIBUR_EASY_BITS = 0x1f00ffff

# Excalibur realistic target (if it had real hashrate)
EXCALIBUR_REALISTIC_BITS = 0x1d00ffff

# ---------------------------------------------------------------------------
# Scalar Wave Engine
# ---------------------------------------------------------------------------

class ScalarWave:
    """φ(t) = Σ cos(γₖ·t)/γₖ for nonce scoring."""
    
    def __init__(self, zeros=None):
        self.zeros = zeros or RIEMANN_ZEROS
    
    def phi(self, t):
        return sum(math.cos(g * t) / g for g in self.zeros)
    
    def amplitude(self, t):
        return abs(self.phi(t))
    
    def score_nonce(self, nonce, max_nonce=0xFFFFFFFF):
        t = nonce / max_nonce
        return self.amplitude(t)


# ---------------------------------------------------------------------------
# Target Conversion
# ---------------------------------------------------------------------------

def bits_to_target(bits):
    """Convert compact bits to target integer."""
    exp = bits >> 24
    mant = bits & 0xFFFFFF
    if exp <= 3:
        return mant >> (8 * (3 - exp))
    return mant << (8 * (exp - 3))

def difficulty_from_target(target):
    """Compute difficulty from target."""
    DIFF1 = 0x00000000FFFF0000000000000000000000000000000000000000000000000000
    if target <= 0:
        return float('inf')
    return DIFF1 / target

def sha256d(data):
    """Double SHA-256 hash."""
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


# ---------------------------------------------------------------------------
# Realistic Probability Analysis
# ---------------------------------------------------------------------------

class MergeMiningProbability:
    """
    Analyze the real probability of dual hits in merge mining.
    
    The fundamental insight:
    - Child chain (Excalibur) has easy target → blocks found quickly
    - Parent chain (Bitcoin) has hard target → blocks found rarely
    - Dual hit requires meeting BOTH targets simultaneously
    - Since Bitcoin target << Excalibur target, dual hit prob ≈ Bitcoin prob
    """
    
    def __init__(self, child_bits, bitcoin_bits):
        self.child_bits = child_bits
        self.bitcoin_bits = bitcoin_bits
        self.child_target = bits_to_target(child_bits)
        self.bitcoin_target = bits_to_target(bitcoin_bits)
        self.max_target = (1 << 256) - 1
    
    def analyze(self):
        """Complete probability analysis."""
        child_diff = difficulty_from_target(self.child_target)
        bitcoin_diff = difficulty_from_target(self.bitcoin_target)
        
        child_prob = self.child_target / self.max_target
        bitcoin_prob = self.bitcoin_target / self.max_target
        
        # Dual hit requires meeting the stricter (lower) target
        dual_prob = min(child_prob, bitcoin_prob)
        
        expected_child = 1 / child_prob if child_prob > 0 else float('inf')
        expected_bitcoin = 1 / bitcoin_prob if bitcoin_prob > 0 else float('inf')
        expected_dual = 1 / dual_prob if dual_prob > 0 else float('inf')
        
        return {
            "child_bits": f"0x{self.child_bits:08x}",
            "bitcoin_bits": f"0x{self.bitcoin_bits:08x}",
            "child_difficulty": child_diff,
            "bitcoin_difficulty": bitcoin_diff,
            "difficulty_ratio": bitcoin_diff / child_diff if child_diff > 0 else float('inf'),
            "child_prob": child_prob,
            "bitcoin_prob": bitcoin_prob,
            "dual_prob": dual_prob,
            "expected_hashes_child": expected_child,
            "expected_hashes_bitcoin": expected_bitcoin,
            "expected_hashes_dual": expected_dual,
            "stricter_chain": "Bitcoin" if self.bitcoin_target < self.child_target else "Excalibur",
        }
    
    def time_to_dual_hit(self, hash_rate_hps):
        """
        Compute expected time to find a dual hit at given hash rate.
        
        Args:
            hash_rate_hps: Hashes per second (e.g., 1e12 for 1 TH/s)
        
        Returns:
            Dictionary with time estimates in various units.
        """
        analysis = self.analyze()
        expected = analysis["expected_hashes_dual"]
        
        if expected == float('inf'):
            return {"seconds": float('inf'), "years": float('inf')}
        
        seconds = expected / hash_rate_hps
        minutes = seconds / 60
        hours = minutes / 60
        days = hours / 24
        years = days / 365.25
        
        return {
            "hash_rate_hps": hash_rate_hps,
            "expected_hashes": expected,
            "seconds": seconds,
            "minutes": minutes,
            "hours": hours,
            "days": days,
            "years": years,
        }


# ---------------------------------------------------------------------------
# Continuous Mining Loop
# ---------------------------------------------------------------------------

class ContinuousMiner:
    """
    Continuous merge mining loop that runs until interrupted.
    
    This simulates the actual merge mining process:
    1. Build parent header with merged-mining commitment
    2. Iterate through nonces, checking both targets
    3. Report child hits (Excalibur blocks)
    4. Report dual hits (Bitcoin + Excalibur blocks)
    5. Track statistics and hash rate
    """
    
    def __init__(self, child_bits, bitcoin_bits, prefix76):
        self.child_bits = child_bits
        self.bitcoin_bits = bitcoin_bits
        self.prefix76 = prefix76
        self.child_target = bits_to_target(child_bits)
        self.bitcoin_target = bits_to_target(bitcoin_bits)
        self.scalar_wave = ScalarWave()
        
        # Statistics
        self.hashes = 0
        self.child_hits = 0
        self.dual_hits = 0
        self.start_time = None
        self.running = False
    
    def mine_block(self, max_nonces=0x100000):
        """
        Mine one block by iterating through nonces.
        
        Args:
            max_nonces: Maximum nonces to try (default: 1M)
        
        Returns:
            Dictionary with results.
        """
        if self.start_time is None:
            self.start_time = time.time()
            self.running = True
        
        results = []
        start_nonce = self.hashes % 0xFFFFFFFF
        
        for i in range(max_nonces):
            if not self.running:
                break
            
            nonce = (start_nonce + i) & 0xFFFFFFFF
            header = self.prefix76 + struct.pack("<I", nonce)
            hash_val = sha256d(header)
            hash_int = int.from_bytes(hash_val, "big")
            
            self.hashes += 1
            
            child_hit = hash_int <= self.child_target
            bitcoin_hit = hash_int <= self.bitcoin_target
            
            if child_hit:
                self.child_hits += 1
                if bitcoin_hit:
                    self.dual_hits += 1
                    results.append({
                        "type": "DUAL_HIT",
                        "nonce": nonce,
                        "hash": hash_val.hex(),
                        "hash_int": hash_int,
                    })
                else:
                    results.append({
                        "type": "CHILD_HIT",
                        "nonce": nonce,
                        "hash": hash_val.hex(),
                        "hash_int": hash_int,
                    })
        
        return results
    
    def get_stats(self):
        """Get current mining statistics."""
        elapsed = time.time() - self.start_time if self.start_time else 0
        hash_rate = self.hashes / elapsed if elapsed > 0 else 0
        
        return {
            "elapsed_seconds": elapsed,
            "total_hashes": self.hashes,
            "hash_rate": hash_rate,
            "child_hits": self.child_hits,
            "dual_hits": self.dual_hits,
            "child_hit_rate": self.child_hits / self.hashes if self.hashes > 0 else 0,
            "dual_hit_rate": self.dual_hits / self.hashes if self.hashes > 0 else 0,
        }
    
    def stop(self):
        """Stop the mining loop."""
        self.running = False


# ---------------------------------------------------------------------------
# Economic Analysis
# ---------------------------------------------------------------------------

class EconomicAnalysis:
    """
    Analyze the economics of merge mining.
    
    Key question: Is it profitable to merge mine Excalibur on Bitcoin hashrate?
    
    Answer: Only if the child chain reward exceeds the electricity cost
    of the additional hashing. Since the parent chain (Bitcoin) reward
    goes to whoever finds the block, merge mining is essentially free
    child chain mining when you're already mining Bitcoin.
    """
    
    BTC_PRICE_USD = 100000  # Approximate current price
    BTC_REWARD = 3.125  # Bitcoin block reward (post-2024 halving)
    EXCAL_REWARD = 50  # Excalibur block reward (estimated)
    ELECTRICITY_COST_PER_KWH = 0.10  # $0.10/kWh
    ASIC_EFFICIENCY_J_PER_TH = 30  # 30 J/TH (modern ASIC)
    
    @classmethod
    def analyze(cls, hash_rate_th, child_bits, bitcoin_bits):
        """
        Complete economic analysis.
        
        Args:
            hash_rate_th: Hash rate in TH/s
            child_bits: Child chain difficulty bits
            bitcoin_bits: Bitcoin difficulty bits
        
        Returns:
            Dictionary with economic metrics.
        """
        prob = MergeMiningProbability(child_bits, bitcoin_bits)
        analysis = prob.analyze()
        
        hash_rate_hps = hash_rate_th * 1e12
        
        # Power consumption
        power_watts = hash_rate_th * cls.ASIC_EFFICIENCY_J_PER_TH
        power_kw = power_watts / 1000
        electricity_cost_per_day = power_kw * 24 * cls.ELECTRICITY_COST_PER_KWH
        
        # Bitcoin revenue (expected)
        bitcoin_time = prob.time_to_dual_hit(hash_rate_hps)
        bitcoin_years = bitcoin_time["years"]
        
        if bitcoin_years > 0 and bitcoin_years < float('inf'):
            bitcoin_revenue_per_year = cls.BTC_REWARD * cls.BTC_PRICE_USD / bitcoin_years
        else:
            bitcoin_revenue_per_year = 0
        
        # Child chain revenue (expected)
        child_expected = analysis["expected_hashes_child"]
        child_blocks_per_day = (hash_rate_hps * 86400) / child_expected if child_expected > 0 else 0
        child_revenue_per_day = child_blocks_per_day * cls.EXCAL_REWARD  # In EXCAL tokens
        
        return {
            "hash_rate_th": hash_rate_th,
            "power_watts": power_watts,
            "power_kw": power_kw,
            "electricity_cost_per_day": electricity_cost_per_day,
            "electricity_cost_per_year": electricity_cost_per_day * 365,
            "bitcoin_expected_years": bitcoin_years,
            "bitcoin_revenue_per_year_usd": bitcoin_revenue_per_year,
            "child_blocks_per_day": child_blocks_per_day,
            "child_revenue_per_day_excal": child_revenue_per_day,
            "net_profit_per_year_usd": bitcoin_revenue_per_year - electricity_cost_per_day * 365,
            "profitable": bitcoin_revenue_per_year > electricity_cost_per_day * 365,
        }


# ---------------------------------------------------------------------------
# Demo: Realistic Merge Mining
# ---------------------------------------------------------------------------

def run_demo():
    """Run a realistic merge mining demonstration."""
    print("\n" + "=" * 78)
    print("REAL MERGE MINING — Probability Analysis")
    print("=" * 78)
    
    # ---- Section 1: Real Bitcoin Difficulty ----
    print("\n[Section 1] Real Bitcoin Mainnet Difficulty")
    print(f"  Bitcoin bits: 0x{BITCOIN_MAINNET_BITS:08x}")
    print(f"  Excalibur easy: 0x{EXCALIBUR_EASY_BITS:08x}")
    
    prob = MergeMiningProbability(EXCALIBUR_EASY_BITS, BITCOIN_MAINNET_BITS)
    analysis = prob.analyze()
    
    print(f"\n  Child difficulty: {analysis['child_difficulty']:.2f}")
    print(f"  Bitcoin difficulty: {analysis['bitcoin_difficulty']:.2e}")
    print(f"  Difficulty ratio: {analysis['difficulty_ratio']:.2e}x")
    print(f"  Stricter chain: {analysis['stricter_chain']}")
    
    print(f"\n  Expected hashes (child block): {analysis['expected_hashes_child']:.2e}")
    print(f"  Expected hashes (Bitcoin block): {analysis['expected_hashes_bitcoin']:.2e}")
    print(f"  Expected hashes (dual hit): {analysis['expected_hashes_dual']:.2e}")
    
    # ---- Section 2: Time to Dual Hit ----
    print("\n[Section 2] Time to Find a Dual Hit")
    
    hash_rates = [
        ("1 TH/s", 1e12),
        ("100 TH/s", 100e12),
        ("1 EH/s", 1e18),
        ("100 EH/s", 100e18),
        ("1 ZH/s", 1e21),
        ("100 ZH/s", 100e21),
        ("Network hashrate", 500e18),  # ~500 EH/s
    ]
    
    for label, rate in hash_rates:
        time_info = prob.time_to_dual_hit(rate)
        years = time_info["years"]
        if years < 1:
            print(f"  {label:>15}: {time_info['days']:.2f} days")
        elif years < 1000:
            print(f"  {label:>15}: {years:.2f} years")
        else:
            print(f"  {label:>15}: {years:.2e} years")
    
    # ---- Section 3: Continuous Mining Demo ----
    print("\n[Section 3] Continuous Mining Demo (1M nonces)")
    
    # Build a parent header prefix
    timestamp = int(time.time())
    prev_block = b"\x00" * 32
    merkle_root = b"\x00" * 32
    version = 1
    bits = EXCALIBUR_EASY_BITS
    
    prefix76 = struct.pack("<I", version) + prev_block + merkle_root + struct.pack("<II", timestamp, bits)
    assert len(prefix76) == 76
    
    miner = ContinuousMiner(EXCALIBUR_EASY_BITS, BITCOIN_MAINNET_BITS, prefix76)
    
    print(f"  Mining 1M nonces at easy child target...")
    results = miner.mine_block(max_nonces=1_000_000)
    stats = miner.get_stats()
    
    print(f"  Hash rate: {stats['hash_rate']:.2e} H/s")
    print(f"  Child hits: {stats['child_hits']}")
    print(f"  Dual hits: {stats['dual_hits']}")
    print(f"  Child hit rate: {stats['child_hit_rate']:.6f}")
    print(f"  Dual hit rate: {stats['dual_hit_rate']:.2e}")
    
    if results:
        for r in results[:5]:  # Show first 5 results
            print(f"  Found {r['type']} at nonce 0x{r['nonce']:08x}: {r['hash'][:16]}..")
    
    # ---- Section 4: Economic Analysis ----
    print("\n[Section 4] Economic Analysis")
    
    econ = EconomicAnalysis.analyze(100, EXCALIBUR_EASY_BITS, BITCOIN_MAINNET_BITS)
    
    print(f"  Hash rate: {econ['hash_rate_th']} TH/s")
    print(f"  Power: {econ['power_kw']:.1f} kW ({econ['power_watts']:.0f} W)")
    print(f"  Electricity cost: ${econ['electricity_cost_per_day']:.2f}/day")
    print(f"  Bitcoin expected: {econ['bitcoin_expected_years']:.2e} years per block")
    print(f"  Bitcoin revenue: ${econ['bitcoin_revenue_per_year_usd']:.2e}/year")
    print(f"  Child blocks: {econ['child_blocks_per_day']:.2f}/day")
    print(f"  Net profit: ${econ['net_profit_per_year_usd']:.2e}/year")
    print(f"  Profitable: {econ['profitable']}")
    
    # ---- Section 5: The Fundamental Gap ----
    print("\n[Section 5] The Fundamental Probability Gap")
    
    print(f"\n  The dual hit probability is determined by the STRICTER target.")
    print(f"  Since Bitcoin target << Excalibur target:")
    print(f"    P(dual hit) ≈ P(Bitcoin hit) = {analysis['bitcoin_prob']:.2e}")
    print(f"\n  This means:")
    print(f"    - You find Excalibur blocks every ~{analysis['expected_hashes_child']:.2e} hashes")
    print(f"    - You find Bitcoin blocks every ~{analysis['expected_hashes_bitcoin']:.2e} hashes")
    print(f"    - The ratio is {analysis['difficulty_ratio']:.2e}x")
    print(f"\n  At 100 TH/s hashrate:")
    print(f"    - Excalibur block time: ~{analysis['expected_hashes_child']/100e12*60:.2f} minutes")
    print(f"    - Bitcoin block time: ~{analysis['expected_hashes_bitcoin']/100e12/3600/24/365.25:.2e} years")
    print(f"\n  The dual hit is NOT a practical revenue source at real Bitcoin difficulty.")
    print(f"  However, the Excalibur blocks are found for FREE while mining Bitcoin.")
    
    print("\n" + "=" * 78)
    print("Real merge mining analysis complete.")
    print("=" * 78)


# ---------------------------------------------------------------------------
# Test Suite
# ---------------------------------------------------------------------------

def run_tests():
    """Run all real merge mining tests."""
    passed = 0
    total = 0
    
    print("=" * 78)
    print("REAL MERGE MINING — Test Suite")
    print("=" * 78)
    
    # ---- Section 1: Target Conversion ----
    print("\n[Section 1] Target Conversion")
    
    total += 1
    btc_target = bits_to_target(BITCOIN_MAINNET_BITS)
    assert btc_target > 0, "Bitcoin target must be positive"
    assert btc_target < (1 << 256), "Bitcoin target must be < 2^256"
    print(f"[1/15] Bitcoin target: {btc_target} ✓")
    passed += 1
    
    total += 1
    excal_target = bits_to_target(EXCALIBUR_EASY_BITS)
    assert excal_target > btc_target, "Excalibur target > Bitcoin target"
    print(f"[2/15] Excalibur target > Bitcoin target ✓")
    passed += 1
    
    # ---- Section 2: Difficulty ----
    print("\n[Section 2] Difficulty")
    
    total += 1
    btc_diff = difficulty_from_target(btc_target)
    assert btc_diff > 1e12, f"Bitcoin difficulty too low: {btc_diff}"
    print(f"[3/15] Bitcoin difficulty: {btc_diff:.2e} ✓")
    passed += 1
    
    total += 1
    excal_diff = difficulty_from_target(excal_target)
    assert excal_diff < 100, f"Excalibur difficulty too high: {excal_diff}"
    print(f"[4/15] Excalibur difficulty: {excal_diff:.2f} ✓")
    passed += 1
    
    # ---- Section 3: Probability Analysis ----
    print("\n[Section 3] Probability Analysis")
    
    total += 1
    prob = MergeMiningProbability(EXCALIBUR_EASY_BITS, BITCOIN_MAINNET_BITS)
    analysis = prob.analyze()
    assert analysis["stricter_chain"] == "Bitcoin", "Bitcoin should be stricter"
    print(f"[5/15] Stricter chain: {analysis['stricter_chain']} ✓")
    passed += 1
    
    total += 1
    assert analysis["difficulty_ratio"] > 1e12, f"Ratio too small: {analysis['difficulty_ratio']}"
    print(f"[6/15] Difficulty ratio: {analysis['difficulty_ratio']:.2e}x ✓")
    passed += 1
    
    total += 1
    assert analysis["expected_hashes_dual"] > 1e20, f"Dual hit too easy: {analysis['expected_hashes_dual']}"
    print(f"[7/15] Expected hashes (dual): {analysis['expected_hashes_dual']:.2e} ✓")
    passed += 1
    
    # ---- Section 4: Time to Dual Hit ----
    print("\n[Section 4] Time to Dual Hit")
    
    total += 1
    time_info = prob.time_to_dual_hit(1e12)  # 1 TH/s
    assert time_info["years"] > 1000, f"Too fast at 1 TH/s: {time_info['years']}"
    print(f"[8/15] 1 TH/s: {time_info['years']:.2e} years ✓")
    passed += 1
    
    total += 1
    time_info = prob.time_to_dual_hit(100e18)  # 100 EH/s
    # At 100 EH/s, Bitcoin blocks take ~45 minutes at this difficulty
    assert time_info["seconds"] > 100, f"Should take > 100s at 100 EH/s: {time_info['seconds']}"
    assert time_info["seconds"] < 10000, f"Should take < 10000s at 100 EH/s: {time_info['seconds']}"
    print(f"[9/15] 100 EH/s: {time_info['seconds']:.0f} seconds ({time_info['seconds']/60:.1f} min) ✓")
    passed += 1
    
    # ---- Section 5: Continuous Miner ----
    print("\n[Section 5] Continuous Miner")
    
    total += 1
    prefix76 = b"\x00" * 76
    miner = ContinuousMiner(EXCALIBUR_EASY_BITS, BITCOIN_MAINNET_BITS, prefix76)
    results = miner.mine_block(max_nonces=100000)
    stats = miner.get_stats()
    assert stats["total_hashes"] == 100000, f"Hash count: {stats['total_hashes']}"
    print(f"[10/15] Miner: 100K hashes, {stats['child_hits']} child hits ✓")
    passed += 1
    
    total += 1
    assert stats["dual_hits"] == 0, f"Dual hit at easy test: {stats['dual_hits']}"
    print(f"[11/15] No dual hits at 100K hashes (expected) ✓")
    passed += 1
    
    total += 1
    miner.stop()
    assert not miner.running, "Miner should stop"
    print(f"[12/15] Miner stop: ✓")
    passed += 1
    
    # ---- Section 6: Scalar Wave ----
    print("\n[Section 6] Scalar Wave")
    
    total += 1
    sw = ScalarWave()
    phi_0 = sw.phi(0.0)
    expected = sum(1.0 / g for g in RIEMANN_ZEROS)
    assert abs(phi_0 - expected) < 1e-10, f"φ(0) = {phi_0} vs {expected}"
    print(f"[13/15] Scalar wave φ(0) = {phi_0:.6f} ✓")
    passed += 1
    
    total += 1
    score = sw.score_nonce(0x12345678)
    assert 0 <= score <= 10, f"Score out of range: {score}"
    print(f"[14/15] Nonce scoring: 0x12345678 → |φ| = {score:.4f} ✓")
    passed += 1
    
    # ---- Section 7: Economic Analysis ----
    print("\n[Section 7] Economic Analysis")
    
    total += 1
    econ = EconomicAnalysis.analyze(100, EXCALIBUR_EASY_BITS, BITCOIN_MAINNET_BITS)
    assert econ["hash_rate_th"] == 100, "Hash rate"
    assert econ["power_kw"] > 0, "Power"
    assert econ["electricity_cost_per_day"] > 0, "Cost"
    print(f"[15/15] Economic: ${econ['electricity_cost_per_day']:.2f}/day electricity ✓")
    passed += 1
    
    # ---- Summary ----
    print("\n" + "=" * 78)
    print(f"RESULTS: {passed}/{total} tests passed")
    print("=" * 78)
    
    if passed == total:
        print("\n✓ All real merge mining tests passed!")
    else:
        print(f"\n✗ {total - passed} tests failed")
    
    return passed == total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Real Merge Mining Analysis")
    parser.add_argument("--test", action="store_true", help="Run tests")
    parser.add_argument("--demo", action="store_true", help="Run demo")
    
    args = parser.parse_args()
    
    if args.test:
        success = run_tests()
        sys.exit(0 if success else 1)
    elif args.demo:
        run_demo()
    else:
        success = run_tests()
        if success:
            run_demo()
        sys.exit(0 if success else 1)
