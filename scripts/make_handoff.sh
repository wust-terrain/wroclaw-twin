#!/usr/bin/env bash
# Task 02d: build handoff/handoff_<R>.zip for a pilot rater (data that is not in git) and copy the JOSM jar to handoff/.
# Reproducible: the content list and SHA256SUMS are identical between runs (the zip bytes are not guaranteed to be).
# Usage: scripts/make_handoff.sh <R1|R2>      (R1 = zone 3, visitor zone 4; R2 = zone 4, visitor zone 3)
# Unzip into the repository root, then run scripts/check_setup.sh <R>.
set -euo pipefail
R="${1:-}"
case "$R" in R1) OWN=3; VIS=4;; R2) OWN=4; VIS=3;; *) echo "Usage: $0 <R1|R2>" >&2; exit 64;; esac
cd "$(dirname "$0")/.."
Z=data/derived/zones_v02
FILES=()
for s in .osm .json _reference.osm .geojson _units.csv _seams.csv _bridges.csv _bridge_ways.csv; do FILES+=("$Z/zone_$OWN/zone_$OWN$s"); done
for s in .osm .json _reference.osm .geojson; do FILES+=("$Z/zone_$VIS/zone_$VIS$s"); done
FILES+=("$Z/ownership_ways.csv" "$Z/ownership_nodes.csv" "$Z/ownership_relations.csv" "$Z/shared_editable_nodes.csv")
FILES+=("data/interim/ring1_roads.osm")   # full base read by src/21_ownership_check.py (config/21_ownership_check.yaml)
for f in README.md units_$R.xlsx pilot_areas_zone_3.osm pilot_areas_zone_4.osm; do FILES+=("data/derived/pilot_kit/$R/$f"); done
for f in "${FILES[@]}"; do [ -f "$f" ] || { echo "missing: $f" >&2; exit 1; }; done

W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
printf '1. Unzip this archive into the repository root (paths are preserved): unzip -o handoff_%s.zip\n2. Run scripts/check_setup.sh %s\n3. Then read docs/pilot/protocol.md\n' "$R" "$R" > "$W/HANDOFF_README.txt"
mapfile -t SORTED < <(printf '%s\n' "${FILES[@]}" | LC_ALL=C sort)
( sha256sum "${SORTED[@]}"; cd "$W" && sha256sum HANDOFF_README.txt ) | LC_ALL=C sort -k2 > "$W/SHA256SUMS"
mkdir -p handoff; OUT="$PWD/handoff/handoff_$R.zip"; rm -f "$OUT"
cp "$W/SHA256SUMS" handoff/SHA256SUMS_$R
touch -d "2000-01-01 00:00:00" "$W/HANDOFF_README.txt" "$W/SHA256SUMS"
zip -X -q "$OUT" "${SORTED[@]}"
( cd "$W" && zip -X -q "$OUT" HANDOFF_README.txt SHA256SUMS )
JAR="${JOSM_JAR:-$HOME/tools/josm-tested.jar}"
[ -f "$JAR" ] || { echo "JOSM jar not found: $JAR (set JOSM_JAR)" >&2; exit 1; }
cp "$JAR" handoff/josm-tested.jar
echo "handoff/josm-tested.jar sha256 $(sha256sum handoff/josm-tested.jar | cut -d' ' -f1) (pinned in docs/pilot/josm.sha256: $(cut -d' ' -f1 docs/pilot/josm.sha256))"
echo "$OUT ($(du -h "$OUT" | cut -f1), ${#SORTED[@]} data files + SHA256SUMS + HANDOFF_README.txt)"
