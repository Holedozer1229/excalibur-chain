# EXCAL Rosetta native lock and witness support

This adapter uses the canonical EXCAL transaction serializer, lock parser,
Trifold witness codec and consensus validator. It does not translate EXCAL
locks into Bitcoin script or pretend every witness is ECDSA.

## Lock matrix

| Lock | Construction payload | Combine witness | Validation |
|---|---|---|---|
| PKH | ECDSA SIGHASH_ALL | compressed pubkey + 64-byte signature + flag | EXCAL validate_tx |
| BRIDGE | ECDSA SIGHASH_ALL | pubkey + signature + flag; x-coordinate checked | EXCAL validate_tx |
| P2PK (legacy) | ECDSA SIGHASH_ALL | 65-byte push + signature + flag | legacy script evaluator |
| OPEN / OP_TRUE | none | empty scriptSig | EXCAL validate_tx |
| PQH | custom trifold payload | complete txpq.encode_witness bytes | Trifold verify + spent-leaf rules |
| HTLC | ECDSA SIGHASH_ALL | mode + pubkey + signature + flag + secret (claim) + descriptor | descriptor, secret, key and timeout checks |
| QHTLC | custom trifold payload | mode + Trifold witness + secret (claim) + descriptor | Trifold verify, branch, timeout and shared spent-leaf rules |
| KNOT | custom excal_knot payload | 16-byte t_star + 40-byte descriptor | deterministic KNOT commitment check |

KNOT is staged at its configured activation height; the adapter refuses
construction below activation. Legacy P2PK and OP_TRUE are refused after the
Lockbox retirement height. Output locks are passed through unchanged and
checked by consensus at the target height.

## Rosetta extension types

The Rosetta standard does not define Lamport/Trifold or KNOT-preimage
signature types. This adapter therefore uses explicit EXCAL extension values
trifold and excal_knot, advertised in NetworkOptions metadata. Do not
rename these to ecdsa, ed25519 or another unrelated standard type.
A Coinbase/rosetta-cli client must be tested to confirm it tolerates these
chain-specific extensions before claiming conformance.

For PQH and QHTLC, the signing service returns the complete native scriptSig
as Signature.hex_bytes with signature_type: "trifold". The EXCAL node
then decodes and consensus-validates it. For KNOT, the complete 56-byte
witness is returned with signature_type: "excal_knot". HTLC ECDSA signatures
carry metadata.mode, metadata.descriptor, and (claim only) metadata.secret.

## Wallet and URUU boundary

The actual Trifold signing primitive is in EXCAL's trifold_lockbox.py,
txpq.py, and excalibur_wallet/wallet.py::Wallet.trifold_key(). The
wallet persists the one-time leaf counter and txpq.sign_pqh_input,
sign_qhtlc_claim, and sign_qhtlc_refund reserve leaves in the shared
spent-leaf registry before emitting witness material. Never reset, copy back,
or bypass those counters. A failed post-reservation transaction burns the
leaf by design.

The separate Uruu-Secure-Recovery repository is a recovery dashboard/API;
its current crypto.ts explicitly implements mock HMAC verifier signatures
and synthetic proof acceptance, and its on-chain routes are skeletons. It
does not implement a production Trifold signer or cryptographic guardian
quorum. excalibur_wallet/uruu.py is a read-only URUU ERC-20 balance client.
excalibur_wallet/frostgate.py signs the wallet's separate Taproot FROST
vault, not EXCAL's Trifold/PKH transaction locks. None of those demo or
unrelated signatures are treated as EXCAL authorization here.

## Broadcast

The /construction/submit endpoint
is enabled only when the adapter is embedded with the live EXCAL Node object.
It delegates to Node.dispatch("sendrawtransaction", [raw_hex]), which calls
the normal mempool validation and P2P relay path. A standalone ChainState-only
process can inspect and construct but cannot broadcast. RPC/P2P exposure and
TLS remain deployment responsibilities.

## Release gates

- Run the complete Python test suite and Rosetta CLI Data API checks.
- Verify all lock witness vectors, malformed-witness rejection, activation
  boundaries, HTLC early-refund rejection, Trifold leaf replay rejection,
  KNOT staged-activation rejection, and mempool double-spend behavior.
- Test trifold and excal_knot extension interoperability with the exact
  Rosetta client / Coinbase integration target.
- Run two-node broadcast/relay and reorg tests.
- Obtain independent review of the custom Trifold scheme. Its source
  explicitly describes it as a custom parameterization without a formal
  security proof; this adapter does not upgrade that claim.
