# CP2a evidence

**The only file CP2a creates in this repository, and CP2b's entry gate.**

This is prose evidence, not a test count, and the distinction is the reason
the file exists. All four of flexicon's structural ratchets are structural,
and **every one of them would have passed a reload bound to a bare update** --
which is the defect cycle 1 actually found. A green suite cannot discharge
the claim that matters most here. A future maintainer asking "how do we know
the reload discards?" must find an answer that is not "there is a test named
that."

| | |
|---|---|
| Checkpoint | CP2a -- the script-library parser surface |
| Implementation repository | `D:\Github\_Projects\_LEX\flexicon`, branch `feat/parser-check-cp2` |
| This repository | `D:\Github\_Projects\_LEX\FlexToolsMCP`, branch `feat/parser-check-cp1` |
| Released version | `4.9.0` (prepared, **not tagged** -- escalation E-C) |
| Component | `ParserCore.dll` 9.3.10, `C:\Program Files\SIL\FieldWorks 9` |
| Date | 2026-09-19 |

Raw transcripts: [`raw/baseline.md`](raw/baseline.md) (T001),
[`raw/tier-a2.md`](raw/tier-a2.md) (T004),
[`raw/tier-a1.md`](raw/tier-a1.md) (T017),
[`raw/tier-a3.md`](raw/tier-a3.md) (T021).

---

## Verdict

**All three tiers ran and passed. Both hard gates are cleared. Tier A4 was
not run, by design.**

| Tier | What it proves | Invocation | Result |
|---|---|---|---|
| **A2** | the members the facade binds exist on the real installed component | `python -m pytest tests/test_parser_reflective.py -m "not requires_live_project" -v` | **11 passed** |
| **A1** | the facade degrades with a reason, exposes no write, binds positionally, and reloads a stale grammar before parsing | `python -m pytest -m "not requires_live_project" -q` | **1923 passed, 0 failed** |
| **A3** | it all actually works against a real grammar | `$env:FLEXLIBS_REQUIRE_LIVE = "1"; python -m pytest tests/operations/test_parser_live.py -m requires_live_project -q` | **18 passed, 0 skipped** |
| **A4** | the stale branch, live | -- | **NOT RUN** -- see below |

Bare `pytest` was never run, and neither was `pytest --ignore=tests/contract`:
both apply no marker filter and would execute `requires_live_project` tests
against real projects.

---

## Tier A2 -- the surface exists (hard gate 1, PASSED)

Run **before any behaviour was written**, against the real installed
`ParserCore.dll`, with FieldWorks present and no project opened. Reflection
only -- `Assembly.LoadFile` plus `GetConstructors`/`GetMethods` -- so no
cache was built, no grammar loaded, no word parsed, and there was nothing to
restore.

`Reset()` and `IsUpToDate()` **both exist, and this was their first
verification anywhere in either repository.** Three findings the facade
depends on:

1. `IsUpToDate()` returns `bool` and takes no arguments, so currency can be
   answered by *asking the parser* rather than from a local flag.
2. `Reset()` returns `void`, not `bool`. It is the discard, not a query --
   so the two-step reload cannot report what it did, and A3.3 had to witness
   the discard some other way.
3. Both are on the `IParser` interface, not only on the concrete class, so
   binding through the interface is safe.

Had `Reset()` been absent, the facade could not have been built as designed
and CP2a would have returned to research rather than binding a reload that
silently short-circuits. It was not absent.

**Directory equality holds on this machine** -- `ParserCore.dll` and
`SIL.LCModel.dll` both resolve from `C:\Program Files\SIL\FieldWorks 9`. The
detected version reads `9.3.10` and is used in no decision.

---

## Tier A1 -- offline behaviour and standing controls

`33 passed` across the two A1 files; `1923 passed, 0 failed` for the whole
offline suite.

### Reconciliation against the T001 baseline

Principle IV requires CP2a-caused failures be separable from inherited ones.
**There were no failures to attribute**, and both counts that moved are fully
accounted for:

| | baseline (T001) | final (T028) | delta |
|---|---|---|---|
| passed | 1878 | 1923 | **+45** |
| deselected | 808 | 826 | **+18** |
| failed | **0** | **0** | 0 |

- **+45 passed** = the three new offline parser files, `test_parser_offline.py`
  (24) + `test_parser_structure.py` (9) + `test_parser_reflective.py` (11) =
  44, plus the one guard added to `tests/contract/test_lcm_contract.py` in
  response to the QC gate.
