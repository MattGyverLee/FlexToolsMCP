# SPEC -- parser-check: let the MCP run FLEx's parser and verify its own work

**Feature:** `parser-check`
**Repo:** FlexToolsMCP
**Status:** spec, not implemented -- rewritten after crew review spurt 1 (cycles 1-2)
**Filed issues:** (none yet)
**Source:** user-contributed `hcparse.ps1` (repo root), 2026-09-15
**Author:** Claude Code, with matthew_lee@sil.org
**Reviews:** [`reviews/`](reviews/) -- cycle1 and cycle2: programmer, domain, author, explore
**Machine state:** [`.crew-handoff.json`](.crew-handoff.json)
**Depends on:** `project_discovery`, `project_access`, `subprocess_helpers`,
`op_telemetry`, `backup.py`, and the `tool-responses/1.0` contract

---

## 1. Context

The MCP can already change a lexicon and a morphology: entries, allomorphs,
environments, MSAs, phon rules, strata. What it cannot do is tell whether any of
that was *linguistically* correct.

`run_module` reporting `[OK] Operation completed successfully` means the Python
ran and LCM accepted the write. It says nothing about whether the affix you just
added actually lets `membaca` parse, or whether the environment you tightened
just broke forty words that used to parse. Without a parser in the loop the user
must leave the session, run the parser by hand in the FLEx GUI, and come back.

FLEx has three parser modes, and this feature serves all three:

| FLEx mode | What it does | Our spine |
|---|---|---|
| 1. Parse a text | Adds new analyses to the database | in-process **write** |
| 2. Try a word | Cannot add analyses; hypothesis testing. **Itself three trace modes** -- 5.1.1 | in-process **read** |
| 3. Run tests | 3a does not update analyses; 3b may | **sandbox** (3a) / spine 1 (3b) |

### 1.1 Two axes, three spines

The design turns on two orthogonal questions that earlier drafts conflated:

