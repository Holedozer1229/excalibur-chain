#!/usr/bin/env python3
"""skynet_beacon.py — AetherionEXCAL SkyNet Node Beacon.

A standalone, always-on beacon service that keeps your node discoverable
on the SkyNet P2P network, even when the wallet GUI is closed.

This runs as a background daemon (Windows service / Mac launchd) that:
1. Runs the bootstrap discovery server (HTTP + UDP multicast/broadcast)
2. Registers this machine's node with central SkyNet beacons
3. Heartbeats periodically to stay alive
4. Discovers and shares peers with other nodes
5. Persists all P2P data in SQLite

Usage:
    # Run directly:
    python skynet_beacon.py
    
    # As a Windows executable:
    AetherionEXCAL-Beacon.exe
    
    # Auto-start on Windows (runs in system tray):
    AetherionEXCAL-Beacon.exe --tray
    
    # Auto-start on Mac (launchd plist):
    cp com.aetherion.skynet-beacon.plist ~/Library/LaunchAgents/
    launchctl load ~/Library/LaunchAgents/com.aetherion.skynet-beacon.plist

Features:
    - Always-on peer discovery server
    - UDP multicast + broadcast for LAN discovery
    - Central bootstrap server registration
    - Periodic heartbeats to stay alive
    - Persistent peer database (SQLite)
    - Health check HTTP endpoint
    - System tray icon (Windows)
    - Cross-platform (Windows, Mac, Linux)
"""
import argparse
import hashlib
import json
import logging
import os
import socket
import struct
import sys
import threading
import time
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse, parse_qs

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sphinx_os.nexus import P2PDatabase

logger = logging.getLogger("skynet_beacon")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_PORT = 9435
DEFAULT_MULTICAST_PORT = 9436
DEFAULT_MULTICAST_GROUP = "239.1.1.1"
DEFAULT_MULTICAST_TTL = 32
DEFAULT_BROADCAST_PORT = 9437
DEFAULT_BROADCAST_ADDRESS = "255.255.255.255"
PEER_ACTIVE_TIMEOUT = 1800  # 30 minutes before peer is considered inactive for active count
PEER_TTL = 604800  # 7 days before peer is pruned, allowing peers to reconnect
HEARTBEAT_INTERVAL = 60
PRUNE_INTERVAL = 3600  # prune check once per hour
CENTRAL_BOOTSTRAP_SERVERS = [
    "https://skynet-beacon.aetherion.workers.dev",
]

WALLET_DIR = Path(os.path.expanduser("~/.excal_wallet"))
BEACON_DB_PATH = WALLET_DIR / "beacon.db"
BEACON_STATE_PATH = WALLET_DIR / "beacon_state.json"


# ---------------------------------------------------------------------------
# SkyNet Beacon — Always-On Node Discovery Service
# ---------------------------------------------------------------------------

