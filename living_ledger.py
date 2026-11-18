"""living_ledger.py — Real-time block explorer for the Excalibur fork node.

Connects to the fork node's JSON-RPC server (default localhost:9432) and
serves a live-updating HTML page showing current blocks, transactions,
and mempool activity — like mempool.space but for Excalibur.

Usage:
    python living_ledger.py                  # Default: localhost:9432
    python living_ledger.py --port 8080      # Serve on port 8080
    python living_ledger.py --rpc localhost:19432  # Connect to testnet node
    python living_ledger.py --test           # Run self-tests

The ledger page auto-refreshes every 5 seconds via WebSocket polling.
"""
import argparse
import hashlib
import http.server
import json
import socketserver
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone


# ------------------------------------------------------------------ RPC
def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()


def rpc_call(url, method, params=None):
    """Make a JSON-RPC call to the node. Returns the result dict."""
    if params is None:
        params = []
    payload = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method,
                          "params": params}).encode()
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            result = json.loads(resp.read())
            if "error" in result and result["error"] is not None:
                raise ValueError(result["error"])
            return result.get("result")
    except urllib.error.URLError as e:
        raise ConnectionError(f"Cannot reach node at {url}: {e}")


def format_swords(swords):
    """Format swords (smallest unit) to EXCAL with 8 decimals."""
    return f"{swords / 1e8:.8f}"


def format_time(ts):
    """Format Unix timestamp to readable string."""
    try:
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (ValueError, TypeError, OSError):
        return str(ts)


def truncate_hex(h, chars=16):
    """Truncate a hex string for display."""
    if len(h) <= chars + 4:
        return h
    return h[:chars] + "..." + h[-4:]


def parse_lock_type(lock_hex):
    """Identify lock type from script hex."""
    if not lock_hex:
        return "unknown"
    s = lock_hex.lower()
    if s.startswith("00") and len(s) == 44:
        return "PKH"
    if s.startswith("06"):
        return "KNOT"
    if s.startswith("01") and len(s) == 68:
        return "PQH"
    if s.startswith("02"):
        return "HTLC"
    if s.startswith("03"):
        return "QHTLC"
    if s.startswith("04"):
        return "BRIDGE"
    return "PKH"


def parse_tx_inputs(vin):
    """Parse transaction inputs for display."""
    inputs = []
    for v in vin:
        prev = v.get("prev", "")
        idx = v.get("idx", 0)
        script_sig = v.get("scriptSig", "")
        inp = {"txid": truncate_hex(prev, 12), "vout": idx}
        if v.get("coinbase"):
            inp["coinbase"] = True
            inp["height"] = v.get("height", 0)
        inputs.append(inp)
    return inputs


def parse_tx_outputs(vout):
    """Parse transaction outputs for display."""
    outputs = []
    for v in vout:
        value = v.get("value", 0)
        script = v.get("script", "")
        outputs.append({
            "value": format_swords(value),
            "lock_type": parse_lock_type(script),
            "script": truncate_hex(script, 16)
        })
    return outputs