- **Does it file?** (non-filing vs. filing)
- **Whose grammar?** (the live project's vs. an edited exported snapshot)

|  | **Live project grammar** | **Edited exported grammar** |
|---|---|---|
| **Non-filing** | **DISCOVERY** -- G1/G2/G3, true answers, no side effects | **SANDBOX** -- speculative grammar edits |
| **Filing** | **COMMIT** -- apply confident changes | *impossible* |

The empty cell is not an oversight. `ParseMorph` holds live `IMoForm` /
`IMoMorphSynAnalysis` references (`ParseResult.cs:154-177`), so results computed
against an *edited* grammar have no valid live objects to point at. Filing from a
sandbox parse is not merely hard to build -- it is semantically incoherent. This
is the same fact that makes FLEx mode 3b unbuildable over the CLI, reached from
the other direction.

### 1.2 The confidence gradient

The maintainer's operating principle, and the spine of the safety design:

> "Tweaking an exported grammar to test a theory IS safer than changing the whole
> database and having to change it back. I can see benefit to tests in an export,
> and live changes for confident changes."

Each rung's safety property is **structural**, not conventional:

| Rung | Mechanism | Safety property | Evidence |
|---|---|---|---|
| **Rehearse** | Export config, run `hc` CLI on a copied project | No path back to the live DB *exists* | `hc` touches only `-i`, `-s`, `-o`; no `.fwdata`, registry or FieldWorks path anywhere in the tool source |
| **Hypothesis-test** | `HCParser(cache)` -> `ParseWord` / `TraceWordXml` | Cannot reach a write type *at all* | `HCParser` never references `ParseFiler`; its full call graph loads no xCore/WinForms |
| **Commit** | `ParseFiler.ProcessParse` | FLEx's own filer, FLEx's own agent, full write ladder | Identical chain to the FLEx menu path |

---

## Clarifications

### Session 2026-09-15

- Q: How does a batch parse return to the caller -- one blocking call, or a
  start-and-poll job? -> A: **Start-and-poll job.** A full-corpus parse can run
  for hours, and the parser can exhaust RAM and die; a blocking call cannot
  represent either outcome honestly.
- Q: Does the single-word `flextools_try_word` also go through the job model, or
  stay a direct blocking call? -> A: **Hybrid fast-path.** Every parse tool starts
  a job; one that finishes inside a short grace window returns its results inline
  and is never polled. One mechanism, low friction preserved.
- Q: What does the ParserCore "version gate" actually test -- a version floor, or
  something else? -> A: **A capability probe, not a version number.** Same-install
  co-location plus reflective verification of the members we bind. The detected
  version is reported, never used to refuse; `required_version` is dropped.
- Q: What happens to the S9 split if flexicon declines the ParserCore dependency?
  -> A: **Not a negotiation -- the flexicon maintainer is this spec's maintainer,
  and wants it,** conditional on it not making flexicon unmaintainable. Ordering
  is **flexicon first, then the MCP**. The former open question is withdrawn.
- Q: What does a multi-hour parse job exclude, given a concurrent write would
  otherwise be filed against a grammar that no longer exists? -> A: **Not the
  project.** Editing the lexicon and user analyses during a parse is normal FLEx
  practice. Only writes to **parser-generated analyses** are excluded, a
  single-word parse **preempts** a background run (FLEx's own parser priority
  levels), and filing is guarded per result by `ParseResult.IsValid`.
  <br>**Footnote, added 2026-09-15 (not a retro-edit).** The answer above is
  recorded as it was given. Its *mechanism* has since been superseded:
  `ParserScheduler.cs:25-32` has five priority levels over one sorted queue with
  **no preemption of in-flight work and no `CancellationToken` anywhere**, so
  what a single-word request actually gets is an **interleave at the next word
  boundary**, not preemption. The user-visible guarantee (a single word is
  answered without waiting for a batch to finish) is unchanged; 5.6 carries the
  mechanism and governs.

### Session 2026-09-15 (second session -- try-a-word mechanics and steering)

- Q: What form does "guide the user to the most efficient parse" take? ->
  A: **A structured `next_step` on every parse response** (10.1), not prose and
  not a separate advisory tool. One of the steps it can propose is a
  **pathological-grammar investigation** (9.5): this feature diagnoses
  non-terminating parses itself rather than waiting on upstream tooling.
- Q: Who proposes the decomposition that mode A needs -- the MCP, the calling
  model, or the user? -> A: **The caller proposes, the MCP resolves, plus a cheap
  assist.** `next_step` names the decomposition as the missing input and points at
  the lexicon lookup; where an unambiguous candidate is already in hand the MCP
  pre-fills it, bounded and labelled a guess. No general segmenter is built (5.1.2).
- Q: Where does the static grammar scan live, given it is the cheapest instrument
  but the exported config belongs to the last checkpoint? -> A: **Pure-LCM scan in
  its own tool, landing early** (9.5.6) -- no export, no subprocess. It is
  *proposed* only when a parse that should have been quick was not, never
  routinely, and never when the session cannot run it.
- Q: Is a caller-supplied decomposition authoritative, or should the MCP push back
  when it looks wrong? (Volunteered by the maintainer, not asked.) -> A: **Trace it
  as given, but gently flag it.** A proposal can be imprecise, and an adjacent
  decomposition may fit better. Surface near-misses and conflicts with existing
  analyses as observations -- never refuse, never substitute, never score (5.1.3).
- Q: How do we reach a Morpher to build the per-morpheme postmortem, given
  `HCParser` exposes no seam? -> A: **Do not go that way.** Instrument 1 becomes
  the primary G4 instrument: take what PanGloss has identified as pathological
  for a compiled FST and detect the same properties **statically in the lexicon**.
  A `HCParser` seam is welcome if it is cheap, but nothing is planned around it,
  and **PanGloss is never a dependency** (9.5.6).
- Q: Which checkpoint owns `flextools_grammar_health`, given it needs no parser at
  all? -> A: **CP1.** It is the primary G4 instrument and the cheapest thing in the
  feature, and CP1 is the earliest checkpoint whose dependencies it already
  satisfies. This widens CP1's boundary from "no cache opened" to "no parser
  constructed" -- see 15.

---

## 2. Settled -- do not revisit

- **S1. Both one-shot parsing and before/after diffing ship.** Diffing is the
  reason the feature exists.
- **S2. (REVISED, 2026-09-15)** The custom interlinear-walk word-list builder is
  **retired**. LCM already owns it: `IStText.UniqueWordforms()` (`StText.cs:654-661`),
  which `ParserListener` unions across a genre (`:609-613`) and across all texts
  (`:650-654`). What survives is genre->text *selection* (section 6.1) and
  dedup/ordering/limit for the sandbox word list (section 6.2).
- **S3. The HermitCrab config is cached**, keyed on `.fwdata` identity plus
  generator identity. Applies to the **sandbox spine only** (section 7).
- **S4. PowerShell is the sandbox spine's mechanism.** Windows only.
- **S5. (REVISED, 2026-09-15)** "Parsing is read-only, always" is **dead** --
  spine 3 writes. Replaced by a per-mode statement:
  - `flextools_try_word` and `flextools_parse_sandbox` are `READ_ONLY_SAFE` **by
    construction**, not by convention (section 12.1).
  - `flextools_parse_text` is write-capable and sits behind the full ladder.
- **S6. Config generation runs on a copy** of the project, never the live `.fwdata`.
- **S7. Responses summarise; they never inline the full result set.** A parse of
  500 words with traces is hundreds of KB. Previews are capped and the detail is
  reachable through `flextools_parse_log`. This applies to every tool here.
- **S8. Depending on ParserCore is accepted.** It reaches beyond the pure-LCM
  layer the MCP has used until now; the maintainer has accepted that cost
  explicitly, because the alternative is a broken feedback loop. The dependency
  widens the **layer** we touch, not the deployment **footprint**: `ParserCore.dll`
  ships in `C:\Program Files\SIL\FieldWorks 9\`, the same directory
  `versioning.py:172` already searches for `SIL.LCModel.dll`. Consequences
  (version coupling, upgrade breakage) remain fair game; arguing the dependency
  away does not.
- **S9. Placement is split, and flexicon goes first** (decided 2026-09-15;
  ordering and acceptance confirmed by the flexicon maintainer, who is this
  spec's maintainer): a thin read-only `project.Parser` facade ships in
  **flexicon**; filing plus the confirmation/backup ladder stays in
  **FlexToolsMCP**. This is not a cross-repo negotiation and must not be planned
  as one. The single condition attached is **maintainability** -- the facade is
  wanted provided it does not make flexicon harder to maintain, which is what the
  two costs in section 5.4 exist to guarantee. **flexicon expands before the
  MCP consumes it.** See section 5.4.

---

## 3. Two correctness rules that outrank convenience

### 3.1 Never infer parseability from database state

`IWfiAnalysis` records are an artifact of work already performed -- parser runs
**and** human interlinearization -- not a statement about what the grammar
accepts. Therefore:

- A project never parsed live has no parser-created analyses, so **every wordform
  looks unparsed** while the grammar may accept all of it.
- A project with extensive hand-interlinearized analyses looks healthy and still
  says nothing about grammar coverage: those carry the *user* agent's opinion,
  not the parser agent's.

**G1 ("which words don't parse") is answerable only by running the parser, never
by querying analyses.** Any implementation that enumerates wordforms with zero
analyses and reports them as failures is WRONG.

This is stated as an anti-requirement because the wrong implementation is the
cheap one: querying the DB costs nothing, parsing costs real time, and an
implementer under pressure will reach for the query. Same register as section
8.4 -- a confident wrong answer about someone's grammar is worse than useless.

### 3.2 Never report the wrong engine's results as the project's

A project declares its own parser: `LanguageProject.MorphologicalDataOA.ActiveParser`
is `"XAmple"` or `"HC"`, and `ParserWorker.cs:65` throws on anything else. Every
parse tool reads it **first** and **refuses** -- never silently substitutes --
when the project is on XAmple and the tool implements HC.

Parsing with the wrong engine and reporting the results as the project's own is
the section-8.4 violation one layer up. Error code `parser_engine_mismatch`; a
one-field read, cheap enough to ship at CP1 regardless of whether XAmple support
ever lands.

---

## 4. Prior art: what `hcparse.ps1` got right

The contributed script encodes lessons the bundled version must preserve, and
this spec records *why* so a later refactor does not drop one.

| Behaviour | Why it is there |
|---|---|
| Copy the project before generating | A running FLEx holds `.fwdata` |
| `Get-Content -Encoding UTF8` | PS 5.1 defaults to the ANSI code page for a BOM-less file. Without this, any non-Latin word list becomes mojibake and HermitCrab reports "invalid segment at position 1" for **every** word -- a total failure that looks like a grammar problem |
| `UTF8Encoding($false)` writing the HC script | HC reads the script as UTF-8; a BOM corrupts the first command |
| Split `-Words` on `[,\s]+` | Under `powershell -File` a comma-separated list arrives as one string |

---

## 5. Architecture

### 5.1 Spine 1 -- in-process read (FLEx mode 2, and all discovery)

```python
parser = HCParser(project.Cache)     # HCParser.cs:50 -- takes ONLY a cache
parser.Update()                      # loads grammar + lexicon
result = parser.ParseWord(word)      # -> ParseResult (typed)
trace  = parser.TraceWordXml(word, None)   # -> XDocument (typed)
```

`HCParser`'s constructor takes no `PropertyTable`, no `IdleQueue`, no UI. Its
usings are `SIL.LCModel`, `SIL.LCModel.Infrastructure`, `SIL.Machine.*`,
`SIL.ObjectModel`. `ParserScheduler` and `ParserWorker` -- which *do* carry
framework coupling -- are FLEx's GUI-responsiveness machinery and are **not
used**; we drive parses synchronously.

`ParseResult` carries `Analyses` (`ReadOnlyCollection<ParseAnalysis>`),
`ErrorMessage`, `ParseTime`, and `IsValid`. **`IsValid` is an LCM object-liveness
guard, not a linguistic judgement** (`ParseResult.cs:199-202`) -- it contributes
nothing to G3 and must never be presented as a validity verdict. It has exactly
one correct use in this feature: the pre-filing object-liveness check of 12.6. Do
not let that dismissal read as "IsValid is unused" and get the check removed.

#### 5.1.1 "Try a word" is three modes, not one

FLEx mode 2 is itself a three-way choice, driven by two checkboxes in
`TryAWordDlg` -- `m_doTraceCheckBox` ("Let me see all the detailed steps the
parser tried (this may take a very long time in some instances)") and
`m_doSelectMorphsCheckBox` ("Let me break the word into its morphemes (this can
make it run faster)"), the second enabled only while the first is checked
(`TryAWordDlg.cs:602-648`). The three reachable configurations are not shades of
verbosity. They answer **different questions at different costs**, and the tool
exposes all three.

| Mode | FLEx UI | Call | Cost | Answers |
|---|---|---|---|---|
| **A. Selected morphs** | trace + "break the word into its morphemes" | `TraceWordXml(form, msaHvos)` | **fastest** | "Here is the decomposition I intended -- why is it not produced?" |
| **B. Results only** | neither box | `ParseWord(form)` / `ParseWordXml(form)` | medium | "What parses, if anything?" |
| **C. Full trace** | trace, no morph selection | `TraceWordXml(form, null)` | **slowest** | "Follow every path to the end, failures included -- where was my parse thrown out?" |

Mode A is the *fastest*, not merely the narrowest, and the reason is mechanical:
`selectTraceMorphs` is a **pre-parse filter** (`HCParser.cs:186-200`) that
installs `m_morpher.LexEntrySelector` and `RuleSelector` so the search never
leaves the morphemes the user named. The space collapses before any tracing cost
is paid. Mode C pays the opposite price -- full instrumentation over an unpruned
search -- which is what the checkbox's "very long time" warning is about.

**Mode C is the G2 answer of record; mode A is its cheap approximation.** A plain
failure (mode B) reports only that nothing parsed. *Why* the intended parse died
-- the environment that did not match, the slot already filled, the stratum that
ended the derivation -- exists only in a trace that follows failing paths to
completion. Wherever this spec says "trace the word to find out why", it means A
or C, never B.

**The cost ordering is a scheduling fact, not a footnote.** The right default for
a drill-down is A when the user has a hypothesis and C only when they do not; the
cap in 9.4 is a cap on **C**. Spending a mode-C budget on a word the user could
have segmented by hand is the most common way this feature will feel slow.

**Mode A's argument is MSA HVOs, not morph strings.** `selectTraceMorphs` is
`IEnumerable<int>` matched against `Morpheme.Properties["ID"]`
(`HCParser.cs:39, 189-196`). FLEx harvests them from the Try A Word sandbox,
where the user has already picked real lexical entries (`TryAWordRootSite.cs:311`,
`TryAWordDlg.cs:515-526`). Over MCP there is no sandbox, so `flextools_try_word`
accepts a decomposition the caller can actually write -- entry headwords, or
entry+sense, or MSA HVOs directly -- and resolves it to MSA HVOs itself. **That
resolver is net-new work.** `HCParser` does not do it for us, and a caller
guessing HVOs is not a design.

**A morph that resolves to no MSA is not a usable selection.** FLEx refuses the
run outright when any selected HVO is `0` (`TryAWordDlg.cs:519-524`) rather than
quietly parsing something adjacent. Mirror that exactly: return
`parse_morph_unresolved` naming the offending morph and its candidates. A
silently-degraded mode A is worse than a failure, because its empty result reads
as "your grammar rejects this analysis" when the truth is "we never tested the
analysis you asked for" -- a fabricated verdict of the kind 8.4 forbids.

#### 5.1.2 Who proposes the decomposition

Mode A is the cheap rung and it is unreachable without a decomposition, so the
question of who supplies one decides whether the ladder of 8.2 is usable at all.

**The caller proposes; the MCP resolves.** The resolver of 5.1.1 -- headwords or
entry+sense or MSA HVOs in, MSA HVOs out, `parse_morph_unresolved` on failure --
is the MCP's whole responsibility here. The proposal itself belongs to the caller,
because a calling model has what the MCP does not: the glosses, the surrounding
text, and the user's actual hypothesis.

**Plus a cheap assist, so the hand-off is not a dead end.** A `next_step` that
merely says "supply a decomposition" has taught the caller nothing. So:

- `next_step` names the decomposition as the **missing input** and states what a
  usable one looks like. It **cannot** point at a lexicon-query tool, because
  there is none: all 21 existing MCP tools are API-discovery, codegen or admin,
  and the only path to lexicon data is `flextools_run_module` executing Python
  with `project` in scope (`dispatch.py:84-106`, `tool_definitions.py:244`). Any
  "look it up" step is therefore a `run_module` snippet, not a tool call --
  verified 2026-09-15, and a constraint on every `next_step` this feature emits.
- Where the MCP already holds an unambiguous candidate -- a single entry per morph
  with no competing allomorph -- it **pre-fills** `args.morphs`. Bounded (never
  more than a handful), and always labelled a guess. The parse tools already hold
  the cache (`HCParser(project.Cache)`), so the assist runs in-process; it does
  not need a lexicon tool to exist.
- A pre-filled candidate is a starting point, never an analysis. Rendering it as
  what the word *means* would be the 8.4 violation in miniature. Label it
  **"proposed, unverified"**: a lexicon string match is not a parse, knows nothing
  about phonological rules or environments, and must never be mistaken for output
  of the HermitCrab path this spec exists to drive.

**What already exists, and what does not** (verified in flexicon, 2026-09-15):

- The retrieval half is largely done. `AllomorphOperations.GetAll(entry_or_hvo=None)`
  (`AllomorphOperations.py:104`) enumerates **every allomorph in the project** with
  `.form`, `.is_stem_allomorph` / `.is_affix_allomorph` and `.environment`;
  `LexEntryOperations.GetAllByMorphType` (`:1657`) and `GetAvailableMorphTypes`
  (`:1552`) give the stem/affix partition per project.
- **No segmentation logic exists anywhere** in flexicon or the MCP. The
  `WfiMorphBundle` readers return a decomposition FLEx already stored; none
  computes one. The matcher is genuinely net-new -- though small, on the order of
  a form -> (entry, morph type) dictionary plus a bounded left-to-right match.
- **Two flexicon read gaps sit directly on mode A's path.** There is no
  `GetOwningEntry` for an allomorph (it exists for Etymology, Sense, Pronunciation
  and Variant, but not allomorphs), and `MSAOperations` **exposes no read surface
  at all** -- its own stub says so (`MSAOperations.pyi:14-20`), so the MSA must be
  reached through raw LCM `sense.MorphoSyntaxAnalysisRA`. Since 5.1.1's resolver
  must end at **MSA HVOs**, this is on the critical path, not adjacent to it. Both
  belong in the S9 flexicon change alongside `Texts.GetGenres()` (5.4).
- **Every existing lookup is an unindexed linear scan**, and `LexEntryOperations.Find`
  (`:759`) is exact, case-sensitive, lexeme-form-only and returns the **first**
  match -- unusable for a candidate generator, which needs all homographs. Build
  the form -> morph index **once per run** and reuse it; a project-wide allomorph
  pass per word is the obvious way to make this feature feel slow.

**Anti-requirement: do not build a general segmenter in the MCP.** Splitting an
arbitrary wordform against every allomorph in a large lexicon is combinatorial --
it is the same path multiplication 9.5.1 exists to diagnose, reintroduced in the
tool meant to diagnose it. The assist is opportunistic and bounded by
construction; if a candidate is not already obvious, say so and hand the question
back rather than searching for one.

#### 5.1.3 When the proposed decomposition looks wrong

A decomposition is a hypothesis, and a hypothesis can be imprecise. A caller may
name a morph boundary slightly off, reach for a homograph, or pick one allomorph
where a sibling fits the surface better. The tool must not treat the proposal as
beyond question -- but neither may it overrule one.

**Always trace what was asked.** Mode A runs the decomposition as given, every
time. 5.1.1 already forbids handing back an unrestricted search under a
restricted label; substituting a *different* restriction is the same violation
with extra confidence. The flag rides **alongside** the result, never in place of
it.

**Two things are worth surfacing**, and only these:

- **An adjacent candidate.** The proposal differs minimally from one that is
  better supported -- a different allomorph of the same entry, a homograph, a
  boundary shifted by one morph. Report it, and let `next_step` (10.1) offer it as
  an additional mode-A run with `args` already filled. Adjacency is the useful
  signal precisely because it is cheap to check and cheap to act on.
- **A conflict with standing evidence.** The proposal contradicts the complete
  (tier 3, 9.3.1) analyses already recorded for this wordform, or shares no entry
  with any analysis of related words. "Vastly different from, or opposed to, what
  is already there" is the case worth naming.

**Silence on agreement.** When a proposal is consistent with the evidence, say
nothing. A tool that congratulates the caller on every correct guess teaches them
to skim the field where the real warnings live.

**The 9.3.2 asymmetry governs here too, and this is the part most likely to be
implemented wrong.** A proposal that diverges sharply from every recorded analysis
may be *the correct analysis of an irregular word* -- that is exactly when a
linguist reaches for Try A Word. So:

- Flag divergence as an **observation**, never a verdict: "this shares no entry
  with the three analyses already recorded for this word" is reportable; "this
  looks incorrect" is not.
- **Never demote, refuse, reorder, or score.** No confidence number on a user's
  hypothesis. Ranking proposals by agreement with existing analyses would
  systematically penalise the irregular words this rung exists to investigate --
  the same inversion 9.3.2 rejects for gloss distance.
- Never let the flag change what is traced, or what the trace is labelled.

The wording of 8.4 applies unchanged: report what was measured -- which entries
were shared, which were not -- and leave the judgement to the linguist.

### 5.2 Spine 2 -- in-process write (FLEx mode 1, and 3b)

`ParseFiler.ProcessParse(IWfiWordform, ParserPriority, ParseResult, bool)` --
FLEx's own filer, reached by the identical chain as the FLEx menu
(`ParserListener` -> `ParserConnection` -> `Scheduler` -> `Worker` -> `ParseFiler`),
so filed analyses carry honest parser-agent provenance.

Headless construction is **stubbed, not native**: `propertyTable` may be null,
`taskUpdateHandler` may be a no-op, and `idleQueue`'s deferred `UpdateWordforms`
is essential to a correct write but a headless caller invokes it **synchronously**
instead of through a real `IdleQueue`.

> Implementation note: supply a real stub `IdleQueue`, never a literal `null`.
> A `Debug.Assert(idleQueue != null)` exists but is elided in the shipped release
> build, so `null` would appear to work. Do not build on assert elision, and do
> not let a later cleanup "simplify" the stub away.

### 5.3 Spine 3 -- the sandbox (FLEx mode 3a)

Export a config, optionally hand-edit it, run the `hc` CLI against it. Bundled at
`src/flextoolsmcp/scripts/hcparse.ps1`, invoked as:

```
powershell -NoProfile -NonInteractive -ExecutionPolicy Bypass -File <hcparse.ps1> ...
```

`-NoProfile` is not optional: a profile that prints a banner lands in stdout and
corrupts output parsing.

The sandbox is genuinely usable, not merely isolated. `HermitCrabInput.dtd` is
618 lines of DTD-documented XML whose elements are the linguist's own vocabulary
-- `PhonologicalRule`, `PhoneticInput`, `LeftEnvironment`, `RightEnvironment`,
`NaturalClasses`, `SegmentNaturalClass`, `SegmentDefinition`, `StemName`,
`PartOfSpeech`. "Tighten the environment on this rule" is editing
`<LeftEnvironment>` inside a `<PhonologicalRule>`.

### 5.4 Where the code lives (S9)

- **flexicon** gets a thin read-only `project.Parser` facade wrapping
  `HCParser(cache)` -- names to flexicon's own verb conventions. Rationale: the
  MCP exists to generate FLExTools modules, and every generated module imports
  `from flexicon import (...)`. Parser access living only in MCP server code is
  unreachable from the artifact this project exists to produce.
- **FlexToolsMCP** keeps filing, the confirmation/backup ladder, and all
  gradient orchestration (diff, sandbox export, caching, run artifacts). The
  write path needs stubs and sits on a non-undoable UOW that can delete data --
  "run a vetted, gated procedure with irreversible side effects" is what the
  MCP's ladder already owns; flexicon has no such ladder.

The facade was accepted on one condition -- that it not make flexicon harder to
maintain. The two costs below are therefore not merely risks to watch; they are
the terms of that acceptance, and failing either is grounds to keep the facade
out of flexicon rather than to ship it degraded:

- **Import must be lazy.** A future FieldWorks that renames or relocates
  `ParserCore.dll` must degrade to "parser unavailable", never break
  `import flexicon` for users of unrelated features.
- **The gate follows the code, and it is a capability probe -- not a version
  number.** ParserCore is versioned independently of `SIL.LCModel`, and needs its
  own gate in flexicon as well as the MCP. But a version *floor* is the wrong
  instrument: the MCP's index is liblcm `v11.0.0` while the install is
  FieldWorks 9, nothing may assume those numbers track each other, and no
  evidence in this spec establishes which ParserCore build is the earliest
  workable one. A floor invented without that evidence refuses installs that work.

  The gate is therefore two checks, neither of which reads a version:

  1. **Same install.** `ParserCore.dll` must come from the same FieldWorks
     directory that supplied the `SIL.LCModel.dll` already resolved by
     `versioning.py:172`. A ParserCore from a *different* install is refused --
     mixing two FieldWorks versions across an in-process boundary is the failure
     no version floor would have caught anyway. The shared accessor is
     `get_resolved_fieldworks_dir()` (a thin wrapper over
     `locate_liblcm_dll().parent` in `versioning.py`), used by both
     `_build_fieldworks_block()` and the parser probe; it recomputes per call
     and retains no binding across calls -- `locate_liblcm_dll()` itself is
     pure, with no module-level memoization, so recomputation is correct and
     cheap (filesystem checks only).
  2. **The surface we bind exists.** Reflect over exactly the members this
     feature calls and refuse if any is absent:
     `HCParser(LcmCache)` (`HCParser.cs:50`), `Update()` (`:67`),
     `ParseWord(string) -> ParseResult` (`:84`),
     `TraceWordXml(string, IEnumerable<int>) -> XDocument` (`:120`),
     `ParseWordXml(string) -> XDocument` (`:127`), and -- for spine 2 only --
     `ParseFiler.ProcessParse(...)`. **Bind positionally, not by keyword:**
     `IParser` names these parameters `word` while `HCParser` implements them as
     `form` (`IParser.cs:23,25`), so keyword binding through pythonnet breaks on
     the interface/impl mismatch. The binding surface is small enough to
     enumerate, which is precisely why probing it is cheaper and truer than
     guessing a version.

  The detected version is **reported** in health output and run artifacts -- it is
  the first thing worth knowing in a bug report -- but it never decides. This
  probe loads `ParserCore.dll` into the process via reflection (the same
  `Assembly.LoadFile` + `GetMethods` pattern `liblcm_extractor.py:332` already
  uses for `SIL.LCModel.dll`) and inspects its members; it never opens an
  `LcmCache`, loads a grammar, or parses a word, so the probe stays inside CP1's
  "no parsing" boundary. Because a CLR load runs static initializers and
  resolves manifest-referenced dependencies, it is heavier than a
  file-existence check -- that cost is gated behind `verbose=True` or memoized
  at the call site, a call-site decision rather than a lazy-import violation;
  the laziness condition above survives because the load is call-triggered, not
  import-triggered. A mismatched transitive dependency can throw during load
  before any member is inspected; that throw is caught and mapped to
  `parser_core_missing` with signal `load_failed`.
- **MCP-side placement.** The detectors that back `flextools_health`'s parser
  block (10.2) -- the same-install check, the member probe, `hc` and
  `GenerateHCConfig.exe` detection -- live in a **new** module
  `src\flextoolsmcp\server\parser_probe.py`, imported by `diagnostic_health.py`
  the same way `versioning.py` and `project_access.py` already are. This is
  distinct from the flexicon facade above: `diagnostic_health.py`'s docstring
  ("pure composition, no new detection logic") is a contract other code and
  tests rely on, so detection logic does not move into that module.
- Companion asks in the same flexicon change, all currently raw-LCM-only:
  a `Texts.GetGenres()` wrapper (`IText.GenresRC`, section 6.1); an
  allomorph -> owning-entry accessor (`GetOwningEntry` exists for Etymology,
  Sense, Pronunciation and Variant but not allomorphs); and an **MSA read
  surface** -- `MSAOperations` exposes none at all (`MSAOperations.pyi:14-20`),
  yet 5.1.1's resolver must terminate in MSA HVOs. The MSA gap is on mode A's
  critical path (5.1.2).

**Build order.** The flexicon facade lands first and the MCP consumes it; the MCP
does not grow a temporary parser path of its own to be retired later. Section 15
sequences this at CP2.

### 5.5 Run artifacts

```
~/.flextoolsmcp/parse/
  config-cache/<project>/<cache_key>/{hc-config.xml, key.json}   # managed, invalidatable
  sandboxes/<project>/<name>/hc-config.xml                        # USER-OWNED, never touched
  runs/<project>/<run_id>/
      run.json  words.txt  hc-script.txt  hc-output.txt
      hc-stdout.txt  generate-config.log  trace.txt
```

`run_id` is `<UTC yyyymmddTHHMMSSZ>-<8 hex>`. Retention: newest 20 runs per
project (mirrors `backup.py::_prune_old_backups`).

**Prior art inside FieldWorks.** `Src\LexText\ParserCore\ParserReport.cs`
already defines a parser run report -- `NumWords`, `NumParseErrors`,
`NumZeroParses`, `TotalParseTime`, `TotalAnalyses`, plus
`TotalUserApprovedAnalysesMissing`, `TotalUserDisapprovedAnalyses` and
`TotalUserNoOpinionAnalyses` (`:51-86`), accumulated per word (`:317-359`). The
last three overlap the oracle of 9.3 directly. Align `run.json`'s field names and
semantics with it where they coincide rather than inventing parallel ones, and
where we deliberately differ -- the tiering of 9.3.1 has no counterpart there --
say so. Note its counters are per word; nothing in it is per rule or per morpheme.

`run.json` is the job's durable state, not only its summary: it carries the
current state, `words_completed` / `words_total`, `engine_at_submission` (5.6),
and on a terminal failure the reason. It is written incrementally so a job that
dies mid-run still describes itself (5.6).

### 5.6 Execution model -- a parse is a job, not a call

Parses are **started and polled**, never awaited inside a single tool call. Two
facts force this, and both are ordinary rather than exceptional:

- **Duration.** A full-corpus parse is an hours-long operation, not merely a slow
  one. No call timeout can be set high enough to cover it without also hiding a
  genuine hang.
- **Mortality.** The parser can exhaust RAM and die mid-run. A blocking call has
  no honest way to report "the grammar loaded, 4,000 words parsed, then the
  process died" -- it can only time out or raise, discarding the work.

So a parse tool returns a `run_id` immediately, and
`flextools_parse_status(run_id)` reports progress and terminal state. Results
accumulate in the run artifact (5.5) as they are produced, so a job that dies at
word 4,000 leaves 4,000 usable results beside a terminal state naming the
failure. `words_completed` on `parser_timeout` (section 14) is the same
commitment seen from the failure side: partial work is preserved and reportable,
never discarded.

**The fast path is part of the contract, not an optimisation.** A job that
reaches a terminal state inside a short grace window (default 5s, configurable)
returns its results *inline*, and the caller never polls. Only a job still
running when the window closes returns a bare `run_id`. This keeps one set of job
machinery -- there is no second, synchronous code path to drift out of sync --
while leaving the hypothesis-testing loop of section 12.1 as cheap as it must be
to stay useful. A single-word probe against a loaded grammar answers inline; the
same call against a cold grammar or a runaway search degrades to a `run_id`
instead of pretending to hang.

The window governs *reporting*, never execution: it is not a timeout, and closing
it neither cancels nor throttles the job.

States: `starting | loading_grammar | parsing | filing | completed | failed |
cancelled`.

A terminal `failed` state carries a `next_step` (10.1) pointing at the G4
instruments of 9.5.2 -- a run that died of memory exhaustion is the single case
where the user most needs to be handed a diagnosis rather than a retry.

`loading_grammar` is a state of its own for two reasons. It is the step that most
often exhausts memory, so attributing a death to it is diagnostic rather than
cosmetic; and on a large project it dominates the run before a single word is
parsed, so a caller shown only "running" concludes the tool is hung.

**Jobs are prioritised, and a single word interleaves ahead of a batch at the
next word boundary -- FLEx does not preempt, and neither do we.** A background
corpus run must never make the hypothesis-testing loop wait hours for an answer.
FLEx's own scheduler achieves this by queue-jump, not preemption:
`ConsumerThread.WorkLoop` (`ConsumerThread.cs:434-453`) calls the handler and
only re-checks the queue after it returns -- there is no cancel, abort or
interrupt of in-flight work anywhere in the scheduler, worker or parser path.
What makes interleaving possible at all is the per-wordform enqueue granularity
(below), not preemption. Because we drive parses ourselves (5.1) rather than
through `ParserScheduler`, we own the queue and must reproduce FLEx's actual
queue-jump behaviour, not an idealised preemptive one.

A high-priority single-word request interleaves at the running batch's next word
boundary: the batch does not restart, does not lose position, and the grammar
stays loaded once for both. The batch's reported progress must account for the
interleave rather than appearing to stall.

**Verified** (`ParserScheduler.cs:25-32`) -- mirror these names and this ordering:

```csharp
ReloadGrammarAndLexicon = 0, TryAWord = 1, High = 2, Medium = 3, Low = 4
```

**Lower value wins.** Five levels, not three: `High`/`Medium`/`Low` are the three
the UI exposes -- single wordform is `High` (`ParserListener.cs:145`), one text or
genre `Medium` (`:529`), **All Texts** `Low` (`:655`) -- with `TryAWord` above all
three and grammar reload above everything.

FLEx implements this as **one sorted queue, not several**: a
`ConsumerThread<ParserPriority, ParserWork>` over a `PriorityQueue` backed by a
`SortedDictionary`, dequeuing the lowest enum value first, FIFO within a level.
"Parse all texts" enqueues one work item **per wordform**, which is what makes
interleaving possible at all -- FLEx's priority is queue-jump, not preemption.

> **Mechanism, for precision.** `ConsumerThread.Stop()` documents that in-flight
> work runs to completion; a `TryAWord` jumps ahead of **queued** items only,
> waiting for the single wordform currently being parsed. That is exactly the
> word-boundary interleave specified above, so our model matches FLEx's
> *committed* behaviour.
>
> Note for whoever builds this: the local FieldWorks working tree carries an
> **uncommitted** change (`ParserScheduler.cs:265-296`) in which `Work()` drains
> the **whole** queue into a batch and runs it under `Parallel.ForEach`, losing
> priority ordering inside a drained batch. This does not bind us -- we own our
> own queue and do not use `ParserScheduler` -- but it means we must never argue
> "FLEx guarantees this ordering" as our correctness rationale. **Our guarantee
> is our own.** If that change lands upstream it would be a further regression
> from FLEx's already-non-preemptive committed behaviour, and our own runner
> must not copy it.

**`ActiveParser` is re-read live on every call, never cached per session.** It is
user-flippable mid-session via Words > Parser > Choose Parser
(`ParserListener.cs:1117-1133` `OnChooseParser`, wired at
`areaConfiguration.xml:26-31`), so nothing may bind it once at project-open.
Accepted values are exactly `"XAmple"` and `"HC"`, case-sensitive
(`ParserWorker.cs:65-77`); the getter defaults to `"XAmple"` on any
`ParserParameters` XML parse failure (`OverridesLing_MoClasses.cs:4213`), so a
corrupt value reads as XAmple and we refuse with `parser_engine_mismatch` --
fail-safe, never silently HC. For a batch job (`flextools_parse_text`) the check
fires once, at submission: `engine_at_submission` is recorded in `run.json`
(5.5). If `ActiveParser` differs at completion, the run summary reports the
divergence as a **warning**, not a refusal -- the results are internally
consistent and were filed under the agent GUID chosen at submission, and 3.2's
rule is a labelling rule, which labelling satisfies.

**A job must be cancellable.** An hours-long operation that can consume all
available memory and cannot be stopped is not an acceptable surface. Cancellation
is cooperative -- it stops at the next word boundary and leaves a `cancelled`
terminal state over the partial results, exactly as a failure would.

This is **new infrastructure**: the MCP has no job runner today. `start_module`
is an interactive wizard, not an async runner, and `subprocess_helpers` is
blocking-with-timeout. The runner lands with the first tool that needs it
(section 15).

---

## 6. Scope resolution (what survives of old section 6)

For spines 1 and 2, the parse target list comes from LCM:
`IStText.UniqueWordforms()`, unioned across a genre or across all texts exactly
as `ParserListener` does. We do not build our own walk.

### 6.1 Genre -> text selection

We still map a user-supplied genre string onto texts. `TextOperations.GetGenre`
returns only the **first** genre, so a text tagged `[Narrative, Folklore]` scoped
by `"Folklore"` would be missed. Genre selection must read the full reference
collection `IText.GenresRC`.

**`GenresRC` is reachable through no flexicon wrapper** -- this is raw-LCM
access, one of the few places this feature drops beneath flexicon. If the
flexicon-side facade lands (S9), a `Texts.GetGenres()` wrapper is the natural
companion.

Matching is case-insensitive against genre name and abbreviation in the default
analysis writing system. More than one match is `parse_scope_ambiguous`.

### 6.2 Word lists for the sandbox spine

The CLI genuinely needs a word-list file. Dedup (NFC-normalized), order by
descending occurrence count then alphabetically, truncate by `limit` *after*
ordering, and record `truncated_by_limit`.

---

## 7. Config cache and three lifecycles

The cache applies to the **sandbox spine only**. Spines 1 and 2 read the live
grammar through `HCParser.Update()`.

### 7.1 Three lifecycles -- do not conflate them

| Artifact | Lifecycle |
|---|---|
| The copied project | **Always deleted.** Confirmed leak today: `hcparse.ps1` cleans `$script` and `$out` but never removes `$work`, so a full project copy accumulates in `%TEMP%` indefinitely |
| The generated config (cache) | Cache-managed, invalidatable, pruned |
| A **user-owned sandbox config** | Keepable, hand-edited, **never** overwritten or invalidated by cache logic |

H6 and H10 pull in opposite directions and must be written as three named
lifecycles, or an implementer will conflate the copy with the config.

### 7.2 Cache key and invalidation

```
cache_key = sha256(fwdata_abspath, fwdata_size, fwdata_mtime_ns,
                   generate_config_exe_path + size + mtime,
                   hcparse_ps1_version_constant)
```

Retention 3 per project, LRU. Invalidate explicitly whenever a write run
completes against the project -- including **spine-2 parser writes**, not just
`run_module` writes.

### 7.3 The shared-mode caveat -- re-scoped, not deleted

Per the confirmed issue #96 root cause: when FLEx holds a project in shared mode,
a peer's commit lands only in the in-memory shared commit log, `.fwdata` advances
only when the master writes, and a fresh open never replays commit-log records.

- For the **sandbox spine** the export step reads `.fwdata`, so mtime/size can be
  unchanged while the grammar has changed. The cache key is structurally
  incapable of noticing, and rebuilding does not help.
- For **spines 1 and 2** the staleness takes a different form: the live cache is
  authoritative for the session that holds it, but a peer's edits are not visible.

When `project_access` reports `shared` or `held_by_other`, set
`staleness: "shared_mode_unverifiable"`, carry a note telling the user to save or
close FLEx, and downgrade a diff's `no_change` to `no_change_unverifiable`.

**Never promise a safe read-back interval.** There is no N that is safe.

---

## 8. Diagnosis: G1 (which words fail) and G2 (why)

### 8.1 Two taxonomies, not one

**In-process:** `ParseResult.ErrorMessage` plus the trace XML. Rule attribution
and the 23-value `FailureReason` vocabulary live inside `<Trace>`.

**Sandbox/CLI:** three top-level outcomes only. `No valid parses.` **conflates**
no-parse with no-lexical-entry; `invalid segment at position N`; success. The
richer `FailureReason` values appear only inside traces.

Do not pretend these are one taxonomy. A CLI run genuinely cannot distinguish
"root not in the lexicon" from "no rule produced a parse".

### 8.2 Tracing

In-process `TraceWordXml` is per-word by design, so tracing is **on demand**:
parse the batch untraced (mode B), then trace the specific words the user drills
into. The old "two-pass trace" design was an artifact of the CLI spine and
applies only there.

Drill-down is not one operation but the ladder of 5.1.1, and G2 climbs it in
order:

1. **Mode B** established *that* the word fails. It cannot say why.
2. **Mode A** -- if the user (or the model, from the lexicon -- see 5.1.2 for who
   proposes and what the MCP contributes) can propose a decomposition, trace only
   that. Cheapest, and it answers the question actually
   being asked: "why was *my* parse excluded?" The trace shows exactly where the
   named morphemes stopped composing.
3. **Mode C** -- only when no hypothesis exists, or when mode A's restricted
   search terminates for a reason outside the selected morphs.

Two consequences for the report. A mode-A trace is **evidence about the proposed
decomposition only**; it is silent on every analysis it filtered away, and must be
labelled as such rather than read as "the parser found nothing". And a mode-A
trace that succeeds where the unrestricted parse failed is itself a finding --
the morphemes compose fine, so the blocker is something the pruned search removed
(a competing entry, a rule ordering), and mode C is now warranted.

Caps (section 9.4) apply to all three, and the expensive cap is mode C's.

Each rung's response names the next one through `next_step` (10.1) with its
`est_cost`, so the ladder is climbed deliberately rather than by guessing. Where
mode C would be the next rung on an unscreened grammar, the static scan of 9.5.2
is proposed **first** -- it is cheaper than the trace it might make unnecessary.

### 8.3 Reading the logs

`flextools_parse_log(run_id, section, word, filter, lines, offset)` with sections
`summary | config_generation | hc_stdout | hc_output | trace | words | results`.

`section="config_generation"` answers the most common sandbox failure -- config
generation produced nothing, so every word "fails". The current script discards
exactly that output via `| Out-Null`.

### 8.4 Never fabricate an explanation

Where a trace is parseable, name the blocking rule or stage in one line. Where it
is not, return the raw slice **and say it is raw**. Fabricating a linguistic
explanation from an unrecognized trace would be a confident wrong answer about
someone's grammar -- worse than useless. This principle is load-bearing and is
referenced by sections 3.1, 3.2 and 9.

---

## 9. G3: overgeneration (why too many / invalid parses are allowed)

Two layers, because rule attribution is inherently per-word.

### 9.1 Batch layer (cheap, whole-run, no tracing)

Computed from typed `ParseMorph` data. Each signal ships with its false-positive
mode stated in the output -- **legitimate ambiguity is normal in many languages
and a high count is not a bug**:

| Signal | What it tells a linguist | False positive |
|---|---|---|
| Analysis count per word | Worklist prioritizer, never a verdict | Real productive ambiguity |
| Root-entry disagreement | One surface derived from two unrelated headwords -- often a spurious affix rule exposing a different root | Genuine root homographs |
| Root analysed as affix stack | A rule loose enough to synthesize a word from affixes alone | Real zero-derivation / cliticization |
| Same surface, incompatible MSA/category | Grammar treats one form as two unrelated categories with no derivation licensing the jump | Genuine cross-category homographs |
| Count-distribution histogram | Re-run after an edit and diff it; a rightward shift is evidence something got looser | -- |

### 9.2 Drill-down layer (per word, `TraceWordXml`)

The trace records the **entire search**, not just the winner. For each accepted
analysis the `MorphologicalRuleApplied` / `LexEntry` sequence gives the rule
chain: `entry -> rule1 (stratum, slot) -> rule2 -> ... -> surface`.

**The attribution method:** compare the chains of a word's N analyses
side-by-side; the rule appearing in every "should not have parsed" chain is the
overgeneration candidate.

Note for implementers: this side-by-side comparison **does not exist yet**. It is
net-new build, not presentation of something `TraceWordXml` already returns.

`selectTraceMorphs` (mode A, 5.1.1) is a **pre-parse filter**
(`HCParser.cs:186-200`) restricting the search space before parsing. It does
**not** attribute an already-produced analysis to a rule; do not design against
it as if it did. The scope of that caveat is G3 attribution specifically -- mode
A remains the cheapest and most direct instrument for G2, where the question is
about one named decomposition rather than about which rule licensed six.

It has one genuine G3 use, by subtraction: re-run a suspect analysis with its own
morphs selected, and the chain that survives is that analysis's derivation in
isolation, uncontaminated by the other N-1. That narrows the candidate set. It
still does not name the rule, which is what the side-by-side comparison above is
for.

### 9.3 The oracle, and its mandatory wording

The project's human-approved analyses are a real but partial gold standard. It is
sound only where the exact morph-bundle signature already exists as an
`IWfiAnalysis`; for an analysis never materialized in the DB there is simply no
row to query.

It is weak in **two independent ways**, and both apply before any approval count
is reported:

1. **Completeness** (9.3.1) -- an approved record may carry meaning without
   morphology, so there is nothing to compare the parser against.
2. **Provenance** (9.3.4) -- most approvals are **tacit**, not affirmed. A
   person used the analysis in a text and never clicked the approve check;
   `ParseFiler` records approval on their behalf. Tacit and affirmed approvals
   are stored identically and **cannot be reliably told apart**.

The second is the stronger caveat. It does not thin the oracle; it changes what
a stored opinion *means*, and it is orthogonal to the tiering -- a record can
pass tier 3 on content while carrying an opinion no human ever formed.

#### 9.3.1 Human approval is not one thing -- tier it before comparing

A human "approved analysis" may record **what a word means** without recording
**how it decomposes**. FLEx's Gloss interlinear mode exists precisely to capture
that: a word gloss and category, no morphology. Treating such a record as a
morphological gold standard is a category error, not merely thin evidence.

This is mechanically decisive, not a matter of taste. `MatchesIWfiAnalysis`
(`ParseResult.cs:110-118`) requires
`analysis.MorphBundlesOS.Count == this.Morphs.Count` and then
`mb.MorphRA == current.Form && mb.MsaRA == current.Msa`. Therefore:

- A **gloss-only** analysis has `MorphBundlesOS.Count == 0`, so it can match only
  a parser result with zero morphs -- i.e. **never**.
- A **sketched** bundle carrying a text `Form` but a null `MorphRA`/`MsaRA` fails
  the identity comparison -- also **never**.

Incomplete human records are thus *invisible* to the comparison. Counting them as
"the human approved 0 of the parser's 6" is wrong: the human expressed an
intention the parser's output cannot be measured against.

**LCM already defines the distinction -- use it rather than inventing one.**
`IWfiMorphBundle.IsComplete` (`OverridesLing_Wfi.cs:861-868`) is
`SenseRA != null && MsaRA != null && MorphRA != null && <all analysis-WS glosses
non-empty> && MorphRA.IsComplete`, and `WfiAnalysis.IsFullyFormed` (`:1160-1175`)
requires a category, at least one complete gloss, **morph bundles that are all
complete**, a human opinion, and no conflicting evaluations.

> Reachability note: `IsFullyFormed` is `internal` and therefore NOT callable
> from pythonnet. `IWfiAnalysis.IsComplete` and `IWfiMorphBundle.IsComplete` are
> public on the interfaces, so compute the tier from `MorphBundlesOS.Count` plus
> each bundle's `IsComplete`. Do not reimplement SIL's completeness predicate.

| Tier | State | Usable as a morphological oracle? |
|---|---|---|
| 0 | No analysis at all | No -- nothing recorded |
| 1 | Category and/or gloss, `MorphBundlesOS.Count == 0` (Gloss-mode work) | **No** -- meaning recorded, decomposition not |
| 2 | Bundles present, some with null `MorphRA`/`MsaRA`/`SenseRA` | **No** -- morphology sketched, not linked |
| 3 | Bundles present and all `IsComplete` | **Yes** -- comparable to parser output |

Only tier 3 enters the "human approved N of the parser's M" statement. Tiers 1
and 2 are reported **separately and by name**, never folded into a count and
never silently dropped -- they are the user's recorded intent and are often the
most interesting rows on the page, because they say "a human believes this word
means X and has not yet said how it gets there."

Corollary for section 12.2: tier-1 and tier-2 records carry a **user-agent**
opinion, so `SetUnsuccessfulParseEvals` will not delete them. They are safe from
the P0 deletion path. Say so when reporting them, so a user does not fear that
running a parse will discard their glossing work.

That shield is narrower than the one 9.3.4 describes, and the two must not be
conflated: tiers 1 and 2 are safe because a human really did record them,
whereas in-segment analyses are safe because `ParseFiler` approves them *on the
user's behalf*. Both end at the same delete check, from opposite directions.

#### 9.3.2 Incomplete records are useful evidence, of a different kind

Tiers 1 and 2 are excluded from the morphological count (9.3.1). They are **not**
excluded from the analysis. They answer a different question, and that makes them
complementary rather than weak:

> The human supplies the **what** (this word means X). The parser supplies the
> **how** (this word decomposes as Y). The parser does not attempt word-level
> semantics at all, so the two never contradict each other -- they compose.

**The 1:1 case is the strong one.** When the parser produces exactly one full
analysis and the human recorded exactly one word gloss, it is statistically
likely they belong together: the parser's morphology is the missing "how" for the
human's recorded "what". Surface that as a **candidate pairing**, ranked highest
in the report, with wording that makes the inference visible rather than implied:
`"One parser analysis, one human gloss -- these probably describe the same word.
The parser's decomposition may be the morphology this gloss is missing."`

**The 1:N case is a disambiguation signal, and this is where G3 gains a new
input.** A parser analysis implies a *composed* gloss: each `IWfiMorphBundle`
carries `SenseRA` (`ILexSense`), which carries its own gloss. Compare the
composed gloss -- the stem sense above all -- against the human's `IWfiGloss.Form`.
When the human glossed a word "read" and one analysis roots it in a sense glossed
"read" while another roots it in "tie", that is genuine evidence about which
proposal is spurious.

**The signal is ASYMMETRIC, and implementing it symmetrically would be worse
than not implementing it.** Morphology is not reliably compositional: adding a
morpheme can produce something greater than the sum of its parts -- a lexicalized
derivation, an idiom, ordinary semantic drift. English `understand` is not
`under` + `stand`. Therefore:

- **Agreement promotes.** A composed gloss matching the human's word gloss is
  decent evidence the analysis is right: it is both morphologically available and
  semantically consistent.
- **Disagreement must NOT demote.** A mismatch is ambiguous between "wrong
  analysis" and "correct analysis of a non-compositional word". Ranking on
  mismatch would systematically penalise the *correct* analysis of exactly the
  words where morphology is most interesting.

So the ranking is a **promotion-only** ordering: matching analyses rise, and
everything else keeps its original order rather than being pushed down. Never
render an unmatched analysis as less likely.

**Persistent disagreement is a finding, not noise.** A word whose best-supported
analysis has a composed gloss far from the human's recorded meaning is a
candidate **lexicalized form** -- precisely the case a lexical entry, or a sense
on a complex form, exists to record, because its meaning is not predictable from
its parts. Report it as such:
`"The parser can derive this word, but its parts do not add up to the recorded
meaning. That may indicate a lexicalized form that deserves its own entry or
sense, rather than a parsing error."`
That reading is often more valuable to a linguist than the parse itself.

This matters because it partly answers the gap in 9.3: the oracle was said to
degrade to nothing on wordforms nobody has fully analysed. It does not. It
degrades to a *semantic* oracle, which is weaker for morphology but still
discriminating -- and on a Gloss-mode-heavy project it may be the only oracle
there is.

**Guardrails, non-negotiable:**

- A pairing is a **suggestion to a human**, never an automatic write. Gloss
  agreement is a prior, not a proof: polysemy, homography, non-compositional
  meaning, and a human gloss describing a sense the parser's root does not carry
  all defeat it.
- **Promotion-only ranking**, per the asymmetry above. Any implementation that
  sorts analyses by gloss distance -- pushing mismatches down -- is wrong and
  must fail review, because it inverts the correct answer on lexicalized forms.
- Never present a low-ranked analysis as wrong. The mandated tier wording of
  9.3.1 still applies; ranking reorders, it does not judge.
- Report the confidence basis explicitly (1:1 count match vs. gloss-string
  agreement vs. both), so the user can see *why* a pairing was proposed.

#### 9.3.3 Consequence: mode 1 duplicates against gloss-only work

`ProcessAnalysis` looks for an existing `IWfiAnalysis` whose morph bundles match
the parse. A gloss-only analysis has zero bundles and can never match
(9.3.1), so filing **creates a second analysis** and the human's gloss-only
record survives beside it -- one carrying meaning, one carrying morphology,
unmerged.

On a project with substantial Gloss-mode work, a mode-1 pass therefore produces
duplicate analyses **by construction**. This is FLEx's own behaviour, not
something we introduce, but we trigger it in batch and must disclose it:

- The mode-1 confirmation (12.4) must project **duplicates** alongside creations
  and deletions: "may create N analyses, M of which duplicate an existing
  gloss-only record."
- Merging the two -- completing a human's tier-1 record with the parser's
  morphology -- would be a genuinely useful operation and is **out of scope
  here**. It is a distinct write path, not reachable through `ProcessParse`, and
  it needs its own design and its own gates. Recorded as a follow-up in 17.6,
  not smuggled into this feature.

**Project-state precondition:** on a project never parsed live, the oracle is not
degraded, it is **absent**. The tool must say so -- "this project has no
parser-created analyses, so no approval comparison is possible" -- rather than
emit a report in which every analysis reads as unreviewed. Silently producing a
degenerate report is how a user concludes their grammar is bad when the truth is
nobody ever ran the parser.

**Mandatory output wording:**

- Approved (tier 3), **and not in any segment**: `"Approved by [user] on
  [date]."`
- Approved (tier 3) **but occurring in a segment**: `"Approved under [user] on
  [date]. This analysis is in use in a text, and approval is recorded for
  anything left in use -- so it may have been affirmed, or merely used. There is
  no way to tell which."` Never render this case with the bare sentence above,
  and never call it unapproved or auto-approved; see 9.3.4.
- Disapproved: `"Marked incorrect by [user] on [date]."`
- No stored opinion: `"Not yet reviewed by a human -- this is not evidence it is
  wrong, only that nobody has checked it."`
- **Tier 1 (gloss only):** `"A human recorded what this word means, but not how
  it decomposes -- there is no morphology here to compare the parser against."`
- **Tier 2 (sketched, unlinked):** `"A human began a morphological analysis but
  did not finish linking it -- [N] of [M] morphs are not linked to a lexical
  entry, so it cannot be compared to the parser's output."`

**Never** render the third case as "invalid", "incorrect", "rejected", or
"flagged". Those words claim a verdict that does not exist. Equally, **never**
render tiers 1 and 2 as disagreement with the parser -- the human has not
disagreed, they have not yet spoken on the question the parser is answering.

#### 9.3.4 "Human approved" is usually tacit, and tacit cannot be told from affirmed

`ParseFiler.SetUnsuccessfulParseEvals` (`ParseFiler.cs:302-320`) writes a
**user-agent approval on the user's behalf** for any analysis in use in a
segment. The comment at `:310` states the intent -- "ensure that used analyses
have a user evaluation" -- and `:311` calls
`m_userAgent.SetEvaluation(analysis, Opinions.approves)` when the analysis, or
one of its glosses, appears in the wordform's `OccurrencesBag` segment analyses.
That call fires **before** the noopinion/delete check at `:313-318`.

**This is not a failure-path quirk.** `SetUnsuccessfulParseEvals` is called on
**both** result branches -- `ParseFiler.cs:231` (`ErrorMessage != null`) and
`:238` (successful parse) -- for every wordform whose `Checksum` changed. Every
filing run therefore writes user approvals across all the wordforms it processes.

**What this looks like from the user's side, which is the common case.** The
mechanism above is not exotic and it is not usually a machine inventing an
opinion out of nothing. It is the ordinary interlinear workflow: a person works
on a text, interacts with one or more parts of an analysis -- picks a sense,
fixes a gloss, leaves the rest standing -- and **never clicks the check that
approves it**. The analysis is now in use in a segment, so the next filing run
records it as approved on their behalf.

Call that a **tacit approval**. The distinction that matters is not
human-versus-machine, it is:

| | What the user did | Strength as an oracle |
|---|---|---|
| **Affirmed** | Clicked approve on this analysis | Strong -- a judgement about this analysis |
| **Tacit** | Used it in a text without approving it | Real but weak -- selection, not a verdict |
| **No opinion** | Nothing | None, and not evidence of wrongness |

Tacit approval is **not nothing**. Leaving an analysis standing in a text you are
working through is a weak human signal, and the spec must not talk about it as
noise or as a bug. But it is not the act the oracle needs: the user affirmed
nothing about the morphology, and may not have looked at it.

**They cannot be reliably distinguished.** The stored evaluation is identical --
same agent, same `Opinions.approves`, no flag recording which path wrote it and
no separate timestamp for the click. This is the governing constraint on
everything below, and no amount of care in the reporting layer removes it.

Consequences, to be honoured rather than worked around:

- `HumanApprovedAnalyses` means **"affirmed OR tacit"**, with no way to split it.
  Any G3 statement that reads a user-agent approval as a judgement about the
  morphology is weaker than it appears.
- A bare user-`noopinion` count is **not** "never human-reviewed": in-segment
  analyses were silently upgraded out of `noopinion`.
- Protectively, and this is the part 12.2 depends on: in-segment analyses are
  **shielded** from the non-undoable delete, because they hold a user approval
  by the time the delete check runs. Tacit approval is weak evidence but a
  **strong** shield -- exactly the asymmetry we want on a non-undoable path.

**Mandatory reporting rule.** Where the oracle is reported, the population in
which tacit approvals live is named **separately** and never folded into a bare
approved count:

> `"[N] analyses carry a human approval. [M] of those appear in a text, where
> approval is recorded for anything left in use -- so some of those were used
> rather than affirmed. There is no way to tell which."`

The **only** discriminator available is a join against segment occurrence, and it
is one-sided:

- **Not in any segment, approved** -- someone clicked. Affirmed, reliably.
- **In a segment, approved** -- affirmed **or** tacit, *unknowable*. A person who
  genuinely clicked approve on a word in their text lands here too.

So the join does not identify tacit approvals; it identifies the population they
live in, which always also contains affirmed ones. Report the split as
`{affirmed, indeterminate}`, never as `{affirmed, tacit}` -- the second labels
individual analyses with a provenance the database does not record, and a user
who *did* review their text would rightly call that wrong about their own work.
Asserting that a human never reviewed an analysis on the strength of an opinion
field is the same class of error as 3.1's inference from database state, one
layer in.

**One further weakening, unverified.** Segment assignment may not always follow
from a human act at all: FLEx propagates guessed analyses through interlinear
text, so an analysis can plausibly reach `AnalysesRS` by being *offered and not
overruled* rather than chosen. If so, part of the indeterminate population is
weaker than tacit. Not established here -- recorded as 17.12, to verify before
CP3 leans on the split. It does not change the reporting rule, which already
refuses to characterise individual analyses; it only makes that refusal more
clearly right.

### 9.4 Cost

Default drill-down cap 10-20 words per session, chosen by the user, never
auto-traced in bulk. When 400 words look overgenerating, do **not** trace 400:
report the batch summary, cluster by shared root entry or category pair (a single
loose rule produces a cluster, not 400 independent problems), and recommend
tracing 1-3 representatives per cluster.

### 9.5 G4: the parse that does not terminate

G1 asks which words fail, G2 why one failed, G3 why too many succeeded. A fourth
question sits underneath all of them and until now had **no answer available
anywhere**: *why does this parse never finish?* There is no in-FLEx way to
diagnose a parse that ran forever or died of memory exhaustion -- the GUI offers a
progress bar and a warning that tracing "may take a very long time", and nothing
else. A user whose parse OOMs learns only that it OOMed.

That gap is the reason G4 belongs here rather than upstream. `PanGloss`
(`sillsdev/PanGloss`) may grow an adaptable parser-health feature, but it is
further from release than this MCP, so it is **convergence to watch, not a
dependency to wait on**. If its heuristics land first, adopt them; nothing in
this section may be deferred on that possibility.

#### 9.5.1 What actually makes a grammar pathological

Non-termination is rarely mysterious. It is almost always **path multiplication**,
and a small set of causes dominates:

| Cause | Why it multiplies paths |
|---|---|
| **Unconstrained null morphemes** | A null morph that can attach anywhere can attach *everywhere*, at every position, in every combination -- the single largest contributor |
| **Short or very common morphemes/allomorphs** | A one- or two-segment allomorph matches at many offsets in every word, so each match forks the search |
| **Underconstrained phonological rules** | A rule with a permissive environment fires on inputs it was never meant to touch, generating spurious intermediate forms that each spawn their own subtree |
| **Poorly distinguished or overlapping phonemes** | When natural classes overlap, a segment satisfies several rules at once and the search follows all of them |

**This table is a starting point, not an inventory.** The maintainer's list is
explicitly incomplete, and PanGloss has more depth here (9.5.3). Treat these four
as the causes known to dominate, add to them as evidence accumulates, and do not
let an implementation read the table as the closed set of checks to write.

These are the same properties that drive G3 overgeneration, seen at a different
magnitude: G3 is "the grammar licensed six analyses", G4 is "the grammar licensed
so many partial derivations that the search never returned". Treating them as one
phenomenon at two scales is correct, and the G3 batch signals of 9.1 are the
early warning for G4.

#### 9.5.2 Three instruments -- and which one carries G4

**Instrument 1 is the primary one** (decided 2026-09-15). G4 is answered by
static detection in the lexicon and grammar, not by runtime instrumentation.
Instruments 2 and 3 are supporting evidence, and instrument 3 is explicitly not
on the critical path -- see 9.5.6 for why.

**1. Static heuristics over an exported grammar -- no parse at all.** The sandbox
spine already exports a DTD-documented HC config (5.3) whose elements are exactly
the objects above: `PhonologicalRule`, `LeftEnvironment`, `RightEnvironment`,
`NaturalClasses`, `SegmentNaturalClass`, `SegmentDefinition`. Scanning it for null
and very short allomorphs, rules with empty or near-empty environments, and
overlapping natural classes is a **static check costing no parse time**, runnable
before a corpus run rather than after it hangs. This is the instrument `next_step`
should reach for first, and it is the cheapest thing in this entire feature.

**2. One bounded complete parse.** Run a single word to completion with a hard
bound and report what it actually cost. A grammar that takes minutes on one short
word will not finish a corpus, and knowing that costs one word rather than one
night.

**3. Incomplete parse plus postmortem.** When a run is aborted -- by cancellation,
timeout, or OOM (5.6) -- report *where the search was spending itself*: per
morpheme, how many times it was considered and how many times that path failed.
"This null morpheme was considered 40,000 times and failed every time" names the
culprit directly, and is the diagnosis a user currently cannot get at any price.

**Instrument 3 is buildable, and the mechanism is now known** (verified against
FieldWorks source and `SIL.Machine.Morphology.HermitCrab` 3.8.4, 2026-09-15).

The engine has **no statistics surface at all** -- reflection over every type
matching `Stat|Count|Metric|Profil|Progress|Cancel|Timeout|Limit` returns zero
types. But it has something better: **`ITraceManager`**, an interface the engine
calls back on at every step and which FieldWorks itself implements
(`FwXmlTraceManager.cs:20`). Its ~28 members are exactly the events we need --
`MorphologicalRuleApplied` / `NotApplied`, `PhonologicalRuleApplied` /
`NotApplied`, `CompoundingRuleNotApplied`, `LexicalLookup`, `Blocked`, `Failed` --
each carrying the rule, allomorph or morpheme, and the failing ones carrying a
`FailureReason` from the same 23-value enum 8.1 already cites. "This morpheme was
considered 40,000 times and failed every time" is a counting `ITraceManager`.

Three facts shape the design:

1. **Counters must live on our object, not on a return value.** `Morpher.ParseWord`
   is eager, not an iterator, and assigns its `out trace` only on normal return.
   `HCParser`'s catch block discards the trace entirely (`HCParser.cs:220-223`).
   So an aborted parse yields nothing through the return path -- but a stateful
   trace manager we own survives the abort and can be read afterwards. This is
   the *only* mechanism in this codebase that produces a postmortem.
2. **Callbacks are gated by `IsTracing`**, checked at 29 IL sites across
   `Morpher` and the analysis/synthesis rules. FieldWorks sets it only in the
   trace path (`HCParser.cs:206`); plain `ParseWord` never does, so bulk parsing
   runs uninstrumented. Turning it on costs something -- but most of FLEx's
   tracing cost is `FwXmlTraceManager` **building an XML tree**, not the callback
   itself. A counting manager that increments integers should be far cheaper than
   mode C. Measure this rather than assuming it.
3. **`HCParser` will not let us inject one.** It constructs `FwXmlTraceManager`
   itself (`HCParser.cs:53`) and hands it to a `Morpher` held in a **private field
   with no public getter** (`HCParser.cs:25`). See the open question in 9.5.6.

> Also verified: there is **no `CancellationToken`, timeout, or step/node budget**
> anywhere on `HCParser`, `IParser`, or `Morpher`. 5.6's cooperative,
> word-boundary cancellation is not a design preference -- it is the only thing
> available.

Instruments 1 and 2 do not depend on any of this and must not be sequenced behind
it.

#### 9.5.3 What PanGloss actually detects statically

`sillsdev/PanGloss` (teammate: Johnml1135) is a Rust port of HermitCrab's parser
running a propose-and-confirm FST architecture, conformance-tested against the C#
HermitCrab oracle in `sillsdev/machine`. Same engine semantics we drive, so its
findings describe our parser rather than an analogous one. Investigated in source
2026-09-15.

**Correction to an earlier draft of this section.** Its three best-known signals
-- *expensive object kinds* (self-time ms), *never-fires rules* (attempted >= 1,000
times in one direction with zero outputs), and *unrooted derivations* (`no_root`,
rules whose outputs repeatedly fail lexical lookup) -- are **corpus-driven
counters from a real parse** (`pangloss batch --stats`), not static checks. Given
9.5.6's decision they are out of reach as a mechanism. They survive as
*vocabulary*: "dead-end morphology" is a real category and `no_root` names it.

The static surface is smaller than PanGloss's own README suggests, and the
valuable material is not in the CLI commands at all.

**`fst-health` emits four findings and exactly one numeric threshold:**

| Finding | Trigger | Threshold |
|---|---|---|
| `BackendCoverageIncomplete` | every backend declines some construct -- nothing can represent it recall-preservingly | -- |
| `UnknownUnboundedConstruct` (cost) | construct is proposed as a superset and pruned by the confirmer | -- |
| `UnknownUnboundedConstruct` (per rule) | **an unbounded Kleene quantifier (`max="-1"`)** anywhere in a rule's LHS, RHS, or either environment | -- |
| `RuleInteractionProduct` | `mrule_count x prule_count` | **64** |

**`grammar-health` runs three authoring lints**, and these are *ported from C#*
`SIL.Machine.Morphology.HermitCrab.GrammarHealthChecker`:
`hc-undeclared-segment` (error -- a morph form contains a character the phoneme
inventory never declares), `hc-duplicate-feature-bundle` (two segments with
identical feature lanes, so "a segment-changing rule cannot reliably tell them
apart"), and `hc-partial-morpheme` ("leaving it partial can broaden analysis and
disable safe final-template pruning").

> **Worth checking early.** `GrammarHealthChecker` is a **C# type in the machine
> library**, and `SIL.Machine.Morphology.HermitCrab.dll` already ships in the
> FieldWorks install directory we load from. If it is public in the installed
> version, those three lints are free -- no port, no reimplementation. Verify at
> CP1 alongside the capability probe.

**The single most transferable idea is the net-shape screen.** It inspects a
compiled FST statically -- `O(states + arcs)`, no word applied -- and asserts
exactly one defect: a **zero-width cycle**, a loop whose every arc consumes
nothing on the tape being read, so each lap yields a different output string. Its
own framing is the sentence to carry over:

> "The null-morph pathology is precisely an `in != EPSILON, out == EPSILON`
> self-loop: invisible in the down direction, unbounded in the up direction."

It has **no threshold**. It is a structural fact, not a measurement.

**Measured blow-up factors**, which is what makes 9.5.1's ranking evidence-based
rather than intuitive:

- **425x** -- an affix allomorph whose whole shape is boundary characters
  degenerates to a zero-width entry sitting on a self-loop, freely repeatable
  (127 -> 53,992 proposals on one five-word slice).
- **Six orders of magnitude** -- zero-surface slot allomorphs admitted at every
  template level rather than once per slot: **2.5M candidates for one Sena word
  where the engine returns 8.**
- **Representation-variant products**, measured per language: Aweti **4096**,
  Mbugwe 256, Sena 8, Amharic 8, Indonesian 4. A phoneme carrying several
  orthographic representations multiplies out across a form -- "a twelve-segment
  root whose segments each carry two spellings is 2^12."
- **One epenthesis or metathesis rule anywhere widens the expensive route to the
  whole grammar** -- a static per-grammar predicate, tripped by a rewrite rule
  with an empty left-hand side.

**Adopt this warning; it is the most useful negative result in the repo.** Size is
**anti-correlated** with cost. Measured on Sena, a 2,044-state / 21,114-arc
network ran roughly **1300x slower** than a 106,365-state / 702,364-arc one:

> "Any metric monotone in states, arcs, or total proposal count picks the wrong
> candidate here."

A scan must therefore never rank grammars by how big anything is. This is the
mechanism behind 9.5.7's no-scalar-score rule, and it is measured rather than
asserted.

**Treat their numbers as placeholders, because they do.** PanGloss labels its own
thresholds: the rule-product 64 is "a conservative, uncalibrated placeholder ...
never used to reject a compile", and the 100 MB payload band says "no grammar was
measured to pick it". Import the *checks*, never the constants, and never present
a borrowed number as measured.

**What PanGloss does NOT check, verified by exhaustive search.** There is **no
short-allomorph check** -- no length test on allomorph forms produces any finding
anywhere -- **no general permissive-environment check** beyond empty-LHS
epenthesis and the unbounded quantifier, and **no overlapping-natural-class
check**. The nearest are duplicate feature bundles at the *segment* level and
overlapping environments between subrules of a single simultaneous rule.

So 9.5.1's causes and PanGloss's findings are **complementary, and neither is a
superset**. Two of the four causes named there have no PanGloss counterpart at
all. Two shapes PanGloss names but has never built -- `null-cycle` and
`optional-slot-branching` -- are catalogue entries with no producer, so
implementing them here puts us ahead rather than behind.

Their scope rule is ours too: **"A pathological verdict is INFORMATION, not
permission to stop proposing."**

#### 9.5.4 The pathology-to-LCM mapping

This is the translation: what PanGloss identifies as pathological for a compiled
FST, restated as something detectable in a FieldWorks lexicon. Ranked by
PanGloss's own measured evidence, highest yield first.

| # | Pathology | Evidence | LCM check |
|---|---|---|---|
| 1 | **Zero-surface morph in a repeatable position** | 425x; 10^6 | an `IMoForm` whose form is empty or only boundary characters, reachable from an optional slot or a self-looping position |
| 2 | **Representation-variant product per form** | Aweti 4096 | product of `IPhPhoneme.CodesOS` counts over a form's segments -- **`CodesOS` verified**, inherited from `IPhTerminalUnit` |
| 3 | **Epenthesis or metathesis anywhere** | whole-grammar cost class | an `IPhRegularRule` with an empty structural description; any `IPhMetathesisRule` |
| 4 | **Unbounded quantifier in a pattern or environment** | `fst-health` finding | `IPhIterationContext.Maximum == -1` -- **verified**; `Maximum` and `Minimum` are `Int32` |
| 5 | **Morphological x phonological rule product** | threshold 64, placeholder | affix-process rule count x (`IPhRegularRule` + `IPhMetathesisRule`) count |
| 6 | **Partial morphemes** | `hc-partial-morpheme` | entries and affix rules lacking category or template analysis -- overlaps the tier-2 "sketched" notion of 9.3.1 |
| 7 | **Multiple allomorphs per entry; stem-name restriction** | both proposed unconditionally, never filtered | `ILexEntry.AlternateFormsOS.Count > 1`; `IMoStemAllomorph.StemNameRA != null` |
| 8 | **Unordered rule application; derivation depth** | 2^N, capped at N=6 | rule ordering is `IPhSegmentRule.OrderNumber`, grouped via `InitialStratumRA`/`FinalStratumRA` -- **verified**; `IMoStratum` has no rule collection, only `Abbreviation`, `Description`, `Name`, `PhonemesRA`; standalone derivational rule count equals chain depth |
| 9 | **Segments with identical feature bundles** | `hc-duplicate-feature-bundle` | compare `IPhPhoneme.FeaturesOA` within a phoneme set -- **`FeaturesOA` verified** |
| 10 | **Optional template slots** | named by PanGloss, never built | independent apply/skip choices across `IMoInflAffixSlot`s -- we would be first |

Plus the three 9.5.1 causes PanGloss does not cover at all: **short allomorphs**,
**broadly permissive rule environments**, and **overlapping natural classes**.

Three implementation notes:

- **Rows 1, 2, 3 (epenthesis half), 4, 6, 8, 9 and 10 have had their LCM property
  names verified**, through this project's own index. Three items remain
  *proposed* and must be checked with `flextools_get_object_api` before they are
  written: row 3's metathesis half (`IPhMetathesisRule`), row 5's rule-count
  product, and row 7's `AlternateFormsOS` half. Do not let the table's confident
  formatting stand in for that check -- that is the 8.4 failure applied to our
  own planning.
- **Most of these properties require a pythonnet cast.** The index reports 26-27
  casting-required properties on `IPhPhoneme` and `IPhIterationContext` alone, and
  the phonological context collections are polymorphic. Use the index's
  `cast_example` output rather than hand-writing accessors.
- **`OrderNumber` is a per-stratum-pair counter, not a grammar-wide ordinal.**
  Each rule references exactly one `InitialStratumRA`/`FinalStratumRA` pair, so
  `OrderNumber` is comparable only within that pair's grouping. Never sort or
  compare it across pairs.
- **The user assigns rules to strata; the data model stores that on the rule.**
  In FLEx the linguist assigns a phonological rule to a stratum from the rule's
  own settings, so the user's mental model is "this rule belongs to this
  stratum." LCM stores exactly that relationship, but on the rule side
  (`InitialStratumRA`/`FinalStratumRA`), which is why `IMoStratum` has no rule
  collection to read back. The two views agree -- only the direction of the
  reference differs. Row 8's `measured`/`evidence_basis` wording must speak the
  user's direction ("rules assigned to stratum X"), never "stratum X owns rules",
  and the absence of a collection on `IMoStratum` is not evidence that strata are
  unordered or unassigned.
- **This table has no writing-system column, but rows 1, 2 and 6 -- plus the
  `objects[]` label sites in rows 5 and 7a -- read an `IMultiUnicode`/
  `IMultiString` field directly off LCM.** Any row that does must resolve
  that field to a plain `str` at a named writing system *before* comparing
  or serializing it (`data-model.md`'s cross-cutting rule 2 states the
  resolve-then-compare order in full). Skipping this step does not make the
  check merely wrong -- it makes the check's predicate unconditionally
  `False`, so it silently reports zero regardless of the project's actual
  data. A future row that touches another multistring field is not exempt
  from this note.

#### 9.5.5 Instrument 1's home: `flextools_grammar_health`

The static scan is **pure LCM** and therefore ships early, decoupled from the
sandbox spine entirely. Everything 9.5.1 looks for is an LCM object: allomorphs
are `IMoForm`, rule environments are `IPhEnvironment` on `IPhRegularRule`,
overlapping phonemes are `IPhNaturalClass`. No export, no project copy, no `hc`
tool, no subprocess -- so it does not wait for CP5, and it is available from the
moment a project can be opened.

The checks it implements are the mapping of 9.5.4, in that order -- highest
measured yield first, and each verified against the LCM index before it is
written.

**It ships at CP1** (section 15) -- it is the only substantial deliverable in this
feature with no dependency on ParserCore, the `hc` tool, or a parse, so nothing
justifies holding it back.

`flextools_grammar_health` is `READ_ONLY_SAFE`, reads no wordforms and runs no
parse. `HCParser.WriteDataIssues(XElement)` (`HCParser.cs:234`) is public and
should be folded in where it overlaps.

**It is proposed, not pushed.** Per the maintainer: offer it when *a parse that
should have been quick was not*. The fast-path window of 5.6 already defines
"should have been quick" -- a `try_word` that misses it is by definition
surprising, and that is the trigger. A scan advertised on every response is noise
that trains people to ignore `next_step`. Routine calls remain available to
anyone who wants one; what is conditional is the *proposal*.

And per 10.1, never propose it when the session cannot run it.

#### 9.5.6 Decided: static detection over runtime instrumentation

Instrument 3 needs a custom `ITraceManager`, and `HCParser` exposes no way to
supply one -- `m_morpher` is private with no getter (`HCParser.cs:25`), the trace
manager is constructed internally (`:53`). The decision is **not to force that
door**.

- **Reflecting into the private field is rejected.** It would break silently on a
  FieldWorks upgrade, and the capability probe of 5.4 could not catch it: the
  member is private and therefore outside the probe's declared surface. A guard
  that structurally cannot guard the thing it depends on is not a guard.
- **A seam would be welcome, and is a FieldWorks ask, not a PanGloss one** -- an
  `ITraceManager` setter or a `Morpher` accessor on `HCParser` in ParserCore. If
  it is cheap it is worth requesting. **Nothing may be planned around it.**
- **Instrument 3 is deferred**, not deleted. Should a seam appear, the design is
  already written (9.5.2) and it drops in as supporting evidence.

**What replaces it: learn the pathology, detect it in the lexicon.** PanGloss
identifies what is pathological *for a compiled FST*. That knowledge transfers
even though the substrate does not, and the reason it transfers is the useful
part: **FST compilation makes path multiplication manifest.** A null morpheme
that can attach anywhere, an allomorph short enough to match at every offset, a
rule whose environment constrains nothing -- these show up at compile time as
state explosion, which is why an FST compiler notices them and a lexicon browser
does not. Its compile-time warnings are therefore a *precomputed catalogue of
lexicon properties worth looking for*. We cannot compile an FST; we can look for
the same properties directly in LCM.

So the work is: take PanGloss's pathology list, translate each item from
FST-compile terms into the LCM objects of 9.5.5, and implement the checks here.

**PanGloss is never a dependency** -- not at runtime, not at build time, not as a
bundled binary. What crosses the boundary is knowledge and, where licensing
allows, algorithms. This holds even if PanGloss ships first.

One adjacent lever worth recording: `Morpher.MaxStemCount` (default 2),
`DeletionReapplications` (0) and `MergeEquivalentAnalyses` are **data-driven**,
read from `MorphologicalDataOA.ParserParameters` (`<HC><MaxRoots>`,
`<DelReapps>`, `<MergeAnalyses>`) inside `LoadParser` and re-read on `Update()`.
So a search bound *is* reachable without any API change -- by editing project
parameters, not by passing an argument. `Morpher.MaxUnapplications` exists and is
**never set by FieldWorks**.

#### 9.5.7 Reporting rule

A G4 finding names a **suspect**, never a defect. An unconstrained null morpheme
may be exactly right for the language; a short allomorph may be the most common
morpheme in the lexicon. The wording of 8.4 governs here as everywhere: report
what was measured -- the count, the rule, the morpheme -- and say what it costs,
not that it is wrong.

---

## 10. Tools

Named per spine. **The spine is stated in the first line of each tool
description** -- a calling model reads descriptions, not annotation bits.

| Tool | Spine | Annotation | Purpose |
|---|---|---|---|
| `flextools_try_word` | in-process read | `READ_ONLY_SAFE` | "in-process, live DB, read-only, cannot add analyses". Answers inline on the fast path (5.6). Takes `trace` -- the three modes of 5.1.1 |
| `flextools_parse_text` | in-process write | `readOnlyHint=False, destructiveHint=True` | "in-process, live DB, WRITES on apply=True, non-undoable, ladder-gated" |
| `flextools_parse_sandbox` | sandbox | `READ_ONLY_SAFE` w.r.t. the live DB | "exported/copied grammar, never touches the live DB, speculative edits welcome" |
| `flextools_parse_diff` | consumer | `READ_ONLY_SAFE` | Before/after over run artifacts |
| `flextools_parse_log` | consumer | `READ_ONLY_SAFE` | Read run artifacts |
| `flextools_parse_status` | consumer | `READ_ONLY_SAFE` | Progress and terminal state of a parse job; cancels one on request (5.6) |
| `flextools_grammar_health` | in-process read | `READ_ONLY_SAFE` | Pure-LCM static scan for path-multiplying grammar properties (9.5.5). No parse, no export, no subprocess |
| `flextools_health` (parser block) | -- | `READ_ONLY_SAFE` | Preflight for all three spines (10.2) |

`flextools_try_word(word, trace="none"|"selected"|"full", morphs=None)` covers
FLEx's whole Try A Word surface in one tool, because all three modes of 5.1.1 are
the same `READ_ONLY_SAFE` call path -- the argument changes cost and verbosity,
never reachable capability. `trace="selected"` requires `morphs`; `morphs`
without `trace="selected"` is a caller error rather than a silent upgrade, since
FLEx itself discards the selection unless tracing is on
(`TryAWordDlg.cs:515-518`) and a user who asked to restrict the search must not
be handed an unrestricted one under the same label. Default `trace="none"` -- the
cheap answer first, with the response naming the next rung of the 8.2 ladder when
the word fails.

`flextools_parse_text` takes `apply` (default `false`). Because parses are jobs
(5.6) it returns a `run_id` rather than results; `applied: true/false` is echoed
on the terminal status, so the record of whether anything was written lives with
the run artifact rather than in a response the caller may never have seen.

**Why a capability split rather than one tool with a flag.** Annotations declare
a tool's *maximum reachable capability*, evaluated before any argument is known.
`try_word`'s call path structurally cannot reach `ParseFiler` or xCore, so it
earns `READ_ONLY_SAFE` on its own facts. Tagging it destructive would *overstate*
and throttle the low-friction hypothesis-testing loop the gradient exists to
enable. `parse_text` reuses `run_module`'s existing ladder verbatim rather than
inventing a parallel gate.

The sandbox tool's risk register is **disk and subprocess** (project copy,
`dotnet` timeout), not the LCM write surface.

### 10.1 `next_step` -- steering is part of the contract

Every parse response carries a structured `next_step`, on success as well as
failure. The confidence gradient (1.2) and the B -> A -> C ladder (8.2) only work
if something tells the caller which rung they are on and what the next one costs;
a gradient nobody is routed along is decoration.

```
next_step: {
  action:     short verb phrase        # "trace the decomposition you expect"
  tool:       tool name                # "flextools_try_word"
  args:       partial argument object  # {"trace": "selected", "morphs": [...]}
  rationale:  one sentence, why this rung and not another
  est_cost:   "inline" | "seconds" | "minutes" | "hours" | "unbounded"
}
```

Rules:

- **It is advisory, never a gate.** "Gently" is the requirement: `next_step`
  proposes, and no tool refuses a call because the caller took a different path.
  A user who wants mode C on 400 words may have it; they may not have it
  *without having been told what it costs*.
- **`est_cost` is mandatory and is the whole point.** It is the field that makes
  an hours-long option visibly hours-long at the moment of choosing, rather than
  discovered by waiting. `"unbounded"` is a real value and the honest one for
  mode C on a grammar that has not been screened by 9.5.
- **It may propose an investigation, not only a parse.** When a run is slow,
  hangs, or dies (5.6), the right next step is usually the static grammar scan of
  9.5.2 -- which costs no parse time and can shortcut most spurious paths before
  they are ever walked. Routing a stuck user to a cheap static check instead of a
  retry is the highest-value thing this field does.
- **`args` must be directly usable.** A proposal the caller has to reconstruct by
  hand will be ignored by a model and misread by a human.
- Never propose a rung the project cannot reach: no sandbox step when `hc` is
  absent (14), no filing step when the session is read-only.
- **Never propose a tool that does not exist.** No MCP tool queries lexicon data
  -- the only path is a `flextools_run_module` snippet (5.1.2). A `next_step`
  whose `tool` names an imagined lexicon search is the 8.4 failure applied to our
  own surface: a confident wrong answer about what the caller can do next.

### 10.2 `flextools_health` parser block

Per-spine, not blanket -- one dead spine must not blank the other two.

```json
"parser": {
  "read":    {"status": "ready|unavailable", "reason": null},
  "write":   {"status": "ready|unavailable", "reason": null},
  "sandbox": {"status": "ready|unavailable", "components": []},
  "active_engine": null,
  "detected": {
    "parser_core_version": null, "lcmodel_install_path": null,
    "hc_tool_version": null, "hc_path": null, "generate_hc_config_path": null
  }
}
```

Two states per spine (`ready`/`unavailable`) -- no third "degraded" value;
degradation lives in `reason`/`components`, reusing the error-code detail
vocabulary (14) so health and error envelopes never drift apart:

- `read.reason` / `write.reason`: `{signal, expected_path, detected_version,
  missing_members, lcmodel_install_path}` -- `parser_core_missing`'s shape
  verbatim. `write` additionally requires `ParseFiler.ProcessParse` in its
  member probe, so `read: ready` / `write: unavailable` is representable when
  only that member is missing. `write` also carries the **project-side**
  precondition of 12.7: with a project open, `ActiveParser == "HC"` and
  `kguidAgentHermitCrabParser` absent from `ICmAgentRepository` gives
  `write: unavailable`, `signal: parser_agent_missing`, and `{agent_guid,
  active_engine}` in the reason. That probe needs an open project, so when
  health runs session-independent it is **skipped, not failed**: `write` status
  stays driven by the member probe alone and the reason records
  `agent_probe: "skipped"`. A skipped probe is never reported as a pass.
- `sandbox.components`: an **array** of `{component: "hc"|"GenerateHCConfig.exe",
  found, expected_path}` -- not singular like `parser_tool_missing`, because the
  two tools fail independently and a caller must know which one to install.

Licenses: `read: ready` -> `flextools_try_word` callable. `write: ready` ->
`flextools_parse_text` callable (still walks the write ladder, 12.4). `sandbox:
ready` -> `flextools_parse_sandbox` callable. `active_engine` is
**informational only** -- it echoes `ActiveParser` when a project is open, else
`null` -- and never a status input; the mismatch gate lives in the per-call
preflight below, not here, since `ActiveParser` is a project property and
health can run session-independent. `detected.parser_core_version` sits beside
it and never decides: no code path may compare it to a floor (5.4).

**Interface seam for the detection agent.** Supply a `ParserDetector` returning
`{read_probe: ProbeResult, write_probe: ProbeResult, sandbox_probe: {hc:
ProbeResult, generate_config: ProbeResult}, active_engine: str|None, versions:
{...}}` where `ProbeResult = {ok: bool, signal, expected_path, missing_members,
detected_version}`. `flextools_health` only reshapes that into the block above
-- no location/reflection logic lives in the handler itself; that logic is
`parser_probe.py` (5.4).

**Shared preflight helper.** `check_active_parser(project,
supported_engines=("HC",)) -> None`, raising `parser_engine_mismatch` on
mismatch, is called as the **first statement** in each of the three
spine-executing handlers (`try_word`, `parse_text`, `parse_sandbox`) -- before
any `HCParser`/config-export construction. `parse_diff`/`parse_log`/
`parse_status` never call it; they read prior artifacts and never touch the
engine. Because `ActiveParser` is user-flippable mid-session (5.6), the helper
always re-reads it live on every call -- there is no session-immutable branch
to optimise for, and `active_engine` above is likewise a live read, true at
call time only. For `parse_text` the check still fires once, at job submission
(12.4's ladder is walked before the job starts, not per-word); a flip mid-job
is reported as a warning on the run summary, not a refusal (5.6).

**`next_step` per unhealthy state:**

| State | action | tool | args | est_cost |
|---|---|---|---|---|
| `read: unavailable` | "install/repair FieldWorks so ParserCore is reachable" | none (external) | -- | n/a |
| `write: unavailable`, `read: ready` | "use read-only Try A Word; filing unavailable" | `flextools_try_word` | `{}` | inline |
| `sandbox.components[hc].found=false` | "install the hc dotnet tool" | none (external) | -- | n/a |
| `sandbox: unavailable` (either component missing) | never propose `flextools_parse_sandbox` | -- | -- | -- |
| `write: unavailable`, `signal: parser_agent_missing` | "this project has never run HermitCrab; run it once from FLEx's Parser menu, then retry filing" | `flextools_try_word` (read-only diagnosis is unaffected) | `{}` | inline |
| `active_engine` mismatch | "project is on {configured_engine}; HC tools refused" | none (external, switch engine in FLEx) | -- | n/a |

No rung ever names a tool whose spine is `unavailable` -- consistent with the
"never propose a rung the project cannot reach" rule above.

---

## 11. Diff semantics

Align on FLEx's own analysis-matching notion, `MatchesIWfiAnalysis`
(`ParseResult.cs:102-133`), rather than inventing a normalized signature -- the
in-process spine gives typed morphs, so we can match the way FLEx matches.

| Condition | Bucket |
|---|---|
| `b == 0, c > 0` | `fixed` |
| `b > 0, c == 0` | `broken` |
| both > 0, sets differ | `changed` |
| identical | `unchanged` |

**Ambiguity is a regression too** -- one analysis becoming seven still "parses"
but the grammar got worse. `changed` must not collapse into `unchanged`.

Sandbox corpus results classify into the **same** buckets: expected-but-missing =
`broken`, actual-but-unexpected = `changed`. This is why the CLI's `test` results
must be read from its `Expected parses:` / `Actual parses:` sections rather than
its binary pass/fail line -- `test` uses exact multiset equality over form+gloss,
order-sensitive, so a corpus entry fails on any legitimate **new ambiguity**, not
only on a regression.

Runs carry a `scope_fingerprint`; mismatched fingerprints are refused with
`parse_scope_mismatch` unless `force=true`, and then diffed on the intersection
only.

---

## 12. Safety

### 12.1 Per-mode, not blanket

- `flextools_try_word` -- cannot reach a write type. **The guarantee is about a
  call path, not a class:** "a tool that constructs only `HCParser` and calls
  `ParseWord`/`TraceWordXml`", never "ParserCore is UI-free". `ParserWorker` and
  `ParserScheduler` pull xCore in through their own constructor parameters, so
  "let's reuse ParserWorker for consistency" is precisely the refactor that
  silently breaks it. Guarded by a standing test (section 16).
- `flextools_parse_sandbox` -- no path back to the live DB exists in the tool.
- `flextools_parse_text` -- write-capable; full ladder below.

### 12.2 P0-1: filing can permanently delete analyses

`ProcessParse` resets the parser agent's opinion on **every** existing analysis to
`noopinion` (`ParseFiler.cs:226-227`), then `SetUnsuccessfulParseEvals` **deletes**
any analysis where parser and user both hold `noopinion` (`:314-315`).
Non-undoable (`UowService.NonUndoableStack`).

So a pass against a broken or half-edited grammar permanently deletes previously
parser-created, never-reviewed analyses -- triggered by the exact edit-then-check
loop this feature enables. This is FLEx's own behaviour (a human hits it from the
menu too), but we would trigger it in batch.

**Risk inverts with project state.** Deletion requires pre-existing
parser-created, never-reviewed analyses. A project never parsed live has none, so
its *first* filing parse cannot delete anything; risk arrives with the second run
and grows. The confirmation must therefore project **actual** deletions computed
from project state -- a concrete "may delete 0 analyses" is far better than an
abstract warning that trains people to click through.

**The deletion set is a conjunction, not a single predicate.** Before the delete
check runs, `SetUnsuccessfulParseEvals` has already written a user approval for
every processed analysis that occurs in a segment -- the tacit approval of 9.3.4.
Those analyses are **shielded**: they no longer hold user `noopinion` at
`:314-315`. Weak evidence, strong shield: an analysis a person merely left
standing in a text cannot be silently deleted, which is the right outcome here
even though that same approval is nearly worthless as an oracle. The projection
must therefore compute

> **user-`noopinion` AND not referenced by any segment**

Projecting on user-`noopinion` alone **over-projects** -- it warns about
analyses that cannot be deleted. That is not a safe direction to err in: it
inflates the number a user is asked to accept, which is precisely how a
confirmation stops being read.

What the user never sees changed: `ProcessParse` never writes
`ISegment.AnalysesRS`, and the user agent's `SetEvaluation` is called in exactly
one place and only to **approve** -- so filing can never overwrite or revoke a
human's opinion. Note the asymmetry 9.3.4 draws out, because this paragraph is
easy to read as stronger than it is: that same single call site *adds* user
approvals the human never gave. Filing cannot take a human opinion away; it can
invent one.

### 12.3 P0-2: the grammar can shrink silently

`HCLoader.Load` always returns a `Language`; the ten `IHCLoadErrorLogger`
callbacks are advisory, with no abort, no severity and no boolean. Errors go to
`{ProjectName}HCLoadErrors.xml`, overwritten every load and never returned to any
caller. `HCLoader.AddEntry` adds an entry only when `Allomorphs.Count > 0`, so
entries whose allomorphs all failed **vanish with no signal**.

These compound into the feature's worst realistic failure: *a grammar silently
shrinks on load, the parse therefore produces fewer analyses, and filing those
results deletes the analyses the missing entries used to license* -- data loss
with no error anywhere in the chain.

**What FLEx itself does with these errors.** `HCLoader.Load` never blocks;
FLEx's own consumer, `HCParser.LoadParser` (`HCParser.cs:144-158`), truncates
and rewrites `{ProjectName}HCLoadErrors.xml` on every load via
`XmlHCLoadErrorLogger` (`HCParser.cs:595-688`). The only UI reader is
`HCTrace.CreateResultPage` (`HCTrace.cs:28-37`), which feeds that file into
`FormatHCTrace.xsl`'s `ShowAnyLoadErrors` (`FormatHCTrace.xsl:229`) on **every**
Try-a-Word result page -- both `"HCTrace"` and `"HCParse"` renders
(`HCTrace.cs:36`). That is the single-word path only: batch/corpus reparse
through `ParserWorker`/`ParserScheduler` has **no UI consumer of the side file
at all**, so a full reparse's load errors are silently written to disk and shown
to no one. Refusing to file on new load errors therefore does not override an
existing FLEx warning -- it **fills a gap** in the exact path (batch reparse)
this feature automates.

**Gate (rungs 1, 3 and 4 validated; rung 2 revised to an MCP-owned baseline,
settled as specified below):**

1. `m_morpher == null` after `Update()` -> **hard refuse**, no override.
   **Validated.**
2. **New** `<LoadError>` entries relative to an **MCP-owned baseline** -> refuse
   by default. This is the "your edit broke the grammar" case, precisely the
   one that deletes data. The baseline is the load-error set captured by
   **our own** run at **our own** grammar load, copied into `runs/<run_id>/`
   and keyed to `scope_fingerprint` -- never FLEx's
   `{ProjectName}HCLoadErrors.xml`. That file is read only as the transport for
   our own load (it is the only channel `HCLoader` offers) and is never treated
   as a prior state: it is truncated and rewritten on every load with no
   timestamp, no grammar hash and no caller identity, so comparing against it
   would conflate "changed since our last run" with "changed since some unknown
   prior FLEx session." On the first run for a given project + scope there is
   no baseline, so every load error is **pre-existing** (rung 3, warn+count),
   never **new** (rung 2) -- the same shape as 12.2's "risk arrives with the
   second run." **Revised 2026-09-15** (domain review); no longer "needs
   validation."
3. Pre-existing load errors -> warn, surface the count, carry it into the
   confirmation. **Validated** -- but "pre-existing load errors are benign" is
   a **working hypothesis**, not a proven baseline: nothing in `HCLoader.cs`
   establishes that such errors are rare or safe to ignore in the field. State
   it as an assumption, not a fact.
4. Confirmation projects **deletions**, not only creations. **Validated** --
   computed with 12.2's conjunction (user-`noopinion` **and** not referenced by
   any segment), never a bare noopinion count.

