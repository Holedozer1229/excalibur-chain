# EXCALIBUR — the fork you can check

![Excalibur — the sword in the stone](docs/assets/hero.webp)

EXCAL is a live Bitcoin fork whose block 0 is **Bitcoin block 968,698**.
It does not ask to be believed. Everything below is a measurement you
can re-run.

**Live status, verified 2026-11-14:** tip height **47,233**; the reference
verifier walked all **47,234** headers from the anchor and passed in 73.8 s.

> [Offer page](https://holedozer1229.github.io/excalibur-chain/) ·
> [ONE SHOT tracker](https://holedozer1229.github.io/excalibur-chain/oneshot.html) ·
> [Dr. Time record](https://holedozer1229.github.io/excalibur-chain/drtime.html)

## What's actually here

- **A living chain.** 47,234 blocks past the anchor, responsive DAA
  (60-block window, 60-second spacing, 4× clamp), deep-reorg guard.
  Fork-native proof-of-work since the anchor: **1,907,246,761,912 hashes**
  (31,836 self-PoW blocks + 15,397 AuxPoW blocks, 18,237 of them accepted
  under the consensus grace rule — all replicated exactly by the verifier).
- **Post-quantum locks, live, not promised.** Since height 25,212 the
  chain enforces PQH locks — `0x02 ‖ hash160(Trifold root)` — spent by
  hash-only Trifold witnesses (~25 KB). No elliptic curves in the spend
  path. The first PQH spend is on-chain (blocks 25,272 / 25,274). The
  opcode-free Lockbox (activation 102) gives PKH (`0x00 ‖ hash160`) and
  OPEN (`0xff`) locks; no new bare P2PK after activation.
- **A countersigned lineage.** Fork block 25,344 carries a Trifold
  (hash-only) signature over the byte-exact Bitcoin genesis header;
  block 25,351 signs block 25,344's header. Every link verifies with
  nothing but SHA-256. The verifier re-checked both test vectors
  against the live chain on 2026-11-14: both match.
- **Mine it with any GPU.** `stratum_fork.py` is a stratum shim in
  front of the node RPC: point a standard SHA-256d stratum miner at
  it and you are mining EXCAL, paid to the node wallet. Templates
  follow the chain's window strategy — difficulty is frozen inside
  each 60-block window and retargets exactly at window boundaries,
  so mid-window block cost is a known constant. A native Windows
  miner port is merged on master (`WINDOWS_MINER.md`, verified
  349,321 H/s on a laptop, submit accepted).
- **Verify it in seconds.** `genealogy_verify.py` is a stdlib-only
  reference verifier: it walks the chain from the Bitcoin anchor and
  checks every header, every AuxPoW attachment, and every difficulty
  transition. Latest verified checkpoint: height 47,233
  (`genealogy_checkpoint.json`, written by the run itself).

## The first sale — 1 EXCAL = 1 BTC, funded on-chain

Three lots are locked on the fork right now. First funded HTLC wins;
later fundings refund after the timeout. No DMs, no trust, just code.

| Lot | Locked | Fork block | Funding tx |
| --- | --- | --- | --- |
| 1 EXCAL = exactly 1 BTC | 1 EXCAL | 42,900 | `449fb35d…` |
| 1,000 EXCAL — you name the price | 1,000 EXCAL | 42,899 | `4873ebb3…` |
| 0.001 EXCAL pilot = 0.001 BTC | 0.001 EXCAL | 43,571 | `6ee1f5da…` |

The locks are QHTLC — hash-based, quantum-resistant Trifold
signatures, not ECDSA. The self-serve kit (`self-serve/`) builds your
BTC HTLC funding transaction; the watcher verifies your funding and
publishes your encrypted claim seed. Offer threads: issues
[#2](https://github.com/Holedozer1229/excalibur-chain/issues/2),
[#3](https://github.com/Holedozer1229/excalibur-chain/issues/3),
[#4](https://github.com/Holedozer1229/excalibur-chain/issues/4).

## Dr. Time — one countersignature, three chains

![Three chains, one countersignature](docs/assets/three-chains.webp)

A Trifold countersignature over the exact 80-byte header of Bitcoin's
invalid overflow block 74,638 (root `7083fbeb…`, leaf 0) now lives on
three chains at once:

- **Excalibur fork, block 43,750** — sealed, tag
  `OVERFLOW COUNTERSIGNED 7083fbeb - DR. TIME 2026-11-11`.
- **Excalibur fork, block 43,924** — sealed, tag
  `DRTIME ON 3 CHAINS - T4 8f81d522 efbe4a1b - 2026-11-12`.
- **Bitcoin testnet4** — two OP_RETURN transactions,
  `8f81d522…` and `efbe4a1b…`.
- **Bitcoin mainnet** — the same payloads are armed in the coinbase
  lottery for the next solo block this rig finds.

The Dr. Time key as a Taproot address (BIP-341, key-path-only):
`bc1p4gssg6hrx323xvp6pddnd65aqvnfxc2nmzls7nc5fpgfqfuk67zqyq7vtk`
(record: `dr-time-bip341.json`). Scope, stated plainly: this is an
Excalibur-key countersignature only — not Satoshi signing, not proof of
control of 1A1z, not a claim on the overflow coins. The overflow stays
rejected. The arrangement is the point. Full record:
[dr-time.html](https://holedozer1229.github.io/excalibur-chain/drtime.html).

The same BIP-341 construction applied to the public Bitcoin genesis
key reproduces the recorded genesis Taproot address exactly:
`bc1p9p9wftxmx25ehgltlfn2j8wmgxnm0gwjlm6p2wveytxc5pzgtspqhgrn93`
(output key `284ae4ac…`). Public-key math only; it proves nothing about
control of the genesis key.

## Messerene / pos28 — the genesis nonce, embedded

The Bitcoin genesis block nonce **2,083,236,893** (`0x7C2BAC1D`,
little-endian bytes `1D AC 2B 7C`) sits at position 28 of the 32-byte
Messerene pattern (`…B3C5D7E9` → `…1DAC2B7C`). Read as a scalar, the
embedded pattern is a valid key whose pubkey is the SHA-256 preimage
of two addresses at once — one key, two encodings:

- P2PKH (base58): `17GHncLkSxQYC5TdfuNxjkjmNb4ZaepawM`
- P2WPKH (bech32): `bc1qgj6srdszgygpltt2kc3eqva0alx9g48gj9fyj5`

Both are public by construction (the pattern and the nonce are public).
A fingerprint, never a wallet — never fund either address. Verified
numbers, including the correction of the first draft's wrong bytes, in
[`pos28`](pos28).

## Burn addresses — 9,020 sats that can never move

BIP-350 (bech32m, witness v1) re-encodings of the f-pattern and
all-zero programs (`btc-burn-bip350.json`):

| Program | v1 address |
| --- | --- |
| f-pattern, 20 bytes | `bc1pffffffffffffffffffffffffffffffffeg49x6` |
| f-pattern, 32 bytes | `bc1pfffffffffffffffffffffffffffffffffffffffffffffffffffqnf0wwz` |
| all-zero, 20 bytes | `bc1pqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqmmente` |
| all-zero, 32 bytes | `bc1pqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqpqqenm` |

Neither 32-byte program is a valid curve point (`lift_x` returns
nothing in two independent implementations), so neither is a Taproot
key at all — key-path spend is impossible at the consensus level, not
merely a missing-key problem. A spend was attempted on every angle
(`zero_spend_hunt.py`): key-path, script-path, quantum, miner
collusion — all fail with evidence. The surprise: the all-zero
32-byte address **holds 9,020 sats in 12 confirmed UTXOs, 0 ever
spent** (verified by both mempool.space and BlockCypher). Real burned
coins, provably unspendable because x = 0 is not on secp256k1. The
only theoretical path is a consensus-rule change — a fork of Bitcoin,
not a spend on it.

## ONE SHOT — winner takes all

One Bitcoin block template, one full sweep of all 4.29 billion nonces.
If a hash lands below target, **3.125 BTC** goes to
`bc1qnfd75mezay3xwqvxwv32z7sh248mwf6de67ce7`. Watch it live:
[oneshot.html](https://holedozer1229.github.io/excalibur-chain/oneshot.html).

## The wallet

A unified `excalibur` CLI (`excalibur_wallet/`, 13 modules): BIP-39
(12/24-word, AES-256-CTR+HMAC at rest), live-RPC ledger with
chain-file fallback and verified light-ledger snapshots, send =
build/sign/verify only (no broadcast path by design), PKH/OPEN/PQH/
HTLC/QHTLC/BRIDGE locks (KNOT refused on the live fork — staged, not
activated), read-only URUU view, and Frostgate 3-of-5 FROST via a real
Aethergate Rust binary. Test suite: 90 passed, 0 failed, 1 skipped
(the skip is environmental). A Linux one-file binary is built
(`build_wallet_exe.py`); the Windows `.exe` must be built on a
Windows machine (`build_exe.bat`).

## Light ledger — trust-minimized, not trust-free

`lightledger.py` exports the fork's UTXO set as a snapshot committed
by two sorted-Merkle roots (overlay + spent tombstones), with
Trifold-signed checkpoints and a URUU bond on zkSync Era
(1,000 URUU, 24 h fraud window). A real-chain test passed at tip
44,523 (44,414 overlay entries, 2,226,150 EXCAL; tamper test rejected;
omission fraud proof proven against a tampered checkpoint, correctly
failing against an honest one). The anchor and swap contracts compile
clean (`light-ledger/`). **Not deployed** — deployment needs the
deployer key and ETH gas. Trust model, stated plainly: no trust in the
auditor's key; what remains is zkSync consensus + contract code + at
least one honest watcher in the window + the fraud verifier. Full
replay is the only trust-free path.

## Golden Stone — one coin, one height

A single legendary coin at fork height **50,000** only, priced at
1 EXCAL for 1 BTC, under a height-50,000-only fusion-lock consensus
patch. A 1 EXCAL lock transaction is already confirmed on the fork;
the counterparty HTLC lock is unsigned and unbroadcast — the taker
pubkey is still to be determined.

## KNOT lock — built, tested, staged, not activated

Lock `0x06`, hash-based and opcode-free: a Möbius (p, q) torus-knot
descriptor; the spend reveals `t_star` and the validator recomputes
the knot point. Tests 60/60, regressions green. Proposed activation
100,000 is a **proposal only** — it needs the go-ahead, and nothing
has been broadcast or mined.

## Sponsor heights and powder lots

- **Sponsor No. 1 is unclaimed.** The first paying sponsor takes a
  permanent, one-of-one seat at the head of the ledger: `FIRST.md`.
- **Sponsored heights are open.** Pick a future block height, pay
  BTC with a self-describing OP_RETURN order, and the live payment
  watcher registers it after one confirmation. When the chain
  reaches that height, its coinbase pays your lock and seals your
  tag automatically. Terms and exact payment format: `SPONSOR.md`;
  the upcoming ~600-block GPU flood inventory: `FLOOD.md`.
- **Powder lots** crowdfund the finale: the Dr. Time broadcast
  trilogy (AETHER/v2, the 1A1z tribute, the QDAY countersignature)
  is armed and waiting on funding. Buy a powder lot from ~1,200
  sats: your own UTXO fires the act you choose, on autopilot, with
  a public proof chain. See [POWDER.md](POWDER.md).

## Phase Omega — the chain countersigns itself

Every block's coinbase carries a Trifold (hash-only, post-quantum)
signature over its parent's header: block N countersigns block N−1,
under published epoch roots. Verify the top of the chain yourself with
`omega_verify.py`. Design, roots, and honest costs: [OMEGA.md](OMEGA.md).

**Status, stated honestly:** the last verified OMEGA1 push on the live
chain is at height 43,610; pushes have been absent since (about 958
blocks at last count). The likely cause is a swallowed error in the
signing path. The lineage blocks (25,344 / 25,351 / 43,750 / 43,924)
never carried OMEGA1 pushes — the Dr. Time countersignature lives in
another form, so the lineage is not broken. Diagnosis is pending.

## Run it

```
python3 genealogy_verify.py     # check the whole chain from the anchor
python3 window_planner.py       # current window: frozen bits, blocks
                                # left, exact expected cost per block
python3 grace_miner.py          # strategy validation + flood simulation
STRATUM_HOST=0.0.0.0 python3 stratum_fork.py   # serve GPU miners
```

## Honest scope

EXCAL has no market and no price; this repo claims neither. Trifold's
security is hash-only — the novelty is the arrangement (ternary Merkle
tree, pattern-fold key schedule), not a new hardness assumption, and it
is unreviewed. The bridge design in `genealogy-bridge-spec.md` is a
specification with a working reference verifier, not a deployed bridge.
The light ledger is optimistic (trust-minimized), not trust-free.
What is claimed is exactly what the verifier checks.
