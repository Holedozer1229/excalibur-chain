# Aetherion-Excalibur: A Bitcoin Hard Fork with Opcode-Free, Quantum-Resistant Locks

**Whitepaper v1.0 — 14 November 2026**

**Project:** Aetherion-Excalibur · **Asset:** EXCAL (native L1 coin)
**Author:** Travis Dale Jones (Lux), Founder
**Status:** Live chain. Every number in this paper was verified against the
live chain or a live public RPC on 14 November 2026, or is labelled as a
design statement. Nothing in this paper is simulated, demo, or testnet
presented as live. No return is promised; EXCAL has no market and no price.

> Aetherion is a proof, not a promise. Glass box, not black box. Auditable AI.

---

## 1. Abstract

Excalibur (EXCAL) is a Bitcoin hard fork that keeps Bitcoin's proof-of-work,
UTXO model, and 21-million-coin shape — and rebuilds the locking system from
scratch. Bitcoin's script opcodes are gone. In their place is a small set of
hash-based locks: a coin is locked to a hash and spent by revealing a preimage
or a hash-only signature. The post-quantum locks use no elliptic curves in
their spend path. The chain is live, the code is public, and every claim in
this paper can be checked by running the reference verifier in the public
repository — it walks every header from the Bitcoin anchor to the tip.

- Block 0 is the header of Bitcoin block 968,698 (public anchor).
- Chain height 47,306 at verification (14 November 2026).
- 50 EXCAL per block, halving every 210,000 blocks, 60-second spacing,
  maximum supply 21,000,000 EXCAL, no premine.
- Mined supply at height 47,306: 2,365,300 EXCAL.

## 2. The problem

### 2.1 Script opcodes are an attack surface

Bitcoin's locking language is a small stack machine with dozens of opcodes.
Every opcode is a rule an implementer must get exactly right, a consensus
edge case, and a potential vulnerability — and the set has only grown with
each soft fork. Exotic scripts (multisig, timelocks, hash locks, Taproot
branches) compose opcodes into programs whose behaviour is hard to audit
and harder to prove. The 2010 value-overflow incident and the long history
of script bugs show the same lesson: the more expressive the locking
language, the larger the surface for consensus failure.

Excalibur removes the language. There are no opcodes. There are six lock
types, each a fixed byte format: a type byte and a hash. Spending is
revealing the preimage, or a hash-only signature over the spend. The
consensus rules for a lock fit in a few lines, and the conformance suite
for the whole lockbox is 41 checks (see §8).

### 2.2 Quantum risk to ECDSA

Bitcoin's standard locks depend on the discrete logarithm problem on
secp256k1. A sufficiently powerful quantum computer running Shor's
algorithm breaks that assumption, and every coin locked to a revealed
public key becomes spendable by anyone with such a machine. The risk is
not imminent, but the migration is slow: coins must move to new locks
before the threat arrives, and the new locks must not depend on the same
assumption.

Excalibur's post-quantum locks (PQH, QHTLC) depend only on hash functions
(SHA-256, RIPEMD-160). Their security rests on preimage and collision
resistance — the same assumptions Bitcoin's own proof-of-work already
depends on — not on any elliptic-curve problem. The Trifold signature
scheme used to spend them is hash-only: a ternary Merkle tree with a
pattern-fold key schedule. Its novelty is arrangement, not a new hardness
assumption, and it is unreviewed (see §8.4).

## 3. Design: opcode-free locks

A lock is a fixed byte string: a one-byte type code followed by a hash.
There is no script to execute and no opcode to interpret.

| Lock | Code | Activated | Spend condition |
| --- | --- | --- | --- |
| PKH | `0x00` + hash160(pubkey) | height 102 | Signature from the key whose hash160 matches |
| OPEN | `0xff` | height 102 | Anyone-can-spend (coinbase outputs use this) |
| PQH | `0x02` + hash160(Trifold root) | height 25,212 (Q-Day) | Hash-only Trifold witness |
| HTLC | `0x03` | height 36,010 | Hash preimage or timeout refund |
| QHTLC | `0x04` | height 40,040 | Quantum-resistant HTLC (Trifold signatures) |
| BRIDGE | `0x05` | height 39,200 | Bridge lock |
| KNOT | `0x06` | staged, **not activated** | Möbius torus-knot lock (see §3.3) |

