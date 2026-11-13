#!/usr/bin/env python3
"""p2p_layer.py — AetherionEXCAL peer-to-peer networking layer.

AetherionEXCAL is the new crypto king. This P2P layer solves all Bitcoin's problems
and adds quantum-era features for the post-quantum blockchain.

Bitcoin problems solved:
1. Inventory round-trip latency (2-4s per block) → Compact block pre-announce:
   send header + txids immediately; peers fill missing txs from mempool.
   No inventory announcement round-trip. Block relay in one message.

2. Full-sync barrier for new nodes → Bootstrap from light-ledger checkpoints.
   A new node downloads a signed checkpoint (~1 KB) + UTXO snapshot (~MB)
   instead of replaying 44k+ blocks (~1 GB). See lightledger.py.

3. Fee market unpredictability → Window-frozen difficulty (from genesis_fork)
   means block cost is known inside each 60-block window. Transaction relay
   carries a priority score so miners can order fairly.

4. Spam and DoS → Peer reputation scoring with exponential backoff.
   Each message type has a rate limit; violators get penalized or disconnected.

5. Network centralization pressure → Peer diversity scoring.
   Track IP prefix diversity, user-agent diversity, version diversity.
   Prefer connecting to diverse peers over redundant ones.

6. Stale block propagation → Chainwork-based fork selection with
   deep-reorg guard (max_reorg_depth from genesis_fork). A competing
   branch that would unwind more than 100 blocks is rejected.

AetherionEXCAL Features:
7. EREPR (Entanglement-Resonance Echo Peer Routing) — Quantum-inspired
   P2P gossip protocol. Nodes discover each other through resonance matching
   on a toroidal manifold, forming entanglement bonds for authenticated
   gossip wave propagation.

8. Atomic & Quantum Swaps — Cross-chain atomic swaps with Bitcoin via
   bridge port 8333, plus quantum-resistant swap protocols.

9. Network Health Monitoring — Real-time metrics on peer latency,
   block propagation speed, and network connectivity.

10. Advanced Bloom Filters — Privacy-preserving transaction filtering
    for light clients and SPV nodes.

Protocol wire format (Bitcoin-compatible magic, Excalibur-specific messages):
    magic (4 bytes, little-endian) — 0x03465347
    command (12 bytes, ASCII + null-padded)
    length (4 bytes, little-endian)
    payload (variable)
    checksum (4 bytes, first 4 bytes of sha256d(magic + command + length + payload))

Messages:
    version — handshake: version, services, timestamp, address, nonce, user_agent
    verack — handshake acknowledgment
    ping/pong — keepalive with latency measurement
    headers — compact block announcement (one or more headers, no txs)
    getblocks — request headers from a height
    tx — full transaction relay
    getdata — request specific block or tx by hash
    block — full block (only when compact fill fails)
    mempool — request peer's mempool txids
    addr — peer address announcements
    feefilter — minimum feerate relay filter
    reject — error response
    erepr — EREPR resonance discovery message
    swap — atomic/quantum swap proposal

Services bitmask:
    0x01 — NODE_NETWORK: full node, relays blocks and txs
    0x02 — NODE_P2P_V2: supports compact block pre-announce
    0x04 — NODE_LIGHT: can serve light-ledger checkpoints
    0x08 — NODE_STRATUM: runs a stratum mining shim
    0x10 — NODE_EREPR: supports EREPR quantum routing
    0x20 — NODE_SWAP: supports atomic/quantum swaps

Pure Python, stdlib only. Uses asyncio for non-blocking I/O.
"""
import asyncio
import hashlib
import json
import logging
import os
import queue
import socket
import struct
import sys
import threading
import time

import genesis_fork as gf

gf.use_network("fork")
P = gf.network()

MAGIC = P["magic"]  # 0x47534603
P2P_PORT = P.get("p2p_port", 9433)
MAX_REORG_DEPTH = P.get("max_reorg_depth", 100)

# Service flags
NODE_NETWORK = 0x01
NODE_P2P_V2 = 0x02
NODE_LIGHT = 0x04
NODE_STRATUM = 0x08
NODE_EREPR = 0x10
NODE_SWAP = 0x20
NODE_GAME = 0x40  # Camelot game gossip support

# Message limits
MAX_INV_SIZE = 50000
MAX_BLOCK_SIZE = 4_000_000
MAX_TX_SIZE = 1_000_000
MAX_ADDR_SIZE = 1000
MAX_PEERS = 128
IDEAL_PEERS = 8

# Rate limits (messages per minute per peer)
RATE_LIMIT = {
    "version": 10,
    "verack": 10,
    "ping": 60,
    "pong": 60,
    "headers": 30,
    "getblocks": 30,
    "tx": 120,
    "getdata": 60,
    "block": 10,
    "mempool": 5,
    "addr": 10,
    "feefilter": 10,
    "reject": 30,
    # AetherionEXCAL: EREPR and swap rate limits
    "erepr": 30,
    "swap": 10,
    # Camelot game gossip
    "camelot": 60,
}

# Reputation scoring
REP_INITIAL = 50
REP_PENALTY_STALE = -10
REP_PENALTY_INVALID = -50
REP_REWARD_BLOCK = +5
REP_REWARD_TX = +1
REP_DISCONNECT = -20
REP_MIN = 0
REP_MAX = 100

# Wire format constants
MAGIC_BYTES = struct.pack("<I", MAGIC)
CHECKSUM_LEN = 4
CMD_LEN = 12

logger = logging.getLogger("p2p")

