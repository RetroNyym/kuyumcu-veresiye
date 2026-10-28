# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — BAYİ anahtar üretici (konsol, tek dosya):
    pyinstaller anahtar_uretici.spec

Çıktı: dist\AnahtarUretici.exe  (MÜŞTERİYE VERİLMEZ)
"""

import os

koku = os.path.abspath(SPECPATH)

block_cipher = None

a = Analysis(
    [os.path.join(koku, "anahtar_uretici.py")],
    pathex=[koku],
    binaries=[],
    datas=[],
    excludes=["flask", "jinja2", "werkzeug", "tkinter", "openpyxl"],
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
    name="AnahtarUretici",
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
    icon=os.path.join(koku, "hacilar.ico"),
)
