"""Task 01 follow-up: compare our signal clusters with netconvert traffic lights.

Needs data/interim/features.gpkg (src/10_build_features.py) and a net produced with
`netconvert ... --junctions.join --tls.join` (path in the config). Skips if the net is missing.

Usage: uv run python src/12_compare_netconvert.py [config/12_compare_netconvert.yaml]
"""
import logging
import pathlib
import sys
import time
import xml.etree.ElementTree as ET

import geopandas as gpd
import numpy as np
import pandas as pd
import pyproj
import yaml
from scipy.spatial import cKDTree

log = logging.getLogger("compare")


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


def read_traffic_lights(net_path, crs_m):
    """Return an (n, 2) array of netconvert traffic_light junction positions in EPSG:crs_m."""
    loc = None
    xs, ys = [], []
    for _, el in ET.iterparse(net_path, events=("end",)):
        if el.tag == "location":
            loc = el.attrib
        elif el.tag == "junction":
            if el.get("type") == "traffic_light":
                xs.append(float(el.get("x")))
                ys.append(float(el.get("y")))
            el.clear()
    ox, oy = (float(v) for v in loc["netOffset"].split(","))
    tr = pyproj.Transformer.from_crs(loc["projParameter"], f"EPSG:{crs_m}", always_xy=True)
    tx, ty = tr.transform(np.array(xs) - ox, np.array(ys) - oy)
    return np.column_stack([tx, ty])


def main():
    t0 = time.time()
    cfg = load_yaml(sys.argv[1] if len(sys.argv) > 1 else "config/12_compare_netconvert.yaml")
    setup_logging(cfg["paths"]["log"])
    net = pathlib.Path(cfg["paths"]["netconvert_net"])
    if not net.exists():
        msg = (f"SKIPPED: netconvert net {net} not found. Generate it with the command from "
               "docs/SETUP.md section 6b plus --junctions.join --tls.join.")
        log.warning(msg)
        print(msg)
        return
    scope = load_yaml(cfg["paths"]["scope"])
    eps = scope["signal_cluster_eps_m"]
    crs_m = cfg["crs_metric"]

    sn = gpd.read_file(cfg["paths"]["features"], layer="signal_nodes")
    sc = gpd.read_file(cfg["paths"]["features"], layer="signal_clusters")
    xy = np.column_stack([sn.geometry.x, sn.geometry.y])
    txy = read_traffic_lights(net, crs_m)

    dist, idx = cKDTree(xy).query(txy)
    matched = dist <= eps
    per = pd.Series(sn["cluster_id"].to_numpy()[idx][matched]).value_counts()
    per = per.reindex(sc["cluster_id"], fill_value=0)

    L = ["# Task 01: our signal clusters vs netconvert traffic lights\n"]
    L.append(f"Net: `{net}` ({len(txy)} junctions of type `traffic_light`, built with `--junctions.join --tls.join`). "
             f"Our clusters: {len(sc)} (single linkage, eps {eps} m). The netconvert count comes from a topological "
             "join, a different method, and is not a ground truth.\n")
    L.append(f"A traffic light belongs to the cluster of the nearest signal node if it lies within eps = {eps} m of it. "
             f"{int((~matched).sum())} of {len(txy)} have no signal node that close "
             f"(distance to nearest signal node: median {np.median(dist):.1f} m, "
             f"p90 {np.percentile(dist, 90):.1f} m).\n")
    L.append("## Our clusters by number of netconvert traffic lights inside\n")
    L.append(md_table(["TLs in cluster", "our clusters"],
                      [("0", int((per == 0).sum())), ("1", int((per == 1).sum())), ("2+", int((per >= 2).sum()))]))
    L.append("\n## Distribution of traffic lights per cluster\n")
    L.append(md_table(["TLs", "clusters"], per.value_counts().sort_index().items()))
    L.append(f"\n## {cfg['top_clusters']} clusters with the most netconvert traffic lights\n")
    top = per.sort_values(ascending=False, kind="stable").head(cfg["top_clusters"])
    sc_i = sc.set_index("cluster_id")
    ll = sc_i.loc[top.index].to_crs(4326).geometry
    L.append(md_table(["cluster_id", "TLs", "n_nodes", f"x [m, {crs_m}]", f"y [m, {crs_m}]", "lon", "lat"],
                      [(cid, int(n), int(sc_i.at[cid, "n_nodes"]), f"{sc_i.geometry[cid].x:.1f}",
                        f"{sc_i.geometry[cid].y:.1f}", f"{ll[cid].x:.5f}", f"{ll[cid].y:.5f}")
                       for cid, n in top.items()]))
    elapsed = time.time() - t0
    L.append(f"\nRun time: {elapsed:.1f} s\n")
    p = pathlib.Path(cfg["paths"]["report"])
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(L), encoding="utf-8")
    print("\n".join(L))
    log.info("done in %.1f s", elapsed)


if __name__ == "__main__":
    main()
