"""
Demo: SphinxOS Nexus - The Grand Unified Quantum Blockchain Organism
===================================================================

This demo showcases the Nexus Orchestrator, the crowning achievement of SphinxOS.
It fuses all subsystems into one living, self-organizing organism.

Run:
    python demo_nexus.py
"""

import sys
import os
import numpy as np

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sphinx_os.nexus import (
    NexusOrchestrator,
    NexusConfig,
    QuantumSpacetimeFabric,
    ConsciousConsensusEngine,
    HolographicP2PLayer,
    SelfOrganizingTreasury,
    NexusPhase,
)


def print_header(title: str):
    """Print a formatted header."""
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}\n")


def demo_individual_components():
    """Demo each component individually."""
    print_header("1. Individual Component Demos")
    
    # --- Quantum-Spacetime Fabric ---
    print("▶ Quantum-Spacetime Fabric")
    fabric = QuantumSpacetimeFabric()
    
    # Apply a Hadamard gate
    H = np.array([[1, 1], [1, -1]], dtype=np.complex128) / np.sqrt(2)
    fabric.apply_quantum_gate(H, [0])
    
    metrics = fabric.unified_step()
    print(f"   Entanglement Entropy: {metrics['entanglement_entropy']:.4f}")
    print(f"   Curvature RMS:        {metrics['curvature_rms']:.2e}")
    print(f"   Quantum Purity:       {metrics['quantum_purity']:.4f}")
    print(f"   Wormhole Nodes:       {len(fabric.wormhole_nodes)}")
    
    # --- Conscious Consensus Engine ---
    print("\n▶ Conscious Consensus Engine")
    consensus = ConsciousConsensusEngine()
    
    # Register validators
    for i in range(5):
        consensus.register_validator(f"validator_{i}", stake=10.0, nft_rarity=0.8)
    
    # Propose a block
    transactions = [
        {"from": "alice", "to": "bob", "amount": 100, "type": "transfer"},
        {"from": "bob", "to": "charlie", "amount": 50, "type": "transfer"},
        {"from": "charlie", "to": "alice", "amount": 75, "type": "nft_mint"},
    ]
    
    candidate = consensus.propose_block("validator_0", transactions)
    if candidate:
        print(f"   Block proposed: height={candidate.height}")
        print(f"   Φ score:        {candidate.phi_score:.4f}")
        print(f"   Conscious:      {candidate.is_conscious}")
        
        # Vote on the block
        for i in range(1, 5):
            consensus.vote(f"validator_{i}", candidate.block_hash, True)
        
        print(f"   Finalized:      {candidate.is_finalized}")
        print(f"   Φ breakdown:    τ={consensus.phi_tau:.3f}, "
              f"GWT={consensus.phi_gwt:.3f}, ICP={consensus.phi_icp:.3f}, "
              f"Fano={consensus.phi_fano:.3f}, QG={consensus.phi_qg:.3f}")
    
    # --- Holographic P2P Layer ---
    print("\n▶ Holographic P2P Layer")
    p2p = HolographicP2PLayer()
    
    # Add peers
    for i in range(5):
        p2p.add_peer(f"peer_{i}", f"192.168.1.{i+1}", 8080 + i)
        p2p.connect_peer(f"peer_{i}")
    
    # Send a message
    msg = p2p.send_message("peer_0", "block_proposal", {
        "height": 1,
        "hash": "abc123",
    })
    
    state = p2p.get_network_state()
    print(f"   Active Peers:       {state['active_peers']}")
    print(f"   Network Coherence:  {state['network_coherence']:.4f}")
    print(f"   Messages Sent:      {state['messages_sent']}")
    
    # --- Self-Organizing Treasury ---
    print("\n▶ Self-Organizing Treasury")
    treasury = SelfOrganizingTreasury()
    
    # Register NFT holders
    treasury.register_nft_holder("alice", 0.9)
    treasury.register_nft_holder("bob", 0.7)
    
    # Collect fees
    split = treasury.collect_fee(100.0, "nft_mint")
    print(f"   Fee split:          treasury={split['treasury']:.2f}, "
          f"operator={split['operator']:.2f}, rewards={split['rewards']:.2f}")
    
    # Compute yield
    yield_amount = treasury.compute_yield(dt_years=1/365)  # 1 day
    print(f"   Daily yield:        {yield_amount:.4f} SKYNT")
    
    # Check deployments
    deployed = treasury.check_deployments()
    print(f"   Deployed chains:    {deployed}")
    
    t_state = treasury.get_treasury_state()
    print(f"   Treasury balance:   {t_state['balance']:.2f} SKYNT")


