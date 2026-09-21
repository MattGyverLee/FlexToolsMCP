# Cycle 2 -- Programmer report: CP2b honesty-gap fix (piece 1)

## Changes, by file:line

**`src/flextoolsmcp/server/parse/worker_main.py`**
- `_summarize_trace(trace)` added (:810-864), alongside `_summarize_plain`.
  Reads `trace.Root.Element("Error")` first (blocking check), else counts
  `root.Elements("Analysis")`. No second parser call.
- `_RealBackend.parse()` (:707-758): `restricted` (:724-750) and `explain`
  (:752-754) branches now call `_summarize_trace` instead of returning
  `{"parse": None, ...}`. **The restricted branch renames the generic
  result** (:745-749) -- `parsed`/`analysis_count` -> `hypothesis_held`/
  `restricted_analysis_count` -- right here, since this is the one place
  that already knows which question the call asked. This makes every
  worker entry self-describing downstream (no `level` plumbing needed in
  `runner.py`, which still passes `result["parse"]` through verbatim,
  unchanged).
- Module docstring (:57-71) updated: `parse` is documented as never null.

**`src/flextoolsmcp/server/handlers/parse.py`**
- Guard at :465 (now :476-483): rewritten to `is_definite_parse_failure`,
  keyed on `"parsed" in result` + `False` + `"parse_error" not in result`,
  restricted to `level in ("plain", "explain")`.
- `_inline_response` else-branch (:555-603): now copies `parse_error`, or
  `parsed`/`analysis_count` (explain), or `hypothesis_held`/
  `restricted_analysis_count` (restricted) into `result`, by name -- no
  key is set on a level it doesn't belong to.
- `_level_guidance` explain branch (:806-... via new code at ~816-829):
  gained the plain branch's success gate (`explains_failure: False,
  next_step: None`) and an error branch that omits `explains_failure`
  entirely. Restricted branch **left untouched** -- out of the settled
  scope, still unconditionally `{"explains_failure": True, "next_step":
  None}`.
- `_result_summary` (:947-980): now counts `hypotheses_held` separately
  from `parsed`, each read only where the entry carries that key.

## The three-way `<Error>` handling, as implemented

`_summarize_trace` checks `root.Element("Error")` before touching
`Elements("Analysis")` at all. Present -> `{"parse_error": str}` alone,
nothing else. Absent -> `{"parsed": bool, "analysis_count": int}` from the
`<Analysis>` count. The restricted branch of `parse()` preserves
`parse_error` verbatim (no renaming) and only renames the non-error shape.
`_inline_response` checks `"parse_error" in parse` first, before the
per-level branches, so neither `parsed` nor `hypothesis_held` can ever
appear alongside `parse_error`. Verified by
`test_explain_on_a_parser_error_names_neither_outcome` and
`test_restricted_on_a_parser_error_names_neither_outcome`.

## Tests

New file `tests/test_summarize_trace.py` (9 tests): hand-rolled
`_FakeXElement`/`_FakeXDocument` stand-ins covering all three outcomes,
including a `<Trace>` sibling holding a nested `<Analysis>` (must not
inflate the count) and `<Error>` alongside an `<Analysis>` (error still
wins).

`tests/test_try_word_handler.py`: `RecordingWorker` gained
`trace_outcome`/`trace_analysis_count` (default `"failure"`, matching most
existing tests' assumptions). Added: explain-success (no proposal, gate
fires), explain-error, restricted-error, restricted-success-never-carries-
`parsed`. Narrowed: `test_the_explaining_levels_say_they_explain` split into
`..._on_failure` (unchanged assertions) + new success test;
`test_explain_steers_back_toward_restricted` and
`test_no_proposal_is_offered_when_the_caller_already_gave_one` got added
assertions (`explains_failure is True`, `"parsed" not in payload`) pinning
which case they exercise.

`tests/test_parse_proposal.py`: `test_agreement_produces_no_commentary` now
sets `wired.trace_outcome = "success"` and asserts `hypothesis_held is
True` -- previously it passed regardless of outcome.

`tests/test_parse_status_handler.py`: two new tests reproduce the NEW HIGH
sibling directly (explain run -> `result_summary["parsed"] == 2`;
restricted run -> `hypotheses_held == 1`, `parsed == 0`).

`tests/test_flexicon_index_floor.py` -- untouched, per instruction.

## Baseline / after

- `tests/test_try_word_handler.py` alone: 40 -> 44 passed, 0 skipped
  either side.
- Full `pytest -m "not requires_flex" --continue-on-collection-errors -q`:
  **before** 2001 passed, 6 skipped, 71 deselected. **after** 2016 passed,
  6 skipped, 71 deselected. (+15 = 4 + 2 + 9 new tests; no failures, no
  newly-skipped.) Measured by stashing only this session's own tracked
  files (leaving the parallel doc/spec agent's uncommitted work
  untouched) and diffing the two runs.

## Could not verify without a live FLEx project

`_summarize_trace`'s calls -- `root.Element("Error")`, `root.Elements
("Analysis")`, and `.Value` on the error element -- are exercised only
against hand-rolled Python stand-ins implementing that slice of
`System.Xml.Linq.XElement`'s public surface. I could not confirm against a
real pythonnet `XDocument` from `TraceWordXml`/`ParseWordXml` that these
calls bind the way I assumed (string-argument overload resolution to
`XName` through pythonnet's implicit-operator handling), nor that a genuine
`<Error>`-bearing document actually arises the way `HCParser.cs:219-222`
describes. `tests/test_parse_live.py` is the existing live-gated harness
that would need a scenario forcing an HC parser exception to close this
gap; none currently does (per cycle 1's test recon, no live test exercises
explain-on-success either, which is the same live gap one level over).

No changes were made outside `src/` and `tests/`.
