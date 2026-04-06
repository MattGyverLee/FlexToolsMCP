# FLExTools Script Flavors: Choose Your API

The MCP can generate scripts in **three flavors**, each with tradeoffs:

## Quick Comparison

| Flavor | API Size | Coverage | Complexity | Best For |
|--------|----------|----------|-----------|----------|
| **FlexLibs (stable)** | ~40 functions | Basic ops | Simple | Legacy systems, constraints |
| **FlexLibs2** | ~200 functions | 90% complete | Moderate | **Recommended** - most use cases |
| **LibLCM** | 500+ types | 100% complete | Complex | Power users, edge cases |

---

## Flavor 1: FlexLibs (Stable v1.x)

### When to Use
- ✓ Old FieldWorks versions (< 9.0)
- ✓ System constraints (limited Python)
- ✓ Simple read-only operations

### When NOT to Use
- ✗ Complex transformations
- ✗ Modern FieldWorks (9.0+)
- ✗ Need fine control

### Example
```python
from flexlibs import FLExProject

def Main(project, report, modify):
    entries = project.LexAllEntries()
    for entry in entries:
        form = project.LexiconGetEntryForm(entry)
        report.Info(form)
```

### Limitations
- Only ~40 core functions available
- Multistring handling requires "***" checks
- No helper methods
- No type safety

### Migration
To upgrade to flexlibs2:
```diff
- from flexlibs import FLExProject
+ from flexlibs2 import FLExProject, LexEntryOperations
```

---

## Flavor 2: FlexLibs2 (Recommended)

### When to Use
- ✓ **Most projects** (recommended)
- ✓ FieldWorks 9.0+
- ✓ Balance of power and simplicity
- ✓ Need multistring edge case handling

### When NOT to Use
- ✗ Legacy systems (old FieldWorks)
- ✗ Need absolute 100% API access

### Example
```python
from flexlibs2 import (
    FLExProject,
    LexEntryOperations,
    LexSenseOperations,
)

def Main(project, report, modify):
    entries = project.LexEntry.GetAll()
    for entry in entries:
        form = project.LexEntry.GetLexemeForm(entry)
        senses = project.LexSense.GetAllSenses(entry)
        report.Info(f"{form} ({len(senses)} senses)")
```

### Advantages
- 90% API coverage (200+ functions)
- Automatic multistring normalization ("***" → "")
- Operations pattern (object-centric)
- Better error messages
- Defensive casting for edge cases
- Well-documented (99% descriptions, 82% examples)

### Conversion to/from other flavors
- **From FlexLibs:** Easy migration (wrapper calls same underlying APIs)
- **From LibLCM:** Use flexlibs2 Operations methods instead of raw C# properties

---

## Flavor 3: LibLCM (Direct C#)

### When to Use
- ✓ Edge cases not covered by flexlibs2
- ✓ Performance-critical code
- ✓ Custom type handling
- ✓ Power users who understand C# data model

### When NOT to Use
- ✗ Simple scripts (overkill)
- ✗ Maintenance burden (complex code)
- ✗ Team not familiar with C#

### Example
```python
from flexlibs2.code.lcm_casting import cast_to_concrete, ILexEntry

def Main(project, report, modify):
    # Direct C# access via pythonnet
    all_entries = project.ServiceLocator.GetInstance("ILexdbAccess").AllInstances("LexEntry")

    for entry in all_entries:
        # Cast to concrete C# interface
        lex_entry = cast_to_concrete(entry, ILexEntry)
        form = lex_entry.LexemeForm.VernacularForm.Text
        report.Info(form)
```

### Advantages
- 100% API access
- Direct C# performance
- No abstraction overhead
- Access to internal/advanced features

### Disadvantages
- Complex code (requires C# knowledge)
- Multistring handling is manual ("***" checks needed)
- Edge case handling is your responsibility
- Harder to maintain and debug
- Type casting complexity

---

## Conversion Guide

### FlexLibs → FlexLibs2 (Easy ✓)

```python
# Before (FlexLibs)
entry = project.LexAllEntries()[0]
form = project.LexiconGetEntryForm(entry)

# After (FlexLibs2)
from flexlibs2 import LexEntryOperations
entry = project.LexEntry.GetAll()[0]
form = project.LexEntry.GetLexemeForm(entry)
```

### FlexLibs2 → LibLCM (Hard ✗)

```python
# Before (FlexLibs2)
form = project.LexEntry.GetLexemeForm(entry)  # Returns normalized string

# After (LibLCM)
from flexlibs2.code.lcm_casting import cast_to_concrete, ILexEntry
entry_obj = cast_to_concrete(entry, ILexEntry)
raw_form = entry_obj.LexemeForm.VernacularForm.Text  # Raw C# access
# Must handle "***" yourself
if raw_form == "***":
    form = ""
else:
    form = raw_form
```

### LibLCM → FlexLibs2 (Easy ✓)

If you have LibLCM code, wrap it with flexlibs2 for better UX:

```python
# Before (LibLCM raw)
entry_obj = cast_to_concrete(entry, ILexEntry)
raw_form = entry_obj.LexemeForm.VernacularForm.Text

# After (FlexLibs2 wrapper)
form = project.LexEntry.GetLexemeForm(entry)  # Handles edge cases
```

---

## Decision Tree

```
Does your system have FieldWorks 9.0+?
├─ NO → Use FlexLibs (stable) template
└─ YES → Does your use case need edge case handling?
    ├─ NO → Use FlexLibs2 template ✓ RECOMMENDED
    └─ YES → Does flexlibs2 cover it?
        ├─ YES → Use FlexLibs2 template ✓ RECOMMENDED
        └─ NO → Use LibLCM template (accept complexity)
```

---

## Asking the MCP

**To generate a script in a specific flavor:**

> "Generate a FLExTools script using **flexlibs2** that..."
> "Generate a FLExTools script using **LibLCM** that..."
> "Generate a FLExTools script using **flexlibs (stable)** that..."

**To port an existing script:**

> "Convert this flexlibs script to flexlibs2"
> "Upgrade this flexlibs script to work with flexlibs2"
> "Rewrite this in LibLCM for performance"

---

## Template Files

- `1-flexlibs-stable-template.py` - Use for legacy systems
- `2-flexlibs2-template.py` - **RECOMMENDED** for most projects
- `3-liblcm-template.py` - Use for edge cases and power users

See each template for detailed examples and best practices for that flavor.
