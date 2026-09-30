# Cycle 7 -- Programmer report: T001 + T002 (Phase 1, Setup)

## Files created
- `src/flextoolsmcp/server/scan/__init__.py` -- package docstring only,
  `__all__ = []`. Notes that `grammar_scan_module.py` (T019) lands here
  later, runs in the FLExTools/IronPython subprocess (via
  `subprocess_helpers.py`), and is never imported by the MCP server
  process. No `pyproject.toml` edit (per instructions) -- `where=["src"]`
  auto-discovers it.
- `tests/fixtures/parser_check.py` -- three fixture groups per T002:
  (1) `FakeParserCoreLocation` dataclass + three instances (complete/
  same-install, missing `ParseFiler.ProcessParse`, foreign-directory)
  built from `HCPARSER_MEMBERS`/`PARSE_FILER_MEMBERS` tuples taken
  verbatim from SPEC 5.4's bound-positional member list; (2) three
  `ParserParameters` XML string constants (valid HC, valid XAmple,
  corrupt/unterminated); (3) `IMoForm`/`IPhPhoneme`/`IMoInflAffixSlot`/
  `IPhSegmentRule` stub dataclasses + factory functions, restricted to
  the properties research.md D4 marks VERIFIED.

## Decisions
- **XML schema is illustrative, not sourced.** No FieldWorks checkout is
  configured in `.env` (path commented out), so I could not confirm the
  literal `ParserParameters` XML shape against `OverridesLing_MoClasses.cs`.
  I modeled it on the one confirmed fragment the spec itself quotes
  (`<HC><MaxRoots>...`, SPEC.md:1493) and said so explicitly in the
  docstring, since only the HC/XAmple/corrupt-reads-as-XAmple
  distinction is contractually load-bearing at CP1, not the exact tag
  names.
- **IPhPhoneme attributes**: T002's line names `IPhPhoneme` with no
  attribute called out (unlike the other three). I added `CodesOS` and
  `FeaturesOA` since those are the *only* two IPhPhoneme properties this
  spec has verified anywhere (research.md D4 rows 2, 9) -- leaving the
  stub attribute-free would make it unusable by anything, and this isn't
  inventing new scope, just completing what T002 named.
- **Import convention -- chose `from fixtures.parser_check import ...`,
  not `tests.fixtures.parser_check`.** Verified empirically (as
  instructed) with a throwaway `python -c` and a throwaway collected test
  file. Surprise: `import tests` on this machine resolves to an unrelated
  repo (`d:\github\word2html\pub\tests\__init__.py`) that shadows a local
  `tests` namespace package entirely -- so the dotted form is unsafe here
  and, more importantly, would be a latent trap for anyone else with a
  same-named package on `sys.path`. `fixtures.parser_check` has no such
  collision and matches pytest's own rootdir "prepend" sys.path insertion
  for files directly under `tests/` (no `__init__.py` needed anywhere,
  consistent with the existing `tests/` tree).

## Verification
- `python -m pytest tests/ -q -x --collect-only` -- 1406 tests collected,
  no errors.
- Fixture module imports and factory functions run correctly under
  pytest's real import path (not just manual `sys.path` hacking).

No `pyproject.toml`, `tests/__init__.py`, or `tests/fixtures/__init__.py`
changes were needed or made.
