# Cycle 4 -- LEX Programmer implementation report (CP2)

Checkpoint: **CP2 -- Reconstruction + normalization** (tasks.md lines 42-73).
Branch: `feat/diagnostic-report-cp1` (continued, not renamed). Repo root:
`D:\Github\_Projects\_LEX\FlexToolsMCP`.

## Files added

- `src/flextoolsmcp/server/diagnostic/reconstruct.py` -- slice reconstruction
  (spec sections 3, 5), rotation stitching (resolved Q3), `MAX_REPORT_OPS`
  (module constant, default 12) summarize-not-drop. Public surface:
  `SliceOp`, `ReportSlice`, `resolve_slice_records()`,
  `apply_max_report_ops()`, `rotation_file_candidates()`,
  `parse_log_text()`, `stitch_and_extract_blocks()`, `reconstruct_slice()`
  (top-level orchestrator).
- `src/flextoolsmcp/server/diagnostic/normalize.py` -- path-scoped
  machine-hygiene normalization (spec section 8.3 / decision E2, NORMATIVE).
  Public surface: `get_home_path()`, `get_username()`,
  `normalize_report_text()`.
- `src/flextoolsmcp/server/diagnostic/render.py` -- seven-part report
  rendering (spec section 7). Public surface: `render_report()`.
- `tests/test_diagnostic_report_reconstruction.py` -- 23 new tests (see
  below).

## Files changed

- `src/flextoolsmcp/server/diagnostic/__init__.py` -- package docstring
  updated to describe CP2's new sibling modules and the `triggers.py`
  addition; no behavior change.
- `src/flextoolsmcp/server/diagnostic/triggers.py` -- added
  `compute_casting_signature(issues) -> str` (CP2 precision fix, see below).
  Added `import hashlib`. No changes to existing trigger-predicate logic;
  `casting_recurrence_signature()` was already CP1-forward-compatible
  (already preferred an explicit `casting_signature` field before falling
  back to `preflight_gate`), so this task was "populate the field for
  real," not "rewrite the dispatch."
- `src/flextoolsmcp/server/handlers/op_telemetry.py` -- `_write_jsonl_line()`
  gained an optional `casting_signature: Optional[str] = None` kwarg,
  persisted as `record["casting_signature"] = casting_signature or ""`.
  Docstring updated to explain the backward-compat story.
- `src/flextoolsmcp/server/handlers/execution.py` -- (a) new import of
  `compute_casting_signature` from `..diagnostic.triggers` (one-way:
  execution.py -> diagnostic, never the reverse -- diagnostic package stays
  transmission-free, see guard note below); (b) `_log_preflight_reject()`
  gained an optional keyword-only `casting_signature` param threaded to
  `_write_jsonl_line`; (c) the actual `casting_issues_detected` preflight-
  reject call site (~line 2101-2113, inside `handle_run_module`) now computes
  `_casting_sig = compute_casting_signature(issues)` from the real
  `casting_check["casting_issues"]` list and passes it through. This is the
  ONLY call site that ever sets `preflight_gate="casting_issues_detected"`,
  confirmed via grep before editing.

**Not touched** (per instructions -- pre-existing uncommitted, unrelated
working-tree changes): `src/flextoolsmcp/server/validators.py`,
`tests/test_validator_cluster_fixes.py`. Verified via `git status` before
and after: both still show only their original diff, no new hunks from me.

## JSONL schema delta

One new field, additive and backward compatible:

```json
{
  "...": "...(unchanged CP1 fields)...",
  "casting_signature": ""   // NEW -- "" when absent/not-applicable
}
```

- Only ever non-empty on a `casting_issues_detected` preflight-reject close;
  every other close path passes `casting_signature=None` implicitly (kwarg
  default), which serializes to `""`.
- Old JSONL lines written before this change simply lack the key entirely
  on `json.loads()` -- `record.get("casting_signature")` returns `None`,
  and `triggers.casting_recurrence_signature()` already treats that as "no
  explicit signature, fall through to `preflight_gate`" (CP1 code,
  unchanged). No migration needed; verified with a dedicated regression
  test (`test_old_jsonl_records_without_casting_signature_field_still_work`).

## Casting-recurrence precision fix (deferred cycle-2 QC P1)

Root cause confirmed by grep + read: `preflight_gate` on a casting reject is
**always** the literal string `"casting_issues_detected"` (same value
`_log_preflight_reject` receives as `reason_code`, which becomes both
`error_code` and `preflight_gate`) -- it never varied per-issue. So the CP1
fallback chain (`casting_signature` -> `preflight_gate` -> bare code) always
bottomed out at an identical value for every casting reject, meaning **any**
two same-turn casting rejects looked like a recurrence of each other,
regardless of whether they were actually the same underlying bug.

