# Task 01: OSM feature layers for RING 1-3

Input: `data/interim/wroclaw_r123.osm.pbf` (snapshot dolnoslaskie_2026-10-23). Output: `data/interim/features.gpkg` (EPSG:2177). Run time: **5.3 s**.

## Correctness checks

| Check | Expected | Actual | Result | Severity |
|---|---|---|---|---|
| signal_nodes junction_signal | == 1207 | 1207 | PASS | hard |
| signal_nodes crossing_signal | >= 2012 | 2044 | PASS | soft |
| signal_clusters (informational) | 1332 (netconvert join, not ground truth) | 900 | INFO | info |
| kbr_points R1 | == 23 | 23 | PASS | hard |
| kbr_points R2 | == 30 | 30 | PASS | hard |
| kbr_points R3 | == 22 | 22 | PASS | hard |
| invalid geometries (all layers) | 0 | 0 | PASS | hard |
| layers with CRS != EPSG:2177 | none | none | PASS | hard |
| ways in highway_exclude | 0 | 0 | PASS | hard |

## Objects per layer

| Layer | Objects |
|---|---|
| ways | 56485 |
| signal_nodes | 3251 |
| signal_clusters | 900 |
| junction_nodes | 38708 |
| junction_clusters | 28050 |
| tram_crossings | 754 |
| kbr_points | 164 |

## Road km by `highway` class

| highway | ways | km |
|---|---|---|
| service | 29447 | 1733.4 |
| track | 4631 | 795.5 |
| residential | 5093 | 644.9 |
| tertiary | 2955 | 272.7 |
| path | 3960 | 228.9 |
| living_street | 1644 | 165.2 |
| cycleway | 3441 | 150.7 |
| secondary | 1766 | 144.7 |
| unclassified | 767 | 85.4 |
| motorway | 212 | 79.3 |
| primary | 633 | 78.0 |
| motorway_link | 180 | 24.6 |
| primary_link | 103 | 7.0 |
| secondary_link | 88 | 4.9 |
| footway | 46 | 4.2 |
| tertiary_link | 90 | 3.0 |
| pedestrian | 2 | 0.3 |
| **total roads** | 55058 | 4422.8 |

Tram track (`is_tram`): 1427 ways, **223.5 km** (of which 0 ways are also in-scope roads and appear in both totals).

Railways outside the scope (`rail_in_scope: false`), km by `railway` value:

| railway | km |
|---|---|
| rail | 528.5 |
| disused | 112.7 |
| platform | 48.4 |
| abandoned | 28.3 |
| proposed | 22.4 |
| engine_shed | 1.9 |
| signal_box | 1.4 |
| razed | 1.2 |
| traverser | 1.0 |
| construction | 0.8 |
| track_ballast | 0.7 |
| loading_ramp | 0.6 |
| wash | 0.5 |
| platform_edge | 0.3 |
| water_tower | 0.1 |
| turntable | 0.1 |
| crossing_box | 0.1 |

## Signals

| kind | nodes |
|---|---|
| crossing_signal | 2044 |
| junction_signal | 1207 |

Signal clusters (eps 20 m): 900 (`812` junction, `88` crossing_only).

Distribution of cluster sizes (`n_nodes`):

| n_nodes | clusters |
|---|---|
| 1 | 194 |
| 2 | 218 |
| 3 | 186 |
| 4 | 73 |
| 5 | 67 |
| 6 | 39 |
| 7 | 22 |
| 8 | 28 |
| 9 | 22 |
| 10 | 16 |
| 11 | 8 |
| 12 | 10 |
| 13 | 5 |
| 14 | 2 |
| 15 | 3 |
| 16 | 3 |
| 17 | 2 |
| 19 | 2 |

## Junctions

Distribution of `degree` in `junction_nodes`:

| degree | nodes |
|---|---|
| 3 | 32358 |
| 4 | 6150 |
| 5 | 174 |
| 6 | 20 |
| 7 | 4 |
| 8 | 2 |

Junction clusters (eps 15 m): **28050** from 38708 junction nodes; with signal: 548, with roundabout: 205, with tram: 24.

## KBR points by `Kordon`

| Kordon | points |
|---|---|
| AOW | 8 |
| KOB | 22 |
| KW | 40 |
| PFO | 7 |
| PPR | 12 |
| R1 | 23 |
| R2 | 30 |
| R3 | 22 |

## Effect of `[TO BE CONFIRMED]` assumptions

| highway | ways | km | share of road km |
|---|---|---|---|
| road | 0 | 0.0 | 0.0% |
| service | 29447 | 1733.4 | 39.2% |
| track | 4631 | 795.5 | 18.0% |

- `service`, `road`, `track`: `junction_nodes` with degree >= 3 would be 9523 instead of 38708 if these three classes were excluded.
- `rail_in_scope: false`: rail km excluded are in the table above.
- `junction_cluster_eps_m: 15`: merges 38708 junction nodes into 28050 clusters (10658 fewer objects); no other value was tried.

## Signal clusters: diagnostics

`signal_clusters` is informational. The reference 1332 comes from `netconvert --junctions.join --tls.join`, a topological join, which is a different method than our distance-based single linkage. It is not a ground truth. Comparison with the netconvert traffic lights: `reports/01_netconvert_comparison.md` (`src/12_compare_netconvert.py`).

### Sensitivity to eps (everything else unchanged)

| eps [m] | signal_clusters |
|---|---|
| 10 | 1611 |
| 15 | 1236 |
| 20 | 900 |
| 30 | 487 |
| 40 | 387 |

### `mid_block` (no junction node with degree >= 3 within 25 m of any member signal node)

`mid_block`:

| kind | mid_block = false | mid_block = true |
|---|---|---|
| crossing_only | 83 | 5 |
| junction | 771 | 41 |

`mid_block_major`:

| kind | mid_block_major = false | mid_block_major = true |
|---|---|---|
| crossing_only | 64 | 24 |
| junction | 643 | 169 |

`mid_block_major` counts only junction nodes formed by ways of the classes motorway, motorway_link, trunk, trunk_link, primary, primary_link, secondary, secondary_link, tertiary, tertiary_link, unclassified, residential, living_street.

### Crossing signals: where they lie

2044 `crossing_signal` nodes vs 2012 turned into signals by `netconvert` (difference 32). Node membership in highway ways, and position relative to the cutting box [16.9002, 51.044, 17.1524, 51.1836]:

| status | inside box | outside box |
|---|---|---|
| no highway way | 2 | 0 |
| on in-scope way | 1972 | 1 |
| only out-of-scope way: construction/footway | 1 | 0 |
| only out-of-scope way: footway | 68 | 0 |
| **total** | 2043 | 1 |

## Notes

- 24 in-scope ways carry `area=yes` (kept as lines; the spec does not exclude them).
- `crossing_signal` nodes are counted over the whole extract, including nodes on ways outside the scope.
- `junction_nodes.has_signal` is true when the node itself is a signal node (junction or crossing kind).
