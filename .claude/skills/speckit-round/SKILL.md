---
name: speckit-round
description: Run exactly ONE round of the post-clarify Companion pipeline in this (fresh) session -- the plan step, the tasks step, or one implement phase -- then stop at a boundary the disk records. Driven by scripts/speckit_rounds.py, one new session per round; also usable by hand in a fresh chat.
compatibility: Requires spec-kit project structure with .specify/ and the companion extension
---

## User Input

```text
$ARGUMENTS
```

A feature directory (`specs/NNN-name`). If absent, use `.specify/feature.json`.

## What a round is

The pipeline after clarify is split into rounds, each run by a **fresh
top-level session** so it starts near-empty and can dispatch its own
subagents:

| Round | Work |
|-------|------|
| plan | `speckit-companion-plan`, fully |
| tasks | `speckit-companion-tasks`, fully |
| implement | ONE phase of `tasks.md` -- the phase containing the next unchecked task |

All memory between rounds is on disk: `.spec-context.json` (step, status,
decisions) and the checkboxes in `tasks.md`. Nothing is carried in chat.
That is what makes a new session per round cheap: orientation is one status
call plus the artifacts this round actually needs.

## Steps

1. **Resolve.**

   ```bash
   python3 .specify/extensions/companion/scripts/status-context.py --feature-dir <feature_dir>
   ```

   Parse the final `RESOLUTION: {...}` line. If `complete: true`, end with
   `ROUND: COMPLETE`. If `empty: true` or the next step is specify/clarify,
   end with `ROUND: BLOCKED needs interactive specify/clarify`.

2. **Unattended.** This round has no human watching:

   ```bash
   python3 .specify/extensions/companion/scripts/write-context.py --feature-dir <feature_dir> --set unattended=true
   ```

   Review gates are recorded and passed, never waited on. State the
   RESOLUTION `decisions[]` as in-scope context for the step.

3. **Do the round's work by invoking the real command -- never re-enact it.**

   - **plan** -> invoke `speckit-companion-plan <feature_dir>` and let it run
     to its `--advance`. Dispatch its per-area investigation workers as the
     skill directs.
   - **tasks** -> invoke `speckit-companion-tasks <feature_dir>` and let it
     run to its `--advance`.
   - **implement** -> invoke `speckit-companion-implement <feature_dir>` with
     this scope limit: **this round owns only the phase containing
     `nextTask`** (the `## Phase` / `## Checkpoint` heading above it in
     `tasks.md`). Within that phase follow the skill exactly: wave order,
     join checks, worker dispatch, `--close-task` or `--append` +
     `--materialize` for every task. Specify/plan/tasks did **not** run in
     this session, so the reading is not spent: dispatch per the skill's
     threshold. Stop once the phase's last task is folded.
     Run implement's wrap-up (full suite via one worker, the capture
     `--batch`, living-spec accounting, `--mark-complete`) **only** if no
     unchecked task remains anywhere in `tasks.md` after this phase.

4. **Honour the project's CLAUDE.md.** It binds this session and every
   worker you dispatch: lean pytest (`-m "not requires_flex"`), never dump
   `user-logs/` or large files, update USAGE.md when tools change. If a task
   needs something this machine lacks (FieldWorks, pythonnet), end with
   `ROUND: BLOCKED <what is missing>` rather than marking it done.

5. **Stop.** Do not start the next step or the next phase, even if context
   remains. The driver starts a fresh session for it.

## Final line (the driver parses it)

End your last message with exactly one of:

```text
ROUND: DONE <one-line summary: step or phase, files touched, tests>
ROUND: COMPLETE
ROUND: BLOCKED <reason>
```

`BLOCKED` is for things a new session cannot fix by trying again: a scope
question for the developer, unverifiable live work, a repeated worker
failure, a broken environment.
