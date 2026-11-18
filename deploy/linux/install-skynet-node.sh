#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="/opt/excalibur-chain"
DATA_DIR="/var/lib/excalibur"
ENV_FILE="/etc/excalibur-node.env"
UNIT_DIR="/etc/systemd/system"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run this installer as root (for example: sudo $0 PUBLIC_HOST [SEEDS])." >&2
  exit 1
fi

if [[ ! -f "$REPO_DIR/fork_node.py" || ! -f "$REPO_DIR/living_ledger.py" ]]; then
  echo "Expected the repository checkout at $REPO_DIR." >&2
  exit 1
fi

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: sudo $0 PUBLIC_IP [SEED_HOST:PORT,SEED_HOST:PORT,...]" >&2
  exit 1
fi

PUBLIC_IP="$1"
SEEDS="${2:-}"
if [[ "$SEEDS" =~ [^A-Za-z0-9.,_:\[\]-] ]]; then
  echo "Seed peers must be comma-separated host:port addresses." >&2
  exit 1
fi

if [[ ! -f "$REPO_DIR/chain.jsonl" ]]; then
  echo "Missing $REPO_DIR/chain.jsonl. Put a verified chain snapshot there before installing." >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1 || ! command -v systemctl >/dev/null 2>&1; then
  echo "This installer requires Python 3 and systemd." >&2
  exit 1
fi
if ! python3 -c '
import ipaddress
import sys
sys.exit(0 if ipaddress.ip_address(sys.argv[1]).is_global else 1)
' "$PUBLIC_IP"; then
  echo "PUBLIC_IP must be a public IPv4 or IPv6 address (DNS is not advertised by P2P)." >&2
  exit 1
fi

id excal >/dev/null 2>&1 || useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin excal
install -d -o excal -g excal -m 0750 "$DATA_DIR"
install -o excal -g excal -m 0640 "$REPO_DIR/chain.jsonl" "$DATA_DIR/chain.jsonl"
python3 -m venv "$REPO_DIR/.venv"
"$REPO_DIR/.venv/bin/python" -m pip install 'cryptography>=41' 'prometheus-client>=0.20,<1'

cat > "$ENV_FILE" <<EOF
EXCAL_CHAIN_FILE=$DATA_DIR/chain.jsonl
EXCAL_WORKSPACE=$REPO_DIR
FORK_RPC_HOST=127.0.0.1
FORK_RPC_PORT=9432
FORK_P2P_HOST=0.0.0.0
FORK_P2P_PORT=9433
FORK_P2P_ADVERTISE_HOST=$PUBLIC_IP
FORK_P2P_SEEDS=$SEEDS
EXCAL_PROMETHEUS_HOST=127.0.0.1
EXCAL_PROMETHEUS_PORT=9435
EOF
chmod 0640 "$ENV_FILE"
chown root:excal "$ENV_FILE"

cat > "$UNIT_DIR/excal-node.service" <<'EOF'
[Unit]
Description=AetherionEXCAL full node and P2P seed
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=excal
Group=excal
WorkingDirectory=/opt/excalibur-chain
EnvironmentFile=/etc/excalibur-node.env
ExecStart=/opt/excalibur-chain/.venv/bin/python /opt/excalibur-chain/fork_node.py
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadWritePaths=/var/lib/excalibur

[Install]
WantedBy=multi-user.target
EOF

cat > "$UNIT_DIR/excal-living-ledger.service" <<'EOF'
[Unit]
Description=AetherionEXCAL Living Ledger web explorer
After=excal-node.service
Requires=excal-node.service

[Service]
Type=simple
User=excal
Group=excal
WorkingDirectory=/opt/excalibur-chain
EnvironmentFile=/etc/excalibur-node.env
ExecStart=/opt/excalibur-chain/.venv/bin/python /opt/excalibur-chain/living_ledger.py --host 127.0.0.1 --port 9434 --rpc http://127.0.0.1:9432
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now excal-node.service excal-living-ledger.service
echo "Node and Living Ledger services installed."
echo "P2P:     TCP 9433 (open this port in the VM firewall/security list)"
echo "RPC:     127.0.0.1:9432 (private)"
echo "Ledger:  127.0.0.1:9434 (put a TLS reverse proxy in front for public web access)"
echo "Metrics: 127.0.0.1:9435/metrics (private; scrape from a local Prometheus)"
echo "Status:  systemctl status excal-node excal-living-ledger"
