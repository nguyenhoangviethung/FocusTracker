from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys

import torch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils.logger import setup_logging, get_logger
from tracking.model_spec import ModelSpec  # noqa: E402
from tracking.sequence_models import ProbabilityWrapper, build_sequence_model  # noqa: E402


logger = get_logger("export_to_onnx")


def export_checkpoint_to_onnx(checkpoint_path: Path, output_path: Path) -> Path:
    logger.info("Exporting checkpoint to ONNX (checkpoint=%s)", checkpoint_path)
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    if "model_state_dict" not in checkpoint:
        raise KeyError("Checkpoint missing 'model_state_dict'.")

    raw_model_kwargs = dict(
        checkpoint.get(
            "model_kwargs",
            {
                "input_size": 90,
                "hidden_size": 64,
                "num_layers": 2,
                "dropout": 0.3,
            },
        )
    )

    input_size = int(raw_model_kwargs.get("input_size", 90))
    sequence_length = int(
        raw_model_kwargs.get(
            "sequence_length",
            raw_model_kwargs.get("max_seq_len", 60),
        )
    )
    raw_feature_dim = int(raw_model_kwargs.get("raw_feature_dim", 30))
    enriched_feature_dim = int(raw_model_kwargs.get("feature_dim", input_size))

    if enriched_feature_dim != input_size:
        raise ValueError(
            f"Checkpoint input_size={input_size} does not match feature_dim={enriched_feature_dim}."
        )

    model_name = str(raw_model_kwargs.get("model_name", checkpoint.get("model_name", "gru"))).strip().lower()
    model_kwargs = dict(raw_model_kwargs)
    if "kernel_size" not in model_kwargs and "tcn_kernel_size" in model_kwargs:
        model_kwargs["kernel_size"] = model_kwargs["tcn_kernel_size"]

    model = build_sequence_model(**model_kwargs)
    model.load_state_dict(checkpoint["model_state_dict"], strict=True)
    model.eval()
    export_model = ProbabilityWrapper(model).eval()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    dummy_input = torch.randn(1, sequence_length, enriched_feature_dim, dtype=torch.float32)
    torch.onnx.export(
        export_model,
        dummy_input,
        output_path,
        export_params=True,
        opset_version=17,
        do_constant_folding=True,
        dynamo=False,
        input_names=["sequence"],
        output_names=["probability"],
        dynamic_axes={
            "sequence": {0: "batch"},
            "probability": {0: "batch"},
        },
    )

    metadata_path = checkpoint_path.with_suffix(".json")
    metadata: dict[str, object] = {}
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            metadata = {}

    threshold = metadata.get("best_threshold") if isinstance(metadata, dict) else None
    smoothing_window = metadata.get("smoothing_window", 5) if isinstance(metadata, dict) else 5
    spec = ModelSpec(
        model_file=output_path,
        sequence_length=sequence_length,
        raw_feature_dim=raw_feature_dim,
        enriched_feature_dim=enriched_feature_dim,
        threshold=float(threshold) if isinstance(threshold, (int, float)) else 0.55,
        smoothing_window=int(smoothing_window),
    )
    spec.save_metadata(
        extra={
            "model_name": model_name,
            "model_kwargs": model_kwargs,
            "best_threshold": threshold,
            "best_temperature": metadata.get("best_temperature", checkpoint.get("best_temperature", 1.0)),
            "prior_shift_calibration": metadata.get(
                "prior_shift_calibration",
                checkpoint.get("prior_shift_calibration", {}),
            ),
            "normalize_features": bool(checkpoint.get("normalize_features", False)),
            "feature_mean": checkpoint.get("feature_mean"),
            "feature_std": checkpoint.get("feature_std"),
            "raw_feature_dim": raw_feature_dim,
            "sequence_length": sequence_length,
            "enriched_feature_dim": enriched_feature_dim,
            "artifact_origin": "local_project_models",
        }
    )

    logger.info("Export completed (onnx=%s)", output_path)
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export EngagementGRU checkpoint to ONNX")
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=PROJECT_ROOT / "training" / "checkpoints" / "engagement_gru.pt",
        help="Path to .pt checkpoint",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "models" / "engagement_gru.onnx",
        help="Destination ONNX path",
    )
    return parser.parse_args()


def main() -> None:
    setup_logging(log_level=logging.INFO)
    args = parse_args()
    logger.info("Using checkpoint=%s output=%s", args.checkpoint, args.output)
    exported = export_checkpoint_to_onnx(args.checkpoint, args.output)
    print(f"Exported ONNX model to: {exported}")


if __name__ == "__main__":
    main()
