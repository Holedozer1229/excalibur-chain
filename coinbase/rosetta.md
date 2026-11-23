# EXCAL Rosetta API

## Implementation

The active adapter is in rosetta/excal_rosetta.py with construction logic in
rosetta/construction.py. It is backed by the live EXCAL ChainState and UTXO
set. The network identifier is blockchain "excal", network "mainnet" (or
"testnet" for the test network). Currency is EXCAL / 8 decimals on mainnet
and tEXCAL / 8 decimals on testnet.

This is an implementation under validation, not a statement of Coinbase
approval or Rosetta certification.

## Account identifiers

EXCAL account identifiers preserve the exact native locking script:

    lock:<scriptPubKey hex>

They are not 20-character uppercase addresses. The exact script is retained
so PKH, PQH, HTLC, QHTLC, BRIDGE, OPEN, P2PK and KNOT locks are not collapsed
into an unrelated ECDSA address format.

## Data API

- POST /network/list
- POST /network/options
- POST /network/status
- POST /block
- POST /block/transaction
- POST /account/balance (tip only; historical lookup is explicitly unsupported)
- POST /mempool
- POST /mempool/transaction

Block and mempool operations use lowercase operation types (coinbase and
transfer) and exact EXCAL script identifiers. Mempool data is only available
when the adapter is embedded with the live node.

## Construction API

- POST /construction/derive
- POST /construction/preprocess
- POST /construction/metadata
- POST /construction/payloads
- POST /construction/combine
- POST /construction/parse
- POST /construction/hash
- POST /construction/submit

Supported lock families: PKH, BRIDGE, legacy P2PK, OPEN/OP_TRUE, PQH,
HTLC, QHTLC and KNOT. Consensus activation gates are enforced. KNOT remains
staged until its configured activation height; retired legacy locks are
refused after their retirement height.

PQH and QHTLC use the native Trifold witness codec and one-time spent-leaf
registry. The local signer bridges are rosetta/trifold_signer.py (PQH/QHTLC) and rosetta/knot_signer.py (KNOT). The Trifold bridge requires an
already-unlocked EXCAL Wallet object. HTLC claim/refund paths require their
native descriptor, correct key and (for claims) secret. KNOT requires its
time/preimage witness and descriptor.

## Signature extensions

Rosetta does not define a standard signature type for this chain's Trifold
one-time hash-based witness or KNOT preimage. The adapter advertises the
chain-specific signature types "trifold" and "excal_knot". They are not
misrepresented as ECDSA or Ed25519. The exact Rosetta CLI and Coinbase
integration client must be tested to verify acceptance of these extensions
before claiming full conformance.

The separate Uruu-Secure-Recovery app currently uses mock verifier signatures
and synthetic proof acceptance; it is not a production Trifold signer or
guardian quorum. The EXCAL wallet's trifold_lockbox.py and txpq.py contain the
actual Trifold signing and verification code. Frostgate is a separate
Taproot FROST vault and does not sign EXCAL's native locks.

## Broadcast

Construction submit is enabled only when the adapter is embedded with the
live EXCAL Node object. It calls Node.dispatch("sendrawtransaction", ...),
which invokes the ordinary mempool validation and P2P relay path. A
standalone ChainState-only adapter cannot broadcast.

## Rosetta CLI validation

Use the profiles in coinbase/rosetta-cli/mainnet.json and
coinbase/rosetta-cli/testnet.json with coinbase/rosetta-cli/config.json.
The unit-test workflow is .github/workflows/rosetta-tests.yml.

Required before production or a Coinbase conformance claim:
- Run the complete Python suite and Rosetta CLI check:data.
- Test all lock witness vectors, malformed-witness rejection, activation
  boundaries, HTLC timeout paths, Trifold spent-leaf replay, and KNOT gating.
- Test construction/offline construction with a wallet client that supports
  EXCAL's custom Trifold and KNOT extension types.
- Run two-node broadcast/relay, mempool conflict and reorg tests.
- Obtain independent review of the custom Trifold construction. The existing
  source audit explicitly says it has no formal security proof.
