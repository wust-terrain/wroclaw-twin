"""Task 02a: site diagnostics and reproducible pilot sample (read-only analysis).

Usage: uv run python src/14_pilot_sample.py [config/14_pilot_sample.yaml]
"""
import hashlib
import logging
import pathlib
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
import yaml
from shapely.geometry import Point

log = logging.getLogger("pilot")


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


def lonlat(cfg, x, y):
    g = gpd.GeoSeries(gpd.points_from_xy(x, y), crs=cfg["crs_metric"]).to_crs(cfg["crs_exchange"])
    return g.x.to_numpy(), g.y.to_numpy()


def build_sites(cfg, units):
    """One row per site_id: centroid, members, composition, diameter, hull."""
    labels = cfg["site_unit_types"]
    order = list(labels.values())
    mem = units[units["site_id"].notna()].copy()
    mem["site_id"] = mem["site_id"].astype(int)
    rows, hulls = [], []
    for sid, g in mem.groupby("site_id", sort=True):
        pts = g[["x", "y"]].to_numpy()
        if len(pts) > 1:
            d = np.sqrt(((pts[:, None, :] - pts[None, :, :]) ** 2).sum(-1))
            diam = float(d.max())
        else:
            diam = 0.0
        present = {labels[t] for t in g["unit_type"]}
        comp = "+".join(l for l in order if l in present)
        hull = shapely.MultiPoint(pts).convex_hull
        if hull.geom_type != "Polygon" or len(pts) <= 2:
            hull = hull.buffer(cfg["hull_buffer_m"])
        counter = g["counter_nearby"].min()
        rows.append({"site_id": sid, "x": pts[:, 0].mean(), "y": pts[:, 1].mean(), "n_units": len(g),
                     "composition": comp, "diameter_m": round(diam, 1),
                     "counter_nearby": counter, "members": ";".join(f"{t}:{i}" for t, i in zip(g["unit_type"], g["id"]))})
        hulls.append(hull)
    sites = pd.DataFrame(rows)
    sites["lon"], sites["lat"] = lonlat(cfg, sites["x"], sites["y"])
    return sites, hulls


def draw(rng, cand, quota, accepted_xy, used, spacing):
    """Take candidates in random order; reject those used already or closer than `spacing` to an accepted unit.

    Returns (chosen index list, redraws). `accepted_xy` and `used` are updated in place.
    """
    chosen, redraws = [], 0
    for i in rng.permutation(len(cand)):
        if len(chosen) == quota:
            break
        row = cand.iloc[i]
        key = (row["unit_type"], row["id"])
        p = np.array([row["x"], row["y"]])
        if key in used or (accepted_xy and np.min(np.hypot(*(np.array(accepted_xy) - p).T)) < spacing):
            redraws += 1
            continue
        chosen.append(cand.index[i])
        accepted_xy.append(tuple(p))
        used.add(key)
    return chosen, redraws


def largest_remainder(total, weights):
    w = pd.Series(weights, dtype=float)
    q = w / w.sum() * total
    base = np.floor(q).astype(int)
    rest = total - int(base.sum())
    frac = (q - base).sort_values(ascending=False, kind="stable")
    for k in frac.index[:rest]:
        base[k] += 1
    return base.to_dict()


def edge_candidates(cfg, name, sp, segs):
    t = cfg["tier_variant"]
    s = segs[segs["kind"].isin(sp["kinds"])] if "kinds" in sp else segs
    if name == "A":
        s = s[(s[t] == "A") & (~s["highway"].isin(sp["exclude_highway"]))]
    elif name == "B-core":
        s = s[s["highway"].isin(sp["highway"])]
    elif name == "B-service":
        s = s[(s[t] == sp["tier"]) & s["highway"].isin(sp["highway"]) & s["service"].isna()]
    elif name == "C":
        s = s[(s["kind"] == "dead_end_spur") | (s[t] == "C")]
        s = s[s["highway"] != "tram"]
    elif name == "tram":
        s = s[s["highway"].isin(sp["highway"])]
    if "min_length_m" in sp:
        s = s[s["length_m"] >= sp["min_length_m"]]
    return s


def site_extras(units):
    """Per-site complexity columns: signal nodes, max junction degree, tram crossings."""
    m = units[units["site_id"].notna()].copy()
    m["site_id"] = m["site_id"].astype(int)
    ids = sorted(m["site_id"].unique())
    sig = m[m["unit_type"] == "signal_cluster"].groupby("site_id")["n_nodes"].sum()
    deg = m[m["unit_type"] == "junction_cluster_complex"].groupby("site_id")["max_degree"].max()
    tram = m[m["unit_type"] == "tram_crossing"].groupby("site_id").size()
    return pd.DataFrame({"n_signal_nodes": sig.reindex(ids, fill_value=0), "max_degree": deg.reindex(ids),
                         "n_tram_crossings": tram.reindex(ids, fill_value=0)})


