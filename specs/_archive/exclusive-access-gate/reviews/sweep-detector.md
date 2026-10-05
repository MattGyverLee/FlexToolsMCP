# Pattern audit: receiver/name matching and role disambiguation (T039)

Original site: `src/flextoolsmcp/server/exclusive_access.py`
`detect_exclusive_only_operations` (with `_wrapper_matches`, `_raw_matches`).

Bug class: a static detector assigns the wrong role to a call by (1) matching
a generic method name on an untyped receiver, (2) matching a receiver by
substring instead of exact identifier, or (3) treating a loop/with element as
an alias of its collection. Swept with the `sweep-pattern` skill (Explore,
very thorough) over `src/flextoolsmcp/server/`, 2026-09-30.

## The detector itself

Already guarded in the shipped code, with tests:

- (1) Untyped receivers match wrapper names by name alone **except**
  `Create`/`Delete` (`_GENERIC_WRAPPER_NAMES`), which are mutating on ~50 other
  Operations classes and every raw LCM factory
  (`test_j_generic_names_on_untyped_receivers_do_not_match`). Raw generic
  methods (`Set`, `Add`, `Save`, ...) match only on the exact WS manager / list
  / services receivers (`test_n_generic_names_on_unrelated_receivers`).
- (2) Raw receivers are compared as exact identifier components
  (`_chain_names`), never substrings.
- (3) The raw alias map binds only `Assign`/`AnnAssign`/`NamedExpr` targets,
  never `for` or `with` targets (`test_iterating_a_ws_list_is_not_a_mutation`).

Probed against the sweep's shapes (scratch run):

| Shape | Result | Verdict |
|---|---|---|
| `for ws in project.WritingSystems.GetAll(): ws.Delete()` | no match | correct |
| `for ws in lp.CurrentVernacularWritingSystems: project.LexEntry.Create(...)` / `items.Add(ws)` / `ws.Remove(x)` | no match | correct |
| `for x in project.WritingSystems: x.Create(...)`, `with project.WritingSystems as w: w.Ensure(...)` | match (via the certifier's `_iter_assign_pairs` for/with binding) | Harmless: iterating or `with`-binding the Operations object is not real code |
| `old_project.CustomFields.CreateField(...)`, `subproject.WritingSystems.Create(...)` | match (certifier Step 1c regex has no `\b`) | Correct in substance: any `.CustomFields.CreateField` / `.WritingSystems.Create` is a schema change, whatever the facade variable is called |

**No confirmed sibling in the detector; no fix needed.**

## Pre-existing siblings in the write gate (out of scope here)

These over-match the existing `unprotected_writes` / `is_cud` gates, which
fail closed on purpose, and one under-matches. None is introduced or worsened
by this feature. They are listed as follow-up candidates for
`issues/filing-ledger.md`; filing needs the maintainer's OK.

| Site | Shape | Effect | Confidence |
|---|---|---|---|
| `validators.py:5982-5989`, skip at `6009-6010` / `6056-6060` (`_collect_local_container_names`) | (3) | A loop target over a list of LCM collections (`for coll in [e.SensesOS, f.SensesOS]: coll.Add(s)`) is marked a "local container", so the real `.Add` is **dropped** from `find_liblcm_mutations`: a missed unprotected write | HIGH (sweep, not reproduced) |
| `validators.py:5995-6011` | line-keyed skip | A local list's `.Add` on the same line hides a real LCM `.Add` (the shape Cycle 2 Finding A removed from Step 2b) | MED |
| `validators.py:100` `_PATTERN_PROJECT_ACCESSOR_CALL`; `160-165` facade templates; `65/73/86` CUD patterns; `137-144`/`79-85` property regex; `62-64` | (2) no left `\b` | `myproject.X.Delete(`, `position.Note = ...` count as writes | HIGH/MED, over-match only |
| `validators.py:122-126`, `58`, `69`, `133`, `135` | (1) any receiver | `sb.Clear()`, `File.Delete(p)`, `promise.Reject()` count as writes / CUD | MED/LOW, over-match only |
| `validators.py:6595-6596` Step 2b | (1) | Untyped `factory.Create()` becomes a suspected mutation: deliberate fail-closed (comment 6578-6588). This feature's detector already excludes Create/Delete from name-only matching | MITIGATED |
| `validators.py:2751-2756` `_iter_assign_pairs` | (3) | for/with target bound to the whole iterable; documented as "over-typing is safe" | MITIGATED |
| `validators.py:5826`, `local_recipes.py:503-521`, `validators.py:970,1038`, `1561-1565` | (1) | diagnostic text, coarse backup check, specific names, suggestion ranking | MITIGATED / not a detector |

Clean: `filing/`, `_resolve_receiver_ops_class`, `find_protected_ranges`.
