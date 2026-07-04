# FlexToolsMCP v1.3.0: Minor Version Upgrade
# Subtitle: Features: Output Formatting, Config Management, Session History + Undo, Lazy Module Loading

## Context

FlexToolsMCP v1.2.0 → v1.3.0 (minor version bump, 0.1 upgrade)

FlexToolsMCP is a mature MCP server. Two sibling CLI projects (Flexlibs-CLI, Fieldworks-CLI)
introduced 4 portable patterns worth back-porting. This plan adds them as Features 1-4, plus infrastructure (Feature 5 future).

**Why a minor version bump (not major)?**
- No breaking API changes — all existing tools work unchanged
- All existing code continues to work without modification (via re-exports)
- New features are additive: 3 new tools, expanded SessionState, modularized architecture
- Backward compatible with v1.2.0 and earlier
- Re-export facade means internal reorganization is invisible to callers

v1.3.0 is a comprehensive upgrade: production-ready with new capabilities, better error handling, persistent config, undo/history tracking, and cleaner internal architecture.

---

## Can We Really Accomplish Undo?

**Yes — by delegating to FLEx's built-in ActionHandler.**

FLEx/LCM already has a full undo stack. Every write transaction is tracked internally.
The Python API exposes it:

```python
cache.GetActionHandler().Undo()   # undoes the last write transaction
cache.GetActionHandler().Redo()   # redoes it
```

This is exactly what `Ctrl+Z` in the FLEx GUI calls. The MCP undo tool would:
1. Check that at least one undoable operation was run this session
2. Generate a short Python script that opens the same project and calls `Undo()`
3. Execute it via the existing `run_operation` subprocess infrastructure
4. Pop the top of the session undo stack

**Caveats to communicate to users:**
- Undoes the most recent FLEx transaction — if the user also used the GUI between calls, GUI actions undo first
- **CRITICAL**: FLEx must be completely shut down to perform undo. Unlike normal write operations (which work in shared mode), undo accesses the ActionHandler which requires exclusive project access. Users must close FLEx GUI before calling undo.
- Each undo call reverses exactly one transaction; multi-step operations may need multiple undo calls

---

## New Files

| File | Purpose |
|------|---------|
| `src/response_utils.py` | Centralized error/response helpers, `@tool_handler` decorator |
| `src/config.py`         | Dotted-key JSON config (`.flextoolsmcp/config.json`)         |

## Modified Files

| File | Changes |
|------|---------|
| `src/server.py` | SessionState history, 2 new tools, use response_utils, lazy MCP import |
| `src/refresh.py` | Read paths from config as fallback after .env |

---

## Feature 1: Centralized Output / Error Formatting

**New file: `src/response_utils.py`**

```python
def make_error(code: str, message: str, **extra) -> dict:
    """Standard error envelope for all tool returns."""
    return {"error": code, "message": message, **extra}

def tool_handler(func):
    """Decorator: catches unhandled exceptions and returns structured errors."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except Exception as exc:
            result = make_error(
                "internal_error",
                str(exc),
                exception_type=type(exc).__name__
            )
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
    return wrapper
```

**Changes to `src/server.py`**:
- Import `make_error` and `tool_handler` from `response_utils` (dual-mode import block)
- Apply `@tool_handler` decorator to all 13 `handle_*` functions (13 touch points, decoration only)
- Replace ~25 raw error-return dicts with `make_error(...)` calls for consistency
  - Priority locations: `call_tool` (line 2085), `handle_run_module` error returns (6 sites), `handle_run_operation` error returns (6 sites)
- `build_response_with_context` (line 1182) stays unchanged — `response_utils` adds to it, not replaces it

**Scope**: ~40 lines changed in server.py, 1 new file (~50 lines)

---

## Feature 2: Dotted-Key JSON Config

**New file: `src/config.py`**

```python
CONFIG_DIR = Path.home() / ".flextoolsmcp"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Cached in-process to avoid disk read on every tool call
_cache: Optional[dict] = None
_cache_mtime: float = 0.0

def config_get(key: str, default=None):
    """Get a config value by dotted key, e.g. 'paths.flexicon'."""

def config_set(key: str, value) -> None:
    """Set a config value. Persists immediately."""

def config_delete(key: str) -> bool:
    """Remove a key. Returns True if found and removed."""
```

**Supported keys (initial set)**:

| Key | Replaces |
|-----|---------|
| `paths.flexlibs` | `FLEXLIBS_PATH` env var |
| `paths.flexicon` | `FLEXICON_PATH` env var |
| `paths.liblcm` | `LIBLCM_PATH` env var |
| `paths.fieldworks` | `FIELDWORKS_PATH` env var |
| `server.index_dir` | hardcoded `Path(__file__).parent.parent / "index"` in `get_index_dir()` |
| `server.log_dir` | hardcoded `~/.flextoolsmcp/logs` in `get_log_dir()` |

**Load priority** (lowest overrides highest): config.json → .env → environment variable

**Changes to `src/server.py`**:
- `get_index_dir()` (line 1472): check `config_get("server.index_dir")` before hardcoded default
- `get_log_dir()` (line 44): same pattern
- Add `config_get` / `config_set` / `config_delete` as a new MCP tool `manage_config`
  (single tool with action param: `get`, `set`, `delete`, `list`)

**Changes to `src/refresh.py`**:
- `load_env()` (line 42): after reading .env, check config.json as lower-priority fallback for path vars

**Scope**: 1 new file (~80 lines), ~15 lines changed in server.py, ~10 lines in refresh.py

---

## Feature 3: Session History + Undo/Redo

**Changes to `SessionState` in `src/server.py` (line 258)**:

Add 3 new fields to `SessionState`:
```python
operations_history: list   # [{timestamp, tool, args_summary, script_code, script_output,
                           #   operation_type, details, success, undoable}]
undo_stack: list           # subset of history entries where undoable=True
redo_stack: list           # popped undo entries
```

Add methods:
```python
def record_operation(self,
                     tool: str,
                     args_summary: str,
                     script_code: str,           # Full Python script executed
                     script_output: str,         # Captured stdout from execution
                     success: bool,
                     undoable: bool = False) -> None:
    """
    Called after every run_operation / run_module execution.
    Correlates our actions with FLEx output to extract what changed.
    """
    entry = {
        "timestamp": time.time(),
        "tool": tool,
        "args_summary": args_summary,
        "script_code": script_code,
        "script_output": script_output,
        "success": success,
        "undoable": undoable,
        "project": self.project_name,
    }

    # Parse script_output to extract operation_type and details
    # Examples:
    #   "[OK] Created entry 'water' (hvo=12345)" -> operation_type="create_entry", details="form='water', hvo=12345"
    #   "[OK] Added sense to entry 'water'" -> operation_type="add_sense"
    self._extract_operation_details(entry)

    self.operations_history.append(entry)
    if undoable:
        self.undo_stack.append(entry)

def can_undo(self) -> bool:
    return bool(self.undo_stack)

def pop_undo(self) -> Optional[dict]:
    """Pop top of undo stack, push to redo stack."""
    # Caller can use returned entry["args_summary"] and entry["details"]
    # to show user: "Undo: Create water entry (hvo=12345)"
```

**Call sites** — add `session_state.record_operation(script_code, script_output, ...)` after result in:
- `handle_run_operation` (line 4132): pass the temp script file content and subprocess stdout
- `handle_run_module` (line 3586): same pattern

**Operation detail extraction** — add `_extract_operation_details(entry)` method to parse common patterns:
```python
# Patterns to recognize (examples):
# "[OK] Created entry 'water' (hvo=12345)" -> operation_type="create_entry", details="form='water', hvo=12345"
# "[OK] Added sense to 'water' with gloss 'H2O'" -> operation_type="add_sense", details="form='water', gloss='H2O'"
# These patterns come from flexicon operation stdout; map common messages to operation_type
```

**New tool: `get_session_history`**

Registered in `list_tools()` and handled in `call_tool()`:
```
Returns:
  {
    "session_initialized": bool,
    "operations": [
      {
        "timestamp": 1234567890,
        "tool": "run_operation",
        "args_summary": "Create water entry",
        "operation_type": "create_entry",        // extracted from script output
        "details": "form='water', hvo=12345",   // extracted from script output
        "script_code": "# Full script...",       // full audit trail
        "script_output": "[OK] Created entry...",
        "success": true,
        "undoable": true,
        "project": "MyLanguage"
      },
      // ... more operations
    ],
    "can_undo": true,
    "can_redo": false,
    "undo_stack_depth": 1,
    "next_undo_description": "Undo: Create water entry (hvo=12345)"  // user-friendly summary
  }
```

