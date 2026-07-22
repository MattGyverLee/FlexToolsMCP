# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure paths (copy and edit .env)
cp .env.example .env

# Refresh all API indexes from source (generates versioned files)
python src/refresh.py

# Test the MCP server loads correctly
python -c "from src.server import APIIndex, get_index_dir; i=APIIndex.load(get_index_dir()); print(f'Loaded {len(i.flexicon.get(\"entities\",{}))} Flexicon entities')"

# Run the MCP server (for Claude Code integration)
python src/server.py
```

## Project Overview

FLExTools MCP is an MCP server that enables AI assistants (Claude Code, Copilot, Gemini CLI) to help users write FLExTools scripts for editing FieldWorks lexicons. The server provides indexed, searchable documentation of the LibLCM and FlexLibs APIs with usage examples.

### Architecture Stack
```
User Request -> AI Assistant -> MCP Server -> Indexed Documentation
                    |
            Generated FLExTools Script
                    |
            FLExTools (IronPython)
                    |
            Flexicon (Python wrappers)
                    |
            LibLCM (C# library)
                    |
            FieldWorks Database
```

## Project Philosophy

FLExTools MCP makes FieldWorks automation accessible to non-programmers by:

- **Indexing, not executing**: The MCP doesn't run code. It provides comprehensive, searchable API documentation so Claude can generate correct FLExTools scripts. Intelligence is in the indexing and presentation.

- **Object-centric, not function-centric**: APIs are organized around what users manipulate (ILexEntry, ILexSense, etc.), not library namespaces. Users think "I want to modify entries", not "which library module should I call?"

- **Self-contained extraction**: All documentation is extracted from source via static analysis (AST for Python, reflection for C#). No external APIs. Regenerable and auditable.

- **Semantic understanding**: Uses embeddings to find APIs by intent ("add a gloss to a sense") rather than exact keyword matching.

- **Pattern learning**: Tracks what works and what fails to gradually improve recommendations over time.

- **Version multiplexing**: Supports multiple library versions coexisting, auto-detecting which to use based on project context.

- **Safety-first**: Read-only by default (`write_enabled=False`). Explicit confirmation required for Create/Update/Delete operations.

## Related Repositories

Configure paths in `.env` file. These dependencies are external repositories,
except Flexicon which is a PyPI package (`pip install pyflexicon`, imported as
`flexicon`) and no longer a cloned sibling repo:

| Dependency | Purpose | Source |
|------------|---------|--------------|
| **FieldWorks** | User-facing GUI for managing lexicons | ../FieldWorks |
| **LibLCM** | C# data model and API for FieldWorks databases | ../liblcm |
| **FlexLibs** (stable) | Shallow IronPython wrapper (~40 functions) | ../flexlibs |
| **Flexicon** | Deep Python wrapper (~90% coverage) | `pip install pyflexicon` (import `flexicon`) |
| **FLExTools** | GUI app for running Python macros | ../flextools |

## Project Structure

```
/src
  server.py              # MCP server with 6 tools
  flexicon_analyzer.py   # FlexLibs stable + Flexicon Python AST extraction
  liblcm_extractor.py    # LibLCM .NET reflection extraction
  refresh.py             # Unified refresh script

/index
  /liblcm                # LibLCM API documentation (versioned JSON)
    liblcm_api_v8.2.3.json    # Version 8.2.3
    liblcm_api_v8.3.0.json    # Version 8.3.0 (etc.)
  /flexlibs              # FlexLibs API documentation (versioned JSON)
    flexlibs_api_v1.0.0.json      # FlexLibs stable version 1.0.0
    flexicon_api_v4.1.0.json     # Flexicon version 4.1.0

/docs
  PROGRESS.md            # Project progress log
  TASKS.md               # Task tracking
  DECISIONS.md           # Architecture decisions

.env                     # Configuration (paths to repositories)
.env.example             # Template for .env
```

## MCP Server Tools

The server exposes 6 tools:
- `get_object_api` - Get methods/properties for objects like ILexEntry, LexSenseOperations
- `search_by_capability` - Natural language search with synonym expansion
- `get_navigation_path` - Find paths between object types (ILexEntry -> ILexSense)
- `find_examples` - Get code examples by operation type (create, read, update, delete)
- `list_categories` - List API categories (lexicon, grammar, texts, etc.)
- `list_entities_in_category` - List entities in a category

Tool responses follow a versioned contract. See [`docs/TOOL-CONTRACT.md`](docs/TOOL-CONTRACT.md) for the envelope shape, all 16 error codes, and the deprecation timeline for the nested `error` object (drops at `tool-responses/2.0`).

## Refreshing Indexes

When LibLCM, FlexLibs stable, or Flexicon changes, refresh the indexes:

```bash
# Refresh all indexes (there is no per-library flag anymore)
python src/refresh.py
```

This always scans every available API in one pass. The reverse mapping
annotates LibLCM entities with their FlexLibs/Flexicon wrappers
(`python_wrappers`), and pattern extraction annotates Flexicon
(`common_patterns`) -- scanning one library in isolation would leave the
others' cross-references stale. LibLCM is best-effort: if FieldWorks DLLs /
pythonnet are unavailable, its scan is skipped gracefully and the existing
LibLCM index is kept rather than failing the whole refresh.

**Post-install warmup**: the package also installs a `flextools-mcp-refresh`
console script (entry point for `flextoolsmcp.refresh:main`) so wheels --
which cannot run code at install time -- have a reliable seam to warm the
index right after `pip install`, avoiding the server's first-run lazy-refresh
delay:

```bash
pip install flextools-mcp
flextools-mcp-refresh
```

Run it once on the machine where the MCP server will actually run:
- On a Windows machine with FieldWorks installed (the normal target), this
  warms all three indexes (flexlibs, flexicon, liblcm) to match the
  installed library versions.
- In a headless environment without FieldWorks, it still warms the
  flexlibs + flexicon indexes but leaves the shipped LibLCM index in place
  (LibLCM regeneration requires FieldWorks/pythonnet).

**API Versioning**: Files are now stored with version suffixes (e.g., `flexicon_api_v4.1.0.json`).
- Server automatically detects library versions and loads matching API files
- Missing versions are auto-refreshed on startup
- Multiple versions can coexist in the index directory
- See [docs/VERSIONING.md](docs/VERSIONING.md) for complete details

## FLEx Data Conventions

### Empty Multistring Fields ('***' Placeholder)

FLEx/LCM uses `'***'` as a placeholder when multilingual string fields (Definition, Gloss, etc.) have no value set.

**Flexicon v2.0+ automatically converts "***" to ""** in all public methods that return multistring values. This is a breaking change from stable FlexLibs v1.x but provides better UX consistency. See the Flexicon MIGRATION_GUIDE (bundled with the `pyflexicon` package) for migration details.

**Affected fields** (in LibLCM / direct C# access): Any property returning `IMultiString` or `IMultiUnicode`:
- `ILexSense.Definition`, `ILexSense.Gloss`
- `ILexEntry.LiteralMeaning`, `ILexEntry.Bibliography`
- Many others...

**Flexicon Operations Methods** - automatically normalize:
```python
# These methods return "" for empty, not "***"
gloss = sense.GetGloss()  # Returns "" if empty, not "***"
definition = sense.GetDefinition()  # Returns "" if empty
form = entry.GetLexemeForm()  # Returns "" if empty

# Simple Python-style empty checks work
if not gloss:
    print("Gloss is empty")
```

**Direct C# field access** - still returns "***":
```python
# If you access C# objects directly, you still see "***"
raw_gloss = sense.Gloss.BestAnalysisAlternative.Text  # Returns "***" if empty

# Need explicit check for direct access
if raw_gloss == "***":
    print("Gloss is empty")
```

**Breaking Change Note**: FlexLibs v1.x scripts that check `if gloss == "***":` need to be updated to `if not gloss:` or `if gloss == ""`. See MIGRATION_GUIDE.md.

## Debugging Missing Properties

When users encounter `AttributeError` or "has no attribute" errors:
1. Direct them to use the `resolve_property` tool
2. It will show casting requirements and polymorphic collection warnings
3. Often indicates they need to cast to a concrete interface first (e.g., `InterfaceType(obj)`)
4. For direct C# field access, check if property requires `pythonnet` casting

## Key Technical Decisions

- **Self-contained extraction**: Can regenerate indexes from source (no external dependencies)
- **Flexicon preferred**: Better documented (99% descriptions, 82% examples)
- **Static analysis primary**: AST parsing for Python, .NET reflection for C#
- **Semantic categorization**: Entities categorized by namespace and naming patterns
- **Object-centric organization**: Index organized around objects (ILexEntry, ILexSense, etc.)
- **API versioning**: Supports multiple library versions simultaneously via filename suffixes (e.g., `liblcm_api_v8.2.3.json`). Server auto-detects and loads matching versions, auto-refreshing missing ones on startup

## Writing FLExTools Modules

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

The skeleton-closet workflow (see issue #24) is the planned persistence
path for working snippets; until it lands, fetch the template at save-time.

The MCP still runs a `partial_module_structure` check at run time: code
that defines `Main` but lacks the `docs` dict / `FlexToolsModule` binding
will be refused with a pointer back to `get_module_template`. That's a
safety net for half-converted modules, not an instruction to fetch the
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
    ReversalOperations,
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
            senses = project.LexSense.GetAllSenses(entry)
            for sense in senses:
                gloss = project.LexSense.GetGloss(sense)
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

## Don'ts:
- This is a Windows system; don't use emojis in console messages.
- Call Python with `python` instead of `python3`.
- **Don't omit the flexicon imports** - this causes silent failures with wrong library versions.
- Don't assume FLExTools will inject the right library - be explicit.
