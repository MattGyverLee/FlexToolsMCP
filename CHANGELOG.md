# FlexToolsMCP Changelog

## [Unreleased]

## [2.9.1] - 2026-08-10

### Fixed: installs of 2.3.1-2.9.0 were broken against mcp 2.0.0

**Every published release from 2.3.1 through 2.9.0 (11 releases) fails to
import on a fresh install today.** `pyproject.toml`/`requirements.txt`
declared an uncapped `mcp>=1.27.0`; mcp 2.0.0 (released 2026-07-28) removed
the low-level `Server.list_tools()`/`call_tool()` decorator API that
`server.py` depends on, so any fresh `pip install` resolving mcp>=2.0.0
raises `AttributeError` at import time. 2.9.1 is the fix: it caps `mcp` back
to the working 1.x range. No forward port to mcp 2.0 is included in this
release (tracked separately, see `specs/mcp2-compat/deferred-issues.md`).

- **Capped `mcp` to `>=1.27.0,<2`** in `pyproject.toml` and `requirements.txt`.
  Newest available 1.x is 1.29.0, which resolves cleanly with no dependency
  fallout.
- **Fixed error laundering in the lazy server loader**
  (`src/flextoolsmcp/server/__init__.py`). The loader's
  `spec.loader.exec_module(...)` call had no try/except; because it runs
  inside module `__getattr__`, CPython's `IMPORT_FROM` opcode reinterprets
  *any* `AttributeError` escaping it as "attribute absent" and re-raises a
  generic `ImportError: cannot import name`, destroying the real
  traceback/message. This is exactly why the original mcp 2.0 break surfaced
  in CI as `ImportError: cannot import name 'APIIndex'`, naming neither `mcp`
  nor `list_tools`. `exec_module` is now wrapped in `try/except Exception`,
  re-raising a clearly labeled `ImportError` chained via `raise ... from exc`
  so the true cause is always visible.
- **Cached the load failure**, not just the success. A broken `server.py`
  previously re-executed in full on *every* subsequent lazy attribute touch,
  compounding side effects (logging setup, decorator registration) and
  further obscuring the original error. A failed load is now cached and
  short-circuits immediately on later access.
- **Added `list_tools`, `call_tool`, and `server` to the lazy-loader's
  `LAZY_IMPORTS` set.** They were defined in `server.py` but never
  registered for lazy loading, so `from flextoolsmcp.server import
  list_tools` always raised `ImportError: cannot import name 'list_tools'`
  even when `server.py` itself imported fine -- and no runtime tool-count
  check could ever exercise the actual decorator-registration seam that
  broke.
- **Fixed `scripts/validate_integrity.py`'s tool-count check, which had been
  silently AST-only for its entire life.** `check_server_tools()` imported
  from `src.server` (a module that can never resolve -- no `src/__init__.py`
  exists), so every run fell through to the AST fallback and reported
  `"23 tool definitions found (AST) [OK]"` against a completely
  non-importable server under mcp 2.0.0. Repointed to
  `flextoolsmcp.server`, which now performs a real runtime `list_tools()`
  call and reports `"N tools registered (runtime) [OK]"`. The AST path
  remains as a fallback but now prints plainly that it is a DEGRADED check
  when it fires, so it can never again be mistaken for a real runtime
  verification. Also fixed a second dead `src.server` import in the
  flexicon contract check.
- **Fixed `check_runtime_import()`'s silent fall-through to green.** A
  non-zero subprocess exit whose stderr contained neither `ImportError` nor
  `ModuleNotFoundError` (e.g. a bare `AttributeError` from a removed
  decorator API) fell through to `return True` -- an unclassified runtime
  failure now correctly fails the check. The existing, deliberate skip for
  genuine third-party "dependency not installed" `ImportError`s is
  unchanged.
- **Added a wheel-install smoke-test job to `.github/workflows/publish.yml`**
  (`smoke`, gating `publish`). It installs the just-built wheel into a
  completely fresh venv -- no repo checkout, no editable install, no
  `conftest.py` sys.path shims -- and runs
  `list_tools()` from a directory outside the repo, exercising the exact
  lazy-loader + decorator-registration seam that broke. `twine check` only
  validates package metadata and could never have caught this.
- **Added `--continue-on-collection-errors` to both pytest invocations in
  `.github/workflows/test.yml`.** On 2026-08-01 the mcp 2.0 break turned a
  single root-cause failure into "0 of 824 tests ran" because two
  module-level imports failed at collection time; this degrades that to
  "N passed, M errors" (still a non-zero exit) instead of masking the
  entire suite's results.
- New regression tests: `tests/test_lazy_loader_diagnostics.py` (loader
  diagnostics, failure caching, `list_tools` reachability) and
  `tests/test_dependency_bounds.py` (mcp major-version and upper-bound
  regression guards).
- Review trail for this investigation and fix is recorded under
  `specs/mcp2-compat/`.

### Fixed: unprotected mutating scripts returned an opaque error instead of guidance (#82)
- **`run_module` on any unprotected mutating script returned `'str' object has
  no attribute 'get'`** instead of the `unprotected_mutations_detected`
  guidance the preflight had already computed. The writeability gate worked
  correctly -- it detected the mutation and decided to reject -- but the
  handler crashed while *logging* that rejection, so the one message telling
  the caller how to fix their script (`wrap writes in if modifyAllowed:`) never
  arrived. Regression from `a449605` (2.7.x); affected every
  `write_enabled` / `confirmed` combination. `validate_only=True` was
  unaffected and was the workaround.
- **Root cause:** the per-issue DEBUG loop iterated `cert["raw_lcm_patterns"]`
  calling `p.get("line")`, but that list holds plain formatted strings
  (`"CREATE (Create())"`) extended from `detect_cud_operations()["operations"]`
  -- not the `{"line", "method", "context"}` dicts its sibling
  `unprotected_liblcm_calls` holds. Copy-paste from the immediately preceding
  loop, which uses the same field names correctly.
