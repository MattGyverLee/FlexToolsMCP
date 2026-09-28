# Quickstart: Unified recipes

Run all of this from the feature worktree `C:\Github\FlexToolsMCP-recipes`,
after the rebase (research R16).

## 1. Suite (no FieldWorks)

```powershell
.venv\Scripts\python -m pytest -q -m "not requires_flex" tests/test_recipe_files.py tests/test_local_recipes.py tests/test_recipe_search.py tests/test_list_recipes.py tests/test_recipe_cli.py tests/test_recipes.py tests/test_mcp_tools.py tests/test_response_contract.py tests/test_server_instructions.py
python scripts/validate_integrity.py server
```

## 2. Add a shipped recipe

1. Create `src/flextoolsmcp/recipe_library/<id>.py` with the metadata
   docstring (`data-model.md` section 6) and a `# --- PARAMS ---` block.
2. Run it through the validator:
   `.venv\Scripts\python -m pytest -q -m "not requires_flex" tests/test_recipes.py -k preflight`.
3. Verify it on **Sena 3** (never Claude-Swahili):
   - Confirm the project with `flextools_list_projects`.
   - Record the `.fwdata` mtime and SHA-256.
   - Run with `flextools_run_module(code=<file text after the docstring>,
     source="existing", user_intent=...)`. Read recipes run with writes off;
     write recipes run first with `write_enabled=false`.
   - Record the hash and mtime again.
   - Write `specs/unified-recipes/evidence/<id>.md`.
4. Set `verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read" | "sena3-dryrun" | "sena3-live"}`.

## 3. Local recipe round trip (SC-002)

1. Run any snippet of at least 4 lines with `user_intent="List entries with
   glosses over five words"`.
2. Restart the MCP server.
3. Call `flextools_search_by_capability(query="long glosses")`. `recipes`
   should include `local-...` with `source: "local"` and `use_count: 1`.
4. Call `flextools_list_recipes(source="local")` to see the compact row, then
   `flextools_list_recipes(recipe_id="local-...")` to get the code.

## 4. Promote

```powershell
flextools-mcp-recipe promote local-3f9a0c1b2d4e --id long-glosses
# -> ~/.flextoolsmcp/recipe-drafts/long-glosses.py, plus any "scrub before shipping" lines
```

Generalize the draft, fill in `match_terms` and `notes`, move it into
`recipe_library/`, then repeat step 2.

## 5. Regenerate the index after adding recipes

```powershell
python -m flextoolsmcp.refresh
git diff --stat src/flextoolsmcp/index
```

The regenerated `common_patterns_flexicon-v4.11.0.json` is committed with the
change (constitution III).
