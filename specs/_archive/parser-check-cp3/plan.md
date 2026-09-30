# Implementation Plan: parser-check CP3 -- the corpus, the artifact, and the diagnosis

**Branch**: `feat/parser-check-cp3` (proposed; not created by this command). Repository is on `main` at `b896633`.

**Date**: 2026-09-22

**Spec**: [`spec.md`](./spec.md) (scoping) over [`../parser-check/SPEC.md`](../parser-check/SPEC.md) section 15 (authoritative)

**Source**: [`../parser-check/CP3-SPEC.md`](../parser-check/CP3-SPEC.md), 887 lines -- **re-verified against shipped code, not trusted** (see research R-02)

**Predecessors**: CP1, CP2, CP2a-bridge, CP2b -- all landed; entry gate satisfied

---

## Summary

CP3 is the first checkpoint that answers a question about a whole project, and
the first that leaves something behind. A linguist names a genre, gets a
definite word list, parses it, reads the run back, edits the grammar, parses
again, and is told what changed.

The technical approach divides on one line: **what CP2b already built, and
what has never existed.**

**Already built, and consumed as shipped.** The job runner, its seven stages,
its cooperative cancellation, its per-wordform queue, its grace window, its
long-lived worker, and the run record on disk. Research R-01 and R-02 found
that FR-014's "no second execution model" and D-6's artifact layout are not
constraints to work around -- they describe the cheapest implementation
available, because `queue.enqueue_run` already takes a priority and enqueues
one item per word, and `record.py` already writes `meta.json`,
`results.jsonl` and `traces/<n>.xml` with a per-line `fsync`. The batch is a
`Priority.LOW` call site.

**Never existed.** Scope resolution, the scope fingerprint, the durable
analysis signature, the comparison, the five batch signals, the completeness
tiering, the approval-provenance join, promotion-only ranking, clustering, and
the bounded measurement. This is where the checkpoint's build and all of its
risk live.

Three things make this plan's shape different from CP2b's:

1. **The artifact is a forward commitment.** CP4 and CP5 both read the run
   record and the per-word stream. Phase 2 settles that shape before Phase 4
   or Phase 5 writes anything that consumes it.
2. **US5 is larger than everything else combined.** Eight distinct pieces of
   build under one user story, one of which (side-by-side rule-chain
   comparison) is net-new rather than a presentation of engine output. It is
   planned as its own phase, per the spec's own risk register.
3. **One function is the correctness risk.** Promotion-only ranking has a
   natural implementation that is shorter than the correct one and confidently
   wrong. SC-014's fixture is written red first (R-10). This is not a general
   test-first preference; it is scheduled that way because the wrong shape is
   the attractive one.

CP3 is entirely read-only. FR-063's standing test asserts that, and it is the
gate the checkpoint cannot ship without.

---

## Scope fence

Recorded so it does not drift by association. Every row is a thing a
reasonable implementer might otherwise pull in.

| Not in this slice | Where | Why |
|---|---|---|
| Any write to a FieldWorks project | CP4 | FR-063, SC-021. Asserted by a standing test, not by inspection |
| Filing, the write ladder, confirmation flow | CP4 | The `filing` stage stays inbound-edgeless (`stages.py:118`); the unlock argument is **absent from the schema** (FR-025/D-1) |
| Acting on either projection | CP4 | FR-050: compute, may report, act on neither |
| Sandbox spine, sandbox tool, config cache, corpus assertions | CP5 | FR-015: those files are not written and are **not created empty**; FR-028 returns a typed not-applicable naming the spine |
| The counting trace instrument | deferred | No engine seam exists. CP3 must not reflect into engine internals for it, and must not plan around the seam appearing |
| A scalar grammar score, severity, verdict wording | never | The parent spec's measured anti-correlation result forbids it; the shipped grammar scan already carries neither |
| Grammar authoring / editing a loose rule | out | Naming it is in scope; editing it is not |
| A second execution model, a batch-specific worker | forbidden | FR-014. A structural runner need is an **escalation**, not an absorbable task |
| `parser_probe.py` | unchanged | Zero lines, as CP2a and CP2b both held |
| Renaming shipped artifact files | rejected | D-6: the parent spec's 5.5 listing is the thing that is wrong, and CP3 corrects **it** |
| A writing-system fallback for genre matching | out | Assumption: default analysis WS is acceptable for CP3, **with the limitation disclosed** (FR-008) |