A blunt any-error gate would make mode 1 permanently unusable on projects with
benign pre-existing errors, and would invite exactly the bypass flag we must not
build. The gate reads the side file for **our own** load -- that part is
unavoidable, since it is the only channel `HCLoader` offers -- but treating
FLEx's copy of it as a cross-session baseline is exactly what rung 2 above
refuses to do.

### 12.4 The write ladder

`flextools_parse_text(apply=true)` passes the **same** ladder as `run_module`:
session `write_enabled`, `require_write_confirmation` (first call returns
`confirmation_required` with the mutation plan; resubmit needs `confirmed=True`),
`perform_pre_write_backup` before the first mutating parse per (session, project),
and the existing `needs_lock` machinery.

**Backup is mandatory here, not best-effort** -- filing is non-undoable, so it is
the only recovery.

**The ladder is walked before the job starts, never during it.** Confirmation and
backup complete while the caller is still present; only then is a `run_id`
issued. A job that paused at hour two to ask permission would be answered by a
model rather than a human, which is the hole 12.4 exists to close.

**No unattended batch parse.** `require_write_confirmation` defaults on and
nothing in this feature may introduce a bypass flag; that would recreate the
audited hole where `confirmed` is asserted by the model and never verified as
human assent.

### 12.5 General

- Subprocess work reuses `run_script_async` (`taskkill /T /F` on Windows --
  necessary because `dotnet` spawns grandchildren).
