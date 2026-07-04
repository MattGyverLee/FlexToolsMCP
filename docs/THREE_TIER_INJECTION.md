# Three-Tier Casting Helper Injection Strategy

## Overview

The system now uses an **intelligent three-tier strategy** to optimize casting helper injection based on pre-flight validation results. This eliminates overhead for safe code while providing defensive protection for edge cases.

**Problem Solved**: Previously, casting helpers were injected into EVERY execution, adding 200+ bytes even when not needed. Now they're injected only when necessary.

---

## The Three Tiers

### Tier 1: `none` (Lightweight - No Helpers)

**When**: Pre-flight validation found NO casting issues
**Cost**: 0 bytes of helper code
**What gets injected**: Nothing

```python
# User code runs with NO helper definitions
api_imports = """from flexicon import FLExInitialize, FLExCleanup, FLExProject"""
# ← No casting helpers added
```

**Safe because**: Pre-flight confirmed the code doesn't use problematic patterns like `sense.Owner.HeadWord`

### Tier 2: `minimal` (Balanced - Only What's Needed)

**When**: Pre-flight found casting issues BUT user confirmed code is correct
**Cost**: ~50-100 bytes (only needed helpers)
**What gets injected**: Only the helpers that are actually needed

```python
api_imports = """from flexicon import FLExInitialize, FLExCleanup, FLExProject
try:
    from casting_helpers import get_headword, safe_get_property
except ImportError:
    def get_headword(entry, default="Unknown"):
        try: return entry.HeadWord.Text
        except: return default
    def safe_get_property(obj, prop, default=None):
        try: return getattr(obj, prop, default)
        except: return default
"""
```

**Example**: If code only uses `HeadWord` pattern, only `get_headword` and `safe_get_property` are injected.

### Tier 3: `full` (Defensive - Complete Suite)

**When**: Defensive mode enabled OR unusual situation detected
**Cost**: ~200 bytes (all helpers)
**What gets injected**: All possible helpers (safe_get_property, smart_cast, cast_or_default, get_headword, get_lexeme_form)

```python
api_imports = """from flexicon import FLExInitialize, FLExCleanup, FLExProject
try:
    from casting_helpers import safe_get_property, smart_cast, cast_or_default, get_headword, get_lexeme_form
except ImportError:
    def safe_get_property(obj, prop, default=None): ...
    def smart_cast(obj, target_type): ...
    def cast_or_default(obj, target_type, prop=None, default=None): ...
    def get_headword(entry, default="Unknown"): ...
    def get_lexeme_form(entry, default=""): ...
"""
```

**Safe because**: Provides complete defensive coverage for any casting pattern

---

## How It Works: End-to-End

### Flow

```
1. User submits code
        ↓
2. Pre-flight: detect_casting_needs(code)
        ↓
3. Returns: {
    "has_casting_issues": bool,
    "helpers_needed": set,           ← Track which helpers are used
    "injection_tier": str            ← Determine which tier to use
   }
        ↓
4a. If issues found:
    Return error with fixes

4b. If NO issues:
    Continue with determined injection_tier
        ↓
5. Call _get_api_mode_imports(api_mode, helpers_needed, injection_tier)
        ↓
6. Generate imports with appropriate helpers
        ↓
7. Execute code
```

### Decision Tree

```
┌─ Pre-flight passed?
├─ No → Return error with fixes (code doesn't execute)
└─ Yes → Determine tier
   ├─ No casting patterns found → Tier 1 (none)
   ├─ Patterns found but pre-flight approved → Tier 2 (minimal)
   └─ Defensive mode enabled → Tier 3 (full)
```

---

## Implementation Details

### 1. Casting Needs Detection

Updated `detect_casting_needs()` now returns:

```python
{
    "has_casting_issues": bool,        # Any issues found?
    "casting_issues": [...],           # Specific issues with fixes
    "helpers_needed": set,             # {"get_headword", "safe_get_property"}
    "injection_tier": str,             # "none" | "minimal" | "full"
    "severity": str                    # "error" | "warning" | "none"
}
```

### 2. Helper Injection Function

New `_get_casting_helpers_code()` generates appropriate code:

```python
def _get_casting_helpers_code(injection_tier: str = "full",
                               helpers_needed: Optional[set] = None) -> str:
    """Generate casting helpers code based on tier."""

    if injection_tier == "none":
        return ""  # Empty string - no injection

    if injection_tier == "minimal":
        # Only import/define specific helpers
        return f"""
try:
    from casting_helpers import {', '.join(sorted(helpers_needed))}
except ImportError:
    # Minimal fallback definitions for {helpers_needed}
    ...
"""

    # Full injection for tier 3
    return """
try:
    from casting_helpers import safe_get_property, smart_cast, ...
except ImportError:
    # Complete fallback definitions
    ...
"""
```

### 3. API Mode Imports Integration

Updated `_get_api_mode_imports()` signature:

```python
def _get_api_mode_imports(
    api_mode: str,
    helpers_needed: Optional[set] = None,
    injection_tier: str = "full"
) -> Tuple[str, dict]:
```

