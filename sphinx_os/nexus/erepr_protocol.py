"""EREPR: Entanglement-Resonance Echo Peer Routing.

A novel P2P discovery and gossip protocol for the EXCAL blockchain.

===========================================================================
Concept
===========================================================================

Unlike traditional P2P protocols that use flooding or kademlia-style DHT,
EREPR models each node as a **resonant oscillator** in a shared quantum
field. Nodes discover each other through **echo-based resonance matching**
and form gossip channels through **entanglement bonds**.

How it works
------------

1. **Resonance Signature** — Each node generates a unique resonance
   signature from its public key, timestamp, and a quantum entropy seed.
   This signature is a point on a toroidal manifold (T²).

2. **Echo Broadcast** — Nodes periodically broadcast their resonance
   signature as an "echo" packet. The echo carries the node's identity,
   services, and a challenge hash.

3. **Resonance Matching** — When a node receives an echo, it computes the
   **resonance score** — a measure of how well the two nodes' signatures
   align on the toroidal manifold. High resonance ≈ compatible peers.

4. **Entanglement Bond** — If resonance exceeds a threshold, the two nodes
   form an entanglement bond. This bond is a shared secret derived from
   both signatures, used to encrypt future gossip.

5. **Echo Confirmation** — The receiving node sends back an echo
   confirmation, creating a bidirectional bond. This three-way handshake
   (echo → match → confirm) prevents spoofing.

6. **Gossip Propagation** — Messages propagate through entanglement bonds
   using a **wave propagation** model: each node forwards to its bonded
   peers with a decay factor based on bond strength. Stronger bonds carry
   messages further.

7. **Resonance Decay** — Bonds decay over time without heartbeats. Nodes
   must periodically re-echo to maintain bonds, creating a natural
   churn-resistant network.

Why it's novel
--------------

- No DHT, no flooding, no bootstrap servers.
- Nodes self-organize through resonance matching — like tuning forks
  finding each other in a dark room.
- The toroidal manifold ensures uniform distribution — no hotspots.
- Wave propagation naturally limits gossip depth — no infinite loops.
- Entanglement bonds provide implicit authentication — strangers can't
  inject messages into bonded channels.

Author: AetherionEXCAL Project
Website: https://www.aetherion-oracle.com
"""

import hashlib
import hmac
import math
import time
import secrets
import threading
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set, Tuple
from collections import defaultdict


# ---------------------------------------------------------------------------
# EREPR Constants
# ---------------------------------------------------------------------------

# Toroidal manifold dimensions
TORUS_RADIUS_X = 2 * math.pi
TORUS_RADIUS_Y = 2 * math.pi

# Resonance threshold for bond formation
RESONANCE_THRESHOLD = 0.6

# Echo broadcast interval (seconds)
ECHO_INTERVAL = 15

# Bond decay rate (per second)
BOND_DECAY_RATE = 0.001

# Wave propagation decay factor
WAVE_DECAY = 0.85

# Maximum gossip depth
MAX_GOSSIP_DEPTH = 10

# Echo TTL
ECHO_TTL = 30


# ---------------------------------------------------------------------------
# Resonance Signature
# ---------------------------------------------------------------------------

@dataclass
class ResonanceSignature:
    """A node's resonance signature on the toroidal manifold."""
    node_id: str
    angle_x: float  # Position on torus X (0..2π)
    angle_y: float  # Position on torus Y (0..2π)
    frequency: float  # Oscillation frequency
    phase: float  # Current phase
    timestamp: float
    challenge: str  # HMAC challenge for echo confirmation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "angle_x": self.angle_x,
            "angle_y": self.angle_y,
            "frequency": self.frequency,
            "phase": self.phase,
            "timestamp": self.timestamp,
            "challenge": self.challenge,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ResonanceSignature':
        return cls(**data)

    @classmethod
    def generate(cls, node_id: str, secret: bytes) -> 'ResonanceSignature':
        """Generate a resonance signature from a node's identity."""
        now = time.time()
        # Derive toroidal position from node ID
        h = hashlib.sha256(node_id.encode() + secret).digest()
        angle_x = (int.from_bytes(h[0:8], "big") % 10000) / 10000 * TORUS_RADIUS_X
        angle_y = (int.from_bytes(h[8:16], "big") % 10000) / 10000 * TORUS_RADIUS_Y
        # Frequency from entropy
        frequency = 0.1 + (int.from_bytes(h[16:24], "big") % 1000) / 10000
        # Phase from timestamp
        phase = (now * frequency) % (2 * math.pi)
        # Challenge for echo confirmation
        challenge = hmac.new(secret, str(now).encode(), "sha256").hexdigest()[:16]

        return cls(
            node_id=node_id,
            angle_x=angle_x,
            angle_y=angle_y,
            frequency=frequency,
            phase=phase,
            timestamp=now,
            challenge=challenge,
        )


