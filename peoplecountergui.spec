# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['peoplecountergui.py'], # Corrected: Only the main script
    pathex=[],
    binaries=[],
    datas=[('detector', 'detector')], # Added: Include the detector folder/files
    hiddenimports=['tracker.centroidtracker', 'tracker.trackableobject'], # Added: Include tracker modules
    hookspath=[],
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
    [],
    exclude_binaries=True,
    name='peoplecountergui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True, # Keep True for testing, False for release
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas, # a.datas is used here to collect the data files specified above
    strip=False,
    upx=True,
    upx_exclude=[],
    name='peoplecountergui',
)