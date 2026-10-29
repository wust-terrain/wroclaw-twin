# Report 09: editing workflow on real JOSM files (task 04r)

Produced by `src/24_real_workflow.py` (config `config/24_real_josm.yaml`, helpers `src/20_josm_file_facts.py`, `src/21_ownership_check.py`, `src/19_osm_submit.py`, `src/18_osm_conflicts.py`, `src/osm_io.py`). Inputs verified with `scripts/verify_inputs.sh` and the sha256 of both v1 packages; `data/raw/` and `legacy_v1/` untouched; nothing committed. Tools: osmium 1.16.0, netconvert 1.28.0, JOSM 19613 files.

## Summary

| Item | Result | Status |
|---|---|---|
| 1 file facts | see table | ok |
| 2 workflow control table | all ok | ok |
| 3 planted cases | all as expected | ok |
| 4 contamination | exit 3, osc written False | ok |
| 5/6 safeguards and synthetic | 22/22 pass | ok |

## 1. Facts about the JOSM file format (full files)

Parsed with `xml.etree`; the quote-style row is a plain substring count on the raw text. Package = the v1 package the editor opened (BASE). Columns A, B are the clean files; `B_update` is the contaminated one (shown only where it differs).

| Fact | A (zone 3) | B (zone 4) | B_update | Verdict |
|---|---|---|---|---|
| attributes single-quoted (package: double-quoted) | 98194 single / 0 double | 92899 single / 0 double | 124965 single / 0 double | **holds** |
| new objects: negative id, action='modify', no version | 3 new, ids [-28583, -28582, -1066], action=modify 3, with version 0 | 3 new, ids [-26143, -26142, -626], action=modify 3, with version 0 | 4 new, ids [-30218, -30216, -30215, -1372], action=modify 4, with version 0 | **holds** |
| existing objects keep version and timestamp | 10865/10865 version, 10865/10865 timestamp equal | 10651/10651 version, 10651/10651 timestamp equal | 10592/10651 version, 10592/10651 timestamp equal | **holds** |
| a moved node marks only that node | 3 moved nodes with 8 ways/relations using them; 0 of those marked | 1 moved nodes with 1 ways/relations using them; 0 of those marked | 1 moved nodes with 1 ways/relations using them; 0 of those marked | **holds** |
| a deleted way keeps its tags and has no `<nd>` | 1 deleted ways: tags kept 1, without nd 1 | 1 deleted ways: tags kept 1, without nd 1 | 4 deleted ways: tags kept 1, without nd 4 (the 6 server-deleted objects have no tags) | **holds** |
| a deleted node keeps its coordinates | 1 deleted nodes: coordinates kept 1, version kept 1 | 1 deleted nodes: coordinates kept 1, version kept 1 | 4 deleted nodes: coordinates kept 1, version kept 1 | **holds** |
| deleted objects stay in the file (file = package + new) | file nodes/ways/relations 8427/2366/75 = package 8425/2365/75 + new 2/1/0 | file nodes/ways/relations 8285/2305/64 = package 8283/2304/64 + new 2/1/0 | file nodes/ways/relations 8296/2305/64 = package 8283/2304/64 + new 3/1/0 (10 extra existing nodes) | **holds** |
| negative ids are not dense | [-1066, -28582, -28583] | [-626, -26142, -26143] | [-1372, -30215, -30216, -30218] | **holds** |
| negative ids differ between sessions | A vs B overlap [] | B vs B_update overlap [] | A vs B_update overlap [] | **holds** |
| editedA_resaved.osm identical to editedA.osm | sha256 equal: True, bytes equal: True |  |  | **holds** |

Canonical comparison with the package (tags as dict, nd / member order significant, coordinates rounded to 7 decimals):

| Measure | A | B | B_update |
|---|---|---|---|
| untouched objects whose canonical content differs from the package (expected 0) | 0 of 10858 | 0 of 10645 | 49 of 10639 (server drift, see item 4) |
| objects whose serialisation differs only in tag order | 0 | 0 | 0 |
| untouched objects with tags in alphabetical order in the file | 10858/10858 | 10645/10645 | 10639/10639 |
| objects whose serialisation differs only in quotes | all (98194 single-quoted attributes vs 87303 double in the package) | all | all |
| untouched node coordinates with 6 / 7 decimals | {'6': 82, '7': 8339} | {'6': 81, '7': 8200} | {'6': 80, '7': 8198} |
| moved node coordinates: decimals | [11] | [11] | - |
| modified existing objects with unchanged version | 5/5 | 4/4 | 4/4 |

