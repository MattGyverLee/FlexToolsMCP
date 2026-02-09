# FlexTools MCP

An MCP server that enables AI assistants to write FlexTools scripts and directly manipulate FieldWorks lexicon data using natural language.
Developed for SIL Global by Matthew Lee with in connection with the SIL's AI Integration Advisory Board and the FLExTrans team.

**TL;DR:** FlexTools MCP gives AI assistants (Claude, Copilot, Gemini) the knowledge to write FLExTools modules by providing indexed, searchable documentation of LibLCM and FlexLibs APIs. It can be used to generate legacy modules (FlexLibs stable), modern modules (FlexLibs 2.0 with ~1,400 functions), or pure LibLCM modules. Beyond code generation, it can execute operations directly on FieldWorks databases using natural language queries like "delete any sense with 'q' in the gloss." Back up your project first - there are no guard-rails.

## What is an MCP Server?

An MCP (Model Context Protocol) server is an "external brain" and toolset that allows AI tools (Claude, GPT, Gemini, etc.) to complete tasks they wouldn't normally have the context or reach to do. Instead of humans calling endpoints, an AI model discovers available tools, understands their schemas, and calls them automatically during conversations to take actions or retrieve information.

**Why do FieldWorks and FlexTools need one?** See [WHY-MCP.md](docs/WHY-MCP.md) for details on the LibLCM complexity problem, pythonnet casting issues, and why generic AI assistants fail without specialized tooling.

**Why use AI at all when the tools exist?** See [WHY-AI.md](docs/WHY-AI.md) for the learning curve problem, use cases where AI excels, and when manual approaches are still better.

## What Does FlexTools MCP Do?

FlexTools MCP provides AI assistants with:

1. **Indexed API Documentation** - Searchable documentation of LibLCM (C# API), FlexLibs stable (~71 methods), and FlexLibs 2.0 (~1,400 methods)
2. **Code Generation** - use the MCP to generate FlexTools modules in three modes:
   - Legacy modules using FlexLibs stable (falling back to liblcm)
   - Modern modules using FlexLibs 2.0
   - Pure LibLCM modules bypassing FlexLibs entirely
3. **Testing and Debugging** - Test the developed FLExTools Modules (in read only mode) on example projects until you're sure it does what you want.
4. **Run Modules Directly** - Once the tests pass, back up the project and run it live on a project.
3. **Direct Execution** - Discuss and run operations directly on FieldWorks databases without writing full modules
4. **Natural Language Queries** - Ask questions like "delete any sense with the letter 'q' in the gloss" and have it executed

**What makes this different from simple code indexing?** See [INNOVATIONS.md](docs/INNOVATIONS.md) for details on pythonnet casting detection, semantic categorization, navigation graphs, and workflow orchestration.

## Architecture

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

## Key Accomplishments

### API Coverage
- **LibLCM**: 2,295 C# entities extracted and indexed
- **FlexLibs Stable**: ~71 methods documented
- **FlexLibs 2.0**: ~1,400 methods with 99% description coverage and 82% code examples

### Domains Covered
- **Lexicon**: Entries, senses, definitions, glosses, examples
- **Grammar**: Parts of speech, phonemes, environments, morphological rules
- **Texts**: Interlinear texts, paragraphs, segments, wordforms
- **Words**: Word analyses, glosses, morpheme bundles
- **Lists**: Semantic domains, publications, possibility lists
- **Scripture**: Scripture references and annotations
- **Notebook**: Research notes, people, locations
- Plus the back end.

### Working Features
- Generate FlexTools modules from natural language descriptions
- Execute modules in read-only (dry-run) or write mode
- Run ad-hoc operations directly on databases
- Search APIs by capability with synonym expansion
- Navigate object relationships (e.g., ILexEntry -> ILexSense -> ILexExampleSentence)
- Find code examples by operation type (create, read, update, delete)

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

## Background

This project evolved from early AI experiments in summer 2025 through the FlexLibs 2.0 rewrite at Christmas 2025, culminating in the MCP server architecture inspired by conversations with Larry Hayashi and Jason Naylor in February 2025.

**Full story:** [BACKGROUND.md](docs/BACKGROUND.md)

## Installation

### Prerequisites

- Python 3.10+
- FieldWorks 9.x installed (for LibLCM DLLs) and projects.
- One or more of:
  - [FlexLibs](https://github.com/cdfarrow/flexlibs) (stable, ~71 functions)
  - [FlexLibs 2.0](https://github.com/your-repo/flexlibs2) (comprehensive, ~1,400 methods)

### Recommended
- Context7 MCP for improving and modernizing generated Python and C# code.
- Fieldworks and FLExTools repositories for examples of real-life code. 

### Setup

1. Clone the repository:
   ```bash
   git clone https://github.com/MattGyverLee/FlexToolsMCP.git
   cd FlexToolsMCP
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Configure paths:
   ```bash
   cp .env.example .env
   # Edit .env with your local paths
   ```

4. Refresh indexes (if needed):
   ```bash
   python src/refresh.py
   ```

5. Test the server loads correctly:
   ```bash
   python -c "from src.server import APIIndex, get_index_dir; i=APIIndex.load(get_index_dir()); print(f'Loaded {len(i.flexlibs2.get(\"entities\",{}))} FlexLibs2 entities')"
   ```

### Connecting to AI Assistants

#### Claude Code
```bash
# User-wide installation (available in all projects)
claude mcp add flextools-mcp -s user python D:/Github/FlexToolsMCP/src/server.py

# Or project-specific (from the FlexToolsMCP directory)
claude mcp add flextools-mcp python src/server.py

# List configured MCP servers
claude mcp list

# Remove from user scope
claude mcp remove flextools-mcp -s user

# Remove from project scope
claude mcp remove flextools-mcp -s project

# Remove from all scopes
claude mcp remove flextools-mcp -s user && claude mcp remove flextools-mcp -s project
```

#### Other MCP-Compatible Tools
Configure the MCP server endpoint according to your tool's documentation.

## MCP Tools

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
    |   - Gets code examples    |
    |   - Returns action plan   |  -> Complete plan with code skeleton
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

### Pythonnet Casting Warning

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

## API Modes

The server supports three API modes for different use cases:

| Mode | Description | Use Case |
|------|-------------|----------|
| `flexlibs2` | FlexLibs 2.0 (~1,400 methods) | Recommended for new development |
| `flexlibs_stable` | FlexLibs stable with LibLCM fallback | Legacy compatibility |
| `liblcm` | Pure LibLCM C# API | Maximum flexibility |

## Project Structure

```
/src
  server.py              # MCP server with 12 tools
  flexlibs2_analyzer.py  # FlexLibs Python AST extraction
  liblcm_extractor.py    # LibLCM .NET reflection extraction
  build_casting_index.py # Pythonnet casting requirements generator
  refresh.py             # Unified refresh script

/index
  /liblcm                # LibLCM API documentation (JSON)
  /flexlibs              # FlexLibs API documentation (JSON)
    flexlibs_api.json    # FlexLibs stable (~71 methods)
    flexlibs2_api.json   # FlexLibs 2.0 (~1,400 methods)
  navigation_graph.json  # Object relationship graph
  casting_index.json     # Pythonnet interface casting requirements

/docs
  WHY-AI.md              # Why use AI for FieldWorks tasks
  WHY-MCP.md             # Why FieldWorks needs an MCP
  BACKGROUND.md          # Project history and motivation
  INNOVATIONS.md         # What makes this MCP unique
  PROGRESS.md            # Project progress log
  TASKS.md               # Task tracking
  DECISIONS.md           # Architecture decisions
```

## Important Warnings

### Data Safety
- **Always backup your FieldWorks project before running write operations**
- The MCP defaults to read-only (dry-run) mode for safety
- Set `write_enabled=True` only after testing thoroughly
- There are no guard-rails - you can delete important data

### Known Limitations
- Cannot control the FLEx GUI interface (e.g., set filters)
- Only manipulates data, not UI state
- FlexLibs 2.0 may contain bugs - further testing needed
- Some edge cases in the Scripture module were recently fixed

### Reproducibility
Results should be reproducible on other machines if they:
1. Download this repo and dependencies
2. Have FlexLibs and/or FlexLibs 2.0 installed
3. Have LibLCM libraries available (via FieldWorks installation)
4. Connect the MCP to Claude Code, Copilot, Gemini CLI, etc.

## Refreshing Indexes

When the source libraries change, refresh the indexes:

```bash
# Refresh all indexes
python src/refresh.py

# Refresh only FlexLibs stable
python src/refresh.py --flexlibs-only

# Refresh only FlexLibs 2.0
python src/refresh.py --flexlibs2-only

# Refresh only LibLCM (requires pythonnet and FieldWorks DLLs)
python src/refresh.py --liblcm-only
```

## Dependencies

| Repository | Purpose | Required |
|------------|---------|----------|
| **FieldWorks** | GUI application (provides DLLs) | Yes |
| **LibLCM** | C# data model | Yes (via FieldWorks) |
| **FlexLibs** | Python wrappers (stable) | Optional |
| **FlexLibs 2.0** | Python wrappers (comprehensive) | Recommended |
| **FlexTools** | GUI for running modules | Optional |

## Technical Decisions

- **Self-contained extraction**: Indexes regenerated from source code
- **Static analysis primary**: Python AST parsing, .NET reflection
- **FlexLibs 2.0 preferred**: Better documentation coverage
- **Semantic categorization**: Entities organized by domain
- **Object-centric organization**: Indexed around LibLCM interfaces

## Future Enhancements

- Semantic search using sentence-transformers and FAISS
- Script validation before execution
- Auto-migration tools (FlexLibs stable -> 2.0)
- Integration with FieldWorks CI/CD
- Extended test generation

## Acknowledgements

This project only happend because I can stand on the shoulders of giants.
- The Fieldworks developers, with a special shoutout to Jason, Ken, and Hasso. 
- Craig, the developer of FLExTools and flexlibs.
- The AIIAG (AI Implementation Advisory Group) who I work with to develop and test ideas like this.
- Ron, Beth and the FLExTrans team, who push FLExTools to and beyond its limits.
- My mentors and supervisors in LangTech (Doug, Jeff, and Jenni). Though my intention was \[only\] to create a FLExTools generator, Doug could see before me that the future might be to bypass modules directly and ask the AI to do direct work.   

## License

MIT License

Copyright (c) 2025

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

## Contributing

Contributions are welcome! Please feel free to submit issues and pull requests.

## Acknowledgments

- The FieldWorks and FlexTools teams for creating the underlying tools
- The FlexLibs maintainers for the Python wrappers
