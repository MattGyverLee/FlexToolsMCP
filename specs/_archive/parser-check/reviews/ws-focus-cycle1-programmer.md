# WS-focus cycle 1 -- programmer report

## What changed

`src/flextoolsmcp/server/scan/grammar_scan_module.py`: added one WS-resolution
seam, not four patches.

- `_ws_handles(project, override=None)` -- resolves `(vernacular_handle,
  analysis_handle)` once per scan via `project.GetDefaultVernacularWSHandle()`
  / `GetDefaultAnalysisWSHandle()`; never raises (each wrapped independently);
  `override` lets a future caller pin non-default WSes.
- `_read_ws(project, field, ws_handle) -> str` -- the canonical multistring
  reader. `None`/`str` pass through untouched (no import touched); a live
  multistring is read via `ITsString(field.get_String(ws_handle)).Text`
  (import local to this branch); falls back to `project.BestStr(field)` on any
  failure or `ws_handle is None`; final fallback `""`. Never raises.
- `_resolve_multistring_best_effort(value)` -- the no-project fallback
  `is_zero_surface_form` uses when called with one argument (every existing
  caller/test), via `.BestVernacularAnalysisAlternative`.
- `is_zero_surface_form(form, resolve=None)` -- now resolves `.Form` before
  testing; `resolve` optional, defaults to the best-effort helper so every
  existing one-arg call keeps working unchanged.
- `_found_object` -- defense in depth: coerces any non-`str` `label` via
  `project.BestStr`, else `""`, before the existing `"***"`/`None` guard.
  Structurally impossible for a non-`str` label to reach the finding dict now.
- Call sites fixed at rows 1, 5 (`affix_process.Form`), 6, 7a: each now resolves
  `.Form` via `_read_ws` at the vernacular handle before `_found_object`. Row 2
  untouched, as instructed.
- `run_grammar_scan(project, ws=None)` -- new defaulted param threading to the
  four affected `_scan_*` functions (each gained matching `ws=None`); still
  callable as `run_grammar_scan(project)`. Not wired to any tool input.

`specs/parser-check/contracts/flextools_grammar_health.md`: added a short
"`label` is always a plain string" section documenting the vernacular/analysis
split and the `""` failure fallback.

`server/handlers/grammar_health.py` and `server/models.py`: unchanged --
no seam-relevant defect found there; `FoundObject.label: str` already types
correctly and needed no change.

## Tests added (`tests/test_grammar_scan_checks.py`)

`_FakeMultiUnicode`/`_FakeTsString`/`_FakeIMoFormLive` model a live multistring
that is NOT a plain string and is never `in (None, "", "***")` (asserted
directly, proving the old predicate shape returns False on it). Then:
`is_zero_surface_form` with an explicit `resolve` returns `True` for a
genuinely empty live form; the no-arg default resolver doesn't crash either;
`_found_object` given such an object as `label` round-trips through
`json.dumps` and yields `label == ""`; and a `BestStr`-raises case still lands
on `""`.

## Result

`python -m pytest tests/test_grammar_scan_checks.py tests/test_grammar_health.py`
-- **102 passed**.

## Left alone

`handlers/execution.py` (fixed one-arg call site) and
`specs/parser-check/data-model.md` -- outside my lock, untouched. Row 2
(`_scan_representation_variant_product`) untouched per instruction (g).
