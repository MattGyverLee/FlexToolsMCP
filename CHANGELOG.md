# FlexToolsMCP Changelog

## [Unreleased] - 2026-05-30

Coverage-test post-mortem follow-up: 13 issues (#17-#29) opened from the May 22 session-log audit, all landed. Three follow-up corrections from lex-domain review also included.

### Features
- Capture `user_intent` on `run_module` / `start_module`; echo into operations log (#18)
- Skeleton storage closet -- auto-capture working helpers, retrieve via `find_examples` + new `list_skeletons` tool (#24)
- Cap `report.Info` messages at 100 (first-50 / last-50 slice + truncation marker) (#25)
- Detect retry loops and code-size oscillation; surface `_assistance` hint on rejections (#28)
- Inline `get_object_api` summary on `api_discovery_required` rejections (#29)
- Inline cast rewrite + `KernelInterfaces` import on `casting_issues_detected` rejections (#21)

### Fixes
- Surface operation failures at ERROR, preflight rejects at WARNING (#17)
- `[TOOL CALL]` always reaches cross-session `operations.log`; `[TOOL ARGS]` demoted to INFO (#19)
- Clarify `undiscovered_entity` rejection when entity is explicitly imported; inline discovery payload (#20)
- Drop alphabetical tie-break for ambiguous cast targets -- route to manual `resolve_property` (#21 follow-up)
- Retarget polymorphic hint at inlined rewrite, not external `resolve_property` (#22)
- Diagnose SharedSettings / path-mismatch errors against discovered project list (#23)
- Surface `project_locked` with close-FieldWorks hint; correct exception class to `LcmFileLockedException` and FW9 lock-file location (#27)
- Retry-loop assistance hint now points at #21 inlined rewrite, not `resolve_property` (#28 follow-up)

### Docs
- Relax module-template mandate; bare snippets are first-class (#26)
- Reword `undiscovered_entity` message ("loaded" not "validated") (#20 follow-up)

## [2.0.0] - 2026-04-07

### Major Features
- **Async-first MCP Architecture**: Complete async implementation for concurrent tool execution
- **FlexLibs2 v3.0.0 Integration**: Deep wrapper support with 90% API coverage
- **LibLCM v11.0.0 Support**: Current version of FieldWorks library bindings
- **Session-based Configuration**: Persistent state management across tool calls
- **Structured Script Certification**: Validate FLExTools scripts before execution

### Code Consolidations & Improvements

#### Core Analyzer Modules
- Eliminated duplicate `infer_output_behavior_lcm()` function (-83 LOC)
- Pre-compiled regex patterns in docstring parsing (5-10% faster)
- Eliminated duplicate AST parsing in FlexLibs stable analysis (~2x faster)
- Merged dual entity iterations in refresh pipeline (O(2n) → O(n))
- Consolidated 52 API categorization constants to shared module

#### Handler Architecture Unification
- Created `response_keys.py` module for centralized response field constants
- Unified `json_response()` helper across all handlers
- Removed duplicate KEY_* constant definitions across handler modules
- Consolidated response formatting patterns

#### Performance Optimizations
- Cached version detection in server startup
- Optimized entity iteration patterns
- Pre-compiled regex patterns for docstring extraction
- Lazy-loaded pattern analyzers

### Bug Fixes
- Fixed duplicate @OperationsMethod decorators in FlexLibs2 (6 methods)
- Fixed undefined KEY_LIMIT and KEY_OFFSET constants
- Improved error handling in PropertyResolver
- Enhanced session state reset for clean test isolation

### Testing
- Added comprehensive validator tests (25+ new tests)
- Improved test fixture consolidation
- Added AST pattern visitor for complex analysis
- Enhanced test isolation with reset_session_state fixture

### Documentation
- Updated FLEXTOOLS-STYLE-GUIDE.md with best practices
- Added API versioning documentation
- Documented safe write guard patterns for user scripts

### Migration Notes
- **Breaking Change**: FlexLibs2 v2.0+ scripts need explicit imports (see CLAUDE.md)
- API response structure unchanged - backward compatible
- Session initialization now required before tool calls (already implemented)

### Known Limitations
- LibLCM reflection requires pythonnet on Windows
- Write operations serialize at project level (by design)
- Session state not persisted across CLI invocations
