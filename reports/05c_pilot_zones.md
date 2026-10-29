# Task 02c': pilot sample inside the two frozen zones

Config: `config/26_pilot_zones.yaml`; script `src/26_pilot_zones.py`. Every number is `[PROPOSED]`. Reads the v2 packages, ownership tables and unit tables; changes none of them. Work areas, record columns and checklist names follow `docs/pilot/protocol.md` (version 2); the sample design follows the task text.

## Checks

| Check | Expected | Actual | Result |
|---|---|---|---|
| zone 3: package v2 sha256 equals the sidecar | 513d17da3fe612b492b0f380c4c8d9587723c2eeeaa98b787edfb96f81b14168 | 513d17da3fe612b492b0f380c4c8d9587723c2eeeaa98b787edfb96f81b14168 | PASS |
| zone 3: package_version | 2 | 2 | PASS |
| zone 4: package v2 sha256 equals the sidecar | ec2e03f55f0f1b9f670d8aa66910d34a195414b9047c4cc64768ed5d72ad2e1e | ec2e03f55f0f1b9f670d8aa66910d34a195414b9047c4cc64768ed5d72ad2e1e | PASS |
| zone 4: package_version | 2 | 2 | PASS |
| zone 3: rows of zone_3_units.csv | 671 | 671 | PASS |
| zone 3: all units have zone = 3 | 0 | 0 | PASS |
| zone 3: sites with member nodes and coordinates, consistent with ring1_sites.gpkg | 0 | 0 | PASS |
| zone 3: sites whose member nodes do not carry the site's site_id in ownership_nodes.csv (nodes taken from cluster_id) | 0 | 0 | PASS |
| zone 3: edge units with a geometry | 589 | 589 | PASS |
| zone 3: bridge groups owned by the zone, all edges are units of the zone | 0 | 0 | PASS |
| zone 3: site constraints (>= 2 signal, >= 2 tram crossing, >= 1 small signal site; warm-up sites fillable); redraws used | <= 200 | 5 | PASS |
| zone 3: B-service composition and warm-up units clear of the forbidden node(s) (release level: edge: B-core + tram segment; B-service redraw attempt 7; warm-ups redrawn ['edge: B-core', 'tram segment']) | True | True | PASS |
| zone 3: warm-up stratum ['site: medium'] contains a forbidden node and cannot be redrawn without moving sample units | redrawable | no candidate (kept, accepted) | INFO |
| zone 4: rows of zone_4_units.csv | 705 | 705 | PASS |
| zone 4: all units have zone = 4 | 0 | 0 | PASS |
| zone 4: sites with member nodes and coordinates, consistent with ring1_sites.gpkg | 0 | 0 | PASS |
| zone 4: sites whose member nodes do not carry the site's site_id in ownership_nodes.csv (nodes taken from cluster_id) | 0 | 1 | NOTE |
| zone 4: edge units with a geometry | 642 | 642 | PASS |
| zone 4: bridge groups owned by the zone, all edges are units of the zone | 0 | 0 | PASS |
| zone 4: site constraints (>= 2 signal, >= 1 tram crossing, >= 1 small signal site; warm-up sites fillable); redraws used | <= 200 | 1 | PASS |
| zone 4: B-service composition and warm-up units clear of the forbidden node(s) (release level: none; B-service redraw attempt 12; warm-ups redrawn ['site: small']) | True | True | PASS |
| zone 3: site: large drawn | 2 | 2 | PASS |
| zone 3: site: small drawn | 4 | 4 | PASS |
| zone 3: site: medium drawn | 3 | 3 | PASS |
| zone 3: bridge group drawn | 1 | 1 | PASS |
| zone 3: tram segment drawn | 2 | 2 | PASS |
| zone 3: edge: A drawn | 5 | 5 | PASS |
| zone 3: edge: B-core drawn | 3 | 3 | PASS |
| zone 3: edge: B-service drawn | 3 | 3 | PASS |
| zone 3: edge: C drawn | 3 | 3 | PASS |
| zone 3: min distance between work areas of all 32 units (sample, warm-up, overlap) m | >= 20 | 21.1 | PASS |
| zone 3: warm-up units | 6 | 6 | PASS |
| zone 3: overlap edge length m | >= 20 | [36.3] | PASS |
| zone 3: overlap units | 3 | 3 | PASS |
| zone 3: pilot_ids unique | 32 | 32 | PASS |
| zone 3: edge units belong to zone_3_units.csv | 0 | 0 | PASS |
| zone 4: site: large drawn | 1 | 1 | PASS |
| zone 4: site: small drawn | 4 | 4 | PASS |
| zone 4: site: medium drawn | 3 | 3 | PASS |
| zone 4: bridge group drawn | 0 | 0 | PASS |
| zone 4: tram segment drawn | 2 | 2 | PASS |
| zone 4: edge: A drawn | 5 | 5 | PASS |
| zone 4: edge: B-core drawn | 3 | 3 | PASS |
| zone 4: edge: B-service drawn | 3 | 3 | PASS |
| zone 4: edge: C drawn | 3 | 3 | PASS |
| zone 4: min distance between work areas of all 30 units (sample, warm-up, overlap) m | >= 20 | 25.4 | PASS |
| zone 4: warm-up units | 6 | 6 | PASS |
| zone 4: overlap edge length m | >= 20 | [25.5] | PASS |
| zone 4: overlap units | 3 | 3 | PASS |
| zone 4: pilot_ids unique | 30 | 30 | PASS |
| zone 4: edge units belong to zone_4_units.csv | 0 | 0 | PASS |
| R1: redraws of the overlap / visitor keys | <= 200 | 2 | PASS |
| R1: list = warm-up + own sample + visitor units | 35 | 35 | PASS |
| R1: visitor units | 3 | 3 | PASS |
| R1: warm-up units first | True | True | PASS |
| R1: own `site: large` units before the projected cut (positions; cut 17) | all <= cut | [3, 15] | PASS |
| R1: first position of an overlap / visitor unit (key range from 0.2) | >= 5 | 11 | PASS |
| R1: overlap + visitor units within the first 70% of the measured list (max position fraction) | <= 0.7 | 0.655 | PASS |
| R2: redraws of the overlap / visitor keys | <= 200 | 0 | PASS |
| R2: list = warm-up + own sample + visitor units | 33 | 33 | PASS |
| R2: visitor units | 3 | 3 | PASS |
| R2: warm-up units first | True | True | PASS |
| R2: own `site: large` units before the projected cut (positions; cut 27) | all <= cut | [10] | PASS |
| R2: first position of an overlap / visitor unit (key range from 0.2) | >= 5 | 8 | PASS |
| R2: overlap + visitor units within the first 70% of the measured list (max position fraction) | <= 0.7 | 0.667 | PASS |
| whitelisted node 3438315710: sample and overlap units whose work area contains it | 0 | [] | PASS |
| INFO whitelisted node 3438315710: warm-up units whose work area contains it (accepted) | - | ['W36'] | INFO |
| R1/zone 3: areas .osm read back with pyosmium (ways written = read; closed, negative ids, tags) | 32 | 32 | PASS |
| R1/zone 3: areas .osm contains every pilot_id | 32 | 32 | PASS |
| R1/zone 4: areas .osm read back with pyosmium (ways written = read; closed, negative ids, tags) | 30 | 30 | PASS |
| R1/zone 4: areas .osm contains every pilot_id | 30 | 30 | PASS |
| R2/zone 3: areas .osm read back with pyosmium (ways written = read; closed, negative ids, tags) | 32 | 32 | PASS |
| R2/zone 3: areas .osm contains every pilot_id | 32 | 32 | PASS |
| R2/zone 4: areas .osm read back with pyosmium (ways written = read; closed, negative ids, tags) | 30 | 30 | PASS |
| R2/zone 4: areas .osm contains every pilot_id | 30 | 30 | PASS |

