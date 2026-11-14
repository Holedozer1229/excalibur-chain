# AetherionEXCAL: Post-Quantum Bitcoin Fork

**A working Bitcoin fork with hash-based post-quantum signatures for Q-Day migration.**

## Overview

AetherionEXCAL is a Bitcoin fork that implements **hash-based digital signatures** (Lamport One-Time Signatures with ternary Merkle trees) as a migration path from quantum-vulnerable ECDSA to quantum-resistant cryptography.

### The Problem

Bitcoin's security relies on ECDSA with secp256k1 elliptic curve cryptography. A cryptographically relevant quantum computer (CRQC) running Shor's algorithm could derive private keys from public keys, compromising all exposed UTXOs. Currently, **6.7 million BTC ($600B+)** are vulnerable.

### Our Solution

A complete post-quantum signature implementation integrated into a running Bitcoin fork:

- **Trifold Lockbox**: Hash-based one-time signatures (Lamport OTS) authenticated by ternary Merkle trees
- **Transaction Layer**: Bitcoin witness encoding/decoding for post-quantum signatures (`txpq.py`)
- **Wallet Integration**: Post-quantum hash addresses (PQH) with migration from ECDSA
- **Spent-Leaf Registry**: Key reuse prevention with persistent state tracking
- **Light Ledger**: Checkpoint attestation with post-quantum signatures

## Technical Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Bitcoin Transaction                       │
│                                                             │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐  │
│  │ ECDSA Input  │    │ PQH Input    │    │ Witness      │  │
│  │ (legacy)     │    │ (post-quantum│    │ Stack        │  │
│  │              │    │  migration)  │    │              │  │
│  └──────────────┘    └──────────────┘    └──────────────┘  │
│                                                             │
│  ┌──────────────────────────────────────────────────────┐   │
│  │  Trifold Signature Scheme                            │   │
│  │                                                      │   │
│  │  Lamport OTS (256 bytes) → SHA-256 → Ternary Merkle  │   │
│  │  Tree (height 6, 729 signatures per key)             │   │
│  │                                                      │   │
│  │  Security: Based on SHA-256 collision resistance     │   │
│  │  (No number-theoretic assumptions)                   │   │
│  └──────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Key Components

| Module | Description |
|--------|-------------|
| `trifold_lockbox.py` | Hash-based signature scheme (Lamport OTS + ternary Merkle tree) |
| `txpq.py` | Q-Day witness codec for Bitcoin script compatibility |
| `excalibur_wallet/` | Wallet with PQH address support and migration |
| `lightledger.py` | Light client with post-quantum checkpoint attestation |
| `spent_leaf_registry.py` | Key reuse prevention across wallet restores |
| `fork_node.py` | Bitcoin fork node with post-quantum transaction support |

## Signature Scheme Details

- **Type**: Hash-based (XMSS-style with ternary Merkle tree)
- **One-Time Signature**: Lamport OTS with 256-byte messages
- **Tree Structure**: Ternary (arity-3) Merkle tree, height 6
- **Signature Capacity**: 729 signatures per key (3^6)
- **Signature Size**: ~25 KB (comparable to SLH-DSA/SHAKE-256s: 22 KB)
- **Security**: Based on SHA-256 collision resistance only
- **Quantum Resistance**: Immune to Shor's algorithm (no curve arithmetic)

## Comparison with NIST Standards

| Scheme | Type | Sig Size | Quantum Safe | NIST Status |
|--------|------|----------|--------------|-------------|
| ECDSA (secp256k1) | Elliptic curve | 64 bytes | ✗ NO | Legacy |
| ML-DSA-65 | Lattice | 2.4 KB | ✓ YES | FIPS 204 |
| SLH-DSA/SHAKE-256s | Hash-based | 22 KB | ✓ YES | FIPS 205 |
| **Trifold** | **Hash-based** | **~25 KB** | **✓ YES** | **Research** |

## Why Hash-Based?

Hash-based signatures are the **most conservative** post-quantum choice:

1. **Minimal assumptions**: Security relies only on hash function collision resistance
2. **Proven track record**: Merkle signatures proposed in 1979, 47 years of cryptanalysis
3. **Bitcoin-native**: SHA-256 is already trusted, optimized, and hardware-accelerated
4. **No new primitives**: Unlike lattice-based schemes, no new mathematical assumptions
5. **NIST-endorsed**: SLH-DSA (FIPS 205) is the NIST standard for hash-based signatures

## Migration Roadmap

### Phase 1: Research ✓
- [x] Hash-based signature implementation
- [x] Bitcoin witness encoding/decoding
- [x] Spent-leaf registry for key reuse prevention
- [x] Integration with Bitcoin fork node

### Phase 2: Testing (Seeking Funding)
- [ ] Testnet deployment with post-quantum addresses
- [ ] Wallet migration tooling (ECDSA → PQH)
- [ ] Performance benchmarking
- [ ] Independent security audit

### Phase 3: Mainnet Preparation
- [ ] BIP proposal for P2QRH (Pay to Quantum Resistant Hash)
- [ ] Soft fork consensus rules
- [ ] Dormant coin protection strategy
- [ ] Community consensus building

### Phase 4: Q-Day Activation
- [ ] Post-quantum address types on mainnet
- [ ] Migration window for exposed UTXOs
- [ ] Hybrid signature support during transition

## Running the Demo

```bash
# Run the post-quantum signature demo
python demo_post_quantum_fork.py
```

Expected output:
- Key generation with ternary Merkle tree
- Transaction signing with Lamport OTS
- Signature verification (valid + invalid cases)
- Bitcoin witness encoding/decoding
- Round-trip verification

## Grant Alignment

This project directly aligns with the **Galaxy Bitcoin Quantum Readiness Initiative** priority areas:

1. ✓ **Post-quantum signature scheme integration**: Trifold hash-based signatures
2. ✓ **Quantum-resistant transaction proposals**: P2QRH address type with witness encoding
3. ✓ **Wallet migration tooling**: PQH address generation and ECDSA migration
4. ⏳ **Formal security audit**: Seeking funding for independent audit

## Funding Request

We are seeking milestone-based grant funding for:

| Milestone | Deliverable | Timeline |
|-----------|-------------|----------|
| 1 | Testnet deployment with PQH addresses | 3 months |
| 2 | Wallet migration tooling (ECDSA → PQH) | 3 months |
| 3 | Performance benchmarking report | 2 months |
| 4 | Independent security audit | 3 months |
| 5 | BIP proposal for P2QRH | 2 months |

## Contact

For grant inquiries, please contact: **quantum@galaxy.com**

## License

MIT License. This is research code — not formally specified or peer-reviewed.

## Acknowledgments

- Ralph Merkle (1979): Merkle tree signatures
- Lamport (1979): One-time signatures
- NIST FIPS 205: SLH-DSA standard
- Galaxy Digital: Bitcoin Quantum Readiness Initiative
- Bitcoin Security Consortium: $15M post-quantum research funding
