# Tasks: Unified recipes

**Input**: `specs/unified-recipes/plan.md`, `spec.md`, `research.md` (R1..R18),
`data-model.md`, `contracts/tools.md`, `raw-lcm-ledger.md`
**Size**: oversized (full phased list) | **Write path**: yes (Sena 3 only)

**Tests**: included. The plan's Test map pairs every FR with a test; write
each story's tests first and confirm they fail before implementing.
Run suites with `.venv\Scripts\python -m pytest -q -m "not requires_flex" <path> | tail -20`.

**Format**: `- [ ] **T###** [P?] [US#] Description · file`
`[P]` = independent within its wave (different file, no incomplete
dependency). All implementation happens in the `feat/unified-recipes`
worktree (R16).

**Live-write rule**: any task marked **(live)** performs a live write on
Sena 3, the designated test project. Unattended runs perform it (constitution
I, Sena 3 exception): assert the project is `Sena 3`, dry-run first, touch
only `zzRecipeTest` objects, clean up in the same session, and record pre/post
evidence (R14). No task ever targets Claude-Swahili; a live write that would
need any other project stops as `needs-human`. Every run goes through
`flextools_run_module`, never a direct `FLExProject` open (R14).

---

## Phase 1: Setup

**Wave 1 (single):**

- [x] **T001** Rebase `feat/unified-recipes` onto `main` (5cc03f0), copy the current `specs/unified-recipes/` artifacts from the main checkout into the worktree, and record a green baseline with `.venv\Scripts\python -m pytest -q -m "not requires_flex"` (R16) · worktree root, `specs/unified-recipes/`

**⟶ Wait for Wave 1 to finish, then:**

**Wave 2 (independent, different files):**

- [x] **T002** [P] Add `recipe_library/*.py` to package data, add the `flextools-mcp-recipe = "flextoolsmcp.recipe_cli:main"` console script, and add `recipe_library` to the ruff exclude (FR-005, FR-030) · `pyproject.toml`
- [x] **T003** [P] Add `graft src/flextoolsmcp/recipe_library` (FR-005) · `MANIFEST.in`
- [x] **T004** [P] Exclude `src/flextoolsmcp/recipe_library` from pyright (FR-005) · `pyrightconfig.json`
- [x] **T005** [P] Create the empty `recipe_library/` data directory (not a package, so no `__init__.py`; R2) and `evidence/README.md` (the evidence protocol from R14, plus a deferred-recipes table) · `src/flextoolsmcp/recipe_library/`, `specs/unified-recipes/evidence/README.md`

---

## Phase 2: Foundational (blocks every story)

The shared recipe-file format, the merge into `CURATED_RECIPES`, and the
response-key registry. No story work starts until this phase is done.

### Tests (write first; they must fail)

**Wave 1 (independent):**

- [x] **T006** [P] Loader tests: header parse (JSON and string values, continuation lines), `code` excludes the docstring, PARAMS with trailing, above-line and inside-value comments, multi-line defaults, missing block gives `[]`, malformed file skipped with one error naming the file and key, `test_file_recipes_merged_into_curated`, `test_id_collision_raises` (file vs file, file vs dict), `test_library_is_package_data` via `importlib.resources` (FR-001..005) · `tests/test_recipe_files.py`
- [x] **T007** [P] `test_verified_version_matches_index_target`: `FLEXICON_VERIFIED_VERSION` equals the flexicon version of the loaded index file (FR-006) · `tests/test_recipes.py`

### Implementation

**⟶ Wait for the tests wave, then Wave 2 (independent):**

