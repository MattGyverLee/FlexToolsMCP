# Cycle 1 — Protocol audit: mcp 2.3.0 low-level `Server` vs `MCPServer` (issue #369)

Reviewer: lex-protocol (read-only audit; no code changed).
Evidence base: the **installed** mcp 2.3.0 in `/tmp/mcp2-probe` — all citations
below are `path:line` relative to
`/tmp/mcp2-probe/lib/python3.12/site-packages/` unless prefixed `repo:`.
Repo citations are relative to this worktree (`feat/369-mcp-modernization`).
Runtime probes were executed with `/tmp/mcp2-probe/bin/python`.

## Verdict up front

**Lead's probe is confirmed, and the picture is stronger than the probe.**
Phase 1 of issue #369 as prescribed (`from mcp.server import MCPServer`) names
the wrong class for this repo. `MCPServer` is the renamed FastMCP framework;
the low-level `Server` in 2.3.0 already (a) takes exactly the
constructor-injected `on_list_tools=`/`on_call_tool=` handlers the existing
shim's 2.x branch builds, (b) serves both protocol eras including stateless
2026-07-28 `server/discover` with **zero app code**, and (c) needs no
framework rewrite to keep this repo's single dispatch function.

**Recommendation: Shape A** — 2.x-only low-level `Server`, shim inlined and
deleted — with two qualifications developed below: the shim's jsonschema
pre-validation must survive the inlining (§1.4), and "inlined" must not mean
deleting the shim's cross-spelling helpers that other modules/tests import
(§7).

---

## 1. Low-level `Server` in 2.3.0: run/stdio, dual era, `server/discover`

### 1.1 Identity and constructor shape

- `mcp/server/__init__.py:5-8` exports both classes side by side:
  `Server` from `.lowlevel`, `MCPServer` from `.mcpserver`, plus
  `ServerRequestContext` from `.context`. They are distinct classes, not
  aliases (probe: `Server.__module__ == "mcp.server.lowlevel.server"`,
  `MCPServer.__module__ == "mcp.server.mcpserver.server"`).
- `mcp/server/fastmcp.py:1-10` is a tombstone: importing it raises
  `ModuleNotFoundError` saying "FastMCP was renamed to MCPServer
  (`from mcp.server.mcpserver import MCPServer`)". This settles the lineage:
  `MCPServer` = FastMCP, not a renamed low-level server.
- Low-level ctor: `mcp/server/lowlevel/server.py:129` (`class Server`),
  signature at `:330-405` (implementation overload): positional `name`,
  keyword-only `version: str = ""`, `title`, `description`, `instructions`,
  `website_url`, `icons`, `cache_hints`, `lifespan`,
  `get_tool_input_schema`, then handler kwargs `on_list_tools`
  (`:153`-style typed as
  `(ctx, PaginatedRequestParams|None) -> Awaitable[ListToolsResult]`),
  `on_call_tool` (`(ctx, CallToolRequestParams) ->
  Awaitable[CallToolResult | InputRequiredResult]`), `on_list_resources`,
  `on_read_resource`, `on_list_prompts`, `on_get_prompt`, `on_completion`,
  `on_ping` (defaulted), etc. Probe confirms `hasattr(Server, "call_tool")
  is False` — the 1.x decorator API is gone, as the shim assumes
  (`repo:src/flextoolsmcp/mcp_compat.py`, `MCP2 = not hasattr(Server,
  "call_tool")`).

### 1.2 `run()` / stdio serving — unchanged for this repo

- `mcp/server/lowlevel/server.py:703` `async def run(self, read_stream,
  write_stream, initialization_options, raise_exceptions=False)`: docstring
  calls it a "thin wrapper over `serve_dual_era_loop`"; it enters
  `self.lifespan(self)` and delegates. No `stateless` kwarg (dropped vs 1.x;
  the repo never passed it).
- `create_initialization_options()` (`lowlevel/server.py:539`) gains only an
  additive `extensions=None`; `stdio_server()` keeps its `(read, write)` CM shape.
- Repo call site needs **no change** (`repo:server.py:1278-1283`:
  `stdio_server()` + `server.run(…, server.create_initialization_options())`).

### 1.3 Both eras are served by the one `run()`

