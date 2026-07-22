# API Index Versioning System

## Overview

The MCP server now supports versioned API indexes, allowing it to handle independent library updates (LibLCM, FlexLibs, Flexicon) that occur at different times.

> **Where the index lives.** A baseline index ships inside the installed
> package (read-only). When installed via `pip`/`uvx`, any index regenerated at
> runtime is written to a user-writable overlay at **`~/.flextoolsmcp/index/`**,
> and the server reads that overlay in preference to the bundled copy. In a
> source checkout, the in-tree `src/flextoolsmcp/index/` is used directly so
> regenerated files can be committed. The `index/...` paths in the examples
> below refer to whichever of these applies to your install.

## How It Works

### 1. Version Detection

Each analyzer automatically detects the version of the library it's scanning:

- **FlexLibs / Flexicon**: Reads version from `setup.py` or `pyproject.toml`
- **LibLCM**: Extracts version from .NET assembly metadata using pythonnet

Version format: `X.Y.Z` (semantic versioning, 3 elements)

### 2. Versioned Filenames

API files are stored with version suffixes in the filename:

```
Old:  flexicon_api.json
New:  flexicon_api_v4.0.0.json
      flexicon_api_v4.1.0.json

Old:  liblcm_api.json
New:  liblcm_api_v8.2.3.json
      liblcm_api_v9.0.0.json

Old:  flexlibs_api.json
New:  flexlibs_api_v1.0.0.json
      flexlibs_api_v1.1.0.json
```

### 3. Refresh Behavior

When running `python -m flextoolsmcp.refresh`:

1. **Version Detection**: Analyzer detects the current version of the library
2. **File Check**: Looks for an existing file with that version
   - If found: Overwrites it (same version, new run)
   - If not found: Creates a new versioned file (new version)
3. **Versioned Storage**: Saves to `{lib}_api_v{X.Y.Z}.json`
4. **Automatic Indexing**: Previous versions remain in the index directory

### 4. Server Initialization

When the MCP server starts (`uvx flextools-mcp`, or `python -m flextoolsmcp` from source):

1. **Version Detection**: Detects current version of each installed library
2. **File Search**: Looks for the matching versioned API file
   - If found: Loads it
   - If not found: Automatically runs refresh for that library
3. **Dynamic Loading**: Uses the latest/most appropriate version available
4. **Graceful Degradation**: Works with any available version

### 5. Auto-Refresh on Demand

If the server can't find an API file matching the installed library version, it
self-heals by running a **full refresh** (at most once per process):

```python
# In server.py
if not liblcm_path:
    auto_refresh_missing_api_file("liblcm", "liblcm_api", liblcm_dir)
    liblcm_path = find_latest_versioned_api_file(liblcm_dir, "liblcm_api")
```

Despite the `library_name` argument (which only names the trigger for logging),
the refresh scans **all available APIs**, not just the missing one. This is
deliberate: the scans are cross-linked -- the reverse mapping annotates LibLCM
entities with their FlexLibs/Flexicon wrappers (`python_wrappers`) and pattern
extraction annotates Flexicon (`common_patterns`) -- so regenerating a single
library in isolation would leave the others' cross-references stale. Refreshing
per-library is exactly how those enrichment fields were lost in 2.8.0; the
self-heal now always runs the full, post-processed refresh so it can never
produce a half-enriched index.

The server will automatically:
- Detect that no index matches the installed library version
- Run a full refresh of all available APIs (LibLCM is best-effort -- skipped,
  keeping the existing index, when FieldWorks DLLs / pythonnet are absent)
- Re-apply the cross-link enrichment (reverse mapping, navigation graph,
  patterns, casting index)
- Load the regenerated index on startup

To avoid paying this refresh cost on the server's first run, warm the index at
install time with the `flextools-mcp-refresh` console command (see the refresh
docs).

## Workflow Example

### Scenario: LibLCM Updates from 8.2.3 → 8.3.0

```bash
# Current state
index/liblcm/
  liblcm_api_v8.2.3.json   (old version)

# User upgrades FieldWorks (updates LibLCM to 8.3.0)
# Server starts and detects mismatch:
#   Installed: LibLCM 8.3.0
#   Available: liblcm_api_v8.2.3.json

# Option 1: Manual refresh (no per-library flag anymore -- this scans all
# available APIs; LibLCM is best-effort and skipped gracefully if FieldWorks
# DLLs/pythonnet are unavailable)
python -m flextoolsmcp.refresh

# Now index contains both:
index/liblcm/
  liblcm_api_v8.2.3.json   (old version)
  liblcm_api_v8.3.0.json   (new version)

# Option 2: Auto-refresh (the server detects the mismatch and refreshes automatically)
uvx flextools-mcp
# Logs: "[INFO] No matching LibLCM API file found for v8.3.0"
# Logs: "[INFO] Auto-refreshing liblcm API index..."
# Logs: "[OK] Successfully refreshed liblcm API index"
```

## Benefits

1. **Multi-Version Support**: Can have API docs for multiple library versions simultaneously
2. **No Data Loss**: Old versions remain in the index for reference
3. **Automatic Updates**: Server auto-refreshes missing versions on startup
4. **Clear Audit Trail**: Filename shows exactly what version of the library was indexed
5. **Independent Updates**: Each library can be updated independently
6. **Backward Compatibility**: Server still works with older API files

## Implementation Details

### Key Functions in `refresh.py`

- `detect_flexlibs_version(path)` - Extract FlexLibs version
- `detect_flexicon_version(path)` - Extract Flexicon version
- `get_versioned_output_path(base_path, version)` - Generate versioned filename
- `extract_version_from_json(path)` - Read version from generated JSON
- `find_existing_versions(dir, prefix)` - List all existing versioned files

### Key Functions in `server.py`

- `find_latest_versioned_api_file(dir, prefix)` - Find latest version of a library
- `auto_refresh_missing_api_file(library, prefix, dir)` - Trigger refresh if missing
- `APIIndex.load()` - Updated to use versioned files and auto-refresh

## Migration

If you have existing non-versioned API files:

1. They will be ignored by the new system
2. Run `python -m flextoolsmcp.refresh` to generate versioned files
3. Old files can be safely deleted

Example:
```bash
# Old files (will be ignored)
index/liblcm/liblcm_api.json
index/python/flexlibs_api.json
index/python/flexicon_api.json

# New versioned files (automatically generated/detected)
index/liblcm/liblcm_api_v8.2.3.json
index/python/flexlibs_api_v1.0.0.json
index/python/flexicon_api_v4.1.0.json
```

## Future Enhancements

- Compare APIs across versions (breaking changes detection)
- Automatic API diff reports
- Version pinning in MCP clients
- Archive old versions separately
