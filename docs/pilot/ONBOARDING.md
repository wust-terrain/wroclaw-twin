# Pilot onboarding (raters R1 and R2)

R1 edits zone 3 (visitor in zone 4), R2 edits zone 4 (visitor in zone 3). Nothing here needs SUMO or `netconvert`.

**Supported systems:** Ubuntu 24.04, natively or in WSL2 or a VM (JOSM needs a desktop session; WSLg works). Other systems are untested.
`osmium` must be exactly **1.16.0** and Java **21**. If `apt` offers another version, stop and ask the project owner.

**Time:** setup takes 30-40 minutes (mostly downloads). It is outside the 5 h pilot budget; do not count it in any record.

## 1. Prerequisites (one-off)

| # | Step | Time |
|---|---|---|
| 1 | `sudo apt-get install git unzip python3` (3.12) | 2 min |
| 2 | uv (tested: 0.11.2): https://docs.astral.sh/uv/ (see also `docs/SETUP.md`) | 3 min |
| 3 | `sudo apt-get install osmium-tool`; `osmium --version` must show 1.16.0 | 2 min |
| 4 | `sudo apt-get install openjdk-21-jre`; `java -version` must show 21 | 5 min |

## 2. Repository and Python environment (about 5 min)

```
git clone <repository URL> wroclaw-twin && cd wroclaw-twin
git fetch --tags && git checkout "$(grep -v '^#' docs/pilot/pilot_tag.txt | head -1)"
uv sync --only-group pilot      # minimal environment (pyyaml, pyproj, shapely); no pymetis, geopandas, ...
```

The tag is named in `docs/pilot/pilot_tag.txt`; the checkout is a detached HEAD, which is fine. Update **only when told**, with the same two commands
(`git fetch --tags && git checkout <tag>`; read the tag from the file after the fetch). Do not run a plain `uv sync`.
`uv sync --only-group pilot` is the command for uv 0.11.2: it installs the `pilot` group of `pyproject.toml` without the project dependencies.

## 3. Handoff data (about 1 min)

You receive `handoff_R1.zip` or `handoff_R2.zip` (zone packages, ownership tables, your kit; not in git). Unzip it in the **repository root**, paths are preserved:

```
unzip -o ~/Downloads/handoff_R1.zip      # from the repository root
sha256sum -c SHA256SUMS                  # every line must say OK
```

## 4. Check (about 1 min)

```
scripts/check_setup.sh R1                # or R2
```

It prints a PASS/FAIL/WARN table and ends with `ALL CHECKS PASSED`. The last row is a dry run of `scripts/submit_edits.sh` on an unchanged copy of your
zone package (expected: `changed objects: 0`). Fix every FAIL before you start (a WARN for a missing `pilot_tag.txt` is not yours to fix; tell the owner).

## 5. JOSM (about 5 min)

Take the jar `josm-tested.jar` (JOSM 19613) from the handoff channel, **not from the internet**, and save it as `~/tools/josm-tested.jar` (`mkdir -p ~/tools`).
`check_setup.sh` compares its sha256 with `docs/pilot/josm.sha256`; other JOSM versions were not tested. Another path: `JOSM_JAR=/path/to.jar`.
`scripts/josm_pilot.sh` runs `java --add-exports=java.base/sun.security.action=ALL-UNNAMED --add-exports=java.desktop/com.sun.imageio.plugins.jpeg=ALL-UNNAMED --add-exports=java.desktop/com.sun.imageio.spi=ALL-UNNAMED -jar ~/tools/josm-tested.jar --offline=osm_api <files>`.
Always start JOSM through this script (no downloads, no uploads).
Remote control (Edit > Preferences > Remote Control): enable it, tick **only** "Change the viewport" and "Read protocol version".

## 6. First session

Follow `docs/pilot/protocol.md` section 3 (session routine: start JOSM only with the script, copy the package once to `zone_<N>_edit.osm`, never use Update data)
and section 10 (recording in the kit and submission with `scripts/submit_edits.sh <zone> zone_<N>_edit.osm`). Start with the warm-up units of your kit.
Everything you create (`zone_<N>_edit*.osm`, `submissions/`) stays untracked; do not commit or push.

## 7. What to send after each session

To: `<TODO: channel>`. Files: `submissions/zone_<N>/<date>/zone_<N>.osc`, `zone_<N>.osc.meta.json`, and your record-sheet `units_<R>.xlsx`.
Do not send the `.osm` files.
