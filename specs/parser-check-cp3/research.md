# Research: parser-check CP3 -- the corpus, the artifact, and the diagnosis

**Date**: 2026-09-22
**Spec**: [`spec.md`](./spec.md)
**Plan**: [`plan.md`](./plan.md)

Phase 0 output. Every `NEEDS CLARIFICATION` raised by the plan's Technical
Context is resolved here, or is explicitly carried as a live question that
the spec itself schedules as work (FR-001, FR-003).

The spec's closing risk is the instruction that governs this whole document:
*"the source document was written against the parent spec rather than against
shipped code."* Every finding below was taken from the tree at `b896633`, not
from the source document.

---

## R-01 -- The batch needs no new execution model; CP2b built the seam for it

**Decision**: a batch is `ParseQueue.enqueue_run(run_id, wordforms,
Priority.LOW)`. No new runner, no new worker, no new queue.

**Rationale**: `src/flextoolsmcp/server/parse/queue.py:132` already takes a run
id, an iterable of wordforms and a priority, and enqueues them **one item per
word** -- its docstring names that as deliberate, "removing the word
boundaries FR-031 interleaves at" being the thing it refuses to do.
`priority.py:44` already defines `MEDIUM` and `LOW` below `TRY_A_WORD`, and
CP2b's own scope fence records that the queue "is built to accept
`Medium`/`Low` enqueues now so that stays true."

So FR-014's "no second execution model may be introduced" is not a constraint
the plan must work around; it is a description of the cheapest available
implementation. FR-026 (progress accounting for interleave) and FR-027 (one
loaded grammar) likewise already have their mechanisms:
`RunMeta.interleaved_by` at `record.py:169` exists precisely so a poll
mid-interleave sees why progress paused, and the warm `starting -> parsing`
edge at `stages.py:98` exists so a second run against a held grammar does not
re-announce a load.

**Alternatives considered**: a batch-specific worker pool (rejected: FR-014
forbids it, and `ParseWorkerPool` is already keyed per project); one composite
queue item per batch (rejected: destroys the interleave boundary, and
`enqueue_run` documents that rejection).

**Consequence for the plan**: the batch handler is mostly scope resolution and
artifact writing. The runner work is per-wordform enqueue plus a `LOW`-priority
call site -- which is why the spec's assumption "CP2's runner is sufficient as
shipped" survives, and why any structural runner change found during
implementation is an escalation (spec, Assumptions), not an absorbable task.

---

## R-02 -- The artifact layout already exists; only `words.txt` is new

**Decision**: adopt `record.py` as shipped. Add exactly one file.

**Rationale**: `record.py:34-42` writes `<record dir>/<run_id>/meta.json`,
`results.jsonl`, `traces/<n>.xml`. `new_run_id()` is `secrets.token_hex(16)`
validated by `\A[0-9a-f]{32}\Z` (`record.py:95`, `:123`). `append_result()`
writes, flushes **and `os.fsync`s** per line (`record.py:296`) -- FR-020's
"valid up to its last complete record" is already stronger than the
requirement, and `iter_results()` already skips a malformed trailing line
rather than raising.

This confirms all three of D-6's factual corrections against the tree:
`results.jsonl` is not net-new, run ids carry no timestamp, and the parent
spec's section 5.5 listing describes a layout no code has written.

**What is genuinely missing**, and therefore is the plan's artifact work:

| Gap | Where | Requirement |
|---|---|---|
| `words.txt` | no persistence for a word list exists | FR-015 |
| Scope fingerprint, engine, load-error baseline on the record | `RunMeta` has none of these fields | FR-010, FR-016, FR-023 |
| The eight host counters | `RunMeta` has `words_total`/`words_completed` only | FR-017, FR-018, FR-019 |
| Retention | nothing prunes run directories at all | FR-022 |

**Alternatives considered**: renaming shipped files to the parent spec's
listing (rejected by D-6 -- churn on an artifact CP4 and CP5 both read).

---

## R-03 -- `list_run_ids()` sorts by mtime, and FR-022 says creation time

**Decision**: retention prunes on `RunMeta.created_at`, read from each
`meta.json`. `list_run_ids()` keeps its mtime ordering for its own caller and
is **not** reused as the retention order.

**Rationale**: `record.py:160` sorts run directories by `st_mtime`, reverse.
That is correct for its stated purpose -- backing `parse_run_not_found`'s
"here are the handles that do exist" -- but it is not creation order, and
FR-022 says "ordered by **recorded creation time**, never by a lexicographic
sort of run-identifier directory names." `RunMeta.created_at` is already
populated at `create()` (`record.py:171`), so the correct key is on disk
already.

The distinction is not pedantry: a run that fails at word four thousand and is
then *read back* has its directory mtime bumped by nothing, but a run whose
`traces/` gained a drill-down file later does. mtime therefore reorders on
read-adjacent activity; `created_at` does not.

