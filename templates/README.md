# FLExTools Script Templates

The MCP can generate scripts in **three flavors**, supporting porting and backporting between them.

## Quick Start

**Start here:** Read [`00-FLAVOR-GUIDE.md`](00-FLAVOR-GUIDE.md)

It explains:
- When to use each flavor
- Tradeoffs (complexity vs power)
- How to convert between flavors
- Decision tree for choosing

## Three Templates

### 1️⃣ FlexLibs Stable (Legacy)
**File:** `1-flexlibs-stable-template.py`

**Use when:**
- Old FieldWorks version (< 9.0)
- System can't upgrade
- Simple read-only operations

**Provides:** ~40 core functions (legacy, limited)

**Example:**
```python
from flexlibs import FLExProject

def Main(project, report, modify):
    entries = project.LexAllEntries()
```

---

### 2️⃣ FlexLibs2 (Recommended ⭐)
**File:** `2-flexlibs2-template.py`

**Use for:** **Most projects** (default choice)

**Provides:** 90% API coverage (~200 functions)

**Advantages:**
- Automatic "***" multistring normalization
- Better error messages
- Defensive casting for edge cases
- Well documented

**Example:**
```python
from flexlibs2 import FLExProject, LexEntryOperations

def Main(project, report, modify):
    entries = project.LexEntry.GetAll()
    for entry in entries:
        form = project.LexEntry.GetLexemeForm(entry)
```

---

### 3️⃣ LibLCM Direct (Power Users)
**File:** `3-liblcm-template.py`

**Use when:**
- Need edge cases not in flexlibs2
- Performance-critical code
- Comfortable with C# data model

**Provides:** 100% API access (but complex)

**Example:**
```python
from flexlibs2.code.lcm_casting import cast_to_concrete, ILexEntry

def Main(project, report, modify):
    entry = cast_to_concrete(entry_obj, ILexEntry)
    form_text = entry.LexemeForm.VernacularForm.Text
```

---

## Asking the MCP to Generate Scripts

### By Flavor
```
"Generate a FLExTools script using flexlibs2 that..."
"Generate a FLExTools script using LibLCM that..."
"Generate a FLExTools script using stable flexlibs that..."
```

### To Port Between Flavors
```
"Convert this flexlibs script to flexlibs2"
"Rewrite this in LibLCM for better performance"
"Upgrade this to use flexlibs2 instead"
```

---

## Flavor Comparison Table

| Aspect | FlexLibs (stable) | FlexLibs2 ⭐ | LibLCM |
|--------|-------------------|-------------|--------|
| **API Size** | ~40 functions | ~200 functions | 500+ types |
| **Coverage** | Basic ops only | 90% complete | 100% complete |
| **Complexity** | Low | Medium | High |
| **Multistring handling** | Manual "***" checks | Auto normalized | Manual "***" checks |
| **Error messages** | Generic | Better | Generic (raw C#) |
| **Edge cases** | Limited | Good | Full access |
| **Maintenance** | Easy | Easy | Hard |
| **Performance** | Good | Good | Excellent |
| **FieldWorks version** | 8.x - 9.x | 9.0+ | 9.0+ |
| **Recommended?** | Only if stuck | **YES ✓** | If flexlibs2 insufficient |

---

## Migration Paths

### FlexLibs → FlexLibs2 (Easy ✓)
Most flexlibs code ports directly to flexlibs2 with minimal changes:
- Method names change from `LexiconGetX()` to `Project.LexEntry.GetX()`
- Multistring handling becomes automatic
- More methods become available

### FlexLibs2 → LibLCM (Hard ✗)
Requires understanding C# data model:
- Use `cast_to_concrete()` to get C# objects
- Access properties directly instead of calling methods
- Handle multistring "***" manually again

### LibLCM → FlexLibs2 (Easy ✓)
Simplify complex LibLCM code by using flexlibs2 wrappers

---

## Best Practices by Flavor

### FlexLibs (Stable)
```python
# Check for empty multistrings explicitly
form = project.LexiconGetEntryForm(entry)
if form == "***":
    form = ""
```

### FlexLibs2 ⭐ (Recommended)
```python
# Automatic multistring handling
form = project.LexEntry.GetLexemeForm(entry)
if not form:  # Empty check is normal Python
    print("Glossless entry")
```

### LibLCM
```python
# Direct C# property access
entry_obj = cast_to_concrete(entry, ILexEntry)
form_text = entry_obj.LexemeForm.VernacularForm.Text
# Must check for "***" again
form = "" if form_text == "***" else form_text
```

---

## Version Information

- **FlexLibs:** v1.2.8 (stable, legacy)
- **FlexLibs2:** v2.0+ (recommended)
- **LibLCM:** v11.0.0+
- **FieldWorks:** 9.0+ for flexlibs2/LibLCM, 8.x for stable flexlibs

---

## Decision Tree

```
Has your system got FieldWorks 9.0+?
│
├─ NO → Use FlexLibs (stable) template
│       └─ Contact your admin about upgrading
│
└─ YES → Does flexlibs2 cover your use case?
    │
    ├─ YES → Use FlexLibs2 template ⭐ RECOMMENDED
    │        └─ Simplest, most maintainable
    │
    └─ NO → Is it an edge case?
        │
        ├─ Maybe, but unsure → Try flexlibs2 first anyway
        │
        └─ Yes, definitely need full API → Use LibLCM template
                └─ Accept the complexity cost
```

---

## Getting Help

See each template file for:
- Detailed examples
- Error handling patterns
- Helper function templates
- Common pitfalls and solutions
- Performance notes

Read `00-FLAVOR-GUIDE.md` for:
- When to use each flavor
- Conversion examples between flavors
- Advantages/disadvantages
- Full feature comparison
