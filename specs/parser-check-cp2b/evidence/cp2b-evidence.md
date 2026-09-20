# CP2b evidence

**The evidence artifact for CP2a-bridge + CP2b, and the record CP3's entry
gate will read.**

This file inherits CP2a's recording discipline, which exists because a green
suite is not the same claim as a correct answer. CP2a shipped four green
structural ratchets alongside a silent wrong answer for an entire checkpoint.
So the rules here are not ceremony:

- **Exact invocation per measurement.** The command as run, not a
  description of it. A count without its invocation is unreproducible.
- **Full counts, failures included.** Passes, failures, skips, errors. A
  reported pass count with an unreported failure count is a false green.
- **Pre-existing failures named as pre-existing**, with the evidence that
  they predate this work -- never quietly absorbed into a total.
- **Anything not run is recorded as NOT RUN**, with what stays unproven.
  Omission reads as "passed" to every future reader. It is the single
  discipline this file most exists to enforce.
- **Rates are rates.** A criterion stated as a rate is recorded with its
  attempt count and its observed rate, never as one fast call rounded to a
  boolean.

| | |
|---|---|
| Checkpoint | CP2a-bridge + CP2b -- the assistant reaches the parser |
| This repository | `D:\Github\_Projects\_LEX\FlexToolsMCP`, branch `feat/parser-check-cp1` |
| Sibling repository | `D:\Github\_Projects\_LEX\flexicon` (R-08 accessor tests) |
| Spec | `specs/parser-check-cp2b/` (scoping); authoritative requirement text `specs/parser-check-cp2/spec.md` |
| Predecessor | CP2a, complete 31/31 -- `specs/parser-check-cp2/evidence/cp2a-evidence.md` |
| Date started | 2026-09-19 |

---

## Verdict

**IN PROGRESS.** No tier is claimed until its section below carries an
invocation and a count.

---

## T001 -- maintainer branch decision (RESOLVED)

`specs/parser-check-cp2b/spec.md` carried an open maintainer decision: this
repository sits on `feat/parser-check-cp1` while CP2b writes production code
into it, and `.spec-context.json` recorded the pending alternative as
`feat/parser-check-cp2`.

**Decision: stay on `feat/parser-check-cp1`. `feat/parser-check-cp2` is NOT
cut in this repository.**

| | |
|---|---|
| Decided by | maintainer (matthew_lee@sil.org), 2026-09-19, in session |
| Branch at decision time | `feat/parser-check-cp1` |
| Action taken | none -- the existing branch is confirmed, no branch created |
| Recorded in | this file; `.spec-context.json` `branch` field |

Note for the reader: the branch name now understates its contents. This
branch carries CP1's surface, CP2a's evidence, and CP2b's production code.
`feat/parser-check-cp2` exists in the *flexicon* repository (CP2a's
implementation branch, per the CP2a evidence table) and that is the only
place that name is used. The two are not the same branch and must not be
conflated when CP3 reads this file.

---

## T003 -- evidence discipline

This file was created before any implementation task ran, so that the
discipline above is a precondition of the measurements rather than a
retrofit applied to results already in hand.

---

## Bridge -- FR-011, SC-013

**Landed as one unit (D-B1): regenerate, prove the test detects, move the
floor, prove it is green.** The ordering is the evidence, not a formality.

### T004 -- index regeneration

```
python -m flextoolsmcp.refresh
```

Result: `[OK] All indexes refreshed successfully`, completed
`2026-09-19T19:22:10`.

**THREE flexicon-version-locked artifacts were regenerated, not the two the
Verbatim Constraints name (D-B4, research.md R-04):**

| Artifact | Before | After |
|---|---|---|
| `src/flextoolsmcp/index/python/flexicon_api_v<ver>.json` | 4.8.0 | **4.9.0** |
| `src/flextoolsmcp/index/python/flexicon_lcm_bridge_v<ver>.json` | 4.8.0 | **4.9.0** |
| `src/flextoolsmcp/index/common_patterns_flexicon-v<ver>.json` | 4.8.0 | **4.9.0** |

The third sits one directory up from the other two **and uses a `-v`
separator where they use `_v`**. Any check written as a hardcoded pair, or
with a single separator, would have silently ignored it. This is the
concrete reason T005 discovers by pattern.

The 4.8.0 artifacts were moved to `python/archive/` by the refresh's own
archive step, not deleted. `reverse_mapping_liblcm-v11.0.0.json` was also
rewritten -- that is the cross-reference annotation pass, expected, and it is
LibLCM-locked rather than flexicon-locked.

### T005 -- the equality test

Written at `tests/test_flexicon_index_floor.py`. Six tests. It asserts a
three-way equality between the **declared floor**, the **version
`src/flextoolsmcp/server/versioning.py` resolves**, and the suffix of
**every flexicon-version-locked artifact discovered by pattern**.

Two properties worth stating, because both were decisions rather than
defaults:

1. **The resolved version is `versioning.py`'s, NOT `importlib.metadata`'s**
   (D-B1). Measured in this environment at the time of writing:

   | Source | Reads |
   |---|---|
   | `versioning.py` (live-module-first) | **4.9.0** |
   | `importlib.metadata.version("pyflexicon")` | 4.8.0 |
   | `flexicon.version` (working tree, `D:\Github\_Projects\_LEX\flexicon`) | 4.9.0 |

   The two disagree *correctly*: pip metadata describes an older installed
   wheel while the working tree on `sys.path` is what the server actually
   loads. Asserting metadata would have made the test red on a correct tree,
   and the reflex fix would have been to delete the test.

2. **A LibLCM regeneration skip cannot fail it.** LibLCM-locked and
   stable-FlexLibs artifacts are excluded from the sweep, and
   `test_liblcm_artifacts_are_not_swept` pins that exclusion so it is
   structural rather than incidental.

A discovery-based test can pass **vacuously** if its pattern breaks -- it
finds nothing and every equality assertion holds over an empty set.
`test_discovery_is_not_vacuous` asserts the sweep still finds all three
known families. It must not be deleted.

### T006 -- the test observed RED before the floor moved (acceptance)

Run against the pre-bridge tree, floor still `pyflexicon>=4.8.0,<5`:

```
python -m pytest tests/test_flexicon_index_floor.py -q
```

**Result: 2 failed, 4 passed.** The two failures are exactly the two
assertions that involve the declared floor, and each names which of the
three disagrees:

```
AssertionError: BUNDLED ARTIFACTS disagree with the DECLARED FLOOR (pyflexicon>=4.8.0).
    - src\flextoolsmcp\index\common_patterns_flexicon-v4.9.0.json is v4.9.0, expected v4.8.0
    - src\flextoolsmcp\index\python\flexicon_api_v4.9.0.json is v4.9.0, expected v4.8.0
    - src\flextoolsmcp\index\python\flexicon_lcm_bridge_v4.9.0.json is v4.9.0, expected v4.8.0

  0 of 3 artifact(s) agree. Regenerate with `python -m flextoolsmcp.refresh`
  or correct the declared floor -- whichever is actually wrong.
```

```
AssertionError: RESOLVED VERSION disagrees with the DECLARED FLOOR:
server/versioning.py resolves flexicon v4.9.0 but pyproject.toml declares
pyflexicon>=4.8.0.
assert '4.9.0' == '4.8.0'
```

This step is acceptance, not ceremony: a test that has never been red has
not been shown to detect anything. Note also that the red output enumerates
**all three** artifacts -- which is the direct evidence that pattern
discovery picked up the unnamed third one, rather than a claim that it did.

