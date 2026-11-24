# EXCAL Rosetta API

## Implementation

The active adapter is in rosetta/excal_rosetta.py with construction logic in
rosetta/construction.py. It is backed by the live EXCAL ChainState and UTXO
set. The network identifier is blockchain "excal", network "mainnet" (or
"testnet" for the test network). Currency is EXCAL / 8 decimals on mainnet
and tEXCAL / 8 decimals on testnet.

This is an implementation under validation, not a statement of Coinbase
approval or Rosetta certification. The production Bitcoin-anchored EXCAL
chain uses ChainState consensus network "fork"; the Rosetta network identifier
presented to Coinbase remains "mainnet". These are separate settings.

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
- POST /account/balance (current and historical balances via ChainState replay)
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

### Target-client acceptance — measured 2026-11-23 (Stage 4)

A stock rosetta-cli v0.10.4 / standard Rosetta client **rejects** these
types in the Construction flow. Evidence:

- The rosetta-sdk-go `types` package defines exactly five
  `SignatureType` values (`ecdsa`, `ecdsa_recovery`, `ed25519`,
  `schnorr_1`, `schnorr_poseidon`), and the asserter exposes
  `SignatureType` validation that fails anything else with "not a
  supported SignatureType". The v0.10.4 binary carries the same
  failure strings ("signature type %s is invalid", "signing payload
  signature type %v is invalid", "cannot determine signature type for
  payload", "sign: unexpected Signature type while signing"). The
  CLI's signer can only sign the five standard types, so
  `check:construction` cannot be run end to end for PQH/QHTLC/KNOT
  inputs at all — it fails at signing, before the server is involved.
- `check:data` is **not** evidence about the custom types either way:
  blocks carry operations only, never signatures, so the Data API
  never presents a `trifold` or `excal_knot` value to the asserter.
  The full-range `check:data` run (5,598/49,999 blocks passed, 0
  failures, when the VM reboot killed it — see `coinbase/README.md`)
  proves only that the `/network/options` advertisement itself passes
  asserter validation. Verified live: `rosetta-cli
  utils:asserter-configuration` against the running server succeeded,
  and the generated asserter config contains no signature-related key
  at all — the asserter has no allowlist for signature types.
- What a third-party client must do: implement the EXCAL signer
  (local bridges `rosetta/trifold_signer.py` for PQH/QHTLC and
  `rosetta/knot_signer.py` for KNOT) or equivalent chain-specific
  code, and bypass/extend the stock asserter's signature-type check
  for these two values. Read the type from
  `/network/options` `metadata.excal_extensions`
  (`trifold_signature_type`, `knot_signature_type`), and read each
  signing payload's `metadata`: for `trifold`, `hex_bytes` is the
  32-byte sighash digest to sign with the Trifold one-time key and
  `Signature.hex_bytes` must be the complete native scriptSig witness
  bytes, not a 64-byte signature; for `excal_knot`, `hex_bytes` is a
  correlation digest only — do NOT sign it — and
  `Signature.hex_bytes` must be the 56-byte preimage witness
  (16-byte `t_star` followed by the 40-byte KNOT descriptor).
  `/construction/combine` matches signatures by the exact
  (digest, signature_type) pair and rejects a witness submitted
  under the wrong type. Tests:
  `tests/test_rosetta_custom_signature_types.py` (8 tests).

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
