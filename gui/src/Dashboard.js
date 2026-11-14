import React, { useCallback, useEffect, useState } from 'react';
import './Dashboard.css';

const RPC_URL = process.env.REACT_APP_RPC_URL || '/rpc';
const GAME_STATS_URL = process.env.REACT_APP_GAME_STATS_URL || '/game-api/api/game/stats';
const REFRESH_INTERVAL = 10000;

async function rpc(method) {
  if (window.electronAPI?.rpc) return window.electronAPI.rpc(method);
  const response = await fetch(RPC_URL, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ jsonrpc: '2.0', method, params: [], id: method })
  });
  if (!response.ok) throw new Error(`RPC returned HTTP ${response.status}`);
  const payload = await response.json();
  if (payload.error) throw new Error(payload.error.message || payload.error);
  return payload.result;
}

async function getGameStats() {
  if (window.electronAPI?.gameStats) return window.electronAPI.gameStats();
  const response = await fetch(GAME_STATS_URL);
  if (!response.ok) throw new Error(`Game API returned HTTP ${response.status}`);
  return response.json();
}

function number(value, options = {}) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return null;
  return new Intl.NumberFormat(undefined, options).format(Number(value));
}

function duration(value) {
  if (!Number.isFinite(Number(value))) return null;
  const minutes = Math.floor(Number(value) / 60);
  const days = Math.floor(minutes / 1440);
  const hours = Math.floor((minutes % 1440) / 60);
  const remainder = minutes % 60;
  if (days) return `${days}d ${hours}h`;
  if (hours) return `${hours}h ${remainder}m`;
  return `${remainder}m`;
}

function Status({ online, loading, children }) {
  const state = online ? 'online' : loading ? 'loading' : 'offline';
  return <span className={`status-pill ${state}`}><i />{children}</span>;
}

function StatCard({ label, value, detail, color }) {
  return (
    <article className="metric-card">
      <span className={`metric-accent ${color}`} aria-hidden="true" />
      <div>
        <p className="metric-label">{label}</p>
        <p className={`metric-value${value == null ? ' empty' : ''}`}>{value ?? '--'}</p>
        {detail && <p className="metric-detail">{detail}</p>}
      </div>
    </article>
  );
}

function SectionTitle({ eyebrow, title, children }) {
  return <div className="section-title"><div><p className="eyebrow">{eyebrow}</p><h2>{title}</h2></div>{children}</div>;
}

