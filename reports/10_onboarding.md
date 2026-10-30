# Task 02d: pilot onboarding report (updated with the follow-up)

uv 0.11.2. Commands: `uv sync --only-group pilot` (pyyaml, pyproj, shapely + numpy, certifi); no environment variable. The scripts call `uv run --no-sync`.
Default `uv sync` unchanged (18 more packages incl. pymetis, geopandas); `uv lock --check` ok.

Follow-up changes: `submit_edits.sh` and `check_setup.sh` use `uv run --no-sync` (the `UV_NO_SYNC` instruction is gone from ONBOARDING);
the branch check is now a tag check (`docs/pilot/pilot_tag.txt`: PASS if the tag is HEAD or an ancestor of HEAD, FAIL if the tag is missing or not contained, WARN if the file is missing);
the JOSM jar is pinned by `docs/pilot/josm.sha256` (JOSM 19613, sha256 7bba9b5d...9077) and copied by `make_handoff.sh` to `handoff/josm-tested.jar`;
`scripts/selftest_handoff.sh <tag-or-commit> <R1|R2>` added; ONBOARDING extended (systems, results channel `<TODO: channel>`, setup time outside the 5 h budget).

## Self-test: `env -u UV_NO_SYNC scripts/selftest_handoff.sh <commit> R1|R2` (plain clone, no working-tree overlay, unzip, `uv sync --only-group pilot`, check_setup.sh incl. dry run)

| rater | commit | result |
|---|---|---|
| R1 | b256f9d (snapshot of the working tree, see below) | PASS: 27 PASS, 1 WARN (pilot_tag.txt missing, expected), 0 FAIL; dry run `changed objects: 0`, exit 0 |
| R2 | b256f9d | PASS: 27 PASS, 1 WARN (same), 0 FAIL; dry run ok |

- The follow-up is not committed (instruction), so `selftest_handoff.sh HEAD R1` correctly FAILs ("scripts/check_setup.sh is not in the commit"). To run the test anyway I built a dangling commit object
  (HEAD plus the working tree, temporary index, temporary ref deleted afterwards; no branch moved, nothing committed). It also contains the unrelated uncommitted change in `docs/decisions.md`.
  After you commit, re-run: `scripts/selftest_handoff.sh <tag> R1` and `R2`.
- Checked by hand in a scratch clone: pilot tag PASS (tag is an ancestor), FAIL for a tag that does not exist, FAIL for a tag that HEAD does not contain; JOSM pin FAIL when `josm.sha256` differs.
- **Not done: a network-clean test** (empty uv cache, no `UV_OFFLINE`, fresh machine or VM, JOSM jar from the handoff). This remains to be done by the project owner. All runs here used the local uv cache and `UV_OFFLINE=1`.

## Zips (`scripts/make_handoff.sh R1|R2`, built twice again after the follow-up: SHA256SUMS identical for R1 and R2; content list unchanged. The JOSM jar is not in the zip, it is `handoff/josm-tested.jar`)

### handoff_R1.zip: 3254385 bytes

| file | sha256 |
|---|---|
| `HANDOFF_README.txt` | 926b74a5895431e1c0c2efdff3005c12281fe16b803ee4128ed6c6fa84dfea0f |
| `data/derived/pilot_kit/R1/README.md` | 4ab75bb145c936b2104e65c28bac1fd6cd3ea427753a186e79ed08f4120efeb7 |
| `data/derived/pilot_kit/R1/pilot_areas_zone_3.osm` | 21b71eec569b7bfde99ff04a6cb0aa60d7d0af11bd2af5596a9a93fdf70dad6b |
| `data/derived/pilot_kit/R1/pilot_areas_zone_4.osm` | 4bf5c72ea5c257f50e0666be0fa6d90f8408e10e7e2cbe3013386bbbc520a128 |
| `data/derived/pilot_kit/R1/units_R1.xlsx` | cf01dcbc3ab9819fd984a3e1c862edb5779f55f94d5a2919b9913f79472c0462 |
| `data/derived/zones_v02/ownership_nodes.csv` | 751af5fc263aff327db3768e99e354b2c7f050a7df75770b8b964636cc4d819d |
| `data/derived/zones_v02/ownership_relations.csv` | 8c69e5e587e88c0e8952ae5601847f3e97a652f1b7d63c01314695f00ab8b230 |
| `data/derived/zones_v02/ownership_ways.csv` | 4a27743850fd3dee261e73cc0e7b75c1bb4bcbf1e4090eb8a435ea5f598faecf |
| `data/derived/zones_v02/shared_editable_nodes.csv` | d5b5935e4211d8cce774f0412529b672a10abe3514ddfffae7e4f961e390126b |
| `data/derived/zones_v02/zone_3/zone_3.geojson` | 779cc54f9d18601f710c56a7923fbbc699cccbc89f277714cd096ca75a834f44 |
| `data/derived/zones_v02/zone_3/zone_3.json` | cb0b61d208074186664eaf3a9b41fe57692b7b29401b2092c1df32f124fc2b6d |
| `data/derived/zones_v02/zone_3/zone_3.osm` | 513d17da3fe612b492b0f380c4c8d9587723c2eeeaa98b787edfb96f81b14168 |
| `data/derived/zones_v02/zone_3/zone_3_bridge_ways.csv` | c2b504561de619d6f1528aeecbf4363671871a2de38a000acfa0667a11a15d0f |
| `data/derived/zones_v02/zone_3/zone_3_bridges.csv` | 3fa7eeb522243c1bd9148f3c5b4823f5ca2755478ea16dbc9908dfb17020bd5b |
| `data/derived/zones_v02/zone_3/zone_3_reference.osm` | 9d98eabc7850ec399afb4cde46d510870c609969cb48110805772e5417030b3f |
| `data/derived/zones_v02/zone_3/zone_3_seams.csv` | 1396df410a17cf12de6be7915bfae8012ee4b12dd2e7c31780ebe242b77e7667 |
| `data/derived/zones_v02/zone_3/zone_3_units.csv` | 9dc7580e516faf11c514b9ab2ec0d5266634d9ee8b63ddf04940e876e247c804 |
| `data/derived/zones_v02/zone_4/zone_4.geojson` | 3f66b2236684aaf5c589b72a4b7fb8cb0e04f09743eb29d7b83d913700fc67c4 |
| `data/derived/zones_v02/zone_4/zone_4.json` | 7fccc4517e959de52af2c8655026153cf97192afd0679f188c5dc19046950f8b |
| `data/derived/zones_v02/zone_4/zone_4.osm` | ec2e03f55f0f1b9f670d8aa66910d34a195414b9047c4cc64768ed5d72ad2e1e |
| `data/derived/zones_v02/zone_4/zone_4_reference.osm` | 8a2d3d23b9a0709eebd8cdd04b9c45e62e2080d8f2d077b495f8d6c4f64564c4 |
| `data/interim/ring1_roads.osm` | 220a82a3ee432eb002a17eaf53c206684e603e2ea05f259fe70e57e8bfd0df11 |

