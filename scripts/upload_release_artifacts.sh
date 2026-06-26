#!/usr/bin/env bash
set -euo pipefail

bucket="${FOCUSFLOW_RELEASE_BUCKET:-my-thesis-496702-focusflow-releases}"
prefix="${FOCUSFLOW_RELEASE_PREFIX:-releases/latest}"
artifact_dir="${1:-release}"
destination="gs://${bucket}/${prefix}/"

required=(
  "FocusFlowAI-Windows.exe"
  "FocusFlowAI-macOS.dmg"
  "FocusFlowAI-Linux.tar.gz"
  "SHA256SUMS.txt"
)

missing=()
for name in "${required[@]}"; do
  if [[ ! -f "${artifact_dir}/${name}" ]]; then
    missing+=("${artifact_dir}/${name}")
  fi
done

if (( ${#missing[@]} > 0 )); then
  echo "Missing release artifacts:" >&2
  printf '  - %s\n' "${missing[@]}" >&2
  echo "" >&2
  echo "Build or copy the files into '${artifact_dir}' before uploading." >&2
  echo "On this Linux machine you can create the Linux package with:" >&2
  echo "  scripts/package_linux_release.sh" >&2
  exit 1
fi

gcloud storage cp "${artifact_dir}/FocusFlowAI-Windows.exe" "${destination}"
gcloud storage cp "${artifact_dir}/FocusFlowAI-macOS.dmg" "${destination}"
gcloud storage cp "${artifact_dir}/FocusFlowAI-Linux.tar.gz" "${destination}"
gcloud storage cp "${artifact_dir}/SHA256SUMS.txt" "${destination}"

echo "Uploaded release artifacts to ${destination}"
