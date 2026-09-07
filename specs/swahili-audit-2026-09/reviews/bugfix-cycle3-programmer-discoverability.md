# Cycle 3 -- #100/#101 discoverability fixes

## #100: facade-only classes advertised as importable

**Generator** (`src/flextoolsmcp/flexicon_analyzer.py`):
- `_extract_facade_access_paths()` (new, ~1300-1369): AST-scans
  `FLExProject.py` for `@property` bodies matching the memoization idiom
  `self._x = ClassName(self)`, returning `{ClassName: "project.<prop>"}`.
  Verified live against the read-only `flexicon` repo (not edited): 55 of
  118 entities get an `access_path` (e.g. `MSAOperations -> project.MSA`,
  `LexEntryOperations -> project.LexEntry`) -- deliberately unconditional on
  whether the class is *also* top-level importable, since `project.X` is
  always valid once a project exists and it's what flexicon's own docs
  teach. Confirmed the class-is-both case concretely: `LexEntryOperations`
  *is* importable (`from flexicon import LexEntryOperations` works) *and*
  gets `access_path`; only `MSAOperations` is genuinely broken to import.
- `analyze_class()` (1372-1450), `_parse_and_analyze_file`,
  `analyze_python_file`, `analyze_flexicon` (1452-1551): threaded an
  optional `facade_access_paths` param through the call chain; the key is
  **omitted** (not `null`) when there's no facade hit.

**Runtime** (`src/flextoolsmcp/server/handlers/api.py`):
- `_build_entity_import()` (394-420) gained an optional `entity` param;
  when `entity.get("access_path")` is truthy it returns that instead of the
  unconditional import line. All 4 call sites updated to pass `entity`
  (468 `_match_canonical_intents`, 1172 `search_by_capability`, 1371
  `find_examples`, 1697 `resolve_type`).
- `paginate_entity` (674-676): **did need a fix**. It builds its own result
  dict rather than passing the raw entity through, so `access_path` did
  not surface via `get_object_api` at all (summary or full mode) until
  added explicitly. Now added unconditionally before the summary/full
  branch, so both modes carry it.
- Left `paginate_entity`'s own, separate `import_statement` builder
  (`is_operations_class` branch) untouched -- `MSAOperations` isn't in
  `constants.KNOWN_OPERATIONS`, so that branch never fired for it anyway;
  changing it was out of scope and `constants.py` isn't in the edit list.

**Locked-file sites, verified only**: `execution.py:1397/1493` both read
`entity.get("import_statement")` -- confirmed 0/118 entities carry that key
today, so both still emit `null`, unchanged by this fix (pre-existing gap,
not this bug).

## #101: 3 types are not ICmPossibility

#87's `interpretation`/`caveats` field does **not** exist yet (grepped
clean; only unrelated hits in `tool_definitions.py` prose and the
diagnostic `render.py`/`reconstruct.py` modules). Took the read-path
approach in `api.py`, not an extractor change: the premise brief said
`base_classes` already carries this fact, but it's actually empty `[]` for
all 6 relevant entities (interfaces don't populate `base_classes` in this
extractor, only `interfaces` does). The real signal is `entity["interfaces"]`
not containing `"ICmPossibility"` -- already present in the shipped index,
no regeneration needed.

Rejected a structural heuristic ("own `Name` property + no `ICmPossibility`")
-- it matches 76 other liblcm entities never mistaken for possibility lists
(`CmAgent`, `CmFile`, `LangProject`, ...). Used a curated `frozenset`
instead (`NOT_CMPOSSIBILITY_NAME_COLLISION`, api.py:~118-137), matching the
codebase's existing `PROJECT_ACCESSOR_ALIASES` pattern: the 3 named
interfaces plus their concrete-class counterparts (`IMoInflAffixSlot`/
`MoInflAffixSlot`, etc., 6 entries). `paginate_entity` (681-687) sets
`not_cmpossibility_warning` whenever `object_type` is in the set.
**`IMoMorphType`/`MoMorphType` confirmed NOT flagged** (both by direct
`_not_cmpossibility_warning()` call and via `paginate_entity`); a real-index
test (`TestRealIndexPremise`) also confirms `IMoMorphType` genuinely has
`ICmPossibility` in its shipped `interfaces` list, and the 3 target types
genuinely don't.

## Tests / pytest

`tests/test_issue100_access_path.py` (new, 26 tests) and
`tests/test_issue101_not_cmpossibility.py` (new, 17 tests incl. subtests)
cover: facade-path extraction (synthetic fixtures, no dependency on the
external flexicon repo), `analyze_class` annotation + omission,
`_build_entity_import` preference + absent-key/empty-string/no-arg
fallback, `paginate_entity`'s allowlist in both modes, and cross-checks
against the real shipped indexes (skip gracefully if the index files are
absent). `python -m pytest -q`: **1084 passed, 4 skipped, 12 subtests
passed** (baseline 1052 passed/4 skipped + 32 new = consistent; no
failures, no regressions). Did not chase the known
`test_new_exact_file_visible_after_write` flake (didn't fire this run).
`flextoolsmcp.server.APIIndex.load(get_index_dir())` loads cleanly (118
flexicon entities, matching pre-refresh count -- confirms no index was
touched). Note: CLAUDE.md's literal `from src.server import ...`
one-liner doesn't resolve as written (no `src/__init__.py`); the
equivalent `from flextoolsmcp.server import ...` (installed package) works
-- pre-existing doc/packaging mismatch, unrelated to this change.

## Files changed

- `src/flextoolsmcp/flexicon_analyzer.py`
- `src/flextoolsmcp/server/handlers/api.py`
- `src/flextoolsmcp/server/response_keys.py` (added `KEY_ACCESS_PATH`,
  `KEY_NOT_CMPOSSIBILITY_WARNING`)
- `tests/test_issue100_access_path.py` (new)
- `tests/test_issue101_not_cmpossibility.py` (new)

Commit: see `git log -1` on `feat/shared-mode-access` immediately following
this report (message: "fix: recover facade access_path for MSAOperations
and flag non-ICmPossibility types (#100, #101)").

`docs/TOOL-CONTRACT.md` was not edited (locked); no contract-shape change
was required since both new keys are additive and optional.
