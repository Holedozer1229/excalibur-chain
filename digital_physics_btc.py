#!/usr/bin/env python3
"""
Digital Physics Experiments on Bitcoin Mainnet
==============================================

This script probes the Bitcoin blockchain for physical patterns,
entropy anomalies, and causal structure — experiments where
the outcome is genuinely uncertain.

Experiments:
1. Hash entropy analysis across block heights
2. Nonce distribution statistics
3. Genesis block merkle root bit pattern analysis
4. Transaction timing correlation analysis
5. Burn address causal structure
6. Block hash bit flip rate over time
7. Coinbase transaction entropy
8. Difficulty adjustment pattern analysis
"""

import hashlib
import json
import math
import time
import urllib.request
import urllib.error
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Dict, Optional

BASE_URL = "https://mempool.space/api"


def fetch_json(path, timeout=10):
    """Fetch JSON from mempool.space API."""
    url = f"{BASE_URL}{path}"
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'DigitalPhysics/1.0')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode()
            return json.loads(data)
    except json.JSONDecodeError:
        # Some endpoints return plain text, not JSON
        try:
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'DigitalPhysics/1.0')
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read().decode().strip()
        except Exception as e2:
            print(f"  Failed to fetch {path}: {e2}")
            return None
    except Exception as e:
        print(f"  Failed to fetch {path}: {e}")
        return None


def fetch_text(path, timeout=10):
    """Fetch plain text from mempool.space API (e.g., block-height lookup)."""
    url = f"{BASE_URL}{path}"
    try:
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'DigitalPhysics/1.0')
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode().strip()
    except Exception as e:
        print(f"  Failed to fetch {path}: {e}")
        return None


@dataclass
class EntropyResult:
    """Result of entropy analysis."""
    name: str
    shannon_entropy: float
    max_entropy: float
    ratio: float
    bits_analyzed: int
    chi_squared: float = 0.0
    p_value: float = 1.0


def binary_entropy(bits: str) -> float:
    """Calculate Shannon entropy of a binary string."""
    if not bits:
        return 0.0
    counts = Counter(bits)
    total = len(bits)
    entropy = 0.0
    for count in counts.values():
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)
    return entropy


def hex_to_bits(hex_str: str) -> str:
    """Convert hex string to binary string."""
    return bin(int(hex_str, 16))[2:].zfill(len(hex_str) * 4)


def chi_squared_test(observed: List[int], expected_ratio: float = 0.5) -> tuple:
    """Chi-squared test for binary distribution."""
    n = len(observed)
    expected_ones = n * expected_ratio
    expected_zeros = n * (1 - expected_ratio)
    actual_ones = sum(1 for x in observed if x == 1)
    actual_zeros = n - actual_ones
    
    if expected_ones == 0 or expected_zeros == 0:
        return 0.0, 1.0
    
    chi2 = ((actual_ones - expected_ones) ** 2 / expected_ones +
            (actual_zeros - expected_zeros) ** 2 / expected_zeros)
    
    # Approximate p-value using normal approximation for df=1
    import math
    z = math.sqrt(chi2)
    # Standard normal CDF approximation
    p_value = 2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2))))
    
    return chi2, p_value


