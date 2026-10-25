#!/usr/bin/env bash
# Verify the frozen OSM snapshot checksum and that the task inputs exist.
set -euo pipefail

cd "$(dirname "$0")/.."

SNAPSHOT=data/raw/osm/dolnoslaskie_2026-10-23.osm.pbf
SHA256=4b708241a7b9af4170e8dc2c11ba94b86154791a6d5f437b6bf27d5a5f4689db
INPUTS=(
  data/interim/wroclaw_r123.osm.pbf
  data/interim/kbr_points.gpkg
  config/scope.yaml
)

if [[ ! -f "$SNAPSHOT" ]]; then
  echo "ERROR: missing $SNAPSHOT" >&2
  exit 1
fi
echo "$SHA256  $SNAPSHOT" | sha256sum -c - || { echo "ERROR: snapshot checksum mismatch" >&2; exit 1; }

for f in "${INPUTS[@]}"; do
  if [[ ! -f "$f" ]]; then
    echo "ERROR: missing $f" >&2
    exit 1
  fi
  echo "OK: $f"
done