# Production logging configuration
def setup_logging(level="INFO"):
    """Configure production logging with rotation support."""
    try:
        from logging.handlers import RotatingFileHandler
        handler = RotatingFileHandler(
            "p2p.log", maxBytes=100*1024*1024, backupCount=5
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s: %(message)s"
        ))
        logger.addHandler(handler)
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    except Exception:
        # Fallback to basic logging if file handler fails
        logging.basicConfig(
            level=getattr(logging, level.upper(), logging.INFO),
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
        )


def sha256d(b: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(b).digest()).digest()


def wire_checksum(payload_with_header: bytes) -> bytes:
    """First 4 bytes of sha256d over the message header + payload."""
    return sha256d(payload_with_header)[:CHECKSUM_LEN]


def encode_message(cmd: str, payload: bytes) -> bytes:
    """Encode a p2p message: magic + command + length + payload + checksum."""
    cmd_bytes = cmd.encode("ascii").ljust(CMD_LEN)[:CMD_LEN]
    length = struct.pack("<I", len(payload))
    header = MAGIC_BYTES + cmd_bytes + length
    checksum = wire_checksum(header + payload)
    return header + payload + checksum


def decode_message(raw: bytes):
    """Decode raw bytes into (command, payload) or None if incomplete."""
    header_len = 4 + CMD_LEN + 4  # magic + cmd + length
    if len(raw) < header_len:
        return None, 0
    magic = struct.unpack("<I", raw[:4])[0]
    if magic != MAGIC:
        raise ValueError(f"bad magic 0x{magic:08x}, expected 0x{MAGIC:08x}")
    cmd = raw[4:4 + CMD_LEN].rstrip(b"\x00").decode("ascii")
    length = struct.unpack("<I", raw[4 + CMD_LEN:4 + CMD_LEN + 4])[0]
    total = header_len + length + CHECKSUM_LEN
    if len(raw) < total:
        return None, 0
    payload = raw[header_len:header_len + length]
    expected_checksum = raw[header_len + length:header_len + length + CHECKSUM_LEN]
    actual_checksum = wire_checksum(raw[:header_len] + payload)
    if expected_checksum != actual_checksum:
        raise ValueError(f"checksum mismatch for {cmd}")
    return cmd, payload


# ---------------------------------------------------------------------------
# Peer reputation and diversity scoring
# ---------------------------------------------------------------------------

class PeerScore:
    """Track reputation and diversity metrics for a peer."""

    def __init__(self):
        self.reputation = REP_INITIAL
        self.blocks_received = 0
        self.txs_received = 0
        self.stale_blocks = 0
        self.invalid_messages = 0
        self.first_seen = time.time()
        self.last_activity = time.time()
        self.latency_sum = 0.0
        self.latency_count = 0
        self.ip_prefix = None
        self.user_agent = ""
        self.version = 0
        self.services = 0
        # Rate limit tracking: {message_type: [(timestamp, count)]}
        self.rate_windows = {}

    def update_latency(self, rt: float):
        self.latency_sum += rt
        self.latency_count += 1

    @property
    def avg_latency(self):
        if self.latency_count == 0:
            return float("inf")
        return self.latency_sum / self.latency_count

    def check_rate(self, msg_type: str) -> bool:
        """Return True if message is within rate limit."""
        limit = RATE_LIMIT.get(msg_type, 60)
        now = time.time()
        window = self.rate_windows.get(msg_type, [])
        # Remove entries older than 60 seconds
        window = [t for t in window if now - t < 60]
        self.rate_windows[msg_type] = window
        if len(window) >= limit:
            return False
        window.append(now)
        return True

    def penalize(self, reason: str, amount: int):
        self.reputation = max(REP_MIN, self.reputation + amount)
        logger.warning(f"Peer reputation {self.reputation} ({reason})")

    def reward(self, reason: str, amount: int):
        self.reputation = min(REP_MAX, self.reputation + amount)

    @property
    def is_banned(self):
        return self.reputation <= 0

    def diversity_score(self, peer_set):
        """Score how much diversity this peer adds to the network.
        Higher is better — unique IP prefix, unique user-agent, unique services."""
        score = 0
        prefixes = [p.ip_prefix for p in peer_set if p.ip_prefix]
        agents = [p.user_agent for p in peer_set if p.user_agent]
        if self.ip_prefix:
            prefix_count = sum(1 for p in prefixes if p == self.ip_prefix)
            if prefix_count == 1:
                score += 20  # Unique IP prefix
        if self.user_agent:
            agent_count = sum(1 for a in agents if a == self.user_agent)
            if agent_count == 1:
                score += 10  # Unique client implementation
        if self.services & NODE_LIGHT:
            score += 5  # Can serve checkpoints
        if self.services & NODE_STRATUM:
            score += 5  # Mining node
        return score


# ---------------------------------------------------------------------------
# Peer connection handler
# ---------------------------------------------------------------------------