- **+18 deselected** = `tests/operations/test_parser_live.py`, correctly
  excluded from the offline tier and run under its own invocation.

No test that passed at baseline fails now. **Nothing is being carried as
pre-existing, because nothing failed.**

### What A1 covers

- **A1.1 (SC-001)** -- asking availability never raises. Tested by
  *simulating* absence, never by observing it: the resolution seams are
  repointed at a path that does not exist, at two differing directories, and
  at a function that throws. This machine has a working parser, so none of
  those three states occurs here naturally; a test that merely ran on a
  broken machine would pass for the wrong reason everywhere else.
- **A1.2 / A1.3** -- standing AST ratchets: zero version comparisons in the
  parser package, zero module-scope parser imports anywhere in the package,
  and (positively) at least one function-local one in the facade. Each
  detector carries a self-test that plants a known violation, so "green"
  means "the detector works and found nothing", never "the detector found
  nothing to look at".
- **A1.4 (FR-002)** -- the public surface is asserted by **set equality**
  against a frozen list of six, not by scanning method names for
  write-looking verbs. A name scan passes anything whose author picked a
  gentle verb.
- **A1.5 (FR-005)** -- positional binding asserted structurally. The
  interface names the parameter `word` and the implementation spells it
  `form`, so a keyword call resolves against whichever pythonnet picked and
  fails on someone else's machine.
- **A1.6 (FR-043)** -- **order, not counts**: a stale grammar must reload
  *before* the word is parsed, on every route. A reload that happens after
  the parse satisfies every count and none of the meaning. The counterweight
  is asserted too -- a grammar reported current is **not** reloaded, or the
  facade would pass every order assertion and be useless.

---

## Tier A3 -- live (hard gate 2, PASSED)

Run against `IndonesianHC-Complete` and `Malay Parsing-20230810withHC`, both
opened **in place with `writeEnabled=False`**. Both are HermitCrab projects.
Nothing was written and nothing needed restoring.

**`tests/live_status.json` reported `"run_mode": "live"`, checked before
anything was recorded.** `FLEXLIBS_REQUIRE_LIVE=1` turns silent mock
degradation into a usage error; a mock fallback would have been a FAIL, not
a pass. It did not occur.

### A3.3 -- the discard, and which witness produced the result

**Witness: the morpher-identity read (D-A11). The documented fallback was not
needed and was not used.**

`HCParser.LoadParser()` replaces the private `m_morpher` instance, so the
identity of that instance across two calls is a direct witness of whether a
reload happened. The field was reflected out of the real component first
rather than assumed to exist. Identity is compared by reference
(`RuntimeHelpers.GetHashCode`), because two distinct `Morpher` objects built
from the same model would compare equal under any value-based comparison.

Both halves were observed **under identical conditions, with no model change
between them**:

| Call | Morpher replaced? | Meaning |
|---|---|---|
| bare `Update()` | **no** | short-circuited; nothing discarded |
| `Reload()` (reset, then update) | **yes** | the grammar was discarded |

That is D-A5 verified rather than argued. `HCParser.Update()` is guarded by
`if (m_changeListener.Reset() || m_forceUpdate) LoadParser();`, so with
nothing changed it does nothing -- and a `Reload()` bound to a bare update
would have discarded nothing while reporting success.

**The first row is as important as the second.** It is the control: had the
bare update also reloaded, D-A5's premise would have been wrong and the
two-step binding should have been revisited rather than kept out of habit.

Timing was deliberately **not** used as a witness: it is a correlation, and a
small grammar on a warm cache makes any threshold machine-dependent. Had
*neither* the field read nor the load-errors-file fallback been available,
the test would have **failed**, not skipped -- an absent witness is absent
evidence.

### A3.4, A3.5, A3.6

- **FR-010 object identity** -- a plain-parse analysis carries a live `Form`
  exposing `Hvo`: a real data-model object, not a string rendering.
- **SC-014** -- one handle across repeated parses; an area re-pointed at
  another project's cache releases the old grammar before binding the new one.
- **SC-015** -- the held parser's currency read was wrapped and counted:
  **3 parses by 3 different routes, 3 confirmations.** A cached answer or an
  exempt route would show as a count that does not match.
- **Engine** -- both projects report `ActiveParser == "HC"`. Recorded because
  **this evidence speaks only for HermitCrab**; an XAmple project exercises a
  different component and nothing here transfers to it.

---

## What the live tier caught that nothing else did

This is the part worth reading twice.

**Tier A1 was green. All four structural ratchets were green. The facade was
returning wrong answers.**

