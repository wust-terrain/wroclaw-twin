# Report 09b: JOSM way and relation operations (task 04r-b)

Produced by `src/25_josm_ops.py` (subcommands `regress`, `targets`, `verify`, `inventory`, `report`; config `config/25_josm_ops.yaml`), with `src/21_ownership_check.py`, `src/19_osm_submit.py`, `src/18_osm_conflicts.py`, `src/osm_io.py`. Inputs verified with `scripts/verify_inputs.sh`; BASE = `data/derived/zones_v02/zone_3/zone_3.osm` (v2, sha256 `513d17da3fe612b492b0f380c4c8d9587723c2eeeaa98b787edfb96f81b14168`); edited file = `data/interim/spike_real2/editedC.osm` (FINAL, sha256 `cdb17b62063b3b67493879ec7f32407b308401fbcd3234678fcf41b8e73bebbc`; the superseded first save `add9ebd3...` is not used); JOSM 19613, osmium 1.16.0, netconvert 1.28.0. `data/raw/`, `legacy_v1/` and the v2 packages are untouched; nothing is committed.

## Summary

| Item | Result | Status |
|---|---|---|
| 1 owned extent, derived edits, inherited connections, invalid / orphan (synthetic, v2 package) | 22 of 22 cases pass | ok |
| 2 v2 regression chain on (a) + (b) | result differs from the full base in exactly the two ways | ok |
| 3 JOSM targets | T1 3, T2 2, T3 3, T4 3, T5 1, T6 1, T7 1 | ok |
| 4 facts of notes.md vs the file | 32 of 32 facts hold | ok |
| 5 full chain on editedC.osm | 11 of 11 scenarios as predicted; exit 1 with exactly 2 violations | ok |
| 5 netconvert (C2, C7, C6) | 3 of 3 pass | ok |
| 6 defect inventory | counts only (section 6) | ok |

## 1. Rule changes in `21_ownership_check.py` and `osm_io.py`

- **Owned extent** = zone polygon UNION `owned_buffer_m` (10 m) buffers of the owned ways that lie (partly) outside it. The ways are the `role=owned_outside_polygon` ways of `zone_N_reference.osm` (20 in zone 3); their geometry is taken from the package, because the reference polygon of such a way is already a closed 10 m buffer ring. New nodes are classified against the extent.
- **Bridge-group owner:** an edit of a spanning way with owner basis `bridge_group` by the group owner is `ok` (`bridge_group_owner`); other spanning ways stay warnings.
- **Inherited connection:** an existing node owned by another zone may appear in a NEW way only if an owned base way that used it is deleted in the change set or its node list no longer contains the node (Split Way, redraw). A modified way that still contains the node does not count.
- **Derived edits:** a relation modified only by replacing a member way with the parts created from it by Split Way, or by the way surviving a Combine Ways, is `ok` when the editor owns the replaced way, whoever owns the relation (`derived_edit`); a way modified only because Merge Nodes replaced a deleted node by the survivor is `ok` when the editor owns the way and the deleted node. Any other change follows the normal owner rule.
- **Invalid and orphan objects:** a new way with fewer than 2 nodes is a violation (`invalid_object`); a new untagged node used by no way and no relation is a warning (`orphan`). A new relation may contain the editor's new ways.
- **`osm_io.canon`:** members of `type=restriction` relations are compared as a multiset (role, type, ref); other relation types keep the order significant. `osm_io.is_new` recognises new objects by their negative id.
- **`19_osm_submit.py`:** no code change was needed: it already recognises new objects by the negative id, drops deleted relations (which have no members), and its renumbering rewrites every negative `ref`, including the `member ref` of existing relations (checked on the real file: `35954` -> `1000000000744`).
- The 04r results are kept: `24_real_workflow.py` was re-run against a copy of its config; it passes every planted and synthetic case (0 FAIL rows) and differs from `reports/09_real_josm_files.md` in two places only: the S2 row now lists an additional `warning / orphan` (the new rule; the expected violation is unchanged), and the three rows that compare with the 04s script from git HEAD (HEAD is now the 04r script). `reports/09_real_josm_files.md` was not regenerated.

## 2. Synthetic cases and package v2 regression (zone 3)

Synthetic files are copies of the v2 package with one scripted edit, written by `osm_io.write_josm` in the JOSM format (attribute order, single quotes, new objects with negative id and `action='modify'`). Judged on the rows of the edited objects.