- No `Invoke-Expression`; word data reaches PowerShell only through a file.
- Words and parser output are **data, never instructions**.

### 12.6 Concurrency: what a running job excludes, and what it does not

**A parse job does not lock the project.** Working on the lexicon and on user
analyses while the parser runs is normal FLEx practice, not a hazard to be
designed out, and a feature that froze the lexicon for the hours a corpus parse
takes would be worse than no feature. Any implementation that takes a
project-wide exclusive claim for the duration of a job is wrong.

What is excluded is narrow: **concurrent writes to parser-generated analyses.**
That is the surface spine 2 owns, and two writers to the parser agent's opinions
is the genuinely incoherent case -- it is also the surface the MCP does not
normally write directly, so the exclusion costs users almost nothing. Concretely,
while a filing job runs: a second filing job against the same project is refused
(`parser_filing_in_progress`), and so is direct manipulation of parser-agent
evaluations. Lexicon edits, user-agent analyses, and non-filing parse jobs
proceed untouched.

**Filing is guarded per result, not per run.** Because the lexicon legitimately
moves under a long job, a blunt "the project changed, the whole run is stale"
verdict would fire on normal work and train people to override it -- the same
failure the any-error gate in 12.3 is rejected for. The available guard is
per-result and already named in this spec: `ParseResult.IsValid`
(`ParseResult.cs:199-202`). Section 5.1 correctly rules it out as a *linguistic*
verdict and it contributes nothing to G3 -- but object liveness is exactly the
question here, so check it immediately before `ProcessParse` on each result and
skip or re-parse a result whose morphs no longer resolve.

