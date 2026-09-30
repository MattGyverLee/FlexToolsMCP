# Implementation Plan: parser-check CP2a-bridge + CP2b -- the assistant reaches the parser

**Scope**: CP2a-bridge (FR-011, this repository's half) and CP2b (US2, US3, US4 --
FR-012..FR-040). CP2a is **complete** and is not replanned here.

**Branch**: `feat/parser-check-cp2` proposed; this repository is currently on
`feat/parser-check-cp1`. See "Open maintainer decision" in
[`spec.md`](./spec.md) -- it blocks the first implementation task, not this plan.

**Date**: 2026-09-19

**Spec**: [`spec.md`](./spec.md) (scoping) over
[`../parser-check-cp2/spec.md`](../parser-check-cp2/spec.md) (authoritative)

**Source**: [`../parser-check/CP2-SPEC.md`](../parser-check/CP2-SPEC.md) sections 4-9

---

## Summary

CP2a made the parser reachable from a generated script. CP2b makes it reachable from
the assistant: a user asks "does this word parse, and if not, why?" and gets an
answer that came from FieldWorks' own parser. Three tools' worth of surface, one new
piece of infrastructure, and a small bridge in front of all of it.

The technical approach divides cleanly into work that has a template here and work
that does not.

**Has a template.** The two tool definitions, their Pydantic input models, the three
additive refusal models, the contract-document rows, and the `next_step` repointing
all follow patterns this repository already runs at scale -- 22 tools, four CP1
parser detail models at `response_models.py:361-416`, a data-driven `ToolDef`
registry.

**Does not.** The run machinery. Research finding R-02 is the plan's spine: **this
server process never opens a project.** Every project-touching operation today runs
in a one-shot subprocess. But the spec requires a *held* grammar, loaded exactly once
across a batch and the urgent word that interrupts it, with its currency confirmed
before each reuse. A one-shot subprocess satisfies none of that. CP2b therefore
introduces a long-lived parse worker process, and that -- not the tools -- is where
the checkpoint's risk lives. It is the "scope risk" the parent spec's register names,
and R-02 shows it is not avoidable rather than merely expensive.

The second risk is the resolver, and CP2a paid for a warning about it: a green
offline suite and four green structural ratchets coexisted with a silent wrong answer
for an entire checkpoint, because the *semantics* of an argument were assumed rather
than verified. CP2b's restricted-trace tool sits on exactly that argument.

---

## Scope fence

Recorded so it does not drift by association.

| Not in this slice | Where | Why |
|---|---|---|
| Any CP2a task | done | 31/31, evidence recorded, gate satisfied |
| `src/flextoolsmcp/server/parser_probe.py` | FR-041 / SC-016 | **0 lines changed**, exactly as CP2a did. The two capability checks diverge in both directions by design and each states what the other carries that it lacks. |
| Batch scoping, `parse_diff`, `parse_log`, `UniqueWordforms()` | CP3 | CP3 consumes this runner and adds no second execution model. The queue is built to accept `Medium`/`Low` enqueues now so that stays true. |
| Filing, `ParseFiler`, the write ladder | CP4 | `filing` exists in the stage enum and is unreachable; a test asserts no CP2b path produces it. |
| The sandbox, `hcparse.ps1` hardening | CP5 | |
| The three grammar lints | CP3, per D5 | The engine-version-specific absence must be **re-probed** there, not inherited from CP2's verdict. |

---

## Technical Context

| | |
|---|---|
| **Language** | Python 3.11+ (server); the worker is plain CPython via `sys.executable`, matching `subprocess_helpers.run_script_async` |
| **Primary dependencies** | `mcp` (capped `<2`), `pydantic`, `pyflexicon>=4.9.0,<5` (this slice raises it), `pythonnet` (worker only, transitively via flexicon) |
| **Storage** | append-only JSONL run records on disk, following `server/skeleton_storage.py`; no database |
| **Testing** | `pytest`. This repository: `python -m pytest -q`. The three flexicon test files R-08 schedules use that repository's required invocation, quoted in full below. |
| **Target platform** | Windows + FieldWorks 9 (`ParserCore.dll` 9.3.10). The server's non-parser surface stays importable without FieldWorks. |
| **Project type** | MCP server, single package |
| **Performance goals** | 5-second default grace window for a single word against a held grammar (SC-004, >=95%); lookup structures built exactly once per run (SC-007) |
| **Constraints** | at most one held grammar (SC-014); 0 parses from unconfirmed currency (SC-015); 0 runs cancelled or slowed by the window closing (SC-010); 0 results lost on kill or cancel (SC-008) |
| **Scale** | `IndonesianHC-Complete` 41 entries for correctness; `Malay Parsing-20230810withHC` 281 entries for the long-run behaviours a 41-entry project cannot exercise |

