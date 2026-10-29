"""Task 04r: run the editing workflow on the real JOSM files and write reports/09_real_josm_files.md.

Usage: uv run python src/24_real_workflow.py [config/24_real_josm.yaml]
Items: 1 file facts (src/20_josm_file_facts.py), 2 full workflow on A and B, 3 planted cases, 4 contaminated file,
5 safeguard exit codes, 6 synthetic cases. Everything generated goes to paths.workdir (wiped at the start); the report is
deterministic (no timestamps), so two runs give identical output hashes (paths.rerun_hashes).
"""
import collections
import hashlib
import importlib.util
import json
import logging
import math
import pathlib
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import pyproj
import yaml
from shapely.geometry import shape

SRC = pathlib.Path(__file__).parent
sys.path.insert(0, str(SRC))
import osm_io  # noqa: E402

log = logging.getLogger("real_workflow")
PY = sys.executable


def load_script(name):
    spec = importlib.util.spec_from_file_location(name.replace(".py", "").replace("-", "_").lstrip("0123456789_") or "m", SRC / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def sh(cmd, **kw):
    log.info("$ %s", " ".join(str(c) for c in cmd))
    r = subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)
    return r


def md_table(header, rows):
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c).replace("|", "\\|") for c in r) + " |" for r in rows]
    return "\n".join(out)


def ids_short(ids, n=12):
    ids = list(ids)
    return ", ".join(str(i) for i in ids[:n]) + (f", ... (+{len(ids) - n})" if len(ids) > n else "")


# ---------------------------------------------------------------- item 1
def section_facts(F):
    A, B, U = F["A"], F["B"], F["B_update"]
    L = ["## 1. Facts about the JOSM file format (full files)\n",
         "Parsed with `xml.etree`; the quote-style row is a plain substring count on the raw text. Package = the v1 package the editor opened (BASE). "
         "Columns A, B are the clean files; `B_update` is the contaminated one (shown only where it differs).\n"]
    rows = []

    def row(fact, a, b, u, holds):
        rows.append((fact, a, b, u, "**holds**" if holds else "**does not hold**"))

    q = lambda r: f"{r['quotes']['file_single']} single / {r['quotes']['file_double']} double"  # noqa: E731
    row("attributes single-quoted (package: double-quoted)", q(A), q(B), q(U),
        all(F[k]["quotes"]["file_double"] == 0 for k in ("A", "B", "B_update")))
    nw = lambda r: (f"{r['new_objects']['n']} new, ids {r['new_objects']['ids']}, action=modify {r['new_objects']['action_modify']}, "  # noqa: E731
                    f"with version {r['new_objects']['with_version']}")
    row("new objects: negative id, action='modify', no version", nw(A), nw(B), nw(U),
        all(F[k]["new_objects"]["n"] == F[k]["new_objects"]["action_modify"] and F[k]["new_objects"]["with_version"] == 0 for k in ("A", "B", "B_update")))
    ex = lambda r: f"{r['existing']['version_equal']}/{r['existing']['in_package']} version, {r['existing']['timestamp_equal']}/{r['existing']['in_package']} timestamp equal"  # noqa: E731
    row("existing objects keep version and timestamp", ex(A), ex(B), ex(U),
        all(F[k]["existing"]["version_equal"] == F[k]["existing"]["in_package"] == F[k]["existing"]["timestamp_equal"] for k in ("A", "B")))
    mv = lambda r: f"{r['moved_nodes']['n']} moved nodes with {r['moved_nodes']['users_ways_relations']} ways/relations using them; {r['moved_nodes']['users_marked_with_action']} of those marked"  # noqa: E731
    row("a moved node marks only that node", mv(A), mv(B), mv(U), all(F[k]["moved_nodes"]["users_marked_with_action"] == 0 for k in ("A", "B", "B_update")))
    dw = lambda r: f"{r['deleted']['ways']['n']} deleted ways: tags kept {r['deleted']['ways']['tags_kept']}, without nd {r['deleted']['ways']['no_nd']}"  # noqa: E731
    row("a deleted way keeps its tags and has no `<nd>`", dw(A), dw(B), dw(U) + " (the 6 server-deleted objects have no tags)",
        all(F[k]["deleted"]["ways"]["tags_kept"] == F[k]["deleted"]["ways"]["n"] == F[k]["deleted"]["ways"]["no_nd"] for k in ("A", "B")))
    dn = lambda r: f"{r['deleted']['nodes']['n']} deleted nodes: coordinates kept {r['deleted']['nodes']['coords_kept']}, version kept {r['deleted']['nodes']['version_kept']}"  # noqa: E731
    row("a deleted node keeps its coordinates", dn(A), dn(B), dn(U), all(F[k]["deleted"]["nodes"]["coords_kept"] == F[k]["deleted"]["nodes"]["n"] for k in ("A", "B")))
    ct = lambda r: "file nodes/ways/relations " + "/".join(str(r["counts"]["file"][t]) for t in osm_io.TYPES) + " = package " + "/".join(str(r["counts"]["package"][t]) for t in osm_io.TYPES) + " + new " + "/".join(str(r["counts"]["new"][t]) for t in osm_io.TYPES)  # noqa: E731
    row("deleted objects stay in the file (file = package + new)", ct(A), ct(B), ct(U) + f" ({U['existing']['n'] - U['existing']['in_package']} extra existing nodes)",
        A["counts_ok"] and B["counts_ok"])
    nid = F["negative_ids"]
    row("negative ids are not dense", str(nid["A"]), str(nid["B"]), str(nid["B_update"]), True)
    row("negative ids differ between sessions", "A vs B overlap " + str(F["negative_ids_overlap"]["A&B"]), "B vs B_update overlap " + str(F["negative_ids_overlap"]["B&B_update"]),
        "A vs B_update overlap " + str(F["negative_ids_overlap"]["A&B_update"]), not any(F["negative_ids_overlap"].values()))
    row("editedA_resaved.osm identical to editedA.osm", f"sha256 equal: {F['resaved_identical']['sha256_equal']}, bytes equal: {F['resaved_identical']['bytes_equal']}", "", "",
        F["resaved_identical"]["bytes_equal"])
    L.append(md_table(["Fact", "A (zone 3)", "B (zone 4)", "B_update", "Verdict"], rows))
    L.append("")
    un = lambda r: f"{r['untouched']['canonical_differs']} of {r['untouched']['n']}"  # noqa: E731
    L.append("Canonical comparison with the package (tags as dict, nd / member order significant, coordinates rounded to 7 decimals):\n")
    L.append(md_table(["Measure", "A", "B", "B_update"], [
        ("untouched objects whose canonical content differs from the package (expected 0)", un(A), un(B), un(U) + " (server drift, see item 4)"),
        ("objects whose serialisation differs only in tag order", A["untouched"]["tag_order_only"], B["untouched"]["tag_order_only"], U["untouched"]["tag_order_only"]),
        ("untouched objects with tags in alphabetical order in the file", f"{A['untouched']['tag_order_alphabetical_in_file']}/{A['untouched']['n']}",
         f"{B['untouched']['tag_order_alphabetical_in_file']}/{B['untouched']['n']}", f"{U['untouched']['tag_order_alphabetical_in_file']}/{U['untouched']['n']}"),
        ("objects whose serialisation differs only in quotes", "all (" + str(A["quotes"]["file_single"]) + " single-quoted attributes vs " + str(A["quotes"]["package_double"]) + " double in the package)", "all", "all"),
        ("untouched node coordinates with 6 / 7 decimals", str(A["untouched"]["node_decimals"]), str(B["untouched"]["node_decimals"]), str(U["untouched"]["node_decimals"])),
        ("moved node coordinates: decimals", str(sorted(set(A["moved_nodes"]["decimals"].values()))), str(sorted(set(B["moved_nodes"]["decimals"].values()))), "-"),
        ("modified existing objects with unchanged version", f"{A['modified_existing']['version_kept']}/{A['modified_existing']['n']}", f"{B['modified_existing']['version_kept']}/{B['modified_existing']['n']}", f"{U['modified_existing']['version_kept']}/{U['modified_existing']['n']}"),
    ]))
    L.append("")
    L.append("Attributes JOSM adds or drops compared with the osmium-written package:\n")
    add = []
    for t in ("node", "way", "relation"):
        fa, pa = A["attrs_file"].get(t, {}), A["attrs_package"].get(t, {})
        add.append((t, ", ".join(sorted(set(fa) - set(pa))) or "-", ", ".join(sorted(set(pa) - set(fa))) or "-"))
    L.append(md_table(["Element", "added by JOSM (clean file A)", "dropped"], add))
    L.append(f"\n- `generator`: package `{A['root_attrs_package']['generator']}`, JOSM file `{A['root_attrs_file']['generator']}`; `version='0.6'` both. No `<bounds>` element (children of `<osm>` other than objects: file {A['non_object_children_file']}, package {A['non_object_children_package']}). No `upload` attribute ({A['extra_attrs']['upload']} in A, {B['extra_attrs']['upload']} in B). "
             f"`visible='true'` on every object (A: {A['extra_attrs']['visible_true']} of {A['existing']['n'] + A['new_objects']['n']}). Clean files: uid/user/changeset = {A['extra_attrs']['uid']}/{A['extra_attrs']['user']}/{A['extra_attrs']['changeset']} (A), "
             f"{B['extra_attrs']['uid']}/{B['extra_attrs']['user']}/{B['extra_attrs']['changeset']} (B).")
    L.append("- Attribute order in a node: `id, action, timestamp, visible, version, lat, lon` (package: `id, version, timestamp, lat, lon`). Nodes without children end with ` />`; a way or relation without children (a deleted way that had no tags) is written as `<way ...>` + newline + `</way>`. Special characters in values: `&quot;`, `&apos;`, `&amp;`.")
    L.append("- `src/osm_io.py:write_josm` reproduces `editedA.osm`, `editedB.osm` and `editedB_with_update.osm` byte for byte (checked in this run), so the synthetic files of item 6 have the real format.")
    return L


