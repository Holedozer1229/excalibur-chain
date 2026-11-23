# Coinbase Rosetta Integration — AetherionEXCAL

## Overview

This directory contains the complete [Coinbase Rosetta](https://www.coinbase.com/cloud/developers/rosetta) integration for **AetherionEXCAL** — a post-quantum Bitcoin fork with 21M supply, 60-second blocks, and hash-only security.

**EXCAL is the new Qrevolution.**

## What's Here

| File | Purpose |
|---|---|
| `rosetta-config.json` | Main Rosetta API configuration |
| `rosetta-cli/mainnet.json` | Rosetta CLI (mesh-cli v0.10.4) syncer configuration for mainnet |
| `rosetta-cli/testnet.json` | Rosetta CLI (mesh-cli v0.10.4) syncer configuration for testnet |
| `rosetta-cli/mainnet-asserter.json` | Asserter configuration generated from the live mainnet server |
| `rosetta-cli/testnet-asserter.json` | Asserter configuration for testnet (same shape, testnet genesis) |
| `rosetta-cli/bootstrap_tx.json` | Genesis bootstrap transaction |
| `rosetta.md` | Detailed Rosetta API documentation |
| `listing-proposal.md` | Exchange listing proposal |
| `coinbase-listing-letter.md` | Formal letter to Coinbase listing team |

## Quick Start

### 1. Install Rosetta CLI

```bash
# mesh-cli v0.10.4 (the rosetta-cli repo was renamed to mesh-cli)
curl -sL -o rosetta-cli.tar.gz \
  https://github.com/coinbase/mesh-cli/releases/download/v0.10.4/rosetta-cli-0.10.4-linux-amd64.tar.gz
tar xzf rosetta-cli.tar.gz
./rosetta-cli-0.10.4-linux-amd64 version  # v0.10.4
```

### 2. Start the Rosetta server (serves the live fork chain as `mainnet`)

```bash
python3 rosetta/excal_rosetta.py --data-dir ./chaindata_fork \
  --host 127.0.0.1 --port 8070 --network mainnet --chain-network fork
```

### 3. Validate with the official CLI (bounded range; full sync is slow)

```bash
rosetta-cli check:data \
  --configuration-file coinbase/rosetta-cli/mainnet.json \
  --asserter-configuration-file coinbase/rosetta-cli/mainnet-asserter.json \
  --data-dir /tmp/rosetta-check \
  --start-block 49900
# End condition (49999) lives in the scratch copy used for the run, not
# in the repo config, so the check follows the live tip by default.
```

Notes:

- The syncer configs set `max_sync_concurrency: 1` and `http_timeout: 30`:
  this server is single-process Python, so concurrent block fetches
  serialize on the GIL and cold renders replay the chain (~5–15s at the
  50k tip). First call per height pays the replay; sequential renders
  reuse the cached UTXO views.
- `rosetta-cli/config.json` targets a pre-rename CLI format and is
  superseded by `mainnet.json` / `testnet.json`; it is left in place for
  reference only.
- The asserter files were generated from the live server with
  `rosetta-cli utils:asserter-configuration`. Regenerate them after any
  `/network/options` change.

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
