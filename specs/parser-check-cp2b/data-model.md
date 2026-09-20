# Phase 1 data model -- CP2a-bridge + CP2b

Entities this slice introduces in **this** repository. Entities CP2a introduced in
`flexicon` (`ParserAvailability`, the facade itself) are in
[`../parser-check-cp2/data-model.md`](../parser-check-cp2/data-model.md) and are
consumed here, not redefined.

Field names drawn from the parent spec's Verbatim Constraints are reproduced
exactly, including order where the spec pins order.

---

## 1. `Run`

The unit of parser work. One per `flextools_try_word` call, whatever the level.

| Field | Type | Notes |
|---|---|---|
| `run_id` | str | The handle. Opaque to callers; the only key `flextools_parse_status` accepts. |
| `stage` | `RunStage` | Section 2. |
| `priority` | `Priority` | Section 3. |
| `project_name` | str | Which worker owns it (R-02). |
| `words_total` | int | Known at enqueue; 1 for a single word. |
| `words_completed` | int | Monotonic. Also `parse_job_cancelled`'s detail field. |
| `created_at` / `started_at` / `ended_at` | ISO-8601 UTC, nullable | |
| `record_path` | Path | Section 5. |
| `failure` | `RunFailure` or null | Section 6. Set only on `failed`. |
| `cancel_requested` | bool | Set by the server; **observed by the worker at the next word boundary** (FR-032). Never a terminal state by itself. |

**Progress and the interleave (FR-031).** `words_completed / words_total` is the
reported progress. When an urgent word interleaves, the batch's own counters do not
move and the batch does not restart -- so a caller polling during the interleave
must not see a stalled run. The status report therefore carries an explicit
`interleaved_by` field naming the run that is currently occupying the worker, which
is what turns "apparently stalled" into "accounted for". Without it, SC-009's
"reported batch progress accounts for the interleave" has no observable.

---

## 2. `RunStage`

A closed enum. **Exactly these names**, from the Verbatim Constraints:

```
starting | loading_grammar | parsing | filing | completed | failed | cancelled
```

- `filing` is **defined here and unreachable until CP4.** A test asserts no CP2b
  code path can produce it, so its presence in the enum is a contract commitment
  rather than dead ambiguity.
- Terminal stages: `completed`, `failed`, `cancelled`.
- `loading_grammar` is distinct from `parsing` for two stated reasons: it is the step
  that most often exhausts memory, so attributing a death to it is diagnostic; and on
  a large project it dominates the run before a single word is parsed, so a caller
  shown only "running" concludes the tool is hung.

**Transitions.**

```
starting -> loading_grammar -> parsing -> completed
                 |                |
                 +-> failed       +-> failed
                 |                +-> cancelled
                 +-> cancelled
```

`starting -> cancelled` is reachable (cancel before the worker picks it up).
Nothing leaves a terminal stage. A cancel or a second cancel against a terminal run
is `parse_job_cancelled`, **not** a stage change (FR-036).

---

## 3. `Priority`

Mirrors the host application's names and values. **Lower value wins**; FIFO within a
level; enqueued per wordform.

```
ReloadGrammarAndLexicon = 0
TryAWord                = 1
High                    = 2
Medium                  = 3
Low                     = 4
```

**The ordering guarantee is this feature's own.** The local FieldWorks tree carries
an uncommitted change draining the queue into a parallel batch and losing priority
ordering within it. We do not use `ParserScheduler`, it does not bind us, and its
behaviour must never be cited as our rationale or copied.

A single-word `flextools_try_word` enqueues at `TryAWord`. CP3's batch will enqueue
at `Medium`/`Low`; the queue is built to accept that now so CP3 adds no second
execution model (FR-026).

---

## 4. `MorphSpec` and `Resolution`

The caller's proposed decomposition and what it resolved to.

### `MorphSpec` -- one piece, as a caller can actually write it

| Field | Type | Notes |
|---|---|---|
| `headword` | str or null | |
| `sense` | str or int or null | Disambiguates homographs. |
| `msa_hvo` | int or null | The identifier form, for a caller that already has one. |
| `position` | int | 0-based index in the decomposition. Echoed in the refusal. |

Exactly one of `headword` / `msa_hvo` is required. There is **no** free-text form:
a bare surface string is a search, and this feature ships no segmenter.

### `Resolution` -- what a `MorphSpec` resolved to

| Field | Type | Notes |
|---|---|---|
| `spec` | `MorphSpec` | |
| `msa_hvos` | list[int] | The analyses the parser requires. |
| `candidates` | list[`Candidate`] | Everything considered, including rejected. Echoed in the refusal so the caller can correct themselves. |
| `outcome` | `ok` \| `none` \| `ambiguous` \| `no_msa` | The three failures are exactly `parse_morph_unresolved.resolved_to`'s enum. |

