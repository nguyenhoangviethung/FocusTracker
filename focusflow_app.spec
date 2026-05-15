# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules


block_cipher = None
project_root = Path(__file__).resolve().parent

hiddenimports = [
    "cv2",
    "numpy",
    "customtkinter",
    "onnxruntime",
    "onnxruntime.capi.onnxruntime_pybind11_state",
]
hiddenimports += collect_submodules("mediapipe")
hiddenimports += collect_submodules("onnxruntime")

mediapipe_datas = collect_data_files("mediapipe", include_py_files=False)

datas = [
    (str(project_root / "models" / "engagement_gru.onnx"), "models"),
    (str(project_root / "assets"), "assets"),
    (str(project_root / "data"), "data"),
]
datas += mediapipe_datas


a = Analysis(
    [str(project_root / "main.py")],
    pathex=[str(project_root)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
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
    name="FocusFlowAI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
