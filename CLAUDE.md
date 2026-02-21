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

FlexTools MCP is an MCP server that enables AI assistants (Claude Code, Copilot, Gemini CLI) to help users write FlexTools scripts for editing FieldWorks lexicons. The server provides indexed, searchable documentation of the LibLCM and FlexLibs APIs with usage examples.

### Architecture Stack
```
User Request -> AI Assistant -> MCP Server -> Indexed Documentation
                    |
            Generated FlexTools Script
                    |
            FLExTools (IronPython)
                    |
            FlexLibs 2.0 (Python wrappers)
                    |
            LibLCM (C# library)
                    |
            FieldWorks Database
```

## Related Repositories

Configure paths in `.env` file. These external repositories are dependencies:

| Repository | Purpose | Default Path |
|------------|---------|--------------|
| **FieldWorks** | User-facing GUI for managing lexicons | D:\Github\Fieldworks |
| **LibLCM** | C# data model and API for FieldWorks databases | D:\Github\liblcm |
| **FlexLibs** (stable) | Shallow IronPython wrapper (~40 functions) | D:\Github\flexlibs |
| **FlexLibs 2.0** | Deep IronPython wrapper (~90% coverage) | D:\Github\flexlibs2 |
| **FlexTools** | GUI app for running Python macros | D:\Github\FlexTools |
| **FLExTools-Generator** | Existing work extracting LibLCM/FlexLibs info (reference) | D:\Github\FLExTools-Generator |

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

FLEx/LCM uses `'***'` as a placeholder when multilingual string fields (Definition, Gloss, etc.) have no value set. This is returned instead of `None` or empty string.

**Affected fields**: Any property returning `IMultiString` or `IMultiUnicode`:
- `ILexSense.Definition`, `ILexSense.Gloss`
- `ILexEntry.LiteralMeaning`, `ILexEntry.Bibliography`
- Many others...

**Helper function available in `run_operation` and `run_module`**:
```python
# Check if a multilingual field is empty (handles '***' placeholder)
if is_empty_multistring(sense.Definition.BestAnalysisAlternative.Text):
    report.Info("Definition is empty")

# Or use the constant directly
if text == FLEX_EMPTY_PLACEHOLDER:  # '***'
    ...
```

## Key Technical Decisions

- **Self-contained extraction**: Can regenerate indexes from source (no external dependencies)
- **FlexLibs 2.0 preferred**: Better documented (99% descriptions, 82% examples)
- **Static analysis primary**: AST parsing for Python, .NET reflection for C#
- **Semantic categorization**: Entities categorized by namespace and naming patterns
- **Object-centric organization**: Index organized around objects (ILexEntry, ILexSense, etc.)
- **API versioning**: Supports multiple library versions simultaneously via filename suffixes (e.g., `liblcm_api_v8.2.3.json`). Server auto-detects and loads matching versions, auto-refreshing missing ones on startup
