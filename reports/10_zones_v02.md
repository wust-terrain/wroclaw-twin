# Task 03c: barrier-aware, block-based partition of RING 1 (v0.2)

Analysis only. All numbers in `config/22_partition_blocks.yaml` are `[PROPOSED]`; work weights are the unmeasured S0 proxy of task 03a. Nothing here changes `scope.yaml`, the polygon, D2-D4, `tiers.yaml` or the v0 results. Decisions applied from the project owner: allocation 8 + 3 zones (`region_zones.csv`), R4 relaxed to 1.10 on face minutes and 1.12 on minutes after ownership, R1 = no zone has land faces of both large regions, bridge groups with one owner, edges inside site hulls follow the site, faces above 350 minutes subdivided.

## Checks

| Check | Expected | Actual | Result |
|---|---|---|---|
| segment units found for all RING 1 edges + tram ways | 6255 | 6255 | PASS |
| tier_tag in units == tier_tag in ownership layer (edges) | 0 | 0 | PASS |
| inside_through edges have both end clusters among the vertices | 0 | 0 | PASS |
| sites | 341 | 341 | PASS |
| road edges in RING 1 | 5804 | 5804 | PASS |
| tram-only ways in RING 1 | 451 | 451 | PASS |
| faces cover RING 1 area (m2 difference) | 0 | 0.0 | PASS |
| units attached to faces | 7018 | 7018.0 | PASS |
| S0 minutes attached to faces == item minutes | 21882.8 | 21882.8 | PASS |
| R1 zones with land faces in both large regions | 0 | 0 | PASS |
| R2 sites split between zones | 0 | 0 | PASS |
| R2 seam edges inside a site hull | 0 | 0 | PASS |
| R2 zone-polygon borders entering a site hull shrunk by 3 m | 0 | 0 | PASS |
| R2/R3 zones not connected (faces) | 0 | 0 | PASS |
| R3 zone polygons in one piece (zones with extra parts: islands and bridge strips of other zones, listed) | 0 | 0 | PASS |
| R3 zone polygons: detached pieces that are neither island land nor bridge strip | 0 | 0 | PASS |
| units sum to total | 7018 | 7018 | PASS |
| R4 balance max/mean on face minutes <= 1.1 | <= 1.1 | 1.094 | PASS |
| R4 balance max/mean on S0 minutes after ownership <= 1.12 | <= 1.12 | 1.116 | PASS |
| bridge groups with more than one owner | 0 | 0 | PASS |
| Dmowskiego bridge edges have one owner | 1 | 1 | PASS |
| R5 face / island / bridge overrides refused | 0 | 0 | PASS |
| R5 override test (changes result, rerun identical, removal restores baseline) | yes | yes | PASS |
| all 11 zones non-empty | 11 | 11 | PASS |
| R1 counters assigned to zones | 23 | 23 | PASS |

## 1. Barriers (water features)

Source: frozen snapshot, `osmium tags-filter nwr/natural=water nwr/waterway=river,canal,riverbank nwr/water=river,canal`, extract bbox `17.00914,51.08883,17.06413,51.12743` (RING 1 bbox + 500 m, strategy smart), `osmium export`. Full table (128 features with non-zero length or area inside RING 1): `reports/water_features.csv`. Island and ring ways pulled in by `osmium` as multipolygon members are not water features and are dropped.

`barriers.names` = ['Odra', 'Odra Północna', 'Odra Południowa']; `include_moat` = False. A waterway line is a barrier when its name is in the list; a water polygon is a barrier when it contains at least 30 m of such a line (the Odra polygons carry no name in OSM). Lines buffered by 5 m; barrier area clipped to RING 1: **40.6 ha** in 1 polygon(s).