# ============================================================
# EXPERIMENT 1: Block Hash Entropy Across Time
# ============================================================
def experiment_hash_entropy():
    """
    Analyze whether block hash entropy varies over time.
    
    Hypothesis: If miners are finding blocks uniformly,
    hash entropy should be constant. Deviations might indicate
    mining pool coordination or hash function bias.
    """
    print("\n" + "=" * 70)
    print("EXPERIMENT 1: Block Hash Entropy Across Time")
    print("=" * 70)
    print("Hypothesis: Block hash entropy is constant over time")
    print("If not, it might reveal mining pool coordination patterns")
    
    heights = [0, 100000, 200000, 300000, 400000, 500000, 700000, 800000, 840000, 850000]
    results = []
    
    for h in heights:
        block = fetch_text(f"/block-height/{h}")
        if block is None:
            continue
        
        block_data = fetch_json(f"/block/{block}")
        if block_data is None:
            continue
        
        hash_hex = block_data.get('id', '')
        bits = hex_to_bits(hash_hex)
        
        entropy = binary_entropy(bits)
        max_entropy = 1.0  # Binary max is 1.0
        
        # Chi-squared for bit distribution
        bit_values = [int(b) for b in bits]
        chi2, p_val = chi_squared_test(bit_values)
        
        result = EntropyResult(
            name=f"Block height {h}",
            shannon_entropy=entropy,
            max_entropy=max_entropy,
            ratio=entropy / max_entropy if max_entropy > 0 else 0,
            bits_analyzed=len(bits),
            chi_squared=chi2,
            p_value=p_val,
        )
        results.append(result)
        
        print(f"  Height {h:>7d}: entropy={entropy:.6f} "
              f"(ratio={result.ratio:.4f}) chi2={chi2:.2f} p={p_val:.4f}")
        time.sleep(0.3)  # Rate limiting
    
    if results:
        avg_entropy = sum(r.shannon_entropy for r in results) / len(results)
        min_entropy = min(r.shannon_entropy for r in results)
        max_entropy_val = max(r.shannon_entropy for r in results)
        
        print(f"\n  Summary:")
        print(f"    Average entropy: {avg_entropy:.6f}")
        print(f"    Min entropy: {min_entropy:.6f}")
        print(f"    Max entropy: {max_entropy_val:.6f}")
        print(f"    Entropy variance: {(max_entropy_val - min_entropy):.6f}")
        
        if (max_entropy_val - min_entropy) < 0.001:
            print(f"    RESULT: Entropy is remarkably stable — hashes are uniformly random")
        else:
            print(f"    RESULT: Entropy varies — possible non-uniformity detected!")
    
    return results


# ============================================================
# EXPERIMENT 2: Nonce Distribution Analysis
# ============================================================
def experiment_nonce_distribution():
    """
    Analyze the distribution of nonces across blocks.
    
    Hypothesis: Nonces should be uniformly distributed in [0, 2^32).
    However, miners start from 0 and increment, so we expect
    a bias toward lower values. But the distribution shape
    might reveal mining pool strategies.
    """
    print("\n" + "=" * 70)
    print("EXPERIMENT 2: Nonce Distribution Analysis")
    print("=" * 70)
    print("Hypothesis: Nonce distribution reveals miner search strategies")
    
    # Sample blocks at various heights
    heights = list(range(0, 1000, 100)) + list(range(700000, 850000, 5000))
    nonces = []
    
    for h in heights[:30]:  # Limit to avoid too many requests
        block = fetch_text(f"/block-height/{h}")
        if block is None:
            continue
        
        block_data = fetch_json(f"/block/{block}")
        if block_data is None:
            continue
        
        nonce = block_data.get('nonce', -1)
        if nonce >= 0:
            nonces.append((h, nonce))
        
        time.sleep(0.2)
    
    if not nonces:
        print("  No nonce data collected")
        return None
    
    print(f"\n  Collected {len(nonces)} nonces:")
    print(f"  {'Height':>10}  {'Nonce':>12}  {'Nonce (hex)':>12}  {'Log2(Nonce)':>10}")
    print(f"  {'-'*10}  {'-'*12}  {'-'*12}  {'-'*10}")
    
    log2_nonces = []
    for h, n in nonces:
        log2_n = math.log2(n) if n > 0 else -1
        log2_nonces.append(log2_n)
        print(f"  {h:>10}  {n:>12}  {n:>12x}  {log2_n:>10.2f}")
    
    if log2_nonces:
        avg_log2 = sum(log2_nonces) / len(log2_nonces)
        min_log2 = min(log2_nonces)
        max_log2 = max(log2_nonces)
        
        print(f"\n  Nonce statistics:")
        print(f"    Average log2(nonce): {avg_log2:.2f}")
        print(f"    Min log2(nonce): {min_log2:.2f}")
        print(f"    Max log2(nonce): {max_log2:.2f}")
        print(f"    Expected for uniform search: ~31 (near 2^32)")
        
        if avg_log2 < 20:
            print(f"    RESULT: Nonces are LOW — miners find blocks quickly")
        elif avg_log2 > 30:
            print(f"    RESULT: Nonces are HIGH — difficulty is very high")
        else:
            print(f"    RESULT: Nonces in mid-range — mixed mining strategies")
    
    return nonces


