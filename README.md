# Aetherion-Excalibur

![Excalibur — the sword in the stone](docs/assets/hero.webp)

**Aetherion-Excalibur is the first hard fork to rebuild Bitcoin's locks from scratch: opcode-free and quantum-resistant.** The coin is **EXCAL**. Its block 0 is **Bitcoin block 968,698** — a live fork you can verify yourself in about two minutes with nothing but the files in this repo and a Python interpreter.

> Aetherion is a proof, not a promise. Glass box, not black box. Auditable AI.

**Live status, verified 2026-11-14:** fork tip **47,301**; the reference verifier walked all **47,302** headers from the anchor and passed in 144.4 s. Bitcoin tip 975,843. The solo miner is hashing at ~3.87M H/s in pool mode while the local Bitcoin node re-syncs.

> [Whitepaper (PDF)](https://holedozer1229.github.io/excalibur-chain/aetherion-excalibur-whitepaper.pdf) ·
> [Offer page](https://holedozer1229.github.io/excalibur-chain/) ·
> [ONE SHOT tracker](https://holedozer1229.github.io/excalibur-chain/oneshot.html) ·
> [Dr. Time record](https://holedozer1229.github.io/excalibur-chain/drtime.html) ·
> [Nostr](https://primal.net/p/npub17mnpcfdwfxh9ld2z4629jpne57pshdmlnfx03xwlam5j84nywhcqapnt6d)

## What EXCAL is

EXCAL is a Bitcoin hard fork — same proof-of-work, same 21-million-coin shape (50 EXCAL subsidy, halving every 210,000 blocks, 60-second spacing) — with the locking system rebuilt from scratch. Bitcoin's script opcodes are gone. In their place: small, hash-based locks. A coin is locked to a hash; it is spent by revealing a preimage or a hash-only signature. No elliptic curves in the spend path of the post-quantum locks, and no new opcodes to audit.

Denominations: whole coins are **EXCAL**; the smallest unit is the **sword** — 1 EXCAL = 100,000,000 swords. Testnet coins are tEXCAL.

The locks, live on-chain:

| Lock | Code | Since | What it is |
| --- | --- | --- | --- |
| PKH | `0x00` + hash160(pubkey) | height 102 | Pay to a public-key hash |
| OPEN | `0xff` | height 102 | Anyone-can-spend (coinbase uses this) |
| PQH | `0x02` + hash160(Trifold root) | height 25,212 | Post-quantum hash lock, spent by hash-only Trifold witnesses (~25 KB) |
| HTLC | `0x03` | height 36,010 | Hash-time-locked contract |
| QHTLC | `0x04` | height 40,040 | Quantum-resistant HTLC — the sale lots below use this |
| BRIDGE | `0x05` | height 39,200 | Bridge lock |
| KNOT | `0x06` | staged, **not activated** | Möbius torus-knot lock — built and tested 60/60, activation proposed at 100,000, proposal only |

## How an investor verifies every claim

Nothing here asks to be believed. Each claim has a check you can run:

1. **The chain is real and anchored to Bitcoin.** `python3 genealogy_verify.py` walks every header from the Bitcoin 968,698 anchor to the tip and checks every difficulty transition and every AuxPoW attachment. Latest run, 2026-11-14: **47,302 headers, ALL CHECKS PASS, 144.4 s.** Checkpoint: `genealogy_checkpoint.json`.
2. **The work is real.** Fork-native proof-of-work since the anchor: **1,910,560,442,042 hashes** (31,836 self-PoW blocks + 15,465 AuxPoW blocks, 18,304 accepted under the consensus grace rule) — replicated exactly by the verifier.
3. **The post-quantum locks are live, not promised.** The first PQH spend is on-chain (blocks 25,272 / 25,274). The Trifold lineage is on-chain too: fork block 25,344 carries a hash-only signature over the byte-exact Bitcoin genesis header; block 25,351 signs 25,344's header. The verifier re-checked both test vectors against the live chain on 2026-11-14: both match.
4. **The sale is funded on-chain.** The three lots below are locked on the fork — check the funding transactions in `self-serve/lots/`.
5. **The token is on-chain.** URUU lives on zkSync Era: contract [`0x5B6C9d85465Cc6FFe84039183872239657D90208`](https://explorer.zksync.io/address/0x5B6C9d85465Cc6FFe84039183872239657D90208), name "Camelot Excalibur URUU", total supply exactly **100,000,000** (verified against the Era RPC, 2026-11-14).
6. **The people are reachable.** Nostr: `npub17mnpcfdwfxh9ld2z4629jpne57pshdmlnfx03xwlam5j84nywhcqapnt6d` (12 notes; #12 is the Dr. Time announcement). Offer threads: issues [#2](https://github.com/Holedozer1229/excalibur-chain/issues/2), [#3](https://github.com/Holedozer1229/excalibur-chain/issues/3), [#4](https://github.com/Holedozer1229/excalibur-chain/issues/4).

## The first sale — 1 EXCAL = 1 BTC, funded on-chain

Three lots are locked on the fork right now. First funded HTLC wins; later fundings refund after the timeout. No DMs, no trust, just code.

| Lot | Locked | Fork block | Funding tx |
| --- | --- | --- | --- |
| 1 EXCAL = exactly 1 BTC | 1 EXCAL | 42,900 | `449fb35dafc7dc8f40faca892845730725961840b0fb945fa8b88b4e902287f1` |
| 1,000 EXCAL — you name the price | 1,000 EXCAL | 42,899 | `4873ebb3a40b83f2401266587aba9f73bf837dd51349e07029b06819fcccfc95` |
| 0.001 EXCAL pilot = 0.001 BTC | 0.001 EXCAL | 43,571 | `6ee1f5da1aaa83c0652603a3f2f07018603b8d1d32b7fda26edfa500b0e1c439` |

The locks are QHTLC — hash-based, quantum-resistant Trifold signatures, not ECDSA. The self-serve kit (`self-serve/`) builds your BTC HTLC funding transaction; the watcher verifies your funding and publishes your encrypted claim seed. The signal address is published on the [offer page](https://holedozer1229.github.io/excalibur-chain/).

## Architecture in plain words

- **Node** (`excalibur.py`, `genesis_fork.py`, `chainstate.py`, `node_rpc.py`, `p2p.py`): a pure-stdlib Python full node and JSON-RPC server — no pip dependencies, no build step. Serves the fork chain (RPC 9432, P2P 9433), plus mainnet/testnet modes.
- **Mining** (`fork_sniper.py`, `stratum_fork.py`, `grace_miner.py`, `btc_core6f.c`): merge-mined against Bitcoin (AuxPoW) plus native self-PoW. Difficulty is frozen inside each 60-block window and retargets exactly at window boundaries. `stratum_fork.py` is a stratum shim: point any standard SHA-256d stratum miner at it and you are mining EXCAL. A native Windows miner port is on master (`WINDOWS_MINER.md`, verified 349,321 H/s on a laptop, submit accepted).
- **Locks** (`txscript.py`, `trifold_lockbox.py`, `caduceus.py`): the opcode-free lockbox, the Trifold hash-only signature scheme (ternary Merkle tree, pattern-fold key schedule), and the 41-check Caduceus conformance suite.
- **Wallet** (`excalibur_wallet/`, 13 modules): a unified `excalibur` CLI — BIP-39 (12/24-word, AES-256-CTR+HMAC at rest), live-RPC ledger with chain-file fallback and verified light-ledger snapshots, send = build/sign/verify only (no broadcast path by design), PKH/OPEN/PQH/HTLC/QHTLC/BRIDGE locks, read-only URUU view. Test suite: 90 passed, 0 failed, 1 skipped (environmental). A Linux one-file binary is built (`build_wallet_exe.py`); the Windows `.exe` builds on a Windows machine (`build_exe.bat`).
- **Light ledger** (`lightledger.py`, `light-ledger/`): the fork's UTXO set as a snapshot committed by two sorted-Merkle roots (overlay + spent tombstones), with Trifold-signed checkpoints and a URUU bond on zkSync Era (1,000 URUU, 24 h fraud window). A real-chain test passed at tip 44,523 (44,414 overlay entries, 2,226,150 EXCAL; tamper test rejected; omission fraud proof proven against a tampered checkpoint, correctly failing against an honest one). The anchor and swap contracts compile clean. **Not deployed** — deployment needs the deployer key and ETH gas. Trust model, stated plainly: no trust in the auditor's key; what remains is zkSync consensus + contract code + at least one honest watcher in the window + the fraud verifier. Full replay is the only trust-free path.
- **Bitcoin solo mining** (ONE SHOT): one Bitcoin block template, one full sweep of all 4.29 billion nonces. If a hash lands below target, **3.125 BTC** goes to `bc1qnfd75mezay3xwqvxwv32z7sh248mwf6de67ce7`. The solo miner (v11) is live at ~3.87M H/s, 13.59B hashes this run, best 39 bits, 0 blocks — in pool mode while the local Bitcoin node re-syncs. Watch it live: [oneshot.html](https://holedozer1229.github.io/excalibur-chain/oneshot.html).

## Run a public SkyNet node

The Living Ledger is an explorer for each user's locally validating node, not a
centralized database. For an Ubuntu P2P seed and public explorer deployment,
including private RPC and TLS reverse-proxy setup, see
[`docs/SKYNET_NODE.md`](docs/SKYNET_NODE.md).

## Dr. Time — one countersignature, three chains

![Three chains, one countersignature](docs/assets/three-chains.webp)

A Trifold countersignature over the exact 80-byte header of Bitcoin's invalid overflow block 74,638 (root `7083fbeb…`, leaf 0) now lives on three chains at once:

- **Excalibur fork, block 43,750** — sealed, tag `OVERFLOW COUNTERSIGNED 7083fbeb - DR. TIME 2026-11-11`.
- **Excalibur fork, block 43,924** — sealed, tag `DRTIME ON 3 CHAINS - T4 8f81d522 efbe4a1b - 2026-11-12`.
- **Bitcoin testnet4** — two OP_RETURN transactions, `8f81d522…` and `efbe4a1b…`.
- **Bitcoin mainnet** — the same payloads are armed in the coinbase lottery for the next solo block this rig finds.

The Dr. Time key as a Taproot address (BIP-341, key-path-only): `bc1p4gssg6hrx323xvp6pddnd65aqvnfxc2nmzls7nc5fpgfqfuk67zqyq7vtk` (record: `dr-time-bip341.json`). Scope, stated plainly: this is an Excalibur-key countersignature only — not Satoshi signing, not proof of control of 1A1z, not a claim on the overflow coins. The overflow stays rejected. The arrangement is the point. Full record: [dr-time.html](https://holedozer1229.github.io/excalibur-chain/drtime.html).

The same BIP-341 construction applied to the public Bitcoin genesis key reproduces the recorded genesis Taproot address exactly: `bc1p9p9wftxmx25ehgltlfn2j8wmgxnm0gwjlm6p2wveytxc5pzgtspqhgrn93` (output key `284ae4ac…`). Public-key math only; it proves nothing about control of the genesis key.

## Messerene / pos28 — the genesis nonce, embedded

The Bitcoin genesis block nonce **2,083,236,893** (`0x7C2BAC1D`) sits at position 28 of the 32-byte Messerene pattern. Read as a scalar, the embedded pattern is a valid key whose pubkey is the SHA-256 preimage of two addresses at once — one key, two encodings:

- P2PKH (base58): `17GHncLkSxQYC5TdfuNxjkjmNb4ZaepawM`
- P2WPKH (bech32): `bc1qgj6srdszgygpltt2kc3eqva0alx9g48gj9fyj5`

Both are public by construction (the pattern and the nonce are public). A fingerprint, never a wallet — never fund either address. Verified numbers, including the correction of the first draft's wrong bytes, in [`pos28`](pos28).

## Golden Stone — one coin, one height

A single legendary coin at fork height **50,000** only, priced at 1 EXCAL for 1 BTC, under a height-50,000-only fusion-lock consensus patch. A 1 EXCAL lock transaction is already confirmed on the fork; the counterparty HTLC lock is unsigned and unbroadcast — the taker pubkey is still to be determined.

## Sponsor heights and powder lots

- **Sponsor No. 1 is unclaimed.** The first paying sponsor takes a permanent, one-of-one seat at the head of the ledger: `FIRST.md`.
- **Sponsored heights are open.** Pick a future block height, pay BTC with a self-describing OP_RETURN order, and the live payment watcher registers it after one confirmation. When the chain reaches that height, its coinbase pays your lock and seals your tag automatically. Ordinary heights: 21,000 sats; round heights (every 1,000th): 0.01 BTC. Terms and exact payment format: `SPONSOR.md`; live inventory: `HEIGHTS.md`.
- **Powder lots** crowdfund the finale: the Dr. Time broadcast trilogy is armed and waiting on funding. Buy a powder lot from ~1,200 sats: your own UTXO fires the act you choose, on autopilot, with a public proof chain. See [POWDER.md](POWDER.md).

## Phase Omega — the chain countersigns itself

Every block's coinbase carries a Trifold (hash-only, post-quantum) signature over its parent's header: block N countersigns block N−1, under published epoch roots (27 epochs). Verify the top of the chain yourself with `omega_verify.py`. Design, roots, and honest costs: [OMEGA.md](OMEGA.md).

**Status, stated honestly:** the last verified OMEGA1 push on the live chain is at height 43,610; pushes have been absent since (about 3,690 blocks at time of writing). The likely cause is a swallowed error in the signing path. The lineage blocks (25,344 / 25,351 / 43,750 / 43,924) never carried OMEGA1 pushes — the Dr. Time countersignature lives in another form, so the lineage is not broken. Diagnosis is pending.

## The raise

Aetherion-Excalibur is raising on a **$1.5M SAFE, $8M post-money cap, 20% discount** (terms confirmed 2026-10-18). The raise funds the chip tapeout, the oracle, and the first EXCAL sale to liquidity — the same work this repo already shows running. Talk to us: sphinxqasi@gmail.com, GitHub Issues on this repo, or on Nostr (link above). No returns are promised; EXCAL has no market and no price.

## The ecosystem

| Repo | What it is |
| --- | --- |
| [excalibur-chain](https://github.com/Holedozer1229/excalibur-chain) (this repo) | The fork: node, locks, wallet, sale, verifier |
| [aetherion-oracle-arcane](https://github.com/Holedozer1229/aetherion-oracle-arcane) | Aetherion Oracle — live site at [excaliburcrypto.com](https://www.excaliburcrypto.com), miner status, URUU |
| [excalibur-rpc-node](https://github.com/Holedozer1229/excalibur-rpc-node) | Excalibur node software v0.2.0 — full node, miner, JSON-RPC |
| [aether-proof](https://github.com/Holedozer1229/aether-proof) | The Aether Proof — a self-verifying cross-chain authorship capsule (`python3 verify_all.py`) |

## AetherionEXCAL Wallet — The Living Interface

**AetherionEXCAL.exe** (34.6 MB) is the unified single-file wallet — node, P2P, mining, governance, and GUI in one executable.

### Cinematic Experience

- **⚔ Quantum Genesis** — On first launch, an animated quantum field materializes the 13-word Prophecy one word at a time, then reveals the Taproot Treasury address derived from the Prophecy hash. Particles converge, bonds form, and the Realm awakens.
- **💎 Living Chain** — A real-time 3D visualization tab shows the blockchain as floating crystals in a quantum field. Each block is a rotating diamond connected by entanglement bonds, gently pulsing with the chain's heartbeat.
- **⚔ Knight's Oath Ceremony** — Swear allegiance to the Knights of the Round Table and receive your unique Genesis Knight NFT, saved locally with a ZK rarity proof.

### Full Feature Set

| Feature | Description |
| --- | --- |
| GUI Wallet | CustomTkinter dark theme with Aetherion Oracle aesthetics |
| Encryption | AES-256-GCM + scrypt KDF key storage |
| Local IPFS | Optional Kubo node; API and gateway bound to localhost, content pinning supported |
| Fork Node | Built-in RPC server (port 9432), auto-starts on launch |
| P2P Database | Persistent SQLite database — peers, txs, blocks survive restart |
| Bootstrap Server | Auto-discovery server (port 9435) — nodes find each other |
| UDP Multicast | LAN peer discovery — no hardcoded IPs needed |
| EREPR P2P | Quantum-inspired gossip protocol — entanglement bonds, no DHT |
| CPU Mining | Multi-threaded SHA-256d mining with thread control |
| GPU Mining | Stratum server for external GPU miners (T-Rex, GMiner, etc.) |
| Knights Governance | 3-of-5 MuSig2 (BIP-327) threshold signing |
| AI Oracle Knights | 5 specialized AI oracles analyze proposals |
| NFT Minting | 13 Knight NFTs with ZK rarity proofs |
| zkSync Bridge | Cross-chain EXCAL↔URUU bridge with bonding curve |
| Oracle Chat | Ask the Omniscient Sphinx anything |

### SkyNet P2P — Always-On Node Beacon

**Your node stays discoverable 24/7**, even when the wallet GUI is closed.

**`AetherionEXCAL-Beacon.exe`** (25.3 MB) is a standalone background service that:
- Runs the bootstrap discovery server (HTTP + UDP multicast/broadcast)
- Registers this machine with central SkyNet beacons
- Heartbeats every 60 seconds to stay alive
- Discovers and shares peers with other nodes
- Persists all P2P data in SQLite

The Windows installer includes an optional **Local IPFS Node** component. It
initializes a per-user Kubo repository with the API and gateway restricted to
localhost. Starting the daemon at sign-in is a separate, unchecked installer
task. See [`docs/SKYNET_NODE.md`](docs/SKYNET_NODE.md) for pinning and IPFS
availability guidance; IPFS serves pinned content, not the live node process.

**Three language implementations** — run any combination:

| Language | File | Build |
| --- | --- | --- |
| **Python** | `skynet_beacon.py` | `pyinstaller AetherionEXCAL-Beacon.spec` → `AetherionEXCAL-Beacon.exe` |
| **Node.js** | `skynet-p2p.js` | `npm install ws` → `node skynet-p2p.js` |
| **.NET 8** | `skynet-p2p.cs` | `dotnet build` → `dotnet run` |

**Auto-start on Windows:**
```powershell
# Double-click or run:
start-beacon.bat
# Or place in shell:startup for auto-start on login
```

**Auto-start on Mac:**
```bash
# Copy plist and load:
cp com.aetherion.skynet-beacon.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.aetherion.skynet-beacon.plist
```

**How SkyNet works:** When you launch the beacon on two machines, they automatically discover each other via UDP multicast (239.1.1.1:9436) and LAN broadcast (255.255.255.255:9437). Each beacon runs an HTTP REST API (port 9435) for peer discovery. No hardcoded IPs, no manual configuration — just launch and connect.

**Cross-network discovery:** Deploy the [SkyNet Cloudflare Worker beacon](skynet-beacon/) for always-on peer discovery across the internet. Free tier: 100K requests/day, $0/month.

### Run it

```
python3 genealogy_verify.py     # check the whole chain from the anchor
python3 window_planner.py       # current window: frozen bits, blocks
                                # left, exact expected cost per block
python3 grace_miner.py          # strategy validation + flood simulation
STRATUM_HOST=0.0.0.0 python3 stratum_fork.py   # serve GPU miners
dist\AetherionEXCAL.exe         # launch the unified wallet (Windows)
dist\AetherionEXCAL-Beacon.exe  # start the always-on SkyNet beacon
node skynet-p2p.js              # Node.js P2P node
dotnet run --project skynet-p2p.cs  # .NET P2P node
```

## Honest scope

EXCAL has no market and no price; this repo claims neither, and no return is promised. Trifold's security is hash-only — the novelty is the arrangement (ternary Merkle tree, pattern-fold key schedule), not a new hardness assumption, and it is unreviewed. The bridge design in `genealogy-bridge-spec.md` is a specification with a working reference verifier, not a deployed bridge. The light ledger is optimistic (trust-minimized), not trust-free. Phase Omega's countersigning is currently silent (see above). What is claimed is exactly what the verifier checks.