**Confirming the pruner finding**: `backup.py:50-59` sorts entries by name and
its own comment says the lexicographic sort is chronological *because backup
directories are timestamp-named*. Run directories are `token_hex(16)`. FR-022's
"adopt the policy, reject the mechanism" is therefore exactly right, and the
mechanism must not be copied even though the shape of the function invites it.

**Alternatives considered**: renaming run directories to timestamps so the
existing sort transfers (rejected: FR-022 forbids re-minting the id form, and
it would break every `\A[0-9a-f]{32}\Z` validation site).

---

## R-04 -- Five new refusal codes follow an established, purely additive pattern

**Decision**: five `*Detail` models in `response_models.py` with
`model_config = ConfigDict(extra="forbid", populate_by_name=True)` and a
`Literal` `error_code`, plus five rows in `docs/TOOL-CONTRACT.md`, plus one
changelog entry. Contract stays `tool-responses/1.0`.

**Rationale**: the file already carries 25 such models; the two parser ones
CP2b added (`ParseRunNotFoundDetail` at `response_models.py:476`,
`ParseJobCancelledDetail` at `:496`) are the template to copy field-for-field.
`docs/TOOL-CONTRACT.md:92-125` is the table, currently 25 rows, and its header
states "Detail models use `extra='forbid'`, so the field lists below are
authoritative."

Adding a code is additive because a client that does not know a code reads the
envelope, not the detail model; no existing code changes shape. That is what
keeps the major version fixed under FR-059.

**The field order is a transcription hazard, not a design question.** The spec
records that CP2's own field-order divergence "cost two crew cycles and
happened during transcription." The five field lists are pinned verbatim in
`contracts/tools.md` and the implementation tasks transcribe from that file,
not from the spec prose and not from the parent spec.

**Alternatives considered**: a single generic `parse_failed` code carrying a
discriminator (rejected: FR-060 requires per-code detail models and per-code
rows, and the five codes carry genuinely different fields).

---

## R-05 -- The bound is process-level because the engine offers no other seam

**Decision**: the bounded measurement runs as its own run, alone in a worker,
terminated via `subprocess_helpers._kill_process_tree`. Reported cost is
wall-clock.

**Rationale**: `worker_client.py:59` already imports `_kill_process_tree`, and
`:208-240` already uses it -- a polite `shutdown`, a timeout, then the tree is
killed regardless. The helper FR-052 names exists and is exercised.

