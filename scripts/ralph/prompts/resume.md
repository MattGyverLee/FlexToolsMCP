# LEX crew spurt -- implement leg, unattended, fresh session

You are resuming the FlexToolsMCP **parser-check** campaign mid-implementation.
This is a BRAND NEW session with no memory of previous spurts. The pipeline
already knows where you are -- do not reconstruct it from prose.

| | |
|---|---|
| Checkpoint | **{{CP}}** -- {{TITLE}} |
| Feature dir | `{{FEATURE_DIR}}` |
| Recorded step | `{{CURRENT_STEP}}` / `{{SPEC_STATUS}}` |
| Next task | **{{NEXT_TASK}}** |
| Iteration | {{ITERATION}} of at most {{MAX_ITERATIONS}} |

## Do this

1. Run `/speckit.companion.resume`. It re-resolves state itself and dispatches
   `{{NEXT_COMMAND}}` at **{{NEXT_TASK}}**. Let it drive -- do not hand-pick
   tasks, and do not re-plan.
2. Work forward to the **next checkpoint boundary only**: a `tasks.md`
   "Checkpoint:" line, the end of the current wave/user story, or ~2 crew
   cycles -- whichever comes first. Then stop. Do not finish the feature in one
   session just because tasks remain.
3. The pipeline's registered `after_implement` hooks (`/lex-qc`, and
   `/lex-verification` for any write-path change) fire as part of the implement
   step. Let them run and act on what they report; a hook that reports a
   blocking finding means the spurt ends at that finding, not past it.

## Then close the spurt (mandatory)

1. Update `STATUS.md` -- what landed, what the next pickup is.
2. Update `{{FEATURE_DIR}}/.crew-handoff.json` -- full machine-state shape.
   This is the outer driver's control signal; it reads nothing else.
3. `git add -A && git commit` the spurt{{PUSH_CLAUSE}}.
4. End your **final message** with the `handoff` fenced block, `status` exactly
   one of `in_progress` / `needs_human` / `feature_complete`. Add the literal
   `<promise>FEATURE COMPLETE</promise>` only alongside `feature_complete`.

## Hard rules

- **No live FLEx write.** If the next task requires writing to a FieldWorks
  project, stop now with `status: needs_human` and a one-line `blocker`.
  Read-only project opens are fine.
- Do **not** start `/ralph-loop` -- the outer driver owns iteration.
- No `git push --force`; no unrecorded branch switches.
- Keep context small: delegate reading to subagents, relay report paths rather
  than report bodies.
