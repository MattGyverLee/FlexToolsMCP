# CONTRACT -- `FLExProject.FromOpenProject()`

Public surface added by this feature. Every identifier below is pinned by `spec.md` and is
copied verbatim: **`FromOpenProject`**, **`_attached_donor`**, **`_undoable`**,
**`project`**, **`lp`**, **`lexDB`**, **`writeEnabled`**, **`FP_ParameterError`**,
**`FP_RuntimeError`**. Do not rename, recase, or pluralize any of them.

**Module:** `flexicon.code.FLExProject`
**Exported as:** `flexicon.FLExProject` -- already exported (`flexicon/__init__.py:90-93`);
this feature adds **no new export** (SPEC T1.4).

---

## 1. Signature

```python
@classmethod
def FromOpenProject(cls, donor): ...
```

Stub to add to `flexicon/code/FLExProject.pyi` (beside the `OpenProject` stub at :186):

```python
@classmethod
def FromOpenProject(cls, donor: Any) -> "FLExProject": ...
```

| Parameter | Meaning |
|---|---|
| `donor` | Whatever the host handed `Main()`: the FlexTools flexlibs `FLExProject`, or a flexicon one. Duck-typed; never `isinstance`-checked against flexlibs. |

**Returns:** an object exposing the full flexicon facade over the donor's cache.
**Never** opens a project. **Never** closes one.

---

## 2. Behaviour

### 2.1 Idempotence

```python
FLExProject.FromOpenProject(x) is x        # True when isinstance(x, FLExProject)
```

Checked **first**, before validation. Returns the donor object itself -- not a copy, not a
wrapper. Its `_undoable` mode and its cached `_<facade>_ops` are left untouched, and
`_attached_donor` is **not** set on it (it still owns its project).

### 2.2 Attach

For any other donor, in this order:

1. Validate (section 3). On failure raise before mutating anything.
2. Allocate with `cls.__new__(cls)` -- **not** `cls()`. No `__init__` is added to the class.
3. Assign exactly:

   | Attribute | Value |
   |---|---|
   | `project` | `donor.project` |
   | `lp` | `donor.lp` if present and non-`None`, else `donor.project.LangProject` |
   | `lexDB` | `donor.lexDB` if present and non-`None`, else `lp.LexDbOA` |
   | `writeEnabled` | `donor.writeEnabled`, verbatim (including `False`) |
   | `_undoable` | `False`, unconditionally |
   | `_attached_donor` | `donor` |

4. Return the view.

No other attribute is set, and the donor is never mutated.

### 2.3 Post-conditions

```python
view = FLExProject.FromOpenProject(donor)

view.project        is donor.project      # the borrowed LcmCache
view.writeEnabled   ==  donor.writeEnabled
view._undoable      is  False             # even when donor.writeEnabled is True
view._attached_donor is donor
isinstance(view, FLExProject)             # True -- full facade
view.LexEntry, view.Senses, view.Variants # resolve (FLExProject.py:1361/1894/2140)
```

---

## 3. Donor validation

Raise **`FP_ParameterError`** (`flexicon/code/exceptions.py:82`, subclass of
`FP_RuntimeError`) when a required attribute is absent or `None`.

| Attribute | Rule |
|---|---|
| `project` | must exist and be non-`None` |
| `writeEnabled` | must exist |
| `lp` | optional -- derived from `project.LangProject` when absent |
| `lexDB` | optional -- derived from `lp.LexDbOA` when absent |

The message lists **every** missing attribute (not just the first) and the donor's
`type(donor).__module__`. `__module__` is the discriminator because both candidate classes
are named `FLExProject`.

Required message content -- assert on substrings, not on exact prose:

- the literal string `FromOpenProject`
- each missing attribute name, spelled exactly (`project`, `writeEnabled`)
- the value of `type(donor).__module__`

ASCII only (`CLAUDE.md`).

---

## 4. Lifecycle refusals on an attached view

All branch on `hasattr(self, "_attached_donor")` -- never on `writeEnabled` or `_undoable`.

