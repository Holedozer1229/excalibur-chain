# -*- mode: python ; coding: utf-8 -*-
"""
AetherionEXCAL SkyNet Beacon PyInstaller Spec File
===================================================
Builds the standalone SkyNet Node Beacon executable for Windows and Mac.
A background service that keeps your node discoverable 24/7 on the SkyNet P2P network.

Usage (Windows):
    pyinstaller AetherionEXCAL-Beacon.spec

Usage (Mac):
    pyinstaller AetherionEXCAL-Beacon.spec

Output:
    dist/AetherionEXCAL-Beacon.exe (Windows)
    dist/AetherionEXCAL-Beacon (Mac)

Features:
    - Always-on peer discovery server
    - UDP multicast + broadcast for LAN discovery
    - Central bootstrap server registration
    - Periodic heartbeats to stay alive
    - Persistent peer database (SQLite)
"""

import sys
import os

block_cipher = None

a = Analysis(
    ['skynet_beacon.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # P2P database
        'sphinx_os',
        'sphinx_os.nexus',
        'sphinx_os.nexus.postgres_p2p',
        # Standard library
        'sqlite3',
        'json',
        'threading',
        'hashlib',
        'argparse',
        'http.server',
        'subprocess',
        'urllib.request',
    ],
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
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

if sys.platform == 'win32':
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name='AetherionEXCAL-Beacon',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=True,  # Console mode for logging
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name='AetherionEXCAL-Beacon',
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=True,
        disable_windowed_traceback=False,
    )
