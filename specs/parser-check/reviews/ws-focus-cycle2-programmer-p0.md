# Cycle 2 -- Programmer P0 fix: `is_empty_multistring` silent-false bug

**Author:** Programmer agent (matthew_lee@sil.org)
**Scope:** shipped runtime helper injected into every generated FLExTools
module / bare snippet run via `run_module` (`src/flextoolsmcp/server/handlers/execution.py`)

## Bug recap

`is_empty_multistring(text)` is documented (style guide, `admin.py`
`namespace_helpers`) as "True for None, '', or '***'". The shipped
implementation coerced any non-`str` input via `str(text)` before
comparing. A raw LCM multistring/tsstring object (`sense.Gloss`,
`form.Form` via direct C# field access -- exactly the shape the style
guide's own "LibLCM (raw C#)" example produces) yields a CLR
`ToString()`/repr that never equals `""` or `"***"`, so the helper
silently returned `False` for a field that was actually empty. Same
defect class as the grammar-scanner P0 already fixed this campaign:
typed-attribute access on a raw LCM object without resolving to text
first.

## Fix

`src/flextoolsmcp/server/handlers/execution.py` (inside the `runner_script`
template string, function at what was line 4067, `is_empty_multistring`):

- Kept the existing `None` -> `True` and `.strip()` / `==` comparisons
  byte-identical.
- Before falling back to `str(text)`, a non-`str` input is now resolved via,
  in order, each attempt independently guarded so it can never raise:
  1. `.Text` (ITsString)
  2. `.BestAnalysisAlternative.Text` (IMultiUnicode / IMultiString)
  3. `.BestVernacularAlternative.Text` (IMultiUnicode / IMultiString)
  A candidate is only accepted if it is itself a `str` (so a `.Text` that
  is `None` or some other non-str CLR artifact is skipped rather than
  crashing `.strip()` later). If every attempt fails or yields a non-str,
  falls back to the original `str(text)` behaviour -- never raises.
- Docstring added stating plainly that the helper accepts EITHER an
  already-resolved `str` OR a raw multistring, and documents the
  resolution order.

This is additive/defensive only: every input that used to return `True`
still returns `True`, every plain-`str` input is handled identically to
before. No caller could have been relying on "False for an empty
multistring" as documented behaviour, per the lead's ruling.

## Docs updated

- `docs/FLEXTOOLS-STYLE-GUIDE.md`:
  - Section 5 ("Multistring Handling", ~line 145) now cross-references the
    "Helper Functions" section and notes `is_empty_multistring` covers all
    three shown shapes (Flexicon str, FlexLibs `"***"` str, raw LibLCM
    object) in one call.
  - Section 8 ("Helper Functions", ~line 264) usage example no longer
    shows a bare, ambiguous `gloss` variable. It now shows both the
    Flexicon-str call site (`project.Senses.GetGloss(sense)`) AND the raw
    C# call site (`sense.Gloss`, no `.Text` extraction needed), and
    cross-references Section 5 for the raw-vs-resolved distinction.
- `src/flextoolsmcp/server/handlers/admin.py` (`namespace_helpers.available`,
  line 295): description extended to state it also accepts a raw
  multistring object and names the resolution order.
- `src/flextoolsmcp/server/tool_definitions.py` (line 282): audited --
  this line is a bare name list (`Helpers: is_empty_multistring,
  FLEX_EMPTY_PLACEHOLDER, ...`), not a behavioural claim, and is not
  inaccurate as written. Left unchanged; no correction was needed here
  (the behavioural claim the audit flagged lives in `admin.py`, which was
  corrected).

## Tests

New file (no existing pytest-real home found -- see below):
`tests/test_is_empty_multistring_defensive.py`

Rationale for a new file rather than reusing an existing one: grepped for
every existing reference to `is_empty_multistring` in `tests/`. The only
candidate "natural home" was `tests/test_flexicon_operations.py`'s
`test_empty_multistring_handling` -- but that method (and its sibling
`FlexiconTestRunner`/`FlexiconStaticAnalyzer` scripts in
`test_flexicon_operations.py` / `test_flexicon_static_analysis.py`) never
actually executes the `test_code` strings it builds; it just records
"structure valid" results with no `assert`. Its embedded snippet also
asserts the OLD, now-superseded contract (`is_empty_multistring('') ==
False`), which would be actively wrong if executed for real. Reusing it
would mean exec-ing dead/stale strings inside a non-pytest harness class,
not a real regression test. Creating a new file was explicitly permitted
by the task brief for exactly this situation.

The new test extracts the real function straight out of
`execution.py`'s `runner_script` template string via `ast` (parses
execution.py to get the string literal's value, parses that as its own
module, locates the `is_empty_multistring` `FunctionDef`, pulls its exact
source segment, and execs it in an isolated namespace seeded with
`FLEX_EMPTY_PLACEHOLDER = "***"`), so the test exercises the exact code
that ships rather than a hand-copied duplicate that could drift.

