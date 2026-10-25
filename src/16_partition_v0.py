"""Task 03a: provisional partition of RING 1 into 11 zones (v0), stability scenarios, robust cores.

Analysis only. Usage: uv run python src/16_partition_v0.py [config/16_partition.yaml]
"""
import hashlib
import logging
import math
import pathlib
import sys
from collections import Counter, defaultdict

import geopandas as gpd
import numpy as np
import pandas as pd
import pymetis
import shapely
import yaml
from scipy.optimize import linear_sum_assignment
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, dijkstra
from scipy.spatial import cKDTree

log = logging.getLogger("partition")


def load_yaml(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def setup_logging(path):
    pathlib.Path(path).parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(path, mode="a"), logging.StreamHandler()],
    )


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


CHECKS = []


def check(name, expected, actual, ok=None):
    ok = (expected == actual) if ok is None else ok
    CHECKS.append((name, expected, actual, "PASS" if ok else "FAIL"))
    if not ok:
        log.error("CHECK FAILED: %s expected=%s actual=%s", name, expected, actual)
    return ok


def km(m):
    return f"{m / 1000:.2f}"


# ---------------------------------------------------------------- loading

def load_inputs(cfg):
    p = cfg["paths"]
    crs = cfg["crs_metric"]
    mem = gpd.read_file(p["membership"], layer="junction_clusters_m").to_crs(crs)
    vt = mem[mem["centroid_in"]].sort_values("junction_cluster_id").reset_index(drop=True)
    edges = gpd.read_file(p["ownership"], layer="edges").to_crs(crs)
    edges = edges[edges["ring1"]].sort_values("edge_id").reset_index(drop=True)
    tram = gpd.read_file(p["ownership"], layer="tram_segments").to_crs(crs)
    tram = tram[tram["ring1"]].sort_values("edge_id", ascending=False).reset_index(drop=True)
    sites = gpd.read_file(p["sites"], layer="sites").to_crs(crs).sort_values("site_id").reset_index(drop=True)
    units = pd.read_csv(p["units"])
    feat = p["features"]
    jn = gpd.read_file(feat, layer="junction_nodes")
    sn = gpd.read_file(feat, layer="signal_nodes")
    kbr = gpd.read_file(feat, layer="kbr_points").to_crs(crs)
    poly = gpd.read_file(p["polygons"], layer=p["polygon_layer"]).to_crs(crs)
    return dict(vt=vt, edges=edges, tram=tram, sites=sites, units=units, jn=jn, sn=sn, kbr=kbr, poly=poly)


def prepare_edges(cfg, d):
    """Attach tier_tag from the work-unit table (the agreed source) to edges and tram segments."""
    seg = d["units"][d["units"]["unit_type"] == "segment"].set_index("id")
    e, t = d["edges"], d["tram"]
    e["tier_tag_u"] = e["edge_id"].map(seg["tier_tag"])
    t["tier_tag_u"] = t["edge_id"].map(seg["tier_tag"])
    check("segment units found for all RING 1 edges + tram ways", len(e) + len(t),
          int(e["tier_tag_u"].notna().sum() + t["tier_tag_u"].notna().sum()))
    check("tier_tag in units == tier_tag in ownership layer (edges)", 0, int((e["tier_tag"] != e["tier_tag_u"]).sum()))
    e["tier_tag"] = e["tier_tag_u"]
    t["tier_tag"] = t["tier_tag_u"]
    return e, t


# ---------------------------------------------------------------- graph

def build_vertex_graph(cfg, vt, edges):
    vid = {int(c): i for i, c in enumerate(vt["junction_cluster_id"])}
    xy = np.column_stack([vt.geometry.x, vt.geometry.y])
    thr = edges[edges["kind"] == "inside_through"]
    a = thr["cluster_a"].map(vid).to_numpy()
    b = thr["cluster_b"].map(vid).to_numpy()
    check("inside_through edges have both end clusters among the vertices", 0, int(np.isnan(a.astype(float)).sum() + np.isnan(b.astype(float)).sum()))
    a, b = a.astype(int), b.astype(int)
    loops = int((a == b).sum())
    loop_km = float(thr['length_m'].to_numpy()[a == b].sum()) / 1000
    keep = a != b
    pair = Counter(zip(np.minimum(a[keep], b[keep]).tolist(), np.maximum(a[keep], b[keep]).tolist()))
    return vid, xy, pair, (loops, loop_km)


def attach_components(cfg, xy, pair):
    n = len(xy)
    rows = np.array([p[0] for p in pair], dtype=int)
    cols = np.array([p[1] for p in pair], dtype=int)
    adj = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n))
    nc, lab = connected_components(adj, directed=False)
    sizes = np.bincount(lab)
    order = np.argsort(-sizes, kind="stable")
    big = order[0]
    info = {"n_components": nc, "sizes": sizes[order].tolist(), "bridges": []}
    big_idx = np.flatnonzero(lab == big)
    tree = cKDTree(xy[big_idx])
    bridges = {}
    for c in order[1:]:
        members = np.flatnonzero(lab == c)
        dist, j = tree.query(xy[members])
        k = int(np.argmin(dist))
        u, v = int(members[k]), int(big_idx[j[k]])
        bridges[(min(u, v), max(u, v))] = 1
        info["bridges"].append({"size": len(members), "vertex": u, "to": v, "dist_m": float(dist[k])})
    return bridges, info, lab


# ---------------------------------------------------------------- sites and weights

def parse_members(s):
    out = []
    for m in str(s).split(";"):
        t, i = m.rsplit(":", 1)
        out.append((t, int(i)))
    return out


def site_vertices(cfg, d, vid, xy):
    """Vertices (junction clusters with centroid_in) of every site; tram/crossing-only sites get none."""
    jn, sn, sites = d["jn"], d["sn"], d["sites"]
    node_cluster = dict(zip(jn["osm_id"].astype(int), jn["junction_cluster_id"].astype(int)))
    sig_nodes = defaultdict(list)
    for o, c, k in zip(sn["osm_id"].astype(int), sn["cluster_id"].astype(int), sn["kind"]):
        if k == "junction_signal":
            sig_nodes[c].append(o)
    sv, src = {}, {}
    for sid, mem in zip(sites["site_id"], sites["members"]):
        vs, how = set(), Counter()
        for t, i in parse_members(mem):
            if t == "junction_cluster_complex":
                cl = [i]
            elif t == "signal_cluster":
                cl = [node_cluster[o] for o in sig_nodes.get(i, []) if o in node_cluster]
            else:   # tram_crossing: an OSM node, a junction node only when it lies on a road junction
                cl = [node_cluster[i]] if i in node_cluster else []
            for c in cl:
                if c in vid:
                    vs.add(vid[c])
                    how[t] += 1
        sv[int(sid)] = sorted(vs)
        src[int(sid)] = how
    return sv