Fix: `triggers.compute_casting_signature(issues)` builds a deterministic,
order-independent signature from the real `detect_casting_needs()` output
(`property` + sorted `missing_on` + `cast_interface`, SHA256-hashed,
truncated to 16 hex chars), computed at the actual reject call site in
`execution.py` and threaded into the JSONL record. Once populated,
`casting_recurrence_signature()` (unchanged) prefers this real value, so
two ops whose casting issues name *different* properties/interfaces no
longer collapse into a false recurrence, while two attempts at the *same*
property/interface still correctly recur.

## E2 anchor (path-scoped normalization)

`normalize.normalize_report_text()` is deliberately safe to run over an
**entire** rendered report body (not just hand-picked "safe" lines) because
protection is structural, not selective-scoping:

1. `_PATH_TOKEN_RE` only matches genuine path-shaped substrings: a
   drive-letter absolute path (`C:\...`), a UNC path (`\\server\...`), or a
   POSIX path rooted at `/home`, `/Users`, or `/root`. Ordinary prose (a
   gloss like "Matthew's toolbox") never matches this regex at all -- it
   has no drive letter, no UNC prefix, and isn't rooted under a recognized
   home directory.
2. Within a matched token, the home-dir prefix is replaced with `~` only
   via a **full prefix compare with a segment-boundary check** (the
   character immediately after the prefix match must be a separator or
   end-of-string) -- this also fixed a real bug I caught in my own first
   draft: without the boundary check, home dir `C:\Users\matt` would
   wrongly prefix-match an unrelated sibling directory
   `C:\Users\matthew\...` (different user, same string prefix). Covered by
   `test_e2_sibling_directory_not_falsely_prefix_matched`.