State the limit honestly: `IsValid` catches **deletion** of a referenced object,
not **modification** of a rule that leaves those objects alive. It is the
strongest guard available at filing time, not a coherence proof, and the run
report must not describe it as one.

---

### 12.7 P0-3: the HermitCrab agent may not exist

Numbered after 12.6 to avoid renumbering cross-referenced subsections; it ranks
with 12.2 and 12.3, not below 12.5.

`BootstrapNewLanguageProject.SetupAgents`
(`liblcm/src/SIL.LCModel/DomainServices/BootstrapNewLanguageProject.cs:140-165`)
creates exactly **three** agents -- `kguidAgentDefUser`,
`kguidAgentXAmpleParser`, `kguidAgentComputer`. It does **not** create
`kguidAgentHermitCrabParser`.

`LangProject.DefaultParserAgent`
(`liblcm/src/SIL.LCModel/DomainImpl/OverridesLangProj.cs:218-231`) nonetheless
resolves `ICmAgentRepository.GetObject(CmAgentTags.kguidAgentHermitCrabParser)`
when `MorphologicalDataOA.ActiveParser == "HC"`. Its own XML doc comment at
`:216` declares `<exception cref="KeyNotFoundException"/>`: the throw is
**documented behaviour**, not speculation.

On a project that has never run HermitCrab, resolving the HC agent may therefore
throw, and an unhandled throw surfaces as a crash rather than a clean `parser_*`
refusal -- a handler that dies mid-call tells the user nothing, which is the one
outcome this feature's preflight exists to prevent.

