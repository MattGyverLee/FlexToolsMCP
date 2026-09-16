# Cycle 7 -- T003 report (response_models.py)

## What landed

Added four `extra="forbid"` detail models to
`src/flextoolsmcp/server/response_models.py`, inserted after
`HvoLiteralWriteRiskDetail` and before the `AnyDetail` union block:
`ParserEngineMismatchDetail`, `ParserCoreMissingDetail`,
`ParserAgentMissingDetail`, `ParserToolMissingDetail`. Field names and types
copied verbatim from `contracts/error-codes.md`. The three closed enums
(`signal`, `probe_source`, `component`) and `agent_name` are `Literal`s with
the exact members from the contract, unmodified. Nullable fields
(`detected_version`, `lcmodel_install_path`, `load_error`) use
`Optional[str] = None` per the surrounding file's convention; fields the
contract lists without "or null" (`configured_engine`, `supported_engines`,
`missing_members`, etc.) are left required, no default, matching how other
required-looking list fields in this file are sometimes defaulted but the
contract here gives no such signal -- treated `missing_members` as required
rather than defaulting to `[]`, since CP1 doesn't specify it's optional.

## Exact edit locations

- `AnyDetail` Union extended at lines 480-484 (the four new models appended
  after `HvoLiteralWriteRiskDetail`).
- Module docstring count bumped 18 -> 22 at line 10 (arithmetic note now
  reads "12 existing + 4 folded in + nested_unit_of_work +
  hvo_literal_write_risk + 4 parser-check CP1 codes").
- Section-comment count bumped 18 -> 22 at line 423 ("Discriminated union
  over all 22 per-code detail models") -- this was a third hand-maintained
  "18" the task prompt didn't name explicitly but the grep sweep caught.
- `validate_detail()` docstring count bumped 18 -> 22 at line 491.
- `grep -n "18"` on the file now returns zero hits.

## Suite result

`python -m pytest tests/ -q`: **1398 passed, 8 skipped**, 23 warnings
(pre-existing `ast.Str` deprecation noise in
`flexicon_analyzer.py:211`, unrelated), 36 subtests passed. No failures.

## Ambiguity in the contract

`error-codes.md` gives types (`str`, `list[str]`, `str or null`) but no
JSON examples and no explicit required/optional marking beyond "or null".
I treated every field without "or null" as required (no default), which is
stricter than several sibling models in this file that default lists to
`[]` even when arguably required. If T006's contract examples always supply
every field, this is moot; if a caller ever wants to omit e.g.
`missing_members`, this will need a `Field(default_factory=list)` follow-up.
Did not touch `docs/TOOL-CONTRACT.md` or `CHANGELOG.md` (T004/T005) or write
`tests/test_parser_error_models.py` (T006).