| id | tags | area m2 in RING 1 | reason |
|---|---|---|---|
| a340917 | natural=water;water=river | 120335 | contains 2208 m of a selected line |
| a340919 | natural=water;water=river | 103680 | contains 1775 m of a selected line |
| a2129626558 | natural=water;water=river | 61378 | contains 571 m of a selected line |
| a2129626556 | natural=water;water=river | 40892 | contains 347 m of a selected line |
| a65846856 | natural=water;water=river | 36946 | contains 639 m of a selected line |
| a736001006 | natural=water;water=river | 28127 | contains 220 m of a selected line |
| a2128678360 | natural=water;water=river | 14989 | contains 187 m of a selected line |

| selected waterway name | ways | length in RING 1 (m) |
|---|---|---|
| Odra | 3 | 1198 |
| Odra Południowa | 15 | 2909 |
| Odra Północna | 6 | 1839 |

Named water features inside RING 1 that are **not** barriers (for your review; add a name to `barriers.names` to include it):

| name | features | area m2 | length m | example tags |
|---|---|---|---|---|
| Fosa Miejska | 1 | 65923 | 0 | natural=water;water=moat |
| Zatoka Gondoli | 2 | 2771 | 247 | natural=water |
| Fontanna "Zdrój" | 2 | 116 | 55 | natural=water |
| Fontanna krasnali | 2 | 24 | 18 | natural=water;water=reservoir |
| Oława | 1 | 0 | 1308 | waterway=river |
| Upust Klary | 2 | 0 | 330 | waterway=canal |
| Kanał Młynu Maria | 4 | 0 | 298 | waterway=canal |
| Upust Powodziowy Klary | 1 | 0 | 170 | waterway=canal |
| Kanał Śluzy Piaskowej | 2 | 0 | 143 | waterway=canal |
| kanał jazu Świętego Macieja | 1 | 0 | 116 | waterway=river |
| Śluza Mieszczańska | 3 | 0 | 49 | waterway=canal;width=5.3 |
| Śluza Piaskowa | 1 | 0 | 42 | waterway=canal;width=5.3 |

Largest unnamed water polygons not selected: a206239148 (29821 m2, natural=water;water=river), a2129626554 (12029 m2, natural=water;water=river), a8524105 (4834 m2, natural=water), a2128624108 (908 m2, natural=water;water=drain), a430691 (636 m2, natural=water), a122723394 (429 m2, natural=water).


## 2. Blocks (faces)

Coarse boundaries: road fragments of classes ['motorway', 'motorway_link', 'trunk', 'trunk_link', 'primary', 'primary_link', 'secondary', 'secondary_link', 'tertiary', 'tertiary_link', 'residential', 'living_street', 'unclassified'] (no tram, cycleway, path, service), minus the barrier area, plus the barrier outline and the RING 1 boundary; noded with `unary_union`, polygonized, faces inside RING 1 kept; slivers < 200 m2 merged into the neighbour with the longest shared boundary.

Coarse faces: 358 (357 land), land area p50 6835 / p90 41824 / max 320223 m2. **4 land faces** with more than 350 S0 minutes were subdivided with ['service', 'cycleway', 'path'] added as boundaries (footway and pedestrian still excluded). New face count: **508** (507 land, 1 water); land area p50 3491 / p90 36462 / max 192945 m2. Heaviest face before the split 808 min, after 337 min; faces still above the limit: 0.


Within-region balance (zone minutes against the mean of the zones of the same region, face level):

| stage | per region (max / min against the region mean) |
|---|---|
| coarse faces (before the split), after pass | region 1: max 1.013 / min 0.982 (8 zones, mean 2135); region 2: max 1.037 / min 0.931 (3 zones, mean 1600) |
| subdivided faces, after pass | region 1: max 1.020 / min 0.976 (8 zones, mean 2135); region 2: max 1.050 / min 0.923 (3 zones, mean 1601) |

Ten heaviest faces after the split:

| face | parent face | area m2 | S0 minutes | units | region | zone |
|---|---|---|---|---|---|---|
| 308 | 202 | 161637 | 337 | 111 | 1 | 6 |
| 178 | 111 | 151072 | 336 | 107 | 1 | 8 |
| 393 | 285 | 73213 | 298 | 108 | 1 | 5 |
| 75 | 44 | 192945 | 280 | 108 | 2 | 11 |
| 219 | 145 | 63603 | 275 | 99 | 1 | 7 |
| 217 | 142 | 147883 | 266 | 94 | 1 | 10 |
| 386 | 284 | 143312 | 237 | 84 | 1 | 5 |
| 460 | 348 | 101610 | 226 | 82 | 2 | 2 |
| 261 | 173 | 61387 | 216 | 69 | 2 | 1 |
| 390 | 280 | 59413 | 210 | 74 | 1 | 4 |

Ten largest faces by area:

| face | area m2 | S0 minutes | units | region | zone |
|---|---|---|---|---|---|
| 75 | 192945 | 280 | 108 | 2 | 11 |
| 308 | 161637 | 337 | 111 | 1 | 6 |
| 178 | 151072 | 336 | 107 | 1 | 8 |
| 217 | 147883 | 266 | 94 | 1 | 10 |
| 386 | 143312 | 237 | 84 | 1 | 5 |
| 408 | 103331 | 72 | 25 | 2 | 2 |
| 460 | 101610 | 226 | 82 | 2 | 2 |
| 326 | 97793 | 154 | 50 | 1 | 4 |
| 404 | 89959 | 130 | 51 | 2 | 2 |
| 384 | 82783 | 169 | 52 | 1 | 3 |

## 3. Regions, islands and zone allocation

Region = land faces connected through shared boundaries (not through water), numbered by decreasing area. 15 regions; a region below 0.35 x mean zone minutes = 696 minutes is merged into the region reached by its best bridge (tier A first, non-tram, longest overlap, lowest edge id). The two regions that remain are the two banks (large regions); merged regions are called islands.

| region | merged into | area km2 | units | S0 minutes | bridges to other regions |
|---|---|---|---|---|---|
| 1 | 1 | 5.060 | 5396.0 | 16885.2 | 28 |
| 2 | 2 | 1.527 | 1556.7 | 4794.4 | 31 |
| 3 | 1 | 0.043 | 28.7 | 90.2 | 7 |
| 4 | 1 | 0.027 | 7.2 | 22.5 | 2 |
| 5 | 1 | 0.014 | 0.3 | 1.0 | 1 |
| 6 | 1 | 0.006 | 8.3 | 26.0 | 5 |
| 7 | 1 | 0.006 | 7.5 | 15.5 | 1 |
| 8 | 1 | 0.005 | 0.5 | 1.0 | 1 |
| 9 | 1 | 0.005 | 10.0 | 35.8 | 3 |
| 10 | 1 | 0.003 | 0.0 | 0.0 | 0 |
| 11 | 1 | 0.002 | 1.0 | 4.0 | 3 |
| 12 | 1 | 0.000 | 0.0 | 0.0 | 0 |
| 13 | 1 | 0.000 | 0.0 | 0.0 | 0 |
| 14 | 2 | 0.000 | 1.8 | 7.1 | 5 |
| 15 | 1 | 0.000 | 0.0 | 0.0 | 0 |

Allocation of the 11 zones (largest remainder, k >= 1, overridden by `region_zones.csv`):

| region | S0 minutes | quota | zones k | minutes per zone | source |
|---|---|---|---|---|---|
| 1 | 17081 | 8.586 | 8 | 2135 | override |
| 2 | 4802 | 2.414 | 3 | 1601 | override |

Mean zone minutes 1989; expected balance after allocation (lower bound): **1.073**.


## 4. Partition

Per region `pymetis.part_graph` on the face adjacency graph (vertex weight = face minutes x 10, edge weight = shared boundary in metres, contiguity on, seed 20261025), best of ufactor [20, 10, 5, 3] by imbalance. Synthetic links of weight 1 join an island to its bank over the bridge used for the merge. Tongue smoothing: up to 20 passes, a face moves to the zone that touches more than 60% of its perimeter if the face balance stays within 1.1 and the old zone stays connected. Balance pass (`balance_pass: true`): faces move from the heaviest zone of a region to a neighbour touching at least 25% of the face perimeter while the pair maximum drops.

