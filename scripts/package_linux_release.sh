#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${project_root}"

python_bin="${PYTHON:-${project_root}/.venv/bin/python}"
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
