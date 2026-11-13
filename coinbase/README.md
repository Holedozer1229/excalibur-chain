# Coinbase Rosetta Integration — AetherionEXCAL

## Overview

This directory contains the complete [Coinbase Rosetta](https://www.coinbase.com/cloud/developers/rosetta) integration for **AetherionEXCAL** — a post-quantum Bitcoin fork with 21M supply, 60-second blocks, and hash-only security.

**EXCAL is the new Qrevolution.**

## What's Here

| File | Purpose |
|---|---|
| `rosetta-config.json` | Main Rosetta API configuration |
| `rosetta-cli/config.json` | Rosetta CLI network configuration |
| `rosetta-cli/mainnet.json` | Mainnet network definition |
| `rosetta-cli/testnet.json` | Testnet network definition |
| `rosetta-cli/bootstrap_tx.json` | Genesis bootstrap transaction |
| `rosetta.md` | Detailed Rosetta API documentation |
| `listing-proposal.md` | Exchange listing proposal |
| `coinbase-listing-letter.md` | Formal letter to Coinbase listing team |

## Quick Start

### 1. Install Rosetta CLI

```bash
# Download from https://github.com/coinbase/rosetta-cli/releases
```

### 2. Validate Configuration

```bash
rosetta-cli check:data \
  --configuration-file coinbase/rosetta-cli/config.json \
  --network mainnet
```

### 3. Deploy Rosetta Server

```bash
rosetta-server --config coinbase/rosetta-config.json
```

## Network Summary

| Parameter | Value |
|---|---|
| Blockchain | `excal` |
| Network | `mainnet` / `testnet` |
| Currency | `EXCAL` (8 decimals) |
| Max Supply | 21,000,000 EXCAL |
| Block Time | 60 seconds |
| Consensus | SHA-256d Proof-of-Work |
| Signatures | SHA-256 hash-only (post-quantum) |
| Address Format | 20-char uppercase hex |

## Operation Types

- **`transfer`** — Standard EXCAL transfers
- **`coinbase`** — Block reward distribution
- **`nft_mint`** — NFT minting
- **`bridge`** — Cross-chain bridge transactions
- **`fee`** — Transaction fee deductions

## Security Features

- **AES-256-GCM** encryption for key storage and network messaging
- **SHA-256 hash-only** signatures — no elliptic curves
- **Post-quantum Trifold** block countersigning
- **scrypt KDF** (N=2^14) for passphrase derivation
- **126 passing tests** covering all core modules

## Exchange Listing

For exchange listing inquiries, see:

- [`listing-proposal.md`](listing-proposal.md) — Full listing proposal document
- [`coinbase-listing-letter.md`](coinbase-listing-letter.md) — Formal letter to Coinbase

## Documentation

- [AetherionEXCAL Website](https://www.aetherion-oracle.com)
- [Tokenomics](../TOKENOMICS.md)
- [Governance](../GOVERNANCE.md)
- [Security Audit](../AUDIT.md)
- [Rosetta API Docs](rosetta.md)

## Contact

- **Website:** https://www.aetherion-oracle.com
- **GitHub:** https://github.com/excalibur-chain/excalibur-chain
