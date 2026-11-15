/**
 * SkyNet Temporal Node Beacon — Cloudflare Worker
 * 
 * An always-on peer discovery bootstrap server for AetherionEXCAL P2P network.
 * Nodes register themselves and query for peers through this beacon.
 * 
 * Deploy to: https://bootstrap.sky-net.excal.workers.dev
 * 
 * Features:
 * - Node registration with automatic IP detection
 * - Peer discovery via REST API
 * - Peer persistence in Workers KV
 * - Health checking and stale peer pruning
 * - CORS support for browser-based wallets
 * 
 * Free tier: 100K requests/day, 1GB KV storage, 1K writes/day
 */

const PEER_TTL = 600; // seconds before peer is considered stale
const MAX_PEERS = 10000; // max peers in KV

// CORS headers for cross-origin requests
const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Content-Type': 'application/json',
};

export default {
  async fetch(request, env, ctx) {
    // Handle CORS preflight
    if (request.method === 'OPTIONS') {
      return new Response(null, { status: 204, headers: CORS_HEADERS });
    }

    const url = new URL(request.url);
    const path = url.pathname;

    try {
      if (path === '/register' && request.method === 'POST') {
        return await handleRegister(request, env);
      } else if (path === '/unregister' && request.method === 'POST') {
        return await handleUnregister(request, env);
      } else if (path === '/peers' && request.method === 'GET') {
        return await handlePeers(request, url, env);
      } else if (path === '/stats' && request.method === 'GET') {
        return await handleStats(env);
      } else if (path === '/health' && request.method === 'GET') {
        return handleHealth();
      } else {
        return jsonResponse({ error: 'not found' }, 404);
      }
    } catch (err) {
      console.error('SkyNet Beacon error:', err);
      return jsonResponse({ error: 'internal error' }, 500);
    }
  }
};

async function handleRegister(request, env) {
  const body = await request.json();
  const { node_id, host, port, services, user_agent } = body;

  if (!node_id || !host || !port) {
    return jsonResponse({ error: 'node_id, host, and port are required' }, 400);
  }

  const peer = {
    node_id,
    host,
    port,
    services: services || 0,
    user_agent: user_agent || '',
    last_seen: Date.now() / 1000,
  };

  // Store peer in KV
  await env.SKYNET_KV.put(`peer:${node_id}`, JSON.stringify(peer));
  
  // Add to index
  const index = await env.SKYNET_KV.get('peer_index') || '[]';
  let peers = JSON.parse(index);
  peers = peers.filter(id => id !== node_id);
  peers.unshift(node_id);
  if (peers.length > MAX_PEERS) {
    peers = peers.slice(0, MAX_PEERS);
  }
  await env.SKYNET_KV.put('peer_index', JSON.stringify(peers));

  console.log(`Registered peer ${node_id} at ${host}:${port}`);
  return jsonResponse({ status: 'ok', peer });
}

async function handleUnregister(request, env) {
  const body = await request.json();
  const { node_id } = body;

  if (!node_id) {
    return jsonResponse({ error: 'node_id is required' }, 400);
  }

  // Remove from KV
  await env.SKYNET_KV.delete(`peer:${node_id}`);
  
  // Remove from index
  const index = await env.SKYNET_KV.get('peer_index') || '[]';
  let peers = JSON.parse(index);
  peers = peers.filter(id => id !== node_id);
  await env.SKYNET_KV.put('peer_index', JSON.stringify(peers));

  console.log(`Unregistered peer ${node_id}`);
  return jsonResponse({ status: 'ok' });
}

async function handlePeers(request, url, env) {
  const limit = parseInt(url.searchParams.get('limit') || '8');
  
  const index = await env.SKYNET_KV.get('peer_index') || '[]';
  let peer_ids = JSON.parse(index);

  const now = Date.now() / 1000;
  const peers = [];

  // Fetch peers (limit to avoid too many KV reads)
  const to_fetch = peer_ids.slice(0, Math.min(limit * 2, 100));
  
  for (const node_id of to_fetch) {
    if (peers.length >= limit) break;
    
    const data = await env.SKYNET_KV.get(`peer:${node_id}`);
    if (!data) continue;
    
    const peer = JSON.parse(data);
    
    // Skip stale peers
    if (now - peer.last_seen > PEER_TTL) {
      // Clean up stale peer
      await env.SKYNET_KV.delete(`peer:${node_id}`);
      continue;
    }

    peers.push({
      node_id: peer.node_id,
      host: peer.host,
      port: peer.port,
      services: peer.services,
    });
  }

  return jsonResponse({ peers });
}

async function handleStats(env) {
  const index = await env.SKYNET_KV.get('peer_index') || '[]';
  const peer_ids = JSON.parse(index);
  
  const now = Date.now() / 1000;
  let active = 0;

  // Check a sample of peers for activity
  for (const node_id of peer_ids.slice(0, 50)) {
    const data = await env.SKYNET_KV.get(`peer:${node_id}`);
    if (data) {
      const peer = JSON.parse(data);
      if (now - peer.last_seen < PEER_TTL) {
        active++;
      }
    }
  }

  return jsonResponse({
    beacon: 'SkyNet Temporal Node Beacon',
    version: '1.0.0',
    peers_registered: peer_ids.length,
    peers_active_estimate: active,
    peer_ttl: PEER_TTL,
    timestamp: now,
  });
}

function handleHealth() {
  return jsonResponse({
    status: 'healthy',
    beacon: 'SkyNet Temporal Node Beacon',
    timestamp: Date.now() / 1000,
  });
}

function jsonResponse(data, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: CORS_HEADERS,
  });
}
