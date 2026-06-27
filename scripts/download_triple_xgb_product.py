from __future__ import annotations

import argparse
import os
import shutil
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

from dotenv import dotenv_values


REPO_ID = "Hnug/daisee-processed"
ARTIFACT_PATH = "checkpoints/runs/triple_xgb_depth_robust_target_band_product.zip"
DEFAULT_OUTPUT = Path("models/triple_xgb_depth_robust_target_band_product")


def _load_token() -> str:
    env = dotenv_values(".env")
    token = (
        os.getenv("HF_KEY")
        or os.getenv("HF_TOKEN")
        or os.getenv("HUGGINGFACE_HUB_TOKEN")
        or env.get("HF_KEY")
        or env.get("HF_TOKEN")
        or env.get("HUGGINGFACE_HUB_TOKEN")
        or ""
    )
    return str(token).strip()


def _download(url: str, destination: Path, token: str) -> None:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    request = Request(url, headers=headers)
    with urlopen(request, timeout=180) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the FocusFlow Triple XGB product artifact.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--zip-path", type=Path, default=Path("/tmp/triple_xgb_depth_robust_target_band_product.zip"))
    args = parser.parse_args()

    token = _load_token()
    url = f"https://huggingface.co/datasets/{REPO_ID}/resolve/main/{ARTIFACT_PATH}"
    args.zip_path.parent.mkdir(parents=True, exist_ok=True)
    _download(url, args.zip_path, token)

    if args.output.exists():
        shutil.rmtree(args.output)
    args.output.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.zip_path) as archive:
        archive.extractall(args.output)

    required = [
        "fusion_config.json",
        "summary.json",
        "final_xgb/model.json",
        "boost_xgb/model.json",
        "targeted_xgb/model.json",
    ]
    missing = [name for name in required if not (args.output / name).exists()]
    if missing:
        raise SystemExit(f"Downloaded artifact is incomplete: {missing}")

    print(f"Triple XGB product artifact installed at {args.output}")


if __name__ == "__main__":
    main()
