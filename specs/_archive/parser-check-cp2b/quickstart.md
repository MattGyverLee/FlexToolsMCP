# Quickstart -- validating CP2a-bridge + CP2b

Runnable scenarios that prove this slice works end to end. Contracts are in
[`contracts/`](./contracts/); entity shapes are in [`data-model.md`](./data-model.md).
Neither is duplicated here.

**Everything below is read-only except scenario 7**, which is the one live write in
this checkpoint and requires human authorisation.

---

## Prerequisites

| | |
|---|---|
| Platform | Windows with FieldWorks 9 installed (`ParserCore.dll` 9.3.10, `C:\Program Files\SIL\FieldWorks 9`) |
| Library | `pyflexicon` 4.9.0 -- published; resolves to the working tree in this environment |
| Projects | `IndonesianHC-Complete` (engine `HC`, 3 rules, 41 entries) -- correctness |
| | `Malay Parsing-20230810withHC` (engine `HC`, 4 rules, 281 entries) -- scale |
| Not usable | `Sena 3` -- engine `XAmple`, 0 rules. This feature's own engine gate refuses it, so it verifies nothing here. It is the right project for scenario 2's *negative*. |

Both live projects are installed under `C:\ProgramData\SIL\FieldWorks\Projects`.

---

## Scenario 0 -- the bridge

```
python -m flextoolsmcp.refresh
python -m pytest tests/test_flexicon_index_floor.py -q
python -m pytest -q
```

**Expected.** Three `v4.9.0` artifacts on disk (two under `index/python/`, one under
`index/`); the equality test green; the full suite green.

**Before accepting the equality test, watch it fail.** Revert the floor in
`pyproject.toml` to `>=4.8.0,<5` and re-run it -- it must go red naming
`pyproject.toml`. A test that has never been red has not been shown to detect
anything.

**Separately, and possibly later** (see `contracts/bridge.md`): in a clean
environment, `pip install "pyflexicon>=4.9.0,<5"` then `python -c "import flexicon;
print(flexicon.version)"` must print `4.9.0`. This cannot be run in this session and
its absence must be recorded as *not run*, never rounded into the equality test's
green.

---

## Scenario 1 -- a word parses, inline

```
flextools_try_word(project_name="IndonesianHC-Complete", word=<a word known to parse>, level="plain")
```

**Expected.** A complete result **in one call**, no `run_id`, within the 5-second
grace window. Run it a second time -- the grammar is already held, so the second call
must not re-enter `loading_grammar`.

**SC-004 is a rate, not a single observation.** It requires >=95% of attempts to
answer inline. Repeat the call across a set of words against the held grammar, record
the attempt count and the observed inline rate, and put both in the evidence
artifact. One fast call does not discharge this criterion, and reporting it as
discharged from one call is the impression rather than the measurement.

---

## Scenario 2 -- the engine gate fires first

```
flextools_try_word(project_name="Sena 3", word="anything", level="plain")
```

**Expected.** `parser_engine_mismatch`, naming `XAmple` as configured and `HC` as
supported. **No parser is constructed** -- assert the negative by recording calls
into the parser area and requiring zero.

Then flip `IndonesianHC-Complete`'s parser in FLEx (Words > Parser > Choose Parser)
mid-session and call again: the refusal must follow immediately, because
`ActiveParser` is re-read live per call and never memoized.

---

## Scenario 3 -- the plain level does not pretend to explain

```
flextools_try_word(..., word=<a word known to FAIL>, level="plain")
```

**Expected.** Reports that nothing parsed. Does **not** offer a reason. Its
`next_step` points at `restricted` or `explain` (FR-013).

Then run the same word at `explain`: the response carries the parser's trace of the
failure, not merely the failure.

---

## Scenario 4 -- the hypothesis is honoured, and an unresolvable piece is refused

```
# a: resolvable
flextools_try_word(..., level="restricted", morphs=[{headword: "...", position: 0}, ...])

# b: one piece resolves to nothing
flextools_try_word(..., level="restricted", morphs=[..., {headword: "zzzznotaword", position: 1}])
```

**Expected (a).** The trace is restricted to exactly the analyses given. Nothing is
reordered, scored or demoted. If the proposal agrees with recorded analyses, the
response says **nothing** about the agreement (FR-025).

**Expected (b).** `parse_morph_unresolved` with `morph`, `position`, `resolved_to`,
`candidates`, `hint` **in that order**; `resolved_to` is `none`. **No parse runs** --
assert the negative (SC-005).

Repeat (b) with a headword that matches several homographs (`resolved_to:
"ambiguous"`) and with one that matches an entry carrying no usable analysis
(`resolved_to: "no_msa"`). The three must stay distinct; collapsing them is the
silent-narrowing failure the requirement exists to prevent.

