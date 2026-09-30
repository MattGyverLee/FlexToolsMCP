# T022 -- Engine-gate tests for check_active_parser

New file: `tests/test_parser_engine_gate.py`. Per-test lazy imports of
`check_active_parser`/`ParserEngineMismatchError` from `parser_probe`
(T008's convention, no `xfail` precedent). `parser_probe.py` exists
(T007/T009 landed) but has no `check_active_parser` yet, so every test
touching it fails with `ImportError` -- correct RED for T024.

**Tests added (20), by property:**
- Sanity (4, pass today, no parser_probe import): the file's own
  `_resolve_active_parser_from_xml` test-only mimic of
  `OverridesLing_MoClasses.cs:4213` against the three T002 fixtures.
- Property 1 -- refusal, not a parse (3): XAmple-active/HC-only-supported
  raises with all three fields; matching engine returns `None`; a
  refusal never touches `LcmCache` (spy technique borrowed from T007's
  `TestCP1Boundary`).
- Property 2 -- case-sensitive closed set (5): exact `"HC"` accepted;
  `"hc"/"Hc"/"hC"` and `"xample"/"HERMITCRAB"/"hermitcrab"/"Xample"` all
  refuse rather than being silently matched.
- Property 3 -- fail-safe on corruption (2): `PARSER_PARAMETERS_XML_CORRUPT`
  refuses as `configured_engine == "XAmple"` when only HC is supported
  (written so an inverted default fails loudly: `pytest.raises` itself
  reports "DID NOT RAISE" first); and is accepted with no refusal at all
  when XAmple is the supported engine, confirming the resolution is the
  literal string, not an error sentinel.
- Property 4 -- live re-read, never cached (3): mutate the fake project's
  underlying XML between two calls on the *same* project object and
  assert the second call observes the flip; a `read_count` counter on
  the fake `ActiveParser` property additionally asserts the live getter
  was touched again (catches a cache that stores the resolved string,
  not just one that stores the verdict); a third test flips back
  XAmple->HC to catch a cache that only "sticks" in one direction.

**Live-re-read construction:** `_ActiveParserSource.ActiveParser` is a
Python `@property` that increments `read_count` and recomputes on every
access (never memoized) from a mutable `_xml`/`_forced_value`. A
per-session cache keyed on the project would (a) return the stale verdict,
failing `pytest.raises`/`is None` directly, and (b) leave `read_count`
flat, which is asserted explicitly -- so a cache subtle enough to still
re-derive the correct verdict some other way is still caught.

Asserted every refusal through `validate_detail()` (never
`ParserEngineMismatchDetail(**...)` directly), matching T006.

**Design assumption, flagged as ambiguity:** the contract/SPEC pin
`check_active_parser(project, supported_engines=("HC",)) -> None, raising
parser_engine_mismatch` but not the exact Python signalling mechanism.
This file assumes a dedicated `ParserEngineMismatchError` exception with a
`.detail` dict matching the contract shape (mirroring T006/T007's own
documented invented-seam pattern). If T024 raises differently, the fix is
a mechanical rename here, not a design change.

**Fixture note:** none -- `PARSER_PARAMETERS_XML_CORRUPT`'s own docstring
already states the intended assertion (resolves to XAmple, not "parsing
raises"), which this file follows directly.

**Results:** `test_parser_engine_gate.py` alone: 4 passed, 16 failed (all
`ImportError` on `check_active_parser`, expected RED). `ruff check`: clean.
Full suite: 1456 passed, 8 skipped, 36 subtests passed, 72 failed (vs.
baseline 1437 passed/8 skipped/36 subtests) -- delta is +16 failed (mine,
RED) + 37 failed (`test_parser_health_block.py`, T008's own in-flight RED,
unchanged by me) + 19 failed (`test_grammar_scan_checks.py`, pre-existing,
confirmed by running it in isolation -- unrelated to this change). No
regression in previously-passing tests.
