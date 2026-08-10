# Cycle 2 — Programmer: mcp 2.0 cap, loader diagnostics, validate_integrity fixes, publish gate

Implements the fix designed in cycle1 (explore/programmer/qc reports in this
same directory). All work landed as commits on `main`; nothing pushed, no
tags created.

## Step 0 — Branch

`fix/82-writeability-reject-logging` had exactly one commit ahead of the then
`main`: `31c53bb fix(#82): return unprotected_mutations_detected guidance,
not opaque AttributeError`. `git checkout main && git merge --ff-only
fix/82-writeability-reject-logging` was a true fast-forward (confirmed via
`git log --oneline -2` showing `31c53bb` directly on top of `994793e`, no
merge commit). All subsequent work is commits on `main`.

## Step 1 — Cap mcp

- `pyproject.toml:33` (dependencies list): `"mcp>=1.27.0"` →
  `"mcp>=1.27.0,<2"`, with a 3-line comment above it citing the removed
  decorator API and the deferred-port issue.
- `requirements.txt:2`: `mcp>=1.27.0` → `mcp>=1.27.0,<2`, same comment
  pattern (3 lines above the pin, under the existing "1.27.0+ required for
  anyio compatibility" comment).

## Step 2/3 — P0/P1 lazy-loader diagnostics (`src/flextoolsmcp/server/__init__.py`)

- Added `_server_load_error = None` module global (line ~82), declared in
  the `global _server_module_cache, _server_load_error` statement inside
  `__getattr__` (line ~94).
- At the top of the `if name in LAZY_IMPORTS:` block (before the
  `_server_module_cache is None` check), added: if `_server_load_error is
  not None`, immediately `raise ImportError(...) from _server_load_error`
  without touching `spec_from_file_location`/`exec_module` again.
- Wrapped `spec.loader.exec_module(_server_module)` in
  `try/except Exception as exc:`, setting `_server_load_error = exc` and
  raising `ImportError(f"...{type(exc).__name__} while executing (NOT a
  missing-attribute error)...") from exc`. Matches the QC report's proposed
  fix verbatim (message text, `from exc` chaining, catching `Exception` not
  just `AttributeError`).

## Step 4 — `list_tools` reachability

Added `'server'`, `'list_tools'`, `'call_tool'` to the `LAZY_IMPORTS` set
(server.py:689 `Server` instance, server.py:809 `list_tools`, server.py:855
`call_tool` — all confirmed present via grep before editing). This was the
gap all three cycle-1 reports missed; without it, `from flextoolsmcp.server
import list_tools` raised `ImportError: cannot import name 'list_tools'`
even on a perfectly healthy `server.py`, and no runtime check could ever
reach the decorator-registration seam that broke under mcp 2.0.

## Step 5 — `scripts/validate_integrity.py`

- **5a** `check_runtime_import` (lines ~156-186 post-edit): restructured so
  a non-zero exit whose stderr contains neither `ImportError` nor
  `ModuleNotFoundError` now prints `RUNTIME ERROR: ... unrecognized
  (non-Import) error` and `return False`, instead of falling through to the
  bare `return True`. The existing deliberate skip-and-return-True path for
  genuine third-party dependency `ImportError`/`ModuleNotFoundError` (local
  module / relative import detection unchanged) is preserved exactly.
- **5b** `check_server_tools` (line 189): `from src.server import
  APIIndex, get_index_dir, list_tools` → `from flextoolsmcp.server import
  APIIndex, get_index_dir, list_tools`. Also fixed the sibling dead import
  at (old) line 390 inside `check_flexicon_contract`: `from
  src.server.constants import NON_ENUMERABLE_OPERATIONS` →
  `from flextoolsmcp.server.constants import NON_ENUMERABLE_OPERATIONS`.
  Both `src.server*` paths could never resolve (no `src/__init__.py`) and
  silently degraded to fallbacks their entire life.
- AST fallback path (`_count_tools_from_ast`) message changed from
  `"N tool definitions found (AST) [OK]"` to `"N tool definitions found
  (AST, DEGRADED -- runtime import check failed, this does NOT prove
  server.py imports/runs) [OK]"` so it can't be mistaken for a real check
  again. `check_server_tools`'s own fallback-trigger print was similarly
  upgraded to name the failure explicitly and echo the last stderr line.

### validate_integrity.py before/after

Before (baseline run, captured after steps 1-4 were already applied but
before step 5's fix — i.e. this reproduces the exact bug the fix targets):

```
[3/5] Checking server...
Checking server.py tool count...
Phase 1: Runtime import check (server.py, refresh.py)...
Phase 2: Functional checks...
  server.py: deps not installed, falling back to AST tool count
  server.py + tool_definitions.py: 23 tool definitions found (AST) [OK]
```

After:

```
[3/5] Checking server...
Checking server.py tool count...
Phase 1: Runtime import check (server.py, refresh.py)...
Phase 2: Functional checks...
  server.py: 22 tools registered (runtime) [OK]
```

Note: the runtime count (22) differs by one from the old AST count (23);
`MIN_TOOL_COUNT=10` so both pass, and the discrepancy is pre-existing
between the AST heuristic (counts `Tool(...)`/`ToolDef(...)` constructor
calls) and the real `list_tools()` return value, not something introduced
by this fix — the whole point of this step was to stop trusting the AST
number as ground truth. Full `validate_integrity.py all` after all changes:
all 5 phases `[OK]`, flexicon contract check passed (43/43 Operations,
0/0 exceptions).

## Step 6 — Publish smoke gate

`.github/workflows/publish.yml`: added a `smoke` job (`needs: build`,
`runs-on: windows-latest`) between `build` and `publish`. It downloads the
`dist` artifact, creates a fresh venv via `python -m venv`, `pip install`s
the built `.whl` directly (not editable, no repo checkout at all — the job
has no `actions/checkout` step), then runs the `list_tools()` smoke command
from `$RUNNER_TEMP/flextools-smoke` (outside `$GITHUB_WORKSPACE`) via an
explicit path to the venv's `python.exe`. Changed `publish`'s `needs` from
`build` to `[build, smoke]`. Added a comment block explaining why
(`twine check` gap, 2.3.1-2.9.0 all shipped un-importable).

## Step 7 — Tests

- `tests/test_lazy_loader_diagnostics.py` (3 tests): monkeypatches
  `importlib.util.spec_from_file_location` to wrap the real loader with a
  `_FakeLoader` whose `exec_module` raises `AttributeError` and counts
  invocations.
  - `test_exec_module_failure_is_diagnosed_not_laundered`: asserts the
    raised `ImportError` message contains "NOT a missing-attribute error"
    and `excinfo.value.__cause__` is the original `AttributeError`.
  - `test_second_access_after_failure_does_not_re_execute`: asserts
    `_FakeLoader.call_count` stays at 1 across two failed accesses
    (`APIIndex` then `main`), locking in the P1 failure-cache behavior.
  - `test_list_tools_is_importable_from_flextoolsmcp_server`: imports
    `list_tools`, `call_tool`, `server` from `flextoolsmcp.server` and
    asserts callability/non-None.
  - An `autouse` fixture resets `fts_server._server_module_cache` /
    `_server_load_error` before and after every test so the real
    module-level singleton isn't left poisoned for other test files.
- `tests/test_dependency_bounds.py` (3 tests): `mcp` major-version check
  (fails by name: `"mcp X outside supported range >=1.27.0,<2 -- the
  low-level Server decorator API was removed in 2.0.0"`), a
  `pyproject.toml` regex check for `<2` in the `mcp` dependency string
  (had to target `"mcp(>=?[^"]*)"` specifically — a naive `"mcp([^"]*)"`
  regex false-matched the bare `"mcp"` entry in the `keywords` list first),
  and the same check against `requirements.txt`. `KNOWN_UNCAPPED_DEPS`
  allowlist is present per the scope limit but currently unused by any
  assertion (no general "all deps capped" check was added, as instructed).

Ruff flagged both new-test files: `B009` (`getattr(x, "const")` →
`x.const`) fixed by switching to attribute access, then `B018` (useless
expression) on the resulting bare attribute-access statements inside
`with pytest.raises(...):` blocks, fixed by assigning to `_`. Final `ruff
check .` is clean.

## Step 8 — Deferred issues

`specs/mcp2-compat/deferred-issues.md`: 4 draft issues (mcp 2.0 port with
the full per-symbol table copied from cycle1-programmer.md; uncapped-dep
bounds + lockfile; exception chaining in the ~15 dual-mode import
fallbacks; extending the smoke job to a full stdio `initialize` handshake).
Not filed — `gh issue create` was not run.

## Step 9 — CI collection resilience

`.github/workflows/test.yml`: added `--continue-on-collection-errors` to
both the Windows coverage pytest invocation and the Linux smoke pytest
invocation, each with a rationale comment. Did not touch
`tests/test_recipes.py` or `tests/test_undo_wiring.py`.

## Step 10 — Release prep (not published)

- `VERSION`: `2.9.0` → `2.9.1`. Grepped for other `2.9.0` occurrences:
  `specs/mcp2-compat/deferred-issues.md` and `cycle1-explore.md` reference
  the *range* `2.3.1-2.9.0` (correct, left alone); `tests/test_update_check.py`
  has an unrelated version-comparison test fixture `("2.10.0", "2.9.0",
  True)` (correct, left alone). `pyproject.toml` reads `version = { file =
  "VERSION" }` and `src/flextoolsmcp/__init__.py` reads
  `importlib.metadata.version("flextools-mcp")` — neither hardcodes a
  version string, so `VERSION` was the only file needing an edit.
- `CHANGELOG.md`: inserted a new `## [2.9.1] - 2026-08-10` section (above
  the pre-existing `## [2.9.0]` entry, below a now-empty `## [Unreleased]`)
  covering the cap, loader diagnostics, both validate_integrity fixes, and
  the publish smoke gate, stating plainly that 2.3.1-2.9.0 are broken
  against mcp 2.0.0. Left the existing `#82` "Fixed" section (already
  present under the old `## [Unreleased]` heading) in place as part of the
  same 2.9.1 release, since `31c53bb` is included in this release too.
- `git add specs/mcp2-compat/` committed separately (see commit log below).
- Did not `git push`, did not create/push a tag.

## Test counts

Before this cycle's work (baseline, run at the very start after the
fast-forward merge, matching the task's stated 824/2): not independently
re-verified in isolation before edits began (edits to `server/__init__.py`
were made before the first full-suite run in this session), but the final
count is exactly baseline + 6 new tests, consistent with no regressions:

- `pytest -q -m "not requires_flex" --continue-on-collection-errors`:
  **830 passed, 2 skipped, 21 deselected** (baseline 824 + 6 new tests in
  `test_lazy_loader_diagnostics.py` (3) and `test_dependency_bounds.py` (3)).

## Ruff

`ruff check .` → **All checks passed!** (after fixing B009/B018 in the two
new test files, described in Step 7 above).

## git log on main (top of history, most recent first)

```
a8294e2 release: 2.9.1 -- fix mcp 2.0.0 install breakage (2.3.1-2.9.0 affected)
5f85a2c docs: commit mcp2-compat review trail + draft deferred issues
0939d52 ci: gate publish on wheel-install smoke test + tolerate collection errors
9483bcd fix: validate_integrity.py tool-count check was AST-only for its entire life
536fb58 fix: stop laundering lazy server-loader failures into misleading ImportErrors
885039d fix: cap mcp dependency to <2 -- mcp 2.0.0 removed decorator API
31c53bb fix(#82): return unprotected_mutations_detected guidance, not opaque AttributeError
994793e release: 2.9.0 -- refresh always scans all APIs + flextools-mcp-refresh warmup
```

`git status` at end of session: `nothing to commit, working tree clean`,
`main` is 7 commits ahead of `origin/main` (not pushed).

## Deviations / things not done exactly as specified

- The `smoke` job in `publish.yml` was written but **could not be executed
  in this session** (no CI runner access; this is a local dev environment).
  It is syntactically reviewed but not dry-run against an actual PyPI-style
  wheel build + fresh Windows venv in CI. Recommend a maintainer trigger a
  `workflow_dispatch` run (the workflow already supports it) before the
  next real tag push, to confirm the job passes end-to-end.
- `CHANGELOG.md`'s new 2.9.1 section folds in the pre-existing `#82`
  changelog entry (previously sitting under `## [Unreleased]`) into the
  same release, since `31c53bb` ships in 2.9.1 too. This wasn't explicitly
  called out in the instructions but seemed correct given #82 was already
  merged and unreleased at the start of this task; flagging it in case a
  different changelog structure (e.g. a separate 2.9.1 entry for #82 alone)
  was intended.
- Everything else in the instructions (steps 0-9, and the parts of step 10
  that don't touch publishing) was completed as specified, including the
  explicit non-actions: no port to mcp 2.0, no `gh issue create`, no
  `git push`, no tag creation.
