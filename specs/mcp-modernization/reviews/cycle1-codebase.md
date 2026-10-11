# Cycle 1 — Codebase audit: retiring `mcp_compat.py`, going mcp>=2-only (issue #369, Phase 1)

- **Worktree / HEAD:** `~/workspace/ftmcp-369`, branch `feat/369-mcp-modernization` @ `c1c751f` (= `origin/main`).
- **Mode:** READ-ONLY audit. No code changed; this report is the only file written.
- **Method:** full-repo grep for every shim symbol + manual read of every consumer;
  plus a live probe in a scratch venv (`/tmp/mcp2probe`, **mcp 2.3.0**, the current
  latest 2.x) to verify every "2.x replacement" claim below against the real API.
  Probe facts are marked **[probe 2.3.0]**; everything else is file:line on this HEAD.
- **Scope note:** Phase 1 only (floor raise + shim retirement). Phases 2–5 of #369
  (structured output, progress/tasks, `server.json`, security audit) are out of scope
  except where they touch the same lines.

## Verdict (read this first)

1. **The shim's 2.x branch is already the correct 2.x code.** Retiring the shim is
   mostly *deleting the 1.x branch and the dual-spelling helpers*, then inlining the
   surviving adapters into `server.py`. No handler, dispatch, or `handlers/*.py`
   change is needed: they keep returning bare `list[TextContent]`.
2. **Issue #369's Phase 1 text contains a material error** (see §7): it says to
   replace `Server` + `build_server()` with `mcp.server.MCPServer` and claims the
   existing handler signatures "already match the 2.x `on_list_tools=`/`on_call_tool=`
   shape". Both halves are wrong under the installed 2.x. The lead should rule on
   *low-level `Server` inline* (recommended, small) vs *`MCPServer` migration*
   (a different, larger rewrite) before implementation starts.
3. **Pre-validation is the one guarantee with no native 2.x replacement on stdio**
   (§2, G1). The `jsonschema` adapter must survive the shim's death verbatim in
   substance. **[probe 2.3.0]** `jsonschema>=4.20.0` is a hard dependency of
   `mcp` 2.3.0, so relying on it adds no new dependency.
4. Everything else — `kernel.py`'s bare `Server(...)`, `stdio_server`,
   `server.run(...)`, `create_initialization_options()`, the dual-path import
   machinery — survives 2.x-only unchanged (§3, §4).

---

## 1. `mcp_compat.py` exports and every call site

File under audit: `src/flextoolsmcp/mcp_compat.py` (355 lines). No `__all__`;
exports = module-level public names. Line ranges are definition spans.

### 1.1 Export inventory + 2.x-only replacement

