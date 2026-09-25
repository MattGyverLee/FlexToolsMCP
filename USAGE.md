# Usage Guide

## Overview

This guide covers how to use FLExTools MCP to generate and run FLExTools modules, execute operations directly on FieldWorks databases, and understand the recommended workflow.

## MCP Tools Reference

This is the one maintained list of the server's tools. The definitions live in
[`src/flextoolsmcp/server/tool_definitions.py`](src/flextoolsmcp/server/tool_definitions.py);
`python scripts/validate_integrity.py server` fails when this list and that file
disagree. AI clients read the full tool descriptions and schemas from the running
server itself. Response shapes and error codes are in
[docs/TOOL-CONTRACT.md](docs/TOOL-CONTRACT.md).

### Session & Configuration

| Tool | Description |
|------|-------------|
| `flextools_start` | **BEGIN HERE** - Initialize the session: project, API mode, and workflow guidance |
| `flextools_list_projects` | List FieldWorks projects available on this machine |
| `flextools_manage_config` | Get, set, delete, or list persistent configuration (dotted keys like `paths.flexicon`) |
| `flextools_get_session_history` | View this session's operation history |

### Discovery & Analysis

| Tool | Description |
|------|-------------|
| `flextools_search_by_capability` | Natural-language search for methods by what they do; surfaces matching skeletons from prior successful runs |
| `flextools_get_object_api` | Full methods/properties for an object such as ILexEntry or LexSenseOperations |
| `flextools_get_navigation_path` | Traversal paths between object types (ILexEntry -> ILexSense -> ILexExampleSentence) |
| `flextools_find_examples` | Code examples by method or operation type (create, read, update, delete, iterate) |
| `flextools_resolve_property` | Resolve property names and detect pythonnet casting requirements |
| `flextools_resolve_type` | Resolve a type name to its namespace, assembly, and import statement |
| `flextools_get_wrapper_dependencies` | LibLCM internals (factories, repositories, properties) a flexlibs/flexicon wrapper uses |
| `flextools_find_wrappers_for_lcm` | Which wrapper methods cover a given LibLCM symbol |

### Catalog & Browsing

| Tool | Description |
|------|-------------|
| `flextools_list_categories` | List API categories (lexicon, grammar, texts, wordform, reversal, etc.) |
| `flextools_list_entities_in_category` | List the entities in a category with summaries |
| `flextools_list_skeletons` | List captured "skeleton" helpers that survived prior sessions |

### Module Creation & Execution

| Tool | Description |
|------|-------------|
| `flextools_get_module_template` | The official FlexTools module scaffold (Main / docs / FlexToolsModule) |
| `flextools_start_module` | Interactive wizard to scaffold a new FlexTools module |
| `flextools_run_module` | Execute code against a FieldWorks project (dry-run by default; `write_enabled=true` for mutations) |
| `flextools_get_operation_logs` | Operation logs plus pattern-based recommendations for common errors |

### Diagnostics

| Tool | Description |
|------|-------------|
| `flextools_health` | Composed health/version snapshot -- call when something seems wrong |
| `flextools_prepare_report` | Prepare a diagnostic report for the maintainer ("send this to the maintainer") |
| `flextools_grammar_health` | Static scan of the grammar for path-multiplying properties |

### Parser Check

| Tool | Description |
|------|-------------|
| `flextools_try_word` | Does this word parse, and if not, why not? |
| `flextools_parse_text` | Batch-parse a corpus scope |
| `flextools_parse_status` | Poll a parse run by its handle: stage, progress, result, or failure |
| `flextools_parse_log` | Read one section of a parse run's record back from disk |
| `flextools_parse_diff` | Compare two batch runs word by word -- did a grammar edit help? |
| `flextools_parse_cancel` | Cancel a parse run by its handle -- it stops at the next word boundary |
| `flextools_parse_release` | Release this server's own idle parse worker(s) for a project, dropping the fwdata lock |
| `flextools_parse_sandbox` | Parse on an exported copy of the grammar with the stand-alone `hc` tool -- never touches the live project; rehearse speculative grammar edits in named sandboxes and re-run saved corpora |

