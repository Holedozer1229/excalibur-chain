# Coinbase Rosetta Integration — AetherionEXCAL

## Overview

This directory contains the complete [Coinbase Rosetta](https://www.coinbase.com/cloud/developers/rosetta) integration for **AetherionEXCAL** — a post-quantum Bitcoin fork with 21M supply, 60-second blocks, and hash-only security.

**EXCAL is the new Qrevolution.**

## What's Here

| File | Purpose |
|---|---|
| `rosetta-config.json` | Main Rosetta API configuration |
| `rosetta-cli/mainnet.json` | Rosetta CLI (mesh-cli v0.10.4) syncer configuration for mainnet |
| `rosetta-cli/testnet.json` | Rosetta CLI (mesh-cli v0.10.4) syncer configuration for testnet |
| `rosetta-cli/mainnet-asserter.json` | Asserter configuration generated from the live mainnet server |
| `rosetta-cli/testnet-asserter.json` | Asserter configuration for testnet (same shape, testnet genesis) |
| `rosetta-cli/bootstrap_tx.json` | Genesis bootstrap transaction |
| `rosetta.md` | Detailed Rosetta API documentation |
| `listing-proposal.md` | Exchange listing proposal |
| `coinbase-listing-letter.md` | Formal letter to Coinbase listing team |

## Quick Start

### 1. Install Rosetta CLI

```bash
# mesh-cli v0.10.4 (the rosetta-cli repo was renamed to mesh-cli)
curl -sL -o rosetta-cli.tar.gz \
  https://github.com/coinbase/mesh-cli/releases/download/v0.10.4/rosetta-cli-0.10.4-linux-amd64.tar.gz
tar xzf rosetta-cli.tar.gz
./rosetta-cli-0.10.4-linux-amd64 version  # v0.10.4
```

### 2. Start the Rosetta server (serves the live fork chain as `mainnet`)

```bash
python3 rosetta/excal_rosetta.py --data-dir ./chaindata_fork \
  --host 127.0.0.1 --port 8070 --network mainnet --chain-network fork
```

### 3. Validate with the official CLI (bounded range; full sync is slow)

```bash
rosetta-cli check:data \
  --configuration-file coinbase/rosetta-cli/mainnet.json \
  --asserter-configuration-file coinbase/rosetta-cli/mainnet-asserter.json \
  --data-dir /tmp/rosetta-check \
  --start-block 49900
# End condition (49999) lives in the scratch copy used for the run, not
# in the repo config, so the check follows the live tip by default.
```

Notes:

- The syncer configs set `max_sync_concurrency: 1` and `http_timeout: 30`:
  this server is single-process Python, so concurrent block fetches
  serialize on the GIL and cold renders replay the chain (~5–15s at the
  50k tip). First call per height pays the replay; sequential renders
  reuse the cached UTXO views.
- `rosetta-cli/config.json` targets a pre-rename CLI format and is
  superseded by `mainnet.json` / `testnet.json`; it is left in place for
  reference only.
- The asserter files were generated from the live server with
  `rosetta-cli utils:asserter-configuration`. Regenerate them after any
  `/network/options` change.

## Network Summary

| Parameter | Value |
|---|---|
| Blockchain | `excal` |
| Network | `mainnet` / `testnet` |
| Currency | `EXCAL` (8 decimals) |
| Max Supply | 21,000,000 EXCAL |
| Block Time | 60 seconds |
| Consensus | SHA-256d Proof-of-Work |
| Signatures | SHA-256 hash-only (post-quantum) |
| Address Format | 20-char uppercase hex |

## Operation Types

The server advertises these operation types in `/network/options`
(`allow.operation_types`): `coinbase`, `transfer`, `input`, `output`,
`fee`. Blocks in practice contain only `coinbase` and `transfer`
operations. (An earlier version of this file listed `nft_mint` and
`bridge` as operation types; the server does not emit operations of
those types — the bridge lock is a lock type, not an operation type —
so they were removed 2026-11-23.)

## Security Features

- **AES-256-GCM** encryption for key storage and network messaging
- **SHA-256 hash-only** signatures — no elliptic curves
- **Post-quantum Trifold** block countersigning
- **scrypt KDF** (N=2^14) for passphrase derivation
- 116 passing Python tests covering all core modules (see the evidence package below for the exact count and what it covers)

## Exchange Listing

For exchange listing inquiries, see:

- [`listing-proposal.md`](listing-proposal.md) — Full listing proposal document
- [`coinbase-listing-letter.md`](coinbase-listing-letter.md) — Formal letter to Coinbase

## Documentation

- [AetherionEXCAL Website](https://www.aetherion-oracle.com)
- [Tokenomics](../TOKENOMICS.md)
- [Governance](../GOVERNANCE.md)
- [Security Audit](../AUDIT.md)
- [Rosetta API Docs](rosetta.md)

## Contact

- **Website:** https://www.aetherion-oracle.com
- **GitHub:** https://github.com/excalibur-chain/excalibur-chain

---

# Submission evidence package — 2026-11-23

Engineering evidence for the EXCAL Rosetta implementation on branch
`feature/excal-rosetta-native-v1`, PR #23. This is an evidence package,
**not a listing claim and not Coinbase certification**. Whether EXCAL is
listable, and on what terms, is Coinbase's decision. Nothing here
asserts readiness beyond the evidence stated.

## Commits

| Commit | What |
|---|---|
| `f01bf61434e27d8cfa5e516cf1e96901a573286f` | Remote head at start of this program (tip-advance guard; registry `pair_key`/`replace_with`) — nothing pushed yet at time of writing |
| `505367bb` (Stage 1) | Persistent per-height UTXO delta index — no more full-chain replay per lookup |
| `73b8bbfa` (Stage 3) | Network-aware `validate_tx` / KNOT signer; lock-witness, activation, timeout, replay, fee and two-node reorg tests |
| `6b5ece2e` (Stage 4) | Custom signature-type acceptance evidence; witness metadata on `trifold` / `excal_knot` payloads; 8 new tests |
| (Stage 5 docs commit — HEAD at submission time; verify with `git -c core.hooksPath=/dev/null log --oneline -1`) | This submission package + Stage 4 client documentation |

All work is local on the detached HEAD in `~/workspace/excalibur-chain-rosetta`; no push has been made from this program.

## Test evidence

- Full Python suite: `python3 -m unittest discover -s tests` — 116 tests OK (skipped=1; 284.7s; 1 graceful skip for the missing prometheus-client). The suite went red once during this program only because the VM reboot wiped the system `customtkinter` package (reinstalled 6.0.0; the failure was the pre-existing atomic-swap import, not a code failure).
- Stage 1 new tests: 14/14 (persistent UTXO delta index, incl. equality with the full-replay path at spot heights and the miner balance 2,495,147.9919 EXCAL at tip).
- Stage 3 new tests: 42 (40 lock-witness vectors + 2 reorg/relay).
- Stage 4 new tests: 8/8 (`tests/test_rosetta_custom_signature_types.py`).
- Official `rosetta-cli` v0.10.4 `check:data`, bounded range 49900–49999: **PASSED** — 100 blocks / 100 transactions / 100 operations, 100 active reconciliations, 0 failed, 100% coverage; Request/Response, Response Assertion, Block Syncing, Balance Tracking and Reconciliation all PASSED.
- Official `rosetta-cli` v0.10.4 `check:data`, full range 0–49999: **INCOMPLETE — do not present as complete.** The run (server PID 4947 on port 8070, CLI PID 6133) reached **block 5,598/49,999 (11.196%), 0 failures, 100.000000% coverage** (5,598 blocks, 5,598 transactions, 5,600 operations, 5,654 reconciliations, 64 inactive) when the VM rebooted at 2026-11-24 03:10:12 UTC and killed both processes; the log (`~/workspace/rosetta-check-data-full.log`) is frozen at 03:11:00 UTC. At death the CLI reported a rate of ~0.95 blocks/s and ~12h56m remaining. The run was not restarted — that decision sits with the program coordinator. CPU starvation is the cause of the slowness: the VM is a 1.5-shared-CPU cell running at load ~10–21, and the server is single-process Python.
- Observed fragility during the full-range run: the CLI retried `/account/balance` fetches 7 times after its 30s client timeout expired while the server was slow under load (2026-11-24 ~01:56 UTC log lines); all retries recovered and no reconciliation failed, but balance calls can exceed the CLI's 30s `http_timeout` when the VM is loaded.

## Endpoints verified live against the real fork chaindata (tip 49999)

Against the live 50k-block fork chain, by hand and via the CLI:

- `/network/list`, `/network/options`, `/network/status` (tip 49999, genesis `000000000000000000015d0478e7b60044314fb055fbb306ac7371ef89b60496`)
- `/block` (heights 0 and 49999; height 50000 correctly returns block-not-found), `/block/transaction`
- `/account/balance`, including historical balances (verified at heights 100/1000/25000/42899/49899; miner balance 2,495,147.9919 EXCAL at tip, exact match to an independent full replay)
- `/construction/derive`, `/construction/preprocess`, `/construction/metadata` (rejects immature tip coinbase), `/construction/payloads`, `/construction/combine`, `/construction/parse`, `/construction/hash`
- `/construction/submit` — **mempool-admission-only semantics**: with a Mempool instance it performs local mempool admission and explicitly reports `relay_attempted: false`. It does not broadcast to peers unless embedded with a live Node object implementing `dispatch("sendrawtransaction", …)`. Standalone mode (ChainState only) returns an explicit unavailable error. Peer delivery is never claimed.

## Supported vs unsupported

Supported: Data API (network list/options/status, canonical block and transaction retrieval, historical UTXO-backed balances, live mempool listing/transaction details when a Mempool instance is supplied); Construction API (derive, preprocess, metadata, payloads, combine, parse, hash, submit as above); lock paths PKH, BRIDGE, legacy P2PK, OPEN/OP_TRUE, PQH, HTLC, QHTLC and KNOT, with activation gates, coinbase maturity, value/fee reconciliation and EXCAL consensus validation before a signed transaction is returned.

Not supported / not claimed: `check:construction` end to end for the custom locks (see below); no P2P relay from the standalone server; no persistent UTXO-index checkpoints (see limitations); no independent security review of the custom Trifold scheme (its source explicitly says it has no formal security proof).

## Custom signature extensions — `trifold` and `excal_knot`

The Rosetta standard defines no Lamport/Trifold or KNOT-preimage
signature type, so the adapter uses explicit EXCAL extension values,
advertised in `/network/options` `metadata.excal_extensions`
(`trifold_signature_type`, `knot_signature_type`, `witness_encoding:
"native scriptSig hex"`). They are **not** mislabeled as ECDSA or
Ed25519. Full client-handling documentation is in `rosetta.md`
("Signature extensions") and `../rosetta/LOCK_SUPPORT.md`.

Target-client acceptance, measured 2026-11-23 (Stage 4) — the honest
verdict is **a stock rosetta-cli / standard Rosetta client rejects
these types in the Construction flow**:

- The rosetta-sdk-go `types` package defines exactly five
  `SignatureType` values (`ecdsa`, `ecdsa_recovery`, `ed25519`,
  `schnorr_1`, `schnorr_poseidon`); the asserter's `SignatureType`
  validation fails anything else with "not a supported SignatureType".
  The v0.10.4 binary carries the same failure strings. The CLI signer
  can only sign the five standard types, so `check:construction`
  cannot be run end to end for PQH/QHTLC/KNOT inputs — it fails at
  signing, before the server is involved.
- `check:data` is no evidence about the custom types either way:
  blocks carry operations only, never signatures. The bounded and
  full-range `check:data` results above prove only that the
  `/network/options` advertisement itself passes asserter validation
  (verified live: `rosetta-cli utils:asserter-configuration` against
  the running server succeeded; the generated asserter config has no
  signature-related key at all).
- What was fixed to make the types consumable without inventing a
  standard claim: each custom signing payload now carries `metadata`
  stating exactly what `Signature.hex_bytes` must contain. For
  `trifold`, `hex_bytes` is the 32-byte sighash digest to sign with
  the Trifold one-time key and the signature is the complete native
  scriptSig witness bytes. For `excal_knot`, `hex_bytes` is a
  correlation digest only — do NOT sign it — and the signature is the
  56-byte preimage witness (16-byte `t_star` + 40-byte descriptor).
  `/construction/combine` matches signatures by the exact
  (digest, signature_type) pair and rejects a witness under the wrong
  type. A third-party client must implement the EXCAL signer
  (`rosetta/trifold_signer.py`, `rosetta/knot_signer.py`) or
  equivalent and bypass/extend the stock asserter's signature-type
  check for these two values. Tests:
  `tests/test_rosetta_custom_signature_types.py` (8 tests).

## Limitations (open, stated plainly)

- **CI is dead.** GitHub Actions runs fail in 4–5s with no logs (GitHub billing lock, same as the other repos). VM runs are the only signal.
- **No persistent UTXO-index checkpoints.** The Stage 1 delta index is rebuilt from the replay on every cold load (~121s cold load for the 50k chain); worst-case `utxo_at` is ~0.14s mid-chain. There is no checkpoint file to skip the rebuild.
- **Two-node test had no live P2P sockets.** The Stage 3 relay/reorg tests deliver validated block records between two ChainState nodes; no live peer sockets were involved.
- **`Mempool.add` and `genesis_fork.validate_block` still read process-global gates** (out of scope for this program; documented, not fixed).
- **`trifold_signer` builds PQH/QHTLC witnesses with no activation check of its own** — consensus rejects at `combine`, but the signer will happily build a witness for a pre-activation spend.
- **Single-process Python server under a loaded VM**: balance calls can exceed the CLI's 30s timeout (7 retries observed during the full-range run; all recovered).
- **KNOT activation discrepancy — open, needs Lux's call, do NOT resolve silently.** The task brief and memory say KNOT is staged only, activation proposed at height 100000, NOT activated. But `genesis_fork.py` sets `KNOT_ACTIVATION = 44520` with an "ACTIVATED 2026-11-16" comment (commit `d1c72cd0`; comment says live fork tip was ~44,515 at activation), while `self-serve/vendor/genesis_fork.py` still carries 100000. Verified 2026-11-23: no `NETWORKS` entry defines `knot_activation` for any network, so the module default 44520 governs the live fork chain. Stage 3's tests assert the code's behaviour (valid ≥44520, rejected below) and changed no value. Nothing in this program changes any activation value.

## Rosetta CLI configuration note

The full-range `check:data` run used a **scratch copy** of the syncer
config (`~/workspace/rosetta-check-data-full-config.json`), not the repo
config. The only difference is `"end_conditions": {"index": 49999}`
under `data` — added to work around a v0.10.4 CLI panic when the check
otherwise follows the live tip with no end. That field was deliberately
**not** baked into `coinbase/rosetta-cli/mainnet.json`: the repo config
follows the live tip by default, which is the correct behaviour for a
reusable config, and the end condition belongs to the individual run.
If you reproduce the bounded run, add the same field to your own copy.

## What is verified / what is NOT verified / what Coinbase must decide

Verified: the full Python suite (count above); bounded official CLI
`check:data` 49900–49999 passed; the endpoints listed above against the
real fork chain at tip 49999; all lock witness vectors, activation
boundaries, HTLC/QHTLC timeout and refund paths, Trifold leaf replay
rejection, mempool double-spend behaviour, two-node relay/reorg; the
exact asserter behaviour for the custom signature types (rejection by
stock clients, documented above).

NOT verified: full-range `check:data` 0–49999 (incomplete — killed at
block 5,598 by a VM reboot; see above); `check:construction` end to end
for any lock (impossible for the custom locks with the stock CLI, and
not run for PKH either — it needs funded accounts and a live
broadcasting node); acceptance of `trifold`/`excal_knot` by Coinbase's
own integration client (only the stock CLI's rejection is measured);
independent review of the Trifold scheme; production deployment
concerns (TLS/auth in front of the endpoint, key custody, monitoring).

What Coinbase would still need to decide: whether to accept the
`trifold`/`excal_knot` extension types and the chain-specific signer
they require; whether the bounded (100-block) plus partial (5,598-block)
`check:data` evidence suffices pending a completed full-range run; and
the listing decision itself, which this package does not presume.