- `mcp/server/runner.py:602` `serve_dual_era_loop`: "The client's first
  request decides the connection's protocol era, once: a request carrying
  the 2026-07-28 per-request `_meta` envelope opens a modern connection, and
  anything else — the `initialize` handshake … — opens a legacy one."
  Dispatch at `runner.py:629-645` to `_serve_modern_stream` (`:755`) or
  `_serve_legacy_stream` (`:717`). Cross-era claims are refused both ways:
  enveloped request on a legacy connection → `INVALID_REQUEST`
  (`runner.py:741-748`); `initialize` on a modern connection →
  `UNSUPPORTED_PROTOCOL_VERSION` (`runner.py:772-778`).
- Legacy path: `initialize` is handled inline by the runner
  (`_handle_initialize` `runner.py:428-446`; negotiation `:421-426` falls back
  to `LATEST_HANDSHAKE_VERSION`); pre-init gate `runner.py:211`,
  `_INIT_EXEMPT={"ping"}` (`:92`); `add_request_handler("initialize",…)` raises
  `ValueError` (`lowlevel/server.py:484-510`).
- Modern path: no handshake at all. Each request builds a "born-ready"
  `Connection.from_envelope(...)` (`mcp/server/connection.py:260`) from the
  `_meta` envelope and is served via `serve_one` (`runner.py:815`).
- Era registry: `mcp_types/version.py:33-41` — HANDSHAKE = 2024-11-05…
  2025-11-25; `MODERN_PROTOCOL_VERSIONS = ("2026-07-28",)`.

### 1.4 `server/discover`: free, auto-derived — what the app must supply

- Registered **unconditionally** in the ctor's spec table:
  `lowlevel/server.py:460` —
  `("server/discover", types.RequestParams, self._handle_discover)`.
  Probe: a bare `Server("x")` with no handlers already has
  `_request_handlers == ["ping", "server/discover"]`.
- Handler: `lowlevel/server.py:672-692` `_handle_discover` returns
  `types.DiscoverResult(supported_versions=list(MODERN_PROTOCOL_VERSIONS),
  capabilities=self.get_capabilities(protocol_version=ctx.protocol_version),
  instructions=self.instructions)`. Docstring: "Auto-derived from server
  state at call time … Operators can replace it wholesale via
  `add_request_handler("server/discover", …)`."
- Reachability is era-gated at the boundary, not in the handler:
  `mcp_types/methods.py` `CLIENT_REQUESTS` contains
  `("server/discover", "2026-07-28")` and no legacy-era row for it.
- `DiscoverResult` shape (`mcp_types/_types.py:593-608`): `supported_versions`,
  `capabilities`, `instructions: str | None = None`,
  `result_type = "complete"`. It inherits `CacheableResult`
  (`_types.py:198-213`) so `ttl_ms` defaults to `0` and `cache_scope` to
  `"private"` — the app does **not** need to set cache fields for a valid
  2026-07-28 result.
- **Name/version are not in `DiscoverResult` at all.** Identity is supplied
  once, at construction, and reaches modern clients two ways:
  (1) `Server.server_info` (`lowlevel/server.py`, `server_info` property:
  `types.Implementation(name=self.name, version=self.version, title=…,
  description=…, website_url=…, icons=…)`);
  (2) the runner stamps it into every modern-era result's `_meta` —
  `ServerRunner._stamp_server_info` (`runner.py:396-419`), applied in
  `_serialize` (`runner.py:341-395`), key `SERVER_INFO_META_KEY`, only when
  `version in MODERN_PROTOCOL_VERSIONS`.
- Capabilities are derived from what is registered:
  `get_capabilities` (`lowlevel/server.py:567-638`) — a tools capability
  exists iff `"tools/list"` is in `_request_handlers`; at modern versions
  the `listChanged`/`subscribe` flags derive from whether
  `subscriptions/listen` is served, ignoring the legacy
  `NotificationOptions`. Extensions map: `self.extensions`
  (`lowlevel/server.py:455`), surfaced via
  `create_initialization_options(extensions=…)`.
- **App obligations (complete list):** pass `name`, an explicit `version`,
  and `instructions` to the ctor, and register `on_list_tools`. The explicit
  version matters: the ctor default is `""` and the `server_info` docstring
  states "the SDK never substitutes its own" — the shim's
  `resolve_server_version()` behaviour (`repo:mcp_compat.py`) must be kept
  in the inlined Shape-A code. This repo already passes both
  (`repo:server.py:1134-1135`, `build_server("flextools-mcp", list_tools,
  call_tool, instructions=SERVER_INSTRUCTIONS)`).

