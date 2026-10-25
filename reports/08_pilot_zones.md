# Task 03b': pilot zones, ownership lists and zone packages (v0.2)

Analysis and packaging only. The v0.2 partition is used as stored (`data/interim/ring1_zones_v02.gpkg`, nothing recomputed); `scope.yaml`, the polygon, D2-D4, `tiers.yaml`, `ring1_zones_v0.gpkg` and the v0.2 results are unchanged. Pilot zones 3, 4; read buffer 60 m. Every number is [PROPOSED] (S0 weights are unmeasured guesses).

## Checks

| Check | Expected | Actual | Result |
|---|---|---|---|
| site zones: hull rule reproduces the stored cluster zones | 0 | 0 | PASS |
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
| ways in the base extract all have a row | 17286 | 17286 | PASS |
| nodes in the base extract all have a row | 57900 | 57900 | PASS |
| relations in the base extract all have a row | 397 | 397 | PASS |
| ways of RING 1 edges all have an owner | 0 | 0 | PASS |
| pilot pair seam edges | 21 | 21 | PASS |
| pilot pair seam km | 1.14 | 1.14 | PASS |
| pilot pair edges_A (decision D6) | 361 | 361 | PASS |
| pilot pair edges_B_core (decision D6) | 167 | 167 | PASS |
| pilot pair edges_B_service (decision D6) | 206 | 206 | PASS |
| pilot pair edges_C (decision D6) | 416 | 416 | PASS |
| pilot pair tram_ways (decision D6) | 81 | 81 | PASS |
| zone 3 seams file: pilot_pair_seam edges | 21 | 21 | PASS |
| zone 4 seams file: pilot_pair_seam edges | 21 | 21 | PASS |

## Ownership rules (all 11 zones)

- **Ways.** Owner = zone with the largest share of the way's length in RING 1: `segments` (way, edge, fragment length) joined to `edges_zone` (edge -> zone); ties go to the lower zone. All ways of a bridge group (ways of the group's edges, and `bridges.way_id`) follow the group owner (`owner_basis=bridge_group`, `bridge_owner_differs_from_share` when that changes the majority owner). `spans_zones` = length above 0.01 m in more than one zone; `shares` = `zone:share` of the length inside RING 1 edges.
- **Ways without an edge** (footways, steps, paths, rail, and network ways whose edge is outside RING 1 by D3) are not in `edges_zone`. This case is not covered by the task text; interpretation used here: the way is cut by the zone faces of the stored partition and takes the zone with the largest length share (`owner_basis=face_geometry`); with no length in a zoned face but crossing RING 1 (water, orphan faces, islands with zone 0) it takes the zone of the nearest zoned face (`nearest_face`); the rest is outside RING 1 and unowned (`outside_ring1`, owner 0).
- **Nodes.** Nodes of a junction cluster take `clusters_zone`; nodes of a site (cluster nodes, signal-cluster nodes, tram-crossing nodes) take the site zone (sites without a junction cluster: hull rule of task 03c on the stored faces, validated against the stored cluster zones). Other nodes take the owner of the longest way (full way length) that uses them among owned ways, ties to the lower way id. `shared_across_zones` = ways with different owners use the node; `way_zones` = `zone:number of ways`. Nodes with no owned way: stored faces as for ways.
- **Relations (turn restrictions).** Owner of the via member (node: node owner; way: way owner); without via, the owner of the from way. `member_zones` lists the owners of all members.

## Ownership counts

| owner zone | ways | of which spanning | nodes | of which shared | relations |
|---|---|---|---|---|---|
| none | 0 | 0 | 0 | 0 | 0 |
| 1 | 1261 | 12 | 4594 | 41 | 31 |
| 2 | 1983 | 4 | 6426 | 28 | 33 |
| 3 | 1716 | 20 | 5708 | 64 | 53 |
| 4 | 1489 | 30 | 4933 | 84 | 29 |
| 5 | 1584 | 39 | 5729 | 71 | 14 |
| 6 | 1542 | 28 | 4804 | 54 | 78 |
| 7 | 1336 | 22 | 4538 | 51 | 38 |
| 8 | 1833 | 23 | 6032 | 66 | 32 |
| 9 | 1468 | 19 | 5228 | 54 | 45 |
| 10 | 2037 | 16 | 6264 | 71 | 25 |
| 11 | 1103 | 10 | 3644 | 30 | 19 |
| total | 17352 | 223 | 57900 | 614 | 397 |

Owner `none` = outside RING 1 (reachable only through `complete_ways`).

