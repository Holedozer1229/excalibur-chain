# EXCAL native Rosetta adapter

Native EXCAL Rosetta Data and Construction adapter. It reads the active
ChainState/UTXO view and preserves each native scriptPubKey as
`lock:<scriptPubKey hex>`. It does not translate the legacy GSF implementation.

## Implemented scope

- Data API: network list/options/status, canonical block and transaction
  retrieval, historical UTXO-backed balances, and live mempool listing and
  transaction details when a Mempool instance is supplied.
- Construction API: derive, preprocess, metadata, payloads, combine, parse,
  hash and submit.
- Lock paths: PKH, BRIDGE, legacy P2PK, OPEN/OP_TRUE, PQH, HTLC, QHTLC and
  KNOT. Activation gates, coinbase maturity, value/fee reconciliation and
  EXCAL consensus validation are applied before a signed transaction is
  returned.
- Trifold and KNOT use explicit EXCAL extension signature types
  `trifold` and `excal_knot`; they are not mislabeled as ECDSA or Ed25519.
- Local Trifold wallet bridge: `rosetta/trifold_signer.py` and
  `rosetta/knot_signer.py` provide native witness helpers. The Trifold helper
  requires an already-unlocked EXCAL Wallet and preserves its durable leaf
  counter and shared spent-leaf registry.
- Submit with a Mempool instance performs local mempool admission only and
  explicitly reports `relay_attempted: false`. If embedded with a live Node
  object that implements the documented `dispatch("sendrawtransaction", ...)`
  interface, submit delegates to that node and reports the peer-relay attempt
  separately. Peer delivery is never claimed.

See `LOCK_SUPPORT.md` for the lock matrix, wallet boundary, extension
limitations and release gates.

## Start (read-only standalone mode)

From the repository root, with a synchronized ChainState data directory:

```sh
python3 rosetta/excal_rosetta.py --data-dir ./chaindata --host 127.0.0.1 --port 8070 --network mainnet --chain-network fork
```

Standalone mode loads ChainState only. It does not attach a live Mempool or
Node, so mempool and submit endpoints return an explicit unavailable error.
When embedding, pass the actual objects owned by the running node:

```python
serve(chainstate, host="127.0.0.1", port=8070,
      network="mainnet", mempool=live_mempool, node=live_node)
```

The Mempool-only configuration supports local admission but not P2P relay.
Only supply `node` if its dispatch and peer-manager interfaces have been
verified against the running node implementation. Keep RPC private and place
any externally reachable Rosetta endpoint behind authenticated TLS.

## Important URUU distinction

The separate Uruu-Secure-Recovery app is currently a recovery dashboard/API
with mock verifier signatures and synthetic proof verification. It is not a
production Trifold signer or guardian quorum. The actual EXCAL Trifold
primitive is in `trifold_lockbox.py` / `txpq.py` and the unlocked EXCAL
wallet. The separate Frostgate FROST vault signs its own Taproot key, not
EXCAL lock spends. No mock URUU approval is accepted as transaction
authorization.

## Validation status

The focused GitHub Actions workflow is configured, but no successful test
execution has been confirmed. A prior run failed before exposing job steps;
treat the tests as unverified until a runner completes them. This is not
Coinbase certification. Before production, run the complete Python suite,
Rosetta CLI checks, all lock witness vectors, activation/timeout/replay tests,
two-node relay/reorg tests, and verify that the target Rosetta client accepts
EXCAL's custom Trifold/KNOT extension types. The Trifold source describes a
custom scheme without a formal security proof; this adapter does not claim
otherwise.
