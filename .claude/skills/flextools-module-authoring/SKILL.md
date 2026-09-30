---
name: flextools-module-authoring
description: How to write FLExTools modules and bare run_module snippets with Flexicon -- check the recipe library first (flextools_list_recipes, PARAMS block, promote), when to fetch the module template, the lightweight no-Main form, the canonical Flexicon template, and the silent-wrong-library pitfall. Use when generating, reusing, or reviewing a FLExTools script/module for a user.
---

# Writing FLExTools Modules

**READ FIRST:** See [`docs/FLEXTOOLS-STYLE-GUIDE.md`](docs/FLEXTOOLS-STYLE-GUIDE.md) for comprehensive best practices that should guide all script generation.

### When to fetch the template (advisory)

`run_module` accepts both bare snippets and full FlexTools modules. Bare
snippets are the right primitive for exploration -- short, low-ceremony,
written and executed in seconds. Don't paper them over with module
boilerplate before they've earned it.

**Use `flextools_get_module_template(flavor='flexicon')` when graduating
a snippet into a reusable, named module** -- i.e., the user wants to keep
the code, run it from FlexTools' GUI, or share it. Cues that you're at the
graduation step: "save this", "make it a module", "deploy", or the user
gives the artifact a name.

### Recipes workflow (reusable scripts)

Before composing code from scratch, check `recipes` in
`flextools_search_by_capability`, or call `flextools_list_recipes` to
browse (filter by `query`, `source`, `requires_write`; fetch full code
with `recipe_id`). To reuse a recipe, edit only the values inside the
`# --- PARAMS ---` / `# --- END PARAMS ---` block and run with
`source="existing"` when nothing outside PARAMS changed. Write recipes
(`requires_write: true`) need a dry run first (`modifyAllowed=False`),
then `write_enabled` plus confirmation. Pass `user_intent` to
`run_module` so a successful run (whole code, at least 4 non-blank,
non-comment lines) is remembered as one local recipe in
`~/.flextoolsmcp/recipes.jsonl` (fingerprinted; repeats bump
`use_count`). Promote with `flextools-mcp-recipe promote <local-id>
--id <new-id>` plus human review -- drafts go to
`~/.flextoolsmcp/recipe-drafts/`, never straight into the package.

The MCP still runs a `partial_module_structure` check at run time, but
only for half-modules: code that defines `Main` and has exactly one of the
`docs` dict / `FlexToolsModule` binding is refused, with the missing piece
in `suggested_scaffold` (or pass `skip_module_check=True`). Code with
`def Main` and neither piece runs as a snippet; the response carries a
`[module scaffold]` warning with the scaffold to paste if you want to save
it as a module file (#303). Neither case is an instruction to fetch the
template before every snippet.

### Lightweight op form (no `Main`)

For exploratory probes that won't be saved, write bare code. The runner pre-injects `project`, `report`, `write_enabled`, and `modifyAllowed` into the namespace, so the same `if modifyAllowed:` guard pattern still applies:

```python
# Bare snippet - no Main, no docs, no FlexToolsModule.
for entry in project.LexEntry.GetAll():
    headword = project.LexEntry.GetLexemeForm(entry)
    if modifyAllowed:
        # mutation goes here, guarded
        pass
    report.Info(headword, project.BuildGotoURL(entry))
```

### Preferred: Flexicon

When generating FLExTools scripts for users, **always use flexicon** template:
- Better documented (99% descriptions, 82% examples)
- 90% API coverage (stable flexlibs only ~40 functions)
- Handles edge cases (multistring normalization, descriptor protocol)
- Actively maintained

**Always use this template**:

```python
"""
FLExTools Module: [Brief Description]

Purpose:
    [What this module does and why]

Requires:
    - Flexicon version 2.0+
    - FieldWorks version [X.Y.Z]+

Author: Claude Code
Date: [Date]

Usage:
    Load in FLExTools and run on a FieldWorks project.
"""

# CRITICAL: Explicitly import from flexicon (pip install pyflexicon)
# Don't rely on FLExTools's default flexlibs (stable version) -- import the
# Flexicon API surface by name so you get the deep wrapper, not the shallow one.
from flexicon import (
    FLExProject,
    LexEntryOperations,
    LexSenseOperations,
    ReversalIndexOperations,
    # Add other operations as needed
)

def Main(project, report, modify):
    """
    Standard FLExTools entry point.

    Args:
        project: FLExProject instance (FieldWorks database connection)
        report: Report object for logging output
        modify: Boolean - whether modifications are enabled
    """
    try:
        # Your implementation here
        # GetAll() returns a behavioral collection -- safe to loop, len(),
        # index/slice, or re-iterate freely. Only wrap in list(...) if you
        # specifically need a plain list.
        entries = project.LexEntry.GetAll()
        report.Info(f"Processing {len(entries)} entries...")

        for entry in entries:
            # Use flexicon wrapped methods
            senses = project.LexEntry.GetAllSenses(entry)
            for sense in senses:
                gloss = project.Senses.GetGloss(sense)
                report.Info(f"  {gloss}")

        report.Info("Complete!")

    except Exception as e:
        report.Error(f"Error: {e}")
        import traceback
        report.Error(traceback.format_exc())
```

### Why This Matters

**Silent Failure Risk**: FLExTools loads stable flexlibs first. Without explicit flexicon imports, your code will silently use the wrong (stable) version:

```python
# WRONG - Gets stable flexlibs version
entry = project.LexEntry.GetAll()

# CORRECT - Guarantees flexicon version
from flexicon import LexEntryOperations
entry = project.LexEntry.GetAll()
```

Users won't see an error—the code will "work" but with incorrect behavior/signatures.

### Key Points

1. **Always import from flexicon**, never rely on global imports
2. **Include Requires section** - tell users what versions they need
3. **Use flexicon wrapped methods** - they handle edge cases (e.g., "***" multistring normalization)
4. **Catch and report errors** - FLExTools captures exceptions, make them visible via report
5. **Comment non-obvious code** - users will read and maintain this