- **Structural hardening:** the reject diagnostics moved into
  `_log_writeability_reject()`, wrapped in a blanket `try/except`. This block
  is diagnostic-only -- it describes a rejection already decided -- so a future
  shape drift in any of the three lists now costs a log line rather than the
  tool result. Also closed a second latent path to the same symptom:
  `get_operations_logger()` is `Optional` and returns `None` before kernel
  init, which would have raised `'NoneType' object has no attribute 'info'` in
  place of the guidance.
- Regression coverage in `tests/test_issue82_writeability_reject_logging.py`,
  including the `raw_lcm_patterns`-is-strings shape contract, so a future
  change to that structure fails loudly instead of silently breaking the log.

## [2.9.0] - 2026-07-22

### Refresh always scans all APIs (per-library filter removed)
- **Removed `--flexicon-only` / `--flexlibs-only` / `--liblcm-only` from
  `refresh.py`.** Every run now scans all available APIs. The scans are
  cross-linked -- the reverse mapping annotates LibLCM entities with their
  FlexLibs/Flexicon wrappers (`python_wrappers`) and pattern extraction
  annotates Flexicon entities (`common_patterns`) -- so refreshing one library
  in isolation left the other libraries' cross-references stale. This regressed
  in 2.8.0, where a targeted `--flexicon-only` refresh silently dropped
  `python_wrappers` from 201 LibLCM entities and `common_patterns` from 9
  Flexicon entities. **Breaking:** any script or automation invoking those
  flags must drop them; the full refresh is the only mode.
- **LibLCM scanning is now best-effort.** A new `liblcm_scannable()` probe
  skips the LibLCM reflection scan (keeping the existing index) when FieldWorks
  DLLs / pythonnet are unavailable, instead of failing the whole refresh.
  Post-processing still re-applies the cross-link enrichment to the retained
  index.
- **Post-processing is no longer gated to full refreshes** (it never should
  have been). Reverse mapping, navigation graph, pattern extraction, and the
  casting index run after every scan; only `--skip-postprocess` suppresses them.
- **Server cold-start self-heal simplified** to trigger a single full refresh
  (the `_REFRESH_ATTEMPTED` dedup means one refresh covers all missing
  indexes). Stale `--*-only` guidance in the runtime version-mismatch warning,
  health warnings, and prefilled bug-report text was updated to the flagless
  command.

### New: `flextools-mcp-refresh` post-install warmup
- **Added the `flextools-mcp-refresh` console entry point**
  (`flextoolsmcp.refresh:main`). Wheels cannot run code at install time, so
  this is the reliable seam to warm the index right after install and avoid the
  server's first-run lazy-refresh delay: run it once after `pip install`, on
  the machine where the server will run. On Windows with FieldWorks it warms
  all three indexes to match the installed libraries; without FieldWorks /
  pythonnet the LibLCM scan is skipped gracefully and the shipped LibLCM index
  is kept.

### Indexes regenerated
- **All bundled indexes regenerated** with the cross-link enrichment restored:
  `python_wrappers` on 201 LibLCM entities, `common_patterns` on 9 Flexicon
  entities, navigation-graph relationships (325 entities), the casting index,
  and the semantic-search embeddings/FAISS index (3579 items).

### Docs & integrity
- Updated `CLAUDE.md`, `CONTRIBUTING.md`, `DEVELOPMENT.md`,
  `docs/VERSIONING.md`, `docs/workflow-detail.md`,
  `docs/workflow-detail-2-foundation.svg`, and `docs/STABILIZATION-STRATEGY.md`
  to the flagless refresh (with the cross-linked-scan rationale and LibLCM
  best-effort note) and to document `flextools-mcp-refresh` as the post-install
  warmup step.
- `scripts/validate_integrity.py` now asserts the removed per-library filter
  flags stay absent from `refresh.py --help`, guarding against reintroduction.

## [2.8.0] - 2026-07-22

### Flexicon 4.3.0 floor + index refresh
- **Minimum `pyflexicon` raised to `>=4.3.0,<5`** (`pyproject.toml`,
  `requirements.txt`). Upgrading FLExToolsMCP now re-resolves to a Flexicon
  that ships the GetAll() behavioral-collection contract by construction, so
  the flexicon-mode advisory removed below is correct for every supported
  install.
- **All bundled indexes regenerated** against the current sources:
  flexicon-mode API + LCM bridge (v4.3.0, sourced from the local clone on the
  dev machine), flexlibs-stable API + LCM bridge (v1.2.8), LibLCM API
  (v11.0.0), and the semantic-search embeddings/FAISS index (3579 items).

### GetAll() behavioral-collection contract (issue #37)
- **Flexicon-mode index regenerated to v4.3.0.** Flexicon 4.3.0 upgraded
  `EnumerableWrapper` (`flexicon/code/BaseOperations.py`, commit 205d5a9) to
  cache its materialized list on first access, so `.GetAll()` results now
  safely support `len()`, subscript/slice, and repeat iteration — a genuine
  behavioral collection, not a one-shot generator. Docs, worked examples, and
  curated recipes are reframed around this contract instead of the previous
  "materialize with `list(...)` to be safe" idiom.
- **Reverses the cycle-2 flexicon-mode overreach.** An earlier synthesis
  (`specs/getall-contract/SPEC.md`) proposed a Level-3 validator rule that
  flagged unsafe `GetAll()` idioms in flexicon mode, keyed off a
  reconciled `returns.type` container-shape taxonomy. That taxonomy is
  obsolete now that flexicon 4.3.0 makes the flexicon-mode result safe by
  construction; the flexicon-mode advisory has been removed.
