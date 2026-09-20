# Issue #144 -- Programmer Cycle 2 Report

## Files changed

- `src/flextoolsmcp/server/handlers/execution.py`
  - New `_probe_undoable_capability()` helper (before `_validate_api_mode`).
  - Runner template (~3905-3923): replaced hardcoded `undoable=False` with
    `import flexicon; _CAPS = getattr(flexicon, "CAPABILITIES", frozenset()); _undoable = "per-operation-uow" in _CAPS`,
    passed as `undoable=_undoable` to `OpenProject`. Comment rewritten.
  - Gate rationale comment (~2887-2911) and rejection message (~2917-2966):
    re-derived per mode; message now mode-conditional via
    `_probe_undoable_capability()`; `next_steps` items 1-2 de-hardcoded.
- `src/flextoolsmcp/server/validators.py`: module comment above
  `detect_nested_unit_of_work` (~452-486) re-derived for both modes;
  verdict text notes the gate stays construct-based/unconditional.
- `src/flextoolsmcp/server/response_models.py`: `NestedUnitOfWorkDetail`
  docstring (~263-276) re-derived.
- `src/flextoolsmcp/server/session.py`: `nested_unit_of_work` assistance
  hint (~75-88) re-scoped off "the runner already has a UnitOfWork open
  for the whole run."
- `src/flextoolsmcp/server/tool_definitions.py`: `flextools_start`
  description undo claim (~112-119) replaced.
- `tests/make_golden.py` (~151-158) + regenerated
  `tests/golden/responses/nested_unit_of_work.json` (via `--regen`).
- `tests/test_nested_uow_gate.py`: docstring re-derived (~6-31); appended
  `TestCapabilityProbe` (3 tests) and `TestModeConditionalMessage` (2
  tests) at EOF.
- `tests/test_issue92_write_path_e2e.py`: docstring (~18-23) re-derived.
- `tests/test_issue55_write_safety_ladder.py`: docstring (~7-19) re-derived.

## Mode-conditional message text

- Legacy / capability-less (`_undoable=False`, unchanged): "Code opens its
  own raw liblcm UnitOfWork, which nests inside the runner's already-open
  non-undoable task and will discard this run's writes."
- Capable (`_undoable=True`, new): "Code opens its own raw liblcm
  UnitOfWork. flexicon already wraps each mutation in its own named unit
  of work; a raw helper call executing while one of those is open nests
  inside it and will discard that operation's writes before the error is
  raised."

Chosen via a new `_probe_undoable_capability()` (best-effort import of
`flexicon` in the server process to select wording; the actual
`undoable=` decision happens independently in the subprocess template, so
a version mismatch between the two processes would only ever mis-word the
message, never mis-fire the gate). `tool_definitions.py`'s
`flextools_start` undo claim and `session.py`'s assistance hint were both
re-scoped the same way (static, not probed at runtime, since they aren't
generated per-request).

## SaveChanges finding (report only, not fixed)

Grepped `src/` for `SaveChanges`: zero call sites in code. The only hits
are (a) index/embedding JSON (generated API docs, not code paths), and
(b) prose in `src/flextoolsmcp/server/handlers/admin.py` (shared-mode
health/lock discussion, explicitly out of scope, untouched) that
speculates about a hypothetical "write-enabled fresh session that calls
SaveChanges() first." Confirmed against the installed flexicon 4.8.0
source (`FLExProject.py:1048-1170`): the depth guard raises
`FP_TransactionError` whenever `CurrentDepth > 0`, and under
`undoable=False` that is unconditionally true for the whole session (the
session-envelope holds depth at 1), so `SaveChanges()` can never succeed
mid-session in that mode -- confirming the premise. Under `undoable=True`
it CAN succeed once called outside any `Transaction()`/`UndoableOperation()`
block. Since this repo's generated runner never calls `SaveChanges()` at
all (it always uses `CloseProject()`), the #144 gate landing changes
nothing observable here -- there is no `SaveChanges()` call site whose
behavior shifts.

## FLEXTOOLSMCP_WRITE_CONTRACT.md

Not present in the installed wheel: checked
`.venv/Lib/site-packages/flexicon/` (via
`uv run python -c "import flexicon, os; print(os.path.dirname(flexicon.__file__))"`)
-- no `docs/` subdirectory at all, matching the domain report's
expectation. Proceeded on source evidence instead: read
`flexicon/__init__.py` (lines ~14-60, the `CAPABILITIES` docstring) and
`flexicon/code/FLExProject.py` (`OpenProject`, `SaveChanges`,
`HasOpenSessionTask`) directly; both match the domain report's citations
exactly, including the literal `getattr(flexicon, "CAPABILITIES", frozenset())`
form and the `per-operation-uow` / `transaction-rollback` token names.

## Tests

`uv run pytest -q`: **1153 passed, 7 skipped, 14 subtests passed** (was
1148/7 baseline; +5 new tests in `test_nested_uow_gate.py`, no
regressions, no other count changes). Also ran
`uv run python tests/make_golden.py --regen` (1 fixture regenerated:
`nested_unit_of_work.json`; the exact-content golden tests only check key
presence/dual-emit shape, not message text, so this was a docs-accuracy
edit, not a required-to-pass one).

No `.fwdata` opened; no live FLEx verification attempted (out of scope
for this agent).