`NOTE` = a finding, not a failure:

- zone 4: site 221: 1 of 1 member nodes (3438315710) do not carry site_id 221 in ownership_nodes.csv (site_id found: 97). Its member nodes are taken from `cluster_id`. `ownership_nodes.csv` is not changed; see section 9.

## 1. Sample size by zone and stratum

| zone | stratum | requested | eligible | drawn | redraws | status |
|---|---|---|---|---|---|---|
| 3 | site: large | all | 2 | 2 | 0 | OK |
| 3 | site: small | 4 | 27 | 4 | 0 | OK |
| 3 | site: medium | 3 | 6 | 3 | 1 | OK |
| 3 | bridge group | 1 | 6 | 1 | 0 | OK |
| 3 | tram segment | 2 | 51 | 2 | 1 | OK |
| 3 | edge: A | 5 | 131 | 5 | 21 | OK |
| 3 | edge: B-core | 3 | 74 | 3 | 6 | OK |
| 3 | edge: B-service | 3 | 80 | 3 | 2 | OK |
| 3 | edge: C | 3 | 158 | 3 | 2 | OK |
| 4 | site: large | all | 1 | 1 | 0 | OK |
| 4 | site: small | 4 | 29 | 4 | 0 | OK |
| 4 | site: medium | 3 | 6 | 3 | 2 | OK |
| 4 | bridge group | 0 | 0 | 0 | 0 | OK |
| 4 | tram segment | 2 | 20 | 2 | 4 | OK |
| 4 | edge: A | 5 | 100 | 5 | 16 | OK |
| 4 | edge: B-core | 3 | 83 | 3 | 0 | OK |
| 4 | edge: B-service | 3 | 120 | 3 | 10 | OK |
| 4 | edge: C | 3 | 257 | 3 | 2 | OK |

