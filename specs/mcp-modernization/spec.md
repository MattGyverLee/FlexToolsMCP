# Spec — MCP modernization (issue #369)

Branch: `feat/369-mcp-modernization` · Base: `origin/main c1c751f`
Cycle 1 evidence: `reviews/cycle1-{protocol,codebase,structured,longops,security,registry}.md`

## Lead rulings (2026-10-11, /lex-lead, Cycle 1 synthesis)

### R1 — Phase 1 shape: A (low-level Server, 2.x-only). Issue text corrected.
#369 prescribes `from mcp.server import MCPServer` with `on_list_tools=` /
`on_call_tool=` handlers. Verified against installed mcp 2.3.0 by two
independent audits: `MCPServer` is the renamed FastMCP framework
(`mcp/server/fastmcp.py` tombstone) and takes **no** such kwargs; they belong
to the low-level `mcp.server.Server`, whose `run()` serves both protocol
eras via `serve_dual_era_loop` and registers `server/discover`
unconditionally. **Phase 1 = raise floor to `mcp>=2,<3`, inline the shim's
2.x branch into `server.py`, delete `mcp_compat.py`.** MCPServer adoption
is a framework migration — out of scope for #369 (its own non-goals argue
against it); it may be proposed as a separate future phase.
- The shim's jsonschema pre-validation survives **verbatim, inlined**:
  2.3.0's `get_tool_input_schema=` is HTTP-transport-only, the runner never
  validates per-tool inputSchema on stdio, and pre-validation ordering
  (before session-state setup) is load-bearing for the cold-session gate.
- Pin: `mcp>=2,<3`. `<3` mandatory (announced 3.0 removals); no feature
  justifies a `>=2.1` floor.

### R2 — Phase 2 batch 1 + preconditions
Advertise `outputSchema` + return `structuredContent` for exactly:
`flextools_run_module`, `flextools_search_by_capability`,
`flextools_get_object_api`. Preconditions, in order:
1. Fix the `handlers/api.py:392` shadowing: its local
   `build_response_with_context` shadows the stamping version, so real
   doc-search payloads carry neither `status` nor `_contract`,
   contradicting `docs/TOOL-CONTRACT.md`.
2. Tighten the two shell Success models (`GetObjectApiSuccess`,
   `SearchByCapabilitySuccess` currently add zero fields over
   `BaseEnvelope`; `extra="ignore"` + all-defaults ⇒ any object validates)
   with the always-present keys traced from real handler payloads.
3. Replace the vacuous validation tests (invented payloads, keys handlers
   never emit, a parametrized test that never validates its own payload)
   with real-payload fixtures.
4. Plumbing: handlers and `json_response` untouched; derive the structured
   dict by parsing the **final** text payload in `server.call_tool`
   (after the `_session_note` rewrite) and attach it in the 2.x adapter.
   Text payload bytes must not change. Never `model_dump()` the envelope
   (drops real payload keys).
5. Error path: attach **no** structuredContent when the payload has
   `status=="error"` / `error_code` (Success schemas currently admit
   `"error"` in the status enum — a trap once models tighten). A union
   `anyOf[Success, RejectionEnvelope]` schema is a post-Phase-2 option.
Batch 2 (models to author, not in this issue's critical path — do if cheap,
else leave as follow-up list in the PR): resolve_property, find_examples,
get_navigation_path, resolve_type (after fixing its non-envelope
`{error:…}` branch), catalog/list_recipes tools. Parse family, start,
health: deferred (shape-variant/stateful).

### R3 — Phase 3 progress scope; Tasks DECLINED
- Seam: extract ctx in the (post-Phase-1, in-server.py) 2.x adapter; build a
  `ProgressReporter` in a `ContextVar` set/reset by `call_tool` around
  dispatch; no-op when no `_meta.progressToken`; all reporter exceptions
  swallowed (filing-claim precedent). Zero handler signature changes.
  Mechanism: `await ctx.session.report_progress(p, total, message)`.
- Instrument, in order: (C) semantic-search model load milestones at the
  existing `_log_info` sites; (B) `run_module` elapsed heartbeat (15 s,
  `total=None`) around `run_script_async`; (E) grammar-health scan via the
  same wrapper; (H) sandbox create/seed per-step milestones.
- Skip: parse runs (domain progress via RunRecord/polling already exceeds
  notifications; the request token is dead after the 5 s grace window).
