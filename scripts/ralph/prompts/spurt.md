# LEX crew spurt -- unattended, fresh session

You are resuming the FlexToolsMCP **parser-check** campaign. This is a BRAND NEW
session: you have no memory of any previous spurt. Your memory is on disk --
`STATUS.md`, the crew handoff json, `tasks.md` checkboxes, the `reviews/` files,
and git history. Read them; do not guess.

An outer driver script owns iteration. It will start another fresh session after
you stop. Your job is **exactly one bounded checkpoint of work**, then a clean
handoff.

| | |
|---|---|
| Checkpoint | **{{CP}}** -- {{TITLE}} |
| Feature slug | `{{FEATURE}}` |
| Feature dir | `{{FEATURE_DIR}}` |
| Parent spec | `{{PARENT_SPEC}}` ({{ROADMAP_SECTION}}) |
| Iteration | {{ITERATION}} of at most {{MAX_ITERATIONS}} |

## Step 0 -- orient (read in this order, nothing else first)

1. `STATUS.md`
2. `{{FEATURE_DIR}}/.crew-handoff.json` -- **absent means this checkpoint has not started**
3. `{{PARENT_SPEC}}` {{ROADMAP_SECTION}}, the `{{CP}}` row
4. These scope references: {{SCOPE_REFS}}
5. `git log --oneline -15` and `git status -s`

## Step 1 -- if `{{FEATURE_DIR}}/spec.md` does NOT exist

This spurt's only job is to create the checkpoint spec. Follow the shape the
previous checkpoint used (`specs/parser-check-cp2/`): a cycle-1 recon pass
through `/lex-lead` first if the surface is unknown, then
`/speckit.companion.specify` scoped to:

> {{SCOPE}}

Do **not** plan, do **not** generate tasks, do **not** implement in this spurt.
Close with a handoff and stop.

## Step 2 -- otherwise, run ONE bounded spurt

Invoke `/lex-lead` in spurt mode with the current state. Follow the LEX Crew
Dispatch Protocol in `CLAUDE.md` exactly:

- execute each `dispatch_plan` group yourself (parallel groups in a single message),
- relay **report FILE PATHS + 2-line summaries**, never report bodies,
- re-invoke `/lex-lead` until it returns a `handoff` block instead of a plan.

The pipeline's own review gates are registered in `.specify/extensions.yml`
and fire from inside the spec-kit steps: `/lex-domain` after specify,
`/lex-qc` after plan and after implement, `/lex-verification` (optional) after
implement for write-path work. Do **not** dispatch those same agents again
through `/lex-lead` for the same artifact -- let the hook's report stand and
act on it. Dispatch crew members the hooks do not cover (Explore, lex-archivist,
lex-doc, lex-simplify, lex-author) as the plan calls for them.

Bound the work to the **next checkpoint only** -- a `tasks.md` "Checkpoint:" line,
one completed user story, or ~2 crew cycles, whichever comes first. Never chain
the whole checkpoint in one session.

## Step 3 -- close the spurt (mandatory, every time)

1. Update `STATUS.md` (prose handoff: what landed, what the next pickup is).
2. Update `{{FEATURE_DIR}}/.crew-handoff.json` (machine state, full shape).
3. `git add -A && git commit` the spurt{{PUSH_CLAUSE}}.
4. End your **final message** with the `handoff` fenced block. `status` must be
   exactly one of `in_progress`, `needs_human`, `feature_complete`.
   - `feature_complete` also requires the literal token
     `<promise>FEATURE COMPLETE</promise>` in that same message.

The driver reads `{{FEATURE_DIR}}/.crew-handoff.json` after you exit. If `status`
is still `in_progress` it starts the next fresh session. If it is `needs_human`
it stops and shows the user your `blocker`. If the file did not change and no
commit landed, it treats the iteration as a stall and stops.

## Hard rules for this unattended run

- **No live FLEx write. None.** If the next task requires writing to a FieldWorks
  project, stop immediately with `status: needs_human` and a one-line `blocker`.
  Read-only project opens are fine.
- **Do not start `/ralph-loop`.** The outer driver owns iteration; an in-session
  Stop-hook loop would defeat the whole point of fresh contexts.
- **Do not `git push --force`**, do not push a branch other than the current one,
  and do not switch branches without recording the switch in `STATUS.md`.
- **Cut `feat/parser-check-{{CP_LOWER}}` before the first IMPLEMENTATION task** of
  this checkpoint -- not before a spec or plan pass.
- **Keep your own context small.** Delegate reading to subagents and relay paths.
  You should not need to read a 1900-line spec end to end; grep to the section.
- If you find yourself past the checkpoint boundary, stop and hand off rather
  than continuing "just to finish".
