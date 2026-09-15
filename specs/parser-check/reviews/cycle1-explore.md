# hc.dll CLI output/trace format (run-tests mode only)

**Bottom line:** Not machine-parseable as-is. The `-o` file is line-oriented human prose
(labeled lines + an ASCII tree for traces), not XML/JSON/CSV. A consumer must screen-scrape
with regexes anchored on literal strings like `Parsing "`, `Morphs:`, `No valid parses.`, and
indentation-based tree lines for traces.

Sources read: `machine/src/SIL.Machine.Morphology.HermitCrab.Tool/{Program,ParseCommand,
TracingCommand,StatsCommand,TestCommand,HCContext,MorphInfo,Extensions}.cs`,
`SIL.Machine.Morphology.HermitCrab.Tool.csproj`, `machine/README.md`, `machine/.github/workflows/ci.yml`.
No `HermitCrab.Tool.Tests` project exists; the Tests dir only covers the engine, not CLI text output.

## 1. CLI flags and script commands
`Program.cs:24-35` — hc.dll accepts: `-i|--input-file=FILE` (config), `-o|--output-file=FILE`,
`-s|--script-file=FILE`, `-c|--continue` (don't quit on config load error), `-h|--help`. Confirms
`-i`/`-s`/`-o` used by hcparse.ps1; no `-c` is passed by the script (Program.cs:22 `quitOnError=true` default).
Script-file commands (registered `ConsoleCommand`s, Program.cs:89-95): `parse <word>` (ParseCommand.cs:16),
`tracing [on|off]` (TracingCommand.cs:13), `test <word> -p <form:gloss|...>` (TestCommand.cs:18),
`stats [-p|-t|-r]` (StatsCommand.cs:16). All four script lines in hcparse.ps1 (`tracing on`, `parse <w>`,
`stats -p`) are valid and exactly match.

## 2/3. `-o` shape and fields, per outcome
Plain text, one block per `parse` call. `ParseCommand.cs:27,42-43` and `Extensions.cs:15-45`:
```
Parsing "word"
Parse 1
Morphs: root suffix
Gloss:  ROOT  SFX
Parse 2
Morphs: ...
Gloss:  ...
Parse time: 12ms
```
Fields per analysis: only **Form** and **Gloss** per morph (`MorphInfo.cs:12,29-37`), space-padded
to align columns; gloss defaults to `"?"` if empty (MorphInfo.cs:25-26). No morph type, no lexical-entry
ID, no stratum, no rule list are printed for a normal parse — only inside a trace (see Q4).
- One analysis: single `Parse 1` block.
- Several analyses: one `Parse N` block per analysis, in Morpher order, no total count line (only
  `stats -p` later gives totals).
- Failure (no parse): `_context.Out.WriteLine("No valid parses.");` (ParseCommand.cs:35) — no `Parse N`
  block at all, still followed by `Parse time:` line.

## 4. `tracing on` output
Printed only if `_context.Morpher.TraceManager.IsTracing` (ParseCommand.cs:46-49), appended after the
parse result and before `Parse time:`. It's a recursive indented tree (`PrintTrace`,
ParseCommand.cs:63-125): each node is one line, `"<TypeLabel> [<RuleLabel>: <Name>(<subruleIdx>), Input: ...,
Output: ..., Reason: <FailureReason>]"`, children drawn below with `|`/`+-` ASCII connectors
(ParseCommand.cs:108-131). No blank-line or marker delimits one node's *children* — indentation and the
next `+-`/`|` glyphs are the only structure. There is **no** word-level start/end delimiter for the trace
itself beyond the surrounding `Parsing "word"` … `Parse time:` lines already used for the parse block, so
a consumer can seek by scanning for `Parsing "` occurrences (regex/line-based), not by fixed byte offsets
(word/gloss/rule-name lengths vary).
Failure identification: yes, in a machine-identifiable way — a `Failed`/`Blocked` node
(`GetTraceTypeString`, ParseCommand.cs:182-217: "Failed Parse"/"Blocked Parse") carries `Reason: <enum>`
whenever `trace.FailureReason != FailureReason.None` (ParseCommand.cs:100-105), and the enclosing node
names the blocking rule via `RuleLabel: Name(subruleIndex)` (e.g. `Rule: Voicing(2)`,
`Stratum: Word`, `Template: Verb`) from `GetRuleLabelString` (ParseCommand.cs:163-172).

