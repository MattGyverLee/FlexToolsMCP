# Cycle 10 -- MCP#80 vs. CP-B's read-only casting downgrade

**Verdict: (a) -- the CP-B downgrade does NOT cover #80's path. Different gate,
no shared code, and the downgrade's entry guard is `False` for #80's code.**
(b) is affirmatively ruled out: the fix predates both recurrences.

## Where #80 actually rejects

| | file:line |
|---|---|
| CP-B downgrade (casting gate) | `execution.py:2931` guard `if casting_check["has_casting_issues"]:`, downgrade at **`:2951`** `if (not write_enabled) and not casting_check["has_error_severity"]:` |
| **#80's hard reject** | `execution.py:3137` gate -> **`:3138` `if write_enabled:`** -> `_log_preflight_reject(..., "api_discovery_required")` at **`:3141-3144`** |

The brief's anchor "2922-2934" has drifted; the live downgrade condition is `:2951`.

## Runtime red/green (probe: scratchpad `probe80.py` / `probe80b.py`, verbatim
recurrence code from `session_204945_auto-Target.log` op #1, 511 bytes)

```
[write_enabled=True ] error_code='api_discovery_required'
    downgrade_predicate_called -> False
    casting_decision {has_casting_issues: False, has_error_severity: False, n_issues: 0}
    REJECT api_discovery_required
[write_enabled=False] error_code=None   (falls through, no reject)
```

Two facts, both runtime-demonstrated on HEAD **with CP-B's downgrade present**:

1. `has_casting_issues == False` (`n_issues=0`), so control never enters the
   `:2931` block at all. The downgrade at `:2951` is unreachable for this code.
   `_has_error_severity_casting_issue` is invoked only inside
   `_compute_casting_decision` (`:1743`); its verdict is discarded.
2. The reject is emitted ~200 lines later at a gate CP-B never touched -- and
   `#80`'s recurrence reproduces on today's HEAD.

## Why (b) is ruled out

#80 Part 1 landed in `7d17d78` "feat(discovery): implement graceful discovery
redirect" at **2026-07-20 16:54:50 -0500 (= 07-20T21:54:50Z)**, i.e. *before*
#80's close (`2026-07-21T06:30:06Z`) and well before both recurrences
(`2026-08-11T06:14:24Z`, `2026-08-15T17:49:55Z`). Not a stale-binary artifact.

## The real defect (also a CP-B-shaped input mismatch)

Both recurrence rows carry **`"write_enabled": true`** (`operations.jsonl:293`
for op-091424882-001; `Write enabled:   True` in the 08-15 session log) -- and
both submissions are pure introspection. Probe: `certify_script_readonly()` on
the 08-15 code returns **`is_certified_readonly = True`, `mutating=[]`**.

So `:3138` keys the hard gate on the **session write flag**, not on whether
*this* code mutates. #80's Part 1 fixed the *read-only-session* case only; a
certified-read-only snippet in a write-enabled session still hard-rejects.
That is the same class of defect as CP-B's P1-1/P1-2 root cause ("the typo
detector's inputs and the casting gate's inputs are not the same set"): here,
the write-safety certifier's inputs and the discovery gate's inputs are not
the same set.

**A fix would have to touch `execution.py:3138`**, replacing `if write_enabled:`
with a certification-aware condition. `cert` (assigned `:2841`) is already in
scope -- verified by AST: `handle_run_module` spans `2555-4658`. `:3138` is
inside it. No new plumbing needed.

**Do not generalize.** CP-B's own ruling
(`tasks-bugfix-campaign.md`, CP-B "Guardrail this imposes on B-1") forbids a
blanket "downgrade all preflight gates on read-only runs" refactor; #80 needs
its own gate-local change, not an extension of B-1.

**Caveat:** the existing `tests/test_issue80_graceful_redirect.py:236-264`
assertions are *source-text* greps over the handler body, not behavioral --
they pass while the recurrence reproduces. Any fix should add a real
`handle_run_module` invocation test.
