# Cycle 1 — Long-Running Operations Audit (lex-longops)

Issue #369, Phase 3: `notifications/progress` for the server's longest
operations, and evaluation of the `io.modelcontextprotocol/tasks` extension.
Worktree at `origin/main c1c751f`. READ-ONLY audit; no code changed.

## 0. Verdict up front

- **Confirmed premise:** `progressToken` is invisible everywhere.
  `grep -rn "progressToken|progress_token|send_progress" src/ tests/` returns
  zero hits. `server.py:903` is
  `async def call_tool(name: str, arguments: dict[str, Any])` — no context
  parameter — and `mcp_compat.make_call_tool_handler._on_call_tool(ctx, params)`
  **receives `ctx` on mcp 2.x and discards it**, delegating only
  `(name, arguments)`. Every handler is `async def handle_*(args: dict)`
  (31 routes in `server/dispatch.py:DISPATCH_ROUTES`).
- **Progress is feasible and cheap for the ops that are actually inside a
  request**, via one seam change in `mcp_compat` + a `ContextVar` reporter
  (the codebase already uses both patterns — §2). Per-op cost ranges from
  "reuse existing log points" (semantic search) to "heartbeat only"
  (`run_module`).
- **The single longest operation — index refresh — is not reachable from any
  request today** (§1.1). It runs at process startup, before `server.run()`,
  or as a standalone CLI. No `progressToken` can ever attach to it. Giving it
  progress first requires a product decision (a refresh *tool*), not plumbing.
- **Tasks extension: DECLINE for Phase 3** (§4). The ops that genuinely
  outlive a request already have a richer domain task system (parse runs);
  everything else is a bounded single call that progress + existing
  cancellation already serve. Revisit triggers are named in §4.4.

SDK facts below were verified against the installed mcp **2.3.0** in
`/tmp/ftmcp-venv` (pyproject allows `mcp>=1.27.0,<3`).

---

## 1. Inventory of long-running operations

### 1.0 Summary table

| # | Operation | Invoked by | Shape | Duration evidence | In a request? |
|---|-----------|-----------|-------|-------------------|---------------|
| A | Full index refresh (all builders) | CLI `flextools-mcp-refresh` / `python -m flextoolsmcp.refresh`; auto-refresh at startup | ~11 sequential `subprocess.run` children | `subprocess.run(..., timeout=300)` for the whole auto-refresh (`server.py:825`); comment at `server.py:303`: refresh "shells out … (seconds…)" per library, and there are 3 libraries + 6 post-processors | **No** — startup or CLI only |
| B | `flextools_run_module` user code | `flextools_run_module` → `handlers/execution.py:3866` → `run_script_async` (`server/subprocess_helpers.py:90`) | One async subprocess, `await process.communicate()`; stdout not streamed | Default `timeout_seconds=300` (`execution.py:5172`); helper default 120 s | Yes |
| C | Semantic-search model load (first search per process) | `flextools_search_by_capability` (`handlers/api.py:1413`) → `SemanticSearch.search` (`server.py:236`) | **Synchronous, event-loop-blocking** in-process call | Log: "Downloading embedding model … (~50MB…)"; FAISS import alone is documented as "14+ second startup cost" (`server.py:~208`) | Yes |
| D | Parse runs (single word, batch, filing, sandbox) | `flextools_try_word`, `flextools_parse_text`, `flextools_parse_sandbox`, filing via `parse_text(apply=true)` | **Already async/deferred**: `ParseRunner.start_run` (`server/parse/runner.py:606`), background task, per-word worker | Grace window default **5.0 s** (`runner.py:DEFAULT_GRACE_WINDOW_SECONDS`); batch runs are unbounded by design ("a run killed at word four thousand"); worker request timeouts 60/300/600 s (`parse/worker_client.py`); sandbox watchdog 600 s + 600 s generate timeout (`sandbox/client.py:104`, `sandbox/cache.py:158`) | Starts in one; **outlives it** |
| E | Grammar-health scan | `flextools_grammar_health` → `run_scan_module` (`execution.py:7229`) | One async subprocess (same seam as B) | `SCAN_TIMEOUT_SECONDS` = 300 s, "generous for a pure-LCM pass" (`grammar_health.py:80`) | Yes |
| F | Bounded word measurement | `flextools_try_word` measurement path (`parse/measure.py`) | Own worker, cooperative bound | Bound 1–600 s (`measure.py:74 MAX_BOUND_SECONDS=600.0`) | Yes |
| G | Embedding build (`build_embeddings.py`) | **Nothing in-server.** Standalone `__main__` script only | Sync in-process `model.encode(...)` over all items | No timing constants; encodes every entity+method text (thousands of items); only progress today is `show_progress_bar=True` to a console tqdm (`build_embeddings.py:248`) | No |
| H | Sandbox creation / corpus seeding | `flextools_parse_sandbox` actions `create_sandbox`, `seed_corpus` | Synchronous steps inside the handler (`handlers/parse/sandbox.py:368,690`); parse actions delegate to D | Stepwise handler (numbered steps 1–8); export is a project copy — size-dependent, no timeout constant found | Yes |

