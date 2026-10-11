# QC Report — MCP modernization (#369), Cycle 2 (code-quality gate)

**Date:** 2026-10-11
**Scope:** `git diff c1c751f..HEAD` on `feat/369-mcp-modernization` (HEAD `b4adb61`),
5 phase commits + spec commit. Read-only review; no code changed.
**Quality Score:** 76/100
**Status:** ISSUES — one P0 blocks merge; one P1 should be fixed or explicitly
ruled on before merge.

Counts: **P0 × 1, P1 × 1, P2 × 8.**
Ruff (run by this reviewer): `ruff check` on every changed, still-existing
Python file, and on all of `src/` — **all checks passed**.
Suites run by this reviewer: `test_tool_poisoning_regression.py`,
`test_structured_output.py`, `test_progress_notifications.py`,
`test_tool_output_model_validation.py`, `test_server_json.py`,
`test_mcp_compat.py` — **79 passed, 3 xfailed** (the 3 xfails verified genuine,
see Test Quality).

---

## P0 — blocks merge

### P0-1 — `run_module` `validate_only` payloads get structuredContent that fails the advertised outputSchema; spec-compliant clients hard-fail the call

- `src/flextoolsmcp/server/handlers/execution.py:3131` (`_handle_validate_only`):
  the payload's status is `"validated"` or `"validation_failed"`, with no
  `error_code` key. This is a long-standing, documented `run_module` mode
  (issue #49), not an edge case.
- `src/flextoolsmcp/server.py:894-922` (`derive_structured_content`): the only
  exclusions are `status == "error"` and `"error_code" in parsed`, so a
  validate-only payload passes through and is attached as `structuredContent`.
- `src/flextoolsmcp/server/response_models.py:99-102` (`RunModuleSuccess`):
  the advertised schema restricts `status` to `Literal["ok", "error"]`.

Verified by this reviewer both ways: `derive_structured_content` attaches the
validate-only payload (status `"validated"`), and jsonschema validation of
that payload against the advertised `RunModuleSuccess` schema fails with
`'validated' is not one of ['ok', 'error']` (same for `'validation_failed'`).
Per the Phase 2 tests' own client model (`test_structured_output.py`,
`_client_validate`, mirroring mcp 2.3.0 `ClientSession.validate_tool_result`),
that mismatch is a hard client-side failure of an otherwise successful tool
call — exactly the trap ruling R2 §5 warned about, reached through a status
vocabulary R2's error check doesn't cover.

Why the suites miss it: `test_structured_output.py`'s run_module success
payload is a single golden (`auto_fix_casting_applied.json`, status `"ok"`),
and `tool_output_validation.capture_real_payloads` captures only the two
doc-search handlers — no validate-only (or discovery-redirect) run_module
shape is ever client-validated.

**Fix direction (any one, first preferred):** (a) validate the derived dict
against the tool's advertised schema inside `derive_structured_content` and
attach nothing on mismatch — this closes the whole class, not just this
status pair; (b) widen `RunModuleSuccess.status` to the full run_module
status vocabulary; (c) exclude non-`ok` statuses in the derivation. Add a
validate-only payload to the client-conformance tests either way.

---

## P1 — should fix

### P1-1 — Phase 5's `parse_sandbox` annotation reclassification silently changes cold-session gate behaviour

- `src/flextoolsmcp/server/tool_definitions.py:837-843`: `flextools_parse_sandbox`
  moves from `READ_ONLY_SAFE` to `readOnlyHint=False` (S-P1-6, correct as an
  annotation — the tool copies projects, writes under `~/.flextoolsmcp/parse/`,
  and spawns external tools).
- But the annotation is load-bearing elsewhere: `src/flextoolsmcp/server.py:1023-1025`
  (`call_tool`) derives the issue-#53 cold-start auto-init from
  `annotation_is_read_only(tool_def.annotations)`, and `flextools_parse_sandbox`
  is **not** in `_SESSION_INDEPENDENT_TOOLS` (`server.py:966`).

Consequence: before this branch, a cold `flextools_parse_sandbox` call (no
prior `flextools_start`) auto-initialized a read-only session and dispatched;
now it returns the `session_not_initialized` error. Nothing in `spec.md` R5 or
`tasks.md` Phase 5 names this behaviour change, and no test in the diff pins
the new cold behaviour (the updated comments in `tests/test_mcp_tools.py`
record the annotation change only). The sibling reclassification,
`flextools_start`, is safe only because it is session-independent by list.