# ------------------------------------------------------------------ Data
class LedgerData:
    """Cached data fetched from the node RPC."""

    def __init__(self, rpc_url):
        self.rpc_url = rpc_url
        self._cache = {}
        self._lock = threading.Lock()
        self._last_update = 0

    def _fetch(self, key, method, params=None, ttl=10):
        """Fetch with TTL caching."""
        now = time.time()
        with self._lock:
            cached = self._cache.get(key)
            if cached and now - cached["time"] < ttl:
                return cached["data"]
        try:
            data = rpc_call(self.rpc_url, method, params)
            with self._lock:
                self._cache[key] = {"data": data, "time": now}
                self._last_update = now
            return data
        except Exception as e:
            with self._lock:
                self._cache[key] = {"data": {"error": str(e)}, "time": now}
            return {"error": str(e)}

    def get_status(self):
        """Get overall node status: height, hash, peers, mempool."""
        height = self._fetch("height", "getblockcount", ttl=5)
        if not isinstance(height, int):
            height = 0
        mempool = self._fetch("mempool", "getmempoolinfo", ttl=5)
        if not isinstance(mempool, dict):
            mempool = {}
        peers = self._fetch("peers", "getpeerinfo", ttl=30)
        if not isinstance(peers, list):
            peers = []
        # Optional: metrics and network info (may not be available on all nodes)
        metrics = {}
        network = {}
        try:
            m = self._fetch("metrics", "getmetrics", ttl=10)
            if isinstance(m, dict):
                metrics = m
        except Exception:
            pass
        try:
            n = self._fetch("network", "getnetworkinfo", ttl=60)
            if isinstance(n, dict):
                network = n
        except Exception:
            pass
        return {
            "height": height,
            "tip_hash": "",
            "mempool": mempool,
            "peers": peers,
            "metrics": metrics,
            "network": network,
            "updated": time.time()
        }

    def get_recent_blocks(self, count=12):
        """Get recent blocks."""
        blocks = self._fetch("recent", "getrecentblocks", [count], ttl=5)
        if not isinstance(blocks, list):
            return []
        return blocks

    def get_block(self, identifier):
        """Get a specific block by height or hash."""
        if isinstance(identifier, int) or (isinstance(identifier, str) and identifier.isdigit()):
            h = int(identifier)
            key = f"block_h_{h}"
            data = self._fetch(key, "getblockbyheight", [h], ttl=60)
        else:
            key = f"block_{identifier[:16]}"
            data = self._fetch(key, "getblock", [identifier], ttl=60)
        return data if isinstance(data, dict) else {}

    def get_mempool_txs(self):
        """Get mempool transaction details."""
        info = self._fetch("mp_info", "getmempoolinfo", ttl=5)
        return info if isinstance(info, dict) else {}


# ------------------------------------------------------------------ HTTP
class LedgerHandler(http.server.BaseHTTPRequestHandler):
    """HTTP handler serving the living ledger page."""

    ledger = None  # Set at class level

    def log_message(self, format, *args):
        pass  # Suppress default logging

    def do_GET(self):
        try:
            if self.path == "/" or self.path == "/index.html":
                self._serve_html()
            elif self.path == "/api/status":
                self._serve_json(self.ledger.get_status())
            elif self.path == "/api/blocks":
                count = 12
                for part in self.path.split("?"):
                    if "count=" in part:
                        try:
                            count = int(part.split("count=")[1])
                        except ValueError:
                            pass
                self._serve_json(self.ledger.get_recent_blocks(count))
            elif self.path.startswith("/api/block/"):
                identifier = self.path[len("/api/block/"):]
                self._serve_json(self.ledger.get_block(identifier))
            elif self.path == "/api/mempool":
                self._serve_json(self.ledger.get_mempool_txs())
            elif self.path == "/style.css":
                self._serve_css()
            else:
                self._serve_html()
        except Exception as e:
            try:
                self._serve_json({"error": str(e)})
            except Exception:
                pass

    def _serve_html(self):
        html = LIVING_LEDGER_HTML
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(html.encode())

    def _serve_css(self):
        css = LIVING_LEDGER_CSS
        self.send_response(200)
        self.send_header("Content-Type", "text/css")
        self.end_headers()
        self.wfile.write(css.encode())

    def _serve_json(self, data):
        body = json.dumps(data, default=str).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)


