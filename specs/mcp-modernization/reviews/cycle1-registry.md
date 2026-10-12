# Cycle 1 — MCP Registry (Phase 4) discovery & audit

Role: lex-registry. Read-only research + repo audit; nothing was published and
`mcp-publisher` was not run. Worktree audited at `origin/main c1c751f`,
package version `2.15.0` (`VERSION` file, consumed dynamically by
`pyproject.toml`; `flextoolsmcp.__version__` reads importlib metadata for
dist `flextools-mcp`).

## Sources (official first)

- Schema (current, dated): https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json
- Quickstart: https://modelcontextprotocol.io/registry/quickstart
- Authentication: https://modelcontextprotocol.io/registry/authentication
- Package types / ownership verification: https://modelcontextprotocol.io/registry/package-types
- GitHub Actions publishing: https://modelcontextprotocol.io/registry/github-actions
- Publisher CLI (repo): https://github.com/modelcontextprotocol/registry/blob/HEAD/cmd/publisher/README.md
- Registry API base: https://registry.modelcontextprotocol.io

Third-party publishing runbooks were used only to corroborate lifecycle
behaviour (`status`, immutability); every normative claim below traces to the
official pages/schema above.

## 1. Current `server.json` schema (2025-12-11)

There is **no `schemaVersion` field** in the current schema. The schema
revision is identified only by the `$schema` URL itself
(`.../schemas/2025-12-11/server.schema.json`). Do not copy older examples that
carry a separate schema-version property or the older un-dated schema URL.

Top-level object (`ServerDetail`):

| Field | Req? | Rules |
|---|---|---|
| `$schema` | no | URI; use the dated URL above |
| `name` | **yes** | Reverse-DNS, pattern `^[a-zA-Z0-9.-]+/[a-zA-Z0-9._-]+$`, exactly one `/`, 3–200 chars |
| `description` | **yes** | 1–100 chars, capabilities not implementation |
| `version` | **yes** | This server's release version; SHOULD be semver, max 255 chars; ranges and `latest` rejected |
| `title` | no | Human display name, 1–100 chars |
| `websiteUrl` | no | URI (homepage/docs) |
| `repository` | no (recommended) | Object, see below |
| `icons` | no | Array of `{src (HTTPS URI, ≤255, required), mimeType?, sizes?, theme?}`; mimeType ∈ png/jpeg/jpg/svg+xml/webp; sizes are `WxH` or `any` |
| `packages` | no* | Array of `Package`; *a listing needs `packages` and/or `remotes` to be installable — this server is local-only, so `packages` only |
| `remotes` | no | Not applicable (no hosted endpoint) |
| `_meta` | no | Reverse-DNS-namespaced vendor extensions only |

Version semantics — three different "versions" not to conflate:

1. `$schema` URL date = manifest format revision.
2. Top-level `version` = the server's own release version. For this repo it
   must equal the `VERSION` file / PyPI release (`2.15.0` today).
3. `packages[].version` = the package version in its registry. Must be a
   specific version (ranges/`latest` rejected) and in practice must equal (2),
   because the registry validates the package at that version exists.

`repository` object: `url` and `source` are **both required if the object is
present** (`source: "github"`); `id` (forge repo ID, anti-resurrection check)
and `subfolder` (monorepo path) are optional. This server is at the repo root,
so no `subfolder`.

`packages[]` (`Package`): required = `registryType`, `identifier`,
`transport`. Optional = `version`, `registryBaseUrl`, `runtimeHint`,
`runtimeArguments`, `packageArguments`, `environmentVariables`, `fileSha256`
(MCPB only in practice).

For a PyPI stdio server:

- `registryType: "pypi"` — only official PyPI (`https://pypi.org`) is
  supported; `registryBaseUrl` may be omitted (default) or set explicitly.
- `identifier`: the PyPI project name, here `flextools-mcp`.
- `transport: {"type": "stdio"}` — no URL for stdio.
- `runtimeHint: "uvx"` — tells clients to launch via `uvx`, i.e. generated
  config is effectively `command: uvx`, `args: ["flextools-mcp==<version>"]`.
  No `packageArguments` are needed: the package ships a console script named
  `flextools-mcp` (and `flextoolsmcp`), and `uvx <pkg>` runs the like-named
  executable. `runtimeArguments` likewise unnecessary.
- `environmentVariables`: array of `KeyValueInput` — `{name (required),
  description?, default?, format? (string|number|boolean|filepath),
  isRequired?, isSecret?, choices?, placeholder?, value?}`. Declare names and
  metadata only; never values for secrets (none of ours are secret).

