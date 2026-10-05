# Cycle 2 Verification Report: mcp 2.0 compat fix set

Date: 2026-08-10
Verifier: Verification Agent
Scope: Empirical proof that the guards added in cycle2-programmer.md actually
fire, not just that a green test run exists (11 prior releases shipped broken
against green checks).

## Result table

| # | Item | Status |
|---|------|--------|
| 1 | Baseline pytest + ruff | PASS |
| 2 | validate_integrity.py all - runtime not AST | PASS |
| 3 | Negative test - guard fires on real mcp 2.0.0 defect | PASS |
| 4 | Loader diagnostics end-to-end (real traceback + __cause__) | PASS |
| 5 | list_tools importable, returns >=10 tools | PASS |
| 6 | publish.yml gating + wheel-install smoke, executed for real | PASS |
| 7 | git clean / no tag / nothing pushed | PASS (minor caveat, see below) |
| 8 | Dep range resolves to mcp 1.29.0, no conflicts | PASS |
| 9 | 22 vs 23 tool-count discrepancy | RESOLVED - not a P0, root cause found |

No P0 found. No guard failed to fire.

## 1. Baseline

```
python -m pytest -q -m "not requires_flex" --continue-on-collection-errors
830 passed, 2 skipped, 21 deselected

python -m pytest -q   (unfiltered, per literal task wording)
851 passed, 2 skipped

ruff check .
All checks passed!
```
Matches programmer's reported 824(baseline)+6(new)=830 exactly. No regressions.
Status: PASS

## 2. validate_integrity.py all

```
[3/5] Checking server...
Checking server.py tool count...
Phase 1: Runtime import check (server.py, refresh.py)...
Phase 2: Functional checks...
  server.py: 22 tools registered (runtime) [OK]
```
Prints "(runtime)", not "(AST)". Full "all" run: all 5 phases OK, flexicon
contract 43/43 Operations, 0/0 exceptions. Status: PASS

## 3. Negative test - does the guard actually fire?

Built a real venv (not a simulation) at D:/tmp/mcp2_test_venv, installed the
actual defective dependency mcp==2.0.0. Confirmed the removed API directly:

```
>>> from mcp.server import Server; s = Server('x')
>>> hasattr(s,'list_tools'), hasattr(s,'call_tool')
False False
```

Ran the repo's own check_runtime_import/check_server_tools logic (i.e. ran
scripts/validate_integrity.py server with that venv's python.exe, which is
exactly what sys.executable resolves to inside the check):

```
$ D:/tmp/mcp2_test_venv/Scripts/python.exe scripts/validate_integrity.py server
RUNTIME ERROR: src/flextoolsmcp/server.py (MCP server) exited 1 with an unrecognized (non-Import) error:
Traceback (most recent call last):
  File "<string>", line 1, in <module>
  File "src/flextoolsmcp/server.py", line 808, in <module>
    @server.list_tools()
     ^^^^^^^^^^^^^^^^^
AttributeError: 'Server' object has no attribute 'list_tools'
Checking server.py tool count...
Phase 1: Runtime import check (server.py, refresh.py)...
Phase 2: Functional checks...
  server.py: runtime import/execution failed, falling back to AST tool count -- DEGRADED CHECK, does not verify server.py actually imports/runs
  (runtime import stderr: ModuleNotFoundError: No module named 'flextoolsmcp')
  server.py + tool_definitions.py: 23 tool definitions found (AST, DEGRADED -- runtime import check failed, this does NOT prove server.py imports/runs) [OK]

EXIT CODE: 1
```
Non-zero exit (1), RUNTIME ERROR block printed, AST fallback explicitly
labeled DEGRADED. Guard fires correctly.

Contrast with pre-fix code, to prove this is a real fix and not coincidental:
extracted scripts/validate_integrity.py as of commit 994793e (immediately
before the fix, 9483bcd), patched only the unrelated dead src.server import
path so the specific fall-through bug under test was isolated, and ran it
against the same mcp==2.0.0 venv:

```
$ D:/tmp/mcp2_test_venv/Scripts/python.exe validate_integrity_OLD.py server
Checking server.py tool count...
Phase 1: Runtime import check (server.py, refresh.py)...
Phase 2: Functional checks...
  server.py: deps not installed, falling back to AST tool count
  server.py + tool_definitions.py: 23 tool definitions found (AST) [OK]
OLD SCRIPT EXIT CODE: 0
```
Pre-fix code returns exit 0 / [OK] against the exact same AttributeError that
mcp 2.0.0 produces -- this is empirical proof of the actual defect that
shipped in 2.3.1-2.9.0, and proof the new code closes it (exit 1 now vs exit 0
before, same input). Status: PASS

