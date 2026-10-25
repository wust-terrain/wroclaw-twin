# Task 01b: RING 1 membership and first workload numbers

Input: `data/interim/features.gpkg`, polygon `data/derived/ring_polygons.gpkg` (layer `ring1`). Rule under test: D3 (`centroid_in`). Output: `data/interim/ring1_membership.gpkg` (EPSG:2177). Read-only analysis: no parameters were tuned.

## Checks

| Check | Expected | Actual | Result |
|---|---|---|---|
| KBR R1 counters | 23 | 23 | PASS |
| counters inside polygon | 23 | 23 | PASS |
| counter clusters centroid_in | 23 | 23 | PASS |
| segment km == way km | 4646268.899 | 4646268.899 | PASS |
| junction nodes without a way vertex | 0 | 0 | PASS |
| junction nodes sharing coordinates | 0 | 0 | PASS |

## Polygon facts (recomputed)

| Fact | Value |
|---|---|
| area | 7.105 km2 |
| perimeter | 10.91 km |
| vertices (exterior) | 23 |
| holes | 0 |
| min counter distance to boundary | 56.2 m |

5 counters closest to the boundary:

| counter | to boundary [m] |
|---|---|
| r1_19 | 56.2 |
| r1_20 | 71.5 |
| r1_11 | 85.0 |
| r1_18 | 126.0 |
| r1_22 | 135.3 |

## Sensitivity of membership rule

| layer | clusters | centroid_in | any_in | all_in | flags disagree (any cluster) |
|---|---|---|---|---|---|
| junction_clusters | 28050 | 2039 | 2040 | 2037 | 3 (0.0%) |
| signal_clusters | 900 | 215 | 215 | 215 | 0 (0.0%) |

Segments (km) under the three rules (segment in iff at least one end cluster satisfies the flag):

| rule | segments | km |
|---|---|---|
| centroid_in (D3) | 7267 | 204.3 |
| any_in | 7275 | 204.8 |
| all_in | 7237 | 203.4 |

## Cluster diameter (max distance between member nodes)

| layer | p50 [m] | p90 [m] | p99 [m] | max [m] |
|---|---|---|---|---|
| junction_clusters | 0.0 | 12.5 | 30.8 | 167.8 |
| signal_clusters | 10.4 | 39.7 | 59.3 | 84.4 |

10 largest junction clusters by diameter:

| junction_cluster_id | lon | lat | n_nodes | diameter [m] | centroid_in |
|---|---|---|---|---|---|
| 11930 | 16.92906 | 51.15883 | 33 | 167.8 | False |
| 11932 | 16.93009 | 51.15995 | 32 | 115.4 | False |
| 761 | 17.04862 | 51.08348 | 21 | 102.1 | False |
| 23728 | 16.99596 | 51.17957 | 13 | 101.2 | False |
| 24577 | 16.99608 | 51.18002 | 11 | 94.3 | False |
| 23727 | 16.99781 | 51.17933 | 11 | 87.2 | False |
| 4501 | 17.06368 | 51.09032 | 8 | 87.0 | False |
| 1295 | 17.00499 | 51.13637 | 7 | 83.9 | False |
| 22457 | 16.99815 | 51.17989 | 16 | 83.9 | False |
| 3276 | 17.00708 | 51.05939 | 29 | 83.7 | False |

## Counter check (23 R1 counters)

