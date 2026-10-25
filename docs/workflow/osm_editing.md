# OSM editing and merging workflow (draft, from spike 04s)

Status: **draft**. Tested with simulated JOSM files only (`reports/07_workflow_spike.md`). Not yet tested with real JOSM-saved files; see section 4. The open decision "how OSM is edited (local patches or live OSM)" is not settled by this document; this is the local-patch variant.

Rule: every object has exactly one owner; people edit only what they own. Nothing in the tooling enforces this; it only detects overlaps afterwards.

## 1. Tools

| Tool | Purpose |
|---|---|
| `scripts/prepare_pilot_osm.sh` | creates the base `data/interim/ring1_roads.osm` (one common base for everybody) |
| `src/19_osm_submit.py` | edited `.osm` -> change file `.osc` (bumps versions of changed objects, drops deleted objects, renumbers new ids) |
| `src/18_osm_conflicts.py` | reports objects changed by more than one editor, and new-id collisions |
| `osmium merge-changes`, `apply-changes`, `check-refs` | merge, apply, verify references |

Editor numbers (`--editor-index`, 0-based) are assigned once per person and never reused. Each number owns a block of one trillion ids; ids of new objects become `(index+1) * 10^12 + n`.

## 2. Steps for a cleaner

1. **Get the base.** Everybody uses the same base file (same checksum). Do not re-extract it yourself with other parameters. Keep the base unchanged; work on a copy.
2. **Extract your zone** (ownership polygon) from the base and open it in JOSM:
   ```bash
   osmium extract -p zone_XX.geojson --strategy complete_ways -o zone_XX.osm data/interim/ring1_roads.osm
   ```
   The base for step 5 must be this same zone file, so keep it unchanged and edit a copy `zone_XX_edit.osm`. (The spike used the whole base file; zone extraction was not part of the test, see section 4.)
3. **Edit in JOSM** only objects you own. New objects: draw them normally (JOSM gives them negative ids). Do not upload to openstreetmap.org.
4. **Save** as `zone_XX_edit.osm` (File > Save, not "Upload").
5. **Submit** (derive the change file and renumber ids):
   ```bash
   uv run python src/19_osm_submit.py zone_XX.osm zone_XX_edit.osm submissions/XX.osc --editor-index N
   ```
   Check the printed line `prepare: {...}`: `bumped` + `new` + `deleted_dropped` should match what you did.
6. **Send** `XX.osc` (small file) to the person who merges. Do not send the full `.osm`.

## 3. Steps for the person who merges

```bash
uv run python src/18_osm_conflicts.py A=submissions/A.osc B=submissions/B.osc ...   # exit 1 = stop, resolve first
osmium merge-changes submissions/*.osc -o merged.osc --overwrite
osmium apply-changes data/interim/ring1_roads.osm merged.osc -o merged.osm --overwrite
osmium check-refs -r merged.osm        # compare with the same command on the base: no new "missing"
netconvert --osm-files merged.osm -o merged.net.xml ...                          # options as in docs/SETUP.md 6b
```

Changes from several zones are applied to the one common base; if the change files come from zone extracts, the objects are looked up by id, so they should apply to the full base as well (untested: the spike derived and applied against the same file; see section 4, item 11).

## 4. To test with real JOSM-saved files (next step)

1. How JOSM writes a **new** object: negative id, `action="modify"`, no `version`? (The spike assumed this.) Does `19_osm_submit.py` count it under `new`?
2. How JOSM writes **deleted** objects: kept in the file with `action="delete"` and the old version, or omitted? Plain `osmium derive-changes` ignores `action="delete"` objects; `19_osm_submit.py` drops them. Check that a deleted way and a deleted node give `<delete>` in the `.osc`. Check what happens to nodes that stay after a way is deleted.
3. How JOSM writes **modified** objects: `version` unchanged and `action="modify"`? Does it write extra attributes (`upload="false"`, `timestamp`, `changeset`, `user`) that break `osmium sort` or `derive-changes`?
4. Does JOSM keep the **negative ids across save/reopen** (they may be renumbered on load)? If an editor opens a saved file, edits more and saves again, are new ids stable? Matters for resubmitting.
5. **Relations**: new/changed turn restrictions and route relations (members with new ids). The spike did not edit relations; `renumber` handles `member ref`, but this is untested.
6. **Extract round trip**: the zone file loaded in JOSM, saved; are untouched objects still identical (same version, same tags)? Any object that JOSM rewrites without a real change would show as `bumped` falsely; the signature check should prevent that, verify it.
7. **Download area / incomplete objects**: does JOSM mark objects at the file boundary as incomplete, and do they appear in the saved file?
8. **Merging**: with two real zone files, are nodes on the border shared by both zones? Who owns them? Is a node moved by one editor and used by a way of the other detected? (The detector does not see this case.)
9. **Large files**: time of `19_osm_submit.py` on a full zone (the spike took about 2 s on 13 MB).
10. Whether JOSM validator warnings (duplicate nodes, crossing ways) appear after merge, and whether a final JOSM check of `merged.osm` should be a required step.
11. **Zone base vs full base**: derive against the zone extract, apply to the full `ring1_roads.osm`. Check that versions and results are identical to deriving against the full base.

## 5. Known limitations

- Plain `osmium derive-changes` silently ignores edits that keep the `version` (all JOSM edits), `action="delete"` objects, and duplicates of negative ids across editors. Use `19_osm_submit.py` and `18_osm_conflicts.py`; never run `derive-changes` by hand.
- The detector sees only identical object ids. Ownership violations that touch different objects are not detected.
- Edits of `lanes=` have no effect on ways that have `lanes:forward` / `lanes:backward`; change those too.
- Netconvert names edges after way ids; new ways get ids `(index+1) * 10^12 + n`, so the edges are `10000...03` and `-10000...03` (reverse). Keep this in mind when looking for new roads in the network.