**Requirement.** CP1's preflight **probes for the agent**; the affected spine
reports `unavailable` with a named reason rather than letting the lookup throw:

- `flextools_health`'s `write` probe (10.2) reports
  `signal: parser_agent_missing` when a project is open, `ActiveParser == "HC"`,
  and the agent is absent from `ICmAgentRepository`.
- Any handler that would resolve the agent raises `parser_agent_missing` (14)
  instead of propagating `KeyNotFoundException`.
- The **read spine is unaffected**. `flextools_try_word` neither files nor
  resolves an agent, so a missing HC agent must never mark `read` unavailable --
  the diagnosis this feature exists to deliver stays available on exactly the
  projects most likely to lack the agent.

**Open for live verification** (17.10). Whether a data migration or a lazy path
materialises the agent elsewhere -- on first HC run from FLEx's own menu, or on
a parser switch -- could not be established from source. If such a path exists
the probe becomes a **warning** rather than a refusal; the probe itself is
required either way, because CP4 must not be the checkpoint that discovers this.
Verify read-only against a real project with `ActiveParser == "HC"` that has
never run the parser.

---

## 13. Hardening delta for `hcparse.ps1`

| # | Change | Reason |
|---|---|---|
| H1 | **REWRITTEN.** `hc` is a **dotnet global tool** (`PackAsTool=true`, `ToolCommandName=hc`, on nuget.org), installing to `%USERPROFILE%\.dotnet\tools` -- **not** `%LOCALAPPDATA%\HermitCrabTool\hc.dll` as the script assumes. Locate via PATH / `dotnet tool list -g`, with a config override. `parser_tool_missing`'s hint is literally `dotnet tool install -g SIL.Machine.Morphology.HermitCrab.Tool` |
| H2 | Words passed **by file only**, never on the command line | Arbitrary orthographies + PowerShell quoting; removes a length ceiling |
| H3 | Write `run.json` with inputs, exit codes, timings, per-word results | L3 must not screen-scrape prose |
| H4 | **REWRITTEN.** Exit code is useless: the CLI returns 0 even when words fail or error (per-command return values are discarded), and only a bad/missing config yields -1. Detect outcomes by parsing `stats`' counter line and per-word text. **Use the right stats variant**: `stats -p` covers parses only; `test` counters need `stats -t` or bare `stats`, or a corpus runner reads zeros |
| H5 | Capture `GenerateHCConfig` output to `generate-config.log` instead of `Out-Null` | The diagnostic the user asked to read. **Its exit-code semantics are unverified** -- do not assume they match H4's finding |
| H6 | **SPLIT.** The copied project is always deleted in `try/finally` -- confirmed leak today | See 7.1 |
| H7 | Free-space preflight, >= 2x project size | Mirrors `backup.py` |
| H8 | `-TimeoutSeconds` around the `dotnet` call | A runaway grammar must not pin a subprocess slot |
| H9 | ASCII-only console output | Repo convention, and these strings get parsed |
| H10 | **SPLIT.** `-ConfigOut` for the cache path, plus a distinct user-owned sandbox path the cache never touches | See 7.1 |
| H11 | Preserve verbatim: UTF-8 no-BOM script write, `-Encoding UTF8`, `[,\s]+` splitting | Section 4 -- bug fixes, not style |
| H12 | `$script:HCPARSE_VERSION`, bumped on behavioural change | Feeds the cache key |

