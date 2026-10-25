"""Task 04s: report objects touched by more than one editor in a set of .osc change files.

Usage: uv run python src/18_osm_conflicts.py A=A.osc B=B.osc [...]
Exit code 1 if there is a conflict (same object in several files, or same negative id in several files).
"""
import collections
import sys
import xml.etree.ElementTree as ET

TYPES = ("node", "way", "relation")


def touched(path):
    """{(type, id): action} for one change file."""
    out = {}
    for block in ET.parse(path).getroot():
        for el in block:
            if el.tag in TYPES:
                out[(el.tag, int(el.get("id")))] = block.tag
    return out


def conflicts(files):
    """files: {editor: path}. Returns (shared existing objects, shared negative ids) as {(type, id): [editors]}."""
    seen = collections.defaultdict(list)
    for ed, path in files.items():
        for key in touched(path):
            seen[key].append(ed)
    shared = {k: v for k, v in seen.items() if len(v) > 1}
    return ({k: v for k, v in shared.items() if k[1] > 0}, {k: v for k, v in shared.items() if k[1] < 0})


def main():
    files = dict(a.split("=", 1) for a in sys.argv[1:])
    if len(files) < 2:
        raise SystemExit(__doc__)
    objs, neg = conflicts(files)
    for title, d in (("CONFLICT: object changed by more than one editor", objs),
                     ("COLLISION: negative id used by more than one editor (renumber first)", neg)):
        for (t, i), eds in sorted(d.items()):
            print(f"{title}: {t} {i} <- {', '.join(eds)}")
    print(f"conflicts: {len(objs)}, negative-id collisions: {len(neg)}")
    sys.exit(1 if objs or neg else 0)


if __name__ == "__main__":
    main()