def demo_nexus_orchestrator():
    """Demo the full Nexus Orchestrator."""
    print_header("2. Full Nexus Orchestrator Demo")
    
    # Create the Nexus
    nexus = NexusOrchestrator()
    
    print("▶ Initializing Nexus organism...")
    print(f"   Initial phase:      {nexus.state.phase.value}")
    
    # Register validators
    print("\n▶ Registering validators...")
    for i in range(5):
        nexus.register_validator(f"validator_{i}", stake=10.0, nft_rarity=0.8)
    print(f"   Validators:         {len(nexus.consensus.validators)}")
    
    # Add peers
    print("\n▶ Adding P2P peers...")
    for i in range(5):
        nexus.add_peer(f"peer_{i}", f"192.168.1.{i+1}", 8080 + i)
        nexus.p2p.connect_peer(f"peer_{i}")
    print(f"   Active peers:       {len(nexus.p2p.get_active_peers())}")
    
    # Register NFT holders
    print("\n▶ Registering NFT holders...")
    nexus.register_nft_holder("alice", 0.9)
    nexus.register_nft_holder("bob", 0.7)
    nexus.register_nft_holder("charlie", 0.5)
    print(f"   NFT holders:        {len(nexus.treasury.nft_holders)}")
    
    # Deposit to treasury
    print("\n▶ Depositing to treasury...")
    nexus.deposit_to_treasury(500.0, "Initial funding")
    print(f"   Treasury balance:   {nexus.treasury.balance:.2f} SKYNT")
    
    # Run unified steps
    print("\n▶ Running unified Nexus steps...")
    for step in range(10):
        state = nexus.step()
    
    print(f"   Steps completed:    10")
    print(f"   Current phase:      {nexus.state.phase.value}")
    print(f"   Nexus coherence:    {nexus.nexus_coherence:.4f}")
    print(f"   Cross-layer entropy:{nexus.cross_layer_entropy:.4f}")
    print(f"   Feedback loops:     {nexus.feedback_loop_count}")
    
    # Propose and consensus a block
    print("\n▶ Proposing block with conscious consensus...")
    transactions = [
        {"from": "alice", "to": "bob", "amount": 100, "type": "transfer"},
        {"from": "bob", "to": "charlie", "amount": 50, "type": "transfer"},
        {"from": "charlie", "to": "alice", "amount": 75, "type": "nft_mint"},
        {"from": "alice", "to": "dave", "amount": 200, "type": "bridge"},
    ]
    
    block_hash = nexus.propose_and_consenus_block("validator_0", transactions)
    print(f"   Block hash:         {block_hash[:16] if block_hash else 'Not finalized'}...")
    print(f"   Chain height:       {nexus.consensus.current_height}")
    print(f"   Blocks finalized:   {nexus.consensus.stats['blocks_finalized']}")
    
    # Send network message
    print("\n▶ Sending holographic P2P message...")
    msg_id = nexus.send_network_message("peer_0", "block_announcement", {
        "height": nexus.consensus.current_height,
        "hash": block_hash or "pending",
    })
    print(f"   Message ID:         {msg_id[:16] if msg_id else 'None'}...")
    
    # Apply quantum gate
    print("\n▶ Applying quantum gate to fabric...")
    H = np.array([[1, 1], [1, -1]], dtype=np.complex128) / np.sqrt(2)
    nexus.apply_quantum_gate(H, [0])
    
    # Get health report
    print("\n▶ Health Report:")
    health = nexus.get_health_report()
    print(f"   Overall health:     {health['overall_health']:.2%}")
    print(f"   Fabric health:      {health['subsystem_health']['fabric']:.2%}")
    print(f"   Consensus health:   {health['subsystem_health']['consensus']:.2%}")
    print(f"   P2P health:         {health['subsystem_health']['p2p']:.2%}")
    print(f"   Treasury health:    {health['subsystem_health']['treasury']:.2%}")
    
    if health['alerts']:
        print(f"   Alerts:")
        for alert in health['alerts']:
            print(f"     ⚠ {alert}")
    
    # Full state
    print("\n▶ Full Nexus State:")
    state = nexus.get_nexus_state()
    print(f"   Phase:              {state['phase']}")
    print(f"   Uptime:             {state['uptime']:.2f}s")
    print(f"   Nexus coherence:    {state['nexus_coherence']:.4f}")
    print(f"   Quantum fidelity:   {state['metrics']['quantum_fidelity']:.4f}")
    print(f"   Entanglement:       {state['metrics']['entanglement_entropy']:.4f}")
    print(f"   Φ score:            {state['metrics']['phi_score']:.4f}")
    print(f"   Chain height:       {state['metrics']['chain_height']}")
    print(f"   Active peers:       {state['metrics']['active_peers']}")
    print(f"   Treasury balance:   {state['metrics']['treasury_balance']:.2f}")


def demo_phase_transitions():
    """Demo the phase transition system."""
    print_header("3. Phase Transitions")
    
    nexus = NexusOrchestrator()
    
    print("Phase progression:")
    phases = [
        NexusPhase.VACUUM,
        NexusPhase.INFLATION,
        NexusPhase.CONDENSATION,
        NexusPhase.CRYSTALLIZATION,
        NexusPhase.CONSCIOUSNESS,
    ]
    
    for phase in phases:
        status = "✓" if nexus.state.phase == phase else " "
        print(f"   [{status}] {phase.value}")
    
    # Run steps to advance through phases
    print("\nRunning steps to advance phases...")
    for i in range(20):
        nexus.step()
        print(f"   Step {i+1:2d}: phase = {nexus.state.phase.value}")


def main():
    """Run all demos."""
    print("\n" + "=" * 70)
    print("  SphinxOS Nexus: Grand Unified Quantum Blockchain Organism")
    print("  Demo — Fusing Everything into One Cohesive Unit")
    print("=" * 70)
    
    demo_individual_components()
    demo_nexus_orchestrator()
    demo_phase_transitions()
    
    print_header("Demo Complete!")
    print("The Nexus is a living organism where:")
    print("  • Quantum gates perturb spacetime curvature")
    print("  • Spacetime evolution is driven by quantum entanglement")
    print("  • Consensus requires conscious agreement (IIT v8)")
    print("  • P2P routing follows entanglement paths")
    print("  • Treasury self-funds and auto-deploys bridges")
    print("  • All layers feed back into each other continuously")
    print()


if __name__ == "__main__":
    main()