---

## 14. Error codes

Additive, so the contract stays at `tool-responses/1.0`; requires a CHANGELOG
entry under **"Tool contract"**.

| Error code | Detail fields |
|---|---|
| `parser_engine_mismatch` | `configured_engine`, `supported_engines`, `hint` |
| `parser_core_missing` | `signal` (`absent` \| `foreign_install` \| `incompatible_surface` \| `load_failed`), `expected_path`, `detected_version`, `missing_members`, `lcmodel_install_path`, `install_hint`, `load_error` |
| `grammar_load_unclean` | `signal` (`morpher_null` \| `new_load_errors`), `new_error_count`, `baseline_error_count`, `baseline_source` (`this_run` \| `prior_run:<run_id>` \| `absent`), `log_path` |
| `parser_tool_missing` | `component` (`"hc"` \| `"GenerateHCConfig.exe"`, closed enum -- shared with `flextools_health`'s `sandbox.components[].component`, 10.2), `expected_path`, `install_hint` |
| `parser_config_failed` | `exit_code`, `stderr_tail`, `log_path`, `run_id` |
| `parser_timeout` | `timeout_seconds`, `words_completed`, `run_id`, `hint` |
| `parser_job_failed` | `state_at_failure`, `failure` (`out_of_memory` \| `crashed` \| `cancelled`), `words_completed`, `words_total`, `run_id`, `log_path` |
| `parse_scope_empty` | `scope`, `matched_texts`, `hint` |
| `parse_scope_ambiguous` | `scope`, `requested`, `candidates` |
| `parse_scope_mismatch` | `baseline_fingerprint`, `current_fingerprint`, `differing_fields`, `hint` |
| `parse_run_not_found` | `run_id`, `available_runs` |
| `parser_filing_in_progress` | `run_id`, `started_at`, `words_completed`, `hint` |
| `parser_agent_missing` | `agent_guid`, `agent_name` (`"HermitCrab"`), `active_engine`, `probe_source` (`bootstrap_absent` \| `lookup_failed`), `hint` |
| `parse_morph_unresolved` | `morph`, `position`, `resolved_to` (`none` \| `ambiguous` \| `no_msa`), `candidates`, `hint` |

Reused: `project_not_found`, `project_locked`, `project_drive_unavailable`,
`project_path_mismatch`.

---

## 15. Checkpoints

| CP | Spine | Deliverable | Writes? |
|---|---|---|---|
| **CP1** | -- / in-process read | Preflight/health for all three spines: `ParserCore.dll` located and **capability-probed** (same-install co-location + reflective member check, 5.4); `ActiveParser` read and `parser_engine_mismatch` refusal; **HC-agent probe with `parser_agent_missing` refusal logic, shipped with tests; first live caller at CP2** (12.7); `hc` located via `dotnet tool list -g`; `GenerateHCConfig.exe`. **Plus `flextools_grammar_health`** (9.5.5) -- the primary G4 instrument, pure LCM, no parser involved. Delivers standalone value on day one | No |
| **CP2** | in-process read | **flexicon first** (S9): the read-only `project.Parser` facade plus `Texts.GetGenres()`, lazily imported and capability-probed on flexicon's own side. Then `flextools_try_word` -- `HCParser(cache)`, `ParseWord`, `TraceWordXml`, **all three trace modes of 5.1.1** including the morph-spec -> MSA-HVO resolver mode A needs. **Ships the job runner (5.6)**: states, incremental `run.json`, cancellation, the fast-path window, and `flextools_parse_status`. Ships the `HCParser_DoesNotLoadXCore` standing test; that test **is** the safety story | No |
| **CP3** | in-process read | G4 instrument 2 (the bounded complete parse); `next_step` routing into the CP1 grammar scan. Instrument 3 only if 9.5.6's seam ever appears. Batch + reporting: `UniqueWordforms()` scoping, run artifacts, `parse_log`, `parse_diff`, G3 batch layer + drill-down. Consumes CP2's runner; adds no second execution model | No |
| **CP4** | in-process write | `ParseFiler` with stubs + synchronous `UpdateWordforms` + full ladder (12.4), deletion projection **on 12.2's conjunction**, refuse-to-file gate (12.3). Live verification incl. the `MoveConcAnnotationsToWordform` edge case, the 9.3.4 auto-approval (an in-segment analysis survives a filing pass that a bare-noopinion projection would have condemned), and 12.7's HC-agent lazy-creation question. **First write** | **Yes** |
| **CP5** | sandbox | Hardened `hcparse.ps1` (H1/H4, three lifecycles), `flextools_parse_sandbox`, corpus assertions via `test` with regression/new-ambiguity classification | No |
| **CP6** | -- | Contract codes, CHANGELOG, telemetry, user docs | No |

**CP1's invariant, restated.** Adding the grammar scan means CP1 now opens a
project and reads LCM objects, so "no cache opened" no longer describes it. The
boundary that still holds, and the one that matters, is: **no parser is
constructed, no grammar is loaded into HermitCrab, and nothing is parsed.**
`HCParser` is touched by reflection only, never instantiated. The capability
probe of 5.4 keeps its stricter no-cache property on its own.

All feature **value** lands before any write exists. A negative outcome on the
write path costs CP4 only. With the scan at CP1 the front of that curve gets
steeper still: the cheapest instrument, and the one 9.5.2 makes primary, ships in
the first checkpoint with nothing blocking it.

---

## 16. Test plan

**Unit**
- Genre selection via `GenresRC` finds a text whose matching genre is **second**.
- Diff: every bucket, `only_in_*`, and the `parse_scope_mismatch` refusal.
- Cache key: stability, and change on mtime / generator / script version.
- Error envelopes validate against their detail models (`extra="forbid"`).
- G3 batch signals against a fixture, including each stated false-positive case.
- Oracle wording: the never-reviewed case renders the mandated sentence and
  **never** the words "invalid", "incorrect", "rejected", "flagged".
- **Oracle completeness tiers (9.3.1)**, one fixture per tier: a gloss-only
  analysis (`MorphBundlesOS.Count == 0`), a sketched analysis with a null
  `MorphRA`, and a fully-linked analysis. Assert that only tier 3 enters the
  "human approved N of M" count, that tiers 1 and 2 are reported by name rather
  than dropped or counted as disagreement, and that the tier is derived from
  `IWfiMorphBundle.IsComplete` rather than a reimplemented predicate.
- **Candidate pairing (9.3.2):** one parser analysis plus one human gloss yields
  a pairing ranked first, labelled as a suggestion with its confidence basis
  stated, and **never** auto-filed.
- **Promotion-only ranking (9.3.2)** -- the regression test that matters most
  here. Fixture: a non-compositional word (composed gloss far from the human
  gloss) whose *correct* analysis is the mismatching one. Assert it is NOT
  demoted below a compositional-but-wrong competitor, and that no output renders
  it as less likely. A sort-by-gloss-distance implementation must fail this test.
- **Lexicalization finding (9.3.2):** a word the parser derives whose parts do
  not add up to the recorded meaning is reported as a candidate lexicalized form,
  not as a parse error.
- **Duplicate projection (9.3.3):** a mode-1 confirmation against a fixture
  containing gloss-only analyses reports the duplicate count, not only creations
  and deletions.
- **Approval provenance (9.3.4):** a fixture analysis holding a user-agent
  `approves` **and** occurring in a segment is reported in the separately named
  **indeterminate** population, never folded into a bare human-approved count.
  An implementation that reads the opinion field alone must fail this test.
  Assert the output never labels an individual analysis "tacit", "unreviewed" or
  "auto-approved" -- the join is one-sided and an affirmed approval lands in the
  same bucket.
- **Deletion projection is a conjunction (12.2):** a fixture with two
  parser-created, user-`noopinion` analyses -- one referenced by a segment, one
  not -- projects **exactly one** deletion. A bare-noopinion projection returns
  two and must fail. Pair it with the inverse assertion: the in-segment analysis
  survives an actual filing pass, confirming the shield is real and not merely
  projected.

**flexicon facade (S9, 5.4)**
- `import flexicon` succeeds on a machine with **no** ParserCore present, and
  `project.Parser` reports unavailable rather than raising -- the lazy-import
  guarantee, tested in flexicon, not only here.
- The capability probe runs on flexicon's side too; a flexicon built against an
  incompatible ParserCore degrades to unavailable, never to a partial facade.

**ParserCore capability probe (5.4)**
- A ParserCore resolved from a directory other than the one supplying
  `SIL.LCModel.dll` yields `parser_core_missing` with `signal=foreign_install`.
- A ParserCore missing one bound member yields `signal=incompatible_surface` with
  that member named in `missing_members`.
- An unexpected-but-complete version passes and is **reported**, not refused --
  the regression test against reintroducing a version floor.
- The probe opens no cache and loads no grammar: assert CP1 preflight performs no
  parse and leaves the project untouched.

**HC agent probe (12.7)**
- A project fixture with `ActiveParser == "HC"` and no `kguidAgentHermitCrabParser`
  in `ICmAgentRepository` yields `write: unavailable` with
  `signal=parser_agent_missing` -- and **no `KeyNotFoundException` escapes the
  handler**. That escape is the failure this test exists to catch.
- The same fixture leaves `read: ready` and `flextools_try_word` callable: a
  missing agent never disables read-only diagnosis.
- With no project open, `write.reason` records `agent_probe: "skipped"` and the
  status is decided by the member probe alone -- a skipped probe never reads as
  a pass.

**Proposal review (5.1.3)**
- A decomposition that conflicts with every recorded analysis is still traced
  exactly as supplied; the flag appears beside the result, never instead of it.
- The flag is phrased as an observation -- assert the output never contains
  "incorrect", "wrong", or a confidence score for a caller's proposal.
- A proposal consistent with existing analyses produces **no** flag.
- Regression test for the 9.3.2 inversion: a correct-but-irregular decomposition
  sharing no entry with any recorded analysis is not demoted, reordered, or
  rendered as less likely.

**G4 / grammar health (9.5)**
- `flextools_grammar_health` opens no parser and runs no parse: assert `HCParser`
  is never constructed and the project is untouched.
- A grammar with a null allomorph attachable at any position is reported as a
  **suspect** with its count, never as a defect, and no scalar score appears
  anywhere in the output (9.5.3).
- A `try_word` that misses the fast-path window emits a `next_step` proposing the
  static scan; one that answers inline does **not** -- the proposal is conditional
  (9.5.5).
- `next_step` never names a tool that does not exist, and never a lexicon query
  tool (10.1, 5.1.2).

**Concurrency (12.6)**
- A running parse job does **not** block a lexicon edit or a user-agent analysis
  write; both succeed while the job is mid-run. The regression test against
  reintroducing a project-wide claim.
- A second filing job against a project already filing is refused with
  `parser_filing_in_progress`.
- A result whose referenced morph was deleted mid-run fails `IsValid` and is
  skipped rather than filed; the run reports the skip.
- A single-word request submitted against a running batch is answered without
  waiting for the batch to finish, and the batch resumes at its next word with
  its position and loaded grammar intact.

**Job model (5.6)**
- A parse finishing inside the grace window returns results inline and no
  `run_id` poll is required; one exceeding it returns a `run_id` that polls to a
  terminal state. Same tool, same machinery, both paths.
- A job killed mid-run leaves its completed words readable through `parse_log`
  and a `parser_job_failed` terminal state naming `out_of_memory` or `crashed` --
  partial work is never discarded.
- Cancellation stops at the next word boundary and leaves `cancelled` over the
  partial results.
- `flextools_parse_text(apply=true)` completes confirmation and backup **before**
  a `run_id` is issued; no path exists by which a running job asks for consent.

**Standing guarantees**
- `HCParser_DoesNotLoadXCore` -- isolated process; after a real `Update()` +
  `ParseWord()`, assert no `XCore` / `System.Windows.Forms` assembly is loaded.
  This also empirically closes the residual `DisposableBase` question.
- `ActiveParser` mismatch produces `parser_engine_mismatch`, never a parse.
- A never-parsed project reports the oracle as **absent**, not as all-unreviewed.
- Parseability is never derived from analysis counts (section 3.1).

**Integration (Windows + FieldWorks, no `hc` tool)**
- `flextools_health` reports the sandbox spine unavailable with the real
  `dotnet tool install` hint, while the in-process spines report ready.

**Live (`lex-verification`, HC-configured project)**
- Non-Latin word list round-trips -- the encoding regression in section 4 gets a
  standing test, since its failure mode looks like a grammar problem.
- Baseline parse -> deliberate grammar break -> diff reports `regression` naming
  the right word -> revert -> diff reports `improvement`.
- Deletion projection matches what filing actually deletes.
- Refuse-to-file fires on a deliberately broken grammar load.
- `MoveConcAnnotationsToWordform` edge case: delete an analysis a segment still
  references and observe what LCM's generic cascade does.
- Shared-mode run returns `staleness: "shared_mode_unverifiable"`.

---

## 17. Open questions

1. **`GenerateHCConfig.exe`'s behaviour against the copied project.** A
   FieldWorks binary whose source was not read. It is *pointed at* a copy by
   construction -- an **unverified link, not a demonstrated leak**.
2. **The refuse-to-file gate's baseline comparison** (12.3). **Resolved
   2026-09-15** (domain review, cycle 3): rung 2 is now specified against an
   **MCP-owned baseline** -- the load-error set captured at our own grammar
   load, keyed to `scope_fingerprint` -- never against FLEx's
   `{ProjectName}HCLoadErrors.xml`, which is provenance-blind (no timestamp, no
   grammar hash, no caller identity). Rungs 1, 3 and 4 were already validated;
   the gate is settled except where 12.3 itself flags rung 3's "pre-existing
   errors are benign" as a working hypothesis, not a proven baseline.
3. **Localized genre names.** Matching against the default analysis WS may miss a
   user working in a localized UI.
4. **Non-file-based backends.** Send/Receive or remote-backend projects may need
   a different export path.
5. **Pathological grammars are diagnosed here** (9.5), not deferred upstream --
   this supersedes an earlier note that treated cancellation as the only remedy.
   There is no in-FLEx way to diagnose a parse that never finished or OOMed, so
   deferring would leave the gap open indefinitely. `sillsdev/PanGloss` may grow
   an adaptable parser-health feature and is worth watching, but it is further
   from release than this MCP: convergence, not a dependency. Investigated
   2026-09-15 -- it already has `fst-health`, `make-report`, and three measured
   pathology categories, and 9.5.3 adopts its vocabulary and its interpretation
   discipline. The genuinely open item is narrower and now sharper: **PanGloss can
   count per-object work because it owns its engine; we call C# HermitCrab.**
   Whether per-morpheme counters are obtainable from the C# engine decides
   instrument 3. **Resolved 2026-09-15 by not needing it**: instrument 1 (static
   LCM detection) is now the primary G4 instrument, enriched by PanGloss's
   pathology list translated out of FST-compile terms (9.5.6). Instrument 3 is
   deferred pending a possible `HCParser` seam -- a FieldWorks ask, not a PanGloss
   one. What remains genuinely open is narrower and is a question for Johnml1135:
   **what has PanGloss identified as pathological for a compiled FST**, item by
   item, so each can be mapped onto an LCM check.
6. **Follow-up feature, deliberately out of scope here: completing a gloss-only
   analysis with parser morphology.** Per 9.3.3, filing duplicates rather than
   merges, and the merge is the operation a user actually wants on a Gloss-mode
   project -- it would turn tier-1 records into tier-3 ones and is arguably the
   highest-value write this whole area could offer. It is not reachable through
   `ProcessParse`, so it needs its own write path, its own gates, and its own
   spec. Do not let it accrete into CP4.
7. **`ParserCore.dll` resolution order and its anchoring to `SIL.LCModel.dll`.**
   Outstanding with the parallel parser-health-detection session: 5.4's "same
   install" check assumes a single unambiguous resolution via
   `get_resolved_fieldworks_dir()`, but the detector's own search order has not
   been specified there.
8. **`hc` detection method, and its timeout/failure behaviour.**
   `dotnet tool list -g` is named (13, H1) but the detector's handling of a
   slow or hanging `dotnet` call is not yet specified.
9. **The concrete output shape the detector returns.** 10.2's `ParserDetector`
   interface seam names the fields (`ProbeResult`, etc.); the parallel session
   owns specifying how each is actually populated.
10. **Does anything create the HermitCrab agent outside `SetupAgents`?** (12.7).
    A data migration or a lazy path -- on first HC run from FLEx's Parser menu,
    or on a parser switch -- would downgrade 12.7's refusal to a warning. Source
    reading could not settle it. **Live read-only probe**, against a project
    with `ActiveParser == "HC"` that has never run the parser. Does not block
    CP1: the probe ships either way, and only its verdict wording depends on
    the answer.
11. **`IStText.UniqueWordforms()` on a never-tokenized text.** Does it return
    anything for a text never opened in interlinear? This is 3.1's
    database-state-as-proxy trap one layer down: an empty result would mean "not
    tokenized", not "no words", and CP3's scoping must not read it as the
    latter. Verify before CP3 relies on the count.
12. **Can a segment assignment arrive without a human act?** (9.3.4). FLEx
    propagates guessed analyses through interlinear text; if an analysis can
    reach `AnalysesRS` by being offered and not overruled, part of the
    indeterminate population is weaker than tacit. Verify before CP3 leans on
    the affirmed/indeterminate split. Does not affect the reporting rule, which
    already declines to characterise individual analyses.

---

## 18. Non-goals

- **XAmple.** Out of scope -- and the *reason* matters, because a wrong reason is
  what gets a non-goal casually reversed. It is not "a different parser". It is
  that **XAmple has no external boundary at all**: HermitCrab ships `hc` as a
  dotnet tool with a text-in/text-out contract we can shell to, while
  `XAmpleParser` runs only in-process through native COM interop around
  `xample.dll`. `IParser`-level symmetry hides an entire interop layer.
  (`dataDir` was never the blocker -- it is a cheap static install-relative
  folder.) Revisit only if a wrapper appears. The engine-mismatch **refusal**
  (3.2) ships regardless.
- **The in-GUI FLEx parser service.** We drive ParserCore, not FLEx.
- **Grammar authoring or rule suggestion.** Reporting "`menulis` broke" and
  "rule X is the loose one" is in scope. Editing the rule for the user is not.
- **Cross-platform support.** Windows only.
- **Inferring parseability from stored analyses.** Not merely out of scope --
  forbidden (3.1).