## 4. Loader diagnostics end-to-end

Triggered the real failure (mcp==2.0.0 venv, real repo, real
flextoolsmcp.server.__getattr__ code path, no monkeypatching):

```
=== TOP-LEVEL EXCEPTION ===
ImportError: flextoolsmcp.server lazy-load of 'list_tools' failed: server.py raised AttributeError while executing (NOT a missing-attribute error). See chained cause below.

=== __cause__ ===
AttributeError: 'Server' object has no attribute 'list_tools'

=== full traceback (from traceback.print_exc()) ===
Traceback (most recent call last):
  File ".../server/__init__.py", line 182, in __getattr__
    spec.loader.exec_module(_server_module)
  File "<frozen importlib._bootstrap_external>", line 995, in exec_module
  File "<frozen importlib._bootstrap>", line 488, in _call_with_frames_removed
  File ".../server.py", line 808, in <module>
    @server.list_tools()
     ^^^^^^^^^^^^^^^^^
AttributeError: 'Server' object has no attribute 'list_tools'

The above exception was the direct cause of the following exception:
...
ImportError: flextoolsmcp.server lazy-load of 'list_tools' failed: server.py raised AttributeError ...
```
Message names AttributeError explicitly and states "NOT a missing-attribute
error" -- this is not a bare "cannot import name". __cause__ is the real
AttributeError, chain intact.

Second-access (failure-cache) check, same process, two consecutive accesses:
```
attempt 0: ImportError - flextoolsmcp.server lazy-load of 'list_tools' failed: server.py raised Attribute...
attempt 1: ImportError - flextoolsmcp.server lazy-load of 'list_tools' failed previously and will not be...
```
Confirms server.py is not re-executed on the second failed access (P1 fix).
Status: PASS

## 5. list_tools importable, >=10 tools (healthy env, mcp 1.27.0 installed)

```
>>> import asyncio; from flextoolsmcp.server import list_tools
>>> len(asyncio.run(list_tools()))
22
```
22 >= 10. Status: PASS

## 6. publish.yml static check + real executed smoke

Static check of .github/workflows/publish.yml:
- publish job: needs: [build, smoke] (line 92). Confirmed.
- smoke job: needs: build, runs-on: windows-latest, no actions/checkout step
  anywhere in the job (only download-artifact + setup-python + venv steps) --
  so no repo checkout, no conftest.py in scope.
- Wheel install: smoke-venv\Scripts\python.exe -m pip install $wheel.FullName
  -- installs the built .whl path directly, not -e .
- Smoke command runs from $RUNNER_TEMP/flextools-smoke (outside
  $GITHUB_WORKSPACE), invoking:
  import asyncio; from flextoolsmcp.server import APIIndex, list_tools;
  ts = asyncio.run(list_tools()); ...
  -- exercises the exact lazy-loader/decorator-registration seam that broke.

Actually executed (could not run GitHub Actions itself, so reproduced the
smoke job's exact command locally): built a real wheel via python -m build
(outdir D:/tmp/smoke_dist, produced flextools_mcp-2.9.1-py3-none-any.whl),
created a fresh venv at D:/tmp/smoke_venv, installed only the wheel
(non-editable), then ran the literal smoke command from D:/tmp/flextools-smoke
(outside the repo checkout):

```
$ cd D:/tmp/flextools-smoke
$ D:/tmp/smoke_venv/Scripts/python.exe -c "import asyncio; from flextoolsmcp.server import APIIndex, list_tools; ts = asyncio.run(list_tools()); print(len(ts)); assert len(ts) >= 10"
22
SMOKE EXIT CODE: 0
```
Passes end to end against a real wheel in a real fresh venv. Status: PASS

## 7. Release-safety check

```
git tag --list "v2.9*"        -> v2.9.0   (no v2.9.1 tag created)
git log origin/main..main     -> 7 commits ahead, all local (nothing pushed)
git status                    -> clean except 2 untracked docs:
                                    specs/mcp2-compat/reviews/cycle2-programmer.md
                                    specs/mcp2-compat/dual-support-analysis.md
```
Both untracked files are review/analysis markdown in specs/mcp2-compat/ (the
artifact this review itself consumes, plus a second analysis doc that
appeared mid-session, presumably from concurrent crew activity) -- not code,
not staged, not committed, and not something this verification pass created
or should delete. Working tree for all tracked source/config files is clean.
Status: PASS (caveat noted, non-blocking)

## 8. Dependency range resolution

```
pip index versions mcp
  Available versions: 2.0.0, 1.29.0, 1.28.1, ...
  INSTALLED: 1.27.0   LATEST: 2.0.0

pip install --dry-run --upgrade "mcp>=1.27.0,<2"
  Using cached mcp-1.29.0-py3-none-any.whl.metadata
  Would install mcp-1.29.0
```
(Plain --dry-run without --upgrade reported "already satisfied" for the
1.27.0 already installed in this environment; --upgrade was required to force
pip to show its actual resolution target within the cap -- both prove the
range excludes 2.0.0 and resolves cleanly, no conflicts reported.)
Status: PASS

## 9. 22 vs 23 tool-count discrepancy - investigated, resolved, NOT a P0

Runtime (22) is correct. AST (23) is a heuristic artifact. No tool is missing.

tool_definitions.py's TOOLS dict has exactly 22 ToolDef(...) entries (counted
directly: grep -c 'ToolDef(' = 22, cross-checked by listing all
name="flextools_..." occurrences = 22 distinct names). The live
asyncio.run(list_tools()) result (Section 5) returns exactly those same 22
names, 1:1, with no extras and no omissions:

```
flextools_find_examples, flextools_find_wrappers_for_lcm,
flextools_get_module_template, flextools_get_navigation_path,
flextools_get_object_api, flextools_get_operation_logs,
flextools_get_session_history, flextools_get_wrapper_dependencies,
flextools_health, flextools_list_categories,
flextools_list_entities_in_category, flextools_list_projects,
flextools_list_skeletons, flextools_manage_config, flextools_prepare_report,
flextools_resolve_property, flextools_resolve_type, flextools_run_module,
flextools_search_by_capability, flextools_start, flextools_start_module,
flextools_undo_last_operation
```

Root cause of the AST's "23": _count_tools_from_ast() in
scripts/validate_integrity.py sums (a) the count of Tool(...) call syntax
occurrences in server.py -- there is exactly one, at server.py line 836
(tools.append(Tool(**kwargs))), which sits inside a
"for tool_def in TOOL_DEFINITIONS.values(): ..." loop (server.py lines
817-836) -- plus (b) the count of ToolDef(...) occurrences in
tool_definitions.py (22). Sum: 1 + 22 = 23. The heuristic conflates one
source-level call site executed 22 times at runtime with "one additional
tool," double-counting the loop body against the dict it iterates. This
loop-based, data-driven architecture (for tool_def in
TOOL_DEFINITIONS.values()) predates this cycle entirely (git log -p traces it
to before 994793e, last touched by 994793e/9443d3e/41d4461, none of which are
cycle-2 commits) -- the discrepancy is pre-existing and was not introduced by
this fix, matching the programmer's claim.

This is a latent bug in a fallback-only, DEGRADED code path (fires only when
the real runtime check has already failed), and cycle2's own fix already
neutralizes the risk by labeling that path's output "(AST, DEGRADED ...)"
instead of implying it's authoritative. MIN_TOOL_COUNT=10 means both 22 and 23
pass either way, so it did not mask a real regression in this release.

Recommendation (non-blocking, follow-up): fix _count_tools_from_ast() to not
add the server.py-side Tool(...) call-site count when tool_definitions.py is
present and countable -- it should be an either/or (prefer counting ToolDef
entries alone), not an additive sum, to avoid this kind of off-by-one
recurring the next time someone reads the AST number as ground truth. Not
filed as a GitHub issue by this verification pass; flagging for the next
deferred-issues sweep.

Status: RESOLVED, not a P0.

## Cleanup performed

Local build/, dist/, src/flextools_mcp.egg-info/ produced by the wheel build
for item 6 were removed after verification (gitignored regardless, but
removed for tidiness). Scratch venvs (D:/tmp/mcp2_test_venv,
D:/tmp/smoke_venv) and scratch dirs (D:/tmp/smoke_dist,
D:/tmp/flextools-smoke) left in place under D:/tmp per session scratch
conventions; not part of the repo.

## Final assessment

Overall status: PASS. Every guard added in cycle2 was independently
reproduced against the real historical defect (mcp==2.0.0 installed for real,
not simulated) and demonstrably fires: validate_integrity.py now exits
non-zero where it previously exited 0 on the identical input, the lazy-loader
raises a diagnosable chained exception instead of a laundered "cannot import
name", list_tools is reachable and returns the full tool set, and the publish
workflow's smoke job -- reproduced by hand against a real wheel in a real
fresh venv -- passes. The one open question flagged by the main session
(tool-count delta) is fully explained, traced to a pre-existing AST-heuristic
double-count bug in a DEGRADED-labeled fallback path, and does not indicate a
missing tool at runtime.

Recommendation: APPROVE.

---
Verified By: Verification Agent
Date: 2026-08-10
