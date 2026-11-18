# OpenSats General Fund Application

## Project: Post-Quantum Bitcoin Fork with Hash-Based Signatures

**Applicant:** [Your Name]
**Repository:** [GitHub link]
**Project type:** General Grant
**Requested amount:** $30,000 (for 6 months of development + security audit)

---

## Project Description

A working Bitcoin fork implementing hash-based post-quantum digital signatures (Lamport One-Time Signatures with ternary Merkle trees) as a migration path from quantum-vulnerable ECDSA to quantum-resistant cryptography.

## Problem

Bitcoin's security relies on ECDSA with secp256k1. A cryptographically relevant quantum computer running Shor's algorithm could derive private keys from public keys, compromising ~6.7 million BTC ($600B+). NIST standardized post-quantum cryptography in 2024, but Bitcoin has no post-quantum migration path yet.

## Solution

A complete post-quantum signature stack integrated into a running Bitcoin fork:

- **Trifold Lockbox**: Hash-based signatures (Lamport OTS + ternary Merkle trees, height 6, 729 signatures/key)
- **Transaction Layer**: Bitcoin witness encoding for post-quantum signatures
- **Wallet**: Post-quantum hash addresses with BIP39 derivation
- **Spent-Leaf Registry**: Key reuse prevention
- **Light Ledger**: Post-quantum checkpoint attestation

Security relies **only** on SHA-256 collision resistance — no new mathematical assumptions.

## What's Done

- ✓ Full hash-based signature implementation (`trifold_lockbox.py`)
- ✓ Bitcoin witness encoding/decoding (`txpq.py`)
- ✓ Wallet with PQH address support (`excalibur_wallet/`)
- ✓ Spent-leaf registry (`spent_leaf_registry.py`)
- ✓ Integration with Bitcoin fork node (`fork_node.py`)
- ✓ Working demo (`demo_post_quantum_fork.py`)

## What Funding Enables

| Milestone | Deliverable | Timeline |
|-----------|-------------|----------|
| 1 | Testnet deployment with PQH addresses | Months 1-3 |
| 2 | Wallet migration tooling (ECDSA → PQH) | Months 3-5 |
| 3 | Performance benchmarking (sign/verify speed, sig size) | Months 4-5 |
| 4 | Independent security audit | Months 5-6 |

## Why OpenSats

- This is foundational Bitcoin security research that is not readily funded elsewhere
- The code is free and open-source (MIT license)
- Direct impact on Bitcoin's long-term security against quantum threats
- Galaxy Digital's $5M Quantum Readiness Initiative validates the need, but capacity is limited

## Technical Details

**Signature scheme:** Hash-based (XMSS-style with ternary Merkle tree)
**One-Time Signature:** Lamport OTS with 256-byte messages
**Tree:** Ternary (arity-3) Merkle tree, height 6
**Capacity:** 729 signatures per key (3^6)
**Signature size:** ~25 KB (comparable to SLH-DSA/SHAKE-256s: 22 KB)
**Security:** SHA-256 collision resistance only

**Comparison:**

| Scheme | Type | Sig Size | Quantum Safe |
|--------|------|----------|--------------|
| ECDSA | Elliptic curve | 64 B | ✗ |
| ML-DSA-65 | Lattice | 2.4 KB | ✓ |
| SLH-DSA | Hash-based | 22 KB | ✓ |
| Trifold | Hash-based | ~25 KB | ✓ |

## Demo

```bash
python demo_post_quantum_fork.py
```

Shows: key generation, transaction signing, witness encoding, verification (valid + invalid cases), round-trip encoding.

## Open Source

All code is MIT licensed and available on GitHub. The project welcomes contributions and code review from the Bitcoin community.
