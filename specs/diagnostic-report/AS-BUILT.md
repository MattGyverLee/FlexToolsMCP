# diagnostic-report: as built

**Status:** Retired 2026-09-29. Merged to main via PR #73 ("send-to-maintainer flow (CP1-CP4)", 2026-07-20, head `feat/diagnostic-report-cp1`, lands as `d7ef275`). Checkpoint commits: CP1 `c52c4a9`, CP2 `356a227`, CP3 `e5ef733` / `f9e3f5b`, CP4 `d7ef275`. Tasks: all checked (CP1-CP4; one `[n/a]` carryover already fixed in CP2).
**Full docs:** [specs/_archive/diagnostic-report/](../_archive/diagnostic-report/) ([spec](../_archive/diagnostic-report/spec.md), [tasks](../_archive/diagnostic-report/tasks.md), [reviews](../_archive/diagnostic-report/reviews/) cycles 1-9). Not read by default.
**Pinned here:** none (no test or code opens these files at runtime; only docstring citations).
**User docs:** `docs/TOOL-CONTRACT.md` ("`diagnostic_report` advisory block"), `docs/DIAGNOSTIC-REPORT-DEMO.md` + `tests/test_diagnostic_report_demo.py` (same stage headings).

## What shipped
- Opt-in "send this to the maintainer" flow: on a reportable failure the MCP writes a full-fidelity local report and prepares transport strings. It never sends anything.
- Package `src/flextoolsmcp/server/diagnostic/`: `triggers`, `signature`, `offered_store`, `reconstruct`, `render`, `normalize`, `sensitivity`, `transports`. Handler `server/handlers/diagnostic_report.py`.
- Tool `flextools_prepare_report` (`op_id`, `op_ids`, `steps_back`, `include_from_op_id`; default = whole turn).
- Additive optional `diagnostic_report` field on `RunModuleSuccess` (`KEY_DIAGNOSTIC_REPORT`); no contract bump (stays `tool-responses/1.0`).
- Optional `user_request` (verbatim text) input on `flextools_start` and `run_module`, logged at op start and in `operations.jsonl`; falls back to `user_intent`.
- Config knobs `report_offers_enabled` (default on; gates only the auto-offer), `report_repo`, `report_email` (`config.py:36-57`).
- Tests: `tests/test_diagnostic_report_{foundation,reconstruction,transport,demo}.py`, `tests/test_diagnostic_no_transmission.py`.

## Public contracts (checked against the code at `0715b64`)
- Trigger (`triggers.py`): `outcome == "runtime_fail"` (any exception class; `timeout` excluded), `error_code == "invalid_api_chain"`, or `casting_issues_detected` on recurrence only, keyed on `casting_signature` in the JSONL. `NON_REPORTABLE_CODES` (line 33) never fire.
- Signature (`signature.py`): code-independent hash; never keys on `code_sha256`. Offer once per signature.
- `~/.flextoolsmcp/reports/offered.json` (`offered_store.py`): `version: 1`, states `offered`/`declined`/`dont_ask_again`, LRU cap 500 by `last_seen`, corrupt or missing file fails open.
- Reconstruction (`reconstruct.py`): JSONL-driven; stitches `session_<id>.log[.1/.2/.3]` in `seq` order; flags ops lost to rotation and mismatched `End` markers (`end_mismatches`); `MAX_REPORT_OPS = 12`, and ops over the cap are summarized, not dropped.
- Report file: `~/.flextoolsmcp/reports/report_<ts>.md`, sections header/request/interpretation/what-was-tried/error/resolution/JSONL appendix, schema `"1"`.
- Normalization (`normalize.py`): home path to `~` and username removed **only inside path-shaped tokens**. It never does a find/replace across the whole document (E2).
- Transports (`transports.py`): `gh issue create --repo <report_repo> --body-file <report> --label auto-report`; prefilled issue URL and `mailto:` each capped at 8 KB and carrying a short, normalized body; the gh-available check can be injected.
- `likely_contains_lexical_data` (`sensitivity.py`): an AST check of code shape (lexical accessors feeding `report.Info`). It only changes the framing between email and GitHub.

## Key decisions
- The payload comes from the session log; `operations.jsonl` is joined in by `op_id`/`seq` (section 3.2).
- Reports are always unscrubbed. Privacy comes from the choice of channel (GitHub by default, email when private, or don't send), not from masking content (sections 7.1, 8, 9).
- The preview shows both the full file and the capped transport string for the chosen channel (E4).
- A turn is grouped by `user_intent`. `user_request` is carried as payload and is not part of the grouping key (E7).
- No-transmission is enforced structurally at two layers: an AST scan of `diagnostic/` and dynamic monkeypatch tests covering all three branches.
- Workaround signal is inferred: reportable failure, then a same-turn `ok` close (section 6.2).
- Option (c): the auto-offer attaches only at a same-turn `ok` close (`execution.py:5490-5495`). A turn that fails and is then abandoned is not auto-offered; the recovery path is `flextools_prepare_report`.

## Gotchas and limits
- Abandoned-turn gap (above) is still live in code.
- #167: reconstruction and the auto-offer filter to `run_module` JSONL records only, so parse telemetry lines do not break turns into pieces (`diagnostic_report.py:356`).
- `_quote_argv` `display` is a POSIX-shell approximation; `argv` is authoritative on Windows.

## Divergences from the spec
- Spec section 11.6 says `user_request` is "primary/mandatory" on `flextools_start`; the code makes it `Optional` on both inputs (`models.py:71`, `:493`).
- Tasks say "13 explicitly non-reportable codes". The set now has 14: `reflection_bypass_detected` was added later (#277).
- `include_from_op_id` is an input on the tool, beyond the spec's `op_id`/`op_ids`/`steps_back` signature (the spec's section 5 prose allows it).
- Issue #72 (the abandoned-turn limitation) is **closed as COMPLETED** (2026-07-20, the same second PR #73 merged). The PR body's sentence "Closes #72 is **not** implied" appears to have triggered GitHub's auto-close. The limitation was never fixed.
- Citations everywhere say `SPEC.md`; the file is `spec.md`.
- Not verified: the test counts in the checkpoints (487/511/577/597) or each acceptance criterion one by one.

## Follow-ups and open issues
- Reopen #72, or record that the limitation is accepted permanently.
- Stale: `STATUS.md:555,1046-1128` still describes the feature as "paused" before CP4; `.spec-context.json` says `status: draft` while `.crew-handoff.json` says `feature_complete`.