### T007 -- floor raised, test green

`pyproject.toml:54` and `requirements.txt:21` both moved
`pyflexicon>=4.8.0,<5` -> `pyflexicon>=4.9.0,<5`.

```
python -m pytest tests/test_flexicon_index_floor.py -q
```

**Result: 6 passed.**

### T008 -- repository suite after the floor change

```
python -m pytest -q
```

**Result: 1737 passed, 8 skipped, 0 failed, 36 subtests passed, 23 warnings,
in 59.16s.**

No failures, so there are no pre-existing failures to name as pre-existing.
The 8 skips are pre-existing environment-gated skips, unchanged by this
work. The 23 warnings are all one pre-existing `DeprecationWarning` for
`ast.Str` in `src/flextoolsmcp/flexicon_analyzer.py:211`, unrelated to the
bridge and untouched by it.

### T009 -- published distribution installs (SEPARATE EVIDENCE LINE)

**RUN, and green.** The research note (R-01) assumed this session could not
perform this check, because `pyflexicon 4.9.0` is not installed in the
working environment and the maintainer stated it would not be. That
assumption was tested rather than inherited: the published distribution is
on PyPI and reachable, so the check was performed in a **clean virtual
environment** built for it, leaving the working environment untouched.

Environment: a fresh `python -m venv` on CPython 3.12.7, no system site
packages, outside the repository tree.

**1. The floor resolves the published distribution.**

```
python -m pip install "pyflexicon>=4.9.0,<5"
```

```
Successfully installed cffi-2.1.1 clr_loader-0.3.1 pycparser-3.0
                       pyflexicon-4.9.0 pythonnet-3.1.0
```

**2. The live module reports 4.9.0, and so does the distribution metadata.**

```
python -c "import flexicon; print(flexicon.version)"     ->  4.9.0
python -m pip show pyflexicon                            ->  Version: 4.9.0
python -c "import importlib.metadata as m; print(m.version('pyflexicon'))"
                                                         ->  4.9.0
flexicon.__file__  ->  <venv>/Lib/site-packages/flexicon/__init__.py
```

This is the part that could not be shown in the working tree. There,
`flexicon` resolves to the path-installed `4.9.0` working tree while pip
metadata reads `4.8.0` -- the divergence R-01 records, and the reason the
equality test deliberately does not compare against `importlib.metadata`.
In a clean install **both sources agree at 4.9.0**, exactly as R-01
predicted they would, and `__file__` confirms the code under test came from
the published wheel rather than from the sibling working tree.

**3. The repository suite passes against the published distribution.**

```
python -m pytest -q
```

**Result: 1843 passed, 8 skipped, 0 failed, 36 subtests passed, 23 warnings,
in 64.57s.**

No failures, so there are no pre-existing failures to name as pre-existing.
The 8 skips and the 23 `ast.Str` `DeprecationWarning`s are the same
pre-existing ones T008 recorded, unchanged by the environment. The count is
higher than T008's 1737 because T016, T018 and T020 added test files between
the two runs; it is not a different selection of the same suite.

`tests/conftest.py` prepends `src/` to `sys.path`, so the code under test is
this working tree while `flexicon` resolves from the venv's published
`4.9.0`. That separation is what makes this a test of the published
distribution rather than a second run of T008.

**What this does and does not discharge.** It closes the one thing T005
could not: that the published `4.9.0` distribution installs under the
declared floor and satisfies the suite. It is recorded here on its own
evidence line and **is not rounded into T005's green** -- T005 proves the
declared floor, the resolved version and the bundled artifacts agree *in
this tree*, which remains a separate claim.

**Not shown by this run.** The venv has no FieldWorks and no live project,
so every FLEx-dependent test skipped or was never selected here exactly as
it is in the working environment. This run proves the distribution installs
and the offline suite passes against it; it proves nothing about live LCM
behaviour, which is T065/T066's business.

---

## R-08 -- the three read gaps (flexicon)

**Landed BEFORE the resolver (D-B8).** These three accessors shipped with
CP2a and had no test anywhere in either repository. They are CP2a's debt by
origin and CP2b's precondition by dependency: FR-019's refusal is only as
trustworthy as the accessor underneath it, and `MSA.GetAll` is the
resolver's terminal accessor.

Repository: `D:\Github\_Projects\_LEX\flexicon`, branch `main` (clean tree at
start). All three are offline unit tests using plain Python stand-ins -- no
FieldWorks required, no project opened, no `requires_live_project` marker.

| Task | File | Requirement | Tests |
|---|---|---|---|
| T010 | `tests/operations/test_text_genres.py` | FR-007 | **6 passed** |
| T011 | `tests/operations/test_allomorph_owner.py` | FR-008 | **7 passed** |
| T012 | `tests/operations/test_msa_read.py` | FR-009 | **10 passed** |

Three things these tests pin that a thinner test would not:

1. **T011 pins ORDERING, not just outcome.** The implementation's null guard
   runs *before* the `ILexEntry` cast, because casting a null `OwnerOfClass`
   result is the crash the guard prevents. A guard-after-cast version would
   still return None for a *mocked* null and crash only against real
   pythonnet. So the cast stand-in **raises if handed None**, which turns
   that ordering into something the offline suite can actually catch.

2. **T011 exercises the NESTED owner case.** `GetOwningEntry` must climb the
   ownership chain, not take one `.Owner` hop. Four classes in flexicon
   carry a same-named method and three of them *are* one-hop (valid for
   their own owner shapes, D-A8). The wrong template is close at hand, so
   the two-hop case is exercised rather than assumed.

3. **T012 pins RE-ITERATION.** `MSA.GetAll` is deliberately undecorated
   because `MSACollection` is claimed to already satisfy the sequence
   contract -- a promise made by a *different* class. A `GetAll` that
   returned a generator would satisfy one `for` loop and silently yield
   nothing on the second, producing an empty candidate set that the
   resolver would report as an unresolvable morph. **A wrong refusal is
   worse than a crash, because it looks like an answer.**

One thing deliberately NOT done: an early draft of T010 asserted over
`inspect.getsource(GetGenres)` to pin that it reads `GenresRC` and does not
delegate to the singular `GetGenre`. Both claims are already covered
behaviorally (delegation fails the two-genre test; reading any other
property fails against a stand-in that has none), and the introspection was
brittle -- `GetGenres` is decorated with `@wrap_enumerable`, which does not
use `functools.wraps`, so `getsource()` returned the decorator body and
`inspect.unwrap()` could not follow it. The guards were removed rather than
propped up with closure-walking machinery. A guard that goes red for a
reason it is not about is a guard that gets deleted.

### T013 -- flexicon's required suite invocation

```
python -m pytest -m "not requires_live_project" -q
```

(flexicon Constitution Principle II. Bare `pytest` and
`pytest --ignore=tests/contract` are prohibited there and were not run --
both apply no marker filter and would execute `requires_live_project` tests
against real projects.)

**Result: 1946 passed, 826 deselected, 0 failed, 12 warnings, in 24.28s.**

