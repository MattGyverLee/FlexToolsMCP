# Stage 02 -- Phoneme Inventory

[Back to overview](../00-overview.md) | [Prev: Stage 01](01-project-survey-and-inventory.md) | [Next: Stage 03](03-phonological-features.md)

## Purpose

Make the project's phoneme inventory match the orthography the parser will actually
tile against, so that every grapheme occurring in any target wordform is a defined
phoneme with a code the parser can match.

Ron sequenced this first and explicitly deferred features:

> "Also populate/edit the phoneme inventory as needed for the language. Don't yet add
> phonological features." (D-M2-05, D-M1-01)

## Entry Criteria

- [Stage 01](01-project-survey-and-inventory.md) complete: current phoneme count,
  natural-class types, and writing systems known.
- A target orthographic inventory exists (from the writing system's script, the target
  texts, or a source-of-truth data module).

## Inputs

- The stock inventory the project shipped with (typically English) -- to be removed.
- The target grapheme list, **decomposed the way LCM stores it**.
- The full set of graphemes occurring in every wordform the paradigm texts will
  contain.

## Procedure

1. **Decide the unit.** The phoneme here is an *orthographic* unit, not a phonetic one:
   it is what the parser tiles the surface string with. Decomposable multi-character
   sequences must be decided one way or the other. In the corpus, three decomposable
   matra phonemes were deleted precisely because they decomposed into units already in
   the inventory (M1 op 4).
2. **Unhook before deleting.** Stock phonemes are referenced by natural classes; remove
   the references first, then delete the phonemes (M1 §5).
3. **Create the target graphemes** in the vernacular WS.
4. **Populate the base natural classes** (Consonants, Vowels, or whatever the shipped
   project has). Check each class's actual LCM class name first:
   a segment-based class (`PhNCSegments`) takes members via its segments collection; a
   feature-based class (`PhNCFeatures`) cannot take phonemes at all (C-M1-01).
5. **Set an explicit code representation on every phoneme**, in the vernacular WS,
   equal to that phoneme's own letter. *"The code representation is what the parser
   actually tiles against"* -- not the phoneme's Name (M1 op 8, M1 §6). Later lookups
   should key off the code, not the display name (M7 op 33).
6. **Normalize consistently.** Use decomposed form for per-character / per-phoneme
   comparison against codes, and composed form for whole-form display and comparison
   (M3 §6). Pick one convention per comparison and apply it to *both* sides.
7. **Verify coverage against the real target set.** Decompose every wordform the
   paradigm texts will contain and assert every character is a defined phoneme.
8. **Guard against orthographic traps specific to the script.** In the corpus, a
   dependent vowel sign (matra) versus an independent vowel letter were confused, which
   silently produced a wrong surface form; the convention adopted was that every suffix
   is stored in its post-consonantal shape and therefore always opens with a dependent
   vowel sign (L-M4-05). Establish the analogous convention for your script **now**,
   not after 100 affixes are wrong.

## Linguistic Decisions Required

- **Orthographic unit vs. phonological segment.** Whether to treat a digraph, conjunct,
  or diacritic as one phoneme or as a sequence. This determines every later natural
  class and rule.
- **Which abstract markers get phoneme status.** The corpus gave phoneme status to
  vowel-killer and nasalization marks and later built natural classes over them
  (L-M2-06, L-M1-06) -- including the counter-intuitive decision that the vowel-killer
  patterns with non-consonantal segments for the `cons` feature.
- **Whether decomposable characters are deleted or retained.**
- **The suffix-shape convention** (dependent vs independent vowel forms) -- L-M4-05.

All of the above are **modeling hypotheses**, not facts about the language. Record them
as such. See [`reference/malayalam-morphophonology.md`](../reference/malayalam-morphophonology.md)
for how the corpus's decisions were recorded.

## QC / Exit Criteria

- Every grapheme required by every target wordform is a defined phoneme. **Test it by
  decomposing the full target wordform list and asserting membership.**
- Every phoneme has an explicit vernacular code representation.
- No stock/foreign phonemes remain.
- Base natural classes are repopulated and their membership counts are as intended.
- Inventory size recorded (the corpus's was 68) so later stages can assert against it.

## Common Failure Modes

- **Adding phonemes to a feature-based natural class.** Fails with "Cannot add phoneme
  to feature-based natural class"; check the class's LCM class name and use the
  matching API (C-M1-01).
- **Deleting a phoneme still referenced by a class.** Unhook first.
- **Relying on phoneme Name instead of code representation** for lookup or for parser
  matching (M1 §6, M7 op 33).
- **NFC/NFD mismatch** producing phantom "missing" or phantom "duplicate" graphemes
  (C-M2-03, D-M8-02).
- **Unprotected writes** -- the first attempt in the corpus was rejected for having no
  `modifyAllowed` guard (M1 op 1).
- **Independent vowel where a dependent sign belongs**, producing a wrong surface form
  that still "writes successfully" (L-M4-05).

## Automation Notes

**Automatable now:** deletion, creation, code population, class repopulation, and the
full coverage assertion -- all scriptable via flexicon phoneme/natural-class operations
plus direct LCM casts where wrappers misclassify class type.

**Human required for:** the unit-of-analysis decisions above.

**Missing tooling (requirements):**
- `build_phoneme_inventory(graphemes)` -- one call that deletes stock, creates targets,
  sets codes, and repopulates base classes, with the unhook ordering handled.
- **`verify_inventory_covers(text_or_wordlist)`** -- decompose a corpus and report any
  character that is not a defined phoneme. The corpus did this by hand every time.
- Natural-class API that dispatches on segment-based vs feature-based instead of
  throwing (fixes C-M1-01 at the wrapper level).
- A script-aware lint for the dependent/independent vowel-form trap.

## Provenance

- M1 ops 1-4 (2026-09-10 16:13-16:16), op 8 (18:30), op 9 (18:37); D-M1-01; L-M1-06;
  C-M1-01; M1 §5 "Phoneme inventory bootstrap"; M1 §6.
- M2 D-M2-05 (2026-09-10 15:36); C-M2-03.
- M3 §6 (normalization discipline: `N()` NFC vs `D()` NFD).
- M4 L-M4-05 (2026-09-12 17:03), C-M4-02.
- M5 ops 5-7 (2026-09-13 22:42-22:43).
- M7 op 33 (2026-09-15 10:32) -- phoneme lookup rebuilt from code, not short name.
- M8 D-M8-02 (2026-09-15 14:06).
- **Merge seam:** Matthew may derive the inventory from an existing writing-system
  definition or LIFT import rather than authoring it; record his source.

## Open Questions

- Is there a principled rule for when a decomposable sequence should be a single
  phoneme? The corpus decided case by case. Q-03.
- The exact content of the feature-assignment source files was never captured in the
  logs (M1 §7), so the inventory is reproducible only from the live project.
</content>
</invoke>
