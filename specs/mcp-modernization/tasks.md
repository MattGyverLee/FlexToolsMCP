# Tasks — MCP modernization (issue #369)

Rulings: see `spec.md` (R1–R5). Evidence: `reviews/cycle1-*.md`.
Env: `/tmp/ftmcp-venv` (recreate per AGENTS.md if gone; install
pytest, pytest-asyncio, pydantic, `mcp>=2,<3`, jsonschema, ruff) with
absolute `PYTHONPATH=/home/hatch/workspace/ftmcp-369/src`. One commit per
phase, pushed as gates go green.

## Phase 1 — mcp 2.x-only, retire the shim (R1)
- [x] pyproject.toml + requirements.txt: `mcp>=2,<3`; rewrite the stale
      shim comments; fix "`uvx flextoolsmcp`" comment while there.
- [x] server.py: inline the shim's 2.x branch — `Server(name,
      version=resolve_server_version(), instructions=…, on_list_tools=,
      on_call_tool=)`; adapters wrap list_tools/call_tool; jsonschema
      pre-validation copied **verbatim** from mcp_compat (same error
      shape, same ordering before session-state setup); CallToolResult
      wrap + isError semantics preserved; `annotation_is_read_only`
      simplified to the 2.x spelling with a local helper if still needed.
- [x] Move `resolve_server_version` into server.py (or a small util it
      already imports); delete `src/flextoolsmcp/mcp_compat.py`.
- [x] server/__init__.py: drop mcp_compat import lines/hints.
- [x] kernel.py bare `Server("flextools-mcp")` — verify unchanged under
      2.x (audit says it survives); touch only if a test proves otherwise.
      Note: verified unchanged under mcp 2.x — no commit on this branch touches kernel.py, the bare `Server("flextools-mcp")` construction works under 2.3.0, and the suite passes; no change was needed.
- [x] Tests: rewrite tests/test_mcp_compat.py's 12 portable tests against
      the inlined adapter (drop only the MCP2-flag test); keep
      test_mcp_tools.py:424-448 end-to-end pre-validation test green;
      add a real-construction serverInfo-version test; add a stdio
      server/discover + legacy-initialize smoke test (raw JSON-RPC,
      no client lib — pattern from specs/mcp2-compat PoC if reusable).
- [x] tests/test_dependency_bounds.py: assert the `>=2` floor, not just
      `<3` (current checks would pass a 1.x floor).
- [ ] CI: test.yml matrix floor `1.27.0` → `2.0.0`, comments updated;
      publish.yml: remove the 1.27.0 smoke block.
      Note: not on this branch — the workflow changes are held in ~/workspace/ftmcp-369-workflows.patch and need a workflow-scoped push.
- [x] Gate: full suite (`-m "not requires_flex"`) green under mcp 2.3.0;
      ruff clean; `scripts/validate_integrity.py all` clean.

## Phase 2 — structured output, batch 1 (R2)
- [x] handlers/api.py:392: remove the shadowing local
      `build_response_with_context`; real payloads carry `status` +
      `_contract` per docs/TOOL-CONTRACT.md; regression test on a real
      handler payload.
- [x] response_models.py: tighten GetObjectApiSuccess /
      SearchByCapabilitySuccess with traced always-present keys.
- [x] tests: real-payload fixtures for the 3 batch-1 tools (capture from
      handlers, not invented dicts); validate fixtures against the
      tightened models; delete/replace vacuous cases in
      test_tool_output_model_validation.py.
- [x] server.py list_tools(): advertise outputSchema for batch-1 tools
      only (output_model present AND in the batch-1 set).
- [x] server.py call_tool() + adapter: parse the final text payload
      (post `_session_note` rewrite) into structuredContent; attach via
      CallToolResult; skip when payload is an error (status/error_code);
      assert text bytes unchanged in tests (golden compare).
- [x] Gate: suite green; a spec-compliant client-side jsonschema check
      of structuredContent vs advertised outputSchema passes for all
      three tools (test, not eyeball).

## Phase 3 — progress notifications (R3)
- [x] ProgressReporter module (kernel-style accessor
      `get_progress_reporter()`), ContextVar set/reset in call_tool;
      adapter extracts ctx; `report_progress` via session; no-token ⇒
      no-op; exceptions swallowed inside the reporter.
- [x] C: semantic-search load milestones at server.py `_log_info` sites
      (start / model ready / searching), total=None or 0→1→2 of 3.
- [x] B: run_module heartbeat task (15 s, total=None) around
      `run_script_async`, cancelled in `finally`.
- [x] E: grammar-health scan reuses the B wrapper.
- [x] H: sandbox create/seed step milestones.
- [x] Tests: FakeCtx seam tests (token ⇒ notifications recorded with
      that token; no token/ctx=None ⇒ nothing emitted, results
      identical); raising sink never propagates; milestone-sequence
      test for C with a capturing reporter; existing direct-call suites
      green unchanged.
- [ ] NOT in phase: parse notifications, tasks extension, refresh /
      embeddings progress (R3 — pending Matthew's product call).

## Phase 4 — discovery (R4)
      Note: refresh / embeddings progress is deferred pending Matthew's product decision (the R3 options were put to him 2026-10-11); parse notifications and the tasks extension remain out of scope.
- [x] server.json at repo root (cycle1-registry draft; version = current
      package version); validate locally; add a CI-runnable validation
      test (schema-shape checks offline; full validator manual).
- [x] README.md: `mcp-name: io.github.mattgyverlee/flextoolsmcp`
      ownership comment; `uvx flextools-mcp` fix; refresh warmup
      surfaced; safety-copy contradictions fixed; Windows/FieldWorks
      requirement stated plainly.
- [x] pyproject description ≤100 chars (registry cap) or a registry-only
      description in server.json — pick one, note which.
      Note: outcome — the registry-only route was chosen: server.json carries a 93-char description; pyproject.toml's description was deliberately left unchanged.
- [ ] Publish handoff note in the PR body: exact steps for Matthew
      (name approval, `mcp-publisher login github` or OIDC workflow),
      incl. "needs a PyPI release carrying the mcp-name string first".

## Phase 5 — security hardening (R5)
      Note: pending the PR below; registry publication itself is Matthew-gated — the manifest is on this branch and validated, but publishing is not done by the agent.
- [x] P0 S-P0-1: run_module must not honour manage_config-persisted keys
      that control its confirmation / pre-write-backup ladder — mirror
      filing's refusal (see test_filing_bypass_surface.py pattern);
      tripwire test T9 first (red), then the fix (green).
- [x] Annotation truth table (security §4): fix parse_sandbox
      READ_ONLY_SAFE (S-P1-6) and flextools_start (P2); reconcile every
      row — fix the annotation or the behavior, no silent rows.
- [x] T1–T12 regression tests from security §6 (poisoned description /
      index-entry / recipe fixtures; annotation truth table test;
      description instruction-scan over shipped ToolDefs).
- [x] S-P1-5 fencing: extend "data, never instructions" framing to
      corpus/project-string outputs where the change is small; report
      anything that balloons as a follow-up instead of absorbing it.
      Note: done as framing — the "data, never instructions" framing in the parse_sandbox description is the landed scope. The follow-ups that ballooned live in reviews/cycle1-security.md (S-P1-1, S-P1-4) and are pinned by the 3 xfail(strict) tests in tests/test_tool_poisoning_regression.py.
- [x] Gate: suite green; security report §4 table re-verified row by row.

## Close-out
- [x] lex-verification + lex-qc + lex-synthesis gates on the full diff.
- [ ] PR against main: `closes #369` only if every Acceptance box in
      spec.md is verified; otherwise `refs #369` + checked/unchecked
      boxes reconciled on the issue. Registry publish + refresh-tool
      decision called out as Matthew's remaining actions.
      Note: pending this close-out commit — the PR is not yet open.
- [ ] "Over and out!" on #369 only when the PR is open and
      feature-complete per the acceptance list.

      Note: pending the PR above.