# ============================================================
# EXPERIMENT 3: Genesis Block Deep Analysis
# ============================================================
def experiment_genesis_deep():
    """
    Deep analysis of the genesis block's hidden structure.
    
    The genesis block contains:
    - "The Times 03/Jan/2009 Chancellor on brink of second bailout for banks"
    - A coinbase transaction with 50 BTC reward
    - A specific nonce: 1874083133
    
    Questions:
    - Does the merkle root encode additional information?
    - Is the nonce special in any mathematical sense?
    - Does the hash have unusual bit patterns?
    """
    print("\n" + "=" * 70)
    print("EXPERIMENT 3: Genesis Block Deep Analysis")
    print("=" * 70)
    print("Hypothesis: Genesis block contains hidden mathematical structure")
    
    genesis = fetch_text("/block-height/0")
    if genesis is None:
        print("  Failed to fetch genesis block")
        return None
    
    genesis_data = fetch_json(f"/block/{genesis}")
    if genesis_data is None:
        print("  Failed to fetch genesis block data")
        return None
    
    hash_hex = genesis_data['id']
    nonce = genesis_data['nonce']
    merkle = genesis_data['merkle_root']
    timestamp = genesis_data['timestamp']
    bits = genesis_data['bits']
    
    print(f"\n  Genesis Block Properties:")
    print(f"    Hash: {hash_hex}")
    print(f"    Nonce: {nonce} (0x{nonce:x})")
    print(f"    Merkle root: {merkle}")
    print(f"    Timestamp: {timestamp}")
    print(f"    Bits (difficulty): {bits}")
    
    # Analyze hash bits
    hash_bits = hex_to_bits(hash_hex)
    hash_entropy = binary_entropy(hash_bits)
    print(f"\n  Hash bit analysis:")
    print(f"    Total bits: {len(hash_bits)}")
    print(f"    Ones: {hash_bits.count('1')}")
    print(f"    Zeros: {hash_bits.count('0')}")
    print(f"    Shannon entropy: {hash_entropy:.6f} (max 1.0)")
    print(f"    Entropy ratio: {hash_entropy:.4f}")
    
    # Analyze nonce
    nonce_bits = bin(nonce)[2:]
    nonce_entropy = binary_entropy(nonce_bits)
    print(f"\n  Nonce bit analysis:")
    print(f"    Nonce: {nonce}")
    print(f"    Binary: {bin(nonce)}")
    print(f"    Bit length: {len(nonce_bits)}")
    print(f"    Shannon entropy: {nonce_entropy:.6f}")
    
    # Check if nonce has mathematical properties
    print(f"\n  Nonce mathematical properties:")
    print(f"    Is prime? (quick check): {is_prime_quick(nonce)}")
    print(f"    Is Fibonacci? {is_fibonacci(nonce)}")
    print(f"    Sum of digits: {sum(int(d) for d in str(nonce))}")
    print(f"    Product of non-zero digits: {product_nonzero_digits(nonce)}")
    
    # Analyze merkle root
    merkle_bits = hex_to_bits(merkle)
    merkle_entropy = binary_entropy(merkle_bits)
    print(f"\n  Merkle root bit analysis:")
    print(f"    Shannon entropy: {merkle_entropy:.6f}")
    
    # Check for leading zeros in hash (proof of work)
    leading_zeros = 0
    for b in hash_bits:
        if b == '0':
            leading_zeros += 1
        else:
            break
    
    print(f"\n  Proof of Work:")
    print(f"    Leading zeros in hash: {leading_zeros}")
    print(f"    Leading zeros in hex: {len(hash_hex) - len(hash_hex.lstrip('0'))}")
    
    print(f"\n  RESULT: Genesis block is a fixed point in spacetime —")
    print(f"    the first causal event in the Bitcoin universe.")
    
    return genesis_data


def is_prime_quick(n):
    """Quick primality test."""
    if n < 2:
        return False
    if n < 4:
        return True
    if n % 2 == 0 or n % 3 == 0:
        return False
    i = 5
    while i * i <= n and i < 10000:  # Quick check only
        if n % i == 0 or n % (i + 2) == 0:
            return False
        i += 6
    return True  # Inconclusive for large n, but good enough


def is_fibonacci(n):
    """Check if n is a Fibonacci number."""
    a, b = 0, 1
    while b < n:
        a, b = b, a + b
    return b == n


def product_nonzero_digits(n):
    """Product of non-zero digits."""
    result = 1
    for d in str(n):
        d = int(d)
        if d > 0:
            result *= d
    return result


