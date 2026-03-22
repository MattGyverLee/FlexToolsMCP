# LibLCM Contextual Mutation Analysis

**Feature**: Intelligent detection of raw LibLCM mutations with protection context awareness.

**Problem Solved**: The MCP needed to understand that direct LibLCM calls are safe **when protected by guards**, but unsafe when unprotected.

---

## Overview

The MCP now performs **control-flow analysis** to detect:
1. **Unprotected LibLCM mutations** - flagged as unsafe in read-only mode
2. **Protected LibLCM mutations** - allowed if guarded by `modifyEnabled` or `writeEnabled`

This enables safer, more flexible scripts that can use raw LibLCM when needed, as long as they're properly guarded.

---

## What Gets Detected

### Mutation Patterns

Raw LibLCM methods that modify database state:

```python
# Direct object creation/deletion
project._cache.CreateObject(...)     # Flagged
project._cache.DeleteObject(...)     # Flagged

# Non-undoable transactions (major warning)
project._cache.BeginNonUndoableTask()  # Flagged

# Collection mutations
entry.SensesOS.Add(sense)             # Flagged
entry.SensesOS.Remove(sense)          # Flagged
entry.AlternateFormsOS.Clear()        # Flagged
collection.MoveTo(old_index, new_index)  # Flagged
collection.Insert(index, item)        # Flagged
```

### Protection Guards

Code blocks that make mutations safe:

```python
# With modifyEnabled context manager
with project.modifyEnabled:
    project._cache.CreateObject(...)  # SAFE

# With writeEnabled conditional
if project.writeEnabled:
    entry.SensesOS.Add(sense)        # SAFE

# Both forms work
if self.project.writeEnabled:
    ...                             # SAFE

with self.project.modifyEnabled:
    ...                             # SAFE
```

---

## Examples

### Example 1: Unprotected Call (Fails Certification)

```python
# Script: unsafe_script.py
entry = project.LexEntry.Find("run")
project._cache.CreateObject(...)  # Unprotected!

# Certification result:
{
  "is_certified_readonly": False,
  "confidence": "high",
  "unprotected_liblcm_calls": [
    {
      "method": "CreateObject",
      "line": 3,
      "context": "project._cache.CreateObject(...)",
      "is_mutating": True
    }
  ]
}
```

### Example 2: Protected Call (Passes Certification)

```python
# Script: safe_script.py
entry = project.LexEntry.Find("run")

with project.modifyEnabled:
    project._cache.CreateObject(...)  # Protected!

# Certification result:
{
  "is_certified_readonly": True,
  "confidence": "high",
  "protected_liblcm_calls": [
    {
      "method": "CreateObject",
      "line": 4,
      "context": "project._cache.CreateObject(...)"
    }
  ]
}
```

### Example 3: Mixed (Fails Due to Unprotected)

```python
# Script: mixed_script.py
with project.modifyEnabled:
    project._cache.CreateObject(...)  # Protected

project._cache.DeleteObject(...)      # Unprotected!

# Certification result:
{
  "is_certified_readonly": False,
  "unprotected_liblcm_calls": [
    {"method": "DeleteObject", "line": 4, ...}
  ],
  "protected_liblcm_calls": [
    {"method": "CreateObject", "line": 2, ...}
  ]
}
```

---

## Implementation Details

### Detection Functions

#### `find_liblcm_mutations(code: str) -> List[Dict]`

Scans code for raw LibLCM mutation patterns using regex.

**Patterns detected**:
- `_cache.CreateObject(`, `_cache.DeleteObject(`, `_cache.BeginNonUndoableTask(`
- `.Add(`, `.Remove(`, `.Clear(`, `.MoveTo(`, `.Insert(`

**Returns**: List of mutations with:
- `method`: Method name (e.g., "CreateObject")
- `line`: Line number in code
- `category`: Type of mutation (Create, Delete, Mutate, Reorder)
- `context`: First 60 characters of the line for display

