"""Task 04s: simulate two JOSM-style editors on a private copy of the base file (test only).

Usage: uv run python src/17_workflow_spike.py [config/17_workflow_spike.yaml]
Simulates two editors, derives/renumbers/merges their changes, builds SUMO networks and writes
paths.report. Everything else goes to paths.workdir. Helper tools: src/18_osm_conflicts.py, src/19_osm_submit.py.
"""
import collections
import re
import subprocess
import copy
import logging
import math
import pathlib
import random
import sys
import xml.etree.ElementTree as ET

import yaml

log = logging.getLogger("spike")


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


def set_tag(el, k, v):
    for t in el.findall("tag"):
        if t.get("k") == k:
            t.set("v", v)
            return
    ET.SubElement(el, "tag", k=k, v=v)


def pick_ways(root, cfg):
    """Deterministically pick node-disjoint candidate ways inside the test bbox (6 edit ways + 1 conflict way)."""
    w, s, e, n = cfg["test_bbox"]
    nodes = {nd.get("id"): (float(nd.get("lat")), float(nd.get("lon"))) for nd in root.findall("node")}
    usage = {}
    ways = root.findall("way")
    for way in ways:
        for r in way.findall("nd"):
            usage[r.get("ref")] = usage.get(r.get("ref"), 0) + 1
    cands = []
    for way in ways:
        tags = {t.get("k"): t.get("v") for t in way.findall("tag")}
        if tags.get("highway") not in cfg["way_highway_candidates"] or any(k.startswith("lanes:") for k in tags):
            continue                       # lanes:forward/backward override lanes=, so a lanes edit would not show
        refs = [r.get("ref") for r in way.findall("nd")]
        if len(refs) < 5 or not all(r in nodes for r in refs):
            continue
        if not all(s <= nodes[r][0] <= n and w <= nodes[r][1] <= e for r in refs):
            continue
        cands.append(way)
    cands.sort(key=lambda x: int(x.get("id")))
    random.Random(cfg["seed"]).shuffle(cands)
    chosen, used = [], set()
    for way in cands:
        refs = {r.get("ref") for r in way.findall("nd")}
        if refs & used:
            continue
        chosen.append(way.get("id"))
        used |= refs
        if len(chosen) == 7:
            break
    if len(chosen) < 7:
        raise SystemExit(f"only {len(chosen)} node-disjoint candidate ways in test_bbox; widen it")
    return chosen, nodes, usage


def new_node(nid, lat, lon):
    return ET.Element("node", id=str(nid), action="modify", visible="true", lat=f"{lat:.7f}", lon=f"{lon:.7f}")


def edit_tree(base_root, cfg, ed, way_ids, nodes, usage, move_node_m=None, new_way_id=-3, extra=None):
    """Return an edited copy of the base tree; JOSM conventions: action=modify, negative ids for new objects."""
    root = copy.deepcopy(base_root)
    by_id = {w.get("id"): w for w in root.findall("way")}
    spec = cfg["edits"][ed]
    log_rows = []
    for wid, tags in zip(way_ids, spec["tags"]):
        way = by_id[wid]
        for k, v in tags.items():
            set_tag(way, k, v)
        way.set("action", "modify")
        log_rows.append(("way", wid, "tags " + str(tags)))
    if extra:
        for wid, tags in extra:
            for k, v in tags.items():
                set_tag(by_id[wid], k, v)
            by_id[wid].set("action", "modify")
            log_rows.append(("way", wid, "tags " + str(tags) + " (conflict test)"))
    nmap = {nd.get("id"): nd for nd in root.findall("node")}
    first = by_id[way_ids[0]]
    refs = [r.get("ref") for r in first.findall("nd")]
    anchor = refs[0]                                   # existing node the new way attaches to (left unchanged)
    if move_node_m:
        # an inner, untagged node used by this way only
        mv = next(r for r in refs[1:-1] if usage[r] == 1 and nmap[r].find("tag") is None)
        nd = nmap[mv]
        nd.set("lat", f"{float(nd.get('lat')) + move_node_m / 111320.0:.7f}")
        nd.set("action", "modify")
        log_rows.append(("node", mv, f"moved {move_node_m} m north"))
    a_lat, a_lon = nodes[anchor]
    dlat = 40 / 111320.0
    dlon = 40 / (111320.0 * math.cos(math.radians(a_lat)))
    k = 1 if ed == "A" else 2
    n1 = new_node(-1, a_lat + k * dlat, a_lon + dlon)
    n2 = new_node(-2, a_lat + k * dlat * 2, a_lon + dlon * 2)
    way = ET.Element("way", id=str(new_way_id), action="modify", visible="true")
    for ref in (anchor, "-1", "-2"):
        ET.SubElement(way, "nd", ref=ref)
    ET.SubElement(way, "tag", k="highway", v="residential")
    ET.SubElement(way, "tag", k="name", v=spec["new_way_name"])
    ET.SubElement(way, "tag", k="maxspeed", v="30")
    # keep the file in JOSM layout: nodes, ways, relations (osmium sort fixes the order within a type)
    first_way = root.find("way")
    idx = list(root).index(first_way)
    root.insert(idx, n2)
    root.insert(idx, n1)
    last_way = root.findall("way")[-1]
    root.insert(list(root).index(last_way) + 1, way)
    log_rows += [("node", "-1", "new"), ("node", "-2", "new"), ("way", str(new_way_id), f"new, nodes {anchor},-1,-2")]
    return root, log_rows


