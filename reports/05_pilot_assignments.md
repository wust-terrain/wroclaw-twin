# Task 02b: pilot extension, rater assignments and planning projection

Config: `config/14_pilot_sample.yaml`, `config/pilot_assignments.yaml`. Numbers marked `[PROPOSED]` are not agreed with the team. Analysis only; `scope.yaml`, polygon, D2-D4 and `tiers.yaml` untouched.

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
| assignment: max per-stratum difference between raters (non-overlap units) | <= 1 | 1 | PASS |
| assignment: max total difference between raters | <= 1 | 1 | PASS |
| assignment: every measured unit assigned | 87 | 87 | PASS |
| assignment: overlap units in every list | 8 | 8 | PASS |
| assignment: warm-up units first, same order for every rater | True | True | PASS |
| assignment: overlap units within the first 70% of every list (max position fraction) | <= 0.7 | 0.688 | PASS |

## Sample size by stratum (analysis sample)

| stratum | requested (02a) | drawn (02a) | drawn (02b) | eligible | redraws |
|---|---|---|---|---|---|
| site: complex | 6 | 6 | 6 | 177 | 0 |
| site: signal+complex | 6 | 6 | 6 | 56 | 0 |
| site: signal | 4 | 4 | 4 | 32 | 0 |
| site: tram | 4 | 4 | 4 | 37 | 0 |
| site: signal+complex+tram | 4 | 4 | 4 | 27 | 2 |
| site: complex+tram | 4 | 4 | 4 | 12 | 0 |
| edge: A | 15 | 15 | 15 | 976 | 5 |
| edge: B-core | 10 | 10 | 10 | 1070 | 5 |
| edge: B-service | 10 | 10 | 10 | 796 | 8 |
| edge: C | 10 | 10 | 10 | 2264 | 7 |
| edge: boundary_stub | 5 | 5 | 5 | 147 | 1 |
| edge: tram | 6 | 6 | 6 | 365 | 8 |
| site: large | 0 | 0 | 3 | 14 | 11 |

Total: 02a 84, 02b 87. `site: large` = sites with n_units >= 10, RNG stream seed + 1000; redraws = candidates rejected because already in the sample or closer than 100 m to an accepted unit. New ids continue after P084.

## Warm-up set (not part of the analysis sample)

RNG stream seed + 2000; units not in the sample and >= 100 m from every sample unit and from each other. Order: assumed minutes of the stratum, then size (n_units for sites, length for edges).

| pilot_id | stratum | unit | size | lon | lat |
|---|---|---|---|---|---|
| W01 | edge: C | segment:36367 | 33.38 m | 17.032856 | 51.119037 |
| W02 | edge: B-core | segment:29980 | 11.12 m | 17.035467 | 51.109110 |
| W03 | edge: tram | segment:-935 | 51.16 m | 17.046625 | 51.107910 |
| W04 | edge: A | segment:14069 | 228.1 m | 17.048482 | 51.109068 |
| W05 | site: complex | site:213 | 1 | 17.041999 | 51.103659 |
| W06 | site: signal+complex | site:45 | 2 | 17.039030 | 51.110724 |

Warm-up draws: site: complex eligible 177, redraws 0; site: signal+complex eligible 56, redraws 0; edge: A eligible 976, redraws 1; edge: B-core eligible 1070, redraws 0; edge: C eligible 2264, redraws 0; edge: tram eligible 365, redraws 0. Assumed warm-up time 35 min against 60 min allotted.

## Units per rater by stratum (2 raters, `n_raters` = 2)

| stratum | R1 non-overlap | R2 non-overlap | R1 total | R2 total |
|---|---|---|---|---|
| site: complex | 3 | 2 | 4 | 3 |
| site: signal+complex | 2 | 3 | 3 | 4 |
| site: signal | 2 | 2 | 2 | 2 |
| site: tram | 2 | 1 | 3 | 2 |
| site: signal+complex+tram | 1 | 2 | 2 | 3 |
| site: complex+tram | 2 | 2 | 2 | 2 |
| edge: A | 8 | 7 | 8 | 7 |
| edge: B-core | 4 | 5 | 5 | 6 |
| edge: B-service | 5 | 5 | 5 | 5 |
| edge: C | 5 | 4 | 6 | 5 |
| edge: boundary_stub | 2 | 2 | 3 | 3 |
| edge: tram | 2 | 3 | 3 | 4 |
| site: large | 2 | 1 | 2 | 1 |
| **all** | 40 | 39 | 48 | 47 |

Max per-stratum difference between raters (non-overlap units): 1. Round-robin pointer carries across strata. Positions below are positions in the measured list (warm-up excluded); `order_index` in the CSV counts the warm-up units too (measured position = order_index - 6).

## Overlap units and their positions

