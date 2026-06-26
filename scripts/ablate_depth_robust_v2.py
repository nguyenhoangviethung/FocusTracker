from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


RAW_DIM = 168
ENRICHED_DIM = RAW_DIM * 3
SEQUENCE_LENGTH = 30
GROUP_SLICES = {
    "geometry": slice(0, 25),
    "canonical_landmarks": slice(25, 100),
    "blendshapes": slice(100, 152),
    "transform": slice(152, 168),
}


def parse_groups(value: str) -> list[str]:
    groups = [item.strip() for item in value.split(",") if item.strip()]
    invalid = sorted(set(groups) - set(GROUP_SLICES))
    if invalid:
        raise argparse.ArgumentTypeError(f"Unknown feature groups: {', '.join(invalid)}")
    if not groups:
        raise argparse.ArgumentTypeError("Select at least one feature group to mask.")
    return groups


def mask_groups(sequence: np.ndarray, groups: list[str]) -> np.ndarray:
    values = np.asarray(sequence, dtype=np.float32).copy()
    if values.shape != (SEQUENCE_LENGTH, ENRICHED_DIM):
        raise ValueError(f"Expected {(SEQUENCE_LENGTH, ENRICHED_DIM)}, got {values.shape}")
    for group in groups:
        raw = GROUP_SLICES[group]
        for offset in (0, RAW_DIM, RAW_DIM * 2):
            values[:, offset + raw.start : offset + raw.stop] = 0.0
    return values


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a depth_robust_v2 ablation manifest while preserving the original data split."
    )
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--drop", type=parse_groups, required=True, help="Comma-separated feature groups to zero.")
    args = parser.parse_args()

    manifest = pd.read_csv(args.manifest)
    if "feature_path" not in manifest:
        raise SystemExit("Manifest must contain feature_path.")
    output_features = args.output_dir / "features"
    output_features.mkdir(parents=True, exist_ok=True)

    rows = []
    for index, row in manifest.iterrows():
        source = Path(str(row["feature_path"]))
        sequence = np.load(source, allow_pickle=False)
        ablated = mask_groups(sequence, args.drop)
        destination = output_features / f"{index:07d}_{source.name}"
        np.save(destination, ablated)
        updated = row.to_dict()
        updated["source_feature_path"] = str(source)
        updated["feature_path"] = str(destination)
        updated["ablation_drop_groups"] = ",".join(args.drop)
        rows.append(updated)

    output_manifest = args.output_dir / "feature_manifest.csv"
    pd.DataFrame(rows).to_csv(output_manifest, index=False)
    print(f"Created {len(rows)} ablated sequences: {output_manifest}")


if __name__ == "__main__":
    main()
