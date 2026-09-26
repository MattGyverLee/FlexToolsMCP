---
name: speckit-conductor
description: Run the post-clarify Companion pipeline (plan -> tasks -> implement) unattended from a thin conductor that keeps its own context small by giving every heavy step to a fresh subagent and reading state from disk. Safe to re-run in a fresh chat at any point; it resumes.
compatibility: Requires spec-kit project structure with .specify/ and the companion extension
---

## User Input

```text
$ARGUMENTS
```

Optional: a feature directory (`specs/NNN-name`). Otherwise `.specify/feature.json` decides.

## What this is for

`speckit-companion-auto` runs every step in *this* chat, so plan, tasks and
every inline implement phase pile into one context -- and because
`speckit-companion-implement` sees that the whole pipeline "ran in front of
it", it builds every phase inline instead of fanning out. That is the heavy,
long-running chat.

Stopping after each step and restarting by hand is the other extreme.

The conductor sits between them. Specify and clarify stay interactive and
happen before this. From there the conductor:

- keeps **no artifact bodies** in its own context -- it never reads
  `spec.md`, `plan.md`, `research.md`, `data-model.md` or source files;
- hands **plan** and **tasks** each to a fresh subagent that invokes the real
  Companion command and returns a short summary;
- runs **implement** itself, but as a dispatcher: every phase that owns
  files goes to its own worker, the conductor only folds results and checks
  joins;
- treats `.spec-context.json` + `tasks.md` as the only memory, so a fresh
  chat running this skill again picks up exactly where the last one stopped.

Target conductor footprint: well under 100K for a normal feature. If it
gets heavy anyway, stop at the next boundary (see "Handoff") -- restarting
costs one status call, not a re-read.

## Rules for the conductor

1. **Invoke, don't reproduce.** Every step is the real
   `speckit-companion-*` command, run by whoever you hand it to. Never write
   plan, tasks or code yourself.
2. **Never read artifacts into your own context.** Your inputs are the
   `RESOLUTION:` line from `status-context.py`, the `Files:` lines and task
   IDs from `tasks.md` (grep them, don't Read the file), and the distilled
   summaries workers return.
3. **Workers return summaries, never file contents.** Say so in every
   dispatch: at most ~15 lines -- what was produced, files touched, tests
   failing, open concerns.
4. **Don't end the turn between steps.** Loop until `complete: true`, a
   real blocker, or a handoff boundary. Stopping after a step is the manual
   flow; this skill exists to not do that.
5. **All `.spec-context.json` writes go through `write-context.py`**, in the
   foreground, one at a time. Workers only `--append`; you `--materialize`.

## Loop

### 0. Mark unattended, resolve

```bash
python3 .specify/extensions/companion/scripts/write-context.py --feature-dir <feature_dir> --set unattended=true
python3 .specify/extensions/companion/scripts/status-context.py --feature-dir <feature_dir>
```

Parse the final `RESOLUTION: {...}` line. Branch:

- `complete: true` -> report done, stop.
- `empty: true`, or the next step is `specify`/`clarify` -> stop and tell the
  developer to run `speckit-companion-specify` / `speckit-clarify` first.
  Those are interactive by design.
- next step `plan` -> step 1. `tasks` -> step 2. `implement` (or `nextTask`
  set) -> step 3.

Re-run `status-context.py` after every step; always branch on what the disk
says, never on what you remember.

### 1. Plan -> one fresh subagent

Dispatch a general-purpose subagent (foreground; you need its result):

> This run is unattended (`unattended: true` in .spec-context.json): record
> review gates and continue, never wait for a human. Invoke the
> `speckit-companion-plan` skill for `<feature_dir>` and let it run fully,
> including its timing and capture calls and `--advance`. If you cannot
> dispatch your own subagents, do the per-area investigation inline as the
> skill's fallback says. Return at most 15 lines: artifacts written, key
> decisions, anything left NEEDS CLARIFICATION. No file contents.

If it reports unresolved NEEDS CLARIFICATION that changes scope, stop and
hand it to the developer -- that is a clarify question, not a planning one.

### 2. Tasks -> one fresh subagent

Same shape, invoking `speckit-companion-tasks`. Ask for: phase list, task
count per phase, each phase's `Files:` count, any file owned by two phases.

### 3. Implement -> you dispatch, workers build

You run `speckit-companion-implement` yourself, reading its body for the
rules (wave order, join checks, `--append`/`--materialize`, the final
`--batch` capture, living-spec accounting, `--mark-complete`). Because plan
and tasks ran in subagents, its "did the pipeline run in this session?" test
is **no**: the reading is not spent, so dispatch. Apply one change to its
threshold, for context rather than cost:

- **Every phase that owns files goes to a worker** -- Setup, Foundational
  and Polish included -- unless it owns two files or fewer, which you may
  build inline. Foundational still blocks the story phases: dispatch it
  alone and wait.
- Story phases with disjoint `Files:` lines go out together in one message.
- Each worker gets: its phase's task lines, its user story from the spec
  (the worker reads it, not you), the plan's Structure Decision, its
  living-spec slice, the `--append` command, the instruction to run only
  the tests its phase owns, and the 15-line return rule.
- After each result: `--materialize`, then verify the claimed files exist
  (`ls`/`test -f`, not Read). One corrective re-run on a bad claim; a second
  failure stops the step.
- At the end: hand typecheck/lint/full test suite to one worker and take
  back only the verdict and failing names. Then the capture `--batch`,
  living-spec accounting and `--mark-complete`, exactly as implement says.

Project rules still bind the workers: point each one at CLAUDE.md, and have
it run tests the lean way CLAUDE.md gives (`-m "not requires_flex"`). Tell
workers never to cat `user-logs/` or dump large files; the read guard will
block them anyway.

## Handoff (the anti-thrash rule)

Only ever stop at a boundary the disk already records: after plan, after
tasks, or after a phase's `--materialize`. Never mid-phase.

Stop and hand off when either holds:

- the conversation has auto-compacted once, or you have run four or more
  implement phases in this chat and the next one is large;
- a worker returned a blocker you cannot resolve from its summary.

On handoff, print one line the developer can paste into a fresh chat:

```text
/speckit-conductor <feature_dir>
```

plus the `RESOLUTION` `nextActionLabel`. Nothing else needs carrying over --
decisions live in `.spec-context.json` and task state in `tasks.md`.

## Output

Per step, one line: `[OK] plan -- <artifacts>` / `[OK] Phase 3 (US1) -- 6 files, tests green`.
At the end: phases dispatched vs. built inline, failing tests if any, and
the final status from `status-context.py`.
