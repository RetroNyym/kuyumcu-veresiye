# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — HACILAR KUYUMCULUK masaüstü (tkinter) tek dosya exe:
    pyinstaller kuyumcu_masaustu.spec

Çıktı: dist\HacilarKuyumculuk.exe
Veritabanı ve yedekler exe'nin yanında oluşur (web sürümüyle paylaşılabilir).
"""

import os

koku = os.path.abspath(SPECPATH)

block_cipher = None

a = Analysis(
    [os.path.join(koku, "masaustu.py")],
    pathex=[koku],
    binaries=[],
    datas=[(os.path.join(koku, "hacilar.ico"), ".")],
    hiddenimports=["tkinter", "tkinter.filedialog", "tkinter.messagebox",
                   "tkinter.simpledialog", "tkinter.ttk"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["flask", "jinja2", "werkzeug"],
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
    name="HacilarKuyumculuk",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(koku, "hacilar.ico"),
)