### 1.5 One caveat the inlining must preserve: input pre-validation

The low-level runner validates the **envelope**, not per-tool arguments:
`ServerRunner._on_request` (`runner.py:185-230`) surface-validates spec
requests via `_methods.validate_client_request(...)` and validates params
against `entry.params_type` — for `tools/call` that is
`CallToolRequestParams` (`mcp_types/_types.py`, `name: str`,
`arguments: dict[str, Any] | None`). Nothing in `runner.py` consults a
tool's `inputSchema`. (`get_tool_input_schema` is used only for
`Mcp-Param-*` header validation on the modern Streamable-HTTP path,
`mcp/server/_streamable_http_modern.py:343-372` — irrelevant to stdio.)
So the shim's jsonschema pre-validation
(`repo:mcp_compat.py:make_call_tool_handler`, incl. its cold-session-gate
ordering rationale) is **still load-bearing in 2.3.0** and must be carried
into the inlined handler, not deleted with the shim.

---

## 2. Progress from a low-level `on_call_tool` handler

### 2.1 The context a low-level handler actually gets

Handlers receive `ServerRequestContext`, **not** the ergonomic `Context`:
`mcp/server/context.py:31-48` — a dataclass with `session: ServerSession`,
`lifespan_context`, `protocol_version`, `method`, `params`, `request_id`,
`meta: RequestParamsMeta | None`, `request`, SSE-close callbacks. It has
**no** `report_progress` method of its own. The richer
`mcp/server/context.py` `Context` class (which does expose progress via
`BaseContext`) states in its docstring: "Not currently constructed by
`ServerRunner`, which hands handlers a `ServerRequestContext` instead."

### 2.2 Exact usable call shape

```python
async def on_call_tool(ctx, params):  # ctx: ServerRequestContext
    await ctx.session.report_progress(progress, total=None, message=None)
    ...
```

- `mcp/server/session.py:426-434` `ServerSession.report_progress(progress,
  total=None, message=None)`: "Report progress for the inbound request this
  session is scoped to. A no-op when the caller did not request progress."
  It delegates to `self._request_outbound.progress(...)`, where
  `_request_outbound` is the per-request `DispatchContext` the runner built
  (`runner.py:327`, `ServerSession(dctx, …, request_meta=…)`).
- This is the same sink the framework uses: `MCPServer`'s
  `Context.report_progress` (`mcp/server/mcpserver/context.py:120-128`) is
  literally `await self.request_context.session.report_progress(...)`, and
  `BaseContext.report_progress` (`mcp/shared/context.py:80-85`) delegates
  identically. There is one mechanism, three facades.

### 2.3 Where the token comes from (handler does not read it)

- The JSON-RPC dispatcher reads it: `progress_token_from_params`
  (`mcp/shared/jsonrpc_dispatcher.py:109-115`) — pattern-matches
  `params._meta.progressToken` as `str | int`, explicitly rejecting `bool`.
- It is stored on the per-request dispatch context at construction
  (`jsonrpc_dispatcher.py:149`, assigned `:602`) and consumed by
  `_JSONRPCDispatchContext.progress` (`:177-185`):

  ```python
  async def progress(self, progress, total=None, message=None):
      if self._progress_token is None:
          return
      params = {"progressToken": self._progress_token, "progress": progress}
      # + "total"/"message" when not None
      await self.notify("notifications/progress", params)
  ```

- **No token ⇒ silent no-op** (no exception); calling it unconditionally is the intended pattern.
- Token inspection (rarely needed): `params.meta["progress_token"]`
  (`RequestParams.meta`, alias `_meta`, `_types.py:80-105`; Python spelling
  vs wire `progressToken`, `mcp/shared/peer.py:52-54`); also `ctx.meta`
  pre-validation (`runner.py:99-107` `_extract_meta`).
- Manual alternative (not recommended): `ctx.session.send_progress_notification(token, …)`
  (`session.py:436-457`) — caller supplies the token, bypassing the no-op guard.

### 2.4 Era/direction nuance

