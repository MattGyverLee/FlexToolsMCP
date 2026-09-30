# Domain Expert Review -- parser-check CP2 (cycle 1)

Static review against liblcm + FieldWorks sources. No FLEx project was opened or
written; no -restore required.

## 1. Where the HC parser lives / same-install check -- SUPPORTED

`SIL.FieldWorks.WordWorks.Parser.HCParser` and `IParser` live in `ParserCore.dll`
(`FieldWorks/Src/LexText/ParserCore/{HCParser,IParser}.cs`), assembly name
`ParserCore`, built for `net48`. `deploy_parsercore.bat` confirms it is deployed
straight into `C:\Program Files\SIL\FieldWorks 9\`, the same directory as
`SIL.LCModel.dll` -- i.e. `parser_probe.py`'s directory-equality check
(`get_resolved_fieldworks_dir()` vs. `locate_liblcm_dll("ParserCore.dll").parent`)
matches real deployment, not a hypothetical.

Real failure mode when absent/relocated: `locate_liblcm_dll` returns `None` ->
`SIGNAL_ABSENT`; this is a cheap filesystem check, never a CLR load, so "missing"
degrades safely as FR-003 requires.

## 2. Mismatched-install edge case -- SUPPORTED, with a residual gap

`Assembly.LoadFile` on a foreign-install `ParserCore.dll` would succeed at the
reflection level regardless of version; the real failure (a `SIL.LCModel`
type-binding mismatch) only surfaces when a member is actually *invoked* (JIT-time),
which is exactly why the directory-equality proxy exists rather than a load-and-call
test.

GAP: the check only compares folder paths -- a foreign DLL manually copied *into* the
correct install directory would pass the same-install gate undetected. Worth a
one-line caveat in the spec.

## 3. Named-vs-positional binding -- REFINE, not REFUTED

Confirmed real, but narrower than the spec states.

- `IParser.cs`: `ParseWord(string word)`, `ParseWordXml(string word)`,
  `TraceWordXml(string word, IEnumerable<int> selectTraceMorphs)`
- `HCParser.cs`: `ParseWord(string word)` -- **matches** the interface -- but
  `ParseWordXml(string form)` and `TraceWordXml(string form, IEnumerable<int> selectTraceMorphs)`
  -- **mismatch** (`form` vs. `word`).

So the mismatch bites exactly two methods (`ParseWordXml`, `TraceWordXml`), not
`ParseWord`. The spec's phrasing ("interface and implementation disagree") is broadly
true but should name these two methods specifically, since `TraceWordXml` is mode
A/C's core call.

## 4. Version reporting -- SUPPORTED, nothing new needed

`detected_version` is `assembly.GetName().Version` (`Major.Minor.Build`) off
`ParserCore.dll` itself, exactly as `parser_probe.py::_load_parser_core_members`
already implements for CP1. CP2 reuses this unchanged; FR-006 requires no new
mechanism.

## 5. Grammar currency / forced discard -- PARTIALLY REFUTED (most valuable finding)

`IParser.IsUpToDate()` -> `HCParser`: `return !m_changeListener.ModelChanged`. Real
production caller, `ParserWorker.CheckNeedsUpdate()`:
`if (!m_parser.IsUpToDate()) m_parser.Update();`

But `Update()` itself is conditional:
`if (m_changeListener.Reset() || m_forceUpdate) LoadParser();`
-- calling `Update()` alone does **not** unconditionally discard/reload when nothing
changed. FieldWorks' own force-reload path, `ParserWorker.ReloadGrammarAndLexicon()`,
calls `m_parser.Reset()` **then** `CheckNeedsUpdate()` -- i.e. the real
"unconditional discard" is `Reset()+Update()`, not `Update()` alone.

CP2-SPEC section 3.1's facade table maps only `Reload() -> Update()` and never wraps
`Reset()` at all. As specified, `project.Parser.Reload()` will NOT satisfy FR-043's
"explicit reload MUST discard the held grammar unconditionally".

**FLAG for spec/plan:** `Reload()` must bind to `Reset()+Update()`, and `Reset()` /
`IsUpToDate()` must be added to the required-member set the capability probe reflects
over -- `HCPARSER_MEMBERS` in `parser_probe.py` currently only lists
`HCParser(LcmCache)`, `Update()`, `ParseWord(string)`, `TraceWordXml(...)`,
`ParseWordXml(string)`; it never verifies `IsUpToDate()` or `Reset()` exist, even
though CP2's whole D2/D3 currency story depends on both.

## 6. The three read gaps -- SUPPORTED for genres/MSA, REFUTED-AS-STATED for allomorph

(a) **Genres -- SUPPORTED.** `IText`'s `GenresRC` is a real full reference collection
(`StText.cs:585`); flexicon's `TextOperations.GetGenre()` returns only one -- genuine
wrapper gap, LCM itself already carries all genres.

(b) **Allomorph -> owning entry -- REFUTED AS FRAMED.** LCM already exposes this:
`MoForm.OwningEntry` (`OverridesLing_MoClasses.cs:3113`,
`[VirtualProperty(..., "LexEntry")]`) is inherited by
`MoStemAllomorph`/`MoAffixAllomorph` (both `partial class` subtypes of `MoForm`), the
same pattern `MoMorphSynAnalysis.OwningEntry` already uses. `AllomorphOperations.py`
confirms the *wrapper* has no `GetOwningEntry` (only
`GetForm/GetFormAudio/GetMorphType/GetPhoneEnv`) -- so this is a trivial wrapper-only
gap, not an LCM limitation. The spec's framing ("LCM read gap") overstates it; useful
for scoping that deliverable's cost down.

(c) **MSA read surface -- SUPPORTED, genuinely absent.** `MSAOperations.pyi:14-20`
states explicitly no `GetAll/Find/Create-adjacent` read surface exists; only
Create/Set/Change/RemoveOrphaned mutators. This one is real and nontrivial (MSA
subtypes -- `MoStemMsa`, `MoInflAffMsa`, `MoDerivAffMsa` -- expose different property
sets, so "a readable-properties surface" is not one flat wrapper).

## 7. Identity preservation -- SUPPORTED for object mode, caveat for XML mode

`HCParser.ParseWord`'s internal `MorphInfo` class carries `IMoForm Form`,
`IMoMorphSynAnalysis Msa`, `ILexEntryInflType InflType` -- real LCM object references,
not strings, matching CP2-SPEC section 3.1's marshalling recommendation.

But `TraceWordXml`/`ParseWordXml` return an already-serialized `XDocument` where
objects appear only as `Hvo` integer attributes (`XAttribute("id", form.Hvo)`,
`XAttribute("id", msa.Hvo)`) -- identity survives only as a raw integer, requiring a
repository lookup to rehydrate, not a live object reference.

FR-010's "preserve identity" claim holds for Mode B (`ParseWord`) but for the trace
payload (Modes A/C) identity is Hvo-only text inside XML. The spec's "trace crosses
unchanged" assumption already anticipates this but should say plainly that it
satisfies FR-010 only via Hvo, not object identity.

## 8. Engine gate -- mechanism SUPPORTED; D3's project claims UNVERIFIABLE-WITHOUT-LIVE-RUN

`LangProject.MorphologicalDataOA.ActiveParser` (`OverridesLing_MoClasses.cs:4197`) is
a real string property, reading `/ParserParameters/ActiveParser` from XML with a hard
`"XAmple"` fail-safe default on any parse exception -- exactly matching
`check_active_parser`'s docstring claims in `parser_probe.py`. This confirms the
*mechanism* fully.

No live FieldWorks project data was opened, so `Sena 3` = XAmple/0 rules vs.
`IndonesianHC-Complete` / `Malay Parsing-20230810withHC` = HC remains unconfirmed --
those per-project facts require opening the actual `.fwdata` files, out of scope for a
static review.

## 9. Additional finding -- ParserCore's XCore reference (bears on FR-017 / HCParser_DoesNotLoadXCore)

`ParserCore.csproj` references `xCoreInterfaces.dll` / `xCore.dll` / `FwUtils.dll`
(`<Private>false</Private>`, expected already present in the FW install dir).
Grepping actual `using XCore;` / `using SIL.FieldWorks.Common.FwUtils;` shows these
are used only in `ParseFiler.cs`, `ParserScheduler.cs`, `ParserWorker.cs` -- **not**
in `HCParser.cs`, `HCLoader.cs`, or `IParser.cs`.

Since all compile into one `ParserCore.dll`, the assembly-level reference to xCore
exists regardless of which types are touched. The SC-003/FR-017 "no UI framework
loaded" guarantee is real only because .NET binds referenced assemblies lazily per
type-touch, NOT because the reference is absent.

The standing test must therefore assert on the *loaded-assemblies list of the process
after a real parse* (which CP2 already plans, per the spec's own wording "must cover
the call path, not a class"). That is already the right design -- worth confirming the
mechanism explicitly rather than assuming "ParserCore doesn't reference xCore."

## Summary -- what needs spec/plan attention

1. `Reload()`'s binding must be `Reset()+Update()`, not `Update()` alone, to satisfy
   FR-043's "unconditional discard".
2. `Reset()` and `IsUpToDate()` must join the capability probe's required-member set.
3. The interface/impl name mismatch is `ParseWordXml` / `TraceWordXml` specifically,
   not `ParseWord`.
4. Allomorph -> owning entry is a flexicon-only gap (LCM already has it via
   `MoForm.OwningEntry`) -- scope that deliverable down.
