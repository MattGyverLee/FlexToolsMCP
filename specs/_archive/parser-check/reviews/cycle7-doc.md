# Cycle 7 -- Doc Agent Report (T004, T005)

**Date:** 2026-09-16
**Trigger:** T004/T005 dispatch, specs/parser-check/tasks.md lines 47-48

## Edits made

### docs/TOOL-CONTRACT.md
- Line 69: `one of the 18 codes below` -> `one of the 22 codes below`.
- After the `runtime_error` row (was line 116, table now runs one row longer),
  appended four rows in the order requested: `parser_engine_mismatch`,
  `parser_core_missing`, `parser_agent_missing`, `parser_tool_missing`.
  Field lists use the same backtick / `(list)` style as existing rows.
  Closed enums shown inline as parenthetical `\|`-separated alternatives
  (matches no exact precedent in the table, since no prior row has a
  multi-value closed enum, but follows the existing convention of
  parenthetical qualifiers like `project_not_found`'s `(default
  "list_projects")`).
  `parser_core_missing`'s `detected_version` field carries an inline clause:
  "reported and never compared: there is no version floor ... SPEC 16"
  per instruction.
- No version string touched; contract stays `tool-responses/1.0`.

### CHANGELOG.md
- Added a `### Tool contract` section under the (previously empty)
  `[Unreleased]` heading, prose paragraphs matching the 2.12.0 entries'
  voice. Covers: what each of the four codes refuses on; that the change is
  purely additive (`tool-responses/1.0` unchanged, no existing shape
  changes); the 18 -> 22 hand-maintained count bump; and that
  `parser_engine_mismatch` / `parser_agent_missing` ship as tested helpers
  with no live caller until CP2. No release number or date invented.

## "18" occurrences found

Grepped the whole file for `18` after the edit -- exactly the one occurrence
(line 69, the error-code count) existed before the edit, and it is now the
only place changed. No other stale "18" references (e.g. in prose counts
elsewhere in the file) were found.

## Ambiguities in error-codes.md

- `parser_core_missing`'s `signal` enum is described as "shared with the
  health block's `read.reason` / `write.reason`" but no inline value list is
  given there the way it is in the T004 dispatch prompt; I trusted the
  dispatch prompt's explicit enum list over re-deriving it from the four
  bullet points (`foreign_install`, `incompatible_surface`, `load_failed`
  are named; `absent` is implied but not explicitly walked through in prose).
- Row ordering/formatting for multi-value closed enums has no prior example
  in the table to match exactly; chose the most literal transcription.

## Files touched
- `D:\Github\_Projects\_LEX\FlexToolsMCP\docs\TOOL-CONTRACT.md`
- `D:\Github\_Projects\_LEX\FlexToolsMCP\CHANGELOG.md`

Not touched: `src\flextoolsmcp\server\response_models.py` (per instruction).

---
**Doc Agent:** /lex-doc
