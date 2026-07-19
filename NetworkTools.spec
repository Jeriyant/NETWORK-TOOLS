# -*- mode: python ; coding: utf-8 -*-
# Single-file EXE. runtime_tmpdir di LocalAppData (bukan Temp sistem).
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = [
    "dns",
    "dns.resolver",
    "customtkinter",
    "clr",
    "clr_loader",
    "pythonnet",
    "webview",
    "webview.platforms.edgechromium",
]

for pkg in ("customtkinter", "webview", "pythonnet", "clr_loader"):
    tmp_ret = collect_all(pkg)
    datas += tmp_ret[0]
    binaries += tmp_ret[1]
    hiddenimports += tmp_ret[2]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=["hooks/pyi_rth_pythonnet.py"],
    excludes=["selenium", "webdriver_manager"],
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
    name="NetworkTools",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    # Extract runtime ke LocalAppData, bukan %TEMP%\_MEI (lebih stabil saat update)
    runtime_tmpdir="%LOCALAPPDATA%\\NetworkTools\\runtime",
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
