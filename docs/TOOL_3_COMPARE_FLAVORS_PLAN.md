# Tool 3: `flextools_compare_flavors` — Plan & Todo

Status: **NOT IMPLEMENTED.** Plan only. Tools 1 (`get_wrapper_dependencies`) and 2 (`find_wrappers_for_lcm`) are live; Tool 3 builds on both.

## Purpose

Show the same operation expressed in all three flavors side-by-side: flexicon wrapper, flexlibs_stable wrapper, raw liblcm. Help users (and the LLM) pick the right flavor for a task and understand the trade-offs.

## When to build

Wait until Tools 1 + 2 have actually been used in real sessions. If the LLM consistently solves cross-flavor questions by chaining Tools 1 + 2 manually, Tool 3 may be unnecessary syntactic sugar. If users keep asking "show me the same thing in all three", that's the signal.

## Design

### Inputs

```python
class CompareFlavorsInput(BaseModel):
    """Show how the same operation looks across flexicon, flexlibs_stable, and liblcm."""
    query: Optional[str] = Field(
        default=None,
        description="Natural-language operation description (e.g. 'get headword for entry'). Mutually exclusive with `operation`."
    )
    operation: Optional[str] = Field(
        default=None,
        description="Specific wrapper method to compare (e.g. 'LexEntryOperations.GetHeadword'). Tool will reverse-resolve to LCM and stable equivalents."
    )
    include: list[str] = Field(
        default_factory=lambda: ["flexicon", "flexlibs_stable", "liblcm"],
        description="Which flavors to include. Omit a flavor if you don't need it."
    )
    show_examples: bool = Field(
        default=True,
        description="Include code examples per flavor when available."
    )
```

Exactly one of `query` or `operation` required.

### Output shape

```json
{
  "found": true,
  "matched_on": "operation" | "query",
  "anchor": {
    "library": "flexicon",
    "class": "LexEntryOperations",
    "method": "GetHeadword",
    "signature": "GetHeadword(entry_or_hvo)",
    "summary": "Get the headword for an entry."
  },
  "flavors": {
    "flexicon": {
      "available": true,
      "class": "LexEntryOperations",
      "method": "GetHeadword",
      "signature": "GetHeadword(entry_or_hvo)",
      "example": "<from index if show_examples>",
      "import": "from flexicon import LexEntryOperations",
      "tradeoff_notes": ["Returns clean Python str", "Handles '***' multistring placeholder"]
    },
    "flexlibs_stable": {
      "available": true | false,
      "class": "FLExProject",
      "method": "LexiconGetHeadword",
      "signature": "LexiconGetHeadword(entry)",
      "example": "<from index>",
      "import": "(no import needed; on project)",
      "tradeoff_notes": ["Direct project method", "Returns IMultiUnicode in some paths"]
    },
    "liblcm": {
      "available": true,
      "entity": "ILexEntry",
      "member": "HeadWord",
      "kind": "property",
      "type": "ITsString",
      "casting_required": false,
      "tradeoff_notes": ["Raw LCM property", "Returns ITsString — call .Text for plain string"]
    }
  },
  "gaps": [],
  "session_mode": "flexicon",
  "advisory": "<contextual advice if user is in a mode missing from results>"
}
```

If a flavor lacks coverage, its block has `available: false` and `gaps` lists the missing flavors.

### Resolution algorithm

**`operation` path**: anchor is the named wrapper method.
1. Look up `operation` in the appropriate bridge file via Tool 1 logic → get LCM internals (factories, properties, methods called).
2. From those internals, identify the primary LCM call site. Heuristic:
   - If `methods_called` is non-empty and `properties_accessed` is empty → primary is the first method in `methods_called`.
   - If `properties_accessed` is non-empty → primary is the first property access.
   - Otherwise, use `factories_used` if present.
3. Use Tool 2's reverse mapping to find the *other* wrapper (stable if anchor was flexicon, vice versa) that covers the same LCM symbol.
4. Build the liblcm block from the LCM symbol directly (look up in `api_index.liblcm.entities` to get type, kind, signature).

**`query` path**: anchor is whichever flavor matches best.
1. Run `search_by_capability` against all three sources internally with the query.
2. Pick the top result as anchor (prefer flexicon > flexlibs_stable > liblcm if scores are close).
3. Resolve to other flavors via the same logic as the `operation` path, using Tool 1 and Tool 2.

### Edge cases & rules

