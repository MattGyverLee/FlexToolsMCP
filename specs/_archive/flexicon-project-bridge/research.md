# RESEARCH -- flexicon project bridge (Phase 0)

Every decision below was checked against the working tree
(`D:/Github/_Projects/_LEX/flexicon`, `D:/Github/_Projects/_LEX/flexlibs`) on
2026-09-09, not inferred from the spec's prose. **R2 and R3 correct drift** between
`spec.md` and the code as it now stands.

---

## R1 -- Construct the view with `cls.__new__(cls)`, assign four attributes

**Decision.** `FromOpenProject` allocates with `cls.__new__(cls)` and sets exactly
`project`, `lp`, `lexDB`, `writeEnabled`, plus `_undoable = False` and
`_attached_donor = donor`. It adds no `__init__`.

**Rationale.** `flexicon.FLExProject` (`flexicon/code/FLExProject.py:123`) has no
`__init__`; all state is born inside `OpenProject`, which after the LCM open does only
`self.lp = self.project.LangProject` (:270), `self.lexDB = self.lp.LexDbOA` (:271),
`self.writeEnabled = ...` (:277) and `self._undoable = ...` (:278). Crucially the facade
properties depend on nothing else: `LexEntry` (:1361) is

```python
if "_lexentry_ops" not in self.__dict__:
    self._lexentry_ops = LexEntryOperations(self)
return self._lexentry_ops
```

and `BaseOperations.__init__` (`BaseOperations.py:617-624`) stores that argument as
`self.project`. So an operation's `self.project` is the *view*, and `self.project.project`
is the borrowed cache -- all 57 attributes the operations touch resolve on flexicon's own
class. `__WSHandle` is a method (:3708), not cached state, and the 51 mangled call sites
spell `_FLExProject__WSHandle`, which resolves on a view because the class name is
unchanged.

**Alternatives considered.** Adding an `__init__` shared by `OpenProject` and the bridge
-- rejected: `FLExProject()` with no arguments is the documented construction in the class
docstring and in every existing script, so any required-argument `__init__` is a breaking
change for callers this feature has no business touching. Copying the donor's `__dict__`
wholesale -- rejected: it would import flexlibs-only private state onto a flexicon instance
and would silently mask a donor that is missing the cache (R5).

---

## R2 -- Force `_undoable = False`, and make the refusal say why

**Decision.** The view sets `_undoable = False` unconditionally. Additionally, the existing
`UndoableOperation` refusal is made attached-view aware.

**Rationale.** flexlibs opens a session-long non-undoable envelope whenever the project is
write-enabled -- `flexlibs/code/FLExProject.py:256-264` calls
`self.project.MainCacheAccessor.BeginNonUndoableTask()` -- so a write-enabled donor arrives
with `ActionHandlerAccessor.CurrentDepth` already at 1. Opening a flexicon Phase 2
`UndoableOperation` inside that is the wrong kind of nesting; Phase 1 `Transaction` is the
correct mode, exactly as SPEC 3a says.

**The drift.** SPEC 3a was written when `undoable` was not yet the default. It is now
`True` since 4.4.0 (`FLExProject.py:179-186`), which makes the consequence of forcing
`False` far louder than the spec accounts for: `_FLExUndoableOperation.__enter__`
(`undoable_operation.py:92-99`) raises `FP_TransactionError` with the text "Project must be
opened with undoable=True to use UndoableOperation. Current project was opened with
undoable=False." On an attached view that message is **actively misleading** -- nobody
called `OpenProject`, and no argument the module could pass would change it. The refusal is
correct; the explanation is not. So the plan adds an `_attached_donor` branch to that
message naming `FromOpenProject`, the host's envelope, and `Transaction()` as the supported
construct.

**Alternatives considered.** Honour the donor's mode -- rejected: flexlibs has no
`_undoable` attribute at all, so there is nothing to honour, and deriving one from
`writeEnabled` would open precisely the nesting this avoids. Leave the existing message
alone -- rejected: an inaccurate error in the first path a migrating module will hit is how
this feature's original incident (a green run that was not green) repeats itself in a new
costume.

---

## R3 -- Guard the attached view before the existing depth guard

**Decision.** `SaveChanges()` and the disposing paths check `_attached_donor` first and
raise `FP_RuntimeError` naming `FromOpenProject`. `CloseProject()` on a view returns
without doing anything, logging at debug.

**Rationale.** `CloseProject` (`FLExProject.py:325`) ends the envelope, runs `usm.Save()`,
then in a `finally` calls `self.project.Dispose()` / `del self.project` (:440-444) -- on a
view that saves and disposes the FlexTools cache out from under FlexTools. It must be a
no-op, and must not raise, so a module that defensively closes still works (SPEC 3b).

**The drift.** `SaveChanges` (:798) has since grown its own issue-#243 depth guard: it
refuses whenever `CurrentDepth > 0`, in either mode. With a write-enabled flexlibs donor
the host envelope holds depth at 1 for the whole session, so `SaveChanges()` on a view
already fails today -- but with a transaction-depth message that says nothing about the
donor. The attached-view check therefore goes **first**, so the module is told the real
reason (the host owns the save), and the depth guard stays as the general-case backstop. A
read-only donor (`writeEnabled=False`, no envelope, depth 0) would otherwise slip past the
depth guard into `FP_ReadOnlyError`, which is also the wrong story.

