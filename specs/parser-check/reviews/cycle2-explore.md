# cycle2-explore: CLI-path sandbox claim, verified from source

> Filed by the orchestrator on the reviewing agent's behalf: the subagent had no
> Write tool. Content is the agent's verbatim report.

Files cited: `hctool\{Program,ParseCommand,TestCommand,StatsCommand,TracingCommand,HCContext,MorphInfo,Extensions}.cs`, `hctool\SIL.Machine.Morphology.HermitCrab.Tool.csproj`, and in-repo `D:\Github\_Projects\_LEX\FlexToolsMCP\hcparse.ps1`.

## 1. Isolation — CONFIRMED, with one unverifiable link

`hc.dll` itself touches exactly three paths, all supplied on the command line: `-i` config (`Program.cs:26,61` `XmlLanguageLoader.Load(inputFile, ...)`), `-s` script (`Program.cs:28,98-113`, read line-by-line), `-o` output (`Program.cs:27,57-58` `new StreamWriter(outputFile)`). No `.fwdata`, registry, or FieldWorks-path reference appears anywhere in the four command classes or `Program.cs`. The only write is to `outputFile` (or `Console.Out` if `-o` is omitted) — confirmed by grep-equivalent read of every `Write`/`WriteLine` call in `Extensions.cs:15-45`, `ParseCommand.cs`, `TestCommand.cs`, `StatsCommand.cs`, `TracingCommand.cs`: all go through `_context.Out`, which is that same stream (`HCContext.cs:9,26-29`). **The sandbox's safety guarantee holds for the tool itself: no path back into a live FLEx project exists in this source.**

The surrounding driver reinforces this by design: `hcparse.ps1:41-45` explicitly copies the project ("Work on a copy so a FLEx instance holding the project can't be disturbed") before running FieldWorks' `GenerateHCConfig.exe` against the copy (`hcparse.ps1:50-53`), not the live `.fwdata`. One caveat I cannot close from source: `GenerateHCConfig.exe` is a FieldWorks-shipped binary, not part of the reviewed files, so its internal read/write behavior against that copy is unverified — it is *pointed at* a copy by construction, but I did not read its source. Separately (not a FLEx leak, but a hygiene gap): `hcparse.ps1` cleans up `$script` and `$out` (lines 83-84) but never removes the `$work` temp directory (created line 42-43) holding the copied project and generated config — it persists in `%TEMP%` indefinitely.

## 2. Editability — PARTIALLY confirmed; DTD/schema **not found**

Confirmed from source: the config is XML (`Program.cs:61` `XmlLanguageLoader.Load`; `hcparse.ps1:48` writes `hc-config.xml`). Not confirmed: I could not find `HermitCrabInput.dtd` or any schema file anywhere in the FlexToolsMCP repo (glob/grep both empty), and the class that defines `Language`/`Stratum`/`AffixTemplate`/`Morpheme` structure — the `SIL.Machine.Morphology.HermitCrab` core library referenced only as a `ProjectReference` (`SIL.Machine.Morphology.HermitCrab.Tool.csproj:25`) — is **not** among the staged files. So I can't state the element/attribute names, confirm human-readability, or describe an "add an affix" edit from source I actually read — that would be guessing. What the Tool source does indirectly confirm is that the domain model is linguistically named, not opaque: trace/print code references `Stratum` (`ParseCommand.cs:165-166`), `AffixTemplate` ("Template", `ParseCommand.cs:169-170`), `IMorphologicalRule`/`IPhonologicalRule` ("Rule", `ParseCommand.cs:167-168`), and `Morpheme.Gloss` (`MorphInfo.cs:24`) — consistent with, but not proof of, a readable rules/entries/strata XML. **This point needs closing with the actual core-library source or a sample `hc-config.xml` before the maintainer's claim can be fully verified; flag as open.**

## 3. `test` command