| counter | nearest cluster | distance [m] | cluster nodes | centroid_in |
|---|---|---|---|---|
| r1_01 | 14747 | 32.4 | 2 | True |
| r1_02 | 11681 | 13.5 | 1 | True |
| r1_03 | 5447 | 29.6 | 2 | True |
| r1_04 | 6422 | 4.7 | 1 | True |
| r1_05 | 13699 | 12.7 | 1 | True |
| r1_06 | 3267 | 9.5 | 7 | True |
| r1_07 | 13993 | 8.0 | 2 | True |
| r1_08 | 13271 | 74.4 | 1 | True |
| r1_09 | 12471 | 7.6 | 2 | True |
| r1_10 | 17259 | 17.8 | 1 | True |
| r1_11 | 11025 | 37.9 | 2 | True |
| r1_12 | 3052 | 76.2 | 3 | True |
| r1_13 | 17689 | 75.1 | 1 | True |
| r1_14 | 256 | 31.1 | 2 | True |
| r1_15 | 17043 | 36.2 | 2 | True |
| r1_16 | 11501 | 46.1 | 1 | True |
| r1_17 | 12370 | 20.8 | 2 | True |
| r1_18 | 23991 | 51.3 | 1 | True |
| r1_19 | 12757 | 10.7 | 3 | True |
| r1_20 | 13981 | 39.8 | 1 | True |
| r1_21 | 12749 | 101.3 | 1 | True |
| r1_22 | 23713 | 38.7 | 3 | True |
| r1_23 | 9364 | 23.4 | 1 | True |

Max counter-to-cluster-node distance: 101.3 m. Distinct clusters: 23 of 23 counters.

## Clusters inside RING 1 (centroid_in)

Junction clusters: **2039** of 28050; signal clusters: **215** of 900.

Signal clusters by kind (x mid_block):

| kind | mid_block = false | mid_block = true | total |
|---|---|---|---|
| crossing_only | 17 | 0 | 17 |
| junction | 187 | 11 | 198 |
| **total** | 204 | 11 | 215 |

Junction clusters by `max_degree`:

| max_degree | clusters |
|---|---|
| 3 | 1587 |
| 4 | 395 |
| 5+ | 57 |

Junction clusters by attribute:

| attribute | true | false |
|---|---|---|
| has_signal | 110 | 1929 |
| has_roundabout | 5 | 2034 |
| has_tram | 16 | 2023 |

## Segments inside RING 1 (centroid_in)

Segments are ways split at junction nodes (degree >= 3): 90954 in total, 7267 in RING 1. Ends with no junction node (dead ends, isolated ways) have no cluster and never count as inside.

| highway | segments in | km in | of which stub km | km RING 1-3 total |
|---|---|---|---|---|
| service | 3202 | 83.74 | 52.23 | 1733.4 |
| residential | 866 | 28.60 | 9.76 | 644.9 |
| tertiary | 876 | 27.82 | 10.59 | 272.7 |
| secondary | 484 | 18.31 | 7.90 | 144.7 |
| path | 670 | 15.66 | 11.27 | 228.9 |
| living_street | 359 | 11.52 | 4.14 | 165.2 |
| cycleway | 566 | 11.30 | 6.98 | 150.7 |
| unclassified | 154 | 4.35 | 1.61 | 85.4 |
| secondary_link | 21 | 0.85 | 0.21 | 4.9 |
| tertiary_link | 39 | 0.72 | 0.10 | 3.0 |
| track | 4 | 0.32 | 0.25 | 795.5 |
| footway | 5 | 0.30 | 0.30 | 4.2 |
| pedestrian | 1 | 0.00 | 0.00 | 0.3 |
| **total roads** | 7247 | 203.50 | 105.33 | 4422.8 |

Road `service` and `track` are listed as their own rows above (both `[TO BE CONFIRMED]` classes).

**Boundary stubs** (exactly one end cluster inside):

| kind | segments | km |
|---|---|---|
| stub to a cluster outside | 78 | 6.51 |
| stub to a dead end (no cluster) | 4209 | 99.03 |
| all stubs | 4287 | 105.54 |

Segments with no end cluster at all: 10251 (712.8 km).

## Tram

| measure | value |
|---|---|
| tram segments by D3 rule | 20 (0.83 km) |
| tram segments with no end cluster | 1418 (214.2 km of 223.5 km total) |
| tram km inside polygon, geometric clip (all tram segments) | 47.84 km |
| tram_crossings inside polygon | 190 of 754 |
| ... of which node is a junction node with centroid_in cluster | 18 |

Tram-only ways carry no junction nodes (degree counts road ways only), so the segment rule cannot place them; the geometric clip is the usable tram figure. Ways that are both tram and in-scope road are counted in both the road and tram rows.
