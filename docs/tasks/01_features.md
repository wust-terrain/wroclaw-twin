# Task 01: OSM feature layers for the RING 1–3 area

## Goal

Build, from the frozen OSM extract, a set of layers (GeoPackage) from which task 02 will compute the work weights and the partition of RING 1 into 11 zones. The task is deliberately based on OSM rather than on a `netconvert` network, because the `netconvert` import configuration has not been decided yet.

## Out of scope

Partitioning, weights, digitising the polygon, running `netconvert`, editing OSM.

## Inputs

- `data/interim/wroclaw_r123.osm.pbf`
- `data/interim/kbr_points.gpkg` (layer `points`, EPSG:2177, columns `Kordon`, `Pkt_pomiar`)
- `config/scope.yaml` (to be created, see below)

## Steps

### 0. Input verification

Create `scripts/verify_inputs.sh`: it checks the snapshot sha256 from `CLAUDE.md` and that the input files exist. It exits with an error on a mismatch.

### 1. `config/scope.yaml`

Create a file with the content below. Items marked `[TO BE CONFIRMED]` are working assumptions. Do not change them without agreement.

```yaml
highway_include:
  - motorway
  - motorway_link
  - trunk
  - trunk_link
  - primary
  - primary_link
  - secondary
  - secondary_link
  - tertiary
  - tertiary_link
  - unclassified
  - residential
  - living_street
  - service          # [TO BE CONFIRMED]
  - road             # [TO BE CONFIRMED]
  - track            # [TO BE CONFIRMED]
  - cycleway         # bicycles are in the model
# pedestrians are out of the model: these types are included only where bicycles are allowed
highway_if_bicycle_allowed:
  types: [footway, pedestrian, path]
  bicycle_values: [yes, designated, permissive]
highway_exclude: [steps, corridor, platform, bridleway, elevator, construction, proposed, raceway]
railway_include: [tram]
rail_in_scope: false              # [TO BE CONFIRMED]
signal_cluster_eps_m: 20          # close to the default tls.join-dist in netconvert (to be verified)
junction_cluster_eps_m: 15        # [TO BE CONFIRMED]
```

### 2. `src/10_build_features.py`

Read the extract with `pyosmium` (`osmium.FileProcessor(...).with_locations()`), build geometries with `shapely`, reproject to EPSG:2177, and cluster with single linkage (`scipy.spatial.cKDTree.query_pairs` + connected components from `scipy.sparse.csgraph`). Write `data/interim/features.gpkg` in EPSG:2177 with the layers:

| Layer | Geometry | Columns |
|---|---|---|
| `ways` | LineString | `osm_id`, `highway`, `railway`, `is_tram`, `length_m`, `oneway`, `lanes`, `maxspeed`, `bridge`, `tunnel`, `service`, `bicycle`, `access`, `cycleway_raw` (raw values of the `cycleway*` tags joined with commas), `name` |
| `signal_nodes` | Point | `osm_id`, `kind` (`junction_signal` for `highway=traffic_signals`, `crossing_signal` for `highway=crossing` + `crossing=traffic_signals`), `bicycle`, `cluster_id` |
| `signal_clusters` | Point (centroid) | `cluster_id`, `n_nodes`, `n_junction`, `n_crossing`, `kind` (`junction` if `n_junction` ≥ 1, otherwise `crossing_only`) |
| `junction_nodes` | Point | `osm_id`, `degree` (number of in-scope road segment ends meeting at the node: an interior node of a way counts 2, an end node counts 1; only nodes with `degree` ≥ 3 go into the layer), `has_signal`, `is_roundabout`, `has_tram`, `junction_cluster_id` |
| `junction_clusters` | Point (centroid) | `junction_cluster_id`, `n_nodes`, `max_degree`, `has_signal`, `has_roundabout`, `has_tram` |
| `tram_crossings` | Point | `osm_id` (nodes shared by a tram way and an in-scope road way) |
| `kbr_points` | Point | copy of `kbr_points.gpkg` (columns `Kordon`, `Pkt_pomiar`) |

Objects outside the scope (`scope.yaml`) do not go into the layers. For `footway`, `pedestrian` and `path` ways apply the `highway_if_bicycle_allowed` rule.

### 3. Report `reports/01_features.md`

It contains: the number of objects in each layer, a table of road km by `highway` class (tram track km separately), the number of signal nodes by `kind`, the distribution of signal cluster sizes, the distribution of `degree` in `junction_nodes`, the number of junction clusters, the number of KBR points by `Kordon`, and the run time.

## Correctness checks (expected values)

| Measurement | Expectation | On a discrepancy |
|---|---|---|
| `signal_nodes` with `kind = junction_signal` | exactly **1207** | stop |
| `signal_nodes` with `kind = crossing_signal` | at least **2012** (that figure covers only the nodes that the `netconvert` import turned into signals; OSM may have more, e.g. on pedestrian ways outside the scope) | report the value and explain the difference |
| `signal_clusters` (eps 20 m) | within ±15% of **1332** (result of `netconvert --junctions.join --tls.join`) | report the discrepancy, do not tune `eps` to the result |
| `kbr_points` | R1 = 23, R2 = 30, R3 = 22 | stop |
| Geometry | all geometries valid, CRS EPSG:2177 | stop |
| `ways` | no ways from a class in `highway_exclude` | stop |

The ±15% tolerance is a heuristic: the joining algorithm in `netconvert` differs from single-linkage clustering, so we expect agreement in order of magnitude, not exact agreement.

## Definition of done

- `scripts/verify_inputs.sh`, `config/scope.yaml`, `src/10_build_features.py` and the report exist, and the script is idempotent (a second run gives identical counts).
- All checks from the table passed, or the discrepancies are described in the report.
- The report lists the assumptions from `scope.yaml` marked `[TO BE CONFIRMED]` and their effect on the numbers (e.g. km of `service` and `track` roads separately).