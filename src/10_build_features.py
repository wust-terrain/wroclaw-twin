"""Task 01: build OSM feature layers for the RING 1-3 area (GeoPackage + report).

Usage: uv run python src/10_build_features.py [config/10_build_features.yaml]
"""
import logging
import pathlib
import sys
import time
import xml.etree.ElementTree as ET

import geopandas as gpd
import numpy as np
import osmium
import pandas as pd
import pyproj
import yaml
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree
from shapely.geometry import LineString, Point

log = logging.getLogger("features")


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


def cluster(xy, eps):
    """Single-linkage clustering; returns integer labels (0..k-1) in input order."""
    n = len(xy)
    if n == 0:
        return np.zeros(0, dtype=int)
    pairs = cKDTree(xy).query_pairs(eps, output_type="ndarray")
    graph = coo_matrix((np.ones(len(pairs)), (pairs[:, 0], pairs[:, 1])), shape=(n, n))
    return connected_components(graph, directed=False)[1]


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def classify_way(tags, scope):
    """Return (is_road, is_tram, is_other_rail) according to scope.yaml."""
    hw = tags.get("highway")
    rw = tags.get("railway")
    is_road = False
    if hw is not None and hw not in scope["highway_exclude"]:
        rule = scope["highway_if_bicycle_allowed"]
        if hw in scope["highway_include"]:
            is_road = True
        elif hw in rule["types"] and tags.get("bicycle") in rule["bicycle_values"]:
            is_road = True
    is_tram = rw in scope["railway_include"]
    is_other_rail = rw is not None and not is_tram and not scope["rail_in_scope"]
    return is_road, is_tram, is_other_rail


def read_osm(path, scope):
    """Single pass over the extract: signal nodes, in-scope ways and their node refs."""
    signal_rows = []
    sig_ids = set()
    sig_way_hits = {}  # signal node id -> [(highway, in_scope_road)] over all highway ways
    ways = []
    fp = osmium.FileProcessor(path, osmium.osm.NODE | osmium.osm.WAY).with_locations()
    for o in fp:
        if o.is_node():
            if not o.tags:
                continue
            hw = o.tags.get("highway")
            if hw == "traffic_signals":
                kind = "junction_signal"
            elif hw == "crossing" and o.tags.get("crossing") == "traffic_signals":
                kind = "crossing_signal"
            else:
                continue
            signal_rows.append(
                (o.id, kind, o.tags.get("bicycle"), o.location.lon, o.location.lat)
            )
            sig_ids.add(o.id)
        elif o.is_way():
            tags = {t.k: t.v for t in o.tags}
            is_road, is_tram, is_other_rail = classify_way(tags, scope)
            if tags.get("highway") is not None:
                for n in o.nodes:
                    if n.ref in sig_ids:
                        sig_way_hits.setdefault(n.ref, []).append((tags["highway"], is_road))
            if not (is_road or is_tram or is_other_rail):
                continue
            nodes = [(n.ref, n.lon, n.lat) for n in o.nodes]
            if len(nodes) < 2:
                continue
            ways.append((o.id, tags, nodes, is_road, is_tram, is_other_rail))
    return signal_rows, ways, sig_way_hits


def compare_netconvert(cfg, sn, clusters, xy, eps, crs_m):
    """Assign netconvert traffic_light junctions to our clusters (nearest signal node within eps)."""
    root = None
    xs, ys, ids = [], [], []
    for _, el in ET.iterparse(cfg["paths"]["netconvert_net"], events=("end",)):
        if el.tag == "location":
            root = el.attrib
        elif el.tag == "junction":
            if el.get("type") == "traffic_light":
                ids.append(el.get("id"))
                xs.append(float(el.get("x")))
                ys.append(float(el.get("y")))
            el.clear()
    ox, oy = (float(v) for v in root["netOffset"].split(","))
    tr = pyproj.Transformer.from_crs(root["projParameter"], f"EPSG:{crs_m}", always_xy=True)
    tx, ty = tr.transform(np.array(xs) - ox, np.array(ys) - oy)
    txy = np.column_stack([tx, ty])
    dist, idx = cKDTree(xy).query(txy)
    matched = dist <= eps
    cid = sn["cluster_id"].to_numpy()[idx]
    per = pd.Series(cid[matched]).value_counts()
    per = per.reindex(clusters["cluster_id"], fill_value=0)
    return {"n_tl": len(ids), "n_unmatched": int((~matched).sum()), "per_cluster": per,
            "dist_median": float(np.median(dist)), "dist_p90": float(np.percentile(dist, 90))}


