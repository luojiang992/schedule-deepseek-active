# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['schedule_app.py'],
    pathex=[],
    binaries=[('D:/miniforge_manba/Library/bin/tcl86t.dll', '.'), ('D:/miniforge_manba/Library/bin/tk86t.dll', '.')],
    datas=[('D:/miniforge_manba/Library/lib/tcl8.6', 'tcl'), ('D:/miniforge_manba/Library/lib/tk8.6', 'tk')],
    hiddenimports=[],
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
    a.binaries,
    a.datas,
    [],
    name='日程管理',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