| region | zones | repair moves | METIS imbalance inside the region |
|---|---|---|---|
| 1 | 8 | 1 | 1.010 (ufactor 3) |
| 2 | 3 | 1 | 1.050 (ufactor 20) |

Balance max/mean before and after the balance pass:

| stage | face minutes | S0 minutes after ownership |
|---|---|---|
| after METIS and tongue smoothing (before the pass) | 1.094 | 1.116 |
| after the balance pass (4 moves) and a second smoothing (3 moves) | 1.094 | 1.116 |

Within-region balance after the pass, face minutes: region 1: max 1.020 / min 0.976 (8 zones, mean 2135); region 2: max 1.050 / min 0.923 (3 zones, mean 1601). After ownership: region 1: max 1.037 / min 0.975 (8 zones, mean 2139); region 2: max 1.036 / min 0.940 (3 zones, mean 1590). Lightest zone 0.751 x mean. Tongue smoothing moves: 3.


### Overrides

`face_zone.csv`: 0 rows, applied 0, refused 0; `island_zone.csv`: 0 rows, applied 0, refused 0; `region_zones.csv`: 2 rows; `bridge_owner.csv`: 2 rows, refused 0.


### R5 override test

Test face override: (268, 6, 5) (face, current zone, new zone); test island override: (3, [3], 4) (island, current zones, new zone). Result digests: baseline 5c7e4cd608d54055, with island override only 81ee442469441e61, with both b99631f0f672ebd7, both again b99631f0f672ebd7, overrides removed again 5c7e4cd608d54055. Applied in the test: faces [(268, 6, 5)], islands [(3, [3], 4)]; refused: ([], []). The test overrides exist only in memory; the override files were not changed.


## 5. Composition of zones (after ownership)

| zone | units | sites (small/medium/large) | sites with signal | sites with tram | km road A/B/C | tram km | edges A/B-core/B-service/C | tram ways | S0 minutes (ownership) | S0 minutes (faces) | area km2 (polygon) | R1 counters |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 464 | 21 (14/7/0) | 8 | 3 | 6.0/5.8/3.9 | 1.1 | 126/86/74/117 | 22 | 1494 | 1484 | 0.36 | 4 |
| 2 | 564 | 17 (13/4/0) | 5 | 1 | 5.6/9.5/8.2 | 2.8 | 77/153/67/208 | 20 | 1628 | 1680 | 0.69 | 2 |
| 3 | 671 | 35 (27/6/2) | 11 | 12 | 10.5/9.5/6.5 | 7.0 | 210/79/83/158 | 59 | 2219 | 2137 | 0.67 | 3 |
| 4 | 705 | 36 (29/6/1) | 12 | 4 | 6.8/8.7/9.6 | 4.4 | 151/88/123/258 | 22 | 2158 | 2170 | 0.76 | 1 |
| 5 | 737 | 32 (26/5/1) | 9 | 5 | 5.6/8.5/12.4 | 3.0 | 132/104/90/315 | 24 | 2143 | 2084 | 0.71 | 2 |
| 6 | 653 | 48 (43/3/2) | 11 | 13 | 6.4/7.8/7.5 | 3.2 | 136/88/95/212 | 37 | 2089 | 2140 | 0.59 | 1 |
| 7 | 690 | 34 (27/6/1) | 10 | 3 | 6.6/8.8/8.2 | 2.9 | 182/94/112/208 | 27 | 2181 | 2145 | 0.52 | 3 |
| 8 | 678 | 29 (20/7/2) | 16 | 8 | 8.2/5.1/10.8 | 6.1 | 168/108/20/212 | 80 | 2118 | 2122 | 0.71 | 2 |
| 9 | 646 | 28 (21/6/1) | 18 | 2 | 9.7/6.4/6.7 | 4.0 | 224/87/61/163 | 45 | 2120 | 2106 | 0.56 | 2 |
| 10 | 688 | 38 (27/9/2) | 11 | 21 | 5.5/7.9/7.4 | 5.4 | 96/177/17/216 | 70 | 2085 | 2177 | 0.68 | 1 |
| 11 | 522 | 23 (21/0/2) | 4 | 4 | 5.1/7.3/5.4 | 3.5 | 108/93/85/143 | 45 | 1647 | 1638 | 0.49 | 2 |
| **all** | 7018 | 341 (268/59/14) | 115 | 76 | 76.1/85.3/86.5 | 43.3 | 1610/1157/827/2210 | 451 | 21883 | 21883 | 6.73 | 23 |

