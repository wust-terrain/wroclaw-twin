# Pilot protocol: time per work unit in the frozen zones 3 and 4

Status: PROPOSED (version 3). It defines how the two pilot raters clean their own zone in JOSM, what "full", "basic" and "scan" validation mean (decision D4), and how the time per work unit is measured. The pilot work is **kept**: the edits are real cleaning of the rater's zone. The result is a table of minutes per unit and stratum, used as work weights when the other nine zones are re-partitioned.

## 1. Design

- Two raters. R1 owns **zone 3**, R2 owns **zone 4** (zones of partition v0.2, frozen). Each rater works only in the package of their own zone (package version 2) and only on objects the zone owns.
- A stratified sample of units, drawn inside the rater's own zone, is processed first, in the order given in the kit. After the sample the rater continues with the rest of the zone.
- Six overlap units (three in each zone) are also processed by the other rater, on a private copy that is discarded. They separate the raters' speed from the difficulty of their zones.
- Budget: about 5 hours per rater: about 1 hour of warm-up (units are real work but excluded from the analysis) and about 4 hours of measured work. The setup of the machine (`docs/pilot/ONBOARDING.md`, about 30-40 minutes) is outside this budget.

Not measured: navigation between units, breaks, the SUMO network build, the quality of the final data.

## 2. Materials (per rater)

- Package of the zone: `data/derived/zones_v02/zone_<N>/zone_<N>.osm` with its sidecar `zone_<N>.json`. **Never edit or overwrite it.**
- Reference layer `zone_<N>_reference.osm` (zone polygon, 60 m read buffer, seam edges, `owned_outside_polygon` buffers) and `pilot_areas_zone_<N>.osm` (work area of every pilot unit, tagged with its `pilot_id`). Open them as extra layers. Never edit or save them.
- `zone_<N>_units.csv`, `zone_<N>_seams.csv`, `zone_<N>_bridges.csv`: your units, the seam edges with their owners, your bridge groups.
- Your kit `data/derived/pilot_kit/<rater>/units_<rater>.xlsx` (units in order with links, and a pre-filled record sheet).
- `scripts/josm_pilot.sh` (starts JOSM offline) and `scripts/submit_edits.sh` (checks and submits your edits). The JOSM jar comes with the handoff, not from the internet.
- A stopwatch that can be paused.

## 3. Session routine

1. Start JOSM only with `scripts/josm_pilot.sh`. It starts JOSM with `--offline=osm_api`, so nothing can be downloaded, updated or uploaded from the OSM server. Remote control must allow only "Change the viewport" and "Read protocol version".
2. First session: `cp zone_<N>.osm zone_<N>_edit.osm`. Later sessions: never copy again (it would overwrite your work); use `cp -n`.
3. Open `zone_<N>_edit.osm` as the data layer and the reference layers. Work only in the data layer.
4. Save often with File > Save (it writes `zone_<N>_edit.osm`). The layer name keeps an asterisk after saving; this is normal. When you close JOSM choose "Exit now" (never Upload). At the end of the session keep a dated copy `zone_<N>_edit_<date>.osm`.
5. End of the session: run `scripts/submit_edits.sh zone_<N> zone_<N>_edit.osm --dry-run`. Compare the line "changed objects" with your own notes of what you did: JOSM's Undo can silently remove an earlier edit (this happened in the tests). Fix every violation (undo that change), then run the command **without** `--dry-run` to write the submission (section 10).
6. **Never** use File > Update data, Download data, Upload, or "Save As" over a package. An accidental Update data fills the file with server data; the submission refuses such a file, and the work must be redone from a copy made before the update.
7. Do not paste (Ctrl+V) objects by accident: a pasted way with one node is reported as an invalid object, and an unused pasted node as an orphan.

## 4. Ownership rules in practice

Every object has exactly one owner zone. You edit only what your zone owns.

- Ways: you own a way if your zone has the largest share of its length. A way that spans two zones is edited only by its owner; the other zone reports the needed change. Warnings for spanning ways (exit code 2) are expected and are not errors. When you split a spanning way, write the split point in `notes`.
- Nodes: a node owned by another zone is read-only. Do not move, delete or retag it, also when it is the end node of a way you own (bridge ends on the other bank, seam nodes).
- Relations (turn restrictions): owned by the zone of the via member (without via, of the from way). Change only restrictions you own. When you change `restriction=`, update or delete the `name` tag so that it does not contradict it.
- Split Way and Combine Ways: JOSM changes the memberships in relations by itself (for example the `from` member of a turn restriction moves to the part that touches the via node). The check accepts this as a derived edit when you own the split or combined way, also when the relation belongs to another zone. Look at the relation after the operation and make sure it is still attached to the right part.
- Merge Nodes: allowed when you own both nodes and every way that uses the deleted node. Otherwise the check reports a violation: ask the owner.
- New ways: a new way may use a foreign node only when you split or redraw one of your own ways that already used it. A new connection to a foreign node is a violation: ask the owner.
- Delete: JOSM deletes only the nodes that no other way uses; check that the check reports no node that is still used.
- Bridge groups are defined by geometry (ways that cross the Odra), not by OSM tags, so many of their ways are approach ways without `bridge=*`. The owner edits all ways of the group; end nodes owned by another zone are read-only.
- Objects outside your zone polygon but inside `owned_outside_polygon` buffers are yours. Objects with no owner (outside RING 1) are read-only.
- Seven nodes of the whitelist `shared_editable_nodes.csv` may be edited by both zones, unless their owner is the other pilot zone; the check shows a warning.
- If you need a change on a foreign object, do not make it. Count it in `foreign_defects` and write its id and the change in `notes`. Once a day send the other rater and the merger the list of such requests.

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
- Time **every bridge group** you clean and every large site, also when it is not in the sample (add a row with `pilot_id` = `X-<group or site id>`). After the sample, time further units as you go if you can; this is the cheapest source of extra data.

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

