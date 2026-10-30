# OSM editing and merging workflow

Status: **tested with real JOSM 19613 files** (`reports/09_real_josm_files.md`, task 04r). The open decision "how OSM is edited (local patches or live OSM)" is not settled by this document; this is the local-patch variant.

Rule: every object has exactly one owner; people edit only what they own. `src/21_ownership_check.py` checks this after the fact (section 3); nothing stops an editor while editing.

## 1. Tools

| Tool | Purpose |
|---|---|
| `scripts/prepare_pilot_osm.sh` | creates the base `data/interim/ring1_roads.osm` (one common base for everybody) |
| `scripts/josm_pilot.sh` | starts JOSM with the OSM API blocked (section 2) |
| `src/19_osm_submit.py` | edited `.osm` -> change file `.osc`; checks the base sha256 (exit 4) and refuses contaminated files (exit 3); bumps versions of changed objects, drops deleted objects, renumbers new ids; writes `OUT.osc.meta.json` |
| `src/21_ownership_check.py` | classifies every changed, deleted and created object against the ownership tables (exit 0/1/2/4) |
| `src/18_osm_conflicts.py` | reports objects changed by more than one editor, and new-id collisions (exit 1) |
| `osmium merge-changes`, `apply-changes`, `check-refs` | merge, apply, verify references |

Editor numbers (`--editor-index`, 0-based) are assigned once per person and never reused. Each number owns a block of one trillion ids; ids of new objects become `(index+1) * 10^12 + n`.

Exit codes:

| Code | Meaning | Script |
|---|---|---|
| 0 | ok | all |
| 1 | violation (ownership) or conflict (same object, same negative id) | 21, 18 |
| 2 | warnings only (new untagged node used by nothing (`orphan`); spanning way of `edges_zone` / face geometry edited by its owner; whitelisted node; cross-editor or relation side effects). Not a warning: edits of bridge-group ways by the group owner (`ok`, category `bridge_group_owner`) | 21 |
| 3 | contaminated input, nothing written | 19 |
| 4 | base mismatch, base not verifiable, or `.osc` derived against another base | 19, 21 |

## 2. Starting JOSM

Use `scripts/josm_pilot.sh [file.osm]`. It runs `java` with `--offline=osm_api` (File > Update data is greyed out, Download data cannot download) and the three Java 21 flags
`--add-exports=java.base/sun.security.action=ALL-UNNAMED`, `--add-exports=java.desktop/com.sun.imageio.plugins.jpeg=ALL-UNNAMED`, `--add-exports=java.desktop/com.sun.imageio.spi=ALL-UNNAMED` (without them JOSM shows a "may work improperly" dialog). JOSM jar: `~/tools/josm-tested.jar` (or `JOSM_JAR=...`); tested with JOSM 19613 and OpenJDK 21.

Remote control (Preferences > Remote Control): JOSM enables 7 actions by default, including "load data from API", "import data from URL" and "create new objects". Allow only **"Change the viewport"** and **"Read protocol version"** (`remotecontrol.permission.*` = false for the others).

**Never use File > Update data (Ctrl+U) or File > Download data.** They pull server data (uid/user/changeset, newer versions, objects deleted upstream) into your layer. In the spike one Ctrl+U put 10 658 refreshed objects, 59 changed versions and 6 upstream deletions into the file. `19_osm_submit.py` refuses such a file (exit 3); the only fix is to redo the edits on a fresh copy of the package. A plain `java -jar` start (without `--offline=osm_api`) does not block the API.

## 3. Steps for a cleaner

1. **Get the base.** Everybody uses the same base file (same checksum). Do not re-extract it yourself with other parameters. Keep the base unchanged; work on a copy.
2. **Take your zone package** (do not cut it yourself): `data/derived/zones_v02/zone_<N>/zone_<N>.osm` with its sidecar `zone_<N>.json` (`sha256_extract` is the checksum of the `.osm`; keep both files together). Package version 2 (`"package_version": 2`) = the zone polygon + 60 m as read-only context, **plus every object owned by the zone** (all its ways with all their nodes, its owned nodes, its owned relations). Open `zone_<N>_reference.osm` as a second JOSM layer: polygon, read buffer, seams, and `role=owned_outside_polygon` areas. Version 1 packages (they lack some owned objects) are kept unchanged in `data/derived/zones_v02/legacy_v1/` only as the base of already saved JOSM files.
   The base for step 5 must be this same zone file, so keep it unchanged and edit a copy `zone_XX_edit.osm`.
