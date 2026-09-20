# Stage 06 -- Stem and Affix Entry Population

[Back to overview](../00-overview.md) | [Prev: Stage 05](05-categories-and-templates.md) | [Next: Stage 07](07-allomorphy-modeling.md)

## Purpose

Create the lexical entries the parser will use: stems and affixes, each with a complete
field set, correct morph type, a sense with a POS-bearing MSA, and -- for affixes --
attachment to the right template slot.

The field-completeness requirement is Ron's, from the opening directive:

> "Each lexeme should be populated with the string in the [vernacular] writing system
> and [transliteration] WS. English gloss should be filled in along with category
> Noun." (D-M2-03)

And the modeling order:

> "Add the stems to the dictionary, add the affixes to the dictionary, add the affixes
> to an Inflection template(s) for noun." (D-M2-02)

## Entry Criteria

- [Stage 05](05-categories-and-templates.md) complete: categories, templates and slots
  exist, and the category objects (not re-typed names) are resolvable.
- A staged, checked source-of-truth data set exists (see Inputs).

## Inputs

- A **source-of-truth data module or JSON** in the scratchpad containing every row to
  be created. In the corpus this was both Python modules exposing a `check()`
  invariant validator, and JSON staging files.
- The existing entry inventory, indexed for dedup (Stage 01).
- The resolved category, slot, inflection-class, stem-name and variant-type objects.

## Procedure

1. **Gate on an offline self-consistency check first.** Each data module exposes a
   `check()` returning rows and errors; the write refuses if it fails -- *"refusing to
   write: fix the data module first"* (M2 §5, M1 §6). **Never write unchecked data.**
2. **Index existing entries for idempotency** by (normalized form, gloss) before any
   bulk create (M5 §6). Normalize both sides (D-M8-02).
3. **Validate-only dry run, then execute** (P5). Report per-row errors rather than
   aborting the whole batch (M5 §5 stage 3).
4. **Create stems**: entry with the correct morph type, no blank sense
   (`create_blank_sense=False`) followed by an explicit sense add, gloss and definition
   in the analysis WS, form in vernacular **and** transliteration WS, and a stem MSA
   carrying the POS -- plus inflection class and stem name where the model calls for
   them.
5. **Create affixes**: entry with the affix morph type, sense, and an **inflectional**
   affix MSA naming the POS and the slot(s) it fills -- or a **derivational** MSA with
   from-POS and to-POS if it changes category (C-M6-03).
6. **Set the citation form explicitly on affix entries** or they display as "-???" in
   the FLEx lexicon (M7 op 18, M7 §6).
7. **Enclitics need attachment declared.** An enclitic attaching to nouns needs both a
   stem MSA with the host POS on its sense **and** an explicit "attaches to" collection
   populated (M2 §6).
8. **Homographs are separate entries.** When a needed affix is homographic with an
   existing unrelated entry, create it as a homograph rather than reusing the entry
   (L-M6-05). Same for variant forms that collide with unrelated entries: log the
   collision, do not avoid the entry (D-M5-03).
9. **Move bulk data out of inline code into JSON** once it is large (M6 §6) -- it
   shrinks the code fingerprint the preflight sees and makes the data reviewable.
10. **Reconcile afterwards -- "skip" does not mean "complete".**
    > "Find nouns from my list that already existed and so never got their oblique
    > stems." (D-M5-13)
    A create-if-not-exists import silently skips existing entries, leaving them without
    the *associated derived data* (allomorphs, oblique stems, inflection class, stem
    name). Always run an explicit "exists but missing associated data" pass.
11. **Verify by re-deriving expected counts from the same source module** used to write
    -- never from a separate hardcoded literal (M2 §5).

### Process hygiene imported from the deck project (G1, language-independent)

12. **Dump wide before authoring.** Over-generate the candidate list beyond the target
    size: an existing entry may need a **new sense** rather than a new entry
    (L-G1-04).
13. **New objects default to published everywhere.** In LCM, a brand-new entry, sense
    or example is published in every publication it is not *explicitly* excluded from;
    the exclusion collection is opt-out, not opt-in (C-G1-03). If the project uses
    publications, exclude new objects from all non-target publications **in the same
    pass that creates them** (D-G1-05).
14. **Restamp the modified date on the owning entry** after editing a linked sense,
    example or reference collection -- LCM does not bump it for you, and downstream
    sync tooling keys off it (D-G1-04).
15. **Never auto-merge an ambiguous match.** An entry that exists but does not match on
    identity is a hard skip with a warning for manual resolution, never an automatic
    merge (G1 §5).
16. **Consolidate bookkeeping into one atomic pass** rather than several sequential
    scripts -- it closes the drift window (D-G1-05).

## Linguistic Decisions Required

- **Citation/lexeme form shape.** The corpus stored verb stems "with their inherent
  vowel and no final vowel-killer" so plain concatenation with a post-consonantal
  suffix reproduces the correct surface (M4 §6), and stored every suffix in its
  post-consonantal shape (L-M4-05). These conventions must be fixed **before** bulk
  population; retrofitting them is a mass edit.
