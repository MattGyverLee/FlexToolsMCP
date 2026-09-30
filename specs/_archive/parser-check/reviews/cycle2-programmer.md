# Cycle 2 -- Programmer audit (parser-check)

## 1. dataDir gap

`m_dataDir` (`XAmpleParser.cs:27,43`) is used exactly once: `m_xample.LoadFiles(Path.Combine(m_dataDir, "Configuration", "Grammar"), Path.GetTempPath(), m_database)` (:139). That's a **static, install-relative support folder** (grammar-debugger stylesheet/template files shipped with FieldWorks), not per-project data -- unlike `m_database`, the sanitized project name (`ConvertNameToUseAnsiCharacters`, :45/:74-92) that XAmple's *generated* per-project files (`adctl.txt`, `gram.txt`, `lex.txt`, `gafawsData.xml`, all written by `M3ToXAmpleTransformer` under `Path.GetTempPath()`) are keyed by. So `dataDir` itself is cheap to supply (bundle the folder, or resolve it the same way H1 resolves `-FieldWorksDir`).

The caller that supplies `dataDir` isn't in the staged set (`ParserScheduler`'s constructor just forwards it), so its origin (presumably FLEx's code-install directory) is inferred, not confirmed.

**The real blocker isn't `dataDir` -- it's that XAmple has no CLI boundary at all.** HermitCrab ships `hc.dll` as an external dotnet global tool with a text-in/text-out contract we can shell out to. XAmple has no equivalent: `XAmpleParser` only runs in-process via `XAmpleWrapperFactory.Create()` -> `IXAmpleWrapper`, a native wrapper around `xample.dll` (COM/native interop, `XAmpleManagedWrapper` namespace), invoked directly against an open `LcmCache`. Supporting XAmple would mean either embedding that native wrapper in the MCP process or shelling into full FieldWorks -- neither fits "indexing, not executing" or the subprocess-CLI pattern H1-H12 already assumes for HC.

**Recommendation:** scope parser-check to `ActiveParser == "HC"` only -- `ParserWorker.cs:65-76` already treats `"XAmple"`/`"HC"` as the only two legal values (`InvalidOperationException` otherwise), so this matches production behavior. Document XAmple as explicitly out of scope pending a real CLI wrapper, not a `dataDir` config knob.

## 2. Safety guarantee (HCParser never loads XCore)

**(a) Robustness.** Confirmed at the source level for the full construct+Update+ParseWord path: `HCParser.cs`, `HCLoader.cs`, `FwXmlTraceManager.cs`, `ParserModelChangeListener.cs`, `IHCLoadErrorLogger.cs` import zero `XCore`/`SIL.FieldWorks.Common.FwUtils` types between them. `HCParser : DisposableBase, IParser` -- base class source isn't staged, so its neutrality is inferred from broad reuse (also base for `ParserScheduler`, `XAmpleParser`, `ParserModelChangeListener`), not proven; stage `SIL.ObjectModel.DisposableBase` before calling this closed. `ParseFiler` is never constructed or referenced by `HCParser` (0 hits) -- it's wired up separately, only by `ParserWorker`'s constructor (`ParserWorker.cs:78`).

The one real fragility: **the guarantee is per call-graph, not per-class.** `ParserWorker`'s and `ParserScheduler`'s own constructors take `PropertyTable`/`IdleQueue` (`XCore` types) as parameters (`ParserWorker.cs:16,59`; `ParserScheduler.cs:147`) -- JITting *those* constructors resolves `XCore` regardless of what `HCParser` does internally. The read-only tool must construct `new HCParser(cache)` directly and never go through `ParserWorker`/`ParserScheduler`. State this constraint explicitly in the design -- it's the one place a future refactor (e.g. "just reuse ParserWorker for consistency") would silently break the guarantee.

**(b) Standing test.** Spawn an isolated process (not the shared test host, which may already have `XCore` loaded for unrelated reasons) that: constructs `new HCParser(cache)` against a real/test `LcmCache`, calls `Update()` then `ParseWord()` for at least one word (forces `HCLoader`/`Morpher`, not just the ctor), then asserts `AppDomain.CurrentDomain.GetAssemblies()` contains no assembly named `XCore`, `System.Windows.Forms`, or `SIL.FieldWorks.XWorks`/`FwUtils`. Make this a named standing test (e.g. `HCParser_DoesNotLoadXCore`) gating any future change to `ParserCore`.

**(c) ParseFiler reachability.** No path from `HCParser` reaches `ParseFiler` -- confirmed by absence of the type in `HCParser.cs`. **A tool that only constructs and drives `HCParser` directly cannot reach a write type at all; that is the feature's safety story**, and it depends on never routing through `ParserWorker`/`ParserScheduler` (see (a)).

## 3. H4 / H1 rewrite

**H4 (was: check `$LASTEXITCODE` after `dotnet hc.dll`; non-zero = hard failure).** False premise confirmed: per-command dispatch discards return codes and falls through to `return 0` (`Program.cs:98-113`); only a bad/missing `-i` config yields `-1`.

> **H4 (replacement):** `$LASTEXITCODE` from `dotnet hc.dll`/`hc.exe` is meaningful **only** as a tool-invocation signal -- nonzero (or the process failing to start) is a hard failure (`parser_tool_missing`/`parser_config_failed`), because the CLI itself always exits 0 once it starts successfully, even when every word fails or errors. Word-level success/failure must be parsed out of the mandatory trailing `stats -p` line, `# of parses: {0}, successful: {1}, failed: {2}, error: {3}` (`StatsCommand.cs:42-48`), for the aggregate, and from each word's own block in the `-o` file for per-word attribution. A word with zero analyses or an internal parse error is a **reportable word-level result**, not a script failure, and must still populate `run.json` (H3) for every word in the input list.

Note H3 should cross-reference this: "per-word results" in H3 are derived from stats+per-word text, not exit code -- H3 itself isn't wrong, just underspecified without H4's method.

**H1 (was: hardcode `%LOCALAPPDATA%\HermitCrabTool\hc.dll`).** False: `hc` is a dotnet **global tool** (`PackAsTool=true`, `ToolCommandName=hc`, published as `SIL.Machine.Morphology.HermitCrab.Tool` on nuget.org), installing an `hc`/`hc.exe` shim to `%USERPROFILE%\.dotnet\tools`.

> **H1 (replacement):** Resolve `hc` in order: (1) `-HcToolPath`/config override `parser.hc_tool_path` if set; (2) `dotnet tool list -g` output, parsed for the `hc` tool's install location; (3) `%USERPROFILE%\.dotnet\tools\hc.exe` on PATH. Invoke the resolved `hc`/`hc.exe` shim directly -- not `dotnet hc.dll`. If none resolve, raise `parser_tool_missing` with `install_hint = "dotnet tool install -g SIL.Machine.Morphology.HermitCrab.Tool"`. The `-FieldWorksDir` half of the original H1 (for `GenerateHCConfig.exe`) is unaffected and stays.

**Other rows:** none of the remaining 10 are factually invalidated by these two fixes. H5's exit-code check is on `GenerateHCConfig.exe`, a different binary whose exit-code semantics weren't examined here (source not staged) -- flag as still-unverified, separate from H4's finding.

**Sandbox implication (H6/H10).** Given the maintainer's framing -- the exported config is a keepable rehearsal artifact, not disposable scratch -- H6 should delete only the **copied `.fwdata` project** (always disposable) and leave the generated `hc-config.xml`'s lifecycle to H10/section-7 caching, not bundle both under one "clean up temp" rule. H10's `-ConfigOut` is fine for the cached/regenerable case, but the design needs a second, distinct path for a **user-owned, hand-edited sandbox config** (hcparse.ps1 already has this half-built via `-Config`, "skip config regeneration") that the cache/fingerprint logic (7.1/7.2) must never silently overwrite or invalidate. Recommend making that distinction explicit before CP3 locks in the cache design.

## 4. Genre fact-check (6.4)

Both halves confirmed against the indexes:
- `flexicon_api_v4.8.0.json`, `TextOperations.GetGenre`: "Retrieves the first genre assigned to the text. In FLEx, texts can technically have multiple genres, but typically only one is assigned." -- matches the spec's claim exactly.
- `liblcm_api_v11.0.0.json`, `IText.GenresRC`: `ILcmReferenceCollection`, target `ICmPossibility`, `pythonic_name: "Genres"`.

**GenresRC is not wrapped by any flexicon Operations method** -- no `TextOperations`/other entity exposes a "get all genres" method; the only flexicon-side surface is the raw LCM property itself (`pythonic_name: "Genres"`, i.e. descriptor-protocol access on the raw LCM object, not an Operations wrapper call). So 6.4's plan does force raw-LCM access (`text.GenresRC` or `text.Genres` via pythonnet), which the spec doesn't currently call out -- worth a one-line addition noting genre-scope resolution is one of the few places this feature touches raw LCM rather than a flexicon wrapper.
