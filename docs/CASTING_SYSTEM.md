# Casting Detection & Correction System

## Overview

The casting system provides **three-layer protection** against polymorphic type errors across all 3 API flavors (flexlibs_stable, flexicon, liblcm).

This solves the problem Dennis encountered:
```python
# WRONG - ICmObject doesn't have HeadWord
for sense in senses:
    hw = sense.Owner.HeadWord.Text  # AttributeError: 'ICmObject' object has no attribute 'HeadWord'
```

## The Three Layers

### Layer 1: Pre-Execution Validation (Preventive)

**When:** Before code runs
**What:** Detects known polymorphic patterns that will fail
**How:** Uses `detect_casting_needs()` - static AST analysis against known C# type issues
**Result:** Rejects code with actionable fix suggestions

```json
{
  "error": "casting_issues_detected",
  "message": "Found 1 polymorphic property access issue(s) that require casting.",
  "severity": "error",
  "issues": [
    {
      "property": "HeadWord",
      "line": 5,
      "missing_on": ["ICmObject"],
      "available_on": ["ILexEntry"],
      "fix": "from SIL.LCModel import ILexEntry\nentry = ILexEntry(sense.Owner)\nheadword = entry.HeadWord.Text"
    }
  ]
}
```

**Works for all 3 flavors** because this is a C# data model issue, not wrapper-specific.

### Layer 2: Safe Helper Functions (Fallback)

**When:** Injected into all generated code
**What:** Functions that safely access properties with automatic fallback
**How:** Imported via `casting_helpers.py` or defined as fallbacks
**Result:** Code doesn't crash if casting is needed

#### Available Helpers

```python
# Safe property access with default value
headword = safe_get_property(sense.Owner, 'HeadWord', 'Unknown')

# Try casting to concrete type
from SIL.LCModel import ILexEntry
entry = smart_cast(sense.Owner, ILexEntry)
if entry:
    headword = entry.HeadWord.Text

# Combine cast + property access
headword = cast_or_default(sense.Owner, ILexEntry, 'HeadWord', 'Unknown')

# Specialized helpers for common patterns
headword = get_headword(sense)  # Works with both entries and senses
form = get_lexeme_form(entry)    # Get entry headword form
```

#### How Helpers Are Available

All generated code automatically includes casting helpers:

```python
from flexicon import FLExInitialize, FLExCleanup, FLExProject
# Auto-injected:
try:
    from casting_helpers import safe_get_property, smart_cast, cast_or_default, get_headword, get_lexeme_form
except ImportError:
    # Fallback definitions provided (minimal versions)
    def safe_get_property(obj, prop, default=None): ...
    def smart_cast(obj, target_type): ...
    # ... etc
```

This means:
- **flexlibs_stable**: Helpers available
- **flexicon**: Helpers available (integrates with cast_to_concrete)
- **liblcm**: Helpers available (handles pythonnet casting)

### Layer 3: On-Error Detection (Recovery)

**When:** If code runs and an error occurs
**What:** Detects `'ObjectType' object has no attribute 'Property'` errors
**How:** Parses error message and suggests `resolve_property()` tool
**Result:** User can look up exact casting requirements

```json
{
  "polymorphic_error_detected": true,
  "error_type": "PolymorphicAttributeError",
  "object_type": "ICmObject",
  "property_name": "HeadWord",
  "help": "Call resolve_property(property_name='HeadWord', context_entity='ICmObject') to find the correct property and required casting."
}
```

---

## Known Polymorphic Patterns (Detected by Layer 1)

These patterns always need casting across all 3 API flavors:

| Pattern | Missing On | Available On | Fix |
|---------|-----------|-------------|-----|
| `sense.Owner.HeadWord` | ICmObject | ILexEntry | `ILexEntry(sense.Owner).HeadWord.Text` |
| `entry.LexemeForm` | ICmObject | ILexEntry | `ILexEntry(entry).LexemeForm` |
| `sense.ReversalEntriesRC` | ILexSense (flexicon) | ILexSense (raw LCM) | Use raw sense or ReversalOperations |