**PyPI ownership verification (critical):** unlike npm (which checks an
`mcpName` key in `package.json`), PyPI verification looks for the literal
string `mcp-name: io.github.mattgyverlee/flextoolsmcp` in the package's PyPI
long description — i.e. in this repo's `README.md` (pyproject `readme =
"README.md"`), possibly inside an HTML comment. The check runs at publish
time against the already-published PyPI release. See §4, finding A1.

## 2. Publishing flow, auth, lifecycle

Flow (`mcp-publisher`, installed from the registry repo's releases or
Homebrew — do not build from source for production use):

```bash
mcp-publisher init        # optional; scaffolds server.json
mcp-publisher validate [server.json]   # local validation, no publish
mcp-publisher login github             # interactive OAuth, OR
mcp-publisher login github-oidc        # inside GitHub Actions only
mcp-publisher publish [server.json]    # validates again, then POSTs to the registry
mcp-publisher logout
# verify: curl "https://registry.modelcontextprotocol.io/v0.1/servers?search=io.github.mattgyverlee/flextoolsmcp"
```

Order matters: the package must be live on PyPI **first** (registry hosts
metadata only, never artifacts), at the exact version named in `server.json`,
and that PyPI release's description must contain the `mcp-name:` string.

GitHub auth and the `io.github.*` namespace:

- Interactive: `login github` runs a GitHub OAuth device flow; the resulting
  short-lived registry JWT proves control of that GitHub account. It grants
  publishing only under `io.github.<that-user>/*` (or an org the user belongs
  to). For `io.github.mattgyverlee/flextoolsmcp` the login must therefore be
  **Matthew's own GitHub account `MattGyverLee`** (namespace segment is the
  lower-cased username in the prescribed name — see flag F3 in §6).
- OIDC (recommended for releases): a workflow in
  `MattGyverLee/FlexToolsMCP` with `permissions: id-token: write` runs
  `login github-oidc`; the Actions OIDC token's repository/owner claims prove
  the same namespace. **No stored secret is needed.** This mirrors the
  existing `.github/workflows/publish.yml`, which already publishes to PyPI
  by OIDC trusted publishing on `v*` tags — a registry job can ride the same
  tag trigger after the PyPI job succeeds.

Lifecycle / reversibility:

- **Published versions are immutable.** A version's metadata cannot be
  edited or replaced; any correction (even a description typo) is a new
  release: bump top-level + package version, publish again. The newest
  version becomes the default/`isLatest`.
- Status **is** mutable per version: `mcp-publisher status --status
  <active|deprecated|deleted> [--message ...] <name> <version>` (or
  `--all-versions`). `deprecated` keeps the entry visible with a warning;
  `deleted` hides it from default listings (still retrievable with
  `include_deleted=true`) and can be reversed back to `active`. There is no
  hard erase — **the server name, once used, is effectively permanent**, so
  the name choice in §6 is the one irreversible decision.
- Re-publishing the same version is a duplicate, not an update.

## 3. Local validation (no publishing)

1. `mcp-publisher validate` (optionally with a path) — checks JSON syntax,
   schema compliance and registry semantic rules in one pass. This is the
   authoritative local check and needs no auth.
2. Pure JSON-Schema check against the pinned schema URL, e.g.
   `uvx check-jsonschema --schemafile https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json server.json`
   — catches schema violations only; it does **not** catch the PyPI
   `mcp-name:` ownership check or package-existence check, which only run
   server-side at publish time.
3. `mcp-publisher init` can scaffold a template for diffing, but the draft in
   §6 should be the starting point instead.

## 4. Audit — README.md / SETUP.md / pyproject.toml

What is already correct: the canonical launch everywhere in README/SETUP is
`uvx flextools-mcp` (hyphenated console script), with matching
`claude mcp add flextoolsmcp -s user -- uvx flextools-mcp`, manual
`{"command":"uvx","args":["flextools-mcp"]}` configs, `pip install
flextools-mcp` / `uv tool install flextools-mcp` alternatives, and the
`uvx flextools-mcp@latest` upgrade caveat. `requires-python >=3.10`, stdio
transport, and both console scripts match `pyproject.toml`.

Inaccuracies / gaps a registry listing would amplify:

- **A1 (publish blocker). No `mcp-name:` string anywhere.** `grep` finds no
  `mcp-name` and no `io.github.*` name in README, SETUP or pyproject. Without
  `mcp-name: io.github.mattgyverlee/flextoolsmcp` in README (an HTML comment
  suffices), PyPI ownership verification fails at publish. Worse: it must be
  in the **PyPI release's** description, so if the current release predates
  the fix, a fresh PyPI release (patch bump) is required before the registry
  publish can succeed.
- **A2. `uvx flextoolsmcp` does not work.** The pyproject comment claims the
  `flextoolsmcp` script name means "`uvx flextoolsmcp` works with no
  `--from`". `uvx <tool>` resolves a PyPI **package** of that name; there is
  no `flextoolsmcp` distribution (the dist is `flextools-mcp`). Correct form
  is `uvx flextools-mcp` (as README/SETUP use) or `uvx --from flextools-mcp
  flextoolsmcp`. Any registry copy or agent brief repeating `uvx
  flextoolsmcp` sends users to a failed/unrelated resolution.
- **A3. Windows/FieldWorks requirement is understated in the places a
  listing quotes.** pyproject classifiers list only
  `Operating System :: Microsoft :: Windows`; SETUP calls Windows +
  FieldWorks 9.x a "hard, Windows-only requirement", but the README leads
  with "nothing else to install" / "installable anywhere" framing.
  `server.json` has no OS field, so the listing will be offered to macOS/
  Linux users: the package installs there, but no FieldWorks work is
  possible. The registry description/title must not imply cross-platform
  function, and README's prerequisite wording should be aligned before the
  listing drives traffic to it.
- **A4. `flextools-mcp-refresh` is invisible to installed users.** pyproject
  presents the refresh console script as the reliable post-install index
  warmup, and RELEASING.md uses it, but neither README nor SETUP's install
  paths mention running it after `pip install`/`uv tool install`; SETUP
  instead says indexes "refresh automatically… You don't need to refresh by
  hand". Both can be true (lazy self-heal exists) but as written the pip
  path silently pays the first-run lazy-refresh delay the pyproject comment
  says the script exists to avoid. A registry-generated install makes the
  pip/uvx path the default, so this needs one consistent sentence.
- **A5. Safety copy contradicts itself.** README's overview warns there are
  "no guard-rails" and to back up, while its Safety section says the MCP
  "defaults to dry-run mode" and "requires explicit user permission for
  write operations". Aggregators quote README text; reconcile before
  listing.
- **A6. User-data inventory drift.** README says `~/.flextoolsmcp/` holds
  `recipes.jsonl` and `recipe-drafts/`; SETUP's inventory lists
  `skeletons.jsonl` and omits the recipe files. Code uses `recipes.jsonl`.
  Minor, but it is exactly the kind of drift a listing's inbound users hit
  first.
- **A7. pyproject description is too long to reuse.** The project
  description is 112 chars; the registry caps `description` at 100. The
  draft in §6 uses a shortened variant — do not copy the pyproject text
  verbatim into `server.json`.
- **A8. No version-sync step exists for a future `server.json`.** Releases
  are tag-driven (`v*` → publish.yml). Nothing yet bumps or checks a
  `server.json`; add a release-checklist/CI step asserting
  `server.json` `version` == `packages[0].version` == `VERSION`, or the
  listing will silently lag PyPI (the registry never auto-follows PyPI).

## 5. Environment variables for the manifest

From `.env.example` (names only; all optional, none secret). Declare in
`server.json` only the ones meaningful to an end user launching via a
registry-generated client config; source-checkout path overrides are
developer/index-regeneration knobs and would make clients prompt for
nonsense — they are listed as excluded, deliberately:

Declare (all `isRequired: false`, `isSecret: false`):

- `FLEXTOOLS_STATELESS` — stateless/short-lived-client mode (from
  `.env.example`; also documented in SETUP for Hermes/OpenClaw hosts).
- `FW_PROJECTS_DIR` — override FieldWorks projects directory (filepath).
- `FLEXTOOLSMCP_LOG_DIR` — override log directory (filepath).
- `FLEXTOOLSMCP_RECIPE_DIR` — override recipe store location (filepath);
  documented in README but **missing from `.env.example`** (doc gap).
- `FLEXTOOLSMCP_NO_UPDATE_CHECK` — disable PyPI update checks (README/SETUP
  only, also missing from `.env.example`).
- `FLEXTOOLSMCP_NO_WORKSPACE_CHECK` — silence the in-checkout workspace
  notice (README/SETUP only).

Do **not** declare: `FLEXLIBS_PATH`, `FLEXICON_PATH`, `LIBLCM_PATH`,
`FIELDWORKS_DLL_PATH`, `FLEXTOOLS_PATH`, `FIELDWORKS_PATH` (source-clone /
index-regeneration overrides from `.env.example`); `FLEXLIBS2_PATH`
(explicitly obsolete per `.env.example`, issue #141); internal tuning vars
found in code but in neither doc (`FLEXTOOLSMCP_INDEX_DIR`,
`FLEXTOOLSMCP_SKELETON_DIR` legacy fallback, the
`FLEXTOOLSMCP_PARSE_*` / `FLEXTOOLSMCP_FILING_*` family) unless a later
phase decides they are user-facing. No variable in this project is a
credential; none gets `isSecret: true`.

## 6. Draft `server.json` (ready to drop in after Phases 1–2 + A1 fix)

```json
{
  "$schema": "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json",
  "name": "io.github.mattgyverlee/flextoolsmcp",
  "title": "FLExTools MCP",
  "description": "Search LibLCM and Flexicon APIs, write and run FLExTools scripts against FieldWorks projects.",
  "version": "2.15.0",
  "websiteUrl": "https://github.com/MattGyverLee/FlexToolsMCP",
  "repository": {
    "url": "https://github.com/MattGyverLee/FlexToolsMCP",
    "source": "github"
  },
  "packages": [
    {
      "registryType": "pypi",
      "registryBaseUrl": "https://pypi.org",
      "identifier": "flextools-mcp",
      "version": "2.15.0",
      "runtimeHint": "uvx",
      "transport": { "type": "stdio" },
      "environmentVariables": [
        {
          "name": "FLEXTOOLS_STATELESS",
          "description": "Set to 1 for short-lived MCP clients that restart the server every turn; skips API-discovery gates only.",
          "isRequired": false,
          "isSecret": false,
          "format": "string",
          "default": "0"
        },
        {
          "name": "FW_PROJECTS_DIR",
          "description": "Override the FieldWorks projects directory used to discover projects.",
          "isRequired": false,
          "isSecret": false,
          "format": "filepath"
        },
        {
          "name": "FLEXTOOLSMCP_LOG_DIR",
          "description": "Override the log directory (default: ~/.flextoolsmcp/logs).",
          "isRequired": false,
          "isSecret": false,
          "format": "filepath"
        },
        {
          "name": "FLEXTOOLSMCP_RECIPE_DIR",
          "description": "Override where saved recipes are stored.",
          "isRequired": false,
          "isSecret": false,
          "format": "filepath"
        },
        {
          "name": "FLEXTOOLSMCP_NO_UPDATE_CHECK",
          "description": "Set to 1 to disable the server's PyPI update checks.",
          "isRequired": false,
          "isSecret": false,
          "format": "string",
          "default": "0"
        },
        {
          "name": "FLEXTOOLSMCP_NO_WORKSPACE_CHECK",
          "description": "Set to 1 to silence the workspace notice when working inside a source checkout.",
          "isRequired": false,
          "isSecret": false,
          "format": "string",
          "default": "0"
        }
      ]
    }
  ]
}
```

Flags — fields not fully verified from repo sources:

- **F1 `version` / `packages[0].version` = `2.15.0`**: taken from the
  worktree `VERSION` file. Whether PyPI's latest published release is
  exactly 2.15.0 was **not verified live**; at publish time both fields must
  equal a PyPI release whose description contains the A1 `mcp-name:`
  string — if that requires a new release, bump all three together.
- **F2 `repository.id` omitted**: optional, recommended for anti-spoofing,
  but the GitHub numeric repo ID was not read from a repo source; add it
  (via `gh api repos/MattGyverLee/FlexToolsMCP --jq .id`) before publishing
  if desired.
- **F3 Name casing**: prescribed name is all-lowercase
  `io.github.mattgyverlee/flextoolsmcp`, while the GitHub account is
  `MattGyverLee`. Schema pattern allows either; the authentication docs
  write the namespace as `io.github.username/*` without a casing rule in
  the material reviewed. Confirm the registry's case handling for the
  GitHub username match at first `validate`/publish attempt; the
  `mcp-name:` string in README must match the chosen name **exactly**.
- **F4 `icons` omitted**: repo images (`docs/MCPodcast.png`,
  `docs/COP-Thumbnail.png`) are video thumbnails, not server icons, and no
  stable HTTPS icon URL is declared in repo sources. Add `icons` only when
  a real icon is hosted.
- **F5 `default: "0"` on the boolean-style flags**: code treats these as
  presence/`"1"`-style toggles (exact parsing not audited line-by-line for
  every flag); the defaults are documentation-grade. Drop the `default`
  keys if `mcp-publisher validate` or Phase 1–2 review prefers absence
  over an explicit off value.
- **F6 Description (93 chars)**: newly written to fit the 100-char cap
  (see A7); not a quote of any existing project text. Matthew may want
  final wording — it is immutable per published version (§2).

## 7. Who does what at publish time

An agent can: add `server.json`, add the `mcp-name:` comment to README,
fix A2/A4–A8 docs, run `mcp-publisher validate` + the JSON-Schema check,
draft the OIDC publish job alongside `publish.yml`, and verify the live
listing via the registry API afterwards.

Matthew personally must: (a) approve the immutable server **name**; (b) for
a manual first publish, run `mcp-publisher login github` under his own
GitHub account `MattGyverLee` (OAuth device flow — an agent cannot hold
that identity); or (c) for the automated path, approve/merge the workflow
change that grants `id-token: write` and runs `login github-oidc` (adding/
changing workflows is the credentialed step), after which tag releases
publish with no stored secret and no further action from him. The PyPI
release carrying the `mcp-name:` fix (A1) must land before either path can
succeed.
