#!/usr/bin/env python3
"""p2p_bootstrap_server.py — AetherionEXCAL Bootstrap Discovery Server.

A central server that nodes register with and query for peers.
This is the breakthrough that enables P2P discovery between machines
without hardcoded seed peers.

Features:
- Node registration with automatic IP detection
- Peer discovery via REST API
- LAN broadcast discovery (UDP multicast)
- Health checking and stale peer pruning
- Cross-platform support (Windows, Mac, Linux, Android, iOS)

Usage:
    python p2p_bootstrap_server.py
    # Or as a library:
    from p2p_bootstrap_server import BootstrapServer
    server = BootstrapServer(port=9435)
    server.start()
"""
import asyncio
import hashlib
import json
import logging
import socket
import struct
import threading
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from .postgres_p2p import P2PDatabase

logger = logging.getLogger("bootstrap")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_PORT = 9435
DEFAULT_MULTICAST_PORT = 9436
DEFAULT_MULTICAST_GROUP = "239.1.1.1"
DEFAULT_MULTICAST_TTL = 32  # Increased from 2 for cross-subnet discovery
PEER_TTL = 600  # seconds before peer is considered stale (increased from 300)
HEALTH_CHECK_INTERVAL = 60  # seconds between health checks

# Central bootstrap servers for cross-network discovery
# After deploying the SkyNet beacon to Cloudflare Workers, replace with your URL:
#   https://skynet-beacon.YOUR_ACCOUNT.workers.dev
CENTRAL_BOOTSTRAP_SERVERS = [
    "https://skynet-beacon.aetherion.workers.dev",  # SkyNet Temporal Node Beacon
]

# LAN broadcast fallback
DEFAULT_BROADCAST_PORT = 9437
DEFAULT_BROADCAST_ADDRESS = "255.255.255.255"


# ---------------------------------------------------------------------------
# Bootstrap Server
# ---------------------------------------------------------------------------

