# Ralph campaign driver (fresh context per spurt)

Runs the LEX crew through a multi-checkpoint feature unattended, **one bounded
spurt per brand-new `claude -p` session**, so no single context window grows
past the compaction threshold.

## Why not `/ralph-loop`

The `ralph-loop` plugin's Stop hook re-feeds the standing prompt **in-session**.
Iteration 6 still carries iterations 1-5 in its context; the only relief is
auto-compaction. That is fine for two or three spurts and wrong for a
four-checkpoint campaign.

This driver inverts it: the loop lives in PowerShell, each iteration is a new
process with an empty window, and continuity comes from the files the crew
already maintains:

| carrier | what it holds |
|---|---|
| `STATUS.md` | prose handoff: what landed, what the next pickup is |
| `specs/<feature>/.crew-handoff.json` | machine state; **the driver's control signal** |
| `specs/<feature>/reviews/cycle<N>-<agent>.md` | specialist reports (paths relayed, never bodies) |
| `tasks.md` checkboxes + git log | what is actually done |

The `.crew-handoff.json` `status` field is the whole protocol:

- `in_progress` -> driver starts another fresh session
- `needs_human` -> driver stops and prints `blocker`
- `feature_complete` -> driver advances to the next checkpoint

## Files

```
scripts/ralph/campaign.json        CP2..CP6: slug, dir, scope, scope refs, write flag, depends_on
scripts/ralph/prompts/spurt.md     full crew briefing  (spec / plan / review legs)
scripts/ralph/prompts/resume.md    thin brief          (implement leg)
scripts/ralph/run-campaign.ps1     the driver
.specify/extensions.yml            LEX crew review gates, registered as pipeline hooks
reports/ralph/<stamp>/             per-iteration rendered prompt + stream-json log (gitignored)
reports/ralph/_fixture/            tiny fixture for exercising the resume branch (gitignored)
```

## Two prompts, chosen per iteration

Before each session the driver runs the Companion resolver
(`status-context.py --feature-dir <dir>`, read-only) and parses its trailing
`RESOLUTION: {json}` line -- the same line `/speckit.companion.resume` parses.

- **`nextTask` is set** (inside implement) -> `prompts/resume.md`. The pipeline
  already knows the exact restart point from `tasks.md` order vs journaled
  checkboxes, so the session gets a short "run `/speckit.companion.resume`,
  work to the checkpoint boundary, hand off" brief instead of a full crew
  briefing. Cheaper session, no position re-derivation from prose.
- **otherwise** (specify / plan / review legs, or no resolution available)
  -> `prompts/spurt.md`, the full crew briefing.

The iteration header prints which one was chosen:
`--- CP3-iter04  (handoff: in_progress | prompt: resume @ T014) ---`.

## Crew gates live in the pipeline, not in the prompt

`.specify/extensions.yml` registers the LEX crew as spec-kit extension hooks, so
the gates fire for an unattended campaign run, an interactive
`/speckit.companion.plan`, and a bare `/speckit.companion.resume` alike:

| hook | agent | optional | why |
|---|---|---|---|
| `after_specify` | `/lex-domain` | no | spec vs LCM/FieldWorks reality -- CP2 spurt 1 found five blocking falsehoods of exactly this class |
| `after_plan` | `/lex-qc` | no | does the plan schedule the coverage and pattern-audit obligations it asserts |
| `after_implement` | `/lex-qc` | no | code-quality gate; blocks on missing pattern audit or missing live-LCM evidence |
| `after_implement` | `/lex-verification` | yes | live-LCM pre/post evidence, write-path changes only |

Three contract details that shaped the file:

1. `optional: false` emits `EXECUTE_COMMAND:` and the host **waits**;
   `optional: true` merely offers the hook.
2. A hook with a non-empty **`condition` is skipped** by the companion command
   body (conditions are left to the HookExecutor). So no gate here uses one --
   `/lex-verification`'s "write paths only" scoping lives in its `prompt` text.
3. Hook dispatch is **model-mediated**: the command bodies instruct the agent to
   read this YAML and emit the hook block. It is not enforced by a parser, so a
   session can in principle skip a gate. The driver's prompts name the same
   gates as a backstop, and `/speckit.companion.doctor` will show a step that
   completed without them.

Because these are project-level hooks, they now fire on **every** spec-kit run
in this repo, not just campaign runs. Set `enabled: false` on an entry to mute
one.

## Usage

`campaign.json` also lists the in-flight **CP2**, so the same rig can finish it
-- and running one real CP2 spurt is the cheapest way to validate the driver
before handing it four unattended checkpoints.