The first PQH spend is on-chain (fork blocks 25,272 / 25,274). The Trifold
lineage is on-chain: fork block 25,344 carries a hash-only signature over
the byte-exact Bitcoin genesis header, and block 25,351 signs 25,344's
header. Both test vectors were re-checked against the live chain on
14 November 2026 and match.

### 3.1 Trifold: hash-only signatures

A Trifold key is a ternary Merkle tree. Signing reveals a path of hashes;
verification recomputes the root. There is no elliptic curve anywhere in
the scheme. A PQH witness is ~25 KB — large by design, because it carries
the hash path, not because it carries a secret. The lockbox conformance
suite (CADUCEUS, 41 checks) and the Q-Day witness suite (31 checks) cover
the format, the canons, and relay validation against UTXO state.

### 3.2 What is still ECDSA

Honesty requires the boundary: PKH spends still use secp256k1 signatures,
and the chain's proof-of-work is SHA-256d. Only the PQH and QHTLC spend
paths are hash-only. A user who wants quantum resistance today uses PQH
locks; PKH remains available for ordinary use. The KNOT lock (§3.3) is
hash-based throughout.

### 3.3 KNOT lock (staged, not activated)

The KNOT lock (type `0x06`) is a hash-based, opcode-free lock built on a
Möbius (p, q) torus knot: the descriptor carries p, q, N (1–1000), an
epsilon, and H = SHA-256 of the knot point at t_star; spending reveals
t_star and the validator recomputes the point. Test results: 60/60
(verified by re-running `test_knot.py` on 14 November 2026). Activation is
proposed at height 100,000 — proposal only, not activated, and activation
requires a founder decision. No mempool policy exists yet for N=1000
(~0.1 s per input), and there is no refund or timeout path, by design.

## 4. Consensus

- **Proof-of-work:** Nakamoto PoW, SHA-256d, same as Bitcoin.
- **Block time:** 60 seconds (target spacing).
- **Difficulty:** frozen inside each 60-block window; retargets exactly at
  window boundaries.
- **Merge mining:** AuxPoW — blocks may be merge-mined against Bitcoin.
  A consensus grace rule accepts blocks whose difficulty bits fall inside
  a window under defined conditions (18,309 blocks accepted via the grace
  path as of height 47,306; the verifier reproduces the count exactly).
- **Block reward:** 50 EXCAL, halving every 210,000 blocks.
- **Maximum supply:** 21,000,000 EXCAL.
- **Premine:** none. Every EXCAL in existence was mined as a block reward.
- **Genesis:** block 0 is the header of Bitcoin block 968,698. The anchor
  is public; no private key is involved.
- **Denominations:** 1 EXCAL = 100,000,000 swords (smallest unit).
  Testnet coins are tEXCAL.

Chain state at verification (14 November 2026, reference verifier run):

- Headers walked from the anchor: **47,307** (heights 0–47,306).
- Verdict: **ALL CHECKS PASS**, in 152.8 seconds.
- Self-PoW blocks: 31,836. AuxPoW blocks: 15,470.
- Fork-native chainwork (excluding anchor): 1,910,748,125,707.
- Mined supply: 2,365,300 EXCAL.

## 5. Tokenomics and distribution

- **Max supply:** 21,000,000 EXCAL (50 × 210,000 × 2, the Bitcoin shape).
- **Issuance:** block rewards only. No premine, no ICO, no team allocation,
  no founder allocation, no airdrop.
- **Circulating (mined) supply at height 47,306:** 2,365,300 EXCAL.
- **Distribution — stated honestly:** mining is concentrated. A single
  sniper miner has sealed most blocks (11,676 blocks, 583,800 EXCAL, over
  its lifetime to date), so the majority of mined EXCAL is held by the
  founding mining operation. There is no public market, no CEX liquidity,
  and no trading pair yet.
- **First sale (funded on-chain, no taker yet):** three QHTLC lots are
  locked on the fork — 1,000 EXCAL (taker names the BTC price; fork block
  42,899), 1 EXCAL for exactly 1 BTC (fork block 42,900), and a 0.001 EXCAL
  pilot for 0.001 BTC (fork block 43,571). The signal address is published
  on the offer page. No sale has completed; no second holder exists yet.
- **No price:** EXCAL has no market and no price. This paper promises
  none, and no return is promised anywhere in the project.

## 6. Security model

What a reviewer can rely on, and what they cannot — stated plainly.

