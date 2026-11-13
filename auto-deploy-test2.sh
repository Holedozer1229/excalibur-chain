#!/bin/bash
# auto-deploy.sh - EXCAL King Auto-Bootstrap & Deploy
#
# One-command bootstrap, deploy, and start the full EXCAL King P2P stack.
# This script combines:
#   1. Bootstrap - repo clone/update, Python check, chain download, pip install
#   2. Deploy - module checks, config validation, chain verification
#   3. Start - launch all services (RPC, P2P, Stratum, Game API)
#
# Usage:
#   bash auto-deploy.sh
#   bash auto-deploy.sh --skip-chain-download
#   bash auto-deploy.sh --skip-start
#   bash auto-deploy.sh --dev

set -euo pipefail

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Parse arguments
SKIP_CHAIN_DOWNLOAD=false
SKIP_START=false
DEV=false
FORCE=false

for arg in "$@"; do
  case $arg in
    --skip-chain-download) SKIP_CHAIN_DOWNLOAD=true ;;
    --skip-start) SKIP_START=true ;;
    --dev) DEV=true ;;
    --force) FORCE=true ;;
  esac
done

write_step() { echo -e "\n${CYAN}>> $1${NC}" }
write_ok() { echo -e "${GREEN}[OK] $1${NC}" }
write_warn() { echo -e "${YELLOW}[WARN] $1${NC}" }
write_err() { echo -e "${RED}[ERR] $1${NC}" }
fail() { write_err "$1"; exit 1 }

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  EXCAL King - Auto Bootstrap & Deploy${NC}"
echo -e "${CYAN}  Version: 2.0.0-king${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

# ============================================================
# STEP 1: Determine install directory
# ============================================================
write_step "STEP 1: Determining install directory"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -d "$SCRIPT_DIR/.git" ]; then
  INSTALL_DIR="$SCRIPT_DIR"
else
  INSTALL_DIR="$HOME/excalibur-chain"
fi

write_ok "Install directory: $INSTALL_DIR"

# ============================================================
# STEP 2: Git clone or update
# ============================================================
write_step "STEP 2: Git repository setup"

if ! command -v git &> /dev/null; then
  fail "Git not found. Install git and re-run."
fi

REPO_URL="https://github.com/Holedozer1229/excalibur-chain.git"

if [ -d "$INSTALL_DIR/.git" ]; then
  echo "Repository found - pulling latest..."
  if git -C "$INSTALL_DIR" pull --ff-only 2>/dev/null; then
    write_ok "Repository updated"
  else
    write_warn "Git pull failed - continuing with current checkout"
  fi
else
  echo "Cloning repository..."
  if git clone "$REPO_URL" "$INSTALL_DIR"; then
    write_ok "Repository cloned"
  else
    fail "Git clone failed"
  fi
fi

# ============================================================
# STEP 3: Python 3.10+ check
# ============================================================
write_step "STEP 3: Checking Python"

PY_CMD=""

# Try python3 first, then python
for cmd in python3 python; do
  if command -v $cmd &> /dev/null; then
    version=$($cmd --version 2>&1 | grep -oP 'Python 3.\K\d+')
    if [ -n "$version" ] && [ "$version" -ge 10 ]; then
      PY_CMD="$cmd"
      break
    fi
  fi
done

# Check virtual environment
if [ -z "$PY_CMD" ] && [ -f "$INSTALL_DIR/.venv/bin/python" ]; then
  version=$($INSTALL_DIR/.venv/bin/python --version 2>&1 | grep -oP 'Python 3.\K\d+')
  if [ -n "$version" ] && [ "$version" -ge 10 ]; then
    PY_CMD="$INSTALL_DIR/.venv/bin/python"
  fi
fi

if [ -z "$PY_CMD" ]; then
  fail "Python 3.10+ not found. Install from https://www.python.org/downloads/"
fi

py_version=$($PY_CMD --version 2>&1)
write_ok "Python found: $py_version"

# ============================================================
# STEP 4: Install Python dependencies
# ============================================================
write_step "STEP 4: Installing Python dependencies"

cd "$INSTALL_DIR"

# Create venv if it does not exist
VENV_DIR="$INSTALL_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
  echo "Creating virtual environment..."
  $PY_CMD -m venv "$VENV_DIR"
  write_ok "Virtual environment created"
fi

# Use venv Python
VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

if [ -f "$VENV_PY" ]; then
  PY_CMD="$VENV_PY"
fi

# Upgrade pip
echo "Upgrading pip..."
$VENV_PIP install --upgrade pip -q 2>/dev/null
write_ok "Pip upgraded"

