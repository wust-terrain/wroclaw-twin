# Task 04m: merge of submissions (`src/28_merge_submissions.py`)

Produced by `src/29_merge_tests.py` (config `config/29_merge_tests.yaml`) with `scripts/merge_submissions.sh`, `scripts/submit_edits.sh`, `src/21_ownership_check.py`, `src/18_osm_conflicts.py`, `src/osm_io.py`. Inputs verified with `scripts/verify_inputs.sh`; real JOSM 19613 files `data/interim/spike_real/editedB.osm` (zone 4, package v1 = v2) and `data/interim/spike_real2/editedC.osm` (zone 3, package v2). `data/raw/` and the packages are untouched; nothing is committed. Scratch files: `data/interim/merge_tests/` (not in git).

## 1. Test table

| Test | Expected | Actual | Status |
|---|---|---|---|
| input: package zone_4.osm sha256 | ec2e03f5... | ec2e03f5... | ok |
| input: package zone_3.osm sha256 | 513d17da... | 513d17da... | ok |
| submit_edits.sh editedB / editedC | exit 1 / 1 (violations written) | 1 / 1 | ok |
| (a) default merge of editedB + editedC | exit 1, both zones refused with exactly B6, C9, C10b | exit 1, violations [('3', 'node 3702470623'), ('3', 'relation 1732342'), ('4', 'way 187980700')] | ok |
| (a) nothing merged | no merged.osm / merged.osc | none written | ok |
| (b) --allow-violations | exit 0, zones 3 and 4 merged, report says so | exit 0 | ok |
| (b) merged differs from base exactly in the edited objects of both files | 27 expected = 27 differing, 0 mismatches | 27 expected, 27 differing, mismatches [], content problems [] | ok |
| (b) osmium check-refs | no new missing references | 0 new | ok |
| submit_edits.sh clean variants | exit 0 / 0 | 0 / 0 | ok |
| (c) clean variants, no --allow-violations | exit 0, zones 3 and 4 merged | exit 0 | ok |
| (c) merged differs from base exactly in the edited objects | 24 expected = 24 differing (27 minus B6, C9, C10b), 0 mismatches | 24 expected, 24 differing, mismatches [], content problems [] | ok |
| (c) netconvert before / after | success; edges after > before (two new ways, one deleted way pair ...) | edges 51484 -> 51487 | ok |
| (c) second run: MERGE_REPORT.md / merged.osc / merged.osm identical | same sha256 | [True, True, True]; report 7111f6e3f1d4d5f8, osc ddb06edaf77e927a | ok |
| (c) same inputs without --netconvert: merged.osc identical | same sha256 | ddb06edaf77e927a | ok |
| (c) hashes equal the first 04m run (before created_utc existed) | MERGE_REPORT.md and merged.osc identical to the 04m results | report 7111f6e3f1d4, osc ddb06edaf77e | ok |
| submit_edits.sh writes created_utc | 2 meta files with created_utc | 2 of 2 | ok |
| (c) other created_utc in the meta files: merge ignores it | MERGE_REPORT.md, merged.osc, merged.osm identical | [True, True, True] | ok |
| (d1) two sessions of zone 3 | exit 0; only the second used, the first superseded | exit 0; superseded line: ['- zone 3: `zone_3/20261029/zone_3.osc`'] | ok |
| (d1) revert list of the cumulative pair | none | none | ok |
| (d1) merged = same result as (c) | 24 = 24, identical merged.osc to (c) | 24 = 24; osc identical True | ok |
| (d2) revert of C5 | exit 0; revert list names exactly relation 3262876 | exit 0; revert list ['relation 3262876'] | ok |
| (e) shared node 3438315710 is in package zone_3 | yes | True | ok |
| (e) shared node 3438315710 is in package zone_4 | yes | True | ok |
| (e) same whitelisted node moved by zones 3 and 4 | exit 1; conflict node reported; both zones refused; nothing merged | exit 1; conflict lines ['- node 3438315710 changed by zone_3, zone_4']; merged none | ok |
| (g) node 165109460 is in package zone_3 | yes | True | ok |
| (g1) default run | exit 1; zone 3 refused (node of zone 4), zone 4 merged | exit 1 | ok |
| (g2) --allow-violations | exit 0; cross-zone warning for node 165109460 (used by way 16313072 changed by zone 4); relation_member warning in the zone's own list | exit 0; cross: ['cross_editor_way'], way 16313072 named: True; own list: ['relation_member'] | ok |
| (h1) intake zone 3, date from created_utc | exit 0, files in zone_3/20261030/ | exit 0; intake zone 3: /home/dominik/projects/terrain/wroclaw-twin/data/interim/merge_tests/sub_intake/zone_3/20261030 | ok |
| (h2) intake zone 4 with record sheet | exit 0, .osc, meta and records/*.xlsx placed | exit 0 | ok |
| (h3) merge of the intaken directory | same merged.osc and merged.osm as (c); records/ ignored | exit 0; osc same True; osm same True | ok |
| (h4) same files again | exit 0, 'identical files already there' | exit 0; True | ok |
| (h5) wrong zone: zone 3 files given as zone 4 | exit 64 (files zone_4.* not found), nothing placed | exit 64; intake refused (exit 64): zone_4.osc not found in /home/dominik/projects/terrain/wroclaw-twin/data/i | ok |
| (h6) zone 3 files renamed to zone_4.* | exit 4 (meta editor_index 3), nothing placed | exit 4; intake refused (exit 4): meta editor_index is 3, not 4: the files belong to another zone | ok |
| (h7) wrong base sha256 | exit 4, nothing placed | exit 4; intake refused (exit 4): meta base_sha256 000000000000... differs from the package sidecar 513d17da3 | ok |
| (h8) empty .osc | exit 64, nothing placed | exit 64; intake refused (exit 64): zone_3.osc contains no objects (empty change file) | ok |
| (h9) older created_utc than the one present | exit 1, nothing placed | exit 1; intake refused (exit 1): older than the submission already present (20261030, created 2026-10-30T17:53:59Z): a | ok |
| (h10) same file with --force | exit 0, placed in zone_3/20261001 | exit 0 | ok |
| (h11) newer submission of the same day, different content, no --replace | exit 1, old files kept | exit 1; intake refused (exit 1): /home/dominik/projects/terrain/wroclaw-twin/data/interim/merge_tests/sub_intake/zone_3/20261030/zone_3.os | ok |
| (h12) same with --replace | exit 0 'replaced', new content in place | exit 0; True | ok |
| (h12b) the replaced file is archived, not deleted | replaced/2026-10-30T17:53:59Z/ with the old .osc (sha256 of the first intake) and meta | ['2026-10-30T17:53:59Z']; content kept: True; meta: True | ok |
| (h13) merge after the replace (the formerly silent case) | exit 0; revert list names relation 3262876; archive listed as superseded | exit 0; revert list ['relation 3262876']; superseded ['replaced/2026-10-30T17:53:59Z/zone_3.osc'] | ok |
| (h13) merged outputs equal those of (d2) (same newest files) | merged.osc and merged.osm identical | True, True | ok |
| (k1) C1-C5 first, then --replace with the C5-reverted variant | intake exit 0; revert list names exactly relation 3262876 | intake 0; exit 0; revert list ['relation 3262876'] | ok |
| (k1) merged outputs equal those of (d2) | merged.osc, merged.osm identical | True, True | ok |
| (k1b) same newest files without the archive | merged.osc and merged.osm identical; revert list empty; reports differ only by the superseded / revert sections | osc True, osm True, reverts [], sections 2-4 equal True | ok |
| (k2) two replaces in a row | both archived files kept; both listed as superseded; revert list names relation 3262876 | intake 0/0; archive ['2026-10-30T17:54:48Z', '2026-10-30T17:54:49Z']; superseded 2; revert list ['relation 3262876', 'relation 3262876'] | ok |
| (k2) merged outputs equal those of (d2) | identical | True | ok |
| (k3) replace with a file that only adds edits | exit 0; archive kept and listed; revert list empty | intake 0; exit 0; revert section: none; superseded 1 | ok |
| (k3) merged outputs equal those of (c) | identical | True | ok |
| (k4) zone 3 archive and zone 4 | zone 4 row (file, counts, status) and sha256 lines identical with and without the archive; no zone 4 revert rows | row equal True; zone 4 reverts [] | ok |
| (f) tampered meta: base sha256 of zone 4 wrong | exit 4; zone 4 refused, zone 3 merged | exit 4; Zones merged: 3 | ok |
| (f) tampered meta: editor index of zone 3 wrong | exit 4; zone 3 refused, zone 4 merged | exit 4; Zones merged: 4 | ok |

52 of 52 rows ok, 0 FAIL.

## 2. Clean variants (made with `osm_io`)

- zone 4: `editedB.osm` without B6 (way 187980700, put back to the package state)
- zone 3: `editedC.osm` without C10b (node 3702470623, put back to the package state), C9 (relation 1732342, put back to the package state)
- zone 3 first session (C1-C5 only): clean variant without C6: [['relation', 4680857]], C7: [['relation', -83]], C8: [['way', 481680205], ['node', 3707768720], ['node', 2268359200]], C10a: [['way', 115117541]]
- zone 3 second session with C5 reverted: clean variant without C5 (relation 3262876 put back to the package state)

## 3. Runtime of a merge

- zones 3 + 4, without netconvert: 5.9 s; with `--netconvert` (base and merged network, bbox of RING 1 + margin): 16.7 s (first run; the base network is built each time in a new output directory).
- zones 3 + 4 with `--allow-violations` (b): 5.9 s (merge only, 2 submissions with 27 objects).


## 4. Idempotence

Two runs on the same submissions (`(c)`, with `--netconvert`, different output directories): `MERGE_REPORT.md` sha256 `7111f6e3f1d4d5f85315210571de9b496b67497eeb232097e47f54cfcd824325` both times; `merged.osc` `ddb06edaf77e927acfa3c714c10cb133add4078a008c9222cec958521af00569` both times; `ring1_roads_merged.osm` `5071758265490ba7e64f07aae5be6e72a89a0655ff3de6a97e6f88b5a67ba180` both times. These are also the hashes of the first 04m run, made before `created_utc` existed in the meta files; the merge ignores that field (the meta hash in section 7 of the merge report is taken over the meta without `created_utc`, which is byte-identical to the file `19_osm_submit.py` wrote). The (h) tests place the same files with `intake_submission.sh` and get the same merged files.

## 5. Design decisions and findings

- **Exit code precedence:** 4 (meta / base refusal) beats 1 (violation / conflict) when both occur in one run; in both cases the remaining zones are merged.
- **Cross-zone check is a warning, a conflict (18) is a refusal.** The brief lists the cross-editor semantic check next to 18; I read "conflict refuses" as applying to 18 only (same object, negative-id collision). If a cross-zone warning should refuse too, it is one line in `src/28_merge_submissions.py`.
- **editedB alone has no semantic warning.** The warning for node 165109460 needs a second editor that MOVES the node (it came from editedA, A6, zone 3 v1). editedB changes only way 16313072 (B1). The path is tested synthetically in (g): zone 3 moves node 165109460 by 7.8 m (a violation, merged only with `--allow-violations`); the report gives the cross-zone warning `cross_editor_way` (way 16313072 changed by zone 4) and `relation_member` (relation 2532024) in the zone's own list.
- **Dates:** `submit_edits.sh` names the directory after the day of the run, so the two-session tests rename the directory to build older / newer days. The older file gets mtime 1970 in those tests, so the date directory alone decides the order (file time is only the tie-breaker within one day). `intake_submission.sh` takes the date from `created_utc` (UTC), so a late-evening local submission may land in the next day's directory.
- **Netconvert bbox:** RING 1 polygon (`data/derived/ring1.geojson`) + 0.004 deg margin (my choice, `config/28_merge.yaml`). Clean merge of zones 3 + 4: 51484 -> 51487 edges. Options: defaults of docs/SETUP.md 6b plus `--keep-edges.in-geo-boundary`; no `--junctions.join --tls.join` (open decision).
- **Not touched:** ownership tables, packages, the checks in 21. `docs/pilot/ONBOARDING.md` is unchanged: raters keep running `submit_edits.sh` and send the same two files; `created_utc` is added automatically. Nothing committed.
- **Same-day replace (04m-c):** `intake_submission.sh --replace` archives the old files in `<date>/replaced/<created_utc>/`; the merge never merges them but uses them (and older date directories) for the revert list and lists them as superseded. The formerly silent h13 case now names relation 3262876. Merged outputs depend only on the newest submission per zone; only the superseded / revert sections of `MERGE_REPORT.md` differ with an archive. The report of a merge with an archive contains the archive's created_utc in its path, so only merges without an archive have a fixed report hash across test reruns. ONBOARDING unchanged: raters do nothing new.
- **Self-tests of the setup:** `scripts/check_setup.sh R1` gives 27 PASS and 1 FAIL (`pilot tag pilot-v1` not found locally; the same FAIL with my changes stashed, so it predates them); its dry run of `submit_edits.sh` passes with the new `created_utc` code. `scripts/selftest_handoff.sh HEAD R1` clones the COMMITTED revision, so it cannot see these uncommitted changes; it gives the same single tag FAIL (27 PASS).
