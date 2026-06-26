# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules


block_cipher = None
project_root = Path(globals().get("SPECPATH", ".")).resolve()

hiddenimports = [
    "cv2",
    "numpy",
    "joblib",
    "sklearn.ensemble._forest",
    "sklearn.tree._classes",
    "onnxruntime",
    "onnxruntime.capi.onnxruntime_pybind11_state",
    "xgboost",
]
hiddenimports += collect_submodules("mediapipe")
hiddenimports += collect_submodules("onnxruntime")
hiddenimports += collect_submodules("sklearn.ensemble")
hiddenimports += collect_submodules("sklearn.tree")
hiddenimports += collect_submodules("sklearn.utils")

mediapipe_datas = collect_data_files("mediapipe", include_py_files=False)


def add_data(path: Path, target: str) -> tuple[str, str] | None:
    return (str(path), target) if path.exists() else None


datas = [
    item
    for item in [
        add_data(project_root / "models" / "deep_forest_product_4class", "models/deep_forest_product_4class"),
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