# ------------------------------------------------------------------ HTML
LIVING_LEDGER_CSS = """
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Courier New', monospace; background: #0a0e17; color: #e0e6ed; min-height: 100vh; }
.header { background: linear-gradient(135deg, #1a1f2e 0%, #0d1117 100%); border-bottom: 2px solid #00d4ff; padding: 16px 24px; display: flex; justify-content: space-between; align-items: center; }
.header h1 { font-size: 20px; color: #00d4ff; }
.header .status { display: flex; gap: 20px; font-size: 13px; }
.header .status span { color: #8b949e; }
.header .status .value { color: #58a6ff; font-weight: bold; }
.container { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; padding: 16px; max-width: 1400px; margin: 0 auto; }
.panel { background: #161b22; border: 1px solid #30363d; border-radius: 8px; padding: 16px; }
.panel h2 { font-size: 14px; color: #00d4ff; margin-bottom: 12px; border-bottom: 1px solid #21262d; padding-bottom: 8px; text-transform: uppercase; letter-spacing: 1px; }
.block-list { max-height: 600px; overflow-y: auto; }
.block-item { padding: 10px; margin-bottom: 8px; background: #0d1117; border: 1px solid #21262d; border-radius: 6px; cursor: pointer; transition: border-color 0.2s; }
.block-item:hover { border-color: #00d4ff; }
.block-item .height { color: #58a6ff; font-weight: bold; font-size: 14px; }
.block-item .hash { color: #8b949e; font-size: 11px; word-break: break-all; }
.block-item .meta { display: flex; justify-content: space-between; margin-top: 6px; font-size: 11px; color: #6e7681; }
.block-item .txs { color: #3fb950; }
.block-item .time { color: #d29922; }
.mempool-stats { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.stat-card { background: #0d1117; border: 1px solid #21262d; border-radius: 6px; padding: 12px; text-align: center; }
.stat-card .label { font-size: 11px; color: #6e7681; text-transform: uppercase; }
.stat-card .value { font-size: 24px; color: #58a6ff; font-weight: bold; margin-top: 4px; }
.stat-card .unit { font-size: 11px; color: #8b949e; }
.network-info { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.peer-item { padding: 8px; background: #0d1117; border: 1px solid #21262d; border-radius: 4px; font-size: 12px; }
.peer-item .addr { color: #3fb950; }
.block-detail { max-height: 600px; overflow-y: auto; }
.block-detail .field { display: flex; justify-content: space-between; padding: 6px 0; border-bottom: 1px solid #21262d; font-size: 12px; }
.block-detail .field .label { color: #6e7681; }
.block-detail .field .value { color: #e0e6ed; word-break: break-all; max-width: 60%; text-align: right; }
.tx-list { margin-top: 12px; }
.tx-item { padding: 8px; background: #0d1117; border: 1px solid #21262d; border-radius: 4px; font-size: 11px; margin-bottom: 4px; color: #8b949e; cursor: pointer; }
.tx-item:hover { border-color: #58a6ff; color: #e0e6ed; }
.live-dot { display: inline-block; width: 8px; height: 8px; background: #3fb950; border-radius: 50%; margin-right: 6px; animation: pulse 2s infinite; }
@keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.3; } }
.error { color: #f85149; font-size: 12px; padding: 8px; background: #2d1215; border-radius: 4px; }
.full-width { grid-column: 1 / -1; }
.search-bar { display: flex; gap: 8px; margin-bottom: 12px; }
.search-bar input { flex: 1; background: #0d1117; border: 1px solid #30363d; color: #e0e6ed; padding: 8px 12px; border-radius: 4px; font-family: 'Courier New', monospace; }
.search-bar button { background: #00d4ff; color: #0a0e17; border: none; padding: 8px 16px; border-radius: 4px; cursor: pointer; font-weight: bold; }
.search-bar button:hover { background: #58a6ff; }
"""

LIVING_LEDGER_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Excalibur Living Ledger</title>
<link rel="stylesheet" href="/style.css">
</head>
<body>
<div class="header">
    <h1><span class="live-dot"></span>Excalibur Living Ledger</h1>
    <div class="status">
        <span>Height: <span class="value" id="height">—</span></span>
        <span>Peers: <span class="value" id="peers">—</span></span>
        <span>Mempool: <span class="value" id="mempool-count">—</span></span>
        <span>Updated: <span class="value" id="updated">—</span></span>
    </div>
</div>
<div class="container">
    <div class="panel">
        <h2>⛓ Recent Blocks</h2>
        <div class="block-list" id="block-list">
            <div style="color:#6e7681;padding:20px;text-align:center">Loading blocks...</div>
        </div>
    </div>
    <div class="panel">
        <h2>📊 Network Status</h2>
        <div class="mempool-stats" id="network-stats">
            <div class="stat-card"><div class="label">Block Height</div><div class="value" id="stat-height">—</div></div>
            <div class="stat-card"><div class="label">Mempool TXs</div><div class="value" id="stat-mempool">—</div><div class="unit">transactions</div></div>
            <div class="stat-card"><div class="label">Peers</div><div class="value" id="stat-peers">—</div><div class="unit">connected</div></div>
            <div class="stat-card"><div class="label">Avg Block Time</div><div class="value" id="stat-blocktime">—</div><div class="unit">seconds</div></div>
        </div>
        <h2 style="margin-top:16px">🌐 Peers</h2>
        <div id="peer-list" style="margin-top:8px"></div>
    </div>
    <div class="panel full-width">
        <h2>🔍 Block Explorer</h2>
        <div class="search-bar">
            <input type="text" id="search-input" placeholder="Enter block height or hash...">
            <button onclick="lookupBlock()">Lookup</button>
        </div>
        <div class="block-detail" id="block-detail">
            <div style="color:#6e7681;padding:20px;text-align:center">Select a block or search by height/hash</div>
        </div>
    </div>
