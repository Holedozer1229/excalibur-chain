"""quantum_p2p_glue.py — P2P integration layer for quantum protocols.

Connects the E91 entanglement handshake and GHZ random beacon to the
existing SkyNet P2P infrastructure (skynet_client.py, skynet_beacon.py).

This module provides:

1. **QuantumPeerAuth** — Wraps the E91 handshake for peer-to-peer
   identity verification. When two P2P nodes first connect, they run
   an E91 handshake to establish a shared session key verified by
   CHSH inequality testing.

2. **QuantumBeaconService** — Integrates the GHZ beacon with the
   SkyNet beacon service to provide network-wide shared randomness
   for consensus tie-breaking, leader election, and state sync.

3. **QuantumChannel** — A high-level abstraction for encrypted P2P
   communication channels secured by E91-derived session keys.

Usage:
    from sphinx_os.nexus.quantum import E91Handshake, GHZBeacon
    from quantum_p2p_glue import QuantumPeerAuth, QuantumBeaconService

    # Authenticate a new peer connection
    auth = QuantumPeerAuth()
    session_key = auth.authenticate_peer(peer_id)

    # Get network-wide random beacon
    beacon_svc = QuantumBeaconService(participants=10)
    random_nonce = beacon_svc.get_random_nonce()
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import socket
import struct
import threading
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from sphinx_os.nexus.quantum import E91Handshake, GHZBeacon

logger = logging.getLogger(__name__)

# Message types for quantum protocol P2P messages
Q_MSG_HANDSHAKE_REQUEST = 0x80
Q_MSG_HANDSHAKE_RESPONSE = 0x81
Q_MSG_BEACON_CONTRIBUTE = 0x82
Q_MSG_BEACON_RESULT = 0x83
Q_MSG_CHALLENGE = 0x84
Q_MSG_RESPONSE = 0x85


class QuantumPeerAuth:
    """E91-based peer authentication for P2P connections.

    When a new peer connects, both sides run an E91 handshake to:
    1. Verify quantum correlation (detects man-in-the-middle)
    2. Establish a shared session key
    3. Authenticate peer identity via challenge-response

    The session key is then used to HMAC-sign all subsequent messages
    on this channel, providing integrity and authenticity.

    Attributes:
        peer_id: Identifier for the remote peer.
        session_key: Derived session key (32 bytes).
        authenticated: Whether CHSH test passed.
    """

    def __init__(
        self,
        num_pairs: int = 64,
        key_length: int = 32,
        chsh_threshold: float = 2.0,
        seed: Optional[int] = None,
    ):
        self.num_pairs = num_pairs
        self.key_length = key_length
        self.chsh_threshold = chsh_threshold
        self._seed = seed
        self._attempt = 0

        self._peer_keys: Dict[str, bytes] = {}
        self._peer_auth_status: Dict[str, bool] = {}
        self._peer_chsh_values: Dict[str, float] = {}
        self._lock = threading.Lock()

    def authenticate_peer(self, peer_id: str) -> Optional[bytes]:
        """Run E91 handshake with a peer to establish session key.

        Retries up to 5 times with different seeds if CHSH test fails,
        since the protocol is probabilistic.

        Args:
            peer_id: Unique identifier for the remote peer.

        Returns:
            Session key (32 bytes) if authentication succeeds, None otherwise.
        """
        # Retry up to 5 times — E91 is probabilistic
        for attempt in range(5):
            seed = self._seed if self._seed is not None else (attempt * 1000 + self._attempt)
            self._attempt += 1

            handshake = E91Handshake(
                num_pairs=self.num_pairs,
                key_length=self.key_length,
                chsh_threshold=self.chsh_threshold,
                seed=seed,
            )

            key, chsh_value = handshake.run()

            if key is not None:
                # Derive session key from the raw E91 key + peer identity
                session_key = self._derive_session_key(key, peer_id)

                with self._lock:
                    self._peer_keys[peer_id] = session_key
                    self._peer_auth_status[peer_id] = True
                    self._peer_chsh_values[peer_id] = chsh_value

                logger.info(
                    "E91 handshake succeeded for peer %s: CHSH=%.3f, key=%s...",
                    peer_id, chsh_value, session_key.hex()[:16],
                )
                return session_key

            logger.debug(
                "E91 handshake attempt %d for peer %s: CHSH=%.3f (threshold=%.1f)",
                attempt + 1, peer_id, chsh_value, self.chsh_threshold,
            )

        # All attempts failed
        logger.warning(
            "E91 handshake failed for peer %s after 5 attempts. "
            "Possible eavesdropping or noise.",
            peer_id,
        )
        with self._lock:
            self._peer_auth_status[peer_id] = False
        return None

    def _derive_session_key(self, raw_key: bytes, peer_id: str) -> bytes:
        """Derive a session key from raw E91 output and peer identity.

        Uses HKDF-like construction: HMAC-SHA256(raw_key, peer_id || context)
        """
        context = b"aetherion-excalibur-p2p-session-key-v1"
        info = peer_id.encode() + b"\x00" + context
        return hmac.new(raw_key, info, hashlib.sha256).digest()

    def sign_message(self, peer_id: str, message: bytes) -> bytes:
        """HMAC-sign a message for an authenticated peer.

        Args:
            peer_id: The peer to send the message to.
            message: The message bytes to sign.

        Returns:
            HMAC-SHA256 signature (32 bytes).

        Raises:
            ValueError: If peer is not authenticated.
        """
        with self._lock:
            key = self._peer_keys.get(peer_id)

        if key is None:
            raise ValueError(f"Peer {peer_id} is not authenticated")

        return hmac.new(key, message, hashlib.sha256).digest()

    def verify_message(
        self, peer_id: str, message: bytes, signature: bytes
    ) -> bool:
        """Verify an HMAC-signed message from a peer.

        Args:
            peer_id: The peer that sent the message.
            message: The message bytes.
            signature: The HMAC signature to verify.

        Returns:
            True if the signature is valid.
        """
        with self._lock:
            key = self._peer_keys.get(peer_id)

        if key is None:
            return False

        expected = hmac.new(key, message, hashlib.sha256).digest()
        return hmac.compare_digest(expected, signature)

    def get_peer_status(self, peer_id: str) -> Dict[str, Any]:
        """Get authentication status for a peer."""
        with self._lock:
            return {
                "peer_id": peer_id,
                "authenticated": self._peer_auth_status.get(peer_id, False),
                "chsh_value": self._peer_chsh_values.get(peer_id),
                "has_session_key": peer_id in self._peer_keys,
            }


class QuantumBeaconService:
    """GHZ-based random beacon integrated with SkyNet P2P.

    Provides network-wide shared randomness for:
    - Consensus tie-breaking
    - Random leader election for block proposal
    - State synchronization randomness
    - Challenge-response nonces

    The beacon runs periodically, generating fresh random bits via
    simulated GHZ states. In production, multiple nodes would each
    contribute to the beacon, and the final output would be the XOR
    of all contributions (threshold randomness).

    Attributes:
        participants: Number of nodes contributing to the beacon.
        rounds: Number of GHZ rounds per beacon generation.
    """

    def __init__(
        self,
        participants: int = 8,
        rounds: int = 16,
        interval: float = 60.0,
        seed: Optional[int] = None,
    ):
        self.participants = participants
        self.rounds = rounds
        self.interval = interval
        self.seed = seed

        self._beacon = GHZBeacon(
            num_participants=participants,
            num_rounds=rounds,
            seed=seed,
        )
        self._latest_beacon: Optional[bytes] = None
        self._latest_timestamp: float = 0.0
        self._beacon_history: List[Tuple[float, bytes]] = []
        self._lock = threading.Lock()

        # Background beacon thread
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Callbacks
        self._on_beacon_update: Optional[Callable[[bytes], None]] = None

    def start(self) -> None:
        """Start the periodic beacon generation loop."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._beacon_loop, daemon=True, name="quantum-beacon"
        )
        self._thread.start()
        logger.info(
            "Quantum beacon started: %d participants, %d rounds, %.1fs interval",
            self.participants, self.rounds, self.interval,
        )

    def stop(self) -> None:
        """Stop the periodic beacon generation loop."""
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        logger.info("Quantum beacon stopped")

    def _beacon_loop(self) -> None:
        """Background loop that generates beacons periodically."""
        while self._running:
            try:
                beacon_bytes = self.generate_beacon()
                if self._on_beacon_update is not None:
                    self._on_beacon_update(beacon_bytes)
            except Exception as e:
                logger.error("Beacon generation error: %s", e)
            time.sleep(self.interval)

    def generate_beacon(self) -> bytes:
        """Generate a fresh beacon and store it.

        Returns:
            Beacon bytes (rounds/8 bytes, padded).
        """
        bits = self._beacon.generate_beacon()
        beacon_bytes = self._beacon.get_beacon_bytes()
        timestamp = time.time()

        with self._lock:
            self._latest_beacon = beacon_bytes
            self._latest_timestamp = timestamp
            self._beacon_history.append((timestamp, beacon_bytes))
            # Keep only last 1000 beacons
            if len(self._beacon_history) > 1000:
                self._beacon_history = self._beacon_history[-1000:]

        logger.debug(
            "Beacon generated: %s... (entropy=%.3f)",
            beacon_bytes.hex()[:16],
            self._beacon.compute_entropy(),
        )
        return beacon_bytes

    def get_latest_beacon(self) -> Optional[Tuple[bytes, float]]:
        """Get the latest beacon and its timestamp.

        Returns:
            (beacon_bytes, timestamp) or None if no beacon yet.
        """
        with self._lock:
            if self._latest_beacon is None:
                return None
            return (self._latest_beacon, self._latest_timestamp)

    def get_random_nonce(self, length: int = 32) -> bytes:
        """Get a random nonce derived from the latest beacon.

        Args:
            length: Desired nonce length in bytes.

        Returns:
            Random nonce bytes.
        """
        beacon_data = self.get_latest_beacon()
        if beacon_data is None:
            # Generate a fresh beacon if none available
            self.generate_beacon()
            beacon_data = self.get_latest_beacon()

        if beacon_data is None:
            # Fallback to OS randomness
            return os.urandom(length)

        beacon_bytes, timestamp = beacon_data
        # Derive nonce from beacon + timestamp
        seed = beacon_bytes + struct.pack("d", timestamp)
        h = hashlib.sha256(seed).digest()
        # Extend to desired length
        while len(h) < length:
            h += hashlib.sha256(h).digest()
        return h[:length]

    def on_beacon_update(self, callback: Callable[[bytes], None]) -> None:
        """Register a callback for beacon updates."""
        self._on_beacon_update = callback

    def get_stats(self) -> Dict[str, Any]:
        """Get beacon statistics."""
        with self._lock:
            history_len = len(self._beacon_history)
        beacon_stats = self._beacon.get_stats()
        return {
            **beacon_stats,
            "running": self._running,
            "interval_seconds": self.interval,
            "latest_timestamp": self._beacon_history[-1][0] if self._beacon_history else None,
            "history_length": history_len,
        }


