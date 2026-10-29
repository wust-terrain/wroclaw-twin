"""Task 02c': pilot sample inside the two frozen zones (work areas, sample, warm-up, overlap, assignments, kits, report).

Units owned by the zone only; the zone packages, ownership tables and unit tables are read, never changed.
Usage: uv run python src/26_pilot_zones.py [config/26_pilot_zones.yaml]
"""
import hashlib
import json
import logging
import pathlib
import re
import sys
import xml.sax.saxutils as xs

import geopandas as gpd
import numpy as np
import openpyxl
import osmium
import pandas as pd
import shapely
import yaml
from openpyxl.styles import Font
from openpyxl.worksheet.datavalidation import DataValidation
from shapely.geometry import Point

log = logging.getLogger("pilot_zones")


# ---------------------------------------------------------------- helpers
def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_logging(path):
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(path, mode="a"), logging.StreamHandler()])


def site_id_gaps(P, nodes_tbl, sites_gpkg):
    """Sites whose member nodes (nodes of their junction clusters and tram crossings) lack the site's id in ownership_nodes.csv.

    Signal clusters cannot be mapped to nodes (their ids are not node or cluster ids), so they are not checked.
    Returns (rows of the sites with a gap, number of sites, number of sites with at least one checkable node).
    """
    wu = pd.read_csv(P["work_units"])
    wu = wu[wu["site_id"].notna()].assign(site_id=lambda d: d["site_id"].astype(int))
    nt = nodes_tbl.set_index("node_id")
    by_cluster = nodes_tbl[nodes_tbl["cluster_id"].notna()].assign(cluster_id=lambda d: d["cluster_id"].astype(int)).groupby("cluster_id")["node_id"].apply(list)
    rows, checkable = [], 0
    for sid in sorted(sites_gpkg["site_id"].astype(int)):
        g = wu[wu["site_id"] == sid]
        exp = {n for c in g.loc[g["unit_type"] == "junction_cluster_complex", "id"] for n in by_cluster.get(int(c), [])}
        exp |= {int(n) for n in g.loc[g["unit_type"] == "tram_crossing", "id"] if int(n) in nt.index}
        if not exp:
            continue
        checkable += 1
        sub = nt.loc[sorted(exp)]
        lack = sub[sub["site_id"].fillna(-1).astype(int) != sid]
        if len(lack):
            rows.append({"site_id": sid, "zone": int(sub["owner_zone"].mode().min()), "member_nodes": len(exp), "nodes_lacking_site_id": len(lack),
                         "owner_basis_of_lacking_nodes": ";".join(f"{k}:{v}" for k, v in lack["owner_basis"].value_counts().sort_index().items()),
                         "site_id_found_on_lacking_nodes": ";".join(sorted({str(int(x)) for x in lack["site_id"].dropna()})) or "none",
                         "owner_zone_of_lacking_nodes": ";".join(str(int(x)) for x in sorted(lack["owner_zone"].unique())),
                         "site_zone_conflict_flag": ";".join(sorted({str(int(x)) for x in lack["site_zone_conflict"].dropna()})) or "none",
                         "units": ";".join(f"{t}:{i}" for t, i in zip(g["unit_type"], g["id"]))})
    return rows, len(sites_gpkg), checkable


def cut_position(cfg, seq, by_id):
    """Planning cut: number of leading units of the measured list whose cumulative assumed minutes fit the budget."""
    T = cfg["time"]
    budget = (T["hours_per_rater"] - T["warmup_hours"]) * 60
    cum = np.cumsum([T["assumed_minutes"][by_id[p]["stratum"]] for p in seq])
    return int((cum <= budget).sum())


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def sha256_of(path):
    p = pathlib.Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def xlsx_content_sha(path):
    """Hash of the cell values, hyperlink targets and validations (independent of zip timestamps)."""
    p = pathlib.Path(path)
    if not p.exists():
        return None
    wb = openpyxl.load_workbook(p)
    parts = []
    for ws in wb.worksheets:
        parts.append(ws.title)
        for row in ws.iter_rows():
            for c in row:
                parts.append([c.coordinate, c.value, c.hyperlink.target if c.hyperlink else None])
        parts.append([[dv.type, dv.formula1, str(dv.sqref)] for dv in ws.data_validations.dataValidation])
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, default=str).encode()).hexdigest()


def to_wgs(cfg, x, y):
    g = gpd.GeoSeries(gpd.points_from_xy(np.atleast_1d(x), np.atleast_1d(y)), crs=cfg["crs_metric"]).to_crs(cfg["crs_exchange"])
    return g.x.to_numpy(), g.y.to_numpy()


def zoom_url(cfg, xmin, ymin, xmax, ymax):
    xs_, ys_ = to_wgs(cfg, [xmin, xmax, xmin, xmax], [ymin, ymin, ymax, ymax])
    return f"{cfg['kit']['josm_base']}?left={xs_.min():.6f}&right={xs_.max():.6f}&bottom={ys_.min():.6f}&top={ys_.max():.6f}"


# ---------------------------------------------------------------- work areas
def edge_area(line, A):
    body = line.buffer(A["edge_buffer_m"], quad_segs=A["quad_segs"], cap_style="flat")
    ends = [Point(line.coords[0]).buffer(A["edge_buffer_m"], quad_segs=A["quad_segs"]),
            Point(line.coords[-1]).buffer(A["edge_buffer_m"], quad_segs=A["quad_segs"])]
    return shapely.union_all([body, *ends])


def site_area(coords, A):
    hull = shapely.MultiPoint(coords).convex_hull          # a point or a line when the nodes are collinear
    return hull.buffer(A["site_buffer_m"], quad_segs=A["quad_segs"])


def read_node_coords(path, need):
    out = {}
    for n in osmium.FileProcessor(path, osmium.osm.NODE):
        if n.id in need:
            out[n.id] = (n.lon, n.lat)
    return out


# ---------------------------------------------------------------- zone model
def size_class(cfg, n):
    for name, (lo, hi) in cfg["site_size_classes"].items():
        if n >= lo and (hi is None or n <= hi):
            return name
    raise ValueError(n)