| pilot_id | stratum |
|---|---|
| P006 | site: complex |
| P008 | site: signal+complex |
| P018 | site: tram |
| P024 | site: signal+complex+tram |
| P045 | edge: B-core |
| P064 | edge: C |
| P077 | edge: boundary_stub |
| P079 | edge: tram |

| rater | overlap units @ measured position | before the projected cut | of |
|---|---|---|---|
| R1 | P018@3, P064@12, P079@13, P024@18, P008@19, P045@27, P077@28, P006@33 | 8 | 8 |
| R2 | P006@5, P018@11, P024@16, P077@19, P064@22, P045@27, P079@29, P008@32 | 8 | 8 |

## Prefix balance (count per stratum in the first 25/50/75% of the measured list)

Overlap units are counted in their own stratum. Last column: max over strata of |count - proportional share of the rater's full list|. Prefix length = round(fraction x list length). Columns: `s:` site stratum, `e:` edge stratum.

| rater | prefix | n | s:complex | s:signal+complex | s:signal | s:tram | s:signal+complex+tram | s:complex+tram | e:A | e:B-core | e:B-service | e:C | e:boundary_stub | e:tram | s:large | max dev |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R1 | 25% | 12 | 1 | 0 | 1 | 2 | 0 | 1 | 2 | 1 | 1 | 2 | 0 | 0 | 1 | 1.25 |
| R1 | 50% | 24 | 2 | 2 | 1 | 2 | 1 | 1 | 4 | 1 | 3 | 3 | 1 | 2 | 1 | 1.50 |
| R1 | 75% | 36 | 3 | 2 | 1 | 2 | 2 | 1 | 5 | 4 | 4 | 5 | 3 | 3 | 1 | 1.00 |
| R2 | 25% | 12 | 1 | 1 | 0 | 1 | 1 | 0 | 3 | 1 | 2 | 1 | 0 | 1 | 0 | 1.21 |
| R2 | 50% | 24 | 3 | 1 | 1 | 1 | 2 | 1 | 3 | 2 | 3 | 3 | 2 | 1 | 1 | 1.47 |
| R2 | 75% | 35 | 3 | 3 | 1 | 1 | 2 | 1 | 5 | 5 | 4 | 4 | 2 | 3 | 1 | 0.77 |

Largest deviation over all raters and prefixes: 1.50 units.

## Planning projection (a GUESS, to be replaced by measured times)

Uses `assumed_minutes` from `config/pilot_assignments.yaml`: site 11, site_large 40, A 4, B-core 3, B-service 3, C 2, boundary_stub 3, tram 4. **[PROPOSED] unmeasured planning guess; it must be replaced by the times measured in the pilot. Nothing here is a result.** Budget for measured units = 5 h - 1 h warm-up = 240 min. Cut position = number of units whose cumulative expected minutes fit in the budget.

| rater | measured units | total expected min | cut position | of list | s:complex | s:signal+complex | s:signal | s:tram | s:signal+complex+tram | s:complex+tram | e:A | e:B-core | e:B-service | e:C | e:boundary_stub | e:tram | s:large |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| R1 | 48 | 351 | 37 | 77% | 3 | 2 | 1 | 2 | 2 | 1 | 6 | 4 | 4 | 5 | 3 | 3 | 1 |
| R2 | 47 | 312 | 36 | 77% | 3 | 3 | 1 | 1 | 2 | 1 | 6 | 5 | 4 | 4 | 2 | 3 | 1 |

Cumulative expected minutes (every 10th position, the cut and the end):

| rater | position | cum. min |  |
|---|---|---|---|
| R1 | 10 | 107 |  |
| R1 | 20 | 155 |  |
| R1 | 30 | 203 |  |
| R1 | 37 | 240 | <- cut |
| R1 | 40 | 258 |  |
| R1 | 48 | 351 |  |
| R2 | 10 | 56 |  |
| R2 | 20 | 156 |  |
| R2 | 30 | 211 |  |
| R2 | 36 | 238 | <- cut |
| R2 | 40 | 257 |  |
| R2 | 47 | 312 |  |

## Output hashes (sha256)

| file | sha256 | same as previous run |
|---|---|---|
| data/derived/pilot_sample.csv | `d9904c2aa5941fda8a01a8ee20a35c09b3e09fd270ae77cd69dd0ef8980ebc05` | yes |
| data/derived/pilot_assignments.csv | `217ff575e57df5e5f4a66ec0f104c1ebe1b083f337eb8164b2696611cad148d7` | yes |

## Outputs

- `data/derived/pilot_sample.csv` (sample + warm-up rows, new columns)
- `data/derived/pilot_sample.gpkg`
- `data/derived/pilot_assignments.csv`
- `docs/pilot/record_sheet.csv` (header only)
