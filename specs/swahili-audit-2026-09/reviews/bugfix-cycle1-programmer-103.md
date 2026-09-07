# Issue #103 (hvo instability) -- programmer report, cycle 1

## `Object()` GUID claim -- confirmed
Read `flexicon/flexicon/code/FLExProject.py:3212-3226` directly. `Object(hvoOrGuid)`
converts a `str` via `System.Guid(hvoOrGuid)` then calls
`self.project.ServiceLocator.GetObject(hvoOrGuid)` for `(System.Guid, int)`. The
round-trip already ships; no flexicon change needed.

## Files changed
- `src/flextoolsmcp/server/validators.py`: new `_HVO_PARAM_SUFFIX`,
  `_method_param_names`, `_is_int_literal` (typed `TypeGuard[ast.Constant]`),
  `detect_hvo_literal_args` -- inserted after `_find_cast_alias_property_writes`,
  lines 2273-2454 (182 new lines). Casting-gate severity logic at
  validators.py:3439/3598/3710/3731 is unmoved content, shifted +182 lines by
  this insertion only -- rebase math: subtract 182 to get pre-#103 line numbers.
- `src/flextoolsmcp/server/handlers/execution.py`: import `detect_hvo_literal_args`
  (2 import blocks, lines 74 and 89). New hard-block gate in
  `handle_run_module`, lines 2771-2829 (59 lines), inserted immediately after the
  existing `unprotected_writes` gate and before the casting-issue block --
  `casting_check["severity"] = "error"` shifted from ~2793 to 2852 (content
  unchanged). New read-only advisory block, lines 3426-3442 (17 lines), inserted
  after the `getall_check` warning in the "Build warnings" section.
- `src/flextoolsmcp/server/handlers/admin.py`: new `hvo_stability` block in
  `RUNTIME_PRIMER`, lines 214-249, quoting `DomainDataByFlid.cs:40-44` verbatim
  and documenting the `project.Object(guid_str)` round trip.
- `src/flextoolsmcp/server/tool_definitions.py`: new "HVO WARNING" paragraph in
  the `flextools_run_module` description (lines ~257-267).
- `docs/TOOL-CONTRACT.md`: added `hvo_literal_write_risk` row to the error-code
  table; bumped "17 codes" -> "18 codes".
- `tests/test_issue103_hvo_stability.py` (new): 13 direct-validator cases +
  5 gate-wiring cases (18 total), matching `test_nested_uow_gate.py` conventions
  (`_stub_env`/monkeypatch harness, no live-FLEx marker needed -- pure AST/gate
  logic, no FieldWorks dependency).

## Read-only vs write-enabled decision
Read-only: WARNING only, appended to the existing `warnings` list (same
non-blocking pattern as the `getall_check` advisory) -- a stray literal in
exploratory code cannot corrupt anything.
Write-enabled: HARD BLOCK (`error_code="hvo_literal_write_risk"`), reusing the
existing gate architecture (same shape as `unprotected_writes` /
`nested_unit_of_work`: log, `error_response(...)`, `_attach_assistance_if_loop`).
Justification: a wrong-target write is exactly the silent-corruption scenario
#103 documents -- the reporter's own near-miss was a write script using stale
hvo literals as targets, saved only by an independent lexeme/gloss re-check.
This preflight already hard-blocks other write-shaped risk unconditionally
(unprotected mutations, nested UnitOfWork); a warning-only response to a write
already in flight through a stale hvo would be the one gate in the ladder that
lets exactly this failure mode through. Detection is a bare-integer-literal AST
check only -- a `.Hvo` variable read this run is never flagged, so no
legitimate guarded write is blocked.

## Worked-example audit (issue #103 ask 4)
- `src/flextoolsmcp/server/worked_examples.py`, `recipes.py`,
  `docs/FLEXTOOLS-STYLE-GUIDE.md`, `docs/workflow-detail.md`: no hvo-persistence
  pattern found (grep clean).
- **Cross-repo dependency, NOT fixed here (flexicon is read-only for me):** the
  offending example is `flexicon/flexicon/code/Shared/MediaOperations.py:1497-1516`,
  `GetHvo`'s docstring (`>>> media2 = project.Object(hvo)`). It is statically
  extracted into this repo's generated index
  (`src/flextoolsmcp/index/python/flexicon_api_v4.5.2.json:44013`), one of the
  pre-existing untracked/modified index files I was told to leave alone anyway.
  Flagging for a flexicon-side docstring fix (swap `hvo`/`GetHvo` for
  `GetGuid`/`guid_str` in that example) -- out of scope this cycle.

## Test results
`python -m pytest -q` (rerun after an isolated flake): **1041 passed, 4 skipped**
(includes the 18 new #103 tests). One run showed a single unrelated failure,
`test_flextools_health.py::TestFileDiscoveryCacheInvalidation::test_new_exact_file_visible_after_write`
(mtime-resolution timing race in file-discovery caching, untouched by this
change); it passed standalone and on a second full-suite rerun, confirming
pre-existing flakiness, not a regression from #103. Current HEAD's baseline is
higher than the stated "961 passed, 3 skipped" because several other commits
landed on this branch since that count was taken.

Not touched: casting gate (`validators.py` severity logic, `execution.py`
casting block) -- content unchanged, only shifted by the two insertions above.
flexicon repo -- read-only, not edited.