- **Tasks extension: DECLINED** (both protocol and longops audits concur:
  types-only in 2.3.0, "never dispatched", no server handler registration,
  zero client support; parse already has a richer in-domain task system;
  process death would vaporize a generic registry). Revisit triggers:
  refresh/embeddings become tool-invoked >10 min ops; a supported client
  hard-caps tool calls below 300 s losing run_module results; SDK ships
  task handlers; a second detach-worthy op that doesn't fit the parse shape.
- Refresh/embeddings progress: **deferred pending Matthew's product call**
  (no request exists to attach a token to — refresh is startup/CLI-only;
  embeddings aren't in the refresh pipeline at all). Options put to
  Matthew 2026-10-11: (i) new `flextools_refresh_indexes` tool;
  (ii) document progress N/A for refresh; (iii) wire embeddings into
  refresh first, then decide. Phases C/B/E/H proceed regardless.

### R4 — Phase 4 discovery
- `server.json` at repo root per cycle1-registry draft (schema 2025-12-11,
  name `io.github.mattgyverlee/flextoolsmcp`, PyPI package block,
  `runtimeHint: uvx`). Validate locally (`mcp-publisher validate` or
  check-jsonschema against the pinned schema URL).
- README/pyproject fixes from the registry audit: `uvx flextools-mcp`
  (the "`uvx flextoolsmcp` works" claim is false), add the
  `mcp-name: io.github.mattgyverlee/flextoolsmcp` ownership string to
  README (lands in the next PyPI release's description — a registry
  publish cannot succeed before a release carrying it), surface
  `flextools-mcp-refresh`, fix contradictory safety copy, keep the
  registry description ≤100 chars (pyproject's is 112).
- **Publish itself is Matthew-gated**: immutable name approval + either
  his `mcp-publisher login github` or merging an `id-token: write`
  workflow for `login github-oidc`. Agent delivers everything up to that
  step and verifies the listing after if he publishes.

### R5 — Phase 5 security scope
Cycle 1 audit: P0×1, P1×6, P2×6; no hidden directives in any shipped
description/instruction/recipe (19 instruction-like passages quoted, all
first-party guidance). In scope for this branch:
- **P0 S-P0-1 fix**: `flextools_manage_config` can persist the very keys
  that control `run_module`'s confirmation and pre-write-backup rungs, with
  no confirmation, annotated non-destructive. Filing already refuses to
  honour that key (`test_filing_bypass_surface.py`); `run_module` must
  get the equivalent protection — config-set ladder keys must not weaken
  run_module's gates.
- Annotation truth fixes: `parse_sandbox` is `READ_ONLY_SAFE` despite
  copying projects, writing under `~/.flextoolsmcp/parse/`, spawning
  external tools (S-P1-6); `flextools_start` annotation vs session/
  `write_enabled` mutation (P2). The annotation truth table (security
  report §4) is the checklist; fix or explicitly reclassify each row.
- Regression suite T1–T12 (security report §6), all offline,
  `not requires_flex`; **T9 config-ladder tripwire is the priority test**.
- Cheap fencing win if it doesn't balloon: extend parse_sandbox's
  "data, never instructions" framing to other corpus/project-string
  outputs (S-P1-5). Anything that balloons (e.g. build-time instruction
  scan of all index content, S-P1-1) is reported as a follow-up, not
  silently absorbed.

## Acceptance (from #369, as corrected by R1)
- [ ] `mcp>=2,<3` in pyproject + requirements; `mcp_compat.py` deleted;
      no 1.x code path remains (CI matrix floor cell becomes 2.0.0).
      Note: branch state — the `mcp>=2,<3` floor, the mcp_compat.py deletion, and the removal of every 1.x code path have landed; only the CI matrix floor cell (2.0.0) is outstanding, held in ~/workspace/ftmcp-369-workflows.patch pending a workflow-scoped push.
- [x] New-era (server/discover) and legacy-era (initialize) clients both
      connect and list/call tools — stdio smoke evidence in the PR.
- [x] Structured output advertised on batch-1 tools; text payloads
      byte-identical; error payloads carry no structuredContent.
- [x] Progress notifications emitted for C/B/E/H ops when a client
      supplies a progressToken; byte-identical behavior without one.
- [ ] `server.json` valid + README accurate; publish step handed to
      Matthew with exact instructions (not done by the agent).
      Note: branch state — server.json is valid and the README is accurate; the publish handoff to Matthew rides the pending PR, and registry publication is Matthew-gated (not done by the agent).
- [x] Security: P0 fixed, annotation truth table reconciled, T1–T12
      regression tests in CI.
- [x] Full suite green in the /tmp/ftmcp-venv (mcp 2.3.0) and ruff clean.
