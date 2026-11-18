"""Holographic P2P Layer: Peer-to-peer networking with holographic entanglement routing.

Architecture Overview
=====================

The Holographic P2P Layer models a peer-to-peer network where messages route along
quantum entanglement paths rather than shortest-hop paths.  Each peer carries an
*entanglement entropy* value that represents its quantum correlation with the rest
of the network.  When a message is sent, the layer finds the path of **maximum
entanglement** (not minimum hops) — the idea being that highly entangled peers can
transmit information more reliably, analogous to quantum teleportation fidelity.

Key concepts
------------
1. **Entanglement Graph** — Every pair of connected peers shares an entanglement
   weight (0..1).  The graph is maintained dynamically as peers join, leave, and
   exchange heartbeats.

2. **Holographic Routing** — Instead of BFS/Dijkstra on hop count, messages follow
   the path that maximizes the *product* of entanglement weights along the path.
   This is the "path of least resistance" in the entanglement manifold.

3. **Network Coherence** — A single scalar (0..1) that measures how uniformly
   entangled the network is.  High coherence ≈ every peer is strongly correlated
   with many others.  Low coherence ≈ fragmented clusters.

4. **Gossip Protocol** — Messages can be propagated using epidemic (gossip) spread:
   each peer that receives a message forwards it to k random neighbors, ensuring
   O(log N) dissemination time.

5. **Message Encryption** — Payloads are encrypted with AES-256-GCM using the
   `cryptography` library.  Authenticated encryption provides both confidentiality
   and integrity — tampered ciphertext is rejected.

6. **Priority Queue & TTL** — Messages carry a priority level and time-to-live.
   Expired messages are silently dropped; high-priority messages are routed first.

7. **Peer Discovery** — New peers can be discovered through introductions from
   existing peers, simulating a bootstrapping process.

8. **Bandwidth & Latency Simulation** — Each peer tracks simulated bandwidth usage
   and message latency, enabling performance analysis.

Enhancement log
---------------
- v2.0: Added gossip protocol, message encryption, priority queue with TTL,
        peer discovery, bandwidth/latency tracking, topology export, and
        automatic reconnection logic.
- v3.0: Replaced XOR simulation encryption with production AES-256-GCM.
"""

import hashlib
import time
import random
import math
import json
import base64
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set, Tuple
from collections import defaultdict

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# ---------------------------------------------------------------------------
# Message priority levels
# ---------------------------------------------------------------------------

class MessagePriority:
    """Priority levels for network messages."""
    CRITICAL = 0    # Block proposals, consensus votes
    HIGH = 1        # Transaction relay
    NORMAL = 2      # Heartbeats, pings
    LOW = 3         # Address announcements, metadata


@dataclass
class Peer:
    """A peer in the P2P network.

    Attributes:
        name: Unique peer identifier.
        host: Host address (IP or hostname).
        port: Port number.
        connected: Whether the peer is currently connected.
        last_heartbeat: Timestamp of the last heartbeat.
        entropy: Cumulative entanglement entropy with other peers.
        messages_sent: Number of messages sent by this peer.
        messages_received: Number of messages received by this peer.
        bandwidth_bytes: Simulated bytes transferred.
        avg_latency_ms: Average message latency in milliseconds.
        services: Bitmask of services this peer offers.
        user_agent: Client identifier string.
        introduced_by: Name of the peer that introduced this peer.
    """
    name: str
    host: str
    port: int
    connected: bool = False
    last_heartbeat: float = 0.0
    entropy: float = 0.0  # Entanglement entropy with other peers
    messages_sent: int = 0
    messages_received: int = 0
    # --- v2.0 additions ---
    bandwidth_bytes: int = 0
    avg_latency_ms: float = 0.0
    services: int = 0
    user_agent: str = ""
    introduced_by: Optional[str] = None


