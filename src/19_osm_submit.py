"""Task 04s/04r: turn a JOSM-saved .osm into a change file that can be merged with other editors' files.

Steps: check the base (sha256 from the sidecar), refuse contaminated input, drop action='delete' objects,
bump the version of changed objects, osmium sort, osmium derive-changes, map negative ids to positive ones above every
real OSM id (per-editor block). Writes OUT.osc and OUT.osc.meta.json (base / edited sha256, stats).

Usage: uv run python src/19_osm_submit.py BASE.osm EDITED.osm OUT.osc --editor-index I [--offset N | --no-renumber | --keep-negative]
       [--base-sidecar BASE.json | --base-sha256 HEX] [--config config/17_workflow_spike.yaml]
Exit codes: 0 ok, 3 contaminated input (nothing written), 4 base mismatch or base not verifiable (nothing written).
"""
import argparse
import hashlib
import json
import logging
import pathlib
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import osm_io  # noqa: E402

log = logging.getLogger("submit")
TYPES = osm_io.TYPES
SERVER_ATTRS = ("uid", "user", "changeset")
EXIT_CONTAMINATED, EXIT_BASE = 3, 4


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def expected_base_sha(base_path, sidecar, explicit):
    """sha256 the base must have: explicit value, else the sidecar `sha256_extract` (default: BASE with .json), else None."""
    if explicit:
        return explicit, "--base-sha256"
    sc = pathlib.Path(sidecar) if sidecar else pathlib.Path(base_path).with_suffix(".json")
    if sc.exists():
        return json.loads(sc.read_text(encoding="utf-8")).get("sha256_extract"), str(sc)
    return None, str(sc)


def detect_contamination(base_objs, edited_objs):
    """Objects in the edited file that cannot come from an offline edit of the base.

    Rules: (1) uid / user / changeset that the base object lacks, (2) visible='false', (3) an existing object whose
    version differs from the base, (4) a positive-id object that is not in the base. The user name is never used.
    """
    bad = {"server_metadata": [], "invisible": [], "version_differs": [], "not_in_base": []}
    for key, el in edited_objs.items():
        b = base_objs.get(key)
        if any(a in el.attrib and (b is None or a not in b.attrib) for a in SERVER_ATTRS):
            bad["server_metadata"].append(key)
        if el.get("visible") == "false":
            bad["invisible"].append(key)
        if key[1] > 0:
            if b is None:
                bad["not_in_base"].append(key)
            elif el.get("version") != b.get("version"):
                bad["version_differs"].append(key)
    return bad


def prepare(base_objs, edited_root, out_path):
    """Write EDITED without deleted objects and with version = base version + 1 on changed objects."""
    stats = {"deleted_dropped": 0, "bumped": 0, "new": 0}
    for el in list(edited_root):
        if el.tag not in TYPES:
            continue
        if el.get("action") == "delete":
            edited_root.remove(el)
            stats["deleted_dropped"] += 1
            continue
        i = int(el.get("id"))
        if i < 0:
            stats["new"] += 1            # JOSM writes new objects with action='modify' and no version
            continue
        b = base_objs.get((el.tag, i))
        if b is not None and osm_io.canon(b) != osm_io.canon(el):
            el.set("version", str(int(b.get("version")) + 1))
            stats["bumped"] += 1
    ET.ElementTree(edited_root).write(out_path, encoding="UTF-8", xml_declaration=True)
    return stats


def renumber(osc_in, osc_out, shift, keep_negative=False):
    """Map every negative id n (object ids and nd/member refs) to shift - n (positive), or to n - shift."""
    tree = ET.parse(osc_in)
    n = 0
    for el in tree.iter():
        attr = "id" if el.tag in TYPES else "ref" if el.tag in ("nd", "member") else None
        if attr and int(el.get(attr)) < 0:
            i = int(el.get(attr))
            el.set(attr, str(i - shift if keep_negative else shift - i))
            n += 1
    ET.indent(tree.getroot(), space="  ")
    tree.write(osc_out, encoding="UTF-8", xml_declaration=True)
    return n


def run(cmd):
    log.info("$ %s", " ".join(cmd))
    subprocess.run(cmd, check=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("base")
    ap.add_argument("edited")
    ap.add_argument("out")
    ap.add_argument("--editor-index", type=int, required=True, help="0 for the first editor, 1 for the second, ...")
    ap.add_argument("--offset", type=int, help="per-editor id offset (default: renumber_offset from the config)")
    ap.add_argument("--no-renumber", action="store_true")
    ap.add_argument("--keep-negative", action="store_true", help="shift ids further negative instead of making them positive")
    ap.add_argument("--base-sidecar", help="JSON with sha256_extract (default: BASE with the suffix .json)")
    ap.add_argument("--base-sha256", help="expected sha256 of BASE (when there is no sidecar)")
    ap.add_argument("--config", default="config/17_workflow_spike.yaml")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    offset = a.offset or yaml.safe_load(open(a.config, encoding="utf-8"))["renumber_offset"]
    # (a) base check
    want, src = expected_base_sha(a.base, a.base_sidecar, a.base_sha256)
    have = sha256_file(a.base)
    if want is None:
        log.error("base not verifiable: no sidecar %s and no --base-sha256; refusing", src)
        sys.exit(EXIT_BASE)
    if want != have:
        log.error("base mismatch: %s has sha256 %s, %s says %s; refusing", a.base, have, src, want)
        sys.exit(EXIT_BASE)
    # contamination check
    base = osm_io.read_osm(a.base)["objs"]
    edited = osm_io.read_osm(a.edited)
    bad = detect_contamination(base, edited["objs"])
    if any(bad.values()):
        log.error("contaminated input (data from the OSM server, or another base): %s", {k: len(v) for k, v in bad.items()})
        for rule, keys in bad.items():
            for t, i in sorted(keys):
                log.error("  %s: %s %d (action=%s)", rule, t, i, edited["objs"][(t, i)].get("action"))
        log.error("no .osc written. Never use File > Update data or Download; redo the edits on a fresh copy of the package.")
        sys.exit(EXIT_CONTAMINATED)
    with tempfile.TemporaryDirectory() as td:
        prep, srt = pathlib.Path(td) / "prep.osm", pathlib.Path(td) / "sorted.osm"
        stats = prepare(base, edited["root"], prep)
        log.info("prepare: %s", stats)
        run(["osmium", "sort", str(prep), "-o", str(srt), "--overwrite"])
        raw = pathlib.Path(td) / "raw.osc"
        run(["osmium", "derive-changes", a.base, str(srt), "-o", str(raw), "--overwrite"])
        shift = None
        if a.no_renumber:
            pathlib.Path(a.out).write_bytes(raw.read_bytes())
        else:
            shift = (a.editor_index + 1) * offset
            log.info("renumbered %d negative ids (block %d)", renumber(raw, a.out, shift, a.keep_negative), shift)
    meta = {"base": a.base, "base_sha256": have, "base_checked_against": src, "edited": a.edited, "edited_sha256": sha256_file(a.edited),
            "editor_index": a.editor_index, "renumber_shift": shift, "keep_negative": a.keep_negative, "prepare": stats}
    pathlib.Path(a.out + ".meta.json").write_text(json.dumps(meta, indent=1, sort_keys=True), encoding="utf-8")


if __name__ == "__main__":
    main()
