# Domain Expert Review — Diagnostic Report Spec (cycle 1)

> Persisted by the main session on behalf of lex-domain (its task tool set was
> Read/Grep/Glob/WebFetch only — no Write). Content is verbatim from the agent's return.

**Date:** 2026-07-13
**Domain:** FLEx / LibLCM / Flexicon (FlexToolsMCP)
**Reviewed:** specs/diagnostic-report/SPEC.md, §11 open questions 1, 2, 4, 6

## Q1 (§11.1) — REPORTABLE_CODES

Grounded in the 16 codes in docs/TOOL-CONTRACT.md and their handling in
validators.py / execution.py. Criterion: does the code reflect a gap in the
MCP's model of LibLCM/Flexicon (index inaccuracy, casting-index blind spot,
uncaught runtime exception against the real API) versus an ordinary
authoring mistake the MCP already guides the user through?

**Proposed REPORTABLE_CODES = {`runtime_error`, `casting_issues_detected`
(recurrence only), `invalid_api_chain`}**

- `runtime_error` — YES, core case. An exception escaped preflight and hit
  live LibLCM/Flexicon. This is exactly the "unhandled inconsistency" class
  the spec's motivation describes (§1). Always reportable (subject to
  dedupe).
- `casting_issues_detected` — CONDITIONAL. This code fires from the
  preflight polymorphic-casting heuristic (validators.py ~2360-2460), which
  is proactive *guidance*, not a failure — most instances resolve cleanly
  once the user casts per the hint and are not maintainer-worthy. Only
  report when the **same op_id's signature recurs after a cast was
  applied** (i.e., the casting_index's known patterns didn't cover the
  case) — that recurrence is a real coverage gap in `known_polymorphic_patterns`
  worth upstreaming.
- `invalid_api_chain` — YES. This means the generated chain doesn't exist
  against the real API surface despite passing discovery — a documentation/
  index mismatch, not a user typo.
- `undiscovered_entity` / `api_discovery_required` — NO. Normal discovery
  flow; firing is expected and self-resolving via the suggested tool call.
- `wrong_library_imports` / `missing_imports` / `undefined_variables` /
  `syntax_error` — NO. Ordinary authoring mistakes, explicitly excluded by
  the spec.
- `unprotected_writes` — NO. Working safety gate, not a defect.
- `partial_module_structure` — NO (explicitly excluded in spec text).
- `project_locked` / `project_drive_unavailable` / `project_path_mismatch` /
  `project_not_found` — NO. Environment/infra issues, not LibLCM domain
  inconsistencies (a locked FLEx project or missing drive is not a bug to
  upstream).
- `server_state_error` — NO for this feature; it's an MCP-infra signal, not
  a lexicon-domain one, and is better served by ordinary MCP issue filing,
  not this per-turn slice.

## Q2 (§11.2) — "LibLCM workaround taken" signal

Grepped src/flextoolsmcp for `workaround`/`inconsistenc*` — **no such signal
exists in code today** (only incidental hits in generated index JSON).
`casting_helpers`, `resolve_property`, and the preflight gate all *prevent*
errors proactively; none currently emits a "this required a workaround"
event.

**Recommendation:** infer it for v1, don't invent new instrumentation yet.
Definition: within one turn, an op closes with `outcome` in
`{preflight_reject, runtime_fail}` and `error_code` in REPORTABLE_CODES,
followed by a later op in the same turn (same `user_intent`/`user_request`
grouping, per op_telemetry's existing turn-grouping) that closes `outcome
== "ok"`. That pair *is* the workaround signal — request → failure →
resolution — and it's exactly the shape §7's bundle already wants (item 6,
"the resolution"). Flag as a follow-up: if `casting_helpers` or
`resolve_property` gain an explicit "cast applied" telemetry point in a
later release, promote that to a first-class signal instead of inference.

## Q4 (§11.4) — Auto-detect substantial lexical data

**Recommendation: auto-detect (structural, not content-inspecting) to drive
the *framing*, but never the final decision — GitHub stays the default and
"don't send" is always available, per §9's existing rule.**

Heuristic (checks code/call shape, not string values):
- The op's code (already hashed/logged, source available in the slice)
  calls known lexical-accessor methods — `GetGloss`, `GetDefinition`,
  `GetLexemeForm`, `.BestVernacularAlternative`, `.BestAnalysisAlternative`,
  `.Text` on multistring fields — AND those results are passed into
  `report.Info(...)`.
- OR the code references writing-system tags in string literals matching a
  BCP-47-like pattern (e.g., `"en"`, `"fr"`, custom vernacular WS codes)
  alongside a multistring accessor call.
- Either condition flips a boolean `likely_contains_lexical_data` used only
  to choose which sentence Claude says ("this report may contain unpublished
  language data — GitHub is public; email is private, want to switch?"),
  never to alter what's written to the local file (already full-fidelity
  per §7.1/§8). This satisfies "does not itself inspect or leak the data" —
  it inspects the *code shape*, not the *string contents* that flow through
  it.

## Q6 (§11.6) — user_request placement

**Recommendation: primary on `flextools_start` (turn-level, mandatory
capture point); optional override on `run_module` only when intent
genuinely drifts within a turn.**

Domain rationale: the common FLEx workflow inside one turn is
retry-with-cast (cast, rerun, cast again) or discovery-then-write — the
*ask* doesn't change, only the approach, so turn-level capture is
sufficient and avoids duplicating verbatim text on every retry op (exactly
the workaround-loop shape from Q2). Per-op capture should be reserved for
the rarer case where the user actually restates/refines the request
mid-turn (e.g., "actually, only do this for the Reversal Index entries") —
Claude decides to re-supply `user_request` on `run_module` only then. This
matches §7 item 2's stated preference for "verbatim text as primary" while
keeping the common path cheap.

---
**Reviewed By:** Domain Expert Agent
**Domain:** FLEx / LibLCM / Flexicon