**Relied on:**

- Hash-function security (SHA-256, RIPEMD-160) for the post-quantum
  locks, the Trifold scheme, and proof-of-work.
- Bitcoin's proof-of-work security for the AuxPoW-merged portion of the
  chain and for the anchor itself.
- Public verifiability: the whole chain, the verifier, the wallet, and
  the lock code are public; any claim in this paper can be re-run.

**Not relied on, and not claimed:**

- No third-party security audit exists. The code is self-tested (see §8).
  A third-party audit is the project's top outstanding security item.
- Trifold's security is hash-only by construction; its novelty is
  arrangement (ternary Merkle tree, pattern-fold key schedule), not a new
  hardness assumption. It is unreviewed by any outside party.
- The chain is small and single-implementer. There is no second
  implementation of the node.
- Phase Omega — the design under which every block's coinbase carries a
  Trifold signature over its parent's header — is currently silent: the
  last verified OMEGA1 push is at height 43,610, absent for roughly
  3,690 blocks at the time of writing. The likely cause is a swallowed
  error in the signing path; diagnosis is pending. The Dr. Time
  countersignature lineage (blocks 25,344 / 25,351 / 43,750 / 43,924)
  never carried OMEGA1 pushes, so the lineage is not broken by this.
- The bridge design is a specification with a working reference verifier,
  not a deployed bridge.
- The light ledger is optimistic (trust-minimized), not trust-free; see §7.

## 7. Wallet and light ledger

**Wallet.** The unified `excalibur` CLI wallet (13 modules): BIP-39
(12/24-word, AES-256-CTR+HMAC at rest), Shamir k-of-n, live-RPC ledger
with chain-file fallback and verified light-ledger snapshots. Send is
build/sign/verify only — there is no broadcast path by design; a
transaction is verified locally before it is submitted. It supports
PKH/OPEN/PQH/HTLC/QHTLC/BRIDGE locks and a read-only URUU view. A Linux
one-file binary is built; the Windows `.exe` builds on a Windows machine.
Test results are in §8.

**Light ledger.** The fork's UTXO set as a snapshot committed by two
sorted-Merkle roots (overlay + spent tombstones), with Trifold-signed
checkpoints and a URUU bond on zkSync Era (1,000 URUU, 24-hour fraud
window). A real-chain test passed at tip 44,523 (44,414 overlay entries,
2,226,150 EXCAL; tamper test rejected; an omission fraud proof was proven
against a tampered checkpoint and correctly failed against an honest one).
The anchor and swap contracts compile clean. **Not deployed** — deployment
needs the deployer key and ETH gas. Trust model, stated plainly: no trust
in the auditor's key; what remains is zkSync consensus, the contract code,
at least one honest watcher in the window, and the fraud verifier. Full
replay is the only trust-free path.

## 8. Testing and audit readiness

All suites below were re-run by the authors on 14 November 2026 against
the live chain or the current code. Exact commands and full outputs are in
the accompanying Audit-Readiness Dossier.

| Suite | Result | What it covers |
| --- | --- | --- |
| Genealogy reference verifier | ALL CHECKS PASS — 47,307 headers, 152.8 s | Every header from the BTC-968698 anchor, difficulty transitions, AuxPoW, lineage test vectors 25,344 / 25,351 |
| Q-Day / Lockbox (`test_qlock.py`) | 31 checks passed | Opcode-free locks, BIP-369 no-RBF mempool, activation 102 |
| CADUCEUS (`test_caduceus.py`) | 41 checks passed | Capsule format, four canons, relay validation vs UTXO state |
| KNOT (`test_knot.py`) | 60 passed | Torus-knot lock math, inversion, timing (N=1000 in 0.014 s) |
| BIP-340 | 19/19 official test vectors, both implementations, cross-check identical | Schnorr sign/verify (both BIP-340 implementations in the repo) |
| Wallet crypto (`test_wallet_crypto.py`) | 18 checks green | AES-256 known-answer vectors, CTR mode, wallet encrypt/decrypt |
| Wallet RPC (`test_wallet_rpc.py`) | 30 checks green | sendtoaddress, fee estimation, mempool pressure |
| Wallet suite (`test_excalibur_wallet.py`) | 90 passed, 0 failed, 1 skipped | Unified CLI wallet (see dossier for the re-run) |