**Then the case most likely to be implemented wrong.** Supply a decomposition that
disagrees with every recorded analysis for the word. It must be traced **exactly as
given**, the disagreement reported as an observation with no confidence figure, and
the result neither reordered nor refused. A ranking-by-agreement implementation
passes scenario 4a and fails this.

---

## Scenario 5 -- the grace window is reporting, not execution

Against `Malay Parsing-20230810withHC` (41 entries cannot exercise this):

```
run = flextools_try_word(..., <enough work to exceed 5s>)
# -> a bare run_id
flextools_parse_status(run_id=run.run_id)   # poll
```

**Expected.**

1. A handle comes back and the work **continues** -- poll twice and watch
   `words_completed` advance. Closing the window cancelled and slowed nothing
   (SC-010).
2. Status distinguishes `loading_grammar` from `parsing`. On a cold run the first
   poll should land in `loading_grammar`.
3. `flextools_parse_status(run_id="no-such-run")` refuses with
   `parse_run_not_found`, naming the handle and listing the handles that do exist.

---

## Scenario 6 -- interleave, cancel, and survival

Still against the Malay project.

**Interleave.** Start a long run; while it is in `parsing`, submit a single word at
`TryAWord`. **Expected.** The urgent word begins within one word boundary; the batch
does not restart, repeats 0 words and does not lose position; the grammar is loaded
**exactly once** for both; and the batch's status reports `interleaved_by` rather
than appearing stalled (SC-009).

**Cancel.** Cancel a run mid-`parsing`. **Expected.** It stops at the next word
boundary, ends `cancelled`, and every result produced so far is still readable.
`flextools_parse_status` reports that **as a success**, with `words_completed` and
the stage at cancel -- not as a refusal. A second cancel against the same run is
`parse_job_cancelled`.

**Survival.** Kill the worker process mid-run. **Expected.** Every result written
before the kill is still readable in the run record -- for any N, 0 results lost
(SC-008). This is the scenario that proves per-word flush rather than buffered write.

---

## Scenario 7 -- LIVE WRITE, requires authorisation (E-D)

**Do not run this unattended.** It is the deferred tier A4: proving FR-043's stale
half live requires editing a project so the model registers as changed, which is a
write.

**Preconditions.** A human is present and has authorised it, against a **backed-up or
copied** project, never an installed project relied on for anything else. An
unattended run must stop and report `needs_human` instead.

**Steps.** Parse a word (grammar now held) -> make a model change -> parse again.

**Expected.** The held grammar's currency reads stale, the facade reloads **before**
the second word is parsed, and the second answer reflects the change. 0 parses served
from a grammar whose currency was not confirmed (SC-015).

**What stays unproven if this is not run.** The automatic path firing when the model
genuinely changes underneath a held grammar. `A3.3` already proved `Reload()`
discards unconditionally and `A1.6` proved the reload precedes the parse against a
stubbed currency read -- but the live link between a real model change and that
reload is covered by nothing else. Record it as **not run**; do not round it into the
suite's green.

---

## Scenario 8 -- the standing guarantees

```
python -m pytest tests/test_parser_no_xcore.py -q      # HCParser_DoesNotLoadXCore
python -m pytest tests/test_cp1_boundary.py -q
python -m pytest -q
```

**`HCParser_DoesNotLoadXCore`.** After a real `Update()` + `ParseWord()` **in the
worker process**, no `XCore` and no `System.Windows.Forms` assembly is loaded. It
must also assert positively that `ParserCore` *is* loaded and that the parse produced
a result -- a test that passes because the parse never happened is the failure mode
here.

**The CP1 boundary.** Still green, with its scope narrowed in writing to the CP1
surface and its worker-module allowlist entry pinned by a test. Amended, never
weakened: the guarantee that the *diagnostic* path still never parses is exactly the
one CP2b makes easier to break.

**The full suite** must include the SPEC 16 groups CP1 deferred -- the
no-user-interface-code guarantee, the no-oracle case, the conditional-proposal case,
and the script-library facade group.

---

## Scenario 9 -- no guidance points at nothing

```
flextools_health(verbose=True)
```

**Expected.** Every CP1 `next_step` row that degraded to `tool: null` because
`flextools_try_word` did not exist now names it, and the
`write: unavailable` / `read: ready` row's replacement action text is reverted to
wording that names the tool (FR-038, SC-011).

Grep the emitted guidance for tool names and assert every one exists in the registry
-- 0 references to tools that do not exist. Note that a "look it up" rung must be a
`flextools_run_module` snippet, not a tool call: no lexicon-query tool exists.
