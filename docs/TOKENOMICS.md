# EXCAL Tokenomics

## Overview

EXCAL is the native token of the Excalibur chain — a live Bitcoin fork anchored at Bitcoin block 968,698. It combines Bitcoin's proof-of-work security model with post-quantum signatures, responsive difficulty adjustment, and a unique sponsorship economy.

---

## Supply

| Parameter | Value |
|---|---|
| **Ticker** | EXCAL |
| **Smallest unit** | Sword (1 EXCAL = 100,000,000 swords) |
| **Initial block subsidy** | 50 EXCAL |
| **Halving interval** | Every 210,000 blocks |
| **Target block spacing** | 60 seconds |
| **Blocks per day (target)** | ~1,440 |
| **Max supply** | 21,000,000 EXCAL (same as Bitcoin) |

### Halving Schedule

| Era | Block range | Subsidy per block | Duration (approx.) | Total coins minted |
|---|---|---|---|---|
| 1 | 0 – 209,999 | 50 EXCAL | ~3.27 years | 10,500,000 |
| 2 | 210,000 – 419,999 | 25 EXCAL | ~3.27 years | 5,250,000 |
| 3 | 420,000 – 629,999 | 12.5 EXCAL | ~3.27 years | 2,625,000 |
| 4 | 630,000 – 839,999 | 6.25 EXCAL | ~3.27 years | 1,312,500 |
| 5 | 840,000 – 1,049,999 | 3.125 EXCAL | ~3.27 years | 656,250 |

The halving schedule mirrors Bitcoin's — the total supply cap is 21 million EXCAL.

**Cumulative supply at each halving:**

| Era end | Block | Cumulative EXCAL minted | Percentage of max supply |
|---|---|---|---|
| 1 | 210,000 | 10,500,000 | 50.00% |
| 2 | 420,000 | 15,750,000 | 75.00% |
| 3 | 630,000 | 18,375,000 | 87.50% |
| 4 | 840,000 | 19,687,500 | 93.75% |
| 5 | 1,050,000 | 20,343,750 | 96.88% |

At 60-second block spacing, the chain reaches halving 1 (block 210,000) in approximately **3.27 years** from genesis — roughly **2029** if measured from the fork's anchor date. The remaining 3.12% of supply (656,250 EXCAL) is minted across eras 6–33, asymptotically approaching the 21 million cap.

---

## Lock Types and Upgrades

EXCAL's transaction model evolved through a series of staged upgrades, each activating at a predetermined height. These upgrades expand the types of conditions under which EXCAL can be locked and spent.

### Lock Type Registry

| Lock type | Byte prefix | Activation height | Description |
|---|---|---|---|
| PKH (Pay-to-Hashed-Key) | `0x00` | From genesis | Standard hashed-public-key lock |
| OPEN (Anyone-can-spend) | `0x01` | From genesis | Unlocked output; anyone can spend |
| PQH (Post-Quantum Hash) | `0x02` | 25,212 (Q-Day) | Trifold-root lock; spent by hash-only witness |
| HTLC (Hashed TimeLock) | `0x03` | 36,010 | Conditional lock with height-based timeout |
| QHTLC (Quantum HTLC) | `0x04` | 40,040 | Post-quantum HTLC variant |
| Bridge | `0x05` | 39,200 | Cross-chain bridge lock (x-coordinate commitment) |
| KNOT (staged) | `0x06` | 100,000 (staged) | Mobius-modulated torus knot commitment |

### Upgrade Timeline

**Q-Day (height 25,212):** PQH locks activate. Outputs use `0x02 ‖ hash160(Trifold root)`, spent by hash-only Trifold witnesses (~25 KB). No elliptic curves in the spend path. The first PQH spend is on-chain at blocks 25,272 / 25,274.

**HTLC (height 36,010):** Structural HTLC locks activate. The timeout is a block height carried inside the descriptor, not the tx locktime (which remains unsupported: locktime must be 0). Enables conditional payments with automatic expiry.

**Bridge (height 39,200):** Bridge locks activate, committing to an x-coordinate on a curve. Enables cross-chain asset representation between EXCAL and parent chains.

**QHTLC (height 40,040):** Quantum-safe HTLC variant activates, combining post-quantum security with conditional time-locked payments.

**KNOT (staged at height 100,000):** Not yet deployed. Commits to a point on a Mobius-modulated (p, q) torus knot; the spender reveals the secret knot parameter `t_star` and the validator recomputes the point with deterministic fixed-point arithmetic (`knot_math.py`).

