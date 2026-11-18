// Excalibur JSON-RPC Proxy
// Server-side proxy that forwards requests to the local Excalibur node
// Keeps the node endpoint private and handles CORS for browser clients

const http = require('http');

// Configuration
const EXCALIBUR_RPC_URL = process.env.EXCALIBUR_RPC_URL || 'http://127.0.0.1:9332';
const TIMEOUT = parseInt(process.env.EXCALIBUR_RPC_TIMEOUT) || 30000;

// Parse the Excalibur URL
const url = new URL(EXCALIBUR_RPC_URL);
const targetHost = url.hostname;
const targetPort = url.port || (url.protocol === 'https:' ? 443 : 8080);
const targetProtocol = url.protocol === 'https:' ? require('https') : http;

// Allowed RPC methods (whitelist for security)
const ALLOWED_METHODS = new Set([
  'getblockcount',
  'getblockhash',
  'getblock',
  'getbalance',
  'getmempoolinfo',
  'getrawmempool',
  'getpeerinfo',
  'getnetworkinfo',
  'getmininginfo',
  'generate',
  'sendrawtransaction',
  'getrawtransaction',
  'ping',
]);

function proxyRequest(body) {
  return new Promise((resolve, reject) => {
    const postData = JSON.stringify(body);

    const options = {
      hostname: targetHost,
      port: targetPort,
      path: '/',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(postData),
      },
      timeout: TIMEOUT,
    };

    const req = targetProtocol.request(options, (res) => {
      let data = '';

      res.on('data', (chunk) => {
        data += chunk;
      });

      res.on('end', () => {
        try {
          const response = JSON.parse(data);
          resolve({ statusCode: res.statusCode, data: response });
        } catch (e) {
          reject(new Error(`Invalid JSON response from Excalibur node: ${data}`));
        }
      });
    });

    req.on('error', (error) => {
      reject(new Error(`Excalibur node unreachable: ${error.message}`));
    });

    req.on('timeout', () => {
      req.destroy();
      reject(new Error(`Request to Excalibur node timed out after ${TIMEOUT}ms`));
    });

    req.write(postData);
    req.end();
  });
}

function handleRequest(req, res) {
  // Set CORS headers
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  // Handle preflight requests
  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    res.end();
    return;
  }

  // Only allow POST requests
  if (req.method !== 'POST') {
    res.writeHead(405, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      jsonrpc: '2.0',
      error: { code: -32601, message: 'Method not allowed' },
      id: null,
    }));
    return;
  }

  // Read request body
  let body = '';

  req.on('data', (chunk) => {
    body += chunk;
  });

  req.on('end', async () => {
    try {
      // Parse JSON-RPC request
      let request;
      try {
        request = JSON.parse(body);
      } catch (e) {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          jsonrpc: '2.0',
          error: { code: -32700, message: 'Invalid JSON' },
          id: null,
        }));
        return;
      }

      // Validate JSON-RPC structure
      if (!request.jsonrpc || request.jsonrpc !== '2.0') {
        res.writeHead(400, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          jsonrpc: '2.0',
          error: { code: -32600, message: 'Invalid Request' },
          id: request.id || null,
        }));
        return;
      }

      // Check if method is allowed
      if (!request.method || !ALLOWED_METHODS.has(request.method)) {
        res.writeHead(403, { 'Content-Type': 'application/json' });
        res.end(JSON.stringify({
          jsonrpc: '2.0',
          error: { code: -32601, message: `Method not allowed: ${request.method || 'unknown'}` },
          id: request.id || null,
        }));
        return;
      }

      // Forward to Excalibur node
      const result = await proxyRequest(request);

      // Return the response
      res.writeHead(result.statusCode, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify(result.data));
    } catch (error) {
      console.error('Proxy error:', error.message);

      res.writeHead(502, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({
        jsonrpc: '2.0',
        error: { code: -32000, message: error.message },
        id: null,
      }));
    }
  });

  req.on('error', (error) => {
    console.error('Request error:', error.message);
    res.writeHead(500, { 'Content-Type': 'application/json' });
    res.end(JSON.stringify({
      jsonrpc: '2.0',
      error: { code: -32000, message: 'Internal server error' },
      id: null,
    }));
  });
}

// Health check endpoint
function healthCheck(req, res) {
  res.setHeader('Content-Type', 'application/json');
  res.writeHead(200);
  res.end(JSON.stringify({
    status: 'ok',
    target: EXCALIBUR_RPC_URL,
    allowedMethods: Array.from(ALLOWED_METHODS),
  }));
}

// Create server
const server = http.createServer((req, res) => {
  // Route to health check
  if (req.url === '/health' && req.method === 'GET') {
    healthCheck(req, res);
    return;
  }

  // Route to proxy
  if (req.url === '/' || req.url === '/api/excalibur-rpc') {
    handleRequest(req, res);
    return;
  }

  // 404 for unknown routes
  res.writeHead(404, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({
    error: 'Not found',
  }));
});

// Start server
const PORT = parseInt(process.env.EXCALIBUR_PROXY_PORT) || 3000;
server.listen(PORT, () => {
  console.log(`Excalibur RPC proxy listening on port ${PORT}`);
  console.log(`Forwarding to: ${EXCALIBUR_RPC_URL}`);
  console.log(`Allowed methods: ${Array.from(ALLOWED_METHODS).join(', ')}`);
});

// Handle graceful shutdown
process.on('SIGTERM', () => {
  console.log('SIGTERM received, shutting down...');
  server.close(() => {
    console.log('Server closed');
    process.exit(0);
  });
});

process.on('SIGINT', () => {
  console.log('SIGINT received, shutting down...');
  server.close(() => {
    console.log('Server closed');
    process.exit(0);
  });
});

module.exports = { handleRequest, proxyRequest, ALLOWED_METHODS };
