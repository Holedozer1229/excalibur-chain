"""Nexus Orchestrator: The Grand Unified Quantum Blockchain Organism.

Integrates all subsystems into one living, self-organizing organism with:
- Quantum-spacetime fabric for entanglement tracking
- Conscious consensus for block finalization
- Holographic P2P for entanglement-based routing
- Self-organizing treasury for autonomous funding
- Phase transitions from vacuum to consciousness
- Cross-layer feedback loops
"""

import time
import math
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple

import numpy as np

from .quantum_spacetime import QuantumSpacetimeFabric
from .conscious_consensus import ConsciousConsensusEngine, BlockCandidate
from .holographic_p2p import HolographicP2PLayer
from .self_organizing_treasury import SelfOrganizingTreasury
from .bonding_curve import CustomBondingCurve, BondingCurveState
from .zksync_bridge import ZkSyncBridge, BridgeState, BridgeStatus
from .knights_round_table import KnightsRoundTable, ProposalType, VoteStatus
from .erepr_protocol import EREPRProtocol, EchoMessage, GossipWave


class NexusPhase(Enum):
    """Phases of the Nexus organism evolution."""
    VACUUM = "Vacuum State"
    INFLATION = "Inflation Epoch"
    CONDENSATION = "Condensation Phase"
    CRYSTALLIZATION = "Crystallization Epoch"
    CONSCIOUSNESS = "Consciousness Emergence"


@dataclass
class NexusConfig:
    """Configuration for the Nexus Orchestrator."""
    num_qubits: int = 4
    grid_size: int = 16
    wormhole_threshold: float = 0.3
    phase_transition_steps: int = 5
    feedback_loop_interval: int = 3
    annual_yield_rate: float = 0.05
    deployment_threshold: float = 1000.0
    # Bonding curve parameters
    uruu_min_price: float = 0.01
    uruu_max_price: float = 10.0
    uruu_steepness: float = 0.1
    uruu_inflection_supply: float = 500000.0
    uruu_initial_reserve: float = 1000.0
    uruu_max_supply: float = 1000000.0
    # Bridge parameters
    bridge_fee_rate: float = 0.001
    required_confirmations: int = 12
    # Governance parameters
    governance_threshold_m: int = 3
    governance_threshold_n: int = 5
    minimum_uruu_threshold: float = 100.0
    minimum_phi_score: float = 0.5
    minimum_stake: float = 1000.0
    # EREPR P2P parameters
    node_id: str = "nexus-node"
    node_secret: bytes = b""


@dataclass
class NexusState:
    """Current state of the Nexus organism."""
    phase: NexusPhase = NexusPhase.VACUUM
    step_count: int = 0
    coherence: float = 0.0
    entropy: float = 0.0
    phi_score: float = 0.0
    chain_height: int = 0
    active_peers: int = 0
    treasury_balance: float = 0.0


