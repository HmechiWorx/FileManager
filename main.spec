# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

python_home = Path(sys.base_prefix)
tcl_root = python_home / 'tcl'
tk_dll_dir = python_home / 'DLLs'
tk_binaries = [
    (str(tk_dll_dir / '_tkinter.pyd'), '.'),
    (str(tk_dll_dir / 'tcl86t.dll'), '.'),
    (str(tk_dll_dir / 'tk86t.dll'), '.'),
]
tk_datas = [
    (str(tcl_root), 'tcl'),
    (str(python_home / 'Lib' / 'tkinter'), 'tkinter'),
]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=tk_binaries,
    datas=tk_datas,
    hiddenimports=['tkinter', 'tkinter.ttk', '_tkinter'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=['pyinstaller_tk_runtime.py'],
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
    name='main',
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