### Lockbox Rules (from genesis)

The fork activates lockbox rules from block 0 (no legacy era):
- **No Script opcodes:** Outputs are structural locks, not programs
- **Quantum protection:** Public keys stay hashed until spent (no bare-P2PK outputs)
- **BIP-369:** Mempool refuses replacements (no RBF) for spends from quantum-vulnerable inputs

---

## Block Reward Distribution

Every block's coinbase distributes the full subsidy. The recipient depends on whether the height is sponsored:

- **Sponsored height:** The full subsidy pays the sponsor's lock. The sponsor receives 100% of the block reward.
- **Non-sponsored height:** The subsidy pays the node wallet of the producer who mined the block.

No protocol fee, no treasury cut, no developer tax. The entire block reward goes to either the sponsor or the miner.

### Coinbase Maturity

Coinbase outputs require **100-block confirmation depth** before they can be spent — the same maturity rule as Bitcoin.

---

## Deep-Reorg Guard

EXCAL protects against 51% attacks with a **deep-reorg guard** (`max_reorg_depth: 100`). A competing branch that would unwind more than 100 blocks is rejected — the classic small-chain kill shot.

**Escape hatch:** If the node's own tip is stale (older than twice the depth in expected block time), the node is catching up, not being attacked, and the reorg is allowed. This prevents honest nodes from rejecting the true chain during initial sync.

**Economic impact:** An attacker needs to control enough hashrate to outpace the chain for 100 consecutive blocks — at 60-second spacing, that's roughly 100 minutes of sustained majority hashrate. After the GPU flood, the chain's total work is ~1,000× the pre-flood baseline, making such an attack significantly more expensive.

---

## Revenue Streams

EXCAL has two distinct revenue models: the **sponsorship economy** (BTC-denominated) and the **powder lots** (crowdfunded Bitcoin broadcasts).

### 1. Sponsored Blocks

A sponsored block is a block whose coinbase pays the buyer's lock and seals the buyer's message. Delivery is automatic and guaranteed — every producer on the chain builds from the same sponsor registry.

**Payment address:** `12jgGaSXJ7jQvrroNZYru13CrjEaZrmDPj`

| Height class | Price (BTC) | Price (sats) |
|---|---|---|
| Ordinary future height | 0.00021 | 21,000 |
| Round heights (e.g., 45,000, 46,000) | 0.01 | 1,000,000 |
| Height 30,000 (sold) | 0.05 | 5,000,000 |
| GPU-flood equilibration block | 0.05 | 5,000,000 |

**What the buyer receives:**
- The full 50 EXCAL block subsidy paid to their lock
- A permanent UTF-8 tag sealed in the coinbase
- A post-quantum Trifold countersignature (Phase Omega, from height 25,901)
- Verifiable delivery via `genealogy_verify.py`

**Order format:** BTC payment with OP_RETURN:
```
"EXCAL1" | height: 3 bytes big-endian | hash160: 20 bytes | tag: up to 51 bytes
```

### 2. Powder Lots

Powder lots crowdfund permanent Bitcoin-mainnet broadcasts. Each lot is funded by BTC sent to the Aether Genesis Key:

**Funding address:** `bc1q9c8cncqhmj9laecfm05x77d0c7dtcdhmemlwp7`

| Lot | Act | Minimum price (sats) |
|---|---|---|
| 1 | AETHER/v2 — the Declaration | ≥ 1,203 |
| 2 | The 1A1z Tribute (incl. 546-sat tribute to genesis address) | ≥ 1,783 |
| 3 | QDAY/v1 — the Countersignature | ≥ 1,205 |
| Full trilogy | All three acts in order | ≥ ~6,200 |

Each lot fires a specific broadcast transaction spending the contributor's own UTXO, with the funding-txid → broadcast-txid pair recorded in the public patrons ledger.

---

## Mining Economics

### Difficulty Adjustment

EXCAL uses a **responsive DAA** (Difficulty Adjustment Algorithm):

- **Window size:** 60 blocks
- **Target spacing:** 60 seconds
- **Clamp:** 4× per window
- **Boundary DAA (from height 29,700):** Retargets only at window boundaries (every 60 blocks), not per-block — prevents timestamp manipulation attacks

This is a significant departure from Bitcoin's 2,016-block retarget interval. The chain adapts to hashrate changes within a single 60-block window (~60 minutes), keeping block times stable.