Redraws = candidates rejected because their work area is closer than 20 m to an already accepted one. Eligible = units of the zone in the stratum; edge strata reuse the 02a filters (A: inside_through, length >= 20 m; B-core, B-service: inside_through; C: dead_end_spur, inside_through, isolated; tram segment: length >= 30 m). Large sites: all of them. Bridge edges are also ordinary edge units and stay eligible in the edge strata; the disjointness rule keeps them apart from a drawn bridge group.

- Zone 3: site redraws (whole site phase repeated until the constraints hold): 5 (limit 200).
- Zone 4: site redraws (whole site phase repeated until the constraints hold): 1 (limit 200).

  - zone 3 level `none`: B-service: no draw with the composition in 200 attempts
- Zone 3: B-service redraw attempt 7 (0 = first draw already satisfied the composition rule); release level `edge: B-core + tram segment`; warm-up strata redrawn: ['edge: B-core', 'tram segment'] (forced by the forbidden node: none; **cannot be redrawn, kept**: ['site: medium']); new warm-up units (stratum: edge or site id): {'edge: B-core': 18137, 'tram segment': -260}.
- Zone 4: B-service redraw attempt 12 (0 = first draw already satisfied the composition rule); release level `none`; warm-up strata redrawn: ['site: small'] (forced by the forbidden node: ['site: small']; **cannot be redrawn, kept**: none); new warm-up units (stratum: edge or site id): {'site: small': 176}.

### B-service composition

Eligible = B-service edges of the zone after the 02a filter (`inside_through`); sample = the 3 drawn units. Rule: at least one `service` and one `path` unit per zone when both types have at least 10 eligible units.

| zone | set | n | highway=service | highway=path | other |
|---|---|---|---|---|---|
| 3 | eligible | 80 | 19 | 61 | 0 |
| 3 | sample | 3 | 1 | 2 | 0 |
| 4 | eligible | 120 | 93 | 27 | 0 |
| 4 | sample | 3 | 2 | 1 | 0 |

By the `service` tag:

| zone | set | service tag (count) |
|---|---|---|
| 3 | eligible | (no service tag) 80 |
| 3 | sample | (no service tag) 3 |
| 4 | eligible | (no service tag) 120 |
| 4 | sample | (no service tag) 3 |

## 2. Bridge groups owned by the zones

Zone 3:

| group | name | edges | length m | eligible (<= 6 edges) | drawn |
|---|---|---|---|---|---|
| 1 | Most Piaskowy | 3 | 141 | yes |  |
| 6 | Kardynała Stefana Wyszyńskiego | 7 | 1458 | no |  |
| 7 | most Grunwaldzki | 5 | 792 | yes |  |
| 9 | Wyspa Słodowa | 1 | 32 | yes |  |
| 10 | Most Tumski | 1 | 68 | yes | yes |
| 11 | Most Młyński Północny | 6 | 238 | yes |  |
| 12 |  | 1 | 85 | yes |  |

Zone 4: no bridge groups.

## 3. Units

### Zone 3

