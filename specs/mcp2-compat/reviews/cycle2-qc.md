# Cycle 2 — QC review of the 2.9.1 release diff

> Authored by the lex-qc agent (read-only role, no Write tool); transcribed to
> this path verbatim by the main session.

**Date:** 2026-08-10
**Quality Score:** 91/100
**Status:** PASS (with two P1 follow-ups recommended, non-blocking)

## Pattern-Audit Gate
- Sweep present in commit body: N/A — none of this cycle's new commits
  (`885039d`, `536fb58`, `9483bcd`, `0939d52`, `5f85a2c`, `a8294e2`) reference
  `closes #N`/`fixes #N` on a bug-labelled issue; this is a firefighting release
  for a packaging/dependency-version incident, not one of the recognized
  recurring FLEx bug shapes (typed-attribute access on LCM objects, list
  assumptions, role disambiguation, multilingual-string typing).
- Spot-check: N/A. Justification: cycle1-qc's own "Sibling sweep" section already
  performed the equivalent manual audit for the actual defect shape
  (AttributeError laundering via `__getattr__`), checking `kernel.py:38-48` (no
  fix needed) and `_import_helper.py` + ~15 dual-mode import blocks (lower
  severity, correctly deferred to issue draft #3 in `deferred-issues.md`). No new
  sibling sites were introduced by this cycle's edits.
- Gate status: **PASS** (one-off/different bug class, prior sweep already on file).

## Code Quality: 24/25
`src/flextoolsmcp/server/__init__.py:181-197` — the P0/P1 fix matches cycle1-qc's
design essentially verbatim: `try/except` scoped to **only**
`spec.loader.exec_module(_server_module)` (line 182), with
`_server_module_cache = _server_module` (line 197) correctly left *outside* the
try block — not over-catching. `raise ImportError(...) from exc` (lines 192-196)
satisfies B904. `global _server_module_cache, _server_load_error` (line 94)
correctly declares both. Failure-cache short-circuit (lines 121-128) re-raises
`from _server_load_error` without touching `exec_module` again — confirmed by
`test_second_access_after_failure_does_not_re_execute`.

## Standards Compliance: 24/25
`scripts/validate_integrity.py` restructuring (lines 156-195) is clean and
well-commented; degraded-AST-path labeling (lines 268-274,
`_count_tools_from_ast`) and `check_server_tools`'s fallback message (lines
228-234) both now explicitly say "DEGRADED". `flextoolsmcp.server.constants`
import fix (line 405) and `flextoolsmcp.server` (`APIIndex`, `get_index_dir`,
`list_tools`, line 204) confirmed correct — verified via grep that
`server.py:689/809/855` define `server`/`list_tools`/`call_tool`, matching the 3
new `LAZY_IMPORTS` entries (`__init__.py:114-118`).

## Error Handling: 23/25

**P1 — pre-existing, not closed by this cycle's fix (not a regression):**
`scripts/validate_integrity.py:159-160`, `any(err in stderr for err in
import_errors)` scans the **entire** stderr text, not just `last_line` (which the
function already computes at line 161), to decide whether to take the "genuine
third-party dependency, skip" path. If a real, unclassifiable failure's traceback
happens to contain the substring "ImportError"/"ModuleNotFoundError" anywhere
upstream (e.g. inside a "During handling of the above exception" chain, or logged
text), it will be misclassified as a benign missing-dependency skip
(`return True`) instead of hitting the new "unclassified failure -> False" branch
added in this cycle (lines 184-194) — undercutting that branch's stated goal.
Recommend keying the classification off `last_line` only. Not introduced this
cycle (explicitly "preserved exactly" per the programmer's report), so
non-blocking, but worth a follow-up ticket since 5a's stated intent ("fail on
unclassified non-zero exits") isn't fully realized while this gate stays
whole-blob.

**P2 — accepted design tradeoff, flagging for visibility only:**
`_server_load_error` (`__init__.py:82`) has no reset path once set; a
transient/recoverable failure in a long-lived MCP server process would
permanently wedge until process restart. This matches cycle1-qc's explicit design
intent (irreversible side effects from partial exec make retry unsafe regardless)
— correctly implemented as designed, not a defect.

## Best Practices: 24/25
CI workflow changes reviewed for structural correctness: `publish.yml` job
ids/`needs` chain (`build` -> `smoke` -> `publish [build, smoke]`) is consistent;
artifact name `dist` matches between upload/download (lines 46, 66, 105). Smoke
job correctly avoids FieldWorks/pythonnet/network-heavy dependencies at import
time — confirmed via grep that `SentenceTransformer` import is lazy
(`server.py:214-215`, only on first search) and `clr.AddReference` in
`versioning.py:100-101` is inside a try/except-guarded function, never at module
scope — so `list_tools()` (which only builds `Tool` objects from static
`TOOL_DEFINITIONS`) is safe to smoke-test on a bare `windows-latest` runner with
no FieldWorks install. `test.yml`'s `--continue-on-collection-errors` does not
mask failures (pytest still exits non-zero on collection errors); `test-linux`
job's `needs: test` correctly references the Windows job's id.

Tests (`tests/test_lazy_loader_diagnostics.py`, `tests/test_dependency_bounds.py`)
assert behavior (cause chaining, exec call-count, major-version int,
regex-anchored upper-bound presence) rather than brittle exact-string matches,
per the ask. `KNOWN_UNCAPPED_DEPS` allowlist is present, scoped, and inert
(documentation-only, no assertion references it) — will not break when a new dep
is added, as required. Autouse fixture in `test_lazy_loader_diagnostics.py` is
module-scoped by construction (defined in that file, not conftest), so no
cross-file state leakage into other test files that do real
`flextoolsmcp.server` imports.

Version/CHANGELOG hygiene: `VERSION` = `2.9.1`; grep for `2.9.0` across the repo
shows only legitimate range references (`2.3.1-2.9.0`, changelog section header,
`test_update_check.py` fixture) — no stale current-version strings.
`CHANGELOG.md`'s `## [2.9.1] - 2026-08-10` entry accurately covers all 6 fix
areas plus the new tests.

## Final Assessment
**Overall Score:** 91/100
**Recommendation:** APPROVE — file the one P1 (`check_runtime_import`'s
whole-stderr substring gate) as a small follow-up rather than blocking this
release; it's a pre-existing gap, not a regression.

---
**Reviewed By:** QC Agent

Key files reviewed: `src/flextoolsmcp/server/__init__.py`,
`scripts/validate_integrity.py`, `.github/workflows/publish.yml`,
`.github/workflows/test.yml`, `tests/test_lazy_loader_diagnostics.py`,
`tests/test_dependency_bounds.py`, `VERSION`, `CHANGELOG.md`.