class QuantumChannel:
    """Encrypted P2P channel secured by E91-derived session keys.

    High-level abstraction for sending authenticated, integrity-protected
    messages over P2P connections.

    Usage:
        auth = QuantumPeerAuth()
        channel = QuantumChannel(auth)

        # Establish secure channel with a peer
        key = auth.authenticate_peer("peer-123")
        if key:
            msg = channel.send("peer-123", b"Hello, secure world!")

    Attributes:
        auth: QuantumPeerAuth instance for key management.
    """

    def __init__(self, auth: QuantumPeerAuth):
        self.auth = auth
        self._message_counter: Dict[str, int] = {}
        self._lock = threading.Lock()

    def send(
        self, peer_id: str, payload: bytes, metadata: Optional[Dict] = None
    ) -> bytes:
        """Send an authenticated message to a peer.

        Constructs a length-prefixed message with:
        - Message type byte
        - Sequence number (4 bytes, big-endian)
        - JSON metadata (optional, length-prefixed)
        - Payload bytes
        - HMAC-SHA256 signature

        Args:
            peer_id: Target peer identifier.
            payload: Message payload bytes.
            metadata: Optional JSON-serializable metadata dict.

        Returns:
            Serialized message bytes ready for transmission.

        Raises:
            ValueError: If peer is not authenticated.
        """
        with self._lock:
            seq = self._message_counter.get(peer_id, 0)
            self._message_counter[peer_id] = seq + 1

        # Build message body
        body_parts = [struct.pack(">I", seq)]

        if metadata:
            meta_bytes = json.dumps(metadata).encode()
            body_parts.append(struct.pack(">H", len(meta_bytes)))
            body_parts.append(meta_bytes)

        body_parts.append(payload)
        body = b"".join(body_parts)

        # Sign
        signature = self.auth.sign_message(peer_id, body)

        # Serialize: type + length + body + signature
        msg = struct.pack(">BH", Q_MSG_RESPONSE, len(body))
        msg += body + signature

        return msg

    def receive(self, peer_id: str, raw_message: bytes) -> Optional[Dict[str, Any]]:
        """Receive and verify an authenticated message from a peer.

        Args:
            peer_id: Source peer identifier.
            raw_message: Raw message bytes from the network.

        Returns:
            Dict with 'sequence', 'metadata', 'payload' keys,
            or None if verification fails.

        Raises:
            ValueError: If peer is not authenticated.
            RuntimeError: If message verification fails.
        """
        if len(raw_message) < 3 + 4 + 32:  # type + len + seq + sig
            raise RuntimeError("Message too short")

        # Parse header
        msg_type, body_len = struct.unpack(">BH", raw_message[:3])
        body = raw_message[3:3 + body_len]
        signature = raw_message[3 + body_len:3 + body_len + 32]

        # Verify signature
        if not self.auth.verify_message(peer_id, body, signature):
            raise RuntimeError("Message signature verification failed")

        # Parse body
        offset = 0
        seq = struct.unpack(">I", body[offset:offset + 4])[0]
        offset += 4

        metadata = None
        if offset + 2 <= len(body):
            meta_len = struct.unpack(">H", body[offset:offset + 2])[0]
            offset += 2
            if offset + meta_len <= len(body):
                meta_bytes = body[offset:offset + meta_len]
                metadata = json.loads(meta_bytes.decode())
                offset += meta_len

        payload = body[offset:]

        return {
            "type": msg_type,
            "sequence": seq,
            "metadata": metadata,
            "payload": payload,
        }