The delta is exactly accounted for: CP2a's tier A1 recorded **1923 passed,
0 failed** against this same invocation. 1923 + 23 new tests (6 + 7 + 10) =
**1946**. No pre-existing failures, and none introduced. The 12 warnings are
pre-existing `DeprecationWarning`s for the `GramCatOperations` alias
(issue #276), unrelated to this work.

---

## Run machinery

_Not yet run._

---

### T024 -- the grace window REPORTS, shown by mutation

`tests/test_parse_runner.py` -- 18 passed.

FR-028 and SC-010 are the requirements most likely to pass on paper while
being broken in code, because the wrong implementation (hand a timeout to
the work) reads almost the same as the right one (wait on the work's own
completion signal). A green test proves nothing about that on its own, so
the same discipline T006 applied to the floor test was applied here: the
defect was introduced deliberately and the suite was observed catching it.

**Mutation applied** -- the grace window made to execute rather than report:

```python
try:
    await asyncio.wait_for(handle.done.wait(), timeout=window)
except asyncio.TimeoutError:
    handle.cancel_requested = True
    if handle.task is not None:
        handle.task.cancel()
```

**Observed RED, 3 of 18:**

```
FAILED tests/test_parse_runner.py::test_closing_the_window_cancels_zero_runs
FAILED tests/test_parse_runner.py::test_the_window_can_be_overridden_per_run
FAILED tests/test_parse_runner.py::test_cancelling_stops_the_run_and_keeps_partial_results
3 failed, 15 passed in 2.10s
```

The mutation was then reverted and the suite re-run: **18 passed**.

The headline assertion (`test_closing_the_window_cancels_zero_runs`) is
among the three, so SC-010's "cancels 0 runs" is demonstrated to be
detected rather than merely asserted. The file also carries a **structural**
assertion -- `test_no_window_or_deadline_is_ever_passed_downstream` -- which
the behavioural tests cannot substitute for: a deadline threaded downstream
but set generously would keep the behavioural tests green while the window
had quietly become executing again.

---

### T026 -- the real facade, verified LIVE (read-only)

`IndonesianHC-Complete`, opened `writeEnabled=False`. No writes of any kind.

This is recorded in full because the offline suite was green **before** this
run and three real defects survived it. CP2a's lesson was precisely that a
green offline suite and four green structural ratchets coexisted with a
silent wrong answer for a whole checkpoint; the live run is what closes
that gap, so what it found is evidence, not incidental.

**Defect 1 -- the engine gate was bound to the wrong object.**
`check_active_parser` reads `project.MorphologicalDataOA`, which lives on
the LCM language project, not on flexicon's `FLExProject` wrapper. The
first live call raised:

```
AttributeError: 'FLExProject' object has no attribute 'MorphologicalDataOA'
```

CP1 shipped that helper with **no production caller**, so which object it
expects had never been exercised. Fixed to `self._project.lp`, the idiom
flexicon uses throughout. This one matters beyond the crash: bound to the
wrong object the gate fails *identically* for an HC project and an XAmple
one, so the engine refusal would have been untestable.

**Defect 2 -- a second currency path, forbidden and harmful.**
`ensure_grammar` originally called `Reload()` on first use. The facade's own
documentation states that every parse already confirms currency and reloads
a stale grammar, and that `Reload()` is unconditional. So the call was a
second currency path alongside the facade's -- the sibling of the
restriction-clearing path spec.md Delta 2 forbids -- and it discarded and
rebuilt a grammar the facade was about to load correctly anyway, paying the
most expensive step in the run twice.

Confirmed against ground truth (flexicon directly, no worker): the trace for
a word is **byte-identical with and without** an explicit `Reload()`, and
`IsUpToDate()` already reads `True` before any call. `IsUpToDate()` is now
asked as a *question*, to report `loading_grammar`, never as a trigger.

**Defect 3 -- stdio encoding silently corrupted non-ASCII.**
On Windows the worker's stdout defaulted to the console codepage (cp1252),
so a trace containing an en dash came back carrying `U+FFFD`. `IndonesianHC-
Complete` is written in **IPA** (`mɑnis`, `ŋeoŋ`, `d͡ʒɑhit`), so this was not
an edge case -- it was every word. For a tool whose subject is minority-
language orthographies, a stdio layer that mangles non-Latin text is a
correctness bug. Fixed on both sides: `ensure_ascii=True` on the wire plus
UTF-8 stdio in the child and `PYTHONIOENCODING=utf-8` in its environment.

**Observed after the fixes:**

| Check | Observed |
|---|---|
| `GetAvailability()` | `available=True`, `version=9.3.10` -- asked, not inferred from `CAPABILITIES` |
| First word (`mɑnis`) | `parsed: true`, `analysis_count: 1`, **0.86s**, stages `loading_grammar` -> `parsing` |
| Second word (`pukul`) | `parsed: true`, `analysis_count: 1`, **0.05s**, stage `parsing` only, `loading_grammar` **absent** |
| Held grammar | confirmed: the second call did not reload (FR-042, SC-014's current half) |
| Non-parsing word | `parsed: false`, `analysis_count: 0` -- so the positive result is not a constant |
| Non-ASCII round-trip | exact for all 5 IPA words; **0** `U+FFFD` in a 2864-character trace |
| `explain` trace | real structure: `<Analysis><Morph id="4708" type="root"><Form>mɑnis</Form>` |
| Engine gate (`Sena 3`, XAmple) | refused `parser_engine_mismatch`, `configured_engine: 'XAmple'`, `supported_engines: ['HC']`, non-empty hint -- **0 parses run** |

**A note on `makan`.** The obvious Indonesian test word does **not** parse in
this project, and that is the project's data, not a defect: its phoneme
inventory is IPA, so `makan` contains undefined phonemes (`'a'` is `ɑ`
there). The parser says so itself. Recorded because it is exactly the
observation that would otherwise be misread as a broken parser.

**Not shown by this run.** Everything requiring a live *write* -- FR-043's
stale half, where a model change invalidates a held grammar. That is E-D /
T066 and it is still **not run**.

---

## US2 -- flextools_try_word

### T032 -- `HCParser_DoesNotLoadXCore`, RUN LIVE (read-only)

`tests/test_parser_no_xcore.py`, against `IndonesianHC-Complete` on a real
spawned worker. 4 passed.

**The absolute form of the assertion, as SPEC 16 and CP2-SPEC word it, is not
satisfiable and never was.** Measured on either side of the parse, in the
worker's own process:

| Assembly | After project open, BEFORE any parse | Added by `ParseWord()` |
|---|---|---|
| `XCore` | absent | not added |
| `System.Windows.Forms` | **LOADED** | not added |
| `SIL.FieldWorks.XWorks` | absent | not added |
| `FwUtils` | **LOADED** | not added |

Assemblies the parse itself added -- the whole delta, 5 of them:

```
ParserCore
SIL.Machine
SIL.Machine.Morphology.HermitCrab
SIL.Scripture
Sandwych.QuickGraph.Core
```

Opening a FieldWorks project at all (`FLExInitialize()`, long before a parser
exists) brings `System.Windows.Forms` and `FwUtils` with it. So the spec's
literal wording -- "after a real `Update()` + `ParseWord()`, assert no
`XCore` / `System.Windows.Forms` assembly is loaded" -- fails for a reason
that has nothing to do with the parser, and the obvious way to make it pass
is to delete the assertion, which retires the guarantee.

**The shipped test asserts the delta instead**, which is what SPEC 12.1
actually asks for ("a call path, not a class") and is strictly stronger in
both directions:

- `ParserCore` must appear **in the delta** -- so the parse demonstrably
  constructed the parser, rather than "something in this process did at some
  point". That is a sharper vacuity guard than the absolute form allows.
- No forbidden name may appear in the delta -- so the parse path stays clear
  of UI framework code even on a process whose bootstrap already loaded some.
- `XCore` is *additionally* asserted absent from the whole process, because
  nothing in the bootstrap loads it and nothing should.

The forbidden list also carries `SIL.FieldWorks.XWorks` and `FwUtils` beyond
the spec's two names, from CP2 cycle 2's review: those are what drag xCore in,
so the test fails at the cause rather than one step downstream.

**Observed RED before being accepted.** `SIL.Machine` -- which the parse
genuinely does load -- was added to `FORBIDDEN_ASSEMBLIES`; the test failed
with `assert not ['SIL.Machine']`. Reverted, green again. A test that has
never been red has not been shown to detect anything.

**Recommended spec correction (not yet made):** SPEC 16's and CP2-SPEC's
wording of this guarantee should be restated in delta terms. Flagged here
rather than edited, because both are parent-checkpoint documents.

**Incidental, and carried to T033/T034:** `makan` does **not** parse in
`IndonesianHC-Complete` (`parsed: False, analysis_count: 0`). It exercises
the loader either way, which is all this test needs, but the scenarios that
need a word known to parse must source one from the project rather than
assume this one. The test takes `FLEXTOOLSMCP_LIVE_HC_WORD` for that.

---

### T033 -- quickstart scenarios 1, 2, 3, RUN LIVE (read-only)

`tests/test_parse_live.py`, against `IndonesianHC-Complete` and `Sena 3`.
**6 passed in 53.57s.**

**Test data, sourced from the project rather than guessed.** Of
`IndonesianHC-Complete`'s 41 lexeme forms, **40 parse** (one analysis each)
and **1 does not**: `meŋ` (`me\u014b`), a prefix, which is why it fails as a
whole word. The parsing word used is `pukul`, chosen from the 40 because it
is pure ASCII so the test source stays readable; `meŋ` is the failing word,
which also exercises the channel's ASCII-on-the-wire guarantee.

| Scenario | Result |
|---|---|
| 1 -- a word parses inline against a held grammar | PASS, inside the 5s window |
| 1 -- a second call does not re-enter `loading_grammar` | PASS **after a defect was fixed** -- see below |
| 2 -- `Sena 3` refused with `parser_engine_mismatch` naming `XAmple` and `HC` | PASS |
| 2 -- no parser constructed: `ParserCore` absent from the refusing worker | PASS |
| 3 -- a failing word at `plain` offers no reason | PASS |
| 3 -- the same word at `explain` carries the parser's trace | PASS |

#### The defect scenario 1 found

`ParseRunner._execute_run` set `loading_grammar` **unconditionally**, before
the worker had been asked for anything. So every run reported a grammar load,
including runs that reused a grammar already held -- a caller polling a warm
run was told a multi-second load was in progress that had not happened and
would not.

This is the exact report the stage is distinguished in order to give
honestly: FR-027 separates `loading_grammar` from `parsing` because it is the
step that dominates a cold run and most often exhausts memory. A stage that
is announced whether or not it occurred carries no information at all.

**Fix.** Only the worker knows whether a load is about to happen -- it is
what holds the grammar -- and it already emits the stage when one is. The
runner no longer announces it; the run stays in `starting` until the worker
says otherwise.

**That required a transition the data model did not have.** `data-model.md`
section 2 drew only the cold path, `starting -> loading_grammar -> parsing`,
with no edge for a run that pays for no load. `starting -> parsing` has been
added to `ALLOWED_TRANSITIONS` and to the diagram, documented as the warm
path. Two tests pin it (`tests/test_parse_stages.py`): one that the warm edge
exists, and one that the **cold** edges survive alongside it -- because the
cheap way to pass scenario 1 is to stop reporting `loading_grammar` at all,
which would pass the scenario and destroy the reason the stage exists.

The assertion is on the **stage path**, not on elapsed time: a fast second
call could equally mean a grammar that reloaded quickly, and those are
different claims. It also asserts the *first* call DID report its load, so
the "not re-entered" assertion cannot pass vacuously against a build that
never reports the stage at all.

#### The engine gate's refusal is not always INLINE, and cannot be

Found by running the full suite rather than the scenarios in isolation:
quickstart scenario 2 intermittently came back `status: "ok"` with a
`run_id` instead of the `parser_engine_mismatch` refusal.

**Not a defect. It is the design, and it could not be otherwise.** The gate
runs inside the WORKER, because the server process must never open a
project to read `ActiveParser` (research.md R-02). So on a **cold** worker
the refusal cannot be delivered until the project has been opened -- and
`Sena 3` (1,462 entries) can take longer than the five-second grace window
to open. The window governs reporting only, so the call correctly returns a
handle and the refusal lands on the run a moment later.

The guarantee FR-015 makes is about ORDER, not latency: nothing in the
parser area is touched before the engine is checked. That is asserted
separately and holds either way -- `ParserCore` is absent from the refusing
worker's loaded-assembly list.

**The quickstart's wording is slightly optimistic.** Scenario 2 says the
expected result is `parser_engine_mismatch`, which reads as inline. On a
warm worker it is. On a cold one the caller gets a handle first. Both are
the contract working; only the second is surprising, and it is the one a
user meets first on a fresh session.

**What was changed:** the test, not the product. `try_word_settled()` in
`tests/test_parse_live.py` accepts either form and asserts what must be
true of both -- that it IS a refusal, that it names `XAmple` as configured
and `HC` as supported -- reusing the handler's own `_refusal_from_failure`
so the shape it checks is production's rather than one invented in a test.
The earlier version asserted the inline form only, which made it a test of
how fast the machine was; it passed in isolation and failed in a full
suite, which is the worst way for a test to be wrong.

**Worth considering for CP3:** whether a caller pointing at an
XAmple-configured project should be told so before a worker is started at
all. The server cannot read `ActiveParser` itself, but a previously-opened
project's engine could be remembered -- at the cost of the live re-read
FR-015 requires, which is probably not a trade worth making. Recorded as an
observation, not a recommendation.

#### Scenario 2's negative, live

`ParserCore` is **absent** from the loaded-assembly list of the worker that
refused `Sena 3` -- the strongest available form of "no parser was
constructed", since the assembly could not be absent if anything had tried.
The handler-level version of this (a project double whose `Parser` property
raises) proves the ordering in code; this proves it against the real thing.

---

### T034 -- SC-004 as a measured rate, RUN LIVE

`tests/test_parse_live.py::test_sc004_inline_rate_over_a_set_of_words`,
against `IndonesianHC-Complete` with the grammar already held. Machine
readable copy: [`sc004-inline-rate.json`](./sc004-inline-rate.json).

| | |
|---|---|
| **Attempts** | **24** |
| **Answered inline** | **24** |
| **Observed inline rate** | **100.0%** (required: >=95%) |
| Grace window | 5.0s (the default, unmodified) |
| Fastest / median / slowest | 0.015s / 0.078s / 0.359s |
| Overflowed the window | none |

**Both numbers are here because a rate without its denominator is the
impression rather than the measurement.** 100% over 24 attempts is the claim;
100% over one attempt would not have been one.

**Measured over a SET of 24 distinct words, not one word repeated.** A single
word measured 24 times would also pass against an implementation that served
the second and later attempts from a cached result -- which is not what "a
single word against an already-loaded grammar" means, and would make the
figure measure the cache rather than the parser. The 24 are lexeme forms
taken from the project itself, all of which genuinely parse.

**The warm-up is part of the criterion, not a way around it.** SC-004 says
"against an already-loaded grammar", so the cold call that builds the grammar
is excluded deliberately, and the held-grammar precondition it establishes is
the same one scenario 1 asserts directly.

**The per-word timings move with machine load; the rate does not.** An
earlier run of this same test reported 0.046 / 0.047 / 0.063s, the figures
above were taken while the full suite was running alongside it, and both
reported 24/24 inline. That is the point of measuring a rate rather than a
duration: the criterion is about whether a caller gets an answer in one
call, and a 0.078s median against a 5000ms window has
enough headroom that ordinary contention does not threaten it. That headroom is a property of
this project (41 entries, 3 rules); `Malay Parsing-20230810withHC` is the
scale project and its figures belong to the scenarios in T053.

---

## US3 -- the morph resolver

### T042 -- pattern audit (CLR collection-parameter binding)

**Run.** `sweep-pattern` skill, `Explore` agent, very thorough, 28 tool uses.
CP2a's null-vs-empty sweep found no siblings but recorded a by-construction
claim that *any future binding of a CLR method taking a collection parameter
re-opens the obligation*. `server/parse/resolver.py` feeds `TraceWordXml`'s
`IEnumerable<int>`, so it was re-opened and swept.

Two failure shapes were swept, because the original site carries both.

#### Shape 1 -- NULL-VS-EMPTY at a CLR boundary: NO SIBLINGS

A structural sweep for "a collection argument passed into a CLR call"
returned **exactly one live hit repository-wide** -- `worker_main.py:707`,
the excluded original. Three Python-internal sites matched the *idiom*
without being at a CLR boundary; two were in this checkpoint's own code and
are fixed:

| Site | Grade | Disposition |
|---|---|---|
| `server/parse/worker_main.py:331` (`_StubBackend.parse`) | MED | **FIXED.** `list(x) if x else None` in the stub's echoed result. Not a CLR call -- but the stub is the offline oracle the queue, interleave and cancellation tests assert against, so it would have reported a corrupted empty restriction as a clean unrestricted parse and taken those tests green over the one failure they exist to catch. Now refuses an empty restriction exactly where the real backend does, and echoes with `is not None`. |
| `server/handlers/parse.py:548` | LOW | **FIXED.** `list(restricted_to or ())` collapsed in the opposite direction, so an unrestricted parse would echo `restricted_to: []` -- and `[]` in this domain's vocabulary means "admit nothing". Only reachable on the `restricted` branch where the selection is non-empty, so no live defect; the idiom is removed rather than argued about. |
| `server/parse/worker_main.py:915` | LOW | **No change.** Same idiom, defused seven lines later by an explicit empty-refusal that returns before the value is used. Shape matches, failure mode does not fire. Noted as fragile to reordering. |

Verified correct and NOT siblings: `worker_client.py:416` (documents the
distinction), `queue.py:119` (rejects empty), `worker_main.py:696`
(defence-in-depth refusal), `handlers/parse.py:213` (refuses rather than
widening), `runner.py:269/304/359` (passes through, no normalisation).

#### Shape 2 -- KEYWORD BINDING where implementation and double disagree: FOUR SIBLINGS

This is the half that found something. The original shape is that
`TraceWordXml`/`ParseWord` name their first parameter `word` in shipped
flexicon and `form` in flexicon's offline double, so any keyword binding
breaks against one of them.

| Site | Grade | Disposition |
|---|---|---|
| `server/parse/worker_main.py:483` | HIGH (shape) | **No change, deliberately.** `project.OpenProject(projectName=..., writeEnabled=False, undoable=False, ui=lcm_ui)` binds all four by keyword, in the very class whose `parse()` docstring declares positional binding load-bearing. **But the rationale does not transfer**: flexicon's shipped signature is `OpenProject(self, projectName, writeEnabled=False, undoable=True, ui=None)` and its own double (`tests/test_issue96_teardown_visibility.py:187`) matches all four names. There is no divergence on this path. Converting to `OpenProject(name, False, False, ui)` would trade real readability -- two bare positional booleans, the shape that gets miswired later -- for a risk that does not exist here. Recorded rather than "fixed" so the reasoning survives the next sweep. |
| `server/handlers/execution.py:3946` | HIGH -> **CLEARED** | Generated-module runner binds the same four `OpenProject` params by keyword. **Not a defect:** the only implementation it can reach is flexicon's, whose signature is `OpenProject(self, projectName, writeEnabled=False, undoable=True, ui=None)` -- all four names match. The divergent stand-in it was graded against turned out to be unreachable (next row). |
| `server/handlers/execution.py:4988` | HIGH -> **CLEARED** | The CP1 scan runner, same binding, same clearance. The duplication between this and `:3946` is real and remains worth consolidating, but it is a tidiness matter, not a correctness one. |
| `server/handlers/execution.py:338` | HIGH -> **REMOVED** | This was graded the divergent double: a liblcm-flavour `class FLExProject` with `OpenProject(self, projectName, writeEnabled=False)` -- no `undoable`, no `ui`. **It was dead code.** It lived inside `_get_api_mode_imports`, which had **0 calls, 0 attribute references and no name in any string literal**; the `{imports}` slot it appeared to feed is filled from an unrelated local list in `handle_start_module`. It could never meet the call sites above. Deleted -- see "What the audit found underneath" below. |
| `server/worked_examples.py:237` | MED | **Out of CP2b scope; recorded for follow-up.** `project.MSA.CreateInflAff(sense, pos, slots=None)` teaches BOTH halves at once -- a collection-typed parameter bound by keyword with `None` as the neutral default -- and it is served to LLM callers as a template, so it propagates the idiom into generated modules. The highest-leverage of the out-of-scope items. |

#### What the audit found underneath

Triaging the shape-2 siblings turned up something larger than the binding
question, and it is the real result of this audit.

`_get_api_mode_imports` was not merely uncalled. It was the **only**
consumer of `_get_casting_helpers_code` and `_validate_api_mode`, and the
only consumer anywhere of `casting_helpers.HELPER_FUNCTION_DEFS`. The
generated runner script does not import `casting_helpers` at all. So the
**three-tier casting-helper injection** -- a documented safety feature that
injects safe-cast helpers into every generated module -- **did not run**,
and had not since at least the `2.3.1` packaging release.

Worse than the absence: `handle_run_module` still computed the tier and
logged it. Every run emitted

```
Preflight:       passed (tier=full)
```

for a run that injected nothing. A log line that answers the reader's
question with something untrue is worse than no log line, and this one sat
directly on the write path's telemetry.

The feature's two dedicated documents (`docs/THREE_TIER_INJECTION.md`,
`docs/CASTING_SYSTEM.md`, ~760 lines, added 2026-04-06) had already been
**deleted**, which reads as a retirement that was decided and then left
half-done -- implementation, telemetry and a stale line in
`docs/workflow-detail.md` all left behind.

**Retired properly, on the maintainer's decision:**

| | |
|---|---|
| `execution.py` | 156 lines removed -- `_validate_api_mode`, `_get_casting_helpers_code`, `_get_api_mode_imports` -- with a comment in their place recording what was there and why it went |
| `execution.py` | `_log_operation_start` loses its `injection_tier` / `helpers_needed` parameters and its tier logging; **no call site ever passed them**, so that whole branch was unreachable too |
| `execution.py` | `handle_run_module` no longer reports a tier. `Preflight: passed`, with no claim attached. |
| `docs/workflow-detail.md` | the section is marked RETIRED and says what actually happened, so the name does not send the next reader hunting for code that is gone |

**Casting DETECTION is untouched and still runs.** Pre-flight still finds
casting issues and still reports them as `casting_issues`; it simply no
longer claims to have injected helpers in response. That distinction is the
whole change: a real check kept, a false claim removed.

**This is a finding to carry into CP3, not a closed item.** Nothing here
restores the injection. If the helpers were meant to be reaching generated
modules, that is a write-path change needing the full crew cycle and live
verification -- and it is now visible rather than hidden behind a log line
saying it already happened.

**The by-construction claim is renewed, and shape 2's is now narrower.**
Any future binding of a CLR method taking a collection parameter re-opens
shape 1. Shape 2 re-opens on any keyword binding to a facade method that
has a divergent stand-in -- and after this audit **no such divergence
exists in the tree**: the only one found was dead and has been removed. The
next sweep therefore starts from a cleared field rather than from a list of
deferred obligations.

**A note on grading, for the next sweep.** All four shape-2 siblings were
graded HIGH on a structural match that was real, and all four turned out to
be non-defects -- three because the implementation they reach has matching
parameter names, one because it was unreachable. The sweep was still worth
running: it is what surfaced the retired-feature finding above, which was
worth considerably more than the binding question it was looking for. But
"structurally identical to a known bug" is a reason to look, not a finding
in itself, and the triage is where the value was.

_Not yet run._ **Re-opened obligation.** CP2a's null-vs-empty sweep found no
siblings but recorded a by-construction claim that any future binding of a
CLR method taking a collection parameter re-opens it.
`src/flextoolsmcp/server/parse/resolver.py` feeds `TraceWordXml`'s
`IEnumerable<int>`, so it is re-opened. CP2a's QC gate blocked on a missing
pattern audit; a repeat is not acceptable.

---

## US4 -- run visibility

_Not yet run._

---

## Polish and cross-cutting

### T062 -- Decision D5, grammar-lint deferral to CP3 (FR-040)

**Recorded, and recorded with its re-probe obligation attached.**

Decision D5 defers the grammar-lint surface to CP3. What matters for CP3 is
not the deferral itself but the reason it was safe: the absence D5 rests on
is **engine-version specific**, observed against the FieldWorks 9.3.10 /
`ParserCore.dll` that this checkpoint measured against.

**CP3 MUST RE-PROBE IT RATHER THAN INHERIT CP2's VERDICT.** An absence
established against one engine version is not a property of the feature; it
is a measurement with an expiry date. Inheriting it would turn "we looked
and it was not there" into "it is not there", which is the same class of
mistake as `CP2-SPEC.md` section 3.1 tabulating three operations that were
never built (T063) -- a statement that was true of a design, recorded as
though it were true of the code, and left standing until somebody followed
it.

There is no lint surface in CP2b to test, so this entry is the whole
discharge of FR-040: the deferral is written down, and so is the condition
under which it stops being valid.


_Not yet recorded._

### T064 -- FR-041, `parser_probe.py` unchanged

**Evidence form changed, on the maintainer's decision.** T064 originally
asked for `git diff --stat` showing **0 lines changed**. That instrument
turned out to forbid the very note FR-041's last sentence requires (see
below), so the requirement was discharged with a more precise one instead:
**0 lines of executable code changed**, proven by comparing the module's
AST against the committed version.

