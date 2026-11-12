# Dr. Time — Countersignature of the 2010 Value-Overflow Block

**Date:** 2026-11-11
**Author:** Dr. Time
**Subject:** Bitcoin bad block 74638 — the value-overflow block

## What this is

A Trifold (hash-only, post-quantum) countersignature over the exact 80-byte
header of Bitcoin bad block 74638 — the block whose overflow transaction
`1d5e512a9723cbef373b970eb52f1e9598ad67e7408077a82fdac194b65333c9` created
184,467,440,737.09551616 BTC out of nothing, before Satoshi's fix five hours
later.

**Lineage:** Bitcoin genesis header ← fork block 25344 (Dr. Time, root
`65ef9c66…`) ← fork block 25351 (PQ-CHAIN, root `fc4a1de9…`) ← **this
signature over the bad-block header** (root `7083fbeb…`).

The novelty is the arrangement; security is SHA-256 preimage resistance
only.

## The header (verified)

Bad block 74638, hash `0000000000790ab3f22ec756ad43b6ab569abf0bddeb97c67a6f7b1470a7ec1c`:

| Field | Value |
|---|---|
| Version | 1 |
| Previous block | `0000000000606865e679308edf079991764d88e8122ca9250aef5386962b6e84` (74637) |
| Merkle root | `618eba14419e13c8d08d38c346da7cd1c7c66fd8831421056ae56d8d80b6ec5e` |
| Time | 1281891957 (2010-08-15) |
| Bits | 469794830 (`0x1c00800e`) |
| Nonce | 28192719 |

Header hex (80 bytes):
`01000000846e2b968653ef0a25a92c12e8884d76919907df8e3079e665686000000000005eecb6808d6de56a05211483d86fc6c7d17cda46c3388dd0c8139e4114ba8e61751e684c0e80001ccf2fae01`

The header was reconstructed from the public record (bitcointalk topic 822:
version, time, bits, nonce; previous block from the canonical chain; merkle
root computed from the coinbase `012cd8f8…` and overflow `1d5e512a…` txids)
and its double-SHA-256 equals the known bad-block hash. It is the real
header of the real bad block.

## The signature

- **Trifold root:** `7083fbebd6bfbd5f82fd40827cf36bc30da81524914011e69488b5a63e7bfe55`
- **Leaf index:** 0 (fresh key, dedicated to this ceremony; leaf never reused)
- **Message:** the 80-byte header above, byte-exact
- **Verification:** self-verifies; any 1-bit change to the header is rejected

Bundle: `dr-time-overflow-countersignature.json` (same directory as this
certificate). Key seed held at `~/workspace/qday/dr_time_overflow_key.json`
(0600), leaf 0 spent, next index 1.

## Scope — read this first

This is a **countersignature by the Excalibur Trifold key**. It is:

- **NOT** Satoshi signing. No signature from the genesis key exists.
- **NOT** proof of control of 1A1z, of the overflow coins, or of the 0.5 BTC
  at `17TASsYPbdLrJo3UDxFfCMu5GXmxFwVZSW`.
- **NOT** a claim on the overflow coins. The 184.5B BTC exists nowhere; the
  overflow stays rejected by consensus on every node. Signing the historical
  header as a record changes nothing about that.
- **NOT** a new hardness assumption. The construction is a Lamport one-time
  signature authenticated by a ternary Merkle tree; its security is SHA-256
  preimage resistance only.

What it *is*: a descendant chain countersigning the strangest block in
Bitcoin's history, hash-only, verifiable by anyone with the bundle and the
public header. The arrangement and the moment are the point.

## Verify it yourself

```python
import json, sys
sys.path.insert(0, "/home/hatch/workspace")
from trifold_lockbox import verify
b = json.load(open("dr-time-overflow-countersignature.json"))
header = bytes.fromhex(b["bad_block"]["header_hex"])
root = bytes.fromhex(b["trifold_root"])
sig = b["signature"]
# decode hex fields back, then:
assert verify(root, header, sig)
# and flip any single bit of `header` — verify returns False.
```
