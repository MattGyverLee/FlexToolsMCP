# FLExTools Script Style Guide

This guide helps AI assistants and users generate **correct, maintainable FLExTools scripts** that follow proven patterns from successful implementations.

---

## CRITICAL: Single Source of Truth

**Write ONE module. Run it everywhere.**

### Execution Contexts (Same Code)

```
┌─ FLExTools GUI
│  └─ Load module → Run directly in FLExTools application
│
├─ FlexToolsMCP (MCP Server)
│  ├─ run_module() → Run module via MCP (same code as GUI)
│  └─ run_operation() → Quick ad-hoc snippets (ONE-OFFS only)
```

### The Rule

**CANONICAL FORM:** A module with `Main(project, report, modifyAllowed)` function.

✓ **DO:**
- Write one module file with Main()
- Run it via FLExTools GUI
- Run it via `flextools_run_module()` in FlexToolsMCP
- Use the same code everywhere (FLExTools, MCP, command line)

✗ **DON'T:**
- Maintain separate `my_operation.py` and `my_module.py` files with similar logic
- Copy-paste snippets into different execution paths
- Let versions drift apart across different tools

### Why This Matters

**Code divergence = false sense of security.** If you have:
- Operation version tested: "Works, I'll use it"
- Module version (slightly different): "I already tested this"
- Result: **Data corruption** or **silent failures**

The `Main()` function allows **one codebase to work in both contexts**. Use it.

### Snippets vs Modules

FlexToolsMCP's `flextools_run_module()` accepts **two equally-valid shapes**:

| Shape | When | Look-and-feel |
| --- | --- | --- |
| **Bare snippet** (no `Main`) | Exploration, probes, one-shot edits | A few lines that use the pre-injected `project`, `report`, `modifyAllowed` |
| **Full module** (`Main(...)` + `docs` + `FlexToolsModule`) | Code the user is keeping or running from the FlexTools GUI | Template from `flextools_get_module_template` |

**Bare snippets are first-class.** Don't wrap a 4-line probe in `Main()` boilerplate just because "modules are canonical" -- the runner injects the same execution environment either way, and the `if modifyAllowed:` guard rule applies to both.

**Graduate to the module form when** the user asks to save, name, deploy, or run-from-FlexTools-GUI the code. That's when you call `flextools_get_module_template`. Issue #24's "skeleton closet" is the planned long-term home for working snippets; until that ships, the module-template is the persistence path.

### Save-time hygiene: in-code intent comment

When you graduate a snippet (or write a full module), drop a one-line `# User asked: ...` comment at the top of the file/code block paraphrasing the human's request. Post-mortems on shipped logs depend on this -- when something breaks weeks later, the intent comment is the single line that lets the next reader see what the script was trying to do.

```python
# User asked: Add a Pinyin (zh-Latn-pinyin) gloss to every sense whose English gloss starts with "to ".

from flexicon import FLExProject, LexSenseOperations
# ... rest of module
```