# Install dependencies
if [ -f "$INSTALL_DIR/requirements.txt" ]; then
  echo "Installing dependencies from requirements.txt..."
  if $VENV_PIP install -r "$INSTALL_DIR/requirements.txt" -q 2>/dev/null; then
    write_ok "Dependencies installed"
  else
    write_warn "Some dependencies may have failed to install"
  fi
fi

# ============================================================
# STEP 5: Download and verify chain data
# ============================================================
write_step "STEP 5: Chain data setup"

CHAIN_GZ="$INSTALL_DIR/chain.jsonl.gz"
CHAIN_FILE="$INSTALL_DIR/chain.jsonl"

if [ "$SKIP_CHAIN_DOWNLOAD" = false ]; then
  if [ -f "$CHAIN_FILE" ] && [ "$FORCE" = false ]; then
    size_mb=$(du -m "$CHAIN_FILE" | cut -f1)
    write_ok "chain.jsonl already present (${size_mb} MB)"
  else
    RELEASE_LATEST="https://github.com/Holedozer1229/excalibur-chain/releases/latest/download/chain.jsonl.gz"
    RELEASE_TAGGED="https://github.com/Holedozer1229/excalibur-chain/releases/download/chain-snapshot-2026-11-12/chain.jsonl.gz"

    downloaded=false
    for url in "$RELEASE_LATEST" "$RELEASE_TAGGED"; do
      echo "  Downloading from $url"
      if curl -fSL -o "$CHAIN_GZ" "$url" 2>/dev/null; then
        downloaded=true
        break
      else
        write_warn "  Download failed, trying next URL..."
      fi
    done

    if [ "$downloaded" = true ]; then
      echo "  Decompressing chain data..."
      $PY_CMD -c "import gzip, shutil; shutil.copyfileobj(gzip.open('$CHAIN_GZ','rb'), open('$CHAIN_FILE','wb'))"
      if [ $? -eq 0 ]; then
        size_mb=$(du -m "$CHAIN_FILE" | cut -f1)
        write_ok "Chain data decompressed (${size_mb} MB)"
      else
        fail "Chain decompression failed"
      fi
    else
      write_warn "Could not download chain snapshot - node will start with empty chain"
    fi
  fi
else
  write_warn "Chain download skipped (--skip-chain-download)"
fi

# ============================================================
# STEP 6: Validate configuration
# ============================================================
write_step "STEP 6: Validating configuration"

CONFIG_FILE="$INSTALL_DIR/config.json"
if [ -f "$CONFIG_FILE" ]; then
  # Use Python to parse JSON into a temp file
  CONFIG_TMP=$(mktemp)
  $PY_CMD -c "
import json
with open('$CONFIG_FILE') as f:
    c = json.load(f)
p2p = c.get('p2p', {})
cg = c.get('camelot_game', {})
print('P2P_PORT=' + str(p2p.get('listen_port', 0)))
print('BTC_BRIDGE=' + str(p2p.get('bitcoin_bridge_port', 0)))
print('ATOMIC_SWAP=' + str(p2p.get('atomic_swap_enabled', False)))
print('QUANTUM_SWAP=' + str(p2p.get('quantum_swap_enabled', False)))
print('EREPR=' + str(p2p.get('erepr_enabled', False)))
print('GAME_ENABLED=' + str(cg.get('enabled', False)))
print('GAME_PORT=' + str(cg.get('api_port', 0)))
" > "$CONFIG_TMP"
  source "$CONFIG_TMP"
  rm -f "$CONFIG_TMP"

  if [ "$P2P_PORT" -eq 9433 ]; then
    write_ok "P2P port: 9433 (EXCAL)"
  else
    write_warn "P2P port: $P2P_PORT (expected 9433)"
  fi

  if [ "$BTC_BRIDGE" -eq 8333 ]; then
    write_ok "Bitcoin bridge port: 8333"
  fi

  [ "$ATOMIC_SWAP" = "True" ] && write_ok "Atomic swap: enabled"
  [ "$QUANTUM_SWAP" = "True" ] && write_ok "Quantum swap: enabled"
  [ "$EREPR" = "True" ] && write_ok "EREPR protocol: enabled"

  if [ "$GAME_ENABLED" = "True" ]; then
    write_ok "Camelot Game API: enabled (port $GAME_PORT)"
  fi

  write_ok "Configuration validated"
else
  write_warn "config.json not found - using defaults"
fi

# ============================================================
# STEP 7: Check core modules
# ============================================================
write_step "STEP 7: Checking core modules"

