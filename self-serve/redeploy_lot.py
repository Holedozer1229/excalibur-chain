#!/usr/bin/env python3
"""redeploy_lot.py — add Frostgate claim_threshold to a lot and re-deploy it.

Reads an existing lot JSON, queries the Frostgate vault for the group key
and threshold parameters, and writes the `claim_threshold` section into
the lot. Also adds `claim_seed_commitment` (SHA-256 of the claim seed)
so the taker can verify the seed was committed before funding.

Usage:
  python3 redeploy_lot.py --lot 1k [--output lots/1k.json]

Requires: the Frostgate ceremony directory (default: ~/workspace/aethergate/ceremony)
with a valid group.json file.
"""
import argparse
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "excalibur_wallet"))


def main():
    ap = argparse.ArgumentParser(
        description="Add Frostgate claim_threshold to a lot JSON and re-deploy.")
    ap.add_argument("--lot", required=True, help="Lot name (e.g. 1k, 1excal)")
    ap.add_argument("--output", default=None,
                    help="Output file (default: overwrite lots/<lot>.json)")
    ap.add_argument("--seed-hex", default=None,
                    help="Claim seed hex for commitment (optional)")
    args = ap.parse_args()

    # Load existing lot
    lot_file = os.path.join(HERE, "lots", args.lot + ".json")
    if not os.path.exists(lot_file):
        sys.exit(f"lot file not found: {lot_file}")
    with open(lot_file) as f:
        lot = json.load(f)

    # Query Frostgate vault status
    try:
        from frostgate import vault_status, DEFAULT_VAULT_DIR
        st = vault_status(DEFAULT_VAULT_DIR)
        group_key_hex = st["group_key"]
        if st["num_operators"] != 5 or st["threshold"] != 3:
            sys.exit(
                f"vault is {st['threshold']}-of-{st['num_operators']}; "
                f"refusing to deploy a lot against it (expected 3-of-5)")
        group_key_xonly = bytes.fromhex(group_key_hex)[-32:]  # strip 02/03 prefix if present
    except Exception as e:
        sys.exit(f"cannot query Frostgate vault: {e}")

    # Add claim_threshold to the lot
    lot["claim_threshold"] = {
        "k": 3,
        "n": 5,
        "group_key": group_key_hex,
        "federation": "aethergate/ceremony (repo Holedozer1229/aethergate)",
        "note": "BTC claim path requires any 3 of 5 operators; "
                "no single party can claim the taker's BTC"
    }

    # Add taker_refund_xonly placeholder (filled by taker at funding time)
    # — not needed in the lot, but documented for the spec
    lot.setdefault("btc_refund_height", None)

    # Add claim seed commitment if seed is provided
    if args.seed_hex:
        lot["claim_seed_commitment"] = hashlib.sha256(
            args.seed_hex.encode()).hexdigest()

    # Write output
    output = args.output or lot_file
    tmp = output + ".tmp"
    with open(tmp, "w") as f:
        json.dump(lot, f, indent=1)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, output)

    print(f"Lot {args.lot} updated with claim_threshold:")
    print(f"  group_key: {group_key_hex}")
    print(f"  threshold: 3-of-5")
    if args.seed_hex:
        print(f"  claim_seed_commitment: {lot['claim_seed_commitment']}")
    print(f"Written to: {output}")


if __name__ == "__main__":
    main()
