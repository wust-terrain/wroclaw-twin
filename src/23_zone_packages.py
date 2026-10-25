"""Task 03b': freeze the pilot zones, ownership lists for all 11 zones, zone packages for the pilot zones. Analysis and packaging only.

Usage: uv run python src/23_zone_packages.py [config/23_zone_packages.yaml]
Reads the v0.2 partition (data/interim/ring1_zones_v02.gpkg) as it is; nothing is recomputed.
"""
import hashlib
import importlib.util
import json
import logging
import pathlib
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from xml.sax.saxutils import quoteattr

import geopandas as gpd
import numpy as np
import pandas as pd
import pyogrio
import shapely
import yaml
from pyproj import Transformer
from shapely.geometry import LineString, Point, mapping
from shapely.ops import unary_union

log = logging.getLogger("packages")
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


def sha256(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def km(m):
    return f"{m / 1000:.2f}"


def fmt_shares(sh):
    return ";".join(f"{z}:{v:.4f}" for z, v in sorted(sh.items(), key=lambda kv: (-kv[1], kv[0])))


def read_table(path, layer, columns=None):
    return pyogrio.read_dataframe(path, layer=layer, read_geometry=False, columns=columns)


# ------------------------------------------------------------------ OSM input
def parse_osm(path):
    """nodes {id: (lon, lat)}, ways {id: (node ids, tags)}, relations {id: (members, tags)}; only the tags that are used are kept."""
    keep = {"name", "highway", "railway", "restriction", "type"}
    nodes, ways, rels = {}, {}, {}
    for _, el in ET.iterparse(path, events=("end",)):
        t = el.tag
        if t == "node":
            nodes[int(el.get("id"))] = (float(el.get("lon")), float(el.get("lat")))
        elif t == "way":
            ways[int(el.get("id"))] = ([int(n.get("ref")) for n in el.findall("nd")],
                                       {x.get("k"): x.get("v") for x in el.findall("tag") if x.get("k") in keep})
        elif t == "relation":
            rels[int(el.get("id"))] = ([(m.get("type"), int(m.get("ref")), m.get("role")) for m in el.findall("member")],
                                       {x.get("k"): x.get("v") for x in el.findall("tag") if x.get("k") in keep})
        else:
            continue
        el.clear()
    return nodes, ways, rels


def way_highway(tags):
    return tags.get("highway") or tags.get("railway") or ""


# ------------------------------------------------------------------ inputs
def load_inputs(cfg, c16):
    P, crs = cfg["paths"], c16["crs_metric"]
    d = {}
    z = P["zones_gpkg"]
    d["zones"] = gpd.read_file(z, layer="zones_v02")
    d["faces"] = gpd.read_file(z, layer="faces")
    d["edges_zone"] = gpd.read_file(z, layer="edges_zone")
    d["clusters_zone"] = read_table(z, "clusters_zone")
    d["seam_edges"] = gpd.read_file(z, layer="seam_edges")
    d["bridges"] = gpd.read_file(z, layer="bridges")
    d["bridge_groups"] = gpd.read_file(z, layer="bridge_groups")
    d["islands"] = gpd.read_file(z, layer="islands")
    o = P["ownership_gpkg"]
    # `segments` carries the sentinel edge_id -1 for every tram fragment; the tram edge -> way mapping is in `tram_segments`
    sg = read_table(o, "segments", ["way_id", "edge_id", "length_m", "highway", "is_tram"])
    em = read_table(o, "edges", ["edge_id", "highway", "length_m", "tier_tag", "tier_promoted"])
    tm = read_table(o, "tram_segments", ["way_id", "edge_id", "highway", "length_m", "tier_tag", "tier_promoted"])
    d["segments"] = pd.concat([sg[~sg["is_tram"]][["way_id", "edge_id", "length_m", "highway"]], tm[["way_id", "edge_id", "length_m", "highway"]]], ignore_index=True)
    d["edge_meta"] = pd.concat([em, tm]).drop_duplicates("edge_id").set_index("edge_id").sort_index()
    f = P["features_gpkg"]
    d["junction_nodes"] = read_table(f, "junction_nodes", ["osm_id", "junction_cluster_id"])
    d["signal_nodes"] = read_table(f, "signal_nodes", ["osm_id", "cluster_id"])
    d["units"] = pd.read_csv(P["units"])
    d["site_hulls"] = gpd.read_file(P["sites_gpkg"], layer="site_hulls").to_crs(crs)
    d["site_points"] = gpd.read_file(P["sites_gpkg"], layer="sites").to_crs(crs)
    d["ring1"] = gpd.read_file(P["polygons"], layer=P["polygon_layer"]).to_crs(crs).geometry.iloc[0]
    return d


# ------------------------------------------------------------------ site zones
def site_zones(cfg, d):
    """Zone of every site: sites with a junction cluster take the zone stored in clusters_zone; the others (signals and tram crossings only)
    get it from the stored face labels by the hull rule of task 03c (largest overlap, ties to the lower zone). Validated on the first group."""
    faces = d["faces"]
    geoms, fz = faces.geometry.to_numpy(), faces["zone"].to_numpy()
    tree = shapely.STRtree(geoms)
    pts = {int(r.site_id): r.geometry for r in d["site_points"].itertuples()}
    rule = {}
    for sid, hull in zip(d["site_hulls"]["site_id"].astype(int), d["site_hulls"].geometry):
        if hull.area < 50:
            hull = hull.union(pts[sid].buffer(cfg["site_min_radius_m"]))
        acc = defaultdict(float)
        for i in tree.query(hull, predicate="intersects"):
            if fz[i] > 0:
                a = hull.intersection(geoms[i]).area
                if a > cfg["hull_touch_min_m2"]:
                    acc[int(fz[i])] += a
        if not acc:
            i = int(tree.nearest(hull))
            acc = {int(fz[i]): 1.0} if fz[i] > 0 else {}
        top = max(acc.values())
        rule[sid] = sorted(z for z, a in acc.items() if a >= top - 1e-6)[0]
    cz = d["clusters_zone"].dropna(subset=["site_id"])
    stored = cz.groupby(cz["site_id"].astype(int))["zone"].first().astype(int).to_dict()
    check("site zones: hull rule reproduces the stored cluster zones", 0, sum(1 for s, z in stored.items() if rule.get(s) != z))
    out = dict(rule)
    out.update(stored)
    return out, len(stored)


# ------------------------------------------------------------------ ownership of ways
def ways_ownership(cfg, d, ways, nxy, wlen, site_zone):
    ez = d["edges_zone"].set_index("edge_id")["zone"]
    seg = d["segments"]
    S = seg[seg["edge_id"].isin(ez.index)].copy()
    S["zone"] = S["edge_id"].map(ez).astype(int)
    zl = defaultdict(dict)
    for (w, z), l in S.groupby(["way_id", "zone"])["length_m"].sum().items():
        zl[int(w)][int(z)] = float(l)
    # bridge groups: the ways of the group's edges follow the group owner
    bridges = d["bridges"]
    way_group = defaultdict(set)
    group_owner, group_ways, group_edges = {}, {}, {}
    eway = S.groupby("edge_id")["way_id"].apply(lambda s: sorted(set(int(x) for x in s))).to_dict()
    for g in d["bridge_groups"].itertuples():
        edges = [int(k) for k in g.edge_ids.split(";")]
        ws = set(int(w) for k in edges for w in eway.get(k, []))
        ws |= set(int(w) for w in bridges.loc[bridges["group_id"] == g.group_id, "way_id"])
        group_owner[int(g.group_id)], group_ways[int(g.group_id)], group_edges[int(g.group_id)] = int(g.owner_zone), sorted(ws), edges
        for w in ws:
            way_group[w].add(int(g.group_id))
        bad = [k for k in edges if int(ez.get(k, -1)) != int(g.owner_zone)]
        check(f"bridge group {g.group_id}: all edges carry the group owner in edges_zone", 0, len(bad))
    conflicts = {w: sorted(gs) for w, gs in way_group.items() if len({group_owner[g] for g in gs}) > 1}
    check("ways in bridge groups with different owners", 0, len(conflicts))
    if conflicts:
        log.error("ways in groups with different owners: %s", conflicts)
    seg_hw = seg.groupby("way_id")["highway"].first()
    seg_total = seg.groupby("way_id")["length_m"].sum()   # length of ways missing from the base extract: sum of their fragments
    # geometry fallback for ways without an edges_zone mapping
    faces = d["faces"]
    zf = faces[faces["zone"] > 0]
    zg, zz = zf.geometry.to_numpy(), zf["zone"].to_numpy()
    ztree = shapely.STRtree(zg)
    ring = d["ring1"]
    shapely.prepare(ring)
    rows = {}
    ids = sorted(set(ways) | set(zl))
    for w in ids:
        tags = ways[w][1] if w in ways else {}
        r = dict(way_id=w, in_base_extract=w in ways, highway=way_highway(tags) if w in ways else str(seg_hw.get(w, "")), name=tags.get("name", ""),
                 length_m=round(wlen[w] if w in wlen else float(seg_total[w]), 2), bridge_group=None)
        if w in zl:
            tot = sum(zl[w].values())
            sh = {z: l / tot for z, l in zl[w].items() if l > cfg["span_min_m"]} or {max(zl[w], key=zl[w].get): 1.0}
            r.update(shares=sh, owner_basis="edges_zone")
        else:
            line = LineString([nxy[n] for n in ways[w][0]])
            acc = defaultdict(float)
            for i in ztree.query(line, predicate="intersects"):
                l = line.intersection(zg[i]).length
                if l > cfg["span_min_m"]:
                    acc[int(zz[i])] += l
            if acc:
                tot = sum(acc.values())
                r.update(shares={z: l / tot for z, l in acc.items()}, owner_basis="face_geometry")
            elif line.intersects(ring):
                r.update(shares={int(zz[int(ztree.nearest(line))]): 1.0}, owner_basis="nearest_face")
            else:
                r.update(shares={}, owner_basis="outside_ring1")
        sh = r["shares"]
        r["owner_zone"] = sorted(sh, key=lambda z: (-sh[z], z))[0] if sh else 0
        if w in way_group and w not in conflicts:
            g = min(way_group[w])
            if r["owner_zone"] != group_owner[g]:
                r["bridge_owner_differs_from_share"] = True
            r.update(owner_zone=group_owner[g], bridge_group=g, owner_basis="bridge_group")
        r["spans_zones"] = len(sh) > 1
        rows[w] = r
    meta = dict(group_owner=group_owner, group_ways=group_ways, group_edges=group_edges, conflicts=conflicts)
    return rows, meta


# ------------------------------------------------------------------ ownership of nodes
def nodes_ownership(cfg, d, nodes, ways, wrows, wlen, nxy, site_zone):
    cz = d["clusters_zone"]
    cl_zone = dict(zip(cz["cluster_id"].astype(int), cz["zone"].astype(int)))
    cl_site = {int(c): int(s) for c, s in zip(cz["cluster_id"], cz["site_id"]) if pd.notna(s)}
    u = d["units"]
    sig_site = {int(i): int(s) for i, s in zip(u.loc[u.unit_type == "signal_cluster", "id"], u.loc[u.unit_type == "signal_cluster", "site_id"])}
    trc_site = {int(i): int(s) for i, s in zip(u.loc[u.unit_type == "tram_crossing", "id"], u.loc[u.unit_type == "tram_crossing", "site_id"])}
    node_site, node_cluster = {}, {}
    for n, c in zip(d["junction_nodes"]["osm_id"], d["junction_nodes"]["junction_cluster_id"]):
        c = int(c)
        if c in cl_zone:
            node_cluster[int(n)] = c
            if c in cl_site:
                node_site[int(n)] = cl_site[c]
    for n, c in zip(d["signal_nodes"]["osm_id"], d["signal_nodes"]["cluster_id"]):
        if int(c) in sig_site:
            node_site[int(n)] = sig_site[int(c)]
    for n, s in trc_site.items():
        node_site[n] = s
    adj = defaultdict(list)
    for w in sorted(ways):
        for n in dict.fromkeys(ways[w][0]):
            adj[n].append(w)
    faces = d["faces"]
    zf = faces[faces["zone"] > 0]
    zg, zz = zf.geometry.to_numpy(), zf["zone"].to_numpy()
    ztree = shapely.STRtree(zg)
    ring = d["ring1"]
    rows, conflicts = {}, []
    for n in sorted(nodes):
        wz = Counter(wrows[w]["owner_zone"] for w in adj.get(n, []) if wrows[w]["owner_zone"] > 0)
        cand = [w for w in adj.get(n, []) if wrows[w]["owner_zone"] > 0]
        owner, basis = 0, "outside_ring1"
        conf = None
        if n in node_cluster:
            owner, basis = cl_zone[node_cluster[n]], "cluster"
            if n in node_site and site_zone[node_site[n]] != owner:   # signal / tram-crossing node of a site in another zone: the junction cluster wins
                conf = site_zone[node_site[n]]
                conflicts.append((n, node_site[n], conf, node_cluster[n], owner))
        elif n in node_site:
            owner, basis = site_zone[node_site[n]], "site"
        elif cand:
            best = sorted(cand, key=lambda w: (-wlen[w], w))[0]
            owner, basis = wrows[best]["owner_zone"], "longest_way"
        else:
            p = Point(nxy[n])
            if ring.intersects(p):
                hit = [i for i in ztree.query(p, predicate="intersects")]
                owner, basis = (int(zz[min(hit)]), "face_geometry") if hit else (int(zz[int(ztree.nearest(p))]), "nearest_face")
        rows[n] = dict(node_id=n, owner_zone=owner, shared_across_zones=len(wz) > 1, owner_basis=basis,
                       site_id=node_site.get(n), cluster_id=node_cluster.get(n), site_zone_conflict=conf, n_ways=len(adj.get(n, [])),
                       way_zones=";".join(f"{z}:{c}" for z, c in sorted(wz.items())))
    return rows, adj, conflicts


# ------------------------------------------------------------------ ownership of relations
def relations_ownership(rels, wrows, nrows):
    rows = {}
    for rid in sorted(rels):
        members, tags = rels[rid]
        by_role = defaultdict(list)
        for t, i, role in members:
            by_role[role].append((t, i))
        frm, via = by_role.get("from", []), by_role.get("via", [])

        def owner_of(m):
            t, i = m
            tab = nrows if t == "node" else wrows if t == "way" else {}
            return tab[i]["owner_zone"] if i in tab else None

        missing = sum(1 for t, i, _ in members if (t == "node" and i not in nrows) or (t == "way" and i not in wrows))
        o, basis, via_s = None, "", ""
        if via:
            o = owner_of(via[0])
            basis, via_s = "via_" + via[0][0], f"{via[0][0]}/{via[0][1]}"
        if o is None and frm:
            o, basis = owner_of(frm[0]), "from_way"
        mz = sorted({z for z in (owner_of((t, i)) for t, i, _ in members) if z})
        rows[rid] = dict(relation_id=rid, owner_zone=o or 0, owner_basis=basis, restriction=tags.get("restriction", ""), via=via_s,
                         from_way=frm[0][1] if frm else None, spans_zones=len(mz) > 1, member_zones=";".join(map(str, mz)),
                         missing_members=missing)
    return rows


# ------------------------------------------------------------------ frozen layers
def unit_tables(d, site_zone, c16):
    """Per-site table and per-unit table with owner zones."""
    u = d["units"].copy()
    ez = d["edges_zone"].set_index("edge_id")["zone"]
    isseg = u["unit_type"] == "segment"
    u["zone"] = np.where(isseg, u["id"].map(ez), u["site_id"].map(site_zone)).astype(int)
    st = u[~isseg]
    sc = c16["site_size_classes"]
    sites = pd.DataFrame({"site_id": sorted(st["site_id"].astype(int).unique())}).set_index("site_id")
    sites["n_units"] = st.groupby(st["site_id"].astype(int)).size()
    sites["size_class"] = np.where(sites["n_units"] <= sc["small_max"], "small", np.where(sites["n_units"] <= sc["medium_max"], "medium", "large"))
    sites["has_signal"] = st.groupby(st["site_id"].astype(int))["unit_type"].apply(lambda s: bool((s == "signal_cluster").any()))
    sites["has_tram"] = st.groupby(st["site_id"].astype(int))["unit_type"].apply(lambda s: bool((s == "tram_crossing").any()))
    sites["zone"] = sites.index.map(site_zone)
    meta = d["edge_meta"]
    u.loc[isseg, "stratum"] = [("tram" if k < 0 else "A" if meta.at[k, "tier_tag"] == "A" else "C" if meta.at[k, "tier_tag"] == "C"
                                else "B_service" if (c16["b_service_promoted"] and bool(meta.at[k, "tier_promoted"])) else "B_core") for k in u.loc[isseg, "id"].astype(int)]
    return u, sites


def item_minutes(cfg, d, ufaces, site_zone):
    im = ufaces.groupby(["unit_type", "key"])["minutes_s0"].sum().reset_index()
    ez = d["edges_zone"].set_index("edge_id")["zone"]
    im["zone"] = np.where(im["unit_type"] == "site", im["key"].map(site_zone), im["key"].map(ez)).astype(int)
    return im


def zone_stats(z, d, u, sites, im, wrows):
    uz = u[u["zone"] == z]
    seg = uz[uz["unit_type"] == "segment"]
    meta = d["edge_meta"]
    length = seg.set_index("id")["length_m"]
    st = dict(zone=z, units=len(uz), s0_minutes=float(im.loc[im["zone"] == z, "minutes_s0"].sum()),
              sites=int((sites["zone"] == z).sum()), tram_ways=int((seg["id"] < 0).sum()), edges=len(seg),
              strata={k: int((seg["stratum"] == k).sum()) for k in ("A", "B_core", "B_service", "C", "tram")})
    sz = sites[sites["zone"] == z]
    st["site_size"] = {k: int((sz["size_class"] == k).sum()) for k in ("small", "medium", "large")}
    st["site_signal"], st["site_tram"] = int(sz["has_signal"].sum()), int(sz["has_tram"].sum())
    km_ = {"A": 0.0, "tram": 0.0, "B": 0.0, "C": 0.0}
    for k, l in length.items():
        t = meta.at[k, "tier_tag"]
        km_[t] += l
        if k < 0:
            km_["tram"] += l
    st["km"] = km_
    st["unit_types"] = {k: int(v) for k, v in uz["unit_type"].value_counts().sort_index().items()}
    return st


def freeze(cfg, d, u, sites, im, pilots, stats):
    out = pathlib.Path(cfg["paths"]["frozen_gpkg"])
    out.parent.mkdir(parents=True, exist_ok=True)
    for suf in ("", "-wal", "-shm"):
        pathlib.Path(str(out) + suf).unlink(missing_ok=True)
    crs = d["zones"].crs
    zn = d["zones"][d["zones"]["zone"].isin(pilots)].copy()
    zn["s0_minutes"] = zn["zone"].map({z: round(stats[z]["s0_minutes"], 2) for z in pilots})
    zn["units"] = zn["zone"].map({z: stats[z]["units"] for z in pilots})
    zn["sites"] = zn["zone"].map({z: stats[z]["sites"] for z in pilots})
    zn["tram_ways"] = zn["zone"].map({z: stats[z]["tram_ways"] for z in pilots})
    zn["edges"] = zn["zone"].map({z: stats[z]["edges"] for z in pilots})
    zn.to_file(out, layer="zones_v02", driver="GPKG")
    ez = d["edges_zone"]
    ez[ez["zone"].isin(pilots)].to_file(out, layer="edges_zone", driver="GPKG", mode="a")
    cz = d["clusters_zone"]
    czg = gpd.read_file(cfg["paths"]["zones_gpkg"], layer="clusters_zone")
    czg[czg["zone"].isin(pilots)].to_file(out, layer="clusters_zone", driver="GPKG", mode="a")
    sm = d["seam_edges"]
    sm = sm[sm["zone"].isin(pilots) | sm["read_buffer_zone"].isin(pilots)]
    sm.to_file(out, layer="seam_edges", driver="GPKG", mode="a")
    bg = d["bridge_groups"]
    bg[bg["owner_zone"].isin(pilots)].to_file(out, layer="bridge_groups", driver="GPKG", mode="a")
    br = d["bridges"]
    br[br["owner_zone"].isin(pilots)].to_file(out, layer="bridges", driver="GPKG", mode="a")
    isl = d["islands"]
    isl[isl["zone"].isin(pilots)].to_file(out, layer="islands", driver="GPKG", mode="a")
    log.info("frozen gpkg written: %s", out)


# ------------------------------------------------------------------ package files
def osm_xml(path, nodes, ways, rels):
    """nodes {id: (lon, lat)}, ways {id: (node ids, tags)}, relations {id: (members, tags)}; negative ids; upload never."""
    L = ["<?xml version='1.0' encoding='UTF-8'?>", '<osm version="0.6" generator="23_zone_packages.py" upload="never">']
    for i in sorted(nodes, reverse=True):
        L.append(f'  <node id="{i}" lat="{nodes[i][1]:.7f}" lon="{nodes[i][0]:.7f}" visible="true"/>')
    for i in sorted(ways, reverse=True):
        nds, tags = ways[i]
        L.append(f'  <way id="{i}" visible="true">')
        L += [f'    <nd ref="{n}"/>' for n in nds]
        L += [f"    <tag k={quoteattr(k)} v={quoteattr(str(v))}/>" for k, v in tags.items()]
        L.append("  </way>")
    for i in sorted(rels, reverse=True):
        mem, tags = rels[i]
        L.append(f'  <relation id="{i}" visible="true">')
        L += [f'    <member type="way" ref="{r}" role="{role}"/>' for r, role in mem]
        L += [f"    <tag k={quoteattr(k)} v={quoteattr(str(v))}/>" for k, v in tags.items()]
        L.append("  </relation>")
    L.append("</osm>")
    pathlib.Path(path).write_text("\n".join(L) + "\n", encoding="utf-8")


class RefBuilder:
    def __init__(self):
        self.nodes, self.ways, self.rels, self.key = {}, {}, {}, {}
        self.nid = self.wid = self.rid = 0

    def node(self, lon, lat):
        k = (round(lon, 7), round(lat, 7))
        if k not in self.key:
            self.nid -= 1
            self.key[k] = self.nid
            self.nodes[self.nid] = k
        return self.key[k]

    def way(self, coords, tags):
        self.wid -= 1
        self.ways[self.wid] = ([self.node(x, y) for x, y in coords], dict(tags))
        return self.wid

    def polygon(self, geom, tags):
        parts = [p for p in shapely.get_parts(geom)]
        rings = []
        for p in parts:
            rings.append((self.way(list(p.exterior.coords), {}), "outer"))
            rings += [(self.way(list(i.coords), {}), "inner") for i in p.interiors]
        if len(rings) == 1:
            self.ways[self.wid] = (self.ways[self.wid][0], dict(tags))
            return
        self.rid -= 1
        self.rels[self.rid] = (rings, dict(tags, type="multipolygon"))


def write_package(cfg, d, z, pilots, ctx):
    """Zone package files for pilot zone z. Returns the extract info."""
    P = cfg["paths"]
    pdir = pathlib.Path(P["derived_dir"]) / f"zone_{z}"
    idir = pathlib.Path(P["interim_dir"]) / f"zone_{z}"
    for p in (pdir, idir):
        p.mkdir(parents=True, exist_ok=True)
    to4326 = Transformer.from_crs(ctx["crs"], 4326, always_xy=True)
    poly = d["zones"].set_index("zone").geometry[z]
    buf = poly.buffer(cfg["read_buffer_m"])
    tr = lambda g: shapely.transform(g, lambda a: np.column_stack(to4326.transform(a[:, 0], a[:, 1])))
    poly4, buf4 = tr(poly), tr(buf)
    gj = lambda g, name: json.dumps({"type": "Feature", "properties": {"name": name}, "geometry": mapping(g)}, sort_keys=True)
    (pdir / f"zone_{z}.geojson").write_text(gj(poly4, f"zone_{z}") + "\n")
    bpoly = idir / f"zone_{z}_buffer.geojson"
    bpoly.write_text(gj(buf4, f"zone_{z}_read_buffer") + "\n")
    # osm extract
    pbf, osm = idir / f"zone_{z}.osm.pbf", pdir / f"zone_{z}.osm"
    subprocess.run(["osmium", "extract", "-p", str(bpoly), "--strategy", "complete_ways", "--overwrite", "-o", str(pbf), P["roads_pbf"]], check=True)
    subprocess.run(["osmium", "cat", "--overwrite", "-o", str(osm), str(pbf)], check=True)
    en, ew, er = parse_osm(osm)
    wrows, nrows, rrows = ctx["wrows"], ctx["nrows"], ctx["rrows"]

    def split(ids, tab):
        c = Counter()
        for i in ids:
            o = tab[i]["owner_zone"]
            c["owned" if o == z else "read_only_other_zone" if o > 0 else "unowned"] += 1
        return {k: c.get(k, 0) for k in ("owned", "read_only_other_zone", "unowned")}
    info = dict(zone=z, read_buffer_m=cfg["read_buffer_m"], counts=dict(nodes=len(en), ways=len(ew), relations=len(er)),
                ways=split(ew, wrows), nodes=split(en, nrows), relations=split(er, rrows),
                sha256_extract=sha256(osm), sha256_base_osm=sha256(P["roads_osm"]), sha256_base_pbf=sha256(P["roads_pbf"]),
                sha256_buffer_polygon=sha256(bpoly), strategy="complete_ways", osmium=subprocess.run(["osmium", "--version"], capture_output=True, text=True).stdout.split("\n")[0])
    (pdir / f"zone_{z}.json").write_text(json.dumps(info, indent=2, sort_keys=True) + "\n")
    # seams
    seams = seam_rows(cfg, d, z, pilots, ctx)
    sdf = pd.DataFrame(seams["rows"])
    sdf.to_csv(pdir / f"zone_{z}_seams.csv", index=False)
    # reference layer
    rb = RefBuilder()
    rb.polygon(poly4, {"name": f"zone_{z}", "role": "owned"})
    rb.polygon(buf4, {"name": f"zone_{z}_read_buffer", "role": "read_buffer"})
    for r, geom in zip(seams["rows"], seams["geoms"]):
        tags = {"role": "seam", "other_zone": r["other_zone"], "owner": r["owner_zone"], "edge_id": r["edge_id"], "highway": r["highway"],
                "pilot_pair_seam": str(r["pilot_pair_seam"]).lower(), "read_only_neighbour": str(r["read_only_neighbour"]).lower()}
        if r["name"]:
            tags["name"] = r["name"]
        rb.way(list(tr(geom).coords), tags)
    osm_xml(pdir / f"zone_{z}_reference.osm", rb.nodes, rb.ways, rb.rels)
    return info, seams


def seam_rows(cfg, d, z, pilots, ctx):
    """Seam edges of zone z in both directions (edges owned by z towards M, and edges owned by M towards z)."""
    sm = d["seam_edges"]
    sm = sm[(sm["zone"] == z) | (sm["read_buffer_zone"] == z)].sort_values("edge_id")
    eway = ctx["edge_ways"]
    rows, geoms = [], []
    for r in sm.itertuples():
        owner = int(r.zone)
        other = int(r.read_buffer_zone) if owner == z else owner
        ways = eway.get(int(r.edge_id), [])
        main = ways[0] if ways else None
        wr = ctx["wrows"].get(main[0]) if main else None
        meta = d["edge_meta"].loc[int(r.edge_id)]
        pilot_pair = other in pilots and other != z
        rows.append(dict(edge_id=int(r.edge_id), way_id=main[0] if main else "", way_ids=";".join(str(w[0]) for w in ways),
                         name=wr["name"] if wr else "", highway=meta["highway"], bridge=bool(r.bridge),
                         bridge_group=int(r.bridge_group) if pd.notna(r.bridge_group) else "", other_zone=other, owner_zone=owner,
                         length_m=round(float(meta["length_m"]), 2), pilot_pair_seam=pilot_pair, read_only_neighbour=not pilot_pair))
        geoms.append(r.geometry)
    return dict(rows=rows, geoms=geoms)


def write_units(cfg, d, u, sites, z, seams, ctx):
    pdir = pathlib.Path(cfg["paths"]["derived_dir"]) / f"zone_{z}"
    ro = {r["edge_id"] for r in seams["rows"] if r["read_only_neighbour"] and r["owner_zone"] == z
          and (cfg["exclude_bridge_seam_edges"] or not r["bridge"])}
    uz = u[u["zone"] == z].copy()
    seg = uz["unit_type"] == "segment"
    excluded = uz[seg & uz["id"].isin(ro)]
    uz = uz.drop(excluded.index)
    to4326 = Transformer.from_crs(ctx["crs"], 4326, always_xy=True)
    lon, lat = to4326.transform(uz["x"].to_numpy(), uz["y"].to_numpy())
    uz["lon"], uz["lat"] = np.round(lon, 7), np.round(lat, 7)
    sid = uz["site_id"]
    uz["site_n_units"] = sid.map(sites["n_units"])
    uz["site_size_class"] = sid.map(sites["size_class"])
    eway = ctx["edge_ways"]
    uz["way_ids"] = [";".join(str(w[0]) for w in eway.get(int(i), [])) if s else "" for i, s in zip(uz["id"], seg.loc[uz.index])]
    uz["edge_id"] = np.where(seg.loc[uz.index], uz["id"], np.nan)
    uz["unit_id"] = uz["id"]
    uz["site_id"] = uz["site_id"].astype("Int64")
    uz["edge_id"] = uz["edge_id"].astype("Int64")
    uz["tier_tag"] = uz["tier_tag"].fillna("")
    order = {"segment": 0, "junction_cluster_complex": 1, "signal_cluster": 2, "tram_crossing": 3}
    uz = uz.sort_values(["unit_type", "unit_id"], key=lambda s: s.map(order) if s.name == "unit_type" else s)
    cols = ["unit_type", "unit_id", "edge_id", "way_ids", "site_id", "site_n_units", "site_size_class", "lon", "lat", "tier_tag", "stratum",
            "highway", "length_m", "kind", "zone"]
    uz[cols].to_csv(pdir / f"zone_{z}_units.csv", index=False)
    return len(uz), excluded


def bridge_files(cfg, d, z, ctx):
    """zone_<z>_bridges.csv (owned bridge groups and islands) and zone_<z>_bridge_ways.csv (end nodes of every owned bridge way)."""
    pdir = pathlib.Path(cfg["paths"]["derived_dir"]) / f"zone_{z}"
    meta, wrows, nrows, ways = ctx["bridge_meta"], ctx["wrows"], ctx["nrows"], ctx["ways"]
    ez = d["edges_zone"].set_index("edge_id")
    em = d["edge_meta"]
    rows, wrs = [], []
    gnames = {}
    for g in d["bridge_groups"].sort_values("group_id").itertuples():
        gnames[int(g.group_id)] = g.name
        if int(g.owner_zone) != z:
            continue
        edges = meta["group_edges"][int(g.group_id)]
        wl = meta["group_ways"][int(g.group_id)]
        endo = []
        for w in wl:
            if w not in ways:
                wrs.append(dict(group_id=int(g.group_id), group_name=g.name, way_id=w, in_base_extract=False, highway="", name="", way_length_m="",
                                end_a="", owner_a="", end_b="", owner_b="", end_nodes_other_zone=""))
                continue
            nds = ways[w][0]
            ea, eb = nds[0], nds[-1]
            oa, ob = nrows[ea]["owner_zone"], nrows[eb]["owner_zone"]
            other = [str(n) for n, o in ((ea, oa), (eb, ob)) if o != z]
            endo += [f"{n}@{o}" for n, o in ((ea, oa), (eb, ob)) if o != z]
            wrs.append(dict(group_id=int(g.group_id), group_name=g.name, way_id=w, in_base_extract=True, highway=wrows[w]["highway"], name=wrows[w]["name"],
                            way_length_m=wrows[w]["length_m"], end_a=ea, owner_a=oa, end_b=eb, owner_b=ob, end_nodes_other_zone=";".join(other)))
        rows.append(dict(kind="bridge_group", id=int(g.group_id), name=g.name, edge_ids=";".join(map(str, edges)), way_ids=";".join(map(str, wl)),
                         other_zone="" if pd.isna(g.other_zone) else int(g.other_zone), length_m=round(float(em.loc[edges, "length_m"].sum()), 2),
                         area_m2="", end_nodes_other_zone=";".join(sorted(set(endo)))))
    br_group = {int(k): int(g) for k, g in zip(d["bridges"]["edge_id"], d["bridges"]["group_id"])}
    for r in d["islands"].sort_values("region_id").itertuples():
        if int(r.zone) != z:
            continue
        k = int(r.bridge) if pd.notna(r.bridge) else None
        g = br_group.get(k)
        ws = ctx["edge_ways"].get(k, []) if k is not None else []
        rows.append(dict(kind="island", id=int(r.region_id), name=gnames.get(g, ""), edge_ids="" if k is None else str(k),
                         way_ids=";".join(str(w[0]) for w in ws), other_zone="", length_m="", area_m2=round(float(r.area), 1), end_nodes_other_zone=""))
    cols = ["kind", "id", "name", "edge_ids", "way_ids", "other_zone", "length_m", "area_m2", "end_nodes_other_zone"]
    pd.DataFrame(rows, columns=cols).to_csv(pdir / f"zone_{z}_bridges.csv", index=False)
    wcols = ["group_id", "group_name", "way_id", "in_base_extract", "highway", "name", "way_length_m", "end_a", "owner_a", "end_b", "owner_b", "end_nodes_other_zone"]
    pd.DataFrame(wrs, columns=wcols).to_csv(pdir / f"zone_{z}_bridge_ways.csv", index=False)
    return rows, wrs


# ------------------------------------------------------------------ report
def pair_counts(sets):
    c = Counter()
    for s in sets:
        s = sorted(s)
        for i, a in enumerate(s):
            for b in s[i + 1:]:
                c[(a, b)] += 1
    return c


def write_report(cfg, R):
    P = cfg["paths"]
    pilots, stats, wrows, nrows, rrows = R["pilots"], R["stats"], R["wrows"], R["nrows"], R["rrows"]
    L = ["# Task 03b': pilot zones, ownership lists and zone packages (v0.2)", "",
         f"Analysis and packaging only. The v0.2 partition is used as stored (`{P['zones_gpkg']}`, nothing recomputed); `scope.yaml`, the polygon, D2-D4, "
         "`tiers.yaml`, `ring1_zones_v0.gpkg` and the v0.2 results are unchanged. Pilot zones " + ", ".join(map(str, pilots)) +
         f"; read buffer {cfg['read_buffer_m']} m. Every number is [PROPOSED] (S0 weights are unmeasured guesses).", "", "## Checks", "",
         md_table(["Check", "Expected", "Actual", "Result"], [list(c) for c in CHECKS]), "",
         "## Ownership rules (all 11 zones)", "",
         "- **Ways.** Owner = zone with the largest share of the way's length in RING 1: `segments` (way, edge, fragment length) joined to `edges_zone` (edge -> zone); "
         "ties go to the lower zone. All ways of a bridge group (ways of the group's edges, and `bridges.way_id`) follow the group owner "
         "(`owner_basis=bridge_group`, `bridge_owner_differs_from_share` when that changes the majority owner). `spans_zones` = length above "
         f"{cfg['span_min_m']} m in more than one zone; `shares` = `zone:share` of the length inside RING 1 edges.",
         "- **Ways without an edge** (footways, steps, paths, rail, and network ways whose edge is outside RING 1 by D3) are not in `edges_zone`. "
         "This case is not covered by the task text; interpretation used here: the way is cut by the zone faces of the stored partition and takes the zone with the largest length share "
         "(`owner_basis=face_geometry`); with no length in a zoned face but crossing RING 1 (water, orphan faces, islands with zone 0) it takes the zone of the nearest zoned face "
         "(`nearest_face`); the rest is outside RING 1 and unowned (`outside_ring1`, owner 0).",
         "- **Nodes.** Nodes of a junction cluster take `clusters_zone`; nodes of a site (cluster nodes, signal-cluster nodes, tram-crossing nodes) take the site zone "
         "(sites without a junction cluster: hull rule of task 03c on the stored faces, validated against the stored cluster zones). Other nodes take the owner of the longest way "
         "(full way length) that uses them among owned ways, ties to the lower way id. `shared_across_zones` = ways with different owners use the node; `way_zones` = `zone:number of ways`. "
         "Nodes with no owned way: stored faces as for ways.",
         "- **Relations (turn restrictions).** Owner of the via member (node: node owner; way: way owner); without via, the owner of the from way. `member_zones` lists the owners of all members.",
         "", "## Ownership counts", ""]
    zs = list(range(0, 12))
    wc, nc, rc = Counter(r["owner_zone"] for r in wrows.values()), Counter(r["owner_zone"] for r in nrows.values()), Counter(r["owner_zone"] for r in rrows.values())
    ws = Counter(r["owner_zone"] for r in wrows.values() if r["spans_zones"])
    ns = Counter(r["owner_zone"] for r in nrows.values() if r["shared_across_zones"])
    L.append(md_table(["owner zone", "ways", "of which spanning", "nodes", "of which shared", "relations"],
                      [[("none" if z == 0 else z), wc.get(z, 0), ws.get(z, 0), nc.get(z, 0), ns.get(z, 0), rc.get(z, 0)] for z in zs] +
                      [["total", len(wrows), sum(ws.values()), len(nrows), sum(ns.values()), len(rrows)]]))
    L += ["", "Owner `none` = outside RING 1 (reachable only through `complete_ways`).", "", "Ways by basis:", "",
          md_table(["owner_basis", "ways"], [[k, v] for k, v in sorted(Counter(r["owner_basis"] for r in wrows.values()).items())]), "",
          md_table(["node owner_basis", "nodes"], [[k, v] for k, v in sorted(Counter(r["owner_basis"] for r in nrows.values()).items())]), "",
          md_table(["relation owner_basis", "relations"], [[k or "(none)", v] for k, v in sorted(Counter(r["owner_basis"] for r in rrows.values()).items())]), "",
          f"Ways in `edges_zone` but missing from the base extract `ring1_roads.osm`: **{R['not_in_extract']}** (no geometry, no nodes; listed with `in_base_extract=False`). "
          f"Ways owned through the nearest-face fallback (zone 0 faces, islands, water): **{R['nearest_ways']}**; nodes: **{R['nearest_nodes']}**. "
          f"Relations with a member missing from the extract: {sum(1 for r in rrows.values() if r['missing_members'])}.", "",
          "**Discrepancy.** The base extract was cut with `osmium extract -p ring1.geojson --strategy complete_ways`, which keeps a way only when one of its nodes lies inside the polygon. "
          "The 66 ways above belong to RING 1 edges by rule D3 (an end cluster inside the polygon) but have no node inside it, so they are absent from `ring1_roads.osm` and from every zone package. "
          "Owners of the 66: " + ", ".join(f"zone {z}: {n}" for z, n in sorted(Counter(r['owner_zone'] for r in wrows.values() if not r['in_base_extract']).items())) + ". "
          "Not changed here; the packages are cut from the base file as specified.", "",
          md_table(["pilot zone", "way", "segment highway", "length m"],
                   [[r["owner_zone"], r["way_id"], r["highway"], r["length_m"]] for r in sorted(wrows.values(), key=lambda r: (r["owner_zone"], r["way_id"]))
                    if not r["in_base_extract"] and r["owner_zone"] in pilots]), "",
          f"Nodes that belong to a site in one zone and to a junction cluster in another (signal or tram-crossing nodes attached to a site by proximity): **{len(R['node_conflicts'])}**. "
          "The task text does not rank the two rules; the junction cluster wins (it is the atomic editing unit) and the node is flagged `site_zone_conflict` in `ownership_nodes.csv`.", ""]
    if R["node_conflicts"]:
        L += [md_table(["node", "site", "site zone", "cluster", "cluster zone (owner)"], [list(c) for c in R["node_conflicts"]]), ""]
    L += ["### Spanning ways and shared nodes", ""]
    sp = [r for r in wrows.values() if r["spans_zones"]]
    spe = [r for r in sp if r["owner_basis"] in ("edges_zone", "bridge_group")]
    L.append(f"Spanning ways: **{len(sp)}** in total (**{len(spe)}** through `edges_zone`, {len(sp) - len(spe)} through face geometry). "
             f"Shared nodes: **{sum(ns.values())}**.")
    pw = pair_counts([set(r["shares"]) for r in sp])
    pn = pair_counts([{int(x.split(':')[0]) for x in r["way_zones"].split(";")} for r in nrows.values() if r["shared_across_zones"]])
    L += ["", md_table(["zone pair", "spanning ways", "shared nodes"], [[f"{a}-{b}", pw.get((a, b), 0), pn.get((a, b), 0)] for a, b in sorted(set(pw) | set(pn))]), "",
          f"The {cfg['longest_spanning']} longest spanning ways:", "",
          md_table(["way", "highway", "name", "length m", "shares", "owner", "basis"],
                   [[r["way_id"], r["highway"], r["name"], r["length_m"], fmt_shares(r["shares"]), r["owner_zone"], r["owner_basis"]]
                    for r in sorted(sp, key=lambda r: (-r["length_m"], r["way_id"]))[:cfg["longest_spanning"]]])]
    L += ["", f"Same, only network ways (`edges_zone`/bridge group):", "",
          md_table(["way", "highway", "name", "length m", "shares", "owner"],
                   [[r["way_id"], r["highway"], r["name"], r["length_m"], fmt_shares(r["shares"]), r["owner_zone"]]
                    for r in sorted(spe, key=lambda r: (-r["length_m"], r["way_id"]))[:cfg["longest_spanning"]]])]
    L += ["", "## Frozen pilot zones", "",
          f"`{P['frozen_gpkg']}`: layers `zones_v02`, `edges_zone`, `clusters_zone`, `seam_edges` (owned by or read-buffer of a pilot zone), `bridge_groups`, `bridges`, `islands`; "
          "zone attributes `s0_minutes`, `units`, `sites`, `tram_ways`, `edges`.", "",
          "Label-drift guard (relative tolerance " + f"{cfg['label_drift_tolerance']:.0%}):", "",
          md_table(["zone", "units (expected / actual)", "S0 minutes (expected / actual)", "sites", "tram ways"],
                   [[z, f"{cfg['expected'][z]['units']} / {stats[z]['units']}", f"{cfg['expected'][z]['s0_minutes']} / {stats[z]['s0_minutes']:.1f}",
                     f"{cfg['expected'][z]['sites']} / {stats[z]['sites']}", f"{cfg['expected'][z]['tram_ways']} / {stats[z]['tram_ways']}"] for z in pilots])]
    for z in pilots:
        s, x = stats[z], R["pk"][z]
        info = x["info"]
        L += ["", f"## Zone {z}", "", "### Composition", "",
              md_table(["item", "value"], [
                  ["work units owned", s["units"]], ["work units in `zone_%d_units.csv`" % z, x["n_units_file"]],
                  ["S0 minutes after ownership", f"{s['s0_minutes']:.1f}"],
                  ["sites (small 1-2 / medium 3-9 / large >= 10)", f"{s['sites']} ({s['site_size']['small']} / {s['site_size']['medium']} / {s['site_size']['large']})"],
                  ["sites with a signal / with a tram crossing", f"{s['site_signal']} / {s['site_tram']}"],
                  ["edges A / B-core / B-service / C", f"{s['strata']['A']} / {s['strata']['B_core']} / {s['strata']['B_service']} / {s['strata']['C']}"],
                  ["tram ways", s["tram_ways"]],
                  ["km by tier_tag A (of which tram) / B / C", f"{km(s['km']['A'])} ({km(s['km']['tram'])}) / {km(s['km']['B'])} / {km(s['km']['C'])}"]]), "",
              "### OSM extract", "",
              f"`{P['derived_dir']}/zone_{z}/zone_{z}.osm`: {info['counts']['nodes']} nodes, {info['counts']['ways']} ways, {info['counts']['relations']} relations "
              f"(sha256 `{info['sha256_extract'][:16]}...`, base `{info['sha256_base_osm'][:16]}...`).", "",
              md_table(["", "owned by zone %d" % z, "read-only, other zone", "unowned (outside RING 1)"],
                       [[k, info[k]["owned"], info[k]["read_only_other_zone"], info[k]["unowned"]] for k in ("ways", "nodes", "relations")]), "",
              "### Neighbours and seams", "",
              md_table(["neighbour", "pilot pair", "seam edges", "of which owned by %d" % z, "seam length km", "treatment"],
                       [[m, "yes" if m in pilots else "no", v["n"], v["owned"], km(v["len"]),
                         "shared by the two raters" if m in pilots else "read-only buffer"] for m, v in sorted(x["nb"].items())]), "",
              f"Seam edges excluded from `zone_{z}_units.csv` (owned by {z}, towards a non-pilot zone): **{len(x['excluded'])}** "
              f"({x['excluded_bridge']} of them bridge-group edges; {km(x['excluded_len'])} km; {x['excluded_min']:.1f} S0 minutes).", "",
              "### Spanning ways touching the zone", ""]
        sz = [r for r in sp if z in r["shares"]]
        c = Counter(m for r in sz for m in r["shares"] if m != z)
        L += [f"{len(sz)} spanning ways have length in zone {z}; by partner zone: " + ", ".join(f"{m}: {n}" for m, n in sorted(c.items())) + ".", "",
              md_table(["way", "highway", "name", "length m", "shares", "owner"],
                       [[r["way_id"], r["highway"], r["name"], r["length_m"], fmt_shares(r["shares"]), r["owner_zone"]]
                        for r in sorted(sz, key=lambda r: (-r["length_m"], r["way_id"]))[:15]]), ""]
        L += ["### Bridge groups and islands", ""]
        if x["bridges"]:
            L.append(md_table(["kind", "id", "name", "edge ids", "way ids", "other zone", "length m", "area m2", "end nodes owned elsewhere"],
                              [[r["kind"], r["id"], r["name"], r["edge_ids"], r["way_ids"], r["other_zone"], r["length_m"], r["area_m2"], r["end_nodes_other_zone"]] for r in x["bridges"]]))
            bw = [r for r in x["bridge_ways"] if r["end_nodes_other_zone"]]
            L += ["", f"Owned bridge ways: {len(x['bridge_ways'])}; with an end node owned by another zone: **{len(bw)}** (editing those touches another zone's junction). "
                  f"Full list: `zone_{z}_bridge_ways.csv`.", "",
                  md_table(["group", "way", "highway", "name", "way length m", "end A (owner)", "end B (owner)", "other-zone end nodes"],
                           [[r["group_id"], r["way_id"], r["highway"], r["name"], r["way_length_m"], f"{r['end_a']} ({r['owner_a']})", f"{r['end_b']} ({r['owner_b']})",
                             r["end_nodes_other_zone"]] for r in bw])]
        else:
            L.append(f"Zone {z} owns no bridge groups and no islands.")
    pp = R["pair"]
    L += ["", "## Pilot pair seam (zones " + " and ".join(map(str, pilots)) + ")", "",
          f"Seam edges between the two zones: **{pp['edges']}**, {km(pp['len'])} km (expected {cfg['expected_pair']['seam_edges']} edges, {cfg['expected_pair']['seam_km']} km). "
          f"Marked `pilot_pair_seam = true` in both seams files; the seams with the other neighbours are marked `read_only_neighbour = true`.", "",
          f"Ways spanning both zones: **{len(pp['ways'])}**.", ""]
    if pp["ways"]:
        L.append(md_table(["way", "highway", "name", "length m", "shares", "owner"], [[r["way_id"], r["highway"], r["name"], r["length_m"], fmt_shares(r["shares"]), r["owner_zone"]] for r in pp["ways"]]))
    L += ["", f"Nodes shared between ways owned by zone {pilots[0]} and ways owned by zone {pilots[1]}: **{len(pp['nodes'])}** (`{P['derived_dir']}/pilot_pair_shared_nodes.csv`).", ""]
    if pp["nodes"]:
        L.append(md_table(["node", "owner", "basis", f"ways of zone {pilots[0]}", f"ways of zone {pilots[1]}"],
                          [[r["node_id"], r["owner_zone"], r["owner_basis"], r["ways_a"], r["ways_b"]] for r in pp["nodes"]]))
    L += ["", "## Files", ""] + [f"- `{p}`" for p in R["files"]]
    pathlib.Path(P["report"]).write_text("\n".join(L) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ qgis layers
def write_qgis(cfg, d, ways, nxy, wrows, nrows):
    out = pathlib.Path(cfg["paths"]["qgis_gpkg"])
    out.parent.mkdir(parents=True, exist_ok=True)
    for suf in ("", "-wal", "-shm"):
        pathlib.Path(str(out) + suf).unlink(missing_ok=True)
    crs = d["zones"].crs
    d["zones"].to_file(out, layer="zones", driver="GPKG")
    recs, geoms = [], []
    for w in sorted(ways):
        r = wrows[w]
        recs.append(dict(way_id=w, owner_zone=r["owner_zone"], spans_zones=r["spans_zones"], owner_basis=r["owner_basis"], shares=fmt_shares(r["shares"]),
                         highway=r["highway"], name=r["name"], length_m=r["length_m"], bridge_group=r["bridge_group"]))
        geoms.append(LineString([nxy[n] for n in ways[w][0]]))
    g = gpd.GeoDataFrame(recs, geometry=geoms, crs=crs)
    g["bridge_group"] = g["bridge_group"].astype("Int64")
    g.to_file(out, layer="ways_owner", driver="GPKG", mode="a")
    sh = [(n, r) for n, r in sorted(nrows.items()) if r["shared_across_zones"]]
    gn = gpd.GeoDataFrame([dict(node_id=n, owner_zone=r["owner_zone"], owner_basis=r["owner_basis"], way_zones=r["way_zones"]) for n, r in sh],
                          geometry=[Point(nxy[n]) for n, _ in sh], crs=crs)
    gn.to_file(out, layer="nodes_shared", driver="GPKG", mode="a")


# ------------------------------------------------------------------ main
def main(cfg_path):
    cfg = load_yaml(cfg_path)
    c16 = load_yaml(cfg["base_config"])
    P = cfg["paths"]
    setup_logging(P["log"])
    log.info("start, config %s", cfg_path)
    if subprocess.run(["scripts/verify_inputs.sh"], capture_output=True, text=True).returncode != 0:
        raise SystemExit("verify_inputs.sh failed: input checksums do not match, aborting")
    pilots = [int(z) for z in cfg["pilot_zones"]]
    d = load_inputs(cfg, c16)
    crs = c16["crs_metric"]
    nodes, ways, rels = parse_osm(P["roads_osm"])
    log.info("base osm: %d nodes, %d ways, %d relations", len(nodes), len(ways), len(rels))
    to_m = Transformer.from_crs(4326, crs, always_xy=True)
    ids = sorted(nodes)
    x, y = to_m.transform([nodes[i][0] for i in ids], [nodes[i][1] for i in ids])
    nxy = {i: (a, b) for i, a, b in zip(ids, x, y)}
    wlen = {}
    for w, (nds, _) in ways.items():
        pts = np.array([nxy[n] for n in nds])
        wlen[w] = float(np.hypot(*np.diff(pts, axis=0).T).sum()) if len(pts) > 1 else 0.0
    site_zone, n_stored = site_zones(cfg, d)
    log.info("site zones: %d sites, %d from clusters_zone", len(site_zone), n_stored)
    ufaces = pd.read_csv(pathlib.Path(P["units"]).with_name("ring1_unit_faces.csv"))
    u, sites = unit_tables(d, site_zone, c16)
    im = item_minutes(cfg, d, ufaces, site_zone)
    check("units: all work units have an owner", 7018, int((u["zone"] > 0).sum()))
    check("S0 minutes by owner sum to the total of the unit-face table", round(float(ufaces["minutes_s0"].sum()), 1), round(float(im["minutes_s0"].sum()), 1))
    stats = {z: zone_stats(z, d, u, sites, im, None) for z in range(1, 12)}
    # label-drift guard
    for z in pilots:
        exp = cfg["expected"].get(z)
        if exp is None:
            raise SystemExit(f"no expected values for pilot zone {z} in the config")
        tol = cfg["label_drift_tolerance"]
        bad = []
        for key, act in (("units", stats[z]["units"]), ("s0_minutes", stats[z]["s0_minutes"]), ("sites", stats[z]["sites"]), ("tram_ways", stats[z]["tram_ways"])):
            ok = abs(act - exp[key]) <= tol * exp[key]
            check(f"zone {z} {key} (label-drift guard, {tol:.0%})", exp[key], round(act, 1), ok)
            if not ok:
                bad.append((key, exp[key], act))
        if bad:
            raise SystemExit(f"label drift: zone {z} differs from the v0.2 run beyond {tol:.0%}: {bad}")
    # ownership
    wrows, bmeta = ways_ownership(cfg, d, ways, nxy, wlen, site_zone)
    if bmeta["conflicts"]:
        raise SystemExit(f"ways belong to bridge groups with different owners: {bmeta['conflicts']}")
    nrows, adj, node_conflicts = nodes_ownership(cfg, d, nodes, ways, wrows, wlen, nxy, site_zone)
    rrows = relations_ownership(rels, wrows, nrows)
    check("ways in the base extract all have a row", len(ways), sum(1 for r in wrows.values() if r["in_base_extract"]))
    check("nodes in the base extract all have a row", len(nodes), len(nrows))
    check("relations in the base extract all have a row", len(rels), len(rrows))
    ez_zone = d["edges_zone"].set_index("edge_id")["zone"]
    seg_in = d["segments"][d["segments"]["edge_id"].isin(ez_zone.index)]
    check("ways of RING 1 edges all have an owner", 0, sum(1 for w in set(seg_in["way_id"]) if wrows[int(w)]["owner_zone"] == 0))
    not_in_extract = sum(1 for r in wrows.values() if not r["in_base_extract"])
    odir = pathlib.Path(P["derived_dir"])
    shutil.rmtree(odir, ignore_errors=True)
    odir.mkdir(parents=True)
    cols_w = ["way_id", "owner_zone", "spans_zones", "owner_basis", "bridge_group", "bridge_owner_differs_from_share", "in_base_extract", "shares", "highway", "name", "length_m"]
    wdf = pd.DataFrame([dict(r, shares=fmt_shares(r["shares"])) for _, r in sorted(wrows.items())]).reindex(columns=cols_w)
    wdf["bridge_group"] = wdf["bridge_group"].astype("Int64")
    wdf["bridge_owner_differs_from_share"] = wdf["bridge_owner_differs_from_share"].fillna(False)
    wdf.to_csv(odir / "ownership_ways.csv", index=False)
    pd.DataFrame([r for _, r in sorted(nrows.items())]).astype({"site_id": "Int64", "cluster_id": "Int64", "site_zone_conflict": "Int64"}).to_csv(odir / "ownership_nodes.csv", index=False)
    pd.DataFrame([r for _, r in sorted(rrows.items())]).astype({"from_way": "Int64"}).to_csv(odir / "ownership_relations.csv", index=False)
    # edge -> ways (longest fragment first)
    sg = seg_in.sort_values(["edge_id", "length_m", "way_id"], ascending=[True, False, True])
    edge_ways = {int(k): [(int(w), float(l)) for w, l in zip(g["way_id"], g["length_m"])] for k, g in sg.groupby("edge_id")}
    ctx = dict(crs=crs, wrows=wrows, nrows=nrows, rrows=rrows, edge_ways=edge_ways, bridge_meta=bmeta, ways=ways)
    # frozen layers
    freeze(cfg, d, u, sites, im, pilots, stats)
    write_qgis(cfg, d, ways, nxy, wrows, nrows)
    # packages
    pk = {}
    for z in pilots:
        info, seams = write_package(cfg, d, z, pilots, ctx)
        n_file, excluded = write_units(cfg, d, u, sites, z, seams, ctx)
        brows, bwrows = bridge_files(cfg, d, z, ctx)
        nb = defaultdict(lambda: dict(n=0, owned=0, len=0.0))
        for r in seams["rows"]:
            v = nb[r["other_zone"]]
            v["n"] += 1
            v["owned"] += r["owner_zone"] == z
            v["len"] += r["length_m"]
        ids_ex = set(excluded["id"].astype(int))
        brg = set(d["bridges"]["edge_id"].astype(int))
        pk[z] = dict(info=info, seams=seams, n_units_file=n_file, nb=dict(nb), excluded=sorted(ids_ex),
                     excluded_bridge=len([k for k in ids_ex if k in brg]), excluded_len=float(d["edge_meta"].loc[sorted(ids_ex), "length_m"].sum()) if ids_ex else 0.0,
                     excluded_min=float(im[(im["unit_type"] != "site") & im["key"].isin(ids_ex)]["minutes_s0"].sum()), bridges=brows, bridge_ways=bwrows)
        # bridge-group edges kept in the units file although they are seam edges
    # pilot pair
    pa = pilots[:2]
    pair_edges = [r for z in pa[:1] for r in pk[z]["seams"]["rows"] if r["other_zone"] == pa[1]]
    pair = dict(edges=len(pair_edges), len=sum(r["length_m"] for r in pair_edges))
    pair["ways"] = sorted((r for r in wrows.values() if pa[0] in r["shares"] and pa[1] in r["shares"]), key=lambda r: (-r["length_m"], r["way_id"]))
    pn = []
    for n, r in sorted(nrows.items()):
        wz = {int(a.split(":")[0]) for a in r["way_zones"].split(";") if a}
        if pa[0] in wz and pa[1] in wz:
            wa = [w for w in adj[n] if wrows[w]["owner_zone"] == pa[0]]
            wb = [w for w in adj[n] if wrows[w]["owner_zone"] == pa[1]]
            pn.append(dict(node_id=n, owner_zone=r["owner_zone"], owner_basis=r["owner_basis"], ways_a=";".join(map(str, wa)), ways_b=";".join(map(str, wb))))
    pair["nodes"] = pn
    pd.DataFrame(pn, columns=["node_id", "owner_zone", "owner_basis", "ways_a", "ways_b"]).to_csv(odir / "pilot_pair_shared_nodes.csv", index=False)
    ep = cfg["expected_pair"]
    check("pilot pair seam edges", ep["seam_edges"], pair["edges"])
    check("pilot pair seam km", ep["seam_km"], round(pair["len"] / 1000, 2), abs(pair["len"] / 1000 - ep["seam_km"]) <= ep["seam_km_tol"])
    tot = {k: sum(stats[z]["strata"][k] for z in pa) for k in ("A", "B_core", "B_service", "C", "tram")}
    for k, key in (("A", "edges_A"), ("B_core", "edges_B_core"), ("B_service", "edges_B_service"), ("C", "edges_C"), ("tram", "tram_ways")):
        check(f"pilot pair {key} (decision D6)", ep[key], tot[k])
    # sanity: seam edges between the pair are marked in both directions
    for z in pa:
        sdf = pd.read_csv(odir / f"zone_{z}" / f"zone_{z}_seams.csv")
        check(f"zone {z} seams file: pilot_pair_seam edges", ep["seam_edges"], int(sdf["pilot_pair_seam"].sum()))
    R = dict(pilots=pilots, stats=stats, wrows=wrows, nrows=nrows, rrows=rrows, pk=pk, pair=pair, not_in_extract=not_in_extract,
             nearest_ways=sum(1 for r in wrows.values() if r["owner_basis"] == "nearest_face"),
             nearest_nodes=sum(1 for r in nrows.values() if r["owner_basis"] == "nearest_face"), files=[], node_conflicts=node_conflicts)
    files = sorted(str(p) for p in odir.rglob("*") if p.is_file()) + [P["frozen_gpkg"], P["qgis_gpkg"]]
    R["files"] = files
    write_report(cfg, R)
    dig = [f"{p} {sha256(p)}" for p in sorted(str(p) for p in odir.rglob("*") if p.is_file())]
    pathlib.Path(P["interim_dir"], "23_digest.txt").write_text("\n".join(dig) + "\n")
    fails = [c for c in CHECKS if c[3] != "PASS"]
    print(md_table(["Check", "Expected", "Actual", "Result"], [list(c) for c in CHECKS]))
    for z in pilots:
        s = stats[z]
        print(f"zone {z}: units {s['units']}, S0 {s['s0_minutes']:.1f} min, sites {s['sites']}, tram ways {s['tram_ways']}")
    log.info("done, %d checks, %d failed", len(CHECKS), len(fails))
    if fails:
        raise SystemExit(f"{len(fails)} checks failed, see {P['report']}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "config/23_zone_packages.yaml")
