# Task 02a: pilot sample and site diagnostics

Inputs: `data/interim/ring1_work_units.csv`, `data/interim/ring1_ownership.gpkg`, `config/tiers.yaml` via column `tier_tag`. Strata, sizes, seed and spacing are `[PROPOSED]` (`config/14_pilot_sample.yaml`). Analysis only.

## Checks

| Check | Expected | Actual | Result |
|---|---|---|---|
| sites | 341 | 341 | PASS |
| site member units | 763 | 763 | PASS |
| sampled units owned by RING 1 (in work-unit table) | 93 | 93 | PASS |
| info: sampled units with midpoint outside the polygon (all edges, owned via end cluster) | 0 | 4 | PASS |
| duplicate (unit_type, id) | 0 | 0 | PASS |
| min pairwise distance >= spacing (m) | >= 100 | 103.8 | PASS |
| overlap units | 8 | 8 | PASS |
| 02a columns of the first base_rows rows unchanged (sha256) | 06efa7d311d9e0a9888de91c3809022ecc8c6773f4c36307774209057cb494c0 | 06efa7d311d9e0a9888de91c3809022ecc8c6773f4c36307774209057cb494c0 | PASS |
| base rows / pilot_ids P001..P084 | 84 | 84 | PASS |
| large sites drawn | 5 | 3 | FAIL |
| warm-up units drawn | 6 | 6 | PASS |
| warm-up ids W01..W06 | ['W01', 'W02', 'W03', 'W04', 'W05', 'W06'] | ['W01', 'W02', 'W03', 'W04', 'W05', 'W06'] | PASS |
| pilot_edges layer rows | 60 | 60 | PASS |

## 1. Site diagnostics

Sites: 341 (member units 763). Units per site:

| n_units | sites |
|---|---|
| 1 | 246 |
| 2 | 22 |
| 3 | 18 |
| 4 | 11 |
| 5 | 13 |
| 6 | 8 |
| 7 | 5 |
| 8 | 3 |
| 9 | 1 |
| 10 | 1 |
| 11 | 5 |
| 13 | 2 |
| 14 | 1 |
| 15 | 2 |
| 17 | 1 |
| 20 | 1 |
| 22 | 1 |

Composition:

| composition | sites |
|---|---|
| complex | 177 |
| signal+complex | 56 |
| tram | 37 |
| signal | 32 |
| signal+complex+tram | 27 |
| complex+tram | 12 |

Site diameter (max distance between member unit centroids, m):

| set | p50 | p90 | p99 | max |
|---|---|---|---|---|
| all sites | 0.0 | 43.6 | 103.1 | 170.4 |
| sites with >1 unit (95) | 32.7 | 68.6 | 121.7 | 170.4 |

10 largest sites (by n_units, then diameter):

| site_id | lon | lat | n_units | composition | diameter_m |
|---|---|---|---|---|---|
| 53 | 17.030577 | 51.104242 | 22 | signal+complex+tram | 107.4 |
| 184 | 17.034642 | 51.110097 | 20 | complex+tram | 170.4 |
| 195 | 17.036027 | 51.113153 | 17 | complex+tram | 118.6 |
| 51 | 17.021252 | 51.107960 | 15 | signal+complex+tram | 101.2 |
| 86 | 17.032740 | 51.097712 | 15 | signal+complex+tram | 73.2 |
| 126 | 17.028141 | 51.117808 | 14 | signal+complex+tram | 58.3 |
| 24 | 17.047624 | 51.108091 | 13 | signal+complex+tram | 104.4 |
| 64 | 17.024509 | 51.116974 | 13 | signal+complex+tram | 58.8 |
| 8 | 17.047152 | 51.105795 | 11 | signal+complex+tram | 79.6 |
| 5 | 17.043295 | 51.098089 | 11 | signal+complex+tram | 69.6 |

Sites with diameter > 150 m: 1

| site_id | lon | lat | n_units | composition | diameter_m |
|---|---|---|---|---|---|
| 184 | 17.034642 | 51.110097 | 20 | complex+tram | 170.4 |

QGIS layers: `data/interim/ring1_sites.gpkg` (`sites`, `site_hulls`, EPSG:2177).

## 2. Pilot sample

Seed 20261025, spacing 100 m. CSV sha256 `d9904c2aa5941fda8a01a8ee20a35c09b3e09fd270ae77cd69dd0ef8980ebc05`.

| stratum | requested | eligible | drawn | status | redraws |
|---|---|---|---|---|---|
| site: complex | 6 | 177 | 6 | OK | 0 |
| site: signal+complex | 6 | 56 | 6 | OK | 0 |
| site: signal | 4 | 32 | 4 | OK | 0 |
| site: tram | 4 | 37 | 4 | OK | 0 |
| site: signal+complex+tram | 4 | 27 | 4 | OK | 2 |
| site: complex+tram | 4 | 12 | 4 | OK | 0 |
| edge: A | 15 | 976 | 15 | OK | 5 |
| edge: B-core | 10 | 1070 | 10 | OK | 5 |
| edge: B-service | 10 | 796 | 10 | OK | 8 |
| edge: C | 10 | 2264 | 10 | OK | 7 |
| edge: boundary_stub | 5 | 147 | 5 | OK | 1 |
| edge: tram | 6 | 365 | 6 | OK | 8 |
| site: large | 5 | 14 | 3 | SHORT | 11 |

Total drawn: 93 of 89 requested; redraws (rejected candidates: spacing or already used): 47.


Eligibility notes: edge strata A and B-core, B-service use kind `inside_through` only; C = `dead_end_spur` or tier C (not boundary_stub, not tram); boundary_stub is its own stratum. Candidate sets are not disjoint across sites vs edges (a unit appears once; spacing applies across all units).

Area cells (500 m grid): 32 covered by the sample; 40 cells contain at least one RING 1 work unit.

## Overlap set (all raters)

| pilot_id | unit_type | id | stratum | lon | lat |
|---|---|---|---|---|---|
| P006 | site | 269 | site: complex | 17.027235 | 51.098511 |
| P008 | site | 15 | site: signal+complex | 17.021445 | 51.111577 |
| P018 | site | 312 | site: tram | 17.027534 | 51.117742 |
| P024 | site | 183 | site: signal+complex+tram | 17.030070 | 51.102839 |
| P045 | segment | 5275 | edge: B-core | 17.054493 | 51.102836 |
| P064 | segment | 3596 | edge: C | 17.046900 | 51.110901 |
| P077 | segment | 47406 | edge: boundary_stub | 17.031524 | 51.095945 |
| P079 | segment | -1300 | edge: tram | 17.042560 | 51.095085 |

Task 02b extended this sample (stratum `site: large`, warm-up set, rater assignments): see `reports/05_pilot_assignments.md`.

## Outputs

- `data/derived/pilot_sample.csv`
- `data/derived/pilot_sample.gpkg` (`pilot`, `pilot_edges`)
- `docs/pilot/record_sheet.csv`
- `data/interim/ring1_sites.gpkg`
