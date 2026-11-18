# Running a SkyNet Living Ledger node

Each participant runs their own full node. The node validates and relays the
chain over P2P; the Living Ledger is a read-only explorer served from that
node. SkyNet beacon discovery can help peers find one another, but it does not
store or control the ledger.

## Public seed node (Ubuntu with systemd)

The deployment uses the repository's `fork_node.py` and `living_ledger.py`.
The node's JSON-RPC endpoint stays on loopback; only P2P is intended to be
reachable directly from the internet. The web explorer listens on loopback and
should be exposed through a TLS reverse proxy. The node exports Prometheus
metrics for chain state, mempool, peer counts, EREPR support/gossip, peer
latency, and uptime on loopback port 9435.

1. Provision an Ubuntu VM with a public IP and install Python 3, `python3-venv`,
   Git, and systemd. Clone this repository to `/opt/excalibur-chain`. The installer
   creates a dedicated virtual environment and installs `prometheus-client`.
2. Place a **verified** `chain.jsonl` snapshot at
   `/opt/excalibur-chain/chain.jsonl`. The node requires this file to start;
   the installer will not silently start an empty chain.
3. Install the systemd services, substituting the VM's public IP or DNS name:

   ```sh
   sudo bash /opt/excalibur-chain/deploy/linux/install-skynet-node.sh NODE_PUBLIC_IP
   ```

   Use the VM's literal public IP here; the P2P handshake advertises IP
   addresses, not DNS names. Use DNS separately for the public Ledger domain.
   To connect it to an existing peer, pass seed addresses as a second
   argument, for example `SEED_HOST:9433,OTHER_SEED:9433`.
4. Allow inbound **TCP 9433 only for P2P** in both the cloud security list and
   host firewall. Keep TCP 9432 private. The services are
   `excal-node.service` and `excal-living-ledger.service`.
5. To publish the explorer, configure Caddy or another TLS reverse proxy for
   a domain to `127.0.0.1:9434`. An example Caddy site is in
   `deploy/linux/excal-ledger.Caddyfile.example`; allow inbound TCP 80/443 for
   certificate issuance and HTTPS.

Check startup with `systemctl status excal-node excal-living-ledger` and
`journalctl -u excal-node -f`. The public P2P address is written to
`/etc/excalibur-node.env`. Seed peers can be updated there, then activated
with `sudo systemctl restart excal-node excal-living-ledger`.

## Prometheus monitoring

The node exposes `/metrics` on `127.0.0.1:9435`; scraping it does not require
opening another public firewall port. Install and run Prometheus on the same VM with `prometheus.yml` as its
configuration to scrape this node. Keep the Prometheus web UI private as well.
If a separate monitoring server is needed, use a VPN
or another authenticated management network and restrict scraping to that
network; do not make port 9435 public. These metrics describe the local node's
view of P2P and are not a network-wide consensus oracle.

On Ubuntu, a local Prometheus installation can use:

```sh
sudo apt-get install prometheus
sudo install -o root -g prometheus -m 0644 \
  /opt/excalibur-chain/prometheus.yml /etc/prometheus/prometheus.yml
sudo systemctl enable --now prometheus
sudo systemctl restart prometheus
curl --fail http://127.0.0.1:9090/-/healthy
```

Do not open TCP 9090 in the VM firewall.

This node runs the repository's `excal-fork` network (the EXCAL fork), not
Bitcoin mainnet. For production use, independently verify the chain snapshot
and test sync, peer connectivity, backups, firewall policy, and TLS before
advertising the seed address.

The VM must have enough storage for the chain and future growth. The installer
copies the snapshot into `/var/lib/excalibur/chain.jsonl` so the service account
can persist its height checkpoint. Back up this directory before replacing or
upgrading chain data.

## IPFS distribution (optional)

Use IPFS to distribute immutable files, such as a verified compressed chain
snapshot or a static copy of the Ledger site. IPFS does not run the node,
provide a live JSON-RPC API, or guarantee that content stays available unless
one or more IPFS nodes keep it pinned. Keep the node's live P2P service on TCP
9433 and its Ledger on HTTPS; IPFS complements those services rather than
replacing them.

Install and initialize Kubo using the
[official Kubo installation guide](https://docs.ipfs.tech/install/command-line/).
Keep the Kubo RPC API on loopback and do not expose TCP 5001 to the internet.
If this VM should also serve IPFS content to peers, allow TCP and UDP 4001
through the host and cloud firewalls. Keep the gateway on loopback unless it is
deliberately placed behind a secured web proxy.

To publish a snapshot after verifying it with the repository's verifier:

```sh
sha256sum chain.jsonl.gz
ipfs add --pin=true --cid-version=1 chain.jsonl.gz
```

Record the resulting CID and SHA-256 in the release notes. Consumers can fetch
the snapshot with `ipfs get <CID>` and should verify the recorded digest and
run the chain verifier before starting their node. A CID proves the downloaded
bytes match that identifier; it does not prove the chain is valid. Keep at
least one independent pin or backup because this VM's pin alone is a
single point of availability.

To publish the static GitHub Pages files, from the repository root run:

```sh
ipfs add -Qr --pin=true --cid-version=1 docs
```

The command prints the root CID for the `docs` directory. Open it at
`https://<CID>.ipfs.dweb.link/` or another trusted IPFS gateway. Relative page
links work at the directory path. For availability, keep this CID pinned on an
always-on Kubo node or a pinning service; a CID by itself is not a storage
service. Pin updated content under its new CID; use IPNS only if a mutable name
is needed, and retain versioned CIDs for rollback. This static copy cannot
keep a browser VM awake and cannot serve the node's live RPC-backed Ledger
data.

## Nodes on users' computers

Users can run the same node locally with Python 3 and their own verified
chain snapshot. Configure one or more stable seed addresses in
`FORK_P2P_SEEDS`, bind P2P on port 9433, and keep `FORK_RPC_HOST=127.0.0.1`.
The local Living Ledger connects to `http://127.0.0.1:9432`; the RPC port must
not be forwarded or exposed to the public internet. Users behind NAT can make
outbound P2P connections without router changes; port forwarding 9433 is
optional and allows other peers to initiate connections.

DistroSea can be opened from the [SkyNet Node Pages portal](./skynet-node.html)
to experiment with Linux in a browser session, but it is not a persistent
public seed. Session lifetime, persistent storage, and inbound P2P connectivity
are not guaranteed; GitHub Pages cannot keep the session running.

The first public seed's IP/DNS name must be added to client seed configuration
after the VM is provisioned. A free-tier VM is subject to provider eligibility
and regional capacity; this repository cannot provision a cloud account or
guarantee free capacity.

## Windows desktop installer

The Windows installer includes an optional **Local IPFS Node** component. The
installer initializes Kubo in the installing user's profile and explicitly
binds its RPC API (`127.0.0.1:5001`) and gateway (`127.0.0.1:8080`) to
loopback. It does not expose the privileged Kubo API to the LAN or internet.
Starting the daemon automatically at sign-in is a separate, unchecked task;
users can also launch **Start Local IPFS Node** from the Start Menu.

The installer build downloads the pinned Kubo `v0.43.1` Windows AMD64 release
from the official IPFS GitHub release and checks its SHA-256 before packaging.
Kubo license files are installed beside the binary. Its repository is stored
in the user's default `.ipfs` directory (or the existing `IPFS_PATH`, when
set); pinned data uses that user's local disk. The daemon must be running to
serve pins, and a single user's pin does not guarantee durable public
availability.