**Alternatives considered.** Rely on the depth guard alone -- rejected on both counts
above. Make `CloseProject` raise on a view -- rejected: SPEC 3b is explicit, and a
defensive `CloseProject()` in an otherwise-correct module is not an error.

---

## R4 -- Idempotence by `isinstance`, returning the donor unchanged

**Decision.** `isinstance(donor, cls)` returns `donor` itself -- the same object, not a
copy and not a wrapper.

**Rationale.** The whole point of SPEC 3d is one module shape that runs unchanged under
both hosts. Under the MCP the donor is already a flexicon `FLExProject`
(`FlexToolsMCP/src/flextoolsmcp/server/handlers/execution.py:3911,3939`), and it owns its
project: the MCP opened it and the MCP will close it. Returning it unchanged preserves that
ownership, keeps its `_undoable` mode (which under the MCP may legitimately be Phase 2), and
keeps the already-cached operations objects in its `__dict__`. Identity, not equivalence, is
the testable property -- CP2 T2.1 asserts `is`.

**Alternatives considered.** Always build a fresh view, even from a flexicon donor --
rejected: it would silently downgrade a Phase 2 MCP session to Phase 1 and leave two objects
believing they own the same cache.

---

## R5 -- Validate the donor at the seam, and name the donor's module

**Decision.** Validate before assigning anything: `project` present and non-None; `lp` and
`lexDB` taken from the donor when present, else derived from `cache.LangProject` /
`.LexDbOA`; `writeEnabled` must exist. On failure raise `FP_ParameterError`
(`exceptions.py:82`, an `FP_RuntimeError` subclass) listing every absent attribute and
`type(donor).__module__`.

**Rationale.** SPEC 3c: the failure this replaces is an `AttributeError` fifty frames deep
inside an operation, which is unreadable to the non-programmer this project exists for.
Collecting *all* missing attributes into one message beats failing on the first.
`type(donor).__module__` rather than the class name is the discriminator, because both
classes are named `FLExProject` (SPEC section 2) -- `flexlibs.code.FLExProject` vs
`flexicon.code.FLExProject` is the only honest distinguisher.

**Alternatives considered.** `hasattr`-based duck typing with no error -- rejected, that is
the current silent-failure behaviour. A new exception type -- rejected: `FP_ParameterError`
is the existing "you passed me the wrong thing" signal, and callers already catch
`FP_RuntimeError`.

---

## R6 -- Unit tests on a fake donor; live tests gate the ship

**Decision.** CP2 goes in a new `tests/test_from_open_project.py` at the `flexicon` repo
root, using a hand-rolled fake donor (a plain object with `project.LangProject.LexDbOA` and
`writeEnabled`), carrying **no** `requires_live_project` marker. CP3 stays a separate,
human-authorized live run and blocks CP1 from shipping.

**Rationale.** `pyproject.toml:90-92` registers exactly one marker,
`requires_live_project` ("test opens a real .fwdata project via
`FLExProject.OpenProject()`"), and the bridge by construction opens nothing -- so the marker
would be a lie. The repo-root `tests/` tree already carries this kind of double
(`tests/conftest.py:305` `MockFLExProject`, `tests/test_b1t_action_handler_double.py`), so
the pattern to copy exists. The four borrowed attributes and the two-state lifecycle are
fully observable on a fake; what a fake **cannot** observe is T3.2 -- whether a Phase 1 write
inside the host's envelope survives to disk. That is why CP3 is a gate and not a follow-up.

**Alternatives considered.** Fold the tests into `tests/test_transaction_honesty.py` --
rejected: that file is about mode honesty within an owned project; the bridge's lifecycle
refusals are a distinct surface and deserve their own file. Skip unit tests and go straight
to live -- rejected: the live run needs FieldWorks and a human, so every property that can be
pinned on a fake must be pinned first, or the scarce live run gets spent on regressions.

---

## R7 -- The attached-view `SaveChanges` refusal must not repeat the existing advice

**Decision.** The attached-view `FP_RuntimeError` raised by `SaveChanges()` says the host
owns the save and the module should simply return. It must **not** tell the caller to use
`CloseProject()` instead.

**Rationale.** Found while verifying R3. The existing `SaveChanges` docstring
(`FLExProject.py:798-826`) ends its `undoable=False` note with "Use ``CloseProject()``
instead, which ends that envelope before saving" -- correct for an owned project, and the
`FP_TransactionError` from the issue-#243 depth guard sits directly under that advice. On an
attached view that advice is a trap: R3 makes `CloseProject()` a silent no-op, so a user who
follows it gets a run that reports success and writes nothing. That is precisely the
failure class this feature exists to end -- a green run that is not green -- reintroduced
one layer down. The attached-view branch must therefore replace the advice, not just the
diagnosis.

**Alternatives considered.** Let the attached-view message inherit the existing wording --
rejected for the reason above. Make `CloseProject()` raise on a view so the advice at least
fails loudly -- rejected: SPEC 3b is explicit that a defensive `CloseProject()` must not
fail, and R3 already settled it.