| # | Export | Def | Production consumers | Test consumers | 2.x-only replacement |
|---|--------|-----|----------------------|----------------|----------------------|
| E1 | `MCP2` flag (`not hasattr(Server, "call_tool")`) | L38 | none directly (only `build_server` L335) | `tests/test_mcp_compat.py:36,75-77` | **Delete.** No replacement; the probe it encodes is meaningless once 1.x is unsupported. **[probe]** `hasattr(Server,"call_tool")` is `False` on 2.3.0, as expected. |
| E2 | `resolve_server_version()` | L41-64 | `build_server` L333 (default version) | `test_mcp_compat.py:41,80-82` | **Keep, move verbatim** into `server.py` (or `server/kernel.py`, see note below). Logic is major-agnostic: `importlib.metadata.version("flextools-mcp")` → walk-up `VERSION` file → `"0.0.0.dev0"`. Still required: **[probe]** 2.x `Server(version="")` defaults to empty, so an explicit version remains the `serverInfo.version` parity fix. |
| E3 | `_construct()` (private; bare-name `TypeError` fallback) | L67-77 | `build_server` L336, L345 | none | **Delete.** **[probe]** 2.3.0 `Server(name, *, version="", instructions=None, on_list_tools=…, on_call_tool=…, …)` accepts every kwarg the shim passes; the fallback only covered hypothetical pre-`version` 1.x constructors. Inline `Server(name, version=…, instructions=…, on_list_tools=…, on_call_tool=…)` at the construction site. |
| E4 | `annotation_is_read_only(annotations)` | L80-102 | `src/flextoolsmcp/server.py:91,109` (import), **`:950`** (cold-session gate) | `test_mcp_compat.py:37,137-152` | **Simplify + inline in `server.py`.** 2.x exposes only `read_only_hint` (**[probe]** camel read raises `AttributeError`). Replacement body: `bool(annotations is not None and getattr(annotations, "read_only_hint", False))`, keeping the dict fallback only if a dict-shaped caller exists — none does in `src/` (gate passes `tool_def.annotations`, a `ToolAnnotations`). A one-liner at `server.py:950` (`tool_def.annotations and tool_def.annotations.read_only_hint`) is also viable; a named helper preserves the gate's readability and its test seam. |
| E5 | `annotation_value(annotations, camel_name)` + `_CAMEL_TO_SNAKE`/`_SNAKE_TO_CAMEL` maps | L105-155 | **none** (docstring: "Test helper (and future production use)") | `tests/test_filing_cancel.py:130-137`; `tests/test_mcp_tools.py:239-268` (3 tests); `tests/test_parse_diff.py:337-344`; `tests/test_parse_text_handler.py:307-314` | **Delete; tests read snake_case directly.** E.g. `annotation_value(a, "readOnlyHint")` → `a.read_only_hint`. **[probe]** 2.3.0 `ToolAnnotations` fields are exactly `title, read_only_hint, destructive_hint, idempotent_hint, open_world_hint`; unset fields read as `None`, and existing assertions use `is True/is False` — see the trap in §2/G4: fields a test expects to be `False` must actually be *set* `False` in `tool_definitions.py` (they are: every `ToolAnnotations(...)` there sets all four hints explicitly, e.g. L90-95, L369-374). |
| E6 | `normalized_annotation_keys(annotations)` | L158-174 | none | `tests/test_mcp_tools.py:227-232` (`test_annotations_have_required_keys`) | **Delete; test rewrites to snake_case.** Replacement: `set(vars(tool.annotations))` compared against `{"read_only_hint","destructive_hint","idempotent_hint","open_world_hint"}` (subset check — **[probe]** `vars()` on 2.3.0 also yields `title`). |
| E7 | `make_list_tools_handler(list_tools_fn)` | L177-190 | `build_server` L350 | `test_mcp_compat.py:40,93-96` | **Keep, move to `server.py`.** Already pure 2.x: wraps `async () -> list[Tool]` into `on_list_tools(ctx, params) -> ListToolsResult(tools=…)`. **[probe]** matches 2.3.0's `on_list_tools: Callable[[ServerRequestContext, PaginatedRequestParams \| None], Awaitable[ListToolsResult]]`. |
| E8 | `_tool_input_schema(tool)` / `tool_input_schema(tool)` (public alias) | L193-206 / L209-215 | `make_schema_provider` L231 | `tests/test_mcp_tools.py:203-208` (`test_all_tools_have_input_schema`) | **Simplify + move with E9.** 2.x-only body: `return tool.input_schema` (**[probe]** `Tool` fields are snake_case; `tool.inputSchema` raises `AttributeError`). The test can read `tool.input_schema` directly and drop the import entirely. |
| E9 | `make_schema_provider(list_tools_fn)` | L218-236 | `build_server` L351-353 | `tests/test_mcp_tools.py:431-437` (wire pre-validation test, §2/G1) | **Keep, move to `server.py`** (with E8 simplified). Builds `{tool.name: input_schema}` from the real tool list; tools without a schema are skipped (fail-open per tool). |
| E10 | `make_call_tool_handler(call_tool_fn, schema_provider=None)` | L239-305 | `build_server` L350-353 | `test_mcp_compat.py:39,99-216` (8 tests); `test_mcp_tools.py:431-448` | **Keep, move to `server.py` — this is the load-bearing adapter** (§2, G1+G3). Drop nothing except 1.x framing in comments. Fail-open paths (no `jsonschema`, provider raises, unknown tool) stay. |
| E11 | `build_server(name, list_tools_fn, call_tool_fn, version=None, instructions=None)` | L308-355 | `src/flextoolsmcp/server.py:91,109` (import), **`:1134`** (the one construction); `tests/test_server_instructions.py:31,39` | `test_mcp_compat.py:38,85-90` | **Delete as a function; inline its 2.x branch (L344-355) at `server.py:1134`.** The 1.x branch (L335-342, decorator registration) dies. Inline form: `Server("flextools-mcp", version=resolve_server_version(), instructions=SERVER_INSTRUCTIONS, on_list_tools=make_list_tools_handler(list_tools), on_call_tool=make_call_tool_handler(call_tool, make_schema_provider(list_tools)))`. `instructions=None`-forwarding nuance disappears: `server.py` always passes a real string; the test (§2) constructs `Server` directly. |

### 1.2 Production call-site inventory (complete)

