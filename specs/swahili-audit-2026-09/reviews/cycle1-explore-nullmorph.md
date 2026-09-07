# cycle1-explore-nullmorph.md

Evidence gathered read-only against local checkouts of FieldWorks, liblcm 11, machine
(HermitCrab), and flexicon. Returned inline by the Explore agent (no Write tool) and persisted
here verbatim.

## Q1. What string denotes a null morpheme in an allomorph form?

**Four strings are accepted, and they are equivalent. U+2205 (∅) is one of them.**

XAmple path (authoritative, with an explicit comment):
- `...\FieldWorks\Src\Transforms\Application\FxtM3ParserToXAmpleLex.xsl:812` — `<!-- allow various ways to indicate a null: ^0, *0, &0, or the Unicode empty set character -->`
- `...\FxtM3ParserToXAmpleLex.xsl:813` — `<xsl:when test="$sForm='^0' or $sForm='&amp;0' or $sForm='*0' or $sForm='∅'">0</xsl:when>` — any of the four is emitted into the XAmple lexicon as the single literal `0`, XAmple's native null.
- Change-log entries in the same file: `:2361` ("now we allow either `*0` or Unicode 2205 (∅), the empty set symbol"), `:2338` ("Allow `^0` and `&0` for null as well").
- This template (`AlloForm`, `:781`) is shared by **both** `MoStemAllomorph` and `MoAffixAllomorph` (`:788`), so the same four strings work on stems and affixes.

HermitCrab path:
- `...\FieldWorks\Src\LexText\ParserCore\HCLoader.cs:2710` — `m_null = m_table.AddBoundary(new[] { "^0", "*0", "&0", "∅" });` — the same four strings registered as one `boundary`-type character definition.
- Boundary nodes are excluded from the surface string: `...\machine\src\SIL.Machine.Morphology.HermitCrab\Morpher.cs:527` and `...\HermitCrabExtensions.cs:260` both skip when `node.Annotation.Type() == HCFeatureSystem.Boundary`.

**Refuted candidates:** the *empty string* is explicitly rejected — `HCLoader.cs:543`
(`IsValidRuleForm`) and `HCLoader.cs:585` (`IsValidLexEntryForm`) both `return false` on
`string.IsNullOrEmpty(formStr)`. Bare `"0"` is **not** in either accepted set; it would be
treated as a literal grapheme.

Third confirmation of the same four-string set outside the parser:
`...\Src\Utilities\pcpatrflex\ToneParsFLExDll\ANABuilder.cs:141`.

## Q2. Dedicated MoMorphType for null in liblcm 11?

**No.** The complete fixed morph-type GUID list is
`...\liblcm\src\SIL.LCModel\ConstantAdditions.cs:364-454`: BoundRoot `d7f713e4-…`,
BoundStem `d7f713e7-…`, Circumfix `d7f713df-…`, Clitic `c2d140e5-7ca9-41f4-a69a-22fc7049dd2c`,
Enclitic `d7f713e1-…`, Infix `d7f713da-…`, Particle `56db04bf-3d58-44cc-b292-4c8aa68538f4`,
Prefix `d7f713db-…`, Proclitic `d7f713e2-…`, Root `d7f713e5-…`, Simulfix `d7f713dc-…`,
Stem `d7f713e8-…`, Suffix `d7f713dd-…`, Suprafix `d7f713de-…`, InfixingInterfix `18d9b1c3-…`,
PrefixingInterfix `af6537b0-…`, SuffixingInterfix `3433683d-…`, Phrase `a23b6faa-…`,
DiscontiguousPhrase `0cc8c35a-…` (`…` = `-e8cf-11d3-9764-00c04f186933`). There is no
`kMorphNull`/`kmtNull`. Nullness is carried **entirely by the form string**, with the ordinary
morph type (Prefix, Suffix, Stem…) unchanged.

## Q3. Do XAmple and HermitCrab diverge?

Not on the accepted strings — both honour the identical four-member set (`xsl:813` vs
`HCLoader.cs:2710`). They diverge in mechanism and limits:
- XAmple emits literal `0` and is governed by `\maxnull`
  (`...\FxtM3ParserToXAmpleADCtl.xsl:117`), whose **default is 1**
  (`...\FxtM3ParserCommon.xsl:28-35`), overridable via `ParserParameters/XAmple/MaxNulls`.
- HermitCrab has no such cap; nulls are boundary segments stripped at surface, and affix
  insertion is form-string concatenation (prefix: `HCLoader.cs:1600`; root: `:811-813`).

## Q4. Sample/test projects containing a null allomorph — exact stored forms

