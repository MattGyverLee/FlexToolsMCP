# WS-focus cycle 2 -- Doc Agent amendment pass

**Date:** 2026-09-20
**Trigger:** lex-lead dispatch, following `ws-focus-cycle1-archivist.md`'s
AMEND verdict on `data-model.md` cross-cutting rule 2.

## Source of truth

Read `specs/parser-check/reviews/ws-focus-cycle1-archivist.md` first, per
instructions. Its verdict: the emptiness predicate `form in (None, "", "***")`
is correct about *values* and silent about *type* -- `IMoForm.Form` is an
`IMultiUnicode` object, never `==` to any of those literals, so the predicate
was unconditionally `False` and the check could never fire. Fix type: AMEND
(insert a WS-resolution step before the existing sentence; predicate itself
unchanged).

## Edits made

### 1. `specs/parser-check/data-model.md` -- cross-cutting rule 2 (was lines 158-173)

Inserted a WS-resolution paragraph between the "will silently miss every one
of them" sentence and the predicate code block. States explicitly:
- `IMoForm.Form` (and every other field this table reads that is typed
  `IMultiUnicode`/`IMultiString`) is an object, not a `str`.
- Vernacular default WS for forms/representations; analysis default WS for
  glosses/names/abbreviations.
- The raw multistring object is never compared directly and never serialized
  directly.
- Cross-references `contracts/flextools_grammar_health.md`'s "`label` is
  always a plain string" rule (output-side twin of this input-side rule) and
  `docs/FLEXTOOLS-STYLE-GUIDE.md:150-160` (the "LibLCM (raw C#)" example
  already in this repo showing resolve-then-compare).
- Restated the predicate's preamble as "**The predicate every row applies to
  that resolved string is exactly:**" -- the code block itself
  (`def is_empty_form(form): return form in (None, "", "***")`) is
  byte-identical to before, per the archivist's "predicate unchanged" verdict.
- Added a closing sentence after the code block clarifying `form` is already
  a plain `str` at that point (the WS-resolution step's output), and that
  skipping the step doesn't merely undercount -- it undercounts
  unconditionally, at zero, forever.

### 2. `specs/parser-check/data-model.md` -- row table (was lines 239-254)

Added one cross-cutting note directly beneath the "ten rows" table (no new
column). States which rows actually touch a multistring field per the
archivist's/lead's scoping -- rows 1, 2, 6, plus the `objects[]` label sites
in rows 5 and 7a -- and that any of those must resolve to a plain `str` at a
named WS before comparison/serialization. Explicitly warns that a future
row 11 is not exempt, addressing the archivist's specific concern that
without this note row 11 would reproduce the bug.

### 3. `specs/parser-check/SPEC.md` -- section 9.5.4 (~line 1440, end of "Three
implementation notes")

Added a fourth bullet mirroring the data-model.md table note: no WS column,
rows 1/2/6 plus label sites in 5/7a are the multistring-touching rows, must
resolve before compare/serialize, skipping the step makes the predicate
unconditionally `False` (not "merely wrong"), future rows are not exempt.
Kept language consistent with the rest of section 9.5.4's implementation-note
style (bullet list, cross-references data-model.md rather than repeating its
full text).

### 4. `specs/parser-check/contracts/flextools_grammar_health.md`

Read the existing cycle-1-programmer addition first ("`label` is always a
plain string," lines ~71-79) to avoid duplication/contradiction, per the
task's explicit instruction. Added a new paragraph immediately after the
existing "Row 1's `measured` wording is deliberately unconditional at CP1"
paragraph (before "### Forbidden in the response"), stating:
- Reaching a nonzero `count` for row 1 (and row 6, same field) requires the
  predicate to run over a WS-resolved string, not the raw object.
- Before that resolution step, `count: 3` in the worked example was
  structurally unreachable -- the check ran but could only ever report zero.
- Explicitly distinguishes this (predicate/count side) from the existing
  `label` rule (serialization side): "this one is about the predicate that
  produces `count`; the one below is about what `objects[]` serializes. Both
  must resolve at a named WS; neither substitutes for the other." This avoids
  contradicting or restating the programmer's section while making clear the
  two fixes are related but distinct.

No language in any of the above uses severity/score/verdict wording --
consistent with SPEC 9.5.3/9.5.7 ("suspects, not verdicts").

### 5. `specs/parser-check/tasks.md` -- T033 (line 129) and T034 (line 142)

Left as a historical log, per instructions -- did not rewrite the quoted
predicate as though it had always been complete. Appended a bracketed
`**[Historical note, added post-hoc: ...]**` sentence to the end of each
task's line (after its file-path marker), each pointing at `data-model.md`'s
amended cross-cutting rule 2. T034's note additionally cross-references
`contracts/flextools_grammar_health.md`'s new count-reachability paragraph.

### 6. `tests/fixtures/parser_check.py` (~line 151-171)

Added a `# KNOWN SIMPLIFICATION:` comment block inside `FakeIMoForm`'s
docstring, immediately after the existing text, per the exact instruction
(comment only, no behavior/type/test change). States that this fixture
models `.Form` as already-resolved, that a live `IMoForm.Form` is an
`IMultiUnicode` object, and that tests built against this fixture cannot
catch a WS-resolution defect -- because the fixture skips straight past the
step that was actually missing. Did not touch the `Form: Optional[str]` type
annotation, any fixture function, or any test file.

## Constraint compliance

- No severity/score/ranking language added anywhere (checked all six edits
  against SPEC 9.5.3/9.5.7's "suspects, never verdicts" rule).
- Only files on the allowed list were touched:
  `specs/parser-check/data-model.md`, `specs/parser-check/SPEC.md`,
  `specs/parser-check/tasks.md`,
  `specs/parser-check/contracts/flextools_grammar_health.md`,
  `tests/fixtures/parser_check.py` (comment only), and this report.
- Did not edit `grammar_scan_module.py` (its docstrings at 110-122 and
  375-377 restate the old rule too -- see "Carried-forward" below).
- Did not edit `docs/FLEXTOOLS-STYLE-GUIDE.md` (read-only cross-reference,
  per instructions -- a lex-programmer agent is editing it concurrently).
- Did not edit `execution.py`, `parse/*`, `subprocess_helpers.py`,
  `CHANGELOG.md`, `docs/TOOL-CONTRACT.md`, or any `specs/parser-check-cp2b/**`
  file -- confirmed untouched.
- Made no commits.

## Carried-forward edit for next checkpoint (not made, per explicit instruction)

`src/flextoolsmcp/server/scan/grammar_scan_module.py` restates the old
predicate without the WS-resolution step in two places, and should be
amended in lockstep with the code fix once live verification against the
current file completes:
- Lines 110-122: `is_empty_form`'s docstring/comment.
- Lines 375-377: row 3a's comment (the archivist's report also lists
  298/560/602/637 as label sites passing raw `.Form` -- those are code, not
  docstrings, and belong to the programmer's concurrent fix, not this doc
  pass).

## Open follow-ups

- The next checkpoint should update `grammar_scan_module.py`'s two
  docstring sites (110-122, 375-377) to match the amended `data-model.md`
  rule 2, once the code fix and live-LCM verification land.
- `tests/fixtures/parser_check.py`'s `FakeIMoForm.Form` remains typed
  `Optional[str]` and does not model the unresolved `IMultiUnicode` shape --
  the `# KNOWN SIMPLIFICATION` comment flags this for the next checkpoint's
  fixture upgrade; deliberately not changed here (would touch the 102
  currently-passing tests, out of scope for this doc-only pass).

---
**Doc Agent:** /lex-doc
