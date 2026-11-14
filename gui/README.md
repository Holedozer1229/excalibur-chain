# AetherionEXCAL React Dashboard

**A desktop and web dashboard for monitoring the AetherionEXCAL network.**

A React dashboard for chain health, peer activity, and Camelot Game API statistics. The dashboard refreshes automatically and shows service availability instead of presenting missing data as live values.

## Features

- **Chain Status**: Real-time block height, hash, and difficulty
- **Network Stats**: Peer count, latency, EREPR resonance bonds
- **Chain Health**: Block height, difficulty, estimated hashrate, and node uptime
- **Network Monitor**: Peer count, protocol version, and node capabilities
- **Camelot Activity**: Events, registered items and players, and active webhooks
- **Connection State**: Clear online, unavailable, and refresh status

## Quick Start

```bash
# Install dependencies
npm install

# Start development server
npm start

# Build for production
npm run build
```

The development server runs on `http://localhost:3000`. Start the node service on port `9432` and, if needed, the Camelot API on port `9436`. The dashboard does not start these services for you. Electron uses a restricted preload bridge to read the local APIs without granting the page general network access.

## Architecture

```
┌─────────────────────────────────────────────┐
│         React Dashboard (Port 3000)          │
├─────────────────────────────────────────────┤
│                                              │
│  ┌────────────┐  ┌────────────────────────┐ │
│  │  Chain     │  │  Network               │ │
│  │  Status    │  │  Stats                 │ │
│  └────────────┘  └────────────────────────┘ │
│                                              │
│  ┌────────────┐  ┌────────────────────────┐ │
│  │  Mining    │  │  Game API              │ │
│  │  Stats     │  │  Monitor               │ │
│  └────────────┘  └────────────────────────┘ │
│                                              │
│              ┌──────────────┐                │
│              │  Health      │                │
│              │  Check       │                │
│              └──────────────┘                │
│                                              │
└──────────────────┬───────────────────────────┘
                   │ Polls every 5-10s
                   ▼
          ┌──────────────────┐
          │  RPC Server      │
          │  :9432           │
          └──────────────────┘
```

## Components

| Component | Description |
|-----------|-------------|
| `App.js` | Main dashboard layout and state management |
| `App.css` | Styling and responsive design |

## API Integration

The dashboard polls the following endpoints:

| Endpoint | Method | Data |
|----------|--------|------|
| `getblockcount` | RPC | Current chain height |
| `getbestblockhash` | RPC | Latest block hash |
| `getmetrics` | RPC | Chain-wide metrics |
| `getnetworkinfo` | RPC | Network status |
| `getmetrics` | JSON-RPC on `9432` | Chain height, hash, difficulty, hashrate estimate, and uptime |
| `getnetworkinfo` | JSON-RPC on `9432` | Peer count, protocol, and capabilities |
| `GET /api/game/stats` | Game API on `9436` | Camelot event, player, item, and webhook totals |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REACT_APP_RPC_URL` | `/rpc` | JSON-RPC endpoint for browser builds |
| `REACT_APP_GAME_STATS_URL` | `/game-api/api/game/stats` | Camelot statistics endpoint for browser builds |

## Production Build

```bash
npm run build
```

Output: `build/` directory with static files. For live data in a browser deployment, route `/rpc` to the node RPC service and `/game-api` to the Camelot API through a same-origin reverse proxy. The Electron installer handles those local requests through its preload bridge.

## Windows desktop installer

```powershell
npm run electron:build:win
```

The installer is written to `../dist-electron/`. It packages the dashboard UI and expects the node and optional Camelot API to be running locally. The Windows build skips executable resource editing so it can compile without the Windows symbolic-link privilege required by the signing helper; code signing is also skipped unless signing credentials are configured.

## License

MIT License — see [LICENSE](../LICENSE) for details.