def load_zone(cfg, z, geoms, nodes_tbl, owner_ways, sites_gpkg, coords_ll, checks):
    """All candidate units of zone z with their work areas: sites, edge units, bridge groups."""
    P, A = cfg["paths"], cfg["areas"]
    zd = pathlib.Path(P["zones_dir"]) / f"zone_{z}"
    u = pd.read_csv(zd / f"zone_{z}_units.csv")
    checks.append((f"zone {z}: rows of zone_{z}_units.csv", cfg["expected_units"][z], len(u), cfg["expected_units"][z] == len(u)))
    checks.append((f"zone {z}: all units have zone = {z}", 0, int((u["zone"] != z).sum()), bool((u["zone"] == z).all())))

    # ---- sites
    rows = []
    su = u[u["site_id"].notna()].copy()
    su["site_id"] = su["site_id"].astype(int)
    nodes_of = nodes_tbl[nodes_tbl["site_id"].notna()].assign(site_id=lambda d: d["site_id"].astype(int)).groupby("site_id")["node_id"].apply(list)
    cl_nodes = nodes_tbl[nodes_tbl["cluster_id"].notna()].assign(cluster_id=lambda d: d["cluster_id"].astype(int)).groupby("cluster_id")["node_id"].apply(list)
    ref = sites_gpkg.set_index("site_id")
    problems, gaps = [], []
    for sid, g in su.groupby("site_id", sort=True):
        types = set(g["unit_type"])
        n = len(g)
        mem_site = nodes_of.get(sid, [])
        # the junction-cluster nodes of the site are members too; ownership_nodes.csv carries site_id only for most of them
        mem_cl = [m for c in g.loc[g["unit_type"] == "junction_cluster_complex", "unit_id"] for m in cl_nodes.get(int(c), [])]
        mem = sorted(set(mem_site) | set(mem_cl))
        if set(mem) - set(mem_site):
            odd = nodes_tbl[nodes_tbl["node_id"].isin(set(mem) - set(mem_site))]
            found = ",".join(sorted({str(int(x)) for x in odd["site_id"].dropna()})) or "none"
            gaps.append(f"site {sid}: {len(odd)} of {len(mem)} member nodes ({', '.join(map(str, odd['node_id']))}) do not carry site_id {sid} in "
                        f"ownership_nodes.csv (site_id found: {found})")
        if not mem:
            problems.append(f"site {sid}: no member nodes in ownership_nodes.csv")
            continue
        lost = [m for m in mem if m not in coords_ll]
        if lost:
            problems.append(f"site {sid}: nodes without coordinates {lost[:5]}")
            continue
        tc = [int(i) for i in g.loc[g["unit_type"] == "tram_crossing", "unit_id"]]
        if any(t not in mem for t in tc):
            problems.append(f"site {sid}: tram crossing node not among the member nodes")
        if int(ref.loc[sid, "n_units"]) != n or int(g["site_n_units"].iloc[0]) != n:
            problems.append(f"site {sid}: n_units {n} differs from ring1_sites.gpkg / site_n_units")
        xy = geoms["to_m"](np.array([coords_ll[m][0] for m in mem]), np.array([coords_ll[m][1] for m in mem]))
        pts = np.column_stack(xy)
        area = site_area(pts, A)
        has_sig, has_tram = "signal_cluster" in types, "tram_crossing" in types
        comp = "+".join(l for t, l in (("signal_cluster", "signal"), ("junction_cluster_complex", "complex"), ("tram_crossing", "tram")) if t in types)
        cx, cy = pts.mean(axis=0)
        rows.append({"kind": "site", "ref": sid, "n_units": n, "size_class": size_class(cfg, n), "has_signal": has_sig, "has_tram": has_tram,
                     "composition": comp, "length_m": np.nan, "highway": None, "n_edges": 0, "area": area, "x": cx, "y": cy,
                     "n_nodes": len(mem), "members": ";".join(f"{t}:{i}" for t, i in zip(g["unit_type"], g["unit_id"]))})
    checks.append((f"zone {z}: sites with member nodes and coordinates, consistent with ring1_sites.gpkg", 0, len(problems), not problems))
    checks.append((f"zone {z}: sites whose member nodes do not carry the site's site_id in ownership_nodes.csv (nodes taken from cluster_id)", 0, len(gaps), "NOTE" if gaps else True))
    for p in problems + gaps:
        log.warning(p)
    sites = pd.DataFrame(rows)

    # ---- edge units
    es = u[u["unit_type"] == "segment"].copy()
    es["edge_id"] = es["edge_id"].astype(int)
    missing = [e for e in es["edge_id"] if e not in geoms["edge"]]
    checks.append((f"zone {z}: edge units with a geometry", len(es), len(es) - len(missing), not missing))
    erows = []
    for r in es.itertuples():
        line = geoms["edge"].get(r.edge_id)
        if line is None:
            continue
        area = edge_area(line, A)
        mid = line.interpolate(0.5, normalized=True)
        erows.append({"kind": "edge", "ref": r.edge_id, "n_units": 1, "size_class": None, "has_signal": False, "has_tram": False,
                      "composition": "", "length_m": r.length_m, "highway": r.highway, "service_tag": geoms["service"].get(r.edge_id), "unit_stratum": r.stratum, "unit_kind": r.kind,
                      "n_edges": 1, "area": area, "x": mid.x, "y": mid.y, "n_nodes": 0, "members": str(r.edge_id)})
    edges = pd.DataFrame(erows)

    # ---- bridge groups owned by the zone
    bf = pd.read_csv(zd / f"zone_{z}_bridges.csv")
    bf = bf[bf["kind"] == "bridge_group"]
    brows = []
    unit_edges = set(es["edge_id"])
    for r in bf.itertuples():
        ids = [int(x) for x in str(r.edge_ids).split(";")]
        own = owner_ways[owner_ways["bridge_group"] == r.id]["owner_zone"].unique().tolist()
        bad = [i for i in ids if i not in unit_edges or i not in geoms["edge"]]
        if own != [z] or bad:
            problems.append(f"bridge group {r.id}: owners {own}, edges not in the zone units {bad}")
        lines = [geoms["edge"][i] for i in ids if i in geoms["edge"]]
        area = shapely.union_all([edge_area(l, A) for l in lines])
        merged = shapely.union_all(lines)
        c = merged.interpolate(merged.project(merged.centroid))
        brows.append({"kind": "bridge", "ref": int(r.id), "n_units": 1, "size_class": None, "has_signal": False, "has_tram": False,
                      "composition": "", "length_m": float(r.length_m), "highway": None, "n_edges": len(ids), "area": area,
                      "x": c.x, "y": c.y, "n_nodes": 0, "members": ";".join(map(str, ids)), "name": r.name if isinstance(r.name, str) else "",
                      "polys": area.geom_type})
    bad_b = [p for p in problems if p.startswith("bridge")]
    checks.append((f"zone {z}: bridge groups owned by the zone, all edges are units of the zone", 0, len(bad_b), not bad_b))
    bridges = pd.DataFrame(brows)
    return {"units": u, "sites": sites, "edges": edges, "bridges": bridges, "gaps": gaps}


def candidates(spec, Z):
    """Candidate table of a stratum (index = row index of the kind's table)."""
    k = spec["kind"]
    if k == "site":
        s = Z["sites"]
        return s[s["size_class"] == spec["size_class"]]
    if k == "bridge":
        b = Z["bridges"]
        return b[b["n_edges"] <= spec["max_edges"]] if len(b) else b
    e = Z["edges"]
    e = e[e["unit_stratum"] == spec["unit_stratum"]]
    if "kinds" in spec:
        e = e[e["unit_kind"].isin(spec["kinds"])]
    if "min_length_m" in spec:
        e = e[e["length_m"] >= spec["min_length_m"]]
    return e


class Taken:
    """Accepted work areas of one zone; a candidate is accepted when it keeps `gap` metres from all of them."""

    def __init__(self, gap):
        self.gap, self.items = gap, []        # items: (label, area)

    def blockers(self, area):
        return [lab for lab, a in self.items if shapely.distance(area, a) < self.gap]

    def add(self, label, area):
        self.items.append((label, area))


def draw(rng, cand, n, taken, label_of):
    """Random order over the candidates; accept the disjoint ones until n are chosen (n None = take all).

    Returns (chosen index list, redraws, rejected {index: blockers}).
    """
    chosen, redraws, rej = [], 0, {}
    order = list(cand.index) if n is None else [cand.index[i] for i in rng.permutation(len(cand))]
    for i in order:
        if n is not None and len(chosen) == n:
            break
        area = cand.loc[i, "area"]
        b = taken.blockers(area)
        if b:
            redraws += 1
            rej[i] = b
            continue
        chosen.append(i)
        taken.add(label_of(cand.loc[i]), area)
    return chosen, redraws, rej


def label(row):
    return f"{row['kind']} {row['ref']}"


def n_requested(spec, z):
    if "zones" in spec and z not in spec["zones"]:
        return 0
    return spec["n"]


def draw_zone(cfg, z, Z, checks, forbid):
    """Draw sample and warm-up of zone z. Each stratum is followed at once by its warm-up unit (if any), so the scarce
    strata (medium sites, tram segments) are not exhausted by the abundant edge strata before the warm-up is drawn.

    Returns (chosen sample [(stratum index, table, index)], warm [same], summary, site redraws, blocked, warm info).
    """
    A, SC, W = cfg["areas"], cfg["site_constraints"], cfg["warmup"]
    seed, strata = cfg["seed"], cfg["strata"]
    tname = {"site": "sites", "edge": "edges", "bridge": "bridges"}
    wk = {name: k for k, name in enumerate(W["units"])}

    def stratum(i, taken, attempt, chosen, warm, summary, blocked, winfo):
        spec = strata[i]
        n = n_requested(spec, z)
        cand = candidates(spec, Z)
        rng = np.random.default_rng([seed, z, i + 1, attempt])
        ch, rd, rej = draw(rng, cand, n, taken, label) if (n is None or n) else ([], 0, {})
        req = len(cand) if n is None else n
        summary[i] = {"requested": req, "eligible": len(cand), "drawn": len(ch), "redraws": rd}
        if len(ch) < req:
            blocked[i] = {c: rej.get(c) for c in cand.index if c not in ch}
        chosen += [(i, tname[spec["kind"]], c) for c in ch]
        if spec["name"] in wk:
            wc = cand[[c not in ch for c in cand.index]]
            wrng = np.random.default_rng([seed, z, W["stream_base"] + wk[spec["name"]], attempt])
            wch, wrd, wrej = draw(wrng, wc, 1, taken, label)
            winfo[spec["name"]] = (len(wc), len(wch), wrd, {} if wch else wrej)
            warm += [(i, tname[spec["kind"]], c) for c in wch]

    def one_pass(idx_list, taken, attempt, state):
        for i in idx_list:
            stratum(i, taken, attempt, *state)

    site_idx = [i for i, s in enumerate(strata) if s["kind"] == "site"]
    other_idx = [i for i, s in enumerate(strata) if s["kind"] != "site"]
    attempts, ok = 0, False
    for attempt in range(SC["max_redraws"] + 1):
        taken = Taken(A["gap_m"])
        state = ([], [], {}, {}, {})          # chosen, warm, summary, blocked, winfo
        one_pass(site_idx, taken, attempt, state)
        sites = Z["sites"].loc[[c for _, _, c in state[0]]]
        small = Z["sites"].loc[[c for si, _, c in state[0] if strata[si]["name"] == "site: small"]]
        warm_sites = sum(1 for n in state[4] if n.startswith("site") and state[4][n][1])
        ok = (int(sites["has_signal"].sum()) >= SC["min_signal_sites"] and int(sites["has_tram"].sum()) >= SC["min_tram_sites"][z]
              and int(small["has_signal"].sum()) >= SC["min_small_signal_sites"]
              and all(state[2][i]["drawn"] == state[2][i]["requested"] for i in site_idx)
              and warm_sites == sum(1 for n in W["units"] if n.startswith("site")))
        attempts = attempt
        if ok:
            break
    checks.append((f"zone {z}: site constraints (>= {SC['min_signal_sites']} signal, >= {SC['min_tram_sites'][z]} tram crossing, "
                   f">= {SC['min_small_signal_sites']} small signal site; warm-up sites fillable); redraws used", f"<= {SC['max_redraws']}", attempts, ok))
    one_pass(other_idx, taken, 0, state)
    chosen, warm, summary, blocked, winfo = state
    info = refine(cfg, z, Z, state, checks, forbid)
    return chosen, warm, summary, attempts, blocked, winfo, info