| Check | Expected | Actual | Status |
|---|---|---|---|
| sha256 of the v2 package | 513d17da3fe612b492b0f380c4c8d9587723c2eeeaa98b787edfb96f81b14168 | 513d17da3fe612b492b0f380c4c8d9587723c2eeeaa98b787edfb96f81b14168 | ok |
| sidecar package_version | 2 | 2 | ok |
| owned ways outside the polygon in the reference layer | 20 | 20 | ok |
| chain 19 (E1, E2) | exit 0 / 0 | exit 0 / 0 | ok |
| chain 18 | exit 0, no conflicts | exit 0: conflicts: 0, negative-id collisions: 0 | ok |
| chain 21 (E1, E2) | exit 0 (both ways ok) | exit 0: Counter({'ok': 2}) | ok |
| osmium merge-changes / apply-changes | exit 0 / 0 | exit 0 / 0 | ok |
| osmium check-refs: result = base | same 'missing' lines | identical | ok |
| result vs full base (canonical, all objects) | exactly [('way', 115117541), ('way', 787515407)], versions +1, tag note=04r-b test | differs: [('way', 115117541), ('way', 787515407)]; versions {('way', 115117541): ('22', '23'), ('way', 787515407): ('9', '10')}; tags ok True | ok |
| (a)+(b) in one file: 19 / 21 | exit 0 / exit 0, both rows ok | exit 0 / exit 0: [(115117541, 'ok', 'own'), (787515407, 'ok', 'bridge_group_owner')] | ok |

| Case | Edit | Expected | Actual | Result |
|---|---|---|---|---|
| N1 | split of owned bridge-group way 115117541 (end node 3702470623 owned by zone 2); the new way takes the foreign end | ok / new_way_own, exit 0 | ok / new_way_own; ok / own, exit 0 | pass |
| N5b | split of spanning seam way 27717899 (owned by zone 3, ends at a node owned by zone 4); the new way takes the foreign end; the old way is a warning (spanning way, unchanged rule) | ok / new_way_own, exit 2 | ok / new_way_own; warning / spanning_owner_edit, exit 2 | pass |
| N5 | split of non-spanning seam way 114815953 (owned by zone 3, ends at a node owned by zone 4); the new way takes the foreign end | ok / new_way_own, exit 0 | ok / new_way_own; ok / own, exit 0 | pass |
| N2 | delete owned way 115117541 and draw a new way between its end nodes (one foreign: 3702470623) | ok / new_way_own, exit 0 | ok / new_in_polygon; ok / new_way_own; ok / own, exit 0 | pass |
| N4 | tag-only edit of owned way 115117541 plus a new way attached to its foreign end node 3702470623: not inherited | violation / new_way_other_zone, exit 1 | ok / own; violation / new_way_other_zone, exit 1 | pass |
| N3 | new way attached to node 158719907 (owner zone 4), no owned way using it is modified or deleted | violation / new_way_other_zone, exit 1 | violation / new_way_other_zone, exit 1 | pass |
| S2 | new node far outside the polygon (>10 m from any owned way) | violation / new_outside_polygon, exit 1 | violation / new_outside_polygon; warning / orphan, exit 1 | pass |
| S2b | new node on owned way 301893757 (outside the polygon, 156 m away), inserted into the way | ok / new_in_polygon, exit 0 | ok / new_in_polygon; ok / own, exit 0 | pass |
| S2c | new node 5 m beside owned way 301893757 (within the buffer), not part of the way (unused node: orphan warning, exit 2) | ok / new_in_polygon, exit 2 | ok / new_in_polygon; warning / orphan, exit 2 | pass |
| S2d | new node 40 m beside owned way 301893757 (20 m from the owned extent, outside the buffer) | violation / new_outside_polygon, exit 1 | violation / new_outside_polygon; warning / orphan, exit 1 | pass |
| S2e | split owned way 301893757 at node 13203459325: new way outside the polygon, all existing nodes owned by zone 3 | ok / new_way_own, exit 0 | ok / new_way_own; ok / own, exit 0 | pass |
| D1 | split of owned way 187980679 (from/to member `from` of relation 2532024, owned by zone 4): the new part replaces it in the relation | ok / derived_edit, exit 0 | ok / derived_edit; ok / new_way_own; ok / own, exit 0 | pass |
| D2 | the same split plus a tag change on relation 2532024 | violation / other_zone, exit 1 | ok / new_way_own; ok / own; violation / other_zone, exit 1 | pass |
| D3 | combine of owned ways 672838074 (member `to` of relation 9352996, owned by zone 4) and 672838073 at node 6300861516; survivor 672838073 | ok / derived_edit, exit 0 | ok / derived_edit; ok / own, exit 0 | pass |
| D4 | merge of owned node 1886574925 into owned node 344662756; ways 30999369 (owned) and 375912817 (owner zone 4) used 1886574925 | violation / other_zone, exit 1 | ok / derived_edit; ok / own; violation / other_zone, exit 1 | pass |
| I1 | the accident of notes.md: new ways -726 (name tag) and -727 (highway=secondary), each with the single new node -26253 | violation / invalid_object, exit 1 | violation / invalid_object, exit 1 | pass |
| O1 | a new untagged node used by no way and no relation | warning / orphan, exit 2 | ok / new_in_polygon; warning / orphan, exit 2 | pass |
| v2(a) | tag edit on way 115117541 (owner 3, bridge group 6) | ok / own, exit 0 | ok / own, exit 0 | pass |
| v2(b) | tag edit on way 787515407 (owner 3, bridge group, end nodes owned by zone 2, spanning) | ok / bridge_group_owner, exit 0 | ok / bridge_group_owner, exit 0 | pass |
| v2(c) | move node 3702470623 (owner 2) by 3.0 m | violation / other_zone, exit 1 | violation / other_zone, exit 1 | pass |
| v2(d) | the v1 package presented to the v2 sidecar: 19_osm_submit.py | exit 4, no .osc | exit 4, .osc: False | pass |
| v2(d2) | an .osc derived against v2 checked with the v1 file as base: 21_ownership_check.py | exit 4 | exit 4 | pass |

