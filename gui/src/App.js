import React, { useState, useEffect } from 'react';
import './App.css';

const RPC_URL = 'http://localhost:9432';

async function rpc(method, params = []) {
  try {
    const res = await fetch(RPC_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ jsonrpc: '2.0', method, params, id: 1 })
    });
    const data = await res.json();
    return data.result || data;
  } catch (e) {
    return null;
  }
}

function StatCard({ label, value, icon }) {
  return (
    <div className="stat-card">
      <div className="stat-icon">{icon}</div>
      <div className="stat-content">
        <div className="stat-label">{label}</div>
        <div className="stat-value">{value !== null ? value : '—'}</div>
      </div>
    </div>
  );
}

function ChainStats() {
  const [metrics, setMetrics] = useState(null);
  const [height, setHeight] = useState(null);
  const [hash, setHash] = useState(null);

  useEffect(() => {
    async function fetch() {
      const m = await rpc('getmetrics');
      const h = await rpc('getblockcount');
      const bh = await rpc('getbestblockhash');
      if (m) setMetrics(m);
      if (h !== null) setHeight(h);
      if (bh) setHash(bh);
    }
    fetch();
    const id = setInterval(fetch, 5000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="section">
      <h2>⛓️ Chain Status</h2>
      <div className="stats-grid">
        <StatCard label="Block Height" value={height} icon="📦" />
        <StatCard label="Best Block" value={hash ? hash.slice(0, 16) + '...' : null} icon="🔗" />
        <StatCard label="Avg Block Time" value={metrics ? `${metrics.avg_block_time.toFixed(1)}s` : null} icon="⏱️" />
        <StatCard label="Hashrate Est." value={metrics ? `${(metrics.hashrate_estimate / 1e9).toFixed(2)} GH/s` : null} icon="⚡" />
        <StatCard label="Difficulty" value={metrics ? metrics.total_difficulty?.toLocaleString() : null} icon="🔒" />
        <StatCard label="Uptime" value={metrics ? `${Math.floor(metrics.uptime_seconds / 60)}m` : null} icon="🕐" />
      </div>
    </div>
  );
}

function NetworkStats() {
  const [info, setInfo] = useState(null);

  useEffect(() => {
    async function fetch() {
      const n = await rpc('getnetworkinfo');
      if (n) setInfo(n);
    }
    fetch();
    const id = setInterval(fetch, 10000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="section">
      <h2>🌐 Network</h2>
      <div className="stats-grid">
        <StatCard label="Version" value={info?.version} icon="📌" />
        <StatCard label="Protocol" value={info?.protocol_version} icon="📡" />
        <StatCard label="Network" value={info?.network} icon="🌍" />
        <StatCard label="Connections" value={info?.connections} icon="🔌" />
      </div>
      {info?.features && (
        <div className="features">
          <h3>Features</h3>
          <div className="feature-tags">
            {info.features.map((f, i) => (
              <span key={i} className="feature-tag">{f}</span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function MiningStats() {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    async function fetch() {
      const s = await fetch(`${RPC_URL}/mining-stats`)
        .then(r => r.json())
        .catch(() => null);
      if (s) setStats(s);
    }
    fetch();
    const id = setInterval(fetch, 5000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="section">
      <h2>⛏️ Mining</h2>
      <div className="stats-grid">
        <StatCard label="Miners Connected" value={stats?.miners_connected} icon="👷" />
        <StatCard label="Total Shares" value={stats?.total_shares?.toLocaleString()} icon="📊" />
        <StatCard label="Blocks Found" value={stats?.total_blocks} icon="🧱" />
        <StatCard label="Shares/sec" value={stats?.shares_per_second?.toFixed(2)} icon="📈" />
      </div>
    </div>
  );
}

function GameStats() {
  const [stats, setStats] = useState(null);

  useEffect(() => {
    async function fetch() {
      const s = await fetch('http://localhost:9436/stats')
        .then(r => r.json())
        .catch(() => null);
      if (s) setStats(s);
    }
    fetch();
    const id = setInterval(fetch, 10000);
    return () => clearInterval(id);
  }, []);

  return (
    <div className="section">
      <h2>🎮 Camelot Game API</h2>
      <div className="stats-grid">
        <StatCard label="Total Events" value={stats?.total_events} icon="📜" />
        <StatCard label="Registered Items" value={stats?.items_count} icon="⚔️" />
        <StatCard label="Active Players" value={stats?.players_count} icon="👥" />
        <StatCard label="Guilds" value={stats?.guilds_count} icon="🏰" />
      </div>
    </div>
  );
}

function App() {
  return (
    <div className="App">
      <header className="App-header">
        <h1>⚔️ AetherionEXCAL Dashboard</h1>
        <p className="subtitle">Real-time blockchain monitoring</p>
      </header>
      <main>
        <ChainStats />
        <NetworkStats />
        <MiningStats />
        <GameStats />
      </main>
    </div>
  );
}

export default App;
