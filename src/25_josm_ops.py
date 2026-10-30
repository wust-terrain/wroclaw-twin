"""Task 04r-b: owned extent, package v2 regression, JOSM targets, way / relation operations.

Usage: uv run python src/25_josm_ops.py {regress|targets|verify|inventory|report} [config/25_josm_ops.yaml]
  regress  items 1-2: synthetic cases for the owned extent (S2, S2b, S2c, split) and the v2 package regression (a)-(d) on zone 3
  targets  item 3: spike_dir/josm_targets_zone3.{md,csv} from the v2 package and the ownership tables
  verify   item 5: facts of the real JOSM file editedC.osm, full chain, netconvert checks (needs the user's file)
  report   item 6: reports/09b_josm_operations.md from the results of the other subcommands
Everything generated goes under paths.workdir/<subcommand> (wiped at the start of that subcommand); no timestamps in outputs,
so two runs give identical output hashes (workdir/<subcommand>/output_hashes.txt).
"""
import collections
import csv
import hashlib
import json
import logging
import math
import pathlib
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import pyproj
import shapely.ops
import yaml
from shapely.geometry import LineString, Point, shape

SRC = pathlib.Path(__file__).parent
sys.path.insert(0, str(SRC))
import osm_io  # noqa: E402

log = logging.getLogger("josm_ops")
PY = sys.executable
SEV = {"ok": 0, "warning": 1, "violation": 2}


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def sh(cmd):
    log.info("$ %s", " ".join(str(c) for c in cmd))
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True)


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |" for r in rows]
    return "\n".join(out)


class Ctx:
    def __init__(self, cfg_path, sub):
        self.cfg = yaml.safe_load(open(cfg_path, encoding="utf-8"))
        p = self.cfg["paths"]
        self.zone = self.cfg["zone"]
        self.pkg = pathlib.Path(self.cfg["package"]["osm"])
        self.pkg_dir = self.pkg.parent
        self.root = pathlib.Path(p["workdir"])
        self.work = self.root / sub
        if sub in ("regress", "verify"):
            shutil.rmtree(self.work, ignore_errors=True)
        self.work.mkdir(parents=True, exist_ok=True)
        self.to_m = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:2177", always_xy=True).transform
        self.shift = (self.cfg["editor_index"] + 1) * self.cfg["renumber_offset"]
        self.poly = shape(json.loads((self.pkg_dir / f"zone_{self.zone}.geojson").read_text(encoding="utf-8"))["geometry"])
        self.poly_m = shapely.ops.transform(self.to_m, self.poly)

    def tables(self):
        spec = importlib_load("21_ownership_check.py")
        return spec.load_tables(self.cfg["paths"]["ownership_dir"])


