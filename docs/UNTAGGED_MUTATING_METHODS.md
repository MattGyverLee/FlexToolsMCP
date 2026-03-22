# Untagged Mutating Methods in FlexLibs2

**Analysis Date**: 2026-03-22
**Index Version**: v2.3.2
**Analyzer**: flexlibs2_analyzer.py with `_EnsureWriteEnabled()` detection
**Total Mutating Methods Analyzed**: 1,237
**Methods WITH Guard**: 459 (37.1%)
**Methods WITHOUT Guard**: 778 (62.9%)

## What This Means

The FlexLibs2 API includes **7 methods that perform database mutations but lack the `_EnsureWriteEnabled()` guard**, a Python-level safety check that prevents write operations when the project is opened in read-only mode.

These methods are vulnerable to misuse - they CAN modify the database even if the caller intends to run in read-only mode, because the FlexLibs2 write-protection mechanism is not invoked.

## Untagged Methods by Class

### BaseOperations (5 methods)

All 5 are reordering/manipulation methods that modify sequence order without checking write access:

| Method | Type | Issue |
|--------|------|-------|
| `MoveUp(parent, item, positions)` | Reordering | Reorders sequence upward without `_EnsureWriteEnabled()` |
| `MoveDown(parent, item, positions)` | Reordering | Reorders sequence downward without `_EnsureWriteEnabled()` |
| `MoveToIndex(parent, item, index)` | Reordering | Moves item to specific index without `_EnsureWriteEnabled()` |
| `MoveBefore(parent, item, before_item)` | Reordering | Moves item before another without `_EnsureWriteEnabled()` |
| `MoveAfter(parent, item, after_item)` | Reordering | Moves item after another without `_EnsureWriteEnabled()` |

**Root Cause**: These methods delegate to `sequence.MoveTo()` (LibLCM C# method). The developer omitted the guard, likely assuming that the C# layer would enforce permissions. However, LibLCM has no read-only mode - write enforcement is entirely FlexLibs2's responsibility.

**Real-World Impact**: A script like this would modify a project even if run with `write_enabled=False`:
```python
entries = project.LexEntry.GetAll()
if entries:
    # This WILL reorder senses, bypassing write protection!
    project.LexEntry.MoveUp(entries[0], entries[0].SensesOS[1])
```

### ExampleOperations (1 method)

| Method | Type | Issue |
|--------|------|-------|
| `AddTranslation(example, translation_form, ws)` | Add/Mutation | Adds translation without `_EnsureWriteEnabled()` |

**Root Cause**: Collection mutation method; guard likely omitted by oversight during refactoring.

### LexEntryOperations (1 method)

| Method | Type | Issue |
|--------|------|-------|
| `SetHeadword(entry, form, ws, is_capitalized)` | Set/Mutation | Sets entry headword without `_EnsureWriteEnabled()` |

**Root Cause**: Sets a mutable field. Guard should be at method entry, likely missed in code review.

---

## Index-Based Detection

All 7 methods are now properly flagged in the API index with:
```json
{
  "name": "MoveUp",
  "is_mutating": true,
  "lcm_mapping": {
    "calls_ensure_write_enabled": false
  }
}
```

The index marks them as `is_mutating=true` (name-prefix heuristic) but `calls_ensure_write_enabled=false` (no guard detected), making them identifiable for:
- Script certification warnings
- Static analysis tools
- IDE hints

---

## Recommendations

### 1. **Add Guards to FlexLibs2 Source** (Priority: High)

Add `self._EnsureWriteEnabled()` at the start of each method:

```python
# BaseOperations.MoveUp (line 418)
def MoveUp(self, parent_or_hvo, item, positions=1):
    self._EnsureWriteEnabled()  # <-- Add this
    if positions <= 0:
        raise ValueError("positions must be positive integer")
    # ... rest of method
```

**File**: `d:/Github/_Projects/_LEX/flexlibs2/flexlibs2/code/BaseOperations.py`
**Lines to fix**:
- Line 418: `MoveUp` method
- Line 450: `MoveDown` method
- Line 484: `MoveToIndex` method
- Line 526: `MoveBefore` method
- Line 559: `MoveAfter` method

**File**: `d:/Github/_Projects/_LEX/flexlibs2/flexlibs2/code/Lexicon/ExampleOperations.py`
**Line**: AddTranslation method

**File**: `d:/Github/_Projects/_LEX/flexlibs2/flexlibs2/code/Lexicon/LexEntryOperations.py`
**Line**: SetHeadword method

### 2. **Runtime Protection** (Until Fixes Applied)

The `certify_script_readonly()` function in `validators.py` conservatively marks any unguarded mutating method as a potential write risk:

```python
cert = certify_script_readonly(code, api_index)
if not cert["is_certified_readonly"]:
    print(f"Warning: Unguarded mutations detected: {cert['mutating_calls']}")
```

Scripts using these 7 methods will:
- Fail certification if `write_enabled=False`
- Require explicit `confirmed=True` if `write_enabled=True`
- Log all violating calls by name

### 3. **Index Regeneration**

After fixing FlexLibs2 source:
```bash
python src/refresh.py --flexlibs2-only
```

This will:
- Update `is_mutating` and `calls_ensure_write_enabled` fields
- Re-evaluate all 1,237 methods
- Produce a v2.x.x index with improved precision

---

## Analysis Methodology

### Detection Logic

The analyzer uses **AST static analysis** to identify guard calls:

```python
# Detect self._EnsureWriteEnabled() in method body
for child in ast.walk(node):
    if isinstance(child, ast.Call):
        if (isinstance(child.func, ast.Attribute)
                and child.func.attr == '_EnsureWriteEnabled'
                and isinstance(child.func.value, ast.Name)
                and child.func.value.id == 'self'):
            result["calls_ensure_write_enabled"] = True
```

### Confidence Levels

- **High confidence**: Guard detected via AST (459 methods) - 100% accurate
- **Medium confidence**: Name-based heuristic (Create/Delete/Set*/Add*) - ~95% accurate
- **Conservative**: Unguarded mutating methods treated as write-risk regardless

### Coverage

- **FlexLibs2**: 104 classes × ~12 methods avg = 1,237 total methods analyzed
- **FlexLibs stable**: No `_EnsureWriteEnabled()` pattern; cannot tag accurately
- **LibLCM**: Pure C#; requires .NET reflection (not in scope for Python analysis)

---

## Verification

To verify the gaps exist in the source:

```bash
# Count _EnsureWriteEnabled calls in FlexLibs2
grep -r "self._EnsureWriteEnabled()" d:/Github/_Projects/_LEX/flexlibs2/flexlibs2/code/ | wc -l
# Expected: 459 (matches detected guards)

# Verify MoveUp lacks guard
grep -A 30 "def MoveUp" d:/Github/_Projects/_LEX/flexlibs2/flexlibs2/code/BaseOperations.py | grep -c "_EnsureWriteEnabled"
# Expected: 0 (no guard found)
```

---

## See Also

- [Script Certification](./SCRIPT_CERTIFICATION.md) - How untagged methods are handled at runtime
- [API Index Schema](./API_INDEX_SCHEMA.md) - Structure of `is_mutating` and `lcm_mapping` fields
- [FlexLibs2 MIGRATION_GUIDE](../flexlibs2/docs/MIGRATION_GUIDE.md) - Breaking changes in write protection