| pilot_id | stratum | unit | flags | area m2 |
|---|---|---|---|---|
| P301 | site: large | site 23: signal+complex+tram, 11 unit(s), 19 nodes |  | 13049.0 |
| P302 | site: large | site 24: signal+complex+tram, 13 unit(s), 15 nodes |  | 15728.6 |
| P303 | site: small | site 41: signal+complex, 2 unit(s), 9 nodes | overlap | 7275.5 |
| P304 | site: small | site 42: complex, 1 unit(s), 1 nodes |  | 2809.3 |
| P305 | site: small | site 335: tram, 1 unit(s), 1 nodes |  | 2809.3 |
| P306 | site: small | site 339: tram, 1 unit(s), 1 nodes |  | 2809.3 |
| P307 | site: medium | site 44: signal+complex, 6 unit(s), 12 nodes | overlap | 10569.1 |
| P308 | site: medium | site 46: signal+complex, 6 unit(s), 15 nodes |  | 9129.6 |
| P309 | site: medium | site 185: complex+tram, 3 unit(s), 7 nodes |  | 6584.1 |
| P310 | bridge group | bridge group 10 'Most Tumski': 1 edge(s), 68 m |  | 2753.5 |
| P311 | tram segment | edge -275: tram, 192 m, kind isolated |  | 6464.7 |
| P312 | tram segment | edge -251: tram, 121 m, kind isolated |  | 4343.5 |
| P313 | edge: A | edge 462: tertiary, 21 m, kind inside_through |  | 1346.1 |
| P314 | edge: A | edge 13900: tertiary, 34 m, kind inside_through |  | 1710.9 |
| P315 | edge: A | edge 19482: tertiary, 108 m, kind inside_through |  | 3948.3 |
| P316 | edge: A | edge 28088: tertiary, 52 m, kind inside_through |  | 2255.5 |
| P317 | edge: A | edge 46318: cycleway, 40 m, kind inside_through |  | 1887.5 |
| P318 | edge: B-core | edge 965: living_street, 52 m, kind inside_through |  | 2262.3 |
| P319 | edge: B-core | edge 2963: unclassified, 91 m, kind inside_through |  | 3420.1 |
| P320 | edge: B-core | edge 29118: residential, 36 m, kind inside_through | overlap | 1792.1 |
| P321 | edge: B-service | edge 14165: path, 156 m, kind inside_through |  | 5356.0 |
| P322 | edge: B-service | edge 30806: path, 89 m, kind inside_through |  | 3368.8 |
| P323 | edge: B-service | edge 32956: service, 89 m, kind inside_through |  | 3365.0 |
| P324 | edge: C | edge 25200: service, 42 m, kind inside_through |  | 1955.7 |
| P325 | edge: C | edge 42918: service, 59 m, kind dead_end_spur |  | 2448.0 |
| P326 | edge: C | edge 60637: service, 13 m, kind inside_through |  | 1078.3 |
| W31 | edge: C | edge 24332: service, 16 m, kind inside_through | warmup | 1182.4 |
| W32 | edge: B-core | edge 18137: residential, 9 m, kind inside_through | warmup | 982.9 |
| W33 | tram segment | edge -260: tram, 76 m, kind isolated | warmup | 2993.5 |
| W34 | edge: A | edge 19112: secondary, 111 m, kind inside_through | warmup | 4021.9 |
| W35 | site: small | site 96: complex, 1 unit(s), 3 nodes | warmup | 4025.9 |
| W36 | site: medium | site 97: signal+complex+tram, 5 unit(s), 24 nodes | warmup | 11843.8 |

### Zone 4