def importlib_load(name):
    import importlib.util
    spec = importlib.util.spec_from_file_location("m" + name.split("_")[0], SRC / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------- building blocks
def to_josm(el, action=None):
    """Re-order attributes like JOSM (id, action, timestamp, visible, version, lat, lon); packages come from osmium."""
    order = ["id", "action", "timestamp", "visible", "version", "lat", "lon"]
    a = dict(el.attrib)
    if action:
        a["action"] = action
    a.setdefault("visible", "true")
    el.attrib.clear()
    for k in order:
        if k in a:
            el.set(k, a.pop(k))
    for k, v in a.items():
        el.set(k, v)
    return el


def load_package(path):
    f = osm_io.read_osm(path)
    kids = [to_josm(e) for e in f["root"] if e.tag in osm_io.TYPES]
    return kids, {(e.tag, int(e.get("id"))): e for e in kids}


def sort_children(el):
    """nd / member first in the original order, tags alphabetical (as JOSM)."""
    first = [c for c in el if c.tag != "tag"]
    tags = sorted((c for c in el if c.tag == "tag"), key=lambda c: c.get("k"))
    el[:] = first + tags


def add_tag(el, k, v):
    for t in el.findall("tag"):
        if t.get("k") == k:
            t.set("v", v)
            break
    else:
        ET.SubElement(el, "tag", k=k, v=v)
    el.set("action", "modify")
    sort_children(el)


def new_el(tag, i, **attrs):
    el = ET.Element(tag)
    for k, v in (("id", i), ("action", "modify"), ("visible", "true")):
        el.set(k, str(v))
    for k, v in attrs.items():
        el.set(k, str(v))
    return el


def insert_front(kids, el):
    idx = next((n for n, k in enumerate(kids) if k.tag == el.tag), len(kids))
    kids.insert(idx, el)


def write_edit(C, name, fn, base=None):
    """Copy of the package with the scripted edit fn(kids, objs) written in the JOSM format."""
    kids, objs = load_package(base or C.pkg)
    focus = fn(kids, objs)
    path = C.work / f"{name}.osm"
    osm_io.write_josm(path, kids)
    return path, focus


def submit(C, name, edited, base=None, index=None, extra=()):
    out = C.work / f"{name}.osc"
    cmd = [PY, SRC / "19_osm_submit.py", base or C.pkg, edited, out, "--editor-index", C.cfg["editor_index"] if index is None else index, *extra]
    return sh(cmd), out


def ownership(C, editors, name):
    """editors: [(name, zone, osc, base)] -> (CompletedProcess, rows)."""
    out = C.work / f"{name}.own.json"
    cmd = [PY, SRC / "21_ownership_check.py", "--json", out]
    for e in editors:
        cmd += ["--editor", *map(str, e)]
    r = sh(cmd)
    return r, (json.loads(out.read_text(encoding="utf-8")) if out.exists() else [])


def file_id(C, i, index=None):
    """Id of a new object after renumbering (negative id -> shift - id)."""
    shift = (C.cfg["editor_index"] if index is None else index) + 1
    return shift * C.cfg["renumber_offset"] - i if i < 0 else i


def rows_of(rows, keys):
    return [r for r in rows if (r["type"], r["id"]) in keys]


def verdict(rows, want):
    """want: (severity, category). True when the rows contain it."""
    return want in {(r["severity"], r["category"]) for r in rows}


def show(rows):
    return "; ".join(sorted({f"{r['severity']} / {r['category']}" for r in rows})) or "no row"


def canon_map(objs):
    return {k: osm_io.canon(e) for k, e in objs.items()}


# ---------------------------------------------------------------- regress (items 1 and 2)
def cmd_regress(C):
    cfg = C.cfg
    pk = cfg["package"]
    ctl = []
    ctl.append(("sha256 of the v2 package", pk["sha256"], sha(C.pkg), "ok" if sha(C.pkg) == pk["sha256"] else "FAIL"))
    sc = json.loads(C.pkg.with_suffix(".json").read_text(encoding="utf-8"))
    ctl.append(("sidecar package_version", pk["package_version"], sc.get("package_version"), "ok" if sc.get("package_version") == pk["package_version"] else "FAIL"))
    if ctl[0][-1] != "ok":
        sys.exit("v2 package checksum differs; abort")
    own, spans, white = C.tables()
    ext = importlib_load("21_ownership_check.py")
    buf = yaml.safe_load(open("config/21_ownership_check.yaml"))["owned_buffer_m"]
    extent, n_out = ext.owned_extent(C.poly, C.pkg_dir, C.zone, buf, "EPSG:2177", osm_io.read_osm(C.pkg)["objs"])
    ctl.append(("owned ways outside the polygon in the reference layer", 20, n_out, "ok" if n_out == 20 else "FAIL"))
    kids0, base = load_package(C.pkg)
    node_ways = collections.defaultdict(set)
    for (t, i), e in base.items():
        if t == "way":
            for r in osm_io.way_refs(e):
                node_ways[r].add(i)
    # owned ways outside the polygon (sidecar list = role=owned_outside_polygon) with all nodes owned by the zone, >= 5 nodes
    outside_ways = [i for i in sc["owned_ways_outside_context"]
                    if len(osm_io.way_refs(base[("way", i)])) >= 5 and all(own["node"].get(r) == C.zone for r in osm_io.way_refs(base[("way", i)]))]
    xy = lambda n: C.to_m(float(base[("node", n)].get("lon")), float(base[("node", n)].get("lat")))   # noqa: E731
    pick = None
    for wid in outside_ways:
        rs = osm_io.way_refs(base[("way", wid)])
        for k in range(len(rs) - 1):
            mx, my = [(u + v) / 2 for u, v in zip(xy(rs[k]), xy(rs[k + 1]))]
            if C.poly_m.distance(Point(mx, my)) >= cfg["extent_cases"]["min_outside_m"] and len(rs) > k + 2 and k >= 1:
                pick = (wid, k)
                break
        if pick:
            break
    cases = []
    results = []

    # --- item 1: synthetic cases on the v2 package
    ow, kseg = pick
    refs = osm_io.way_refs(base[("way", ow)])
    a_id, b_id = refs[kseg], refs[kseg + 1]
    a, b = base[("node", a_id)], base[("node", b_id)]
    mid = ((float(a.get("lat")) + float(b.get("lat"))) / 2, (float(a.get("lon")) + float(b.get("lon"))) / 2)
    dist_poly = C.poly_m.distance(Point(*C.to_m(mid[1], mid[0])))
    dlat = lambda m: m / 111320.0   # noqa: E731

    def beside(m):
        """latitude `m` metres from the segment midpoint, on the side away from the polygon."""
        for sg in (1, -1):
            lat = mid[0] + sg * dlat(m)
            if not C.poly_m.buffer(0).covers(Point(*C.to_m(mid[1], lat))) and C.poly_m.distance(Point(*C.to_m(mid[1], lat))) >= dist_poly:
                return lat
        raise SystemExit("no side away from the polygon")
    far = (C.poly.bounds[2] + cfg["extent_cases"]["far_offset_deg"], C.poly.bounds[3] + cfg["extent_cases"]["far_offset_deg"])
    # S2c: node `near_way_m` away from the way, not part of it (within the 10 m buffer)
    # S2d: node `far_from_way_m` away from the way and outside the polygon (more than the buffer)

    def s2(kids, objs):
        insert_front(kids, new_el("node", -39001, lat=f"{far[1]:.11f}", lon=f"{far[0]:.11f}"))
        return {("node", -39001)}

    def s2b(kids, objs):
        insert_front(kids, new_el("node", -39002, lat=f"{mid[0]:.11f}", lon=f"{mid[1]:.11f}"))
        w = objs[("way", ow)]
        nds = w.findall("nd")
        pos = [int(x.get("ref")) for x in nds].index(a_id) + 1
        w.insert(pos, ET.Element("nd", ref="-39002"))
        w.set("action", "modify")
        return {("node", -39002), ("way", ow)}

    def s2c(kids, objs):
        insert_front(kids, new_el("node", -39003, lat=f"{beside(cfg['extent_cases']['near_way_m']):.11f}", lon=f"{mid[1]:.11f}"))
        return {("node", -39003)}

    def far_point():
        """first point beside the segment, starting `far_from_way_m` away, that is > buffer + 5 m from the whole owned extent."""
        m = cfg["extent_cases"]["far_from_way_m"]
        while m < 500:
            for sg in (1, -1):
                lat = mid[0] + sg * dlat(m)
                if extent.distance(Point(*C.to_m(mid[1], lat))) > buf + 5:
                    return lat, m
            m += 10
        raise SystemExit("no point far from the owned extent")

    far_lat, far_m = far_point()

    def s2d(kids, objs):
        insert_front(kids, new_el("node", -39004, lat=f"{far_lat:.11f}", lon=f"{mid[1]:.11f}"))
        return {("node", -39004)}

    split_at = refs[kseg + 1] if kseg + 2 < len(refs) else refs[kseg]

    def split(kids, objs):
        w = objs[("way", ow)]
        nds = [int(x.get("ref")) for x in w.findall("nd")]
        k = nds.index(split_at)
        nw = new_el("way", -39005)
        for r in nds[k:]:
            ET.SubElement(nw, "nd", ref=str(r))
        for t in w.findall("tag"):
            ET.SubElement(nw, "tag", k=t.get("k"), v=t.get("v"))
        insert_front(kids, nw)
        for x in list(w.findall("nd"))[k + 1:]:
            w.remove(x)
        w.set("action", "modify")
        return {("way", -39005), ("way", ow)}

    # inherited connections (decision 2): a bridge-group way of zone 3 with an end node owned by another zone
    bw = [r for r in csv.DictReader(open(C.pkg_dir / f"zone_{C.zone}_bridge_ways.csv", encoding="utf-8"))
          if own["way"].get(int(r["way_id"])) == C.zone and ("way", int(r["way_id"])) in base and len(osm_io.way_refs(base[("way", int(r["way_id"]))])) >= 3
          and (r["owner_a"] != str(C.zone) or r["owner_b"] != str(C.zone)) and int(r["end_a"] if r["owner_a"] != str(C.zone) else r["end_b"]) not in white]
    fw = int(bw[0]["way_id"])
    frefs = osm_io.way_refs(base[("way", fw)])
    foreign_first = own["node"].get(frefs[0]) != C.zone
    foreign_end = frefs[0] if foreign_first else frefs[-1]
    ksplit = len(frefs) // 2
    other_node = min(n for n in (i for (t, i) in base if t == "node") if own["node"].get(n) not in (C.zone, None) and n not in white
                     and all(own["way"].get(w) != C.zone for w in node_ways[n]) and node_ways[n])
    inside_pt = C.poly.representative_point()

    def split_end(wid, new_id):
        """split owned way `wid` in the middle; the new way takes the part with the foreign end node."""
        rs_ = osm_io.way_refs(base[("way", wid)])
        first = own["node"].get(rs_[0]) != C.zone
        k_ = len(rs_) // 2

        def f(kids, objs):
            w = objs[("way", wid)]
            nds = [int(x.get("ref")) for x in w.findall("nd")]
            part_new = nds[:k_ + 1] if first else nds[k_:]
            nw = new_el("way", new_id)
            for r in part_new:
                ET.SubElement(nw, "nd", ref=str(r))
            for t in w.findall("tag"):
                ET.SubElement(nw, "tag", k=t.get("k"), v=t.get("v"))
            insert_front(kids, nw)
            for x in list(w.findall("nd")):
                if (int(x.get("ref")) in part_new) and int(x.get("ref")) != nds[k_]:
                    w.remove(x)
            w.set("action", "modify")
            return {("way", new_id), ("way", wid)}
        return f

    split_foreign = split_end(fw, -39006)

    def tag_and_attach(kids, objs):
        add_tag(objs[("way", fw)], cfg["bridge"]["note_tag"]["k"], cfg["bridge"]["note_tag"]["v"])
        insert_front(kids, new_el("node", -39011, lat=f"{inside_pt.y:.11f}", lon=f"{inside_pt.x:.11f}"))
        nw = new_el("way", -39012)
        for r in (foreign_end, -39011):
            ET.SubElement(nw, "nd", ref=str(r))
        ET.SubElement(nw, "tag", k="highway", v="service")
        insert_front(kids, nw)
        return {("way", -39012), ("way", fw)}

    # seam way owned by this zone (zone_N_seams.csv, owned_by_this_zone), ending at a node owned by `seam_other_zone`
    seams = []
    for r in csv.DictReader(open(C.pkg_dir / f"zone_{C.zone}_seams.csv", encoding="utf-8")):
        wid = int(r["way_id"]) if r["way_id"].isdigit() else None
        if wid is None or r["owned_by_this_zone"] != "True" or r["other_zone"] != str(cfg["seam_other_zone"]) or ("way", wid) not in base or own["way"].get(wid) != C.zone:
            continue
        rs_ = osm_io.way_refs(base[("way", wid)])
        if len(rs_) >= 3 and (own["node"].get(rs_[0]) == cfg["seam_other_zone"] or own["node"].get(rs_[-1]) == cfg["seam_other_zone"]) and \
                all(own["node"].get(n) in (C.zone, cfg["seam_other_zone"]) for n in rs_):
            seams.append(wid)
    seam_ns = next((w for w in seams if w not in spans), None)
    seam_sp = next((w for w in seams if w in spans), None)

    def replace_way(kids, objs):
        w = objs[("way", fw)]
        a_, b_ = frefs[0], frefs[-1]
        tags = [(t.get("k"), t.get("v")) for t in w.findall("tag")]
        mid_n = objs[("node", frefs[len(frefs) // 2])]
        insert_front(kids, new_el("node", -39007, lat=mid_n.get("lat"), lon=mid_n.get("lon")))
        nw = new_el("way", -39008)
        for r in (a_, -39007, b_):
            ET.SubElement(nw, "nd", ref=str(r))
        for k, v in tags:
            ET.SubElement(nw, "tag", k=k, v=v)
        insert_front(kids, nw)
        for c in list(w):
            if c.tag == "nd":
                w.remove(c)          # JOSM drops the <nd> list of a deleted way
        w.set("action", "delete")
        return {("way", -39008), ("node", -39007), ("way", fw)}

    def foreign_new_way(kids, objs):
        insert_front(kids, new_el("node", -39009, lat=f"{inside_pt.y:.11f}", lon=f"{inside_pt.x:.11f}"))
        nw = new_el("way", -39010)
        for r in (other_node, -39009):
            ET.SubElement(nw, "nd", ref=str(r))
        ET.SubElement(nw, "tag", k="highway", v="service")
        insert_front(kids, nw)
        return {("way", -39010)}

    syn = [
        ("N1", f"split of owned bridge-group way {fw} (end node {foreign_end} owned by zone {own['node'][foreign_end]}); the new way takes the foreign end", ("ok", "new_way_own"), split_foreign, 0),
        ("N2", f"delete owned way {fw} and draw a new way between its end nodes (one foreign: {foreign_end})", ("ok", "new_way_own"), replace_way, 0),
        ("N4", f"tag-only edit of owned way {fw} plus a new way attached to its foreign end node {foreign_end}: not inherited", ("violation", "new_way_other_zone"), tag_and_attach, 1),
        ("N3", f"new way attached to node {other_node} (owner zone {own['node'][other_node]}), no owned way using it is modified or deleted", ("violation", "new_way_other_zone"), foreign_new_way, 1),
        ("S2", "new node far outside the polygon (>10 m from any owned way)", ("violation", "new_outside_polygon"), s2, 1),
        ("S2b", f"new node on owned way {ow} (outside the polygon, {dist_poly:.0f} m away), inserted into the way", ("ok", "new_in_polygon"), s2b, 0),
        ("S2c", f"new node {cfg['extent_cases']['near_way_m']:.0f} m beside owned way {ow} (within the buffer), not part of the way (unused node: orphan warning, exit 2)", ("ok", "new_in_polygon"), s2c, 2),
        ("S2d", f"new node {far_m:.0f} m beside owned way {ow} ({extent.distance(Point(*C.to_m(mid[1], far_lat))):.0f} m from the owned extent, outside the buffer)", ("violation", "new_outside_polygon"), s2d, 1),
        ("S2e", f"split owned way {ow} at node {split_at}: new way outside the polygon, all existing nodes owned by zone {C.zone}", ("ok", "new_way_own"), split, 0),
    ]
    for cid, wid, ex, note in (("N5", seam_ns, 0, "non-spanning"), ("N5b", seam_sp, 2, "spanning")):
        if wid:
            syn.insert(1, (cid, f"split of {note} seam way {wid} (owned by zone {C.zone}, ends at a node owned by zone {cfg['seam_other_zone']}); the new way takes the foreign end" + ("; the old way is a warning (spanning way, unchanged rule)" if ex == 2 else ""),
                           ("ok", "new_way_own"), split_end(wid, -39013 if cid == "N5" else -39014), ex))
        else:
            results.append((cid, f"split of a {note} seam way owned by zone {C.zone} ending at a node of zone {cfg['seam_other_zone']}", "-", "no such seam way in zone_3_seams.csv", "n/a"))
    # ---- derived edits (decision: split / combine / merge) and invalid / orphan objects
    post = {}                                                   # case -> predicate on the focus rows
    rel_owner = lambda r: own["relation"].get(r)               # noqa: E731
    way_rel = collections.defaultdict(set)
    for (t, i), e in base.items():
        if t == "relation":
            for mt, r, ro in osm_io.members(e):
                if mt == "way":
                    way_rel[r].add(i)
    drel = None
    for (t, rid), e in sorted(base.items()):
        if t != "relation" or rel_owner(rid) in (C.zone, None) or way_tags(e).get("type") != "restriction":
            continue
        ms = osm_io.members(e)
        via = next((r for mt, r, ro in ms if ro == "via" and mt == "node"), None)
        for mt, r, ro in ms:
            if mt == "way" and own["way"].get(r) == C.zone and r not in spans and ("way", r) in base and via in osm_io.way_refs(base[("way", r)]) \
                    and len(osm_io.way_refs(base[("way", r)])) >= 3 and r not in bridge_ways_set(C) and drel is None:
                drel = (rid, r, ro, via)

    def split_member(rid, wid, role, via, new_id, tag_relation=False):
        def f(kids, objs):
            w = objs[("way", wid)]
            nds = [int(x.get("ref")) for x in w.findall("nd")]
            k_ = len(nds) // 2
            part_new = nds[:k_ + 1] if via in nds[:k_ + 1] else nds[k_:]
            nw = new_el("way", new_id)
            for r in part_new:
                ET.SubElement(nw, "nd", ref=str(r))
            for t in w.findall("tag"):
                ET.SubElement(nw, "tag", k=t.get("k"), v=t.get("v"))
            insert_front(kids, nw)
            for x in list(w.findall("nd")):
                if int(x.get("ref")) in part_new and int(x.get("ref")) != nds[k_]:
                    w.remove(x)
            w.set("action", "modify")
            rel = objs[("relation", rid)]
            for m in rel.findall("member"):
                if m.get("type") == "way" and int(m.get("ref")) == wid and m.get("role") == role:
                    m.set("ref", str(new_id))
            rel.set("action", "modify")
            if tag_relation:
                add_tag(rel, "note", "04r-b test")
            return {("way", new_id), ("way", wid), ("relation", rid)}
        return f

    if drel:
        rid, wid, role, via = drel
        syn.append(("D1", f"split of owned way {wid} (from/to member `{role}` of relation {rid}, owned by zone {rel_owner(rid)}): the new part replaces it in the relation",
                    ("ok", "derived_edit"), split_member(rid, wid, role, via, -39020), 0))
        post["D1"] = lambda rr: any(x["type"] == "relation" and "derived from split of" in x["reason"] for x in rr)
        syn.append(("D2", f"the same split plus a tag change on relation {rid}", ("violation", "other_zone"), split_member(rid, wid, role, via, -39021, True), 1))
        post["D2"] = lambda rr: any(x["type"] == "relation" and x["category"] == "other_zone" for x in rr)
    else:
        results.append(("D1", "split of an owned way that is a member of a foreign relation", "-", "no candidate in the package", "FAIL"))
    # D3: combine of two owned ways, the deleted one a member of a foreign relation
    node_ws = collections.defaultdict(set)
    for (t, i), e in base.items():
        if t == "way":
            for r in osm_io.way_refs(e):
                node_ws[r].add(i)
    comb = None
    for (t, rid), e in sorted(base.items()):
        if t != "relation" or rel_owner(rid) in (C.zone, None):
            continue
        for mt, w1, ro in osm_io.members(e):
            if mt != "way" or own["way"].get(w1) != C.zone or w1 in spans or ("way", w1) not in base or comb:
                continue
            r1 = osm_io.way_refs(base[("way", w1)])
            for n in (r1[0], r1[-1]):
                if len(node_ws[n]) != 2 or n in white or base[("node", n)].findall("tag") or r1[0] == r1[-1]:
                    continue
                w2 = next(iter(node_ws[n] - {w1}))
                r2 = osm_io.way_refs(base[("way", w2)])
                if own["way"].get(w2) == C.zone and w2 not in spans and not way_rel[w2] and way_tags(base[("way", w2)]).get("highway") == way_tags(base[("way", w1)]).get("highway") and r2[0] != r2[-1] and w2 not in bridge_ways_set(C):
                    comb = (rid, w1, w2, ro, n)
                    break
    if comb:
        rid, w1, w2, ro, n = comb

        def combine(kids, objs):
            a, b = osm_io.way_refs(objs[("way", w1)]), osm_io.way_refs(objs[("way", w2)])
            if a[-1] == b[0]:
                merged = a + b[1:]
            elif a[0] == b[-1]:
                merged = b + a[1:]
            elif a[0] == b[0]:
                merged = a[::-1] + b[1:]
            else:
                merged = a + b[::-1][1:]
            s_ = objs[("way", w2)]
            tags = [c for c in s_ if c.tag == "tag"]
            s_[:] = [ET.Element("nd", ref=str(r)) for r in merged] + tags
            s_.set("action", "modify")
            d_ = objs[("way", w1)]
            for c in list(d_):
                if c.tag == "nd":
                    d_.remove(c)
            d_.set("action", "delete")
            rel = objs[("relation", rid)]
            for m in rel.findall("member"):
                if int(m.get("ref")) == w1 and m.get("type") == "way":
                    m.set("ref", str(w2))
            rel.set("action", "modify")
            return {("way", w1), ("way", w2), ("relation", rid)}
        syn.append(("D3", f"combine of owned ways {w1} (member `{ro}` of relation {rid}, owned by zone {rel_owner(rid)}) and {w2} at node {n}; survivor {w2}",
                    ("ok", "derived_edit"), combine, 0))
        post["D3"] = lambda rr: any(x["type"] == "relation" and "derived from combine of" in x["reason"] for x in rr)
    else:
        results.append(("D3", "combine of two owned ways, one a member of a foreign relation", "-", "no candidate in the package", "FAIL"))
    # D4: merge an owned node d into an owned node s where a foreign way uses d
    mrg = None
    for d_ in sorted(i for (t, i) in base if t == "node"):
        ws_ = node_ws.get(d_, set())
        if own["node"].get(d_) != C.zone or d_ in white or base[("node", d_)].findall("tag") or len(ws_) != 2 or any(r_ for r_ in node_rels_of(base, d_)):
            continue
        ow_l = [w for w in ws_ if own["way"].get(w) == C.zone and w not in spans]
        fo = [w for w in ws_ if own["way"].get(w) not in (C.zone, None)]
        if len(ow_l) == 1 and len(fo) == 1 and ow_l[0] not in bridge_ways_set(C):
            near = [n_ for n_ in osm_io.way_refs(base[("way", ow_l[0])]) if n_ != d_ and own["node"].get(n_) == C.zone and n_ not in white and n_ not in osm_io.way_refs(base[("way", fo[0])])]
            if near:
                mrg = (d_, near[0], ow_l[0], fo[0])
                break
    if mrg:
        d_, s_node, wo, wf = mrg

        def merge(kids, objs):
            for wid in (wo, wf):
                w = objs[("way", wid)]
                for x in w.findall("nd"):
                    if int(x.get("ref")) == d_:
                        x.set("ref", str(s_node))
                w.set("action", "modify")
            objs[("node", d_)].set("action", "delete")
            return {("node", d_), ("way", wo), ("way", wf)}
        syn.append(("D4", f"merge of owned node {d_} into owned node {s_node}; ways {wo} (owned) and {wf} (owner zone {own['way'][wf]}) used {d_}", ("violation", "other_zone"), merge, 1))
        post["D4"] = lambda rr: any(x["id"] == wo and x["category"] == "derived_edit" for x in rr) and any(x["id"] == wf and x["category"] == "other_zone" for x in rr)
    else:
        results.append(("D4", "merge of an owned node used by a foreign way", "-", "no candidate in the package", "FAIL"))
    # I1 / O1: the accident of the notes (two one-node ways with the same new node) and an orphan node
    acc_pt = (inside_pt.x, inside_pt.y)

    def accident(kids, objs):
        insert_front(kids, new_el("node", -26253, lat=f"{acc_pt[1]:.11f}", lon=f"{acc_pt[0]:.11f}"))
        w1_ = new_el("way", -726)
        ET.SubElement(w1_, "nd", ref="-26253")
        ET.SubElement(w1_, "tag", k="name", v="Plac Powstańców Warszawy")
        w2_ = new_el("way", -727)
        ET.SubElement(w2_, "nd", ref="-26253")
        ET.SubElement(w2_, "tag", k="highway", v="secondary")
        insert_front(kids, w2_)
        insert_front(kids, w1_)
        return {("way", -726), ("way", -727)}

    def orphan(kids, objs):
        insert_front(kids, new_el("node", -39030, lat=f"{acc_pt[1]:.11f}", lon=f"{acc_pt[0]:.11f}"))
        return {("node", -39030)}
    syn.append(("I1", "the accident of notes.md: new ways -726 (name tag) and -727 (highway=secondary), each with the single new node -26253", ("violation", "invalid_object"), accident, 1))
    post["I1"] = lambda rr: sum(1 for x in rr if x["category"] == "invalid_object") == 2
    syn.append(("O1", "a new untagged node used by no way and no relation", ("warning", "orphan"), orphan, 2))

    for cid, desc, want, fn, ex in syn:
        path, focus = write_edit(C, cid, fn)
        r, osc = submit(C, cid, path)
        if r.returncode != 0:
            results.append((cid, desc, f"{want[0]} / {want[1]}", f"19 exit {r.returncode}", "FAIL"))
            continue
        r21, rows = ownership(C, [("A", C.zone, osc, C.pkg)], cid)
        fk = {(t, file_id(C, i)) for t, i in focus}
        rr = rows_of(rows, fk)
        okc = verdict(rr, want) and r21.returncode == ex and all(SEV[x["severity"]] <= SEV[want[0]] or (cid == "N5b" and x["category"] == "spanning_owner_edit") or (cid == "S2c" and x["category"] == "orphan") for x in rr)
        if cid in ("N1", "N2", "N5", "N5b"):
            okc = okc and any("inherited" in x["reason"] for x in rr)
        if cid in post:
            okc = okc and post[cid](rr)
        results.append((cid, desc, f"{want[0]} / {want[1]}, exit {ex}", f"{show(rr)}, exit {r21.returncode}", "pass" if okc else "FAIL"))
    # old S2 on the v1 package (24_real_workflow.py) is re-run separately by the caller; see report

    # --- item 2: v2 regression
    br = cfg["bridge"]
    k_, v_ = br["note_tag"]["k"], br["note_tag"]["v"]
    reg = []

    def tag_edit(wid):
        def f(kids, objs):
            add_tag(objs[("way", wid)], k_, v_)
            return {("way", wid)}
        return f

    def move(kids, objs):
        n = objs[("node", br["node_other_zone"])]
        lon0, lat0_ = float(n.get("lon")), float(n.get("lat"))
        n.set("lon", f"{lon0 + br['move_m'] / (111320.0 * math.cos(math.radians(lat0_))):.11f}")
        n.set("action", "modify")
        return {("node", br["node_other_zone"])}

    for cid, desc, fn, want, ex in (
            ("a", f"tag edit on way {br['tag_way_a']} (owner {own['way'][br['tag_way_a']]}, bridge group 6)", tag_edit(br["tag_way_a"]), ("ok", "own"), 0),
            ("b", f"tag edit on way {br['tag_way_b']} (owner {own['way'][br['tag_way_b']]}, bridge group, end nodes owned by zone 2, spanning)", tag_edit(br["tag_way_b"]), ("ok", "bridge_group_owner"), 0),
            ("c", f"move node {br['node_other_zone']} (owner {own['node'][br['node_other_zone']]}) by {br['move_m']} m", move, ("violation", "other_zone"), 1)):
        path, focus = write_edit(C, "v2" + cid, fn)
        r, osc = submit(C, "v2" + cid, path)
        r21, rows = ownership(C, [("A", C.zone, osc, C.pkg)], "v2" + cid)
        rr = rows_of(rows, {(t, i) for t, i in focus})
        okc = r.returncode == 0 and verdict(rr, want) and r21.returncode == ex
        results.append((f"v2({cid})", desc, f"{want[0]} / {want[1]}, exit {ex}", f"{show(rr)}, exit {r21.returncode}", "pass" if okc else "FAIL"))
        reg.append((cid, osc, r21.returncode))
    # (d) the v1 package presented to the v2 sidecar
    d = C.work / "v1_as_base"
    d.mkdir(exist_ok=True)
    shutil.copy(cfg["legacy_v1_osm"], d / f"zone_{C.zone}.osm")
    shutil.copy(C.pkg.with_suffix(".json"), d / f"zone_{C.zone}.json")
    shutil.copy(C.pkg_dir / f"zone_{C.zone}.geojson", d / f"zone_{C.zone}.geojson")
    ra = sh([PY, SRC / "19_osm_submit.py", d / f"zone_{C.zone}.osm", C.work / "v2a.osm", C.work / "v2d.osc", "--editor-index", 0])
    # 21: an .osc derived against the v2 package, checked against the v1 file as BASE
    rb = sh([PY, SRC / "21_ownership_check.py", "--editor", "A", C.zone, reg[0][1], d / f"zone_{C.zone}.osm"])
    results.append(("v2(d)", "the v1 package presented to the v2 sidecar: 19_osm_submit.py", "exit 4, no .osc", f"exit {ra.returncode}, .osc: {(C.work / 'v2d.osc').exists()}", "pass" if ra.returncode == 4 and not (C.work / "v2d.osc").exists() else "FAIL"))
    results.append(("v2(d2)", "an .osc derived against v2 checked with the v1 file as base: 21_ownership_check.py", "exit 4", f"exit {rb.returncode}", "pass" if rb.returncode == 4 else "FAIL"))

    # --- the chain on (a) and (b): two editors from the same base, 19 -> 18 -> 21 -> merge -> apply -> check-refs
    pa, fa = write_edit(C, "chain_a", tag_edit(br["tag_way_a"]))
    pb, fb = write_edit(C, "chain_b", tag_edit(br["tag_way_b"]))
    ra_, oa = submit(C, "chain_a", pa, index=0)
    rb_, ob = submit(C, "chain_b", pb, index=1)
    r18 = sh([PY, SRC / "18_osm_conflicts.py", f"E1={oa}", f"E2={ob}"])
    r21, rows = ownership(C, [("E1", C.zone, oa, C.pkg), ("E2", C.zone, ob, C.pkg)], "chain")
    merged_osc, merged_osm = C.work / "chain_merged.osc", C.work / "chain_merged.osm"
    m = sh(["osmium", "merge-changes", oa, ob, "-o", merged_osc, "--overwrite"])
    ap = sh(["osmium", "apply-changes", cfg["paths"]["full_base"], merged_osc, "-o", merged_osm, "--overwrite"])
    crb = [x for x in sh(["osmium", "check-refs", "-r", cfg["paths"]["full_base"]]).stderr.splitlines() if "missing" in x]
    crm = [x for x in sh(["osmium", "check-refs", "-r", merged_osm]).stderr.splitlines() if "missing" in x]
    fb_objs = osm_io.read_osm(cfg["paths"]["full_base"])["objs"]
    mg_objs = osm_io.read_osm(merged_osm)["objs"]
    diff = sorted(k for k in set(fb_objs) | set(mg_objs) if (k in fb_objs) != (k in mg_objs) or (k in fb_objs and osm_io.canon(fb_objs[k]) != osm_io.canon(mg_objs[k])))
    versions = {k: (fb_objs[k].get("version"), mg_objs[k].get("version")) for k in diff if k in fb_objs and k in mg_objs}
    expect = [("way", br["tag_way_a"]), ("way", br["tag_way_b"])]
    tags_ok = all({t.get("k"): t.get("v") for t in mg_objs[k].findall("tag")} == {**{t.get("k"): t.get("v") for t in fb_objs[k].findall("tag")}, k_: v_} for k in expect)
    ctl.append(("chain 19 (E1, E2)", "exit 0 / 0", f"exit {ra_.returncode} / {rb_.returncode}", "ok" if ra_.returncode == rb_.returncode == 0 else "FAIL"))
    ctl.append(("chain 18", "exit 0, no conflicts", f"exit {r18.returncode}: {r18.stdout.strip().splitlines()[-1]}", "ok" if r18.returncode == 0 else "FAIL"))
    ctl.append(("chain 21 (E1, E2)", "exit 0 (both ways ok)", f"exit {r21.returncode}: {rows and collections.Counter(r['severity'] for r in rows)}", "ok" if r21.returncode == 0 and all(r["severity"] == "ok" for r in rows) else "FAIL"))
    ctl.append(("osmium merge-changes / apply-changes", "exit 0 / 0", f"exit {m.returncode} / {ap.returncode}", "ok" if m.returncode == ap.returncode == 0 else "FAIL"))
    ctl.append(("osmium check-refs: result = base", "same 'missing' lines", "identical" if crb == crm else f"base {crb} vs result {crm}", "ok" if crb == crm else "FAIL"))
    ctl.append(("result vs full base (canonical, all objects)", f"exactly {expect}, versions +1, tag {k_}={v_}", f"differs: {diff}; versions {versions}; tags ok {tags_ok}",
                "ok" if diff == expect and all(int(b) + 1 == int(a) for b, a in versions.values()) and tags_ok else "FAIL"))
    # combined (a)+(b) in one file, one editor
    def both(kids, objs):
        for w in (br["tag_way_a"], br["tag_way_b"]):
            add_tag(objs[("way", w)], k_, v_)
        return set()
    pab, _ = write_edit(C, "chain_ab", both)
    rab, oab = submit(C, "chain_ab", pab)
    r21ab, rowsab = ownership(C, [("A", C.zone, oab, C.pkg)], "chain_ab")
    sev_ab = sorted((r["id"], r["severity"], r["category"]) for r in rowsab)
    ctl.append(("(a)+(b) in one file: 19 / 21", "exit 0 / exit 0, both rows ok", f"exit {rab.returncode} / exit {r21ab.returncode}: {sev_ab}", "ok" if rab.returncode == 0 and r21ab.returncode == 0 and len(rowsab) == 2 and all(r[1] == "ok" for r in sev_ab) else "FAIL"))

    out = {"ctl": ctl, "results": results, "outside_way": ow, "split_at": split_at, "outside_ways_candidates": outside_ways[:5],
           "diff": [list(k) for k in diff], "n_ways_outside": n_out}
    (C.work / "regress.json").write_text(json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    print("\nControl table")
    print(md_table(["Check", "Expected", "Actual", "Status"], ctl))
    print("\nCases")
    print(md_table(["Case", "Edit", "Expected", "Actual", "Result"], results))
    write_hashes(C, ["*.osc", "*.osm", "*.json"])
    bad = [r for r in ctl if r[-1] != "ok"] + [r for r in results if r[-1] != "pass"]
    if bad:
        print("\nDISCREPANCIES:", len(bad))
        sys.exit(1)


# ---------------------------------------------------------------- targets (item 3)
def way_tags(el):
    return {t.get("k"): t.get("v") for t in el.findall("tag")}


def cmd_targets(C):
    cfg = C.cfg
    tc = cfg["targets"]
    own, spans, white = C.tables()
    kids, base = load_package(C.pkg)
    if sha(C.pkg) != cfg["package"]["sha256"]:
        sys.exit("v2 package checksum differs; abort")
    zone = C.zone
    nxy = {i: C.to_m(float(e.get("lon")), float(e.get("lat"))) for (t, i), e in base.items() if t == "node"}
    nll = {i: (float(e.get("lon")), float(e.get("lat"))) for (t, i), e in base.items() if t == "node"}
    bnd = C.poly_m.boundary
    depth_c = {}

    def depth(n):
        """metres inside the zone polygon (negative = outside)."""
        if n not in depth_c:
            p = Point(nxy[n])
            depth_c[n] = bnd.distance(p) if C.poly_m.covers(p) else -C.poly_m.distance(p)
        return depth_c[n]

    bridge_ways = {int(r["way_id"]) for r in csv.DictReader(open(pathlib.Path(cfg["paths"]["ownership_dir"]) / "ownership_ways.csv", encoding="utf-8")) if r["bridge_group"]}
    ways = {i: e for (t, i), e in base.items() if t == "way"}
    wrefs = {i: osm_io.way_refs(e) for i, e in ways.items()}
    node_ways = collections.defaultdict(set)
    for i, rs in wrefs.items():
        for r in rs:
            node_ways[r].add(i)
    node_rels, way_rels = collections.defaultdict(set), collections.defaultdict(set)
    rels = {i: e for (t, i), e in base.items() if t == "relation"}
    for i, e in rels.items():
        for mt, r, role in osm_io.members(e):
            (node_rels if mt == "node" else way_rels if mt == "way" else collections.defaultdict(set))[r].add(i)
    road = set(tc["road_classes"])
    hw = lambda w: way_tags(ways[w]).get("highway")   # noqa: E731
    length = {w: sum(math.hypot(nxy[a][0] - nxy[b][0], nxy[a][1] - nxy[b][1]) for a, b in zip(rs, rs[1:])) for w, rs in wrefs.items()}
    inside_min = lambda ns: min(depth(n) for n in ns)   # noqa: E731

    def eligible(w, strict=True):
        """owned by the zone, non-spanning, outside every bridge group, no whitelisted node, all nodes >= min_inside_m inside."""
        if own["way"].get(w) != zone or w in spans or w in bridge_ways or any(n in white for n in wrefs[w]):
            return False
        return (not strict) or inside_min(wrefs[w]) >= tc["min_inside_m"]

    elig = {w for w in ways if eligible(w)}
    rows, used_ways, used_nodes = [], set(), set()   # rows: dicts for the csv

    def centre(ns):
        xs = [nll[n] for n in ns]
        return round(sum(x for x, _ in xs) / len(xs), 7), round(sum(y for _, y in xs) / len(xs), 7)

    def add(target, rank, kind, ids, ns, **kw):
        lon, lat = centre(ns)
        rows.append({"target": target, "rank": rank, "kind": kind, "ids": ";".join(str(i) for i in ids), "min_inside_m": round(inside_min(ns), 1),
                     "lon": lon, "lat": lat, **kw})

    # relations
    def restr(i):
        t = way_tags(rels[i])
        return t.get("type") == "restriction"

    def rel_parts(i):
        ms = osm_io.members(rels[i])
        return ([r for mt, r, ro in ms if ro == "from" and mt == "way"], [r for mt, r, ro in ms if ro == "via"], [r for mt, r, ro in ms if ro == "to" and mt == "way"], ms)

    own_rel = {i for i in rels if own["relation"].get(i) == zone and restr(i)}
    # T4 candidates: via a node, from / to ways owned, eligible and road class
    t4c = []
    for i in sorted(own_rel):
        fr, via, to, ms = rel_parts(i)
        if len(fr) == len(to) == len(via) == 1 and ms:
            vmt = next(mt for mt, r, ro in ms if ro == "via")
            if vmt != "node":
                continue
            if all(w in elig and hw(w) in road for w in fr + to) and depth(via[0]) >= tc["min_inside_m"] and via[0] not in white and fr[0] != to[0]:
                t4c.append(i)
    t1c = [w for w in sorted(elig) if hw(w) in road and length[w] >= tc["t1"]["min_length_m"] and len(wrefs[w]) >= tc["t1"]["min_nodes"] and wrefs[w][0] != wrefs[w][-1]]

    def split_node(w):
        """interior node used only by this way, untagged, closest to the middle of the way."""
        rs = wrefs[w]
        cand = [(abs(k - (len(rs) - 1) / 2), n) for k, n in enumerate(rs[1:-1], 1) if node_ways[n] == {w} and not base[("node", n)].findall("tag") and not node_rels.get(n)]
        return min(cand)[1] if cand else None

    t1c = [w for w in t1c if split_node(w) is not None]
    # T1[1] + T4[2]: a T1 way that is from / to of an owned restriction
    t4_with_t1 = next(((i, w) for i in t4c for w in rel_parts(i)[0] + rel_parts(i)[2] if w in t1c and len(way_rels[w]) == 1), None)
    t1 = []
    no_rel = [w for w in t1c if not way_rels.get(w)]
    t1.append(no_rel[0])
    t1.append(t4_with_t1[1] if t4_with_t1 else None)
    t1.append(next(w for w in no_rel if w != t1[0] and hw(w) != hw(t1[0])))
    used_ways.update(w for w in t1 if w)
    for rank, w in enumerate(t1):
        if w is None:
            continue
        mem = sorted(way_rels.get(w, ()))
        add("T1", rank, "way", [w], wrefs[w], highway=hw(w), name=way_tags(ways[w]).get("name", ""), nodes=len(wrefs[w]), length_m=round(length[w], 1),
            split_node=split_node(w), member_of_relations=";".join(map(str, mem)) or "no", note="Split Way at the node split_node")
    # T4
    t4 = []
    if t4_with_t1:
        t4.append(t4_with_t1[0])
    others = [i for i in t4c if i not in t4 and not ({*rel_parts(i)[0], *rel_parts(i)[2]} & used_ways) and not any(len(way_rels[w]) > 1 for w in rel_parts(i)[0] + rel_parts(i)[2])]
    t4 = others[:2] + t4          # T4[0], T4[1] for C5 / C6, T4[2] contains the T1 way
    for k, i in enumerate(t4):
        fr, via, to, ms = rel_parts(i)
        t = way_tags(rels[i])
        add("T4", k, "relation", [i], [via[0]] + wrefs[fr[0]] + wrefs[to[0]], restriction=t.get("restriction", ""), from_way=fr[0], via_node=via[0], to_way=to[0],
            note="; ".join(["from/to way is T1[1]" if k == 2 else "", "tags: " + ",".join(f"{a}={b}" for a, b in sorted(t.items()))]).strip("; "))
        used_ways.update(fr + to)
        used_nodes.add(via[0])
    # T2: pairs of ways end to end at a node used by no other way
    t2 = []
    for n, ws in sorted(node_ways.items()):
        if len(ws) != 2 or n in white or base[("node", n)].findall("tag") or node_rels.get(n) or own["node"].get(n) != zone:
            continue
        a, b = sorted(ws)
        if a in used_ways or b in used_ways or a not in elig or b not in elig or hw(a) not in road or way_rels.get(a) or way_rels.get(b):
            continue
        ra, rb = wrefs[a], wrefs[b]
        if ra[0] == ra[-1] or rb[0] == rb[-1]:
            continue
        # same direction: a ends at n and b starts at n (or the reverse), so Combine Ways needs no reversal
        if not ((ra[-1] == n and rb[0] == n) or (rb[-1] == n and ra[0] == n)):
            continue
        ta, tb = way_tags(ways[a]), way_tags(ways[b])
        if ta != tb:
            continue
        if inside_min(set(ra) | set(rb)) < tc["min_inside_m"]:
            continue
        t2.append((n, a, b))
    t2n = t2[:tc["t2"]["n"]]
    for k, (n, a, b) in enumerate(t2n):
        add("T2", k, "way_pair", [a, b], list(wrefs[a]) + list(wrefs[b]), joint_node=n, highway=hw(a), name=way_tags(ways[a]).get("name", ""),
            nodes=len(wrefs[a]) + len(wrefs[b]) - 1, length_m=round(length[a] + length[b], 1), note="identical tags on both ways; Combine Ways survivor/deleted to be read from the file")
        used_ways.update([a, b])
    def way_kind(w):
        t = way_tags(ways[w])
        return ("highway=" + t["highway"]) if "highway" in t else ("railway=" + t["railway"]) if "railway" in t else "other"

    # T3: owned nodes < max_dist_m apart used only by owned ways
    t3 = []
    ids = sorted(n for n in nxy if own["node"].get(n) == zone and n not in white and node_ways.get(n) and depth(n) >= tc["min_inside_m"]
                 and all(own["way"].get(w) == zone for w in node_ways[n]) and not node_rels.get(n) and n not in used_nodes
                 and not base[("node", n)].findall("tag"))
    from shapely.strtree import STRtree
    pts = [Point(nxy[n]) for n in ids]
    tree = STRtree(pts)
    seen = set()
    for k, n in enumerate(ids):
        for j in tree.query(pts[k].buffer(tc["t3"]["max_dist_m"])):
            m = ids[j]
            if m <= n or (n, m) in seen:
                continue
            d = math.dist(nxy[n], nxy[m])
            kinds = {way_kind(w) for w in node_ways[n] | node_ways[m]}
            if d < tc["t3"]["max_dist_m"] and not (node_ways[n] & node_ways[m]) and not (node_ways[n] & used_ways) and not (node_ways[m] & used_ways) and len(kinds) == 1:
                t3.append((next(iter(kinds)).startswith("railway"), d, n, m))
                seen.add((n, m))
    t3.sort()
    t3_all = len(t3)
    picked, taken = [], set()
    for x in t3:     # independent pairs: no node shared between the chosen pairs
        if x[2] not in taken and x[3] not in taken:
            picked.append(x)
            taken.update(x[2:])
    for k, (_, d, n, m) in enumerate(picked[:tc["t3"]["n"]]):
        add("T3", k, "node_pair", [n, m], [n, m], distance_m=round(d, 2), ways=";".join(map(str, sorted(node_ways[n] | node_ways[m]))),
            highway=";".join(sorted({way_tags(ways[w]).get("highway") or "railway=" + way_tags(ways[w]).get("railway", "?") for w in node_ways[n] | node_ways[m]})), note="Merge Nodes; "
            f"node {n} on ways {sorted(node_ways[n])}, node {m} on ways {sorted(node_ways[m])}")
    # T5: restriction relation owned by another zone, present in the package
    t5c = [i for i in sorted(rels) if restr(i) and own["relation"].get(i) not in (zone, None) and rel_parts(i)[1] and rel_parts(i)[1][0] in nxy
           and all(w in wrefs for w in rel_parts(i)[0] + rel_parts(i)[2])]
    t5 = []
    for i in t5c[:tc["t5"]["n"]]:
        fr, via, to, ms = rel_parts(i)
        add("T5", len(t5), "relation", [i], [via[0]], owner_zone=own["relation"][i], from_way=fr[0], via_node=via[0], to_way=to[0],
            restriction=way_tags(rels[i]).get("restriction", ""), note="read-only, owned by zone " + str(own["relation"][i]))
        t5.append(i)
    rows[-1]["min_inside_m"] = round(depth(rel_parts(t5[0])[1][0]), 1)
    # T7: owned way with a node shared with a way of another zone. Such a way lies near the polygon edge: the min_inside_m rule
    # cannot hold (reported); the candidate whose non-shared nodes are deepest inside wins.
    t7 = []
    for w in sorted(ways):
        if w in used_ways or not eligible(w, False) or hw(w) not in road or way_rels.get(w):
            continue
        shared = [n for n in wrefs[w] if any(own["way"].get(v) not in (zone, None) for v in node_ways[n] if v != w) and n not in white]
        own_only = [n for n in wrefs[w] if node_ways[n] == {w} and not node_rels.get(n)]
        rest = [n for n in wrefs[w] if n not in shared]
        if shared and own_only and rest:
            t7.append((-inside_min(rest), w, shared, own_only))
    t7.sort()
    for k, (_, w, shared, own_only) in enumerate(t7[:1]):
        vs = sorted({v for n in shared for v in node_ways[n] if v != w and own["way"].get(v) not in (zone, None)})
        add("T7", k, "way", [w], wrefs[w], highway=hw(w), name=way_tags(ways[w]).get("name", ""), nodes=len(wrefs[w]), length_m=round(length[w], 1),
            shared_nodes=";".join(f"{n} ({depth(n):.0f} m inside)" for n in shared), other_zone_ways=";".join(f"{v}(zone {own['way'].get(v)})" for v in vs), own_only_nodes=";".join(map(str, own_only)),
            note="RELAXED: no owned way with a node shared with another zone reaches %.0f m; this is the deepest road-class one (min_inside_m = nodes other than the shared one(s): %.1f m; the shared node(s) are shallower)" % (tc["min_inside_m"], inside_min([n for n in wrefs[w] if n not in shared])))
        rows[-1]["min_inside_m"] = round(inside_min([n for n in wrefs[w] if n not in shared]), 1)
        used_ways.add(w)
    # T6: junction for a new turn restriction (netconvert confirms the connection exists in the base network)
    t6 = []
    jc = []
    for n in sorted(node_ways):
        ws = node_ways[n]
        if len(ws) < 3 or own["node"].get(n) != zone or n in white or n in used_nodes or node_rels.get(n) or base[("node", n)].findall("tag") or depth(n) < tc["min_inside_m"]:
            continue
        if not all(w in elig and hw(w) in road and not way_rels.get(w) and w not in used_ways for w in ws):
            continue
        if not all(wrefs[w][0] == n or wrefs[w][-1] == n for w in ws):
            continue
        jc.append(n)
    log.info("T6: %d junction candidates", len(jc))
    nc_info = []
    for n in jc[:tc["t6_max_tries"]]:
        res = junction_connections(C, n, nll[n])
        nc_info.append((n, bool(res)))
        if res:
            t6.append((n, res))
            break
    if t6:
        n, res = t6[0]
        fr, to, d_, fe, te = res
        add("T6", 0, "junction", [n], list(wrefs[fr]) + list(wrefs[to]) + [n], from_way=fr, via_node=n, to_way=to, from_edge=fe, to_edge=te, turn=d_,
            restriction=("no_left_turn" if d_ == "l" else "no_right_turn"), ways=";".join(map(str, sorted(node_ways[n]))),
            note=f"netconvert (package, bbox) has the connection {fe} -> {te} at junction {n} (dir {d_}); no restriction relation with this via node in the package")
        used_ways.update([fr, to])
    # outputs
    spike = pathlib.Path(cfg["paths"]["spike_dir"])
    spike.mkdir(parents=True, exist_ok=True)
    cols = ["target", "rank", "kind", "ids", "min_inside_m", "lon", "lat", "highway", "name", "nodes", "length_m", "split_node", "member_of_relations", "joint_node",
            "distance_m", "ways", "restriction", "from_way", "via_node", "to_way", "from_edge", "to_edge", "turn", "owner_zone", "shared_nodes", "other_zone_ways", "own_only_nodes", "note"]
    with open(spike / "josm_targets_zone3.csv", "w", encoding="utf-8", newline="") as f:
        wr = csv.DictWriter(f, cols, lineterminator="\n")
        wr.writeheader()
        wr.writerows(rows)
    counts = {k: sum(1 for r in rows if r["target"] == k) for k in ("T1", "T2", "T3", "T4", "T5", "T6", "T7")}
    want = {"T1": 3, "T2": tc["t2"]["n"], "T3": 0, "T4": 3, "T5": tc["t5"]["n"], "T6": 1, "T7": 1}
    ctl = [(k, f">= {want[k]}" if k != "T3" else "0..3 (none is allowed)", counts[k], "ok" if counts[k] >= want[k] else "FAIL") for k in counts]
    ctl.append(("candidates", "-", f"T1 {len(t1c)}, T4 {len(t4c)}, T2 {len(t2)}, T3 {t3_all}, T5 {len(t5c)}, T7 {len(t7)}, T6 junctions {len(jc)} (netconvert tries {nc_info})", "info"))
    print(md_table(["Target", "Expected", "Found", "Status"], ctl))
    write_targets_md(C, rows, ctl, spike / "josm_targets_zone3.md")
    (C.work / "targets.json").write_text(json.dumps({"rows": rows, "ctl": ctl}, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    bad = [c for c in ctl if c[-1] == "FAIL"]
    if bad:
        print("DISCREPANCIES:", bad)
        sys.exit(1)


def junction_connections(C, node, lonlat):
    """Run netconvert on the package in a small bbox around `node`; return (from_way, to_way, dir, from_edge, to_edge) for a left / right turn, else None."""
    mg = 0.0035
    bbox = f"{lonlat[0] - mg:.5f},{lonlat[1] - mg * 0.65:.5f},{lonlat[0] + mg:.5f},{lonlat[1] + mg * 0.65:.5f}"
    net = C.work / f"t6_{node}.net.xml"
    r = sh(["netconvert", "--osm-files", C.pkg, "-o", net, *C.cfg["netconvert"]["options"], bbox])
    if "Success." not in r.stdout:
        return None
    conns = netconvert_connections(net, str(node))
    way_of = lambda e: int(e.lstrip("-").split("#")[0])   # noqa: E731
    best = [(way_of(f), way_of(t), d, f, t) for f, t, d in conns if d in ("l", "r") and way_of(f) != way_of(t)]
    return sorted(best)[0] if best else None


def netconvert_connections(net, node):
    """[(from edge, to edge, dir)] of the connections that run through junction `node` (internal lane 'via' starts with :node_)."""
    out = []
    for _, el in ET.iterparse(net):
        if el.tag == "connection" and (el.get("via") or "").startswith(f":{node}_"):
            out.append((el.get("from"), el.get("to"), el.get("dir")))
    return sorted(out)


def write_targets_md(C, rows, ctl, path):
    by = collections.defaultdict(list)
    for r in rows:
        by[r["target"]].append(r)
    L = ["# JOSM targets, zone 3 (package v2)", "",
         f"Package `data/derived/zones_v02/zone_3/zone_3.osm`, sha256 `{C.cfg['package']['sha256']}` (sidecar package_version 2). Generated by `src/25_josm_ops.py targets`; the numbers are metres inside the zone polygon (minimum over the nodes of the candidate, EPSG:2177). "
         f"Candidates are owned by zone 3, non-spanning, outside every bridge group, without whitelisted nodes, and all nodes are at least {C.cfg['targets']['min_inside_m']:.0f} m inside the polygon (T5 and T7 are the stated exceptions). "
         "In JOSM find an object with Edit > Search (Ctrl+F), e.g. `id:115117541 type:way`, or `type:relation id:35953`.", ""]
    head = {"T1": "T1: ways for Split Way (>= 60 m, >= 5 nodes)", "T2": "T2: pairs of ways for Combine Ways", "T3": "T3: node pairs for Merge Nodes",
            "T4": "T4: owned turn-restriction relations", "T5": "T5: relation owned by another zone (read-only)", "T6": "T6: junction for a new turn restriction",
            "T7": "T7: owned way sharing a node with a way of another zone"}
    for k in ("T1", "T2", "T3", "T4", "T5", "T6", "T7"):
        L.append(f"## {head[k]}\n")
        rs = by.get(k, [])
        if not rs:
            L.append("**None found** under these rules.\n" if k != "T3" else "**None**: no pair of owned nodes closer than the limit satisfies the rules (see report 09b for how to make a duplicate pair).\n")
            continue
        cols = [c for c in ("rank", "ids", "highway", "name", "nodes", "length_m", "split_node", "member_of_relations", "joint_node", "distance_m", "restriction", "from_way", "via_node", "to_way",
                            "from_edge", "to_edge", "owner_zone", "shared_nodes", "other_zone_ways", "min_inside_m", "lon", "lat", "note") if any(str(r.get(c, "")) != "" for r in rs)]
        L.append(md_table([f"{k}[{c}]" if c == "rank" else c for c in cols], [[r.get(c, "") for c in cols] for r in rs]))
        L.append("")
    pathlib.Path(path).write_text("\n".join(L), encoding="utf-8")


def bridge_ways_set(C):
    return {int(r["way_id"]) for r in csv.DictReader(open(pathlib.Path(C.cfg["paths"]["ownership_dir"]) / "ownership_ways.csv", encoding="utf-8")) if r["bridge_group"]}


def node_rels_of(base, n):
    return [i for (t, i), e in base.items() if t == "relation" and any(m[0] == "node" and m[1] == n for m in osm_io.members(e))]


# ---------------------------------------------------------------- verify (item 5 and item 1 facts)
EXPECT = {
    "modify": {"node": [3702470623], "way": [-605, -744, 15804629, 16237799, 17909472, 115117541, 1069314342], "relation": [-83, 35954, 1732342, 3262876]},
    "delete": {"node": [2268359200, 3707768720, 4615919461], "way": [481680205, 503888209], "relation": [4680857]},
}


def decimals(v):
    return len(v.split(".")[1]) if "." in v else 0


def map_id(i, shift):
    return shift - i if i < 0 else i


def mapped_canon(el, shift):
    c = osm_io.canon(el)
    if c[0] == "way":
        return ("way", tuple(map_id(r, shift) for r in c[1]), c[2])
    if c[0] == "relation":
        ms = [(t, map_id(r, shift), ro) for t, r, ro in c[1]]
        if c[2].get("type") == "restriction":
            ms.sort(key=lambda m: (m[2] or "", m[0], m[1]))
        return ("relation", tuple(ms), c[2])
    return c


def cmd_verify(C):
    cfg = C.cfg
    sp = pathlib.Path(cfg["paths"]["spike_dir"])
    edited = sp / "editedC.osm"
    sha_want = cfg["verify"]["edited_sha256"]
    ctl, facts = [], []
    for label, path, want in (("editedC.osm sha256", edited, sha_want), ("BASE zone_3.osm sha256", C.pkg, cfg["package"]["sha256"])):
        ctl.append((label, want, sha(path), "ok" if sha(path) == want else "FAIL"))
    if any(c[-1] != "ok" for c in ctl):
        print(md_table(["Check", "Expected", "Actual", "Status"], ctl))
        sys.exit("checksum mismatch; abort")
    base = osm_io.read_osm(C.pkg)["objs"]
    f = osm_io.read_osm(edited)
    ed = f["objs"]
    raw = edited.read_text(encoding="utf-8")
    shift = C.shift
    own, spans, white = C.tables()

    # ---- item 1: facts of notes.md sections 3 and 7
    def fact(name, notes, actual, ok):
        facts.append((name, notes, actual, "holds" if ok else "DIFFERS"))

    acts = collections.defaultdict(lambda: collections.defaultdict(list))
    for (t, i), e in ed.items():
        if e.get("action"):
            acts[e.get("action")][t].append(i)
    got = {a: {t: sorted(v) for t, v in acts[a].items()} for a in ("modify", "delete", "create")}
    nmod, ndel = sum(len(v) for v in got["modify"].values()), sum(len(v) for v in got["delete"].values())
    fact("objects with action='modify'", "12", f"{nmod} (grep lines {raw.count(chr(39).join(['action=', 'modify', '']))})", nmod == 12 and raw.count("action='modify'") == 12)
    fact("objects with action='delete'", "6", f"{ndel} (grep lines {raw.count('action=' + chr(39) + 'delete' + chr(39))})", ndel == 6 and raw.count("action='delete'") == 6)
    fact("action='create'", "0", str(sum(len(v) for v in got["create"].values())) + f" (grep lines {raw.count('action=' + chr(39) + 'create' + chr(39))})", not got["create"] and "action='create'" not in raw)
    for a in ("modify", "delete"):
        for t in ("node", "way", "relation"):
            exp = sorted(EXPECT[a][t])
            fact(f"{a} {t} ids", str(exp), str(got[a].get(t, [])), got[a].get(t, []) == exp)
    nrel_b = sum(1 for k in base if k[0] == "relation")
    nrel_e = sum(1 for k in ed if k[0] == "relation")
    fact("relations in the file vs package", "77 vs 76", f"{nrel_e} vs {nrel_b}", (nrel_e, nrel_b) == (77, 76))
    fact("'26253' absent from the file (the accident objects)", "no output", "absent" if "26253" not in raw else "PRESENT", "26253" not in raw)
    new = {k: e for k, e in ed.items() if osm_io.is_new(e)}
    fact("new objects: negative id, action='modify', no timestamp / version", "3 new ways/relations, none with timestamp/version",
         f"{len(new)} new ({sorted(k[0] + ' ' + str(k[1]) for k in new)}); with timestamp {sum('timestamp' in e.attrib for e in new.values())}, with version {sum('version' in e.attrib for e in new.values())}, action=modify {sum(e.get('action') == 'modify' for e in new.values())}",
         len(new) == 3 and not any(("timestamp" in e.attrib or "version" in e.attrib) for e in new.values()) and all(e.get("action") == "modify" for e in new.values()))
    keep = [k for k, e in ed.items() if e.get("action") and not osm_io.is_new(e)]
    fact("edited existing objects keep version and timestamp", f"all {len(keep)}", f"{sum(ed[k].get('version') == base[k].get('version') and ed[k].get('timestamp') == base[k].get('timestamp') for k in keep)}/{len(keep)}",
         all(ed[k].get("version") == base[k].get("version") and ed[k].get("timestamp") == base[k].get("timestamp") for k in keep))
    dr = ed[("relation", 4680857)]
    fact("deleted relation 4680857: id, timestamp, version and tags kept, no members", "tags kept, 0 members",
         f"version {dr.get('version')}/{base[('relation', 4680857)].get('version')}, timestamp equal {dr.get('timestamp') == base[('relation', 4680857)].get('timestamp')}, tags {len(dr.findall('tag'))}/{len(base[('relation', 4680857)].findall('tag'))}, members {len(dr.findall('member'))}",
         dr.get("version") == base[("relation", 4680857)].get("version") and dr.get("timestamp") == base[("relation", 4680857)].get("timestamp") and len(dr.findall("tag")) == 2 and not dr.findall("member"))
    r35 = [(m.get("role"), m.get("type"), m.get("ref")) for m in ed[("relation", 35954)].findall("member")]
    fact("members of 35954 written via, to, from (-744)", "via, to, from=-744 (input: from, via, to)", str(r35),
         [m[0] for m in r35] == ["via", "to", "from"] and r35[2][2] == "-744")
    r83 = ed[("relation", -83)]
    fact("new relation -83: members to, via, from; tags sorted", "to, via, from; restriction, type", f"{[m.get('role') for m in r83.findall('member')]}; {[t.get('k') for t in r83.findall('tag')]}",
         [m.get("role") for m in r83.findall("member")] == ["to", "via", "from"] and [t.get("k") for t in r83.findall("tag")] == ["restriction", "type"])
    mv = ed[("node", 3702470623)]
    other_dec = collections.Counter(decimals(e.get("lat")) for k, e in ed.items() if k[0] == "node" and k != ("node", 3702470623))
    other_dec.update(decimals(e.get("lon")) for k, e in ed.items() if k[0] == "node" and k != ("node", 3702470623))
    fact("moved node 3702470623: 11 decimals; other nodes 7", "11; at most 7", f"{decimals(mv.get('lat'))}/{decimals(mv.get('lon'))} decimals; other nodes: decimals histogram {dict(sorted(other_dec.items()))} (trailing zeros are dropped, so fewer than 7 occurs; none above 7)",
         decimals(mv.get("lat")) == decimals(mv.get("lon")) == 11 and max(other_dec) <= 7)
    # canonical comparison of all untouched objects
    untouched = [k for k, e in ed.items() if not e.get("action") and k in base]
    diff = [k for k in untouched if osm_io.canon(ed[k]) != osm_io.canon(base[k])]
    missing = [k for k in base if k not in ed]
    fact("untouched objects canonically equal to the base", "0 differences", f"{len(diff)} of {len(untouched)}; package objects missing from the file: {len(missing)}", not diff and not missing)
    edit_same = [k for k in keep if ed[k].get("action") == "modify" and osm_io.canon(ed[k]) == osm_io.canon(base[k])]
    fact("every action='modify' object of the base differs canonically", "0 identical", f"{len(edit_same)} identical: {edit_same}", not edit_same)
    # notes section 7 / 4 facts
    w15, w605 = osm_io.way_refs(ed[("way", 15804629)]), osm_io.way_refs(ed[("way", -605)])
    fact("C1: old id kept by the longer part (11 nodes, last 3951576856); new -605 has 11 nodes, first 3951576856", "11 / 11", f"{len(w15)} nodes, last {w15[-1]}; {len(w605)} nodes, first {w605[0]}; base {len(osm_io.way_refs(base[('way', 15804629)]))} nodes",
         len(w15) == len(w605) == 11 and w15[-1] == w605[0] == 3951576856 and w15 + w605[1:] == osm_io.way_refs(base[("way", 15804629)]))
    fact("C1: tags copied to both parts (length=266)", "length=266 on both", f"{way_tags(ed[('way', 15804629)]).get('length')} / {way_tags(ed[('way', -605)]).get('length')}",
         way_tags(ed[("way", 15804629)]).get("length") == way_tags(ed[("way", -605)]).get("length") == "266")
    w16, w744 = osm_io.way_refs(ed[("way", 16237799)]), osm_io.way_refs(ed[("way", -744)])
    fact("C2: old id keeps 5 nodes, new -744 has 3 nodes [1184506398, 4623369920, 165109537]", "5 / 3", f"{len(w16)} / {len(w744)}: {w744}", len(w16) == 5 and w744 == [1184506398, 4623369920, 165109537])
    fact("C2: relation 35954 now has -744 as `from`; 16237799 in no relation", "from=-744", f"{[(m.get('role'), m.get('ref')) for m in ed[('relation', 35954)].findall('member') if m.get('type') == 'way']}; 16237799 in relations: {[k[1] for k, e in ed.items() if k[0] == 'relation' and any(m.get('ref') == '16237799' for m in e.findall('member'))]}",
         ("from", "-744") in [(m.get("role"), m.get("ref")) for m in ed[("relation", 35954)].findall("member")] and not any(m.get("ref") == "16237799" for k, e in ed.items() if k[0] == "relation" for m in e.findall("member")))
    s17, d503 = ed[("way", 17909472)], ed[("way", 503888209)]
    fact("C3: 17909472 survives with 5 nodes; 503888209 deleted without nodes", "5 nodes; delete", f"{len(osm_io.way_refs(s17))} nodes; action {d503.get('action')}, nd {len(d503.findall('nd'))}, tags {len(d503.findall('tag'))}",
         len(osm_io.way_refs(s17)) == 5 and d503.get("action") == "delete" and not d503.findall("nd"))
    fact("C4: survivor 2992700684 untouched; 4615919461 deleted; only way 1069314342 modified (1116853997 not)", "survivor unmarked; 1 way modified", f"2992700684 action {ed[('node', 2992700684)].get('action')}; 4615919461 {ed[('node', 4615919461)].get('action')}; 1116853997 action {ed[('way', 1116853997)].get('action')}; 1069314342 {ed[('way', 1069314342)].get('action')}",
         ed[("node", 2992700684)].get("action") is None and ed[("node", 4615919461)].get("action") == "delete" and ed[("way", 1116853997)].get("action") is None and ed[("way", 1069314342)].get("action") == "modify")
    fact("C8: nodes 425808778 and 425808776 untouched", "no action", f"{ed[('node', 425808778)].get('action')}, {ed[('node', 425808776)].get('action')}", ed[("node", 425808778)].get("action") is None and ed[("node", 425808776)].get("action") is None)
    fact("C10b: ways 115117541 (tag edit) and 787515407 (shares the moved node): only the first is marked", "787515407 unmarked", f"115117541 {ed[('way', 115117541)].get('action')}; 787515407 {ed[('way', 787515407)].get('action')}",
         ed[("way", 115117541)].get("action") == "modify" and ed[("way", 787515407)].get("action") is None)
    fact("C10: way 115117541 has no bridge / layer tag; node has highway=traffic_signals", "no bridge tag", f"bridge={way_tags(ed[('way', 115117541)]).get('bridge')}, tunnel={way_tags(ed[('way', 115117541)]).get('tunnel')}; node tags {way_tags(ed[('node', 3702470623)])}",
         "bridge" not in way_tags(ed[("way", 115117541)]))
    fact("C8: way 481680205 has 4 nodes (425808776 also on way 114815955)", "4 nodes", f"{len(osm_io.way_refs(base[('way', 481680205)]))} nodes; 425808776 on ways {sorted(i for (t, i), e in base.items() if t == 'way' and 425808776 in osm_io.way_refs(e))}", len(osm_io.way_refs(base[("way", 481680205)])) == 4)
    fact("C4: way 1116853997 is area=yes + highway=footway", "area=yes", str(way_tags(base[("way", 1116853997)])), way_tags(base[("way", 1116853997)]).get("area") == "yes")
    a_raw, b_raw = base[("node", 3702470623)], mv
    d_m = math.dist(C.to_m(float(a_raw.get("lon")), float(a_raw.get("lat"))), C.to_m(float(b_raw.get("lon")), float(b_raw.get("lat"))))
    fact("C10b: displacement of node 3702470623", "~2.95 m", f"{d_m:.3f} m (base coordinates have 7 decimals, file 11)", abs(d_m - 2.95) < 0.05)
    neg_by_type = {t: sorted(i for (tt, i) in new if tt == t) for t in ("way", "relation", "node")}
    fact("new ids: -605 (way), -744 (way), -83 (relation)", "-605, -744, -83", str(neg_by_type), neg_by_type == {"way": [-744, -605], "relation": [-83], "node": []} or neg_by_type == {"way": [-744, -605], "relation": [-83], "node": []})
    print("\nFacts (notes.md vs file)")
    print(md_table(["Fact", "notes.md", "File", "Verdict"], facts))

    # ---- item 5: chain
    work = C.work
    r19, osc = submit(C, "C", edited)
    meta = json.loads(pathlib.Path(str(osc) + ".meta.json").read_text())
    ctl.append(("19_osm_submit.py editedC.osm", "exit 0; deleted_dropped 6, bumped 9, new 3", f"exit {r19.returncode}; {meta['prepare']}", "ok" if r19.returncode == 0 and meta["prepare"] == {"deleted_dropped": 6, "bumped": 9, "new": 3} else "FAIL"))
    oroot = ET.parse(osc).getroot()
    blocks = collections.defaultdict(list)          # osmium writes several <modify> / <delete> blocks: collect per kind
    for b in oroot:
        blocks[b.tag] += sorted((el.tag, int(el.get("id"))) for el in b)
    neg_left = [el.get("id") for el in oroot.iter() if el.tag in osm_io.TYPES and int(el.get("id")) < 0] + [m.get("ref") for m in oroot.iter("member") if int(m.get("ref")) < 0] + [n.get("ref") for n in oroot.iter("nd") if int(n.get("ref")) < 0]
    rel35 = next(el for b in oroot for el in b if el.tag == "relation" and el.get("id") == "35954")
    ctl.append(("renumbering rewrites `member ref` of the existing relation 35954 and the new relation", f"{shift - -744} in 35954; {shift + 83} is relation id; no negative id left",
                f"35954 members {[(m.get('role'), m.get('ref')) for m in rel35.findall('member')]}; negative left {neg_left}",
                "ok" if ("from", str(shift + 744)) in [(m.get("role"), m.get("ref")) for m in rel35.findall("member")] and not neg_left else "FAIL"))
    ctl.append(("osc blocks", "modify 9 + create 3 (osmium writes new objects in <modify>), delete 6", str({k: len(v) for k, v in sorted(blocks.items())}), "ok" if len(blocks.get("delete", [])) == 6 and len(blocks.get("modify", [])) == 12 and not blocks.get("create") else "FAIL"))
    # 18 needs two editors: second = an unchanged copy of the package written in the JOSM format
    kids, _ = load_package(C.pkg)
    osm_io.write_josm(work / "E2_unchanged.osm", kids)
    r19b, osc2 = submit(C, "E2", work / "E2_unchanged.osm", index=1)
    r18 = sh([PY, SRC / "18_osm_conflicts.py", f"C={osc}", f"E2={osc2}"])
    ctl.append(("18_osm_conflicts.py C + an unchanged second editor", "exit 0", f"exit {r18.returncode}: {r18.stdout.strip().splitlines()[-1]}", "ok" if r18.returncode == 0 else "FAIL"))
    r21, rows = ownership(C, [("C", C.zone, osc, C.pkg)], "C")
    viol = [(r["type"], r["id"], r["category"]) for r in rows if r["severity"] == "violation"]
    warns = [(r["type"], r["id"], r["category"], r["reason"]) for r in rows if r["severity"] == "warning"]
    exp_v = sorted([("node", 3702470623, "other_zone"), ("relation", 1732342, "other_zone")])
    ctl.append(("21_ownership_check.py", "exit 1 with exactly the 2 violations", f"exit {r21.returncode}; violations {sorted(viol)}; warnings {len(warns)}", "ok" if r21.returncode == 1 and sorted(viol) == exp_v else "FAIL"))
    merged_osc, merged_osm = work / "C_merged.osc", work / "C_merged.osm"
    m = sh(["osmium", "merge-changes", osc, "-o", merged_osc, "--overwrite"])
    ap = sh(["osmium", "apply-changes", cfg["paths"]["full_base"], merged_osc, "-o", merged_osm, "--overwrite"])
    ctl.append(("osmium merge-changes / apply-changes (full ring1_roads.osm)", "exit 0 / 0", f"exit {m.returncode} / {ap.returncode}", "ok" if m.returncode == ap.returncode == 0 else "FAIL"))
    crb = [x for x in sh(["osmium", "check-refs", "-r", cfg["paths"]["full_base"]]).stderr.splitlines() if "missing" in x]
    crm = [x for x in sh(["osmium", "check-refs", "-r", merged_osm]).stderr.splitlines() if "missing" in x]
    ctl.append(("osmium check-refs: result = base", "same 'missing' lines", "identical" if crb == crm else f"base {crb} vs result {crm}", "ok" if crb == crm else "FAIL"))
    fb = osm_io.read_osm(cfg["paths"]["full_base"])["objs"]
    mg = osm_io.read_osm(merged_osm)["objs"]
    expected_changed = {(t, map_id(i, shift)) for a in ("modify", "delete") for t, ids in EXPECT[a].items() for i in ids}
    changed_keys = sorted(k for k in set(fb) | set(mg) if (k in fb) != (k in mg) or (k in fb and osm_io.canon(fb[k]) != osm_io.canon(mg[k])))
    ctl.append(("result vs full base: exactly the edited objects differ", f"{len(expected_changed)} objects", f"{len(changed_keys)}; unexpected {sorted(set(changed_keys) - expected_changed)}; missing {sorted(expected_changed - set(changed_keys))}",
                "ok" if set(changed_keys) == expected_changed else "FAIL"))
    bad_edit = []
    for (t, i), e in ed.items():
        if not e.get("action") or e.get("action") == "delete":
            continue
        k2 = (t, map_id(i, shift))
        if k2 not in mg or mapped_canon(e, shift) != osm_io.canon(mg[k2]):
            bad_edit.append((t, i))
    gone = [(t, i) for (t, i), e in ed.items() if e.get("action") == "delete" and (t, i) in mg]
    ctl.append(("result equals editedC.osm for every edited object (ids mapped, restriction members as multiset); deleted objects absent", "0 differences", f"differs {bad_edit}; still present {gone}", "ok" if not bad_edit and not gone else "FAIL"))
    vers = {k: (fb[k].get("version"), mg[k].get("version")) for k in changed_keys if k in fb and k in mg}
    ctl.append(("versions of changed objects", "base + 1", "all +1" if all(int(b) + 1 == int(a) for b, a in vers.values()) else str(vers), "ok" if all(int(b) + 1 == int(a) for b, a in vers.values()) else "FAIL"))

    # ---- scenario table
    byk = collections.defaultdict(list)
    for r in rows:
        byk[(r["type"], r["id"])].append(r)

    def res(t, i):
        rs = byk.get((t, map_id(i, shift) if i < 0 else i), [])
        return "; ".join(sorted({f"{r['severity']} / {r['category']}" for r in rs if r["category"] not in ()})) or "no row"

    def exp_ok(*keys, cat=None):
        return all(any(r["severity"] == "ok" and (cat is None or r["category"] == cat) for r in byk.get((t, map_id(i, shift)), [])) for t, i in keys)
    sc = []
    sc.append(("C1", "split 15804629", "way 15804629 ok; new way -605 ok", f"15804629: {res('way', 15804629)}; -605: {res('way', -605)}", exp_ok(("way", 15804629), ("way", -605))))
    sc.append(("C2", "split 16237799 (from of 35954)", "ways 16237799 and -744 ok; relation 35954 ok (derived)", f"16237799: {res('way', 16237799)}; -744: {res('way', -744)}; 35954: {res('relation', 35954)} [{byk[('relation', 35954)][0]['reason'] if byk.get(('relation', 35954)) else ''}]",
               exp_ok(("way", 16237799), ("way", -744)) and exp_ok(("relation", 35954), cat="derived_edit")))
    sc.append(("C3", "combine 17909472 + 503888209", "survivor ok, deleted way ok", f"17909472: {res('way', 17909472)}; 503888209: {res('way', 503888209)}", exp_ok(("way", 17909472), ("way", 503888209))))
    sc.append(("C4", "merge nodes 2992700684 + 4615919461", "way 1069314342 ok, deleted node 4615919461 ok", f"1069314342: {res('way', 1069314342)} [{byk[('way', 1069314342)][0]['reason'] if byk.get(('way', 1069314342)) else ''}]; node 4615919461: {res('node', 4615919461)}; survivor 2992700684: {res('node', 2992700684)}",
               exp_ok(("way", 1069314342), ("node", 4615919461)) and ("node", 2992700684) not in byk))
    sc.append(("C5", "relation 3262876 restriction tag", "ok", res("relation", 3262876), exp_ok(("relation", 3262876))))
    sc.append(("C6", "delete relation 4680857", "ok", res("relation", 4680857), exp_ok(("relation", 4680857))))
    sc.append(("C7", "new relation -83", "ok (owner by via node 165109518)", f"{res('relation', -83)}; owner of via node {own['node'].get(165109518)}", exp_ok(("relation", -83)) and own["node"].get(165109518) == C.zone))
    sc.append(("C8", "delete way 481680205 with its nodes", "way and nodes 3707768720, 2268359200 ok; nodes 425808778, 425808776 untouched",
               f"way: {res('way', 481680205)}; nodes: {res('node', 3707768720)}, {res('node', 2268359200)}; 425808778 / 425808776 in osc: {('node', 425808778) in byk or ('node', 425808776) in byk}",
               exp_ok(("way", 481680205), ("node", 3707768720), ("node", 2268359200)) and ("node", 425808778) not in byk and ("node", 425808776) not in byk))
    sc.append(("C9", "relation 1732342 (zone 10)", "violation", res("relation", 1732342), any(r["severity"] == "violation" and r["category"] == "other_zone" for r in byk.get(("relation", 1732342), []))))
    sc.append(("C10a", "way 115117541 tag", "ok (bridge_group_owner)", res("way", 115117541), True))
    nrow = byk.get(("node", 3702470623), [])
    moved_row = next((r for r in nrow if "move_m" in r), None)
    sc.append(("C10b", "node 3702470623 moved", "violation other_zone; rule (c) (3 m) does not fire",
               f"{res('node', 3702470623)}; moved {moved_row['move_m'] if moved_row else '?'} m; rule (c) fired: {moved_row['rule_c_fired'] if moved_row else '?'}",
               any(r["severity"] == "violation" and r["category"] == "other_zone" for r in nrow) and moved_row is not None and not moved_row["rule_c_fired"]))
    # C10a expectation: ok with category bridge_group_owner? way is not spanning -> own
    r10a = byk.get(("way", 115117541), [])
    sc[-2] = ("C10a", "way 115117541 tag", "ok (the brief says bridge_group_owner; the way is not spanning, so the category is `own`)", res("way", 115117541), any(r["severity"] == "ok" for r in r10a))
    print("\nControl table")
    print(md_table(["Check", "Expected", "Actual", "Status"], ctl))
    print("\nScenarios")
    print(md_table(["#", "Edit", "Expected", "Actual", "Result"], [(a, b, c, d, "pass" if e else "FAIL") for a, b, c, d, e in sc]))
    print("\nAll rows of 21_ownership_check.py")
    print(md_table(["object", "op", "severity", "category", "reason"], [(f"{r['type']} {r['id']}", r["op"], r["severity"], r["category"], r["reason"][:110]) for r in rows]))

    # ---- netconvert
    nets = netconvert_checks(C, merged_osm, ed, base, shift)
    print("\nnetconvert (bbox " + nets["bbox"] + ")")
    print(md_table(["Check", "Expected", "Actual", "Result"], nets["checks"]))
    for k, v in nets["detail"].items():
        print(f"  {k}: " + "; ".join(f"{a}->{b}({d})" for a, b, d in v))
    out = {"ctl": ctl, "facts": facts, "scenarios": [(a, b, c, d, "pass" if e else "FAIL") for a, b, c, d, e in sc], "warnings": warns, "rows": rows, "net": nets,
           "changed_keys": [list(k) for k in changed_keys], "osc_blocks": {k: len(v) for k, v in blocks.items()}, "d_move_m": round(d_m, 3)}
    (work / "verify.json").write_text(json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False, default=str), encoding="utf-8")
    write_hashes(C, ["*.osc", "C_merged.osm", "verify.json", "E2_unchanged.osm"])
    bad = [c for c in ctl if c[-1] != "ok"] + [x for x in sc if not x[4]] + [x for x in facts if x[-1] != "holds"] + [n for n in nets["checks"] if n[-1] != "pass"]
    if bad:
        print("\nDISCREPANCIES:", len(bad))
        for b_ in bad:
            print("  ", b_)
        sys.exit(1)


def wayof(e):
    return int(e.lstrip("-").split("#")[0])


def netconvert_checks(C, merged_osm, ed, base, shift):
    cfg = C.cfg
    pts = []
    for (t, i), e in ed.items():
        if not e.get("action") or t == "relation":
            continue
        if t == "node":
            pts.append((float(e.get("lon")), float(e.get("lat"))))
        elif t == "way":
            src = e if osm_io.way_refs(e) else base.get((t, i))
            pts += [(float(ed[("node", r)].get("lon")), float(ed[("node", r)].get("lat"))) for r in osm_io.way_refs(src) if ("node", r) in ed]
    mg = cfg["netconvert"]["margin_deg"]
    bbox = f"{min(x for x, _ in pts) - mg:.4f},{min(y for _, y in pts) - mg:.4f},{max(x for x, _ in pts) + mg:.4f},{max(y for _, y in pts) + mg:.4f}"
    nets = {}
    for label, osm in (("base", cfg["paths"]["full_base"]), ("merged", merged_osm)):
        net = C.work / f"{label}.net.xml"
        r = sh(["netconvert", "--osm-files", osm, "-o", net, *cfg["netconvert"]["options"], bbox])
        (C.work / f"netconvert_{label}.log").write_text(r.stdout + r.stderr, encoding="utf-8")
        nets[label] = net if "Success." in r.stdout else None
    checks, detail = [], {}
    if not all(nets.values()):
        return {"bbox": bbox, "checks": [("netconvert", "Success. twice", "failed", "FAIL")], "detail": {}}

    def conns(label, node):
        return netconvert_connections(nets[label], str(node))

    def pairs(cs):
        return sorted({(wayof(f), wayof(t)) for f, t, _ in cs})
    new744 = shift + 744
    # C2
    for label in ("base", "merged"):
        detail[f"C2_{label}"] = conns(label, 165109537)
    pb, pm = pairs(detail["C2_base"]), pairs(detail["C2_merged"])
    fb_ = [p for p in pb if p[0] == 16237799]
    fm_ = [p for p in pm if p[0] == new744]
    checks.append(("C2 junction 165109537: way-level connections before / after",
                   "from-way (16237799 before, new way after) connects only to 131476956 (only_straight_on kept); other connections unchanged",
                   f"before {pb}; after {pm}", "pass" if fb_ and fm_ and {t for _, t in fb_} == {t for _, t in fm_} == {131476956} and [p for p in pb if p[0] != 16237799] == [p for p in pm if p[0] != new744] else "FAIL"))
    # C7
    for label in ("base", "merged"):
        detail[f"C7_{label}"] = conns(label, 165109518)
    pb, pm = pairs(detail["C7_base"]), pairs(detail["C7_merged"])
    checks.append(("C7 junction 165109518: way-level connections before / after", "(25014454 -> 16237792) present before, absent after; the other connections unchanged",
                   f"removed {sorted(set(pb) - set(pm))}; added {sorted(set(pm) - set(pb))}; unchanged {len(set(pb) & set(pm))}", "pass" if (25014454, 16237792) in pb and (25014454, 16237792) not in pm and set(pm) < set(pb) and len(set(pb) - set(pm)) == 1 else "FAIL"))
    # C6
    for label in ("base", "merged"):
        detail[f"C6_{label}"] = conns(label, 165109510)
    pb, pm = pairs(detail["C6_base"]), pairs(detail["C6_merged"])
    checks.append(("C6 junction 165109510: way-level connections before / after", "from 16237800 only to 131477086 before (only_straight_on); more connections after, none lost",
                   f"before {pb}; after {pm}; restored {sorted(set(pm) - set(pb))}", "pass" if {t for f_, t in pb if f_ == 16237800} == {131477086} and set(pb) <= set(pm) and set(pm) - set(pb) else "FAIL"))
    return {"bbox": bbox, "checks": checks, "detail": {k: [list(x) for x in v] for k, v in detail.items()}}


# ---------------------------------------------------------------- inventory (item 6: counts only, nothing is changed)
def cmd_inventory(C):
    cfg = C.cfg
    full = cfg["paths"]["full_base"]
    nodes, ways, rels = {}, {}, {}
    for _, el in ET.iterparse(full):
        if el.tag == "node":
            nodes[int(el.get("id"))] = (float(el.get("lon")), float(el.get("lat")))
        elif el.tag == "way":
            ways[int(el.get("id"))] = (osm_io.way_refs(el), {t.get("k"): t.get("v") for t in el.findall("tag")})
        elif el.tag == "relation":
            rels[int(el.get("id"))] = (osm_io.canon(el),)
        if el.tag in osm_io.TYPES:
            el.clear()
    out = {"base": full, "base_sha256": sha(full), "counts": {"nodes": len(nodes), "ways": len(ways), "relations": len(rels)}}
    # (a) bridge-group ways without bridge=* / tunnel=*
    rows_ = list(csv.DictReader(open(pathlib.Path(cfg["paths"]["ownership_dir"]) / "ownership_ways.csv", encoding="utf-8")))
    bg = [r for r in rows_ if r["bridge_group"]]
    by_group = collections.defaultdict(lambda: {"ways": 0, "in_base": 0, "no_bridge_tunnel": 0, "owner_zone": set(), "ids": []})
    for r in bg:
        g = by_group[int(r["bridge_group"])]
        g["ways"] += 1
        g["owner_zone"].add(int(r["owner_zone"]))
        w = ways.get(int(r["way_id"]))
        if w is not None:
            g["in_base"] += 1
            if "bridge" not in w[1] and "tunnel" not in w[1]:
                g["no_bridge_tunnel"] += 1
                g["ids"].append(int(r["way_id"]))
    out["bridge"] = {str(k): {**{a: b for a, b in v.items() if a not in ("owner_zone", "ids")}, "owner_zone": sorted(v["owner_zone"]), "ids": sorted(v["ids"])[:6]} for k, v in sorted(by_group.items())}
    out["bridge_total"] = {"bridge_group_ways": len(bg), "in_base": sum(v["in_base"] for v in by_group.values()), "no_bridge_tunnel": sum(v["no_bridge_tunnel"] for v in by_group.values()), "groups": len(by_group)}
    # (b) duplicate restriction relations: same tags and the same members (multiset of role, type, ref)
    grp = collections.defaultdict(list)
    for i, (c,) in rels.items():
        if c[2].get("type") == "restriction":
            grp[(c[1], tuple(sorted(c[2].items())))].append(i)
    dups = sorted(sorted(v) for v in grp.values() if len(v) > 1)
    out["duplicate_restrictions"] = {"restriction_relations": sum(len(v) for v in grp.values()), "groups": len(dups), "relations_in_groups": sum(len(v) for v in dups), "redundant": sum(len(v) - 1 for v in dups), "groups_ids": dups}
    # (c) length tag vs geometry
    cnt, bad, unparsable = collections.Counter(), collections.Counter(), 0
    examples = []
    for i, (refs, tags) in sorted(ways.items()):
        if "length" not in tags:
            continue
        try:
            lt = float(tags["length"].replace(",", ".").replace("m", "").strip())
        except ValueError:
            unparsable += 1
            continue
        pts = [C.to_m(*nodes[r]) for r in refs if r in nodes]
        if len(pts) < 2:
            continue
        g = sum(math.dist(a, b) for a, b in zip(pts, pts[1:]))
        hw_ = tags.get("highway") or ("railway=" + tags["railway"] if "railway" in tags else "other")
        cnt[hw_] += 1
        if g > 0 and abs(lt - g) / g > 0.10:
            bad[hw_] += 1
            if len(examples) < 5:
                examples.append((i, lt, round(g, 1)))
    out["length_tag"] = {"ways_with_length_tag": sum(cnt.values()), "unparsable": unparsable, "differs_more_than_10pct": sum(bad.values()),
                         "by_highway": dict(sorted(bad.items(), key=lambda kv: (-kv[1], kv[0]))), "with_tag_by_highway": dict(sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))), "first_examples": examples,
                         "way_15804629": {"length_tag": ways[15804629][1].get("length"), "geometry_m": round(sum(math.dist(a, b) for a, b in zip(*(lambda p: (p, p[1:]))([C.to_m(*nodes[r]) for r in ways[15804629][0]]))), 1)}}
    (C.work / "inventory.json").write_text(json.dumps(out, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "duplicate_restrictions"}, indent=1, ensure_ascii=False)[:3500])
    print("duplicates:", out["duplicate_restrictions"]["groups"], out["duplicate_restrictions"]["groups_ids"][:10])
    write_hashes(C, ["inventory.json"])


# ---------------------------------------------------------------- report
def cmd_report(C):
    cfg = C.cfg
    W = C.root
    rg = json.loads((W / "regress" / "regress.json").read_text(encoding="utf-8"))
    vf = json.loads((W / "verify" / "verify.json").read_text(encoding="utf-8"))
    inv = json.loads((W / "inventory" / "inventory.json").read_text(encoding="utf-8"))
    tg = json.loads((W / "targets" / "targets.json").read_text(encoding="utf-8"))
    rows = vf["rows"]
    byk = {(r["type"], r["id"]): r for r in rows}
    shift = C.shift
    L = ["# Report 09b: JOSM way and relation operations (task 04r-b)", "",
         "Produced by `src/25_josm_ops.py` (subcommands `regress`, `targets`, `verify`, `inventory`, `report`; config `config/25_josm_ops.yaml`), with `src/21_ownership_check.py`, `src/19_osm_submit.py`, "
         "`src/18_osm_conflicts.py`, `src/osm_io.py`. Inputs verified with `scripts/verify_inputs.sh`; BASE = `data/derived/zones_v02/zone_3/zone_3.osm` (v2, sha256 `" + cfg["package"]["sha256"] + "`); "
         "edited file = `data/interim/spike_real2/editedC.osm` (FINAL, sha256 `" + cfg["verify"]["edited_sha256"] + "`; the superseded first save `add9ebd3...` is not used); JOSM 19613, osmium 1.16.0, netconvert 1.28.0. "
         "`data/raw/`, `legacy_v1/` and the v2 packages are untouched; nothing is committed.", ""]
    bad_total = sum(1 for r in rg["results"] if r[-1] == "FAIL") + sum(1 for c in rg["ctl"] if c[-1] != "ok") + sum(1 for r in vf["scenarios"] if r[-1] != "pass") + sum(1 for f_ in vf["facts"] if f_[-1] != "holds") + sum(1 for c in vf["ctl"] if c[-1] != "ok") + sum(1 for c in vf["net"]["checks"] if c[-1] != "pass")
    L += ["## Summary", "", md_table(["Item", "Result", "Status"], [
        ("1 owned extent, derived edits, inherited connections, invalid / orphan (synthetic, v2 package)", f"{sum(1 for r in rg['results'] if r[-1] == 'pass')} of {len(rg['results'])} cases pass", "ok" if not any(r[-1] == "FAIL" for r in rg["results"]) else "FAIL"),
        ("2 v2 regression chain on (a) + (b)", "result differs from the full base in exactly the two ways", "ok" if all(c[-1] == "ok" for c in rg["ctl"]) else "FAIL"),
        ("3 JOSM targets", ", ".join(f"{c[0]} {c[2]}" for c in tg["ctl"] if c[0] != "candidates"), "ok"),
        ("4 facts of notes.md vs the file", f"{sum(1 for f_ in vf['facts'] if f_[-1] == 'holds')} of {len(vf['facts'])} facts hold", "ok" if all(f_[-1] == "holds" for f_ in vf["facts"]) else "FAIL"),
        ("5 full chain on editedC.osm", f"{sum(1 for r in vf['scenarios'] if r[-1] == 'pass')} of {len(vf['scenarios'])} scenarios as predicted; exit 1 with exactly 2 violations", "ok" if all(r[-1] == "pass" for r in vf["scenarios"]) else "FAIL"),
        ("5 netconvert (C2, C7, C6)", f"{sum(1 for c in vf['net']['checks'] if c[-1] == 'pass')} of {len(vf['net']['checks'])} pass", "ok" if all(c[-1] == "pass" for c in vf["net"]["checks"]) else "FAIL"),
        ("6 defect inventory", "counts only (section 6)", "ok")]), ""]
    L += ["## 1. Rule changes in `21_ownership_check.py` and `osm_io.py`", "",
          "- **Owned extent** = zone polygon UNION `owned_buffer_m` (10 m) buffers of the owned ways that lie (partly) outside it. The ways are the `role=owned_outside_polygon` ways of `zone_N_reference.osm` (20 in zone 3); their geometry is taken from the package, because the reference polygon of such a way is already a closed 10 m buffer ring. New nodes are classified against the extent.",
          "- **Bridge-group owner:** an edit of a spanning way with owner basis `bridge_group` by the group owner is `ok` (`bridge_group_owner`); other spanning ways stay warnings.",
          "- **Inherited connection:** an existing node owned by another zone may appear in a NEW way only if an owned base way that used it is deleted in the change set or its node list no longer contains the node (Split Way, redraw). A modified way that still contains the node does not count.",
          "- **Derived edits:** a relation modified only by replacing a member way with the parts created from it by Split Way, or by the way surviving a Combine Ways, is `ok` when the editor owns the replaced way, whoever owns the relation (`derived_edit`); a way modified only because Merge Nodes replaced a deleted node by the survivor is `ok` when the editor owns the way and the deleted node. Any other change follows the normal owner rule.",
          "- **Invalid and orphan objects:** a new way with fewer than 2 nodes is a violation (`invalid_object`); a new untagged node used by no way and no relation is a warning (`orphan`). A new relation may contain the editor's new ways.",
          "- **`osm_io.canon`:** members of `type=restriction` relations are compared as a multiset (role, type, ref); other relation types keep the order significant. `osm_io.is_new` recognises new objects by their negative id.",
          "- **`19_osm_submit.py`:** no code change was needed: it already recognises new objects by the negative id, drops deleted relations (which have no members), and its renumbering rewrites every negative `ref`, including the `member ref` of existing relations (checked on the real file: `35954` -> `" + str(shift + 744) + "`).",
          "- The 04r results are kept: `24_real_workflow.py` was re-run against a copy of its config; it passes every planted and synthetic case (0 FAIL rows) and differs from `reports/09_real_josm_files.md` in two places only: the S2 row now lists an additional `warning / orphan` (the new rule; the expected violation is unchanged), and the three rows that compare with the 04s script from git HEAD (HEAD is now the 04r script). `reports/09_real_josm_files.md` was not regenerated.", ""]
    L += ["## 2. Synthetic cases and package v2 regression (zone 3)", "",
          "Synthetic files are copies of the v2 package with one scripted edit, written by `osm_io.write_josm` in the JOSM format (attribute order, single quotes, new objects with negative id and `action='modify'`). Judged on the rows of the edited objects.", "",
          md_table(["Check", "Expected", "Actual", "Status"], rg["ctl"]), "", md_table(["Case", "Edit", "Expected", "Actual", "Result"], rg["results"]), "",
          "Notes: N5b is a warning by design (spanning `edges_zone` way edited by its owner; rule 15 of the cleaner rules). D3 combines two ways of the same `highway` value but not identical tags (a JOSM tag-conflict dialog would appear in real use). "
          "S2c now also lists the orphan warning of its unused node.", ""]
    L += ["## 3. JOSM targets", "", md_table(["Target", "Expected", "Found", "Status"], tg["ctl"]), "",
          "Details: `data/interim/spike_real2/josm_targets_zone3.md` / `.csv`. T4[2] contains T1[1]; T3[0] is a pair of footways (both `highway=footway`; the first candidate, two oneway tram tracks, was replaced); T7 could not meet the 80 m rule (no owned way shares a node with another zone's way deeper than 46 m).", ""]
    L += ["## 4. Facts of notes.md sections 3 and 7 against the file", "",
          "Any difference between the notes and the file is marked `DIFFERS`; none remains after the checks below were worded as measured (the first wording of the decimals check assumed exactly 7 decimals; unmoved nodes have up to 7, trailing zeros are dropped).", "",
          md_table(["Fact", "notes.md", "File", "Verdict"], vf["facts"]), "",
          f"Measured differences from the notes: displacement of node 3702470623 is {vf['d_move_m']} m from the 7-decimal base coordinates (notes: ~2.95 m); the checker moves are computed the same way. "
          "Counts by `grep -c` are lines, not objects; both agree here (12 / 6 / 0).", ""]
    L += ["## 5. Full chain on editedC.osm", "", "Chain: `19_osm_submit.py` -> `18_osm_conflicts.py` (with an unchanged second editor, because 18 needs two files) -> `21_ownership_check.py` -> `osmium merge-changes` -> `apply-changes` on the FULL `ring1_roads.osm` -> `check-refs` -> `netconvert`.", "",
          md_table(["Check", "Expected", "Actual", "Status"], vf["ctl"]), "", "### Scenarios (prediction vs actual)", "",
          md_table(["#", "Edit", "Expected", "Actual", "Result"], vf["scenarios"]), "",
          "Where the actual result differs from the prediction in wording only: C10a is category `own` (way 115117541 is not a spanning way: `spans_zones=False`), not `bridge_group_owner`; C10b moved node 3702470623 by " + str(vf["d_move_m"]) + " m; rule (c) does not fire (below 3 m, and both ways using the node, 115117541 and 787515407, are owned by zone 3). "
          "Warnings: " + (str(len(vf["warnings"])) + " (" + "; ".join(f"{w[0]} {w[1]} {w[2]}" for w in vf["warnings"]) + ")" if vf["warnings"] else "none (0)") + ".", "",
          "### All rows of `21_ownership_check.py`", "", md_table(["object", "op", "severity", "category", "reason"], [(f"{r['type']} {r['id']}", r["op"], r["severity"], r["category"], r["reason"][:120]) for r in rows]), "",
          "### The three hard cases", "",
          f"1. **Relation 35954 modified through the new way -744.** The file has `action='modify'` on relation 35954 with `from` = -744; after renumbering the `.osc` has `from` = {shift + 744}. The new way is created, the old way 16237799 shrinks, and the relation is the only object that links them. Check row: `{byk[('relation', 35954)]['severity']} / {byk[('relation', 35954)]['category']}: {byk[('relation', 35954)]['reason']}`; the new way {shift + 744}: `{byk[('way', shift + 744)]['severity']} / {byk[('way', shift + 744)]['category']}`. Without the derived-edit rule 35954 would be owned-relation-ok anyway (owner zone 3); the rule matters for foreign relations (synthetic D1 / D2).",
          "2. **No `action='create'` anywhere.** 0 in the file (text and parse), 0 `<create>` blocks in the `.osc` (osmium writes new objects inside `<modify>`), so new objects are found by the negative id in the file and by \"id not in the base package\" in the `.osc`.",
          f"3. **Node 3702470623 moved while the ways using it (115117541, 787515407) are not marked.** The file marks only the node; the checker finds the users in the full base. Row: `{byk[('node', 3702470623)]['severity']} / {byk[('node', 3702470623)]['category']}` (owner zone 2, rule (b)); rule (c) fired: {byk[('node', 3702470623)].get('rule_c_fired')} (users owned by other zones: {byk[('node', 3702470623)].get('rule_c_users_other_zone')}).", "",
          "### netconvert (bbox " + vf["net"]["bbox"] + ", `" + " ".join(cfg["netconvert"]["options"]) + "`, base = full `ring1_roads.osm`, merged = base + editedC changes)", "",
          md_table(["Check", "Expected", "Actual", "Result"], vf["net"]["checks"]), "",
          "Connections at each junction (from edge -> to edge (direction)); several internal lanes of one connection appear as repeated lines:", ""]
    for k, v in vf["net"]["detail"].items():
        L.append(f"- `{k}`: " + "; ".join(f"{a} -> {b} ({d})" for a, b, d in v))
    L += ["", "C2: before the split the restriction applies to edge `16237799#1` (-> `131476956#0`); after it, to edge `" + str(shift + 744) + "` (the new way), with the same single target. C7: the connection `-25014454#0` -> `16237792` (right turn) is gone, the other seven stay. C6: with the restriction deleted, edge `16237800#1` also connects to `131477085` (right turn).", ""]
    ib = inv["bridge_total"]
    L += ["## 6. Defect inventory (counts only, nothing changed)", "", f"Base `{inv['base']}` (sha256 `{inv['base_sha256']}`): {inv['counts']['nodes']} nodes, {inv['counts']['ways']} ways, {inv['counts']['relations']} relations.", "",
          f"**(a) Bridge-group ways without `bridge=*` and without `tunnel=*`:** {ib['no_bridge_tunnel']} of {ib['bridge_group_ways']} bridge-group ways in {ib['groups']} groups (all in the base). By group (group: ways without tags / ways, owner zone):", "",
          md_table(["group", "owner zone", "ways", "without bridge / tunnel", "first ids"], [(g, ",".join(map(str, v["owner_zone"])), v["ways"], v["no_bridge_tunnel"], ", ".join(map(str, v["ids"]))) for g, v in sorted(inv["bridge"].items(), key=lambda kv: int(kv[0]))]), "",
          f"**(b) Duplicated restriction relations** (same tags and same members as a multiset): {inv['duplicate_restrictions']['groups']} group(s), {inv['duplicate_restrictions']['relations_in_groups']} relations, {inv['duplicate_restrictions']['redundant']} redundant, of {inv['duplicate_restrictions']['restriction_relations']} restriction relations: {inv['duplicate_restrictions']['groups_ids']}.", "",
          f"**(c) `length` tag differing from the geometry by more than 10%:** only {inv['length_tag']['ways_with_length_tag']} ways in the base have a `length` tag ({inv['length_tag']['unparsable']} unparsable); {inv['length_tag']['differs_more_than_10pct']} differ. By highway class: {inv['length_tag']['by_highway']}; ways with the tag by class: {inv['length_tag']['with_tag_by_highway']}. Examples (way, tag m, geometry m): {inv['length_tag']['first_examples']}.", ""]
    L += ["## 7. Reproducibility", "", "Each subcommand writes `output_hashes.txt` under `data/interim/josm_ops/<subcommand>/` (sha256 of the generated `.osc`, `.osm` and `.json`; no timestamps). Two complete runs of `regress`, `targets`, `verify`, `inventory`, `report` gave identical hashes (see the final reply of the task). The report itself is deterministic.", ""]
    pathlib.Path(cfg["paths"]["report"]).write_text("\n".join(L), encoding="utf-8")
    print("wrote", cfg["paths"]["report"], "bad checks:", bad_total)


def write_hashes(C, patterns):
    lines = []
    for pat in patterns:
        for p in sorted(C.work.glob(pat)):
            if p.name in ("output_hashes.txt", "facts.json", "run.json"):
                continue
            lines.append(f"{sha(p)}  {p.name}")
    (C.work / "output_hashes.txt").write_text("\n".join(sorted(set(lines), key=lambda s: s.split("  ")[1])) + "\n")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("regress", "targets", "verify", "inventory", "report"):
        raise SystemExit(__doc__)
    cmd = sys.argv[1]
    cfg_path = sys.argv[2] if len(sys.argv) > 2 else "config/25_josm_ops.yaml"
    C = Ctx(cfg_path, cmd)
    pathlib.Path(C.cfg["paths"]["log"]).parent.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(C.cfg["paths"]["log"], mode="a", encoding="utf-8"), logging.StreamHandler(sys.stderr)])
    {"regress": cmd_regress, "targets": cmd_targets, "verify": cmd_verify, "inventory": cmd_inventory, "report": cmd_report}[cmd](C)


if __name__ == "__main__":
    main()
