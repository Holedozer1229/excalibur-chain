# SphinxOS Nexus

**The quantum blockchain operating system powering AetherionEXCAL.**

SphinxOS Nexus is the core orchestrator that ties together all subsystems of the AetherionEXCAL blockchain: EREPR P2P gossip, conscious consensus, governance, treasury, ZK-Sync bridging, and more.

## Architecture

```
┌─────────────────────────────────────────────────┐
│           SphinxOS Nexus Orchestrator            │
├─────────────────────────────────────────────────┤
│                                                  │
│  ┌──────────────┐  ┌──────────────────────────┐ │
│  │   EREPR      │  │  Conscious Consensus     │ │
│  │  Protocol    │  │                          │ │
│  └──────┬───────┘  └────────────┬─────────────┘ │
│         │                       │               │
│  ┌──────┴───────┐  ┌────────────┴─────────────┐ │
│  │ Knights of   │  │  Self-Organizing         │ │
│  │ Round Table  │  │  Treasury                │ │
│  └──────┬───────┘  └────────────┬─────────────┘ │
│         │                       │               │
│  ┌──────┴───────┐  ┌────────────┴─────────────┘ │
│  │  zkSync      │  │  Bonding Curve             │ │
│  │  Bridge      │  │                            │ │
│  └──────────────┘  └────────────────────────────┘ │
│                                                  │
│  ┌──────────────┐  ┌──────────────────────────┐ │
│  │   MuSig2     │  │  FROST DKG               │ │
│  │  (BIP-327)   │  │                          │ │
│  └──────────────┘  └──────────────────────────┘ │
│                                                  │
│  ┌──────────────┐  ┌──────────────────────────┐ │
│  │ AI Oracle    │  │  Knight NFTs             │ │
│  │ Knights      │  │  (13 total)              │ │
│  └──────────────┘  └──────────────────────────┘ │
│                                                  │
└─────────────────────────────────────────────────┘
```

## Subsystems

| Module | Description |
|--------|-------------|
| [`orchestrator.py`](nexus/orchestrator.py) | Main Nexus orchestrator — ties all subsystems together |
| [`erepr_protocol.py`](nexus/erepr_protocol.py) | Entanglement-Resonance Echo Peer Routing (Q-Day protocol) |
| [`conscious_consensus.py`](nexus/conscious_consensus.py) | Quantum-inspired consensus engine |
| [`knights_round_table.py`](nexus/knights_round_table.py) | Governance: Knights of the Round Table, 3-of-5 threshold |
| [`self_organizing_treasury.py`](nexus/self_organizing_treasury.py) | Autonomous treasury with bonding curve |
| [`zksync_bridge.py`](nexus/zksync_bridge.py) | Cross-chain bridge to zkSync Era |
| [`bonding_curve.py`](nexus/bonding_curve.py) | Custom sigmoid bonding curve for URUU token |
| [`musig2.py`](nexus/musig2.py) | MuSig2 (BIP-327) key aggregation and signing |
| [`frost.py`](nexus/frost.py) | FROST distributed key generation |
| [`ai_oracle_knight.py`](nexus/ai_oracle_knight.py) | AI oracle with 5 specialization types |
| [`knight_nft.py`](nexus/knight_nft.py) | 13 Knight NFTs with ZK rarity proofs |
| [`holographic_p2p.py`](nexus/holographic_p2p.py) | Holographic P2P layer for wallet gossip |
| [`quantum_spacetime.py`](nexus/quantum_spacetime.py) | Quantum state simulation on toroidal manifold |

## Core Concepts

### EREPR Protocol

Entanglement-Resonance Echo Peer Routing is a quantum-inspired P2P gossip protocol where nodes discover each other through resonance matching on a toroidal manifold. Nodes form entanglement bonds for authenticated gossip wave propagation.

### Knights of the Round Table

Governance is controlled by a sovereign council of Knights elected by 3-of-5 threshold voting. Each Knight holds a MuSig2 (BIP-327) key share; the aggregate key controls the Taproot treasury.

### AI Oracle Knights

Five specialization types provide risk-based proposal analysis:
- **Sentinel**: Security and threat detection
- **Treasurer**: Financial analysis and treasury management
- **Oracle**: Data verification and external feeds
- **Bridge**: Cross-chain interoperability
- **Curve**: Bonding curve and tokenomics

### Knight NFTs

13 unique NFTs (12 Mythical + 1 Legendary King) with ZK rarity proofs. Each NFT represents a seat at the Round Table.

## Running Tests

```bash
python -m unittest discover -s sphinx_os/tests
```

**Test coverage:** 494+ tests passing across all subsystems.

## Integration

SphinxOS Nexus is integrated into the AetherionEXCAL stack via:

- **`fork_node.py`**: RPC endpoints for governance, staking, treasury
- **`p2p_layer.py`**: EREPR protocol messages and resonance matching
- **`camelot_api.py`**: Game integration with Nexus subsystems

## License

MIT License — see [LICENSE](../LICENSE) for details.
