---
layout: default
title: Holo-wallet
---

# Holo-wallet — P2P Wallet for SphinxOS Nexus

`holo_wallet.py` is a full CLI wallet integrated with the Holographic P2P layer. It supports key generation, hash-only transaction signing, balance tracking, encrypted messaging, gossip broadcast, and network topology export.

## Installation

```bash
# Install dependencies
pip install -r requirements.txt

# Or use the compiled Windows executable
dist\Holo-wallet.exe
```

## Commands

### Generate Key Pair

Generate a new key pair and address:

```bash
python holo_wallet.py generate
python holo_wallet.py generate --label "My Wallet"
```

**Output:**
```
Private key:  a1b2c3d4...
Public key:   5e6f7a8b...
Address:      ABC123DEF456...
```

### Check Balance

Show wallet balance:

```bash
python holo_wallet.py balance
```

**Output:**
```
Address:    ABC123DEF456...
Balance:    100.5000 SKYNT
```

### Send Transaction

Send SKYNT to another address:

```bash
python holo_wallet.py send --to ABC123DEF456 --amount 10.5
python holo_wallet.py send --to ABC123DEF456 --amount 10.5 --type transfer --description "Payment"
```

**Options:**
- `--to` — Recipient address (required)
- `--amount` — Amount in SKYNT (required)
- `--type` — Transaction type: transfer, nft_mint, bridge (default: transfer)
- `--description` — Transaction description

### List Peers

List connected P2P peers:

```bash
python holo_wallet.py peers
```

**Output:**
```
Peer        Address         Port   Status    Entanglement
peer_0      192.168.1.1     8080   Active    0.8500
peer_1      192.168.1.2     8081   Active    0.7200
```

### Export Network Topology

Export the network topology for visualization:

```bash
python holo_wallet.py topology --format json
python holo_wallet.py topology --format graphml --output network.graphml
```

**Formats:**
- `json` — JSON format for programmatic access
- `graphml` — GraphML format for graph visualization tools

### Encrypt Message

Send an encrypted message to a peer:

```bash
python holo_wallet.py encrypt --to peer_0 --message "secret message"
```

**Options:**
- `--to` — Recipient peer name (required)
- `--message` — Message text (required)

### Gossip Broadcast

Broadcast a message via the gossip protocol:

```bash
python holo_wallet.py gossip --message "hello network"
```

**Options:**
- `--message` — Message text (required)

The gossip protocol uses epidemic propagation with O(log N) dissemination time.

### Show Status

Show full wallet and network status:

```bash
python holo_wallet.py status
```

**Output:**
```
Wallet:
  Address:    ABC123DEF456...
  Balance:    100.5000 SKYNT
  Keys:       1
  Transactions: 5

Network:
  Active Peers: 6
  Coherence:    1.0000
  Encryption:   Enabled
```

## Security

### Hash-Only Signatures

The wallet uses SHA-256 hash-only signatures (post-quantum style):

```
signature = SHA-256(private_key || tx_hash)
```

This approach is consistent with the project's Trifold hash-only philosophy.

### Encryption

Messages are encrypted using XOR-based symmetric cipher with base64 encoding. For production deployment, this would be replaced with AES encryption.

### Key Storage

Private keys are stored in `~/.holo_wallet/wallet.json`. For production use, consider encrypting the wallet file at rest.

## Integration with SphinxOS

The wallet integrates with the Holographic P2P layer for:

- **Entanglement-based routing** — Messages follow maximum-entanglement paths
- **Gossip protocol** — Epidemic message propagation
- **Priority queues** — 4-level priority (CRITICAL/HIGH/NORMAL/LOW)
- **TTL-based expiry** — Messages expire after time-to-live

## Building the Executable

To build the Windows executable:

```bash
pyinstaller --onefile --name Holo-wallet --add-data "sphinx_os;sphinx_os" holo_wallet.py
```

The executable will be created in `dist/Holo-wallet.exe`.

## Data Storage

All wallet data is stored in `~/.holo_wallet/`:

- `wallet.json` — Keys, addresses, and transactions
- `peers.json` — Peer connection data
- `messages.json` — Received messages
