"""Task 01c: RING 1 ownership layer and work-unit table (read-only analysis).

Usage: uv run python src/13_ring1_ownership.py [config/13_ring1_ownership.yaml]
"""
import collections
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
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from shapely.geometry import MultiLineString

log = logging.getLogger("ownership")
TIERS = ["A", "B", "C", "unmapped"]
KINDS = ["inside_through", "boundary_stub", "dead_end_spur", "isolated"]


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


def km(m):
    return f"{m / 1000:.2f}"


def key(pt, dec):
    return (round(pt[0], dec), round(pt[1], dec))


def road_degree(ways, dec):
    """Node degree by rounded coordinate, as in task 01: interior vertex 2, way end 1."""
    deg = collections.Counter()
    for g in ways.geometry:
        c = [key(p, dec) for p in g.coords]
        for p in c[1:-1]:
            deg[p] += 2
        deg[c[0]] += 1
        deg[c[-1]] += 1
    return deg


def merge_chains(road, deg, cluster_of, dec):
    """Merge road fragments across degree-2 nodes (no junction cluster) into graph edges.

    Returns (edge geometries, fragment -> edge index, number of anomalous merges).
    """
    ends = collections.defaultdict(list)
    for i, g in enumerate(road.geometry):
        for p in (g.coords[0], g.coords[-1]):
            k = key(p, dec)
            if k not in cluster_of and deg.get(k, 0) == 2:
                ends[k].append(i)
    rows, cols, anomalies = [], [], 0
    for lst in ends.values():
        if len(lst) == 2:
            rows.append(lst[0])
            cols.append(lst[1])
        else:
            anomalies += 1
    n = len(road)
    adj = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n))
    n_edges, label = connected_components(adj, directed=False)
    geoms = [None] * n_edges
    members = collections.defaultdict(list)
    for i, lab in enumerate(label):
        members[lab].append(i)
    split = 0
    for lab, idx in members.items():
        if len(idx) == 1:
            geoms[lab] = road.geometry.iloc[idx[0]]
        else:
            m = shapely.line_merge(MultiLineString([road.geometry.iloc[i] for i in idx]))
            if m.geom_type != "LineString":
                split += 1
            geoms[lab] = m
    return geoms, label, anomalies, split


