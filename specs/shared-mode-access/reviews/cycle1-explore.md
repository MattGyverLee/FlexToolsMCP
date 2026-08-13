# Cycle 1 Explore — Undo Removal Map

Line numbers verified against the working tree at cycle 1. Where the approved
plan's line numbers had drifted, the ACTUAL numbers are given and the drift is
flagged. Four plan claims were refuted outright — see the callouts.

## 1. Generated-script OpenProject + UNDOABLE template var (execution.py)
- `execution.py:2480-2481` — `undoable = session_state.is_undoable() and write_enabled` — **edit/delete** (drop var; see §6).
- `execution.py:3505` — `project.OpenProject(..., undoable=UNDOABLE)` — **edit** (drop kwarg). CONFIRMED.
- `execution.py:3696` — `UNDOABLE = {undoable}` in `full_script` — **delete**. CONFIRMED.
- `execution.py:3703` — `undoable=repr(undoable)` format arg — **delete**. CONFIRMED.

## 2. `undoable` session flag + plumbing
- `session.py:134` field decl; `session.py:286` (kwarg allowlist), `303-304` (setter), `314` (mode_info log), `422` (`summary()` key), `396-403` `is_undoable()` — all **delete/edit**.
- `session.py:117` `OperationRecord.undoable`; `695` export key — **delete** (part of §5).
- `admin.py:309` comment "Used for write_enabled and undoable" — **edit**.
- `admin.py:423-444` — inheritance/default block. CONFIRMED at those lines — **delete**.
- `admin.py:466` `undoable=undoable` into session init; `484` log line — **edit**.
- `admin.py:539-551` warnings — **delete** (see §4).
- `models.py:69-83` `undoable` Field on `FlexToolsStartInput` — **delete**.
- `tool_definitions.py:113-120` "Undoable mode" paragraph in flextools_start description — **delete**.
- `kernel.py` — NO `undoable` hits. **Plan claim REFUTED**; kernel needs no change.
- `dispatch.py` — no `undoable` flag references (only the tool).
- `validators.py:94, 2227` — `BeginNonUndoableTask` static-analysis rule, unrelated — **keep**.

## 3. `flextools_undo_last_operation` end to end
- `tool_definitions.py:27` import; `416-439` ToolDef (CONFIRMED, entry closes at 439) — **delete**.
- `dispatch.py:19` import, `47` const, `90` list entry, `120`, `160`, `199`, `225` lazy-handler wiring, `258` routing table — all **delete**. `258` CONFIRMED.
- `models.py:120-129` `UndoLastOperationInput` — CONFIRMED — **delete**.
- `admin.py:683-784` `handle_undo_last_operation` — CONFIRMED — **delete**. Also key consts `admin.py:93,96,101,105,107` and header comment `admin.py:10`.
- `src/flextoolsmcp/server/undo_subprocess.py` (199 lines, whole file) — **delete**.
- `handlers/__init__.py:11` docstring mention only (no export symbol) — **edit**. Plan's "handlers/__init__ exports" is **REFUTED** — there is no `handle_undo_last_operation` export there.
- `server/__init__.py:26` re-exports `UndoLastOperationInput` — **delete**.

## 4. False undo claims
- `admin.py:539-546` "can reverse them across MCP sessions" — plan said 534-541; **ACTUAL 539-546 (DRIFT)** — **delete**.
- `admin.py:547-551` coerced-to-False warning — **delete**.
- `admin.py:647-680` `handle_get_session_history`; `650-651` can_undo/can_redo; `669-670` `undo_available`/`redo_available`; `675-676` next_steps — plan said 647-680, CONFIRMED — **edit** (strip undo/redo fields).
- `admin.py:94` `KEY_REDO_AVAILABLE`, `93` `KEY_UNDO_AVAILABLE` — **delete**.
- `tool_definitions.py:388-390`, `models.py:113` get_session_history descriptions — **edit**.

## 5. Dead Feature-3 machinery (session.py)
- `session.py:428-518` (plan said 430-518; block header at 428) — `record_operation` 430-478, `can_undo` 480-482, `can_redo` 484-486, `pop_undo` 488-502, `pop_redo` 504-518 — **delete**.
- Fields `session.py:151` `undo_stack`, `152` `redo_stack` — **delete**. `149` header comment.
- `session.py:588-592` history summary keys (`undoable_count`, `can_undo`, `can_redo`, `undo_stack_depth`, `redo_stack_depth`) — **edit**.
- **Call sites — CONFIRMED, `SessionState.record_operation` is never called from production.** Only hits: `execution.py:4039` `tracker.record_operation(...)` which is `kernel.py:575` — a DIFFERENT class/signature (`code, success, error_msg, error_type`) — **keep**. Test-only call: `tests/test_v1_3_0_upgrade.py:156-166`. `pop_undo`/`pop_redo`/`can_redo` have ZERO call sites anywhere. `can_undo` only at `admin.py:650,675` and `session.py:496,589`.