Ways by basis:

| owner_basis | ways |
|---|---|
| bridge_group | 183 |
| edges_zone | 6563 |
| face_geometry | 10564 |
| nearest_face | 42 |

| node owner_basis | nodes |
|---|---|
| cluster | 3145 |
| longest_way | 53963 |
| site | 792 |

| relation owner_basis | relations |
|---|---|
| from_way | 2 |
| via_node | 373 |
| via_way | 22 |

Ways in `edges_zone` but missing from the base extract `ring1_roads.osm`: **66** (no geometry, no nodes; listed with `in_base_extract=False`). Ways owned through the nearest-face fallback (zone 0 faces, islands, water): **42**; nodes: **0**. Relations with a member missing from the extract: 4.

**Discrepancy.** The base extract was cut with `osmium extract -p ring1.geojson --strategy complete_ways`, which keeps a way only when one of its nodes lies inside the polygon. The 66 ways above belong to RING 1 edges by rule D3 (an end cluster inside the polygon) but have no node inside it, so they are absent from `ring1_roads.osm` and from every zone package. Owners of the 66: zone 1: 7, zone 2: 19, zone 3: 5, zone 5: 3, zone 6: 7, zone 7: 6, zone 8: 6, zone 9: 13. Not changed here; the packages are cut from the base file as specified.

| pilot zone | way | segment highway | length m |
|---|---|---|---|
| 3 | 301893757 | service | 44.76 |
| 3 | 301893758 | service | 62.89 |
| 3 | 1090301197 | service | 15.17 |
| 3 | 1117107774 | service | 89.17 |
| 3 | 1118041070 | service | 12.07 |

Nodes that belong to a site in one zone and to a junction cluster in another (signal or tram-crossing nodes attached to a site by proximity): **7**. The task text does not rank the two rules; the junction cluster wins (it is the atomic editing unit) and the node is flagged `site_zone_conflict` in `ownership_nodes.csv`.

| node | site | site zone | cluster | cluster zone (owner) |
|---|---|---|---|---|
| 173178354 | 46 | 3 | 371 | 10 |
| 312606382 | 27 | 3 | 3121 | 10 |
| 1297337833 | 21 | 10 | 6435 | 8 |
| 1299373989 | 51 | 8 | 6436 | 9 |
| 2428025531 | 46 | 3 | 371 | 10 |
| 3438315710 | 97 | 3 | 13901 | 4 |
| 5042243602 | 291 | 10 | 18346 | 8 |

### Spanning ways and shared nodes

Spanning ways: **223** in total (**90** through `edges_zone`, 133 through face geometry). Shared nodes: **614**.

| zone pair | spanning ways | shared nodes |
|---|---|---|
| 1-2 | 10 | 28 |
| 1-3 | 3 | 11 |
| 1-11 | 12 | 35 |
| 2-3 | 3 | 30 |
| 3-4 | 22 | 66 |
| 3-8 | 0 | 3 |
| 3-10 | 12 | 37 |
| 4-5 | 24 | 66 |
| 4-8 | 9 | 24 |
| 5-6 | 41 | 65 |
| 5-8 | 0 | 5 |
| 6-7 | 24 | 52 |
| 6-8 | 0 | 1 |
| 7-8 | 19 | 45 |
| 8-9 | 14 | 50 |
| 8-10 | 8 | 19 |
| 9-10 | 15 | 47 |
| 9-11 | 3 | 8 |
| 10-11 | 6 | 28 |

The 20 longest spanning ways:

| way | highway | name | length m | shares | owner | basis |
|---|---|---|---|---|---|---|
| 862075030 | tram |  | 1150.46 | 9:0.6738;8:0.3262 | 9 | face_geometry |
| 207220708 | tertiary | Na Grobli | 1089.81 | 3:0.7555;4:0.2445 | 3 | edges_zone |
| 184500800 | disused |  | 920.03 | 5:0.7209;4:0.2791 | 5 | face_geometry |
| 115083604 | tertiary | Henryka Sienkiewicza | 536.47 | 2:0.6500;1:0.3500 | 2 | edges_zone |
| 115616475 | residential | Stefana Żeromskiego | 471.35 | 1:0.7930;2:0.2070 | 1 | edges_zone |
| 84822919 | tertiary | Tadeusza Kościuszki | 330.29 | 5:0.5807;4:0.4193 | 5 | edges_zone |
| 27717916 | residential | Generała Ignacego Prądzyńskiego | 327.02 | 4:0.6946;5:0.3054 | 4 | edges_zone |
| 22734955 | residential | Stanisława Więckowskiego | 322.33 | 5:0.5380;4:0.4620 | 5 | edges_zone |
| 28458115 | secondary | Podwale | 315.63 | 4:0.9590;3:0.0410 | 4 | edges_zone |
| 632644115 | path |  | 307.61 | 6:0.6431;5:0.3569 | 6 | face_geometry |
| 23283447 | tertiary | Komuny Paryskiej | 283.71 | 4:0.8338;5:0.1662 | 4 | edges_zone |
| 1451049811 | tertiary | Henryka Sienkiewicza | 277.14 | 1:0.6739;2:0.3261 | 1 | edges_zone |
| 16313057 | tertiary | Piaskowa | 256.86 | 3:0.6645;10:0.3355 | 3 | edges_zone |
| 1513859759 | service |  | 255.43 | 7:0.8729;8:0.1271 | 7 | edges_zone |
| 17787687 | tertiary | Tadeusza Kościuszki | 230.01 | 8:0.5746;7:0.4254 | 8 | edges_zone |
| 136989160 | residential | Wojciecha Cybulskiego | 227.18 | 11:0.9161;1:0.0839 | 11 | edges_zone |
| 421984616 | path |  | 198.95 | 4:0.8770;3:0.1230 | 4 | edges_zone |
| 17787689 | unclassified | Wojciecha Bogusławskiego | 198.1 | 6:0.8665;7:0.1335 | 6 | edges_zone |
| 114549380 | secondary | Kazimierza Wielkiego | 141.89 | 10:0.6024;8:0.3976 | 10 | edges_zone |
| 189500474 | secondary | Świdnicka | 133.3 | 8:0.9542;7:0.0458 | 8 | edges_zone |

Same, only network ways (`edges_zone`/bridge group):

| way | highway | name | length m | shares | owner |
|---|---|---|---|---|---|
| 207220708 | tertiary | Na Grobli | 1089.81 | 3:0.7555;4:0.2445 | 3 |
| 115083604 | tertiary | Henryka Sienkiewicza | 536.47 | 2:0.6500;1:0.3500 | 2 |
| 115616475 | residential | Stefana Żeromskiego | 471.35 | 1:0.7930;2:0.2070 | 1 |
| 84822919 | tertiary | Tadeusza Kościuszki | 330.29 | 5:0.5807;4:0.4193 | 5 |
| 27717916 | residential | Generała Ignacego Prądzyńskiego | 327.02 | 4:0.6946;5:0.3054 | 4 |
| 22734955 | residential | Stanisława Więckowskiego | 322.33 | 5:0.5380;4:0.4620 | 5 |
| 28458115 | secondary | Podwale | 315.63 | 4:0.9590;3:0.0410 | 4 |
| 23283447 | tertiary | Komuny Paryskiej | 283.71 | 4:0.8338;5:0.1662 | 4 |
| 1451049811 | tertiary | Henryka Sienkiewicza | 277.14 | 1:0.6739;2:0.3261 | 1 |
| 16313057 | tertiary | Piaskowa | 256.86 | 3:0.6645;10:0.3355 | 3 |
| 1513859759 | service |  | 255.43 | 7:0.8729;8:0.1271 | 7 |
| 17787687 | tertiary | Tadeusza Kościuszki | 230.01 | 8:0.5746;7:0.4254 | 8 |
| 136989160 | residential | Wojciecha Cybulskiego | 227.18 | 11:0.9161;1:0.0839 | 11 |
| 421984616 | path |  | 198.95 | 4:0.8770;3:0.1230 | 4 |
| 17787689 | unclassified | Wojciecha Bogusławskiego | 198.1 | 6:0.8665;7:0.1335 | 6 |
| 114549380 | secondary | Kazimierza Wielkiego | 141.89 | 10:0.6024;8:0.3976 | 10 |
| 189500474 | secondary | Świdnicka | 133.3 | 8:0.9542;7:0.0458 | 8 |
| 1002026904 | service |  | 129.84 | 4:0.8494;8:0.1506 | 4 |
| 16313068 | tertiary | Stawowa | 129.13 | 7:0.6352;6:0.3648 | 7 |
| 187980661 | tertiary | Księdza Piotra Skargi | 123.13 | 4:0.8677;8:0.1323 | 4 |

## Frozen pilot zones

`data/derived/zones_v02_frozen.gpkg`: layers `zones_v02`, `edges_zone`, `clusters_zone`, `seam_edges` (owned by or read-buffer of a pilot zone), `bridge_groups`, `bridges`, `islands`; zone attributes `s0_minutes`, `units`, `sites`, `tram_ways`, `edges`.

