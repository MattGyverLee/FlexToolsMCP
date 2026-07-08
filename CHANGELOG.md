# FlexToolsMCP Changelog

## [Unreleased] - 2026-07-07

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
- **outputSchema exposure in list_tools()**: tools that declare an
  `output_model` now emit a JSON Schema `outputSchema` field in `list_tools`
  (Pydantic `by_alias` serialization). Covered tools: `run_module`,
  `get_object_api`, `search_by_capability`.
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
