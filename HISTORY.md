# Release History

## v1.3.0 (2026-03-16)

### Major Features
- **Session History & Undo** - Track operations during a session and undo/redo via FLEx's built-in ActionHandler
- **Persistent Configuration** - Dotted-key JSON config system for managing settings across sessions
- **Lazy Module Loading** - Modules load on-demand, improving startup performance
- **Improved Error Handling** - Centralized response formatting with structured error envelopes
- **Modularized Architecture** - Internal handlers extracted into focused, reusable modules

### What's New

#### Session History & Undo
- `SessionState` now tracks operation history during a session
- New `undo_operation` tool reverses the most recent FLEx transaction
- New `redo_operation` tool re-applies an undone transaction
- Full compatibility with FLEx GUI undo stack — changes made in GUI are undone first

#### Configuration Management
- New `.flextoolsmcp/config.json` with dotted-key support (e.g., `logging.level`, `paths.default_project`)
- `refresh.py` reads fallback paths from config if `.env` not available
- Persistent settings survive tool restarts

#### Code Organization
- Response formatting centralized in `response_utils.py` with `@tool_handler` decorator
- Handler functions extracted into focused modules:
  - `catalog.py` - Lexicon browsing and discovery
  - `admin.py` - Project management and admin operations
  - `discovery.py` - Navigation and property resolution
  - `common.py` - Shared utilities across handlers
- All existing tools remain unchanged — re-export facade ensures backward compatibility

#### Performance
- Lazy import of MCP library — only loaded when tools are called
- Module initialization deferred until needed
- Faster startup for non-interactive use cases

### Benefits for Users
- **Undo workflows** - Experiment safely knowing you can undo/redo any operation
- **Persistent settings** - No need to reconfigure on each session
- **Better error messages** - Structured, consistent error responses
- **Same API** - All existing code continues to work without modification
- **Cleaner codebase** - Easier to understand and extend the MCP server

### Backward Compatibility
- ✅ All v1.2.0 tools work unchanged
- ✅ All existing code continues without modification
- ✅ Re-export facade hides internal reorganization
- ✅ Config is optional — `.env` continues to work as before

---

## v1.2.0 (2026-02-22)

### Major Features
- **Library Version Detection** - Automatically detect which FlexLibs/LibLCM versions are installed
- **Flexible Library Configuration** - Use installed packages or repository clones via .env configuration

### What's New
- Added library version detection for FlexLibs stable (from __init__.py)
- Added library version detection for FlexLibs 2.0 (from __init__.py)
- Added version detection for LibLCM via Assembly reflection
- Enhanced .env configuration to support both package and repository paths
- Added version reporting to refresh output

### Under the Hood
- Extended flexlibs2_analyzer.py with version detection logic
- Extended liblcm_extractor.py with version detection logic
- Enhanced refresh.py to report detected versions

---

## v1.1.0 (2026-02-18)

### Major Features
- **API Mode Support** - run_module and run_operation now accept api_mode parameter
- **FlexLibs Stable Support** - Can target legacy FlexLibs (~71 methods) or modern FlexLibs 2.0 (~1,400 methods)

### What's New
- Added api_mode parameter to run_module tool
- Added api_mode parameter to run_operation tool
- Both tools now support: flexlibs_stable, flexlibs2 (default), and liblcm
- Module execution results show which API mode was used

### Benefits
- Users can choose to generate simpler modules using FlexLibs stable
- Legacy code can continue to use older API approach
- Gradual migration path to FlexLibs 2.0

---

## v1.0.0 (2026-02-15)

### Initial Release

**MCP Server for FieldWorks Automation**

Core Features:
- 12 discovery and execution tools
- 2,295 LibLCM C# entities
- ~1,400 FlexLibs 2.0 Python methods (99% documented, 82% with examples)
- ~71 FlexLibs stable methods
- Semantic search with synonym expansion
- Dry-run and write modes for safe testing
- Code example extraction
- Navigation path finding between object types

This release provides the foundation for AI-assisted FieldWorks automation through a comprehensive, searchable API documentation system.