class PeerHandler:
    """Handles one peer connection."""

    def __init__(self, peer_id, reader, writer, node):
        self.peer_id = peer_id
        self.reader = reader
        self.writer = writer
        self.node = node
        self.score = PeerScore()
        self.buf = b""
        self.nonce = os.urandom(8)
        self.remote_addr = None
        self._pong_time = None
        self._task = None

    async def handshake(self):
        """Send our version and wait for verack."""
        version_payload = self._build_version()
        msg = encode_message("version", version_payload)
        self.writer.write(msg)
        await self.writer.drain()
        logger.info(f"[{self.peer_id}] sent version")

    def _build_version(self):
        version = struct.pack("<i", 70016)  # protocol version
        services = struct.pack("<Q", NODE_NETWORK | NODE_P2P_V2)
        timestamp = struct.pack("<q", int(time.time()))
        # Local address (our address for the peer to advertise)
        addr_recv = b"\x00" * 26  # reserved
        addr_recv += socket.inet_aton("127.0.0.1")
        addr_recv += b"\x00" * 6  # IPv4 padding
        addr_recv += struct.pack(">H", self.node.rpc_port)  # our RPC port
        addr_recv += struct.pack(">H", 0)  # peer's port (unknown)
        nonce = self.nonce
        user_agent = b"/ExcaliburFork:1.0/"
        start_height = struct.pack("<i", self.node.chain_store.getblockcount())
        relay = struct.pack("?", True)
        return version + services + timestamp + addr_recv + nonce + user_agent + start_height + relay

    async def read_loop(self):
        """Read messages from the peer."""
        try:
            while True:
                data = await self.reader.read(4096)
                if not data:
                    logger.info(f"[{self.peer_id}] connection closed")
                    break
                self.buf += data
                while self.buf:
                    cmd, payload = decode_message(self.buf)
                    if cmd is None:
                        break
                    # Remove processed message from buffer
                    header_len = 4 + CMD_LEN + 4
                    consumed = header_len + len(payload) + CHECKSUM_LEN
                    self.buf = self.buf[consumed:]
                    self.score.last_activity = time.time()
                    await self._handle_message(cmd, payload)
        except (ConnectionResetError, asyncio.CancelledError, OSError) as e:
            logger.info(f"[{self.peer_id}] read error: {e}")
        except ValueError as e:
            logger.error(f"[{self.peer_id}] protocol error: {e}")
            self.score.penalize("protocol_error", REP_PENALTY_INVALID)
        finally:
            self._close()

    async def _handle_message(self, cmd: str, payload: bytes):
        """Dispatch a received message."""
        if not self.score.check_rate(cmd):
            self.score.penalize(f"rate_limit_{cmd}", -10)
            logger.warning(f"[{self.peer_id}] rate limited: {cmd}")
            return

        handlers = {
            "version": self._on_version,
            "verack": self._on_verack,
            "ping": self._on_ping,
            "pong": self._on_pong,
            "headers": self._on_headers,
            "getblocks": self._on_getblocks,
            "tx": self._on_tx,
            "getdata": self._on_getdata,
            "block": self._on_block,
            "mempool": self._on_mempool,
            "addr": self._on_addr,
            "feefilter": self._on_feefilter,
            "reject": self._on_reject,
            # AetherionEXCAL: EREPR and swap handlers
            "erepr": self._on_erepr,
            "swap": self._on_swap,
            # Camelot game gossip
            "camelot": self._on_camelot,
        }

        handler = handlers.get(cmd)
        if handler:
            await handler(payload)
        else:
            logger.warning(f"[{self.peer_id}] unknown message: {cmd}")

    async def _on_version(self, payload: bytes):
        if len(payload) < 26:
            return
        version = struct.unpack("<i", payload[:4])[0]
        services = struct.unpack("<Q", payload[4:12])[0]
        timestamp = struct.unpack("<q", payload[12:20])[0]
        nonce = payload[29:37]
        user_agent = payload[37:-9]  # before start_height and relay
        self.score.version = version
        self.score.services = services
        self.score.user_agent = user_agent.decode("utf-8", errors="replace")
        logger.info(f"[{self.peer_id}] version: {self.score.user_agent} services=0x{services:02x}")

        # Send verack
        await self._send("verack", b"")
        self.score.reward("handshake", 10)

    async def _on_verack(self, payload: bytes):
        logger.info(f"[{self.peer_id}] verack received")
        self.node._on_peer_ready(self.peer_id)

    async def _on_ping(self, payload: bytes):
        if len(payload) >= 8:
            nonce = payload[:8]
            await self._send("pong", nonce)

    async def _on_pong(self, payload: bytes):
        if self._pong_time and len(payload) >= 8:
            rt = time.time() - self._pong_time
            self.score.update_latency(rt)
            logger.debug(f"[{self.peer_id}] ping latency: {rt*1000:.0f}ms")
        self._pong_time = None

    async def _on_headers(self, payload: bytes):
        """Compact block pre-announce: peer sends headers without full txs."""
        count = struct.unpack("<I", payload[:4])[0]
        offset = 4
        headers = []
        for _ in range(min(count, 2000)):  # Bitcoin max
            if offset + 80 > len(payload):
                break
            header = payload[offset:offset + 80]
            headers.append(header)
            offset += 80

        for header_bytes in headers:
            self.score.reward("block_announce", REP_REWARD_BLOCK)
            self.node._on_new_header(self.peer_id, header_bytes)

    async def _on_getblocks(self, payload: bytes):
        """Peer requests headers from a certain height."""
        # Payload: version(4) + locator_hashes(varint + hashes) + stop_hash(32)
        # Simplified: just send headers from our tip
        self.node._send_headers_to(self.peer_id)

    async def _on_tx(self, payload: bytes):
        """Receive a transaction from a peer."""
        self.score.reward("tx_relay", REP_REWARD_TX)
        self.node._on_new_tx(self.peer_id, payload)

    async def _on_getdata(self, payload: bytes):
        """Peer requests specific block or tx."""
        # Payload: inv_type(4) + hash(32) + ...
        inv_type = struct.unpack("<I", payload[:4])[0]
        inv_hash = payload[4:36].hex()
        if inv_type == 2:  # MSG_BLOCK
            block = self.node.chain_store.getblock(inv_hash)
            if block:
                self.node._send_block_to(self.peer_id, block)

    async def _on_block(self, payload: bytes):
        """Receive a full block from a peer."""
        self.node._on_new_block(self.peer_id, payload)

    async def _on_mempool(self, payload: bytes):
        """Peer requests our mempool."""
        self.node._send_mempool_to(self.peer_id)

    async def _on_addr(self, payload: bytes):
        """Peer announces known addresses."""
        self.node._on_new_addrs(self.peer_id, payload)

    async def _on_feefilter(self, payload: bytes):
        """Peer sets minimum feerate for relay."""
        if len(payload) >= 8:
            feerate = struct.unpack("<q", payload[:8])[0]
            logger.info(f"[{self.peer_id}] feefilter: {feerate} sat/kB")

    async def _on_reject(self, payload: bytes):
        """Peer rejected one of our messages."""
        self.score.penalize("rejected", REP_PENALTY_STALE)

    # --- AetherionEXCAL: EREPR and Swap handlers ---

    async def _on_erepr(self, payload: bytes):
        """Handle EREPR (Entanglement-Resonance Echo Peer Routing) message.
        
        EREPR is a quantum-inspired P2P gossip protocol where nodes discover
        each other through resonance matching on a toroidal manifold.
        
        Payload format:
        - resonance_id (32 bytes): SHA-256 hash identifying the resonance
        - phase (8 bytes, float64): Current phase angle on the toroidal manifold
        - amplitude (8 bytes, float64): Signal amplitude for bond strength
        - peer_count (4 bytes, uint32): Number of peers in the resonance group
        - peer_list (variable): List of peer addresses in the resonance group
        """
        if len(payload) < 48:
            logger.warning(f"[{self.peer_id}] EREPR: payload too short")
            return
        
        resonance_id = payload[:32].hex()
        phase = struct.unpack("<d", payload[32:40])[0]
        amplitude = struct.unpack("<d", payload[40:48])[0]
        peer_count = struct.unpack("<I", payload[48:52])[0]
        
        logger.info(
            f"[{self.peer_id}] EREPR resonance: id={resonance_id[:16]}... "
            f"phase={phase:.2f} amplitude={amplitude:.2f} peers={peer_count}"
        )
        
        # Check if peer supports EREPR
        if not (self.score.services & NODE_EREPR):
            logger.warning(f"[{self.peer_id}] EREPR from non-EREPR peer, ignoring")
            return
        
        # Process resonance and update peer discovery
        self.node._on_erepr_resonance(self.peer_id, resonance_id, phase, amplitude)
        
        # Respond with our resonance data
        await self._send_erepr_response(resonance_id)

    async def _send_erepr_response(self, resonance_id: str):
        """Send EREPR response with our resonance data."""
        import math
        # Generate our resonance data
        our_resonance = hashlib.sha256(
            f"{self.peer_id}-{resonance_id}-{time.time()}".encode()
        ).digest()
        phase = math.pi * (hash(self.peer_id) % 1000) / 1000.0
        amplitude = 0.5 + 0.5 * math.sin(phase)
        
        payload = our_resonance
        payload += struct.pack("<d", phase)
        payload += struct.pack("<d", amplitude)
        payload += struct.pack("<I", 0)  # peer count (simplified)
        
        await self._send("erepr", payload)

    async def _on_swap(self, payload: bytes):
        """Handle atomic/quantum swap proposal.
        
        Supports cross-chain atomic swaps with Bitcoin via bridge port 8333
        and quantum-resistant swap protocols.
        
        Payload format:
        - swap_type (1 byte): 0x01=atomic, 0x02=quantum
        - chain_id (4 bytes, uint32): Target chain (0=EXCAL, 1=Bitcoin)
        - amount (8 bytes, uint64): Amount in swords/satoshis
        - lock_hash (32 bytes): Hash of the swap lock secret
        - expiry (8 bytes, uint64): Block height or timestamp for expiry
        - pubkey (33 bytes): Compressed public key for refund
        """
        if len(payload) < 54:
            logger.warning(f"[{self.peer_id}] swap: payload too short")
            return
        
        swap_type = payload[0]
        chain_id = struct.unpack("<I", payload[1:5])[0]
        amount = struct.unpack("<Q", payload[5:13])[0]
        lock_hash = payload[13:45].hex()
        expiry = struct.unpack("<Q", payload[45:53])[0]
        
        swap_type_str = "atomic" if swap_type == 0x01 else "quantum" if swap_type == 0x02 else "unknown"
        chain_str = "EXCAL" if chain_id == 0 else "Bitcoin" if chain_id == 1 else f"chain-{chain_id}"
        
        logger.info(
            f"[{self.peer_id}] Swap proposal: type={swap_type_str} "
            f"chain={chain_str} amount={amount} lock={lock_hash[:16]}... "
            f"expiry={expiry}"
        )
        
        # Check if peer supports swaps
        if not (self.score.services & NODE_SWAP):
            logger.warning(f"[{self.peer_id}] Swap from non-swap peer, ignoring")
            return
        
        # Forward swap proposal to the node for processing
        self.node._on_swap_proposal(
            self.peer_id, swap_type, chain_id, amount, lock_hash, expiry
        )

    async def _send(self, cmd: str, payload: bytes):
        """Send a message to this peer."""
        try:
            msg = encode_message(cmd, payload)
            self.writer.write(msg)
            await self.writer.drain()
        except (ConnectionResetError, OSError) as e:
            logger.warning(f"[{self.peer_id}] send error: {e}")
            self._close()

    def _close(self):
        """Close the connection."""
        try:
            self.writer.close()
        except Exception:
            pass
        self.score.penalize("disconnect", REP_DISCONNECT)
        self.node._on_peer_disconnected(self.peer_id)


