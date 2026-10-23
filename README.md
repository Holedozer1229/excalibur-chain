# EXCALIBUR — the fork you can check

EXCAL is a live Bitcoin fork whose block 0 is **Bitcoin block 968,698**.
It does not ask to be believed. Everything below is a measurement you
can re-run.

## What's actually here

- **A living chain.** ~25,600 blocks past the anchor, responsive DAA
  (60-block window, 60-second spacing, 4× clamp), deep-reorg guard.
- **Post-quantum locks, live, not promised.** Since height 25,212 the
  chain enforces PQH locks — `0x02 ‖ hash160(Trifold root)` — spent by
  hash-only Trifold witnesses (~25 KB). No elliptic curves in the spend
  path. The first PQH spend is on-chain (blocks 25,272 / 25,274).
- **A countersigned lineage.** Fork block 25,344 carries a Trifold
  (hash-only) signature over the byte-exact Bitcoin genesis header;
  block 25,351 signs block 25,344's header. Every link verifies with
  nothing but SHA-256.
- **Mine it with any GPU.** `stratum_fork.py` is a stratum shim in
  front of the node RPC: point a standard SHA-256d stratum miner at
  it and you are mining EXCAL, paid to the node wallet. Templates
  follow the chain's window strategy — difficulty is frozen inside
  each 60-block window and retargets exactly at window boundaries,
  so mid-window block cost is a known constant.
- **Sponsored heights are open.** Pick a future block height, pay
  BTC with a self-describing OP_RETURN order, and the live payment
  watcher registers it after one confirmation. When the chain
  reaches that height, its coinbase pays your lock and seals your
  tag automatically. Terms and exact payment format: `SPONSOR.md`;
  the upcoming ~600-block GPU flood inventory: `FLOOD.md`.
- **Verify it in seconds.** `genealogy_verify.py` is a stdlib-only
  reference verifier: it walks the chain from the Bitcoin anchor and
  checks every header, every AuxPoW attachment, and every difficulty
  transition (24,400 self-PoW + 1,431 AuxPoW blocks, including 599
  accepted under the consensus grace rule, replicated exactly).
  Full run: under 10 seconds. Its DAA replication predicted the
  live window-boundary retarget at height 25,680 to the bit — and
  the first stratum-mined block followed at 25,681, ground through
  `stratum_fork.py` by an independent miner implementation and
  accepted by the node. Latest verified checkpoint: height 25,831
  (`genealogy_checkpoint.json`).

## The numbers that matter

- Fork-native proof-of-work since the anchor: ~1.04 × 10¹² hashes.
- A single 6-GPU rig (~90 GH/s) re-bases that in about 90 minutes:
  the catch-up simulation (`grace_miner.py`) shows ~628 blocks and
  ~5 × 10¹⁴ of new fork-native work before difficulty equilibrates
  at the 60-second spacing — a ~500× multiplication of the chain's
  security basis in one afternoon.

## Run it

```
python3 genealogy_verify.py     # check the whole chain from the anchor
python3 window_planner.py       # current window: frozen bits, blocks
                                # left, exact expected cost per block
python3 grace_miner.py          # strategy validation + flood simulation
STRATUM_HOST=0.0.0.0 python3 stratum_fork.py   # serve GPU miners
```

## Honest scope

EXCAL has no market and no price; this repo claims neither. Trifold's
security is hash-only — the novelty is the arrangement (ternary Merkle
tree, pattern-fold key schedule), not a new hardness assumption, and it
is unreviewed. The bridge design in `genealogy-bridge-spec.md` is a
specification with a working reference verifier, not a deployed bridge.
What is claimed is exactly what the verifier checks.

## Powder lots — crowdfund the finale

The Dr. Time broadcast trilogy (AETHER/v2, the 1A1z tribute, the QDAY
countersignature) is armed and waiting on funding. Buy a powder lot
from ~1,200 sats: your own UTXO fires the act you choose, on autopilot,
with a public proof chain. See [POWDER.md](POWDER.md).
