# Task 03a: provisional partition of RING 1 into 11 zones (v0)

Analysis only. All numbers in `config/16_partition.yaml` are `[PROPOSED]`; the work weights are unmeasured guesses (timing pilot not evaluated). Nothing here changes `scope.yaml`, the polygon, D2-D4 or `tiers.yaml`. Outputs: `data/interim/ring1_zones_v0.gpkg`, `data/interim/ring1_zones_v0_scenarios.csv`.

## Checks

| Check | Expected | Actual | Result |
|---|---|---|---|
| segment units found for all RING 1 edges + tram ways | 6255 | 6255 | PASS |
| tier_tag in units == tier_tag in ownership layer (edges) | 0 | 0 | PASS |
| vertices (junction clusters, centroid_in) | 2039 | 2039 | PASS |
| sites | 341 | 341 | PASS |
| units in sites | 763 | 763 | PASS |
| road edges in RING 1 | 5804 | 5804 | PASS |
| tram-only ways in RING 1 | 451 | 451 | PASS |
| units = site units + edges + tram ways | 7018 | 7018 | PASS |
| work-unit table rows | 7018 | 7018 | PASS |
| KBR R1 counters | 23 | 23 | PASS |
| inside_through edges have both end clusters among the vertices | 0 | 0 | PASS |
| units attached to vertices | 7018 | 7018.0 | PASS |
| S0: every zone connected | 0 | 0 | PASS |
| S0: all 11 zones non-empty | 11 | 11 | PASS |
| S0: sites split between zones | 0 | 0 | PASS |
| S1: every zone connected | 0 | 0 | PASS |
| S1: all 11 zones non-empty | 11 | 11 | PASS |
| S1: sites split between zones | 0 | 0 | PASS |
| S2: every zone connected | 0 | 0 | PASS |
| S2: all 11 zones non-empty | 11 | 11 | PASS |
| S2: sites split between zones | 0 | 0 | PASS |
| S3: every zone connected | 0 | 0 | PASS |
| S3: all 11 zones non-empty | 11 | 11 | PASS |
| S3: sites split between zones | 0 | 0 | PASS |
| S4: every zone connected | 0 | 0 | PASS |
| S4: all 11 zones non-empty | 11 | 11 | PASS |
| S4: sites split between zones | 0 | 0 | PASS |
| zone units sum to total | 7018 | 7018 | PASS |
| seam edges == road edges cut by the partition (S0) | 101 | 101 | PASS |
| R1 counters assigned to zones | 23 | 23 | PASS |
| S1: balance (own weights) <= 1.05 | <= 1.05 | 1.047 | PASS |
| S2: balance (own weights) <= 1.05 | <= 1.05 | 1.045 | PASS |
| S3: balance (own weights) <= 1.05 | <= 1.05 | 1.034 | PASS |
| S4: balance (own weights) <= 1.05 | <= 1.05 | 1.050 | PASS |
| S0: balance <= 1.05 | <= 1.05 | 1.033 | PASS |

## 1. Graph

Vertices = 2039 junction clusters with `centroid_in`. Graph edges = `inside_through` road edges between two vertices, multi-edges merged (2756 vertex pairs from 3152 edges; 1253 intra-cluster loops dropped, 14.35 km; their minutes stay on the cluster). Boundary stubs, dead-end spurs, isolated roads and tram-only ways carry weight only.

Connected components: **7**; sizes [2028, 3, 3, 2, 1, 1, 1].

Every component other than the largest was attached (one synthetic graph edge, weight 1) to the geometrically nearest vertex of the largest one:

| component size (vertices) | distance to largest (m) |
|---|---|
| 3 | 51 |
| 3 | 36 |
| 2 | 31 |
| 1 | 53 |
| 1 | 24 |
| 1 | 17 |

The synthetic edges are not road edges; they are excluded from cut-edge counts and hop distances.


## 2. Atomic sites

341 sites; 1950 super-vertices after contraction (89 vertices merged). Site vertices = complex clusters of the site, junction clusters of its signal nodes on junctions, and tram-crossing nodes that are junction nodes (only those with `centroid_in`). Sites with no such vertex (tram-only / crossing-only): **66**, attached to the nearest vertex. Vertices claimed by more than one site (those sites then share one super-vertex): 0.


