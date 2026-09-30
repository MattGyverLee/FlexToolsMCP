# Doc Agent Report -- cycle 4, CP2b Delta 6 closure + live-lesson recording

**Date:** 2026-09-20
**Trigger:** cycle-3 author review (6/10) + cycle-3 live verification (FAIL)

## Files touched

- `specs/parser-check-cp2b/spec.md` Delta 6 (:170-275-ish, was :170-237):
  (1) derivation sentence now scoped to "a document we can read", naming the
  rootless case as the boundary, not an omission; (2) new paragraph joining
  the rootless outcome to the `<Error>` case -- both now `parse_error`,
  neither `parsed` nor `hypothesis_held`, closed in cycle 4 (was a
  manufactured `{"parsed": False, "analysis_count": 0}`); (3) new "fourth
  instance" paragraph recording `_level_guidance`'s `restricted` branch
  (`parse.py:852-855`) split by `hypothesis_held`/`parse_error` instead of
  the old unconditional `explains_failure: True`.
- `specs/parser-check-cp2b/contracts/tools.md` (:122-163, was :122-140):
  restricted row now says the keys are "absent ... never present and set to
  false"; `<Error>` paragraph extended to cover the rootless case and states
  `parse_error` **replaces**, not joins, both field pairs; new
  `explains_failure`/`next_step` paragraph covering all three levels,
  including the cycle-4 restricted-branch split. `result_summary` note
  (:189-224 area) gained one sentence: a `parse_error` entry counts toward
  `words`/`traces_written` only, never `parsed`/`hypotheses_held`.
- `docs/TOOL-CONTRACT.md` (:265-296): mirrored the same three changes at
  smaller scale -- absent-keys language on the restricted row, rootless
  case folded into the `parse_error` paragraph with the replaces-not-joins
  clause, and one added sentence on `result_summary`.
- `specs/parser-check-cp2b/evidence/cp2b-evidence.md` (after :721, before the
  US3 `---`): two new sections. "LESSON -- a green mock suite is not a
  verified one for this call path" states the 2016/6/0 mock parity across
  cycles 2 and 3 against the live `XName` `TypeError` at `worker_main.py:852`
  (both `pukul` and `meŋ`), and that Explore (cycle 1) predicted the seam
  and QC (cycle 1/2) re-flagged it P2 before it shipped. "State -- the
  empirical equality check is BLOCKED, not passed" separates the source
  reading (done) from the live cross-check (blocked by the crash before any
  count returned), and says Delta 6's derivation claim rests on reading
  alone until the re-run lands.

## The four author rewrites -- applied where they fall on my side of the line

Rewrites 1 and 2 target the docstring/comment in `worker_main.py`, which is
src and not mine to edit -- the parallel agent owns that file. I applied
the equivalent outward-facing content in spec.md instead (item above). As
read just now, `worker_main.py:844-850` still has the pre-cycle-4 code (the
manufactured `parsed: False`, and the "never as an error" comment the
author flagged as backwards), and `parse.py:852-855` still hardcodes
`explains_failure: True` for every restricted outcome. Rewrites 3 and 4 are
applied in full (spec.md and both contract docs respectively).

## Open follow-up

`worker_main.py:844-857` (`_summarize_trace`'s rootless branch, its
docstring, and its comment) and `parse.py:852-855` (`_level_guidance`'s
restricted branch) do not yet match the text above -- flagging for whoever
lands the src-side cycle-4 fix, since specs/contracts now describe the
ruled target state, not (yet) the shipped one.

Not committed, per instruction.

---
**Doc Agent:** /lex-doc