- Server→client progress survives the modern era: modern dispatch wraps the
  context in `_NoServerRequestsDispatchContext` (`runner.py:552-600`),
  whose `send_raw_request` raises `NoBackChannelError` ("the modern protocol
  forbids server-initiated JSON-RPC requests") but whose `progress()`
  (`:598-599`) and `notify()` delegate to the inner context. Accordingly
  `mcp_types/methods.py` `SERVER_NOTIFICATIONS` includes
  `("notifications/progress", "2026-07-28")`.
- The deprecated direction is the reverse: client→server progress.
  `CLIENT_NOTIFICATIONS` has no `notifications/progress` row for
  2026-07-28, and passing `on_progress=` to the low-level ctor emits an
  `MCPDeprecationWarning` ("Client-to-server progress is deprecated as of
  2026-07-28", `lowlevel/server.py:413-419`).
- Repo impact: nothing to migrate today (no progress use in
  `repo:server.py`/`dispatch.py`), but adopting progress for long index
  builds requires threading `ctx` through the adapter — the current shim
  signature `call_tool_fn(name, arguments)` discards it
  (`repo:mcp_compat.py:make_call_tool_handler`). That threading is a
  Shape-A-preserving change: adapter keeps `ctx` and passes
  `ctx.session.report_progress` (or `ctx`) into dispatch.

---

## 3. Tasks extension (`io.modelcontextprotocol/tasks`): not in the box

- **No ctor parameters.** The full low-level ctor list (§1.1) contains no
  `on_create_task`/`on_get_task`/`on_list_tasks` or any tasks hook; the
  spec-handler table (`lowlevel/server.py:458-479`) registers no `tasks/*`
  method. `MCPServer`'s ctor likewise has no tasks parameter.
- **Types-only, deliberately undispatched.** `mcp_types/_types.py:610-612`:
  "Tasks: introduced in 2025-11-25, removed from the core spec in
  2026-07-28 (continuing as an extension). Defined here types-only; their
  methods are not in the request/notification unions below, so they are
  never dispatched." The models still exist — `Task`, `CreateTaskResult`,
  `GetTaskRequest` (`tasks/get`), `CancelTaskRequest` (`tasks/cancel`),
  `GetTaskPayloadRequest` (`tasks/result`), `ListTasksRequest`
  (`tasks/list`) at `_types.py:630-740`; `CallToolRequestParams.task:
  TaskMetadata | None` is annotated "(2025-11-25 only)";
  `ServerCapabilities.tasks` (`_types.py:511-512`) is likewise
  "(2025-11-25 only)" and `get_capabilities` never populates it.
- **Surface maps exclude it everywhere:** `mcp_types/methods.py` annotates
  its 2025-11-25 blocks "(tasks/* deliberately absent)" (`:101`, `:174`)
  and "(tasks/status deliberately absent)" (`:146`, `:209`); there are no
  `tasks/*` rows for 2026-07-28 either.
- **No implementation anywhere in the package:** a package-wide search for
  `tasks/list|tasks/get|tasks/result|tasks/cancel|CreateTaskResult` in
  `mcp/` returns only the docstring example in `mcp/server/extension.py:59`
  ("A new request method an extension serves, e.g. `tasks/get`"). The
  string `io.modelcontextprotocol/tasks` appears only as a generic
  extension-identifier example in a capabilities docstring
  (`mcp_types/_v2026_07_28/__init__.py:2057`). **Client side: zero** tasks
  methods in `mcp/client/**`.
- **What adoption would require (all hand-rolled):**
  1. A task store (id minting, status state machine
     `working|input_required|completed|failed|cancelled`, TTL/retention,
     poll-interval, result payload retention) — nothing provided.
  2. Handlers for `tasks/get`, `tasks/list`, `tasks/result`,
     `tasks/cancel` (+ optionally `notifications/tasks/status`), registered
     either via low-level `Server.add_request_handler(method, params_type,
     handler)` (`lowlevel/server.py:484`) — non-spec methods fall through
     the runner's surface gate to `entry.params_type` validation
     (`runner.py:191-198` comment) — or as a SEP-2133 `Extension`
     (`mcp/server/extension.py:96`, `MethodBinding` at `:59-90`;
     `MCPServer(extensions=[...])` advertises settings under
     `capabilities.extensions[identifier]`).
  3. Advertising: manually set `server.extensions["io.modelcontextprotocol/
     tasks"] = {...}` (low-level) or the extension's `settings()`.
  4. Task-augmented `tools/call` handling: intercept `params.task`, return
     `CreateTaskResult` instead of executing synchronously — the runner
     gives no help; this would live inside this repo's dispatch.
  5. Own client story: SDK clients in 2.3.0 cannot consume it.
- **Stability verdict: experimental / not-yet-an-extension in this SDK.**
  In 2.3.0 tasks is a removed core feature with retained types and an
  architectural placeholder (SEP-2133), not a shipped extension. Issue
  #369 should treat tasks as **deferred research**, not a Phase deliverable;
  progress (§2) is the available mechanism for long-running index builds
  today.

---

## 4. Structured output: who validates what

### 4.1 Low-level server side: no output-schema validation

- The runner's only result pass is `_serialize` (`runner.py:341-395`):
  cache-hint filling, per-version **surface sieve** via
  `_methods.serialize_server_result(method, version, dumped)` (validates
  the result against the wire model for that method/version — i.e. that a
  `CallToolResult` is well-formed), `resultType` completion, and the
  `serverInfo` stamp. It never looks up the called tool, let alone its
  `output_schema`. A low-level handler may return any
  `structured_content` (or none) regardless of the advertised schema.
- (Framework contrast: `MCPServer` validates server-side against a pydantic
  model, not the JSON Schema — `FuncMetadata.convert_result`,
  `func_metadata.py:186-226`. The low-level path does not inherit this.)

### 4.2 Client side: the SDK client enforces it, hard

- `mcp/client/session.py:1100-1103`: after `call_tool`, any non-error
  `CallToolResult` goes to `validate_tool_result(name, result)`.
- `validate_tool_result` (`client/session.py:1118-1155`): looks up the
  tool's cached `output_schema` (populated by `list_tools`,
  `:1317-1327`). If a schema exists:
  - `structured_content is None` **and** `"structured_content" not in
    result.model_fields_set` → `RuntimeError("Tool {name} has an output
    schema but did not return structured content")` (`:1139-1140`). Note
    the subtlety: an explicitly-set `structured_content=None` escapes the
    missing check and is instead schema-validated as `None`.
  - Otherwise the content is validated with a compiled `jsonschema`
    validator (`_output_schema_validator`, `:1156-1181`, cached per
    schema); any error → `RuntimeError("Invalid structured content
    returned by tool {name}: …")`; an unresolvable `$ref` or invalid
    schema → `RuntimeError` as well.

### 4.3 What `CallToolResult` requires

- Monolith model `mcp_types/_types.py:1463-1485`: `content: list[
  ContentBlock]` (required), `structured_content: Any = None`,
  `is_error: bool = False`, `result_type: ResultType = "complete"`.
  Probe: `CallToolResult(content=[])` dumps to `{"content": [],
  "structuredContent": None (excluded on wire by exclude_none),
  "isError": False, "resultType": "complete"}`.
- Era difference: 2026-07-28 `structured_content` is any JSON value;
  2025 eras restrict it to a JSON object (`_types.py:1470-1473`).
- **Consequence for this repo:** the disabled-`outputSchema` note at
  `repo:src/flextoolsmcp/server.py:871-882` remains exactly right under
  2.3.0. Advertising `outputSchema` while `call_tool` returns text-only
  makes the *SDK's own client* raise on every successful call. Enabling
  structured output is a coupled change: advertise the schema **and** have
  the dispatch return `CallToolResult(content=[...],
  structured_content=<dict>)` — in Shape A that means extending the
  inlined `on_call_tool` adapter (today it wraps
  `CallToolResult(content=list(content))`, `repo:mcp_compat.py`) to thread
  an optional structured payload out of dispatch, then validating handler
  dicts against the `*Success` models as the repo note prescribes.

---

## 5. Version policy 2.0.0 → 2.3.0

### 5.1 What cannot be verified from the installed package

There is **no changelog, HISTORY, migration guide, or any `.md`/`.rst`
file inside the installed `mcp` or `mcp_types` packages** (verified by
filesystem search; each `*.dist-info` contains only `METADATA`, `RECORD`,
`WHEEL`, `licenses/`). `METADATA` links externally to
`https://py.sdk.modelcontextprotocol.io/` ("What's new in v2", migration
guide) — outside the evidence base of this audit. Any claim about
individual 2.0.x→2.3.0 changes is therefore **unverifiable from source
alone** and is not made here.

### 5.2 What the 2.3.0 source does establish

- The 2.0 break itself, still in force: decorator API absent (probe,
  §1.1); `mcp.server.fastmcp` tombstone (`fastmcp.py:1-10`); types split
  into a separate distribution pinned exactly — `METADATA`:
  `Requires-Dist: mcp-types==2.3.0`; `mcp/types/__init__.py` is a 31-line
  re-export layer over `mcp_types`. Canonical field names are snake_case
  with camelCase pydantic aliases preserved (the repo's camelCase kwargs
  in `Tool(...)`/`CallToolResult(...)` continue to construct — consistent
  with the shim's verified claim).
- Announced 3.0 removals visible as deprecations in 2.3.0:
  `FuncMetadata.call_fn_with_arg_validation` ("deprecated and will be
  removed in 3.0", `func_metadata.py:165-170`); logging, roots, and
  client→server progress deprecated as of 2026-07-28 / SEP-2577
  (`lowlevel/server.py:209-215`, warnings at `:405-419`);
  `SUPPORTED_PROTOCOL_VERSIONS` kept as a deprecated union alias
  (`mcp_types/version.py:44-50`). None of these touch this repo's surface
  (it uses none of logging/roots/progress-inbound).
- Provisional-within-2.x surfaces (explicit in-source warnings):
  `Server.middleware` — "TODO(L54): provisional — signature and semantics
  may change in a 2.x minor release" (`lowlevel/server.py:448-450`);
  dispatcher lifecycle — "The lifecycle surface is provisional; `run()` may
  change in a 2.x minor release" (`mcp/shared/dispatcher.py:257-260`);
  capabilities API rethink TODO (`lowlevel/server.py:534-538`). This repo
  uses **none** of the provisional surfaces; its entire contact area is
  ctor handlers, `run()`, `create_initialization_options()`,
  `stdio_server()`, and `mcp.types` models.
- Shape stability across the 2.x line is corroborated from the repo side:
  the shim header records decorator-absence "verified against 2.0.0 and
  2.2.0"; this audit re-verified the identical ctor/handler/discover shape
  against 2.3.0.
- Packaging: `Requires-Python: >=3.10`; deps include `pydantic>=2.12.0`,
  `jsonschema>=4.20.0`, `httpx2>=2.10.0` (the fork, not `httpx`) (`METADATA`).

### 5.3 Recommendation

**Pin `mcp>=2,<3`** (i.e. keep the existing `<3` ceiling pattern from
`repo:pyproject.toml:36`, raising the floor from `>=1.27.0` to `>=2` when
Shape A lands). Reasoning:

- `<3` is mandatory, not cautious: 3.0 removals are already announced in
  the 2.3.0 source (above), and 2.0 demonstrated this project's willingness
  to remove APIs at a major.
- Do **not** floor at `>=2.1`/`>=2.3`: no feature this repo needs is
  attributable to a specific 2.x minor — dual-era serving, discover,
  progress, and the handler shape are architectural (present in the 2.0
  design and re-verified in 2.3.0). A higher floor would exclude users for
  no named benefit.
- Do **not** pin `==2.3.0`: minors/patches are where the provisional-surface
  churn lives, but they are also where protocol-surface fixes land; the
  repo's narrow, non-provisional contact area makes riding `>=2,<3` with
  CI resolving latest (plus the existing wheel smoke test) the right
  risk posture. If a future minor breaks the narrow surface, the failure
  mode is loud at import/ctor time, not silent.

---

## 6. Does `MCPServer` offer a single-dispatch escape hatch?

**Technically yes; as a supported API, no.** Detail:

- `MCPServer` is a composition layer over a private low-level server:
  `mcp/server/mcpserver/server.py:212-232` constructs
  `self._lowlevel_server = Server(..., on_list_tools=self._handle_list_tools,
  on_call_tool=self._handle_call_tool, on_list_resources=…,
  get_tool_input_schema=self._tool_input_schema, …)`. Its own stdio runner
  is `self._lowlevel_server.run(…, self._lowlevel_server.
  create_initialization_options())` (`:1074-1080`). Pass-through properties
  expose `name`, `version`, `instructions`, `middleware`,
  `session_manager` — but **not** the low-level server itself; reaching it
  means using the private `_lowlevel_server` attribute.
- There is **no ctor escape hatch**: `MCPServer.__init__` (`:158-190`)
  accepts `tools: list[Tool] | None` (framework `Tool` objects managed by
  its `ToolManager`), `resources`, `extensions`, auth, lifespan,
  `middleware` — no `on_list_tools=`/`on_call_tool=` parameter exists.
- Post-construction replacement is demonstrably possible, because the
  framework does it to itself: `_apply_extension` registers extension
  methods via `self._lowlevel_server.add_request_handler(...)`
  (`:350`), and `_install_extension_interceptor` replaces the `tools/call`
  handler with `compose_tool_call_handler(self._extensions,
  self._handle_call_tool)` (`:363-368`). `Server.add_request_handler`
  (`lowlevel/server.py:484`) replaces any method except `initialize`.
  So `mcp_server._lowlevel_server.add_request_handler("tools/call",
  CallToolRequestParams, my_dispatch)` would work — while relying on a
  private attribute, fighting the `ToolManager` registry (which would
  still own `tools/list` unless also overwritten), and discarding the
  framework's argument validation that is the only thing the framework
  would have bought this repo.
- The sanctioned framework hook is narrower: SEP-2133 `Extension.intercept_tool_call`
  (`extension.py:135-155`) wraps `tools/call` around `call_next`; it can short-circuit
  but is designed to wrap the framework handler, not *be* a hand-rolled dispatch.
- Plainly: **if the goal is "keep our one dispatch function", the
  supported surface for that is the low-level `Server` itself.** The
  `MCPServer` route preserves the dispatch only through private-attribute
  surgery that negates the framework's benefits.

---

## 7. Verdict: Shape A vs Shape B, and what Shape A actually entails

**Shape A (2.x-only low-level `Server`, shim inlined + deleted) — adopt.**

For this repo it is a small, mechanical change, because the shim's 2.x
branch already *is* Shape A behind an indirection:

1. `repo:server.py:1134` keeps calling one builder with
   `(name, list_tools, call_tool, instructions=…)`; the builder body
   (ctor with `on_list_tools=make_list_tools_handler(...)`,
   `on_call_tool=make_call_tool_handler(..., make_schema_provider(...))`,
   explicit `version=resolve_server_version()`) moves into `server.py`
   (or a small `server/` module) unchanged in behaviour.
2. Delete from the shim: the `MCP2` probe, the 1.x decorator branch, and
   `_construct`'s bare-name fallback. **Keep and relocate** (do not delete):
   the jsonschema pre-validation (§1.5), `resolve_server_version` (§1.4),
   and the cross-spelling helpers `annotation_is_read_only` /
   `annotation_value` / `normalized_annotation_keys` / `tool_input_schema`
   — on a 2.x-only codebase the 1.x spellings become dead, but these
   helpers are imported by `server.py` and tests today; collapsing them to
   their snake_case-only forms is a separate small cleanup, not part of
   the deletion.
3. `pyproject.toml`: `mcp>=1.27.0,<3` → `mcp>=2,<3` (§5.3).
4. Gains for free, no code: dual-era serving and `server/discover`
   advertisement (§1.3-1.4); progress becomes available by threading
   `ctx.session` when wanted (§2); structured output remains an opt-in
   coupled change (§4.3); tasks remains deferred research (§3).

**Shape B (MCPServer framework rewrite) — reject for #369.** It would
require re-expressing this repo's tool surface (Pydantic input models in
`server/tool_definitions.py` feeding one `call_tool(name, arguments) ->
list[TextContent]` dispatch over `server/dispatch.py` + `handlers/*`) as
framework-managed tools: per-tool functions or `Tool` objects whose
arguments are validated by `FuncMetadata` *before* dispatch — inverting
the repo's deliberate ordering in which the cold-session gate in
`repo:server.py:call_tool` configures session state before re-validation
(the exact ordering the shim's pre-validation exists to preserve, §1.5).
It would also couple the repo to the framework's result conversion
(`func_metadata.py:186-226`), its `Context` injection model, and surfaces
the SDK itself marks provisional — in exchange for no protocol capability
the low-level server lacks. The one framework-only feature found,
server-side output-model validation (§4.1), does not require the
framework: the client already enforces `outputSchema` (§4.2), and the repo
can validate its own dicts against its `*Success` models in dispatch.

**Corrections to #369 Phase 1 as written:** (i) `MCPServer` → low-level
`Server`; (ii) discover needs no implementation phase — it ships with the
class; (iii) progress needs only `ctx` threading; (iv) tasks must not be
scheduled as an SDK adoption — there is nothing to adopt in 2.3.0.