#### `find_protected_ranges(code: str) -> List[tuple]`

Uses Python's AST module to identify protected code blocks.

**Detects**:
- `with project.modifyEnabled:` blocks
- `with self.project.modifyEnabled:` blocks
- `if project.writeEnabled:` blocks
- `if self.project.writeEnabled:` blocks
- `if project.writeEnabled == True:` blocks

**Returns**: List of `(start_line, end_line)` tuples representing protected ranges.

#### `certify_script_readonly(code: str, api_index) -> dict`

Enhanced to call both detection functions and match mutations to protection contexts.

**New result fields**:
- `unprotected_liblcm_calls`: Mutations without guards
- `protected_liblcm_calls`: Mutations with guards

**Logic**:
```
For each detected mutation:
  If mutation line is within a protected range:
    → Add to protected_liblcm_calls
  Else:
    → Add to unprotected_liblcm_calls
    → Set is_certified_readonly = False
```

---

## Certification Semantics

| Scenario | is_certified_readonly | Confidence |
|----------|---------------------|----|
| No mutations | `True` | `high` |
| Only FlexLibs2 methods | `True` | `high` |
| Only protected LibLCM | `True` | `high` |
| Mixed protected + FlexLibs2 | `True` | `high` |
| Unprotected LibLCM present | `False` | `high` |
| Unknown FlexLibs2 methods | `False` | `low` |

---

## Use Cases

### Safe: Conditional Batch Operations

```python
# OK: Protected by writeEnabled check
if project.writeEnabled:
    for entry in project.LexEntry.GetAll():
        project._cache.CreateObject(...)
```

### Safe: Scoped Modifications

```python
# OK: Protected by modifyEnabled block
with project.modifyEnabled:
    entry = project.LexEntry.Find("run")
    entry.SensesOS.Add(project._cache.CreateObject(...))
```

### Unsafe: Unprotected Direct Access

```python
# BAD: No protection
entry = project.LexEntry.Find("run")
project._cache.BeginNonUndoableTask()  # Will fail certification
```

### Safe: FlexLibs2 Already Guards

```python
# OK: No need for extra guard (FlexLibs2 has _EnsureWriteEnabled)
entry = project.LexEntry.Create("new_word")
entry.SensesOS.Add(project.LexSense.Create(...))
```

---

## Testing

Run the test suite:

```bash
python tests/test_script_certification.py
```

**Coverage**:
- `test_unprotected_liblcm_calls`: Direct calls without guards
- `test_protected_liblcm_with_modifyenabled`: `with project.modifyEnabled:` blocks
- `test_protected_liblcm_with_writeenabled`: `if project.writeEnabled:` blocks
- `test_mixed_protected_and_unprotected`: Mixed scenarios
- `test_collection_mutations`: .Add, .Remove, .Clear, .Insert, .MoveTo

All tests passing ✓

---

## Limitations

**Not detected**:
- Nested protection contexts (only outer block matters)
- Complex conditionals: `if a or (b and c): ...` (only simple checks detected)
- Try/except handlers (assumed unprotected)
- Else/elif branches of unprotected if statements

**Conservative approach**: If line number falls outside detected ranges, it's marked unprotected. Better to flag safe code as unsafe than miss genuine risks.

---

## Future Enhancements

Possible improvements:
1. **Nested context tracking** - handle `if writeEnabled: with modifyEnabled: ...`
2. **Try/except analysis** - consider error handling context
3. **Variable tracking** - recognize `w = project.writeEnabled; if w: ...`
4. **LibLCM state analysis** - detect UnitOfWork state changes
5. **Cross-module analysis** - track guards across function calls

---

## See Also

- [Script Certification](./SCRIPT_CERTIFICATION.md)
- [Untagged Mutating Methods](./UNTAGGED_MUTATING_METHODS.md)
- [Async Write Locking](./ASYNC_CONCURRENCY_ANALYSIS.md)
