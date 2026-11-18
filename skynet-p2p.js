/**
 * AetherionEXCAL SkyNet P2P — Node.js Implementation
 * 
 * Cross-platform P2P node that works alongside the Python beacon.
 * Uses the same Stratum protocol and REST API for peer discovery.
 * 
 * Usage:
 *   node skynet-p2p.js
 *   node skynet-p2p.js --port 9433 --beacon http://localhost:9435
 * 
 * Features:
 *   - HTTP REST API for peer discovery
 *   - UDP multicast/broadcast for LAN discovery
 *   - WebSocket support for real-time peer updates
 *   - Compatible with Python beacon and wallet
 */

const http = require('http');
const dgram = require('dgram');
const crypto = require('crypto');
const { WebSocketServer } = require('ws');

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

const DEFAULT_PORT = 9433;
const DEFAULT_BEACON_PORT = 9435;
const MULTICAST_GROUP = '239.1.1.1';
const MULTICAST_PORT = 9436;
const BROADCAST_PORT = 9437;
const BROADCAST_ADDRESS = '255.255.255.255';
const PEER_TTL = 600; // seconds
const HEARTBEAT_INTERVAL = 60000; // ms

// ---------------------------------------------------------------------------
// SkyNet P2P Node
// ---------------------------------------------------------------------------

class SkyNetNode {
    constructor(options = {}) {
        this.port = options.port || DEFAULT_PORT;
        this.beaconUrl = options.beacon || `http://localhost:${DEFAULT_BEACON_PORT}`;
        this.nodeId = crypto.randomUUID();
        this.host = this._getLocalIP();
        this.peers = new Map(); // nodeId -> {host, port, lastSeen, services}
        this.httpServer = null;
        this.wsServer = null;
        this.multicastSocket = null;
        this.broadcastSocket = null;
        this.heartbeatTimer = null;
        this.running = false;
        
        console.log('='.repeat(50));
        console.log('  AetherionEXCAL SkyNet P2P (Node.js)');
        console.log('='.repeat(50));
        console.log(`  Node ID:  ${this.nodeId}`);
        console.log(`  Host:     ${this.host}`);
        console.log(`  Port:     ${this.port}`);
        console.log(`  Beacon:   ${this.beaconUrl}`);
        console.log('='.repeat(50));
    }
    
    _getLocalIP() {
        const interfaces = require('os').networkInterfaces();
        for (const name of Object.keys(interfaces)) {
            for (const iface of interfaces[name]) {
                if (iface.family === 'IPv4' && !iface.internal) {
                    return iface.address;
                }
            }
        }
        return '127.0.0.1';
    }
    
    start() {
        this.running = true;
        
        // Start HTTP server
        this._startHTTP();
        
        // Start WebSocket server
        this._startWebSocket();
        
        // Start multicast listener
        this._startMulticast();
        
        // Start broadcast listener
        this._startBroadcast();
        
        // Register with beacon
        this._registerWithBeacon();
        
        // Start heartbeat
        this.heartbeatTimer = setInterval(() => {
            this._heartbeat();
        }, HEARTBEAT_INTERVAL);
        
        console.log(`\nSkyNet P2P node started on port ${this.port}`);
        console.log(`Discover peers: ${this.beaconUrl}/peers\n`);
    }
    
    stop() {
        this.running = false;
        
        if (this.heartbeatTimer) {
            clearInterval(this.heartbeatTimer);
        }
        if (this.httpServer) {
            this.httpServer.close();
        }
        if (this.wsServer) {
            this.wsServer.close();
        }
        if (this.multicastSocket) {
            this.multicastSocket.close();
        }
        if (this.broadcastSocket) {
            this.broadcastSocket.close();
        }
        
        console.log('SkyNet P2P node stopped');
    }
    