3. **Edit in JOSM** (started with `scripts/josm_pilot.sh`) only objects you own. New objects: draw them normally (JOSM gives them negative ids). Do not upload to openstreetmap.org.
4. **Save** as `zone_XX_edit.osm` (File > Save, not "Upload").
5. **Submit** (derive the change file and renumber ids):
   ```bash
   uv run python src/19_osm_submit.py zone_XX.osm zone_XX_edit.osm submissions/XX.osc --editor-index N
   uv run python src/21_ownership_check.py --editor NAME ZONE submissions/XX.osc zone_XX.osm      # ZONE = your zone number
   ```
   The first command prints `prepare: {...}`: `bumped` + `new` + `deleted_dropped` should match what you did. Exit 3 = contaminated file, exit 4 = wrong or unverifiable base. The second lists every changed object with `ok` / `warning` / `violation`; fix violations before sending.
6. **Send** `XX.osc` and `XX.osc.meta.json` (small files) to the person who merges. Do not send the full `.osm`.

## 4. Steps for the person who merges (by hand; `scripts/merge_submissions.sh` does all of this, see "Merging")

```bash
uv run python src/18_osm_conflicts.py A=submissions/A.osc B=submissions/B.osc ...   # exit 1 = stop, resolve first
uv run python src/21_ownership_check.py --editor A 3 A.osc zone_3.osm --editor B 4 B.osc zone_4.osm   # all editors together (cross-editor warnings)
osmium merge-changes submissions/*.osc -o merged.osc --overwrite
osmium apply-changes data/interim/ring1_roads.osm merged.osc -o merged.osm --overwrite
osmium check-refs -r merged.osm        # compare with the same command on the base: no new "missing"
netconvert --osm-files merged.osm -o merged.net.xml ...                          # options as in docs/SETUP.md 6b
```

Change files derived against a zone package apply to the full base and give exactly the objects the editors changed (tested: 87 746 objects compared, 0 differences; the v1 packages equal the full base in content and version). Do **not** derive against the full base: every object outside the zone would become a `<delete>`.

## Merging

`scripts/merge_submissions.sh` replaces the manual commands of section 4 (they stay valid for debugging). Task 04m, report `reports/11_merge.md`.

```bash
scripts/merge_submissions.sh [--allow-violations] [--netconvert] <submissions_dir> <out_dir>
# example: scripts/merge_submissions.sh submissions merged/2026-11-02 --netconvert
```

`<submissions_dir>` holds `zone_<N>/<YYYYMMDD>/zone_<N>.osc` + `.osc.meta.json` (written by `scripts/submit_edits.sh`; copy the files the raters send to this layout). Output in `<out_dir>`: `ring1_roads_merged.osm` (full base + changes), `merged.osc`, `MERGE_REPORT.md`; with `--netconvert` also `netconvert/{base,merged}.net.xml`. The same inputs give identical `MERGE_REPORT.md`, `merged.osc` and `ring1_roads_merged.osm` (no times or paths in them). A merge of two zones takes about 6 s, with `--netconvert` about 16 s.

What it does, in order:

1. Per zone it takes the NEWEST cumulative submission (date directory, then file time); older ones are listed as superseded and used only for revert detection.
2. Verifies the meta file: `base_sha256` = `sha256_extract` of the zone's package sidecar, `editor_index` = zone number, package unchanged, full base = `sha256_base_osm` of the sidecar. A zone that fails is refused (exit 4 at the end).
3. Ownership check (21) per submission. A zone with a violation is refused and its violations listed; warnings are only listed. `--allow-violations` merges such a zone anyway and the report says so in a banner.
4. `18_osm_conflicts.py` over the accepted submissions (same object changed by two zones, negative-id collisions). All zones involved in a conflict are refused. Then 21 over all remaining zones together: rows the single runs did not give are listed as cross-zone warnings (for example a node moved by one zone and used by a way changed by another); they do not refuse.
5. `osmium merge-changes` (zone order), `apply-changes` onto the full `data/interim/ring1_roads.osm`, `check-refs -r` against the base (new missing references are an error, exit 70), and a check that the merged file differs from the base exactly in the objects of `merged.osc`.
6. Revert list: objects changed in an older submission and absent from the newest one (back in the base state, for example through Undo).
7. `--netconvert`: network of the base and of the merged file with `--keep-edges.in-geo-boundary` over the bbox of `data/derived/ring1.geojson` plus 0.004 deg (`config/28_merge.yaml`), edges and traffic lights before and after. The base network is reused in the same `<out_dir>` while the base is unchanged.

