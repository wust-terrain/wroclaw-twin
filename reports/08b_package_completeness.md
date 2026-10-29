# Task 03b'': package completeness

Analysis and packaging only; the partition and the ownership tables are unchanged (regression below). The real-JOSM test showed that `zone_3.osm` (package version 1) lacked objects owned by zone 3. Version 1 was cut with `osmium extract -p <zone polygon + 60 m> --strategy complete_ways`, which keeps a way only when one of its nodes lies inside; the 03b' hard check covered the base, not the packages.

## 1. Diagnosis (version 1 method, all 11 zones)

Owned objects (`ownership_*.csv`, `owner_zone` = zone) that the context extract alone leaves out:

| zone | owned ways | missing | owned nodes | missing | owned relations | missing |
|---|---|---|---|---|---|---|
| 1 | 1261 | 0 | 4620 | 0 | 31 | 0 |
| 2 | 1983 | 4 | 6490 | 18 | 36 | 1 |
| 3 | 1716 | 20 | 5718 | 58 | 53 | 1 |
| 4 | 1489 | 0 | 4933 | 0 | 29 | 0 |
| 5 | 1584 | 1 | 5740 | 2 | 14 | 0 |
| 6 | 1542 | 2 | 4815 | 4 | 78 | 0 |
| 7 | 1336 | 1 | 4558 | 2 | 38 | 0 |
| 8 | 1833 | 2 | 6049 | 13 | 32 | 0 |
| 9 | 1468 | 7 | 5259 | 18 | 45 | 0 |
| 10 | 2037 | 1 | 6264 | 1 | 25 | 0 |
| 11 | 1103 | 1 | 3644 | 6 | 19 | 1 |

Expected: zone 3: 20 ways, 58 nodes, 1 relation; zone 4: 0. Found: zone 3: 20 / 58 / 1; zone 4: 0 / 0 / 0. **No difference.**

Zones with missing owned objects: 2, 3, 5, 6, 7, 8, 9, 10, 11

Hypothesis: the missing ways are bridge-group ways whose nodes lie outside polygon + buffer. **Half confirmed, half refuted.** In every zone with missing ways all of them lie outside polygon + buffer (no node within the buffer: confirmed), which is exactly why `complete_ways` drops them. But only 3 of the 39 missing ways belong to bridge groups (zone 3: 2 of 20); the others are ways of RING 1 edges (`edges_zone`) or footways assigned by face geometry whose zone ownership reaches beyond the zone polygon, because ownership follows edges and sites, not the polygon (see 03c). The problem is therefore general, not specific to bridges, and affects 9 of the 11 zones.

- zone 2: 4 ways missing (0 bridge-group)
- zone 3: 20 ways missing (2 bridge-group)
- zone 5: 1 ways missing (0 bridge-group)
- zone 6: 2 ways missing (0 bridge-group)
- zone 7: 1 ways missing (0 bridge-group)
- zone 8: 2 ways missing (0 bridge-group)
- zone 9: 7 ways missing (0 bridge-group)
- zone 10: 1 ways missing (0 bridge-group)
- zone 11: 1 ways missing (1 bridge-group)

### Zone 3: missing from the version 1 package

Ways (20): 115117541, 301893757, 301893758, 301894198, 327512886, 765695794, 765695795, 787515407, 952995213, 1090301197, 1090301739, 1090301740, 1137616257, 1137616258, 1137616259, 1137616260, 1137616769, 1137616771, 1177925032, 1177925033

Nodes (58): 165109721, 165109837, 1191040951, 1989660088, 3060594235, 3060594238, 3060594245, 3060596561, 3343011735, 3343011738, 3343011739, 3343011740, 3343011742, 3343011744, 3343011746, 3343011748, 3343011750, 3343011751, 3469928438, 3469928441, 3469928442, 3469928444, 3469928445, 3469928448, 3469928454, 3469928460, 3607431342, 3764793632, 4620137957, 4620151781, 4620151782, 4620381822, 4620381823, 4620381824, 4620381825, 4945051167, 4945051169, 5001615482, 5001615483, 7151247303, 7151247304, 7151247317, 7151247318, 7151247319, 7151247320, 7151247321, 9986651955, 9986651957, 9986651958, 9986651959, 9986651960, 9986651961, 10604260025, 10604260026, 10604260027, 10604260028, 13203459325, 13695044845. Of these, 58 are nodes of the missing ways.