def service_type(row):
    return row["highway"] if row["highway"] in ("service", "path") else "other"


def refine(cfg, z, Z, state, checks, forbid):
    """Post-processing of the first draw; sample and overlap units are never redrawn, only warm-up units and, if needed, the
    B-service stratum.

    1. B-service composition: each zone gets >= min_each unit of every type in `types` when each type has >= min_eligible eligible
       units. If the first draw fails, B-service is redrawn (attempt 1, 2, ...) against the final areas of all other units; when that
       is impossible, warm-up units are released step by step (levels: none, forced, forced + each group of
       warmup_redraw.composition_release in turn; the first level that works is taken).
    2. Forbidden nodes (whitelisted conflict node): warm-up units whose work area contains one are redrawn from their stratum (same rules).
    Released warm-ups are redrawn after B-service (stream attempt 1000 + level), from their own stratum, excluding the sample units and the old unit.
    Returns an info dict for the report.
    """
    strata, A, W, WR = cfg["strata"], cfg["areas"], cfg["warmup"], cfg["warmup_redraw"]
    chosen, warm, summary = state[0], state[1], state[2]
    name = lambda si: strata[si]["name"]  # noqa: E731
    wk = {n: k for k, n in enumerate(W["units"])}
    i = next(k for k, sp in enumerate(strata) if "composition" in sp)
    spec = strata[i]
    comp = spec["composition"]
    cand = candidates(spec, Z)
    types = cand.apply(service_type, axis=1)
    applies = all(int((types == t).sum()) >= comp["min_eligible"] for t in comp["types"])

    def good(idx):
        got = types.reindex(idx) if len(idx) else types.iloc[:0]
        return (not applies) or all(int((got == t).sum()) >= comp["min_each"] for t in comp["types"])

    contains = lambda tb, c: any(Z[tb].loc[c, "area"].contains(pt) for pt in forbid)  # noqa: E731
    forced_all = sorted((name(si) for si, tb, c in warm if contains(tb, c)), key=wk.get)
    # a forced warm-up is redrawable only if its stratum has a candidate clear of every sample / overlap unit (those are never redrawn)
    fixed_areas = [Z[tb].loc[c, "area"] for si, tb, c in chosen if si != i]
    forced, stuck = [], []
    for n in forced_all:
        old = next(x for x in warm if name(x[0]) == n)
        cc = candidates(strata[old[0]], Z)
        sample_idx = {c for si, _, c in chosen if si == old[0]}
        free = [c for c in cc.index if c not in sample_idx and c != old[2] and not contains(old[1], c)
                and all(shapely.distance(cc.loc[c, "area"], a) >= A["gap_m"] for a in fixed_areas)]
        (forced if free else stuck).append(n)
    levels, rel = [("none", set())], set(forced)
    levels.append(("forced", set(rel)))
    for grp in WR["composition_release"]:
        rel = rel | set(grp)
        levels.append((" + ".join(grp), set(rel)))
    info = {"forced": forced, "stuck": stuck, "level": None, "released": [], "bs_attempt": 0, "replaced": {}, "trace": []}
    cur = [c for si, _, c in chosen if si == i]
    done = False
    tried = set()
    for lv, (lname, L) in enumerate(levels):
        if frozenset(L) in tried:
            continue
        tried.add(frozenset(L))
        keep_s = [x for x in chosen if x[0] != i]
        keep_w = [x for x in warm if name(x[0]) not in L]
        R = sorted(set(L) | set(forced), key=wk.get)

        def redraw_warm(new_bs):
            taken = Taken(A["gap_m"])
            for si, tb, c in keep_s + [x for x in warm if name(x[0]) not in R]:
                taken.add(f"{tb} {c}", Z[tb].loc[c, "area"])
            for c in new_bs:
                taken.add(f"edges {c}", Z["edges"].loc[c, "area"])
            repl = {}
            for n in R:
                old = next(x for x in warm if name(x[0]) == n)
                cc = candidates(strata[old[0]], Z)
                sample_idx = {c for si, _, c in chosen if si == old[0]}
                cc = cc[[(c not in sample_idx) and c != old[2] and not contains(old[1], c) for c in cc.index]]
                rng = np.random.default_rng([cfg["seed"], z, W["stream_base"] + wk[n], 1000 + lv])
                ch, _, _ = draw(rng, cc, 1, taken, label)
                if not ch:
                    return None, n
                repl[n] = (old[0], old[1], ch[0])
            return repl, None

        attempts_bs = [(0, cur, summary[i]["redraws"])] if good(cur) else []
        if not attempts_bs:
            for att_bs in range(1, comp["max_redraws"] + 1):
                taken = Taken(A["gap_m"])
                for si, tb, c in keep_s + keep_w:
                    taken.add(f"{tb} {c}", Z[tb].loc[c, "area"])
                rng = np.random.default_rng([cfg["seed"], z, i + 1, att_bs])
                ch, rd_bs, _ = draw(rng, cand, spec["n"], taken, label)
                if len(ch) == spec["n"] and good(ch):
                    attempts_bs.append((att_bs, ch, rd_bs))
        if not attempts_bs:
            info["trace"].append((lname, "B-service: no draw with the composition in 200 attempts"))
            continue
        why, tried_bs = None, 0
        for att_bs, new_bs, rd_bs in attempts_bs:
            repl, why = redraw_warm(new_bs)
            tried_bs += 1
            if repl is not None:
                break
        if repl is None:
            info["trace"].append((lname, f"{len(attempts_bs)} B-service draw(s) with the composition, but warm-up '{why}' cannot be redrawn after any of them"))
            continue
        chosen[:] = [x for x in chosen if x[0] != i] + [(i, "edges", c) for c in new_bs]
        warm[:] = [repl.get(name(x[0]), x) for x in warm]
        summary[i]["redraws"] = rd_bs
        info.update({"level": lname, "released": R, "bs_attempt": att_bs, "replaced": {n: int(Z[v[1]].loc[v[2], "ref"]) for n, v in repl.items()}})
        done = True
        break
    final = [c for si, _, c in chosen if si == i]
    ok = done and good(final)
    if not done:
        keep = [(si, tb, c) for si, tb, c in chosen + warm if si != i]
        miss = [t for t in comp["types"] if int((types.reindex(final) == t).sum()) < comp["min_each"]]
        summary[i]["comp_blockers"] = {
            (types[c], int(cand.loc[c, "ref"])): [(strata[si]["name"], int(Z[tb].loc[cc, "ref"]), tb) for si, tb, cc in keep
                                                  if shapely.distance(cand.loc[c, "area"], Z[tb].loc[cc, "area"]) < A["gap_m"]]
            for c in cand.index if types[c] in miss}
    summary[i]["drawn"] = len(final)
    checks.append((f"zone {z}: B-service composition and warm-up units clear of the forbidden node(s) (release level: {info['level']}; "
                   f"B-service redraw attempt {info['bs_attempt']}; warm-ups redrawn {info['released']})", True, ok, ok))
    if stuck:
        checks.append((f"zone {z}: warm-up stratum {stuck} contains a forbidden node and cannot be redrawn without moving sample units", "redrawable", "no candidate (kept, accepted)", "INFO"))
    return info


