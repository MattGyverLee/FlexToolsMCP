# Domain Expert Review -- parser-check tasks.md, cycle 5 (Phase 4 / US2: T014-T021, T027)

> **Provenance note.** Authored by `lex-domain` in cycle 5. The agent has no write tool
> (Read/Grep/Glob/WebFetch only), so the main session persisted this body verbatim to the
> path the dispatch plan specified. Content is lex-domain's, unedited.

All property/type names below were checked against
`src/flextoolsmcp/index/liblcm/liblcm_api_v11.0.0.json` directly (not through the MCP
tool layer, which wasn't in this agent's toolset).

## P0 -- blocks implementation

**1. T019's `"***"` -> `""` claim is backwards for this code path.**
`IMoForm`'s `python_wrappers.flexlibs_2` lists
`CustomFieldOperations`/`LexEntryOperations`/`WfiMorphBundleOperations` but with
`"methods": []` -- there is no Operations wrapper that normalizes `IMoForm.Form`. Per
CLAUDE.md's own documented convention, direct C# property access (which is exactly what a
generated-module scan over `IMoForm`/`IPhSegmentRule`/etc. does -- these are grammar
objects, not Flexicon lexicon-entry wrappers) still returns `"***"` for empty
multistrings, not `""`. T019's line "Empty multistrings normalize to `""`, never `"***"`"
will cause rows 1 and 6 (zero-surface morph / `IsComplete`) to silently match nothing,
because the emptiness test will look for `""` while the LCM data actually holds `"***"`.

**Fix T019:** treat `form in ("", "***")` as empty, or explicitly call out that this scan
reads LCM directly and must check for `"***"`, not rely on Flexicon's normalization
(which doesn't apply here).

**2. Rows 5, 7, and row 3's metathesis half have no landing task regardless of T016's
outcome.**
T016 exists precisely so each of `IMoAffixProcess`, `IPhMetathesisRule`,
`ILexEntry.AlternateFormsOS` "either becomes a written check or is named in
`checks_skipped`." But T019 (the only scan-writing task) hardcodes "rows 1, 2, 4, 6, 9,
10 ... plus row 3's epenthesis half ... and row 8" and never mentions `IPhMetathesisRule`,
`IMoAffixProcess`, or `AlternateFormsOS` at all -- not as written checks, not as
`checks_skipped` entries. If T016 confirms these names (I confirmed all three exist in the
index: `IMoAffixProcess` and `IPhMetathesisRule` are real entities,
`ILexEntry.AlternateFormsOS` is a real `OS` property), nothing in the task list wires them
anywhere, which is the exact silent-omission failure the contract
(`flextools_grammar_health.md`, "checks_skipped") warns against.

**Fix:** add explicit branching to T019: on T016 confirmation, add row 5 (`affix-process
rule count x (IPhRegularRule + IPhMetathesisRule) count`, gated by `Disabled`) and row 3's
metathesis half; add row 7's `AlternateFormsOS.Count > 1` half. Anything T016 cannot
confirm must appear in `checks_skipped` -- never dropped silently.

## P1 -- must fix before the task runs

**3. Row 7's `StemNameRA` half is already verified and shouldn't be gated at all.**
I confirmed `IMoStemAllomorph.StemNameRA` (kind `RA`, target `IMoStemName`) exists in the
index -- matching research D4's "PARTIAL...StemNameRA VERIFIED" note. T016 correctly gates
only `AlternateFormsOS` (the actually-outstanding half), but the task list should say
explicitly that row 7 is two independently-gateable sub-checks, so an implementer doesn't
wait on `AlternateFormsOS` confirmation before writing the `StemNameRA` half.

**4. Row 8's mapping is correct, but `OrderNumber` comparability needs a caveat.**
Confirmed: `IMoStratum`'s own properties are exactly `Abbreviation`, `Description`,
`Name`, `PhonemesRA` -- no rule collection, matching research's refutation.
`IPhSegmentRule` declares `OrderNumber` (Int32) and single-valued
`InitialStratumRA`/`FinalStratumRA` (each `RA`, target `IMoStratum`, cardinality one).
Because each rule references exactly one initial/final stratum pair (not a list),
`OrderNumber` is only meaningfully comparable among rules sharing the same
`(InitialStratumRA, FinalStratumRA)` pair -- it is very likely a per-stratum-pair counter,
not a grammar-wide ordinal.

**Fix T019/T027:** add "`OrderNumber` is comparable only within the same stratum-pair
grouping; never sort/compare it across different pairs."

**5. SPEC 9.5.4's own implementation note is now stale relative to research D4**, and T027
doesn't fix it. It still says "only rows 2, 4 and 9 have had their LCM property names
verified," but D4 (and my own index check) confirms rows 1, 2, 3 (epenthesis half), 4, 6,
8 (corrected), 9, and 10 are verified -- only rows 3's metathesis half, 5, and 7
(partially) remain outstanding, which is exactly what T016 targets. T027 currently only
fixes the row-8 text.

**Fix T027:** also update the "only rows 2, 4, 9 verified" sentence to match D4's actual
state, or it will mislead the next implementer the same way row 8 did.

**6. Row 1's "reachable from an optional slot or a self-looping position" is not
implemented by T019 at all.**
T019's row-1 check uses only `IMoForm.Form` (emptiness), with no graph walk from
`IMoInflAffixSlot.Affixes` to the owning allomorph. This is computable (slot -> `Affixes`
-> MSA -> owning entry -> `AlternateFormsOS` -> `IMoForm.Form`) but T019 as written will
flag every zero-surface `IMoForm` regardless of position, which is broader than the spec's
stated pathology and than the 425x evidence basis (which was specifically about
repeatable/optional-slot placement).

**Fix:** either implement the slot-reachability walk, or narrow the `measured` wording to
not claim position-conditioning it doesn't perform.

## P2 -- nice to have

**7.** `Disabled`/`OrderNumber`/`InitialStratumRA`/`FinalStratumRA` are declared once on
`IPhSegmentRule` and not redeclared in `IPhRegularRule`'s or `IPhMetathesisRule`'s own
`properties` array in the index (only their `interfaces` list names `IPhSegmentRule`).
Functionally this is fine -- C#/pythonnet inheritance makes these members accessible on any
object satisfying either derived interface -- but a future implementer who looks up
`IPhRegularRule` via `flextools_get_object_api` won't see `Disabled` there. Worth a
one-line note in T019 pointing at the base interface.

**8.** `IMoInflAffixSlot` confirmed **not** `ICmPossibility`
(`interfaces: [ICloneableCmObject, ICmObject, ICmObjectOrId]`). Its own `Name`
(`IMultiUnicode`), `.Optional` (Boolean), and `.Affixes` (IEnumerable) are all its own
declared properties -- T015's assertion is correct.
