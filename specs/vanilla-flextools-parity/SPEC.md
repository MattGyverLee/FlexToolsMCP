# SPEC -- vanilla FlexTools parity: run modules through the real host

**Feature:** `vanilla-flextools-parity`
**Repo:** FlexToolsMCP
**Status:** spec, not implemented
**Filed issues:** (none yet)
**Source:** triage of `user-logs/Kendall/session_{112101,145439,154828}*.log`, 2026-09-09
**Depends on:** `flexicon-project-bridge` (the fix under test),
`portability-preflight` (this spec is the empirical check on that gate)

---

## 1. Context

The MCP blessed four distinct broken modules across three sessions with
`[OK] Operation completed successfully`, because it runs them against a
**flexicon** project (`execution.py:3911,3939`) while FlexTools runs them
against a **flexlibs** one (`flextoolslib/code/FTModules.py:75,24`). Nothing in
our test suite exercises the FlexTools path, so the divergence was invisible to
us and expensive for the user.

`portability-preflight` adds a *static* gate. This spec adds the *empirical*
one: actually run the module through real `flextoolslib` and compare.

### The harness already exists upstream

`flextoolslib/misc/RunModule.py` is a headless FlexTools module runner (the
frame behind `FlexTools\scripts\TestAModule.py`):

```python
from flexlibs import FLExInitialize, FLExCleanup
from flexlibs import FLExProject, FP_ProjectError, FP_FileNotFoundError
from ..code.FTModuleClass import FTM_ModuleError
from ..code.FTReport import FTReporter
...
    ftm = mod.FlexToolsModule            # requires the real binding
    FlexDB = FLExProject()               # :89  the flexlibs project
    FlexDB.OpenProject(projectName = project)
    reporter = FTReporter()
    ftm.Run(FlexDB, reporter)            # goes through FTModuleClass.Run
    ...
    FlexDB.CloseProject()
```

This is ground truth in every respect that matters: the real flexlibs project,
the real `FTModuleClass.Run` including its `FTM_ModifiesDB` clamp
(`FTModuleClass.py:106-112`), the real `FTReporter`, the real
`FLExInitialize`/`FLExCleanup` lifecycle.

**Two limits to design around.** `OpenProject(projectName = project)` passes no
`writeEnabled`, and `ftm.Run(FlexDB, reporter)` lets `modifyAllowed` default to
False. So upstream `RunModule` is **read-only only**. Write parity needs our own
runner that mirrors it -- see 3b.

---

## 2. Settled -- do not revisit

- **Do not patch `flextoolslib` or `flexlibs`.** Both are upstream (cdfarrow).
  We import them and, where we need behaviour they do not expose, we write our
  own runner that *mirrors* theirs with the difference documented.
- **Prefer upstream `RunModule` wherever it suffices.** For read-only parity it
  is exactly right, and using it means we are testing their code path, not our
  imitation of it.
- **Parity tests require FieldWorks.** They are `requires_flex` and never gate
  a headless CI run. The static gate in `portability-preflight` is what runs
  everywhere.
- **Read-only parity is the default.** Write parity runs only against a scratch
  project, never Sena 3 or a user project.

---

## 3. Design

### 3a. Read-only parity via upstream

`tests/parity/run_vanilla.py`: write the module under test to a temp `.py`
file, call `flextoolslib.misc.RunModule.RunModule(path, project)`, capture the
`FTReporter` messages and any exception.

`FTReporter.messages` yields `(msgType, msg, ref)` **tuples** (per the
`TYPE_LOOKUP` loop in `RunModule.py`), while our `SimpleReporter`
(`execution.py:3766+`) collects `{"type", "message", "ref"}` **dicts** with
`TYPE_NAMES = ["INFO","WARNING","ERROR","BLANK"]`. The comparator must
normalise both to a common shape before diffing.

### 3b. Write parity via a mirrored runner

`tests/parity/run_vanilla_write.py` -- a deliberate, documented copy of
upstream `__RunModule` differing in exactly two lines:

```python
FlexDB.OpenProject(projectName = project, writeEnabled = True)
ftm.Run(FlexDB, reporter, modifyAllowed = True)
```

Header comment must name the upstream file, the version it was copied from, and
the two deltas, so drift is detectable. Add a test that asserts the upstream
function still has the shape we copied (signature check), failing loudly when
`flextoolslib` changes.

Note `ftm.Run` still applies the `FTM_ModifiesDB` clamp, which is the point:
write parity also exercises `modifiesdb-parity`.

### 3c. The comparator

`compare_runs(mcp_result, vanilla_result) -> ParityVerdict` over:

- outcome class: `ok` / `error` / `exception` (type name, not message text)
- message sequence, normalised per 3a; compare **structure and count** first,
  then text
- for write runs: a pre/post project-state diff on the touched objects

Verdict is one of `match`, `mcp_only_success` (**the Kendall failure -- passes
here, fails there; the single most important thing this harness detects**),
`vanilla_only_success`, `both_fail_same`, `both_fail_differently`.

### 3d. The corpus

Seed from the logs. The corpus is **already extracted and checked in** at
`specs/vanilla-flextools-parity/evidence/corpus/`, with `MANIFEST.json` and
`regenerate.py`. Every file reproduces its logged `sha256` prefix and byte
count exactly (verified 10/10), so these are the bytes the MCP actually ran,
not a paraphrase.

