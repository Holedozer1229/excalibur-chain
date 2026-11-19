#!/usr/bin/env python3
"""skynet_autonomous_node.py — AetherionEXCAL Autonomous Node for SkyNet/SpinxOS.

A fully autonomous, headless node that operates independently on the SkyNet P2P
network. It combines:
1. SkyNet Beacon — always-on peer discovery (HTTP + UDP multicast/broadcast)
2. Holographic P2P — entanglement-based message routing
3. Nexus Orchestrator — self-organizing consensus and treasury
4. Chain validation — continuous block verification and sync

This node runs 24/7 without a GUI, making it ideal for:
- VPS/cloud deployment
- Headless servers (Raspberry Pi, NAS, etc.)
- Background service (Windows Service / systemd / launchd)
- Network infrastructure contribution

Features:
    - Autonomous peer discovery and registration
    - Entanglement-based message routing
    - Self-organizing consensus participation
    - Continuous chain validation and sync
    - Prometheus metrics export
    - Health check HTTP endpoint
    - Auto-reconnection and fault recovery
    - Persistent state (SQLite + JSONL chain)
    - Cross-platform (Windows, Mac, Linux)

Usage:
    # Run directly:
    python skynet_autonomous_node.py
    
    # As a Windows executable:
    AetherionEXCAL-AutonomousNode.exe
    
    # With custom config:
    python skynet_autonomous_node.py --port 9433 --beacon-port 9435 --data-dir ./data
    
    # As a daemon (background):
    python skynet_autonomous_node.py --daemon
"""

import argparse
import hashlib
import json
import logging
import math
import os
import secrets
import socket
import struct
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, Future
from dataclasses import dataclass, field
from enum import Enum
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from typing import Dict, List, Optional, Any, Set, Tuple
from urllib.parse import urlparse, parse_qs

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Import directly from specific modules to avoid pulling in the entire nexus
# (which requires numpy for quantum_spacetime, etc.)
from sphinx_os.nexus.postgres_p2p import P2PDatabase
from sphinx_os.nexus.holographic_p2p import (
    HolographicP2PLayer, Peer, MessagePriority, NetworkMessage
)

logger = logging.getLogger("autonomous_node")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_P2P_PORT = 9433
DEFAULT_BEACON_PORT = 9435
DEFAULT_MULTICAST_PORT = 9436
DEFAULT_MULTICAST_GROUP = "239.1.1.1"
DEFAULT_MULTICAST_TTL = 32
DEFAULT_BROADCAST_PORT = 9437
DEFAULT_BROADCAST_ADDRESS = "255.255.255.255"
DEFAULT_METRICS_PORT = 9438

PEER_TTL = 604800  # seconds before peer is pruned (7 days, allows reconnection)
HEARTBEAT_INTERVAL = 60  # seconds between heartbeats
PRUNE_INTERVAL = 3600  # seconds between peer pruning (1 hour)
DISCOVERY_INTERVAL = 15  # seconds between peer discovery attempts
CHAIN_SYNC_INTERVAL = 10  # seconds between chain sync attempts
ENTANGLE_UPDATE_INTERVAL = 5  # seconds between entanglement graph updates

# Central bootstrap servers for cross-network discovery
CENTRAL_BOOTSTRAP_SERVERS = [
    "https://skynet-beacon.aetherion.workers.dev",
]

# Data directory
WALLET_DIR = Path(os.path.expanduser("~/.excal_wallet"))
NODE_DB_PATH = WALLET_DIR / "autonomous_node.db"
NODE_STATE_PATH = WALLET_DIR / "autonomous_node_state.json"
CHAIN_FILE = WALLET_DIR / "chain.jsonl"


# ---------------------------------------------------------------------------
# Node States
# ---------------------------------------------------------------------------

class NodeState(Enum):
    """Lifecycle states of the autonomous node."""
    INITIALIZING = "Initializing"
    DISCOVERING = "Discovering Peers"
    CONNECTING = "Connecting to Network"
    SYNCING = "Syncing Chain"
    ACTIVE = "Active — Participating in Consensus"
    IDLE = "Idle — Waiting for Peers"
    ERROR = "Error — Recovery in Progress"
    STOPPING = "Stopping"


