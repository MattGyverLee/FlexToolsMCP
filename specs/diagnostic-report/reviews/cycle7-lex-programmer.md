# CP3 implementation report -- "Surface + transport + guard"

Spec: `specs/diagnostic-report/SPEC.md` sections 8, 9, 10, 12. Tasks:
`specs/diagnostic-report/tasks.md` "CP3" + "CP2 carryover (P2)". Landed on
top of CP1/CP2 (511-test baseline).

## Summary

All 5 CP3 line-items + both CP2 carryover P2 fixes implemented. Full suite:
**577 passed / 0 failed** (511 baseline + 66 new tests, no regressions).
No contract version bump (`tool-responses/1.0` unchanged, per resolved Q5).

## New files

- `src/flextoolsmcp/server/diagnostic/transports.py` -- pure string/argv
  builders for the three transports (spec section 9): `build_gh_command`
  (exact `gh issue create` argv), `build_github_issue_url` (percent-encoded,
  <=8KB total), `build_mailto`, and `build_transports()` orchestrating all
  three. `default_gh_available()` checks `shutil.which("gh")` only --
  never invokes `gh`. `gh_available_fn` is injectable throughout (decision
  E6).
- `src/flextoolsmcp/server/diagnostic/sensitivity.py` -- `detect_lexical_shape()`
  (AST-based) and `likely_contains_lexical_data(slice_obj)` implementing
  resolved Q4: fires on (a) a lexical accessor's result flowing into
  `report.Info(...)` (direct call, attribute access, or via a simple local
  variable), or (b) a BCP-47-shaped string literal (regex on the literal's
  *shape*, not lexical content) alongside a lexical accessor reference
  anywhere in the same code. Reuses `render._extract_code_block()` so both
  modules agree on the code boundary.
- `src/flextoolsmcp/server/handlers/diagnostic_report.py` -- the
  `flextools_prepare_report` tool handler (`handle_prepare_report`) plus
  the shared orchestration `prepare_report_bundle()` (reconstruct -> anchor
  selection -> signature -> [offer_gate] -> render -> write ONE local file
  -> transports -> sensitivity) and `build_advisory_for_success_close(op_id)`
  (the run_module success-close hook, fail-open by contract). Deliberately
  NOT inside `server/diagnostic/` (it does real file I/O: reads
  operations.jsonl / the session log, writes the report file) but is
  explicitly in scope for the no-transmission guard.
- `tests/test_diagnostic_no_transmission.py` -- the two-layer guard (16
  tests): static AST scan of every `diagnostic/*.py` module + the handler,
  scan-coverage sanity check, "strings may contain gh/mailto" guard against
  over-fixing, and 4 dynamic monkeypatch-and-drive tests (gh-present,
  gh-absent, mailto branch, full `flextools_prepare_report` tool end-to-end)
  asserting zero banned invocations and exactly one local file write each.
- `tests/test_diagnostic_report_transport.py` -- 46 tests: `transports.py`
  (gh argv exact shape, custom repo/label, display-string quoting,
  `gh_available` injectability, URL validity/percent-encoding/8KB cap,
  mailto shape/cap/"works with neither present", preview-fidelity: all
  three simultaneously); `sensitivity.py` (10 shape-detection cases,
  positive and negative, plus syntax-error/empty-code safety); `
  prepare_report_bundle` (anchor selection, exactly-one-file-write,
  markdown/file parity, `offer_gate` true/false, lexical-flag present/
  absent, stable fallback signature on an all-green slice); config knobs
  (`report_offers_enabled` default-on + kill switch);
  `build_advisory_for_success_close` (fires on workaround-taken turn, no-op
  on all-`ok` turn, `dont_ask_again` dedupe + report file persists after
  suppression, fail-open on internal exception); explicit
  `flextools_prepare_report` bypassing dedupe entirely; `RunModuleSuccess`
  accepting/defaulting the new field; and a full wiring test driving two
  real `handle_run_module()` calls (fail then ok, same turn) confirming the
  advisory is attached to the *resolving* success response, and a
  companion test confirming no advisory on an all-green turn.

## Modified files

