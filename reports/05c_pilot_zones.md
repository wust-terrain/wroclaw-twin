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
| zone 3: sites whose member nodes lack site_id in ownership_nodes.csv (taken from cluster_id) | 0 | 0 | PASS |
| zone 3: edge units with a geometry | 589 | 589 | PASS |
| zone 3: bridge groups owned by the zone, all edges are units of the zone | 0 | 0 | PASS |
| zone 3: site constraints (>= 2 signal, >= 2 tram crossing, >= 1 small signal site; warm-up sites fillable); redraws used | <= 200 | 5 | PASS |
| zone 4: rows of zone_4_units.csv | 705 | 705 | PASS |
| zone 4: all units have zone = 4 | 0 | 0 | PASS |
| zone 4: sites with member nodes and coordinates, consistent with ring1_sites.gpkg | 0 | 0 | PASS |
| zone 4: sites whose member nodes lack site_id in ownership_nodes.csv (taken from cluster_id) | 0 | 1 | NOTE |
| zone 4: edge units with a geometry | 642 | 642 | PASS |
| zone 4: bridge groups owned by the zone, all edges are units of the zone | 0 | 0 | PASS |
| zone 4: site constraints (>= 2 signal, >= 1 tram crossing, >= 1 small signal site; warm-up sites fillable); redraws used | <= 200 | 1 | PASS |
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
| zone 4: overlap units | 3 | 3 | PASS |
| zone 4: pilot_ids unique | 30 | 30 | PASS |
| zone 4: edge units belong to zone_4_units.csv | 0 | 0 | PASS |
| R1: redraws of the overlap / visitor keys | <= 200 | 1 | PASS |
| R1: list = warm-up + own sample + visitor units | 35 | 35 | PASS |
| R1: visitor units | 3 | 3 | PASS |
| R1: warm-up units first | True | True | PASS |
| R1: overlap + visitor units within the first 70% of the measured list (max position fraction) | <= 0.7 | 0.69 | PASS |
| R2: redraws of the overlap / visitor keys | <= 200 | 0 | PASS |
| R2: list = warm-up + own sample + visitor units | 33 | 33 | PASS |
| R2: visitor units | 3 | 3 | PASS |
| R2: warm-up units first | True | True | PASS |
| R2: overlap + visitor units within the first 70% of the measured list (max position fraction) | <= 0.7 | 0.63 | PASS |
| R1/zone 3: areas .osm read back with pyosmium (ways written = read; closed, negative ids, tags) | 32 | 32 | PASS |
| R1/zone 3: areas .osm contains every pilot_id | 32 | 32 | PASS |
| R1/zone 4: areas .osm read back with pyosmium (ways written = read; closed, negative ids, tags) | 30 | 30 | PASS |
| R1/zone 4: areas .osm contains every pilot_id | 30 | 30 | PASS |
| R2/zone 3: areas .osm read back with pyosmium (ways written = read; closed, negative ids, tags) | 32 | 32 | PASS |
| R2/zone 3: areas .osm contains every pilot_id | 32 | 32 | PASS |
| R2/zone 4: areas .osm read back with pyosmium (ways written = read; closed, negative ids, tags) | 30 | 30 | PASS |
| R2/zone 4: areas .osm contains every pilot_id | 30 | 30 | PASS |

`NOTE` = a finding, not a failure:

- zone 4: site 221: 1 of 1 member nodes lack site_id in ownership_nodes.csv. The site is a single junction cluster; its nodes are taken from `cluster_id` (the other sites agree with `site_id` exactly). `ownership_nodes.csv` is not changed; the team should decide whether the missing `site_id` is a defect of the ownership table.

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
| 3 | edge: B-service | 3 | 80 | 3 | 28 | OK |
| 3 | edge: C | 3 | 158 | 3 | 2 | OK |
| 4 | site: large | all | 1 | 1 | 0 | OK |
| 4 | site: small | 4 | 29 | 4 | 0 | OK |
| 4 | site: medium | 3 | 6 | 3 | 2 | OK |
| 4 | bridge group | 0 | 0 | 0 | 0 | OK |
| 4 | tram segment | 2 | 20 | 2 | 4 | OK |
| 4 | edge: A | 5 | 100 | 5 | 16 | OK |
| 4 | edge: B-core | 3 | 83 | 3 | 0 | OK |
| 4 | edge: B-service | 3 | 120 | 3 | 3 | OK |
| 4 | edge: C | 3 | 257 | 3 | 2 | OK |

