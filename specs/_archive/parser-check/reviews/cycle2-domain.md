# G3 Design: Overgeneration ("why does my grammar allow too many/invalid parses")

> Filed by the orchestrator on the reviewing agent's behalf: the subagent was
> provisioned with Read/Grep/Glob/WebFetch only and had no Write tool. Content
> is the agent's verbatim report.

## 1. Batch layer (cheap, whole-run, no tracing)

Everything here comes from `ParseResult.Analyses` / `ParseAnalysis.Morphs` / `ParseMorph` (ParseResult.cs:72-227) after a plain `ParseWord` call over a wordlist — no `TraceWordXml`, no per-word cost.

- **Analysis count per word.** Trivial: `len(result.Analyses)`. Tell the linguist "word X has N candidate parses." **False-positive mode: high count is not a bug.** Many languages have real, productive ambiguity (agglutinative morphology, homographic affixes, compounding). This signal is a *worklist prioritizer*, never a verdict.
- **Root-entry disagreement.** For each word, look at the `ParseMorph` whose `Form.MorphTypeRA` is a stem/root type; if analyses disagree on which `ILexEntry` (via `Form.Owner`) supplies the root, flag it. Tells the linguist "this surface form is being derived from two unrelated headwords" — often a real overgeneration bug (a spurious affix rule is stripping material that shouldn't be strippable, exposing a different root). False positive: legitimate root-level homographs (two real lexemes that happen to share a stem) will also trigger this.
- **Root analysed as an affix stack.** Compare, across analyses of the same word, whether the same headword sometimes appears as the sole stem morph and sometimes only as part of a longer morph chain built entirely from affix/clitic `MoForm`s with no stem morph at all (i.e., one analysis has 1 morph, another has 4+, both for the same surface string). Flags rules matching on features so loose they can synthesize a whole word from affixes alone. False positive: real zero-derivation / cliticization patterns.
- **Same surface, incompatible MSA/category.** Group by wordform; for each analysis look at `Msa` (IMoMorphSynAnalysis, resolvable to `PartOfSpeechRA` etc. via LibLCM). Flag wordforms whose analyses span incompatible categories (e.g. one parse Noun, one parse Verb) with no derivational MSA (`IMoDerivAffMsa`) connecting them. Tells the linguist "grammar treats one surface form as two unrelated categories with no derivation licensing the jump." False positive: genuine cross-category homographs.
- **Distribution shape across the corpus.** A histogram of analysis-count per word (median, p90, max) is a cheap regression detector: re-run after a rule edit, diff the histogram. A rightward shift is evidence *something* got looser, even before any single word is inspected.

None of these signals use `IsValid` (established in cycle 1 as LCM liveness only, ParseResult.cs:199-202) — they are all derived from the typed `Form`/`Msa`/`InflType` references, which is the only rich data the batch layer has.

## 2. Drill-down layer (per word, `TraceWordXml`)

`TraceWordXml` (HCParser.cs:120-125, 178-228) sets `IsTracing = true` and, per FwXmlTraceManager.cs, the returned `<Trace>` records the **entire search**, not just the winner: `MorphologicalRuleApplied`/`PhonologicalRuleApplied`/`Successful` for accepted steps, and typed `FailureReason` (`RequiredSyntacticFeatureStruct`, `RequiredMprFeatures`, `Pattern`/environment, `MaxApplicationCount`, `AllomorphCoOccurrenceRules`, etc.) for rejected ones.

**Yes** — the successful-chain portion of the trace is exactly the attribution G3 needs: for each accepted analysis, the sequence of `MorphologicalRuleApplied`/rule-name + `LexEntry` nodes tells you precisely which morphological rule(s), which lexical entry allomorphs, and which stratum/template licensed that surface form. Present it per-analysis as a rule-chain: `entry → rule₁ (stratum, slot) → rule₂ → ... → surface`. When comparing N analyses of one word side-by-side, the linguist can visually spot the *shared* rule that appears in the chain of every "should not have parsed" analysis — that shared rule is the overgeneration candidate. The rejected-branch `FailureReason` nodes are secondary here (they matter for G1/G2, "why did a *desired* form fail") but are useful in G3 as a sanity check: if a rule *almost* rejected a bad analysis (a `FailureReason` was raised and then overridden by a broader alternative allomorph), that alternative allomorph is the loose one, not the rule itself.

## 3. The oracle

Sound framing: **"The parser proposes 6 analyses for this word. 1 has been reviewed and approved by a human. The other 5 have never been reviewed."** This is sound whenever the exact morph-bundle signature already exists as an `IWfiAnalysis` with `GetAgentOpinion(userAgent)` resolvable (ParseResult.cs:102-133 `MatchesIWfiAnalysis`). It degrades to nothing for any analysis that has never been materialized in the DB (never occurred in a text, never manually disambiguated) — there `GetAgentOpinion` simply has no row to query, and the tool must not silently treat "no row" as "no opinion == disapproved."

**Exact output wording, mandatory:**
- Approved: `"Approved by [user] on [date]."`
- Explicitly disapproved: `"Marked incorrect by [user] on [date]."`
- No stored opinion: `"Not yet reviewed by a human — this is not evidence it is wrong, only that nobody has checked it."` **Never** render this case as "invalid," "incorrect," "rejected," or "flagged" — those words claim a verdict that does not exist.

## 4. Workflow

1. **(sandbox)** Batch-parse the corpus/wordlist against the current grammar (live or exported) and compute the count/root-disagreement/category-clash signals from §1.
2. **(sandbox)** Linguist reviews the ranked worklist, picks a handful of suspicious words (not all — see §5).
3. **(sandbox)** Run `TraceWordXml` on each picked word; compare rule chains across its analyses; identify the shared/loose rule or allomorph.
4. **(sandbox)** Cross-reference with the oracle (§3) for any analyses already materialized, to see whether a human already rejected one of the offending analyses — this is corroborating evidence, not proof.
5. **(sandbox)** Linguist edits the exported grammar snapshot (tighten the environment/feature/MPR-feature restriction on the identified rule), re-runs step 1 on the same wordlist, confirms the count/disagreement signals shrink and no previously-good word broke.
6. **(go live)** Only after the sandbox re-run is clean does the linguist apply the same edit to the live grammar via FLEx. Nothing in steps 1-5 ever touches the live project.

Step 3's side-by-side rule-chain comparison view does not exist yet as a tool feature — currently `TraceWordXml` returns raw XML for one word; a diff/comparison presentation across a word's own analyses would need to be built.

## 5. Cost and caps

Tracing is one word at a time and expensive; recommend: default drill-down cap of **10-20 words per session**, chosen by the linguist from the batch worklist, never auto-traced in bulk. If 400 words look overgenerating, the tool should **not** trace all 400. Instead: report the batch-level histogram/signal summary, cluster flagged words by shared root entry or shared category pair (since a single loose rule typically produces a cluster, not 400 independent problems), and recommend tracing 1-3 representative words per cluster. State explicitly: "400 flagged words likely share a small number of root causes; trace representative samples, not the whole set."

## P0: loader cleanliness signal

`HCLoader.Load` (HCLoader.cs:30-35) always returns a `Language` object; the ten `IHCLoadErrorLogger` callbacks (IHCLoadErrorLogger.cs:7-16) are pure advisory logging — none of them abort the load, none carry a severity level, and there is **no boolean/success return value**. In `HCParser.LoadParser` (HCParser.cs:144-176), the logger writes to a per-project temp file (`{ProjectName}HCLoadErrors.xml`, line 152) that is overwritten on every load and never returned to any caller — it is a side-effect dump, not part of `ParseResult` or any typed API surface. The load call itself (line 157) is **not** wrapped in try/catch inside `HCParser` (unlike `ParseWord`, lines 92-99), so a genuine C# exception during `LoadLanguage()` propagates out of `Update()` uncaught by this class.

So there is exactly one clean, binary signal, and it is coarse: **did `Update()`/`LoadParser()` throw, leaving `m_morpher == null`** (checked before every parse/trace call, HCParser.cs:88-89, 180-181)? That distinguishes "hard failure" from "loaded." It does **not** distinguish "loaded cleanly" from "loaded but silently dropped/excluded entries or rules" (e.g. `AddEntry`, HCLoader.cs:681-689, only adds an entry if `hcEntry.Allomorphs.Count > 0` — entries whose every allomorph failed via `InvalidShape` are silently excluded from the grammar with no severity flag beyond a `LoadError` XML row).

**Recommendation for the filing gate**: treat "any `<LoadError>` element present in that XML file" OR "`m_morpher == null` after `Update()`" as non-clean, and refuse to file in either case, since the loader itself provides no gradation between "cosmetic warning" and "silently shrank the grammar." This requires the MCP integration to read the LoadErrors.xml side file after triggering a load — it is not currently exposed through any return value the MCP could otherwise consume.