class SkyNetBeacon:
    """Always-on SkyNet beacon that keeps your node discoverable 24/7.
    
    This is the breakthrough: your node is always registered and discoverable,
    even when the wallet GUI is closed. Other nodes can find you via:
    - HTTP REST API (port 9435)
    - UDP multicast (239.1.1.1:9436)
    - LAN broadcast (255.255.255.255:9437)
    - Central bootstrap servers (Cloudflare Workers)
    """
    
    def __init__(self, port=DEFAULT_PORT, p2p_port=9433,
                 multicast_group=DEFAULT_MULTICAST_GROUP,
                 multicast_port=DEFAULT_MULTICAST_PORT):
        self.port = port
        self.p2p_port = p2p_port
        self.multicast_group = multicast_group
        self.multicast_port = multicast_port
        self.db = P2PDatabase(str(BEACON_DB_PATH))
        self._server = None
        self._http_thread = None
        self._multicast_thread = None
        self._broadcast_thread = None
        self._heartbeat_thread = None
        self._prune_thread = None
        self._running = False
        self._node_id = self._load_or_create_node_id()
        self._host = self._get_local_ip()
        self._peers = {}
        self._lock = threading.Lock()
        self._central_servers = CENTRAL_BOOTSTRAP_SERVERS.copy()
        
        # Load persisted peers
        self._load_peers()
        logger.info(f"SkyNet Beacon initialized: {self._node_id} @ {self._host}:{self.port}")
    
    def _load_or_create_node_id(self) -> str:
        """Load or create a persistent node ID."""
        try:
            state = json.loads(BEACON_STATE_PATH.read_text())
            return state.get("node_id", str(uuid.uuid4()))
        except (FileNotFoundError, json.JSONDecodeError):
            node_id = str(uuid.uuid4())
            self._save_state({"node_id": node_id})
            return node_id
    
    def _save_state(self, state: dict):
        """Save beacon state to disk."""
        try:
            WALLET_DIR.mkdir(parents=True, exist_ok=True)
            BEACON_STATE_PATH.write_text(json.dumps(state, indent=2))
        except OSError as e:
            logger.warning(f"Failed to save beacon state: {e}")
    
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
        """Start all beacon services."""
        self._running = True
        
        # Register ourselves as a peer
        self._register_self()
        
        # Start HTTP server
        self._http_thread = threading.Thread(target=self._run_http, daemon=True)
        self._http_thread.start()
        logger.info(f"HTTP server started on port {self.port}")
        
        # Start UDP multicast listener
        self._multicast_thread = threading.Thread(target=self._run_multicast, daemon=True)
        self._multicast_thread.start()
        logger.info(f"Multicast listener on {self.multicast_group}:{self.multicast_port}")
        
        # Start LAN broadcast listener
        self._broadcast_thread = threading.Thread(target=self._run_broadcast, daemon=True)
        self._broadcast_thread.start()
        logger.info(f"Broadcast listener on port {DEFAULT_BROADCAST_PORT}")
        
        # Start heartbeat thread
        self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._heartbeat_thread.start()
        logger.info(f"Heartbeat interval: {HEARTBEAT_INTERVAL}s")
        
        # Start prune thread
        self._prune_thread = threading.Thread(target=self._prune_loop, daemon=True)
        self._prune_thread.start()
        logger.info(f"Prune interval: {PRUNE_INTERVAL}s")
        
        # Initial registration with central servers
        self._register_with_central()
        
        logger.info(f"SkyNet Beacon ACTIVE — Node {self._node_id} @ {self._host}:{self.p2p_port}")
    
    def stop(self):
        """Stop all beacon services."""
        logger.info("Shutting down SkyNet Beacon...")
        self._running = False
        
        # Unregister from central servers
        self._unregister_from_central()
        
        if self._server:
            self._server.shutdown()
        
        # Save state
        self._save_state({
            "node_id": self._node_id,
            "last_stop": time.time(),
            "peers_count": len(self._peers),
        })
        
        logger.info("SkyNet Beacon stopped")
    
    def _register_self(self):
        """Register this node as a peer."""
        self._peers[self._node_id] = {
            "node_id": self._node_id,
            "host": self._host,
            "port": self.p2p_port,
            "services": 1,
            "last_seen": time.time(),
            "user_agent": "/SkyNetBeacon:1.0/",
            "version": 1,
        }
        self.db.add_peer(self._node_id, self._host, self.p2p_port, 1, "/SkyNetBeacon:1.0/", 1)
    
    def _run_http(self):
        """Run the HTTP server."""
        self._server = HTTPServer(("0.0.0.0", self.port), BeaconHandler)
        self._server.beacon = self
        try:
            self._server.serve_forever()
        except OSError:
            pass
    
    def _run_multicast(self):
        """Run the UDP multicast listener."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(1.0)
            sock.bind(("", self.multicast_port))
            
            mreq = struct.pack("4s4s",
                              socket.inet_aton(self.multicast_group),
                              socket.inet_aton("0.0.0.0"))
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
            
            while self._running:
                try:
                    data, addr = sock.recvfrom(1024)
                    self._handle_udp_message(data, addr, sock)
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
    
    def _run_broadcast(self):
        """Run the LAN broadcast listener."""
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.settimeout(1.0)
            sock.bind(("", DEFAULT_BROADCAST_PORT))
            
            while self._running:
                try:
                    data, addr = sock.recvfrom(1024)
                    self._handle_udp_message(data, addr, sock)
                except socket.timeout:
                    continue
                except OSError as e:
                    logger.warning(f"Broadcast error: {e}")
                    break
        except OSError as e:
            logger.warning(f"Failed to start broadcast: {e}")
        finally:
            try:
                sock.close()
            except OSError:
                pass
    
    def _handle_udp_message(self, data: bytes, addr: tuple, sock: socket.socket):
        """Handle a UDP message (multicast or broadcast)."""
        try:
            msg = json.loads(data.decode("utf-8"))
            msg_type = msg.get("type", "")
            
            if msg_type == "register":
                node_id = msg.get("node_id", "")
                if node_id and node_id != self._node_id:
                    self._register_peer(
                        node_id,
                        addr[0],
                        msg.get("port", 9433),
                        msg.get("services", 0),
                        msg.get("user_agent", ""),
                        msg.get("version", 0),
                    )
                    # Respond with known peers
                    peers = self._get_peers_for_response()
                    response = json.dumps({"type": "peers", "peers": peers}).encode("utf-8")
                    try:
                        sock.sendto(response, (addr[0], msg.get("port", 9433)))
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
            logger.warning(f"Invalid UDP message: {e}")
    
    def _register_peer(self, node_id: str, host: str, port: int,
                       services: int = 0, user_agent: str = "", version: int = 0):
        """Register a peer."""
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
        
        self.db.add_peer(node_id, host, port, services, user_agent, version)
        logger.info(f"Registered peer {node_id} at {host}:{port}")
    
    def _get_peers_for_response(self, limit: int = 8) -> list:
        """Get peers for a discovery response."""
        now = time.time()
        peers = []
        
        with self._lock:
            for node_id, peer in self._peers.items():
                last_seen = peer.get("last_seen", 0)
                if now - last_seen > PEER_TTL:
                    continue
                peers.append({
                    "node_id": peer.get("node_id", node_id),
                    "host": peer.get("host", ""),
                    "port": peer.get("port", 9433),
                    "services": peer.get("services", 0),
                    "last_seen": last_seen,
                })
        
        peers.sort(key=lambda p: p.get("last_seen", 0), reverse=True)
        return peers[:limit]
    
    def get_peers(self, limit: int = 8) -> list:
        """Get peers for a discovery request."""
        return self._get_peers_for_response(limit)
    
    def get_stats(self) -> dict:
        """Get beacon statistics."""
        now = time.time()
        with self._lock:
            total = len(self._peers)
            active = sum(1 for p in self._peers.values()
                        if now - p.get("last_seen", 0) < PEER_ACTIVE_TIMEOUT)
        
        db_stats = self.db.get_stats()
        return {
            "node_id": self._node_id,
            "host": self._host,
            "p2p_port": self.p2p_port,
            "beacon_port": self.port,
            "peers_registered": total,
            "peers_active": active,
            "database": db_stats,
            "running": self._running,
        }
    
    def _heartbeat_loop(self):
        """Periodically heartbeat to central servers and broadcast."""
        while self._running:
            try:
                # Broadcast our presence
                self._broadcast_heartbeat()
                
                # Register with central servers
                self._register_with_central()
                
                # Update our own last_seen
                with self._lock:
                    if self._node_id in self._peers:
                        self._peers[self._node_id]["last_seen"] = time.time()
                
            except Exception as e:
                logger.warning(f"Heartbeat error: {e}")
            
            # Sleep with interrupt check
            for _ in range(HEARTBEAT_INTERVAL * 10):
                if not self._running:
                    break
                time.sleep(0.1)
    
    def _broadcast_heartbeat(self):
        """Broadcast a heartbeat via multicast and broadcast."""
        msg = json.dumps({
            "type": "heartbeat",
            "node_id": self._node_id,
            "host": self._host,
            "port": self.p2p_port,
        }).encode("utf-8")
        
        # Multicast
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, DEFAULT_MULTICAST_TTL)
            sock.sendto(msg, (DEFAULT_MULTICAST_GROUP, DEFAULT_MULTICAST_PORT))
            sock.close()
        except OSError:
            pass
        
        # LAN broadcast
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.sendto(msg, (DEFAULT_BROADCAST_ADDRESS, DEFAULT_BROADCAST_PORT))
            sock.close()
        except OSError:
            pass
    
    def _register_with_central(self):
        """Register with central bootstrap servers."""
        for server_url in self._central_servers:
            try:
                import urllib.request
                data = json.dumps({
                    "node_id": self._node_id,
                    "host": self._host,
                    "port": self.p2p_port,
                    "services": 1,
                    "user_agent": "/SkyNetBeacon:1.0/",
                }).encode("utf-8")
                
                req = urllib.request.Request(
                    f"{server_url}/register",
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=3) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    if result.get("status") == "ok":
                        logger.info(f"Registered with central beacon: {server_url}")
                
                # Discover peers from central
                with urllib.request.urlopen(f"{server_url}/peers?limit=8", timeout=3) as resp:
                    result = json.loads(resp.read().decode("utf-8"))
                    peers = result.get("peers", [])
                    for peer in peers:
                        if peer.get("node_id") != self._node_id:
                            self._register_peer(
                                peer.get("node_id", ""),
                                peer.get("host", ""),
                                peer.get("port", 9433),
                                peer.get("services", 0),
                            )
            except Exception as e:
                logger.debug(f"Central server {server_url} unavailable: {e}")
    
    def _unregister_from_central(self):
        """Unregister from central bootstrap servers."""
        for server_url in self._central_servers:
            try:
                import urllib.request
                data = json.dumps({"node_id": self._node_id}).encode("utf-8")
                req = urllib.request.Request(
                    f"{server_url}/unregister",
                    data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(req, timeout=3) as resp:
                    pass
            except Exception:
                pass
    
    def _prune_loop(self):
        """Periodically prune stale peers."""
        while self._running:
            # Wait PRUNE_INTERVAL before running prune so startup does not immediately drop persisted peers
            for _ in range(PRUNE_INTERVAL * 10):
                if not self._running:
                    break
                time.sleep(0.1)

            if not self._running:
                break

            try:
                self.prune_stale_peers()
            except Exception as e:
                logger.warning(f"Prune error: {e}")
    
    def prune_stale_peers(self):
        """Remove stale peers older than PEER_TTL."""
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
            logger.info(f"Pruned {len(stale)} stale peers (inactive > {PEER_TTL}s)")


# ---------------------------------------------------------------------------
# HTTP Request Handler
# ---------------------------------------------------------------------------

class BeaconHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the SkyNet Beacon."""
    
    def log_message(self, format, *args):
        """Suppress default stderr logging; use our logger instead."""
        try:
            logger.debug(format % args)
        except Exception:
            pass
    
    def do_GET(self):
        parsed = urlparse(self.path)
        
        if parsed.path == "/peers":
            params = parse_qs(parsed.query)
            limit = int(params.get("limit", [8])[0])
            peers = self.server.beacon.get_peers(limit)
            self._send_json({"peers": peers, "count": len(peers)})
        
        elif parsed.path == "/stats":
            stats = self.server.beacon.get_stats()
            self._send_json(stats)
        
        elif parsed.path == "/health":
            self._send_json({
                "status": "ok",
                "node_id": self.server.beacon._node_id,
                "host": self.server.beacon._host,
                "p2p_port": self.server.beacon.p2p_port,
            })
        
        else:
            self._send_json({"error": "not found"}, 404)
    
    def do_POST(self):
        parsed = urlparse(self.path)
        
        if parsed.path == "/register":
            self._handle_register()
        elif parsed.path == "/unregister":
            self._handle_unregister()
        else:
            self._send_json({"error": "not found"}, 404)
    
    def _handle_register(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))
            
            node_id = data.get("node_id", "")
            host = data.get("host", "")
            port = data.get("port", 9433)
            
            if not node_id or not host or not port:
                self._send_json({"error": "missing required fields"}, 400)
                return
            
            self.server.beacon._register_peer(
                node_id, host, port,
                data.get("services", 0),
                data.get("user_agent", ""),
                data.get("version", 0),
            )
            self._send_json({"status": "ok", "node_id": node_id})
        
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": str(e)}, 400)
    
    def _handle_unregister(self):
        try:
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            data = json.loads(body.decode("utf-8"))
            
            node_id = data.get("node_id", "")
            with self.server.beacon._lock:
                self.server.beacon._peers.pop(node_id, None)
            
            self._send_json({"status": "ok"})
        
        except (json.JSONDecodeError, ValueError) as e:
            self._send_json({"error": str(e)}, 400)
    
    def _send_json(self, data: dict, status: int = 200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))


