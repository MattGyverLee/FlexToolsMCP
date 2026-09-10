# Verification: issue #135 LibLCM Core-namespace fix (cycle 1)

**Verdict: PASS**

Read-only verification against `liblcm_extractor.py` diff (HEAD vs. working
tree) and the four regenerated index JSONs. No refresh run, no edits, no
commit performed by this agent.

## 1. Nothing dropped

Diffed HEAD's `liblcm_api_v11.0.0.json` (1878 entities) vs. working tree
(2026 entities): `set(HEAD) - set(CUR)` = **0** dropped entities. Checked
every entity present in both for shrinkage in `methods`/`properties` array
length: **0** entities shrank. All 148 new entities are additive.

## 2. Noise check

New-entity namespace breakdown (148 total): Text 53, KernelInterfaces 47,
Scripture 19, WritingSystems 15, Cellar 6, SpellChecking 6, **Phonology 2**
-- matches claim exactly. Regex-scanned all 148 added names for
`Class_\d|yy|tokens|Nfa|Dfa|Lexer|Parser|Regex|Environment_\d|LeftContext_\d|
RightContext_\d|OptionalSegment_\d|TermSequence_\d|Term_\d|Segment_\d|
Literal_\d|Ident$` -- **0 matches**, i.e. no CSTools-generated machinery
leaked. Confirmed `SIL.LCModel.Core.Phonology` added entities are exactly
`['PhonEnvRecognizer', 'SyntaxErrType']`, matching `NAMESPACE_TYPE_ALLOWLIST`.
Full-index scan for any entity whose namespace starts with
`SIL.LCModel.Tools` -- **0 leaked**. Confirmed presence + correct namespace
for all 8 named types (ITsString, ITsTextProps, ITsStrBldr, ITsIncStrBldr,
ITsStrFactory, ITsPropsBldr, FwTextPropType -> KernelInterfaces;
TsStringUtils -> Text).

## 3. Downstream consistency

- **casting_index**: `class_name_mapping` grew 660->693 entries (85->103
  concrete classes not separately indexed -- same ~13% ratio as HEAD, not a
  regression, since only interfaces are indexed as entities by design). All
  693 mapped *interfaces* resolve into the current 2026-entity set (0
  dangling). Confirmed new concrete->interface pairs present: `TsString ->
  ITsString`, `TsStrBldr -> ITsStrBldr`, `TsTextProps -> ITsTextProps`,
  `TsPropsBldr -> ITsPropsBldr`.
- **navigation_graph**: `entities` key set is **exactly equal** to the
  liblcm entity set (2026 == 2026, symmetric diff empty). `graph` has 298
  nodes, 909 edges recorded in `statistics`, **0 dangling edge targets**.
  New Core/Ts-family types have 0 graph edges, which is expected and
  correct -- they are value types (ITsString etc.), not owned `CmObject`
  entries in the ownership hierarchy the nav graph models.
- **reverse_mapping**: the 9-line delta is **not** attributable to this
  fix. `by_liblcm_entity` key count is unchanged at 211 in both HEAD and
  working tree (it indexes only entities Flexicon source actually
  references, not all liblcm entities), and the diff content -- `ITsString`
  dropped from `ConstChartRowOperations.wraps_interfaces`,
  `WritingSystemOperations.method_count` 23->25 -- lines up with the
  parallel, unrelated Flexicon 4.7.0->4.8.0 bump visible in `git status`
  (`flexicon_api_v4.7.0.json` deleted, `v4.8.0.json` added). Confirmed all
  211 `by_liblcm_entity` keys still resolve in the current 2026-entity
  index (0 dangling).

## 4. Server surface

In-process, via `flextoolsmcp.server.kernel.initialize_kernel()` +
`handlers.api.handle_get_object_api` with `session_state.api_mode =
"liblcm"`: `ITsString` found=True (13 methods, 3 properties),
`ITsTextProps` found=True (5 methods, 2 properties), `FwTextPropType`
found=True (0 methods/properties -- correct, it's an enum). `
search_by_capability("writing system of a text run")` returned
`ILgWritingSystemFactory` (`SIL.LCModel.Core.KernelInterfaces`) in the top
results -- new Core types are discoverable via semantic/keyword search, not
just direct lookup. Note: `_contract`/`status` envelope keys are added by
the outer MCP dispatch wrapper, which I bypassed by calling the handler
directly; this is a test-harness artifact, not a defect.

## 5. Tests

`python -m pytest -q`: **1382 passed, 8 skipped**, 0 failed. No new
failures attributable to this change.

## Blockers
None.

## Recommendation
APPROVE.