Attributes JOSM adds or drops compared with the osmium-written package:

| Element | added by JOSM (clean file A) | dropped |
|---|---|---|
| node | action, visible | - |
| way | action, visible | - |
| relation | visible | - |

- `generator`: package `osmium/1.16.0`, JOSM file `JOSM`; `version='0.6'` both. No `<bounds>` element (children of `<osm>` other than objects: file [], package []). No `upload` attribute (0 in A, 0 in B). `visible='true'` on every object (A: 10868 of 10868). Clean files: uid/user/changeset = 0/0/0 (A), 0/0/0 (B).
- Attribute order in a node: `id, action, timestamp, visible, version, lat, lon` (package: `id, version, timestamp, lat, lon`). Nodes without children end with ` />`; a way or relation without children (a deleted way that had no tags) is written as `<way ...>` + newline + `</way>`. Special characters in values: `&quot;`, `&apos;`, `&amp;`.
- `src/osm_io.py:write_josm` reproduces `editedA.osm`, `editedB.osm` and `editedB_with_update.osm` byte for byte (checked in this run), so the synthetic files of item 6 have the real format.

## 2. Full workflow on A and B (real format)

Control table:

| Check | Expected | Actual | Status |
|---|---|---|---|
| 19_osm_submit.py A | exit 0, .osc written | exit 0, prepare {'bumped': 5, 'deleted_dropped': 2, 'new': 3} | ok |
| 19_osm_submit.py B | exit 0, .osc written | exit 0, prepare {'bumped': 4, 'deleted_dropped': 2, 'new': 3} | ok |
| 18_osm_conflicts.py A B | exit 0, 0 conflicts, 0 collisions | exit 0: conflicts: 0, negative-id collisions: 0 | ok |
| 21_ownership_check.py A B | exit 1 (planted violations A6, A7, B6) | exit 1: ok 15, warning 3, violation 4 (of which unowned 0) | ok |
| osmium merge-changes / apply-changes | exit 0 / 0 | exit 0 / 0 | ok |
| osmium check-refs: merged = base | same 'missing' lines as the base | identical | ok |
| merged objects = base + editors' changes (canonical) | 0 missing, 0 extra, 0 differing | 0 missing, 0 extra, 0 differing | ok |
| objects changed vs base (existing) | 9 (modified by editors) | 9 | ok |
| created / deleted objects | 6 / 4 | 6 / 4 | ok |
| version of modified objects = base + 1 | 9 | 9 | ok |
| v1 package A vs full base (10865 objects) | 0 objects differ (content, version) | 0 differ | ok |
| v1 package B vs full base (10651 objects) | 0 objects differ (content, version) | 0 differ | ok |
| netconvert base (bbox 17.0330,51.0964,17.0579,51.1177) | Success. | Success., 24544 edges | ok |
| netconvert merged (bbox 17.0330,51.0964,17.0579,51.1177) | Success. | Success., 24546 edges | ok |

Per editor (from the JOSM files): A {'create': 3, 'modify': 5, 'delete': 2}, B {'create': 3, 'modify': 4, 'delete': 2}. `modify` counts objects whose canonical content really changed; `modify_noop` would be marked `action='modify'` without a change.

A change derived against a zone package and applied to the full base: **gives exactly the objects the editors changed**. Compared 87746 objects of the expected result (full base + changes) with the 87746 objects of `merged.osm`: missing 0, extra 0, differing 0. The 11-decimal coordinates written by JOSM are stored by osmium with 7 decimals; the largest displacement caused by this is 0.56 cm.

netconvert (`--keep-edges.in-geo-boundary 17.0330,51.0964,17.0579,51.1177`, defaults otherwise, as in docs/SETUP.md 6b) on the full base and on the merged file; effect on the edges:

| Case | Object | Base net | Merged net | Expected | Status |
|---|---|---|---|---|---|
| A1 | way 27717899 | 10 edges, speeds [13.89] | 10 edges, speeds [8.33] | 8.33 | ok |
| A2 | way 421983573 | 4 edges, speeds [13.89] | 4 edges, speeds [11.11] | 11.11 | ok |
| B1 | way 16313072 | 2 edges, speeds [22.22] | 2 edges, speeds [11.11] | 11.11 | ok |
| B2 | way 506664739 | 6 edges, speeds [13.89] | 6 edges, speeds [11.11] | 11.11 | ok |
| A4 | new way 1000000001066 | 0 edges | 2 edges ['-1000000001066', '1000000001066'] | >= 1 edge | ok |
| B4 | new way 2000000000626 | 0 edges | 2 edges ['-2000000000626', '2000000000626'] | >= 1 edge | ok |
| A5 | deleted way 676874278 | 2 edges | 0 edges | 0 edges after | ok |
| B5 | deleted way 1509285303 | 1 edges | 0 edges | 0 edges after | ok |

## 3. Planted cases (classified by the ownership tables)

Owner and `spans_zones` come from `ownership_{ways,nodes}.csv`; the classification is the output of `src/21_ownership_check.py` (`ok` / `warning` / `violation`).

| Case | Object | Owner (table) | Change | Expected | Actual | Categories / notes | Result |
|---|---|---|---|---|---|---|---|
| A1 | way 27717899 | zone 3, spans zones | maxspeed 50->30 | warning | warning | spanning_owner_edit | pass |
| A2 | way 421983573 | zone 3 | maxspeed=40 | ok | ok | own | pass |
| A3 | node 5931056508 | zone 3 | moved 2.04 m | ok | ok | own; moved 2.038 m (JOSM file: 2.04 m); rule (c) fired: False | pass |
| A4 | new way -1066 (osc 1000000001066) from node 3170927238 | anchor node: zone 3 | new way anchored at node | ok | ok | new_in_polygon, new_way_own | pass |
| A5 | way 676874278 + node 6338339587 | way: zone 3, node: zone 3 | deleted way and node | ok | ok | own | pass |
| A6 | node 165109460 | zone 4 | moved 5.01 m (owner zone 4) | violation | violation | move_exceeds_threshold, other_zone; moved 5.023 m (JOSM file: 5.03 m); rule (c) fired: True | pass |
| A7 | node 11811708916 | zone 2 | moved 2.97 m (owner zone 2) | violation | violation | other_zone; moved 2.978 m (JOSM file: 2.98 m); rule (c) fired: False | pass |
| B1 | way 16313072 | zone 4 | maxspeed=40 | ok | ok | own | pass |
| B2 | way 506664739 | zone 4 | maxspeed=40 | ok | ok | own | pass |
| B3 | node 4954533516 | zone 4 | moved 2.38 m | ok | ok | own; moved 2.39 m (JOSM file: 2.39 m); rule (c) fired: False | pass |
| B4 | new way -626 (osc 2000000000626) from node 3170927244 | anchor node: zone 4 | new way anchored at node | ok | ok | new_in_polygon, new_way_own | pass |
| B5 | way 1509285303 + node 13796870222 | way: zone 4, node: zone 4 | deleted way and node | ok | ok | own | pass |
| B6 | way 187980700 | zone 10 | note=test | violation | violation | other_zone; owner table says zone 10, not zone 4, so B6 tests a violation (owned by another zone) | pass |

Semantic warnings (rule d), listed from `21_ownership_check.py`:

| Case | Expected | Actual | Result |
|---|---|---|---|
| B1 vs A6 (cross-editor) | warning: node 165109460 moved by A is used by way 16313072 changed by B | node moved 5.02 m by A is used by way 16313072 changed by B (modify) | pass |
| relation 2532024 (turn restriction, via node 165109460) | warning: moved node is a member of the relation | node moved 5.02 m by A is a member of relation 2532024 (owner zone 4) | pass |

Owner of relation 2532024 by the table: zone 4 (via node 165109460); the relation itself was not edited and is not marked in the JOSM file (confirmed).

All rows of `21_ownership_check.py` for A and B (full output):

