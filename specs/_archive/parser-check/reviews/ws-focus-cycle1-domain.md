# Domain Review — WS focus, row 2 case-variant IPhCode product

**Verdict: case-variant sibling codes should NOT multiply.** Confidence: high on the structural argument, medium-high on FieldWorks-specific mechanics (reasoned from LCM's `IPhCode`/`CodesOS` design and documented FieldWorks phoneme-setup convention, not from having read HermitCrab's tokenizer source in this session).

## Why

`IPhCode.Representation` (via `CodesOS`) is HermitCrab's grapheme-to-phoneme layer: each code is a literal surface spelling that maps an input substring to a phoneme before rule application. Adding an uppercase sibling code for any phoneme whose grapheme can appear capitalized (sentence-initial, proper nouns) is standard, documented FieldWorks practice — exactly the cause the user confirmed here.

Upper/lower code pairs are mutually exclusive at any single input position: the literal text there is either "K" or "k", never both, so at most one of the pair can ever match. Both resolve to the *same* phoneme node, so the parser follows exactly one path, not two — whether HermitCrab casefolds input before matching (making the uppercase code dead weight) or matches literal case (making the two codes disjoint), the multiplicity added is zero either way.

This is categorically different from genuine grapheme ambiguity — e.g. a digraph "ng" vs. sequential "n"+"g" — where two *different* segmentations of the *same* substring are both viable and the tokenizer must fork. That is the real path-multiplying pathology row 2 exists for (SPEC 9.5.1's "poorly distinguished or overlapping phonemes"), and is presumably what PanGloss's Aweti 4096 measured. Naively counting `.CodesOS.Count` conflates the two, which is exactly how a routine, universally-applied capitalization convention inflates the product to 18+ billion.

Per SPEC 9.5.3/9.5.7: this is a finding about the CHECK's arithmetic, not a verdict on the grammar.

## Discriminator (implementable)

Dedupe `CodesOS` by casefolded `Representation` at the WS the codes are actually recorded in (default vernacular, per confirmed facts) before counting:

```
reps = set()
for code in ph.CodesOS:
    rep = get_multiunicode(code.Representation, default_vernacular_ws)
    if rep and rep != "***":
        reps.add(casefold(rep))
n = len(reps)
if n > 1:
    product *= n
```

Only distinct casefolded spellings count toward `n`; drop empty/`"***"` per cross-cutting rule 2 rather than seeding a spurious empty variant.

## Second question: WS assignment

Correct as stated. `IMoForm.Form` / `IMoAffixProcess.Form` / `IMoStemAllomorph.Form` and `IPhCode.Representation` are vernacular-side data (actual forms/transcriptions); gloss/category/slot/stratum `Name`/`Description`/`Abbreviation` are analysis-side (linguist metalanguage labels). No row misassigned.

## Legitimate count-change risk (not a regression)

Any multi-vernacular-WS project (e.g. IPA-transcription WS plus practical-orthography WS) where a form or code `Representation` is recorded only in a non-default vernacular WS will newly read empty under single-WS resolution. This is explicitly flagged for **Row 1** (zero-surface-form) in the prompt, and equally applies to **Row 2** once codes resolve via one WS: a phoneme whose sole code lives only in a secondary vernacular WS would newly show `n=0` rather than being skipped as "single code, no multiply." Both are legitimate consequences of the WS seam and should be called out to reviewers as such, not treated as regressions.
