"""Readable summary of the --json output of 21_ownership_check.py (used by scripts/submit_edits.sh).

Usage: uv run python src/27_submit_summary.py ROWS.json
Prints the counts ok / warning / violation and, for every warning and violation, the object, what was changed and a one-line reason.
"""
import collections
import json
import pathlib
import sys

rows = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
count = collections.Counter(r["severity"] for r in rows)
print(f"ownership check: ok {count['ok']}, warning {count['warning']}, violation {count['violation']} (changed objects: {len(rows)})")
for sev in ("violation", "warning"):
    sub = [r for r in rows if r["severity"] == sev]
    if not sub:
        continue
    print(f"\n{sev.upper()}S ({len(sub)}):")
    for r in sub:
        what = f"{r['op']}: {r['detail']}"
        print(f"  {r['type']} {r['id']}  |  {what}  |  {r['category']}: {r['reason']}")