- **Validator (`server/validators.py`) rescoped to `flexlibs_stable` mode
  only.** `detect_getall_unsafe_idiom` now flags raw one-shot
  iterators/generators in the stable FlexLibs API only (e.g.
  `LexiconAllEntries`, `LexiconAllEntriesSorted`, `ObjectsIn`,
  `GetLexicalRelationTypes`, `ReversalEntries`, `TextsGetAll`) via a
  hand-curated, docstring-sourced allowlist, and is silent in flexicon mode.
  Wired into `handlers/execution.py` alongside the other advisory detectors.
- **v4.2.1 index files archived**, still resolvable for projects pinned to
  older Flexicon versions (`src/flextoolsmcp/index/python/archive/`,
  `src/flextoolsmcp/index/archive/`).

## [2.7.0] - 2026-07-20

### Proactive update notice (issue #79)
- **The server now tells users when a newer `flextools-mcp` is on PyPI.**
  Neither `uvx`, `uv tool`, nor `pip` proactively notifies, so users got
  silently stuck on old builds — a stale `uvx` cache served a pre-2.6.2 build
  (Flexicon 4.1.2) even after 2.6.2 shipped, and a blanket `pip install -U`
  upgraded Flexicon but left the MCP behind. The notice rides out on the
  tool-response envelope as an optional `update_notice` block so the assistant
  relays it, with the correct upgrade command for each install method
  (`uvx flextools-mcp@latest` / `uv tool upgrade flextools-mcp` /
  `pip install -U flextools-mcp`).
- **Cheap and safe by construction.** The PyPI check is cached in
  `~/.flextoolsmcp/update-check.json` (~24h TTL) and runs on a background daemon
  thread; the tool-call path only reads the cache and never blocks on the
  network. Any failure fails open to no notice and never raises into the op
  path. Emitted at most once per process. Skipped for source/dev installs.
- **Opt-out:** set `FLEXTOOLSMCP_NO_UPDATE_CHECK=1` to disable entirely (no
  thread, no notice).
- Additive-optional envelope field — does **not** bump the tool contract
  (still `tool-responses/1.0`). Documented in
  [`docs/TOOL-CONTRACT.md`](docs/TOOL-CONTRACT.md#update_notice-advisory-block).

## [2.6.2] - 2026-07-20

### Raise the `pyflexicon` floor to 4.2.0
- **`pyflexicon` is now required at `>=4.2.0,<5`** (was `>=4.1,<5`). The bundled
  Flexicon API index and generated-script guidance track the 4.2.x surface, so
  the floor is raised to keep installs resolving to a matching library. Still a
  floor (not a pin), capped at the next major. Mirrored in `requirements.txt`.

## [2.6.1] - 2026-07-13

### Ship stable `flexlibs` as a runtime dependency
- **`flexlibs` (the shallow/stable cdfarrow wrapper) is now a declared
  dependency**, alongside `pyflexicon`. It is small and its only dependency
  (`pythonnet`) was already required, so bundling it costs little and means the
  stable-flexlibs index now matches the installed library out of the box (the
  bundled index is `flexlibs_api_v1.2.8` and PyPI `flexlibs` is 1.2.8). It also
  makes the runtime `--flexlibs-only` refresh path viable without a manual
  install, so the 2.6.0 version-mismatch handling can regenerate a matching
  index if the installed `flexlibs` ever drifts. Floor `>=1.2.8`, capped `<2`.
  Verified conflict-free: `flexlibs` and `pyflexicon` both require
  `pythonnet<3.1,>=3.0.3`, satisfied by our existing `pythonnet>=3.0.0`.
  Mirrored in `requirements.txt`.

## [2.6.0] - 2026-07-13

### Handle installed API versions that don't match the shipped index
- **Version mismatch now triggers a refresh-to-match, then a warned fallback.**
  `_load_library_api_index` previously only auto-refreshed when the index dir
  was *empty*; on a version mismatch it silently served the latest shipped
  index, so a user whose LibLCM / Flexicon / FlexLibs was newer *or* older than
  what shipped got a doc surface that didn't match their library, with no signal.
  Now, when no exact-version index exists for the detected installed version, the
  loader (1) attempts one refresh to regenerate a matching index from the
  installed library, and (2) if that can't reproduce it, serves the nearest
  shipped index but emits a WARNING naming the installed version, the served
  version, and the mismatch direction (older/newer), with the exact
  `python -m flextoolsmcp.refresh --<lib>-only` command to regenerate.
- **Refresh is attempted at most once per library per process** (`_REFRESH_ATTEMPTED`
  guard) so startup and repeated loads never shell out repeatedly when a user's
  version simply isn't reproducible on their machine (e.g. no FieldWorks DLLs for
  LibLCM). Refresh needs the extraction source — pyflexicon (always present),
  FieldWorks DLLs (LibLCM), or flexlibs — so it degrades gracefully to the warned
  fallback when the source is unreachable.
- **Fixed a latent cache bug on the refresh path.** `find_versioned_api_file`
  caches negative results, so the pre-existing "refresh then re-search" flow
  could return a stale `None` and fail to load a just-written index. The new
  `_try_refresh_once` clears the file-discovery cache after a successful refresh.
- New `tests/test_version_mismatch.py` covers exact match (no refresh), installed
  newer/older than shipped (both warning directions), refresh-regenerates-match,
  missing-entirely, the once-per-process guard, and crash-proof version parsing.

### Exclude index `archive/` from the built wheel (packaging)
- `include-package-data=true` + the `index/**/*` package-data glob swept the
  `archive/` subdirs (old index versions kept for local diffing) into the wheel;
  MANIFEST.in `prune` only trims the sdist. Added
  `[tool.setuptools.exclude-package-data]` so wheel and sdist both ship zero
  archive files while all live indexes remain.

## [2.5.0] - 2026-07-13

