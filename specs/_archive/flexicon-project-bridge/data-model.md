# DATA MODEL -- flexicon project bridge (Phase 1)

This feature introduces no persisted entity and no LCM schema change. What it introduces
is a second **construction mode** for an existing runtime object, `flexicon.FLExProject`,
and one new attribute that distinguishes the two. This document pins that state.

---

## 1. Entity: `FLExProject` (existing, reshaped)

`flexicon/code/FLExProject.py:123`. One class, now reachable in two ways.

| Field | Type | Owned mode (`OpenProject`) | Attached mode (`FromOpenProject`) |
|---|---|---|---|
| `project` | `LcmCache` | Created by `FLExLCM.OpenProject` (:249) | **Borrowed** from `donor.project` |
| `lp` | `ILangProject` | `self.project.LangProject` (:270) | `donor.lp` if present, else `cache.LangProject` |
| `lexDB` | `ILexDb` | `self.lp.LexDbOA` (:271) | `donor.lexDB` if present, else `lp.LexDbOA` |
| `writeEnabled` | `bool` | Caller argument (:277) | **Borrowed** from `donor.writeEnabled` |
| `_undoable` | `bool` | `undoable and writeEnabled` (:278) | **Always `False`** (R2) |
| `_attached_donor` | object or absent | **Absent** | The donor object |
| `_<facade>_ops` | operations instance | Lazily cached in `__dict__` on first property access | Identical -- no special handling |

**Invariant A (mode discriminator).** `_attached_donor` is present **iff** the instance is
an attached view. Owned instances never set it. All lifecycle guards branch on
`hasattr(self, "_attached_donor")`, never on `writeEnabled` or `_undoable`, because a
read-only owned project and a read-only view are indistinguishable by those.

**Invariant B (no ownership).** An attached view never creates, saves, or disposes a cache.
`self.project` on a view is a reference to an object whose lifetime the host controls; the
view has no say in it and must be unable to end it.

**Invariant C (facade completeness).** Because operations receive the *view*
(`BaseOperations.__init__` stores the argument as `self.project`), every flexicon attribute
resolves on flexicon's own class. Only the cache is foreign. This is what makes the 42
missing-attribute measurement in SPEC section 1 irrelevant to this design rather than an
argument against it.

**Invariant D (name preservation).** The class name stays `FLExProject`, so
`self.project._FLExProject__WSHandle(...)` -- spelled literally at 51 call sites -- resolves
on a view exactly as on an owned instance.

---

## 2. Entity: donor (input contract, not a type)

The object the host passed to `Main()`. It is duck-typed, never `isinstance`-checked
against flexlibs (which may not even be importable in the MCP process).

| Attribute | Required? | Validation |
|---|---|---|
| `project` | **Yes** | must exist and be non-`None` |
| `writeEnabled` | **Yes** | must exist (flexlibs sets it; value is borrowed verbatim, including `False`) |
| `lp` | No | used if present; else derived from `project.LangProject` |
| `lexDB` | No | used if present; else derived from `lp.LexDbOA` |

Known donor shapes:

| Host | Donor class | `__module__` | Envelope state on arrival |
|---|---|---|---|
| Real FlexTools | `flexlibs` `FLExProject` (`flextoolslib/code/FTModules.py:75`) | `flexlibs.code.FLExProject` | `BeginNonUndoableTask()` open when write-enabled (`flexlibs/code/FLExProject.py:262`), so `CurrentDepth >= 1`; nothing open when read-only |
| This MCP | `flexicon` `FLExProject` (`execution.py:3939`) | `flexicon.code.FLExProject` | Owned; may be Phase 1 or Phase 2 |

Validation failure raises `FP_ParameterError` naming every absent attribute plus
`type(donor).__module__`. `__module__` is the discriminator, not the class name -- both are
`FLExProject` (SPEC section 2).

---

## 3. State transitions

An attached view has two states and no terminal one -- it is never closed, because it never
owned anything.

```
                 FromOpenProject(donor)
  [donor]  ---------------------------->  [ATTACHED VIEW]
     |         (validate, borrow 4,            |
     |          _undoable=False)               |  reads: unrestricted
     |                                         |  writes: allowed iff writeEnabled,
     |     donor is already a flexicon         |          inside Transaction() only
     +---- FLExProject: return it -----> [OWNED, unchanged]
                  (identity, R4)

  ATTACHED VIEW, terminal actions:
    CloseProject()      -> no-op, debug log, returns None   (SPEC 3b)
    SaveChanges()       -> FP_RuntimeError naming FromOpenProject
    dispose paths       -> FP_RuntimeError naming FromOpenProject
    UndoableOperation() -> FP_TransactionError, attached-view wording (R2)
    Transaction()       -> permitted; Phase 1 labelling semantics
```

There is no ATTACHED -> CLOSED edge by design. The view is garbage-collected; the host
saves and disposes the cache on its own schedule.

---

## 4. What is deliberately not modelled

- **No copy of the donor's state.** Four attributes, named explicitly. A `__dict__` copy
  would drag flexlibs-private state onto a flexicon instance (R1).
- **No adapter layer.** No object stands between an operation and the view (SPEC section 2).
- **No nesting counter.** `_transaction_depth` was removed as issue #234; depth is read from
  `ActionHandlerAccessor.CurrentDepth` at each `__enter__`. The view adds no new counter.
- **No mode negotiation.** The view does not inspect the donor's transaction mode. It is
  Phase 1, unconditionally, because the host owns the envelope.