**Not covered — stated plainly:** no third-party audit exists. There is no
external review of the consensus code, the Trifold scheme, the wallet, or
the contracts. The suites above are self-tests written by the authors.

One reproduction note, recorded for reviewers: `test_caduceus.py` fails to
import when run from the workspace root because a directory named
`caduceus/` shadows the module `caduceus.py`. The 41 checks pass when run
from an isolated directory containing only the two files. The collision is
a test-harness defect, not a code defect, and it is fixed by renaming one
of the two — a change reserved for the authors.

## 9. URUU — the Layer 2 token (a separate asset)

URUU is a separate asset from EXCAL and must not be confused with it.
URUU lives on zkSync Era (chain 324), contract
`0x5B6C9d85465Cc6FFe84039183872239657D90208`, name "Camelot Excalibur
URUU", 18 decimals, total supply exactly **100,000,000**, verified live
against the Era RPC on 14 November 2026. URUU is the Layer 2 asset of the
Aetherion-Excalibur system and the bond asset of the light ledger. This
paper covers EXCAL; URUU's own documentation is in the project repository.

## 10. Team

- **Travis Dale Jones (Lux)** — Founder, Blanco, Texas. Designed the
  fork, the lockbox, Trifold, and the mining operation.
- Development is public on GitHub under Holedozer1229. There is no
  anonymous team member and no advisor list to disclose.

## 11. Roadmap

Stated as intentions, not promises. Items requiring a founder decision or
funding are marked as such.

1. **Third-party security audit** — to be commissioned; the top
   outstanding item. No auditor is engaged yet.
2. **Omega diagnosis** — find and fix the swallowed error silencing the
   per-block countersignatures (last push 43,610).
3. **KNOT activation** — proposed at height 100,000. Proposal only;
   activation requires a founder decision, plus mempool policy for N=1000.
4. **Light-ledger deployment** — needs the deployer key and ETH gas.
5. **First sale completion** — the three funded lots await a taker.
6. **Exchange listings** — Coinbase Asset Hub application in preparation
   (November 2026). No listing is promised or agreed.
7. **Chip tapeout and oracle** — funded by the concurrent $1.5M SAFE
   raise ($8M post-money cap, 20% discount; terms confirmed 18 October
   2026). The raise is a separate securities matter and is not part of
   this listing application.

## 12. Links and how to verify

- Chain + offer page: https://holedozer1229.github.io/excalibur-chain/
- Source (fork): https://github.com/Holedozer1229/excalibur-chain
- Node software: https://github.com/Holedozer1229/excalibur-rpc-node
- Oracle / live miner status: https://aetherion-oracle.com
- Nostr: npub17mnpcfdwfxh9ld2z4629jpne57pshdmlnfx03xwlam5j84nywhcqapnt6d
- URUU contract: https://explorer.zksync.io/address/0x5B6C9d85465Cc6FFe84039183872239657D90208

Verify the chain yourself (about three minutes, Python 3 only):

```
git clone https://github.com/Holedozer1229/excalibur-chain
cd excalibur-chain
python3 genealogy_verify.py
```

The verifier walks every header from the Bitcoin 968,698 anchor to the
tip and checks every difficulty transition, every AuxPoW attachment, and
both lineage test vectors. On 14 November 2026 it reported ALL CHECKS
PASS over 47,307 headers in 152.8 seconds. The anchor cross-check against
a public Bitcoin node requires network access to a Bitcoin RPC; where
unavailable, the verifier enforces internal consistency and prints the
anchor's display hash for manual comparison:
`000000000000000000015d0478e7b60044314fb055fbb306ac7371ef89b60496`.

## 13. Honest scope

EXCAL has no market and no price; this paper claims neither, and no return
is promised. Trifold's security is hash-only and unreviewed. The bridge is
a specification, not a deployment. The light ledger is optimistic, not
trust-free. Phase Omega is currently silent. What is claimed is exactly
what the verifier checks. If a claim in this paper cannot be verified from
the public repository and the live chain, it should not be believed — and
the authors invite the reader to say so.

---

*Aetherion-Excalibur Whitepaper v1.0, 14 November 2026. Numbers verified
live on the day shown: fork tip 47,306; mined supply 2,365,300 EXCAL;
URUU totalSupply 100,000,000 (zkSync Era RPC). Test results re-run by the
authors on the same day; see the accompanying Audit-Readiness Dossier for
exact commands and outputs.*
