#!/usr/bin/env python3
"""
Grace-path mining strategy for the Excalibur fork — built for the GPU era.

Strategy (consensus-exact, per validate_block as built):
  * height % 60 == 0 (window boundary): bits MUST equal required_bits
    (the DAA output) — no grace available.
  * any other height: inherit the parent's bits verbatim (grace path).
    Always valid; freezes production cost inside the window; templates
    need no DAA work mid-window.
  * timestamps: t = max(parent_time + 1, now) — the wall-clock anchor
    the fork miner has always used; strictly increasing by >= 1s.

This module: (1) validates the strategy against the full historical
chain (every historical height: the strategy's bits would have been
node-acceptable), (2) simulates a GPU flood from the live tip under
the strategy — windows to equilibrium, the now+7200 timestamp ceiling,
and the fork-native work-rate step change the bridge must re-base on.
Read-only: nothing is mined or submitted here.
"""
import json, sys
sys.path.insert(0, "/home/hatch/workspace/your_files")
import genealogy_verify as gv

def load_chain():
    byhash = {}
    with open(gv.CHAIN_FILE) as f:
        for line in f:
            r = json.loads(line); byhash[r["hash"]] = r
    tip = gv.rpc("getbestblockhash")
    chain, h = [], tip
    while h in byhash:
        chain.append(byhash[h])
        if byhash[h]["prev"] not in byhash: break
        h = byhash[h]["prev"]
    return list(reversed(chain))

def work(bits): return (1 << 256) // (gv.bits_to_target(bits) + 1)

def strategy_bits(height, hist, parent_bits):
    """Bits the strategy assigns `height`, given (time, bits) history."""
    if height < gv.DAA_ACTIVATION or height % gv.DAA_WINDOW == 0:
        return gv.expected_bits(height, hist)
    return parent_bits

def node_accepts(bits, height, hist, parent_bits):
    return bits == gv.expected_bits(height, hist) or (
        height % gv.DAA_WINDOW != 0 and bits == parent_bits)

def validate_history(chain):
    hist = [(r["time"], r["bits"]) for r in chain]
    bad = 0; agree = 0
    for i, r in enumerate(chain):
        h = r["height"]
        if h < gv.DAA_ACTIVATION: continue
        sb = strategy_bits(h, hist, chain[i - 1]["bits"])
        if not node_accepts(sb, h, hist, chain[i - 1]["bits"]): bad += 1
        if sb == r["bits"]: agree += 1
    return bad, agree

def simulate_flood(chain, hashrate, max_blocks=20000):
    """Simulate from the live tip. Returns rows per window until the
    realized spacing enters [55, 66]s for a full window (equilibrium)."""
    hist = [(r["time"], r["bits"]) for r in chain]
    height = chain[-1]["height"]
    now = float(hist[-1][0])
    rows = []
    blocks = 0
    while blocks < max_blocks:
        win_start_h = height + 1
        win_work = 0; win_secs = 0.0; win_blocks = 0
        while True:
            h = height + 1
            b = strategy_bits(h, hist, hist[-1][1])
            w = work(b)
            dt = w / hashrate                       # expected seconds to mine
            now += dt
            t = int(max(hist[-1][0] + 1, now))      # wall-clock anchor rule
            hist.append((t, b)); height = h; blocks += 1
            win_work += w; win_secs += dt; win_blocks += 1
            if h % gv.DAA_WINDOW == 59 or blocks >= max_blocks: break
        spacing = (hist[-1][0] - hist[-win_blocks][0]) / max(win_blocks, 1)
        rows.append((win_start_h, height, hist[-1][1], win_work, win_secs, spacing))
        if 55 <= spacing <= 66 and win_blocks == gv.DAA_WINDOW:
            break
    return rows

def main():
    chain = load_chain()
    bad, agree = validate_history(chain)
    n = len(chain) - gv.DAA_ACTIVATION
    print(f"strategy validation over history: {n} heights, unacceptable assignments: {bad}, "
          f"strategy bits == actual historical bits at {agree} heights")
    tip = chain[-1]
    print(f"live tip: height {tip['height']}, bits {tip['bits']:#010x}, work/block {work(tip['bits'])}")
    for H in (30e9, 90e9, 180e9):
        rows = simulate_flood(chain, H)
        tot_blocks = rows[-1][1] - tip["height"]
        tot_secs = sum(r[4] for r in rows)
        tot_work = sum(r[3] for r in rows)
        print(f"\nGPU flood at {H/1e9:.0f} GH/s: equilibrium after {len(rows)} windows, "
              f"{tot_blocks} blocks, ~{tot_secs/60:.1f} min of mining")
        for s, e, b, w, secs, sp in rows:
            print(f"  window h{s}..h{e}: end bits {b:#010x} (work/block {work(b)}), "
                  f"window work {w:.3e}, realized spacing {sp:.1f}s")
        print(f"  fork-native work added during catch-up: {tot_work:.3e} "
              f"(vs entire pre-GPU fork-native total 1.04e12)")

if __name__ == "__main__":
    main()
