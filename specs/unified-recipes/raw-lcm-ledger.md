# Raw LibLCM ledger (recipe batch 1)

A deduplicated log of every raw LibLCM access in the harvested recipe sources.
Each access is classified as either a **rewrite** (a flexicon interface exists,
so the recipe must use it) or a **gap** (flexicon has no equivalent, so the
recipe keeps raw LCM with a `# flexicon gap: <issue>` note, and a flexicon
issue is filed). This is the working list behind FR-045 and research R18.

- **Source scanned**: the 13 MCPlayground `flex-parse-fixup/scripts/lib/`
  scripts mapped to FR-050 recipes 1-13. Recipes 14-16 (`create-text-from-lines`,
  `create-variant-entries`, `affix-template-setup`) come from logs, not
  files; add their rows when they are written.
- **Classified against**: flexicon 4.11.0 index (`flexicon_api_v4.11.0.json`)
  and bridge index (`flexicon_lcm_bridge_v4.11.0.json`); LibLCM 11.0.0 index.
- **Regenerate**: `python specs/unified-recipes/tools/scan_raw_lcm.py > scan.json`
  (AST scan; prints every access with call sites and bridge candidates).
- **Scan date**: 2026-09-27. The scan found 86 distinct accesses: 26 interface
  casts, 1 `ClassName` dispatch, 2 escape hatches and 57 members.

## How to use this file

1. When a recipe is ported, every access it keeps must appear here as a
   **gap** with an issue number. Every access it drops must be a **rewrite**
   row whose suggested method was confirmed with `flextools_get_object_api`.
   Once confirmed, change the row's status from `proposed` to `confirmed`.
2. A new raw access found while porting gets a new row. Do not add a
   duplicate; extend the existing row's `Recipes` column.
3. Every gap row without an issue number (`TODO-file`) must be filed on
   `MattGyverLee/flexicon` before the recipe ships, and its number recorded
   here.
4. When a flexicon release closes a gap, the FR-045 gate starts failing
   the recipe's fallback. Flip the row to rewrite and update the recipe.
5. Casts are not tracked on their own. A cast exists only to reach the
   members listed against it, and it disappears when those members are
   rewritten. The cast table shows what each cast unlocks, so it is obvious
   which casts must remain (the ones that reach a gap member).

Status values: `proposed` (suggested from the index, not yet checked),
`confirmed` (checked with `get_object_api` at port time), `filed` (a gap
with an issue), `TODO-file` (a gap that still needs an issue).

Recipe abbreviations:

| Abbr | Recipe |
|---|---|
| cov | parser-coverage |
| look | lexicon-form-lookup |
| det | entry-parser-detail |
| wfa | wordform-analyses |
| use | form-usage-before-edit |
| tpl | affix-templates-and-slots |
| phon | phonological-rules |
| var | wordform-case-variants |
| cre | create-entries-idempotent |
| like | create-entry-like-comparator |
| env | set-allomorph-environments |
| aff | add-inflectional-affix |
| allo | add-allomorph |

---

## A. Rewrite: a flexicon interface exists