    _startHTTP() {
        this.httpServer = http.createServer((req, res) => {
            const url = new URL(req.url, `http://localhost:${this.port}`);
            
            res.setHeader('Content-Type', 'application/json');
            res.setHeader('Access-Control-Allow-Origin', '*');
            
            if (req.method === 'GET') {
                if (url.pathname === '/peers') {
                    const limit = parseInt(url.searchParams.get('limit') || '8');
                    const peers = this._getPeers(limit);
                    res.end(JSON.stringify({ peers, count: peers.length }));
                } else if (url.pathname === '/stats') {
                    res.end(JSON.stringify(this._getStats()));
                } else if (url.pathname === '/health') {
                    res.end(JSON.stringify({
                        status: 'ok',
                        node_id: this.nodeId,
                        host: this.host,
                        port: this.port,
                    }));
                } else {
                    res.statusCode = 404;
                    res.end(JSON.stringify({ error: 'not found' }));
                }
            } else if (req.method === 'POST') {
                let body = '';
                req.on('data', chunk => body += chunk);
                req.on('end', () => {
                    try {
                        const data = JSON.parse(body);
                        
                        if (url.pathname === '/register') {
                            this._addPeer(
                                data.node_id,
                                data.host,
                                data.port || 9433,
                                data.services || 0
                            );
                            res.end(JSON.stringify({ status: 'ok' }));
                        } else if (url.pathname === '/unregister') {
                            this.peers.delete(data.node_id);
                            res.end(JSON.stringify({ status: 'ok' }));
                        } else {
                            res.statusCode = 404;
                            res.end(JSON.stringify({ error: 'not found' }));
                        }
                    } catch (e) {
                        res.statusCode = 400;
                        res.end(JSON.stringify({ error: e.message }));
                    }
                });
            } else {
                res.statusCode = 405;
                res.end(JSON.stringify({ error: 'method not allowed' }));
            }
        });
        
        this.httpServer.listen(this.port, () => {
            console.log(`HTTP server listening on port ${this.port}`);
        });
    }
    
    _startWebSocket() {
        this.wsServer = new WebSocketServer({ server: this.httpServer });
        
        this.wsServer.on('connection', (ws) => {
            console.log('WebSocket client connected');
            
            // Send current peers
            ws.send(JSON.stringify({
                type: 'peers',
                peers: this._getPeers(32),
            }));
            
            ws.on('message', (message) => {
                try {
                    const data = JSON.parse(message);
                    
                    if (data.type === 'register') {
                        this._addPeer(data.node_id, data.host, data.port, data.services);
                        ws.send(JSON.stringify({
                            type: 'peers',
                            peers: this._getPeers(8),
                        }));
                    }
                } catch (e) {
                    console.error('WebSocket message error:', e);
                }
            });
            
            ws.on('close', () => {
                console.log('WebSocket client disconnected');
            });
        });
    }
    
    _startMulticast() {
        try {
            this.multicastSocket = dgram.createSocket('udp4');
            this.multicastSocket.setMulticastTTL(32);
            this.multicastSocket.addMembership(MULTICAST_GROUP);
            this.multicastSocket.bind(MULTICAST_PORT, () => {
                console.log(`Multicast listener on ${MULTICAST_GROUP}:${MULTICAST_PORT}`);
            });
            
            this.multicastSocket.on('message', (msg, rinfo) => {
                this._handleUDPMessage(msg, rinfo);
            });
        } catch (e) {
            console.warn(`Failed to start multicast: ${e.message}`);
        }
    }
    
    _startBroadcast() {
        try {
            this.broadcastSocket = dgram.createSocket('udp4');
            this.broadcastSocket.bind(BROADCAST_PORT, () => {
                console.log(`Broadcast listener on port ${BROADCAST_PORT}`);
            });
            
            this.broadcastSocket.on('message', (msg, rinfo) => {
                this._handleUDPMessage(msg, rinfo);
            });
        } catch (e) {
            console.warn(`Failed to start broadcast: ${e.message}`);
        }
    }
    
    _handleUDPMessage(msg, rinfo) {
        try {
            const data = JSON.parse(msg.toString());
            
            if (data.type === 'register') {
                this._addPeer(data.node_id, data.host, data.port || 9433, data.services || 0);
                
                // Respond with known peers
                const response = JSON.stringify({
                    type: 'peers',
                    peers: this._getPeers(8),
                });
                
                try {
                    const sock = dgram.createSocket('udp4');
                    sock.send(response, 0, response.length, data.port || 9433, data.host);
                    sock.close();
                } catch (e) {}
            } else if (data.type === 'heartbeat') {
                const peer = this.peers.get(data.node_id);
                if (peer) {
                    peer.lastSeen = Date.now() / 1000;
                }
            }
        } catch (e) {
            // Ignore invalid messages
        }
    }
    