**Not long-running (checked, excluded):** all catalog/discovery/equivalence
handlers are in-memory dict lookups over pre-loaded indexes;
`flextools_manage_config` is a KV read/write (`handlers/admin.py:757`);
`flextools_prepare_report` is a local JSONL scan; `flextools_health` is
detector composition + a lock sweep. **No admin tool triggers a rebuild** —
`handle_start` only *reports* stashed startup refresh failures
(`handlers/admin.py:490,725`) and names the CLI command as the remedy.

### 1.1 Refresh and the builders it drives (A, G)

`refresh.py:main()` is a fixed sequential pipeline, each step a
`run_command(cmd, description)` → `subprocess.run(capture_output=True)`
(`refresh.py:~130`):

1. `flexicon_analyzer.py` → FlexLibs index; 2. same → Flexicon index;
3. `liblcm_extractor.py` → LibLCM index (best-effort, needs pythonnet +
   FieldWorks DLLs) + in-process `apply_categorization()`;
4. post-processors, each its own subprocess: `build_reverse_mapping.py`,
   `build_navigation_graph.py`, `build_casting_index.py`,
   `extract_patterns.py`, `build_element_types.py`,
   `build_getall_contract.py`; 5. `archive_old_versions.py`.

Every builder is a standalone `__main__` script with a pure
`build_*(...) -> dict` core and **no callback parameters anywhere**
(grep for `callback|Callable` across all builders: only
`build_embeddings.py`'s unrelated tqdm flag). None is importable as a
progress-reporting library call without new parameters.

Two reachability facts dominate Phase 3 scoping:

- **In-server refresh happens only inside `APIIndex.load()`**
  (`server.py:1165` in `main()`, and `server/kernel.py:844` in the legacy
  kernel init) via `_try_refresh_once` → `auto_refresh_missing_api_file`
  (`server.py:787`), guarded once-per-library-per-process
  (`_REFRESH_ATTEMPTED`). `main()` calls it **before**
  `stdio_server()`/`server.run()` — there is no client request, no session,
  and no token in existence yet. Progress notifications are
  request-scoped by definition; this path can never emit them.
- **`build_embeddings.py` is not part of the refresh pipeline at all**
  (absent from `refresh.py`'s step list). The shipped
  `index/embeddings/{embeddings.npy,faiss.index}` are regenerated only by
  running the script manually. Any Phase 3 line item saying "embedding
  builds get progress via refresh" is false today; it would need wiring
  into refresh first, which is a separate decision.

### 1.2 `run_module` (B) — the longest *routine* in-request op

Chain: `call_tool` → dispatch → `handle_run_module` → preflight gates →
optional pre-write backup → `run_script_async(temp_script_path,
timeout_seconds)` → single `await asyncio.wait_for(process.communicate(),
timeout)`. The child's stdout is **piped and read only at exit**; nothing
streams. The generated module's `report` object even carries the FLExTools
progress surface — `ProgressStart/ProgressUpdate/ProgressStop` at
`execution.py:5441` — as **no-op stubs**. So there are exactly two honest
progress levels for B: (a) milestone + elapsed heartbeat around the await,
(b) a future, larger change that streams child output lines and maps
`report.Progress*` calls onto notifications. Phase 3 should do (a) only.

### 1.3 Semantic-search first load (C) — the cheapest real win

`SemanticSearch.search` is called synchronously from an async handler. On
first use it lazy-loads `SentenceTransformer` (download ~50 MB if uncached),
then encodes. It is also the only long op that **blocks the event loop**,
which matters for §2: notifications queued during the load cannot flush
until it returns, so boundary notifications (before-load, after-load) are
what's achievable without moving the load to `asyncio.to_thread`.

### 1.4 Parse runs (D) — already a task system (see §4)

`ParseRunner.start_run` waits out a 5 s grace window on a *copy* of the
completion signal (FR-028: the window governs reporting, never execution),
then returns a `RunHandle{run_id, stage, words_completed, words_total}`.
Progress is already first-class: `_execute_run` increments
`handle.words_completed` per word and `_persist_progress` writes it to the
on-disk `RunRecord` **after every word** (FR-016); an observer hook
(`handle.observer.on_result/on_start/on_terminal`, `runner.py:534,721,885`)
already fans per-word events out. Clients poll via `flextools_parse_status`,
cancel via `flextools_parse_cancel`, read results via
`flextools_parse_log`/`_diff`, release via `flextools_parse_release`.

---

## 2. Call-chain trace: where a reporter must be threaded

```
client ──tools/call──► mcp framework
  2.x: mcp_compat._on_call_tool(ctx, params)      ← ctx DISCARDED today
  1.x: Server.call_tool() decorator ──► server.request_context (ContextVar in SDK)
        │
        ▼
server.py call_tool(name, arguments)              ← signature has no context
        │  get_tool_handler(name) → (handler, InputModel)
        ▼
dispatch.DISPATCH_ROUTES → handler(dumped: dict)  ← all 31 handlers, one arg
        │
        ├─► execution.handle_run_module ─► run_script_async (opaque await)
        ├─► api.handle_search_by_capability ─► SemanticSearch.search (sync)
        ├─► grammar_health ─► run_scan_module ─► run_script_async
        └─► parse handlers ─► ParseRunner (already async, see §1.4)
```

### 2.1 Recommended mechanism: seam extraction + ContextVar, NOT parameters

Adding a parameter means changing `call_tool`, the dispatch tuple type, and
all 31 handler signatures (plus every direct-call test) to benefit ~5 ops.
The codebase already has the lighter pattern twice over:

- kernel-level ambient accessors: handlers call `get_operations_logger()`,
  `get_api_index()` rather than receiving them;
- a per-call `ContextVar`: `execution.py`'s `_RUN_RECIPE_CONTEXT` is set at
  the top of `handle_run_module` and read by shared failure helpers.

Design: in `mcp_compat.make_call_tool_handler._on_call_tool` (2.x) read
`ctx.session` / `ctx.meta`; on 1.x read the SDK's request-context ContextVar
inside `call_tool`. Build a small `ProgressReporter` (async
`report(progress, total=None, message=None)`, **no-op when no token was
supplied**, all exceptions swallowed — precedent: `log_parse_op` is wrapped
so telemetry can never fail a tool call, `server.py:~1095`) and stash it in
a ContextVar that `call_tool` sets/resets around `await handler(dumped)`.
Long ops fetch it via a kernel-style `get_progress_reporter()`.

Verified SDK surface (mcp 2.3.0): `ServerRequestContext.session` is a
`ServerSession` with
`async report_progress(progress, total=None, message=None)` — documented
as *"A no-op when the caller did not request progress"* — plus the explicit
`send_progress_notification(progress_token, …)`. The token itself arrives
as `params._meta.progressToken` (`RequestParamsMeta.progress_token`;
`ProgressNotificationParams = {progress_token, progress, total, message}`).
The 1.x equivalent is `session.send_progress_notification` reached via the
request-context ContextVar, with the token at the same `_meta` location —
so one reporter class with two construction sites covers both majors, in
the same file that already absorbs every other 1.x/2.x difference.

**Threading cost: one seam (≈30–50 lines in `mcp_compat.py` + a reporter
module + 3 lines in `call_tool`). Zero handler signature changes.** After
that, per-op cost is only the instrumentation in §2.2.

### 2.2 Per-op instrumentation cost

| Op | Granularity honestly available | Cost | Notes |
|----|-------------------------------|------|-------|
| C semantic load | 3 milestones (load start / model ready / searching) | **Trivial** — reporter calls at the existing `_log_info` sites (`server.py:246,248,254`); optionally `to_thread` the load so the "ready" note flushes promptly | No total; use indeterminate (`total=None`) or 0→1→2 of 3 |
| B run_module | Start + elapsed heartbeat (e.g. every 15 s, `total=None`) + finish | **Low** — an `asyncio.Task` heartbeat wrapped around the existing `await run_script_async(...)` at `execution.py:6363`; cancel the heartbeat in `finally` | True intra-run progress needs child-output streaming — out of scope (§1.2) |
| E grammar scan | Same heartbeat wrapper | **Trivial once B exists** — identical await shape (`run_scan_module`) | Reuse, don't duplicate |
| F measurement | Start/finish only | Trivial | Bounded, usually fast; low value |
| H sandbox create/seed | Milestone per numbered handler step | Low | The handler is already a step ladder (steps 1–8); report between steps |
| D parse (in-window) | Stage changes + word counters | Low technically — hook `_set_stage`/`_persist_progress` or the observer — **but low value**: after the 5 s grace window the originating request has returned, so its token is dead. Notifications only help a `try_word` that finishes *inside* the window, i.e. the fast cases that need them least | **Recommend: skip in Phase 3** |
| A refresh | One event per pipeline step (i/N, description) — genuinely coarse-grained and informative | Trivial *as instrumentation*: `run_command` already prints `[INFO] desc…` / `[OK] desc` per step; a reporter callback parameter on `run_command`/`main` maps 1:1 | **Blocked on reachability, not cost** (§1.1): needs a tool-shaped entry point first |
| G embeddings | Batch milestones: load indexes / extract items / encode / save | Low (4 print sites in `main()` already exist; `model.encode` also accepts a per-batch callback path if finer grain is ever wanted) | Blocked like A: not invoked by anything in-server |

### 2.3 Invariants the implementation must keep

1. **No token ⇒ byte-identical behavior.** The reporter's no-op default is
   what keeps the 31 untouched handlers and all direct-call tests valid.
2. **Progress never fails a tool.** Swallow in the reporter, not at call
   sites (the `log_parse_op` and filing-claim precedents, §3).
3. **Notifications don't order-guarantee against the result.** Clients may
   drop late notifications after the response; emit finish-state via the
   result payload (already the pattern: parse responses carry counters).
4. **Throttle word-level sources.** If D is ever wired, emit on stage
   change or every ≥1 % / ≥100 words — never per word (a 4 000-word batch
   must not emit 4 000 notifications).

---

## 3. Existing partial hooks (reuse, don't reinvent)

- **`operations_logger`** (`server/kernel.py`, `get_operations_logger()`):
  always-on rotating `operations.log`. `call_tool` already logs
  `[TOOL CALL]` / `[TOOL ARGS]` / `[TOOL OK|TOOL ERROR]` around dispatch.
  It is a *file*, invisible to the MCP client mid-call — it proves the
  milestone points exist but delivers none of Phase 3's UX.
- **`_log_info` progress-shaped messages in `server.py`**: semantic search
  already narrates itself in reporter vocabulary — `"Loading semantic
  search index..."` (216), `"Semantic search ready…"` (222),
  `"Loading/Downloading embedding model…"` (246/248),
  `"Model ready, search in progress..."` (254); startup narrates index
  loads and auto-refresh attempts (414–474, 821–844). These strings are
  the ready-made `message=` values for §2.2-C.
- **Structured per-op telemetry**: `handlers/op_telemetry.py` emits one
  JSONL line per `run_module` op with `duration_s`; `handlers/
  parse_telemetry.py:log_parse_op` does the same post-hoc for parse tools
  from `call_tool`. Both are *after-the-fact* — they establish that
  durations are already measured, and neither can become the progress
  channel (they fire at close).
- **A real progress-callback precedent**: `server/filing/claims.py` —
  `FilingClaim.progress: Optional[Callable[[], int]]`, `attach_progress()`,
  and `filing/observer.py:101` wiring `lambda: handle.words_completed`, so
  a *refusal* response can quote a live counter from a running job. Also
  `FilingClaim.words_completed` demonstrates the house rule: "a progress
  read never fails" (exceptions → 0). The reporter's failure semantics
  should copy this.
- **The parse observer** (`runner.py` `on_start/on_result/on_terminal`) is
  a working per-unit progress fan-out; if parse notifications are ever
  added, this — not the queue — is the hook.
- **Callbacks in builders/refresh: none.** `refresh.run_command` and every
  `build_*` function take no callback; their only channel is `print()`
  (captured wholesale by `capture_output=True` in-process, so even the
  prints are invisible until each subprocess exits).

---

## 4. Tasks extension (`io.modelcontextprotocol/tasks`) evaluation

### 4.1 What it would require here

SDK 2.3.0 already ships the types (`Task`, `CreateTaskResult`,
`GetTaskRequest`, `ListTasksResult`, `CancelTaskResult`,
`TaskStatusNotification`, `CallToolRequestParams.task: TaskMetadata`,
`ServerCapabilities.tasks`) — but the low-level `Server` in use exposes **no
task-handler registration**, and `mcp_compat.build_server` advertises no
tasks capability. Adopting tasks therefore means, from scratch: capability
advertisement, handlers for create/get/list/cancel/get-payload, a task
registry, result retention with TTL, `pollInterval` semantics, status
notifications — **twice-shaped** across the 1.x/2.x seam that Phases 1–2
just stabilized (tasks is a 2025-11-25-era extension; 1.x-era clients in
the supported range cannot be assumed to speak it).

### 4.2 Which ops would even qualify?

A task handle pays off only when an op (a) routinely exceeds plausible
client tool-call timeouts, (b) has no other handle, and (c) produces a
result worth retrieving later.

- **D parse runs: disqualified by (b).** They already have run_ids,
  status, cancel, persisted records, and polling tools — strictly richer
  than the generic task model (interleave notes, filing state, per-word
  partial results). Re-exposing them as MCP tasks creates **two handle
  namespaces for the same work** and a mapping layer to keep consistent.
- **B run_module / E scan: fail (a) on evidence.** Both are server-capped
  (300 s defaults) and already cancellable two ways: client-side request
  cancellation propagates and kills the process tree
  (`subprocess_helpers.py` `CancelledError` path, issue #315), and the
  timeout returns a normal error result. No repo evidence (issues,
  telemetry, docs) shows clients timing out *below* the server's own cap
  and losing work — the result of a killed `run_module` is an error
  message, not a retrievable artifact, so (c) also fails.
- **A refresh / G embeddings: would qualify on duration — but neither is
  a tool call today** (§1.1). Tasks cannot attach to a CLI run or to
  pre-serve startup work. They become candidates only *after* a
  refresh-tool decision, and even then a background-run + status-tool
  shape (the parse pattern, in-domain) is available without the protocol
  extension.

### 4.3 State the server would have to keep — and what dies

This server is a **per-client stdio process** (`main()` → `stdio_server()`),
single-session, with deliberately minimal durable state. A task registry
would be an in-memory `dict[task_id → {asyncio.Task, status, result, ttl}]`:

- **Process death = total loss.** Unlike parse `RunRecord`s (persisted per
  word under the run's record dir, deliberately so a killed batch "says
  how far it got"), a generic task's status *and result* would vanish on
  restart, crash, or the client closing the session — precisely the
  long-op scenarios tasks are meant to survive. The codebase already
  learned this lesson once: startup sweeps orphaned filing claims and
  marks their records `crashed` (`server.py:~1240`) because "its in-memory
  claim died with that process".
- New obligations with no current consumer: TTL eviction, result-size
  retention (a `run_module` result can be ~1 MB by contract), cancel
  races against the existing write-lock/backup machinery in B.
- Multi-client isolation is a non-issue (one stdio client), which removes
  the other classic justification for a server-side task store.

### 4.4 Verdict: DECLINE for Phase 3 (defer, with triggers)

Progress notifications cover the actual Phase 3 need — *visibility into
ops the client is already waiting on* — at roughly one seam + three small
instrumentations. Tasks solve a different problem (detach/reattach) that
this server's one detach-worthy workload already solves in-domain.

**Revisit when any trigger fires:** (1) refresh/embeddings become
tool-invoked and routinely exceed ~10 min; (2) a supported client is shown
to hard-cap tool calls below 300 s and lose `run_module` results;
(3) SDK support lands such that `build_server` gets task handlers on both
majors without a hand-rolled registry; (4) a second detach-worthy op
appears that does not fit the parse-run shape.

---

## 5. Testability

No live client is needed at any layer; the existing test style already
proves each seam:

- **Reporter unit tests:** the reporter is an injected async callable —
  a fake sink (`list.append`) captures `(progress, total, message)`
  tuples; assert monotonic progress, stable totals, and that a *raising*
  sink never propagates (house rule, §3).
- **Seam tests:** `tests/test_mcp_compat.py` already drives the 2.x
  adapter directly with `SimpleNamespace(name=…, arguments=…)` params and
  `ctx=None` (`handler(None, params)`). Extend that pattern: a `FakeCtx`
  whose `session.report_progress` records calls, params carrying
  `meta={"progressToken": "tok-1"}`; assert notifications bear the token,
  and that `ctx=None` / no-token calls emit nothing and return identical
  results. On the 1.x branch, the same assertions run against a stubbed
  request-context ContextVar.
- **Handler-level tests:** existing suites call `call_tool`/handlers
  directly (e.g. `test_issue243_prehandler_dispatch_envelope.py`,
  `test_issue53_cold_start.py`) with no transport — the ContextVar
  default (no-op reporter) must keep all of them green *unchanged*; that
  is itself the regression test for invariant §2.3-1. For instrumented
  ops, set a capturing reporter in the ContextVar and assert the milestone
  sequence.
- **Parse:** `server/parse/worker_backend.py` ships fake backends
  (`parse_seconds` sleeps) — if D is ever wired, a fake-backend run +
  capturing reporter verifies stage/word emissions with no FieldWorks.
- **Refresh:** a fake reporter + a stubbed `run_command` (the step list is
  data-like) asserts one event per step, including failure steps, without
  running any builder.
- **Gap noted:** there is **no in-process client/transport test harness**
  in `tests/` (no `ClientSession`/memory-stream tests found) — adapter-
  and handler-level fakes are the established substitute, and one manual
  stdio smoke with a progress-capable client should be listed as the
  Phase 3 verification step rather than assumed covered.

---

## 6. Ranked Phase 3 work list

1. **Reporter plumbing** — `mcp_compat` seam + ContextVar reporter (§2.1).
   Prerequisite for everything; touches no handler.
2. **C — semantic-search model load milestones** (§2.2). Cheapest real
   win; log points already exist; fixes the most common "server hung?"
   first-run experience.
3. **B — `run_module` elapsed heartbeat**, then **E — grammar scan** by
   reuse of the same wrapper. Longest routine waits; heartbeat-only is
   honest about the opaque subprocess.
4. **H — sandbox create/seed step milestones.** Small, structural.
5. **A/G — refresh & embeddings: DEFERRED pending a product decision.**
   Instrumentation is trivial (§2.2) but there is no request to attach
   to. Options for Matthew: (i) new `flextools_refresh_indexes` tool
   (then coarse step progress applies immediately); (ii) leave refresh
   CLI/startup-only and document that progress does not apply;
   (iii) wire embeddings into refresh first, then (i)/(ii) covers both.
6. **D — parse notifications: SKIP.** Domain progress already exceeds
   what `notifications/progress` could say (§1.4, §4.2).
7. **Tasks extension: DECLINE** (§4.4), revisit on named triggers.
