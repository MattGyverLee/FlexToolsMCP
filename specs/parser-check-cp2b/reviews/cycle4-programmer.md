# Programmer Report -- Cycle 4

## Fix 1 -- the proven XName defect (`worker_main.py:844-865`, was 844-865)

Replaced both `root.Element("Error")` and `root.Elements("Analysis")` (bare
`str` args, which pythonnet's CLR binding rejects with `TypeError: No method
matches given arguments for XContainer.Element: (<class 'str'>)`) with a
**single no-argument `root.Elements()` pass**, matching each child's
`.Name.LocalName` against `"Error"`/`"Analysis"` in one walk. Counts
`<Analysis>` and detects `<Error>` in that same pass; `<Error>` still wins
even if both appear (checked after the full walk, so encounter order can't
flip precedence). No `XName`/`System.Xml.Linq` import added; no bare string
left behind.

**Test that would have caught it**: `tests/test_summarize_trace.py`'s
`_FakeXElement.Element()`/`.Elements(name)` now **raise `TypeError`** for
any non-`None` argument, exactly like the live CLR binding; only no-arg
`.Elements()` works. The old stand-in accepted a string silently -- that's
why 2016 mock tests passed while both live levels were 100% broken.
`test_never_passes_a_bare_string_to_element_or_elements` (new) pins this
directly; all 8 pre-existing behavioral tests in that file now run against
the CLR-faithful double too, so any regression to `Element("Error")` would
raise the same `TypeError` in the suite, not just live.

## Fix 2 -- the rootless branch (`worker_main.py:844-853`)

Rootless now returns `{"parse_error": "the trace document has no root
element"}` instead of `{"parsed": False, "analysis_count": 0}`. Deleted the
comment defending the old behavior ("treated the same as zero `<Analysis>`
... never as an error, which would be inventing a fact") and replaced it
with the Delta-6 framing: an unreadable document is indeterminate, and
inventing `parsed: False` for it IS the fact-invention the old comment
claimed to avoid. Kept the asymmetry: a document WITH a root and neither
child stays a genuine `parsed: False` (unchanged,
`test_a_bare_wordform_with_no_children_at_all_is_parsed_false`, comment
updated to point at the new rootless test).
`test_a_rootless_document_is_a_parse_error_not_a_negative` replaces the old
pinning test.

## Fix 3 -- the lying signature (`parse.py:530-531`)

`_inline_response` annotation changed `-> List[TextContent]` to `-> Dict[str,
Any]`; body untouched (it always returned a dict). `pyright
src/flextoolsmcp/server/handlers/parse.py`: **7 errors -> 0 errors** (the
:479/:485/:487 subscript-on-list errors from the new presence guard, plus
the pre-existing :606 return-type mismatch, all resolved by the one
annotation fix; no code changed to match the annotation).

## Fix 4 -- the residual restricted branch (`parse.py:852-869`)

`_level_guidance`'s restricted case no longer hardcodes `explains_failure:
True`. Now: `parse_error` -> `{"next_step": None}` (flag omitted, mirrors
explain's error case); `hypothesis_held` True -> `{"explains_failure":
False, "next_step": None}` (FR-025/contracts/tools.md:97); `hypothesis_held`
False -> unchanged `{"explains_failure": True, "next_step": None}`. New
test `test_restricted_on_a_held_hypothesis_offers_no_commentary`; extended
`test_restricted_on_a_parser_error_names_neither_outcome` with
`"explains_failure" not in payload` and `next_step is None`. Failure-case
coverage already existed (`test_the_explaining_levels_say_they_explain_on_failure`,
`test_restricted_steers_nowhere`) and still passes unchanged.

## Suite counts

Baseline (cycle 3, before any fix): `pytest -m "not requires_flex"
--continue-on-collection-errors -q` -> **2016 passed, 6 skipped, 71
deselected, 0 failed**.

After all four fixes: **2018 passed, 6 skipped, 71 deselected, 0 failed**
(net +2: one CLR-faithful regression test in `test_summarize_trace.py`, one
restricted-success test in `test_try_word_handler.py`; the rootless test was
a rename/behavior-swap of an existing test, not an addition).

Did not commit, per instructions.

## Files touched (src/ and tests/ only)

- `src/flextoolsmcp/server/parse/worker_main.py` (`_summarize_trace`)
- `src/flextoolsmcp/server/handlers/parse.py` (`_inline_response` annotation,
  `_level_guidance` restricted branch)
- `tests/test_summarize_trace.py` (CLR-faithful fakes, rootless test,
  new regression test)
- `tests/test_try_word_handler.py` (restricted parse_error assertions,
  new restricted-success test)