def main():
    t0 = time.time()
    cfg = load_yaml(sys.argv[1] if len(sys.argv) > 1 else "config/13_ring1_ownership.yaml")
    setup_logging(cfg["paths"]["log"])
    crs, dec = cfg["crs_metric"], cfg["coord_match_decimals"]
    tcfg = load_yaml(cfg["paths"]["tiers"])
    tier_of = {h: t for t, hs in tcfg["tiers"].items() for h in hs}
    ovr = tcfg["through_override"]
    checks = []

    def check(name, expected, actual, ok=None):
        checks.append((name, expected, actual, (expected == actual) if ok is None else ok))

    poly_gdf = gpd.read_file(cfg["paths"]["polygons"], layer=cfg["paths"]["polygon_layer"])
    assert poly_gdf.crs.to_epsg() == crs and len(poly_gdf) == 1
    poly = poly_gdf.geometry.iloc[0]
    shapely.prepare(poly)

    fp, mp = cfg["paths"]["features"], cfg["paths"]["membership"]
    ways = gpd.read_file(fp, layer="ways")
    jn = gpd.read_file(fp, layer="junction_nodes")
    tc = gpd.read_file(fp, layer="tram_crossings")
    kbr = gpd.read_file(fp, layer="kbr_points")
    jcm = gpd.read_file(mp, layer="junction_clusters_m")
    scm = gpd.read_file(mp, layer="signal_clusters_m")
    seg = gpd.read_file(mp, layer="segments_m")

    # --- node degrees recomputed from ways; must reproduce the junction_nodes layer ---
    road_ways = ways[ways["highway"].notna()]
    deg = road_degree(road_ways, dec)
    n_deg3 = sum(1 for v in deg.values() if v >= 3)
    cluster_of = {key((x, y), dec): (nid, c) for nid, c, x, y in zip(
        jn["osm_id"], jn["junction_cluster_id"], jn.geometry.x, jn.geometry.y)}
    check("junction_nodes (layer)", cfg["expected"]["junction_nodes"], len(jn))
    check("coordinates with degree >= 3 (recomputed)", len(jn), n_deg3)
    check("junction nodes sharing coordinates", len(jn), len(cluster_of))
    cin = jcm.set_index("junction_cluster_id")["centroid_in"].to_dict()

    # --- fragments -> edges ---
    road = seg[seg["highway"].notna()].reset_index(drop=True)
    tram = seg[seg["highway"].isna() & seg["is_tram"]].reset_index(drop=True)
    check("fragments = road + tram", len(seg), len(road) + len(tram))
    geoms, label, merge_anom, merge_split = merge_chains(road, deg, cluster_of, dec)
    check("deg-2 nodes with other than 2 fragment ends", 0, merge_anom)
    check("merged chains that are not a single LineString", 0, merge_split)
    road["edge"] = label
    g_hw = road.groupby(["edge", "highway"])["length_m"].sum().reset_index()
    g_hw = g_hw.sort_values(["edge", "length_m", "highway"], ascending=[True, False, True])
    main_hw = g_hw.drop_duplicates("edge").set_index("edge")["highway"]
    n_hw = g_hw.groupby("edge").size()
    frag_n = road.groupby("edge").size()
    edges = gpd.GeoDataFrame({
        "edge_id": np.arange(len(geoms)), "highway": main_hw.reindex(range(len(geoms))).to_numpy(),
        "n_highways": n_hw.reindex(range(len(geoms))).to_numpy(),
        "n_fragments": frag_n.reindex(range(len(geoms))).to_numpy(),
    }, geometry=geoms, crs=crs)
    edges["length_m"] = edges.geometry.length
    check("edge km == road fragment km", f"{road['length_m'].sum():.3f}", f"{edges['length_m'].sum():.3f}",
          abs(road["length_m"].sum() - edges["length_m"].sum()) < 1e-3)
    ka = [key(g.coords[0], dec) for g in edges.geometry]
    kb = [key(g.coords[-1], dec) for g in edges.geometry]
    edges["node_a"] = [cluster_of.get(k, (-1, -1))[0] for k in ka]
    edges["node_b"] = [cluster_of.get(k, (-1, -1))[0] for k in kb]
    edges["cluster_a"] = [cluster_of.get(k, (-1, -1))[1] for k in ka]
    edges["cluster_b"] = [cluster_of.get(k, (-1, -1))[1] for k in kb]
    edges["deg_a"] = [deg.get(k, 0) for k in ka]
    edges["deg_b"] = [deg.get(k, 0) for k in kb]
    has_a, has_b = edges["cluster_a"] >= 0, edges["cluster_b"] >= 0
    n_cl = has_a.astype(int) + has_b.astype(int)
    other_deg = np.where(has_a, edges["deg_b"], edges["deg_a"])
    edges["kind0"] = np.select(
        [n_cl == 2, (n_cl == 1) & (other_deg == 1), n_cl == 0],
        ["through", "dead_end_spur", "isolated"], default="unclassified")
    check("edges not classifiable", 0, int((edges["kind0"] == "unclassified").sum()))
    # isolated edges must have both ends of degree 1 (or form a closed ring)
    bad_iso = (edges["kind0"] == "isolated") & ~(
        ((edges["deg_a"] == 1) & (edges["deg_b"] == 1)) | (edges["deg_a"] == edges["deg_b"]) & (edges["deg_a"] == 2))
    check("isolated edges with an end of degree > 2", 0, int(bad_iso.sum()))

    # --- tiers ---
    n_e = len(edges)
    through = edges["kind0"] == "through"
    # first-run rule (reproduction only): tier of the longest fragment, service/path through -> B
    promote_run1 = through & edges["highway"].isin(ovr["classes"])
    edges["tier_run1"] = np.where(promote_run1, ovr["to"], edges["highway"].map(tier_of).fillna("unmapped"))
    # tier_base: HIGHEST tier among the fragments (A > B > C)
    rank = {"A": 0, "B": 1, "C": 2, "unmapped": 3}
    inv = {v: k for k, v in rank.items()}
    road["tier_frag"] = road["highway"].map(tier_of).fillna("unmapped")
    edges["tier_base"] = (road["tier_frag"].map(rank).groupby(road["edge"]).min()
                          .reindex(range(n_e)).map(inv).to_numpy())
    edges["tier_longest"] = edges["highway"].map(tier_of).fillna("unmapped")
    edges["tier_promoted"] = through & edges["highway"].isin(ovr["classes"]) & (edges["tier_base"] == "C")
    edges["tier"] = np.where(edges["tier_promoted"], ovr["to"], edges["tier_base"])
    unmapped = sorted(edges.loc[edges["tier_base"] == "unmapped", "highway"].unique())

    # service tag from the fragments' ways
    assert ways["osm_id"].is_unique
    road["service"] = road["way_id"].map(ways.set_index("osm_id")["service"])
    tagged = road[road["service"].notna()]
    top_tag = (tagged.sort_values(["edge", "length_m", "service"], ascending=[True, False, True])
               .drop_duplicates("edge").set_index("edge")["service"])
    edges["service"] = top_tag.reindex(range(n_e)).to_numpy()
    edges["service_mixed"] = (tagged.groupby("edge")["service"].nunique().reindex(range(n_e)).fillna(0) > 1).to_numpy()
    all_c = tagged.groupby("edge")["service"].apply(lambda s: bool(s.isin(tcfg["service_tag_c"]).all()))
    tag_c = all_c.reindex(range(n_e)).fillna(False).to_numpy(dtype=bool)
    edges["tier_tag"] = np.where(edges["tier_promoted"] & tag_c, "C", edges["tier"])

    # topology of C-base edges (whole extract)
    topo_c = set(tcfg["topology_base"]["c"])
    road["c_frag"] = road["highway"].isin(topo_c)
    edges["c_base"] = road["c_frag"].groupby(road["edge"]).all().reindex(range(n_e)).to_numpy()
    check("promoted edges that are not C-base", 0, int((edges["tier_promoted"] & ~edges["c_base"]).sum()))
    cb = edges[edges["c_base"]]
    ends = pd.concat([cb["node_a"], cb["node_b"]])
    ab_nodes = set(pd.concat([edges.loc[~edges["c_base"], "node_a"], edges.loc[~edges["c_base"], "node_b"]])) - {-1}
    # node index per C edge end (-1 = no node)
    uniq_nodes = pd.Index(sorted(set(ends[ends >= 0])))
    pos = {v: i for i, v in enumerate(uniq_nodes)}
    ia = np.array([pos.get(v, -1) for v in cb["node_a"]])
    ib = np.array([pos.get(v, -1) for v in cb["node_b"]])
    both = (ia >= 0) & (ib >= 0)
    nn = len(uniq_nodes)
    nlab = connected_components(
        coo_matrix((np.ones(both.sum()), (ia[both], ib[both])), shape=(nn, nn)), directed=False)[1]
    comp = np.where(ia >= 0, nlab[np.maximum(ia, 0)], np.where(ib >= 0, nlab[np.maximum(ib, 0)], -1))
    n_lone = int((comp < 0).sum())
    comp[comp < 0] = nlab.max() + 1 + np.arange(n_lone) if nn else np.arange(n_lone)
    is_att = np.array([v in ab_nodes for v in uniq_nodes])
    comp_att = pd.Series(is_att).groupby(nlab).sum()
    att_of = pd.Series(comp).map(comp_att).fillna(0).astype(int).to_numpy()
    edges["c_component_id"] = pd.array([pd.NA] * n_e, dtype="Int64")
    edges["c_component_attachments"] = pd.array([pd.NA] * n_e, dtype="Int64")
    edges["topo_through"] = pd.array([pd.NA] * n_e, dtype="boolean")
    cmask = edges["c_base"].to_numpy()
    edges.loc[cmask, "c_component_id"] = comp
    edges.loc[cmask, "c_component_attachments"] = att_of
    edges.loc[cmask, "topo_through"] = att_of >= cfg["component_min_attachments"]
    edges["tier_topo"] = np.where(
        edges["tier_promoted"] & edges["topo_through"].fillna(False).to_numpy(dtype=bool),
        ovr["to"], edges["tier_base"])

    # ownership (D3 for end-cluster edges, midpoint rule for isolated ones)
    edges["end_a_in"] = edges["cluster_a"].map(lambda c: cin.get(c, False))
    edges["end_b_in"] = edges["cluster_b"].map(lambda c: cin.get(c, False))
    edges["mid"] = shapely.line_interpolate_point(edges.geometry.values, 0.5, normalized=True)
    mid_in = shapely.contains(poly, edges["mid"].values)
    edges["ring1"] = np.where(edges["kind0"] == "isolated", mid_in, edges["end_a_in"] | edges["end_b_in"])
    stub = (edges["kind0"] == "through") & (edges["end_a_in"] ^ edges["end_b_in"])
    edges["boundary_stub"] = stub
    edges["kind"] = np.select(
        [stub & edges["ring1"], edges["kind0"] == "through"],
        ["boundary_stub", "inside_through"], default=edges["kind0"])
    edges.loc[~edges["ring1"], "kind"] = edges.loc[~edges["ring1"], "kind0"].map(
        {"through": "through_outside"}).fillna(edges["kind0"])
    # tram: fragments (OSM ways split at junction nodes were never cut: tram has no clusters)
    tram = tram.assign(edge_id=-1 - np.arange(len(tram)), n_fragments=1, n_highways=0, tier="A",
                       tier_base="A", tier_tag="A", tier_topo="A", tier_promoted=False, kind0="isolated")
    tram["highway"] = "tram"
    tram["mid"] = shapely.line_interpolate_point(tram.geometry.values, 0.5, normalized=True)
    tram["ring1"] = shapely.contains(poly, tram["mid"].values)
    tram["kind"] = np.where(tram["ring1"], "isolated", "isolated_outside")
    tram["boundary_stub"] = False

    inside = edges[edges["ring1"]]
    tram_in = tram[tram["ring1"]]

    # --- reproduction of the first run (hard checks) ---
    ex = cfg["expected_run1"]
    check("repro: edges", ex["edges"], len(edges))
    for k, name in (("inside_through", "inside_through"), ("boundary_stub", "boundary_stub"),
                    ("dead_end_spur", "dead_end_spur")):
        check(f"repro: {name} inside RING 1", ex["segments_inside"][k], int((inside["kind"] == k).sum()))
    check("repro: isolated roads", ex["segments_inside"]["isolated_roads"], int((inside["kind"] == "isolated").sum()))
    check("repro: isolated tram-only", ex["segments_inside"]["isolated_tram"], len(tram_in))
    p1 = edges[edges["ring1"] & promote_run1]
    ep = ex["promoted_inside"]
    for name, sub, en, ekm in (("all", p1, ep["n"], ep["km"]), ("< 30 m", p1[p1["length_m"] < 30], ep["n_lt30"], ep["km_lt30"]),
                               ("> 100 m", p1[p1["length_m"] > 100], ep["n_gt100"], ep["km_gt100"])):
        check(f"repro: promoted inside RING 1, {name}: edges", en, len(sub))
        a = round(float(sub["length_m"].sum()) / 1000, 2)
        check(f"repro: promoted inside RING 1, {name}: km", ekm, a, abs(a - ekm) < 1e-9)

    # --- through-network degree (tier A/B through edges only) per junction node ---
    # Complexity uses the first-run tier (`tier_run1`) so that the unit table stays comparable with run 1;
    # the count under the new `tier` is reported as a side figure.
    def junction_table(tier_col):
        thr = edges[(edges["kind0"] == "through") & edges[tier_col].isin(["A", "B"])]
        nd = collections.Counter(thr["node_a"].tolist() + thr["node_b"].tolist())
        j = jn.assign(deg_ab=jn["osm_id"].map(lambda i: nd.get(i, 0)))
        j["flag_ok"] = j["deg_ab"] >= cfg["complex_min_degree_any"]
        g = j.groupby("junction_cluster_id")
        cagg = pd.DataFrame({
            "max_degree_ab": g["deg_ab"].max(),
            "rb": g.apply(lambda d: bool((d["is_roundabout"] & d["flag_ok"]).any()), include_groups=False),
            "tr": g.apply(lambda d: bool((d["has_tram"] & d["flag_ok"]).any()), include_groups=False),
        })
        return jcm.merge(cagg, left_on="junction_cluster_id", right_index=True, how="left")
    jc = junction_table("tier_run1")
    jc_new = junction_table("tier")
    n_complex_new = int(((jc_new["centroid_in"]) & ((jc_new["max_degree_ab"] >= cfg["complex_min_degree"])
                         | jc_new["rb"] | jc_new["tr"])).sum())
    jc_in = jc[jc["centroid_in"]].copy()
    check("RING 1 junction clusters", cfg["expected"]["ring1_junction_clusters"], len(jc_in))
    check("RING 1 signal clusters", cfg["expected"]["ring1_signal_clusters"], int(scm["centroid_in"].sum()))
    jc_in["complex"] = (jc_in["max_degree_ab"] >= cfg["complex_min_degree"]) | jc_in["rb"] | jc_in["tr"]
    jc_in["reason"] = [
        "+".join(r for r, f in (("deg>=%d" % cfg["complex_min_degree"], d >= cfg["complex_min_degree"]),
                               ("roundabout", rb), ("tram", tr)) if f)
        for d, rb, tr in zip(jc_in["max_degree_ab"], jc_in["rb"], jc_in["tr"])]
    cplx = jc_in[jc_in["complex"]]

    # --- tram crossings ---
    tc_in = tc[shapely.contains(poly, tc.geometry.values)].copy()
    check("RING 1 tram crossings", cfg["expected"]["ring1_tram_crossings"], len(tc_in))
    jn_by_id = jn.set_index("osm_id")
    tc_in["is_junction_node"] = tc_in["osm_id"].isin(jn_by_id.index)
    tc_in["junction_cluster_id"] = tc_in["osm_id"].map(jn_by_id["junction_cluster_id"])
    tc_in["degree"] = tc_in["osm_id"].map(jn_by_id["degree"])

    # --- counters ---
    r1 = kbr[kbr["Kordon"] == cfg["kbr_ring"]].reset_index(drop=True)
    check("KBR %s counters" % cfg["kbr_ring"], cfg["kbr_expected"], len(r1))
    ctree = shapely.STRtree(r1.geometry.values)

    def counter_cols(geoms):
        idx, dist = ctree.query_nearest(np.asarray(geoms), return_distance=True, all_matches=False)
        order = np.argsort(idx[0])
        cid = r1["Pkt_pomiar"].to_numpy()[idx[1][order]]
        d = dist[order]
        ok = d < cfg["counter_nearby_m"]
        return np.where(ok, cid, None), np.where(ok, d, np.nan)

    # --- work units ---
    cols = ["unit_type", "id", "x", "y", "n_nodes", "max_degree", "length_m", "highway", "tier",
            "kind", "mid_block_major", "counter_id", "counter_nearby",
            "tier_base", "tier_tag", "tier_topo", "topo_through", "site_id"]
    parts = []

    def pt_units(df, utype, idcol, extra):
        out = pd.DataFrame({"unit_type": utype, "id": df[idcol].to_numpy(),
                            "x": df.geometry.x.to_numpy(), "y": df.geometry.y.to_numpy()})
        for k, v in extra.items():
            out[k] = v
        cid, cd = counter_cols(df.geometry.values)
        out["counter_id"], out["counter_nearby"] = cid, cd
        return out

    sc_in = scm[scm["centroid_in"]]
    parts.append(pt_units(sc_in, "signal_cluster", "cluster_id", {
        "n_nodes": sc_in["n_nodes"].to_numpy(), "kind": sc_in["kind"].to_numpy(),
        "mid_block_major": sc_in["mid_block_major"].to_numpy()}))
    parts.append(pt_units(cplx, "junction_cluster_complex", "junction_cluster_id", {
        "n_nodes": cplx["n_nodes"].to_numpy(), "max_degree": cplx["max_degree_ab"].to_numpy(),
        "kind": cplx["reason"].to_numpy()}))
    parts.append(pt_units(tc_in, "tram_crossing", "osm_id", {
        "n_nodes": 1, "max_degree": tc_in["degree"].to_numpy(),
        "tier": "A", "kind": np.where(tc_in["is_junction_node"], "junction_node", "plain")}))
    seg_units = pd.concat([
        inside.assign(unit_type="segment", id=inside["edge_id"]),
        tram_in.assign(unit_type="segment", id=tram_in["edge_id"]),
    ], ignore_index=True)
    seg_units = gpd.GeoDataFrame(seg_units, geometry="mid", crs=crs)
    sg = pd.DataFrame({
        "unit_type": "segment", "id": seg_units["id"].to_numpy(),
        "x": seg_units["mid"].x.to_numpy(), "y": seg_units["mid"].y.to_numpy(),
        "length_m": seg_units["length_m"].to_numpy(), "highway": seg_units["highway"].to_numpy(),
        "tier": seg_units["tier"].to_numpy(), "kind": seg_units["kind"].to_numpy(),
        "tier_base": seg_units["tier_base"].to_numpy(), "tier_tag": seg_units["tier_tag"].to_numpy(),
        "tier_topo": seg_units["tier_topo"].to_numpy()})
    sg["topo_through"] = pd.array([pd.NA if pd.isna(v) else bool(v) for v in seg_units["topo_through"]],
                                  dtype="boolean")
    cid, cd = counter_cols(seg_units["geometry"].values)
    sg["counter_id"], sg["counter_nearby"] = cid, cd
    parts.append(sg)
    units = pd.concat(parts, ignore_index=True)
    # --- sites: coinciding signal / complex-junction / tram-crossing units share a site_id ---
    units["site_id"] = pd.array([pd.NA] * len(units), dtype="Int64")
    site_of, site_info = assign_sites(cfg, units, jn, cplx, sc_in, tc_in)
    nodeu = units["unit_type"] != "segment"
    units.loc[nodeu, "site_id"] = [site_of[(t, i)] for t, i in zip(units.loc[nodeu, "unit_type"], units.loc[nodeu, "id"])]
    units = units.reindex(columns=cols)
    units["x"], units["y"] = units["x"].round(2), units["y"].round(2)
    units["length_m"] = units["length_m"].round(2)
    units[["n_nodes", "max_degree"]] = units[["n_nodes", "max_degree"]].astype("Int64")
    units["counter_nearby"] = units["counter_nearby"].round(1)
    units = units.sort_values(["unit_type", "id"], kind="stable").reset_index(drop=True)
    check("work units: segments = RING 1 edges + tram fragments", len(inside) + len(tram_in),
          int((units["unit_type"] == "segment").sum()))
    check("units with duplicate (unit_type, id)", 0, int(units.duplicated(["unit_type", "id"]).sum()))
    check("repro: work units", ex["units"], len(units))

    # --- console summary ---
    print(md_table(["Check", "Expected", "Actual", "Result"],
                   [(n, e, a, "PASS" if ok else "FAIL") for n, e, a, ok in checks]))
    if not all(ok for *_, ok in checks):
        log.error("hard check failed; no outputs written")
        sys.exit(1)
    if unmapped:
        log.warning("highway classes without a tier: %s", unmapped)

    # --- outputs ---
    out = pathlib.Path(cfg["paths"]["output_gpkg"])
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()
    e_out = edges.drop(columns=["mid", "c_base"]).assign(kind_raw=edges["kind0"]).drop(columns=["kind0"])
    e_out.to_file(out, layer="edges", driver="GPKG")
    t_out = tram.drop(columns=["mid", "kind0"])
    t_out.to_file(out, layer="tram_segments", driver="GPKG")
    seg_t = seg.copy()
    seg_t["edge_id"] = -1
    seg_t.loc[seg_t["highway"].notna(), "edge_id"] = label
    seg_t["tier"] = seg_t["highway"].map(tier_of).fillna("unmapped")
    seg_t.loc[seg_t["highway"].isna() & seg_t["is_tram"], "tier"] = "A"
    seg_t.to_file(out, layer="segments", driver="GPKG")
    units.to_csv(cfg["paths"]["output_csv"], index=False)

    L = write_report(cfg, tcfg, checks, seg, road, edges, tram, inside, tram_in, units, jc_in, cplx,
                     sc_in, tc_in, jc, unmapped, deg, r1, poly, t0, len(tc))
    L += followup_sections(cfg, tcfg, edges, road, tram_in, inside, units, site_info, n_complex_new,
                           len(cplx), p1, promote_run1)
    L.append(f"\nRun time: {time.time() - t0:.1f} s.")
    pathlib.Path(cfg["paths"]["report"]).write_text("\n".join(L) + "\n", encoding="utf-8")

    fpr = {
        "units": units.groupby("unit_type").size().to_dict(),
        "inside_km": {k: round(float(inside.loc[inside["kind"] == k, "length_m"].sum()), 2) for k in KINDS},
        "edges": len(edges), "tram_in": len(tram_in), "sites": site_info["n_sites"],
        "promoted_in": int(inside["tier_promoted"].sum()),
        "tier_km": {v: {t: round(float(inside.loc[inside[v] == t, "length_m"].sum()), 2) for t in "ABC"}
                    for v in ("tier", "tier_tag", "tier_topo")},
        "tram_km": round(float(tram_in["length_m"].sum()), 2),
    }
    print("FINGERPRINT", json.dumps(fpr, sort_keys=True))
    log.info("done in %.1f s", time.time() - t0)


