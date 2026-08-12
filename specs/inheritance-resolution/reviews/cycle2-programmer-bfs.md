# Cycle 2 — Programmer: BFS reconstruction fix (CP1 T1.3-T1.6)

## What changed

**`src/flextoolsmcp/server/handlers/discovery.py`** (`find_path_bfs`, ~line 77):
the `target == end` branch previously reconstructed by walking `parent`
starting at `node = target`, but `parent[end]` is never recorded (per DEC-1's
guidance, mutating it would corrupt a pre-existing, possibly-shorter parent
entry for a node already in `visited`). Fixed by seeding the path list with
the final edge `{from: current, to: target, via, type}` directly, then
walking `parent` backwards from `current` (the guidance's exact approach).
`get_depth()`'s max_depth semantics are untouched — it never depended on
`parent[end]`.

**`tests/test_issue85_navigation_path.py`**: flipped
`TestFindPathBfsReconstructionBug` → `TestFindPathBfsReconstruction`,
asserting correct direct-edge and two-hop reconstruction instead of pinning
`[]`. Renamed/rewrote `test_known_good_query_still_not_found_due_to_separate_bfs_bug`
→ `test_known_good_query_now_resolves_via_bfs`, asserting `found: true`,
`source: computed`, and the exact 2-hop step sequence (verified directly
against `navigation_graph_liblcm-v11.0.0.json`: `IFsFeatStruc
--FeatureSpecsOC--> IFsFeatureSpecification --FeatureRA--> IFsFeatDefn`).
Kept `test_missing_downcast_edge_still_not_found` (`ILexSense ->
IFsSymFeatVal`) unchanged in outcome, with an added comment explaining this
`found:false` is correct — `MsFeaturesOA` lives on concrete `IMoStemMsa`,
not the base `IMoMorphSynAnalysis` the graph walks; a downcast edge is CP3
(DEC-4), not this bug.

## Test results

Targeted file: 7/7 passed. Full suite: **953 passed, 2 skipped, 0 failed**.

## Surprising

Nothing unexpected — the graph data matched the spec's claimed 2-hop path
exactly on direct inspection, and no other test in the suite depended on the
old (buggy) `[]`-returning behavior.
