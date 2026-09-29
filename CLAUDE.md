# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Configure paths (copy and edit .env)
cp .env.example .env

# Refresh all API indexes from source (generates versioned files)
python -m flextoolsmcp.refresh

# Test the MCP server loads correctly
python -c "from flextoolsmcp.server import APIIndex, get_index_dir; i=APIIndex.load(get_index_dir()); print(f'Loaded {len(i.flexicon.get(\"entities\",{}))} Flexicon entities')"

# Run the MCP server (for Claude Code integration)
flextoolsmcp
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

## MCP Server Tools

Tools are defined in `src/flextoolsmcp/server/tool_definitions.py` and handled in
`src/flextoolsmcp/server/handlers/`. The maintained tool list is
[USAGE.md](USAGE.md#mcp-tools-reference) -- don't copy it here or elsewhere;
`python scripts/validate_integrity.py server` checks USAGE.md against the
definitions, so adding, renaming, or removing a tool means updating USAGE.md.

Tool responses follow a versioned contract. See [`docs/TOOL-CONTRACT.md`](docs/TOOL-CONTRACT.md) for the envelope shape, all error codes, and the deprecation timeline for the nested `error` object (drops at `tool-responses/2.0`).

## Refreshing Indexes

When LibLCM, FlexLibs stable, or Flexicon changes, refresh the indexes:

```bash
# Refresh all indexes (there is no per-library flag anymore)
python -m flextoolsmcp.refresh
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

## Writing FLExTools Modules

Generating, reusing, or reviewing a FLExTools script/module? Load the `flextools-module-authoring`
skill (recipe library first, template, bare-snippet form, when to fetch
`flextools_get_module_template`) and follow [`docs/FLEXTOOLS-STYLE-GUIDE.md`](docs/FLEXTOOLS-STYLE-GUIDE.md).
Always import from `flexicon` explicitly (see Don'ts).

## Context Hygiene

A user-level `read_guard.py` PreToolUse hook blocks unbounded dumps of large
files (>48 KB) and of `user-logs/` in the main thread. Work with it, not
around it:

- **Logs**: never `cat`/`sed`/Read a `user-logs/` session log in the main
  thread. Delegate: `lex-logscan` for triage and issue filing, a
  general-purpose subagent for "what happened in this session?". Grep for a
  signature and read <= 200 lines around the hit only if you need one detail.
- **Large files** (`parse/worker_main.py`, `handlers/parse.py`,
  `parse/runner.py`, `specs/*/spec.md|plan.md|tasks.md`, index JSONs): Grep
  for the symbol or heading, then Read with offset/limit. For "how does X
  work across the parse stack" questions, dispatch an Explore agent and keep
  its summary instead of re-reading the files.
- **Don't re-read** a file already read this session unless it changed.
- **pytest** is already lean; keep it that way:
  `.venv\Scripts\python -m pytest -q -m "not requires_flex" <path> | tail -20`.

## Don'ts:
- This is a Windows system; don't use emojis in console messages.
- Call Python with `python` instead of `python3` (exception: run tests with `.venv\Scripts\python -m pytest` -- see #285).
- Don't run pytest with bare `python` / system Python -- its `mcp` version may fall outside the supported range (`mcp>=1.27.0,<3`), which breaks collection confusingly; the suite fails fast with the fix. Always use `.venv\Scripts\python -m pytest` (or `pip install -r requirements.txt` in that interpreter).
- **Don't omit the flexicon imports** - this causes silent failures with wrong library versions.
- Don't assume FLExTools will inject the right library - be explicit.

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan:
`specs/parser-check-cp2b/plan.md` (parser-check CP2a-bridge + CP2b).

Companions: `specs/parser-check-cp2b/spec.md` (scoping; the authoritative
requirement text is `specs/parser-check-cp2/spec.md`),
`specs/parser-check-cp2b/research.md`, `data-model.md`,
`contracts/tools.md`, `contracts/bridge.md`, `quickstart.md`.
<!-- SPECKIT END -->