- [x] **T008** [P] Build `recipe_files.py`: header parser (R3), PARAMS parser via tokenize/AST (R4), `load_recipe_library()` over `importlib.resources` (R2), malformed-file skip vs collision raise (R5), `code_terms` extraction with camelCase/underscore split and alias table (R10), shared scrub patterns (GUID, `[A-Za-z]:\\Users\\`, forbidden names), and the draft renderer used by promote (R13). Files are parsed statically, never executed (FR-001..003) · `src/flextoolsmcp/recipe_files.py`
- [x] **T009** [P] Add `KEY_RECIPES`, `KEY_RECIPES_COUNT`, `KEY_RECIPE`, `KEY_RECIPES_AMBIGUOUS`, `KEY_RECIPES_HINT`, `KEY_DEPRECATION`, `KEY_SKELETONS_FROM_YOUR_SESSIONS` and export them in `__all__` (contracts section 6) · `src/flextoolsmcp/server/response_keys.py`

**⟶ Wait for Wave 2, then Wave 3 (independent):**

- [x] **T010** [P] Merge `load_recipe_library()` into `CURATED_RECIPES` with an import-time collision raise, and set `FLEXICON_VERIFIED_VERSION = "4.11.0"` (FR-004, FR-006) · `src/flextoolsmcp/curated_recipes.py`
- [x] **T011** [P] Seed recipe `parser-coverage` ported to flexicon 4.11.0 from MCPlayground `candidates.py`, with a full header and PARAMS block (`COUNT`), to exercise the path end to end. Sena 3 verification is T041 · `src/flextoolsmcp/recipe_library/parser-coverage.py`

**Checkpoint**: T006/T007 pass; `CURATED_RECIPES` holds the 24 dict recipes plus `parser-coverage`; the existing suite stays green.

---

## Phase 3: User Story 1 — Search finds a working recipe (P1, MVP)

**Goal**: `search_by_capability` returns a ranked `recipes` list; a clear winner carries code and params; `results[0].recipe` is unchanged.

**Independent Test**: With the dict recipes plus the seed recipe, run the query battery through `search_by_capability` and check the expected recipe is in the top 3 for at least 90% of queries.

### Tests (write first; they must fail)

**Wave 1 (independent):**

- [x] **T012** [P] [US1] Ranking tests: normalization (case, punctuation, plural), bag weights (task word > code word > object word on crafted fixtures), IDF (a word in every fixture recipe contributes about 0), `code_terms` + alias table (`PhoneEnvRC` gives phone + environment), shipped and `use_count` boosts, null-intent penalty, "frobnicate the widgets" returns `[]`; response tests `test_search_response_recipes_keys`, `test_clear_winner_gets_code`, `test_object_only_query_no_code`, `test_close_scores_no_code`, `test_no_duplicate_code_with_legacy_attachment` (`code_at`), `test_hint_present_iff_ambiguous`, `test_top_row_records_validated_compact_rows_do_not`, `test_compact_row_size_budget` (mean < 400 chars), `test_battery_at_most_one_code_body`; `QUERY_BATTERY` (at least 20 entries, including the US1 acceptance queries) with `test_battery_top3_rate >= 0.9`. Battery entries whose recipe lands in Phase 5 are marked and skipped until it exists (FR-020, FR-021, FR-026, FR-061, SC-001, SC-005) · `tests/test_recipe_search.py`
- [x] **T013** [P] [US1] `test_attachment_identical_to_pre_change`: frozen `results[0].recipe` dict for "list all entries with their glosses" (FR-022) · `tests/test_recipes.py`
- [x] **T014** [P] [US1] Server-instructions round trip under the installed mcp: instructions carry the "check `recipes` first", PARAMS and `source="existing"` guidance (FR-027) · `tests/test_server_instructions.py`

### Implementation

**⟶ Wait for the tests wave, then Wave 2 (single):**

- [x] **T015** [US1] Unified ranked search in `server/recipes.py`: normalize both sources to the internal Recipe shape (data-model section 1), weighted bags, IDF over the recipe set, boosts, null-intent penalty, the clear-winner gate (minimum score, 1.5x the runner-up, not objects-only), compact vs full row shapes, and a pluggable local-recipe provider (empty until US2). Keep the old `results[0].recipe` attachment function separate and untouched (R10) · `src/flextoolsmcp/server/recipes.py`