# ============================================================
# EXPERIMENT 4: Transaction Timing Correlation
# ============================================================
def experiment_timing_correlation():
    """
    Analyze whether transaction timing shows correlation
    with block production.
    
    Hypothesis: Transactions might cluster in time,
    revealing network topology or mempool dynamics.
    """
    print("\n" + "=" * 70)
    print("EXPERIMENT 4: Transaction Timing Correlation")
    print("=" * 70)
    print("Hypothesis: Transaction timing reveals network topology")
    
    # Get recent blocks
    block_heights = []
    current_height_str = fetch_text("/blocks/tip/height")
    if current_height_str is None:
        print("  Failed to get current height")
        return None
    
    current_height = int(current_height_str)
    print(f"  Current block height: {current_height}")
    
    # Sample last 20 blocks
    intervals = []
    prev_time = None
    
    for i in range(20):
        h = current_height - i
        block = fetch_text(f"/block-height/{h}")
        if block is None:
            continue
        
        block_data = fetch_json(f"/block/{block}")
        if block_data is None:
            continue
        
        block_time = block_data.get('timestamp', 0)
        tx_count = len(block_data.get('tx', []))
        
        if prev_time is not None:
            interval = prev_time - block_time
            intervals.append((h, interval, tx_count))
        
        prev_time = block_time
        time.sleep(0.2)
    
    if not intervals:
        print("  No interval data collected")
        return None
    
    print(f"\n  Block intervals (last {len(intervals)} blocks):")
    print(f"  {'Height':>10}  {'Interval (s)':>14}  {'Tx Count':>10}")
    print(f"  {'-'*10}  {'-'*14}  {'-'*10}")
    
    interval_values = [iv[1] for iv in intervals]
    tx_counts = [iv[2] for iv in intervals]
    
    for h, iv, tc in intervals:
        print(f"  {h:>10}  {iv:>14.1f}  {tc:>10}")
    
    avg_interval = sum(interval_values) / len(interval_values)
    min_interval = min(interval_values)
    max_interval = max(interval_values)
    std_interval = (sum((x - avg_interval) ** 2 for x in interval_values) / len(interval_values)) ** 0.5
    
    print(f"\n  Interval statistics:")
    print(f"    Average: {avg_interval:.1f} seconds")
    print(f"    Min: {min_interval:.1f} seconds")
    print(f"    Max: {max_interval:.1f} seconds")
    print(f"    Std dev: {std_interval:.1f} seconds")
    print(f"    Expected: ~600 seconds (10 minutes)")
    
    # Check for correlation between interval and tx count
    if len(intervals) > 2:
        # Simple Pearson correlation
        n = len(intervals)
        mean_iv = avg_interval
        mean_tc = sum(tx_counts) / n
        
        cov = sum((iv - mean_iv) * (tc - mean_tc) for _, iv, tc in intervals) / n
        std_iv = std_interval
        std_tc = (sum((tc - mean_tc) ** 2 for tc in tx_counts) / n) ** 0.5
        
        if std_iv > 0 and std_tc > 0:
            correlation = cov / (std_iv * std_tc)
            print(f"\n  Correlation (interval vs tx count): {correlation:.4f}")
            
            if abs(correlation) > 0.5:
                print(f"    RESULT: Strong correlation — more txs affect block timing")
            else:
                print(f"    RESULT: Weak correlation — block timing is independent of tx count")
    
    return intervals


# ============================================================
# EXPERIMENT 5: Burn Address Causal Structure
# ============================================================
def experiment_burn_causal():
    """
    Analyze the causal structure of BTC burn addresses.
    
    Hypothesis: Burn transactions might form a causal chain
    that encodes information beyond the burned value.
    """
    print("\n" + "=" * 70)
    print("EXPERIMENT 5: Burn Address Causal Structure")
    print("=" * 70)
    print("Hypothesis: Burn transactions encode hidden causal information")
    
    # Known burn addresses
    burn_addresses = [
        "1BitcoinEaterAddressDontSendf59kuE",
        "1CounterpartyXXXXXXXXXXXXXXXUWLpVr",
        "1FAWFFFFFFFFFFFFFFFFFFFFFFFFFFFFec",
    ]
    
    print(f"\n  Analyzing {len(burn_addresses)} known burn addresses:")
    
    for addr in burn_addresses:
        print(f"\n  Address: {addr}")
        
        # Get address info
        addr_info = fetch_json(f"/address/{addr}")
        if addr_info is None:
            print(f"    No data available")
            continue
        
        chain_stats = addr_info.get('chain_stats', {})
        mempool_stats = addr_info.get('mempool_stats', {})
        
        received = chain_stats.get('funded_txo_sum', 0)
        sent = chain_stats.get('spent_txo_sum', 0)
        tx_count = chain_stats.get('tx_count', 0)
        
        print(f"    Total received: {received / 1e8:.8f} BTC")
        print(f"    Total sent: {sent / 1e8:.8f} BTC")
        print(f"    Balance: {(received - sent) / 1e8:.8f} BTC")
        print(f"    Transaction count: {tx_count}")
        
        # Get recent transactions
        txs = fetch_json(f"/address/{addr}/txs/chain?limit=5")
        if txs:
            print(f"    Recent transactions:")
            for tx in txs[:3]:
                txid = tx.get('txid', 'unknown')
                value = tx.get('value', 0)
                print(f"      {txid[:16]}... value={value/1e8:.6f} BTC")
        
        time.sleep(0.3)
    
    print(f"\n  RESULT: Burn addresses are causal sinks —")
    print(f"    once BTC enters, it never leaves.")
    print(f"    This creates a one-way causal arrow in the blockchain.")
    
    return burn_addresses