**Fix direction:** decouple the #53 gate from the host-facing annotation
(an explicit per-tool cold-start set), or add `flextools_parse_sandbox` to
the session-independent set if cold use is intended — and pin whichever
behaviour is chosen with a `test_issue53_cold_start.py`-style test. If the
new hard gate is in fact intended, it needs a lead ruling recorded in the
spec, not silence.

---

## P2 — notes

1. **Structured derivation can still raise outside any guard (latent).**
   `src/flextoolsmcp/server.py:911`: `content[0]` is indexed before any
   type check; verified that dict/int `content` raises `KeyError`/`TypeError`.
   The call site (`server.py:1399`, in `make_call_tool_handler`) sits
   *after* the `try/finally` that wraps `call_tool_fn`, so such a raise would
   escape the adapter instead of degrading to a plain result. Production
   `call_tool` always returns a list, so this is latent — but it contradicts
   the module's stated "derivation must never fail a tool call" invariant,
   and P0-1's fix (a) is the natural place to close it.
2. **No schema safety net in the derivation seam.**
   `derive_structured_content` (`server.py:894-922`) attaches any non-error
   JSON dict without validating it against the advertised schema. P0-1 is
   the live instance; any future handler shape drift re-opens it. (Fix
   folded into P0-1 direction (a).)
3. **Shadow removal widens Phase 2's text-byte changes beyond the batch-1 tools.**
   Deleting the local `build_response_with_context` in
   `src/flextoolsmcp/server/handlers/api.py:23,62` (canonical import) fixes
   the R2 §1 shadowing for the doc-search tools, but every other handler in
   that module (`find_examples`, `resolve_property`, `resolve_type`,
   `get_navigation_path`, …) now also gains `_contract` plus the canonical
   stamper's once-per-process `update_notice` / `workspace_notice` /
   ephemeral session notices. That is consistent with issue #54's
   stamp-every-success intent and is probably desirable — but it is a text
   payload change for non-batch-1 tools that R2 §4's "text payload bytes
   must not change" never scopes or acknowledges. Record it in the spec/PR
   body so the byte-identity acceptance box reads honestly.
4. **Progress instrumentation B and half of H have no tests.**
   The `run_module` heartbeat wrappers
   (`src/flextoolsmcp/server/handlers/execution.py:6388,6395`, R3 item B)
   and the sandbox *create* milestones (`handlers/parse/sandbox.py`,
   `_sandbox_create`, R3 item H) are untested; `tests/test_progress_notifications.py`
   covers the grammar-scan heartbeat (E) and sandbox *seed* only. The seam
   tests that exist are real (recording/raising sessions, token matrix), so
   this is a coverage gap, not vacuity — but B is the highest-traffic
   instrumented path.
5. **Semantic-search load rungs 0/1 may never fire in production.**
   `src/flextoolsmcp/server.py:230,239` (`SemanticSearch.load`) is reached
   only via `APIIndex.ensure_semantic_search_loaded` (`server.py:695`),
   which has no caller anywhere in `src/` — true at the diff base too, so
   pre-existing wiring, not a #369 regression. R3 item C's live half is the
   `search()` rungs 2/3 (`server.py:272,281`), which the tests do exercise.
   Either wire the ensure-call or stop counting the load rungs as shipped
   instrumentation.
6. **`report_nowait` tasks are unreferenced.**
   `src/flextoolsmcp/server/progress.py:96`: `loop.create_task(...)` keeps
   no strong reference, so a notification task can in principle be GC'd
   mid-flight (and can outlive the response it describes). Sink exceptions
   are correctly swallowed inside `report()`, so the blast radius is a lost
   advisory notification — but a held reference set is the standard fix.
7. **Vestigial ladder conditional (style/dead code).**
   `src/flextoolsmcp/server/handlers/execution.py:6194`:
   `_require_confirmation = True` followed by `if _require_confirmation and …`
   keeps a branch that can no longer be taken. The S-P0-1 comment explains
   *why* confirmation is unconditional; the code should just say
   `if not args.get("confirmed", False):`. Harmless, but it reads as if a
   config read were still pending.
