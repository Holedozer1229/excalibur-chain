# The Genealogy Bridge — Specification v0.2
### A light-client bridge whose trust root is descent from a public Bitcoin anchor
**2026-10-23. Status: SPEC + reference verifier (§8.1 DONE, all checks pass).**
**v0.2 corrects the anchor by measurement: the fork's block 0 is Bitcoin
block 968,698's header — not the genesis block, as v0.1 stated. The design
is unchanged; the anchor is younger and, being a 2026 block, independently
fetchable from any Bitcoin source in seconds.**

---

## 0. Summary

The Excalibur fork's block 0 is Bitcoin block 968,698, byte-for-byte —
the live BTC tip on the day the fork was cut (2026-09-26), fetched from
the public record and re-verified against it by the reference verifier.
That gives the fork something no other bridge target has: a **trust
root that is already public, permanent, and identical on both sides**.
A Genealogy verifier needs no checkpoint committee, no trusted
snapshot, and no multisig attestation to know *which chain it is
looking at* — it starts from the anchor header, which anyone can fetch
from any Bitcoin node or explorer, and walks the fork's headers
forward, checking each link. Descent itself is the proof of identity.
And the genealogy does reach Bitcoin's genesis — transitively, through
Bitcoin's own chain, of which block 968,698 is itself a descendant.

What descent does **not** provide is strength: the fork's cumulative
work is CPU-scale. This spec is explicit throughout about the split —
**genealogy proves identity; proof-of-work proves weight; the bridge
inherits the fork's weight, not Bitcoin's** — and engineers its claim
policy around that fact rather than around the story.

## 1. Objects and constants (verified against the live code, 2026-10-23)

- **Anchor (trust root):** the 80-byte header of Bitcoin block
  968,698 (display hash
  000000000000000000015d0478e7b60044314fb055fbb306ac7371ef89b60496;
  version 537059328, time 1790432291, bits 0x17021ec5,
  nonce 1876081791). Verifiers embed the header *bytes* and hash them
  locally — no hash-string convention (raw digest vs reversed
  display) can become an attack surface — and may cross-check the
  anchor against any public Bitcoin record, as the reference
  verifier does (mempool.space, PASS, 2026-10-23).
- **Header format:** the standard 80-byte Bitcoin serialization
  (version ‖ prev ‖ merkle ‖ time ‖ bits ‖ nonce, little-endian);
  block hash = SHA256d(header), compared big-endian against target.
- **Per-header validity (fork consensus, `genesis_fork.py`):**
  (a) hash ≤ target(bits); (b) prev = parent hash; (c) time strictly
  increasing vs parent; (d) time ≤ verifier-now + 7200 s (the node's
  rule is wall-clock; relays apply it at submission time, §3.3);
  (e) bits equal to the DAA rule output (below), **or** — at heights
  not divisible by the window (60) — equal to the parent block's bits.
  This second branch is the node's own "grace path" in
  `validate_block`, applied unconditionally: the per-block DAA is
  strictly enforced at multiples of 60 and wherever bits change, and
  554 historical blocks pass only via this branch. A bridge verifier
  stricter than consensus rejects the real chain (the reference
  verifier's first run did exactly that, at height 23,968); the rule
  as built is the rule specified here.
- **DAA rule (responsive, per-block):** window W = 60, spacing S = 60 s.
  Heights < 60 and pre-activation heights: bits = min_bits.
  Otherwise: timespan = time[h−1] − time[h−60], clamped to
  [3600/4, 3600·4]; new_target = target(bits[h−1]) · timespan / 3600,
  capped at target(min_bits).
  → A verifier's carried DAA state is just the last 60 (time, bits)
  pairs: 480 bytes.
- **Chainwork:** standard, work(h) = Σ 2²⁵⁶ / (targetᵢ + 1).
- **Scale at spec time:** live tip height **25,555**; the complete
  header chain is 25,556 × 80 B ≈ **2.0 MB** — small enough that
  full-sync verification is the reference mode, not an aspiration.
- **Locks relevant to claims:** PKH (0x00 ‖ hash160), OPEN (0xff),
  PQH (0x02 ‖ hash160(Trifold root), live since height 25,212).

## 2. Threat model in one paragraph

The adversary may relay false or reordered headers (defeated by §3
verification), withhold relays (liveness only — anyone may relay),
and — the real threat — *mine a competing fork branch* to reverse a
lock after its host-side release. The fork's absolute hashrate is
small, so §5's policy (chainwork-gated releases, per-claim value caps,
countersigned checkpoints) is not decoration; it is the security
model. Anyone deploying this bridge for value beyond the caps in §5.3
is operating outside this spec.