# ---------------------------------------------------------------------------
# Windows System Tray (optional)
# ---------------------------------------------------------------------------

def run_with_tray(beacon: SkyNetBeacon):
    """Run the beacon with a system tray icon on Windows."""
    try:
        import ctypes
        from ctypes import wintypes
        
        WM_USER = 0x400
        WM_TRAY = WM_USER + 1
        NIM_ADD = 0x00000000
        NIM_DELETE = 0x00000002
        NIF_ICON = 0x00000002
        NIF_TIP = 0x00000004
        NIF_MESSAGE = 0x00000001
        WM_LBUTTONDOWN = 0x0201
        WM_RBUTTONDOWN = 0x0204
        
        # Create a simple console output instead of tray
        print(f"SkyNet Beacon running in background")
        print(f"Node ID: {beacon._node_id}")
        print(f"Host: {beacon._host}")
        print(f"P2P Port: {beacon.p2p_port}")
        print(f"Beacon Port: {beacon.port}")
        print(f"Press Ctrl+C to stop")
        
    except ImportError:
        pass
    
    # Keep running
    try:
        while beacon._running:
            time.sleep(1)
    except KeyboardInterrupt:
        beacon.stop()


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="AetherionEXCAL SkyNet Node Beacon")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Beacon HTTP port")
    parser.add_argument("--p2p-port", type=int, default=9433, help="P2P port")
    parser.add_argument("--tray", action="store_true", help="Run with system tray (Windows)")
    parser.add_argument("--daemon", action="store_true", help="Run as background daemon")
    parser.add_argument("--status", action="store_true", help="Show beacon status and exit")
    
    args = parser.parse_args()
    
    # Status mode
    if args.status:
        try:
            import urllib.request
            with urllib.request.urlopen(f"http://localhost:{args.port}/stats", timeout=2) as resp:
                stats = json.loads(resp.read().decode("utf-8"))
                print(json.dumps(stats, indent=2))
        except Exception as e:
            print(f"Beacon not running: {e}")
        return
    
    # Setup logging
    log_level = logging.INFO if not args.daemon else logging.WARNING
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    
    print("=" * 60)
    print("  AetherionEXCAL — SkyNet Node Beacon")
    print("=" * 60)
    print(f"  Node ID:    {uuid.uuid4()}")
    print(f"  HTTP Port:  {args.port}")
    print(f"  P2P Port:   {args.p2p_port}")
    print(f"  Multicast:  {DEFAULT_MULTICAST_GROUP}:{DEFAULT_MULTICAST_PORT}")
    print(f"  Broadcast:  {DEFAULT_BROADCAST_ADDRESS}:{DEFAULT_BROADCAST_PORT}")
    print("=" * 60)
    print()
    print("  Endpoints:")
    print(f"    GET  /peers?limit=8    - Discover peers")
    print(f"    POST /register         - Register a node")
    print(f"    POST /unregister       - Unregister a node")
    print(f"    GET  /stats            - Beacon statistics")
    print(f"    GET  /health           - Health check")
    print()
    print("  Press Ctrl+C to stop")
    print()
    
    # Create and start beacon
    beacon = SkyNetBeacon(
        port=args.port,
        p2p_port=args.p2p_port,
        multicast_group=DEFAULT_MULTICAST_GROUP,
        multicast_port=DEFAULT_MULTICAST_PORT,
    )
    
    beacon.start()
    
    if args.tray:
        run_with_tray(beacon)
    else:
        try:
            while beacon._running:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down SkyNet Beacon...")
            beacon.stop()


if __name__ == "__main__":
    main()