# ---------------------------------------------------------------- unit table
def describe(row, spec_name):
    if row["kind"] == "site":
        return f"site {row['ref']}: {row['composition']}, {row['n_units']} unit(s), {row['n_nodes']} nodes"
    if row["kind"] == "bridge":
        nm = f" '{row['name']}'" if row.get("name") else ""
        return f"bridge group {row['ref']}{nm}: {row['n_edges']} edge(s), {row['length_m']:.0f} m"
    return f"edge {row['ref']}: {row['highway']}, {row['length_m']:.0f} m, kind {row['unit_kind']}"


def build_units(cfg, z, Z, chosen, warm, overlap_pick):
    """Rows (dicts with the area) for sample and warm-up units of zone z with pilot_ids."""
    A, kit = cfg["areas"], cfg["kit"]
    names = [s["name"] for s in cfg["strata"]]
    Pfx, Wfx = cfg["assignment"]["sample_id_prefix"], cfg["warmup"]["id_prefix"]
    rows = []

    def make(si, tb, idx, warmup):
        r = Z[tb].loc[idx]
        name = names[si]
        d = r.to_dict()
        d.update({"zone": z, "stratum": name, "warmup": warmup, "description": describe(r, name)})
        return d

    smp = sorted((make(si, tb, idx, False) for si, tb, idx in chosen), key=lambda d: (names.index(d["stratum"]), d["ref"]))
    for j, d in enumerate(smp, start=1):
        d["pilot_id"] = f"{Pfx}{z}{j:02d}"
    mins = cfg["time"]["assumed_minutes"]
    wl = [make(si, tb, idx, True) for si, tb, idx in warm]
    wl.sort(key=lambda d: (mins[d["stratum"]], names.index(d["stratum"])))   # easy to hard; ties by stratum order, so ids stay with strata
    for j, d in enumerate(wl, start=1):
        d["pilot_id"] = f"{Wfx}{z}{j}"
    rows = smp + wl
    for d in rows:
        d["overlap"] = False
    # overlap: stratum / requirement -> one unit, own stream
    rng = np.random.default_rng([cfg["seed"], z, cfg["overlap"]["stream_id"], 0])
    for spec in cfg["overlap"]["units"]:
        c = [d for d in smp if d["stratum"] == spec["stratum"] and (spec.get("require") != "signal" or d["has_signal"])
             and (d["kind"] == "site" or d["length_m"] >= spec.get("min_length_m", 0))]
        if not c:
            overlap_pick.append((z, spec["stratum"], 0))
            continue
        c[int(rng.integers(len(c)))]["overlap"] = True
    for d in rows:
        d["checklist"] = kit["checklist_names"]["site" if d["kind"] == "site" else d["stratum"]]
        if d["kind"] == "site":
            h = kit["point_box_m"] / 2
            d["josm_zoom"] = zoom_url(cfg, d["x"] - h, d["y"] - h, d["x"] + h, d["y"] + h)
        else:
            x0, y0, x1, y1 = d["area"].bounds
            # bounding box of the unit geometry + padding; the area itself is the geometry buffered by edge_buffer_m
            pad = kit["line_pad_m"] - A["edge_buffer_m"]
            d["josm_zoom"] = zoom_url(cfg, x0 - pad, y0 - pad, x1 + pad, y1 + pad)
        lon, lat = to_wgs(cfg, d["x"], d["y"])
        d["lon"], d["lat"] = round(float(lon[0]), 6), round(float(lat[0]), 6)
        d["streetview"] = f"{kit['streetview_base']}{d['lat']:.6f},{d['lon']:.6f}"
        d["area_m2"] = round(d["area"].area, 1)
    return rows


# ---------------------------------------------------------------- assignment
def assign(cfg, units):
    """Per rater: warm-up first, then own sample units (balanced prefix) and the other zone's overlap units as visitor."""
    AS = cfg["assignment"]
    lo, hi = AS["overlap_key_range"]
    by_id = {u["pilot_id"]: u for u in units}
    strata = [s["name"] for s in cfg["strata"]]
    rows, lists, key_attempts = [], {}, {}
    for j, (r, z) in enumerate(cfg["raters"].items()):
        rng = np.random.default_rng([cfg["seed"], z, AS["stream_base"] + j, 0])
        own = [u for u in units if u["zone"] == z and not u["warmup"]]
        warm = sorted((u for u in units if u["zone"] == z and u["warmup"]), key=lambda u: u["pilot_id"])
        keys = {}
        for s in strata:
            ids = sorted(u["pilot_id"] for u in own if u["stratum"] == s and not u["overlap"])
            n_h = len(ids)
            for k, pid in enumerate([ids[i] for i in rng.permutation(n_h)], start=1):
                keys[pid] = (k - rng.uniform()) / n_h
        lrng = np.random.default_rng([cfg["seed"], z, AS["stream_base"] + j, 10_000])
        for pid in sorted(u["pilot_id"] for u in own if u["stratum"] == "site: large" and not u["overlap"]):
            keys[pid] = lrng.uniform(*AS["large_key_range"])      # replaces the balanced-prefix key
        ov_ids = sorted(u["pilot_id"] for u in own if u["overlap"])
        visitors = sorted(u["pilot_id"] for u in units if u["zone"] != z and u["overlap"])
        # overlap and visitor keys come from U(lo, hi); their own stream is redrawn until every one of them also
        # sits within the first `hi` of the measured list (the balanced keys of the other units are not uniform)
        for attempt in range(AS["max_key_redraws"] + 1):
            orng = np.random.default_rng([cfg["seed"], z, AS["stream_base"] + j, 1 + attempt])
            k2 = dict(keys) | {pid: orng.uniform(lo, hi) for pid in ov_ids + visitors}
            order = sorted(k2, key=lambda p: (k2[p], p))
            if all((order.index(p) + 1) / len(order) <= hi for p in ov_ids + visitors):
                break
        key_attempts[r] = attempt
        seq = [w["pilot_id"] for w in warm] + order
        lists[r] = seq
        for i, pid in enumerate(seq, start=1):
            u = by_id[pid]
            rows.append({"rater": r, "zone": u["zone"], "order_index": i, "pilot_id": pid, "mode": "visitor" if pid in visitors else "own",
                         "overlap": bool(u["overlap"]), "warmup": bool(u["warmup"])})
    return pd.DataFrame(rows), lists, key_attempts


# ---------------------------------------------------------------- outputs
def write_osm(path, rows, crs_m):
    """JOSM reference layer: closed ways (negative ids) of the work areas in WGS84; exterior rings only."""
    tr = gpd.GeoSeries([r["area"] for r in rows], crs=crs_m).to_crs(4326)
    nid, wid = 0, 0
    nodes, ways = [], []
    for r, geom in zip(rows, tr):
        parts = list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]
        for p in parts:
            refs = []
            for lon, lat in list(p.exterior.coords)[:-1]:
                nid -= 1
                nodes.append((nid, lat, lon))
                refs.append(nid)
            wid -= 1
            tags = {"name": r["pilot_id"], "pilot_id": r["pilot_id"], "stratum": r["stratum"],
                    "overlap": "yes" if r["overlap"] else "no", "warmup": "yes" if r["warmup"] else "no"}
            ways.append((wid, refs + [refs[0]], tags))
    out = ["<?xml version='1.0' encoding='UTF-8'?>", "<osm version='0.6' generator='wroclaw-twin 26_pilot_zones'>"]
    for i, lat, lon in nodes:
        out.append(f"  <node id='{i}' action='modify' visible='true' lat='{lat:.7f}' lon='{lon:.7f}' />")
    for i, refs, tags in ways:
        out.append(f"  <way id='{i}' action='modify' visible='true'>")
        out += [f"    <nd ref='{n}' />" for n in refs]
        out += [f"    <tag k={xs.quoteattr(k)} v={xs.quoteattr(v)} />" for k, v in tags.items()]
        out.append("  </way>")
    out.append("</osm>")
    pathlib.Path(path).write_text("\n".join(out) + "\n", encoding="utf-8")
    return len(ways)


def read_back_osm(path):
    ways = []
    for w in osmium.FileProcessor(path, osmium.osm.WAY):
        ways.append((w.id, {t.k: t.v for t in w.tags}, w.is_closed(), len(w.nodes)))
    return ways


