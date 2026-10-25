"""Task 04s: turn a JOSM-saved .osm into a change file that can be merged with other editors' files.

Steps: drop action="delete" objects, bump the version of changed objects, osmium sort, osmium derive-changes,
map negative ids to positive ones above every real OSM id (per-editor block).

Usage: uv run python src/19_osm_submit.py BASE.osm EDITED.osm OUT.osc --editor-index I [--offset N | --no-renumber | --keep-negative]
       [--config config/17_workflow_spike.yaml]
"""
import argparse
import logging
import pathlib
import subprocess
import tempfile
import xml.etree.ElementTree as ET

import yaml

log = logging.getLogger("submit")
TYPES = ("node", "way", "relation")


def signature(el):
    tags = tuple(sorted((t.get("k"), t.get("v")) for t in el.findall("tag")))
    if el.tag == "node":
        return (round(float(el.get("lat")), 7), round(float(el.get("lon")), 7), tags)
    if el.tag == "way":
        return (tuple(n.get("ref") for n in el.findall("nd")), tags)
    return (tuple((m.get("type"), m.get("ref"), m.get("role")) for m in el.findall("member")), tags)


def prepare(base_path, edited_path, out_path):
    """Write EDITED without deleted objects and with version = base version + 1 on changed objects."""
    base = {}
    for _, el in ET.iterparse(base_path):
        if el.tag in TYPES:
            base[(el.tag, el.get("id"))] = (int(el.get("version", 0)), signature(el))
            el.clear()
    root = ET.parse(edited_path).getroot()
    stats = {"deleted_dropped": 0, "bumped": 0, "new": 0}
    for el in list(root):
        if el.tag not in TYPES:
            continue
        if el.get("action") == "delete":
            root.remove(el)
            stats["deleted_dropped"] += 1
            continue
        key = (el.tag, el.get("id"))
        if int(el.get("id")) < 0:
            stats["new"] += 1
            continue
        if key in base and base[key][1] != signature(el):
            el.set("version", str(base[key][0] + 1))
            stats["bumped"] += 1
    ET.ElementTree(root).write(out_path, encoding="UTF-8", xml_declaration=True)
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
    ap.add_argument("--config", default="config/17_workflow_spike.yaml")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    offset = a.offset or yaml.safe_load(open(a.config, encoding="utf-8"))["renumber_offset"]
    with tempfile.TemporaryDirectory() as td:
        prep, srt = pathlib.Path(td) / "prep.osm", pathlib.Path(td) / "sorted.osm"
        stats = prepare(a.base, a.edited, prep)
        log.info("prepare: %s", stats)
        run(["osmium", "sort", str(prep), "-o", str(srt), "--overwrite"])
        raw = pathlib.Path(td) / "raw.osc"
        run(["osmium", "derive-changes", a.base, str(srt), "-o", str(raw), "--overwrite"])
        if a.no_renumber:
            pathlib.Path(a.out).write_bytes(raw.read_bytes())
        else:
            shift = (a.editor_index + 1) * offset
            log.info("renumbered %d negative ids (block %d)", renumber(raw, a.out, shift, a.keep_negative), shift)


if __name__ == "__main__":
    main()