def contract(sv, n_vertices):
    """Union-find over vertices of the same site; sites sharing a vertex end up in one super-vertex."""
    parent = list(range(n_vertices))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    shared = 0
    for vs in sv.values():
        for v in vs[1:]:
            ra, rb = find(vs[0]), find(v)
            if ra != rb:
                parent[max(ra, rb)] = min(ra, rb)
    roots = np.array([find(v) for v in range(n_vertices)])
    uniq, sup = np.unique(roots, return_inverse=True)
    owner = defaultdict(set)
    for sid, vs in sv.items():
        for v in vs:
            owner[v].add(sid)
    shared = sum(1 for s in owner.values() if len(s) > 1)
    return sup, len(uniq), shared


def nearest_vertex(geoms, xy):
    tree = shapely.STRtree(shapely.points(xy))
    idx = tree.nearest(np.asarray(geoms))
    dist = shapely.distance(np.asarray(geoms), shapely.points(xy[idx]))
    return np.asarray(idx), np.asarray(dist)


def build_items(cfg, d, vid, xy, sv):
    """Weight items: each has a list of (vertex, share) and a distance used for the attachment report."""
    sites, edges, tram = d["sites"], d["edges"], d["tram"]
    items = []   # dicts: kind, key, n_units, length, tier, shares, dist, how
    # sites
    spt = shapely.points(np.column_stack([sites.geometry.x, sites.geometry.y]))
    need = [k for k, sid in enumerate(sites["site_id"]) if not sv[int(sid)]]
    near_v, near_d = nearest_vertex(spt[need], xy) if need else (np.array([], int), np.array([]))
    nn = dict(zip(need, zip(near_v.tolist(), near_d.tolist())))
    for k, (sid, nu, comp) in enumerate(zip(sites["site_id"], sites["n_units"], sites["composition"])):
        vs = sv[int(sid)]
        if vs:
            dist = float(shapely.distance(spt[k], shapely.points(xy[vs])).min())
            sh, how = [(vs[0], 1.0)], "own"
        else:
            v, dist = nn[k]
            sh, how = [(v, 1.0)], "nearest"
        items.append(dict(kind="site", key=int(sid), n_units=int(nu), comp=comp, shares=sh, dist=dist, how=how,
                          sv=vs, x=float(sites.geometry.x.iloc[k]), y=float(sites.geometry.y.iloc[k])))
    # road edges
    iso = [k for k, kd in enumerate(edges["kind"]) if kd == "isolated"]
    iv, idist = nearest_vertex(edges.geometry.to_numpy()[iso], xy) if iso else (np.array([], int), np.array([]))
    isod = dict(zip(iso, zip(iv.tolist(), idist.tolist())))
    for k, r in enumerate(edges.itertuples()):
        if r.kind == "inside_through":
            a, b = vid[int(r.cluster_a)], vid[int(r.cluster_b)]
            sh, how, dist = [(a, 0.5), (b, 0.5)], "ends", 0.0
        elif r.kind in ("dead_end_spur", "boundary_stub"):
            ends = [vid[int(c)] for c, f in ((r.cluster_a, r.end_a_in), (r.cluster_b, r.end_b_in)) if f and int(c) in vid]
            assert len(ends) == 1, (r.edge_id, r.kind, ends)
            sh, how, dist = [(ends[0], 1.0)], "end", 0.0
        else:
            v, dist = isod[k]
            sh, how = [(v, 1.0)], "nearest"
        items.append(dict(kind="edge", key=int(r.edge_id), tier=r.tier_tag, length=float(r.length_m), shares=sh,
                          dist=dist, how=how, ekind=r.kind, promoted=bool(r.tier_promoted)))
    # tram-only ways (all go to the nearest vertex, including 18 pieces that touch a junction cluster)
    tv, td = nearest_vertex(tram.geometry.to_numpy(), xy)
    for k, r in enumerate(tram.itertuples()):
        items.append(dict(kind="tram", key=int(r.edge_id), tier="A", length=float(r.length_m),
                          shares=[(int(tv[k]), 1.0)], dist=float(td[k]), how="nearest", has_end_cluster=int(r.cluster_a) >= 0))
    return items


def item_weight(cfg, scn, it):
    w = cfg["weights"]
    kind = scn["kind"]
    if it["kind"] == "site":
        if kind == "unit":
            return float(it["n_units"])
        if kind == "length":
            return scn["site_base"] + scn["site_per_unit"] * it["n_units"]
        return scn.get("site_mult", 1.0) * min(w["site_cap"], w["site_base"] + w["site_per_unit"] * it["n_units"])
    if kind == "unit":
        return 1.0
    if kind == "length":
        return it["length"]
    return float(w["tram_segment"] if it["kind"] == "tram" else w["edge_tier"][it["tier"]])


def vertex_weights(cfg, scn, items, n):
    wv = np.zeros(n)
    for it in items:
        w = item_weight(cfg, scn, it)
        for v, s in it["shares"]:
            wv[v] += w * s
    return wv


# ---------------------------------------------------------------- partitioning

def super_graph(pair, bridges, sup, m):
    agg = Counter()
    for (a, b), c in list(pair.items()) + list(bridges.items()):
        sa, sb = int(sup[a]), int(sup[b])
        if sa != sb:
            agg[(min(sa, sb), max(sa, sb))] += c
    nbr = [dict() for _ in range(m)]
    for (a, b), c in agg.items():
        nbr[a][b] = c
        nbr[b][a] = c
    return agg, nbr


def to_csr(nbr):
    xadj, adjncy, ew = [0], [], []
    for d in nbr:
        for j in sorted(d):
            adjncy.append(j)
            ew.append(int(d[j]))
        xadj.append(len(adjncy))
    return xadj, adjncy, ew


