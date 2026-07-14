# Diagnostic-report feature: checkpoint plan

Durable spurt plan for the "send this to the maintainer" flow. Spec:
[`SPEC.md`](SPEC.md) (status APPROVED-WITH-EDITS). Each checkpoint is a
bounded spurt; check off tasks as they land and update the "Checkpoint:"
line with the commit/PR that closed it.

## CP1 -- Foundation

- [x] `user_request` plumbing (spec section 4): optional verbatim-text field
      on `flextools_start` (turn-level, `FlexToolsStartInput`) and
      `flextools_run_module` (optional mid-turn override, `RunModuleInput`);
      threaded through `execution._log_operation_start` /
      `_stash_op_start` / `op_telemetry._write_jsonl_line`; falls back to
      `user_intent` when absent, same "(not provided)" idiom.
- [x] Trigger predicate (spec section 6.1): fires on `outcome ==
      "runtime_fail"` (any exception class, excludes `timeout`),
      `error_code == "invalid_api_chain"`, and
      `error_code == "casting_issues_detected"` on recurrence only; the 13
      explicitly non-reportable codes never fire.
- [x] Inferred workaround signal (spec section 6.2): reportable failure
      followed by a same-turn `outcome == "ok"` close.
- [x] Code-independent signature (spec section 6.3): hash of
      `(exception-class, normalized failing symbol)` for runtime_fail, the
      normalized offending chain for `invalid_api_chain`, the recurring
      casting signature for casting recurrence. Never keys on
      `code_sha256`.
- [x] `offered.json` store (spec section 6.4):
      `~/.flextoolsmcp/reports/offered.json`, fail-open on corrupt/missing
      file, LRU prune by `last_seen` capped at 500 entries,
      `dont_ask_again` persists across restarts.
- [x] Unit tests: `tests/test_diagnostic_report_foundation.py`.

**Checkpoint:** CP1 landed 2026-07-13. Files: see
`specs/diagnostic-report/reviews/impl-cycle1-lex-programmer.md` for the
full file list and module layout. Cycle-2 review (verification PASS,
QC 89/100) surfaced two P1s; the `save_store` fail-open P1 was fixed in
cycle 3 (see `reviews/cycle3-lex-programmer.md`) and the casting-recurrence
heuristic P1 is deferred to CP2 as a line-item below. 37/37 new tests green;
full suite (487 tests) green.

## CP2 -- Reconstruction + normalization

- [x] Slice reconstruction: join `operations.jsonl` lines to session-log
      `=== Operation #N Start/End (op_id) ===` blocks by `op_id`/`seq`
      (spec sections 3, 5).
- [x] Rotation stitching: resolve the target `op_id`/`seq` list from JSONL
      first, then scan `session_<id>.log[.1/.2/.3]` for matching blocks and
      concatenate in `seq` order (JSONL-driven, not file-boundary-driven --
      resolved question Q3). Surface "history truncated by rotation" if a
      requested op was already recycled by `backupCount`.
- [x] `MAX_REPORT_OPS` (default 12) summarize-not-drop: excess ops in an
      LLM-sized slice are summarized, not silently dropped ("no silent
      caps" rule).
- [x] Path-scoped machine-hygiene normalization (spec section 8.3, decision
      E2): home-dir / OS-username substitution anchored ONLY on
      path-shaped tokens (resolved `expanduser('~')` / `USERPROFILE` at the
      start of a path segment); MUST NOT be a document-wide find/replace
      of the username string (would corrupt lexical data that happens to
      contain the username as a substring).
- [x] Report rendering (spec section 7): header, request, interpretation,
      what-was-tried, error, resolution, structured JSONL appendix.
- [x] Casting-recurrence signature precision (deferred P1 from cycle-2 QC,
      `triggers.py:62-77` `casting_recurrence_signature`): the CP1 v1 fallback
      treats ANY two `casting_issues_detected` closes in the same turn as a
      recurrence when `casting_signature`/`preflight_gate` are both blank, so
      two *unrelated* casting issues collapse into one "same bug" recurrence.
      Safe-by-construction for CP1 (only ever widens the offer surface, never
      suppresses a genuine report), but must be tightened here: thread the real
      `casting_signature` into the JSONL schema and key recurrence on it, not on
      the bare code. Add a regression test for the two-unrelated-issues case.

**Checkpoint:** CP2 landed 2026-07-13 (spurt 2, cycles 4-6). All six line-items
green. Verification PASS (full suite 511 passed / 0 failed; +1 from the 510
baseline, no regressions). Domain E2 privacy gate PASS. Cycle-2 casting-recurrence
P1 CLOSED. A post-auto-fix stale-`issues` P1 found in cycle 5
(`handlers/execution.py`) was fixed and verified in cycle 6 with a dedicated
regression test (`test_partial_auto_fix_reports_only_residual_casting_issue`,
confirmed failing pre-fix / passing post-fix). See
`reviews/cycle5-*` and `reviews/cycle6-*`.

**CP2 carryover (P2, non-blocking -- harden during CP3):**
- `reconstruct.py` mismatched-`End` silent truncation.
- `render.py` `_CODE_STOP_MARKERS` substring false-positive (tighten to a
  boundary match).

## CP3 -- Surface + transport + guard

- [ ] `flextools_prepare_report` tool (spec section 10): accepts explicit
      `op_id`/`op_ids`/`steps_back`, defaults to the whole turn.
- [ ] `diagnostic_report` advisory block on `RunModuleSuccess` (spec
      section 10; additive optional field, no contract version bump per
      resolved Q5).
- [ ] Three transports -- `gh` CLI, prefilled GitHub issue URL, `mailto:`
      (spec section 9); "gh available" check is injectable for CI.
- [ ] `likely_contains_lexical_data` code-shape sensitivity flag (spec
      section 9, resolved Q4): detected from code SHAPE (lexical-accessor
      calls feeding `report.Info`), never from content; drives only the
      email-vs-GitHub framing, never the local file's fidelity or the
      final send decision.
- [ ] Two-layer no-transmission guard (spec section 8.1/12): static AST
      scan of the `diagnostic/` module tree fails the build on any
      `subprocess`/`gh`/`git issue create`, `smtplib`, `webbrowser.open`,
      `urllib`/`requests`/`http.client`, or raw `socket` call; dynamic test
      monkeypatches those to raise and drives all three transport branches,
      asserting zero such invocations and exactly one local file write.

**Checkpoint:** not started.

## CP4 -- Docs + demo

- [ ] `docs/TOOL-CONTRACT.md` patch documenting the `diagnostic_report`
      advisory block on `RunModuleSuccess`.
- [ ] Downstream demo: end-to-end walk-through (trigger -> offer -> prepare
      -> preview -> gh/email/decline) against a real or fixture session
      log.

**Checkpoint:** not started.
