from __future__ import annotations

import argparse
from pathlib import Path
import sys

import torch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from model import EngagementGRU  # noqa: E402


def export_checkpoint_to_onnx(checkpoint_path: Path, output_path: Path) -> Path:
    checkpoint = torch.load(checkpoint_path, map_location="cpu")
    if "model_state_dict" not in checkpoint:
        raise KeyError("Checkpoint missing 'model_state_dict'.")

    model_kwargs = checkpoint.get(
        "model_kwargs",
        {
            "input_size": 90,
            "hidden_size": 64,
            "num_layers": 2,
            "dropout": 0.3,
        },
    )

    if int(model_kwargs.get("input_size", 90)) != 90:
        raise ValueError(
            f"Expected input_size=90 for production pipeline, got {model_kwargs.get('input_size')}"
        )

    model = EngagementGRU(**model_kwargs)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()

    output_path.parent.mkdir(parents=True, exist_ok=True)

    dummy_input = torch.randn(1, 60, 90, dtype=torch.float32)
    torch.onnx.export(
        model,
        dummy_input,
        output_path,
        export_params=True,
        opset_version=17,
        do_constant_folding=True,
        dynamo=False,
        input_names=["input"],
        output_names=["logits"],
        dynamic_axes={
            "input": {0: "batch_size"},
            "logits": {0: "batch_size"},
        },
    )

    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export EngagementGRU checkpoint to ONNX")
    parser.add_argument(
        "--checkpoint",
        type=Path,
        default=PROJECT_ROOT / "train_2" / "engagement_gru.pt",
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
    args = parse_args()
    exported = export_checkpoint_to_onnx(args.checkpoint, args.output)
    print(f"Exported ONNX model to: {exported}")


if __name__ == "__main__":
    main()