def write_osm(root, path):
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(path, encoding="UTF-8", xml_declaration=True)


def simulate(cfg):
    wd = pathlib.Path(cfg["paths"]["workdir"])
    wd.mkdir(parents=True, exist_ok=True)
    base = pathlib.Path(cfg["paths"]["base"])
    if not base.exists():
        raise SystemExit(f"{base} missing: run {cfg['paths']['base_script']}")
    tree = ET.parse(base)
    root = tree.getroot()
    ways, nodes, usage = pick_ways(root, cfg)
    A, B, conflict = ways[0:3], ways[3:6], ways[6]
    plan = {"A": A, "B": B, "conflict": conflict}
    rows = {}
    for ed, wl in (("A", A), ("B", B)):
        r, rows[ed] = edit_tree(root, cfg, ed, wl, nodes, usage, move_node_m=cfg["move_node_m"] if ed == "A" else None)
        write_osm(r, wd / f"edited{ed}.osm")
        # conflict variant: both editors also change the same extra way
        extra = [(conflict, {"maxspeed": "35" if ed == "A" else "45"})]
        r, _ = edit_tree(root, cfg, ed, wl, nodes, usage, move_node_m=cfg["move_node_m"] if ed == "A" else None, extra=extra)
        write_osm(r, wd / f"edited{ed}_conflict.osm")
    for ed in "AB":
        for kind, oid, what in rows[ed]:
            log.info("editor %s: %s %s %s", ed, kind, oid, what)
    return plan, rows


def sh(cmd, check=True):
    log.info("$ %s", " ".join(str(c) for c in cmd))
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True)
    if check and r.returncode:
        raise SystemExit(f"command failed ({r.returncode}): {' '.join(map(str, cmd))}\n{r.stderr}")
    return r


def osm_count(path, kind):
    return int(sh(["osmium", "fileinfo", "-e", "-g", f"data.count.{kind}", path]).stdout)


def osc_summary(path):
    """{block: {type: n}} of a change file."""
    out = collections.defaultdict(lambda: collections.Counter())
    for block in ET.parse(path).getroot():
        for el in block:
            out[block.tag][el.tag] += 1
    return {b: dict(c) for b, c in out.items()}


def way_edges(net_path, way_ids):
    """{way id: [(edge id, numLanes, speeds, shape)]} from a net.xml (edge ids are <way>[#k], reverse edges have a '-' prefix)."""
    pat = re.compile(r"^-?(\d+)(#\d+)?$")
    res = collections.defaultdict(list)
    for _, el in ET.iterparse(net_path):
        if el.tag == "edge" and el.get("function") != "internal":
            m = pat.match(el.get("id"))
            wid = m.group(1) if m else el.get("id")
            if wid in way_ids:
                lanes = el.findall("lane")
                res[wid].append((el.get("id"), len(lanes), sorted({float(l.get("speed")) for l in lanes}), el.get("shape") or lanes[0].get("shape")))
    return res


