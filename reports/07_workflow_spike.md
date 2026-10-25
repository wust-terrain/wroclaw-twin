# Report 07: OSM editing and merging workflow spike (task 04s)

Test only. Base: `data/interim/ring1_roads.osm` (57900 nodes, 17286 ways). Work directory: `data/interim/spike/`. Produced by `src/17_workflow_spike.py` (config `config/17_workflow_spike.yaml`); inputs verified with `scripts/verify_inputs.sh`; `data/raw/` not touched; nothing committed. Tools: osmium 1.16.0, netconvert 1.28.0.

**Result: 17 of 17 checks as expected.**

## 1. Simulated editors

Editors are simulated by `src/17_workflow_spike.py` (not JOSM). It writes JOSM-style files: changed objects keep their `version` and get `action="modify"`; new objects have negative ids and `action="modify"`; both editors deliberately use the ids -1, -2 (nodes) and -3 (way). The new way is attached to an existing, unchanged node of the editor's own area.

| Editor | Type | Id | Edit |
|---|---|---|---|
| A | way | 190721402 | tags {'lanes': '3'} |
| A | way | 28458068 | tags {'maxspeed': '30'} |
| A | way | 187980719 | tags {'maxspeed': '70', 'lanes': '2'} |
| A | node | 3771392250 | moved 2.0 m north |
| A | node | -1 | new |
| A | node | -2 | new |
| A | way | -3 | new, nodes 2013583179,-1,-2 |
| B | way | 358949459 | tags {'maxspeed': '20'} |
| B | way | 546186130 | tags {'lanes': '4'} |
| B | way | 16237819 | tags {'maxspeed': '60', 'lanes': '1'} |
| B | node | -1 | new |
| B | node | -2 | new |
| B | way | -3 | new, nodes 167131069,-1,-2 |

Extra way for the conflict test (changed by both editors): `255898440` (A: maxspeed=35, B: maxspeed=45; values differ from the base, a no-op edit is not a change).

## 2. What `osmium derive-changes` does

Pitfalls demonstrated with plain osmium (these are expected to fail; they are why the helper scripts exist):

| Pitfall | Correct result | Plain osmium result |
|---|---|---|
| derive-changes on raw editor A file | 7 objects (3 ways + 1 node moved + 2 new nodes + 1 new way) | 3 objects (modify: 2 node+1 way) |
| deletions (1 `action=delete`, 1 omitted) | 2 deletes | 1 delete |
| merge of A and B without renumbering: nodes / ways added | 4 / 2 | 2 / 1 |

### 2.1 Modified objects are silently lost (important)

`osmium sort` + `osmium derive-changes BASE EDITED` on the raw editor-A file gives **modify: 2 node+1 way**: only the new objects. The three tag edits and the moved node are missing, because `derive-changes` compares `(type, id, version)` and JOSM does not change `version` of edited objects (the server does that on upload). `osmium sort` also drops the `action` attribute, so it cannot be used to tell the objects apart afterwards. No warning is printed, exit code 0.

Fix (`src/19_osm_submit.py`, function `prepare`): compare each existing object with the base (tags, coordinates, node list, members) and set `version = base version + 1` on the ones that differ. This does not rely on `action`, so it also works for files that were not written by JOSM.

### 2.2 Deletions

Test file: one way marked `action="delete"` (what JOSM writes, to be confirmed, see section 6) and one way simply missing. Plain `osmium derive-changes`: **1 delete** (only the missing way; the `action="delete"` way is treated as unchanged and stays in the result). With `19_osm_submit.py` (drops `action="delete"` objects before deriving): **2 deletes**. Deleting a way does not delete its nodes; they stay as orphans unless the editor deletes them too (JOSM normally does).

### 2.3 Negative ids

`derive-changes` accepts negative ids and passes them through unchanged, as `<modify>` (never `<create>`). Both editors' files therefore contain node -1, node -2, way -3. `osmium merge-changes` accepts this without any message and writes both versions (`modify: 5 node+8 way`). `osmium apply-changes` then keeps the last one: **A's new nodes -1, -2 and way -3 are silently replaced by B's** (nodes +2 and ways +1 instead of +4 and +2). No error, no warning: A's new road is simply gone.