- `src/flextoolsmcp/server/diagnostic/reconstruct.py` -- CP2 carryover P2
  fix: `parse_log_text()`'s mismatched-`End`-marker case no longer resets
  `current_op_id`/`current_lines` (which silently dropped every subsequent
  line until the block's real End, if any). It now keeps the block open and
  records the mismatch in a new `end_mismatches` list, threaded through
  `ReportSlice.end_mismatches`.
- `src/flextoolsmcp/server/diagnostic/render.py` -- CP2 carryover P2 fix:
  `_CODE_STOP_MARKERS` matching changed from `marker in line` (unanchored
  substring) to `stripped_line.startswith(marker)` via new
  `_is_code_stop_marker()`, since every genuine stop line is logger-emitted
  at column 0. Also renders `end_mismatches` as a "Log parse warning" note
  under "What was tried".
- `src/flextoolsmcp/server/diagnostic/__init__.py` -- CP3 docstring update.
- `src/flextoolsmcp/server/kernel.py` -- added `get_current_session_log_path()`
  (reads the live per-session `RotatingFileHandler.baseFilename` off
  `operations_logger`, skipping the cross-session handler via the existing
  `_CROSS_SESSION_HANDLER_FLAG`).
- `src/flextoolsmcp/config.py` -- added `REPORT_OFFERS_ENABLED_KEY/DEFAULT`
  (default `True`), `REPORT_REPO_KEY/DEFAULT`
  (`MattGyverLee/FlexToolsMCP`), `REPORT_EMAIL_KEY/DEFAULT`
  (`matthew_lee@sil.org`) -- same `config_get(key, default)` pattern as
  `AUTO_FIX_ENABLED_KEY`.
- `src/flextoolsmcp/server/response_keys.py` -- added `KEY_DIAGNOSTIC_REPORT
  = "diagnostic_report"`.
- `src/flextoolsmcp/server/response_models.py` -- added `diagnostic_report:
  Optional[Dict[str, Any]] = None` to `RunModuleSuccess`, same additive
  pattern as the #46/#47 fields; no contract bump.
- `src/flextoolsmcp/server/models.py` -- added `PrepareReportInput`
  (`op_id`, `op_ids`, `steps_back`, `include_from_op_id`).
- `src/flextoolsmcp/server/tool_definitions.py` -- registered
  `flextools_prepare_report` (annotations: `readOnlyHint=False` since it
  writes a local file; `idempotentHint=False` since each call writes a new
  timestamped file).
- `src/flextoolsmcp/server/dispatch.py` -- wired
  `TOOL_PREPARE_REPORT`/`handle_prepare_report`/`PrepareReportInput` into
  `ALL_TOOL_NAMES` and `DISPATCH_ROUTES`.
- `src/flextoolsmcp/server/handlers/execution.py` -- imports
  `build_advisory_for_success_close`; calls it at the success-close site
  (after the #47 auto-discovery attach) and attaches the result under
  `KEY_DIAGNOSTIC_REPORT` when non-`None`. No try/except needed at the call
  site since the function is fail-open by contract.
- `tests/test_diagnostic_report_reconstruction.py` -- 4 new regression
  tests for the two CP2 carryover P2 fixes.
- `tests/test_mcp_tools.py` -- added `flextools_prepare_report` to
  `EXPECTED_TOOL_NAMES` (pre-existing test, legitimately needed updating;
  NOT added to `READ_ONLY_TOOLS` since the tool writes a local file).

## Design resolution worth flagging: where the advisory actually attaches

Spec section 6.1 predicate fires on `runtime_fail` / `invalid_api_chain` /
casting-recurrence -- all of which are **non-success** closes (they return
through the rejection/failure paths, not `RunModuleSuccess`). Per section
6.2 ("workaround-taken signal") and section 6.5, the advisory is meant to
surface on the **resolving** `ok` close of the same turn, not on the
failing close itself (which can't carry a `RunModuleSuccess` field at all).
`build_advisory_for_success_close(op_id)` therefore: locates the turn
containing the just-closed `ok` op via `group_records_by_intent`, checks
`triggers.find_reportable_closes()` over that turn, and -- only if a
reportable failure exists earlier in the same turn -- builds the bundle
and attaches it to *this* success response. This matches the task
prompt's intent ("fires for the just-closed op") in spirit while being
literally accurate to how the trigger predicate and the envelope type
actually compose.

`report_path` is included in the advisory (spec section 10 lists it
explicitly) even though the orchestrator-prompt line-item text omitted it;
transports (especially `gh --body-file <report_path>`) inherently need it,
so this reads as an elision rather than an intentional exclusion.

## Two-layer no-transmission guard

- **Static**: `tests/test_diagnostic_no_transmission.py` AST-parses every
  `.py` file in `server/diagnostic/` plus `handlers/diagnostic_report.py`
  and fails on any `import`/`from` of `subprocess`, `smtplib`, `webbrowser`,
  `socket`, `requests`, `http`, or the network-capable `urllib.request`/
  `urllib.error`/`http.client` submodules (deliberately NOT the whole
  `urllib` root, since `transports.py` legitimately uses `urllib.parse` for
  percent-encoding -- pure string encoding, no network capability), plus
  `os.system`/`os.popen`/`webbrowser.open` call-site checks.
- **Dynamic**: monkeypatches `subprocess.*`, `os.system/popen`,
  `smtplib.SMTP*`, `webbrowser.open`, `urllib.request.urlopen` to raise, then
  drives `prepare_report_bundle` (gh-present, gh-absent) and the real
  `flextools_prepare_report` tool end-to-end, asserting zero invocations and
  exactly one `Path.write_text` call per prepared report. `socket.socket`
  is deliberately **not** globally patched -- on Windows, `asyncio.run()`
  itself creates an internal loopback socketpair for its self-pipe, so a
  blanket patch broke the test harness, not the code under test. The static
  scan already fully bans `import socket` anywhere in the guarded tree, so
  the dynamic layer's remaining coverage (subprocess/smtplib/webbrowser/
  urllib.request) plus the write-count assertion still catches any genuine
  violation without fighting the async runtime.

## Deviations from the literal prompt text

1. `report_path` included in the auto-offer advisory (see above) -- spec
   §10 requires it; the prompt's item-4 bullet list omitted it.
2. `socket.socket` excluded from the dynamic monkeypatch set for the reason
   above; the static scan covers `socket` fully instead.
3. Filenames use `report_<ts>.md` with a microsecond-resolution timestamp
   (`YYYYMMDDTHHMMSSssssssZ`) rather than second-resolution, to avoid
   filename collisions when multiple reports are prepared within the same
   wall-clock second (relevant in tests and in rapid-retry sessions).
4. `_extract_failing_symbol()` (best-effort `has no attribute 'X'` regex
   over the anchor op's raw log lines) is a v1 heuristic, documented inline
   the same way CP1's `casting_recurrence_signature()` fallback was --
   sufficient to sharpen the runtime-fail signature beyond
   `(exception_class, "")` when a polymorphic-attribute traceback line is
   present in the slice; falls back gracefully to an empty symbol
   otherwise (never raises, never blocks the pipeline).

## Full-suite result

```
577 passed in ~41s
```
(baseline 511 + 66 new: 16 in `test_diagnostic_no_transmission.py`, 46 in
`test_diagnostic_report_transport.py`, 4 in
`test_diagnostic_report_reconstruction.py`). Zero failures, zero
regressions in any pre-existing test (including `test_mcp_tools.py` once
`EXPECTED_TOOL_NAMES` was updated for the new tool).

## Residual concerns / follow-ups for CP4 or later

- `docs/TOOL-CONTRACT.md` is not yet patched to document the
  `diagnostic_report` advisory block -- explicitly CP4 scope per
  `tasks.md`, not attempted here.
- `_extract_failing_symbol()` only recognizes the `"has no attribute 'X'"`
  shape; other exception classes (e.g. `KeyError`, `TypeError`) fall back to
  an empty symbol, which is safe (signature still keys on exception class)
  but coarser than it could be. Worth revisiting if runtime_fail dedupe
  granularity becomes a real-world pain point.
- The auto-offer advisory intentionally omits `report_markdown` (the full
  rendered text) to keep the `RunModuleSuccess` payload light; Claude can
  read `report_path` directly or call `flextools_prepare_report` for the
  inline markdown. Flagging in case the crew wants the advisory to carry
  the full text too for a single-round-trip preview.
- `flextools_prepare_report`'s `annotations.idempotentHint=False` because
  each call mints a new timestamped file; if a caller retries the exact
  same request expecting deduped output, they'll get N files. This matches
  the "always full-fidelity, no auto-scrubbing, no auto-dedup-of-explicit-
  requests" spirit of spec section 5, but worth confirming with product
  intent if it becomes noisy.

## Unrelated pre-existing changes (not touched)

`src/flextoolsmcp/server/validators.py` and
`tests/test_validator_cluster_fixes.py` were already modified in the
working tree before this task started (per the task briefing) and were
left untouched throughout this implementation.