| Site | What it uses |
|------|--------------|
| `src/flextoolsmcp/server.py:91` | `from .mcp_compat import annotation_is_read_only, build_server` (package branch) |
| `src/flextoolsmcp/server.py:109` | `from mcp_compat import annotation_is_read_only, build_server` (script branch) |
| `src/flextoolsmcp/server.py:950` | `annotation_is_read_only(tool_def.annotations)` — cold-session gate (see §2/G1, §3) |
| `src/flextoolsmcp/server.py:1134` | `server = build_server("flextools-mcp", list_tools, call_tool, instructions=SERVER_INSTRUCTIONS)` (no explicit `version=` — relies on E2 default) |
| `src/flextoolsmcp/server/__init__.py:126-129` | Comment only ("registered via mcp_compat") inside the lazy-loader docstring/`LAZY_IMPORTS` note; the lazy names themselves (`server`, `list_tools`, `call_tool`, `Server`) are shim-independent. Text must be updated, behavior unchanged. |

No other `src/` file imports the shim (verified by grep over `src/`, `scripts/`,
`tests/`). `dispatch.py` and `handlers/*.py` never touch it — they return bare
`list[TextContent]` and are insulated by E10, exactly as the shim docstring
(L15-18) intended.

### 1.3 Where the survivors should live

All surviving code (E2, E4-simplified, E7, E8/E9-simplified, E10) is used by
exactly one module, `server.py`, and `server.py` is where `list_tools`/`call_tool`
already live. **Inline into `server.py`** (above the L1134 construction) rather
than creating a successor module — a new `mcp_server_setup.py` would just be the
shim renamed. One judgment call for the implementer: E2 duplicates the
package-version logic already in `server/kernel.py:510-533` (session header).
Consolidating E2 into kernel and importing it is a pre-existing duplication fix,
*not* required by Phase 1; flag it, don't smuggle it in.

---

## 2. Behavioral guarantees that must survive as tests

The shim docstring (L20-27) states the core guarantee; the code adds three more.
Each is mapped to its existing tests and its post-shim disposition.

### G1 — Input pre-validation BEFORE any session-state setup (critical)

- **Guarantee:** `arguments` are validated against the tool's `inputSchema`
  (via `jsonschema`) *before* `call_tool_fn` is invoked. Reason (shim L20-27):
  `server.py`'s cold-session gate (`server.py:940-1000`, gate condition L943,
  `session_state.configure(...)` at ~L972) configures session state **before**
  `call_tool`'s own Pydantic re-validation (~L1037). On 1.x the decorator
  validated first, so a rejected first call left the session cold; a raw 2.x
  `on_call_tool` does not validate, so without E10's pre-validation a rejected
  first `flextools_run_module` call would auto-initialize the session — a
  behavioral divergence, not a cosmetic one. Failure shape must also match:
  `CallToolResult(isError=True, content=[TextContent("Input validation error: …")])`
  (shim L287-296).
- **No native substitute on stdio [probe 2.3.0]:** low-level `Server` accepts a
  `get_tool_input_schema=` constructor kwarg, but in 2.3.0 it is consumed only by
  the streamable-HTTP transport (Mcp-Param header validation,
  `mcp/server/_streamable_http_modern.py:343-368`); the stdio `tools/call`
  dispatch does not validate against it. Do **not** let an implementer "simplify"
  G1 away by passing that kwarg. (If a later phase adds HTTP transport, revisit.)
- **Existing tests:**
  - `tests/test_mcp_tools.py:424-448` `test_wire_rejected_cold_run_module_leaves_session_cold`
    — the end-to-end form: real adapter + real tool list + real dispatcher;
    invalid `flextools_run_module` args → `is_error`, `"Input validation error"`,
    `srv.session_state.initialized is False`. **Must survive** — rewire its import
    (L431-434) from `flextoolsmcp.mcp_compat` to wherever E9/E10 land in
    `server.py` (note: this file already loads `server.py` directly via
    importlib, L37-52, so `srv.make_call_tool_handler` is the natural seam).
    Its `is_error` reader (L441-444) already handles the 2.x spelling first.
  - `tests/test_mcp_compat.py:172-216` — adapter-unit form: pre-validates without
    invoking the handler (L172), valid args delegate (L189), unknown tool fails
    open (L197), failing provider fails open (L207). **Rewrite** against the
    moved adapter in `server.py` (or keep the file, retitled — see §2.1).

### G2 — `serverInfo.version` is ours, never `""`

- **Guarantee:** explicit `version=` at construction (shim L320-333). 2.x defaults
  `version=""` **[probe: confirmed]**; 1.x defaulted to the mcp library version.
  **[probe]** on 2.3.0, `create_initialization_options()` returns
  `InitializationOptions` with flat `server_version` (no `server_info`).