## 3. Proxy weights (S0)

site = min(45, 6 + 1.6 * n_units); edge A/B/C = {'A': 4, 'B': 3, 'C': 2}; tram segment = 4 min. Edge minutes split half and half between end vertices (all to the one vertex for spurs and stubs); isolated roads and tram-only ways go to the nearest vertex.

| attached by nearest vertex | n | > 100 m from the segment | max distance (m) |
|---|---|---|---|
| sites (no own vertex -> nearest) | 66 | 0 | 55 |
| isolated road edges -> nearest | 20 | 0 | 45 |
| tram-only ways -> nearest | 451 | 0 | 81 |

Sites that own vertices: 275; the farthest of their vertices from the site point is 20 m (0 sites > 100 m). Tram-only ways that have an end junction cluster: 18 (still attached to the nearest vertex).

Total S0 minutes: 21883; per zone mean 1989.


## 4. Partition (S0)

Method: `pymetis.part_graph` on the contracted graph (vertex weight = S0 minutes x 10, edge weight = number of merged road edges), k = 11, seed 20261025, contiguity on, ncuts 10, niter 20; imbalance factors tried in order [50, 30, 20, 10, 5], first one with max/mean <= 1.05 kept. S0 used ufactor 50; zones repaired after METIS: 0 moves.


Zones are numbered 1-11 clockwise from north around the RING 1 centroid (S0 only; S1-S4 are matched to S0).


## 5. Stability scenarios

S0 proxy; S1 every unit 1; S2 length (edge = length_m, site = 100 + 20 n_units); S3 S0 with site minutes x 0.6; S4 x 1.6. Labels matched to S0 by Hungarian assignment on shared S0 weight.

| scenario | balance (own weights) | balance (S0 weights) | cut vertex pairs | cut road edges | ufactor | repair moves | S0 minutes keeping zone | units keeping zone | super-vertices keeping zone |
|---|---|---|---|---|---|---|---|---|---|
| S0 | 1.033 | 1.033 | 88 | 101 | 50 | 0 | 100.0% | 100.0% | 1950/1950 |
| S1 | 1.047 | 1.055 | 87 | 101 | 50 | 0 | 70.0% | 69.5% | 1354/1950 |
| S2 | 1.045 | 1.073 | 92 | 99 | 50 | 0 | 60.7% | 61.4% | 1173/1950 |
| S3 | 1.034 | 1.046 | 88 | 99 | 50 | 0 | 83.4% | 83.6% | 1644/1950 |
| S4 | 1.050 | 1.064 | 93 | 100 | 50 | 0 | 83.5% | 83.3% | 1600/1950 |

Share of each S0 zone's minutes that stays in the zone, by scenario:

| zone | S1 | S2 | S3 | S4 |
|---|---|---|---|---|
| 1 | 66.5% | 39.6% | 95.1% | 96.5% |
| 2 | 86.2% | 77.1% | 83.9% | 73.3% |
| 3 | 67.5% | 44.1% | 80.5% | 68.5% |
| 4 | 63.7% | 65.3% | 76.4% | 64.1% |
| 5 | 30.1% | 54.3% | 48.1% | 59.8% |
| 6 | 57.6% | 71.9% | 48.1% | 94.0% |
| 7 | 82.1% | 71.0% | 97.1% | 88.4% |
| 8 | 81.9% | 65.3% | 97.8% | 81.7% |
| 9 | 67.3% | 76.0% | 95.3% | 95.3% |
| 10 | 98.9% | 56.8% | 98.9% | 100.0% |
| 11 | 69.4% | 45.8% | 98.1% | 97.8% |

## 6. Robust cores

