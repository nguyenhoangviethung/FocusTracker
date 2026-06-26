#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source_dir="${repo_root}/docs/uml"
output_dir="${source_dir}/rendered"
thesis_img_dir="${repo_root}/../Thesis/SOICT_DATN_Base/Hinhve/focusflow"

mkdir -p "${output_dir}"

for source in "${source_dir}"/*.mmd; do
    name="$(basename "${source}" .mmd)"
    if command -v mmdc >/dev/null 2>&1; then
        mmdc --input "${source}" --output "${output_dir}/${name}.svg" \
            --backgroundColor transparent
        mmdc --input "${source}" --output "${output_dir}/${name}.png" \
            --backgroundColor white --scale 2
    else
        # Kroki keeps the workflow dependency-free when Mermaid CLI is absent.
        curl --fail --silent --show-error \
            --header "Content-Type: text/plain" \
            --data-binary "@${source}" \
            "https://kroki.io/mermaid/svg" \
            --output "${output_dir}/${name}.svg"
        curl --fail --silent --show-error \
            --header "Content-Type: text/plain" \
            --data-binary "@${source}" \
            "https://kroki.io/mermaid/png" \
            --output "${output_dir}/${name}.png"
    fi
done

printf 'Rendered UML assets to %s\n' "${output_dir}"

# If thesis directory exists, sync the PNGs to it
if [ -d "${thesis_img_dir}" ]; then
    cp "${output_dir}"/*.png "${thesis_img_dir}/"
    printf 'Synced rendered PNGs to thesis directory: %s\n' "${thesis_img_dir}"
fi