def classify_crossings(cfg, sn, hits, crs_m):
    """Where do crossing_signal nodes lie: scope status of the highway ways and cutting box."""
    cr = sn[sn["kind"] == "crossing_signal"].copy()
    w, s_, e, n = cfg["cutting_box"]
    ll = cr.to_crs(4326).geometry
    cr["in_box"] = (ll.x >= w) & (ll.x <= e) & (ll.y >= s_) & (ll.y <= n)

    def status(nid):
        h = hits.get(nid, [])
        if any(r for _, r in h):
            return "on in-scope way"
        return "only out-of-scope way: " + "/".join(sorted({x for x, _ in h})) if h else "no highway way"

    cr["status"] = [status(i) for i in cr["osm_id"]]
    return cr[["osm_id", "in_box", "status"]]


def build(cfg, scope):
    crs_m = cfg["crs_metric"]
    sig_eps = scope["signal_cluster_eps_m"]
    jun_eps = scope["junction_cluster_eps_m"]
    tbc_types = {"service", "road", "track"}  # [TO BE CONFIRMED] highway classes

    signal_rows, raw_ways, sig_way_hits = read_osm(cfg["paths"]["extract"], scope)
    log.info("read %d signal nodes, %d candidate ways", len(signal_rows), len(raw_ways))

    # --- ways ---
    way_rows, geoms = [], []
    degree, degree_core, coords = {}, {}, {}
    road_ways_at, tram_ways_at, roundabout = {}, {}, set()
    other_rail_geoms = []
    for wid, tags, nodes, is_road, is_tram, is_other_rail in raw_ways:
        line = [(lon, lat) for _, lon, lat in nodes]
        if is_other_rail and not (is_road or is_tram):
            other_rail_geoms.append((tags["railway"], LineString(line)))
            continue
        cyc = ",".join(v for k, v in sorted(tags.items()) if k.startswith("cycleway"))
        way_rows.append({
            "osm_id": wid,
            "highway": tags.get("highway") if is_road else None,
            "railway": tags.get("railway"),
            "is_tram": is_tram,
            "oneway": tags.get("oneway"),
            "lanes": tags.get("lanes"),
            "maxspeed": tags.get("maxspeed"),
            "bridge": tags.get("bridge"),
            "tunnel": tags.get("tunnel"),
            "service": tags.get("service"),
            "bicycle": tags.get("bicycle"),
            "access": tags.get("access"),
            "cycleway_raw": cyc or None,
            "name": tags.get("name"),
            "area": tags.get("area"),
        })
        geoms.append(LineString(line))
        last = len(nodes) - 1
        is_round = tags.get("junction") in ("roundabout", "circular")
        for i, (ref, lon, lat) in enumerate(nodes):
            coords[ref] = (lon, lat)
            if is_road:
                inc = 1 if i in (0, last) else 2
                degree[ref] = degree.get(ref, 0) + inc
                if tags.get("highway") not in tbc_types:
                    degree_core[ref] = degree_core.get(ref, 0) + inc
                road_ways_at.setdefault(ref, set()).add(wid)
                if is_round:
                    roundabout.add(ref)
            if is_tram:
                tram_ways_at.setdefault(ref, set()).add(wid)

    ways = gpd.GeoDataFrame(way_rows, geometry=geoms, crs=4326).to_crs(crs_m)
    ways["length_m"] = ways.geometry.length
    n_area = int((ways["area"] == "yes").sum())
    ways = ways.drop(columns="area")
    ways = ways[["osm_id", "highway", "railway", "is_tram", "length_m", "oneway", "lanes",
                 "maxspeed", "bridge", "tunnel", "service", "bicycle", "access",
                 "cycleway_raw", "name", "geometry"]]

    # rail ways outside the scope (rail_in_scope = false): length by railway value
    if other_rail_geoms:
        og = gpd.GeoDataFrame(
            {"railway": [r for r, _ in other_rail_geoms]},
            geometry=[g for _, g in other_rail_geoms], crs=4326,
        ).to_crs(crs_m)
        other_rail_m = og.geometry.length.groupby(og["railway"]).sum().to_dict()
    else:
        other_rail_m = {}

    # --- signal nodes and clusters ---
    sn = pd.DataFrame(signal_rows, columns=["osm_id", "kind", "bicycle", "lon", "lat"])
    sn = sn.sort_values("osm_id").reset_index(drop=True)
    sn_gdf = gpd.GeoDataFrame(
        sn[["osm_id", "kind", "bicycle"]],
        geometry=gpd.points_from_xy(sn.lon, sn.lat), crs=4326,
    ).to_crs(crs_m)
    xy = np.column_stack([sn_gdf.geometry.x, sn_gdf.geometry.y])
    sn_gdf["cluster_id"] = cluster(xy, sig_eps)
    g = sn_gdf.assign(x=xy[:, 0], y=xy[:, 1]).groupby("cluster_id")
    sc = pd.DataFrame({
        "n_nodes": g.size(),
        "n_junction": g["kind"].apply(lambda s: int((s == "junction_signal").sum())),
        "x": g["x"].mean(), "y": g["y"].mean(),
    }).reset_index()
    sc["n_crossing"] = sc["n_nodes"] - sc["n_junction"]
    sc["kind"] = np.where(sc["n_junction"] >= 1, "junction", "crossing_only")
    signal_clusters = gpd.GeoDataFrame(
        sc[["cluster_id", "n_nodes", "n_junction", "n_crossing", "kind"]],
        geometry=gpd.points_from_xy(sc.x, sc.y), crs=crs_m,
    )
    signal_ids = set(sn["osm_id"])
    sensitivity = [(e, int(cluster(xy, e).max()) + 1) for e in cfg["eps_sensitivity_m"]]

    # --- junction nodes and clusters ---
    jids = sorted(r for r, d in degree.items() if d >= 3)
    jll = np.array([coords[r] for r in jids])
    jn_gdf = gpd.GeoDataFrame(
        {
            "osm_id": jids,
            "degree": [degree[r] for r in jids],
            "degree_core": [degree_core.get(r, 0) for r in jids],
            "has_signal": [r in signal_ids for r in jids],
            "is_roundabout": [r in roundabout for r in jids],
            "has_tram": [r in tram_ways_at for r in jids],
        },
        geometry=gpd.points_from_xy(jll[:, 0], jll[:, 1]), crs=4326,
    ).to_crs(crs_m)
    jxy = np.column_stack([jn_gdf.geometry.x, jn_gdf.geometry.y])
    jn_gdf["junction_cluster_id"] = cluster(jxy, jun_eps)
    jg = jn_gdf.assign(x=jxy[:, 0], y=jxy[:, 1]).groupby("junction_cluster_id")
    jc = pd.DataFrame({
        "n_nodes": jg.size(), "max_degree": jg["degree"].max(),
        "has_signal": jg["has_signal"].any(), "has_roundabout": jg["is_roundabout"].any(),
        "has_tram": jg["has_tram"].any(), "x": jg["x"].mean(), "y": jg["y"].mean(),
    }).reset_index()
    junction_clusters = gpd.GeoDataFrame(
        jc.drop(columns=["x", "y"]),
        geometry=gpd.points_from_xy(jc.x, jc.y), crs=crs_m,
    )
    jn_core = jn_gdf.drop(columns="degree_core")

    # mid_block: no junction node (degree >= 3) within the radius of any member signal node
    near = cKDTree(jxy).query(xy)[0] <= cfg["mid_block_radius_m"]
    near_cluster = pd.Series(near).groupby(sn_gdf["cluster_id"].to_numpy()).any()
    signal_clusters["mid_block"] = ~near_cluster.reindex(signal_clusters["cluster_id"]).to_numpy()

    nc = compare_netconvert(cfg, sn_gdf, signal_clusters, xy, sig_eps, crs_m)
    crossing_origin = classify_crossings(cfg, sn_gdf, sig_way_hits, crs_m)

    # --- tram crossings: node shared by a tram way and a different in-scope road way ---
    tc_ids = sorted(
        r for r, t in tram_ways_at.items()
        if r in road_ways_at and len(t | road_ways_at[r]) > 1
    )
    tll = np.array([coords[r] for r in tc_ids]).reshape(-1, 2)
    tram_crossings = gpd.GeoDataFrame(
        {"osm_id": tc_ids}, geometry=gpd.points_from_xy(tll[:, 0], tll[:, 1]), crs=4326,
    ).to_crs(crs_m)

    # --- KBR points ---
    kbr = gpd.read_file(cfg["paths"]["kbr_points"], layer=cfg["paths"]["kbr_layer"])
    kbr = kbr[["Kordon", "Pkt_pomiar", "geometry"]]

    layers = {
        "ways": ways, "signal_nodes": sn_gdf, "signal_clusters": signal_clusters,
        "junction_nodes": jn_core, "junction_clusters": junction_clusters,
        "tram_crossings": tram_crossings, "kbr_points": kbr,
    }
    extra = {
        "n_area_ways": n_area, "other_rail_m": other_rail_m,
        "jn_degree_core": jn_gdf, "tbc_types": sorted(tbc_types),
        "sensitivity": sensitivity, "nc": nc, "crossing_origin": crossing_origin,
    }
    return layers, extra