## API Modes

The server supports three API modes for different use cases:

| Mode | Description | Use Case |
|------|-------------|----------|
| `flexicon` | Flexicon (~1,400 methods) | Recommended for new development |
| `flexlibs_stable` | FlexLibs stable with LibLCM fallback | Legacy compatibility |
| `liblcm` | Pure LibLCM C# API | Maximum flexibility |

**Note:** `flexicon` is the canonical `api_mode` value. The former `flexicon` value is still accepted as a deprecated alias.

## Recommended Workflow

**IMPORTANT:** Follow this workflow to avoid common pitfalls. Skipping discovery and going straight to `run_module` often leads to errors, incorrect code, or data corruption.

### Quick Start: Use `start`

The easiest way is to use the unified `start` tool, which orchestrates the entire discovery workflow automatically:

```
User Query: "I want to delete senses with 'test' in the gloss"
                    |
                    v
    +---------------------------+
    |     flextools_start       |  task="delete senses with test in gloss"
    |   - Analyzes your task    |  api_mode="flexicon"
    |   - Finds relevant APIs   |
    |   - Checks casting needs  |
    |   - Gets code examples    |  -> Complete plan with code skeleton
    |   - Returns action plan   |
    +---------------------------+
                    |
                    v
    +---------------------------+
    |   flextools_run_module    |  write_enabled=FALSE (dry run)
    +---------------------------+
                    |
            Review output
                    |
                    v
    +---------------------------+
    |   flextools_run_module    |  write_enabled=TRUE
    |       BACKUP FIRST!       |
    +---------------------------+
```

### Manual Workflow (For Reference)

If you prefer to run individual tools or need more control, here's the detailed workflow:

#### Phase 1: Discovery (Required)

```
User Query: "I want to delete senses with 'test' in the gloss"
                    |
                    v
    +---------------------------+
    | 1. search_by_capability   |  "delete sense gloss"
    |    - Find relevant APIs   |  -> LexSenseOperations.Delete, GetGloss
    +---------------------------+
                    |
                    v
    +---------------------------+
    | 2. get_navigation_path    |  ILexEntry -> ILexSense
    |    - How to traverse      |  -> entry.SensesOS
    +---------------------------+
```

#### Phase 2: Understanding (Required)

```
    +---------------------------+
    | 3. get_object_api         |  LexSenseOperations
    |    - Full API details     |  -> Delete(), GetGloss(), GetAll()
    +---------------------------+
                    |
                    v
    +---------------------------+
    | 4. resolve_property       |  "PartOfSpeechRA"
    |    - Property names       |  -> CASTING WARNING: Not on IMoMorphSynAnalysis!
    |    - Casting requirements |  -> Use get_pos_from_msa() helper
    +---------------------------+
                    |
                    v
    +---------------------------+
    | 5. find_examples          |  operation_type="delete"
    |    - Code patterns        |  -> Example delete code
    +---------------------------+
```

#### Phase 3: Implementation

```
    +---------------------------+
    | 6. context7 (if available)|  Get latest Python/API docs
    +---------------------------+
                    |
                    v
    +---------------------------+
    | 7. get_module_template    |  (if building a module)
    |    - Boilerplate code     |
    +---------------------------+
                    |
                    v
    +---------------------------+
    | 8. Write the code         |  Using discovered APIs
    +---------------------------+
```

**Building blocks, not invention.** Step 8 is assembly, not creative writing. By the time you reach it, the previous phases have produced the concrete artifacts that drop directly into the module:

- **From `start`** — runtime conventions: `report.*` calls, `project.BuildGotoURL`, the `if modifyAllowed:` guard, `'***'` empty-field normalization, pre-injected helpers.
- **From `get_module_template`** — the skeleton: `docs` dict, `Main(project, report, modifyAllowed)`, `FlexToolsModule` binding, the auto-injected write-guard.
- **From `get_object_api`** — the verbatim `import_statement` plus exact method signatures, parameter names, and return types.
- **From `get_navigation_path`** — a code skeleton for entity-to-entity traversal with null-safety and casts already in place.
- **From `find_examples`** — real CRUD snippets that anchor call shape (argument order, paired calls, surrounding loop structure).
- **From `resolve_property` / `find_wrappers_for_lcm`** — casting fixes and explicit `gaps[]` advisories that decide whether to stay in flexicon or drop to liblcm.

