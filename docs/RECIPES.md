# Recipes

One concept, called "recipes". A recipe is a runnable `run_module` snippet
plus metadata. It is either **shipped** (in the package, for every user) or
**local** (captured from this user's own successful runs). Both share one
shape, one ranked search, and one listing tool,
`flextools_list_recipes`. `flextools_list_skeletons` is a deprecated alias
for the local side (removal at `tool-responses/2.0`).

## Shipped recipe files

Shipped recipes live one-file-per-recipe under
`src/flextoolsmcp/recipe_library/*.py`. Each file has two parts: a metadata
docstring, then code.

The docstring holds one `key: value` line per key. Values are JSON-parsed
where possible, otherwise kept as strings (so `false` becomes a bool and a
bare sentence stays a string). Indented continuation lines join onto the
current key with a single space. Required keys: `id`, `intent`,
`match_terms`, `entities`, `operations`, `requires_write`, `notes`,
`origin`. Optional keys: `verified_against`, `takes_params`,
`raw_lcm_lines`. The loader strips the docstring; `code` is the rest of the
file. The file stem must equal `id`, and `origin` never names a user
project. When `verified_against` omits `flexicon`,
`FLEXICON_VERIFIED_VERSION` is substituted (currently `4.11.0`).

Files are parsed statically (AST/tokenize) and never executed. At import,
file recipes merge into `CURATED_RECIPES` so the validator, search, and
`extract_patterns` see them. An id collision (file vs file, or file vs dict
entry) raises `ValueError`. A malformed file is skipped at runtime with one
logged error naming the file and key, so the server still starts; in tests
loading fails loudly. The library directory ships as wheel package data and
is excluded from pyright, since the files reference runner-injected names
(`project`, `report`, `modifyAllowed`).

## PARAMS block

Parameters use the MCPlayground convention. The tunable values sit between
markers:

```text
# --- PARAMS ---
COUNT = 10  # how many unparsed words to list
# --- END PARAMS ---
```

Each top-level assignment inside the block becomes one parameter:
`name` is the assignment target (UPPER_CASE by convention), `default` is
the value's source text exactly as written (never evaluated), and
`description` is the trailing comment, else the standalone comment lines
above it, plus comments inside a multi-line value. Order follows the
source. A missing block gives `params: []` and the recipe still loads; a
present-but-broken block (unclosed, misordered, unparsable, or defining no
parameters) fails shipped validation, as does a header claiming parameters
the block does not define.

## Using recipes

Check `recipes` in `flextools_search_by_capability` before composing code,
or call `flextools_list_recipes` (filters `query`, `source`
`all|shipped|local`, `requires_write`, `limit`; full code only with
`recipe_id`). To reuse a recipe, edit only the values inside the PARAMS
block and run with `source="existing"` when nothing outside PARAMS
changed. Write recipes (`requires_write: true`) need a dry run first
(`modifyAllowed=False`), then `write_enabled` plus confirmation. Pass
`user_intent` to `run_module` so a successful run is remembered as a local
recipe.

## Local capture

After a successful `run_module`, the whole executed code is captured as one
local recipe when `user_intent` is non-empty (after `strip()`) and the code
has at least 4 non-blank, non-comment lines. Per-`def` capture is gone; a
2-line probe, a run without intent, or unparsable code stores nothing.

A local record holds `id` (`local-` plus 12 hex chars of fingerprint),
`intent`, `code`, `entities` (from this code's AST only: `project.<X>`
accessors mapped to entity names, plus `I*` interfaces named),
`requires_write` (true when the run was write-enabled and the script is
mutating), `operations`, `params` (from the PARAMS block if present),
`projects`, `first_used`, `last_used`, `use_count`, `op_ids` (last 5),
`source: "local"`. Identity is a SHA-256 fingerprint of the code with
comments stripped, blank lines dropped, and whitespace runs collapsed, so
comment/whitespace-only edits are repeats: they bump `use_count`, update
`last_used`/`op_ids`/`projects`, OR `requires_write`, and refresh `intent`
and `code` instead of adding a row.

Capture never raises and never fails the op; every failure path returns
`None`. Malformed JSONL lines are skipped on read and dropped on the next
rewrite. The store is capped at 2,000 rows; over the cap the
lowest-`use_count`, oldest-`last_used` rows are dropped on rewrite.
Storage is UTF-8 JSONL at `~/.flextoolsmcp/recipes.jsonl`, atomic via
temp-file plus `os.replace`. Override the directory with
`FLEXTOOLSMCP_RECIPE_DIR`; the old `FLEXTOOLSMCP_SKELETON_DIR` is honoured
as a fallback.

## Legacy migration

On first load, when `recipes.jsonl` is absent and `skeletons.jsonl` exists,
legacy entries migrate once. Entries are grouped by `op_id` into one
candidate recipe; intent is recovered from `logs/operations.jsonl` by
`op_id` (falling back to the entry's own intent, else null, lowest rank).
Bodies under 5 real lines and trivial text/`'***'` helpers are dropped;
near-duplicates merge. The legacy file is never modified or deleted.

## Ranked search

`server/recipes.py` runs one ranked search over shipped and local recipes.
Query words score against three bags, weighted highest to lowest: task text
(`match_terms` phrases, then `intent` words); function and property names
from the code's AST (`code_terms`, split on camelCase and underscores with
a small alias table such as `env` for environment and `msa` for
grammatical info); object names (`entities`, and object words in `id`),
weighted lowest. Each word is weighted by rarity across the recipe set
(IDF-style), so a word shared by most recipes contributes little.
Normalization covers case, punctuation, and plural `-s`. Shipped recipes
and local recipes with higher `use_count` get a boost.

Search returns up to 3 rows plus `recipes_count` and `recipes_ambiguous`.
The top row carries full `code` only for a clear winner (score above a
minimum, at least 1.5x the second row, and not reached through object names
alone); otherwise every row is compact (no `code`), `recipes_ambiguous` is
true, and the response hints to refine the query or fetch one by id. A
response never carries the same recipe's code twice: when the winner is
also attached at `results[0].recipe`, the `recipes[0]` row stays compact
with `code_at: "results[0].recipe"`. Compact rows average under 400
characters; `params[].default` truncates to 60 characters there. Serving a
recipe with code records its entities as validated discovery.

## Promotion

A repeatable path from local to shipped, via the console script:

```text
flextools-mcp-recipe promote <local-id> --id <new-id> [--out DIR] [--force]
```

The draft goes to `~/.flextoolsmcp/recipe-drafts/<new-id>.py` by default
(`--out DIR` overrides), never into the package. The header is prefilled
from the local record (intent, entities, reads/writes, origin) with
`match_terms: []` and `notes: "TODO"` so the draft fails shipped
validation until a human generalizes it. Promotion prints one
`scrub before shipping` line per line containing a GUID literal, a Windows
user path, or a project name from the record (plus the forbidden names):
scrub each before shipping. Exit codes: `0` draft written; `2` unknown
local id (prints nearest ids); `3` target exists without `--force` or is
unwritable; `4` new id is not kebab-case or collides with a shipped id.

## Verification rules

Every shipped recipe must pass `recipe_validator.validate_recipe` with
`shipped=True` in CI. On top of the run-time preflight subset (parses,
`requires_write` agrees with CUD detection, `if modifyAllowed:` guard,
imports, undefined names, valid `project.<X>` chains, no deprecated
member), the shipped gate checks: the PARAMS block parses; every
`requires_write` recipe guards writes; no curated- or index-deprecated
member; no GUID literal, Windows user path, or `Claude-Swahili`/`Target`
defaults; no `print()` (report through `report.*`); and minimal raw-LibLCM
use — each raw access (casts to `I*` interfaces, `OA`/`OS`/`OC`/`RA`/`RS`
/`RC` properties, `project.project`, `ServiceLocator`, `ClassName`
dispatch) either names its flexicon wrapper or carries a
`flexicon gap` / `raw-lcm` reason comment. Each recipe header records
`raw_lcm_lines`, and a test fails when the code count exceeds it.

Live verification runs on **Sena 3 only**, never on work projects. Every
shipped read recipe is run unchanged (default params, or params set to Sena
3 data); every shipped write recipe is run with `modifyAllowed=False`
(dry run) showing intended changes; recipes that create or delete objects
also get a live write with pre/post evidence. Each run records `op_id`,
flexicon version, parameter values, a report excerpt, and the Sena 3
`.fwdata` mtime and hash before and after; live runs add pre/post object
values and same-session cleanup of `zzRecipeTest`-prefixed objects. Each
recipe sets `verified_against` with the flexicon version and `verified_by`
(`preflight`, `sena3-read`, `sena3-dryrun`, `sena3-live`); evidence files
live under `specs/_archive/unified-recipes/evidence/<recipe-id>.md` per the
protocol in `specs/_archive/unified-recipes/evidence/README.md`.
