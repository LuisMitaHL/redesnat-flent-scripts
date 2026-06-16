#!/bin/bash
set -euo pipefail
shopt -s nullglob

for flent_file in ./*.flent ./*.flent.gz; do
    base="${flent_file%.flent.gz}"
    base="${base%.flent}"
    csv_file="${base}.csv"

    if [ -f "$csv_file" ]; then
        echo "SKIP: $csv_file already exists"
    else
        echo "EXPORT: $flent_file -> $csv_file"
        flent -i "$flent_file" -f csv -o "$csv_file"
    fi
done
