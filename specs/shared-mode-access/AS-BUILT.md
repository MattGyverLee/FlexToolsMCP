# Shared-mode access (#93): as built

**Status:** Retired 2026-09-30 **INCOMPLETE, by user decision**: #93 is being closed and the remaining work moves to `specs/exclusive-access-gate/` (branch `feat/exclusive-access-gate`). Shipped across PR #114 (merge `ae73eef`, 2026-09-07), direct-to-main commits through 2026-09-08, and PR #274 (merge `3bd8ddf`, 2026-09-26). There was no `tasks.md`; tasks were inline in the spec (CP1-CP6). Gate 2 (all tasks done) is NOT met: CP5 is unimplemented.
**Full docs:** [specs/_archive/shared-mode-access/](../_archive/shared-mode-access/) (spec.md, reviews, evidence, `.crew-handoff.json`, `issues/DRAFT-issues.md`). Not read by default.
**Pinned here:** none (`tests/test_issue128_spec_md_case.py` falls back to the archive's `spec.md`).
**User-facing doc:** [docs/SHARED-MODE.md](../../docs/SHARED-MODE.md).

## What shipped
- CP1 (#92, closed): write path fixed (`undoable=False` hardcoded at the generated `OpenProject`); `flextools_undo_last_operation`, `undo_subprocess.py` and the undo stacks deleted; success no longer reported over `report.Error`.
- CP2: pure-filesystem access probe; stale-lock sweep; `flextools_health(verbose=True)` `project_access` block.
- CP3: lock diagnosis names the holder and verdict-specific remedy. Signed off live 2026-09-08.
- CP4: probe-driven write gate; only `open_exclusive` and `held_by_other` refuse. Signed off live 2026-09-08.
- CP6 (mostly, `3bd8ddf`/#274): docs/SHARED-MODE.md, workflow-detail.md, RECOVERY.md, CHANGELOG, `check_project_locked` renamed `find_lock_file`.

## Public contracts (checked at origin/main db66f11)
- `server/project_access.py`: `probe_project_access(name) -> ProjectAccess(project_name, verdict, sharing_enabled, holder, lock_age_seconds, probed=True)`; `LockHolder(pid, process_name, timestamp_ticks)`; `read_lock_holder`, `_pid_is_alive`, `is_project_sharing_enabled`, `build_access_remedy`, `build_lock_diagnosis`.
- Verdicts: `free`, `open_shared`, `open_exclusive`, `stale_lock`, `held_by_other`, `unknown` (`unknown`/`probed=False` when the projects dir cannot be resolved; #118).
- `server/write_ladder.py`: `probe_write_access(name) -> AccessDecision` (:130), `PEER_BACKUP_CAVEAT` (:79). free/open_shared/stale_lock/unknown proceed (shared gets an advisory); `unknown` proceeds for `run_module` while filing refuses with `project_drive_unavailable`.
- `server/project_discovery.py`: `find_lock_file` (:312), `sweep_stale_locks() -> list[str]` (:455), detection only, never deletes.
- `handlers/execution.py`: `_diagnose_project_open_error` (:1223, calls the probe). `response_models.py:396` `ProjectLockedDetail` (extra=forbid): `error_code, guidance, lock_file_path, verdict, sharing_enabled, holder_pid, holder_process, remedy`.
- `handlers/diagnostic_health.py:624` `_build_project_access_block`.
- Tests: `test_shared_mode_access.py`, `test_shared_mode_lock_diagnosis.py`, `test_shared_mode_write_gate.py`, `test_startup_lock_sweep.py`.

## Key decisions
- Probe is filesystem-only and never opens the project, so it is safe before confirmation.
- Stale lock proceeds: LCM treats it as acquirable.
- `build_access_remedy` not widened for stale_lock; separate `build_lock_diagnosis` instead.
- Fail-open probe (#118): `probed` flag plus `unknown` verdict landed.
- Undo deleted, not repaired: it never worked across sessions.

## Gotchas and limits
- Writing-system changes by a peer crash FLEx 9.3.10 (`NullReferenceException`, `WritingSystemListHandler.AddWritingSystemList`); both legs reach disk; nothing refuses it.
- Custom-field create already refuses in flexicon (`FP_TransactionError`).
- FLEx shows peer writes only after navigating away and back, not F5 (#96 docs point). `FLExProject.SyncForeignChanges()` (flexicon#292) is unused; the `shared_mode_read_back` note in `handlers/admin.py:285` calls that path untested.
- Undo (user note): FLEx starts with a fresh undo history on open, so its UI cannot undo anything done while it was closed. With the UI open it is unknown whether peer writes populate (or should populate) the metadata Undo needs. Programmatic undo via LCM may be feasible; never built.
- Related open issue #315 (project_locked by an unkillable python PID, maybe the idle parse worker).

## Divergences from the spec
- Spec tracking says #118, #119, #104, #105 are open: all CLOSED on GitHub (verified 2026-09-30). #93 closed at retirement.
- Spec and docs cite uppercase `SPEC.md`; the file is `spec.md` (#128). Inbound references in docs/SHARED-MODE.md, STATUS.md and code comments were repointed to the archive at retirement.
- `.spec-context.json` says CP5 scoped only, docs missing; superseded by `.crew-handoff.json` and #274.
- `requires_exclusive_access` exists only in docs/SHARED-MODE.md:75 prose, not in code.

## NOT shipped: carried to the new spec
- **CP5 `requires_exclusive_access` gate**: deliberately open. Interim policy (2026-09-08): writing-system AND custom-field operations are assumed exclusive-only, unenforced. CP5-a acceptance test withdrawn as invalid. Class B (silently lost) writes never observed; Class C (`crashes_holder`) is the proven one. Operation tables: archived spec section 3.
- Stale undo text: docs/workflow-summary.md (Stage 6 "Inspect & Undo", `flextools_undo_last_operation`, lines 16, 170-211) and docs/FLEXTOOLS-STYLE-GUIDE.md:688-693 ("Undoable by default").
- Four unfiled upstream flexicon issues: ConflictingSave modal, BeginUndoTask arity, `_transaction_depth` leak, RollbackToMark.
- Unfiled drafts: archive `issues/DRAFT-issues.md` (nothing filed; needs user sign-off).
- Deferred P2-4: unreadable-PID branch of `build_lock_diagnosis` untested. P2-8: flat (CP3) vs `shared_mode`-namespaced (CP4) payload drift.