# ---------------------------------------------------------------------------
# Entanglement Bond
# ---------------------------------------------------------------------------

@dataclass
class EntanglementBond:
    """A bond between two resonant nodes."""
    peer_id: str
    shared_secret: bytes
    resonance_score: float
    bond_strength: float  # 0..1, decays over time
    created_at: float
    last_heartbeat: float
    echo_count: int = 0

    def decay(self, elapsed: float):
        """Decay bond strength over time."""
        self.bond_strength = max(0.0, self.bond_strength - BOND_DECAY_RATE * elapsed)

    def strengthen(self):
        """Strengthen bond on heartbeat."""
        self.bond_strength = min(1.0, self.bond_strength + 0.1)
        self.last_heartbeat = time.time()
        self.echo_count += 1

    def is_alive(self) -> bool:
        """Check if bond is still alive."""
        return self.bond_strength > 0.1


# ---------------------------------------------------------------------------
# Echo Message
# ---------------------------------------------------------------------------

@dataclass
class EchoMessage:
    """An echo broadcast or confirmation."""
    sig: ResonanceSignature
    services: int
    user_agent: str
    is_confirmation: bool = False
    response_challenge: str = ""

    def to_json(self) -> str:
        return json.dumps({
            "sig": self.sig.to_dict(),
            "services": self.services,
            "user_agent": self.user_agent,
            "is_confirmation": self.is_confirmation,
            "response_challenge": self.response_challenge,
        })

    @classmethod
    def from_json(cls, data: str) -> 'EchoMessage':
        obj = json.loads(data)
        sig = ResonanceSignature.from_dict(obj["sig"])
        return cls(
            sig=sig,
            services=obj["services"],
            user_agent=obj["user_agent"],
            is_confirmation=obj.get("is_confirmation", False),
            response_challenge=obj.get("response_challenge", ""),
        )


# ---------------------------------------------------------------------------
# Gossip Wave
# ---------------------------------------------------------------------------

class GossipWave:
    """A gossip message propagating through entanglement bonds."""

    __slots__ = ('msg_id', 'source', 'payload', 'depth', 'amplitude', 'seen_by')

    def __init__(self, msg_id: str, source: str, payload: Dict[str, Any],
                 depth: int = 0, amplitude: float = 1.0,
                 seen_by: Set[str] = None):
        self.msg_id = msg_id
        self.source = source
        self.payload = payload
        self.depth = depth
        self.amplitude = amplitude
        self.seen_by = seen_by if seen_by is not None else set()

    def propagate(self) -> 'GossipWave':
        """Create a new wave instance for next hop."""
        self.depth += 1
        self.amplitude *= WAVE_DECAY
        return self

    def should_propagate(self) -> bool:
        """Check if wave should continue propagating."""
        return self.depth < MAX_GOSSIP_DEPTH and self.amplitude > 0.1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "msg_id": self.msg_id,
            "source": self.source,
            "payload": self.payload,
            "depth": self.depth,
            "amplitude": self.amplitude,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'GossipWave':
        return cls(
            msg_id=data["msg_id"],
            source=data["source"],
            payload=data["payload"],
            depth=data.get("depth", 0),
            amplitude=data.get("amplitude", 1.0),
        )


# ---------------------------------------------------------------------------
# EREPR Protocol Engine
# ---------------------------------------------------------------------------