8. **Two weak tests.**
   `tests/test_tool_poisoning_regression.py:337` (T2): input schemas are
   built from static Pydantic input models that never consult the API
   index, so monkeypatching `api.get_api_index` cannot change them — the
   test cannot fail for the reason its docstring names; it is a pin, not a
   proof. `tests/test_progress_notifications.py:307`
   (`test_heartbeat_noop_reporter_spawns_nothing`) has no assertion; it
   fails only if the wrapper raises. Neither is load-bearing for a ruling,
   but neither should be cited as evidence.

---

## Verified sound (checked, not assumed)

- **Progress never fails a tool, on the real paths.** `ProgressReporter.report`
  (`progress.py`) swallows all sink exceptions; `build_progress_reporter`
  degrades to the no-op reporter on any context surprise; the heartbeat
  task is cancelled in `finally` and its own exceptions are contained.
  The adapter + `call_tool` double set/reset of the ContextVar
  (`server.py:1137` region) is redundant but correctly nested — no leak
  past a call, verified by the adapter seam tests.
- **S-P0-1 ladder fix is complete for `run_module`.** Confirmation is
  unconditional (`execution.py:6194`); both backup call sites pass
  `_ladder_backup_before_write(args)` (`execution.py:6204,6366`), which
  resolves to a non-`None` bool, so neither `write_ladder.backup_intent`'s
  config reader nor `backup.perform_pre_write_backup`'s config fallback is
  ever consulted on this path. The per-call `backup_before_write=False`
  opt-out still works. T9's tests are genuine: one drives the real
  `handle_manage_config` → real config file → real handler path for the
  confirmation rung, and the backup test asserts a real `.fwdata` copy
  lands on disk despite the persisted `false`.
- **The 3 xfail(strict) tests are genuinely strict.** Re-run with
  `--runxfail`, all three fail on their intended assertions, not on setup:
  T3a (`test_tool_poisoning_regression.py:420`, no `data_provenance` on a
  poisoned index payload), T3b (:431, `import_statement == "import os"`
  served unflagged), T5-scrub (:786, `find_scrub_lines` still flags the
  stored local recipe). `strict=True` means a future fix XPASSes and fails
  the suite until the marker is removed — the right shape for the
  S-P1-1 / S-P1-4 follow-ups R5 scoped out.
- **Structured-output tests are otherwise real.** Golden byte-identity is
  compared on the raw text (including a non-canonical-spacing payload that
  would expose any re-serialization), error payloads are checked for *no*
  structuredContent, and client conformance is validated the way the mcp
  2.3.0 client builds its validator. The hole is shape coverage (P0-1),
  not assertion quality.
- **No dead shim code remains.** No `mcp_compat` import or `MCP2` probe
  survives in `src/`; remaining "1.x" mentions are the historical
  `TOOL-CONTRACT 1.x` comment (pre-existing), the FlexLibs template title,
  and `tests/test_mcp_compat.py`, whose docstring honestly records it as
  the ported suite for the inlined adapters (filename is now a misnomer —
  naming debt only). `server/__init__.py`'s stale "compat shim / mcp>=1.27"
  guidance was correctly updated to the 2.x-only wording.
- **Annotation truth table (T8) reconciles.** The frozen 31-tool table in
  `test_tool_poisoning_regression.py` matches `tool_definitions.py` row by
  row, including `manage_config`'s new `destructiveHint=True`. The only
  side effect found is P1-1's gate coupling, not a table error.
- **Style.** New code (`progress.py`, the `server.py` adapters, the
  execution/sandbox Phase 5 blocks) matches the repo's dense,
  issue-referenced comment voice; no clashes found beyond P2-7.
- **`server.json`** matches `VERSION` (2.15.0), carries the pinned
  2025-12-11 schema and the `io.github.mattgyverlee/flextoolsmcp` name per
  R4; publishing remains Matthew-gated as ruled.

## Final Assessment

**Overall Score:** 76/100
**Recommendation:** DO NOT MERGE until P0-1 is fixed (validate-only
`run_module` results currently break spec-compliant clients — a
regression shipped by Phase 2, invisible to its own test suite). P1-1
should be fixed or explicitly ruled on in the spec before merge, since
it changes cold-call behaviour for `parse_sandbox` as a side effect of
an annotation fix. Everything else is P2 notes; Phases 1, 3 (seam), 4,
and the Phase 5 ladder/annotation work itself verified sound, with
ruff clean and the Phase 2/3/5 suites green as run above.