Exit codes:

| Code | Meaning |
|---|---|
| 0 | all zones merged (warnings are listed, they do not change the exit code; also with `--allow-violations`) |
| 1 | at least one zone refused for violations or conflicts; the other zones were merged |
| 4 | at least one zone refused for meta / base / package mismatch (takes precedence over 1); the others were merged |
| 64 | usage error, or no submission found |
| 70 | a step failed (osmium, netconvert, 21), or the merged file does not match `merged.osc`, or new missing references |

Daily routine (the person who merges, once per working day, after the raters have run `submit_edits.sh`):

1. For each rater's files (`zone_<N>.osc`, `zone_<N>.osc.meta.json`, optionally the record sheet `.xlsx`) in a directory of their own: `scripts/intake_submission.sh <zone> <dir>`. It places the files in `submissions/zone_<N>/<YYYYMMDD>/` (date from `created_utc` in the meta file, else `--date`, else today; the record sheet goes to `records/`) and prints one summary line. Do not copy by hand. See "Intake" below for the refusals.
2. `scripts/verify_inputs.sh`, then `scripts/merge_submissions.sh submissions merged/<date> --netconvert`.
3. Read `MERGE_REPORT.md` top to bottom: refused zones, violations, conflicts, warnings, revert list, edge and traffic light counts before / after.
4. Resolve every refusal (below), ask the raters about every revert, re-run. Keep `merged/<date>` only for the last good run; the merged `.osm` is the base for the network of the day, not a new base for the raters (they keep working on their package).

**Dates are UTC.** The date directory comes from `created_utc` of the meta file, which is UTC; a submission made late in the evening in Poland (UTC+1 / +2) can land in the next day's directory. This is intended: the order of submissions is decided by the directory date and the time, not by the local calendar.

**Replace archive.** `intake_submission.sh --replace` never deletes anything: the replaced `.osc`, its meta file and the records of the day (if any) are copied to `submissions/zone_<N>/<YYYYMMDD>/replaced/<created_utc of the old file>/` (`_2`, `_3` ... if that name exists). The archive is NOT a submission: the merge never merges it. It uses the archived files, together with the older date directories, to build the revert list (objects changed in any earlier submission of the zone but back in the base state in the newest one) and lists them as superseded. So a same-day replace that loses an edit (for example the C5 case) is reported like a revert between days. The merge outputs (`merged.osc`, `ring1_roads_merged.osm`) depend only on the newest submission of each zone, with or without an archive; only the superseded and revert sections of `MERGE_REPORT.md` differ. Keep the archive; do not copy it to the raters.

Intake (`scripts/intake_submission.sh <zone> <dir> [--date YYYYMMDD] [--replace] [--force]`, `SUBMISSIONS_DIR` overrides `submissions`). It checks the file names (`zone_<N>.osc`, `zone_<N>.osc.meta.json`), that the `.osc` contains objects, that the meta `editor_index` is the zone and that the meta `base_sha256` equals `sha256_extract` of the zone's package sidecar. A second submission of the same day normally replaces the first, so different content in an existing date directory needs `--replace` (the old files go to the archive above); the same files again are accepted without change. A submission whose `created_utc` is older than the newest one already present for the zone (an old file sent again) is refused unless `--force`. `created_utc` is written by `submit_edits.sh`; it is informational, the merge ignores it (merge outputs stay byte-identical).

