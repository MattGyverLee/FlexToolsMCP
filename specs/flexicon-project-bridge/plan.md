# PLAN -- flexicon project bridge: `FLExProject.FromOpenProject()`

**Feature:** `flexicon-project-bridge`
**Spec:** [`spec.md`](./spec.md)
**Implementation repo:** `flexicon` (`D:/Github/_Projects/_LEX/flexicon`, shipped as `pyflexicon`)
**This repo (`FlexToolsMCP`):** holds the spec, the cross-repo regression gate, and
(as of CP4, added in the tasks step) the flexicon pre-flight block in the module template.
**Size:** normal (no `size` recorded; full plan)

---

## Summary

FlexTools hands `Main()` a **flexlibs** `FLExProject`; this MCP hands it a **flexicon**
one, and a module written against the flexicon facade (`project.LexEntry`,
`project.Senses`, `LexEntryOperations(project)`) therefore runs green under the MCP
and dies under real FlexTools. The fix is a single seam in flexicon: a
`FromOpenProject(donor)` classmethod that builds a flexicon `FLExProject` **view**
over a cache someone else already opened, borrowing four attributes and never
opening, saving, or disposing anything. Because `flexicon.FLExProject` has no
`__init__` and every facade property lazily constructs its operations object from
`self`, the view is five assignments plus lifecycle guards -- no adapter, no rename,
no reopen.

The work is Python-only inside the existing `flexicon` package: one classmethod and
its type stub, guards on the three lifecycle methods that end the host's envelope or
dispose its cache, a donor-validation error path, and unit tests that need no
FieldWorks. The one thing this plan **cannot** settle by reading is whether a write
made through an attached view actually reaches disk on the host's save (SPEC T3.2);
that is a live gate, and it blocks CP1 from shipping.

---

## Project Structure

Source changes land in the `flexicon` repo. Paths below are relative to that repo root.

```
flexicon/
  flexicon/
    code/
      FLExProject.py          # + FromOpenProject classmethod (next to OpenProject:164)
                              # + attached-view guards in CloseProject (:325) and
                              #   SaveChanges (:798)
      FLExProject.pyi         # + FromOpenProject stub (OpenProject stub is at :186)
                              # NB: that stub is itself stale -- it omits the runtime
                              # `undoable` parameter. Pre-existing; NOT fixed here.
      undoable_operation.py   # attached-view-aware message on the _undoable refusal (:92-99)
      exceptions.py           # unchanged -- FP_ParameterError (:82) / FP_RuntimeError (:53) reused
    __init__.py               # unchanged -- FLExProject already exported (:90-93)
  tests/
    test_from_open_project.py # NEW -- CP2 unit tests, no FieldWorks, no requires_live_project
  docs/
    TRANSACTION_GUIDE.md      # attached views are Phase 1; UndoableOperation is refused
    MIGRATION_GUIDE.md        # the portable module shape (SPEC 3d)
  CHANGELOG.md                # new entry
```

CP4 adds the only FlexToolsMCP-side source change, in this repo:

```
FlexToolsMCP/
  src/flextoolsmcp/
    templates/
      2-flexicon-template.py    # + flexicon pre-flight block and
                                #   _flexicon_preflight(report), called first in Main()
  tests/
    test_template_flexicon_preflight.py   # NEW -- CP4 unit tests, no FieldWorks
```

Beyond CP4's pre-flight block, `FlexToolsMCP` does not change under this spec. The
template's *teaching shape* and its inaccurate "CRITICAL REQUIREMENT" preamble stay with
`flexicon-guidance-correction`; MCP-side injection through this seam is
`vanilla-flextools-parity` CP2. The other FlexToolsMCP obligation here is SPEC section 5.4:
run the MCP suite against the new `pyflexicon` before those specs land.

**Ordering note for CP4.** The pre-flight's capability probe is
`hasattr(FLExProject, "FromOpenProject")`, so a template shipped before CP1 lands would
warn on every machine, correctly but uselessly. CP4 therefore ships *after* CP1, and its
tests monkeypatch the probe rather than depending on the installed flexicon carrying the
attribute.

