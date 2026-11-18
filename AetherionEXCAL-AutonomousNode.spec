# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for AetherionEXCAL-AutonomousNode.exe"""

a = Analysis(
    ['skynet_autonomous_node.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'sphinx_os',
        'sphinx_os.nexus',
        'sphinx_os.nexus.holographic_p2p',
        'sphinx_os.config',
        'cryptography',
        'cryptography.hazmat',
        'cryptography.hazmat.primitives',
        'cryptography.hazmat.primitives.ciphers',
        'cryptography.hazmat.primitives.ciphers.aead',
    ],
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'pytest',
        'setuptools',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='AetherionEXCAL-AutonomousNode',
    debug=True,
    console=True,  # Console output for headless operation
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