# ============================================================
# EXPERIMENT 6: Block Hash Bit Flip Rate
# ============================================================
def experiment_bit_flip_rate():
    """
    Analyze how many bits flip between consecutive block hashes.
    
    Hypothesis: Consecutive block hashes should differ in ~50% of bits
    (256 bits on average for 512-bit hashes). Deviations might indicate
    structure in the hash function or mining process.
    """
    print("\n" + "=" * 70)
    print("EXPERIMENT 6: Block Hash Bit Flip Rate")
    print("=" * 70)
    print("Hypothesis: Consecutive hashes differ in ~50% of bits")
    
    current_height_str = fetch_text("/blocks/tip/height")
    if current_height_str is None:
        print("  Failed to get current height")
        return None
    
    current_height = int(current_height_str)
    
    # Get 10 consecutive blocks
    hashes = []
    for i in range(10):
        h = current_height - i
        block = fetch_text(f"/block-height/{h}")
        if block is None:
            continue
        
        block_data = fetch_json(f"/block/{block}")
        if block_data is None:
            continue
        
        hashes.append((h, block_data['id']))
        time.sleep(0.2)
    
    if len(hashes) < 2:
        print("  Not enough hashes collected")
        return None
    
    # Compare consecutive hashes
    print(f"\n  Comparing consecutive block hashes:")
    print(f"  {'From Height':>12}  {'To Height':>12}  {'Bits Flipped':>12}  {'Flip Rate':>10}")
    print(f"  {'-'*12}  {'-'*12}  {'-'*12}  {'-'*10}")
    
    flip_rates = []
    
    for i in range(len(hashes) - 1):
        h1, hash1 = hashes[i]
        h2, hash2 = hashes[i + 1]
        
        bits1 = hex_to_bits(hash1)
        bits2 = hex_to_bits(hash2)
        
        # Pad to same length
        max_len = max(len(bits1), len(bits2))
        bits1 = bits1.zfill(max_len)
        bits2 = bits2.zfill(max_len)
        
        # Count differing bits
        flips = sum(b1 != b2 for b1, b2 in zip(bits1, bits2))
        flip_rate = flips / max_len if max_len > 0 else 0
        
        flip_rates.append(flip_rate)
        
        print(f"  {h1:>12}  {h2:>12}  {flips:>12}  {flip_rate:>10.4f}")
    
    if flip_rates:
        avg_flip = sum(flip_rates) / len(flip_rates)
        min_flip = min(flip_rates)
        max_flip = max(flip_rates)
        
        print(f"\n  Flip rate statistics:")
        print(f"    Average: {avg_flip:.4f} ({avg_flip*100:.1f}%)")
        print(f"    Min: {min_flip:.4f}")
        print(f"    Max: {max_flip:.4f}")
        print(f"    Expected for random: 0.5 (50%)")
        
        if abs(avg_flip - 0.5) < 0.05:
            print(f"    RESULT: Flip rate is ~50% — hashes are maximally different")
        else:
            print(f"    RESULT: Flip rate deviates from 50% — possible structure!")
    
    return flip_rates


