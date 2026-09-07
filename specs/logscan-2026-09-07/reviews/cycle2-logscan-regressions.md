# Log-Scan Phase B — Regression Comments Only (cycle 2)

Scope: exactly five CLOSED MattGyverLee/FlexToolsMCP issues, comment-only, no new
filings, no other issues touched, no reopen/close/relabel/edit performed.
**Reopening is explicitly NOT authorized this run** and is pending user
confirmation for every issue below.

Source: `specs/logscan-2026-09-07/reviews/cycle1-logscan-august.md`,
section "REGRESSIONS (recurred after the tracking issue's close date)",
items 1-5 (lead-verified).

## Regression comments filed

| Issue | Close date | Recurrence date(s) | Elapsed (close -> first/only recurrence) | Comment URL |
|---|---|---|---|---|
| #84 | 2026-08-12T21:05:10Z | 2026-08-12T22:03:12Z | 58 minutes | https://github.com/MattGyverLee/FlexToolsMCP/issues/84#issuecomment-5568158117 |
| #39 | 2026-07-21T07:38:02Z | 08-11 09:18:23; 08-13 00:02:20; 08-15 20:51:44; 08-15 20:53:19; 08-15 20:53:51; 08-21 08:43:40; 08-21 08:44:34; 08-26 16:02:57; 08-26 16:03:13; 08-28 16:44:57 (10 total) | ~21 days to first recurrence | https://github.com/MattGyverLee/FlexToolsMCP/issues/39#issuecomment-5568161494 |
| #75 | 2026-07-20T23:31:51Z | 2026-08-11T06:15:37Z | ~21 days | https://github.com/MattGyverLee/FlexToolsMCP/issues/75#issuecomment-5568163038 |
| #80 | 2026-07-21T06:30:06Z | 2026-08-11T06:14:24Z; 2026-08-15T17:49:55Z (20:49:55 local) | ~21 days | https://github.com/MattGyverLee/FlexToolsMCP/issues/80#issuecomment-5568168165 |
| #69 | 2026-07-20T09:09:30Z | 2026-08-21T08:43:40Z | ~32 days | https://github.com/MattGyverLee/FlexToolsMCP/issues/69#issuecomment-5568170194 |

Each comment includes: close date, recurrence timestamp(s), verbatim error
text, exact log path, elapsed close-to-recurrence time, and an explicit note
that reopening is NOT authorized this run and is pending user confirmation.

## Ranked reopen recommendation (strongest first)

1. **#84** — 58-minute close-to-recurrence gap (by far the shortest of the
   five), and `gh issue view 84` shows the merged fix was documentation-only
   with no template code diff — the closing rationale does not plausibly
   explain why the identical `'FLExProject' object has no attribute
   'LexSense'` error still fired less than an hour later. Strongest reopen
   candidate.
2. **#39** — recurred 10 times across a 20-day window (matching the jsonl
   `PolymorphicAttributeError` tally exactly), with the identical
   pre-fix hint template every time; two of the ten occurrences are
   confirmed non-user-fixable (a flexicon library bug and a recurring
   discoverability trap), meaning the fix this issue closed on is
   demonstrably not preventing the class of failure it targeted.
3. **#80** — both recurrences reproduce a **hard preflight_reject**, the
   exact failure mode Part 1 of this issue's fix was supposed to replace
   with a soft advisory redirect; this is a direct regression of the
   fix's stated behavior change, not just a related error resurfacing.
4. **#69** — recurred once ~32 days after close with the same root
   confusion (guessing at the raw `ILangProject` accessor), compounded by
   a second wrong guess in the same session that also missed the
   documented `project.lp` accessor — evidence the "did you mean" gap is
   still live end-to-end.
5. **#75** — recurred once ~21 days after close, but at a **new, third**
   call site (`ISilDataAccess.BeginUndoTask`) rather than the originally
   reported ones (`GetFields`/`Create`); this could be read as the original
   fix holding for its two known sites while the underlying gap simply
   generalizes to new call sites — weakest case for reopening the specific
   closed issue versus filing a follow-on for site generalization.

## Notes

- All five issues were independently re-verified as CLOSED via `gh issue
  view` immediately before commenting (dates matched cycle-1's report
  exactly).
- No issue was reopened, closed, relabeled, or edited. No new issues were
  filed by this run. No issue outside this list of five was touched.
- `docs/logscan-state.json` was not modified by this run; ledger
  corrections referenced in the #80 comment (retarget `53d4e6f0b229` from
  #53 to #80) are for the archivist/main session to apply when merging
  this cycle's ledger updates.
