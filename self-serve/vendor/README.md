# Vendored Modules

This directory contains copies of modules from the project root, vendored for
offline use when the self-serve scripts run in an environment where the project
root is not on `sys.path`.

## Files

| File | Source | Used By |
|------|--------|---------|
| `btc_htlc.py` | Original (not in root) | `deliver_seed.py`, `claim_btc.py` |
| `secp256k1.py` | Root `secp256k1.py` | `btc_htlc.py`, `txscript.py` |
| `txscript.py` | Root `txscript.py` | `btc_htlc.py` |
| `genesis_fork.py` | Root `genesis_fork.py` | `txscript.py` |
| `messerene_operator.py` | Root `messerene_operator.py` | (standalone) |
| `txpq.py` | Root `txpq.py` | (standalone) |
| `ripemd160_pure.py` | Original (not in root) | `txscript.py` |

## Syncing

When modules in the project root are updated, sync them to vendor/ using:

```bash
# From the project root:
python self-serve/vendor/sync.py
```

Or manually copy changed files:

```bash
cp secp256k1.py self-serve/vendor/secp256k1.py
cp txscript.py self-serve/vendor/txscript.py
cp genesis_fork.py self-serve/vendor/genesis_fork.py
cp messerene_operator.py self-serve/vendor/messerene_operator.py
cp txpq.py self-serve/vendor/txpq.py
```

## Note on Duplication

The following code is duplicated between root and vendor/self-serve files:

- **secp256k1 arithmetic** (`_add`, `_mul`): 4 copies total
  - Root: `secp256k1.py`
  - Vendor: `self-serve/vendor/secp256k1.py`
  - Self-serve: `self-serve/taker_htlc.py` (inline copy)
  - Root: `messerene_operator.py` (inline copy)

- **Bech32 encoding** (`_polymod`, `_convertbits`): 3 copies total
  - `self-serve/taker_claim.py` (inline copy)
  - `self-serve/taker_htlc.py` (inline copy)
  - `messerene_operator.py` (inline copy)

These inline copies exist because the self-serve scripts are designed to run
independently of the project root. Consider consolidating them into a shared
utility module when the self-serve flow is stabilized.
