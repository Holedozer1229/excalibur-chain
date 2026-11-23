# EXCAL native Rosetta adapter

This package is the new Rosetta adapter for **Aetherion-Excalibur (EXCAL)**.
It reads the repository's actual `ChainState` and UTXO set; it does not
translate the older Genesis Fork / GSF Rosetta implementation.

## Important scope boundary

The Data API is implemented for the native EXCAL chain. Account identifiers
are lossless: `lock:<scriptPubKey hex>`. This preserves the exact native lock
for PKH, PQH, HTLC, QHTLC, BRIDGE and future script types.

The Construction API is deliberately fail-closed (HTTP 501) in this first
version. The previous Rosetta implementation assumes ECDSA/secp256k1 and a
single P2PK-style address model. Reusing it for EXCAL's hash-based Trifold
locks would misrepresent signing support and could create unsafe transactions.
Native construction support must be implemented against EXCAL's transaction
serializer, lock interpreter and signing vectors before being enabled.

## Start

From the repository root, with a synchronized EXCAL node data directory:

```sh
python3 rosetta/excal_rosetta.py --data-dir ./chaindata --host 127.0.0.1 --port 8070 --network fork
```

Keep the service private behind an authenticated/TLS reverse proxy if exposed.
Do not expose the node RPC or wallet secrets. For production, prefer embedding
`serve(cs, ...)` in the node process so Rosetta reads the same live ChainState
object and cannot drift from the node.

## Endpoints

- `POST /network/list`
- `POST /network/options`
- `POST /network/status`
- `POST /block`
- `POST /block/transaction`
- `POST /account/balance` (tip only)
- `POST /mempool` (currently reports empty; mempool adapter not yet wired)
- `POST /construction/*` (explicitly disabled pending native lock-aware construction)

## Account identifier

For a locking script `0014...`, query:

```json
{
  "network_identifier": {"blockchain": "EXCAL", "network": "fork"},
  "account_identifier": {"address": "lock:0014..."}
}
```

Amounts are integer swords, with 8 decimal places per EXCAL.

## Validation status

This is an initial implementation, not a Coinbase-certified Rosetta service.
Before calling it complete, run Rosetta CLI data checks against a real node,
verify operation reconciliation over representative blocks containing every
active lock type, test reorg behavior, and implement/test native construction.
