# Bitcoin UTXO snapshot format v2

This specification is the importer contract for `utxodb.py`. It is not, by
itself, evidence that a production Bitcoin UTXO set has been generated or
verified.

## Header

All integers are little-endian:

| Field | Width | Required value |
|---|---:|---|
| Magic | u32 | `0x45425346` |
| Version | u32 | `2` |
| Bitcoin block height | u32 | Must equal the configured anchor height |
| Record count | u64 | Exact number of following records |

## Each output record

| Field | Encoding |
|---|---|
| Transaction ID | 32 bytes, internal/raw byte order used by the chainstate |
| Output index | u32 little-endian |
| Value | u64 little-endian, in satoshi-sized units |
| Locking script | Bitcoin-style canonical varint length, then exact script bytes |
| Flags | u8; bit 0 means spendable; all other bits are reserved and must be zero |
| Coinbase flag | u8; exactly 0 or 1 |
| Coinbase creation height | u32 little-endian; nonzero only when coinbase flag is 1 |

A coinbase output must retain its original creation height so the fork can
apply the 100-block maturity rule. A non-coinbase output must encode creation
height zero. Records must be complete, count-exact, and consume the file
exactly; truncation, noncanonical varints, unknown flag bits, duplicate
outpoints, or trailing bytes cause import failure.

## Compatibility and rollout

Version 1 is intentionally rejected by the updated importer because it
contains no coinbase lineage. Do not convert v1 records by filling
`is_coinbase=0`; that would incorrectly make immature Bitcoin coinbase
outputs spendable.

The snapshot producer must be updated to emit v2, then independently rebuilt
from Bitcoin Core state at the exact committed anchor. Compare record count,
spendable count, total value, script distribution, and a deterministic
manifest/hash across at least two independent builds before activation.

This importer change does **not** activate inherited balances. Network-wide
activation height/hash, consensus-pinned snapshot commitment, complete script
validation, and reorg/activation tests remain separate release blockers.
