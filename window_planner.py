#!/usr/bin/env python3
"""
Grace-path window planner (Excalibur fork).

Consensus fact (found by genealogy_verify.py, 2026-10-23): at heights not
divisible by the DAA window (60), the node accepts bits == parent's bits
even when they differ from the DAA output. Difficulty is therefore FROZEN
inside a window unless a miner voluntarily adopts the DAA value; it is
only forced at window boundaries (h % 60 == 0).

Advantage, made operational:
  * Mid-window, block production cost is a known constant: expected
    hashes per block = 2^256 / (target(frozen bits) + 1). A mining
    session (e.g., hand-mining a countersignature block) can be planned
    to the hash for the rest of the window.
  * Templates need no DAA recomputation mid-window; the boundary block
    is the only one that must solve required_bits exactly.

This tool is read-only: it reports history (how much the grace path has
already been used, and its local cost delta vs a strict-DAA
counterfactual holding history fixed) and the current window card.
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

def main():
    chain = load_chain()
    hist = [(r["time"], r["bits"]) for r in chain]
    grace_blocks = []
    runs = []            # (start_h, end_h, bits) constant-bits runs, h >= 74
    run_start = None
    for i, r in enumerate(chain):
        h = r["height"]
        if h < gv.DAA_ACTIVATION: continue
        eb = gv.expected_bits(h, hist)
        if r["bits"] != eb and h % gv.DAA_WINDOW != 0 and r["bits"] == chain[i - 1]["bits"]:
            grace_blocks.append(h)
        if run_start is None or r["bits"] != chain[run_start]["bits"]:
            if run_start is not None:
                runs.append((chain[run_start]["height"], chain[i - 1]["height"], chain[run_start]["bits"]))
            run_start = i
    if run_start is not None:
        runs.append((chain[run_start]["height"], chain[-1]["height"], chain[run_start]["bits"]))
    long_runs = sorted(runs, key=lambda x: x[1] - x[0], reverse=True)[:5]

    # local (non-compounded) cost delta of the grace blocks actually taken
    saved = 0
    for h in grace_blocks:
        saved += work(gv.expected_bits(h, hist)) - work(chain[h]["bits"])
    print(f"history: {len(grace_blocks)} grace-path blocks (bits != DAA, == parent, h%60 != 0)")
    print(f"local cost delta of grace blocks vs strict-DAA (same history): {saved:+} hashes "
          f"({'cheaper' if saved > 0 else 'dearer'} under grace)")
    print("longest constant-bits runs (start, end, bits):")
    for s, e, b in long_runs:
        print(f"  h{s}..h{e} ({e - s + 1} blocks) bits {b:#010x}  work/block {work(b)}")

    tip = chain[-1]; th = tip["height"]
    pos = th % gv.DAA_WINDOW
    # current frozen run containing the tip
    cs = th
    while cs > 0 and chain[cs - 1]["bits"] == tip["bits"] and chain[cs]["height"] % gv.DAA_WINDOW != 0 or cs == th:
        if chain[cs - 1]["bits"] != tip["bits"]: break
        cs -= 1
        if cs == th: break
    remaining = gv.DAA_WINDOW - 1 - pos
    print(f"\ncurrent window card:")
    print(f"  tip height {th} (window position {pos}/59), frozen bits {tip['bits']:#010x} "
          f"held since height {chain[cs]['height']}")
    print(f"  blocks remaining in window at frozen bits: {remaining}")
    print(f"  expected hashes per block: {work(tip['bits'])}  |  rest of window: "
          f"{remaining * work(tip['bits'])}")
    print(f"  next boundary (DAA forced): height {th + remaining + 1}")
    print(f"  current window realized spacing: "
          f"{(hist[th][0] - hist[th - pos][0]) / max(pos,1):.1f}s/block (target 60s)")

if __name__ == "__main__":
    main()