Now works for all 3 modes:
- **flexlibs_stable**: Uses tier-based injection
- **flexicon**: Uses tier-based injection
- **liblcm**: Uses tier-based injection

### 4. Execution Handler Integration

In `handle_run_operation()`:

```python
# After pre-flight passes:
injection_tier = casting_check.get("injection_tier", "full")
helpers_needed = casting_check.get("helpers_needed", set())

# Log for telemetry
operations_logger.debug(f"Three-tier injection: tier={injection_tier}, helpers={helpers_needed}")

# Get imports with appropriate tier
api_imports, _ = _get_api_mode_imports(api_mode, helpers_needed, injection_tier)
```

---

## Performance Impact

### Code Size

| Tier | Overhead | Reduction |
|------|----------|-----------|
| Tier 1 (none) | 0 bytes | -100% ✅ |
| Tier 2 (minimal) | 50-100 bytes | -50-75% ✅ |
| Tier 3 (full) | 200 bytes | 0% (baseline) |

### Execution Time

- Tier 1 (no helpers): No imports, no overhead
- Tier 2 (minimal): Fast import + fallback for ~2-3 helpers
- Tier 3 (full): Single try/except + fallback for 5 helpers

**All tiers**: <1ms for import, negligible compared to actual work

### Memory

All tiers: ~1KB per execution (negligible)

---

## Examples

### Example 1: Safe Code (Tier 1)

**User code:**
```python
from SIL.LCModel import ILexEntry

for entry in project.LexEntry.GetAll():
    entry_concrete = ILexEntry(entry)  # Explicit cast
    headword = entry_concrete.HeadWord.Text
    report.Info(f"Entry: {headword}")
```

**Pre-flight result**: `injection_tier = "none"`, `helpers_needed = set()`

**Generated code:**
```python
from flexicon import FLExInitialize, FLExCleanup, FLExProject
# ← NO casting helpers injected (user was explicit about casting)

def Main(project, report, modifyAllowed):
    # User's code runs as-is
```

**Cost**: Minimal - only what's needed

---

### Example 2: Conditional Casting (Tier 2)

**User code:**
```python
for sense in senses:
    # Uses safe helper for potential casting issues
    hw = safe_get_property(sense.Owner, 'HeadWord', 'Unknown')
    report.Info(f"Entry: {hw}")
```

**Pre-flight result**:
```python
injection_tier = "minimal"
helpers_needed = {"safe_get_property"}
```

**Generated code:**
```python
from flexicon import FLExInitialize, FLExCleanup, FLExProject
try:
    from casting_helpers import safe_get_property
except ImportError:
    def safe_get_property(obj, prop, default=None):
        try: return getattr(obj, prop, default)
        except: return default

def Main(project, report, modifyAllowed):
    # User's code runs with only the helper it needs
```

**Cost**: Balanced - only ~30 bytes for the one helper used

---

### Example 3: Defensive Mode (Tier 3)

**User code:**
```python
for sense in senses:
    # Complex navigation without explicit casting
    hw = sense.Owner.HeadWord.Text
    report.Info(f"Entry: {hw}")
```

**Pre-flight result**: `injection_tier = "full"` (issues found, defensive mode)

**Generated code:**
```python
from flexicon import FLExInitialize, FLExCleanup, FLExProject
try:
    from casting_helpers import safe_get_property, smart_cast, cast_or_default, get_headword, get_lexeme_form
except ImportError:
    # Complete fallback for all helpers
    ...

def Main(project, report, modifyAllowed):
    # User's code runs with full helper suite available
```

**Cost**: Full suite injected for safety (200 bytes)

---

## Telemetry & Monitoring

### Logged Information

```python
operations_logger.debug(f"Three-tier injection: tier={injection_tier}, helpers_needed={helpers_needed}")
```

This helps track:
- Which tier is most commonly used
- Which helpers are actually needed
- Optimization opportunities

### Analysis Over Time

- **Tier 1 (none)** frequency: Most users write safe code
- **Tier 2 (minimal)** frequency: Users who need specific helpers
- **Tier 3 (full)** frequency: Defensive mode or edge cases

---

## Future Enhancements

1. **User-configurable tiers**: Allow users to prefer tier 1 (fast) vs tier 3 (safe)
2. **Tier statistics**: Track which helpers are used most often
3. **Auto-downgrade**: If helpers never used, suggest tier 1 next time
4. **Tier recommendations**: "Your code works best with tier 2" suggestions

---

## Migration from Old System

**Old system**: Always inject all helpers (200 bytes per execution)

**New system**: Inject based on tier (0-200 bytes, usually 0-50)

**Backward compatible**: Code that worked before still works, just more efficiently

---

## Related Documentation

- [CASTING_SYSTEM.md](CASTING_SYSTEM.md) - Complete casting system overview
- [casting_helpers.py](../src/casting_helpers.py) - Helper function implementations
- [validators.py](../src/server/validators.py) - detect_casting_needs() function
- [handlers/execution.py](../src/server/handlers/execution.py) - Three-tier integration
