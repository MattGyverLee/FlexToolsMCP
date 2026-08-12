# Cycle 1 — QC review (issue #84)

Score: 58/100 — FIX ISSUES. See cycle1-adjudication.md: the headline P0 is REJECTED
on evidence; the P1 is confirmed and fixed.

## P0 (claimed) — "only 2 of 31 phantoms fixed"
Claims 31 of the 43 Operations shorthands are phantom (`Example`->`Examples`,
`WritingSystem`->`WritingSystems`, `Text`->`Texts`, ...), derived from the
FLExProject `properties` block of `index/python/flexicon_api_v4.3.0.json`.

**REJECTED** — see adjudication. The index property list enumerates 58 names; the
live class exposes both singular and plural aliases. All 29 of the disputed names
exist on `dir(FLExProject)`. The index was the wrong oracle.

## P0 (claimed) — "design rationale cites its own counterexamples"
Same root error: `project.Example` / `project.WritingSystem` are real. REJECTED.

## P0 (claimed) — "CLAUDE.md still teaches project.LexSense"
Stale read — CLAUDE.md was swept in the same change. REJECTED.

## P1 — Dangling script reference (CONFIRMED)
`constants.py` pointed at `scripts/check_project_accessors.py`, which did not exist.
Fixed by writing the script (it diffs shorthands against the LIVE class, not the
index — precisely the error this review made).

## Q1 — Auto-fix semantics
Argues alias-sourced issues should REJECT rather than auto-fix: `project.LexSense`
was taught by our own template, so auto-fixing hides the docs bug and leaves the
user's saved source broken outside the MCP. Judgment call — deferred to the user;
current behaviour keeps auto-fix, which already emits an
"[ACTION REQUIRED] update your source file" note.

## Q4 — Self-filter safety (CONFIRMED SAFE)
A candidate equal to the failing attribute can never be a valid fix — if it were,
no AttributeError would have fired. The `if not candidates` early-return behaves
correctly when filtering empties the list.