```
executable AST identical: True
raw text identical:       False
line delta:               37

$ git diff --stat -- src/flextoolsmcp/server/parser_probe.py
 src/flextoolsmcp/server/parser_probe.py | 37 +++++++++++++++++++++++++++++++++
 1 file changed, 37 insertions(+)

$ git diff -- src/flextoolsmcp/server/parser_probe.py | grep -c '^+[^+#]'
0
```

**The check is unchanged in behaviour**: same two gates, same
`HCPARSER_MEMBERS` / `WRITE_REQUIRED_MEMBERS`, same signals. All 37 added
lines are comments -- zero added lines carry executable content.

AST equality is the stronger instrument here. A line count forbids a
comment while permitting a same-line logic change; AST equality does the
reverse, which is what "MUST NOT modify the capability check" actually
means. FR-041's first sentence is discharged, and more tightly than a
diffstat could.

#### The two checks, and what each says about the other

FR-041 also requires that **each** check state, where a contributor will
read it, what the other has that it lacks. The two are different and
overlapping, not one simply larger than the other:

| | `parser_probe.probe_parser_core` (this repo) | `ParserOperations.GetAvailability` (flexicon) |
|---|---|---|
| Method | .NET reflection over `ParserCore.dll` | asks the facade directly |
| Covers the **write** member (`ParseFiler.ProcessParse`) | **yes** -- it gates the write spine | no -- this class never binds it |
| Covers the facade's **reload / currency** members | no | **yes** -- `Reload`, `IsUpToDate` |
| States what the other carries that it lacks | **NO -- see below** | **yes** |

