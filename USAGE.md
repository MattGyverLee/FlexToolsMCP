# Usage Guide

## Overview

This guide covers how to use FlexTools MCP to generate and run FLExTools modules, execute operations directly on FieldWorks databases, and understand the recommended workflow.

## MCP Tools Reference

The server exposes 12 tools:

| Tool | Description |
|------|-------------|
| `start` | **BEGIN HERE** - Unified entry point that orchestrates the discovery workflow |
| `get_object_api` | Get methods/properties for objects like ILexEntry, LexSenseOperations |
| `search_by_capability` | Natural language search with synonym expansion |
| `get_navigation_path` | Find paths between object types (ILexEntry -> ILexSense) |
| `find_examples` | Get code examples by operation type (create, read, update, delete) |
| `list_categories` | List API categories (lexicon, grammar, texts, etc.) |
| `list_entities_in_category` | List entities in a category |
| `get_module_template` | Get the official FlexTools module template |
| `start_module` | Interactive wizard to create a new FlexTools module |
| `run_module` | Execute a FlexTools module against a FieldWorks project |
| `run_operation` | Execute FlexLibs2 operations directly without module boilerplate |
| `resolve_property` | Resolve property names and get pythonnet casting requirements |

## API Modes

The server supports three API modes for different use cases:

| Mode | Description | Use Case |
|------|-------------|----------|
| `flexlibs2` | FlexLibs 2.0 (~1,400 methods) | Recommended for new development |
| `flexlibs_stable` | FlexLibs stable with LibLCM fallback | Legacy compatibility |
| `liblcm` | Pure LibLCM C# API | Maximum flexibility |

## Recommended Workflow

**IMPORTANT:** Follow this workflow to avoid common pitfalls. Skipping directly to `run_operation` or `run_module` often leads to errors, incorrect code, or data corruption.

### Quick Start: Use `start`

The easiest way is to use the unified `start` tool, which orchestrates the entire discovery workflow automatically:

```
User Query: "I want to delete senses with 'test' in the gloss"
                    |
                    v
    +---------------------------+
    |         start             |  task="delete senses with test in gloss"
    |   - Analyzes your task    |  output_type="operation" or "module"
    |   - Finds relevant APIs   |  flavor="flexlibs2"
    |   - Checks casting needs  |
    |   - Gets code examples    |  -> Complete plan with code skeleton
    |   - Returns action plan   |
    +---------------------------+
                    |
                    v
    +---------------------------+
    |   run_operation/module    |  write_enabled=FALSE (dry run)
    +---------------------------+
                    |
            Review output
                    |
                    v
    +---------------------------+
    |   run with write access   |  write_enabled=TRUE
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

#### Phase 4: Testing (Required before write)

```
    +---------------------------+
    | 9. run_operation/module   |  write_enabled=FALSE (default)
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

# RIGHT - Use FlexLibs2 casting helper
from flexlibs2.code.lcm_casting import get_pos_from_msa
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
- Update FlexLibs 2.0

The server detects version changes on startup and refreshes missing or outdated indexes automatically.

**Only manual refresh is needed if:** You're a developer modifying FlexLibs 2.0 between releases without incrementing the version number. See [DEVELOPMENT.md](DEVELOPMENT.md) for manual refresh commands.

## Known Limitations

- Cannot control the FLEx GUI interface (e.g., set filters)
- Only manipulates data, not UI state
- FlexLibs 2.0 may contain bugs - further testing needed
- Some edge cases in the Scripture module were recently fixed

## Next Steps

- See [SETUP.md](SETUP.md) if you haven't installed yet
- See [DEVELOPMENT.md](DEVELOPMENT.md) if you want to contribute or extend the MCP