def write_kit(cfg, rater, zone, asg, units, path):
    kit = cfg["kit"]
    by_id = {u["pilot_id"]: u for u in units}
    wb = openpyxl.Workbook()
    wb.properties.creator = "26_pilot_zones.py"
    wb.properties.created = wb.properties.modified = pd.Timestamp("2000-01-01").to_pydatetime()
    ws = wb.active
    ws.title = "Units"
    head = ["order_index", "pilot_id", "mode", "flags", "unit type", "stratum", "short description", "checklist", "JOSM zoom", "Street View", "note"]
    ws.append(head)
    mine = asg[asg["rater"] == rater]
    for r in mine.itertuples():
        u = by_id[r.pilot_id]
        flags = ";".join(f for f, on in (("warmup", r.warmup), ("overlap", r.overlap), ("visitor", r.mode == "visitor")) if on)
        ws.append([r.order_index, r.pilot_id, r.mode, flags, {"site": "site", "edge": "edge", "bridge": "bridge group"}[u["kind"]],
                   u["stratum"], u["description"], u["checklist"], "JOSM", "Street View", u["wl_note"] or None])
        row = ws.max_row
        for col, key in ((9, "josm_zoom"), (10, "streetview")):
            c = ws.cell(row=row, column=col)
            c.hyperlink = u[key]
            c.style = "Hyperlink"
    for c in ws[1]:
        c.font = Font(bold=True)
    ws.freeze_panes = "A2"
    for col, w in zip("ABCDEFGHIJK", (11, 10, 9, 18, 13, 18, 60, 22, 10, 12, 90)):
        ws.column_dimensions[col].width = w
    rs = wb.create_sheet("Record")
    cols = kit["record_columns"]
    rs.append(cols)
    for r in mine.itertuples():
        row = {"pilot_id": r.pilot_id, "rater": rater, "order_index": r.order_index}
        rs.append([row.get(c) for c in cols])
    for c in rs[1]:
        c.font = Font(bold=True)
    rs.freeze_panes = "A2"
    last = max(rs.max_row, 2)
    for name, formula in (("checklist_complete", '"y,n"'), ("difficulty", '"1,2,3"')):
        dv = DataValidation(type="list", formula1=formula, allow_blank=True, showErrorMessage=True)
        col = openpyxl.utils.get_column_letter(cols.index(name) + 1)
        dv.add(f"{col}2:{col}{last}")
        rs.add_data_validation(dv)
    for i, c in enumerate(cols, start=1):
        rs.column_dimensions[openpyxl.utils.get_column_letter(i)].width = max(12, len(c) + 2)
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return len(mine)


README = """# Pilot kit {rater} (zone {zone})

Rules, work areas, ownership, visitor mode and the record sheet: `docs/pilot/protocol.md` (checklists: section 8).

Files
- `units_{rater}.xlsx`: sheet `Units` = your list in working order (warm-up first, `mode` = own / visitor, `flags`,
  JOSM zoom link and Street View link); sheet `Record` = one pre-filled row per unit (fill in the rest).
- `pilot_areas_zone_{zone}.osm`, `pilot_areas_zone_{other}.osm`: reference layers with the work areas (open as a second JOSM layer;
  `name` = pilot_id, tags `stratum`, `overlap`, `warmup`). The JOSM zoom links need JOSM remote control (Change the viewport).

Whitelisted nodes (`shared_editable_nodes.csv`): a whitelisted node may be edited by the zone of its site, unless its owner zone is the other
pilot zone. The ownership check prints a warning for an edit of such a node; that is expected, mention it in `notes`.
{wl_notes}

Own units are edited in `zone_{zone}_edit.osm` (a copy of the package of zone {zone}); visitor units (zone {other}) are processed in a private
copy of the zone {other} package (`zone_{other}_visitor.osm`), which is discarded and never submitted. Submit your own edits with `scripts/submit_edits.sh {zone} zone_{zone}_edit.osm [--dry-run]`.
"""


