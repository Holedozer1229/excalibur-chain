#!/usr/bin/env bash
# Start an EXCAL fork full node that accepts community P2P connections.
# RPC deliberately stays bound to loopback and is never published by this script.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
exec python3 "$SCRIPT_DIR/excalibur.py" \
  --network fork \
  --p2p-host "${EXCAL_P2P_HOST:-0.0.0.0}" \
  --p2p-port "${EXCAL_P2P_PORT:-9433}" \
  --rpc-host 127.0.0.1 \
  --rpc-port "${EXCAL_RPC_PORT:-9432}" \
  --no-mine "$@"
