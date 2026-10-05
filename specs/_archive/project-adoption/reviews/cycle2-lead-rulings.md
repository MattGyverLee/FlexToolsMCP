# Cycle 2 -- Team lead rulings (synthesis of cycle 1)

Feature: project-adoption (#168 / #169 / #170)
Note: authored by lex-lead; persisted by the main session.

## Consensus accepted from cycle 1

#168 is a three-site one-line guard change; the write-gating invariant is
PASS with evidence (`execution.py:2770-2771` computes `write_enabled`
*before* the adoption block at `:2851`); `project_not_found` adopts
nothing; `normalized` adopts the canonical on-disk name;
`admin.py:507` is already effectively unconditional.

## R1 -- `admin.py:507` stays untouched. Confirmed.

The guard there only gates the `[SESSION-START] project_name autocorrected`
log line at `:514-517`; the name reaches the session unconditionally via
`configure()` at `:547`. Changing it would destroy the autocorrect log
line and gain nothing. This makes the feature a consistency restoration:
the other three sites come *into line with* admin.py.

## R2 -- Overturning QC on #169: do NOT add `cold_adopt_consumed`.

`execution.py:2769` takes `project_name` from `args` *or* session, and the
resolve/adopt block at `:2837-2854` runs regardless of
`session_state.initialized`. So once #168 lands, `flextools_start()`
(empty) -> `run_module(project_name=X)` adopts X on the
warm-but-projectless path -- which *is* #169's acceptance criterion. #169
closes as fixed-by-#168.

Worse, QC's option (c) carries the exact defect QC used to reject option
(a), merely narrowed. Re-entering the cold branch calls
`configure(api_mode="flexicon", write_enabled=cold_write_enabled, ...)` at
`server.py:906-910`, which after an empty
`flextools_start(api_mode="liblcm", write_enabled=True)` would (a) stomp
the explicit `liblcm` choice and (b) silently downgrade `write_enabled` to
False whenever the `run_module` call doesn't re-pass it -- contradicting
#9's inheritance fix at `admin.py:521-529`. Not re-entering avoids both.
A regression test that would fail under (c) locks this ruling in.

Residual #169 gap that #168 does not cover: `session_id` stays
`auto-<random>` instead of `auto-<project>`, and no adoption appears in
the ops log. **Do not re-anchor `session_id`** -- that mints a new id and
fires `clear_discovered_apis()` mid-session, the precise regression the P0
comment at `admin.py:543-547` was written to prevent. Take domain
guardrail #1 instead: a `[PROJECT-ADOPTED]` ops-log line.

## R3 -- QC's regression risk #1 is wrong in direction.

Adoption is a bare attribute set (`session_state.project_name = resolved`),
never `configure()`, so `session.py:249-255` is never reached by adoption.
The real delta is the inverse: after adoption sets `project_name=X`, a
*later* `flextools_start(project_name=X)` now sees
`incoming_project == self.project_name` -> `same_project=True` -> no new
session and **no** discovery wipe, where previously (`project_name == ""`)
it minted `auto-X` and wiped. The change makes restarts more continuous,
not less. Second-order consequence worth a test: `same_project=True` also
means `write_enabled` is now *inherited* on that restart via
`_resolve_inherited_flag`. Adoption never sets `write_enabled`, so there
is no escalation -- but verification must prove it.

## R4 -- #170 acceptance is satisfied by new assertions.

The existing checks in `TestAssistanceHintsPointToAvailableProjects` are
substring assertions (`"available_projects" in hint`, `"project_name" in
hint`, `"call flextools_list_projects" not in hint`) that still hold
against the proposed strings. The criterion's intent is "tests pin the
settled wording," not "the diff must show edited lines." Add assertions;
delete or weaken none -- removing them would regress #53's actual win,
which #170 explicitly forbids. Also: the `project_not_open` string keeps a
per-op mention, which #170 sanctions conditionally ("keep it only once the
per-op route actually persists") -- #168 makes it persist, so it is
allowed. Both strings approved verbatim.

## R5 -- Overturning Explore on deferral: all three sites land now.

The uncommitted CP2b hunks in `parse.py` begin at line 465
(`handle_flextools_try_word`, `_inline_response`, `_level_guidance`,
`_result_summary`). `_resolve_project` at `:289-328` is untouched by CP2b
-- zero textual overlap, no merge risk. Deferring would leave #168 partly
fixed and preserve exactly the inconsistency the issue names. Constraint:
touch nothing in `parse.py` outside `:326-328`, and put new parse coverage
in the *clean* test files, not the dirty parse suites.

## R6 -- One owner for all hint work.

Domain guardrail #2 and #170's rewording are different channels
(success-path note vs. `_ASSISTANCE_HINTS_BY_ERROR_CODE` rejection text),
but both go to `lex-programmer` in cycle 2 so they cannot conflict.
Ruling: implement guardrail #1 (log line) now; **defer** guardrail #2's
success-path note -- it needs a decision about which field carries it on a
success envelope and risks a `tool-responses/1.0` touch. Recorded as an
open P2.

## Accepted residual risk

Last-wins cross-project reassignment remains a real moderate/high
silent-write vector. The user's decision is settled; write-gating is
unchanged and confirmed PASS; `session.summary()` already carries
`project_name` on every envelope. Log line + this on-record note is the
mitigation for this feature.
