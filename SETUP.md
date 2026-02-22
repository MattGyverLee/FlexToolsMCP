# Setup & Installation

## Prerequisites

- Python 3.10+
- FieldWorks 9.x installed (for LibLCM DLLs)
- One or more of:
  - [FlexLibs](https://github.com/cdfarrow/flexlibs) (stable, ~71 functions)
  - [FlexLibs 2.0](https://github.com/your-repo/flexlibs2) (comprehensive, ~1,400 methods)

### Recommended
- Context7 MCP for improving and modernizing generated Python and C# code
- FieldWorks and FLExTools repositories for examples of real-life code

## Installation Steps

### 1. Set up Python in Windows Path

Install a current version of FLEx and FLExTools (with Python). Make sure Python paths (e.g. `C:\Program Files\Python311\Scripts\` and `C:\Program Files\Python311\`) are in your Windows Path. **Reboot after installing Python if this is your first Python installation.**

### 2. Clone FlexToolsMCP

```bash
git clone https://github.com/MattGyverLee/FlexToolsMCP.git
cd FlexToolsMCP
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Clone and Install FlexLibs 2.0

**Note:** The repo is named `flexlibs`, so clone it into the `flexlibs2` folder to avoid naming conflicts:

```bash
cd ..
git clone https://github.com/MattGyverLee/flexlibs.git flexlibs2
pip install ./flexlibs2
```

### 5. Configure Paths

```bash
cd FlexToolsMCP
cp .env.example .env
# Edit .env with your local paths
```

### 6. Test the Installation

```bash
python -c "from src.server import APIIndex, get_index_dir; i=APIIndex.load(get_index_dir()); print(f'Loaded {len(i.flexlibs2.get(\"entities\",{}))} FlexLibs2 entities')"
```

If this succeeds, the MCP and FlexLibs2 are installed correctly.

## Connecting to AI Assistants

**Note:** Indexes refresh automatically when you update FieldWorks or any of the libraries. You don't need to manually refresh.

### Claude Code

Create a folder for experimenting with MCPs (e.g., `C:/Github/MCPlayground`), then open it in VSCode.

```bash
# User-wide installation (available in all projects)
claude mcp add flextools-mcp -s user python C:/Github/FlexToolsMCP/src/server.py

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

Alternatively, add this to your Claude Code config file (`.claude/mcp_servers.json` at user or project level):

```JSON
{
  "mcpServers": {
    "flextools-mcp": {
      "command": "python",
      "args": [
        "C:/Github/FlexToolsMCP/src/server.py"
      ]
    }
  }
}
```

### Antigravity

Create a folder for experimenting with MCPs (e.g., `C:/Github/MCPlayground`), then open it in Antigravity.

Once open, click the `...` in the top-right of the chat window and choose `MCP Servers`. If FlexTools MCP isn't in the list, click the `Manage MCP Servers` link at the top.

Click `View RAW Config` and add the following to your Antigravity configuration file (`.antigravity/config.json` or similar):

```json
{
  "mcpServers": {
    "flextools-mcp": {
      "command": "python",
      "args": [
        "c://work//FlexToolsMCP//src//server.py",
        "--transport=stdio"
      ]
    }
  }
}
```

Adjust the path to match your FlexToolsMCP installation location.

### Other MCP-Compatible Tools

Configure the MCP server endpoint according to your tool's documentation.

## Next Steps

See [USAGE.md](USAGE.md) to learn how to use the MCP with your AI assistant.
