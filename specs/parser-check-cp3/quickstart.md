# Quickstart: validating parser-check CP3

**Date**: 2026-09-22 · **Spec**: [`spec.md`](./spec.md) · **Plan**: [`plan.md`](./plan.md)

Phase 1 output. Runnable validation scenarios that prove CP3 works end to end.
Each maps to the success criteria it discharges. This is a **validation guide**,
not an implementation guide -- shapes are in
[`data-model.md`](./data-model.md) and strings in
[`contracts/tools.md`](./contracts/tools.md).

---

## Prerequisites

| | |
|---|---|
| OS | Windows with FieldWorks installed (live scenarios); any platform for the offline suite |
| Python | 3.11+ |
| Library floor | `pyflexicon >= 4.9.0, < 5` -- the parser surface plus the three read gaps |
| Correctness project | `IndonesianHC-Complete` |
| Scale project | `Malay Parsing-20230810withHC` |
| **Excluded** | **`Sena 3`** -- reports engine `XAmple`; this feature's own engine gate refuses it. Do not substitute it |

```bash
pip install -r requirements.txt
python -m flextoolsmcp.refresh          # warm the index to the installed floor
```

**Before anything else, confirm the entry gate is still closed.** The
floor/index equality test must be green: an index predating the parser surface
would leave every generated CP3 script written against an API the index cannot
describe. It must not be weakened or skipped to land a CP3 change.

```bash
pytest tests/ -k "floor or index_equality" -q
pytest tests/test_parser_no_xcore.py -q   # HCParser_DoesNotLoadXCore
```

---

## Offline suite

Everything except the live scenarios runs headless.

```bash
pytest tests/ -q                                  # full suite; CP1 + CP2 groups included
pytest tests/ -k "scope or fingerprint or signature or diff or retention" -q
pytest tests/ -k "signals" -q
pytest tests/test_parse_no_project_writes.py tests/test_parse_no_edit_blocking.py -q
```

**Expected**: green, including CP1's and CP2's standing groups (SC-022's
offline half).

---

## Scenario 1 -- Which words am I actually asking about? (US1)

*Discharges SC-001, SC-002, SC-003. No parse is started.*

On `IndonesianHC-Complete`:

1. Resolve a scope by **genre**, by **text**, and across **all texts**.
2. Resolve by the **second** of two genres on a text tagged with both.
3. Resolve a genre string that matches **two** genres.
4. Re-resolve the same scope with a **word limit**.
5. Resolve a scope containing a text that has **never been opened for
   interlinear work**.

**Expected**

- (2) the text is **included** -- the first-genre-only failure mode occurs 0
  times (SC-001).
- (3) refused with `parse_scope_ambiguous`, **both candidates named**.
- (4) ordering by descending occurrence then alphabetically happens **first**,
  the limit truncates **afterwards**, and the response records that truncation
  occurred. Repeating the whole scenario yields an **identical list and an
  identical fingerprint** (SC-002).
- (5) the response does **not** assert the text has no words, and does not
  reuse the empty-scope refusal (SC-003).
- A genre that matches nothing records that matching ran against the **default
  analysis writing system**, rather than asserting no such genre exists.

---

## Scenario 2 -- Parse my corpus, and don't lose the work (US2)

*Discharges SC-004, SC-005, SC-006.*

On `Malay Parsing-20230810withHC` (the scale project):

1. Submit a batch over a genre-scoped list of a few thousand words.
2. While it runs, poll status; then issue an **urgent single-word** request.
3. Let it finish. Inspect the run directory.
4. Submit a second batch and **kill the worker process** at roughly word 4000.
5. Inspect that run directory.
6. Submit a third batch and **cancel** it.

**Expected**

- (2) the single-word request is answered **without waiting for the batch**;
  the batch then resumes at its next word with its position and its loaded
  grammar intact, and **0 grammar reloads** (SC-005). Across the batch plus the
  interleave the grammar is loaded **exactly once** (SC-006). Progress reporting
  accounts for the interleave rather than appearing to stall.