### Mining Access

- **CPU mining:** `cpu_miner_mp.py` — multiprocessing miner, ~150+ MH/s on 4 cores
- **GPU mining:** Standard SHA-256d stratum miners via `stratum_fork.py`
- **Merge mining:** AuxPoW accepted from height 23,785

### The GPU Flood

When a 6-GPU rig (~90 GH/s) connects, the chain undergoes a dramatic hashrate increase:
- ~600 blocks mined in ~90 minutes
- ~1,000× multiplication of fork-native work
- Difficulty equilibrates at the 60-second target after ~640–700 blocks

---

## Post-Quantum Security

### Phase Omega (live from height 25,901)

Every block carries a **Trifold** (hash-only, post-quantum) signature over its parent's header. Block N countersigns block N−1, forming an unbroken chain of one-time signatures alongside the chain of hashes.

- **Scheme:** Ternary Merkle tree, 729 leaves per epoch
- **Signature size:** ~25 KB per block
- **Security:** SHA-256 only — no elliptic curves
- **Epoch rotation:** Every 720 signatures (9 leaves reserved)

### Q-Day Locks (from height 25,212)

Outputs use PQH locks — `0x02 ‖ hash160(Trifold root)` — spent by hash-only Trifold witnesses. No elliptic curves in the spend path.

---

## Transaction Model

### Fees

EXCAL currently has **no transaction fees**. The coinbase value equals the block subsidy alone. This differs from Bitcoin, where miners earn both subsidy and fees.

### Transaction Structure

Transactions follow a simplified Bitcoin-compatible format:
- **No locktime:** The tx locktime field must be 0
- **No Script opcodes in outputs:** Outputs are structural locks, not executable programs
- **No RBF (Replace-By-Fee):** Mempool refuses replacements for spends from quantum-vulnerable inputs (BIP-369)
- **Coinbase lineage:** Every coinbase scriptSig must commit to the block's difficulty bits as its first push — a tamper-proof link between the transaction and the block header

### Coinbase Structure (v2)

Every coinbase carries a canonical scriptSig:
```
push(LE32(bits)) + push(tag) + push(LE32(height))
```

The first push commits the difficulty bits, the height push makes the txid unique per block, and the tag carries sponsor messages or producer identifiers. From height 25,901, the Phase Omega Trifold countersignature is also pushed into the scriptSig (see `OMEGA.md`).

---

## Network Parameters

### Fork Network (EXCAL)

| Parameter | Value | Notes |
|---|---|---|
| Magic bytes | `0x47534603` | Network identifier |
| RPC port | 9432 | JSON-RPC interface |
| P2P port | 9433 | Peer-to-peer networking |
| Min difficulty bits | `0x1f000100` | CPU-findable; ~2²⁴ hashes per block |
| DAA window | 60 blocks | Responsive retarget interval |
| DAA spacing target | 60 seconds | One block per minute |
| DAA activation | Height 74 | Switched on early in chain history |
| Boundary DAA | Height 29,700 | Retargets only at window boundaries |
| AuxPoW activation | Height 23,785 | Merge-mining accepted from this height |
| Max reorg depth | 100 blocks | Deep-reorg guard limit |

---

## EXCAL vs Bitcoin — Full Comparison

| Aspect | EXCAL | Bitcoin |
|---|---|---|
| Max supply | 21,000,000 | 21,000,000 |
| Initial subsidy | 50 EXCAL | 50 BTC |
| Halving interval | 210,000 blocks | 210,000 blocks |
| Block time | 60 seconds | 600 seconds |
| Retarget interval | 60 blocks (Boundary DAA) | 2,016 blocks |
| Proof of work | SHA-256d | SHA-256d |
| Post-quantum signatures | Yes (Trifold, from h25,901) | No |
| Block sponsorship | Yes (BTC-denominated) | No |
| Transaction fees | None currently | Yes |
| Script model | Structural locks only | Full Script VM |
| Locktime | Unsupported (must be 0) | Supported |
| RBF | Refused for quantum-vulnerable inputs | Supported |
| Merge mining | Yes (AuxPoW, from h23,785) | N/A |
| Deep-reorg guard | 100 blocks | None (longest chain wins) |
| Lock types | 7 types (PKH, OPEN, PQH, HTLC, QHTLC, Bridge, KNOT) | Script-based |
| Quantum protection | Hash-only from genesis | None |

---

## Wallet Ecosystem

