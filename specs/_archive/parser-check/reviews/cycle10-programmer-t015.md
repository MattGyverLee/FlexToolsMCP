# Cycle 10 -- Programmer T015

**File:** `tests/test_grammar_scan_checks.py` (new). No `src/` file touched; no fixture
additions (T002's stubs already cover everything needed).

## Tests added (19, in 4 classes, RED by design)

**`TestZeroSurfaceMorphRow1`** (row 1) -- against `is_zero_surface_form(form)`:
`"***"` counted (the regression guard -- direct-LCM-read gets no Flexicon
`"***"`->`""` normalization); `None`/`""` counted; a real surface never counted;
**CP1-scope positive assertion**: `inspect.signature` has no slot/position param,
plus a form with no slot association is still counted, proving the check cannot be
conditioned on optional-slot reachability (deferred to T034); a mixed-list count
sanity check.

**`TestOptionalTemplateSlotsRow10`** (row 10) -- against `is_optional_slot(slot)`:
optional/non-optional counted correctly; run on `FakeIMoInflAffixSlot` (no `.Name`
attribute by fixture design) and assert **no `AttributeError`** -- proves the
predicate never does `ICmPossibility(obj).Name`; plus a static
`inspect.getsource()` grep asserting the literal string `"ICmPossibility("` never
appears in the module once it exists.

**`TestDisabledRulesExcludedBeforeCounting`** -- against `exclude_disabled_rules(rules)`:
filters one disabled rule out, retains all-enabled, all-disabled yields `[]`, and
an explicit "excluded count != raw count" assertion so exclusion can't be mistaken
for a post-hoc filter applied after counting.

**`TestChecksSkippedUnverifiedNeverSilentlyOmitted`** -- against `skipped_check(check_id)`:
reason is exactly the literal `"lcm_name_unverified"`; entry is closed to exactly
`{check_id, reason}` (no severity-proxy key); parametrized over three plausible
gated check-ids to show the reason string is stable, not tied to which row it is.

## API assumed (documented as CONTRACT AMBIGUITY in the file header)

Neither `data-model.md` nor the tool contract pins per-check function names inside
`grammar_scan_module.py`, and `scan/__init__.py`'s own docstring forbids that module
importing `flextoolsmcp.server.*` (so it cannot build `GrammarHealthFinding`/
`FoundObject` pydantic models itself -- those need a live `project` for
`BuildGotoURL` anyway). I inferred a predicate-level API -- `is_zero_surface_form`,
`is_optional_slot`, `exclude_disabled_rules`, `skipped_check` -- directly from the
task text's own phrasing ("The emptiness predicate is `form in (None, "", "***")`")
rather than guessing at a finding-builder. Matched T008's convention: per-test lazy
imports, no `xfail`, plain failures. If T019/T034/T035 choose different names, only
this file's imports need to change.

**Row I could not pin a predicate for:** none of rows 1/10/Disabled-gate -- those
are exactly what T015 targets and SPEC 9.5.4 gives concrete predicates for all
three. Rows 3/5/7 (the `checks_skipped` gate) are deliberately tested only through
the generic `skipped_check()` mechanism, not against a specific row, since which
rows land verified vs. skipped depends on T016's not-yet-run research.

## Pass/fail and full-suite delta

- `pytest tests/test_grammar_scan_checks.py -q`: **19 failed** (all clean
  per-test `ModuleNotFoundError`/`ImportError` -- no collection error, no other
  failure mode).
- `ruff check tests/test_grammar_scan_checks.py`: clean.
- `pytest tests/ -q`: **1452 passed, 8 skipped, 36 subtests passed, 56 failed**.
  56 = my 19 (T015, new) + 37 pre-existing `tests/test_parser_health_block.py`
  (T008, already RED before I started, not touched by me). `tests/test_parser_probe.py`
  (T007) passes fully (15/15) and was untouched. No unrelated regression; I did not
  modify `tests/fixtures/parser_check.py`, so nothing there could break.