---

## Technical Context

| | |
|---|---|
| **Language/Version** | Python 3.11+ (server and worker). Generated FLExTools scripts target IronPython via `pyflexicon` |
| **Primary Dependencies** | `pyflexicon >= 4.9.0, < 5` (parser surface + the three read gaps); `mcp` (tool surface); `pydantic` v2 (`ConfigDict(extra="forbid")` detail models); `pythonnet` in the worker only |
| **Storage** | Filesystem run records under `record.get_record_dir()` -- `meta.json`, `results.jsonl`, `traces/<n>.xml`, plus CP3's one net-new `words.txt`. No database |
| **Testing** | `pytest`. Offline suite is the default; live-project groups are marked and run against the two designated projects |
| **Target Platform** | Windows with FieldWorks installed (live paths); headless CI for the offline suite |
| **Project Type** | Single Python package -- an MCP server (`src/flextoolsmcp/`) with a long-lived parse worker subprocess |
| **Performance Goals** | A batch runs for hours and that is expected. The binding constraints are **not** throughput: grammar loaded exactly once per batch-plus-interleave (SC-006), a single-word request answered without waiting for the batch (SC-005), and progress that does not appear to stall (FR-026) |
| **Constraints** | Read-only (FR-063); no project-wide claim and no blocking of a concurrent lexicon edit (FR-061, SC-020); contract stays `tool-responses/1.0` (FR-059); no live data-model references serialized (FR-021); no invented engine step counts (FR-053) |
| **Scale/Scope** | Three new tools, five new refusal codes, one net-new artifact file, ~15 new modules. Word lists in the tens of thousands on the designated scale project; retention 20 runs per project |

**Unknowns**: none blocking. The two live questions (FR-001, FR-003) are
scheduled as Phase 1 tasks with mandated safe defaults, and identifier
stability is an assumption with a specified fallback (FR-033). See research
R-08 and the Risk register.

---

## Constitution Check

*GATE: must pass before Phase 0 research. Re-checked after Phase 1 design.*

**There is no `.specify/memory/constitution.md` in this repository.** Gates are
therefore taken from the standing rules the campaign actually enforces: the
project's `CLAUDE.md`, the parent spec's cross-checkpoint obligations, and the
`lex-crew` review gates registered in `.specify/extensions.yml`.

| Gate | Source | Status |
|---|---|---|
| Invent nothing -- no fabricated API, no invented number | campaign standing rule | **Pass.** FR-053 forbids an engine step count; FR-029 returns raw-and-labelled rather than an invented explanation; FR-057 forbids naming a nonexistent tool |
| Read-only by default; writes explicitly gated | `CLAUDE.md`, philosophy | **Pass by construction.** CP3 ships no write path at all (FR-063) |
| No second execution model | FR-014, CP2b scope fence | **Pass.** R-01: the batch is an existing call site |
| Additive contract changes only | FR-059 | **Pass.** Five new codes, `tool-responses/1.0` unchanged, 25 -> 30 |
| Pattern audit on a shaped bug | `lex-qc` gate | **Scheduled.** Two shaped classes are already known: name-sorted retention (R-03) and first-genre-only reads (FR-006). Both get an explicit sweep task |
| Live-LCM evidence for write-path work | `lex-verification` gate | **N/A by scope, and that is itself the claim.** There is no write path. The gate is discharged by FR-063's standing test, not by skipping it |
| Live verification on the designated projects | SC-022 | **Scheduled.** `IndonesianHC-Complete` and `Malay Parsing-20230810withHC`. Explicitly **not** `Sena 3` -- it reports engine `XAmple` and this feature's own gate refuses it |
| Floor/index equality test stays green | entry gate | **Standing obligation.** Must not be weakened or skipped to land a CP3 change |
| `HCParser_DoesNotLoadXCore` stays green | Verbatim Constraints | **Standing.** In the regression set for every phase |

**Post-design re-check (after Phase 1)**: unchanged. The design adds no write
path, no second runner, and no contract-breaking change. The one place CP3
deliberately overstates is D-1's tool annotation, and it is recorded in
Complexity Tracking below rather than absorbed silently.

