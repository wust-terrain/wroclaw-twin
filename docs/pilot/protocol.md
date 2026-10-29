# Pilot protocol: time per work unit in the frozen zones 3 and 4

Status: PROPOSED (version 2). It defines how the two pilot raters clean their own zone in JOSM, what "full", "basic" and "scan" validation mean (decision D4), and how the time per work unit is measured. The pilot work is **kept**: the edits are real cleaning of the rater's zone. The result is a table of minutes per unit and stratum, used as work weights when the other nine zones are re-partitioned.

## 1. Design

- Two raters. R1 owns **zone 3**, R2 owns **zone 4** (zones of partition v0.2, frozen). Each rater works only in the package of their own zone (package version 2) and only on objects the zone owns.
- A stratified sample of units, drawn inside the rater's own zone, is processed first, in the order given in the kit. After the sample the rater continues with the rest of the zone.
- Six overlap units (three in each zone) are also processed by the other rater, on a private copy that is discarded. They separate the raters' speed from the difficulty of their zones.
- Budget: about 5 hours per rater: about 1 hour of warm-up (units are real work but excluded from the analysis) and about 4 hours of measured work.

Not measured: navigation between units, breaks, the SUMO network build, the quality of the final data.

## 2. Materials (per rater)

- Package of the zone: `data/derived/zones_v02/zone_<N>/zone_<N>.osm` with its sidecar `zone_<N>.json` (sha256 of the package and of the base). **Never edit or overwrite it.**
- Reference layer `zone_<N>_reference.osm` (zone polygon, 60 m read buffer, seam edges, `owned_outside_polygon` buffers) and `pilot_areas_zone_<N>.osm` (work area of every pilot unit, tagged with its `pilot_id`). Open them as extra layers. Never edit or save them.
- `zone_<N>_units.csv`, `zone_<N>_seams.csv`, `zone_<N>_bridges.csv`: your units, the seam edges with their owners, your bridge groups.
- Your kit `data/derived/pilot_kit/<rater>/units_<rater>.xlsx` (units in order with links, and a pre-filled record sheet).
- `scripts/josm_pilot.sh` (starts JOSM offline), `scripts/submit_edits.sh` (checks and submits your edits).
- A stopwatch that can be paused.

## 3. Session routine

1. Start JOSM only with `scripts/josm_pilot.sh`. It starts JOSM with `--offline=osm_api`, so nothing can be downloaded, updated or uploaded. Remote control must allow only "Change the viewport" and "Read protocol version".
2. First session: `cp zone_<N>.osm zone_<N>_edit.osm`. Later sessions: never copy again (it would overwrite your work); use `cp -n`.
3. Open `zone_<N>_edit.osm` as the data layer, and the reference layers. Work only in the data layer.
4. Save often with File > Save (it writes `zone_<N>_edit.osm`). At the end of the session also keep a dated copy `zone_<N>_edit_<date>.osm`.
5. At the end of the session run `scripts/submit_edits.sh` (section 10).
6. **Never** use File > Update data, Download data, Upload, or "Save As" over a package. An accidental Update data changes the file with server data and the submission refuses it; the work in that file must then be redone from a copy made before the update.

## 4. Ownership rules in practice

Every object has exactly one owner zone. You edit only what your zone owns.

- Ways: you own a way if your zone has the largest share of its length. A way that spans two zones is edited only by its owner; the other zone reports the needed change.
- Nodes: a node owned by another zone is read-only. Do not move, delete or retag it, also when it is the end node of a way you own (bridge ends on the other bank, seam nodes).
- Relations (turn restrictions): owned by the zone of the via member (without via, of the from way).
- Bridge groups: the owner edits all bridge ways of the group; end nodes owned by another zone stay read-only.
- Objects outside your zone polygon but inside `owned_outside_polygon` buffers are yours.
- Objects with no owner (outside RING 1) are read-only.
- Seven nodes of the whitelist `shared_editable_nodes.csv` may be edited by both zones; the check shows a warning.
- If you need a change on a foreign object, do not make it. Count it in `foreign_defects` and write its id and the change in `notes`.

`scripts/submit_edits.sh --dry-run` runs the ownership check without submitting. A violation (exit code 1) means: undo that change, then run it again.

## 5. Procedure per unit