def run_checks(cfg, layers):
    """Return list of (name, expected, actual, status, severity)."""
    c = cfg["checks"]
    sn, sc, kbr, ways = (layers[k] for k in ("signal_nodes", "signal_clusters", "kbr_points", "ways"))
    rows = []
    n_j = int((sn["kind"] == "junction_signal").sum())
    rows.append(("signal_nodes junction_signal", f"== {c['junction_signal_expected']}", n_j,
                 n_j == c["junction_signal_expected"], "hard"))
    n_c = int((sn["kind"] == "crossing_signal").sum())
    rows.append(("signal_nodes crossing_signal", f">= {c['crossing_signal_min']}", n_c,
                 n_c >= c["crossing_signal_min"], "soft"))
    n_sc = len(sc)
    rows.append(("signal_clusters (informational)",
                 f"{c['signal_clusters_reference']} (netconvert join, not ground truth)",
                 n_sc, True, "info"))
    counts = kbr["Kordon"].value_counts().to_dict()
    for k, v in c["kbr_expected"].items():
        rows.append((f"kbr_points {k}", f"== {v}", counts.get(k, 0), counts.get(k, 0) == v, "hard"))
    invalid = {n: int((~g.geometry.is_valid).sum()) for n, g in layers.items()}
    rows.append(("invalid geometries (all layers)", "0", sum(invalid.values()),
                 sum(invalid.values()) == 0, "hard"))
    bad_crs = [n for n, g in layers.items() if g.crs is None or g.crs.to_epsg() != cfg["crs_metric"]]
    rows.append(("layers with CRS != EPSG:%d" % cfg["crs_metric"], "none",
                 ",".join(bad_crs) or "none", not bad_crs, "hard"))
    return rows


