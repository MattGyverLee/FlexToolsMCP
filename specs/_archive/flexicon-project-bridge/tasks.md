# TASKS -- flexicon project bridge: `FLExProject.FromOpenProject()`

**Feature:** `flexicon-project-bridge`
**Spec:** [`spec.md`](./spec.md) | **Plan:** [`plan.md`](./plan.md) | **Contract:** [`contracts/from-open-project.md`](./contracts/from-open-project.md)
**Size:** normal (no `size` recorded)

> **Implementation repo is mostly NOT this one.** Unless a path says otherwise, every
> source path below is relative to `D:/Github/_Projects/_LEX/flexicon` (shipped as
> `pyflexicon`). There are two exceptions, both in `FlexToolsMCP`: the cross-repo
> regression gate (T021), and **US5 / CP4** (T023-T025) -- the template pre-flight
> added to `spec.md` during this tasks step at the user's request.

---

## Phase 1: Setup

**Wave 1 -- single task:**

- [x] **T001** Create a working branch in the `flexicon` repo and confirm the tree is clean before any edit; all source lands there, not in `FlexToolsMCP` · `D:/Github/_Projects/_LEX/flexicon` (git)

---

## Phase 2: Foundational (BLOCKS all stories)

Shared discriminator and shared test doubles. No user-story work begins until this phase is done.

**Wave 1 -- independent (different files):**

- [x] **T002** [P] Add the attached-view discriminator: a private helper implementing Invariant A's `hasattr(obj, "_attached_donor")` check, with a docstring stating that lifecycle guards branch on it and **never** on `writeEnabled` or `_undoable` (a read-only owned project and a read-only view are indistinguishable by those) · `flexicon/code/FLExProject.py`
- [x] **T003** [P] Create the CP2 test module with the shared doubles: `_FakeCache` (exposing `LangProject.LexDbOA`, `MainCacheAccessor` with `BeginNonUndoableTask`/`EndNonUndoableTask` spies, `ActionHandlerAccessor.CurrentDepth`, and a `Dispose` spy) and `_FakeDonor(write_enabled=True)` carrying `project` + `writeEnabled`. **No `requires_live_project` marker** -- the bridge opens nothing, and that is the only marker `pyproject.toml:90-92` registers · `tests/test_from_open_project.py`

**Checkpoint:** the discriminator both stories branch on exists, and the fake donor both stories test against exists.

---

## Phase 3: US1 -- Attach a flexicon facade to a project the host already opened (P1, MVP)

**Goal:** a module handed a flexlibs `FLExProject` by FlexTools can obtain the full flexicon
facade over that same cache -- `FromOpenProject(donor)` -- without opening, saving, or
disposing anything, and gets a readable error instead of a deep `AttributeError` when the
donor is unusable.

**Independent Test:** run `tests/test_from_open_project.py` against a `_FakeDonor`; the four
borrowed attributes, `_undoable is False`, donor identity, and the `FP_ParameterError`
message are all observable with no FieldWorks present.

### Tests (write first, must fail)

**Wave 1 -- single task (one file):**

- [x] **T004** [US1] Write the attach tests -- T2.1a: the four attributes are borrowed and `view.project is donor.project`; T2.1b: `view._undoable is False` even when `donor.writeEnabled is True`; T2.1c: `FromOpenProject(flexicon_instance) is flexicon_instance` (identity, and `_attached_donor` is **not** set on it); T2.3: a donor missing `project` raises `FP_ParameterError` whose message contains `project`, `FromOpenProject`, and `type(donor).__module__`; plus SPEC T1.4: `FLExProject.FromOpenProject` is reachable from the package root with **no** edit to `flexicon/__init__.py`. Assert on substrings, never exact prose · `tests/test_from_open_project.py`

### Implementation

**⟶ Wait for Wave 1 to finish, then:**

**Wave 2 -- independent (different files):**

