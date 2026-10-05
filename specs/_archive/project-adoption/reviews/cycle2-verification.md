# Cycle 2 -- Verification report (project-adoption, #168/#169/#170)

**Verdict: GREEN** (with one pre-existing, unrelated open item noted below)

## 1. Test run (verbatim)

Full suite (`python -m pytest tests -q`, read-only run, no tree mutation):
`2105 passed, 8 skipped, 23 warnings, 36 subtests passed in 402.65s`. **Zero
failures.** (A concurrent session reported 1 order-dependent failure in
`test_parse_status_handler.py` on an earlier run of the same tree; my own
run did not reproduce it -- 0 failures observed here. Not attributable to
this change regardless: that file stubs `_resolve_project` wholesale,
bypassing the adoption guard entirely. Recorded as pre-existing suite-hygiene
noise, not this feature's responsibility.)

Required subset (`test_project_discovery.py test_issue53_cold_start.py
test_issue47_auto_discovery.py test_issue10_session_persistence.py
test_retry_loop_detection.py test_issue55_write_safety_ladder.py`): **84
passed** -- matches programmer's claim exactly.

No failures anywhere in my runs, so no (a)/(b)/(c) triage was needed.

## 2. Scope audit -- PASS, with two flagged-but-cleared observations

`git diff` (read-only) confirms: `execution.py` -- one clean hunk at :2851
(guard + log). `grammar_health.py` -- one clean hunk at :258. `parse.py` --
one clean hunk at `_resolve_project` (:326-341, structurally identical to
the other two sites) plus unrelated pre-existing CP2b hunks at :465+
(untouched by this diff, confirmed by hunk headers). `session.py` -- only
the two hint strings. `admin.py` -- **empty diff** from this change (the
one hunk present, near :295, is a third concurrent session's
`is_empty_multistring` doc edit per the coordinator's note -- correctly not
ours, and nowhere near :507 or :521-547).

`server.py` is modified, but **not by this feature**: an unrelated
`operations_logger` -> `get_operations_logger()` refactor (4 line
insertions). The cold-start `configure()` block (originally :891-917) is
textually **unchanged** -- verified by direct read -- merely shifted ~4
lines down by the unrelated insertions above it. No logic in that block
was touched.

## 3. Invariants

**(a) WRITE GATING UNCHANGED -- PASS.** Read execution.py:2770-2771:
`write_enabled` computed before the adoption block at :2851, which is a
bare `session_state.project_name = resolved` (no `configure()` call).
Identical structure confirmed in grammar_health.py and parse.py.

**(b) NO-STOMP -- PASS.** `TestNoStompRegression::test_adopted_project_does_not_reset_api_mode_or_write_enabled`
exists exactly as specified and passes in isolation (1 passed).

**(c) DISCOVERY-STATE DELTA -- PASS**, confirmed empirically via a manual
trace script (not just code-read): empty start (write_enabled=False,
session_id=`auto-<random>`) -> `run_module(project_name="ProjX")` adopts
(write_enabled stays False) -> `flextools_start(project_name="ProjX")`:
`session_id` **unchanged** (same_project=True, no wipe) and
`discovered_apis` marker **preserved**. No escalation: `write_enabled`
stayed False throughout the whole sequence -- no P0.

**(d) project_not_found adopts nothing -- PASS.** All three sites `return`
inside the `if _resolve_err:` block before the `if resolved:` adoption
line; verified by direct read of all three diffs.

## 4. Live smoke -- PASS (genuinely live, not deferred)

A live FieldWorks registry with real projects (including "Target") is
present on this machine. Ran, via direct handler calls (no mocked
resolver): cold `flextools_start({})` -> `run_module(project_name="Target",
code=<read-only LexEntry.GetAll() count>)` -> bare `run_module()` (no
`project_name`).

Result: RUN1 executed against the real live LCM (`success=True`,
`entry_count=15318`, zero writes -- `write_enabled=False` throughout).
Session adopted `"Target"`. RUN2 (bare) targeted `"Target"`
(`error_code != project_name_required`) and `write_enabled` remained
`False`. No write occurred; nothing to restore.

## Open items

- P2 (pre-existing, out of scope): `test_parse_status_handler.py`
  order-dependent failure reported by a concurrent session on a full-suite
  run; not reproduced in my run; not caused by this diff (file bypasses the
  adoption guard). Worth its own suite-hygiene issue, not this feature's.

## Recommendation

APPROVE.