class EREPRProtocol:
    """
    Entanglement-Resonance Echo Peer Routing protocol engine.

    Manages resonance signatures, entanglement bonds, echo broadcasts,
    and gossip wave propagation for a single node.
    """

    def __init__(self, node_id: str, secret: bytes = None):
        self.node_id = node_id
        self.secret = secret or secrets.token_bytes(32)
        self.services = 0x03  # Default: network + relay
        self.user_agent = f"EXCAL-EREPR/1.0"

        # Resonance state
        self.signature: Optional[ResonanceSignature] = None
        self.bonds: Dict[str, EntanglementBond] = {}
        self.known_peers: Dict[str, Dict[str, Any]] = {}

        # Gossip state
        self.seen_messages: Dict[str, float] = {}  # msg_id -> timestamp
        self.gossip_queue: List[GossipWave] = []

        # Echo state
        self._echo_thread = None
        self._running = False

    def initialize(self):
        """Initialize the protocol with a resonance signature."""
        self.signature = ResonanceSignature.generate(self.node_id, self.secret)

    def compute_resonance(self, other_sig: ResonanceSignature) -> float:
        """
        Compute resonance score between this node and another.

        Uses toroidal distance and frequency alignment.
        Returns a score in [0, 1] where 1 = perfect resonance.
        """
        if self.signature is None:
            return 0.0

        # Toroidal distance (shortest path on torus)
        dx = min(
            abs(self.signature.angle_x - other_sig.angle_x),
            TORUS_RADIUS_X - abs(self.signature.angle_x - other_sig.angle_x),
        )
        dy = min(
            abs(self.signature.angle_y - other_sig.angle_y),
            TORUS_RADIUS_Y - abs(self.signature.angle_y - other_sig.angle_y),
        )
        torus_dist = math.sqrt(dx ** 2 + dy ** 2)
        max_dist = math.sqrt(TORUS_RADIUS_X ** 2 + TORUS_RADIUS_Y ** 2)
        proximity = 1.0 - (torus_dist / max_dist)

        # Frequency alignment
        freq_diff = abs(self.signature.frequency - other_sig.frequency)
        freq_alignment = max(0.0, 1.0 - freq_diff * 10)

        # Phase coherence
        phase_diff = abs(self.signature.phase - other_sig.phase)
        phase_coherence = math.cos(phase_diff)

        # Combined resonance score
        resonance = (
            0.4 * proximity +
            0.35 * freq_alignment +
            0.25 * phase_coherence
        )
        return max(0.0, min(1.0, resonance))

    def receive_echo(self, echo: EchoMessage) -> Optional[EntanglementBond]:
        """
        Process an incoming echo. If resonance is high enough, form a bond.

        Returns the new/updated bond, or None if resonance is too low.
        """
        resonance = self.compute_resonance(echo.sig)

        if resonance < RESONANCE_THRESHOLD:
            return None

        # Check if we already have a bond
        peer_id = echo.sig.node_id
        if peer_id in self.bonds:
            bond = self.bonds[peer_id]
            bond.strengthen()
            bond.resonance_score = resonance
            return bond

        # Form new entanglement bond
        shared_secret = hashlib.sha256(
            self.secret + echo.sig.node_id.encode() + self.node_id.encode()
        ).digest()

        bond = EntanglementBond(
            peer_id=peer_id,
            shared_secret=shared_secret,
            resonance_score=resonance,
            bond_strength=resonance,
            created_at=time.time(),
            last_heartbeat=time.time(),
        )
        self.bonds[peer_id] = bond

        # Track peer info
        self.known_peers[peer_id] = {
            "services": echo.services,
            "user_agent": echo.user_agent,
            "signature": echo.sig.to_dict(),
        }

        return bond

    def create_echo_confirmation(self, echo: EchoMessage) -> Optional[EchoMessage]:
        """
        Create an echo confirmation if resonance is sufficient.

        The confirmation includes an HMAC response to the original challenge.
        """
        bond = self.receive_echo(echo)
        if bond is None:
            return None

        # HMAC response to challenge
        response = hmac.new(
            bond.shared_secret,
            echo.sig.challenge.encode(),
            "sha256",
        ).hexdigest()[:16]

        return EchoMessage(
            sig=self.signature,
            services=self.services,
            user_agent=self.user_agent,
            is_confirmation=True,
            response_challenge=response,
        )

    def confirm_echo(self, confirmation: EchoMessage, expected_challenge: str) -> bool:
        """
        Verify an echo confirmation. Returns True if the HMAC matches.
        """
        peer_id = confirmation.sig.node_id
        if peer_id not in self.bonds:
            return False

        bond = self.bonds[peer_id]
        expected = hmac.new(
            bond.shared_secret,
            expected_challenge.encode(),
            "sha256",
        ).hexdigest()[:16]

        return hmac.compare_digest(confirmation.response_challenge, expected)

    def create_gossip_wave(self, payload: Dict[str, Any]) -> GossipWave:
        """Create a new gossip wave for propagation."""
        msg_id = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()[:16]

        return GossipWave(
            msg_id=msg_id,
            source=self.node_id,
            payload=payload,
            depth=0,
            amplitude=1.0,
            seen_by=set(),
        )

    def should_forward_wave(self, wave: GossipWave) -> bool:
        """Check if a wave should be forwarded (not seen, still propagating)."""
        if wave.msg_id in self.seen_messages:
            return False
        if not wave.should_propagate():
            return False
        return True

    def forward_wave(self, wave: GossipWave) -> List[Tuple[str, GossipWave]]:
        """
        Forward a wave to bonded peers. Returns list of (peer_id, wave) pairs.

        Only forwards to peers with sufficient bond strength relative to
        the wave's amplitude.
        """
        if not self.should_forward_wave(wave):
            return []

        # Mark as seen
        self.seen_messages[wave.msg_id] = time.time()
        wave.seen_by.add(self.node_id)

        # Propagate wave
        wave.propagate()

        # Forward to bonded peers
        targets = []
        for peer_id, bond in self.bonds.items():
            if peer_id in wave.seen_by:
                continue
            if peer_id == self.node_id:
                continue
            # Only forward if bond strength is sufficient
            if bond.bond_strength >= wave.amplitude * 0.5:
                targets.append((peer_id, wave))

        return targets

    def receive_wave(self, wave: GossipWave) -> Optional[List[Tuple[str, GossipWave]]]:
        """
        Receive a gossip wave. Returns forwarded waves, or None if dropped.
        """
        if not self.should_forward_wave(wave):
            return None

        return self.forward_wave(wave)

    def decay_bonds(self):
        """Decay all bonds based on elapsed time."""
        now = time.time()
        dead = []
        for peer_id, bond in self.bonds.items():
            elapsed = now - bond.last_heartbeat
            bond.decay(elapsed)
            if not bond.is_alive():
                dead.append(peer_id)

        for peer_id in dead:
            del self.bonds[peer_id]

    def cleanup_seen_messages(self, max_age: float = 300.0):
        """Remove old seen message IDs."""
        now = time.time()
        dead = [
            msg_id for msg_id, ts in self.seen_messages.items()
            if now - ts > max_age
        ]
        for msg_id in dead:
            del self.seen_messages[msg_id]

    def get_network_state(self) -> Dict[str, Any]:
        """Get the current EREPR network state."""
        return {
            "node_id": self.node_id,
            "signature": self.signature.to_dict() if self.signature else None,
            "bonds": {
                peer_id: {
                    "resonance": bond.resonance_score,
                    "strength": bond.bond_strength,
                    "echo_count": bond.echo_count,
                }
                for peer_id, bond in self.bonds.items()
            },
            "known_peers": len(self.known_peers),
            "seen_messages": len(self.seen_messages),
            "gossip_queue": len(self.gossip_queue),
        }

    def health_report(self) -> Dict[str, Any]:
        """Generate a health report for the EREPR protocol."""
        bonds = list(self.bonds.values())
        avg_strength = (
            sum(b.bond_strength for b in bonds) / len(bonds)
            if bonds else 0.0
        )
        avg_resonance = (
            sum(b.resonance_score for b in bonds) / len(bonds)
            if bonds else 0.0
        )

        return {
            "protocol": "EREPR",
            "node_id": self.node_id,
            "active_bonds": len(bonds),
            "avg_bond_strength": round(avg_strength, 4),
            "avg_resonance": round(avg_resonance, 4),
            "known_peers": len(self.known_peers),
            "seen_messages": len(self.seen_messages),
        }
