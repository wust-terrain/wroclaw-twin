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