# PyInstaller spec — CAN Bootloader GUI
# Run from tools/:  pyinstaller CANBootloaderFlasher.spec

import sys
from pathlib import Path

block_cipher = None

tools_dir = Path(SPECPATH).resolve()
repo_dir = tools_dir.parent
bms_root = repo_dir.parent
hex2bin_src = repo_dir / "Hex2bin-2.5" / "bin" / "Release" / "hex2bin.exe"
dbc_src = bms_root / "FSAE_CHD_BMS_CAN_Protocol_V0.2.dbc"
if not dbc_src.is_file():
    dbc_src = repo_dir / "FSAE_CHD_BMS_CAN_Protocol_V0.2.dbc"

binaries = []
if hex2bin_src.is_file():
    binaries.append((str(hex2bin_src), "."))
else:
    print(f"warning: {hex2bin_src} missing — build will fail at runtime for .hex files")

datas = []
if dbc_src.is_file():
    datas.append((str(dbc_src), "."))
else:
    print(f"warning: {dbc_src} missing — cell monitor will not work in packaged app")

a = Analysis(
    ["flash_gui.py"],
    pathex=[str(tools_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=[
        "cantools",
        "cantools.database",
        "cantools.database.can",
        "cantools.database.can.signal",
        "can.interfaces.pcan",
        "can.interfaces.pcan.pcan",
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
    [],
    exclude_binaries=True,
    name="CANBootloaderFlasher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="CANBootloaderFlasher",
)
