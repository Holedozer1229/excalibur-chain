# EXCAL Bitcoin Ownership Inheritance — Source Audit

**Audit date:** 2026-11-23  
**Repository:** `Holedozer1229/excalibur-chain`  
**Reviewed ref:** `master` at `60b84c7175ea378c321b27562552e20571fca9f3`  
**Scope:** read-only source inspection of `chainstate.py`, `utxodb.py`, `txscript.py`, `genesis_fork.py`, `stratum_fork.py`, and repository metadata.  
**Status:** findings are not a consensus certification; no production node or private runtime data was accessed.

## Executive finding

EXCAL has meaningful UTXO snapshot infrastructure. It is not accurate to describe the implementation as merely anchoring a Bitcoin header. The current source contains a two-tier UTXO design (immutable Bitcoin snapshot + EXCAL overlay), activation-height logic, an activation-block coinbase commitment, cumulative-work tip selection, side-branch storage, and reorganization replay.

However, the public source does **not yet establish that all Bitcoin owners retain their original spending conditions**. Several correctness and consensus-pinning gaps must be resolved before calling EXCAL a balance-preserving Bitcoin fork.

## Confirmed implementation

- `chainstate.py`: `_open_snapshot()`, `_snapshot_active_at()`, `_fork_utxo()`, `_check_activation_commitment()`, `_select_best_tip()`, and `submit_block()`.
- `utxodb.py`: SQLite snapshot database, immutable snapshot handle, EXCAL overlay, spent-output tombstones, snapshot stats, and a `spendable` field.
- `chainstate.py`: candidate branch work is computed cumulatively; heavier branches can become active and UTXOs are replayed along the selected path.
- `genesis_fork.py`: fork anchor is declared as Bitcoin block 968,698 with hash `000000000000000000015d0478e7b60044314fb055fbb306ac7371ef89b60496`.

## Consensus blockers

### 1. Snapshot activation is optional local configuration

In `chainstate.py::_open_snapshot()`:
- Missing snapshot metadata returns `None` and the node explicitly falls back to fork-only UTXOs.
- `activation.json` is optional; without it, the snapshot remains inactive.
- The activation height and snapshot hash are read from local JSON rather than being pinned in the public fork-network consensus parameters.
- The public `master` tree inspected during this audit did not contain a `fork_balances/` directory or the referenced snapshot artifacts.

**Risk:** two nodes can have different local snapshot files/configuration and therefore different UTXO state/activation knowledge. A coinbase commitment does not fix this if nodes disagree on the expected activation height/hash.

**Required:** make the source block hash, snapshot commitment, format version, and activation height deterministic fork-network consensus parameters. A node must not silently validate fork-only state if the network requires the snapshot. First inspect the actual production node's local snapshot and activation files; do not change existing history blindly.

### 2. Snapshot importer drops coinbase origin metadata

In `utxodb.py::_load_dat_into_db()`, each imported record is inserted with `is_cb=0` and `cb_h=0`. The record format read by this importer contains txid, vout, value, script, and a one-byte flags field, but the importer does not use that flag to reconstruct coinbase status or creation height.

The transaction validator enforces EXCAL's `COINBASE_MATURITY = 100` using `is_cb` and `cb_h`. Imported Bitcoin coinbase outputs will not receive that maturity check if these fields remain zero.

**Required:** snapshot schema v2 must carry and validate coinbase origin and creation height (or provide an independently verifiable reconstruction method). Test immature and mature inherited coinbase spends at the exact boundary.

### 3. The `spendable` column is not enforced on lookup paths

The importer stores `spendable` in SQLite. But:
- `SnapshotDB.get()` selects and returns rows without checking `spendable`.
- `SnapshotDB.find_by_spk()` enumerates rows without checking `spendable`.
- `UtxoSet.items()` enumerates all snapshot rows without checking `spendable`.

**Risk:** an output intentionally classified as non-spendable can still be exposed as an ordinary UTXO to validation or wallet/query code.

**Required:** define the exact consensus meaning of the flag and enforce it consistently. Preserve a separate audit/reporting view of excluded outputs; do not turn unsupported scripts into OPEN locks or administrator-controlled outputs.

### 4. Bitcoin script compatibility is not demonstrated