### handoff_R2.zip: 3251687 bytes

| file | sha256 |
|---|---|
| `HANDOFF_README.txt` | 2876588e97cc4bf4530794c31b18c033f21352794237b17b49b90e6fdf11da2d |
| `data/derived/pilot_kit/R2/README.md` | 8eef97e6da8284d7d9b26136143b73774be4b4bc25637014029d134d47f64007 |
| `data/derived/pilot_kit/R2/pilot_areas_zone_3.osm` | 21b71eec569b7bfde99ff04a6cb0aa60d7d0af11bd2af5596a9a93fdf70dad6b |
| `data/derived/pilot_kit/R2/pilot_areas_zone_4.osm` | 4bf5c72ea5c257f50e0666be0fa6d90f8408e10e7e2cbe3013386bbbc520a128 |
| `data/derived/pilot_kit/R2/units_R2.xlsx` | 9aa73d0b53ca4aa04bbc982a7029ec59ec80416be82ae4838b68eae5457a633b |
| `data/derived/zones_v02/ownership_nodes.csv` | 751af5fc263aff327db3768e99e354b2c7f050a7df75770b8b964636cc4d819d |
| `data/derived/zones_v02/ownership_relations.csv` | 8c69e5e587e88c0e8952ae5601847f3e97a652f1b7d63c01314695f00ab8b230 |
| `data/derived/zones_v02/ownership_ways.csv` | 4a27743850fd3dee261e73cc0e7b75c1bb4bcbf1e4090eb8a435ea5f598faecf |
| `data/derived/zones_v02/shared_editable_nodes.csv` | d5b5935e4211d8cce774f0412529b672a10abe3514ddfffae7e4f961e390126b |
| `data/derived/zones_v02/zone_3/zone_3.geojson` | 779cc54f9d18601f710c56a7923fbbc699cccbc89f277714cd096ca75a834f44 |
| `data/derived/zones_v02/zone_3/zone_3.json` | cb0b61d208074186664eaf3a9b41fe57692b7b29401b2092c1df32f124fc2b6d |
| `data/derived/zones_v02/zone_3/zone_3.osm` | 513d17da3fe612b492b0f380c4c8d9587723c2eeeaa98b787edfb96f81b14168 |
| `data/derived/zones_v02/zone_3/zone_3_reference.osm` | 9d98eabc7850ec399afb4cde46d510870c609969cb48110805772e5417030b3f |
| `data/derived/zones_v02/zone_4/zone_4.geojson` | 3f66b2236684aaf5c589b72a4b7fb8cb0e04f09743eb29d7b83d913700fc67c4 |
| `data/derived/zones_v02/zone_4/zone_4.json` | 7fccc4517e959de52af2c8655026153cf97192afd0679f188c5dc19046950f8b |
| `data/derived/zones_v02/zone_4/zone_4.osm` | ec2e03f55f0f1b9f670d8aa66910d34a195414b9047c4cc64768ed5d72ad2e1e |
| `data/derived/zones_v02/zone_4/zone_4_bridge_ways.csv` | 106b95c828cbb2de818a3aac641f86bafff674f0933fd87f3f80c67b0631de07 |
| `data/derived/zones_v02/zone_4/zone_4_bridges.csv` | 838bdebdcf8057f31b4b4f63994db756a093bbb38c4513d66e7bd3b2e7f9355c |
| `data/derived/zones_v02/zone_4/zone_4_reference.osm` | 8a2d3d23b9a0709eebd8cdd04b9c45e62e2080d8f2d077b495f8d6c4f64564c4 |
| `data/derived/zones_v02/zone_4/zone_4_seams.csv` | ccf5c3e91e946b01d570225ca15e1e808d8cd3db9228005e501c76de43059a41 |
| `data/derived/zones_v02/zone_4/zone_4_units.csv` | b5608322b4a6f6a51eaaba9275d4999e4f378ee5bdca7011365c25451999d913 |
| `data/interim/ring1_roads.osm` | 220a82a3ee432eb002a17eaf53c206684e603e2ea05f259fe70e57e8bfd0df11 |

Files found by tracing `submit_edits.sh` (strace): own package + json + reference + geojson, ownership_{ways,nodes,relations}.csv, shared_editable_nodes.csv,
and `data/interim/ring1_roads.osm` (15 MB, `full_base` in config/21_ownership_check.yaml; not in git). `pilot_zones.gpkg` is not needed by any script.
