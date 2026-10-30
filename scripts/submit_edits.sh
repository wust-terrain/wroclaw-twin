#!/usr/bin/env bash
# Task 02c': submit the edits of one zone: verify the package, derive the change file, check the ownership, print a summary.
# Usage: scripts/submit_edits.sh <zone> <edited.osm> [--dry-run]
# Writes submissions/<zone dir>/<YYYYMMDD>/zone_<N>.osc and zone_<N>.osc.meta.json (SUBMISSIONS_DIR overrides `submissions`);
# The meta file gets `created_utc` (UTC time of the submission; informational).
# --dry-run runs everything in a temporary directory and writes no .osc. ZONES_DIR overrides data/derived/zones_v02.
# The editor index is the zone number. Nothing is downloaded.
# Exit codes (docs/workflow/osm_editing.md): 0 ok, 1 violation, 2 warnings only, 3 contaminated input (nothing written),
# 4 package does not match its sidecar / base mismatch; 64 usage error or missing file; 70 unexpected failure of a step.
set -uo pipefail

usage() { echo "Usage: $0 <zone> <edited.osm> [--dry-run]" >&2; exit 64; }
[ $# -ge 2 ] && [ $# -le 3 ] || usage
ZONE="$1"; EDITED="$2"; DRY=0
[[ "$ZONE" =~ ^[0-9]+$ ]] || usage
if [ $# -eq 3 ]; then [ "$3" = "--dry-run" ] && DRY=1 || usage; fi
[ -f "$EDITED" ] || { echo "edited file not found: $EDITED" >&2; exit 64; }
EDITED="$(realpath "$EDITED")"

cd "$(dirname "$0")/.."
PKG_DIR="${ZONES_DIR:-data/derived/zones_v02}/zone_${ZONE}"
PKG="$PKG_DIR/zone_${ZONE}.osm"; SIDE="$PKG_DIR/zone_${ZONE}.json"
[ -f "$PKG" ] && [ -f "$SIDE" ] || { echo "package or sidecar not found: $PKG, $SIDE" >&2; exit 64; }

WANT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8")).get("sha256_extract", ""))' "$SIDE")"
HAVE="$(sha256sum "$PKG" | cut -d' ' -f1)"
if [ -z "$WANT" ] || [ "$WANT" != "$HAVE" ]; then
  echo "package sha256 mismatch: $PKG is $HAVE, $SIDE says '$WANT'. Use the unchanged package of your zone." >&2
  exit 4
fi
echo "package ok: $PKG (sha256 ${HAVE:0:12}...)"

mkdir -p logs
LOG="logs/submit_edits_zone_${ZONE}.log"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
if [ "$DRY" -eq 1 ]; then
  OUTDIR="$TMP/out"
else
  OUTDIR="${SUBMISSIONS_DIR:-submissions}/zone_${ZONE}/$(date +%Y%m%d)"
fi
mkdir -p "$OUTDIR"
OSC="$OUTDIR/zone_${ZONE}.osc"

uv run --no-sync python src/19_osm_submit.py "$PKG" "$EDITED" "$OSC" --editor-index "$ZONE" > "$LOG" 2>&1
RC=$?
grep -E "prepare:|renumbered" "$LOG" | sed 's/^[0-9-]* [0-9:,]* INFO /  /'
if [ $RC -eq 3 ] || [ $RC -eq 4 ]; then
  echo "submit refused (exit $RC); nothing written:" >&2
  grep -E "ERROR" "$LOG" | sed 's/^[0-9-]* [0-9:,]* //' >&2
  exit $RC
elif [ $RC -ne 0 ]; then
  echo "19_osm_submit.py failed (exit $RC), see $LOG" >&2
  exit 70
fi

# informational time stamp for the intake (scripts/intake_submission.sh); the merge ignores it
python3 - "$OSC.meta.json" <<'PY'
import datetime, json, sys
p = sys.argv[1]
m = json.load(open(p, encoding="utf-8"))
m["created_utc"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
open(p, "w", encoding="utf-8").write(json.dumps(m, indent=1, sort_keys=True))
PY

uv run --no-sync python src/21_ownership_check.py --editor "zone_${ZONE}" "$ZONE" "$OSC" "$PKG" --json "$TMP/rows.json" >> "$LOG" 2>&1
RC=$?
if [ $RC -eq 4 ]; then echo "ownership check: .osc derived against another base (exit 4), see $LOG" >&2; exit 4; fi
if [ $RC -gt 2 ] || [ ! -f "$TMP/rows.json" ]; then echo "21_ownership_check.py failed (exit $RC), see $LOG" >&2; exit 70; fi
uv run --no-sync python src/27_submit_summary.py "$TMP/rows.json"

if [ "$DRY" -eq 1 ]; then
  echo "dry run: no .osc written."
else
  echo "written: $OSC and $OSC.meta.json (log: $LOG)"
fi
exit $RC
