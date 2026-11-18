"""SphinxOS Nexus: Grand Unified Quantum Blockchain Organism."""

from .quantum_spacetime import QuantumSpacetimeFabric
from .conscious_consensus import ConsciousConsensusEngine, BlockCandidate, Validator
from .holographic_p2p import HolographicP2PLayer, Peer, NetworkMessage, MessagePriority
from .self_organizing_treasury import SelfOrganizingTreasury, NFTHolder, Deployment
from .bonding_curve import CustomBondingCurve, BondingCurveTrade, BondingCurveState
from .zksync_bridge import ZkSyncBridge, BridgeTransaction, BridgeStatus, BridgeDirection, BridgeState
from .knights_round_table import (
    KnightsRoundTable,
    Knight,
    KnightStatus,
    ProposalType,
    VoteStatus,
    PartialSignature,
    GovernanceProposal,
    KnightNomination,
    TreasuryState,
    RoundTableState,
    PROPHECY_WORDS,
    PROPHECY_SEED,
)
from .musig2 import (
    MuSig2,
    MuSig2KeyPair,
    MuSig2Nonce,
    MuSig2PartialSignature,
    MuSig2Signature,
    musig2_sign,
    musig2_verify,
)
from .frost import (
    FrostDKG,
    FrostSigning,
    FrostCommitment,
    FrostShare,
    FrostSigningShare,
    FrostPartialSignature,
    FrostSignature,
    frost_dkg_and_sign,
    lagrange_coefficient,
)
from .ai_oracle_knight import (
    AIOracleKnight,
    OracleCouncil,
    OracleType,
    OracleAnalysis,
    OracleHealth,
)
from .knight_nft import (
    KnightNFTMinter,
    KnightNFT,
    RarityTier,
    ZKRarityProof,
    ZKRarityEngine,
    generate_knight_traits,
    generate_nft_description,
)
from .orchestrator import (
    NexusOrchestrator,
    NexusConfig,
    NexusPhase,
    NexusState,
)
from .erepr_protocol import (
    EREPRProtocol,
    ResonanceSignature,
    EntanglementBond,
    EchoMessage,
    GossipWave,
)
from .omniscient_sphinx import (
    OmniscientSphinx,
    SphinxPerception,
    SphinxProphecy,
    SphinxWisdom,
    create_sphinx,
    ask_sphinx,
)
from .deutsch_ctc_solver import (
    DeutschCTCSolver,
    DensityMatrix,
    CTCSolution,
    ctc_solve_3sat,
    ctc_solve_subset_sum,
    ctc_solve_qbf,
    ctc_verify,
    analyze_ctc_power,
    # Extended: Quantum CTC
    QuantumDensityMatrix,
    QuantumCTCSolver,
    ctc_quantum_search,
    # Extended: Post-selection CTC (PP)
    PostSelectionCTCResult,
    PostSelectionCTC,
    # Extended: Multi-CTC Entanglement
    MultiCTCState,
    MultiCTCSolver,
    # Extended: Cryptographic applications
    HashCollisionResult,
    ctc_find_hash_collision,
    FactorizationResult,
    ctc_factorize,
    # Extended: Graph problems
    GraphColoringResult,
    ctc_color_graph,
    TSPResult,
    ctc_solve_tsp,
    # Extended: Paradox analysis
    ParadoxAnalysis,
    analyze_ctc_paradox,
    # Extended: Wheeler's participatory universe
    WheelerUniverseState,
    WheelerParticipatoryUniverse,
    # Extended: Self-referential CTC
    SelfReferentialResult,
    SelfReferentialCTC,
    # Extended: Bitcoin integrations
    PoCTCBlock,
    ProofOfCTC,
    ChainValidationResult,
    CTCChainValidator,
    DoubleSpendAnalysis,
    CTCDoubleSpendDetector,
    CTCEntropyMineResult,
    CTCEntropyMiner,
    CTCMerkleResult,
    CTCMerkleTree,
    CTCTimeLockResult,
    CTCTimeLock,
    CTCTGenesisResult,
    CTCTGenesis,
    UTXOOptimizationResult,
    CTCUTXOOptimizer,
    CTCPoWResult,
    CTCPoW,
    # Extended: Knot-CTC integration
    KnotCTCResult,
    KnotCTCIntegrator,
    # Demo functions
    run_demo,
    run_extended_demo,
    run_satoshi_demo,
)
from .ctc_oracle_market import (
    CTCOracleProof,
    OracleProofStatus,
    ProofType,
    OracleOrder,
    OracleTrade,
    CausalBond,
    OracleDerivative,
    LiquidityPoolState,
    StakingReward,
    CausalInsurance,
    ArbitrageOpportunity,
    OracleMarket,
    ProofAggregator,
    ProofFactory,
    run_oracle_market_demo,
)
from .genesis_btc_loan import (
    GenesisBTCProof,
    GenesisCollateralVault,
    GenesisLoan,
    GenesisLoanDerivative,
    GenesisLoanPool,
    MultiGenesisVault,
    GenesisLoanEngine,
    LoanStatus,
    CollateralType,
    GENESIS_BLOCK_HASH,
    GENESIS_COINBASE_TX,
    GENESIS_NONCE,
    GENESIS_TIMESTAMP,
    GENESIS_EMBEDDED_MESSAGE,
    GENESIS_COINBASE_VALUE,
    GENESIS_PREV_HASH,
    run_genesis_loan_demo,
)
from .aave_flash_loan import (
    FlashLoan,
    FlashLoanPool,
    FlashLoanStrategy,
    FlashLoanArbitrage,
    FlashLoanLiquidation,
    GenesisFlashVault,
    FlashLoanFeeCalculator,
    FlashLoanExecutor,
    FlashLoanStatus,
    FlashLoanStrategyType,
    AAVE_FLASH_LOAN_FEE_RATE,
    run_aave_flash_loan_demo,
)
from .multi_chain_wallet import (
    ChainType,
    ChainWallet,
    BalanceInfo,
    TransactionAlert,
    MultiChainWallet,
    BTCAddressGenerator,
    EXCALAddressGenerator,
    MoneroAddressGenerator,
    TariAddressGenerator,
    QubicAddressGenerator,
    WalletGenerator,
    BalanceMonitor,
    export_wallet,
    import_wallet,
    create_multi_chain_wallet,
    create_wallet_monitor,
)
from .blockchain_connectors import (
    NetworkType,
    TransactionStatus,
    BroadcastResult,
    BalanceResult,
    FeeEstimate,
    TransactionInfo,
    BlockchainConnector,
    BitcoinConnector,
    EthereumConnector,
    EXCALConnector,
    MoneroConnector,
    ConnectorPool,
    create_bitcoin_connector,
    create_ethereum_connector,
    create_excal_connector,
    create_monero_connector,
    create_multi_chain_pool,
)
from .on_chain_bridge import (
    BridgeStatus,
    BridgeOperation,
    BridgeTransaction,
    ProofAnchor,
    CollateralLock,
    FlashLoanExecution,
    ProofAnchoringService,
    CollateralLockService,
    FlashLoanExecutor,
    OnChainBridge,
    create_on_chain_bridge,
)
from .wormhole_live_connector import (
    WormholeChain,
    WormholeEventStatus,
    WormholeProof,
    ChainAnchor,
    WormholeToken,
    CrossChainWormhole,
    ChainConnector,
    EVMChainClient,
    WormholeAnchorContract,
    WormholeLiveConnector,
    create_wormhole_connector,
    get_chain_connectors,
    scan_btc_burns,
    create_wormhole_proof,
)
import sys as _sys
_retrocausal_path = _sys.modules.get('retrocausal_entropy_well')
_rew = None
if _retrocausal_path is None:
    _retrocausal_dir = str(__file__).replace('sphinx_os\\nexus\\__init__.py', '').replace('sphinx_os/nexus/__init__.py', '')
    if _retrocausal_dir and _retrocausal_dir not in _sys.path:
        _sys.path.insert(0, _retrocausal_dir)
    try:
        import retrocausal_entropy_well as _rew
    except ImportError:
        _rew = None