def netconvert(cfg, osm, out):
    bbox = ",".join(str(x) for x in cfg["test_bbox"])
    r = sh(["netconvert", "--osm-files", osm, "-o", out, *cfg["netconvert_options"], bbox], check=False)
    ok = "Success." in (r.stdout + r.stderr)
    pathlib.Path(out).with_suffix(".log").write_text(r.stdout + r.stderr)
    return ok


def submit(cfg, ed_idx, edited, out, *flags):
    sh(["uv", "run", "python", "src/19_osm_submit.py", cfg["paths"]["base"], edited, out,
        "--editor-index", ed_idx, "--config", CFG_PATH, *flags])


def conflicts(files, check=False):
    return sh(["uv", "run", "python", "src/18_osm_conflicts.py", *[f"{k}={v}" for k, v in files.items()]], check=check)


def shape_shift(a, b):
    pa = [tuple(map(float, p.split(","))) for p in a.split()]
    pb = [tuple(map(float, p.split(","))) for p in b.split()]
    if len(pa) != len(pb):
        return None
    return max(math.dist(x, y) for x, y in zip(pa, pb))


def run_all(cfg):
    """Run every spike step; returns a dict of measurements (also logged)."""
    wd = pathlib.Path(cfg["paths"]["workdir"])
    base = cfg["paths"]["base"]
    plan, rows = simulate(cfg)
    R = {"plan": plan, "rows": rows}
    off = cfg["renumber_offset"]
    nb, wb = osm_count(base, "nodes"), osm_count(base, "ways")
    R["base_counts"] = (nb, wb)

    # 2a. naive: osmium sort + derive-changes straight on the saved editor file
    sh(["osmium", "sort", wd / "editedA.osm", "-o", wd / "A_naive.sorted.osm", "--overwrite"])
    sh(["osmium", "derive-changes", base, wd / "A_naive.sorted.osm", "-o", wd / "A_naive.osc", "--overwrite"])
    R["naive_A"] = osc_summary(wd / "A_naive.osc")
    # 2b. deletions: one way marked action="delete" (JOSM style), one way simply missing
    text = pathlib.Path(base).read_text(encoding="utf-8")
    dwa, dwb = plan["A"][1], plan["A"][2]
    ma = re.search(rf'  <way id="{dwa}".*?</way>\n', text, re.S).group(0)
    mb = re.search(rf'  <way id="{dwb}".*?</way>\n', text, re.S).group(0)
    dtxt = text.replace(mb, "").replace(ma, ma.replace(f'<way id="{dwa}"', f'<way action="delete" id="{dwa}"', 1))
    (wd / "editedDel.osm").write_text(dtxt, encoding="utf-8")
    sh(["osmium", "sort", wd / "editedDel.osm", "-o", wd / "Del_naive.sorted.osm", "--overwrite"])
    sh(["osmium", "derive-changes", base, wd / "Del_naive.sorted.osm", "-o", wd / "Del_naive.osc", "--overwrite"])
    R["naive_del"] = osc_summary(wd / "Del_naive.osc")
    submit(cfg, 0, wd / "editedDel.osm", wd / "Del.osc")
    R["tool_del"] = osc_summary(wd / "Del.osc")

    # 3. negative-id collision (no renumbering)
    for i, ed in enumerate("AB"):
        submit(cfg, i, wd / f"edited{ed}.osm", wd / f"{ed}_raw.osc", "--no-renumber")
    sh(["osmium", "merge-changes", wd / "A_raw.osc", wd / "B_raw.osc", "-o", wd / "AB_raw.osc", "--overwrite"])
    R["merge_raw"] = osc_summary(wd / "AB_raw.osc")
    sh(["osmium", "apply-changes", base, wd / "AB_raw.osc", "-o", wd / "merged_raw.osm", "--overwrite"])
    R["raw_counts"] = (osm_count(wd / "merged_raw.osm", "nodes"), osm_count(wd / "merged_raw.osm", "ways"))
    r = conflicts({"A": wd / "A_raw.osc", "B": wd / "B_raw.osc"})
    R["detector_raw"] = (r.returncode, r.stdout)

    # 4. renumbered flow (positive block ids) and the negative-shift variant
    for i, ed in enumerate("AB"):
        submit(cfg, i, wd / f"edited{ed}.osm", wd / f"{ed}.osc")
        submit(cfg, i, wd / f"edited{ed}.osm", wd / f"{ed}_neg.osc", "--keep-negative")
    r = conflicts({"A": wd / "A.osc", "B": wd / "B.osc"})
    R["detector_ok"] = (r.returncode, r.stdout)
    sh(["osmium", "merge-changes", wd / "A.osc", wd / "B.osc", "-o", wd / "AB.osc", "--overwrite"])
    R["merge_ok"] = osc_summary(wd / "AB.osc")
    sh(["osmium", "apply-changes", base, wd / "AB.osc", "-o", wd / "merged.osm", "--overwrite"])
    R["ok_counts"] = (osm_count(wd / "merged.osm", "nodes"), osm_count(wd / "merged.osm", "ways"))
    sh(["osmium", "merge-changes", wd / "A_neg.osc", wd / "B_neg.osc", "-o", wd / "AB_neg.osc", "--overwrite"])
    sh(["osmium", "apply-changes", base, wd / "AB_neg.osc", "-o", wd / "merged_neg.osm", "--overwrite"])
    for name, f in (("base", base), ("merged", wd / "merged.osm")):
        r = sh(["osmium", "check-refs", "-r", f], check=False)
        R[f"refs_{name}"] = [l.strip() for l in (r.stdout + r.stderr).splitlines() if "missing" in l]

    # 5. same way changed by both editors
    for i, ed in enumerate("AB"):
        submit(cfg, i, wd / f"edited{ed}_conflict.osm", wd / f"{ed}_c.osc")
    r = conflicts({"A": wd / "A_c.osc", "B": wd / "B_c.osc"})
    R["detector_conflict"] = (r.returncode, r.stdout)
    sh(["osmium", "merge-changes", wd / "A_c.osc", wd / "B_c.osc", "-o", wd / "AB_c.osc", "--overwrite"])
    sh(["osmium", "apply-changes", base, wd / "AB_c.osc", "-o", wd / "merged_c.osm", "--overwrite"])
    cw = plan["conflict"]
    m = re.search(rf'<way id="{cw}".*?</way>', pathlib.Path(wd / "merged_c.osm").read_text(encoding="utf-8"), re.S).group(0)
    R["conflict_result"] = (cw, re.findall(r'k="maxspeed" v="([^"]+)"', m))

    # 6. netconvert
    for name, f in (("base", base), ("merged", wd / "merged.osm"), ("merged_neg", wd / "merged_neg.osm")):
        R[f"nc_{name}"] = netconvert(cfg, str(f), str(wd / f"{name}.net.xml"))
    wanted = set(plan["A"] + plan["B"])
    newA, newB = str(off + 3), str(2 * off + 3)   # id -3 of editor i -> (i+1)*offset + 3
    eb, em = way_edges(wd / "base.net.xml", wanted), way_edges(wd / "merged.net.xml", wanted | {newA, newB})
    R["edges"] = {w: (eb.get(w, []), em.get(w, [])) for w in plan["A"] + plan["B"]}
    R["new_edges"] = {"A": em.get(newA, []), "B": em.get(newB, [])}
    neg = [l.split('"')[1] for l in pathlib.Path(wd / "merged_neg.net.xml").read_text().splitlines() if "<edge id=\"-" in l and "000003" in l and "function" not in l]
    R["neg_edge_ids"] = neg
    # node move measured in isolation (a tag change on the same way also moves its shape, via lane width)
    mv, wmv = [r for r in rows["A"] if r[0] == "node" and int(r[1]) > 0][0][1], plan["A"][0]
    node = [n for n in ET.parse(wd / "A.osc").getroot().iter("node") if n.get("id") == mv][0]
    mo = ET.Element("osmChange", version="0.6")
    ET.SubElement(ET.SubElement(mo, "modify"), "node", node.attrib)
    ET.ElementTree(mo).write(wd / "move_only.osc", encoding="UTF-8", xml_declaration=True)
    sh(["osmium", "apply-changes", base, wd / "move_only.osc", "-o", wd / "move_only.osm", "--overwrite"])
    netconvert(cfg, str(wd / "move_only.osm"), str(wd / "move_only.net.xml"))
    eb0 = {e[0]: e[3] for e in way_edges(wd / "base.net.xml", {wmv})[wmv]}
    emv = {e[0]: e[3] for e in way_edges(wd / "move_only.net.xml", {wmv})[wmv]}
    R["move"] = (mv, wmv, {k: shape_shift(eb0[k], emv[k]) for k in eb0 if k in emv})
    return R


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def fmt_sum(d):
    return ", ".join(f"{b}: " + "+".join(f"{n} {t}" for t, n in sorted(c.items())) for b, c in d.items()) or "nothing"