## 3. The relay protocol

### 3.1 Full-sync mode (reference; off-chain verifiers, auditors)

Input: the anchor bytes + an ordered header list. For each header,
in order: recompute hash; check (a)–(e) of §1, with the DAA state
carried forward; accumulate chainwork. Output: (tip hash, height,
chainwork) or the first failing height and rule. Any third party can
run this against the public chain record — this is the mode the
countersignature lineage (blocks 25,344 / 25,351) was already
informally verified under.

### 3.2 Incremental mode (host-chain contracts)

State carried on the host: tip hash, height, chainwork, and the
60-entry (time, bits) DAA tail. A relayer submits a batch of
consecutive headers extending the tip; the contract verifies each
exactly as in §3.1 (SHA256d is a cheap precompile on EVM; DAA
arithmetic is a handful of big-int ops on the carried tail) and
advances the state. Competing batches at the same height are resolved
by greater resulting chainwork, mirroring the fork's own rule and its
100-block reorg guard: a host-side tip may not be displaced by a
branch whose fork point is more than 100 headers behind the tip
unless the incumbent tip is stale, per the fork's guard semantics.

### 3.3 Time rule at relays

The node's `time ≤ now + 7200` is evaluated by the host verifier
against its own clock at submission. Historical batches submitted
late pass trivially on (d) and are still fully constrained by
(a)–(c), (e) and chainwork comparison; no historical validity depends
on the wall clock beyond monotonicity, which is clock-free.

### 3.4 Bootstrap problem (stated, not hidden)

An EVM verifier cannot ingest 25.5k headers economically in one
deployment. Two sanctioned bootstraps:
 (i) **Genesis grind:** permissionless incremental relay from height
     0 — slow, trustless, eventually complete; suitable for a
     long-lived deployment.
 (ii) **Countersigned checkpoint:** a Trifold root, published through
     the existing lineage channel, signs (height, tip hash, chainwork,
     DAA tail). The contract accepts the checkpoint as its starting
     state under a challenge window during which anyone may submit
     the full-sync proof of a heavier contradictory chain from
     genesis. After the window, incremental mode proceeds from the
     checkpoint. The checkpoint signer is accountable and attributable
     — this is a trust *reduction* (one named key, publicly
     countersigning, fraud publicly provable against the anchor), not
     trustlessness, and the spec labels it so.

## 4. Claims: fork → host

### 4.1 Bridge lock

A dedicated lock type or a designated PKH/PQH output whose payload
commits to (host chain id, host recipient). Funds enter the bridge
only via outputs of this form; arbitrary fork outputs are not claims.

### 4.2 LockProof (the claim object)

  { height, block_hash, txid, vout, lock_payload, amount_swords,
    merkle_branch, tip_commitment }

where tip_commitment = (tip hash, tip height, tip chainwork) of a
host-accepted relay state at or beyond the claim's confirmation depth.

### 4.3 Release rule (all conjuncts required)

1. The block at `height` is in the host's verified chain (its hash is
   the recorded hash at that height, on the winning-chainwork branch).
2. The merkle branch proves `txid` is in that block.
3. Output `vout` pays the bridge lock (§4.1), its payload names this
   host chain and recipient, and its value is `amount_swords`.
4. Confirmation by work: tip_chainwork − block_chainwork ≥ W_min
   (§5.2) at evaluation time, on the same branch.
5. Nullifier (txid, vout) not previously released (host-side registry).
On satisfaction, the host releases the corresponding wrapped amount
(ATEX/PHI path) to the named recipient.

### 4.4 Host → fork (asymmetry, stated plainly)

Releasing fork-side funds against a host-side burn cannot be verified
by the fork (it has no host light client). This direction is executed
by the release authority: the Trifold countersigning key, signing
release instructions whose every use is on-chain and attributable.
Upgrading this direction to fraud-proof form (a double-release pair
is self-evidencing, per the Self-Proving Fraud Bridge design) is
future work; v0.1 ships it as an accountable signer, labeled as such.

