# Implementation plan: issue #369, modernizing FlexToolsMCP for MCP spec 2026-07-28 and mcp 2.x (revised after critiques)

Release placeholders: **R1** is the release that drops mcp 1.x. It is 2.16.0 if Q13 picks a minor bump, or 3.0.0 if it picks a major. R2, R3 and later are the releases after it. Q13 must be answered before PR-B1 merges.

## 0. Corrections to the issue

1. **Phase 1 names the wrong class.**
   - `MCPServer` (`from mcp.server import MCPServer`) is the old FastMCP decorator framework. Its constructor has no `on_list_tools=` or `on_call_tool=`. Tools are registered with `@tool`/`add_tool`, and schemas come from function signatures.
   - Moving to it would mean rewriting about 31 tools and losing the schemas we generate from Pydantic. It also goes against `docs/TODO.md:40-44` ("Do NOT migrate to FastMCP") and the issue's own non-goal.
   - **The right target is the low-level `mcp.server.Server`**: `Server(name, version="", instructions=, on_list_tools=, on_call_tool=)`. `mcp_compat.build_server()` already uses it on 2.x.
   - The handler signatures differ from the issue. Handlers take `(ctx, params)` and return a full `ListToolsResult`, or a `CallToolResult | InputRequiredResult`. Thin adapters are still needed.
2. **"Delete mcp_compat.py and keep its notes as tests" is not enough.** The mcp 2.3.0 SDK does not provide three of its behaviors, so they must stay as production code:
   - **(a) Input validation before the cold-session gate.**
     - The low-level Server does no `inputSchema` validation. Verified: an argument with an extra key reached the handler.
     - `get_tool_input_schema` is used only for HTTP `Mcp-Param` headers (`lowlevel/server.py:431-437`).
     - Today the shim returns `isError=True` with the text "Input validation error: ..." (`mcp_compat.py:279-295`).
   - **(b) Exceptions that escape `call_tool` must become `isError` results.**
     - Handler exceptions are already caught inside `call_tool` (`server.py:1049-1070`). They return the documented `internal_error` envelope, which includes `traceback` (TOOL-CONTRACT.md:114, `InternalErrorDetail` at `response_models.py:182-188`).
     - Only code before and after dispatch can escape: `session_state.configure`, `get_tool_handler`, the logger, and the `_session_note` rewrite. The telemetry hook already swallows its own errors (`server.py:1117-1126`).
     - What escapes becomes a JSON-RPC error. On legacy connections that is code `0` with message `str(exc)` (`jsonrpc_dispatcher.py:775-777`). On modern connections it is `-32603` (`runner.py:534-548`).
     - Note: `error_response` does **no** sanitizing, so tracebacks already reach the model through `internal_error`. That existing exposure is handled in Phase 5 (Q15). It is not a reason for this adapter.
   - **(c) Wrapping `list[TextContent]` in `CallToolResult`.**
3. **Dual-era negotiation and `server/discover` already work.**
   - `Server.run()` uses `serve_dual_era_loop`. Verified on 2.3.0 with the current shim:
     - `Client(mode='auto')` negotiates 2026-07-28.
     - `mode='legacy'` negotiates 2025-11-25.
     - An mcp 1.30 `ClientSession` connects over stdio.
   - So the deliverable is **tests plus a stdio handshake that CI requires**, not protocol code.
   - In-process `Client(server, mode='auto')` goes through `DirectDispatcher`, **not** through the modern branch of `serve_dual_era_loop`. Only a subprocess test exercises the real modern stdio path.
4. **"CI matrix covers both" needs redefining.**
   - Today the matrix is over mcp **library versions** (1.27.0 vs latest). It must become a matrix over **client protocol eras**: legacy and auto in-process, plus a required stdio subprocess cell for each.
   - The `mcp==1.27.0` downgrade steps go away: `test.yml:94-96` (axis at `:80`) and `publish.yml:104-108`.
   - Clients that negotiate 2024-11-05 or 2025-03-26 get text only. The per-version serializer drops `outputSchema` and `structuredContent` (`mcp_types/methods.py:641-655`).
5. **The version range is hard-coded in many places.**
   - Where it appears:
     - `pyproject.toml:33-36`, `requirements.txt:1-5` (comment at `:1`)
     - `tests/conftest.py:46-99`, `tests/test_dependency_bounds.py`
     - `server/__init__.py:204-231` and its test `tests/test_lazy_loader_diagnostics.py:42-104`
     - `scripts/cap_canary.py:6` (already stale at `<2`)
     - `RELEASING.md:54`, `docs/TODO.md:27`
     - workflow comments at `test.yml:3-10,74-80` and `publish.yml:25,60-68`
     - `.claude/mcp-init-profile.md:44`
     - `specs/mcp2-compat/*`
   - Co-dependency floors move with it:
     - `pydantic>=2.12`
     - `anyio>=4.9` (`>=4.10` on Python 3.14)
   - New transitive dependencies: `httpx2`, `mcp-types`, `opentelemetry-api`.
   - `pywin32` is **not** new: mcp 1.30 already requires `>=310` (`>=311` on 3.14).
   - mcp 2.x drops `httpx`, `httpx-sse`, `pydantic-settings` and `websockets` from its own requirements. The repo imports `httpx` directly (`update_check.py`), so we keep our own pin. The only direct `jsonschema` import is in `mcp_compat.py`; `tool_output_validation.py` and the tests get it transitively. Declaring it explicitly is Q16.