Relations (1): 12832677

| way | highway | name | bridge group | basis | nodes | nearest node m | farthest node m | end A (owner) | end B (owner) |
|---|---|---|---|---|---|---|---|---|---|
| 115117541 | secondary | Kardynała Stefana Wyszyńskiego | 6 | bridge_group | 7 | 96.8 | 177.9 | 1302027827 (3) | 3702470623 (2) |
| 301893757 | service |  | None | edges_zone | 5 | 152.8 | 159.1 | 3469928460 (3) | 3469928445 (3) |
| 301893758 | service |  | None | edges_zone | 3 | 92.9 | 155.1 | 3469928445 (3) | 3469928454 (3) |
| 301894198 | service |  | None | edges_zone | 9 | 159.9 | 218.5 | 3060594245 (3) | 3758276605 (3) |
| 327512886 | secondary |  | None | edges_zone | 13 | 69.0 | 145.8 | 3764793632 (3) | 3343011741 (3) |
| 765695794 | service |  | None | edges_zone | 5 | 155.0 | 172.0 | 3469928445 (3) | 7151247318 (3) |
| 765695795 | service |  | None | edges_zone | 4 | 160.7 | 161.3 | 3469928442 (3) | 7151247320 (3) |
| 787515407 | secondary | Kardynała Stefana Wyszyńskiego | 6 | bridge_group | 6 | 177.9 | 209.3 | 3702470623 (2) | 185460721 (2) |
| 952995213 | secondary |  | None | edges_zone | 3 | 145.8 | 161.1 | 165109710 (10) | 3764793632 (3) |
| 1090301197 | service |  | None | edges_zone | 2 | 155.1 | 170.3 | 3469928445 (3) | 3469928444 (3) |
| 1090301739 | steps |  | None | face_geometry | 2 | 112.2 | 113.2 | 9986651959 (3) | 9986651955 (3) |
| 1090301740 | footway |  | None | face_geometry | 4 | 99.1 | 112.1 | 4620381829 (3) | 9986651960 (3) |
| 1137616257 | footway |  | None | face_geometry | 2 | 115.3 | 115.5 | 10604260026 (3) | 10604260025 (3) |
| 1137616258 | footway |  | None | face_geometry | 2 | 110.9 | 112.2 | 9986651955 (3) | 9986651954 (3) |
| 1137616259 | steps |  | None | face_geometry | 2 | 118.0 | 119.1 | 9986651958 (3) | 10604260028 (3) |
| 1137616260 | footway |  | None | face_geometry | 3 | 119.1 | 121.9 | 10604260028 (3) | 9986651956 (3) |
| 1137616769 | footway |  | None | face_geometry | 7 | 158.4 | 217.7 | 4620381822 (3) | 4620381826 (3) |
| 1137616771 | footway |  | None | face_geometry | 4 | 112.1 | 118.0 | 9986651960 (3) | 9986651958 (3) |
| 1177925032 | steps |  | None | face_geometry | 2 | 179.5 | 179.9 | 10942461589 (4) | 4620151781 (3) |
| 1177925033 | footway |  | None | face_geometry | 3 | 178.1 | 179.5 | 4620151781 (3) | 4620381825 (3) |

Distances are from the zone polygon (EPSG:2177); the buffer is 60 m.

### Zone 4: missing from the version 1 package

Ways (0): none

Nodes (0): none

Relations (0): none

### Objects named in the JOSM test

| object | owner zone | in zone 3 missing list | in the version 2 package of zone 3 |
|---|---|---|---|
| w115117541 | 3 | yes | yes |
| w787515407 | 3 | yes | yes |
| n3702470623 | 2 | no | yes |
| n185460721 | 2 | no | yes |
| n4616719047 | 2 | no | yes |

