# EXCAL Rosetta API Implementation

## Overview

This directory contains the complete [Coinbase Rosetta](https://www.coinbase.com/cloud/developers/rosetta) implementation for the **AetherionEXCAL** blockchain. Rosetta is an open-source framework that provides a standardized API for blockchain connectivity, enabling seamless integration with exchanges, wallets, and enterprise systems.

## File Structure

```
coinbase/
├── rosetta-config.json        # Main Rosetta API configuration
├── rosetta-cli/
│   ├── config.json            # Rosetta CLI configuration
│   ├── mainnet.json           # Mainnet network definition
│   ├── testnet.json           # Testnet network definition
│   └── bootstrap_tx.json      # Genesis bootstrap transaction
├── README.md                  # This file
├── rosetta.md                 # Detailed Rosetta API documentation
├── listing-proposal.md        # Exchange listing proposal document
└── coinbase-listing-letter.md # Formal letter to Coinbase listing team
```

## Network Parameters

| Parameter | Mainnet | Testnet |
|---|---|---|
| Blockchain | `excal` | `excal` |
| Network | `mainnet` | `testnet` |
| Currency | `EXCAL` | `TEXCAL` |
| Decimals | 8 | 8 |
| Genesis Block | 0 | 0 |
| Block Time | 60 seconds | 60 seconds |
| Max Supply | 21,000,000 | Unlimited |

## Operation Types

| Type | Description | Fungible |
|---|---|---|
| `transfer` | Standard EXCAL transfer between addresses | Yes |
| `coinbase` | Block reward distribution | Yes |
| `nft_mint` | NFT minting operation | No |
| `bridge` | Cross-chain bridge transaction | No |
| `fee` | Transaction fee deduction | Yes |

## Address Format

EXCAL uses **20-character uppercase hexadecimal** addresses derived from SHA-256 hash-only signatures. Example:

```
A1B2C3D4E5F6A7B8C9D0
```

## Running the Rosetta CLI

### Prerequisites

- [Rosetta CLI](https://github.com/coinbase/rosetta-cli) installed
- Rosetta API server running locally

### Data Check

```bash
# Validate mainnet configuration
rosetta-cli check:data --configuration-file coinbase/rosetta-cli/config.json --network mainnet

# Validate testnet configuration
rosetta-cli check:data --configuration-file coinbase/rosetta-cli/config.json --network testnet
```

### Construction Check

```bash
# Validate transaction construction
rosetta-cli check:construction --configuration-file coinbase/rosetta-cli/config.json --network mainnet
```

### Offline Construction Check

```bash
# Validate offline transaction building
rosetta-cli check:construction:offline --configuration-file coinbase/rosetta-cli/config.json --network mainnet
```

## API Endpoints

The Rosetta API exposes the following endpoints:

| Endpoint | Method | Description |
|---|---|---|
| `/network/list` | POST | List supported networks |
| `/network/status` | POST | Get network status and genesis block |
| `/block` | POST | Get block by identifier |
| `/block/transactions` | POST | Get transactions in a block |
| `/mempool` | POST | Get mempool contents |
| `/mempool/transaction` | POST | Get specific mempool transaction |
| `/account/balance` | POST | Get account balance |
| `/construction/derive` | POST | Derive account from public key |
| `/construction/preprocess` | POST | Preprocess transaction metadata |
| `/construction/metadata` | POST | Get transaction metadata |
| `/construction/payloads` | POST | Build transaction payloads |
| `/construction/combine` | POST | Combine signed payloads |
| `/construction/parse` | POST | Parse raw transaction |

## Security

- **AES-256-GCM** encryption for all key storage and network messaging
- **SHA-256 hash-only** signatures — no elliptic curves in the spend path
- **scrypt KDF** (N=2^14) for passphrase-derived key encryption
- **Post-quantum Trifold** signatures for block-level countersigning

## Integration Guide

### 1. Start the Rosetta Server

Deploy the Rosetta API server pointing to the EXCAL chain data:

```bash
# Example (implementation-specific)
rosetta-server --config coinbase/rosetta-config.json
```

### 2. Run Validation

```bash
rosetta-cli check:data --configuration-file coinbase/rosetta-cli/config.json --network mainnet
```

### 3. Integrate with Exchange

Use the Rosetta API endpoints to:
- Query balances and transaction history
- Build and sign transactions
- Monitor mempool and block confirmations

## Compliance

This implementation follows the [Coinbase Rosetta Specification v1.4.0](https://www.coinbase.com/cloud/developers/rosetta) and provides:

- ✅ Complete Data API (network, blocks, transactions, accounts, mempool)
- ✅ Complete Construction API (derive, preprocess, payloads, combine, parse)
- ✅ Standard error codes and messages
- ✅ Currency and operation type definitions
- ✅ Bootstrap transaction for genesis block

## References

- [Coinbase Rosetta Documentation](https://www.coinbase.com/cloud/developers/rosetta)
- [Rosetta GitHub Repository](https://github.com/coinbase/rosetta)
- [AetherionEXCAL Documentation](https://www.aetherion-oracle.com)
- [EXCAL Tokenomics](../TOKENOMICS.md)
- [EXCAL Governance](../GOVERNANCE.md)
- [EXCAL Security Audit](../AUDIT.md)