def assign_sites(cfg, units, jn, cplx, sc_in, tc_in):
    """Union signal clusters / complex junction clusters / tram crossings closer than site_radius_m.

    A signal cluster joins a complex junction cluster if its centroid is within the radius of the cluster
    centroid or of any member node; a tram crossing joins a complex junction cluster the same way.
    """
    from scipy.spatial import cKDTree
    r = cfg["site_radius_m"]
    cids = cplx["junction_cluster_id"].to_numpy()
    nodes = jn[jn["junction_cluster_id"].isin(set(cids))]
    pts = np.vstack([np.column_stack([cplx.geometry.x, cplx.geometry.y]),
                     np.column_stack([nodes.geometry.x, nodes.geometry.y])])
    owner = np.concatenate([cids, nodes["junction_cluster_id"].to_numpy()])
    tree = cKDTree(pts)
    parent = {}

    def find(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)   # deterministic root: the smaller key

    for t, i in zip(units["unit_type"], units["id"]):
        if t != "segment":
            find((t, int(i)))
    near = {}
    for name, df, idc in (("signal_cluster", sc_in, "cluster_id"), ("tram_crossing", tc_in, "osm_id")):
        hits = tree.query_ball_point(np.column_stack([df.geometry.x, df.geometry.y]), r)
        for i, h in zip(df[idc], hits):
            cl = sorted(set(owner[h].tolist()))
            near[(name, int(i))] = cl
            for c in cl:
                union((name, int(i)), ("junction_cluster_complex", int(c)))
    keys = sorted(parent)
    num, site_of = {}, {}
    for k in keys:
        root = find(k)
        if root not in num:
            num[root] = len(num) + 1
        site_of[k] = num[root]
    comp = collections.defaultdict(set)
    for k in keys:
        comp[site_of[k]].add(k[0])
    short = {"signal_cluster": "signal", "junction_cluster_complex": "complex", "tram_crossing": "tram"}
    combos = collections.Counter("+".join(short[t] for t in sorted(v, key=lambda x: list(short).index(x)))
                                 for v in comp.values())
    n_cluster_multi = sum(1 for k, v in near.items() if len(v) > 1)
    # tram crossings left standalone but within the radius of a signal cluster (informational)
    sig_tree = cKDTree(np.column_stack([sc_in.geometry.x, sc_in.geometry.y]))
    tram_alone = [k for k in keys if k[0] == "tram_crossing" and len(comp[site_of[k]]) == 1]
    tdf = tc_in.set_index("osm_id").loc[[k[1] for k in tram_alone]]
    d = sig_tree.query(np.column_stack([tdf.geometry.x, tdf.geometry.y]))[0] if len(tdf) else np.array([])
    return site_of, {"n_sites": len(comp), "combos": combos, "multi_link": n_cluster_multi,
                     "alone_near_signal": int((d <= r).sum()), "n_alone_tram": len(tram_alone)}