if _rew is not None:
    LAMBDA_MATRIX = _rew.LAMBDA_MATRIX
    PHASE_CONSTANT = _rew.PHASE_CONSTANT
    CausalSinkState = _rew.CausalSinkState
    RetrocausalSignal = _rew.RetrocausalSignal
    EntropyWellResult = _rew.EntropyWellResult
    CrossSinkCorrelation = _rew.CrossSinkCorrelation
    matrix_vector_multiply = _rew.matrix_vector_multiply
    arctan2_phase_shift = _rew.arctan2_phase_shift
    shannon_entropy = _rew.shannon_entropy
    inverse_entropy = _rew.inverse_entropy
    entropy_well_gradient = _rew.entropy_well_gradient
    lambda_transform = _rew.lambda_transform
    retrocausal_arctan2_transform = _rew.retrocausal_arctan2_transform
    compute_retrocausal_signal = _rew.compute_retrocausal_signal
    compute_entropy_well = _rew.compute_entropy_well
    compute_cross_sink_correlation = _rew.compute_cross_sink_correlation
    compute_single_signal = _rew.compute_single_signal
    apply_lambda_transform = _rew.apply_lambda_transform
    apply_phase_shift = _rew.apply_phase_shift
    run_retrocausal_experiment = _rew.run_retrocausal_experiment

