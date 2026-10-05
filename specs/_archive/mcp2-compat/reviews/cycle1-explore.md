# Cycle 1 — Explore: why 824 tests + CI are blind to the mcp 2.0 break

> Authored by the Explore agent (read-only role, no Write tool); transcribed to
> this path verbatim by the main session. CI history, the
> `validate_integrity.py` swallow, the dead `src.server` path, and the missing
> `publish.yml` test gate were independently re-verified by the main session —
> see "Main-session verification" at the end.

## (a) A or B? Neither — CI is RED but illegibly so

`gh run list --workflow=test.yml --limit 30` shows only ONE run after mcp 2.0.0
(2026-07-28): run **30712521422** (2026-08-01, dependabot setup-python PR).
Its install log proves the resolution: `Downloading mcp-2.0.0-py3-none-any.whl`
plus `Collecting mcp-types==2.0.0`. The 07-22 baseline (run 29965312704) shows
`Downloading mcp-1.28.1`.

So (A) is closer than (B), but with three twists that explain "nobody noticed":

1. **No green→red transition existed.** CI was *already* red on 07-20, 07-21 and
   07-22 (flaky `test_flextools_health` cache test: `1 failed, 805 passed`). Red
   was the steady state. py3.10 did flip green→red, but invisibly.
2. **The error names the wrong culprit.** Failure is
   `ImportError: cannot import name 'APIIndex' from 'flextoolsmcp.server'` —
   it reads like a refactor/rename bug. `mcp` and `list_tools` appear nowhere.
3. **Only one run in 13 days**, on an unrelated dependabot PR that nobody merged.

## (b) Which layers are blind, and by what mechanism

| Layer | File | Mechanism |
|---|---|---|
| Root cause | `pyproject.toml:33` | `mcp>=1.27.0`, no upper cap. No `uv.lock`/constraints file exists. |
| Traceback erasure | `src/flextoolsmcp/server/__init__.py:152-167` | Lazy `__getattr__` → `spec.loader.exec_module()` raises `AttributeError` at `server.py:808`. CPython's `IMPORT_FROM` converts *any* `AttributeError` escaping `__getattr__` into `ImportError: cannot import name ...`, discarding the real traceback. |
| Integrity Phase 1 | `scripts/validate_integrity.py:141-180` | `check_runtime_import` DOES exec `server.py` and DOES get a non-zero exit — but `import_errors = ("ImportError","ModuleNotFoundError")` excludes `AttributeError`, so the `if any(...)` is False and control falls through to a bare `return True` (line 180). Silently swallowed. |
| Integrity Phase 2 | `scripts/validate_integrity.py:190` | `from src.server import ... list_tools` — invalid path (`src/` has no `__init__.py`; real path is `src.flextoolsmcp.server`). Always fails → always falls back to `_count_tools_from_ast()`, pure AST, imports nothing. CI on 08-01 printed `deps not installed, falling back to AST tool count` → `23 tool definitions found (AST) [OK]`. **Step reported green under mcp 2.0.0.** |
| Test suite | pytest collection | `tests/test_recipes.py:22` and `tests/test_undo_wiring.py:17` do module-level `from ...server import APIIndex` → collection ERROR → `Interrupted: 2 errors during collection` / `21 deselected, 2 errors in 4.58s`. **Zero of 824 tests ran.** |
| The tests that WOULD catch it | `tests/test_mcp_tools.py:40-48`, `tests/test_response_contract.py:376-391` | Both `exec_module()` `server.py` and await `list_tools()` — they *would* surface the real error, but they are invoked inside test bodies, so the collection abort kills the run before they execute. Coverage exists; it is simply never reached. |
| Publish path | `.github/workflows/publish.yml` | `build` → `twine check` → `pypa/gh-action-pypi-publish`. **No install of the built wheel, no console-script boot, and no dependency on `test.yml`** (test.yml comments confirm: "Keeps main green without gating releases"). A red test run cannot block a PyPI upload. |