---

## When Casting Is Needed

### Pattern 1: Collections Returning Base Types

```python
# These return ICmObject, not concrete types
for sense in entry.SensesOS:  # SensesOS returns base ILexSense
    # sense is ICmObject internally
    definition = sense.Definition  # May fail on base type
    # Fix: Cast to concrete type
    from SIL.LCModel import ILexSense
    concrete_sense = ILexSense(sense)
    definition = concrete_sense.Definition
```

### Pattern 2: Navigation Properties Returning Base Types

```python
sense = senses[0]

# sense.Owner is ICmObject, not ILexEntry
headword = sense.Owner.HeadWord  # WRONG - ICmObject doesn't expose HeadWord

# Fix: Cast to concrete type
from SIL.LCModel import ILexEntry
entry = ILexEntry(sense.Owner)
headword = entry.HeadWord.Text
```

### Pattern 3: Flexicon-Wrapped Objects

```python
# flexicon wrappers may not expose all collection properties
from flexicon import LexSenseOperations

# GetAll() returns a behavioral collection -- safe to subscript, len(), or
# re-iterate directly. Only wrap in list(...) if you specifically need a
# plain list.
sense = LexSenseOperations.GetAll(project)[0]

# Some collections only exist on raw LCM
reversals = sense.ReversalEntriesRC  # May not exist on wrapped object

# Fix 1: Unwrap if possible
if hasattr(sense, '_raw'):
    raw_sense = sense._raw
    reversals = raw_sense.ReversalEntriesRC

# Fix 2: Use Operations classes
reversals = project.Reversal.GetAll()  # Use dedicated operations
```

---

## Implementation Details

### Casting Detection (`validators.py`)

```python
def detect_casting_needs(code: str, casting_index: Optional[Dict] = None) -> dict:
    """
    Detect property access patterns that likely need casting.

    Returns:
    - has_casting_issues: bool
    - casting_issues: list of detected issues with fix suggestions
    - severity: "error" | "warning"
    """
```

**Detection Strategy:**
1. Uses regex to find known polymorphic patterns
2. If `casting_index` provided, checks against the full index
3. Returns specific line numbers and suggested fixes

### Safe Helpers (`casting_helpers.py`)

```python
# Universal casting pattern that works across all 3 APIs
def smart_cast(obj: Any, target_type: Type) -> Optional[Any]:
    """Try to cast object to target type, return None if fails."""
    try:
        return target_type(obj)
    except (TypeError, AttributeError):
        return None

# Specialized helper for common pattern
def get_headword(entry_or_sense: Any, default: str = "Unknown") -> str:
    """Get headword text from entry or sense's owner."""
    # Tries direct access first
    # Then tries casting sense.Owner to ILexEntry
    # Finally returns default
```

### Execution Integration (`handlers/execution.py`)

**Pre-flight checks in order:**
1. Mutation protection check (write safety)
2. **NEW: Casting needs check** ← Returns error with fixes
3. API discovery check
4. Output mechanism check
5. Undefined variables check
6. Missing imports check

**Auto-injection of helpers:**
All generated code includes casting helper imports/definitions for all 3 API modes.

---

## Error Flow Example: Dennis's HeadWord Case

### What Happens Now (With System)

```
1. User submits code with sense.Owner.HeadWord
   ↓
2. Pre-flight: detect_casting_needs() finds the pattern
   ↓
3. STOP - Return error with fix:
   "Missing on: ['ICmObject']"
   "Available on: ['ILexEntry']"
   "Fix: from SIL.LCModel import ILexEntry; entry = ILexEntry(sense.Owner)"
   ↓
4. User updates code to cast properly
   ↓
5. Code runs successfully
```

### What Would Happen Without System

