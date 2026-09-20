# UOW Capability Gate -- Domain Review, Cycle 1

Agent: lex-domain (read-only; report transcribed to disk by the main session,
which independently re-verified every file:line citation below against the
installed flexicon 4.8.0 source).

Installed flexicon: 4.8.0, via `uv run`. Source read at
`C:\Users\thoua\AppData\Local\uv\cache\archive-v0\FLIZB7h4vh7yhFvj\flexicon\`.
Note the repo's bare `python` on PATH is 3.14 and has no flexicon -- use
`uv run python`.

## 1. Does the #92 failure mode still exist on 4.8.0's `undoable=True` path?

**No -- fixed.** The #92 comment claimed "flexicon's `undoable=True` path skips
`BeginNonUndoableTask()` and opens no UnitOfWork ... every mutating call
raised." The first half is true and by design; the conclusion is false. Under
`undoable=True` no session envelope is opened *because* each mutation opens its
own task.

Deciding code, `FLExProject.py:411-414`:

```python
elif self.writeEnabled and self._undoable:
    # Phase 2 behavior: no envelope; each UndoableOperation wraps its own task
    logging.getLogger(__name__).debug("OpenProject: undoable mode enabled")
    # Nothing to do here; BeginUndoTask called per-operation by UndoableOperation
```

No raise, no missing-envelope condition. `__init__.py:49-53` names the
capability: `per-operation-uow` -- "Every LCM mutation runs inside a named,
nesting-aware unit of work."

## 2. Recommended gate expression for `execution.py`

Per the probe form the flexicon docstring prescribes at `__init__.py:22-29`
(which names FlexToolsMCP explicitly as the intended consumer):

```python
_CAPS = getattr(flexicon, "CAPABILITIES", frozenset())
_undoable = "per-operation-uow" in _CAPS
project.OpenProject(
    projectName=PROJECT_NAME,
    writeEnabled=WRITE_ENABLED,
    undoable=_undoable,
    ui=_lcm_ui,
)
```

- **Required token:** `per-operation-uow` -- it governs the OpenProject-time
  mode choice.
- **`transaction-rollback`** should be probed the same way wherever rollback
  behaviour is *asserted to users* (e.g. write_certification), but it is not an
  independent gate: it is a consequence of the same mode flag.
- **Fallback on <=4.3.0:** `CAPABILITIES` is undefined, `getattr` returns
  `frozenset()`, `_undoable` is `False` -- reproducing today's hardcoded
  behaviour exactly. The 4.3.0 floor is preserved by the empty-set default with
  no version-string branch. Use the one-line `getattr(..., frozenset())` form,
  not a two-step `hasattr()`; flexicon's docstring is explicit about this.

## 3. `detect_nested_unit_of_work` -- re-derivation (the hard part)

**Verdict: keep the gate, re-scope the message. Do not remove it.**

The gate's stated rationale (`validators.py:448-472`) is scoped to "the runner
holds ONE session-long non-undoable task". That premise is `_undoable=False`
only. Under `_undoable=True`, `OpenProject()` opens no session envelope
(`FLExProject.py:411-414`), confirmed structurally by `HasOpenSessionTask()`
(`FLExProject.py:772-814`), which returns `False` *unconditionally* in that mode
-- and whose docstring exists precisely to stop consumers reading
`CurrentDepth == 1` as mode-agnostic (flexicon issue #243).

But the risk **relocates rather than vanishes**:

- flexicon's own `Transaction()` / `UndoableOperation()` read
  `ActionHandlerAccessor.CurrentDepth` and **join** rather than nest
  (`FLExProject.py:745-750`).
- A script calling a **raw** liblcm helper (`UndoableUnitOfWorkHelper`,
  `NonUndoableUnitOfWorkHelper`, bare `BeginUndoTask` /
  `BeginNonUndoableTask`) from *inside* a flexicon per-operation block still
  nests a second raw task inside that task, with the same liblcm `UndoStack.cs`
  behaviour: the open task rolls back before the raise.

Under `undoable=True` essentially every mutating call is individually wrapped,
so "one small per-operation envelope" replaces "one big session envelope" as the
thing that can be nested into. The AST-level ban should therefore stay
**construct-based and unconditional** -- a script cannot reliably know whether
it is executing inside flexicon's wrapper at the point it calls the raw helper.

What must change is the **explanation**, which currently misdescribes the
mechanism under the new mode. Make it mode-conditional:

- `_undoable=False` (unchanged): "Code opens its own raw liblcm UnitOfWork,
  which nests inside the runner's already-open non-undoable task and will
  discard this run's writes."
- `_undoable=True` (new): "Code opens its own raw liblcm UnitOfWork. flexicon
  already wraps each mutation in its own named unit of work; a raw helper call
  executing while one of those is open nests inside it and will discard that
  operation's writes before the error is raised."

## 4. DateModified stamping -- HYPOTHESIS ONLY, not confirmed

Nothing in the read source ties `DateModified` to UOW boundaries. flexicon has
no stamping code; if liblcm stamps, it does so on task commit / `PropChanged`,
which is not visible from `FLExProject.py`.

Plausible mechanism: `_undoable=True` opens and closes a distinct task **per
mutating call**, so each may get its own commit-time stamping pass, where the
session-envelope mode defers everything to the single `EndNonUndoableTask()` /
`usm.Save()` at `CloseProject()` (`FLExProject.py:607-693`).

**This must not be treated as established.** It requires a live FLEx project and
a before/after `DateModified` comparison under each mode. Also to reproduce
live: the reported asymmetry, where `LexReferenceOperations.Delete` *does* move
`DateModified` because liblcm's domain layer stamps affected entries inline in
the delete side-effect, independent of the UOW pass.

## Follow-up pointer

flexicon's docstring cites `docs/FLEXTOOLSMCP_WRITE_CONTRACT.md` section 3 --
a contract document written for this consumer specifically. Read it before
implementing the gate.