**New tool: `undo_last_operation`**

```
Parameters: none (undo is always the most recent undoable operation)

Tool description: "Undo the most recent write operation via FLEx ActionHandler.
  PREREQUISITE: FLEx GUI must be completely closed. Unlike normal write operations
  (which work in shared mode), undo requires exclusive project access."

Logic:
  1. Check session_state.can_undo() — return error if not
  2. Check session_state.write_enabled — undo only makes sense when writes happened
  3. Pop entry = session_state.pop_undo()
     - User sees: "Undoing: Create water entry (hvo=12345)"
       [extracted from entry["args_summary"] + entry["details"]]
  4. Generate undo script:
       cache.GetActionHandler().Undo()
  5. Execute via same subprocess infrastructure as run_operation
  6. If subprocess fails with "project locked" or similar, include prominent
     suggestion: "FLEx GUI appears to be open. Close FLEx and try again."
  7. Return result + updated session history summary
```

The generated undo script template (stored inline or in `get_module_template`):
```python
# FlexToolsMCP Auto-Generated Undo Script
from flexicon import FLExProject
project = FLExProject()
project.OpenProject(project_name, write_enabled=True)
try:
    cache = project.project
    if cache.GetActionHandler().CanUndo():
        cache.GetActionHandler().Undo()
        fp.flush_write()
        print("[OK] Undo successful")
    else:
        print("[WARN] Nothing to undo in FLEx ActionHandler")
finally:
    project.CloseProject()
```

**Scope**: ~120 lines added to server.py (SessionState + detail extraction + 2 tools), no new files

---

## Feature 4: Formalized Lazy Module Loading

The codebase already has ad-hoc lazy loading. This feature formalizes it with a consistent pattern.

**Changes to `src/server.py`**:

Replace the top-level MCP import (line 1195) with a lazy loader and clear error:
```python
# Current (line ~32):
from mcp.server import Server

# Becomes (at module level):
_mcp_error: Optional[str] = None
try:
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent, CallToolResult
except ImportError as exc:
    _mcp_error = str(exc)
    Server = None  # type: ignore
```

Add startup check in `main()`:
```python
if _mcp_error:
    print(f"[ERROR] MCP library not available: {_mcp_error}")
    print("[INFO] Install with: pip install mcp")
    sys.exit(1)
```

Formalize the semantic search lazy load (lines 1202-1209) — already correct, just add docstring.

Formalize `_validate_api_mode` flexlibs import (lines 4035-4050) — extract to `_ensure_flexicon()` function mirroring `liblcm_extractor.init_pythonnet()`.

**Scope**: ~20 lines changed/added in server.py

---

## v1.3.0 Release Summary

### Features (5 major additions)

| Feature | What's New | Impact |
|---------|-----------|--------|
| **Feature 1** | Centralized error handling via `@tool_handler` + `make_error()` | Consistent error envelopes, better resilience |
| **Feature 2** | Persistent dotted-key JSON config (`~/.flextoolsmcp/config.json`) | Users can customize paths and settings without code changes |
| **Feature 3** | Session history + undo/redo via `get_session_history`, `undo_last_operation` tools | Track operations, see what will be undone, leverage FLEx ActionHandler |
| **Feature 4** | Formalized lazy module loading for MCP, semantic search, flexicon | Better startup resilience if dependencies missing |
| **Feature 5** | Modularized server.py architecture (8 focused modules, 300-600 lines each) | Easier to navigate, test, and maintain; re-exports preserve backward compatibility |

### New Tools (3 tools added)

| Tool | Purpose | Type |
|------|---------|------|
| `manage_config` | Get/set/delete/list persistent config values | Admin |
| `get_session_history` | List operations run this session; show undo availability | Admin |
| `undo_last_operation` | Undo most recent write via FLEx ActionHandler | Execution |

**Tool count**: 12 existing → 15 tools

### Internal Architecture

**New structure** (modularized but backward compatible):
```
src/server/
  __init__.py           # Re-exports for backward compatibility
  kernel.py             # Shared state (api_index, session_state, pattern_tracker)
  session.py            # SessionState, PatternTracker, operation tracking
  handlers/
    api.py              # Read-only API queries
    execution.py        # Write operations, undo, logging
    admin.py            # Configuration, session management
    navigation.py       # Navigation paths, examples
    catalog.py          # Category listings
  validators.py         # Validation gates
  patterns.py           # Pattern tracking, recommendations
```