Label-drift guard (relative tolerance 1%):

| zone | units (expected / actual) | S0 minutes (expected / actual) | sites | tram ways |
|---|---|---|---|---|
| 3 | 671 / 671 | 2219 / 2219.2 | 35 / 35 | 59 / 59 |
| 4 | 705 / 705 | 2158 / 2157.8 | 36 / 36 | 22 / 22 |

## Zone 3

### Composition

| item | value |
|---|---|
| work units owned | 671 |
| work units in `zone_3_units.csv` | 644 |
| S0 minutes after ownership | 2219.2 |
| sites (small 1-2 / medium 3-9 / large >= 10) | 35 (27 / 6 / 2) |
| sites with a signal / with a tram crossing | 11 / 12 |
| edges A / B-core / B-service / C | 210 / 79 / 83 / 158 |
| tram ways | 59 |
| km by tier_tag A (of which tram) / B / C | 17.47 (7.00) / 9.51 / 6.55 |

### OSM extract

`data/derived/zones_v02/zone_3/zone_3.osm`: 8415 nodes, 2360 ways, 75 relations (sha256 `7b0357a45036150f...`, base `e8c7c3d881f67130...`).

|  | owned by zone 3 | read-only, other zone | unowned (outside RING 1) |
|---|---|---|---|
| ways | 1694 | 666 | 0 |
| nodes | 5657 | 2758 | 0 |
| relations | 52 | 23 | 0 |

### Neighbours and seams

| neighbour | pilot pair | seam edges | of which owned by 3 | seam length km | treatment |
|---|---|---|---|---|---|
| 1 | no | 7 | 7 | 0.31 | read-only buffer |
| 2 | no | 12 | 12 | 2.25 | read-only buffer |
| 4 | yes | 21 | 12 | 1.14 | shared by the two raters |
| 8 | no | 1 | 1 | 0.02 | read-only buffer |
| 10 | no | 8 | 7 | 0.61 | read-only buffer |

Seam edges excluded from `zone_3_units.csv` (owned by 3, towards a non-pilot zone): **27** (22 of them bridge-group edges; 3.09 km; 98.0 S0 minutes).

### Spanning ways touching the zone

40 spanning ways have length in zone 3; by partner zone: 1: 3, 2: 3, 4: 22, 10: 12.

| way | highway | name | length m | shares | owner |
|---|---|---|---|---|---|
| 207220708 | tertiary | Na Grobli | 1089.81 | 3:0.7555;4:0.2445 | 3 |
| 28458115 | secondary | Podwale | 315.63 | 4:0.9590;3:0.0410 | 4 |
| 16313057 | tertiary | Piaskowa | 256.86 | 3:0.6645;10:0.3355 | 3 |
| 421984616 | path |  | 198.95 | 4:0.8770;3:0.1230 | 4 |
| 546630808 | tertiary | Zygmunta Krasińskiego | 120.04 | 4:0.9141;3:0.0859 | 4 |
| 311900065 | footway |  | 117.61 | 3:0.6579;10:0.3421 | 3 |
| 27717899 | tertiary | plac Generała Walerego Wróblewskiego | 104.08 | 3:0.7677;4:0.2323 | 3 |
| 372275282 | path |  | 100.65 | 3:0.7923;4:0.2077 | 3 |
| 187980732 | secondary | Generała Romualda Traugutta | 96.61 | 3:0.6149;4:0.3851 | 3 |
| 164210871 | tertiary | Walońska | 86.56 | 4:0.7879;3:0.2121 | 4 |
| 311444370 | path |  | 71.87 | 4:0.9307;3:0.0693 | 4 |
| 784029981 | cycleway |  | 62.76 | 4:0.7187;3:0.2813 | 4 |
| 51179164 | living_street | Katedralna | 59.04 | 1:0.9335;3:0.0665 | 3 |
| 163865480 | path | przejście Oławskie | 57.88 | 4:0.9313;3:0.0687 | 4 |
| 436613760 | path | Żabia kładka | 53.94 | 3:0.5621;1:0.4379 | 3 |

### Bridge groups and islands

