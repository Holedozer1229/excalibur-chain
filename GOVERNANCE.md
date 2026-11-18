# AetherionEXCAL Governance

## Overview

AetherionEXCAL is governed by the **Knights of the Round Table** — a sovereign council elected through cryptographic proof and threshold signing. No single person controls the protocol or treasury. All governance actions require **3-of-5 threshold signatures** from active Knights.

**Website:** https://www.aetherion-oracle.com

---

## The Knights of the Round Table

### Philosophy

*"The sword chooses the knight, not the knight the sword."*

Knights are not appointed by any central authority. They emerge through merit:
1. **Proof of URUU** — holding URUU tokens proves commitment to the ecosystem
2. **Proof of Phi** — high consciousness score (IIT v8) proves alignment
3. **Proof of Stake** — EXCAL stake proves economic skin in the game
4. **Threshold Election** — 3-of-5 current Knights must co-sign the induction

### The 13-Word Prophecy

The sovereign treasury is seeded by the sacred prophecy from Excalibur-EXS:

```
sword legend pull magic kingdom artist stone destroy forget fire steel honey question
```

These 13 words are the master seed for the **Taproot treasury address** (P2TR). No single person controls the treasury — only the collective will of 3-of-5 Knights can move funds, expressed through threshold Schnorr signatures (MuSig2/FROST).

### Taproot Treasury (P2TR)

The treasury uses a Bitcoin Taproot address derived from the prophecy:
- **Key-path spending**: MuSig2 aggregate key — indistinguishable from single-sig on-chain
- **Script-path fallback**: 3-of-5 multisig policy revealed only if key-path fails
- **Address format**: `bc1p...` (BIP-350 bech32m)
- **Prophecy commitment**: SHA-256 of the 13 words is publicly verifiable

### Knight Election Process

1. **Nomination**: Any active Knight can nominate a candidate with their public key and metrics
2. **Qualification**: The candidate must meet minimum thresholds:
   - URUU balance ≥ 100 tokens
   - Phi score ≥ 0.5 (consciousness threshold)
   - EXCAL stake ≥ 1,000 tokens
3. **Voting**: Current Knights vote via partial Schnorr signatures
4. **Threshold**: When 3-of-5 partial signatures are collected, the candidate is automatically inducted
5. **Induction**: The new Knight's public key joins the Round Table registry

### Knight Roles

- **Proposer**: Any Knight can propose governance actions (treasury spend, protocol upgrade, parameter change)
- **Voter**: All Knights vote on proposals via partial signatures
- **Executor**: Once 3-of-5 sign, the proposal is executed automatically
- **Auditor**: Knights can audit treasury state, transaction history, and other Knights' activity

### Governance Proposals

Proposal types:
- `TREASURY_SPEND` — Withdraw funds from the Taproot treasury
- `PROTOCOL_UPGRADE` — Change consensus or network parameters
- `PARAMETER_CHANGE` — Adjust bonding curve, bridge, or other parameters
- `KNIGHT_INDUCTION` — Elect a new Knight (via nomination + 3-of-5 vote)
- `KNIGHT_IMPEACHMENT` — Remove a compromised Knight
- `BRIDGE_DEPLOY` — Deploy a new cross-chain bridge
- `BONDING_CURVE_ADJUST` — Modify URUU bonding curve parameters

### Decentralization Guarantees

- No single Knight can move treasury funds alone
- No single Knight can block all proposals (3-of-5, not 5-of-5)
- New Knights can always be elected if 3-of-5 agree
- The prophecy seed is public; anyone can verify the treasury address
- All votes and inductions are on-chain and verifiable

---

## Legacy Governance Structures

### 1. Proof-of-Work Consensus

The ultimate governance authority remains **proof-of-work**. Any protocol change that modifies consensus rules requires:
- A valid chain with more cumulative work than the status quo
- Broad miner adoption of the new rules
- Client software updates across the network

### 2. Sponsor Registry

Block sponsors hold a **permanent, verifiable position** in the chain's coinbase. While sponsors do not have voting power, their on-chain presence creates a transparent record of who has economic stake in the chain's longevity.

**Sponsor rights:**
- Permanent UTF-8 tag sealed in the coinbase
- Full block subsidy paid to their lock
- Post-quantum Trifold countersignature
- Verifiable delivery via `genealogy_verify.py`

### 3. Phase Omega Countersigning