Syntax: `test <word> -p <form1>:<gloss1>|<form2>:<gloss2>|...` — one required positional `<word>` (`TestCommand.cs:25`), and `-p`/`--parse` is repeatable: each occurrence appends one expected-parse spec to a list (`TestCommand.cs:20-24`). A spec is `|`-delimited morphs, each `form:gloss` (`TestCommand.cs:102-108`); `\` escapes a literal delimiter (`TestCommand.cs:111-127`).

Matching (`TestCommand.cs:36-53`): for each actual parse from `Morpher.ParseWord(word)` (no trace), its morph sequence (`MorphInfo[]`) is compared via `SequenceEqual` against the remaining expected-parse list; a match is consumed (removed) so it can't double-match. `MorphInfo.Equals` (`MorphInfo.cs:39-42`) compares **both** form and gloss — gloss-sensitive. `SequenceEqual` is **order-sensitive** within one parse. Any actual parse not matched, and any expected parse never matched, both count as failures (`TestCommand.cs:55`) — this is exact multiset equality between expected and actual parse sets, not subset/superset tolerant.

Pass: `"Test passed."` (`TestCommand.cs:84`), preceded by `"Testing \"{word}\""` (`:35`).
Fail: `"Test failed."` / `"Expected parses:"` then either `"None"` or each unmatched expected parse via `WriteParse` (Morphs:/Gloss: lines) / `"Actual parses:"` then either `"None"` or each unmatched actual parse (`TestCommand.cs:58-79`).
Error (bad segment): `"The word contains an invalid segment at position {0}."` (`:92`), `ErrorTestCount++` (`:91`).

Machine-detectable: yes, unambiguously — `"Test passed."` and `"Test failed."` are distinct literal strings printed exactly once per test, with expected-vs-actual always both printed on failure.

## 4. Stats/tracing interaction

`test` increments its own counters — `TestCount`/`PassedTestCount`/`FailedTestCount`/`ErrorTestCount` (`HCContext.cs:36-39`, `TestCommand.cs:34,57,83,91`) — kept **separate** from parse counters. `stats -p` (as `hcparse.ps1:72` calls it) shows only parse stats (`StatsCommand.cs:18,40-49`); test stats need `stats -t` or bare `stats` (`StatsCommand.cs:19,25-29`). `tracing on` has **no effect** on `test` output: `TestCommand.Run` calls the non-tracing `ParseWord(word)` overload and never checks `IsTracing` or prints a trace (`TestCommand.cs:37`), unlike `ParseCommand.cs:30,46-49` which uses the `out trace` overload and prints when tracing is on.

## 5. Verdict

(a) **YES** — the export/CLI tool has no write-back path to a FLEx project in this source, and the driver already isolates the live `.fwdata` by copying it before config generation; the one unverified link (`GenerateHCConfig.exe`'s own behavior against that copy) is outside the reviewed source, not a demonstrated leak.

(b) **PARTIALLY** — `test`'s pass/fail text is unambiguous and prints expected-vs-actual, making it genuinely scriptable. But: exit code is useless for this (`Program.cs:98-113` discards every `ConsoleCommand.Run` return value in script mode and falls through to `return 0` at `:136`, exactly as already found for `parse` in cycle1-explore.md), so a corpus runner must screen-scrape `-o`/`stats -t`, not `$LASTEXITCODE`; and matching is strict multiset equality with no partial/subset mode, so a corpus entry breaks on any legitimate new ambiguity the grammar starts producing, not just on genuine regressions.

## 6. Honest job description

The maintainer's framing is **confirmed** by source for the write-safety half, **refined** for the workflow half: the CLI path is a disconnected, hand-editable HermitCrab grammar rehearsal environment — a linguist can edit the exported XML and use `parse`/`test`/`stats` to check hypotheses and a hand-curated regression corpus by exact form+gloss match, with no path back into the FLEx database in this source — but `test` corpora must be consumed via text (not exit code), the config's real editability rests on the core-library schema this review could not read (open item), and none of this changes the separate finding that mode 3b (filing) is unbuildable over this path since `ParseResult` needs live LCM object references the CLI's prose cannot reconstruct — so its job is strictly "rehearse and assert against a disposable grammar copy," never "apply."

**Open item to close before this fully lands:** the core `SIL.Machine.Morphology.HermitCrab` library source (or a real sample `hc-config.xml`/`HermitCrabInput.dtd`) was not in the staged files, so Q2's editability claim is only indirectly supported, not verified.

---

## Orchestrator addendum — the open item is CLOSED

The reviewing agent could not reach the core library and flagged §2 (editability)
as only indirectly supported. The orchestrator located and inspected the schema:

`d:\Github\_Projects\_LEX\machine\src\SIL.Machine.Morphology.HermitCrab\HermitCrabInput.dtd`
— 618 lines, and its element names are fully linguistic and human-readable:

```
HermitCrabInput Language PartsOfSpeech PartOfSpeech PhonologicalFeatureSystem
HeadFeatures FootFeatures SymbolicFeature Symbols Symbol ComplexFeature
FeatureValue MorphologicalPhonologicalRuleFeatures ... StemNames StemName
Regions Region CharacterDefinitionTable SegmentDefinitions SegmentDefinition
Representations Representation BoundaryDefinitions BoundaryDefinition
NaturalClasses FeatureNaturalClass SegmentNaturalClass Families Family
PhonologicalRuleDefinitions PhonologicalRule PhoneticInput
PhonologicalSubrules PhonologicalSubrule PhoneticOutput
LeftEnvironment RightEnvironment
```

**Verdict on §2: CONFIRMED, not merely indirectly supported.** The exported
config is DTD-documented XML whose elements map directly onto the linguist's own
vocabulary. The concrete edit lex-domain's G3 workflow step 5 calls for —
"tighten the environment restriction on the identified rule" — is editing
`<LeftEnvironment>` / `<RightEnvironment>` inside a `<PhonologicalRule>`, which
this schema exposes by name. Sibling files `XmlLanguageLoader.cs`, `Language.cs`
and `Stratum.cs` are present in the same directory if deeper verification is
wanted.

The sandbox is therefore usable in practice, not only in principle. The one
genuinely unverified link remains `GenerateHCConfig.exe`'s own behaviour against
the copied project (a FieldWorks binary, source not read) — that is an
unverified link, not a demonstrated leak.