def zone_components(part, nbr):
    """Connected components of every zone inside the zone-induced subgraph: {zone: [list of vertex lists]}."""
    out = defaultdict(list)
    seen = np.zeros(len(part), bool)
    for s in range(len(part)):
        if seen[s]:
            continue
        stack, comp = [s], []
        seen[s] = True
        while stack:
            u = stack.pop()
            comp.append(u)
            for v in nbr[u]:
                if not seen[v] and part[v] == part[s]:
                    seen[v] = True
                    stack.append(v)
        out[int(part[s])].append(comp)
    return out


def repair(part, nbr, wv):
    """Move non-largest components of a disconnected zone to the neighbouring zone with the most shared edges."""
    moves = []
    while True:
        comps = zone_components(part, nbr)
        bad = [(z, cs) for z, cs in sorted(comps.items()) if len(cs) > 1]
        if not bad:
            return part, moves
        z, cs = bad[0]
        cs = sorted(cs, key=lambda c: (-len(c), min(c)))
        for c in cs[1:]:
            share = Counter()
            for u in c:
                for v, w in nbr[u].items():
                    if part[v] != z:
                        share[int(part[v])] += w
            if not share:
                raise RuntimeError("disconnected zone component without a neighbour")
            to = sorted(share.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
            moves.append({"from": z, "to": to, "vertices": len(c), "weight": float(wv[c].sum())})
            for u in c:
                part[u] = to


def run_metis(cfg, nbr, wv_int, nparts):
    xadj, adjncy, ew = to_csr(nbr)
    mc = cfg["metis"]
    last = None
    for uf in mc["ufactor_try"]:
        opt = pymetis.Options(seed=cfg["seed"], contig=1 if mc["contig"] else 0, ufactor=int(uf),
                              ncuts=mc["ncuts"], niter=mc["niter"], numbering=0)
        cut, part = pymetis.part_graph(nparts, xadj=xadj, adjncy=adjncy, vweights=wv_int, eweights=ew, options=opt)
        part = np.array(part)
        part, moves = repair(part, nbr, wv_int.astype(float))
        tot = np.bincount(part, weights=wv_int, minlength=nparts)
        bal = float(tot.max() / tot.mean())
        last = (part, moves, uf, bal)
        log.info("METIS ufactor=%s -> balance %.4f, repair moves %d", uf, bal, len(moves))
        if bal <= cfg["balance_max"] and not np.any(tot == 0):
            return last
    return last


def partition_scenario(cfg, name, scn, items, sup, m, n, agg, nbr):
    wv = vertex_weights(cfg, scn, items, n)
    wsup = np.bincount(sup, weights=wv, minlength=m)
    wint = np.maximum(1, np.rint(wsup * cfg["weight_scale"])).astype(int)
    part, moves, uf, bal = run_metis(cfg, nbr, wint, cfg["zones"])
    return dict(name=name, part=part, moves=moves, ufactor=uf, balance_try=bal, wsup=wsup, wv=wv)


def cut_stats(part, agg, pair_real_sup):
    cut_pairs = sum(1 for (a, b) in agg if part[a] != part[b])
    cut_edges = sum(c for (a, b), c in pair_real_sup.items() if part[a] != part[b])
    return cut_pairs, cut_edges


def hungarian_relabel(ref_part, part, w, k):
    ov = np.zeros((k, k))
    np.add.at(ov, (ref_part, part), w)
    r, c = linear_sum_assignment(-ov)
    mp = np.zeros(k, int)
    mp[c] = r
    return mp[part]


# ---------------------------------------------------------------- main analysis

def order_zones(part, wsup, sxy, centre, k):
    """Relabel zones 1..k clockwise from north around the RING 1 centroid (deterministic labels)."""
    ang = []
    for z in range(k):
        m = part == z
        cx, cy = np.average(sxy[m], axis=0, weights=wsup[m])
        ang.append(math.atan2(cx - centre[0], cy - centre[1]) % (2 * math.pi))
    rank = np.argsort(np.argsort(ang, kind="stable"), kind="stable")
    return rank[part]


def main(cfg_path):
    cfg = load_yaml(cfg_path)
    setup_logging(cfg["paths"]["log"])
    log.info("task 03a start, config %s", cfg_path)
    k = cfg["zones"]
    exp = cfg["expected"]
    d = load_inputs(cfg)
    edges, tram = prepare_edges(cfg, d)
    d["edges"], d["tram"] = edges, tram
    vt, units = d["vt"], d["units"]
    n = len(vt)
    check("vertices (junction clusters, centroid_in)", exp["vertices"], n)
    check("sites", exp["sites"], len(d["sites"]))
    check("units in sites", exp["site_units"], int(d["sites"]["n_units"].sum()))
    check("road edges in RING 1", exp["road_edges"], len(edges))
    check("tram-only ways in RING 1", exp["tram_segments"], len(tram))
    check("units = site units + edges + tram ways", exp["units"], int(d["sites"]["n_units"].sum()) + len(edges) + len(tram))
    check("work-unit table rows", exp["units"], len(units))
    kbr = d["kbr"]
    r1 = kbr[kbr["Kordon"] == cfg["kbr_ring"]]
    check("KBR R1 counters", cfg["kbr_expected"], len(r1))

    # 1. graph
    vid, xy, pair, loops = build_vertex_graph(cfg, vt, edges)
    bridges, cinfo, lab = attach_components(cfg, xy, pair)
    log.info("graph: %d vertices, %d merged pairs, %d components", n, len(pair), cinfo["n_components"])

    # 2. sites
    sv = site_vertices(cfg, d, vid, xy)
    sup, m, shared = contract(sv, n)
    items = build_items(cfg, d, vid, xy, sv)
    sx = np.array([[it["x"], it["y"]] for it in items if it["kind"] == "site"])
    agg, nbr = super_graph(pair, bridges, sup, m)
    real_agg, _ = super_graph(pair, {}, sup, m)
    sup_xy = np.zeros((m, 2))
    np.add.at(sup_xy, sup, xy)
    sup_xy /= np.bincount(sup, minlength=m)[:, None]

    # 3. weights
    scen = {}
    for name, sc in cfg["scenarios"].items():
        scen[name] = sc
    wv0 = vertex_weights(cfg, scen["S0"], items, n)
    units_v = np.zeros(n)
    for it in items:
        for v, s in it["shares"]:
            units_v[v] += s * (it["n_units"] if it["kind"] == "site" else 1)
    check("units attached to vertices", exp["units"], round(float(units_v.sum()), 6))
    usup = np.bincount(sup, weights=units_v, minlength=m)
    far = {}
    for kind in ("site", "edge", "tram"):
        its = [it for it in items if it["kind"] == kind and it["how"] == "nearest"]
        own = [it for it in items if it["kind"] == kind and it["how"] != "nearest"]
        far[kind] = dict(n_nearest=len(its), n_far=sum(it["dist"] > cfg["attach_far_m"] for it in its),
                         max_nearest=max([it["dist"] for it in its], default=0.0),
                         own_max=max([it["dist"] for it in own], default=0.0),
                         own_far=sum(it["dist"] > cfg["attach_far_m"] for it in own), n_own=len(own))

    # 4-5. partitions
    res = {}
    for name, sc in scen.items():
        res[name] = partition_scenario(cfg, name, sc, items, sup, m, n, agg, nbr)
        log.info("%s: balance(try) %.4f ufactor %s", name, res[name]["balance_try"], res[name]["ufactor"])
    centre = np.array(d["poly"].geometry.iloc[0].centroid.coords[0])
    w0sup = res["S0"]["wsup"]
    res["S0"]["part"] = order_zones(res["S0"]["part"], w0sup, sup_xy, centre, k)
    ref = res["S0"]["part"]
    for name in scen:
        if name != "S0":
            res[name]["part"] = hungarian_relabel(ref, res[name]["part"], w0sup, k)
    # connectivity check after repair (and after relabel)
    for name, r in res.items():
        comps = zone_components(r["part"], nbr)
        check(f"{name}: every zone connected", 0, sum(1 for cs in comps.values() if len(cs) > 1))
        check(f"{name}: all {k} zones non-empty", k, len(comps))
        wsplit = 0
        for it in items:
            if it["kind"] == "site":
                zs = {int(r["part"][sup[v]]) for v in it["sv"]}
                wsplit += len(zs) > 1
        check(f"{name}: sites split between zones", 0, wsplit)

    # 6. cores
    sup_adj = coo_matrix((np.ones(len(real_agg) * 2), ([a for a, b in real_agg] + [b for a, b in real_agg],
                                                      [b for a, b in real_agg] + [a for a, b in real_agg])), shape=(m, m)).tocsr()
    dist_other = np.full(m, np.inf)
    for z in range(k):
        src = np.flatnonzero(ref != z)
        dz = dijkstra(sup_adj, directed=False, unweighted=True, indices=src, min_only=True)
        dist_other[ref == z] = dz[ref == z]
    stable = np.ones(m, bool)
    for name in scen:
        stable &= res[name]["part"] == ref
    core = stable & (dist_other >= cfg["core_hops"])
    log.info("stable super-vertices %d, core %d of %d", stable.sum(), core.sum(), m)

    out = dict(cfg=cfg, d=d, n=n, m=m, vid=vid, xy=xy, sup=sup, sup_xy=sup_xy, pair=pair, bridges=bridges, cinfo=cinfo,
               loops=loops, shared=shared, sv=sv, items=items, agg=agg, real_agg=real_agg, nbr=nbr, far=far,
               res=res, ref=ref, usup=usup, core=core, stable=stable, dist_other=dist_other, scen=scen, k=k,
               w0sup=w0sup, units_v=units_v, wv0=wv0)
    assign_and_report(out)


def assign_and_report(o):
    cfg, d, sup, ref, core, k = o["cfg"], o["d"], o["sup"], o["ref"], o["core"], o["k"]
    items, vt, edges, tram, sites = o["items"], d["vt"], d["edges"], d["tram"], d["sites"]
    vid = o["vid"]
    maxdeg = vt["max_degree"].to_numpy()
    cid = vt["junction_cluster_id"].to_numpy()
    vzone = ref[sup]
    vcore = core[sup]
    w = cfg["weights"]

    # 7. seam rule + per-element zone
    rows = []
    for it in items:
        if it["kind"] == "site":
            continue
        shares = it["shares"]
        if it["kind"] == "edge" and it["ekind"] == "inside_through":
            (a, _), (b, _) = shares
            za, zb = int(vzone[a]), int(vzone[b])
            if za == zb:
                z, seam, buf, inc = za, False, -1, bool(vcore[a] and vcore[b])
            else:
                keep_a = (maxdeg[a] > maxdeg[b]) or (maxdeg[a] == maxdeg[b] and cid[a] < cid[b])
                z, buf = (za, zb) if keep_a else (zb, za)
                seam, inc = True, False
        else:
            v = shares[0][0]
            z, seam, buf, inc = int(vzone[v]), False, -1, bool(vcore[v])
        rows.append(dict(kind=it["kind"], edge_id=it["key"], zone=z, in_core=inc, seam=seam, read_buffer_zone=buf))
    ez = pd.DataFrame(rows)
    ez["zone"] += 1
    ez["read_buffer_zone"] = ez["read_buffer_zone"].where(ez["read_buffer_zone"] < 0, ez["read_buffer_zone"] + 1)
    ez = ez.set_index("edge_id")
    sz = {}
    for it in items:
        if it["kind"] == "site":
            v = it["shares"][0][0]
            sz[it["key"]] = (int(vzone[v]) + 1, bool(vcore[v]))
    write_all(o, ez, sz)


def sample_points(geoms, step):
    xs, ys, idx = [], [], []
    for i, g in enumerate(geoms):
        L = g.length
        dist = np.append(np.arange(0, L, step), L)
        pts = shapely.line_interpolate_point(g, dist)
        xs.extend(shapely.get_x(pts))
        ys.extend(shapely.get_y(pts))
        idx.extend([i] * len(dist))
    return np.array(xs), np.array(ys), np.array(idx)


def build_polygons(cfg, d, eg, cl):
    """Voronoi cells of edge samples + cluster centroids, dissolved by zone / (zone, in_core), clipped to RING 1."""
    crs = cfg["crs_metric"]
    ring = d["poly"].geometry.iloc[0]
    x, y, idx = sample_points(eg.geometry.to_numpy(), cfg["voronoi_step_m"])
    pts = pd.DataFrame({"x": np.concatenate([cl.geometry.x.to_numpy(), x]),
                        "y": np.concatenate([cl.geometry.y.to_numpy(), y]),
                        "zone": np.concatenate([cl["zone"].to_numpy(), eg["zone"].to_numpy()[idx]]),
                        "in_core": np.concatenate([cl["in_core"].to_numpy(), eg["in_core"].to_numpy()[idx]])})
    pts["key"] = list(zip(pts["x"].round(2), pts["y"].round(2)))
    pts = pts.drop_duplicates("key", keep="first").reset_index(drop=True)   # cluster centroids come first
    mp = shapely.multipoints(pts[["x", "y"]].to_numpy())
    extent = shapely.box(*ring.buffer(cfg["voronoi_extent_buffer_m"]).bounds)
    cells = shapely.get_parts(shapely.voronoi_polygons(mp, extend_to=extent))
    cg = gpd.GeoDataFrame(geometry=cells, crs=crs)
    pg = gpd.GeoDataFrame(pts[["zone", "in_core"]], geometry=shapely.points(pts[["x", "y"]].to_numpy()), crs=crs)
    j = gpd.sjoin(cg, pg, predicate="contains", how="inner").sort_index()
    assert len(j) == len(cg) == len(pts), (len(j), len(cg), len(pts))
    j["geometry"] = j.geometry.intersection(ring)
    zv = j.dissolve(by="zone", as_index=False)[["zone", "geometry"]]
    zc = j.dissolve(by=["zone", "in_core"], as_index=False)[["zone", "in_core", "geometry"]]
    zv["area_km2"] = zv.geometry.area / 1e6
    zc["area_km2"] = zc.geometry.area / 1e6
    return zv.sort_values("zone").reset_index(drop=True), zc.sort_values(["zone", "in_core"]).reset_index(drop=True), len(pts)


def layer_digest(path):
    import pyogrio
    h = hashlib.sha256()
    for name in sorted(str(r[0]) for r in pyogrio.list_layers(path)):
        g = gpd.read_file(path, layer=name)
        h.update(name.encode())
        h.update(g.drop(columns="geometry").to_csv(index=False).encode())
        h.update(b"".join(shapely.to_wkb(g.geometry.to_numpy())))
    return h.hexdigest()


def write_all(o, ez, sz):
    cfg, d, items, k = o["cfg"], o["d"], o["items"], o["k"]
    vt, edges, tram, sites, sup, res = d["vt"], d["edges"], d["tram"], d["sites"], o["sup"], o["res"]
    ref, core, scen = o["ref"], o["core"], o["scen"]
    crs, w = cfg["crs_metric"], cfg["weights"]
    out_gpkg = pathlib.Path(cfg["paths"]["output_gpkg"])
    out_gpkg.parent.mkdir(parents=True, exist_ok=True)
    for suf in ("", "-wal", "-shm"):
        pathlib.Path(str(out_gpkg) + suf).unlink(missing_ok=True)

    # ---- layers
    allseg = pd.concat([edges[["edge_id", "geometry"]], tram[["edge_id", "geometry"]]], ignore_index=True)
    eg = gpd.GeoDataFrame(allseg, crs=crs)
    for c in ("zone", "in_core", "seam", "read_buffer_zone"):
        eg[c] = eg["edge_id"].map(ez[c]).to_numpy()
    eg["read_buffer_zone"] = eg["read_buffer_zone"].astype("Int64").where(eg["read_buffer_zone"] > 0)
    eg = eg[["edge_id", "zone", "in_core", "seam", "read_buffer_zone", "geometry"]]
    cl = gpd.GeoDataFrame({"cluster_id": vt["junction_cluster_id"].to_numpy(), "zone": ref[sup] + 1, "in_core": core[sup]},
                          geometry=vt.geometry.to_numpy(), crs=crs)
    zv, zc, n_pts = build_polygons(cfg, d, eg, cl)
    seam = eg[eg["seam"]].copy()
    eg.to_file(out_gpkg, layer="edges_zone", driver="GPKG")
    cl.to_file(out_gpkg, layer="clusters_zone", driver="GPKG", mode="a")
    zv.to_file(out_gpkg, layer="zones_v0", driver="GPKG", mode="a")
    zc.to_file(out_gpkg, layer="zones_core", driver="GPKG", mode="a")
    seam.to_file(out_gpkg, layer="seam_edges", driver="GPKG", mode="a")

    # scenario csv
    sc = pd.DataFrame({"cluster_id": vt["junction_cluster_id"].to_numpy()})
    for name in scen:
        sc[name.lower() + "_zone"] = res[name]["part"][sup] + 1
    sc["stable_all"] = o["stable"][sup]
    sc["hops_to_other_zone"] = np.where(np.isinf(o["dist_other"][sup]), -1, o["dist_other"][sup]).astype(int)
    sc["in_core"] = core[sup]
    sc.to_csv(cfg["paths"]["output_scenarios"], index=False)

    # ---- tables
    seg = pd.concat([
        pd.DataFrame([dict(edge_id=it["key"], tram=False, tier=it["tier"], promoted=it["promoted"], length=it["length"])
                      for it in items if it["kind"] == "edge"]),
        pd.DataFrame([dict(edge_id=it["key"], tram=True, tier="A", promoted=False, length=it["length"])
                      for it in items if it["kind"] == "tram"])], ignore_index=True)
    seg = seg.join(ez[["zone", "in_core", "seam"]], on="edge_id")
    seg["stratum"] = np.where(seg["tram"], "tram_segment", "edge_" + seg["tier"])
    if cfg["b_service_promoted"]:
        seg.loc[(seg["stratum"] == "edge_B") & seg["promoted"], "stratum"] = "edge_B_service"
        seg.loc[seg["stratum"] == "edge_B", "stratum"] = "edge_B_core"
    seg["minutes"] = np.where(seg["tram"], w["tram_segment"], seg["tier"].map(w["edge_tier"]))
    s0 = scen["S0"]
    st = pd.DataFrame([dict(site_id=it["key"], n_units=it["n_units"], comp=it["comp"], zone=sz[it["key"]][0],
                            in_core=sz[it["key"]][1], minutes=item_weight(cfg, s0, it), how=it["how"]) for it in items if it["kind"] == "site"])
    sc_ = cfg["site_size_classes"]
    st["size"] = np.where(st["n_units"] <= sc_["small_max"], "small", np.where(st["n_units"] <= sc_["medium_max"], "medium", "large"))
    st["signal"] = st["comp"].str.contains("signal")
    st["tram"] = st["comp"].str.contains("tram")
    ring_area = zv["area_km2"].sum()

    zones = list(range(1, k + 1))
    kb = d["kbr"]
    r1 = kb[kb["Kordon"] == cfg["kbr_ring"]]
    jz = gpd.sjoin(r1, zv[["zone", "geometry"]], predicate="within", how="left")
    n_unassigned = int(jz["zone"].isna().sum())
    if n_unassigned:
        near = gpd.sjoin_nearest(r1.loc[jz["zone"].isna().to_numpy()], zv[["zone", "geometry"]], how="left")
        jz.loc[jz["zone"].isna(), "zone"] = near["zone"].to_numpy()
    r1_cnt = jz["zone"].astype(int).value_counts().to_dict()

    comp_rows, strata_core = [], {}
    for z in zones:
        sz_ = st[st["zone"] == z]
        sg = seg[seg["zone"] == z]
        sc_z = sz_[sz_["in_core"]]
        sgc = sg[sg["in_core"]]
        cnt = {"site_small": int((sc_z["size"] == "small").sum()), "site_medium": int((sc_z["size"] == "medium").sum()),
               "site_large": int((sc_z["size"] == "large").sum()), "site_tram": int(sc_z["tram"].sum())}
        for s in ("edge_A", "edge_B_core", "edge_B_service", "edge_C", "tram_segment"):
            cnt[s] = int((sgc["stratum"] == s).sum())
        strata_core[z] = cnt
        roads = sg[~sg["tram"]]
        comp_rows.append(dict(
            zone=z, units=int(sz_["n_units"].sum() + len(sg)), sites=len(sz_), small=int((sz_["size"] == "small").sum()),
            medium=int((sz_["size"] == "medium").sum()), large=int((sz_["size"] == "large").sum()),
            signal=int(sz_["signal"].sum()), tram_site=int(sz_["tram"].sum()),
            kmA=roads.loc[roads["tier"] == "A", "length"].sum() / 1000, kmB=roads.loc[roads["tier"] == "B", "length"].sum() / 1000,
            kmC=roads.loc[roads["tier"] == "C", "length"].sum() / 1000, tram_km=sg.loc[sg["tram"], "length"].sum() / 1000,
            nA=int((sg["stratum"] == "edge_A").sum()), nBc=int((sg["stratum"] == "edge_B_core").sum()),
            nBs=int((sg["stratum"] == "edge_B_service").sum()), nC=int((sg["stratum"] == "edge_C").sum()),
            ntram=int(sg["tram"].sum()), minutes=float(sz_["minutes"].sum() + sg["minutes"].sum()),
            part_minutes=float(o["w0sup"][ref == z - 1].sum()),
            area=float(zv.loc[zv["zone"] == z, "area_km2"].iloc[0]), r1=int(r1_cnt.get(z, 0)),
            core_units=int(sc_z["n_units"].sum() + len(sgc)), core_minutes=float(sc_z["minutes"].sum() + sgc["minutes"].sum()),
            core_vertices=int(core[ref == z - 1].sum()), vertices=int((ref == z - 1).sum())))
    comp = pd.DataFrame(comp_rows)
    check("zone units sum to total", cfg["expected"]["units"], int(comp["units"].sum()))
    seam_n = int(seg["seam"].sum())
    cut_road = sum(c for (a, b), c in o["real_agg"].items() if ref[a] != ref[b])
    check("seam edges == road edges cut by the partition (S0)", cut_road, seam_n)
    check("R1 counters assigned to zones", cfg["kbr_expected"], int(sum(r1_cnt.values())))

    # stability
    stab = []
    tot0, totu = o["w0sup"].sum(), o["usup"].sum()
    for name in scen:
        r = res[name]
        wsup = r["wsup"]
        tz = np.bincount(r["part"], weights=wsup, minlength=k)
        tz0 = np.bincount(r["part"], weights=o["w0sup"], minlength=k)
        keep = r["part"] == ref
        cp, ce = cut_stats(r["part"], o["agg"], o["real_agg"])
        stab.append((name, f"{tz.max() / tz.mean():.3f}", f"{tz0.max() / tz0.mean():.3f}", cp, ce, r["ufactor"], len(r["moves"]),
                     f"{o['w0sup'][keep].sum() / tot0:.1%}", f"{o['usup'][keep].sum() / totu:.1%}",
                     f"{int(keep.sum())}/{o['m']}"))
        if name != "S0":
            check(f"{name}: balance (own weights) <= {cfg['balance_max']}", f"<= {cfg['balance_max']}", f"{tz.max() / tz.mean():.3f}",
                  tz.max() / tz.mean() <= cfg["balance_max"])
    check("S0: balance <= %s" % cfg["balance_max"], f"<= {cfg['balance_max']}", stab[0][1], float(stab[0][1]) <= cfg["balance_max"])
    per_zone_keep = []
    for z in range(k):
        mk = ref == z
        row = [z + 1]
        for name in list(scen)[1:]:
            row.append(f"{o['w0sup'][mk & (res[name]['part'] == ref)].sum() / o['w0sup'][mk].sum():.1%}")
        per_zone_keep.append(row)

    # pair table
    seam_df = seg[seg["seam"]].join(ez[["read_buffer_zone"]], on="edge_id")
    pairs = sorted({(min(a, b), max(a, b)) for a, b in zip(seam_df["zone"], seam_df["read_buffer_zone"])})
    need = cfg["needed"]
    prow = []
    for a, b in pairs:
        cn = {s: strata_core[a][s] + strata_core[b][s] for s in need}
        ratios = {s: min(1.0, cn[s] / need[s]) for s in need}
        lim = min(ratios, key=lambda s: (ratios[s], list(need).index(s)))
        nseam = int(((seam_df["zone"].isin([a, b])) & (seam_df["read_buffer_zone"].isin([a, b]))).sum())
        prow.append(dict(a=a, b=b, nseam=nseam, cn=cn, score=ratios[lim], mean=float(np.mean(list(ratios.values()))), limiting=lim))
    prow.sort(key=lambda r: (-r["score"], -r["mean"], r["a"], r["b"]))

    write_report(o, comp, stab, per_zone_keep, prow, seam_df, seg, st, strata_core, r1_cnt, n_unassigned, n_pts, ez)
    dig = {nm: layer_digest(str(out_gpkg)) for nm in [""]}
    pathlib.Path(cfg["paths"]["output_digest"]).write_text(f"gpkg_content_sha256 {dig['']}\n")
    log.info("outputs written; gpkg content digest %s", dig[""])
    if any(c[3] == "FAIL" for c in CHECKS):
        log.error("some checks FAILED; see %s", cfg["paths"]["report"])


def write_report(o, comp, stab, per_zone_keep, prow, seam_df, seg, st, strata_core, r1_cnt, n_unassigned, n_pts, ez):
    cfg, d, k, res, items = o["cfg"], o["d"], o["k"], o["res"], o["items"]
    ci, far = o["cinfo"], o["far"]
    w = cfg["weights"]
    L = ["# Task 03a: provisional partition of RING 1 into 11 zones (v0)", ""]
    L.append("Analysis only. All numbers in `config/16_partition.yaml` are `[PROPOSED]`; the work weights are unmeasured guesses "
             "(timing pilot not evaluated). Nothing here changes `scope.yaml`, the polygon, D2-D4 or `tiers.yaml`. "
             f"Outputs: `{cfg['paths']['output_gpkg']}`, `{cfg['paths']['output_scenarios']}`.\n")
    L.append("## Checks\n")
    L.append(md_table(["Check", "Expected", "Actual", "Result"], CHECKS))
    L.append("\n## 1. Graph\n")
    L.append(f"Vertices = {o['n']} junction clusters with `centroid_in`. Graph edges = `inside_through` road edges between two vertices, "
             f"multi-edges merged ({len(o['pair'])} vertex pairs from {sum(o['pair'].values())} edges; {o['loops'][0]} intra-cluster loops dropped, {o['loops'][1]:.2f} km; their minutes stay on the cluster). "
             "Boundary stubs, dead-end spurs, isolated roads and tram-only ways carry weight only.\n")
    L.append(f"Connected components: **{ci['n_components']}**; sizes {ci['sizes'][:12]}{' ...' if len(ci['sizes']) > 12 else ''}.\n")
    if ci["bridges"]:
        L.append("Every component other than the largest was attached (one synthetic graph edge, weight 1) to the geometrically nearest vertex of the largest one:\n")
        L.append(md_table(["component size (vertices)", "distance to largest (m)"],
                          [(b["size"], f"{b['dist_m']:.0f}") for b in ci["bridges"]]))
        L.append(f"\nThe synthetic edges are not road edges; they are excluded from cut-edge counts and hop distances.\n")
    L.append("\n## 2. Atomic sites\n")
    n_none = sum(1 for it in items if it["kind"] == "site" and not it["sv"])
    L.append(f"{len(o['sv'])} sites; {o['m']} super-vertices after contraction ({o['n'] - o['m']} vertices merged). "
             f"Site vertices = complex clusters of the site, junction clusters of its signal nodes on junctions, and tram-crossing nodes that are junction nodes (only those with `centroid_in`). "
             f"Sites with no such vertex (tram-only / crossing-only): **{n_none}**, attached to the nearest vertex. "
             f"Vertices claimed by more than one site (those sites then share one super-vertex): {o['shared']}.\n")
    L.append("\n## 3. Proxy weights (S0)\n")
    L.append(f"site = min({w['site_cap']}, {w['site_base']} + {w['site_per_unit']} * n_units); edge A/B/C = {w['edge_tier']}; tram segment = {w['tram_segment']} min. "
             "Edge minutes split half and half between end vertices (all to the one vertex for spurs and stubs); isolated roads and tram-only ways go to the nearest vertex.\n")
    rows = []
    lab = {"site": "sites (no own vertex -> nearest)", "edge": "isolated road edges -> nearest", "tram": "tram-only ways -> nearest"}
    for kd in ("site", "edge", "tram"):
        f = far[kd]
        rows.append((lab[kd], f["n_nearest"], f["n_far"], f"{f['max_nearest']:.0f}"))
    L.append(md_table(["attached by nearest vertex", "n", f"> {cfg['attach_far_m']} m from the segment", "max distance (m)"], rows))
    sfar = far["site"]
    L.append(f"\nSites that own vertices: {sfar['n_own']}; the farthest of their vertices from the site point is {sfar['own_max']:.0f} m "
             f"({sfar['own_far']} sites > {cfg['attach_far_m']} m). Tram-only ways that have an end junction cluster: "
             f"{sum(1 for it in items if it['kind'] == 'tram' and it['has_end_cluster'])} (still attached to the nearest vertex).\n")
    tot = sum(r["wsup"].sum() for r in [res["S0"]])
    L.append(f"Total S0 minutes: {tot:.0f}; per zone mean {tot / k:.0f}.\n")
    L.append("\n## 4. Partition (S0)\n")
    r0 = res["S0"]
    L.append(f"Method: `pymetis.part_graph` on the contracted graph (vertex weight = S0 minutes x {cfg['weight_scale']}, edge weight = number of merged road edges), "
             f"k = {k}, seed {cfg['seed']}, contiguity on, ncuts {cfg['metis']['ncuts']}, niter {cfg['metis']['niter']}; "
             f"imbalance factors tried in order {cfg['metis']['ufactor_try']}, first one with max/mean <= {cfg['balance_max']} kept. "
             f"S0 used ufactor {r0['ufactor']}; zones repaired after METIS: {len(r0['moves'])} moves.\n")
    for name in res:
        if res[name]["moves"]:
            L.append(f"- {name} repair moves: " + "; ".join(f"{m['vertices']} super-vertices (weight {m['weight'] / cfg['weight_scale']:.1f}) from zone {m['from']} to {m['to']} (pre-relabel labels)" for m in res[name]["moves"]))
    L.append("\nZones are numbered 1-11 clockwise from north around the RING 1 centroid (S0 only; S1-S4 are matched to S0).\n")
    L.append("\n## 5. Stability scenarios\n")
    L.append("S0 proxy; S1 every unit 1; S2 length (edge = length_m, site = 100 + 20 n_units); S3 S0 with site minutes x 0.6; S4 x 1.6. Labels matched to S0 by Hungarian assignment on shared S0 weight.\n")
    L.append(md_table(["scenario", "balance (own weights)", "balance (S0 weights)", "cut vertex pairs", "cut road edges", "ufactor", "repair moves",
                       "S0 minutes keeping zone", "units keeping zone", "super-vertices keeping zone"], stab))
    L.append("\nShare of each S0 zone's minutes that stays in the zone, by scenario:\n")
    L.append(md_table(["zone"] + list(res)[1:], per_zone_keep))
    L.append("\n## 6. Robust cores\n")
    L.append(f"Core = super-vertices in the same matched zone in S0-S4 and at least {cfg['core_hops']} junction hops (real graph edges, sites contracted) from any vertex of a different S0 zone. "
             f"Stable in all five scenarios: {int(o['stable'].sum())} of {o['m']} super-vertices; core: {int(o['core'].sum())}. "
             "An element is in the core if its vertex is; a through edge needs both end vertices in the core; seam edges are never in the core. "
             "Minutes and units are counted after the seam rule (an edge's full minutes belong to its zone).\n")
    crow = []
    for r in comp.itertuples():
        crow.append((r.zone, f"{r.core_vertices}/{r.vertices}", r.core_units, f"{r.core_minutes:.0f}", f"{r.core_minutes / r.minutes:.1%}", f"{r.core_units / r.units:.1%}"))
    tc = comp[["core_units", "core_minutes"]].sum()
    crow.append(("**all**", f"{int(comp['core_vertices'].sum())}/{int(comp['vertices'].sum())}", int(tc.core_units), f"{tc.core_minutes:.0f}",
                 f"{tc.core_minutes / comp['minutes'].sum():.1%}", f"{tc.core_units / comp['units'].sum():.1%}"))
    L.append(md_table(["zone", "core vertices / vertices", "core units", "core S0 minutes", "share of zone minutes", "share of zone units"], crow))
    L.append("\n## 7. Seam rule\n")
    L.append("A road edge whose end clusters lie in different zones belongs to the zone of the end cluster with the larger `max_degree` (tie: lower cluster id); `seam = true`, the other zone is `read_buffer_zone`.\n")
    sl = seam_df["length"].sum() / 1000
    L.append(f"Seam edges: **{len(seam_df)}**, **{sl:.2f} km** (all tiers); by tier: " +
             ", ".join(f"{t} {int((seam_df['tier'] == t).sum())}" for t in "ABC") + ".\n")
    L.append("\n## 8. Composition of S0 zones (after the seam rule)\n")
    rows = [(r.zone, r.units, f"{r.sites} ({r.small}/{r.medium}/{r.large})", r.signal, r.tram_site, f"{r.kmA:.1f}/{r.kmB:.1f}/{r.kmC:.1f}",
             f"{r.tram_km:.1f}", f"{r.nA}/{r.nBc}/{r.nBs}/{r.nC}", r.ntram, f"{r.minutes:.0f}", f"{r.part_minutes:.0f}",
             f"{r.area:.2f}", r.r1) for r in comp.itertuples()]
    t = comp
    rows.append(("**all**", int(t.units.sum()), f"{int(t.sites.sum())} ({int(t.small.sum())}/{int(t.medium.sum())}/{int(t.large.sum())})", int(t.signal.sum()),
                 int(t.tram_site.sum()), f"{t.kmA.sum():.1f}/{t.kmB.sum():.1f}/{t.kmC.sum():.1f}", f"{t.tram_km.sum():.1f}",
                 f"{t.nA.sum()}/{t.nBc.sum()}/{t.nBs.sum()}/{t.nC.sum()}", int(t.ntram.sum()), f"{t.minutes.sum():.0f}", f"{t.part_minutes.sum():.0f}",
                 f"{t.area.sum():.2f}", int(t.r1.sum())))
    L.append(md_table(["zone", "units", "sites (small/medium/large)", "sites with signal", "sites with tram", "km road A/B/C", "tram km",
                       "edges A/B-core/B-service/C", "tram ways", "S0 minutes (seam rule)", "S0 minutes (partition)", "area km2", "R1 counters"], rows))
    L.append("\nSite size classes: small 1-2 units, medium 3-9, large >= 10. Tram ways are the tram-only ways (not counted in the A edges). "
             "'S0 minutes (partition)' is the quantity METIS balanced (edge minutes split half/half); '(seam rule)' gives each edge entirely to its zone. "
             f"R1 counters: contained in the zone polygon; {n_unassigned} outside every polygon were assigned to the nearest zone. "
             f"Polygons: Voronoi of {n_pts} points (edge samples every {cfg['voronoi_step_m']} m plus cluster centroids), dissolved and clipped to RING 1.\n")
    L.append("\n## 9. Adjacent zone pairs and coverage of the combined core\n")
    needs = cfg["needed"]
    L.append(f"{len(prow)} adjacent pairs (share at least one seam edge). Coverage score = min over strata of min(1, count / needed), needed = {needs}. "
             "Counts are core elements of both zones combined. Ties broken by mean of the per-stratum ratios.\n")
    head = ["pair", "seam edges", "score", "limiting stratum"] + list(needs)
    rows = [(f"{r['a']}-{r['b']}", r["nseam"], f"{r['score']:.2f}", r["limiting"]) + tuple(r["cn"][s] for s in needs) for r in prow[:cfg["top_pairs"]]]
    L.append("Top %d pairs:\n" % cfg["top_pairs"])
    L.append(md_table(head, rows))
    L.append("\nScore distribution over all pairs: " + ", ".join(f"{r['a']}-{r['b']}: {r['score']:.2f}" for r in prow) + ".\n")
    L.append("\n## 10. Per-zone core strata\n")
    rows = [(z,) + tuple(strata_core[z][s] for s in needs) for z in strata_core]
    L.append(md_table(["zone"] + list(needs), rows))
    pathlib.Path(cfg["paths"]["report"]).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(cfg["paths"]["report"]).write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(L[:12]))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config/16_partition.yaml")
