# API Index Versioning Implementation Summary

## Changes Made

### 1. **flexlibs2_analyzer.py** - Version Detection

Added two new functions to detect library versions from source:

```python
def detect_flexlibs_version(flexlibs_path: str) -> str:
    """Detect FlexLibs stable version from setup.py or pyproject.toml"""

def detect_flexlibs2_version(flexlibs2_path: str) -> str:
    """Detect FlexLibs 2.0 version from setup.py or pyproject.toml"""
```

**Changes**:
- `analyze_flexlibs2()` now detects and stores version in `_source.version`
- `analyze_flexlibs_stable()` now detects and stores version in `_source.version`
- Version format: `X.Y.Z` (3 elements, semantic versioning)

### 2. **liblcm_extractor.py** - .NET Assembly Version Detection

Added version detection from .NET assemblies:

```python
def get_liblcm_version(assemblies: List) -> str:
    """Extract LibLCM version from loaded .NET assemblies"""
```

**Changes**:
- Reads version from `Assembly.GetName().Version`
- Stores in `_source.version`
- Updated `stamp_document()` to accept and include version parameter
- Updated `main()` to detect version and pass to `stamp_document()`

### 3. **refresh.py** - Versioned File Handling

Major updates for versioned file management:

```python
def get_versioned_output_path(base_path: Path, version: str) -> Path:
    """Generate versioned filename: lib_api_vX.Y.Z.json"""

def extract_version_from_json(json_path: Path) -> str:
    """Extract version from generated API JSON file"""

def find_existing_versions(base_dir: Path, prefix: str) -> dict:
    """Find all existing versioned API files"""
```

**Changes**:
- `refresh_flexlibs_stable()` - Uses temp file, extracts version, moves to versioned path
- `refresh_flexlibs2()` - Uses temp file, extracts version, moves to versioned path
- `refresh_liblcm()` - Uses temp file, extracts version, moves to versioned path
- `apply_categorization()` - Finds latest versioned file and applies categorization

**File Naming**:
- Old: `flexlibs_api.json`
- New: `flexlibs_api_v1.0.0.json`

### 4. **server.py** - Dynamic Version-Aware Loading

Added version detection and auto-refresh functionality:

```python
def find_latest_versioned_api_file(index_dir: Path, prefix: str) -> Optional[Path]:
    """Find the latest versioned API file for a library"""

def auto_refresh_missing_api_file(library_name: str, prefix: str,
                                   index_dir: Path) -> bool:
    """Auto-refresh a missing API file by running the analyzer"""
```

**Changes**:
- `APIIndex.load()` completely rewritten:
  - Uses `find_latest_versioned_api_file()` instead of hardcoded paths
  - Auto-refreshes missing API files
  - Logs which files are loaded and which versions
  - Gracefully handles missing files with auto-refresh
- Operations logger now tracks version loading and auto-refresh attempts

## Behavior

### When Refresh is Run

```bash
$ python src/refresh.py --flexlibs2-only
[INFO] Analyzing FlexLibs 2.0 at: D:\Github\flexlibs2\flexlibs2\code
[INFO] Detected version: 2.1.5
[INFO] Refreshing FlexLibs 2.0 index...
[INFO] Saved FlexLibs 2.0 v2.1.5 to flexlibs2_api_v2.1.5.json
```

**File System Result**:
```
index/flexlibs/
  flexlibs2_api_v2.0.0.json  (existing)
  flexlibs2_api_v2.1.0.json  (existing)
  flexlibs2_api_v2.1.5.json  (newly created/updated)
```

### When Server Starts

```bash
$ python src/server.py
[INFO] Detected LibLCM version: 8.3.0
[INFO] Loaded LibLCM from liblcm_api_v8.3.0.json
[INFO] Detected FlexLibs 2.0 version: 2.1.5
[INFO] Loaded FlexLibs 2.0 from flexlibs2_api_v2.1.5.json
```

**If Version is Missing**:
```bash
$ python src/server.py
[INFO] No FlexLibs 2.0 API file found for v2.2.0
[INFO] Auto-refreshing flexlibs2 API index...
[OK] Successfully refreshed flexlibs2 API index
[INFO] Loaded FlexLibs 2.0 from flexlibs2_api_v2.2.0.json
```

## Benefits

1. **Multi-Version Support** - Store API docs for multiple versions simultaneously
2. **No Data Loss** - Old versions preserved in index
3. **Automatic Updates** - Server auto-refreshes missing versions
4. **Audit Trail** - Filename shows exactly what version was indexed
5. **Independent Updates** - Each library updates independently
6. **Transparent to Users** - Server handles all version logic automatically

## Testing

All functions have been validated:
- ✓ Version detection from setup.py/pyproject.toml
- ✓ Version extraction from .NET assemblies
- ✓ Versioned filename generation
- ✓ Finding latest version in directory
- ✓ Auto-refresh on missing versions
- ✓ Server loading with versioned files

## Files Modified

1. `src/flexlibs2_analyzer.py` - Added version detection functions
2. `src/liblcm_extractor.py` - Added .NET version extraction
3. `src/refresh.py` - Complete versioning implementation
4. `src/server.py` - Dynamic loading and auto-refresh
5. `CLAUDE.md` - Updated documentation
6. `docs/VERSIONING.md` - New comprehensive guide (created)

## Backward Compatibility

- Old non-versioned files (e.g., `flexlibs_api.json`) will be ignored
- Server only looks for versioned files (`*_vX.Y.Z.json`)
- Run `python src/refresh.py` to generate versioned files from existing repos
- Can safely delete old non-versioned files after migration

## Migration Path

For users with existing non-versioned files:

1. Run `python src/refresh.py` to generate versioned files
2. Old files are automatically ignored (not deleted)
3. Server will use new versioned files
4. Optional: `rm index/liblcm/liblcm_api.json` to clean up old files

## Future Enhancements

- Cross-version API diffs (detect breaking changes)
- Version pinning in MCP tool parameters
- Automatic change logs between versions
- Archive old versions separately
