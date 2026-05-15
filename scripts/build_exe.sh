#!/usr/bin/env bash
set -euo pipefail

# Build one-file desktop executable using the prepared spec.
pyinstaller --noconfirm --clean focusflow_app.spec

echo "Build complete. Output is in dist/FocusFlowAI" 