Redraws = candidates rejected because their work area is closer than 20 m to an already accepted one. Eligible = units of the zone in the stratum; edge strata reuse the 02a filters (A: inside_through, length >= 20 m; B-core, B-service: inside_through; C: dead_end_spur, inside_through, isolated; tram segment: length >= 30 m). Large sites: all of them. Bridge edges are also ordinary edge units and stay eligible in the edge strata; the disjointness rule keeps them apart from a drawn bridge group.

- Zone 3: site redraws (whole site phase repeated until the constraints hold): 5 (limit 200).
- Zone 4: site redraws (whole site phase repeated until the constraints hold): 1 (limit 200).

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
| P321 | edge: B-service | edge 23811: path, 7 m, kind inside_through |  | 914.1 |
| P322 | edge: B-service | edge 38946: path, 24 m, kind inside_through |  | 1431.7 |
| P323 | edge: B-service | edge 50903: path, 138 m, kind inside_through |  | 4824.5 |
| P324 | edge: C | edge 25200: service, 42 m, kind inside_through |  | 1955.7 |
| P325 | edge: C | edge 42918: service, 59 m, kind dead_end_spur |  | 2448.0 |
| P326 | edge: C | edge 60637: service, 13 m, kind inside_through |  | 1078.3 |
| W31 | edge: C | edge 24332: service, 16 m, kind inside_through | warmup | 1182.4 |
| W32 | edge: B-core | edge 5704: living_street, 31 m, kind inside_through | warmup | 1635.7 |
| W33 | tram segment | edge -270: tram, 67 m, kind isolated | warmup | 2719.7 |
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
| P417 | edge: B-core | edge 49429: living_street, 25 m, kind inside_through |  | 1466.5 |
| P418 | edge: B-core | edge 64229: residential, 2 m, kind inside_through | overlap | 755.3 |
| P419 | edge: B-service | edge 27952: service, 44 m, kind inside_through |  | 1962.4 |
| P420 | edge: B-service | edge 36819: service, 26 m, kind inside_through |  | 1494.0 |
| P421 | edge: B-service | edge 60761: service, 33 m, kind inside_through |  | 1684.9 |
| P422 | edge: C | edge 50573: service, 36 m, kind dead_end_spur |  | 1790.6 |
| P423 | edge: C | edge 59236: service, 94 m, kind inside_through |  | 2479.1 |
| P424 | edge: C | edge 67238: service, 26 m, kind dead_end_spur |  | 1464.9 |
| W41 | edge: C | edge 48702: service, 75 m, kind dead_end_spur | warmup | 2905.5 |
| W42 | edge: B-core | edge 5228: residential, 80 m, kind inside_through | warmup | 3099.8 |
| W43 | tram segment | edge -1447: tram, 82 m, kind isolated | warmup | 3171.0 |
| W44 | edge: A | edge 51991: cycleway, 124 m, kind inside_through | warmup | 4407.1 |
| W45 | site: small | site 221: complex, 1 unit(s), 1 nodes | warmup | 2809.3 |
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
| P418 | 4 | edge: B-core | R2 | R1 |

## 5. Prefix balance (count per stratum in the first 25/50/75% of the measured list)

Warm-up excluded; own overlap and visitor units are counted in their own stratum. Last column: max over strata of |count - proportional share of the full list|. Prefix length = round(fraction x list length). Columns: `s:` site, `e:` edge.

| rater | prefix | n | s:large | s:small | s:medium | bridge | tram | e:A | e:B-core | e:B-service | e:C | max dev |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R1 | 25% | 7 | 1 | 2 | 1 | 0 | 0 | 1 | 1 | 0 | 1 | 0.79 |
| R1 | 50% | 15 | 1 | 4 | 1 | 1 | 1 | 2 | 3 | 1 | 1 | 1.41 |
| R1 | 75% | 22 | 2 | 4 | 4 | 1 | 1 | 3 | 3 | 2 | 2 | 0.97 |
| R2 | 25% | 7 | 0 | 2 | 0 | 0 | 1 | 1 | 2 | 0 | 1 | 1.04 |
| R2 | 50% | 14 | 0 | 4 | 3 | 0 | 1 | 2 | 2 | 1 | 1 | 1.41 |
| R2 | 75% | 20 | 1 | 4 | 3 | 0 | 2 | 3 | 3 | 2 | 2 | 0.70 |

Largest deviation: 1.41 units.

## 6. Planning projection (a GUESS)