- **Which morph type** each entry gets (stem / suffix / prefix / enclitic / ...).
- **Which slot(s)** each affix fills, and whether it is inflectional or derivational.
- **Whether an inflection class / stem name assignment belongs at creation time.**
- **Whether to list a surface form or decompose it.** See P10 and
  [Stage 13](13-cleanup-and-consolidation.md); the corpus's rule is decompose only
  where the composition is transparent (L-M5-07).
- **Whether an unattested paradigm cell should be invented.** It should not: the corpus
  deliberately omitted four case cells with zero corpus attestation rather than
  inventing them (L-M5-02).

## QC / Exit Criteria

- Every created entry has: vernacular form, transliteration form, gloss, a sense, and
  an MSA carrying the correct POS.
- Every affix entry has a citation form set and is attached to its intended slot(s);
  slot filler counts match intent.
- Reconciliation reports zero missing rows and zero rows "present but missing
  associated data".
- Duplicate detection is clean (no near-duplicate created by a normalization miss).
- Counts re-derived from the source module match the database.
- No entry was created whose form is unattested and invented.

## Common Failure Modes

- **POS name mismatch**: 69/69 rows failed with "POS not found" because names were
  re-typed in a second script (C-M5-01).
- **Normalization miss creating duplicates.** Three duplicate allomorphs were created
  because an NFC literal was compared against NFD-stored text, so the "already have
  this" guard missed -- compounded by an accidental double run (C-M2-03).
- **Half-built entries from a mid-script crash.** A `None` variant type was passed to
  an add call; in non-undoable write mode the partial mutations stayed in the cache and
  needed a bespoke repair pass (C-M6-02). Guard every add against `None`, and expect a
  repair pass to be needed.
- **"Skip" mistaken for "complete"** (D-M5-13).
- **Publish-everywhere leakage** for new objects (C-G1-03).
- **Unprotected writes** rejected by preflight -- recurring across the whole corpus
  (C-M3-02, C-M6-01, C-M8-04).
- **Missing flexicon imports** for an operations class used deep in a helper
  (C-M6-01); hallucinated operations-class names (C-M1-03, C-M2-04, C-M3-01).
- **Wrapper methods that assume a single allomorph subtype** and throw on the other
  (C-M1-02, C-M2-01).

## Automation Notes

**Automatable now:** essentially the whole stage. Bulk idempotent import, field
population across writing systems, MSA creation, slot attachment, citation-form
setting, reconciliation, and count verification.

**Human required for:** the form-shape conventions, and the decompose-vs-list call.

**Missing tooling (requirements):**
- A **transactional bulk-import primitive**: all-or-nothing, so a mid-script failure
  cannot leave half-built entries. The corpus ran in a mode where "the atomicity unit
  for this whole session is the SESSION, not the operation" (M5 §6, M6 §6, M8 §6) --
  this is the single most dangerous property of the current tooling for this stage.
- `reconcile_import(plan)` -- present / missing / present-but-incomplete, where
  "incomplete" is parameterized by the derived data each row should have (D-M5-13).
- Polymorphic-safe allomorph read/write wrappers so stem-vs-affix subtype does not
  throw (C-M1-02, C-M2-01).
- Automatic citation-form population for affix entries (M7 §6).
- An "attaches to" helper for enclitics -- the corpus had to drop to raw LCM (M2 §6).
- A required-fields lint: report every entry missing a WS form, gloss, sense, or POS.

## Provenance

- M1 ops 5-6, 13 (2026-09-10 16:16-16:18, 19:54); D-M1-01; M1 §5-§6.
- M2 ops 1, 3-5 (2026-09-10 15:36-20:46); **D-M2-02, D-M2-03**; C-M2-01, C-M2-03;
  M2 §5 "Gated write", "Post-write verification"; M2 §6.
- M3 §5 "Precondition-gated write".
- M4 ops 5-7 (2026-09-12 17:05-17:07) -- 100-verb bulk build; D-M4-02; M4 §5
  "Precondition-gated bulk creation"; M4 §6; L-M4-05.
- M5 ops 11-12, 16, 21-23, 56, 60, 68, 72, 76 (2026-09-13 23:07 .. 09-14 14:19);
  D-M5-01, D-M5-03, **D-M5-13**; L-M5-02; C-M5-01; M5 §5 stages 3 and 5; M5 §6.
- M6 ops 14, 16, 18 (2026-09-14 16:19-16:28); C-M6-01, C-M6-02; L-M6-05; M6 §5 stage 3.
- M7 op 18 (2026-09-15 08:34) -- citation form; D-M7-05.
- M8 ops 5-6 (2026-09-15 14:08-14:09); D-M8-04; L-M8-02, L-M8-03; C-M8-04.
- G1 §5 steps 1-3, D-G1-04, D-G1-05, L-G1-04, C-G1-03 -- imported as language-independent
  hygiene per G1 §9.
- **Merge seam:** Matthew's staging format and field conventions; whether he imports
  from LIFT/CSV rather than authoring a checked data module.

## Open Questions

- The corpus's source-of-truth data modules live only in a local scratchpad and are not
  in any of the logs (M1 §8, M2 §7). The *format* is recoverable, the content is not.
  Q-11.
- Whether the citation form for a given POS should differ from the bare lexeme form
  (raised in G1 L-G1-03, never resolved). Q-12.
</content>
</invoke>
