# Camelot Fair — EXCAL integration hook

This is the chain-side integration seam for Camelot Fair: Rise of Excalibur. It is independent of the game engine, so Unity/Unreal (or another client) can be imported later without changing EXCAL consensus.

## Wired now

- Server-side Python client for the existing EXCAL node JSON-RPC.
- Read-only chain status using getblockcount and getbestblockhash.
- Read-only UTXO lookup for a public EXCAL PKH lock using getutxos.
- Integer-only sword accounting (1 EXCAL = 100,000,000 swords).
- Strict RPC method allowlist and loopback-only HTTP transport by default.

## Not enabled

- No game-client access to node RPC.
- No private keys, seed phrases, wallet unlock, or signing in the game.
- No automatic payments or reward payouts.
- No minting, consensus change, or special game privileges.
- No claim that UTXO lookup proves wallet ownership or payment finality.

The current node RPC returns mature as a coinbase-maturity flag, not a general confirmation count. Therefore this adapter does not mark a player payment as settled. A later payment verifier must locate the transaction in an accepted block, verify its output lock and exact sword amount, count confirmations, and handle reorganizations.

## Usage

Run this only in a trusted game backend beside an EXCAL node:

```python
from integrations.camelot_fair.excal_client import ExcalClient

excal = ExcalClient()  # defaults to http://127.0.0.1:9432
status = excal.chain_status()
utxos = excal.get_utxos("00" + "ab" * 20)  # example lock shape only
```

Do not expose the node RPC port to the public internet. Put a separately authenticated game API in front of this client. The game client talks to the game API, never directly to EXCAL RPC.

## Engine hook contract

The game backend should expose these app-level operations after authentication:

1. GET /api/excal/chain — chain height and best block hash.
2. POST /api/excal/wallet/challenge — issue a short-lived, one-use nonce.
3. POST /api/excal/wallet/verify — verify an address-control signature using the actual EXCAL wallet signature standard; reject until that verifier is implemented.
4. GET /api/excal/wallet/{playerId}/balance — read UTXOs for the linked public lock; disclose only to the authenticated player.
5. POST /api/excal/payment/intent — create a server-side quote with amount in integer swords, purpose, expiry, and unique reference.
6. POST /api/excal/payment/verify — future chain verifier; must check output, amount, confirmations, expiry, and reorg status before marking paid.
7. POST /api/excal/reward/propose — future server-authorized reward request; disabled until an audited payout policy and signing service exist.

Operations 3, 6, and 7 are not implemented by this read-only hook. Fail closed; do not simulate success.

## Amount rules

- Consensus/accounting values are integer swords.
- 100,000,000 swords = 1 EXCAL.
- Never use floating point for balances or payments.
- This is a denomination rule, not a BTC peg or redemption promise.