export default function Dashboard() {
  const [data, setData] = useState({ metrics: null, network: null, game: null });
  const [services, setServices] = useState({ node: 'loading', game: 'loading' });
  const [updatedAt, setUpdatedAt] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [version, setVersion] = useState(null);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    const [metrics, network, game] = await Promise.allSettled([
      rpc('getmetrics'), rpc('getnetworkinfo'), getGameStats()
    ]);
    const nodeOnline = metrics.status === 'fulfilled' && network.status === 'fulfilled';
    setServices({ node: nodeOnline ? 'online' : 'offline', game: game.status === 'fulfilled' ? 'online' : 'offline' });
    setData(previous => ({
      metrics: metrics.status === 'fulfilled' ? metrics.value : previous.metrics,
      network: network.status === 'fulfilled' ? network.value : previous.network,
      game: game.status === 'fulfilled' ? game.value : previous.game
    }));
    if (nodeOnline || game.status === 'fulfilled') setUpdatedAt(new Date());
    setRefreshing(false);
  }, []);

  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, REFRESH_INTERVAL);
    if (window.electronAPI?.getAppVersion) window.electronAPI.getAppVersion().then(setVersion).catch(() => {});
    return () => window.clearInterval(timer);
  }, [refresh]);

  const nodeOnline = services.node === 'online';
  const hash = data.metrics?.chain_hash;
  const rawHashrate = Number(data.metrics?.hashrate_estimate);
  const hashrate = Number.isFinite(rawHashrate)
    ? `${number(rawHashrate / 1e9, { maximumFractionDigits: 2 })} GH/s`
    : null;
  const updatedLabel = updatedAt
    ? `Updated ${updatedAt.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}`
    : 'Waiting for node data';

  return (
    <div className="dashboard-shell" id="top">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="AetherionEXCAL dashboard home">
          <img src={`${process.env.PUBLIC_URL}/logo.png`} alt="" />
          <span><strong>AETHERION</strong><small>EXCAL NETWORK</small></span>
        </a>
        <nav aria-label="Dashboard sections"><a className="selected" href="#overview">Overview</a><a href="#network">Network</a><a href="#activity">Activity</a></nav>
        <div className="topbar-actions">
          <Status online={nodeOnline} loading={services.node === 'loading'}>{nodeOnline ? 'Node online' : services.node === 'loading' ? 'Connecting' : 'Node offline'}</Status>
          <button className="refresh-button" onClick={refresh} disabled={refreshing} type="button"><span className={refreshing ? 'refresh-symbol spinning' : 'refresh-symbol'} aria-hidden="true">&#8635;</span>{refreshing ? 'Refreshing' : 'Refresh'}</button>
        </div>
      </header>

      <main className="dashboard-main">
        <section className="hero" id="overview">
          <div className="hero-content">
            <p className="eyebrow">NETWORK OVERVIEW <span className="live-tag"><i /> LIVE</span></p>
            <h1>Network at a glance</h1>
            <p className="hero-description">Chain health, peer activity, and ecosystem signals in one place.</p>
            <p className="updated-label"><span />{updatedLabel}</p>
          </div>
          <div className="hero-block"><span>Current block</span><strong>{number(data.metrics?.chain_height) ?? '--'}</strong><small>{data.network?.network || 'EXCAL network'}</small></div>
          <div className="hero-ring ring-a" /><div className="hero-ring ring-b" />
        </section>

        <section className="dashboard-section">
          <SectionTitle eyebrow="CHAIN" title="Chain health"><Status online={nodeOnline} loading={services.node === 'loading'}>{nodeOnline ? 'Connected' : 'Waiting for node'}</Status></SectionTitle>
          <div className="metric-grid">
            <StatCard label="Block height" value={number(data.metrics?.chain_height)} detail="Validated chain tip" color="purple" />
            <StatCard label="Difficulty" value={number(data.metrics?.total_difficulty, { notation: 'compact', maximumFractionDigits: 2 })} detail="Current chain difficulty" color="blue" />
            <StatCard label="Hashrate estimate" value={hashrate} detail="Estimated from chain history" color="green" />
            <StatCard label="Node uptime" value={duration(data.metrics?.uptime_seconds)} detail="Since this node started" color="amber" />
          </div>
          <div className="hash-panel"><div className="hash-heading"><span className="hash-mark">#</span><span><strong>Latest block</strong><small>Best known block hash</small></span></div><code title={hash || ''}>{hash || 'Waiting for the node to report a block hash'}</code></div>
        </section>

        <section className="dashboard-section" id="network">
          <SectionTitle eyebrow="PEER TO PEER" title="Network"><Status online={nodeOnline} loading={services.node === 'loading'}>{nodeOnline ? 'Network active' : 'No connection'}</Status></SectionTitle>
          <div className="network-grid">
            <div className="metric-grid network-metrics">
              <StatCard label="Connected peers" value={number(data.network?.connections)} detail="Active node connections" color="blue" />
              <StatCard label="Protocol" value={number(data.network?.protocol_version)} detail={`Node ${data.network?.version || '--'}`} color="purple" />
            </div>
            <div className="capability-panel"><div className="capability-heading"><span>Node capabilities</span><span>{data.network?.features?.length || 0}</span></div>
              {data.network?.features?.length ? <div className="capability-list">{data.network.features.map(feature => <span className="capability-chip" key={feature}><i />{feature.replaceAll('-', ' ')}</span>)}</div> : <p className="empty-message">Capabilities will appear when the node connects.</p>}
            </div>
          </div>
        </section>

        <section className="dashboard-section" id="activity">
          <SectionTitle eyebrow="ECOSYSTEM" title="Camelot activity"><Status online={services.game === 'online'} loading={services.game === 'loading'}>{services.game === 'online' ? 'API connected' : 'API unavailable'}</Status></SectionTitle>
          <div className="metric-grid">
            <StatCard label="Total events" value={number(data.game?.total_events)} detail="Recorded game events" color="purple" />
            <StatCard label="Registered items" value={number(data.game?.registered_items)} detail="Items in the registry" color="blue" />
            <StatCard label="Registered players" value={number(data.game?.registered_players)} detail="Players with activity" color="green" />
            <StatCard label="Active webhooks" value={number(data.game?.active_webhooks)} detail="Event delivery hooks" color="amber" />
          </div>
          {services.game === 'offline' && <p className="service-note">Camelot statistics appear when the Game API is running on this device.</p>}
        </section>

        {!nodeOnline && <aside className="connect-note" role="status"><span className="info-mark">i</span><div><strong>Connect a local node to see live data</strong><p>Start the Excalibur node service on port 9432. This dashboard refreshes automatically when it becomes available.</p></div></aside>}
        <footer className="dashboard-footer"><span>AetherionEXCAL Network Dashboard{version ? ` · v${version}` : ''}</span><span>{updatedLabel}</span></footer>
      </main>
    </div>
  );
}
