# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — tek dosya exe üretmek için:
    pyinstaller kuyumcu_veresiye.spec
"""

import os

koku = os.path.abspath(SPECPATH)

block_cipher = None

a = Analysis(
    [os.path.join(koku, "baslat.py")],
    pathex=[koku],
    binaries=[],
    datas=[
        (os.path.join(koku, "templates"), "templates"),
        (os.path.join(koku, "static"), "static"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="KuyumcuVeresiye",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