class NexusOrchestrator:
    """The Nexus Orchestrator: a living organism where quantum gates perturb spacetime,
    consensus requires conscious agreement, P2P routing follows entanglement paths,
    and the treasury self-funds and auto-deploys bridges.
    
    All layers feed back into each other continuously through cross-layer entropy
    and nexus coherence metrics.
    """
    
    def __init__(self, config: Optional[NexusConfig] = None):
        self.config = config or NexusConfig()
        self.start_time = time.time()
        
        # Subsystems
        self.fabric = QuantumSpacetimeFabric(
            num_qubits=self.config.num_qubits,
            wormhole_threshold=self.config.wormhole_threshold,
        )
        self.consensus = ConsciousConsensusEngine()
        self.p2p = HolographicP2PLayer()
        self.treasury = SelfOrganizingTreasury(
            annual_yield_rate=self.config.annual_yield_rate,
            deployment_threshold=self.config.deployment_threshold,
        )
        
        # Bonding curve for URUU token
        self.bonding_curve = CustomBondingCurve(
            min_price=self.config.uruu_min_price,
            max_price=self.config.uruu_max_price,
            steepness=self.config.uruu_steepness,
            inflection_supply=self.config.uruu_inflection_supply,
            initial_reserve=self.config.uruu_initial_reserve,
            max_supply=self.config.uruu_max_supply,
        )
        
        # zkSync Era bridge
        self.bridge = ZkSyncBridge(
            bridge_fee_rate=self.config.bridge_fee_rate,
            required_confirmations=self.config.required_confirmations,
        )
        self.bridge.on_bridge_complete = self._on_bridge_complete
        
        # Knights of the Round Table — sovereign governance
        self.governance = KnightsRoundTable(
            threshold_m=self.config.governance_threshold_m,
            threshold_n=self.config.governance_threshold_n,
            minimum_uruu_threshold=self.config.minimum_uruu_threshold,
            minimum_phi_score=self.config.minimum_phi_score,
            minimum_stake=self.config.minimum_stake,
        )
        
        # EREPR — Entanglement-Resonance Echo Peer Routing (P2P gossip)
        import secrets as _secrets
        erepr_secret = self.config.node_secret or _secrets.token_bytes(32)
        self.erepr = EREPRProtocol(
            node_id=self.config.node_id,
            secret=erepr_secret,
        )
        self.erepr.initialize()
        
        # Nexus-level state
        self.state = NexusState()
        self.nexus_coherence: float = 1.0
        self.cross_layer_entropy: float = 0.0
        self.feedback_loop_count: int = 0
        
        # Phase transition tracking
        self._steps_since_last_transition: int = 0
        
    # --- Validator Management ---
    
    def register_validator(self, name: str, stake: float, nft_rarity: float):
        """Register a validator in the consensus engine.
        
        Args:
            name: Validator identifier.
            stake: Amount staked.
            nft_rarity: NFT rarity score (0-1).
        """
        self.consensus.register_validator(name, stake, nft_rarity)
    
    # --- P2P Management ---
    
    def add_peer(self, name: str, host: str, port: int):
        """Add a peer to the P2P network.
        
        Args:
            name: Peer identifier.
            host: Host address.
            port: Port number.
        """
        self.p2p.add_peer(name, host, port)
    
    # --- NFT Holder Management ---
    
    def register_nft_holder(self, name: str, rarity: float):
        """Register an NFT holder in the treasury.
        
        Args:
            name: Holder identifier.
            rarity: NFT rarity score (0-1).
        """
        self.treasury.register_nft_holder(name, rarity)
    
    # --- Treasury Operations ---
    
    def deposit_to_treasury(self, amount: float, description: str = ""):
        """Deposit funds into the treasury.
        
        Args:
            amount: Amount to deposit.
            description: Optional description.
        """
        self.treasury.deposit(amount, description)
    
    # --- Bonding Curve Operations ---
    
    def buy_uruu(self, amount_excal: float, trader_address: str):
        """Buy URUU tokens with EXCAL using the bonding curve.
        
        Args:
            amount_excal: Amount of EXCAL to spend.
            trader_address: Address of the trader.
            
        Returns:
            Trade record.
        """
        trade = self.bonding_curve.buy(amount_excal, trader_address)
        # Collect trading fee to treasury
        fee = amount_excal * self.bonding_curve.fee_rate
        self.treasury.collect_fee(fee, "bonding_curve")
        return trade
    
    def sell_uruu(self, amount_uruu: float, trader_address: str):
        """Sell URUU tokens for EXCAL using the bonding curve.
        
        Args:
            amount_uruu: Amount of URUU to sell.
            trader_address: Address of the trader.
            
        Returns:
            Trade record.
        """
        trade = self.bonding_curve.sell(amount_uruu, trader_address)
        # Collect trading fee to treasury
        fee_on_output = trade.amount_out * self.bonding_curve.fee_rate
        self.treasury.collect_fee(fee_on_output, "bonding_curve")
        return trade
    
    def get_uruu_price(self) -> float:
        """Get the current URUU price in EXCAL.
        
        Returns:
            Current price.
        """
        return self.bonding_curve.calculate_price()
    
    def get_uruu_price_impact(self, amount: float, is_buy: bool = True) -> dict:
        """Calculate the price impact of a potential URUU trade.
        
        Args:
            amount: Trade amount.
            is_buy: True for buy, False for sell.
            
        Returns:
            Dictionary with price impact metrics.
        """
        return self.bonding_curve.get_price_impact(amount, is_buy)
    
    def get_bonding_curve_state(self) -> BondingCurveState:
        """Get the current state of the bonding curve.
        
        Returns:
            BondingCurveState.
        """
        return self.bonding_curve.get_state()
    
    # --- zkSync Bridge Operations ---
    
    def bridge_to_zksync(
        self,
        token_symbol: str,
        amount: float,
        sender_address: str,
        receiver_address: str,
    ):
        """Bridge tokens from EXCAL to zkSync Era.
        
        Args:
            token_symbol: Token to bridge (EXCAL or URUU).
            amount: Amount to bridge.
            sender_address: Sender address on EXCAL.
            receiver_address: Receiver address on zkSync.
            
        Returns:
            Bridge transaction record.
        """
        tx = self.bridge.initiate_deposit(token_symbol, amount, sender_address, receiver_address)
        # Collect bridge fee to treasury
        fee = amount * self.bridge.bridge_fee_rate
        self.treasury.collect_fee(fee, "bridge")
        return tx
    
    def bridge_to_excal(
        self,
        token_symbol: str,
        amount: float,
        sender_address: str,
        receiver_address: str,
    ):
        """Bridge tokens from zkSync Era to EXCAL.
        
        Args:
            token_symbol: Token to bridge (wEXCAL or URUU).
            amount: Amount to bridge.
            sender_address: Sender address on zkSync.
            receiver_address: Receiver address on EXCAL.
            
        Returns:
            Bridge transaction record.
        """
        tx = self.bridge.initiate_withdrawal(token_symbol, amount, sender_address, receiver_address)
        # Collect bridge fee to treasury
        fee = amount * self.bridge.bridge_fee_rate
        self.treasury.collect_fee(fee, "bridge")
        return tx
    
    def confirm_bridge_transaction(self, tx_id: str, confirmations: int, tx_hash: str = None):
        """Add confirmations to a bridge transaction.
        
        Args:
            tx_id: Transaction ID.
            confirmations: Number of new confirmations.
            tx_hash: Optional transaction hash.
        """
        self.bridge.confirm_transaction(tx_id, confirmations, tx_hash)
    
    def get_bridge_state(self) -> BridgeState:
        """Get the current state of the zkSync bridge.
        
        Returns:
            BridgeState.
        """
        return self.bridge.get_state()
    
    def _on_bridge_complete(self, tx):
        """Callback when a bridge transaction completes.
        
        Args:
            tx: Completed bridge transaction.
        """
        # Broadcast completion to P2P network
        self.p2p.send_message(
            "bridge_oracle",
            "bridge_complete",
            {
                "tx_id": tx.tx_id,
                "amount": tx.amount,
                "token": tx.token_symbol,
                "direction": tx.direction.value,
            },
        )
    
    # --- Governance Operations (Knights of the Round Table) ---
    
    def add_founder_knight(
        self,
        name: str,
        public_key: bytes,
        uruu_balance: float,
        phi_score: float,
        excal_stake: float,
    ):
        """Add a founder Knight to the Round Table.
        
        Args:
            name: Knight identifier.
            public_key: 32-byte x-only public key.
            uruu_balance: URUU tokens held.
            phi_score: Consciousness score (0-1).
            excal_stake: EXCAL staked.
        """
        self.governance.add_founder_knight(name, public_key, uruu_balance, phi_score, excal_stake)
    
    def nominate_knight(
        self,
        candidate_name: str,
        candidate_public_key: bytes,
        nominator: str,
        uruu_balance: float,
        phi_score: float,
        excal_stake: float,
    ):
        """Nominate a candidate for Knight induction.
        
        Args:
            candidate_name: Name of the candidate.
            candidate_public_key: Candidate's public key.
            nominator: Name of the nominating Knight.
            uruu_balance: Candidate's URUU balance.
            phi_score: Candidate's phi score.
            excal_stake: Candidate's EXCAL stake.
            
        Returns:
            KnightNomination if qualified, None otherwise.
        """
        return self.governance.nominate_knight(
            candidate_name, candidate_public_key, nominator,
            uruu_balance, phi_score, excal_stake,
        )
    
    def vote_on_knight_nomination(
        self,
        nomination_id: str,
        voter_name: str,
        vote_yes: bool,
        voter_secret: bytes,
    ):
        """Vote on a Knight nomination.
        
        Args:
            nomination_id: ID of the nomination.
            voter_name: Name of the voting Knight.
            vote_yes: True to approve.
            voter_secret: Voter's secret key.
        """
        self.governance.vote_on_nomination(nomination_id, voter_name, vote_yes, voter_secret)
    
    def create_governance_proposal(
        self,
        proposal_type: ProposalType,
        proposer: str,
        description: str,
        parameters: Dict[str, Any],
    ):
        """Create a governance proposal.
        
        Args:
            proposal_type: Type of proposal.
            proposer: Name of the proposing Knight.
            description: Description of the proposal.
            parameters: Proposal parameters.
        """
        self.governance.create_proposal(proposal_type, proposer, description, parameters)
    
    def vote_on_governance_proposal(
        self,
        proposal_id: str,
        voter_name: str,
        vote_yes: bool,
        voter_secret: bytes,
    ):
        """Vote on a governance proposal.
        
        Args:
            proposal_id: ID of the proposal.
            voter_name: Name of the voting Knight.
            vote_yes: True to approve.
            voter_secret: Voter's secret key.
        """
        self.governance.vote_on_proposal(proposal_id, voter_name, vote_yes, voter_secret)
    
    def deposit_to_governance_treasury(
        self,
        amount: float,
        token: str = "EXCAL",
        sender: str = "",
        description: str = "",
    ):
        """Deposit to the Round Table Taproot treasury.
        
        Args:
            amount: Amount to deposit.
            token: Token symbol (EXCAL or URUU).
            sender: Sender identifier.
            description: Description.
        """
        self.governance.deposit_to_treasury(amount, token, sender, description)
    
    def get_governance_state(self):
        """Get the current state of the Round Table governance."""
        return self.governance.get_round_table_state()
    
    def get_governance_health(self) -> Dict[str, Any]:
        """Get health report for the Round Table."""
        return self.governance.get_health_report()
    
    def get_taproot_treasury_address(self) -> str:
        """Get the Taproot treasury address derived from the 13-word prophecy.
        
        Returns:
            The bc1p... Taproot address.
        """
        return self.governance._taproot_address
    
    # --- EREPR P2Gossip Operations ---
    
    def broadcast_gossip(
        self,
        payload: Dict[str, Any],
    ) -> GossipWave:
        """Broadcast a gossip message through the EREPR network.
        
        Args:
            payload: Message payload.
            
        Returns:
            The created GossipWave.
        """
        wave = self.erepr.create_gossip_wave(payload)
        self.erepr.gossip_queue.append(wave)
        return wave
    
    def receive_echo_from_peer(self, echo: EchoMessage) -> Optional[EchoMessage]:
        """Receive an echo from a peer and respond if resonance is sufficient.
        
        Args:
            echo: Incoming echo message.
            
        Returns:
            Echo confirmation if resonance is sufficient, None otherwise.
        """
        return self.erepr.create_echo_confirmation(echo)
    
    def receive_gossip_wave(self, wave: GossipWave) -> Optional[List[Tuple[str, GossipWave]]]:
        """Receive and forward a gossip wave.
        
        Args:
            wave: Incoming gossip wave.
            
        Returns:
            List of (peer_id, wave) pairs to forward, or None if dropped.
        """
        return self.erepr.receive_wave(wave)
    
    def get_erepr_network_state(self) -> Dict[str, Any]:
        """Get the current EREPR network state.
        
        Returns:
            Dictionary with EREPR network metrics.
        """
        return self.erepr.get_network_state()
    
    def get_erepr_health(self) -> Dict[str, Any]:
        """Get health report for EREPR protocol.
        
        Returns:
            Dictionary with EREPR health metrics.
        """
        return self.erepr.health_report()
    
    # --- Quantum Operations ---
    
    def apply_quantum_gate(self, gate: np.ndarray, qubits: List[int]):
        """Apply a quantum gate to the spacetime fabric.
        
        Args:
            gate: Unitary matrix of the gate.
            qubits: Qubit indices to apply the gate to.
        """
        self.fabric.apply_quantum_gate(gate, qubits)
    
    # --- Consensus Operations ---
    
    def propose_and_consenus_block(
        self,
        proposer: str,
        transactions: List[Dict[str, Any]],
    ) -> Optional[str]:
        """Propose a block and attempt to reach conscious consensus.
        
        Args:
            proposer: Validator proposing the block.
            transactions: List of transactions.
            
        Returns:
            Block hash if finalized, None otherwise.
        """
        candidate = self.consensus.propose_block(proposer, transactions)
        if not candidate:
            return None
        
        # Broadcast to P2P network
        self.p2p.send_message(
            proposer,
            "block_proposal",
            {
                "height": candidate.height,
                "hash": candidate.block_hash,
                "phi_score": candidate.phi_score,
            },
        )
        
        # Auto-vote from other validators
        for validator_name in self.consensus.validators:
            if validator_name != proposer:
                # Vote based on φ score
                should_vote = candidate.phi_score > 0.3
                self.consensus.vote(validator_name, candidate.block_hash, should_vote)
        
        # Collect transaction fees
        for tx in transactions:
            fee = tx.get("amount", 0) * 0.001  # 0.1% fee
            tx_type = tx.get("type", "transfer")
            self.treasury.collect_fee(fee, tx_type)
        
        if candidate.is_finalized:
            return candidate.block_hash
        return None
    
    # --- P2P Operations ---
    
    def send_network_message(
        self,
        source: str,
        msg_type: str,
        payload: Dict[str, Any],
        destination: Optional[str] = None,
    ) -> Optional[str]:
        """Send a message through the holographic P2P network.
        
        Args:
            source: Source peer.
            msg_type: Message type.
            payload: Message payload.
            destination: Optional destination.
            
        Returns:
            Message ID if sent.
        """
        return self.p2p.send_message(source, msg_type, payload, destination)
    
    # --- Unified Step ---
    
    def step(self) -> Dict[str, Any]:
        """Perform one unified Nexus step.
        
        This is the heart of the organism: all subsystems evolve together,
        cross-layer feedback is applied, and phase transitions are checked.
        
        Returns:
            Dictionary with the current Nexus state.
        """
        self.state.step_count += 1
        self._steps_since_last_transition += 1
        
        # 1. Evolve each subsystem
        fabric_metrics = self.fabric.unified_step()
        self.p2p.step()
        self.treasury.step()
        self.erepr.decay_bonds()
        self.erepr.cleanup_seen_messages()
        
        # 2. Apply Nexus influence to bonding curve
        entanglement = self.fabric.compute_entanglement_entropy()
        phi_score = self.consensus.phi_tau
        self.bonding_curve.apply_nexus_influence(entanglement, phi_score)
        
        # 3. Compute cross-layer entropy
        self._compute_cross_layer_entropy(fabric_metrics)
        
        # 4. Apply feedback loops
        if self.state.step_count % self.config.feedback_loop_interval == 0:
            self._apply_feedback_loops()
        
        # 5. Update nexus coherence
        self._update_nexus_coherence()
        
        # 6. Check for phase transitions
        self._check_phase_transition()
        
        # 7. Update state
        self._update_state()
        
        return self.get_nexus_state()
    
    def _compute_cross_layer_entropy(self, fabric_metrics: Dict[str, Any]):
        """Compute cross-layer entropy between subsystems.
        
        The cross-layer entropy measures how much information is shared
        between the quantum fabric, consensus, P2P, and treasury layers.
        """
        # Entropy from fabric
        fabric_entropy = fabric_metrics.get("entanglement_entropy", 0.0)
        
        # Entropy from consensus (based on φ score distribution)
        consensus_entropy = 1.0 - self.consensus.phi_tau if self.consensus.phi_tau > 0 else 0.0
        
        # Entropy from P2P (based on network coherence)
        p2p_entropy = 1.0 - self.p2p.network_coherence
        
        # Entropy from treasury (based on balance volatility)
        treasury_entropy = 0.0
        if self.treasury.balance > 0:
            treasury_entropy = min(1.0, math.log1p(self.treasury.balance) / 10.0)
        
        # Entropy from bonding curve (based on trading volume)
        curve_entropy = 0.0
        if self.bonding_curve.total_volume > 0:
            curve_entropy = min(1.0, math.log1p(self.bonding_curve.total_volume) / 20.0)
        
        # Entropy from bridge (based on pending transactions)
        bridge_entropy = 0.0
        pending = len(self.bridge.get_pending_transactions())
        if pending > 0:
            bridge_entropy = min(1.0, pending / 10.0)
        
        # Entropy from EREPR (based on bond strength)
        erepr_entropy = 0.0
        if self.erepr.bonds:
            avg_strength = sum(b.bond_strength for b in self.erepr.bonds.values()) / len(self.erepr.bonds)
            erepr_entropy = 1.0 - avg_strength
        
        # Cross-layer entropy: weighted combination (adjusted weights for EREPR)
        self.cross_layer_entropy = (
            0.20 * fabric_entropy
            + 0.18 * consensus_entropy
            + 0.12 * p2p_entropy
            + 0.12 * treasury_entropy
            + 0.12 * curve_entropy
            + 0.10 * bridge_entropy
            + 0.16 * erepr_entropy
        )
    
    def _apply_feedback_loops(self):
        """Apply cross-layer feedback loops.
        
        Feedback loops:
        - Fabric → Consensus: entanglement entropy influences φ score
        - Consensus → P2P: finalized blocks boost network coherence
        - P2P → Treasury: message volume influences fee collection
        - Treasury → Fabric: treasury balance influences curvature
        """
        self.feedback_loop_count += 1
        
        # Fabric → Consensus: boost φ components based on entanglement
        entanglement = self.fabric.compute_entanglement_entropy()
        if entanglement > 0.5:
            self.consensus.phi_qg = min(1.0, self.consensus.phi_qg + 0.05)
        
        # Consensus → P2P: finalized blocks boost coherence
        if self.consensus.stats["blocks_finalized"] > 0:
            self.p2p.network_coherence = min(
                1.0,
                self.p2p.network_coherence + 0.02 * self.consensus.stats["blocks_finalized"],
            )
        
        # P2P → Treasury: message volume as fee proxy
        if self.p2p.messages_sent > 0:
            msg_fee = self.p2p.messages_sent * 0.01
            self.treasury.collect_fee(msg_fee, "p2p_activity")
        
        # Treasury → Fabric: balance influences curvature
        if self.treasury.balance > 0:
            curvature_boost = min(0.1, self.treasury.balance / 10000.0)
            center = self.fabric.grid_size // 2
            self.fabric.curvature[center, center] += curvature_boost
        
        # Bonding curve → Treasury: trading volume adds to treasury
        if self.bonding_curve.total_trades > 0:
            volume_fee = self.bonding_curve.total_volume * 0.0001
            self.treasury.collect_fee(volume_fee, "bonding_curve_volume")
        
        # Bridge → Consensus: completed bridges boost phi score
        completed_bridges = sum(
            1 for tx in self.bridge.transactions.values()
            if tx.status == BridgeStatus.COMPLETED
        )
        if completed_bridges > 0:
            self.consensus.phi_qg = min(1.0, self.consensus.phi_qg + 0.01 * completed_bridges)
        
        # EREPR → Consensus: active bonds boost phi score
        if self.erepr.bonds:
            active_bonds = sum(1 for b in self.erepr.bonds.values() if b.is_alive())
            if active_bonds > 0:
                self.consensus.phi_qg = min(1.0, self.consensus.phi_qg + 0.005 * active_bonds)
        
        # Consensus → EREPR: finalized blocks strengthen bonds
        if self.consensus.stats["blocks_finalized"] > 0:
            for bond in self.erepr.bonds.values():
                bond.strengthen()
    
    def _update_nexus_coherence(self):
        """Update the overall nexus coherence metric."""
        # Coherence is the inverse of cross-layer entropy, normalized
        fabric_purity = self.fabric.compute_quantum_purity()
        p2p_coherence = self.p2p.network_coherence
        consensus_health = self.consensus.phi_tau
        treasury_health = min(1.0, self.treasury.balance / 1000.0) if self.treasury.balance > 0 else 0.5
        
        # Bonding curve health (based on liquidity and volume)
        curve_health = 0.5
        if self.bonding_curve.reserve > 0:
            curve_health = min(1.0, self.bonding_curve.reserve / self.bonding_curve.initial_reserve)
        
        # Bridge health
        bridge_health = self.bridge.get_state().health_score
        
        # EREPR health (based on active bonds)
        erepr_health = 0.5
        if self.erepr.bonds:
            active_bonds = sum(1 for b in self.erepr.bonds.values() if b.is_alive())
            erepr_health = min(1.0, active_bonds / 5.0)
        
        self.nexus_coherence = (
            0.18 * fabric_purity
            + 0.15 * p2p_coherence
            + 0.18 * consensus_health
            + 0.12 * treasury_health
            + 0.10 * curve_health
            + 0.07 * bridge_health
            + 0.20 * erepr_health
        )
    
    def _check_phase_transition(self):
        """Check if the Nexus should transition to the next phase."""
        if self._steps_since_last_transition < self.config.phase_transition_steps:
            return
        
        self._steps_since_last_transition = 0
        
        phase_order = list(NexusPhase)
        current_idx = phase_order.index(self.state.phase)
        
        if current_idx < len(phase_order) - 1:
            # Check conditions for transition
            can_transition = self._can_transition_to(phase_order[current_idx + 1])
            
            if can_transition:
                self.state.phase = phase_order[current_idx + 1]
    
    def _can_transition_to(self, next_phase: NexusPhase) -> bool:
        """Check if conditions are met to transition to the next phase.
        
        Args:
            next_phase: Target phase.
            
        Returns:
            True if transition conditions are met.
        """
        if next_phase == NexusPhase.INFLATION:
            # Need at least some quantum activity
            return self.fabric.step_count >= 1
        
        if next_phase == NexusPhase.CONDENSATION:
            # Need validators and peers
            return (
                len(self.consensus.validators) >= 2
                and len(self.p2p.get_active_peers()) >= 2
            )
        
        if next_phase == NexusPhase.CRYSTALLIZATION:
            # Need finalized blocks and treasury activity
            return (
                self.consensus.stats["blocks_finalized"] >= 1
                and self.treasury.balance > 0
            )
        
        if next_phase == NexusPhase.CONSCIOUSNESS:
            # Need high coherence and cross-layer integration
            return (
                self.nexus_coherence > 0.5
                and self.feedback_loop_count >= 2
                and self.cross_layer_entropy > 0.1
            )
        
        return True
    
    def _update_state(self):
        """Update the Nexus state dataclass."""
        self.state.coherence = self.nexus_coherence
        self.state.entropy = self.cross_layer_entropy
        self.state.phi_score = self.consensus.phi_tau
        self.state.chain_height = self.consensus.current_height
        self.state.active_peers = len(self.p2p.get_active_peers())
        self.state.treasury_balance = self.treasury.balance
    
    # --- State and Health ---
    
    def get_nexus_state(self) -> Dict[str, Any]:
        """Get the full state of the Nexus organism.
        
        Returns:
            Dictionary with complete Nexus state.
        """
        return {
            "phase": self.state.phase.value,
            "step_count": self.state.step_count,
            "uptime": time.time() - self.start_time,
            "nexus_coherence": self.nexus_coherence,
            "cross_layer_entropy": self.cross_layer_entropy,
            "feedback_loop_count": self.feedback_loop_count,
            "metrics": {
                "quantum_fidelity": self.fabric.compute_quantum_purity(),
                "entanglement_entropy": self.fabric.compute_entanglement_entropy(),
                "curvature_rms": float(np.sqrt(np.mean(self.fabric.curvature ** 2))),
                "phi_score": self.consensus.phi_tau,
                "chain_height": self.consensus.current_height,
                "blocks_finalized": self.consensus.stats["blocks_finalized"],
                "active_peers": len(self.p2p.get_active_peers()),
                "network_coherence": self.p2p.network_coherence,
                "treasury_balance": self.treasury.balance,
                "treasury_deployments": len(self.treasury.deployments),
                # Bonding curve metrics
                "uruu_price": self.bonding_curve.calculate_price(),
                "uruu_supply": self.bonding_curve.supply,
                "uruu_reserve": self.bonding_curve.reserve,
                "uruu_volume": self.bonding_curve.total_volume,
                "uruu_trades": self.bonding_curve.total_trades,
                "uruu_phase": self.bonding_curve.get_phase(),
                # Bridge metrics
                "bridge_volume": self.bridge.total_volume,
                "bridge_transactions": self.bridge.total_transactions,
                "bridge_pending": len(self.bridge.get_pending_transactions()),
                "bridge_health": self.bridge.get_state().health_score,
                # EREPR P2P gossip metrics
                "erepr_active_bonds": len([b for b in self.erepr.bonds.values() if b.is_alive()]),
                "erepr_known_peers": self.erepr.known_peers,
                "erepr_avg_bond_strength": (
                    sum(b.bond_strength for b in self.erepr.bonds.values()) / len(self.erepr.bonds)
                    if self.erepr.bonds else 0.0
                ),
                "erepr_gossip_queue": len(self.erepr.gossip_queue),
            },
        }
    
    def get_health_report(self) -> Dict[str, Any]:
        """Get a health report for all subsystems.
        
        Returns:
            Dictionary with health metrics and alerts.
        """
        alerts = []
        
        # Fabric health
        fabric_purity = self.fabric.compute_quantum_purity()
        fabric_health = fabric_purity
        if fabric_purity < 0.9:
            alerts.append("Quantum state purity below threshold")
        
        # Consensus health
        consensus_health = self.consensus.phi_tau
        if self.consensus.stats["blocks_finalized"] == 0 and self.consensus.stats["blocks_proposed"] > 0:
            alerts.append("No blocks finalized despite proposals")
        
        # P2P health
        p2p_health = self.p2p.network_coherence
        if p2p_health < 0.3:
            alerts.append("Network coherence critically low")
        
        # Treasury health
        treasury_health = min(1.0, self.treasury.balance / 100.0) if self.treasury.balance > 0 else 0.0
        if self.treasury.balance < 10.0:
            alerts.append("Treasury balance critically low")
        
        # Bonding curve health
        curve_health = 0.5
        if self.bonding_curve.reserve < self.bonding_curve.initial_reserve * 0.1:
            curve_health = 0.1
            alerts.append("Bonding curve reserve critically low")
        elif self.bonding_curve.supply >= self.bonding_curve.max_supply * 0.9:
            curve_health = 0.7
            alerts.append("URUU supply approaching maximum")
        else:
            curve_health = min(1.0, self.bonding_curve.reserve / self.bonding_curve.initial_reserve)
        
        # Bridge health
        bridge_health = self.bridge.get_state().health_score
        if bridge_health < 0.3:
            alerts.append("Bridge health critically low")
        pending_bridges = len(self.bridge.get_pending_transactions())
        if pending_bridges > 10:
            alerts.append(f"High number of pending bridge transactions: {pending_bridges}")
        
        # EREPR health
        erepr_health = 0.5
        if self.erepr.bonds:
            active_bonds = sum(1 for b in self.erepr.bonds.values() if b.is_alive())
            erepr_health = min(1.0, active_bonds / 5.0)
        else:
            alerts.append("No EREPR P2P bonds — node is isolated")
        
        # Overall health (adjusted weights for 7 subsystems + EREPR)
        overall_health = (
            0.18 * fabric_health
            + 0.15 * consensus_health
            + 0.12 * p2p_health
            + 0.12 * treasury_health
            + 0.10 * curve_health
            + 0.10 * bridge_health
            + 0.23 * erepr_health
        )
        
        if overall_health < 0.3:
            alerts.append("Overall Nexus health critically low")
        
        return {
            "overall_health": overall_health,
            "subsystem_health": {
                "fabric": fabric_health,
                "consensus": consensus_health,
                "p2p": p2p_health,
                "treasury": treasury_health,
                "bonding_curve": curve_health,
                "bridge": bridge_health,
                "erepr": erepr_health,
            },
            "alerts": alerts,
            "phase": self.state.phase.value,
            "nexus_coherence": self.nexus_coherence,
        }
