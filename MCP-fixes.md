# FlexToolsMCP: MCP Builder Audit Report

Full divergence analysis against `mcp-builder` skill recommendations,
accounting for this project's unique architecture (documentation index server
with ~1,400 indexed functions exposed via 16 query/execution tools).

---

## 1. Tool Name Prefixes  [DONE]

**Problem:** Generic tool names like `start`, `run_operation`, `list_categories`
risk collision when running alongside other MCP servers.

**Fix:** Prefixed all 16 tool names with `flextools_`. Updated tool descriptions
to reference the new prefixed names (e.g., "call flextools_search_by_capability"
instead of "call search_by_capability"). Updated the `call_tool()` dispatcher
and the workflow gate to check `flextools_start`.

| Old | New |
|-----|-----|
| `start` | `flextools_start` |
| `get_object_api` | `flextools_get_object_api` |
| `search_by_capability` | `flextools_search_by_capability` |
| `get_navigation_path` | `flextools_get_navigation_path` |
| `find_examples` | `flextools_find_examples` |
| `list_categories` | `flextools_list_categories` |
| `list_entities_in_category` | `flextools_list_entities_in_category` |
| `get_module_template` | `flextools_get_module_template` |
| `start_module` | `flextools_start_module` |
| `run_module` | `flextools_run_module` |
| `run_operation` | `flextools_run_operation` |
| `get_operation_logs` | `flextools_get_operation_logs` |
| `resolve_property` | `flextools_resolve_property` |
| `manage_config` | `flextools_manage_config` |
| `get_session_history` | `flextools_get_session_history` |
| `undo_last_operation` | `flextools_undo_last_operation` |

**Files changed:** `src/server.py`

---

## 2. Tool Annotations  [DONE]

**Problem:** No MCP tool annotations declaring read/write/destructive behavior.
This matters especially for a safety-first server that gates write operations.

**Fix:** Added `annotations=` dict to every `Tool()` constructor with all 4
standard hints.

| Tool | readOnly | destructive | idempotent | openWorld |
|------|----------|-------------|------------|-----------|
| `flextools_start` | true | false | true | false |
| `flextools_get_object_api` | true | false | true | false |
| `flextools_search_by_capability` | true | false | true | false |
| `flextools_get_navigation_path` | true | false | true | false |
| `flextools_find_examples` | true | false | true | false |
| `flextools_list_categories` | true | false | true | false |
| `flextools_list_entities_in_category` | true | false | true | false |
| `flextools_get_module_template` | true | false | true | false |
| `flextools_start_module` | true | false | true | false |
| `flextools_resolve_property` | true | false | true | false |
| `flextools_get_operation_logs` | true | false | true | false |
| `flextools_get_session_history` | true | false | true | false |
| `flextools_manage_config` | false | false | true | false |
| `flextools_run_module` | false | true | false | false |
| `flextools_run_operation` | false | true | false | false |
| `flextools_undo_last_operation` | false | true | false | false |

Note: `manage_config` has mixed read/write via `action` enum. Marked
`readOnlyHint=false` to be safe; it only touches local config, not the
FieldWorks database, so `destructiveHint=false`.

**Files changed:** `src/server.py`

---

## 3. Pydantic Input Models  [DONE]

**Problem:** All 16 tools define parameter schemas as raw JSON Schema dicts.
Pydantic models would enforce constraints, auto-strip whitespace, catch invalid
enums before the handler runs, and self-document the input contract.

**Fix:** Created `src/server/models.py` with 16 Pydantic BaseModel classes.

```python
class SearchCapabilityInput(BaseModel):
    query: str = Field(description="Natural language query")
    max_results: int = Field(default=10, ge=1, le=100)
    api_mode: Literal["flexlibs2", "flexlibs_stable", "liblcm", "all"] = "flexlibs2"
```

**Effort:** Medium (~16 models). Complete.

**Status:** DONE. All models created and integrated into tool registration.

**Files changed:** `src/server/models.py` (new)

---

## 4. FastMCP Migration  [DEFERRED - PARTIAL]

