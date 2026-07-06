# FlexToolsMCP Changelog

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
