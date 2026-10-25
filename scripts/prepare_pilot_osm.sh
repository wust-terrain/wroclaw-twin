#!/usr/bin/env bash
# Task 02b: cut the roads extract to the RING 1 polygon and convert it to .osm XML for JOSM (idempotent).
set -euo pipefail

cd "$(dirname "$0")/.."
mkdir -p logs
exec > >(tee -a logs/prepare_pilot_osm.log) 2>&1

scripts/verify_inputs.sh

IN=data/interim/wroclaw_roads.osm.pbf
POLY=data/derived/ring1.geojson
PBF=data/interim/ring1_roads.osm.pbf
OUT=data/interim/ring1_roads.osm

osmium extract -p "$POLY" --strategy complete_ways --overwrite -o "$PBF" "$IN"
osmium cat --overwrite -o "$OUT" "$PBF"

echo "nodes:     $(osmium fileinfo -e -g data.count.nodes "$OUT")"
echo "ways:      $(osmium fileinfo -e -g data.count.ways "$OUT")"
echo "relations: $(osmium fileinfo -e -g data.count.relations "$OUT")"
echo "size:      $(du -h "$OUT" | cut -f1) ($(stat -c %s "$OUT") bytes)"
