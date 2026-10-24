# CLAUDE.md

Instructions for the agent working in this repository. Read the whole file before every task.

## Project

A group MSc AI research project (Wrocław University of Science and Technology): traffic signal control with multi-agent reinforcement learning (MARL) on a digital twin of Wrocław's road network (SUMO; MATSim as the demand generator). The current stage is network preparation: the RING 1 area from KBR 2018 is split into 11 zones for independent OSM cleaning, then RING 2. The SUMO model boundary is RING 2. The MATSim area is to be decided.

You run scripts and analyses. Scope and domain decisions belong to the team. When the data does not match the assumptions, **report the discrepancy and stop** instead of silently fixing it or tuning parameters by eye.

## Model scope (decided)

- pedestrians: out of the model (for now)
- bicycles: in the model
- trams: in the model
- road classes: all (tentatively)

## Open decisions (do not settle them yourself)

- whether signalised pedestrian crossings (`highway=crossing` + `crossing=traffic_signals`) are signals in the model
- scope of railways other than trams
- `netconvert` import configuration (type map, bicycle import, removal of pedestrian edges)
- the RING 1 polygon (manual digitisation in QGIS, it does not exist yet)
- work weights and the balance criterion (after the timing pilot)
- how OSM is edited (local patches or live OSM)

## Environment and data

Full instructions and control values: `docs/SETUP.md`. Frozen inputs:

- OSM snapshot: `data/raw/osm/dolnoslaskie_2026-10-23.osm.pbf`, sha256 `4b708241a7b9af4170e8dc2c11ba94b86154791a6d5f437b6bf27d5a5f4689db`
- SUMO/`netconvert` 1.28.0, `osmium` 1.16.0, Python 3.12 (`uv`)
- extract `data/interim/wroclaw_r123.osm.pbf` (roads, tracks and turn restrictions only), cutting box `16.9002,51.0440,17.1524,51.1836`
- KBR 2018: `data/raw/kbr2018/` (count points in `points/`, coordinate system EPSG:2177)

KBR (Kompleksowe Badania Ruchu) is the 2018 Comprehensive Traffic Survey of Wrocław; RING 1–3 are groups of count points forming rings around the city centre.

At the start of every task verify the snapshot checksum (`scripts/verify_inputs.sh`). On a mismatch, abort.

## Repository layout

```
CLAUDE.md
config/        # task parameters (YAML), in git
src/           # scripts NN_name.py, in git
scripts/       # shell scripts, in git
docs/          # SETUP.md, decisions.md, tasks/NN_*.md, in git
reports/       # run reports (markdown), in git
data/raw/      # NOT in git, read-only
data/interim/  # NOT in git, intermediate products
data/derived/  # in git, small results (zones, weights)
logs/          # NOT in git
```

## Working rules

1. `data/raw/` is read-only. Never modify or delete these files.
2. Do metric computations in EPSG:2177. Write files exchanged with others (GeoJSON) in EPSG:4326.
3. Scripts must be idempotent, numbered (`NN_name.py`), parametrised from `config/`, and log to `logs/`. No parameters hard-coded in the code.
4. Do not add dependencies without agreement (`uv add` only after approval). Allowed: `scipy`.
5. Do not download anything from the network. All data is local and frozen.
6. After every run print a control table, compare it with the expected values and save a report in `reports/`. If a discrepancy exceeds the threshold given in the task, stop and describe it.
7. Do not commit or push unless explicitly asked.
8. Comments and documentation in English; identifiers in code in English.

## Known pitfalls

- `highway=traffic_signals` (1207 nodes in the extract) is **not** the number of signals in the model. The default `netconvert` import also treats 2012 `highway=crossing` + `crossing=traffic_signals` nodes as signals. The RING 1–3 network has 3220 signals, and 1332 after `--junctions.join --tls.join`.
- `osmium extract --strategy complete_ways` keeps ways whole, so the data bounding box of the extract is a few km wider than the cutting box. Do not treat the box from `osmium fileinfo` as a check.
- KBR: the column `Ogółem liczba samochodów` ("total number of cars") also includes bicycles and motorcycles. The hour label denotes the end of the interval (e.g. `01:00:00` means 00:00–01:00). In the `BAZA DANYCH` sheet the last row is a totals row (empty labels) that must be dropped. The points shapefile requires an explicit `set_crs(2177)`. For point `r1_02` the measurement date differs between sheets (2018-04-17 vs 2018-06-12); the numbers are identical.
- The `R1` points (23) do not form a clean ring (angular order zigzags, `r1_17` and `r1_18` are about 100 m apart), so the interior polygon has to be digitised manually.

## Task plan

1. `docs/tasks/01_features.md`: OSM feature layers for RING 1–3.
2. Timing pilot and work weights (humans), then the weights script.
3. Partitioning RING 1 into 11 zones (after the polygon is digitised).
4. Report with the rationale for the decisions (the DoD document).