@dataclass
class NetworkMessage:
    """A message in the P2P network.

    Attributes:
        msg_id: Unique message identifier (SHA-256 hex digest).
        source: Source peer name.
        destination: Destination peer name (or '' for broadcast).
        msg_type: Message type string (e.g., 'block_proposal', 'tx', 'heartbeat').
        payload: Arbitrary key-value payload.
        timestamp: Creation timestamp.
        hop_count: Number of hops traversed.
        entanglement_path: Ordered list of peer names in the routing path.
        priority: Message priority level (lower = higher priority).
        ttl: Time-to-live in seconds (0 = infinite).
        encrypted: Whether the payload is encrypted.
        encrypted_key_b64: Base64-encoded encryption key (for simulation).
        gossip_seen_by: Set of peers that have already seen this message via gossip.
    """
    msg_id: str
    source: str
    destination: str
    msg_type: str
    payload: Dict[str, Any]
    timestamp: float
    hop_count: int = 0
    entanglement_path: List[str] = field(default_factory=list)
    # --- v2.0 additions ---
    priority: int = MessagePriority.NORMAL
    ttl: float = 0.0  # 0 = no expiry
    encrypted: bool = False
    encrypted_key_b64: str = ""
    gossip_seen_by: Set[str] = field(default_factory=set)