An unrestricted trace was passing an **empty** restriction to the component
instead of a **null**. `ParseToXml` branches on `selectTraceMorphs != null`:
a null **reopens** the morpher's entry and rule selectors, an empty array
installs a filter that **admits nothing** -- near-opposites. Worse, the
selectors are set at the start of every such call and **outlive it**, and
plain `ParseWord` never touches them.

Observed on `IndonesianHC-Complete`: a word parsing with one analysis
returned **zero** after any restricted trace, and kept returning zero,
indefinitely, with no exception. A silent wrong answer -- the worst shape a
defect can take.

This was the facade's bug, not the component's, and it is exactly the failure
Principle I names: the *semantics* of an argument were assumed rather than
verified. Tier A2 confirmed `TraceWordXml(string, IEnumerable<int>)` exists;
existence was never the question, and no amount of reflection would have
surfaced it. Only running it against a real grammar did.

Fixed, and pinned by four tests (two live, two offline): `None` now passes
null; an empty sequence is **refused** rather than quietly widened to an
unrestricted search; a real restriction is cleared before the next plain
parse, at a cost of one extra parse paid only when that sequence actually
occurs.

**The lesson for CP2b, stated plainly:** structural tests confirm the shape
of the code, not the meaning of its arguments. CP2b's tools are built on
exactly these two calls.

---

## Pattern audit

Required by Constitution Quality Gate 3 for a shaped bug, and initially
missing from this artifact -- the QC gate blocked on its absence. The
diagnosis above was not a sweep.

**The shape.** *A Python `None`/empty optional collection marshalled across
the pythonnet boundary into a CLR reference parameter, where the callee
branches on `!= null` so the two readings are near-opposites, and the effect
outlives the call.*

**Sweep basis.** Over `flexicon/**/*.py`, excluding `__pycache__`:

| Probe | Hits |
|---|---|
| `System.Array[...]` construction | **1** -- `flexicon/code/Parser/ParserOperations.py:811`, the site itself |
| `System.Collections.Generic.List[...]`, `List[System....]` | 0 |
| `.ToArray()`, `Enumerable.Empty` | 0 |
| literal `None` passed as a CLR call argument (non-docstring) | 12, all inspected |

**Finding: no sibling occurrences. This is the package's only site that
marshals a Python optional collection into a CLR reference parameter.**

The twelve `None`-at-a-CLR-call hits were inspected rather than counted, and
none carries the shape, because none involves a *collection* parameter:

- `FLExProject.py:3848` (`bldr.Replace(..., None)`), `:4539`
  (`SetString(hvo, fid, None)`), `:4548` (`set_String(ws, None)`),
  `ExampleOperations.py:1052`, `EtymologyOperations.py:549` -- null-as-clear
  on a string or a field. The callee's null semantics **are** the intent, and
  there is no empty form to confuse it with.
- `BaseOperations.py:2977` (`PropertyInfo.GetValue(parent, None)`),
  `FLExProject.py:963` (`bound.Invoke(sl, None)`) -- the .NET reflection
  convention for "no index arguments". Fixed by the API, not a choice.
- `FLExProject.py:1046`, `:4351`, `POSOperations.py:1162` -- Python-level
  defaults that never cross the boundary as an ambiguous collection.

**By-construction claim for the future.** The shape needs a CLR parameter
typed as a reference collection whose callee distinguishes null from empty.
Only `TraceWordXml(string, IEnumerable<int>)` in the bound surface qualifies,
and it is now the only such call. Any future binding of a CLR method taking a
collection parameter re-opens this obligation.

**The obligation CP2b inherits.** CP2b's restricted-trace tool sits directly
on this call and will pass caller-supplied decompositions into it. It inherits
both the null-vs-empty contract and the outlives-the-call property.

---

## What was NOT run, and why

**Tier A4 -- the live half of FR-043's stale branch. NOT RUN.**

Making a grammar stale on purpose requires changing the model, which is a
write. CP2a is read-only throughout, so Constitution Principle II defers it
to CP2b with `needs_human` (**escalation E-D, standing and unresolved**).

Precisely what this leaves unproven: A3.3 shows `Reload()` discards
unconditionally, and A1.6 shows the facade reloads *before* parsing when
currency comes back false. What is **not** proven live is the automatic path
firing when the model genuinely changes underneath a held grammar -- that
link is covered only against a stubbed currency read.

