# Setup & Installation

FLExToolsMCP is published on [PyPI](https://pypi.org/project/flextools-mcp/) as
**`flextools-mcp`**. For normal use you do **not** clone this repo or install
anything by hand — one command wires it into your AI assistant and pulls every
dependency (including Flexicon) automatically.

## Prerequisites

- **Windows** with **FieldWorks 9.x** installed (FLExTools automation needs the
  FieldWorks/.NET runtime — this is a hard, Windows-only requirement).
- **Python 3.10+** on your PATH.

### Step 1 — Install `uv` (all users, every AI tool)

Every supported AI assistant launches FLExToolsMCP the same way: with `uvx`
(from [uv](https://docs.astral.sh/uv/)). Install it first, before touching any
tool config:

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Then log off and back on — or reboot — so Windows picks up the new PATH.**
The uv installer adds `uvx` to your PATH, but that change does **not** reach
terminals or GUI apps that were already running, and on Windows it often does
not fully settle until you start a fresh login session. A quick "open a new
terminal" sometimes works, but a **log off / reboot is the reliable fix** and
is what we recommend.

After logging back on, confirm `uvx` resolves:

```powershell
uvx --version
```

This must print a version. If it fails with "not recognized" /
"command not found", skip ahead to [Troubleshooting](#troubleshooting) before
wiring anything up.

### Step 2 — Pre-warm the cache (recommended, all users)

Run the server once from a plain terminal so `uvx` downloads and caches
`flextools-mcp` and its dependencies **outside** your AI tool:

```powershell
uvx flextools-mcp
```

Let it start up (it will print startup logs and wait on stdio — press
`Ctrl+C` to stop it once you see it running), then continue to
[Connecting to AI assistants](#connecting-to-ai-assistants).

Do this even though the tool config below could trigger the same download on
first launch. Letting a GUI assistant (e.g. Antigravity) perform that initial
download inline is where things go wrong — the large first-run download
(`pyflexicon`, the .NET interop, and the semantic-search stack) frequently
surfaces as confusing load/connection errors inside the tool. Priming the cache
in a terminal first makes the tool's launch instant and clean.

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

> [!IMPORTANT]
> `claude mcp add` only **records** the command — it reports success even if
> `uvx` isn't installed or isn't on your PATH. The failure surfaces later, when
> your AI assistant tries to *launch* the server (it appears to hang, fails to
> connect, or shows no FLExTools tools). Always run `uvx --version` in a fresh
> terminal **before** `claude mcp add`. See [Troubleshooting](#troubleshooting).

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

> [!IMPORTANT]
> Make sure you completed **[Step 2 — Pre-warm the cache](#step-2--pre-warm-the-cache-recommended-all-users)**
> before adding the server here. If Antigravity is the first thing to run
> `uvx flextools-mcp`, it does the large first-run download inline, which
> commonly shows up as weird load/connection errors in the tool. Running
> `uvx flextools-mcp` once in a terminal first avoids this entirely.

## Updating

The server itself will tell you when a newer release is out: when it detects a
newer `flextools-mcp` on PyPI it adds an `update_notice` to its responses and
your assistant relays it, with the right command for your install. (It checks
PyPI at most once a day, in the background; disable with
`FLEXTOOLSMCP_NO_UPDATE_CHECK=1`.)

Use the command that matches how you installed it:

- **On-demand `uvx`:** run **`uvx flextools-mcp@latest`**. Plain
  `uvx flextools-mcp` does **not** reliably pick up new releases — `uvx` reuses
  its cached tool environment and won't re-check PyPI on its own. To make the
  MCP config always re-resolve, set the launch args to `flextools-mcp@latest`.
- **Persistent install:** `uv tool upgrade flextools-mcp`.
- **pip install:** `pip install -U flextools-mcp` — **name the package.** A
  blanket `pip install -U` (or upgrading only `pyflexicon`) can leave the MCP
  itself behind while bumping its dependencies; pip does not discover that a
  newer MCP exists.

Upgrading `flextools-mcp` also re-resolves `pyflexicon` to its latest
compatible version.

> [!TIP]
> To confirm the version actually running, ask the assistant, or check the same
> environment the server launches from: `pip show flextools-mcp pyflexicon`
> (pip installs) or `uv tool list` (uv tool installs). If it's launched via
> `uvx`, `pip show` won't find it — that itself tells you pip is not the lever
> to upgrade with.

## Troubleshooting

### The server won't start / no FLExTools tools appear (`uvx` not found)

**Symptom:** `claude mcp add flextoolsmcp -- uvx flextools-mcp` completed
successfully, but the server never connects — your AI assistant shows the
server as failed/disconnected, hangs on startup, or exposes no `flextools_*`
tools.

**Cause:** `claude mcp add` only records the launch command; it does not check
that `uvx` exists. When the assistant later tries to run `uvx flextools-mcp`,
`uvx` isn't found on the PATH the assistant sees, so the server dies
immediately. This most often happens right after installing `uv`: the installer
adds `uvx` to your PATH, but **already-open terminals and apps keep their old
PATH until they are restarted.**

**Fix:**

1. Install `uv` if you haven't (see [Prerequisites](#prerequisites)):
   ```powershell
   powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
   ```
2. **Log off and back on, or reboot.** This is the step most people miss — the
   new PATH does not reach programs that were already running, and on Windows it
   often does not fully settle until a fresh login session. A brand-new terminal
   sometimes suffices, but a log off / reboot is the reliable fix because it also
   refreshes GUI apps like Claude Desktop and Antigravity, which inherit PATH
   from when they launched.
3. Confirm `uvx` is now resolvable:
   ```powershell
   uvx --version        # must print a version
   where uvx            # shows where it was found (usually %USERPROFILE%\.local\bin)
   ```
4. Fully quit and reopen your AI assistant (Claude Desktop / Antigravity /
   Cursor), or re-run `claude mcp add` for Claude Code, then reconnect.

### The server runs an old version / wrong dependency (stale `uvx` cache)

**Symptom:** you released or expected a newer `flextools-mcp` (or a newer
`pyflexicon`), but the running server is still on an old build — e.g. it loads
an older Flexicon than the current release requires.

**Cause:** `uvx flextools-mcp` (no `@latest`) reuses uv's **cached** tool
environment and does not re-check PyPI on every launch, so it can keep serving a
build from before your last upgrade.

**Fix:** force a re-resolve —

```powershell
uvx flextools-mcp@latest        # run the newest, re-resolving now
# or, to clear just this tool's cache and rebuild on next launch:
uv cache clean flextools-mcp
```

`@latest` re-resolves but still **reuses cached wheels** for anything unchanged,
so this does not re-download the heavy stack (torch, faiss, pythonnet) unless
those themselves changed version. Avoid `uvx --refresh` / `uv cache clean`
(no args) for routine updates — those force a full re-download. To keep an MCP
config always current, set its launch args to `flextools-mcp@latest`.

### `uvx --version` still fails after a reboot

The uv installer normally drops `uvx.exe` in `%USERPROFILE%\.local\bin`. If that
folder isn't on your PATH, either add it, or point the MCP config at the
absolute path instead of relying on PATH resolution:

```json
{
  "mcpServers": {
    "flextoolsmcp": {
      "command": "C:\\Users\\<you>\\.local\\bin\\uvx.exe",
      "args": ["flextools-mcp"]
    }
  }
}
```

Run `where uvx` (or `Get-Command uvx`) to find the exact path on your machine.
For Claude Code, pass the absolute path the same way:
`claude mcp add flextoolsmcp -- "C:\Users\<you>\.local\bin\uvx.exe" flextools-mcp`.

### Prefer to avoid `uvx` entirely

If PATH issues persist, install the package into a Python environment you
already control and launch it without `uvx`:

```powershell
pip install flextools-mcp
```

Then configure the server to run via Python:

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

(Make sure the same `python` is the one that has `flextools-mcp` installed.)

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