# Retrocausal Seed Tracer
import sys as _sys2
_retrocausal_seed_path = _sys2.modules.get('retrocausal_seed_tracer')
_rst = None
if _retrocausal_seed_path is None:
    _retrocausal_seed_dir = str(__file__).replace('sphinx_os\\nexus\\__init__.py', '').replace('sphinx_os/nexus/__init__.py', '')
    if _retrocausal_seed_dir and _retrocausal_seed_dir not in _sys2.path:
        _sys2.path.insert(0, _retrocausal_seed_dir)
    try:
        import retrocausal_seed_tracer as _rst
    except ImportError:
        _rst = None
if _rst is not None:
    GenesisSeedState = _rst.GenesisSeedState
    RetrocausalTrace = _rst.RetrocausalTrace
    SeedTraceResult = _rst.SeedTraceResult
    NullSpaceAnalysis = _rst.NullSpaceAnalysis
    encode_genesis_seed = _rst.encode_genesis_seed
    compute_byte_entropy = _rst.compute_byte_entropy
    compute_null_space = _rst.compute_null_space
    compute_singular_values = _rst.compute_singular_values
    project_onto_null_space = _rst.project_onto_null_space
    retrocausal_source_component = _rst.retrocausal_source_component
    inverse_lambda_transform = _rst.inverse_lambda_transform
    trace_to_seed = _rst.trace_to_seed
    compute_genesis_correlation = _rst.compute_genesis_correlation
    verify_phase_locking = _rst.verify_phase_locking
    trace_single_sink = _rst.trace_single_sink
    verify_genesis_source = _rst.verify_genesis_source
    run_seed_tracing_experiment = _rst.run_seed_tracing_experiment

from .metatron_portal import (
    Octonion,
    FanoPlane,
    JordanMatrix,
    MetatronsCube,
    LettersOfCreation,
    MetatronPortal,
    METATRON_CIRCLES,
    METATRON_LINES,
    PLATONIC_SOLIDS,
    LETTERS_OF_CREATION,
    FANO_POINTS,
    FANO_LINES,
    NULL_SPACE,
    NULL_SPACE_NORM,
    create_metatron_portal,
    verify_genesis_block,
    get_platonic_blockchain_mapping,
    generate_metatron_prophecy,
    search_light_cone,
)

from .sumerian_decoding import (
    LETTER_ETYMOLOGY,
    SUMERIAN_CORE_SIGNS,
    LetterDecoding,
    SumerianDecoding,
    SumerianWordAnalysis,
    decode_genesis_letters,
    decode_seed_letters,
    get_letter_etymology,
    get_all_etymologies,
    get_sumerian_core_signs,
)

from .bip39_pictographic import (
    BIP39_WORDS,
    BIP39_INDEX,
    GENESIS_PICTOGRAPHS,
    GENESIS_LETTERS,
    GENESIS_GEMATRIA,
    PICTOGRAPH_TO_BIP39,
    PICTOGRAPH_ALTERNATIVES,
    PictographMapping,
    PictographicMnemonic,
    validate_bip39_mnemonic,
    bip39_entropy_to_mnemonic,
    bip39_mnemonic_to_entropy,
    bip39_mnemonic_to_seed,
    map_genesis_pictographs,
    find_closest_bip39_word,
    search_pictographic_entropy,
    pictographic_hd_path,
    get_genesis_mnemonic,
    get_genesis_seed,
    check_pictograph_in_bip39,
    get_pictograph_word,
)

