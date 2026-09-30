# Cycle 2 Doc Report

**Trigger:** lead's cycle-2 dispatch, writing the contract/spec record for
Delta 6 (diagnostic levels report their result) and Delta 7 (narrow analysis
signature, spec-only) ahead of parallel implementation.

## Files touched

- `specs/parser-check-cp2b/spec.md:170-280` -- new **Delta 6** (`:170-237`)
  and **Delta 7** (`:239-280`), following the Delta 1-5 pattern.
- `specs/parser-check-cp2b/contracts/tools.md`:
  - `:122-140` -- new per-level result-field table + `parse_error` paragraph
    under `flextools_try_word`'s Output section (`### Output` at `:117`).
  - `:189-206` -- new `result_summary` table under `flextools_parse_status`'s
    Output section (`### Output` at `:178`).
  - `:242-262` -- new "Which of the four rows Delta 6 touches" subsection
    under Contract-document obligations.
- `specs/parser-check-cp2b/evidence/cp2b-evidence.md:690-716` -- new
  "Pattern audit -- 'truth-test on a key a code path never sets'" section,
  quoting cycle1-qc-pattern-audit.md section 3 verbatim, inserted before
  `## US3`.
- `CHANGELOG.md:37-52` -- new paragraph under the existing `[Unreleased]` /
  "Tool contract" heading.
- `docs/TOOL-CONTRACT.md:255-296` -- new "Parser diagnostic-level result
  fields" section, inserted before "Inherited member fields". Error-code
  count at `:69` (now shifted a few lines by the earlier edit but unchanged
  in content) was **not** touched.

All edits confirmed against current source before writing: `worker_main.py`
lines 728/732/754-785, `handlers/parse.py` lines 465/513-558/776-789/881-901
were re-read this cycle and match every citation above and in the source
reviews.

## Inconsistencies found, not smoothed over

1. **Line-number drift between the archivist's report and current source.**
   The archivist cites `_inline_response` at `parse.py:508-531`; the file at
   HEAD has it at `:513-558`. Likely a small edit landed between cycle 1 and
   now (or the archivist counted a slightly different revision). Content
   matches exactly; only offsets moved. Not fixed in the archivist's file
   (out of scope -- that's a review artifact, not a live doc) but flagged
   here so cycle 2's line numbers (which I re-verified against current HEAD)
   are the ones to trust.

2. **"Piece 1" is used with two different referents across sources.** The
   archivist's report (part D) uses "piece 1" for the *already-shipped*
   plain-level count (no delta needed) and "piece 2" for the narrow
   signature (which the archivist itself labels "Delta 6"). The lead's
   dispatch prompt renumbers: my Delta 6 is the domain review's
   explain/restricted honesty gap (a topic the archivist's report never
   discusses at all), and my Delta 7 is the archivist's "piece 2"/"Delta 6"
   renamed. The obligations-table instruction ("mark which of the four rows
   piece 1 touches") reads as referring to *my* Delta 6, not the
   archivist's "piece 1" -- I followed that reading since the archivist's
   actual piece 1 needs zero file changes by their own account, which would
   make the instruction a no-op. Recorded rather than silently reconciled,
   since a future reader comparing the two documents by "piece 1" alone
   will find them disagreeing.

## Not done (explicitly out of scope this cycle)

No `src/` or `tests/` edits (owned by the parallel agent). No commit.
