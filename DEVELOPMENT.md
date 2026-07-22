# Development Guide

## Project Structure

```
/src
  server.py              # MCP server with 12 tools
  flexicon_analyzer.py  # FlexLibs Python AST extraction
  liblcm_extractor.py    # LibLCM .NET reflection extraction
  build_casting_index.py # Pythonnet casting requirements generator
  refresh.py             # Unified refresh script

/index
  /liblcm                # LibLCM API documentation (versioned JSON)
    liblcm_api_v11.0.0.json     # LibLCM version 11.0.0
    liblcm_api_v11.0.1.json     # etc.
  /flexlibs              # FlexLibs API documentation (versioned JSON)
    flexlibs_api_v1.2.8.json    # FlexLibs stable v1.2.8
    flexicon_api_v4.0.0.json    # Flexicon v4.0.0
    flexicon_api_v4.1.0.json    # etc.
  /embeddings            # Cached embeddings for semantic search
  navigation_graph.json  # Object relationship graph
  casting_index.json     # Pythonnet interface casting requirements
  common_patterns.json   # Extracted code patterns
  reverse_mapping.json   # Index for reverse lookups

/docs
  WHY-AI.md              # Why use AI for FieldWorks tasks
  WHY-MCP.md             # Why FieldWorks needs an MCP
  BACKGROUND.md          # Project history and motivation
  INNOVATIONS.md         # What makes this MCP unique
  PROGRESS.md            # Project progress log
  TASKS.md               # Task tracking
  DECISIONS.md           # Architecture decisions
  VERSIONING.md          # API versioning strategy
```

## API Versioning

The MCP supports multiple library versions simultaneously:

- API files are stored with version suffixes: `flexicon_api_v4.1.0.json`
- The server auto-detects installed library versions on startup
- Missing versions are automatically refreshed
- This allows users to run on different library versions without conflicts

See [docs/VERSIONING.md](docs/VERSIONING.md) for complete details.

## Refreshing Indexes

Users typically don't need to manually refresh - it happens automatically when versions change. However, developers modifying Flexicon between releases may need manual refreshing.

### Manual Refresh Commands

```bash
# Refresh all indexes (there is no per-library flag anymore)
python src/refresh.py
```

Every run scans all available APIs in one pass -- the reverse mapping
annotates LibLCM entities with their FlexLibs/Flexicon wrappers and pattern
extraction annotates Flexicon, so scanning one library in isolation would
leave the others' cross-references stale. LibLCM is best-effort: if
FieldWorks DLLs/pythonnet are unavailable, its scan is skipped gracefully
and the existing LibLCM index is kept.

As a one-time post-install step, run the `flextools-mcp-refresh` console
script (installed by the package, entry point for
`flextoolsmcp.refresh:main`) on the machine where the MCP server will
actually run, to warm the index and avoid the server's first-run
lazy-refresh delay:

```bash
pip install flextools-mcp
flextools-mcp-refresh
```

- On a Windows machine with FieldWorks installed (the normal target), this
  warms all three indexes (flexlibs, flexicon, liblcm) to match the
  installed library versions.
- In a headless environment without FieldWorks, it still warms the
  flexlibs + flexicon indexes but leaves the shipped LibLCM index in place
  (LibLCM regeneration requires FieldWorks/pythonnet).

### When to Manually Refresh

If you're iterating on Flexicon without changing the version number:

1. Modify the library code
2. Run `python src/refresh.py`
3. Test with the MCP

## Key Technical Decisions

- **Self-contained extraction**: Indexes regenerated from source code
- **Static analysis primary**: Python AST parsing for FlexLibs, .NET reflection for LibLCM
- **Flexicon preferred**: Better documentation coverage (99% descriptions, 82% examples)
- **Semantic categorization**: Entities organized by domain and capability
- **Object-centric organization**: Index organized around LibLCM interfaces (ILexEntry, ILexSense, etc.)
- **API versioning**: Support multiple library versions via filename suffixes

## Dependencies

| Repository | Purpose | How It's Used |
|------------|---------|---------------|
| **FieldWorks** | User-facing GUI (provides LibLCM DLLs) | Required - .NET reflection |
| **LibLCM** | C# data model (2,295 entities) | Required - via FieldWorks |
| **FlexLibs** | Python wrappers stable (~71 methods) | Optional - indexed for legacy modules |
| **Flexicon** (`pyflexicon` on PyPI) | Python wrappers comprehensive (~1,400 methods) | Optional - indexed for modern modules |
| **FLExTools** | GUI for running modules | Optional - reference only |

Python packages (see `requirements.txt`):
- `pythonnet` - Access .NET libraries from Python
- `anthropic` - Claude API integration
- `pydantic` - Data validation

## API Coverage

### LibLCM
- **2,295** C# entities extracted and indexed
- Includes all public interfaces, classes, enumerations
- Generated from .NET reflection of FieldWorks DLLs

### FlexLibs Stable
- **~71** methods documented
- Legacy wrapper around LibLCM
- Used for backward compatibility

### Flexicon
- **~1,400** methods with comprehensive documentation
- 99% description coverage
- 82% code example coverage
- Recommended for new development

## Domains Covered

- **Lexicon**: Entries, senses, definitions, glosses, examples
- **Grammar**: Parts of speech, phonemes, environments, morphological rules
- **Texts**: Interlinear texts, paragraphs, segments, wordforms
- **Words**: Word analyses, glosses, morpheme bundles
- **Lists**: Semantic domains, publications, possibility lists
- **Scripture**: Scripture references and annotations
- **Notebook**: Research notes, people, locations
- **Backend**: Infrastructure and utility classes

## Future Enhancements

- Semantic search using sentence-transformers and FAISS
- Script validation before execution
- Auto-migration tools (FlexLibs stable -> 2.0)
- Integration with FieldWorks CI/CD
- Extended test generation
- Performance optimization for large databases

## Architecture

The MCP sits between AI assistants and FieldWorks data:

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

## Related Documentation

- [WHY-MCP.md](docs/WHY-MCP.md) - Problem statement and motivation
- [WHY-AI.md](docs/WHY-AI.md) - Use cases where AI excels
- [INNOVATIONS.md](docs/INNOVATIONS.md) - Technical innovations
- [DECISIONS.md](docs/DECISIONS.md) - Architecture decisions
- [PROGRESS.md](docs/PROGRESS.md) - Development history

## Contributing

Contributions are welcome! Areas for contribution:

- Adding more code examples to the index
- Testing edge cases in Flexicon
- Improving semantic search
- Performance optimizations
- Documentation improvements

Please submit issues and pull requests on GitHub.