def zoom_url(cfg, xmin, ymin, xmax, ymax):
    xs, ys = lonlat(cfg, [xmin, xmax, xmin, xmax], [ymin, ymin, ymax, ymax])
    return f"{cfg['josm']['base']}?left={xs.min():.6f}&right={xs.max():.6f}&bottom={ys.min():.6f}&top={ys.max():.6f}"


def stratum_minutes(acfg, stratum):
    """Assumed minutes per unit for a stratum label like 'site: complex' or 'edge: A'."""
    kind, name = stratum.split(": ")
    if kind == "site":
        return acfg["assumed_minutes"]["site_large" if name == "large" else "site"]
    return acfg["assumed_minutes"][name]


def sha256_of(path):
    p = pathlib.Path(path)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.exists() else None


def assign(acfg, smp):
    """Rater lists: warm-up first, then overlap + round-robin share of the rest in balanced-prefix order."""
    n = acfg["n_raters"]
    assert n in (2, 3), "n_raters must be 2 or 3"
    raters = acfg["rater_ids"][:n]
    meas = smp[~smp["warmup"]]
    warm = smp[smp["warmup"]]
    strata = list(dict.fromkeys(meas["stratum"]))
    arng = np.random.default_rng([acfg["seed"], 0])
    own = {r: [] for r in raters}
    ptr = 0   # the pointer carries across strata so the totals stay within +-1 as well
    for s in strata:
        ids = meas[(meas["stratum"] == s) & ~meas["overlap"]]["pilot_id"].to_numpy()
        for pid in ids[arng.permutation(len(ids))]:
            own[raters[ptr % n]].append(pid)
            ptr += 1
    stratum_of = smp.set_index("pilot_id")["stratum"]
    overlap_ids = list(meas[meas["overlap"]]["pilot_id"])
    lo, hi = acfg["overlap_key_range"]
    rows = []
    for j, r in enumerate(raters):
        rng = np.random.default_rng([acfg["seed"], j + 1])
        keys = {}
        by_s = {}
        for pid in own[r]:
            by_s.setdefault(stratum_of[pid], []).append(pid)
        for s in strata:
            ids = by_s.get(s, [])
            n_h = len(ids)
            for k, pid in enumerate(rng.permutation(ids), start=1):
                keys[pid] = (k - rng.uniform()) / n_h
        for pid in overlap_ids:
            keys[pid] = rng.uniform(lo, hi)
        order = sorted(keys, key=lambda p: (keys[p], p))
        seq = list(warm["pilot_id"]) + order
        ov = set(overlap_ids)
        w = set(warm["pilot_id"])
        for i, pid in enumerate(seq, start=1):
            rows.append({"rater": r, "order_index": i, "pilot_id": pid, "overlap": pid in ov, "warmup": pid in w})
    return pd.DataFrame(rows), raters