1. Open the unit: click `josm_zoom_url` (JOSM zooms to it) and `streetview_url`.
2. Start the timer.
3. Apply the checklist for the unit type and tier (section 8) in the listed order. Make the edits in JOSM.
4. Stop the timer when the checklist is complete and the edits are done.
5. Fill one row of the record sheet immediately.

Rules:

- Pause the timer for breaks, messages and for looking up how to do something in JOSM. Write the pause minutes. Do not pause for thinking or for waiting for imagery.
- Process the sample units in the given order. Do not skip or reorder them.
- Do not compare your results with the other rater during the pilot.
- If a unit cannot be assessed (no imagery, construction), set `checklist_complete = n`, write the reason in `notes`, and keep the time.
- The edits are real: do not make a change you are unsure about. Put uncertain items in `notes`.

## 6. Warm-up and time budget

- **Warm-up (about 1 hour, excluded from the analysis):** work through the official JOSM beginner guide, then process the warm-up units listed first in your kit (`warmup = true`). Record them like any other unit. Do the warm-up together with the other rater and compare how you read the checklists. After that, work independently.
- **Measured part (about 4 hours):** the order is interleaved across strata, so the units you finish are always a roughly balanced sample, wherever you stop.
- **Calibration check:** after the first 10 measured units compute the mean active minutes per unit and project the total. If the list does not fit in your hours, do not speed up. Stop at the end of your budget.
- When the budget is used up, finish the current unit, fill its row and stop the measured part. Continue with the rest of your zone outside the measurement.

## 7. Work area of a unit

Every pilot unit has a work area, shown as a polygon in `pilot_areas_zone_<N>.osm`:

- **Site:** the convex hull of the nodes of the site plus a 30 m margin (the junction and about 30 m of every approach).
- **Edge (road or tram segment):** the segment plus a 15 m margin, including a 15 m disc around each end node.
- **Bridge group:** the union of the work areas of its edges.

Check and edit only owned objects inside the work area of the unit you are working on. A way that crosses the boundary may be edited where the edit concerns the part inside. Defects outside the work area are counted in `outside_defects` and described in `notes`; do not fix them during the unit.

## 8. Checklists (PROPOSED)

Common checks:

- **C1** The object exists on the ground (imagery date noted).
- **C2** Connectivity: ways are connected at junction nodes (not only overlapping), no duplicated or stacked ways or nodes, no dangling ends where the road continues.
- **C3** The `highway` class matches the function of the road.
- **C4** `oneway` is correct.
- **C5** Access: `access`, `motor_vehicle`, `bus`, `bicycle` where the use is restricted.

### Road edge, tier A (full)

C1–C5, plus: `lanes` (and `lanes:forward` / `lanes:backward`, which must stay consistent with `lanes`); a numeric `maxspeed` that matches the posted limit (a road without a numeric `maxspeed` gets the class default in `netconvert`, for example 80 km/h for a tertiary road, so a missing value is a defect); bicycle infrastructure (`cycleway*` tags, separate cycleways connected); `bridge`, `tunnel`, `layer`; `junction=roundabout`; tram tracks in or beside the carriageway as separate `railway=tram` ways.

### Road edge, tier B (basic)

C1–C5, plus `lanes` only where there are two or more lanes per direction or the tags are inconsistent, a numeric `maxspeed` if it is missing, and the bicycle tag if a cycle lane or track is clearly visible.

### Road edge, tier C (scan)

C1, C2 and C5 only. No lane or speed checks. Mark or remove a `highway=service` stub only if it is clearly wrong.

### Boundary stub

The checklist of its tier, and check that the junction at its inner end is complete.

### Tram segment

Track exists and is continuous across junctions; tagged `railway=tram`; the second track of a double line is present once; connected to adjacent tram segments; tram crossings with roads tagged at the crossing node. Tram stops and public transport relations are out of scope.

### Site (junction, signal or tram crossing)

For every approach: C1–C5; lanes and `turn:lanes`; turn restrictions (`type=restriction` relations exist and are correct where signs or markings prohibit a turn; check their from, via and to members); `highway=traffic_signals` at the stop line of every signalised approach and absent elsewhere (compare with the ZDiUM list if usable); signalised pedestrian crossings: note their presence only (pedestrians are out of the model); roundabouts; tram tracks connected through the junction and crossing nodes tagged; bicycle infrastructure through the junction; `maxspeed` on the approaches.