def stats(d):
    if len(d) == 0:
        return (0, "0.00", "-", "-")
    return (len(d), km(d["length_m"].sum()), f"{d['length_m'].median():.1f}",
            f"{np.percentile(d['length_m'], 90):.1f}")


def kind_table(inside, tram_in):
    rows = []
    for k in KINDS:
        e = inside[inside["kind"] == k]
        if k == "isolated":
            rows.append(("isolated, roads", len(e), km(e["length_m"].sum())))
            rows.append(("isolated, tram-only ways", len(tram_in), km(tram_in["length_m"].sum())))
            rows.append(("**isolated, total**", len(e) + len(tram_in),
                         km(e["length_m"].sum() + tram_in["length_m"].sum())))
        else:
            rows.append((k, len(e), km(e["length_m"].sum())))
    n = len(inside) + len(tram_in)
    m = inside["length_m"].sum() + tram_in["length_m"].sum()
    rows.append(("**all segments in RING 1**", n, km(m)))
    return rows


def followup_sections(cfg, tcfg, edges, road, tram_in, inside, units, site_info, n_complex_new,
                      n_complex_run1, p1, promote_run1):
    ovr = tcfg["through_override"]
    VARS = ("tier", "tier_tag", "tier_topo")
    L = ["\n# Follow-up: tier variants for decision D4\n"]
    L.append("Analysis only; `tier`, `tier_tag` and `tier_topo` are reported side by side and none is chosen. "
             "Counts are edges unless stated; 'inside' = RING 1 (D3 / midpoint rule as above).\n")
    L.append("**Edge definition.** An edge is a maximal chain of way fragments between junction nodes "
             "(degree >= 3) and dead ends (degree 1); fragments are merged across degree-2 nodes. "
             "`mixed_class` is `n_highways > 1` (no separate column).\n")
    L.append("Variants: `tier_base` = highest tier among an edge's fragments (A > B > C) from the class lists, "
             "no override. `tier` = `tier_base`, except `tier_promoted` edges (a `through` edge whose longest-"
             f"fragment class is {'/'.join(ovr['classes'])} and `tier_base` is C) become {ovr['to']}. "
             f"`tier_tag` = `tier`, but a promoted edge whose tagged fragments all have `service` in "
             f"{{{', '.join(tcfg['service_tag_c'])}}} is C. `tier_topo` = `tier_base`, but a promoted edge "
             f"with `topo_through` is {ovr['to']} (promoted edges without it stay C).\n")

    # ---- item 0
    L.append("## Reproduction of run 1\n")
    L.append("All `repro:` rows of the Checks table pass (edges, segments by kind, work units, and the "
             "promoted-edge figures computed with the run-1 rule: longest-fragment class, service/path "
             "`through` -> B). The new `tier_base` rule can change which edges are promoted; the figures below use it.\n")
    L.append(f"Promoted inside RING 1: run-1 rule {len(p1)} edges / {km(p1['length_m'].sum())} km; "
             f"new `tier_promoted` {int(inside['tier_promoted'].sum())} edges / "
             f"{km(inside.loc[inside['tier_promoted'], 'length_m'].sum())} km. "
             f"Complex junction clusters (units are built on the run-1 tier): {n_complex_run1}; under the new `tier`: "
             f"{n_complex_new}.\n")

    # ---- item 2
    L.append("## 2. Mixed-class edges\n")
    mixed = edges["n_highways"] > 1
    chg = mixed & (edges["tier_longest"] != edges["tier_base"])
    rows = []
    for name, m in (("RING 1-3", slice(None)), ("RING 1", edges["ring1"])):
        e = edges[m] if not isinstance(m, slice) else edges
        mx, ch = e[e["n_highways"] > 1], e[(e["n_highways"] > 1) & (e["tier_longest"] != e["tier_base"])]
        rows.append((name, len(mx), km(mx["length_m"].sum()), len(ch), km(ch["length_m"].sum())))
    L.append(md_table(["scope", "mixed edges", "km", "change base tier (longest -> highest)", "km"], rows))
    ct = pd.crosstab(edges.loc[chg, "tier_longest"], edges.loc[chg, "tier_base"])
    L.append("\nEdges that change base tier, RING 1-3 (rows: longest-fragment tier, columns: highest tier):\n")
    L.append(md_table(["longest \\ highest"] + list(ct.columns), [(i, *r) for i, r in ct.iterrows()]))

    # ---- item 3
    L.append("\n## 3. Service tag and `tier_tag`\n")
    moved = edges["tier_promoted"] & (edges["tier"] == "B") & (edges["tier_tag"] == "C")
    sp = edges["highway"].isin(ovr["classes"])
    rows = []
    for name, m in (("RING 1-3", edges["ring1"] | True), ("RING 1", edges["ring1"])):
        rows.append((name, "promoted edges", int((m & edges["tier_promoted"]).sum()),
                     km(edges.loc[m & edges["tier_promoted"], "length_m"].sum())))
        rows.append((name, "moved B -> C by `tier_tag`", int((m & moved).sum()), km(edges.loc[m & moved, "length_m"].sum())))
        for lab, sel in (("service/path edges without `service` tag", sp & edges["service"].isna()),
                         ("... of which promoted", sp & edges["service"].isna() & edges["tier_promoted"]),
                         ("service/path edges, all", sp), ("edges with `service_mixed`", edges["service_mixed"])):
            rows.append((name, lab, int((m & sel).sum()), km(edges.loc[m & sel, "length_m"].sum())))
    L.append(md_table(["scope", "measure", "edges", "km"], rows))

    # ---- item 4
    L.append("\n## 4. Topology of C-base edges\n")
    L.append("C-base edge: all fragments in the C-base list (service, track, path, footway, pedestrian); all "
             "other edges are A/B-base. Components connect C-base edges sharing an end junction node over the "
             "whole extract. An attachment node is a junction node where a C-base edge and an A/B-base edge both "
             "end (tram ways are separate segments and are not part of this graph). `topo_through` = component "
             "has >= 2 distinct attachment nodes.\n")
    cb = edges[edges["c_base"]].copy()
    cb["att"] = cb["c_component_attachments"].astype(int)
    cb["cid"] = cb["c_component_id"].astype(int)
    comp = cb.groupby("cid").agg(n_edges=("edge_id", "size"), m=("length_m", "sum"), att=("att", "first"),
                                 n_in=("ring1", "sum"),
                                 m_in=("length_m", lambda s: s[cb.loc[s.index, "ring1"]].sum()),
                                 n_prom_in=("tier_promoted", lambda s: (s & cb.loc[s.index, "ring1"]).sum()))
    cb["mx"], cb["my"] = shapely.get_x(cb["mid"].values), shapely.get_y(cb["mid"].values)
    mx = cb[cb["ring1"]].groupby("cid").agg(x=("mx", "mean"), y=("my", "mean"))
    comp = comp.join(mx)
    rows = []
    for lab, sel in (("0 attachments", comp["att"] == 0), ("1 attachment", comp["att"] == 1),
                     (">= 2 attachments", comp["att"] >= 2)):
        c = comp[sel]
        rows.append((lab, len(c), int(c["n_edges"].sum()), km(c["m"].sum()), int(c["n_in"].sum()), km(c["m_in"].sum())))
    L.append("C-base components in the extract:\n")
    L.append(md_table(["component class", "components", "edges", "km", "edges inside RING 1", "km inside RING 1"], rows))

    pin = inside[inside["tier_promoted"]]
    L.append("\nPromoted edges inside RING 1 that stay in tier B under each variant, split by `topo_through` "
             "(length_m median / p90 in metres):\n")
    rows = []
    for v in VARS:
        kept = pin[pin[v] == "B"]
        for lab, d in (("kept B, topo_through = true", kept[kept["topo_through"].fillna(False).astype(bool)]),
                       ("kept B, topo_through = false", kept[~kept["topo_through"].fillna(False).astype(bool)]),
                       ("**kept B, total**", kept), ("moved to C", pin[pin[v] != "B"])):
            rows.append((v, lab, *stats(d)))
    L.append(md_table(["variant", "set", "edges", "km", "median m", "p90 m"], rows))

    def ll(df):
        g = gpd.GeoSeries(gpd.points_from_xy(df["x"], df["y"]), crs=cfg["crs_metric"]).to_crs(4326)
        return g.x.to_numpy(), g.y.to_numpy()
    tt = comp[(comp["att"] >= cfg["component_min_attachments"]) & (comp["n_in"] > 0)].copy()
    tt["lon"], tt["lat"] = ll(tt)
    hdr = ["component", "lon", "lat", "edges inside / total", "km inside / total", "attachments", "promoted edges inside"]

    def comp_rows(d):
        return [(i, f"{r.lon:.5f}", f"{r.lat:.5f}", f"{int(r.n_in)} / {int(r.n_edges)}",
                 f"{r.m_in / 1000:.2f} / {r.m / 1000:.2f}", int(r.att), int(r.n_prom_in)) for i, r in d.iterrows()]
    L.append(f"\n{cfg['top_components']} largest `topo_through` components touching RING 1 "
             "(by km inside RING 1; lon/lat = mean of the inside edges' midpoints):\n")
    L.append(md_table(hdr, comp_rows(tt.sort_values(["m_in", "m"], ascending=False).head(cfg["top_components"]))))
    big = tt[tt["m"] > cfg["component_list_min_km"] * 1000].sort_values("m", ascending=False)
    L.append(f"\nEvery component > {cfg['component_list_min_km']} km with >= {cfg['component_min_attachments']} "
             f"attachments that touches RING 1 ({len(big)} of {int(((comp['att'] >= 2) & (comp['m'] > 1000)).sum())} "
             "in the extract; a parking lot with two entrances counts as through):\n")
    L.append(md_table(hdr, comp_rows(big)))

    # ---- item 5
    ti = pd.concat([inside, tram_in.assign(service=None)])[
        ["highway", "kind", "length_m", "tier", "tier_tag", "tier_topo", "service", "tier_promoted"]]
    L.append("\n## 5. Report tables (RING 1)\n")
    L.append("### (a) highway x kind: edges / km\n")
    pv_n = ti.pivot_table(index="highway", columns="kind", values="length_m", aggfunc="size", fill_value=0)
    pv_k = ti.pivot_table(index="highway", columns="kind", values="length_m", aggfunc="sum", fill_value=0)
    order = pv_k.sum(axis=1).sort_values(ascending=False).index
    rows = []
    for h in order:
        rows.append((h, *[f"{pv_n.loc[h].get(k, 0)} / {km(pv_k.loc[h].get(k, 0))}" for k in KINDS],
                     f"{pv_n.loc[h].sum()} / {km(pv_k.loc[h].sum())}"))
    rows.append(("**total**", *[f"{pv_n[k].sum() if k in pv_n else 0} / {km(pv_k[k].sum() if k in pv_k else 0)}" for k in KINDS],
                 f"{pv_n.values.sum()} / {km(pv_k.values.sum())}"))
    L.append(md_table(["highway"] + KINDS + ["total"], rows))

    sv = ti[ti["highway"] == "service"]
    top = sv[sv["service"].notna()].groupby("service")["length_m"].sum().sort_values(ascending=False)
    top_vals = list(top.index[:cfg["service_top_n"]])
    ti = ti.assign(label=np.where(
        ti["highway"] != "service", ti["highway"],
        np.where(ti["service"].isna(), "service / untagged",
                 np.where(ti["service"].isin(top_vals), "service / " + ti["service"].astype(str), "service / other"))))
    srv_order = ["service / " + v for v in top_vals] + ["service / other", "service / untagged"]
    lab_order = []
    for h in order:
        if h == "service":
            lab_order += ["service (all)"] + srv_order
        else:
            lab_order.append(h)
    L.append("\n### (b) km by tier variant x highway (service split by `service` value; top "
             f"{cfg['service_top_n']} by km)\n")
    for v in VARS:
        pv = ti.pivot_table(index="label", columns=v, values="length_m", aggfunc="sum", fill_value=0)
        for t in "ABC":
            if t not in pv:
                pv[t] = 0.0
        pv = pv[["A", "B", "C"]]
        rows = []
        for lab in lab_order:
            if lab == "service (all)":
                r = pv.loc[[i for i in pv.index if i.startswith("service /")]].sum()
            elif lab in pv.index:
                r = pv.loc[lab]
            else:
                continue
            rows.append((lab, km(r["A"]), km(r["B"]), km(r["C"]), km(r.sum())))
        tot = pv.sum()
        rows.append(("**total**", km(tot["A"]), km(tot["B"]), km(tot["C"]), km(tot.sum())))
        L.append(f"\n`{v}` (km):\n")
        L.append(md_table(["highway", "A", "B", "C", "total"], rows))

    L.append("\n### (c) composition of tier B (share of tier-B km)\n")
    cats = ["residential", "living_street", "unclassified", "service-through", "path-through", "other"]
    rows = []
    for v in VARS:
        b = ti[ti[v] == "B"]
        cat = np.select([b["highway"].isin(["residential", "living_street", "unclassified"]) & ~b["tier_promoted"],
                         b["tier_promoted"] & (b["highway"] == "service"),
                         b["tier_promoted"] & (b["highway"] == "path")],
                        [b["highway"], "service-through", "path-through"], default="other")
        s_ = b.groupby(cat)["length_m"].sum()
        tot = s_.sum()
        rows.append((v, km(tot), *[f"{100 * s_.get(c, 0) / tot:.1f}%" for c in cats]))
    L.append(md_table(["variant", "tier B km"] + cats, rows))

    L.append("\n### (d) promoted edges by length bucket (`tier_promoted`, RING 1)\n")
    lo, hi = cfg["length_buckets_m"]
    rows = []
    for lab, d in ((f"< {lo} m", pin[pin["length_m"] < lo]),
                   (f"{lo}-{hi} m", pin[(pin["length_m"] >= lo) & (pin["length_m"] <= hi)]),
                   (f"> {hi} m", pin[pin["length_m"] > hi]), ("**all promoted**", pin)):
        rows.append((lab, *stats(d)))
    L.append(md_table(["bucket", "edges", "km", "median m", "p90 m"], rows))

    # ---- item 6
    L.append("\n## 6. Sites\n")
    L.append(f"`site_id` joins a signal cluster to a complex junction cluster if the signal centroid is within "
             f"{cfg['site_radius_m']} m (`[PROPOSED]`) of the junction cluster centroid or of any of its member nodes, "
             "and a tram crossing to a complex junction cluster by the same distance rule; groups are merged "
             "transitively. Segments have no `site_id`.\n")
    cmb = site_info["combos"]
    rows = sorted(cmb.items(), key=lambda kv: -kv[1])
    L.append(md_table(["site composition", "sites"], rows + [("**distinct sites**", site_info["n_sites"])]))
    with_tram = sum(v for k, v in cmb.items() if "tram" in k)
    nodeu = units[units["unit_type"] != "segment"]
    L.append(f"\nSites with a tram crossing: {with_tram}. Node units: {len(nodeu)} -> {site_info['n_sites']} sites "
             f"({len(nodeu) - site_info['n_sites']} units merged). Signal or tram units linked to more than one "
             f"complex cluster: {site_info['multi_link']}. Standalone tram crossings: {site_info['n_alone_tram']} "
             f"({site_info['alone_near_signal']} of them within {cfg['site_radius_m']} m of a signal cluster, "
             "not merged because the rule joins tram crossings to junction clusters only).")

    # ---- item 7
    Z = cfg["zones"]
    L.append(f"\n## 7. Zone-size arithmetic (RING 1 / {Z})\n")
    nseg = int((units["unit_type"] == "segment").sum())
    rows = [("total work units", len(units), f"{len(units) / Z:.1f}"),
            ("distinct sites (node units merged)", site_info["n_sites"], f"{site_info['n_sites'] / Z:.1f}"),
            ("segment units", nseg, f"{nseg / Z:.1f}"),
            ("sites + segments", site_info["n_sites"] + nseg, f"{(site_info['n_sites'] + nseg) / Z:.1f}")]
    L.append(md_table(["measure", "RING 1", f"per zone (/{Z})"], rows))
    L.append("\nSegment km by tier variant (RING 1 incl. tram, which is tier A):\n")
    rows = []
    for v in VARS:
        k_ = ti.groupby(v)["length_m"].sum()
        rows.append((v, *[f"{k_.get(t, 0) / 1000:.1f} ({k_.get(t, 0) / 1000 / Z:.1f})" for t in "ABC"],
                     f"{k_.sum() / 1000:.1f} ({k_.sum() / 1000 / Z:.1f})"))
    L.append(md_table(["variant", "A km (per zone)", "B km (per zone)", "C km (per zone)", "total km (per zone)"], rows))
    return L