**⟶ Wait for Wave 2, then Wave 3 (independent):**

- [x] **T016** [P] [US1] `handle_search_by_capability`: add `recipes`, `recipes_count`, `recipes_ambiguous` and the hint; set `code_at: "results[0].recipe"` when the winner is already attached; record only the served top row's entities as validated (FR-021, FR-022, FR-026) · `src/flextoolsmcp/server/handlers/api.py`
- [x] **T017** [P] [US1] Add `SERVER_INSTRUCTIONS` (R11) and update the `search_by_capability` / `run_module` descriptions to say "check `recipes` before composing code; edit PARAMS values only; run with `source="existing"` when only PARAMS changed" (FR-027) · `src/flextoolsmcp/server/tool_definitions.py`

**⟶ Wait for Wave 3, then Wave 4 (single):**

- [x] **T018** [US1] Pass `instructions=SERVER_INSTRUCTIONS` to `build_server`, compatible with mcp 1.x and 2.x through the compat shim (FR-027) · `src/flextoolsmcp/server.py`

**Checkpoint**: T012..T014 pass on the current recipe set (Phase 5 battery entries skipped); US1 acceptance 1..5 hold for recipes that exist.

---

## Phase 4: User Story 2 — The MCP remembers what worked for this user (P1)

**Goal**: A successful run with `user_intent` is captured whole as one local recipe, deduplicated by fingerprint, and findable by search and `find_examples` after a restart.

**Independent Test**: Run a successful snippet with `user_intent`, reload the store in a new process, search a paraphrase, and get the local recipe with its full code.

### Tests (write first; they must fail)

**Wave 1 (independent):**

- [x] **T019** [P] [US2] Port `test_skeleton_storage.py` into `test_local_recipes.py` and add: path resolution (`FLEXTOOLSMCP_RECIPE_DIR`, the `FLEXTOOLSMCP_SKELETON_DIR` fallback, default); `test_record_fields`; `test_entities_from_this_code_only`; `test_repeat_updates_not_duplicates` (comment and whitespace variants); `test_op_ids_capped_at_5`; `test_projects_union`; `test_capture_never_raises`; `test_legacy_migration_*` (grouping by op_id, intent from the ops log, trivial/short bodies dropped, duplicates merged, legacy bytes hash-unchanged, missing ops log gives null intent); `test_migration_shrinks_fixture` (309-row-shaped fixture, at least 50% smaller); `test_cap_2000_drops_least_used_oldest`; `test_paraphrase_finds_local_after_restart` (FR-010..016, SC-002, SC-004) · `tests/test_local_recipes.py`
- [x] **T020** [P] [US2] Handler-level capture tests through `handle_run_module` with a stub executor: captured with intent and at least 4 real lines; not captured for a 2-line probe, an empty intent, or a failed run; `requires_write` only when write-enabled and mutating (FR-011, FR-012) · `tests/test_local_recipe_capture.py`
- [x] **T021** [P] [US2] `test_find_examples_includes_local`, `test_skeletons_key_still_emitted_with_deprecation` (FR-023) · `tests/test_recipe_search.py`

### Implementation

**⟶ Wait for the tests wave, then Wave 2 (single):**

- [x] **T022** [US2] Build `server/local_recipes.py`: store path resolution, fingerprint (comments and blank lines removed, whitespace normalized), capture with upsert (`use_count`, `last_used`, `op_ids` last 5, `projects` union), entities from this code's AST via `validators._accessor_to_ops_map` plus `I*` names (R8), atomic rewrite with `os.replace`, UTF-8 JSONL with `ensure_ascii=False`, 2,000-row cap, one-time legacy migration from `skeletons.jsonl` with intent recovery from `logs/operations.jsonl` (R7, R9), never raises (FR-010..016) · `src/flextoolsmcp/server/local_recipes.py`

**⟶ Wait for Wave 2, then Wave 3 (independent):**