| Intake exit | Meaning and action |
|---|---|
| 0 | placed, or identical files already there |
| 1 | refused: different content on the same day (use `--replace` if the new file is the rater's later submission), or older than the newest present (ask the rater which file is current; `--force` only if intended) |
| 4 | meta says another zone (`editor_index`) or another package (`base_sha256`): ask the rater to submit again from the unchanged package |
| 64 | wrong or missing file names (also: files of another zone), empty `.osc`, invalid XML / JSON, bad `--date` |

What to do for each refusal:

| Report says | Action |
|---|---|
| exit 4, "base sha256 in meta differs" | The rater edited another package or file. Ask for the right file; the rater must `submit_edits.sh` again from the unchanged package. Never edit the meta file by hand. |
| exit 4, "editor index" | The file is in the wrong `zone_<N>` directory, or was submitted with another script. Move it or ask for a new submission. |
| exit 4, "package ... differs from its sidecar" or "full base differs" | Your own copy of the package / `ring1_roads.osm` is wrong. Restore it (`git`/handoff, `scripts/check_setup.sh`); do not merge until it matches. |
| violation (`other_zone`, ...) | Ask the rater to undo the edit on the foreign object and submit again (a cumulative file without it). If the change is needed, give it to the owner zone. `--allow-violations` only for a test or after the team decided to accept the edit; write the decision in `docs/decisions.md`. |
| conflict (same object in two zones) | Two raters changed the same object (whitelisted node, or an ownership table error). Decide which change wins, ask the other rater to undo theirs, submit again. Both zones stay out of the merge until then. |
| negative-id collision | Cannot occur with `submit_edits.sh` (the editor index is the zone number). It means a file was renumbered by hand: ask for a new submission. |
| cross-zone warning | Not a refusal. Check on the map that the two edits fit together; ask both raters if unsure. |
| revert list | Ask the rater whether the object was meant to go back to the base state (Undo can remove an edit silently, section 5 rule 18). If not, the rater redoes it and submits again. |
| superseded | Information only: the older file was replaced by a newer cumulative one. If the newest file is the wrong one (an old file with a newer name), remove that directory and run again. |

## 5. Rules for cleaners

1. Start JOSM only with `scripts/josm_pilot.sh`; open your `zone_N.osm` and `zone_N_reference.osm`, edit a copy.
2. Never use File > Update data or File > Download data. If it happened, throw the file away and start again from the package.
3. Edit only objects owned by your zone (`ownership_*.csv`; `role=owned` areas in the reference layer). Buffer and other-zone objects are read-only.
4. A node owned by another zone is read-only even when it is the end node of your way: do not move, retag or delete it.
5. A spanning way (`spans_zones`) is edited only by its owner (the check shows a warning); others write the needed change to the owner. Exception: a spanning way whose owner basis is `bridge_group` is `ok` for the group owner (rule 6).
6. Bridges: the owner of the bridge group edits all bridge ways of the group; end nodes owned by another zone stay untouched.
7. Whitelisted nodes (`shared_editable_nodes.csv`) may be edited by either listed zone (warning); tell the other zone what you changed.
8. Draw new objects inside your polygon; attach them only to nodes you own (or whitelisted ones).
9. Delete a way and the nodes that no other way uses; never delete a node that a way or relation still uses.
10. Move a node used by a way of another zone by at most 3 m (config `move_threshold_m`).
11. When you change `lanes`, check `lanes:forward`, `lanes:backward` and `lanes:both_ways`: they override `lanes` in `netconvert` and must add up to it.
12. Do not edit relations (turn restrictions) unless you own them; do not touch ids or versions. Exception: the membership changes JOSM makes by itself when you split or combine a way of yours are `derived_edit`s and are ok (section 5b); any tag change on a foreign relation is a violation.
13. Do not upload anything to openstreetmap.org.
14. Run `scripts/submit_edits.sh <zone> zone_<N>_edit.osm --dry-run` (it runs `19_osm_submit.py` and `21_ownership_check.py`) before sending; fix exit codes 1, 3 and 4. Warnings (exit 2) need a short note to the merger.
15. Warnings for spanning ways (exit code 2) are expected and are not errors; when splitting a spanning way, write the split point in the notes.
16. After Split Way, review the tags copied to both parts (for example `length`: in the test `length=266` stayed on both parts of a 203 m way).
17. JOSM updates relation memberships silently when you split or combine ways (no dialog about relations). The check may therefore list relation changes (`derived_edit`); they are expected when the split or combined way is yours.
18. Undo can silently remove an edit (C5 was lost this way). At the end of every session compare the "changed objects" count of `submit_edits.sh --dry-run` with your own notes.
19. The layer name keeps its asterisk after Save As, and the exit dialog offers Upload: choose "Exit now". Never upload.

## 6. Real JOSM file format (JOSM 19613, verified on the full files)

- Single-quoted attributes (`action='modify'`); header `<osm version='0.6' generator='JOSM'>`, no `<bounds>`, no `upload`. Parse with a real XML parser, never with regular expressions on quotes.
- Every object has `visible='true'`; attribute order `id, action, timestamp, visible, version, lat, lon`. Tags are written in alphabetical order (the packages already are).
- New objects: negative id, `action='modify'` (never `create`), no `version`, no `timestamp`. Ids are not dense, not renumbered on save / reload, and differ between sessions (they do not restart at -1 after a restart). Two editors can use the same negative id: use `--no-renumber` to see it with `18_osm_conflicts.py`; the per-editor renumbering keeps them apart.
- Existing objects keep `version` and `timestamp`; changed ones get `action='modify'`. Moving a node marks only that node (ways and relations that use it are not marked).
- Deleted objects stay in the file with `action='delete'`. A deleted way keeps its tags but has no `<nd>` (a way without tags and `<nd>` is written as `<way ...>` newline `</way>`); a deleted node keeps coordinates, version and timestamp. File counts = package + new objects. Nodes of a deleted way stay.
- Untouched objects are canonically identical to the package (0 of 10 858 / 10 645 differ). Moved nodes have up to 11 decimals; `osmium` stores 7 (<= 1 cm).
- Re-saving a reloaded file gives an identical file.
- `osmium derive-changes` writes new objects inside `<modify>` (not `<create>`), and deleted objects without `<nd>` and tags; `21_ownership_check.py` takes the node list of a deleted way from the BASE package.
- Contamination (any of: uid / user / changeset that the package object lacks; `visible='false'`; version different from the base; positive-id object not in the base) means `File > Update data` or `Download` was used. The user name is never used for detection.

## 6b. Way and relation operations in the real file (JOSM 19613, zone 3 test `editedC.osm`, report `reports/09b_josm_operations.md`)

- **Split Way:** one part keeps the old id (`action='modify'`, same version and timestamp, shorter node list); the other part is a new way (negative id, `action='modify'`, no version / timestamp) with ALL tags copied, also stale ones such as `length`. In both tests the longer part kept the old id; that is two cases, not a rule. The part that touches the via node of a restriction became the new way and replaced the old way in the relation: JOSM edits the relation silently (relation `35954`: `action='modify'`, version kept, member `from` now the new way, members written via, to, from instead of from, via, to).
- **Combine Ways:** the survivor keeps its id (`modify`, merged node list); the other way is `action='delete'` with its tags but no `<nd>`.
- **Merge Nodes:** the survivor node is unchanged (not marked); the other node is `action='delete'`; only the ways whose node list changed are `modify` (a way that already contained the survivor is not marked).
- **Relations:** a new relation has a negative id, `action='modify'`, no version, members in arbitrary order (`to, via, from`) and alphabetically sorted tags; a changed relation is `action='modify'` with version and timestamp kept; a deleted relation keeps id, version, timestamp and tags but has NO members (the members are taken from the BASE when needed). Member order is not preserved, so members of `type=restriction` relations are compared as a multiset (role, type, ref) in `osm_io.canon`; for other relation types the order stays significant.
- **Renumbering** (`19_osm_submit.py`) rewrites every negative `ref` in `nd` and `member`, also the `member ref` of EXISTING relations that point to new objects (`35954`: `-744` -> `1000000000744`) and of new relations. No `action='create'` appears anywhere; new objects are recognised by their negative id (`osm_io.is_new`).
- **`osmium derive-changes`/`apply-changes`:** the full chain on `editedC.osm` gives exactly the 18 edited objects when applied to the full base (0 differences; versions +1; `check-refs` unchanged).

## 7. Known limitations

- Plain `osmium derive-changes` silently ignores edits that keep the `version` (all JOSM edits), `action="delete"` objects, and duplicates of negative ids across editors. Use `19_osm_submit.py` and `18_osm_conflicts.py`; never run `derive-changes` by hand.
- `18_osm_conflicts.py` sees only identical object ids. Edits of different objects that interact are reported by `21_ownership_check.py` as warnings (a node moved or deleted by one editor and used by a way changed by another, or a member of a relation), not as conflicts.
- The 3 m move threshold is strict (`>`): a node used by a way of another zone moved by 2.98 m does not fire it (it is still a violation when the node is owned by another zone).
- Edits of `lanes=` have no effect on ways that have `lanes:forward` / `lanes:backward`; change those too.
- Netconvert names edges after way ids; new ways get ids `(index+1) * 10^12 + n`, so the edges are `10000...03` and `-10000...03` (reverse). Keep this in mind when looking for new roads in the network.
- A valid sidecar of the wrong package is not detected by the checksum; the contamination rule "positive-id object not in the base" refuses it (exit 3).

## 5b. Owned extent and inherited connections (`21_ownership_check.py`)

- **Owned extent** of a zone = zone polygon UNION buffers (`owned_buffer_m`, 10 m) of its owned ways that lie (partly) outside the polygon (the ways with `role=owned_outside_polygon` in `zone_N_reference.osm`; their geometry is taken from the package). A new node inside the extent is `ok`; outside it is a violation (`new_outside_polygon`). Splitting such a way is `ok` when all existing nodes of the new way are owned.
- **Derived edits (`derived_edit`, ok):** (1) a relation modified only by replacing a member way with the parts created from it by Split Way, or by the way that survives a Combine Ways, is ok when the editor owns the replaced way, whoever owns the relation (reason "derived from split/combine of <way>"); a tag change or any other member change follows the normal owner rule (a foreign relation is then a violation). (2) A way modified only because Merge Nodes replaced a deleted node by the survivor is ok when the editor owns the way and the deleted node; a modified foreign way stays a violation.
- **Invalid and orphan objects:** a new way with fewer than 2 nodes is a violation (`invalid_object`, e.g. the two one-node ways of a slipped copy/paste); a new untagged node used by no way and no relation is a warning (`orphan`).
- **Bridge groups:** a spanning way with owner basis `bridge_group` edited by the group owner is ok (`bridge_group_owner`); other spanning ways stay warnings.
- **Inherited connection:** a new way may contain an existing node owned by another zone when the node was used in the base by an owned way that the same change set deletes, or whose node list no longer contains it (split, replacement, redraw); `ok`, reason says "inherited". A modified way that still contains the node (tag edit, other nodes changed) does not make it inherited. A new way attached to a foreign node that no deleted or shortened owned way released stays a violation (`new_way_other_zone`).

## 6. Ownership rules

Tables: `data/derived/zones_v02/ownership_{ways,nodes,relations}.csv` (task 03b'); rules in `reports/08_pilot_zones.md`. Each object has one owner zone; the owner is the only editor.
- **Ways:** the owner is the zone with the largest share of the way's length (ties: lower zone). The owner edits geometry and tags. A spanning way (`spans_zones`) is still edited only by its owner; the other zone reports needed changes in the notes.
- **Nodes:** nodes of a junction cluster or site belong to its zone; other nodes to the owner of the longest way that uses them. A node owned by another zone is read-only: do not move, delete or retag it, also when it is an end node of a way you own.
- **Relations (turn restrictions):** owned by the zone of the via member, without via (or with an unowned via) by the zone of the from way.
- **Bridge groups:** one owner per group; the owner edits all bridge ways of the group. End nodes owned by another zone (`other_zone_end_nodes`, `zone_<N>_bridge_ways.csv`) are read-only.
- **Seam edges** are owned by the zone with the larger sum of `max_degree` of the end clusters (ties: lower zone); `zone_<N>_seams.csv` has `owner_zone`, `owned_by_this_zone` and `pilot_pair_seam`. Edges owned by the neighbour are read-only context.
- **Whitelist:** `data/derived/zones_v02/shared_editable_nodes.csv` lists nodes that belong to a site in one zone and to a junction cluster in another; `src/21_ownership_check.py` accepts an edit by either listed zone with a warning.