| pilot_id | stratum | unit | flags | area m2 |
|---|---|---|---|---|
| P401 | site: large | site 8: signal+complex+tram, 11 unit(s), 17 nodes |  | 9419.1 |
| P402 | site: small | site 208: complex, 1 unit(s), 6 nodes |  | 4163.1 |
| P403 | site: small | site 213: complex, 1 unit(s), 2 nodes |  | 3160.8 |
| P404 | site: small | site 224: complex, 1 unit(s), 3 nodes |  | 3903.1 |
| P405 | site: small | site 280: signal, 1 unit(s), 12 nodes | overlap | 9720.1 |
| P406 | site: medium | site 22: signal+complex, 3 unit(s), 8 nodes |  | 6738.4 |
| P407 | site: medium | site 223: signal+complex+tram, 5 unit(s), 9 nodes | overlap | 4626.8 |
| P408 | site: medium | site 236: complex+tram, 3 unit(s), 5 nodes |  | 4032.4 |
| P409 | tram segment | edge -1299: tram, 160 m, kind isolated |  | 5516.5 |
| P410 | tram segment | edge -300: tram, 61 m, kind isolated |  | 2540.4 |
| P411 | edge: A | edge 11507: path, 46 m, kind inside_through |  | 2077.0 |
| P412 | edge: A | edge 15640: secondary, 24 m, kind inside_through |  | 1419.6 |
| P413 | edge: A | edge 16669: secondary, 66 m, kind inside_through |  | 2695.4 |
| P414 | edge: A | edge 21214: secondary, 87 m, kind inside_through |  | 3308.2 |
| P415 | edge: A | edge 41442: tertiary, 107 m, kind inside_through |  | 3918.3 |
| P416 | edge: B-core | edge 5282: residential, 15 m, kind inside_through |  | 1161.9 |
| P417 | edge: B-core | edge 49429: living_street, 25 m, kind inside_through | overlap | 1466.5 |
| P418 | edge: B-core | edge 64229: residential, 2 m, kind inside_through |  | 755.3 |
| P419 | edge: B-service | edge 25988: service, 40 m, kind inside_through |  | 1907.0 |
| P420 | edge: B-service | edge 36819: service, 26 m, kind inside_through |  | 1494.0 |
| P421 | edge: B-service | edge 38578: path, 124 m, kind inside_through |  | 4420.8 |
| P422 | edge: C | edge 50573: service, 36 m, kind dead_end_spur |  | 1790.6 |
| P423 | edge: C | edge 59236: service, 94 m, kind inside_through |  | 2479.1 |
| P424 | edge: C | edge 67238: service, 26 m, kind dead_end_spur |  | 1464.9 |
| W41 | edge: C | edge 48702: service, 75 m, kind dead_end_spur | warmup | 2905.5 |
| W42 | edge: B-core | edge 5228: residential, 80 m, kind inside_through | warmup | 3099.8 |
| W43 | tram segment | edge -1447: tram, 82 m, kind isolated | warmup | 3171.0 |
| W44 | edge: A | edge 51991: cycleway, 124 m, kind inside_through | warmup | 4407.1 |
| W45 | site: small | site 176: complex, 1 unit(s), 2 nodes | warmup | 3621.3 |
| W46 | site: medium | site 129: signal+complex, 3 unit(s), 8 nodes | warmup | 6432.3 |

Warm-up draws (right after the sample draw of the same stratum): zone 3 site: small: eligible 23, drawn 1, redraws 0; zone 3 site: medium: eligible 3, drawn 1, redraws 0; zone 3 tram segment: eligible 49, drawn 1, redraws 2; zone 3 edge: A: eligible 126, drawn 1, redraws 3; zone 3 edge: B-core: eligible 71, drawn 1, redraws 4; zone 3 edge: C: eligible 155, drawn 1, redraws 0; zone 4 site: small: eligible 25, drawn 1, redraws 0; zone 4 site: medium: eligible 3, drawn 1, redraws 0; zone 4 tram segment: eligible 18, drawn 1, redraws 3; zone 4 edge: A: eligible 95, drawn 1, redraws 1; zone 4 edge: B-core: eligible 80, drawn 1, redraws 0; zone 4 edge: C: eligible 254, drawn 1, redraws 4. Warm-up units are ordered by assumed minutes of the stratum, then size (easy to hard); they are real work but excluded from the analysis.

## 4. Overlap and visitor units

| pilot_id | zone (owner) | stratum | processed by (own) | visitor |
|---|---|---|---|---|
| P303 | 3 | site: small | R1 | R2 |
| P307 | 3 | site: medium | R1 | R2 |
| P320 | 3 | edge: B-core | R1 | R2 |
| P405 | 4 | site: small | R2 | R1 |
| P407 | 4 | site: medium | R2 | R1 |
| P417 | 4 | edge: B-core | R2 | R1 |

## 5. Prefix balance (count per stratum in the first 25/50/75% of the measured list)

Warm-up excluded; own overlap and visitor units are counted in their own stratum. Last column: max over strata of |count - proportional share of the full list|. Prefix length = round(fraction x list length). Columns: `s:` site, `e:` edge.

