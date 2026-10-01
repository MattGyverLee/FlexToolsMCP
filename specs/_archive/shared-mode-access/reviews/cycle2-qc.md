# QC Report — CP1 (commit d17105f, closes #92)

**Score:** 75/100 — **Recommendation: FIX ISSUES** (gate block overrides an otherwise clean diff)

## Pattern-Audit Gate — **BLOCK (P0)**

`.git/COMMIT_EDITMSG` (the artifact for this direct-commit workflow) has no "Pattern audit" heading and no "N/A (one-off)" exemption. Issue #92 is `bug`-labelled (`specs/shared-mode-access/SPEC.md:6`) and the bug has a gate-listed recognizable shape: **default-arg semantics** (`undoable=True` silently defaulting into a broken write path). Per the gate rules this requires `/lex-programmer` to run `sweep-pattern` for other LCM-behavior-changing optional kwargs/defaults and paste the sibling list, or explicitly justify a one-off exemption. Neither happened.

## Contract change — not a P0, but the framing needs correction

`execution.py:4186` (`runtime_error_code = execution_result.get("error_type") or "runtime_error"`) only feeds the internal retry-loop tracker (`_attach_assistance_if_loop`/`session_state.record_op_signal`, `execution.py:4189`, `session.py:462-479`) — it never becomes the response's top-level canonical `error_code`. Confirmed: run_module's raw success/failure dict (`execution.py:4188/4193`) is returned verbatim, never routed through `RejectionEnvelope`/`error_response()`, so it carries no `_contract`/`status`/`error_code` at all — only `success`/`error`/`error_type`. This channel was already open-ended pre-fix (`ClassIdConstantError` at `4975`... `execution.py:3975/3997/4042/4213`), so `"ReportedError"` fits the existing pattern. `CHANGELOG.md:5-42` describes the behavior accurately; no `TOOL-CONTRACT.md` row is needed since the closed 16-code set is untouched.

**P2 (pre-existing, out of scope):** `TOOL-CONTRACT.md:13-26` claims all success responses carry `_contract`/`status`/`op_id`, but run_module's raw dict never does — a doc/impl gap that predates this commit.

## Dead code — clean

Verified `admin.py` KEY_* constants all referenced; no leftover `UNDO`/`REDO`/`UNDOABLE` anywhere in `src/` (grep-clean); `dispatch.py`, `tool_definitions.py`, `session.py`, top-level `server.py` all clean. Author's dead-code claims check out.

## New e2e test — genuine regression test

`tests/test_issue92_write_path_e2e.py:135-138`: default `result["success"]=False` (`execution.py:3484`) means the pre-fix `undoable=True` default (forcing `SetGloss` to raise) would leave `success=False` and fail this assertion — real regression coverage, not a tautology. `requires_flex` marker correctly registered (`pytest.ini:8`), consistent with 16 other files.

## P1: weakened test

`tests/test_v1_3_0_upgrade.py:141-154` (`test_operation_history_tracking`) — no code anywhere calls `operations_history.append(...)` (grep-confirmed), so `assertEqual(state.operations_history, [])` is trivially true regardless of whether tracking works. Docstring ("operations can be recorded") overclaims; should exercise real recording or be relabeled as an existence-only smoke check.

---

**Provenance:** produced by the read-only lex-qc agent in cycle 2; written to
disk verbatim by the orchestrator because that agent has no write tool.