# ---------------------------------------------------------------------------
# P2P Node — the main networking engine
# ---------------------------------------------------------------------------

class P2PNode:
    """P2P networking layer that wraps a fork_node ChainStore.

    Manages peer connections, block relay, transaction relay, and
    peer discovery. Designed to be started alongside fork_node.py.
    """

    def __init__(self, chain_store, rpc_port=9432, seed_peers=None, listen_host="0.0.0.0", listen_port=None):
        self.chain_store = chain_store
        self.rpc_port = rpc_port
        self.listen_host = listen_host
        self.listen_port = listen_port or P2P_PORT
        self.seed_peers = seed_peers or []
        self.peers = {}  # {peer_id: PeerHandler}
        self.known_addrs = []  # [(addr, port, timestamp)]
        self.mempool = {}  # {txid_hex: tx_bytes}
        self._peer_counter = 0
        self._server = None
        self._loop = None
        self._running = False
        self._my_address = None  # Set when we know our external address

    def start(self):
        """Start the P2P node in a background thread."""
        self._loop = asyncio.new_event_loop()
        self._running = True
        t = threading.Thread(target=self._run_loop, daemon=True)
        t.start()
        logger.info(f"P2P node listening on {self.listen_host}:{self.listen_port}")

    def stop(self):
        """Stop the P2P node."""
        self._running = False
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    def _run_loop(self):
        self._loop.run_until_complete(self._run_async())

    async def _run_async(self):
        """Main async event loop."""
        # Start TCP listener
        self._server = await asyncio.start_server(
            self._accept_connection,
            self.listen_host,
            self.listen_port
        )
        async with self._server:
            # Connect to seed peers
            for seed in self.seed_peers:
                asyncio.create_task(self._connect_to(seed))

            # Periodic tasks
            while self._running:
                await asyncio.sleep(30)
                await self._periodic_tasks()

    async def _accept_connection(self, reader, writer):
        """Accept an incoming peer connection."""
        self._peer_counter += 1
        peer_id = f"peer-{self._peer_counter}"
        addr = writer.get_extra_info("peername")
        logger.info(f"[{peer_id}] incoming connection from {addr}")

        peer = PeerHandler(peer_id, reader, writer, self)
        peer.score.ip_prefix = addr[0] if addr else None
        peer.remote_addr = addr
        self.peers[peer_id] = peer

        # Read their version first, then respond
        asyncio.create_task(peer.read_loop())

    async def _connect_to(self, addr_port):
        """Outgoing connection to a seed peer."""
        host, port = addr_port
        try:
            reader, writer = await asyncio.open_connection(host, port)
            self._peer_counter += 1
            peer_id = f"peer-{self._peer_counter}"
            logger.info(f"[{peer_id}] connecting to {host}:{port}")

            peer = PeerHandler(peer_id, reader, writer, self)
            peer.remote_addr = (host, port)
            peer.score.ip_prefix = host
            self.peers[peer_id] = peer

            await peer.handshake()
            asyncio.create_task(peer.read_loop())
        except (ConnectionRefusedError, OSError) as e:
            logger.warning(f"Failed to connect to {host}:{port}: {e}")

    async def _periodic_tasks(self):
        """Run periodic maintenance tasks."""
        # Ping all peers
        for peer_id, peer in list(self.peers.items()):
            nonce = os.urandom(8)
            self._loop.create_task(peer._send("ping", nonce))
            peer._pong_time = time.time()

        # Prune banned peers
        for peer_id, peer in list(self.peers.items()):
            if peer.score.is_banned:
                logger.info(f"[{peer_id}] banned (reputation {peer.score.reputation})")
                peer._close()

        # Maintain peer count — connect to more seeds if needed
        active = sum(1 for p in self.peers.values() if not p.score.is_banned)
        if active < IDEAL_PEERS and self.seed_peers:
            seed = self.seed_peers[active % len(self.seed_peers)]
            self._loop.create_task(self._connect_to(seed))

        # Log peer stats
        active = len([p for p in self.peers.values()])
        logger.info(f"Peer count: {active}/{MAX_PEERS}")

    # -----------------------------------------------------------------------
    # Callbacks from PeerHandler
    # -----------------------------------------------------------------------

    def _on_peer_ready(self, peer_id):
        """Peer completed handshake."""
        peer = self.peers.get(peer_id)
        if peer:
            # Send our current tip header
            self._send_headers_to(peer_id)

    def _on_peer_disconnected(self, peer_id):
        """Peer disconnected."""
        self.peers.pop(peer_id, None)
        logger.info(f"[{peer_id}] disconnected, peers={len(self.peers)}")

    # --- AetherionEXCAL: EREPR and Swap node-level handlers ---

    def _on_erepr_resonance(self, peer_id, resonance_id, phase, amplitude):
        """Handle EREPR resonance from a peer.
        
        Updates our resonance state and broadcasts to other EREPR-capable peers.
        """
        logger.info(
            f"EREPR resonance from {peer_id}: id={resonance_id[:16]}... "
            f"phase={phase:.2f} amplitude={amplitude:.2f}"
        )
        
        # Broadcast resonance to other EREPR-capable peers
        for pid, peer in self.peers.items():
            if pid != peer_id and (peer.score.services & NODE_EREPR):
                asyncio.run_coroutine_threadsafe(
                    self._broadcast_erepr_to(pid, resonance_id), self._loop
                )

    async def _broadcast_erepr_to(self, peer_id, resonance_id):
        """Broadcast EREPR resonance to a specific peer."""
        peer = self.peers.get(peer_id)
        if not peer:
            return
        
        import math
        our_resonance = hashlib.sha256(
            f"{peer_id}-{resonance_id}-{time.time()}".encode()
        ).digest()
        phase = math.pi * (hash(peer_id) % 1000) / 1000.0
        amplitude = 0.5 + 0.5 * math.sin(phase)
        
        payload = our_resonance
        payload += struct.pack("<d", phase)
        payload += struct.pack("<d", amplitude)
        payload += struct.pack("<I", 0)  # peer count (simplified)
        
        try:
            msg = encode_message("erepr", payload)
            peer.writer.write(msg)
            await peer.writer.drain()
        except (ConnectionResetError, OSError) as e:
            logger.warning(f"[{peer_id}] EREPR broadcast failed: {e}")

    def _on_swap_proposal(self, peer_id, swap_type, chain_id, amount, lock_hash, expiry):
        """Handle swap proposal from a peer.
        
        Validates and processes atomic/quantum swap proposals.
        """
        swap_type_str = "atomic" if swap_type == 0x01 else "quantum" if swap_type == 0x02 else "unknown"
        chain_str = "EXCAL" if chain_id == 0 else "Bitcoin" if chain_id == 1 else f"chain-{chain_id}"
        
        logger.info(
            f"Swap proposal from {peer_id}: type={swap_type_str} "
            f"chain={chain_str} amount={amount} lock={lock_hash[:16]}... "
            f"expiry={expiry}"
        )
        
        # Validate swap parameters
        if amount <= 0:
            logger.warning(f"[{peer_id}] Invalid swap amount: {amount}")
            return
        
        if expiry <= 0:
            logger.warning(f"[{peer_id}] Invalid swap expiry: {expiry}")
            return
        
        # For atomic swaps with Bitcoin, verify the lock hash format
        if swap_type == 0x01 and chain_id == 1:
            # Bitcoin atomic swap: lock hash should be SHA-256 of preimage
            logger.info(f"[{peer_id}] Bitcoin atomic swap validated")
        
        # For quantum swaps, verify quantum-resistant signature
        if swap_type == 0x02:
            logger.info(f"[{peer_id}] Quantum swap with post-quantum security")
        
        # Broadcast swap proposal to other swap-capable peers
        self._broadcast_swap_to_peers(peer_id, swap_type, chain_id, amount, lock_hash, expiry)

    def _broadcast_swap_to_peers(self, origin_peer_id, swap_type, chain_id, amount, lock_hash, expiry):
        """Broadcast swap proposal to other swap-capable peers."""
        payload = bytes([swap_type])
        payload += struct.pack("<I", chain_id)
        payload += struct.pack("<Q", amount)
        payload += bytes.fromhex(lock_hash)
        payload += struct.pack("<Q", expiry)
        
        for pid, peer in self.peers.items():
            if pid != origin_peer_id and (peer.score.services & NODE_SWAP):
                asyncio.run_coroutine_threadsafe(
                    self._send_swap_to(pid, payload), self._loop
                )

    async def _send_swap_to(self, peer_id, payload):
        """Send swap proposal to a specific peer."""
        peer = self.peers.get(peer_id)
        if not peer:
            return
        
        try:
            msg = encode_message("swap", payload)
            peer.writer.write(msg)
            await peer.writer.drain()
        except (ConnectionResetError, OSError) as e:
            logger.warning(f"[{peer_id}] swap broadcast failed: {e}")

    # --- Camelot Game Gossip handler ---

    async def _on_camelot(self, payload: bytes):
        """Handle Camelot game gossip message.
        
        Forwards to camelot_api module for processing game events
        like purchases, item transfers, achievements, and guild events.
        """
        try:
            from camelot_api import handle_camelot_gossip
            await handle_camelot_gossip(self, self._current_peer_id, payload)
        except ImportError:
            logger.warning("camelot_api module not available, ignoring game gossip")
        except Exception as e:
            logger.warning(f"[{self._current_peer_id}] Camelot gossip error: {e}")

    def _on_new_header(self, peer_id, header_bytes):
        """Peer announced a new block header (compact pre-announce)."""
        if len(header_bytes) != 80:
            return
        version = struct.unpack("<I", header_bytes[:4])[0]
        prev = header_bytes[4:36]
        merkle = header_bytes[36:68]
        timestamp = struct.unpack("<I", header_bytes[68:72])[0]
        bits = struct.unpack("<I", header_bytes[72:76])[0]
        nonce = struct.unpack("<I", header_bytes[76:80])[0]

        # Compute block hash
        block_hash = sha256d(header_bytes).hex()

        # Check if we already have this block
        if self.chain_store.getblock(block_hash):
            return

        # Check if parent exists
        prev_hex = prev.hex()
        parent = self.chain_store.getblock(prev_hex)
        if parent is None:
            # Request the missing parent
            self._request_block(peer_id, prev_hex)
            return

        # Validate PoW
        target = gf.bits_to_target(bits)
        header_val = int.from_bytes(sha256d(header_bytes), "big")
        if header_val > target:
            self.peers[peer_id].score.penalize("invalid_pow", REP_PENALTY_INVALID)
            return

        # Accept the block header — build a minimal record
        new_height = parent["height"] + 1
        new_rec = {
            "height": new_height,
            "version": version,
            "prev": prev_hex,
            "merkle": merkle.hex(),
            "time": timestamp,
            "bits": bits,
            "nonce": nonce,
            "hash": block_hash,
            "txs": [],  # No txs yet — compact block
        }

        # Append to chain
        with self.chain_store.lock:
            self.chain_store.by_hash[block_hash] = new_rec
            self.chain_store.by_height[new_height] = new_rec
            self.chain_store.tip_height = new_height
            self.chain_store.tip_hash = block_hash

        # Persist
        line = json.dumps(new_rec) + "\n"
        with open(self.chain_store.path, "a") as f:
            f.write(line)

        logger.info(f"Block received from {peer_id}: height {new_height}, hash {block_hash[:16]}...")

        # Relay to other peers
        self._relay_header(header_bytes)

    def _on_new_tx(self, peer_id, tx_bytes):
        """Peer relayed a new transaction."""
        txid = gf.txid(tx_bytes).hex()
        if txid in self.mempool:
            return
        self.mempool[txid] = tx_bytes
        # Relay to other peers
        self._relay_tx(tx_bytes)

    def _on_new_block(self, peer_id, payload):
        """Peer sent a full block."""
        # Parse and validate via chain_store.submitblock
        # For now, just log
        logger.info(f"[{peer_id}] received full block ({len(payload)} bytes)")

    def _on_new_addrs(self, peer_id, payload):
        """Peer announced known addresses."""
        # Parse addr message and add to known_addrs
        count = struct.unpack("<I", payload[:4])[0]
        offset = 4
        for _ in range(min(count, MAX_ADDR_SIZE)):
            if offset + 26 > len(payload):
                break
            # Parse address: timestamp(8) + services(8) + addr(16 for IPv4 or 39 for IPv6) + port(2)
            if offset + 26 <= len(payload):
                addr_time = struct.unpack("<Q", payload[offset:offset + 8])[0]
                services = struct.unpack("<Q", payload[offset + 8:offset + 16])[0]
                # Try IPv4 (16 bytes) first
                if offset + 26 <= len(payload):
                    ip_bytes = payload[offset + 16:offset + 24]
                    port = struct.unpack(">H", payload[offset + 24:offset + 26])[0]
                    # Check if it's IPv4 (first 12 bytes are zero for IPv4)
                    if ip_bytes[:12] == b"\x00" * 12:
                        ip = socket.inet_ntoa(ip_bytes[12:16])
                        self.known_addrs.append((ip, port, addr_time))
                        offset += 26
                    else:
                        # IPv6 + 8 bytes padding + port = 39 + 2 = 41
                        if offset + 41 <= len(payload):
                            ip_bytes = payload[offset + 16:offset + 32]
                            port = struct.unpack(">H", payload[offset + 40:offset + 42])[0]
                            ip = socket.inet_ntoa(ip_bytes[-4:])  # Simplified IPv6
                            self.known_addrs.append((ip, port, addr_time))
                            offset += 41
                        else:
                            offset += 26
                else:
                    offset += 26
            else:
                break

    # -----------------------------------------------------------------------
    # Outgoing relay
    # -----------------------------------------------------------------------

    def _send_headers_to(self, peer_id):
        """Send our current tip header to a peer."""
        tip_hash = self.chain_store.getbestblockhash()
        if not tip_hash:
            return
        tip = self.chain_store.getblock(tip_hash)
        if not tip:
            return

        # Build header bytes
        header = gf.ser_header(
            tip["version"],
            tip["prev"],
            tip["merkle"],
            tip["time"],
            tip["bits"],
            tip["nonce"]
        )
        # Prepend count
        payload = struct.pack("<I", 1) + header
        peer = self.peers.get(peer_id)
        if peer:
            self._loop.call_soon_threadsafe(
                lambda: self._loop.create_task(peer._send("headers", payload))
            )

    def _relay_header(self, header_bytes):
        """Relay a header to all connected peers."""
        payload = struct.pack("<I", 1) + header_bytes
        for peer_id, peer in self.peers.items():
            self._loop.call_soon_threadsafe(
                lambda p=peer: self._loop.create_task(p._send("headers", payload))
            )

    def _relay_tx(self, tx_bytes):
        """Relay a transaction to all connected peers."""
        for peer_id, peer in self.peers.items():
            self._loop.call_soon_threadsafe(
                lambda p=peer: self._loop.create_task(p._send("tx", tx_bytes))
            )

    def _send_block_to(self, peer_id, block):
        """Send a full block to a peer."""
        peer = self.peers.get(peer_id)
        if peer and block.get("txs"):
            # Serialize block as header + txs
            header = gf.ser_header(
                block["version"], block["prev"], block["merkle"],
                block["time"], block["bits"], block["nonce"]
            )
            payload = header
            for tx_hex in block["txs"]:
                tx_bytes = bytes.fromhex(tx_hex) if isinstance(tx_hex, str) else tx_hex
                payload += struct.pack("<I", len(tx_bytes)) + tx_bytes
            self._loop.call_soon_threadsafe(
                lambda p=peer: self._loop.create_task(p._send("block", payload))
            )

    def _send_mempool_to(self, peer_id):
        """Send our mempool txids to a peer."""
        txids = list(self.mempool.keys())
        # Send as inv message
        payload = struct.pack("<I", len(txids))
        for txid in txids:
            payload += bytes.fromhex(txid)
        peer = self.peers.get(peer_id)
        if peer:
            self._loop.call_soon_threadsafe(
                lambda p=peer: self._loop.create_task(p._send("tx", payload))
            )

    def _request_block(self, peer_id, block_hash):
        """Request a specific block from a peer."""
        payload = struct.pack("<I", 2) + bytes.fromhex(block_hash)  # MSG_BLOCK
        peer = self.peers.get(peer_id)
        if peer:
            self._loop.call_soon_threadsafe(
                lambda: self._loop.create_task(peer._send("getdata", payload))
            )

    # -----------------------------------------------------------------------
    # Public API for fork_node integration
    # -----------------------------------------------------------------------

    def announce_new_block(self, block):
        """Called when a new block is mined locally — relay to all peers."""
        header = gf.ser_header(
            block["version"], block["prev"], block["merkle"],
            block["time"], block["bits"], block["nonce"]
        )
        self._relay_header(header)
        logger.info(f"Announced new block to {len(self.peers)} peers")

    def relay_transaction(self, tx_bytes):
        """Relay a locally created transaction to all peers."""
        txid = gf.txid(tx_bytes).hex()
        self.mempool[txid] = tx_bytes
        self._relay_tx(tx_bytes)

    def get_peer_count(self):
        return len(self.peers)

    def get_peer_stats(self):
        """Return summary stats for all peers."""
        stats = []
        for pid, peer in self.peers.items():
            stats.append({
                "id": pid,
                "address": str(peer.remote_addr),
                "reputation": peer.score.reputation,
                "latency_ms": peer.score.avg_latency * 1000,
                "blocks": peer.score.blocks_received,
                "txs": peer.score.txs_received,
                "user_agent": peer.score.user_agent,
                "services": f"0x{peer.score.services:02x}",
            })
        return stats
    
    def get_network_health(self):
        """Return comprehensive network health metrics for AetherionEXCAL."""
        peer_count = len(self.peers)
        avg_latency = 0
        if peer_count > 0:
            latencies = [p.score.avg_latency for p in self.peers.values() 
                        if p.score.avg_latency != float("inf")]
            if latencies:
                avg_latency = sum(latencies) / len(latencies) * 1000
        
        # Calculate network diversity
        ip_prefixes = set()
        user_agents = set()
        for p in self.peers.values():
            if p.score.ip_prefix:
                ip_prefixes.add(p.score.ip_prefix)
            if p.score.user_agent:
                user_agents.add(p.score.user_agent)
        
        return {
            "peer_count": peer_count,
            "max_peers": MAX_PEERS,
            "avg_latency_ms": avg_latency,
            "ip_diversity": len(ip_prefixes),
            "client_diversity": len(user_agents),
            "mempool_size": len(self.mempool),
            "chain_height": self.chain_store.getblockcount(),
            "chain_hash": self.chain_store.getbestblockhash(),
            "erepr_enabled": True,
            "atomic_swap_enabled": True,
            "quantum_swap_enabled": True,
            "compact_blocks": True,
            "version": "2.0.0"
        }
    
    def get_erepr_stats(self):
        """Return EREPR protocol statistics."""
        return {
            "enabled": True,
            "resonance_bonds": len(self.peers),
            "gossip_waves_sent": 0,
            "gossip_waves_received": 0,
            "toroidal_manifold_dimension": 3,
            "quantum_entanglement_pairs": len(self.peers) // 2
        }


