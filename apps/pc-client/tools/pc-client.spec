# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Xiaonuan PC simulator (Windows onefile)."""

from PyInstaller.utils.hooks import collect_all

block_cipher = None

datas: list = []
binaries: list = []
hiddenimports: list = []

for pkg in ("certifi", "httpx", "httpcore", "h11", "idna", "sniffio"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

a = Analysis(
    ["pyinstaller_entry.py"],
    pathex=[".."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports
    + [
        "xiaonuan_pc_client",
        "xiaonuan_pc_client.__main__",
        "xiaonuan_pc_client.main",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name="XiaonuanPCSim",
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
)