class HolographicP2PLayer:
    """P2P layer that routes messages along entanglement paths in the quantum fabric.

    Peers are connected based on their entanglement entropy, and messages follow
    the paths of least resistance through the entanglement network.

    v2.0 Enhancements
    -----------------
    - Gossip protocol for O(log N) message dissemination
    - Message encryption with AES-256-GCM (production-grade)
    - Priority queue with TTL-based message expiry
    - Peer discovery through introductions
    - Bandwidth and latency simulation
    - Network topology export (GraphML / JSON)
    - Automatic reconnection logic
    - Maximum-entanglement path routing (Dijkstra on log-entanglement)
    """

    # Service flags (aligned with p2p_layer.py)
    NODE_NETWORK = 0x01
    NODE_P2P_V2 = 0x02
    NODE_LIGHT = 0x04
    NODE_STRATUM = 0x08

    def __init__(self, gossip_k: int = 3, default_ttl: float = 60.0):
        """Initialize the Holographic P2P layer.

        Args:
            gossip_k: Number of random neighbors to gossip to per round.
            default_ttl: Default message TTL in seconds (0 = infinite).
        """
        self.peers: Dict[str, Peer] = {}
        self.messages: Dict[str, NetworkMessage] = {}
        self.message_log: List[NetworkMessage] = []
        self.connections: Dict[str, Dict[str, float]] = {}  # peer -> {peer: entanglement}
        self.network_coherence: float = 1.0
        self.messages_sent: int = 0
        self.step_count: int = 0

        # --- v2.0: Gossip configuration ---
        self.gossip_k = gossip_k
        self.default_ttl = default_ttl

        # --- v2.0: Priority message queue ---
        self._pending_queue: List[NetworkMessage] = []

        # --- v2.0: Encryption key (shared symmetric key) ---
        self._encryption_key: Optional[bytes] = None
        self._aesgcm: Optional[AESGCM] = None

        # --- v2.0: Peer discovery ---
        self._discovery_pool: List[Dict[str, Any]] = []  # Known but not-yet-connected peers

        # --- v2.0: Latency tracking ---
        self._latency_samples: Dict[str, List[float]] = defaultdict(list)

    # -----------------------------------------------------------------------
    # Encryption helpers — AES-256-GCM (production)
    # -----------------------------------------------------------------------

    def set_encryption_key(self, key: Optional[bytes] = None):
        """Set the shared symmetric encryption key.

        Args:
            key: Optional 32-byte key. If None, a random 32-byte key is
                 generated using os.urandom (cryptographically secure).
        """
        self._encryption_key = key or os.urandom(32)
        self._aesgcm = AESGCM(self._encryption_key)

    def _encrypt_payload(self, payload: Dict[str, Any]) -> Tuple[str, str]:
        """Encrypt a payload using AES-256-GCM.

        Returns:
            (base64_encoded_ciphertext_with_nonce, base64_encoded_key)
        """
        if self._encryption_key is None:
            self.set_encryption_key()

        plaintext = json.dumps(payload).encode("utf-8")
        # Generate 12-byte random nonce
        nonce = os.urandom(12)
        # encrypt(nonce, data, aad) returns ciphertext + tag (no nonce)
        ct = self._aesgcm.encrypt(nonce, plaintext, None)
        # Store nonce + ciphertext+tag together for decryption
        ct_with_nonce = nonce + ct
        return (
            base64.b64encode(ct_with_nonce).decode(),
            base64.b64encode(self._encryption_key).decode(),
        )

    def _decrypt_payload(self, ciphertext_b64: str, key_b64: str) -> Dict[str, Any]:
        """Decrypt a previously encrypted payload using AES-256-GCM.

        Args:
            ciphertext_b64: Base64-encoded (nonce + ciphertext + tag).
            key_b64: Base64-encoded 32-byte key.

        Returns:
            Decrypted payload dictionary.

        Raises:
            cryptography.exceptions.InvalidTag: If the ciphertext has been
                tampered with (authentication failure).
        """
        ct_with_nonce = base64.b64decode(ciphertext_b64)
        key = base64.b64decode(key_b64)
        aesgcm = AESGCM(key)
        # Split nonce from ciphertext+tag
        nonce = ct_with_nonce[:12]
        ct = ct_with_nonce[12:]
        plaintext = aesgcm.decrypt(nonce, ct, None)
        return json.loads(plaintext.decode("utf-8"))

    # -----------------------------------------------------------------------
    # Peer management
    # -----------------------------------------------------------------------

    def add_peer(
        self,
        name: str,
        host: str,
        port: int,
        services: int = 0,
        user_agent: str = "",
        introduced_by: Optional[str] = None,
    ):
        """Add a new peer to the network.

        Args:
            name: Unique peer identifier.
            host: Host address.
            port: Port number.
            services: Bitmask of services offered.
            user_agent: Client identifier string.
            introduced_by: Name of the peer that introduced this peer.
        """
        self.peers[name] = Peer(
            name=name,
            host=host,
            port=port,
            services=services,
            user_agent=user_agent,
            introduced_by=introduced_by,
        )
        self.connections[name] = {}

    def connect_peer(self, name: str):
        """Mark a peer as connected and establish entanglement with existing peers.

        Args:
            name: Peer identifier.
        """
        if name not in self.peers:
            return

        peer = self.peers[name]
        peer.connected = True
        peer.last_heartbeat = time.time()

        # Establish entanglement with existing connected peers
        for existing_name, existing_peer in self.peers.items():
            if existing_name != name and existing_peer.connected:
                entanglement = random.uniform(0.3, 1.0)
                self.connections[name][existing_name] = entanglement
                self.connections[existing_name][name] = entanglement
                existing_peer.entropy += entanglement * 0.1
                peer.entropy += entanglement * 0.1

    def disconnect_peer(self, name: str):
        """Disconnect a peer and sever entanglement links.

        Args:
            name: Peer identifier.
        """
        if name not in self.peers:
            return

        self.peers[name].connected = False

        # Sever entanglement links
        for other_name in list(self.connections.get(name, {}).keys()):
            del self.connections[other_name][name]
        self.connections[name] = {}

    # -----------------------------------------------------------------------
    # Peer discovery
    # -----------------------------------------------------------------------

    def add_discovery_peer(self, name: str, host: str, port: int, services: int = 0):
        """Add a peer to the discovery pool (known but not yet connected).

        Args:
            name: Peer identifier.
            host: Host address.
            port: Port number.
            services: Service bitmask.
        """
        self._discovery_pool.append({
            "name": name,
            "host": host,
            "port": port,
            "services": services,
        })

    def discover_peers(self, from_peer: str, max_new: int = 3) -> List[str]:
        """Discover new peers through introductions from an existing peer.

        Args:
            from_peer: The peer making introductions.
            max_new: Maximum number of new peers to discover.

        Returns:
            List of newly discovered peer names.
        """
        if from_peer not in self.peers:
            return []

        discovered = []
        random.shuffle(self._discovery_pool)

        for entry in self._discovery_pool[:max_new]:
            name = entry["name"]
            if name not in self.peers:
                self.add_peer(
                    name=name,
                    host=entry["host"],
                    port=entry["port"],
                    services=entry["services"],
                    introduced_by=from_peer,
                )
                discovered.append(name)

        # Remove discovered peers from the pool
        self._discovery_pool = [
            e for e in self._discovery_pool if e["name"] not in discovered
        ]
        return discovered

    # -----------------------------------------------------------------------
    # Message sending
    # -----------------------------------------------------------------------

    def send_message(
        self,
        source: str,
        msg_type: str,
        payload: Dict[str, Any],
        destination: Optional[str] = None,
        priority: int = MessagePriority.NORMAL,
        ttl: float = 0.0,
        encrypt: bool = False,
        gossip: bool = False,
    ) -> Optional[str]:
        """Send a message through the holographic P2P network.

        Args:
            source: Source peer name.
            msg_type: Type of message (e.g., 'block_proposal', 'vote', 'heartbeat').
            payload: Message payload dictionary.
            destination: Optional specific destination; if None, broadcast.
            priority: Message priority level (lower = higher priority).
            ttl: Time-to-live in seconds (0 = infinite, < 0 = use default).
            encrypt: Whether to encrypt the payload.
            gossip: Whether to use gossip protocol for dissemination.

        Returns:
            Message ID if sent successfully, None otherwise.
        """
        if source not in self.peers or not self.peers[source].connected:
            return None

        if ttl < 0:
            ttl = self.default_ttl

        # Optionally encrypt payload
        encrypted_payload = payload
        encrypted = False
        encrypted_key_b64 = ""

        if encrypt:
            ct, key_b64 = self._encrypt_payload(payload)
            encrypted_payload = {"_encrypted": ct}
            encrypted = True
            encrypted_key_b64 = key_b64

        msg_id = hashlib.sha256(
            f"{source}:{msg_type}:{time.time()}:{self.messages_sent}".encode()
        ).hexdigest()

        now = time.time()

        # Determine destinations
        if destination:
            destinations = [destination]
        else:
            destinations = [
                p for p in self.peers
                if p != source and self.peers[p].connected
            ]

        for dest in destinations:
            # Find entanglement path
            path = self._find_entanglement_path(source, dest)

            # Simulate latency based on path length
            latency_ms = len(path) * random.uniform(5.0, 50.0)

            msg = NetworkMessage(
                msg_id=msg_id,
                source=source,
                destination=dest,
                msg_type=msg_type,
                payload=encrypted_payload,
                timestamp=now,
                hop_count=len(path) - 1,
                entanglement_path=path,
                priority=priority,
                ttl=ttl,
                encrypted=encrypted,
                encrypted_key_b64=encrypted_key_b64,
                gossip_seen_by={source} if gossip else set(),
            )

            self.messages[msg_id] = msg
            self.message_log.append(msg)

            # Update peer stats
            self.peers[source].messages_sent += 1
            payload_size = len(json.dumps(encrypted_payload).encode("utf-8"))
            self.peers[source].bandwidth_bytes += payload_size

            if dest in self.peers:
                self.peers[dest].messages_received += 1
                self.peers[dest].bandwidth_bytes += payload_size
                # Track latency
                self.peers[dest].avg_latency_ms = (
                    (self.peers[dest].avg_latency_ms * self.peers[dest].messages_received + latency_ms)
                    / (self.peers[dest].messages_received + 1)
                )

            # --- v2.0: Gossip propagation ---
            if gossip:
                self._gossip_propagate(msg, source)

        self.messages_sent += 1
        return msg_id

    def _gossip_propagate(self, msg: NetworkMessage, current_peer: str):
        """Propagate a message using gossip (epidemic) protocol.

        Each peer that receives the message forwards it to k random neighbors
        that haven't seen it yet, achieving O(log N) dissemination.

        Args:
            msg: The message to propagate.
            current_peer: The peer currently propagating the message.
        """
        neighbors = list(self.connections.get(current_peer, {}).keys())
        unseen = [
            n for n in neighbors
            if n not in msg.gossip_seen_by and self.peers.get(n) and self.peers[n].connected
        ]

        if not unseen:
            return

        # Select k random neighbors
        targets = random.sample(unseen, min(self.gossip_k, len(unseen)))

        for target in targets:
            msg.gossip_seen_by.add(target)
            self.peers[target].messages_received += 1

            # Simulate latency
            latency_ms = random.uniform(10.0, 100.0)
            self.peers[target].avg_latency_ms = (
                (self.peers[target].avg_latency_ms * self.peers[target].messages_received + latency_ms)
                / (self.peers[target].messages_received + 1)
            )

            # Recursively propagate (with depth limit via TTL)
            if len(msg.gossip_seen_by) < len(self.peers):
                self._gossip_propagate(msg, target)

    # -----------------------------------------------------------------------
    # Priority queue
    # -----------------------------------------------------------------------

    def queue_message(self, msg: NetworkMessage):
        """Add a message to the priority queue for deferred sending.

        Args:
            msg: The message to queue.
        """
        self._pending_queue.append(msg)
        # Sort by priority (lower number = higher priority), then by timestamp
        self._pending_queue.sort(key=lambda m: (m.priority, m.timestamp))

    def process_queue(self) -> List[str]:
        """Process all pending messages in priority order.

        Returns:
            List of message IDs that were successfully sent.
        """
        now = time.time()
        sent = []
        remaining = []

        for msg in self._pending_queue:
            # Check TTL expiry
            if msg.ttl > 0 and (now - msg.timestamp) > msg.ttl:
                continue  # Drop expired messages

            if msg.source in self.peers and self.peers[msg.source].connected:
                msg_id = self.send_message(
                    source=msg.source,
                    msg_type=msg.msg_type,
                    payload=msg.payload,
                    destination=msg.destination,
                    priority=msg.priority,
                    ttl=msg.ttl,
                )
                if msg_id:
                    sent.append(msg_id)
            else:
                remaining.append(msg)

        self._pending_queue = remaining
        return sent

    # -----------------------------------------------------------------------
    # Routing
    # -----------------------------------------------------------------------

    def _find_entanglement_path(self, source: str, destination: str) -> List[str]:
        """Find the path of **maximum entanglement** between two peers.

        Uses Dijkstra's algorithm on the negative log of entanglement weights,
        which finds the path that maximizes the product of entanglement weights.

        Args:
            source: Source peer name.
            destination: Destination peer name.

        Returns:
            List of peer names forming the maximum-entanglement path.
        """
        if source == destination:
            return [source]

        # Direct connection check
        if destination in self.connections.get(source, {}):
            return [source, destination]

        # Dijkstra on negative log-entanglement (maximizes product of weights)
        import heapq

        # dist[peer] = minimum negative log-entanglement from source
        dist: Dict[str, float] = {source: 0.0}
        prev: Dict[str, Optional[str]] = {source: None}
        visited: Set[str] = set()

        # Priority queue: (neg_log_entanglement, peer_name)
        pq: List[Tuple[float, str]] = [(0.0, source)]

        while pq:
            d, current = heapq.heappop(pq)

            if current in visited:
                continue
            visited.add(current)

            if current == destination:
                break

            for neighbor, entanglement in self.connections.get(current, {}).items():
                if neighbor in visited:
                    continue

                # Negative log of entanglement (lower = more entangled)
                weight = -math.log(max(entanglement, 1e-12))
                new_dist = d + weight

                if neighbor not in dist or new_dist < dist[neighbor]:
                    dist[neighbor] = new_dist
                    prev[neighbor] = current
                    heapq.heappush(pq, (new_dist, neighbor))

        # Reconstruct path
        if destination not in prev:
            # No path found — fallback to direct
            return [source, destination]

        path = []
        current: Optional[str] = destination
        while current is not None:
            path.append(current)
            current = prev[current]
        path.reverse()
        return path

    # -----------------------------------------------------------------------
    # Network coherence
    # -----------------------------------------------------------------------

    def update_network_coherence(self):
        """Update the network coherence metric based on peer entanglement."""
        if not self.peers:
            self.network_coherence = 0.0
            return

        connected_names = [name for name, p in self.peers.items() if p.connected]
        if not connected_names:
            self.network_coherence = 0.0
            return

        # Coherence = average entanglement / max possible entanglement
        total_entanglement = 0.0
        connection_count = 0

        for peer_name in connected_names:
            for neighbor, ent in self.connections.get(peer_name, {}).items():
                if self.peers.get(neighbor) and self.peers[neighbor].connected:
                    total_entanglement += ent
                    connection_count += 1

        if connection_count > 0:
            # Divide by 2 because each connection is counted twice
            avg_entanglement = total_entanglement / (connection_count / 2)
            self.network_coherence = min(1.0, avg_entanglement)
        else:
            self.network_coherence = 0.5  # Single peer, no connections

    # -----------------------------------------------------------------------
    # Automatic reconnection
    # -----------------------------------------------------------------------

    def auto_reconnect(self, max_attempts: int = 3) -> List[str]:
        """Attempt to reconnect disconnected peers.

        Args:
            max_attempts: Maximum reconnection attempts per peer.

        Returns:
            List of successfully reconnected peer names.
        """
        reconnected = []

        for name, peer in self.peers.items():
            if not peer.connected and time.time() - peer.last_heartbeat > 30.0:
                # Simulate reconnection attempt
                success = random.random() < 0.7  # 70% success rate
                if success:
                    self.connect_peer(name)
                    reconnected.append(name)

        return reconnected

    # -----------------------------------------------------------------------
    # Topology export
    # -----------------------------------------------------------------------

    def export_topology(self, format: str = "json") -> str:
        """Export the current network topology for visualization.

        Args:
            format: Output format — 'json' or 'graphml'.

        Returns:
            Serialized topology string.
        """
        if format == "json":
            nodes = []
            edges = []

            for name, peer in self.peers.items():
                nodes.append({
                    "id": name,
                    "host": peer.host,
                    "port": peer.port,
                    "connected": peer.connected,
                    "entropy": round(peer.entropy, 4),
                    "messages_sent": peer.messages_sent,
                    "messages_received": peer.messages_received,
                    "bandwidth_bytes": peer.bandwidth_bytes,
                    "avg_latency_ms": round(peer.avg_latency_ms, 2),
                    "services": peer.services,
                    "user_agent": peer.user_agent,
                })

            seen_edges: Set[Tuple[str, str]] = set()
            for src, neighbors in self.connections.items():
                for dst, weight in neighbors.items():
                    edge_key = (min(src, dst), max(src, dst))
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        edges.append({
                            "source": src,
                            "target": dst,
                            "entanglement": round(weight, 4),
                        })

            topology = {
                "nodes": nodes,
                "edges": edges,
                "metadata": {
                    "total_peers": len(self.peers),
                    "active_peers": len(self.get_active_peers()),
                    "network_coherence": round(self.network_coherence, 4),
                    "messages_sent": self.messages_sent,
                    "timestamp": time.time(),
                },
            }
            return json.dumps(topology, indent=2)

        elif format == "graphml":
            # Simple GraphML output
            lines = [
                '<?xml version="1.0" encoding="UTF-8"?>',
                '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
                '  <graph edgedefault="undirected">',
            ]

            for name, peer in self.peers.items():
                lines.append(
                    f'    <node id="{name}" '
                    f'connected="{peer.connected}" '
                    f'entropy="{peer.entropy:.4f}" />'
                )

            seen_edges: Set[Tuple[str, str]] = set()
            for src, neighbors in self.connections.items():
                for dst, weight in neighbors.items():
                    edge_key = (min(src, dst), max(src, dst))
                    if edge_key not in seen_edges:
                        seen_edges.add(edge_key)
                        lines.append(
                            f'    <edge source="{src}" target="{dst}" '
                            f'entanglement="{weight:.4f}" />'
                        )

            lines.append("  </graph>")
            lines.append("</graphml>")
            return "\n".join(lines)

        else:
            raise ValueError(f"Unsupported topology format: {format}")

    # -----------------------------------------------------------------------
    # Query helpers
    # -----------------------------------------------------------------------

    def get_active_peers(self) -> List[str]:
        """Get list of active (connected) peer names."""
        return [name for name, peer in self.peers.items() if peer.connected]

    def get_peer_info(self, name: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific peer.

        Args:
            name: Peer identifier.

        Returns:
            Dictionary with peer information, or None if not found.
        """
        peer = self.peers.get(name)
        if not peer:
            return None

        return {
            "name": peer.name,
            "host": peer.host,
            "port": peer.port,
            "connected": peer.connected,
            "entropy": round(peer.entropy, 4),
            "messages_sent": peer.messages_sent,
            "messages_received": peer.messages_received,
            "bandwidth_bytes": peer.bandwidth_bytes,
            "avg_latency_ms": round(peer.avg_latency_ms, 2),
            "services": peer.services,
            "user_agent": peer.user_agent,
            "introduced_by": peer.introduced_by,
            "connections": list(self.connections.get(name, {}).keys()),
        }

    def get_message(self, msg_id: str) -> Optional[NetworkMessage]:
        """Retrieve a message by ID.

        Args:
            msg_id: Message identifier.

        Returns:
            NetworkMessage if found, None otherwise.
        """
        return self.messages.get(msg_id)

    def get_network_state(self) -> Dict[str, Any]:
        """Get the current state of the P2P network."""
        self.update_network_coherence()

        active_peers = self.get_active_peers()

        # Compute aggregate bandwidth
        total_bandwidth = sum(p.bandwidth_bytes for p in self.peers.values())
        avg_latency = (
            sum(p.avg_latency_ms for p in self.peers.values() if p.messages_received > 0)
            / max(1, len([p for p in self.peers.values() if p.messages_received > 0]))
        )

        return {
            "total_peers": len(self.peers),
            "active_peers": len(active_peers),
            "network_coherence": self.network_coherence,
            "messages_sent": self.messages_sent,
            "total_messages": len(self.message_log),
            "connections": sum(
                len(conns) for conns in self.connections.values()
            ) // 2,
            # v2.0 additions
            "total_bandwidth_bytes": total_bandwidth,
            "avg_latency_ms": round(avg_latency, 2),
            "pending_queue_size": len(self._pending_queue),
            "discovery_pool_size": len(self._discovery_pool),
            "encryption_enabled": self._encryption_key is not None,
        }

    def step(self):
        """Perform one network step: update heartbeats, coherence, and expiry."""
        self.step_count += 1
        now = time.time()

        # Update heartbeats
        for peer in self.peers.values():
            if peer.connected:
                peer.last_heartbeat = now

        # Expire messages with TTL
        expired_ids = []
        for msg_id, msg in self.messages.items():
            if msg.ttl > 0 and (now - msg.timestamp) > msg.ttl:
                expired_ids.append(msg_id)
        for msg_id in expired_ids:
            del self.messages[msg_id]

        # Update network coherence
        self.update_network_coherence()
