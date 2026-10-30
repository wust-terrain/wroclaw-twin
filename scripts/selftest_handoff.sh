#!/usr/bin/env bash
# Task 02d: end-to-end test of a handoff as a rater sees it: plain clone at a tag or commit (no working-tree overlay),
# unzip handoff/handoff_<R>.zip, uv sync --only-group pilot, scripts/check_setup.sh <R>. Prints one PASS/FAIL line.
# Usage: scripts/selftest_handoff.sh <tag-or-commit> <R1|R2>
# The clone also fetches all refs of this repository, so tags and commits of local branches resolve. Uses the uv cache; with
# UV_OFFLINE=1 nothing is downloaded. The temporary directory is removed unless KEEP=1.
set -uo pipefail
REV="${1:-}"; R="${2:-}"
[ -n "$REV" ] && { [ "$R" = R1 ] || [ "$R" = R2 ]; } || { echo "Usage: $0 <tag-or-commit> <R1|R2>" >&2; exit 64; }
SRC="$(cd "$(dirname "$0")/.." && pwd)"
ZIP="$SRC/handoff/handoff_$R.zip"; [ -f "$ZIP" ] || { echo "FAIL $R @ $REV: $ZIP not found (scripts/make_handoff.sh $R)"; exit 1; }
T="$(mktemp -d)"; [ "${KEEP:-0}" = 1 ] || trap 'rm -rf "$T"' EXIT
fail() {
  cp "$T/selftest.log" "${TMPDIR:-/tmp}/selftest_$R.log" 2>/dev/null
  echo "FAIL $R @ $REV: $1 (log: ${TMPDIR:-/tmp}/selftest_$R.log)"; exit 1; }
L="$T/selftest.log"
git clone -q --no-checkout "$SRC" "$T/repo" >>"$L" 2>&1 || fail "clone"
cd "$T/repo" || fail "cd"
git fetch -q origin '+refs/*:refs/selftest/*' >>"$L" 2>&1 || fail "fetch refs"
git checkout -q "$REV" >>"$L" 2>&1 || fail "checkout"
for f in scripts/check_setup.sh scripts/submit_edits.sh; do [ -f "$f" ] || fail "$f is not in the commit (not committed yet?)"; done
unzip -q -o "$ZIP" >>"$L" 2>&1 || fail "unzip"
sha256sum -c SHA256SUMS >>"$L" 2>&1 || fail "SHA256SUMS of the zip"
uv sync --only-group pilot >>"$L" 2>&1 || fail "uv sync --only-group pilot"
scripts/check_setup.sh "$R" >"$T/check.txt" 2>&1; RC=$?
cat "$T/check.txt" >>"$L"
P=$(grep -c '^PASS' "$T/check.txt"); W=$(grep -c '^WARN' "$T/check.txt"); F=$(grep -c '^FAIL' "$T/check.txt")
if [ $RC -eq 0 ]; then echo "PASS $R @ $REV ($(git rev-parse --short HEAD)): check_setup $P PASS, $W WARN, $F FAIL; dry run ok"
else grep '^FAIL' "$T/check.txt"; fail "check_setup.sh exit $RC ($P PASS, $W WARN, $F FAIL)"; fi