| kind | id | name | edge ids | way ids | other zone | length m | area m2 | end nodes owned elsewhere |
|---|---|---|---|---|---|---|---|---|
| bridge_group | 1 | Most Piaskowy | -284;-278;322 | 16313065;51943719;51943721;178312981;178312988 | 10 | 140.7 |  |  |
| bridge_group | 6 | Kardynała Stefana Wyszyńskiego | -1041;-19;468;469;14070;23887;35919 | 16752115;16752117;16752118;21751090;27582033;115117541;117370609;117370611;188337231;188337254;274285413;274554257;322657364;371352966;389858722;408334938;408334941;503032832;511282431;511282432;624099659;787515407;899622453;899622454;899622457;899622458;899622459;899622460;899622461;899622463;899622464;899622466;899622467 | 2 | 1458.2 |  | 11811708916@2;185460721@2;3702470623@2;4616718959@2;8358678200@2;8358678201@2 |
| bridge_group | 7 | most Grunwaldzki | -254;-253;470;14489;16248 | 16752120;125370119;127897753;133866975;164216271;164216275;164216279;178280409;178280410;233303587;233303588;342167793;342167795;369298562;511438509;583231221 | 2 | 792.09 |  | 1886484802@2;1886484804@2;2416791832@2;311408076@2;5003341313@2 |
| bridge_group | 9 | Wyspa Słodowa | 5705 | 27833797;27833799;27833805 |  | 32.23 |  |  |
| bridge_group | 10 | Most Tumski | 6231 | 28354584;28354585;51179164;761992024 | 1 | 68.37 |  | 254858099@2 |
| bridge_group | 11 | Most Młyński Północny | -282;-281;-280;-276;6363;13354 | 28354639;28354640;98750126;98750139;178312979;178312983;178312984;178312985;354668449;354668450;360786757 | 1 | 238.24 |  | 167074547@1;1886774155@1;1886774157@1 |
| bridge_group | 12 |  | 11715 | 52007097;335275279;1157376479 |  | 84.92 |  |  |
| island | 3 | Most Piaskowy | -284 | 178312988 |  |  | 43380.7 |  |
| island | 4 | Wyspa Słodowa | 5705 | 27833797;27833805;27833799 |  |  | 26912.4 |  |
| island | 5 |  | 11715 | 1157376479;52007097;335275279 |  |  | 14171.3 |  |
| island | 6 | Most Młyński Północny | -282 | 178312985 |  |  | 6122.6 |  |

