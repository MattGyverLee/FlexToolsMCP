# SPEC -- flexicon project bridge: `FLExProject.FromOpenProject()`

**Feature:** `flexicon-project-bridge`
**Repo:** `flexicon` (shipped as `pyflexicon`) -- NOT FlexToolsMCP
**Status:** spec, not implemented
**Filed issues:** (none yet)
**Source:** triage of `user-logs/Kendall/session_{112101,145439,154828}*.log`, 2026-09-09
**Blocks:** `portability-preflight`, `flexicon-guidance-correction`,
`vanilla-flextools-parity`, `broken-script-migration`

---

## 1. Context

FlexTools and this MCP hand `Main()` **different project objects**, and nothing
in either stack says so.

- Real FlexTools: `flextoolslib/code/FTModules.py:75` does
  `self.project = FLExProject()` where `FLExProject` is imported
  `from flexlibs` (`FTModules.py:24`). The module receives a **flexlibs**
  project.
- This MCP: `execution.py:3911` imports `FLExProject` from flexicon and
  `execution.py:3939` constructs it. The module receives a **flexicon**
  project.

flexlibs has no flexicon facade at all:

```
grep -rn "AddComplexFormComponent|self\.LexEntry\b|VariantOperations" site-packages/flexlibs/
-> (no matches)
```

So any module using `project.LexEntry.*`, `project.Senses.*`, or
`LexEntryOperations(project)` runs green under the MCP and dies under
FlexTools. Kendall hit exactly this: three sessions of a variant-to-complex-form
module that the MCP reported as `[OK] Operation completed successfully` (5 info,
0 errors) while it failed in his FlexTools install.

**Importing the class does not change the instance you are given.** The
`from flexicon import FLExProject` line in every one of the affected modules is
dead -- and our own guidance told him to write it (see
`flexicon-guidance-correction`).

### Why not a duck-type adapter

Measured across `flexicon/code/`: flexicon operations touch **57 distinct
project attributes over 1011 call sites**. Against a flexlibs donor:

```
satisfied by a flexlibs FLExProject : 15 attrs,  841 sites  (83%)
MISSING on flexlibs                 : 42 attrs,  170 sites
```

The 83% is `self.project.project` (the LcmCache, 406x), `.lp` (182x) and
`.Object` (149x). But 14 of the 42 gaps are whole flexicon-only sub-facades --
`WritingSystems` (46x), `Media`, `Publications`, `MSA`, `PhonFeatures`,
`Senses`, `PossibilityLists`, `LexEntry`, `Texts`, `Wordforms`, `Segments`,
`WfiGlosses`, `POS`, `Person`, `Confidence`. An adapter means reimplementing
those against flexlibs and re-syncing every flexicon release. Wrong shape.

**This gap measurement is the evidence that direct construction --
`LexEntryOperations(flexlibs_project)`, exactly what the broken modules wrote --
cannot work. It is NOT an argument against the bridge below, which makes the
gap irrelevant.** `BaseOperations.__init__(self, project)` sets
`self.project = project` (`BaseOperations.py:617-624`), so `self.project` inside
an operation is the *FLExProject instance* and `self.project.project` is the
cache. Give operations a genuine flexicon `FLExProject` and all 57 attributes
resolve on flexicon own class; only the cache is borrowed.

### Why not rename to `FlexiconProject`

The shared class name is load-bearing. flexicon reaches the flexlibs **private**
method by its mangled name, literally, in 51 places:

```python
# flexicon/code/BaseOperations.py:3610 and 50 others
ws = self.project._FLExProject__WSHandle(...)
# flexlibs/code/FLExProject.py:628: def __WSHandle(self, languageTagOrHandle, defaultWS)
```

Rename the flexicon class and its own instances store
`_FlexiconProject__WSHandle`, breaking all 51 sites -- for no gain. The problem
was never the name: `Main()` receives an instance the module did not create and
cannot choose. A rename makes the confusion more visible while leaving every
script equally broken, and breaks every existing flexicon script. Where code
needs to tell the two apart, use `type(donor).__module__`, not the class name.

---

## 2. Settled -- do not revisit

- **No rename.** `flexicon.FLExProject` keeps its name (51 mangled-name sites).
- **No duck-type adapter** over a flexlibs project (42 attrs / 170 sites,
  14 sub-facades, drifts every release).
- **The bridge lives in flexicon, not the MCP.** The goal is modules that run
  in real FlexTools, and FlexTools imports flexlibs. Only the module itself can
  bridge, so the seam must ship in `pyflexicon`.
- **Never reopen the project.** `FLExLCM.OpenProject` on a project FlexTools
  already holds raises `FP_FileLockedError`. This is the trap any naive "just
  make your own flexicon project" advice walks into.

