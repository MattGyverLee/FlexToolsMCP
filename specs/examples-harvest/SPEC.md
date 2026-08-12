# SPEC — Harvesting execution-verified examples and recipes

**Status:** DRAFT (scoping pass, 2026-08-12)
**Feature slug:** `examples-harvest`
**Owner:** LEX crew
**Origin:** follow-on from issue #84. Not a prerequisite for it, and not blocked by it.

## 1. Problem

Two gaps, one shared cause.

**Coverage.** The grammar half of the flexicon index is documented but not
demonstrated. Measured against `index/python/flexicon_api_v4.3.0.json`:

| Operations class | methods | with description | with examples |
|---|---:|---:|---:|
| `POSOperations` | 21 | 21 | **0** |
| `InflectionFeatureOperations` | 27 | 27 | **0** |
| `GramCatOperations` | 12 | 12 | **0** |
| `MSAOperations` | 9 | 9 | **0** |

Downstream, `curated_recipes.py` ships 21 recipes of which 4 touch POS
(`count-senses-by-pos`, `list-entries-with-pos`, `find-entries-missing-pos`,
`list-parts-of-speech`) and **none** touch inflection features.
`worked_examples.py` has 6 entries; only `msa-creation-and-attach` and
`closed-feature-with-values` are relevant. So the surface an assistant reaches
for when a user says "set inflection features on these senses" is prose-only.

**Trust.** The current bar for shipping a recipe is `recipe_validator.validate_all`
— a static gate. Issue #84 proved that bar is too low. The fix's own sweep
produced `project.Senses.GetAllSenses(entry)`, which passed the accessor gate,
passed 876 tests, and shipped into the authoritative template. It was wrong:
`GetAllSenses` exists on **both** operations classes with different parameters
(`LexEntryOperations.GetAllSenses(entry_or_hvo)` vs
`LexSenseOperations.GetAllSenses(sense_or_hvo)`), and both duck-type on an
`AllSenses` property, so passing an entry to the sense flavour silently returns
plausible results instead of raising. Only reading flexicon's source caught it.

The accessor gate compares attribute **names** via difflib. It has no model of
argument types, so this defect class is structurally invisible to it. Any
harvest that leans on static validation alone will reproduce it at scale.

**Therefore:** a recipe is not "confirmed-good" until it has been *executed*
read-only against a real project and its output recorded.

## 2. Sources

### 2.1 Ruled out, with evidence

FLExTools' own `flextools/FlexTools/Modules/` tree. A word-boundary grep for
genuine POS/MSA/inflection API usage returns **2 hits**, both
`MorphoSyntaxAnalysisRA` in `Duplicates/Merge_Senses.py`. (A case-insensitive
`POS` grep looks far more promising but matches "pur**pos**e" and
"**pos**ition" — do not re-run it that way.) The tree is also written in the
stable-flexlibs idiom (`project.LexiconGetSenseGloss`, `project.LexiconAllEntries`).

### 2.2 Primary — the contributed module corpus

`D:\Github\_Projects\_LEX\MyFlextool\FlexTools Modules-20260812T202142Z-1-001.zip`
(a local export of the shared Drive folder; 79 entries, **75 `.py`**, five
contributors: Ken, Larry, Matthew, Peter, Ron).

Aggregate API density across the corpus: `MorphoSyntaxAnalysisRA` 72,
`PartOfSpeechRA` 55, `StemNameRA` 14, `MsFeaturesOA` 12, `InflFeatsOA` 12,
`ProdRestrictOA` 4, `FeatureSystemOA` 2, `PartsOfSpeechOA` 1.

Best recipe candidates are the small single-purpose modules, not the FLExTrans
infrastructure:

| module | hits | lines | likely recipe theme |
|---|---:|---:|---|
| `From Matthew/Bulk_Set_Stem_Name.py` | 13 | 302 | stem names on allomorphs |
| `From Matthew/Bulk_Set_Exception_Features.py` | 7 | 356 | exception ("productivity restriction") features |
| `From Ron/SetFeatures.py` | 5 | 151 | inflection feature assignment |
| `From Matthew/Overpowered_Affixes.py` | 4 | 384 | affix/MSA diagnostics |

