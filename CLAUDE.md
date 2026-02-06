# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure paths (copy and edit .env)
cp .env.example .env

# Refresh all API indexes from source
python src/refresh.py

# Or refresh individually:
python src/flexlibs2_analyzer.py --flexlibs-path D:/Github/flexlibs --output index/flexlibs/flexlibs_api.json
python src/flexlibs2_analyzer.py --flexlibs2-path D:/Github/flexlibs2 --output index/flexlibs/flexlibs2_api.json
python src/liblcm_extractor.py --output index/liblcm/liblcm_api.json

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
  /liblcm                # LibLCM API documentation (JSON)
  /flexlibs              # FlexLibs stable + 2.0 API documentation (JSON)
    flexlibs_api.json    # FlexLibs stable (~71 methods)
    flexlibs2_api.json   # FlexLibs 2.0 (~1400 methods)

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

## Key Technical Decisions

- **Self-contained extraction**: Can regenerate indexes from source (no external dependencies)
- **FlexLibs 2.0 preferred**: Better documented (99% descriptions, 82% examples)
- **Static analysis primary**: AST parsing for Python, .NET reflection for C#
- **Semantic categorization**: Entities categorized by namespace and naming patterns
- **Object-centric organization**: Index organized around objects (ILexEntry, ILexSense, etc.)