6. **Phase 2 assumes the models and envelope are ready. They are not.**
   - The three `*Success` models (`server/response_models.py:67-156`) are placeholders. Nothing is required, the `status` enum includes `'error'`, and everything validates.
   - The doc-search tools emit **neither `status` nor `_contract`**. `handlers/api.py:392` shadows `src/flextoolsmcp/response_utils.build_response_with_context`.
   - Even the shared builder (`response_utils.py:146-175`) only does `setdefault("_contract")` and **never stamps `status`**.
   - Every tool error goes out with `isError=false`. Some error payloads have no `status` at all, only a top-level `error` (for example `catalog.py:247-248`).
   - Only 3 tools have an `output_model`.
   - TOOL-CONTRACT.md:23-25 says success models use `extra="ignore"`.
   - `_contract` and `_session_note` start with an underscore, so Pydantic treats them as private and leaves them out of schemas unless they are aliased.
7. **Phase 3's targets can't carry progress.**
   - Index refresh runs in `main()` before stdio opens (`server.py:1165` vs `:1265`). Embedding builds are CLI-only.
   - `parse_text` batch is already submit-then-poll.
   - The calls that really block are `run_module`, `grammar_health`, and `try_word` in `bound_seconds` mode.
   - The first semantic search **blocks the event loop** (`api.py:1413`). That is a correctness bug in its own right.
   - **Tasks:** mcp-types 2.3.0 ships the experimental 2025-11-25 task *types* (`_types.py:346-639`), and `mcp.server.extension.Extension` can register custom methods. There is **no SDK-managed task runtime**, so defer it.
8. **The Phase 4 registry name is invalid.**
   - `io.github.mattgyverlee.flextoolsmcp` has no `/`, and the OIDC namespace match is case-sensitive.
   - Use `io.github.MattGyverLee/<name>` (Q7).
   - Ownership is checked against the PyPI README of the exact version listed (`mcp-name:` marker). Entries can't be renamed or deleted.
9. **Phase 5 can't test model behavior.** The server runs no LLM, so acceptance has to be stated as server-side invariants.
   - The realistic attack surfaces are:
     - `.fwdata` content echoed back
     - the persistent local-recipe/skeleton store
     - `flextools_manage_config`, which can turn off confirmation and backups, is annotated non-destructive, and can redirect reports
     - tracebacks in `internal_error`
   - **Elicitation is era-dependent, not impossible.** Legacy connections support `ctx.session.elicit`. 2026-07-28 connections raise `NoBackChannelError` for server-initiated requests; their replacement is multi-round-trip `InputRequiredResult` returned from `on_call_tool` (`mcp_types/_types.py:2074-2097`).
10. **Latent test bug.** `tests/test_response_contract.py:753` reads `getattr(t,'outputSchema',None)`, which is always `None` on 2.x, so that check always passes.

---

## 1. Sequencing overview

| PR | Content | Depends on | Release | Contract | Size |
|---|---|---|---|---|---|
| **PR-0** | Wire-level goldens and tool-surface snapshot captured on mcp 1.x | none (lands first on main) | none | none | M |
| PR-A | Transports quoting bug and description accuracy | none | next patch | 1.0 | S |
| PR-A2 | `asyncio.to_thread` for the embedding model load/encode | none | next patch | 1.0 | S |
| **PR-B1** | mcp 2.x only, shim retired, behavior verbatim | PR-0, Q13, Q2 | **R1** | 1.0 (no wire change) | M-L |
| PR-B2 | Pydantic-first validation reorder and route-lookup move | PR-B1, Q1 | R2 | 1.1 | M |
| PR-C | README `mcp-name` marker and `server.json` (separate PR, never squashed into B1) | PR-B1 merged, Q7 answered **before merge**, Q17 | R1 or later | none | S |
| PR-D | Registry publish job | PR-C, and a healthy release carrying the marker (Q17) | the gated tag | none | S |
| PR-E | `status`/`_contract` normalization and `is_error` on **hard** errors, with switch | PR-B1, Q18 | R2/R3 | 1.1 (or 1.2) | M |
| Spike | Do clients send `progressToken` and show progress? Validator dialect check | none | none | none | 1 day |
| PR-F | Real models and structured-output pilot (2 tools), default `off` | PR-E | next | +1 minor | M-L |
| PR-F2 | One-line default flip to `pilot` | exit criteria (section 4) | patch | none | XS |
| PR-G | (conditional; see "Decision point after PR-F") `run_module`, then the other read-only tools in batches | PR-F2, and evidence that a client consumes `structuredContent` | later | +1 minor per batch | M each |
| PR-H | Progress heartbeat (only if the spike passes) | PR-B1, spike | any | none | S-M |
| PR-I1 | Lint for the model-visible surface and an index-content lint | PR-0 snapshot | any | none | M |
| PR-I2a/b/c | Least-privilege changes, each flagged (warn by default) | Q10, Q11, Q19 | each own | +1 minor if a new error code | M each |
| PR-I3 | Injection invariants and the "Tool poisoning" section in SECURITY.md | PR-B1 | any | none | M |

**Cross-phase invariants** (umbrella `specs/mcp-modernization/contracts.md`):
- Every wire-visible change bumps the minor `tool-responses/*` version, and the target version is listed for each PR.
- Text payloads change only where a PR's CHANGELOG says so, measured against the PR-0 goldens.
- For any tool that advertises an output schema, every result is either `is_error=True` or carries a dict `structured_content` that passes the schema.

**Speckit:**
- Use the umbrella spec plus full speckit features only where there is contract or behavior risk: `specs/mcp2-only/` (B1+B2), `specs/structured-output/` (E/F/G), and `specs/tool-surface-security/` (I2).
- PR-0, A, A2, C, D, H, I1 and I3 are plain issues/PRs linked from #369.
- Do the work on a feature branch in a worktree (`.claude/worktrees/`). The maintainer's live server runs from an editable install of the main checkout, so a 2.x-only branch checked out there would break the next server restart while the tool env still has mcp 1.30.

