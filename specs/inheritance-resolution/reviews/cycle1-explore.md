# Explore Review — cycle 1: Inheritance Resolver Surface

**Date:** 2026-08-12
**Reviewer:** Explore Agent (read-only)

> Persisted by the orchestrator: the Explore agent runs read-only and had no
> Write tool. Body is verbatim from the agent's return.
>
> **Orchestrator note on §5:** the agent read `discovery.py` *after*
> lex-programmer's concurrent #85 fix had landed, so it observed the
> already-corrected `args.get(...)` form. The pre-fix state was
> `args.from_object` at line 174. Its conclusion (no unguarded attribute
> access remains) is correct for the post-fix tree.

**Summary:** There is NO ancestor walk anywhere in the runtime —
`resolve_property` only *appears* to resolve inheritance because the build-time
casting index pre-propagated properties to descendants; a real walk must be
written from scratch. Inheritance merge is safe for interfaces (0 name
collisions), and the index is small enough (8.2 MB, max depth 6) that a
memoized walk is trivial.

---

## 1. How `handle_resolve_property` "resolves" inheritance — it doesn't

- `resolve_pythonic_property` (`src/flextoolsmcp/server/handlers/api.py:541`,
  sig `def resolve_pythonic_property(name: str, context_entity: str | None = None) -> List[Dict[str, Any]]`)
  does **exact entity equality only**: line 556
  `results = [m for m in matches if m[KEY_ENTITY] == context_entity]`, and the
  fallback at 563 builds literal key `f"{context_entity}.{name}"`. No transitive
  step, no `interfaces`, no `base_classes`.
- Verified: `suffix_index.by_pythonic_name["Feature"]` contains entities
  `FsFeatureSpecification, IFsFeatureSpecification, IPhFeatureConstraint,
  PhFeatureConstraint` — **not** `IFsClosedValue`. So the walk returns `[]`.
- The correct answer comes from the **casting-index rescue** at
  `api.py:1216-1221` (`if property_name in casting_props: result[KEY_FOUND] = True`)
  plus `property_to_concrete_mapping` at `api.py:1246-1291`.
  `casting_index_liblcm-v11.0.0.json` has
  `property_to_concrete_mapping.FeatureRA.available_on = [IFsClosedValue, IFsComplexValue, …]`.
- That descendant propagation happens **at build time** in
  `src/flextoolsmcp/build_casting_index.py:153-188`
  (`compute_all_descendants(iface, cache=descendants_cache)`, memoized DFS,
  transitive, reads `interfaces` only at line 93).
- **Nothing is reusable.** There is no ancestor-walk helper to import; the only
  transitive logic is a closure inside an offline build script, and it is
  descendant-direction, capped by `COMMON_BASE_INTERFACE_THRESHOLD` noise
  filters.

## 2. `paginate_entity` (api.py:420)

`paginate_entity(entity, summary_only, method_filter, limit, offset, object_type="", library="flexicon", casting_index=None) -> dict`

- Methods: filtered by substring `method_filter` (447), `total_methods = len(methods)`
  **after** filter (450), then `methods[offset:offset+limit]` (453).
- Properties: same `method_filter` applied to property names (500-502),
  `total_properties` after filter (504), then the **same `offset`/`limit`
  applied independently** (507).
- `has_more`/`next_offset` (478-480) are computed from methods only — properties
  have no `has_more`. That's the coherence bug merged members will amplify.
- Merged ancestor members must be spliced into `entity[KEY_PROPERTIES]`/`[KEY_METHODS]`
  **before line 444/482** (i.e. dedupe + tag `inherited_from` upstream, or wrap
  the entity dict), so totals, filters, slicing, and the casting join at 523 all
  stay consistent. Consumer note: `handle_get_object_api` feeds returned
  props/methods into `session_state.record_discovered_api` (api.py:742-751), so
  merged members would also become "discovered".

## 3. Collisions

Transitive over `interfaces` + `base_classes`: **2214 colliding
(entity, property) pairs across 250 entities — all of them classes; 0
interface-vs-ancestor collisions.**

- `BackupFileSettings.BackupTime` (own `can_write: true`) vs
  `IBackupSettings.BackupTime` (`can_write: false`) — a real semantic override.
- `AnalysisRepository.Count` vs `IRepository.Count` — identical re-declaration.

Since liblcm discovery targets `I*` interfaces, override semantics are
effectively theoretical for interfaces; a simple "child wins" dedupe suffices,
but it matters if class entities are merged.

## 4. Perf

`liblcm_api_v11.0.0.json` = 8,167,775 bytes (8.2 MB), 1878 entities, already
fully in memory after `ensure_liblcm_loaded()`. Deepest `interfaces` chain =
**6**: `PhSimpleContextBdry → IPhSimpleContextBdry → IPhSimpleContext →
IPhPhonContext → IPhContextOrVar → ICmObject → ICmObjectOrId`. Average depth
1.33; max transitive ancestor set 14, average 2.38. Walk is O(depth) ≈ a handful
of dict lookups — memoization is optional, though a module-level cache is cheap.
Cycle guard still advisable (interfaces + base_classes can theoretically loop).
`IFsClosedValue` merges 2 own → 31 total properties.

## 5. `args` attribute-access sweep — clean

No unguarded attribute access exists. `discovery.py:173-174` uses
`args.get("from_object")` / `args.get("to_object")`. Only two guarded sites
remain: `catalog.py:182` (`isinstance(args, dict)` else `getattr`) and
`catalog.py:213` (`args.limit if hasattr(args, "limit")`). Both are defensive
dual-mode, not bugs.

---
**Reviewed By:** Explore Agent
