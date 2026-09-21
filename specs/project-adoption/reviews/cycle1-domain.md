# Domain Expert Review -- Session Project Adoption (Unconditional)

**Date:** 2026-09-20
**Domain:** FLExTools/FLEx project session-management workflow
**Status:** Design accepted as given; guardrails proposed
**Note:** authored by the lex-domain agent (read-only, no write tool);
persisted verbatim by the main session.

## Last-wins risk assessment

Plausible, and the live evidence cited
(`auto-0106f53b19ed45ec8f84a727162e7e21` carrying `Claude-Swahili` on ~20
consecutive ops) shows the *opposite* failure mode already occurring
today -- a correctly-named project failing to stick because it matches
the caller's typed name. Unconditional adoption fixes that but opens the
mirror case: an LLM caller doing a one-off cross-project read
(`flextools_grammar_health(project_name="ProjectB")` while the session is
mid-edit on `ProjectA`) permanently reassigns
`session_state.project_name` to B. A subsequent *unqualified*
`flextools_run_module(code=..., write_enabled=True)` -- which falls back
via `args.get("project_name") or session_state.get_project()`
(execution.py:2769) -- now mutates B, not A. Severity: high if it
happens, because the write silently lands on the wrong FLEx project with
no exception, no obviously-wrong output ("gloss added" is true, just to
the wrong lexicon) -- exactly the SPEC 8.4-flavored silent-failure class
this codebase is already vigilant about. Likelihood: moderate-real;
multi-project comparison/read ("check how X is glossed in ProjectB") is a
natural conversational digression an LLM agent will make without being
told it changes session state.

## Write-gating invariant (pass/fail + evidence)

**PASS.** Adoption is a bare attribute set,
`session_state.project_name = resolved` (execution.py:2853,
grammar_health.py:259, parse.py:327), never a call to
`session_state.configure()`. `write_enabled` lives in a separate
dataclass field (session.py:143) that adoption never touches. In
`run_module`, the effective `write_enabled` local is computed at
execution.py:2770-2771 -- `bool(args.get("write_enabled") if not None
else session_state.is_write_enabled())` -- strictly from the
explicit-arg-or-prior-session-value, and this line runs *before* the
adoption block (2851-2854) in the same call, so even within one call
adoption cannot retroactively arm a write. `try_word` (parse.py) is
READ_ONLY_SAFE with `writeEnabled=False` hardcoded in the worker;
`write_enabled` is never in scope on that path at all. Cold-start
(server.py:906-910) independently enforces "never default write_enabled
to True unless the caller passed it explicitly this call" -- consistent
with the same invariant, unrelated code path.

## `project_not_found` / normalized behavior

**Confirmed correct, no change needed.** `resolve_or_explain`
(project_discovery.py:449-471) returns `(None, error_dict)` for
`no_match`/`ambiguous_normalized`; all three handlers check
`if _resolve_err:` and `return error_response(...)` immediately
(execution.py:2838-2850, grammar_health.py:249-257, parse.py:317-325) --
the adoption line is unreachable on that path, so nothing is adopted on
`project_not_found`. On `reason == "normalized"`, `resolve_project_name`
(project_discovery.py:253-254) returns `matches[0]` -- the real on-disk
name from `list_projects()` -- not the caller's typed spelling, so
adoption always writes the canonical form.

## Recommended guardrails (ranked)

1. **Operations-log line on adoption CHANGE** (highest value/cost ratio):
   when `resolved != session_state.project_name` and
   `session_state.project_name` was already non-empty, log
   `[PROJECT-ADOPTED] {name}: session project changed 'A' -> 'B'` via
   `get_operations_logger()`, mirroring the existing `[AUTO-INIT]`
   pattern (server.py:912-917). Free (no schema touch), and gives exactly
   the forensic trail issue-report evidence needed.
2. **Response hint text on the SAME call that changes it**: add a
   plain-language note to the existing `hint`/advisory channel (not a new
   field) saying "session project is now 'B'; unqualified calls will
   target it until changed again." Low cost, catches the LLM in the
   moment rather than after the fact.
3. **`session.summary()` already exposes `project_name`**
   (session.py:396) -- no work needed; every response already carries
   current truth. Not a new guardrail, just confirm callers read it.

## Contract-touch flags

None of the above requires a `tool-responses/1.0` schema change: (1) is
log-only, (2) reuses the existing `hint`/`session` fields already in the
envelope, (3) is a no-op. If a future iteration wants a *dedicated*
`project_adopted: bool` response field, flag that explicitly as a
CONTRACT TOUCH requiring `docs/TOOL-CONTRACT.md` versioning -- not
proposed here.

---
**Reviewed By:** Domain Expert Agent