| Call | Behaviour on an attached view | Rationale |
|---|---|---|
| `CloseProject()` | **No-op.** Returns `None`, logs at `debug`. Does not raise. Must not reach `EndNonUndoableTask`, `usm.Save()`, `Dispose()`, or `del self.project`. | SPEC 3b -- a module that defensively closes must not fail, and the host's cache must survive. |
| `SaveChanges()` | Raise **`FP_RuntimeError`** naming `FromOpenProject`. Checked **before** the existing issue-#243 depth guard (`FLExProject.py:798`) and before the `writeEnabled` check, so the module hears "the host owns the save" rather than a depth or read-only message. The message says the host saves and the module should return; it must **not** advise `CloseProject()` -- on a view that is a no-op, so the advice would produce a green run that writes nothing. | R3, R7 |
| Any disposing path (`Dispose`, and any save path that touches `Begin`/`End`) | Raise **`FP_RuntimeError`** naming `FromOpenProject`. | SPEC 3b |
| `UndoableOperation(...)` | Raise `FP_TransactionError` (unchanged type) with **attached-view wording**: names `FromOpenProject`, states the host owns a non-undoable envelope, points at `Transaction()`. Must not say "opened with undoable=False" -- nobody called `OpenProject`. | R2, `undoable_operation.py:92-99` |
| `Transaction(...)` | **Permitted.** Phase 1 labelling semantics, as for any `_undoable=False` project. | SPEC 3a |
| Reads (`LexEntry.GetAll()`, `WSHandle`, ...) | **Unrestricted.** | -- |

---

## 5. The portable module shape (SPEC 3d)

This exact shape is what the docs and the migration catch must produce. It is identical
under real FlexTools and under this MCP.

```python
from flexicon import FLExProject

def Main(project, report, modifyAllowed):
    fx = FLExProject.FromOpenProject(project)
    lex, variants = fx.LexEntry, fx.Variants
```

Under FlexTools, `project` is a flexlibs instance and `fx` is a new view. Under the MCP,
`project` is already a flexicon instance and `fx is project`. Either way the facade is
present -- which is what finally makes `from flexicon import FLExProject` a load-bearing
import rather than the dead line the template has been emitting.

---

## 6. Test-facing contract (CP2, no FieldWorks)

New file: `tests/test_from_open_project.py` in the `flexicon` repo. **No**
`requires_live_project` marker -- the bridge opens nothing.

Fake donor shape:

```python
class _FakeDonor:
    def __init__(self, write_enabled=True):
        self.project = _FakeCache()      # .LangProject.LexDbOA, .MainCacheAccessor,
                                         # .ActionHandlerAccessor.CurrentDepth
        self.writeEnabled = write_enabled
```

| Test | Asserts |
|---|---|
| T2.1a | the four attributes are borrowed; `view.project is donor.project` |
| T2.1b | `view._undoable is False` even with `donor.writeEnabled is True` |
| T2.1c | `FromOpenProject(flexicon_instance) is flexicon_instance` (identity) |
| T2.2a | `CloseProject()` on a view returns without raising and leaves the donor cache un-disposed, un-saved, with no `EndNonUndoableTask` call |
| T2.2b | `SaveChanges()` on a view raises `FP_RuntimeError`; the message contains `FromOpenProject` and does **not** contain `CloseProject` (R7) |
| T2.2c | `UndoableOperation()` on a view raises `FP_TransactionError` whose message contains `FromOpenProject` and does **not** contain `opened with undoable=False` |
| T2.3 | a donor missing `project` raises `FP_ParameterError` whose message contains `project`, `FromOpenProject`, and the donor's `__module__` |

---

## 7. Unresolved -- gates the ship

**T3.2.** With FLEx holding the project, does a Phase 1 `Transaction` inside the flexlibs
non-undoable task actually commit on the host's save, or does it need an explicit
`MainCacheAccessor` flush? This contract asserts nothing about it. If a `SetGloss` through an
attached view does not survive close-and-reopen under real FlexTools, then `_undoable = False`
alone is insufficient and **CP1 must not ship** -- section 2.2 would need a flush step and this
contract would change.

---

## 8. Template pre-flight (CP4, FlexToolsMCP repo)

Added in the tasks step. Lives in
`FlexToolsMCP/src/flextoolsmcp/templates/2-flexicon-template.py` -- the emitted
module carries it, so it runs in the user's FlexTools environment, not ours.

### 8.1 Shape

```python
_FLEXICON_IMPORT_ERROR = None
try:
    import flexicon as _flexicon
    from flexicon import FLExProject
except ImportError as _e:                 # pyflexicon absent
    _flexicon = None
    FLExProject = None
    _FLEXICON_IMPORT_ERROR = str(_e)


def _flexicon_installed_version():
    """Best-effort version string for diagnostics only. Never raises."""
    ...


def _flexicon_preflight(report):
    """True when flexicon is usable; else report.Error(...) and False."""
    ...
```

`Main()` calls it first:

```python
def Main(project, report, modifyAllowed):
    if not _flexicon_preflight(report):
        return
    fx = FLExProject.FromOpenProject(project)
```

### 8.2 The two failures and their probes

| Failure | Probe | Report |
|---|---|---|
| `pyflexicon` not installed | `_flexicon is None` | `report.Error(...)` naming `pip install pyflexicon`, quoting the captured `ImportError` text |
| `pyflexicon` too old (no bridge) | `not hasattr(FLExProject, "FromOpenProject")` | `report.Error(...)` naming `pip install -U pyflexicon` and the version found |