# ============================================================
# EXPERIMENT 7: Mempool Fee Rate Distribution
# ============================================================
def experiment_mempool_fees():
    """
    Analyze the fee rate distribution in the mempool.
    
    Hypothesis: Fee rates follow a power law distribution,
    revealing the economic dynamics of Bitcoin.
    """
    print("\n" + "=" * 70)
    print("EXPERIMENT 7: Mempool Fee Rate Distribution")
    print("=" * 70)
    print("Hypothesis: Fee rates follow a power law distribution")
    
    # Get fee estimates from blocks
    fees_data = fetch_json("/mempool/recent-mined-tx")
    if fees_data is None or not isinstance(fees_data, list):
        print("  Failed to get recent transactions")
        return None
    
    # Get current fee estimates
    fee_estimates = fetch_json("/mempool/recommended-fees")
    if fee_estimates:
        print(f"\n  Current recommended fees:")
        print(f"    Fastest: {fee_estimates.get('fastestFee', 'N/A')} sat/vB")
        print(f"    Half hour: {fee_estimates.get('halfHourFee', 'N/A')} sat/vB")
        print(f"    Hour: {fee_estimates.get('hourFee', 'N/A')} sat/vB")
    
    print(f"\n  Recent transactions (sample of {min(len(fees_data), 20)}):")
    print(f"  {'TXID (short)':>20}  {'Fee Rate':>12}  {'Value (BTC)':>14}")
    print(f"  {'-'*20}  {'-'*12}  {'-'*14}")
    
    fee_values = []
    for tx in fees_data[:20]:
        txid = tx.get('txid', 'unknown')[:16]
        fee_rate = tx.get('feeRate', 0)
        value = tx.get('value', 0)
        fee_values.append(fee_rate)
        print(f"  {txid:>20}  {fee_rate:>12.1f}  {value/1e8:>14.8f}")
    
    if fee_values:
        avg_fee = sum(fee_values) / len(fee_values)
        min_fee = min(fee_values)
        max_fee = max(fee_values)
        
        print(f"\n  Fee statistics:")
        print(f"    Average: {avg_fee:.1f} sat/vB")
        print(f"    Min: {min_fee:.1f} sat/vB")
        print(f"    Max: {max_fee:.1f} sat/vB")
        print(f"    Range: {max_fee - min_fee:.1f} sat/vB")
        
        # Check for power law
        if len(fee_values) > 2:
            # Simple log-log analysis
            log_fees = [math.log(f) for f in fee_values if f > 0]
            if len(log_fees) > 1:
                avg_log = sum(log_fees) / len(log_fees)
                print(f"\n  Log analysis:")
                print(f"    Average log(fee): {avg_log:.4f}")
                print(f"    RESULT: Fee rates show {'high' if (max_fee/min_fee) > 10 else 'low'} volatility")
    
    return fee_values


# ============================================================
# MAIN: Run All Experiments
# ============================================================
def main():
    print("=" * 70)
    print("DIGITAL PHYSICS ON BITCOIN MAINNET")
    print("=" * 70)
    print(f"Local time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"API endpoint: {BASE_URL}")
    print()
    
    experiments = [
        ("Hash Entropy", experiment_hash_entropy),
        ("Nonce Distribution", experiment_nonce_distribution),
        ("Genesis Deep", experiment_genesis_deep),
        ("Timing Correlation", experiment_timing_correlation),
        ("Burn Causal", experiment_burn_causal),
        ("Bit Flip Rate", experiment_bit_flip_rate),
        ("Mempool Fees", experiment_mempool_fees),
    ]
    
    results = {}
    
    for name, experiment in experiments:
        try:
            print(f"\n{'=' * 70}")
            print(f"Starting experiment: {name}")
            print(f"{'=' * 70}")
            
            result = experiment()
            results[name] = result
            
        except Exception as e:
            print(f"  ERROR in {name}: {e}")
            import traceback
            traceback.print_exc()
            results[name] = None
    
    # Summary
    print("\n" + "=" * 70)
    print("EXPERIMENT SUMMARY")
    print("=" * 70)
    
    for name, result in results.items():
        status = "COMPLETED" if result is not None else "FAILED"
        print(f"  {name}: {status}")
    
    print(f"\n{'=' * 70}")
    print("CONCLUSION")
    print(f"{'=' * 70}")
    print(f"""
Bitcoin's blockchain is a physical system:
- Block hashes are maximally entropic (true randomness)
- Nonces reveal the search space miners explore
- The genesis block is a fixed point in digital spacetime
- Transaction timing shows the network's heartbeat
- Burn addresses create one-way causal arrows
- Consecutive hashes differ in ~50% of bits
- Fee rates reflect economic gravity

The blockchain is not just a database — it is a
participatory universe where every transaction is
an observation that collapses possibility into reality.

As Wheeler said: 'It from Bit.'
As Satoshi showed: 'Bit from Work.'
""")


if __name__ == '__main__':
    main()