```
editor object                     op      detail                                       result    category / reason
A      node 165109460             modify  moved 5.02 m                                 violation move_exceeds_threshold: moved 5.02 m > 3.0 m and used by ways of other zones: [16313072, 187980674, 295082888]
A      node 165109460             modify  moved 5.02 m                                 violation other_zone: owned by zone 4
A      node 165109460             modify  moved 5.02 m                                 warning   cross_editor_way: node moved 5.02 m by A is used by way 16313072 changed by B (modify)
A      node 165109460             modify  moved 5.02 m                                 warning   relation_member: node moved 5.02 m by A is a member of relation 2532024 (owner zone 4)
A      node 5931056508            modify  moved 2.04 m                                 ok        own: owned by zone 3
A      node 6338339587            delete  delete                                       ok        own: owned by zone 3
A      node 11811708916           modify  moved 2.98 m                                 violation other_zone: owned by zone 2
A      node 1000000028582         create  new node                                     ok        new_in_polygon: inside the zone polygon
A      node 1000000028583         create  new node                                     ok        new_in_polygon: inside the zone polygon
A      way 27717899               modify  modify tags                                  warning   spanning_owner_edit: spanning way, edited by its owner
A      way 421983573              modify  modify tags                                  ok        own: owned by zone 3
A      way 676874278              delete  delete way (3 nodes in BASE, 1 deleted too)  ok        own: owned by zone 3
A      way 1000000001066          create  new way, 3 nodes                             ok        new_way_own: new nodes inside the polygon, existing nodes own
B      node 4954533516            modify  moved 2.39 m                                 ok        own: owned by zone 4
B      node 13796870222           delete  delete                                       ok        own: owned by zone 4
B      node 2000000026142         create  new node                                     ok        new_in_polygon: inside the zone polygon
B      node 2000000026143         create  new node                                     ok        new_in_polygon: inside the zone polygon
B      way 16313072               modify  modify tags                                  ok        own: owned by zone 4
B      way 187980700              modify  modify tags                                  violation other_zone: owned by zone 10
B      way 506664739              modify  modify tags                                  ok        own: owned by zone 4
B      way 1509285303             delete  delete way (2 nodes in BASE, 1 deleted too)  ok        own: owned by zone 4
B      way 2000000000626          create  new way, 3 nodes                             ok        new_way_own: new nodes inside the polygon, existing nodes own
ok 15, warning 3, violation 4 (of which unowned 0)
```

## 4. Contaminated file `editedB_with_update.osm`

`19_osm_submit.py` on this file: **exit code 3** (required: 3), `.osc` written: **False** (required: no). Offenders by rule (the user name is not used):

| Rule | Objects |
|---|---|
| uid / user / changeset that the package object lacks | 10658 |
| visible='false' | 6: node 7134174248, node 9199480306, node 14053613504, way 784024859, way 784024860, way 996255004 |
| existing object with a version different from the base | 59 (32 nodes, 27 ways) |
| positive-id object not in the base | 10: node 7323602633, node 14316618422, node 14320697813, node 14320697822, node 14320697825, node 14320697826, node 14320697827, node 14320697852, node 14320699368, node 14320699369 |

The six objects the brief expects (deleted upstream on 26-27 Oct 2026, after the snapshot of 23 Oct):

| Object | In file | Attributes | Flagged by | Result |
|---|---|---|---|---|
| node 7134174248 | present | action=delete, visible=false, version 2 (package 1), timestamp 2026-10-26T10:59:37Z | server_metadata, invisible, version_differs | pass |
| node 9199480306 | present | action=delete, visible=false, version 3 (package 2), timestamp 2026-10-27T10:58:04Z | server_metadata, invisible, version_differs | pass |
| node 14053613504 | present | action=delete, visible=false, version 2 (package 1), timestamp 2026-10-27T10:58:04Z | server_metadata, invisible, version_differs | pass |
| way 784024859 | present | action=delete, visible=false, version 2 (package 1), timestamp 2026-10-26T10:59:37Z | server_metadata, invisible, version_differs | pass |
| way 784024860 | present | action=delete, visible=false, version 2 (package 1), timestamp 2026-10-26T10:59:37Z | server_metadata, invisible, version_differs | pass |
| way 996255004 | present | action=delete, visible=false, version 3 (package 2), timestamp 2026-10-27T10:58:04Z | server_metadata, invisible, version_differs | pass |

