#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${project_root}"

python_bin="${PYTHON:-${project_root}/.venv/bin/python}"
test -s "${project_root}/models/triple_xgb_depth_robust_maxacc_product/fusion_config.json" || {
  echo "Missing models/triple_xgb_depth_robust_maxacc_product. Run scripts/download_triple_xgb_product.py first." >&2
  exit 1
}
"${python_bin}" -m PyInstaller --noconfirm --clean focusflow_app.spec

mkdir -p release
rm -f release/FocusFlowAI-Linux.tar.gz
tar -C dist -czf release/FocusFlowAI-Linux.tar.gz FocusFlowAI

(
  cd release
  sha256sum FocusFlowAI-Linux.tar.gz > SHA256SUMS.txt
)

echo "Linux release package written to release/FocusFlowAI-Linux.tar.gz"
echo "Checksum written to release/SHA256SUMS.txt"