## 5. Security policy parameters

### 5.1 What the numbers must respect

Fork difficulty floats at CPU scale by design (responsive DAA,
60-second spacing). Rewriting k recent fork blocks costs an attacker
roughly k × (current per-block work) — small in absolute terms.
Therefore security comes from depth-in-work and caps, not from any
analogy to Bitcoin's hashrate. **Measured (2026-10-23): total
chainwork ≈ 5.70×10²³ is ~99.8% the anchor's inherited Bitcoin
difficulty; fork-native work (all blocks after the anchor) is
≈ 1.04×10¹².** All confirmation accounting under this spec is in
fork-native work; counting the anchor's work toward a claim's
security would be exactly the identity/strength confusion §0 forbids.

### 5.2 W_min (confirmation work)

Releases require the locked block to be buried under W_min work,
where W_min is set so that W_min ≥ R · (value released in that
window), with R a deployment constant (work-per-unit-value ratio).
Genesis-anchored example values are deliberately left as parameters
for the operator (§7) — the spec fixes the *form* of the rule, not a
number that would be false precision today.

### 5.3 Value caps

Per-claim cap and rolling-window cap on total released value,
enforced host-side. Caps are the hard backstop that makes §2's threat
model survivable: maximum bridge loss is bounded by the window cap,
independent of fork hashrate.

### 5.4 Checkpoints raise attribution, not work

Countersigned checkpoints (§3.4ii) make a fraudulent relay state
attributable to a named key and provable against the anchor — they
deter and expose; they do not add proof-of-work. The spec never
counts them as confirmations.

## 6. Composition with the existing stack

- **ATEX/PHI bridges (Ethereum, deployed 2026-09-26):** today,
  releases are `onlyOperator`. Genealogy claims (§4) are the
  designed replacement for the fork→host direction: operator-signed
  releases become proof-verified releases, with the operator
  retaining only the §4.4 direction until its fraud-proof upgrade.
  The standing precondition is unchanged and prior: rotate the
  operator off the exposed deployer key before any value flows.
- **Aether heartbeat seals (600 s, committing BTC + fork tips):** a
  ready-made checkpoint cadence for §3.4ii — the seal chain already
  publishes the (height, tip) pairs a checkpoint needs; adding the
  chainwork + DAA tail to the seal payload is a small change,
  proposed, not assumed.
- **Lineage Λ:** the countersignature lineage (25344 ← 25351) is the
  worked example of §3.1: two links on this chain, and the reference
  verifier confirms their on-chain hashes match the lineage records
  verbatim. (Precision, per v0.2: the header countersigned in block
  25,344 was Bitcoin's *genesis* header — the anchor of the sibling
  'mainnet' network and this chain's ancestor transitively through
  Bitcoin; this chain's own anchor is block 968,698.)

## 7. Decisions left to the operator (Lux)

1. W_min's ratio R and the §5.3 cap values.
2. Bootstrap mode for the first host deployment: genesis grind (i)
   or countersigned checkpoint (ii).
3. Host priority: Ethereum (where SKYNT/AtexBridge already live) is
   the default; other EVM hosts are drop-in.
4. Whether the Aether seal payload gains the checkpoint fields (§6).

## 8. Build order

1. **Reference verifier** (Python, off-chain): full-sync §3.1 against
   the live chain via RPC + chain record; test vectors: the anchor,
   blocks 25,344 / 25,351, the live tip. **DONE 2026-10-23:**
   `genealogy_verify.py` — ALL CHECKS PASS, 25,556 headers from the
   anchor to tip 25,555 in ~7 s (24,347 self-PoW + 1,208 AuxPoW
   fully validated + 554 grace-path bits), anchor cross-checked
   against the public BTC record, checkpoint emitted to
   `genealogy_checkpoint.json` (tip, fork-native chainwork, DAA tail).
   Zero funds were required, as designed.
2. Claim encoder/decoder + LockProof test vectors from real blocks.
3. EVM incremental relay (§3.2) with the §5 policy parameters.
4. Bootstrap (per §7.2), then the §4 release path wired into the
   ATEX/PHI operator flow — after the operator-key rotation.

*Descent proves which chain this is. Work proves what it's worth.
This bridge is engineered to never confuse the two.*