## 5. Distinct failure outputs
Three distinguishable top-level outcomes:
1. **Invalid/unknown character** — thrown before parsing as `InvalidShapeException`; printed as
   `"The word contains an invalid segment at position {N}."` (ParseCommand.cs:57, 1-based position) —
   counted in `ErrorParseCount` (HCContext.cs:34; ParseCommand.cs:56).
2. **Genuine no-parse / missing lexical entry** — both produce the *same* top-level text,
   `"No valid parses."` (ParseCommand.cs:35), counted in `FailedParseCount`. There is no distinct
   "unknown word / no lexical entry" message at the `-o` top level. With `tracing on`, the two are
   distinguishable only by tree-walking: a `Lexical Lookup` node with no children means no root matched
   (`TraceManager.cs:123-127`), vs. a `Lexical Lookup` node with children whose descendants hit a
   `Blocked`/`Failed` node with a `Reason:` (rule/pattern/co-occurrence blocked) means a real rule failure.
3. **Successful parse** — `Parse N` / `Morphs:` / `Gloss:` blocks (see Q2/Q3).
`FailureReason` enum (23 values) is exhaustive per `ITraceManager.cs:3-29` (e.g. `Pattern`,
`RequiredMprFeatures`, `BoundRoot`, `PartialParse`, `MaxApplicationCount`, etc.) — only surfaced when tracing.

## 6. `stats -p` output
`StatsCommand.cs:42-48`: single line —
`"# of parses: {0}, successful: {1}, failed: {2}, error: {3}"` followed by a blank line
(StatsCommand.cs:62). Counters are cumulative for the whole script run, not per word.

## 7. Exit codes
`Program.Main` returns `-1` only for: no `-i` / `--help` (Program.cs:47-51), an `OptionException`
parsing args (Program.cs:41-45), or a config-load `IOException`/`Exception` (Program.cs:74-87).
Critically, when a script file is used, **per-command return codes are discarded**: the loop at
`Program.cs:98-113` calls `ConsoleCommandDispatcher.DispatchCommand(commands, cmdArgs, context.Out);`
without checking or propagating its `int` return, and falls through to `return 0;` at Program.cs:136
unconditionally. So `ParseCommand.Run` returning `1` on `InvalidShapeException` (ParseCommand.cs:59) or
a word simply failing to parse (`"No valid parses."`, still `return 0` at ParseCommand.cs:52) **never**
changes the process exit code. **A caller cannot distinguish a run with failed/errored words from a
clean run via exit code alone** — exit code is 0 in both cases; only a bad/missing config file yields -1.
This must be checked by parsing `stats -p`'s `failed`/`error` counts (or per-word text) from `-o`, not `$LASTEXITCODE`.

## 8. Install story
`SIL.Machine.Morphology.HermitCrab.Tool.csproj:4-11`: `PackAsTool=true`, `ToolCommandName=hc`,
`AssemblyName=hc`, `PackageId=SIL.Machine.Morphology.HermitCrab.Tool` — this is a real **dotnet global
tool**, packed and pushed to nuget.org by CI (`.github/workflows/ci.yml:100` packs
`SIL.Machine.Morphology.HermitCrab.Tool.csproj`; line 115 `dotnet nuget push artifacts\*.nupkg ...
-s https://api.nuget.org/v3/index.json`). It is not vendored/build-yourself only; README.md:85-88 shows
the general pattern for the sibling tool (`dotnet tool install -g SIL.Machine.Tool`), so the equivalent
real install hint is `dotnet tool install -g SIL.Machine.Morphology.HermitCrab.Tool`. Note this installs
an `hc`/`hc.exe` shim under the user's dotnet tools dir (typically `%USERPROFILE%\.dotnet\tools`), **not**
`hc.dll` under `%LOCALAPPDATA%\HermitCrabTool\` as hcparse.ps1 currently expects (hcparse.ps1:23-25) — a
"tool not installed" error should mention the `dotnet tool install -g` command, not just the missing path.