Balance max/mean: **1.116** on the minutes after ownership (target 1.12), **1.094** on the face minutes (target 1.1).


## 6. Compactness (area / convex hull area, perimeter / sqrt(area)); v0 zones matched by shared S0 minutes

| zone v0.2 | area/hull v0.2 | area/hull v0 | perimeter/sqrt(area) v0.2 | perimeter/sqrt(area) v0 | matched v0 zone | flag |
|---|---|---|---|---|---|---|
| 1 | 0.648 | 0.780 | 6.17 | 7.53 | 11 | worse |
| 2 | 0.834 | 0.811 | 4.66 | 6.15 | 1 |  |
| 3 | 0.650 | 0.688 | 8.38 | 8.48 | 2 | worse |
| 4 | 0.856 | 0.750 | 4.98 | 10.15 | 3 |  |
| 5 | 0.818 | 0.740 | 5.23 | 9.25 | 4 |  |
| 6 | 0.858 | 0.754 | 4.93 | 7.81 | 6 |  |
| 7 | 0.883 | 0.809 | 4.82 | 7.91 | 7 |  |
| 8 | 0.800 | 0.569 | 5.36 | 12.08 | 5 |  |
| 9 | 0.714 | 0.741 | 5.83 | 9.28 | 8 | worse |
| 10 | 0.780 | 0.769 | 7.13 | 6.89 | 9 | worse |
| 11 | 0.744 | 0.866 | 7.23 | 6.13 | 10 | worse |

## 7. Seam edges per zone pair

Seam edge = an edge whose faces belong to different zones, owner by the larger sum of `max_degree` of its end clusters in the zone (tie: lower zone id); edges inside a site hull and edges of bridge groups are handled by the hull and group rules. Total: **252 edges, 16.74 km**.

| zone pair | seam edges | km |
|---|---|---|
| 1-2 | 17 | 0.74 |
| 1-3 | 7 | 0.31 |
| 1-11 | 15 | 1.50 |
| 2-3 | 12 | 2.25 |
| 3-4 | 21 | 1.14 |
| 3-8 | 1 | 0.02 |
| 3-10 | 8 | 0.61 |
| 4-5 | 32 | 1.48 |
| 4-8 | 5 | 0.38 |
| 5-6 | 22 | 1.23 |
| 5-8 | 4 | 0.21 |
| 6-7 | 24 | 1.00 |
| 6-8 | 2 | 0.09 |
| 7-8 | 21 | 1.22 |
| 8-9 | 10 | 0.78 |
| 8-10 | 17 | 0.81 |
| 9-10 | 17 | 0.84 |
| 9-11 | 6 | 1.35 |
| 10-11 | 11 | 0.78 |

## 8. Bridge groups and owners

Bridge = an edge with more than 3 m inside the barrier area (road and tram-only ways). Group = equal name, or over-water parts within 40 m of each other. One owner per group: among the zones whose faces touch the group, the zone with the larger sum of `max_degree` of the distinct end clusters of the whole group in it (tie: more faces, then lower zone id); a zone without land at the bridge could not join its strip to its polygon. Strip = group buffered by 12 m, clipped to the barrier area, added to the owner's polygon.

