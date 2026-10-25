# Task 01c: RING 1 ownership layer and work-unit table

Input: `data/interim/features.gpkg`, `data/interim/ring1_membership.gpkg`, polygon `data/derived/ring_polygons.gpkg`. Rule: D3 (`centroid_in`) for segments with an end cluster, midpoint-in-polygon for segments without one. Read-only analysis; tiers are `[PROPOSED]` (`config/tiers.yaml`). Outputs: `data/interim/ring1_work_units.csv`, `data/interim/ring1_ownership.gpkg` (layers `edges`, `tram_segments`, `segments`).

## Checks

| Check | Expected | Actual | Result |
|---|---|---|---|
| junction_nodes (layer) | 38708 | 38708 | PASS |
| coordinates with degree >= 3 (recomputed) | 38708 | 38708 | PASS |
| junction nodes sharing coordinates | 38708 | 38708 | PASS |
| fragments = road + tram | 90954 | 90954 | PASS |
| deg-2 nodes with other than 2 fragment ends | 0 | 0 | PASS |
| merged chains that are not a single LineString | 0 | 0 | PASS |
| edge km == road fragment km | 4422772.979 | 4422772.979 | PASS |
| edges not classifiable | 0 | 0 | PASS |
| isolated edges with an end of degree > 2 | 0 | 0 | PASS |
| promoted edges that are not C-base | 0 | 0 | PASS |
| repro: edges | 69640 | 69640 | PASS |
| repro: inside_through inside RING 1 | 4405 | 4405 | PASS |
| repro: boundary_stub inside RING 1 | 147 | 147 | PASS |
| repro: dead_end_spur inside RING 1 | 1232 | 1232 | PASS |
| repro: isolated roads | 20 | 20 | PASS |
| repro: isolated tram-only | 451 | 451 | PASS |
| repro: promoted inside RING 1, all: edges | 1960 | 1960 | PASS |
| repro: promoted inside RING 1, all: km | 88.83 | 88.83 | PASS |
| repro: promoted inside RING 1, < 30 m: edges | 979 | 979 | PASS |
| repro: promoted inside RING 1, < 30 m: km | 15.6 | 15.6 | PASS |
| repro: promoted inside RING 1, > 100 m: edges | 200 | 200 | PASS |
| repro: promoted inside RING 1, > 100 m: km | 31.14 | 31.14 | PASS |
| RING 1 junction clusters | 2039 | 2039 | PASS |
| RING 1 signal clusters | 215 | 215 | PASS |
| RING 1 tram crossings | 190 | 190 | PASS |
| KBR R1 counters | 23 | 23 | PASS |
| work units: segments = RING 1 edges + tram fragments | 6255 | 6255 | PASS |
| units with duplicate (unit_type, id) | 0 | 0 | PASS |
| repro: work units | 7018 | 7018 | PASS |

## Segment definition: fragments vs edges

The 01b `segments_m` layer cuts ways only at junction nodes, but OSM ways are also split where tags change, so most fragment ends are *degree-2 continuation nodes*, not dead ends. To classify dead ends at all, road fragments were merged across degree-2 nodes (no junction cluster, degree exactly 2) into **edges**. All counts below are edges unless stated.

Road fragment ends (2 per fragment):

| end type | count |
|---|---|
| junction cluster (degree >= 3) | 122708 |
| degree 1 (true dead end) | 16568 |
| degree 2 (continuation to another way) | 39722 |
| **total** | 178998 |

Road fragments: 89499 -> edges: 69640 (1518 edges mix more than one `highway` value; the edge takes the class with most length). Tram-only ways are not merged (they have no junction nodes; 1455 ways, each a segment).


## 1-2. Segments in RING 1 by kind

`inside_through`: both end clusters inside. `boundary_stub`: through segment with exactly one end cluster inside. `dead_end_spur`: one end cluster (inside), other end degree 1. `isolated`: no end cluster, midpoint inside the polygon.

| kind | segments | km |
|---|---|---|
| inside_through | 4405 | 184.27 |
| boundary_stub | 147 | 16.20 |
| dead_end_spur | 1232 | 45.84 |
| isolated, roads | 20 | 1.57 |
| isolated, tram-only ways | 451 | 43.28 |
| **isolated, total** | 471 | 44.85 |
| **all segments in RING 1** | 6255 | 291.16 |