def main():
    cfg = load_yaml(sys.argv[1] if len(sys.argv) > 1 else "config/26_pilot_zones.yaml")
    P = cfg["paths"]
    setup_logging(P["log"])
    crs = cfg["crs_metric"]
    checks = []
    zones = sorted(cfg["raters"].values())

    # ---------------- inputs
    prev = {k: sha256_of(P[k]) for k in ("units_csv", "assignments_csv", "record_sheet", "site_gaps_csv")}
    prev |= {str(f): sha256_of(f) for f in pathlib.Path(P["kit_dir"]).glob("R*/*.osm")}
    zd = pathlib.Path(P["zones_dir"])
    in_hash = {}
    for z in zones:
        side = json.loads((zd / f"zone_{z}" / f"zone_{z}.json").read_text(encoding="utf-8"))
        pk = sha256_of(zd / f"zone_{z}" / f"zone_{z}.osm")
        in_hash[f"zone_{z}.osm"] = pk
        checks.append((f"zone {z}: package v2 sha256 equals the sidecar", side["sha256_extract"], pk, side["sha256_extract"] == pk))
        checks.append((f"zone {z}: package_version", 2, side.get("package_version"), side.get("package_version") == 2))
    for f in ("ownership_nodes", "ownership_ways"):
        in_hash[f + ".csv"] = sha256_of(P[f])

    import pyproj
    t = pyproj.Transformer.from_crs(4326, crs, always_xy=True)
    to_m = lambda lon, lat: t.transform(lon, lat)  # noqa: E731

    og = gpd.read_file(P["ownership_gpkg"], layer="edges")
    tg = gpd.read_file(P["ownership_gpkg"], layer="tram_segments")
    edge_geom = {int(r.edge_id): r.geometry for r in og.itertuples() if r.edge_id >= 0}
    edge_geom |= {int(r.edge_id): r.geometry for r in tg.itertuples() if r.edge_id < 0}
    nodes_tbl = pd.read_csv(P["ownership_nodes"])
    owner_ways = pd.read_csv(P["ownership_ways"])
    sites_gpkg = gpd.read_file(P["sites_gpkg"], layer="sites")
    white = pd.read_csv(pathlib.Path(P["zones_dir"]) / "shared_editable_nodes.csv")
    need = set(nodes_tbl.loc[nodes_tbl["site_id"].notna(), "node_id"]) | set(white["node_id"]) | set(cfg["warmup_redraw"]["forbidden_nodes"])
    coords_ll = read_node_coords(P["base_osm"], need)
    edge_service = {int(r.edge_id): (r.service if isinstance(r.service, str) else None) for r in og.itertuples() if r.edge_id >= 0}
    geoms = {"edge": edge_geom, "to_m": to_m, "service": edge_service}

    forbid = [Point(*to_m(*coords_ll[n])) for n in cfg["warmup_redraw"]["forbidden_nodes"]]

    # ---------------- zones
    Zs, drawn, warmd, summ, att, blocked, warm_info, info_z = {}, {}, {}, {}, {}, {}, {}, {}
    for z in zones:
        Zs[z] = load_zone(cfg, z, geoms, nodes_tbl, owner_ways, sites_gpkg, coords_ll, checks)
        drawn[z], warmd[z], summ[z], att[z], blocked[z], warm_info[z], info_z[z] = draw_zone(cfg, z, Zs[z], checks, forbid)

    units, overlap_missing = [], []
    for z in zones:
        units += build_units(cfg, z, Zs[z], drawn[z], warmd[z], overlap_missing)
    for z, s, _ in overlap_missing:
        checks.append((f"zone {z}: overlap candidate for '{s}'", ">= 1", 0, False))

    # ---------------- checks on the sample
    names = [s["name"] for s in cfg["strata"]]
    for z in zones:
        for i, s in enumerate(cfg["strata"]):
            req = summ[z][i]["requested"]
            got = summ[z][i]["drawn"]
            checks.append((f"zone {z}: {s['name']} drawn", req, got, req == got))
        zu = [u for u in units if u["zone"] == z]
        mind = min(shapely.distance(a["area"], b["area"]) for ia, a in enumerate(zu) for b in zu[ia + 1:])
        checks.append((f"zone {z}: min distance between work areas of all {len(zu)} units (sample, warm-up, overlap) m", f">= {cfg['areas']['gap_m']}",
                       round(mind, 1), mind >= cfg["areas"]["gap_m"]))
        npw = sum(u["warmup"] for u in zu)
        checks.append((f"zone {z}: warm-up units", len(cfg["warmup"]["units"]), npw, npw == len(cfg["warmup"]["units"])))
        ovl = [u["length_m"] for u in zu if u["overlap"] and u["kind"] == "edge"]
        minl = [sp.get("min_length_m", 0) for sp in cfg["overlap"]["units"] if sp["stratum"].startswith("edge")][0]
        checks.append((f"zone {z}: overlap edge length m", f">= {minl}", [round(x, 1) for x in ovl], all(x >= minl for x in ovl)))
        nov = sum(u["overlap"] for u in zu)
        checks.append((f"zone {z}: overlap units", len(cfg["overlap"]["units"]), nov, nov == len(cfg["overlap"]["units"])))
        ids = [u["pilot_id"] for u in zu]
        checks.append((f"zone {z}: pilot_ids unique", len(ids), len(set(ids)), len(ids) == len(set(ids))))
        unit_rows = Zs[z]["units"]
        nonmember = [u["ref"] for u in zu if u["kind"] == "edge" and u["ref"] not in set(unit_rows["edge_id"].dropna().astype(int))]
        checks.append((f"zone {z}: edge units belong to zone_{z}_units.csv", 0, len(nonmember), not nonmember))

    asg, lists, key_att = assign(cfg, units)
    by_id = {u["pilot_id"]: u for u in units}
    for r, z in cfg["raters"].items():
        checks.append((f"{r}: redraws of the overlap / visitor keys", f"<= {cfg['assignment']['max_key_redraws']}", key_att[r],
                       key_att[r] <= cfg["assignment"]["max_key_redraws"]))
        n_own = sum(1 for u in units if u["zone"] == z and not u["warmup"])
        n_vis = int((asg[(asg["rater"] == r)]["mode"] == "visitor").sum())
        n_w = int(asg[(asg["rater"] == r)]["warmup"].sum())
        checks.append((f"{r}: list = warm-up + own sample + visitor units", len(cfg["warmup"]["units"]) + n_own + len(cfg["overlap"]["units"]),
                       len(lists[r]), len(lists[r]) == len(cfg["warmup"]["units"]) + n_own + len(cfg["overlap"]["units"])))
        checks.append((f"{r}: visitor units", len(cfg["overlap"]["units"]), n_vis, n_vis == len(cfg["overlap"]["units"])))
        first = asg[asg["rater"] == r].head(n_w)["warmup"].all()
        checks.append((f"{r}: warm-up units first", True, bool(first), bool(first)))
        mpos = [i for i, p in enumerate(lists[r][n_w:], start=1) if by_id[p]["overlap"]]
        worst = max(mpos) / (len(lists[r]) - n_w)
        hi = cfg["assignment"]["overlap_key_range"][1]
        meas = lists[r][n_w:]
        cut = cut_position(cfg, meas, by_id)
        lg = [meas.index(p) + 1 for p in meas if by_id[p]["stratum"] == "site: large"]
        checks.append((f"{r}: own `site: large` units before the projected cut (positions; cut {cut})", "all <= cut", lg, all(k <= cut for k in lg)))
        lo = cfg["assignment"]["overlap_key_range"][0]
        ovp = [meas.index(p) + 1 for p in meas if by_id[p]["overlap"]]
        checks.append((f"{r}: first position of an overlap / visitor unit (key range from {lo})", f">= {int(lo * len(meas))}", min(ovp), min(ovp) >= int(lo * len(meas))))
        checks.append((f"{r}: overlap + visitor units within the first {hi:.0%} of the measured list (max position fraction)", f"<= {hi}",
                       round(worst, 3), worst <= hi))

    gap_rows, n_sites, n_checkable = site_id_gaps(P, nodes_tbl, sites_gpkg)
    white_hits, notes = {}, {}
    for r in white.itertuples():
        pt = Point(*to_m(*coords_ll[r.node_id]))
        white_hits[int(r.node_id)] = (r.zones_allowed, r.reason, [(u["pilot_id"], u["warmup"]) for u in units if u["area"].contains(pt)])
    own_of = lambda reason: int(re.search(r"owner (\d+)", reason).group(1))  # noqa: E731
    for u in units:
        mine = [n for n, v in white_hits.items() if any(p == u["pilot_id"] for p, _ in v[2])]
        for owner in sorted({own_of(white_hits[n][1]) for n in mine}):
            ns = [n for n in mine if own_of(white_hits[n][1]) == owner]
            if owner == u["zone"]:
                continue
            word = "node" if len(ns) == 1 else "nodes"
            lst = " and ".join(map(str, ns))
            key = "note_foreign_owner" if owner in cfg["raters"].values() else "note_inactive_owner"
            u.setdefault("wl_note", []).append(cfg["kit"][key].format(word=word, nodes=lst, owner=owner, verb="lies" if len(ns) == 1 else "lie"))
    for u in units:
        u["wl_note"] = " ".join(u.get("wl_note", []))
    for n in cfg["warmup_redraw"]["forbidden_nodes"]:
        hit = [p for p, w in white_hits[n][2] if not w]
        checks.append((f"whitelisted node {n}: sample and overlap units whose work area contains it", 0, hit, not hit))
    for n, v in white_hits.items():
        wu = [p for p, w in v[2] if w]
        if wu:
            checks.append((f"INFO whitelisted node {n}: warm-up units whose work area contains it (accepted)", "-", wu, "INFO"))
    extra = {"info": info_z, "white_hits": white_hits, "gap_rows": gap_rows, "n_sites": n_sites, "n_checkable": n_checkable}
    pd.DataFrame(gap_rows).to_csv(P["site_gaps_csv"], index=False)

    # ---------------- write: units csv, assignments, gpkg
    for p in ("units_csv", "assignments_csv", "areas_gpkg", "report"):
        pathlib.Path(P[p]).parent.mkdir(parents=True, exist_ok=True)
    cols = ["pilot_id", "zone", "kind", "ref", "stratum", "warmup", "overlap", "description", "n_units", "n_edges", "length_m", "has_signal",
            "has_tram", "area_m2", "lon", "lat", "josm_zoom", "streetview", "checklist", "members"]
    ut = pd.DataFrame([{c: u[c] for c in cols} for u in units])
    ut["length_m"] = ut["length_m"].round(2)
    ut.to_csv(P["units_csv"], index=False)
    asg.to_csv(P["assignments_csv"], index=False)
    ga = gpd.GeoDataFrame(ut.drop(columns=["josm_zoom", "streetview"]), geometry=[u["area"] for u in units], crs=crs)
    ga = ga.rename(columns={"ref": "unit_ref"})
    pathlib.Path(P["areas_gpkg"]).unlink(missing_ok=True)
    ga.to_file(P["areas_gpkg"], layer="pilot_areas", driver="GPKG")
    rs_cols = cfg["kit"]["record_columns"]
    pathlib.Path(P["record_sheet"]).write_text(",".join(rs_cols) + "\n")

    # ---------------- kits
    kd = pathlib.Path(P["kit_dir"])
    osm_files, xlsx_files, osm_info = {}, {}, {}
    for r in cfg["raters"]:
        (kd / r).mkdir(parents=True, exist_ok=True)
        for z in zones:
            f = kd / r / f"pilot_areas_zone_{z}.osm"
            osm_files[(r, z)] = f
            zrows = [u for u in units if u["zone"] == z]
            nw = write_osm(f, zrows, crs)
            back = read_back_osm(f)
            tag_ok = all(w[2] and w[1].get("pilot_id") == w[1].get("name") and {"stratum", "overlap", "warmup"} <= set(w[1]) and w[0] < 0 for w in back)
            ids_back = {w[1]["pilot_id"] for w in back}
            osm_info[(r, z)] = (nw, len(back))
            checks.append((f"{r}/zone {z}: areas .osm read back with pyosmium (ways written = read; closed, negative ids, tags)", nw, len(back), nw == len(back) and tag_ok))
            checks.append((f"{r}/zone {z}: areas .osm contains every pilot_id", len(zrows), len(ids_back), ids_back == {u["pilot_id"] for u in zrows}))
    prev_x = {}
    wl_text = "Whitelisted nodes inside work areas of the kits:\n" + "\n".join(f"- {u['pilot_id']}: {u['wl_note']}" for u in units if u["wl_note"])
    for r, z in cfg["raters"].items():
        other = [x for x in zones if x != z][0]
        d = kd / r
        d.mkdir(parents=True, exist_ok=True)
        f = d / f"units_{r}.xlsx"
        prev_x[r] = (sha256_of(f), xlsx_content_sha(f))
        write_kit(cfg, r, z, asg, units, f)
        xlsx_files[r] = f
        (d / "README.md").write_text(README.format(rater=r, zone=z, other=other, wl_notes=wl_text), encoding="utf-8")

    # ---------------- report
    write_report(cfg, units, Zs, summ, att, blocked, warm_info, asg, lists, checks, osm_files, xlsx_files, prev, prev_x, in_hash, osm_info, extra)
    for a, b, c, d in checks:
        log.info("%s | expected %s | actual %s | %s", a, b, c, {True: "PASS", False: "FAIL"}.get(d, d))
    if any(c[3] is False for c in checks):
        log.error("CHECK FAILED")
        sys.exit(1)


