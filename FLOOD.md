# The Flood — ~600 blocks that change the chain

When a 6-GPU rig connects to the public stratum endpoint, the chain
sprints. Block timestamps force a hard floor of one block per second;
difficulty chases at its maximum 4×-per-window climb; equilibrium —
one block per minute at the rig's full weight — arrives roughly
**640–700 blocks** later. Simulation from the live chain state
(height 25,761, bits frozen at 0x1e010000, the cheapest tier):

- Sprint work added: **≈ 1.04×10¹⁵ hashes** — about **1000× the
  entire fork-native work of the chain's history** (1.04×10¹²),
  compressed into ~2 hours.
- Spacing reaches the 60-second target in the window ending near
  **height ~26,400**.
- Every sprint block is sealed under up to ~500× the work of the
  blocks before it. Provenance you can weigh.

## The lot board (sponsored heights — see SPONSOR.md)

**Sales are open now for any unsold future height**, not only after
the rig connects. The payment watcher is live and registers a valid
paid order automatically after one Bitcoin confirmation.

When the rig connects, the next ~600 unmined heights become the
flood span. That span is assigned from the actual connection height,
so it cannot go stale in this document. Lots are first-come-first-
served at the SPONSOR.md schedule (payment in BTC to
`12jgGaSXJ7jQvrroNZYru13CrjEaZrmDPj`):

| Lot class | Heights | Price (BTC) |
|---|---|---|
| Ordinary / flood ordinary | Any unsold future height, except below | 0.00021 |
| Round height | **26,000** (and each later x,000 height) | 0.01 |
| Equilibration block | The actual height where the DAA settles at the rig's weight, assigned when the rig connects | 0.05 |

A sponsored lot's coinbase pays the buyer's lock and seals the
buyer's tag automatically when the chain reaches the height —
mined by whoever mines it, delivered by construction, verifiable
by anyone with `genealogy_verify.py`.

## Connecting a miner

Stratum v1 at the public endpoint published by the node operator
(the anonymous relay endpoint rotates; the current one is recorded
in the repo's releases/status). Any stratum miner works
(6-GPU rigs: use share difficulty via the shim's defaults; every
valid share at multiplier 1 is a block candidate). Coinbase payouts
go to the node wallet or the height's sponsor — miners earn the
chain's gratitude and, for sponsored heights, nothing is skimmed:
the full 50 EXCAL subsidy pays the sponsor's lock.
