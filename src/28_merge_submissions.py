"""Task 04m: merge the newest cumulative submission of every zone into the full RING 1 base.

Steps: pick the newest submission per zone (date directory, then file time; older ones, and files archived by `intake_submission.sh --replace`, are "superseded"), verify its
.osc.meta.json (exit 4), run the ownership check (21) per submission, run the conflict check (18) and the cross-editor
check, `osmium merge-changes` (zone order), `apply-changes` onto the full base, `check-refs`, detect reverts against the
older submissions, optionally build the network before / after. Writes OUT/ring1_roads_merged.osm, OUT/merged.osc and
OUT/MERGE_REPORT.md (no timestamps, no absolute paths: the same inputs give the same files).

Usage: uv run python src/28_merge_submissions.py [--allow-violations] [--netconvert] [--config config/28_merge.yaml] SUBMISSIONS_DIR OUT_DIR
SUBMISSIONS_DIR/zone_<N>/<YYYYMMDD>/zone_<N>.osc (+ .osc.meta.json), as written by scripts/submit_edits.sh.
Exit codes: 0 ok (warnings are listed only), 1 a zone was refused (violation or conflict) and the rest was merged,
4 a zone was refused (meta / base / package mismatch) or the full base does not match, 64 usage / nothing to merge, 70 a step failed.
"""
import argparse
import collections
import hashlib
import importlib.util
import json
import logging
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

import yaml

SRC = pathlib.Path(__file__).resolve().parent
ROOT = SRC.parent
sys.path.insert(0, str(SRC))
import osm_io  # noqa: E402

log = logging.getLogger("merge")
DATE_RE = re.compile(r"^\d{8}$")
TYPE_ORDER = {"node": 0, "way": 1, "relation": 2}


def load(name):
    spec = importlib.util.spec_from_file_location(pathlib.Path(name).stem, SRC / name)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def run(cmd, **kw):
    log.info("$ %s", " ".join(str(c) for c in cmd))
    return subprocess.run([str(c) for c in cmd], capture_output=True, text=True, **kw)


def discover(sub_dir):
    """{zone: [entry, ...]} sorted oldest -> newest by (date directory, file time, path)."""
    out = {}
    for zdir in sorted(sub_dir.glob("zone_*")):
        m = re.fullmatch(r"zone_(\d+)", zdir.name)
        if not m or not zdir.is_dir():
            continue
        zone = int(m.group(1))
        for ddir in sorted(zdir.iterdir()):
            osc = ddir / f"zone_{zone}.osc"
            if ddir.is_dir() and DATE_RE.match(ddir.name) and osc.is_file():
                out.setdefault(zone, []).append({"zone": zone, "date": ddir.name, "osc": osc, "mtime": osc.stat().st_mtime_ns,
                                                 "rel": f"{zdir.name}/{ddir.name}/{osc.name}"})
    for zone in out:
        out[zone].sort(key=lambda e: (e["date"], e["mtime"], e["rel"]))
    return out


def discover_archived(sub_dir, zone):
    """Files replaced by intake_submission.sh --replace: zone_<N>/<date>/replaced/<created_utc>/zone_<N>.osc. Never merged."""
    out = []
    for osc in sorted((sub_dir / f"zone_{zone}").glob(f"[0-9]*/replaced/*/zone_{zone}.osc")):
        date, stamp = osc.parent.parent.parent.name, osc.parent.name
        if DATE_RE.match(date):
            out.append({"zone": zone, "date": date, "stamp": stamp, "osc": osc, "archived": True, "rel": f"zone_{zone}/{date}/replaced/{stamp}/{osc.name}"})
    return out


def counts(osc, pkg_objs):
    """{(op, type): n}; op = create (id not in the package) / modify / delete."""
    c = collections.Counter()
    for block in ET.parse(osc).getroot():
        for el in block:
            if el.tag in osm_io.TYPES:
                key = (el.tag, int(el.get("id")))
                op = "delete" if block.tag == "delete" else ("modify" if key in pkg_objs else "create")
                c[(op, el.tag)] += 1
    return c


