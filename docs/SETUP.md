# SETUP: environment and input data

Goal: every team member has **the same environment and exactly the same input data**, so zone partitioning, OSM cleaning and SUMO networks are comparable and reproducible.

Terminology: **KBR** (Kompleksowe Badania Ruchu) is the Comprehensive Traffic Survey of Wrocław and its surroundings, conducted in 2018. **RING 1–3** are the groups of traffic count points that form concentric rings around the city centre in that survey. **ZDiUM** (Zarząd Dróg i Utrzymania Miasta) is the Wrocław municipal roads authority.

Two rules the rest of this document follows from:

1. **Do not download `dolnoslaskie-latest.osm.pbf` on your own.** The `-latest` file changes daily. Everyone uses one frozen snapshot and verifies it with a checksum.
2. **The SUMO version is pinned.** The network produced by `netconvert` depends on its version.

This guide was tested on Ubuntu 24.04. Other systems are unverified (on Windows, WSL2 with Ubuntu 24.04 is probably the simplest option, but we have not tested it).

---

## 0. Frozen inputs

| Item | Value |
|---|---|
| OS | Ubuntu 24.04 |
| SUMO / `netconvert` | **1.28.0** (PPA `ppa:sumo/stable`) |
| Python | 3.12 (managed by `uv`) |
| OSM snapshot | `data/raw/osm/dolnoslaskie_2026-10-23.osm.pbf` |
| Data timestamp (`osmosis_replication_timestamp`) | `2026-10-23T20:20:51Z` |
| File size | 181,792,406 B |
| SHA-256 | `4b708241a7b9af4170e8dc2c11ba94b86154791a6d5f437b6bf27d5a5f4689db` |
| Source | Geofabrik, `europe/poland/dolnoslaskie` |
| KBR 2018 data | `23.10.2026 https://bip.um.wroc.pl/attachments/download/75769` |
| `osmium` (osmium-tool) | 1.16.0 |

Changing any row is a **team decision**: change this table in a separate commit and record the reason in `docs/decisions.md`. Results (zones, weights, reports) always state which snapshot they were produced from.

---

## 1. Installing the tools

```bash
sudo add-apt-repository ppa:sumo/stable
sudo apt-get update
sudo apt-get install sumo sumo-tools sumo-doc osmium-tool qgis
echo 'export SUMO_HOME="/usr/share/sumo"' >> ~/.bashrc
source ~/.bashrc
curl -LsSf https://astral.sh/uv/install.sh | sh     # if you do not have uv yet
```

Check the versions:

```bash
netconvert --version | head -1     # expected: Eclipse SUMO netconvert 1.28.0
osmium --version | head -1
uv --version
echo "$SUMO_HOME"                  # expected: /usr/share/sumo
test -d "$SUMO_HOME/data/typemap" && echo "typemap OK"
```

If `SUMO_HOME` is empty, run `source ~/.bashrc` or open a new terminal. Without this variable `netconvert` prints warnings and uses its built-in road type maps, so results may differ between people.

If the PPA already offers a newer SUMO version than 1.28.0, **do not upgrade on your own**. Check `apt-cache policy sumo` and report it to the team.