- [x] **T005** [P] [US1] Add the `FromOpenProject(cls, donor)` classmethod beside `OpenProject` (`FLExProject.py:164`): `isinstance(donor, cls)` short-circuit **first** (return the donor unchanged), then validation, then `cls.__new__(cls)` -- **not** `cls()`, no `__init__` is added -- then assign exactly `project`, `lp` (donor's if present and non-`None`, else `donor.project.LangProject`), `lexDB` (donor's if present and non-`None`, else `lp.LexDbOA`), `writeEnabled` verbatim, `_undoable = False` unconditionally, `_attached_donor = donor`. Never mutate the donor · `flexicon/code/FLExProject.py`
- [x] **T006** [P] [US1] Add `def FromOpenProject(cls, donor: Any) -> "FLExProject": ...` beside the `OpenProject` stub (`FLExProject.pyi:186`). Leave that stub's pre-existing staleness (it omits the runtime `undoable` parameter) alone -- out of scope · `flexicon/code/FLExProject.pyi`

**⟶ Wait for Wave 2 to finish, then:**

**Wave 3 -- single task (same file as T005):**

- [x] **T007** [US1] Add the donor-validation path called by T005: require `project` present and non-`None` and `writeEnabled` present; collect **every** missing attribute (not just the first) and raise `FP_ParameterError` (`exceptions.py:82`) naming `FromOpenProject`, each absent attribute, and `type(donor).__module__` -- the module is the discriminator because both candidate classes are named `FLExProject`. ASCII only · `flexicon/code/FLExProject.py`

**Checkpoint:** US1 is independently functional -- a fake or real donor yields a working
flexicon facade, and an unusable donor fails readably at the seam. T004 passes.

---

## Phase 4: US2 -- A view can never destroy the host's project, nor report a save it did not make (P1)

**Goal:** every lifecycle path that would end the host's envelope or dispose its cache is
refused on an attached view, and each refusal tells the true story -- the host owns the save
-- rather than a transaction-depth, read-only, or `opened with undoable=False` message that
blames an argument nobody passed.

**Independent Test:** with `_attached_donor` set on a fake, `CloseProject()` returns without
touching the cache spies, and `SaveChanges()` / `UndoableOperation()` raise with the required
substrings present and the trap substrings absent.

### Tests (write first, must fail)

**Wave 1 -- single task (one file):**

- [x] **T008** [US2] Write the lifecycle tests -- T2.2a: `CloseProject()` on a view returns `None`, does not raise, and leaves the fake cache with **no** `EndNonUndoableTask`, no `usm.Save()`, and no `Dispose()` call; T2.2b: `SaveChanges()` raises `FP_RuntimeError` whose message contains `FromOpenProject` and does **NOT** contain `CloseProject` (R7 -- the standing advice is a silent no-op on a view, so repeating it would yield a green run that writes nothing); T2.2c: `UndoableOperation()` raises `FP_TransactionError` whose message contains `FromOpenProject` and does **NOT** contain `opened with undoable=False` · `tests/test_from_open_project.py`

### Implementation

**⟶ Wait for Wave 1 to finish, then:**

**Wave 2 -- independent (different files):**

- [x] **T009** [P] [US2] Add the attached-view no-op at the top of `CloseProject` (`FLExProject.py:325`), before anything reaches `EndNonUndoableTask` (`:366`), `usm.Save()`, or the `finally` that runs `self.project.Dispose()` / `del self.project` (`:443`): log at `debug`, return `None`, **never raise** (SPEC 3b -- a defensive close in an otherwise-correct module is not an error). Note for the contract's "disposing paths" row: `CloseProject` is the *only* path that reaches `Dispose()` -- `flexicon.FLExProject` exposes no public `Dispose()` method (verified), so this guard closes that surface · `flexicon/code/FLExProject.py`
- [x] **T010** [P] [US2] Add an attached-view branch to the `_undoable` refusal in `_FLExUndoableOperation.__enter__` (`undoable_operation.py:92-99`): the new message names `FromOpenProject`, states that the host holds a session-long non-undoable envelope, and points at `Transaction()` as the supported construct. Keep the exception type `FP_TransactionError`; keep the existing owned-project wording for non-views · `flexicon/code/undoable_operation.py`

