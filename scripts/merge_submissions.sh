#!/usr/bin/env bash
# Task 04m: merge the newest cumulative submission of every zone into the full RING 1 base.
# Usage: scripts/merge_submissions.sh [--allow-violations] [--netconvert] <submissions_dir> <out_dir>
# Writes <out_dir>/ring1_roads_merged.osm, merged.osc and MERGE_REPORT.md (see docs/workflow/osm_editing.md, section "Merging").
# Exit codes: 0 ok, 1 a zone was refused (violation or conflict; the others were merged), 4 a zone was refused (meta / base / package
# mismatch), 64 usage error or nothing to merge, 70 a step failed.
set -uo pipefail
ARGS=(); DIRS=()
for a in "$@"; do
  case "$a" in
    --allow-violations|--netconvert) ARGS+=("$a");;
    -*) echo "unknown option: $a" >&2; exit 64;;
    *) DIRS+=("$(realpath -m "$a")");;
  esac
done
[ ${#DIRS[@]} -eq 2 ] || { echo "Usage: $0 [--allow-violations] [--netconvert] <submissions_dir> <out_dir>" >&2; exit 64; }
cd "$(dirname "$0")/.."
exec uv run --no-sync python src/28_merge_submissions.py "${ARGS[@]}" "${DIRS[0]}" "${DIRS[1]}"