```powershell
# See what would run and read the rendered prompt first. Always do this once.
powershell -File scripts/ralph/run-campaign.ps1 -Only CP3 -DryRun

# Finish the in-flight checkpoint (follows its handoff next_entry: plan CP2a only).
powershell -File scripts/ralph/run-campaign.ps1 -Only CP2 -MaxIterations 2

# One checkpoint, attended-ish (watch the tool trace scroll by).
powershell -File scripts/ralph/run-campaign.ps1 -Only CP3

# CP3 then stop, capped at 8 sessions.
powershell -File scripts/ralph/run-campaign.ps1 -StopAfter CP3 -MaxIterations 8

# The whole campaign. Halts on its own at CP4 (write checkpoint).
powershell -File scripts/ralph/run-campaign.ps1
```

### Parameters

| flag | default | note |
|---|---|---|
| `-Only <CPn>` | all | run a single checkpoint |
| `-StopAfter <CPn>` | -- | stop once that checkpoint completes |
| `-MaxIterations` | 12 | fresh sessions per checkpoint before halting |
| `-MaxBudgetUsd` | 15 | per session, via `claude --max-budget-usd` |
| `-Model` | `opus` | passed through to `--model` |
| `-PermissionMode` | `bypassPermissions` | with `--permission-prompts none`, so nothing can hang waiting for a human |
| `-AutoCompactTokens` | 300000 | `--autocompact`: a ceiling, not a target -- a well-bounded spurt should land far below it |
| `-AllowWriteCheckpoints` | off | required to touch CP4 at all |
| `-IgnoreDependencies` | off | skip the `depends_on` predecessor gate |
| `-NoPush` | off | spurts commit but do not push |
| `-DryRun` | off | render prompts, start nothing |

## Stop conditions

The driver exits non-zero rather than grinding:

| exit | meaning |
|---|---|
| 1 | `claude` exited non-zero; see the iteration's `.jsonl` log |
| 2 | handoff says `needs_human`; the blocker is printed |
| 3 | two consecutive iterations produced **no commit and no handoff change** (stall) |
| 4 | `-MaxIterations` hit |

It also refuses to start if `.claude/ralph-loop.local.md` exists -- an in-session
ralph loop and this driver would fight over iteration.

## Safety posture

- **CP4 is gated.** It is the first write checkpoint (`ParseFiler`, live filing).
  The driver will not run it without `-AllowWriteCheckpoints`, and even then the
  spurt prompt forbids a live FLEx write and requires `needs_human` at the first
  filing task. Automate CP4's spec/plan/tasks; supervise its implementation.
- The spurt prompt bans `git push --force`, branch switches that are not recorded,
  and starting a nested ralph loop.
- `bypassPermissions` is scoped to this repo's working directory plus whatever
  `extra_dirs` the campaign entry declares. Drop to `-PermissionMode acceptEdits`
  if you would rather have non-allowlisted Bash denied outright -- but expect the
  crew to lose `pytest`/`git`/`python` unless `.claude/settings.json` allows them.
- **`extra_dirs` grants file access, not command execution.** `--add-dir` lets a
  spurt read and edit files in another repo; it does **not** authorise Bash
  scoped to that directory. Under `acceptEdits`, `git -C <other-repo> status` and
  a `pytest` run over there are both denied with "no approval surface". For a
  checkpoint whose work lands in a sibling repo -- CP2a is 30-of-31 in
  `flexicon` -- `extra_dirs` alone is not enough: run at the documented
  `bypassPermissions` default, or add allow rules covering
  `git -C <other-repo> *` and that repo's test invocation. CP2 spurt 5 burned a
  full session discovering exactly this and could not even commit its own
  findings.
- **The stall detector watches `HEAD` in *this* repo only.** For a sibling-repo
  checkpoint, the commits it would look for land elsewhere. What saves it is the
  handoff-hash half of the test: every spurt must update
  `specs/<feature>/.crew-handoff.json` here, so real progress always moves one of
  the two signals. Keep that obligation in the prompt if you touch it.

## Keeping each session small

Fresh contexts only help if a single spurt stays small. The three disciplines
already in `CLAUDE.md` do the work; the prompt restates them:

1. **Bound every plan to the next checkpoint** (a `tasks.md` "Checkpoint:" line,
   one user story, or ~2 crew cycles).
2. **Relay report paths, not bodies.** Specialists write to
   `specs/<feature>/reviews/`; the main session passes the path + 2 lines.
3. **End each spurt with a handoff**, never a dangling dispatch.

A spurt that blows past ~300k is a spurt that was not bounded -- fix the
checkpoint granularity in `campaign.json`, not the compaction setting.

## Adding a checkpoint

Append to `checkpoints[]` in `campaign.json`:

```json
{
  "id": "CP7",
  "feature": "parser-check-cp7",
  "feature_dir": "specs/parser-check-cp7",
  "title": "short human label",
  "writes": false,
  "depends_on": "parser-check-cp6 at feature_complete",
  "scope": "one paragraph the specify step can be scoped to",
  "scope_refs": ["specs/parser-check/SPEC.md section N"],
  "extra_dirs": []
}
```

The driver bootstraps the spec itself: when `<feature_dir>/spec.md` is absent,
the first spurt's only job is to create it via `/speckit.companion.specify`
scoped to `scope`, then hand off.
