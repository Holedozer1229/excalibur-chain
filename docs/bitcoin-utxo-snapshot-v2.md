# Bitcoin inherited-UTXO snapshot format v2

**Status: importer contract; not an activation certificate.** This document defines
the file format consumed by `utxodb.py`. A file conforming to this format is
not, by itself, proof that its rows are the complete Bitcoin UTXO set. That
requires an independently reproduced export from Bitcoin Core and comparison
against the pinned Bitcoin block.

## Pinned source

The EXCAL fork anchor is:

- Bitcoin height: `968698`
- Bitcoin display-order block hash:
  `000000000000000000015d0478e7b60044314fb055fbb306ac7371ef89b60496`

The companion `snapshot_968698.json` metadata must contain all of:

```json
{
  "format": "fork-snapshot-v2",
  "height": 968698,
  "block_hash": "000000000000000000015d0478e7b60044314fb055fbb306ac7371ef89b60496",
  "sha256d": "<64 lowercase hex characters>"
}
```

`sha256d` is SHA256(SHA256(file_bytes)), encoded as lowercase hex. The
metadata's height and block hash are checked against the hard-coded fork
anchor. The binary file's embedded height is checked against metadata.
A matching file digest establishes byte identity only; it does not establish
that the file is complete, canonical, or correctly sourced.

## Binary encoding

All integers are unsigned little-endian unless noted. The file is:

| Field | Encoding |
|---|---|
| Magic | `u32 = 0x45425346` |
| Version | `u32 = 2` |
| Bitcoin height | `u32 = 968698` |
| Record count | `u64` |
| Records | exactly `count` records, no trailing bytes |

Each record is:

| Field | Encoding |
|---|---|
| Transaction ID | 32 raw bytes in the byte order used by EXCAL's outpoint key |
| Output index | `u32` |
| Value | `u64`, satoshis |
| ScriptPubKey length | canonical Bitcoin CompactSize |
| ScriptPubKey | exactly the declared number of bytes |
| Flags | `u8` |
| Coinbase creation height | `u32` |

Flag bits:

- bit 0: spendable (1) or provably unspendable (0)
- bit 1: created by a coinbase transaction
- bits 2-7: reserved; must be zero

The spendable bit must be derived from Bitcoin Core's consensus
`CScript::IsUnspendable()` semantics, not from EXCAL's current script parser
or wallet policy. Do not mark an output unspendable merely because EXCAL does
not yet support its script type.

For a coinbase output, bit 1 is set and the final field is its actual Bitcoin
creation height. For a non-coinbase output, bit 1 is clear and the final field
must be zero. Coinbase maturity is evaluated by EXCAL consensus from the
preserved creation height; it must not be inferred from the snapshot height.

Records must be unique by (txid, vout). Values must not exceed Bitcoin's
`MAX_MONEY`. The importer rejects unknown flag bits, noncanonical CompactSize,
truncation, incorrect height, unsupported v1 files, duplicate outpoints, and
trailing bytes.

## Required independent source procedure

Before producing a candidate file:

1. Use a fully validated Bitcoin Core node at the pinned block hash, not merely
   a node reporting the same height.
2. Export the complete UTXO set at that exact block. Preserve each outpoint,
   value, scriptPubKey, coinbase bit, and coinbase creation height.
3. Independently obtain `gettxoutsetinfo` at that same block and compare its
   best block, transaction/output statistics, and total amount with the
   export. Where Bitcoin Core exposes a UTXO-set hash for that release, record
   it and verify it independently.
4. Rebuild the v2 file twice from independent exports and require byte-identical
   output and identical SHA256d.
5. Publish the source Bitcoin Core version, exact block hash, export command,
   builder version/commit, file digest, row count, total value, and independent
   verification results alongside the file.

The current repository does not contain the full Bitcoin snapshot or a
verified export pipeline. Do not invent the missing dataset, set an activation
height, or claim inherited ownership until these steps and the full inherited
Bitcoin script/witness authorization tests pass.

## Activation safety

The v2 importer is deliberately incompatible with v1. Existing v1 files omit
coinbase provenance and cannot be upgraded losslessly by guessing. A v1 or
unverified database must be rebuilt from a verified v2 source. This importer
change does not activate the snapshot or change any existing chain history.