# ---------------------------------------------------------------- helpers for the workflow
class Ctx:
    pass


def derive(C, name, edited_path, key, extra=(), index=None, out=None):
    """Run 19_osm_submit.py; returns (CompletedProcess, osc path)."""
    b = C.cfg["bases"][key]
    out = out or C.work / f"{name}.osc"
    cmd = [PY, SRC / "19_osm_submit.py", b["osm"], edited_path, out, "--editor-index", C.cfg["editor_index"][key] if index is None else index, *extra]
    return sh(cmd), out


def ownership(C, editors, json_out):
    """editors: [(name, zone, osc, base)]."""
    cmd = [PY, SRC / "21_ownership_check.py", "--json", json_out]
    for e in editors:
        cmd += ["--editor", *e]
    r = sh(cmd)
    return r, (json.loads(pathlib.Path(json_out).read_text(encoding="utf-8")) if pathlib.Path(json_out).exists() else [])


def edge_summary(net_path):
    """{edge id: speed of the first lane} of non-internal edges."""
    out = {}
    for _, el in ET.iterparse(net_path):
        if el.tag == "edge":
            if el.get("function") != "internal":
                lane = el.find("lane")
                out[el.get("id")] = float(lane.get("speed")) if lane is not None else None
            el.clear()
    return out


def way_edges(summary, way):
    return {e: s for e, s in summary.items() if e.lstrip("-").split("#")[0] == str(way)}


def worst(rows):
    return max((r["severity"] for r in rows), key=lambda s: {"ok": 0, "warning": 1, "violation": 2}[s], default="-")


