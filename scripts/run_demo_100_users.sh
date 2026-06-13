#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env}"
PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.venv/bin/python}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Missing env file: $ENV_FILE" >&2
  exit 1
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="$(command -v python3)"
fi

if [[ -z "${PYTHON_BIN:-}" ]]; then
  echo "Could not find a Python interpreter" >&2
  exit 1
fi

set -a
source "$ENV_FILE"
set +a

if [[ -z "${FOCUSFLOW_CLOUD_API_URL:-}" ]]; then
  echo "FOCUSFLOW_CLOUD_API_URL is not set" >&2
  exit 1
fi

if [[ -z "${FOCUSFLOW_CLOUD_API_KEY:-}" ]]; then
  echo "FOCUSFLOW_CLOUD_API_KEY is not set" >&2
  exit 1
fi

MANIFEST_PATH="${MANIFEST_PATH:-/tmp/focusflow-video-manifest.json}"
STREAM_INTERVAL_SECONDS="${STREAM_INTERVAL_SECONDS:-1.0}"
PLAYBACK_SPEED="${PLAYBACK_SPEED:-1.0}"
VIDEO_INPUT_DIR="${VIDEO_INPUT_DIR:-$ROOT_DIR/demo/Data}"
USER_MANIFEST_PATH="${USER_MANIFEST_PATH:-/tmp/focusflow-user-manifest.json}"
RESULTS_DIR="${RESULTS_DIR:-/tmp/focusflow-demo-results}"
VIDEO_LIMIT="${VIDEO_LIMIT:-100}"
STAGES="${STAGES:-100:10}"

echo "Using Python: $PYTHON_BIN"
echo "API URL:      $FOCUSFLOW_CLOUD_API_URL"
echo "Video input:  $VIDEO_INPUT_DIR"
echo "Manifest:     $MANIFEST_PATH"
echo "Stream intvl: $STREAM_INTERVAL_SECONDS"
echo "Playback spd: $PLAYBACK_SPEED"
echo "Users file:   $USER_MANIFEST_PATH"
echo "Results:      $RESULTS_DIR"
echo "Stages:       $STAGES"

echo "Checking /readyz ..."
curl -fsS "$FOCUSFLOW_CLOUD_API_URL/readyz"
echo

echo "Selecting focus/distracted mix videos ..."
"$PYTHON_BIN" "$ROOT_DIR/scripts/select_focus_demo_videos.py" \
  --input "$VIDEO_INPUT_DIR" \
  --limit "$VIDEO_LIMIT" \
  --output "$MANIFEST_PATH"

echo "Building user manifest ..."
"$PYTHON_BIN" -m demo.seed_users \
  --count "$VIDEO_LIMIT" \
  --output "$USER_MANIFEST_PATH"

echo "Running scale replay ..."
rm -rf "$RESULTS_DIR"
"$PYTHON_BIN" -m demo.run_scale \
  --stages "$STAGES" \
  --stream-interval-seconds "$STREAM_INTERVAL_SECONDS" \
  --playback-speed "$PLAYBACK_SPEED" \
  --manifest "$MANIFEST_PATH" \
  --users-manifest "$USER_MANIFEST_PATH" \
  --output "$RESULTS_DIR"

echo "Done."
echo "Dashboard: $FOCUSFLOW_CLOUD_API_URL/dashboard"
