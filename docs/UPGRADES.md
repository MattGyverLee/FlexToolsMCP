# FlexToolsMCP +1 Upgrade Plan
# Features: Output Formatting, Config Management, Session History + Undo, Lazy Module Loading

## Context

FlexToolsMCP is a mature MCP server. Two sibling CLI projects (Flexlibs-CLI, Fieldworks-CLI)
introduced 4 portable patterns worth back-porting. This plan adds them as an incremental "+1"
upgrade without breaking existing tools or callers.

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
    """Get a config value by dotted key, e.g. 'paths.flexlibs2'."""

def config_set(key: str, value) -> None:
    """Set a config value. Persists immediately."""

def config_delete(key: str) -> bool:
    """Remove a key. Returns True if found and removed."""
```

**Supported keys (initial set)**:

| Key | Replaces |
|-----|---------|
| `paths.flexlibs` | `FLEXLIBS_PATH` env var |
| `paths.flexlibs2` | `FLEXLIBS2_PATH` env var |
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
# These patterns come from flexlibs2 operation stdout; map common messages to operation_type
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
from flexlibs2 import FLExProject
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

Formalize `_validate_api_mode` flexlibs import (lines 4035-4050) — extract to `_ensure_flexlibs2()` function mirroring `liblcm_extractor.init_pythonnet()`.

**Scope**: ~20 lines changed/added in server.py

---

## New Tool Summary

| Tool | Purpose |
|------|---------|
| `manage_config` | Get/set/delete/list persistent config values |
| `get_session_history` | List operations run this session; show undo availability |
| `undo_last_operation` | Undo most recent write via FLEx ActionHandler |

Total tool count: 12 existing → 15 tools

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

## Implementation Order

1. `src/response_utils.py` (standalone, no deps)
2. `src/config.py` (standalone, no deps)
3. Feature 4 lazy loading in `server.py` (isolated at top of file)
4. Feature 1 `@tool_handler` + `make_error` in `server.py`
5. Feature 2 `manage_config` tool in `server.py`
6. Feature 3 `SessionState` changes + `get_session_history` tool
7. Feature 3 `undo_last_operation` tool (last, depends on session history)
8. Feature 2 config fallback in `refresh.py`