`txscript.py::parse_tx()` explicitly parses legacy transaction serialization and rejects trailing bytes. The validator requires version 1 and locktime 0 and recognizes EXCAL's custom lock vocabulary. This is not Bitcoin's full Script/witness consensus engine.

The inspected source does not demonstrate original authorization semantics for all inherited output classes, including:
- P2SH and P2SH multisig;
- native SegWit P2WPKH and P2WSH;
- Taproot P2TR key-path and script-path spends;
- Bitcoin CSV/CLTV and other script-dependent conditions;
- witness and Taproot signature hashing (BIP-143/BIP-341/BIP-342).

**Required:** implement a Bitcoin-compatible validation path for inherited UTXOs or a formally specified, cryptographically safe migration that preserves the original owner's authorization. Each supported class needs Bitcoin Core-derived test vectors. Until then, do not claim all Bitcoin UTXOs are inherited with unchanged spending conditions.

### 5. Snapshot file header and anchor need cross-checks

`build_snapshot_db()` verifies a SHA256d file digest and records a metadata height. `_load_dat_into_db()` reads the snapshot file's own height/count header, but the inspected code does not compare the file header height with the metadata height or independently verify the exact source block hash against the declared Bitcoin anchor.

**Required:** verify all of the following before opening the DB:
- source height equals exactly 968,698;
- source block hash equals the declared Bitcoin hash;
- snapshot file header height equals metadata height;
- row count matches metadata and independently rebuilt count;
- every outpoint/value/script/coinbase field is canonical;
- file digest and deterministic UTXO commitment match the pinned consensus parameters.

A SHA256d file checksum establishes byte identity with a chosen file, not completeness or correctness of the UTXO set. Independent reconstruction from a separately validating Bitcoin Core node is required.

### 6. AuxPoW Bitcoin-parent hash byte order

EXCAL's own header validation uses a custom big-endian interpretation of the raw SHA256d digest. That may be a deliberate EXCAL consensus convention if all EXCAL miners and validators consistently implement it.

But `validate_auxpow()` applies the same big-endian comparison to `sha256d(parent_header)` when the parent header is a Bitcoin SHA256d header. Bitcoin's uint256 target interpretation uses the little-endian integer represented by the raw digest bytes. This needs a Bitcoin-parent regression test and likely a separate little-endian parent comparison. Do **not** change EXCAL's own PoW interpretation as part of this fix without a separate consensus analysis.

## Reorg review correction

The earlier preliminary review incorrectly suggested no chainwork/reorg handling was demonstrated. The current `chainstate.py` does implement cumulative work, side branches, and reorganization replay. Remaining work is adversarial testing:
- competing branches with different cumulative work;
- equal-work tie behavior and restart determinism;
- snapshot activation across a reorg that crosses the activation height;
- spent-output and Trifold spent-leaf rollback/replay;
- deep-reorg guard behavior and stale-node recovery.

## Public marker and live-state caveat

The tracked `chain.jsonl.height` marker says height 44,629 and contains a hash/timestamp. The source declares KNOT activation at height 44,520. This is a repository marker, not a live RPC query. It does not prove the current production tip or whether any locally deployed snapshot activation file exists.

Before consensus work proceeds, the operator should collect from the production fork node:
- `getblockcount`;
- `getbestblockhash`;
- the block hash at the reported height;
- whether snapshot metadata, data file, SQLite DB, and activation config exist;
- snapshot metadata hash, source height/hash, row count, total value, and spendable count.

Do not share RPC credentials, wallet files, private keys, or seed phrases.

## Recommended sequence

1. Capture and independently verify the production node's exact state and determine whether snapshot activation is pending or already active.
2. Specify the inherited Bitcoin UTXO serialization and classification policy.
3. Build a deterministic snapshot exporter/importer with source block hash, coinbase metadata, and explicit spendability reasons.
4. Pin snapshot commitment and activation height in a versioned consensus upgrade.
5. Implement original Bitcoin script authorization for each inherited output class; never substitute an admin key or OPEN output.
6. Add differential tests against Bitcoin Core and multi-node consensus/reorg tests.
7. Only then stage activation on a separate network/branch with a published upgrade plan.

**No live consensus rules were modified in this audit.**