def write_gpkg(path, layers):
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        p.unlink()
    for name, gdf in layers.items():
        gdf.to_file(p, layer=name, driver="GPKG")


def write_report(cfg, scope, layers, extra, checks, elapsed):
    ways, sn = layers["ways"], layers["signal_nodes"]
    sc, jn, jc = layers["signal_clusters"], layers["junction_nodes"], layers["junction_clusters"]
    L = []
    L.append("# Task 01: OSM feature layers for RING 1-3\n")
    L.append(f"Input: `{cfg['paths']['extract']}` (snapshot dolnoslaskie_2026-10-23). "
             f"Output: `{cfg['paths']['output']}` (EPSG:{cfg['crs_metric']}). "
             f"Run time: **{elapsed:.1f} s**.\n")
    L.append("## Correctness checks\n")
    L.append(md_table(["Check", "Expected", "Actual", "Result", "Severity"],
                      [(n, e, a, ("INFO" if s == "info" else "PASS" if ok else "FAIL"), s) for n, e, a, ok, s in checks]))
    L.append("\n## Objects per layer\n")
    L.append(md_table(["Layer", "Objects"], [(k, len(v)) for k, v in layers.items()]))

    road = ways[ways["highway"].notna()]
    km = (road.groupby("highway")["length_m"].agg(["count", "sum"]).sort_values("sum", ascending=False))
    L.append("\n## Road km by `highway` class\n")
    rows = [(h, int(r["count"]), f"{r['sum']/1000:.1f}") for h, r in km.iterrows()]
    rows.append(("**total roads**", len(road), f"{road['length_m'].sum()/1000:.1f}"))
    L.append(md_table(["highway", "ways", "km"], rows))
    tram = ways[ways["is_tram"]]
    L.append(f"\nTram track (`is_tram`): {len(tram)} ways, **{tram['length_m'].sum()/1000:.1f} km** "
             f"(of which {int(tram['highway'].notna().sum())} ways are also in-scope roads and appear in both totals).\n")
    L.append("Railways outside the scope (`rail_in_scope: false`), km by `railway` value:\n")
    orm = extra["other_rail_m"]
    L.append(md_table(["railway", "km"], [(k, f"{v/1000:.1f}") for k, v in sorted(orm.items(), key=lambda kv: -kv[1])]) if orm else "none")

    L.append("\n## Signals\n")
    L.append(md_table(["kind", "nodes"], sn["kind"].value_counts().sort_index().items()))
    L.append(f"\nSignal clusters (eps {scope['signal_cluster_eps_m']} m): {len(sc)} "
             f"(`{sc['kind'].value_counts().get('junction', 0)}` junction, "
             f"`{sc['kind'].value_counts().get('crossing_only', 0)}` crossing_only).\n")
    L.append("Distribution of cluster sizes (`n_nodes`):\n")
    L.append(md_table(["n_nodes", "clusters"], sc["n_nodes"].value_counts().sort_index().items()))

    L.append("\n## Junctions\n")
    L.append("Distribution of `degree` in `junction_nodes`:\n")
    L.append(md_table(["degree", "nodes"], jn["degree"].value_counts().sort_index().items()))
    L.append(f"\nJunction clusters (eps {scope['junction_cluster_eps_m']} m): **{len(jc)}** "
             f"from {len(jn)} junction nodes; with signal: {int(jc['has_signal'].sum())}, "
             f"with roundabout: {int(jc['has_roundabout'].sum())}, with tram: {int(jc['has_tram'].sum())}.\n")

    L.append("## KBR points by `Kordon`\n")
    L.append(md_table(["Kordon", "points"], layers["kbr_points"]["Kordon"].value_counts().sort_index().items()))

    L.append("\n## Effect of `[TO BE CONFIRMED]` assumptions\n")
    tbc = km.reindex(extra["tbc_types"]).fillna(0)
    L.append(md_table(["highway", "ways", "km", "share of road km"],
                      [(h, int(r["count"]), f"{r['sum']/1000:.1f}",
                        f"{r['sum']/road['length_m'].sum():.1%}") for h, r in tbc.iterrows()]))
    jd = extra["jn_degree_core"]
    L.append(f"\n- `service`, `road`, `track`: `junction_nodes` with degree >= 3 would be "
             f"{int((jd['degree_core'] >= 3).sum())} instead of {len(jd)} if these three classes were excluded.")
    L.append(f"- `rail_in_scope: false`: rail km excluded are in the table above.")
    L.append(f"- `junction_cluster_eps_m: {scope['junction_cluster_eps_m']}`: merges {len(jn)} junction nodes "
             f"into {len(jc)} clusters ({len(jn) - len(jc)} fewer objects); no other value was tried.\n")
    L.append("## Signal clusters: diagnostics\n")
    L.append(f"`signal_clusters` is informational. The reference {cfg['checks']['signal_clusters_reference']} comes from "
             "`netconvert --junctions.join --tls.join`, a topological join, which is a different method than our "
             "distance-based single linkage. It is not a ground truth.\n")
    L.append("### Sensitivity to eps (everything else unchanged)\n")
    L.append(md_table(["eps [m]", "signal_clusters"], extra["sensitivity"]))
    nc = extra["nc"]
    per = nc["per_cluster"]
    L.append(f"\n### Comparison with netconvert traffic lights\n")
    L.append(f"`{cfg['paths']['netconvert_net']}`: {nc['n_tl']} junctions of type `traffic_light`, converted to EPSG:{cfg['crs_metric']} "
             f"with the net's `netOffset` and `projParameter`. A TL belongs to the cluster of the nearest signal node if it is "
             f"within eps = {scope['signal_cluster_eps_m']} m of it; {nc['n_unmatched']} TLs have no signal node that close "
             f"(distance to nearest signal node: median {nc['dist_median']:.1f} m, p90 {nc['dist_p90']:.1f} m).\n")
    L.append("Our clusters by number of netconvert TLs inside:\n")
    bins = [("0", int((per == 0).sum())), ("1", int((per == 1).sum())), ("2+", int((per >= 2).sum()))]
    L.append(md_table(["TLs in cluster", "our clusters"], bins))
    L.append("\nDistribution of TLs per cluster:\n")
    L.append(md_table(["TLs", "clusters"], per.value_counts().sort_index().items()))
    L.append("\nTen clusters with the most netconvert TLs:\n")
    top = per.sort_values(ascending=False, kind="stable").head(10)
    sc_i = sc.set_index("cluster_id")
    ll = sc_i.loc[top.index].to_crs(4326).geometry
    L.append(md_table(["cluster_id", "TLs", "n_nodes", "x [m, 2177]", "y [m, 2177]", "lon", "lat"],
                      [(cid, int(n), int(sc_i.at[cid, "n_nodes"]), f"{sc_i.geometry[cid].x:.1f}",
                        f"{sc_i.geometry[cid].y:.1f}", f"{ll[cid].x:.5f}", f"{ll[cid].y:.5f}")
                       for cid, n in top.items()]))
    L.append("\n### `mid_block` (no junction node with degree >= 3 within "
             f"{cfg['mid_block_radius_m']} m of any member signal node)\n")
    mb = pd.crosstab(sc["kind"], sc["mid_block"])
    mb = mb.reindex(columns=[False, True], fill_value=0)
    L.append(md_table(["kind", "mid_block = false", "mid_block = true"],
                      [(k, r[False], r[True]) for k, r in mb.iterrows()]))
    L.append("\n### Crossing signals: where they lie\n")
    co = extra["crossing_origin"]
    L.append(f"{len(co)} `crossing_signal` nodes vs 2012 turned into signals by `netconvert` "
             f"(difference {len(co) - 2012}). Node membership in highway ways, and position relative to the cutting box "
             f"{cfg['cutting_box']}:\n")
    ct = pd.crosstab(co["status"], co["in_box"].map({True: "inside box", False: "outside box"}))
    ct = ct.reindex(columns=["inside box", "outside box"], fill_value=0)
    L.append(md_table(["status", "inside box", "outside box"],
                      [(k, r["inside box"], r["outside box"]) for k, r in ct.iterrows()]
                      + [("**total**", ct["inside box"].sum(), ct["outside box"].sum())]))
    L.append("")
    L.append("## Notes\n")
    L.append(f"- {extra['n_area_ways']} in-scope ways carry `area=yes` (kept as lines; the spec does not exclude them).")
    L.append("- `crossing_signal` nodes are counted over the whole extract, including nodes on ways outside the scope.")
    L.append("- `junction_nodes.has_signal` is true when the node itself is a signal node (junction or crossing kind).")
    p = pathlib.Path(cfg["paths"]["report"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(L) + "\n", encoding="utf-8")


def main():
    t0 = time.time()
    cfg = load_yaml(sys.argv[1] if len(sys.argv) > 1 else "config/10_build_features.yaml")
    setup_logging(cfg["paths"]["log"])
    scope = load_yaml(cfg["paths"]["scope"])
    layers, extra = build(cfg, scope)

    excluded = set(scope["highway_exclude"])
    bad = layers["ways"]["highway"].isin(excluded).sum()
    checks = run_checks(cfg, layers)
    checks.append(("ways in highway_exclude", "0", int(bad), bad == 0, "hard"))

    write_gpkg(cfg["paths"]["output"], layers)
    elapsed = time.time() - t0
    write_report(cfg, scope, layers, extra, checks, elapsed)

    print(md_table(["Check", "Expected", "Actual", "Result", "Severity"],
                   [(n, e, a, ("INFO" if s == "info" else "PASS" if ok else "FAIL"), s) for n, e, a, ok, s in checks]))
    print(md_table(["Layer", "Objects"], [(k, len(v)) for k, v in layers.items()]))
    log.info("done in %.1f s", elapsed)
    if any(not ok and sev == "hard" for _, _, _, ok, sev in checks):
        log.error("hard check failed: see report")
        sys.exit(1)


if __name__ == "__main__":
    main()
