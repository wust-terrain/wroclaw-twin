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
| 2 | warnings only | 21 |
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

## 4. Steps for the person who merges

```bash
uv run python src/18_osm_conflicts.py A=submissions/A.osc B=submissions/B.osc ...   # exit 1 = stop, resolve first
uv run python src/21_ownership_check.py --editor A 3 A.osc zone_3.osm --editor B 4 B.osc zone_4.osm   # all editors together (cross-editor warnings)
osmium merge-changes submissions/*.osc -o merged.osc --overwrite
osmium apply-changes data/interim/ring1_roads.osm merged.osc -o merged.osm --overwrite
osmium check-refs -r merged.osm        # compare with the same command on the base: no new "missing"
netconvert --osm-files merged.osm -o merged.net.xml ...                          # options as in docs/SETUP.md 6b
```

Change files derived against a zone package apply to the full base and give exactly the objects the editors changed (tested: 87 746 objects compared, 0 differences; the v1 packages equal the full base in content and version). Do **not** derive against the full base: every object outside the zone would become a `<delete>`.

## 5. Rules for cleaners

1. Start JOSM only with `scripts/josm_pilot.sh`; open your `zone_N.osm` and `zone_N_reference.osm`, edit a copy.
2. Never use File > Update data or File > Download data. If it happened, throw the file away and start again from the package.
3. Edit only objects owned by your zone (`ownership_*.csv`; `role=owned` areas in the reference layer). Buffer and other-zone objects are read-only.
4. A node owned by another zone is read-only even when it is the end node of your way: do not move, retag or delete it.
5. A spanning way (`spans_zones`) is edited only by its owner (the check shows a warning); others write the needed change to the owner.
6. Bridges: the owner of the bridge group edits all bridge ways of the group; end nodes owned by another zone stay untouched.
7. Whitelisted nodes (`shared_editable_nodes.csv`) may be edited by either listed zone (warning); tell the other zone what you changed.
8. Draw new objects inside your polygon; attach them only to nodes you own (or whitelisted ones).
9. Delete a way and the nodes that no other way uses; never delete a node that a way or relation still uses.
10. Move a node used by a way of another zone by at most 3 m (config `move_threshold_m`).
11. When you change `lanes`, check `lanes:forward`, `lanes:backward` and `lanes:both_ways`: they override `lanes` in `netconvert` and must add up to it.
12. Do not edit relations (turn restrictions) unless you own them; do not touch ids or versions.
13. Do not upload anything to openstreetmap.org.
14. Run `19_osm_submit.py` and `21_ownership_check.py` before sending; fix exit codes 1, 3 and 4. Warnings (exit 2) need a short note to the merger.

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

## 7. Known limitations

- Plain `osmium derive-changes` silently ignores edits that keep the `version` (all JOSM edits), `action="delete"` objects, and duplicates of negative ids across editors. Use `19_osm_submit.py` and `18_osm_conflicts.py`; never run `derive-changes` by hand.
- `18_osm_conflicts.py` sees only identical object ids. Edits of different objects that interact are reported by `21_ownership_check.py` as warnings (a node moved or deleted by one editor and used by a way changed by another, or a member of a relation), not as conflicts.
- The 3 m move threshold is strict (`>`): a node used by a way of another zone moved by 2.98 m does not fire it (it is still a violation when the node is owned by another zone).
- Edits of `lanes=` have no effect on ways that have `lanes:forward` / `lanes:backward`; change those too.
- Netconvert names edges after way ids; new ways get ids `(index+1) * 10^12 + n`, so the edges are `10000...03` and `-10000...03` (reverse). Keep this in mind when looking for new roads in the network.
- A valid sidecar of the wrong package is not detected by the checksum; the contamination rule "positive-id object not in the base" refuses it (exit 3).

## 6. Ownership rules

Tables: `data/derived/zones_v02/ownership_{ways,nodes,relations}.csv` (task 03b'); rules in `reports/08_pilot_zones.md`. Each object has one owner zone; the owner is the only editor.
- **Ways:** the owner is the zone with the largest share of the way's length (ties: lower zone). The owner edits geometry and tags. A spanning way (`spans_zones`) is still edited only by its owner; the other zone reports needed changes in the notes.
- **Nodes:** nodes of a junction cluster or site belong to its zone; other nodes to the owner of the longest way that uses them. A node owned by another zone is read-only: do not move, delete or retag it, also when it is an end node of a way you own.
- **Relations (turn restrictions):** owned by the zone of the via member, without via (or with an unowned via) by the zone of the from way.
- **Bridge groups:** one owner per group; the owner edits all bridge ways of the group. End nodes owned by another zone (`other_zone_end_nodes`, `zone_<N>_bridge_ways.csv`) are read-only.
- **Seam edges** are owned by the zone with the larger sum of `max_degree` of the end clusters (ties: lower zone); `zone_<N>_seams.csv` has `owner_zone`, `owned_by_this_zone` and `pilot_pair_seam`. Edges owned by the neighbour are read-only context.
- **Whitelist:** `data/derived/zones_v02/shared_editable_nodes.csv` lists nodes that belong to a site in one zone and to a junction cluster in another; `src/21_ownership_check.py` accepts an edit by either listed zone with a warning.