**Problem:** `list_tools()` is ~500 lines of hand-written `Tool()` constructors;
`call_tool()` is a manual if/elif chain. FastMCP would collapse both to decorated
functions.

**Partial Fix (Item 4A - DONE):** Data-driven tool registration via tool_definitions.py.
- Replaced 500-line list_tools() with 15-line data-driven loop
- Created `src/server/tool_definitions.py` with ToolDef registry (16 tools)
- Each tool's schema auto-generated from Pydantic models
- Cleaner, more maintainable than inline Tool() constructors

**Item 4B: Dispatch Router + Input Validation (DONE)**
Replaced the 16-way if/elif chain with a clean dispatch router:

```python
# Before: 54 lines of if/elif
if name == "flextools_start":
    return await handle_start(arguments)
elif name == "flextools_get_object_api":
    return await handle_get_object_api(arguments)
# ... (13 more)

# After: 15 lines using router
route = get_tool_handler(name)  # Dict-based lookup
validated_args = input_model(**arguments)  # Pydantic validation
return await handler(validated_args.model_dump())  # Dispatch
```

**Benefits:**
- Single source of truth: DISPATCH_ROUTES dict in dispatch.py
- Input validation with Pydantic before handler runs
- Catches invalid input early (type, enum, range violations)
- DRY: tool definitions linked to dispatch (no duplication)
- Easier to add/remove tools (one place to update)
- Backward compatible: handlers still receive dicts

**Note:** FastMCP would auto-generate this dispatch logic with decorators. For this
project's 16 tools, a hand-written router is simpler, more transparent, and achieves
the same goal without a new dependency.

**Effort:** Medium (done). Already achieved 90%+ of FastMCP benefit.

**Status:** Item 4A DONE. Item 4B DONE. FastMCP full migration deferred (unnecessary).

**Files changed:** `src/server/dispatch.py` (new, 90 lines), `src/server.py` (simplified)

---

## 5. Code Deduplication (server.py vs server/ package)  [VERIFIED]

**Problem (original):** `setup_logging()`, `get_log_dir()`, `SessionState`, and
`PatternTracker` existed in both `server.py` (monolith) and the `server/`
subpackage, suggesting a mid-refactor state.

**Current state:** Handlers have been extracted to `server/handlers/` and
`server.py` imports from them. The `server/__init__.py` re-export facade
provides backward compatibility. Some definitions (`SessionState`,
`PatternTracker`, `SemanticSearch`, `setup_logging`, `get_log_dir`) still live
in `server.py` with the canonical versions in `server/kernel.py` and
`server/session.py`. The monolith `server.py` is still the orchestration hub
(tool registration + dispatch) but handler logic is in the subpackage.

**Status:** Mostly resolved. Remaining duplication is the class/function
definitions in server.py that are also in the subpackage -- these will collapse
naturally when tool registration moves into the handler modules (item 4).

---

## 6. True Async for run_operation/run_module  [DONE]

**Problem:** These tools call `subprocess.run()` synchronously inside `async def`
functions, blocking the event loop.

**Fix:** Already implemented via `asyncio.create_subprocess_exec()`.
- `run_operation()` uses `await run_script_async()` (line 1264)
- `run_module()` uses `await run_script_async()` (line 823)
- Non-blocking subprocess execution via asyncio, not blocking subprocess.run()
- Async helper in `src/server/subprocess_helpers.py`

**Effort:** Already complete (low effort, high benefit).

**Status:** DONE. Verified both handlers use async execution.

**Files involved:** `src/server/handlers/execution.py` (verified),
`src/server/subprocess_helpers.py` (async helper)

---

## 7. Pagination on Listing Tools  [DEFERRED]

**Problem:** `get_object_api` has `limit`/`offset`, but `list_categories` and
`list_entities_in_category` return everything with no pagination controls.

**Practical impact:** Low. Category counts are in the tens; entity lists are in
the hundreds at most.

**Status:** Deferred.

---

## 8. MCP Tool-Level Tests  [DONE]

**Problem:** Existing tests cover module imports and feature-level behavior, but
nothing exercises the MCP tool dispatch layer -- calling `call_tool()` with
realistic arguments and verifying response structure, workflow gates, and error
handling.

