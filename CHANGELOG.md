# Changelog

All notable changes to FlexTools MCP are documented in this file.

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
- MCP server with 6 tools for FlexTools script generation
- FlexLibs2 API indexing and semantic search
- LibLCM API reflection and documentation
- Operation and module execution with dry-run support
- Auto-refresh capability for API indexes when versions change