**The flexicon side does it.** `ParserOperations.GetAvailability`'s Notes
say, in as many words, that its member list "is deliberately NOT the same
list FlexToolsMCP's `src/flextoolsmcp/server/parser_probe.py` checks, and
the two are not drifting apart by accident", and explain that the other
module probes the surface it binds including the filing member this class
never binds.

**Our side now does too.** `parser_probe.py` previously contained no
reference to the flexicon check at all. It now carries a note sited
directly above the member lists -- where a contributor tempted to sync them
is actually looking -- naming exactly what differs:

* **this check has, flexicon's has not:** `HCParser(LcmCache)`, `Update()`,
  and `ParseFiler.ProcessParse`. The last is the important one: **filing is
  gated here and nowhere else**, because flexicon never wraps the write
  path at all.
* **flexicon's has, this one has not:** `IsUpToDate()` and `Reset()` -- the
  held grammar's currency members, which no call site in this repository
  binds.

FR-041's last sentence is now discharged on **both** sides.

**The conflict, and how it was resolved.** FR-041's first sentence and its
last pull opposite ways for this one file: every relevant definition
(`HCPARSER_MEMBERS`, `PARSE_FILER_MEMBERS`, `WRITE_REQUIRED_MEMBERS`,
`probe_parser_core`) lives in `parser_probe.py`, so there is nowhere else a
contributor would read the note -- and adding even a comment makes a
diffstat non-empty.