---

## 3. Design

`OpenProject` (`flexicon/code/FLExProject.py:164`) establishes almost no state:

```python
self.project = FLExLCM.OpenProject(projectName, ui)   # :249  the LcmCache
self.lp      = self.project.LangProject               # :270
self.lexDB   = self.lp.LexDbOA                        # :271
self.writeEnabled = writeEnabled                      # :277
self._undoable    = undoable and writeEnabled         # :278
```

`flexicon.FLExProject` has **no `__init__`** (0 matches in the class body) --
all state is born in `OpenProject`. `__WSHandle` is a method (`:3708`), not
cached state, so there is no cache to copy. A view is therefore five
assignments.

### 3a. The classmethod

```python
@classmethod
def FromOpenProject(cls, donor):
    """Attach a flexicon facade to a project someone else already opened.

    `donor` is whatever the host handed Main(): the FlexTools flexlibs
    FLExProject, or a flexicon one. Returns an object exposing the full
    flexicon facade over the donor cache. Never opens or closes a project.
    """
```

- **Idempotent.** `isinstance(donor, cls)` -> return `donor` unchanged. A
  module written against the bridge must be safe to run under the MCP.
- **Construct via `cls.__new__(cls)`**, not `cls()` -- there is no `__init__`,
  and adding one now would be a breaking change for `OpenProject` callers.
- **Borrow exactly:** `project`, `lp`, `lexDB`, `writeEnabled`. Read `lp` and
  `lexDB` from the donor when present, else derive from the cache
  (`cache.LangProject` / `.LexDbOA`) so a thinner donor still works.
- **Force `_undoable = False`.** flexlibs opens a non-undoable envelope at
  `flexlibs/code/FLExProject.py:262` (`BeginNonUndoableTask()`, when
  write-enabled) and mirrors it at `:275`. The host owns that envelope, so the
  flexicon Phase 2 `UndoableOperation` blocks would nest an undoable UOW
  inside a non-undoable task. Phase 1 `Transaction` is the correct mode.
- **Mark the view:** `self._attached_donor = donor`, so lifecycle methods and
  diagnostics can tell an attached view from an owned one.

### 3b. Lifecycle -- what the view must refuse

`CloseProject` (`FLExProject.py:325`) calls `EndNonUndoableTask`, `usm.Save()`,
then `Dispose()` / `del self.project`. Running that on an attached view saves
and disposes the FlexTools cache out from under it.

- `CloseProject()` on an attached view: **no-op**, log at debug. Do not raise --
  a module that defensively calls it should not fail.
- Anything that ends the host envelope or disposes the cache
  (`Dispose`, `SaveChanges` if it touches Begin/End): refuse with a clear
  `FP_RuntimeError` naming `FromOpenProject`. The host saves; the module must
  not.

### 3c. Fail fast on a donor we cannot use

A donor missing the cache must fail at the bridge with a message naming what is
missing, not with an `AttributeError` fifty frames deep inside an operation.
Validate `project` is present and non-None; derive or validate `lp` / `lexDB`;
require `writeEnabled` to exist (flexlibs sets it). Raise
`FP_ParameterError` listing the absent attributes and the donor
`type(donor).__module__`.

### 3d. The portable module shape

This is what the template and docs must teach, and what the migration catch
must produce:

```python
from flexicon import FLExProject

def Main(project, report, modifyAllowed):
    fx = FLExProject.FromOpenProject(project)   # identical under FlexTools and the MCP
    lex, variants = fx.LexEntry, fx.Variants
```

`FLExProject.LexEntry` is at `:1361`, `Senses` at `:1894`, `Variants` at
`:2140`. Note this finally makes `from flexicon import FLExProject` a
meaningful import rather than the dead line our template has been emitting.

---

## 4. Checkpoints

### CP1 -- the seam

- **T1.1** Add `FromOpenProject` classmethod per 3a, in
  `flexicon/code/FLExProject.py` next to `OpenProject`.
- **T1.2** Guard the lifecycle methods per 3b (`_attached_donor` checks).
- **T1.3** Donor validation and error message per 3c.
- **T1.4** Export nothing new -- `FLExProject` is already exported; the
  classmethod rides along.

### CP2 -- tests that do not need FieldWorks

- **T2.1** A fake donor (plain object carrying a stub `project` with
  `LangProject.LexDbOA`, plus `writeEnabled`) proves: attach borrows the four
  attributes; `_undoable` is False even when the donor is write-enabled;
  `FromOpenProject` on a flexicon instance returns it unchanged (identity).
- **T2.2** `CloseProject()` on an attached view is a no-op and does not touch
  the donor cache; the disposing paths raise.
