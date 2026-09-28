# Contract: MCP tool surface changes

Contract version stays `tool-responses/1.x`. Every change here is additive
(constitution IV). Identifiers are copied verbatim from the spec.

## 1. `flextools_search_by_capability` (changed, additive)

New top-level keys in the success payload:

| Key | Type | Rule |
|---|---|---|
| `recipes` | list | 0..3 rows, ranked (R10). `recipes[0]` is a **full recipe** (has `code`) only for a clear winner (R10 code gate); otherwise all rows are **compact** (no `code`). If the winner is the recipe already attached at `results[0].recipe`, `recipes[0]` is compact and adds `code_at: "results[0].recipe"`. Always present; `[]` when nothing scores. |
| `recipes_count` | int | `len(recipes)` |
| `recipes_ambiguous` | bool | true when `recipes` is non-empty and there is no clear winner (this includes object-only queries such as "entry") |
| `recipes_hint` | str | present only when `recipes_ambiguous` is true. Example: "Several recipes match; refine the query or fetch one with flextools_list_recipes(recipe_id=...)" |

Invariant (SC-005): across `results[0].recipe` and `recipes`, a response carries
at most one `code` body.

These stay unchanged:

- `results[0].recipe` (FR-022). It is still chosen by the old
  first-match-over-shipped rule, has the same dict shape, and keeps
  `source: "curated"`.
- `worked_examples` and `worked_examples_count`, and every other existing key.

Side effect (FR-026): `session_state.record_validated_api(e)` is called for
each entity of `recipes[0]` only. Compact rows are not "served code", so they
are not recorded.

`SearchByCapabilitySuccess` (`extra="ignore"`) needs no change. If an optional
typed field is added, it must default to `[]` / `0`.

## 2. `flextools_find_examples` (changed, additive)

- `recipes`: the existing list keeps its current shipped entries (same shape
  as today). Matching **local** recipes are appended as compact rows with
  `source: "local"`, filtered by the same `object_type` / `operation_type`
  rules. Shipped rows come first. The length is still bounded by
  `max_results`.
- `recipes_count`: updated to match.
- `skeletons_from_your_sessions`: still emitted when non-empty (from local
  recipes, in the legacy row shape; see data-model section 5).
- `deprecation` (new, only when `skeletons_from_your_sessions` is present):

```json
{"deprecated": "skeletons_from_your_sessions",
 "replacement": "recipes (source=\"local\")",
 "removal": "tool-responses/2.0"}
```

Side effect: entities of every served recipe that carries `code` are recorded
as validated. That is today's behaviour for shipped entries, and it is
unchanged.

## 3. `flextools_list_recipes` (new)

Annotations: `READ_ONLY_SAFE`. Input model `ListRecipesInput`:

| Arg | Type | Default | Rule |
|---|---|---|---|
| `query` | str \| null | null | ranked with the search scorer when given; otherwise the order is shipped first (by id), then local (by `last_used` desc) |
| `source` | `"all"` \| `"shipped"` \| `"local"` | `"all"` | a `Literal` in the input model, so any other value is refused by the existing `invalid_input` gate |
| `requires_write` | bool \| null | null | filter when not null |
| `limit` | int | 50 | clamped to 1..200 |
| `recipe_id` | str \| null | null | when set, the other filters are ignored and the full recipe is returned |

Success without `recipe_id`:

```json
{"recipes": [<compact row>, ...], "recipes_count": 12, "total": 40,
 "source": "all", "storage_path": "C:\\Users\\...\\.flextoolsmcp\\recipes.jsonl"}
```

Success with `recipe_id`:

```json
{"recipe": <full recipe>}
```

Records the recipe's entities as validated (FR-026).

An unknown `recipe_id` gives the new error code `recipe_not_found`, with the
detail fields, in this order: `recipe_id` (the required string that was
asked for), `closest_matches` (a list of up to 3 nearest ids by `difflib`),
and `hint` (which names `flextools_list_recipes(query=...)`; constitution V).
The code is appended to the error-code table in `docs/TOOL-CONTRACT.md`
(the "one of the 43 codes" count becomes 44), to the error-detail models,
and to the golden fixtures (`tests/make_golden.py`).

The response uses the standard envelope (`build_response_with_context`), not
raw `json.dumps`.

## 4. `flextools_list_skeletons` (deprecated alias)

- The input (`limit`) and the top-level keys `count`, `limit`,
  `storage_path` and `skeletons` stay as they are. Rows come from local
  recipes in the legacy shape. `storage_path` now points at `recipes.jsonl`.
- It adds a top-level `deprecation`:

```json
{"deprecated": "flextools_list_skeletons",
 "replacement": "flextools_list_recipes(source=\"local\")",
 "removal": "tool-responses/2.0"}
```

- The description starts with `DEPRECATED: use flextools_list_recipes.`

## 5. Server instructions (new)

`SERVER_INSTRUCTIONS` is passed as `instructions=` to the MCP `Server`. It
must say:

1. Before composing code, check `recipes` in `search_by_capability`, or
   call `flextools_list_recipes`.
2. To reuse a recipe, edit only the values inside `# --- PARAMS ---` ...
   `# --- END PARAMS ---`. If nothing outside PARAMS changed, run it with
   `source="existing"`.
3. Write recipes (`requires_write: true`) need a dry run first, then
   `write_enabled` plus confirmation.
4. Pass `user_intent` to `run_module` so a successful run is remembered as
   a local recipe.

The same four points, shortened, go in the descriptions of
`search_by_capability`, `find_examples` and `list_recipes` (FR-027).

## 6. Response-key registry

Add to `server/response_keys.py` (and to `__all__`): `KEY_RECIPES =
"recipes"`, `KEY_RECIPES_COUNT = "recipes_count"`, `KEY_RECIPE = "recipe"`,
`KEY_RECIPES_AMBIGUOUS = "recipes_ambiguous"`, `KEY_RECIPES_HINT =
"recipes_hint"`, `KEY_DEPRECATION = "deprecation"`,
`KEY_SKELETONS_FROM_YOUR_SESSIONS = "skeletons_from_your_sessions"`.
Handlers use the constants.

## 7. Console script (new)

`flextools-mcp-recipe = "flextoolsmcp.recipe_cli:main"`

```
flextools-mcp-recipe promote <local-id> --id <new-id> [--out DIR] [--force]
```

- Writes `<DIR or ~/.flextoolsmcp/recipe-drafts>/<new-id>.py` and prints the
  path.
- Prints one `scrub before shipping: L<n>: <text>` line for each GUID
  literal, Windows user path (`[A-Za-z]:\\Users\\`), or name from the
  record's `projects` or the forbidden-names list.
- Exit codes:
  - `0`: draft written;
  - `2`: unknown local id, printing the nearest ids;
  - `3`: the target exists and `--force` was not given;
  - `4`: `<new-id>` is not kebab-case or collides with a shipped id.

## 8. Contract tests

`tests/test_response_contract.py` gets a snapshot of the pre-change key sets
for the four tools above. It asserts that every old key is still present
(SC-006) and that the new keys exist.