Assumed minutes per unit (**[PROPOSED] unmeasured planning guesses, to be replaced by the times measured in the pilot; nothing here is a result**): site: small 8, site: medium 20, site: large 40, edge: A 4, edge: B-core 3, edge: B-service 3, edge: C 2, tram segment 4, bridge group 45. Visitor units are assumed to cost the same as the owner's. Budget for measured units = 5 h - 1 h warm-up = 240 min. Cut = number of measured units whose cumulative expected minutes fit the budget (`order_index` of the last one = cut + number of warm-up units).

| rater | measured units | total expected min | cut (measured position) | cut (order_index) | share of list | warm-up expected min | first unit past the budget | overlap/visitor @ measured position | of which before the cut |
|---|---|---|---|---|---|---|---|---|---|
| R1 | 29 | 300 | 18 | 24 | 62% | 41 | P302 (site: large) | P405@1, P418@2, P303@12, P320@15, P407@16, P307@20 | 5 |
| R2 | 27 | 215 | 27 | 33 | 100% | 41 | - | P405@4, P418@7, P407@10, P307@13, P303@14, P320@17 | 6 |

Cumulative expected minutes (every 5th position, the cut and the end):

| rater | position | unit | cum. min |  |
|---|---|---|---|---|
| R1 | 5 | P317 | 57 |  |
| R1 | 10 | P322 | 137 |  |
| R1 | 15 | P320 | 163 |  |
| R1 | 18 | P309 | 207 | <- cut |
| R1 | 20 | P307 | 267 |  |
| R1 | 25 | P318 | 283 |  |
| R1 | 29 | P316 | 300 |  |
| R2 | 5 | P403 | 25 |  |
| R2 | 10 | P407 | 75 |  |
| R2 | 15 | P401 | 155 |  |
| R2 | 20 | P409 | 171 |  |
| R2 | 25 | P424 | 191 |  |
| R2 | 27 | P413 | 215 | <- cut |

## 7. Output hashes (sha256)

| file | sha256 | same as previous run |
|---|---|---|
| data/derived/pilot_zone_units.csv | cb956279abd682b98d02031055a55c6f55eb64c64a973b6723f336df288a93b4 | yes |
| data/derived/pilot_assignments.csv | b8d9675cf935c0c3420a45efd4bc4e9617e5b80f7b6926a64d0fa044a777fc6d | yes |
| docs/pilot/record_sheet.csv | fd766321fa778b89d9c1dbcddfe451afee01a298349a091efd235caf86e03c07 | yes |
| data/derived/pilot_kit/R1/pilot_areas_zone_3.osm | e64475caa4df45c8af4e2e66babbfb149445ac365d398f942d5e1c8d0b33149c | yes |
| data/derived/pilot_kit/R1/pilot_areas_zone_4.osm | 469deb01136d91b7a683d588023eed247f9328421cc21dd88a9cc75701b75812 | yes |
| data/derived/pilot_kit/R2/pilot_areas_zone_3.osm | e64475caa4df45c8af4e2e66babbfb149445ac365d398f942d5e1c8d0b33149c | yes |
| data/derived/pilot_kit/R2/pilot_areas_zone_4.osm | 469deb01136d91b7a683d588023eed247f9328421cc21dd88a9cc75701b75812 | yes |

| xlsx | file sha256 | same | cell-content sha256 | same |
|---|---|---|---|---|
| data/derived/pilot_kit/R1/units_R1.xlsx | 8be6ba2e2de8bcb67f9a71ea232746d3116daef489ccfe51ced82990be9b6861 | no | 678949e7bdf7b3baaf66a4a9e611bd91f282501a194a9972dcbc8d006420d724 | yes |
| data/derived/pilot_kit/R2/units_R2.xlsx | eb308410ff39df86ffc03126baaffbab38f4354984f6dd2ed0003fac1aff2e5f | no | 2a480072e81a247c4ef1ae1c11154522a1ab0f13ec402f799ddd601e2bdaf142 | yes |

Inputs (unchanged): `zone_3.osm` `513d17da3fe6`, `zone_4.osm` `ec2e03f55f0f`, `ownership_nodes.csv` `751af5fc263a`, `ownership_ways.csv` `4a27743850fd`.

## 8. Outputs

- `data/derived/pilot_zone_units.csv`, `data/derived/pilot_assignments.csv`, `data/derived/pilot_zones.gpkg` (layer `pilot_areas`, EPSG:2177)
- `data/derived/pilot_kit/R1`, `data/derived/pilot_kit/R2` (`units_<R>.xlsx`, `README.md`, `pilot_areas_zone_<N>.osm`), `data/derived/pilot_kit/<R>/pilot_areas_zone_<N>.osm`
- `docs/pilot/record_sheet.csv` (header only)