Notes: N5b is a warning by design (spanning `edges_zone` way edited by its owner; rule 15 of the cleaner rules). D3 combines two ways of the same `highway` value but not identical tags (a JOSM tag-conflict dialog would appear in real use). S2c now also lists the orphan warning of its unused node.

## 3. JOSM targets

| Target | Expected | Found | Status |
|---|---|---|---|
| T1 | >= 3 | 3 | ok |
| T2 | >= 2 | 2 | ok |
| T3 | 0..3 (none is allowed) | 3 | ok |
| T4 | >= 3 | 3 | ok |
| T5 | >= 1 | 1 | ok |
| T6 | >= 1 | 1 | ok |
| T7 | >= 1 | 1 | ok |
| candidates | - | T1 35, T4 13, T2 2, T3 28, T5 23, T7 16, T6 junctions 10 (netconvert tries [(165109518, True)]) | info |

Details: `data/interim/spike_real2/josm_targets_zone3.md` / `.csv`. T4[2] contains T1[1]; T3[0] is a pair of footways (both `highway=footway`; the first candidate, two oneway tram tracks, was replaced); T7 could not meet the 80 m rule (no owned way shares a node with another zone's way deeper than 46 m).

## 4. Facts of notes.md sections 3 and 7 against the file

Any difference between the notes and the file is marked `DIFFERS`; none remains after the checks below were worded as measured (the first wording of the decimals check assumed exactly 7 decimals; unmoved nodes have up to 7, trailing zeros are dropped).

| Fact | notes.md | File | Verdict |
|---|---|---|---|
| objects with action='modify' | 12 | 12 (grep lines 12) | holds |
| objects with action='delete' | 6 | 6 (grep lines 6) | holds |
| action='create' | 0 | 0 (grep lines 0) | holds |
| modify node ids | [3702470623] | [3702470623] | holds |
| modify way ids | [-744, -605, 15804629, 16237799, 17909472, 115117541, 1069314342] | [-744, -605, 15804629, 16237799, 17909472, 115117541, 1069314342] | holds |
| modify relation ids | [-83, 35954, 1732342, 3262876] | [-83, 35954, 1732342, 3262876] | holds |
| delete node ids | [2268359200, 3707768720, 4615919461] | [2268359200, 3707768720, 4615919461] | holds |
| delete way ids | [481680205, 503888209] | [481680205, 503888209] | holds |
| delete relation ids | [4680857] | [4680857] | holds |
| relations in the file vs package | 77 vs 76 | 77 vs 76 | holds |
| '26253' absent from the file (the accident objects) | no output | absent | holds |
| new objects: negative id, action='modify', no timestamp / version | 3 new ways/relations, none with timestamp/version | 3 new (['relation -83', 'way -605', 'way -744']); with timestamp 0, with version 0, action=modify 3 | holds |
| edited existing objects keep version and timestamp | all 15 | 15/15 | holds |
| deleted relation 4680857: id, timestamp, version and tags kept, no members | tags kept, 0 members | version 3/3, timestamp equal True, tags 2/2, members 0 | holds |
| members of 35954 written via, to, from (-744) | via, to, from=-744 (input: from, via, to) | [('via', 'node', '165109537'), ('to', 'way', '131476956'), ('from', 'way', '-744')] | holds |
| new relation -83: members to, via, from; tags sorted | to, via, from; restriction, type | ['to', 'via', 'from']; ['restriction', 'type'] | holds |
| moved node 3702470623: 11 decimals; other nodes 7 | 11; at most 7 | 11/11 decimals; other nodes: decimals histogram {3: 2, 4: 18, 5: 140, 6: 1549, 7: 15267} (trailing zeros are dropped, so fewer than 7 occurs; none above 7) | holds |
| untouched objects canonically equal to the base | 0 differences | 0 of 10935; package objects missing from the file: 0 | holds |
| every action='modify' object of the base differs canonically | 0 identical | 0 identical: [] | holds |
| C1: old id kept by the longer part (11 nodes, last 3951576856); new -605 has 11 nodes, first 3951576856 | 11 / 11 | 11 nodes, last 3951576856; 11 nodes, first 3951576856; base 21 nodes | holds |
| C1: tags copied to both parts (length=266) | length=266 on both | 266 / 266 | holds |
| C2: old id keeps 5 nodes, new -744 has 3 nodes [1184506398, 4623369920, 165109537] | 5 / 3 | 5 / 3: [1184506398, 4623369920, 165109537] | holds |
| C2: relation 35954 now has -744 as `from`; 16237799 in no relation | from=-744 | [('to', '131476956'), ('from', '-744')]; 16237799 in relations: [] | holds |
| C3: 17909472 survives with 5 nodes; 503888209 deleted without nodes | 5 nodes; delete | 5 nodes; action delete, nd 0, tags 8 | holds |
| C4: survivor 2992700684 untouched; 4615919461 deleted; only way 1069314342 modified (1116853997 not) | survivor unmarked; 1 way modified | 2992700684 action None; 4615919461 delete; 1116853997 action None; 1069314342 modify | holds |
| C8: nodes 425808778 and 425808776 untouched | no action | None, None | holds |
| C10b: ways 115117541 (tag edit) and 787515407 (shares the moved node): only the first is marked | 787515407 unmarked | 115117541 modify; 787515407 None | holds |
| C10: way 115117541 has no bridge / layer tag; node has highway=traffic_signals | no bridge tag | bridge=None, tunnel=None; node tags {'highway': 'traffic_signals'} | holds |
| C8: way 481680205 has 4 nodes (425808776 also on way 114815955) | 4 nodes | 4 nodes; 425808776 on ways [114815955, 481680205] | holds |
| C4: way 1116853997 is area=yes + highway=footway | area=yes | {'area': 'yes', 'highway': 'footway', 'lit': 'no', 'surface': 'compacted'} | holds |
| C10b: displacement of node 3702470623 | ~2.95 m | 2.956 m (base coordinates have 7 decimals, file 11) | holds |
| new ids: -605 (way), -744 (way), -83 (relation) | -605, -744, -83 | {'way': [-744, -605], 'relation': [-83], 'node': []} | holds |

Measured differences from the notes: displacement of node 3702470623 is 2.956 m from the 7-decimal base coordinates (notes: ~2.95 m); the checker moves are computed the same way. Counts by `grep -c` are lines, not objects; both agree here (12 / 6 / 0).

## 5. Full chain on editedC.osm

Chain: `19_osm_submit.py` -> `18_osm_conflicts.py` (with an unchanged second editor, because 18 needs two files) -> `21_ownership_check.py` -> `osmium merge-changes` -> `apply-changes` on the FULL `ring1_roads.osm` -> `check-refs` -> `netconvert`.

| Check | Expected | Actual | Status |
|---|---|---|---|
| editedC.osm sha256 | cdb17b62063b3b67493879ec7f32407b308401fbcd3234678fcf41b8e73bebbc | cdb17b62063b3b67493879ec7f32407b308401fbcd3234678fcf41b8e73bebbc | ok |
| BASE zone_3.osm sha256 | 513d17da3fe612b492b0f380c4c8d9587723c2eeeaa98b787edfb96f81b14168 | 513d17da3fe612b492b0f380c4c8d9587723c2eeeaa98b787edfb96f81b14168 | ok |
| 19_osm_submit.py editedC.osm | exit 0; deleted_dropped 6, bumped 9, new 3 | exit 0; {'bumped': 9, 'deleted_dropped': 6, 'new': 3} | ok |
| renumbering rewrites `member ref` of the existing relation 35954 and the new relation | 1000000000744 in 35954; 1000000000083 is relation id; no negative id left | 35954 members [('via', '165109537'), ('to', '131476956'), ('from', '1000000000744')]; negative left [] | ok |
| osc blocks | modify 9 + create 3 (osmium writes new objects in <modify>), delete 6 | {'delete': 6, 'modify': 12} | ok |
| 18_osm_conflicts.py C + an unchanged second editor | exit 0 | exit 0: conflicts: 0, negative-id collisions: 0 | ok |
| 21_ownership_check.py | exit 1 with exactly the 2 violations | exit 1; violations [('node', 3702470623, 'other_zone'), ('relation', 1732342, 'other_zone')]; warnings 0 | ok |
| osmium merge-changes / apply-changes (full ring1_roads.osm) | exit 0 / 0 | exit 0 / 0 | ok |
| osmium check-refs: result = base | same 'missing' lines | identical | ok |
| result vs full base: exactly the edited objects differ | 18 objects | 18; unexpected []; missing [] | ok |
| result equals editedC.osm for every edited object (ids mapped, restriction members as multiset); deleted objects absent | 0 differences | differs []; still present [] | ok |
| versions of changed objects | base + 1 | all +1 | ok |

### Scenarios (prediction vs actual)

| # | Edit | Expected | Actual | Result |
|---|---|---|---|---|
| C1 | split 15804629 | way 15804629 ok; new way -605 ok | 15804629: ok / own; -605: ok / new_way_own | pass |
| C2 | split 16237799 (from of 35954) | ways 16237799 and -744 ok; relation 35954 ok (derived) | 16237799: ok / own; -744: ok / new_way_own; 35954: ok / derived_edit [derived from split of 16237799] | pass |
| C3 | combine 17909472 + 503888209 | survivor ok, deleted way ok | 17909472: ok / own; 503888209: ok / own | pass |
| C4 | merge nodes 2992700684 + 4615919461 | way 1069314342 ok, deleted node 4615919461 ok | 1069314342: ok / derived_edit [derived from merge of nodes [4615919461] into [2992700684]]; node 4615919461: ok / own; survivor 2992700684: no row | pass |
| C5 | relation 3262876 restriction tag | ok | ok / own | pass |
| C6 | delete relation 4680857 | ok | ok / own | pass |
| C7 | new relation -83 | ok (owner by via node 165109518) | ok / new_relation; owner of via node 3 | pass |
| C8 | delete way 481680205 with its nodes | way and nodes 3707768720, 2268359200 ok; nodes 425808778, 425808776 untouched | way: ok / own; nodes: ok / own, ok / own; 425808778 / 425808776 in osc: False | pass |
| C9 | relation 1732342 (zone 10) | violation | violation / other_zone | pass |
| C10a | way 115117541 tag | ok (the brief says bridge_group_owner; the way is not spanning, so the category is `own`) | ok / own | pass |
| C10b | node 3702470623 moved | violation other_zone; rule (c) (3 m) does not fire | violation / other_zone; moved 2.959 m; rule (c) fired: False | pass |

Where the actual result differs from the prediction in wording only: C10a is category `own` (way 115117541 is not a spanning way: `spans_zones=False`), not `bridge_group_owner`; C10b moved node 3702470623 by 2.956 m; rule (c) does not fire (below 3 m, and both ways using the node, 115117541 and 787515407, are owned by zone 3). Warnings: none (0).

### All rows of `21_ownership_check.py`

| object | op | severity | category | reason |
|---|---|---|---|---|
| node 2268359200 | delete | ok | own | owned by zone 3 |
| node 3702470623 | modify | violation | other_zone | owned by zone 2 |
| node 3707768720 | delete | ok | own | owned by zone 3 |
| node 4615919461 | delete | ok | own | owned by zone 3 |
| way 15804629 | modify | ok | own | owned by zone 3 |
| way 16237799 | modify | ok | own | owned by zone 3 |
| way 17909472 | modify | ok | own | owned by zone 3 |
| way 115117541 | modify | ok | own | owned by zone 3 |
| way 481680205 | delete | ok | own | owned by zone 3 |
| way 503888209 | delete | ok | own | owned by zone 3 |
| way 1069314342 | modify | ok | derived_edit | derived from merge of nodes [4615919461] into [2992700684] |
| way 1000000000605 | create | ok | new_way_own | new nodes inside the polygon, existing nodes own |
| way 1000000000744 | create | ok | new_way_own | new nodes inside the polygon, existing nodes own |
| relation 35954 | modify | ok | derived_edit | derived from split of 16237799 |
| relation 1732342 | modify | violation | other_zone | owned by zone 10 |
| relation 3262876 | modify | ok | own | owned by zone 3 |
| relation 4680857 | delete | ok | own | owned by zone 3 |
| relation 1000000000083 | create | ok | new_relation | all members own or new |

### The three hard cases

1. **Relation 35954 modified through the new way -744.** The file has `action='modify'` on relation 35954 with `from` = -744; after renumbering the `.osc` has `from` = 1000000000744. The new way is created, the old way 16237799 shrinks, and the relation is the only object that links them. Check row: `ok / derived_edit: derived from split of 16237799`; the new way 1000000000744: `ok / new_way_own`. Without the derived-edit rule 35954 would be owned-relation-ok anyway (owner zone 3); the rule matters for foreign relations (synthetic D1 / D2).
2. **No `action='create'` anywhere.** 0 in the file (text and parse), 0 `<create>` blocks in the `.osc` (osmium writes new objects inside `<modify>`), so new objects are found by the negative id in the file and by "id not in the base package" in the `.osc`.
3. **Node 3702470623 moved while the ways using it (115117541, 787515407) are not marked.** The file marks only the node; the checker finds the users in the full base. Row: `violation / other_zone` (owner zone 2, rule (b)); rule (c) fired: False (users owned by other zones: []).

### netconvert (bbox 17.0365,51.1033,17.0544,51.1176, `--keep-edges.in-geo-boundary`, base = full `ring1_roads.osm`, merged = base + editedC changes)

| Check | Expected | Actual | Result |
|---|---|---|---|
| C2 junction 165109537: way-level connections before / after | from-way (16237799 before, new way after) connects only to 131476956 (only_straight_on kept); other connections unchanged | before [(16237799, 131476956), (131476907, 131476955)]; after [(131476907, 131476955), (1000000000744, 131476956)] | pass |
| C7 junction 165109518: way-level connections before / after | (25014454 -> 16237792) present before, absent after; the other connections unchanged | removed [(25014454, 16237792)]; added []; unchanged 5 | pass |
| C6 junction 165109510: way-level connections before / after | from 16237800 only to 131477086 before (only_straight_on); more connections after, none lost | before [(16237800, 131477086), (131477038, 131477085)]; after [(16237800, 131477085), (16237800, 131477086), (131477038, 131477085)]; restored [(16237800, 131477085)] | pass |

Connections at each junction (from edge -> to edge (direction)); several internal lanes of one connection appear as repeated lines:

- `C2_base`: 131476907 -> 131476955 (s); 131476907 -> 131476955 (s); 131476907 -> 131476955 (s); 16237799#1 -> 131476956#0 (s); 16237799#1 -> 131476956#0 (s)
- `C2_merged`: 1000000000744 -> 131476956#0 (s); 1000000000744 -> 131476956#0 (s); 131476907 -> 131476955 (s); 131476907 -> 131476955 (s); 131476907 -> 131476955 (s)
- `C6_base`: 131477038 -> 131477085 (s); 131477038 -> 131477085 (s); 16237800#1 -> 131477086 (s); 16237800#1 -> 131477086 (s)
- `C6_merged`: 131477038 -> 131477085 (s); 131477038 -> 131477085 (s); 16237800#1 -> 131477085 (r); 16237800#1 -> 131477086 (s); 16237800#1 -> 131477086 (s)
- `C7_base`: -25014454#0 -> 16237792 (r); -25014454#0 -> 25014454#0 (t); -25014454#0 -> 30999112 (R); 191002276 -> 16237792 (s); 191002276 -> 16237792 (s); 191002276 -> 16237792 (s); 191002276 -> 25014454#0 (r); 191002276 -> 30999112 (L)
- `C7_merged`: -25014454#0 -> 25014454#0 (t); -25014454#0 -> 30999112 (R); 191002276 -> 16237792 (s); 191002276 -> 16237792 (s); 191002276 -> 16237792 (s); 191002276 -> 25014454#0 (r); 191002276 -> 30999112 (L)

C2: before the split the restriction applies to edge `16237799#1` (-> `131476956#0`); after it, to edge `1000000000744` (the new way), with the same single target. C7: the connection `-25014454#0` -> `16237792` (right turn) is gone, the other seven stay. C6: with the restriction deleted, edge `16237800#1` also connects to `131477085` (right turn).

## 6. Defect inventory (counts only, nothing changed)

Base `data/interim/ring1_roads.osm` (sha256 `220a82a3ee432eb002a17eaf53c206684e603e2ea05f259fe70e57e8bfd0df11`): 67232 nodes, 20091 ways, 421 relations.

**(a) Bridge-group ways without `bridge=*` and without `tunnel=*`:** 120 of 183 bridge-group ways in 15 groups (all in the base). By group (group: ways without tags / ways, owner zone):

| group | owner zone | ways | without bridge / tunnel | first ids |
|---|---|---|---|---|
| 1 | 3 | 5 | 2 | 16313065, 51943721 |
| 2 | 10 | 7 | 4 | 16584757, 24320105, 427901089, 1458351532 |
| 3 | 11 | 28 | 22 | 16584767, 16584776, 16584779, 277218767, 296430671, 427901085 |
| 4 | 11 | 19 | 12 | 16584773, 16584788, 16584792, 55468339, 188148322, 339043151 |
| 5 | 1 | 14 | 9 | 16584780, 1090590815, 1137331695, 1137331697, 1137331699, 1137331700 |
| 6 | 3 | 33 | 24 | 16752115, 16752117, 115117541, 117370609, 188337231, 188337254 |
| 7 | 3 | 16 | 11 | 16752120, 133866975, 164216275, 164216279, 233303587, 233303588 |
| 8 | 11 | 21 | 15 | 17922921, 17922923, 24585821, 288225522, 288225536, 363024550 |
| 9 | 3 | 3 | 2 | 27833797, 27833805 |
| 10 | 3 | 4 | 3 | 28354584, 51179164, 761992024 |
| 11 | 3 | 11 | 5 | 28354640, 98750126, 354668449, 354668450, 360786757 |
| 12 | 3 | 3 | 2 | 335275279, 1157376479 |
| 13 | 10 | 3 | 2 | 59965324, 435820719 |
| 14 | 10 | 3 | 2 | 103155255, 103155257 |
| 15 | 10 | 13 | 5 | 114549377, 322541930, 427901091, 1137334665, 1137334666 |

**(b) Duplicated restriction relations** (same tags and same members as a multiset): 1 group(s), 2 relations, 1 redundant, of 421 restriction relations: [[4680853, 18791081]].

**(c) `length` tag differing from the geometry by more than 10%:** only 4 ways in the base have a `length` tag (0 unparsable); 2 differ. By highway class: {'secondary': 1, 'tertiary': 1}; ways with the tag by class: {'secondary': 1, 'tertiary': 3}. Examples (way, tag m, geometry m): [[15804629, 266.0, 203.2], [187405572, 17.0, 11.6]].

## 7. Reproducibility

Each subcommand writes `output_hashes.txt` under `data/interim/josm_ops/<subcommand>/` (sha256 of the generated `.osc`, `.osm` and `.json`; no timestamps). Two complete runs of `regress`, `targets`, `verify`, `inventory`, `report` gave identical hashes (see the final reply of the task). The report itself is deterministic.