No NEEDS CLARIFICATION remains. The five unknowns the parent spec carried are
resolved in [`research.md`](./research.md); the three that remain open (E-C's
environment, E-D, the branch) are not research questions -- see below.

---

## Constitution Check

**This repository has no `.specify/memory/constitution.md`.** CP2a was governed by
flexicon's constitution because the work landed there; CP2b lands here, where none
exists. Rather than declare the gate vacuous, it is assessed against the three
standards this repository actually enforces: `CLAUDE.md`, the registered
`.specify/extensions.yml` crew gates, and the parent specification's own
non-negotiables.

Gate status before Phase 0: **PASS**. Re-checked after Phase 1 design: **PASS**.

| Standard | Assessment |
|---|---|
| **Verify the surface before building on it** (flexicon Principle I, which CP2a proved is load-bearing across the repo boundary) | **PASS, and it is why this plan differs from `CP2-SPEC.md`.** Section 3.1 of that document tabulates a facade named `TryWord`/`TraceWord`. The shipped surface is six differently-named members. The plan binds what was built, verified by reading the frozen stub, not what was specified. |
| **No live FLEx write without a human gate** | **PASS.** One live write exists in the whole slice -- scenario 7, tier A4, escalation **E-D** -- and it is scheduled as a task that **stops with `needs_human`** rather than performing it unattended. Everything else opens projects `writeEnabled=False`. |
| **Controls, not prohibitions** | **PASS.** Every guarantee that could be prose is a test that fails loudly: FR-019's "no parse runs" is a recorded-call negative assertion; SC-010's "the window is not a timeout" asserts the run advances after the handle; SC-009's interleave asserts 0 repeated words and exactly one grammar load; the bridge's equality test is **observed failing** before acceptance; the boundary test's new allowlist is pinned by a test so widening it means editing a test. |
| **Report the measurement, not the impression** | **PASS, and it constrains the bridge.** The equality test cannot prove the published distribution installs, because it is not installed here. That check is a separate task with a separate evidence line and is recorded as **not run** if it is not run (R-01). |
| **Honest API surface** | **PASS.** `READ_ONLY_SAFE` is not asserted, it is backed: a facade that cannot reach a write path, a `writeEnabled=False` open, and `HCParser_DoesNotLoadXCore` against the worker's own loaded-assembly list. |
| **`sweep-pattern` on a shaped bug** (CLAUDE.md; the gate CP2a's QC blocked on) | **PASS as an obligation, carried forward.** CP2a's null-vs-empty defect had its sweep run in flexicon with no siblings found, and recorded a **by-construction claim that CP2b re-opens**: any future binding of a CLR method taking a collection parameter renews it. CP2b binds exactly that call, so the obligation is scheduled, not assumed discharged. |
| **Live-LCM verification for write-path changes** (CLAUDE.md; non-waivable) | **N/A by scope, with one exception.** CP2b is read-only. The exception is E-D, which is gated as above. |
| **The fast path does not apply** | Correct. This is ~20 files including the transaction-shaped worker seam. Full crew cycle. |

No Complexity Tracking table: the one structural addition (the worker process) is
forced by R-02, not chosen, and its rejected alternatives are recorded there.

---

## Project Structure

All paths relative to `D:\Github\_Projects\_LEX\FlexToolsMCP` unless marked.

```
pyproject.toml                          # floor -> pyflexicon>=4.9.0,<5
requirements.txt                        # mirror of the above
src/flextoolsmcp/
  index/
    common_patterns_flexicon-v4.9.0.json        # regenerated (R-04)
    python/
      flexicon_api_v4.9.0.json                  # regenerated
      flexicon_lcm_bridge_v4.9.0.json           # regenerated
  server/
    parser_probe.py                     # UNTOUCHED -- 0 lines (FR-041 / SC-016)
    models.py                           # + TryWordInput, ParseStatusInput
    response_models.py                  # + 3 detail models (extra="forbid", Literal)
    tool_definitions.py                 # + 2 ToolDef entries, READ_ONLY_SAFE
    parse/                              # NEW package -- the run machinery
      __init__.py                       # NEW
      stages.py                         # NEW -- the 7-name enum, transitions
      priority.py                       # NEW -- the 5 levels, lowest wins, FIFO
      queue.py                          # NEW -- one sorted queue, per-wordform
      record.py                         # NEW -- JSONL run record + size cap
      runner.py                         # NEW -- grace window, lifecycle, cancel
      worker_client.py                  # NEW -- server side of the channel
      worker_main.py                    # NEW -- the long-lived child; holds the
                                        #   project, the grammar and the facade
      resolver.py                       # NEW -- MorphSpec -> MSA hvos, once/run
    handlers/
      parse.py                          # NEW -- the two handlers
      diagnostic_health.py              # next_step rows repointed (FR-038)
    dispatch.py                         # + 2 routes
docs/
  TOOL-CONTRACT.md                      # 3 rows; documented count 22 -> 25
CHANGELOG.md                            # one entry under "Tool contract"
tests/
  test_flexicon_index_floor.py          # NEW -- the bridge equality test
  test_parse_stages.py                  # NEW
  test_parse_priority_queue.py          # NEW -- ordering, FIFO, interleave
  test_parse_record.py                  # NEW -- incremental flush, kill survival
  test_parse_runner.py                  # NEW -- grace window is not a timeout
  test_parse_resolver.py                # NEW -- the three outcomes, once/run
  test_parse_proposal.py                # NEW -- traced as given; silence on agree
  test_try_word_handler.py              # NEW -- levels, engine gate first
  test_parse_status_handler.py          # NEW -- terminal != refusal
  test_parser_no_xcore.py               # NEW -- HCParser_DoesNotLoadXCore
  test_parse_live.py                    # NEW -- SC-004 / SC-012 / SC-017, read-only
  test_cp1_boundary.py                  # AMENDED, not weakened (R-06)
  test_flextools_health.py              # AMENDED -- the CP1 next_step rows that
                                        #   degraded to tool: null now name
                                        #   flextools_try_word (FR-038, SC-011)
  test_response_contract.py             # + the 3 codes
specs/parser-check-cp2b/evidence/
  cp2b-evidence.md                      # NEW -- the record, per CP2a's precedent
```

Plus three test files in **the flexicon repository** (`D:\Github\_Projects\_LEX\flexicon`),
closing R-08's gap. No production change there; CP2a's surface is frozen.

```
tests/operations/test_text_genres.py        # FR-007
tests/operations/test_allomorph_owner.py    # FR-008
tests/operations/test_msa_read.py           # FR-009
```

**Structure Decision.** The run machinery gets its own package,
`server/parse/`, rather than joining `handlers/` or extending
`subprocess_helpers.py`. Three reasons, in order of weight: it is the only part of
this repository that owns a **process lifetime**, and a package boundary is what
makes that ownership expressible; `handlers/execution.py` is already 5,341 lines and
adding a queue and a worker protocol to it would bury both; and CP3 consumes this
package directly, so a named import surface now is what stops CP3 growing a second
runner. The worker's entry point is a **module**, addressed by dotted path exactly as
`run_scan_module` addresses `scan/grammar_scan_module.py` -- the server process must
never import it, because importing it would pull pythonnet into the process that must
not hold a project.

---

## Phase 0 -- Research

Complete. [`research.md`](./research.md) carries eight findings and their decisions.
The three that change what the task list can assume:

1. **R-02 -- the server never opens a project**, so the held grammar the spec
   requires cannot live in it. A long-lived worker process is forced, not chosen.
   This is the largest single item in the checkpoint.
2. **R-01 -- `pyflexicon` 4.9.0 is published (E-C resolved), but is not installed
   here** and will not be within this session. The floor may be raised; the equality
   test compares the version the *server* resolves, not pip metadata, and a separate
   task proves the published distribution actually installs.
3. **R-08 -- the resolver's terminal accessor is untested.** `MSA.GetAll`,
   `Texts.GetGenres` and `Allomorphs.GetOwningEntry` shipped in CP2a with no test
   scheduled for any of them. FR-019's refusal is only as trustworthy as the accessor
   underneath it, so closing this is a precondition of the resolver rather than
   inherited debt to note.

---

## Phase 1 -- Design and contracts

- [`data-model.md`](./data-model.md) -- `Run`, `RunStage`, `Priority`, `MorphSpec`,
  `Resolution`, `RunRecord`, `RunFailure`, the three refusal payloads, and the worker
  channel.
- [`contracts/tools.md`](./contracts/tools.md) -- `flextools_try_word`,
  `flextools_parse_status` and the run contract, with every spec-pinned identifier
  copied exactly.
- [`contracts/bridge.md`](./contracts/bridge.md) -- the three facts that must agree,
  why `importlib.metadata` is deliberately not one of them, and the third
  version-locked artifact the Verbatim Constraints do not name.
- [`quickstart.md`](./quickstart.md) -- nine runnable scenarios, with scenario 7
  marked as the one live write.

**The evidence artifact.** This slice ends by writing
`specs/parser-check-cp2b/evidence/cp2b-evidence.md`, following CP2a's precedent: what
was *observed* per scenario, with the exact invocation that produced it, full counts
including failures, pre-existing failures named as pre-existing, and anything not run
recorded as not run. CP2a's live tier is the argument for this artifact existing --
it caught a silent wrong answer that a green suite and four green ratchets had missed
for the length of a checkpoint.

---

## Test coverage -- which test discharges which requirement

Scheduled, not asserted. Every row names a file that appears in the structure above.

| Requirement | Discharged by |
|---|---|
| FR-011, SC-013 (floor == index) | `test_flexicon_index_floor.py`, observed failing first |
| FR-011 (the published dist installs) | clean-environment install task, **separate evidence line** |
| FR-012 (three levels reach three calls) | `test_try_word_handler.py` |
| FR-013 (plain does not explain) | `test_try_word_handler.py` |
| FR-014 (guidance defaults) | `test_try_word_handler.py` |
| FR-015 (engine gate first, zero parser calls) | `test_try_word_handler.py` + `test_parse_live.py` scenario 2 |
| FR-016 (missing agent ≠ read unavailable) | `test_try_word_handler.py` |
| FR-017, SC-003 (`HCParser_DoesNotLoadXCore`) | `test_parser_no_xcore.py`, with the positive vacuity guard |
| FR-018 (headword / sense / hvo input) | `test_parse_resolver.py` |
| FR-019, SC-005 (refuse, name the piece, **0 parses**) | `test_parse_resolver.py`, negative assertion |
| FR-020, SC-007 (index built once per run) | `test_parse_resolver.py` |
| FR-021, FR-022 (proposal, labelled; guidance names only real actions) | `test_parse_proposal.py` |
| FR-023, FR-024, FR-025, SC-006 (traced as given, observation not verdict, silence on agreement) | `test_parse_proposal.py` -- a ranking-by-agreement implementation must fail it |
| FR-026 (one mechanism) | `test_parse_runner.py` + an AST check that no handler reaches the facade outside `parse/` |
| FR-027 (seven stages; `filing` unreachable) | `test_parse_stages.py` |
| FR-028, SC-010 (window reports, never cancels) | `test_parse_runner.py` |
| SC-004 (>=95% of single words answer inline inside the 5s window) | `test_parse_live.py` scenario 1 -- a **measured rate over repeated attempts against a held grammar**, not a boolean. The observed rate and the attempt count go in the evidence artifact; a single fast call is not this criterion. |
| FR-029, SC-008 (incremental, survives kill) | `test_parse_record.py` |
| FR-030 (priority, FIFO, per-wordform) | `test_parse_priority_queue.py` |
| FR-031, SC-009 (interleave; 0 repeats; one grammar load) | `test_parse_priority_queue.py` + `test_parse_live.py` scenario 6 |
| FR-032 (cooperative cancel) | `test_parse_priority_queue.py` |
| FR-033, FR-036 (terminal is a success, not a refusal) | `test_parse_status_handler.py`, both directions |
| FR-034 (failure carries diagnostic guidance) | `test_parse_status_handler.py` |
| FR-035 (unknown handle names the available ones) | `test_parse_status_handler.py` |
| FR-037 (3 codes, field **order**, count 22 -> 25) | `test_response_contract.py` |
| FR-038, SC-011 (every CP1 `tool: null` row repointed; 0 dangling tools) | `test_flextools_health.py` amendment + a registry sweep |
| FR-039 (CP1's deferred SPEC 16 groups) | the full suite; enumerated in the evidence artifact |
| FR-040 (D5 deferral recorded) | documentation task, no test |
| SC-012 (all three levels succeed live, restricted driven by a caller-supplied decomposition) | `test_parse_live.py` scenarios 1, 3 and 4a against `IndonesianHC-Complete` |
| SC-017 (the long-run behaviours live) | `test_parse_live.py` scenarios 5 and 6 against `Malay Parsing-20230810withHC` -- grace-window overflow, word-boundary interleave, cooperative cancel, partial-result survival. 41 entries cannot exercise these; the project split is not interchangeable. |
| FR-041, SC-016 (0 lines in `parser_probe.py`) | `git diff --stat` in the evidence artifact, as CP2a recorded it |
| FR-042, SC-014 (one held grammar, released on switch) | `test_parse_live.py` |
| FR-043, SC-015 (currency confirmed; reset-then-reload) | `test_parse_live.py` (the **current** half) + **E-D** for the live stale half |
| R-06 (CP1 boundary amended, allowlist pinned) | `test_cp1_boundary.py` |
| R-08 (the three read gaps) | three files in the flexicon repository |

**Two obligations this table does not let hide.**

- **FR-043 is only half dischargeable here.** The live stale branch is E-D. The
  evidence artifact must say so explicitly rather than showing FR-043 green.
- **The pattern-audit obligation is live.** CP2a's sweep found no siblings and
  recorded a by-construction claim that *any future binding of a CLR method taking a
  collection parameter re-opens it*. `resolver.py` feeds `TraceWordXml`'s collection
  parameter, so the audit is re-run here and its result goes in the evidence
  artifact -- this is the gate CP2a's QC blocked on, and a repeat is not acceptable.

---

## Sequencing

Constrained, not stylistic. Each phase's output is the next phase's precondition.

**Phase A -- the bridge.** Regenerate the index; raise the floor in both files; add
the equality test and **watch it fail** before accepting it; run the full suite.
CP2b's first parser task may not start until this has landed. The separate
clean-environment install check may lag; it does not gate.

**Phase B -- close R-08, in flexicon.** Three test files for `Texts.GetGenres`,
`Allomorphs.GetOwningEntry` and `MSA.GetAll`. Before the resolver, because the
resolver's correctness claim rests on the third of them. Required invocation, quoted
per that repository's Constitution Principle II:

```
python -m pytest -m "not requires_live_project" -q
```

`pytest --ignore=tests/contract` is prohibited there and appears nowhere in this
plan.

**Phase C -- the run machinery, bottom-up.** `stages` -> `priority`/`queue` ->
`record` -> `worker_main`/`worker_client` -> `runner`. Each with its tests before the
next. The worker is built and proven against a *stub* parse before it is pointed at
the real facade, so a queue defect and a parser defect cannot be confused for one
another -- which is the distinction CP2a's live tier needed and did not have until it
ran.

**Phase D -- the resolver.** Needs Phase B. Its three failure outcomes and its
once-per-run index are the correctness risk of this checkpoint.

**Phase E -- the two tools.** Input models, detail models, `ToolDef` entries,
handlers, dispatch routes, contract rows, CHANGELOG. Needs C and D.

**Phase F -- the standing guarantees and the carry-over.** `HCParser_DoesNotLoadXCore`;
the `test_cp1_boundary.py` amendment; the CP1 `next_step` repointing; D5's deferral
recorded; the full suite including CP1's deferred SPEC 16 groups.

**Phase G -- live verification.** `IndonesianHC-Complete` for the three levels,
`Malay Parsing-20230810withHC` for grace-window overflow, interleave, cancellation
and partial-result survival. Read-only throughout.

**Phase H -- E-D, and only with a human.** Tier A4. The loop **stops** here with
`needs_human` if nobody is watching. It must run against a backed-up or copied
project, never an installed one relied on for anything else.

**Phase I -- the evidence artifact**, then the crew's `after_implement` gates.

---

## Risks specific to this slice

- **The worker process is the scope risk, and it is now also a lifetime risk.**
  `subprocess_helpers._kill_process_tree` exists because a pythonnet grandchild
  holding a `.fwdata` lock is a known failure here (issue #57). A *long-lived* holder
  makes that worse. Idle release, shutdown teardown and the orphan case are scheduled
  as tests, not left to review.

- **The resolver is the correctness risk, and CP2a paid for the warning.** A green
  offline suite and four green structural ratchets coexisted with a silent wrong
  answer for a whole checkpoint, because an argument's *semantics* were assumed. The
  resolver feeds exactly that argument. Its three failure outcomes must stay distinct
  and its refusal must fire before the facade is reached -- an `FP_ParameterError`
  surfacing as an internal error is this tool's defect, not a safety net.

- **`CP2-SPEC.md` section 3.1 is stale and will mislead an implementer who reads it
  first.** It names `TryWord`/`TryWordXml`/`TraceWord`; none exists. The plan records
  the real six-member surface in `spec.md` Delta 1, and a task updates that section in
  place so the next reader is not misled again.

- **No CI.** No workflow runs pytest on a hosted runner and the self-hosted
  `[windows, fieldworks]` pool has zero registered runners. Every measurement in this
  plan is local and manual, which is what raises the stakes on the evidence artifact's
  exact-invocation discipline.

- **E-D is the only live write, and an unattended loop must not perform it.** The
  failure mode is not a bad test result; it is a written-to FLEx project nobody
  authorised.
