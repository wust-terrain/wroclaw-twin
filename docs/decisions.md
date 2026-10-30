# Decisions

## D1: Signalised pedestrian crossings in the model
- Status: OPEN
- Question: are `highway=crossing` + `crossing=traffic_signals` nodes signals in the SUMO model?
- Context: pedestrians are out of the model; 2012 such nodes exist in RING 1–3.
- Options: (a) exclude them, (b) keep them as signals.
- Decision / date / who: -

## D2: RING 1 polygon definition

- **Date:** 2026-10-25
- **Status:** DECIDED
- **Decision:** RING 1 is a coarse hand-digitised polygon enclosing all 23 KBR 2018
  RING 1 counters (r1_01-r1_23) and their junctions. It is the working area for
  the OSM cleaning split into 11 zones.
- **Rule:** boundary drawn just outside the counters; counter junctions fully
  inside; minor side streets near the boundary may be cut (139 junction clusters
  lie within 30 m of the boundary and were reviewed manually); the boundary does
  not follow the moat, railway or river closely (23 straight segments).
- **Margin:** minimum ~55 m (r1_19), then r1_20 ~71 m and r1_11 ~85 m; 18 of 23
  counters are more than 150 m from the boundary. Area ~7.1 km2. ~1.51 times bigger 
  than the polygon connecting all the KBR points. 6% of points are >300m far from the KBR.
- **Verification:** Select by Location (KBR points `Kordon = 'R1'` within `ring1`)
  returns 23/23.
- **Files:** `data/derived/ring_polygons.gpkg` (layer `ring1`, EPSG:2177),
  `data/derived/ring1.geojson` (EPSG:4326, for sharing), `qgis/ring1.qgz`.
- **Not decided here:** the junction membership rule for the zone split (e.g. a
  junction belongs to RING 1 if its `junction_clusters` point lies inside the polygon).

  ## D3: Junction membership rule for the RING 1 / RING 2 split

- **Date:** 2026-10-25
- **Status:** DECIDED
- **Decision:** a junction cluster belongs to RING 1 iff its centroid lies inside the RING 1 polygon (D2). A road segment between junction clusters belongs to RING 1 iff at least one of its end clusters does. Everything else is handled in the RING 2 stage.
- **Rationale:** junction clusters are atomic; the polygon is a selector and need not follow streets; segments with one end outside ("boundary stubs") give a natural one-segment overlap at the seam.
- **Alternatives:** any member node inside (larger area, ambiguous); all member nodes inside (large junctions on the boundary fall out).
- **Checks:** all 23 counter junctions are inside; sensitivity of cluster counts to the three rules reported in `reports/02_ring1_membership.md`.
- **Polygon freeze point:** before OSM cleaning starts (zones get owners).  

## D4: Validation tiers (work depth per road segment)

- **Date:** 2026-10-25
- **Status:** PROPOSED (to be re-confirmed after the timing pilot)
- **Decision:** use the `tier_tag` variant. Tram tracks are a separate category measured in km, not part of tier A.
- **Tiers:** A = full validation (secondary and above, links, cycleway); B = basic validation (residential, living_street, unclassified, and through service/path edges not tagged driveway, parking_aisle, alley or emergency_access); C = imported without edge-by-edge validation, checked by sampling (tagged driveways and parking aisles, dead-end spurs, track, footway, pedestrian).
- **RING 1 km (`tier_tag`):** A 119.4 (of which tram 43.3), B 85.3, C 86.5.
- **Rejected:** `tier` (B 127.6 km, of which 50.9% service-through including 32.7 km of driveways); `tier_topo` (barely differs from `tier`: 2003 of 7767 C-base components have two or more attachments and hold 76% of C-base km).
- **Known gap:** 22.85 km of untagged `service` edges stay in tier B; the pilot samples them as a separate stratum.
- **Open:** what "full" and "basic" validation mean in terms of checked attributes; to be defined together with the pilot checklist.

## D6: Pilot zones (frozen)

