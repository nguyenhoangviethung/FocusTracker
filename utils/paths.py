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
    return resource_base_dir() / "models" / "engagement_gru.onnx"


def data_dir() -> Path:
    path = writable_base_dir() / "data"
    path.mkdir(parents=True, exist_ok=True)
    return path


def history_path() -> Path:
    return data_dir() / "history.json"
