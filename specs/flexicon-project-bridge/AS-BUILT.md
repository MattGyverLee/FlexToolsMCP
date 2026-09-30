# flexicon-project-bridge: as built

**Status:** Retired 2026-09-29. MCP side merged to main as PR #129 (merge `8024123`, 2026-09-10; branch `flexicon-project-bridge-mcp`). Flexicon side merged in flexicon `4a6d6de` and released in pyflexicon 4.7.0 (2026-09-09, flexicon PR #304). Tasks: 25/25 complete.
**Full docs:** [specs/_archive/flexicon-project-bridge/](../_archive/flexicon-project-bridge/) (spec, plan, tasks, research, data-model, [contract](../_archive/flexicon-project-bridge/contracts/from-open-project.md), [gate decision](../_archive/flexicon-project-bridge/gate-decision-t3.2.md), [validation](../_archive/flexicon-project-bridge/validation-t022.md), reviews). Not read by default.
**Pinned here:** none (no test or code opens these files at runtime; only docstring citations).
**Scope:** The seam is flexicon-side (`C:\Github\flexicon`). This repo owns only CP4, the template pre-flight, plus a write-gate fix found while reviewing it. Parent campaign: `specs/CAMPAIGN-flexproject-parity.md` (spec 1 of 4; dependents are `flexicon-guidance-correction`, `portability-preflight`, `vanilla-flextools-parity`, `broken-script-migration`).

## Problem it solved
Real FlexTools passes `Main()` a **flexlibs** `FLExProject` (`flextoolslib/code/FTModules.py:75`). The MCP passed a flexicon one. So a module that used `project.LexEntry` passed under the MCP and failed in FlexTools. `from flexicon import FLExProject` did nothing, because importing a class does not change the instance the module is given.

## What shipped
- flexicon: `FLExProject.FromOpenProject(donor)` classmethod. It attaches the full flexicon facade to a cache the host already opened. It never opens, closes, saves or mutates the donor.
- flexicon: lifecycle refusals on an attached view, plus docs (`docs/TRANSACTION_GUIDE.md` sec. 5, `docs/MIGRATION_GUIDE.md`) and a CHANGELOG 4.7.0 entry.
- MCP: `src/flextoolsmcp/templates/2-flexicon-template.py` gains `_flexicon_preflight(report)`. It is the first statement of `Main()`, followed by `fx = FLExProject.FromOpenProject(project)`. Tests: `tests/test_template_flexicon_preflight.py`.
- MCP: `_TESTED_AGAINST` is stamped at generation time by `src/flextoolsmcp/server/handlers/admin.py:347-385`.

## Public contracts (checked against flexicon v4.11.0-4, `flexicon/code/FLExProject.py`)
- `FromOpenProject(cls, donor) -> FLExProject` (:460). Steps in order:
  1. `isinstance(donor, cls)` returns the donor by identity. `_attached_donor` is not set on it.
  2. `_ValidateDonor`.
  3. `cls.__new__(cls)`. No `__init__` is called.
  4. Borrow `project`, `lp` and `lexDB` (from the donor, or derived from the cache) and `writeEnabled` verbatim.
  5. Set `_undoable = False` unconditionally and `_attached_donor = donor`.
- Discriminator: `_IsAttachedView(obj)` = `hasattr(obj, "_attached_donor")` (:150). Guards branch on it, never on `writeEnabled` or `_undoable`.
- Bad donor: `FP_ParameterError` naming every missing attribute, `FromOpenProject`, and `type(donor).__module__`.
- On a view:
  - `CloseProject()` is a debug-logged no-op returning `None` (:643).
  - `SaveChanges()` raises `FP_RuntimeError` (:1164). This check runs before the write-enabled and depth checks, and the message never advises `CloseProject()`.
  - `UndoableOperation()` raises `FP_TransactionError` naming `FromOpenProject` (`undoable_operation.py:117`).
  - Refusal texts are module constants: `_ATTACHED_VIEW_*_REFUSAL`, :173-212.
