# FLExTools Module Templates

This directory contains templates for writing FLExTools modules using flexlibs2.

## Files

### `flextools_module_template.py`

**Purpose:** Complete, well-documented template for any FLExTools module

**Features:**
- Mandatory flexlibs2 imports (prevents silent failure with wrong library)
- Standard entry point (`Main` function)
- Example implementation with common patterns
- Error handling best practices
- Helper function pattern
- Comprehensive notes and debugging tips

**How to use:**
1. Copy this file as your starting point
2. Replace `[Placeholders]` with your actual code
3. Keep the flexlibs2 imports at the top
4. Update the docstring with your module purpose

## Critical: Explicit Imports

⚠️ **IMPORTANT**: Every FLExTools module MUST explicitly import from flexlibs2:

```python
from flexlibs2 import (
    FLExProject,
    LexEntryOperations,
    LexSenseOperations,
    # ... other operations
)
```

**Why?** FLExTools loads the stable flexlibs library first. Without explicit flexlibs2 imports, your code will silently use the wrong version, causing subtle bugs that are hard to debug.

**What happens without it:**
```python
# WRONG - Uses stable flexlibs by accident
entry = project.LexEntry.GetAll()
gloss = entry.GetGloss()  # Wrong implementation!

# CORRECT - Guarantees flexlibs2
from flexlibs2 import LexSenseOperations
gloss = project.LexSense.GetGloss(sense)
```

## Common Operations

### Read Operations

```python
# Get all entries
entries = project.LexEntry.GetAll()

# Get entry form (headword)
form = project.LexEntry.GetLexemeForm(entry)

# Get all senses
senses = project.LexSense.GetAllSenses(entry)

# Get sense information
gloss = project.LexSense.GetGloss(sense)
definition = project.LexSense.GetDefinition(sense)
```

### Write Operations

```python
# Only if modify=True!
if modify:
    project.LexEntry.SetLexemeForm(entry, "new_form")
    project.LexSense.SetGloss(sense, "new_gloss")
```

### Error Handling

```python
try:
    result = project.LexEntry.GetAll()
except Exception as e:
    report.Error(f"Failed: {e}")
    import traceback
    report.Error(traceback.format_exc())
```

## FlexLibs2 Features

- **Multistring Normalization:** Returns `""` for empty fields, not `"***"`
- **Comprehensive Coverage:** ~90% of FieldWorks API wrapped
- **Better Error Messages:** Clear, actionable error text
- **Defensive Casting:** Handles descriptor protocol edge cases
- **Operations Pattern:** Organized around objects (LexEntry, LexSense) not functions

## Main Function Signature

Every FLExTools module must have this entry point:

```python
def Main(project, report, modify):
    """
    project: FLExProject instance connected to FieldWorks database
    report: Report object for output (visible in FLExTools UI)
    modify: Boolean - True if writes are enabled, False for read-only
    """
```

FLExTools will call this with these exact parameters.

## Debugging Tips

Use the report object for all output:
```python
report.Debug("Verbose debug message")     # Only shown if DEBUG enabled
report.Info("Progress message")           # Always shown
report.Error("Error message")             # Always shown, highlighted red
```

Don't print to console - FLExTools captures exceptions and won't show them.

## Version Information

- **Requires:** FlexLibs2 2.0+
- **Tested with:** FieldWorks 9.0+, Python 3.7+
- **Platform:** Windows (IronPython via FLExTools)

## Questions?

See the main `../CLAUDE.md` file for more information about:
- FLEx data conventions
- Namespace collision risks
- API versioning
- Property access patterns
