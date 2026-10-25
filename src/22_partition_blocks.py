"""Task 03c: barrier-aware, block-based partition of RING 1 (v0.2). Analysis only.

Usage: uv run python src/22_partition_blocks.py [config/22_partition_blocks.yaml]
Reuses the loaders, weights and scenario definitions of src/16_partition_v0.py.
"""
import hashlib
import importlib.util
import json
import logging
import math
import pathlib
import subprocess
import sys
from collections import Counter, defaultdict

import geopandas as gpd
import numpy as np
import pandas as pd
import pymetis
import shapely
import yaml
from scipy.optimize import linear_sum_assignment
from shapely.geometry import shape
from shapely.ops import polygonize, unary_union

log = logging.getLogger("blocks")
CHECKS = []


def _load_v0():
    spec = importlib.util.spec_from_file_location("v0", pathlib.Path(__file__).with_name("16_partition_v0.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


v0 = _load_v0()
load_yaml, md_table, setup_logging = v0.load_yaml, v0.md_table, v0.setup_logging


def check(name, expected, actual, ok=None):
    ok = (expected == actual) if ok is None else ok
    CHECKS.append((name, expected, actual, "PASS" if ok else "FAIL"))
    if not ok:
        log.error("CHECK FAILED: %s expected=%s actual=%s", name, expected, actual)
    return ok


def read_override(path, cols):
    p = pathlib.Path(path)
    df = pd.read_csv(p) if p.exists() else pd.DataFrame(columns=cols)
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise SystemExit(f"override file {path} lacks columns {missing}")
    return df


# ------------------------------------------------------------------ 1. water and barriers

def extract_water(cfg, ring):
    """osmium tags-filter + extract (RING 1 bbox + buffer) + export to GeoJSON from the frozen snapshot."""
    from pyproj import Transformer
    wdir = pathlib.Path(cfg["paths"]["water_dir"])
    wdir.mkdir(parents=True, exist_ok=True)
    b = ring.buffer(cfg["water_bbox_buffer_m"]).bounds
    tr = Transformer.from_crs(cfg["crs_metric"], 4326, always_xy=True)
    (x0, y0), (x1, y1) = tr.transform(b[0], b[1]), tr.transform(b[2], b[3])
    bbox = f"{x0:.5f},{y0:.5f},{x1:.5f},{y1:.5f}"
    allw, box, gj = wdir / "water_all.osm.pbf", wdir / "water_box.osm.pbf", wdir / "water.geojson"
    run = lambda cmd: subprocess.run(cmd, check=True, capture_output=True)
    run(["osmium", "tags-filter", cfg["paths"]["snapshot"], "nwr/natural=water", "nwr/waterway=river,canal,riverbank",
         "nwr/water=river,canal", "-o", str(allw), "--overwrite"])
    run(["osmium", "extract", "-b", bbox, "--strategy", "smart", str(allw), "-o", str(box), "--overwrite"])
    run(["osmium", "export", str(box), "-o", str(gj), "--overwrite", "-f", "geojson", "--add-unique-id=type_id"])
    log.info("water extracted: bbox %s", bbox)
    return gj, bbox


def matches_water_filter(p):
    return (p.get("natural") == "water" or p.get("waterway") in ("river", "canal", "riverbank")
            or p.get("water") in ("river", "canal"))


def load_water(cfg, gj):
    keep = ("name", "waterway", "natural", "water", "tunnel", "layer", "width", "place", "bridge")
    rows = []
    for f in json.load(open(gj, encoding="utf-8"))["features"]:
        p = f["properties"]
        if f["geometry"]["type"] == "Point" or not matches_water_filter(p):
            continue   # points and the island/ring ways that osmium pulled in with multipolygon members
        rows.append(dict(id=f["id"], **{k: p.get(k) for k in keep}, geometry=shape(f["geometry"])))
    g = gpd.GeoDataFrame(rows, crs=4326).to_crs(cfg["crs_metric"])
    return g.sort_values("id").reset_index(drop=True)


def select_barriers(cfg, water, ring):
    bc = cfg["barriers"]
    names = list(bc["names"]) + (list(bc["moat_names"]) if bc["include_moat"] else [])
    g = water.copy()
    g["is_poly"] = g.geom_type.isin(["Polygon", "MultiPolygon"])
    g["inside"] = g.geometry.intersection(ring)
    g["measure"] = np.where(g["is_poly"], g["inside"].area, g["inside"].length)
    g["kind"] = np.where(g["is_poly"], "area", "line")
    line_sel = (~g["is_poly"]) & g["name"].isin(names) & (g["measure"] > 0)
    sel_lines = unary_union(g.loc[line_sel, "inside"].to_numpy()) if line_sel.any() else shapely.GeometryCollection()
    reason = pd.Series("", index=g.index)
    reason[line_sel] = "named line"
    sel = line_sel.copy()
    for i in g.index[g["is_poly"] & (g["measure"] > 0)]:
        row = g.loc[i]
        ln = row["inside"].intersection(sel_lines).length if not sel_lines.is_empty else 0.0
        by_name = row["name"] in names
        moat = bc["include_moat"] and row["water"] == "moat"
        if by_name or moat or ln >= bc["select_overlap_min_m"]:
            sel[i] = True
            reason[i] = "named polygon" if by_name else ("moat" if moat else f"contains {ln:.0f} m of a selected line")
    g["selected"] = sel
    g["reason"] = reason
    polys = g.loc[sel & g["is_poly"], "inside"]
    lines = g.loc[sel & ~g["is_poly"], "inside"]
    parts = list(polys) + [x.buffer(bc["line_buffer_m"]) for x in lines]
    area = unary_union(parts).intersection(ring)
    area = shapely.make_valid(area)
    area = unary_union([p for p in shapely.get_parts(area) if p.geom_type == "Polygon" and p.area > 0])
    return g, area, names


def water_table(cfg, g):
    t = g[g["measure"] > 0].copy()
    t["osm"] = t["id"]
    t["type"] = np.where(t["is_poly"], "area", "line")
    tags = []
    for r in t.itertuples():
        tags.append(";".join(f"{k}={getattr(r, k)}" for k in ("natural", "waterway", "water", "tunnel", "layer", "width") if pd.notna(getattr(r, k))))
    t["tags"] = tags
    out = pd.DataFrame({"id": t["id"], "type": t["type"], "name": t["name"], "tags": t["tags"],
                        "length_m_inside": np.where(t["is_poly"], np.nan, t["measure"].round(1)),
                        "area_m2_inside": np.where(t["is_poly"], t["measure"].round(1), np.nan),
                        "selected_as_barrier": t["selected"], "selection_reason": t["reason"]})
    out = out.sort_values(["selected_as_barrier", "type", "area_m2_inside", "length_m_inside", "id"],
                          ascending=[False, True, False, False, True], na_position="last")
    p = pathlib.Path(cfg["paths"]["water_table"])
    p.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(p, index=False)
    return out


# ------------------------------------------------------------------ 2. blocks

def merge_slivers(fg, nbr, sliver_m2, min_len):
    """Merge faces < sliver_m2 into the neighbour (same kind first) with the longest shared boundary."""
    geoms = list(fg.geometry)
    water = list(fg["water"])
    alive = set(range(len(geoms)))
    merged_into = {}
    log_rows = []
    while True:
        small = sorted((geoms[i].area, i) for i in alive if geoms[i].area < sliver_m2)
        moved = False
        for _, i in small:
            cand = {j: L for j, L in nbr[i].items() if j in alive}
            if not cand:
                continue
            same = {j: L for j, L in cand.items() if water[j] == water[i]}
            pool = same or cand
            j = sorted(pool.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            log_rows.append((i, j, geoms[i].area, pool[j]))
            geoms[j] = geoms[j].union(geoms[i])
            if not same and water[i] != water[j]:
                pass   # no same-kind neighbour: the sliver takes the kind of the neighbour
            for k, L in nbr[i].items():
                if k != j and k in alive:
                    nbr[j][k] = nbr[j].get(k, 0.0) + L
                    nbr[k][j] = nbr[j][k]
                    nbr[k].pop(i, None)
            nbr[j].pop(i, None)
            alive.discard(i)
            merged_into[i] = j
            moved = True
            break
        if not moved:
            break
    keep = sorted(alive)
    newid = {old: n for n, old in enumerate(keep)}
    out = gpd.GeoDataFrame({"water": [water[i] for i in keep]}, geometry=[shapely.make_valid(geoms[i]) for i in keep], crs=fg.crs)
    nb2 = [dict() for _ in keep]
    for old in keep:
        for k, L in nbr[old].items():
            if k in newid:
                nb2[newid[old]][newid[k]] = L
    return out, nb2, log_rows


def face_stats(fg):
    land = fg[~fg["water"]]
    a = land.area
    return dict(n=len(fg), n_water=int(fg["water"].sum()), n_land=len(land),
                p50=float(a.quantile(0.5)), p90=float(a.quantile(0.9)), max=float(a.max()))


# ------------------------------------------------------------------ 4. units -> faces

def edge_faces(cfg, geom, tree, face_geoms, tol, step, min_share):
    """Faces bordering an edge: those within tol of at least min_share of the samples that touch any face."""
    L = geom.length
    n = max(1, int(math.ceil(L / step)))
    pts = shapely.line_interpolate_point(geom, (np.arange(n) + 0.5) / n, normalized=True)
    near = tree.query(pts, predicate="dwithin", distance=tol)
    cnt = Counter()
    tot = set()
    for pi, fi in zip(near[0], near[1]):
        cnt[int(fi)] += 1
        tot.add(int(pi))
    if not tot:
        return []
    need = min_share * len(tot)
    sel = [f for f, c in cnt.items() if c >= need]
    if not sel:
        sel = [sorted(cnt.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]]
    return sorted(sel)


def face_values(uf, item_index, item_w, units_of, n_faces):
    """Sum share * weight (and share * units) per face."""
    idx = np.array([item_index[(t, k)] for t, k in zip(uf["unit_type"], uf["key"])])
    w = uf["share"].to_numpy() * item_w[idx]
    u = uf["share"].to_numpy() * units_of[idx]
    return (np.bincount(uf["face_id"], weights=w, minlength=n_faces),
            np.bincount(uf["face_id"], weights=u, minlength=n_faces))


def bridge_regions(uf, br, reg, item_by_key):
    """For every bridge: tier and the set of regions its land faces touch."""
    rows = []
    for b in br:
        k = b["key"]
        it = item_by_key[k]
        sub = uf[(uf["key"] == k) & (uf["unit_type"].isin(["edge", "tram"]))]
        regs = sorted({int(reg[f]) for f in sub["face_id"] if reg[f] >= 0})
        rows.append(dict(key=k, tier=it["tier"], tram=it["kind"] == "tram", regions=regs, overlap_m=b["overlap_m"]))
    return rows


def merge_regions(cfg, reg, fmin, bridges, mean_zone_minutes):
    """Merge regions below min_region_share * mean zone minutes into the region reached by their best bridge."""
    thr = cfg["min_region_share"] * mean_zone_minutes
    group = {int(r): int(r) for r in sorted(set(reg[reg >= 0]))}
    minutes = {r: float(fmin[reg == r].sum()) for r in group}
    log_rows = []
    rank = {"A": 0, "B": 1, "C": 2}
    while True:
        gm = defaultdict(float)
        for r, g in group.items():
            gm[g] += minutes[r]
        small = sorted((m, g) for g, m in gm.items() if m < thr)
        done = False
        for m, g in small:
            cands = []
            for b in bridges:
                gs = {group[r] for r in b["regions"]}
                if g in gs and len(gs) > 1:
                    for other in sorted(gs - {g}):
                        cands.append((rank[b["tier"]], b["tram"], -b["overlap_m"], b["key"], other, b))
            if not cands:
                continue
            cands.sort(key=lambda c: c[:4])
            best = cands[0]
            tgt = best[4]
            for r in [r for r, gg in group.items() if gg == g]:
                group[r] = tgt
            log_rows.append(dict(region=g, minutes=m, into=tgt, bridge=best[3], tier=best[5]["tier"]))
            done = True
            break
        if not done:
            break
    gm = defaultdict(float)
    for r, g in group.items():
        gm[g] += minutes[r]
    unmerged_small = [(g, m) for g, m in gm.items() if m < thr]
    return group, log_rows, unmerged_small, thr


def largest_remainder(minutes_by_region, total_zones, fixed=None):
    fixed = fixed or {}
    free = {r: m for r, m in minutes_by_region.items() if r not in fixed}
    left = total_zones - sum(fixed.values())
    tot = sum(free.values())
    quota = {r: left * m / tot for r, m in free.items()}
    k = {r: max(1, int(math.floor(q))) for r, q in quota.items()}
    rem = sorted(free, key=lambda r: (-(quota[r] - math.floor(quota[r])), r))
    i = 0
    while sum(k.values()) < left:
        k[rem[i % len(rem)]] += 1
        i += 1
    while sum(k.values()) > left:   # k >= 1 forced too many: take from the largest k with the smallest remainder
        r = sorted((r for r in k if k[r] > 1), key=lambda r: (quota[r] - k[r], r))[0]
        k[r] -= 1
    out = dict(k)
    out.update(fixed)
    return out, quota


def orphan_links(fg, reg, group, orphans):
    """Attach tiny regions without any bridge to the geometrically nearest face of another region."""
    geoms = fg.geometry.to_numpy()
    out = []
    for g in orphans:
        mine = [f for f in range(len(fg)) if reg[f] >= 0 and group[reg[f]] == g]
        best = None
        for f in mine:
            for h in range(len(fg)):
                if reg[h] >= 0 and group[reg[h]] != g:
                    dd = geoms[f].distance(geoms[h])
                    if best is None or (dd, f, h) < best:
                        best = (dd, f, h)
        out.append(best)
    return out


def expected_balance(gmin, k):
    tot = sum(gmin.values())
    return max(gmin[g] / k[g] for g in gmin) / (tot / sum(k.values()))


def group_graph(land_faces, nbr, links):
    """Local adjacency (real shared boundary + synthetic links) of a set of faces."""
    pos = {f: i for i, f in enumerate(land_faces)}
    loc = [dict() for _ in land_faces]
    for f in land_faces:
        for h, L in nbr[f].items():
            if h in pos:
                loc[pos[f]][pos[h]] = max(1, int(round(L)))
    for a, b, w in links:
        if a in pos and b in pos:
            loc[pos[a]][pos[b]] = loc[pos[a]].get(pos[b], 0) + w
            loc[pos[b]][pos[a]] = loc[pos[b]].get(pos[a], 0) + w
    return pos, loc


def metis_group(cfg, c16, loc, vmin, k):
    """Best of several ufactors by max/mean of the group's zone minutes; zones repaired to be connected."""
    if k == 1:
        return np.zeros(len(loc), int), 0, None
    wint = np.maximum(1, np.rint(vmin * cfg["weight_scale"])).astype(int)
    xadj, adjncy, ew = v0.to_csr(loc)
    best = None
    for uf in cfg["metis_ufactor_try"]:
        opt = pymetis.Options(seed=c16["seed"], contig=1, ufactor=int(uf), ncuts=c16["metis"]["ncuts"],
                              niter=c16["metis"]["niter"], numbering=0)
        _, part = pymetis.part_graph(k, xadj=xadj, adjncy=adjncy, vweights=wint, eweights=ew, options=opt)
        part = np.array(part)
        part, moves = v0.repair(part, loc, wint.astype(float))
        tot = np.bincount(part, weights=vmin, minlength=k)
        bal = float(tot.max() / tot.mean()) if tot.min() > 0 else 99.0
        if best is None or bal < best[1] - 1e-12:
            best = (part, bal, uf, len(moves))
    return best[0], best[3], (best[1], best[2])


def zone_connected(zface, zones_of, nbr_ext):
    """True when the faces of one zone form one connected set in nbr_ext (dict-of-dict, global face ids)."""
    faces = [f for f in zface]
    if not faces:
        return False
    s = set(faces)
    seen, stack = {faces[0]}, [faces[0]]
    while stack:
        u = stack.pop()
        for v in nbr_ext[u]:
            if v in s and v not in seen:
                seen.add(v)
                stack.append(v)
    return len(seen) == len(s)


def smooth(cfg, zone, fmin, perim, nbr, nbr_ext, group_of_face, n_zones, mean):
    """Move tongue faces (> smooth_share of the perimeter touches one neighbouring zone) while balance holds."""
    moves = []
    zmin = np.bincount(zone[zone >= 0], weights=fmin[zone >= 0], minlength=n_zones)
    for it in range(cfg["smooth_iter"]):
        n_moved = 0
        for f in range(len(zone)):
            if zone[f] < 0:
                continue
            touch = defaultdict(float)
            for h, L in nbr[f].items():
                if zone[h] >= 0:
                    touch[int(zone[h])] += L
            cand = [(L / perim[f], z) for z, L in touch.items() if z != zone[f] and L / perim[f] > cfg["smooth_share"]]
            if not cand:
                continue
            share, z = sorted(cand, key=lambda c: (-c[0], c[1]))[0]
            old = int(zone[f])
            new_t = zmin.copy()
            new_t[old] -= fmin[f]
            new_t[z] += fmin[f]
            cur_b, new_b = zmin.max() / mean, new_t.max() / mean
            if new_b > max(cfg["balance_face_max"], cur_b) + 1e-12:
                continue
            rest = [h for h in range(len(zone)) if zone[h] == old and h != f]
            if not rest or not zone_connected(rest, None, nbr_ext):
                continue
            zone[f] = z
            zmin = new_t
            moves.append((it + 1, f, old, z, share))
            n_moved += 1
        if not n_moved:
            break
    return moves


def balance_pass(cfg, zone, fmin, perim, nbr, nbr_ext, group_of_face, nz):
    """Per region: move boundary faces from the heaviest zone to a lighter neighbour while the pair maximum drops."""
    moves = []
    zmin = np.bincount(zone[zone >= 0], weights=fmin[zone >= 0], minlength=nz)
    zgroup = {}
    for f in range(len(zone)):
        if zone[f] >= 0:
            zgroup[int(zone[f])] = int(group_of_face[f])
    groups = sorted(set(zgroup.values()))
    for it in range(cfg["balance_iter"]):
        moved = False
        for g in groups:
            zs = [z for z in zgroup if zgroup[z] == g]
            if len(zs) < 2:
                continue
            zmax = max(zs, key=lambda z: (zmin[z], -z))
            best = None
            for f in np.flatnonzero(zone == zmax):
                touch = defaultdict(float)
                for h, L in nbr[f].items():
                    if zone[h] >= 0 and zone[h] != zmax:
                        touch[int(zone[h])] += L
                for z2, L in touch.items():
                    if L / perim[f] < cfg["balance_min_touch"]:
                        continue
                    new_pair = max(zmin[zmax] - fmin[f], zmin[z2] + fmin[f])
                    if new_pair < zmin[zmax] - 1e-9:
                        key = (new_pair, -L / perim[f], int(f), z2)
                        if best is None or key < best:
                            best = key
            if best is None:
                continue
            _, _, f, z2 = best
            rest = [h for h in np.flatnonzero(zone == zmax) if h != f]
            if not rest or not zone_connected(rest, None, nbr_ext):
                # try the next-best moves is not needed for a first version: stop this region
                continue
            zone[f] = z2
            zmin[zmax] -= fmin[f]
            zmin[z2] += fmin[f]
            moves.append((f, zmax, z2))
            moved = True
        if not moved:
            break
    return moves


def run_partition(cfg, c16, ctx, fmin, scn_name, k_fixed=None, apply_stop=False):
    """Allocation + METIS per merged region + smoothing. Returns dict with zone per face (0..10) and diagnostics."""
    fg, nbr, group_of_face, groups, links, perim = ctx["fg"], ctx["nbr"], ctx["group_of_face"], ctx["groups"], ctx["links"], ctx["perim"]
    gmin = {g: float(fmin[group_of_face == g].sum()) for g in groups}
    kk, quota = largest_remainder(gmin, c16["zones"], fixed=k_fixed)
    exp_bal = expected_balance(gmin, kk)
    out = dict(gmin=gmin, k=kk, quota=quota, expected_balance=exp_bal)
    if apply_stop and exp_bal > cfg["allocation_stop_balance"]:
        out["stopped"] = True
        return out
    n = len(fg)
    zone = np.full(n, -1)
    base = 0
    info = {}
    for g in sorted(groups):
        lf = [f for f in range(n) if group_of_face[f] == g]
        pos, loc = group_graph(lf, nbr, [l for l in links if group_of_face[l[0]] == g])
        part, nmoves, bi = metis_group(cfg, c16, loc, fmin[lf], kk[g])
        for f, p in zip(lf, part):
            zone[f] = base + int(p)
        info[g] = dict(k=kk[g], repair_moves=nmoves, best=bi)
        base += kk[g]
    nz = base
    mean = fmin[zone >= 0].sum() / nz
    nbr_ext = ctx["nbr_ext"]
    out["pre_smooth_balance"] = float(np.bincount(zone[zone >= 0], weights=fmin[zone >= 0], minlength=nz).max() / mean)
    sm = smooth(cfg, zone, fmin, perim, nbr, nbr_ext, group_of_face, nz, mean)
    out["zone_prepass"] = zone.copy()
    out["post_smooth_balance"] = float(np.bincount(zone[zone >= 0], weights=fmin[zone >= 0], minlength=nz).max() / mean)
    bm = balance_pass(cfg, zone, fmin, perim, nbr, nbr_ext, group_of_face, nz) if cfg["balance_pass"] else []
    sm2 = smooth(cfg, zone, fmin, perim, nbr, nbr_ext, group_of_face, nz, mean) if bm else []
    zt = np.bincount(zone[zone >= 0], weights=fmin[zone >= 0], minlength=nz)
    out.update(zone=zone, n_zones=nz, smooth_moves=sm, balance_moves=bm, smooth2_moves=sm2, balance=float(zt.max() / mean), zmin=zt, metis=info)
    return out


# ------------------------------------------------------------------ labels, ownership

def label_zones(fg, zone, ring_centre):
    """Raw zone index -> label 1..n, clockwise from north by zone centroid."""
    nz = int(zone.max()) + 1
    ang = []
    for z in range(nz):
        c = unary_union(fg.geometry.to_numpy()[zone == z]).centroid
        ang.append(math.atan2(c.x - ring_centre[0], c.y - ring_centre[1]) % (2 * math.pi))
    rank = np.argsort(np.argsort(ang, kind="stable"), kind="stable")
    return rank + 1


def overlap_by_zone(hull, tree, geoms, face_zone, min_area):
    acc = defaultdict(float)
    for f in tree.query(hull, predicate="intersects"):
        z = int(face_zone[f])
        if z > 0:
            a = hull.intersection(geoms[f]).area
            if a > min_area:
                acc[z] += a
    return dict(acc)


def cluster_hulls(cfg, c16, d):
    jn = d["jn"].to_crs(c16["crs_metric"])
    jn = jn[jn["junction_cluster_id"].isin(set(d["vt"]["junction_cluster_id"]))]
    out = {}
    r = cfg["cluster_node_radius_m"]
    for cid, grp in jn.groupby("junction_cluster_id"):
        out[int(cid)] = unary_union([p.buffer(r) for p in grp.geometry])
    return out


def bridge_names(c16, d, bridges, items_by_key):
    sg = gpd.read_file(c16["paths"]["ownership"], layer="segments")
    sg = sg[sg["edge_id"].isin([b["key"] for b in bridges])]
    ways = gpd.read_file(c16["paths"]["features"], layer="ways", columns=["osm_id", "name"], ignore_geometry=True) \
        if False else gpd.read_file(c16["paths"]["features"], layer="ways").drop(columns="geometry")
    nm = dict(zip(ways["osm_id"].astype(int), ways["name"]))
    best = {}
    for r in sg.itertuples():
        if r.edge_id not in best or r.length_m > best[r.edge_id][1]:
            best[r.edge_id] = (int(r.way_id), r.length_m)
    tram = d["tram"].set_index("edge_id")
    out = {}
    for b in bridges:
        k = b["key"]
        if k in best:
            wid = best[k][0]
        else:
            wid = int(tram.loc[k, "way_id"])
        n = nm.get(wid)
        out[k] = (wid, "" if n is None or (isinstance(n, float) and math.isnan(n)) else str(n))
    return out


def compactness(geom):
    a = geom.area
    return (a / geom.convex_hull.area if geom.convex_hull.area else float("nan"), geom.length / math.sqrt(a) if a else float("nan"))


# ------------------------------------------------------------------ main

def zone_totals(face_label, fmin, nz):
    return np.bincount(face_label[face_label > 0] - 1, weights=fmin[face_label > 0], minlength=nz)


def match_labels(ref_label, raw_zone, w, nz):
    """Hungarian match of scenario zones (0..nz-1) to reference labels (1..nz) by shared weight."""
    ov = np.zeros((nz, nz))
    ok = (raw_zone >= 0) & (ref_label > 0)
    np.add.at(ov, (raw_zone[ok], ref_label[ok] - 1), w[ok])
    r, c = linear_sum_assignment(-ov)
    mp = np.zeros(nz, int)
    mp[r] = c
    return mp


def layer_digest_one(path, layer):
    g = gpd.read_file(path, layer=layer)
    h = hashlib.sha256()
    h.update(g.drop(columns="geometry").to_csv(index=False).encode())
    h.update(b"".join(shapely.to_wkb(g.geometry.to_numpy())))
    return h.hexdigest()


def fmt_pair(p):
    return f"{p[0]}-{p[1]}"




def adjacency(fg, min_len):
    """Shared boundary length of every pair of touching faces (tolerant to 1 cm vertex noise)."""
    tree = shapely.STRtree(fg.geometry.to_numpy())
    geoms = fg.geometry.to_numpy()
    bnd = shapely.boundary(geoms)
    nbr = [dict() for _ in range(len(fg))]
    a, b = tree.query(geoms, predicate="intersects")
    for i, j in zip(a, b):
        if i < j:
            L = bnd[i].intersection(bnd[j].buffer(0.01)).length
            if L > min_len:
                nbr[i][int(j)] = float(L)
                nbr[j][int(i)] = float(L)
    return nbr


def make_faces(cfg, base, extra=None):
    """Polygonize the noded linework (coarse roads, barrier outline, RING 1 boundary, optional extra lines)."""
    ring, barrier = base["ring"], base["barrier"]
    lines = [base["roads_coarse"], ring.boundary]
    if not barrier.is_empty:
        lines.append(barrier.boundary)
    if extra is not None and not extra.is_empty:
        lines.append(extra)
    noded = unary_union(lines)
    faces = [p for p in polygonize(noded) if p.representative_point().within(ring)]
    faces.sort(key=lambda p: (round(p.representative_point().x, 3), round(p.representative_point().y, 3)))
    n_raw = len(faces)
    water_flag = [bool(not barrier.is_empty and p.intersection(barrier).area > 0.5 * p.area) for p in faces]
    fg = gpd.GeoDataFrame({"water": water_flag}, geometry=faces, crs=cfg["crs_metric"])
    nbr = adjacency(fg, cfg["face_adjacency_min_m"])
    fg, nbr, slivers = merge_slivers(fg, nbr, cfg["sliver_m2"], cfg["face_adjacency_min_m"])
    fg["face_id"] = np.arange(len(fg))
    fg["area"] = fg.area
    return fg, nbr, n_raw, slivers


def assign_units(cfg, d, items, fg, barrier, bridge_info):
    """Unit -> faces table. Bridges (bridge_info: key -> metres over water) are assigned to the land faces at their ends."""
    tol, step, share = cfg["edge_boundary_tol_m"], cfg["edge_sample_step_m"], cfg["edge_face_min_share"]
    geoms = fg.geometry.to_numpy()
    tree = shapely.STRtree(geoms)
    land = ~fg["water"].to_numpy()
    land_ids = np.flatnonzero(land)
    land_tree = shapely.STRtree(geoms[land_ids])
    geo = {int(r.edge_id): r.geometry for r in d["edges"].itertuples()}
    geo.update({int(r.edge_id): r.geometry for r in d["tram"].itertuples()})
    rows = []
    nearest_land = lambda pt: int(land_ids[int(land_tree.nearest(pt))])
    for it in items:
        if it["kind"] == "site":
            hull = d["hulls"][it["key"]]
            cand = tree.query(hull, predicate="intersects")
            fs = [int(f) for f in cand if land[f] and hull.intersection(geoms[f]).area > cfg["hull_touch_min_m2"]]
            how = "hull"
            if not fs:
                fs, how = [nearest_land(shapely.Point(it["x"], it["y"]))], "nearest"
            for f in sorted(fs):
                rows.append((it["kind"], it["key"], f, 1.0 / len(fs), how))
            continue
        g = geo[it["key"]]
        if it["key"] in bridge_info:
            parts = [p for p in shapely.get_parts(g.difference(barrier)) if p.length > 0]
            fs = sorted({f for p in parts for f in edge_faces(cfg, p, tree, geoms, tol, step, share) if land[f]})
            how = "bridge"
            if not fs:
                fs = sorted({nearest_land(shapely.Point(g.coords[0])), nearest_land(shapely.Point(g.coords[-1]))})
                how = "bridge-nearest"
        elif it["kind"] == "tram":
            mid = g.interpolate(0.5, normalized=True)
            fs = [int(f) for f in tree.query(mid, predicate="intersects") if land[f]]
            how = "midpoint"
            if not fs:
                fs, how = [nearest_land(mid)], "nearest"
        else:
            fs = edge_faces(cfg, g, tree, geoms, tol, step, share)
            how = "boundary" if len(fs) > 1 else "single"
            fs = [f for f in fs if land[f]] or [nearest_land(g.interpolate(0.5, normalized=True))]
        for f in sorted(fs):
            rows.append((it["kind"], it["key"], f, 1.0 / len(fs), how))
    return pd.DataFrame(rows, columns=["unit_type", "key", "face_id", "share", "how"]), geo


def land_regions(fg, nbr):
    """Connected land components, numbered 1.. by decreasing area (stable when faces are subdivided)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components
    land = ~fg["water"].to_numpy()
    r, c = [], []
    for i, dct in enumerate(nbr):
        if not land[i]:
            continue
        for j in dct:
            if land[j]:
                r.append(i)
                c.append(j)
    n = len(fg)
    adj = coo_matrix((np.ones(len(r)), (r, c)), shape=(n, n))
    nc, lab = connected_components(adj, directed=False)
    area = fg["area"].to_numpy()
    first = {}
    tot = defaultdict(float)
    for f in range(n):
        if land[f]:
            tot[int(lab[f])] += area[f]
            first.setdefault(int(lab[f]), f)
    order = sorted(tot, key=lambda c_: (-round(tot[c_], 3), first[c_]))
    remap = {c_: i + 1 for i, c_ in enumerate(order)}
    return np.array([remap[int(lab[f])] if land[f] else -1 for f in range(n)])


def build_base(cfg, c16, d):
    """Inputs that do not depend on the face subdivision: water, barrier, linework, items, hulls, bridges."""
    crs = cfg["crs_metric"]
    ring = d["poly"].geometry.iloc[0]
    gj, bbox = extract_water(cfg, ring)
    water = load_water(cfg, gj)
    wg, barrier, names = select_barriers(cfg, water, ring)
    wtab = water_table(cfg, wg)
    sg = gpd.read_file(cfg["paths"]["ownership"], layer="segments").to_crs(crs)
    sg = sg[~sg["is_tram"] & sg.intersects(ring)]

    def lines_of(classes):
        g = unary_union(sg[sg["highway"].isin(classes)].geometry.to_numpy()).intersection(ring)
        return g.difference(barrier) if not barrier.is_empty else g

    vt = d["vt"]
    vid, xy, pair, loops = v0.build_vertex_graph(c16, vt, d["edges"])
    sv = v0.site_vertices(c16, d, vid, xy)
    items = v0.build_items(c16, d, vid, xy, sv)
    hulls = gpd.read_file(c16["paths"]["sites"], layer="site_hulls").to_crs(crs)
    hull_of = dict(zip(hulls["site_id"].astype(int), hulls.geometry))
    sites_xy = {it["key"]: (it["x"], it["y"]) for it in items if it["kind"] == "site"}
    for k_, h in list(hull_of.items()):
        if h.area < 50:
            hull_of[k_] = h.union(shapely.Point(*sites_xy[k_]).buffer(cfg["site_min_radius_m"]))
    d["hulls"] = hull_of
    cid = vt["junction_cluster_id"].to_numpy().astype(int)
    sv_ids = {sid: [int(cid[v]) for v in vs] for sid, vs in sv.items()}
    cluster_site = {c: sid for sid, cl in sv_ids.items() for c in cl}
    inv = set(cid.tolist())
    edge_ends = {int(r.edge_id): [int(c) for c in (r.cluster_a, r.cluster_b) if int(c) in inv] for r in d["edges"].itertuples()}
    geo = {int(r.edge_id): r.geometry for r in d["edges"].itertuples()}
    geo.update({int(r.edge_id): r.geometry for r in d["tram"].itertuples()})
    bridge_info = {}
    for k_, g in geo.items():
        over = g.intersection(barrier).length if not barrier.is_empty else 0.0
        mid_in = k_ < 0 and not barrier.is_empty and barrier.contains(g.interpolate(0.5, normalized=True))
        if over > cfg["bridge_min_overlap_m"] or mid_in:
            bridge_info[k_] = float(over)
    item_index = {(it["kind"], it["key"]): i for i, it in enumerate(items)}
    item_by_key = {it["key"]: it for it in items if it["kind"] != "site"}
    units_of = np.array([it["n_units"] if it["kind"] == "site" else 1 for it in items], float)
    return dict(d=d, ring=ring, bbox=bbox, water=wg, wtab=wtab, barrier=barrier, names=names,
                roads_coarse=lines_of(cfg["boundary_classes"]),
                roads_fine=lines_of(list(cfg["boundary_classes"]) + list(cfg["split_extra_classes"])),
                items=items, sv=sv, sv_ids=sv_ids, cluster_site=cluster_site, edge_ends=edge_ends, geo=geo,
                bridge_info=bridge_info, item_index=item_index, item_by_key=item_by_key, units_of=units_of,
                hulls_eff=hull_of, vid=vid, chulls=cluster_hulls(cfg, c16, d))


def attach_faces(cfg, c16, base, fg, nbr, n_raw, slivers, parent=None):
    ctx = dict(base)
    ctx.update(fg=fg, nbr=nbr, n_raw=n_raw, slivers=slivers, perim=fg.geometry.length.to_numpy(), parent=parent)
    uf, _ = assign_units(cfg, base["d"], base["items"], fg, base["barrier"], base["bridge_info"])
    ctx["uf"] = uf
    ctx["bridges"] = [dict(key=k_, overlap_m=o) for k_, o in sorted(base["bridge_info"].items())]
    return ctx


def item_weights(c16, scn, items):
    return np.array([v0.item_weight(c16, scn, it) for it in items])


def split_heavy(cfg, c16, base, ctx0, fm0):
    """Subdivide land faces above split_face_minutes with all road classes as boundaries."""
    fg0 = ctx0["fg"]
    heavy = [f for f in range(len(fg0)) if not fg0["water"].iloc[f] and fm0[f] > cfg["split_face_minutes"]]
    if not heavy:
        return None
    extra = unary_union([base["roads_fine"].intersection(fg0.geometry.iloc[f]) for f in heavy])
    fg, nbr, n_raw, slivers = make_faces(cfg, base, extra)
    tree = shapely.STRtree(fg0.geometry.to_numpy())
    parent = []
    for g in fg.geometry:
        hit = tree.query(g.representative_point(), predicate="within")
        parent.append(int(hit[0]) if len(hit) else -1)
    return fg, nbr, n_raw, slivers, np.array(parent), heavy


def setup_regions(cfg, c16, ctx, fmin0, reg=None):
    fg, nbr, uf = ctx["fg"], ctx["nbr"], ctx["uf"]
    if reg is None:
        reg = land_regions(fg, nbr)
    brs = bridge_regions(uf, ctx["bridges"], reg, ctx["item_by_key"])
    mean_zone = fmin0.sum() / c16["zones"]
    group, mlog, uns, thr = merge_regions(cfg, reg, fmin0, brs, mean_zone)
    orphan_rows = []
    if cfg["orphan_policy"] == "nearest" and uns:
        for g, m in sorted(uns, key=lambda x: (x[1], x[0])):
            gm = defaultdict(float)
            for r, gg in group.items():
                gm[gg] += float(fmin0[reg == r].sum())
            if g not in gm or gm[g] >= thr:
                continue
            dd, f, h = orphan_links(fg, reg, group, [g])[0]
            tgt = group[int(reg[h])]
            members = [r for r, gg in group.items() if gg == g]
            for r in members:
                group[r] = tgt
            orphan_rows.append(dict(region=g, minutes=m, into=tgt, distance_m=float(dd), faces=(f, h), members=members))
    group_of_face = np.array([group[int(r)] if r >= 0 else -1 for r in reg])
    groups = sorted(set(group.values()))
    links, seen = [], set()
    for b in brs:
        by = defaultdict(list)
        for f in uf.loc[(uf["key"] == b["key"]) & (uf["unit_type"].isin(["edge", "tram"])), "face_id"]:
            if reg[f] >= 0:
                by[int(reg[f])].append(int(f))
        rs = sorted(by)
        for i, ra in enumerate(rs):
            for rb in rs[i + 1:]:
                if group[ra] == group[rb] and (ra, rb) not in seen:
                    seen.add((ra, rb))
                    links.append((min(by[ra]), min(by[rb]), cfg["bridge_link_weight"]))
    for row in orphan_rows:
        links.append((row["faces"][0], row["faces"][1], cfg["bridge_link_weight"]))
    extra_links = []
    while True:
        nbr_ext = [dict(x) for x in nbr]
        for a, b, w in links:
            nbr_ext[a][b] = nbr_ext[a].get(b, 0) + w
            nbr_ext[b][a] = nbr_ext[b].get(a, 0) + w
        added = False
        for g in groups:
            lf = [f for f in range(len(fg)) if group_of_face[f] == g]
            comps, left = [], set(lf)
            while left:
                s0 = min(left)
                st, seen_ = [s0], {s0}
                while st:
                    u = st.pop()
                    for v in nbr_ext[u]:
                        if v in left and v not in seen_:
                            seen_.add(v)
                            st.append(v)
                comps.append(sorted(seen_))
                left -= seen_
            if len(comps) > 1:
                comps.sort(key=lambda c: (-len(c), c[0]))
                geoms = fg.geometry.to_numpy()
                best = min(((geoms[a].distance(geoms[b]), a, b) for a in comps[1] for b in comps[0]))
                links.append((best[1], best[2], cfg["bridge_link_weight"]))
                extra_links.append(best)
                added = True
                break
        if not added:
            break
    ctx.update(reg=reg, brs=brs, group=group, groups=groups, group_of_face=group_of_face, links=links, nbr_ext=nbr_ext,
               merge_log=mlog, orphan_rows=orphan_rows, region_threshold=thr, extra_links=extra_links)
    return ctx


def group_balance(res, fmin, nz, ctx):
    """Within-region balance: zone minutes against the mean of the zones of the same region."""
    out = {}
    zone, gof = res["zone"], ctx["group_of_face"]
    zt = np.bincount(zone[zone >= 0], weights=fmin[zone >= 0], minlength=nz)
    zg = {}
    for f in range(len(zone)):
        if zone[f] >= 0:
            zg[int(zone[f])] = int(gof[f])
    for g in sorted(set(zg.values())):
        zs = [z for z in zg if zg[z] == g]
        v = zt[zs]
        out[g] = (float(v.max() / v.mean()), float(v.min() / v.mean()), len(zs), float(v.mean()))
    return out


def group_bridges(cfg, base, meta):
    """Group bridge edges (road and tram): equal name, or over-water parts within bridge_group_m of each other."""
    keys = sorted(base["bridge_info"])
    barrier, geo = base["barrier"], base["geo"]
    over = {}
    for k in keys:
        o = geo[k].intersection(barrier)
        over[k] = o if not o.is_empty else geo[k]
    parent = {k: k for k in keys}

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    by_name = defaultdict(list)
    for k in keys:
        if meta[k][1]:
            by_name[meta[k][1]].append(k)
    name_far = []
    for nm, ks in by_name.items():
        for k in ks[1:]:
            union(ks[0], k)
        if len(ks) > 1:
            far = max(over[a].distance(over[b]) for a in ks for b in ks)
            name_far.append((nm, ks, far))
    for i, a in enumerate(keys):
        for b in keys[i + 1:]:
            if over[a].distance(over[b]) <= cfg["bridge_group_m"]:
                union(a, b)
    members = defaultdict(list)
    for k in keys:
        members[find(k)].append(k)
    ordered = sorted(members.values(), key=lambda ks: (min((x for x in ks if x >= 0), default=10 ** 9), min(ks)))
    groups, gid_of = [], {}
    for i, ks in enumerate(ordered):
        names = Counter(meta[k][1] for k in ks if meta[k][1])
        nm = names.most_common(1)[0][0] if names else ""
        groups.append(dict(group_id=i + 1, name=nm, edges=sorted(ks), ways=sorted({meta[k][0] for k in ks})))
        for k in ks:
            gid_of[k] = i + 1
    return groups, gid_of, name_far


def ownership(cfg, c16, ctx, face_label, bridge_override):
    """Zone of clusters, sites, edges, bridge groups. face_label: label per face (0 = water)."""
    d, items, uf, fg = ctx["d"], ctx["items"], ctx["uf"], ctx["fg"]
    geoms = fg.geometry.to_numpy()
    tree = shapely.STRtree(geoms)
    vt = d["vt"]
    cids = vt["junction_cluster_id"].to_numpy().astype(int)
    maxdeg = dict(zip(cids, vt["max_degree"].astype(int)))
    own_c = {}
    for c in cids:
        ov = overlap_by_zone(ctx["chulls"][int(c)], tree, geoms, face_label, 0.0)
        own_c[int(c)] = sorted(ov.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if ov else 0
    site_zone, site_split = {}, []
    for it in items:
        if it["kind"] != "site":
            continue
        hull = ctx["hulls_eff"][it["key"]]
        ov = overlap_by_zone(hull, tree, geoms, face_label, cfg["hull_touch_min_m2"])
        if not ov:
            f = int(tree.nearest(hull))
            ov = {int(face_label[f]): 1.0} if face_label[f] > 0 else {}
        top = max(ov.values())
        tied = sorted(z for z, a in ov.items() if a >= top - 1e-6)
        if len(tied) > 1:
            md = {z: max([maxdeg[c] for c in ctx["sv_ids"].get(it["key"], []) if own_c.get(c) == z] or [0]) for z in tied}
            tied = sorted(tied, key=lambda z: (-md[z], z))
        site_zone[it["key"]] = tied[0]
        if len(ov) > 1:
            site_split.append((it["key"], dict(ov)))
    cluster_zone = dict(own_c)
    for sid, cl in ctx["sv_ids"].items():
        for c in cl:
            cluster_zone[c] = site_zone[sid]
    # edges: hull rule, then seam rule; bridges are overridden afterwards by their group owner
    hkeys = list(ctx["hulls_eff"].keys())
    htree = shapely.STRtree([ctx["hulls_eff"][k] for k in hkeys])
    ufe = uf[uf["unit_type"] != "site"]
    rows, in_site = {}, {}
    for key, grp in ufe.groupby("key", sort=True):
        key = int(key)
        g = ctx["geo"][key]
        ends = ctx["edge_ends"].get(key, [])
        site = None
        if len(ends) == 2 and ctx["cluster_site"].get(ends[0]) is not None and ctx["cluster_site"].get(ends[0]) == ctx["cluster_site"].get(ends[1]):
            site = ctx["cluster_site"][ends[0]]
        elif g.length > 0:
            best = (0.0, None)
            for hi in htree.query(g, predicate="intersects"):
                cov = g.intersection(ctx["hulls_eff"][hkeys[hi]]).length / g.length
                if cov > best[0] + 1e-12 or (abs(cov - best[0]) <= 1e-12 and best[1] is not None and hkeys[hi] < best[1]):
                    best = (cov, hkeys[hi])
            if best[0] >= cfg["hull_edge_cover"]:
                site = best[1]
        fz = [int(face_label[f]) for f in grp["face_id"]]
        cnt = Counter(fz)
        cand = sorted(cnt)
        if site is not None and key not in ctx["bridge_info"]:
            in_site[key] = site
            rows[key] = dict(zone=site_zone[site], seam=False, other=0, bridge=False, cand=cand, group=None)
            continue
        if len(cand) == 1:
            owner, other, seam = cand[0], 0, False
        else:
            ssum = {z: sum(maxdeg[c] for c in ends if cluster_zone.get(c) == z) for z in cand}
            owner = sorted(cand, key=lambda z: (-ssum[z], z))[0]
            other = sorted((z for z in cand if z != owner), key=lambda z: (-cnt[z], z))[0]
            seam = True
        rows[key] = dict(zone=owner, seam=seam, other=other, bridge=key in ctx["bridge_info"], cand=cand, group=None, cnt=dict(cnt))
    # bridge groups: one owner per group
    groups_out, refused = [], []
    for g in ctx["bridge_groups"]:
        ks = g["edges"]
        cnt = Counter()
        for k in ks:
            for z in rows[k]["cand"]:
                cnt[z] += rows[k].get("cnt", {z: 1}).get(z, 1)
        clusters = sorted({c for k in ks for c in ctx["edge_ends"].get(k, [])})
        ssum = Counter()
        for c in clusters:
            z = cluster_zone.get(c, 0)
            if z > 0:
                ssum[z] += maxdeg[c]
        cand = sorted(cnt)   # only a zone that touches the bridge by faces can own it (its strip must join its polygon)
        owner = sorted(cand, key=lambda z: (-ssum.get(z, 0), -cnt[z], z))[0]
        ov = None
        for k in ks:
            ov = bridge_override.get(("edge", k), ov)
        for w in g["ways"]:
            ov = bridge_override.get(("way", w), ov)
        if ov is not None:
            if ov in cand:
                owner = ov
            else:
                refused.append((g["group_id"], ks[0], ov, cand))
        others = sorted((z for z in cnt if z != owner), key=lambda z: (-cnt[z], z))
        other = others[0] if others else 0
        for k in ks:
            rows[k].update(zone=owner, seam=bool(other), other=other, bridge=True, group=g["group_id"])
        groups_out.append(dict(g, owner_zone=owner, other_zone=other or None, candidates=cand, sums=dict(ssum)))
    return dict(cluster_zone=cluster_zone, site_zone=site_zone, site_split=site_split, edge_rows=rows, groups=groups_out,
                bridge_refused=refused, in_site=in_site)


def zone_polygons(cfg, ctx, face_label, own, nz):
    """polygon(z) = faces(z) + hulls of sites owned by z + strips of its bridge groups - hulls of other zones' sites."""
    geoms, ring, barrier = ctx["fg"].geometry.to_numpy(), ctx["ring"], ctx["barrier"]
    empty = shapely.Polygon()
    H = defaultdict(list)
    for sid, z in own["site_zone"].items():
        H[z].append(ctx["hulls_eff"][sid].intersection(ring))
    used, hull_final = empty, {}
    for z in range(1, nz + 1):
        hz = unary_union(H[z]).difference(used) if H[z] else empty
        hull_final[z] = hz
        used = used.union(hz)
    strip_used, strip_final = empty, {}
    S = defaultdict(list)
    gstrip = {}
    for g in own["groups"]:
        s = unary_union([ctx["geo"][k] for k in g["edges"]]).buffer(cfg["bridge_strip_m"]).intersection(barrier)
        S[g["owner_zone"]].append(s)
        gstrip[g["group_id"]] = s
    for z in range(1, nz + 1):
        sz = unary_union(S[z]).difference(used).difference(strip_used) if S[z] else empty
        strip_final[z] = sz
        strip_used = strip_used.union(sz)
    polys = {}
    for z in range(1, nz + 1):
        others = unary_union([hull_final[y] for y in hull_final if y != z])
        fz = unary_union(geoms[face_label == z]).difference(others)
        polys[z] = unary_union([fz, hull_final[z], strip_final[z]])
    pieces = []
    for z, p in polys.items():
        for q in shapely.get_parts(p):
            if q.geom_type == "Polygon" and q.area > 0:
                pieces.append([z, q])
    main = {}
    for i, (z, q) in enumerate(pieces):
        if z not in main or q.area > pieces[main[z]][1].area:
            main[z] = i
    merged_slivers, dropped = [], []
    while True:
        small = sorted(((q.area, z, i) for i, (z, q) in enumerate(pieces) if q is not None and main.get(z) != i and q.area < cfg["sliver_polygon_m2"]))
        if not small:
            break
        a, z, i = small[0]
        q = pieces[i][1]
        best = None
        for j, (zj, qj) in enumerate(pieces):
            if j == i or qj is None:
                continue
            L = q.boundary.intersection(qj.boundary.buffer(0.01)).length
            if L > 0.05 and (best is None or (-L, zj, j) < best[0]):
                best = ((-L, zj, j), j)
        if best is None:
            dropped.append((z, a))
        else:
            j = best[1]
            pieces[j][1] = unary_union([pieces[j][1], q])
            merged_slivers.append((z, pieces[j][0], a))
        pieces[i][1] = None
    # detached lobes of ordinary land (cut off by the hull of another zone's site) join the neighbour with the longest border;
    # detached island land and bridge strips are legitimate and are only listed
    reg, group = ctx["reg"], ctx["group"]
    isl_mask = np.array([r >= 0 and group[int(r)] != int(r) for r in reg])
    island_u = unary_union(geoms[isl_mask]) if isl_mask.any() else empty
    lobes = []
    while True:
        cand = []
        for i, (z, q) in enumerate(pieces):
            if q is None or main.get(z) == i:
                continue
            water_share = q.intersection(barrier).area / q.area if q.area and not barrier.is_empty else 0.0
            isl_share = q.intersection(island_u).area / q.area if q.area and not island_u.is_empty else 0.0
            if water_share < 0.5 and isl_share < 0.5:
                cand.append((q.area, z, i))
        if not cand:
            break
        a, z, i = sorted(cand)[0]
        q = pieces[i][1]
        best = None
        for j, (zj, qj) in enumerate(pieces):
            if j == i or qj is None or zj == z:
                continue
            L = q.boundary.intersection(qj.boundary.buffer(0.01)).length
            if L > 0.05 and (best is None or (-L, zj, j) < best[0]):
                best = ((-L, zj, j), j)
        if best is None:
            main[z] = main.get(z)  # nothing to merge into; leave as an exception below
            pieces[i].append("stuck")
            break
        j = best[1]
        lobes.append((z, pieces[j][0], a))
        pieces[j][1] = unary_union([pieces[j][1], q])
        pieces[i][1] = None
    final = defaultdict(list)
    for z, q, *_ in pieces:
        if q is not None:
            final[z].append(q)
    out, raw = {}, []
    for z in range(1, nz + 1):
        u = unary_union(final[z])
        out[z] = u
        parts = shapely.get_parts(u)
        if len(parts) > 1:
            for q in sorted(parts, key=lambda x: -x.area)[1:]:
                raw.append((z, q))
    island_regions = {}
    for r in sorted(set(reg[reg >= 0])):
        if group[int(r)] != int(r):
            island_regions[int(r)] = unary_union(geoms[reg == r])
    exceptions = []
    for z, q in raw:
        ws = q.intersection(barrier).area / q.area if not barrier.is_empty else 0.0
        isl_s = q.intersection(island_u).area / q.area if not island_u.is_empty else 0.0
        kind = "bridge_strip" if ws >= 0.5 else ("island_land" if isl_s >= 0.5 else "other")
        ref = None
        if kind == "bridge_strip":
            ref = max(gstrip, key=lambda g_: (q.intersection(gstrip[g_]).area, -g_), default=None)
        elif kind == "island_land":
            ref = max(island_regions, key=lambda r_: (q.intersection(island_regions[r_]).area, -r_), default=None)
        touches = [y for y in range(1, nz + 1) if y != z and out[y].distance(q) <= 0.05]
        exceptions.append(dict(zone=z, area=float(q.area), where=(round(q.centroid.x), round(q.centroid.y)), kind=kind, ref=ref,
                               touches=touches, geometry=q))
    # borders between zone polygons against site hulls shrunk by 3 m
    zs = list(range(1, nz + 1))
    border_parts = []
    for i, a in enumerate(zs):
        for b in zs[i + 1:]:
            if out[a].intersects(out[b]):
                sh = out[a].boundary.intersection(out[b].boundary.buffer(0.01))
                if not sh.is_empty and sh.length > 0:
                    border_parts.append(sh)
    borders = unary_union(border_parts) if border_parts else empty
    thru = []
    for sid, h in ctx["hulls_eff"].items():
        core = h.intersection(ring).buffer(-cfg["hull_border_tol_m"])
        if not core.is_empty and borders.intersects(core):
            thru.append((sid, own["site_zone"][sid], float(borders.intersection(core).length)))
    return out, dict(exceptions=exceptions, lobes=lobes, merged_slivers=merged_slivers, dropped=dropped, hull_through=thru,
                     hull_final=hull_final, strip_final=strip_final, borders=borders)


def apply_face_overrides(fz, face_label, ctx, nz):
    applied, refused = [], []
    gof = ctx["group_of_face"]
    for r in fz.itertuples():
        f, z = int(r.face_id), int(r.zone)
        if f < 0 or f >= len(face_label) or gof[f] < 0:
            refused.append((f, z, "not a land face"))
        elif z < 1 or z > nz:
            refused.append((f, z, f"zone outside 1..{nz}"))
        elif not any(face_label[h] == z and gof[h] == gof[f] for h in range(len(face_label))):
            refused.append((f, z, "zone has no face in the same region (would lie across a barrier)"))
        else:
            applied.append((f, int(face_label[f]), z))
            face_label[f] = z
    return applied, refused


def apply_island_overrides(isl, face_label, ctx, nz):
    applied, refused = [], []
    gof, reg, group = ctx["group_of_face"], ctx["reg"], ctx["group"]
    for r in isl.itertuples():
        rid, z = int(r.region_id), int(r.zone)
        fs = np.flatnonzero(reg == rid)
        if rid not in group or group[rid] == rid or not len(fs):
            refused.append((rid, z, "not a merged island"))
        elif z < 1 or z > nz or not any(face_label[h] == z and gof[h] == group[rid] and reg[h] != rid for h in range(len(face_label))):
            refused.append((rid, z, "zone has no face in the region the island was merged into"))
        else:
            applied.append((rid, sorted({int(face_label[f]) for f in fs}), z))
            face_label[fs] = z
    return applied, refused


def ownership_minutes(ctx, own, iw0, nz):
    tot = np.zeros(nz)
    for i, it in enumerate(ctx["items"]):
        z = own["site_zone"][it["key"]] if it["kind"] == "site" else own["edge_rows"][it["key"]]["zone"]
        tot[z - 1] += iw0[i]
    return tot


def finalize(cfg, c16, ctx, face_label0, fm0, iw0, fz_ov, isl_ov, bridge_ov, nz, polygons):
    """Overrides -> ownership -> islands follow the owner of their bridge group -> ownership (-> polygons). Pure function."""
    face_label = face_label0.copy()
    reg, group, gof = ctx["reg"], ctx["group"], ctx["group_of_face"]
    for r in ctx["unzoned_regions"]:
        face_label[reg == r] = 0
    isl_a, isl_r = apply_island_overrides(isl_ov, face_label, ctx, nz)
    fz_a, fz_r = apply_face_overrides(fz_ov, face_label, ctx, nz)
    overridden = {int(r) for r in isl_ov["region_id"]}
    own = ownership(cfg, c16, ctx, face_label, bridge_ov)
    follow = []
    if cfg["island_follow_bridge"]:
        mlog = {m["region"]: m for m in ctx["merge_log"]}
        owner_of_gid = lambda o: {g["group_id"]: g["owner_zone"] for g in o["groups"]}
        for it in range(3):
            og = owner_of_gid(own)
            changed = False
            for r in sorted(mlog, reverse=True):
                if r in overridden or group.get(r) == r or r in ctx["unzoned_regions"]:
                    continue
                fs = np.flatnonzero(reg == r)
                gid = ctx["bridge_gid"].get(mlog[r]["bridge"])
                tgt = og.get(gid)
                cur = {int(face_label[f]) for f in fs}
                if tgt and cur != {tgt} and any(face_label[h] == tgt and gof[h] == group[r] and reg[h] != r for h in range(len(face_label))):
                    follow.append((r, sorted(cur), tgt))
                    face_label[fs] = tgt
                    changed = True
            if not changed:
                break
            own = ownership(cfg, c16, ctx, face_label, bridge_ov)
    res = dict(face_label=face_label, own=own, isl_applied=isl_a, isl_refused=isl_r, fz_applied=fz_a, fz_refused=fz_r, follow=follow)
    res["final_minutes"] = ownership_minutes(ctx, own, iw0, nz)
    res["face_minutes"] = zone_totals(face_label, fm0, nz)
    if polygons:
        res["polys"], res["poly_info"] = zone_polygons(cfg, ctx, face_label, own, nz)
    return res


def result_digest(res):
    h = hashlib.sha256()
    h.update(res["face_label"].tobytes())
    o = res["own"]
    h.update(json.dumps(sorted((k, v["zone"], v["seam"], v["other"]) for k, v in o["edge_rows"].items())).encode())
    h.update(json.dumps(sorted(o["site_zone"].items())).encode())
    h.update(json.dumps(sorted(o["cluster_zone"].items())).encode())
    return h.hexdigest()[:16]


def read_overrides(cfg):
    ov = cfg["paths"]["overrides"]
    fz = read_override(ov["face_zone"], ["face_id", "zone"])
    rz = read_override(ov["region_zones"], ["region_id", "k"])
    bo = read_override(ov["bridge_owner"], ["edge_id", "way_id", "zone"])
    isl = read_override(ov["island_zone"], ["region_id", "zone"])
    bmap = {}
    for r in bo.itertuples():
        if pd.notna(r.edge_id):
            bmap[("edge", int(r.edge_id))] = int(r.zone)
        elif pd.notna(r.way_id):
            bmap[("way", int(r.way_id))] = int(r.zone)
    return fz, rz, isl, bmap


def r5_test(cfg, c16, ctx, fin, face_label0, fm0, iw0, fz_ov, isl_ov, bridge_ov, nz):
    """Apply one face override and one island override on top of the current ones, rerun, remove them again."""
    gof, reg, group, nbr, nbr_ext = ctx["group_of_face"], ctx["reg"], ctx["group"], ctx["nbr"], ctx["nbr_ext"]
    fg = ctx["fg"]
    out = {}
    lab = face_label0
    test_face = None
    for f in sorted(np.flatnonzero(gof >= 0), key=lambda f: (-fg["area"].iloc[f], f)):
        if fg["area"].iloc[f] < 500 or fg["area"].iloc[f] > 20000 or reg[f] in [r for r in group if group[r] != r]:
            continue
        z = int(lab[f])
        tgt = sorted({int(lab[h]) for h in nbr[f] if lab[h] > 0 and lab[h] != z})
        rest = [h for h in np.flatnonzero(lab == z) if h != f]
        if tgt and rest and zone_connected(rest, None, nbr_ext):
            test_face = (int(f), z, tgt[0])
            break
    islands = sorted(r for r in group if group[r] != r and (reg == r).any())
    test_isl = None
    for r in islands:
        fs = np.flatnonzero(reg == r)
        cur = sorted({int(lab[f]) for f in fs})
        zs = sorted({int(lab[h]) for h in np.flatnonzero(gof == group[r]) if reg[h] != r})
        alt = [z for z in zs if z not in cur]
        if alt:
            test_isl = (r, cur, alt[0])
            break
    fzt = pd.concat([fz_ov, pd.DataFrame({"face_id": [test_face[0]], "zone": [test_face[2]]})]) if test_face else fz_ov
    islt = pd.concat([isl_ov, pd.DataFrame({"region_id": [test_isl[0]], "zone": [test_isl[2]]})]) if test_isl else isl_ov
    base = fin
    t1 = finalize(cfg, c16, ctx, face_label0, fm0, iw0, fz_ov, islt, bridge_ov, nz, False)
    t2 = finalize(cfg, c16, ctx, face_label0, fm0, iw0, fzt, islt, bridge_ov, nz, False)
    t2b = finalize(cfg, c16, ctx, face_label0, fm0, iw0, fzt, islt, bridge_ov, nz, False)
    b2 = finalize(cfg, c16, ctx, face_label0, fm0, iw0, fz_ov, isl_ov, bridge_ov, nz, False)
    out.update(test_face=test_face, test_island=test_isl, d_base=result_digest(base), d_island=result_digest(t1), d_both=result_digest(t2),
               d_both2=result_digest(t2b), d_base2=result_digest(b2), refused=(t2["fz_refused"], t2["isl_refused"]),
               applied=(t2["fz_applied"], t2["isl_applied"]), minutes_after=t2["final_minutes"])
    return out


def main(cfg_path):
    cfg = load_yaml(cfg_path)
    c16 = load_yaml(cfg["base_config"])
    cfg["crs_metric"] = c16["crs_metric"]
    cfg["paths"] = {**c16["paths"], **cfg["paths"]}
    setup_logging(cfg["paths"]["log"])
    log.info("task 03c start, config %s", cfg_path)
    d = v0.load_inputs(c16)
    edges, tram = v0.prepare_edges(c16, d)
    d["edges"], d["tram"] = edges, tram
    exp, nz = c16["expected"], c16["zones"]
    base = build_base(cfg, c16, d)
    CHECKS.extend(v0.CHECKS)
    keys = [dict(key=k_) for k_ in sorted(base["bridge_info"])]
    base["bridge_meta"] = bridge_names(c16, d, keys, base["item_by_key"])
    base["bridge_groups"], base["bridge_gid"], base["name_far"] = group_bridges(cfg, base, base["bridge_meta"])
    items = base["items"]
    iw = {name: item_weights(c16, scn, items) for name, scn in c16["scenarios"].items()}
    fz_ov, rz_ov, isl_ov, bridge_ov = read_overrides(cfg)
    kfix = {int(r.region_id): int(r.k) for r in rz_ov.itertuples()}

    def build(fg, nbr, n_raw, slivers, parent=None, reg_coarse=None):
        ctx = attach_faces(cfg, c16, base, fg, nbr, n_raw, slivers, parent)
        F = len(fg)
        fm, fu = {}, {}
        for name in iw:
            fm[name], fu[name] = face_values(ctx["uf"], ctx["item_index"], iw[name], base["units_of"], F)
        reg_in = None
        if reg_coarse is not None:   # subdivided faces inherit the region of their parent face (thin necks must not cut a region)
            assert (ctx["parent"] >= 0).all()
            reg_in = reg_coarse[ctx["parent"]]
        ctx = setup_regions(cfg, c16, ctx, fm["S0"], reg_in)
        ctx["unzoned_regions"] = sorted(r for o in ctx["orphan_rows"] for r in o["members"]
                                        if cfg["unzone_empty_orphans"] and fu["S0"][ctx["reg"] == r].sum() == 0 and fm["S0"][ctx["reg"] == r].sum() == 0)
        return ctx, fm, fu

    fg0, nbr0, n_raw0, sl0 = make_faces(cfg, base)
    ctx0, fm_c, fu_c = build(fg0, nbr0, n_raw0, sl0, np.arange(len(fg0)))
    split = split_heavy(cfg, c16, base, ctx0, fm_c["S0"]) if cfg["split_faces"] else None
    bad = [g for g in kfix if g not in ctx0["groups"]]
    if bad:
        raise SystemExit(f"region_zones.csv: unknown region_id {bad}; regions are {ctx0['groups']}")
    res_before = run_partition(cfg, c16, ctx0, fm_c["S0"], "S0", kfix, apply_stop=True)
    R = dict(cfg=cfg, c16=c16, base=base, ctx0=ctx0, fm_c=fm_c, res_before=res_before, kfix=kfix, nz=nz, fz_ov=fz_ov, isl_ov=isl_ov,
             bridge_ov=bridge_ov, split=None, iw=iw)
    if split is not None:
        fg, nbr, n_raw, slivers, parent, heavy = split
        ctx, fm, fu = build(fg, nbr, n_raw, slivers, parent, ctx0["reg"])
        R["split"] = dict(n_heavy=len(heavy), heavy=heavy, n_before=len(fg0), n_after=len(fg))
    else:
        ctx, fm, fu = ctx0, fm_c, fu_c
    F = len(ctx["fg"])
    conn = [dict(x) for x in ctx["nbr_ext"]]
    ufe = ctx["uf"][ctx["uf"]["unit_type"] != "site"]
    for g_ in ctx["bridge_groups"]:
        fs_ = sorted(set(ufe[ufe["key"].isin(g_["edges"])]["face_id"]))
        for a_ in fs_:
            for b_ in fs_:
                if a_ != b_:
                    conn[a_][b_] = conn[a_].get(b_, 0) + 1
    ctx["nbr_conn"] = conn
    check("sites", exp["sites"], sum(1 for it in items if it["kind"] == "site"))
    check("road edges in RING 1", exp["road_edges"], len(edges))
    check("tram-only ways in RING 1", exp["tram_segments"], len(tram))
    check("faces cover RING 1 area (m2 difference)", 0, round(abs(ctx["fg"].area.sum() - ctx["ring"].area), 3), abs(ctx["fg"].area.sum() - ctx["ring"].area) < 1.0)
    check("units attached to faces", exp["units"], round(float(fu["S0"].sum()), 6))
    check("S0 minutes attached to faces == item minutes", round(float(iw["S0"].sum()), 3), round(float(fm["S0"].sum()), 3))
    res = run_partition(cfg, c16, ctx, fm["S0"], "S0", kfix, apply_stop=True)
    R.update(ctx=ctx, fm=fm, fu=fu, res0=res)
    if res.get("stopped"):
        log.error("STOP: expected balance %.3f after the allocation %s", res["expected_balance"], res["k"])
        write_report(R, stopped=True)
        sys.exit(2)
    zone = res["zone"]
    centre = np.array(ctx["ring"].centroid.coords[0])
    lab = label_zones(ctx["fg"], zone, centre)
    face_label0 = np.where(zone >= 0, lab[np.maximum(zone, 0)], 0).astype(int)
    pre = res["zone_prepass"]
    face_label_pre = np.where(pre >= 0, lab[np.maximum(pre, 0)], 0).astype(int)
    fin = finalize(cfg, c16, ctx, face_label0, fm["S0"], iw["S0"], fz_ov, isl_ov, bridge_ov, nz, True)
    fin_pre = finalize(cfg, c16, ctx, face_label_pre, fm["S0"], iw["S0"], fz_ov, isl_ov, bridge_ov, nz, False)
    R.update(face_label0=face_label0, lab=lab, fin=fin, fin_pre=fin_pre)
    R["variants"] = variant_table(cfg, c16, ctx, face_label0, fm["S0"], iw["S0"], fz_ov, isl_ov, bridge_ov, nz)
    R["r5"] = r5_test(cfg, c16, ctx, fin, face_label0, fm["S0"], iw["S0"], fz_ov, isl_ov, bridge_ov, nz)
    sc = {"S0": fin["face_label"] - 1}
    sres = {"S0": res}
    for name in list(c16["scenarios"])[1:]:
        r = run_partition(cfg, c16, ctx, fm[name], name, dict(res["k"]), apply_stop=False)
        mp = match_labels(fin["face_label"], r["zone"], fm["S0"], nz)
        sc[name] = np.where(r["zone"] >= 0, mp[np.maximum(r["zone"], 0)], -1)
        sres[name] = r
    R["scen"], R["sres"] = sc, sres
    build_outputs(R)
    write_report(R, stopped=False)
    if any(c[3] == "FAIL" for c in CHECKS):
        log.error("some checks FAILED; see %s", cfg["paths"]["report"])


def island_rows(R):
    ctx, fin = R["ctx"], R["fin"]
    reg, group, fm, fu = ctx["reg"], ctx["group"], R["fm"]["S0"], R["fu"]["S0"]
    fg = ctx["fg"]
    mlog = {m["region"]: m for m in ctx["merge_log"]}
    orph = {o["region"]: o for o in ctx["orphan_rows"]}
    rows = []
    for r in sorted(group):
        if group[r] == r or not (reg == r).any():
            continue
        m = reg == r
        zc = Counter()
        for f in np.flatnonzero(m):
            zc[int(fin["face_label"][f])] += fm[f]
        z = sorted(zc, key=lambda k: (-zc[k], k))[0]
        mm = mlog.get(r)
        o = orph.get(r)
        rows.append(dict(region_id=int(r), merged_into=int(group[r]), direct_into=(mm["into"] if mm else (o["into"] if o else None)),
                         bridge=(mm["bridge"] if mm else None), bridge_tier=(mm["tier"] if mm else None), orphan=bool(o and not mm),
                         area=float(fg["area"][m].sum()), minutes=float(fm[m].sum()), units=float(fu[m].sum()), zone=z, n_zones=len(zc),
                         geometry=unary_union(fg.geometry.to_numpy()[m])))
    return rows


def build_outputs(R):
    cfg, c16, ctx, fin, nz = R["cfg"], R["c16"], R["ctx"], R["fin"], R["nz"]
    d, fg, items, uf, crs = ctx["d"], ctx["fg"], ctx["items"], ctx["uf"], cfg["crs_metric"]
    own, face_label = fin["own"], fin["face_label"]
    fm, fu = R["fm"]["S0"], R["fu"]["S0"]
    geoms = fg.geometry.to_numpy()
    gof, reg = ctx["group_of_face"], ctx["reg"]
    out = pathlib.Path(cfg["paths"]["output_gpkg"])
    out.parent.mkdir(parents=True, exist_ok=True)
    for suf in ("", "-wal", "-shm"):
        pathlib.Path(str(out) + suf).unlink(missing_ok=True)
    faces = gpd.GeoDataFrame({"face_id": fg["face_id"].to_numpy(), "parent_face": ctx["parent"], "region_id": gof, "region_orig": reg,
                              "zone": face_label, "minutes": fm.round(4), "area": fg["area"].round(2).to_numpy(),
                              "water": fg["water"].to_numpy()}, geometry=geoms, crs=crs)
    faces.to_file(out, layer="faces", driver="GPKG")
    pinfo = fin["poly_info"]
    zrows = []
    for z in range(1, nz + 1):
        u = fin["polys"][z]
        zrows.append(dict(zone=z, area_km2=u.area / 1e6, n_faces=int((face_label == z).sum()), n_parts=len(shapely.get_parts(u)), geometry=u))
    zones = gpd.GeoDataFrame(zrows, geometry="geometry", crs=crs)
    zones.to_file(out, layer="zones_v02", driver="GPKG", mode="a")
    rrows = []
    for g in ctx["groups"]:
        m = gof == g
        rrows.append(dict(region_id=g, orig_regions=",".join(str(int(r)) for r in sorted(set(reg[m]))), area_km2=float(fg["area"][m].sum() / 1e6),
                          minutes=float(fm[m].sum()), units=float(fu[m].sum()), k=R["res0"]["k"][g], geometry=unary_union(geoms[m])))
    gpd.GeoDataFrame(rrows, geometry="geometry", crs=crs).to_file(out, layer="regions", driver="GPKG", mode="a")
    isl = island_rows(R)
    R["islands"] = isl
    if isl:
        gdf = gpd.GeoDataFrame(isl, geometry="geometry", crs=crs)
        for c in ("direct_into", "bridge"):
            gdf[c] = gdf[c].astype("Int64")
        gdf.to_file(out, layer="islands", driver="GPKG", mode="a")
    else:
        gpd.GeoDataFrame({"region_id": [], "geometry": []}, geometry="geometry", crs=crs).to_file(out, layer="islands", driver="GPKG", mode="a")
    dp = pinfo["exceptions"]
    dpg = gpd.GeoDataFrame({"zone": [e["zone"] for e in dp], "kind": [e["kind"] for e in dp], "area_m2": [round(e["area"], 1) for e in dp],
                            "island_id": [e["ref"] if e["kind"] == "island_land" else None for e in dp],
                            "group_id": [e["ref"] if e["kind"] == "bridge_strip" else None for e in dp],
                            "touching_zones": [";".join(str(t) for t in e["touches"]) for e in dp]},
                           geometry=[e["geometry"] for e in dp], crs=crs)
    dpg["island_id"] = dpg["island_id"].astype("Int64")
    dpg["group_id"] = dpg["group_id"].astype("Int64")
    dpg.to_file(out, layer="detached_pieces", driver="GPKG", mode="a")
    wb = gpd.GeoDataFrame({"part": range(len(shapely.get_parts(ctx["barrier"])))}, geometry=list(shapely.get_parts(ctx["barrier"])), crs=crs)
    wb.to_file(out, layer="water_barrier", driver="GPKG", mode="a")
    erows = []
    for key in sorted(own["edge_rows"], key=lambda k: (k < 0, abs(k))):
        r = own["edge_rows"][key]
        erows.append(dict(edge_id=key, zone=r["zone"], seam=r["seam"], read_buffer_zone=(r["other"] or None), bridge=r["bridge"],
                          bridge_group=r["group"], site_id=own["in_site"].get(key), geometry=ctx["geo"][key]))
    eg = gpd.GeoDataFrame(erows, geometry="geometry", crs=crs)
    for c in ("read_buffer_zone", "bridge_group", "site_id"):
        eg[c] = eg[c].astype("Int64")
    eg.to_file(out, layer="edges_zone", driver="GPKG", mode="a")
    eg[eg["seam"]].to_file(out, layer="seam_edges", driver="GPKG", mode="a")
    brg = gpd.GeoDataFrame([dict(edge_id=k, way_id=ctx["bridge_meta"][k][0], name=ctx["bridge_meta"][k][1], tier=ctx["item_by_key"][k]["tier"],
                                 group_id=ctx["bridge_gid"][k], owner_zone=own["edge_rows"][k]["zone"], other_zone=own["edge_rows"][k]["other"] or None,
                                 geometry=ctx["geo"][k]) for k in sorted(ctx["bridge_info"])], geometry="geometry", crs=crs)
    brg["other_zone"] = brg["other_zone"].astype("Int64")
    brg.to_file(out, layer="bridges", driver="GPKG", mode="a")
    bg = gpd.GeoDataFrame([dict(group_id=g["group_id"], name=g["name"], edge_ids=";".join(str(k) for k in g["edges"]), owner_zone=g["owner_zone"],
                                other_zone=g["other_zone"], geometry=unary_union([ctx["geo"][k] for k in g["edges"]])) for g in own["groups"]],
                          geometry="geometry", crs=crs)
    bg["other_zone"] = bg["other_zone"].astype("Int64")
    bg.to_file(out, layer="bridge_groups", driver="GPKG", mode="a")
    vt = d["vt"]
    cz = gpd.GeoDataFrame({"cluster_id": vt["junction_cluster_id"].astype(int).to_numpy(),
                           "zone": [own["cluster_zone"][int(c)] for c in vt["junction_cluster_id"]],
                           "site_id": [ctx["cluster_site"].get(int(c)) for c in vt["junction_cluster_id"]]},
                          geometry=vt.geometry.to_numpy(), crs=crs)
    cz["site_id"] = cz["site_id"].astype("Int64")
    cz.to_file(out, layer="clusters_zone", driver="GPKG", mode="a")
    u2 = uf.copy()
    ii = np.array([ctx["item_index"][(t, k)] for t, k in zip(u2["unit_type"], u2["key"])])
    u2["minutes_s0"] = (u2["share"].to_numpy() * R["iw"]["S0"][ii]).round(4)
    u2["zone"] = face_label[u2["face_id"].to_numpy()]
    u2.to_csv(cfg["paths"]["output_unit_faces"], index=False)
    sc = pd.DataFrame({"face_id": fg["face_id"].to_numpy(), "parent_face": ctx["parent"], "region_id": gof, "minutes_s0": fm.round(4), "units": fu.round(4)})
    for name, z in R["scen"].items():
        sc[name.lower() + "_zone"] = np.where(z >= 0, z + 1, 0)
    for name in list(R["scen"])[1:]:
        sc["keep_" + name.lower()] = (sc[name.lower() + "_zone"] == sc["s0_zone"]) & (sc["s0_zone"] > 0)
    sc.to_csv(cfg["paths"]["output_scenarios"], index=False)
    R["zones_gdf"], R["edges_gdf"], R["faces_gdf"] = zones, eg, faces
    dig = []
    for lyr in ("faces", "zones_v02", "bridges", "bridge_groups", "islands", "detached_pieces", "seam_edges", "edges_zone", "clusters_zone", "regions", "water_barrier"):
        dig.append(f"{lyr} {layer_digest_one(out, lyr)}")
    for p in (cfg["paths"]["output_scenarios"], cfg["paths"]["output_unit_faces"], cfg["paths"]["water_table"]):
        dig.append(f"{pathlib.Path(p).name} {hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()}")
    pathlib.Path(cfg["paths"]["output_digest"]).write_text("\n".join(dig) + "\n")
    tables(R)


def seam_in_hull(cfg, ctx, seam_ids):
    """Seam edges that lie inside a site hull (covered >= hull_edge_cover, or both end clusters in one site); bridges excluded."""
    hkeys = list(ctx["hulls_eff"].keys())
    htree = shapely.STRtree([ctx["hulls_eff"][k] for k in hkeys])
    inside = []
    for k in seam_ids:
        g = ctx["geo"][k]
        ends = ctx["edge_ends"].get(k, [])
        both = len(ends) == 2 and ctx["cluster_site"].get(ends[0]) is not None and ctx["cluster_site"].get(ends[0]) == ctx["cluster_site"].get(ends[1])
        cov = max([g.intersection(ctx["hulls_eff"][hkeys[hi]]).length / g.length for hi in htree.query(g, predicate="intersects")] or [0.0]) if g.length else 0
        if (both or cov >= cfg["hull_edge_cover"]) and k not in ctx["bridge_info"]:
            inside.append(k)
    return inside


def variant_metrics(cfg, c16, ctx, fin, nz, fm0):
    own, fl = fin["own"], fin["face_label"]
    gof = ctx["group_of_face"]
    span = sum(1 for z in range(1, nz + 1) if len(set(gof[fl == z])) > 1)
    seam = [k for k, v in own["edge_rows"].items() if v["seam"]]
    pinfo = fin["poly_info"]
    fb = float(fin["face_minutes"].max() / fin["face_minutes"].mean())
    ob = float(fin["final_minutes"].max() / fin["final_minutes"].mean())
    return dict(detached=len(pinfo["exceptions"]), detached_zones=len({e["zone"] for e in pinfo["exceptions"]}), r1=span,
                r2_seam_hull=len(seam_in_hull(cfg, ctx, seam)), r2_border=len(pinfo["hull_through"]), face_bal=fb, final_bal=ob,
                owners={g["group_id"]: g["owner_zone"] for g in own["groups"]}, refused=len(own["bridge_refused"]))


def variant_table(cfg, c16, ctx, face_label0, fm0, iw0, fz_ov, isl_ov, bridge_ov, nz):
    """Each configured bridge-owner variant is applied on top of the override files and evaluated."""
    name_gid = {g["name"]: g for g in ctx["bridge_groups"] if g["name"]}
    rows = []
    for vname, spec in [("current override files", {})] + list(cfg["bridge_owner_variants"].items()):
        ov = dict(bridge_ov)
        for gname, zone in spec.items():
            g = name_gid[gname]
            ov[("edge", g["edges"][0])] = int(zone)
        fin = finalize(cfg, c16, ctx, face_label0, fm0, iw0, fz_ov, isl_ov, ov, nz, True)
        m = variant_metrics(cfg, c16, ctx, fin, nz, fm0)
        m["name"], m["spec"] = vname, spec
        rows.append(m)
    return rows


def tables(R):
    cfg, c16, ctx, fin, nz = R["cfg"], R["c16"], R["ctx"], R["fin"], R["nz"]
    own, face_label, d, items = fin["own"], fin["face_label"], ctx["d"], ctx["items"]
    zones, fm = R["zones_gdf"], R["fm"]["S0"]
    S0 = c16["scenarios"]["S0"]
    st = pd.DataFrame([dict(site_id=it["key"], n_units=it["n_units"], comp=it["comp"], zone=own["site_zone"][it["key"]],
                            minutes=v0.item_weight(c16, S0, it)) for it in items if it["kind"] == "site"])
    sc_ = c16["site_size_classes"]
    st["size"] = np.where(st["n_units"] <= sc_["small_max"], "small", np.where(st["n_units"] <= sc_["medium_max"], "medium", "large"))
    st["signal"] = st["comp"].str.contains("signal")
    st["tram"] = st["comp"].str.contains("tram")
    seg = pd.DataFrame([dict(edge_id=it["key"], tram=it["kind"] == "tram", tier=it["tier"], promoted=it.get("promoted", False), length=it["length"],
                             minutes=v0.item_weight(c16, S0, it), zone=own["edge_rows"][it["key"]]["zone"], seam=own["edge_rows"][it["key"]]["seam"])
                        for it in items if it["kind"] != "site"])
    seg["stratum"] = np.where(seg["tram"], "tram_segment", "edge_" + seg["tier"])
    if c16["b_service_promoted"]:
        seg.loc[(seg["stratum"] == "edge_B") & seg["promoted"], "stratum"] = "edge_B_service"
        seg.loc[seg["stratum"] == "edge_B", "stratum"] = "edge_B_core"
    kb = d["kbr"]
    r1 = kb[kb["Kordon"] == c16["kbr_ring"]].reset_index(drop=True)
    r1z = []
    for p in r1.geometry:
        hit = [int(z) for z, g in zip(zones["zone"], zones.geometry) if g.covers(p)]
        if not hit:
            hit = [int(zones["zone"].iloc[int(np.argmin([g.distance(p) for g in zones.geometry]))])]
        r1z.append(hit[0])
    r1c = Counter(r1z)
    rows = []
    for z in range(1, nz + 1):
        sz, sg = st[st["zone"] == z], seg[seg["zone"] == z]
        roads = sg[~sg["tram"]]
        rows.append(dict(zone=z, units=int(sz["n_units"].sum() + len(sg)), sites=len(sz), small=int((sz["size"] == "small").sum()),
                         medium=int((sz["size"] == "medium").sum()), large=int((sz["size"] == "large").sum()), signal=int(sz["signal"].sum()),
                         tram_site=int(sz["tram"].sum()), kmA=roads.loc[roads["tier"] == "A", "length"].sum() / 1000,
                         kmB=roads.loc[roads["tier"] == "B", "length"].sum() / 1000, kmC=roads.loc[roads["tier"] == "C", "length"].sum() / 1000,
                         tram_km=sg.loc[sg["tram"], "length"].sum() / 1000, nA=int((sg["stratum"] == "edge_A").sum()),
                         nBc=int((sg["stratum"] == "edge_B_core").sum()), nBs=int((sg["stratum"] == "edge_B_service").sum()),
                         nC=int((sg["stratum"] == "edge_C").sum()), ntram=int(sg["tram"].sum()),
                         minutes=float(sz["minutes"].sum() + sg["minutes"].sum()), face_minutes=float(fm[face_label == z].sum()),
                         area=float(zones.loc[zones["zone"] == z, "area_km2"].iloc[0]), r1=int(r1c.get(z, 0))))
    comp = pd.DataFrame(rows)
    R["comp"], R["st"], R["seg"] = comp, st, seg
    # v0 comparison (compactness and keep shares)
    v0z = gpd.read_file(cfg["paths"]["v0_gpkg"], layer="zones_v0").to_crs(cfg["crs_metric"])
    cz2 = {int(r.zone): compactness(r.geometry) for r in zones.itertuples()}
    cz0 = {int(r.zone): compactness(r.geometry) for r in v0z.itertuples()}
    ed0 = gpd.read_file(cfg["paths"]["v0_gpkg"], layer="edges_zone")
    z0 = dict(zip(ed0["edge_id"].astype(int), ed0["zone"].astype(int)))
    segm = seg.copy()
    segm["z0"] = segm["edge_id"].map(z0)
    cl0 = gpd.read_file(cfg["paths"]["v0_gpkg"], layer="clusters_zone").to_crs(cfg["crs_metric"])
    from scipy.spatial import cKDTree
    ktree = cKDTree(np.column_stack([cl0.geometry.x, cl0.geometry.y]))
    cl0z = cl0["zone"].astype(int).to_numpy()
    cid2v = {int(c): i for i, c in enumerate(cl0["cluster_id"])}
    sz0 = []
    for it in items:
        if it["kind"] != "site":
            continue
        cl = ctx["sv_ids"].get(it["key"], [])
        sz0.append(cl0z[cid2v[cl[0]]] if cl else cl0z[int(ktree.query([it["x"], it["y"]])[1])])
    st["z0"] = sz0
    ov = np.zeros((nz, nz))
    np.add.at(ov, (segm["z0"].to_numpy() - 1, segm["zone"].to_numpy() - 1), segm["minutes"].to_numpy())
    np.add.at(ov, (st["z0"].to_numpy() - 1, st["zone"].to_numpy() - 1), st["minutes"].to_numpy())
    r_, c_ = linear_sum_assignment(-ov)
    m0 = dict(zip(r_ + 1, c_ + 1))
    inv0 = {b: a for a, b in m0.items()}
    un_all = np.zeros((nz, nz))
    np.add.at(un_all, (segm["z0"].to_numpy() - 1, segm["zone"].to_numpy() - 1), 1.0)
    np.add.at(un_all, (st["z0"].to_numpy() - 1, st["zone"].to_numpy() - 1), st["n_units"].to_numpy())
    R["v0_cmp"] = (ov[r_, c_].sum() / ov.sum(), sum(un_all[a - 1, b - 1] for a, b in m0.items()) / un_all.sum())
    R["compact"] = [(z, cz2[z], cz0[inv0[z]], inv0[z]) for z in range(1, nz + 1)]
    sm = seg[seg["seam"]].copy()
    sm["other"] = [own["edge_rows"][k]["other"] for k in sm["edge_id"]]
    sm["pair"] = [(min(a, b), max(a, b)) for a, b in zip(sm["zone"], sm["other"])]
    R["seam_pairs"] = sm.groupby("pair").agg(n=("edge_id", "size"), km=("length", lambda x: x.sum() / 1000)).reset_index().sort_values("pair")
    R["seam_in_hull"] = seam_in_hull(cfg, ctx, sm["edge_id"].tolist())
    inside = R["seam_in_hull"]
    gof, reg = ctx["group_of_face"], ctx["reg"]
    span_g, span_r = [], []
    for z in range(1, nz + 1):
        m = face_label == z
        gs, rs = sorted(set(gof[m])), sorted(set(reg[m]))
        if len(gs) > 1:
            span_g.append((z, gs))
        if len(rs) > 1:
            span_r.append((z, [int(r) for r in rs]))
    R["span_g"], R["span_r"] = span_g, span_r
    disc = [z for z in range(1, nz + 1) if not zone_connected([f for f in range(len(face_label)) if face_label[f] == z], None, ctx["nbr_conn"])]
    split_sites = sum(1 for sid, cl in ctx["sv_ids"].items() if len({own["cluster_zone"][c] for c in cl}) > 1)
    final_bal = float(comp["minutes"].max() / comp["minutes"].mean())
    face_bal = float(comp["face_minutes"].max() / comp["face_minutes"].mean())
    R["final_bal"], R["face_bal"] = final_bal, face_bal
    pinfo = fin["poly_info"]
    dm = [k for k, v in ctx["bridge_meta"].items() if "Dmowskiego" in v[1]]
    dm_owners = sorted({own["edge_rows"][k]["zone"] for k in dm})
    grp_split = sum(1 for g in own["groups"] if len({own["edge_rows"][k]["zone"] for k in g["edges"]}) > 1)
    R["dm"] = (dm, dm_owners)
    check("R1 zones with land faces in both large regions", 0, len(span_g))
    check("R2 sites split between zones", 0, split_sites)
    check("R2 seam edges inside a site hull", 0, len(inside))
    check(f"R2 zone-polygon borders entering a site hull shrunk by {cfg['hull_border_tol_m']} m", 0, len(pinfo["hull_through"]))
    check("R2/R3 zones not connected (faces)", 0, len(disc))
    check("R3 zone polygons in one piece (zones with extra parts: islands and bridge strips of other zones, listed)", 0, len({e["zone"] for e in pinfo["exceptions"]}))
    check("R3 zone polygons: detached pieces that are neither island land nor bridge strip", 0, sum(1 for e in pinfo["exceptions"] if e["kind"] == "other"))
    check("units sum to total", c16["expected"]["units"], int(comp["units"].sum()))
    check(f"R4 balance max/mean on face minutes <= {cfg['balance_face_max']}", f"<= {cfg['balance_face_max']}", f"{face_bal:.3f}", face_bal <= cfg["balance_face_max"])
    check(f"R4 balance max/mean on S0 minutes after ownership <= {cfg['balance_final_max']}", f"<= {cfg['balance_final_max']}", f"{final_bal:.3f}", final_bal <= cfg["balance_final_max"])
    check("bridge groups with more than one owner", 0, grp_split)
    check("Dmowskiego bridge edges have one owner", 1, len(dm_owners), len(dm_owners) == 1 and len(dm) > 0)
    check("R5 face / island / bridge overrides refused", 0, len(fin["fz_refused"]) + len(fin["isl_refused"]) + len(fin["own"]["bridge_refused"]))
    r5 = R["r5"]
    ok5 = r5["test_face"] is not None and r5["test_island"] is not None and r5["d_both"] != r5["d_base"] and r5["d_both"] == r5["d_both2"] and r5["d_base2"] == r5["d_base"]
    check("R5 override test (changes result, rerun identical, removal restores baseline)", "yes", "yes" if ok5 else "no", ok5)
    check("all 11 zones non-empty", nz, int((comp["units"] > 0).sum()))
    check("R1 counters assigned to zones", c16["kbr_expected"], int(comp["r1"].sum()))
    stab = []
    tot_m, tot_u = fm.sum(), R["fu"]["S0"].sum()
    for name, z in R["scen"].items():
        wmin = R["fm"][name]
        tz = np.bincount(z[z >= 0], weights=wmin[z >= 0], minlength=nz)
        tz0 = np.bincount(z[z >= 0], weights=fm[z >= 0], minlength=nz)
        keep = (z == R["scen"]["S0"]) & (z >= 0)
        k = R["sres"][name]["k"]
        stab.append((name, f"{tz.max() / tz.mean():.3f}", f"{tz0.max() / tz0.mean():.3f}", "/".join(str(k[g]) for g in sorted(k)),
                     f"{fm[keep].sum() / tot_m:.1%}", f"{R['fu']['S0'][keep].sum() / tot_u:.1%}"))
    R["stab"] = stab


def own_group_balance(R, minutes):
    ctx, fl = R["ctx"], R["fin"]["face_label"]
    zg = {}
    for f in range(len(fl)):
        if fl[f] > 0:
            zg[int(fl[f]) - 1] = int(ctx["group_of_face"][f])
    out = {}
    for g in sorted(set(zg.values())):
        zs = [z for z in zg if zg[z] == g]
        v = minutes[zs]
        out[g] = (float(v.max() / v.mean()), float(v.min() / v.mean()), len(zs), float(v.mean()))
    return out


def fmt_gb(gb):
    return "; ".join(f"region {g}: max {v[0]:.3f} / min {v[1]:.3f} ({v[2]} zones, mean {v[3]:.0f})" for g, v in gb.items())


def write_report(R, stopped):
    cfg, c16, ctx = R["cfg"], R["c16"], R["ctx"]
    nz, fm, fu, res0 = R["nz"], R["fm"]["S0"], R["fu"]["S0"], R["res0"]
    fg, reg, gof = ctx["fg"], ctx["reg"], ctx["group_of_face"]
    L = ["# Task 03c: barrier-aware, block-based partition of RING 1 (v0.2)", ""]
    if stopped:
        L.append(f"> **STOPPED after the zone allocation:** {dict(sorted(res0['k'].items()))} gives expected balance {res0['expected_balance']:.3f} "
                 f"(limit {cfg['allocation_stop_balance']}). Set `config/overrides/region_zones.csv` and rerun.\n")
    L.append("Analysis only. All numbers in `config/22_partition_blocks.yaml` are `[PROPOSED]`; work weights are the unmeasured S0 proxy of task 03a. "
             "Nothing here changes `scope.yaml`, the polygon, D2-D4, `tiers.yaml` or the v0 results. Decisions applied from the project owner: allocation 8 + 3 zones "
             "(`region_zones.csv`), R4 relaxed to 1.10 on face minutes and 1.12 on minutes after ownership, R1 = no zone has land faces of both large regions, "
             "bridge groups with one owner, edges inside site hulls follow the site, faces above 350 minutes subdivided.\n")
    L.append("## Checks\n")
    L.append(md_table(["Check", "Expected", "Actual", "Result"], CHECKS))
    # ---- 1 barriers
    L.append("\n## 1. Barriers (water features)\n")
    wt = ctx["wtab"]
    L.append(f"Source: frozen snapshot, `osmium tags-filter nwr/natural=water nwr/waterway=river,canal,riverbank nwr/water=river,canal`, extract bbox `{ctx['bbox']}` (RING 1 bbox + {cfg['water_bbox_buffer_m']} m, strategy smart), "
             f"`osmium export`. Full table ({len(wt)} features with non-zero length or area inside RING 1): `{cfg['paths']['water_table']}`. Island and ring ways pulled in by `osmium` as multipolygon members are not water features and are dropped.\n")
    L.append(f"`barriers.names` = {cfg['barriers']['names']}; `include_moat` = {cfg['barriers']['include_moat']}. A waterway line is a barrier when its name is in the list; a water polygon is a barrier when it contains at least "
             f"{cfg['barriers']['select_overlap_min_m']} m of such a line (the Odra polygons carry no name in OSM). Lines buffered by {cfg['barriers']['line_buffer_m']} m; barrier area clipped to RING 1: "
             f"**{ctx['barrier'].area / 1e4:.1f} ha** in {len(shapely.get_parts(ctx['barrier']))} polygon(s).\n")
    sel = wt[wt["selected_as_barrier"]]
    ar = sel[sel["type"] == "area"]
    L.append(md_table(["id", "tags", "area m2 in RING 1", "reason"], [(r.id, r.tags, f"{r.area_m2_inside:.0f}", r.selection_reason) for r in ar.itertuples()]))
    ln = sel[sel["type"] == "line"].groupby("name").agg(n=("id", "size"), m=("length_m_inside", "sum")).reset_index()
    L.append("\n" + md_table(["selected waterway name", "ways", "length in RING 1 (m)"], [(r.name, r.n, f"{r.m:.0f}") for r in ln.itertuples()]))
    ns = wt[~wt["selected_as_barrier"]]
    named = ns[ns["name"].notna()].groupby("name").agg(n=("id", "size"), area=("area_m2_inside", "sum"), length=("length_m_inside", "sum"), tags=("tags", "first")).reset_index()
    L.append("\nNamed water features inside RING 1 that are **not** barriers (for your review; add a name to `barriers.names` to include it):\n")
    L.append(md_table(["name", "features", "area m2", "length m", "example tags"],
                      [(r.name, r.n, f"{r.area:.0f}", f"{r.length:.0f}", r.tags) for r in named.sort_values(["area", "length"], ascending=False).itertuples()]))
    big = ns[(ns["type"] == "area") & ns["name"].isna()].head(6)
    L.append("\nLargest unnamed water polygons not selected: " + (", ".join(f"{r.id} ({r.area_m2_inside:.0f} m2, {r.tags})" for r in big.itertuples()) or "none") + ".\n")
    # ---- 2 blocks
    fs_ = face_stats(fg)
    L.append("\n## 2. Blocks (faces)\n")
    L.append(f"Coarse boundaries: road fragments of classes {cfg['boundary_classes']} (no tram, cycleway, path, service), minus the barrier area, plus the barrier outline and the RING 1 boundary; "
             f"noded with `unary_union`, polygonized, faces inside RING 1 kept; slivers < {cfg['sliver_m2']} m2 merged into the neighbour with the longest shared boundary.\n")
    sp = R["split"]
    c0 = face_stats(R["ctx0"]["fg"])
    if sp:
        L.append(f"Coarse faces: {c0['n']} ({c0['n_land']} land), land area p50 {c0['p50']:.0f} / p90 {c0['p90']:.0f} / max {c0['max']:.0f} m2. "
                 f"**{sp['n_heavy']} land faces** with more than {cfg['split_face_minutes']} S0 minutes were subdivided with {cfg['split_extra_classes']} added as boundaries "
                 f"(footway and pedestrian still excluded). New face count: **{fs_['n']}** ({fs_['n_land']} land, {fs_['n_water']} water); land area p50 {fs_['p50']:.0f} / p90 {fs_['p90']:.0f} / max {fs_['max']:.0f} m2. "
                 f"Heaviest face before the split {R['fm_c']['S0'].max():.0f} min, after {fm.max():.0f} min; faces still above the limit: {int((fm > cfg['split_face_minutes']).sum())}.\n")
        sub = [(f, int(ctx['parent'][f]), f"{fm[f]:.0f}") for f in range(len(fg)) if not fg['water'].iloc[f] and ctx['parent'][f] in set(R['split']['heavy']) ]
    else:
        L.append(f"{fs_['n']} faces ({fs_['n_land']} land, {fs_['n_water']} water); no face above {cfg['split_face_minutes']} minutes.\n")
    L.append("\nWithin-region balance (zone minutes against the mean of the zones of the same region, face level):\n")
    rb = group_balance(R["res_before"], R["fm_c"]["S0"], nz, R["ctx0"])
    ra = group_balance(res0, fm, nz, ctx)
    L.append(md_table(["stage", "per region (max / min against the region mean)"],
                      [("coarse faces (before the split), after pass", fmt_gb(rb)), ("subdivided faces, after pass", fmt_gb(ra))]))
    L.append("\nTen heaviest faces after the split:\n")
    top = sorted(np.flatnonzero(~fg["water"].to_numpy()), key=lambda f: (-fm[f], f))[: cfg["largest_faces"]]
    zl = R["fin"]["face_label"]
    L.append(md_table(["face", "parent face", "area m2", "S0 minutes", "units", "region", "zone"],
                      [(f, ctx["parent"][f], f"{fg['area'].iloc[f]:.0f}", f"{fm[f]:.0f}", f"{fu[f]:.0f}", gof[f], zl[f]) for f in top]))
    top2 = sorted(np.flatnonzero(~fg["water"].to_numpy()), key=lambda f: (-fg["area"].iloc[f], f))[: cfg["largest_faces"]]
    L.append("\nTen largest faces by area:\n")
    L.append(md_table(["face", "area m2", "S0 minutes", "units", "region", "zone"], [(f, f"{fg['area'].iloc[f]:.0f}", f"{fm[f]:.0f}", f"{fu[f]:.0f}", gof[f], zl[f]) for f in top2]))
    # ---- 3 regions
    L.append("\n## 3. Regions, islands and zone allocation\n")
    L.append(f"Region = land faces connected through shared boundaries (not through water), numbered by decreasing area. {len(set(reg[reg >= 0]))} regions; a region below "
             f"{cfg['min_region_share']} x mean zone minutes = {ctx['region_threshold']:.0f} minutes is merged into the region reached by its best bridge (tier A first, non-tram, longest overlap, lowest edge id). "
             "The two regions that remain are the two banks (large regions); merged regions are called islands.\n")
    rows = []
    for r in sorted(set(reg[reg >= 0])):
        m = reg == r
        nb = sum(1 for b in ctx["brs"] if r in b["regions"] and len(b["regions"]) > 1)
        rows.append((r, ctx["group"][int(r)], f"{fg['area'][m].sum() / 1e6:.3f}", f"{fu[m].sum():.1f}", f"{fm[m].sum():.1f}", nb))
    L.append(md_table(["region", "merged into", "area km2", "units", "S0 minutes", "bridges to other regions"], rows))
    L.append("\nAllocation of the 11 zones (largest remainder, k >= 1, overridden by `region_zones.csv`):\n")
    rows = [(g, f"{res0['gmin'][g]:.0f}", f"{res0['gmin'][g] / sum(res0['gmin'].values()) * nz:.3f}", res0["k"][g], f"{res0['gmin'][g] / res0['k'][g]:.0f}", "override" if g in R["kfix"] else "")
            for g in ctx["groups"]]
    L.append(md_table(["region", "S0 minutes", "quota", "zones k", "minutes per zone", "source"], rows))
    L.append(f"\nMean zone minutes {fm.sum() / nz:.0f}; expected balance after allocation (lower bound): **{res0['expected_balance']:.3f}**.\n")
    # ---- 4 partition
    L.append("\n## 4. Partition\n")
    L.append(f"Per region `pymetis.part_graph` on the face adjacency graph (vertex weight = face minutes x {cfg['weight_scale']}, edge weight = shared boundary in metres, contiguity on, seed {c16['seed']}), best of ufactor {cfg['metis_ufactor_try']} by imbalance. "
             f"Synthetic links of weight {cfg['bridge_link_weight']} join an island to its bank over the bridge used for the merge. Tongue smoothing: up to {cfg['smooth_iter']} passes, a face moves to the zone that touches more than {cfg['smooth_share']:.0%} "
             f"of its perimeter if the face balance stays within {cfg['balance_face_max']} and the old zone stays connected. Balance pass (`balance_pass: {str(cfg['balance_pass']).lower()}`): faces move from the heaviest zone of a region to a neighbour touching at least "
             f"{cfg['balance_min_touch']:.0%} of the face perimeter while the pair maximum drops.\n")
    rows = [(g, i["k"], i["repair_moves"], "-" if i["best"] is None else f"{i['best'][0]:.3f} (ufactor {i['best'][1]})") for g, i in sorted(res0["metis"].items())]
    L.append(md_table(["region", "zones", "repair moves", "METIS imbalance inside the region"], rows))
    fin, fpre = R["fin"], R["fin_pre"]
    mean_all = fm.sum() / nz
    fb_pre = float(fpre["face_minutes"].max() / mean_all)
    ob_pre = float(fpre["final_minutes"].max() / (fpre["final_minutes"].sum() / nz))
    ob_post = float(fin["final_minutes"].max() / (fin["final_minutes"].sum() / nz))
    L.append("\nBalance max/mean before and after the balance pass:\n")
    L.append(md_table(["stage", "face minutes", "S0 minutes after ownership"],
                      [("after METIS and tongue smoothing (before the pass)", f"{res0['post_smooth_balance']:.3f}", f"{ob_pre:.3f}"),
                       (f"after the balance pass ({len(res0['balance_moves'])} moves) and a second smoothing ({len(res0['smooth2_moves'])} moves)", f"{res0['balance']:.3f}", f"{ob_post:.3f}")]))
    L.append(f"\nWithin-region balance after the pass, face minutes: {fmt_gb(group_balance(res0, fm, nz, ctx))}. After ownership: "
             f"{fmt_gb(own_group_balance(R, fin['final_minutes']))}. Lightest zone {fin['final_minutes'].min() / (fin['final_minutes'].sum() / nz):.3f} x mean. "
             f"Tongue smoothing moves: {len(res0['smooth_moves'])}.\n")
    L.append("\n### Overrides\n")
    L.append(f"`face_zone.csv`: {len(R['fz_ov'])} rows, applied {len(fin['fz_applied'])}, refused {len(fin['fz_refused'])}; `island_zone.csv`: {len(R['isl_ov'])} rows, applied {len(fin['isl_applied'])}, refused {len(fin['isl_refused'])}; "
             f"`region_zones.csv`: {len(R['kfix'])} rows; `bridge_owner.csv`: {len(R['bridge_ov'])} rows, refused {len(fin['own']['bridge_refused'])}.\n")
    for f, a, b in fin["fz_applied"]:
        L.append(f"- face {f}: zone {a} -> {b}")
    for r, a, b in fin["isl_applied"]:
        L.append(f"- island region {r}: zone {a} -> {b}")
    for f, z, why in fin["fz_refused"]:
        L.append(f"- REFUSED face {f} -> zone {z}: {why}")
    for r, z, why in fin["isl_refused"]:
        L.append(f"- REFUSED island {r} -> zone {z}: {why}")
    r5 = R["r5"]
    L.append("\n### R5 override test\n")
    L.append(f"Test face override: {r5['test_face']} (face, current zone, new zone); test island override: {r5['test_island']} (island, current zones, new zone). Result digests: baseline {r5['d_base']}, "
             f"with island override only {r5['d_island']}, with both {r5['d_both']}, both again {r5['d_both2']}, overrides removed again {r5['d_base2']}. "
             f"Applied in the test: faces {r5['applied'][0]}, islands {r5['applied'][1]}; refused: {r5['refused']}. The test overrides exist only in memory; the override files were not changed.\n")
    # ---- 5 composition
    comp = R["comp"]
    L.append("\n## 5. Composition of zones (after ownership)\n")
    rows = [(r.zone, r.units, f"{r.sites} ({r.small}/{r.medium}/{r.large})", r.signal, r.tram_site, f"{r.kmA:.1f}/{r.kmB:.1f}/{r.kmC:.1f}", f"{r.tram_km:.1f}",
             f"{r.nA}/{r.nBc}/{r.nBs}/{r.nC}", r.ntram, f"{r.minutes:.0f}", f"{r.face_minutes:.0f}", f"{r.area:.2f}", r.r1) for r in comp.itertuples()]
    t = comp
    rows.append(("**all**", int(t.units.sum()), f"{int(t.sites.sum())} ({int(t.small.sum())}/{int(t.medium.sum())}/{int(t.large.sum())})", int(t.signal.sum()), int(t.tram_site.sum()),
                 f"{t.kmA.sum():.1f}/{t.kmB.sum():.1f}/{t.kmC.sum():.1f}", f"{t.tram_km.sum():.1f}", f"{t.nA.sum()}/{t.nBc.sum()}/{t.nBs.sum()}/{t.nC.sum()}", int(t.ntram.sum()),
                 f"{t.minutes.sum():.0f}", f"{t.face_minutes.sum():.0f}", f"{t.area.sum():.2f}", int(t.r1.sum())))
    L.append(md_table(["zone", "units", "sites (small/medium/large)", "sites with signal", "sites with tram", "km road A/B/C", "tram km", "edges A/B-core/B-service/C", "tram ways",
                       "S0 minutes (ownership)", "S0 minutes (faces)", "area km2 (polygon)", "R1 counters"], rows))
    L.append(f"\nBalance max/mean: **{R['final_bal']:.3f}** on the minutes after ownership (target {cfg['balance_final_max']}), **{R['face_bal']:.3f}** on the face minutes (target {cfg['balance_face_max']}).\n")
    # ---- 6 compactness
    L.append("\n## 6. Compactness (area / convex hull area, perimeter / sqrt(area)); v0 zones matched by shared S0 minutes\n")
    rows, worse = [], []
    for z, (c2, p2), (c0_, p0), z0 in R["compact"]:
        w = c2 < c0_ - 1e-9 or p2 > p0 + 1e-9
        if w:
            worse.append(z)
        rows.append((z, f"{c2:.3f}", f"{c0_:.3f}", f"{p2:.2f}", f"{p0:.2f}", z0, "worse" if w else ""))
    R["worse"] = worse
    L.append(md_table(["zone v0.2", "area/hull v0.2", "area/hull v0", "perimeter/sqrt(area) v0.2", "perimeter/sqrt(area) v0", "matched v0 zone", "flag"], rows))
    # ---- 7 seam
    L.append("\n## 7. Seam edges per zone pair\n")
    spair = R["seam_pairs"]
    L.append(f"Seam edge = an edge whose faces belong to different zones, owner by the larger sum of `max_degree` of its end clusters in the zone (tie: lower zone id); edges inside a site hull and edges of bridge groups are handled by the hull and group rules. "
             f"Total: **{int(spair['n'].sum())} edges, {spair['km'].sum():.2f} km**.\n")
    L.append(md_table(["zone pair", "seam edges", "km"], [(fmt_pair(r.pair), r.n, f"{r.km:.2f}") for r in spair.itertuples()]))
    # ---- 8 bridges
    L.append("\n## 8. Bridge groups and owners\n")
    L.append(f"Bridge = an edge with more than {cfg['bridge_min_overlap_m']} m inside the barrier area (road and tram-only ways). Group = equal name, or over-water parts within {cfg['bridge_group_m']} m of each other. "
             "One owner per group: among the zones whose faces touch the group, the zone with the larger sum of `max_degree` of the distinct end clusters of the whole group in it (tie: more faces, then lower zone id); a zone without land at the bridge could not join its strip to its polygon. Strip = group buffered by "
             f"{cfg['bridge_strip_m']} m, clipped to the barrier area, added to the owner's polygon.\n")
    rows = []
    for g in fin["own"]["groups"]:
        tiers = "".join(sorted({ctx["item_by_key"][k]["tier"] for k in g["edges"]}))
        nroad = sum(1 for k in g["edges"] if k >= 0)
        rows.append((g["group_id"], g["name"] or "-", f"{nroad} road + {len(g['edges']) - nroad} tram", tiers, g["owner_zone"], g["other_zone"] or "-", dict(sorted(g["sums"].items()))))
    L.append(md_table(["group", "name", "edges", "tiers", "owner zone", "other zone", "max_degree sums"], rows))
    far = [(n, ks, f) for n, ks, f in ctx["name_far"] if f > cfg["bridge_group_m"]]
    if far:
        L.append("\nGroups joined by equal name whose members are more than the proximity distance apart (check): " + "; ".join(f"{n} ({len(ks)} edges, up to {f:.0f} m)" for n, ks, f in far) + ".\n")
    dm, dmo = R["dm"]
    L.append(f"\nDmowskiego bridge edges {dm}: owner zone(s) {dmo}.\n")
    # ---- 9 stability
    L.append("\n## 9. Stability (S0-S4) and comparison with v0\n")
    L.append("Same method and seed; no face, island or bridge overrides; region groups and number of zones per region fixed to the S0 allocation. Labels matched to S0 by Hungarian assignment on S0 minutes. Shares are measured on faces.\n")
    L.append(md_table(["scenario", "balance (own weights)", "balance (S0 weights)", "zones per region", "S0 minutes keeping zone", "units keeping zone"], R["stab"]))
    kmn, kun = R["v0_cmp"]
    L.append(f"\nv0.2 S0 against v0 S0 (labels matched, measured on units: edges, tram ways, sites): **{kmn:.1%}** of S0 minutes and **{kun:.1%}** of units keep the zone.\n")
    # ---- 10 review
    L.append("\n## 10. Places to review by hand\n")
    isl = R["islands"]
    L.append("### Merged islands\n")
    if isl:
        L.append(md_table(["island (region id)", "area m2", "S0 minutes", "units", "merged into region", "bridge edge (tier)", "zone joined", "zones touched"],
                          [(i["region_id"], f"{i['area']:.0f}", f"{i['minutes']:.1f}", f"{i['units']:.1f}", f"{i['direct_into']} -> {i['merged_into']}" if i["direct_into"] != i["merged_into"] else i["merged_into"],
                            (f"{i['bridge']} ({i['bridge_tier']})" if i["bridge"] is not None else "none: nearest region"), i["zone"], i["n_zones"]) for i in isl]))
        L.append("\nSet `config/overrides/island_zone.csv` (`region_id,zone`) to change the zone of an island.\n")
    L.append("\n### Bridge-owner variants (R3 cleanup)\n")
    L.append("Each variant is applied on top of the current `bridge_owner.csv` (groups identified by name, the override applies to the whole group) and evaluated with the same rules. "
             "Detached = pieces of zone polygons that are not connected to the main piece of their zone.\n")
    gnames = {g["group_id"]: (g["name"] or "-") for g in fin["own"]["groups"]}
    vrows = []
    for v in R["variants"]:
        vrows.append((v["name"], "; ".join(f"{k} -> {z}" for k, z in v["spec"].items()) or "-", f"{v['detached']} pieces in {v['detached_zones']} zones", v["r1"], f"{v['r2_seam_hull']} / {v['r2_border']}",
                      f"{v['face_bal']:.3f}", f"{v['final_bal']:.3f}", v["refused"]))
    L.append(md_table(["variant", "overrides", "R3 detached", "R1 zones in both banks", "R2 seam edges in hulls / borders in hulls", "balance faces", "balance after ownership", "refused"], vrows))
    L.append("\nOwner of every bridge group per variant:\n")
    L.append(md_table(["group", "name"] + [v["name"] for v in R["variants"]], [(gid, gnames[gid]) + tuple(v["owners"][gid] for v in R["variants"]) for gid in sorted(gnames)]))
    L.append("\n### Zone polygons\n")
    pinfo = fin["poly_info"]
    L.append(f"Slivers < {cfg['sliver_polygon_m2']} m2 merged into the neighbour with the longest shared border: {len(pinfo['merged_slivers'])} (total {sum(a for _, _, a in pinfo['merged_slivers']):.0f} m2); dropped: {len(pinfo['dropped'])}. "
             f"Lobes of ordinary land cut off by the hull of another zone's site and merged into the neighbour with the longest border: {len(pinfo['lobes'])}"
             + ("; " + "; ".join(f"{a:.0f} m2 from zone {z} to zone {y}" for z, y, a in pinfo["lobes"]) if pinfo["lobes"] else "")
             + f". Detached pieces left (island land or bridge strip whose owner has no land next to it): {len(pinfo['exceptions'])}"
             + (" (table below)" if pinfo["exceptions"] else "") + ".\n")
    if pinfo["exceptions"]:
        L.append(md_table(["zone", "kind", "area m2", "island / bridge group", "zones whose polygon touches the piece", "near (x, y)"],
                          [(e["zone"], e["kind"], f"{e['area']:.0f}", (f"island {e['ref']}" if e["kind"] == "island_land" else f"group {e['ref']}"),
                            e["touches"] or "-", e["where"]) for e in pinfo["exceptions"]]) + "\n")
    L.append(f"Zone borders entering a site hull shrunk by {cfg['hull_border_tol_m']} m (the check asks for hull buffered by 3 m; a border running along the hull outline necessarily lies in the buffered hull, so the inner tolerance is used): "
             f"{len(pinfo['hull_through'])}" + ("; " + "; ".join(f"site {s} (zone {z}, {l:.0f} m)" for s, z, l in pinfo["hull_through"]) if pinfo["hull_through"] else "") + ".\n")
    L.append(f"Sites whose hull overlaps faces of more than one zone (whole site goes to the zone with most hull area, hull added to that zone's polygon): {len(fin['own']['site_split'])} of {len(R['st'])}. "
             f"Edges placed by the hull rule: {len(fin['own']['in_site'])}. Seam edges inside a hull: {len(R['seam_in_hull'])}.\n")
    L.append(f"Zones with compactness worse than v0: {R['worse'] or 'none'} (flag column in section 6).\n")
    L.append("\nRobust cores are not computed in this task.\n")
    pathlib.Path(cfg["paths"]["report"]).write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config/22_partition_blocks.yaml")
