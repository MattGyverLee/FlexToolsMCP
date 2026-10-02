# Programmer Report -- Cycle 3 (process fix: pattern-audit gate + P1 test)

## 1. Pattern sweep

Shape: an optional kwarg/default arg that silently selects a different
flexicon/LCM execution path, where the wrong path fails quietly or reports
false success. Scope: `src/flextoolsmcp/` (execution.py end-to-end,
session.py, admin.py, models.py, tool_definitions.py, kernel.py,
validators.py, subprocess_helpers.py, server.py, response_utils.py,
op_telemetry.py, curated_recipes.py, worked_examples.py, and the
generated-doc index under `src/flextoolsmcp/index/`).

**Siblings found:**

- **[MED]** `execution.py:326` -- the `"liblcm"` API-mode's
  `FLExProject.OpenProject(self, projectName, writeEnabled=False)` stub
  (inside `BASE_IMPORTS["liblcm"]`, built by `_get_api_mode_imports()`)
  ignores `writeEnabled` entirely and has no `undoable` param at all.
  `_get_api_mode_imports()` has zero callers in `src/` today (dead code),
  so it can't fire now -- but it's the exact bug shape lying dormant: if
  ever wired back in, the hardcoded `undoable=False` call this commit adds
  at `execution.py:3508` would `TypeError` against this stub, or silently
  ignore `writeEnabled`. No fix applied (inert, out of CP1 scope).
- **[LOW]** `execution.py:3345` -- `FlexToolsModule.Run(..., modifyAllowed=False)`
  defaults safe-direction; sole call site (`execution.py:3632`) always
  passes `WRITE_ENABLED` explicitly. Defensive/unreachable, not live.
- **[LOW]** `index/common_patterns_flexicon-v4.3.0.json:1271` (+ archived
  versions) -- flexicon's own `CreateField()` docstring, surfaced via
  `find_examples`/`get_object_api`, already documents a structurally
  identical landmine (raw-LCM schema bypass "appears to succeed" without
  persisting). Not our code; already self-documented; flagged FYI only.

No HIGH siblings. Other default-arg chains reviewed (`write_enabled_arg`/
`effective_auto_fix`/`backup_before_write`/`validate_only` in
`execution.py:2474-2620`, `_resolve_inherited_flag` in `admin.py`, `Field()`
defaults in `models.py`) each have a single explicit-value call site or
default toward the safe direction.

## 2. Amended commit

`d17105f` -> **`8a4fae53c413f271d704a4832a533d7e0fd47ce5`** (amend). Added
a "Pattern audit" heading with the sibling list above between the prose
body and the `Co-Authored-By` trailer; body/trailers preserved verbatim
otherwise. Also folded in the item-3 test fix (see below) into the same
commit, since it touches the same test CP1 already modified.

## 3. Test fix

`tests/test_v1_3_0_upgrade.py` -- `test_operation_history_tracking`
renamed to `test_operation_history_field_exists_and_starts_empty`.
`operations_history` is never appended to anywhere in production
(grep-confirmed, read-only field); the old assertion
(`assertEqual(state.operations_history, [])`) was trivially true and the
docstring overclaimed "operations can be recorded." New docstring states
plainly this is an existence/empty-default smoke check, not a recording
test. `pytest tests/test_v1_3_0_upgrade.py` -- 22 passed.

## 4. SPEC.md additions

- **T6.7** (under CP6): document the `error_type="ReportedError"` retry
  contract -- callers must check `summary.error_count` vs
  `summary.total_messages` before retrying, and never blind-retry
  Create*/append mutations (only idempotent setters like `SetGloss`/
  `SetLexemeForm` are safe to re-run). Source: cycle2-domain.md.
- New **Section 8, "Deferred follow-ups"**: pre-existing P2 --
  `docs/TOOL-CONTRACT.md:13-26` claims all success responses carry
  `_contract`/`status`/`op_id`, but `run_module`'s raw dict never does.
  Predates CP1, out of scope, draft only -- no issue filed.

Separate commit `af79d81`: `docs: record the CP1 review trail and
deferred follow-ups (#93)`.
