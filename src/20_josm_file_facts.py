"""Task 04r, item 1: check what JOSM really writes (facts from notes.md) on the full real files.

Usage: uv run python src/20_josm_file_facts.py [config/24_real_josm.yaml]
Writes paths.facts_json. Parses the XML with xml.etree only; the quote-style fact is a plain substring count on the raw text.
"""
import collections
import hashlib
import json
import logging
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import osm_io  # noqa: E402

log = logging.getLogger("facts")


def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def decimals(s):
    return len(s.split(".")[1]) if "." in s else 0


def tag_order(el):
    return [(t.get("k"), t.get("v")) for t in el.findall("tag")]


def attr_sets(osm):
    out = collections.defaultdict(collections.Counter)
    for key, el in osm["objs"].items():
        for a in el.attrib:
            out[key[0]][a] += 1
        for ch in el:
            for a in ch.attrib:
                out[ch.tag][a] += 1
    return {k: dict(v) for k, v in out.items()}


def analyse(path, base_path):
    f, b = osm_io.read_osm(path), osm_io.read_osm(base_path)
    text = pathlib.Path(path).read_text(encoding="utf-8")
    btext = pathlib.Path(base_path).read_text(encoding="utf-8")
    R = {"file": pathlib.Path(path).name, "sha256": sha256(path)}
    R["quotes"] = {"file_single": text.count("='"), "file_double": text.count('="'),
                   "package_single": btext.count("='"), "package_double": btext.count('="')}
    R["root_attrs_file"], R["root_attrs_package"] = dict(f["root"].attrib), dict(b["root"].attrib)
    R["non_object_children_file"] = sorted({e.tag for e in f["root"] if e.tag not in osm_io.TYPES})
    R["non_object_children_package"] = sorted({e.tag for e in b["root"] if e.tag not in osm_io.TYPES})
    fo, bo = f["objs"], b["objs"]
    cnt = lambda objs: {t: sum(1 for k in objs if k[0] == t) for t in osm_io.TYPES}  # noqa: E731
    new = {k: e for k, e in fo.items() if k[1] < 0}
    R["counts"] = {"file": cnt(fo), "package": cnt(bo), "new": cnt(new)}
    R["counts_ok"] = all(R["counts"]["file"][t] == R["counts"]["package"][t] + R["counts"]["new"][t] for t in osm_io.TYPES)
    # new objects
    R["new_objects"] = {"n": len(new), "action_modify": sum(e.get("action") == "modify" for e in new.values()),
                        "with_version": sum("version" in e.attrib for e in new.values()),
                        "with_timestamp": sum("timestamp" in e.attrib for e in new.values()),
                        "ids": sorted(k[1] for k in new)}
    # existing objects
    ex = {k: e for k, e in fo.items() if k[1] > 0}
    in_base = {k: e for k, e in ex.items() if k in bo}
    R["existing"] = {"n": len(ex), "in_package": len(in_base), "not_in_package": sorted(k for k in ex if k not in bo),
                     "version_equal": sum(e.get("version") == bo[k].get("version") for k, e in in_base.items()),
                     "timestamp_equal": sum(e.get("timestamp") == bo[k].get("timestamp") for k, e in in_base.items())}
    actions = collections.Counter((k[0], e.get("action")) for k, e in fo.items() if e.get("action"))
    R["actions"] = {f"{t}:{a}": n for (t, a), n in sorted(actions.items())}
    # untouched objects: canonical content vs package
    untouched = {k: e for k, e in in_base.items() if e.get("action") is None}
    diff = [k for k, e in untouched.items() if osm_io.canon(e) != osm_io.canon(bo[k])]
    order_only = [k for k, e in untouched.items() if osm_io.canon(e) == osm_io.canon(bo[k]) and tag_order(e) != tag_order(bo[k])]
    R["untouched"] = {"n": len(untouched), "canonical_differs": len(diff), "canonical_differs_ids": [list(k) for k in diff[:20]],
                      "tag_order_only": len(order_only),
                      "tag_order_alphabetical_in_file": sum(tag_order(e) == sorted(tag_order(e)) for e in untouched.values()),
                      "node_decimals": dict(collections.Counter(max(decimals(e.get("lat")), decimals(e.get("lon")))
                                                                for k, e in untouched.items() if k[0] == "node"))}
    # moved nodes
    modified = {k: e for k, e in in_base.items() if e.get("action") == "modify"}
    moved = {k: e for k, e in modified.items() if k[0] == "node" and (e.get("lat"), e.get("lon")) != (bo[k].get("lat"), bo[k].get("lon"))}
    users_w = collections.defaultdict(list)
    for k, e in fo.items():
        if k[0] == "way":
            for r in osm_io.way_refs(e):
                users_w[r].append(k)
        if k[0] == "relation":
            for t, r, _ in osm_io.members(e):
                if t == "node":
                    users_w[r].append(k)
    marked_users = 0
    users_total = 0
    for k in moved:
        for u in users_w.get(k[1], []):
            users_total += 1
            marked_users += fo[u].get("action") is not None
    R["moved_nodes"] = {"n": len(moved), "ids": sorted(k[1] for k in moved),
                        "decimals": {str(k[1]): max(decimals(e.get("lat")), decimals(e.get("lon"))) for k, e in moved.items()},
                        "users_ways_relations": users_total, "users_marked_with_action": marked_users,
                        "users_marked_ids": [list(u) for k in moved for u in users_w.get(k[1], []) if fo[u].get("action")]}
    R["modified_existing"] = {"n": len(modified), "version_kept": sum(e.get("version") == bo[k].get("version") for k, e in modified.items()),
                              "by_type": dict(collections.Counter(k[0] for k in modified))}
    # deleted objects
    dw = {k: e for k, e in in_base.items() if e.get("action") == "delete" and k[0] == "way"}
    dn = {k: e for k, e in in_base.items() if e.get("action") == "delete" and k[0] == "node"}
    R["deleted"] = {
        "ways": {"n": len(dw), "ids": sorted(k[1] for k in dw),
                 "tags_kept": sum(bool(tag_order(e)) and sorted(tag_order(e)) == sorted(tag_order(bo[k])) for k, e in dw.items()),
                 "no_nd": sum(not e.findall("nd") for k, e in dw.items()),
                 "package_nd": {str(k[1]): len(bo[k].findall("nd")) for k in dw}},
        "nodes": {"n": len(dn), "ids": sorted(k[1] for k in dn),
                  "coords_kept": sum((e.get("lat"), e.get("lon")) == (bo[k].get("lat"), bo[k].get("lon")) for k, e in dn.items()),
                  "version_kept": sum(e.get("version") == bo[k].get("version") for k, e in dn.items())},
        "other_types": sum(1 for k, e in in_base.items() if e.get("action") == "delete" and k[0] == "relation"),
        "still_in_file": len(dw) + len(dn)}
    # attributes
    R["attrs_file"], R["attrs_package"] = attr_sets(f), attr_sets(b)
    R["extra_attrs"] = {"uid": sum("uid" in e.attrib for e in fo.values()), "user": sum("user" in e.attrib for e in fo.values()),
                        "changeset": sum("changeset" in e.attrib for e in fo.values()),
                        "visible_false": sum(e.get("visible") == "false" for e in fo.values()),
                        "visible_true": sum(e.get("visible") == "true" for e in fo.values()),
                        "upload": sum("upload" in e.attrib for e in fo.values())}
    return R