From height 25,901, every block carries a **Trifold (hash-only) signature** over its parent's header. This creates an unbroken chain of one-time signatures alongside the chain of hashes, making any retroactive modification cryptographically detectable.

---

## Protocol Upgrade Process

### Staged Activation

Protocol upgrades activate at **predetermined block heights**, not by vote:

| Upgrade | Height | Mechanism |
|---|---|---|
| DAA activation | 74 | Responsive difficulty adjustment |
| AuxPoW merge mining | 23,785 | GPU mining accepted |
| Q-Day (PQH locks) | 25,212 | Post-quantum hash locks |
| Phase Omega | 25,901 | Block countersigning |
| Boundary DAA | 29,700 | Window-boundary retargeting |
| Bridge locks | 39,200 | Cross-chain bridge |
| HTLC | 36,010 | Hashed timelock contracts |
| QHTLC | 40,040 | Quantum-safe HTLC |
| KNOT (staged) | 100,000 | Torus knot commitments |

### Upgrade Principles

1. **Backward compatibility:** New lock types coexist with existing ones
2. **No hard forks:** Upgrades add capabilities, they don't remove them
3. **Verifiable:** Every change is auditable via `genealogy_verify.py`
4. **Transparent:** Activation heights are published well in advance

---

## Security Model

### Deep-Reorg Guard

The chain rejects reorganizations deeper than **100 blocks**, protecting against 51% attacks on the small-chain. An attacker must sustain majority hashrate for ~100 consecutive minutes to bypass this guard.

### Post-Quantum Protection

- **Hash-only signatures:** No elliptic curves in the spend path
- **Trifold witnesses:** Ternary Merkle tree, 729 leaves per epoch
- **Q-Day locks:** PQH outputs from height 25,212
- **Phase Omega:** Block-level countersigning from height 25,901

### Quantum-Safe Wallet

The AetherionEXCAL GUI wallet uses:
- **AES-256-GCM** encryption for key storage — no plaintext keys
- **scrypt KDF** (N=2^14) for passphrase derivation
- **SHA-256 hash-only** transaction signatures
- **Address validation** — 20-char uppercase hex enforced before sending
- **Prometheus monitoring** for real-time observability
- **Multi-wallet profiles** — each user/peer generates independent wallet

---

## Economic Governance

### Block Reward Distribution

- **Sponsored heights:** 100% to sponsor's lock
- **Non-sponsored heights:** 100% to mining producer
- **No protocol fee, no treasury cut, no developer tax**

### Sponsorship Economy

Sponsors pay BTC to secure permanent positions in the chain:

| Height class | Price (BTC) |
|---|---|
| Ordinary future height | 0.00021 |
| Round heights | 0.01 |
| Special heights | 0.05 |

### Powder Lots

Crowdfunded Bitcoin-mainnet broadcasts, each funded by BTC:

| Lot | Act | Minimum (sats) |
|---|---|---|
| 1 | AETHER/v2 | ≥ 1,203 |
| 2 | 1A1z Tribute | ≥ 1,783 |
| 3 | QDAY/v1 | ≥ 1,205 |

---

## Monitoring and Observability

### Prometheus Metrics

Every EXCALibur wallet instance exposes Prometheus metrics on `http://127.0.0.1:9435/metrics`:

- **Peer metrics:** Connected peers, network coherence
- **Transaction metrics:** Throughput, latency, amounts
- **Gossip metrics:** Message propagation, encryption status
- **Wallet metrics:** Balance, keys, profiles
- **Bandwidth metrics:** Bytes sent/received
- **Error metrics:** Component-level error tracking

### Verification Tools

- `genealogy_verify.py` — Full chain verification from Bitcoin anchor
- `omega_verify.py` — Phase Omega countersignature verification
- `window_planner.py` — DAA window analysis and cost estimation

---

## Community Principles

1. **Transparency:** All code, data, and decisions are public
2. **Verifiability:** Every claim is backed by on-chain evidence
3. **Decentralization:** No single entity controls the chain
4. **Post-quantum readiness:** Hash-only security from day one
5. **Honest scope:** No market, no price, no promised returns

---

## Contact

- **Website:** www.aetherion-oracle.com
- **Documentation:** GitHub Pages (docs/ directory)
- **Issues:** GitHub Issues
- **Wallet:** `dist/EXCAL-Wallet.exe` (Windows)