### Backward Compatibility

✓ All existing 12 tools remain unchanged
✓ No breaking changes to tool signatures or response formats
✓ Existing code calling `run_operation`, `get_object_api`, etc. continues to work (re-exports via `__init__.py`)
✓ `SessionState.summary()` expanded but doesn't change existing fields
✓ Can also use new modular imports if desired: `from server.handlers.execution import handle_run_operation`

### What "v1.3.0" Signifies

- **Minor version**: New features + architectural improvement, fully backward compatible
- **Stable API**: Users can upgrade from v1.2.0 safely — no code changes required
- **Production-ready**: Full test coverage, documented caveats, error handling
- **Clean internals**: Modularized architecture with facade for transparent upgrade

---

## File Touch Summary

| File | Lines Changed | Risk |
|------|--------------|------|
| `src/server.py` | ~190 added, ~25 modified | Medium (large file, isolated changes) |
| `src/refresh.py` | ~10 modified | Low |
| `src/response_utils.py` | ~50 new | None |
| `src/config.py` | ~80 new | None |

---

## Verification

```bash
# 1. Server loads without error
python -c "from src.server import APIIndex, get_index_dir; print('[OK] import')"

# 2. Config tool works
python src/server.py  # then call manage_config(action="list")

# 3. Session history appears after run_operation
# call start() -> run_operation() -> get_session_history()

# 4. Undo available after a write operation
# call start(write_enabled=True) -> run_operation() -> undo_last_operation()

# 5. Lazy load: verify server starts even with mcp uninstalled
pip uninstall mcp -y && python src/server.py  # should print [ERROR] with install hint
pip install mcp  # restore
```

---

## Feature 5: Modularize server.py (Included in v1.3.0, Backward Compatible)

**Problem**: server.py is 4,000 lines. Hard to navigate, understand, and test individual handlers.

**Solution**: Split into focused modules with re-export facade. Ships with v1.3.0 alongside Features 1-4.

```
src/
  server.py                   # Thin entry point (imports and re-exports from server/)
  server/
    __init__.py              # Re-exports all public API for backward compatibility
    kernel.py                # Shared state: api_index, session_state, pattern_tracker
    session.py               # SessionState, PatternTracker
    handlers/
      __init__.py            # Imports all handlers
      api.py                 # get_object_api, search_by_capability, resolve_property
      navigation.py          # get_navigation_path, find_examples
      catalog.py             # list_categories, list_entities_in_category
      execution.py           # run_operation, run_module, get_operation_logs, undo_last_operation
      admin.py               # start, manage_config, get_session_history, get_module_template, start_module
    validators.py            # Validation gates: detect_cud_operations, detect_undefined_variables, etc.
    navigation.py            # find_path_bfs, navigation graph logic
    patterns.py              # PatternTracker, pattern extraction, recommendations
```

**Backward Compatibility** (key innovation):

All old imports continue to work via re-exports:

```python
# src/server/__init__.py
# Re-export everything from handlers for backward compatibility
from .handlers.api import handle_get_object_api, handle_search_by_capability, handle_resolve_property
from .handlers.execution import handle_run_operation, handle_run_module, handle_get_operation_logs, handle_undo_last_operation
from .handlers.admin import handle_start, handle_manage_config, handle_get_session_history, ...
from .session import SessionState, PatternTracker
# ... etc

# Old code still works (v1.2.0 → v1.4.0 compatible):
from server import handle_run_operation  # ✓ works via __init__

# New code can also use modular paths:
from server.handlers.execution import handle_run_operation  # ✓ also works
```

**Benefits**:
- Each handler file: 200-400 lines (human-readable)
- Clear grouping by concern: read-only vs execution vs admin
- Easier to find code: `handlers/execution.py` for run_operation
- Easier to test: mock imports, unit test individual handlers
- Clearer dependencies: import chains visible at module level
- **ZERO breaking changes**: backward compatible via re-exports

**Challenges**:
- Circular imports between handlers and core utilities
- Solution: use `kernel.py` module with shared state (session_state, api_index, pattern_tracker, etc.)