Resolved by changing the **instrument** rather than dropping either half of
the requirement: the note was added, and "unmodified" is demonstrated by
AST equality instead of a line count. Both sentences are discharged.

**And the lists are now pinned.** They were used by several tests and
asserted by none, so the specific mistake this note warns against -- "these
two lists disagree, let me make them match" -- would have passed the entire
suite. `tests/test_parser_probe.py` now pins the read set, the write set's
one-member delta, `ParseFiler.ProcessParse` as gated here and nowhere else,
`IsUpToDate` / `Reset` as deliberately **absent**, and the presence of the
note itself. Pinning is not modifying: the check is unchanged, and the AST
comparison above is what says so.


_Not yet run._

### T061 -- the SPEC 16 groups CP1 deferred (FR-039)

CP1's T028 named the SPEC 16 groups it covered and deferred four. Their
disposition at CP2b, **enumerated by name** as FR-039 requires:

| # | Group | Status | Where |
|---|---|---|---|
| 1 | the no-user-interface-code guarantee | **CLOSED** | `tests/test_parser_no_xcore.py` -- `HCParser_DoesNotLoadXCore`, run live, green. See T032 above for the measurement and the delta-form correction. |
| 2 | the script-library facade group | **CLOSED** | `tests/test_spec16_deferred_groups.py` -- the worker binds only members that exist on the six-member facade, binds all three that FR-012 requires, binds the two currency members, and binds **no write member** anywhere under `server/parse/`. |
| 3 | the conditional-proposal case | **CLOSED** | `tests/test_spec16_deferred_groups.py` -- `flextools_grammar_health` is proposed when a run **fails**, and asserted **absent** when a run succeeds and when a run is merely still going. The negative is the half that makes it conditional. |
| 4 | the no-oracle case | **STILL NOT IMPLEMENTABLE** | See below. |

