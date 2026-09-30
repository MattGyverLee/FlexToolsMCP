# Pattern audit: provenance from ambient session instead of artifact (US2 T028)

Original site: `src/flextoolsmcp/server/handlers/execution.py::_entities_used_in_session` (removed in T023).
Bug class: tagging a specific code artifact with entity provenance taken from ambient session state (`validated_apis`, `discovered_apis`) instead of from the artifact itself (the code's AST via `validators._accessor_to_ops_map` plus `I*` names, the op's own `user_intent`/`project`). Session tags average 23 entries and leak across ops; the store must derive tags from this code only (FR-012).

Scope checked: `server/handlers/op_telemetry.py` (`auto_discovered`), `extract_patterns.py` mining evidence, `server/handlers/execution.py` remaining uses, `server/recipes.py`.

## Pattern audit: provenance-from-session

Original site: src/flextoolsmcp/server/handlers/execution.py:_entities_used_in_session (removed)

Siblings found:
- src/flextoolsmcp/extract_patterns.py:329  [LOW] Notes string still says "session log or skeleton closet" to recover code; wording is stale (T064 will point at the local-recipe store) but it does not take provenance from session state -- intents/shas come from each op's own JSONL record.

Sites cleared / not enumerated:
- server/handlers/op_telemetry.py `auto_discovered` placeholder and `group_records_by_session`: session_id is the correct grouping key for turn/session stats (identity anchor, not artifact provenance); `user_intent` stays a display label. Different failure mode -- cleared.
- server/handlers/execution.py auto-discovery attach (`session_state.record_validated_api`, `auto_discovered_entities`): records discovery for the session; does not label a stored artifact. Cleared.
- server/recipes.py ranker and `find_recipes_for_examples`: consume each recipe's own `entities`/`intent`; no session read. Cleared.
- server/handlers/api.py `handle_find_examples` / `handle_search_by_capability` (T025/T024): load local rows from disk and filter by each row's own entities; skeletons key rebuilt from local rows in legacy shape. Cleared.

Result: no HIGH/MED siblings. Fix stays point-local (T022/T023) plus the T064 wording follow-up already tracked in Phase 7.