---

## Project Structure

### Documentation (this feature)

```text
specs/parser-check-cp3/
├── plan.md              # This file
├── spec.md              # Scoping spec (already written)
├── research.md          # Phase 0 output -- R-01..R-11
├── data-model.md        # Phase 1 output -- entities and the on-disk artifact
├── quickstart.md        # Phase 1 output -- live validation scenarios
├── contracts/
│   ├── tools.md         # The three tools, five refusal codes, verbatim strings
│   └── artifact.md      # The run-directory contract CP4 and CP5 read
├── checklists/
│   └── requirements.md  # Already written
└── tasks.md             # Phase 2 output (/speckit.tasks -- NOT created here)
```

### Source Code (repository root)

New modules are grouped by the thing they are about, not by layer, matching
the existing `server/parse/` and `server/scan/` packages.

```text
src/flextoolsmcp/server/
├── parse/                          # CP2b's package -- extended, not replaced
│   ├── queue.py                    # unchanged; LOW-priority enqueue already supported
│   ├── priority.py                 # unchanged
│   ├── stages.py                   # unchanged; `filing` stays inbound-edgeless
│   ├── runner.py                   # + batch submission, + engine check once at submission
│   ├── record.py                   # + words.txt, + fingerprint/engine/baseline/counters on meta
│   ├── retention.py                # NEW -- keep-newest-20 by created_at (R-03)
│   ├── scope.py                    # NEW -- scope resolution, genre matching, ordering, limit
│   ├── fingerprint.py              # NEW -- the seven fields; grammar deliberately excluded
│   ├── signature.py                # NEW -- ordered identifier triples + guessed-form marker
│   ├── diff.py                     # NEW -- fixed|broken|changed|unchanged, shared-mode downgrade
│   ├── measure.py                  # NEW -- bounded single-word measurement, own worker
│   ├── project_state.py            # NEW -- the ONE read-only probe, three consumers (FR-004)
│   └── worker_main.py              # + batch parse loop, + structured-result extraction
├── signals/                        # NEW package -- US5, planned as its own phase
│   ├── tiers.py                    # completeness tiers from the public flag + bundle count
│   ├── oracle.py                   # provenance join, the six verbatim sentences
│   ├── batch_signals.py            # the five signals, each with its false-positive line
│   ├── ranking.py                  # promotion-only. SC-014 lives here
│   ├── pairing.py                  # candidate pairing, suggestion-only
│   ├── clustering.py               # root entry, then category pair; representatives capped at 3
│   ├── attribution.py              # side-by-side rule-chain comparison (net-new)
│   └── projections.py              # deletion + duplicate projections; computed, never acted on
├── handlers/
│   └── parse.py                    # + parse_text, parse_log, parse_diff handlers
├── response_models.py              # + five detail models (extra="forbid")
├── models.py                       # + three input models
├── tool_definitions.py             # + three ToolDefs; parse_text annotated destructive (D-1)
└── dispatch.py                     # + three routes

docs/
├── TOOL-CONTRACT.md                # 25 -> 30 code rows
└── CHANGELOG.md                    # one entry under the tool-contract heading

specs/parser-check/
└── SPEC.md                         # section 5.5 file listing CORRECTED (D-6)

tests/
├── test_parse_scope.py             ├── test_parse_signature.py
├── test_parse_fingerprint.py       ├── test_parse_diff.py
├── test_parse_retention.py         ├── test_parse_log_sections.py
├── test_parse_batch_artifact.py    ├── test_parse_measure.py
├── test_parse_counters.py          # FR-017..FR-019 -- R-09's "trap"
├── test_signals_tiers.py           ├── test_signals_oracle_wording.py
├── test_signals_ranking.py         # SC-014 -- written FIRST, red
├── test_signals_batch_signals.py   ├── test_signals_pairing.py
├── test_signals_attribution.py     # FR-049 -- the net-new piece
├── test_signals_clustering.py      ├── test_signals_projections.py
├── test_parse_runner.py            # EXISTS (CP2b) -- extended, not created
├── test_parse_proposal.py          # EXISTS (CP2b) -- extended, not created
├── test_parse_no_project_writes.py # FR-063 standing test
├── test_parse_no_edit_blocking.py  # FR-061 standing regression
└── test_parse_live_cp3.py          # live-marked; the two designated projects
```