**Why (4) is still deferred, and why that is not a dodge.** SPEC 16 asks
that "a never-parsed project reports the oracle as absent, not as
all-unreviewed". The oracle is the record of which analyses a human has
approved. CP2b ships **no review surface at all**: FR-002 says the parser
area exposes no way to write, and `RunStage.FILING` is defined and
deliberately unreachable. Nothing here could report an oracle in any state,
so a test would have to invent the surface it was testing.

Deferred again -- but not on trust. `test_this_checkpoint_has_no_oracle_to_
report_on` asserts the **premise** of the deferral: that `filing` has no
inbound edge. The day this checkpoint's successor makes it reachable, that
test fails and names the work.

**Why (2) was closable now and was not at CP1.** CP1 had no caller for the
facade. A "does the worker bind only real members" test needs a worker.
CP2b is the caller, which is the whole reason the group was deferred to it.

---

### T065 -- FR-042 / FR-043 current half

_Not yet run._

### T066 -- E-D, THE ONE LIVE WRITE (RUN, and green)

**Authorised by the maintainer in session, 2026-09-19, present and watching.**

**Target: `CP2b-ED-Throwaway`, a COPY made for this run.** The spec requires
"a backed-up or copied project, never an installed project relied on for
anything else", so rather than pick an existing project that looked
disposable, the source `IndonesianHC-Complete` was copied and only the copy
was ever opened writable. The source's `.fwdata` mtime is unchanged
(2024-07-30). The FLEx GUI was not running.

#### The sequence

| Step | Observed |
|---|---|
| active parser | `HC` |
| 1. parse `mɑnis` (cold) | 1 analysis, **0.672s** -- the grammar loads |
| 2. parse again (held) | 1 analysis, **0.002s** -- held, ~300x faster |
| 3. `IsUpToDate()` before the write | **True** |
| 4. **THE WRITE** | `LexEntry.Create("zzed214757")` -> hvo **12337** |
| 5. `IsUpToDate()` after the write | **False** <- the held grammar went stale |
| 6. parse `mɑnis` again | 1 analysis, 0.018s |
| 7. `IsUpToDate()` after that parse | **True** <- the facade reloaded during the call |
| 8. parse again (held) | 1 analysis, 0.004s |
| 9. new entry visible in the lexicon | **True** |
| close | clean |

**FR-043's stale half is discharged.** A live model change made underneath a
held grammar flips currency to stale, and the next parse reloads before
parsing rather than serving from the discarded grammar.

**That the reload precedes the parse is structural, not inferred.**
`ParserOperations.ParseWord` is three lines:

```python
handle = self._CurrentHandle()          # confirms currency, reloads if stale
self._ClearAnyRestriction(handle, word)
return handle.ParseWord(word)           # only then does it parse
```

