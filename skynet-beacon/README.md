# SkyNet Temporal Node Beacon

An always-on Cloudflare Worker that serves as the central peer discovery bootstrap server for AetherionEXCAL's SkyNet P2P network.

## What it does

When two machines run AetherionEXCAL on different networks (different LANs, different ISPs, different countries), they need a way to find each other. The SkyNet Beacon is that way — a free, always-on server hosted on Cloudflare's global edge network.

## How it works

1. **Node A** starts AetherionEXCAL → registers with the beacon → stores its IP and port
2. **Node B** starts AetherionEXCAL → queries the beacon → discovers Node A's address
3. **Node A ↔ Node B** → direct P2P connection established

## Deployment

### Prerequisites

- Cloudflare account (free)
- Node.js installed (for wrangler CLI)

### Steps

```bash
# 1. Install wrangler
npm install -g wrangler

# 2. Login to Cloudflare
wrangler login

# 3. Create KV namespace
wrangler kv:namespace create SKYNET_KV
# Copy the ID from the output

# 4. Update wrangler.toml
# Replace YOUR_KV_NAMESPACE_ID with the ID from step 3

# 5. Deploy
cd skynet-beacon
npx wrangler deploy
```

After deployment, your beacon will be available at:
```
https://skynet-beacon.YOUR_ACCOUNT.workers.dev
```

### Update the wallet

Edit `sphinx_os/nexus/p2p_bootstrap_server.py` and replace the central server URL:

```python
CENTRAL_BOOTSTRAP_SERVERS = [
    "https://skynet-beacon.YOUR_ACCOUNT.workers.dev",
]
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/register` | Register a node |
| POST | `/unregister` | Unregister a node |
| GET | `/peers?limit=8` | Discover peers |
| GET | `/stats` | Beacon statistics |
| GET | `/health` | Health check |

### Register

```bash
curl -X POST https://skynet-beacon.YOUR_ACCOUNT.workers.dev/register \
  -H "Content-Type: application/json" \
  -d '{"node_id":"abc123","host":"192.168.1.100","port":9433}'
```

### Discover Peers

```bash
curl https://skynet-beacon.YOUR_ACCOUNT.workers.dev/peers?limit=8
```

### Health Check

```bash
curl https://skynet-beacon.YOUR_ACCOUNT.workers.dev/health
```

## Free Tier Limits

- **100,000 requests/day** — enough for ~4,000 nodes registering every minute
- **1GB KV storage** — enough for ~10,000 peer records
- **1,000 KV writes/day** — enough for ~40 registrations per minute
- **$0/month** — completely free for small networks

## Custom Domain (Optional)

If you own a domain on Cloudflare, you can set up a custom route:

1. In `wrangler.toml`, uncomment the `routes` section
2. Set up DNS: `bootstrap.sky-net.excal → your worker`
3. Deploy: `npx wrangler deploy`

## Architecture

```
┌─────────────┐     ┌─────────────┐
│  Node A     │     │  Node B     │
│  Mac        │     │  Windows    │
│  10.0.1.5   │     │  192.168.1. │
└──────┬──────┘     └──────┬──────┘
       │                   │
       │  POST /register   │  GET /peers
       │───────────────────│───────────┐
       │                   │           │
       │                   ▼           │
       │            ┌─────────────┐    │
       │            │  SkyNet     │    │
       │            │  Beacon     │◄───┘
       │            │  (Cloudflare│
       │            │   Worker)   │
       │            └─────────────┘
       │                   │
       │           Returns peer list
       │                   │
       ▼                   ▼
  Connects to Node B ←── Direct P2P
```

## Why Cloudflare Workers?

- **Always on** — no server to manage, no uptime to worry about
- **Global** — deployed to 300+ edge locations worldwide
- **Free** — generous free tier for peer discovery
- **Simple** — deploy with one command
- **Secure** — HTTPS by default, DDoS protection included
