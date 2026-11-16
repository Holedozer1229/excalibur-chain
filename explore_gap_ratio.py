"""
Explore the spectral gap ratio lambda_1 / delta_gamma^2 across different
zero heights to determine whether it is truly constant (universal).

This tests the claim from Patch 10 that the Cayley graph Laplacian spectral
gap and the Hilbert-Polya operator level repulsion are connected by a
universal constant.
"""

import sys
import math
sys.path.insert(0, '.')
from spectral_graph_shor import BellStateSpectralAnalysis, RIEMANN_ZEROS, ScalarWave

def compute_gap_ratio_for_subset(zeros_subset):
    """Compute the gap ratio for a subset of Riemann zeros."""
    n = len(zeros_subset)
    if n < 2:
        return None

    # Hilbert-Polya gap: difference between first two zeros in subset
    delta_gamma = zeros_subset[1] - zeros_subset[0]

    # Mean spacing in this subset
    total_spread = zeros_subset[-1] - zeros_subset[0]
    mean_spacing = total_spread / (n - 1)

    # Cayley graph period: number of zeros in subset
    period = n

    # Cayley graph Laplacian spectral gap
    lam1 = 2.0 * (1.0 - math.cos(2.0 * math.pi / period))

    # Gap ratio: lambda_1 / delta_gamma^2
    gap_ratio = lam1 / (delta_gamma ** 2)

    # Mean spacing ratio
    spacing_ratio = delta_gamma / mean_spacing if mean_spacing > 0 else float('inf')

    return {
        'n': n,
        'delta_gamma': delta_gamma,
        'mean_spacing': mean_spacing,
        'period': period,
        'lam1': lam1,
        'gap_ratio': gap_ratio,
        'spacing_ratio': spacing_ratio,
        'zeros_range': (zeros_subset[0], zeros_subset[-1])
    }


def compute_all_pairwise_ratios(zeros):
    """Compute gap ratio for every consecutive pair of zeros."""
    ratios = []
    for i in range(len(zeros) - 1):
        delta = zeros[i+1] - zeros[i]
        # For a pair, period = 2
        lam1 = 2.0 * (1.0 - math.cos(2.0 * math.pi / 2))  # = 2.0
        ratio = lam1 / (delta ** 2)
        ratios.append({
            'pair': (i+1, i+2),
            'gamma1': zeros[i],
            'gamma2': zeros[i+1],
            'delta': delta,
            'lam1': lam1,
            'ratio': ratio
        })
    return ratios


def compute_sliding_window_ratios(zeros, window_size=5):
    """Compute gap ratio for sliding windows of zeros."""
    ratios = []
    for i in range(len(zeros) - window_size + 1):
        subset = zeros[i:i + window_size]
        result = compute_gap_ratio_for_subset(subset)
        if result:
            result['window_start'] = i + 1
            ratios.append(result)
    return ratios