def write_report(cfg, units, Zs, summ, att, blocked, warm_info, asg, lists, checks, osm_files, xlsx_files, prev, prev_x, in_hash, osm_info, extra):
    P, T = cfg["paths"], cfg["time"]
    names = [s["name"] for s in cfg["strata"]]
    by_id = {u["pilot_id"]: u for u in units}
    zones = sorted(cfg["raters"].values())
    mins = T["assumed_minutes"]
    L = ["# Task 02c': pilot sample inside the two frozen zones", "",
         "Config: `config/26_pilot_zones.yaml`; script `src/26_pilot_zones.py`. Every number is `[PROPOSED]`. "
         "Reads the v2 packages, ownership tables and unit tables; changes none of them. "
         "Work areas, record columns and checklist names follow `docs/pilot/protocol.md` (version 2); the sample design follows the task text.", "",
         "## Checks", "", md_table(["Check", "Expected", "Actual", "Result"], [(a, b, c, {True: "PASS", False: "FAIL"}.get(d, d)) for a, b, c, d in checks]), "",
         "`NOTE` = a finding, not a failure:", ""]
    for z in zones:
        L += [f"- zone {z}: {g}. Its member nodes are taken from `cluster_id`. `ownership_nodes.csv` is not changed; see section 9."
              for g in Zs[z]["gaps"]]
    L += ["", "## 1. Sample size by zone and stratum", ""]
    rows = []
    for z in zones:
        for i, n in enumerate(names):
            s = summ[z][i]
            rows.append((z, n, "all" if cfg["strata"][i]["n"] is None else s["requested"], s["eligible"], s["drawn"], s["redraws"],
                         "OK" if s["drawn"] == s["requested"] else "SHORT"))
    L += [md_table(["zone", "stratum", "requested", "eligible", "drawn", "redraws", "status"], rows), "",
          "Redraws = candidates rejected because their work area is closer than "
          f"{cfg['areas']['gap_m']} m to an already accepted one. Eligible = units of the zone in the stratum; edge strata reuse the 02a filters "
          "(A: inside_through, length >= 20 m; B-core, B-service: inside_through; C: dead_end_spur, inside_through, isolated; tram segment: length >= 30 m). "
          "Large sites: all of them. Bridge edges are also ordinary edge units and stay eligible in the edge strata; "
          "the disjointness rule keeps them apart from a drawn bridge group.", ""]
    for z in zones:
        L += [f"- Zone {z}: site redraws (whole site phase repeated until the constraints hold): {att[z]} (limit {cfg['site_constraints']['max_redraws']})."]
    L.append("")
    for z in zones:
        inf = extra["info"][z]
        L += [f"  - zone {z} level `{lv}`: {why}" for lv, why in inf["trace"]]
        L += [f"- Zone {z}: B-service redraw attempt {inf['bs_attempt']} (0 = first draw already satisfied the composition rule); release level `{inf['level']}`; "
              f"warm-up strata redrawn: {inf['released'] or 'none'} (forced by the forbidden node: {inf['forced'] or 'none'}; **cannot be redrawn, kept**: {inf['stuck'] or 'none'}); "
              f"new warm-up units (stratum: edge or site id): {inf['replaced'] or 'none'}."]
    L += ["", "### B-service composition", "",
          "Eligible = B-service edges of the zone after the 02a filter (`inside_through`); sample = the 3 drawn units. "
          "Rule: at least one `service` and one `path` unit per zone when both types have at least "
          f"{[s for s in cfg['strata'] if 'composition' in s][0]['composition']['min_eligible']} eligible units.", ""]
    rowsc = []
    for z in zones:
        E = Zs[z]["edges"]
        E = E[E["unit_stratum"] == "B_service"]
        E = E[E["unit_kind"].isin([s for s in cfg["strata"] if "composition" in s][0]["kinds"])]
        smp = [u for u in units if u["zone"] == z and u["stratum"] == "edge: B-service"]
        for lab, rows_, n_ in (("eligible", [service_type(r) for _, r in E.iterrows()], len(E)), ("sample", [service_type(u) for u in smp], len(smp))):
            c = pd.Series(rows_).value_counts()
            rowsc.append((z, lab, n_, c.get("service", 0), c.get("path", 0), c.get("other", 0)))
    L += [md_table(["zone", "set", "n", "highway=service", "highway=path", "other"], rowsc), "", ]
    rowst = []
    for z in zones:
        E = Zs[z]["edges"]
        E = E[(E["unit_stratum"] == "B_service") & (E["unit_kind"].isin(["inside_through"]))]
        smp = [u for u in units if u["zone"] == z and u["stratum"] == "edge: B-service"]
        for lab, vals in (("eligible", list(E["service_tag"])), ("sample", [u["service_tag"] for u in smp])):
            c = pd.Series([v if isinstance(v, str) else "(no service tag)" for v in vals]).value_counts()
            rowst.append((z, lab, ", ".join(f"{k} {v}" for k, v in c.items())))
    L += ["By the `service` tag:", "", md_table(["zone", "set", "service tag (count)"], rowst), ""]
    pid_of = {(u["stratum"], u["kind"], u["ref"]): u["pilot_id"] for u in units}
    for z in zones:
        for i, cb in [(i, summ[z][i].get("comp_blockers")) for i in summ[z] if summ[z][i].get("comp_blockers")]:
            free = [k for k, v in cb.items() if not v]
            cnt = {}
            for v in cb.values():
                for st, ref, tb in v:
                    cnt[(st, ref, tb)] = cnt.get((st, ref, tb), 0) + 1
            single = {}
            for k, v in cb.items():
                if len(v) == 1:
                    single.setdefault(v[0], []).append(k[1])
            L += [f"**Zone {z}: the B-service composition rule cannot be met without changing other units.** "
                  f"Missing type(s): {sorted({k[0] for k in cb})}; {len(cb)} eligible candidate(s) of that type, {len(free)} not blocked by the units already drawn "
                  f"(all other strata and the warm-up are kept as required, so nothing was replaced). Blocking units, by number of candidates blocked:", "",
                  md_table(["blocking unit", "stratum", "candidates blocked", "candidates blocked only by this unit"],
                           [(pid_of.get((st, {"edges": "edge", "sites": "site", "bridges": "bridge"}[tb], ref), f"{st} {ref}"), st, n, ", ".join(map(str, single.get((st, ref, tb), []))) or "-")
                            for (st, ref, tb), n in sorted(cnt.items(), key=lambda x: -x[1])]), ""]
    for z in zones:
        for i, b in blocked[z].items():
            L += [f"**Zone {z}, stratum {names[i]}: not filled.** Blocking units per rejected candidate:", ""]
            L += [f"- {Zs[z][ {'site': 'sites', 'edge': 'edges', 'bridge': 'bridges'}[cfg['strata'][i]['kind']] ].loc[c, 'ref']}: "
                  f"{', '.join(v) if v else 'not drawn (quota reached)'}" for c, v in b.items() if v]
            L.append("")
    # bridge groups
    L += ["## 2. Bridge groups owned by the zones", ""]
    for z in zones:
        b = Zs[z]["bridges"]
        if not len(b):
            L += [f"Zone {z}: no bridge groups.", ""]
            continue
        drawn_ids = {u["ref"] for u in units if u["zone"] == z and u["kind"] == "bridge"}
        L += [f"Zone {z}:", "", md_table(["group", "name", "edges", "length m", "eligible (<= %d edges)" % [s for s in cfg["strata"] if s["kind"] == "bridge"][0]["max_edges"], "drawn"],
                                         [(r.ref, r.name, r.n_edges, f"{r.length_m:.0f}", "yes" if r.n_edges <= [s for s in cfg["strata"] if s["kind"] == "bridge"][0]["max_edges"] else "no",
                                           "yes" if r.ref in drawn_ids else "") for r in b.itertuples()]), ""]
    # lists
    L += ["## 3. Units", ""]
    for z in zones:
        L += [f"### Zone {z}", "", md_table(["pilot_id", "stratum", "unit", "flags", "area m2"],
                                          [(u["pilot_id"], u["stratum"], u["description"], ";".join(f for f, on in (("warmup", u["warmup"]), ("overlap", u["overlap"])) if on), u["area_m2"])
                                           for u in units if u["zone"] == z]), ""]
    L += ["Warm-up draws (right after the sample draw of the same stratum): " + "; ".join(f"zone {z} {n}: eligible {e}, drawn {d}, redraws {rd}" for z in zones for n, (e, d, rd, _) in warm_info[z].items()) +
          ". Warm-up units are ordered by assumed minutes of the stratum, then size (easy to hard); they are real work but excluded from the analysis.", ""]
    L += ["## 4. Overlap and visitor units", "",
          md_table(["pilot_id", "zone (owner)", "stratum", "processed by (own)", "visitor"],
                   [(u["pilot_id"], u["zone"], u["stratum"], [r for r, z in cfg["raters"].items() if z == u["zone"]][0],
                     [r for r, z in cfg["raters"].items() if z != u["zone"]][0]) for u in units if u["overlap"]]), ""]
    # prefix balance and projection
    AS = cfg["assignment"]
    budget = (T["hours_per_rater"] - T["warmup_hours"]) * 60
    short = {n: n.replace("site: ", "s:").replace("edge: ", "e:").replace("tram segment", "tram").replace("bridge group", "bridge") for n in names}
    pref, proj, cum_rows, dev_max = [], [], [], 0.0
    for r in cfg["raters"]:
        seq = [p for p in lists[r] if not by_id[p]["warmup"]]
        n = len(seq)
        full = pd.Series([by_id[p]["stratum"] for p in seq]).value_counts().reindex(names, fill_value=0)
        for fr in AS["prefix_fractions"]:
            k = int(np.floor(fr * n + 0.5))
            c = pd.Series([by_id[p]["stratum"] for p in seq[:k]]).value_counts().reindex(names, fill_value=0)
            dev = float((c - full * k / n).abs().max())
            dev_max = max(dev_max, dev)
            pref.append((r, f"{int(fr * 100)}%", k, *c.tolist(), f"{dev:.2f}"))
        m = np.array([mins[by_id[p]["stratum"]] for p in seq])
        cum = np.cumsum(m)
        cut = int((cum <= budget).sum())
        c = pd.Series([by_id[p]["stratum"] for p in seq[:cut]]).value_counts().reindex(names, fill_value=0)
        nxt = f"{seq[cut]} ({by_id[seq[cut]]['stratum']})" if cut < n else "-"
        warm_min = sum(mins[by_id[p]["stratum"]] for p in lists[r] if by_id[p]["warmup"])
        ov = [(k, p) for k, p in enumerate(seq, start=1) if by_id[p]["overlap"]]
        proj.append((r, n, int(cum[-1]), cut, cut + len(lists[r]) - n, f"{100 * cut / n:.0f}%", warm_min, nxt,
                     ", ".join(f"{p}@{k}" for k, p in ov), sum(1 for k, _ in ov if k <= cut)))
        for k in sorted(set(list(range(5, n, 5)) + [cut, n])):
            if k:
                cum_rows.append((r, k, seq[k - 1], int(cum[k - 1]), "<- cut" if k == cut else ""))
    L += ["## 5. Prefix balance (count per stratum in the first 25/50/75% of the measured list)", "",
          "Warm-up excluded; own overlap and visitor units are counted in their own stratum. Last column: max over strata of |count - proportional share of the full list|. "
          "Prefix length = round(fraction x list length). Columns: `s:` site, `e:` edge.", "",
          md_table(["rater", "prefix", "n", *[short[n] for n in names], "max dev"], pref), "",
          f"Largest deviation: {dev_max:.2f} units.", "",
          "## 6. Planning projection (a GUESS)", "",
          "Assumed minutes per unit (**[PROPOSED] unmeasured planning guesses, to be replaced by the times measured in the pilot; nothing here is a result**): " +
          ", ".join(f"{k} {v}" for k, v in mins.items()) + f". Visitor units are assumed to cost the same as the owner's. Budget for measured units = "
          f"{T['hours_per_rater']} h - {T['warmup_hours']} h warm-up = {budget:g} min. Cut = number of measured units whose cumulative expected minutes fit the budget "
          "(`order_index` of the last one = cut + number of warm-up units).", "",
          md_table(["rater", "measured units", "total expected min", "cut (measured position)", "cut (order_index)", "share of list", "warm-up expected min",
                    "first unit past the budget", "overlap/visitor @ measured position", "of which before the cut"], proj), "",
          "Cumulative expected minutes (every 5th position, the cut and the end):", "",
          md_table(["rater", "position", "unit", "cum. min", ""], cum_rows), ""]
    # site_id gaps
    gr = extra["gap_rows"]
    L += ["## 9. Sites whose member nodes do not carry the site's `site_id`", "",
          f"All {extra['n_sites']} sites of `ring1_sites.gpkg`; {extra['n_checkable']} have member nodes that can be identified (nodes of their junction clusters via "
          "`cluster_id`, and their tram crossing nodes); the others consist of signal clusters only, whose ids are not node ids, and are not checkable. "
          f"A node counts when `site_id` in `ownership_nodes.csv` is empty or names another site. Found: {len(gr)}. No table is changed. "
          f"List: `{P['site_gaps_csv']}`.", ""]
    if gr:
        L += [md_table(["site_id", "zone", "member nodes", "nodes lacking", "owner_basis of those nodes", "site_id found on them", "owner_zone of them",
                        "site_zone_conflict flag", "units"],
                       [(r["site_id"], r["zone"], r["member_nodes"], r["nodes_lacking_site_id"], r["owner_basis_of_lacking_nodes"], r["site_id_found_on_lacking_nodes"],
                         r["owner_zone_of_lacking_nodes"], r["site_zone_conflict_flag"], r["units"]) for r in gr]), ""]
    L += ["## 10. Whitelisted nodes (`shared_editable_nodes.csv`) inside pilot work areas", "",
          f"Node(s) {cfg['warmup_redraw']['forbidden_nodes']} must not lie in any sample or overlap work area (checked). Warm-up units that contain a whitelisted node are reported only (W36 was accepted by decision); the pilot rule is the note below.", "",
          md_table(["node", "zones allowed", "reason", "pilot units whose work area contains it"],
                   [(n, v[0], v[1], ", ".join(p + (" (warm-up)" if w else " (sample)") for p, w in v[2]) or "none") for n, v in extra["white_hits"].items()]), "",
          "Notes written to the Units sheet (column `note`) and to the README of both kits:", "",
          md_table(["pilot_id", "note"], [(u["pilot_id"], u["wl_note"]) for u in units if u["wl_note"]]), ""]
    # hashes
    def same(prev_hash, new):
        return {None: "no previous file"}.get(prev_hash, "yes" if prev_hash == new else "no")
    out_rows = [(P["units_csv"], sha256_of(P["units_csv"]), same(prev["units_csv"], sha256_of(P["units_csv"]))),
                (P["assignments_csv"], sha256_of(P["assignments_csv"]), same(prev["assignments_csv"], sha256_of(P["assignments_csv"]))),
                (P["record_sheet"], sha256_of(P["record_sheet"]), same(prev["record_sheet"], sha256_of(P["record_sheet"]))),
                (P["site_gaps_csv"], sha256_of(P["site_gaps_csv"]), same(prev["site_gaps_csv"], sha256_of(P["site_gaps_csv"])))]
    for f in osm_files.values():
        out_rows.append((str(f), sha256_of(f), same(prev.get(str(f)), sha256_of(f))))
    xrows = []
    for r, f in xlsx_files.items():
        cs = xlsx_content_sha(f)
        xrows.append((str(f), sha256_of(f), same(prev_x[r][0], sha256_of(f)), cs, same(prev_x[r][1], cs)))
    L += ["## 7. Output hashes (sha256)", "", md_table(["file", "sha256", "same as previous run"], out_rows), "",
          md_table(["xlsx", "file sha256", "same", "cell-content sha256", "same"], xrows), "",
          "Inputs (unchanged): " + ", ".join(f"`{k}` `{v[:12]}`" for k, v in in_hash.items()) + ".", "",
          "## 8. Outputs", "", f"- `{P['units_csv']}`, `{P['assignments_csv']}`, `{P['areas_gpkg']}` (layer `pilot_areas`, EPSG:{cfg['crs_metric']})",
          f"- `{P['kit_dir']}/R1`, `{P['kit_dir']}/R2` (`units_<R>.xlsx`, `README.md`, `pilot_areas_zone_<N>.osm`), `{P['kit_dir']}/<R>/pilot_areas_zone_<N>.osm`",
          f"- `{P['record_sheet']}` (header only)", ""]
    pathlib.Path(P["report"]).write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