def osc_objects(osc):
    """{(type, id): (block, canonical content or None for delete)}."""
    out = {}
    for block in ET.parse(osc).getroot():
        for el in block:
            if el.tag in osm_io.TYPES:
                out[(el.tag, int(el.get("id")))] = (block.tag, None if block.tag == "delete" else osm_io.canon(el))
    return out


def row_key(r):
    return (r["editor"], r["type"], r["id"], r["op"], r["category"], r["reason"])


def check_ownership(own_mod_path, editors, tmp, label):
    """Run 21_ownership_check.py for [(name, zone, osc, pkg)]; return (exit code, rows)."""
    js = pathlib.Path(tmp) / f"rows_{label}.json"
    cmd = [sys.executable, own_mod_path]
    for name, zone, osc, pkg in editors:
        cmd += ["--editor", name, str(zone), osc, pkg]
    cmd += ["--json", js]
    r = run(cmd, cwd=ROOT)
    if r.returncode > 2 or (r.returncode != 4 and not js.exists()):
        log.error("21_ownership_check.py failed (exit %d): %s", r.returncode, r.stderr[-800:])
        sys.exit(70)
    rows = json.loads(js.read_text(encoding="utf-8")) if js.exists() else []
    return r.returncode, rows


def checkref_lines(path):
    r = run(["osmium", "check-refs", "-r", "--show-ids", path])
    return sorted(set(l for l in (r.stdout + r.stderr).splitlines() if l.strip() and not l.startswith("There are")))


def ring1_bbox(poly_path, margin):
    xs, ys = [], []

    def walk(c):
        if c and isinstance(c[0], (int, float)):
            xs.append(c[0]); ys.append(c[1])
        else:
            for x in c:
                walk(x)
    gj = json.loads(pathlib.Path(poly_path).read_text(encoding="utf-8"))
    for f in gj.get("features", [gj]):
        walk(f["geometry"]["coordinates"])
    return f"{min(xs) - margin:.4f},{min(ys) - margin:.4f},{max(xs) + margin:.4f},{max(ys) + margin:.4f}"


def net_counts(net):
    edges = lights = progs = 0
    for _, el in ET.iterparse(net, events=("end",)):
        if el.tag == "edge" and el.get("function") != "internal":
            edges += 1
        elif el.tag == "junction" and el.get("type") == "traffic_light":
            lights += 1
        elif el.tag == "tlLogic":
            progs += 1
        if el.tag in ("edge", "junction", "tlLogic"):
            el.clear()
    return {"edges": edges, "traffic_light_junctions": lights, "tlLogic": progs}


def build_net(osm, net, bbox, options, base_sha=None):
    """netconvert; the network of the unchanged base is reused when its marker file matches."""
    marker = pathlib.Path(str(net) + ".key")
    key = json.dumps([base_sha, bbox, options]) if base_sha else None
    if key and net.exists() and marker.exists() and marker.read_text() == key:
        log.info("reusing %s", net)
        return net_counts(net)
    r = run(["netconvert", "--osm-files", osm, "-o", net, *options, bbox])
    pathlib.Path(str(net) + ".log").write_text(r.stdout + r.stderr, encoding="utf-8")
    if "Success." not in r.stdout:
        log.error("netconvert failed for %s, see %s.log", osm, net)
        sys.exit(70)
    if key:
        marker.write_text(key)
    return net_counts(net)