- **Date:** 2026-10-25
- **Status:** PROPOSED
- **Decision:** v0.2 zones 3 and 4 are frozen as they are and assigned to the two pilot raters (one each). The other nine zones are re-partitioned after the pilot with measured weights.
- **Rationale:** neighbours with a shared seam (21 edges, 1.14 km); together 3 of the 14 large sites, 16 of 76 sites with a tram crossing, and enough edges in every stratum (361 A, 167 B-core, 206 B-service, 416 C, 81 tram ways).
- **Known:** zone 3 is the heaviest zone (2219 S0 minutes, 112% of the mean), zone 4 the third (108%); weights are guesses. Zone 3 owns 7 bridge groups and 4 islands.
- **Consequence:** pilot work is kept; any difference between measured and assumed workload is compensated in the RING 2 assignment.

## D7: RING 1 zone partition v0.2

- **Date:** 2026-10-25
- **Status:** PROPOSED (provisional until re-partition with measured weights)
- **Decision:** RING 1 is split into 11 zones built from street blocks, with the Odra as a barrier. A bridge group has exactly one owner and its strip never reaches the other bank. Zones 8 + 3 across the two banks (the smaller bank holds zones 1, 2, 11).
- **Rationale:** v0 zones had tongues, crossed the Odra and cut through large junctions.
- **Balance:** max/mean 1.094 on faces, 1.116 after ownership. The smaller bank is structurally lighter (zones 1, 2, 11 at 75-82% of the mean); compensated in the RING 2 assignment.
- **Cost:** seam edges grew from 101 (9.4 km) to 252 (16.7 km).
- **Weights:** unmeasured guesses (S0); the partition is recomputed after the pilot.


## D8: Ownership of OSM objects

- **Date:** 2026-10-25
- **Status:** PROPOSED
- **Decision:** every OSM object inside RING 1 has exactly one owner zone. Way: the zone with the largest share of the way's length in RING 1; all ways of a bridge group follow the group owner. Node: the zone of its junction cluster; otherwise the zone of its site; otherwise the owner of the longest owned way using it. Relation (turn restriction): owner of the via member. Seam edge: the zone with the larger sum of max_degree of the end clusters. Sites are atomic.
- **Rules for editors:** a zone edits what it owns. Spanning ways: the owner edits tags, the other zone reports defects in notes. Nodes owned by another zone are read-only (including end nodes of bridges on the opposite bank). Seven site/cluster conflict nodes are editable by both zones, with a warning.
- **Rationale:** a single owner per object avoids merge conflicts; the ownership check (task 04r) enforces it.
- **Checked:** 223 spanning ways (1.3%) and 614 shared nodes across all zones; for the pilot pair 22 ways and 66 nodes.

## D9: JOSM runs offline on a frozen snapshot

- **Date:** 2026-10-28
- **Status:** PROPOSED
- **Decision:** cleaners start JOSM with `--offline=osm_api` (scripts/josm_pilot.sh) and never use File > Update data or Download. A saved file that carries server metadata (uid, user, changeset), invisible objects, versions different from the base, or positive-id objects absent from the base is rejected, not repaired.
- **Evidence:** an accidental Update data in the zone 4 test added 6 upstream deletions (26-27 Oct, after the 23 Oct snapshot) and server metadata to over 10,000 objects.
- **Consequence:** our data diverges from live OSM from the snapshot date on. Whether and how it is rebased later is a separate decision.

## D10: netconvert import configuration

- **Date:** 2026-10-28
- **Status:** OPEN
- **Question:** which type map and options for the model network (urban speed defaults, bicycle import, removal of pedestrian edges).
- **New evidence (report 09):** a tertiary way with only `maxspeed:type=PL:urban` gets 22.22 m/s (80 km/h) in the default import; ways with a numeric `maxspeed` get that value.
- **Consequence for cleaning:** a numeric `maxspeed` is a checklist item; in-scope ways without it are counted as defects.
- **Next:** compare the default and the urban (50 km/h) type maps on RING 1 (count of ways without numeric `maxspeed` by class and zone).