JOSM is installed later, at the cleaning stage (from the project's official website, because distribution packages tend to be outdated).

## 2. Repository and Python environment

```bash
git clone https://github.com/wust-terrain/wroclaw-twin
cd wroclaw-twin
uv sync
mkdir -p data/raw/osm data/raw/kbr2018/points data/interim data/derived
```

`uv sync` installs the dependencies from `pyproject.toml` and `uv.lock`, so do not use `uv add` without agreement. If `pymetis` fails to install, report it. We will pick an alternative (KaHIP or a custom implementation on top of `networkx`).

`data/raw/` and `data/interim/` are in `.gitignore`. Raw data is not committed.

## 3. KBR 2018 data

Unpack the package with the road traffic measurements and copy the files:

```bash
REPO=$(pwd)
cd /path/to/unpacked/package     # directory containing the .xlsx files and EtapV-2_Punkty_*
cp *.xlsx "$REPO/data/raw/kbr2018/"
cp EtapV-2_Punkty_pomiarowe_ruchu_drogowego.{shp,dbf,shx,prj,cpg,sbn,sbx,xml} "$REPO/data/raw/kbr2018/points/"
cd "$REPO/data/raw/kbr2018"
mv *ring\ 1.xlsx ring1.xlsx
mv *ring\ 2.xlsx ring2.xlsx
mv *ring\ 3.xlsx ring3.xlsx
cd "$REPO"
```

The file names in the original package have broken encoding of Polish characters. Renaming the three ring files to ASCII is therefore mandatory, because the scripts refer to `ring1.xlsx`, `ring2.xlsx` and `ring3.xlsx`. Leave the other xlsx files unchanged.

The shapefile coordinate system is ETRF2000-PL / CS2000/18 (EPSG:2177). `geopandas` does not pick it up automatically from the `.prj`, so the scripts set it explicitly.

## 4. OSM snapshot

**Option A (try first): the dated file on Geofabrik.** The server also keeps files with the date in the name, but not permanently:

```bash
cd data/raw/osm
curl -LO https://download.geofabrik.de/europe/poland/dolnoslaskie-261023.osm.pbf
mv dolnoslaskie-261023.osm.pbf dolnoslaskie_2026-10-23.osm.pbf
cd ../../..
```

If you get a 404, or the checksum (below) does not match, go to option B.

**Option B: the team copy.** Download `dolnoslaskie_2026-10-23.osm.pbf` from `https://drive.google.com/file/d/1bnzrQAgaZxDZa6urcRYAaz0iTsWHokj9/view?usp=drive_link` and put it in `data/raw/osm/`.

**Verification (mandatory):**

```bash
echo "4b708241a7b9af4170e8dc2c11ba94b86154791a6d5f437b6bf27d5a5f4689db  data/raw/osm/dolnoslaskie_2026-10-23.osm.pbf" | sha256sum -c
osmium fileinfo data/raw/osm/dolnoslaskie_2026-10-23.osm.pbf | grep osmosis_replication_timestamp
```

Expected: `OK` and `osmosis_replication_timestamp=2026-10-23T20:20:51Z`. With any other result **do not continue**, and do not download `-latest` as a replacement.

## 5. OSM extract for RING 1–3

The extract is derived from the frozen file (it can be cut again at any time), so we do not version it in git. The area is a bounding box around the `R1`–`R3` KBR points plus a margin of about 3 km. First we filter only the objects needed for the road network and tracks, then we cut the bounding box.

Note: `--strategy complete_ways` keeps ways whole, so ways that stick out of the box bring in nodes from outside it. The data bounding box reported by `osmium fileinfo` is therefore wider than the cutting box and **is not a correctness check**. Exact clipping to the area is done later (zone polygon, or the `netconvert --keep-edges.in-geo-boundary` option).

```bash
BBOX=$(uv run python src/00_kbr_points.py)
echo "$BBOX"
osmium tags-filter data/raw/osm/dolnoslaskie_2026-10-23.osm.pbf \
  w/highway w/railway r/type=restriction \
  -o data/interim/wroclaw_roads.osm.pbf --overwrite
osmium extract --bbox "$BBOX" --strategy complete_ways \
  data/interim/wroclaw_roads.osm.pbf -o data/interim/wroclaw_r123.osm.pbf --overwrite
```

The filter drops, among other things, buildings, land use, administrative boundaries, waterways and public transport lines. If the model needs them, we cut them again from the frozen file.

The script `src/00_kbr_points.py` converts the KBR points to `data/interim/kbr_points.gpkg` and prints the bbox in `W,S,E,N` format.

Expected bbox (script output): `16.9002,51.0440,17.1524,51.1836`.

Quick check of the extract (the signal count also includes signals on ways that stick out of the box):

```bash
osmium fileinfo -e data/interim/wroclaw_r123.osm.pbf
osmium tags-filter data/interim/wroclaw_r123.osm.pbf n/highway=traffic_signals \
  -o /tmp/ts.osm.pbf --overwrite && osmium fileinfo -e /tmp/ts.osm.pbf
```

Control values for this snapshot and `osmium` 1.16.0 (everyone should get identical results):

| Measurement | Expected value |
|---|---|
| Extract `wroclaw_r123.osm.pbf`: nodes / ways / relations | 524,073 / 132,766 / 1,194 |
| Extract size | ca. 7.5 MB (7,527,278 B) |
| Data bounding box of the extract (`fileinfo`) | `16.8779,51.0156,17.2081,51.2331` |
| `highway=traffic_signals` nodes | **1207** (all inside the cutting box) |

The data bounding box is a few km wider than the cutting box (the `complete_ways` effect). This is normal. Note that this counts only nodes tagged `highway=traffic_signals` and is **not the number of signals in the model**. `netconvert` also imports `highway=crossing` + `crossing=traffic_signals` nodes as signals (section 6b), and every carriageway and every crossing is a separate OSM node. Byte-for-byte equality of the extract depends on the `osmium` version, so we compare counts, not checksums.

## 6. SUMO smoke test

Checks that the tools work together, on a small area in the city centre:

```bash
osmium extract --bbox 17.015,51.095,17.055,51.12 data/interim/wroclaw_r123.osm.pbf \
  -o /tmp/test.osm.pbf --overwrite
osmium cat /tmp/test.osm.pbf -o /tmp/test.osm --overwrite
netconvert --osm-files /tmp/test.osm -o /tmp/test.net.xml
```

Expected: the message `Success.` at the end. Hundreds of warnings are normal for OSM in the centre of a large city. There should be no warnings about `SUMO_HOME` (section 1). Size check of the test network: `grep -c '<tlLogic' /tmp/test.net.xml` and `grep -c 'type="traffic_light"' /tmp/test.net.xml` should give **862** and **862** (for `netconvert` 1.28.0 with default options). The `netconvert` options here are the defaults and serve only as a test. The model parameters will be decided separately and recorded in `docs/decisions.md`.

## 6b. Full RING 1–3 network (control values)

```bash
BBOX=16.9002,51.0440,17.1524,51.1836
osmium cat data/interim/wroclaw_r123.osm.pbf -o /tmp/r123.osm --overwrite
time netconvert --osm-files /tmp/r123.osm -o /tmp/r123.net.xml \
  --keep-edges.in-geo-boundary "$BBOX" > /tmp/nc_r123.log 2>&1
grep -E "Success|Error" /tmp/nc_r123.log
grep -c 'type="traffic_light"' /tmp/r123.net.xml
```

Expected (`netconvert` 1.28.0, default options plus `--keep-edges.in-geo-boundary`): `Success.`, about 35 s, **3220** signals in the network. Of these:

| Source in OSM | Count |
|---|---|
| `highway=traffic_signals` nodes | 1206 (out of 1207 in the extract) |
| `highway=crossing` + `crossing=traffic_signals` nodes (signalised pedestrian crossings) | 2012 |
| unidentified | 2 |

Without the joining options every such node is a separate signal, so 3220 is much larger than the number of signalised intersections. Adding `--junctions.join --tls.join` to the command above reduces the number of signals to **1332** (about 54 s), i.e. by a factor of about 2.4 (on the small test area from section 6: 862 → 360). This is an upper estimate of the number of signalised intersections, because isolated pedestrian crossings remain separate signals. Whether pedestrian crossings should be signals in the model is a team decision (to be recorded in `docs/decisions.md`).

## 7. Checklist

- [ ] `netconvert --version` → 1.28.0
- [ ] `echo "$SUMO_HOME"` → `/usr/share/sumo`
- [ ] SHA-256 of the OSM snapshot matches
- [ ] `osmosis_replication_timestamp` = `2026-10-23T20:20:51Z`
- [ ] `uv sync` completes without errors
- [ ] extract bbox and `traffic_signals` count match the values from section 5
- [ ] the SUMO smoke test finishes by creating `/tmp/test.net.xml`
- [ ] full RING 1–3 network (section 6b): `Success.` and 3220 signals

## 8. Troubleshooting

- **404 on Geofabrik.** The dated file may already have disappeared from the server. Use option B.
- **Checksum mismatch.** Do not use the file. Download it again or use the team copy.
- **`sumo-gui` or `netedit` does not start.** This happens under Wayland. Try an X11 session. The GUI is not needed for zone partitioning.
- **Garbled KBR file names (mojibake).** Do the rename from section 3.
- **`uv` warns that `VIRTUAL_ENV` does not match the project environment.** You have another virtual environment active. `uv` ignores it and uses the repo's `.venv`, so it works correctly. To silence the warning, run `deactivate` before working in the repo.
- **`netconvert` warns about `SUMO_HOME`.** The variable is not set in this shell. Run `source ~/.bashrc` or open a new terminal and repeat the test from section 6.