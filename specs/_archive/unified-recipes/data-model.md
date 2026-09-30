# Data model: Unified recipes

Four entities. **Recipe** is the internal shape both sources normalize to.
**Recipe row** and **full recipe** are the two ways it is exposed. The rest
are storage forms.

## 1. Recipe (internal, normalized)

Every recipe, shipped or local, is normalized to this dict before ranking or
serving.

| Field | Type | Shipped | Local | Rule |
|---|---|---|---|---|
| `id` | str | header `id` = file stem, or dict key | `local-<fp12>` | unique across both sources; a shipped collision raises (R5) |
| `intent` | str \| null | required | `user_intent` at capture; `null` only for migrated rows | non-empty for shipped |
| `match_terms` | list[str] | required, non-empty | `[]` | |
| `entities` | list[str] | required, non-empty | from the code's AST (R8) | sorted, de-duplicated |
| `operations` | list[str] | required | derived: `["read"]` or `["read","write"]` | |
| `requires_write` | bool | header | `write_enabled and is_mutating_script` | shipped: must agree with the validator (FR-041) |
| `params` | list[Parameter] | from the PARAMS block | from the PARAMS block if present, else `[]` | |
| `code_terms` | list[str] | derived at load | derived at capture/load | **internal only, never serialized in rows**. Function-call and attribute names from the code's AST, split and aliased (R10) |
| `raw_lcm_lines` | int | header, required when the code has raw LCM access | absent | must be at least the `detect_raw_lcm_access` count; ratchets down only (R18) |
| `code` | str | file text after the docstring | the whole executed snippet | shipped: must pass `validate_recipe` |
| `notes` | str | required | `""` | |
| `origin` | str | e.g. `"MCPlayground lib/candidates.py; Ron"` | `"local"` | shipped only: never names a user project |
| `source` | `"curated"` \| `"local"` | `"curated"` | `"local"` | internal value; rows map `curated` to `shipped` (R6) |
| `verified_against` | `{flexicon, verified_by}` | required | absent | `verified_by` is one of `eval-corpus`, `preflight`, `sena3-read`, `sena3-dryrun`, `sena3-live` |
| `use_count`, `first_used`, `last_used`, `projects`, `op_ids`, `migrated` | | absent | see section 3 | |

## 2. Parameter

`{ "name": str, "default": str, "description": str }`

- `name`: the assignment target inside the PARAMS block; an UPPER_CASE
  identifier by convention (the validator warns otherwise).
- `default`: the value's **source text**, exactly as written (for example
  `"10"` or `'["zaa", "ambi"]'`). It is never evaluated.
- `description`: the trailing comment, else the standalone comment lines
  above it, plus comments inside a multi-line value (R4). May be `""`.
- Order follows the source.

## 3. Local recipe record (`recipes.jsonl`, one JSON object per line)

```json
{
  "id": "local-3f9a0c1b2d4e",
  "intent": "List entries with glosses over five words",
  "code": "...whole snippet...",
  "entities": ["LexEntry", "LexSense"],
  "requires_write": false,
  "params": [],
  "projects": ["Sena 3"],
  "first_used": "2026-09-27T14:02:11+00:00",
  "last_used": "2026-09-28T09:15:40+00:00",
  "use_count": 2,
  "op_ids": ["op-...-001", "op-...-014"],
  "source": "local",
  "migrated": false,
  "schema": "local-recipe/1"
}
```

Validation and lifecycle:

- **Capture preconditions (FR-011)**: `run_module` succeeded; `user_intent`
  is non-empty after `strip()`; the code has at least 4 lines that are
  neither blank nor comment-only. Otherwise nothing is written.
- **Identity (FR-013)**: `id = "local-" + sha256(normalized_code)[:12]` (R7).
  An existing id is updated: `use_count += 1`, `last_used = now`, the new
  `op_id` is appended to `op_ids` (only the last 5 are kept), the project is
  added to `projects` (as a set, sorted), and `requires_write` is OR-ed.
  `intent` is replaced by the newest non-empty intent. `code` keeps the
  latest text, which can differ from the old one only in comments or
  whitespace.