Differences from the package apart from the editor's own edits (B1-B6, found by comparing with the clean `editedB.osm`):

| Measure | Count / ids |
|---|---|
| objects of the package missing from the file | 0 |
| existing objects (not edited by the user) with a different version | 59 (32 nodes, 27 ways, 0 relations); of these deleted upstream (visible='false'): 6 |
| same version but different canonical content | 0 |
| objects that differ from the package apart from B1-B6 (version or content) | 59 |
| objects with server metadata but identical version and content (refreshed only) | 10586 |
| objects with uid / user / changeset in total | 10658 |
| extra positive-id nodes (not in the package) | 10: 7323602633, 14316618422, 14320697813, 14320697822, 14320697825, 14320697826, 14320697827, 14320697852, 14320699368, 14320699369 |
| ... of these in the full base `ring1_roads.osm` (snapshot of 23 Oct) | 0 of 10 |
| ... of these used by a way in the file | 10: 7323602633 -> ways [315188209]; 14316618422 -> ways [1497857611]; 14320697813 -> ways [416479039]; 14320697822 -> ways [447256087]; 14320697825 -> ways [447256094]; 14320697826 -> ways [447256094]; 14320697827 -> ways [447256094]; 14320697852 -> ways [447256083]; 14320699368 -> ways [784024858]; 14320699369 -> ways [763480493] |

First lines of the refusal (stderr of `19_osm_submit.py`):
```
ERROR contaminated input (data from the OSM server, or another base): {'server_metadata': 10658, 'invisible': 6, 'version_differs': 59, 'not_in_base': 10}
ERROR   server_metadata: node 158719881 (action=None)
ERROR   server_metadata: node 158719882 (action=None)
  ...
```

## 5. Safeguards and 6. Synthetic coverage (real format)

Synthetic files are copies of `editedA.osm` / `editedB.osm` with one scripted edit each, written by `osm_io.write_josm` (byte-identical to JOSM output for the real files). Judged on the rows of the added object only; the real edits stay in the file. Objects were picked deterministically from the ownership tables: unowned_way = 301893751, dangling_node = 158719891, shared_node = 165109578, own_only_node = 158719888, other_zone_node = 158719907, white_node = 173178354.

| Case | Edit | Expected | Actual | Result |
|---|---|---|---|---|
| S1 | edit of unowned way 301893751 (owner 0, note=test) | violation / unowned | violation / unowned | pass |
| S2 | new node outside the zone polygon | violation / new_outside_polygon | violation / new_outside_polygon | pass |
| S3 | delete node 158719891 that a remaining way (114959446) still uses | violation / dangling_reference | violation / dangling_reference | pass |
| S3b | osmium check-refs on the result of S3 (why the rule exists) | missing nodes in ways | Nodes in ways missing: 1 | pass |
| S4 | new way anchored at node 158719907 (owner zone 4) | violation / new_way_other_zone | violation / new_way_other_zone | pass |
| S8a | own node 165109578 used by a way of another zone, moved 5 m | violation / move_exceeds_threshold | violation / move_exceeds_threshold; warning / relation_member | pass |
| S8b | same node 165109578 moved 2 m (below the 3 m threshold) | ok / own | ok / own; warning / relation_member | pass |
| S8c | own node 158719888 used only by own ways, moved 5 m | ok / own | ok / own | pass |
| S9 | tag edit of whitelisted node 173178354 (zones [3, 10], owner 10) | warning / whitelisted | warning / whitelisted | pass |
| S5a | both editors use the same negative ids (-1066, -28582, -28583); 18 before renumbering | exit 1, 3 COLLISION lines | exit 1, 3 COLLISION lines | pass |
| S5b | same ids, after renumbering (editor 0 / 1): 18 and merge | 18 exit 0; 6 new objects (2 ways + 4 nodes) with distinct ids | 18 exit 0; 6 new objects (2 ways, 4 nodes) | pass |
| S5c | same ids WITHOUT renumbering: merge-changes + apply-changes (what 18 prevents) | only 3 new objects survive (silent loss) | 3 new objects in the result | pass |
| S6a | base differs from the sidecar sha256 (one extra byte) | exit 4, no .osc | exit 4, .osc: False | pass |
| S6b | base without sidecar and without --base-sha256 | exit 4 | exit 4 | pass |
| S6c | explicit wrong --base-sha256 | exit 4 | exit 4 | pass |
| S6d | zone 3 edits submitted against the zone 4 package (its sidecar matches) | refused (exit 3: positive ids not in the base) | exit 3 | pass |
| S7a | uid attribute on an untouched node | exit 3, no .osc | exit 3, .osc: False | pass |
| S7b | visible='false' on an untouched way | exit 3, no .osc | exit 3, .osc: False | pass |
| S7c | version of an untouched node differs from the base | exit 3, no .osc | exit 3, .osc: False | pass |
| S7d | positive-id node that is not in the base | exit 3, no .osc | exit 3, .osc: False | pass |
| S10 | the submission records the base sha256 (OUT.osc.meta.json) | 92bff0233ecbb715939af219445f370cb69a78616c6df3d98bf9d67048dd429c | 92bff0233ecbb715939af219445f370cb69a78616c6df3d98bf9d67048dd429c | pass |
| S11 | 21_ownership_check.py with A.osc and the zone 4 package as base | exit 4 | exit 4 | pass |