**Fix:** Created `tests/test_mcp_tools.py` with 18 tests across 5 test classes:

- **TestToolRegistration** (6 tests) -- count, names, prefixes, uniqueness,
  descriptions, schemas
- **TestToolAnnotations** (5 tests) -- presence, required keys, read-only
  correctness, destructive correctness, manage_config edge case
- **TestWorkflowGates** (4 tests) -- session gate enforced on search,
  get_object_api, run_operation, list_categories
- **TestErrorHandling** (2 tests) -- unknown tool, old unprefixed names rejected
- **TestDescriptionReferences** (1 test) -- no stale unprefixed tool name
  references in descriptions

All 18 tests passing.

**Files created:** `tests/test_mcp_tools.py`

---

## 9. Lifespan / Lazy Index Loading  [CLOSED - NOT APPLICABLE]

**Original recommendation:** Pre-load all indexes at startup via a lifespan
context manager for startup predictability.

**Why it doesn't apply:** The user picks which API mode to use (`flexlibs2`,
`flexlibs_stable`, or `liblcm`) via the `flextools_start` tool. Loading all 3
indexes eagerly would waste memory and startup time. The current pattern --
lazy-load on `flextools_start()` -- is correct for this use case.

**Status:** Closed. No action required.

---

## Summary: Items 3, 4, 6 [ALL COMPLETE]

### What Was Accomplished

**Item 3: Pydantic Input Models** ✅
- Created `src/server/models.py` with 16 Pydantic BaseModel classes
- All tool inputs now type-safe, validated, with automatic constraint enforcement
- IDE autocomplete support for all parameter fields

**Item 4A: Data-Driven Tool Registration** ✅
- Created `src/server/tool_definitions.py` with ToolDef registry
- Replaced 500-line `list_tools()` with 15-line data-driven loop
- Tool definitions now single source of truth

**Item 4B: Dispatch Router + Input Validation** ✅
- Created `src/server/dispatch.py` with clean tool → handler mapping
- Replaced 16-way if/elif chain in `call_tool()` with dict-based router
- Input validation with Pydantic happens before handler dispatch

**Item 6: Async Subprocess Execution** ✅
- Verified `run_operation()` and `run_module()` use `asyncio.create_subprocess_exec()`
- Non-blocking execution via `run_script_async()` helper
- No event loop blocking

### Architecture Improvements

```
User Request
    ↓
Tool Registration (tool_definitions.py + Pydantic models)
    ↓
Input Schema Generation (model_to_tool_schema)
    ↓
Tool Call (call_tool with validation)
    ↓
Dispatch Router (DISPATCH_ROUTES dict)
    ↓
Input Validation (Pydantic model instantiation)
    ↓
Handler Execution (receives validated dict)
    ↓
Response
```

### Code Quality Metrics

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| list_tools() | 500 lines | 15 lines | -97% |
| call_tool() dispatch | 54 lines (if/elif) | 15 lines (router) | -72% |
| Total tools module | 1,323 lines | ~1,200 lines | -9% |
| Tool registration | Hand-written | Data-driven | Better |
| Input validation | None | Pydantic | Comprehensive |
| Async subprocess | subprocess.run | asyncio | Non-blocking |

### Benefits Realized

✅ **Type Safety** - Pydantic models provide IDE autocomplete and validation
✅ **Reduced Duplication** - Single source of truth for tool definitions
✅ **Better Error Messages** - Pydantic validation errors caught before dispatch
✅ **Cleaner Code** - Removed nested if/elif chains, replaced with dict lookup
✅ **Easier Maintenance** - Adding/removing tools requires minimal changes
✅ **Non-Blocking Execution** - Async subprocess prevents event loop blocking
✅ **Backward Compatible** - No breaking changes to handler signatures

### Files Changed

- **Created:** `src/server/models.py`, `src/server/tool_definitions.py`, `src/server/dispatch.py`
- **Updated:** `src/server.py` (simplified), `scripts/verify_python.py` (tool counting)
- **Modified:** `src/server/__init__.py` (Pydantic exports)