- [x] **T023** [P] [US2] Rewire capture: pass the whole code, `user_intent`, project name and `is_mutating_script` to `local_recipes.capture`; remove per-`def` capture and `_entities_used_in_session` (FR-011, FR-012) · `src/flextoolsmcp/server/handlers/execution.py`
- [x] **T024** [P] [US2] Plug `local_recipes` into the ranker's local provider (T015 seam) · `src/flextoolsmcp/server/recipes.py`

**⟶ Wait for Wave 3, then Wave 4 (independent):**

- [x] **T025** [P] [US2] `handle_find_examples`: add matching local recipes to the existing `recipes` list; keep emitting `skeletons_from_your_sessions` with a `deprecation` notice naming `tool-responses/2.0` (FR-023) · `src/flextoolsmcp/server/handlers/api.py`
- [x] **T026** [P] [US2] Delete `server/skeleton_storage.py` and `tests/test_skeleton_storage.py`; repoint every remaining import to `local_recipes` (Grep for `skeleton_storage`) · `src/flextoolsmcp/server/skeleton_storage.py`, `tests/test_skeleton_storage.py`
- [x] **T027** [P] [US2] Fix the stale skeleton-closet comment · `src/flextoolsmcp/file_utils.py`

**⟶ Wait for Wave 4, then Wave 5 (single):**

- [x] **T028** [US2] Pattern audit (sweep-pattern skill) for the shaped bug "provenance taken from the ambient session instead of the artifact": check at least `op_telemetry` `auto_discovered` and the `extract_patterns` mining evidence; write the sibling list into `evidence/pattern-audit.md` for the PR body · `specs/unified-recipes/evidence/pattern-audit.md`

**Checkpoint**: T019..T021 pass; US2 acceptance 1..4 hold; the US1 tests still pass with local recipes included.

---

## Phase 5: User Story 3 — A shipped library of real grammar and lexicon recipes (P1)

**Goal**: At least 12 of the 16 FR-050 recipes ship, each validator-green (including the raw-LCM gate) and verified on Sena 3 with recorded evidence.

**Independent Test**: CI validator passes over the shipped set; each read recipe runs unchanged on Sena 3; each write recipe dry-runs on Sena 3 and reports its intended changes.

### Tests (write first; they must fail)

**Wave 1 (independent):**

- [x] **T029** [P] [US3] Validator tests: a bad PARAMS block, an unguarded write, `DoNotUseForParsing`, a GUID, a user path, and `Claude-Swahili` / `Target` defaults each fail; a `print` call fails (`detect_print_calls`); the shipped set passes (`test_all_curated_recipes_pass_preflight` now covers file recipes); `test_shipped_file_recipes_have_sena3_verification`; `test_first_batch_count` (at least 12 of the 16 ids); `test_vernacular_recipes_normalize` (FR-040, FR-041, FR-044, FR-050..053, SC-003) · `tests/test_recipes.py`
- [x] **T030** [P] [US3] Index-driven deprecation: a seeded recipe calling an index-deprecated flexicon method fails through `validate_recipe`; the run-time preflight (no `api_index`) is unchanged (FR-041, R17) · `tests/test_validators_deprecation_index.py`
- [x] **T031** [P] [US3] Raw-LCM gate: `PhoneEnvRC` with no note fails and names `AllomorphOperations.GetPhoneEnv`; an unwrapped property fails without a note and passes with `# flexicon gap: #NNN` or `# raw-lcm: reason`; `raw-lcm:` overrides a wrapper suggestion; `Duplicate` / `Delete` are never suggested; interface cast, `project.project`, `ServiceLocator` and `ClassName` comparison are each flagged; count above `raw_lcm_lines` fails and below passes; bridge inversion tested against the real 4.11.0 bridge file (FR-045, R18) · `tests/test_raw_lcm_gate.py`

### Implementation: validator

**⟶ Wait for the tests wave, then Wave 2 (single):**