Console script `flextoolsmcp = "flextoolsmcp.server:run"` — `run` is in
`LAZY_IMPORTS`, so every published 2.3.1–2.9.0 dies through the same seam.

## (c) Regression-coverage options

**Option 1 — Import-smoke test that executes the decorators.**
Lives in `tests/test_import_smoke.py`. Asserts `exec_module(server.py)` succeeds
and `len(await list_tools()) >= 23`, at *module scope* so it cannot be silently
deselected. Cost: ~20 lines, ~2s. Catches at **test time**, but only if the
resolved `mcp` is broken in that env — and today it would be masked by the same
collection abort unless the two `test_recipes`/`test_undo_wiring` module-level
imports are made lazy. Must be paired with `--continue-on-collection-errors`
or fixed imports.

**Option 2 — Resolved-dependency version assertion.**
A CI step (or `tests/test_dependency_bounds.py`) asserting
`importlib.metadata.version("mcp")` falls inside a declared, capped range, and
that every runtime dep in `pyproject.toml` has an upper bound. Cost: ~15 lines,
~0s. Catches at **install time** cheaply and names the culprit *explicitly*
("mcp 2.0.0 outside supported <2") — fixing the diagnosability problem, which is
the real failure here. Does not prove the server boots.

**Option 3 — Clean-install wheel + boot job.**
New job in `test.yml` (and a `needs:` gate in `publish.yml`): `python -m build`,
then in a fresh venv `pip install dist/*.whl`, then
`timeout 20 flextoolsmcp --help` / spawn and expect a valid MCP `initialize`
handshake on stdio. Cost: ~25 YAML lines, ~2-3 min per run. Catches at
**install time** and is the only option that reproduces the *user's* failure
(fresh resolution, real console script, no editable-install or `sys.path`
shims from `conftest.py`).

## (d) Ranked recommendation

1. **Option 3 first**, plus wiring `publish.yml` to `needs: test`. It is the only
   layer that would have stopped all 11 bad releases; every other seam is
   defeated by the editable install and the `conftest.py` path shims.
2. **Option 2 second** — near-zero cost, and it converts an illegible
   `cannot import name 'APIIndex'` into an actionable message. Highest
   diagnosability-per-line in the whole list.
3. **Option 1 third** — genuinely valuable, but note the coverage *already
   exists* (`test_mcp_tools.py`); it was defeated by the collection abort. So the
   higher-leverage fix is de-fanging the abort (make `test_recipes.py:22` /
   `test_undo_wiring.py:17` import lazily, add
   `--continue-on-collection-errors`) rather than adding a new test.

**Immediate hotfix, independent of coverage:** cap `mcp>=1.27.0,<2` in
`pyproject.toml:33` and `requirements.txt`, and stop `validate_integrity.py`
from swallowing non-`ImportError` failures (line 180) and from using the dead
`src.server` path (lines 190, 381).

---

## Main-session verification

Independently re-confirmed before accepting this report:

- **CI red history** — `gh run list --workflow=test.yml`: 2026-08-01 runs
  `30712521422` and `30712520448` both `failure`; 07-22 `29965312704` and
  `29965313811` already `failure`; 07-20 had `success` runs earlier the same
  day. Confirms both the post-2.0.0 red AND the pre-existing red that masked it.
- **`check_runtime_import` swallow** — read `scripts/validate_integrity.py`
  lines 141-180. Confirmed: `import_errors = ("ImportError", "ModuleNotFoundError")`;
  when `returncode != 0` and stderr matches neither, control reaches the bare
  `return True` at line 180.
- **Dead `src.server` path** — `src/__init__.py` does **not** exist, so
  `from src.server import ...` at line 190 can never succeed; line 213
  unconditionally falls back to `_count_tools_from_ast()`.
- **No publish gate** — `.github/workflows/publish.yml` declares only
  `needs: build` (line 51). No `needs: test`, no `workflow_run` trigger.
