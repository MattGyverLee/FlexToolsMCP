# FlexTools MCP

An MCP server that enables AI assistants to write FlexTools scripts and directly manipulate FieldWorks lexicon data using natural language.
Developed for SIL Global by Matthew Lee with in connection with the SIL's AI Integration Advisory Board and the FLExTrans team.

**TL;DR:** FlexTools MCP gives AI assistants (Claude, Copilot, Gemini) the knowledge to write FLExTools modules by providing indexed, searchable documentation of LibLCM and FlexLibs APIs. It can be used to generate legacy modules (FlexLibs stable), modern modules (FlexLibs 2.0 with ~1,400 functions), or pure LibLCM modules. Beyond code generation, it can execute operations directly on FieldWorks databases using natural language queries like "delete any sense with 'q' in the gloss." Back up your project first - there are no guard-rails.

## What is an MCP Server?

An MCP (Model Context Protocol) server is an "external brain" and toolset that allows AI tools (Claude, GPT, Gemini, etc.) to complete tasks they wouldn't normally have the context or reach to do. Instead of humans calling endpoints, an AI model discovers available tools, understands their schemas, and calls them automatically during conversations to take actions or retrieve information.

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
"Are there any User Approved wordforms with stars (***) in one or more morphemes?"
```

## Background

Since I started working with AI, I dreamed of having an AI tool that could assist with or write "proper" FLExTools modules. The challenge was that the "agent" neeeded to deeply understand the FLEx Model, FLExTools preferences, which Flextools functions existed, and when to fall back to the Fieldworks API (flexlibs). This was too much data to be held in memory for AI work, or for most humans.

Since summer of 2025, I've tried to build a Chipp AI agent for this task by giving it existing documentation and some code, and the results were dismal. It would call functions that didn't exist and required significant handholding to massage the drafts into something workable.

I realized that one barrier to progress was enabling FLExTools (flexlibs) to be access and edit the WHOLE FLEx database (not having to learn and switch between the FLextools and FLEx backends). Christmas of 2025, I set Claude Code on the task of a COMPLETE rewrite of FlexLibs that I'm calling FlexLibs 2.0. Instead of the ~70 functions currently supported in FlexLibs stable, FlexLibs 2.0 provides nearly 1,400 functions covering full CRUD operations for the Lexicon, Grammar, Texts, Words, Lists, Scripture, and Notebook domains. A byproduct of the process was an early abstracted annotated json representation of LibLCM ([flex-api-enhanced.json](index/liblcm/flex-api-enhanced.json)).

In Feb 4th conversations with Larry Hayashi and Jason Naylor, I realized that instead of building an AI Agent with all of the skills (running and looping in-memory, which is very expensive and inefficient), What was needed was an MCP server (an external brain) that could quickly and efficiently look up the needed functions and structure that the AI could piece together. 

The evening of Feb 5th, I started by enriching the shallow annotated code indexes of FlexLib and LibLCM that I had, and then built a new index of FlexLibs 2.0 (which already links the Python and C# functions explicitly). The results are:

- [flexlibs_api.json](index/flexlibs/flexlibs_api.json) - FlexLibs stable (~71 methods)
- [flexlibs2_api.json](index/flexlibs/flexlibs2_api.json) - FlexLibs 2.0 (~1,400 methods)
- [liblcm_api.json](index/liblcm/liblcm_api.json) - LibLCM C# API

The MCP server was built with a host of tools to enable AI assistants to query those abstractions based on natural language input. 

The breakthrough came when Claude Code (using the MCP) could generate at will:
- **Legacy FlexTool Modules** that prefer FlexLibs stable calls with LibLCM fallback
- **Modern FlexTool Modules** that use entirely FlexLibs 2.0 calls
- **Pure LibLCM Modules** that skip FlexLibs entirely and make direct LibLCM calls

Beyond FlexTools module generation, the MCP can alternately run code directly on the database, enabling natural language editing of ANY FLEx data without writing a full module.

My goal was to succesfully write FLExTools, but I accidentally created what Doug hoped to see, a scary-powerful natural-language interface to interact with Fieldworks Data.  

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
```

#### Other MCP-Compatible Tools
Configure the MCP server endpoint according to your tool's documentation.

## MCP Tools

The server exposes 9 tools:

| Tool | Description |
|------|-------------|
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
  server.py              # MCP server with 9 tools
  flexlibs2_analyzer.py  # FlexLibs Python AST extraction
  liblcm_extractor.py    # LibLCM .NET reflection extraction
  refresh.py             # Unified refresh script

/index
  /liblcm                # LibLCM API documentation (JSON)
  /flexlibs              # FlexLibs API documentation (JSON)
    flexlibs_api.json    # FlexLibs stable (~71 methods)
    flexlibs2_api.json   # FlexLibs 2.0 (~1,400 methods)
  navigation_graph.json  # Object relationship graph

/docs
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
