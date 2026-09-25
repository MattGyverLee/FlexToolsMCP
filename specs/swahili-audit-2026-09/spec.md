# Swahili Audit 2026-09 -- cross-repo findings inventory

Source: empirical audit of FLEx project **Claude-Swahili** via FlexToolsMCP +
flexicon 4.5.2 / liblcm 11.0.0 (session 2026-09-06/07). Every item below blocked
or actively misled real work; none are speculative.

Repos in play:
- flexicon   `D:\Github\_Projects\_LEX\flexicon` (main @ 3abf6b5)
- FlexToolsMCP `D:\Github\_Projects\_LEX\FlexToolsMCP` (feat/shared-mode-access @ db52c3a)
- live project `C:\ProgramData\SIL\FieldWorks\Projects\Claude-Swahili`

## Constraints (standing, do not violate)
- FieldWorks **PID 15400 has Claude-Swahili OPEN in shared mode**. MCP writes
  attach as a non-master peer and DO land. Custom-field and writing-system
  changes are **NOT safe** on that path.
- The **user is at the keyboard** and runs the FLEx parser themselves.
- Backup: `~/.flextoolsmcp/backups/Claude-Swahili/20260907T015115Z/`
- **No destructive live-LCM write unattended.** Ever.

## Priority ranking (lead's call)

| P | Item | Why |
|---|------|-----|
| **P0** | B1 | Zero noun-class prefixes use literal U+2205 as lexeme form -> no zero-prefix noun can parse. Gates 5,922/11,175 wordforms (53%), 5,915 attested. Critical path. |
| **P0** | A4 + A8 | Write-path **safety cluster**. A4: read-after-write staleness made a landed write look discarded -> invites a redundant re-write, which is the real data risk. A8: the automatic pre-write backup did not fire on first mutating run. Both observed under shared mode, i.e. squarely inside the active `shared-mode-access` feature. |
| **P1** | A7 | `WfiMorphBundleOperations.GetMorphType` returns the IMoForm allomorph, not the morph type. **Silently** wrong -> defeated a morphotactic check. Name and docstring both wrong. |
| **P1** | A1 | No wrapper to create an inflectional affix slot; raw-LCM-only. Blocks a whole authoring workflow. |
| **P1** | B5 | 12 Concord entries have `feats=None`; authoring them fixes numerals AND adjectives together. Best effort/reward ratio in Workstream B. |
| **P1** | B2, B3 | Category / modelling decisions blocking 6 bound stems + `marafiki`. |
| **P2** | A3 | `MakeFeatStruc` cannot do what its own docstring claims (owner needs `FeaturesOA`, MSAs expose `InflFeatsOA`); no nested structures. |
| **P2** | A6 | Casting validator detects reliably but mis-suggests; conflates same-named vars across if/elif branches. |
| **P2** | A2, A5 | Advertised `from flexicon import MSAOperations` ImportError; stale `WordformInventoryOA` worked example. |
| **P2** | B4, B6 | B4 needs a user-run "Try A Word" trace. B6 likely a B1 dependent (null morph, verb side). |

## Workstream A -- library gaps
- **A1** No affix-slot creation wrapper. Proposal: `POSOperations.CreateAffixSlot(pos, name, optional=True)` + `MorphRuleOperations.AddSlotToTemplate(template, slot, side, index=None)`. Anchors: `flexicon/code/Grammar/POSOperations.py:758` (`GetAffixSlots`, read-only), `flexicon/code/Grammar/MorphRuleOperations.py:361` (`CreateAffixTemplate`).
- **A2** `from flexicon import MSAOperations` -> ImportError, but `flextools_get_object_api` advertises exactly that `import_statement`. Only `project.MSA` works. Anchors: `flexicon/flexicon/__init__.py`, `flexicon/code/Lexicon/MSAOperations.py`, MCP `src/flextoolsmcp/server/handlers/api.py`.
- **A3** `InflectionFeatureOperations.MakeFeatStruc(specs, owner)` requires `FeaturesOA`; `IMoInflAffMsa` exposes `InflFeatsOA`. No nested `FsComplexValue -> FsFeatStruc -> FsClosedValue` support (needed for Bantu `nagr`). Anchor: `flexicon/code/Grammar/InflectionFeatureOperations.py:970`.
- **A4** Read-after-write staleness: fresh MCP session read ~12s post-commit returned PRE-write state. Data was on disk all along.
- **A5** Stale worked example `analysis-subtype-disambiguation` uses `Cache.LangProject.WordformInventoryOA` -> AttributeError on liblcm 11. Use `WordformOperations.GetAll()`. Anchor: `src/flextoolsmcp/server/worked_examples.py`.
- **A6** Casting-validator suggestion quality (IWfiGloss -> "ILexEtymology", MoMorphType -> "ICmAgent", MSA -> "IMoDerivStepMsa"; all wrong). Branch conflation on same-named vars. Anchors: `src/flextoolsmcp/casting_helpers.py`, `src/flextoolsmcp/build_casting_index.py`.
- **A7** `GetMorphType` returns allomorph not type; correct path is `IMoForm(obj).MorphTypeRA`. Anchor: `flexicon/code/TextsWords/WfiMorphBundleOperations.py:785`.
- **A8** Pre-write backup did not run on first mutating run (no project backup dir existed); fired on a later run. Anchors: `src/flextoolsmcp/server/backup.py`, `src/flextoolsmcp/server/handlers/execution.py`.

## Workstream B -- Claude-Swahili data/grammar

Already fixed + verified this session (do not redo): 6 malformed affix entries
(mis-slotted `-i` moved Neg2->FV; `cha-` disabled for parsing; `m-`/`pa-`/`mu-`
given proper MoInflAffMsa); PossConcord slot+template on pro-form, NumConcord on
num, 21 concord senses; 9 class-feature structures deep-copied onto PossConcord.
Validator on the parsed text: 20 flagged/116 analyses -> **2/88**.

- **B1** (P0, critical path) Five zero noun-class-prefix entries (∅-1..∅-5) carry literal **U+2205** as lexeme form. Parser looks for that glyph in surface text, never finds it. Kills class 9/10, 1a, 5, 16. Need the *correct* FLEx null-allomorph representation (`*0` vs empty form vs other) -- **must not be guessed**.
- **B2** Six bound stems in categories with no affix slots: `*yake, *zao, *hivi` (det); `-pi, -ngapi, *juu` (part). `*yake`/`*zao` look redundant with the now-working `-ake` series; `*juu` is probably a free stem (adverb "up/above"); `-pi`/`-ngapi` take concord (`yu-pi`, `wa-ngapi`) so need a concord-bearing category.
- **B3** `marafiki` unparseable: stem `*rafiki` is BantuPl:2 but the only `ma-` ClassPrefix is BantuPl:6. Class 1a/2 nouns take the `ma-` SHAPE while agreeing class 2.
- **B4** Unexplained non-parses despite all morphemes existing and class features unifying: `matunda` (ma+tunda), `msituni` (m+situ+ni), `wenye` (w+enye). Needs a user-run "Try A Word" trace.
- **B5** NumConcord senses carry no class features because the source adjectival Concord set has `feats=None` on all 12 entries. Authoring those 12 fixes numerals AND adjectives.
- **B6** Two `kushuka` analyses put a Caus SUFFIX slot before the stem, filled by an empty-form morph: `ku[Subj]+∅[Caus]+ku[stem]+k[Stat]+a[FV]` -- does not spell the word. Likely B1 on the verb side.
