from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import tempfile
from urllib.error import HTTPError
from urllib.request import Request, urlopen
import zipfile

from dotenv import load_dotenv


REPOSITORY = "Hnug/daisee-processed"
ARTIFACT_PATH = "checkpoints/runs/deep_forest_product_4class.zip"
DOWNLOAD_URL = f"https://huggingface.co/datasets/{REPOSITORY}/resolve/main/{ARTIFACT_PATH}?download=true"


def _find_file(root: Path, filename: str) -> Path:
    matches = list(root.rglob(filename))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {filename} in the archive, found {len(matches)}.")
    return matches[0]


def download(output_dir: Path, token: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    request = Request(DOWNLOAD_URL, headers={"Authorization": f"Bearer {token}"})
    try:
        with urlopen(request, timeout=120) as response, tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as archive:
            shutil.copyfileobj(response, archive)
            archive_path = Path(archive.name)
    except HTTPError as exc:
        raise RuntimeError(f"Hugging Face download failed with HTTP {exc.code}.") from exc

    try:
        with tempfile.TemporaryDirectory(prefix="focusflow-deep-forest-") as temp_dir:
            extracted = Path(temp_dir)
            with zipfile.ZipFile(archive_path) as bundle:
                for member in bundle.infolist():
                    target = (extracted / member.filename).resolve()
                    if extracted not in target.parents and target != extracted:
                        raise RuntimeError("Archive contains an unsafe output path.")
                bundle.extractall(extracted)
            model = _find_file(extracted, "model.joblib")
            summary = _find_file(extracted, "summary.json")
            shutil.copy2(model, output_dir / "model.joblib")
            shutil.copy2(summary, output_dir / "summary.json")
    finally:
        archive_path.unlink(missing_ok=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download the calibrated FocusFlow DeepForest product artifact.")
    parser.add_argument("--output", type=Path, default=Path("models/deep_forest_product_4class"))
    args = parser.parse_args()
    load_dotenv()
    token = (os.getenv("HF_TOKEN") or os.getenv("HF_KEY") or "").strip()
    if not token.startswith("hf_"):
        raise SystemExit("Set HF_TOKEN or HF_KEY to a Hugging Face read token before downloading.")
    download(args.output, token)
    print(f"DeepForest product artifact installed at {args.output}")


if __name__ == "__main__":
    main()
