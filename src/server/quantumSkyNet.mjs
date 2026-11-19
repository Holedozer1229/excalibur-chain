/**
 * quantumSkyNet.mjs — SkyNet Quantum WebRTC Mesh & Browser-Native Data Channel Hub
 *
 * Implements browser-native P2P mesh data channels for the Excalibur Chain.
 * Allows Web browser nodes and headless instances to establish direct, low-latency,
 * encrypted peer-to-peer data channels for EREPR quantum gossip and Caduceus state tunnels.
 *
 * Protocol:
 *   - Channel label: "excal-p2p-v1"
 *   - Magic: 0x5843414c (ASCII 'XCAL')
 *   - Message Framing: Magic(4) + Command(12) + Length(4) + Payload(N) + Checksum(4)
 *   - ICE / SDP Signaling: Dual REST & WebSocket fallback
 *
 * Author: Travis Dale Jones
 */

import http from 'http';
import { createHash, randomBytes } from 'crypto';
import { EventEmitter } from 'events';

export const P2P_MAGIC = Buffer.from('XCAL');
export const DATA_CHANNEL_LABEL = 'excal-p2p-v1';
export const DEFAULT_PORT = 9436;
export const MAX_SIGNAL_BODY_BYTES = 64 * 1024;
export const MAX_SIGNAL_PEERS = 256;
export const MAX_CANDIDATES_PER_PEER = 64;

/**
 * Encodes a message for transmission over WebRTC Data Channel or TCP/WS.
 */
export function encodeFrame(command, payload = Buffer.alloc(0)) {
  const cmdBuf = Buffer.alloc(12, 0);
  cmdBuf.write(command.slice(0, 12), 'utf-8');

  const payloadBuf = Buffer.isBuffer(payload) ? payload : Buffer.from(payload);
  const lenBuf = Buffer.alloc(4);
  lenBuf.writeUInt32BE(payloadBuf.length, 0);

  const hash = createHash('sha256').update(payloadBuf).digest();
  const checksum = hash.subarray(0, 4);

  return Buffer.concat([P2P_MAGIC, cmdBuf, lenBuf, payloadBuf, checksum]);
}

/**
 * Decodes a binary frame received from WebRTC Data Channel.
 */
export function decodeFrame(buf) {
  if (buf.length < 24) return null; // Minimum header: 4 + 12 + 4 + 4

  const magic = buf.subarray(0, 4);
  if (!magic.equals(P2P_MAGIC)) {
    throw new Error('Invalid magic bytes in frame');
  }

  const command = buf.subarray(4, 16).toString('utf-8').replace(/\0/g, '').trim();
  const length = buf.readUInt32BE(16);

  if (buf.length < 24 + length) return null; // Incomplete frame

  const payload = buf.subarray(20, 20 + length);
  const checksum = buf.subarray(20 + length, 24 + length);

  const expectedHash = createHash('sha256').update(payload).digest().subarray(0, 4);
  if (!checksum.equals(expectedHash)) {
    throw new Error('Payload checksum mismatch');
  }

  return {
    command,
    payload,
    totalBytes: 24 + length,
  };
}

/**
 * WebRTC Mesh Peer Connection wrapper
 */
export class WebRTCMeshPeer extends EventEmitter {
  constructor(peerId, signalingHub) {
    super();
    this.peerId = peerId;
    this.hub = signalingHub;
    this.pc = null;
    this.dataChannel = null;
    this.status = 'initializing';
    this.rxBuffer = Buffer.alloc(0);
    this.connectedAt = null;
    this.bytesReceived = 0;
    this.bytesSent = 0;
  }

  attachDataChannel(channel) {
    this.dataChannel = channel;
    this.dataChannel.binaryType = 'arraybuffer';

    this.dataChannel.onopen = () => {
      this.status = 'connected';
      this.connectedAt = Date.now();
      this.emit('connected', this);
      this.send('ping', Buffer.from(JSON.stringify({ timestamp: Date.now() })));
    };

    this.dataChannel.onclose = () => {
      this.status = 'closed';
      this.emit('disconnected', this);
    };

    this.dataChannel.onerror = (err) => {
      this.emit('error', err);
    };

    this.dataChannel.onmessage = (event) => {
      const data = Buffer.from(event.data);
      this.bytesReceived += data.length;
      this.rxBuffer = Buffer.concat([this.rxBuffer, data]);

      while (this.rxBuffer.length >= 24) {
        try {
          const frame = decodeFrame(this.rxBuffer);
          if (!frame) break;
          this.rxBuffer = this.rxBuffer.subarray(frame.totalBytes);
          this.emit('frame', frame.command, frame.payload, this);
        } catch (err) {
          this.emit('error', err);
          this.rxBuffer = Buffer.alloc(0);
          break;
        }
      }
    };
  }

  send(command, payload = Buffer.alloc(0)) {
    if (this.dataChannel && this.dataChannel.readyState === 'open') {
      const frame = encodeFrame(command, payload);
      this.dataChannel.send(frame);
      this.bytesSent += frame.length;
      return true;
    }
    return false;
  }

  close() {
    this.status = 'closed';
    if (this.dataChannel) {
      try { this.dataChannel.close(); } catch (_) {}
    }
    if (this.pc) {
      try { this.pc.close(); } catch (_) {}
    }
  }
}

/**
 * QuantumSkyNetHub — Mesh Signaling and WebRTC Manager
 */