## 6. undo_checkpoints + lcm_undoable_action_count
- `session.py:19-21` `_UNDO_CHECKPOINT_CAP`, `154-171` `undo_checkpoints` field + comments — **delete**.
- `execution.py:4119-4143` checkpoint append + rollover WARN — plan said 4123-4143; the guard `if write_enabled and undoable:` is at **4123**, comment starts 4119 — **delete**.
- `admin.py:697, 770-782` checkpoint pop — deleted with §3.
- `execution.py:3632-3643` `lcm_undoable_action_count` — CONFIRMED at 3641; this is a read-only diagnostic read of `ActionHandlerAccessor.UndoableActionCount` gated on `WRITE_ENABLED` only, independent of `undoable` — **KEEP**.

## 7. Test references
- `tests/test_undo_wiring.py` (216 lines, whole file; imports at :19) — **delete**.
- `tests/test_mcp_tools.py:85` (EXPECTED_TOOL_NAMES), `:120` (DESTRUCTIVE_TOOLS) — **delete**. `:93` `EXPECTED_TOOL_COUNT = len(EXPECTED_TOOL_NAMES)` is DERIVED, and `:142-145` `test_tool_count` compares against it — **keep, no drift risk** (contradicts the "count assertion will break" worry).
- `tests/test_v1_3_0_upgrade.py:150-166` — **delete** that block.
- `tests/test_issue55_write_safety_ladder.py:4,8-9,58-94` — Rung 1 class `TestRung1UndoableDefault` (61-94) — **delete**.
- `tests/test_issue10_session_persistence.py:173-174` — **edit** (drop `undoable` key + user_provided entry); `:122` comment ref — **edit**.

## 8. Golden/contract surface
- `tests/make_golden.py` `GOLDEN_FIXTURES` (:105) and `AUTO_FIX_GOLDEN_FIXTURES` (:31) — **no** undo/session_history keys. `tests/test_response_contract.py` — zero matches. All 19 fixtures in `tests/golden/responses/` are error-code/auto-fix shapes. **No fixture regeneration needed. Plan concern REFUTED.**

## 9. Docs
- `README.md:151` — **delete** line; `:150` — **edit**.
- `USAGE.md:17-18` — plan said `:228`; **ACTUAL 17-18 (DRIFT)** — **delete** :18, **edit** :17.
- `CLAUDE.md:59` "Safety-first" bullet contains NO undo claim — **keep. Plan claim REFUTED.**
- `docs/workflow-detail.md:327, 347, 389, 408, 415, 417-418, 420-427, 471, 535-540` — plan said 420-427 only; there are 3 more blocks — **edit/delete**.
- `docs/workflow-summary.md:16, 137, 170, 178-179, 184, 187, 189, 211` — **edit/delete**.
- `docs/FLEXTOOLS-STYLE-GUIDE.md:505-510` — **delete**.
- `docs/INNOVATIONS.md:301` (roadmap wish) — **keep/optional**.
- SVGs with undo text: `docs/workflow-detail-4-execute-iterate.svg`, `-6-cross-cutting.svg`, `workflow-map*.svg` — **edit** (regen).
- `CHANGELOG.md`, `HISTORY.md`, `docs/archive/UPGRADES.md`, `IMPLEMENTATION_PLAN.md` — historical — **keep**.

## 10. report.Error collection / success emission
- `execution.py:629-668` `_log_report_messages` — `:663-664` is the ERROR branch. **Keep** (edit target for later gating).
- `execution.py:3646-3653` (in-subprocess template) — `result["success"] = True` set unconditionally, then `summary.error_count` from `report.messageCounts[SimpleReporter.ERROR]` — **the root of unconditional success**.
- `execution.py:4045` `error_count = summary.get("error_count", 0)`; `4056` `report_messages`.
- `execution.py:4111-4118` `if execution_result.get("success"): _log_operation_end_success(...)` — the caller to make conditional.
- `execution.py:671-699` `_log_operation_end_success`, with `:696 logger.info("[OK] Operation completed successfully")` — CONFIRMED.
- Failure counterpart: `execution.py:784` (`include_info=True`), `:810`, and `:4189-4190`.

---

**Provenance:** produced by the read-only Explore agent in cycle 1; written to
disk by the orchestrator because that agent has no write tool.