# ---------------------------------------------------------------- item 2
def section_workflow(C):
    cfg, work = C.cfg, C.work
    L = ["## 2. Full workflow on A and B (real format)\n"]
    ctl = []
    sub = {}
    for k in ("A", "B"):
        r, osc = derive(C, k, C.spike / cfg["files"][k], k)
        sub[k] = (r, osc)
        stats = json.loads(pathlib.Path(str(osc) + ".meta.json").read_text())["prepare"]
        ctl.append((f"19_osm_submit.py {k}", "exit 0, .osc written", f"exit {r.returncode}, prepare {stats}", "ok" if r.returncode == 0 else "FAIL"))
    r18 = sh([PY, SRC / "18_osm_conflicts.py", f"A={sub['A'][1]}", f"B={sub['B'][1]}"])
    ctl.append(("18_osm_conflicts.py A B", "exit 0, 0 conflicts, 0 collisions", f"exit {r18.returncode}: {r18.stdout.strip().splitlines()[-1]}", "ok" if r18.returncode == 0 else "FAIL"))
    own_json = str(work / "ownership_AB.json")
    r21, rows = ownership(C, [("A", "3", str(sub["A"][1]), cfg["bases"]["A"]["osm"]), ("B", "4", str(sub["B"][1]), cfg["bases"]["B"]["osm"])], own_json)
    C.rows_AB, C.r21_AB = rows, r21
    ctl.append(("21_ownership_check.py A B", "exit 1 (planted violations A6, A7, B6)", f"exit {r21.returncode}: {r21.stdout.strip().splitlines()[-1]}", "ok" if r21.returncode == 1 else "FAIL"))
    # merge / apply / check-refs
    merged_osc, merged_osm = work / "merged.osc", work / "merged.osm"
    m = sh(["osmium", "merge-changes", sub["A"][1], sub["B"][1], "-o", merged_osc, "--overwrite"])
    ap = sh(["osmium", "apply-changes", cfg["paths"]["full_base"], merged_osc, "-o", merged_osm, "--overwrite"])
    cr_b = sh(["osmium", "check-refs", "-r", cfg["paths"]["full_base"]]).stderr.strip().splitlines()
    cr_m = sh(["osmium", "check-refs", "-r", merged_osm]).stderr.strip().splitlines()
    cr_b, cr_m = [x for x in cr_b if "missing" in x], [x for x in cr_m if "missing" in x]
    ctl.append(("osmium merge-changes / apply-changes", "exit 0 / 0", f"exit {m.returncode} / {ap.returncode}", "ok" if m.returncode == ap.returncode == 0 else "FAIL"))
    ctl.append(("osmium check-refs: merged = base", "same 'missing' lines as the base", "identical" if cr_b == cr_m else f"base {cr_b} vs merged {cr_m}", "ok" if cr_b == cr_m else "FAIL"))
    # canonical comparison against the full base
    base = osm_io.read_osm(cfg["paths"]["full_base"])["objs"]
    merged = osm_io.read_osm(merged_osm)["objs"]
    expected = {k: osm_io.canon(e) for k, e in base.items()}
    changed_keys, created_keys, deleted_keys, version_ok = set(), set(), set(), 0
    per_editor = {}
    for k in ("A", "B"):
        shift = (cfg["editor_index"][k] + 1) * C.offset
        edited = osm_io.read_osm(C.spike / cfg["files"][k])["objs"]
        cnt = collections.Counter()
        mapid = lambda i: i if i > 0 else shift - i  # noqa: E731
        for (t, i), el in edited.items():
            act = el.get("action")
            if act == "delete":
                expected[(t, i)] = None
                deleted_keys.add((t, i))
                cnt["delete"] += 1
            elif i < 0:
                c = osm_io.canon(el)
                if t == "way":
                    c = ("way", tuple(mapid(x) for x in c[1]), c[2])
                expected[(t, mapid(i))] = c
                created_keys.add((t, mapid(i)))
                cnt["create"] += 1
            elif act == "modify":
                c = osm_io.canon(el)
                if c != expected[(t, i)]:
                    cnt["modify"] += 1
                    changed_keys.add((t, i))
                else:
                    cnt["modify_noop"] += 1
                expected[(t, i)] = c
        per_editor[k] = cnt
    exp_live = {k: v for k, v in expected.items() if v is not None}
    missing = sorted(set(exp_live) - set(merged))
    extra = sorted(set(merged) - set(exp_live))
    differ = sorted(k for k in set(exp_live) & set(merged) if osm_io.canon(merged[k]) != exp_live[k])
    n_changed_vs_base = sum(1 for k in merged if k in base and osm_io.canon(merged[k]) != osm_io.canon(base[k]))
    n_new = sum(1 for k in merged if k not in base)
    n_gone = sum(1 for k in base if k not in merged)
    for (t, i) in changed_keys:
        version_ok += int(merged[(t, i)].get("version") == str(int(base[(t, i)].get("version")) + 1))
    ctl.append(("merged objects = base + editors' changes (canonical)", "0 missing, 0 extra, 0 differing", f"{len(missing)} missing, {len(extra)} extra, {len(differ)} differing", "ok" if not (missing or extra or differ) else "FAIL"))
    exp_changed = sum(c["modify"] for c in per_editor.values())
    ctl.append(("objects changed vs base (existing)", f"{exp_changed} (modified by editors)", f"{n_changed_vs_base}", "ok" if n_changed_vs_base == exp_changed else "FAIL"))
    exp_new = sum(c["create"] for c in per_editor.values())
    exp_del = sum(c["delete"] for c in per_editor.values())
    ctl.append(("created / deleted objects", f"{exp_new} / {exp_del}", f"{n_new} / {n_gone}", "ok" if (n_new, n_gone) == (exp_new, exp_del) else "FAIL"))
    ctl.append(("version of modified objects = base + 1", f"{len(changed_keys)}", f"{version_ok}", "ok" if version_ok == len(changed_keys) else "FAIL"))
    # package vs full base
    drift = {}
    for k in ("A", "B"):
        pk = osm_io.read_osm(cfg["bases"][k]["osm"])["objs"]
        d = [key for key, e in pk.items() if key not in base or osm_io.canon(e) != osm_io.canon(base[key]) or e.get("version") != base[key].get("version")]
        drift[k] = (len(pk), len(d))
        ctl.append((f"v1 package {k} vs full base ({len(pk)} objects)", "0 objects differ (content, version)", f"{len(d)} differ", "ok" if not d else "FAIL"))
    # coordinates: 11 decimals -> osmium 7
    prec = []
    for k in ("A", "B"):
        edited = osm_io.read_osm(C.spike / cfg["files"][k])["objs"]
        to_m = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:2177", always_xy=True).transform
        for (t, i), el in sorted(edited.items()):
            if t == "node" and i > 0 and el.get("action") == "modify":
                b0 = base[(t, i)]
                x0, y0 = to_m(float(b0.get("lon")), float(b0.get("lat")))
                x1, y1 = to_m(float(el.get("lon")), float(el.get("lat")))
                x2, y2 = to_m(float(merged[(t, i)].get("lon")), float(merged[(t, i)].get("lat")))
                prec.append((k, i, math.hypot(x1 - x0, y1 - y0), math.hypot(x2 - x0, y2 - y0), math.hypot(x2 - x1, y2 - y1)))
    C.move_exact = {i: d for _, i, d, _, _ in prec}
    C.merged_coords_err = max(p[4] for p in prec)
    # netconvert
    ns = set()
    for key in changed_keys | created_keys | deleted_keys:
        if key in merged:
            els = [merged[key]]
            if key[0] == "way":
                els = [merged[("node", r)] for r in osm_io.way_refs(merged[key])]
            ns.update((float(e.get("lon")), float(e.get("lat"))) for e in els if e.tag == "node")
        elif key in base and key[0] == "node":
            ns.add((float(base[key].get("lon")), float(base[key].get("lat"))))
        elif key in base and key[0] == "way":
            ns.update((float(base[("node", r)].get("lon")), float(base[("node", r)].get("lat"))) for r in osm_io.way_refs(base[key]) if ("node", r) in base)
    mg = cfg["netconvert"]["margin_deg"]
    bbox = f"{min(x for x, _ in ns) - mg:.4f},{min(y for _, y in ns) - mg:.4f},{max(x for x, _ in ns) + mg:.4f},{max(y for _, y in ns) + mg:.4f}"
    nets = {}
    for label, osm in (("base", cfg["paths"]["full_base"]), ("merged", merged_osm)):
        r = sh(["netconvert", "--osm-files", osm, "-o", work / f"{label}.net.xml", *cfg["netconvert"]["options"], bbox])
        (work / f"netconvert_{label}.log").write_text(r.stdout + r.stderr, encoding="utf-8")
        ok = "Success." in r.stdout
        nets[label] = edge_summary(work / f"{label}.net.xml") if ok else {}
        ctl.append((f"netconvert {label} (bbox {bbox})", "Success.", "Success., %d edges" % len(nets[label]) if ok else "FAILED", "ok" if ok else "FAIL"))
    C.nets, C.bbox, C.merged, C.base_objs = nets, bbox, merged, base
    C.created_keys, C.deleted_keys, C.changed_keys = created_keys, deleted_keys, changed_keys
    net_rows = []
    pl = cfg["planted"]
    way_expect = {  # case -> (way id in the net, expected speed m/s or None)
        "A1": (27717899, 30 / 3.6), "A2": (421983573, 40 / 3.6), "B1": (16313072, 40 / 3.6), "B2": (506664739, 40 / 3.6)}
    for case, (w, sp) in way_expect.items():
        eb, em = way_edges(nets["base"], w), way_edges(nets["merged"], w)
        got = sorted({round(v, 2) for v in em.values()})
        net_rows.append((case, f"way {w}", f"{len(eb)} edges, speeds {sorted({round(v, 2) for v in eb.values()})}", f"{len(em)} edges, speeds {got}",
                         f"{sp:.2f}", "ok" if em and got == [round(sp, 2)] else "FAIL"))
    for case, k in (("A4", "A"), ("B4", "B")):
        wid = next(i for t, i in created_keys if t == "way" and (i // C.offset) == cfg["editor_index"][k] + 1)
        em = way_edges(nets["merged"], wid)
        net_rows.append((case, f"new way {wid}", "0 edges", f"{len(em)} edges {sorted(em)}", ">= 1 edge", "ok" if em else "FAIL"))
    for case in ("A5", "B5"):
        w = pl[case]["way"]
        eb, em = way_edges(nets["base"], w), way_edges(nets["merged"], w)
        net_rows.append((case, f"deleted way {w}", f"{len(eb)} edges", f"{len(em)} edges", "0 edges after" if eb else "n/a (not imported by netconvert)", "ok" if not em else "FAIL"))
    L.append("Control table:\n")
    L.append(md_table(["Check", "Expected", "Actual", "Status"], ctl))
    L.append(f"\nPer editor (from the JOSM files): A {dict(per_editor['A'])}, B {dict(per_editor['B'])}. `modify` counts objects whose canonical content really changed; `modify_noop` would be marked `action='modify'` without a change.")
    L.append(f"\nA change derived against a zone package and applied to the full base: {'**gives exactly the objects the editors changed**' if not (missing or extra or differ) else '**does not give exactly the changed objects**'}. "
             f"Compared {len(exp_live)} objects of the expected result (full base + changes) with the {len(merged)} objects of `merged.osm`: missing {len(missing)}, extra {len(extra)}, differing {len(differ)}. "
             f"The 11-decimal coordinates written by JOSM are stored by osmium with 7 decimals; the largest displacement caused by this is {C.merged_coords_err * 100:.2f} cm.")
    if missing or extra or differ:
        L.append(f"\nFirst differences: missing {missing[:5]}, extra {extra[:5]}, differing {differ[:5]}")
    L.append(f"\nnetconvert (`{' '.join(cfg['netconvert']['options'])} {bbox}`, defaults otherwise, as in docs/SETUP.md 6b) on the full base and on the merged file; effect on the edges:\n")
    L.append(md_table(["Case", "Object", "Base net", "Merged net", "Expected", "Status"], net_rows))
    C.ctl_ok = all(r[-1] == "ok" for r in ctl) and all(r[-1] == "ok" for r in net_rows)
    C.sub = sub
    C.hash_files += [sub["A"][1], sub["B"][1], merged_osc, merged_osm, work / "ownership_AB.json"]
    C.hash_extra["edge_summary"] = json.dumps({k: sorted(v.items()) for k, v in nets.items()}, sort_keys=True)
    L.append("")
    return L


# ---------------------------------------------------------------- item 3
def section_planted(C):
    cfg = C.cfg
    own, spans, white = C.tables
    rows = C.rows_AB
    offset = C.offset
    L = ["## 3. Planted cases (classified by the ownership tables)\n",
         "Owner and `spans_zones` come from `ownership_{ways,nodes}.csv`; the classification is the output of `src/21_ownership_check.py` (`ok` / `warning` / `violation`).\n"]
    out = []
    mm = {}
    edited = {k: osm_io.read_osm(C.spike / cfg["files"][k])["objs"] for k in ("A", "B")}

    def rows_for(ed, keys):
        return [r for r in rows if r["editor"] == ed and (r["type"], r["id"]) in keys and not r["category"].startswith(("cross_editor", "relation_member"))]

    for case, p in cfg["planted"].items():
        ed, kind = p["editor"], p["kind"]
        shift = (cfg["editor_index"][ed] + 1) * offset
        if kind == "new_way":
            wneg = next(i for (t, i), el in edited[ed].items() if t == "way" and i < 0 and osm_io.way_refs(el)[0] == p["anchor"])
            nodes = [r for r in osm_io.way_refs(edited[ed][("way", wneg)]) if r < 0]
            keys = {("way", shift - wneg)} | {("node", shift - n) for n in nodes}
            obj = f"new way {wneg} (osc {shift - wneg}) from node {p['anchor']}"
            ow = f"anchor node: zone {own['node'].get(p['anchor'])}"
        elif kind == "deleted_way_and_node":
            keys = {("way", p["way"]), ("node", p["node"])}
            obj = f"way {p['way']} + node {p['node']}"
            ow = f"way: zone {own['way'].get(p['way'])}, node: zone {own['node'].get(p['node'])}"
        else:
            keys = {(kind, p["id"])}
            obj = f"{kind} {p['id']}"
            ow = f"zone {own[kind].get(p['id'])}" + (", spans zones" if kind == "way" and p["id"] in spans else "") + (", whitelisted" if kind == "node" and p["id"] in white else "")
        rr = rows_for(ed, keys)
        act = worst(rr)
        cats = sorted({f"{r['category']}" for r in rr})
        extra = ""
        if kind == "node":
            r0 = next((r for r in rr if "move_m" in r), None)
            if r0:
                extra = f"; moved {r0['move_m']} m (JOSM file: {C.move_exact.get(p['id'], 0):.2f} m); rule (c) fired: {r0['rule_c_fired']}"
        passed = (act == p["expected"])
        if case == "A1":
            passed = passed and "spanning_owner_edit" in cats
        if case in ("A6", "A7"):
            passed = passed and "other_zone" in cats
        if case == "B6":
            extra = f"; owner table says zone {own['way'].get(p['id'])}, not zone 4, so B6 {'tests a violation (owned by another zone)' if own['way'].get(p['id']) != 4 else 'did NOT test a violation'}"
        mm[case] = (act, cats)
        out.append((case, obj, ow, p["change"], p["expected"], act, ", ".join(cats) + extra, "pass" if passed else "FINDING"))
    L.append(md_table(["Case", "Object", "Owner (table)", "Change", "Expected", "Actual", "Categories / notes", "Result"], out))
    # cross-editor + relation
    cross = [r for r in rows if r["category"] == "cross_editor_way"]
    rel = [r for r in rows if r["category"] == "relation_member"]
    rc = cfg["relation_case"]
    b1 = [r for r in cross if "way 16313072" in r["reason"]]
    L.append("\nSemantic warnings (rule d), listed from `21_ownership_check.py`:\n")
    L.append(md_table(["Case", "Expected", "Actual", "Result"], [
        ("B1 vs A6 (cross-editor)", "warning: node 165109460 moved by A is used by way 16313072 changed by B", "; ".join(r["reason"] for r in b1) or "none", "pass" if b1 else "FINDING"),
        (f"relation {rc['id']} (turn restriction, via node {rc['via_node']})", "warning: moved node is a member of the relation",
         "; ".join(r["reason"] for r in rel if str(rc["id"]) in r["reason"]) or "none", "pass" if any(str(rc["id"]) in r["reason"] for r in rel) else "FINDING")]))
    L.append(f"\nOwner of relation {rc['id']} by the table: zone {own['relation'].get(rc['id'])} (via node {rc['via_node']}); the relation itself was not edited and is not marked in the JOSM file ({'confirmed' if edited['A'][('relation', rc['id'])].get('action') is None else 'marked'}).")
    L.append("\nAll rows of `21_ownership_check.py` for A and B (full output):\n")
    L.append("```\n" + C.r21_AB.stdout.rstrip() + "\n```")
    C.planted_ok = all(r[-1] == "pass" for r in out)
    C.planted_summary = out
    L.append("")
    return L


# ---------------------------------------------------------------- item 4
def section_contamination(C):
    cfg = C.cfg
    sub19 = C.mod19
    L = ["## 4. Contaminated file `editedB_with_update.osm`\n"]
    out = C.work / "Bu.osc"
    if out.exists():
        out.unlink()
    r, _ = derive(C, "Bu", C.spike / cfg["files"]["B_update"], "B", out=out)
    log_lines = [x for x in r.stderr.splitlines() if "ERROR" in x]
    base = osm_io.read_osm(cfg["bases"]["B"]["osm"])["objs"]
    full = C.base_objs
    f = osm_io.read_osm(C.spike / cfg["files"]["B_update"])
    bad = sub19.detect_contamination(base, f["objs"])
    L.append(f"`19_osm_submit.py` on this file: **exit code {r.returncode}** (required: 3), `.osc` written: **{out.exists()}** (required: no). Offenders by rule (the user name is not used):\n")
    L.append(md_table(["Rule", "Objects"], [
        ("uid / user / changeset that the package object lacks", len(bad["server_metadata"])),
        ("visible='false'", f"{len(bad['invisible'])}: " + ", ".join(f"{t} {i}" for t, i in sorted(bad["invisible"]))),
        ("existing object with a version different from the base", f"{len(bad['version_differs'])} ({sum(1 for k in bad['version_differs'] if k[0] == 'node')} nodes, {sum(1 for k in bad['version_differs'] if k[0] == 'way')} ways)"),
        ("positive-id object not in the base", f"{len(bad['not_in_base'])}: " + ", ".join(f"{t} {i}" for t, i in sorted(bad["not_in_base"]))),
    ]))
    exp = [("node", i) for i in cfg["contamination_expected"]["nodes"]] + [("way", i) for i in cfg["contamination_expected"]["ways"]]
    flagged = set().union(*[set(v) for v in bad.values()])
    exp_rows = []
    for k in exp:
        el = f["objs"].get(k)
        exp_rows.append((f"{k[0]} {k[1]}", "present" if el is not None else "absent", f"action={el.get('action')}, visible={el.get('visible')}, version {el.get('version')} (package {base[k].get('version')}), timestamp {el.get('timestamp')}" if el is not None else "-",
                         ", ".join(rule for rule, ks in bad.items() if k in ks) or "NOT FLAGGED", "pass" if k in flagged else "FINDING"))
    L.append("\nThe six objects the brief expects (deleted upstream on 26-27 Oct 2026, after the snapshot of 23 Oct):\n")
    L.append(md_table(["Object", "In file", "Attributes", "Flagged by", "Result"], exp_rows))
    # drift
    edited_own = {k for k, e in f["objs"].items() if e.get("action") in ("modify", "delete") or k[1] < 0}
    clean = osm_io.read_osm(C.spike / cfg["files"]["B"])["objs"]
    own_edits = {k for k, e in clean.items() if e.get("action") in ("modify", "delete") or k[1] < 0}
    drift_v, drift_c = [], []
    for k, e in f["objs"].items():
        if k in base and k not in own_edits:
            if e.get("version") != base[k].get("version"):
                drift_v.append(k)
            elif osm_io.canon(e) != osm_io.canon(base[k]):
                drift_c.append(k)
    drift_all = sorted(set(drift_v) | set(drift_c))
    only_meta = [k for k, e in f["objs"].items() if k in base and "uid" in e.attrib and k not in drift_all and k not in own_edits]
    missing = sorted(set(base) - set(f["objs"]))
    extra = sorted(k for k in f["objs"] if k[1] > 0 and k not in base)
    extra_refs = collections.defaultdict(list)
    for k, e in f["objs"].items():
        if k[0] == "way":
            for r_ in osm_io.way_refs(e):
                if ("node", r_) in {x for x in extra}:
                    extra_refs[r_].append(k[1])
    edited_by_b = [k for k in own_edits if k in f["objs"] and osm_io.canon(f["objs"][k]) != osm_io.canon(clean.get(k, f["objs"][k]))]
    L.append("\nDifferences from the package apart from the editor's own edits (B1-B6, found by comparing with the clean `editedB.osm`):\n")
    L.append(md_table(["Measure", "Count / ids"], [
        ("objects of the package missing from the file", len(missing)),
        ("existing objects (not edited by the user) with a different version", f"{len(drift_v)} ({sum(1 for k in drift_v if k[0] == 'node')} nodes, {sum(1 for k in drift_v if k[0] == 'way')} ways, {sum(1 for k in drift_v if k[0] == 'relation')} relations); of these deleted upstream (visible='false'): {sum(1 for k in drift_v if f['objs'][k].get('visible') == 'false')}"),
        ("same version but different canonical content", len(drift_c)),
        ("objects that differ from the package apart from B1-B6 (version or content)", len(drift_all)),
        ("objects with server metadata but identical version and content (refreshed only)", len(only_meta)),
        ("objects with uid / user / changeset in total", len(bad["server_metadata"])),
        ("extra positive-id nodes (not in the package)", f"{len(extra)}: " + ", ".join(str(i) for _, i in extra)),
        ("... of these in the full base `ring1_roads.osm` (snapshot of 23 Oct)", f"{sum(1 for k in extra if k in full)} of {len(extra)}"),
        ("... of these used by a way in the file", f"{sum(1 for k in extra if extra_refs.get(k[1]))}: " + "; ".join(f"{k[1]} -> ways {sorted(extra_refs[k[1]])}" for k in extra if extra_refs.get(k[1]))),
    ]))
    L.append("\nFirst lines of the refusal (stderr of `19_osm_submit.py`):\n```\n" + "\n".join(x.split(" ", 2)[2] if x.count(" ") > 2 else x for x in log_lines[:3]) + "\n  ...\n```")
    C.contam = {"exit": r.returncode, "osc": out.exists(), "flagged_all": all(k in flagged for k in exp)}
    L.append("")
    return L


# ---------------------------------------------------------------- items 5 and 6
def jmod(C, src_key, fn, name):
    """Copy of an edited file with a scripted edit (written in the JOSM format). fn(children, ctx) -> list of focus keys (file ids)."""
    f = osm_io.read_osm(C.spike / C.cfg["files"][src_key])
    kids = list(f["root"])
    focus = fn(kids, f["objs"])
    path = C.work / "syn" / f"{name}.osm"
    path.parent.mkdir(exist_ok=True)
    osm_io.write_josm(path, kids)
    return path, focus


def new_el(tag, i, **attrs):
    el = ET.Element(tag)
    el.set("id", str(i))
    el.set("action", "modify")
    el.set("visible", "true")
    for k, v in attrs.items():
        el.set(k, str(v))
    return el


def insert_front(kids, el):
    """New objects go first within their type, like JOSM (negative ids sort first)."""
    idx = next((n for n, k in enumerate(kids) if k.tag == el.tag), len(kids))
    kids.insert(idx, el)


def section_synthetic(C):
    cfg = C.cfg
    own, spans, white = C.tables
    offset = C.offset
    bA = osm_io.read_osm(cfg["bases"]["A"]["osm"])["objs"]
    poly = shape(json.loads((pathlib.Path(cfg["bases"]["A"]["osm"]).parent / "zone_3.geojson").read_text(encoding="utf-8"))["geometry"])
    node_ways = collections.defaultdict(set)
    for (t, i), e in bA.items():
        if t == "way":
            for r_ in osm_io.way_refs(e):
                node_ways[r_].add(i)
    editedA = osm_io.read_osm(C.spike / cfg["files"]["A"])["objs"]
    a_touched = {k[1] for k, e in editedA.items() if e.get("action")} | {r_ for (t, i), e in editedA.items() if t == "way" and e.get("action") for r_ in osm_io.way_refs(bA.get((t, i), e))}
    log_ok = lambda k: k[0] == "node" and not bA[k].findall("tag") and k[1] not in a_touched and k[1] not in white  # noqa: E731
    pick = {
        "unowned_way": min(i for (t, i) in bA if t == "way" and own["way"].get(i) is None and i not in a_touched),
        "dangling_node": min(i for (t, i) in bA if log_ok((t, i)) and own["node"].get(i) == 3 and len(node_ways[i]) == 1 and own["way"].get(next(iter(node_ways[i]))) == 3 and next(iter(node_ways[i])) not in a_touched),
        "shared_node": min(i for (t, i) in bA if log_ok((t, i)) and own["node"].get(i) == 3 and any(own["way"].get(w) not in (3, None) for w in node_ways[i]) and not (node_ways[i] & a_touched)),
        "own_only_node": min(i for (t, i) in bA if log_ok((t, i)) and own["node"].get(i) == 3 and node_ways[i] and all(own["way"].get(w) == 3 for w in node_ways[i]) and not (node_ways[i] & a_touched)),
        "other_zone_node": min(i for (t, i) in bA if own["node"].get(i) == 4 and i not in white and i not in a_touched),
        "white_node": min(i for i in white if ("node", i) in bA and 3 in white[i] and i not in a_touched),
    }
    inside = poly.representative_point()
    outside = (poly.bounds[2] + 0.01, poly.bounds[3] + 0.01)
    lat0 = 51.1
    dlon = lambda m: m / (111320.0 * math.cos(math.radians(lat0)))  # noqa: E731
    cases = []   # (id, description, expected text, expected (sev, cat), exit19, focus fn)

    def setattr_(e, **kw):
        for k, v in kw.items():
            e.set(k, v)

    def edit_unowned(kids, objs):
        w = objs[("way", pick["unowned_way"])]
        ET.SubElement(w, "tag", k="note", v="test")
        w.set("action", "modify")
        w[:] = sorted(w, key=lambda x: (x.tag != "nd", x.get("k") or ""))  # nd first, tags alphabetical (as JOSM)
        return [("way", pick["unowned_way"])]

    def new_node_outside(kids, objs):
        insert_front(kids, new_el("node", -39001, lat=f"{outside[1]:.11f}", lon=f"{outside[0]:.11f}"))
        return [("node", -39001)]

    def delete_used(kids, objs):
        n = objs[("node", pick["dangling_node"])]
        n.set("action", "delete")
        return [("node", pick["dangling_node"])]

    def anchored_other(kids, objs):
        a = objs[("node", pick["other_zone_node"])]
        insert_front(kids, new_el("node", -39003, lat=f"{inside.y:.11f}", lon=f"{inside.x:.11f}"))
        w = new_el("way", -39004)
        for ref in (pick["other_zone_node"], -39003):
            ET.SubElement(w, "nd", ref=str(ref))
        ET.SubElement(w, "tag", k="highway", v="service")
        insert_front(kids, w)
        return [("way", -39004), ("node", -39003)]

    def move_node(node, metres):
        def f(kids, objs):
            n = objs[("node", node)]
            n.set("lon", f"{float(n.get('lon')) + dlon(metres):.11f}")
            n.set("action", "modify")
            return [("node", node)]
        return f

    def tag_white(kids, objs):
        n = objs[("node", pick["white_node"])]
        ET.SubElement(n, "tag", k="note", v="test")
        n.set("action", "modify")
        n[:] = sorted(n, key=lambda x: x.get("k"))
        return [("node", pick["white_node"])]

    cases = [
        ("S1", f"edit of unowned way {pick['unowned_way']} (owner 0, note=test)", ("violation", "unowned"), 1, edit_unowned),
        ("S2", "new node outside the zone polygon", ("violation", "new_outside_polygon"), 1, new_node_outside),
        ("S3", f"delete node {pick['dangling_node']} that a remaining way ({next(iter(node_ways[pick['dangling_node']]))}) still uses", ("violation", "dangling_reference"), 1, delete_used),
        ("S4", f"new way anchored at node {pick['other_zone_node']} (owner zone 4)", ("violation", "new_way_other_zone"), 1, anchored_other),
        ("S8a", f"own node {pick['shared_node']} used by a way of another zone, moved 5 m", ("violation", "move_exceeds_threshold"), 1, move_node(pick["shared_node"], 5.0)),
        ("S8b", f"same node {pick['shared_node']} moved 2 m (below the 3 m threshold)", ("ok", "own"), 0, move_node(pick["shared_node"], 2.0)),
        ("S8c", f"own node {pick['own_only_node']} used only by own ways, moved 5 m", ("ok", "own"), 0, move_node(pick["own_only_node"], 5.0)),
        ("S9", f"tag edit of whitelisted node {pick['white_node']} (zones {sorted(white[pick['white_node']])}, owner {own['node'].get(pick['white_node'])})", ("warning", "whitelisted"), 2, tag_white),
    ]
    results = []
    det = {}
    for cid, desc, (esev, ecat), eexit, fn in cases:
        path, focus = jmod(C, "A", fn, cid)
        r, osc = derive(C, cid, path, "A", out=C.work / "syn" / f"{cid}.osc")
        shift = (cfg["editor_index"]["A"] + 1) * offset
        fk = {(t, shift - i if i < 0 else i) for t, i in focus}
        if r.returncode != 0:
            results.append((cid, desc, f"{esev}/{ecat}", f"19 exit {r.returncode}", "FAIL"))
            continue
        r21, rows = ownership(C, [("A", "3", str(osc), cfg["bases"]["A"]["osm"])], str(C.work / "syn" / f"{cid}.own.json"))
        rr = [x for x in rows if (x["type"], x["id"]) in fk]
        got = sorted({(x["severity"], x["category"]) for x in rr if x["severity"] != "ok" or x["category"] in (ecat,)})
        match = (esev, ecat) in {(x["severity"], x["category"]) for x in rr}
        det[cid] = r21.returncode
        # the real A edits are in every file: the exit code is only informative here, so judge by the focus rows
        results.append((cid, desc, f"{esev} / {ecat}", "; ".join(f"{s} / {c}" for s, c in got) or "no row", "pass" if match else "FAIL"))
        if cid == "S3":
            ap = sh(["osmium", "apply-changes", cfg["paths"]["full_base"], osc, "-o", C.work / "syn" / "S3.osm", "--overwrite"])
            cr = [x for x in sh(["osmium", "check-refs", C.work / "syn" / "S3.osm"]).stderr.splitlines() if "missing" in x or "Nodes" in x]
            results.append(("S3b", "osmium check-refs on the result of S3 (why the rule exists)", "missing nodes in ways", ("; ".join(cr)) or "no output", "pass" if any("missing" in x and not x.strip().endswith(": 0") for x in cr) else "FAIL"))
    # S5: same negative ids in both editors
    mapping = {-626: -1066, -26142: -28582, -26143: -28583}

    def clash(kids, objs):
        for e in kids:
            if e.tag in osm_io.TYPES and int(e.get("id")) in mapping:
                e.set("id", str(mapping[int(e.get("id"))]))
            for c in e:
                if c.tag == "nd" and int(c.get("ref")) in mapping:
                    c.set("ref", str(mapping[int(c.get("ref"))]))
        return []

    pathB, _ = jmod(C, "B", clash, "S5_B")
    ncA, ncB = C.work / "syn" / "S5_A_nr.osc", C.work / "syn" / "S5_B_nr.osc"
    rA, _ = derive(C, "x", C.spike / cfg["files"]["A"], "A", extra=["--no-renumber"], out=ncA)
    rB, _ = derive(C, "x", pathB, "B", extra=["--no-renumber"], out=ncB)
    r18 = sh([PY, SRC / "18_osm_conflicts.py", f"A={ncA}", f"B={ncB}"])
    coll = [x for x in r18.stdout.splitlines() if x.startswith("COLLISION")]
    results.append(("S5a", "both editors use the same negative ids (-1066, -28582, -28583); 18 before renumbering", "exit 1, 3 COLLISION lines", f"exit {r18.returncode}, {len(coll)} COLLISION lines", "pass" if r18.returncode == 1 and len(coll) == 3 else "FAIL"))
    mo = C.work / "syn" / "S5_nr_merged.osc"
    sh(["osmium", "merge-changes", ncA, ncB, "-o", mo, "--overwrite"])
    mr = sh(["osmium", "apply-changes", cfg["paths"]["full_base"], mo, "-o", C.work / "syn" / "S5_nr.osm", "--overwrite"])
    res_nr = osm_io.read_osm(C.work / "syn" / "S5_nr.osm")["objs"] if mr.returncode == 0 else {}
    new_nr = sum(1 for k in res_nr if k not in C.base_objs)
    rA2, osA = derive(C, "x", C.spike / cfg["files"]["A"], "A", out=C.work / "syn" / "S5_A.osc")
    rB2, osB = derive(C, "x", pathB, "B", out=C.work / "syn" / "S5_B.osc")
    r18b = sh([PY, SRC / "18_osm_conflicts.py", f"A={osA}", f"B={osB}"])
    mo2 = C.work / "syn" / "S5_merged.osc"
    sh(["osmium", "merge-changes", osA, osB, "-o", mo2, "--overwrite"])
    sh(["osmium", "apply-changes", cfg["paths"]["full_base"], mo2, "-o", C.work / "syn" / "S5.osm", "--overwrite"])
    res = osm_io.read_osm(C.work / "syn" / "S5.osm")["objs"]
    new_r = sorted(k for k in res if k not in C.base_objs)
    results.append(("S5b", "same ids, after renumbering (editor 0 / 1): 18 and merge", "18 exit 0; 6 new objects (2 ways + 4 nodes) with distinct ids", f"18 exit {r18b.returncode}; {len(new_r)} new objects ({sum(1 for t, _ in new_r if t == 'way')} ways, {sum(1 for t, _ in new_r if t == 'node')} nodes)", "pass" if r18b.returncode == 0 and len(new_r) == 6 else "FAIL"))
    results.append(("S5c", "same ids WITHOUT renumbering: merge-changes + apply-changes (what 18 prevents)", "only 3 new objects survive (silent loss)", f"{new_nr} new objects in the result", "pass" if new_nr == 3 else "FAIL"))
    # S6: base checks (exit 4) and contamination variants (exit 3)
    syn = C.work / "syn"
    zone3 = pathlib.Path(cfg["bases"]["A"]["osm"])
    bad_base = syn / "zone_3.osm"
    bad_base.write_bytes(zone3.read_bytes() + b"\n")
    shutil.copy(zone3.with_suffix(".json"), syn / "zone_3.json")
    cmd = [PY, SRC / "19_osm_submit.py", bad_base, C.spike / cfg["files"]["A"], syn / "S6a.osc", "--editor-index", 0]
    r6a = sh(cmd)
    results.append(("S6a", "base differs from the sidecar sha256 (one extra byte)", "exit 4, no .osc", f"exit {r6a.returncode}, .osc: {(syn / 'S6a.osc').exists()}", "pass" if r6a.returncode == 4 and not (syn / "S6a.osc").exists() else "FAIL"))
    nosc = syn / "nosidecar"
    nosc.mkdir(exist_ok=True)
    shutil.copy(zone3, nosc / "zone_3.osm")
    r6b = sh([PY, SRC / "19_osm_submit.py", nosc / "zone_3.osm", C.spike / cfg["files"]["A"], syn / "S6b.osc", "--editor-index", 0])
    results.append(("S6b", "base without sidecar and without --base-sha256", "exit 4", f"exit {r6b.returncode}", "pass" if r6b.returncode == 4 else "FAIL"))
    r6c = sh([PY, SRC / "19_osm_submit.py", zone3, C.spike / cfg["files"]["A"], syn / "S6c.osc", "--editor-index", 0, "--base-sha256", "0" * 64])
    results.append(("S6c", "explicit wrong --base-sha256", "exit 4", f"exit {r6c.returncode}", "pass" if r6c.returncode == 4 else "FAIL"))
    r6d = sh([PY, SRC / "19_osm_submit.py", cfg["bases"]["B"]["osm"], C.spike / cfg["files"]["A"], syn / "S6d.osc", "--editor-index", 0])
    results.append(("S6d", "zone 3 edits submitted against the zone 4 package (its sidecar matches)", "refused (exit 3: positive ids not in the base)", f"exit {r6d.returncode}", "pass" if r6d.returncode == 3 else "FAIL"))
    first_untouched = lambda objs, t: next(k for k, e in objs.items() if k[0] == t and not e.get("action") and k[1] > 0)  # noqa: E731

    def c_uid(kids, objs):
        objs[first_untouched(objs, "node")].set("uid", "1")
        return []

    def c_vis(kids, objs):
        objs[first_untouched(objs, "way")].set("visible", "false")
        return []

    def c_ver(kids, objs):
        e = objs[first_untouched(objs, "node")]
        e.set("version", str(int(e.get("version")) + 1))
        return []

    def c_pos(kids, objs):
        insert_front(kids, ET.fromstring("<node id='99999999999' timestamp='2026-10-27T00:00:00Z' visible='true' version='1' lat='51.1' lon='17.0' />"))
        return []

    for cid, desc, fn in (("S7a", "uid attribute on an untouched node", c_uid), ("S7b", "visible='false' on an untouched way", c_vis),
                          ("S7c", "version of an untouched node differs from the base", c_ver), ("S7d", "positive-id node that is not in the base", c_pos)):
        p, _ = jmod(C, "A", fn, cid)
        r7 = sh([PY, SRC / "19_osm_submit.py", cfg["bases"]["A"]["osm"], p, syn / f"{cid}.osc", "--editor-index", 0])
        results.append((cid, desc, "exit 3, no .osc", f"exit {r7.returncode}, .osc: {(syn / f'{cid}.osc').exists()}", "pass" if r7.returncode == 3 and not (syn / f"{cid}.osc").exists() else "FAIL"))
    # S10: base sha recorded in the meta file
    meta = json.loads(pathlib.Path(str(C.sub["A"][1]) + ".meta.json").read_text())
    results.append(("S10", "the submission records the base sha256 (OUT.osc.meta.json)", cfg["bases"]["A"]["sha256"], meta["base_sha256"], "pass" if meta["base_sha256"] == cfg["bases"]["A"]["sha256"] else "FAIL"))
    # S11: 21 refuses an .osc derived against another base (exit 4)
    r21b = sh([PY, SRC / "21_ownership_check.py", "--editor", "A", "3", C.sub["A"][1], cfg["bases"]["B"]["osm"]])
    results.append(("S11", "21_ownership_check.py with A.osc and the zone 4 package as base", "exit 4", f"exit {r21b.returncode}", "pass" if r21b.returncode == 4 else "FAIL"))
    L = ["## 5. Safeguards and 6. Synthetic coverage (real format)\n",
         "Synthetic files are copies of `editedA.osm` / `editedB.osm` with one scripted edit each, written by `osm_io.write_josm` (byte-identical to JOSM output for the real files). "
         "Judged on the rows of the added object only; the real edits stay in the file. Objects were picked deterministically from the ownership tables: "
         + ", ".join(f"{k} = {v}" for k, v in pick.items()) + ".\n"]
    L.append(md_table(["Case", "Edit", "Expected", "Actual", "Result"], results))
    L.append("\nExit codes (all scripts):\n")
    L.append(md_table(["Code", "Meaning", "Script"], [
        (0, "ok", "all"), (1, "violation or conflict (ownership violation; same object / negative id changed by several editors)", "21, 18"),
        (2, "warnings only", "21"), (3, "contaminated input, nothing written", "19"), (4, "base mismatch / base not verifiable / .osc from another base", "19, 21")]))
    C.syn_ok = all(r[-1] == "pass" for r in results)
    C.syn_results = results
    C.hash_extra["synthetic"] = json.dumps(results, sort_keys=True)
    L.append("")
    return L


# ---------------------------------------------------------------- script changes
def section_changes(C):
    """Run the 04s versions of 19_osm_submit.py (from git HEAD) on the real files and compare with the new version."""
    cfg = C.cfg
    old = C.work / "19_osm_submit_04s.py"
    g = subprocess.run(["git", "show", "HEAD:src/19_osm_submit.py"], capture_output=True, text=True)
    old.write_text(g.stdout, encoding="utf-8")
    rows = []
    for k in ("A", "B"):
        o = C.work / f"old_{k}.osc"
        r = sh([PY, old, cfg["bases"][k]["osm"], C.spike / cfg["files"][k], o, "--editor-index", cfg["editor_index"][k]])
        same = r.returncode == 0 and o.read_bytes() == C.sub[k][1].read_bytes()
        rows.append((f"04s `19_osm_submit.py` on edited{k}.osm", "unchanged result", f"exit {r.returncode}; .osc byte-identical to the new one: {same}", "ok" if same else "DIFFERS"))
    o = C.work / "old_Bu.osc"
    r = sh([PY, old, cfg["bases"]["B"]["osm"], C.spike / cfg["files"]["B_update"], o, "--editor-index", 1])
    n_old = sum(1 for _, el in ET.iterparse(o) if el.tag in osm_io.TYPES) if o.exists() else 0
    rows.append(("04s `19_osm_submit.py` on editedB_with_update.osm", "must refuse", f"exit {r.returncode}, .osc with {n_old} objects written (bumped versions of refreshed objects, deletes of server-deleted objects)", "ACCEPTED (defect)" if r.returncode == 0 else "refused"))
    ob = ET.parse(C.sub["A"][1]).getroot()
    creates = sum(len(b) for b in ob if b.tag == "create")
    new_in_modify = sum(1 for b in ob if b.tag == "modify" for el in b if int(el.get("id")) > C.offset)
    dels = [el for b in ob if b.tag == "delete" for el in b]
    rows.append(("osmium output for new objects", "`<create>`", f"{creates} objects in `<create>`, {new_in_modify} new objects inside `<modify>` (no version); `osmium apply-changes` accepts them", "info"))
    rows.append(("osmium output for deleted objects", "with `<nd>` / tags", f"{len(dels)} deleted objects, children: {sum(len(list(el)) for el in dels)} (osmium writes id, version, timestamp only)", "info"))
    L = ["## 7. What broke in the scripts and what was changed\n",
         "Nothing in the quote style, deletions without `<nd>`, `action='modify'` on new objects or the alphabetical tag order broke `18_osm_conflicts.py` or `19_osm_submit.py`: they parse with `xml.etree`, compare canonical signatures (tags sorted, `nd` order, 7-decimal coordinates) and `osmium sort` / `derive-changes` accept the JOSM attributes (`visible`, `action`). "
         "The real defect was missing guards.\n", md_table(["Check", "Expected", "Actual", "Status"], rows), "",
         "Changes made:\n",
         "- `src/19_osm_submit.py`: refuses a base whose sha256 differs from the sidecar `sha256_extract` (or an explicit `--base-sha256`), or that cannot be verified (exit 4); refuses contaminated input by the four rules of item 4 (exit 3, no `.osc`); the changed-object test now uses `osm_io.canon`; writes `OUT.osc.meta.json` (base and edited sha256, editor, shift, prepare counts).",
         "- `src/osm_io.py` (new, shared helper): parsing, canonical content, `write_josm` (JOSM-format writer used for the synthetic files).",
         "- `src/21_ownership_check.py` (new): ownership classification, rules (b), (c), (d), exit codes 0/1/2/4.",
         "- `src/18_osm_conflicts.py`: unchanged. It reports a negative-id collision only on `.osc` files made with `--no-renumber` (after renumbering the id blocks of the editors cannot collide).",
         "- `src/20_josm_file_facts.py`, `src/24_real_workflow.py`, `config/21_ownership_check.yaml`, `config/24_real_josm.yaml`, `scripts/josm_pilot.sh`: new.", ""]
    C.changes_ok = all(r[-1] in ("ok", "info", "refused", "ACCEPTED (defect)") for r in rows)
    return L


def main():
    cfg_path = sys.argv[1] if len(sys.argv) > 1 else "config/24_real_josm.yaml"
    cfg = yaml.safe_load(open(cfg_path, encoding="utf-8"))
    p = cfg["paths"]
    pathlib.Path(p["log"]).parent.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(p["log"], mode="a"), logging.StreamHandler()])
    r = subprocess.run(["scripts/verify_inputs.sh"], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("verify_inputs.sh failed: " + r.stdout + r.stderr)
    for k, b in cfg["bases"].items():
        if sha(b["osm"]) != b["sha256"]:
            raise SystemExit(f"base {k} ({b['osm']}) has another sha256 than expected; stop")
    work = pathlib.Path(p["workdir"])
    shutil.rmtree(work / "work", ignore_errors=True)
    work = work / "work"
    work.mkdir(parents=True)
    C = Ctx()
    C.cfg, C.work, C.spike = cfg, work, pathlib.Path(p["spike_dir"])
    C.offset = yaml.safe_load(open("config/17_workflow_spike.yaml", encoding="utf-8"))["renumber_offset"]
    C.hash_files, C.hash_extra = [], {}
    C.mod19 = load_script("19_osm_submit.py")
    C.mod21 = load_script("21_ownership_check.py")
    C.tables = C.mod21.load_tables(cfg["paths"]["ownership_dir"])
    r = subprocess.run([PY, SRC / "20_josm_file_facts.py", cfg_path], capture_output=True, text=True)
    if r.returncode:
        raise SystemExit(r.stderr)
    F = json.loads(pathlib.Path(p["facts_json"]).read_text(encoding="utf-8"))
    C.hash_files.append(p["facts_json"])
    S1 = section_facts(F)
    S2 = section_workflow(C)
    S3 = section_planted(C)
    S4 = section_contamination(C)
    S5 = section_synthetic(C)
    S6 = section_changes(C)
    summary = [("1 file facts", "see table", "ok"), ("2 workflow control table", "all ok" if C.ctl_ok else "see FAIL rows", "ok" if C.ctl_ok else "FAIL"),
               ("3 planted cases", "all as expected" if C.planted_ok else "findings", "ok" if C.planted_ok else "FINDING"),
               ("4 contamination", f"exit {C.contam['exit']}, osc written {C.contam['osc']}", "ok" if C.contam["exit"] == 3 and not C.contam["osc"] and C.contam["flagged_all"] else "FAIL"),
               ("5/6 safeguards and synthetic", f"{sum(1 for r in C.syn_results if r[-1] == 'pass')}/{len(C.syn_results)} pass", "ok" if C.syn_ok else "FAIL")]
    head = ["# Report 09: editing workflow on real JOSM files (task 04r)\n",
            "Produced by `src/24_real_workflow.py` (config `config/24_real_josm.yaml`, helpers `src/20_josm_file_facts.py`, `src/21_ownership_check.py`, `src/19_osm_submit.py`, `src/18_osm_conflicts.py`, `src/osm_io.py`). "
            "Inputs verified with `scripts/verify_inputs.sh` and the sha256 of both v1 packages; `data/raw/` and `legacy_v1/` untouched; nothing committed. Tools: osmium 1.16.0, netconvert 1.28.0, JOSM 19613 files.\n",
            "## Summary\n", md_table(["Item", "Result", "Status"], summary), ""]
    text = "\n".join(head + S1 + [""] + S2 + S3 + S4 + S5 + S6) + "\n"
    pathlib.Path(p["report"]).write_text(text, encoding="utf-8")
    C.hash_files.append(p["report"])
    lines = [f"{sha(f)}  {f if not str(f).startswith(str(work)) else pathlib.Path(f).name}" for f in C.hash_files]
    for k, v in sorted(C.hash_extra.items()):
        lines.append(f"{hashlib.sha256(v.encode()).hexdigest()}  <{k}>")
    pathlib.Path(p["rerun_hashes"]).write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.info("report %s written; hashes in %s", p["report"], p["rerun_hashes"])
    print("\n".join(lines))


if __name__ == "__main__":
    main()