`Library files that support modules/Utils.py` (31 hits, 1425 lines) and
`DoStampSynthesis.py` (21 hits, 1217 lines) are FLExTrans infrastructure — mine
them for **idiom**, do not convert wholesale.

### 2.3 Secondary — sibling repos

`FLExTrans/Dev/{Lib,Modules}` and `GramTrans/src/gramtrans/Lib` both carry
substantial morphosyntax code (`categories.py`, `Utils.py`, `TextClasses.py`,
`TestbedValidator.py`, `AdHocConstrForCluster.py`). Same translation caveat.
`paws` and `MyFlextool` contain none.

## 3. Verification projects

Chosen by probing, not by name. All four probes were read-only via
`flextools_run_module`; entry iteration capped at 400 entries.

| project | POS | infl. features | infl. classes | entries | senses | senses w/ POS |
|---|---:|---:|---:|---:|---:|---:|
| `feat-swahili` | 5 | 4 | 0 | **0** | 0 | 0 |
| `Turkish` | 6 | 0 | 0 | 15 | 15 | 15 |
| `Sena 3` | 37 | 3 | 0 | 1540 | 584* | 567 |
| **`French-FLExTrans-Demo2025`** | 27 | **10** | 0 | 126 | 135 | **135** |

\* sampled from the first 400 entries.

**Decision:** `French-FLExTrans-Demo2025` is the primary verification project
(richest inflection-feature system, 100% of senses carry a POS).
`Sena 3` is the secondary/scale check (1540 entries, 37 POS).

Two findings from the probes that shape recipe design:

1. **`feat-swahili` is a trap.** The name suggests a features corpus; it is a
   feature-system sandbox with **zero entries**. Any sense-level recipe verified
   only there would be vacuously green.
2. **`Sena 3` has a POS with an empty name** — the sample rendered as
   `"Advérbio, Nome, , Nominalizador"`. A recipe calling `POS.GetName(p)`
   without a guard prints a blank line and reads as broken. This is exactly the
   defect class static validation cannot see, and it is why the secondary
   project is not optional.

Also confirmed from the live index: `InflectionFeatureOperations.FeatureStructureGetAll()`
is documented as *"Yields nothing in the current implementation"* — `IFsFeatStruc`
objects are not held in a project-level collection. Feature-structure recipes
must reach them through their owners, not by enumeration.

## 4. The translation hazard

Every source in §2 is written in direct-LCM idiom
(`sense.MorphoSyntaxAnalysisRA.PartOfSpeechRA`) or stable flexlibs. Recipes ship
in flexicon Operations idiom. **The translation step is the defect surface** —
it is where issue #84's bug was introduced, by a mechanical substitution that
every existing gate approved.

Rules for translation:

- Never mechanically find-replace an accessor across a corpus. Issue #84's sweep
  did exactly that and broke six call sites.
- When a method name exists on more than one Operations class, resolve the
  **argument type** from the flexicon `.pyi` / source before choosing, not from
  the name. `GetAllSenses` is the known instance; assume others exist.
- Prefer `project.<Accessor>` forms over constructing `XOperations(project)`,
  matching the house idiom in `curated_recipes.py`.
- Verify the accessor exists with `scripts/check_project_accessors.py` semantics
  (live `dir(FLExProject)`), never against the index property list — that list
  under-reports by 29 names.

## 5. Verification harness (the new piece)

Everything else already exists. What is missing is an execution gate.

**Requirement.** For each candidate recipe, run it read-only against the primary
and secondary projects via `flextools_run_module` (`write_enabled=False`), and
persist an evidence record.

**Evidence record** (one per recipe per project), stored under
`specs/examples-harvest/evidence/<recipe-id>.<project>.json`:

```
{ "recipe_id", "project", "flexicon_version", "liblcm_version",
  "status": "ok" | "error", "exit_code", "error_code",
  "info_count", "warning_count", "error_count",
  "sample_output": [ first N report lines ],
  "op_id", "run_at" }
```

`op_id` ties the record back to the MCP operations log for post-mortem.

**Acceptance criteria for promotion to `curated`:**

1. Passes `recipe_validator.validate_all` (existing bar).
2. Executes with `exit_code == 0` and `error_count == 0` on **both** projects.
3. Produces non-empty, non-degenerate output on at least the primary project —
   a recipe that silently reports zero rows everywhere is not verified, it is
   untested. (This is the check that would have caught `feat-swahili`.)
4. Write-shaped recipes: dry-run only. Their mutation path is certified by
   `write_certification` / `validate_only`, never executed against a real
   project under this spec. See §8.
5. Argument-type assertion: any call whose method name is ambiguous across
   Operations classes carries a test in the style of
   `TestGetAllSensesArgumentType` (issue #84).

**Non-goal:** this harness does not run in normal CI — it needs FieldWorks,
pythonnet and real projects. It is a maintainer-run gate whose *output*
(the evidence records) is committed, so CI can assert that every curated recipe
has a current evidence record.

## 6. Pipeline integration

No new plumbing. Reuse:

- `extract_patterns.py --mine-operations-log` → emits `source: "mined"` candidates.
- `curated_recipes.py` → human-reviewed `source: "curated"` only; the file's own
  docstring already forbids adding `mined` entries directly.
- `tests/test_recipes.py` → gates every curated recipe through the validator chain.
- `worked_examples.py` → for longer narrative examples (the MSA/feature-creation
  shape), as distinct from short recipes.

Add: a CI assertion that each `curated` recipe has an evidence record whose
`flexicon_version` matches the indexed version.

## 7. Phases

- **P0 — harness.** Build the run-and-record loop and the CI evidence assertion.
  Validate it by re-verifying the 4 existing POS recipes; expect them to pass and
  to produce real evidence records. Any that fail were never actually confirmed.
- **P1 — narrow proof.** Take `SetFeatures.py` and `Bulk_Set_Stem_Name.py` end to
  end: harvest → translate → execute-verify → curate. Two recipes, full loop.
  Stop and review before scaling.
- **P2 — inflection features.** The zero-coverage gap. Target ~6 recipes:
  list features, read a sense's feature structure, find senses missing features,
  feature-value inventory, inflection-class listing, POS-scoped feature lookup.
- **P3 — POS/MSA depth.** Extend beyond the current 4 read-only POS recipes into
  MSA-shape awareness (stem vs affix MSAs), which is where `Overpowered_Affixes.py`
  and `Utils.py` pay off.
- **P4 — sibling repos.** FLExTrans/GramTrans sweep, if P1–P3 prove the process.

## 8. Risks and open questions

- **Write-shaped recipes.** Most of the richest harvest candidates
  (`Bulk_Set_*`, `SetFeatures`) are mutating. This spec verifies them dry-run
  only. Genuinely verifying a write needs a disposable project and an undo
  strategy; `ResembliO-Delete` and `Circumsanity` look like candidates but were
  not probed. **Open: do we designate a scratch project for write verification?**
- **Attribution and licensing.** Contributed modules carry named authorship
  (Ken/Larry/Matthew/Peter/Ron). Recipes derived from them should credit the
  source module. **Open: confirm redistribution is acceptable to contributors.**
- **Stale locks.** Four projects currently show stale `.fwdata.lock` files
  (`French-FLExTrans-Exp5`, `Mbugwe LizzieHC practice`, `Puguli`, `feat-swahili`).
  Read-only runs are unaffected; any future write verification is not.
- **Project drift.** Evidence records are tied to specific projects whose content
  can change. The `flexicon_version` check catches library drift but not project
  drift. Accept, and re-run the harness when output counts move.
- **Corpus is a point-in-time export.** The zip is dated 2026-08-12; the upstream
  Drive folder may move on. Record the export date in each derived recipe.