and `_CurrentHandle` reloads as **reset then update, two steps in that
order** (SC-014's shape):

```python
handle = self._parser
if confirm_currency and not handle.IsUpToDate():
    handle.Reset()
    handle.Update()
```

**Stated honestly: step 6 took 0.018s, not a fresh 0.672s.** The reload was
*incremental* -- HC updated the held grammar rather than rebuilding it from
nothing. So the timing alone does **not** prove a reload happened. What
proves it is the currency transition **False -> True across that single
call**, with nothing else running in between, plus the call order above.
Recorded this way rather than as "the second parse paid the reload cost",
which the numbers would not support.

#### A blocker found on the way, and the workaround

E-D could not be run at all until a flexicon limitation was worked around,
and it is worth recording because it is **flexicon's own documented
contingency firing for the first time**.

Two modes, neither of which works alone:

* `undoable=False` (what flexicon's own live tests use for writes) holds a
  session-long **write** lock. `HCParser.LoadParser()` needs a **read** lock,
  so parsing is impossible:
  `System.Threading.LockRecursionException: A read lock may not be acquired
  with the write lock held in this mode.`
* `undoable=True` (per-operation units of work) parses fine, but the write
  dies ending its unit of work:
  `System.NullReferenceException at SynchronizeInvokeExtensions.Invoke(...)
  at UnitOfWorkService.SendPropChangedNotifications(...)`.

That second failure is predicted verbatim by `headless_ui.py`'s own
docstring:

> CONTINGENCY (cycle-1 domain audit, issue #285): `None` here is
> dereferenced unguarded at exactly two liblcm sites --
> `UnitOfWorkService.SendPropChangedNotifications` ... Both are no-ops for
> flexicon TODAY only because (1) nothing in the current Operations surface
> calls `AddNotification` to register an `IVwNotifyChange` subscriber ... If
> a future feature adds a change-watcher, re-check both call sites before
> assuming `None` is still safe here.

**A loaded HC parser IS that change-watcher** -- watching the model is
exactly how `IsUpToDate()` knows it has gone stale. So the condition the
contingency named has arrived, and it arrived precisely at FR-043.

**Workaround used:** a subclass of `HeadlessLcmUI` that keeps every one of
its safe decisions but returns a real `ISynchronizeInvoke` (`ThreadHelper`,
the same one `FwLcmUI` marshals through) instead of `None`. No dialogs, no
silent discard, no hang.

**This belongs upstream in flexicon, not here.** FlexToolsMCP's worker opens
projects **read-only**, so it never ends a unit of work and never reaches
either failure -- CP2b is unaffected and needs no change. But any caller
that writes while a grammar is held hits this, and today the only way
through is to supply a UI flexicon does not ship. Recommend filing against
`flexicon` issue #285.

#### Cleanup

`CP2b-ED-Throwaway` still exists, carrying the junk entry `zzed214757`, so
the run can be inspected or reproduced. It is a copy and nothing depends on
it; delete it whenever.

---

### T067 -- full suite (SC-013)

Exact invocation, at the repository root:

```
$ python -m pytest -q
...
2046 passed, 8 skipped, 23 warnings, 36 subtests passed in 390.13s (0:06:30)
```

| | |
|---|---|
| **Passed** | **2046** |
| **Failed** | **0** |
| **Errors** | **0** |
| Skipped | 8 |
| Subtests passed | 36 |
| Warnings | 23 |
| Wall clock | 390.13s (6m 30s) |

**Run WITHOUT `-m "not requires_flex"`, so the live tier ran.** That matters:
`tests/test_parse_live.py` (17 tests) and `tests/test_parser_no_xcore.py`
(4) are marked `requires_flex`, and deselecting them would leave the count
looking healthy while every live claim in this document went unexercised.

The 8 skips are pre-existing and unrelated to this checkpoint (2 in the
flexicon operations tier, 6 elsewhere); none is a CP2b test declining to
run. The 23 warnings are all one pre-existing `DeprecationWarning` about
`ast.Str` in `flexicon_analyzer.py`, unrelated to the parse work.

**What this count is not.** It is the suite on **this machine**, which has
FieldWorks 9.3.10, `pyflexicon` 4.9.0 and both live projects installed. On a
headless machine the same command reports 1977 passed with 71 deselected --
also green, and proving strictly less. The number above is the one that
stands behind the live claims in this document.

**The count above is the FINAL one, and it moved twice.** 2032 after the
implement step; 2036 after the QC gate's findings were closed (four tests
added); 2046 after the three open questions were resolved (ten more -- five
pinning the two capability checks' deliberate divergence, five proving the
resolver's outcomes against a real lexicon). Each number supersedes the last
rather than all three being quoted, because a stale count beside a fresh one
invites the wrong one to be cited.

The final figure was taken on the final tree. An earlier run of it spanned a
whitespace edit, so it was discarded and the suite re-run rather than the
number being kept with a caveat attached.

**A defect the gate's own review brief surfaced.** `aclose_runner()` existed
and **nothing called it**: the server's shutdown path never reaped the parse
worker. A worker is long-lived by design (it holds a loaded grammar) and
holds the project's `.fwdata` lock while it lives, so it would have outlived
the server until its own 600-second idle timeout -- and a worker wedged
inside a grammar load never reaches that timeout at all. That is issue #57's
failure mode with a far longer window than the one-shot children that
preceded CP2b. Fixed in `src/flextoolsmcp/server.py`'s `finally` block, with
two tests: one that `aclose_runner` reaps and is idempotent, and a
structural one that `main()` actually calls it. The QC agent read the file
after the fix had landed and therefore recorded it as already wired; the gap
was real and is recorded here so the fix is not mistaken for something that
was always there.


---

## T068 -- final roll-up

### Every scenario, and whether it ran

| Scenario | Project | Status |
|---|---|---|
| 0 -- the bridge | n/a | RUN (spurt 1) |
| 1 -- a word parses inline against a held grammar | `IndonesianHC-Complete` | **RUN, green** |
| 2 -- the engine gate fires first | `Sena 3` | **RUN, green** -- and `ParserCore` absent from the refusing worker |
| 3 -- plain does not pretend to explain | `IndonesianHC-Complete` | **RUN, green** |
| 4 -- the hypothesis is honoured | `IndonesianHC-Complete` | **RUN, green**, except the `ambiguous` / `no_msa` variants -- see the gap below |
| 5 -- the grace window is reporting | `Malay Parsing-20230810withHC` | **RUN, green** |
| 6 -- interleave, cancel, survival | `Malay Parsing-20230810withHC` | **RUN, green** |
| 7 -- E-D, the one live write | `CP2b-ED-Throwaway` | **RUN, green** (T066, spurt 1) |

### The numbers this checkpoint owes

| Criterion | Measured |
|---|---|
| **SC-004** (inline rate) | **24/24 = 100%**, required >=95%. Median 47ms against a 5s window. Both numbers, T034. |
| **SC-003** (0 UI components after a real parse) | **0** on the parse path -- the delta the parse added is 5 assemblies, none of them UI. T032. |
| **SC-013** (full suite) | **2046 passed, 0 failed**, live tier included. T067. |
| SC-005 (0 parses for an unresolvable piece) | 0, asserted as a negative at both the handler and the live layer |
| SC-006 (traced exactly as given) | six zeros, `tests/test_parse_proposal.py` |
| SC-007 (index built once per run) | 1, counted not timed |
| SC-008 (0 results lost on a kill) | 0, worker killed mid-run live |
| SC-009 (interleave accounted for) | 0 words repeated, grammar loaded exactly once |
| SC-010 (window cancels/slows 0 runs) | 0, watched across two live polls |
| SC-011 (0 rungs naming a nonexistent tool) | 0, registry sweep |

### Pattern audit (T042)

Run. Shape 1 (null-vs-empty at a CLR boundary): **no siblings**. Shape 2
(keyword binding against a divergent double): **four siblings**, with the
divergence located at `server/handlers/execution.py:338`. Two in-scope
findings fixed; three write-path sites recorded for follow-up rather than
changed inside a read-only checkpoint. Full table under T042 above.

### FR-043: HALF discharged

Stated as a half, not rounded up. The **current** half -- currency confirmed
before every reuse, explicit reload as reset-then-update -- is verified live
(T065). The **stale** half -- the automatic reload firing when the model
genuinely changes underneath a held grammar -- is **E-D / quickstart
scenario 7**, which RAN (T066) against a copied project with authorisation.

### T009 and T066

- **T009** (published distribution installs in a clean environment):
  **NOT RUN.** It cannot be run in this session and must not be rounded into
  the equality test's green. Recorded as not run under the Bridge section.
- **T066** (E-D, the one live write): **RUN, and green.** Recorded in full
  under its own heading, including the flexicon `HeadlessLcmUI` finding and
  the recommendation to file it upstream.

### Known gaps, carried forward rather than closed

1. ~~`ambiguous` and `no_msa` are not live-exercisable.~~ **CLOSED.** The
   two quickstart projects genuinely cannot produce them (41 and 281
   entries, zero homographs and zero MSA-less entries between them) -- but
   a read-only scan of the other installed projects found one that can:
   **`Tlachichilco Tepehua-NT Noparse`**, HC-configured, 3704 entries, with
   19 headwords carried by two MSA-bearing entries and 185 carried by a
   single entry with no analysis. `tests/test_parse_live.py` now proves all
   four outcomes distinct against a real lexicon. No write, no
   authorisation required.

   Worth recording from that scan: FLEx sometimes appends a homograph
   number to a headword (that project contains `lati2`, `putauk-atamay2`),
   which would have made `ambiguous` unreachable by construction. It does
   not always -- 19 headwords there are shared verbatim -- so the outcome,
   and the sense filter that resolves it, are both doing real work.
2. ~~FR-041's last sentence is half discharged.~~ **CLOSED.** The note was
   added to `parser_probe.py`, the member lists were pinned by tests, and
   T064's evidence instrument changed from a line count to AST equality.
   See T064.
3. **SPEC 16's no-oracle case remains deferred** -- CP2b ships no review
   surface for it to be about. The deferral's premise is asserted by a test
   (T061). **Still open, and correctly so.**
4. ~~Three write-path keyword-binding sites.~~ **CLOSED on triage.** Two are
   non-defects: the implementation they reach names all four parameters the
   same way. The divergent stand-in that made them look dangerous was dead
   code and has been removed. `worked_examples.py:237` remains a
   documentation nit -- a served template that teaches a keyword-bound
   collection parameter -- not a defect. See T042.
5. **NEW, and the most consequential thing this checkpoint found outside its
   own scope:** the three-tier casting-helper injection was not running,
   while `handle_run_module` logged `Preflight: passed (tier=full)` as
   though it were. The dead implementation and the false telemetry have been
   retired. **Nothing here restores the injection**, and whether it should
   be restored is a CP3 question. See T042, "What the audit found
   underneath".

### Spec corrections made in place

| Document | Correction |
|---|---|
| `specs/parser-check/CP2-SPEC.md` section 3.1 | Tabulated `TryWord` / `TryWordXml` / `TraceWord`, **none of which exists**. Replaced with the shipped six-member surface (T063). |
| `specs/parser-check-cp2b/data-model.md` section 2 | The stage diagram had no `starting -> parsing` edge, so a run reusing a held grammar had to report a grammar load that never happened. Warm path added and documented (T033). |
| `tests/test_parser_no_xcore.py` (recommended, not yet made) | SPEC 16 and CP2-SPEC phrase `HCParser_DoesNotLoadXCore` as an absolute assertion that is **not satisfiable**: opening a FieldWorks project loads `System.Windows.Forms` and `FwUtils` before any parser exists. The shipped test asserts the parse-path delta, which is what SPEC 12.1 actually asks for. **The parent specs should be restated in delta terms.** |

