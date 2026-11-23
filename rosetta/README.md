# EXCAL native Rosetta adapter

Native EXCAL Rosetta Data and Construction adapter. It reads the actual
ChainState/UTXO view and preserves every native scriptPubKey as
lock:<scriptPubKey hex>. It does not translate the legacy GSF implementation.

## Implemented scope

- Data API: network list/options/status, block, block transaction, tip balance,
  live mempool list and transaction operations.
- Construction API: derive, preprocess, metadata, payloads, combine, parse,
  hash and submit.
- Lock handling: PKH, BRIDGE, legacy P2PK, OPEN/OP_TRUE, PQH, HTLC, QHTLC and
  KNOT. Activation gates and exact consensus validation are enforced.
- Trifold payloads use the explicit EXCAL extension signature type trifold;
  KNOT uses excal_knot. They are not mislabeled as ECDSA or Ed25519.
- Local Trifold wallet bridge: rosetta/trifold_signer.py accepts an already
  unlocked EXCAL Wallet object and returns the native PQH/QHTLC witness while
  preserving the durable leaf counter and spent-leaf registry.
- Broadcast is enabled only when embedded with the live Node object. Submit
  delegates to Node.dispatch("sendrawtransaction"), which validates through
  the real mempool and broadcasts through the node peer manager.

See LOCK_SUPPORT.md for the complete lock matrix, wallet boundary, extension
limitations and release gates.

## Start (read-only / no broadcast)

From the repository root, with a synchronized node data directory:

    python3 rosetta/excal_rosetta.py --data-dir ./chaindata --host 127.0.0.1 --port 8070 --network fork

Standalone mode cannot broadcast because it does not own the live Node.
Production embedding must call serve(node.cs, ..., mempool=node.mempool,
node=node) inside the node process. Keep RPC private and place any externally
reachable Rosetta endpoint behind authenticated TLS.

## Important URUU distinction

The separate Uruu-Secure-Recovery app is currently a recovery dashboard/API
with mock verifier signatures and synthetic proof verification. It is not a
production Trifold signer or guardian quorum. The actual EXCAL Trifold
primitive is in trifold_lockbox.py / txpq.py and the unlocked EXCAL wallet.
The separate Frostgate FROST vault signs its own Taproot key, not EXCAL lock
spends. No mock URUU approval is accepted as transaction authorization.

## Validation status

Code and tests are committed on the feature branch, but tests have not yet
been executed here. This is not Coinbase certification. Before production,
run the full Python suite, Rosetta CLI checks, all lock witness vectors,
activation/timeout/replay tests, two-node relay/reorg tests, and verify that
the target Rosetta client accepts EXCAL's custom Trifold/KNOT extension types.
The Trifold source itself documents that it is a custom scheme without a
formal security proof; this adapter does not claim otherwise.
