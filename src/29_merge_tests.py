"""Task 04m: tests of 28_merge_submissions.py with the real JOSM files editedB (zone 4) and editedC (zone 3).

Scenarios (a) default run, (b) --allow-violations, (c) clean variants, (d) two sessions and a revert, (e) conflict on a whitelisted node,
plus tampered meta files (exit 4) and a repeat run (identical hashes). Writes reports/11_merge.md.

Usage: uv run python src/29_merge_tests.py [--config config/29_merge_tests.yaml]
"""
import argparse
import copy
import datetime
import hashlib
import json
import logging
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

import yaml

SRC = pathlib.Path(__file__).resolve().parent
ROOT = SRC.parent
sys.path.insert(0, str(SRC))
import osm_io  # noqa: E402

log = logging.getLogger("merge_tests")
T = []          # (test, expected, actual, status)


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def row(test, expected, actual, ok):
    T.append((test, expected, actual, "ok" if ok else "FAIL"))
    log.info("%-4s %s | expected %s | actual %s", "ok" if ok else "FAIL", test, expected, actual)


def sh(cmd, env=None):
    r = subprocess.run([str(c) for c in cmd], cwd=ROOT, capture_output=True, text=True, env={**os.environ, **(env or {})})
    return r


def make_variant(edited, pkg, out, revert=(), drop=(), mutate=None):
    """Copy of a JOSM file with the listed objects put back to the package state (revert) or removed (drop)."""
    ed, pk = osm_io.read_osm(edited), osm_io.read_osm(pkg)["objs"]
    els = []
    for key, el in ed["objs"].items():
        if key in drop:
            continue
        if key in revert:
            el = copy.deepcopy(pk[key])
        if mutate:
            new = mutate(key, el)
            el = el if new is None else new
        els.append(el)
    osm_io.write_josm(out, els)


def submit(zone, edited, subdir, date):
    """scripts/submit_edits.sh into subdir/zone_N/<date>/; returns the exit code."""
    r = sh(["scripts/submit_edits.sh", zone, edited], env={"SUBMISSIONS_DIR": str(subdir)})
    today = next((subdir / f"zone_{zone}").iterdir()) if (subdir / f"zone_{zone}").exists() else None
    if today and today.name != date:
        tgt = subdir / f"zone_{zone}" / date
        shutil.rmtree(tgt, ignore_errors=True)
        today.rename(tgt)
    return r.returncode


def merge(subdir, out, *flags):
    shutil.rmtree(out, ignore_errors=True)
    t0 = time.time()
    r = sh(["scripts/merge_submissions.sh", *flags, subdir, out])
    rep = out / "MERGE_REPORT.md"
    return r.returncode, (rep.read_text(encoding="utf-8") if rep.exists() else ""), time.time() - t0


def section(rep, n):
    m = re.search(rf"## {n}\. .*?\n(.*?)(?=\n## |\Z)", rep, re.S)
    return m.group(1) if m else ""


def table_objects(text):
    """{(zone, 'type id')} from the rows of a report table."""
    return {(m.group(1), m.group(2)) for m in re.finditer(r"^\| (\d+) \| ((?:node|way|relation) -?\d+) \|", text, re.M)}


def expected_vs_actual(base_path, merged_path, variants):
    """Independent check: the merged file differs from the base exactly in the edited objects, with the edited content."""
    base, merged = osm_io.read_osm(base_path)["objs"], osm_io.read_osm(merged_path)["objs"]
    expect, problems = set(), []
    for zone, pkgp, edp in variants:
        pk, ed = osm_io.read_osm(pkgp)["objs"], osm_io.read_osm(edp)["objs"]
        shift = (zone + 1) * 10 ** 12

        def mp(i):
            return shift - i if i < 0 else i
        for (t, i), el in ed.items():
            if el.get("action") == "delete":
                expect.add((t, i))
                if (t, i) in merged:
                    problems.append(f"deleted {t} {i} still present")
                continue
            e2 = copy.deepcopy(el)                  # renumber negative ids and refs (also in existing relations, e.g. 35954)
            e2.set("id", str(mp(i)))
            for c in e2:
                if c.tag in ("nd", "member") and int(c.get("ref")) < 0:
                    c.set("ref", str(mp(int(c.get("ref")))))
            key = (t, mp(i))
            if i < 0:
                expect.add(key)
                if key not in merged or osm_io.canon(merged[key]) != osm_io.canon(e2):
                    problems.append(f"new {t} {i} -> {key[1]} differs")
            elif osm_io.canon(pk[key]) != osm_io.canon(e2):
                expect.add(key)
                if key not in merged or osm_io.canon(merged[key]) != osm_io.canon(e2):
                    problems.append(f"{t} {i} differs from the edited file")
    diff = {k for k in set(base) | set(merged) if k not in base or k not in merged or osm_io.canon(base[k]) != osm_io.canon(merged[k]) or base[k].get("version") != merged[k].get("version")}
    return len(expect), len(diff), sorted(diff ^ expect)[:10], problems[:10]