- (3) the directory holds `meta.json`, `results.jsonl` and `words.txt`. No
  sandbox-spine file exists, **and none was created empty**.
- (5) **100% of completed words are readable**, and the run reports a terminal
  failure naming `out_of_memory`, `crashed` or `cancelled` (SC-004). A partial
  trailing line in `results.jsonl` is tolerated, not fatal.
- (6) it stops at the **next word boundary** and partial results are retained
  under a cancelled state.
- If the active engine changes mid-job, that is a **warning on the summary**,
  not a refusal, and results stay labelled with the engine recorded at
  submission.

---

## Scenario 3 -- Show me what happened (US3)

*Discharges SC-007.*

Against the completed run from Scenario 2, request **every** section:

```
summary | config_generation | hc_stdout | hc_output | trace | words | results
```

**Expected**

- `summary`, `words`, `results` return real content, **paged**.
- `config_generation`, `hc_stdout`, `hc_output` return a **typed
  not-applicable** response naming the spine and the checkpoint that will fill
  it. **0 sections return empty content** (SC-007).
- A trace that cannot be parsed returns the **raw slice, labelled raw**, with
  no invented explanation.

---

## Scenario 4 -- Did my grammar edit help? (US4)

*Discharges SC-008, SC-009, SC-010.*

On `IndonesianHC-Complete`:

1. Baseline parse over a small genre scope.
2. **Deliberately break** one grammar rule in FieldWorks.
3. Parse again. Diff.
4. **Revert.** Parse again. Diff.
5. Diff two runs over **different scopes**, then force it.
6. Delete and recreate a morph between two runs. Diff.

**Expected**

- (3) the deliberately broken word is in the **`broken`** bucket, with **0 false
  members** (SC-009).
- (4) after revert it is in **`fixed`**, again with 0 false members.
- A word going from one analysis to seven is classified **`changed`**, not
  unchanged (SC-008). *A count-equality implementation fails here.*
- (5) refused naming **which fields differ**; forced, it runs on the
  **intersection only** and says so.
- (6) reported as an **identity change** -- identical rendered forms, differing
  identifiers -- 100% of the time, and as behavioural change **0 times**
  (SC-010).
- With the project open in **shared mode** elsewhere, a no-change result is
  downgraded to `no_change_unverifiable` and carries
  `staleness: "shared_mode_unverifiable"`. **No safe read-back interval is
  promised.**
- Any analysis with a **guessed morph form** reports **provisional** rather
  than asserting behavioural identity.

---

## Scenario 5 -- Which analyses are wrong, and why? (US5)

*Discharges SC-011 through SC-016. Fixture-driven; the live half is the oracle.*

Offline, against fixtures covering every completeness tier and every stated
false-positive case:

```bash
pytest tests/ -k "signals" -q
```

**Expected**

- All **six mandated sentences rendered verbatim** -- byte-exact, not
  paraphrased (SC-011).
- The words `invalid`, `incorrect`, `rejected`, `flagged` appear **0 times** in
  connection with an analysis carrying no stored opinion (SC-011).
- **0 individual analyses** labelled `tacit`, `unreviewed` or `auto_approved`
  anywhere (SC-012). The split is `{affirmed, indeterminate}`.
- A meaning-only human record is **named as such**, counted as neither agreement
  nor disagreement, and **not dropped**.
- A sketched-but-unlinked record is named with **how many of its morphs are
  unlinked**.
- In the **non-compositional ranking fixture**, the correct analysis is ranked
  **above** the compositional-but-wrong competitor (SC-014). *A
  sort-by-gloss-distance implementation fails this. It is the single most
  important regression test in CP3.*
- The **deletion projection** over a fixture with one segment-referenced and one
  unreferenced candidate returns **exactly one** (SC-015). *A bare no-opinion
  projection returns two and fails.*
- Four hundred suspect words produce a **clustered** recommendation of one to
  three representatives per cluster, not four hundred traces.