Core = super-vertices in the same matched zone in S0-S4 and at least 2 junction hops (real graph edges, sites contracted) from any vertex of a different S0 zone. Stable in all five scenarios: 691 of 1950 super-vertices; core: 670. An element is in the core if its vertex is; a through edge needs both end vertices in the core; seam edges are never in the core. Minutes and units are counted after the seam rule (an edge's full minutes belong to its zone).

| zone | core vertices / vertices | core units | core S0 minutes | share of zone minutes | share of zone units |
|---|---|---|---|---|---|
| 1 | 11/224 | 37 | 108 | 5.6% | 5.5% |
| 2 | 83/163 | 272 | 870 | 44.4% | 45.0% |
| 3 | 9/168 | 40 | 116 | 5.7% | 6.3% |
| 4 | 121/246 | 312 | 894 | 43.8% | 44.6% |
| 5 | 0/152 | 0 | 0 | 0.0% | 0.0% |
| 6 | 12/160 | 39 | 105 | 5.2% | 6.0% |
| 7 | 71/176 | 202 | 643 | 32.8% | 32.5% |
| 8 | 90/149 | 361 | 1139 | 59.5% | 61.7% |
| 9 | 141/207 | 426 | 1257 | 61.7% | 62.9% |
| 10 | 102/164 | 290 | 862 | 42.7% | 46.2% |
| 11 | 30/141 | 92 | 281 | 14.5% | 15.8% |
| **all** | 670/1950 | 2071 | 6277 | 28.7% | 29.5% |

## 7. Seam rule

A road edge whose end clusters lie in different zones belongs to the zone of the end cluster with the larger `max_degree` (tie: lower cluster id); `seam = true`, the other zone is `read_buffer_zone`.

Seam edges: **101**, **9.44 km** (all tiers); by tier: A 57, B 37, C 7.


## 8. Composition of S0 zones (after the seam rule)

| zone | units | sites (small/medium/large) | sites with signal | sites with tram | km road A/B/C | tram km | edges A/B-core/B-service/C | tram ways | S0 minutes (seam rule) | S0 minutes (partition) | area km2 | R1 counters |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 669 | 20 (15/5/0) | 6 | 1 | 6.7/12.3/9.8 | 3.8 | 83/181/87/248 | 26 | 1926 | 1937 | 0.91 | 4 |
| 2 | 605 | 35 (27/7/1) | 10 | 11 | 7.2/7.3/6.3 | 4.2 | 167/102/49/154 | 45 | 1960 | 1962 | 0.63 | 0 |
| 3 | 638 | 40 (30/7/3) | 14 | 13 | 8.5/6.6/7.2 | 4.5 | 167/63/80/199 | 36 | 2028 | 2015 | 0.59 | 1 |
| 4 | 700 | 29 (27/2/0) | 6 | 2 | 5.1/8.9/12.2 | 3.1 | 123/123/96/308 | 9 | 2041 | 2055 | 0.76 | 2 |
| 5 | 659 | 32 (23/7/2) | 14 | 10 | 6.3/6.3/8.2 | 6.3 | 142/82/58/207 | 75 | 2046 | 2027 | 0.60 | 0 |
| 6 | 653 | 39 (35/2/2) | 8 | 8 | 5.5/8.2/8.0 | 2.6 | 120/91/116/225 | 28 | 2014 | 2015 | 0.58 | 3 |
| 7 | 621 | 30 (23/6/1) | 11 | 3 | 6.1/7.7/7.9 | 2.4 | 171/84/89/189 | 25 | 1962 | 1971 | 0.48 | 2 |
| 8 | 585 | 31 (24/6/1) | 15 | 7 | 8.7/5.0/8.2 | 5.2 | 170/69/53/160 | 62 | 1914 | 1918 | 0.55 | 3 |
| 9 | 677 | 30 (21/7/2) | 13 | 13 | 5.6/7.2/8.2 | 5.4 | 122/155/21/237 | 59 | 2039 | 2038 | 0.72 | 0 |
| 10 | 628 | 24 (19/4/1) | 8 | 1 | 7.9/9.0/6.2 | 3.4 | 172/117/89/154 | 44 | 2017 | 2012 | 0.74 | 3 |
| 11 | 583 | 31 (24/6/1) | 10 | 7 | 8.4/6.7/4.3 | 2.4 | 173/90/89/129 | 42 | 1937 | 1932 | 0.52 | 5 |
| **all** | 7018 | 341 (268/59/14) | 115 | 76 | 76.1/85.3/86.5 | 43.3 | 1610/1157/827/2210 | 451 | 21883 | 21883 | 7.11 | 23 |

Site size classes: small 1-2 units, medium 3-9, large >= 10. Tram ways are the tram-only ways (not counted in the A edges). 'S0 minutes (partition)' is the quantity METIS balanced (edge minutes split half/half); '(seam rule)' gives each edge entirely to its zone. R1 counters: contained in the zone polygon; 0 outside every polygon were assigned to the nearest zone. Polygons: Voronoi of 16941 points (edge samples every 20 m plus cluster centroids), dissolved and clipped to RING 1.


## 9. Adjacent zone pairs and coverage of the combined core

21 adjacent pairs (share at least one seam edge). Coverage score = min over strata of min(1, count / needed), needed = {'site_small': 6, 'site_medium': 6, 'site_large': 3, 'site_tram': 6, 'edge_A': 12, 'edge_B_core': 8, 'edge_B_service': 8, 'edge_C': 8, 'tram_segment': 8}. Counts are core elements of both zones combined. Ties broken by mean of the per-stratum ratios.

Top 10 pairs:

| pair | seam edges | score | limiting stratum | site_small | site_medium | site_large | site_tram | edge_A | edge_B_core | edge_B_service | edge_C | tram_segment |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 8-9 | 2 | 0.67 | site_large | 18 | 8 | 2 | 6 | 186 | 125 | 45 | 274 | 73 |
| 7-8 | 11 | 0.33 | site_large | 20 | 8 | 1 | 4 | 158 | 55 | 55 | 183 | 42 |
| 2-9 | 6 | 0.33 | site_large | 18 | 6 | 1 | 3 | 174 | 139 | 28 | 247 | 46 |
| 5-8 | 2 | 0.33 | site_large | 9 | 5 | 1 | 3 | 104 | 29 | 25 | 114 | 42 |
| 8-10 | 5 | 0.33 | site_large | 22 | 5 | 1 | 3 | 130 | 101 | 78 | 224 | 58 |
| 5-9 | 1 | 0.33 | site_large | 9 | 3 | 1 | 3 | 82 | 96 | 20 | 160 | 31 |
| 9-10 | 1 | 0.33 | site_large | 22 | 3 | 1 | 3 | 108 | 168 | 73 | 270 | 47 |
| 9-11 | 4 | 0.33 | site_large | 13 | 3 | 1 | 3 | 100 | 111 | 44 | 191 | 31 |
| 2-3 | 7 | 0.00 | site_large | 10 | 4 | 0 | 1 | 97 | 46 | 17 | 104 | 17 |
| 1-2 | 1 | 0.00 | site_large | 12 | 3 | 0 | 1 | 95 | 49 | 14 | 105 | 15 |

Score distribution over all pairs: 8-9: 0.67, 7-8: 0.33, 2-9: 0.33, 5-8: 0.33, 8-10: 0.33, 5-9: 0.33, 9-10: 0.33, 9-11: 0.33, 2-3: 0.00, 1-2: 0.00, 2-4: 0.00, 2-5: 0.00, 2-11: 0.00, 10-11: 0.00, 3-4: 0.00, 5-7: 0.00, 6-7: 0.00, 4-5: 0.00, 1-11: 0.00, 1-3: 0.00, 5-6: 0.00.


## 10. Per-zone core strata

| zone | site_small | site_medium | site_large | site_tram | edge_A | edge_B_core | edge_B_service | edge_C | tram_segment |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 3 | 0 | 0 | 1 | 3 | 6 | 6 | 18 | 0 |
| 2 | 9 | 3 | 0 | 0 | 92 | 43 | 8 | 87 | 15 |
| 3 | 1 | 1 | 0 | 1 | 5 | 3 | 9 | 17 | 2 |
| 4 | 10 | 0 | 0 | 0 | 44 | 65 | 55 | 135 | 3 |
| 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| 6 | 2 | 0 | 0 | 0 | 3 | 8 | 2 | 24 | 0 |
| 7 | 11 | 3 | 0 | 1 | 54 | 26 | 30 | 69 | 0 |
| 8 | 9 | 5 | 1 | 3 | 104 | 29 | 25 | 114 | 42 |
| 9 | 9 | 3 | 1 | 3 | 82 | 96 | 20 | 160 | 31 |
| 10 | 13 | 0 | 0 | 0 | 26 | 72 | 53 | 110 | 16 |
| 11 | 4 | 0 | 0 | 0 | 18 | 15 | 24 | 31 | 0 |