- Stub: `FLExProject.pyi:233`, plus the `_attached_donor` attribute (:102).
- Template pre-flight (contract sec. 8):
  - The gate is `hasattr(FLExProject, "FromOpenProject")`. There is no version floor.
  - Missing flexicon: the message says `pip install pyflexicon`. Pre-bridge flexicon: `pip install -U pyflexicon`, plus the version found.
  - Output is ASCII only. The pre-flight is silent when it passes, and fails open if a probe raises.
  - An installed flexicon older than `_TESTED_AGAINST` gets a `report.Warning` only. It never changes the return value.

## Key decisions
- No rename of `flexicon.FLExProject`: 51 `_FLExProject__WSHandle` mangled-name sites depend on the name. To tell the two classes apart, use `type(x).__module__`.
- No duck-type adapter over flexlibs. There are 42 missing attributes over 170 sites, 14 of them whole sub-facades. The view is a real flexicon instance, and only the LcmCache is borrowed.
- The bridge lives in flexicon, because only the module itself can bridge under FlexTools. Never reopen a project the host holds: that raises `FP_FileLockedError`.
- A view is always Phase 1: `Transaction()` works and `UndoableOperation()` is refused. The flexlibs host holds a session-long `BeginNonUndoableTask` envelope, and a real flexlibs donor has no `_undoable` at all.
- The gate is a capability probe, not a version floor. Field evidence: on the FlexTools machine, `flexicon.version` said 4.6.0 while `importlib.metadata` said 4.1.1.
- T3.2 live gate PASSED: a `Transaction()` write through a view persists on the host's close, with no flush. It was run through FlexTools' `ModuleManager.RunModules()` on a scratch copy and on Sena 3, and Sena 3 was restored byte-identical. Evidence is in flexicon `evidence/t3_{1,2}_*_2026-09-09.txt`.

## Gotchas and limits
- On a read-only view, `UndoableOperation()` raises `FP_ReadOnlyError` before it reaches the attached-view branch. This is deliberate and the reverse of `SaveChanges`. It is pinned by `test_read_only_attached_view_reports_read_only_not_attached_view`.
- `CloseProject` is the only path that reaches `Dispose()`. flexicon has no public `Dispose()`.
- US5 was meant to ship only after flexicon released the seam. Otherwise the probe warns on every machine.
- The CP2 unit tests use a fake donor with no marker. The live tiers (T013-T015) were manual and needed human authorization. Nothing runs in CI.

## Divergences from the spec
- More refusals than the spec named: `AbortSession()` (flexicon `3dcba4f`, :1517) and later `SyncForeignChanges()` (`8480702`, #292, :1321) also raise `FP_RuntimeError` on a view.
- `_TESTED_AGAINST` and the "older than tested" warning were added after validation, at the user's request (contract sec. 8.2b). They replace the original T4.2c ratchet, which banned any version comparison. The new rule bans a comparison that gates, plus third-party version machinery.
- T025 also changed `Main()`'s example body from `project.*` to `fx.*`. The "CRITICAL REQUIREMENT" preamble was left for `flexicon-guidance-correction`.
- Paths: tasks.md cites `D:/Github/_Projects/_LEX/flexicon`. The checkout is now `C:\Github\flexicon`.
- pyflexicon floor: the feature shipped in 4.7.0. This repo now requires `>=4.11.0,<5` (requirements.txt:21, pyproject.toml:54).
- Residual from validation, now resolved: the stale index (`flexicon_api_v4.6.0.json` lacked `FromOpenProject`). The shipped index is `flexicon_api_v4.11.0.json`, which lists it.
- Not re-verified: test counts (39 flexicon unit, 12 MCP pre-flight) and live evidence contents. These are taken from `validation-t022.md`.

## Follow-ups and open issues
- Write-gate batch on the MCP branch (not a bridge task; `STATUS.md:1659`):
  - Commit `23ff2c8` fixed two `certify_script_readonly` bypasses. Step 2b deduplicated calls by line, and annotated or walrus facade bindings were missed. Test: `tests/test_cycle2_step2b_finding_a_b.py`.
  - The comment/string-stripping false positives were filed as #133, which is now CLOSED.
- Cleanup left on the dev machine: the `Sena3 Bridge Scratch` project and the `D:\Apps\FlexTools\FlexTools\Modules\BridgeGate\` gate modules.
