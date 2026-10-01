# Cycle 8 verification -- issue #93

**Scope note:** neither commit touches an Operations class or an LCM call
directly; both harden the write-path safety gate in front of LCM. No
live-LCM claim is made, and the brief explicitly rescoped Part B away from
a live-LCM re-test. Verdict below is a code/regression audit plus a
live-adjacent (non-LCM) stdlib reproduction, as directed.

## Part A -- static

**A1 diffs (a8cf35b, ee53b11):** read in full; match their reports, with
one discrepancy: mutations report claims "test_script_certification.py
(+7)" but the diff adds exactly 5 new `def test_` functions (21->26,
confirmed via `pytest --collect-only`), not 7. Suite-wide total unaffected.

**A2 full suite:** `1159 passed, 4 skipped` (baseline 1148/4). Delta +11
fully accounted, no drops, no new skips: test_shared_mode_access.py +3,
test_script_certification.py +5, test_issue49_validate_only.py +2,
test_issue55_write_safety_ladder.py +1.

**A3** `scripts/validate_integrity.py`: all 5 checks pass, exit 0.

**A4 focused pass** (7 named files incl. test_startup_lock_sweep.py):
127 passed, 0 failed, 0 skipped.

**A5 `_pid_is_alive` adversarial read -- PASS.** project_access.py:188-225:
`finally: kernel32.CloseHandle(handle)` runs on every path incl. the
`GetExitCodeProcess`-failure branch; `ERROR_ACCESS_DENIED` (214-215) fires
only when `handle` is falsy, never calling `GetExitCodeProcess`; DWORD
out-param uses `ctypes.wintypes.DWORD()` + `ctypes.byref`, not a bare int;
`ctypes.wintypes` import gated `if sys.platform == "win32":` (47-48); POSIX
`os.kill(pid, 0)` (217-225) is byte-identical to pre-fix.

**A6 mutation-detection adversarial read -- PASS, index-authoritative, not
a partial verb fix.** `project.<Accessor>` resolves via Step 1c
(validators.py:3060-3078) against `access_path` index metadata; the
verdict itself is `method.get("is_mutating", False)` (line 3097) -- the
index's own flag, not a widened verb list -- proven by
`test_accessor_mutation_verb_outside_any_regex_list` (AgentOperations.
Duplicate: `is_cud=False`, zero regex overlap, yet
`compute_is_mutating_script` True). Both guarded `SetGloss` and guarded
`CreateField` now produce non-empty `mutations_detected` +
`is_mutating_script: true` (new unit tests + validators.py:3110-3130/
3417-3454 read directly).

**A7 test-intent audit -- PASS.** `test_cud_regex_only_still_flags_mutating`
docstring deliberately rewritten to scope it to the genuine
no-line-aware-source edge case, distinguished from the (a)/(d) guarded
shape (now covered by 2 new tests). Full-range `git diff` on tests shows
zero removed `assert` lines.

## Part B

**B1 -- BLOCKED.** Tried to restart the live MCP server (PID 15852,
`python -m flextoolsmcp`, started 10:39:09, predates both fixes); the
sandbox auto-mode classifier denied `Stop-Process`. Escalating as a
blocker; substituted B2's fresh-process route, immune to server staleness.

**B2 -- reproduced, no FieldWorks needed.** Spawned a throwaway PID
(`Popen -c "pass"`, let it exit), probed byte-identical OLD (`git show
a8cf35b^`) vs NEW `_pid_is_alive` in-process at t=0/5/30s: OLD =
True/True/True (the parent's own `Popen` handle keeps the dead child's
kernel object alive -- the same mechanism as finding (k)'s crash reporter);
NEW = False/False/False at all 3 samples. This route does reproduce the
handle-retention condition.

**B3 -- confirmed from code, caching site named.**
`api_index.startup_lock_warnings` is computed ONCE at server.py:1048-1050
(`sweep_stale_locks()` runs only at startup). `diagnostic_health.py:245`
(`_build_warnings()`) reads that frozen list every call without
recomputing, while `verbose.project_access` (diagnostic_health.py:296)
calls `probe_project_access()` fresh every call -- genuinely different
freshness paths, confirmed. Also `validators.py:221`
(`validate_server_state()`, run every `run_module` preflight) reads the
SAME frozen attribute, so CP2/CP3's warnings share this stale cache too.
Item G is NOT fixed by either reviewed commit; remains open.

## Overall

**PASS** for both commits (a8cf35b, ee53b11) as static/regression changes.
Blocker: B1 needs elevated permission/human to restart the server. Open,
unaddressed: B3/Item G (server.py:1048-1050 / diagnostic_health.py:245) --
recommend a follow-up fix, not a gate here.