`src/18_osm_conflicts.py` detects this ("negative-id collision"):

```
COLLISION: negative id used by more than one editor (renumber first): node -2 <- A, B
COLLISION: negative id used by more than one editor (renumber first): node -1 <- A, B
COLLISION: negative id used by more than one editor (renumber first): way -3 <- A, B
conflicts: 0, negative-id collisions: 3
```

### 2.4 Renumbering step (implemented and tested)

`19_osm_submit.py` maps every negative id `n` (object ids, `nd ref`, `member ref`) of editor `i` (0-based) to **`(i+1) * 1,000,000,000,000 - n`**, so A's -1,-2,-3 become 1000000000001,1000000000002,1000000000003 and B's become 2000000000001,2000000000002,2000000000003. The block size is above the highest real id in the snapshot (nodes 14,313,717,029, ways 1,571,183,111, relations 21,771,971), so the new ids cannot collide with existing ones.

Why positive and not "shift further negative": the negative shift also works in osmium, but `netconvert` names the edges after the way id and uses a `-` prefix for the reverse direction. A way with id -1000000000003 gives the edges `--1000000000003`, `--2000000000003`, `-1000000000003`, `-2000000000003`, i.e. the reverse edge starts with `--` and the forward edge looks like the reverse edge of way 1000000000003. Positive ids give clean names (`-1000000000003`, `1000000000003`).

## 3. Merge, apply, conflict detection

```bash
BASE=data/interim/ring1_roads.osm; W=data/interim/spike
uv run python src/19_osm_submit.py $BASE $W/editedA.osm $W/A.osc --editor-index 0
uv run python src/19_osm_submit.py $BASE $W/editedB.osm $W/B.osc --editor-index 1
uv run python src/18_osm_conflicts.py A=$W/A.osc B=$W/B.osc          # exit 1 on conflict/collision
osmium merge-changes $W/A.osc $W/B.osc -o $W/AB.osc --overwrite
osmium apply-changes $BASE $W/AB.osc -o $W/merged.osm --overwrite
osmium check-refs -r $W/merged.osm
```

Disjoint edits: detector `conflicts: 0, negative-id collisions: 0`; merged file has +4 nodes, +2 ways; `osmium check-refs` output equals the base (the 4 "ways in relations missing" are already in the base, they come from the polygon cut).

Same way changed by A and B: detector output `CONFLICT: object changed by more than one editor: way 255898440 <- A, B` and exit code 1. Without the detector `osmium merge-changes`/`apply-changes` raise no error: the result silently has maxspeed `45` on way 255898440 (B wins; the change files must be given to `merge-changes` in a fixed order, the last one wins).

## 4. netconvert

Options as in `docs/SETUP.md` 6b (defaults + `--keep-edges.in-geo-boundary`), bbox `17.03,51.1,17.045,51.11`, on the base and on `merged.osm`. Both: Success.

| Editor | Way | Edit | Base (forward edges) | Merged (forward edges) | Check |
|---|---|---|---|---|---|
| A | 190721402 | lanes=3 maxspeed=None | 2 lanes, [13.89] m/s | 3 lanes, [13.89] m/s | OK |
| A | 28458068 | lanes=None maxspeed=30 | 2 lanes, [13.89] m/s | 2 lanes, [8.33] m/s | OK |
| A | 187980719 | lanes=2 maxspeed=70 | 2 lanes, [13.89] m/s | 2 lanes, [19.44] m/s | OK |
| B | 358949459 | lanes=None maxspeed=20 | 1 lanes, [13.89] m/s | 1 lanes, [5.56] m/s | OK |
| B | 546186130 | lanes=4 maxspeed=None | 2 lanes, [13.89] m/s | 4 lanes, [13.89] m/s | OK |
| B | 16237819 | lanes=1 maxspeed=60 | 2 lanes, [13.89] m/s | 1 lanes, [16.67] m/s | OK |

New ways (each has a forward and a reverse edge, because they are two-way by default):

| Editor | Edges in merged network | Lanes | Speed [m/s] |
|---|---|---|---|
| A | -1000000000003, 1000000000003 | 1 | [8.33] |
| B | -2000000000003, 2000000000003 | 1 | [8.33] |

