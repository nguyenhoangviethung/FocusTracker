from __future__ import annotations

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def resource_base_dir() -> Path:
    """Directory containing bundled read-only resources (model/assets)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(getattr(sys, "_MEIPASS"))
    return PROJECT_ROOT


def writable_base_dir() -> Path:
    """Directory for writable runtime data like session history."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return PROJECT_ROOT


def model_path() -> Path:
    return late_fusion_gru_model_path()


def late_fusion_model_dir() -> Path:
    return resource_base_dir() / "models" / "late_fusion"


def late_fusion_gru_model_path() -> Path:
    return late_fusion_model_dir() / "engagement_gru.onnx"


def late_fusion_tcn_model_path() -> Path:
    return late_fusion_model_dir() / "engagement_tcn.onnx"


def late_fusion_gru_metadata_path() -> Path:
    return late_fusion_model_dir() / "engagement_gru.json"


def late_fusion_tcn_metadata_path() -> Path:
    return late_fusion_model_dir() / "engagement_tcn.json"


def late_fusion_xgb_model_path() -> Path:
    return late_fusion_model_dir() / "engagement_xgb.json"


def late_fusion_xgb_summary_path() -> Path:
    return late_fusion_model_dir() / "engagement_xgb.summary.json"


def late_fusion_xgb_preprocessor_path() -> Path:
    return late_fusion_model_dir() / "engagement_xgb.preprocess.npz"


def late_fusion_report_path() -> Path:
    return late_fusion_model_dir() / "late_fusion_gru_tcn_xgb_report.json"


def data_dir() -> Path:
    path = writable_base_dir() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def history_path() -> Path:
    return data_dir() / "history.json"