After Split Way review the tags that JOSM copied to both parts (for example `lanes`, `turn:lanes`, `maxspeed`, `length`): a tag that applies to one part only must be changed.

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

For every approach: C1–C5; lanes and `turn:lanes`; turn restrictions (`type=restriction` relations exist and are correct where signs or markings prohibit a turn; check their from, via and to members; remove a duplicate restriction that has the same tags and members as another); `highway=traffic_signals` at the stop line of every signalised approach and absent elsewhere (compare with the ZDiUM list if usable); signalised pedestrian crossings: note their presence only (pedestrians are out of the model); roundabouts; tram tracks connected through the junction and crossing nodes tagged; bicycle infrastructure through the junction; `maxspeed` on the approaches.

How to edit a restriction in JOSM: Relations panel, New relation, tags `type=restriction` and `restriction=...`, members with the roles `from` (way), `via` (node) and `to` (way). No turn-restriction preset was found in JOSM 19613 in our setup.

### Bridge group

Every way of the group: geometry of deck and ramps, `bridge=yes` on the deck ways, `layer`, lanes, `oneway`, both tram tracks if present, connection to the junctions at both ends. Approach ways may legitimately have no `bridge` tag. End nodes owned by another zone are read-only: report mismatches in `foreign_defects`.

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

Submission at the end of each session: `scripts/submit_edits.sh zone_<N> zone_<N>_edit.osm` (first with `--dry-run`, see section 3). It verifies the package checksum, derives a change file (`submissions/zone_<N>/<date>/zone_<N>.osc` and `.osc.meta.json`), and runs the ownership check. The change file is cumulative (all edits since the package), so the newest file replaces the older ones. Send the two small files and the record-sheet xlsx to the channel given in `ONBOARDING.md`, not the `.osm`. The editor index equals the zone number.

Exit codes of the checks: 0 ok; 1 violation or conflict (fix it); 2 warnings only (expected for spanning ways; add a short note); 3 contaminated input (the file contains server data: redo the work from a copy made before); 4 package or base mismatch; 64 and 70 usage errors and failing steps.

## 11. Sources and legal note

Sources in order of use: imagery (Street View, other street-level imagery), the ZDiUM list, knowledge of the place. Record the source and the imagery year in every row. The OpenStreetMap community does not accept data copied from Google Maps or Street View. Edits stay local, but if the cleaned data is ever contributed to OSM or published, the source of the edits must be compatible with OSM rules. The task definition names Street View, so this must be decided with the supervisor and recorded in `docs/decisions.md` (D11) before the pilot edits are used outside the project. Until then, no data derived from the edits is published.

## 12. Quality control and analysis plan

1. Clean: `active_minutes` = end minus start minus pauses. Flag values above 3 times the stratum median, but do not drop them.
2. Rater factor: on the overlap units take the log ratio of the two raters' times. Zone 3 units are visited by R2 and zone 4 units by R1, so the average over all six pairs cancels the visitor effect. Expect an uncertainty of about 15–20%. Cross-check with the rater effect in `log t = stratum + rater + order_index` on all measured units.
3. Learning effect: regress log time on `order_index`. If the time falls by more than 30% from the first to the last third, add a learning factor.
4. Edge strata: fit `t = a + b * length_m` per stratum (robust). Keep `b` only if its 80% bootstrap interval excludes zero; otherwise use the median.
5. Sites: fit `log t = a + b * log(n_units) + c * has_tram`; predictors fixed in advance.
6. Bridges: time of every bridge group cleaned by R1 (seven groups) gives minutes per group and per way; report them with their sizes.
7. Uncertainty: bootstrap by unit (1000 resamples), 80% interval per weight.
8. Output `data/derived/work_weights.yaml` and `reports/06_pilot_analysis.md`. Use: zone workload = sum of predicted minutes; re-partition the nine unfrozen zones with these weights; the measured workload of zones 3 and 4 is compared with the plan, and any difference is compensated in the RING 2 assignment.

## 13. Limitations

- The two raters' skill differs from that of the other nine cleaners, and rater and zone are confounded except through the six overlap units.
- Imagery age varies by location.
- Rework, review and merge conflicts are not measured.
- Per-stratum samples are small (3 to 5 per zone), so edge weights will have intervals of 25–40%. The continued work in the zones is the cheapest source of additional timed units.
- Upstream OSM changes after the snapshot (23 Oct 2026) are not applied (offline rule); our data diverges from live OSM.