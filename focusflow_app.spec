# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules


block_cipher = None
project_root = Path(globals().get("SPECPATH", ".")).resolve()

hiddenimports = [
    "cv2",
    "numpy",
    "xgboost",
]
hiddenimports += collect_submodules("mediapipe")

mediapipe_datas = collect_data_files("mediapipe", include_py_files=False)


def add_data(path: Path, target: str) -> tuple[str, str] | None:
    return (str(path), target) if path.exists() else None


datas = [
    item
    for item in [
        add_data(project_root / "models" / "triple_xgb_depth_robust_target_band_product", "models/triple_xgb_depth_robust_target_band_product"),
        add_data(project_root / "models" / "face_landmarker.task", "models"),
        add_data(project_root / "assets", "assets"),
        add_data(project_root / "data", "data"),
    ]
    if item is not None
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