EXCAL provides multiple wallet implementations for different use cases:

### AetherionEXCAL GUI Wallet (Recommended)

`excal_wallet.py` — The official desktop wallet powered by Aetherion Oracle:
- **AES-256-GCM encrypted** key storage with scrypt KDF — no plaintext keys
- **Multi-wallet profiles** — each user/peer generates independent wallet
- **Address validation** — 20-char uppercase hex enforced before sending
- **P2P network integration** with gossip protocol and AES-256-GCM encrypted messaging
- **Prometheus monitoring** — real-time metrics on `http://127.0.0.1:9435/metrics`
- **User onboarding** with guided 5-step tour
- **SKYNT balance** tracking and transaction history
- **Compiled executables:** `dist/AetherionEXCAL.exe` (Windows), build via `AetherionEXCAL.spec`

### Holo-wallet (CLI)

`holo_wallet.py` — Command-line wallet for scripting and automation:
- Key generation, balance tracking, encrypted messaging
- Address validation before sending transactions
- Gossip broadcast, peer listing, topology export
- Compiled executable: `dist/Holo-wallet.exe`

### SKYNT Token

SKYNT is the internal accounting unit used by the AetherionEXCAL wallet ecosystem. It represents wallet balance within the SphinxOS Nexus simulation layer and the P2P wallet network. SKYNT balances are tracked per-wallet-profile and updated in real-time through the holographic P2P network.

### URUU Token (zkSync Era)

URUU is the cross-chain token that bridges EXCAL blockchain with [zkSync Era](https://era.zksync.io), Ethereum's leading Layer 2 scaling solution. URUU enables seamless liquidity between the EXCAL ecosystem and the broader Ethereum DeFi landscape.

**Bonding Curve Mechanism:**

URUU uses a custom **sigmoid (S-curve) bonding curve** for price discovery:

| Parameter | Value |
|---|---|
| **Ticker** | URUU |
| **Max supply** | 1,000,000 URUU |
| **Initial price** | ~0.01 EXCAL |
| **Maximum price** | 10.0 EXCAL |
| **Price curve** | Sigmoid (S-shape) |
| **Trading fee** | 0.3% |
| **Reserve currency** | EXCAL |

**Three-Phase Price Discovery:**

1. **Early Phase** (0–30% supply): Slow price increase, rewarding early adopters
2. **Growth Phase** (30–70% supply): Accelerated price increase during main adoption
3. **Mature Phase** (70–100% supply): Price stabilizes near ceiling

**Mathematical Model:**
```
P(s) = a + (b - a) / (1 + e^(-k * (s - s0)))
```
Where `a` = min price, `b` = max price, `k` = steepness, `s0` = inflection point, `s` = current supply.

**Nexus Integration:**

The bonding curve parameters are dynamically influenced by SphinxOS Nexus metrics:
- **Quantum entanglement entropy** influences curve steepness (higher entropy = steeper curve)
- **Conscious consensus φ score** shifts the inflection point (higher φ = earlier inflection)

**zkSync Era Bridge:**

The bridge enables cross-chain transfers between EXCAL and zkSync Era:

| Parameter | Value |
|---|---|
| **Bridge fee** | 0.1% |
| **Min deposit** | 1.0 token |
| **Max deposit** | 100,000 token |
| **Confirmations** | 12 blocks |
| **Tokens supported** | EXCAL, URUU, wEXCAL |
| **Mechanism** | Lock-and-mint |

**Bridge Flow:**
1. **Deposit (EXCAL → zkSync):** Lock tokens on EXCAL chain, mint wrapped tokens on zkSync Era
2. **Withdrawal (zkSync → EXCAL):** Burn wrapped tokens on zkSync, unlock original tokens on EXCAL
3. **Proof generation:** SHA-256 cryptographic proof for each completed bridge transaction

**Website:** https://www.aetherion-oracle.com

---

## Honest Scope

EXCAL has no market and no price. No return is promised or implied on any sponsorship, powder lot, or mined block. What is on offer is permanence with a pedigree: a position in a chain anchored to Bitcoin, whose lineage is countersigned back to the Bitcoin genesis header by hash-only signatures — sealed under proof-of-work that anyone can audit.

See [README.md](README.md) for verification tools, [SPONSOR.md](SPONSOR.md) for sponsorship terms, [OMEGA.md](OMEGA.md) for Phase Omega details, and [POWDER.md](POWDER.md) for powder lot pricing.
