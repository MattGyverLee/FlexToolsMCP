# Original Author Review -- cycle1 -- inheritance-resolution

**Date:** 2026-08-12
**Reviewer:** Original Author Agent (read-only)

> Persisted by the orchestrator: lex-author runs with Read/Grep/Glob only and
> had no Write tool. Body is verbatim from the agent's return.

## 1. Output shape: (a) inline `inherited_from` tag

Reject (c): `interfaces`/`base_classes` are already exposed today -- shipping
only an ancestor list is the status quo, not a fix; it forces exactly the
extra discovery round-trip issue #48 was written to eliminate ("resolve_property
is not reliably called... teach cast-correct code on the first draft").
Reject (b): a second top-level block doubles pagination/offset math and
`summary_only` truncation logic that `paginate_entity` already owns for one
list; no precedent for parallel paginated blocks in this codebase.
Choose (a): `paginate_entity` (api.py:420) already merges synthetic entries
into the single `properties` list before counting (the `FLExProject`
Operations-accessor block, line 484-498) -- inline merging is the established
pattern, not a novel one. Token cost is one short string key per inherited
row; it survives `summary_only` cheaply (add `inherited_from` to the
3-field-max summary shape, same treatment `casting_notes` gets). An AI caller
distinguishes own-vs-inherited with a single `.get("inherited_from")` check.

**Implementation note (verified in `liblcm_extractor.py:698`):** `interfaces`
is built from .NET's `t.GetInterfaces()`, which is *already the full
transitive closure*, not just immediate parents -- one pass over
`entity["interfaces"]` is enough for interface ancestors, no recursive walk
needed. `base_classes` (line 695-696) is NOT flattened -- only `t.BaseType`
(one level) -- so class-inheritance chains >1 level need an actual walk.
Property source is `BindingFlags.DeclaredOnly` (line 656), confirming each
entity's own list is genuinely own-only today.

## 2. `total_properties` semantics

Recommend: **keep `total_properties` byte-identical (own-only)**, add
`total_properties_including_inherited`. `total_properties` isn't in
TOOL-CONTRACT.md's stability table at all, but the project's unbroken
precedent (`update_notice`, `diagnostic_report`, `auto_discovered`) is
additive-only, never redefine an existing field's meaning. Caveat that must
land with the fix: `KEY_HAS_MORE`/`KEY_NEXT_OFFSET` (api.py:478-480,
mirrored for properties) currently key off `total_properties` for pagination
math -- once the paginated candidate list includes inherited members, that
math must switch to the new combined total internally, or pagination
under-reports remaining pages. That's an internal wiring fix, not a
contract change.

## 3. Version bump: not warranted

Both additions (`inherited_from` per-item, `total_properties_including_inherited`
top-level) are additive-optional fields on an unversioned tool-data shape --
same category as every prior additive change in CHANGELOG.md, none of which
bumped `tool-responses/1.0`. Only the CHANGELOG "Tool contract" heading is
reserved for removals/renames (see #54 entry); this is a normal `Added` line.

## 4. Cross-tool consistency invariant

> For every `(property, concrete_type)` pair where `property` is declared
> (own, `DeclaredOnly`) on some `A` in `concrete_type`'s `interfaces`
> closure: `get_object_api(concrete_type)` MUST list `property` in
> `properties` with `inherited_from == A`, AND
> `resolve_property(property, context_entity=concrete_type)` MUST return
> `found: True` for that same `concrete_type`.

Caution: `validators._interface_member_names` (validators.py:765-798) is a
**third** surface with the same class of bug -- it only recurses one level
below `_depth == 0`. Because `interfaces` is pre-flattened, single-hop
interface lookups happen to work today, but this function also folds in
`base_classes` implicitly via entity properties/methods and would break for
class-inheritance chains >1 level. The consistency test should sample against
this typo-preflight path too, not just the two discovery tools named in the
ticket.

## 5. Docs to update in the same PR

- `docs/TOOL-CONTRACT.md` -- add a short additive-field section (pattern:
  `update_notice`/`diagnostic_report` sections) documenting `inherited_from`
  and `total_properties_including_inherited`.
- `CHANGELOG.md` -- `Added` entry, not under "Tool contract" heading.
- `docs/LIBLCM_CONTEXTUAL_ANALYSIS.md` if it documents `interfaces`/
  `base_classes` semantics -- note the `GetInterfaces()` full-closure vs
  `BaseType` single-level asymmetry, since implementers will hit it.

**Recommendation:** APPROVE the direction (a) + additive fields, contingent
on fixing the internal pagination-total wiring and covering
`_interface_member_names` in the consistency test.

---
**Reviewed By:** Original Author Agent
