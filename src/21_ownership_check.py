"""Task 04r: check change files (.osc from 19_osm_submit.py) against the ownership tables.

For every editor lists the changed, deleted and created objects and classifies each one:
  ok         own object / new object inside the zone polygon / new way anchored on own nodes
  warning    spanning way edited by its owner; node in shared_editable_nodes.csv; cross-editor or relation side effects
  violation  object owned by another zone; unowned object (reported separately); new node outside the polygon;
             new way anchored at a node of another zone; deleted node (or way) still referenced;
             node used by a way of another zone moved by more than move_threshold_m
Rules: moving a node owned by another zone is a violation at any distance. Node lists of deleted ways come from BASE.

Usage: uv run python src/21_ownership_check.py --editor NAME ZONE OSC BASE [--editor ...] [--json OUT.json] [--config config/21_ownership_check.yaml]
Exit codes: 0 ok, 1 violation, 2 warnings only, 4 the sha256 in OSC.meta.json differs from BASE.
"""
import argparse
import collections
import csv
import hashlib
import json
import logging
import math
import pathlib
import sys
import xml.etree.ElementTree as ET

import pyproj
import yaml
from shapely.geometry import Point, shape

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import osm_io  # noqa: E402

log = logging.getLogger("ownership")
SEV = {"ok": 0, "warning": 1, "violation": 2}
TYPE_ORDER = {"node": 0, "way": 1, "relation": 2}


def load_tables(d):
    d = pathlib.Path(d)
    own = {"node": {}, "way": {}, "relation": {}}
    spans = set()
    for t, f, col in (("way", "ownership_ways.csv", "way_id"), ("node", "ownership_nodes.csv", "node_id"),
                      ("relation", "ownership_relations.csv", "relation_id")):
        for r in csv.DictReader(open(d / f, encoding="utf-8")):
            z = int(r["owner_zone"])
            own[t][int(r[col])] = z if z > 0 else None      # owner 0 = outside RING 1 = unowned
            if t == "way" and r["spans_zones"] == "True":
                spans.add(int(r[col]))
    white = {int(r["node_id"]): {int(z) for z in r["zones_allowed"].split(";")}
             for r in csv.DictReader(open(d / "shared_editable_nodes.csv", encoding="utf-8"))}
    return own, spans, white


def load_full_base(path):
    """node -> set(way ids), node -> set(relation ids), way -> node list, relation -> members (only what the checks need)."""
    node_ways, node_rels, ways, rels = collections.defaultdict(set), collections.defaultdict(set), {}, {}
    for _, el in ET.iterparse(path):
        if el.tag == "way":
            refs = osm_io.way_refs(el)
            ways[int(el.get("id"))] = refs
            for r in refs:
                node_ways[r].add(int(el.get("id")))
            el.clear()
        elif el.tag == "relation":
            m = osm_io.members(el)
            rels[int(el.get("id"))] = m
            for t, r, _ in m:
                if t == "node":
                    node_rels[r].add(int(el.get("id")))
            el.clear()
        elif el.tag == "node":
            el.clear()
    return node_ways, node_rels, ways, rels


def read_osc(path, base):
    """Return [(op, element)] with op in create / modify / delete; 'create' = id not in the editor's base package."""
    out = []
    for block in ET.parse(path).getroot():
        for el in block:
            if el.tag not in osm_io.TYPES:
                continue
            key = (el.tag, int(el.get("id")))
            op = "delete" if block.tag == "delete" else ("modify" if key in base else "create")
            out.append((op, key, el))
    return out