**Structure Decision:** the seam ships in `flexicon/code/FLExProject.py` beside
`OpenProject`, because only the module itself can bridge (SPEC section 2) and FlexTools
imports flexlibs, so a bridge anywhere else is unreachable from a real FlexTools run.

---

## Constitution Check

This project has **no `.specify/memory/constitution.md`** -- the directory does not exist.
There are therefore no ratified principles to gate against. The table records the standing
house rules this plan is nonetheless bound by (SPEC section 2 "Settled", `CLAUDE.md`), so a
later constitution has something to compare to.

| Principle (house rule) | Assessment |
|---|---|
| No rename of `flexicon.FLExProject` (51 mangled `_FLExProject__WSHandle` sites) | **PASS** -- the plan adds a classmethod; the class name is untouched, which is exactly what keeps the mangled lookups resolving on a view. |
| No duck-type adapter over a flexlibs project (42 attrs / 170 sites / 14 sub-facades) | **PASS** -- the view *is* a flexicon `FLExProject`; only the LcmCache is borrowed, so all 57 attributes resolve on flexicon's own class. |
| The bridge ships in `flexicon`, not the MCP | **PASS** -- every source change is in the `flexicon` repo. |
| Never reopen a project FlexTools holds (`FP_FileLockedError`) | **PASS** -- `FromOpenProject` calls no `FLExLCM.OpenProject`; the lifecycle guards additionally make it impossible for a view to save or dispose the host cache. |
| No breaking change to existing `OpenProject` callers | **PASS** -- construction via `cls.__new__(cls)` means no `__init__` is added; `OpenProject`'s own path is untouched. |
| Windows console output is ASCII-only (`CLAUDE.md`) | **PASS** -- all new log/exception text is plain ASCII. |
| Write-path changes need live-LCM evidence before approval | **AT RISK, gated** -- CP3/T3.2 is unresolved by construction (see Complexity Tracking). |

### Complexity Tracking

| Violation | Why needed | Simpler alternative rejected |
|---|---|---|
| CP1 cannot be approved on unit tests alone; it needs a live FieldWorks run (T3.2) before shipping | Whether a Phase 1 `Transaction` inside the host's `BeginNonUndoableTask` envelope commits on the host's save is a property of liblcm, not of this code. No amount of reading settles it, and shipping a seam whose writes may silently not persist is the exact failure class this feature exists to end. | Ship on unit tests and let field use decide -- rejected: silent non-persistence is indistinguishable from success to the user, which is precisely Kendall's original incident. |
| `_undoable` is forced `False`, which makes `UndoableOperation()` unavailable on an attached view | The host already holds a non-undoable envelope (`flexlibs/code/FLExProject.py:262`); opening an undoable UOW inside it nests the wrong kind of task. Phase 1 `Transaction` is the only correct mode for a borrowed cache. | Let the view honour the donor's mode -- rejected: flexlibs has no `_undoable` at all, so there is no mode to honour, and inferring one from `writeEnabled` would open exactly the nesting this avoids. |

Re-checked after Phase 1 design: unchanged. No further violations introduced by the data
model or the contract.

---

## Phase 0 -- Research

See [`research.md`](./research.md). Seven decisions, each grounded in a line read in the
live tree rather than in the spec's narrative; three of them **correct drift** between the
spec (written 2026-09-09 against an older flexicon) and the code as it stands today -- R2
(`undoable` now defaults to `True`), R3 (`SaveChanges` grew an issue-#243 depth guard), and
R7 (that guard's standing advice, "use `CloseProject()` instead", is a silent no-op on a
view and must not be repeated in the attached-view refusal).

## Phase 1 -- Design

- [`data-model.md`](./data-model.md) -- the attached view's state, the donor's required
  shape, and the two-state lifecycle.
- [`contracts/from-open-project.md`](./contracts/from-open-project.md) -- the exact public
  surface: signature, borrowed attributes, return identity, refusals, and error text.