def main():
    print("=" * 70)
    print("  SPECTRAL GAP RATIO EXPLORATION")
    print("  Testing lambda_1 / delta_gamma^2 universality")
    print("=" * 70)

    # --- Section 1: First 15 Riemann zeros ---
    print(f"\n=== FIRST 15 RIEMANN ZEROS ===")
    for i, g in enumerate(RIEMANN_ZEROS):
        print(f"  gamma_{i+1} = {g:.6f}")

    # --- Section 2: Consecutive spacings ---
    print(f"\n=== CONSECUTIVE ZERO SPACINGS ===")
    spacings = []
    for i in range(1, len(RIEMANN_ZEROS)):
        spacing = RIEMANN_ZEROS[i] - RIEMANN_ZEROS[i-1]
        spacings.append(spacing)
        print(f"  delta_gamma_{i+1} = {spacing:.6f}")

    mean_spacing = sum(spacings) / len(spacings)
    min_spacing = min(spacings)
    max_spacing = max(spacings)
    print(f"\n  Mean spacing: {mean_spacing:.6f}")
    print(f"  Min spacing:  {min_spacing:.6f}")
    print(f"  Max spacing:  {max_spacing:.6f}")
    print(f"  Range ratio:  {max_spacing/min_spacing:.4f}")

    # --- Section 3: Gap ratio for growing subsets ---
    print(f"\n=== GAP RATIO FOR GROWING SUBSETS ===")
    print(f"  {'n':>4} {'delta_gamma':>12} {'mean_spacing':>14} {'period':>8} {'lambda_1':>12} {'lambda_1/delta^2':>18} {'spacing_ratio':>14}")
    print(f"  {'-'*4} {'-'*12} {'-'*14} {'-'*8} {'-'*12} {'-'*18} {'-'*14}")

    subset_ratios = []
    for n in range(2, len(RIEMANN_ZEROS) + 1):
        subset = RIEMANN_ZEROS[:n]
        result = compute_gap_ratio_for_subset(subset)
        if result:
            subset_ratios.append(result)
            print(f"  {result['n']:4d} {result['delta_gamma']:12.6f} {result['mean_spacing']:14.6f} "
                  f"{result['period']:8d} {result['lam1']:12.6e} {result['gap_ratio']:18.6e} "
                  f"{result['spacing_ratio']:14.6f}")

    # --- Section 4: Pairwise ratios (period = 2) ---
    print(f"\n=== PAIRWISE RATIOS (period = 2, lambda_1 = 2.0) ===")
    print(f"  {'Pair':>8} {'gamma1':>12} {'gamma2':>12} {'delta':>10} {'ratio':>14}")
    print(f"  {'-'*8} {'-'*12} {'-'*12} {'-'*10} {'-'*14}")

    pairwise = compute_all_pairwise_ratios(RIEMANN_ZEROS)
    for pw in pairwise:
        print(f"  ({pw['pair'][0]},{pw['pair'][1]}) {pw['gamma1']:12.6f} {pw['gamma2']:12.6f} "
              f"{pw['delta']:10.6f} {pw['ratio']:14.6e}")

    pairwise_ratios = [pw['ratio'] for pw in pairwise]
    print(f"\n  Mean pairwise ratio: {sum(pairwise_ratios)/len(pairwise_ratios):.6e}")
    print(f"  Min pairwise ratio:  {min(pairwise_ratios):.6e}")
    print(f"  Max pairwise ratio:  {max(pairwise_ratios):.6e}")

    # --- Section 5: Sliding window analysis ---
    for window in [3, 5, 7]:
        if window > len(RIEMANN_ZEROS):
            continue
        print(f"\n=== SLIDING WINDOW (size={window}) ===")
        print(f"  {'Window':>8} {'delta_gamma':>12} {'lambda_1':>12} {'ratio':>14}")
        print(f"  {'-'*8} {'-'*12} {'-'*12} {'-'*14}")

        windows = compute_sliding_window_ratios(RIEMANN_ZEROS, window)
        window_ratios = []
        for w in windows:
            window_ratios.append(w['gap_ratio'])
            print(f"  [{w['window_start']}:{w['window_start']+window-1}] "
                  f"{w['delta_gamma']:12.6f} {w['lam1']:12.6e} {w['gap_ratio']:14.6e}")

        if window_ratios:
            print(f"\n  Mean ratio: {sum(window_ratios)/len(window_ratios):.6e}")
            print(f"  Std dev:    {math.sqrt(sum((r - sum(window_ratios)/len(window_ratios))**2 for r in window_ratios)/len(window_ratios)):.6e}")
            cv = math.sqrt(sum((r - sum(window_ratios)/len(window_ratios))**2 for r in window_ratios)/len(window_ratios)) / (sum(window_ratios)/len(window_ratios))
            print(f"  CV:         {cv:.6f}")

    # --- Section 6: The key insight ---
    print(f"\n{'='*70}")
    print(f"  KEY INSIGHT")
    print(f"{'='*70}")

    # The gap ratio lambda_1 / delta_gamma^2 is NOT constant for growing subsets
    # because lambda_1 depends on the period (number of zeros), while delta_gamma
    # is the gap between the first two zeros. As n grows, lambda_1 ~ 2*pi^2/n^2
    # but delta_gamma stays fixed at gamma_2 - gamma_1.

    # The TRUE universal constant is the Montgomery pair correlation constant.
    # For GUE, the pair correlation is:
    #   R_2(w) = 1 - |sin(pi*w)/(pi*w)|^2
    # where w = delta_gamma / mean_spacing is the normalized spacing.

    print(f"\n  The ratio lambda_1 / delta_gamma^2 is NOT universal for growing subsets.")
    print(f"  As n increases, lambda_1 ~ 2*pi^2/n^2 while delta_gamma is fixed.")
    print(f"\n  The TRUE universal constant is the Montgomery pair correlation:")
    print(f"    R_2(w) = 1 - |sin(pi*w)/(pi*w)|^2")
    print(f"  where w = delta_gamma / mean_spacing is the normalized spacing.")
    print(f"\n  For the first 15 Riemann zeros:")

    for pw in pairwise[:5]:
        w = pw['delta'] / mean_spacing
        r2 = 1.0 - abs(math.sin(math.pi * w) / (math.pi * w + 1e-30))**2
        print(f"    Pair ({pw['pair'][0]},{pw['pair'][1]}): w = {w:.4f}, R_2(w) = {r2:.6f}")

    # --- Section 7: What IS constant ---
    print(f"\n{'='*70}")
    print(f"  WHAT IS CONSTANT: THE NORMALIZED SPACING DISTRIBUTION")
    print(f"{'='*70}")

    # Normalize all spacings by the mean
    normalized = [s / mean_spacing for s in spacings]
    print(f"\n  Normalized spacings (w_k = delta_gamma_k / mean_spacing):")
    for i, w in enumerate(normalized):
        print(f"    w_{i+1} = {w:.6f}")

    # The GUE prediction for the mean of R_2(w)
    print(f"\n  GUE pair correlation R_2(w) for each spacing:")
    r2_values = []
    for i, w in enumerate(normalized):
        r2 = 1.0 - abs(math.sin(math.pi * w) / (math.pi * w + 1e-30))**2
        r2_values.append(r2)
        print(f"    R_2(w_{i+1}) = {r2:.6f}")

    mean_r2 = sum(r2_values) / len(r2_values)
    print(f"\n  Mean R_2(w): {mean_r2:.6f}")
    print(f"  GUE prediction at w=1: {1.0 - abs(math.sin(math.pi)/(math.pi))**2:.6f}")

    # --- Section 8: The actual universal connection ---
    print(f"\n{'='*70}")
    print(f"  THE ACTUAL UNIVERSAL CONNECTION")
    print(f"{'='*70}")
    print(f"\n  The Cayley graph Laplacian spectral gap lambda_1 = 2(1-cos(2*pi/r))")
    print(f"  and the Hilbert-Polya gap delta_gamma = gamma_2 - gamma_1 are connected")
    print(f"  NOT by a constant ratio, but by the Montgomery pair correlation function.")
    print(f"\n  The universal constant is the GUE level repulsion strength:")
    print(f"    P(s) ~ pi*s/2 for small s (Wigner surmise)")
    print(f"  where s = delta_gamma / mean_spacing is the normalized spacing.")
    print(f"\n  This means:")
    print(f"    - Small spacings are suppressed (level repulsion)")
    print(f"    - The mean spacing encodes the spectral density")
    print(f"    - The Cayley graph period r = N(T) encodes the zero counting function")
    print(f"\n  The connection is: lambda_1 ~ 2*pi^2/N(T)^2 and delta_gamma ~ 2*pi/log(T)")
    print(f"  So lambda_1 / delta_gamma^2 ~ (pi/N(T)^2) / (2*pi/log(T))^2")
    print(f"  ~ log(T)^2 / (4*pi*N(T)^2)")
    print(f"  ~ log(T)^2 / (4*pi*((T/(2*pi))*log(T/(2*pi)))^2)")
    print(f"  ~ 1 / (4*pi*(T/(2*pi))^2)  for large T")
    print(f"\n  This ratio DECAYS as 1/T^2, confirming it is NOT constant.")
    print(f"  The universality is in the NORMALIZED spacing distribution, not the ratio.")

    # --- Section 9: Patch 10 correction ---
    print(f"\n{'='*70}")
    print(f"  PATCH 10 CORRECTION")
    print(f"{'='*70}")
    print(f"\n  The spectral_gap_of_h() method should return the NORMALIZED gap ratio")
    print(f"  that IS universal, not the raw lambda_1/delta_gamma^2 which decays.")
    print(f"\n  The universal quantity is:")
    print(f"    w = delta_gamma / mean_spacing  (normalized spacing)")
    print(f"    R_2(w) = 1 - |sin(pi*w)/(pi*w)|^2  (Montgomery pair correlation)")
    print(f"\n  For the first 15 Riemann zeros, the mean normalized spacing is:")
    print(f"    mean(w) = {sum(normalized)/len(normalized):.6f}  (should be ~1.0 by definition)")
    print(f"    mean(R_2(w)) = {mean_r2:.6f}")
    print(f"\n  This IS the universal constant: the GUE pair correlation function.")


if __name__ == '__main__':
    main()
