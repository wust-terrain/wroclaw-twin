#!/usr/bin/env bash
# Task 02d: setup check for a pilot rater. Prints a PASS/FAIL table, exits 1 on any FAIL. Needs neither netconvert nor SUMO.
# Usage: scripts/check_setup.sh [R1|R2]      (R1 = zone 3, visitor zone 4; R2 = zone 4, visitor zone 3; default R1)
# JOSM_JAR overrides the jar (default ~/tools/josm-tested.jar), as in scripts/josm_pilot.sh.
set -uo pipefail
R="${1:-R1}"
case "$R" in R1) OWN=3; VIS=4;; R2) OWN=4; VIS=3;; *) echo "Usage: $0 [R1|R2]" >&2; exit 64;; esac
cd "$(dirname "$0")/.."
JOSM_JAR="${JOSM_JAR:-$HOME/tools/josm-tested.jar}"
Z=data/derived/zones_v02; KIT=data/derived/pilot_kit/$R
FAILS=0
row() { # status name detail
  printf '%-5s %-34s %s\n' "$1" "$2" "$3"; [ "$1" = FAIL ] && FAILS=$((FAILS+1)); return 0; }
check() { # name detail command...
  local n="$1" d="$2"; shift 2
  if "$@" >/dev/null 2>&1; then row PASS "$n" "$d"; else row FAIL "$n" "$d"; fi; }

printf '%-5s %-34s %s\n' STATUS CHECK DETAIL
check "repository root" "$PWD" test -d .git -a -f pyproject.toml -a -f scripts/submit_edits.sh
TAGF=docs/pilot/pilot_tag.txt
TAG="$(grep -v '^[[:space:]]*\(#\|$\)' "$TAGF" 2>/dev/null | head -1 | tr -d '[:space:]')"
if [ -z "$TAG" ]; then row WARN "pilot tag" "$TAGF missing or empty (git fetch --tags; ask the project owner)"
elif ! git rev-parse -q --verify "refs/tags/$TAG^{commit}" >/dev/null; then row FAIL "pilot tag" "tag '$TAG' not found: run git fetch --tags"
elif git merge-base --is-ancestor "$TAG" HEAD; then row PASS "pilot tag" "$TAG; HEAD $(git rev-parse --short HEAD) is the tag or a descendant"
else row FAIL "pilot tag" "HEAD $(git rev-parse --short HEAD) does not contain tag $TAG: git fetch --tags && git checkout $TAG"; fi
if command -v uv >/dev/null; then row PASS "uv" "$(uv --version)"; else row FAIL "uv" "not found"; fi
PYV="$(uv run --no-sync python -c 'import sys; print(sys.version.split()[0])' 2>&1 | tail -1)"
[[ "$PYV" =~ ^3\.[0-9]+\.[0-9]+$ ]] && row PASS "python (uv environment)" "$PYV" || row FAIL "python (uv environment)" "run: uv sync --group pilot ($PYV)"
for m in yaml pyproj shapely; do
  check "import $m" "needed by src/19, 21, 27" uv run --no-sync python -c "import $m"
done
check "stdlib imports" "argparse csv hashlib json xml.etree" uv run --no-sync python -c "import argparse, csv, hashlib, json, xml.etree.ElementTree"
OV="$(osmium --version 2>/dev/null | head -1)"
[[ "$OV" == *"osmium version 1.16.0"* ]] && row PASS "osmium 1.16.0" "$OV" || row FAIL "osmium 1.16.0" "'${OV:-not found}'"
JV="$(java -version 2>&1 | head -1)"
[[ "$JV" == *'"21.'* ]] && row PASS "java 21" "$JV" || row FAIL "java 21" "'${JV:-not found}'"
if [ ! -s "$JOSM_JAR" ]; then row FAIL "JOSM jar" "not found: $JOSM_JAR"
else
  JW="$(cut -d' ' -f1 docs/pilot/josm.sha256 2>/dev/null)"; JH="$(sha256sum "$JOSM_JAR" | cut -d' ' -f1)"
  [ -n "$JW" ] && [ "$JW" = "$JH" ] && row PASS "JOSM jar (pinned, 19613)" "$JOSM_JAR" || row FAIL "JOSM jar (pinned, 19613)" "sha256 ${JH:0:16}... differs from docs/pilot/josm.sha256; other JOSM versions are untested; take the jar from the handoff"
fi
check "scripts/josm_pilot.sh executable" "" test -x scripts/josm_pilot.sh

zone_pkg() { # zone label
  local z="$1" l="$2" d="$Z/zone_$1" want have
  want="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("sha256_extract",""))' "$d/zone_$z.json" 2>/dev/null)"
  have="$(sha256sum "$d/zone_$z.osm" 2>/dev/null | cut -d' ' -f1)"
  if [ -n "$want" ] && [ "$want" = "$have" ]; then row PASS "$l package sha256 (zone $z)" "${have:0:16}..."
  else row FAIL "$l package sha256 (zone $z)" "package missing or differs from its sidecar"; fi
}
zone_pkg $OWN own
for f in zone_${OWN}_reference.osm zone_${OWN}.geojson zone_${OWN}_units.csv zone_${OWN}_seams.csv zone_${OWN}_bridges.csv; do
  check "file $f" "" test -s "$Z/zone_$OWN/$f"; done
check "file pilot_areas_zone_$OWN.osm" "" test -s "$KIT/pilot_areas_zone_$OWN.osm"
check "kit units_$R.xlsx" "" test -s "$KIT/units_$R.xlsx"
for f in ownership_ways.csv ownership_nodes.csv ownership_relations.csv shared_editable_nodes.csv; do
  check "file $f" "" test -s "$Z/$f"; done
check "file data/interim/ring1_roads.osm" "full base, config/21_ownership_check.yaml" test -s data/interim/ring1_roads.osm
zone_pkg $VIS visitor
check "file zone_${VIS}_reference.osm" "visitor zone" test -s "$Z/zone_$VIS/zone_${VIS}_reference.osm"

# dry run on an unchanged copy of the own package
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT
if [ -f "$Z/zone_$OWN/zone_$OWN.osm" ]; then
  cp "$Z/zone_$OWN/zone_$OWN.osm" "$T/zone_${OWN}_edit.osm"
  OUT="$(scripts/submit_edits.sh "$OWN" "$T/zone_${OWN}_edit.osm" --dry-run 2>&1)"; RC=$?
  if [ $RC -eq 0 ] && grep -q "changed objects: 0)" <<<"$OUT"; then row PASS "dry run submit_edits.sh $OWN" "changed objects: 0, exit 0"
  else row FAIL "dry run submit_edits.sh $OWN" "exit $RC; last line: $(tail -1 <<<"$OUT")"; fi
else row FAIL "dry run submit_edits.sh $OWN" "package missing"; fi

echo; [ $FAILS -eq 0 ] && echo "ALL CHECKS PASSED ($R)" || echo "$FAILS CHECK(S) FAILED ($R)"
[ $FAILS -eq 0 ]