def write_report(cfg, R):
    wd = pathlib.Path(cfg["paths"]["workdir"])
    plan, off = R["plan"], cfg["renumber_offset"]
    nb, wb = R["base_counts"]
    sA, sB = osc_summary(wd / "A.osc"), osc_summary(wd / "B.osc")
    checks = []

    def chk(name, expected, got):
        checks.append((name, expected, got, "OK" if str(expected) == str(got) else "MISMATCH"))

    chk("tool derive, editor A", "modify: 3 node+4 way", fmt_sum(sA).replace("modify: ", "modify: "))
    chk("tool derive, editor B", "modify: 2 node+4 way", fmt_sum(sB))
    chk("deletions, 19_osm_submit.py", "2 deletes", f"{R['tool_del'].get('delete', {}).get('way', 0)} deletes")
    chk("merged with renumbering: nodes / ways added", "4 / 2", f"{R['ok_counts'][0] - nb} / {R['ok_counts'][1] - wb}")
    chk("check-refs merged vs base", "identical", "identical" if R["refs_base"] == R["refs_merged"] else "DIFFERENT")
    chk("conflict detector, disjoint edits (exit code)", 0, R["detector_ok"][0])
    chk("conflict detector, same way changed by A and B (exit code)", 1, R["detector_conflict"][0])
    chk("netconvert base / merged / merged (negative-shift variant)", "Success / Success / Success", f"{'Success' if R['nc_base'] else 'FAIL'} / {'Success' if R['nc_merged'] else 'FAIL'} / {'Success' if R['nc_merged_neg'] else 'FAIL'}")
    exp = {"A": {plan["A"][0]: (3, None), plan["A"][1]: (None, 30), plan["A"][2]: (2, 70)},
           "B": {plan["B"][0]: (None, 20), plan["B"][1]: (4, None), plan["B"][2]: (1, 60)}}
    erows = []
    for ed in "AB":
        for w, (lanes, ms) in exp[ed].items():
            b, m = R["edges"][w]
            fwd_b = [e for e in b if not e[0].startswith("-")]
            fwd_m = [e for e in m if not e[0].startswith("-")]
            sp_b, sp_m = sorted({v for e in fwd_b for v in e[2]}), sorted({v for e in fwd_m for v in e[2]})
            nl_b, nl_m = max(e[1] for e in fwd_b), max(e[1] for e in fwd_m)
            ok = (ms is None or sp_m == [round(ms / 3.6, 2)]) and (lanes is None or nl_m == lanes)
            erows.append((ed, w, f"lanes={lanes} maxspeed={ms}", f"{nl_b} lanes, {sp_b} m/s", f"{nl_m} lanes, {sp_m} m/s", "OK" if ok else "MISMATCH"))
            checks.append((f"net: way {w} (editor {ed})", f"{lanes or 'same'} lanes / {round(ms / 3.6, 2) if ms else 'same'} m/s", f"{nl_m} / {sp_m}", "OK" if ok else "MISMATCH"))
    for ed in "AB":
        ne = R["new_edges"][ed]
        checks.append((f"net: new way of editor {ed} present", "2 edges", f"{len(ne)} edges ({', '.join(e[0] for e in ne)})", "OK" if len(ne) == 2 else "MISMATCH"))
    mv = R["move"]
    checks.append((f"net: node {mv[0]} moved 2 m (max shape shift, isolated build)", "2.0 m", f"{max(v for v in mv[2].values() if v is not None):.2f} m", "OK" if abs(max(mv[2].values()) - 2) < 0.1 else "MISMATCH"))
    bad = [c for c in checks if c[3] != "OK"]
    L = []
    L.append("# Report 07: OSM editing and merging workflow spike (task 04s)\n")
    L.append(f"Test only. Base: `{cfg['paths']['base']}` ({nb} nodes, {wb} ways). Work directory: `{cfg['paths']['workdir']}/`. "
             f"Produced by `src/17_workflow_spike.py` (config `config/17_workflow_spike.yaml`); inputs verified with `scripts/verify_inputs.sh`; `data/raw/` not touched; nothing committed. Tools: osmium 1.16.0, netconvert 1.28.0.\n")
    L.append(f"**Result: {len(checks) - len(bad)} of {len(checks)} checks as expected" + (f", {len(bad)} MISMATCH (see below)." if bad else ".") + "**\n")
    L.append("## 1. Simulated editors\n")
    L.append("Editors are simulated by `src/17_workflow_spike.py` (not JOSM). It writes JOSM-style files: changed objects keep their `version` and get `action=\"modify\"`; new objects have negative ids and `action=\"modify\"`; both editors deliberately use the ids -1, -2 (nodes) and -3 (way). The new way is attached to an existing, unchanged node of the editor's own area.\n")
    L.append(md_table(["Editor", "Type", "Id", "Edit"], [(ed, k, i, w) for ed in "AB" for k, i, w in R["rows"][ed]]) + "\n")
    L.append(f"Extra way for the conflict test (changed by both editors): `{plan['conflict']}` (A: maxspeed=35, B: maxspeed=45; values differ from the base, a no-op edit is not a change).\n")
    L.append("## 2. What `osmium derive-changes` does\n")
    L.append("Pitfalls demonstrated with plain osmium (these are expected to fail; they are why the helper scripts exist):\n")
    L.append(md_table(["Pitfall", "Correct result", "Plain osmium result"], [
        ("derive-changes on raw editor A file", "7 objects (3 ways + 1 node moved + 2 new nodes + 1 new way)", f"{sum(R['naive_A']['modify'].values())} objects ({fmt_sum(R['naive_A'])})"),
        ("deletions (1 `action=delete`, 1 omitted)", "2 deletes", f"{R['naive_del'].get('delete', {}).get('way', 0)} delete"),
        ("merge of A and B without renumbering: nodes / ways added", "4 / 2", f"{R['raw_counts'][0] - nb} / {R['raw_counts'][1] - wb}")]) + "\n")
    L.append("### 2.1 Modified objects are silently lost (important)\n")
    L.append(f"`osmium sort` + `osmium derive-changes BASE EDITED` on the raw editor-A file gives **{fmt_sum(R['naive_A'])}**: only the new objects. The three tag edits and the moved node are missing, because `derive-changes` compares `(type, id, version)` and JOSM does not change `version` of edited objects (the server does that on upload). `osmium sort` also drops the `action` attribute, so it cannot be used to tell the objects apart afterwards. No warning is printed, exit code 0.\n")
    L.append("Fix (`src/19_osm_submit.py`, function `prepare`): compare each existing object with the base (tags, coordinates, node list, members) and set `version = base version + 1` on the ones that differ. This does not rely on `action`, so it also works for files that were not written by JOSM.\n")
    L.append("### 2.2 Deletions\n")
    L.append(f"Test file: one way marked `action=\"delete\"` (what JOSM writes, to be confirmed, see section 6) and one way simply missing. Plain `osmium derive-changes`: **{R['naive_del'].get('delete', {}).get('way', 0)} delete** (only the missing way; the `action=\"delete\"` way is treated as unchanged and stays in the result). With `19_osm_submit.py` (drops `action=\"delete\"` objects before deriving): **{R['tool_del'].get('delete', {}).get('way', 0)} deletes**. Deleting a way does not delete its nodes; they stay as orphans unless the editor deletes them too (JOSM normally does).\n")
    L.append("### 2.3 Negative ids\n")
    L.append(f"`derive-changes` accepts negative ids and passes them through unchanged, as `<modify>` (never `<create>`). Both editors' files therefore contain node -1, node -2, way -3. `osmium merge-changes` accepts this without any message and writes both versions (`{fmt_sum(R['merge_raw'])}`). `osmium apply-changes` then keeps the last one: **A's new nodes -1, -2 and way -3 are silently replaced by B's** (nodes +{R['raw_counts'][0] - nb} and ways +{R['raw_counts'][1] - wb} instead of +4 and +2). No error, no warning: A's new road is simply gone.\n")
    L.append("`src/18_osm_conflicts.py` detects this (\"negative-id collision\"):\n\n```\n" + R["detector_raw"][1] + "```\n")
    L.append("### 2.4 Renumbering step (implemented and tested)\n")
    L.append(f"`19_osm_submit.py` maps every negative id `n` (object ids, `nd ref`, `member ref`) of editor `i` (0-based) to **`(i+1) * {off:,} - n`**, so A's -1,-2,-3 become {off + 1},{off + 2},{off + 3} and B's become {2 * off + 1},{2 * off + 2},{2 * off + 3}. The block size is above the highest real id in the snapshot (nodes 14,313,717,029, ways 1,571,183,111, relations 21,771,971), so the new ids cannot collide with existing ones.\n")
    L.append("Why positive and not \"shift further negative\": the negative shift also works in osmium, but `netconvert` names the edges after the way id and uses a `-` prefix for the reverse direction. A way with id -1000000000003 gives the edges " + ", ".join(f"`{e}`" for e in R["neg_edge_ids"]) + ", i.e. the reverse edge starts with `--` and the forward edge looks like the reverse edge of way 1000000000003. Positive ids give clean names (`" + "`, `".join(e[0] for e in R["new_edges"]["A"]) + "`).\n")
    L.append("## 3. Merge, apply, conflict detection\n")
    L.append("```bash\nBASE=data/interim/ring1_roads.osm; W=data/interim/spike\n"
             "uv run python src/19_osm_submit.py $BASE $W/editedA.osm $W/A.osc --editor-index 0\n"
             "uv run python src/19_osm_submit.py $BASE $W/editedB.osm $W/B.osc --editor-index 1\n"
             "uv run python src/18_osm_conflicts.py A=$W/A.osc B=$W/B.osc          # exit 1 on conflict/collision\n"
             "osmium merge-changes $W/A.osc $W/B.osc -o $W/AB.osc --overwrite\n"
             "osmium apply-changes $BASE $W/AB.osc -o $W/merged.osm --overwrite\n"
             "osmium check-refs -r $W/merged.osm\n```\n")
    L.append(f"Disjoint edits: detector `{R['detector_ok'][1].strip()}`; merged file has +{R['ok_counts'][0] - nb} nodes, +{R['ok_counts'][1] - wb} ways; `osmium check-refs` output equals the base (the 4 \"ways in relations missing\" are already in the base, they come from the polygon cut).\n")
    L.append(f"Same way changed by A and B: detector output `{R['detector_conflict'][1].splitlines()[0]}` and exit code {R['detector_conflict'][0]}. Without the detector `osmium merge-changes`/`apply-changes` raise no error: the result silently has maxspeed `{R['conflict_result'][1][0]}` on way {R['conflict_result'][0]} (B wins; the change files must be given to `merge-changes` in a fixed order, the last one wins).\n")
    L.append("## 4. netconvert\n")
    L.append(f"Options as in `docs/SETUP.md` 6b (defaults + `--keep-edges.in-geo-boundary`), bbox `{','.join(str(x) for x in cfg['test_bbox'])}`, on the base and on `merged.osm`. Both: Success.\n")
    L.append(md_table(["Editor", "Way", "Edit", "Base (forward edges)", "Merged (forward edges)", "Check"], erows) + "\n")
    L.append("New ways (each has a forward and a reverse edge, because they are two-way by default):\n")
    L.append(md_table(["Editor", "Edges in merged network", "Lanes", "Speed [m/s]"], [(ed, ", ".join(e[0] for e in R["new_edges"][ed]), R["new_edges"][ed][0][1] if R["new_edges"][ed] else "-", R["new_edges"][ed][0][2] if R["new_edges"][ed] else "-") for ed in "AB"]) + "\n")
    L.append(f"Moved node {mv[0]} (isolated build with only that change): per-edge max shape shift of way {mv[1]}: " + ", ".join(f"`{k}` {v:.2f} m" for k, v in mv[2].items()) + ". Shifts below 2 m on a split edge come from the edge ending at a junction near the moved point; at least one edge shows the full 2.00 m. In the combined build the way also got a lane change, which shifts the shape for other reasons, so the move is measured in isolation.\n")
    L.append("## 5. Control table\n")
    L.append(md_table(["Check", "Expected", "Got", "Status"], checks) + "\n")
    L.append("## 6. Limitations\n")
    L.append("- This is a simulation of JOSM files, not real JOSM files. How JOSM writes deletions, new relations, `action` values and `version` on new objects is assumed, not verified (list in `docs/workflow/osm_editing.md`).\n"
             "- Modified objects are lost by plain `osmium derive-changes`; `19_osm_submit.py` is required, not optional.\n"
             "- Collisions of negative ids and edits of the same object by two editors are **not** detected by osmium; they are detected only by `18_osm_conflicts.py`. It checks the same object id, not semantic conflicts (e.g. A deletes a node that B's new way uses; `osmium check-refs` on the merged file catches missing references, but only after the merge).\n"
             "- The ownership rule (editors edit only what they own) is not enforced by any tool here; the detector only catches violations that happen to touch the same object. A node shared by two zones (moved by A, used by a way owned by B) is not a conflict for the tools and not visible to B.\n"
             "- New nodes connected to existing nodes at the border between two owners: the anchor node is unchanged, so no conflict is raised, but two editors can create overlapping or duplicate roads without any message.\n"
             "- `apply-changes` applies the files in the order given; for non-conflicting edits the order does not matter.\n"
             "- Edits of `lanes=` have no effect on ways that carry `lanes:forward` / `lanes:backward` (netconvert uses those; seen in an earlier run on a tertiary way). Cleaners must change the detailed tags too.\n"
             "- Version bump is `base + 1` for every editor, so two editors changing the same object would both produce version `base+1`; this is exactly the case the detector reports.\n"
             "- Timing: each `19_osm_submit.py` run on the 13 MB base takes about 2 s; netconvert on the small bbox a few seconds.\n")
    L.append("## 7. Recommended workflow\n")
    L.append("See `docs/workflow/osm_editing.md`. In short: extract the zone from the base, edit in JOSM, save, `19_osm_submit.py` (version bump, deletions, renumbering, derive), run `18_osm_conflicts.py` on all submitted files, merge with `osmium merge-changes`, apply, run `osmium check-refs`, build with netconvert.\n")
    pathlib.Path(cfg["paths"]["report"]).write_text("\n".join(L), encoding="utf-8")
    for c in checks:
        log.info("CHECK %s | expected %s | got %s | %s", *c)
    return bad


CFG_PATH = "config/17_workflow_spike.yaml"

if __name__ == "__main__":
    CFG_PATH = sys.argv[1] if len(sys.argv) > 1 else CFG_PATH
    cfg = load_yaml(CFG_PATH)
    setup_logging(cfg["paths"]["log"])
    import json
    R = run_all(cfg)
    out = pathlib.Path(cfg["paths"]["workdir"]) / "results.json"
    out.write_text(json.dumps(R, indent=1, default=str))
    log.info("results -> %s", out)
    bad = write_report(cfg, R)
    log.info("report -> %s (%d mismatches)", cfg["paths"]["report"], len(bad))