This pairs with the `user_intent` parameter on `flextools_run_module` (see issue #18) -- the parameter captures intent in the structured log, the comment captures it in the saved artifact.

---

## For AI Assistants (Claude, Copilot, etc.)

When generating FLExTools scripts, **match the form to the task**: bare snippet for exploration and one-shots, full module (template from `flextools_get_module_template`) when the code is being saved or run from the FlexTools GUI. The MCP tool `flextools_run_module()` executes both shapes against the same execution environment.

### 1. Choose the Right Flavor

```python
# USE FLEXICON BY DEFAULT
# Unless:
#   - User explicitly requests a specific flavor
#   - FieldWorks < 9.0 (use stable flexlibs)
#   - Edge case not covered by flexicon (use LibLCM)

from flexicon import FLExProject, LexEntryOperations, LexSenseOperations
```

**Never assume stable flexlibs** - it has ~40 functions (limiting).

### 2. Always Add Clickable Navigation Links

Use `BuildGoToURL()` to help users navigate FLExTools output back to FieldWorks:

```python
# Include this in every script that processes entries/senses
try:
    entry_url = project.BuildGotoURL(entry)
    report.Info(f"Entry: {entry_url}")  # User can click this
except Exception:
    pass  # Not available in all versions
```

This was discovered by Dennis - it's a **proven UX improvement**.

### 3. Explicit Imports (CRITICAL)

```python
# ALWAYS import explicitly from flexicon
from flexicon import (
    FLExProject,
    LexEntryOperations,
    LexSenseOperations,
    ReversalOperations,
    # ... others as needed
)

# DON'T rely on global imports (FLExTools will shadow with stable flexlibs)
```

**Why:** FLExTools loads stable flexlibs first. Without explicit imports, code silently uses the wrong library.

### 4. Proper Report Usage

```python
# Progress/information
report.Info(f"Processing {count} entries...")

# Clickable links (use BuildGoToURL)
report.Info(f"  {form}: {entry_url}")

# Verbose debugging (only shown if DEBUG mode)
report.Debug(f"Internal state: {some_var}")

# Warnings (logged but not blocking)
report.Warning("No senses found for this entry")

# Errors (always shown, highlighted)
report.Error(f"Failed to process entry: {e}")
```

**Don't use print()** - FLExTools captures exceptions and won't display console output.

### 5. Multistring Handling

```python
# Flexicon (recommended)
gloss = project.LexSense.GetGloss(sense)
if not gloss:  # Empty check is normal Python
    report.Info("Gloss is empty")

# FlexLibs stable (legacy)
gloss = project.LexiconGetSenseGloss(sense)
if gloss == "***":  # Must check for "***"
    gloss = ""

# LibLCM (raw C#)
gloss_text = sense.Gloss.AnalysisDefaultWritingSystem.Text
if gloss_text == "***":  # Must check for "***"
    gloss = ""
```

### 6. Error Handling Pattern

```python
def Main(project, report, modify):
    try:
        # Your implementation
        entries = project.LexEntry.GetAll()
        for entry in entries:
            try:
                # Process individual items
                form = project.LexEntry.GetLexemeForm(entry)
                report.Info(f"  {form}")
            except Exception as e:
                report.Error(f"  Error: {e}")

        report.Info("Complete!")

    except Exception as e:
        report.Error(f"Fatal error: {e}")
        import traceback
        report.Error(traceback.format_exc())
```

**Always wrap in try/except** - FLExTools silences unhandled exceptions.

### 7. Write Permission Checking - CRITICAL

**ALWAYS check `modifyAllowed` before ANY write operation** (standard FLExTools parameter)

Note: `modifyAllowed` is the **per-script control** (FLExTools passes this parameter).
Don't confuse it with `project.writeEnabled` (system permission setting - different scope).

```python
def Main(project, report, modifyAllowed):
    # ALWAYS check modifyAllowed before ANY write operation
    if modifyAllowed:
        project.LexEntry.SetLexemeForm(entry, new_form)
        report.Info(f"✓ Updated: {new_form}")
    else:
        report.Info(f"(Would update to: {new_form})")
```

**Lightweight op form** (no `Main` function — bare snippet via `run_module`):

`modifyAllowed` is exposed as a top-level namespace variable, so the same guard pattern works at script root:

```python
# Bare snippet - no Main, no docs, no FlexToolsModule binding.
# modifyAllowed and write_enabled are pre-injected; use either name.
for entry in project.LexEntry.GetAll():
    if some_condition(entry):
        if modifyAllowed:
            project.LexEntry.SetLexemeForm(entry, new_form)
            report.Info(f"Updated: {new_form}", project.BuildGotoURL(entry))
        else:
            report.Info(f"(Would update to: {new_form})", project.BuildGotoURL(entry))
```

**UNPROTECTED WRITES ARE A CRITICAL BUG**
- Every write must be guarded with `if modifyAllowed:`
- Writes without protection will silently corrupt data
- MCP tools detect and warn about unprotected writes
- Always test in read-only mode first

**Examples of unprotected writes (BAD):**
```python
# WRONG - No permission check!
project.LexEntry.SetLexemeForm(entry, new_form)

# WRONG - Missing permission check!
entry.LexemeForm = new_value

# WRONG - Modification without guard!
project.LexSense.SetGloss(sense, "new gloss")
```

**Correct pattern:**
```python
# CORRECT - Protected write
if modifyAllowed:
    project.LexEntry.SetLexemeForm(entry, new_form)

# CORRECT - Protected with reporting
if modifyAllowed:
    entry.LexemeForm = new_value
    report.Info(f"Updated: {new_value}")
else:
    report.Info(f"(Would set to: {new_value})")
```

Allow users to preview changes without write access enabled.

### 8. Helper Functions

**Pre-injected runtime helpers** (MCP runner only — do NOT redefine these):

The MCP runner injects these into the execution namespace before running your code, in both lightweight ops and full modules. Importing them is unnecessary and reinventing them is a code smell.

> ⚠️ **Scope warning:** these helpers exist only inside the MCP runner subprocess. If you save your code as a FlexTools module file (`.py` in the FlexTools modules folder), the helpers are NOT there when FlexTools loads the file — inline your own copies, or stick to standard flexicon calls.

```python
# Empty-multistring detection (covers None, "", and "***")
if is_empty_multistring(gloss):
    report.Warning("Gloss is empty")

# The literal "***" placeholder constant for direct comparisons
if raw_text == FLEX_EMPTY_PLACEHOLDER:
    raw_text = ""

# Writing-system lookup by name or tag (substring match, case-insensitive)
ws_handle = find_writing_system(project, "pyn")  # finds "Pinyin", "zh-Latn-pinyin", etc.

# Enumerate writing systems with their display names and tags
for ws_info in list_writing_systems(project):
    report.Info(f"{ws_info['name']} ({ws_info['tag']})")
```

**User-defined helpers** — include reusable patterns specific to your script:

```python
def report_with_link(project, report, obj, label):
    """Report with clickable link - Dennis's proven pattern"""
    try:
        url = project.BuildGotoURL(obj)
        report.Info(f"{label} {url}")
        return True
    except Exception:
        return False

def multistring_safe(project, sense, field_name):
    """Get multistring field safely (flexicon)"""
    try:
        if field_name == "gloss":
            return project.LexSense.GetGloss(sense)
        elif field_name == "definition":
            return project.LexSense.GetDefinition(sense)
        return ""
    except Exception:
        return ""
```

---

## Best Practices Summary

### DO ✓

- ✓ Use flexicon by default (unless constrained)
- ✓ Add BuildGoToURL links for navigation
- ✓ Import explicitly from flexicon
- ✓ Use report.Info/Warning/Error appropriately
- ✓ Wrap in try/except at multiple levels
- ✓ **ALWAYS check `modifyAllowed` before ANY write** (CRITICAL)
- ✓ Include helper functions for reuse
- ✓ Report progress frequently
- ✓ Test on actual FieldWorks projects (read-only first)
- ✓ Document why you chose a specific flavor
- ✓ Use the unified module approach with Main() for all code

### DON'T ✗

- ✗ Use print() - FLExTools won't show it
- ✗ Assume stable flexlibs is available/correct
- ✗ Skip error handling (FLExTools silences exceptions)
- ✗ **Write without checking `modifyAllowed` flag (DATA CORRUPTION RISK)**
- ✗ Leave BuildGoToURL out (users benefit from navigation)
- ✗ Process huge collections without reporting progress
- ✗ Use LibLCM for simple operations (overkill)
- ✗ Ignore multistring "***" handling (stable flexlibs/LibLCM)
- ✗ Swallow exceptions silently (always report)
- ✗ Generate code without using templates
- ✗ Use parameter name `modify` - it's `modifyAllowed`
- ✗ Maintain separate operation vs module versions (causes divergence)

---

## The Unified Module Approach

FlexToolsMCP uses **only** `flextools_run_module()` - a single, unified execution path:

```python
# ALWAYS use this pattern, even for quick tests
def Main(project, report, modifyAllowed):
    """Standard FLExTools entry point."""
    entries = project.LexEntry.GetAll()
    report.Info(f"Found {len(entries)} entries")

    if modifyAllowed:
        # Make changes here
        pass
    else:
        report.Info("(Preview mode - no changes)")
```

### Benefits of Single-Tool Design

- **No code divergence**: One module works everywhere
- **Consistent testing**: Test once, run everywhere
- **Easier maintenance**: No separate operation/module versions to sync
- **Better safety**: Write protection always applies
- **Cleaner MCP interface**: One tool instead of two

This design emerged from lessons learned about code divergence - using two separate tools led to bugs.

---

## Template Selection

When generating a script:

1. **Default** → Use `2-flexicon-template.py`
2. **User says "stable flexlibs"** → Use `1-flexlibs-stable-template.py`
3. **User says "edge case" or "performance"** → Use `3-liblcm-template.py`
4. **Unsure** → Ask the user which flavor, or use flexicon

---

## Real-World Examples from Dennis's Work

Dennis discovered these patterns through actual FLExTools usage:

### Pattern 1: Navigation Links
```python
# Dennis's working discovery
rev_url = project.BuildGotoURL(rev_entry)
sns_url = project.BuildGotoURL(sense)
report.Info("  Goto Reversal: {}".format(rev_url))
report.Info("  Goto Sense:    {}".format(sns_url))
```
**Impact:** Users can click links instead of manually searching for items.

### Pattern 2: Error Recovery
Dennis bounced between approaches and found that:
- When one method fails, try the alternative
- Don't give up on the whole flavor
- Report what you tried
```python
try:
    result = project.LexEntry.GetAll()
except Exception as e:
    report.Error(f"Method failed: {e}")
    # Try alternative approach
```

### Pattern 3: Namespace Awareness
Dennis lost trust in flexicon when hitting the OperationsMethod bug. Lesson:
- Every template must explicitly import from its flavor
- Prevent silent shadowing by stable flexlibs
- Make it obvious which version is being used

---

## Detecting Unprotected Writes

The MCP can analyze generated scripts for **critical bugs**:

### What to Check For

```python
# UNPROTECTED - Write without permission check
❌ project.LexEntry.SetLexemeForm(entry, value)
❌ entry.LexemeForm = new_value
❌ project.LexSense.SetGloss(sense, gloss)

# PROTECTED - Properly guarded
✓ if modifyAllowed:
✓     project.LexEntry.SetLexemeForm(entry, value)
```

### Common Unprotected Write Patterns

1. **Direct assignment without guard**
   ```python
   project.LexEntry.SetLexemeForm(entry, value)  # ❌ Unprotected
   ```

2. **Method call that modifies**
   ```python
   project.LexSense.SetGloss(sense, "new")  # ❌ Unprotected
   ```

3. **C# property assignment (LibLCM)**
   ```python
   entry.LexemeForm = new_value  # ❌ Unprotected
   ```

4. **Bulk operations without guard**
   ```python
   for entry in entries:
       project.LexEntry.SetLexemeForm(entry, f)  # ❌ Unprotected loop
   ```

### MCP Constraints

The MCP should:
1. **Detect** unprotected writes in generated code
2. **Warn** the user before generating
3. **Refuse** to generate obviously unsafe code
4. **Suggest** how to fix the issue

Example warning:
```
⚠️  WARNING: Generated code contains 3 unprotected writes:
  - Line 45: project.LexEntry.SetLexemeForm() without modifyAllowed check
  - Line 67: sense.Gloss assignment without guard
  - Line 89: Bulk Set operation in unguarded loop

Fix by wrapping writes:
  if modifyAllowed:
      project.LexEntry.SetLexemeForm(entry, value)
```

---

## Feedback Loop

The MCP server learns from patterns:
- `patterns.json` tracks successful methods
- `operations.log` records what users try
- Detects and reports unprotected write attempts
- This guide should evolve as more patterns are discovered

If you discover a new pattern or best practice:
1. Test it in real FLExTools
2. Document it
3. Add to template examples
4. Update this guide

---

## Version Information

- **FlexLibs stable:** v1.2.8 (limited, legacy)
- **Flexicon:** v4.1.0+ (recommended, preferred)
- **LibLCM:** v11.0.0+ (full API, complex)
- **FieldWorks:** 9.0+ for flexicon/LibLCM; 8.x for stable

---

## See Also

- `templates/00-FLAVOR-GUIDE.md` - Flavor comparison and when to use each
- `templates/1-flexlibs-stable-template.py` - Stable flexlibs examples
- `templates/2-flexicon-template.py` - Flexicon examples (RECOMMENDED)
- `templates/3-liblcm-template.py` - LibLCM examples
- `CLAUDE.md` - Overall project guidelines