- **Existing tests:** `test_mcp_compat.py:80-82` (E2 never empty) and `:85-90`
  (`build_server(..., version="9.9.9")` → options carry `9.9.9`; its
  `_options_version` helper L58-63 reads both majors' shapes). **Rewrite:**
  construct the real server (or the inlined construction) and assert the flat
  `opts.server_version == "9.9.9"` only — the dual-shape helper dies. Also keep
  an E2 test at its new home.

### G3 — `CallToolResult` wrapping + `isError` semantics

- **Guarantee:** bare `list[TextContent]` from handlers is wrapped in
  `CallToolResult(content=…)` (shim L303); a raising handler becomes
  `CallToolResult(content=[TextContent(f"Error: {exc}")], isError=True)`
  (L298-302), mirroring the 1.x decorator; `params.arguments or {}` tolerates a
  null arguments payload (L280). **[probe]** 2.3.0 `CallToolResult` canonical
  read is `is_error`; construction via `isError=` alias still works but the
  inlined code should construct with `is_error=` (the shim already does, L294/301).
- **Existing tests:** `test_mcp_compat.py:93-96` (list-tools adapter wraps into
  `ListToolsResult`), `:99-105` (wrap bare content), `:107-114` (exception →
  `isError` + message), `:116-128` (null arguments). **Rewrite** against the
  moved adapters; drop the dual-spelling `_is_error` helper (L66-72) for direct
  `.is_error` reads.

### G4 — Annotation read-only spelling (cold-session gate correctness)

- **Guarantee:** the gate at `server.py:950` must read the *installed* major's
  spelling; reading only `readOnlyHint` silently disabled cold-session
  auto-init for every read-only tool under 2.x (shim L83-90). 2.x-only form is
  trivial (E4) but the *behavior* — read-only tools auto-init, write tools
  don't — must stay tested against the real `TOOL_DEFINITIONS`.
- **Existing tests:** `test_mcp_compat.py:137-141` (helper reads both spellings —
  **dies**, single-spelling now) and `:143-152`
  `test_real_tool_annotations_resolve_on_this_major` (real
  `flextools_search_by_capability` is read-only, `flextools_run_module` is not,
  through the exact gate lookup). **Rewrite :143-152** against the simplified
  helper / direct `.read_only_hint` read; it remains the regression test for G4.
- **Annotation-value consumers (E5/E6)** — assertion-only tests, behavior is
  "the shipped annotations say what the design says":
  `tests/test_filing_cancel.py:129-137`, `tests/test_parse_diff.py:336-344`,
  `tests/test_parse_text_handler.py:306-314`,
  `tests/test_mcp_tools.py:200-208` (E8), `:226-232` (E6), `:238-268` (E5 ×3).
  **All rewrite in place** to direct snake_case attribute reads; no new helper
  module. Trap: `ToolAnnotations` fields default to `None` on 2.x, so
  `is False` assertions only pass because `tool_definitions.py` sets all four
  hints explicitly on every tool — do not "clean up" those explicit `False`s
  in the same PR.

### 2.1 Test disposition summary

| File | Disposition |
|------|-------------|
| `tests/test_mcp_compat.py` (216 lines, 13 tests) | **Dies as named.** 1 test is pure-shim (`test_mcp2_flag_matches_live_server_class`, L75). The other 12 carry G1–G4 and must be **rewritten, not deleted**: recommend a successor file (e.g. `tests/test_mcp_server_wiring.py`) importing the adapters from `flextoolsmcp.server`-loaded module, with dual-spelling helpers (`_options_version`, `_is_error`) collapsed to 2.x reads. Net ≈ same size. |
| `tests/test_mcp_tools.py` | 6 import sites rewired (L203, L227, L239, L250, L264 → direct reads; L431-437 → moved adapters). The G1 wire test (L424-448) is the single most important test in the migration — it must pass *before and after* with only its import changed. |
| `tests/test_filing_cancel.py`, `test_parse_diff.py`, `test_parse_text_handler.py` | 1 import + 3-4 assertion lines each → direct `.read_only_hint` etc. |
| `tests/test_server_instructions.py` (46 lines) | L31/39: replace `build_server(...)` round-trip with direct `Server("test-instructions", instructions=SERVER_INSTRUCTIONS, …)` construction; the assertion (`server.instructions == SERVER_INSTRUCTIONS`, L46) is already 2.x-valid **[probe: `instructions` is a plain attribute on 2.3.0 `Server`]**. Other 3 tests untouched. |
| `tests/test_dependency_bounds.py` (89 lines, 3 tests) | **Rewrite** — see §5. |
| **New tests needed** | (a) A *construction* test: the module-level `server` object in `server.py` is a 2.x `Server` whose `create_initialization_options().server_version` is non-empty and equals `resolve_server_version()` — today G2 is only tested via `build_server` with a fake version, never against the real construction. (b) A *discover/negotiation smoke*: #369 Phase 1 acceptance asks for dual-era negotiation + `server/discover` verification. **[probe]** low-level `Server` in 2.3.0 registers `server/discover` natively (`_handle_discover` in its request table), so a test that the built server answers it is cheap — but no harness for protocol-level calls exists in the suite today; building one is the only genuinely *new* test infrastructure in Phase 1 and should be sized separately if the lead requires it in Phase 1 rather than as a follow-up. (c) Nothing else: G1/G3/G4 coverage is complete once rewired. |

---

## 3. `server.py` module surface

File: `src/flextoolsmcp/server.py` (1324 lines).

- **Construction — L1129-1135:** comment block (L1129-1133) + the single line
  `server = build_server("flextools-mcp", list_tools, call_tool, instructions=SERVER_INSTRUCTIONS)`
  at L1134. This is the *only* place a handler-bearing server is built.
  Replacement per E11: inline `Server(...)` with `on_list_tools=`/`on_call_tool=`,
  explicit `version=resolve_server_version()`. Adapters (E7/E9/E10) must be
  defined above this line — natural home is directly above it, after
  `call_tool` ends (~L1127).
- **`list_tools()` — L853-885** (def L856): undecorated `async () -> list[Tool]`,
  builds `Tool(**kwargs)` with camelCase `inputSchema` kwarg (L869). **[probe]**
  construction via camelCase alias still works on 2.3.0 — *no change required*;
  converting to `input_schema=` is optional cosmetic churn (recommend: leave it,
  same ruling as the archived mcp2-compat audit). The disabled-`outputSchema`
  comment block (L871-883) is Phase 2 territory; untouched by Phase 1.
- **`call_tool(name, arguments)` — L901-1127** (def L904):
  `async (str, dict) -> list[TextContent]`. Body unchanged. Its cold-session
  gate is at L943-1000 (see G1); its Pydantic re-validation at ~L1037 is why
  G1's ordering matters. Note for the implementer: this signature does **not**
  match 2.x's `on_call_tool(ctx, params)` — that mismatch is precisely what
  E10 adapts, and why E10 survives.
- **`main()` / stdio path — L1138-1307; `run()` at end of file:**
  `main()` preloads indexes, then L1278 `async with stdio_server() as
  (read_stream, write_stream):` and L1283
  `await server.run(read_stream, write_stream, server.create_initialization_options())`.
  Imports: `stdio_server` at L170, `Tool`/`TextContent` at L171-174.
  **[probe]** all three are present and signature-compatible on 2.3.0
  (`Server.run` exists; `create_initialization_options()` gained only an
  optional `extensions=` kwarg). **No change.**
- **`Server` re-export — L68:** `from mcp.server import Server  # noqa: F401`
  exists so the lazy loader can serve `from flextoolsmcp.server import Server`
  (see `server/__init__.py` `LAZY_IMPORTS`, L117-132). **[probe]** `Server`
  remains importable from `mcp.server` on 2.3.0. **No change** — but note the
  inline construction at L1134 can use this already-imported name; no new
  import line is needed in `server.py`.
- **Console entry points:** `pyproject.toml` `[project.scripts]` points both
  `flextoolsmcp` and `flextools-mcp` at `flextoolsmcp.server:run`. Unaffected.

### `kernel.py`'s bare `Server(...)` — exists, survives

- `src/flextoolsmcp/server/kernel.py:42-53`: guarded import
  (`from mcp.server import Server`, `stdio_server`, `Tool/TextContent/CallToolResult`
  at L43-45; on `ImportError` all set to `None`, error kept for
  `check_mcp_available()` L55-63, re-exported via `server/__init__.py`).
- `kernel.py:764-765`: `mcp_server: Optional[object] = None` global.
- `kernel.py:828` (inside `initialize_kernel()`, L808+):
  `mcp_server = Server("flextools-mcp")` — a bare, handler-less health-check /
  availability instantiation; nothing registers on it and `main()` never uses
  this instance (the real server is `server.py`'s).
- **[probe]** `Server("flextools-mcp")` constructs fine on 2.3.0 (all other
  params optional). **Survives 2.x-only with zero changes**, including the
  guarded-import shape. Caveat to record, not fix: this instance is vestigial
  (a second server object that serves nothing); deleting it is a cleanup
  decision outside Phase 1's "preserve behavior" remit.
- `kernel.py:510-533` duplicates E2's version-resolution logic for the session
  header — see §1.3 note.

---

## 4. Dual-path import pattern — NOT affected

Two distinct mechanisms, neither of which references the shim's *behavior*:

1. **`server.py`'s own dual branch (L74-109):** `if __package__:` relative
   imports (`.mcp_compat`, L91) vs script-mode absolute imports (`mcp_compat`,
   L109), mirrored for kernel/tool_definitions/dispatch/etc. Removing the shim
   changes exactly these two lines: both branches drop the `build_server` /
   `annotation_is_read_only` import (the inlined adapters need no import at
   all). The branch structure itself stays — it exists for script-mode
   execution of `server.py`, not for mcp.
   Also update the stale comments at `server.py:70` ("registration itself
   moved to .mcp_compat.build_server()"), L728-732, L853, L901, L1129-1133.
2. **`server/_dual_path.py` (35 lines)** + consumers
   (`kernel.py:944-955` `_register_kernel_module_aliases()`,
   `session.py:18,885-887`): collapses `flextoolsmcp.server.*` vs legacy
   `server.*` module spellings (#172). It never mentions `mcp_compat`
   (grep-verified: no pair for it exists — the shim was only ever loaded
   under one spelling per process via branch (1)). **Zero changes.**
3. **`server/__init__.py` lazy loader:** `LAZY_IMPORTS` (L117-132) includes
   `server`, `list_tools`, `call_tool`, `Server` — all survive. Two text-only
   updates: the "registered via mcp_compat" comment (L126-129) and the
   #285 error hint (L204-232) which tells users the supported range is
   `mcp>=1.27.0,<3` (strings at L218, L221) — must become `mcp>=2,<3` or the
   hint will misdiagnose the next import break.

---

## 5. Dependencies & CI — every place that must change

### 5.1 Dependency declarations

| Place | Current | Change |
|-------|---------|--------|
| `pyproject.toml:32-36` | comment (dual-major shim rationale) + `"mcp>=1.27.0,<3"` (L36) | `"mcp>=2,<3"` (issue #369's exact floor spelling); rewrite comment: 2.x-only, shim retired, pre-validation now in `server.py`. |
| `requirements.txt:1-4` | header comment + `mcp>=1.27.0,<3` (L4) | Same floor + comment rewrite. Header "1.27.0+ required for anyio compatibility" is stale under the new floor. |
| `jsonschema` | **Not declared** anywhere in `pyproject.toml`/`requirements.txt`; the shim relies on it transitively (docstring L22: "a hard mcp 2.x dependency") | **[probe]** verified hard dep of mcp 2.3.0 (`jsonschema>=4.20.0`). Phase 1 may keep relying on it, but since G1 code now lives in `server.py` permanently, the lead should consider declaring `jsonschema` directly — a one-line addition that removes a transitive-dep assumption. Flagged, not required. |

### 5.2 `tests/test_dependency_bounds.py` (89 lines) — rewrite

- Module docstring (L1-26) and all three tests assert the *dual* range.
- `test_installed_mcp_major_version_is_supported` (L49-62): `major in (1, 2)` →
  `major == 2`; message text naming `mcp_compat.py`'s two APIs must be rewritten.
- `test_pyproject_mcp_requirement_has_upper_bound` (L65-77) /
  `test_requirements_txt_mcp_requirement_has_upper_bound` (L80-89): both assert
  only `"<3" in requirement`. **Insufficient after the floor raise:** they would
  still pass with `mcp>=1.27.0,<3`. Add a floor assertion (`>=2` present /
  `1.27` absent) to both, or the exact regression #369 exists to prevent
  (floor silently staying at 1.x) is unguarded.
- `KNOWN_UNCAPPED_DEPS` (L37-44): unrelated to mcp; keep.

### 5.3 CI workflows

| Place | Current | Change |
|-------|---------|--------|
| `.github/workflows/test.yml:4-9` | header describes full tier as "py3.10/3.12 x mcp 1.27.0/latest" | Update prose: the mcp axis becomes a *2.x floor* axis (see next row). |
| `.github/workflows/test.yml:69,74-80` | matrix `mcp: ["1.27.0", "latest"]` on full tier; fast tier `["latest"]`; comment L74-77 justifies two cells by "two live registration paths" | The two-path rationale **dies with the shim**. Replace floor cell `"1.27.0"` with the oldest supported 2.x — recommend `"2.0.0"` (first 2.x; catches accidental use of 2.1+ APIs) — matrix becomes `["2.0.0", "latest"]`. Fast tier unchanged. |
| `.github/workflows/test.yml:94-96` | "Downgrade mcp to floor under test" step (`pip install "mcp==${{ matrix.mcp }}"`) | Mechanism unchanged; it will simply install 2.0.0. No edit beyond the matrix value. |
| `.github/workflows/test.yml:115` | comment referencing the 2.0.0 decorator-removal collection break | Historical; may stay or be trimmed. Non-blocking. |
| `.github/workflows/publish.yml:25` | comment "py3.10/3.12 x mcp 1.27.0/latest" | Prose update to match test.yml. |
| `.github/workflows/publish.yml:56-108` (smoke job) | installs wheel, smoke-tests under resolved mcp, **then downgrades to `mcp==1.27.0` (L105) and smoke-tests again (L106-108)** | **Delete the 1.x floor block (L104-108)** — under `mcp>=2,<3` metadata, installing 1.27.0 against the wheel is a resolver conflict, and the dual-support rationale in the job comment (L60-68) must be rewritten to "resolved 2.x only" (or, if the lead wants a floor smoke, downgrade to `mcp==2.0.0` instead — recommend this, it preserves the job's original two-cell value). |
| `.github/workflows/dep-cap-canary.yml` | No mcp pin or version literal (grep-verified); it reads caps from `pyproject.toml` via `scripts/cap_canary.py` | **No functional change.** Cosmetic only: `scripts/cap_canary.py:6` docstring example still says `mcp>=1.27.0,<2` (pre-#83 text, already stale today). |
| `scripts/validate_integrity.py` | No shim/mcp-version references (grep-verified; its runtime tool-count check imports `list_tools` from `flextoolsmcp.server`, which survives) | No change. |

### 5.4 Non-blocking text (do not gate Phase 1 on these)

- `CHANGELOG.md:559,580,583` — historical entries describing the shim's
  introduction and the `<3` cap. **Do not rewrite history**; add a new entry
  for the floor raise + shim removal in the release that ships it.
- `docs/TODO.md:27` — notes a 1.27.0 `call_tool` tuple-return behavior;
  stale under 2.x-only, worth a one-line tidy, not a blocker.
- `specs/mcp2-compat/README.md` + `deferred-issues.md` — the archived #83
  record; leave as history. (Its draft issue #1, "Port to mcp 2.0", is
  superseded by #369.)

---

## 6. Other 1.x-isms in `src/` (grep sweep)

Swept for: `hasattr` probes on mcp objects, version parsing of the mcp package,
camelCase/snake_case dual-spelling reads, `Server(` constructions, all
`from mcp` imports. Findings:

1. **The shim is the only concentration.** Outside it, dual-spelling *reads*
   exist at exactly one production site: the `server.py:950` gate (via E4).
   Everywhere else, mcp types are used construction-only or not at all.
2. **CamelCase *construction* kwargs (keep — verified working on 2.x):**
   - `server.py:869` `Tool(..., inputSchema=schema)` in `list_tools()`.
   - `src/flextoolsmcp/server/tool_definitions.py`: every `ToolAnnotations(...)`
     uses camelCase kwargs — `READ_ONLY_SAFE` (L90-95) and per-tool annotations
     at L369-374, L401-407, L445-450, L715-720, L743-748, L824-829 (representative;
     all follow the same pattern).
   - **[probe 2.3.0]** pydantic alias construction accepts both spellings;
     attribute *reads* accept only snake_case. So these sites need **no change**
     for correctness. Converting them to snake_case in Phase 1 is optional
     consistency churn (~30 lines in `tool_definitions.py`); recommend deferring
     it to a separate cosmetic PR so Phase 1's diff stays behavioral-zero.
3. **All other `from mcp` imports in `src/`** are `TextContent`-only and
   major-insensitive: `response_utils.py:23`, `server/dispatch.py:12`,
   `server/handlers/*.py` (admin, api, catalog, diagnostic_health, discovery,
   equivalence, execution, grammar_health, parse/*), `server/kernel.py:43-45`,
   `server/tool_definitions.py:13` (`ToolAnnotations`), `server.py:68,170-174`.
   No changes.
4. **No mcp version parsing anywhere in `src/`** outside E2/`kernel.py:510-533`
   (both parse the *flextools-mcp* version, not mcp's) and the
   `server/__init__.py:212` diagnostic hint (reads mcp's version for an error
   message only — §4.3). No `packaging.version`, no `mcp.__version__` probes.
5. **No other `Server(` constructions** in `src/`: only `kernel.py:828` (§3)
   and the shim itself (grep-verified).
6. **Non-mcp `hasattr` hits are unrelated** (AST nodes, LCM objects, session
   state) — e.g. `flexicon_analyzer.py`, `server/validators.py`,
   `response_utils.py:201`. Not 1.x-isms; do not touch.

---

## 7. Discrepancy in issue #369 Phase 1 — lead ruling needed

The issue text (Phase 1, bullets 2-3) instructs: *"Replace the low-level
`Server` + `mcp_compat.build_server()` adapter with `from mcp.server import
MCPServer`, keeping the existing `list_tools()` / `call_tool(name, arguments)`
handler functions (their signatures already match the 2.x `on_list_tools=` /
`on_call_tool=` shape)."* Verified against mcp 2.3.0 **[probe]**:

- `MCPServer` exists (`mcp.server.mcpserver.server.MCPServer`) but is the
  high-level framework class: it takes `name, version="", instructions=…,
  tools: list[Tool] | None` and exposes `.tool()`/`.add_tool()`/
  `.run_stdio_async()` etc. It does **not** accept `on_list_tools=` /
  `on_call_tool=` kwargs, and it does not preserve the
  `server.run(read, write, server.create_initialization_options())` stdio
  path in `server.py:1278-1283`.
- The `on_list_tools=` / `on_call_tool=` shape belongs to the **low-level
  `Server`** — the very class the issue says to replace — and even there,
  `call_tool(name, arguments) -> list[TextContent]` does **not** "already
  match": `on_call_tool` is `(ctx, CallToolRequestParams) -> CallToolResult`.
  The adapter (E10) is what bridges that gap, on any 2.x path that keeps
  the existing dispatch.
- The issue's own non-goals say *"No switch to the independent FastMCP 3.x
  framework… the official mcp 2.x `MCPServer` fits the existing hand-rolled
  dispatch"* — the probe shows it does not fit without re-plumbing tool
  registration and the run path.

**Recommendation to the lead:** Phase 1 = floor raise + inline the shim's 2.x
branch into `server.py` on the low-level `Server` (this report's §1/§8 plan;
behavioral-zero, ~11 files). Treat `MCPServer` adoption, if still wanted, as
its own phase with its own audit — it changes tool registration, the stdio
run path, and where G1 pre-validation would live. Note the low-level path
already gets #369's Phase 1 acceptance item "`server/discover` advertises
correctly" for free: **[probe]** 2.3.0 low-level `Server` registers a native
`server/discover` handler.

---

## 8. Phase 1 change-list estimate

| # | File | Change | Approx LOC |
|---|------|--------|-----------|
| 1 | `src/flextoolsmcp/mcp_compat.py` | **Delete** | −355 |
| 2 | `src/flextoolsmcp/server.py` | Inline E2/E4/E7/E8/E9/E10 above L1134; replace L1134 construction; fix 2 import lines (L91, L109); refresh stale comments (L70, L728-732, L853, L901, L1129-1133, L946-947) | +150 / −20 |
| 3 | `src/flextoolsmcp/server/__init__.py` | Comment (L126-129) + #285 hint range strings (L218, L221) | ~8 |
| 4 | `pyproject.toml` | Floor `mcp>=2,<3` + comment (L32-36); optional direct `jsonschema` dep (§5.1) | ~6 |
| 5 | `requirements.txt` | Floor + header comment (L1-4) | ~5 |
| 6 | `tests/test_mcp_compat.py` → successor wiring-test file | Rewrite 12/13 tests against moved adapters; drop MCP2 test + dual-spelling helpers | ~200 (replaces 216) |
| 7 | `tests/test_mcp_tools.py` | 6 import sites → direct reads / moved adapters (L203, L227, L239, L250, L264, L431-437) | ~20 |
| 8 | `tests/test_filing_cancel.py` | L130-137 → direct reads | ~8 |
| 9 | `tests/test_parse_diff.py` | L337-344 → direct reads | ~8 |
| 10 | `tests/test_parse_text_handler.py` | L307-314 → direct reads | ~8 |
| 11 | `tests/test_server_instructions.py` | L31-46 → direct `Server` construction | ~12 |
| 12 | `tests/test_dependency_bounds.py` | Rewrite docstring + 3 tests; add floor assertions (§5.2) | ~60 (replaces 89) |
| 13 | `.github/workflows/test.yml` | Matrix floor cell `1.27.0`→`2.0.0` + header/comment prose (L4-9, L74-80) | ~12 |
| 14 | `.github/workflows/publish.yml` | Smoke job: remove/replace 1.27.0 floor block (L104-108) + comments (L25, L60-68) | ~12 |
| 15 | New tests (§2.1) | Real-construction version test (a); optional `server/discover` smoke (b) — (b) is new harness work, size separately | +20 (a only) |

**Totals:** ~15 files touched (1 deleted, 1 test file replaced in place),
**≈ +430 / −600 LOC, net ≈ −170**. Production-code change is confined to
`server.py` (+~130 net) and two text-only files; everything else is tests,
pins, and CI. No changes to `kernel.py`, `dispatch.py`, any `handlers/*.py`,
`tool_definitions.py`, `_dual_path.py`, or `response_utils.py`.

**Sequencing note for the implementer:** rewire `test_mcp_tools.py:424-448`
(the G1 wire test) *first* and keep it green at every step — it is the only
test that proves the migration's one real behavioral risk stayed closed.