### Bridge group

Every way of the group: geometry of deck and ramps, `bridge=yes`, `layer`, lanes, `oneway`, both tram tracks if present, connection to the junctions at both ends. End nodes owned by another zone are read-only: report mismatches in `foreign_defects`.

## 9. Overlap units (visitor mode)

Six units (three in zone 3, three in zone 4) are processed by both raters. The owner processes the unit in the real work file as any other unit. The other rater (the visitor) processes the same unit on a **private copy** of the owner's package (`zone_<M>_visitor.osm`), records the time, and then discards the copy. Visitor results are never submitted. The design is balanced, so the effect of working in a foreign zone cancels out in the analysis.

## 10. Recording and submission

Record one row per unit in the `Record` sheet of your kit:

| column | meaning |
|---|---|
| pilot_id, rater, order_index | from the kit |
| start_time, end_time, pause_minutes, active_minutes | wall clock; active = end minus start minus pauses |
| defects_total, defects_G / L / R / S / V / B / T | defects found, by category: Geometry or topology, Lanes, Restrictions, Signals, speed or access (V), Bicycle, Tram |
| edits_made | number of objects changed |
| outside_defects | defects outside the work area (not fixed) |
| foreign_defects | defects on objects owned by another zone (not fixed; ids in notes) |
| imagery_source, imagery_year | source and year of the imagery used |
| checklist_complete | y or n |
| difficulty | 1 easy, 2 normal, 3 hard |
| notes | anything unusual |

Submission at the end of each session: `scripts/submit_edits.sh <zone> zone_<N>_edit.osm`. It verifies the package checksum, derives a change file (`submissions/zone_<N>/<date>/zone_<N>.osc`), and runs the ownership check. The change file is cumulative (all edits since the package). Send the small `.osc` and `.osc.meta.json`, not the `.osm`. The editor index equals the zone number.

## 11. Sources and legal note

Sources in order of use: imagery (Street View, other street-level imagery), the ZDiUM list, knowledge of the place. Record the source and the imagery year in every row. The OpenStreetMap community does not accept data copied from Google Maps or Street View. Edits stay local, but if the cleaned data is ever contributed to OSM or published, the source of the edits must be compatible with OSM rules. The task definition names Street View, so raise this with the supervisor and record the decision in `docs/decisions.md`.

## 12. Quality control and analysis plan

1. Clean: `active_minutes` = end minus start minus pauses. Flag values above 3 times the stratum median, but do not drop them.
2. Rater factor: on the overlap units take the log ratio of the two raters' times. Zone 3 units are visited by R2 and zone 4 units by R1, so the average over all six pairs cancels the visitor effect. Expect an uncertainty of about 15–20%. Cross-check with the rater effect in `log t = stratum + rater + order_index` on all measured units.
3. Learning effect: regress log time on `order_index`. If the time falls by more than 30% from the first to the last third, add a learning factor.
4. Edge strata: fit `t = a + b * length_m` per stratum (robust). Keep `b` only if its 80% bootstrap interval excludes zero; otherwise use the median.
5. Sites: fit `log t = a + b * log(n_units) + c * has_tram`; predictors fixed in advance.
6. Bridges: with one bridge group measured, report minutes per edge and per way only as a rough figure.
7. Uncertainty: bootstrap by unit (1000 resamples), 80% interval per weight.
8. Output `data/derived/work_weights.yaml` and `reports/06_pilot_analysis.md`. Use: zone workload = sum of predicted minutes; re-partition the nine unfrozen zones with these weights; the measured workload of zones 3 and 4 is compared with the plan, and any difference is compensated in the RING 2 assignment.

## 13. Limitations

- The two raters' skill differs from that of the other nine cleaners, and rater and zone are confounded except through the six overlap units.
- Imagery age varies by location.
- Rework, review and merge conflicts are not measured.
- Per-stratum samples are small (3 to 5 per zone), so edge weights will have intervals of 25–40%. The continued work in the zones is the cheapest source of additional timed units.
- Upstream OSM changes after the snapshot (23 Oct 2026) are not applied (offline rule); our data diverges from live OSM.