**⟶ Wait for Wave 2 to finish, then:**

**Wave 3 -- single task (same file as T009):**

- [x] **T011** [US2] Add the `SaveChanges` attached-view guard (`FLExProject.py:798`) **before** the `writeEnabled` check and **before** the existing issue-#243 `CurrentDepth > 0` guard, so a write-enabled donor hears "the host owns the save" instead of a depth message and a read-only donor does not slip into `FP_ReadOnlyError`. Raise `FP_RuntimeError` naming `FromOpenProject`, saying the host saves and the module should simply return; it must **not** advise `CloseProject()`. Leave the depth guard in place as the general-case backstop · `flexicon/code/FLExProject.py`

**⟶ Wait for Wave 3 to finish, then:**

**Wave 4 -- single task (same file, same method):**

- [x] **T012** [US2] Scope the `SaveChanges` docstring's "Use `CloseProject()` instead" note to *owned* projects and document the attached-view refusal beside it, so the docstring can no longer be read as advice a view should follow (R7) · `flexicon/code/FLExProject.py`

**Checkpoint:** US2 is independently functional -- a view cannot save, close, dispose, or open
an undoable UOW, and every refusal is honest. T008 passes.

---

## Phase 5: US3 -- Live persistence gate: prove a write through a view reaches disk (P1, BLOCKS SHIP)

**Goal:** settle SPEC T3.2, which no amount of reading can settle -- with FLEx holding the
project, does a Phase 1 `Transaction` inside the flexlibs non-undoable task actually commit
on the host's save, or does it need an explicit `MainCacheAccessor` flush?

**Requires FieldWorks and explicit human authorization** (live write path). Do not run
unattended.

**Independent Test:** the recorded pre/post evidence artifact itself -- a value set through an
attached view, observed after closing and reopening FlexTools.

**Wave 1 -- independent (different environments):**

- [x] **T013** [P] [US3] SPEC T3.1: under this MCP, run a module in the SPEC 3d shape (`fx = FLExProject.FromOpenProject(project)`) and a control module using `project.LexEntry` directly against the same project; assert the results are identical. Record the evidence artifact · `evidence/` (flexicon repo)
- [x] **T014** [P] [US3] SPEC T3.2 (**the gate**): on a scratch project with real FlexTools holding it, `SetGloss` through an attached view inside `Transaction()`, close FlexTools, reopen, and assert the value persisted. Record pre/post evidence · `evidence/` (flexicon repo)

**⟶ Wait for Wave 1 to finish, then:**

**Wave 2 -- single task:**

- [x] **T015** [US3] Repeat T3.2 on Sena 3 (SPEC 5.2 -- scratch project first, then Sena 3) and record the evidence · `evidence/` (flexicon repo)

**⟶ Wait for Wave 2 to finish, then:**

**Wave 3 -- single task:**

- [x] **T016** [US3] Record the gate decision. If the value persisted, CP1 is clear to ship. **If it did not, STOP: CP1 must not ship** -- `_undoable = False` alone is insufficient, `contracts/from-open-project.md` section 2.2 needs a flush step, and this feature returns to plan rather than proceeding to docs · `specs/flexicon-project-bridge/` (this repo) + `evidence/` (flexicon repo)

**Checkpoint:** the one question the plan could not answer by reading is answered with live
evidence, and the ship/no-ship decision is recorded rather than assumed.

---

## Phase 6: US4 -- The docs teach the portable module shape (P2)

**Goal:** the shape in SPEC 3d is what a user finds when they look, so the next module is
written portable instead of migrated later.

**Independent Test:** each document states the attached-view rule without contradicting the
refusals shipped in US2.