    _addPeer(nodeId, host, port, services = 0) {
        if (!nodeId || nodeId === this.nodeId) return;
        
        this.peers.set(nodeId, {
            node_id: nodeId,
            host,
            port,
            services,
            lastSeen: Date.now() / 1000,
        });
        
        // Notify WebSocket clients
        if (this.wsServer) {
            const msg = JSON.stringify({
                type: 'peer_joined',
                peer: { node_id: nodeId, host, port },
            });
            this.wsServer.clients.forEach(client => {
                if (client.readyState === 1) {
                    client.send(msg);
                }
            });
        }
    }
    
    _getPeers(limit = 8) {
        const now = Date.now() / 1000;
        const peers = [];
        
        for (const [nodeId, peer] of this.peers) {
            if (now - peer.lastSeen < PEER_TTL) {
                peers.push({
                    node_id: peer.node_id,
                    host: peer.host,
                    port: peer.port,
                    services: peer.services,
                });
            }
        }
        
        peers.sort((a, b) => b.lastSeen - a.lastSeen);
        return peers.slice(0, limit);
    }
    
    _getStats() {
        const now = Date.now() / 1000;
        const active = Array.from(this.peers.values())
            .filter(p => now - p.lastSeen < PEER_TTL).length;
        
        return {
            node_id: this.nodeId,
            host: this.host,
            port: this.port,
            peers_registered: this.peers.size,
            peers_active: active,
            running: this.running,
        };
    }
    
    _registerWithBeacon() {
        const data = JSON.stringify({
            node_id: this.nodeId,
            host: this.host,
            port: this.port,
            services: 1,
            user_agent: '/SkyNet-NodeJS:1.0/',
        });
        
        const options = {
            hostname: new URL(this.beaconUrl).hostname,
            port: new URL(this.beaconUrl).port,
            path: '/register',
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        };
        
        const req = http.request(options, (res) => {
            let body = '';
            res.on('data', chunk => body += chunk);
            res.on('end', () => {
                try {
                    const result = JSON.parse(body);
                    if (result.status === 'ok') {
                        console.log(`Registered with beacon: ${this.beaconUrl}`);
                    }
                } catch (e) {}
            });
        });
        
        req.on('error', (e) => {
            console.warn(`Beacon registration failed: ${e.message}`);
        });
        
        req.write(data);
        req.end();
    }
    
    _heartbeat() {
        // Broadcast heartbeat
        const msg = JSON.stringify({
            type: 'heartbeat',
            node_id: this.nodeId,
            host: this.host,
            port: this.port,
        });
        
        // Multicast
        try {
            const sock = dgram.createSocket('udp4');
            sock.setMulticastTTL(32);
            sock.send(msg, 0, msg.length, MULTICAST_PORT, MULTICAST_GROUP);
            sock.close();
        } catch (e) {}
        
        // LAN broadcast
        try {
            const sock = dgram.createSocket('udp4');
            sock.send(msg, 0, msg.length, BROADCAST_PORT, BROADCAST_ADDRESS);
            sock.close();
        } catch (e) {}
        
        // Re-register with beacon
        this._registerWithBeacon();
    }
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main() {
    const args = process.argv.slice(2);
    const options = {};
    
    for (let i = 0; i < args.length; i++) {
        if (args[i] === '--port' && args[i + 1]) {
            options.port = parseInt(args[++i]);
        } else if (args[i] === '--beacon' && args[i + 1]) {
            options.beacon = args[++i];
        }
    }
    
    const node = new SkyNetNode(options);
    node.start();
    
    process.on('SIGINT', () => {
        console.log('\nShutting down...');
        node.stop();
        process.exit(0);
    });
    
    process.on('SIGTERM', () => {
        node.stop();
        process.exit(0);
    });
}

main();
