# Implement gate -- lex-qc, cycle 1

**Date:** 2026-09-24
**Reviewed:** the uncommitted CP5 working tree on `feat/parser-check-cp5` against `main`.
**Verdict:** APPROVE, score 92/100. There are no blocking findings. One escalation and one
follow-up are carried forward.

## Pattern-audit gate: PASS

`reviews/pattern-audit.md` covers the five sweeps the plan requires, plus a sixth: "a transient read
treated as absence". Each sweep has a file:line, finding, confidence and verdict table. The reviewer
spot-checked two rows against the code:

- **Sweep 1:** `sandbox/cache.py:271-280` `judge_generation` requires exit 0, a non-empty config
  and a `Writing completed.` line. The row matches the code.
- **Sweep 2:** `backup.py:74-90, 194-204`. `_remove_partial_backup` runs whenever `copy2` fails.
  The row matches the code.

## Live-LCM evidence gate: PASS (no write path, verified in code)

- **Write-adjacent call sites:** there are only two, `handlers/execution.py:2663-2681` and
  `filing/observer.py:161-189`.
  - Each only invalidates MCP-owned cache entries after a write has already completed.
  - Each is guarded, and each is logged and swallowed rather than propagated.
  - Neither calls into LCM or flexicon.
- **Engine check:** `sandbox/engine.py` reads the live `.fwdata` as a plain `rb` stream with
  `iterparse`, and imports nothing from LCM, flexicon, flexlibs or pythonnet.
- **Live evidence:** `evidence/s1-health-no-hc.json` exists. S2-S13 and L-1..L-7 (FR-045) are
  honestly recorded as `needs_human` and blocked on M-1. They are not claimed as done.

## Scores

| Area | Score | Notes |
|---|---|---|
| Code quality | 23/25 | Each module's docstring maps it to its FR or research item. The handler walks contracts/tools.md section 3's steps as numbered comments. Deduction: open audit follow-ups |
| Standards | 25/25 | Detail-model field order matches the contract. Closed `Literal` enums, `extra="forbid"` |
| Error handling | 24/25 | The engine check fails safe. The sweep 6 `read_meta_strict` fix closes a meta-wipe risk in `set_stage`/`set_section`. The two broad catches on cache invalidation are justified in comments |
| Best practices | 24/25 | A per-run `SandboxClient` reuses the job model. No exit code is trusted alone. `iterparse` stops early |

## Carried forward

1. **Escalation to `/lex-lead` (not a QC block).** FR-045's live verification (T095) is
   `needs_human` and blocked on M-1, because this machine has no working `hc`.
   - It is safe to merge with the gap flagged, because the spine cannot touch a live project.
   - It must not be upgraded to "verified" until the M-1 route is chosen and the S2-S13 / L-1..L-7
     evidence has landed.
2. **Non-blocking follow-up.** `sandbox/store.py` `create_sandbox` can leave a claimed sandbox
   directory behind after a mid-write disk failure (pattern-audit sweep 2). Deleting inside a
   user-owned area needs a deliberate decision under FR-025. File a ticket for it.
