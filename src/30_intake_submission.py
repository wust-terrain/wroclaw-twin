"""Task 04m follow-up: place the files a rater sent into submissions/zone_<N>/<YYYYMMDD>/ after validating them.

Expects in DIR: zone_<N>.osc and zone_<N>.osc.meta.json (optionally one record sheet *.xlsx, copied to <date>/records/).
Checks: file names, meta editor_index = N, meta base_sha256 = sha256_extract of the package sidecar, .osc not empty.
Date directory: date of meta `created_utc` if present, else --date, else today. A second submission of the same day normally
REPLACES the first: it is refused without --replace when the content differs; the replaced files (.osc, meta, records) are
archived in <date>/replaced/<created_utc of the old file>/ and never deleted (the merge uses them for the revert list only). A submission whose created_utc (or date) is older than
the newest one already present for the zone (an old file sent again) is refused unless --force.

Usage: uv run python src/30_intake_submission.py ZONE DIR [--date YYYYMMDD] [--replace] [--force] [--submissions DIR] [--zones-dir DIR]
Exit codes: 0 placed (or identical files already there), 1 refused (would overwrite different content / older than present),
4 meta does not match the zone or the package, 64 usage error, missing or wrongly named file, empty .osc.
"""
import argparse
import datetime
import hashlib
import json
import pathlib
import re
import shutil
import sys
import xml.etree.ElementTree as ET

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent


def die(code, msg):
    print(f"intake refused (exit {code}): {msg}", file=sys.stderr)
    sys.exit(code)


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def parse_utc(text):
    return datetime.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zone", type=int)
    ap.add_argument("dir")
    ap.add_argument("--date")
    ap.add_argument("--replace", action="store_true", help="replace different files of the same day (the normal case for a second submission)")
    ap.add_argument("--force", action="store_true", help="accept a submission older than the newest one present")
    ap.add_argument("--submissions", default=None)
    ap.add_argument("--zones-dir", default=None)
    a = ap.parse_args()
    cfg = yaml.safe_load(open(ROOT / "config/28_merge.yaml", encoding="utf-8"))
    sub_root = pathlib.Path(a.submissions or "submissions")
    zones_dir = ROOT / cfg["zones_dir"] if not a.zones_dir else pathlib.Path(a.zones_dir)
    src = pathlib.Path(a.dir)
    z = a.zone
    if a.date and not re.fullmatch(r"\d{8}", a.date):
        die(64, f"--date must be YYYYMMDD, got {a.date}")
    osc, meta_p = src / f"zone_{z}.osc", src / f"zone_{z}.osc.meta.json"
    for f in (osc, meta_p):
        if not f.is_file():
            others = sorted(p.name for p in src.glob("zone_*.osc*")) if src.is_dir() else []
            die(64, f"{f.name} not found in {src}" + (f" (found: {', '.join(others)}; is this the right zone?)" if others else ""))
    xlsx = sorted(src.glob("*.xlsx"))
    if len(xlsx) > 1:
        die(64, f"more than one .xlsx in {src}: {', '.join(p.name for p in xlsx)}")
    try:
        objs = sum(1 for blk in ET.parse(osc).getroot() for el in blk if el.tag in ("node", "way", "relation"))
    except ET.ParseError as e:
        die(64, f"{osc.name} is not valid XML: {e}")
    if objs == 0:
        die(64, f"{osc.name} contains no objects (empty change file)")
    try:
        meta = json.loads(meta_p.read_text(encoding="utf-8"))
    except ValueError as e:
        die(64, f"{meta_p.name} is not valid JSON: {e}")
    if meta.get("editor_index") != z:
        die(4, f"meta editor_index is {meta.get('editor_index')}, not {z}: the files belong to another zone")
    side = zones_dir / f"zone_{z}" / f"zone_{z}.json"
    try:
        want = json.loads(side.read_text(encoding="utf-8")).get("sha256_extract")
    except (OSError, ValueError) as e:
        die(64, f"package sidecar {side} unreadable: {e}")
    if meta.get("base_sha256") != want:
        die(4, f"meta base_sha256 {str(meta.get('base_sha256'))[:12]}... differs from the package sidecar {str(want)[:12]}...: derived against another base")
    created = None
    if "created_utc" in meta:
        try:
            created = parse_utc(meta["created_utc"])
        except ValueError:
            die(64, f"created_utc '{meta['created_utc']}' is not YYYY-MM-DDTHH:MM:SSZ")
    date = created.strftime("%Y%m%d") if created else (a.date or datetime.date.today().strftime("%Y%m%d"))

    zdir = sub_root / f"zone_{z}"
    dest = zdir / date
    # older than what is already present? (created_utc where both have it, else the date directory)
    present = []
    for d in sorted(zdir.glob("[0-9]" * 8)) if zdir.is_dir() else []:
        m = d / f"zone_{z}.osc.meta.json"
        if (d / f"zone_{z}.osc").is_file():
            c = None
            try:
                c = parse_utc(json.loads(m.read_text(encoding="utf-8")).get("created_utc", ""))
            except (OSError, ValueError):
                pass
            present.append((d.name, c))
    for dname, c in present:
        old = (created < c) if (created and c) else (date < dname)
        if old and not a.force:
            die(1, f"older than the submission already present ({dname}" + (f", created {c.isoformat()}Z" if c else "") + "): an old file sent again? Use --force if it is intended")
    same = (dest / osc.name).is_file() and (dest / osc.name).read_bytes() == osc.read_bytes()
    replaced = False
    if (dest / osc.name).is_file() and not same:
        if not a.replace:
            die(1, f"{dest}/{osc.name} exists with different content. A second submission of the same day normally replaces the first: use --replace")
        replaced = True
    if replaced:                                     # never delete: the replaced files go to <date>/replaced/<created_utc of the old file>/
        old_meta = dest / meta_p.name
        try:
            stamp = json.loads(old_meta.read_text(encoding="utf-8"))["created_utc"]
            parse_utc(stamp)
        except (OSError, ValueError, KeyError):
            stamp = "mtime-" + datetime.datetime.fromtimestamp((dest / osc.name).stat().st_mtime, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        arch, n = dest / "replaced" / stamp, 1
        while arch.exists():
            n += 1
            arch = dest / "replaced" / f"{stamp}_{n}"
        arch.mkdir(parents=True)
        shutil.copyfile(dest / osc.name, arch / osc.name)
        if old_meta.is_file():
            shutil.copyfile(old_meta, arch / meta_p.name)
        if (dest / "records").is_dir():
            shutil.copytree(dest / "records", arch / "records")
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(osc, dest / osc.name)
    shutil.copyfile(meta_p, dest / meta_p.name)
    if xlsx:
        (dest / "records").mkdir(exist_ok=True)
        shutil.copyfile(xlsx[0], dest / "records" / xlsx[0].name)
    state = f"replaced; old files in {arch.relative_to(dest)}/" if replaced else "identical files already there" if same else "new"
    print(f"intake zone {z}: {dest} ({state}); {objs} objects, osc sha256 {sha(osc)[:12]}..., created {meta.get('created_utc', 'n/a')}, records {'yes' if xlsx else 'no'}")


if __name__ == "__main__":
    main()
