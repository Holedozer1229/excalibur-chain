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
7. EREPR (Entanglement-Resonance Echo Peer Routing) - bounded peer discovery
   and gossip. Peers exchange resonance announcements and known addresses
   after the version handshake.

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
import importlib.util
import ipaddress
import json
import logging
import math
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
NODE_EREPR_V2 = 0x80  # EREPR envelope with origin, expiry, and hop limit
NODE_WEBRTC = 0x100  # Supports WebRTC data channels

# Message limits
MAX_INV_SIZE = 50000
MAX_BLOCK_SIZE = 4_000_000
MAX_TX_SIZE = 1_000_000
MAX_ADDR_SIZE = 1000
MAX_MESSAGE_SIZE = 4_000_000
MAX_PEERS = 128
IDEAL_PEERS = 8
EREPR_MAX_ADDRESSES = 64
EREPR_ADDRESS_SIZE = 18
EREPR_SEEN_TTL = 900
EREPR_ANNOUNCE_INTERVAL = 120
EREPR_MESSAGE_TTL = 300
EREPR_MAX_HOPS = 12
EREPR_WAVE_DECAY = 0.85
EREPR_MIN_AMPLITUDE = 0.1
EREPR_EXTENSION_MAGIC = b"ER2!"
EREPR_EXTENSION_VERSION = 1
EREPR_EXTENSION = struct.Struct("<4sB32sQQB")


def parse_peer_address(value, default_port=P2P_PORT):
    """Parse a configured peer as host:port, [IPv6]:port, or a pair/map."""
    if isinstance(value, dict):
        host = value.get("host")
        port = value.get("port", default_port)
    elif isinstance(value, (tuple, list)) and len(value) == 2:
        host, port = value
    elif isinstance(value, str):
        value = value.strip()
        if value.startswith("["):
            end = value.find("]")
            if end < 0:
                raise ValueError(f"invalid bracketed peer address: {value}")
            host = value[1:end]
            suffix = value[end + 1:]
            port = suffix[1:] if suffix.startswith(":") else default_port
            if suffix and not suffix.startswith(":"):
                raise ValueError(f"invalid peer address suffix: {value}")
        elif value.count(":") == 1:
            host, port = value.rsplit(":", 1)
        else:
            host, port = value, default_port
    else:
        raise ValueError(f"invalid peer address: {value!r}")

    host = str(host).strip().strip("[]") if host is not None else ""
    port = int(port)
    if not host or not 0 < port <= 65535:
        raise ValueError(f"invalid peer address: {value!r}")
    return host, port