- Drill-down traces at most the **user-chosen cap (10-20)**; bulk auto-tracing
  occurs **0 times** (SC-016).

The absent-oracle case has an **offline fixture** as well as a live check, so
SC-013 has a standing regression rather than depending on a live run happening
to hit that state. Live, on a project **the parser has never run against**:

- The oracle is reported **absent**, with its own sentence. A degenerate
  all-unreviewed report is emitted **0 times** (SC-013).

---

## Scenario 6 -- Is my grammar broken? (US6)

*Discharges SC-017, SC-018, SC-019.*

1. Run the bounded single-word measurement against a **known-slow** grammar.
2. Run it against a **known-fast** one.
3. Trigger a terminal failure and read the proposals.

**Expected**

- (1) terminates at its bound and reports a **terminal result carrying a
  wall-clock measurement** -- not an error (SC-017). **0 invented engine step or
  node counts.** A grammar-scan proposal is attached.
- (2) answered inside the fast-path window: **0 grammar-scan proposals**
  (SC-018). One that misses the window carries **exactly one**.
- (3) the proposal names the bounded measurement or the static scan, with a
  **mandatory cost estimate** and **directly usable arguments**. Where both a
  trace and the static scan are candidates, the **static scan is proposed
  first**.
- Across every response the feature can emit: proposals name a nonexistent tool
  **0 times** and omit a cost estimate **0 times** (SC-019).
- No proposal ever names a **filing step** -- at CP3 that is every session.
- The measurement ran in its **own worker**, not one shared with a batch.

---

## Scenario 7 -- The standing guarantees

*Discharges SC-020, SC-021.*

```bash
pytest tests/test_parse_no_edit_blocking.py -q     # FR-061, SC-020
pytest tests/test_parse_no_project_writes.py -q    # FR-063, SC-021
```

**Expected**

- A running parse job blocks a concurrent lexicon edit or human-analysis write
  **0 times** (SC-020). No project-wide claim is introduced. This is a
  **standing** regression, not a one-off check.
- **No code path shipped by CP3 writes to a FieldWorks project** -- 0
  occurrences, asserted by a **standing test**, not by inspection (SC-021).

Also confirm, by inspection of the tool schema:

- `flextools_parse_text` is annotated at its **designed maximum capability**,
  its description's first line states that **filing is not yet reachable**, and
  the filing argument is **absent from the schema**.

---

## Exit criteria (SC-022)

- Live verification passes on **both** designated projects.
- The **full suite is green**, including CP1's and CP2's standing groups.
- `HCParser_DoesNotLoadXCore` is green.
- The floor/index equality test is green and was not weakened.
- The parent spec's section 5.5 file listing has been **corrected** (D-6), and
  FR-001's and FR-003's answers are recorded in its open-question register.
- FR-062's three deferred lints are either folded in or their continued
  deferral is **recorded with a reason**. A third silent move is drift.

---

## Run log

Recorded as each gate is actually run, newest last. T001 requires the entry
gate be recorded green here before any CP3 change lands; T002 requires a
full-suite baseline so later red is attributable to CP3 rather than inherited.

### 2026-09-22 -- T001 entry gate: GREEN

| Gate | Command | Result |
|---|---|---|
| Floor / index equality | `pytest tests/ -k "floor or index_equality" -q` | **10 passed**, 2118 deselected |
| `HCParser_DoesNotLoadXCore` | `pytest tests/test_parser_no_xcore.py -q` | **4 passed** |

Neither was weakened or skipped.

**Environment note.** The gate was first red for an environment reason, not a
code one: the shared venv carried `pyflexicon==4.8.0` while the repository's
committed floor (pre-existing on `main`, not a CP3 change) is
`pyflexicon>=4.9.0,<5`. `server/versioning.py` resolved `4.8.0` against bundled
index artifacts at `4.9.0`, so both floor assertions failed. Resolved by
bringing the venv up to the declared floor
(`uv pip install "pyflexicon>=4.9.0,<5"`), after which both gates are green.
The floor itself was not touched.

### 2026-09-22 -- T002 full-suite baseline