Coverage (15 tests, 2 classes):
- `TestIsEmptyMultistringRegression` (7 tests) -- None / `"***"` / `""` /
  whitespace-only / whitespace-padded `"***"` / non-empty str / whitespace-
  padded non-empty str, all asserting IDENTICAL behaviour to before (the
  regression-guard half the brief called out as mattering as much as the
  new behaviour).
- `TestIsEmptyMultistringDefensiveUnwrap` (8 tests) -- fake object with
  `.Text == ""` (must now be `True`, this was the bug), `.Text` non-empty
  (`False`), `.BestAnalysisAlternative.Text` empty/non-empty, fall-through
  to `.BestVernacularAlternative.Text` when both `.Text` and
  `.BestAnalysisAlternative` raise, an object where every unwrap attempt
  raises (must not propagate, must return `bool`, falls back to
  `str(obj)`) tested both where the fallback resolves empty and non-empty,
  and a `.Text` that exists but is `None` (non-str) being correctly
  skipped rather than crashing `.strip()`.

## Test results

```
python -m pytest tests/test_is_empty_multistring_defensive.py -v
=> 15 passed in 1.09s

python -m pytest tests/test_auto_fix.py tests/test_cp1_boundary.py \
  tests/test_diagnostic_report_reconstruction.py tests/test_diagnostic_report_transport.py \
  tests/test_info_message_cap.py tests/test_issue10_session_persistence.py \
  tests/test_issue103_hvo_stability.py tests/test_issue40_casting_severity.py \
  tests/test_issue42_session_identity.py tests/test_issue47_auto_discovery.py \
  tests/test_issue49_validate_only.py tests/test_issue53_cold_start.py \
  tests/test_issue55_write_safety_ladder.py tests/test_issue80_graceful_redirect.py \
  tests/test_issue82_writeability_reject_logging.py tests/test_issue84_project_lexsense_accessor.py \
  tests/test_issue92_write_path_e2e.py tests/test_issue96_teardown_visibility.py \
  tests/test_nested_uow_gate.py tests/test_project_discovery.py tests/test_rejection_payloads.py \
  tests/test_retry_loop_detection.py tests/test_shared_mode_lock_diagnosis.py \
  tests/test_shared_mode_write_gate.py tests/test_v1_3_0_upgrade.py \
  tests/test_is_empty_multistring_defensive.py -q
=> 619 passed, 2 skipped, 2 subtests passed in 24.77s
```

(the 2 skips are pre-existing/unrelated -- present before this change, not
introduced by it)

Also verified: `ast.parse()` succeeds on the full `execution.py` file AND
on the extracted `runner_script` template string in isolation (confirms
the edit didn't break the triple-quoted literal boundary or introduce a
syntax error in the subprocess-side script).

## Files touched

- `src/flextoolsmcp/server/handlers/execution.py` (helper body + docstring)
- `docs/FLEXTOOLS-STYLE-GUIDE.md` (sections 5 and 8)
- `src/flextoolsmcp/server/handlers/admin.py` (`namespace_helpers` description)
- `tests/test_is_empty_multistring_defensive.py` (new)
- this report

`src/flextoolsmcp/server/tool_definitions.py` was read and audited but not
edited (see "Docs updated" above -- no inaccurate claim found there).

Not committed, per instructions -- the lead is scoping a path-limited
commit.
