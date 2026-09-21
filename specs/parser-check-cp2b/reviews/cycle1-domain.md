# Cycle 1 Domain Review — parser levels: explain/restricted honesty gap

## Q1 — Verdict: **(b), derive from the trace document. Reliable; confirmed by source, no live probe needed.**

`TraceWordXml` and `ParseWordXml` are the same C# method: both call `ParseToXml(form, tracing, selectTraceMorphs)` (`HCParser.cs:120-131`), which builds one `<Wordform>` document (`:178,207`) from `m_morpher.ParseWord(form, out trace, ...)` (`:211`) and appends an `<Analysis>` child per surviving analysis (`:213-215`) — regardless of the `tracing` bool. `tracing=true` only adds one extra sibling `<Trace>` element (`:217-218`) holding explored/rejected paths; rejected paths are never promoted into `<Analysis>`. `FormatHCTrace.xsl` corroborates this is the field FieldWorks itself already treats as the success marker: `:194` tests `/Wordform/Analysis` to render "parsed successfully" vs. `:210-212` for failure, and `ShowSuccessfulAnalyses` (`:1199-1204`) iterates that same node set. So `len(doc.Root.findall("Analysis"))` on the `explain`/`restricted` trace document is *identical* to what `ParseWord`'s own `Analyses.Count` reports — not an approximation. Option (a) buys nothing and costs a redundant parse.

## Q2 — Verdict: **Yes, a bare `ParseWord` answers a different question. Report `hypothesis_held` (bool), not `parsed`/`analysis_count`.**

`ParseToXml` installs `LexEntrySelector`/`RuleSelector` closures from `selectTraceMorphs` *before* calling `m_morpher.ParseWord(...)` (`HCParser.cs:186-199,211`) — a real narrowing of the search space, not a post-hoc filter on trace output. The `<Analysis>` elements a restricted trace returns are already scoped to the hypothesis; their presence answers "does my restriction still admit an analysis," never "does this word parse at all." Naming that field `parsed`/`analysis_count` — the same names `plain` uses for the unrestricted question — would let a caller compare a restricted `false` against a genuine unrestricted failure as if they meant the same thing. Recommended fields: `hypothesis_held: bool` and, optionally, `restricted_analysis_count: int` (count of `<Analysis>` survivors under the given restriction) — names that say only what was tested.

## Q3 — Verdict: **Safe** (mechanically — no corruption), but composing restricted + a second call is still the wrong move per Q2, not because state leaks.

Two independent resets already guard this, both acting at the *start* of the next call rather than trusting the prior call to clean up:
1. `HCParser.cs:178,186-205` — every `ParseToXml` call sets `LexEntrySelector`/`RuleSelector` fresh from its **own** `selectTraceMorphs` argument (open if `None`, narrowed otherwise), so no call can inherit a previous call's restriction.
2. `ParserOperations.py:481` — the Python facade's public `ParseWord` calls `_ClearAnyRestriction` (`:750-779`) first, which reissues an unrestricted `ParseWordXml` if `self._restricted` is still `True`, before calling `handle.ParseWord`.

So a second facade call cannot observe or corrupt restriction state left by the first. The cost, if the second call is `ParseWord` after a restricted trace, is one extra parse (paid inside `_ClearAnyRestriction`) plus — per Q2 — an answer to the wrong question.

## Q4 — Verdict: **Stays inside all three controls; does not disturb control 2.**

Control 1 (`tools.md:16-20`) is about which *members* the facade binds, frozen by `REQUIRED_MEMBERS` (`ParserOperations.py:58-66`); a second call reuses an already-whitelisted member, adding none. Control 2 (`tools.md:21-27`, `HCParser_DoesNotLoadXCore`, `tests/test_parser_no_xcore.py`) is asserted on the worker's assembly *delta*; `ParseWord`, `ParseWordXml`, `TraceWordXml` all live on one `HCParser` instance inside `ParserCore.dll` (`HCParser.cs:120-132`) and never touch `ParserWorker`/`ParserScheduler` — the classes `tools.md:26` names as the actual xCore carriers. A second call among these three loads nothing new, so the forbidden list (`test_parser_no_xcore.py:114-119`) is unaffected. Control 3 (`writeEnabled=False`) is a project-open-time setting, untouched by call count. Caveat: `test_HCParser_DoesNotLoadXCore` currently only exercises `level="plain"` (one call, `test_parser_no_xcore.py:148-154`); this verdict is reasoned from source, not re-verified live for two-calls-per-request.

## RECOMMENDATION

**explain**: implement (b) in `worker_main.py`'s `parse()` (currently `:730-732`) — after `trace = parser.TraceWordXml(wordform, None)`, derive `parsed`/`analysis_count` from that same `XDocument` *before* `_as_text` (`:739-751`) discards structure, by counting `trace.Root.findall("Analysis")` (root is `<Wordform>`, per `HCParser.cs:207`). No second facade call. Factor this into a `_summarize_trace(trace)` helper alongside `_summarize_plain` (`:754-785`).

**restricted**: reuse `_summarize_trace` for the count, but surface it under **new field names** — `hypothesis_held: bool` (and optionally `restricted_analysis_count: int`) — never `parsed`/`analysis_count`. This is a naming/handler change in `handlers/parse.py`'s `_inline_response` (`:535-554`), not a new parser call, so the Q3 hazard never arises for this recommendation in practice. Do not add a second facade call for either level: unnecessary per Q1, and for restricted it would answer the wrong question per Q2 even though Q3 shows it wouldn't corrupt state.