All edges in RING 1-3 for context (inside + outside):

| kind | segments | km |
|---|---|---|
| dead_end_spur | 16250 | 950.43 |
| isolated | 230 | 29.99 |
| through | 53160 | 3442.35 |
| isolated (tram-only ways) | 1455 | 223.50 |

## 3. Tram

| measure | value |
|---|---|
| tram segments (ways) in RING 1, midpoint rule | 451 of 1455 |
| tram track km in RING 1, midpoint rule | 43.28 km (of 223.50 km in RING 1-3) |
| tram_crossings in RING 1 (point in polygon) | 190 of 754 |
| ... also junction nodes with degree >= 3 | 18 |
| ... of those, in a junction cluster flagged complex | 14 |

## 4. Tiers

All `[PROPOSED]`:

| tier | highway classes |
|---|---|
| A | motorway, motorway_link, trunk, trunk_link, primary, primary_link, secondary, secondary_link, tertiary, tertiary_link, tram, cycleway |
| B | residential, living_street, unclassified |
| C | service, track, path, footway, pedestrian |

Override: a `through` edge of class service, path is promoted to tier B (24536 edges in RING 1-3, 1869 in RING 1).

Tier x kind in RING 1 (km; tram counted in tier A, `isolated`):

| tier | inside_through | boundary_stub | dead_end_spur | isolated | total |
|---|---|---|---|---|---|
| A | 68.57 | 6.04 | 1.49 | 43.28 | 119.39 |
| B | 115.62 | 10.02 | 1.94 | 0.00 | 127.58 |
| C | 0.07 | 0.14 | 42.41 | 1.57 | 44.19 |
| **total** | 184.27 | 16.20 | 45.84 | 44.85 | 291.16 |

Tier x kind in RING 1 (segments; tram counted in tier A, `isolated`):

| tier | inside_through | boundary_stub | dead_end_spur | isolated | total |
|---|---|---|---|---|---|
| A | 1527 | 49 | 34 | 451 | 2061 |
| B | 2877 | 97 | 52 | 0 | 3026 |
| C | 1 | 1 | 1146 | 20 | 1168 |
| **total** | 4405 | 147 | 1232 | 471 | 6255 |

## 5-6. Work units in RING 1

| unit_type | tier | units | km |
|---|---|---|---|
| signal_cluster | - | 215 | - |
| junction_cluster_complex | - | 358 | - |
| tram_crossing | - | 190 | - |
| segment | A | 2061 | 119.39 |
| segment | B | 3026 | 127.58 |
| segment | C | 1168 | 44.19 |
| **total units** |  | 7018 | 291.16 |

`counter_nearby` is filled for 2090 units (R1 counter within 150 m); 23 of 23 counters have at least one unit nearby.

Segment units by kind (rows of the CSV with `unit_type = segment`):

| kind | units | km |
|---|---|---|
| boundary_stub | 147 | 16.20 |
| dead_end_spur | 1232 | 45.84 |
| inside_through | 4405 | 184.27 |
| isolated | 471 | 44.85 |

### Junction clusters in RING 1

2039 junction clusters have `centroid_in`; **358** are complex. Degree is recomputed from through edges of tier A/B only (`max_degree_ab`).

| reason (any of deg>=4, roundabout, tram) | clusters |
|---|---|
| deg>=4 | 340 |
| tram | 9 |
| deg>=4+roundabout | 4 |
| deg>=4+tram | 4 |
| roundabout | 1 |

All RING 1 junction clusters by `max_degree_ab` (original `max_degree` in brackets for 4+):

| max_degree_ab | clusters |
|---|---|
| 0 | 1 |
| 1 | 168 |
| 2 | 455 |
| 3 | 1067 |
| 4 | 297 |
| 5+ | 51 |
| original max_degree >= 4 | 452 |

## Columns of `ring1_work_units.csv`