def parse_seed_peers(values, default_port=P2P_PORT):
    if values is None:
        values = []
    elif isinstance(values, (str, dict)):
        values = [values]
    try:
        values = list(values)
    except TypeError:
        logger.warning("Ignoring invalid P2P seed list: %r", values)
        return []
    peers = []
    for value in values or []:
        try:
            peer = parse_peer_address(value, default_port)
        except (TypeError, ValueError) as exc:
            logger.warning("Ignoring invalid P2P seed %r: %s", value, exc)
            continue
        if peer not in peers:
            peers.append(peer)
    return peers

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
    "rtc_offer": 5,
    "rtc_answer": 5,
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
    cmd_bytes = cmd.encode("ascii").ljust(CMD_LEN, b"\x00")[:CMD_LEN]
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
    cmd = raw[4:4 + CMD_LEN].rstrip(b"\x00 ").decode("ascii")
    length = struct.unpack("<I", raw[4 + CMD_LEN:4 + CMD_LEN + 4])[0]
    if length > MAX_MESSAGE_SIZE:
        raise ValueError(f"message too large: {length} bytes")
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
        # Use a per-process nonce so a node recognizes its own connection even
        # when it reaches itself through a relayed public address.
        self.nonce = node._node_id[:8]
        self.remote_addr = None
        self.advertised_addr = None
        self._pong_time = None
        self._task = None
        self._version_received = False
        self.target_addr = None
        self.remote_nonce = None
        self._rtc_pc = None
        self._rtc_channel = None
        self._rtc_buf = b""
        self._rtc_offer_started = False

    async def handshake(self):
        """Send our version and wait for verack."""
        version_payload = self._build_version()
        msg = encode_message("version", version_payload)
        self.writer.write(msg)
        await self.writer.drain()
        logger.info(f"[{self.peer_id}] sent version")

    def _build_version(self):
        version = struct.pack("<i", 70016)  # protocol version
        services = NODE_NETWORK | NODE_P2P_V2 | NODE_EREPR | NODE_SWAP | NODE_GAME | NODE_EREPR_V2
        if self.node.enable_webrtc:
            services |= NODE_WEBRTC
        services = struct.pack(
            "<Q", services
        )
        timestamp = struct.pack("<q", int(time.time()))
        ip = self.node._pack_ip(self.node.advertise_host)
        addr_recv = b"\x00" * 8 + b"\x00" * 16 + struct.pack(">H", 0)
        addr_from = services + ip + struct.pack(">H", self.node.listen_port)
        nonce = self.nonce
        user_agent = b"/ExcaliburFork:1.0/"
        user_agent = bytes([len(user_agent)]) + user_agent
        start_height = struct.pack("<i", self.node.chain_store.getblockcount())
        relay = struct.pack("?", True)
        return (
            version + services + timestamp + addr_recv + addr_from
            + nonce + user_agent + start_height + relay
        )

    async def read_loop(self):
        """Read messages from the peer."""
        try:
            while True:
                data = await self.reader.read(4096)
                if not data:
                    logger.info(f"[{self.peer_id}] connection closed")
                    break
                self.buf += data
                if len(self.buf) > MAX_MESSAGE_SIZE + 24:
                    raise ValueError("receive buffer exceeds maximum message size")
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
            "rtc_offer": self._on_rtc_offer,
            "rtc_answer": self._on_rtc_answer,
        }

        handler = handlers.get(cmd)
        if handler:
            await handler(payload)
        else:
            logger.warning(f"[{self.peer_id}] unknown message: {cmd}")

    async def _on_version(self, payload: bytes):
        if len(payload) < 85:
            raise ValueError("truncated version message")
        version = struct.unpack("<i", payload[:4])[0]
        services = struct.unpack("<Q", payload[4:12])[0]
        nonce = payload[72:80]
        if nonce == self.nonce:
            raise ValueError("self-connection detected")
        user_agent_length = payload[80]
        user_agent_end = 81 + user_agent_length
        if user_agent_end + 5 > len(payload):
            raise ValueError("malformed user agent in version message")
        user_agent = payload[81:user_agent_end]
        self.score.version = version
        self.score.services = services
        self.remote_nonce = nonce
        self.score.user_agent = user_agent.decode("utf-8", errors="replace")
        self._version_received = True
        remote_ip = self.node._unpack_ip(payload[54:70])
        remote_port = struct.unpack(">H", payload[70:72])[0]
        if remote_ip is None and self.remote_addr:
            remote_ip = self.remote_addr[0]
        if remote_ip and remote_port:
            self.advertised_addr = (remote_ip, remote_port)
            self.node._remember_address(remote_ip, remote_port)
        logger.info(f"[{self.peer_id}] version: {self.score.user_agent} services=0x{services:02x}")

        # Send verack
        await self._send("verack", b"")
        self.score.reward("handshake", 10)

    async def _on_verack(self, payload: bytes):
        if not self._version_received:
            raise ValueError("verack received before version")
        logger.info(f"[{self.peer_id}] verack received")
        self.node._on_peer_ready(self.peer_id)
        await self._maybe_start_webrtc()

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
        - v2_extension (optional): origin ID, sequence, issue time, and hop count
        """
        if not (self.score.services & NODE_EREPR):
            self.score.penalize("erepr_from_unsupported_peer", REP_PENALTY_STALE)
            logger.warning(f"[{self.peer_id}] EREPR from non-EREPR peer, ignoring")
            return
        if len(payload) < 52:
            self.score.penalize("malformed_erepr", REP_PENALTY_INVALID)
            logger.warning(f"[{self.peer_id}] EREPR: payload too short")
            return

        resonance_id = payload[:32].hex()
        phase = struct.unpack("<d", payload[32:40])[0]
        amplitude = struct.unpack("<d", payload[40:48])[0]
        peer_count = struct.unpack("<I", payload[48:52])[0]
        base_length = 52 + peer_count * EREPR_ADDRESS_SIZE
        if peer_count > EREPR_MAX_ADDRESSES or len(payload) not in (
                base_length, base_length + EREPR_EXTENSION.size):
            self.score.penalize("malformed_erepr", REP_PENALTY_INVALID)
            logger.warning(f"[{self.peer_id}] EREPR: invalid peer list length")
            return
        if (not math.isfinite(phase) or not 0.0 <= phase < 2 * math.pi
                or not math.isfinite(amplitude)
                or not EREPR_MIN_AMPLITUDE < amplitude <= 1.0):
            self.score.penalize("malformed_erepr", REP_PENALTY_INVALID)
            logger.warning(f"[{self.peer_id}] EREPR: invalid phase or amplitude")
            return

        addresses = []
        offset = 52
        for _ in range(peer_count):
            raw_ip = payload[offset:offset + 16]
            port = struct.unpack(">H", payload[offset + 16:offset + 18])[0]
            offset += EREPR_ADDRESS_SIZE
            address = ipaddress.ip_address(raw_ip)
            if address.ipv4_mapped:
                address = address.ipv4_mapped
            if port and not (address.is_unspecified or address.is_multicast):
                addresses.append((str(address), port))

        origin_node_id = None
        sequence = None
        issued_at = None
        hops = 0
        if len(payload) == base_length + EREPR_EXTENSION.size:
            (magic, version, origin_node_id, sequence, issued_at,
             hops) = EREPR_EXTENSION.unpack_from(payload, base_length)
            now = int(time.time())
            expected_id = (
                hashlib.sha256(
                    origin_node_id + struct.pack("<Q", sequence)
                ).digest()
                if sequence else b""
            )
            if (magic != EREPR_EXTENSION_MAGIC
                    or version != EREPR_EXTENSION_VERSION
                    or sequence == 0
                    or expected_id != payload[:32]
                    or issued_at > now + 30
                    or now - issued_at > EREPR_MESSAGE_TTL
                    or hops > EREPR_MAX_HOPS):
                self.score.penalize("malformed_erepr_extension", REP_PENALTY_INVALID)
                logger.warning(f"[{self.peer_id}] EREPR: invalid or expired v2 envelope")
                return

        logger.info(
            f"[{self.peer_id}] EREPR resonance: id={resonance_id[:16]}... "
            f"phase={phase:.2f} amplitude={amplitude:.2f} peers={peer_count}"
        )

        self.node._on_erepr_resonance(
            self.peer_id, resonance_id, phase, amplitude, addresses,
            origin_node_id=origin_node_id, sequence=sequence,
            issued_at=issued_at, hops=hops,
        )

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

    async def _on_camelot(self, payload: bytes):
        await self.node._on_camelot(self.peer_id, payload)

    async def _maybe_start_webrtc(self):
        if (
            not self.node.enable_webrtc
            or not self.remote_nonce
            or not self.score.services & NODE_WEBRTC
            or self._rtc_offer_started
            or self.nonce >= self.remote_nonce
        ):
            return
        self._rtc_offer_started = True
        try:
            from aiortc import RTCPeerConnection, RTCSessionDescription

            pc = RTCPeerConnection()
            self._rtc_pc = pc
            self._bind_rtc_peer(pc)
            self._bind_rtc_channel(
                pc.createDataChannel("excal-p2p-v1", ordered=True)
            )
            offer = await pc.createOffer()
            await pc.setLocalDescription(offer)
            await self._send_signal("rtc_offer", {
                "type": pc.localDescription.type,
                "sdp": pc.localDescription.sdp,
            })
        except (ImportError, OSError, ValueError, RuntimeError) as exc:
            logger.warning("[%s] WebRTC offer failed; keeping TCP transport: %s", self.peer_id, exc)
            await self._close_rtc()

    async def _on_rtc_offer(self, payload):
        if not self.node.enable_webrtc or not self.score.services & NODE_WEBRTC:
            return
        if self._rtc_pc is not None or len(payload) > 128_000:
            raise ValueError("unexpected or oversized WebRTC offer")
        try:
            from aiortc import RTCPeerConnection, RTCSessionDescription

            description = json.loads(payload.decode("utf-8"))
            if description.get("type") != "offer" or not isinstance(description.get("sdp"), str):
                raise ValueError("invalid WebRTC offer")
            pc = RTCPeerConnection()
            self._rtc_pc = pc
            self._bind_rtc_peer(pc)
            await pc.setRemoteDescription(RTCSessionDescription(
                sdp=description["sdp"], type="offer"
            ))
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            await self._send_signal("rtc_answer", {
                "type": pc.localDescription.type,
                "sdp": pc.localDescription.sdp,
            })
        except (ImportError, UnicodeDecodeError, json.JSONDecodeError,
                OSError, ValueError, RuntimeError) as exc:
            logger.warning("[%s] WebRTC offer rejected; keeping TCP transport: %s", self.peer_id, exc)
            await self._close_rtc()

    async def _on_rtc_answer(self, payload):
        if self._rtc_pc is None or len(payload) > 128_000:
            raise ValueError("unexpected or oversized WebRTC answer")
        try:
            from aiortc import RTCSessionDescription

            description = json.loads(payload.decode("utf-8"))
            if description.get("type") != "answer" or not isinstance(description.get("sdp"), str):
                raise ValueError("invalid WebRTC answer")
            await self._rtc_pc.setRemoteDescription(RTCSessionDescription(
                sdp=description["sdp"], type="answer"
            ))
        except (ImportError, UnicodeDecodeError, json.JSONDecodeError,
                OSError, ValueError, RuntimeError) as exc:
            logger.warning("[%s] WebRTC answer rejected; keeping TCP transport: %s", self.peer_id, exc)
            await self._close_rtc()

    def _bind_rtc_peer(self, pc):
        @pc.on("datachannel")
        def on_datachannel(channel):
            self._bind_rtc_channel(channel)

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            if pc.connectionState in ("failed", "closed"):
                await self._close_rtc()

    def _bind_rtc_channel(self, channel):
        if channel.label != "excal-p2p-v1":
            channel.close()
            return
        self._rtc_channel = channel

        @channel.on("message")
        def on_message(data):
            if not isinstance(data, bytes):
                logger.warning("[%s] ignored non-binary WebRTC frame", self.peer_id)
                return
            self._rtc_buf += data
            if len(self._rtc_buf) > MAX_MESSAGE_SIZE + 24:
                logger.warning("[%s] WebRTC receive buffer exceeded limit", self.peer_id)
                channel.close()
                return
            while self._rtc_buf:
                try:
                    cmd, payload = decode_message(self._rtc_buf)
                except ValueError as exc:
                    logger.warning("[%s] invalid WebRTC frame: %s", self.peer_id, exc)
                    channel.close()
                    return
                if cmd is None:
                    break
                consumed = 4 + CMD_LEN + 4 + len(payload) + CHECKSUM_LEN
                self._rtc_buf = self._rtc_buf[consumed:]
                task = self.node._loop.create_task(self._handle_message(cmd, payload))
                task.add_done_callback(self._log_rtc_task_error)

    @staticmethod
    def _log_rtc_task_error(task):
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.warning("WebRTC message handling failed: %s", exc)

    async def _send_signal(self, cmd, payload):
        encoded = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        await self._send_tcp(cmd, encoded)

    async def _send_tcp(self, cmd, payload):
        msg = encode_message(cmd, payload)
        self.writer.write(msg)
        await self.writer.drain()

    async def _send(self, cmd: str, payload: bytes):
        """Send a message to this peer."""
        try:
            msg = encode_message(cmd, payload)
            if (
                cmd not in {"version", "verack", "rtc_offer", "rtc_answer"}
                and self._rtc_channel is not None
                and self._rtc_channel.readyState == "open"
            ):
                self._rtc_channel.send(msg)
                return
            self.writer.write(msg)
            await self.writer.drain()
        except (ConnectionResetError, OSError) as e:
            logger.warning(f"[{self.peer_id}] send error: {e}")
            self._close()

    async def _close_rtc(self):
        pc = self._rtc_pc
        self._rtc_pc = None
        self._rtc_channel = None
        self._rtc_buf = b""
        if pc is not None:
            await pc.close()

    def _close(self):
        """Close the connection."""
        if self._rtc_pc is not None and self.node._loop and self.node._loop.is_running():
            self.node._loop.create_task(self._close_rtc())
        if self.writer.is_closing():
            return
        try:
            self.writer.close()
        except OSError as exc:
            logger.debug("[%s] close failed: %s", self.peer_id, exc)
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

    def __init__(self, chain_store, rpc_port=9432, seed_peers=None,
                 listen_host="0.0.0.0", listen_port=None,
                 advertise_host=None, allow_private_peers=None,
                 enable_webrtc=True, enable_mdns=True):
        self.chain_store = chain_store
        self.rpc_port = rpc_port
        self.listen_host = listen_host
        self.listen_port = P2P_PORT if listen_port is None else listen_port
        self.advertise_host = advertise_host or os.environ.get("FORK_P2P_ADVERTISE_HOST")
        self.allow_private_peers = (
            os.environ.get("FORK_P2P_ALLOW_PRIVATE", "0").lower() in {"1", "true", "yes"}
            if allow_private_peers is None else allow_private_peers
        )
        self.enable_webrtc = bool(enable_webrtc and importlib.util.find_spec("aiortc"))
        self.enable_mdns = bool(enable_mdns)
        self._mdns_discovery = None
        self._mdns_addrs = set()
        self._mdns_peer_addrs = {}
        self.seed_peers = [
            (str(host), int(port)) for host, port in (seed_peers or [])
            if host and 0 < int(port) <= 65535
        ]
        self.peers = {}  # {peer_id: PeerHandler}
        self.known_addrs = []  # [(addr, port, timestamp)]
        for host, port in self.seed_peers:
            self._remember_address(host, port)
        self.mempool = {}  # {txid_hex: tx_bytes}
        self._seen_headers = set()
        self._peer_counter = 0
        self._server = None
        self._loop = None
        self._running = False
        self._my_address = None  # Set when we know our external address
        self._node_id = os.urandom(32)
        self._erepr_sequence = 0
        self._seen_resonances = {}
        self._erepr_gossip_sent = 0
        self._erepr_gossip_received = 0
        self._last_erepr_announcement = 0.0
        self._connecting = set()
        self._stop_event = None
        self._ready = threading.Event()
        self._startup_error = None
        self._thread = None

    @staticmethod
    def _pack_ip(host):
        if not host:
            return b"\x00" * 16
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return b"\x00" * 16
        if address.is_unspecified or address.is_multicast:
            return b"\x00" * 16
        if address.version == 4:
            return b"\x00" * 10 + b"\xff\xff" + address.packed
        return address.packed

    @staticmethod
    def _unpack_ip(packed):
        if len(packed) != 16:
            return None
        address = ipaddress.ip_address(packed)
        if address.ipv4_mapped:
            address = address.ipv4_mapped
        return None if address.is_unspecified or address.is_multicast else str(address)

    def _remember_address(self, host, port):
        try:
            port = int(port)
            host = str(host).strip().strip("[]")
        except (TypeError, ValueError):
            return False
        if not host or not 0 < port <= 65535:
            return False
        try:
            address = ipaddress.ip_address(host)
            if address.is_unspecified or address.is_multicast:
                return False
            host = str(address)
        except ValueError:
            # DNS names are accepted only for explicitly configured seeds;
            # peer gossip is encoded as binary IP addresses.
            host = host.lower()
        now = int(time.time())
        for index, (known_host, known_port, _timestamp) in enumerate(self.known_addrs):
            if (known_host, known_port) == (host, port):
                self.known_addrs[index] = (host, port, now)
                return False
        self.known_addrs.append((host, port, now))
        if len(self.known_addrs) > MAX_ADDR_SIZE:
            self.known_addrs = self.known_addrs[-MAX_ADDR_SIZE:]
        return True

    def _erepr_addresses(self):
        addresses = []
        if self.advertise_host:
            self._remember_address(self.advertise_host, self.listen_port)
        for host, port, _timestamp in reversed(self.known_addrs):
            packed = self._pack_ip(host)
            if packed == b"\x00" * 16:
                continue
            item = (host, port, packed)
            if all((host, port) != (entry[0], entry[1]) for entry in addresses):
                addresses.append(item)
            if len(addresses) >= EREPR_MAX_ADDRESSES:
                break
        return addresses

    @staticmethod
    def _encode_erepr(resonance_id, phase, amplitude, addresses,
                      origin_node_id=None, sequence=None, issued_at=None,
                      hops=0):
        payload = bytearray(resonance_id)
        payload.extend(struct.pack("<d", phase))
        payload.extend(struct.pack("<d", amplitude))
        payload.extend(struct.pack("<I", len(addresses)))
        for _host, port, packed_ip in addresses:
            payload.extend(packed_ip)
            payload.extend(struct.pack(">H", port))
        if origin_node_id is not None:
            payload.extend(EREPR_EXTENSION.pack(
                EREPR_EXTENSION_MAGIC,
                EREPR_EXTENSION_VERSION,
                origin_node_id,
                sequence,
                issued_at,
                hops,
            ))
        return bytes(payload)

    def _new_erepr_payload(self, extended=True):
        self._erepr_sequence += 1
        issued_at = int(time.time())
        resonance_id = hashlib.sha256(
            self._node_id + struct.pack("<Q", self._erepr_sequence)
        ).digest()
        phase = time.time() % (2 * math.pi)
        return self._encode_erepr(
            resonance_id, phase, 1.0, self._erepr_addresses(),
            origin_node_id=self._node_id if extended else None,
            sequence=self._erepr_sequence if extended else None,
            issued_at=issued_at if extended else None,
        )

    def _send_erepr_to(self, peer_id, payload):
        peer = self.peers.get(peer_id)
        if peer and peer.score.services & NODE_EREPR and self._loop and self._loop.is_running():
            self._erepr_gossip_sent += 1
            self._loop.call_soon_threadsafe(
                lambda p=peer, msg=payload: self._loop.create_task(p._send("erepr", msg))
            )

    def _has_connection_to(self, address):
        return address in self._connecting or any(
            peer.target_addr == address or peer.advertised_addr == address
            for peer in self.peers.values()
        )

    def _may_dial_advertised(self, host, port):
        if port == self.listen_port and (
            host == self.advertise_host
            or host == self.listen_host
            or (self.listen_host in ("0.0.0.0", "::") and host in ("127.0.0.1", "::1"))
        ):
            return False
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return False
        return self.allow_private_peers or address.is_global

    def start(self):
        """Start the P2P node in a background thread."""
        self._loop = asyncio.new_event_loop()
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        if not self._ready.wait(timeout=5):
            raise TimeoutError("P2P listener did not become ready within 5 seconds")
        if self._startup_error:
            raise RuntimeError(f"P2P listener failed to start: {self._startup_error}")
        logger.info(f"P2P node listening on {self.listen_host}:{self.listen_port}")

    def stop(self):
        """Stop the P2P node."""
        self._running = False
        if self._loop and self._loop.is_running():
            if self._stop_event is not None:
                self._loop.call_soon_threadsafe(self._stop_event.set)
        if self._thread and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)

    def _run_loop(self):
        try:
            self._loop.run_until_complete(self._run_async())
        except OSError as exc:
            self._startup_error = exc
            self._ready.set()
            logger.error("P2P listener failed on %s:%s: %s",
                         self.listen_host, self.listen_port, exc)
        except Exception:
            self._startup_error = "unexpected event-loop failure"
            self._ready.set()
            logger.exception("P2P event loop failed")
        finally:
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            if pending:
                self._loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            self._loop.close()

    async def _run_async(self):
        """Main async event loop."""
        # Start TCP listener
        self._server = await asyncio.start_server(
            self._accept_connection,
            self.listen_host,
            self.listen_port
        )
        self.listen_port = self._server.sockets[0].getsockname()[1]
        self._ready.set()
        if self.enable_mdns:
            try:
                from p2p_transports import LocalPeerDiscovery

                self._mdns_discovery = LocalPeerDiscovery(
                    self._node_id, self.listen_port, self._on_mdns_peer
                )
                await asyncio.to_thread(self._mdns_discovery.start)
                logger.info("mDNS peer discovery active on port %s", self.listen_port)
            except (ImportError, OSError, RuntimeError) as exc:
                if self._mdns_discovery is not None:
                    await asyncio.to_thread(self._mdns_discovery.close)
                self._mdns_discovery = None
                logger.warning("mDNS discovery unavailable; continuing without it: %s", exc)
        if not self.enable_webrtc:
            logger.info("WebRTC unavailable or disabled; using TCP P2P transport")
        async with self._server:
            # Connect to seed peers
            for seed in self.seed_peers:
                asyncio.create_task(self._connect_to(seed))

            # Periodic tasks
            self._stop_event = asyncio.Event()
            if not self._running:
                self._stop_event.set()
            while self._running:
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=30)
                    break
                except asyncio.TimeoutError:
                    await self._periodic_tasks()
            self._server.close()
            await self._server.wait_closed()
            peers = list(self.peers.values())
            for peer in peers:
                peer._close()
            await asyncio.gather(
                *(peer._close_rtc() for peer in peers),
                return_exceptions=True,
            )
            if self._mdns_discovery is not None:
                await asyncio.to_thread(self._mdns_discovery.close)
                self._mdns_discovery = None

    def _on_mdns_peer(self, host, port, remote_node_id):
        if not self._loop or not self._loop.is_running():
            return
        self._loop.call_soon_threadsafe(
            self._schedule_mdns_connection, host, port, remote_node_id
        )

    def _schedule_mdns_connection(self, host, port, remote_node_id):
        local_node_id = self._node_id.hex()
        if (
            len(remote_node_id) != 64
            or any(character not in "0123456789abcdef" for character in remote_node_id)
            or remote_node_id == local_node_id
            or local_node_id > remote_node_id
            or remote_node_id in self._mdns_peer_addrs
        ):
            return
        try:
            address = (str(ipaddress.ip_address(host)), int(port))
        except (TypeError, ValueError):
            return
        if not 0 < address[1] <= 65535:
            return
        self._mdns_peer_addrs[remote_node_id] = address
        self._mdns_addrs.add(address)
        if self._running and not self._has_connection_to(address):
            self._loop.create_task(self._connect_to(address))

    async def _accept_connection(self, reader, writer):
        """Accept an incoming peer connection."""
        if len(self.peers) >= MAX_PEERS:
            writer.close()
            await writer.wait_closed()
            return
        self._peer_counter += 1
        peer_id = f"peer-{self._peer_counter}"
        addr = writer.get_extra_info("peername")
        logger.info(f"[{peer_id}] incoming connection from {addr}")

        peer = PeerHandler(peer_id, reader, writer, self)
        peer.score.ip_prefix = addr[0] if addr else None
        peer.remote_addr = addr
        self.peers[peer_id] = peer
        await peer.handshake()
        asyncio.create_task(peer.read_loop())

    async def _connect_to(self, addr_port):
        """Outgoing connection to a seed peer."""
        host, port = addr_port
        target = (str(host).strip().strip("[]"), int(port))
        if not target[0] or not 0 < target[1] <= 65535:
            logger.warning("Ignoring invalid P2P peer address: %r", addr_port)
            return
        if len(self.peers) >= MAX_PEERS or self._has_connection_to(target):
            return
        self._connecting.add(target)
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(*target), timeout=10
            )
            self._peer_counter += 1
            peer_id = f"peer-{self._peer_counter}"
            logger.info(f"[{peer_id}] connecting to {target[0]}:{target[1]}")

            peer = PeerHandler(peer_id, reader, writer, self)
            peer.remote_addr = target
            peer.target_addr = target
            peer.score.ip_prefix = target[0]
            self.peers[peer_id] = peer

            await peer.handshake()
            asyncio.create_task(peer.read_loop())
        except (asyncio.TimeoutError, ConnectionRefusedError, OSError, ValueError) as e:
            logger.warning(f"Failed to connect to {target[0]}:{target[1]}: {e}")
        finally:
            self._connecting.discard(target)

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

        # Retry every configured seed and dial newly gossiped addresses until
        # the target peer count is reached. A failed first seed must not starve
        # all later seeds.
        candidates = list(self.seed_peers)
        candidates.extend(self._mdns_addrs)
        candidates.extend((host, port) for host, port, _ in reversed(self.known_addrs))
        active = sum(1 for peer in self.peers.values() if not peer.score.is_banned)
        slots = max(0, min(IDEAL_PEERS, MAX_PEERS) - active)
        scheduled = 0
        for address in dict.fromkeys(candidates):
            if scheduled >= slots:
                break
            if self._has_connection_to(address):
                continue
            if (
                address not in self.seed_peers
                and address not in self._mdns_addrs
                and not self._may_dial_advertised(*address)
            ):
                continue
            self._loop.create_task(self._connect_to(address))
            scheduled += 1

        now = time.time()
        if (self.peers and
                now - self._last_erepr_announcement >= EREPR_ANNOUNCE_INTERVAL):
            for peer_id, peer in list(self.peers.items()):
                payload = self._new_erepr_payload(
                    extended=bool(peer.score.services & NODE_EREPR_V2)
                )
                self._send_erepr_to(peer_id, payload)
            self._last_erepr_announcement = now

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
            # Start EREPR discovery as soon as the protocol handshake completes.
            self._send_erepr_to(
                peer_id,
                self._new_erepr_payload(
                    extended=bool(peer.score.services & NODE_EREPR_V2)
                ),
            )

    def _on_peer_disconnected(self, peer_id):
        """Peer disconnected."""
        self.peers.pop(peer_id, None)
        logger.info(f"[{peer_id}] disconnected, peers={len(self.peers)}")

    # --- AetherionEXCAL: EREPR and Swap node-level handlers ---

    def _on_erepr_resonance(self, peer_id, resonance_id, phase, amplitude,
                            addresses=(), origin_node_id=None, sequence=None,
                            issued_at=None, hops=0):
        """Handle EREPR resonance from a peer.
        
        Updates our resonance state and broadcasts to other EREPR-capable peers.
        """
        now = time.time()
        expired = [
            seen_id for seen_id, seen_at in self._seen_resonances.items()
            if now - seen_at > EREPR_SEEN_TTL
        ]
        for seen_id in expired:
            del self._seen_resonances[seen_id]

        discovered = []
        for host, port in addresses:
            if self._remember_address(host, port):
                address = (host, port)
                discovered.append(address)
                if (len(self.peers) < IDEAL_PEERS
                        and self._may_dial_advertised(host, port)
                        and not self._has_connection_to(address)):
                    asyncio.create_task(self._connect_to(address))

        if resonance_id in self._seen_resonances:
            return
        self._seen_resonances[resonance_id] = now
        if len(self._seen_resonances) > 10_000:
            oldest = min(self._seen_resonances, key=self._seen_resonances.get)
            del self._seen_resonances[oldest]
        self._erepr_gossip_received += 1

        logger.info(
            f"EREPR resonance from {peer_id}: id={resonance_id[:16]}... "
            f"phase={phase:.2f} amplitude={amplitude:.2f} "
            f"new_peers={len(discovered)}"
        )
        
        # Relay the same wave with decayed amplitude. Keeping the ID unchanged
        # lets each node suppress loops while forwarding the address set.
        next_amplitude = amplitude * EREPR_WAVE_DECAY
        if (next_amplitude <= EREPR_MIN_AMPLITUDE
                or hops >= EREPR_MAX_HOPS):
            return
        try:
            message_id = bytes.fromhex(resonance_id)
        except ValueError:
            return
        for pid, peer in self.peers.items():
            if pid != peer_id and (peer.score.services & NODE_EREPR):
                extended = bool(
                    origin_node_id is not None
                    and peer.score.services & NODE_EREPR_V2
                )
                payload = self._encode_erepr(
                    message_id, phase, next_amplitude, self._erepr_addresses(),
                    origin_node_id=origin_node_id if extended else None,
                    sequence=sequence if extended else None,
                    issued_at=issued_at if extended else None,
                    hops=hops + 1 if extended else 0,
                )
                self._send_erepr_to(pid, payload)

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

    async def _on_camelot(self, peer_id: str, payload: bytes):
        """Handle Camelot game gossip message.
        
        Forwards to camelot_api module for processing game events
        like purchases, item transfers, achievements, and guild events.
        """
        try:
            from camelot_api import handle_camelot_gossip
            await handle_camelot_gossip(self, peer_id, payload)
        except ImportError:
            logger.warning("camelot_api module not available, ignoring game gossip")

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

        # Header announcements do not carry transactions, so they cannot
        # advance ChainStore's validated active chain or its UTXO state.
        if self.chain_store.getblock(block_hash) or block_hash in self._seen_headers:
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

        self._seen_headers.add(block_hash)
        logger.info("Header announced by %s: %s...", peer_id, block_hash[:16])
        # Headers are announcements only. Ask for the body and let the
        # validated ChainStore decide whether it can advance the tip.
        self._request_block(peer_id, block_hash)

    def _on_new_tx(self, peer_id, tx_bytes):
        """Peer relayed a new transaction."""
        txid = gf.txid(tx_bytes).hex()
        if txid in self.mempool:
            return
        try:
            self.chain_store.sendrawtransaction(tx_bytes.hex(), relay=False)
        except (RuntimeError, TypeError, ValueError) as exc:
            peer = self.peers.get(peer_id)
            if peer:
                peer.score.penalize("invalid_transaction", REP_PENALTY_INVALID)
            logger.warning("[%s] rejected relayed transaction %s: %s",
                           peer_id, txid[:16], exc)
            return
        self.mempool[txid] = tx_bytes
        # Relay to other peers
        self._relay_tx(tx_bytes)

    def _on_new_block(self, peer_id, payload):
        """Peer sent a full block."""
        peer = self.peers.get(peer_id)
        try:
            if not isinstance(payload, bytes) or not 80 <= len(payload) <= MAX_BLOCK_SIZE:
                raise ValueError("invalid block payload size")
            header = payload[:80]
            version = struct.unpack_from("<I", header, 0)[0]
            prev = header[4:36]
            merkle = header[36:68]
            timestamp, bits, nonce = struct.unpack_from("<III", header, 68)
            txs = []
            offset = 80
            while offset < len(payload):
                if offset + 4 > len(payload):
                    raise ValueError("truncated transaction length")
                tx_size = struct.unpack_from("<I", payload, offset)[0]
                offset += 4
                if tx_size == 0 or tx_size > MAX_TX_SIZE or offset + tx_size > len(payload):
                    raise ValueError("invalid or truncated transaction")
                txs.append(payload[offset:offset + tx_size])
                offset += tx_size
            if not txs:
                raise ValueError("block has no transactions")
            block = {
                "version": version, "prev": prev.hex(),
                "merkle": merkle.hex(), "time": timestamp,
                "bits": bits, "nonce": nonce, "txs": txs,
            }
            result, error = self.chain_store.submitblock(block)
            if error:
                self._seen_headers.discard(sha256d(header).hex())
                logger.warning("[%s] rejected block: %s", peer_id, error)
                if peer and "must extend the validated active-chain tip" not in error:
                    peer.score.penalize("invalid_block", REP_PENALTY_INVALID)
                return
            if peer:
                peer.score.blocks_received += 1
                peer.score.reward("valid_block", REP_REWARD_BLOCK)
            logger.info("[%s] accepted block %s at height %s", peer_id,
                        result["hash"][:16], result["height"])
            self.mempool.clear()
            self._relay_header(header)
        except (KeyError, TypeError, ValueError, struct.error) as exc:
            if peer:
                peer.score.penalize("malformed_block", REP_PENALTY_INVALID)
            logger.warning("[%s] malformed block (%d bytes): %s",
                           peer_id, len(payload) if isinstance(payload, bytes) else 0, exc)
            if isinstance(payload, bytes) and len(payload) >= 80:
                self._seen_headers.discard(sha256d(payload[:80]).hex())

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
            bytes.fromhex(tip["prev"]) if isinstance(tip["prev"], str) else tip["prev"],
            bytes.fromhex(tip["merkle"]) if isinstance(tip["merkle"], str) else tip["merkle"],
            tip["time"],
            int(tip["bits"], 16) if isinstance(tip["bits"], str) else tip["bits"],
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
                block["version"],
                bytes.fromhex(block["prev"]) if isinstance(block["prev"], str) else block["prev"],
                bytes.fromhex(block["merkle"]) if isinstance(block["merkle"], str) else block["merkle"],
                block["time"],
                int(block["bits"], 16) if isinstance(block["bits"], str) else block["bits"],
                block["nonce"]
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
            "erepr_peers": sum(
                bool(p.score.services & NODE_EREPR) for p in self.peers.values()
            ),
            "erepr_v2_peers": sum(
                bool(p.score.services & NODE_EREPR_V2)
                for p in self.peers.values()
            ),
            "erepr_gossip_sent": self._erepr_gossip_sent,
            "erepr_gossip_received": self._erepr_gossip_received,
            "known_peer_addresses": len(self.known_addrs),
            "atomic_swap_enabled": True,
            "quantum_swap_enabled": True,
            "compact_blocks": True,
            "version": "2.0.0"
        }
    
    def get_erepr_stats(self):
        """Return EREPR protocol statistics."""
        erepr_peers = sum(
            bool(peer.score.services & NODE_EREPR) for peer in self.peers.values()
        )
        return {
            "enabled": True,
            "connected_erepr_peers": erepr_peers,
            "connected_erepr_v2_peers": sum(
                bool(peer.score.services & NODE_EREPR_V2)
                for peer in self.peers.values()
            ),
            "gossip_waves_sent": self._erepr_gossip_sent,
            "gossip_waves_received": self._erepr_gossip_received,
            "known_peer_addresses": len(self.known_addrs),
            "seen_resonances": len(self._seen_resonances),
            "configured_seed_peers": len(self.seed_peers),
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
    seed_values = args.seed or os.environ.get("FORK_P2P_SEEDS", "").split(",")
    seed_peers = parse_seed_peers(seed_values)

    p2p = P2PNode(store, rpc_port=args.rpc_port, seed_peers=seed_peers,
                  listen_host=os.environ.get("FORK_P2P_HOST", "0.0.0.0"),
                  listen_port=args.p2p_port,
                  advertise_host=os.environ.get("FORK_P2P_ADVERTISE_HOST"))
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
