# WS-focus cycle 1 -- Archivist investigation

## 1. Rule text and fix type

`specs/parser-check/data-model.md`, `### Cross-cutting rules`, item **"2. The
emptiness predicate is `form in (None, "", "***")`."** (lines 158-173):
applies to every row reading `IMoForm.Form`/`IMultiUnicode`/`IMultiString`
"directly off LCM"; predicate `is_empty_form`.

**Verdict: AMEND.** The rule never states `form`'s type at the predicate.
`IMoForm.Form` is an `IMultiUnicode` object, not `str`; a pythonnet
multistring is never `==` `"***"`/`""`/`None`, so the predicate is
unconditionally `False` -- the check can never fire. Minimal fix: insert a
WS-resolution step before the existing sentence -- resolve the multistring to
a plain string at a named WS (vernacular default for forms, analysis default
for glosses) **before** calling `is_empty_form`. The predicate is unchanged;
only its input contract needs stating.

## 2. Provenance -- unexamined, not deliberate

`cycle10-doc-t033.md`, `cycle10-programmer-t019.md`,
`cycle10-programmer-t034.md`, `tasks.md` T019/T033/T034/T035 (lines 129, 138,
142, 146) restate `form in (None, "", "***")` verbatim -- zero mention of
"writing system," `.Text`, or `BestVernacularAlternative`. No review reasons
about which WS. `tests/fixtures/parser_check.py` (`FakeIMoForm.Form:
Optional[str]`) stubs `.Form` as a plain string, masking the bug in tests
too. T033 transcribed CLAUDE.md's `"***"` fact minus the type step; T019/T034
implemented literally against that table. Contrast:
`docs/FLEXTOOLS-STYLE-GUIDE.md:150-160` already shows the correct pattern
(`.AnalysisDefaultWritingSystem.Text` resolved *before* the `"***"` compare)
-- the right idiom existed elsewhere and wasn't carried over.

## 3. Every restatement (file:line)

- `data-model.md:158-173` (rule 2), `:263` (row 1 predicate)
- `tasks.md:129` (T033), `:142` (T034)
- `grammar_scan_module.py:110-122` (`is_empty_form`), `:375-377` (row 3a
  comment), `:298,560,602,637` (label sites passing raw `.Form`)
- `tests/fixtures/parser_check.py:150-160`; `tests/test_grammar_scan_checks.py:44`
- `docs/FLEXTOOLS-STYLE-GUIDE.md:155,160,265,269` -- CORRECT already
  (WS-resolve first); cross-reference, don't fix.
- CLAUDE.md's `"***"` section covers Operations-layer normalization only, no
  raw-predicate restatement -- no edit needed.

## 4. Contract impact

`contracts/flextools_grammar_health.md:48-54`: row 1's "deliberately
unconditional at CP1" is about slot-reachability, stays accurate. But the
worked example (`count: 3`) is currently unreachable -- code structurally
always yields `count: 0` for row 1 (and row 6). Post-fix, `count` becomes
real for the first time -- add a sentence noting the WS fix enables a
nonzero count. Separately, `label` in `objects[]` is built from a raw
`IMultiUnicode` at 4 sites (298/602/637/560); serializing that to JSON is
the shipped crash, independent of row 1's predicate -- fix both together.

## 5. SPEC 9.5.4 row table

`data-model.md:239-254` / `SPEC.md:1392-1442` have no WS column. Add one
cross-cutting note (not a full column -- only rows 1, 6, and label sites
5/7a touch multistring fields): "any row reading `IMultiUnicode`/
`IMultiString` must resolve it at a named WS before comparing/serializing."
Without it, row 11 reproduces the bug.

## Doc edits required (file -> change)

- `data-model.md` -- amend rule 2 (add WS-resolution step); add WS note to
  the row table.
- `tasks.md` -- T033/T034 quote the old predicate; footnote or leave as
  historical log (lex-lead's call).
- `contracts/flextools_grammar_health.md` -- note row 1's `count`/label
  becomes non-structurally-zero only after the WS fix.
- `grammar_scan_module.py` docstrings (110-122, 375-377) -- code fix, update
  in lockstep with the spec amendment.
- `tests/fixtures/parser_check.py` -- `FakeIMoForm.Form` should model the
  WS-resolution requirement (or flag the simplification).

---
**Archivist:** /lex-archivist