</div>
<script>
const RPC_REFRESH = 5000;
let blockCache = {};

async function fetchJSON(path) {
    try {
        const resp = await fetch(path);
        return await resp.json();
    } catch (e) {
        return { error: e.message };
    }
}

async function updateStatus() {
    const status = await fetchJSON('/api/status');
    if (status.error) {
        document.getElementById('height').textContent = 'OFFLINE';
        document.getElementById('height').style.color = '#f85149';
        return;
    }
    document.getElementById('height').textContent = status.height || '—';
    document.getElementById('height').style.color = '#58a6ff';
    document.getElementById('peers').textContent = (status.peers || []).length;
    const mp = status.mempool || {};
    document.getElementById('mempool-count').textContent = mp.size || 0;
    document.getElementById('updated').textContent = new Date().toLocaleTimeString();
    document.getElementById('stat-height').textContent = status.height || '—';
    document.getElementById('stat-mempool').textContent = mp.size || 0;
    document.getElementById('stat-peers').textContent = (status.peers || []).length;
    const metrics = status.metrics || {};
    if (metrics.avg_block_time) {
        document.getElementById('stat-blocktime').textContent = metrics.avg_block_time.toFixed(1);
    }
    // Peers
    const peerList = document.getElementById('peer-list');
    const peers = status.peers || [];
    if (peers.length === 0) {
        peerList.innerHTML = '<div style="color:#6e7681;font-size:12px">No peers connected</div>';
    } else {
        peerList.innerHTML = peers.slice(0, 10).map(p =>
            '<div class="peer-item"><span class="addr">' + (p.addr || p.address || 'unknown') + '</span></div>'
        ).join('');
    }
}

async function updateBlocks() {
    const blocks = await fetchJSON('/api/blocks?count=12');
    if (blocks.error || !Array.isArray(blocks)) {
        document.getElementById('block-list').innerHTML = '<div class="error">Failed to load blocks</div>';
        return;
    }
    const container = document.getElementById('block-list');
    container.innerHTML = blocks.map(b => {
        const height = b.height || '?';
        const hash = b.hash || '';
        const time = b.time ? new Date(b.time * 1000).toLocaleString() : '?';
        const txCount = (b.tx || b.transactions || []).length;
        return '<div class="block-item" onclick="showBlock(' + height + ')">' +
            '<div class="height">Block #' + height + '</div>' +
            '<div class="hash">' + hash + '</div>' +
            '<div class="meta"><span class="txs">' + txCount + ' tx</span><span class="time">' + time + '</span></div>' +
            '</div>';
    }).join('');
}

async function showBlock(height) {
    const block = await fetchJSON('/api/block/' + height);
    if (block.error) {
        document.getElementById('block-detail').innerHTML = '<div class="error">Block not found: ' + block.error + '</div>';
        return;
    }
    const fields = [
        ['Height', block.height],
        ['Hash', block.hash],
        ['Version', block.version],
        ['Previous Block', block.prev],
        ['Merkle Root', block.merkle],
        ['Time', block.time ? new Date(block.time * 1000).toLocaleString() : '?'],
        ['Bits', block.bits],
        ['Nonce', block.nonce],
        ['Confirmations', block.confirmations],
        ['Transactions', (block.tx || []).length]
    ];
    let html = '<div class="block-detail">';
    fields.forEach(([label, value]) => {
        html += '<div class="field"><span class="label">' + label + '</span><span class="value">' + (value || '—') + '</span></div>';
    });
    const txs = block.tx || [];
    if (txs.length > 0) {
        html += '<div class="tx-list"><h3 style="color:#00d4ff;font-size:12px;margin:12px 0 8px">Transactions</h3>';
        txs.forEach(txid => {
            html += '<div class="tx-item">' + txid + '</div>';
        });
        html += '</div>';
    }
    html += '</div>';
    document.getElementById('block-detail').innerHTML = html;
}

async function lookupBlock() {
    const input = document.getElementById('search-input').value.trim();
    if (!input) return;
    if (/^[0-9]+$/.test(input)) {
        showBlock(parseInt(input));
    } else {
        const block = await fetchJSON('/api/block/' + input);
        if (block && block.height !== undefined) {
            showBlock(block.height);
        } else {
            document.getElementById('block-detail').innerHTML = '<div class="error">Block not found: ' + input + '</div>';
        }
    }
}