def write_assignments(cfg, acfg, smp, summary, warm_summary, prev_sha, sha_sample, checks):
    P = cfg["paths"]
    asg, raters = assign(acfg, smp)
    pathlib.Path(P["assignments_csv"]).parent.mkdir(parents=True, exist_ok=True)
    asg.to_csv(P["assignments_csv"], index=False)
    sha_asg = sha256_of(P["assignments_csv"])
    st = smp.set_index("pilot_id")
    meas = smp[~smp["warmup"]]
    strata = list(dict.fromkeys(meas["stratum"]))
    short = [("s:" + s.split(": ")[1]) if s.startswith("site") else "e:" + s.split(": ")[1] for s in strata]
    lists = {r: asg[(asg["rater"] == r) & ~asg["warmup"]]["pilot_id"].tolist() for r in raters}
    n_warm = int(smp["warmup"].sum())

    # ---- checks on the assignment ----
    ov = set(meas[meas["overlap"]]["pilot_id"])
    cnt = {r: pd.Series([st.loc[p, "stratum"] for p in lists[r] if p not in ov]).value_counts().reindex(strata, fill_value=0) for r in raters}
    cdf = pd.DataFrame(cnt)
    spread = int((cdf.max(axis=1) - cdf.min(axis=1)).max())
    tot = [len(lists[r]) for r in raters]
    checks.append(("assignment: max per-stratum difference between raters (non-overlap units)", "<= 1", spread, spread <= 1))
    checks.append(("assignment: max total difference between raters", "<= 1", max(tot) - min(tot), max(tot) - min(tot) <= 1))
    union = set().union(*map(set, lists.values()))
    checks.append(("assignment: every measured unit assigned", len(meas), len(union), len(meas) == len(union)))
    checks.append(("assignment: overlap units in every list", len(ov), min(len(ov & set(lists[r])) for r in raters),
                   all(ov <= set(lists[r]) for r in raters)))
    warm_first = all(list(asg[(asg["rater"] == r)]["pilot_id"][:n_warm]) == list(smp[smp["warmup"]]["pilot_id"]) for r in raters)
    checks.append(("assignment: warm-up units first, same order for every rater", True, warm_first, warm_first))
    hi = acfg["overlap_key_range"][1]
    worst = max((lists[r].index(p) + 1) / len(lists[r]) for r in raters for p in ov)
    checks.append((f"assignment: overlap units within the first {hi:.0%} of every list (max position fraction)", f"<= {hi}",
                   round(worst, 3), worst <= hi))

    # ---- prefix balance ----
    pref_rows, dev_max = [], 0.0
    for r in raters:
        n = len(lists[r])
        full = pd.Series([st.loc[p, "stratum"] for p in lists[r]]).value_counts().reindex(strata, fill_value=0)
        for fr in acfg["prefix_fractions"]:
            L = int(np.floor(fr * n + 0.5))
            c = pd.Series([st.loc[p, "stratum"] for p in lists[r][:L]]).value_counts().reindex(strata, fill_value=0)
            dev = float((c - full * L / n).abs().max())
            dev_max = max(dev_max, dev)
            pref_rows.append((r, f"{int(fr * 100)}%", L, *c.tolist(), f"{dev:.2f}"))

    # ---- planning projection (a guess) ----
    budget = (acfg["hours_per_rater"] - acfg["warmup_hours"]) * 60
    proj, cum_rows, ov_pos = [], [], []
    warm_min = sum(stratum_minutes(acfg, s) for s in smp[smp["warmup"]]["stratum"])
    for r in raters:
        mins = np.array([stratum_minutes(acfg, st.loc[p, "stratum"]) for p in lists[r]])
        cum = np.cumsum(mins)
        cut = int((cum <= budget).sum())
        c = pd.Series([st.loc[p, "stratum"] for p in lists[r][:cut]]).value_counts().reindex(strata, fill_value=0)
        proj.append((r, len(mins), int(cum[-1]), cut, f"{100 * cut / len(mins):.0f}%", *c.tolist()))
        for k in sorted(set(list(range(10, len(mins), 10)) + [cut, len(mins)])):
            cum_rows.append((r, k, int(cum[k - 1]), "<- cut" if k == cut else ""))
        pos = sorted((lists[r].index(p) + 1, p) for p in ov)
        ov_pos.append((r, ", ".join(f"{p}@{k}" for k, p in pos), sum(1 for k, _ in pos if k <= cut), len(pos)))

    L = ["# Task 02b: pilot extension, rater assignments and planning projection", "",
         "Config: `config/14_pilot_sample.yaml`, `config/pilot_assignments.yaml`. Numbers marked `[PROPOSED]` are not agreed with the team. "
         "Analysis only; `scope.yaml`, polygon, D2-D4 and `tiers.yaml` untouched.", "",
         "## Checks", "", md_table(["Check", "Expected", "Actual", "Result"],
                                   [(a, b, c, "PASS" if d else "FAIL") for a, b, c, d in checks]), "",
         "## Sample size by stratum (analysis sample)", ""]
    new = {s[0]: s for s in summary}
    old_names = [s[0] for s in summary if s[0] != "site: large"]
    rows = [(n, new[n][1], new[n][3], new[n][3], new[n][2], new[n][4]) for n in old_names]
    rows.append(("site: large", 0, 0, new["site: large"][3], new["site: large"][2], new["site: large"][4]))
    L += [md_table(["stratum", "requested (02a)", "drawn (02a)", "drawn (02b)", "eligible", "redraws"], rows), "",
          f"Total: 02a {sum(r[2] for r in rows)}, 02b {sum(r[3] for r in rows)}. `site: large` = sites with n_units >= {cfg['site_large']['min_units']}, "
          f"RNG stream seed + {cfg['site_large']['seed_offset']}; redraws = candidates rejected because already in the sample or closer than "
          f"{cfg['min_spacing_m']} m to an accepted unit. New ids continue after P{cfg['expected']['base_rows']:03d}.", "",
          "## Warm-up set (not part of the analysis sample)", "",
          f"RNG stream seed + {cfg['warmup']['seed_offset']}; units not in the sample and >= {cfg['min_spacing_m']} m from every sample unit "
          "and from each other. Order: assumed minutes of the stratum, then size (n_units for sites, length for edges).", "",
          md_table(["pilot_id", "stratum", "unit", "size", "lon", "lat"],
                   [(r.pilot_id, r.stratum, f"{r.unit_type}:{r.id}", int(r.n_units) if r.unit_type == "site" else f"{r.length_m} m",
                     f"{r.lon:.6f}", f"{r.lat:.6f}") for r in smp[smp["warmup"]].itertuples()]), "",
          "Warm-up draws: " + "; ".join(f"{s[0]} eligible {s[2]}, redraws {s[4]}" for s in warm_summary) +
          f". Assumed warm-up time {warm_min} min against {acfg['warmup_hours'] * 60} min allotted.", "",
          f"## Units per rater by stratum ({len(raters)} raters, `n_raters` = {acfg['n_raters']})", ""]
    full_cnt = pd.DataFrame({r: pd.Series([st.loc[p, "stratum"] for p in lists[r]]).value_counts().reindex(strata, fill_value=0) for r in raters})
    L += [md_table(["stratum", *[f"{r} non-overlap" for r in raters], *[f"{r} total" for r in raters]],
                   [(s, *[cdf.loc[s, r] for r in raters], *[full_cnt.loc[s, r] for r in raters]) for s in strata] +
                   [("**all**", *[cdf[r].sum() for r in raters], *[full_cnt[r].sum() for r in raters])]), "",
          f"Max per-stratum difference between raters (non-overlap units): {spread}. Round-robin pointer carries across strata. "
          "Positions below are positions in the measured list (warm-up excluded); `order_index` in the CSV counts the warm-up units too "
          f"(measured position = order_index - {n_warm}).", "",
          "## Overlap units and their positions", "",
          md_table(["pilot_id", "stratum"], [(p, st.loc[p, "stratum"]) for p in sorted(ov)]), "",
          md_table(["rater", "overlap units @ measured position", "before the projected cut", "of"], ov_pos), "",
          "## Prefix balance (count per stratum in the first 25/50/75% of the measured list)", "",
          "Overlap units are counted in their own stratum. Last column: max over strata of |count - proportional share of the rater's full list|. "
          "Prefix length = round(fraction x list length). Columns: `s:` site stratum, `e:` edge stratum.", "",
          md_table(["rater", "prefix", "n", *short, "max dev"], pref_rows), "",
          f"Largest deviation over all raters and prefixes: {dev_max:.2f} units.", "",
          "## Planning projection (a GUESS, to be replaced by measured times)", "",
          "Uses `assumed_minutes` from `config/pilot_assignments.yaml`: " +
          ", ".join(f"{k} {v}" for k, v in acfg["assumed_minutes"].items()) + ". **[PROPOSED] unmeasured planning guess; "
          "it must be replaced by the times measured in the pilot. Nothing here is a result.** "
          f"Budget for measured units = {acfg['hours_per_rater']} h - {acfg['warmup_hours']} h warm-up = {budget:g} min. "
          "Cut position = number of units whose cumulative expected minutes fit in the budget.", "",
          md_table(["rater", "measured units", "total expected min", "cut position", "of list", *short], proj), "",
          "Cumulative expected minutes (every 10th position, the cut and the end):", "",
          md_table(["rater", "position", "cum. min", ""], cum_rows), "",
          "## Output hashes (sha256)", "",
          md_table(["file", "sha256", "same as previous run"],
                   [(P["sample_csv"], f"`{sha_sample}`", {None: "no previous file", sha_sample: "yes"}.get(prev_sha["sample"], "no")),
                    (P["assignments_csv"], f"`{sha_asg}`", {None: "no previous file", sha_asg: "yes"}.get(prev_sha["assign"], "no"))]), "",
          "## Outputs", "", f"- `{P['sample_csv']}` (sample + warm-up rows, new columns)", f"- `{P['sample_gpkg']}`",
          f"- `{P['assignments_csv']}`", f"- `{P['record_sheet']}` (header only)", ""]
    pathlib.Path(P["report_assign"]).write_text("\n".join(L))
    log.info("assignments sha256 %s", sha_asg)
    log.info("projection (rater, units, total min, cut): %s", [(p[0], p[1], p[2], p[3]) for p in proj])


