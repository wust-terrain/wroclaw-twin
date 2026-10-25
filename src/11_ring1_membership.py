"""Task 01b: RING 1 membership of junction/signal clusters and road segments (read-only analysis).

Usage: uv run python src/11_ring1_membership.py [config/11_ring1_membership.yaml]
"""
import json
import logging
import pathlib
import sys
import time

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
import yaml
from scipy.spatial import cKDTree
from scipy.spatial.distance import pdist
from shapely.geometry import LineString

log = logging.getLogger("membership")


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


def membership_flags(clusters, nodes, id_col, poly):
    """Add centroid_in / any_in / all_in / diameter_m to a cluster layer from its member nodes."""
    prep = shapely.prepared.prep(poly)
    inside = np.array([prep.contains(g) for g in nodes.geometry])
    nodes = nodes.assign(
        inside=inside, x=nodes.geometry.x.to_numpy(), y=nodes.geometry.y.to_numpy()
    )
    g = nodes.groupby(id_col)
    flags = pd.DataFrame({"any_in": g["inside"].any(), "all_in": g["inside"].all()})
    diam = {
        k: (float(pdist(v[["x", "y"]].to_numpy()).max()) if len(v) > 1 else 0.0)
        for k, v in g
    }
    flags["diameter_m"] = pd.Series(diam)
    out = clusters.merge(flags, left_on=id_col, right_index=True, how="left")
    out["centroid_in"] = [prep.contains(g_) for g_ in out.geometry]
    return out


def split_ways(ways, jn, cluster_of):
    """Split ways at junction-node vertices; returns a GeoDataFrame of segments."""
    rows, geoms = [], []
    for w in ways.itertuples():
        pts = list(w.geometry.coords)
        keys = [cluster_of.get((round(x, DEC), round(y, DEC))) for x, y in pts]
        idx = [i for i, k in enumerate(keys) if k is not None]
        cuts = sorted(set([0, len(pts) - 1] + idx))
        for a, b in zip(cuts[:-1], cuts[1:]):
            ca = keys[a][1] if keys[a] is not None else -1
            cb = keys[b][1] if keys[b] is not None else -1
            rows.append((w.osm_id, w.highway, bool(w.is_tram), ca, cb))
            geoms.append(LineString(pts[a:b + 1]))
    seg = gpd.GeoDataFrame(
        pd.DataFrame(rows, columns=["way_id", "highway", "is_tram", "cluster_a", "cluster_b"]),
        geometry=geoms, crs=ways.crs,
    )
    seg["length_m"] = seg.geometry.length
    return seg