| column | definition |
|---|---|
| unit_type | `signal_cluster`, `junction_cluster_complex`, `tram_crossing` or `segment` |
| id | `cluster_id` (signal), `junction_cluster_id` (junction), OSM node id (tram crossing), `edge_id` of the `edges` layer (road segment) or negative index into `tram_segments` (tram); unique within `unit_type` |
| x, y | centroid in EPSG:2177 [m]; for segments the point at half the length |
| n_nodes | member nodes of the cluster (1 for a tram crossing); empty for segments |
| max_degree | junction: max over member nodes of the number of through edges of tier A/B ending there (`max_degree_ab`); tram crossing: OSM degree if it is a junction node; empty otherwise |
| length_m | segments only: edge length [m] |
| highway | segments only: `highway` of the longest fragment; `tram` for tram |
| tier | A/B/C/unmapped for segments (see tiers); `A` for tram crossings; empty for clusters |
| kind | signal: `junction` or `crossing_only`; junction: reason for complex (`deg>=4`, `roundabout`, `tram`); tram crossing: `junction_node` or `plain`; segment: `inside_through`, `boundary_stub`, `dead_end_spur`, `isolated` |
| mid_block_major | signal clusters only: no junction node of a major-class way within 25 m (`mid_block_major` from task 01 is present and used; plain `mid_block` is not exported) |
| counter_id | nearest R1 counter if closer than the threshold |
| counter_nearby | distance [m] from the unit geometry (point, or the whole segment line) to that counter, only if < 150 m; empty otherwise |
| tier_base, tier_tag, tier_topo | segments: tier variants (see the follow-up section); `tier` is the base tier with the service/path through override; tram is A in all |
| topo_through | segments: C-base edges only; their C-component has >= 2 attachment nodes |
| site_id | signal clusters, complex junction clusters and tram crossings closer than 30 m (`[PROPOSED]`) share an id; empty for segments |

Complex junction cluster: `max_degree_ab >= 4`, or a roundabout node, or a tram node, where the roundabout/tram flags count only on member nodes with `max_degree_ab >= 3` and the degree counts only `through` edges of tier A or B (after the service/path override).

Units overlap by design: a tram crossing may sit inside a signal or junction cluster, and segments are separate from nodes. Overlap is not removed here.

# Follow-up: tier variants for decision D4

Analysis only; `tier`, `tier_tag` and `tier_topo` are reported side by side and none is chosen. Counts are edges unless stated; 'inside' = RING 1 (D3 / midpoint rule as above).

**Edge definition.** An edge is a maximal chain of way fragments between junction nodes (degree >= 3) and dead ends (degree 1); fragments are merged across degree-2 nodes. `mixed_class` is `n_highways > 1` (no separate column).

Variants: `tier_base` = highest tier among an edge's fragments (A > B > C) from the class lists, no override. `tier` = `tier_base`, except `tier_promoted` edges (a `through` edge whose longest-fragment class is service/path and `tier_base` is C) become B. `tier_tag` = `tier`, but a promoted edge whose tagged fragments all have `service` in {parking_aisle, driveway, drive-through, emergency_access} is C. `tier_topo` = `tier_base`, but a promoted edge with `topo_through` is B (promoted edges without it stay C).

## Reproduction of run 1

All `repro:` rows of the Checks table pass (edges, segments by kind, work units, and the promoted-edge figures computed with the run-1 rule: longest-fragment class, service/path `through` -> B). The new `tier_base` rule can change which edges are promoted; the figures below use it.

Promoted inside RING 1: run-1 rule 1960 edges / 88.83 km; new `tier_promoted` 1869 edges / 79.56 km. Complex junction clusters (units are built on the run-1 tier): 358; under the new `tier`: 358.

## 2. Mixed-class edges

| scope | mixed edges | km | change base tier (longest -> highest) | km |
|---|---|---|---|---|
| RING 1-3 | 1518 | 225.01 | 620 | 94.96 |
| RING 1 | 199 | 17.48 | 100 | 10.02 |

Edges that change base tier, RING 1-3 (rows: longest-fragment tier, columns: highest tier):

| longest \ highest | A | B |
|---|---|---|
| B | 6 | 0 |
| C | 426 | 188 |

## 3. Service tag and `tier_tag`

| scope | measure | edges | km |
|---|---|---|---|
| RING 1-3 | promoted edges | 24536 | 1287.84 |
| RING 1-3 | moved B -> C by `tier_tag` | 8491 | 401.06 |
| RING 1-3 | service/path edges without `service` tag | 20454 | 1190.39 |
| RING 1-3 | ... of which promoted | 16030 | 885.29 |
| RING 1-3 | service/path edges, all | 38422 | 1957.53 |
| RING 1-3 | edges with `service_mixed` | 156 | 12.49 |
| RING 1 | promoted edges | 1869 | 79.56 |
| RING 1 | moved B -> C by `tier_tag` | 1042 | 42.31 |
| RING 1 | service/path edges without `service` tag | 1093 | 54.53 |
| RING 1 | ... of which promoted | 827 | 37.24 |
| RING 1 | service/path edges, all | 3125 | 132.17 |
| RING 1 | edges with `service_mixed` | 38 | 2.51 |

