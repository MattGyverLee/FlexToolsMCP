# Cycle 2 Verification — independent check

## 1. Full suite — PASS
`python -m pytest -q`: **977 passed, 2 skipped, 0 failed** (re-run twice,
including after a concurrent crew's commit landed mid-verification).
Matches 953-baseline + 24 new. No failures.

## 2. CP1 2-hop path via server.call_tool — PASS
Initialized `APIIndex`/`set_api_index`, called `server.call_tool` (fields
are `from_object`/`to_object`). Result: `found: true`, `source: computed`,
2 steps: `IFsFeatStruc --FeatureSpecsOC--> IFsFeatureSpecification
--FeatureRA--> IFsFeatDefn`. Matches report exactly.

## 3. ILexSense -> IFsSymFeatVal — PASS
Returns `found: false`. Test docstring explicitly attributes this to the
missing downcast edge (`MsFeaturesOA` lives on concrete `IMoStemMsa`, not
base `IMoMorphSynAnalysis`), pinned as CP3/DEC-4 scope, not the D2 bug.

## 4. IFsClosedValue FeatureRA / 2->31 — PASS
`get_object_api("IFsClosedValue")`: `total_properties: 2`,
`total_properties_including_inherited: 31`, `FeatureRA` present with
`inherited_from: "IFsFeatureSpecification"`.

## 5. total_properties byte-identical — PASS
Built a `git worktree` at HEAD (pre-cycle-2), diffed output for
IFsClosedValue/ILexEntry/ICmObject: `total_properties`/`total_methods`
identical (2/2, 53/53, 25/25). `total_properties_including_inherited`
present and larger only in current output.

## 6. Pagination has_more/next_offset — PASS, deviation is correct
Paged IFsClosedValue (31 props/14 methods, limit=5): all 31 properties
reached, 0 duplicates, no early stop. Tested widened OR-logic against all
3 scenarios: (a) `ICmObjectInternal`, 64 methods vs 27 properties, merged
— full coverage both dimensions, exact counts; (b) `IFsClosedValue`,
properties > methods — as above; (c) non-interface `LexSense` (79 own
props, unmerged) — total == total_including_inherited, full coverage,
confirming non-merged entities see no behavior change.

## 7. Cross-tool consistency invariant — PASS
`resolve_property(Feature/FeatureRA, IFsClosedValue)` → `found: true`,
`inherited_from: IFsFeatureSpecification`, matching `get_object_api`.
`validators._interface_member_names` includes `FeatureRA` for
`IFsClosedValue` and `ConfidenceRA` for `IChkTerm` (2nd sample pair).

## 8. Lane discipline — PASS
`git diff` shows `api.py`/`discovery.py` (+ new test files) as the only
inheritance-resolution edits. `validators.py`, `CHANGELOG.md`,
`docs/TOOL-CONTRACT.md` diffs contain **zero** matches for
inherit/#85/#86/navigation_path/find_path_bfs (grep-verified) — content
is entirely the concurrent workspace_notice/issue-#84 crews' work (one
committed as `01c1553` mid-verification, unrelated to this cycle). `git
stash list` unchanged (2 pre-existing entries); `git ls-files -u` empty.

**Overall: 8/8 PASS. No fixes made; no destructive git commands run.**
