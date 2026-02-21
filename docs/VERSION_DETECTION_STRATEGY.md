# Version Detection Strategy

## Overview

The MCP uses a multi-tier version detection strategy to ensure reliable API indexing across different library versions and deployment scenarios.

## Version Detection Hierarchy

### For Python Libraries (FlexLibs, FlexLibs 2.0)

```
Priority 1: Repository Code
├─ Read from flexlibs/__init__.py (or flexlibs2/__init__.py)
├─ Extract: version = "X.Y.Z"
└─ Location: Repository directory on disk

Priority 2: setup.py
├─ Read from setup.py in repository
├─ Extract version field
└─ Fallback if __init__.py missing

Priority 3: pyproject.toml
├─ Read from pyproject.toml
├─ Extract version field
└─ Alternative package metadata

Priority 4: Installed Package
├─ Import flexlibs or flexlibs2
├─ Read installed package version
└─ Fallback for non-repo scenarios

Default: 0.0.0 (if all methods fail)
```

### For .NET Libraries (LibLCM)

```
Priority 1: Assembly Metadata
├─ Load DLL using pythonnet
├─ Extract: Assembly.GetName().Version
├─ Location: FieldWorks installation directory

Priority 2: Standard Paths
├─ Search known FieldWorks locations
├─ C:/Program Files/SIL/FieldWorks 9
└─ D:/Github/Fieldworks/Output/Debug

Default: 0.0.0 (if assembly not found)
```

## Why This Design?

### Robustness
- **Multiple fallback layers** ensure version detection works in various scenarios
- Doesn't rely on single source of truth
- Graceful degradation to defaults

### Flexibility
- Supports editable installs (pip install -e)
- Supports pip-installed packages
- Supports local development from git repos
- Works with multiple installation methods

### Consistency
- Tested: Repo and installed packages produce identical APIs
- Version is read from authoritative source (the code itself)
- No dependency on environment state

## Deployment Scenarios

### Scenario 1: Development (Local Git)
```
.env: FLEXLIBS2_PATH=D:/Github/flexlibs2
Flow: D:/Github/flexlibs2/flexlibs2/__init__.py -> version="2.0.0"
```
✓ Primary method works
✓ Fallback method works (editable install)

### Scenario 2: Editable Install
```
pip install -e D:/Github/flexlibs2
Flow: Local git repo used for both
```
✓ Primary method works (reads from repo)
✓ Fallback method works (imports installed package)

### Scenario 3: Regular Pip Install
```
pip install flexlibs2==2.0.0
FLEXLIBS2_PATH not configured
Flow: Fallback to installed package version
```
✓ Fallback method works (imports flexlibs2.version)

### Scenario 4: CI/CD Pipeline
```
Clone repo -> Run refresh -> Push versioned files
Flow: Primary method works (repo on CI server)
```
✓ Primary method works
✓ Can also use pip-installed versions

## API Consistency Validation

### Test Results
```
Analyzing FlexLibs 2.0 from both sources:

Metric              Repo        Installed   Match
────────────────────────────────────────────────
total_classes       79          79          [OK]
total_methods       1404        1404        [OK]
total_properties    62          62          [OK]
total_entities      76          76          [OK]
version             2.0.0       2.0.0       [OK]
```

**Conclusion**: Repo and installed versions produce identical APIs. No data loss or inconsistency when switching between sources.

## Version Format

All versions use **semantic versioning (X.Y.Z)**:
- X = Major version (breaking changes)
- Y = Minor version (new features)
- Z = Patch version (bug fixes)

### Examples
- FlexLibs: 1.2.8 (stable API wrapper)
- FlexLibs 2.0: 2.0.0 (extended API wrapper)
- LibLCM: 11.0.0 (from FieldWorks 9.1.1 release)

## Versioned File Naming

API indexes are stored with version suffixes:
```
flexlibs_api_v1.2.8.json      (FlexLibs stable, version 1.2.8)
flexlibs2_api_v2.0.0.json     (FlexLibs 2.0, version 2.0.0)
flexlibs2_api_v2.1.0.json     (FlexLibs 2.0, version 2.1.0 - new version)
liblcm_api_v11.0.0.json       (LibLCM, version 11.0.0)
liblcm_api_v12.0.0.json       (LibLCM, version 12.0.0 - new version)
```

## Refresh Behavior

### On Refresh (python src/refresh.py)
1. **Detect current library version**
   - Uses hierarchy above to find version
   - For FlexLibs: reads from __init__.py
   - For LibLCM: reads from assembly metadata

2. **Analyze library**
   - Extract APIs using AST or reflection
   - Store in temporary file

3. **Version and save**
   - Extract version from analysis output
   - Rename to versioned filename: `lib_api_v{version}.json`
   - If version exists: overwrite
   - If version is new: create new file

### Result
- Old versions remain in index
- New version added alongside
- All versions coexist peacefully
- Clear audit trail in filenames

## Server Initialization (python src/server.py)

### On Startup
1. **Detect installed library versions**
   - Check what's currently installed
   - Determine expected version of each library

2. **Find matching API files**
   - Look for `lib_api_v{version}.json` for each library
   - Use latest version if multiple exist

3. **Auto-refresh if missing**
   - If API file doesn't exist for installed version
   - Automatically run analyzer to create it
   - No manual intervention needed

4. **Load and ready**
   - APIs loaded into memory
   - Ready to serve MCP tools

## Migration Path

If upgrading from non-versioned system:

```
Old structure:
  index/liblcm/liblcm_api.json
  index/flexlibs/flexlibs_api.json
  index/flexlibs/flexlibs2_api.json

Upgrade process:
  python src/refresh.py

New structure:
  index/liblcm/liblcm_api_v11.0.0.json
  index/flexlibs/flexlibs_api_v1.2.8.json
  index/flexlibs/flexlibs2_api_v2.0.0.json

Optional cleanup:
  rm index/liblcm/liblcm_api.json
  rm index/flexlibs/flexlibs_api.json
  rm index/flexlibs/flexlibs2_api.json
```

## Advantages

✓ **Multi-version support**: Multiple library versions indexed simultaneously
✓ **No data loss**: Old versions remain for reference
✓ **Automatic updates**: Server auto-refreshes missing versions
✓ **Clear audit trail**: Version in filename shows exactly what was indexed
✓ **Independent updates**: Each library updates independently
✓ **Flexible deployment**: Works with repo clones or pip installs
✓ **Transparent to users**: Automatic version handling, zero configuration
✓ **API consistency**: Verified that different source types produce identical APIs

## Future Enhancements

- Cross-version API diffs (detect breaking changes)
- Automatic change log generation
- Version pinning in MCP tool parameters
- Archive old versions separately
- Version recommendation engine