**Kernel structure**:
```python
# server/kernel.py
api_index: Optional[APIIndex] = None
session_state: SessionState = SessionState()
pattern_tracker: PatternTracker = PatternTracker()
operations_logger: logging.Logger = setup_logging()
# All handlers import from kernel, avoiding circular deps
```

**Version**: v1.3.0 (ships with Features 1-4)

**Why include modularization in v1.3.0?**
- Zero breaking changes due to re-export facade
- Cleaner codebase delivered simultaneously with new features
- Internal architecture improvement aligns with adding new tools
- Users get benefits immediately (easier to read code, test contributions)

**Scope**: Split server.py into ~8 modules, each 300-600 lines. No new features, purely structural. Risk: medium (requires careful import structure and full test coverage, but backward compatibility facade eliminates integration risk).

---

## Implementation Order

### Single Release: v1.3.0 (All Features 1-5)

Unified release combining new functionality (Features 1-4) and architectural improvement (Feature 5).

**Step-by-step implementation:**

1. **Create new utility modules** (standalone, no interdependencies):
   - `src/response_utils.py` (Feature 1)
   - `src/config.py` (Feature 2)

2. **Modularize server structure** (Feature 5 - structural foundation):
   - Create `src/server/` directory
   - Create `src/server/kernel.py` (shared state)
   - Create `src/server/session.py` (SessionState, PatternTracker)
   - Create `src/server/handlers/` subdirectory:
     - `handlers/api.py` (get_object_api, search_by_capability, resolve_property)
     - `handlers/navigation.py` (get_navigation_path, find_examples)
     - `handlers/catalog.py` (list_categories, list_entities_in_category)
     - `handlers/execution.py` (run_operation, run_module, get_operation_logs, undo_last_operation)
     - `handlers/admin.py` (start, manage_config, get_session_history, get_module_template, start_module)
   - Create `src/server/validators.py` (validation gates)
   - Create `src/server/navigation.py` (find_path_bfs, navigation logic)
   - Create `src/server/patterns.py` (PatternTracker, patterns)
   - Create `src/server/__init__.py` (re-exports for backward compatibility)

3. **Update main entry point**:
   - Rename `src/server.py` → `src/server_v1_legacy.py` (backup)
   - Create new thin `src/server.py` that imports from `src/server/__init__.py`

4. **Add Feature 1 (Centralized Error Handling)**:
   - Import `make_error`, `@tool_handler` from `response_utils`
   - Apply to all handlers in their respective modules
   - ~40 lines changed across handler modules

5. **Add Feature 2 (Config Management)**:
   - Import config functions in `handlers/admin.py`
   - Add `manage_config` tool
   - Update `get_index_dir()`, `get_log_dir()` to use config
   - ~15 lines changed in kernel.py, handlers

6. **Add Feature 4 (Lazy Loading)**:
   - Add `_ensure_flexicon()` function in kernel.py
   - Wrap MCP imports with try/except in `src/server/__init__.py`
   - ~20 lines in kernel.py

7. **Add Feature 3 (Session History + Undo)**:
   - Expand SessionState in `session.py`: operations_history, undo_stack, redo_stack, record_operation(), can_undo(), pop_undo()
   - Add `_extract_operation_details()` method in `session.py`
   - Add `get_session_history` tool in `handlers/admin.py`
   - Add `undo_last_operation` tool in `handlers/execution.py`
   - Update `handle_run_operation()` and `handle_run_module()` to call `record_operation()`
   - ~120 lines in session.py, handlers

8. **Update `src/refresh.py`**:
   - Add config fallback after .env reading
   - ~10 lines

9. **Testing & validation**:
   - All old imports work via `src/server/__init__.py` re-exports
   - New imports via `src/server.handlers.*` also work
   - Full test suite passes
   - Verify backward compatibility with v1.2.0 code

### Future Maintenance (v1.5.0+)

**v1.5.0+ updates** (if needed):
- Bug fixes and patch releases
- New features from user feedback
- Keep v1.x API stable

**v2.0.0 Planning** (far future, if ever):
- Only consider if truly breaking changes are needed
- Would require explicit deprecation period

**Release timeline**:
1. **v1.3.0** (Features 1-5 combined, single integrated release)
2. **v1.5.x+** (patches and maintenance as needed)
3. **v2.0.0** (only if absolutely necessary breaking changes arise)
