# Quickstart: validating mcp2-only

Run everything from the repo root on the feature branch. The maintainer's
`uv tool` server env is separate; see "Live server" at the end.

## Prerequisites

- PR-0 has merged to `main` and this branch is rebased onto it
  (`tests/golden/wire/` and `tests/golden/tool_surface.json` exist).
- The repo venv is on the new floors. The venv has no pip:

  ```
  uv pip install -r requirements.txt --python .venv\Scripts\python.exe
  .venv\Scripts\python -c "import importlib.metadata as m; print(m.version('mcp'))"
  ```

  Expect `2.3.0` or later, and below 3.

## CP1 checks

1. **Whole suite, both eras in process**:
   `.venv\Scripts\python -m pytest -q -m "not requires_flex" | tail -20`
   gives a pass, including `tests/test_mcp_registration.py` (legacy and auto)
   and `tests/test_wire_goldens.py` (both eras).
2. **Stdio, real subprocess**:
   `.venv\Scripts\python -m pytest -q -m requires_subprocess | tail -20`
   gives a pass in both eras: handshake, `tools/list`, one read-only call, one
   forced error, no early stdout.
3. **Integrity**: `python scripts/validate_integrity.py server` exits 0
   (USAGE.md tool list vs definitions).
4. **Shim gone**: `git ls-files src/flextoolsmcp/mcp_compat.py` prints
   nothing, and the camelCase guard test passes.
5. **1.x unsatisfiable**: `uv pip compile pyproject.toml --python-version 3.12`
   with an extra `mcp<2` constraint fails to resolve.
6. **Lower bound**: `uv pip compile pyproject.toml --extra dev --resolution
   lowest-direct -o %TEMP%\lowest.txt`, install it into a scratch venv with
   the package `--no-deps`, and run the suite. It passes. This is the CI
   `lowest` cell, run locally.
7. **Wheel smoke**: build the wheel, install it into a fresh venv outside the
   repo, then run the publish workflow's stdio handshake against the
   `flextools-mcp` console script in both eras.
8. **Sena 3 read smoke** (before tagging 3.0.0, never Claude-Swahili):
   `flextools_start` on Sena 3, one `flextools_get_object_api`, one read-only
   `run_module`. Expect the same results as on 2.15.x. Parse tests may rewrite
   the `.fwdata`; that is known.

## CP2 checks

1. Cold session (fresh server): call `nonexistent_tool` and expect
   `unknown_tool` with `isError=true`. Call `flextools_run_module` with
   `{"code": 5}` and expect `invalid_input` with `isError=true`. Then call
   `flextools_health` and expect the session to still be uninitialized.
2. Contract stamp: any response's `_contract` is `tool-responses/1.1`.
3. Parity audit: `.venv\Scripts\python -m pytest -q
   tests/test_validation_parity.py`. Every reported difference has a CHANGELOG
   line.

## Live server (maintainer, after each merge)

1. Stop every client using the server.
2. `uv tool install --editable C:\Github\FlexToolsMCP --with-editable C:\Github\flexicon --reinstall`.
   Don't interrupt it.
3. `flextools_health` reports healthy.
4. Then pull `main`.
