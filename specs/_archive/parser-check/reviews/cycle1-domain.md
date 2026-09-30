# Domain Review — cycle1: ParseFiler data semantics, FLEx parser modes, G3

> Filed by the orchestrator on the reviewing agent's behalf: the subagent was
> provisioned with Read/Grep/Glob/WebFetch only and had no Write tool. Content
> is the agent's verbatim report.

**Q2 direct answer: NO — ProcessParse cannot silently repaint a user's displayed interlinear text, with one narrow, non-arbitrary exception (deletion of never-reviewed candidates), and that exception is pre-existing FLEx behavior, not something an MCP would add.**

**Q4 direct answer: YES — calling ParseFiler.ProcessParse is FLEx's own menu-driven code path; provenance (parser-agent authorship) is indistinguishable from a human running Tools > Parser from the GUI.**

## Q1 — ProcessParse mechanics

(`ParseFiler.cs:191-245`, `ProcessAnalysis` at `263-298`, `SetUnsuccessfulParseEvals` at `302-320`.)

Filing is a two-phase, both-reuse-and-create process, all inside one `NonUndoableUnitOfWorkHelper.Do` block (`ParseFiler.cs:191`). For each queued wordform:

1. skip if invalid or checksum unchanged (`202-213`);
2. delete any stale parser-agent problem annotations (`219-224`);
3. reset the parser agent's opinion on **every** existing analysis to `noopinion` (`226-227`) — a blanket reset, done before anything else;
4. for each analysis the fresh parse produced, `ProcessAnalysis` looks for an existing `IWfiAnalysis` whose morph bundles match (`MatchesIWfiAnalysis`, `ParseResult.cs:102-133`); if found it reuses it, if not it creates a new `IWfiAnalysis` + `IWfiMorphBundle`s (`ParseFiler.cs:274-293`), then sets `m_parserAgent.SetEvaluation(match, Opinions.approves)` (`297`).

So: **both** — reuse when the morph-bundle signature matches, create otherwise. Analyses the parser no longer produces are **never deleted directly by the parser's disagreement** — they are only re-opined (parser noopinion) via step 3; deletion only happens later, conditionally (see Q2). A human-approved analysis the parser disagrees with is **untouched at the user-agent level**: `SetEvaluation` for the user agent is called only once in this whole class, at `311`, and only to *approve* (never to disapprove or clear) an analysis that a segment currently displays. The parser can never overwrite or clear a user's approval.

## Q2 — pollution risk, in depth

`SetUnsuccessfulParseEvals` (`302-320`) is the only place that touches display-relevant state or deletes anything. It first re-affirms `m_userAgent.SetEvaluation(analysis, approves)` for any analysis currently referenced by a segment (`305-311`) — protective, not destructive. Then, per remaining analysis: if the parser now has `noopinion` on it (i.e. this parse run didn't reconfirm it) **and** the user also has `noopinion` (never reviewed) → `analysis.Delete()` (`314-315`). Only in that double-noopinion case is anything removed. If the user has any opinion at all (approve or disapprove), the analysis survives with `disapproves` from the parser instead (`316-317`).

**Crucially, `ProcessParse` never writes to `ISegment.AnalysesRS`** — nothing in `ParseFiler.cs` assigns what a segment displays. So a currently-displayed, human-reviewed analysis cannot be silently swapped out.

The one loose end: deleting a never-reviewed `IWfiAnalysis` that happens to still be referenced by a segment relies on LCM's generic reference-cleanup on `Delete()`. The domain model has an explicit `MoveConcAnnotationsToWordform` helper (`OverridesLing_Wfi.cs:1325-1337`) built for exactly this "retarget the segment to the bare wordform before deleting" scenario, but `ParseFiler`'s delete call does **not** invoke it. I could not confirm from these files what the generic cascade does in that edge case — flagging as open, but note it is identical for MCP and for a human clicking "Parse Words in Text" (`ParserListener.cs:521-533`, same `UniqueWordforms()`→`ProcessParse` path), so it is a pre-existing FLEx risk, not one an MCP integration introduces.

## Q3 — non-undoable, confirmed

`NonUndoableUnitOfWorkHelper` runs the task on `UowService.NonUndoableStack`, not the regular undo stack (`NonUndoableUnitOfWorkHelper.cs:34-45`, `129-136`). There is no "Undo" for a parse pass in FLEx's UI. A pre-write backup (or re-running the previous parser version) is the only recovery path.

## Q4 — provenance

`ParserListener.OnParseWordsInCurrentText` (`521-533`) and `OnCheckParserOnCurrentText` (`569-580`) call the identical `ParserConnection→ParserScheduler→ParserWorker→ParseFiler.ProcessParse` chain we'd drive in-process. Evaluations are stamped by `m_parserAgent` (XAmple or HermitCrab `CmAgent`, `ParserWorker.cs:64-77`), so a human reopening FLEx sees parser-authored analyses exactly as if run from the menu.

## Q5 — scope input

Mode 1 input is `IStText.UniqueWordforms()` (`StText.cs:654-661`), a per-paragraph/segment wordform collector **already owned by LCM**. `ParserListener.cs` uses it for the current text (`528`), unions it across a genre's texts (`609-613`) or all texts (`650-654`), and for "unapproved only" walks `seg.AnalysesRS` directly (`549-566`).

**A custom interlinear-walk word-list builder is not needed for mode 1** (or 3b, which reuses the same path). It may still be needed for tooling that must report per-occurrence context, but not to gather the parse target list.

## Q6 — G3 inputs

**(a) `IsValid` is a staleness guard, not a linguistic judgment.** `ParseResult.IsValid` / `ParseAnalysis.IsValid` / `ParseMorph.IsValid` (`ParseResult.cs:46-49, 86-89, 199-202`) check `IsValidObject` on the referenced `Form`/`Msa`/`InflType` — i.e. "do these DB objects still exist." It answers none of G3's "why too many/invalid parses" concern.

**(b) `selectTraceMorphs` is a PRE-parse filter, not retroactive attribution.** (`HCParser.cs:186-200`) It restricts `LexEntrySelector`/`RuleSelector` to a caller-supplied MSA-id set *before* parsing runs; it narrows the search space, it does not explain which rule licensed an already-produced analysis. That explanation lives in the `<Trace>` element built from the Morpher's `trace` out-param (`178-218`), available only via `TryAWord`/`TraceWordXml`, **one word at a time**.

**(c) Human approvals are a real but partial oracle.** `GetAgentOpinion(m_userAgent)==approves` is a genuine per-wordform gold signal, but silence (`noopinion`) means "never reviewed," not "wrong," and it only covers analyses whose exact morph-bundle signature was already materialized in the DB — a parser proposal with a genuinely new combination has no gold counterpart. "Parser proposes 6, human approved 1, here are the other 5" is sound only for wordforms that have at least one reviewed analysis; for the (likely majority of) unreviewed wordforms it degrades to "parser proposes 6, nobody has judged any of them."