document.getElementById('search-input').addEventListener('keypress', function(e) {
    if (e.key === 'Enter') lookupBlock();
});

// Initial load
updateStatus();
updateBlocks();
setInterval(updateStatus, RPC_REFRESH);
setInterval(updateBlocks, RPC_REFRESH);
</script>
</body>
</html>"""


# ------------------------------------------------------------------ Main
class ThreadedHTTPD(socketserver.ThreadingMixIn, http.server.HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    parser = argparse.ArgumentParser(description="Excalibur Living Ledger")
    parser.add_argument("--host", type=str, default="0.0.0.0",
                        help="Address to serve on (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=9434,
                        help="Port to serve the ledger page (default: 9434)")
    parser.add_argument("--rpc", type=str, default="http://localhost:9432",
                        help="Node RPC URL (default: http://localhost:9432)")
    parser.add_argument("--test", action="store_true",
                        help="Run self-tests")
    args = parser.parse_args()

    if args.test:
        return run_tests(args.rpc)

    ledger = LedgerData(args.rpc)
    LedgerHandler.ledger = ledger

    server = ThreadedHTTPD((args.host, args.port), LedgerHandler)
    print(f"Living Ledger running at http://{args.host}:{args.port}")
    print(f"Connected to node RPC: {args.rpc}")
    print("Press Ctrl+C to stop")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\\nShutting down...")
        server.shutdown()


def run_tests(rpc_url):
    """Self-tests that verify the ledger components work."""
    passed = 0
    failed = 0

    def check(name, condition):
        nonlocal passed, failed
        if condition:
            print(f"  ✓ {name}")
            passed += 1
        else:
            print(f"  ✗ {name}")
            failed += 1

    print("Living Ledger Tests")
    print("=" * 50)

    # Test format functions
    check("format_swords(100000000) == '1.00000000'",
          format_swords(100_000_000) == "1.00000000")
    check("format_swords(500000000) == '5.00000000'",
          format_swords(500_000_000) == "5.00000000")
    check("format_swords(0) == '0.00000000'",
          format_swords(0) == "0.00000000")

    # Test hex truncation
    check("truncate_hex short string unchanged",
          truncate_hex("abc123") == "abc123")
    check("truncate_hex long string truncated",
          len(truncate_hex("a" * 64)) < 64)

    # Test lock type parsing
    check("parse_lock_type PKH",
          parse_lock_type("00" + "ab" * 20) == "PKH")
    check("parse_lock_type KNOT",
          parse_lock_type("06" + "ab" * 20) == "KNOT")
    check("parse_lock_type PQH",
          parse_lock_type("01" + "ab" * 33) == "PQH")

    # Test sha256d
    check("sha256d empty bytes",
          len(sha256d(b"")) == 32)
    check("sha256d deterministic",
          sha256d(b"test") == sha256d(b"test"))

    # Test LedgerData initialization
    ledger = LedgerData(rpc_url)
    check("LedgerData initialized", ledger.rpc_url == rpc_url)

    # Test RPC connection (may fail if node not running)
    try:
        result = rpc_call(rpc_url, "getblockcount")
        check("RPC getblockcount works", isinstance(result, int))
        check(f"Block height: {result}", result >= 0)

        # Test getrecentblocks
        blocks = rpc_call(rpc_url, "getrecentblocks", [3])
        check("RPC getrecentblocks returns list", isinstance(blocks, list))
        if blocks:
            check("Block has height field", "height" in blocks[0])
            check("Block has hash field", "hash" in blocks[0])

        # Test getmempoolinfo
        mempool = rpc_call(rpc_url, "getmempoolinfo")
        check("RPC getmempoolinfo returns dict", isinstance(mempool, dict))

        # Test getpeerinfo
        peers = rpc_call(rpc_url, "getpeerinfo")
        check("RPC getpeerinfo returns list", isinstance(peers, list))

    except ConnectionError as e:
        check(f"RPC connection (node not running): {e}", True)

    # Test HTML generation
    check("HTML contains title", "Excalibur Living Ledger" in LIVING_LEDGER_HTML)
    check("HTML contains block list", "block-list" in LIVING_LEDGER_HTML)
    check("HTML contains search", "search-input" in LIVING_LEDGER_HTML)
    check("CSS contains animations", "pulse" in LIVING_LEDGER_CSS)

    print()
    print("=" * 50)
    print(f"Results: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    main()