Two files in that list already exist in the tree at `b896633` --
`tests/test_parse_runner.py` and `tests/test_parse_proposal.py` are CP2b's.
CP3 **extends** them rather than creating them, and they are listed so the
Test strategy table below does not appear to name a file nothing schedules.

**Structure Decision**: extend `server/parse/` for everything about *running
and recording* a batch, and add a sibling `server/signals/` package for
everything about *interpreting* one. The split is the spec's own: US2's
artifact is a forward commitment that CP4 and CP5 read, while US5's analysis is
CP3-local and is the part explicitly planned as its own phase. Keeping them in
one package would put the checkpoint's largest and most volatile surface inside
the one module that two later checkpoints depend on.

---

## Implementation phases

Ordering is by dependency, and by the spec's own priorities where dependency
leaves a choice. Each phase names its exit condition.

### Phase 1 -- The two live questions and the shared probe (FR-001..FR-004)

Answer FR-001 (never-tokenized vs genuinely empty) and FR-003 (analysis
without a human act) on a live project, and write both answers back to the
parent spec's open-question register. Build `project_state.py` **once**, with
its three consumers named in its docstring -- the never-parsed warning, the
oracle precondition, and CP4's deletion-projection precondition -- so CP4
consumes it rather than growing a second one (FR-004).

Neither question blocks the rest of the checkpoint (R-08): FR-002's
conservative wording and FR-003's explicit permission to build the split let
everything else proceed. What they block is two sentences.

*Exit*: both answers recorded in the parent spec; `project_state.py` has one
implementation and three named consumers.

### Phase 2 -- Scope, fingerprint, and the artifact shape (US1, FR-005..FR-013, FR-015..FR-023)

The forward commitment. Scope resolution over the data model's own
unique-wordform enumeration (never a hand-rolled corpus walk, FR-005),
all-genres matching (FR-006), case-insensitive name-or-abbreviation with an
ambiguity refusal (FR-007), NFC de-duplication with ordering **before**
truncation (FR-009), and the seven-field fingerprint that is deliberately
silent about the grammar (FR-010/FR-011/D-3).

Then the artifact: `words.txt`, the fingerprint/engine/baseline/counter fields
on `meta.json`, retention by `created_at` (R-03), and the divergence statement
for the two counters that do not mean what their host namesakes mean (FR-017,
FR-018, FR-019, R-09).

This phase also pins the empty-collection contract of the genre read CP3
consumes (FR-013) -- it shipped with no tests of its own and CP3 is its first
consumer.

*Exit*: SC-001, SC-002, SC-003 green; the artifact contract is frozen and
`contracts/artifact.md` matches the code.

### Phase 3 -- The batch and reading it back (US2, US3, FR-014, FR-024..FR-029)

`flextools_parse_text` submits at `Priority.LOW`, with the engine capability
check as the **first statement of the handler**, before any parser is
constructed, firing once at submission (FR-024). `flextools_parse_log` serves
the seven named sections, returning a typed not-applicable naming the spine for
every sandbox section (FR-028) -- never an empty one.

D-1's annotation lands here: `parse_text` is annotated at its designed maximum
capability from its first release, the unlock argument is absent from the
schema, and the description's first line states that filing is not yet
reachable (FR-025).

*Exit*: SC-004..SC-007 green, including a live kill-mid-batch leaving every
completed word readable.

### Phase 4 -- The comparison (US4, FR-030..FR-034)

The durable signature as the ordered (morph-form, morph-syntax-analysis,
inflection-type) identifier triples (D-2, FR-031), with rendered forms
alongside, the guessed-form component disclosed as **provisional** rather than
silently dropped (FR-031a), identity change distinguished from behavioural
change (FR-032), the FR-033 fallback wired behind the live verification that
may disprove identifier stability, and the shared-mode downgrade over
`probe_project_access` (FR-034, R-06).

*Exit*: SC-008, SC-009, SC-010 green, including a live break-then-revert cycle.

### Phase 5 -- The batch report and the oracle (US5, FR-035..FR-050)

Its own phase because it is larger than everything else combined. Order within
it is set by risk, not by requirement number:

1. **SC-014's ranking fixture, red.** Before `ranking.py` exists (R-10).
2. Completeness tiers from the public flag plus bundle count (FR-038).
3. The oracle: the six verbatim sentences, the absent case, the
   affirmed/indeterminate split -- never `{affirmed, tacit}` (FR-039..FR-042).
4. The segment-occurrence join, built once and structured for reuse, because
   CP4's deletion projection is the same join for the opposite purpose (FR-043).
5. Promotion-only ranking, against the now-red fixture (FR-045).
6. Candidate pairing, lexicalization finding, clustering per D-5, the
   drill-down cap (FR-044, FR-046, FR-047, FR-048).
7. Side-by-side rule-chain attribution -- the net-new piece. The engine's
   pre-parse morph filter is **not** an attribution mechanism; its only
   legitimate use is narrowing by subtraction (FR-049).
8. Both projections, computed and reported as information, acted on by nothing
   (FR-050).

*Exit*: SC-011..SC-016 green. SC-014 is the phase's gate, not one of its
assertions.

### Phase 6 -- The bounded measurement and routing (US6, FR-051..FR-058)

The measurement as its own run, alone in a worker the supervisor may terminate,
bounded at process level (D-4, R-05), reporting wall-clock and never an
invented step count. Then the proposal rules: fires on four conditions, never
on an inline answer, always costed, always with directly usable arguments,
static scan before trace. FR-058's revisit of every null-tool row for the three
tools CP3 ships.

*Exit*: SC-017, SC-018, SC-019 green.

### Phase 7 -- Cross-cutting, contract, and the corrections (FR-059..FR-063)

Five refusal codes transcribed from `contracts/tools.md` (R-04), 25 -> 30 in
the contract document, one changelog entry. FR-061's standing no-blocking
regression and FR-063's standing no-write test. FR-062's re-probe of the three
deferred lints -- fold in, or record the reason; a third silent move is drift.
D-6's correction to the parent spec's section 5.5 listing.

*Exit*: SC-020, SC-021, SC-022 green; full suite green including CP1's and
CP2's standing groups.

---

## Test strategy

Named here because the `lex-qc` plan gate asks for coverage that is *scheduled*,
not merely asserted.

| Requirement class | Proof | Where |
|---|---|---|
| FR-006 all-genres | two-genre text found by the second genre | `test_parse_scope.py`, SC-001 |
| FR-009 order-then-truncate | same corpus, two orderings, identical list | `test_parse_scope.py`, SC-002 |
| FR-002 never-tokenized | 0 responses asserting "no words" | `test_parse_scope.py`, SC-003 |
| FR-013 genre empty-collection | the read's contract pinned by this feature | `test_parse_scope.py` |
| FR-020 partial stream | kill mid-batch, all completed words readable | `test_parse_batch_artifact.py`, SC-004 (live) |
| FR-027 one grammar load | batch + interleave, load count == 1 | `test_parse_runner.py`, SC-006 |
| FR-028 no empty sections | every sandbox section typed not-applicable | `test_parse_log_sections.py`, SC-007 |
| FR-017 counter names | eight host names byte-exact; `counter_divergences` present **in the artifact** | `test_parse_counters.py` |
| FR-018 approved-missing | computed over fully linked only; an all-analyses impl **fails** | `test_parse_counters.py` |
| FR-019 no-opinion counter | never named/documented as "unreviewed"; split rides beside it | `test_parse_counters.py` |
| FR-030 changed != unchanged | 1 analysis -> 7 classified changed; count-equality impl **fails** | `test_parse_diff.py`, SC-008 |
| FR-032 identity change | identical rendered forms, different ids | `test_parse_signature.py`, SC-010 |
| FR-040 verbatim wording | all six sentences byte-exact; four forbidden words absent | `test_signals_oracle_wording.py`, SC-011 |
| FR-041 oracle absent | never-parsed project -> absent, **offline fixture**, not live-only | `test_signals_oracle_wording.py`, SC-013 |
| FR-042 no tacit labelling | 0 analyses labelled tacit/unreviewed/auto-approved | `test_signals_oracle_wording.py`, SC-012 |
| FR-036 five signals | each prints its false-positive line **in the output** | `test_signals_batch_signals.py` |
| FR-037 distribution | presented as comparison instrument; 0 severity, 0 verdict wording | `test_signals_batch_signals.py` |
| FR-044 candidate pairing | ranked first, confidence basis named, **never filed** | `test_signals_pairing.py` |
| FR-046 lexicalization | mandated wording; not reported as a parse error | `test_signals_pairing.py` |
| FR-049 rule attribution | side-by-side chains; the morph filter is **not** an attribution mechanism | `test_signals_attribution.py` |
| FR-045 promotion-only | correct non-compositional analysis above compositional-but-wrong; **a sort fails** | `test_signals_ranking.py`, SC-014 |
| FR-050 deletion projection | 1 of 2 candidates; a bare no-opinion projection returns 2 and fails | `test_signals_projections.py`, SC-015 |
| FR-050 duplicate projection | filings that would duplicate an existing meaning-only record | `test_signals_projections.py` |
| FR-033 signature fallback | fallback exercised by **fixture**, whatever live verification finds | `test_parse_signature.py` |
| FR-054 bound is a result | terminated measurement reports a measurement, not an error | `test_parse_measure.py`, SC-017 |
| FR-057 proposals | 0 nonexistent tools, 0 missing cost estimates | `test_parse_proposal.py`, SC-019 |
| FR-061 no blocking | concurrent lexicon edit during a run -- **standing** | `test_parse_no_edit_blocking.py`, SC-020 |
| FR-063 no writes | no CP3 path writes to a project -- **standing** | `test_parse_no_project_writes.py`, SC-021 |
| FR-022 retention | newest 20 by `created_at`; a name-sorted impl **fails** | `test_parse_retention.py` |