**Spec retirement:** `specs/_archive/mcp2-compat/` already exists. Merge `specs/mcp2-compat/{README,deferred-issues}.md` into it (marking drafts 1 and 4 resolved) and add a Companion status note. Don't do a plain move, which would collide.

**Release order:** no phase changes the API indexes. If a refresh lands in the same window, release pyflexicon first and regenerate before tagging.

**CHANGELOG:** every PR gets an entry. B1, B2, E and the I2 PRs carry "Behavior/Breaking" notes.

---

## 2. PR-0: baseline capture (lands first on mcp 1.x)

- Add `scripts/capture_wire_goldens.py`. It goes through the real SDK path (an in-process 1.x client session) and writes `tests/golden/wire/`:
  - `tools/list`, normalized: name, description, annotations, `inputSchema`
  - `tools/call` results (content text and `isError`) for:
    - every tool whose success path runs under `-m "not requires_flex"`: the index-backed and session-independent tools (we can't get success goldens for every tool without FieldWorks)
    - invalid input
    - unknown tool
    - a cold-session non-read-only call
    - a cold-session read-only auto-init
    - an exception injected into `session_state.configure`
  - Normalize volatile fields: timestamps, paths, the update and workspace notices.
- Add `tests/golden/tool_surface.json`: name, description sha256, annotations, and schema hashes. This baseline was moved up from PR-I1.
- Add `tests/test_wire_goldens.py`. It is version-agnostic (it compares the normalized JSON) and reads `CONTRACT_VERSION` instead of the literal `"tool-responses/1.0"`, so later bumps don't mean rewriting 46 files.
- **Acceptance:** green on main with mcp 1.30. The script can be rerun.

---

## 3. PR-B1: mcp 2.x only, `mcp_compat.py` retired, behavior verbatim

**Goal:** the server runs on `mcp>=2.3,<3` through a single registration path on the low-level `Server`. The wire output (text and `is_error`) matches the PR-0 goldens exactly. This is a dependency-only PR, which keeps a revert clean.

### Tasks
1. **Dependencies.**
   - `pyproject.toml:33-36` and `requirements.txt:1-5` become `mcp>=2.3.0,<3`.
   - Set `pydantic>=2.12` and `anyio>=4.9` (with the `>=4.10; python_version>='3.14'` marker if supported) at `pyproject.toml:37,43` and `requirements.txt:6,25`.
   - Keep `httpx>=0.27.1`. Rewrite the comments.
2. **New `src/flextoolsmcp/server/registration.py`:**
   - `resolve_server_version()`, moved from `mcp_compat.py:41-65`. It is still needed because 2.3.0 defaults `version=''`.
   - `build_server(list_tools_fn, call_tool_fn)`, which returns `Server("flextools-mcp", version=..., instructions=SERVER_INSTRUCTIONS, on_list_tools=..., on_call_tool=...)`.
   - `_on_list_tools(ctx, params)` returns `ListToolsResult(tools=await list_tools_fn())`. Pagination is ignored.
   - `_on_call_tool(ctx, params)` works in this order:
     1. **jsonschema pre-validation moved verbatim from `mcp_compat.py:279-295`**, including the schema-provider cache. On failure it returns `CallToolResult(is_error=True, content=[TextContent("Input validation error: ...")])`.
     2. It awaits `call_tool_fn(params.name, params.arguments or {})`. If the result is an `InputRequiredResult` it passes through untouched. Otherwise it is wrapped in `CallToolResult(content=...)`.
     3. An `except Exception` logs the traceback to the operations log and returns `is_error=True` with the shim's **plain text `Error: {exc}`, kept verbatim** (`mcp_compat.py:298-302`). B1 promises no wire change, and the PR-0 golden for an exception injected into `session_state.configure` pins this text. Moving to an `internal_error` envelope is a wire change, so it goes to PR-B2.
   - No `current_request_ctx` ContextVar here. PR-H adds it if the spike justifies it.
   - Drop `MCP2`, `_construct`, the 1.x decorator branch, `_CAMEL_TO_SNAKE`, `annotation_value`, `normalized_annotation_keys`, `annotation_is_read_only`, and the camelCase `tool_input_schema` reader.
3. **`server.py`:**
   - Change both import branches: `:91` (package) and `:109` (`__package__ is None` → `from server.registration import build_server`).
   - Replace `annotation_is_read_only(tool_def.annotations)` at `:948-951` with `tool_def.annotations is not None and tool_def.annotations.read_only_hint is True`.
   - Change `:1134` to `registration.build_server(...)`.
   - Update the comments at `:67-71,:70,:728,:946-947,:1128-1132`.
4. **`server/__init__.py:204-231`.** The lazy-load hint now says `mcp>=2.3,<3` and gives the install fix. Remove the "1.x→2.x AttributeError on Server" heuristic, and update `tests/test_lazy_loader_diagnostics.py:42-104` to match.
5. **`server/kernel.py`.**
   - Keep the `try/except ImportError` and `check_mcp_available` (`:41-63`), which are public, exported at `server/__init__.py:55,261`.
   - Remove only the bare `Server("flextools-mcp")` at `:828`, and the `mcp_server` global at `:765` if nothing reads it (grep first).
6. **Delete `src/flextoolsmcp/mcp_compat.py`.**
7. **Docs and tooling:**
   - `RELEASING.md:54`, `docs/TODO.md:27`, `scripts/cap_canary.py:6`, `dep-cap-canary.yml`
   - the workflow comments, `.claude/mcp-init-profile.md:44`
   - merge the spec into the archive (section 1)
   - CHANGELOG: "Requires mcp 2.3+; last 1.x-compatible release is 2.15.x."
8. **Dev-environment instructions.** The venv was made by uv and has no pip. Use `uv pip install -r requirements.txt --python .venv\Scripts\python.exe`. Put that exact command in the conftest fail-fast message and in CLAUDE.md, replacing the `pip install -r requirements.txt` wording.

### Tests
- Rename `tests/test_mcp_compat.py` to `tests/test_mcp_registration.py` and parametrize it over `Client(server, mode='legacy')` and `mode='auto'`. Assert:
  - the negotiated `protocol_version` (2025-11-25 / 2026-07-28)
  - `server_info.version != ''`
  - `instructions == SERVER_INSTRUCTIONS`
  - the tool count equals `len(TOOLS)`
  - a read-only call works
  - invalid arguments give `is_error=True` with the "Input validation error" text
  - **a raise injected by monkeypatching `session_state.configure` (or `get_tool_handler`)** gives `is_error=True` with the verbatim `Error: {exc}` text, and no `MCPError`, in both modes
  - `InputRequiredResult` passes through (adapter unit test)
  - Drop the dict-annotation cases at `:131-152`, since dict annotations no longer exist.
- `tests/test_mcp_tools.py:419-448` (cold `run_module` rejected on the wire): use `Client(server)` and `.is_error` only. The assertions are otherwise unchanged.
- Snake-case rewrites:
  - `test_mcp_tools.py:203,227-270`
  - `test_filing_cancel.py:130-137`
  - `test_parse_diff.py:337-344`
  - `test_parse_text_handler.py:307-314`
  - `test_server_instructions.py:30-45`
- Change `test_response_contract.py:753` to read `t.output_schema`.
- `tests/conftest.py:46-99`: set `_SUPPORTED_MCP_FLOOR=(2,3,0)` and `_SUPPORTED_MCP_MAJORS=(2,)`.
- `tests/test_dependency_bounds.py`:
  - assert `major == 2`
  - assert the `<3` literal
  - assert the floor excludes 1.x
  - `KNOWN_UNCAPPED_DEPS` stays a name set; add a separate floor test for pydantic and anyio if wanted
- **Stdio subprocess test.** Register a `requires_subprocess` marker in `pytest.ini:7-8`. It is still `not requires_flex`.
  - Command: `StdioServerParameters(command=sys.executable, args=['-m','flextoolsmcp'])`.
  - Env: `FLEXTOOLSMCP_NO_UPDATE_CHECK=1`, `FLEXTOOLSMCP_NO_WORKSPACE_CHECK=1`, a temp `FLEXTOOLSMCP_LOG_DIR`, and `FLEXTOOLSMCP_INDEX_DIR` pinned to the shipped indexes. Assert that no refresh subprocess runs.
  - Use a generous explicit timeout (60s).
  - Run in both modes: handshake/discover, `tools/list`, one read-only call, and one forced-error call.
  - Assert nothing goes to stdout before the stream opens.
- **Guard test.** Grep `src/` and `tests/` for camelCase attribute reads of mcp types: `\.(inputSchema|outputSchema|isError|readOnlyHint|destructiveHint|structuredContent)\b` and `getattr\(.*'(readOnlyHint|isError|inputSchema|outputSchema)'`. Constructor kwargs are allowed.
- **PR-0 wire goldens** must pass unchanged in both modes.

### CI
- `test.yml`:
  - Replace the mcp axis at `:80` with Q2's choice. If the floor cell is kept, it pins the **whole lower-bound set** via `uv pip compile --resolution lowest-direct`. Otherwise use latest only and say so in RELEASING.md.
  - Delete the downgrade step at `:94-96`.
  - Make the stdio subprocess test a **required** cell on Windows. Decide whether Linux runs it too (no FieldWorks is needed for this test).
- `publish.yml:104-108`: replace the 1.27.0 re-smoke with a stdio handshake in both modes against the **built wheel's `flextools-mcp` console script** in a fresh venv.
- Locally, before merging:
  ```
  uv pip install -r requirements.txt --python .venv\Scripts\python.exe
  .venv\Scripts\python -m pytest -q -m "not requires_flex" | tail -20
  python scripts/validate_integrity.py server
  ```

### Install paths
- **uvx users:** `uvx` can serve a stale cache (`update_check.py:6-8,251-253`). Release notes and the README say to run `uvx flextools-mcp@latest`, or `uv tool upgrade flextools-mcp` for `uv tool` users (README:126).
- **Maintainer (pre-merge and post-merge):**
  1. Stop every client using the server.
  2. Run `uv tool install --editable C:\Github\FlexToolsMCP --with-editable C:\Github\flexicon --reinstall`.
  3. Verify `flextools_health`.
  4. Then pull main.

  Don't interrupt the reinstall; if it is cut short, the launcher RECORD problem appears. Add this as a new "Post-merge dev steps" section in RELEASING.md.
- **pip shared envs:** add a README note: "install in its own env; pin `flextools-mcp<R1` to stay on mcp 1.x."
- Run one manual `requires_flex` smoke on **Sena 3** before tagging, never Claude-Swahili. Expect `.fwdata` rewrites from parse tests.

### Acceptance
- `mcp_compat.py` is gone, and the guard test is clean.
- An mcp 1.x install is unsatisfiable.
- Both eras list and call tools in process, over stdio (in CI), and in the publish smoke.
- The PR-0 wire goldens match: text **and** `is_error`, including invalid-input and exception paths.
- The cold-session regression test passes.

### Risks
- Silent session or error-shape regression (PR-0 goldens cover it).
- Windows transitive dependencies vs pythonnet (Sena 3 smoke).
- SDK churn (verified floor, `<3` cap).

---

## 4. PR-B2: Pydantic-first validation (after Q1)

- Move `get_tool_handler(name)` together with the `input_model(**arguments)` validation (`server.py:1022-1045`) ahead of the cold-session gate (`:943-1020`).
- Delete the adapter's jsonschema pre-check.
- The adapter's exception fallback switches from plain `Error: {exc}` to an `error_response("internal_error", ...)` body. It uses the same fields as `server.py:1058-1070` (`error_type`, `tool`, `traceback`), so escaped and caught exceptions look alike. Whether to drop `traceback` is Q15, decided for both sites at once in Phase 5.
- **New error precedence, documented in TOOL-CONTRACT:**
  - a cold call to an unknown tool returns `unknown_tool` (was `session_not_initialized`)
  - a cold call with bad arguments to a non-read-only tool returns `invalid_input` (was `session_not_initialized`)
  - invalid input returns the `invalid_input` envelope (was plain text)
- `_on_call_tool` sets `is_error=True` for `invalid_input`, `unknown_tool`, `internal_error` and `session_not_initialized`, using the classifier extracted from `server.py:1090-1102` (`error_code`, then nested `error.code`, then top-level `error`). PR-E reuses this classifier.
- **Verdict-parity audit.** A parametrized test runs every tool's schema against a bad-input set (extra keys, str→int coercion, missing required). Test the session-independent tools separately: `FlexToolsStartInput` is `extra="allow"` (`models.py:47`). Record each intended difference in the CHANGELOG.
- Note that `invalid_input` echoes `received_arguments` and raw Pydantic `str(e)`. That is fine (it is the caller's own data), but PR-I1 lints it.
- Update `test_issue243_prehandler_dispatch_envelope.py`, `test_issue53_cold_start.py`, `test_mcp_tools.py:419-448` and the PR-0 goldens for the changed paths. Add a test that a cold session stays cold after unknown-tool and invalid-input calls.
- Bump the contract to 1.1.

---

## 5. Phase 4: discovery manifest and registry (PR-C, PR-D)

Timing is a maintainer decision (Q17). The issue says to publish "once Phases 1-2 are done". The alternative is to register early, gated on a healthy release. Either way, **Q7 (the immutable name) is answered before PR-C merges**, because the marker ships to PyPI.

- **PR-C** (separate PR, merged after B1):
  - Add `<!-- mcp-name: io.github.MattGyverLee/<name> -->` after `README.md:1`.
  - Add `server.json` at the repo root:
    - schema `2025-12-11`, pypi/stdio
    - optional env vars `FIELDWORKS_DLL_PATH`, `FW_PROJECTS_DIR`, `FLEXTOOLS_STATELESS`
    - `_meta` `platforms:["windows"]`
    - version = the target release; keep it out of the wheel
  - Add an integrity check (`validate_integrity.py`) and a test:
    - `server.json.version == packages[0].version == VERSION`
    - `identifier == [project].name`
    - the marker is present
    - description ≤100 chars
  - In the README, mention the registry, plus the Windows + FieldWorks 9 requirement.
- **PR-D:** a `registry` job after `publish`:
  - `id-token: write`, `contents: read`, and optionally a protected environment (Q8)
  - pinned, checksum-verified `mcp-publisher` v1.8.1
  - a tag == VERSION == server.json check
  - `mcp-publisher validate`
  - a poll until the PyPI JSON for that version contains the marker
  - `login github-oidc`, then `publish`
  - RELEASING.md gets a "bump server.json" step, recovery by re-running the failed job, and `mcp-publisher status --status deprecated`.
- **Acceptance:**
  - the integrity check passes
  - `validate` is clean locally
  - after the gated tag, the registry lists the entry
- **Risks:**
  - The name is immutable.
  - PyPI lag (handled by polling).
  - A half-published release (rerun the job).
  - A non-Windows install should start with a friendly "FieldWorks required" message; verify this.

---

## 6. Phase 2: structured output (PR-E → PR-F → PR-F2 → PR-G)

**Goal:** migrated tools advertise a real `outputSchema` (type:object root, JSON Schema 2020-12), and on success `structured_content == json.loads(content[0].text)`. Errors are `is_error=True` and text-only. Q18 settles whether text payloads may gain `status`/`_contract`; the issue says "existing text payloads unchanged".

### PR-E: envelope and hard-error flag
- **If Q18 is yes:**
  - The shared builder in `src/flextoolsmcp/response_utils.py:146-175` gets `data.setdefault("status","ok")`.
  - Remove the shadow at `handlers/api.py:392-402`.
  - Route the direct `TextContent(json.dumps(...))` sites through `response_utils.json_response`:
    - `catalog.py:124,170,199,247,253`
    - `discovery.py:216,232,243,257`
    - `equivalence.py:72`
    - `execution.py:1172,3129,7500`
    - `api.py:1275-1278`
  - Switching to the shared builder also attaches `update_notice` and `workspace_notice` to search and `get_object_api`. The "once per process" notice moves to whichever tool is called first. Put that in the CHANGELOG and goldens.
- **If Q18 is no:** skip the normalization. PR-F models the current shapes as they are.
- `_on_call_tool` applies the shared classifier (from B2, or extracted here if B2 hasn't shipped). It sets `is_error=True` only for **hard** errors, and the text stays byte-identical.
  - Soft gates (`confirmation_required`, `api_discovery_required`, `casting_issues_detected`) stay `is_error=False` until Q3 is answered after a client smoke. Marking `confirmation_required` as an error could make clients show a failure or retry automatically.
- **Implement the env switch `FLEXTOOLS_MCP_ERROR_FLAG=off`**, with a test. The rollback depends on it.
- `docs/TOOL-CONTRACT.md`:
  - make the success section match reality
  - add an "isError semantics" section
  - bump the contract minor
  - leave removal of the nested `error` object at 2.0
- **Tests:**
  - every tool's success carries `status`/`_contract` (if Q18 is yes)
  - in both modes, forced hard errors give `is_error` true with `structured_content is None`, and soft gates give false
  - with the switch off, errors give false
  - update the goldens via `CONTRACT_VERSION`

### PR-F: models and pilot (ships with default `off`)
- Replace `GetObjectApiSuccess` and `SearchByCapabilitySuccess` with real models:
  - `status: Literal['ok']`
  - required = keys that are always present
  - `extra='allow'`, which needs a TOOL-CONTRACT.md:23-25 update
  - `contract: str = Field(alias="_contract")`, plus `_session_note` and the notices as aliased optionals
  - schema via `model_json_schema(by_alias=True, mode='serialization')`
- **Schema unit tests:**
  - root `type=='object'`
  - only internal `#/$defs` refs (the client validates with an empty `Registry()`, `client/session.py:1170-1181`)
  - `Draft202012Validator.check_schema` passes
  - `_contract` appears in `properties` and `required`
  - **a lint that rejects 2020-12-only keywords** (`prefixItems`, `$dynamicRef`, `unevaluated*`) and sets `$schema` explicitly, since the Node clients validate with the TS SDK (Ajv); the spike confirms Ajv's dialect
  - a `tools/list` run under **`mode='legacy'` specifically**: only 2025-11-25 enforces `type: Literal["object"]`, and a bad root there gives -32603 "Handler returned an invalid result" for every legacy client (`runner.py:376-386`)
- Add `ToolDef.advertise_output_schema: bool = False` and `FLEXTOOLS_MCP_STRUCTURED_OUTPUT=off|pilot|all` (default `off` in this PR).
  - `list_tools()` (`server.py:862-883`) emits `outputSchema` only for flagged tools. Delete the comment at `:871-882`.
- **Mirror rule** (the client raises `RuntimeError` when a schema'd tool returns no structured content, `client/session.py:1101-1102,1138-1139`):
  - For a flagged tool, `_on_call_tool` builds `structured_content = json.loads(text)` from the **text**, never from handler dicts.
  - If the result is not an error and the parse fails, isn't a dict, or fails server-side validation against the published schema, **force `is_error=True`** and log it.
  - Any soft gate left non-error under Q3 must therefore validate against the success schema, or the tool must not be flagged.
- **Conformance test** (`tests/test_structured_output_conformance.py`):
  - Run real handlers over an argument matrix per tool: found and not-found, semantic on/off, each `api_mode`, cold and warm, and the soft gates.
  - Validate with `jsonschema` against the exact published schema, and also through a Node/Ajv step if the spike finds dialect differences.
  - Fail if any advertising tool lacks fixtures, and assert the forced-`is_error` path.
  - Replace `_MINIMAL_SUCCESS_PAYLOADS` (`tool_output_validation.py:50-63`) and wire it into `validate_integrity.py`.
- **End-to-end:** in both modes, in process **and over stdio**, `Client` calls each pilot tool, which runs the SDK's `validate_tool_result`.
- Flip `TestOutputSchema` (`test_response_contract.py:716-776`): the advertising set must equal the flagged set.
- Add a "Structured output" section to TOOL-CONTRACT: which tools, the mirror rule, errors as text-only, forward-compatible extra keys, and older handshake versions getting text only.

### Decision point after PR-F
Structured output only pays off if a client uses it. Today it adds a duplicate JSON copy of each response, and may double the tokens the model sees.

Writing schemas is the expensive part. The text and code pieces are JSON string fields inside one envelope, so mirroring the text is cheap. But each tool's envelope has many variable keys across branches (redirects, auto-fix, soft gates, `api_mode` variants). This is the same mismatch that ruled out FastMCP's typed returns (`docs/TODO.md:39-42`).

If the F2 smoke and the token check (Q6) show no client consuming `structuredContent`, **stop after the pilot**: leave it at `off`/`pilot` and drop PR-G.

### PR-F2: default flip to `pilot`. Exit criteria:
1. A documented smoke in Claude Code, Copilot and Gemini CLI: each lists and calls both pilot tools with no validation errors, in whatever era each client negotiates.
2. 14 days of maintainer use with `pilot` set locally and zero `structured_content`/forced-`is_error` events in the operations logs. A lex-logscan pass checks this; the main thread does not read `user-logs/`.
3. A record of whether clients send both copies to the model (Q6).

### PR-G
- The order is fixed when PR-F merges: the Q14 log scan if it has been done, otherwise `run_module` (redirect and auto-fix goldens), then `resolve_property`/`find_examples`/`list_recipes`, then the remaining read-only tools.
- Each batch ships with its fixtures and gets a contract minor bump.

### Risks
- Strict-client rejection (coverage test, mirror rule, kill switch).
- `is_error` changes client display (PR-E is a separate, switchable release).
- Token doubling.
- Tightening a model later can reject live responses.

---

## 7. Phase 3: long-running UX (trimmed and gated)

- **PR-A2 (now, independent):** run the SentenceTransformer load and encode through `asyncio.to_thread` in `search_by_capability` (`api.py:1411-1413`, `server.py:236-271`).
  - Test: a concurrent `parse_status` call completes while the patched slow model load is in progress.
- **README/USAGE:** one line recommending `flextools-mcp-refresh` after install. That is the only fix available for the startup stall.
- **Spike (1 day):** check whether Claude Code, Copilot and Gemini send `progressToken` and show progress (Q9). Build PR-H only if at least the primary client does.
- **PR-H (conditional):**
  - Add the `current_request_ctx` ContextVar in `_on_call_tool`, reset in `finally`.
  - `server/progress.py`:
    - `report_progress(...)` calls `ctx.session.report_progress` unconditionally, wrapped in `suppress(Exception)`. It works on both eras; on the modern in-process path the token is `None`.
    - It may be called **only from the request task and its heartbeat**. Code that starts long-lived `create_task` jobs (the `parse_text` batch) must run them under `contextvars.copy_context()` with the variable reset to `None`. Executor threads don't inherit it.
  - `heartbeat(label, interval=5.0)`: an elapsed-seconds task, cancelled in `finally`.
  - Apply it to:
    - `handle_run_module` (lock wait vs child running, `execution.py:6359-6372`)
    - `grammar_health` (`grammar_health.py:273`, `execution.py:7219-7305`)
    - `try_word` measurement (`parse/measure.py:278-285`)
  - Tests:
    - with a `progress_callback`: at least 2 increasing values, none after the result, in both modes **and over stdio**
    - without a callback: identical result
    - cancellation leaves no task behind
    - the background batch emits no progress after the response
- **Deferred:**
  - progress for index refresh and embedding builds (no request exists then)
  - `parse_text`, `prepare_report`, `flextools_start` (already polled, or fast)
  - **tasks**: there is no SDK runtime. A facade over ParseRunner via `mcp.server.extension.Extension` is possible later, but stay with FR-014 "no second execution model". Revisit when the SDK and Claude Code support it, and record this on #369.
  - line-by-line stdout streaming

---

## 8. Phase 5: security

### PR-A (now)
- **Bug:** `server/diagnostic/transports.py:77-95,113-121`. `_quote_argv` escapes only `"`, so `$(...)` and backticks in a title (which includes the model-supplied `user_intent`) are expanded in a POSIX shell.
  - Fix: `shlex.quote` for POSIX display, a separate PowerShell-safe rendering (or argv only), and stripping of control characters.
  - Test: `x $(touch pwned) \`id\` \\ "q"` round-trips through `shlex.split` to the exact argv.
- **Accuracy fixes:**
  - `models.py:433` ("pre-imported")
  - `tool_definitions.py:413` (drop "AI-generated")
  - `tool_definitions.py:107` (the tool count is 31)
  - the README line "Requires explicit user permission for write operations" (`README.md:282-292`): `confirmed=True` comes from the model, and the human check is the client's prompt on destructive tools

### PR-I1: surface lint
- `tests/test_tool_surface_lint.py` covers descriptions, every `get_schema()` string, `SERVER_INSTRUCTIONS`, output-schema descriptions after PR-F, and the fixed text in `invalid_input`/`internal_error`. Checks:
  - printable ASCII only, with no zero-width, bidi or tag characters
  - a URL allowlist
  - every `flextools_\w+` mention resolves to a key in `TOOLS`
  - deny patterns
  - MUST/ALWAYS/NEVER counts pinned per tool
- The `tool_surface.json` drift check from PR-0 gets a regeneration flag.
- **Index-content lint** in refresh/`liblcm_index_sanity.py`, with a pinned allowlist (one "you must" in flexicon 4.12.0, the sillsdev/liblcm URL). It warns on upstream text and fails on repo-authored text (Q12).

### PR-I2: least privilege. Each item is its own PR behind an env flag that defaults to **warn**.
- **I2a: annotations.**
  - First add `ToolDef.cold_auto_init`, which **separates cold auto-init from `readOnlyHint`**. The gate at `server.py:943-952` reads the new flag, and `test_mcp_tools.py:388,674` must still pass.
  - Then add the side-effect table (none / local-files / session-state / project-db) and a test that it agrees with the annotations.
  - Resolve `flextools_start` (Q11), `parse_sandbox` `create_sandbox`/`seed_corpus`, and `manage_config destructiveHint`.
  - CHANGELOG and USAGE.md notes for each annotation change.
- **I2b: protected config keys** (Q10).
  - Keys: `require_write_confirmation`, `backup_before_write`, `report_repo`, `report_email`, `auto_fix_enabled`.
  - Warn mode, then refuse mode with a new `config_key_protected` error code: a TOOL-CONTRACT entry and contract minor bump, and an `extra='forbid'` detail model.
  - A tripwire test mirroring `tests/test_filing_bypass_surface.py`.
- **I2c: non-LCM side-effect tripwire** (Q19).
  - In the `run_module` preflight (`validators.py`): subprocess, socket, urllib, ctypes, System.Net, Process, `exec`/`__import__`.
  - Results go into `writeability.non_lcm_side_effects[]`. Warn mode only reports; enforce mode requires `confirmed=True`.
  - Call it a tripwire, not a sandbox (SECURITY.md).
  - **Regression run over the whole recipe library plus the maintainer's stored local recipes** before enforce becomes the default.

### PR-I3: injection invariants
- A fake runner/backend injects a canary into the outputs of `run_module`, `parse_log`, `try_word`, local `list_recipes` rows and `get_session_history`. The canary includes instruction text, shell metacharacters, `</output>` and zero-width characters. Assert:
  - the canary appears only in data fields, never in `message`/`hint`/`next_steps`/`how_to_run`
  - `session_state.write_enabled` and the config are unchanged
  - the canary is JSON-escaped
- `reviewed: true|false` on recipe rows. Injected local rows never become `recommended_recipe`.
- Extend the "data, never instructions" sentence to the tools that echo project data, pinned by tests.
- Apply the Q15 traceback decision to both `internal_error` sites (traceback to the operations log only, paths removed from messages).
- Add a "Tool poisoning and least privilege" section to SECURITY.md.
- **Human confirmation is deferred, not ruled out (era-dependent).** Legacy connections can use `ctx.session.elicit`. On 2026-07-28 the route is an `InputRequiredResult` multi-round-trip from `on_call_tool`; the PR-B1 adapter already passes it through. Write this down as the future path for confirming writes.

---

## 9. Deferred items
- An SDK-managed tasks extension, or an `Extension`-based facade over ParseRunner.
- MRTR/elicitation-based write confirmation.
- Streaming child stdout.
- PR-G, the structured-output rollout beyond the pilot, unless a client is shown to consume `structuredContent` (see "Decision point after PR-F").
- Shrinking text when structured content is present (Q6).
- Removing the nested `error` object (contract 2.0, on its existing schedule).

## 10. Rollback

| Change | Rollback |
|---|---|
| PR-B1 | One squash revert (PR-C is separate, so the marker survives) and ship R1+1. Users pin `uvx flextools-mcp==2.15.0`. Don't yank unless the server won't start. |
| PR-B2 | Revert. The precedence and the plain-text invalid input come back. Docs return to the previous contract minor. |
| PR-E | `FLEXTOOLS_MCP_ERROR_FLAG=off` (built and tested in PR-E), with no release needed. Or revert. |
| PR-F/F2/G | `FLEXTOOLS_MCP_STRUCTURED_OUTPUT=off` at runtime. Per tool: clear `advertise_output_schema` and ship a patch. F2 is a one-line revert. |
| PR-A2/PR-H | Trivial revert. Progress is a no-op on failure. |
| Registry | Can't be deleted or renamed. Use `mcp-publisher status --status deprecated` and publish a corrected version. |
| PR-I2a/b/c | Env flag back to warn. Revert restores the behavior, and the error code stays documented as reserved. |

## 11. Open questions for the maintainer
1. **Validation in B2:** use Pydantic-first, with the new precedence (unknown_tool/invalid_input ahead of session_not_initialized)? *Recommendation: yes, after the parity audit.*
2. **CI floor:** keep a full lower-bound cell (`--resolution lowest-direct`: mcp 2.3.0, pydantic 2.12, anyio 4.9) plus latest, or latest only?
3. **Soft gates and `is_error`:** decide after the client smoke. *Default: false.*
4. ~~**Output schemas:** keep `additionalProperties` open permanently?~~ **Decided: yes.** Schemas stay open and require few fields, because tool envelopes mix many variable text and code fields per branch (the FastMCP rationale). "Closed output schemas" in section 9 is dropped, not deferred.
5. Should `kernel.py`'s `mcp_server` global be removed if unused? (`check_mcp_available` stays.)
6. **Token cost** if clients send both copies: shrink the text later?
7. **Registry name:** `io.github.MattGyverLee/flextools-mcp` or `.../flextoolsmcp`? It must be answered **before PR-C merges**. Should `FLEXTOOLSMCP_LOG_DIR`/`INDEX_DIR` be advertised? Is there an icon?
8. **Registry job** behind a protected environment with required reviewers?
9. **Progress:** answered by the spike. Does PR-H get built?
10. **Protected config keys:** refuse, or warn only? Should `run_module` confirmation be unconditional, like filing?
11. **`flextools_start`:** keep `readOnlyHint=True`, or split write arming into its own path?
12. **Lint severity** for upstream docstrings: warn or fail?
13. **R1 version:** 2.16.0 or 3.0.0? It must be answered before PR-B1.
14. **Traffic ranking for PR-G:** run a lex-logscan scan of `operations.jsonl`?
15. **Tracebacks in `internal_error`:** keep them in tool output (current contract), or send them to the operations log only? This touches the contract.
16. Declare `jsonschema` as an explicit (test) dependency, now that the direct import goes away?
17. **Registry timing:** after Phases 1-2 as the issue says, or early, gated on R1 being healthy for N days (or R1+1)?
18. **May text payloads gain `status`/`_contract`** (PR-E normalization), given the issue's "existing text payloads unchanged" acceptance?
19. **Side-effect tripwire (I2c):** wanted at all? If so, does enforce ever become the default, and on what evidence?

---

## Appendix: critiques rejected or partially accepted

- **scope-sequencing, PR-0 "every tool's success path": partially accepted.** About a third of the tools need a live FieldWorks project, so their success goldens can't run under `-m "not requires_flex"` in CI. PR-0 covers every tool that runs without FieldWorks, all the shared error and gate paths, and the full `tools/list` surface. The FieldWorks-dependent success paths are covered by the existing handler-level goldens and the Sena 3 manual smoke.
- **sdk-correctness #3, "add a real sanitizer in PR-B": partially accepted.** The factual correction is accepted: `error_response` does not sanitize, and tracebacks already leak through `internal_error`. Sanitizing in PR-B1 would change a documented contract field and break the "no wire change" property of B1. Instead, B1 keeps the shim's `Error: {exc}` text verbatim. PR-B2 switches the fallback to the existing `internal_error` fields, and traceback handling changes for both sites together in PR-I3 under Q15. (Amended after review: an earlier draft put the `internal_error` body in B1, which contradicted B1's no-wire-change goldens.)
- **sdk-correctness #2 and repo-fit #4 (set `is_error` for `invalid_input` in PR-B): handled differently.** Following the scope-sequencing blocker, B1 keeps the jsonschema pre-check in the adapter verbatim, so `is_error=True` and the "Input validation error" text are preserved without special-casing. The `is_error` classification for `invalid_input` moves to B2, together with the reorder that creates the envelope.
- All other critiques were accepted. They were spot-checked against the repo:
  - `src/flextoolsmcp/server/__main__.py` is absent; the entry point is `src/flextoolsmcp/__main__.py`.
  - The telemetry hook is wrapped in `try/except: pass` (`server.py:1117-1126`).
  - The shared builder sets only `_contract`, not `status`.
  - `specs/_archive/mcp2-compat/` already exists.
  - `pytest.ini` registers only `requires_flex`.
  - `.venv` has no pip.
  - `response_utils.py` lives at `src/flextoolsmcp/response_utils.py`, not under `server/`.