### Renamed the bundled Python-API index dir: `index/flexlibs` -> `index/python`
- **The folder held both wrapper libraries, so its name was misleading.**
  `src/flextoolsmcp/index/flexlibs/` contained the **Flexicon** index
  (`flexicon_api_v*`, `flexicon_lcm_bridge_v*`) *and* the **FlexLibs-stable**
  index (`flexlibs_api_v*`, `flexlibs_lcm_bridge_v*`). It is now
  `index/python/`, mirroring the sibling `index/liblcm/` (C#) — the taxonomy is
  now cleanly by source language: `python/` = the two Python wrappers, `liblcm/`
  = the C# API. All path references updated in `server.py` (API + LCM bridge
  loaders), `refresh.py`, `build_embeddings.py`, `build_reverse_mapping.py`,
  `extract_patterns.py`, `archive_old_versions.py`, plus `.gitignore`,
  `MANIFEST.in`, and the CI comment in `test.yml`.
- **Fixed `test_script_certification` to resolve the index like production.**
  It hardcoded the stale repo-root path `index/flexlibs/` (broken since the
  `src/` layout move), so all 21 of its cases errored locally with
  `FileNotFoundError` and were only green in CI because they're deselected via
  the `requires_flex` marker. It now uses `get_index_dir() / "python"`; the full
  suite is green locally (443 passed).

### Installation docs — uvx PATH troubleshooting
- **Documented the "`claude mcp add` succeeded but the server won't start"
  failure mode.** `claude mcp add` only *records* the launch command and reports
  success even when `uvx` is missing or not yet on PATH; the failure surfaces
  later, when the AI assistant tries to *launch* the server (it hangs, fails to
  connect, or shows no `flextools_*` tools). SETUP.md gains a prerequisite step
  to verify `uvx --version` in a **fresh** shell — the uv installer's PATH change
  does not reach already-open terminals or GUI apps until a new shell or reboot —
  an IMPORTANT callout at the quick-install step, and a Troubleshooting section
  covering uvx-not-found, the absolute-path fallback, and a uvx-free
  `pip install` + `python -m flextoolsmcp` alternative. README.md links to it.
- **Normalized package vs. server-alias naming.** Fixed four spots in README.md
  that passed the no-hyphen `flextoolsmcp` to `uvx`/`pip`/`uv tool`. The PyPI
  package is `flextools-mcp` (hyphenated); `flextoolsmcp` (no hyphen) is only the
  MCP server alias, the importable Python module, and the `~/.flextoolsmcp/` data
  directory.