```
1. User submits code with sense.Owner.HeadWord
   ↓
2. Code runs
   ↓
3. Runtime error: 'ICmObject' object has no attribute 'HeadWord'
   ↓
4. Error detection suggests: "Call resolve_property(...)"
   ↓
5. User must manually look up casting requirements
   ↓
6. User rewrites code
   ↓
7. Code runs successfully
```

**Difference:** Layer 1 prevents the error from happening at all, saving user time and frustration.

---

## Usage Examples

### Example 1: Using Safe Helpers

```python
from flexicon import FLExInitialize, FLExCleanup, FLExProject
# Casting helpers automatically available (or defined as fallback)

def Main(project, report, modifyAllowed):
    entries = project.LexEntry.GetAll()

    for entry in entries:
        # Instead of: hw = entry.Owner.HeadWord.Text (might fail)
        # Use safe helper:
        hw = get_headword(entry)  # Returns "Unknown" if fails

        senses = project.LexSense.GetAllSenses(entry)
        for sense in senses:
            # Access nested collection safely
            form = safe_get_property(sense.Owner, 'LexemeForm', '')
            report.Info(f"{hw}: {form}")
```

### Example 2: Explicit Casting (Recommended)

```python
from flexicon import FLExInitialize, FLExCleanup, FLExProject
from SIL.LCModel import ILexEntry

def Main(project, report, modifyAllowed):
    entries = project.LexEntry.GetAll()

    for entry in entries:
        # Explicit cast - clear intent
        entry_concrete = ILexEntry(entry)
        hw = entry_concrete.HeadWord.Text
        report.Info(f"Entry: {hw}")
```

### Example 3: With cast_or_default Helper

```python
from flexicon import FLExInitialize, FLExCleanup, FLExProject

def Main(project, report, modifyAllowed):
    senses = project.LexSense.GetAll()

    for sense in senses:
        # One-liner for cast + property access
        hw = cast_or_default(
            sense.Owner,
            'ILexEntry',  # Target type
            'HeadWord',     # Property to access
            'Unknown'       # Default if fails
        )
        report.Info(f"Headword: {hw}")
```

---

## Best Practices

### DO

✅ Import concrete types explicitly:
```python
from SIL.LCModel import ILexEntry, ILexSense, IMoForm
```

✅ Cast at the point of use:
```python
entry = ILexEntry(sense.Owner)
headword = entry.HeadWord.Text
```

✅ Use helpers when uncertain:
```python
headword = get_headword(sense)  # Safe default
```

✅ Handle None/default cases:
```python
hw = cast_or_default(obj, ILexEntry, 'HeadWord', 'Unknown')
if hw == 'Unknown':
    report.Warn("Entry has no headword")
```

### DON'T

❌ Assume base types have all properties:
```python
# Wrong - ICmObject doesn't have HeadWord
hw = sense.Owner.HeadWord.Text
```

❌ Ignore AttributeError:
```python
# Wrong - swallows real errors
try:
    hw = sense.Owner.HeadWord
except:
    pass
```

❌ Chain uncertain casts:
```python
# Wrong - breaks at first cast failure
hw = ILexEntry(ILexSense(entry).Owner).HeadWord.Text
```

---

## Testing

Run the casting detection test:

```bash
python test_casting_detection.py
```

This tests:
- Dennis's HeadWord error case (detected and fixed)
- ReversalEntriesRC issue (detected)
- Clean code (no false positives)

---

## Future Enhancements

1. **Auto-fix generation**: Return exact code to insert, not just error message
2. **Casting index expansion**: Add more polymorphic patterns from user feedback
3. **Type inference**: Track object types through code to predict casting needs earlier
4. **Smart imports**: Auto-add required imports when suggesting fixes
5. **Performance**: Cache casting patterns to skip re-scanning on multiple runs

---

## Related Documentation

- [FLEXTOOLS-STYLE-GUIDE.md](FLEXTOOLS-STYLE-GUIDE.md) - Code generation standards
- [PROGRESS.md](PROGRESS.md) - Casting system implementation progress
- [casting_helpers.py](../src/casting_helpers.py) - Helper function source code
