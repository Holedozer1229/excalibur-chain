# vendor/ — verbatim copies of the Excalibur modules the taker scripts need

These files are copied byte-for-byte from the Excalibur workspace so a
taker can run `taker_claim.py` (and `deliver_seed.py`) from a plain
clone of this repo, with no other checkout:

- `txscript.py` — fork transaction serialization + validation + QHTLC
- `txpq.py` — Trifold witness encode/decode + verification
- `secp256k1.py` — pure-Python secp256k1 (signing, key derivation)
- `genesis_fork.py` — fork network constants (block 968698 anchor, etc.)
- `messerene_operator.py` — the public Messerene pattern constant
- `btc_htlc.py` — Bitcoin HTLC witness-script builder/parser (BIP143)
- `ripemd160_pure.py` — pure-Python RIPEMD-160 fallback for hash160

They contain no private keys, no secrets, and no seed material — only
public constants (hashes, roots, the public pattern) and code. The only
secret-hash values in here are hashes, never preimages. `trifold_lockbox.py`
(the Trifold key implementation) already lives at the repo root and is
imported from there, not from this directory.