- **Cap (FR-016)**: at most 2,000 rows; over the cap, drop by
  `(use_count asc, last_used asc)`.
- **Failure (FR-014)**: every exception in capture is swallowed and returns
  `None`. The op result never changes.
- **Malformed lines**: skipped on read and dropped on the next rewrite.
  (The rewrite only ever writes valid rows.)
- `projects` and `op_ids` are local-only. They never appear in shipped
  recipes and are omitted from compact rows (section 5).

State transitions for a local row: *absent* -> *captured* (`use_count` 1)
-> *reused* (`use_count` n+1). A row leaves either by the cap or by
`promote` (a copy; the row stays).

## 4. Legacy skeleton entry (read-only input to migration)

This is the existing `SkeletonClosetEntry`: `{name, source, entities,
user_intent, captured_at, op_id, session_id, duration_ms}`. Migration (R9)
groups these by `op_id` into one candidate local recipe and sets
`migrated: true`. `first_used` and `last_used` come from the min and max
`captured_at`, and `use_count` counts the distinct ops that merged into the
fingerprint. `skeletons.jsonl` is never written.

## 5. Exposed shapes

**Recipe row (compact)**, used by the search `recipes[1..]`, `list_recipes`
without `recipe_id`, and local entries in `find_examples.recipes`:

```json
{
  "id": "parser-coverage",
  "intent": "Parser coverage and the most frequent unparsed wordforms",
  "source": "shipped",
  "requires_write": false,
  "params": [{"name": "COUNT", "default": "10", "description": "how many unparsed words to list"}],
  "entities": ["WfiWordform"],
  "use_count": null,
  "last_used": null,
  "score": 11.5
}
```

- It has no `code`. SC-005 sets a budget of under 400 characters on average.
  To stay within it, `params[].default` is truncated to 60 characters with
  a trailing `...` in compact rows only.
- `use_count` and `last_used` are `null` for shipped rows. `score` appears
  only in search results.
- `code_at` (optional, search only) is set to `"results[0].recipe"` when
  this row's code is already in the response's legacy attachment.

**Full recipe**, used by the search `recipes[0]` and `list_recipes(recipe_id=...)`:
the compact row plus `code`, `notes`, `match_terms`, `operations`, `origin`,
and `verified_against` (shipped rows only).

**Legacy skeleton row**, used by `list_skeletons` and
`find_examples.skeletons_from_your_sessions`. It is built from local recipes:

- `list_skeletons` rows: `{name: id, source: code, entities, user_intent:
  intent, captured_at: last_used, op_id: op_ids[-1], session_id: "",
  duration_ms: 0}`
- `skeletons_from_your_sessions` rows: `{name: id, source: code, captured_at:
  last_used, attribution}`, keeping the existing attribution string format.

## 6. Recipe file (shipped source)

```python
"""
id: parser-coverage
intent: Parser coverage and the most frequent unparsed wordforms
match_terms: ["parser coverage", "unparsed words", "words that don't parse", "parse rate"]
entities: ["WfiWordform"]
operations: ["read", "iterate"]
requires_write: false
origin: MCPlayground flex-parse-fixup lib/candidates.py; second-user logs
verified_against: {"flexicon": "4.11.0", "verified_by": "sena3-read"}
raw_lcm_lines: 1
notes: Frequency is GetOccurrenceCount. A wordform counts as parsed when
    the parser has at least one analysis (ParserCount > 0).
"""
# --- PARAMS ---
COUNT = 10  # how many unparsed words to list, most frequent first
# --- END PARAMS ---

...code...
```

Load rules: see R3 and R4. The file stem must equal `id`. A value that
`json.loads` rejects is kept as a string (so `false` becomes a bool,
`4.11.0` stays a string, and a bare sentence stays a string).
`FLEXICON_VERIFIED_VERSION` (bumped to `4.11.0`) is substituted when
`verified_against` omits `flexicon`.