The reason it is the *only* option is structural: the queue's cancellation is
cooperative and observed at a word boundary (`queue.py:162` docstring, "a word
already handed to the worker is not clawed back"). For a one-word measurement
the next word boundary is *after* the parse being bounded, so cooperative
cancellation cannot bound it even in principle. D-4 states this; the code
confirms it.

FR-051's "MUST NOT share a worker with a batch" follows directly:
`ParseWorkerPool` is keyed by project name (`worker_client.py:625`), so a
measurement on the same project as a running batch would land in the same
worker and killing the tree would take the batch with it. The measurement
therefore needs its own pool key, and that is a real (small) change to the
pool, not a call-site choice.

**Alternatives considered**: a step budget or cancellation token on the engine
(does not exist -- the parent spec verified the parse path carries none);
thread-level interruption (CPython cannot interrupt a blocking pythonnet call).

---

## R-06 -- The shared-mode marker has a shipped probe

**Decision**: FR-034 reads `project_access.probe_project_access(project_name)`
and treats verdicts `open_shared` and `open_exclusive` as staleness-carrying.

**Rationale**: `project_access.py:373` returns a `ProjectAccess` whose verdict
vocabulary (`project_access.py:87`) already distinguishes `free`,
`open_shared`, `open_exclusive` and `stale_lock`. The module is pure
server-side -- no pythonnet, no project open -- so a comparison tool can call
it without violating FR-024's "the reading, comparison and log tools MUST NOT
call [the engine check] -- they read prior artifacts and never touch the
engine."

The module's own docstring records a known fail-open gap. FR-034 is worded
compatibly: it requires a marker and a downgrade, and forbids promising a safe
read-back interval. A fail-open probe under-reports sharing, so the downgrade
is best-effort by construction, and the report must not claim otherwise.

**Alternatives considered**: opening the project to ask (rejected: costs a
project open on a pure-artifact read path, and FR-024 forbids the comparison
tool touching the engine).

---

## R-07 -- CP1's grammar scan exists and has never had a caller

**Decision**: US6's proposals name `flextools_grammar_health`, which is a
registered tool (`tool_definitions.py:431`) backed by
`handlers/grammar_health.py` over `scan/grammar_scan_module.py`.

**Rationale**: the scan module ships roughly a dozen `_scan_*` checks. FR-056
gives it its first four trigger conditions and FR-057 requires the proposal to
carry directly usable arguments. Because the tool exists and is registered, no
proposal CP3 emits names a nonexistent tool for this step -- which is half of
SC-019 discharged by construction.

The other half is FR-058: rows left pointing at a null tool at CP2b must be
revisited for the three tools CP3 ships. `runner.py:92` holds
`_FAILURE_NEXT_STEP` as prose naming `flextools_health` and
`flextools_grammar_health`; `handlers/parse.py:1018` holds
`_status_next_step`. Both are the revisit sites.

**FR-062's lint question is re-probed, not inherited.** CP2b's scope fence
records the three deferred lints as "CP3, per D5 -- the engine-version-specific
absence must be **re-probed** there, not inherited from CP2's verdict." That
re-probe is a scheduled task, and its outcome is either a fold-in or a written
reason. A third silent move is the failure FR-062 names.

---

## R-08 -- Two live questions gate wording, not build

**Decision**: FR-001 and FR-003 are scheduled as the first two tasks of the
implementation, run against a live project, and their answers are written back
to the parent spec's open-question register. The structures they gate
(`scope refusal wording`, `indeterminate population description`) are built
behind them; everything else proceeds in parallel.

**Rationale**: neither question can be answered from this tree. FR-001 asks
whether a never-interlinearized text is distinguishable from an empty one
through the data model alone; FR-003 asks whether an analysis can be recorded
against a segment with no human act. Both are questions about LCM behaviour on
a live project, and both have a *safe default* the spec already mandates --
FR-002's conservative wording and FR-003's explicit permission to build the
split while the answer is outstanding.

So they are sequencing constraints on two sentences, not blockers on the
checkpoint. Treating them as blockers would stall CP3 behind live-project
access; treating them as optional would ship the exact wording the spec spends
its longest requirements preventing.

**Alternatives considered**: deferring both to CP4 (rejected: FR-001 gates
scope refusal wording, which ships in CP3's US1).

---

## R-09 -- Where the eight host counters come from, and the one that is a trap

**Decision**: adopt the eight names verbatim into the run record.
`TotalUserApprovedAnalysesMissing` is computed over **fully linked** human
analyses only; `TotalUserNoOpinionAnalyses` is never named or documented as a
count of unreviewed analyses, and ships beside the affirmed/indeterminate
split.

**Rationale**: FR-017 requires verbatim adoption where the counters coincide
with the host application's parser report, and requires every deliberate
divergence to be stated **in the artifact itself**. FR-018 and FR-019 are two
such divergences, and they are the two that a plausible implementation gets
wrong in the same direction -- by computing over all human analyses, and by
treating "no stored opinion" as "unreviewed."

The completeness tier that makes FR-018 computable comes from FR-038: the
public per-bundle completeness flag plus the bundle count, never a
reimplementation of the host's internal fully-formed predicate.

**Consequence**: the divergence statement is a field in `meta.json`, not a
comment in the source. A reader of the artifact who never sees this repository
must still be told which two counters do not mean what their host-application
namesakes mean.

---

## R-10 -- Promotion-only ranking is written test-first

**Decision**: SC-014's fixture is written and red before the ranking function
exists.

**Rationale**: the spec names this "the single most important regression test
in CP3" and its risk register says the failure "must be tested before it is
written, not after." The reason is specific rather than ceremonial: the natural
implementation (sort candidates by gloss distance) is *shorter and more
obvious* than the correct one, so a test written afterwards is written by
someone who has already accepted the wrong shape.

FR-045's rule is mechanical enough to test exactly: agreement promotes;
disagreement changes nothing; everything not promoted keeps its original
order. A sort -- any sort -- fails that last clause, which is what makes the
assertion catch the wrong implementation rather than merely disagreeing with it.

**Alternatives considered**: none. This is the spec's own instruction.

---

## R-11 -- Structured result, never documents

**Decision**: every batch signal, every signature and every diff binds to the
parser surface's typed structured result.

**Rationale**: the spec's entry gate states this as settled fact about shipped
code: the structured result's analyses carry live references to the data-model
objects for morph form, morph-syntax analysis and inflection type, while the
document-returning operations preserve those objects only as integer
identifiers. FR-035 and the entry gate both forbid re-litigating it.

FR-021 then forbids serializing those live references. The two together define
the artifact's central move: **read live objects, write identifiers plus
rendered text.** The identifiers are the durable signature (FR-031); the
rendered text is what lets a report render without reopening the project.

FR-031a is the honest residue: the host predicate's fourth component -- a
writing-system-alternative match on a guessed surface form -- has no
serialized equivalent, so a comparison touching a guessed-form analysis reports
**provisional**, not identical.

---

## Open items carried into implementation

| Item | Kind | Handling |
|---|---|---|
| FR-001 -- never-tokenized vs empty text | live question | Task 1; conservative wording ships regardless (FR-002) |
| FR-003 -- analysis without a human act | live question | Task 2; gates one sentence, not the split |
| Identifier stability across sessions | unverified assumption | live verification; FR-033 fallback if disproved |
| D-1 -- destructive annotation | maintainer decision | adopted; overturning before implementation costs nothing |
| `pyflexicon` 4.9.0 tag | maintainer act | non-blocking; floor and bundled index already agree |