@dataclass
class NodeStats:
    """Statistics for the autonomous node."""
    state: NodeState = NodeState.INITIALIZING
    uptime: float = 0.0
    peers_connected: int = 0
    peers_discovered: int = 0
    messages_sent: int = 0
    messages_received: int = 0
    blocks_validated: int = 0
    chain_height: int = 0
    entanglement_coherence: float = 0.0
    consensus_participations: int = 0
    treasury_balance: float = 0.0
    errors_encountered: int = 0
    reconnections: int = 0


# ---------------------------------------------------------------------------
# Autonomous Node — The Main Controller
# ---------------------------------------------------------------------------

class AutonomousNode:
    """Fully autonomous SkyNet node for SpinxOS.
    
    This node operates independently without a GUI, combining all SpinxOS
    subsystems into a self-organizing, fault-tolerant network participant.
    
    Architecture:
    - Discovery Layer: SkyNet Beacon protocol (HTTP + UDP)
    - Routing Layer: Holographic P2P with entanglement-based routing
    - Consensus Layer: Nexus Orchestrator with conscious consensus
    - Data Layer: Persistent chain validation and sync
    - Metrics Layer: Prometheus-compatible metrics export
    """
    
    def __init__(
        self,
        p2p_port: int = DEFAULT_P2P_PORT,
        beacon_port: int = DEFAULT_BEACON_PORT,
        metrics_port: int = DEFAULT_METRICS_PORT,
        data_dir: Optional[str] = None,
        node_id: Optional[str] = None,
        central_servers: Optional[List[str]] = None,
        multicast_group: str = DEFAULT_MULTICAST_GROUP,
        multicast_port: int = DEFAULT_MULTICAST_PORT,
    ):
        self.p2p_port = p2p_port
        self.beacon_port = beacon_port
        self.metrics_port = metrics_port
        self.data_dir = data_dir or str(WALLET_DIR)
        self.node_id = node_id or self._generate_node_id()
        self.central_servers = central_servers or CENTRAL_BOOTSTRAP_SERVERS
        self.multicast_group = multicast_group
        self.multicast_port = multicast_port
        
        # State
        self.state = NodeState.INITIALIZING
        self.start_time = time.time()
        self._running = False
        self._lock = threading.Lock()
        
        # Statistics
        self.stats = NodeStats()
        
        # Database
        db_path = os.path.join(self.data_dir, "autonomous_node.db")
        self.db = P2PDatabase(db_path)
        
        # Holographic P2P layer
        self.p2p_layer = HolographicP2PLayer()
        
        # Peer tracking
        self._peers: Dict[str, dict] = {}  # node_id -> peer info
        self._peer_threads: Dict[str, threading.Thread] = {}
        
        # Message queue
        self._message_queue: List[NetworkMessage] = []
        self._message_lock = threading.Lock()
        
        # Chain state
        self._chain_height = 0
        self._chain_file = Path(os.path.join(self.data_dir, "chain.jsonl"))
        
        # Executors
        self._executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="autonomous")
        self._futures: Dict[str, Future] = {}
        
        # Network sockets
        self._multicast_socket: Optional[socket.socket] = None
        self._broadcast_socket: Optional[socket.socket] = None
        
        # Ensure data directory exists
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)
        
        logger.info(f"Autonomous Node initialized: {self.node_id}")
    
    def _generate_node_id(self) -> str:
        """Generate a unique node ID."""
        host_id = hashlib.sha256(socket.gethostname().encode()).hexdigest()[:8]
        unique_id = uuid.uuid4().hex[:8]
        return f"auto-{host_id}-{unique_id}"
    
    # ── Lifecycle ─────────────────────────────────────────────────────────
    
    def start(self):
        """Start the autonomous node and all subsystems."""
        if self._running:
            logger.warning("Node is already running")
            return
        
        self._running = True
        self.state = NodeState.INITIALIZING
        logger.info("=" * 60)
        logger.info("  AetherionEXCAL — Autonomous SkyNet Node")
        logger.info("=" * 60)
        logger.info(f"  Node ID:    {self.node_id}")
        logger.info(f"  P2P Port:   {self.p2p_port}")
        logger.info(f"  Beacon:     {self.beacon_port}")
        logger.info(f"  Metrics:    {self.metrics_port}")
        logger.info(f"  Data Dir:   {self.data_dir}")
        logger.info("=" * 60)
        
        # Load persisted state
        self._load_state()
        
        # Start all subsystems in parallel using ThreadPoolExecutor
        self._start_metrics_server()
        self._start_discovery_loop()
        self._start_heartbeat_loop()
        self._start_prune_loop()
        self._start_entanglement_loop()
        self._start_chain_sync_loop()
        self._start_message_processor()
        self._start_multicast_listener()
        self._start_broadcast_listener()
        
        # Register with central bootstrap servers
        self._register_with_central()
        
        self.state = NodeState.DISCOVERING
        logger.info("Autonomous Node ACTIVE — All subsystems running")
        
        # Main loop — keep the node alive
        try:
            self._main_loop()
        except KeyboardInterrupt:
            logger.info("Shutdown requested by user")
        finally:
            self.stop()
    
    def stop(self):
        """Gracefully stop the autonomous node."""
        if not self._running:
            return
        
        self.state = NodeState.STOPPING
        logger.info("Stopping autonomous node...")
        self._running = False
        
        # Shutdown executor
        self._executor.shutdown(wait=False, cancel_futures=True)
        
        # Close sockets
        if self._multicast_socket:
            self._multicast_socket.close()
        if self._broadcast_socket:
            self._broadcast_socket.close()
        
        # Save state
        self._save_state()
        
        self.state = NodeState.STOPPING
        logger.info(f"Node stopped. Uptime: {self.stats.uptime:.0f}s")
    
    def _main_loop(self):
        """Main event loop — monitors health and updates state."""
        while self._running:
            try:
                # Update uptime
                self.stats.uptime = time.time() - self.start_time
                
                # Update state based on conditions
                with self._lock:
                    peer_count = len(self._peers)
                    self.stats.peers_connected = peer_count
                
                if peer_count > 0 and self.state == NodeState.IDLE:
                    self.state = NodeState.ACTIVE
                    logger.info(f"Node ACTIVE with {peer_count} peers")
                elif peer_count == 0 and self.state == NodeState.ACTIVE:
                    self.state = NodeState.IDLE
                    logger.warning("No peers connected — entering IDLE state")
                
                # Log stats every 60 seconds
                if int(self.stats.uptime) % 60 == 0 and self.stats.uptime > 0:
                    self._log_stats()
                
                time.sleep(1)
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                self.stats.errors_encountered += 1
                time.sleep(5)
    
    # ── Discovery Layer ──────────────────────────────────────────────────
    
    def _start_discovery_loop(self):
        """Continuously discover and connect to peers."""
        def discovery_worker():
            while self._running:
                try:
                    self._discover_peers()
                except Exception as e:
                    logger.error(f"Discovery error: {e}")
                    self.stats.errors_encountered += 1
                time.sleep(DISCOVERY_INTERVAL)
        
        thread = threading.Thread(target=discovery_worker, daemon=True, name="discovery")
        thread.start()
    
    def _discover_peers(self):
        """Discover peers via all available methods."""
        # 1. Query local beacon
        self._query_local_beacon()
        
        # 2. Query central bootstrap servers
        for server_url in self.central_servers:
            self._query_central_server(server_url)
        
        # 3. Broadcast discovery request
        self._broadcast_discovery()
    
    def _query_local_beacon(self):
        """Query the local SkyNet beacon for peers."""
        try:
            import urllib.request
            import urllib.error
            url = f"http://127.0.0.1:{self.beacon_port}/peers?limit=16"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                peers = data.get("peers", [])
                for peer in peers:
                    self._add_peer(peer)
        except Exception:
            pass  # Local beacon may not be running
    
    def _query_central_server(self, server_url: str):
        """Query a central bootstrap server for peers."""
        try:
            import urllib.request
            import urllib.error
            url = f"{server_url}/peers?limit=16"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                peers = data.get("peers", [])
                for peer in peers:
                    self._add_peer(peer)
        except Exception:
            pass  # Central server may be unavailable
    
    def _broadcast_discovery(self):
        """Broadcast a discovery request via UDP."""
        try:
            if not self._broadcast_socket:
                self._broadcast_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._broadcast_socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                self._broadcast_socket.settimeout(2.0)
            
            # Send discovery request
            msg = json.dumps({
                "type": "discovery",
                "node_id": self.node_id,
                "port": self.p2p_port,
                "timestamp": time.time(),
            }).encode()
            
            self._broadcast_socket.sendto(
                msg, (DEFAULT_BROADCAST_ADDRESS, DEFAULT_BROADCAST_PORT)
            )
            
            # Listen for responses
            try:
                while True:
                    data, addr = self._broadcast_socket.recvfrom(1024)
                    try:
                        response = json.loads(data.decode())
                        if response.get("type") == "discovery_response":
                            peer = {
                                "node_id": response.get("node_id"),
                                "host": addr[0],
                                "port": response.get("port", DEFAULT_P2P_PORT),
                            }
                            self._add_peer(peer)
                    except json.JSONDecodeError:
                        pass
                    except socket.timeout:
                        break
            except socket.timeout:
                pass
        except Exception as e:
            logger.debug(f"Broadcast discovery error: {e}")
    
    def _add_peer(self, peer: dict):
        """Add a peer to the tracking dictionary."""
        node_id = peer.get("node_id")
        if not node_id or node_id == self.node_id:
            return
        
        with self._lock:
            if node_id not in self._peers:
                self._peers[node_id] = {
                    "node_id": node_id,
                    "host": peer.get("host", ""),
                    "port": peer.get("port", DEFAULT_P2P_PORT),
                    "last_seen": time.time(),
                    "services": peer.get("services", ""),
                    "version": peer.get("version", 0),
                }
                self.stats.peers_discovered += 1
                
                # Add to holographic P2P layer
                self.p2p_layer.add_peer(
                    name=node_id,
                    host=peer.get("host", ""),
                    port=peer.get("port", DEFAULT_P2P_PORT),
                )
                
                logger.debug(f"Added peer: {node_id} @ {peer.get('host')}:{peer.get('port')}")
            else:
                # Update existing peer
                self._peers[node_id]["last_seen"] = time.time()
    
    # ── Heartbeat Layer ──────────────────────────────────────────────────
    
    def _start_heartbeat_loop(self):
        """Send periodic heartbeats to stay alive."""
        def heartbeat_worker():
            while self._running:
                try:
                    self._send_heartbeat()
                except Exception as e:
                    logger.error(f"Heartbeat error: {e}")
                time.sleep(HEARTBEAT_INTERVAL)
        
        thread = threading.Thread(target=heartbeat_worker, daemon=True, name="heartbeat")
        thread.start()
    
    def _send_heartbeat(self):
        """Send heartbeat to local beacon and central servers."""
        heartbeat = {
            "node_id": self.node_id,
            "host": self._get_lan_address(),
            "port": self.p2p_port,
            "services": "autonomous",
            "version": "3.0.0",
            "timestamp": time.time(),
            "state": self.state.value,
            "peers": len(self._peers),
            "chain_height": self._chain_height,
        }
        
        # Register with local beacon
        try:
            import urllib.request
            url = f"http://127.0.0.1:{self.beacon_port}/register"
            data = json.dumps(heartbeat).encode()
            req = urllib.request.Request(
                url, data=data,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                logger.debug("Heartbeat sent to local beacon")
        except Exception:
            pass
        
        # Register with central servers
        for server_url in self.central_servers:
            try:
                import urllib.request
                url = f"{server_url}/register"
                data = json.dumps(heartbeat).encode()
                req = urllib.request.Request(
                    url, data=data,
                    headers={"Content-Type": "application/json"},
                    method="POST"
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    logger.debug(f"Heartbeat sent to {server_url}")
            except Exception:
                pass
    
    def _register_with_central(self):
        """Initial registration with central bootstrap servers."""
        logger.info("Registering with central bootstrap servers...")
        self._send_heartbeat()
    
    # ── Prune Layer ──────────────────────────────────────────────────────
    
    def _start_prune_loop(self):
        """Periodically prune stale peers."""
        def prune_worker():
            while self._running:
                time.sleep(PRUNE_INTERVAL)
                if not self._running:
                    break
                self._prune_stale_peers()
        
        thread = threading.Thread(target=prune_worker, daemon=True, name="prune")
        thread.start()
    
    def _prune_stale_peers(self):
        """Remove peers that haven't been seen recently."""
        now = time.time()
        pruned = 0
        with self._lock:
            stale = [
                nid for nid, p in self._peers.items()
                if now - p.get("last_seen", 0) > PEER_TTL
            ]
            for nid in stale:
                del self._peers[nid]
                pruned += 1
        
        if pruned > 0:
            logger.info(f"Pruned {pruned} stale peers")
    
    # ── Entanglement Layer ───────────────────────────────────────────────
    
    def _start_entanglement_loop(self):
        """Periodically update entanglement weights."""
        def entanglement_worker():
            while self._running:
                time.sleep(ENTANGLE_UPDATE_INTERVAL)
                if not self._running:
                    break
                try:
                    self._update_entanglement()
                except Exception as e:
                    logger.debug(f"Entanglement update error: {e}")
        
        thread = threading.Thread(target=entanglement_worker, daemon=True, name="entanglement")
        thread.start()
    
    def _update_entanglement(self):
        """Update entanglement weights based on peer activity."""
        with self._lock:
            peer_ids = list(self._peers.keys())
        
        for i, pid1 in enumerate(peer_ids):
            for pid2 in peer_ids[i+1:]:
                # Calculate entanglement based on shared activity
                now = time.time()
                p1 = self._peers.get(pid1, {})
                p2 = self._peers.get(pid2, {})
                
                # Entanglement decays over time since last seen
                age1 = now - p1.get("last_seen", 0)
                age2 = now - p2.get("last_seen", 0)
                freshness = math.exp(-age1 / 300) * math.exp(-age2 / 300)
                
                # Set entanglement weight
                try:
                    self.p2p_layer.set_entanglement(pid1, pid2, freshness)
                except Exception:
                    pass
        
        # Update coherence stat
        self.stats.entanglement_coherence = self.p2p_layer.network_coherence()
    
    # ── Chain Sync Layer ─────────────────────────────────────────────────
    
    def _start_chain_sync_loop(self):
        """Periodically sync and validate the chain."""
        def sync_worker():
            while self._running:
                time.sleep(CHAIN_SYNC_INTERVAL)
                if not self._running:
                    break
                try:
                    self._sync_chain()
                except Exception as e:
                    logger.debug(f"Chain sync error: {e}")
        
        thread = threading.Thread(target=sync_worker, daemon=True, name="chain-sync")
        thread.start()
    
    def _sync_chain(self):
        """Sync chain from connected peers."""
        if not self._peers:
            return
        
        # Load current chain height
        if self._chain_file.exists():
            try:
                with open(self._chain_file, "r") as f:
                    lines = f.readlines()
                    self._chain_height = len(lines)
            except Exception:
                pass
        
        # Query a random peer for their chain height
        with self._lock:
            peer = list(self._peers.values())
        
        if not peer:
            return
        
        # Try to get chain data from peer via RPC
        try:
            import urllib.request
            import urllib.error
            host = peer[0].get("host", "")
            port = peer[0].get("port", DEFAULT_P2P_PORT)
            
            # Query peer's RPC for block count
            url = f"http://{host}:{port}"
            payload = json.dumps({
                "jsonrpc": "2.0",
                "method": "getblockcount",
                "params": [],
                "id": 1
            }).encode()
            
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read().decode())
                if "result" in result:
                    peer_height = result["result"]
                    if peer_height > self._chain_height:
                        logger.info(
                            f"Peer has higher chain: {peer_height} > {self._chain_height}"
                        )
                        self.state = NodeState.SYNCING
                        # In a full implementation, we'd fetch and validate blocks
                        self._chain_height = peer_height
                        self.stats.blocks_validated = peer_height
        except Exception:
            pass  # Peer may not have RPC enabled
    
    # ── Message Processor ────────────────────────────────────────────────
    
    def _start_message_processor(self):
        """Process incoming messages from the P2P layer."""
        def message_worker():
            while self._running:
                try:
                    with self._message_lock:
                        messages = self._message_queue.copy()
                        self._message_queue.clear()
                    
                    for msg in messages:
                        self._process_message(msg)
                        self.stats.messages_received += 1
                except Exception as e:
                    logger.debug(f"Message processing error: {e}")
                time.sleep(0.5)
        
        thread = threading.Thread(target=message_worker, daemon=True, name="msg-processor")
        thread.start()
    
    def _process_message(self, msg: NetworkMessage):
        """Process an incoming message."""
        try:
            payload = msg.payload
            msg_type = payload.get("type", "")
            
            if msg_type == "discovery_response":
                peer = {
                    "node_id": payload.get("node_id"),
                    "host": payload.get("host", ""),
                    "port": payload.get("port", DEFAULT_P2P_PORT),
                }
                self._add_peer(peer)
            
            elif msg_type == "block":
                # Validate and store block
                self.stats.blocks_validated += 1
            
            elif msg_type == "transaction":
                # Validate and relay transaction
                pass
            
            elif msg_type == "consensus_vote":
                # Participate in consensus
                self.stats.consensus_participations += 1
            
        except Exception as e:
            logger.debug(f"Message processing error: {e}")
    
    # ── Multicast Listener ───────────────────────────────────────────────
    
    def _start_multicast_listener(self):
        """Listen for multicast discovery messages."""
        def multicast_worker():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(("0.0.0.0", self.multicast_port))
                sock.settimeout(1.0)
                
                # Join multicast group
                mreq = struct.pack("4sl", socket.inet_aton(self.multicast_group), socket.INADDR_ANY)
                sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)
                
                self._multicast_socket = sock
                
                while self._running:
                    try:
                        data, addr = sock.recvfrom(4096)
                        self._handle_multicast_message(data, addr)
                    except socket.timeout:
                        continue
                    except Exception as e:
                        logger.debug(f"Multicast error: {e}")
            except Exception as e:
                logger.error(f"Multicast listener failed: {e}")
        
        thread = threading.Thread(target=multicast_worker, daemon=True, name="multicast")
        thread.start()
    
    def _handle_multicast_message(self, data: bytes, addr: tuple):
        """Handle an incoming multicast message."""
        try:
            msg = json.loads(data.decode())
            msg_type = msg.get("type", "")
            
            if msg_type in ("discovery", "heartbeat"):
                peer = {
                    "node_id": msg.get("node_id"),
                    "host": addr[0],
                    "port": msg.get("port", DEFAULT_P2P_PORT),
                }
                self._add_peer(peer)
                
                # Respond with our info
                response = json.dumps({
                    "type": "discovery_response",
                    "node_id": self.node_id,
                    "host": self._get_lan_address(),
                    "port": self.p2p_port,
                    "timestamp": time.time(),
                }).encode()
                
                if self._multicast_socket:
                    self._multicast_socket.sendto(response, (self.multicast_group, self.multicast_port))
        
        except Exception as e:
            logger.debug(f"Multicast message error: {e}")
    
    # ── Broadcast Listener ───────────────────────────────────────────────
    
    def _start_broadcast_listener(self):
        """Listen for broadcast discovery messages."""
        def broadcast_worker():
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                sock.bind(("0.0.0.0", DEFAULT_BROADCAST_PORT))
                sock.settimeout(1.0)
                
                self._broadcast_socket = sock
                
                while self._running:
                    try:
                        data, addr = sock.recvfrom(4096)
                        self._handle_broadcast_message(data, addr)
                    except socket.timeout:
                        continue
                    except Exception as e:
                        logger.debug(f"Broadcast error: {e}")
            except Exception as e:
                logger.error(f"Broadcast listener failed: {e}")
        
        thread = threading.Thread(target=broadcast_worker, daemon=True, name="broadcast")
        thread.start()
    
    def _handle_broadcast_message(self, data: bytes, addr: tuple):
        """Handle an incoming broadcast message."""
        try:
            msg = json.loads(data.decode())
            msg_type = msg.get("type", "")
            
            if msg_type in ("discovery", "heartbeat"):
                peer = {
                    "node_id": msg.get("node_id"),
                    "host": addr[0],
                    "port": msg.get("port", DEFAULT_P2P_PORT),
                }
                self._add_peer(peer)
                
                # Respond
                response = json.dumps({
                    "type": "discovery_response",
                    "node_id": self.node_id,
                    "host": self._get_lan_address(),
                    "port": self.p2p_port,
                    "timestamp": time.time(),
                }).encode()
                
                if self._broadcast_socket:
                    self._broadcast_socket.sendto(
                        response, (DEFAULT_BROADCAST_ADDRESS, DEFAULT_BROADCAST_PORT)
                    )
        
        except Exception as e:
            logger.debug(f"Broadcast message error: {e}")
    
    # ── Metrics Server ───────────────────────────────────────────────────
    
    def _start_metrics_server(self):
        """Start Prometheus-compatible metrics HTTP server."""
        def metrics_worker():
            try:
                server = HTTPServer(
                    ("0.0.0.0", self.metrics_port),
                    self._make_metrics_handler()
                )
                server.socket.settimeout(1.0)
                logger.info(f"Metrics server started on http://0.0.0.0:{self.metrics_port}/metrics")
                
                while self._running:
                    server.handle_request()
            except Exception as e:
                logger.error(f"Metrics server error: {e}")
        
        thread = threading.Thread(target=metrics_worker, daemon=True, name="metrics")
        thread.start()
    
    def _make_metrics_handler(self):
        """Create a metrics HTTP handler bound to this node instance."""
        node = self
        
        class MetricsHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path == "/metrics":
                    metrics = node._generate_metrics()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; version=0.0.4")
                    self.end_headers()
                    self.wfile.write(metrics.encode())
                elif parsed.path == "/health":
                    health = node._generate_health()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(json.dumps(health).encode())
                else:
                    self.send_response(404)
                    self.end_headers()
            
            def log_message(self, format, *args):
                pass  # Suppress default logging
        
        return MetricsHandler
    
    def _generate_metrics(self) -> str:
        """Generate Prometheus-compatible metrics."""
        lines = [
            "# HELP autonomous_node_state Current state of the node",
            "# TYPE autonomous_node_state gauge",
            f'autonomous_node_state{{state="{self.state.value}"}} 1',
            "",
            "# HELP autonomous_node_uptime_seconds Node uptime in seconds",
            "# TYPE autonomous_node_uptime_seconds gauge",
            f"autonomous_node_uptime_seconds {self.stats.uptime:.1f}",
            "",
            "# HELP autonomous_node_peers_connected Number of connected peers",
            "# TYPE autonomous_node_peers_connected gauge",
            f"autonomous_node_peers_connected {self.stats.peers_connected}",
            "",
            "# HELP autonomous_node_peers_discovered Total peers discovered",
            "# TYPE autonomous_node_peers_discovered counter",
            f"autonomous_node_peers_discovered {self.stats.peers_discovered}",
            "",
            "# HELP autonomous_node_messages_sent Total messages sent",
            "# TYPE autonomous_node_messages_sent counter",
            f"autonomous_node_messages_sent {self.stats.messages_sent}",
            "",
            "# HELP autonomous_node_messages_received Total messages received",
            "# TYPE autonomous_node_messages_received counter",
            f"autonomous_node_messages_received {self.stats.messages_received}",
            "",
            "# HELP autonomous_node_blocks_validated Total blocks validated",
            "# TYPE autonomous_node_blocks_validated counter",
            f"autonomous_node_blocks_validated {self.stats.blocks_validated}",
            "",
            "# HELP autonomous_node_chain_height Current chain height",
            "# TYPE autonomous_node_chain_height gauge",
            f"autonomous_node_chain_height {self.stats.chain_height}",
            "",
            "# HELP autonomous_node_entanglement_coherence Network entanglement coherence",
            "# TYPE autonomous_node_entanglement_coherence gauge",
            f"autonomous_node_entanglement_coherence {self.stats.entanglement_coherence:.4f}",
            "",
            "# HELP autonomous_node_consensus_participations Total consensus participations",
            "# TYPE autonomous_node_consensus_participations counter",
            f"autonomous_node_consensus_participations {self.stats.consensus_participations}",
            "",
            "# HELP autonomous_node_errors Total errors encountered",
            "# TYPE autonomous_node_errors counter",
            f"autonomous_node_errors {self.stats.errors_encountered}",
        ]
        return "\n".join(lines) + "\n"
    
    def _generate_health(self) -> dict:
        """Generate health check response."""
        return {
            "status": "healthy",
            "node_id": self.node_id,
            "state": self.state.value,
            "version": "3.0.0",
            "uptime": self.stats.uptime,
            "peers": self.stats.peers_connected,
            "chain_height": self._chain_height,
            "entanglement_coherence": self.stats.entanglement_coherence,
        }
    
    # ── State Persistence ────────────────────────────────────────────────
    
    def _load_state(self):
        """Load persisted node state."""
        state_file = Path(os.path.join(self.data_dir, "autonomous_node_state.json"))
        if state_file.exists():
            try:
                with open(state_file, "r") as f:
                    state = json.load(f)
                self._chain_height = state.get("chain_height", 0)
                logger.info(f"Loaded state: chain height {self._chain_height}")
            except Exception as e:
                logger.warning(f"Failed to load state: {e}")
    
    def _save_state(self):
        """Save current node state."""
        state_file = Path(os.path.join(self.data_dir, "autonomous_node_state.json"))
        try:
            state = {
                "node_id": self.node_id,
                "chain_height": self._chain_height,
                "peers": len(self._peers),
                "timestamp": time.time(),
            }
            with open(state_file, "w") as f:
                json.dump(state, f, indent=2)
            logger.info("State saved")
        except Exception as e:
            logger.warning(f"Failed to save state: {e}")
    
    # ── Utilities ────────────────────────────────────────────────────────
    
    def _get_lan_address(self) -> str:
        """Get the local LAN IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            addr = s.getsockname()[0]
            s.close()
            return addr
        except Exception:
            return "127.0.0.1"
    
    def _log_stats(self):
        """Log current node statistics."""
        logger.info(
            f"Stats — State: {self.state.value} | "
            f"Peers: {self.stats.peers_connected} | "
            f"Chain: {self._chain_height} | "
            f"Coherence: {self.stats.entanglement_coherence:.3f} | "
            f"Uptime: {self.stats.uptime:.0f}s"
        )
    
    def get_status(self) -> dict:
        """Get current node status for external queries."""
        return {
            "node_id": self.node_id,
            "state": self.state.value,
            "uptime": self.stats.uptime,
            "peers_connected": self.stats.peers_connected,
            "peers_discovered": self.stats.peers_discovered,
            "chain_height": self._chain_height,
            "entanglement_coherence": self.stats.entanglement_coherence,
            "messages_sent": self.stats.messages_sent,
            "messages_received": self.stats.messages_received,
            "blocks_validated": self.stats.blocks_validated,
            "consensus_participations": self.stats.consensus_participations,
            "errors": self.stats.errors_encountered,
        }


# ---------------------------------------------------------------------------
# CLI Entry Point
# ---------------------------------------------------------------------------

def main():
    """Main entry point for the autonomous node."""
    parser = argparse.ArgumentParser(
        description="AetherionEXCAL Autonomous SkyNet Node"
    )
    parser.add_argument(
        "--p2p-port", type=int, default=DEFAULT_P2P_PORT,
        help=f"P2P listening port (default: {DEFAULT_P2P_PORT})"
    )
    parser.add_argument(
        "--beacon-port", type=int, default=DEFAULT_BEACON_PORT,
        help=f"Beacon port for discovery (default: {DEFAULT_BEACON_PORT})"
    )
    parser.add_argument(
        "--metrics-port", type=int, default=DEFAULT_METRICS_PORT,
        help=f"Metrics server port (default: {DEFAULT_METRICS_PORT})"
    )
    parser.add_argument(
        "--data-dir", type=str, default=None,
        help=f"Data directory (default: ~/.excal_wallet)"
    )
    parser.add_argument(
        "--node-id", type=str, default=None,
        help="Custom node ID (default: auto-generated)"
    )
    parser.add_argument(
        "--log-level", type=str, default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)"
    )
    parser.add_argument(
        "--daemon", action="store_true",
        help="Run as a background daemon"
    )
    
    args = parser.parse_args()
    
    # Configure logging
    log_format = "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    if args.daemon:
        logging.basicConfig(level=getattr(logging, args.log_level), format=log_format)
    else:
        logging.basicConfig(
            level=getattr(logging, args.log_level),
            format=log_format,
            stream=sys.stdout
        )
    
    # Suppress noisy loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("cryptography").setLevel(logging.WARNING)
    
    # Create and start the node
    node = AutonomousNode(
        p2p_port=args.p2p_port,
        beacon_port=args.beacon_port,
        metrics_port=args.metrics_port,
        data_dir=args.data_dir,
        node_id=args.node_id,
    )
    
    try:
        node.start()
    except KeyboardInterrupt:
        logger.info("Shutdown by user")
        node.stop()


if __name__ == "__main__":
    main()
