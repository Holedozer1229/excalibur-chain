# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:/Users/gregj/PycharmProjects/excalibur-chain/excalibur_wallet/__main__.py'],
    pathex=['C:/Users/gregj/PycharmProjects/excalibur-chain'],
    binaries=[],
    datas=[('C:/Users/gregj/PycharmProjects/excalibur-chain/excalibur_wallet/bip39_english.txt', 'excalibur_wallet')],
    hiddenimports=['lightledger', 'txscript', 'secp256k1', 'genesis_fork', 'txpq', 'knot_math', 'trifold_lockbox', 'file_locks', 'spent_leaf_registry', 'messerene_operator', 'p2p'],
    hookspath=['hooks'],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='excalibur',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
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