**Wave 1 -- independent (different files):**

- [x] **T017** [P] [US4] Document that attached views are Phase 1 unconditionally: `Transaction()` is supported, `UndoableOperation()` is refused, and the host -- not the module -- owns the save · `docs/TRANSACTION_GUIDE.md`
- [x] **T018** [P] [US4] Document the portable module shape (SPEC 3d) and why `from flexicon import FLExProject` alone was never enough: importing the class does not change the instance `Main()` is handed · `docs/MIGRATION_GUIDE.md`
- [x] **T019** [P] [US4] Add the `[Unreleased]` entry for `FLExProject.FromOpenProject()`, the lifecycle refusals, and the reworded `UndoableOperation` message · `CHANGELOG.md`

**Checkpoint:** a user reading the docs writes the portable shape without being told.

---

## Phase 7: US5 -- Warn when flexicon is missing or out of date (P2, CP4)

**Goal:** SPEC 3d finally makes `from flexicon import FLExProject` load-bearing, which means
the module now depends on whatever Python environment the user's FlexTools install has. Two
environment failures become possible, and neither reads as one: an absent `pyflexicon` dies
with an `ImportError` load traceback before `Main()` runs, and a pre-bridge `pyflexicon`
imports cleanly and then dies with `AttributeError: type object 'FLExProject' has no
attribute 'FromOpenProject'` on the first line of `Main()`. Both are this feature's own
failure class one layer out -- the user cannot tell an environment problem from a bug in
their module.

**Ships after CP1 is released, not merely written.** The probe is
`hasattr(FLExProject, "FromOpenProject")`, so a template shipped ahead of US1 would warn
correctly but uselessly on every machine (plan.md, "Ordering note for CP4").

**Independent Test:** `tests/test_template_flexicon_preflight.py` exercises the helper
directly against a fake `report` with the probes monkeypatched -- no FieldWorks, and without
uninstalling flexicon from the dev environment.

### Tests (write first, must fail)

**Wave 1 -- single task (one file):**

- [x] **T023** [US5] Write the pre-flight tests per contract section 8.4 -- T4.1a: the template emitted by `flextools_get_module_template(flavor='flexicon')` contains `_flexicon_preflight` and calls it as the first statement of `Main()`; T4.2a: the not-installed path returns `False` and the message contains `pip install pyflexicon` plus the captured `ImportError` text; T4.2b: the too-old path (flexicon present, `FromOpenProject` absent) returns `False` and the message contains `pip install -U pyflexicon` plus the version found; T4.2c: a **ratchet** asserting the template source contains no version-string comparison, so a hardcoded floor cannot drift back in; T4.3a: every character the pre-flight can emit is ASCII; T4.4a: the happy path returns `True` and calls **no** `report` method at all; T4.4b: a probe that itself raises returns `True` (fail open) and does not propagate · `FlexToolsMCP/tests/test_template_flexicon_preflight.py`

### Implementation

**⟶ Wait for Wave 1 to finish, then:**

**Wave 2 -- single task (one file):**

- [x] **T024** [US5] Add the pre-flight block per contract section 8.1: wrap the existing `from flexicon import (...)` in `try/except ImportError`, capturing the error text and setting `_flexicon = None`; add `_flexicon_installed_version()` reading `getattr(_flexicon, "version", None)` first (present today -- `4.6.0`) then `importlib.metadata.version("pyflexicon")`, each guarded, both falling back to `"unknown"`; add `_flexicon_preflight(report)` probing `_flexicon is None`, then `hasattr(FLExProject, "FromOpenProject")`. **Capability probe only -- never a version comparison** (T4.2: a hardcoded floor is a second source of truth that goes wrong the first release nobody remembers to raise it). Never raises, silent on success, ASCII with the `[ERROR]` prefix the file already uses · `FlexToolsMCP/src/flextoolsmcp/templates/2-flexicon-template.py`

**⟶ Wait for Wave 2 to finish, then:**

