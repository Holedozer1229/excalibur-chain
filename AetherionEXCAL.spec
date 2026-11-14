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
    ],
    hookspath=[],
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
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
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
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
    )
