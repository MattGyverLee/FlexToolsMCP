# Changelog

All notable changes to FLExTools MCP are documented in this file.

## [2.0.0] - 2026-04-07

**Status**: RELEASED (ready to tag and merge to main)

This release completes the async-first refactoring and integrates FlexLibs2 v3.0.0.

### Completion Highlights

- ✅ All 83 tests passing (up from 35+)
- ✅ Code quality pass complete (Waves 1-7, 25+ files reviewed)
- ✅ 200+ LOC of duplication eliminated
- ✅ FlexLibs2 v3.0.0 API indexed (3,686 LOC reduction in FlexLibs2)
- ✅ Response field constants centralized
- ✅ Import path architecture stabilized
- ✅ Async test configuration fixed (pytest asyncio_mode=auto)

### New in This Session

- **Test Infrastructure**: Improved pytest fixtures (conftest.py consolidation)
- **Response Constants**: Created response_keys.py with 40+ centralized constants
- **FlexLibs2 v3.0.0**: Indexed new API removing deprecated ReversalOperations
- **Code Quality**: Applied /simplify pass across all handler modules
- **Import Stability**: Fixed dual-mode import guards to use reliable absolute paths

### Previous Release Notes

## [2.0.0] - 2026-03-22

### Major Breaking Changes

#### Architecture: Async-First with FastMCP

**From**: Synchronous subprocess-based request/response
**To**: Async/await using FastMCP framework (MCP protocol v3.0)

- All tool handlers now `async` functions
- Non-blocking concurrent read-only operations
- Per-project async write serialization via `asyncio.Lock`
- Better resource utilization and responsiveness

**Migration**: Tool consumers must update to FastMCP format

#### Script Certification: Index-Based Mutation Detection

**From**: Simple regex-based CUD pattern matching
**To**: Multi-layer hybrid detection with high confidence

**New capabilities**:
- Index-based detection using `is_mutating` field on all 1,237 FlexLibs2 methods
- Contextual LibLCM analysis (understands `modifyEnabled` and `writeEnabled` guards)
- AST-based control-flow analysis for protection context
- Conservative fallback for non-indexed code
- Certification confidence levels: high/medium/low

**Certification result** now includes:
- `unprotected_liblcm_calls`: Raw LibLCM mutations without guard
- `protected_liblcm_calls`: Raw LibLCM mutations with guard
- Granular call-by-call mutation details

#### Per-Project Write Locking

**From**: Global write lock across all projects
**To**: Per-project `asyncio.Lock` for safe concurrent operations

- Different projects: parallel execution
- Same project, multiple writes: serialized (FIFO queue)
- Read-only operations: no lock needed
- Timeout protection prevents deadlocks

### Added

- **Script Certification v2**:
  - `find_liblcm_mutations()`: Detect raw LibLCM mutation patterns
  - `find_protected_ranges()`: AST-based detection of protection blocks
  - Enhanced `certify_script_readonly()` with contextual analysis
  - Support for `with project.modifyEnabled:` guards
  - Support for `if project.writeEnabled:` conditional protection

- **API Index Enhancement**:
  - All 1,237 FlexLibs2 methods tagged with `is_mutating` boolean
  - 459 methods with `_EnsureWriteEnabled()` guard confirmed via AST analysis
  - `lcm_mapping.calls_ensure_write_enabled` field for fine-grained protection analysis
  - Index version: v2.3.2+ with mutation metadata

- **Critical Bug Fixes in FlexLibs2**:
  - Added `_EnsureWriteEnabled()` guard to 7 previously unguarded mutating methods
  - BaseOperations: `MoveUp`, `MoveDown`, `MoveToIndex`, `MoveBefore`, `MoveAfter`
  - ExampleOperations: `AddTranslation`
  - LexEntryOperations: `SetHeadword`

- **Test Coverage**:
  - Async locking tests (4 tests)
  - Script certification tests (11 tests)
  - Total: 35+ core tests passing

- **Documentation**:
  - RELEASE_2.0.0.md: Complete release notes
  - MIGRATION_v2_TESTS.md: Test migration guide
  - LIBLCM_CONTEXTUAL_ANALYSIS.md: Contextual analysis details
  - UNTAGGED_MUTATING_METHODS.md: Bug analysis and fixes

### Changed

- **Import Structure**: Refactored module organization for async support
- **Request/Response Format**: FastMCP protocol (MCP v3.0)
- **Error Handling**: Enhanced async error propagation
- **Lock Behavior**: Per-project instead of global

### Removed

