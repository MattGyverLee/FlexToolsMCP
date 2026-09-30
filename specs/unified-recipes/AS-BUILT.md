# unified-recipes: as built

**Status:** Retired 2026-09-29. Squash-merged to main as `af8e97d` (PR #295, merged 2026-09-28). Tasks: 73/73 complete.
**Full docs:** [specs/_archive/unified-recipes/](../_archive/unified-recipes/) (spec, plan, research R1-R18, data-model, contracts/tools.md, raw-lcm-ledger, checklists, per-recipe evidence). Not read by default.
**Pinned here:** none. No test or code opens these files. `docs/RECIPES.md` and `specs/recipe-distill/spec.md` cite them under `specs/_archive/unified-recipes/`.
**Scope:** This repo only. The flexicon API gaps found during the work were fixed separately, in the flexicon repo (see Follow-ups).

## What shipped
- Recipes are now one concept. A recipe is either **shipped** (in the package) or **local** (captured from this user's successful runs). The old skeleton closet (`server/skeleton_storage.py`) is gone.
- `src/flextoolsmcp/recipe_library/*.py` holds 43 shipped recipes, one per file: the 16 from FR-050 (0 deferred) plus 27 ported from real FLExTools modules (#292, merged into this PR). They are merged into `CURATED_RECIPES` next to the 24 older dict recipes.
- Ranked recipe search in `flextools_search_by_capability` and `flextools_find_examples`.
- New tool `flextools_list_recipes`. `flextools_list_skeletons` stays as a deprecated alias.
- A `flextools-mcp-recipe promote` console script.
- The shipped-recipe validator gate (PARAMS, write guard, deprecation, scrub, print, raw-LCM).
- Server `instructions=`.

## Public contracts (checked against main `0715b64`)
- **Recipe file:** a `key: value` metadata docstring with `id`, `intent`, `match_terms`, `entities`, `operations`, `requires_write`, `origin`, `verified_against`, `notes` and optionally `raw_lcm_lines`. Values are JSON-parsed where possible. `code` is the file minus the docstring. The `# --- PARAMS ---` / `# --- END PARAMS ---` block becomes `params: [{name, default, description}]`. Code is in `recipe_files.py` (`parse_params`, `load_recipe_library`). Files are parsed statically, never imported. A malformed file is skipped with one logged error; an id collision raises at import.
- **Package:** `recipe_library/*.py` is package data (pyproject.toml:113). It is excluded from pyright and ruff. Console script: `flextools-mcp-recipe = "flextoolsmcp.recipe_cli:main"` (pyproject.toml:95).
- `FLEXICON_VERIFIED_VERSION = "4.11.0"` (curated_recipes.py:37). It must equal the flexicon version of the loaded index.
- **Local store:** `server/local_recipes.py` writes to `~/.flextoolsmcp/recipes.jsonl`. Override with `FLEXTOOLSMCP_RECIPE_DIR`; `FLEXTOOLSMCP_SKELETON_DIR` still works as a fallback.
  - Capture takes the whole snippet, and only when `user_intent` is non-empty and the code has at least 4 real lines.
  - The id is `local-<sha256[:12]>` of the code with comments and blank lines removed and whitespace normalized. A repeat run updates `use_count`, `last_used`, `op_ids` (last 5) and `projects` instead of adding a row.
  - The store is capped at 2,000 rows. Capture never raises.
  - The first load migrates `skeletons.jsonl` once and leaves that file untouched.
- **Search** (`server/recipes.py`): each query word is weighted by where it matches (task text 2.0, a phrase 4.0, code terms 1.5, object words 0.25), times an IDF term. Shipped recipes get +1.0. The top row carries `code` only when it is a clear winner: score at least 3.0, at least 1.5 times the runner-up, and not matched through object words alone.
  - New `search_by_capability` keys: `recipes` (0-3 rows), `recipes_count`, `recipes_ambiguous`, and `recipes_hint` (only when ambiguous). A row whose code is already attached at `results[0].recipe` gets `code_at: "results[0].recipe"` instead. A response never carries more than one code body.
  - `results[0].recipe` is unchanged (old first-match rule, `source: "curated"`).
- **`flextools_list_recipes`** takes `query`, `source` (`all`/`shipped`/`local`), `requires_write`, `limit` (1..200, default 50) and `recipe_id`. Without `recipe_id` it returns compact rows only. An unknown `recipe_id` returns error `recipe_not_found`, with details in this order: `recipe_id`, `closest_matches`, `hint`. That makes 44 error codes (TOOL-CONTRACT.md:155).
- **Deprecations** (removal at `tool-responses/2.0`): `flextools_list_skeletons`, and the `skeletons_from_your_sessions` key in `find_examples`. Each response that still uses them carries a `deprecation` object.
- **Promote:** `promote <local-id> --id <new-id> [--out DIR] [--force]`. The default output directory is `~/.flextoolsmcp/recipe-drafts/`.
  - Exit codes: 0 written, 2 unknown id, 3 target exists, 4 bad or colliding id.
  - It prints a "scrub before shipping" line for each GUID, user path (`\`, `\\` or `/` forms) and project or forbidden name.

## Key decisions
- Recipes are full runnable scripts, not skeletal pseudocode. Response size is kept down with compact rows; full code comes back only for a clear winner or by id.
- Parameters live in the in-code PARAMS block. `run_module` gets no new argument. To reuse a recipe, edit the values and run with `source="existing"`.
- The MCPlayground `flex-parse-fixup` scripts are the primary source. Ron's code was rewritten to current flexicon, and none of his data ships.
- The raw-LCM gate is a style gate. A raw access with a flexicon wrapper fails and names that wrapper; any other raw access needs a `# flexicon gap: #N` or `# raw-lcm: reason` note. `raw_lcm_lines` is a per-recipe ratchet. The note never relaxes a write-safety or casting check.
- Deprecation checks read the index's markers as well as the curated list. `DoNotUseForParsing` is banned.
- Contracts are append-only: the old tool and key remain as aliases.

## Gotchas and limits
- Sena 3 is the only verification target; Claude-Swahili is never used. Live writes use `zzRecipeTest` objects, are cleaned up in the same session, and record the `.fwdata` hash before and after.
- Verification tags across the 43 shipped recipes: 24 `sena3-read`, 12 `sena3-dryrun`, 7 `sena3-live`. Only the 16 FR-050 recipes have evidence files. The 27 #292 ports are backed by the PR description only.
- Local capture needs `user_intent`. Runs without it are never remembered.
- Ranking is lexical only. Embedding ranking is an optional follow-up.

## Divergences from the spec
- **Scope grew:** 43 recipes shipped instead of 16, because #292 was folded into the PR. FR-050's count is met.
- **SC-004 is mixed:** the live developer store shrank by 42.6% (319 to 183 rows), under the 50% bar. It has no rows under 5 lines, and the fixture test passes (see the evidence README).
- **Constants:** contracts section 6 says handlers use the key constants, but `handlers/api.py:1797-1799` uses the literal `"skeletons_from_your_sessions"`.
- **Scrub regex:** it was widened after review to catch escaped and forward-slash user paths.
- **Not verified here:** each recipe's behaviour, and the SC-001 90% battery rate. Only the surface above was read.

## Follow-ups and open issues
- **Raw-LCM notes still in shipped recipes.** 18 recipes (59 `raw_lcm_lines` in total) still carry `flexicon gap:` notes for #573 (11 of them), #574, #578, #581, #582 and #583.
  - All of these issues are CLOSED on GitHub. But in `C:\Github\flexicon` main (v4.11.0-4), the fixes for #573, #575, #577, #578, #580, #582 and #583 are only on side branches (for example `issue-573-msa-inflection-class`). No commit was found for #574 or #581.
  - Following the spec's release rule, the recipes should be updated once a pyflexicon release contains those fixes.
- #542-#547 are fixed on flexicon main. Safety issues #277-#280 are closed.
- The follow-up spec is [../recipe-distill/](../recipe-distill/): quality-gating the local recipe journal.