- **T2.3** A donor missing `project` raises `FP_ParameterError` naming it.

### CP3 -- live verification *(requires FieldWorks + human authorization)*

- **T3.1** Under the MCP, a module using the 3d shape produces results
  identical to the same module using `project.LexEntry` directly.
- **T3.2** **The open question this spec cannot settle by reading:** with FLEx
  holding the project, does a Phase 1 `Transaction` inside the flexlibs
  non-undoable task actually commit on the host save, or does it need an
  explicit `MainCacheAccessor` flush? Run a `SetGloss` through an attached view
  under real FlexTools, close FlexTools, reopen, assert the value persisted.
  **If it does not persist, this spec is wrong that `_undoable = False` alone
  is sufficient, and CP3 must block CP1 from shipping.**
- **T3.3** The variant-to-complex-form module from the Kendall logs, migrated to
  the 3d shape, runs to completion under vanilla FlexTools -- delegated to
  `vanilla-flextools-parity`.

### CP4 -- template pre-flight: flexicon missing or too old *(FlexToolsMCP repo)*

*Added during the tasks step, 2026-09-09, at the user's request.* The 3d shape
finally makes `from flexicon import FLExProject` load-bearing -- which means the
module now depends on the Python environment the user's FlexTools install
actually has. Two environment failures become possible, and neither produces a
readable error on its own:

- `pyflexicon` **not installed** -> `ImportError` at module import time, before
  `Main()` runs. FlexTools shows a load traceback naming a package, with no
  remedy and no indication the module itself is fine.
- `pyflexicon` **installed but predating `FromOpenProject`** -> the module
  imports cleanly and then dies on the first line of `Main()` with
  `AttributeError: type object 'FLExProject' has no attribute
  'FromOpenProject'`.

Both are this feature's own failure class one layer out: the user cannot tell an
environment problem from a bug in their module.

- **T4.1** The flexicon template
  (`src/flextoolsmcp/templates/2-flexicon-template.py`) gains a pre-flight
  block -- a guarded `import flexicon`, a capability probe, and a
  `_flexicon_preflight(report)` helper that `Main()` calls first and returns on
  failure.
- **T4.2** Probe by **capability, not version floor**:
  `hasattr(FLExProject, "FromOpenProject")`. A `hasattr` probe cannot drift and
  needs no constant to bump at each release, whereas a hardcoded floor is a
  second source of truth that will be wrong the first time someone forgets to
  raise it. The installed version is emitted as **diagnostic text only**, read
  from `flexicon.version` (present today; `4.6.0`) with
  `importlib.metadata.version("pyflexicon")` as fallback. Never parse or
  compare version strings.
- **T4.3** Messages are ASCII-only (`CLAUDE.md`), name the remedy
  (`pip install pyflexicon` / `pip install -U pyflexicon`), report the version
  found, and state plainly that the module is correct and the environment is
  not.
- **T4.4** The pre-flight must be **invisible under the MCP**: the runner's own
  environment always has flexicon importable, and once CP1 ships
  `FromOpenProject` is present, so the helper returns `True` and says nothing.
  It must not raise, and must not fire on a bare snippet -- it lives in the
  module template only, where a `report` object is guaranteed.

**Boundary.** CP4 adds the pre-flight and nothing else. The template's
"CRITICAL REQUIREMENT" preamble still claims that explicit flexicon imports
prevent the wrong library version being used -- which SPEC section 1 disproves
(importing the class does not change the instance you are given) -- and it still
teaches Shape B (`LexEntryOperations(project)`). Both are
`flexicon-guidance-correction`'s to fix, not this spec's. The pre-flight is
correct and useful either way: it reports the environment, not the code shape.

---

## 5. Verification

1. **Unit** -- CP2, no FieldWorks required; mark nothing `requires_flex`.
2. **Live** -- CP3, on a scratch project, then on Sena 3.
3. **Regression** -- full flexicon `pytest`; confirm no existing
   `OpenProject`/`CloseProject` test changes behavior.
4. **Cross-repo** -- the FlexToolsMCP suite still passes against the new
   `pyflexicon` before the MCP-side specs land.
5. **Template pre-flight** -- CP4, in the FlexToolsMCP suite: no FieldWorks and
   no flexicon uninstall required; the helper is exercised directly against a
   fake `report` and a monkeypatched probe.

---

## 6. Out of scope

- Renaming either class (settled, section 2).
- Making the 42 missing attributes work on a bare flexlibs project (settled).
- Changing how FlexTools opens projects -- `flextoolslib` is upstream
  (cdfarrow); we do not patch it. If a change there would help, that is an
  upstream issue, filed separately.
- Teaching the MCP to inject through this seam -- that is
  `vanilla-flextools-parity` CP2.