```
pytest tests/ -q
1 failed, 2118 passed, 9 skipped, 23 warnings, 36 subtests passed in 213.16s
```

**Inherited failure (pre-CP3, not attributable to this checkpoint):**

- `tests/test_parse_live.py::test_scenario_2_an_xample_project_is_refused_naming_both_engines`
  -- the local `Sena 3` project file will not open:
  `LcmInitializationException: File is not a valid FieldWorks project file`.
  The test needs a loadable `Sena 3` to observe it reporting engine `XAmple`.
  This is the same project CP3 excludes by name from its own live scenarios
  (see Prerequisites), so it gates no CP3 task; it must simply still be the
  *only* failure when the suite is re-run at T126.

**Baseline for T126**: any failure beyond this one is CP3's.

### 2026-09-22 -- T122-T125 live verification (read-only)

`pytest tests/test_parse_live_cp3.py -q` -- **8 passed**. Evidence under
`specs/parser-check-cp3/evidence/` (`t122-*`, `t123-*`, `t124-scale`,
`t125-identifier-stability`).

| Scenario | Project | Result |
|---|---|---|
| 1 -- scope resolution | IndonesianHC-Complete | Order-then-truncate deterministic across two resolutions (SC-002); a missing genre refuses `parse_scope_empty` naming the analysis WS. |
| 2 -- batch + urgent word | IndonesianHC-Complete | 38-word batch completed; an urgent word sent mid-batch answered inline in 0.1 s; **1** grammar load across both (SC-005, SC-006); directory holds only `meta.json`, `results.jsonl`, `words.txt`. |
| 3 -- every section | IndonesianHC-Complete | All seven sections `ok` and non-empty; the three sandbox sections typed not-applicable naming CP5 (SC-007). |
| kill mid-batch | IndonesianHC-Complete | Worker tree killed at word 6: run `failed`, **6/6** completed words readable (SC-004). |
| cancel | IndonesianHC-Complete | Stops at a word boundary; partials retained; status points at `flextools_parse_log`. |
| scope mismatch | IndonesianHC-Complete | Refused naming `limit`, `truncated`; forced compares the intersection. |
| identifier stability (T125) | IndonesianHC-Complete | **Stable**: 38/38 identical GUID-triple signatures across a close/reopen; identifier mode now authoritative. |
| 6 -- measurement | IndonesianHC-Complete | Generous and 1-second bounds both completed (0.55 s including a cold grammar load). |
| scale (T124) | Malay Parsing-20230810withHC | Whole-lexicon batch (262 words), urgent word inline in 0.05 s, 1 grammar load, killed at 175 with 175/175 readable. |

**Not verifiable here, and why**

- **Genre scenarios (SC-001 second genre, ambiguity refusal)**: neither
  designated project carries any genre. Proven offline
  (`tests/test_parse_scope.py`); adding a genre would be a project write.
- **Scale as specified ("a few thousand words", kill at ~4000)**: the scale
  project holds 262 lexemes and three short texts. The whole lexicon was the
  largest honest scope.
- **A live `terminated_at_bound`**: no available grammar is slow -- this one
  loads and parses a word in 0.55 s. The terminated path is proven against real
  killed stub workers (`tests/test_parse_measure.py`).
- **Needs a human in FieldWorks** (project edits outside this server, which
  CP3 must not make): SC-009 break-then-revert, SC-010's delete-and-recreate
  morph, and FR-034's shared-mode staleness with the project open in
  FieldWorks.

### 2026-09-22 -- T126 full suite: GREEN against the T002 baseline

```
pytest tests/ -q
1 failed, 2598 passed, 9 skipped, 23 warnings, 36 subtests passed in 361.79s
pytest tests/ -k "floor or index_equality" -q   -> 10 passed (unweakened)
pytest tests/test_parser_no_xcore.py -q          -> 4 passed
```

The one failure is the inherited `Sena 3` one recorded at T002 (the local
project file will not open). No other failure, so nothing here is CP3's.
