# ParserCore Headless-Feasibility Check (cycle 1)

**Q1 VERDICT: PARTIALLY STUBBABLE.** `m_propertyTable` is fully optional (one
read, defaults safely to `null`); `m_idleQueue` is NOT optional as-is, but its
one real job (deferred `UpdateWordforms`) can be called synchronously by a
headless caller instead of enqueuing through `IdleQueue`.

## Q1 -- ParseFiler without the framework

a) **`m_propertyTable` usage -- exactly one read**, `ParseFiler.cs:193`:
`bool updateAnalyses = m_propertyTable == null ? true : m_propertyTable.GetBoolProperty("CheckParserUpdatesAnalyses", true);`
This already null-guards itself and defaults to `true` (do the write) when
null. It is a UI preference toggle, not load-bearing for the write path.
**Pass `null` for `propertyTable`.**

b) **`m_idleQueue` usage -- two sites, `ParseFiler.cs:132` and `:146`**, both
`m_idleQueue.Add(IdleQueuePriority.Low, UpdateWordforms)`. `UpdateWordforms`
(lines 160-247) is where all real work happens: dequeues `m_workQueue`,
wraps two `NonUndoableUnitOfWorkHelper.Do` blocks, calls `ProcessAnalysis`
and `SetUnsuccessfulParseEvals`, and is what actually persists the parse into
`AnalysesOC`/`MorphBundlesOS`. **This is essential, not a UI refresh** --
skipping it means `ProcessParse` silently does nothing but enqueue. It is
gated only by `CanStartUow` (line 165), a plain `IActionHandlerExtensions`
check, not a UI/idle-loop concept. A headless caller can call
`UpdateWordforms(null)` directly and synchronously after `ProcessParse`
instead of routing through a real `IdleQueue`; the constructor's
`Debug.Assert(idleQueue != null)` (line 100) means you still need a
minimal no-op/synchronous stand-in object satisfying the `IdleQueue` type,
not a literal `null`.

c) Both `NonUndoableUnitOfWorkHelper.Do` blocks (179-189, 191-245) close over
`m_cache.ActionHandlerAccessor` and otherwise touch only cache-derived
factories/repositories (`m_analysisFactory`, `m_mbFactory`,
`m_baseAnnotationRepository`, `m_parserAgent`, `m_userAgent`) set up in the
ctor from `cache.ServiceLocator`. Nothing beyond the cache is required.

d) `taskUpdateHandler`: yes, can be a no-op `Action<TaskReport>` -- it is
only invoked via `TaskReport` construction (line 215) for progress
reporting, `Debug.Assert(taskUpdateHandler != null)` (line 99) just forbids
literal `null`, not a no-op delegate. `WordformUpdated` (line 62): safely
left unsubscribed -- `FireWordformUpdated` (249-253) null-checks the
handler before invoking.

e) **Net verdict**: STUBBABLE with two concrete adaptations: (1) pass
`propertyTable = null`; (2) supply a minimal `IdleQueue`-typed stub whose
`Add` either runs the callback immediately or is replaced by the caller
invoking `UpdateWordforms` synchronously post-`ProcessParse`. Nothing in
`ParseFiler` requires the FLEx GUI, `PropertyTable` settings, or an actual
idle-loop thread to produce a correct DB write.

## Q2 -- Parser/agent selection

Confirmed verbatim in `ParserWorker.cs`:
- Line 65: `switch (m_cache.LanguageProject.MorphologicalDataOA.ActiveParser)`
- Line 67: `case "XAmple":` -> line 69:
  `cache.ServiceLocator.GetInstance<ICmAgentRepository>().GetObject(CmAgentTags.kguidAgentXAmpleParser)`
- Line 71: `case "HC":` -> line 73:
  `cache.ServiceLocator.GetInstance<ICmAgentRepository>().GetObject(CmAgentTags.kguidAgentHermitCrabParser)`
- Line 75-76: `default: throw new InvalidOperationException(...)`.

`ICmAgentRepository.GetObject(guid)` is called directly on
`cache.ServiceLocator` with no `ParserWorker` instance involved -- a headless
caller can replicate lines 65-77's switch/GUID lookup verbatim without ever
constructing `ParserWorker`.

## Q3 -- XAmple's `dataDir`