| rater | prefix | n | s:large | s:small | s:medium | bridge | tram | e:A | e:B-core | e:B-service | e:C | max dev |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R1 | 25% | 7 | 1 | 1 | 1 | 1 | 1 | 1 | 0 | 0 | 1 | 0.97 |
| R1 | 50% | 15 | 2 | 3 | 3 | 1 | 1 | 2 | 1 | 1 | 1 | 1.07 |
| R1 | 75% | 22 | 2 | 4 | 4 | 1 | 1 | 3 | 3 | 2 | 2 | 0.97 |
| R2 | 25% | 7 | 0 | 1 | 1 | 0 | 1 | 1 | 1 | 1 | 1 | 0.48 |
| R2 | 50% | 14 | 1 | 3 | 3 | 0 | 1 | 2 | 2 | 1 | 1 | 0.93 |
| R2 | 75% | 20 | 1 | 4 | 3 | 0 | 2 | 3 | 3 | 2 | 2 | 0.70 |

Largest deviation: 1.07 units.

## 6. Planning projection (a GUESS)

Assumed minutes per unit (**[PROPOSED] unmeasured planning guesses, to be replaced by the times measured in the pilot; nothing here is a result**): site: small 8, site: medium 20, site: large 40, edge: A 4, edge: B-core 3, edge: B-service 3, edge: C 2, tram segment 4, bridge group 45. Visitor units are assumed to cost the same as the owner's. Budget for measured units = 5 h - 1 h warm-up = 240 min. Cut = number of measured units whose cumulative expected minutes fit the budget (`order_index` of the last one = cut + number of warm-up units).

| rater | measured units | total expected min | cut (measured position) | cut (order_index) | share of list | warm-up expected min | first unit past the budget | overlap/visitor @ measured position | of which before the cut |
|---|---|---|---|---|---|---|---|---|---|
| R1 | 29 | 300 | 17 | 23 | 59% | 41 | P314 (edge: A) | P303@11, P307@13, P407@14, P405@16, P417@17, P320@19 | 5 |
| R2 | 27 | 215 | 27 | 33 | 100% | 41 | - | P405@8, P417@9, P407@11, P307@14, P303@16, P320@18 | 6 |

Cumulative expected minutes (every 5th position, the cut and the end):

| rater | position | unit | cum. min |  |
|---|---|---|---|---|
| R1 | 5 | P304 | 74 |  |
| R1 | 10 | P305 | 138 |  |
| R1 | 15 | P302 | 229 |  |
| R1 | 17 | P417 | 240 | <- cut |
| R1 | 20 | P309 | 267 |  |
| R1 | 25 | P318 | 283 |  |
| R1 | 29 | P316 | 300 |  |
| R2 | 5 | P411 | 21 |  |
| R2 | 10 | P401 | 95 |  |
| R2 | 15 | P419 | 150 |  |
| R2 | 20 | P409 | 171 |  |
| R2 | 25 | P424 | 191 |  |
| R2 | 27 | P413 | 215 | <- cut |

## 9. Sites whose member nodes do not carry the site's `site_id`

All 341 sites of `ring1_sites.gpkg`; 309 have member nodes that can be identified (nodes of their junction clusters via `cluster_id`, and their tram crossing nodes); the others consist of signal clusters only, whose ids are not node ids, and are not checkable. A node counts when `site_id` in `ownership_nodes.csv` is empty or names another site. Found: 1. No table is changed. List: `data/derived/pilot_site_id_gaps.csv`.

| site_id | zone | member nodes | nodes lacking | owner_basis of those nodes | site_id found on them | owner_zone of them | site_zone_conflict flag | units |
|---|---|---|---|---|---|---|---|---|
| 221 | 4 | 1 | 1 | cluster:1 | 97 | 4 | 3 | junction_cluster_complex:13901 |

## 10. Whitelisted nodes (`shared_editable_nodes.csv`) inside pilot work areas

Node(s) [3438315710] must not lie in any sample or overlap work area (checked). Warm-up units that contain a whitelisted node are reported only (W36 was accepted by decision); the pilot rule is the note below.