def main():
    global DEC
    t0 = time.time()
    cfg = load_yaml(sys.argv[1] if len(sys.argv) > 1 else "config/11_ring1_membership.yaml")
    setup_logging(cfg["paths"]["log"])
    crs = cfg["crs_metric"]
    DEC = cfg["coord_match_decimals"]
    fp = cfg["paths"]["features"]

    poly_gdf = gpd.read_file(cfg["paths"]["polygons"], layer=cfg["paths"]["polygon_layer"])
    assert poly_gdf.crs.to_epsg() == crs and len(poly_gdf) == 1
    poly = poly_gdf.geometry.iloc[0]
    shapely.prepare(poly)

    jc = gpd.read_file(fp, layer="junction_clusters")
    jn = gpd.read_file(fp, layer="junction_nodes")
    sc = gpd.read_file(fp, layer="signal_clusters")
    sn = gpd.read_file(fp, layer="signal_nodes")
    ways = gpd.read_file(fp, layer="ways")
    tc = gpd.read_file(fp, layer="tram_crossings")
    kbr = gpd.read_file(fp, layer="kbr_points")

    # (a, b) flags and diameters
    jcm = membership_flags(jc, jn, "junction_cluster_id", poly)
    scm = membership_flags(sc, sn, "cluster_id", poly)
    log.info("flags computed")

    def sens(c):
        dis = c[["centroid_in", "any_in", "all_in"]]
        disagree = ~(dis.nunique(axis=1) == 1)
        return {k: int(c[k].sum()) for k in dis.columns} | {
            "n": len(c), "disagree": int(disagree.sum())}
    sens_j, sens_s = sens(jcm), sens(scm)

    # (d) counters
    r1 = kbr[kbr["Kordon"] == cfg["kbr_ring"]].reset_index(drop=True)
    checks = [("KBR %s counters" % cfg["kbr_ring"], cfg["kbr_expected"], len(r1),
               len(r1) == cfg["kbr_expected"])]
    d, ni = cKDTree(np.column_stack([jn.geometry.x, jn.geometry.y])).query(
        np.column_stack([r1.geometry.x, r1.geometry.y]))
    cl = jn["junction_cluster_id"].to_numpy()[ni]
    cm = jcm.set_index("junction_cluster_id")
    counters = pd.DataFrame({
        "counter": r1["Pkt_pomiar"], "cluster": cl, "dist_m": d,
        "centroid_in": cm.loc[cl, "centroid_in"].to_numpy(),
        "n_nodes": cm.loc[cl, "n_nodes"].to_numpy(),
        "to_boundary_m": [poly.exterior.distance(g) for g in r1.geometry],
        "counter_in": [poly.contains(g) for g in r1.geometry],
    })
    checks.append(("counters inside polygon", len(r1), int(counters["counter_in"].sum()),
                   bool(counters["counter_in"].all())))
    checks.append(("counter clusters centroid_in", len(r1), int(counters["centroid_in"].sum()),
                   bool(counters["centroid_in"].all())))

    # (e) segments
    cluster_of = {
        (round(x, DEC), round(y, DEC)): (nid, c)
        for nid, c, x, y in zip(jn["osm_id"], jn["junction_cluster_id"],
                                jn.geometry.x, jn.geometry.y)
    }
    n_coord_collisions = len(jn) - len(cluster_of)
    seg = split_ways(ways, jn, cluster_of)
    log.info("%d segments from %d ways", len(seg), len(ways))
    cin = cm["centroid_in"].to_dict()
    cin[-1] = False
    seg["end_a_in"] = seg["cluster_a"].map(cin)
    seg["end_b_in"] = seg["cluster_b"].map(cin)
    seg["ring1"] = seg["end_a_in"] | seg["end_b_in"]
    seg["boundary_stub"] = seg["end_a_in"] ^ seg["end_b_in"]
    seg["stub_dead_end"] = seg["boundary_stub"] & (
        (seg["cluster_a"] == -1) | (seg["cluster_b"] == -1))
    seg["no_end_cluster"] = (seg["cluster_a"] == -1) & (seg["cluster_b"] == -1)
    for name, col in (("any_in", "any_in"), ("all_in", "all_in")):
        m = cm[col].to_dict(); m[-1] = False
        seg["ring1_" + name] = seg["cluster_a"].map(m) | seg["cluster_b"].map(m)
    seg["inside_frac"] = shapely.length(shapely.intersection(seg.geometry.values, poly)) / seg["length_m"]
    checks.append(("segment km == way km", f"{ways['length_m'].sum():.3f}",
                   f"{seg['length_m'].sum():.3f}",
                   abs(ways["length_m"].sum() - seg["length_m"].sum()) < 1e-3))
    # every junction node must have been matched to a vertex
    vkeys = {(round(x, DEC), round(y, DEC)) for g in ways.geometry for x, y in g.coords}
    unmatched = len(set(cluster_of) - vkeys)
    checks.append(("junction nodes without a way vertex", 0, unmatched, unmatched == 0))
    checks.append(("junction nodes sharing coordinates", 0, n_coord_collisions, n_coord_collisions == 0))

    # polygon facts
    pf = {
        "area_km2": poly.area / 1e6, "perimeter_km": poly.length / 1000,
        "vertices": len(poly.exterior.coords) - 1, "holes": len(poly.interiors),
        "min_counter_m": counters["to_boundary_m"].min(),
    }

    # console summary
    print(md_table(["Check", "Expected", "Actual", "Result"],
                   [(n, e, a, "PASS" if ok else "FAIL") for n, e, a, ok in checks]))
    if not counters["centroid_in"].all() or not counters["counter_in"].all():
        print("STOP: counters whose cluster is not centroid_in:")
        print(counters[~counters["centroid_in"]].to_string())
        log.error("counter check failed; no outputs written")
        sys.exit(1)
    if not all(ok for _, _, _, ok in checks):
        log.error("hard check failed; no outputs written")
        sys.exit(1)

    # outputs
    out = pathlib.Path(cfg["paths"]["output"])
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    jcm.to_file(out, layer="junction_clusters_m", driver="GPKG")
    scm.to_file(out, layer="signal_clusters_m", driver="GPKG")
    seg.to_file(out, layer="segments_m", driver="GPKG")

    write_report(cfg, poly, jcm, scm, sens_j, sens_s, counters, seg, tc, jn, pf, checks)

    # run fingerprint for the idempotence check (counts only)
    fpr = {
        "junction": sens_j, "signal": sens_s, "segments": len(seg),
        "seg_ring1": int(seg["ring1"].sum()),
        "m_ring1": round(float(seg.loc[seg["ring1"], "length_m"].sum()), 3),
    }
    print("FINGERPRINT", json.dumps(fpr, sort_keys=True))
    log.info("done in %.1f s", time.time() - t0)


def pct(a, b):
    return f"{100 * a / b:.1f}%" if b else "-"