Exit codes (all scripts):

| Code | Meaning | Script |
|---|---|---|
| 0 | ok | all |
| 1 | violation or conflict (ownership violation; same object / negative id changed by several editors) | 21, 18 |
| 2 | warnings only | 21 |
| 3 | contaminated input, nothing written | 19 |
| 4 | base mismatch / base not verifiable / .osc from another base | 19, 21 |

## 7. What broke in the scripts and what was changed

Nothing in the quote style, deletions without `<nd>`, `action='modify'` on new objects or the alphabetical tag order broke `18_osm_conflicts.py` or `19_osm_submit.py`: they parse with `xml.etree`, compare canonical signatures (tags sorted, `nd` order, 7-decimal coordinates) and `osmium sort` / `derive-changes` accept the JOSM attributes (`visible`, `action`). The real defect was missing guards.

| Check | Expected | Actual | Status |
|---|---|---|---|
| 04s `19_osm_submit.py` on editedA.osm | unchanged result | exit 0; .osc byte-identical to the new one: True | ok |
| 04s `19_osm_submit.py` on editedB.osm | unchanged result | exit 0; .osc byte-identical to the new one: True | ok |
| 04s `19_osm_submit.py` on editedB_with_update.osm | must refuse | exit 0, .osc with 79 objects written (bumped versions of refreshed objects, deletes of server-deleted objects) | ACCEPTED (defect) |
| osmium output for new objects | `<create>` | 0 objects in `<create>`, 3 new objects inside `<modify>` (no version); `osmium apply-changes` accepts them | info |
| osmium output for deleted objects | with `<nd>` / tags | 2 deleted objects, children: 0 (osmium writes id, version, timestamp only) | info |

Changes made:

- `src/19_osm_submit.py`: refuses a base whose sha256 differs from the sidecar `sha256_extract` (or an explicit `--base-sha256`), or that cannot be verified (exit 4); refuses contaminated input by the four rules of item 4 (exit 3, no `.osc`); the changed-object test now uses `osm_io.canon`; writes `OUT.osc.meta.json` (base and edited sha256, editor, shift, prepare counts).
- `src/osm_io.py` (new, shared helper): parsing, canonical content, `write_josm` (JOSM-format writer used for the synthetic files).
- `src/21_ownership_check.py` (new): ownership classification, rules (b), (c), (d), exit codes 0/1/2/4.
- `src/18_osm_conflicts.py`: unchanged. It reports a negative-id collision only on `.osc` files made with `--no-renumber` (after renumbering the id blocks of the editors cannot collide).
- `src/20_josm_file_facts.py`, `src/24_real_workflow.py`, `config/21_ownership_check.yaml`, `config/24_real_josm.yaml`, `scripts/josm_pilot.sh`: new.

