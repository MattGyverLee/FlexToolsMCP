# Domain Review — cycle 1: Inheritance Resolution in Navigation Graph

**Date:** 2026-08-12
**Domain:** FLEx/LCM linguistic data model (grammar/MSA feature structures)
**Reviewer:** Domain Expert Agent

> Persisted by the orchestrator: lex-domain runs with Read/Grep/Glob/WebFetch
> only and had no write tool. Body is verbatim from the agent's return.

## 1. Path vs. "no path, cast advised"

Neither pure form is correct pedagogy. A bare path (cast baked in silently as an
edge) teaches a *false* mental model: it implies `MorphoSyntaxAnalysisRA ->
MsFeaturesOA` is a uniform, always-present relationship, when in LCM the MSA
slot is genuinely polymorphic — a sense's grammatical payload only exists on
the concrete POS-specific subtype the entry actually has. Users who copy that
code will hit `AttributeError` the first time they run it on an affix entry,
with no clue why. Conversely, flat "no path" is also wrong — it implies a dead
end, when in fact there IS a well-known, teachable route. The correct answer
is a **labeled/conditional path**: Sense -> MSA (generic) -- *requires cast* ->
IMoStemMsa -> MsFeaturesOA -> FeatureSpecsOC -> *cast* -> IFsClosedValue ->
ValueRA -> IFsSymFeatVal. This is the only framing that both gets the user
working code AND correctly teaches that MSA is a base-type slot, which is
exactly the lesson `_add_polymorphic_warnings` is designed to deliver.

## 2. Wrong-subtype BFS harm for MSA subtypes

Confirmed via casting_index (`unique_properties_by_type`): only `IMoStemMsa`
(and the less user-facing `IMoDerivStepMsa`) expose a plain `MsFeaturesOA`.
`IMoInflAffMsa` uses `InflFeatsOA`, `IMoDerivAffMsa` uses `FromMsFeaturesOA`/
`ToMsFeaturesOA` (no direct `MsFeaturesOA`), and `IMoUnclassifiedAffixMsa` has
no feature property at all. In a typical lexicon, stem/root entries vastly
outnumber affixal entries, so `IMoStemMsa` is the statistically correct
default. If edge generation orders subtypes alphabetically, `IMoDerivAffMsa`
comes first — a BFS pick there would emit code referencing a property that
literally doesn't exist on that class, or (worse) silently returns None if a
`getattr(default=None)` pattern is used, matching the exact silent-misread
pattern in Q3. This is worse than no path: "no path" is an honest gap that
sends the user to documentation; a wrong-subtype path is confidently wrong,
runs without immediate error, and a linguist without engineering background
has no independent way to catch it before it corrupts a batch report.

## 3. Issue #86 — FeatureRA hidden, LongName parsing

Confirmed: `FeatureRA -> IFsFeatDefn` (the feature name, e.g. "Noun Class") and
`ValueRA -> IFsSymFeatVal` (the value, e.g. "NC 4") are the structured pairing
mechanism inside `FeatureSpecsOC`. If `get_object_api` hides `FeatureRA`
(inherited-property suppression), users lose the only reliable name/value
correlation and fall back to `LongName`, a display string. This fails two
independent ways: `FeatureSpecsOC` is an *unordered* `ILcmOwningCollection`
(per the index), so positional parsing has no contractual basis; and Swahili
noun-class values ("NC 4", "NC 1a") contain embedded spaces, breaking
delimiter-based parsing even if position were abandoned. This silently
misreports linguistic feature data as authoritative with no exception raised —
it won't be caught on English-only test data. Severity: **High** — it doesn't
mutate the FieldWorks project, but it corrupts the *read* path feeding any
downstream export/analysis script, which is functionally data-corrupting for
the user's research output even though the source DB stays intact.

## 4. Recommendation

Both, combined: add downcast edges to the graph tagged with a `required_cast`
field, scoped to the single dominant concrete subtype per casting_index's
existing `base_type`/`concrete_types` mapping (IMoStemMsa for MSA), and keep
the `_add_polymorphic_warnings` advisory attached to those edges listing the
other subtypes and their differently-named equivalents (InflFeatsOA, From/To
MsFeaturesOA) as alternates — not as competing BFS edges. This gives the
common case working code while still teaching, and warning about, the
polymorphism.

## Files read (no edits made)

- `src/flextoolsmcp/server/handlers/discovery.py`
- `src/flextoolsmcp/index/casting_index_liblcm-v11.0.0.json`
- `src/flextoolsmcp/index/liblcm/liblcm_api_v11.0.0.json`

---
**Reviewed By:** Domain Expert Agent