- **Casting hints**: when the liblcm block returns a polymorphic type, include a casting note pulled from `casting_index_liblcm-v11.0.0.json`. Reuse the polymorphic-collection logic from `resolve_property`.
- **Empty multistring**: any flavor returning a multistring should note that flexicon normalizes `'***'` to `''` while raw liblcm does not. Pull this from the existing `KEY_IS_MULTISTRING` / `KEY_EMPTY_VALUE_WARNING` machinery.
- **Mode coherence**: if `session_mode` is not in `include`, surface an advisory ("you're in flexicon mode but didn't ask for flexicon — most users want this included").
- **No anchor found**: return `{"found": false}` with hints to try `search_by_capability` or `find_wrappers_for_lcm` directly.

### What it composes

| Calls into | Why |
|---|---|
| `flexicon_lcm_bridge` (Tool 1's data) | Resolve flexicon method → LCM internals |
| `flexlibs_lcm_bridge` (Tool 1's data) | Resolve flexlibs_stable method → LCM internals |
| `reverse_mapping` (Tool 2's data) | Resolve LCM symbol → wrapper coverage in *other* libraries |
| `api_index.liblcm["entities"]` | Get the liblcm-flavor signature, kind, type |
| `api_index.casting_index` | Casting hints for polymorphic types |
| `search_by_capability` (existing) | When `query` mode is used, find the anchor |

Tool 3 is a true *aggregator* — it adds no new data, just composes the three sources into one coherent answer. Worth waiting until composition friction is observed before building.

### Risks

- **Heuristic fragility**: picking the "primary LCM symbol" from `lcm_internals` is a heuristic. If a wrapper method calls multiple LCM methods/properties, the wrong one might anchor the comparison. Mitigation: include a `multiple_lcm_targets: true` flag and surface all candidates if heuristic confidence is low.
- **Search quality**: the `query` path leans on `search_by_capability`'s ranking. If that ranking is fuzzy, Tool 3 will be fuzzy too. Mitigation: keep `operation` as the precise path and document `query` as best-effort.
- **Cross-mode bleed (regression risk)**: Tool 3 by design surfaces all three flavors in one response. Make sure it's only invoked explicitly and never auto-called from other handlers — the source-isolation guarantee for `get_object_api`/`search_by_capability` must not regress.

## Todo

- [ ] **Trigger check**: confirm with usage data that Tool 3 is needed (look for repeated Tool 1 → Tool 2 chains in transcripts).
- [ ] Write `CompareFlavorsInput` in `src/server/models.py`.
- [ ] Add `handle_compare_flavors` in `src/server/handlers/equivalence.py` (same file as Tools 1 + 2).
- [ ] Implement `_resolve_operation_to_anchor(operation, library)` helper.
- [ ] Implement `_resolve_query_to_anchor(query, include)` helper, calling `search_by_capability` internals.
- [ ] Implement `_pick_primary_lcm_symbol(lcm_internals)` heuristic; return `(symbol, kind, confidence)`.
- [ ] Implement `_build_flavor_block(library, anchor, lcm_symbol, show_examples)` — fan-out for each flavor.
- [ ] Implement gap detection across `include` list.
- [ ] Add `TOOL_COMPARE_FLAVORS = "flextools_compare_flavors"` to `dispatch.py` (constant + ALL_TOOL_NAMES + handler import + dispatch entry).
- [ ] Add `ToolDef` entry in `tool_definitions.py` with `READ_ONLY_SAFE`.
- [ ] Add response key constants if needed (`KEY_FLAVORS`, `KEY_TRADEOFF_NOTES`, `KEY_ANCHOR`, `KEY_AVAILABLE`, `KEY_MATCHED_ON`).
- [ ] Reuse casting-hint logic from `resolve_property` rather than re-implementing.
- [ ] Tests:
  - [ ] `operation`-mode: `LexEntryOperations.GetHeadword` returns three populated flavor blocks.
  - [ ] `operation`-mode: a flexicon-only wrapper returns `flexlibs_stable.available=false` with gap surfaced.
  - [ ] `query`-mode: "get headword for entry" lands on a sensible anchor.
  - [ ] `include=["liblcm"]` returns only the liblcm block.
  - [ ] Multistring case (e.g. `LexSenseOperations.GetGloss`) surfaces the `'***'` normalization advisory.
  - [ ] Polymorphic case: liblcm block includes casting hint.
  - [ ] Bogus inputs return `found=false` with hints.
- [ ] Update CLAUDE.md tool count if it lists one.
