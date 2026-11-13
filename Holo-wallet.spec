# -*- mode: python ; coding: utf-8 -*-
# Holo-wallet PyInstaller spec — production build for Windows

a = Analysis(
    ['holo_wallet.py'],
    pathex=[],
    binaries=[],
    datas=[('sphinx_os', 'sphinx_os')],
    hiddenimports=[
        'sphinx_os.nexus',
        'sphinx_os.nexus.quantum_spacetime',
        'sphinx_os.nexus.conscious_consensus',
        'sphinx_os.nexus.holographic_p2p',
        'sphinx_os.nexus.self_organizing_treasury',
        'sphinx_os.nexus.orchestrator',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'pytest', 'setuptools'],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Holo-wallet',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
