# -*- mode: python ; coding: utf-8 -*-
"""
AetherionEXCAL PyInstaller Spec File
=====================================
Builds the unified AetherionEXCAL installer executable for Windows and Mac.
A single executable that installs everything: fork node, wallet GUI, P2P network,
mining (CPU + GPU stratum), and EREPR gossip protocol.

Usage (Windows):
    pyinstaller AetherionEXCAL.spec

Usage (Mac):
    pyinstaller AetherionEXCAL.spec

Output:
    dist/AetherionEXCAL.exe (Windows)
    dist/AetherionEXCAL (Mac)

Features:
    - Fork node RPC server (starts automatically)
    - GUI wallet with onboarding wizard
    - EREPR P2P gossip protocol for node discovery
    - CPU mining + GPU stratum server
    - CLI mode (with arguments)
"""

import sys
import os

# ---------------------------------------------------------------------------
# Blockers
# ---------------------------------------------------------------------------
block_cipher = None

# ---------------------------------------------------------------------------
# Assembly — the main wallet script
# ---------------------------------------------------------------------------
a = Analysis(
    ['excal_wallet.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # Holo-wallet CLI — fused into single executable
        'holo_wallet',
        # Fork node — starts automatically with wallet
        'fork_node',
        'genesis_fork',
        # Stratum miner — integrated GPU mining
        'stratum_miner',
        'stratum_fork',
        # Cryptography — AES-256-GCM + scrypt KDF
        'cryptography',
        'cryptography.hazmat.primitives.ciphers.aead',
        'cryptography.hazmat.primitives.kdf.scrypt',
        'cryptography.hazmat.backends.openssl.backend',
        'cryptography.hazmat.primitives.ciphers',
        'cryptography.hazmat.primitives.ciphers.algorithms',
        # CustomTkinter GUI framework
        'customtkinter',
        'darkdetect',
        # SphinxOS Nexus subsystems
        'sphinx_os',
        'sphinx_os.nexus',
        'sphinx_os.nexus.holographic_p2p',
        'sphinx_os.nexus.quantum_spacetime',
        'sphinx_os.nexus.quantum',
        'sphinx_os.nexus.quantum.e91',
        'sphinx_os.nexus.quantum.ghz',
        'quantum_p2p_glue',
        'skynet_beacon',
        'skynet_client',
        'sphinx_os.nexus.conscious_consensus',
        'sphinx_os.nexus.self_organizing_treasury',
        'sphinx_os.nexus.orchestrator',
        'sphinx_os.nexus.bonding_curve',
        'sphinx_os.nexus.zksync_bridge',
        'sphinx_os.nexus.knights_round_table',
        'sphinx_os.nexus.musig2',
        'sphinx_os.nexus.frost',
        'sphinx_os.nexus.ai_oracle_knight',
        'sphinx_os.nexus.knight_nft',
        'sphinx_os.nexus.erepr_protocol',
        'sphinx_os.secure_store',
        'sphinx_os.prometheus_metrics',
        # Prometheus metrics (optional)
        'prometheus_client',
        'prometheus_client.registry',
        'prometheus_client.metrics_core',
        'prometheus_client.exposition',
        # Numerical computing
        'numpy',
        'numpy.core',
        'numpy.core.multiarray',
        # Standard library
        'secrets',
        'hashlib',
        'json',
        'threading',
        'base64',
        'argparse',
        'http.client',
        'subprocess',
        # Transaction script
        'txscript',
        # Stateful post-quantum wallet signing and cross-process state
        'wallet_transactions',
        'txpq',
        'trifold_lockbox',
        'file_locks',
        'spent_leaf_registry',
        'messerene_operator',
        # KNOT lock — Möbius torus-knot commitment transactions
        'knot_wallet',
        'knot_math',
        # Living ledger — real-time block explorer
        'living_ledger',
        # Merge mining — Bitcoin + Monero AuxPoW
        'merge_mining',
        'monero_merge_mining',
        'live_merge_mining',
        'auxlib',
        # UTXO tracer with Fibonacci genesis law
        'follow_utxos',
        # Genesis address proof of control
        'proof_of_control_1a1z',
        # Spectral graph Shor algorithm
        'spectral_graph_shor',
        # Scalar wave unification framework
        'scalar_wave_unification',
        # Bell state assembly language
        'bell_state_asm',
        # Riemann hypothesis and Hilbert-Pólya operator
        'riemann_hypothesis',
        'hilbert_polya',
        # Bitcoin puzzle solver
        'btc_puzzle_solver',
        'genesis_block_puzzle',
        'genesis_nonce_reuse',
        # Key recovery
        'key_recovery_superposition',
        # Topological quantum field theory
        'topological_quantum_field',
        # Montgomery pair correlation
        'montgomery_pair_correlation',
        # DNA-Riemann connection
        'dna_riemann',
        # Bat Doppler-Riemann connection
        'bat_doppler_riemann',
        # Hyperbolic geometry and music
        'friedman_hyperbolic_rsa',
        'hyperbolic_music',
        # Theory of everything unification
        'theory_of_everything',
        # Caduceus framework
        'caduceus',
        # Riemann crystal quasicrystals
        'riemann_crystal',
        # Omega signing
        'omega_sign',
        'omega_verify',
        # Genesis signer
        'genesis_signer',
        # Payment watcher
        'payment_watcher',
        # P2P wallet
        'p2p_wallet',
        # Light ledger
        'lightledger',
        # Dyson miner
        'dyson_miner',
        # CPU miner
        'cpu_miner',
        'cpu_miner_mp',
        # Grace miner
        'grace_miner',
        # Fork sniper
        'fork_sniper',
        # Stratum fork
        'stratum_fork',
        # P2P layer
        'p2p_layer',
        # Inventory board
        'inventory_board',
        # Skynet autonomous node
        'skynet_autonomous_node',
        # Skynet scalar wave
        'skynet_scalar_wave',
        # Quantum P2P glue
        'quantum_p2p_glue',
        # EREPR protocol
        'sphinx_os.nexus.erepr_protocol',
        # Holo wallet
        'holo_wallet',
        # Secp256k1
        'secp256k1',
        # Wallet crypto
        'wallet_crypto',
        # Chain state
        'chainstate',
        # UTXO database
        'utxodb',
        # Mempool
        'mempool',
        # Node RPC
        'node_rpc',
        # Excalibur main module
        'excalibur',
        # P2P discovery
        'p2p',
        # Phi drive
        'phi_drive',
        # p mod 4 key derivation
        'p_mod4_key_derivation',
        # Messerene 1A1Z relationship
        'messerene_1a1z_relationship',
        # BIP32 Messerene derivations
        'bip32_messerene_derivations',
        # Retrocausal entropy well
        'retrocausal_entropy_well',
        # Retrocausal seed tracer
        'retrocausal_seed_tracer',
        # Digital physics BTC
        'digital_physics_btc',
        # Autonomous BTC learner
        'autonomous_btc_learner',
        # The key
        'the_key',
        # Riemann spectral descent
        'riemann_spectral_descent',
        # Riemann hypothesis proof
        'riemann_hypothesis_proof',
        # Noble surprise
        'nobel_surprise',
    ],
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter.test',
        'pytest',
        'setuptools',
        'pip',
        'ensurepip',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# ---------------------------------------------------------------------------
# Platform-specific executable
# ---------------------------------------------------------------------------
if sys.platform == 'win32':
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name='AetherionEXCAL',
        debug=True,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=True,  # Console for debugging
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
else:
    # macOS / Linux
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name='AetherionEXCAL',
        debug=True,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=True,  # Console for debugging
        disable_windowed_traceback=False,
    )