class BootstrapServer:
    """Central bootstrap discovery server for AetherionEXCAL P2P network.
    
    Nodes register with this server and query it for peer addresses.
    Supports both REST API and UDP multicast discovery.
    """
    
    def __init__(self, port=DEFAULT_PORT, db_path=None, 
                 multicast_group=DEFAULT_MULTICAST_GROUP,
                 multicast_port=DEFAULT_MULTICAST_PORT):
        """Initialize the bootstrap server.
        
        Args:
            port: HTTP server port
            db_path: Path to SQLite database
            multicast_group: UDP multicast group for LAN discovery
            multicast_port: UDP multicast port for LAN discovery
        """
        self.port = port
        self.multicast_group = multicast_group
        self.multicast_port = multicast_port
        self.db = P2PDatabase(db_path)
        self._server = None
        self._thread = None
        self._multicast_thread = None
        self._running = False
        self._node_id = str(uuid.uuid4())
        self._peers = {}  # {node_id: {host, port, last_seen, services, ...}}
        self._lock = threading.Lock()
        
        # Load persisted peers from database
        self._load_peers()
    
    def _load_peers(self):
        """Load peers from the persistent database."""
        peers = self.db.get_peers(limit=1000)
        for peer in peers:
            node_id = peer["node_id"]
            self._peers[node_id] = {
                "node_id": node_id,
                "host": peer["host"],
                "port": peer["port"],
                "services": peer["services"],
                "last_seen": peer["last_seen"],
                "user_agent": peer.get("user_agent", ""),
                "version": peer.get("version", 0),
            }
    
    def start(self):
        """Start the bootstrap server in a background thread."""
        self._running = True
        
        # Start HTTP server
        self._thread = threading.Thread(target=self._run_http, daemon=True)
        self._thread.start()
        
        # Start UDP multicast listener
        self._multicast_thread = threading.Thread(target=self._run_multicast, daemon=True)
        self._multicast_thread.start()
        
        logger.info(f"Bootstrap server started on port {self.port}")
        logger.info(f"Multicast listener on {self.multicast_group}:{self.multicast_port}")
    
    def stop(self):
        """Stop the bootstrap server."""
        self._running = False
        if self._server:
            self._server.shutdown()
        if self._thread:
            self._thread.join(timeout=5)
        if self._multicast_thread:
            self._multicast_thread.join(timeout=5)
        logger.info("Bootstrap server stopped")
    
    def _run_http(self):
        """Run the HTTP server."""
        self._server = HTTPServer(("0.0.0.0", self.port), BootstrapHandler)
        self._server.bootstrap_server = self
        try:
            self._server.serve_forever()
        except OSError:
            pass
    
    def _run_multicast(self):
        """Run the UDP multicast listener for LAN discovery."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(1.0)
            sock.bind(("", self.multicast_port))
            
            # Join multicast group
            mreq = struct.pack("4s4s", 
                              socket.inet_aton(self.multicast_group),
                              socket.inet_aton("0.0.0.0"))
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            
            while self._running:
                try:
                    data, addr = sock.recvfrom(1024)
                    self._handle_multicast_message(data, addr)
                except socket.timeout:
                    continue
                except OSError as e:
                    logger.warning(f"Multicast error: {e}")
                    break
        except OSError as e:
            logger.warning(f"Failed to start multicast: {e}")
        finally:
            try:
                sock.close()
            except OSError:
                pass
    
    def _handle_multicast_message(self, data: bytes, addr: tuple):
        """Handle a UDP multicast message."""
        try:
            msg = json.loads(data.decode("utf-8"))
            msg_type = msg.get("type", "")
            
            if msg_type == "register":
                self._register_peer(
                    msg.get("node_id", ""),
                    addr[0],
                    msg.get("port", 9433),
                    msg.get("services", 0),
                    msg.get("user_agent", ""),
                    msg.get("version", 0),
                )
                # Send response with known peers
                peers = self._get_peers_for_response()
                response = json.dumps({
                    "type": "peers",
                    "peers": peers,
                }).encode("utf-8")
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.settimeout(1.0)
                    sock.sendto(response, (addr[0], msg.get("port", 9433)))
                    sock.close()
                except OSError:
                    pass
            
            elif msg_type == "heartbeat":
                node_id = msg.get("node_id", "")
                with self._lock:
                    if node_id in self._peers:
                        self._peers[node_id]["last_seen"] = time.time()
            
            elif msg_type == "unregister":
                node_id = msg.get("node_id", "")
                with self._lock:
                    self._peers.pop(node_id, None)
        
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.warning(f"Invalid multicast message: {e}")
    
    def _register_peer(self, node_id: str, host: str, port: int, 
                       services: int = 0, user_agent: str = "", version: int = 0):
        """Register a peer with the bootstrap server."""
        if not node_id:
            node_id = hashlib.sha256(f"{host}:{port}".encode()).hexdigest()[:16]
        
        with self._lock:
            self._peers[node_id] = {
                "node_id": node_id,
                "host": host,
                "port": port,
                "services": services,
                "last_seen": time.time(),
                "user_agent": user_agent,
                "version": version,
            }
        
        # Persist to database
        self.db.add_peer(node_id, host, port, services, user_agent, version)
        logger.info(f"Registered peer {node_id} at {host}:{port}")
    
    def _get_peers_for_response(self, limit: int = 8) -> list:
        """Get peers for a discovery response."""
        now = time.time()
        peers = []
        
        with self._lock:
            for node_id, peer in self._peers.items():
                last_seen = peer.get("last_seen", 0)
                # Skip stale peers
                if now - last_seen > PEER_TTL:
                    continue
                peers.append({
                    "node_id": peer.get("node_id", node_id),
                    "host": peer.get("host", ""),
                    "port": peer.get("port", 9433),
                    "services": peer.get("services", 0),
                    "last_seen": last_seen,
                })
        
        # Sort by last_seen (most recent first)
        peers.sort(key=lambda p: p.get("last_seen", 0), reverse=True)
        return peers[:limit]
    
    def get_peers(self, limit: int = 8) -> list:
        """Get peers for a discovery request.
        
        Args:
            limit: Maximum number of peers to return
            
        Returns:
            list[dict]: Peer information
        """
        return self._get_peers_for_response(limit)
    
    def get_stats(self) -> dict:
        """Get bootstrap server statistics."""
        now = time.time()
        with self._lock:
            total = len(self._peers)
            active = sum(1 for p in self._peers.values() 
                        if now - p.get("last_seen", 0) < PEER_TTL)
        
        db_stats = self.db.get_stats()
        return {
            "node_id": self._node_id,
            "port": self.port,
            "peers_registered": total,
            "peers_active": active,
            "database": db_stats,
        }
    
    def prune_stale_peers(self):
        """Remove stale peers from memory and database."""
        now = time.time()
        with self._lock:
            stale = [
                node_id for node_id, peer in self._peers.items()
                if now - peer.get("last_seen", 0) > PEER_TTL
            ]
            for node_id in stale:
                del self._peers[node_id]
        
        if stale:
            self.db.prune_stale_peers(PEER_TTL)
            logger.info(f"Pruned {len(stale)} stale peers")


# ---------------------------------------------------------------------------
# HTTP Request Handler
# ---------------------------------------------------------------------------

class BootstrapHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the bootstrap server."""
    
    def log_message(self, format, *args):
        """Override to use our logger."""
        try:
            logger.debug(format % args)
        except Exception:
            pass
    
    def do_GET(self):
        """Handle GET requests."""
        parsed = urlparse(self.path)
        
        if parsed.path == "/peers":
            self._handle_get_peers(parsed)
        elif parsed.path == "/stats":
            self._handle_get_stats()
        elif parsed.path == "/health":
            self._handle_health()
        else:
            self._send_json({"error": "not found"}, 404)
    
    def do_POST(self):
        """Handle POST requests."""
        parsed = urlparse(self.path)
        
        if parsed.path == "/register":
            self._handle_register()
        elif parsed.path == "/unregister":
            self._handle_unregister()
        else:
            self._send_json({"error": "not found"}, 404)
    
    def _handle_get_peers(self, parsed):
        """Handle GET /peers?limit=8"""
        params = parse_qs(parsed.query)
        limit = int(params.get("limit", [8])[0])
        
        server = self.server.bootstrap_server
        peers = server.get_peers(limit)
        self._send_json({"peers": peers, "count": len(peers)})
    
    def _handle_get_stats(self):
        """Handle GET /stats"""
        server = self.server.bootstrap_server
        stats = server.get_stats()
        self._send_json(stats)
    
    def _handle_health(self):
        """Handle GET /health"""
        self._send_json({"status": "ok", "node_id": self.server.bootstrap_server._node_id})
    
    def _handle_register(self):
        """Handle POST /register"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))
            
            node_id = data.get("node_id", "")
            host = data.get("host", "")
            port = data.get("port", 9433)
            services = data.get("services", 0)
            user_agent = data.get("user_agent", "")
            version = data.get("version", 0)
            
            if not node_id or not host or not port:
                self._send_json({"error": "missing required fields"}, 400)
                return
            
            self.server.bootstrap_server._register_peer(node_id, host, port, services, user_agent, version)
            self._send_json({"status": "ok", "node_id": node_id})
        
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": str(e)}, 400)
    
    def _handle_unregister(self):
        """Handle POST /unregister"""
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))
            
            node_id = data.get("node_id", "")
            with self.server.bootstrap_server._lock:
                self.server.bootstrap_server._peers.pop(node_id, None)
            
            self._send_json({"status": "ok"})
        
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": str(e)}, 400)
    
    def _send_json(self, data: dict, status: int = 200):
        """Send a JSON response."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))


