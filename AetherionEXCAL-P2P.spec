# -*- mode: python ; coding: utf-8 -*-
"""
AetherionEXCAL P2P Wallet PyInstaller Spec File
=================================================
Builds a single executable P2P wallet with BTC and EXCAL dual lanes.
Includes: fork node, wallet GUI, P2P network, mining, encryption, desktop icon.

Usage (Windows):
    pyinstaller AetherionEXCAL-P2P.spec

Output:
    dist/AetherionEXCAL-P2P.exe  (single executable with desktop icon)
"""

import sys
import os

# ---------------------------------------------------------------------------
# Blockers
# ---------------------------------------------------------------------------
block_cipher = None
platform_excludes = (
    ['darkdetect._mac_detect']
    if sys.platform == 'win32'
    else ['win32com', 'pythoncom']
)
windows_com_hiddenimports = (
    [
        'win32com',
        'win32com.client',
        'win32com.shell',
        'win32com.shell.shell',
        'win32com.shell.shellcon',
        'pythoncom',
    ]
    if sys.platform == 'win32'
    else []
)

# ---------------------------------------------------------------------------
# Logo icon (if available) — __file__ not set in spec, use cwd
# ---------------------------------------------------------------------------
base_dir = os.getcwd()
icon_path = os.path.join(base_dir, "logo.jpeg")
ico_path = os.path.join(base_dir, "assets", "aetherion-logo.ico")
if os.path.exists(ico_path):
    app_icon = ico_path
elif os.path.exists(icon_path):
    app_icon = icon_path
else:
    app_icon = None

# ---------------------------------------------------------------------------
# Assembly — the main P2P wallet script
# ---------------------------------------------------------------------------
a = Analysis(
    ['p2p_wallet.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # Main wallet components
        'holo_wallet',
        'fork_node',
        'genesis_fork',
        'p2p_transports',
        'aiortc',
        'zeroconf',
        
        # Mining
        'stratum_miner',
        'stratum_fork',
        'cpu_miner',
        
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
        'sphinx_os.nexus.deutsch_ctc_oracle',
        'sphinx_os.nexus.unity_seal',
        'sphinx_os.nexus.omniscient_sphinx',
        'sphinx_os.nexus.btc_wallet_generator',
        'sphinx_os.nexus.btc_burn_wormhole',
        'sphinx_os.nexus.btc_burn_wormhole_recovery',
        'sphinx_os.nexus.btc_burn_collector',
        'sphinx_os.nexus.wormhole_governance',
        'sphinx_os.nexus.quantum_signal_generator',
        'sphinx_os.nexus.quantum_atomic_swap',
        'sphinx_os.nexus.pirate_burn_claim',
        'sphinx_os.nexus.btc_mainnet_sender',
        'sphinx_os.nexus.btc_accumulator',
        'sphinx_os.nexus.excal_liquidity_pool',
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
        'hmac',
        'struct',
        
        # Transaction script
        'txscript',
        
        # Stateful post-quantum wallet signing and cross-process state
        'wallet_transactions',
        'txpq',
        'trifold_lockbox',
        'file_locks',
        'spent_leaf_registry',
        'messerene_operator',
        'secp256k1',
        
        # BTC wallet components
        'excalibur_wallet',
        'excalibur_wallet.bip39',
        'excalibur_wallet.keys',
    ] + windows_com_hiddenimports,
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter.test',
        'pytest',
        'setuptools',
        'pip',
        'ensurepip',
        'unittest',
    ] + platform_excludes,
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
        name='AetherionEXCAL-P2P',
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
        icon=app_icon,  # Desktop icon
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
        name='AetherionEXCAL-P2P',
        debug=True,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=True,  # Console for debugging
        disable_windowed_traceback=False,
    )

# ---------------------------------------------------------------------------
# Single executable bundle
# ---------------------------------------------------------------------------
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    a.zipfiles,
    name='AetherionEXCAL-P2P',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
)
