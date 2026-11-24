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

The focused GitHub Actions workflow is configured, but CI has never
completed a run: every invocation fails in 4–8s before any job step
executes (GitHub billing-lock pattern, same as the other repos). VM runs
are the only real signal and they are green: the full Python suite
(52 tests, 1 graceful skip for the missing prometheus-client) passes,
including the Rosetta Data + Construction tests and the ChainState
submit-block regression tests.

Official `rosetta-cli` (mesh-cli v0.10.4) conformance was run against the
live 50k-block fork chain: `check:data` over blocks 49900–49999 with
reconciliation enabled (configs in `coinbase/rosetta-cli/`) **passed**:
100 blocks / 100 transactions / 100 operations, 100 active
reconciliations, 0 failed, 100% coverage — Request/Response, Response
Assertion, Block Syncing, Balance Tracking and Reconciliation all PASSED.
A full 0–49999 sync has not been run yet. The per-height replay blocker
is removed: ChainState now keeps a persistent per-height UTXO delta
index (`utxo_index.py`, `ChainState.utxo_at()`; deltas + manifest under
`<data-dir>/utxo_index/`), so a cold block/balance lookup at any height
no longer replays the chain from genesis — measured on the live chain
2026-11-23: cold `/network/status` 17.5s → 0.07s, cold
`/block` at height 25000 0.13s, cold historical balance lookups
0.04–0.19s across heights 100–49899 (was 0.5–8.0s), all verified equal
to the full-replay path and to the known miner balance 2,495,147.9919
EXCAL at tip. This is not Coinbase certification. Before production,
run the complete Python suite, a full Rosetta CLI sync, all lock witness
vectors, activation/timeout/replay tests, two-node relay/reorg tests,
and verify that the target Rosetta client accepts EXCAL's custom
Trifold/KNOT extension types. The Trifold source describes a custom scheme
without a formal security proof; this adapter does not claim otherwise.
