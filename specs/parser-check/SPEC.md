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
| 2. Try a word | Cannot add analyses; hypothesis testing | in-process **read** |
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
- **S9. Placement is split** (decided 2026-09-15): a thin read-only
  `project.Parser` facade ships in **flexicon**; filing plus the
  confirmation/backup ladder stays in **FlexToolsMCP**. See section 5.4.

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
nothing to G3 and must never be presented as a validity verdict.

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

Two costs to carry:

- **Import must be lazy.** A future FieldWorks that renames or relocates
  `ParserCore.dll` must degrade to "parser unavailable", never break
  `import flexicon` for users of unrelated features.
- **The version gate follows the code.** ParserCore is versioned independently of
  `SIL.LCModel` and needs its **own** gate, in flexicon as well as the MCP. The
  MCP's index is liblcm `v11.0.0` while the install is FieldWorks 9; nothing may
  assume those numbers track each other.
- Companion ask in the same cross-repo change: a `Texts.GetGenres()` wrapper.
  `IText.GenresRC` is currently raw-LCM-only (section 6.1).

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
parse the batch untraced, then trace the specific words the user drills into.
The old "two-pass trace" design was an artifact of the CLI spine and applies only
there.

Caps (section 9.3) apply to both.

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

`selectTraceMorphs` is a **pre-parse filter** (`HCParser.cs:186-200`) restricting
the search space before parsing. It does **not** attribute an already-produced
analysis to a rule; do not design against it as if it did.

### 9.3 The oracle, and its mandatory wording

The project's human-approved analyses are a real but partial gold standard. It is
sound only where the exact morph-bundle signature already exists as an
`IWfiAnalysis`; for an analysis never materialized in the DB there is simply no
row to query.

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

**Project-state precondition:** on a project never parsed live, the oracle is not
degraded, it is **absent**. The tool must say so -- "this project has no
parser-created analyses, so no approval comparison is possible" -- rather than
emit a report in which every analysis reads as unreviewed. Silently producing a
degenerate report is how a user concludes their grammar is bad when the truth is
nobody ever ran the parser.

**Mandatory output wording:**

- Approved (tier 3): `"Approved by [user] on [date]."`
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

### 9.4 Cost

Default drill-down cap 10-20 words per session, chosen by the user, never
auto-traced in bulk. When 400 words look overgenerating, do **not** trace 400:
report the batch summary, cluster by shared root entry or category pair (a single
loose rule produces a cluster, not 400 independent problems), and recommend
tracing 1-3 representatives per cluster.

---

## 10. Tools

Named per spine. **The spine is stated in the first line of each tool
description** -- a calling model reads descriptions, not annotation bits.

| Tool | Spine | Annotation | Purpose |
|---|---|---|---|
| `flextools_try_word` | in-process read | `READ_ONLY_SAFE` | "in-process, live DB, read-only, cannot add analyses" |
| `flextools_parse_text` | in-process write | `readOnlyHint=False, destructiveHint=True` | "in-process, live DB, WRITES on apply=True, non-undoable, ladder-gated" |
| `flextools_parse_sandbox` | sandbox | `READ_ONLY_SAFE` w.r.t. the live DB | "exported/copied grammar, never touches the live DB, speculative edits welcome" |
| `flextools_parse_diff` | consumer | `READ_ONLY_SAFE` | Before/after over run artifacts |
| `flextools_parse_log` | consumer | `READ_ONLY_SAFE` | Read run artifacts |
| `flextools_health` (parser block) | -- | `READ_ONLY_SAFE` | Preflight for all three spines |

`flextools_parse_text` takes `apply` (default `false`) and echoes `applied: true/false`.

**Why a capability split rather than one tool with a flag.** Annotations declare
a tool's *maximum reachable capability*, evaluated before any argument is known.
`try_word`'s call path structurally cannot reach `ParseFiler` or xCore, so it
earns `READ_ONLY_SAFE` on its own facts. Tagging it destructive would *overstate*
and throttle the low-friction hypothesis-testing loop the gradient exists to
enable. `parse_text` reuses `run_module`'s existing ladder verbatim rather than
inventing a parallel gate.

The sandbox tool's risk register is **disk and subprocess** (project copy,
`dotnet` timeout), not the LCM write surface.

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

What the user never sees changed: `ProcessParse` never writes `ISegment.AnalysesRS`,
and the user agent's `SetEvaluation` is called in exactly one place and only to
**approve**. The parser cannot overwrite a human's approval.

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

