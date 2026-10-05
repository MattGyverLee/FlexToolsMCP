# after_implement QC gate (lex-qc), 2026-09-30

Scope: `e092fe3..40d8e55`. Saved by the main session; the reviewer's tools
were read-only. The reviewer read the final files but could not run git or
the tests.

**Score 84/100. Status: ISSUES.**

## BLOCKING

- **B1: live-LCM evidence missing.** This is a write-path change, and
  `evidence/live-gate.md` does not exist (T025 V5, T030 V7, T036 V1-V4/V6 not
  run). FieldWorks is closed and the steps need the maintainer, so this is
  `needs_human`, not a PASS. Merge is blocked until `live-gate.md` records
  `run_mode: live` (cross-checked with `tests/live_status.json`), the
  `FLEXLIBS_REQUIRE_LIVE=1` commands, pre/post values re-queried from LCM, and
  `zzExclTest` cleanup.
- **B2: confirm that the Pattern audit is in the commit body.** RESOLVED: the
  `b52a7de` body carries the "Pattern audit" section (line 29).

## Non-blocking

| # | Finding | Disposition |
|---|---|---|
| N1 | `exclusive_access.REFUSING_VERDICTS` (open_shared, unknown) and `write_ladder.REFUSING_VERDICTS` (open_exclusive, held_by_other) have opposite meanings, used on adjacent lines | **Fixed**: renamed to `GATED_VERDICTS` |
| N2 | `_raw_matches` is about 65 lines; lookup tables are rebuilt on every call | Deferred (cost is negligible; one AST walk per write-enabled run) |
| N3 | The gate re-certifies even when no auto-fix changed the code; no test covers auto-fix-then-refuse | Deferred: the re-certify is deliberate (deviation c). The test needs the real index plus the typo auto-fix path |
| N4 | `_exclusive_access_report` reports `required: False` on a syntax error | Accepted: syntax_error already fails validate_only |
| N5 | Evidence strings are built by concatenation | Cosmetic, left |
| N6 | `except Exception: pass` in the validate_only probe-unavailable branch | **Fixed**: now logs at debug level, like the branch above |
| N7 | With an empty `project_name`, no `exclusive_access` key is emitted | Consistent with the other probe fields; the data model says "present only when the probe ran" |
| - | The gate uses `probe_write_access`; validate_only uses `probe_project_access` | Same underlying probe today; noted |

## Deviations judged

All four were **accepted**:

- (a) untyped receivers do not match Create/Delete by name. Document the
  false negative as a known limit.
- (b) `blocking` is true on `unknown`.
- (c) re-certify after auto-fix.
- (d) every detail field has a default.

The docs should say why `project_lock.blocking` (null on `unknown`) and
`exclusive_access.blocking` (true) differ. That is covered in TOOL-CONTRACT.md:
"`blocking` is null only when the probe itself failed".