Every method name in the finished module traces back to a discovery step you can audit. If a needed call wasn't surfaced by Phases 1–2, return to discovery rather than guess — `run_module` refuses execution when no APIs were discovered (gate 6, `api_discovery_required`).

#### Phase 4: Testing (Required before write)

```
    +---------------------------+
    | 9. flextools_run_module   |  write_enabled=FALSE (default)
    |    - DRY RUN FIRST        |  -> See what WOULD happen
    +---------------------------+
                    |
          Review output
                    |
          Fix any issues
                    |
                    v
    +---------------------------+
    | 10. run with write access |  write_enabled=TRUE
    |     - BACKUP FIRST!       |  -> User permission required
    +---------------------------+
```

### Why This Workflow Matters

| Skipping Step | What Goes Wrong |
|---------------|-----------------|
| search_by_capability | Using wrong or non-existent functions |
| get_navigation_path | Can't traverse from entries to senses |
| resolve_property | pythonnet casting errors at runtime |
| find_examples | Reinventing patterns that already exist |
| Dry run | Data corruption, unintended deletions |

## Example Natural Language Queries

These queries have been successfully tested:

```
"Remove "el " from the beginning of any Spanish gloss."
"Add an environment named 'pre-y' with the context '/_y'."
"Give me a report of each part of speech with a count of lexemes under it. Skip POS's with 0 entries."
"Delete the entry with a lexeme of ɛʃːɛr"
"List entries with "ː" in the headword."
"List the first two texts with the word "not" in the baseline and show the context."
"Show me the full morpheme analysis of the first word in the the first text."
"Regarding both glosses (fuzzy match) and part of speech, are there any likely synonyms in this database?"
"Propose glosses in French for 3 senses with examples sentence translations that confirm the context."
"Are there any User Approved Analyses with one or more unlinked morphemes?"
"I need a module that will fuzzily identify duplicate lexemes (levenshtein) with similar glosses (semantically) and the same POS."
```

## Pythonnet Casting Warning

When working with collections like `MorphoSyntaxAnalysesOC`, objects are returned as base interface types. Use `resolve_property` to check if casting is needed:

```python
# WRONG - PartOfSpeechRA not visible on base type
for msa in entry.MorphoSyntaxAnalysesOC:
    pos = msa.PartOfSpeechRA  # AttributeError!

# RIGHT - Use Flexicon casting helper
from flexicon.code.lcm_casting import get_pos_from_msa
for msa in entry.MorphoSyntaxAnalysesOC:
    pos = get_pos_from_msa(msa)  # Works!
```

## Data Safety

- **Always backup your FieldWorks project before running write operations**
- The MCP defaults to read-only (dry-run) mode for safety
- Set `write_enabled=True` only after testing thoroughly
- There are no guard-rails - you can delete important data

## Automatic Index Refreshing

Indexes refresh automatically when you:
- Update FieldWorks (LibLCM version may change)
- Update FlexLibs
- Update Flexicon

The server detects version changes on startup and refreshes missing or outdated indexes automatically.

**Only manual refresh is needed if:** You're a developer modifying Flexicon between releases without incrementing the version number. See [DEVELOPMENT.md](DEVELOPMENT.md) for manual refresh commands.

## Known Limitations

- Cannot control the FLEx GUI interface (e.g., set filters)
- Only manipulates data, not UI state
- Flexicon may contain bugs - further testing needed
- Some edge cases in the Scripture module were recently fixed

## Next Steps

- See [SETUP.md](SETUP.md) if you haven't installed yet
- See [DEVELOPMENT.md](DEVELOPMENT.md) if you want to contribute or extend the MCP