`ParserWorker.cs:59`'s ctor takes `dataDir` as a plain parameter with no
default and no derivation inside `ParserWorker.cs` itself -- it is passed
straight through to `new XAmpleParser(cache, dataDir)` (line 68) and is
otherwise unused in this file. `ParserWorker.cs` gives no clue what the
caller (`ParserScheduler`, not staged in full detail here beyond the
already-established facts) passes as `dataDir`. `M3ToXAmpleTransformer.cs`
(used by `XAmpleParser`, not staged) writes its generated `adctl.txt`,
`gram.txt`, `lex.txt`, `gafawsData.xml` files via
`Path.Combine(Path.GetTempPath(), m_database + "...")` (lines 185, 195, 201-215)
-- i.e. XAmple's working files go to the OS temp dir keyed by a `database`
string passed to its own ctor (`M3ToXAmpleTransformer(string database)`,
line 36), not to `dataDir` directly. **Gap: cannot determine from staged
files** what value `ParserScheduler`/its caller supplies for
`ParserWorker`'s `dataDir`, nor how/whether `XAmpleParser.cs` relates that
argument to `M3ToXAmpleTransformer`'s `database` string (same value? a
parent directory of it?). `XAmpleParser.cs` was not staged and is required
to close this gap -- flagging per instructions rather than guessing.

## Q4 -- Loading and version coupling

a) Confirmed: `_default_liblcm_search_paths()`
(`src/flextoolsmcp/server/versioning.py:156-175`) already includes
`Path(r"C:/Program Files/SIL/FieldWorks 9")` (line 172) and the x86 variant
(line 173), the same directory `ParserCore.dll` ships in. `locate_liblcm_dll()`
(178-201) walks that same list. **No new install step, download, or loading
mechanism is needed** -- adding a `ParserCore.dll` load is an additional
`clr.AddReference`/`Assembly.Load` call against a directory the server
already searches. This is a layer-widening change, not a footprint change.

b) No. Loading `ParserCore.dll` and constructing `HCParser` does **not**
force `xCore`/WinForms to load. `HCParser.cs`'s `using` list (lines 5-18) is
`System*`, `SIL.LCModel`, `SIL.LCModel.Infrastructure`,
`SIL.Machine.Annotations`, `SIL.Machine.Morphology.HermitCrab(.MorphologicalRules)`,
`SIL.ObjectModel` -- no `XCore` using, and grepping the file for
`XCore|PropertyTable|IdleQueue` returns zero matches. The .NET CLR resolves
an assembly reference only on first use of a type from it (JIT-time, per
method); since `HCParser`'s own code (ctor, `IsUpToDate`, `Update`,
`ParseWord`, `ParseWordXml`, `TraceWordXml`) never references an `XCore.*`
or `PropertyTable`/`IdleQueue` type, no `xCore.dll` load is triggered by
that call path -- even though `ParserCore.csproj` references `xCore` and
`xCoreInterfaces` at the assembly level (those references exist to satisfy
`ParseFiler.cs` and `ParserWorker.cs`, which are NOT on the read-only
`HCParser`-only call path). The read-only path is UI-free at runtime, not
just at the source level, PROVIDED the caller instantiates `HCParser`
directly and never touches `ParserWorker`/`ParseFiler`/`ParserScheduler`.

c) The existing version-detection machinery (`detect_liblcm_version_from_disk`,
`locate_liblcm_dll`, `find_versioned_api_file`) is keyed to `SIL.LCModel.dll`
specifically and to the `liblcm_api_v*.json` index-file naming convention;
nothing in it inspects `ParserCore.dll`'s own assembly version. `ParserCore`
and `LCModel` ship from the same FieldWorks install and directory, but the
established index (`v11.0.0`) is an *LCM* API-surface version, not a
FieldWorks build number, and there is no guarantee `ParserCore.dll`'s
assembly version moves in lockstep with `SIL.LCModel.dll`'s (they're
separate projects in the same solution/release train, but independently
versioned assemblies). **Recommend: give ParserCore its own version gate**
(a `detect_installed_library_version(..., assembly_name="ParserCore")` call
plus a `parsercore_api_v*.json`-style versioned index, mirroring the LCM
pattern) rather than assuming the LCM version number covers it -- reusing
LCM's version silently would give false confidence if a future FieldWorks
release bumps `ParserCore.dll` without bumping `SIL.LCModel.dll`, or ships a
prerelease combination of the two.

## Staged-file gaps
`XAmpleParser.cs` was not staged (as flagged upfront) -- Q3's `dataDir`
provenance and `M3ToXAmpleTransformer`-to-`XAmpleParser` linkage cannot be
fully closed without it. `ParserScheduler.cs` was staged but not re-read in
this pass beyond already-established facts; if the orchestrator wants
`dataDir`'s ultimate origin traced further up the call chain, that file's
constructor/caller code would need a targeted re-read.
