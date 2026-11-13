# Excalibur Wallet

A P2P ledger wallet for the Excalibur fork — real keys, real chain,
real signatures. No demos, no simulated balances, no broadcasts.

- **Keys:** BIP39-style 12/24-word mnemonic, AES-256-CTR + HMAC
  encrypted at rest (600,000-iteration PBKDF2). The mnemonic is shown
  once at creation and never again. Shamir's Secret Sharing (k-of-n)
  seed backup via `wallet split` / `wallet restore --shares`.
- **Ledger:** balance/UTXOs/history from the live node RPC first,
  falling back to a read-only scan of the local `chain.jsonl`, then to
  a verified lightledger snapshot. P2P header sync (`ledger sync
  --via p2p`) walks back from a peer with header PoW + Merkle checks.
- **Aetherion QAI light ledger:** `checkpoint verify` checks the
  QAI-audited Trifold checkpoint attestations actually mined in the
  chain (Dr. Time lineage genesis ← 25344 ← 25351 ← 43750). If an
  attestation cannot be verified from real chain data, the wallet
  falls back to full local verification and says so.
- **URUU:** read-only view of the live zkSync Era contract
  `0x5B6C9d85465Cc6FFe84039183872239657D90208` (100,000,000 supply).
  No keys, no signing, no bridge execution.
- **Frostgate:** 3-of-5 FROST threshold vault (Aethergate Rust code,
  RFC 9591). Dealerless DKG, threshold signing, Taproot key-path
  spends. Testnet-only. The wallet shells out to the real Rust
  binary — the FROST math is never re-implemented in Python.
- **Send:** build + sign + verify locally under the full
  spend-and-sign protocol. **This wallet never broadcasts.** There is
  no broadcast command. Submitting a signed tx is a separate,
  explicit user action outside this wallet.

## Install

Pure stdlib, Python 3.10+. No pip packages.

```sh
./excalibur --help
# Windows:
excalibur.bat --help
# or:
python3 -m excalibur_wallet --help
```

Default datadir: `~/workspace/excalibur-wallet-data` (override with
`--datadir` or `EXCAL_WALLET_DIR`). The passphrase comes from a 0600
file (`--passphrase-file`) or an interactive prompt — never from a
command-line argument.

## Commands

```
wallet create [--words 12|24]        new encrypted wallet (mnemonic shown once)
wallet restore --mnemonic '...'      restore from words
wallet restore --shares S...         restore from k SSS shares
wallet address [--index N]           show a receive address
wallet receive                       fresh receive address
wallet info                          summary (kind, indices, PQH, Frostgate)
wallet balance [--via rpc|local|snapshot]
wallet utxos [--lock HEX]            list UTXOs
wallet history [--limit N]
wallet send --to LOCK --amount AMT   build+sign+verify ONLY (never broadcasts)
wallet locks                         lock types + activation at tip
wallet split --threshold K --shares N  Shamir-split the seed
wallet import-node --wallet FILE [--keyfile F]
wallet htlc create --secret HEX --claim-pubkey HEX --refund-pubkey HEX --timeout H
wallet htlc claim --utxo TXID:VOUT --dest LOCK --secret HEX [--fee N]
wallet htlc refund --utxo TXID:VOUT --dest LOCK [--fee N]
wallet qhtlc create --secret HEX --claim-root HEX --refund-root HEX --timeout H
wallet qhtlc claim|refund --utxo TXID:VOUT --dest LOCK [--fee N]
wallet pqh address                   Trifold-root PQH address
wallet pqh spend --utxo TXID:VOUT --dest LOCK [--fee N] --yes
wallet knot lock|spend ...           TEST-CHAIN ONLY (KNOT staged, not activated)
ledger sync [--via rpc|local|p2p] [--wallet] [--peer HOST:PORT]
ledger tip
checkpoint verify [--file CHECKPOINT.json]
uruu info                            live URUU contract (name/symbol/supply)
uruu balance --address 0x...
frostgate init [--dir D] [--operators 5] [--threshold 3]
frostgate address [--dir D] [--network testnet|regtest|mainnet]
frostgate status [--dir D]
frostgate sign --message HEX32 [--signers 1,2,3]
frostgate spend --prev-txid T --prev-vout N --prev-value S --dest ADDR [--fee N]
node status                          fork node RPC + P2P status
```

Amounts: integer swords, or decimal EXCAL (`1.5` = 150,000,000 swords).
Locks are hex: `00…` PKH, `ff` OPEN, `02…` PQH, `03…` HTLC, `04…`
QHTLC, `05…` BRIDGE. `06…` KNOT is refused on the live fork.

## What each source means

| Source | What it proves |
|---|---|
| `live node RPC` | current tip + indexed UTXOs from your own fork node |
| `local chain scan` | full read-only replay of `chain.jsonl` (slow first run, cached) |
| `verified light snapshot` | lightledger overlay: SHA-256 + Merkle roots verified; fork-created UTXOs only |
| `P2P sync` | headers from a peer, PoW + Merkle verified; full tx validation stays the node's job |

## Honestly still open / blocked

- **No broadcast path** — by design. Sending stops at build/sign/
  verify. Broadcast needs a separate explicit user decision.
- **KNOT (0x06) staged, not activated** (proposed height 100,000).
  The wallet refuses KNOT outputs on the live fork; `wallet knot`
  builds test-chain-only txs validated at height 100,000.
- **Snapshot coverage:** lightledger snapshots cover fork-created
  UTXOs only — the Bitcoin snapshot base (block 968698) is not built
  on this VM.
- **URUU anchor leg:** the lightledger anchor contract is not
  deployed (needs Lux's deployer key + gas); checkpoints carry
  `uruu.contract = null`. The wormhole burn/claim path (EXCAL ↔ URUU)
  is designed in the wallet but not executed — no burn, no claim,
  no invented URUU balance.
- **P2P seeds:** `seeds.json` is empty on this VM, so `ledger sync
  --via p2p` defaults to the local node at 127.0.0.1:9433; pass
  `--peer` for a real seed. The tunnel-proxy dial path is unproven.
- **Frostgate:** testnet-only. The vault controls no existing address
  (not the EXCAL miner key, not any BTC mainnet address). The
  coordinator is trusted for liveness; `frost-secp256k1-tr` was
  outside the NCC audit scope of the FROST core. Local rehearsal
  keeps all 5 operator files on one machine; production splits them
  across 5 operator machines.
- **PyInstaller one-file executables** (Windows/Linux/macOS via
  GitHub releases) are not built yet — the package is pure stdlib and
  ready for it, but no binary has been produced.
- **Derivation is HMAC-SHA512, not BIP32** (documented in
  `excalibur_wallet/keys.py`). Addresses are stable for this wallet
  but are not BIP32/BIP44 addresses and will not match other wallets.

## Tests

```sh
python3 test_excalibur_wallet.py
```

Unit tests run on a synthetic chain (fake funding UTXOs validated
through the real `validate_tx`); live tests run against the real
fork chain, the live node RPC, the live zkSync Era contract, and the
real Frostgate Rust binary. Live tests skip (reported, not passed)
when the live service is unreachable.
