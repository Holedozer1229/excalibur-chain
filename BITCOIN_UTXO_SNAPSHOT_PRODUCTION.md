# Producing an EXCAL Bitcoin anchor snapshot

The importer accepts only snapshot-v2 at Bitcoin height **968,698**. The
adapter in `scripts/convert_utxo_forge_tsv.py` converts a UTXO Forge TSV
release into that binary format; it does not create or validate a Bitcoin
UTXO set.

## Required source evidence

Before conversion, obtain a release whose manifest identifies all of:

- Bitcoin mainnet block height exactly `968698`
- the block hash at that height
- the exact UTXO row count
- the SHA-256 of the original compressed TSV archive

Keep the original archive and manifest beside the generated snapshot. A
current-height release is not interchangeable with the anchor release.
UTXO Forge documents these TSV fields: `txid`, `vout`, `value_sats`,
`height`, `coinbase`, `script_type`, `address`, and
`script_pub_key`. Its public free-download speed limit makes large exports
slow; do not pay for a release just to run this adapter.

## Convert

Decompress the exact release to a TSV file, retaining the original archive:

```sh
zstd -dc utxos.tsv.zst > utxos.tsv
python3 scripts/convert_utxo_forge_tsv.py utxos.tsv snapshot_968698.dat \
  --source-archive utxos.tsv.zst \
  --height 968698 \
  --block-hash <64-hex-block-hash-from-manifest> \
  --manifest release-manifest.json
```

The adapter verifies the archive SHA-256, manifest height/hash binding,
header, row count, integer satoshi values, creation heights, coinbase flags,
and script hex. It preserves raw script bytes and coinbase creation heights.
Publisher txids are reversed from display order into the importer’s internal
byte order. The output is written atomically.

The manifest key aliases currently accepted are:
- height: `height` or `block_height`
- block hash: `block_hash` or `bestblock`
- row count: `row_count` or `utxo_count`
- archive SHA-256: `sha256` or `file_sha256`

If the publisher's actual manifest uses a different schema, adapt it
explicitly; do not silently guess values.

## Mandatory independent verification before activation

This conversion is only a format bridge. It does **not** prove the TSV
contains every Bitcoin UTXO, and the resulting SHA-256/SHA256d only identify
the bytes produced. Before any inherited balance is activated:

1. Confirm the source block hash at height 968,698 against an independent
   Bitcoin block source.
2. Have at least two independently operated Bitcoin Core nodes compute
   `gettxoutsetinfo muhash 968698` (with `coinstatsindex`) and agree on
   block hash, MuHash, output count, and total amount.
3. Reconcile the converted dataset against that Core evidence using a
   verifier that computes the Bitcoin Core MuHash over every serialized
   output. A row count and total-value match alone are insufficient.
4. Review all script types against EXCAL’s spending interpreter. Never
   translate a script into an address-only or administrator-controlled
   balance. Unsupported scripts remain locked until a consensus-safe
   compatibility path is reviewed.
5. Publish the exact source archive hash, manifest, anchor block hash,
   Core version, MuHash, row count, total, converter version, and output
   hash in a reproducible audit record.

Bitcoin Core documents historical `gettxoutsetinfo` queries when the
coinstats index is available. A public MuHash explorer can provide a
cross-check, but it is not a substitute for two independent validating
nodes or for checking every output.

**Fail closed:** no snapshot, no verified inherited balances. This PR does
not activate inheritance, change consensus, or claim private-key recovery.