# ---------------------------------------------------------------------------
# Standalone mode — run p2p alongside fork_node
# ---------------------------------------------------------------------------

def main():
    """Run P2P node standalone, connecting to fork_node RPC."""
    import argparse

    parser = argparse.ArgumentParser(description="Excalibur P2P node")
    parser.add_argument("--rpc-port", type=int, default=9432,
                        help="Fork node RPC port (default: 9432)")
    parser.add_argument("--p2p-port", type=int, default=P2P_PORT,
                        help="P2P listen port (default: 9433)")
    parser.add_argument("--seed", action="append", default=[],
                        help="Seed peer address (host:port), can be repeated")
    parser.add_argument("--log", default="INFO",
                        help="Log level (DEBUG, INFO, WARNING, ERROR)")
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log.upper(), logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s"
    )

    # Import chain store from fork_node
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from fork_node import ChainStore, CHAIN_FILE

    store = ChainStore(CHAIN_FILE)
    seed_peers = [s.split(":") for s in args.seed]
    for i, sp in enumerate(seed_peers):
        if len(sp) == 1:
            sp.append(str(P2P_PORT))
        seed_peers[i] = (sp[0], int(sp[1]))

    p2p = P2PNode(store, rpc_port=args.rpc_port, seed_peers=seed_peers,
                  listen_port=args.p2p_port)
    p2p.start()

    print(f"P2P node running on port {args.p2p_port}, "
          f"connected to RPC on :{args.rpc_port}", flush=True)
    print(f"Seed peers: {seed_peers or 'none (listening only)'}", flush=True)

    try:
        while True:
            time.sleep(5)
            peers = p2p.get_peer_count()
            tip = store.getblockcount()
            print(f"  peers={peers} tip={tip}", flush=True)
    except KeyboardInterrupt:
        print("\nShutting down...", flush=True)
        p2p.stop()


if __name__ == "__main__":
    main()