The three nodes are owned by **zone 2** in the ownership tables (end nodes of zone 3's bridge ways, read-only for zone 3), not by zone 3. They are missing from the version 1 package because they lie outside polygon + buffer; version 2 contains them as read-only nodes of the owned ways (`--add-referenced`).

## 2. Fix (package version 2)

Package = union of (a) the read-only context extract and (b) every object owned by the zone: its ways with all their nodes, its owned nodes, and its owned relations as relation objects. Commands (per zone, in `data/interim/zones_v02/zone_<N>/`; `BASE` = `data/interim/ring1_roads.osm.pbf`):

```
osmium extract -p zone_3_buffer.geojson --strategy complete_ways -o zone_3_context.osm.pbf data/interim/ring1_roads.osm.pbf
osmium getid --add-referenced -i zone_3_owned_ids.txt -o zone_3_owned.osm.pbf data/interim/ring1_roads.osm.pbf
osmium getid -i zone_3_owned_relation_ids.txt -o zone_3_owned_relations.osm.pbf data/interim/ring1_roads.osm.pbf
osmium merge -o zone_3.osm.pbf zone_3_context.osm.pbf zone_3_owned.osm.pbf zone_3_owned_relations.osm.pbf
osmium cat -o zone_3.osm zone_3.osm.pbf
```

Duplicates are removed by `osmium merge` (checked on every run; a fallback keeps the first line per `(type, id)`); `osmium check-refs` on way nodes must pass. Hard checks on every run for every packaged zone: every owned way, node and relation is in the package, no duplicate objects, `check-refs` passes; otherwise the run stops. The sidecar `zone_<N>.json` has `package_version: 2`, object counts split into owned / read-only / unowned, the objects added by part (b) and the sha256 of the base.

| zone | ways (owned / read-only / unowned) | nodes (owned / read-only / unowned) | relations (owned / read-only / unowned) | added by (b): ways / nodes / relations | sha256 package |
|---|---|---|---|---|---|
| 3 | 1716 / 666 / 3 | 5718 / 2764 / 7 | 53 / 23 / 0 | 20 / 58 / 1 | `513d17da3fe612b4...` |
| 4 | 1489 / 720 / 95 | 4933 / 3037 / 313 | 29 / 34 / 1 | 0 / 0 / 0 | `ec2e03f55f0f1b9f...` |

Reference layer: owned ways without any node inside polygon + buffer are added to `zone_<N>_reference.osm` as 10 m buffers with `role=owned_outside_polygon`: zone 3: 20, zone 4: 0.

## 3. Regression

Files that must equal the 03b' follow-up outputs (ownership tables, units, seams, bridge files, geojson, shared nodes): 15 compared, 15 identical.

| zone | objects in version 1 | objects in version 2 | version 1 objects missing in version 2 | objects added | file identical |
|---|---|---|---|---|---|
| 3 | 10865 | 10950 | 0 | 85 | no |
| 4 | 10651 | 10651 | 0 | 0 | yes |

Added objects by type: zone 3: n 64, r 1, w 20; zone 4: none.

Version 1 packages are kept unchanged in `data/derived/zones_v02/legacy_v1/` (with `SHA256SUMS`, checked on every run) for task 04r.

## Checks

| Check | Expected | Actual | Result |
|---|---|---|---|
| legacy_v1 package files (used by task 04r) match their SHA256SUMS | all OK | all OK | PASS |
| fingerprint: layer zones_v02 equals the digest of the v0.2 run | identical | identical | PASS |
| fingerprint: layer edges_zone equals the digest of the v0.2 run | identical | identical | PASS |
| fingerprint: layer clusters_zone equals the digest of the v0.2 run | identical | identical | PASS |
| fingerprint: layer bridge_groups equals the digest of the v0.2 run | identical | identical | PASS |
| fingerprint: layer islands equals the digest of the v0.2 run | identical | identical | PASS |
| freeze fingerprint equals the stored one | identical | identical | PASS |
| site zones: hull rule reproduces the stored cluster zones | 0 | 0 | PASS |
| bridge group 1: all edges carry the group owner in edges_zone | 0 | 0 | PASS |
| bridge group 2: all edges carry the group owner in edges_zone | 0 | 0 | PASS |
| bridge group 3: all edges carry the group owner in edges_zone | 0 | 0 | PASS |
| bridge group 4: all edges carry the group owner in edges_zone | 0 | 0 | PASS |
| bridge group 5: all edges carry the group owner in edges_zone | 0 | 0 | PASS |
| bridge group 6: all edges carry the group owner in edges_zone | 0 | 0 | PASS |
| bridge group 7: all edges carry the group owner in edges_zone | 0 | 0 | PASS |
| bridge group 8: all edges carry the group owner in edges_zone | 0 | 0 | PASS |
| bridge group 9: all edges carry the group owner in edges_zone | 0 | 0 | PASS |
| bridge group 10: all edges carry the group owner in edges_zone | 0 | 0 | PASS |
| bridge group 11: all edges carry the group owner in edges_zone | 0 | 0 | PASS |
| bridge group 12: all edges carry the group owner in edges_zone | 0 | 0 | PASS |
| bridge group 13: all edges carry the group owner in edges_zone | 0 | 0 | PASS |
| bridge group 14: all edges carry the group owner in edges_zone | 0 | 0 | PASS |
| bridge group 15: all edges carry the group owner in edges_zone | 0 | 0 | PASS |
| ways in bridge groups with different owners | 0 | 0 | PASS |
| hard: every way of a RING 1 edge or bridge group is in the base | 6746 | 6746 | PASS |
| the ways with owner_basis edges_zone / bridge_group are exactly the ways of RING 1 edges and bridge groups | 6746 | 6746 | PASS |
| base: duplicate (type, id) objects after the union | 0 | 0 | PASS |
| base: osmium check-refs (way nodes) | 0 | 0 | PASS |
| ways that had an owner before the rebuild and changed it | 0 | 0 | PASS |
| units: all work units have an owner | 7018 | 7018 | PASS |
| S0 minutes by owner sum to the total of the unit-face table | 21882.8 | 21882.8 | PASS |
| zone 3 units (label-drift guard, 1%) | 671 | 671 | PASS |
| zone 3 s0_minutes (label-drift guard, 1%) | 2219 | 2219.2 | PASS |
| zone 3 sites (label-drift guard, 1%) | 35 | 35 | PASS |
| zone 3 tram_ways (label-drift guard, 1%) | 59 | 59 | PASS |
| zone 4 units (label-drift guard, 1%) | 705 | 705 | PASS |
| zone 4 s0_minutes (label-drift guard, 1%) | 2158 | 2157.8 | PASS |
| zone 4 sites (label-drift guard, 1%) | 36 | 36 | PASS |
| zone 4 tram_ways (label-drift guard, 1%) | 22 | 22 | PASS |
| ways in the base extract all have a row | 20091 | 20091 | PASS |
| nodes in the base extract all have a row | 67232 | 67232 | PASS |
| relations in the base extract all have a row | 421 | 421 | PASS |
| ways of RING 1 edges all have an owner | 0 | 0 | PASS |
| zone 3 package: every owned way is in the package | 0 | 0 | PASS |
| zone 3 package: every owned node is in the package | 0 | 0 | PASS |
| zone 3 package: every owned relation is in the package | 0 | 0 | PASS |
| zone 3 package: duplicate (type, id) objects | 0 | 0 | PASS |
| zone 3 package: osmium check-refs (way nodes) | 0 | 0 | PASS |
| zone 3: units file holds all owned units | 671 | 671 | PASS |
| zone 4 package: every owned way is in the package | 0 | 0 | PASS |
| zone 4 package: every owned node is in the package | 0 | 0 | PASS |
| zone 4 package: every owned relation is in the package | 0 | 0 | PASS |
| zone 4 package: duplicate (type, id) objects | 0 | 0 | PASS |
| zone 4 package: osmium check-refs (way nodes) | 0 | 0 | PASS |
| zone 4: units file holds all owned units | 705 | 705 | PASS |
| seam edges: end points matched to OSM nodes within the tolerance (max distance m) | <= 1.0 | 0.0 | PASS |
| pilot pair seam edges | 21 | 21 | PASS |
| pilot pair seam km | 1.14 | 1.14 | PASS |
| pilot pair edges_A (decision D6) | 361 | 361 | PASS |
| pilot pair edges_B_core (decision D6) | 167 | 167 | PASS |
| pilot pair edges_B_service (decision D6) | 206 | 206 | PASS |
| pilot pair edges_C (decision D6) | 416 | 416 | PASS |
| pilot pair tram_ways (decision D6) | 81 | 81 | PASS |
| zone 3 seams file: pilot_pair_seam edges | 21 | 21 | PASS |
| zone 4 seams file: pilot_pair_seam edges | 21 | 21 | PASS |
| regression: files identical to the 03b' follow-up outputs (ownership tables, units, seams, bridges, geojson, shared nodes) | 15 | 15 | PASS |
| regression: zone 3 package keeps every object of its first version | 0 | 0 | PASS |
| regression: zone 4 package keeps every object of its first version | 0 | 0 | PASS |
