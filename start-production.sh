#!/bin/bash
# AetherionEXCAL P2P Stack - Production Startup Script
# Starts: fork_node (RPC), P2P layer with EREPR, stratum server, and Camelot Game API
#
# Environment variables:
#   EXCAL_WORKSPACE - path to chain.jsonl
#   FORK_RPC_PORT   - RPC port (default: 9432)
#   FORK_RPC_HOST   - RPC bind host (default: 0.0.0.0)
#   STRATUM_HOST    - Stratum bind host (default: 0.0.0.0)
#   STRATUM_PORT    - Stratum port (default: 9434)
#   GAME_API_PORT   - Game API port (default: 9436)

set -e

echo "========================================"
echo "  ⚔️ AetherionEXCAL P2P Stack - Production"
echo "  Version: 2.0.0"
echo "========================================"
echo

# Set default environment variables
export EXCAL_WORKSPACE="${EXCAL_WORKSPACE:-$(dirname "$0")}"
export FORK_RPC_PORT="${FORK_RPC_PORT:-9432}"
export FORK_RPC_HOST="${FORK_RPC_HOST:-0.0.0.0}"
export STRATUM_HOST="${STRATUM_HOST:-0.0.0.0}"
export STRATUM_PORT="${STRATUM_PORT:-9434}"
export GAME_API_PORT="${GAME_API_PORT:-9436}"

echo "Configuration:"
echo "  Workspace: $EXCAL_WORKSPACE"
echo "  RPC: $FORK_RPC_HOST:$FORK_RPC_PORT"
echo "  Stratum: $STRATUM_HOST:$STRATUM_PORT"
echo "  Game API: 0.0.0.0:$GAME_API_PORT"
echo

# Check chain file
if [ ! -f "$EXCAL_WORKSPACE/chain.jsonl" ]; then
    echo "WARNING: chain.jsonl not found in $EXCAL_WORKSPACE"
    echo "The node will start with an empty chain."
    echo
fi

# Cleanup function
cleanup() {
    echo "Shutting down EXCAL stack..."
    kill $FORK_PID $P2P_PID $STRATUM_PID $GAME_PID 2>/dev/null
    wait $FORK_PID $P2P_PID $STRATUM_PID $GAME_PID 2>/dev/null
    echo "All services stopped."
    exit 0
}

trap cleanup SIGINT SIGTERM

# Start fork node (RPC server)
echo "Starting fork node RPC server..."
python3 fork_node.py &
FORK_PID=$!

# Wait for RPC to be ready
echo "Waiting for RPC server..."
sleep 5

# Start P2P layer
echo "Starting P2P layer..."
python3 p2p_layer.py --rpc-port $FORK_RPC_PORT &
P2P_PID=$!

# Start stratum server
echo "Starting stratum server..."
python3 stratum_fork.py &
STRATUM_PID=$!

# Start Camelot Game API
echo "Starting Camelot Game API..."
python3 camelot_api.py &
GAME_PID=$!

echo
echo "========================================"
echo "  ⚔️ AetherionEXCAL Stack Started"
echo "========================================"
echo
echo "Services:"
echo "  RPC:            $FORK_RPC_HOST:$FORK_RPC_PORT"
echo "  P2P (EREPR):    0.0.0.0:9433"
echo "  Bitcoin Bridge: 0.0.0.0:8333"
echo "  Stratum:        $STRATUM_HOST:$STRATUM_PORT"
echo "  Health Check:   0.0.0.0:9435"
echo "  Game API:       0.0.0.0:$GAME_API_PORT"
echo
echo "Press Ctrl+C to stop all services"
echo

# Wait for all background processes
wait