def refs(path):
    r = sh(["osmium", "check-refs", "-r", "--show-ids", path])
    return sorted(l for l in (r.stdout + r.stderr).splitlines() if l.strip() and not l.startswith("There are"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "config/29_merge_tests.yaml"))
    cfg = yaml.safe_load(open(ap.parse_args().config, encoding="utf-8"))
    (ROOT / cfg["log"]).parent.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s",
                        handlers=[logging.FileHandler(ROOT / cfg["log"], encoding="utf-8"), logging.StreamHandler()])
    W = ROOT / cfg["workdir"]
    shutil.rmtree(W, ignore_errors=True)
    W.mkdir(parents=True)
    zd = ROOT / cfg["zones_dir"]
    pkg = {z: zd / f"zone_{z}" / f"zone_{z}.osm" for z in cfg["zones"]}
    base = ROOT / "data/interim/ring1_roads.osm"
    notes, details = [], []
    for z, c in cfg["zones"].items():
        h = sha(pkg[z])
        row(f"input: package zone_{z}.osm sha256", c["package_sha256_prefix"] + "...", h[:8] + "...", h.startswith(c["package_sha256_prefix"]))
    d1, d2 = cfg["dates"]["first"], cfg["dates"]["second"]

    # (a) default run on the raw files
    S = W / "sub_raw"
    rcs = {z: submit(z, ROOT / c["edited"], S, d2) for z, c in cfg["zones"].items()}
    row("submit_edits.sh editedB / editedC", "exit 1 / 1 (violations written)", f"{rcs[4]} / {rcs[3]}", rcs[4] == 1 and rcs[3] == 1)
    rc, rep, secs = merge(S, W / "out_a")
    got = table_objects(section(rep, 2))
    want = {(str(z), f"{t} {i}") for z, d in cfg["planted"].items() for t, i in d.values()}
    row("(a) default merge of editedB + editedC", "exit 1, both zones refused with exactly B6, C9, C10b", f"exit {rc}, violations {sorted(got)}", rc == 1 and got == want and "Zones merged: none" in rep)
    row("(a) nothing merged", "no merged.osm / merged.osc", "none written" if not (W / "out_a/ring1_roads_merged.osm").exists() else "written", not (W / "out_a/ring1_roads_merged.osm").exists())

    # (b) --allow-violations
    rc, rep, secs_b = merge(S, W / "out_b", "--allow-violations")
    variants = [(z, pkg[z], ROOT / c["edited"]) for z, c in cfg["zones"].items()]
    n_exp, n_diff, sym, prob = expected_vs_actual(base, W / "out_b/ring1_roads_merged.osm", variants)
    row("(b) --allow-violations", "exit 0, zones 3 and 4 merged, report says so", f"exit {rc}", rc == 0 and "Zones merged: 3, 4" in rep and "WARNING: merged with `--allow-violations`" in rep)
    row("(b) merged differs from base exactly in the edited objects of both files", "27 expected = 27 differing, 0 mismatches", f"{n_exp} expected, {n_diff} differing, mismatches {sym}, content problems {prob}", n_exp == n_diff == 27 and not sym and not prob)
    rb, rm = refs(base), refs(W / "out_b/ring1_roads_merged.osm")
    row("(b) osmium check-refs", "no new missing references", f"{len(set(rm) - set(rb))} new", not (set(rm) - set(rb)))

    # (c) clean variants
    E = W / "edited"
    E.mkdir()
    clean = {}
    for z, c in cfg["zones"].items():
        rev = {(v[0], v[1]) for v in cfg["planted"][z].values()}
        clean[z] = E / f"zone_{z}_clean.osm"
        make_variant(ROOT / c["edited"], pkg[z], clean[z], revert=rev)
        details.append(f"- zone {z}: `{pathlib.Path(c['edited']).name}` without " + ", ".join(f"{k} ({v[0]} {v[1]}, put back to the package state)" for k, v in cfg["planted"][z].items()))
    S = W / "sub_clean"
    rcs = {z: submit(z, clean[z], S, d2) for z in clean}
    row("submit_edits.sh clean variants", "exit 0 / 0", f"{rcs[4]} / {rcs[3]}", rcs[4] == 0 and rcs[3] == 0)
    rc, rep, secs_c = merge(S, W / "out_c", "--netconvert")
    n_exp, n_diff, sym, prob = expected_vs_actual(base, W / "out_c/ring1_roads_merged.osm", [(z, pkg[z], clean[z]) for z in clean])
    row("(c) clean variants, no --allow-violations", "exit 0, zones 3 and 4 merged", f"exit {rc}", rc == 0 and "Zones merged: 3, 4" in rep and "Zones refused: none" in rep)
    row("(c) merged differs from base exactly in the edited objects", "24 expected = 24 differing (27 minus B6, C9, C10b), 0 mismatches", f"{n_exp} expected, {n_diff} differing, mismatches {sym}, content problems {prob}", n_exp == n_diff == 24 and not sym and not prob)
    nets = re.findall(r"\| edges \(without internal\) \| (\d+) \| (\d+) \|", rep)
    row("(c) netconvert before / after", "success; edges after > before (two new ways, one deleted way pair ...)", f"edges {nets[0][0]} -> {nets[0][1]}" if nets else "missing", bool(nets))
    rc2, rep2, _ = merge(S, W / "out_c2", "--netconvert")
    same = [sha(W / f"out_c/{f}") == sha(W / f"out_c2/{f}") for f in ("MERGE_REPORT.md", "merged.osc", "ring1_roads_merged.osm")]
    row("(c) second run: MERGE_REPORT.md / merged.osc / merged.osm identical", "same sha256", f"{same}; report {sha(W / 'out_c/MERGE_REPORT.md')[:16]}, osc {sha(W / 'out_c/merged.osc')[:16]}", all(same) and rc2 == 0)
    rc3, rep3, secs_nonet = merge(S, W / "out_c3")
    row("(c) same inputs without --netconvert: merged.osc identical", "same sha256", sha(W / "out_c/merged.osc")[:16], sha(W / "out_c/merged.osc") == sha(W / "out_c3/merged.osc"))

    prev = cfg["previous_04m"]
    row("(c) hashes equal the first 04m run (before created_utc existed)", "MERGE_REPORT.md and merged.osc identical to the 04m results",
        f"report {sha(W / 'out_c/MERGE_REPORT.md')[:12]}, osc {sha(W / 'out_c/merged.osc')[:12]}",
        sha(W / "out_c/MERGE_REPORT.md") == prev["merge_report_sha256_c"] and sha(W / "out_c/merged.osc") == prev["merged_osc_sha256_c"])
    metas = [json.loads(p.read_text()) for p in S.glob("zone_*/*/*.meta.json")]
    row("submit_edits.sh writes created_utc", "2 meta files with created_utc", f"{sum('created_utc' in m for m in metas)} of {len(metas)}", len(metas) == 2 and all("created_utc" in m for m in metas))
    S_ts = W / "sub_ts"
    shutil.copytree(S, S_ts)
    for k, mp in enumerate(sorted(S_ts.glob("zone_*/*/*.meta.json"))):
        m = json.loads(mp.read_text())
        m["created_utc"] = f"2031-0{k + 1}-15T01:02:03Z"
        mp.write_text(json.dumps(m, indent=1, sort_keys=True))
    rc4, rep4, _ = merge(S_ts, W / "out_ts")
    row("(c) other created_utc in the meta files: merge ignores it", "MERGE_REPORT.md, merged.osc, merged.osm identical",
        f"{[sha(W / f'out_ts/{f}') == sha(W / f'out_c3/{f}') for f in ('MERGE_REPORT.md', 'merged.osc', 'ring1_roads_merged.osm')]}",
        rc4 == 0 and all(sha(W / f"out_ts/{f}") == sha(W / f"out_c3/{f}") for f in ("MERGE_REPORT.md", "merged.osc", "ring1_roads_merged.osm")))

    # (d) two sessions of zone 3
    after = {tuple(o) for v in cfg["after_c5"].values() for o in v}
    drop = {(t, i) for t, i in after if i < 0}
    first = E / "zone_3_c1_c5.osm"
    make_variant(clean[3], pkg[3], first, revert={k for k in after if k[1] > 0}, drop=drop)
    details.append("- zone 3 first session (C1-C5 only): clean variant without " + ", ".join(f"{k}: {v}" for k, v in cfg["after_c5"].items()))
    S = W / "sub_two"
    submit(4, clean[4], S, d2)
    submit(3, first, S, d1)
    submit(3, clean[3], S, d2)
    os.utime(S / f"zone_3/{d1}/zone_3.osc", (1, 1))
    rc, rep, _ = merge(S, W / "out_d1")
    sup = section(rep, 1)
    row("(d1) two sessions of zone 3", "exit 0; only the second used, the first superseded", f"exit {rc}; superseded line: {re.findall(r'- zone 3: `[^`]+`', sup)}",
        rc == 0 and f"- zone 3: `zone_3/{d1}/zone_3.osc`" in sup and f"| 3 | `zone_3/{d2}/zone_3.osc`" in rep)
    rev_sec = section(rep, 5)
    row("(d1) revert list of the cumulative pair", "none", rev_sec.strip(), rev_sec.strip() == "none")
    n_exp, n_diff, sym, prob = expected_vs_actual(base, W / "out_d1/ring1_roads_merged.osm", [(4, pkg[4], clean[4]), (3, pkg[3], clean[3])])
    row("(d1) merged = same result as (c)", "24 = 24, identical merged.osc to (c)", f"{n_exp} = {n_diff}; osc identical {sha(W / 'out_d1/merged.osc') == sha(W / 'out_c/merged.osc')}", n_exp == n_diff == 24 and not sym and not prob and sha(W / "out_d1/merged.osc") == sha(W / "out_c/merged.osc"))
    nc5 = E / "zone_3_without_c5.osm"
    make_variant(clean[3], pkg[3], nc5, revert={tuple(cfg["c5"])})
    details.append(f"- zone 3 second session with C5 reverted: clean variant without C5 ({cfg['c5'][0]} {cfg['c5'][1]} put back to the package state)")
    S = W / "sub_rev"
    submit(4, clean[4], S, d2)
    submit(3, clean[3], S, d1)       # older: everything, with C5
    submit(3, nc5, S, d2)            # newer: C5 lost (as in the notes)
    os.utime(S / f"zone_3/{d1}/zone_3.osc", (1, 1))
    rc, rep, _ = merge(S, W / "out_d2")
    rev_sec = section(rep, 5)
    names = re.findall(r"^\| 3 \| ((?:node|way|relation) -?\d+) \|", rev_sec, re.M)
    row("(d2) revert of C5", "exit 0; revert list names exactly relation 3262876", f"exit {rc}; revert list {names}", rc == 0 and names == ["relation 3262876"])
    nrev = re.search(r"merged\.osc \| (\d+)", rep)

    # (e) two zones edit the same object
    def mover(z):
        dx, dy = cfg["shared_move_deg"][z] if z in cfg["shared_move_deg"] else cfg["shared_move_deg"][str(z)]

        def f(key, el):
            if key == ("node", cfg["shared_node"]):
                el = copy.deepcopy(el)
                el.set("lat", f"{float(el.get('lat')) + dx:.7f}")
                el.set("lon", f"{float(el.get('lon')) + dy:.7f}")
                el.set("action", "modify")
                return el
        return f
    S = W / "sub_conf"
    for z in (3, 4):
        k = ("node", cfg["shared_node"])
        has = k in osm_io.read_osm(pkg[z])["objs"]
        row(f"(e) shared node {cfg['shared_node']} is in package zone_{z}", "yes", str(has), has)
        v = E / f"zone_{z}_conflict.osm"
        make_variant(clean[z], pkg[z], v, mutate=mover(z))
        submit(z, v, S, d2)
    rc, rep, _ = merge(S, W / "out_e")
    cs = section(rep, 4)
    row("(e) same whitelisted node moved by zones 3 and 4", "exit 1; conflict node reported; both zones refused; nothing merged",
        f"exit {rc}; conflict lines {re.findall(r'- node .*', cs)}; merged {'none' if 'Zones merged: none' in rep else 'some'}",
        rc == 1 and f"node {cfg['shared_node']} changed by zone_3, zone_4" in cs and "Zones merged: none" in rep)

    # (g) cross-zone warning: zone 3 moves a node of zone 4 (violation, merged only with --allow-violations)
    ck = ("node", cfg["cross_node"])
    row(f"(g) node {ck[1]} is in package zone_3", "yes", str(ck in osm_io.read_osm(pkg[3])["objs"]), ck in osm_io.read_osm(pkg[3])["objs"])

    def cross_move(key, el):
        if key == ck:
            el = copy.deepcopy(el)
            el.set("lat", f"{float(el.get('lat')) + cfg['cross_move_deg'][0]:.7f}")
            el.set("lon", f"{float(el.get('lon')) + cfg['cross_move_deg'][1]:.7f}")
            el.set("action", "modify")
            return el
    S = W / "sub_cross"
    cv = E / "zone_3_cross.osm"
    make_variant(clean[3], pkg[3], cv, mutate=cross_move)
    submit(4, clean[4], S, d2)
    submit(3, cv, S, d2)
    rc, rep, _ = merge(S, W / "out_g1")
    row("(g1) default run", "exit 1; zone 3 refused (node of zone 4), zone 4 merged", f"exit {rc}", rc == 1 and "Zones merged: 4." in rep and "Zones refused: 3." in rep)
    rc, rep, _ = merge(S, W / "out_g2", "--allow-violations")
    cw = section(rep, 4).split("Cross-zone warnings")[1]
    row("(g2) --allow-violations", "exit 0; cross-zone warning for node 165109460 (used by way 16313072 changed by zone 4); relation_member warning in the zone's own list",
        f"exit {rc}; cross: {sorted(set(re.findall(r'cross_editor_way', cw)))}, way 16313072 named: {'way 16313072' in cw}; own list: {sorted(set(re.findall(r'relation_member', section(rep, 3))))}",
        rc == 0 and "cross_editor_way" in cw and "way 16313072" in cw and "relation_member" in section(rep, 3))

    # (h) intake
    def intake(zone, src, sub, *args):
        r = sh(["scripts/intake_submission.sh", zone, src, *args], env={"SUBMISSIONS_DIR": str(sub)})
        return r.returncode, (r.stdout + r.stderr).strip().splitlines()[-1:] or [""]

    def stage(name, zone, srcdir, rename_to=None, meta_edit=None, osc_text=None, xlsx=False, day=None):
        d = W / "intake_src" / name
        shutil.rmtree(d, ignore_errors=True)
        d.mkdir(parents=True)
        z2 = rename_to or zone
        o = sorted(srcdir.glob(f"zone_{zone}/{day or '*'}/zone_{zone}.osc"))[-1]
        shutil.copyfile(o, d / f"zone_{z2}.osc")
        m = json.loads(pathlib.Path(str(o) + ".meta.json").read_text())
        if meta_edit:
            meta_edit(m)
        (d / f"zone_{z2}.osc.meta.json").write_text(json.dumps(m, indent=1, sort_keys=True))
        if osc_text is not None:
            (d / f"zone_{z2}.osc").write_text(osc_text)
        if xlsx:
            (d / "records_zone.xlsx").write_bytes(b"PK dummy record sheet")
        return d
    I = W / "sub_intake"
    c3 = json.loads(next((W / "sub_clean/zone_3").glob("*/zone_3.osc.meta.json")).read_text())["created_utc"]
    day3 = c3[:10].replace("-", "")
    rc, msg = intake(3, stage("z3", 3, W / "sub_clean"), I)
    ok_place = rc == 0 and (I / f"zone_3/{day3}/zone_3.osc").is_file() and (I / f"zone_3/{day3}/zone_3.osc.meta.json").is_file()
    row("(h1) intake zone 3, date from created_utc", f"exit 0, files in zone_3/{day3}/", f"exit {rc}; {msg[0][:110]}", ok_place)
    rc, msg = intake(4, stage("z4", 4, W / "sub_clean", xlsx=True), I)
    ok_place = rc == 0 and (I / f"zone_4/{day3}/zone_4.osc").is_file() and (I / f"zone_4/{day3}/records/records_zone.xlsx").is_file()
    row("(h2) intake zone 4 with record sheet", "exit 0, .osc, meta and records/*.xlsx placed", f"exit {rc}", ok_place)
    rc, rep, _ = merge(I, W / "out_h")
    row("(h3) merge of the intaken directory", "same merged.osc and merged.osm as (c); records/ ignored",
        f"exit {rc}; osc same {sha(W / 'out_h/merged.osc') == sha(W / 'out_c/merged.osc')}; osm same {sha(W / 'out_h/ring1_roads_merged.osm') == sha(W / 'out_c/ring1_roads_merged.osm')}",
        rc == 0 and sha(W / "out_h/merged.osc") == sha(W / "out_c/merged.osc") and sha(W / "out_h/ring1_roads_merged.osm") == sha(W / "out_c/ring1_roads_merged.osm"))
    rc, msg = intake(3, W / "intake_src/z3", I)
    row("(h4) same files again", "exit 0, 'identical files already there'", f"exit {rc}; {'identical' in msg[0]}", rc == 0 and "identical files already there" in msg[0])
    J = W / "sub_intake_bad"
    rc, msg = intake(4, W / "intake_src/z3", J)
    row("(h5) wrong zone: zone 3 files given as zone 4", "exit 64 (files zone_4.* not found), nothing placed", f"exit {rc}; {msg[0][:100]}", rc == 64 and not J.exists())
    rc, msg = intake(4, stage("z3_as_4", 3, W / "sub_clean", rename_to=4), J)
    row("(h6) zone 3 files renamed to zone_4.*", "exit 4 (meta editor_index 3), nothing placed", f"exit {rc}; {msg[0][:100]}", rc == 4 and not J.exists())
    rc, msg = intake(3, stage("badsha", 3, W / "sub_clean", meta_edit=lambda m: m.update(base_sha256="0" * 64)), J)
    row("(h7) wrong base sha256", "exit 4, nothing placed", f"exit {rc}; {msg[0][:100]}", rc == 4 and not J.exists())
    rc, msg = intake(3, stage("emptyosc", 3, W / "sub_clean", osc_text="<?xml version='1.0'?><osmChange version='0.6'/>"), J)
    row("(h8) empty .osc", "exit 64, nothing placed", f"exit {rc}; {msg[0][:100]}", rc == 64 and not J.exists())
    rc, msg = intake(3, stage("older", 3, W / "sub_clean", meta_edit=lambda m: m.update(created_utc="2026-10-01T08:00:00Z")), I)
    row("(h9) older created_utc than the one present", "exit 1, nothing placed", f"exit {rc}; {msg[0][:110]}", rc == 1 and not (I / "zone_3/20261001").exists())
    K = W / "sub_intake_force"
    shutil.copytree(I, K)
    rc, msg = intake(3, W / "intake_src/older", K, "--force")
    row("(h10) same file with --force", "exit 0, placed in zone_3/20261001", f"exit {rc}", rc == 0 and (K / "zone_3/20261001/zone_3.osc").is_file())
    t_new = (datetime.datetime.strptime(c3, "%Y-%m-%dT%H:%M:%SZ") + datetime.timedelta(seconds=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    newer = stage("newer_same_day", 3, W / "sub_rev", meta_edit=lambda m: m.update(created_utc=t_new))
    if t_new[:10] != c3[:10]:
        notes.append("(h11) skipped: +1 s crossed midnight")
    rc, msg = intake(3, newer, I)
    row("(h11) newer submission of the same day, different content, no --replace", "exit 1, old files kept", f"exit {rc}; {msg[0][:130]}",
        rc == 1 and sha(I / f"zone_3/{day3}/zone_3.osc") == sha(W / "intake_src/z3/zone_3.osc") and "--replace" in msg[0])
    rc, msg = intake(3, newer, I, "--replace")
    row("(h12) same with --replace", "exit 0 'replaced', new content in place", f"exit {rc}; {'replaced' in msg[0]}",
        rc == 0 and "replaced" in msg[0] and sha(I / f"zone_3/{day3}/zone_3.osc") == sha(newer / "zone_3.osc"))
    arch = sorted((I / f"zone_3/{day3}/replaced").glob("*/zone_3.osc"))
    row("(h12b) the replaced file is archived, not deleted", f"replaced/{c3}/ with the old .osc (sha256 of the first intake) and meta",
        f"{[p.parent.name for p in arch]}; content kept: {bool(arch) and sha(arch[0]) == sha(W / 'intake_src/z3/zone_3.osc')}; meta: {bool(arch) and (arch[0].parent / 'zone_3.osc.meta.json').is_file()}",
        len(arch) == 1 and arch[0].parent.name == c3 and sha(arch[0]) == sha(W / "intake_src/z3/zone_3.osc") and (arch[0].parent / "zone_3.osc.meta.json").is_file())
    rc, rep, _ = merge(I, W / "out_h2")
    names = re.findall(r"^\| 3 \| ((?:node|way|relation) -?\d+) \|", section(rep, 5), re.M)
    row("(h13) merge after the replace (the formerly silent case)", "exit 0; revert list names relation 3262876; archive listed as superseded",
        f"exit {rc}; revert list {names}; superseded {re.findall(r'replaced/[^`]+', section(rep, 1))}",
        rc == 0 and names == ["relation 3262876"] and f"zone_3/{day3}/replaced/{c3}/zone_3.osc" in section(rep, 1))
    row("(h13) merged outputs equal those of (d2) (same newest files)", "merged.osc and merged.osm identical",
        f"{sha(W / 'out_h2/merged.osc') == sha(W / 'out_d2/merged.osc')}, {sha(W / 'out_h2/ring1_roads_merged.osm') == sha(W / 'out_d2/ring1_roads_merged.osm')}",
        sha(W / "out_h2/merged.osc") == sha(W / "out_d2/merged.osc") and sha(W / "out_h2/ring1_roads_merged.osm") == sha(W / "out_d2/ring1_roads_merged.osm"))

    # (k) same-day replace and the revert list
    def bump(c, secs):
        return (datetime.datetime.strptime(c, "%Y-%m-%dT%H:%M:%SZ") + datetime.timedelta(seconds=secs)).strftime("%Y-%m-%dT%H:%M:%SZ")
    t0 = json.loads(next((W / "sub_two/zone_3").glob(f"{d1}/zone_3.osc.meta.json")).read_text())["created_utc"]
    v_c15 = stage("k_c15", 3, W / "sub_two", day=d1, meta_edit=lambda m: m.update(created_utc=t0))
    v_full = stage("k_full", 3, W / "sub_two", day=d2, meta_edit=lambda m: m.update(created_utc=bump(t0, 1)))   # C1-C10 clean: only adds to C1-C5
    v_nc5 = stage("k_nc5", 3, W / "sub_rev", day=d2, meta_edit=lambda m: m.update(created_utc=bump(t0, 2)))     # clean, C5 reverted
    v_nc5b = stage("k_nc5b", 3, W / "sub_rev", day=d2, meta_edit=lambda m: m.update(created_utc=bump(t0, 1)))
    z4 = stage("k_z4", 4, W / "sub_clean")
    dayk = t0[:10].replace("-", "")

    def revs(rep):
        return re.findall(r"^\| 3 \| ((?:node|way|relation) -?\d+) \|", section(rep, 5), re.M)
    # (k1)
    K1 = W / "sub_k1"
    intake(4, z4, K1), intake(3, v_c15, K1)
    rc1, m1 = intake(3, v_nc5b, K1, "--replace")
    rc, rep, _ = merge(K1, W / "out_k1")
    row("(k1) C1-C5 first, then --replace with the C5-reverted variant", "intake exit 0; revert list names exactly relation 3262876",
        f"intake {rc1}; exit {rc}; revert list {revs(rep)}", rc1 == 0 and rc == 0 and revs(rep) == ["relation 3262876"])
    row("(k1) merged outputs equal those of (d2)", "merged.osc, merged.osm identical", f"{sha(W / 'out_k1/merged.osc') == sha(W / 'out_d2/merged.osc')}, {sha(W / 'out_k1/ring1_roads_merged.osm') == sha(W / 'out_d2/ring1_roads_merged.osm')}",
        sha(W / "out_k1/merged.osc") == sha(W / "out_d2/merged.osc") and sha(W / "out_k1/ring1_roads_merged.osm") == sha(W / "out_d2/ring1_roads_merged.osm"))
    # (k1b) with and without the archive
    K1b = W / "sub_k1_noarch"
    shutil.copytree(K1, K1b)
    shutil.rmtree(K1b / f"zone_3/{dayk}/replaced")
    rc, rep_b, _ = merge(K1b, W / "out_k1b")
    row("(k1b) same newest files without the archive", "merged.osc and merged.osm identical; revert list empty; reports differ only by the superseded / revert sections",
        f"osc {sha(W / 'out_k1b/merged.osc') == sha(W / 'out_k1/merged.osc')}, osm {sha(W / 'out_k1b/ring1_roads_merged.osm') == sha(W / 'out_k1/ring1_roads_merged.osm')}, reverts {revs(rep_b)}, "
        f"sections 2-4 equal {all(section(rep, n) == section(rep_b, n) for n in (2, 3, 4))}",
        rc == 0 and sha(W / "out_k1b/merged.osc") == sha(W / "out_k1/merged.osc") and sha(W / "out_k1b/ring1_roads_merged.osm") == sha(W / "out_k1/ring1_roads_merged.osm")
        and revs(rep_b) == [] and all(section(rep, n) == section(rep_b, n) for n in (2, 3, 4)))
    # (k2) two replaces in a row
    K2 = W / "sub_k2"
    intake(4, z4, K2), intake(3, v_c15, K2)
    r1, _ = intake(3, v_full, K2, "--replace")
    r2, _ = intake(3, v_nc5, K2, "--replace")
    arch = sorted((K2 / f"zone_3/{dayk}/replaced").glob("*/zone_3.osc"))
    rc, rep, _ = merge(K2, W / "out_k2")
    row("(k2) two replaces in a row", "both archived files kept; both listed as superseded; revert list names relation 3262876",
        f"intake {r1}/{r2}; archive {[p.parent.name for p in arch]}; superseded {len(re.findall('replaced/', section(rep, 1)))}; revert list {revs(rep)}",
        r1 == r2 == 0 and [p.parent.name for p in arch] == [t0, bump(t0, 1)] and len(re.findall("replaced/", section(rep, 1))) == 2 and set(revs(rep)) == {"relation 3262876"}
        and sha(arch[0]) == sha(v_c15 / "zone_3.osc") and sha(arch[1]) == sha(v_full / "zone_3.osc"))
    row("(k2) merged outputs equal those of (d2)", "identical", f"{sha(W / 'out_k2/merged.osc') == sha(W / 'out_d2/merged.osc')}", sha(W / "out_k2/merged.osc") == sha(W / "out_d2/merged.osc"))
    # (k3) a replace that only adds edits
    K3 = W / "sub_k3"
    intake(4, z4, K3), intake(3, v_c15, K3)
    r3, _ = intake(3, v_full, K3, "--replace")
    rc, rep, _ = merge(K3, W / "out_k3")
    row("(k3) replace with a file that only adds edits", "exit 0; archive kept and listed; revert list empty", f"intake {r3}; exit {rc}; revert section: {section(rep, 5).strip()}; superseded {len(re.findall('replaced/', section(rep, 1)))}",
        r3 == 0 and rc == 0 and section(rep, 5).strip() == "none" and len(re.findall("replaced/", section(rep, 1))) == 1)
    row("(k3) merged outputs equal those of (c)", "identical", f"{sha(W / 'out_k3/merged.osc') == sha(W / 'out_c/merged.osc')}", sha(W / "out_k3/merged.osc") == sha(W / "out_c/merged.osc"))
    # (k4) the archive of one zone does not influence the other zone
    z4row = lambda r: re.findall(r"^\| 4 \| .*$", section(r, 1), re.M)
    z4in = lambda r: [l for l in section(r, 5).splitlines() if l.startswith("| 4 |")]
    rev_k1 = open(W / "out_k1/MERGE_REPORT.md", encoding="utf-8").read()
    row("(k4) zone 3 archive and zone 4", "zone 4 row (file, counts, status) and sha256 lines identical with and without the archive; no zone 4 revert rows",
        f"row equal {z4row(rep_b) == z4row(rev_k1)}; zone 4 reverts {z4in(rev_k1)}",
        z4row(rep_b) == z4row(rev_k1) and z4in(rev_k1) == [] and [l for l in section(rev_k1, 7).splitlines() if "zone_4" in l] == [l for l in section(rep_b, 7).splitlines() if "zone_4" in l])

    # tampered meta
    for label, field, val, zone in (("base sha256 of zone 4 wrong", "base_sha256", "0" * 64, 4), ("editor index of zone 3 wrong", "editor_index", 9, 3)):
        S2 = W / f"sub_meta_{field}"
        shutil.copytree(W / "sub_clean", S2)
        mp = next((S2 / f"zone_{zone}").glob("*/zone_*.osc.meta.json"))
        m = json.loads(mp.read_text())
        m[field] = val
        mp.write_text(json.dumps(m))
        rc, rep, _ = merge(S2, W / f"out_meta_{field}")
        other = 3 if zone == 4 else 4
        row(f"(f) tampered meta: {label}", f"exit 4; zone {zone} refused, zone {other} merged", f"exit {rc}; {re.search(r'Zones merged: [^.]*', rep).group(0)}", rc == 4 and f"Zones merged: {other}." in rep and f"Zones refused: {zone}." in rep)

    # timing / report
    L = ["# Task 04m: merge of submissions (`src/28_merge_submissions.py`)", "",
         "Produced by `src/29_merge_tests.py` (config `config/29_merge_tests.yaml`) with `scripts/merge_submissions.sh`, `scripts/submit_edits.sh`, `src/21_ownership_check.py`, `src/18_osm_conflicts.py`, `src/osm_io.py`. "
         "Inputs verified with `scripts/verify_inputs.sh`; real JOSM 19613 files `data/interim/spike_real/editedB.osm` (zone 4, package v1 = v2) and `data/interim/spike_real2/editedC.osm` (zone 3, package v2). "
         "`data/raw/` and the packages are untouched; nothing is committed. Scratch files: `data/interim/merge_tests/` (not in git).", "",
         "## 1. Test table", "", "| Test | Expected | Actual | Status |", "|---|---|---|---|"]
    L += [f"| {a} | {b} | {c.replace('|', '/')} | {d} |" for a, b, c, d in T]
    fails = sum(t[3] != "ok" for t in T)
    L += ["", f"{len(T) - fails} of {len(T)} rows ok, {fails} FAIL.", "", "## 2. Clean variants (made with `osm_io`)", ""] + details
    L += ["", "## 3. Runtime of a merge", "",
          f"- zones 3 + 4, without netconvert: {secs_nonet:.1f} s; with `--netconvert` (base and merged network, bbox of RING 1 + margin): {secs_c:.1f} s (first run; the base network is built each time in a new output directory).",
          f"- zones 3 + 4 with `--allow-violations` (b): {secs_b:.1f} s (merge only, 2 submissions with 27 objects).", ""]
    c_net = nets[0] if nets else ("?", "?")
    L += ["", "## 4. Idempotence", "",
          f"Two runs on the same submissions (`(c)`, with `--netconvert`, different output directories): `MERGE_REPORT.md` sha256 `{sha(W / 'out_c/MERGE_REPORT.md')}` both times; "
          f"`merged.osc` `{sha(W / 'out_c/merged.osc')}` both times; `ring1_roads_merged.osm` `{sha(W / 'out_c/ring1_roads_merged.osm')}` both times. "
          "These are also the hashes of the first 04m run, made before `created_utc` existed in the meta files; the merge ignores that field "
          "(the meta hash in section 7 of the merge report is taken over the meta without `created_utc`, which is byte-identical to the file `19_osm_submit.py` wrote). "
          "The (h) tests place the same files with `intake_submission.sh` and get the same merged files.",
          "", "## 5. Design decisions and findings", "",
          "- **Exit code precedence:** 4 (meta / base refusal) beats 1 (violation / conflict) when both occur in one run; in both cases the remaining zones are merged.",
          "- **Cross-zone check is a warning, a conflict (18) is a refusal.** The brief lists the cross-editor semantic check next to 18; I read \"conflict refuses\" as applying to 18 only (same object, negative-id collision). If a cross-zone warning should refuse too, it is one line in `src/28_merge_submissions.py`.",
          "- **editedB alone has no semantic warning.** The warning for node 165109460 needs a second editor that MOVES the node (it came from editedA, A6, zone 3 v1). editedB changes only way 16313072 (B1). The path is tested synthetically in (g): zone 3 moves node 165109460 by 7.8 m (a violation, merged only with `--allow-violations`); the report gives the cross-zone warning `cross_editor_way` (way 16313072 changed by zone 4) and `relation_member` (relation 2532024) in the zone's own list.",
          "- **Dates:** `submit_edits.sh` names the directory after the day of the run, so the two-session tests rename the directory to build older / newer days. The older file gets mtime 1970 in those tests, so the date directory alone decides the order (file time is only the tie-breaker within one day). `intake_submission.sh` takes the date from `created_utc` (UTC), so a late-evening local submission may land in the next day's directory.",
          f"- **Netconvert bbox:** RING 1 polygon (`data/derived/ring1.geojson`) + 0.004 deg margin (my choice, `config/28_merge.yaml`). Clean merge of zones 3 + 4: {c_net[0]} -> {c_net[1]} edges. Options: defaults of docs/SETUP.md 6b plus `--keep-edges.in-geo-boundary`; no `--junctions.join --tls.join` (open decision).",
          "- **Not touched:** ownership tables, packages, the checks in 21. `docs/pilot/ONBOARDING.md` is unchanged: raters keep running `submit_edits.sh` and send the same two files; `created_utc` is added automatically. Nothing committed.",
          "- **Same-day replace (04m-c):** `intake_submission.sh --replace` archives the old files in `<date>/replaced/<created_utc>/`; the merge never merges them but uses them (and older date directories) for the revert list and lists them as superseded. The formerly silent h13 case now names relation 3262876. Merged outputs depend only on the newest submission per zone; only the superseded / revert sections of `MERGE_REPORT.md` differ with an archive. The report of a merge with an archive contains the archive's created_utc in its path, so only merges without an archive have a fixed report hash across test reruns. ONBOARDING unchanged: raters do nothing new.",
          "- **Self-tests of the setup:** `scripts/check_setup.sh R1` gives 27 PASS and 1 FAIL (`pilot tag pilot-v1` not found locally; the same FAIL with my changes stashed, so it predates them); its dry run of `submit_edits.sh` passes with the new `created_utc` code. `scripts/selftest_handoff.sh HEAD R1` clones the COMMITTED revision, so it cannot see these uncommitted changes; it gives the same single tag FAIL (27 PASS)."]
    L += ["", *notes] if notes else []
    (ROOT / cfg["report"]).write_text("\n".join(L) + "\n", encoding="utf-8")
    print("\n".join(f"{t[3]:4} {t[0]}" for t in T))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
