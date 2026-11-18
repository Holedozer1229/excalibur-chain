# AetherionEXCAL — Exchange Listing Proposal

## Executive Summary

**AetherionEXCAL** (ticker: **EXCAL**) is a live Bitcoin fork anchored at Bitcoin block 968,698, featuring post-quantum security, responsive difficulty adjustment, and a complete Coinbase Rosetta API implementation. This document outlines the technical, economic, and security foundations that make EXCAL ready for exchange listing.

**Website:** https://www.aetherion-oracle.com

---

## 1. Project Overview

### What is EXCAL?

EXCAL is a production-ready blockchain that combines Bitcoin's proven proof-of-work security with post-quantum cryptographic protections. It is not a simulation or concept — it is a **living chain** with ~25,600+ blocks, active mining, and a full wallet ecosystem.

### Key Differentiators

| Feature | EXCAL | Bitcoin |
|---|---|---|
| Max supply | 21,000,000 | 21,000,000 |
| Block time | 60 seconds | 600 seconds |
| Post-quantum signatures | Yes (Trifold, hash-only) | No |
| Responsive DAA | 60-block window | 2,016 blocks |
| Deep-reorg guard | 100 blocks | None |
| Cross-chain bridge | Yes (from height 39,200) | No |
| Rosetta API | Full implementation | N/A |

### The Qrevolution

EXCAL introduces **post-quantum security from day one**:
- **Q-Day (height 25,212):** PQH locks activate — `0x02 ‖ hash160(Trifold root)` — spent by hash-only Trifold witnesses
- **Phase Omega (height 25,901):** Every block carries a Trifold signature over its parent's header
- **No elliptic curves** in the spend path — SHA-256 only

---

## 2. Tokenomics

### Supply Schedule

| Parameter | Value |
|---|---|
| **Ticker** | EXCAL |
| **Max supply** | 21,000,000 EXCAL |
| **Smallest unit** | Sword (1 EXCAL = 100,000,000 swords) |
| **Initial block subsidy** | 50 EXCAL |
| **Halving interval** | 210,000 blocks (~3.27 years) |
| **Target block spacing** | 60 seconds |
| **Blocks per day** | ~1,440 |

### Halving Schedule

| Era | Block Range | Subsidy | Total Minted |
|---|---|---|---|
| 1 | 0 – 209,999 | 50 EXCAL | 10,500,000 |
| 2 | 210,000 – 419,999 | 25 EXCAL | 5,250,000 |
| 3 | 420,000 – 629,999 | 12.5 EXCAL | 2,625,000 |
| 4 | 630,000 – 839,999 | 6.25 EXCAL | 1,312,500 |
| 5+ | 840,000+ | 3.125+ EXCAL | 3,125,000 |

### Revenue Model

- **No transaction fees** — coinbase value equals block subsidy alone
- **No protocol fee, no treasury cut, no developer tax**
- **Sponsorship economy** — BTC-denominated block sponsorship creates permanent on-chain positions
- **Powder lots** — Crowdfunded Bitcoin-mainnet broadcasts

---

## 3. Technical Architecture

### Consensus

- **SHA-256d Proof-of-Work** — Compatible with standard mining hardware
- **Responsive DAA** — 60-block window, 60-second target, 4× clamp
- **Boundary DAA** — Retargets only at window boundaries (from height 29,700)
- **Deep-reorg guard** — Rejects reorganizations deeper than 100 blocks

### SphinxOS Nexus

The `sphinx_os/` package implements a unified blockchain organism with 7 integrated subsystems:
- **Quantum-Spacetime Fabric** — Quantum state simulation with entanglement entropy
- **Conscious Consensus Engine** — IIT v8 φ-score driven block consensus
- **Holographic P2P Layer** — Entanglement-based routing with AES-256-GCM encryption
- **Self-Organizing Treasury** — Autonomous treasury with NFT-based governance
- **Custom Bonding Curve** — Sigmoid (S-curve) pricing for URUU token
- **zkSync Era Bridge** — Cross-chain lock-and-mint with cryptographic proofs
- **Knights of the Round Table** — Sovereign governance with MuSig2 (BIP-327)

### Governance — Knights of the Round Table

EXCAL governance is controlled by a sovereign council elected by 3-of-5 threshold voting:
- **MuSig2 (BIP-327)** — Production-ready threshold signing with additive inverse handling
- **FROST DKG** — Distributed key generation with Feldman VSS
- **AI Oracle Knights** — 5 specialization types (Sentinel, Treasurer, Oracle, Bridge, Curve)
- **Knight NFTs** — 13 NFTs (12 Mythical + 1 Legendary King) with ZK rarity proofs
- **Taproot Treasury** — Derived from the 13-word prophecy code

### zkSync Era Integration

- **URUU Token** — 1,000,000 max supply with custom sigmoid bonding curve
- **Bridge** — Lock-and-mint mechanism with SHA-256 cryptographic proofs
- **Bridge fee** — 0.1%
- **Tokens** — EXCAL, URUU, wEXCAL

### Wallet Ecosystem

