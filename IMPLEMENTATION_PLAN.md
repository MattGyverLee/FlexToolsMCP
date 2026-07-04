# Implementation Plan: Items 3, 4, and 6

## Overview
Refactor MCP server to:
1. **Item 3**: Add Pydantic input models for all 16 tools (~50 lines per model)
2. **Item 4**: Migrate to FastMCP framework (cleaner registration & dispatch)
3. **Item 6**: Replace synchronous subprocess.run with async asyncio.create_subprocess_exec

Total effort: ~500-600 lines of new/changed code across 4-5 files.

---

## Item 3: Pydantic Input Models

### Scope
Convert 16 tool parameter schemas from raw JSON Schema dicts to Pydantic BaseModel classes.

### Approach

**File: `src/server/models.py` (NEW)**
- Create dedicated module for all Pydantic input/output models
- One model per tool, named `<ToolName>Input` (e.g., `SearchCapabilityInput`, `RunOperationInput`)
- Use Pydantic v2 features: `Field()`, `Literal[]`, validators
- Export all models from `__init__.py` for clean imports

**Models to create (16 total):**
1. `FlexToolsStartInput` - api_mode, task, project_name, output_type, write_enabled
2. `GetObjectApiInput` - object_type, include_flexicon, include_liblcm, summary_only, method_filter, limit, offset
3. `SearchCapabilityInput` - query, max_results, api_mode
4. `GetNavigationPathInput` - from_object, to_object
5. `FindExamplesInput` - method_name, operation_type, object_type, max_results
6. `ListCategoriesInput` - (no parameters, empty model)
7. `ListEntitiesInCategoryInput` - category
8. `GetModuleTemplateInput` - module_name, synopsis, modifies_db
9. `StartModuleInput` - module_name, synopsis, api_target, modifies_db, domain, include_dry_run
10. `RunModuleInput` - module_code, project_name, write_enabled, timeout_seconds, show_code, confirmed
11. `GetOperationLogsInput` - log_lines, include_patterns, errors_only
12. `RunOperationInput` - operations, project_name, write_enabled, timeout_seconds, show_code, confirmed
13. `ResolvePropertyInput` - property_name, context_entity, include_casting_info
14. `ManageConfigInput` - action, key, value
15. `GetSessionHistoryInput` - include_operations
16. `UndoLastOperationInput` - (no parameters, empty model)

### Files to modify:
1. Create `src/server/models.py` - All Pydantic models
2. Update `src/server/__init__.py` - Export models
3. Update `src/server.py`:
   - Import models from `server.models`
   - Replace inputSchema dicts with `model.model_json_schema()`
   - No handler changes needed (handlers still get dicts, extracted from Pydantic models)

### Validation benefits:
- Enum values validated before handler runs
- min_length/ge/le constraints enforced
- Type coercion (e.g., "50" -> 50 for integers)
- Better IDE autocomplete for handler authors
- Automatic schema generation

---

## Item 4: FastMCP Migration

### Scope
Replace manual tool registration + dispatch with FastMCP decorators.

### Approach

**Installation:**
- Add `fastmcp>=1.0.0` to requirements.txt
- FastMCP provides `@mcp.tool()` decorator to replace manual `Tool()` constructors

**File: `src/server/tools.py` (NEW)**
- Use `@mcp.tool()` decorators on handler functions directly
- FastMCP auto-generates schemas from Pydantic models
- FastMCP auto-generates tool descriptions (via docstrings)

**Handler signature change:**
```python
# Before (handler receives raw dict)
async def handle_search_by_capability(args: dict) -> list[TextContent]:
    query = args.get("query")

# After (FastMCP deserializes to Pydantic)
@mcp.tool()
async def handle_search_by_capability(args: SearchCapabilityInput) -> list[TextContent]:
    query = args.query
```

**Files to modify:**
1. Add `fastmcp>=1.0.0` to requirements.txt
2. Create `src/server/tools.py`:
   - Import all handlers from `server/handlers/`
   - Import all Pydantic models from `server/models.py`
   - Apply `@mcp.tool()` to each handler
   - Extract server dispatch to FastMCP