3. The username substitution operates on whole **path segments** (split on
   `\`/`/`), requiring an exact case-insensitive segment match -- never a
   substring "contains" check. So even inside a real path token, "Matthew's"
   as a segment never equals "matt".

Net effect: lexical collisions are protected twice over (regex doesn't even
consider non-path-shaped text; segment-exact matching doesn't fire on
partial overlaps even inside real paths). This is NOT a document-wide
find/replace at any point in the implementation -- there is no `str.replace`
or blanket `re.sub` of the bare username/home-path string anywhere in
`normalize.py`.

Acceptance-mapped tests: `test_e2_username_substring_in_lexical_data_survives`
(the literal §12 case: gloss "Matthew's toolbox" survives, path token
normalized), `test_e2_document_wide_replace_would_have_failed_this_test`
(sanity check proving the fixture is meaningful -- a case-insensitive naive
replace WOULD corrupt it), `test_e2_sibling_directory_not_falsely_prefix_matched`,
`test_e2_username_segment_removed_outside_home_dir`,
`test_e2_normalize_is_noop_on_text_with_no_path_tokens`.

## Reconstruction design notes

- **Rotation stitching is JSONL-driven** (resolved Q3): `reconstruct_slice()`
  always resolves the target op_id list from JSONL records FIRST, then
  calls `stitch_and_extract_blocks()`, which concatenates
  `.log.3, .log.2, .log.1, .log` (only the ones that exist) in true
  chronological order (oldest -> newest) into one virtual text stream
  before block-parsing. This correctly reconstructs an operation block that
  straddles a rotation boundary (Start in an older file, End in a newer
  one) without any file-boundary-aware special-casing -- proven by
  `test_rotation_stitch_across_log_and_backups`, which deliberately splits
  one op's block mid-stream across `.log.1` and the base file.
- **Recycled-op truncation is never silent**: if a requested op_id's Start
  marker cannot be found anywhere in the available rotation files,
  `ReportSlice.rotation_truncated` lists it explicitly, and
  `render.render_report()` emits a `"History truncated by rotation:"` note
  naming the op_id(s) -- covered by
  `test_rotation_recycled_op_is_flagged_not_silently_omitted`.
- **Turn boundary reuses `op_telemetry.group_records_by_intent()`
  unchanged** (decision E7) -- `resolve_slice_records()` imports it
  directly rather than reimplementing grouping, so report slice boundaries
  stay identical to the shipped green-rate/turns-to-green analytics.
- **`MAX_REPORT_OPS` summarize-not-drop**: `apply_max_report_ops()` keeps
  the most recent `cap` (default 12) records verbatim and summarizes older
  excess into `{op_id, seq, outcome, error_code, one_line}` dicts -- nothing
  is dropped from the appendix either: `ReportSlice.turn_records` always
  carries the FULL uncapped resolved slice for the JSONL appendix (section
  7), independent of the `ops` list's cap.
- Session-log lines are stripped of the
  `'%(asctime)s | %(levelname)-7s | %(message)s'` logging-formatter prefix
  at parse time (`_strip_log_prefix`), so `render.py` works with clean
  message content.
- The one-time `=== Session Environment ===` block (emitted by
  `kernel._emit_session_header()`) is captured verbatim during parsing and
  used directly for the Header section, rather than re-deriving versions --
  consistent with "session log is the primary source" (spec section 3.2).

## Test names + counts

New file `tests/test_diagnostic_report_reconstruction.py` -- **23 tests**,
all passing:

- Reconstruction/join: `test_reconstruct_joins_jsonl_to_log_blocks_by_op_id`,
  `test_reconstruct_defaults_to_whole_turn_via_user_intent_grouping`,
  `test_reconstruct_steps_back_and_explicit_op_ids`
- Rotation stitching: `test_rotation_stitch_across_log_and_backups`,
  `test_rotation_recycled_op_is_flagged_not_silently_omitted`
- MAX_REPORT_OPS: `test_apply_max_report_ops_summarizes_excess_not_drops`,
  `test_max_report_ops_under_cap_returns_unchanged`,
  `test_max_report_ops_is_a_module_constant`,
  `test_render_surfaces_truncation_summary_not_silent_drop`
- E2 normalization: `test_e2_username_substring_in_lexical_data_survives`,
  `test_e2_document_wide_replace_would_have_failed_this_test`,
  `test_e2_sibling_directory_not_falsely_prefix_matched`,
  `test_e2_username_segment_removed_outside_home_dir`,
  `test_e2_normalize_is_noop_on_text_with_no_path_tokens`
- Seven-section render: `test_render_report_has_all_seven_sections_in_order`,
  `test_render_abandoned_turn_notes_no_resolution`
- Casting-recurrence precision (CP2 regression):
  `test_compute_casting_signature_differs_for_unrelated_issues`,
  `test_compute_casting_signature_stable_for_same_issue_reordered`,
  `test_two_unrelated_casting_issues_in_same_turn_no_longer_collapse`,
  `test_two_same_casting_issue_attempts_do_recur_with_real_signature`,
  `test_old_jsonl_records_without_casting_signature_field_still_work`,
  `test_casting_signature_round_trips_into_jsonl_record`,
  `test_casting_signature_defaults_to_empty_string_when_not_passed`

Full-suite run: **510 passed** (487 baseline + 23 new), no regressions,
`tests/test_diagnostic_report_foundation.py` (37 CP1 tests) still green
unmodified.

Informal AST scan (ahead of the CP3-scheduled formal build guard): walked
every module under `server/diagnostic/` for `subprocess`, `smtplib`,
`webbrowser`, `urllib`, `requests`, `http`, `socket` imports -- zero hits.
Correction (cycle-6): this originally read "only one new import, never
diagnostic->handlers," which was incomplete. There are in fact **two** new
cross-package imports touching this package, both intra-repo and pure-function
(no I/O/network), so the no-transmission acceptance criterion still holds:
`execution.py` -> `diagnostic.triggers` (`compute_casting_signature`), and
`reconstruct.py:43` -> `handlers.op_telemetry` (`group_records_by_intent`),
i.e. one `diagnostic -> handlers` import DOES exist. See
`reviews/cycle5-lex-verification.md` for the discrepancy this corrects.

## Deviations from the brief / risks for reviewers

1. **MAX_REPORT_OPS truncation direction is a judgment call.** The spec
   (section 5) doesn't specify *which* excess ops get summarized when a
   slice exceeds the cap -- only that none may be silently dropped. I chose
   "keep the most recent `cap` ops verbatim, summarize the earlier ones,"
   reasoning that the failure and its resolution (both near the end of a
   turn) matter most for reproduction, and earlier discovery/setup steps
   compress well into a one-liner. If the maintainer's mental model is
   different (e.g., "always keep the anchor +/- N regardless of position"),
   this is the one place to push back -- the cap/summarize *mechanism* is
   solid, the *selection policy* is the part I made a call on.
2. **Header section relies on the session log's own environment block**
   rather than recomputing versions independently. If a requested slice's
   rotation window doesn't include that one-time block (e.g. a very long
   session with many rotations since the header was written and
   `backupCount` has recycled it), the Header section falls back to
   `"(session environment block not available in this log slice -- possibly
   recycled by rotation)"` rather than silently guessing. This seemed more
   honest than re-deriving versions out-of-band (which could disagree with
   what was actually running at incident time), but it does mean very old
   incidents in long sessions may render a header-less bundle. Flagging for
   awareness, not proposing a change without direction.
3. **`flextools_start` args recovery is best-effort.** The Request section's
   `flextools_start` args come from whatever `[TOOL CALL]`/`[TOOL ARGS]`
   pair happened to precede the FIRST op in the resolved slice. If a turn's
   `flextools_start` call is further back than the slice's start boundary
   (e.g. an explicit `op_ids`/`steps_back` selection that starts mid-turn),
   the Request section just omits the `flextools_start` args line rather
   than reaching further back to find it. This matches the "reconstruction
   only extends as far as the resolved slice" principle but is worth a
   reviewer's eyes.
4. **CP3 dependency**: `render_report()` returns a markdown string only --
   no file write, no transport wiring. That is explicitly CP3 scope per the
   brief; not implemented here, and correctly excluded from this
   checkpoint's tests.
5. Kept the diagnostic package's existing style (module-constant caps,
   dataclasses, pure functions, injectable paths for testability) rather
   than introducing new patterns, to stay consistent with the CP1 modules
   reviewers already approved.