# ---------------------------------------------------------------------------
# Peer Client — for nodes to register and discover peers
# ---------------------------------------------------------------------------

class BootstrapClient:
    """Client for the bootstrap discovery server.
    
    Use this to register your node and discover peers.
    """
    
    def __init__(self, server_url: str = None, node_id: str = None,
                 host: str = None, port: int = 9433,
                 services: int = 0, user_agent: str = "/AetherionEXCAL:1.0/"):
        """Initialize the bootstrap client.
        
        Args:
            server_url: Bootstrap server URL (e.g., http://localhost:9435)
            node_id: Unique node ID (auto-generated if not provided)
            host: Your node's host address
            port: Your node's P2P port
            services: Your node's service flags
            user_agent: Your node's user agent string
        """
        self.server_url = server_url or "http://localhost:9435"
        self.node_id = node_id or str(uuid.uuid4())
        self.host = host or self._get_local_ip()
        self.port = port
        self.services = services
        self.user_agent = user_agent
        self._multicast_sock = None
        self._central_servers = CENTRAL_BOOTSTRAP_SERVERS.copy()
    
    def _get_local_ip(self) -> str:
        """Get the local IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except OSError:
            return "127.0.0.1"
    
    def register(self) -> bool:
        """Register this node with the bootstrap server.
        
        Returns:
            bool: True if registration succeeded
        """
        try:
            import urllib.request
            data = json.dumps({
                "node_id": self.node_id,
                "host": self.host,
                "port": self.port,
                "services": self.services,
                "user_agent": self.user_agent,
            }).encode("utf-8")
            
            req = urllib.request.Request(
                f"{self.server_url}/register",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result.get("status") == "ok"
        except Exception as e:
            logger.warning(f"Failed to register with bootstrap server: {e}")
            return False
    
    def unregister(self):
        """Unregister this node from the bootstrap server."""
        try:
            import urllib.request
            data = json.dumps({"node_id": self.node_id}).encode("utf-8")
            
            req = urllib.request.Request(
                f"{self.server_url}/unregister",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                pass
        except Exception as e:
            logger.warning(f"Failed to unregister from bootstrap server: {e}")
    
    def discover_peers(self, limit: int = 8) -> list:
        """Discover peers from the bootstrap server.
        
        Args:
            limit: Maximum number of peers to return
            
        Returns:
            list[tuple]: (host, port) pairs
        """
        try:
            import urllib.request
            with urllib.request.urlopen(f"{self.server_url}/peers?limit={limit}", timeout=5) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                peers = result.get("peers", [])
                return [(p["host"], p["port"]) for p in peers]
        except Exception as e:
            logger.warning(f"Failed to discover peers: {e}")
            return []
    
    def broadcast_multicast(self):
        """Broadcast a registration message via UDP multicast."""
        try:
            msg = json.dumps({
                "type": "register",
                "node_id": self.node_id,
                "host": self.host,
                "port": self.port,
                "services": self.services,
                "user_agent": self.user_agent,
            }).encode("utf-8")
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, DEFAULT_MULTICAST_TTL)
            sock.sendto(msg, (DEFAULT_MULTICAST_GROUP, DEFAULT_MULTICAST_PORT))
            sock.close()
            
            # Also broadcast via LAN broadcast for maximum reach
            try:
                broadcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                broadcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                broadcast_sock.sendto(msg, (DEFAULT_BROADCAST_ADDRESS, DEFAULT_BROADCAST_PORT))
                broadcast_sock.close()
                logger.info(f"Broadcasted registration via LAN broadcast")
            except OSError as e:
                logger.warning(f"Failed to broadcast via LAN: {e}")
        except OSError as e:
            logger.warning(f"Failed to broadcast multicast: {e}")
    
    def start_multicast_listener(self, callback):
        """Start listening for multicast and broadcast messages.
        
        Args:
            callback: Function called with (node_id, host, port, services) for each peer
        """
        def _listen():
            seen_peers = {}  # Deduplicate peer discoveries
            
            # Multicast listener
            multicast_sock = None
            try:
                multicast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
                multicast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                multicast_sock.settimeout(1.0)
                multicast_sock.bind(("", DEFAULT_MULTICAST_PORT))
                
                mreq = struct.pack("4s4s",
                                  socket.inet_aton(DEFAULT_MULTICAST_GROUP),
                                  socket.inet_aton("0.0.0.0"))
                multicast_sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                logger.info(f"Multicast listener started on {DEFAULT_MULTICAST_GROUP}:{DEFAULT_MULTICAST_PORT}")
            except OSError as e:
                logger.warning(f"Failed to start multicast listener: {e}")
            
            # Broadcast listener
            broadcast_sock = None
            try:
                broadcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                broadcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                broadcast_sock.settimeout(1.0)
                broadcast_sock.bind(("", DEFAULT_BROADCAST_PORT))
                logger.info(f"Broadcast listener started on port {DEFAULT_BROADCAST_PORT}")
            except OSError as e:
                logger.warning(f"Failed to start broadcast listener: {e}")
            
            socks = []
            if multicast_sock:
                socks.append(multicast_sock)
            if broadcast_sock:
                socks.append(broadcast_sock)
            
            while True:
                for sock in socks:
                    try:
                        data, addr = sock.recvfrom(1024)
                        msg = json.loads(data.decode("utf-8"))
                        
                        if msg.get("type") == "peers":
                            for peer in msg.get("peers", []):
                                peer_key = f"{peer.get('host', '')}:{peer.get('port', 9433)}"
                                if peer_key not in seen_peers:
                                    seen_peers[peer_key] = time.time()
                                    callback(
                                        peer.get("node_id", ""),
                                        peer.get("host", ""),
                                        peer.get("port", 9433),
                                        peer.get("services", 0),
                                    )
                        elif msg.get("type") == "register":
                            # Respond to registration with our known peers
                            peer_key = f"{msg.get('host', '')}:{msg.get('port', 9433)}"
                            if peer_key not in seen_peers:
                                seen_peers[peer_key] = time.time()
                                callback(
                                    msg.get("node_id", ""),
                                    msg.get("host", ""),
                                    msg.get("port", 9433),
                                    msg.get("services", 0),
                                )
                    except (socket.timeout, json.JSONDecodeError):
                        continue
                    except OSError:
                        break
                
                # Prune stale seen_peers
                now = time.time()
                seen_peers = {k: v for k, v in seen_peers.items() if now - v < PEER_TTL}
            
        def _cleanup():
            try:
                if multicast_sock:
                    multicast_sock.close()
                if broadcast_sock:
                    broadcast_sock.close()
            except OSError:
                pass
        
        thread = threading.Thread(target=_listen, daemon=True)
        thread.start()
        return thread
    
    def discover_central_peers(self, limit: int = 8) -> list:
        """Try to discover peers from central bootstrap servers.
        
        Returns:
            list[tuple]: (host, port) pairs from central servers
        """
        all_peers = []
        for server_url in CENTRAL_BOOTSTRAP_SERVERS:
            try:
                import urllib.request
                with urllib.request.urlopen(f"{server_url}/peers?limit={limit}", timeout=3) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    peers = result.get("peers", [])
                    all_peers.extend([(p["host"], p["port"]) for p in peers])
                    logger.info(f"Discovered {len(peers)} peers from central server: {server_url}")
            except Exception as e:
                logger.debug(f"Central server {server_url} unavailable: {e}")
        
        # Deduplicate
        seen = set()
        unique = []
        for host, port in all_peers:
            key = f"{host}:{port}"
            if key not in seen:
                seen.add(key)
                unique.append((host, port))
        return unique


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    """Run the bootstrap server."""
    import argparse
    
    parser = argparse.ArgumentParser(description="AetherionEXCAL Bootstrap Discovery Server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="HTTP server port")
    parser.add_argument("--db", type=str, default=None, help="Database path")
    parser.add_argument("--multicast-group", type=str, default=DEFAULT_MULTICAST_GROUP,
                       help="UDP multicast group")
    parser.add_argument("--multicast-port", type=int, default=DEFAULT_MULTICAST_PORT,
                       help="UDP multicast port")
    
    args = parser.parse_args()
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    
    server = BootstrapServer(
        port=args.port,
        db_path=args.db,
        multicast_group=args.multicast_group,
        multicast_port=args.multicast_port,
    )
    
    print(f"AetherionEXCAL Bootstrap Discovery Server")
    print(f"HTTP: http://0.0.0.0:{args.port}")
    print(f"Multicast: {args.multicast_group}:{args.multicast_port}")
    print(f"Node ID: {server._node_id}")
    print()
    print("Endpoints:")
    print(f"  GET  /peers?limit=8    - Discover peers")
    print(f"  POST /register         - Register a node")
    print(f"  POST /unregister       - Unregister a node")
    print(f"  GET  /stats            - Server statistics")
    print(f"  GET  /health           - Health check")
    print()
    
    server.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.stop()


if __name__ == "__main__":
    main()