export class QuantumSkyNetHub extends EventEmitter {
  constructor(options = {}) {
    super();
    this.nodeId = options.nodeId || randomBytes(16).toString('hex');
    this.port = options.port || DEFAULT_PORT;
    // Keep the unauthenticated signaling endpoint local by default. Deployments
    // that intentionally expose it must configure a protected reverse proxy.
    this.host = options.host || process.env.EXCAL_SIGNAL_HOST || '127.0.0.1';
    this.peers = new Map();
    this.pendingOffers = new Map();
    this.candidates = new Map();
    this.server = null;
  }

  start() {
    this.server = http.createServer((req, res) => this.handleHttpRequest(req, res));
    return new Promise((resolve, reject) => {
      this.server.listen(this.port, this.host, () => {
        resolve({
          nodeId: this.nodeId,
          port: this.port,
          host: this.host,
        });
      });
      this.server.on('error', reject);
    });
  }

  stop() {
    for (const peer of this.peers.values()) {
      peer.close();
    }
    this.peers.clear();
    if (this.server) {
      return new Promise((resolve) => this.server.close(resolve));
    }
    return Promise.resolve();
  }

  broadcast(command, payload) {
    let sentCount = 0;
    for (const peer of this.peers.values()) {
      if (peer.send(command, payload)) {
        sentCount++;
      }
    }
    return sentCount;
  }

  handleHttpRequest(req, res) {
    // CORS headers for browser-native dApp integration
    res.setHeader('Access-Control-Allow-Origin', '*');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

    if (req.method === 'OPTIONS') {
      res.writeHead(204);
      res.end();
      return;
    }

    const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);

    if (url.pathname === '/health' && req.method === 'GET') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        status: 'online',
        nodeId: this.nodeId,
        peerCount: this.peers.size,
        dataChannel: DATA_CHANNEL_LABEL,
        peers: Array.from(this.peers.values()).map((p) => ({
          peerId: p.peerId,
          status: p.status,
          bytesSent: p.bytesSent,
          bytesReceived: p.bytesReceived,
          connectedAt: p.connectedAt,
        })),
      }, null, 2));
      return;
    }

    if (url.pathname === '/webrtc/signal/offer' && req.method === 'POST') {
      this.readJsonBody(req, (err, body) => {
        if (err || !body || typeof body.peerId !== 'string' ||
            body.peerId.length < 1 || body.peerId.length > 128 ||
            typeof body.sdp !== 'string' || body.sdp.length < 1 ||
            Buffer.byteLength(body.sdp, 'utf8') > 48 * 1024) {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'Invalid offer payload. Required: peerId, sdp' }));
          return;
        }

        if (!this.peers.has(body.peerId) && this.peers.size >= MAX_SIGNAL_PEERS) {
          res.writeHead(429, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'Signaling peer capacity reached' }));
          return;
        }
        const peer = new WebRTCMeshPeer(body.peerId, this);
        this.peers.set(body.peerId, peer);
        this.pendingOffers.set(body.peerId, body.sdp);

        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          status: 'offer_received',
          targetNodeId: this.nodeId,
          peerId: body.peerId,
        }));
      });
      return;
    }

    if (url.pathname === '/webrtc/signal/candidate' && req.method === 'POST') {
      this.readJsonBody(req, (err, body) => {
        if (err || !body || typeof body.peerId !== 'string' ||
            body.peerId.length < 1 || body.peerId.length > 128 ||
            typeof body.candidate !== 'string' || body.candidate.length < 1 ||
            Buffer.byteLength(body.candidate, 'utf8') > 4096) {
          res.writeHead(400, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'Invalid candidate payload. Required: peerId, candidate' }));
          return;
        }

        if (!this.peers.has(body.peerId)) {
          res.writeHead(404, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'Unknown signaling peer' }));
          return;
        }
        if (!this.candidates.has(body.peerId)) {
          this.candidates.set(body.peerId, []);
        }
        const queue = this.candidates.get(body.peerId);
        if (queue.length >= MAX_CANDIDATES_PER_PEER) {
          res.writeHead(429, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ error: 'Candidate queue capacity reached' }));
          return;
        }
        queue.push(body.candidate);

        res.writeHead(200, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({ status: 'candidate_queued' }));
      });
      return;
    }

    res.writeHead(404, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({ error: 'Endpoint not found' }));
  }

  readJsonBody(req, callback) {
    let raw = '';
    let received = 0;
    let finished = false;
    const finish = (err, value) => {
      if (finished) return;
      finished = true;
      callback(err, value);
    };
    req.on('data', (chunk) => {
      received += chunk.length;
      if (received > MAX_SIGNAL_BODY_BYTES) {
        finish(new Error('Request body too large'), null);
        req.destroy();
        return;
      }
      raw += chunk;
    });
    req.on('end', () => {
      if (finished) return;
      try {
        const json = JSON.parse(raw);
        if (!json || typeof json !== 'object' || Array.isArray(json)) {
          throw new Error('JSON body must be an object');
        }
        finish(null, json);
      } catch (err) {
        finish(err, null);
      }
    });
    req.on('error', (err) => finish(err, null));
  }
}

// Standalone execution entrypoint
if (process.argv[1] && process.argv[1].endsWith('quantumSkyNet.mjs')) {
  const hub = new QuantumSkyNetHub();
  hub.start().then((info) => {
    console.log(`[QuantumSkyNet] WebRTC Mesh Hub active on port ${info.port} (Node: ${info.nodeId})`);
  }).catch((err) => {
    console.error('[QuantumSkyNet] Startup failed:', err);
    process.exit(1);
  });
}