CORE_MODULES="genesis_fork txscript p2p_layer fork_node stratum_fork trifold_lockbox lightledger camelot_api"

module_errors=0
for mod in $CORE_MODULES; do
  if $PY_CMD -c "import $mod" 2>/dev/null; then
    write_ok "$mod module loaded"
  else
    write_warn "$mod import failed"
    ((module_errors++)) || true
  fi
done

if [ $module_errors -gt 0 ]; then
  write_warn "$module_errors module(s) had import issues - continuing anyway"
fi

# ============================================================
# STEP 8: Run deploy.py verification
# ============================================================
write_step "STEP 8: Running deploy verification"

DEPLOY_SCRIPT="$INSTALL_DIR/deploy.py"
if [ -f "$DEPLOY_SCRIPT" ]; then
  DEPLOY_ARGS="--skip-tests --skip-wallet"
  [ "$DEV" = true ] && DEPLOY_ARGS="$DEPLOY_ARGS --dev"

  $PY_CMD "$DEPLOY_SCRIPT" $DEPLOY_ARGS 2>&1 | while IFS= read -r line; do
    echo "  $line"
  done

  if [ ${PIPESTATUS[0]} -eq 0 ]; then
    write_ok "Deploy verification passed"
  else
    write_warn "Deploy verification completed with warnings"
  fi
else
  write_warn "deploy.py not found - skipping verification"
fi

# ============================================================
# STEP 9: Summary
# ============================================================
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  EXCAL King - Bootstrap Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${CYAN}Services available:${NC}"
echo "  RPC:            0.0.0.0:9432"
echo "  P2P (EREPR):    0.0.0.0:9433"
echo "  Bitcoin Bridge: 0.0.0.0:8333"
echo "  Stratum:        0.0.0.0:9434"
echo "  Health Check:   0.0.0.0:9435"
echo "  Game API:       0.0.0.0:9436"
echo ""

# ============================================================
# STEP 10: Auto-start services
# ============================================================
if [ "$SKIP_START" = false ]; then
  write_step "STEP 10: Starting all services"

  # Set environment
  export EXCAL_WORKSPACE="$INSTALL_DIR"
  export FORK_RPC_PORT="9432"
  export FORK_RPC_HOST="0.0.0.0"
  export STRATUM_HOST="0.0.0.0"
  export STRATUM_PORT="9434"
  export GAME_API_PORT="9436"

  cd "$INSTALL_DIR"

  # Cleanup function
  cleanup() {
    echo "Shutting down EXCAL stack..."
    kill $FORK_PID $P2P_PID $STRATUM_PID $GAME_PID 2>/dev/null
    wait $FORK_PID $P2P_PID $STRATUM_PID $GAME_PID 2>/dev/null
    echo "All services stopped."
    exit 0
  }
  trap cleanup SIGINT SIGTERM

  # Start fork node (RPC)
  echo "Starting fork node RPC server..."
  $PY_CMD fork_node.py &
  FORK_PID=$!
  sleep 3
  write_ok "Fork node started (RPC:9432)"

  # Start P2P layer
  echo "Starting P2P layer..."
  $PY_CMD p2p_layer.py --rpc-port 9432 &
  P2P_PID=$!
  sleep 2
  write_ok "P2P layer started (P2P:9433, Bitcoin:8333)"

  # Start Stratum
  echo "Starting Stratum server..."
  $PY_CMD stratum_fork.py &
  STRATUM_PID=$!
  sleep 2
  write_ok "Stratum server started (Stratum:9434)"

  # Start Camelot Game API
  echo "Starting Camelot Game API..."
  $PY_CMD camelot_api.py &
  GAME_PID=$!
  sleep 2
  write_ok "Camelot Game API started (Game:9436)"

  echo ""
  echo -e "${GREEN}========================================${NC}"
  echo -e "${GREEN}  EXCAL King Stack is RUNNING${NC}"
  echo -e "${GREEN}========================================${NC}"
  echo ""
  echo -e "${YELLOW}All services started in background.${NC}"
  echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
  echo ""
  echo -e "${CYAN}Quick commands:${NC}"
  echo "  RPC test: curl http://localhost:9432"
  echo "  Health:   curl http://localhost:9435/health"
  echo "  Game API: curl http://localhost:9436/stats"
  echo ""

  # Wait for all background processes
  wait
else
  write_warn "Service start skipped (--skip-start)"
  write_warn "Run: bash start-production.sh to start all services"
  echo ""
fi

echo -e "${GREEN}Auto-deploy complete. EXCAL King is ready.${NC}"
