"""sphinx_os.nexus.quantum — Quantum protocol suite for Aetherion-Excalibur.

Provides simulated quantum protocols for P2P network security:

- **E91Handshake**: Entanglement-based quantum key distribution for peer
  identity verification and session key establishment between P2P nodes.
  Uses Bell pairs and CHSH inequality testing to detect eavesdropping.

- **GHZBeacon**: Greenberger-Horne-Zeilinger state-based random beacon
  for network-wide shared randomness. Used for consensus tie-breaking,
  leader election, and state synchronization.

These protocols are simulated classically using numpy for the quantum
state vector. In a production deployment with actual quantum hardware,
the OpenQASM 3 circuits (e91_handshake.qasm, ghz_beacon.qasm) would be
compiled and executed on a quantum processor.

Usage:
    from sphinx_os.nexus.quantum import E91Handshake, GHZBeacon

    # Establish secure channel between two peers
    handshake = E91Handshake(num_pairs=64)
    key, chsh_value = handshake.run()

    # Generate network-wide random beacon
    beacon = GHZBeacon(participants=8, rounds=16)
    random_bits = beacon.generate_beacon()
"""

from .e91 import E91Handshake
from .ghz import GHZBeacon

__all__ = ["E91Handshake", "GHZBeacon"]
