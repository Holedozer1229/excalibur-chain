# AetherionEXCAL React Dashboard

**Real-time monitoring dashboard for the AetherionEXCAL blockchain.**

A React-based dashboard that provides real-time visibility into chain status, network health, mining statistics, and Camelot Game API events.

## Features

- **Chain Status**: Real-time block height, hash, and difficulty
- **Network Stats**: Peer count, latency, EREPR resonance bonds
- **Mining Dashboard**: Hashrate, shares, blocks found
- **Game API Monitor**: Camelot Fair events, item transfers, achievements
- **Health Check**: Service status for all 6 ports

## Quick Start

```bash
# Install dependencies
npm install

# Start development server
npm start

# Build for production
npm run build
```

The development server runs on `http://localhost:3000` and proxies API requests to the RPC server at `http://localhost:9432`.

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
| `get_mining_stats` | Stratum | Mining statistics |
| `game_stats` | Game API | Camelot game statistics |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `REACT_APP_RPC_PORT` | `9432` | RPC server port |
| `REACT_APP_STRATUM_PORT` | `9434` | Stratum server port |
| `REACT_APP_GAME_API_PORT` | `9436` | Game API port |

## Production Build

```bash
npm run build
```

Output: `build/` directory with static files that can be served by any HTTP server.

## License

MIT License — see [LICENSE](../LICENSE) for details.