- [x] **T032** [US3] `detect_deprecated_members(api_index=...)` reading index deprecation markers (R17); `detect_raw_lcm_access` plus the bridge-index inversion for wrapper suggestions (R18) · `src/flextoolsmcp/server/validators.py`

**⟶ Wait for Wave 2, then Wave 3 (single):**

- [x] **T033** [US3] Extend `validate_recipe` with a `shipped=True` flag: PARAMS parses, `if modifyAllowed:` guard for `requires_write`, index-driven deprecation, scrub patterns from `recipe_files`, `detect_print_calls`, the raw-LCM gate and the `raw_lcm_lines` ratchet (FR-040, FR-041, FR-045) · `src/flextoolsmcp/recipe_validator.py`

### Implementation: recipe batch

Each recipe task: port to flexicon 4.11.0 (cite the `get_object_api` / `search_by_capability` calls used, R15), get the validator green, run on Sena 3 (assert the project name via `flextools_list_projects` first), record `.fwdata` SHA-256 and mtime before and after every run, write `evidence/<id>.md`, then set `verified_against` and `raw_lcm_lines`. Evidence and recipe files are per-recipe, so each task is independent. Ledger updates are batched into the join tasks, because `raw-lcm-ledger.md` is shared.

**⟶ Wait for Wave 3, then Wave 4 — read recipes (independent):**