## 4. Topology of C-base edges

C-base edge: all fragments in the C-base list (service, track, path, footway, pedestrian); all other edges are A/B-base. Components connect C-base edges sharing an end junction node over the whole extract. An attachment node is a junction node where a C-base edge and an A/B-base edge both end (tram ways are separate segments and are not part of this graph). `topo_through` = component has >= 2 distinct attachment nodes.

C-base components in the extract:

| component class | components | edges | km | edges inside RING 1 | km inside RING 1 |
|---|---|---|---|---|---|
| 0 attachments | 241 | 388 | 45.43 | 23 | 1.71 |
| 1 attachment | 5523 | 11691 | 599.12 | 850 | 31.37 |
| >= 2 attachments | 2003 | 31676 | 2024.80 | 2164 | 90.67 |

Promoted edges inside RING 1 that stay in tier B under each variant, split by `topo_through` (length_m median / p90 in metres):

| variant | set | edges | km | median m | p90 m |
|---|---|---|---|---|---|
| tier | kept B, topo_through = true | 1614 | 70.61 | 28.9 | 97.9 |
| tier | kept B, topo_through = false | 255 | 8.95 | 29.8 | 64.2 |
| tier | **kept B, total** | 1869 | 79.56 | 29.2 | 92.2 |
| tier | moved to C | 0 | 0.00 | - | - |
| tier_tag | kept B, topo_through = true | 773 | 35.51 | 26.6 | 109.5 |
| tier_tag | kept B, topo_through = false | 54 | 1.74 | 28.3 | 67.8 |
| tier_tag | **kept B, total** | 827 | 37.24 | 26.7 | 105.7 |
| tier_tag | moved to C | 1042 | 42.31 | 29.9 | 84.7 |
| tier_topo | kept B, topo_through = true | 1614 | 70.61 | 28.9 | 97.9 |
| tier_topo | kept B, topo_through = false | 0 | 0.00 | - | - |
| tier_topo | **kept B, total** | 1614 | 70.61 | 28.9 | 97.9 |
| tier_topo | moved to C | 255 | 8.95 | 29.8 | 64.2 |