def write_report(cfg, tcfg, checks, seg, road, edges, tram, inside, tram_in, units, jc_in, cplx,
                 sc_in, tc_in, jc, unmapped, deg, r1, poly, t0, n_tc_total):
    L = ["# Task 01c: RING 1 ownership layer and work-unit table\n"]
    L.append(f"Input: `{cfg['paths']['features']}`, `{cfg['paths']['membership']}`, polygon "
             f"`{cfg['paths']['polygons']}`. Rule: D3 (`centroid_in`) for segments with an end cluster, "
             "midpoint-in-polygon for segments without one. Read-only analysis; tiers are `[PROPOSED]` "
             f"(`{cfg['paths']['tiers']}`). Outputs: `{cfg['paths']['output_csv']}`, "
             f"`{cfg['paths']['output_gpkg']}` (layers `edges`, `tram_segments`, `segments`).\n")
    L.append("## Checks\n")
    L.append(md_table(["Check", "Expected", "Actual", "Result"],
                      [(n, e, a, "PASS" if ok else "FAIL") for n, e, a, ok in checks]))

    # fragment end census
    L.append("\n## Segment definition: fragments vs edges\n")
    L.append("The 01b `segments_m` layer cuts ways only at junction nodes, but OSM ways are also split where "
             "tags change, so most fragment ends are *degree-2 continuation nodes*, not dead ends. "
             "To classify dead ends at all, road fragments were merged across degree-2 nodes (no junction "
             "cluster, degree exactly 2) into **edges**. All counts below are edges unless stated.\n")
    ka = [key(g.coords[0], cfg["coord_match_decimals"]) for g in road.geometry]
    kb = [key(g.coords[-1], cfg["coord_match_decimals"]) for g in road.geometry]
    ends = pd.Series([deg.get(k, 0) for k in ka + kb])
    has_cl = pd.concat([road["cluster_a"] >= 0, road["cluster_b"] >= 0], ignore_index=True)
    cens = [("junction cluster (degree >= 3)", int(has_cl.sum())),
            ("degree 1 (true dead end)", int((~has_cl & (ends == 1)).sum())),
            ("degree 2 (continuation to another way)", int((~has_cl & (ends == 2)).sum()))]
    L.append("Road fragment ends (2 per fragment):\n")
    L.append(md_table(["end type", "count"], cens + [("**total**", 2 * len(road))]))
    L.append(f"\nRoad fragments: {len(road)} -> edges: {len(edges)} "
             f"({int((edges['n_highways'] > 1).sum())} edges mix more than one `highway` value; the edge "
             "takes the class with most length). Tram-only ways are not merged (they have no junction "
             f"nodes; {len(tram)} ways, each a segment).\n")

    L.append("\n## 1-2. Segments in RING 1 by kind\n")
    L.append("`inside_through`: both end clusters inside. `boundary_stub`: through segment with exactly one "
             "end cluster inside. `dead_end_spur`: one end cluster (inside), other end degree 1. "
             "`isolated`: no end cluster, midpoint inside the polygon.\n")
    L.append(md_table(["kind", "segments", "km"], kind_table(inside, tram_in)))
    L.append("\nAll edges in RING 1-3 for context (inside + outside):\n")
    allk = edges.groupby("kind0").agg(n=("edge_id", "size"), m=("length_m", "sum"))
    allk.loc["isolated (tram-only ways)"] = [len(tram), tram["length_m"].sum()]
    L.append(md_table(["kind", "segments", "km"], [(k, int(r.n), km(r.m)) for k, r in allk.iterrows()]))

    L.append("\n## 3. Tram\n")
    tcl = tc_in
    L.append(md_table(["measure", "value"], [
        ("tram segments (ways) in RING 1, midpoint rule", f"{len(tram_in)} of {len(tram)}"),
        ("tram track km in RING 1, midpoint rule", f"{km(tram_in['length_m'].sum())} km "
                                                  f"(of {km(tram['length_m'].sum())} km in RING 1-3)"),
        ("tram_crossings in RING 1 (point in polygon)", f"{len(tcl)} of {n_tc_total}"),
        ("... also junction nodes with degree >= 3", int(tcl["is_junction_node"].sum())),
        ("... of those, in a junction cluster flagged complex",
         int(tcl["junction_cluster_id"].isin(cplx["junction_cluster_id"]).sum()))]))

    L.append("\n## 4. Tiers\n")
    L.append("All `[PROPOSED]`:\n")
    L.append(md_table(["tier", "highway classes"],
                      [(t, ", ".join(h)) for t, h in tcfg["tiers"].items()]))
    L.append(f"\nOverride: a `through` edge of class {', '.join(tcfg['through_override']['classes'])} "
             f"is promoted to tier {tcfg['through_override']['to']} "
             f"({int(edges['tier_promoted'].sum())} edges in RING 1-3, "
             f"{int(inside['tier_promoted'].sum())} in RING 1).")
    if unmapped:
        L.append(f"\n**Highway classes without a tier: {', '.join(unmapped)}** "
                 f"(kept as `unmapped`; in RING 1: "
                 f"{int((inside['tier'] == 'unmapped').sum())} edges, "
                 f"{km(inside.loc[inside['tier'] == 'unmapped', 'length_m'].sum())} km).")
    allin = pd.concat([inside[["tier", "kind", "length_m"]],
                       tram_in.assign(kind="isolated")[["tier", "kind", "length_m"]]])
    for what, fn in (("km", lambda d: km(d["length_m"].sum())), ("segments", lambda d: len(d))):
        L.append(f"\nTier x kind in RING 1 ({what}; tram counted in tier A, `isolated`):\n")
        rows = []
        for t in TIERS:
            d = allin[allin["tier"] == t]
            if d.empty and t == "unmapped":
                continue
            rows.append((t, *[fn(d[d["kind"] == k]) for k in KINDS], fn(d)))
        rows.append(("**total**", *[fn(allin[allin["kind"] == k]) for k in KINDS], fn(allin)))
        L.append(md_table(["tier"] + KINDS + ["total"], rows))

    L.append("\n## 5-6. Work units in RING 1\n")
    sg = units[units["unit_type"] == "segment"]
    rows = []
    for ut in ("signal_cluster", "junction_cluster_complex", "tram_crossing"):
        rows.append((ut, "-", int((units["unit_type"] == ut).sum()), "-"))
    for t in TIERS:
        d = sg[sg["tier"] == t]
        if len(d):
            rows.append(("segment", t, len(d), km(d["length_m"].sum())))
    rows.append(("**total units**", "", len(units), km(sg["length_m"].sum())))
    L.append(md_table(["unit_type", "tier", "units", "km"], rows))
    L.append(f"\n`counter_nearby` is filled for {int(units['counter_nearby'].notna().sum())} units "
             f"(R1 counter within {cfg['counter_nearby_m']} m); {units.loc[units['counter_nearby'].notna(), 'counter_id'].nunique()} "
             f"of {len(r1)} counters have at least one unit nearby.\n")
    L.append("Segment units by kind (rows of the CSV with `unit_type = segment`):\n")
    L.append(md_table(["kind", "units", "km"],
                      [(k, len(d), km(d["length_m"].sum())) for k, d in sg.groupby("kind")]))

    L.append("\n### Junction clusters in RING 1\n")
    d4 = cfg["complex_min_degree"]
    L.append(f"{len(jc_in)} junction clusters have `centroid_in`; **{len(cplx)}** are complex. "
             f"Degree is recomputed from through edges of tier A/B only (`max_degree_ab`).\n")
    reasons = collections.Counter()
    for r in cplx["reason"]:
        reasons[r] += 1
    L.append(md_table(["reason (any of deg>=%d, roundabout, tram)" % d4, "clusters"],
                      sorted(reasons.items(), key=lambda kv: -kv[1])))
    vc = jc_in["max_degree_ab"].clip(upper=5).value_counts().sort_index()
    L.append("\nAll RING 1 junction clusters by `max_degree_ab` (original `max_degree` in brackets for 4+):\n")
    L.append(md_table(["max_degree_ab", "clusters"], [(("5+" if k == 5 else k), v) for k, v in vc.items()]
                      + [("original max_degree >= 4", int((jc_in["max_degree"] >= 4).sum()))]))

    L.append("\n## Columns of `ring1_work_units.csv`\n")
    L.append(md_table(["column", "definition"], [
        ("unit_type", "`signal_cluster`, `junction_cluster_complex`, `tram_crossing` or `segment`"),
        ("id", "`cluster_id` (signal), `junction_cluster_id` (junction), OSM node id (tram crossing), "
               "`edge_id` of the `edges` layer (road segment) or negative index into `tram_segments` (tram); unique within `unit_type`"),
        ("x, y", "centroid in EPSG:2177 [m]; for segments the point at half the length"),
        ("n_nodes", "member nodes of the cluster (1 for a tram crossing); empty for segments"),
        ("max_degree", "junction: max over member nodes of the number of through edges of tier A/B ending there "
                       "(`max_degree_ab`); tram crossing: OSM degree if it is a junction node; empty otherwise"),
        ("length_m", "segments only: edge length [m]"),
        ("highway", "segments only: `highway` of the longest fragment; `tram` for tram"),
        ("tier", "A/B/C/unmapped for segments (see tiers); `A` for tram crossings; empty for clusters"),
        ("kind", "signal: `junction` or `crossing_only`; junction: reason for complex "
                 f"(`deg>={d4}`, `roundabout`, `tram`); tram crossing: `junction_node` or `plain`; "
                 "segment: `inside_through`, `boundary_stub`, `dead_end_spur`, `isolated`"),
        ("mid_block_major", "signal clusters only: no junction node of a major-class way within 25 m "
                            "(`mid_block_major` from task 01 is present and used; plain `mid_block` is not exported)"),
        ("counter_id", "nearest R1 counter if closer than the threshold"),
        ("counter_nearby", f"distance [m] from the unit geometry (point, or the whole segment line) to "
                           f"that counter, only if < {cfg['counter_nearby_m']} m; empty otherwise"),
        ("tier_base, tier_tag, tier_topo", "segments: tier variants (see the follow-up section); `tier` is the "
                                           "base tier with the service/path through override; tram is A in all"),
        ("topo_through", "segments: C-base edges only; their C-component has >= 2 attachment nodes"),
        ("site_id", f"signal clusters, complex junction clusters and tram crossings closer than "
                    f"{cfg['site_radius_m']} m (`[PROPOSED]`) share an id; empty for segments")]))
    L.append("\nComplex junction cluster: `max_degree_ab >= %d`, or a roundabout node, or a tram node, where the "
             "roundabout/tram flags count only on member nodes with `max_degree_ab >= %d` and the degree counts "
             "only `through` edges of tier A or B (after the service/path override)."
             % (d4, cfg["complex_min_degree_any"]))
    L.append("\nUnits overlap by design: a tram crossing may sit inside a signal or junction cluster, and "
             "segments are separate from nodes. Overlap is not removed here.")
    return L


if __name__ == "__main__":
    main()