`python .../corpus/regenerate.py --check` re-verifies against
`user-logs/Kendall/`; without `--check` it rebuilds.

**Trailing whitespace is significant** -- two of the modules contain it, and it
is part of what the log hashed. A formatter in this environment stripped it
from `*.py` twice during this work, breaking those two fingerprints both
times. Hence the files are stored as **`<fingerprint>.py.txt`**, an inert
extension the formatter leaves alone; the harness writes each to a temp `.py`
before running it (3a), so nothing needs them importable in place. The
directory also carries `.gitattributes` with `*.py.txt -text -diff`.

Put `regenerate.py --check` in CI. Without it, a reformat silently invalidates
the evidence and the parity suite starts testing something other than what the
MCP actually ran.

Ten distinct modules. Seven are loadable by `RunModule`, which requires a
`mod.FlexToolsModule` binding:

| fingerprint | source | notes |
|---|---|---|
| `b9f01db03221` | 112101 op1 | doubleref |
| `b6257c1de3e1` | 112101 op2 | doubleref+types; our casting gate refused it |
| `98abf566dc9c` | 112101 op3/4 | doubleref+types, accepted |
| `527d148f3617` | 145439 op1-3 | variant convert; `ModifiesDB: False` yet wrote -- also the `modifiesdb-parity` fixture |
| `0ce1eadb7869` | 154828 op1-3 | variant convert; wrote with no confirmation in the trail -- also the `write-authorization-audit` fixture |
| `e7040da6ad7b` | 154828 op4 | cast-free variant; the false-pass run |
| `eadf9869c01b` | 154828 op7 | `cast_to_concrete` variant |

Expected verdict pre-fix for all seven: `mcp_only_success`.
Post-`flexicon-project-bridge`, the migrated form of each must flip to `match`.
That transition is the acceptance criterion for the bridge.

Three are **not** parity candidates and are kept as evidence only:
`70e77d29b9d3` (145439 op4) and `7a16bca3a156` (154828 op5) are partial modules
with a `Main` but no `docs`/`FlexToolsModule` binding, so `RunModule` cannot
load them; `0c64798c1c25` (154828 op6) is a `bare_snippet`, excluded by section
2. Note `7a16bca3a156` was already refused here by
`partial_module_structure` -- our existing gate, working correctly.

### 3e. Fixture project

Parity runs need a disposable project with known variant and complex-form
structure -- the Kendall corpus is all variant/complex-form work, and op#4 in
session 154828 produced a **false pass precisely because the data it needed had
been deleted** by the previous op. So the fixture must be restored to a known
state before every write-parity run, from a checked-in seed rather than a
backup of whatever state the last run left.

Reuse the backup/restore path from `write-authorization-audit` 3d if it lands
first; otherwise a plain file copy of the seed `.fwdata`.

---

## 4. Checkpoints

### CP1 -- read-only harness

- **T1.1** `tests/parity/run_vanilla.py` per 3a.
- **T1.2** `tests/parity/compare.py` per 3c, with the reporter normalisation.
- **T1.3** Corpus + sidecars per 3d.
- **T1.4** `pytest -m parity` marker, `requires_flex`, skipped by default.

### CP2 -- MCP side of the comparison

- **T2.1** A programmatic entry to run a module through the MCP path without
  going through the MCP protocol, so the two runs are directly comparable.
- **T2.2** Have the MCP inject the project through the
  `flexicon-project-bridge` seam (`FromOpenProject`) rather than constructing
  flexicon directly at `execution.py:3939`, so MCP runs exercise the same code
  path modules will use. Without this, parity tests validate a path production
  does not take.

### CP3 -- write parity

- **T3.1** `tests/parity/run_vanilla_write.py` per 3b, plus the upstream
  signature-drift test.
- **T3.2** Fixture seed and restore-before-run per 3e.
- **T3.3** Pre/post state diff in the comparator.

### CP4 -- keep it honest

- **T4.1** Run the corpus in the pre-fix tree and record the verdicts as the
  baseline. Every entry should read `mcp_only_success`. **If any reads `match`
  before the bridge lands, the harness is not actually reaching the vanilla
  path and CP1 is wrong.**
- **T4.2** Cross-check against `portability-preflight`: every corpus entry the
  static gate refuses should be `mcp_only_success` here, and vice versa. A
  disagreement is a bug in one of the two, and the parity result wins.

---

## 5. Verification

1. **Baseline** -- CP4/T4.1, before any fix. This is the test that proves the
   harness works.
2. **Post-fix** -- migrated corpus flips to `match`.
3. **Drift** -- the upstream signature test fails when `flextoolslib` changes
   shape under us.
4. **Headless** -- with FieldWorks absent, the whole parity suite skips
   cleanly; `pytest` stays green.
5. **Regression** -- full `pytest`, `validate_integrity.py all`,
   `verify_python.py`.

---

## 6. Out of scope

- Driving the FlexTools **GUI**. `RunModule` is the headless frame and is
  sufficient; UI automation is not.
- Testing IronPython. Modules claim `Platforms: Python .NET and IronPython`,
  but we have no IronPython runtime here; note the untested claim and move on.
- Parity for `bare_snippet` runs -- they have no `FlexToolsModule` binding, so
  `RunModule` cannot load them and they are not destined for FlexTools anyway.