**The three read gaps shipped with no tests.** FR-007 (`Texts.GetGenres`),
FR-008 (`Allomorphs.GetOwningEntry`) and FR-009 (`MSA.GetAll`) each had a
single implementation task in `tasks.md` and no test task was scheduled for
any of them. Nothing pins the empty-collection contract, the null-owner
branch, or the MSA wiring, and none was exercised against a live project.
All three were written from verified LCM citations and the offline suite is
green, so this is a Principle III gap -- a promise rather than a control --
not a known defect. It should be closed before CP2b relies on them.

**One unplanned change.** `tests/contract/extract_lcm_contract.py` gained a
`NON_CONTRACT_PREFIXES` exclusion for `SIL.FieldWorks.WordWorks.Parser`. No
task names that file. The facade is the first code in the package to import
from a SIL namespace that is **not a required library**, and the contract
extractor had no concept of an optional one: it classified `HCParser` as an
LCM dependency and the live contract verification then failed to find it
(three real failures). Adding `HCParser` to the baseline would not have
helped -- that baseline is itself checked against the liblcm snapshot -- and
teaching the snapshot generator to load `ParserCore.dll` would have made an
optional component mandatory for the contract suite, the direct opposite of
FR-003. The exclusion is scoped to the parser namespace alone; the four other
`SIL.FieldWorks.*` modules already in the baseline are untouched.

---

## FR-041 / SC-016 -- the shipped capability check is untouched

`src/flextoolsmcp/server/parser_probe.py`: **zero-line working-tree diff, and
zero commits touching it since CP2a began** (first CP2a commit `789bcc4`,
2026-09-18). It last changed on 2026-09-16 in `70a189a`, CP1 Phase 3.

*(A `git diff` against `main` shows +978 lines for this file, but only
because it does not exist on `main` -- CP1 added it on this branch. `main` is
the wrong baseline for FR-041.)*

The two checks **diverge in both directions, deliberately**, and neither
should be reconciled into the other:

| | flexicon's facade | `parser_probe.py` |
|---|---|---|
| ctor, `Update`, `ParseWord`, `ParseWordXml`, `TraceWordXml` | required | required |
| `Reset()`, `IsUpToDate()` | **required** | absent |
| the parse-filing member (the write spine) | **never bound** | required |

Each probes what its own surface binds. The divergence is recorded in both
places, so a later contributor finding them different learns that it was
intended.

---

## The QC gate blocked, and what that changed

The registered `after_implement` code-quality gate returned **BLOCKED** on the
first prepared cut, with three findings. All three were real, all three were
verified independently before being fixed, and the release commit was amended
rather than followed by a patch -- the tag was still unpushed, so the cut was
still the cheap place to fix them.

**B-1 -- the null/empty fix was not exception-safe.** `TraceWordXml` set its
`_restricted` flag *after* the component call. But the component installs its
selectors at the **start** of the call, so a trace that threw part-way through
left the morpher narrowed while the flag stayed false -- the clear would be
skipped and the next plain parse served truncated. That is the original defect
reachable by a second route. The flag is now set **before** the call, which
fails the safe way: the worst case is one wasted clearing parse instead of a
wrong answer. Pinned offline by a test that makes the stub's trace raise.

**B-2 -- no pattern audit.** The artifact diagnosed the shaped bug well and
swept for siblings not at all, which Constitution Quality Gate 3 requires. The
sweep is now above, run and verified independently: `System.Array[...]` is
constructed in exactly one place in the package, and none of the twelve
`None`-at-a-CLR-call sites involves a collection parameter. No siblings.

**B-3 -- the backup witness could not run.** The A3.3 fallback looked for the
HC side file under the project directory and read `ProjectName` as an
attribute when it is a method, so it always returned `None`. A documented
guarantee that could not execute -- precisely the shape this checkpoint spent
its effort avoiding, sitting inside the test that enforces it. It failed
*closed*, so no false pass was produced and the A3.3 result stands. Fixed
(the component writes to its private `m_outputDirectory`, `HCParser.cs:152`)
and, more importantly, **now exercised on every run** by its own test, so a
dead fallback fails loudly instead of waiting for the day the primary witness
breaks.

Three non-blocking findings were also taken:

- the class docstring claimed "read-only by construction" without stating its
  limit; the inherited `Swap` / `MoveBefore` / `MoveAfter` /
  `ApplySyncableProperties` generics are reachable and do write, though none
  can record a parse result. The limit is now stated in both the class
  docstring and the `FLExProject.Parser` property, not only in a test;