Owned bridge ways: 75; with an end node owned by another zone: **15** (editing those touches another zone's junction). Full list: `zone_3_bridge_ways.csv`.

| group | way | highway | name | way length m | end A (owner) | end B (owner) | other-zone end nodes |
|---|---|---|---|---|---|---|---|
| 6 | 27582033 | tram |  | 117.41 | 8358678193 (3) | 8358678200 (2) | 8358678200 |
| 6 | 115117541 | secondary | Kardynała Stefana Wyszyńskiego | 84.68 | 1302027827 (3) | 3702470623 (2) | 3702470623 |
| 6 | 117370609 | path |  | 13.87 | 3706627107 (3) | 4616718959 (2) | 4616718959 |
| 6 | 188337231 | secondary | Kardynała Stefana Wyszyńskiego | 185.32 | 11811708916 (2) | 165109891 (3) | 11811708916 |
| 6 | 787515407 | secondary | Kardynała Stefana Wyszyńskiego | 32.24 | 3702470623 (2) | 185460721 (2) | 3702470623;185460721 |
| 6 | 899622461 | tram |  | 117.39 | 8358678201 (2) | 8358678192 (3) | 8358678201 |
| 7 | 133866975 | secondary | most Grunwaldzki | 16.14 | 311408076 (2) | 173178507 (3) | 311408076 |
| 7 | 178280409 | tram |  | 114.53 | 1886484804 (2) | 1886484792 (3) | 1886484804 |
| 7 | 178280410 | tram |  | 114.49 | 1886484790 (3) | 1886484802 (2) | 1886484802 |
| 7 | 233303587 | path |  | 10.52 | 2416791832 (2) | 4946141968 (3) | 2416791832 |
| 7 | 511438509 | path |  | 6.0 | 5003341313 (2) | 5002731322 (3) | 5003341313 |
| 10 | 51179164 | living_street | Katedralna | 59.04 | 6482314564 (3) | 254858099 (2) | 254858099 |
| 11 | 178312979 | tram |  | 35.46 | 1886774148 (3) | 1886774155 (1) | 1886774155 |
| 11 | 178312984 | tram |  | 34.81 | 1886774157 (1) | 1886774151 (3) | 1886774157 |
| 11 | 354668449 | living_street | plac Generała Józefa Bema | 17.59 | 2964724282 (3) | 167074547 (1) | 167074547 |

## Zone 4

### Composition

| item | value |
|---|---|
| work units owned | 705 |
| work units in `zone_4_units.csv` | 682 |
| S0 minutes after ownership | 2157.8 |
| sites (small 1-2 / medium 3-9 / large >= 10) | 36 (29 / 6 / 1) |
| sites with a signal / with a tram crossing | 12 / 4 |
| edges A / B-core / B-service / C | 151 / 88 / 123 / 258 |
| tram ways | 22 |
| km by tier_tag A (of which tram) / B / C | 11.19 (4.36) / 8.69 / 9.58 |

### OSM extract

`data/derived/zones_v02/zone_4/zone_4.osm`: 7959 nodes, 2204 ways, 63 relations (sha256 `1cc40f508fdd759f...`, base `e8c7c3d881f67130...`).

|  | owned by zone 4 | read-only, other zone | unowned (outside RING 1) |
|---|---|---|---|
| ways | 1489 | 715 | 0 |
| nodes | 4933 | 3026 | 0 |
| relations | 29 | 34 | 0 |

### Neighbours and seams

| neighbour | pilot pair | seam edges | of which owned by 4 | seam length km | treatment |
|---|---|---|---|---|---|
| 3 | yes | 21 | 9 | 1.14 | shared by the two raters |
| 5 | no | 32 | 20 | 1.48 | read-only buffer |
| 8 | no | 5 | 3 | 0.38 | read-only buffer |

Seam edges excluded from `zone_4_units.csv` (owned by 4, towards a non-pilot zone): **23** (0 of them bridge-group edges; 1.20 km; 88.0 S0 minutes).

### Spanning ways touching the zone

55 spanning ways have length in zone 4; by partner zone: 3: 22, 5: 24, 8: 9.

| way | highway | name | length m | shares | owner |
|---|---|---|---|---|---|
| 207220708 | tertiary | Na Grobli | 1089.81 | 3:0.7555;4:0.2445 | 3 |
| 184500800 | disused |  | 920.03 | 5:0.7209;4:0.2791 | 5 |
| 84822919 | tertiary | Tadeusza Kościuszki | 330.29 | 5:0.5807;4:0.4193 | 5 |
| 27717916 | residential | Generała Ignacego Prądzyńskiego | 327.02 | 4:0.6946;5:0.3054 | 4 |
| 22734955 | residential | Stanisława Więckowskiego | 322.33 | 5:0.5380;4:0.4620 | 5 |
| 28458115 | secondary | Podwale | 315.63 | 4:0.9590;3:0.0410 | 4 |
| 23283447 | tertiary | Komuny Paryskiej | 283.71 | 4:0.8338;5:0.1662 | 4 |
| 421984616 | path |  | 198.95 | 4:0.8770;3:0.1230 | 4 |
| 1002026904 | service |  | 129.84 | 4:0.8494;8:0.1506 | 4 |
| 187980661 | tertiary | Księdza Piotra Skargi | 123.13 | 4:0.8677;8:0.1323 | 4 |
| 464556002 | path |  | 122.03 | 5:0.8580;4:0.1420 | 5 |
| 114998052 | tertiary | Komuny Paryskiej | 121.35 | 4:0.9107;5:0.0893 | 4 |
| 546630808 | tertiary | Zygmunta Krasińskiego | 120.04 | 4:0.9141;3:0.0859 | 4 |
| 229650097 | secondary | Podwale | 105.69 | 4:0.8219;5:0.1781 | 4 |
| 27717899 | tertiary | plac Generała Walerego Wróblewskiego | 104.08 | 3:0.7677;4:0.2323 | 3 |

### Bridge groups and islands

Zone 4 owns no bridge groups and no islands.

## Pilot pair seam (zones 3 and 4)

Seam edges between the two zones: **21**, 1.14 km (expected 21 edges, 1.14 km). Marked `pilot_pair_seam = true` in both seams files; the seams with the other neighbours are marked `read_only_neighbour = true`.

Ways spanning both zones: **22**.

| way | highway | name | length m | shares | owner |
|---|---|---|---|---|---|
| 207220708 | tertiary | Na Grobli | 1089.81 | 3:0.7555;4:0.2445 | 3 |
| 28458115 | secondary | Podwale | 315.63 | 4:0.9590;3:0.0410 | 4 |
| 421984616 | path |  | 198.95 | 4:0.8770;3:0.1230 | 4 |
| 546630808 | tertiary | Zygmunta Krasińskiego | 120.04 | 4:0.9141;3:0.0859 | 4 |
| 27717899 | tertiary | plac Generała Walerego Wróblewskiego | 104.08 | 3:0.7677;4:0.2323 | 3 |
| 372275282 | path |  | 100.65 | 3:0.7923;4:0.2077 | 3 |
| 187980732 | secondary | Generała Romualda Traugutta | 96.61 | 3:0.6149;4:0.3851 | 3 |
| 164210871 | tertiary | Walońska | 86.56 | 4:0.7879;3:0.2121 | 4 |
| 311444370 | path |  | 71.87 | 4:0.9307;3:0.0693 | 4 |
| 784029981 | cycleway |  | 62.76 | 4:0.7187;3:0.2813 | 4 |
| 163865480 | path | przejście Oławskie | 57.88 | 4:0.9313;3:0.0687 | 4 |
| 301676189 | service |  | 27.54 | 4:0.7600;3:0.2400 | 4 |
| 191640877 | secondary | Kujawska | 26.48 | 3:0.5385;4:0.4615 | 3 |
| 402785398 | path |  | 16.4 | 3:0.6063;4:0.3937 | 3 |
| 369525525 | footway |  | 16.32 | 3:0.6247;4:0.3753 | 3 |
| 467386907 | footway |  | 16.04 | 4:0.7073;3:0.2927 | 4 |
| 312075500 | service |  | 12.48 | 3:0.8528;4:0.1472 | 3 |
| 366799080 | footway |  | 11.2 | 4:0.5443;3:0.4557 | 4 |
| 365836478 | footway |  | 10.94 | 4:0.6815;3:0.3185 | 4 |
| 784029983 | service |  | 8.89 | 3:0.6337;4:0.3663 | 3 |
| 520621554 | footway |  | 8.29 | 4:0.5031;3:0.4969 | 4 |
| 366799074 | cycleway |  | 7.18 | 4:0.5422;3:0.4578 | 4 |

Nodes shared between ways owned by zone 3 and ways owned by zone 4: **66** (`data/derived/zones_v02/pilot_pair_shared_nodes.csv`).

| node | owner | basis | ways of zone 3 | ways of zone 4 |
|---|---|---|---|---|
| 165109460 | 4 | cluster | 187980640;187980679 | 16313072;187980674 |
| 165109463 | 4 | cluster | 16313071 | 114549381;187980657;481682857 |
| 185460602 | 3 | cluster | 28458114;28458117;114815953;327636497 | 28458115 |
| 269291570 | 4 | cluster | 114815953 | 29447978;53212283 |
| 302964911 | 3 | longest_way | 183214674 | 27687600;159093708 |
| 304383402 | 4 | cluster | 25014457;27717899 | 27717900;149115902 |
| 304383630 | 4 | longest_way | 27717917 | 164210871 |
| 344662756 | 3 | longest_way | 30999369 | 27687600;36575421 |
| 1601818624 | 3 | cluster | 366799070;1040173975 | 146988600;314550827;1040173972 |
| 1601818629 | 4 | cluster | 28458117 | 146988603 |
| 1601818630 | 3 | site | 28458117 | 366799080 |
| 1657121732 | 3 | longest_way | 27717899 | 311444370 |
| 1657121749 | 4 | longest_way | 191640877 | 191640878 |
| 1886574925 | 3 | longest_way | 30999369 | 375912817 |
| 1886574939 | 3 | longest_way | 182831021 | 159093708;182831018 |
| 1886575019 | 4 | longest_way | 182382633;182382646 | 178292073 |
| 1886734488 | 4 | longest_way | 178309644;183114206 | 178309646 |
| 1886734490 | 4 | longest_way | 178309647;182422756 | 178458097 |
| 1986129361 | 4 | longest_way | 402785398;497692544 | 464526906 |
| 1986129364 | 3 | longest_way | 402785398 | 1040173973 |
| 1986129367 | 3 | cluster | 114959439;187980738;187980770;672838076 | 546630808 |
| 2013583187 | 4 | cluster | 190721409 | 187980674;481682856;481682857 |
| 2015842523 | 4 | site | 369525525 | 191640878 |
| 2834021413 | 4 | cluster | 27717902 | 164210871;784029979 |
| 3171117622 | 4 | cluster | 506116434;763481098 | 27717900;505067338;784029967 |
| 3178926211 | 4 | cluster | 247597656;672838076 | 672838075 |
| 3178926218 | 4 | longest_way | 312075500 | 996255019 |
| 3374033511 | 4 | longest_way | 330442979 | 163865480 |
| 3374033513 | 4 | longest_way | 330442978 | 163865480 |
| 3438333366 | 3 | site | 497692537 | 178292073 |
| 3698409154 | 3 | longest_way | 365836486 | 365836478 |
| 3707768575 | 3 | longest_way | 1040173975 | 366799074 |
| 3707768633 | 4 | longest_way | 366799067 | 366799080 |
| 3733061103 | 3 | longest_way | 369525525 | 508228358 |
| 3758276603 | 3 | cluster | 207220708 | 301676189 |
| 3758276993 | 4 | cluster | 27717918;207220708;301893748 | 301676180 |
| 3899360436 | 4 | longest_way | 683402563 | 164210871;683402565 |
| 4217090400 | 4 | cluster | 421983575 | 1547548778 |
| 4217102920 | 4 | cluster | 187980732 | 1302108327 |
| 4217102928 | 3 | cluster | 564048466 | 421984616 |
| 4396704237 | 4 | cluster | 187980732 | 441980499 |
| 4444323238 | 4 | cluster | 207220708 | 447263660 |
| 4444323239 | 3 | longest_way | 372275282 | 520621556 |
| 4444323240 | 3 | longest_way | 207220708 | 520621554 |
| 4475427648 | 3 | cluster | 312075500 | 421984616 |
| 4620138013 | 3 | cluster | 372275282;784029980;784029983 | 467384779 |
| 4620151772 | 3 | longest_way | 207220708 | 467386907 |
| 4620381833 | 3 | longest_way | 447263659 | 520621554 |
| 4623182383 | 3 | cluster | 402785398 | 546630808 |
| 4623471366 | 4 | cluster | 27717899 | 1235839777 |
| 4623471383 | 3 | longest_way | 187980732 | 672838072 |
| 4623864729 | 4 | longest_way | 467783986 | 311444370 |
| 4975643462 | 4 | cluster | 508228370;508228402 | 498093164;1050213349 |
| 5435088381 | 3 | cluster | 497692543;497692544 | 421984616 |
| 6300861519 | 4 | cluster | 672838074 | 672838075;996255021 |
| 6563523269 | 3 | cluster | 698949694 | 698949695;698949697 |
| 7134274502 | 4 | cluster | 27717904;763481098;1068804183 | 164245550 |
| 7323602676 | 4 | longest_way | 784029982 | 784029981 |
| 7323650893 | 4 | cluster | 372275282 | 301676180 |
| 7323650895 | 4 | longest_way | 372275282 | 683661687;784029984 |
| 9204975338 | 3 | cluster | 1074151461 | 163865480 |
| 9807185628 | 3 | longest_way | 511346007 | 505067338 |
| 9852821845 | 4 | longest_way | 163865486 | 163865480 |
| 10459628177 | 4 | cluster | 207220708 | 1129836569 |
| 10942461589 | 4 | longest_way | 1177925032 | 467386907 |
| 11473154314 | 4 | site | 30999369 | 114979745 |

## Files

- `data/derived/zones_v02/ownership_nodes.csv`
- `data/derived/zones_v02/ownership_relations.csv`
- `data/derived/zones_v02/ownership_ways.csv`
- `data/derived/zones_v02/pilot_pair_shared_nodes.csv`
- `data/derived/zones_v02/zone_3/zone_3.geojson`
- `data/derived/zones_v02/zone_3/zone_3.json`
- `data/derived/zones_v02/zone_3/zone_3.osm`
- `data/derived/zones_v02/zone_3/zone_3_bridge_ways.csv`
- `data/derived/zones_v02/zone_3/zone_3_bridges.csv`
- `data/derived/zones_v02/zone_3/zone_3_reference.osm`
- `data/derived/zones_v02/zone_3/zone_3_seams.csv`
- `data/derived/zones_v02/zone_3/zone_3_units.csv`
- `data/derived/zones_v02/zone_4/zone_4.geojson`
- `data/derived/zones_v02/zone_4/zone_4.json`
- `data/derived/zones_v02/zone_4/zone_4.osm`
- `data/derived/zones_v02/zone_4/zone_4_bridge_ways.csv`
- `data/derived/zones_v02/zone_4/zone_4_bridges.csv`
- `data/derived/zones_v02/zone_4/zone_4_reference.osm`
- `data/derived/zones_v02/zone_4/zone_4_seams.csv`
- `data/derived/zones_v02/zone_4/zone_4_units.csv`
- `data/derived/zones_v02_frozen.gpkg`
- `data/interim/zones_v02/zones_v02_ownership.gpkg`