def write_report(cfg, poly, jcm, scm, sens_j, sens_s, counters, seg, tc, jn, pf, checks):
    L = ["# Task 01b: RING 1 membership and first workload numbers\n"]
    L.append(f"Input: `{cfg['paths']['features']}`, polygon `{cfg['paths']['polygons']}` "
             f"(layer `{cfg['paths']['polygon_layer']}`). Rule under test: D3 (`centroid_in`). "
             f"Output: `{cfg['paths']['output']}` (EPSG:{cfg['crs_metric']}). "
             "Read-only analysis: no parameters were tuned.\n")
    L.append("## Checks\n")
    L.append(md_table(["Check", "Expected", "Actual", "Result"],
                      [(n, e, a, "PASS" if ok else "FAIL") for n, e, a, ok in checks]))

    L.append("\n## Polygon facts (recomputed)\n")
    L.append(md_table(["Fact", "Value"], [
        ("area", f"{pf['area_km2']:.3f} km2"), ("perimeter", f"{pf['perimeter_km']:.2f} km"),
        ("vertices (exterior)", pf["vertices"]), ("holes", pf["holes"]),
        ("min counter distance to boundary", f"{pf['min_counter_m']:.1f} m")]))
    nb = cfg["nearest_boundary_counters"]
    nearest = counters.sort_values("to_boundary_m").head(nb)
    L.append(f"\n{nb} counters closest to the boundary:\n")
    L.append(md_table(["counter", "to boundary [m]"],
                      [(r.counter, f"{r.to_boundary_m:.1f}") for r in nearest.itertuples()]))

    L.append("\n## Sensitivity of membership rule\n")
    rows = []
    for name, s in (("junction_clusters", sens_j), ("signal_clusters", sens_s)):
        rows.append((name, s["n"], s["centroid_in"], s["any_in"], s["all_in"],
                     f"{s['disagree']} ({pct(s['disagree'], s['n'])})"))
    L.append(md_table(["layer", "clusters", "centroid_in", "any_in", "all_in",
                       "flags disagree (any cluster)"], rows))
    L.append("\nSegments (km) under the three rules (segment in iff at least one end cluster satisfies the flag):\n")
    L.append(md_table(["rule", "segments", "km"], [
        (n, int(seg[c].sum()), f"{seg.loc[seg[c], 'length_m'].sum() / 1000:.1f}")
        for n, c in (("centroid_in (D3)", "ring1"), ("any_in", "ring1_any_in"),
                     ("all_in", "ring1_all_in"))]))

    L.append("\n## Cluster diameter (max distance between member nodes)\n")
    qs = cfg["diameter_quantiles"]
    hdr = ["layer"] + [f"p{int(q * 100)} [m]" for q in qs] + ["max [m]"]
    rows = [(n, *[f"{c['diameter_m'].quantile(q):.1f}" for q in qs], f"{c['diameter_m'].max():.1f}")
            for n, c in (("junction_clusters", jcm), ("signal_clusters", scm))]
    L.append(md_table(hdr, rows))
    top = jcm.sort_values("diameter_m", ascending=False).head(cfg["top_clusters"])
    ll = top.to_crs(4326).geometry
    L.append(f"\n{cfg['top_clusters']} largest junction clusters by diameter:\n")
    L.append(md_table(["junction_cluster_id", "lon", "lat", "n_nodes", "diameter [m]", "centroid_in"],
                      [(r.junction_cluster_id, f"{p.x:.5f}", f"{p.y:.5f}", r.n_nodes,
                        f"{r.diameter_m:.1f}", r.centroid_in) for r, p in zip(top.itertuples(), ll)]))

    L.append("\n## Counter check (23 R1 counters)\n")
    L.append(md_table(["counter", "nearest cluster", "distance [m]", "cluster nodes", "centroid_in"],
                      [(r.counter, r.cluster, f"{r.dist_m:.1f}", r.n_nodes, r.centroid_in)
                       for r in counters.sort_values("counter").itertuples()]))
    L.append(f"\nMax counter-to-cluster-node distance: {counters['dist_m'].max():.1f} m. "
             "Distinct clusters: %d of %d counters." % (counters["cluster"].nunique(), len(counters)))

    ins = jcm[jcm["centroid_in"]]
    sins = scm[scm["centroid_in"]]
    L.append("\n## Clusters inside RING 1 (centroid_in)\n")
    L.append(f"Junction clusters: **{len(ins)}** of {len(jcm)}; signal clusters: **{len(sins)}** of {len(scm)}.\n")
    L.append("Signal clusters by kind (x mid_block):\n")
    ct = pd.crosstab(sins["kind"], sins["mid_block"]).reindex(columns=[False, True], fill_value=0)
    L.append(md_table(["kind", "mid_block = false", "mid_block = true", "total"],
                      [(k, r[False], r[True], r[False] + r[True]) for k, r in ct.iterrows()]
                      + [("**total**", ct[False].sum(), ct[True].sum(), len(sins))]))
    bins = cfg["degree_bins"]
    lab = ins["max_degree"].clip(upper=bins[-1]).map(lambda v: f"{v}+" if v == bins[-1] else str(v))
    L.append("\nJunction clusters by `max_degree`:\n")
    L.append(md_table(["max_degree", "clusters"], lab.value_counts().sort_index().items()))
    L.append("\nJunction clusters by attribute:\n")
    L.append(md_table(["attribute", "true", "false"],
                      [(c, int(ins[c].sum()), int((~ins[c]).sum()))
                       for c in ("has_signal", "has_roundabout", "has_tram")]))

    L.append("\n## Segments inside RING 1 (centroid_in)\n")
    L.append(f"Segments are ways split at junction nodes (degree >= 3): {len(seg)} in total, "
             f"{int(seg['ring1'].sum())} in RING 1. Ends with no junction node (dead ends, "
             "isolated ways) have no cluster and never count as inside.\n")
    road = seg[seg["highway"].notna()]
    g_all = road.groupby("highway")["length_m"].agg(["count", "sum"])
    g_in = road[road["ring1"]].groupby("highway")["length_m"].agg(["count", "sum"])
    g_stub = road[road["boundary_stub"]].groupby("highway")["length_m"].sum()
    rows = []
    for h in g_in.sort_values("sum", ascending=False).index:
        rows.append((h, int(g_in.loc[h, "count"]), f"{g_in.loc[h, 'sum'] / 1000:.2f}",
                     f"{g_stub.get(h, 0) / 1000:.2f}", f"{g_all.loc[h, 'sum'] / 1000:.1f}"))
    rows.append(("**total roads**", int(g_in["count"].sum()), f"{g_in['sum'].sum() / 1000:.2f}",
                 f"{g_stub.sum() / 1000:.2f}", f"{g_all['sum'].sum() / 1000:.1f}"))
    L.append(md_table(["highway", "segments in", "km in", "of which stub km", "km RING 1-3 total"], rows))
    r_in = road[road["ring1"]]
    L.append("\nRoad `service` and `track` are listed as their own rows above (both `[TO BE CONFIRMED]` classes).")
    stub = seg[seg["boundary_stub"]]
    real = stub[~stub["stub_dead_end"]]
    L.append("\n**Boundary stubs** (exactly one end cluster inside):\n")
    L.append(md_table(["kind", "segments", "km"], [
        ("stub to a cluster outside", len(real), f"{real['length_m'].sum() / 1000:.2f}"),
        ("stub to a dead end (no cluster)", int(stub["stub_dead_end"].sum()),
         f"{stub.loc[stub['stub_dead_end'], 'length_m'].sum() / 1000:.2f}"),
        ("all stubs", len(stub), f"{stub['length_m'].sum() / 1000:.2f}")]))
    L.append(f"\nSegments with no end cluster at all: {int(seg['no_end_cluster'].sum())} "
             f"({seg.loc[seg['no_end_cluster'], 'length_m'].sum() / 1000:.1f} km).")

    tram = seg[seg["is_tram"]]
    t_rule = tram[tram["ring1"]]
    t_geom = (tram["length_m"] * tram["inside_frac"]).sum() / 1000
    t_noc = tram[tram["no_end_cluster"]]
    L.append("\n## Tram\n")
    tcg = tc.copy()
    tcg_in = tcg[[poly.contains(g) for g in tcg.geometry]]
    jn_c = jn.merge(jcm[["junction_cluster_id", "centroid_in"]], on="junction_cluster_id")
    tc_jn = tcg_in.merge(jn_c[["osm_id", "centroid_in"]], on="osm_id", how="left")
    L.append(md_table(["measure", "value"], [
        ("tram segments by D3 rule", f"{len(t_rule)} ({t_rule['length_m'].sum() / 1000:.2f} km)"),
        ("tram segments with no end cluster", f"{len(t_noc)} ({t_noc['length_m'].sum() / 1000:.1f} km of {tram['length_m'].sum() / 1000:.1f} km total)"),
        ("tram km inside polygon, geometric clip (all tram segments)", f"{t_geom:.2f} km"),
        ("tram_crossings inside polygon", f"{len(tcg_in)} of {len(tc)}"),
        ("... of which node is a junction node with centroid_in cluster", int(tc_jn['centroid_in'].fillna(False).sum()))]))
    L.append("\nTram-only ways carry no junction nodes (degree counts road ways only), so the segment rule "
             "cannot place them; the geometric clip is the usable tram figure. Ways that are both tram and "
             "in-scope road are counted in both the road and tram rows.")

    pathlib.Path(cfg["paths"]["report"]).write_text("\n".join(L) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