### Inline casting metadata into get_object_api (issue #48)
- **Casting requirements now surface at discovery time.** Casting knowledge
  previously lived only in `flextools_resolve_property`, a tool the model
  reliably ignored (#22). `get_object_api` — the discovery gate's *required*
  step — now joins each property against the loaded casting index: properties
  that need a pythonnet cast gain `requires_cast` / `cast_to` / `cast_example`,
  polymorphic collections gain `polymorphic` / `iteration_note`, and a
  top-level `casting_notes` counter summarizes the entity. The model writes
  cast-correct code on the first draft instead of learning it from a rejection.
- **One vocabulary, taught earlier.** `cast_example` is produced by the same
  `_pick_cast_interface` + `_build_cast_rewrite` generator that powers
  `casting_issues[*].rewrite` (#21), so discovery-time guidance is
  byte-identical to what a preflight rejection would emit. The new
  `build_property_cast_example()` / `annotate_properties_with_casting()` helpers
  in `validators.py` are the shared join, called from both `paginate_entity`
  (get_object_api) and `_inline_discovery_docs` (discover-and-run rejections),
  keeping the two paths consistent.
- **No divergence, no bloat.** The annotation mirrors the rejection path's
  flow-independent skips (`Guid`/`Hvo`/`ClassID`/`ClassName` and multistring
  value accessors, #40) so it never re-introduces needless casts. Only
  index-member properties are annotated (entities with none come back
  byte-identical), and `summary_only` (#11) emits just the top-level counter.
- **resolve_property drops off the happy path.** Tool descriptions updated:
  `get_object_api` advertises the inline casting info; `resolve_property` is
  now scoped to chained/ambiguous receivers (`rewrite: null` cases) and
  debugging. New `tests/test_issue48_inline_casting.py` covers annotation,
  golden byte-identity, summary mode, safe-member parity, and the
  cast_example ↔ rewrite consistency contract.

## [2.4.0] - 2026-07-11

### MCP spec compliance — outputSchema (issue #54 follow-up)
- **Disabled the `outputSchema` advertisement in `list_tools()`.** The
  tool-responses/1.0 work wired `list_tools()` to advertise `outputSchema` for
  the three tools carrying an `output_model`, but `call_tool()` returns text-only
  (`json_response()` -> `[TextContent]`) and never populates `structuredContent`.
  Per MCP spec 2025-06-18, a tool advertising `outputSchema` MUST return matching
  `structuredContent`, and spec-compliant clients (e.g. Claude Code) reject
  text-only responses — so `run_module` / `get_object_api` / `search_by_capability`
  failed for those clients while all other tools worked. The advertisement is now
  commented out; `output_model` metadata is retained for the follow-up.
  `tests/test_response_contract.py::TestOutputSchema` inverted to guard that no
  tool advertises `outputSchema` until structured content is returned.
- **Operational note:** requires an MCP server **restart** to take effect (the
  running process does not hot-reload). Returning `structuredContent` so the
  schemas can be re-advertised is tracked in `docs/TODO.md` ("Option B"), scoped
  to the low-level `mcp` tuple return — NOT a FastMCP migration.

### Session identity + read-only auto-discovery (issues #42, #47)
- **#42 -- Session-state identity / discovery-state leak fixed**: `SessionState`
  is a long-lived global singleton; without an identity key it leaked discovery
  state across logical sessions. `session.py configure()` rewritten to branch on
  explicit `session_id` kwarg / `new_session=True` / first-configure /
  `project_name` change / else keep-current-no-wipe (project-anchored identity,
  `auto-<project|uuid>` minting). Fixes the P0 where the production start path
  minted a fresh uuid every call and wiped discovery on every `flextools_start`
  (broke the supported mid-session restart flow, issue #9). `admin.py` removes
  dead `session_state.session_id = ...` direct assignment; passes `project_name`
  through; adds unknown-kwarg warning guard. New `TestProductionPathSessionContinuity`
  covers the same-project-restart-preserves case that would have caught the P0.
  `#42.2` (missing Operation End on writeability reject) was already correct --
  locked with a regression test only.
- **#47 -- Read-only auto-discovery**: introduces a separate
  `auto_discovered_apis` set that the write gate never reads (write-gate
  isolation -- `validators.py:851` reads only `validated_apis`; write never
  auto-discovers). Resolve criterion uses the api_mode-specific entity table plus
  accessor-to-ops map (rejects naive `f"{name}Operations"` fallback). Cap 5 on
  read runs, 0 on write runs. Success path attaches Optional `auto_discovered` /
  `_inline_discovery` / `discovery_note` on `RunModuleSuccess`. The
  `KEY_INLINE_DISCOVERY = "_inline_discovery"` leading underscore is intentional:
  matches existing reject-payload `_inline_discovery`/`_assistance` keys that
  clients already parse.
- `docs/TOOL-CONTRACT.md` updated with the 3 new `RunModuleSuccess` Optional
  fields (`auto_discovered`, `_inline_discovery`, `discovery_note`).
- +26 tests (400 passed, 21 deselected). New `tests/test_issue42_session_identity.py`
  and `tests/test_issue47_auto_discovery.py`.

### Validator + auto-fix (issues #40, #46)
- **#40 — Casting whitelist false-positive fix**: `detect_casting_needs()` no
  longer over-rejects receivers whose var is a known cast-alias or a
  multistring-value accessor (`BestAnalysisAlternative`/`BestVernacularAlternative`/`.Text`),
  and never flags `project.*` wrapper calls. The advanced `casting_index` loop
  now consults `cast_aliases.get(obj_var)` against
  `_extract_interface_names(defined_on)` before flagging. Conditional-safe
  members (`LexemeFormOA`/`AnalysesRS`/`Wordform`/`Form`/`FreeTranslation`)
  pass only when a cast-alias proves the receiver type.
- **#46 — Fix-and-run auto-apply**: on read-only runs with `auto_fix` on, the
  preflight now auto-applies SAFE casting rewrites (exactly-one concrete target)
  and single-candidate typo corrections (difflib ratio >= 0.9), re-parses +
  re-runs the full preflight on the patched code, and executes in the same call,
  returning `auto_fixes_applied` + `auto_fix_note`. Write runs keep the hard
  rejection unconditionally. Cap of 5 fixes. New config kill switch
  `auto_fix_enabled`; `RunModuleInput.auto_fix` per-call override. Collision
  pre-pass rejects the whole fix set if any `(line, found_at)` key repeats.
- +5 tests (374 passed, 21 deselected). New `tests/test_auto_fix.py` covers
  re-parse-failure degradation, same-line collision rejection, and accumulator
  cap. 3 new golden response fixtures for auto-fix applied/not-applied paths.
  New `RunModuleSuccess` Optional keys (`auto_fixes_applied`, `auto_fix_note`)
  compose with the #54 contract.

### Tool contract (issue #54)
- **tool-responses/1.0 contract introduced**: all tool responses are now stamped
  with `_contract: "tool-responses/1.0"` and a unique `op_id`. Success responses
  carry a typed envelope; error responses carry flat canonical fields
  (`error_code`, `message`, `hint`, `error_details`) plus a per-code `detail`
  object validated against one of 16 Pydantic models.
- **outputSchema exposure — DEFERRED** (see "MCP spec compliance" below): the
  `output_model` metadata is retained on `ToolDef` for `run_module`,
  `get_object_api`, and `search_by_capability`, but the `list_tools()`
  advertisement of `outputSchema` is currently disabled. Advertising a schema
  without returning matching `structuredContent` breaks spec-compliant clients;
  re-enabling is tracked as a follow-up (docs/TODO.md, "Option B").
- **Dual-emit deprecation of nested `error{}` shape**: the legacy
  `error: {code, message, hint}` sub-object is still emitted alongside the
  new flat fields for backward compatibility. Scheduled for removal at
  `tool-responses/2.0`.
- New: `src/flextoolsmcp/server/response_models.py` (BaseEnvelope,
  RejectionEnvelope, 3 success models, 16 detail models, AnyDetail union,
  `validate_detail()`).
- New: `tests/test_response_contract.py` (94+ tests), 16 golden fixtures in
  `tests/golden/responses/`, `tests/make_golden.py` drift tooling.
- New: `docs/TOOL-CONTRACT.md` — full contract reference.

### Telemetry
- **First-pass-green metric now emitted** (issue #50): every `run_module`
  operation writes one JSONL line to `operations.jsonl` alongside the
  existing prose `operations.log`.  Fields include `ts`, `op_id`, `seq`,
  `project`, `write_enabled`, `source_kind`, `user_intent`, `code_sha256`,
  `code_bytes`, `code_lines`, `outcome` (ok / preflight_reject /
  runtime_fail / timeout), `error_code`, `preflight_gate`, `duration_s`,
  `auto_fixes_applied`, `auto_discovered`, `assistance_triggered`,
  `info_count`, `warning_count`, `error_count`.
- JSONL is written from inside the three close functions
  (`_log_operation_end_success`, `_log_operation_failure`,
  `_log_preflight_reject`) -- NOT at the ~12 individual call sites -- so the
  prose log and JSONL file can never diverge.
- `operations.jsonl` rotates at 10 000 lines to `operations.jsonl.1`.
- `get_operation_logs` statistics block now includes `first_pass_green_rate`,
  `turns_to_green_median`, and `rejects_by_error_code` (top 5) computed from
  JSONL.
- New CLI: `scripts/green_report.py` (stdlib only) -- reads one or more
  JSONL files, computes first-pass green rate, turns-to-green (median + p90),
  abandoned groups, retry-loop trips, and a reject-by-error-code table with
  optional `--previous` trend diff.  `--json` flag for CI integration.

### CI / Robustness (issue #57)
- **Added `.github/workflows/test.yml`**: runs on every push and pull_request.
  Windows-latest matrix over Python 3.10 and 3.12; steps are `pip install -e .[dev]`,
  `python scripts/validate_integrity.py all`,
  `pytest -m "not requires_flex" --cov=src/flextoolsmcp --cov=server --cov-fail-under=25`,
  and `ruff check .`.  A second job `test-linux` runs on `ubuntu-latest`
  (needs: test) with the same pytest surface.  Both jobs deselect
  `requires_flex` because GitHub runners have no FieldWorks install or
  generated Flexicon index.
- **Added `pytest-cov` and `ruff` to `[project.optional-dependencies] dev`** in
  `pyproject.toml` so `pip install -e .[dev]` sets up CI tooling in one step.
- **Fixed `tests/conftest.py`** path setup: added `src/flextoolsmcp/` to `sys.path`
  so legacy `from server.xxx import` statements resolve correctly alongside the
  installed `flextoolsmcp` package form.
- **Subprocess process-tree kill** (`server/subprocess_helpers.py`): on timeout,
  `run_script_async` now kills the entire process tree (`taskkill /T /F /PID` on
  Windows, `os.killpg` on POSIX) instead of only the immediate child.  Prevents
  grandchildren spawned by pythonnet / FLExInit from orphaning and holding
  `.fwdata` locks.  Regression test added: `tests/test_subprocess_tree_kill.py`
  (Windows-only, no live FLEx required).
- **Startup stale-lock sweep** (`server/project_discovery.sweep_stale_locks()`):
  at server startup, all `.fwdata.lock` files under the FieldWorks projects
  directory are logged at WARNING level and surfaced via `validate_server_state()`
  warnings; the `flextools_run_module` preflight health check picks them up.
  Detection only -- no deletion.  Tests in `tests/test_startup_lock_sweep.py`.
- **Added `requires_flex` pytest marker** in `pytest.ini`, applied to
  `test_script_certification.py` (needs a generated Flexicon index that CI
  runners lack) so both CI jobs deselect it with `-m "not requires_flex"`.
- **Fixed `src/flextoolsmcp/server/kernel.py` dual-import guard**: under the
  bare-`server` layout `__package__ == "server"` (truthy) wrongly took the
  relative-import branch, raising "attempted relative import beyond top-level
  package" and failing `test_undo_wiring.py` in CI.  Guarded with
  `__package__.startswith("flextoolsmcp")` so the relative branch is used only
  when installed as the package.
- **Repointed and un-quarantined `tests/test_mcp_tools.py`**: it loaded the
  pre-src-layout `src/server.py` via importlib; repointed to
  `src/flextoolsmcp/server.py` -- 18 tests now pass with no marker (the earlier
  `requires_flex` mark was masking a stale path, not a FieldWorks dependency).
- **Scoped ruff to fatal-only** via `[tool.ruff.lint] select = ["E9","F63","F7","F82"]`
  in `pyproject.toml` (matches the pre-commit hook); the incremental
  lint-widening in issue #57 part 2 broadens this set in follow-up PRs.
- Added `.coverage` and `htmlcov/` to `.gitignore`.

### Packaging / Policy (issue #57)
- Added `src/flextoolsmcp/py.typed` marker (PEP 561) and registered it in
  `[tool.setuptools.package-data]` so it ships inside the wheel.
- Capped `pyflexicon` at `>=4.1,<5` in `pyproject.toml` and `requirements.txt`
  to prevent silent breakage on a future major-version bump.
- Added `.github/dependabot.yml` for monthly Dependabot checks on
  `github-actions` and `pip` (dev dependencies).
- Added `SECURITY.md`: supported-versions table, private-report contact via
  GitHub Security Advisories, and explicit TRUST-MODEL statement clarifying
  that `write_enabled` gating is a safety feature (not a security boundary)
  and the server is intended for localhost/stdio use only.
- Added `CONTRIBUTING.md`: dev setup (`pip install -e .[dev]`),
  `pre-commit install`, refresh and test commands, and PR rules (CHANGELOG
  entry required; extractor changes need index diff; payload-shape changes
  need golden-file regen).
- Appended ROLLBACK PROCEDURE and PRE-RELEASE CHECKLIST sections to
  `RELEASING.md` (previously absent; flagged by STABILITY-SURVEY sec 5).

## [2.3.3] - 2026-07-06

### Index
- **Refreshed the Flexicon API index to v4.1.2** (v4.1.0 and v4.1.1 moved to
  `index/flexlibs/archive/`); regenerated the matching `common_patterns` and
  `flexicon_lcm_bridge` artifacts.
- **Refreshed the LibLCM v11.0.0 index**: added `PhonemeOperations` wrapper
  mappings and cleaned up stale `IDataReader` wrapper entries; regenerated the
  LibLCM reverse-mapping index.

### Internal
- Build scripts (`build_casting_index`, `build_navigation_graph`,
  `build_reverse_mapping`) now resolve their input/output locations via
  `get_index_dir()` instead of hardcoded package-relative paths, so they honor
  the user-overlay index directory.

## [2.3.2] - 2026-07-04

### Documentation
- Rewrote **SETUP.md** around the `uvx flextools-mcp` one-liner (source install
  kept as a dev option); fixed **README** update instructions and anchor links.
- Corrected commands and clarified the bundled-vs-`~/.flextoolsmcp/index` overlay
  location in **docs/VERSIONING.md**.
- Added an **INNOVATIONS.md** chapter on the zero-setup distribution and
  self-healing index overlay.
- Archived the historical v1.3.0 implementation plan to `docs/archive/`.

## [2.3.1] - 2026-07-04

### Packaging
- **Published to PyPI as `flextools-mcp`** — installable/runnable with a single
  `uvx flextools-mcp` (or `pip install flextools-mcp`); no clone or manual
  dependency install. The indexed API documentation ships inside the wheel as
  package data. Restructured to a `src/flextoolsmcp/` src-layout with a
  `pyproject.toml`, console-script entry points (`flextools-mcp` /
  `flextoolsmcp`), and a `python -m flextoolsmcp` module runner.
- **`pyflexicon` is now a runtime dependency**, so the deep FieldWorks wrapper
  is installed automatically and re-resolves to the latest on upgrade.
- **User-writable state consolidated under `~/.flextoolsmcp/`** (logs, saved
  skeletons, model cache, and runtime-refreshed indexes) so it persists across
  upgrades and is never written into the installed package. Runtime
  auto-refresh writes a user-overlay index seeded from the bundled one; source
  checkouts still refresh the in-tree index for committing.
- Added a tag-triggered GitHub Actions release workflow using PyPI Trusted
  Publishing (OIDC), plus `RELEASING.md`.

## [2.3.0] - 2026-07-04

### Changed
- **Renamed `flexlibs2` -> `flexicon`.** The deep wrapper is now the `flexicon`
  package, installed via `pip install pyflexicon` (imported as `flexicon`)
  instead of being cloned as a sibling repo. Updated across the MCP: analyzer
  module (`flexicon_analyzer.py`), index prefixes (`flexicon_api`,
  `flexicon_lcm_bridge`, `common_patterns_flexicon`), refresh CLI
  (`--flexicon-only` / `--flexicon-path`), the `FLEXICON_PATH` env var, and all
  templates/docs. The `api_mode` / `library` / template-flavor value is now
  `flexicon`; the previous `flexlibs2` value is still accepted as a **deprecated
  alias** (normalized to `flexicon`). Version detection now reads the
  `pyflexicon` distribution. Dated entries below retain their original
  `flexlibs2` naming for historical accuracy.

## [2.2.1] - 2026-07-01

June session-log triage follow-up: index freshness + discoverability.

### Features
- Canonical-intent map for `search_by_capability`: high-frequency intents now surface the exact flexlibs2 method as the top result instead of the assistant guessing nonexistent accessor/method names. E.g. "get sense part of speech" -> `LexSenseOperations.GetPartOfSpeechObject`, "list texts" -> `TextOperations.GetAll`, "wordform gloss" -> `WfiGlossOperations.GetForm`. Canonical hits are flagged (`canonical_intent`), counted (`canonical_matches`), and recorded so the same search also satisfies the discovery gate (#45)

### Fixes
- Library version detection now honors a live module `version` attribute (flexlibs2's convention), preferring it over stale `importlib.metadata`. Previously the server detected 3.0.0 from pip metadata while flexlibs2 4.0.1 was on the path, so it loaded a mismatched (archived) index and false-rejected valid code such as `ApplySyncableProperties` (#38)
- Reindexed flexlibs2 to v4.0.1 so recently-added methods (`ApplySyncableProperties` on all 13+ Operations classes, etc.) are present in the API index (#38)

### Tests
- Reconciled a stale #20 test with #31's implicit-discovery behavior (`from flexlibs2 import X` counts as discovery)

## [2.2.0] - 2026-06-30

Follow-up release from the June session-log audit: a validator-cluster fix pass (#39-#45 triage), the #16/#30-#36 batch, plus shared-mode, indexing, and session-header improvements.

### Features
- `report.Result(data)` for structured payload return from user scripts (1 MB cap, JSON-validated, distinct sentinel) (#35)
- Expose `lcm_undoable_action_count` after write-enabled runs so callers can see how many actions the UoW actually committed (#16)

### Fixes
- Casting gate no longer over-rejects safe read-only access: whitelist universally-safe members (`Guid`/`Hvo`/`ClassID`/`ClassName`), skip method calls on Operations-class aliases (`segOps.IsLabel(seg)`), and normalize the cast-alias `defined_on` check so a cast satisfies the property even with a descriptive `"(raw LCM)"` qualifier (#40)
- Missing-imports gate is now AST-based, so parenthesized / multi-line `from flexlibs2 import (...)` no longer false-rejects (#41)
- Attribute typos prefer Python's authoritative `Did you mean: 'X'?` suggestion (surfaced as `did_you_mean`) instead of routing through the cast path with an unactionable "resubmit" hint (e.g. `ILexDb.EntriesOC` -> `Entries`) (#39)
- Writeability preflight reports a consistent mutation total: a raw `set_String` now counts toward `mutating` instead of logging the self-contradictory `mutating=0 ... raw_lcm=1` (#44)
- `unprotected_writes` no longer false-positives on `Get*`/`Find*`/`Is*`/`Has*`/`Count*`/`Contains*` methods absent from the API index (#32)
- Fuzzy validator replaces the blanket `Lexicon*` skip with an enumerated method set from the FLExProject index, so typos like `LexiconGetSenses` still get caught (#34)
- Casting typed-receiver hint extended to `_obj`/`_typed`/`_cast` variable-name variants (#30)
- `undiscovered_entity` no longer rejects operations classes on a fresh session when they are explicitly imported (`from flexlibs2 import X` treated as implicit discovery) (#31)
- Runtime `PolymorphicAttributeError` embeds the resolved cast `rewrite` + `imports_needed`, matching the preflight payload (#36)
- Read-only operations are allowed on FLEx-open projects (shared mode): the `.fwdata.lock` preflight gates on write intent only, letting LCM arbitrate concurrent reads; exclusive writes still fail fast (#33)
- Enhanced domain and search synonyms for inflection and related terms

### Performance
- `get_object_api` thin-indexes Operations classes: returns name/signature/one-line description by default (full bodies still returned when `method_filter` narrows the request)

### Observability
- Session header now populates the FlexToolsMCP version (from the repo `VERSION` file) and the LibLCM version (read from `SIL.LCModel.dll` on disk), instead of logging `(unknown)` when run from source

## [2.1.0] - 2026-05-30

Coverage-test post-mortem follow-up: 13 issues (#17-#29) opened from the May 22 session-log audit, all landed. Three follow-up corrections from lex-domain review also included, plus a late-cycle Seth-session false-positive fix and a logging-gap audit pass.

### Features
- Capture `user_intent` on `run_module` / `start_module`; echo into operations log (#18)
- Skeleton storage closet -- auto-capture working helpers, retrieve via `find_examples` + new `list_skeletons` tool (#24)
- Cap `report.Info` messages at 100 (first-50 / last-50 slice + truncation marker) (#25)
- Detect retry loops and code-size oscillation; surface `_assistance` hint on rejections (#28)
- Inline `get_object_api` summary on `api_discovery_required` rejections (#29)
- Inline cast rewrite + `KernelInterfaces` import on `casting_issues_detected` rejections (#21)

### Fixes
- Surface operation failures at ERROR, preflight rejects at WARNING (#17)
- `[TOOL CALL]` always reaches cross-session `operations.log`; `[TOOL ARGS]` demoted to INFO (#19)
- Clarify `undiscovered_entity` rejection when entity is explicitly imported; inline discovery payload (#20)
- Drop alphabetical tie-break for ambiguous cast targets -- route to manual `resolve_property` (#21 follow-up)
- Retarget polymorphic hint at inlined rewrite, not external `resolve_property` (#22)
- Diagnose SharedSettings / path-mismatch errors against discovered project list (#23)
- Surface `project_locked` with close-FieldWorks hint; correct exception class to `LcmFileLockedException` and FW9 lock-file location (#27)
- Retry-loop assistance hint now points at #21 inlined rewrite, not `resolve_property` (#28 follow-up)
- Casting validator skips mid-chain segments rooted at a typed receiver -- eliminates the `wf.Form.BestVernacularAlternative` and `IWfiWordform(ana).Form.BestVernacularAlternative` false positives surfaced in Seth's 2026-05-28 session

### Observability
- Writeability rejects log per-issue DEBUG (mutating calls / unprotected LCM / raw LCM patterns with line + context), mirroring the casting-reject log pattern
- Close logging gaps so every `error_response` in `handle_run_module` is preceded by either `_log_preflight_reject` (in-op) or `[PRE-OP REJECT]` WARN (pre-op-id rejections like `project_name_required` / fuzzy-resolve failure)
- `handle_list_skeletons` storage failure now logs at ERROR with `exc_info`, not just packed into JSON
- Silent `list_projects()` failure inside the path-failed diagnostic now WARNs so the operator can tell discovery-failed from no-projects-nearby

### Docs
- Relax module-template mandate; bare snippets are first-class (#26)
- Reword `undiscovered_entity` message ("loaded" not "validated") (#20 follow-up)

## [2.0.0] - 2026-04-07

### Major Features
- **Async-first MCP Architecture**: Complete async implementation for concurrent tool execution
- **FlexLibs2 v3.0.0 Integration**: Deep wrapper support with 90% API coverage
- **LibLCM v11.0.0 Support**: Current version of FieldWorks library bindings
- **Session-based Configuration**: Persistent state management across tool calls
- **Structured Script Certification**: Validate FLExTools scripts before execution

### Code Consolidations & Improvements

#### Core Analyzer Modules
- Eliminated duplicate `infer_output_behavior_lcm()` function (-83 LOC)
- Pre-compiled regex patterns in docstring parsing (5-10% faster)
- Eliminated duplicate AST parsing in FlexLibs stable analysis (~2x faster)
- Merged dual entity iterations in refresh pipeline (O(2n) → O(n))
- Consolidated 52 API categorization constants to shared module

#### Handler Architecture Unification
- Created `response_keys.py` module for centralized response field constants
- Unified `json_response()` helper across all handlers
- Removed duplicate KEY_* constant definitions across handler modules
- Consolidated response formatting patterns

#### Performance Optimizations
- Cached version detection in server startup
- Optimized entity iteration patterns
- Pre-compiled regex patterns for docstring extraction
- Lazy-loaded pattern analyzers

### Bug Fixes
- Fixed duplicate @OperationsMethod decorators in FlexLibs2 (6 methods)
- Fixed undefined KEY_LIMIT and KEY_OFFSET constants
- Improved error handling in PropertyResolver
- Enhanced session state reset for clean test isolation

### Testing
- Added comprehensive validator tests (25+ new tests)
- Improved test fixture consolidation
- Added AST pattern visitor for complex analysis
- Enhanced test isolation with reset_session_state fixture

### Documentation
- Updated FLEXTOOLS-STYLE-GUIDE.md with best practices
- Added API versioning documentation
- Documented safe write guard patterns for user scripts

### Migration Notes
- **Breaking Change**: FlexLibs2 v2.0+ scripts need explicit imports (see CLAUDE.md)
- API response structure unchanged - backward compatible
- Session initialization now required before tool calls (already implemented)

### Known Limitations
- LibLCM reflection requires pythonnet on Windows
- Write operations serialize at project level (by design)
- Session state not persisted across CLI invocations