| Raw access | Recipes | Sites | Use instead | Status |
|---|---|---|---|---|
| `project.project` / `LangProject` (escape hatch) | aff, tpl, use, phon, env | 5 | the specific accessor below (`Environment.GetAll`, `PhonologicalRule.GetAll`, `WfiAnalysis` approval) | proposed |
| `PhonologicalDataOA` | allo, tpl, phon, env | 4 | `project.Environment.GetAll()`, `project.PhonologicalRule.GetAll()`, `NaturalClass.GetAll()`, `Phoneme.GetAll()` | proposed |
| `EnvironmentsOS` | allo, tpl, env | 3 | `project.Environment.GetAll()` | proposed |
| `StringRepresentation` (environment) | allo, tpl, det, env | 8 | `Environment.GetStringRepresentation` | proposed |
| `PhoneEnvRC` | det, env | 4 | `Allomorph.GetPhoneEnv` / `AddPhoneEnv` / `RemovePhoneEnv` | proposed |
| `LexemeFormOA` | det, use, env | 4 | `LexEntry.GetLexemeForm` for text; `Allomorph.GetAll(entry)` for objects (check whether the lexeme form is included) | proposed |
| `AlternateFormsOS` | det, use, look, env | 4 | `Allomorph.GetAll(entry)` | proposed |
| `Form` (MoForm) | det, use, look, env, wfa | 6 | `Allomorph.GetForm` | proposed |
| `IsAbstract` | det | 1 | `Allomorph.GetIsAbstract` (flexicon#546, looks landed in 4.11.0; confirm) | proposed |
| `MorphTypeRA` | det | 1 | `LexEntry.GetMorphType` / `Allomorph.GetMorphType` | proposed |
| `MorphoSyntaxAnalysisRA` | aff, tpl, cre, like, det, look | 7 | `LexSense.GetMSA` / `GetGrammaticalInfo` | proposed |
| `PartOfSpeechRA` | aff, cre, like, det | 8 | read: `LexSense.GetPartOfSpeechObject`; write: `MSA.SetStemMsaPos` (then restore inflection class; see gap B2) | proposed |
| `SlotsRC` (infl-affix MSA) | aff, tpl, det | 3 | `MSA.GetInflAffMsaSlots` / `SetInflAffMsaSlots`; create: `MSA.CreateInflAff(..., slots=)` | proposed |
| `Optional` (slot) | tpl | 2 | `POS.IsSlotOptional` | proposed |
| `AffixTemplatesOS` | tpl | 1 | `MorphRule.GetAllAffixTemplatesForPOS` | proposed |
| `MsFeaturesOA` (stem MSA) | cre, like, det | 5 | read: `MSA.GetStemFeatures` / `MSA.GetFeatures` (flexicon#544, confirm); write: `InflectionFeature.MakeFeatStruc(owner=)` | proposed |
| `InflFeatsOA` (infl-affix MSA) | tpl, det | 4 | `MSA.GetInflAffFeatures` (flexicon#544, confirm) | proposed |
| Feature-structure walk: `FeatureSpecsOC`, `FeatureRA`, `ValueRA`, `ValueOA` | det | 8 | `InflectionFeature.DescribeFeatStruc` | proposed |
| `AnalysesOC` | use, wfa | 2 | `Wordform.GetAnalyses` | proposed |
| `MorphBundlesOS` | use, wfa | 2 | `WfiAnalysis.GetMorphBundles` | proposed |
| `MorphRA` | use, wfa | 5 | `WfiMorphBundle.GetMorph` | proposed |
| `SenseRA` (bundle) | wfa | 2 | `WfiMorphBundle.GetSense` / `GetGloss` | proposed |
| `ParserCount` / `UserCount` | cov, var, wfa | 6 | `Wordform.GetAnalyses` + `WfiAnalysis.IsComputerApproved` / `IsHumanApproved`. A count helper is requested in B7 (flexicon#576); check that the composite matches `ParserCount` semantics on Sena 3 | proposed |
| `GetAgentOpinion`, `DefaultUserAgent`, `DefaultParserAgent` | use | 4 | `WfiAnalysis.GetApprovalStatus` / `IsHumanApproved` / `IsComputerApproved` | proposed |
| `Gloss` (sense / bundle) | aff, tpl, det, look, wfa | 4 | `LexSense.GetGloss`, `WfiMorphBundle.GetGloss` | proposed |
| `Guid` | env | 1 | `LexEntry.GetGuid` / `Allomorph` equivalent | proposed |
| `Hvo` comparisons | cre, use | 6 | compare objects or GUIDs (`GetGuid`); never HVOs | proposed |
| `Abbreviation` (phon feature) | phon | 1 | `PhonFeature.GetAbbreviation` / `NaturalClass.GetAbbreviation` | proposed |
| `Direction` (phon rule) | phon | 1 | `PhonologicalRule.GetDirection` | proposed |
| `PhonRulesOS` | phon | 1 | `project.PhonologicalRule.GetAll()` | proposed |
| `LongName` (MSA / entry display) | aff, tpl, cre, like, det, look | 7 | entries: `LexEntry.GetLongName`. MSAs: no getter yet (B5, flexicon#575) | proposed |
| Multistring reads: `BestAnalysisAlternative`, `BestVernacularAnalysisAlternative`, `VernacularDefaultWritingSystem` (+ `.Text`) | 11 of 13 | 40 | the owning getter (`GetGloss`, `GetForm`, `POS.GetName`, `GetSlotName`, `InflectionClassGetName`, ...). These are not flagged by the FR-045 regex; they disappear when their parent access is rewritten. Any that remain must carry a `raw-lcm:` note. | proposed |
| `ClassName` dispatch | aff, tpl, cre, det, look, phon, env | 17 | allomorph kind: `Allomorph.GetMorphType`; MSA kind: `LexSense.GetMSA` + a typed getter. The rest follow the phon gap (B1). No MSA-type getter exists yet: `MSA.GetMSAType` is requested in flexicon#575. Until then, MSA-kind checks keep `ClassName` with a `# flexicon gap: #575` note | proposed |

## B. Gap: no flexicon equivalent (keep raw LCM with a note, file an issue)

| # | Raw access | Recipes | Sites | Needed flexicon API | Issue | Status |
|---|---|---|---|---|---|---|
| B1 | Phonological rule internals not covered by the `PhonologicalRule` / `PhonologicalContext` wrappers (which already give `input_contexts`, `output_specs`, `direction`, segment and natural class, so `StrucDescOS` / `StrucChangeOS` / `RightHandSidesOS` are rewrites through the wrapper): `LeftContextOA` / `RightContextOA` (getters; only setters exist), `ExclRuleFeatsRC`, `ReqRuleFeatsRC`, `InputPOSesRC`, `FeatureStructureRA`, `MemberRA`, `MembersRS`, `Minimum` / `Maximum` (iteration context), `Disabled` (phon rule; only `MorphRule.IsDisabled` exists) | phon | 16 | a phonological-rule reader: `PhonologicalRule.GetInput/GetOutput/GetLeftContext/GetRightContext/GetRequiredFeatures/GetExcludedFeatures/GetInputPOSes/IsDisabled`, plus `DescribeRule(rule)` | flexicon#572 | filed |
| B2 | `InflectionClassRA` on a stem MSA (read and write) | cre, like, det | 7 | `MSA.GetInflectionClass(msa)` / `MSA.SetInflectionClass(msa, icl)`. Needed so the "restore inflection class after `SetStemMsaPos`" lesson (FR-053) can be written in flexicon | flexicon#573 | filed |
| B3 | ~~`PrefixSlotsRS` / `SuffixSlotsRS` on an affix template~~ | tpl | 2 | **Covered**: the `AffixTemplate` wrapper (from `MorphRule.GetAllAffixTemplatesForPOS`) has `prefix_slots` / `suffix_slots`; slot name and optional via `POS.GetSlotName` / `IsSlotOptional` (flexicon#542, closed). Treat as a rewrite | flexicon#542 | closed, confirm at port |
| B4 | `ProdRestrictRC` (MSA exception "features") | det | 1 | `MSA.GetProdRestrictions(msa)`. Not `LexEntry.GetRestrictions`, which is the Restrictions *text* field | flexicon#574 | filed |
| B5 | `LongName` on an MSA (display) | aff, tpl, cre, like, det, look | subset of 7 | `MSA.GetLongName(msa)` plus `MSA.GetMSAType(msa)` (which also removes most `ClassName` dispatch) | flexicon#575 | filed |
| B6 | ~~Infl-affix slot membership reader~~ | tpl | (in `SlotsRC`) | **Covered**: `MSA.GetInflAffMsaSlots` is in the 4.11.0 index (flexicon#543, closed) | flexicon#543 | closed |
| B7 | Parser/user analysis counts per wordform | cov, var, wfa | 6 | a convenience: `Wordform.GetParserCount` / `GetUserCount`. A composite with `GetAnalyses` works meanwhile, so this is optional | flexicon#576 (optional) | filed |

Other known gaps from the harvest that the 13 scripts did not hit: sense
`DoNotPublishIn` (flexicon#545) and the `AddSubcategory` catalog id
(flexicon#547). They may appear when recipes 14-16 are written.

## C. Casts and what they unlock

| Cast | Recipes | Sites | Reaches | Remains after port? |
|---|---|---|---|---|
| `IMoStemMsa` | cre, like, det | 12 | `InflectionClassRA`, `MsFeaturesOA`, `PartOfSpeechRA`, `ProdRestrictRC` | yes, until flexicon#573 (and #574 for `det`) |
| `IMoForm` | det, use, look, env, wfa | 8 | `Form`, `IsAbstract`, `MorphTypeRA` | no |
| `ILexEntry` | det, use, env | 7 | `LexemeFormOA`, `AlternateFormsOS` | no |
| `ILexSense` | aff, cre, like | 4 | `MorphoSyntaxAnalysisRA` | no |
| `IMoInflAffMsa` | aff, tpl, det | 3 | `SlotsRC`, `InflFeatsOA`, `ProdRestrictRC` | only for exception features, until flexicon#574 |
| `IMoInflAffixSlot` | tpl | 4 | `Optional`, name | no |
| `IMoInflAffixTemplate` | tpl | 1 | `PrefixSlotsRS` / `SuffixSlotsRS` | no (`AffixTemplate` wrapper) |
| `IPartOfSpeech` | tpl | 1 | `AffixTemplatesOS` | no |
| `IMoAffixAllomorph`, `IMoStemAllomorph` | det, env | 4 | `PhoneEnvRC` | no |
| `IWfiAnalysis`, `IWfiMorphBundle` | use, wfa | 4 | `MorphBundlesOS`, `MorphRA`, `SenseRA` | no |
| `IFsFeatStruc`, `IFsFeatureSpecification`, `IFsClosedValue`, `IFsComplexValue` | det | 8 | the feature-structure walk | no (`DescribeFeatStruc`) |
| `IPhSegmentRule`, `IPhRegularRule`, `IPhSegRuleRHS`, `IPhSequenceContext`, `IPhIterationContext`, `IPhSimpleContextSeg`, `IPhSimpleContextNC`, `IPhSimpleContextBdry`, `IPhPhonRuleFeat`, `ICmPossibility` | phon | 14 | B1 | partly: contexts and output via the wrappers; rule features, input POSes and iteration contexts until flexicon#572 |

## Summary

| | Distinct accesses | Notes |
|---|---|---|
| Rewrite (A) | about 60 | All proposed. Confirm each with `get_object_api` at port time. |
| Gap (B) | 5 open rows (about 15 accesses; `LongName` and the parser counts also appear in A because only part of their use is a gap) | All filed 2026-09-27: flexicon#572 (phon rules), #573 (stem MSA inflection class), #574 (exception features), #575 (MSA long name / type), #576 (parser counts, optional). B3 and B6 turned out to be covered by the closed #542 and #543. |
| Casts (C) | 26 | 3 cast families remain after the port: `IMoStemMsa` (#573/#574), `IMoInflAffMsa` for exception features (#574), and part of the `IPh*` set (#572). |

Expected raw-LCM residue after batch 1:
- `phonological-rules`, reduced (the wrappers cover the input, output and
  contexts) but still present until flexicon#572;
- `create-entries-idempotent`, `create-entry-like-comparator` and
  `entry-parser-detail`, from `IMoStemMsa.InflectionClassRA` (#573), plus
  exception features in `entry-parser-detail` (#574);
- the other recipes should reach `raw_lcm_lines: 0`.