def main():
    t0 = time.time()
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("submissions_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--allow-violations", action="store_true", help="merge zones with ownership violations too (the report says so)")
    ap.add_argument("--netconvert", action="store_true", help="also build the network before and after")
    ap.add_argument("--config", default=str(ROOT / "config/28_merge.yaml"))
    a = ap.parse_args()
    cfg = yaml.safe_load(open(a.config, encoding="utf-8"))
    logpath = ROOT / cfg["log"]
    logpath.parent.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(logpath, encoding="utf-8"), logging.StreamHandler(sys.stdout)])
    sub_dir, out = pathlib.Path(a.submissions_dir).resolve(), pathlib.Path(a.out_dir).resolve()
    if not sub_dir.is_dir():
        log.error("submissions directory not found: %s", sub_dir)
        sys.exit(64)
    found = discover(sub_dir)
    if not found:
        log.error("no submissions (zone_<N>/<YYYYMMDD>/zone_<N>.osc) in %s", sub_dir)
        sys.exit(64)
    out.mkdir(parents=True, exist_ok=True)
    zones_dir = ROOT / cfg["zones_dir"]
    own_script = SRC / "21_ownership_check.py"
    own = load("21_ownership_check.py")
    confl = load("18_osm_conflicts.py")
    full_base = ROOT / cfg["full_base"]
    tmpdir = tempfile.TemporaryDirectory(prefix="merge_")
    tmp = tmpdir.name

    subs = {}                                       # zone -> dict
    meta_refused, refused_viol, refused_conf = {}, {}, {}
    for zone in sorted(found):
        ents = found[zone]
        new = ents[-1]
        older = sorted(ents[:-1] + discover_archived(sub_dir, zone), key=lambda e: (e["date"], e.get("stamp", "~"), e["rel"]))   # archived files of a day come before its live file
        pkg, side = zones_dir / f"zone_{zone}" / f"zone_{zone}.osm", zones_dir / f"zone_{zone}" / f"zone_{zone}.json"
        s = {"zone": zone, "file": new, "superseded": older, "pkg": pkg, "side": side, "rows": [], "reasons": []}
        subs[zone] = s
        # 1. meta / package check
        metap = pathlib.Path(str(new["osc"]) + ".meta.json")
        try:
            side_j = json.loads(side.read_text(encoding="utf-8"))
            s["sidecar"] = side_j
        except (OSError, ValueError) as e:
            s["reasons"].append(f"package sidecar {side.relative_to(ROOT)} unreadable: {e}")
            side_j = {}
        if not metap.is_file():
            s["reasons"].append(f"{new['rel']}.meta.json missing")
        else:
            try:
                meta = json.loads(metap.read_text(encoding="utf-8"))
            except ValueError as e:
                meta = {}
                s["reasons"].append(f"{new['rel']}.meta.json unreadable: {e}")
            # created_utc is informational: the hash is taken over the meta as 19_osm_submit.py wrote it (without that field)
            s["meta_sha"] = hashlib.sha256(json.dumps({k: v for k, v in meta.items() if k != "created_utc"}, indent=1, sort_keys=True).encode("utf-8")).hexdigest()
            want = side_j.get("sha256_extract")
            if meta and meta.get("base_sha256") != want:
                s["reasons"].append(f"base sha256 in meta ({str(meta.get('base_sha256'))[:12]}...) differs from the package sidecar ({str(want)[:12]}...): derived against another base")
            if meta and meta.get("editor_index") != zone:
                s["reasons"].append(f"editor index in meta is {meta.get('editor_index')}, directory says zone {zone}")
        if side_j and pkg.is_file() and sha256_file(pkg) != side_j.get("sha256_extract"):
            s["reasons"].append(f"package {pkg.relative_to(ROOT)} differs from its sidecar sha256")
        if not pkg.is_file():
            s["reasons"].append(f"package {pkg.relative_to(ROOT)} not found")
        if s["reasons"]:
            meta_refused[zone] = s["reasons"]
            log.error("zone %d refused (exit 4): %s", zone, "; ".join(s["reasons"]))
            continue
        s["pkg_objs"] = osm_io.read_osm(pkg)["objs"]
        s["counts"] = counts(new["osc"], s["pkg_objs"])
        # 2. ownership check per submission
        rc, rows = check_ownership(str(own_script), [(f"zone_{zone}", zone, str(new["osc"]), str(pkg))], tmp, f"z{zone}")
        if rc == 4:
            meta_refused[zone] = ["ownership check: .osc derived against another base (exit 4)"]
            continue
        s["rows"] = rows
        s["viol"] = [r for r in rows if r["severity"] == "violation"]
        s["warn"] = [r for r in rows if r["severity"] == "warning"]
        if s["viol"] and not a.allow_violations:
            refused_viol[zone] = s["viol"]
            log.error("zone %d refused: %d ownership violation(s)", zone, len(s["viol"]))

    # the full base must be the base of every package
    base_sha = sha256_file(full_base)
    bad_base = sorted(z for z, s in subs.items() if "sidecar" in s and s["sidecar"].get("sha256_base_osm") != base_sha)
    if bad_base:
        log.error("full base %s (sha256 %s) is not the base of the package(s) of zone(s) %s", full_base, base_sha, bad_base)
        for z in bad_base:
            meta_refused.setdefault(z, []).append(f"full base sha256 {base_sha[:12]}... differs from sha256_base_osm in the package sidecar")

    # 3. conflicts between the remaining submissions
    eligible = sorted(z for z in subs if z not in meta_refused and z not in refused_viol)
    conflicts_txt, neg_txt, cross_rows = [], [], []
    if len(eligible) >= 2:
        objs, neg = confl.conflicts({f"zone_{z}": str(subs[z]["file"]["osc"]) for z in eligible})
        for (t, i), eds in sorted(objs.items(), key=lambda kv: (TYPE_ORDER[kv[0][0]], kv[0][1])):
            conflicts_txt.append(f"{t} {i} changed by {', '.join(eds)}")
        for (t, i), eds in sorted(neg.items(), key=lambda kv: (TYPE_ORDER[kv[0][0]], kv[0][1])):
            neg_txt.append(f"{t} {i} (negative id) used by {', '.join(eds)}")
        for eds in [e for v in list(objs.values()) + list(neg.values()) for e in v]:
            refused_conf.setdefault(int(eds.split("_")[1]), []).append("conflict with another zone")
        eligible = [z for z in eligible if z not in refused_conf]
    # 4. cross-editor semantic check (all editors together): rows that the single runs did not give
    if len(eligible) >= 2:
        rc, rows = check_ownership(str(own_script), [(f"zone_{z}", z, str(subs[z]["file"]["osc"]), str(subs[z]["pkg"])) for z in eligible], tmp, "all")
        single = {row_key(r) for z in eligible for r in subs[z]["rows"]}
        cross_rows = [r for r in rows if row_key(r) not in single]
        for r in cross_rows:
            if r["severity"] == "violation" and not a.allow_violations:
                z = int(r["editor"].split("_")[1])
                refused_viol.setdefault(z, []).append(r)
        eligible = [z for z in eligible if z not in refused_viol]
    merge_zones = eligible

    # 5. merge, apply, check-refs
    merged_osc, merged_osm = out / "merged.osc", out / "ring1_roads_merged.osm"
    res = {"merged": merge_zones}
    if merge_zones:
        r = run(["osmium", "merge-changes", "--overwrite", "-o", merged_osc, *[subs[z]["file"]["osc"] for z in merge_zones]])
        if r.returncode:
            log.error("merge-changes failed: %s", r.stderr[-500:]); sys.exit(70)
        r = run(["osmium", "apply-changes", "--overwrite", full_base, merged_osc, "-o", merged_osm])
        if r.returncode:
            log.error("apply-changes failed: %s", r.stderr[-500:]); sys.exit(70)
        base_refs, merged_refs = checkref_lines(full_base), checkref_lines(merged_osm)
        res["new_missing"] = sorted(set(merged_refs) - set(base_refs))
        res["base_missing_n"] = len(base_refs)
        # merged file differs from the base exactly in the objects of merged.osc
        bo, mo = osm_io.read_osm(full_base)["objs"], osm_io.read_osm(merged_osm)["objs"]
        diff = {k for k in set(bo) | set(mo) if k not in bo or k not in mo or osm_io.canon(bo[k]) != osm_io.canon(mo[k]) or bo[k].get("version") != mo[k].get("version")}
        expected = set(osc_objects(merged_osc))
        res["diff_n"], res["expected_n"] = len(diff), len(expected)
        res["diff_extra"] = sorted(diff - expected)[:20]
        res["diff_missing"] = sorted(expected - diff)[:20]
        del bo, mo
    elif merged_osm.exists():
        merged_osm.unlink(); merged_osc.unlink(missing_ok=True)

    # 6. reverts: objects changed in an older submission, absent from the newest one
    reverts = {}
    for z, s in subs.items():
        if z in meta_refused or not s["superseded"]:
            continue
        newest = osc_objects(s["file"]["osc"])
        for old in s["superseded"]:
            for key, (blk, _) in sorted(osc_objects(old["osc"]).items(), key=lambda kv: (TYPE_ORDER[kv[0][0]], kv[0][1])):
                if key not in newest:
                    reverts.setdefault(z, []).append((key, blk, old["rel"]))

    # 7. network
    nets = None
    if a.netconvert and merge_zones:
        bbox = ring1_bbox(ROOT / cfg["netconvert"]["ring1_polygon"], cfg["netconvert"]["margin_deg"])
        nd = out / "netconvert"
        nd.mkdir(exist_ok=True)
        opts = cfg["netconvert"]["options"]
        nets = {"bbox": bbox, "options": opts,
                "before": build_net(full_base, nd / "base.net.xml", bbox, opts, base_sha),
                "after": build_net(merged_osm, nd / "merged.net.xml", bbox, opts)}

    # 8. report
    refused_any_4 = bool(meta_refused)
    refused_1 = {z for z in list(refused_viol) + list(refused_conf) if z not in meta_refused}
    L = ["# Merge report", "",
         f"Zones merged: {', '.join(str(z) for z in merge_zones) or 'none'}. "
         f"Zones refused: {', '.join(str(z) for z in sorted(set(meta_refused) | refused_1)) or 'none'}. "
         f"Mode: {'`--allow-violations`' if a.allow_violations else 'default (violations refuse the zone)'}."]
    if a.allow_violations and any(subs[z].get("viol") for z in merge_zones):
        L += ["", "**WARNING: merged with `--allow-violations`; zones " + ", ".join(str(z) for z in merge_zones if subs[z].get("viol")) + " contain ownership violations (section 2).**"]
    L += ["", "## 1. Submissions used", "",
          "| zone | file | date | modified | created | deleted | status |", "|---|---|---|---|---|---|---|"]
    for z in sorted(subs):
        s = subs[z]
        status = ("REFUSED (meta/base)" if z in meta_refused else "REFUSED (violations)" if z in refused_viol else
                  "REFUSED (conflict)" if z in refused_conf else "merged" + (" WITH VIOLATIONS" if s.get("viol") else ""))
        if z in meta_refused:
            L.append(f"| {z} | `{s['file']['rel']}` | {s['file']['date']} | - | - | - | {status} |")
            continue
        c = s["counts"]
        cell = lambda op: ", ".join(f"{c[(op, t)]} {t}" for t in osm_io.TYPES if c[(op, t)]) or "0"
        L.append(f"| {z} | `{s['file']['rel']}` | {s['file']['date']} | {cell('modify')} | {cell('create')} | {cell('delete')} | {status} |")
    L += ["", "Newest cumulative submission per zone (date directory, then file time).", "", "### Superseded (older, not merged)", ""]
    sup = [(z, e) for z in sorted(subs) for e in subs[z]["superseded"]]
    L += [f"- zone {z}: `{e['rel']}`" + (" (replaced the same day, archived)" if e.get("archived") else "") for z, e in sup] or ["none"]
    L += ["", "### Refused", ""]
    for z in sorted(meta_refused):
        L += [f"- zone {z} (exit 4): " + "; ".join(meta_refused[z])]
    for z in sorted(refused_viol):
        L += [f"- zone {z} (ownership violations): {len(refused_viol[z])}"]
    for z in sorted(refused_conf):
        L += [f"- zone {z} (conflict with another zone)"]
    if not (meta_refused or refused_viol or refused_conf):
        L += ["none"]

    def table(rows):
        t = ["| zone | object | op | detail | category | reason |", "|---|---|---|---|---|---|"]
        for r in sorted(rows, key=lambda r: (r["editor"], TYPE_ORDER[r["type"]], r["id"], r["category"])):
            t.append(f"| {r['editor'].split('_')[1]} | {r['type']} {r['id']} | {r['op']} | {r['detail']} | {r['category']} | {r['reason'].replace('|', '/')} |")
        return t
    L += ["", "## 2. Ownership violations", ""]
    viol = [r for z in sorted(subs) for r in subs[z].get("viol", [])] + [r for r in cross_rows if r["severity"] == "violation"]
    L += table(viol) if viol else ["none"]
    L += ["", "## 3. Warnings (per submission)", ""]
    warn = [r for z in sorted(subs) for r in subs[z].get("warn", [])]
    L += table(warn) if warn else ["none"]
    L += ["", "## 4. Conflicts and cross-zone warnings", "", "Conflicts (`18_osm_conflicts.py`, among submissions that passed the checks before it):", ""]
    L += [f"- {x}" for x in conflicts_txt + neg_txt] or ["none"]
    L += ["", "Cross-zone warnings (ownership check of all merged zones together, rows the single runs did not give):", ""]
    cw = [r for r in cross_rows if r["severity"] == "warning"]
    L += table(cw) if cw else ["none"]
    L += ["", "## 5. Possible reverts (changed in an older submission, absent from the newest one)", ""]
    if reverts:
        L += ["The object is back in its base state in the newest file (for example through Undo). Ask the rater whether this was intended.", "",
              "| zone | object | was | older file |", "|---|---|---|---|"]
        for z in sorted(reverts):
            L += [f"| {z} | {k[0]} {k[1]} | {blk} | `{rel}` |" for k, blk, rel in reverts[z]]
    else:
        L += ["none"]
    L += ["", "## 6. Result", ""]
    if merge_zones:
        L += ["| check | result |", "|---|---|",
              f"| `merge-changes` order | zones {', '.join(map(str, merge_zones))} |",
              f"| objects in `merged.osc` | {res['expected_n']} |",
              f"| objects of the merged file that differ from the base | {res['diff_n']} ({'equal to merged.osc' if not res['diff_extra'] and not res['diff_missing'] else 'MISMATCH extra ' + str(res['diff_extra']) + ' missing ' + str(res['diff_missing'])}) |",
              f"| `check-refs -r`: missing references in the base | {res['base_missing_n']} lines |",
              f"| `check-refs -r`: new missing references | {len(res['new_missing'])}" + (": " + "; ".join(res["new_missing"]) if res["new_missing"] else "") + " |"]
    else:
        L += ["Nothing merged."]
    if nets:
        b, n = nets["before"], nets["after"]
        L += ["", f"### netconvert (`{' '.join(nets['options'])} {nets['bbox']}`, defaults otherwise)", "",
              "| | before (base) | after (merged) |", "|---|---|---|",
              f"| edges (without internal) | {b['edges']} | {n['edges']} |",
              f"| junctions of type traffic_light | {b['traffic_light_junctions']} | {n['traffic_light_junctions']} |",
              f"| tlLogic programs | {b['tlLogic']} | {n['tlLogic']} |"]
    L += ["", "## 7. sha256", "", "| file | sha256 |", "|---|---|"]
    L.append(f"| full base `{cfg['full_base']}` | `{base_sha}` |")
    for z in sorted(subs):
        s = subs[z]
        for e in s["superseded"] + [s["file"]]:
            L.append(f"| `{e['rel']}`{' (superseded)' if e in s['superseded'] else ''} | `{sha256_file(e['osc'])}` |")
        if "meta_sha" in s:
            L.append(f"| `{s['file']['rel']}.meta.json` | `{s['meta_sha']}` |")
        if "sidecar" in s:
            L.append(f"| package `zone_{z}.osm` | `{s['sidecar'].get('sha256_extract')}` |")
    if merge_zones:
        L += [f"| `merged.osc` | `{sha256_file(merged_osc)}` |", f"| `ring1_roads_merged.osm` | `{sha256_file(merged_osm)}` |"]
    (out / "MERGE_REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    # control table (stdout)
    rc = 4 if refused_any_4 else 1 if refused_1 else 0
    print("\ncontrol table")
    print(f"  zones merged: {merge_zones}   refused (exit 4): {sorted(meta_refused)}   refused (violations/conflicts): {sorted(refused_1)}")
    if merge_zones:
        print(f"  merged.osc objects {res['expected_n']}, differing from base {res['diff_n']}, new missing refs {len(res['new_missing'])}")
        ok = not res["diff_extra"] and not res["diff_missing"] and not res["new_missing"] and res["diff_n"] == res["expected_n"]
        if not ok:
            log.error("merged file does not match merged.osc or has new missing references: see the report")
            rc = rc or 70
    print(f"  report: {out / 'MERGE_REPORT.md'}   exit {rc}   runtime {time.time() - t0:.1f} s")
    sys.exit(rc)


if __name__ == "__main__":
    main()