3. Update `src/server.py`:
   - Remove ~500-line `list_tools()` function
   - Replace manual if/elif chain in `call_tool()` with FastMCP dispatch
   - FastMCP handles schema generation + validation

**Benefits:**
- Eliminates 500+ lines of boilerplate
- Automatic schema generation from Pydantic models
- Cleaner handler signatures (typed args, not dicts)
- Single source of truth (docstring + model = tool docs + schema)

### Risks & Mitigations
- **Risk**: FastMCP might not support all MCP features (annotations, complex schemas)
  - **Mitigation**: Verify FastMCP supports `ToolAnnotations` before starting; fall back to manual if needed
- **Risk**: Handler extraction order might matter (circular imports)
  - **Mitigation**: Keep handlers in separate modules; import in `tools.py` to create DAG

---

## Item 6: True Async for run_operation/run_module

### Scope
Replace two `subprocess.run()` calls with async `asyncio.create_subprocess_exec()`.

### Current code (blocking):
```python
result = subprocess.run(
    [sys.executable, temp_script_path],
    capture_output=True,
    text=True,
    timeout=timeout_seconds,
)
```

### New code (non-blocking):
```python
try:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        temp_script_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        encoding='utf-8',
    )
    stdout, stderr = await asyncio.wait_for(
        process.communicate(),
        timeout=timeout_seconds,
    )
    returncode = process.returncode
except asyncio.TimeoutError:
    process.kill()
    await process.wait()
    # Handle timeout
```

### Files to modify:
1. `src/server/handlers/execution.py`:
   - Line ~817: Replace `subprocess.run()` in `handle_run_operation()`
   - Line ~1254: Replace `subprocess.run()` in `handle_run_module()`
   - Import `asyncio` (already imported)
   - Already async functions, so no wrapper needed

### Practical impact:
- If server handles concurrent requests (rare for MCP), improves latency
- Otherwise, minimal observable impact (MCP sessions are typically single-threaded)
- Correct async pattern for a proper async framework

---

## Implementation Order

### Phase 1: Pydantic Models (Item 3) - ~2 hours
1. Create `src/server/models.py` with 16 models
2. Update `src/server.py` to use `model_json_schema()` in Tool constructors
3. Verify all schemas match original JSON schemas
4. Run existing tests to ensure no breaking changes

### Phase 2: FastMCP Migration (Item 4) - ~3 hours
1. Add FastMCP to requirements.txt
2. Create `src/server/tools.py` with decorated handlers
3. Verify FastMCP generates correct schemas from Pydantic models
4. Update `src/server.py` to use FastMCP dispatch
5. Test that all 16 tools still work via MCP

### Phase 3: Async Subprocess (Item 6) - ~30 minutes
1. Update `src/server/handlers/execution.py` (2 functions)
2. Test run_operation and run_module still complete successfully
3. Verify error handling (timeouts, killed processes) still works

### Phase 4: Testing & Cleanup - ~1 hour
1. Run full test suite (`pytest`)
2. Test manual MCP interaction (start -> search -> run_operation)
3. Clean up any dead code or temporary changes
4. Update MCP-fixes.md with completion status

---

## Rollback Plan
If FastMCP causes issues during Phase 2:
- Keep Phase 1 (Pydantic models) - orthogonal to FastMCP
- Revert Phase 2 (keep manual list_tools + call_tool)
- Continue with Phase 3 (async subprocess)

---

## Success Criteria
- [x] All 16 tools still accessible via MCP
- [x] Tool schemas unchanged (identical JSON schemas)
- [x] All existing tests pass
- [x] Handlers receive properly typed/validated arguments
- [x] Async subprocess calls don't block event loop
- [x] MCP-fixes.md updated with "DONE" status for all 3 items

---

## Dependencies
- **Phase 1**: None (Pydantic v2 already in requirements.txt)
- **Phase 2**: FastMCP package (needs verification of support for MCP features)
- **Phase 3**: asyncio (stdlib, already imported)