**Capability, not version floor.** The staleness probe is `hasattr`, never a
version comparison. A hardcoded floor is a second source of truth that goes
wrong the first time a release forgets to raise it; `hasattr` asks the only
question that matters -- is the bridge there. Version strings are read for the
message only, via `getattr(_flexicon, "version", None)` first (present today:
`4.6.0`) then `importlib.metadata.version("pyflexicon")`, each guarded, both
falling back to `"unknown"`.

### 8.2b The version note *(added 2026-09-09, at the user's request)*

A third case sits between "works" and "too old": a flexicon that **has** the
bridge but predates the one the module was generated against. That is a
supported configuration, so it is a `report.Warning`, never a refusal.

| Element | Contract |
|---|---|
| `_TESTED_AGAINST` | Module-level constant, ships as `"unknown"` in the template file, **stamped by `flextools_get_module_template()`** with the flexicon version detected at generation time |
| Comparison | `_version_parts()` -> tuple of ints; returns `None` for anything not plain dotted digits. `_flexicon_is_behind()` answers `False` whenever either side is `None` |
| Effect | Adds warning lines only. **Cannot change the return value.** Runs after the `hasattr` gate has already passed |
| Silence | Equal, newer, or unparseable on either side -> no output at all |

**Why this does not contradict 8.2.** 8.2 forbids a version comparison from
*gating* -- deciding whether the module runs. This one cannot: a wrong
comparison costs a spurious note, never a working module. The distinction is
the whole point, and it is now pinned behaviourally rather than by grepping
(see 8.4).

**Why the constant is stamped, not hand-written.** A hand-maintained version in
a template is precisely the rot this feature already found: the template's own
`REQUIRES: - Flexicon version 2.0+` line was prose, unenforced, and false by
the time anyone read it. Stamping at generation time means the recorded value
is observed, not remembered. A hand-copied template file keeps `"unknown"` and
simply emits no note.

### 8.3 Guarantees

- **Never raises.** Every path returns `True` or `False`; a probe that itself
  throws is treated as "cannot determine" and returns `True` (fail open -- the
  pre-flight must never be the reason a working module stops running).
- **Silent on success.** No `report.Info` on the happy path. Under the MCP,
  and on any machine with a current `pyflexicon`, the block says nothing.
- **ASCII only** (`CLAUDE.md`), with `[ERROR]` prefixes matching the template's
  existing message style.
- **Module template only.** Bare snippets are not touched -- they have no
  `Main()` and their `report` contract is the runner's.

### 8.4 Test-facing contract (CP4)

New file: `FlexToolsMCP/tests/test_template_flexicon_preflight.py`. No
FieldWorks, no flexicon uninstall; the template is loaded as source and the
probes are monkeypatched.

| Test | Asserts |
|---|---|
| T4.1a | the emitted template (via `flextools_get_module_template(flavor='flexicon')`) contains `_flexicon_preflight` and calls it as the first statement of `Main()` |
| T4.2a | with `_flexicon = None`, the helper returns `False` and the message contains `pip install pyflexicon` and the captured `ImportError` text |
| T4.2b | with flexicon present but `FromOpenProject` absent, the helper returns `False` and the message contains `pip install -U pyflexicon` and the version found |
| T4.2c | **superseded 2026-09-09.** Originally: the template source contains no version-string comparison at all. That ban was broader than 8.2 requires and would have blocked the advisory note in 8.2b, so it is replaced by two checks -- (i) no third-party version machinery (`packaging`, `pkg_resources`, `LooseVersion`, `StrictVersion`, `parse_version`), and (ii) a **behavioural** ratchet: with `_TESTED_AGAINST` set absurdly high, a capable flexicon at `0.0.1` / `1.0.0` / `2.0.0` / `4.0.0` still returns `True` and emits no `Error`. Behaviour is the property worth pinning; source-grepping only approximated it |
| T4.2d | older-than-tested warns, names **both** versions and the `-U` remedy, and the emitted calls are `Warning` only -- not `Error` (reads as failure) and not `Info` (invisible in a long run) |
| T4.2e | equal / newer is silent. Includes `4.10.0` vs `4.7.0` on purpose: a string comparison ranks it below, a tuple comparison does not |
| T4.2f | unparseable on either side (`"unknown"`, `4.7.0.dev1`, `4.7.0+g1234abc`) produces no note rather than a wrong one |
| T4.2g | the template **file** still ships `_TESTED_AGAINST = "unknown"`, while the **emitted** template carries a real stamped version |
| T4.3a | every character the pre-flight can emit is ASCII (`text.encode("ascii")` does not raise) |
| T4.4a | with flexicon present and `FromOpenProject` present, the helper returns `True` and calls no `report` method at all |
| T4.4b | a probe that raises returns `True` (fail open) and does not propagate |
