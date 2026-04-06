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
python -c "from src.server import APIIndex, get_index_dir; i=APIIndex.load(get_index_dir()); print(f'Loaded {len(i.flexlibs2.get(\"entities\",{}))} FlexLibs2 entities')"

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
            FlexLibs 2.0 (Python wrappers)
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

Configure paths in `.env` file. These external repositories are dependencies:

| Repository | Purpose | Default Path |
|------------|---------|--------------|
| **FieldWorks** | User-facing GUI for managing lexicons | ../FieldWorks |
| **LibLCM** | C# data model and API for FieldWorks databases | ../liblcm |
| **FlexLibs** (stable) | Shallow IronPython wrapper (~40 functions) | ../flexlibs |
| **FlexLibs 2.0** | Deep IronPython wrapper (~90% coverage) | ../flexlibs2 |
| **FLExTools** | GUI app for running Python macros | ../flextools |

## Project Structure

```
/src
  server.py              # MCP server with 6 tools
  flexlibs2_analyzer.py  # FlexLibs stable + 2.0 Python AST extraction
  liblcm_extractor.py    # LibLCM .NET reflection extraction
  refresh.py             # Unified refresh script

/index
  /liblcm                # LibLCM API documentation (versioned JSON)
    liblcm_api_v8.2.3.json    # Version 8.2.3
    liblcm_api_v8.3.0.json    # Version 8.3.0 (etc.)
  /flexlibs              # FlexLibs API documentation (versioned JSON)
    flexlibs_api_v1.0.0.json      # FlexLibs stable version 1.0.0
    flexlibs2_api_v2.1.5.json     # FlexLibs 2.0 version 2.1.5

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

## Refreshing Indexes

When LibLCM, FlexLibs stable, or FlexLibs 2.0 changes, refresh the indexes:

```bash
# Refresh all
python src/refresh.py

# Refresh only FlexLibs stable
python src/refresh.py --flexlibs-only

# Refresh only FlexLibs 2.0
python src/refresh.py --flexlibs2-only

# Refresh only LibLCM (requires pythonnet and FieldWorks DLLs)
python src/refresh.py --liblcm-only
```

**API Versioning**: Files are now stored with version suffixes (e.g., `flexlibs2_api_v2.1.5.json`).
- Server automatically detects library versions and loads matching API files
- Missing versions are auto-refreshed on startup
- Multiple versions can coexist in the index directory
- See [docs/VERSIONING.md](docs/VERSIONING.md) for complete details

## FLEx Data Conventions

### Empty Multistring Fields ('***' Placeholder)

FLEx/LCM uses `'***'` as a placeholder when multilingual string fields (Definition, Gloss, etc.) have no value set.

**FlexLibs2 v2.0+ automatically converts "***" to ""** in all public methods that return multistring values. This is a breaking change from stable FlexLibs v1.x but provides better UX consistency. See [FlexLibs2 MIGRATION_GUIDE](../flexlibs2/docs/MIGRATION_GUIDE.md) for migration details.

**Affected fields** (in LibLCM / direct C# access): Any property returning `IMultiString` or `IMultiUnicode`:
- `ILexSense.Definition`, `ILexSense.Gloss`
- `ILexEntry.LiteralMeaning`, `ILexEntry.Bibliography`
- Many others...

**FlexLibs2 Operations Methods** - automatically normalize:
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
- **FlexLibs 2.0 preferred**: Better documented (99% descriptions, 82% examples)
- **Static analysis primary**: AST parsing for Python, .NET reflection for C#
- **Semantic categorization**: Entities categorized by namespace and naming patterns
- **Object-centric organization**: Index organized around objects (ILexEntry, ILexSense, etc.)
- **API versioning**: Supports multiple library versions simultaneously via filename suffixes (e.g., `liblcm_api_v8.2.3.json`). Server auto-detects and loads matching versions, auto-refreshing missing ones on startup

## Writing FLExTools Modules

When generating FLExTools scripts for users, **always use this template**:

```python
"""
FLExTools Module: [Brief Description]

Purpose:
    [What this module does and why]

Requires:
    - FlexLibs2 version 2.0+
    - FieldWorks version [X.Y.Z]+

Author: Claude Code
Date: [Date]

Usage:
    Load in FLExTools and run on a FieldWorks project.
"""

# CRITICAL: Explicitly import from flexlibs2
# This prevents FLExTools's default flexlibs (stable version) from shadowing flexlibs2
from flexlibs2 import (
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
        entries = project.LexEntry.GetAll()
        report.Info(f"Processing {len(entries)} entries...")

        for entry in entries:
            # Use flexlibs2 wrapped methods
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

**Silent Failure Risk**: FLExTools loads stable flexlibs first. Without explicit flexlibs2 imports, your code will silently use the wrong (stable) version:

```python
# WRONG - Gets stable flexlibs version
entry = project.LexEntry.GetAll()

# CORRECT - Guarantees flexlibs2 version
from flexlibs2 import LexEntryOperations
entry = project.LexEntry.GetAll()
```

Users won't see an error—the code will "work" but with incorrect behavior/signatures.

### Key Points

1. **Always import from flexlibs2**, never rely on global imports
2. **Include Requires section** - tell users what versions they need
3. **Use flexlibs2 wrapped methods** - they handle edge cases (e.g., "***" multistring normalization)
4. **Catch and report errors** - FLExTools captures exceptions, make them visible via report
5. **Comment non-obvious code** - users will read and maintain this

## Don'ts:
- This is a Windows system; don't use emojis in console messages.
- Call Python with `python` instead of `python3`.
- **Don't omit the flexlibs2 imports** - this causes silent failures with wrong library versions.
- Don't assume FLExTools will inject the right library - be explicit.
