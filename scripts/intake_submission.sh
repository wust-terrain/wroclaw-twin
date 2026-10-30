#!/usr/bin/env bash
# Task 04m follow-up: validate the files a rater sent and place them in submissions/zone_<N>/<YYYYMMDD>/.
# Usage: scripts/intake_submission.sh <zone> <dir_with_files> [--date YYYYMMDD] [--replace] [--force]
# DIR holds zone_<N>.osc and zone_<N>.osc.meta.json (and optionally the record-sheet .xlsx, copied to <date>/records/).
# SUBMISSIONS_DIR overrides `submissions`. Exit codes: 0 placed, 1 refused (different content on the same day without --replace,
# or older than the newest submission present without --force), 4 meta does not match the zone / package, 64 usage or bad files.
set -uo pipefail
[ $# -ge 2 ] || { echo "Usage: $0 <zone> <dir_with_files> [--date YYYYMMDD] [--replace] [--force]" >&2; exit 64; }
ZONE="$1"; DIR="$(realpath -m "$2")"; shift 2
[[ "$ZONE" =~ ^[0-9]+$ ]] || { echo "zone must be a number" >&2; exit 64; }
SUB="$(realpath -m "${SUBMISSIONS_DIR:-submissions}")"
cd "$(dirname "$0")/.."
exec uv run --no-sync python src/30_intake_submission.py "$ZONE" "$DIR" --submissions "$SUB" "$@"
