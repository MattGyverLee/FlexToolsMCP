# Cycle 8 -- Doc Agent report (#93)

**Date:** 2026-09-08

## Files touched

- `specs/shared-mode-access/SPEC.md` -- Section 3 rewritten (:95-209): new
  `Class C` / `crashes_holder` (3c), new `3a-ii` safe/no-gate class (Q2),
  `3b` writing-system row removed, `3d` "Unclassified" emptied with a
  pointer for Q3's removal, one-sentence Class-A scoping note (:118-124).
  CP3 checkpoint (:357+) and CP4 checkpoint (:385+) each got a **SIGNED
  OFF 2026-09-08** paragraph citing `live-cp4.md` line numbers. CP5 T5.1
  scoping note (:406+) corrected -- stale "Section 3b/3c" pointer fixed,
  flagged that writing systems' new `crashes_holder` status may need a
  CP5-scope ruling from lex-lead (not decided here).
- `specs/shared-mode-access/evidence/live-cp4.md` -- Section 5 (:104) and
  Section 6 (:140) each got a **RESOLVED** note in place (original text
  kept, per "never delete"). Verified and corrected all cross-reference
  line numbers after the insertions shifted the file (+34 lines total; the
  Session 2026-09-08 content moved from offset 152 to 174).
- `specs/shared-mode-access/evidence/live-session-checklist.md` -- added a
  "Preconditions" block under Session 2 (after the old blanket pre-flight
  note, which it supersedes) with per-test sharing-state requirements.

## Q1 label decision

**Deviated from the brief's literal "Class A" label**, per the embedded
LEX-LEAD RULING: introduced `failure_class: crashes_holder` as its own
subsection (3c), not filed under Class A. Reasoning matches the ruling --
Class A's own prose ("safe by construction... needs no alarm") is
falsified by this row (nothing refused it, and the consequence is an app
crash, the opposite of "no alarm"). Added a one-sentence scoping note
limiting "safe by construction" to the `refused` mechanism specifically, so
future rows can't be miscategorized the same way.

## Corrections applied mid-task

Per the coordinator's two corrections: Session-2 test 1 preconditions now
lead with "CP5 gate code does not exist" (not scheduling/human-availability)
and note a proposed, unauthorized companion test for the untested Class B
mechanism itself. The blanket "Sena 3 must return to sharing-OFF" framing
was replaced with per-test sharing-state lines; the CP3 re-test line now
says flip OFF then restore to ON (current as-found state), not the reverse.

## SPEC.md contradictions found

The CP5 T5.1 scoping note (pre-edit) pointed to "Section 3b/3c" for
writing systems/possibility lists/reversal indexes and called them "open
live experiments" to be "added later by row" -- all three are now resolved,
and writing systems resolved to a **mandatory refusal**, not a deferrable
row. I flagged this as a scope question for lex-lead rather than silently
expanding CP5's implementation scope myself.

## Not touched (flagged, not fixed)

`.crew-handoff.json` and `STATUS.md` still show `cp3_live_sharing_off` /
`cp4_live_open_shared` as "NOT RUN" and the live session as "the only gate,
STILL OPEN." Left untouched given the concurrency note (both files are
high-traffic crew-state files likely touched by sibling agents this cycle)
and because they weren't named in my brief; recommend lex-lead/archivist
sync them to the SIGNED OFF state recorded in SPEC.md.

---
**Doc Agent:** /lex-doc