Five of these are written so the *wrong* implementation fails rather than
merely disagreeing: SC-008 against count-equality, SC-014 against any sort,
SC-015 against a bare no-opinion projection, FR-018 against computing over all
human analyses, and retention against name sorting. That is the property that
makes them worth the lines.

**Pattern-audit obligations.** Two shaped classes are known before
implementation starts and each gets a sweep, not a point fix:

- *Name-sorted directory retention* (R-03). `backup.py:50` is sound only
  because backup directories are timestamp-named. The sweep asks where else the
  tree sorts opaque directory names as if they were chronological.
- *First-element-only reads of a multi-valued LCM collection* (FR-006). The
  sweep asks where else the tree takes `[0]` from a collection the data model
  allows to hold several.
- *Multistring / `ITsString` field access* (FR-008, FR-010, FR-031). The scope
  layer reads genre names and abbreviations and records a `vernacular_ws`
  against the default analysis writing system, and the signature carries
  `rendered_morphs` and `category_labels` read off multistring-typed fields.
  That is the same shape as the standing `ITsString`-vs-`IMultiString`
  confusion class (issues #36/#39/#40), and it gets its own sweep rather than
  riding on the fact that `grammar_health` already resolves multistrings at a
  named writing system (`b896633`).

One further shape is **noted rather than swept**, deliberately: FR-043's
segment-occurrence join walks from an analysis to the segments referencing it,
which is structurally the unguarded-`.Owner`-on-base-`ICmObject` class
(#32/#97/#98). It gets a one-line check when the join is actually written, not
a plan-stage sweep -- the traversal does not exist yet, so a sweep now would
have nothing of CP3's to find.

**Live runs carry pre/post evidence, even though they are reads.** The
live-LCM evidence gate formally applies to write paths, and CP3 has none -- but
several of the facts this plan rests on are live-only: identifier stability
(FR-033), the shared-mode probe (FR-034), and both Phase 1 questions (FR-001,
FR-003). Those runs are captured with the same evidence discipline a write
would get, because "unknowns: none blocking" above is true only if those
answers are recorded rather than observed once and remembered.

**Live verification.** SC-022 requires both designated projects:
`IndonesianHC-Complete` (correctness) and `Malay Parsing-20230810withHC`
(scale). `Sena 3` is excluded by name -- it reports engine `XAmple` and this
feature's own gate refuses it. The live scenarios are in
[`quickstart.md`](./quickstart.md).

---

## Complexity Tracking

| Violation | Why needed | Simpler alternative rejected because |
|---|---|---|
| `flextools_parse_text` annotated destructive while shipping no write path (D-1, FR-025) | A capability annotation is cached by hosts and read by calling models, so flipping it at CP4 is a caller-visible contract event for a tool that did not change its name | Annotating read-only-safe now and flipping at CP4 **is** that event. Accepting a filing argument that always refuses advertises an argument that never works. Adding a parameter at CP4 is additive; changing an annotation is not. **Maintainer may overturn -- costs nothing before implementation** |
| A second `ParseWorkerPool` key for the bounded measurement (FR-051, R-05) | The pool is keyed by project name, so a measurement on a project with a running batch lands in the batch's worker -- and the bound is enforced by killing the process tree | Sharing the worker means the bound takes the batch with it. Cooperative cancellation cannot bound a single-word parse even in principle: its next word boundary is after the parse being bounded |
| A new `server/signals/` package rather than extending `server/parse/` | US5 is the largest and most volatile surface in the checkpoint; `server/parse/` is the artifact two later checkpoints read | One package puts CP3's most-likely-to-change code inside CP4's and CP5's dependency |
| `FR-031a` provisional marker instead of a clean boolean identity | The host predicate's fourth component -- a writing-system-alternative match on a guessed surface form -- has no serialized equivalent | Dropping it silently claims alignment with a predicate the signature does not reproduce. That is the failure the requirement exists to prevent |

---

## Risks

Carried from the spec, with the plan's handling attached.

| Risk | Handling |
|---|---|
| **Promotion-only ranking** -- the natural implementation is shorter and confidently wrong about exactly the words a linguist cares most about | SC-014's fixture written **red before the function exists** (R-10). Phase 5's gate |
| **US5 is the scope risk** -- eight pieces under one story, one net-new | Its own phase, risk-ordered within it, with the net-new attribution piece scheduled last so it is not on the critical path of the other seven |
| **The artifact is a forward commitment** -- CP4 and CP5 both read it | Phase 2 freezes it before Phase 4 or 5 consumes it; `contracts/artifact.md` is the frozen thing |
| **Oracle wording is a user-trust risk** -- telling a linguist nobody reviewed an analysis they did review | Byte-exact assertions on all six sentences plus a forbidden-word scan (SC-011, SC-012) |
| **Identifier stability is assumed, not proven** | FR-033's fallback is wired behind live verification, and the resulting ambiguity is stated in the report. The fallback is materially weaker and the report says so |
| **The three read gaps shipped untested** -- CP3 is their first consumer | FR-013 makes the genre read explicit; the tests are written as if they belonged to the library |
| **Two known limitations carried, not solved** | Genre matching against the default analysis WS is **disclosed** (FR-008), not fixed. The three lints get a fold-in or a written reason (FR-062) -- a third silent move is drift |
| **The source document predates CP2b** | Three of its claims were false by the time CP2b landed. Every remaining source-document claim about on-disk shape is re-verified against `record.py` (R-02) |
| **The parent spec's 5.5 listing is wrong** | Corrected as part of CP3 (D-6), not left as a silent divergence |

---

## Open maintainer decision

### Status as of 2026-09-22 (recorded at T006, blocks T050)

**NOT OVERTURNED. The planned annotation stands, and T050 proceeds on it.**

| | |
|---|---|
| Decision | D-1 -- annotate `flextools_parse_text` `readOnlyHint=False, destructiveHint=True` from its first release, at its designed maximum capability, although CP3 ships no write path |
| Status | Open, unexercised. No maintainer has overturned it |
| Effect on the build | T050 is unblocked and implements the annotation as planned |
| Still overturnable | Yes -- until CP3 ships. After that, changing it is the caller-visible contract event D-1 exists to avoid |

Recording "not overturned" is a deliberate act, not a default that passed by:
the whole reason D-1 is surfaced as a maintainer decision is that the
annotation deliberately overstates the tool's CP3 capability, and a decision to
overstate should be taken knowingly rather than inherited from a plan. If the
maintainer wants the tool annotated to its actual CP3 capability instead,
say so before CP3 ships and T050 is a one-line change; afterwards it is not.

**D-1's annotation call**, unchanged from the spec. It is adopted so planning
is not blocked. Overturning it before implementation costs nothing; overturning
it after CP3 ships costs the caller-visible contract event D-1 exists to avoid.
It blocks the first implementation task of Phase 3, not this plan.
