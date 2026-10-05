# exclusive-access-gate: as built

**Status:** Retired 2026-10-04. Merged to main as `8a3339d` (PR #343, 2026-10-02, "refuse WS/CF schema changes while FLEx holds the project"); the four review findings resolved in `6673a65` (PR #360, 2026-10-02). Released in 2.15.0 (#365). Tasks: 48/48 complete. T048 (needs-human) closed 2026-10-04: pyflexicon 4.12.0 ships the `peer-schema-guard` capability (present in `src/flextoolsmcp/index/python/flexicon_api_v4.12.0.json`); PR #364 regenerated the indexes against 4.12.0 and raised the floor to `pyflexicon>=4.12.0,<5`.
**Full docs:** [specs/_archive/exclusive-access-gate/](../_archive/exclusive-access-gate/) (spec, plan, tasks, research, data-model, [contract](../_archive/exclusive-access-gate/contracts/requires_exclusive_access.md), checklists, quickstart, reviews, evidence, [filing ledger](../_archive/exclusive-access-gate/issues/filing-ledger.md)). Not read by default.
**Pinned here:** none (no test or code opens these files at runtime; only docstring citations).
**Scope:** Successor to `shared-mode-access` (#93), carrying forward what it left unbuilt: the CP5 `requires_exclusive_access` gate, the remaining undo/shared-mode doc corrections, `SyncForeignChanges` for write-enabled runs, and the unfiled upstream findings. Programmatic undo is out of scope (separate spec if wanted).
**User docs:** `docs/SHARED-MODE.md` ("Close FLEx for these", "Seeing an MCP change in FLEx", Undo facts), `docs/TOOL-CONTRACT.md` (`requires_exclusive_access` row), `docs/RECOVERY.md` (pre-write backup as the safety net).

## What shipped
- `server/exclusive_access.py`: `EXCLUSIVE_ONLY_OPERATIONS` — one table for the detector, the refusal and the docs (FR-001). `detect_exclusive_only_operations` combines certifier rows for wrapper calls with one AST pass for raw LCM names, receiver-scoped generic methods and schema-property assignments. Untyped-receiver rows match wrapper names by name alone, except `Create`/`Delete` (mutating on ~50 other classes; would refuse ordinary raw-LCM factory writes).
- The gate runs in `handle_run_module` on the final (post-auto-fix) code, before the confirmation gate, the pre-write backup and any subprocess. A write-enabled run whose script contains an exclusive-only operation is refused with `requires_exclusive_access` when the access probe reports `open_shared` or `unknown` (fail closed, FR-006). `open_exclusive` / `held_by_other` keep their existing `project_locked` refusal (FR-007).
- `validate_only`: `project_lock.exclusive_access = {required, operations, blocking}`; `blocking` is true on `unknown` (the real run refuses it, FR-009), null only when the probe raised.
- Conditional `WritingSystems.Ensure()` (FR-002b amendment, maintainer-approved 2026-10-01): refusing every `Ensure()` made users close FieldWorks for no-ops, so two layers decide it. (1) Before the run, the project's active lists (`CurVernWss` / `CurAnalysisWss`) stream from the `.fwdata` — pure filesystem, no project open, ~156 ms on Sena 3's 53 MB file, cached per path on (size, mtime). Literal + active runs; literal + would-add is refused up front (stage: preflight); non-literal or unreadable file defers to layer 2. (2) During the run, flexicon's peer schema guard (capability `"peer-schema-guard"`, flexicon#601) raises `FP_ExclusiveAccessRequiredError` before writing, mapped to `requires_exclusive_access` with `stage: runtime`. The runner's `PEER_SCHEMA_GUARD` line (`off` / `on` / `required`) is patched after the probe; without the guard in the installed flexicon the run fails closed.
- New error code `requires_exclusive_access` (contract 47 -> 48), detail model `RequiresExclusiveAccessDetail`, golden fixture, `TOOL-CONTRACT.md` row. An allowed run carries `exclusive_access` on its success result.
- US2 recovery: a specific assistance hint per refusal; the generic "close FieldWorks and retry" fallback no longer appears for `open_shared` (pattern audit of every "close FieldWorks" string; `write_ladder.py` advisory repointed at the gate).
- US4 doc corrections: "Inspect & Undo" is gone from `workflow-summary.md`; `FLEXTOOLS-STYLE-GUIDE.md` and the `flextools_start` definition no longer claim undo; `SHARED-MODE.md` states the four undo facts (no MCP undo, FLEx opens with an empty undo history, peer writes land non-undoable, programmatic undo not built) with LCM citations; `tests/test_docs_no_undo_claims.py` pins the wording.
- US5: `shared_mode_read_back` notes corrected — the read-back saw the write only because FLEx was idle and had flushed the `.fwdata`; not a guarantee.
- US6: the filing ledger (T032-T035) triaged the predecessor's unfiled findings; all 14 still-new items filed 2026-10-02 with the maintainer's OK (flexicon #602-#608, FlexToolsMCP #347-#350); four flexicon hazards verified already fixed upstream.
- US3: the custom-field hazard proved live (V7): a peer-added CF definition committed while FLEx held the project was silently lost — stronger than research R9's "visible, then gone".
- Live evidence V1-V8 on Sena 3 (evidence/live-gate.md, live drivers and snippets). Tests: `tests/test_exclusive_access_detect.py`, `tests/test_exclusive_access_gate.py`.

## Public contracts (checked against main `e7489b7`)
- `server/exclusive_access.py`: `EXCLUSIVE_ONLY_OPERATIONS` (table rows carry `conditional`, true for `Ensure`); `detect_exclusive_only_operations`; `GATED_VERDICTS`; `PEER_SCHEMA_GUARD_CAPABILITY = "peer-schema-guard"` (:686); `_ACTIVE_WS_CACHE` keyed on (size, mtime_ns); `execution._peer_schema_guard_available` probe.
- Refusal detail (`RequiresExclusiveAccessDetail`, `response_models.py`): `error_code, guidance, verdict, holder_pid, holder_process, operations[{key, category, failure_class, call, line, source}], remedy`, plus `stage` (`preflight` / `runtime`) for conditional `Ensure`.
- `validate_only`: `project_lock.exclusive_access.{required, operations, blocking}`.
- An allowed write-enabled run on a gated verdict carries `exclusive_access` on the success result.
- The gate never fires for reads or value edits (FR-002a); bare snippets are never gated.

## Key decisions
- One table drives the detector, the refusal text and the docs, so they cannot drift (FR-001).
- Fail closed on `unknown`: the probe cannot distinguish "FLEx has it open" from "cannot tell", and guessing wrong destroys data (FR-006, FR-009).
- The `.fwdata` read replaces an earlier LCM-subprocess snapshot at the maintainer's suggestion (~0.5 s vs ~4 s); the `.ldml` store is deliberately not consulted because store-present tags can be inactive.
- A once-per-session cache would refuse from a stale entry after an FLEx save; the cache keys on (size, mtime) so any save forces a fresh read. Unsaved FLEx state is invisible either way — the runtime guard covers it.
- Programmatic undo is out of scope; the pre-write backup is the documented safety net.

## Gotchas and limits
- A runtime (`stage: runtime`) refusal means writes earlier in the script are already saved; only the `Ensure` itself was blocked.
- Open question, unresolved: whether `ProjectSettingsOperations.SetDefaultVernacular` / `SetDefaultAnalysis` belong in the gated list.
- `exclusive_access` on the success result is advisory; the authoritative record is the refusal or the run.

## Divergences from the spec
- FR-002b (conditional `Ensure`) is a 2026-10-01 maintainer-approved amendment, not in the original spec text; the spec file was amended in place.
- The four review findings on PR #343 were resolved on a fresh branch (PR #360) at the maintainer's direction, not on the PR branch.