| node | zones allowed | reason | pilot units whose work area contains it |
|---|---|---|---|
| 173178354 | 3;10 | site 46 (zone 3) and junction cluster 371 (zone 10); owner 10 | P308 (sample) |
| 312606382 | 3;10 | site 27 (zone 3) and junction cluster 3121 (zone 10); owner 10 | none |
| 1297337833 | 8;10 | site 21 (zone 10) and junction cluster 6435 (zone 8); owner 8 | none |
| 1299373989 | 8;9 | site 51 (zone 8) and junction cluster 6436 (zone 9); owner 9 | none |
| 2428025531 | 3;10 | site 46 (zone 3) and junction cluster 371 (zone 10); owner 10 | P308 (sample) |
| 3438315710 | 3;4 | site 97 (zone 3) and junction cluster 13901 (zone 4); owner 4 | W36 (warm-up) |
| 5042243602 | 8;10 | site 291 (zone 10) and junction cluster 18346 (zone 8); owner 8 | none |

Notes written to the Units sheet (column `note`) and to the README of both kits:

| pilot_id | note |
|---|---|
| P308 | Whitelisted nodes 173178354 and 2428025531 (owner zone 10, not active in the pilot) may be edited when the checklist requires it; the ownership check will print a warning, which is expected; mention it in notes. |
| W36 | Whitelisted node 3438315710 lies in this work area. Its owner is zone 4: do not move, delete or retag it; write the needed change in foreign_defects and notes. |

## 7. Output hashes (sha256)

| file | sha256 | same as previous run |
|---|---|---|
| data/derived/pilot_zone_units.csv | 54fb04f214d33d5fc1949eabd3796a804e397826dbbbd8b59329f06d697ff06d | yes |
| data/derived/pilot_assignments.csv | 480c65844b7c34341aaffd6391f7d3ade048a09cea7b3edbdb4388f0f3b164d2 | yes |
| docs/pilot/record_sheet.csv | fd766321fa778b89d9c1dbcddfe451afee01a298349a091efd235caf86e03c07 | yes |
| data/derived/pilot_site_id_gaps.csv | b282dbb450da8bf5f236d9c49c50fc5bbf58ac1b7f5451f25d5dd6a3f216aea9 | yes |
| data/derived/pilot_kit/R1/pilot_areas_zone_3.osm | 21b71eec569b7bfde99ff04a6cb0aa60d7d0af11bd2af5596a9a93fdf70dad6b | yes |
| data/derived/pilot_kit/R1/pilot_areas_zone_4.osm | 4bf5c72ea5c257f50e0666be0fa6d90f8408e10e7e2cbe3013386bbbc520a128 | yes |
| data/derived/pilot_kit/R2/pilot_areas_zone_3.osm | 21b71eec569b7bfde99ff04a6cb0aa60d7d0af11bd2af5596a9a93fdf70dad6b | yes |
| data/derived/pilot_kit/R2/pilot_areas_zone_4.osm | 4bf5c72ea5c257f50e0666be0fa6d90f8408e10e7e2cbe3013386bbbc520a128 | yes |

| xlsx | file sha256 | same | cell-content sha256 | same |
|---|---|---|---|---|
| data/derived/pilot_kit/R1/units_R1.xlsx | cf01dcbc3ab9819fd984a3e1c862edb5779f55f94d5a2919b9913f79472c0462 | no | db42afcfd5e3a44134746aaea8c5e08dd79b0e6a0b44fc0adbf45bfd03820697 | yes |
| data/derived/pilot_kit/R2/units_R2.xlsx | 9aa73d0b53ca4aa04bbc982a7029ec59ec80416be82ae4838b68eae5457a633b | no | d4dc89864584026cf4e63e59cd1c6da6c82eada5e2579cdf8b3a1af6e52dcfb5 | yes |

Inputs (unchanged): `zone_3.osm` `513d17da3fe6`, `zone_4.osm` `ec2e03f55f0f`, `ownership_nodes.csv` `751af5fc263a`, `ownership_ways.csv` `4a27743850fd`.

## 8. Outputs

- `data/derived/pilot_zone_units.csv`, `data/derived/pilot_assignments.csv`, `data/derived/pilot_zones.gpkg` (layer `pilot_areas`, EPSG:2177)
- `data/derived/pilot_kit/R1`, `data/derived/pilot_kit/R2` (`units_<R>.xlsx`, `README.md`, `pilot_areas_zone_<N>.osm`), `data/derived/pilot_kit/<R>/pilot_areas_zone_<N>.osm`
- `docs/pilot/record_sheet.csv` (header only)
