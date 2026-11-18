# Trifold code audit

## Scope

This is a source-level review of `trifold_lockbox.py`, the PQH/QHTLC
witness paths, the wallet leaf registry, and the node's block validation
and UTXO replay. It is not an independent cryptanalytic proof or a
third-party review.

## Construction

Trifold is a Lamport one-time signature at each leaf, with leaf public
keys committed by a ternary Merkle tree. The leaf secret is deterministically
derived from the seed, leaf index, and a public pattern constant. The
pattern adds no entropy or independent hardness assumption. This is a
custom parameterization of established hash-based components; describing
it as unrelated to Lamport or as a novel signature family is inaccurate.

For each bit of `SHA256(message)`, a signature reveals one of two
32-byte Lamport secrets. Verification hashes those secrets, reconstructs
the leaf commitment, and follows the Merkle path to the root. Reusing a
leaf on different messages reveals additional secret preimages. With
enough distinct messages, both choices become known for every bit and
the leaf can forge signatures for arbitrary digests. One reuse by itself
does not immediately reveal every secret. This is the standard stateful
OTS failure mode described for XMSS and LMS: signing different messages
with one OTS key can make forgeries computationally feasible, so state
must be advanced before a signature is exported ([RFC 8391, security
considerations](https://www.rfc-editor.org/rfc/rfc8391.html#section-1.1),
[NIST SP 800-208, Section 9.1](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-208.pdf)).

## Findings and changes

### Leaf reuse across consensus blocks — high

Previously, block validation could create a fresh spent-pair set per
block. The same `(root, index)` could therefore be accepted again in a
later block. The node now reconstructs the spent-pair set while validating
the full active-chain history and passes a copy into every candidate block
validation. Block validation without this state fails closed. The set is
committed only after a block has passed validation and been persisted.

Wallet PQH and QHTLC signing now atomically reserves `(root, index)` in a
cross-process locked registry before asking the key to emit a signature.
The key counter is also advanced under a process lock and persisted before
the signature is built. Missing, corrupt, or mismatched state fails
closed. Trifold signing without a persistent state path is refused.

### Concurrent wallet signing — medium

The old registry check-then-append could race across wallet processes.
`reserve()` now performs refresh, duplicate detection, and durable append
under one interprocess lock. Registry corruption is no longer silently
ignored. The Trifold counter has its own interprocess lock, and the Omega
allocator now advances its counter durably before deriving secrets, on
Windows as well as POSIX systems.

### Malformed signature handling — low

The raw verifier previously indexed caller-provided lists without checking
their shape and could raise on malformed objects. It now validates root,
index, tree height, path, and every Lamport element, returning `False` for
malformed inputs. The three-byte witness index only represents heights
up to 15 in a ternary tree; the verifier and codecs enforce that wire bound.
Key generation is capped at height 10 to bound its exponential CPU and
memory cost.
The wallet codec also retains strict witness-length and index bounds.

## Remaining design limits

- The on-chain PQH lock commits to a root with `HASH160`, which has a
  160-bit classical preimage target and roughly an 80-bit generic quantum
  preimage target. That is materially weaker than the 256-bit SHA-256
  commitments used inside the tree. Raising this bound requires a new lock
  format and consensus activation; it cannot be repaired by changing the
  off-chain signer alone. The quantum estimate is an inference from the
  160-bit output size and Grover's quadratic search bound ([Grover, 1996](https://arxiv.org/abs/quant-ph/9605043)).
- There is no formal reduction or peer-reviewed security proof for this
  exact KDF, serialization, and ternary-tree composition. The implemented
  assumptions are hash preimage/collision resistance and strict one-time
  leaf use.
- Local counters and registries can be rolled back together from a backup
  or cloned to another device. Consensus rejects reuse after a spend is
  included in the chain, but it cannot stop two disconnected copies from
  producing conflicting signatures before either spend is observed.
- The implementation's SHA-256 based key schedule does not gain entropy
  from the public pattern. Seed quality remains the caller's responsibility.

## UTXO integration

The fork genesis intentionally carries no Bitcoin transactions or balances.
The node builds its complete set from the fork's own transaction history.
It checks contiguous heights, parent links, header hashes, proof of work,
Merkle roots, coinbase lineage, transaction validity, and global Trifold
leaf use before enabling wallet balances or spending. Any invalid or
incomplete history leaves those RPCs disabled. Header-only P2P announcements
do not advance the validated active chain. Wallet responses include
immature confirmed outputs and label maturity and mempool-spend status;
transaction building selects only mature outputs that are not pending-spent.
