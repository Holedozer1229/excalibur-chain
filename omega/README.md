# Omega — Epoch Verification

**Omega epoch data for AetherionEXCAL chain verification.**

This directory contains epoch checkpoint data used for verifying the AetherionEXCAL chain state at specific block heights.

## Files

| File | Description |
|------|-------------|
| `epochs.json` | Epoch checkpoint data with block heights, hashes, and verification metadata |

## Usage

Epoch data is used by `omega_sign.py` and `omega_verify.py` to sign and verify chain state at epoch boundaries.

```bash
# Sign an epoch checkpoint
python omega_sign.py

# Verify an epoch checkpoint
python omega_verify.py
```

## License

MIT License — see [LICENSE](../LICENSE) for details.