All real FLEx project dumps under `...\ParserCore\ParserCoreTests\M3ToXAmpleTransformerTestsDataFiles\`:
- **`Abaza-OrderclassPlay.xml:16178`** — `<MoAffixAllomorph Id="30249" MorphType="114676" IsAbstract="0"><Form>∅</Form><PhoneEnv dst="59472"/>` (also `:16260`). Stored form is literally U+2205.
- **`QuechuaMYLFxtResult.xml:118999`** — `<MoStemAllomorph Id="19857" … StemName="25517"><Form>∅</Form>` (also `:135256, :135327, :135567`). A null **stem** allomorph stored as U+2205.
- `M3FXTDump.xml:1877` — `<MoAffixAllomorph … MorphType="d7f713dd-…" (Suffix)><Form>*0</Form>` — the `*0` variant on an ordinary Suffix morph type.
- `OrizabaParserFxtResult.xml:2428,2466,2467`, `CliticParserFxtResult.xml:656` — more `*0` affixes.
- UI round-trip: `...\WordGrammarDebuggingInputsAndResults\niyumamwupeStemNameSetNoFsStep00.xml:54-55` shows `<alloform>-*0</alloform>`.

## Q5. Null affix in an inflectional template slot

Two distinct things exist; do not conflate them.

1. **A user-authored null affix in a slot** uses exactly the Q1 representation, with morph type
   Prefix/Suffix (`M3FXTDump.xml:1877`, `Abaza-OrderclassPlay.xml:16178`). Nothing special.
2. **An auto-generated null** that FLEx synthesises for *required* slots so irregularly
   inflected forms still parse. HC: `HCLoader.cs:1725-1729` ("add a null affix to the required
   slot so that irregularly inflected forms can parse correctly") → `LoadNullAffixProcessRule`
   (`:1771`), inserting `Segments("^0+")` for prefix slots and `Segments("+^0")` for suffix
   slots (`:1791`, `:1795`), tagged `msubrule.Properties[HCParser.IsNull] = true` (`:1802`).
   Reported with `id="0"`, form `^0`, headword "Automatically generated null affix for the
   {InflType} irregularly inflected form" (`FwXmlTraceManager.cs:506-524`). XAmple analogue:
   `FxtM3ParserToXAmpleLex.xsl:621` → `\a 0 {…}` at `:637`.

This #2 machinery — not a lexical entry — is the most likely source of the `kushuka` Caus-slot
empty morph. Note the audit reports an *empty* form there, whereas HC's synthetic null is `^0`;
if the observed morph truly has an empty form it is neither #1 nor #2 and needs separate
diagnosis.

## CONFIDENCE

**PROVED (code-level, cited):**
- `^0`, `*0`, `&0`, and `∅` (U+2205) are all accepted and mutually equivalent null markers, in
  both XAmple (`xsl:812-813`) and HermitCrab (`HCLoader.cs:2710`).
- Therefore **storing `∅` in a lexeme form is *not*, by itself, the bug.** The premise "the
  parser searches surface text for that glyph" is contradicted by `xsl:813` (converted to
  XAmple `0`) and by `Morpher.cs:527` / `HermitCrabExtensions.cs:260` (boundary nodes skipped).
- The empty string is rejected outright (`HCLoader.cs:543`, `:585`).
- No null MoMorphType exists in liblcm 11 (`ConstantAdditions.cs:364-454`).
- Shipped sample dumps store null allomorphs as literal `∅` on both affixes and stems.
- XAmple's `\maxnull` defaults to **1** (`FxtM3ParserCommon.xsl:28-35`).
- The auto-generated required-slot null uses `^0` and no lexical entry.

**INFERRED (not proved here):**
- That the Swahili failure is caused by something *other* than the ∅ glyph. Two untested
  hypotheses: (a) the five class-prefix entries carry a **stem/root** morph type rather than
  **Prefix** (`HCLoader.cs:584-590` routes by morph type); (b) if the active parser is XAmple,
  `MaxNulls=1` blocks any wordform requiring two or more nulls.
- Whether a null **root/stem** allomorph functions correctly in HermitCrab.

**AMBIGUOUS — flagged rather than resolved:** which of the four spellings is *canonical*.
FLEx's own generated output uses `^0`; the oldest documented user convention is `*0`; `∅` is
documented as supported since 2004 and appears in shipped samples. No file states a preference
for user-entered data.

---
---

## Editorial notes added on persistence (not part of the Explore report)

**Hypothesis (a) is refuted by project data already in hand.** The five entries were dumped
earlier this session as `type=prefix` for all five:
`∅-1 form='∅' [U+2205] type=prefix` … `∅-5 … type=prefix`. They are Prefixes, not stems/roots.

**Hypothesis (b) is weak for the observed cases.** Every failing noun needs at most ONE null:
`sungura` = ∅+sungura, `sokoni` = ∅+soko+ni. `MaxNulls=1` would permit these.

**The stronger unifying observation:** `matunda` (= `ma`+`tunda`) contains **no null morpheme at
all** and also fails to parse. So whatever blocks these nouns is not null-related. The common
factor across every failing noun — sungura, fisi, matunda, msituni, nyumbani, sokoni, wenye — is
`ClassPrefix + bound stem` on the noun template, which is exactly what lex-domain independently
predicted for B4 (morph-type / inflection-class restriction on the slot filler). Meanwhile
adjectives using the `Concord` slot (`mkubwa` = m+kubwa, `matamu` = ma+tamu) DO parse.

Next diagnostic: determine whether ANY wordform in the project has a parser-generated analysis
containing a ClassPrefix morpheme. If none do, the noun template is broken as a whole and that,
not the ∅ glyph, is the 53%-of-corpus root cause.