def main():
    cfg = load_yaml(sys.argv[1] if len(sys.argv) > 1 else "config/14_pilot_sample.yaml")
    P = cfg["paths"]
    setup_logging(P["log"])
    crs = cfg["crs_metric"]
    checks = []

    def check(name, expected, actual, ok=None):
        checks.append((name, expected, actual, (expected == actual) if ok is None else ok))

    units = pd.read_csv(P["units"])
    poly = gpd.read_file(P["polygons"], layer=P["polygon_layer"]).geometry.iloc[0]
    shapely.prepare(poly)

    # ---------- 1. site diagnostics ----------
    sites, hulls = build_sites(cfg, units)
    check("sites", cfg["expected"]["sites"], len(sites))
    check("site member units", cfg["expected"]["site_member_units"], int(sites["n_units"].sum()))
    for p in (sites["x"], sites["y"]):
        assert p.notna().all()
    gs = gpd.GeoDataFrame(sites.drop(columns=["lon", "lat"]), geometry=gpd.points_from_xy(sites["x"], sites["y"]), crs=crs)
    gh = gpd.GeoDataFrame(sites[["site_id", "n_units", "composition", "diameter_m"]], geometry=hulls, crs=crs)
    out = pathlib.Path(P["sites_gpkg"])
    out.unlink(missing_ok=True)
    gs.to_file(out, layer="sites", driver="GPKG")
    gh.to_file(out, layer="site_hulls", driver="GPKG")

    diam = sites["diameter_m"]
    pct = {"p50": np.percentile(diam, 50), "p90": np.percentile(diam, 90), "p99": np.percentile(diam, 99), "max": diam.max()}
    multi = sites[sites["n_units"] > 1]
    pct_multi = {k: f(multi["diameter_m"]) for k, f in
                 (("p50", lambda s: np.percentile(s, 50)), ("p90", lambda s: np.percentile(s, 90)),
                  ("p99", lambda s: np.percentile(s, 99)), ("max", lambda s: s.max()))}
    top = sites.sort_values(["n_units", "diameter_m", "site_id"], ascending=[False, False, True]).head(cfg["top_sites"])
    big = sites[sites["diameter_m"] > cfg["site_diameter_flag_m"]].sort_values("diameter_m", ascending=False)

    # ---------- 2. pilot sample ----------
    segs = units[units["unit_type"] == "segment"].copy()
    own = gpd.read_file(P["ownership"], layer="edges")
    segs["service"] = segs["id"].map(own.set_index("edge_id")["service"])   # tram (id < 0) -> NaN
    seg_geom = {int(r.edge_id): r.geometry for r in own.itertuples() if r.edge_id >= 0 and r.ring1}
    tram = gpd.read_file(P["ownership"], layer="tram_segments")
    tram = tram[tram["ring1"]]
    assert tram["edge_id"].is_unique
    seg_geom |= {int(r.edge_id): r.geometry for r in tram.itertuples()}
    rng = np.random.default_rng(cfg["seed"])
    accepted, used = [], set()
    drawn = []    # (stratum, unit_type, index in `units`/sites, kind)
    summary = []  # stratum, requested, eligible, drawn, redraws
    site_rows = {}

    for strat, n in cfg["site_strata"].items():
        cand = sites[sites["composition"] == strat].sort_values("site_id").copy()
        cand["unit_type"], cand["id"] = "site", cand["site_id"]
        ch, rd = draw(rng, cand, n, accepted, used, cfg["min_spacing_m"])
        for i in ch:
            drawn.append((strat, "site", i))
        summary.append((f"site: {strat}", n, len(cand), len(ch), rd))

    for strat, sp in cfg["edge_strata"].items():
        cand = edge_candidates(cfg, strat, sp, segs).sort_values("id")
        if sp.get("stratify_by_highway_km"):
            km = cand.groupby("highway")["length_m"].sum()
            quota = largest_remainder(sp["n"], km)
            ch, rd = [], 0
            for h in sorted(quota):
                c, r = draw(rng, cand[cand["highway"] == h], quota[h], accepted, used, cfg["min_spacing_m"])
                ch += c
                rd += r
            alloc = ", ".join(f"{h} {quota[h]}" for h in sorted(quota))
            note = f"allocation by km: {alloc}"
        else:
            ch, rd = draw(rng, cand, sp["n"], accepted, used, cfg["min_spacing_m"])
            note = ""
        for i in ch:
            drawn.append((strat, "segment", i))
        summary.append((f"edge: {strat}", sp["n"], len(cand), len(ch), rd))
        if note:
            summary[-1] += (note,)

    # ---------- 02b extension: large sites and warm-up set (separate RNG streams) ----------
    ext = "site_large" in cfg
    acfg = load_yaml(P["assignments_cfg"]) if ext else None
    large_drawn, warm_drawn, warm_summary = [], [], []
    if ext:
        SL, W = cfg["site_large"], cfg["warmup"]
        cand = sites[sites["n_units"] >= SL["min_units"]].sort_values("site_id").copy()
        cand["unit_type"], cand["id"] = "site", cand["site_id"]
        ch, rd = draw(np.random.default_rng(cfg["seed"] + SL["seed_offset"]), cand, SL["n"], accepted, used, cfg["min_spacing_m"])
        large_drawn = [("large", "site", i) for i in ch]
        summary.append(("site: large", SL["n"], len(cand), len(ch), rd))
        wrng = np.random.default_rng(cfg["seed"] + W["seed_offset"])
        for strat in W["sites"]:
            cand = sites[sites["composition"] == strat].sort_values("site_id").copy()
            cand["unit_type"], cand["id"] = "site", cand["site_id"]
            ch, rd = draw(wrng, cand, 1, accepted, used, cfg["min_spacing_m"])
            warm_drawn += [(strat, "site", i) for i in ch]
            warm_summary.append((f"site: {strat}", 1, len(cand), len(ch), rd))
        for strat in W["edges"]:
            cand = edge_candidates(cfg, strat, cfg["edge_strata"][strat], segs).sort_values("id")
            ch, rd = draw(wrng, cand, 1, accepted, used, cfg["min_spacing_m"])
            warm_drawn += [(strat, "segment", i) for i in ch]
            warm_summary.append((f"edge: {strat}", 1, len(cand), len(ch), rd))

    # ---------- assemble the sample ----------
    def make_row(strat, ut, i):
        if ut == "site":
            s = sites.loc[i]
            return ({"unit_type": "site", "id": int(s["site_id"]), "site_id": int(s["site_id"]), "stratum": f"site: {strat}",
                         "x": s["x"], "y": s["y"], "length_m": np.nan, "highway": None, "service": None, "tier_tag": None,
                         "composition": s["composition"], "counter_nearby": s["counter_nearby"],
                         "n_units": int(s["n_units"]), "diameter_m": s["diameter_m"]})
        else:
            s = segs.loc[i]
            return ({"unit_type": "segment", "id": int(s["id"]), "site_id": None, "stratum": f"edge: {strat}",
                         "x": s["x"], "y": s["y"], "length_m": s["length_m"], "highway": s["highway"],
                         "service": s["service"], "tier_tag": s[cfg["tier_variant"]], "composition": None,
                         "counter_nearby": s["counter_nearby"], "n_units": None, "diameter_m": None})

    cs = cfg["area_cell_m"]

    def to_frame(items):
        df = pd.DataFrame([make_row(*d) for d in items])
        df["lon"], df["lat"] = lonlat(cfg, df["x"], df["y"])
        df["area_cell"] = [f"{int(x // cs)}_{int(y // cs)}" for x, y in zip(df["x"], df["y"])]
        return df

    smp = to_frame(drawn)

    # overlap set: different strata, seeded
    orng = np.random.default_rng(cfg["seed"] + 1)
    smp["overlap"] = False
    for kind, key in (("site", "sites"), ("segment", "edges")):
        sub = smp[smp["unit_type"] == kind]
        strata = sorted(sub["stratum"].unique())
        pick = orng.permutation(len(strata))[: cfg["overlap"][key]]
        for k in pick:
            cands = sub[sub["stratum"] == strata[k]].index.to_numpy()
            smp.loc[cands[orng.integers(len(cands))], "overlap"] = True

    smp["_ord"] = smp["stratum"].map({f"site: {s}": j for j, s in enumerate(cfg["site_strata"])} |
                                     {f"edge: {s}": 100 + j for j, s in enumerate(cfg["edge_strata"])})
    smp = smp.sort_values(["_ord", "id"], kind="stable").reset_index(drop=True).drop(columns="_ord")
    smp.insert(0, "pilot_id", [f"P{j + 1:03d}" for j in range(len(smp))])
    n_base = len(smp)
    if ext:
        lg = to_frame(large_drawn)
        lg["overlap"] = False
        lg.insert(0, "pilot_id", [f"P{n_base + j + 1:03d}" for j in range(len(lg))])
        wm = to_frame(warm_drawn)
        wm["overlap"] = False
        wm["_size"] = np.where(wm["unit_type"] == "site", wm["n_units"], wm["length_m"])
        wm["_min"] = [stratum_minutes(acfg, s) for s in wm["stratum"]]
        wm = wm.sort_values(["_min", "_size", "id"], kind="stable").drop(columns=["_min", "_size"]).reset_index(drop=True)
        wm.insert(0, "pilot_id", [f"W{j + 1:02d}" for j in range(len(wm))])
        lg["warmup"], wm["warmup"] = False, True
        smp["warmup"] = False
        smp = pd.concat([smp, lg, wm], ignore_index=True)
    for c in ("x", "y"):
        smp[c] = smp[c].round(2)
    smp["length_m"] = smp["length_m"].round(2)
    smp["lon"], smp["lat"] = smp["lon"].round(6), smp["lat"].round(6)
    cols = ["pilot_id", "unit_type", "id", "site_id", "stratum", "x", "y", "lon", "lat", "length_m", "highway", "service",
            "tier_tag", "composition", "overlap", "area_cell", "counter_nearby", "n_units", "diameter_m"]
    smp = smp[cols + (["warmup"] if ext else [])]
    prev_sha = {"sample": sha256_of(P["sample_csv"]), "assign": sha256_of(P["assignments_csv"]) if ext else None}
    if ext:
        base_sha = hashlib.sha256(smp.iloc[:n_base][cols].to_csv(index=False).encode()).hexdigest()
        ex = site_extras(units)
        for c in ex.columns:
            smp[c] = smp["site_id"].map(ex[c]).astype("Int64")
        urls_j, urls_s = [], []
        jc = cfg["josm"]
        for r in smp.itertuples():
            if r.unit_type == "site":
                h = jc["point_box_m"] / 2
                urls_j.append(zoom_url(cfg, r.x - h, r.y - h, r.x + h, r.y + h))
            else:
                x0, y0, x1, y1 = seg_geom[int(r.id)].bounds
                d = jc["line_pad_m"]
                urls_j.append(zoom_url(cfg, x0 - d, y0 - d, x1 + d, y1 + d))
            urls_s.append(f"{cfg['streetview_base']}{r.lat:.6f},{r.lon:.6f}")
        smp["josm_zoom_url"], smp["streetview_url"] = urls_j, urls_s
    pathlib.Path(P["sample_csv"]).parent.mkdir(parents=True, exist_ok=True)
    smp.to_csv(P["sample_csv"], index=False)
    sha = sha256_of(P["sample_csv"])

    # gpkg
    pts = gpd.GeoDataFrame(smp, geometry=gpd.points_from_xy(smp["x"], smp["y"]), crs=crs)
    es = smp[smp["unit_type"] == "segment"]
    lines = gpd.GeoDataFrame(es, geometry=[seg_geom[i] for i in es["id"]], crs=crs)
    g = pathlib.Path(P["sample_gpkg"])
    g.unlink(missing_ok=True)
    pts.to_file(g, layer="pilot", driver="GPKG")
    lines.to_file(g, layer="pilot_edges", driver="GPKG")

    rs = pathlib.Path(P["record_sheet"])
    rs.parent.mkdir(parents=True, exist_ok=True)
    rs.write_text(",".join(cfg["record_sheet_columns"]) + "\n" if ext else
                  "pilot_id,rater,start_time,end_time,minutes,defects_found,edits_made,checklist_complete,notes\n")

    # ---------- checks ----------
    xy = smp[["x", "y"]].to_numpy()
    dmat = np.sqrt(((xy[:, None] - xy[None]) ** 2).sum(-1)) + np.eye(len(xy)) * 1e9
    # ownership (D3) is by end cluster for stubs and spurs, so their midpoint can lie outside the polygon
    mid_out = smp[~shapely.contains_xy(poly, xy[:, 0], xy[:, 1])]
    check("sampled units owned by RING 1 (in work-unit table)", len(smp),
          int(smp.merge(units[["unit_type", "id"]], on=["unit_type", "id"]).shape[0]) + int((smp["unit_type"] == "site").sum()))
    check("info: sampled units with midpoint outside the polygon (all edges, owned via end cluster)", 0, len(mid_out),
          bool((mid_out["unit_type"] == "segment").all()))
    check("duplicate (unit_type, id)", 0, int(smp.duplicated(["unit_type", "id"]).sum()))
    check("min pairwise distance >= spacing (m)", f">= {cfg['min_spacing_m']}", round(dmat.min(), 1), dmat.min() >= cfg["min_spacing_m"])
    check("overlap units", 8, int(smp["overlap"].sum()), int(smp["overlap"].sum()) == cfg["overlap"]["sites"] + cfg["overlap"]["edges"])
    if ext:
        check("02a columns of the first base_rows rows unchanged (sha256)", cfg["expected"]["base_sample_sha256"], base_sha)
        check("base rows / pilot_ids P001..P084", cfg["expected"]["base_rows"], n_base)
        check("large sites drawn", cfg["site_large"]["n"], len(large_drawn))
        check("warm-up units drawn", 6, int(smp["warmup"].sum()))
        check("warm-up ids W01..W06", [f"W{j:02d}" for j in range(1, 7)], list(smp[smp["warmup"]]["pilot_id"]))
    check("pilot_edges layer rows", int((smp["unit_type"] == "segment").sum()), len(lines))

    ncell = smp["area_cell"].nunique()
    total_cells = len({(int(x // cs), int(y // cs)) for x, y in zip(units["x"], units["y"])})

    # ---------- report ----------
    L = ["# Task 02a: pilot sample and site diagnostics", "",
         f"Inputs: `{P['units']}`, `{P['ownership']}`, `config/tiers.yaml` via column `{cfg['tier_variant']}`. "
         "Strata, sizes, seed and spacing are `[PROPOSED]` (`config/14_pilot_sample.yaml`). Analysis only.", "",
         "## Checks", "", md_table(["Check", "Expected", "Actual", "Result"],
                                   [(a, b, c, "PASS" if d else "FAIL") for a, b, c, d in checks]), "",
         "## 1. Site diagnostics", "",
         f"Sites: {len(sites)} (member units {int(sites['n_units'].sum())}). Units per site:", "",
         md_table(["n_units", "sites"], [(k, v) for k, v in sites["n_units"].value_counts().sort_index().items()]), "",
         "Composition:", "", md_table(["composition", "sites"], [(k, v) for k, v in sites["composition"].value_counts().items()]), "",
         "Site diameter (max distance between member unit centroids, m):", "",
         md_table(["set", "p50", "p90", "p99", "max"],
                  [("all sites", *(f"{pct[k]:.1f}" for k in ("p50", "p90", "p99", "max"))),
                   (f"sites with >1 unit ({len(multi)})", *(f"{pct_multi[k]:.1f}" for k in ("p50", "p90", "p99", "max")))]), "",
         f"{cfg['top_sites']} largest sites (by n_units, then diameter):", "",
         md_table(["site_id", "lon", "lat", "n_units", "composition", "diameter_m"],
                  [(r.site_id, f"{r.lon:.6f}", f"{r.lat:.6f}", r.n_units, r.composition, r.diameter_m) for r in top.itertuples()]), "",
         f"Sites with diameter > {cfg['site_diameter_flag_m']} m: {len(big)}", ""]
    if len(big):
        L += [md_table(["site_id", "lon", "lat", "n_units", "composition", "diameter_m"],
                       [(r.site_id, f"{r.lon:.6f}", f"{r.lat:.6f}", r.n_units, r.composition, r.diameter_m) for r in big.itertuples()]), ""]
    L += [f"QGIS layers: `{P['sites_gpkg']}` (`sites`, `site_hulls`, EPSG:{crs}).", "",
          "## 2. Pilot sample", "", f"Seed {cfg['seed']}, spacing {cfg['min_spacing_m']} m. CSV sha256 `{sha}`.", ""]
    srows = [(s[0], s[1], s[2], s[3], "OK" if s[3] == s[1] else "SHORT", s[4]) for s in summary]
    L += [md_table(["stratum", "requested", "eligible", "drawn", "status", "redraws"], srows), "",
          f"Total drawn: {len(smp)} of {sum(s[1] for s in summary)} requested; redraws (rejected candidates: spacing or already used): "
          f"{sum(s[4] for s in summary)}.", ""]
    for s in summary:
        if len(s) > 6:
            L += [f"- {s[0]}: {s[6]}"]
    L += ["", f"Eligibility notes: edge strata A and B-core, B-service use kind `inside_through` only; C = `dead_end_spur` or tier C "
          "(not boundary_stub, not tram); boundary_stub is its own stratum. Candidate sets are not disjoint across sites vs edges "
          "(a unit appears once; spacing applies across all units).", "",
          f"Area cells ({cs} m grid): {ncell} covered by the sample; {total_cells} cells contain at least one RING 1 work unit.", "",
          "## Overlap set (all raters)", "",
          md_table(["pilot_id", "unit_type", "id", "stratum", "lon", "lat"],
                   [(r.pilot_id, r.unit_type, r.id, r.stratum, f"{r.lon:.6f}", f"{r.lat:.6f}") for r in smp[smp["overlap"]].itertuples()]), "",
          *(["Task 02b extended this sample (stratum `site: large`, warm-up set, rater assignments): see `reports/05_pilot_assignments.md`.", ""]
            if ext else []),
          "## Outputs", "", f"- `{P['sample_csv']}`", f"- `{P['sample_gpkg']}` (`pilot`, `pilot_edges`)", f"- `{P['record_sheet']}`",
          f"- `{P['sites_gpkg']}`", ""]
    pathlib.Path(P["report"]).write_text("\n".join(L))
    if ext:
        write_assignments(cfg, acfg, smp, summary, warm_summary, prev_sha, sha, checks)
    for a, b, c, d in checks:
        log.info("%s | expected %s | actual %s | %s", a, b, c, "PASS" if d else "FAIL")
    for s in summary:
        log.info("stratum %s requested %s eligible %s drawn %s redraws %s", *s[:5])
    log.info("sample sha256 %s", sha)
    if not all(c[3] for c in checks):
        log.error("CHECK FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
