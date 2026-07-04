# Setup & Installation

FLExToolsMCP is published on [PyPI](https://pypi.org/project/flextools-mcp/) as
**`flextools-mcp`**. For normal use you do **not** clone this repo or install
anything by hand — one command wires it into your AI assistant and pulls every
dependency (including Flexicon) automatically.

## Prerequisites

- **Windows** with **FieldWorks 9.x** installed (FLExTools automation needs the
  FieldWorks/.NET runtime — this is a hard, Windows-only requirement).
- **Python 3.10+** on your PATH.
- **[uv](https://docs.astral.sh/uv/)** (provides the `uvx` runner). Install once:
  ```powershell
  powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
  ```

`pyflexicon` (the deep FieldWorks wrapper) is a declared dependency, so it is
installed for you — no separate step.

### Recommended (optional)
- Context7 MCP for improving/modernizing generated Python and C# code.
- The FieldWorks and FLExTools repositories on hand for real-life code examples.

## Quick install (recommended)

```bash
# Claude Code
claude mcp add flextoolsmcp -- uvx flextools-mcp
```

`uvx` fetches `flextools-mcp` and its dependencies into an isolated cache and
runs the server over stdio. The indexed API documentation ships inside the
package, so there is nothing else to download or build.

Prefer a persistent install instead of on-demand? Either works:
```bash
uv tool install flextools-mcp      # installs the `flextools-mcp` command
pip install flextools-mcp          # into the current environment
```

## Connecting to AI assistants

**Note:** Indexes ship with the package and also refresh automatically when your
installed FieldWorks / library versions change. You don't need to refresh by hand.

### Claude Code

```bash
# Project scope (from any project directory)
claude mcp add flextoolsmcp -- uvx flextools-mcp

# User scope (available in all projects)
claude mcp add flextoolsmcp -s user -- uvx flextools-mcp

# List / remove
claude mcp list
claude mcp remove flextoolsmcp -s user
```

### Claude Desktop, Cursor, and other MCP tools

Add this to the tool's MCP config (e.g. Claude Desktop's
`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "flextoolsmcp": {
      "command": "uvx",
      "args": ["flextools-mcp"]
    }
  }
}
```

### Antigravity

Open the MCP settings (`...` menu -> `MCP Servers` -> `View RAW Config`) and add:

```json
{
  "mcpServers": {
    "flextoolsmcp": {
      "command": "uvx",
      "args": ["flextools-mcp"]
    }
  }
}
```

If `uvx` is not found by your tool, use its absolute path (run `where uvx` /
`which uvx`) as the `command`.

## Updating

- **`uvx flextools-mcp`** (on-demand) picks up new releases automatically; pin
  or force the latest with `uvx flextools-mcp@latest`.
- **Persistent install:** `uv tool upgrade flextools-mcp` or
  `pip install -U flextools-mcp`.

Upgrading also re-resolves `pyflexicon` to its latest compatible version.

## Where your data lives

All user-writable state is under **`~/.flextoolsmcp/`** and persists across
upgrades (it is never written into the installed package):

- `logs/` — operation logs
- `skeletons.jsonl` — saved module skeletons
- `index/` — any indexes refreshed at runtime for your installed library versions
- `hf/` — cached embedding model

## Install from source (for development)

Only needed if you want to modify FLExToolsMCP or regenerate the indexes.

```bash
git clone https://github.com/MattGyverLee/FlexToolsMCP.git
cd FlexToolsMCP
pip install -e ".[dev]"          # editable install with dev tools (pulls in Flexicon)
cp .env.example .env             # configure paths for index regeneration

# Sanity check
python -c "from flextoolsmcp.server import APIIndex, get_index_dir; i=APIIndex.load(get_index_dir()); print('Loaded', len(i.flexicon.get('entities', {})), 'Flexicon entities')"
```

Point your AI tool at the source checkout by running the module directly:
```json
{
  "mcpServers": {
    "flextoolsmcp": {
      "command": "python",
      "args": ["-m", "flextoolsmcp"]
    }
  }
}
```

Regenerating indexes and cutting releases are documented in
[RELEASING.md](RELEASING.md) and [docs/VERSIONING.md](docs/VERSIONING.md).

## Next Steps

See [USAGE.md](USAGE.md) to learn how to use the MCP with your AI assistant.