**The three failures are kept distinct on purpose.** Collapsing "no such headword",
"several homographs" and "matched, but carries no usable analysis" into a bare
refusal reproduces the silent-narrowing failure the requirement exists to prevent --
the caller cannot tell whether to fix their spelling, pick a homograph, or conclude
the entry has no analysis at all.

### `Candidate`

| Field | Type |
|---|---|
| `headword` | str |
| `sense` | str or null |
| `msa_hvo` | int or null (**null is `no_msa`**) |
| `entry_hvo` | int |

---

## 5. `RunRecord`

The durable artifact results accumulate in **as they are produced** (FR-029), so a
run that dies or is cancelled leaves everything finished readable (SC-008).

Shape follows `server/skeleton_storage.py` (R-07): append-only JSONL, one object per
line, under a `threading.Lock`, with an environment override for the directory.

```
<record dir>/<run_id>/
    meta.json        # the Run, rewritten on stage change
    results.jsonl    # one line per completed word, appended and flushed
    traces/<n>.xml   # trace payloads, out of line -- see below
```

| Constraint | Why |
|---|---|
| appended **and flushed** per word | a buffered write loses the tail of a killed run, which is precisely SC-008's case |
| trace payloads written to their own file, never inlined into a response | the parent spec calls their size "a design decision rather than a detail"; a large trace in a response is unreadable and may not fit |
| a **size cap** from day one | `skeleton_storage`'s own docstring records unbounded growth as known debt with a *small* payload; a record of traces cannot inherit that omission (R-07) |
| `run_id` is not a path component the caller controls | an opaque server-issued id, never a caller string, so no traversal is reachable |

`meta.json` is rewritten rather than appended because it is the current state;
`results.jsonl` is appended because it is history. Mixing the two into one appended
file would make "what stage is it in now" an O(file) read on every status poll.

---

## 6. `RunFailure`

| Field | Type |
|---|---|
| `stage_at_failure` | `RunStage` |
| `message` | str |
| `next_step` | list of `next_step` rungs |

FR-034: a failed run carries guidance pointing at the diagnostic instruments,
because memory exhaustion -- the characteristic `loading_grammar` death -- is the
case where a diagnosis beats a retry. Every rung must name an action the caller can
actually perform (SC-011); at CP2b the diagnostic instruments that exist are
`flextools_health` and `flextools_grammar_health`.

---

## 7. Refusal detail payloads

Three additive codes. Contract count **22 -> 25**, `tool-responses/1.0` unchanged
(additive). Models go in `server/response_models.py` with
`ConfigDict(extra="forbid", populate_by_name=True)` and a `Literal` discriminator,
matching every model from `:142` onward and the four CP1 parser models at `:361-416`.

### `parse_morph_unresolved`

Five fields, **in this order** -- the order is pinned by the parent spec and was the
subject of a three-way agreement check across `SPEC.md`, `CP2-SPEC.md` and `spec.md`
during CP2's cycle 3. Do not reorder, rename, recase or pluralize.

| Field | Type |
|---|---|
| `morph` | str |
| `position` | int |
| `resolved_to` | `none` \| `ambiguous` \| `no_msa` |
| `candidates` | list[`Candidate`] |
| `hint` | str |

**No parse runs when this fires** (FR-019, SC-005). The refusal is raised by the
resolver before the worker is asked for anything, and a test asserts the negative.

### `parse_run_not_found`

| Field | Type |
|---|---|
| `run_id` | str |
| `available_runs` | list[str] |

Already specified in SPEC 14; first emitted here. The **only** refusal
`flextools_parse_status` issues (FR-033).

### `parse_job_cancelled`

| Field | Type |
|---|---|
| `run_id` | str |
| `words_completed` | int |
| `state_at_cancel` | `RunStage` |

**Fires only when a call attempts to act on an already-terminal run** -- a second
cancellation, or a single-word request attaching to a run someone else cancelled.
It does **not** fire from `flextools_parse_status` merely reporting a cancelled
state: asking about a dead run is a successful query, not a failed request (FR-033,
FR-036). A test asserts the status tool returns success over a cancelled run.

---

## 8. `WorkerChannel` (internal)

Not caller-visible. Recorded because it is the seam R-02's decision creates and the
place its guarantees are enforced.

| Aspect | Contract |
|---|---|
| transport | line-delimited JSON over the child's stdin/stdout, launched through the existing `subprocess_helpers.run_script_async` family -- **not a second execution mechanism** |
| lifetime | one worker per project; idle timeout releases the project and exits |
| first action per request | `check_active_parser(project, supported_engines=("HC",))` (R-03) |
| held grammar | one slot, currency confirmed before every reuse, released on project switch (FR-042, FR-043) |
| cancellation | the server sets `cancel_requested`; the worker observes it **at a word boundary** and returns `cancelled` over the partial results |
| shutdown | server shutdown kills the tree via the existing `_kill_process_tree` path (issue #57) -- a long-lived pythonnet holder of a `.fwdata` lock is a known failure mode here, not a hypothetical |