Moved node 3771392250 (isolated build with only that change): per-edge max shape shift of way 190721402: `190721402#0` 2.00 m, `190721402#1` 1.90 m, `190721402#2` 0.00 m, `190721402#3` 0.00 m. Shifts below 2 m on a split edge come from the edge ending at a junction near the moved point; at least one edge shows the full 2.00 m. In the combined build the way also got a lane change, which shifts the shape for other reasons, so the move is measured in isolation.

## 5. Control table

| Check | Expected | Got | Status |
|---|---|---|---|
| tool derive, editor A | modify: 3 node+4 way | modify: 3 node+4 way | OK |
| tool derive, editor B | modify: 2 node+4 way | modify: 2 node+4 way | OK |
| deletions, 19_osm_submit.py | 2 deletes | 2 deletes | OK |
| merged with renumbering: nodes / ways added | 4 / 2 | 4 / 2 | OK |
| check-refs merged vs base | identical | identical | OK |
| conflict detector, disjoint edits (exit code) | 0 | 0 | OK |
| conflict detector, same way changed by A and B (exit code) | 1 | 1 | OK |
| netconvert base / merged / merged (negative-shift variant) | Success / Success / Success | Success / Success / Success | OK |
| net: way 190721402 (editor A) | 3 lanes / same m/s | 3 / [13.89] | OK |
| net: way 28458068 (editor A) | same lanes / 8.33 m/s | 2 / [8.33] | OK |
| net: way 187980719 (editor A) | 2 lanes / 19.44 m/s | 2 / [19.44] | OK |
| net: way 358949459 (editor B) | same lanes / 5.56 m/s | 1 / [5.56] | OK |
| net: way 546186130 (editor B) | 4 lanes / same m/s | 4 / [13.89] | OK |
| net: way 16237819 (editor B) | 1 lanes / 16.67 m/s | 1 / [16.67] | OK |
| net: new way of editor A present | 2 edges | 2 edges (-1000000000003, 1000000000003) | OK |
| net: new way of editor B present | 2 edges | 2 edges (-2000000000003, 2000000000003) | OK |
| net: node 3771392250 moved 2 m (max shape shift, isolated build) | 2.0 m | 2.00 m | OK |

## 6. Limitations

- This is a simulation of JOSM files, not real JOSM files. How JOSM writes deletions, new relations, `action` values and `version` on new objects is assumed, not verified (list in `docs/workflow/osm_editing.md`).
- Modified objects are lost by plain `osmium derive-changes`; `19_osm_submit.py` is required, not optional.
- Collisions of negative ids and edits of the same object by two editors are **not** detected by osmium; they are detected only by `18_osm_conflicts.py`. It checks the same object id, not semantic conflicts (e.g. A deletes a node that B's new way uses; `osmium check-refs` on the merged file catches missing references, but only after the merge).
- The ownership rule (editors edit only what they own) is not enforced by any tool here; the detector only catches violations that happen to touch the same object. A node shared by two zones (moved by A, used by a way owned by B) is not a conflict for the tools and not visible to B.
- New nodes connected to existing nodes at the border between two owners: the anchor node is unchanged, so no conflict is raised, but two editors can create overlapping or duplicate roads without any message.
- `apply-changes` applies the files in the order given; for non-conflicting edits the order does not matter.
- Edits of `lanes=` have no effect on ways that carry `lanes:forward` / `lanes:backward` (netconvert uses those; seen in an earlier run on a tertiary way). Cleaners must change the detailed tags too.
- Version bump is `base + 1` for every editor, so two editors changing the same object would both produce version `base+1`; this is exactly the case the detector reports.
- Timing: each `19_osm_submit.py` run on the 13 MB base takes about 2 s; netconvert on the small bbox a few seconds.

## 7. Recommended workflow

See `docs/workflow/osm_editing.md`. In short: extract the zone from the base, edit in JOSM, save, `19_osm_submit.py` (version bump, deletions, renumbering, derive), run `18_osm_conflicts.py` on all submitted files, merge with `osmium merge-changes`, apply, run `osmium check-refs`, build with netconvert.