10 largest `topo_through` components touching RING 1 (by km inside RING 1; lon/lat = mean of the inside edges' midpoints):

| component | lon | lat | edges inside / total | km inside / total | attachments | promoted edges inside |
|---|---|---|---|---|---|---|
| 557 | 17.02925 | 51.09845 | 104 / 125 | 4.06 / 5.38 | 64 | 90 |
| 122 | 17.05074 | 51.11222 | 74 / 76 | 4.04 / 4.07 | 18 | 58 |
| 34 | 17.04588 | 51.10680 | 82 / 82 | 3.43 / 3.43 | 33 | 66 |
| 607 | 17.03923 | 51.09629 | 74 / 91 | 2.27 / 2.73 | 38 | 68 |
| 938 | 17.04414 | 51.09518 | 55 / 83 | 2.25 / 4.14 | 6 | 36 |
| 47 | 17.04037 | 51.09929 | 53 / 53 | 2.17 / 2.17 | 20 | 43 |
| 55 | 17.02058 | 51.11714 | 32 / 32 | 2.14 / 2.14 | 14 | 28 |
| 299 | 17.04373 | 51.10874 | 21 / 21 | 1.73 / 1.73 | 7 | 16 |
| 77 | 17.02472 | 51.10306 | 42 / 42 | 1.67 / 1.67 | 22 | 37 |
| 43 | 17.03788 | 51.10584 | 40 / 40 | 1.62 / 1.62 | 25 | 34 |

Every component > 1.0 km with >= 2 attachments that touches RING 1 (23 of 345 in the extract; a parking lot with two entrances counts as through):

| component | lon | lat | edges inside / total | km inside / total | attachments | promoted edges inside |
|---|---|---|---|---|---|---|
| 19 | 17.05401 | 51.10986 | 17 / 726 | 1.06 / 45.68 | 226 | 15 |
| 30 | 17.01682 | 51.10907 | 4 / 305 | 0.89 / 17.47 | 59 | 4 |
| 444 | 17.05601 | 51.10358 | 11 / 95 | 0.46 / 5.63 | 19 | 7 |
| 557 | 17.02925 | 51.09845 | 104 / 125 | 4.06 / 5.38 | 64 | 90 |
| 938 | 17.04414 | 51.09518 | 55 / 83 | 2.25 / 4.14 | 6 | 36 |
| 122 | 17.05074 | 51.11222 | 74 / 76 | 4.04 / 4.07 | 18 | 58 |
| 446 | 17.05042 | 51.09637 | 9 / 53 | 0.59 / 3.74 | 4 | 6 |
| 58 | 17.01737 | 51.10814 | 6 / 38 | 0.57 / 3.67 | 5 | 4 |
| 34 | 17.04588 | 51.10680 | 82 / 82 | 3.43 / 3.43 | 33 | 66 |
| 607 | 17.03923 | 51.09629 | 74 / 91 | 2.27 / 2.73 | 38 | 68 |
| 628 | 17.05104 | 51.11988 | 14 / 50 | 0.89 / 2.45 | 20 | 10 |
| 47 | 17.04037 | 51.09929 | 53 / 53 | 2.17 / 2.17 | 20 | 43 |
| 55 | 17.02058 | 51.11714 | 32 / 32 | 2.14 / 2.14 | 14 | 28 |
| 2434 | 17.05446 | 51.10515 | 14 / 41 | 0.35 / 1.84 | 5 | 9 |
| 76 | 17.02094 | 51.10359 | 8 / 48 | 0.53 / 1.74 | 24 | 6 |
| 299 | 17.04373 | 51.10874 | 21 / 21 | 1.73 / 1.73 | 7 | 16 |
| 174 | 17.02616 | 51.09736 | 9 / 18 | 0.44 / 1.69 | 4 | 6 |
| 77 | 17.02472 | 51.10306 | 42 / 42 | 1.67 / 1.67 | 22 | 37 |
| 43 | 17.03788 | 51.10584 | 40 / 40 | 1.62 / 1.62 | 25 | 34 |
| 1652 | 17.03280 | 51.10124 | 51 / 51 | 1.60 / 1.60 | 12 | 41 |
| 54 | 17.02897 | 51.11822 | 36 / 43 | 1.12 / 1.37 | 16 | 31 |
| 175 | 17.02462 | 51.09864 | 21 / 31 | 0.91 / 1.33 | 7 | 16 |
| 2689 | 17.02207 | 51.11584 | 22 / 22 | 1.10 / 1.10 | 4 | 20 |

## 5. Report tables (RING 1)

### (a) highway x kind: edges / km

| highway | inside_through | boundary_stub | dead_end_spur | isolated | total |
|---|---|---|---|---|---|
| service | 1506 / 60.08 | 54 / 5.20 | 1086 / 39.14 | 17 / 1.23 | 2663 / 105.66 |
| tram | 0 / 0.00 | 0 / 0.00 | 0 / 0.00 | 451 / 43.28 | 451 / 43.28 |
| tertiary | 688 / 28.73 | 19 / 1.71 | 0 / 0.00 | 0 / 0.00 | 707 / 30.44 |
| residential | 674 / 26.94 | 24 / 2.70 | 16 / 0.64 | 0 / 0.00 | 714 / 30.29 |
| path | 383 / 20.80 | 17 / 2.75 | 59 / 2.62 | 3 / 0.33 | 462 / 26.51 |
| secondary | 375 / 19.73 | 13 / 1.92 | 0 / 0.00 | 0 / 0.00 | 388 / 21.64 |
| living_street | 277 / 11.58 | 3 / 0.16 | 34 / 1.12 | 0 / 0.00 | 314 / 12.87 |
| cycleway | 328 / 10.74 | 9 / 1.00 | 28 / 1.03 | 0 / 0.00 | 365 / 12.77 |
| unclassified | 119 / 4.03 | 7 / 0.62 | 0 / 0.00 | 0 / 0.00 | 126 / 4.65 |
| footway | 0 / 0.00 | 0 / 0.00 | 5 / 0.97 | 0 / 0.00 | 5 / 0.97 |
| secondary_link | 18 / 0.85 | 0 / 0.00 | 0 / 0.00 | 0 / 0.00 | 18 / 0.85 |
| tertiary_link | 36 / 0.72 | 0 / 0.00 | 0 / 0.00 | 0 / 0.00 | 36 / 0.72 |
| track | 1 / 0.07 | 1 / 0.14 | 3 / 0.31 | 0 / 0.00 | 5 / 0.52 |
| pedestrian | 0 / 0.00 | 0 / 0.00 | 1 / 0.00 | 0 / 0.00 | 1 / 0.00 |
| **total** | 4405 / 184.27 | 147 / 16.20 | 1232 / 45.84 | 471 / 44.85 | 6255 / 291.16 |

### (b) km by tier variant x highway (service split by `service` value; top 8 by km)


`tier` (km):

| highway | A | B | C | total |
|---|---|---|---|---|
| service (all) | 0.15 | 65.30 | 40.20 | 105.66 |
| service / driveway | 0.00 | 32.67 | 29.16 | 61.83 |
| service / parking_aisle | 0.08 | 9.68 | 5.79 | 15.55 |
| service / alley | 0.00 | 0.00 | 0.14 | 0.14 |
| service / emergency_access | 0.00 | 0.10 | 0.01 | 0.12 |
| service / untagged | 0.07 | 22.85 | 5.10 | 28.02 |
| tram | 43.28 | 0.00 | 0.00 | 43.28 |
| tertiary | 30.44 | 0.00 | 0.00 | 30.44 |
| residential | 0.11 | 30.18 | 0.00 | 30.29 |
| path | 9.22 | 14.58 | 2.70 | 26.51 |
| secondary | 21.64 | 0.00 | 0.00 | 21.64 |
| living_street | 0.00 | 12.87 | 0.00 | 12.87 |
| cycleway | 12.77 | 0.00 | 0.00 | 12.77 |
| unclassified | 0.00 | 4.65 | 0.00 | 4.65 |
| footway | 0.21 | 0.00 | 0.76 | 0.97 |
| secondary_link | 0.85 | 0.00 | 0.00 | 0.85 |
| tertiary_link | 0.72 | 0.00 | 0.00 | 0.72 |
| track | 0.00 | 0.00 | 0.52 | 0.52 |
| pedestrian | 0.00 | 0.00 | 0.00 | 0.00 |
| **total** | 119.39 | 127.58 | 44.19 | 291.16 |

`tier_tag` (km):

| highway | A | B | C | total |
|---|---|---|---|---|
| service (all) | 0.15 | 22.99 | 82.52 | 105.66 |
| service / driveway | 0.00 | 0.14 | 61.69 | 61.83 |
| service / parking_aisle | 0.08 | 0.00 | 15.47 | 15.55 |
| service / alley | 0.00 | 0.00 | 0.14 | 0.14 |
| service / emergency_access | 0.00 | 0.00 | 0.12 | 0.12 |
| service / untagged | 0.07 | 22.85 | 5.10 | 28.02 |
| tram | 43.28 | 0.00 | 0.00 | 43.28 |
| tertiary | 30.44 | 0.00 | 0.00 | 30.44 |
| residential | 0.11 | 30.18 | 0.00 | 30.29 |
| path | 9.22 | 14.58 | 2.70 | 26.51 |
| secondary | 21.64 | 0.00 | 0.00 | 21.64 |
| living_street | 0.00 | 12.87 | 0.00 | 12.87 |
| cycleway | 12.77 | 0.00 | 0.00 | 12.77 |
| unclassified | 0.00 | 4.65 | 0.00 | 4.65 |
| footway | 0.21 | 0.00 | 0.76 | 0.97 |
| secondary_link | 0.85 | 0.00 | 0.00 | 0.85 |
| tertiary_link | 0.72 | 0.00 | 0.00 | 0.72 |
| track | 0.00 | 0.00 | 0.52 | 0.52 |
| pedestrian | 0.00 | 0.00 | 0.00 | 0.00 |
| **total** | 119.39 | 85.27 | 86.50 | 291.16 |

`tier_topo` (km):

| highway | A | B | C | total |
|---|---|---|---|---|
| service (all) | 0.15 | 56.35 | 49.15 | 105.66 |
| service / driveway | 0.00 | 27.04 | 34.80 | 61.83 |
| service / parking_aisle | 0.08 | 8.10 | 7.36 | 15.55 |
| service / alley | 0.00 | 0.00 | 0.14 | 0.14 |
| service / emergency_access | 0.00 | 0.10 | 0.01 | 0.12 |
| service / untagged | 0.07 | 21.11 | 6.84 | 28.02 |
| tram | 43.28 | 0.00 | 0.00 | 43.28 |
| tertiary | 30.44 | 0.00 | 0.00 | 30.44 |
| residential | 0.11 | 30.18 | 0.00 | 30.29 |
| path | 9.22 | 14.58 | 2.70 | 26.51 |
| secondary | 21.64 | 0.00 | 0.00 | 21.64 |
| living_street | 0.00 | 12.87 | 0.00 | 12.87 |
| cycleway | 12.77 | 0.00 | 0.00 | 12.77 |
| unclassified | 0.00 | 4.65 | 0.00 | 4.65 |
| footway | 0.21 | 0.00 | 0.76 | 0.97 |
| secondary_link | 0.85 | 0.00 | 0.00 | 0.85 |
| tertiary_link | 0.72 | 0.00 | 0.00 | 0.72 |
| track | 0.00 | 0.00 | 0.52 | 0.52 |
| pedestrian | 0.00 | 0.00 | 0.00 | 0.00 |
| **total** | 119.39 | 118.63 | 53.14 | 291.16 |

### (c) composition of tier B (share of tier-B km)

| variant | tier B km | residential | living_street | unclassified | service-through | path-through | other |
|---|---|---|---|---|---|---|---|
| tier | 127.58 | 23.7% | 10.1% | 3.6% | 50.9% | 11.4% | 0.3% |
| tier_tag | 85.27 | 35.4% | 15.1% | 5.5% | 26.6% | 17.1% | 0.4% |
| tier_topo | 118.63 | 25.4% | 10.8% | 3.9% | 47.2% | 12.3% | 0.3% |

### (d) promoted edges by length bucket (`tier_promoted`, RING 1)

| bucket | edges | km | median m | p90 m |
|---|---|---|---|---|
| < 30 m | 970 | 15.40 | 15.2 | 27.2 |
| 30-100 m | 733 | 39.01 | 48.6 | 82.3 |
| > 100 m | 166 | 25.16 | 134.7 | 219.4 |
| **all promoted** | 1869 | 79.56 | 29.2 | 92.2 |

## 6. Sites

`site_id` joins a signal cluster to a complex junction cluster if the signal centroid is within 30 m (`[PROPOSED]`) of the junction cluster centroid or of any of its member nodes, and a tram crossing to a complex junction cluster by the same distance rule; groups are merged transitively. Segments have no `site_id`.

| site composition | sites |
|---|---|
| complex | 177 |
| signal+complex | 56 |
| tram | 37 |
| signal | 32 |
| signal+complex+tram | 27 |
| complex+tram | 12 |
| **distinct sites** | 341 |

Sites with a tram crossing: 76. Node units: 763 -> 341 sites (422 units merged). Signal or tram units linked to more than one complex cluster: 147. Standalone tram crossings: 37 (16 of them within 30 m of a signal cluster, not merged because the rule joins tram crossings to junction clusters only).

## 7. Zone-size arithmetic (RING 1 / 11)

| measure | RING 1 | per zone (/11) |
|---|---|---|
| total work units | 7018 | 638.0 |
| distinct sites (node units merged) | 341 | 31.0 |
| segment units | 6255 | 568.6 |
| sites + segments | 6596 | 599.6 |

Segment km by tier variant (RING 1 incl. tram, which is tier A):

| variant | A km (per zone) | B km (per zone) | C km (per zone) | total km (per zone) |
|---|---|---|---|---|
| tier | 119.4 (10.9) | 127.6 (11.6) | 44.2 (4.0) | 291.2 (26.5) |
| tier_tag | 119.4 (10.9) | 85.3 (7.8) | 86.5 (7.9) | 291.2 (26.5) |
| tier_topo | 119.4 (10.9) | 118.6 (10.8) | 53.1 (4.8) | 291.2 (26.5) |

Run time: 14.4 s.
