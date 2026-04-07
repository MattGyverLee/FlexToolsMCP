# FlexToolsMCP Changelog

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