**Wave 3 -- single task (same file as T024):**

- [x] **T025** [US5] Make `if not _flexicon_preflight(report): return` the first statement of `Main()`, followed by `fx = FLExProject.FromOpenProject(project)` (contract section 8.1). Leave the "CRITICAL REQUIREMENT" preamble and the Shape B `LexEntryOperations(project)` examples **alone** -- both are wrong, and both belong to `flexicon-guidance-correction`, not this spec (spec.md CP4 "Boundary") · `FlexToolsMCP/src/flextoolsmcp/templates/2-flexicon-template.py`

**Checkpoint:** a user whose FlexTools environment lacks `pyflexicon`, or carries a
pre-bridge one, gets a named remedy and is told plainly that the module is correct and the
environment is not -- instead of a traceback. Invisible under the MCP and on any current
install.

---

## Phase 8: Polish

**Wave 1 -- independent (different repos):**

- [x] **T020** [P] Run the full `flexicon` pytest suite; confirm no existing `OpenProject`/`CloseProject` test changes behaviour (SPEC 5.3) · `D:/Github/_Projects/_LEX/flexicon`
- [x] **T021** [P] Cross-repo gate: run the `FlexToolsMCP` suite against the new `pyflexicon` before the dependent specs land (SPEC 5.4 -- the only `FlexToolsMCP` obligation under this feature) · `D:/Github/_Projects/_LEX/FlexToolsMCP`

**⟶ Wait for Wave 1 to finish, then:**

**Wave 2 -- single task:**

- [x] **T022** Validate against the spec's Success Criteria (SPEC section 5, all five levels: unit CP2, live CP3, flexicon regression, cross-repo, and the CP4 template pre-flight) and confirm every Constitution Check row in `plan.md` still holds -- including the "AT RISK, gated" row, which T016 resolves · `specs/flexicon-project-bridge/`

---

## Dependencies & Execution Order

**Phase order:** Setup (T001) → Foundational (T002, T003) → US1 (T004-T007) → US2 (T008-T012) → US3 (T013-T016) → US4 (T017-T019) → US5 (T023-T025) → Polish (T020-T022).

- **Setup → Foundational.** T001 blocks everything; nothing is edited before the branch exists.
- **Foundational → all stories.** T002 (discriminator) and T003 (fake donor) are independent of each other and together block US1 and US2.
- **US1:** T004 (tests) → Wave 2 (T005 classmethod, T006 stub -- independent) → T007 (validation, same file as T005).
- **US2:** T008 (tests) → Wave 2 (T009 `CloseProject`, T010 `UndoableOperation` message -- independent) → T011 (`SaveChanges` guard, same file as T009) → T012 (its docstring, same method as T011).
- **US1 alongside US2.** The two stories touch `FLExProject.py` in different methods and can be built in either order, but they are *not* parallel-safe in the same file: sequence T005/T007 against T009/T011/T012 rather than interleaving them.
- **US2 → US3.** The live gate exercises the guards; running it before US2 lands would test a view that can still save.
- **US3 → US4.** T016 is a real gate: a negative T3.2 result sends the feature back to plan, and the docs must not describe a seam whose write semantics changed.
- **US5:** T023 (tests) → T024 (the pre-flight block) → T025 (the `Main()` call site, same file as T024). All three live in `FlexToolsMCP`, so US5 is parallel-safe against every flexicon-repo task -- but it is **not** parallel-safe against the release itself: T023's ratchet and T025's call site both assume the seam T005 adds, so US5 lands after US1 ships. Its own tests monkeypatch the probe and so do not wait on an installed `pyflexicon`.
- **US3 → US5.** The same gate that governs US4: a negative T3.2 result changes what the template should teach, so do not ship a pre-flight for a seam that is going back to plan.
- **All stories → Polish.** T020/T021 are independent (different repos); T022 depends on both, and now also on T023-T025 for the fifth Success-Criteria clause.
