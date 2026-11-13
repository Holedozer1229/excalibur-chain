#!/usr/bin/env python3
"""sync.py — Sync vendor/ copies from the project root.

Run from the project root to update vendored modules:
    python self-serve/vendor/sync.py

Copies only files that exist in both the root and vendor/.
Skips files that are original to vendor/ (like btc_htlc.py).
"""
import os
import shutil

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)  # self-serve/
_PROJECT = os.path.dirname(_ROOT)  # project root

# Files to sync from project root to vendor/
SYNC_FILES = [
    "secp256k1.py",
    "txscript.py",
    "genesis_fork.py",
    "messerene_operator.py",
    "txpq.py",
]


def main():
    synced = []
    skipped = []
    for name in SYNC_FILES:
        src = os.path.join(_PROJECT, name)
        dst = os.path.join(_HERE, name)
        if not os.path.isfile(src):
            skipped.append((name, "not found in project root"))
            continue
        # Only copy if content differs
        with open(src, "r", encoding="utf-8") as f:
            src_content = f.read()
        if os.path.isfile(dst):
            with open(dst, "r", encoding="utf-8") as f:
                dst_content = f.read()
            if src_content == dst_content:
                skipped.append((name, "already up to date"))
                continue
        shutil.copy2(src, dst)
        synced.append(name)
        print(f"  synced: {name}")

    if not synced and skipped:
        print("All vendor files are already up to date.")
    elif synced:
        print(f"Synced {len(synced)} file(s) to vendor/.")
    if skipped:
        for name, reason in skipped:
            print(f"  skipped: {name} ({reason})")


if __name__ == "__main__":
    main()