| group | name | edges | tiers | owner zone | other zone | max_degree sums |
|---|---|---|---|---|---|---|
| 1 | Most Piaskowy | 1 road + 2 tram | AB | 3 | 10 | {3: 7} |
| 2 | Mostowa | 1 road + 2 tram | A | 10 | 11 | {9: 3, 11: 6} |
| 3 | Mosty Uniwersyteckie | 5 road + 0 tram | A | 11 | 1 | {1: 4, 10: 5, 11: 4} |
| 4 | Stanisława Dubois | 4 road + 3 tram | AB | 11 | - | {11: 30} |
| 5 | Most Pomorski Północny | 3 road + 2 tram | A | 1 | 11 | {1: 10, 11: 7} |
| 6 | Kardynała Stefana Wyszyńskiego | 5 road + 2 tram | AB | 3 | 2 | {2: 14, 3: 20} |
| 7 | most Grunwaldzki | 3 road + 2 tram | ABC | 3 | 2 | {2: 4, 3: 7} |
| 8 | Most Romana Dmowskiego | 4 road + 2 tram | AB | 11 | 9 | {9: 7, 11: 14} |
| 9 | Wyspa Słodowa | 1 road + 0 tram | B | 3 | - | {3: 6} |
| 10 | Most Tumski | 1 road + 0 tram | B | 3 | 1 | {1: 3, 3: 3} |
| 11 | Most Młyński Północny | 2 road + 4 tram | AB | 3 | 1 | {1: 4, 3: 6} |
| 12 | - | 1 road + 0 tram | B | 3 | - | {3: 3} |
| 13 | - | 1 road + 0 tram | B | 10 | - | {10: 6} |
| 14 | - | 1 road + 0 tram | C | 10 | - | {10: 4} |
| 15 | Most Pomorski Południowy | 2 road + 6 tram | A | 10 | 11 | {10: 8, 11: 3} |

Dmowskiego bridge edges [411, 1061, 1064]: owner zone(s) [11].


## 9. Stability (S0-S4) and comparison with v0

Same method and seed; no face, island or bridge overrides; region groups and number of zones per region fixed to the S0 allocation. Labels matched to S0 by Hungarian assignment on S0 minutes. Shares are measured on faces.

| scenario | balance (own weights) | balance (S0 weights) | zones per region | S0 minutes keeping zone | units keeping zone |
|---|---|---|---|---|---|
| S0 | 1.094 | 1.094 | 8/3 | 100.0% | 100.0% |
| S1 | 1.088 | 1.167 | 8/3 | 75.9% | 75.8% |
| S2 | 1.090 | 1.144 | 8/3 | 77.2% | 77.4% |
| S3 | 1.083 | 1.101 | 8/3 | 92.4% | 92.4% |
| S4 | 1.096 | 1.105 | 8/3 | 71.8% | 72.4% |

v0.2 S0 against v0 S0 (labels matched, measured on units: edges, tram ways, sites): **61.4%** of S0 minutes and **62.2%** of units keep the zone.


## 10. Places to review by hand

### Merged islands

| island (region id) | area m2 | S0 minutes | units | merged into region | bridge edge (tier) | zone joined | zones touched |
|---|---|---|---|---|---|---|---|
| 3 | 43381 | 90.2 | 28.7 | 1 | -284 (A) | 3 | 1 |
| 4 | 26912 | 22.5 | 7.2 | 6 -> 1 | 5705 (B) | 3 | 1 |
| 5 | 14171 | 1.0 | 0.3 | 4 -> 1 | 11715 (B) | 3 | 1 |
| 6 | 6123 | 26.0 | 8.3 | 3 -> 1 | -282 (A) | 3 | 1 |
| 7 | 6118 | 15.5 | 7.5 | 1 | 12418 (B) | 10 | 1 |
| 8 | 4935 | 1.0 | 0.5 | 1 | 13498 (C) | 10 | 1 |
| 9 | 4898 | 35.8 | 10.0 | 1 | 13865 (A) | 10 | 1 |
| 10 | 2734 | 0.0 | 0.0 | 1 | none: nearest region | 0 | 1 |
| 11 | 1554 | 4.0 | 1.0 | 1 | 405 (A) | 10 | 1 |
| 12 | 413 | 0.0 | 0.0 | 1 | none: nearest region | 0 | 1 |
| 13 | 341 | 0.0 | 0.0 | 1 | none: nearest region | 0 | 1 |
| 14 | 224 | 7.1 | 1.8 | 2 | 39612 (A) | 1 | 1 |
| 15 | 205 | 0.0 | 0.0 | 1 | none: nearest region | 0 | 1 |

