#!/usr/bin/env bash
# Excalibur bootstrap (Linux/macOS) — clone/update the repo, fetch the chain snapshot, verify it.
#   ./bootstrap.sh [install-dir]      (default: ~/excalibur-chain)
#   FORCE=1 ./bootstrap.sh            re-download the chain snapshot
#   SKIP_VERIFY=1 ./bootstrap.sh      skip the verification run
# Nothing is signed, spent, or broadcast. No keys are needed.
set -euo pipefail

REPO_URL="https://github.com/Holedozer1229/excalibur-chain.git"
RELEASE_LATEST="https://github.com/Holedozer1229/excalibur-chain/releases/latest/download/chain.jsonl.gz"
RELEASE_TAGGED="https://github.com/Holedozer1229/excalibur-chain/releases/download/chain-snapshot-2026-11-12/chain.jsonl.gz"

fail() { echo "BOOTSTRAP FAILED: $*" >&2; exit 1; }

echo "== Excalibur bootstrap =="
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -n "${1:-}" ]; then INSTALL_DIR="$1"
elif [ -d "$SCRIPT_DIR/.git" ]; then INSTALL_DIR="$SCRIPT_DIR"
else INSTALL_DIR="$HOME/excalibur-chain"; fi
echo "install dir: $INSTALL_DIR"

command -v git >/dev/null || fail "git not found — install it and re-run."

if [ -d "$INSTALL_DIR/.git" ]; then
  echo "repo present — pulling latest..."
  git -C "$INSTALL_DIR" pull --ff-only || echo "git pull failed (local changes?); continuing with the checkout as-is."
else
  echo "cloning $REPO_URL ..."
  git clone "$REPO_URL" "$INSTALL_DIR" || fail "git clone failed."
fi

PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null && "$c" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
    PY="$c"; break
  fi
done
[ -n "$PY" ] || fail "Python 3.10+ not found — install it and re-run."
echo "python: $PY ($("$PY" --version))"

CHAIN_GZ="$INSTALL_DIR/chain.jsonl.gz"
CHAIN_FILE="$INSTALL_DIR/chain.jsonl"
if [ -s "$CHAIN_FILE" ] && [ "${FORCE:-0}" != "1" ]; then
  echo "chain.jsonl already present — skipping download (FORCE=1 to re-fetch)."
else
  echo "downloading chain snapshot (several hundred MB; this takes a while)..."
  if ! curl -fL -o "$CHAIN_GZ" "$RELEASE_LATEST" 2>/dev/null; then
    echo "latest-release URL failed, trying tagged URL..."
    curl -fL -o "$CHAIN_GZ" "$RELEASE_TAGGED" || fail "could not download the chain snapshot."
  fi
  echo "decompressing..."
  "$PY" -c "import gzip, shutil; shutil.copyfileobj(gzip.open('$CHAIN_GZ','rb'), open('$CHAIN_FILE','wb'))"
fi
echo "chain file: $CHAIN_FILE ($(du -h "$CHAIN_FILE" | cut -f1))"

if [ "${SKIP_VERIFY:-0}" != "1" ]; then
  echo "verifying the chain from the anchor..."
  EXCAL_CHAIN_FILE="$CHAIN_FILE" EXCAL_CHECKPOINT_FILE="$INSTALL_DIR/genealogy_checkpoint.json" \
    "$PY" "$INSTALL_DIR/genealogy_verify.py"
fi

echo "BOOTSTRAP OK — repo at $INSTALL_DIR, chain verified."
echo "Re-run the verifier any time: $PY genealogy_verify.py"
