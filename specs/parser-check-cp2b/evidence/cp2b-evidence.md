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

_Not yet run._ This session cannot perform it: `pyflexicon 4.9.0` is
published but is **not installed in this environment** and will not be within
this session -- `flexicon` resolves to the working tree at 4.9.0 while pip
metadata reads 4.8.0 (escalation E-C, research.md R-01).

**It must never be rounded into T005's green.** T005 proves the declared
floor, the resolved version and the bundled artifacts agree *in this tree*.
It does not prove the published distribution installs anywhere.

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

## US2 -- flextools_try_word

### T034 -- SC-004 as a measured rate

_Not yet run._ Required: attempt count AND observed inline rate (>=95%).
One fast call does not discharge this criterion.

---

## US3 -- the morph resolver

### T042 -- pattern audit (CLR collection-parameter binding)

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

### T062 -- Decision D5, grammar-lint deferral

_Not yet recorded._

### T064 -- FR-041, parser_probe.py unchanged

_Not yet run._

### T065 -- FR-042 / FR-043 current half

_Not yet run._

### T066 -- E-D, THE ONE LIVE WRITE

_Not yet run._ **Requires a present human's authorisation and a backed-up or
copied project.** An unattended run must not perform it and must report
status `needs_human`.

If it is not run, what stays unproven is: the automatic reload path firing
when the model genuinely changes underneath a held grammar. **FR-043 and
SC-015 must not be shown green without it.**

### T067 -- full suite

_Not yet run._