Set `config/overrides/island_zone.csv` (`region_id,zone`) to change the zone of an island.


### Bridge-owner variants (R3 cleanup)

Each variant is applied on top of the current `bridge_owner.csv` (groups identified by name, the override applies to the whole group) and evaluated with the same rules. Detached = pieces of zone polygons that are not connected to the main piece of their zone.

| variant | overrides | R3 detached | R1 zones in both banks | R2 seam edges in hulls / borders in hulls | balance faces | balance after ownership | refused |
|---|---|---|---|---|---|---|---|
| current override files | - | 0 pieces in 0 zones | 0 | 0 / 0 | 1.094 | 1.116 | 0 |
| A_uniwersyteckie_11 | Mosty Uniwersyteckie -> 11 | 0 pieces in 0 zones | 0 | 0 / 0 | 1.094 | 1.116 | 0 |
| B_mostowa_10 | Mostowa -> 10 | 0 pieces in 0 zones | 0 | 0 / 0 | 1.094 | 1.116 | 0 |
| AB_both | Mosty Uniwersyteckie -> 11; Mostowa -> 10 | 0 pieces in 0 zones | 0 | 0 / 0 | 1.094 | 1.116 | 0 |

Owner of every bridge group per variant:

| group | name | current override files | A_uniwersyteckie_11 | B_mostowa_10 | AB_both |
|---|---|---|---|---|---|
| 1 | Most Piaskowy | 3 | 3 | 3 | 3 |
| 2 | Mostowa | 10 | 10 | 10 | 10 |
| 3 | Mosty Uniwersyteckie | 11 | 11 | 11 | 11 |
| 4 | Stanisława Dubois | 11 | 11 | 11 | 11 |
| 5 | Most Pomorski Północny | 1 | 1 | 1 | 1 |
| 6 | Kardynała Stefana Wyszyńskiego | 3 | 3 | 3 | 3 |
| 7 | most Grunwaldzki | 3 | 3 | 3 | 3 |
| 8 | Most Romana Dmowskiego | 11 | 11 | 11 | 11 |
| 9 | Wyspa Słodowa | 3 | 3 | 3 | 3 |
| 10 | Most Tumski | 3 | 3 | 3 | 3 |
| 11 | Most Młyński Północny | 3 | 3 | 3 | 3 |
| 12 | - | 3 | 3 | 3 | 3 |
| 13 | - | 10 | 10 | 10 | 10 |
| 14 | - | 10 | 10 | 10 | 10 |
| 15 | Most Pomorski Południowy | 10 | 10 | 10 | 10 |

### Zone polygons

Slivers < 200 m2 merged into the neighbour with the longest shared border: 0 (total 0 m2); dropped: 0. Lobes of ordinary land cut off by the hull of another zone's site and merged into the neighbour with the longest border: 1; 3647 m2 from zone 3 to zone 4. Detached pieces left (island land or bridge strip whose owner has no land next to it): 0.

Zone borders entering a site hull shrunk by 3 m (the check asks for hull buffered by 3 m; a border running along the hull outline necessarily lies in the buffered hull, so the inner tolerance is used): 0.

Sites whose hull overlaps faces of more than one zone (whole site goes to the zone with most hull area, hull added to that zone's polygon): 84 of 341. Edges placed by the hull rule: 1041. Seam edges inside a hull: 0.

Zones with compactness worse than v0: [1, 3, 9, 10, 11] (flag column in section 6).


Robust cores are not computed in this task.