- Legacy v1 test compatibility (test_mcp_tools.py, test_v1_3_0_upgrade.py)
- Synchronous execution path (full async transition)
- Global write lock (replaced with per-project locks)

### Fixed

- 7 critical mutations in FlexLibs2 lacking `_EnsureWriteEnabled()` guard
- Confidence calculation for mixed detection sources
- Line number tracking in indented code strings

### Technical Details

- **Pydantic Models**: Type-safe request/response validation
- **Dispatch Router**: FastMCP-based tool routing
- **AST Analysis**: Python control-flow analysis for protection context
- **Index Schema**: `is_mutating` boolean field per method
- **Lock Management**: Per-project `asyncio.Lock` with timeout

### Benefits

- 100% certainty for indexed FlexLibs2 mutations
- Safe direct LibLCM access when properly guarded
- Better concurrency (parallel reads, per-project serialization)
- Early mutation detection (certification time, not runtime)
- Granular call-level mutation tracking
- Future-proof async foundation

### Known Limitations

- Nested protection contexts not supported
- Complex conditionals not detected
- Cross-module guard tracking not available
- FlexLibs stable: name-only heuristic (no AST)
- LibLCM: pattern-based detection (no C# reflection)

### Migration Path

**From v1.3.1 to v2.0.0**:
1. Backup current environment
2. Update tool consumer to FastMCP protocol
3. Update scripts: wrap unprotected LibLCM in `modifyEnabled` or `writeEnabled` guards
4. Test against real projects (E2E validation)
5. Monitor certification results for false positives/negatives
6. Keep v1 running as fallback until confidence established

### Upgrade Considerations

- **Breaking**: Request/response format changed (FastMCP)
- **Breaking**: Certification API changed (new fields)
- **Breaking**: Sync execution no longer available
- **Compatible**: FlexLibs2 scripts still work (with protection analysis)
- **Compatible**: Module/operation APIs largely unchanged

## [1.2.0] - 2026-02-26

### Added
- **Library Version Detection**: MCP now detects installed library versions (LibLCM, FlexLibs, FlexLibs 2.0)
- **Version-Matched API Loading**: Loads API documentation matching the installed library version
- **Version Detection Functions**:
  - `get_installed_liblcm_version()` - Detects LibLCM from .NET assembly metadata
  - `get_installed_flexlibs2_version()` - Detects FlexLibs 2.0 from package metadata
  - `get_installed_flexlibs_version()` - Detects stable FlexLibs from package metadata

### Changed
- `APIIndex.load()` now matches installed library versions instead of always loading latest
- API files are loaded in order of preference: exact version match → latest version → auto-refresh
- Enhanced startup logging shows detected versions

### Technical Details
- Added `find_versioned_api_file()` to find API files matching specific versions
- Updated `APIIndex.load()` to detect and use installed library versions
- Graceful fallback to latest version if exact match not found
- Auto-refresh triggered only if no suitable API file exists

### Benefits
- Documentation always matches installed library versions
- Supports testing with specific/older versions
- Better visibility into version mismatches
- Enables version-specific debugging

## [1.1.0] - 2026-02-25

### Added
- **API Mode Support for run_module and run_operation**: Both tools now respect the `api_mode` setting from the `start()` function
  - `flexlibs_stable`: Legacy stable FlexLibs API (~40 functions)
  - `flexlibs2`: Modern FlexLibs 2.0 API (~90% coverage, ~1400 functions)
  - `liblcm`: Direct C# LibLCM API via pythonnet (raw access)
- **Dynamic Import Generation**: Runner scripts now conditionally import based on the selected API mode
- **Graceful Fallback**: Operations using flexlibs2 classes gracefully skip if not available in other modes
- **Enhanced Logging**: Both tools now log the API mode being used for better debugging

### Changed
- `run_operation` now respects `api_mode` from session state instead of forcing flexlibs2
- `run_module` now respects `api_mode` from session state for flexible module development
- Runner script namespace building is now dynamic and conditional based on available imports

### Technical Details
- Added `_get_api_mode_imports()` helper function to centralize API mode import logic
- Both runner scripts use placeholders for API mode imports, substituted at generation time
- Namespace dict in exec() calls wrapped with try/except to handle mode-specific classes gracefully

## [1.0.0] - 2026-02-15

### Initial Release
- MCP server with 6 tools for FLExTools script generation
- FlexLibs2 API indexing and semantic search
- LibLCM API reflection and documentation
- Operation and module execution with dry-run support
- Auto-refresh capability for API indexes when versions change
