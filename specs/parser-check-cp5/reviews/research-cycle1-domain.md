# Domain/Parser-Parity Review — CP5 research cycle 1

Reviewer: lex-domain (read-only; written to disk by the main session because the
reviewer had no Write/Bash tool). Main-session verification against the
`v3.8.2` tag is marked **[verified v3.8.2]**.

## 1. FLEx parser defaults — CONFIRMED; MaxAlternatives resolved

`HCParser.cs:51-60` sets `m_guessRoots` / `m_mergeAnalyses = true` in the ctor.
`LoadParser()` (`HCParser.cs:145-182`) uses `delReapps=0` (149), `maxStemCount=2`
(152), `maxAlternatives=0` (153), each overridden only if the project's
`ParserParameters` `<HC>` element carries `<DelReapps>` / `<GuessRoots>` /
`<MergeAnalyses>` / `<MaxRoots>` / `<MaxAlternatives>` (161-176). A real project
can carry non-default values; GenerateHCConfig does not export them, so the
sandbox must read them from the project's `ParserParameters`.

`MaxAlternatives`: the reviewer found it at `Morpher.cs:83` in the `C:\Github\machine`
HEAD checkout, but could not check the tag. **[verified v3.8.2]** It is ABSENT in
v3.8.2: `Morpher` has only `DeletionReapplications` (70), `MaxStemCount` (72),
`MaxUnapplications` (79), `MergeEquivalentAnalyses` (85). The first commit adding
it is contained in v3.9.1+. `../fieldworks` HEAD's `HCParser.cs:181` therefore does
not describe installed FW 9.3.11 (engine 3.8.2). Apply properties by feature
detection.

`ParseWord` overloads **[verified v3.8.2]**: `ParseWord(word)` → `guessRoot=false`
(98-100); `ParseWord(word, out trace, bool guessRoot)` (112).

## 2. Try A Word shaping vs the XML path — CONFIRMED DIFFERENT

`HCParser.GetMorphs` (`HCParser.cs:332-440`) skips morphs with `FormID==0`
(343-345), doubles APR circumfixes via `FormID2` (347-393), and drops the whole
analysis if the `IMoForm` / MSA / `ILexEntryInflType` ids do not resolve in LCM
(357-362, 396-416); glosses come from the live LCM objects. The XML path
(`reference/hc_fw_prototype.py:360-374`, `morph_infos`) walks every morph and
uses `Morpheme.Gloss` (`?` if empty), with none of that shaping.

`XmlLanguageWriter` / `XmlLanguageLoader` round-trip `Properties` (FormID / MsaID /
InflTypeID; `XmlLanguageWriter.cs:1042-1043,1086-1087,1124-1127`;
`XmlLanguageLoader.cs:469,517,590,912,981,1048`) and `Gloss`
(`XmlLanguageWriter.cs:1040-1041`; `XmlLanguageLoader.cs:441,863,958`). So the IDs
survive the export: FormID-0 skipping and circumfix doubling COULD be replicated
from `Properties`. Only "drop analyses whose ids do not resolve in the live
project" cannot, because there is no LCM.

## 3. Recognising a guessed root — CONFIRMED

Guesses come from `Morpher.LexicalGuess`, only when `guessRoot=true`. It matches
`IsPattern` root allomorphs and synthesises `RootAllomorph { Guessed = true }`
**[verified v3.8.2: Morpher.cs:400; RootAllomorph.cs:46 IsPattern]** in a synthetic
entry whose Gloss is the shape string. Reliable signal:
`word.GetAllomorph(morph).Guessed`. Heuristic fallback: gloss == form (fragile).
`morph_infos` should return `guessed` per morph.

## 4. File writes in the engine path — CONFIRMED CLEAN

`XmlLanguageLoader.cs` has no `File.` / `StreamWriter` / `Directory.` writes.
`Morpher`'s only write, `File.WriteAllLines("analyses.txt")`, is inside
`#if OUTPUT_ANALYSES` **[verified v3.8.2: lines 10, 126, 135]**, not defined in a
release build. `HCLoadErrors.xml` in `%TEMP%` is written by `HCParser.LoadParser`
via `HCLoader` / `XmlHCLoadErrorLogger`, which the sandbox never calls.
`XmlLanguageLoader.Load` + `Morpher` + `ParseWord` write no files.

## Proposed SC-003 parity definition

Sandbox parity with Try A Word means, at the same engine version:
(a) the same parsed / not-parsed / invalid-segment outcome, and the same set of
(form, gloss) sequences for words whose analyses involve no circumfix and only ids
that resolve in the live project;
(b) guessed-root analyses flagged via `Guessed` and compared as their own
category;
(c) the Morpher settings (DelReapps, MaxRoots→MaxStemCount, MergeAnalyses,
GuessRoots, and MaxAlternatives where the engine has it) taken from the same
project's `ParserParameters`, with FLEx's defaults (0 / 2 / true / true / 0) when
absent;
(d) known gaps named, not treated as mismatches: dropped-unresolvable-id analyses
(not replicable without LCM); circumfix doubling and FormID-0 skipping unless
implemented from `Properties`; glosses from `Morpheme.Gloss`, not live senses.
