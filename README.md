# FlexTools MCP

An MCP server that enables AI assistants to write FlexTools scripts and directly manipulate FieldWorks lexicon data using natural language.

Developed for SIL Global by Matthew Lee in connection with the SIL's AI Integration Advisory Board and the FLExTrans team.

## Quick Overview

**What it does:** FlexTools MCP gives AI assistants (Claude, Copilot, Gemini) the knowledge to write FLExTools modules by providing indexed, searchable documentation of LibLCM and FlexLibs APIs.

**Three ways to use it:**
1. Generate legacy modules (FlexLibs stable)
2. Generate modern modules (FlexLibs 2.0 with ~1,400 functions)
3. Run operations directly on FieldWorks databases using natural language queries

**Example:** "Delete any sense with 'q' in the gloss" → AI generates, tests, and runs the operation automatically.

⚠️ **Warning:** Backup your project first - there are no guard-rails.

## Why MCP? Why AI?

- **What is an MCP Server?** See [WHY-MCP.md](docs/WHY-MCP.md) - explains the LibLCM complexity problem and why generic AI assistants fail
- **When is AI useful?** See [WHY-AI.md](docs/WHY-AI.md) - learning curve problems and when manual approaches are better

## Getting Started

### 1. Installation
See [SETUP.md](SETUP.md) for detailed installation steps.

**Quick summary:**
```bash
git clone https://github.com/MattGyverLee/FlexToolsMCP.git
cd FlexToolsMCP
pip install -r requirements.txt

# Install FlexLibs 2.0
cd ..
git clone https://github.com/MattGyverLee/flexlibs.git flexlibs2
pip install ./flexlibs2

# Test it works
cd FlexToolsMCP
python -c "from src.server import APIIndex, get_index_dir; i=APIIndex.load(get_index_dir()); print(f'Loaded {len(i.flexlibs2.get(\"entities\",{}))} FlexLibs2 entities')"
```

### 2. Connect to Your AI Assistant
See [SETUP.md](SETUP.md#connecting-to-ai-assistants) for Claude Code, Antigravity, and other tools.

**Note:** Each AI tool has different MCP configuration syntax. See SETUP.md for your specific tool.

### 3. Start Using
See [USAGE.md](USAGE.md) for workflows, tool reference, and examples.

## What's Included

### MCP Tools (12)
- `start` - Unified workflow orchestrator
- `search_by_capability` - Find APIs by what you want to do
- `get_object_api` - Get methods/properties for LibLCM objects
- `get_navigation_path` - Traverse between object types
- `find_examples` - Find code examples by operation type
- `run_module` / `run_operation` - Execute code with dry-run and write modes
- Plus 6 more discovery and templating tools

### API Coverage
- **LibLCM**: 2,295 C# entities
- **FlexLibs Stable**: ~71 methods
- **FlexLibs 2.0**: ~1,400 methods (99% documented, 82% with examples)

### Test-Proven Examples
```
"Remove 'el ' from the beginning of any Spanish gloss"
"Add an environment named 'pre-y' with the context '/_y'"
"Delete the entry with lexeme ɛʃːɛr"
"List entries with "ː" in the headword"
"Are there any duplicates by gloss (fuzzy match) and POS?"
```

## Key Features

- **Automatic index refresh** when you update FieldWorks or libraries
- **Dry-run mode** to test before writing data
- **Semantic search** with synonym expansion
- **Pythonnet casting detection** - warns when you need type conversions
- **Code examples** extracted from real-world usage
- **Multiple library versions** supported simultaneously

## Documentation

| Document | Purpose |
|----------|---------|
| [SETUP.md](SETUP.md) | Installation and AI tool configuration |
| [USAGE.md](USAGE.md) | How to use the MCP, workflows, examples |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Project structure, architecture, contributing |
| [docs/WHY-MCP.md](docs/WHY-MCP.md) | Why FieldWorks needs MCP servers |
| [docs/WHY-AI.md](docs/WHY-AI.md) | When AI is useful for FieldWorks work |
| [docs/INNOVATIONS.md](docs/INNOVATIONS.md) | Technical innovations in this MCP |
| [docs/BACKGROUND.md](docs/BACKGROUND.md) | Project history |

## Safety & Limitations

### Safety
- **Always backup before write operations** - the MCP defaults to dry-run mode
- Dry run shows what would happen before writing
- Requires explicit user permission for write operations

### Limitations
- Cannot control the FLEx GUI (filters, display, etc.)
- Only manipulates data, not UI state
- FlexLibs 2.0 still undergoing extensive testing
- Some Scripture module edge cases recently fixed

## Architecture

```
User Request -> AI Assistant -> MCP Server -> Indexed APIs
                    |
            Generated FlexTools Script or Direct Execution
                    |
            FLExTools (IronPython) or FlexLibs 2.0
                    |
            LibLCM (C# data model)
                    |
            FieldWorks Database
```

For technical details, see [DEVELOPMENT.md](DEVELOPMENT.md#architecture).

## License

MIT License - See LICENSE file for details

## Contributing

Contributions are welcome! Please submit issues and pull requests on GitHub.

For development info, see [DEVELOPMENT.md](DEVELOPMENT.md).

## Acknowledgments

- The FieldWorks developers (Jason, Ken, Hasso, and team)
- Craig, the developer of FLExTools and FlexLibs
- The SIL AI Implementation Advisory Board
- Ron, Beth and the FLExTrans team
- My mentors Doug, Jeff, and Jenni at SIL LangTech