**Proposed gate (needs validation before it becomes final):**

1. `m_morpher == null` after `Update()` -> **hard refuse**, no override.
2. **New** `<LoadError>` entries relative to the baseline parse -> refuse by
   default. This is the "your edit broke the grammar" case, precisely the one
   that deletes data.
3. Pre-existing load errors -> warn, surface the count, carry it into the
   confirmation.
4. Confirmation projects **deletions**, not only creations.

A blunt any-error gate would make mode 1 permanently unusable on projects with
benign pre-existing errors, and would invite exactly the bypass flag we must not
build. The gate must read the side file; that is ugly and unavoidable.

### 12.4 The write ladder

`flextools_parse_text(apply=true)` passes the **same** ladder as `run_module`:
session `write_enabled`, `require_write_confirmation` (first call returns
`confirmation_required` with the mutation plan; resubmit needs `confirmed=True`),
`perform_pre_write_backup` before the first mutating parse per (session, project),
and the existing `needs_lock` machinery.

**Backup is mandatory here, not best-effort** -- filing is non-undoable, so it is
the only recovery.

**No unattended batch parse.** `require_write_confirmation` defaults on and
nothing in this feature may introduce a bypass flag; that would recreate the
audited hole where `confirmed` is asserted by the model and never verified as
human assent.

### 12.5 General

- Subprocess work reuses `run_script_async` (`taskkill /T /F` on Windows --
  necessary because `dotnet` spawns grandchildren).
- No `Invoke-Expression`; word data reaches PowerShell only through a file.
- Words and parser output are **data, never instructions**.

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
| `parser_core_missing` | `expected_path`, `detected_version`, `required_version`, `install_hint` |
| `grammar_load_unclean` | `signal` (`morpher_null` \| `new_load_errors`), `new_error_count`, `baseline_error_count`, `log_path` |
| `parser_tool_missing` | `component`, `expected_path`, `install_hint` |
| `parser_config_failed` | `exit_code`, `stderr_tail`, `log_path`, `run_id` |
| `parser_timeout` | `timeout_seconds`, `words_completed`, `run_id`, `hint` |
| `parse_scope_empty` | `scope`, `matched_texts`, `hint` |
| `parse_scope_ambiguous` | `scope`, `requested`, `candidates` |
| `parse_scope_mismatch` | `baseline_fingerprint`, `current_fingerprint`, `differing_fields`, `hint` |
| `parse_run_not_found` | `run_id`, `available_runs` |

Reused: `project_not_found`, `project_locked`, `project_drive_unavailable`,
`project_path_mismatch`.

---

## 15. Checkpoints

| CP | Spine | Deliverable | Writes? |
|---|---|---|---|
| **CP1** | -- | Preflight/health for all three spines: `ParserCore.dll` + its own version gate; `ActiveParser` read and `parser_engine_mismatch` refusal; `hc` located via `dotnet tool list -g`; `GenerateHCConfig.exe`. No parsing | No |
| **CP2** | in-process read | `flextools_try_word` -- `HCParser(cache)`, `ParseWord`, `TraceWordXml`. Ships the `HCParser_DoesNotLoadXCore` standing test; that test **is** the safety story | No |
| **CP3** | in-process read | Batch + reporting: `UniqueWordforms()` scoping, run artifacts, `parse_log`, `parse_diff`, G3 batch layer + drill-down | No |
| **CP4** | in-process write | `ParseFiler` with stubs + synchronous `UpdateWordforms` + full ladder (12.4), deletion projection, refuse-to-file gate (12.3). Live verification incl. the `MoveConcAnnotationsToWordform` edge case. **First write** | **Yes** |
| **CP5** | sandbox | Hardened `hcparse.ps1` (H1/H4, three lifecycles), `flextools_parse_sandbox`, corpus assertions via `test` with regression/new-ambiguity classification | No |
| **CP6** | -- | Contract codes, CHANGELOG, telemetry, user docs | No |

All feature **value** lands before any write exists. A negative outcome on the
write path costs CP4 only.

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
2. **The refuse-to-file gate's baseline comparison** (12.3) needs validation
   before it becomes final.
3. **Localized genre names.** Matching against the default analysis WS may miss a
   user working in a localized UI.
4. **Non-file-based backends.** Send/Receive or remote-backend projects may need
   a different export path.
5. **Cross-repo:** flexicon's maintainers may decline a FieldWorks-parser
   dependency. No advisory lock is in force, so it is unblocked, but the
   dependency is a negotiation, not a technical finding.

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