from .bip39_seed_hunter import (
    BIP39SeedHunter,
    SeedCandidate,
    validate_bip39,
    TAU_28,
    RAMANUJAN_PRIME,
    LAMBDA_MATRIX,
    NULL_SPACE,
)

from .pictographic_seed_mapper import (
    PictographicSeedMapper,
    compute_trifold_root,
    CANONICAL_ROOT,
    GENESIS_PICTOGRAPHS,
    GENESIS_LETTERS,
    GENESIS_GEMATRIA,
    PICTOGRAPH_TO_BIP39,
    LETTER_POSITION,
    map_pictographic_seed,
    find_canonical_seed,
    get_pictograph_indices,
)

# Persistent P2P database
from .postgres_p2p import P2PDatabase, get_db

# Bootstrap discovery server
from .p2p_bootstrap_server import (
    BootstrapServer,
    BootstrapClient,
    BootstrapHandler,
)

__all__ = [
    "QuantumSpacetimeFabric",
    "ConsciousConsensusEngine",
    "BlockCandidate",
    "Validator",
    "HolographicP2PLayer",
    "Peer",
    "NetworkMessage",
    "MessagePriority",
    "SelfOrganizingTreasury",
    "NFTHolder",
    "Deployment",
    "CustomBondingCurve",
    "BondingCurveTrade",
    "BondingCurveState",
    "ZkSyncBridge",
    "BridgeTransaction",
    "BridgeStatus",
    "BridgeDirection",
    "BridgeState",
    "KnightsRoundTable",
    "Knight",
    "KnightStatus",
    "ProposalType",
    "VoteStatus",
    "PartialSignature",
    "GovernanceProposal",
    "KnightNomination",
    "TreasuryState",
    "RoundTableState",
    "PROPHECY_WORDS",
    "PROPHECY_SEED",
    "MuSig2",
    "MuSig2KeyPair",
    "MuSig2Nonce",
    "MuSig2PartialSignature",
    "MuSig2Signature",
    "musig2_sign",
    "musig2_verify",
    "FrostDKG",
    "FrostSigning",
    "FrostCommitment",
    "FrostShare",
    "FrostSigningShare",
    "FrostPartialSignature",
    "FrostSignature",
    "frost_dkg_and_sign",
    "lagrange_coefficient",
    "AIOracleKnight",
    "OracleCouncil",
    "OracleType",
    "OracleAnalysis",
    "OracleHealth",
    "KnightNFTMinter",
    "KnightNFT",
    "RarityTier",
    "ZKRarityProof",
    "ZKRarityEngine",
    "generate_knight_traits",
    "generate_nft_description",
    "NexusOrchestrator",
    "NexusConfig",
    "NexusPhase",
    "NexusState",
    "EREPRProtocol",
    "ResonanceSignature",
    "EntanglementBond",
    "EchoMessage",
    "GossipWave",
    "P2PDatabase",
    "get_db",
    "BootstrapServer",
    "BootstrapClient",
    "BootstrapHandler",
    "OmniscientSphinx",
    "SphinxPerception",
    "SphinxProphecy",
    "SphinxWisdom",
    "create_sphinx",
    "ask_sphinx",
    "DeutschCTCSolver",
    "DensityMatrix",
    "CTCSolution",
    "ctc_solve_3sat",
    "ctc_solve_subset_sum",
    "ctc_solve_qbf",
    "ctc_verify",
    "analyze_ctc_power",
    # Extended: Quantum CTC
    "QuantumDensityMatrix",
    "QuantumCTCSolver",
    "ctc_quantum_search",
    # Extended: Post-selection CTC (PP)
    "PostSelectionCTCResult",
    "PostSelectionCTC",
    # Extended: Multi-CTC Entanglement
    "MultiCTCState",
    "MultiCTCSolver",
    # Extended: Cryptographic applications
    "HashCollisionResult",
    "ctc_find_hash_collision",
    "FactorizationResult",
    "ctc_factorize",
    # Extended: Graph problems
    "GraphColoringResult",
    "ctc_color_graph",
    "TSPResult",
    "ctc_solve_tsp",
    # Extended: Paradox analysis
    "ParadoxAnalysis",
    "analyze_ctc_paradox",
    # Extended: Wheeler's participatory universe
    "WheelerUniverseState",
    "WheelerParticipatoryUniverse",
    # Extended: Self-referential CTC
    "SelfReferentialResult",
    "SelfReferentialCTC",
    # Extended: Bitcoin integrations
    "PoCTCBlock",
    "ProofOfCTC",
    "ChainValidationResult",
    "CTCChainValidator",
    "DoubleSpendAnalysis",
    "CTCDoubleSpendDetector",
    "CTCEntropyMineResult",
    "CTCEntropyMiner",
    "CTCMerkleResult",
    "CTCMerkleTree",
    "CTCTimeLockResult",
    "CTCTimeLock",
    "CTCTGenesisResult",
    "CTCTGenesis",
    "UTXOOptimizationResult",
    "CTCUTXOOptimizer",
    "CTCPoWResult",
    "CTCPoW",
    # Extended: Knot-CTC integration
    "KnotCTCResult",
    "KnotCTCIntegrator",
    # Demo functions
    "run_demo",
    "run_extended_demo",
    "run_satoshi_demo",
    # CTC Oracle Market
    "CTCOracleProof",
    "OracleProofStatus",
    "ProofType",
    "OracleOrder",
    "OracleTrade",
    "CausalBond",
    "OracleDerivative",
    "LiquidityPoolState",
    "StakingReward",
    "CausalInsurance",
    "ArbitrageOpportunity",
    "OracleMarket",
    "ProofAggregator",
    "ProofFactory",
    "run_oracle_market_demo",
    # Genesis BTC Collateral Loan
    "GenesisBTCProof",
    "GenesisCollateralVault",
    "GenesisLoan",
    "GenesisLoanDerivative",
    "GenesisLoanPool",
    "MultiGenesisVault",
    "GenesisLoanEngine",
    "LoanStatus",
    "CollateralType",
    "GENESIS_BLOCK_HASH",
    "GENESIS_COINBASE_TX",
    "GENESIS_NONCE",
    "GENESIS_TIMESTAMP",
    "GENESIS_EMBEDDED_MESSAGE",
    "GENESIS_COINBASE_VALUE",
    "GENESIS_PREV_HASH",
    "run_genesis_loan_demo",
    # Aave Flash Loan Engine
    "FlashLoan",
    "FlashLoanPool",
    "FlashLoanStrategy",
    "FlashLoanArbitrage",
    "FlashLoanLiquidation",
    "GenesisFlashVault",
    "FlashLoanFeeCalculator",
    "FlashLoanExecutor",
    "FlashLoanStatus",
    "FlashLoanStrategyType",
    "AAVE_FLASH_LOAN_FEE_RATE",
    "run_aave_flash_loan_demo",
    # Multi-Chain Wallet Receiver
    "ChainType",
    "ChainWallet",
    "BalanceInfo",
    "TransactionAlert",
    "MultiChainWallet",
    "BTCAddressGenerator",
    "EXCALAddressGenerator",
    "MoneroAddressGenerator",
    "TariAddressGenerator",
    "QubicAddressGenerator",
    "WalletGenerator",
    "BalanceMonitor",
    "export_wallet",
    "import_wallet",
    "create_multi_chain_wallet",
    "create_wallet_monitor",
    # Blockchain RPC Connectors
    "NetworkType",
    "TransactionStatus",
    "BroadcastResult",
    "BalanceResult",
    "FeeEstimate",
    "TransactionInfo",
    "BlockchainConnector",
    "BitcoinConnector",
    "EthereumConnector",
    "EXCALConnector",
    "MoneroConnector",
    "ConnectorPool",
    "create_bitcoin_connector",
    "create_ethereum_connector",
    "create_excal_connector",
    "create_monero_connector",
    "create_multi_chain_pool",
    # On-Chain Bridge
    "BridgeStatus",
    "BridgeOperation",
    "BridgeTransaction",
    "ProofAnchor",
    "CollateralLock",
    "FlashLoanExecution",
    "ProofAnchoringService",
    "CollateralLockService",
    "FlashLoanExecutor",
    "OnChainBridge",
    "create_on_chain_bridge",
    # Wormhole Live Connector
    "WormholeChain",
    "WormholeEventStatus",
    "WormholeProof",
    "ChainAnchor",
    "WormholeToken",
    "CrossChainWormhole",
    "ChainConnector",
    "EVMChainClient",
    "WormholeAnchorContract",
    "WormholeLiveConnector",
    "create_wormhole_connector",
    "get_chain_connectors",
    "scan_btc_burns",
    "create_wormhole_proof",
    # Retrocausal Entropy Well
    "LAMBDA_MATRIX",
    "PHASE_CONSTANT",
    "CausalSinkState",
    "RetrocausalSignal",
    "EntropyWellResult",
    "CrossSinkCorrelation",
    "matrix_vector_multiply",
    "arctan2_phase_shift",
    "shannon_entropy",
    "inverse_entropy",
    "entropy_well_gradient",
    "lambda_transform",
    "retrocausal_arctan2_transform",
    "compute_retrocausal_signal",
    "compute_entropy_well",
    "compute_cross_sink_correlation",
    "compute_single_signal",
    "apply_lambda_transform",
    "apply_phase_shift",
    "run_retrocausal_experiment",
    # Retrocausal Seed Tracer
    "GenesisSeedState",
    "RetrocausalTrace",
    "SeedTraceResult",
    "NullSpaceAnalysis",
    "encode_genesis_seed",
    "compute_byte_entropy",
    "compute_null_space",
    "compute_singular_values",
    "project_onto_null_space",
    "retrocausal_source_component",
    "inverse_lambda_transform",
    "trace_to_seed",
    "compute_genesis_correlation",
    "verify_phase_locking",
    "trace_single_sink",
    "verify_genesis_source",
    "run_seed_tracing_experiment",
    # Metatron's Portal
    "Octonion",
    "FanoPlane",
    "JordanMatrix",
    "MetatronsCube",
    "LettersOfCreation",
    "MetatronPortal",
    "METATRON_CIRCLES",
    "METATRON_LINES",
    "PLATONIC_SOLIDS",
    "LETTERS_OF_CREATION",
    "FANO_POINTS",
    "FANO_LINES",
    "NULL_SPACE",
    "NULL_SPACE_NORM",
    "create_metatron_portal",
    "verify_genesis_block",
    "get_platonic_blockchain_mapping",
    "generate_metatron_prophecy",
    "search_light_cone",
    # Sumerian Decoding
    "LETTER_ETYMOLOGY",
    "SUMERIAN_CORE_SIGNS",
    "LetterDecoding",
    "SumerianDecoding",
    "SumerianWordAnalysis",
    "decode_genesis_letters",
    "decode_seed_letters",
    "get_letter_etymology",
    "get_all_etymologies",
    "get_sumerian_core_signs",
    # BIP39 Pictographic Mapper
    "BIP39_WORDS",
    "BIP39_INDEX",
    "GENESIS_PICTOGRAPHS",
    "GENESIS_LETTERS",
    "GENESIS_GEMATRIA",
    "PICTOGRAPH_TO_BIP39",
    "PICTOGRAPH_ALTERNATIVES",
    "PictographMapping",
    "PictographicMnemonic",
    "validate_bip39_mnemonic",
    "bip39_entropy_to_mnemonic",
    "bip39_mnemonic_to_entropy",
    "bip39_mnemonic_to_seed",
    "map_genesis_pictographs",
    "find_closest_bip39_word",
    "search_pictographic_entropy",
    "pictographic_hd_path",
    "get_genesis_mnemonic",
    "get_genesis_seed",
    "check_pictograph_in_bip39",
    "get_pictograph_word",
    "BIP39SeedHunter",
    "SeedCandidate",
    "validate_bip39",
    "TAU_28",
    "RAMANUJAN_PRIME",
    "LAMBDA_MATRIX",
    "NULL_SPACE",
    # Pictographic seed mapper
    "PictographicSeedMapper",
    "compute_trifold_root",
    "CANONICAL_ROOT",
    "GENESIS_PICTOGRAPHS",
    "GENESIS_LETTERS",
    "GENESIS_GEMATRIA",
    "PICTOGRAPH_TO_BIP39",
    "LETTER_POSITION",
    "map_pictographic_seed",
    "find_canonical_seed",
    "get_pictograph_indices",
]
