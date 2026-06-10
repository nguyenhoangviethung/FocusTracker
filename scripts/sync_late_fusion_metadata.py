from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import torch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENGAGEMENT_REPO = PROJECT_ROOT.parent / "engagement-cpu"
DEFAULT_RUN_DIR = DEFAULT_ENGAGEMENT_REPO / "checkpoints" / "runs" / "final_rnn_temporal_models_20260529"
ARTIFACT_DIR = PROJECT_ROOT / "models" / "late_fusion"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _sync_component(component: str, checkpoint_path: Path, metadata_path: Path) -> None:
    if not checkpoint_path.exists():
        raise FileNotFoundError(f"Source checkpoint not found: {checkpoint_path}")
    if not metadata_path.exists():
        raise FileNotFoundError(f"Bundled metadata not found: {metadata_path}")

    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    metadata = _load_json(metadata_path)

    for key in [
        "best_threshold",
        "best_temperature",
        "feature_mean",
        "feature_std",
        "model_kwargs",
        "normalize_features",
        "prior_shift_calibration",
    ]:
        if key in checkpoint:
            metadata[key] = checkpoint[key]

    model_kwargs = checkpoint.get("model_kwargs", {})
    metadata["sequence_length"] = int(model_kwargs.get("max_seq_len", 30))
    metadata["raw_feature_dim"] = 30
    metadata["enriched_feature_dim"] = int(model_kwargs.get("input_size", 90))
    metadata["metadata_source_checkpoint"] = (
        f"engagement-cpu/checkpoints/runs/final_rnn_temporal_models_20260529/"
        f"rnn_{component}/engagement_{component}.pt"
    )
    metadata["metadata_source_note"] = (
        "feature_mean/feature_std copied into this repo; runtime must not read this source path"
    )
    metadata["source_checkpoint"] = f"models/late_fusion/engagement_{component}.onnx"
    metadata["onnx_artifact"] = f"models/late_fusion/engagement_{component}.onnx"
    metadata["last_checkpoint_path"] = f"models/late_fusion/engagement_{component}.onnx"
    metadata["bundled_artifact_path"] = f"models/late_fusion/engagement_{component}.onnx"
    metadata["model_file"] = f"models/late_fusion/engagement_{component}.onnx"

    _write_json(metadata_path, metadata)


def _make_artifact_paths_portable() -> None:
    xgb_summary = ARTIFACT_DIR / "engagement_xgb.summary.json"
    if xgb_summary.exists():
        payload = _load_json(xgb_summary)
        payload["preprocessor_path"] = "models/late_fusion/engagement_xgb.preprocess.npz"
        _write_json(xgb_summary, payload)

    report = ARTIFACT_DIR / "late_fusion_gru_tcn_xgb_report.json"
    if report.exists():
        payload = _load_json(report)
        payload["models"] = {
            "gru": "models/late_fusion/engagement_gru.onnx",
            "tcn": "models/late_fusion/engagement_tcn.onnx",
            "xgboost": "models/late_fusion/engagement_xgb.json",
        }
        payload["xgb_summary"] = "models/late_fusion/engagement_xgb.summary.json"
        _write_json(report, payload)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy deployment-critical normalization metadata from engagement-cpu into bundled artifacts."
    )
    parser.add_argument("--engagement-repo", type=Path, default=DEFAULT_ENGAGEMENT_REPO)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_dir = args.engagement_repo / "checkpoints" / "runs" / "final_rnn_temporal_models_20260529"
    _sync_component("gru", run_dir / "rnn_gru" / "engagement_gru.pt", ARTIFACT_DIR / "engagement_gru.json")
    _sync_component("tcn", run_dir / "rnn_tcn" / "engagement_tcn.pt", ARTIFACT_DIR / "engagement_tcn.json")
    _make_artifact_paths_portable()
    print(f"Synced late-fusion metadata into {ARTIFACT_DIR}")


if __name__ == "__main__":
    main()