- **AetherionEXCAL GUI Wallet** — Premium desktop wallet with AES-256-GCM encryption, multi-wallet profiles, and P2P networking (33.7 MB production build)
- **Holo-wallet** — CLI wallet for scripting and automation
- **Compiled executables** — Windows (.exe) and Mac builds available

---

## 4. Security

### Cryptographic Security

| Component | Implementation |
|---|---|
| Key storage | AES-256-GCM with scrypt KDF (N=2^14) |
| Network messaging | AES-256-GCM authenticated encryption |
| Transaction signatures | SHA-256 hash-only (no elliptic curves) |
| Block countersigning | Post-quantum Trifold (ternary Merkle tree) |
| Address validation | 20-char uppercase hex format enforced |

### Audit Status

- **361 passing unit tests** covering all core modules (MuSig2, FROST, AI Oracle Knights, Knight NFTs, Knights of the Round Table, bonding curve, zkSync bridge, SphinxOS Nexus)
- **Full security audit** — See [AUDIT.md](../AUDIT.md)
- **All critical issues resolved** — AES-256-GCM replaces XOR simulation
- **No plaintext key storage** — All keys encrypted at rest

### Verification Tools

- `genealogy_verify.py` — Full chain verification from Bitcoin anchor
- `omega_verify.py` — Phase Omega countersignature verification
- `window_planner.py` — DAA window analysis

---

## 5. Rosetta API Compliance

AetherionEXCAL provides a **complete Coinbase Rosetta implementation**:

### Data API

- ✅ `/network/list` — Supported networks
- ✅ `/network/status` — Network status and genesis
- ✅ `/block` — Block retrieval by identifier
- ✅ `/block/transactions` — Transaction listing
- ✅ `/mempool` — Mempool contents
- ✅ `/mempool/transaction` — Specific mempool transaction
- ✅ `/account/balance` — Account balance queries

### Construction API

- ✅ `/construction/derive` — Account derivation from public key
- ✅ `/construction/preprocess` — Transaction preprocessing
- ✅ `/construction/metadata` — Transaction metadata
- ✅ `/construction/payloads` — Payload generation
- ✅ `/construction/combine` — Signed payload combination
- ✅ `/construction/parse` — Raw transaction parsing

### Configuration Files

All Rosetta configuration files are provided in the `coinbase/` directory:
- `rosetta-config.json` — Main API configuration
- `rosetta-cli/mainnet.json` — Mainnet network definition
- `rosetta-cli/testnet.json` — Testnet network definition
- `rosetta-cli/bootstrap_tx.json` — Genesis bootstrap transaction

### Validation

```bash
rosetta-cli check:data --configuration-file coinbase/rosetta-cli/config.json --network mainnet
rosetta-cli check:construction --configuration-file coinbase/rosetta-cli/config.json --network mainnet
```

---

## 6. Network Infrastructure

### Mining

- **CPU mining** — `cpu_miner_mp.py` (~150+ MH/s on 4 cores)
- **GPU mining** — Standard SHA-256d stratum miners via `stratum_fork.py`
- **Merge mining** — AuxPoW accepted from height 23,785

### Network Parameters

| Parameter | Value |
|---|---|
| Magic bytes | `0x47534603` |
| RPC port | 9432 |
| P2P port | 9433 |
| Min difficulty bits | `0x1f000100` |
| Max reorg depth | 100 blocks |

### Monitoring

- **Prometheus metrics** — Real-time observability at `http://127.0.0.1:9435/metrics`
- **Peer metrics** — Connected peers, network coherence
- **Transaction metrics** — Throughput, latency, amounts
- **Error metrics** — Component-level error tracking

---

## 7. Governance

EXCAL operates under a **proof-of-work governance model**:

- **No central authority** — The chain follows the longest valid work
- **Staged protocol upgrades** — Activate at predetermined block heights
- **Transparent on-chain signaling** — All changes verifiable via `genealogy_verify.py`
- **Community principles** — Transparency, verifiability, decentralization, post-quantum readiness

See [GOVERNANCE.md](../GOVERNANCE.md) for full details.

---

## 8. Honest Scope

EXCAL has no market and no price. No return is promised or implied. What is on offer is:

- **Permanence with a pedigree** — A position in a chain anchored to Bitcoin
- **Post-quantum security** — Hash-only signatures from genesis
- **Full auditability** — Every claim backed by on-chain evidence
- **Rosetta compliance** — Standardized API for exchange integration

---

## 9. Documentation

| Document | Link |
|---|---|
| Tokenomics | [TOKENOMICS.md](../TOKENOMICS.md) |
| Governance | [GOVERNANCE.md](../GOVERNANCE.md) |
| Security Audit | [AUDIT.md](../AUDIT.md) |
| Rosetta API | [rosetta.md](rosetta.md) |
| Phase Omega | [OMEGA.md](../OMEGA.md) |
| Sponsorship | [SPONSOR.md](../SPONSOR.md) |

---

## 10. Contact

- **Website:** https://www.aetherion-oracle.com
- **GitHub:** https://github.com/excalibur-chain/excalibur-chain
- **Rosetta Files:** `coinbase/` directory

---

*This proposal is provided for informational purposes. EXCAL is a live blockchain with verifiable on-chain data. All claims can be independently verified using the tools and documentation referenced above.*
