# CP4 live evidence

Every file here is a before/after record from a live run against a
**disposable copy** of a FieldWorks project (`CP4-Scratch-<source>-<stamp>`,
made by `tests/live_support/make_disposable.py`; FR-037). No artifact is ever
written inside a project folder (FR-042). Runs are under
`FLEXLIBS_REQUIRE_LIVE=1`, so a missing prerequisite fails rather than skips.

Naming follows the CP2b/CP3 precedent: one JSON file per question or
scenario, named for what it answers. Each file records the project copy, the
FieldWorks and pyflexicon versions, the `.fwdata` sha256 and mtime before and
after, the calls made, and the verdict.

## Phase 1 -- the live questions that can move the design

| File | Question | Blocks |
|---|---|---|
| `l0-coexistence.json` | L-0 / R-10: can a read-only open and a writable open hold one **non-shared** project at once? Includes the root cause of the read worker's save (memory `parse-worker-saves-xample-project`). | M-1: FR-027 on non-shared projects |
| `q2-agent.json` | Q2: is the HermitCrab parser agent present and resolvable by GUID on a copy never parsed from FLEx? (parent 17.10) | a later downgrade of `parser_agent_missing` |
| `q3-staleness.json` | Q3 / R-05: does filing one word leave `IsUpToDate()` true? | throughput only |
| `q5-checksum.json` | Q5: does `ParseResult.GetHashCode()` in our worker match the checksum FLEx stored? | the accuracy of the `unchanged` count |

## Phase 8 -- the five FR-036 cases, plus Q1 and Q4

| File | FR-036 case / question | SC |
|---|---|---|
| `q1-moveconc.json` | the `MoveConcAnnotationsToWordform` edge case: where a segment reference ends up when an analysis it points at is deleted through the generic `Delete()` path | SC-009 |
| `s2-auto-approval-survival.json` | an in-text analysis survives a pass that a bare-no-opinion projection would have condemned | SC-002, SC-009 |
| `q2-agent.json` | the HermitCrab agent lazy-creation question (shared with Phase 1) | SC-009 |
| `s2-projection-vs-actual.json` | projection versus actual deletions: every actual deletion was in the confirmed projection | SC-002, SC-009 |
| `s4-refuse-to-file.json` | refuse-to-file on a deliberately broken grammar load (new errors, a silently dropped entry, confirm-time and mid-run) | SC-005, SC-009 |
| `s1-preview-writes-nothing.json` | scenario 1: an unconfirmed request leaves the `.fwdata` byte-identical | SC-001, SC-003 |
| `s3-disapproval-overwrite.json` | scenario 3: a human disapproval overwritten by filing is projected and listed | SC-011 |
| `s5-backup-outcomes.json` | scenario 5: the stated backup intent equals the outcome; the no-recovery warning | SC-004 |
| `s6-concurrency.json` | scenario 6: second request refused in under 1 s; try-word answers during a run; crash sweep | SC-006, SC-007 |
| `q4-checker-reprobe.json` | Q4 / FR-038: the installed engine re-probed for public grammar-health checkers | -- |
| `s8-cancel.json` | scenario 8: a cancelled run reports `filed_words` and the not-undoable wording | -- |

A question that could not be run live is recorded as such, with the reason.
It is never recorded as a pass: an unrun verification is not a verification.