- [x] **T034** [P] [US3] `lexicon-form-lookup` (NFC on both sides; US3 acceptance 2) from `lexicon_lookup.py` · `src/flextoolsmcp/recipe_library/lexicon-form-lookup.py`, `specs/unified-recipes/evidence/lexicon-form-lookup.md`
- [x] **T035** [P] [US3] `entry-parser-detail` from `entry_detail.py` · `src/flextoolsmcp/recipe_library/entry-parser-detail.py`, `specs/unified-recipes/evidence/entry-parser-detail.md`
- [x] **T036** [P] [US3] `wordform-analyses` from `wordform_analyses.py` · `src/flextoolsmcp/recipe_library/wordform-analyses.py`, `specs/unified-recipes/evidence/wordform-analyses.md`
- [x] **T037** [P] [US3] `form-usage-before-edit` from `allomorph_refs.py` · `src/flextoolsmcp/recipe_library/form-usage-before-edit.py`, `specs/unified-recipes/evidence/form-usage-before-edit.md`
- [x] **T038** [P] [US3] `affix-templates-and-slots` from `templates_slots_envs.py` (note: don't cast flexicon wrappers such as `AffixTemplate` to LCM interfaces) · `src/flextoolsmcp/recipe_library/affix-templates-and-slots.py`, `specs/unified-recipes/evidence/affix-templates-and-slots.md`
- [x] **T039** [P] [US3] `phonological-rules` from `phon_rules.py` (known flexicon gap: raw LCM with a filed-issue note, or defer per FR-052) · `src/flextoolsmcp/recipe_library/phonological-rules.py`, `specs/unified-recipes/evidence/phonological-rules.md`
- [x] **T040** [P] [US3] `wordform-case-variants` from `find_variants.py` · `src/flextoolsmcp/recipe_library/wordform-case-variants.py`, `specs/unified-recipes/evidence/wordform-case-variants.md`
- [x] **T041** [P] [US3] Verify the seed `parser-coverage` on Sena 3 and record evidence (the file itself is T011) · `src/flextoolsmcp/recipe_library/parser-coverage.py`, `specs/unified-recipes/evidence/parser-coverage.md`

**⟶ Wait for Wave 4, then Wave 5 (single):**

- [x] **T042** [US3] Ledger join for the read recipes: move relied-on rewrite rows to `confirmed`, add new rows, and file a `MattGyverLee/flexicon` issue for every kept gap (no `TODO-file` rows for a shipped recipe) · `specs/unified-recipes/raw-lcm-ledger.md`

**⟶ Then Wave 6 — write recipes (independent; dry run for each, live write (live) for the ones that create objects):**

- [x] **T043** [P] [US3] `create-entries-idempotent` from `w_create_entries.py` (validate every POS before any write; skip existing lf+gloss+POS). Dry run + live write **(live)** with `zzRecipeTest` objects and cleanup · `src/flextoolsmcp/recipe_library/create-entries-idempotent.py`, `specs/unified-recipes/evidence/create-entries-idempotent.md`
- [x] **T044** [P] [US3] `create-entry-like-comparator` from `w_create_stem_like.py` (restore `InflectionClassRA` after `SetStemMsaPos`). Dry run + live write **(live)** · `src/flextoolsmcp/recipe_library/create-entry-like-comparator.py`, `specs/unified-recipes/evidence/create-entry-like-comparator.md`
- [x] **T045** [P] [US3] `set-allomorph-environments` from `w_set_allomorph_env.py` (existing environments only). Dry run · `src/flextoolsmcp/recipe_library/set-allomorph-environments.py`, `specs/unified-recipes/evidence/set-allomorph-environments.md`
- [x] **T046** [P] [US3] `add-inflectional-affix` from `w_add_affix.py`. Dry run + live write **(live)** · `src/flextoolsmcp/recipe_library/add-inflectional-affix.py`, `specs/unified-recipes/evidence/add-inflectional-affix.md`
- [x] **T047** [P] [US3] `add-allomorph` from `w_add_allomorph.py`. Dry run + live write **(live)** · `src/flextoolsmcp/recipe_library/add-allomorph.py`, `specs/unified-recipes/evidence/add-allomorph.md`
- [x] **T048** [P] [US3] `create-text-from-lines` from logs (Ron): one paragraph per line; warn if the title exists rather than delete-and-recreate. Dry run + live write **(live)**; add its ledger rows in T051 · `src/flextoolsmcp/recipe_library/create-text-from-lines.py`, `specs/unified-recipes/evidence/create-text-from-lines.md`
- [x] **T049** [P] [US3] `create-variant-entries` from logs (Ron). Dry run + live write **(live)** · `src/flextoolsmcp/recipe_library/create-variant-entries.py`, `specs/unified-recipes/evidence/create-variant-entries.md`
- [x] **T050** [P] [US3] `affix-template-setup` from developer op `op-142307019-033`: POS subcategory, template, existing slots, repoint stem MSAs restoring inflection class. Dry run + live write **(live)** · `src/flextoolsmcp/recipe_library/affix-template-setup.py`, `specs/unified-recipes/evidence/affix-template-setup.md`

**⟶ Wait for Wave 6, then Wave 7 (single):**

- [x] **T051** [US3] Ledger join for the write recipes (rows for recipes 14..16 added; every kept gap has an issue number), and list any deferred recipe with its blocking issue in `evidence/README.md` (FR-052). Confirm at least 12 of the 16 shipped · `specs/unified-recipes/raw-lcm-ledger.md`, `specs/unified-recipes/evidence/README.md`

**Checkpoint**: T029..T031 pass over the shipped set; at least 12 recipes have Sena 3 evidence; US3 acceptance 1..3 hold. Re-run T012 with the Phase 5 battery entries unskipped (the battery must now hit at least 90%).

---

## Phase 6: User Story 4 — Browse what recipes exist (P2)

**Goal**: `flextools_list_recipes` lists compact rows with filters and returns one full recipe by id; `flextools_list_skeletons` is a deprecated alias.

**Independent Test**: Call the tool with each filter and with `recipe_id`; check shapes, and that no row carries code unless `recipe_id` is given.

### Tests (write first; they must fail)

**Wave 1 (independent):**

- [x] **T052** [P] [US4] Each `source`, `requires_write`, `limit` clamp, `query` ordering, shipped-first default order, `recipe_id` returns the full recipe, no `code` without `recipe_id`, `recipe_not_found` shape and field order with `closest_matches`, `test_recipe_id_records_validated`, `test_list_skeletons_alias_shape_and_deprecation` (FR-024..026) · `tests/test_list_recipes.py`
- [x] **T053** [P] [US4] Add `flextools_list_recipes` to the tool list and `READ_ONLY_TOOLS`; `test_recipe_guidance_in_descriptions` (FR-027, FR-061) · `tests/test_mcp_tools.py`
- [x] **T054** [P] [US4] `test_recipe_tools_keys_superset`: pre-change key-set snapshot for the four tools; every old key present, new keys present (SC-006) · `tests/test_response_contract.py`

### Implementation

**⟶ Wait for the tests wave, then Wave 2 (independent):**

- [x] **T055** [P] [US4] `ListRecipesInput` (`query`, `source`, `requires_write`, `limit`, `recipe_id`) · `src/flextoolsmcp/server/models.py`
- [x] **T056** [P] [US4] `recipe_not_found` error-detail model (appended error code) · `src/flextoolsmcp/server/response_models.py`

**⟶ Wait for Wave 2, then Wave 3 (independent):**

- [x] **T057** [P] [US4] `flextools_list_recipes` ToolDef; mark `flextools_list_skeletons` DEPRECATED in its description · `src/flextoolsmcp/server/tool_definitions.py`
- [x] **T058** [P] [US4] `handle_list_recipes` (compact rows, filters, `recipe_id` full recipe recording validated entities, `recipe_not_found`); `handle_list_skeletons` becomes an alias over local recipes in the old row shape plus `deprecation` (FR-024..026) · `src/flextoolsmcp/server/handlers/catalog.py`

**⟶ Wait for Wave 3, then Wave 4 (single):**

- [x] **T059** [US4] Register `list_recipes` at all five dispatch touch points · `src/flextoolsmcp/server/dispatch.py`

**⟶ Wait for Wave 4, then Wave 5 (single):**

- [x] **T060** [US4] Generate the `recipe_not_found` golden fixture with `make_golden.py` · `tests/golden/responses/recipe_not_found.json`

**Checkpoint**: T052..T054 pass; US4 acceptance 1..3 hold.

---

## Phase 7: User Story 5 — Promote a local recipe to the shipped library (P3)

**Goal**: `flextools-mcp-recipe promote` writes a draft recipe file outside the package and flags lines that need scrubbing.

**Independent Test**: Promote a fixture local recipe into a temp directory; the draft parses as a recipe file and fails validation only on `match_terms` / `notes`.

### Tests (write first; they must fail)

**Wave 1 (independent):**

- [x] **T061** [P] [US5] Default out dir under a tmp HOME, `--out`, refuses to overwrite without `--force`, exit codes 2/3/4, scrub lines for a GUID, `C:\Users\...` and a recorded project name, draft parses with `recipe_files` but fails validation on `match_terms` / `notes` (FR-030, FR-031) · `tests/test_recipe_cli.py`
- [x] **T062** [P] [US5] `test_mined_notes_point_at_local_recipes`: mined notes no longer say "skeleton closet" (FR-032) · `tests/test_extract_patterns.py`

### Implementation

**⟶ Wait for the tests wave, then Wave 2 (independent):**

- [x] **T063** [P] [US5] `recipe_cli.py` with `promote <local-id> --id <new-id> [--out DIR] [--force]`, using the `recipe_files` draft renderer and scrub patterns; ASCII-only console output; UTF-8 draft files; nearest ids on exit 2 (R13, contracts section 7) · `src/flextoolsmcp/recipe_cli.py`
- [x] **T064** [P] [US5] Point `--mine-operations-log` docs and comments at the local-recipe store; carry `params` into the index (FR-032) · `src/flextoolsmcp/extract_patterns.py`

**Checkpoint**: T061/T062 pass; US5 acceptance 1..2 hold.

---

## Phase 8: Polish and cross-cutting

**Wave 1 (independent, different files):**

- [x] **T065** [P] New `docs/RECIPES.md`: file format, PARAMS, local capture, promotion, verification rules (FR-060) · `docs/RECIPES.md`
- [x] **T066** [P] USAGE.md tool reference: add `flextools_list_recipes`, mark `flextools_list_skeletons` deprecated (FR-060) · `USAGE.md`
- [x] **T067** [P] Replace the skeleton-closet paragraph with the recipes workflow (FR-060) · `CLAUDE.md`
- [x] **T068** [P] Update the user-data line (`recipes.jsonl`, `recipe-drafts/`) (FR-060) · `README.md`
- [x] **T069** [P] Add the `recipes`/`recipes_count`/`recipes_ambiguous`/`deprecation` keys, the `recipe_not_found` code, and the deprecation timeline entries · `docs/TOOL-CONTRACT.md`
- [x] **T070** [P] Point script-generation guidance at recipes and PARAMS · `docs/FLEXTOOLS-STYLE-GUIDE.md`
- [x] **T071** [P] CHANGELOG "Tool contract" entry: new tool, new keys, new error code, deprecations with removal at `tool-responses/2.0` (FR-060) · `CHANGELOG.md`

**⟶ Wait for Wave 1, then Wave 2 (single):**

- [x] **T072** Full refresh (`python -m flextoolsmcp.refresh`) to regenerate `common_patterns` with the file recipes merged; commit the regenerated index (constitution III) · `src/flextoolsmcp/index/common_patterns_flexicon-v4.11.0.json`

**⟶ Wait for Wave 2, then Wave 3 (single):**

- [x] **T073** Validate against the Success Criteria: `.venv\Scripts\python -m pytest -q -m "not requires_flex"` (whole suite, including the battery for SC-001 and the size/code-body budgets for SC-005), `python scripts/validate_integrity.py server`, pre-commit, and a wheel build asserting the `recipe_library/*.py` count (FR-005). Record the one-off SC-004 measurement on the developer store in `evidence/README.md` · repository root, `specs/unified-recipes/evidence/README.md`

---

## Dependencies & Execution Order

**Phases**: Setup (1) → Foundational (2) → US1 (3) → US2 (4) → US3 (5) → US4 (6) → US5 (7) → Polish (8).

- US1 and US3 validator work (T029..T033) both need only Phase 2; US3 recipe ports (T034+) need T033.
- US2 needs US1's ranker seam (T015) for T024 and T025.
- US4 needs US1 (T015) and US2 (T022) because it lists both sources.
- US5 needs US2 (T022) for local records and Phase 2 (T008) for the renderer.
- Polish needs every story; T072 must follow the last recipe file (T051).

**Waves per phase**:

- **Phase 1**: W1 T001 → W2 T002..T005.
- **Phase 2**: W1 tests T006, T007 → W2 T008, T009 → W3 T010, T011.
- **Phase 3 (US1)**: W1 tests T012..T014 → W2 T015 → W3 T016, T017 → W4 T018.
- **Phase 4 (US2)**: W1 tests T019..T021 → W2 T022 → W3 T023, T024 → W4 T025..T027 → W5 T028.
- **Phase 5 (US3)**: W1 tests T029..T031 → W2 T032 → W3 T033 → W4 read recipes T034..T041 → W5 ledger T042 → W6 write recipes T043..T050 (live writes on Sena 3, unattended OK) → W7 ledger/deferrals T051.
- **Phase 6 (US4)**: W1 tests T052..T054 → W2 T055, T056 → W3 T057, T058 → W4 T059 → W5 T060.
- **Phase 7 (US5)**: W1 tests T061, T062 → W2 T063, T064.
- **Phase 8**: W1 docs T065..T071 → W2 index regen T072 → W3 validation T073.

**Live writes**: T043, T044, T046..T050 include live writes on Sena 3. Unattended runs perform them under the Sena 3 exception (constitution I, R14); they stop as `needs-human` only if the project cannot be asserted to be Sena 3.
