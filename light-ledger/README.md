# Light ledger — URUU-anchored trustless checkpoints

A new Excalibur node today must replay the whole fork chain (44k+
blocks, 1.1 GB) before it trusts anything. The light ledger removes
that download without removing the trust. It is the ledger layer of
the quantum P2P EXCAL wallet.

## The three legs

1. **Snapshot.** The QAI auditor (a full node) exports the fork's live
   UTXO overlay at height H — fork-created outputs plus tombstones of
   spent Bitcoin-snapshot outputs — and commits to it with two Merkle
   roots (`overlay_root`, `spent_root`). The snapshot is
   content-addressed: its SHA-256 is in the checkpoint, so a tampered
   download is caught by hashing alone. Format:
   `excal-overlay-snapshot-v1`, gzip JSONL, one line per UTXO.

2. **Checkpoint + attestation.** The checkpoint `{height, tip_hash,
   chainwork, overlay_root, spent_root, ...}` is signed with the QAI
   auditor's Trifold key (hash-only Lamport-style signatures — no curve,
   nothing for a quantum adversary to break). The signature proves WHO
   published the checkpoint. It does not by itself prove the checkpoint
   is TRUE — that is leg 3.

3. **URUU anchor.** The checkpoint hash is anchored on zkSync Era in
   the URUU anchor contract (`anchor_contract.sol`), with a URUU bond
   posted by the auditor and a fraud window (default 24h). Anyone may
   challenge a checkpoint inside the window with a fraud proof (an
   omitted UTXO, a bad tip); a proven challenge voids the checkpoint
   and slashes the bond to the challenger. After the window passes
   unchallenged, the checkpoint is FINAL. A light node bootstraps ONLY
   from final checkpoints.

## What "trustless" means here

No trust in the auditor's key. What remains is (a) zkSync Era
consensus + the anchor contract's code, (b) at least one honest
watcher inside the fraud window, and (c) the fraud-proof verifier
(`lightledger.py` + the contract). That is the standard optimistic
model — trust-minimized, not trust-free. Full replay remains the only
trust-free path.

## URUU (verified live 2026-11-12)

zkSync Era chain 324, token `0x5B6C9d85465Cc6FFe84039183872239657D90208`
("Camelot Excalibur URUU"), 18 decimals, total supply exactly
100,000,000. Bond: 1,000 URUU per checkpoint.

## Files

- `../lightledger.py` — snapshot export/import, Merkle inclusion +
  absence proofs (sorted-tree, adjacency-checked), checkpoint
  attest/verify, fraud-proof build/verify, auditor key management.
- `../lightledger_test_real.py` — real-chain test (see results below).
- `anchor_contract.sol` — checkpoint bond / challenge / finalize.
  Compiles clean with solc 0.8.20. NOT DEPLOYED: deployment needs
  Lux's deployer key + ETH for gas on zkSync Era.
- `uruu_htlc.sol` — the URUU leg of an EXCAL <-> URUU quantum atomic
  swap. Same `sha256(secret)` hash lock as the fork QHTLC leg, so
  revealing the secret claims both legs. Compiles clean with solc
  0.8.20. NOT DEPLOYED.
- `overlay_snapshot_test.jsonl.gz` — reference snapshot at fork height
  44,523 (test run, 1.9 MB). Goes stale as the chain grows; regenerate
  with `lightledger_test_real.py` or `export_overlay` directly.

## Verified results (real chain, 2026-11-12 ~12:12 CST)

- ChainState loaded: tip 44,523, hash `52cfc9f7…`, chainwork
  570195989280312334592582, 77.7s.
- Overlay: 44,414 entries, 2,226,150 EXCAL total; spent tombstones 0
  (the Bitcoin snapshot base is not built on this VM yet — see below).
- Snapshot export + import round-trip: OK, roots match.
  overlay_root `acb4865d…`, snapshot sha256 `a6f678c0…`.
- Checkpoint attested (throwaway test key, leaf 0): Trifold verify
  TRUE, status pending -> final after the window.
- Tamper: dropping one coinbase UTXO changes the root; import of the
  tampered snapshot is rejected ("overlay Merkle root mismatch").
- Fraud proof: omission of a confirmed coinbase UTXO (height 13,164)
  PROVEN against the tampered checkpoint; the same proof FAILS against
  the honest checkpoint (no false positives).
- Merkle unit tests: inclusion 7/7, absence at all three edges,
  wrong-adjacency rejected, present-key rejected, empty set.

## Known limits (honest)

- **Snapshot base not built on this VM.** `fork_balances/` has
  `snapshot_937817` files but not `snapshot_968698.json`, so the fork
  node runs on fork blocks only and this snapshot covers fork-created
  UTXOs only (`spent_count` 0). The base leg (tombstones + base root)
  is phase 2, once the 968698 snapshot is built.
- **On-chain fraud proofs need a header chain.** Challenging an old
  UTXO means submitting every header from its block to the tip
  (31,359 headers for the height-13,164 test UTXO). Frequent
  checkpoints keep that segment short; the Python verifier is the
  reference implementation.
- **Anchor contract not deployed.** Until deployment, checkpoints
  carry `uruu.contract = null` and the anchor leg is pending; legs
  1–2 already verify offline.
- **Node integration pending.** The wallet's P2P sync (main-chat
  build) will consume this module; the `ChainState.load_from_snapshot`
  hook that starts a node from a snapshot instead of full replay is
  not built yet.