def sha256_file(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--editor", nargs=4, action="append", metavar=("NAME", "ZONE", "OSC", "BASE"), required=True)
    ap.add_argument("--json")
    ap.add_argument("--config", default="config/21_ownership_check.yaml")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    cfg = yaml.safe_load(open(a.config, encoding="utf-8"))
    own, spans, white = load_tables(cfg["ownership_dir"])
    node_ways, node_rels, base_ways, base_rels = load_full_base(cfg["full_base"])
    to_m = pyproj.Transformer.from_crs("EPSG:4326", cfg["metric_crs"], always_xy=True).transform

    editors = {}
    for name, zone, osc, basep in a.editor:
        meta = pathlib.Path(osc + ".meta.json")
        if meta.exists() and json.loads(meta.read_text())["base_sha256"] != sha256_file(basep):
            log.error("editor %s: %s was derived against another base than %s", name, osc, basep)
            sys.exit(4)
        base = osm_io.read_osm(basep)["objs"]
        poly = shape(json.loads((pathlib.Path(basep).parent / f"zone_{zone}.geojson").read_text(encoding="utf-8"))["geometry"])
        editors[name] = {"zone": int(zone), "osc": osc, "base": base, "poly": poly, "ops": read_osc(osc, base)}

    rows = []

    def add(ed, key, op, detail, sev, cat, why, **extra):
        rows.append({"editor": ed, "type": key[0], "id": key[1], "op": op, "detail": detail, "severity": sev, "category": cat,
                     "reason": why, **extra})

    changed = collections.defaultdict(dict)         # (type, id) -> {editor: op}
    for n, e in editors.items():
        for op, key, _ in e["ops"]:
            changed[key][n] = op
    deleted_nodes = {k[1] for k, v in changed.items() if k[0] == "node" and "delete" in v.values()}
    deleted_ways = {k[1] for k, v in changed.items() if k[0] == "way" and "delete" in v.values()}
    new_nodes = {n: {k[1] for op, k, _ in e["ops"] if op == "create" and k[0] == "node"} for n, e in editors.items()}
    final_way_nodes = {}                             # ways created / modified: id -> (editor, node list)
    for n, e in editors.items():
        for op, k, el in e["ops"]:
            if k[0] == "way" and op != "delete":
                final_way_nodes[k[1]] = (n, osm_io.way_refs(el))
    moved = {}                                       # node -> (editor, metres)
    for n, e in editors.items():
        for op, k, el in e["ops"]:
            if k[0] == "node" and op == "modify":
                b = e["base"][k]
                if (round(float(b.get("lat")), 7), round(float(b.get("lon")), 7)) != (round(float(el.get("lat")), 7), round(float(el.get("lon")), 7)):
                    x0, y0 = to_m(float(b.get("lon")), float(b.get("lat")))
                    x1, y1 = to_m(float(el.get("lon")), float(el.get("lat")))
                    moved[k[1]] = (n, math.hypot(x1 - x0, y1 - y0))

    def classify_existing(zone, key, what):
        """(severity, category, reason) of an edit of an existing object by the editor of `zone`."""
        t, i = key
        if t == "node" and i in white:
            if zone in white[i]:
                return "warning", "whitelisted", f"node in shared_editable_nodes.csv (zones {sorted(white[i])})"
        owner = own[t].get(i, "missing")
        if owner == "missing" or owner is None:
            return "violation", "unowned", "object has no owner zone (outside RING 1 or not in the ownership table)"
        if owner != zone:
            return "violation", "other_zone", f"owned by zone {owner}"
        if t == "way" and i in spans:
            return "warning", "spanning_owner_edit", "spanning way, edited by its owner"
        return "ok", "own", f"owned by zone {zone}"

    def anchor_class(zone, i):
        if i in white and zone in white[i]:
            return "warning", "whitelisted_anchor", f"anchored at whitelisted node {i}"
        o = own["node"].get(i)
        if o == zone:
            return "ok", "own", ""
        if o is None:
            return "violation", "unowned", f"anchored at unowned node {i}"
        return "violation", "other_zone", f"anchored at node {i} owned by zone {o}"

    for name, e in editors.items():
        zone, base = e["zone"], e["base"]
        for op, key, el in sorted(e["ops"], key=lambda x: (TYPE_ORDER[x[1][0]], x[1][1])):
            t, i = key
            if op == "create":
                if t == "node":
                    inside = e["poly"].covers(Point(float(el.get("lon")), float(el.get("lat"))))
                    add(name, key, op, "new node", "ok" if inside else "violation",
                        "new_in_polygon" if inside else "new_outside_polygon",
                        "inside the zone polygon" if inside else "outside the zone polygon")
                elif t == "way":
                    worst, why = ("ok", "new_way_own", "new nodes inside the polygon, existing nodes own"), []
                    for r in osm_io.way_refs(el):
                        if r in new_nodes[name]:
                            sv = next(x["severity"] for x in rows if x["editor"] == name and x["type"] == "node" and x["id"] == r)
                            if sv != "ok":
                                why.append(f"new node {r} outside the polygon")
                                worst = ("violation", "new_way_outside", "")
                        else:
                            sv, cat, w = anchor_class(zone, r)
                            if SEV[sv] > SEV[worst[0]]:
                                worst = (sv, "new_way_" + cat, "")
                            if sv != "ok":
                                why.append(w)
                    add(name, key, op, f"new way, {len(osm_io.way_refs(el))} nodes", worst[0], worst[1], "; ".join(why) or worst[2])
                else:
                    bad = [m for m in osm_io.members(el) if m[0] != "node" or m[1] not in new_nodes[name]]
                    bad = [m for m in bad if own[m[0]].get(m[1]) != zone]
                    add(name, key, op, "new relation", "violation" if bad else "ok", "new_relation",
                        f"members not owned: {bad}" if bad else "all members own or new")
                continue
            detail = op
            if t == "node" and i in moved and moved[i][0] == name:
                detail = f"moved {moved[i][1]:.2f} m"
            elif op == "modify":
                b = base[key]
                parts = []
                if osm_io.canon(el)[-1] != osm_io.canon(b)[-1]:
                    parts.append("tags")
                if t == "way" and osm_io.way_refs(el) != osm_io.way_refs(b):
                    parts.append("nodes")
                if t == "relation" and osm_io.members(el) != osm_io.members(b):
                    parts.append("members")
                detail = "modify " + "+".join(parts or ["?"])
            extra = {}
            if op == "delete" and t == "way":
                refs = osm_io.way_refs(base[key])           # JOSM drops the <nd> list of a deleted way: take it from BASE
                extra["way_nodes_in_base"] = len(refs)
                extra["way_nodes_also_deleted"] = sum(r in deleted_nodes for r in refs)
                detail = f"delete way ({len(refs)} nodes in BASE, {extra['way_nodes_also_deleted']} deleted too)"
            sev, cat, why = classify_existing(zone, key, detail)
            add(name, key, op, detail, sev, cat, why, **extra)
            if t == "node" and i in moved and moved[i][0] == name:
                # rule (c): a node used by a way of another zone must not move by more than the threshold
                dist = moved[i][1]
                users = [w for w in node_ways.get(i, ()) if w not in deleted_ways and own["way"].get(w) != zone]
                users += [w for w, (ed, refs) in final_way_nodes.items() if i in refs and editors[ed]["zone"] != zone and w not in users]
                fired = dist > cfg["move_threshold_m"] and bool(users)
                rows[-1]["move_m"] = round(dist, 3)
                rows[-1]["rule_c_fired"] = fired
                rows[-1]["rule_c_users_other_zone"] = sorted(users)[:8]
                if fired:
                    add(name, key, op, detail, "violation", "move_exceeds_threshold",
                        f"moved {dist:.2f} m > {cfg['move_threshold_m']} m and used by ways of other zones: {sorted(users)[:8]}")

    # rule (c), part 1: deleted objects must not remain referenced
    for name, e in editors.items():
        for op, key, el in e["ops"]:
            if op != "delete":
                continue
            t, i = key
            if t == "node":
                ways_left = [w for w in node_ways.get(i, ()) if w not in deleted_ways and not (w in final_way_nodes and i not in final_way_nodes[w][1])]
                ways_left += [w for w, (_, refs) in final_way_nodes.items() if i in refs and w not in ways_left]
                rels_left = sorted(r for r in node_rels.get(i, ()) if changed.get(("relation", r), {}) == {})
                if ways_left or rels_left:
                    add(name, key, op, "deleted node still referenced", "violation", "dangling_reference",
                        f"still used by ways {sorted(ways_left)[:8]} relations {rels_left[:8]}")
            elif t == "way":
                rels = sorted(r for r, m in base_rels.items() if ("way", i) in {(x[0], x[1]) for x in m} and ("relation", r) not in changed)
                if rels:
                    add(name, key, op, "deleted way still a relation member", "violation", "dangling_reference", f"member of relations {rels[:8]}")

    # rule (d): cross-editor and relation side effects of moved / deleted nodes
    for i, (name, dist) in sorted(moved.items()):
        what = f"moved {dist:.2f} m"
        _warn_node_users(rows, editors, changed, name, i, what, node_ways, node_rels, final_way_nodes, own)
    for i in sorted(deleted_nodes):
        name = next(n for n, op in changed[("node", i)].items() if op == "delete")
        _warn_node_users(rows, editors, changed, name, i, "deleted", node_ways, node_rels, final_way_nodes, own)

    rows.sort(key=lambda r: (r["editor"], TYPE_ORDER[r["type"]], r["id"], -SEV[r["severity"]], r["category"]))
    worst = max((SEV[r["severity"]] for r in rows), default=0)
    print(f"{'editor':6} {'object':26} {'op':7} {'detail':44} {'result':9} category / reason")
    for r in rows:
        print(f"{r['editor']:6} {r['type'] + ' ' + str(r['id']):26} {r['op']:7} {r['detail'][:44]:44} {r['severity']:9} {r['category']}: {r['reason']}")
    c = collections.Counter(r["severity"] for r in rows)
    unowned = sum(r["category"] == "unowned" for r in rows)
    print(f"ok {c['ok']}, warning {c['warning']}, violation {c['violation']} (of which unowned {unowned})")
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(rows, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    sys.exit({0: 0, 1: 2, 2: 1}[worst])


def _warn_node_users(rows, editors, changed, name, i, what, node_ways, node_rels, final_way_nodes, own):
    """Semantic warnings for a node moved / deleted by editor `name`: its users changed by another editor, or relations."""
    key = ("node", i)
    users = set(node_ways.get(i, ())) | {w for w, (_, refs) in final_way_nodes.items() if i in refs}
    for w in sorted(users):
        others = [(n, op) for n, op in changed.get(("way", w), {}).items() if n != name]
        if others:
            rows.append({"editor": name, "type": "node", "id": i, "op": "modify" if what.startswith("moved") else "delete", "detail": what, "severity": "warning", "category": "cross_editor_way",
                         "reason": f"node {what} by {name} is used by way {w} changed by {others[0][0]} ({others[0][1]})"})
    for r in sorted(node_rels.get(i, ())):
        rows.append({"editor": name, "type": "node", "id": i, "op": "modify" if what.startswith("moved") else "delete", "detail": what, "severity": "warning", "category": "relation_member",
                     "reason": f"node {what} by {name} is a member of relation {r} (owner zone {own['relation'].get(r)})"})


if __name__ == "__main__":
    main()
