# Setup & Installation

FLExToolsMCP is published on [PyPI](https://pypi.org/project/flextools-mcp/) as
**`flextools-mcp`**. For normal use you do **not** clone this repo or install
anything by hand — one command wires it into your AI assistant and pulls every
dependency (including Flexicon) automatically.

## Where do I type these commands?

In a **Windows terminal** — PowerShell or Command Prompt — **not** in the Claude
chat box. `claude` is the Claude Code command-line program, so `claude mcp add`
is a shell command in the same family as `git`, `pip`, or `uvx`. If you paste it
into a conversation with Claude, nothing is installed.

Commands shown in `powershell` blocks are PowerShell-specific (the `uv`
installer is the main one). Everything else works in either shell.

The one thing you do *inside* Claude is **use** the tools once the server is
registered — see [USAGE.md](USAGE.md).

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

## Choose a working folder first

Before you connect an assistant, make a **new, empty folder** for your FLEx work
and open your assistant *there*:

```bash
mkdir ~/flex-scripts        # any empty folder; the name doesn't matter
```

> [!IMPORTANT]
> **Do not work inside a clone of FlexToolsMCP** (or of LibLCM, Flexicon,
> FlexLibs, FLExTools, or FieldWorks). You don't need any of that source —
> `uvx`/`pip` installs everything. When the workspace is one of those checkouts,
> assistants stop calling the MCP tools and start reading the repository instead:
> grepping the bundled API index, hand-copying templates, and in the worst case
> parsing LCM model XML or your project's `.fwdata` directly instead of going
> through the API. The result is slower, less accurate scripts.
>
> The server detects this and adds a `workspace_notice` to its responses asking
> you to move. If you are developing the MCP itself, the checkout *is* your
> workspace — set `FLEXTOOLSMCP_NO_WORKSPACE_CHECK=1` to silence it.

## Connecting to AI assistants

**Note:** Indexes ship with the package and also refresh automatically when your
installed FieldWorks / library versions change. You don't need to refresh by hand.

### Claude Code

Run these in PowerShell, not in the Claude chat:

```powershell
# User-wide (recommended): available in every folder you open
claude mcp add flextoolsmcp -s user -- uvx flextools-mcp

# Current directory only (this is the DEFAULT scope, "local")
claude mcp add flextoolsmcp -- uvx flextools-mcp

# List / remove
claude mcp list
claude mcp remove flextoolsmcp -s user
```

**How to install user-wide:** add `-s user`. The three scopes are:

| Scope | Flag | Stored in | Applies to |
|---|---|---|---|
| `local` | *(default, no flag)* | `%USERPROFILE%\.claude.json`, under the current directory's entry | only the folder you ran it in |
| `user` | `-s user` | `%USERPROFILE%\.claude.json`, top-level `mcpServers` | every folder you open Claude Code in |
| `project` | `-s project` | `.mcp.json` in the project, meant to be committed | anyone who checks out that repo |

Because `local` is the default, an `add` with no `-s` flag is the usual reason
the `flextools_*` tools "vanish" after you open a different folder. Use
`-s user` unless you specifically want the server tied to one directory.

Confirm registration and health:

```powershell
claude mcp list
# flextoolsmcp: uvx flextools-mcp - Connected
```

> [!IMPORTANT]
> **Restart your editor after the command succeeds.** Adding a server only
> writes configuration; MCP clients read that configuration when they start.
> Quit VS Code / Claude Desktop / Antigravity / Cursor **completely** and reopen
> it — closing a panel or opening a new chat is not enough. In VS Code you can
> instead run "Developer: Reload Window". Until you do, `claude mcp list` can
> report **Connected** while your assistant still exposes no `flextools_*`
> tools, because the running client never read the new config. This applies
> equally after an upgrade.

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

## Keeping both environments in sync

This is the most common source of "it worked in Claude but fails in FLExTools".
There are **two independent Python interpreters**, and Flexicon must be current
in whichever ones you use:

| Environment | Which interpreter | What runs there | Upgrade Flexicon with |
|---|---|---|---|
| **MCP server** | whatever launches the server: the `uvx` cache, a conda env, a venv, or the `python` you `pip install`ed into | `flextools_run_module` — the MCP runs generated code with its **own** `sys.executable` | comes with the MCP; `pyflexicon` is a declared dependency of `flextools-mcp` |
| **FLExTools GUI** | the Windows launcher `py` — your PATH Python (e.g. `C:\Python313`) | modules saved into `FlexTools\Modules\` and run from the FLExTools window | `py -m pip install -U pyflexicon` |

### Why there are two

FLExTools decides its interpreter in `FlexTools\scripts\FlexToolsCommands.vbs`,
which sets `PYTHON = "py"` — the Windows Python launcher, resolving to your
system-registered default Python. The MCP, meanwhile, executes generated modules
with its own `sys.executable`. If your assistant launches the MCP from a conda
environment, a venv, or the `uvx` cache, then *by construction* that is not the
same interpreter FLExTools uses.

So:

- `flextools_run_module` succeeding proves Flexicon is fine in the **MCP's**
  environment. It proves nothing about the FLEx side.
- Saving that same module and running it from the FLExTools GUI exercises the
  **`py`** environment. A missing or old `pyflexicon` there produces
  `ImportError`, `AttributeError`, or quietly different behaviour — for code
  the MCP just validated.

> [!IMPORTANT]
> FLExTools' `InstallOrUpdate.vbs` upgrades **only `flextoolslib`**. It never
> touches `pyflexicon`. Nothing in FLExTools will ever update the FLEx-side
> Flexicon for you — that upgrade is yours to run.

### Check what each environment actually has

```powershell
# 1. The FLExTools GUI side (the `py` launcher)
py -c "import sys; print(sys.executable)"
py -m pip show pyflexicon flextoolslib

# 2. The MCP side -- first find out what launches it
claude mcp list
```

`claude mcp list` prints the launch command. Read it and check that same
interpreter:

- **`uvx flextools-mcp`** — an ephemeral, self-managing environment. `pip show`
  will not find it; that is expected. Upgrade it with `uvx flextools-mcp@latest`.
- **`<path>\python.exe -m flextoolsmcp`** (a conda env, venv, or system Python)
  — check and upgrade *that exact* interpreter:

  ```powershell
  & "D:\path\to\python.exe" -m pip show flextools-mcp pyflexicon
  & "D:\path\to\python.exe" -m pip install -U flextools-mcp
  ```

  Using the full path matters: a bare `pip` in your shell may well be a
  different Python than the one Claude launches the server with.

### The version that has to match

`flextools-mcp` declares a `pyflexicon` floor, and the bundled API index is
built against it. Both environments should be at or above that floor and, ideally,
on the same version. To see the floor for the release you are running:

```powershell
py -m pip show flextools-mcp          # "Requires:" lists pyflexicon
py -m pip index versions pyflexicon   # what is available on PyPI
```

If the FLEx-side version is below the floor, generated modules can reference
methods that copy of Flexicon does not have.

### Upgrade everything, in order

```powershell
# 1. The MCP + the Flexicon inside its own environment
uvx flextools-mcp@latest                     # uvx installs
# or: uv tool upgrade flextools-mcp          # uv tool installs
# or: pip install -U flextools-mcp           # pip installs (name the package!)
# or, for a specific interpreter:
#     & "D:\path\to\python.exe" -m pip install -U flextools-mcp

# 2. Flexicon on the FLExTools GUI side (separate, always required)
py -m pip install -U pyflexicon

# 3. FLExTools itself, if it is also behind
py -m pip install -U flextoolslib

# 4. Verify both
py -m pip show pyflexicon
claude mcp list
```

Then **fully restart your AI assistant** so it relaunches the server.

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
compatible version — **but only inside the MCP's own environment.** Flexicon on
the FLExTools GUI side is a separate upgrade that nothing does for you:

```powershell
py -m pip install -U pyflexicon
```

See [Keeping both environments in sync](#keeping-both-environments-in-sync).

**Then restart your editor / assistant.** A running MCP client keeps the server
process it already launched; it will not pick up the new version until you fully
quit and reopen the application (or, in VS Code, "Developer: Reload Window").

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

### Works under the MCP, fails in the FLExTools GUI (environment drift)

**Symptom:** `flextools_run_module` runs a module fine, but saving that same
module into `FlexTools\Modules\` and running it from the FLExTools window raises
`ImportError: No module named flexicon`, an `AttributeError` on a Flexicon
method, or produces different results.

**Cause:** two different interpreters. The MCP runs code with its own
`sys.executable`; FLExTools runs it with `py` (your PATH Python). Flexicon is
missing, or older, in the `py` environment. FLExTools' `InstallOrUpdate.vbs`
upgrades only `flextoolslib`, so it never fixes this.

**Fix:**

```powershell
py -c "import sys; print(sys.executable)"   # which Python FLExTools uses
py -m pip install -U pyflexicon             # install/upgrade Flexicon there
py -m pip show pyflexicon                   # confirm
```

Compare that version against the floor the MCP requires
(`py -m pip show flextools-mcp` → `Requires:`). Full detail in
[Keeping both environments in sync](#keeping-both-environments-in-sync).

### The assistant shows no `flextools_*` tools even though `claude mcp list` says Connected

**Cause:** the MCP client has not been restarted since the config changed.
`claude mcp add` and `claude mcp list` talk to the config file; your editor's
running session does not re-read it.

**Fix:** quit VS Code / Claude Desktop / Antigravity / Cursor **entirely** and
reopen it (in VS Code, "Developer: Reload Window" also works). Closing a tab,
closing the Claude panel, or starting a new chat is not sufficient.

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

Point your AI tool at the source checkout by running the module directly. Add
`FLEXTOOLSMCP_NO_WORKSPACE_CHECK=1` so the `workspace_notice` doesn't fire — when
you're developing the MCP, the checkout legitimately *is* your workspace:
```json
{
  "mcpServers": {
    "flextoolsmcp": {
      "command": "python",
      "args": ["-m", "flextoolsmcp"],
      "env": { "FLEXTOOLSMCP_NO_WORKSPACE_CHECK": "1" }
    }
  }
}
```

Regenerating indexes and cutting releases are documented in
[RELEASING.md](RELEASING.md) and [docs/VERSIONING.md](docs/VERSIONING.md).

## Next Steps

See [USAGE.md](USAGE.md) to learn how to use the MCP with your AI assistant.
