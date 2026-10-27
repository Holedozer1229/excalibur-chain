# Phase Omega — the chain countersigns itself

**Live since 2026-10-23, from fork height 25,901.**

Every block produced by this chain's standing producers — the
merge-mining sniper, the built-in CPU miners, and the stratum shim any
GPU miner connects to — carries one extra coinbase push:

```
push( "OMEGA1" || epoch:uint16 || Trifold signature )
```

The signature is over the **parent block's raw 80-byte header**. Block
N's coinbase therefore countersigns block N−1, and a chain of
post-quantum, hash-only signatures runs unbroken alongside the chain
of hashes. Rewrite history and you must forge not only the work but
a one-time signature whose leaf was spent exactly once, in order,
under a published Merkle root.

## The signature scheme

Trifold (see `trifold_lockbox.py`): a Lamport-style one-time
signature whose 729 leaves hang in a *ternary* Merkle tree, with leaf
keys derived through a pattern-fold schedule. Security rests on
SHA-256 alone — no elliptic curves, nothing for a quantum computer
to bite. Each signature is 24,964 bytes; the blob with its header is
24,972.

Leaf discipline is the whole security model, and it is mechanical:
indices are allocated under a lock by `omega_sign.py` alone, the
spent leaf is persisted *before* the signature is released, templates
competing for the same parent share one cached signature instead of
burning two leaves, and epochs rotate at leaf 720 of 729. Epoch
roots are public:

| Epoch | Root | From height |
|---|---|---|
| 1 | `1128e5657397a91bb9ab36f13432099dbf6f1a974156ba3b004cb0c63b468f0e` | 25,901 |
| 2 | `8c4969b186388069d286b1fc96c977f8580928d784d91b877d16ab20afcf6a22` | 26,557 |
| 3 | `715773d10a94da6e229cf3c4cee8e5fedc3db250bfbaf5c9bb646d88e87d9af4` | 27,197 |
| 4 | `193a435ab15e4a2fe5a3ce2c2125fdb09365024768221657801de20244523b78` | 27,836 |
| 5 | `32bfd3acc6eec75387fb62f7596a4b400fdf641c4501caa80cfd79cdc38d0e48` | 28,464 |
| 6 | `78c8f10c83d5607f2cc69e569f5c49b9aea31c8a69ef1451c529e208ddc506e7` | 29,100 |
| 7 | `65b7d609b3ecdf5858022f0180305cba63f8b133dcd734a3d7203777cc91e355` | 29,746 |

The machine-readable ledger is `omega_epochs.json`.

## Verify it yourself

```
python3 omega_verify.py 10     # checks the top 10 canonical blocks
```

It walks the chain from the node tip, pulls each coinbase's Omega
blob, reconstructs the parent header, and verifies the signature
against the epoch root. First results on the live chain:

```
h25904 [auxpow] OMEGA epoch 1 leaf 4 — signature VERIFIES
h25903 [auxpow] OMEGA epoch 1 leaf 3 — signature VERIFIES
h25902 [auxpow] OMEGA epoch 1 leaf 2 — signature VERIFIES
h25901 [pow]    OMEGA epoch 1 leaf 0 — signature VERIFIES
```

## Honest costs and scope

- **Size.** Blocks grow by ~25 KB each (≈50 KB hex in the chain
  file). At the current ~1,200 blocks/day that is real growth —
  the price of carrying full one-time signatures in-band. A future
  epoch format could carry a commitment instead; this one chose
  self-contained verifiability.
- **Coverage.** Blocks from the standing producers are signed.
  Nothing forces an outside miner to sign; an unsigned block is
  still a valid block. Omega is a property of this chain's
  production, not (yet) a consensus rule.
- **A consensus parser fix shipped with it.** The coinbase lineage
  check originally read the scriptSig length as a single byte,
  silently mis-parsing any script of 253+ bytes. It now decodes the
  varint properly — byte-identical verdicts on every historical
  block (the full genealogy verifier passes: 25,905 headers), and
  long coinbases parse as they should.
- **Novelty, scoped.** The arrangement — a proof-of-work chain
  whose every block post-quantum-countersigns its parent — is, to
  our knowledge, unheard of. The primitives (hash-based one-time
  signatures, Merkle trees) are classical and borrowed; no new
  hardness assumption is claimed.
