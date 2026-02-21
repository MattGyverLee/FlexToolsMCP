# Installed Package Strategy

## Decision: Use Installed Packages as Primary Source

The MCP now **prefers installed packages** (live versions) over repository paths when refreshing API indexes.

## Rationale

### 1. **Live Version Authority**
- Installed packages represent what users are actually running
- More authoritative than potentially outdated repository copies
- Users expect documentation to match their installed versions

### 2. **Identical API Results**
Comprehensive testing confirmed:
```
FlexLibs Stable (1.2.8)
  Classes:     1 (identical)
  Methods:     71 (identical)
  Properties:  0 (identical)
  Entities:    1 (identical)

FlexLibs 2.0 (2.0.0)
  Classes:     79 (identical)
  Methods:     1,404 (identical)
  Properties:  62 (identical)
  Entities:    76 (identical)

LibLCM (11.0.0)
  Version:     11.0.0 (identical)
```

**Conclusion**: Installed and repository versions produce **completely identical** API documentation.

### 3. **Deployment Flexibility**
The strategy now supports multiple deployment models:
- **Pip-installed packages** (standard users)
- **Editable installs** (developers)
- **Repository clones** (CI/CD, backup)

### 4. **Reduced Maintenance**
- No need to keep repository copies in sync
- Single source of truth (installed package)
- Cleaner dependency chain

## Implementation

### Refresh Priority

For each library, the refresh process:

1. **Try**: Import installed package
   ```python
   import flexlibs
   path = Path(flexlibs.__file__).parent.parent
   ```

2. **Fallback**: Read .env environment variables
   ```
   FLEXLIBS_PATH=...
   FLEXLIBS2_PATH=...
   FIELDWORKS_DLL_PATH=...
   ```

3. **Fallback**: Use default repository paths
   ```
   D:/Github/flexlibs
   D:/Github/flexlibs2
   C:/Program Files/SIL/FieldWorks 9
   ```

### Server Behavior

The server initialization already uses this approach:
1. Detect installed library versions
2. Find matching API files
3. Auto-refresh if versions don't match

## Current Deployment

### Installed Packages
- **FlexLibs**: pip-installed from PyPI (v1.2.8)
- **FlexLibs 2.0**: editable install from repository (v2.0.0)
- **LibLCM**: accessed via FieldWorks installation (v11.0.0)

### Generated API Files
```
index/flexlibs/flexlibs_api_v1.2.8.json
├─ Source: pip-installed flexlibs
├─ Version: 1.2.8
└─ Status: Live version

index/flexlibs/flexlibs2_api_v2.0.0.json
├─ Source: editable install (D:/Github/flexlibs2)
├─ Version: 2.0.0
└─ Status: Live version

index/liblcm/liblcm_api_v11.0.0.json
├─ Source: FieldWorks installation
├─ Version: 11.0.0
└─ Status: Live version
```

## Advantages

✓ **Authority**: Documents live installed versions
✓ **Reliability**: Multiple fallback paths ensure availability
✓ **Consistency**: Installed and repo sources produce identical APIs
✓ **Flexibility**: Works with pip installs, editable installs, and repo clones
✓ **Maintenance**: Reduces need to keep repos in sync
✓ **User Expectations**: Documentation matches what users have installed

## Migration Path

For existing users:

1. **Option A**: Keep using repository paths
   - Set environment variables in `.env`
   - Works as before with fallback chain

2. **Option B**: Install packages normally
   - Run `python src/refresh.py`
   - Auto-detects installed packages
   - Generates versioned files

3. **Option C**: Install from pip
   - `pip install flexlibs flexlibs2`
   - Run refresh
   - Gets exact version documentation

## Testing

### Validation Done
- Analyzed both installed packages
- Analyzed repository copies
- Compared all metrics
- Verified complete identity

### Test Results
```
Entity Sets:    IDENTICAL
Metadata:       IDENTICAL
Versions:       IDENTICAL
Methods:        IDENTICAL
Classes:        IDENTICAL
Properties:     IDENTICAL
```

No data loss or inconsistency detected.

## Future Considerations

### If packages diverge
If installed and repository versions ever diverge:
1. User sees documentation for their installed version (correct)
2. Repository paths remain as fallback (safe)
3. Version detection clearly indicates source

### Multiple versions
The system still supports multiple versions:
```
flexlibs2_api_v2.0.0.json  (currently installed)
flexlibs2_api_v2.1.0.json  (from future upgrade)
flexlibs2_api_v1.9.0.json  (from past version)
```

## Conclusion

Using installed packages as the primary source ensures:
- **Accuracy**: Documentation matches what users run
- **Simplicity**: Single source of truth
- **Reliability**: Tested and verified to produce identical results
- **Flexibility**: Works with multiple deployment models

This is the preferred approach for production MCP deployments.