def main():
    cfg = yaml.safe_load(open(sys.argv[1] if len(sys.argv) > 1 else "config/24_real_josm.yaml", encoding="utf-8"))
    p = cfg["paths"]
    pathlib.Path(p["facts_json"]).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(p["log"]).parent.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(p["log"], mode="a"), logging.StreamHandler()])
    sp = pathlib.Path(p["spike_dir"])
    out = {}
    for name, key in (("A", "A"), ("B", "B"), ("B_update", "B")):
        base = cfg["bases"][key]
        assert sha256(base["osm"]) == base["sha256"], f"base {key} checksum mismatch"
        out[name] = analyse(sp / cfg["files"][name], base["osm"])
        log.info("analysed %s", name)
    a, r = sp / cfg["files"]["A"], sp / cfg["files"]["A_resaved"]
    out["resaved_identical"] = {"sha256_equal": sha256(a) == sha256(r), "bytes_equal": a.read_bytes() == r.read_bytes()}
    ids = {n: set(out[n]["new_objects"]["ids"]) for n in ("A", "B", "B_update")}
    out["negative_ids"] = {n: sorted(v, reverse=True) for n, v in ids.items()}
    out["negative_ids_overlap"] = {"A&B": sorted(ids["A"] & ids["B"]), "B&B_update": sorted(ids["B"] & ids["B_update"]), "A&B_update": sorted(ids["A"] & ids["B_update"])}
    pathlib.Path(p["facts_json"]).write_text(json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    log.info("written %s", p["facts_json"])


if __name__ == "__main__":
    main()
