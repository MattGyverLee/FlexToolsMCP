# Release History

## v1.3.1 (2026-02-28)

### Major Features
- **Deterministic JSON Output** - All API files now have consistently sorted keys and arrays, eliminating spurious diffs when regenerating indexes
- **Complete Casting Support** - Comprehensive Python interface casting guidance with property-to-concrete-type mappings for 1,068 concrete types
- **Enhanced Property Discovery** - New resolve_property tool shows which concrete interfaces have specific properties, with polymorphic collection warnings

### What's New
- Created `json_utils.py` module for JSON normalization across all build scripts
- Implemented `sort_json_arrays()` function that:
  - Recursively sorts inventory/lookup arrays (properties_accessed, methods_called, factories_used, etc.)
  - Deduplicates array values
  - Preserves meaningful order for sequence arrays (examples, steps, code snippets)
- Updated all 9 build scripts to normalize JSON output for clean diffs
- Removed auto-generated timestamp fields (_patterns_added, _relationships_added, _python_wrappers_added) that were causing unnecessary git diffs
- Enhanced resolve_property tool with property_availability_in_context section showing which concrete types have a property

### Bug Fixes
- Fixed file discovery functions to handle both underscore and hyphen naming patterns for versioned API files
- Fixed json.dump() calls missing sort_keys=True in default branches of build scripts
- Fixed non-deterministic JSON key ordering that was making version diffs hard to interpret

### Under the Hood
- Casting index now includes comprehensive property-to-concrete mappings (1,068 entries)
- Casting index includes ClassName-to-interface mappings (659 entries)
- Navigation paths now include warnings for polymorphic collections that require casting
- All API files regenerated with fully sorted and deduplicated arrays

### Benefits for Users
- Can now reliably diff API files across versions without spurious changes
- Get better guidance on when and how to use casting operations
- Understand which concrete types support specific properties
- Cleaner, more maintainable git history for the project

---

## v1.3.0 (2026-02-26)

### Major Features
- **API Versioning** - Support for multiple library versions coexisting (e.g., LibLCM 8.2.3, 8.3.0, 11.0.0)
- **Archive System** - Automatically archive old API versions to keep /index directory clean
- **Casting Operations API** - New CastingOperations wrapper class for discovering pythonnet casting functions via search

### What's New
- Added version detection for FlexLibs stable, FlexLibs 2.0, and LibLCM via file naming convention
- Implemented automatic version matching - server loads API files matching installed library versions
- Created archive subdirectory system for old API versions with configurable retention
- Added CastingOperations.cast_to_concrete() and related static methods for polymorphic collection handling
- Removed timestamp fields from all API files to reduce spurious diffs

### Bug Fixes
- Server now auto-refreshes missing API versions on startup
- Fixed version detection for LibLCM in FieldWorks installations
- Improved file naming consistency across all API extractors

### Under the Hood
- Renamed API files with version suffixes: flexlibs2_api_v2.3.0.json, liblcm_api_v11.0.0.json
- Updated all build scripts to generate versioned filenames
- Enhanced refresh.py to handle version detection and archiving

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