- `_restricted` was not cleared on reload or project switch, so the flag
  approximated component state rather than tracking it -- which is what made
  B-1 easy to miss. Now cleared in both places;
- `NON_CONTRACT_PREFIXES` was a silent exclusion list with no guard. A test
  now pins it to the one reviewed entry, so widening it means editing a test
  rather than appending a line nobody sees.

One finding is recorded and **not** fixed, because it is out of scope:
`BaseOperations.Swap` calls `_TransactionCM` but never `_EnsureWriteEnabled`,
unlike its five siblings -- an unguarded writer on all 43 Operations classes.
Pre-existing, unrelated to CP2a, and it needs its own issue.

Counts after the fixes: offline **1923 passed, 0 failed**; live **18 passed,
0 skipped**, `run_mode: live`.

---

## Handoff state

Recorded so the next session inherits the position rather than reconstructing
it.

### What landed

The flexicon release commit is **prepared and pushed, not tagged**:

```
1b6f5533  chore(release): cut 4.9.0 -- the parser becomes reachable, read-only
          branch feat/parser-check-cp2, pushed to origin
          21 files changed, 2774 insertions(+), 12 deletions(-)
```

All 31 CP2a tasks are complete. All four release ratchets are green.

### Escalations standing and UNRESOLVED

**E-C -- the `v4.9.0` tag push and `gh release create`.** Deliberately not
performed. Both publish to PyPI and are irreversible, which makes them
maintainer acts. The prepared release commit was the last reversible moment
for anything in `contracts/parser-operations.md`; **that moment has now
passed for the commit, but not for the tag.** Until the tag exists the
surface can still be changed by amending the cut.

**E-D -- tier A4, the live half of FR-043's stale branch.** Not run.
Exercising it requires writing to a project to make a grammar stale on
purpose, which CP2a's read-only scope forbids. Deferred to CP2b with
`needs_human`.

### CP2a-bridge -- NOT STARTED

Three items remain in **this** repository before CP2b's first parser task.
None was begun:

1. the `pyflexicon>=4.9.0,<5` floor;
2. refreshed bundled index artifacts;
3. the floor/index-equality test asserting the declared minimum and the
   bundled index agree.

Note the ordering that CP2 already settled (Decision D4): the seam CP2b
depends on is *proven*, not *released*. The evidence gate and the tag are on
separate timelines, which is why FR-011 was amended in cycle 3. CP2b's entry
gate is this artifact, not the tag.

### CP2b -- NOT STARTED

FR-012 through FR-040 are untouched: `flextools_try_word`,
`flextools_parse_status`, the run record, stages, the priority queue,
cancellation, the three new refusal codes, and the
`HCParser_DoesNotLoadXCore` / SC-003 standing test.

**Three things CP2a learned that CP2b should not rediscover:**

1. **An empty restriction is not "no restriction."** The component reads
   null and empty as near-opposites, and the setting outlives the call.
   CP2b's restricted-trace tool sits directly on this call.
2. **Structural tests confirm the shape of the code, not the meaning of its
   arguments.** A green offline suite and four green ratchets coexisted with
   a silent wrong answer for the entire checkpoint.
3. **A CAPABILITIES token is not a runtime probe.** `"parser"` says the build
   ships the surface. CP2b must call `GetAvailability()` and must not infer
   reachability from the token.

### Debt CP2a is handing on

- **The three read gaps have no tests** (FR-007, FR-008, FR-009). `tasks.md`
  scheduled an implementation task for each and a test task for none. Close
  this before CP2b relies on them.
- **`_FILE_PATH_DOMAIN_HINTS`** in `tests/flex_plugin.py` has no `parser`
  entry, so parser tests without a `live_phase` marker resolve to `Unknown`
  in the dashboard. The live tier carries the marker, so this is cosmetic
  today; a one-line hint would close it.
- **`CHANGELOG.md`'s tail is stale** -- a "Future Roadmap" section still
  planning v2.4.0/v3.0.0 and a support table calling v2.3.x current, at
  4.9.0. Pre-existing, out of CP2a's scope, and contradicting the top of its
  own file.
- **This repository is on branch `feat/parser-check-cp1`**, not a cp2 branch.
  All CP2 spec work to date is already committed there and the only CP2a
  deliverable here is this artifact, so continuing was consistent rather than
  a new deviation -- but the CP2 handoff `branch_note` asked for
  `feat/parser-check-cp2` to be cut before the first CP2a implementation
  task. It was cut in flexicon, where every other CP2a task landed, and not
  here. A maintainer should decide before the tag.
