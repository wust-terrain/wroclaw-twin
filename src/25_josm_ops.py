"""Task 04r-b: owned extent, package v2 regression, JOSM targets, way / relation operations.

Usage: uv run python src/25_josm_ops.py {regress|targets|verify|report} [config/25_josm_ops.yaml]
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

    syn = [
        ("S2", "new node far outside the polygon (>10 m from any owned way)", ("violation", "new_outside_polygon"), s2, 1),
        ("S2b", f"new node on owned way {ow} (outside the polygon, {dist_poly:.0f} m away), inserted into the way", ("ok", "new_in_polygon"), s2b, 0),
        ("S2c", f"new node {cfg['extent_cases']['near_way_m']:.0f} m beside owned way {ow} (within the buffer), not part of the way", ("ok", "new_in_polygon"), s2c, 0),
        ("S2d", f"new node {far_m:.0f} m beside owned way {ow} ({extent.distance(Point(*C.to_m(mid[1], far_lat))):.0f} m from the owned extent, outside the buffer)", ("violation", "new_outside_polygon"), s2d, 1),
        ("S2e", f"split owned way {ow} at node {split_at}: new way outside the polygon, all existing nodes owned by zone {C.zone}", ("ok", "new_way_own"), split, 0),
    ]
    for cid, desc, want, fn, ex in syn:
        path, focus = write_edit(C, cid, fn)
        r, osc = submit(C, cid, path)
        if r.returncode != 0:
            results.append((cid, desc, f"{want[0]} / {want[1]}", f"19 exit {r.returncode}", "FAIL"))
            continue
        r21, rows = ownership(C, [("A", C.zone, osc, C.pkg)], cid)
        fk = {(t, file_id(C, i)) for t, i in focus}
        rr = rows_of(rows, fk)
        okc = verdict(rr, want) and r21.returncode == ex and all(SEV[x["severity"]] <= SEV[want[0]] for x in rr)
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
            ("b", f"tag edit on way {br['tag_way_b']} (owner {own['way'][br['tag_way_b']]}, end nodes owned by zone 2, spanning)", tag_edit(br["tag_way_b"]), ("warning", "spanning_owner_edit"), 2),
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
    ctl.append(("chain 21 (E1, E2)", "exit 2 (one spanning warning), 0 violations", f"exit {r21.returncode}: {rows and collections.Counter(r['severity'] for r in rows)}", "ok" if r21.returncode == 2 and not any(r["severity"] == "violation" for r in rows) else "FAIL"))
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
    ctl.append(("(a)+(b) in one file: 19 / 21", "exit 0 / exit 2, rows ok + warning", f"exit {rab.returncode} / exit {r21ab.returncode}: {sev_ab}", "ok" if rab.returncode == 0 and r21ab.returncode == 2 and len(rowsab) == 2 else "FAIL"))

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
            if d < tc["t3"]["max_dist_m"] and not (node_ways[n] & node_ways[m]) and not (node_ways[n] & used_ways) and not (node_ways[m] & used_ways):
                t3.append((d, n, m))
                seen.add((n, m))
    t3.sort()
    t3_all = len(t3)
    for k, (d, n, m) in enumerate(t3[:tc["t3"]["n"]]):
        add("T3", k, "node_pair", [n, m], [n, m], distance_m=round(d, 2), ways=";".join(map(str, sorted(node_ways[n] | node_ways[m]))), note="Merge Nodes; "
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


def write_hashes(C, patterns):
    lines = []
    for pat in patterns:
        for p in sorted(C.work.glob(pat)):
            if p.name in ("output_hashes.txt", "facts.json", "run.json"):
                continue
            lines.append(f"{sha(p)}  {p.name}")
    (C.work / "output_hashes.txt").write_text("\n".join(sorted(set(lines), key=lambda s: s.split("  ")[1])) + "\n")


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("regress", "targets", "verify", "report"):
        raise SystemExit(__doc__)
    cmd = sys.argv[1]
    cfg_path = sys.argv[2] if len(sys.argv) > 2 else "config/25_josm_ops.yaml"
    C = Ctx(cfg_path, cmd)
    pathlib.Path(C.cfg["paths"]["log"]).parent.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(C.cfg["paths"]["log"], mode="a", encoding="utf-8"), logging.StreamHandler(sys.stderr)])
    {"regress": cmd_regress, "targets": cmd_targets}[cmd](C)


if __name__ == "__main__":
    main()
