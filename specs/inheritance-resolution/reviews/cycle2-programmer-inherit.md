# Programmer Review — cycle 2: CP2 inheritance merge (T2.1-T2.5)

**Date:** 2026-08-12
**File touched:** `src/flextoolsmcp/server/handlers/api.py` only (+ new test file). `validators.py`, `discovery.py` untouched.

## What changed

- **T2.1** `collect_inherited_members(entity_name, index)`: BFS over `interfaces` UNION `base_classes`, memoized by `(id(index), entity_name)`, cycle-guarded via `visited`. Returns ancestor-only members tagged `inherited_from`. Helper `_ancestor_entity_names` shares the walk for name-only lookups. Gate helper `_is_interface_entity` (name starts with "I" AND `type == "interface"`) enforces DEC-2's scope narrowing everywhere it's used.
- **T2.2/T2.3** `paginate_entity` merges inherited methods+properties before filtering/totals/slicing (new `entities_index` param, default `None` — old callers unaffected, verified byte-identical). `total_properties`/`total_methods` stay own-only; added `total_properties_including_inherited` / `total_methods_including_inherited`. `inherited_from` survives `summary_only` truncation (added to method and property summary shapes, matching `casting_notes`' treatment).
- **Deviation from literal spec, disclosed:** `has_more`/`next_offset` were previously computed from `total_methods` alone — properties had no signal at all. Fixing this only for merged entities was insufficient: IFsClosedValue has 14 combined methods vs 31 combined properties, so the old method-only signal went `False` after page 3 while 16 properties remained unreachable. I widened the fix to `methods_has_more OR properties_has_more` for **all** entities (not just I*-merged ones), since this is a real pre-existing bug the spec explicitly called out ("or pagination will under-report remaining pages") and DEC-3 frames it as internal wiring, not contract-breaking. No existing test asserts the old (wrong) value.
- **T2.4** `resolve_pythonic_property` gets an ancestor-aware fallback, gated the same way, firing only when the exact match returns nothing. Fixed a mutation bug I introduced in an early draft: `by_pythonic_name` matches are shared index objects — tagging `inherited_from` needed `dict(m)` copies first, or the tag would leak into unrelated lookups. Regression test (`test_fallback_does_not_mutate_shared_index`) locks this.
- **T2.5** New file `tests/test_issue86_inheritance_resolution.py`, 24 tests, 2 independent ancestor-chain examples (IFsClosedValue/FeatureRA/IFsFeatureSpecification and IChkTerm/ConfidenceRA/ICmPossibility).

## Counts

IFsClosedValue: 2 own -> 31 total properties, matching spec exactly. `total_properties` stays 2.

## validators._interface_member_names assertion

Passed for both sample pairs, unedited, confirming DEC-5's claim (works today only because `interfaces` is pre-flattened).

## Test results

977 passed, 2 skipped (baseline 953 passed + 24 new = 977; no regressions).
