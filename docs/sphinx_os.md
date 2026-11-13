---
layout: default
title: SphinxOS Nexus
---

# SphinxOS Nexus — Grand Unified Quantum Blockchain Organism

The `sphinx_os/` package implements the Nexus Orchestrator, fusing five subsystems into one self-organizing organism.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   Nexus Orchestrator                        │
│                                                             │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │ Quantum-Spacetime│  │ Conscious         │                │
│  │ Fabric           │  │ Consensus Engine  │                │
│  └────────┬─────────┘  └────────┬─────────┘                │
│           │                     │                           │
│  ┌────────┴─────────┐  ┌────────┴─────────┐                │
│  │ Holographic P2P  │  │ Self-Organizing  │                │
│  │ Layer            │  │ Treasury         │                │
│  └──────────────────┘  └──────────────────┘                │
│                                                             │
│  Feedback Loops: Fabric → Consensus → P2P → Treasury → ... │
└─────────────────────────────────────────────────────────────┘
```

## Subsystems

### 1. Quantum-Spacetime Fabric

Quantum state simulator with density matrix tracking and spacetime curvature evolution.

**Key Features:**
- Quantum gate application (Hadamard, CNOT, etc.)
- Von Neumann entanglement entropy calculation
- Discrete wave equation for curvature evolution
- Wormhole detection based on curvature thresholds

**Usage:**
```python
from sphinx_os.nexus import QuantumSpacetimeFabric
import numpy as np

fabric = QuantumSpacetimeFabric()

# Apply a Hadamard gate
H = np.array([[1, 1], [1, -1]], dtype=np.complex128) / np.sqrt(2)
fabric.apply_quantum_gate(H, [0])

# Run unified step
metrics = fabric.unified_step()
print(f"Entanglement: {metrics['entanglement_entropy']:.4f}")
```

### 2. Conscious Consensus Engine

Block consensus driven by Integrated Information Theory (IIT v8) φ-scores.

**Key Features:**
- Validator registration with stake and NFT rarity
- Block proposals with φ-score calculation
- Supermajority voting and finalization
- φ breakdown: τ (temporal coherence), GWT, ICP, Fano efficiency, QG coupling

**Usage:**
```python
from sphinx_os.nexus import ConsciousConsensusEngine

consensus = ConsciousConsensusEngine()

# Register validators
for i in range(5):
    consensus.register_validator(f"validator_{i}", stake=10.0, nft_rarity=0.8)

# Propose a block
transactions = [
    {"from": "alice", "to": "bob", "amount": 100, "type": "transfer"},
]
candidate = consensus.propose_block("validator_0", transactions)
```

### 3. Holographic P2P Layer

Peer-to-peer networking with entanglement-based routing and gossip protocol.

**Key Features:**
- **Gossip protocol**: Epidemic message propagation with O(log N) dissemination
- **Message encryption**: XOR-based symmetric cipher with base64 encoding
- **Priority queue with TTL**: 4-level priority (CRITICAL/HIGH/NORMAL/LOW)
- **Peer discovery**: Introduction-based bootstrapping
- **Bandwidth & latency simulation**: Per-peer tracking
- **Dijkstra maximum-entanglement routing**: Optimal path finding
- **Topology export**: JSON and GraphML formats

**Usage:**
```python
from sphinx_os.nexus import HolographicP2PLayer

p2p = HolographicP2PLayer()

# Add peers
for i in range(5):
    p2p.add_peer(f"peer_{i}", f"192.168.1.{i+1}", 8080 + i)
    p2p.connect_peer(f"peer_{i}")

# Send encrypted message
msg_id = p2p.send_message("peer_0", "block_proposal", {"height": 1})

# Export topology
p2p.export_topology("network.json", "json")
```

### 4. Self-Organizing Treasury

Autonomous treasury with NFT-based governance and auto-deployment.

**Key Features:**
- NFT holder registration with rarity weights
- Type-aware fee splitting (treasury/operator/rewards)
- Compound yield computation
- Auto-deployment of bridges and oracles

**Usage:**
```python
from sphinx_os.nexus import SelfOrganizingTreasury

treasury = SelfOrganizingTreasury()

# Register NFT holders
treasury.register_nft_holder("alice", 0.9)
treasury.register_nft_holder("bob", 0.7)

# Collect fees
split = treasury.collect_fee(100.0, "nft_mint")

# Compute yield
yield_amount = treasury.compute_yield(dt_years=1/365)
```

### 5. Nexus Orchestrator

Unified orchestrator that integrates all subsystems with feedback loops.

**Key Features:**
- Unified stepping across all subsystems
- Cross-layer entropy calculation
- Feedback loops between all layers
- Phase transitions: Vacuum → Inflation → Condensation → Crystallization → Consciousness
- Health reporting with alerts

**Usage:**
```python
from sphinx_os.nexus import NexusOrchestrator

nexus = NexusOrchestrator()

# Register components
nexus.register_validator("validator_0", stake=10.0, nft_rarity=0.8)
nexus.add_peer("peer_0", "192.168.1.1", 8080)
nexus.register_nft_holder("alice", 0.9)

# Run unified steps
for i in range(10):
    state = nexus.step()

# Get health report
health = nexus.get_health_report()
print(f"Health: {health['overall_health']:.2%}")
```

## Phase Transitions

The Nexus evolves through five phases:

1. **Vacuum** — Initial state, no activity
2. **Inflation** — Quantum fluctuations begin
3. **Condensation** — Spacetime structure forms
4. **Crystallization** — Consensus patterns emerge
5. **Consciousness** — Full organism awareness

## Running the Demo

```bash
python demo_nexus.py
```

This will demonstrate all five subsystems individually, then run the full orchestrator with phase transitions.
