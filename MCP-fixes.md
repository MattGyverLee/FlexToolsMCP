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

## 3. Pydantic Input Models  [DEFERRED]

**Problem:** All 16 tools define parameter schemas as raw JSON Schema dicts.
Pydantic models would enforce constraints, auto-strip whitespace, catch invalid
enums before the handler runs, and self-document the input contract.

**Example improvement:**
```python
class SearchParams(BaseModel):
    query: str = Field(..., min_length=1, description="Natural language query")
    max_results: int = Field(default=10, ge=1, le=200)
    api_mode: Literal["flexlibs2", "flexlibs_stable", "liblcm", "all"] = "flexlibs2"
```

**Effort:** Medium (~16 models). Independent of FastMCP.

**Status:** Deferred -- valuable but not low-hanging fruit.

---

## 4. FastMCP Migration  [DEFERRED]

**Problem:** `list_tools()` is ~500 lines of hand-written `Tool()` constructors;
`call_tool()` is a manual if/elif chain. FastMCP would collapse both to decorated
functions.

**Note:** This project deliberately uses 16 tools as a query layer over 1,400
indexed functions. The "hundreds of tools" concern doesn't apply. FastMCP would
still simplify the 16 tools you do have (auto-generated schemas, cleaner dispatch).

**Effort:** High (registration refactor). Best combined with Pydantic migration.

**Status:** Deferred.

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

## 6. True Async for run_operation/run_module  [DEFERRED]

**Problem:** These tools call `subprocess.run()` synchronously inside `async def`
functions, blocking the event loop.

**Fix:** Use `asyncio.create_subprocess_exec()`.

**Effort:** Low (swap `subprocess.run` calls). But only matters if the server
handles concurrent requests.

**Status:** Deferred -- low practical impact for single-user MCP sessions.

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
