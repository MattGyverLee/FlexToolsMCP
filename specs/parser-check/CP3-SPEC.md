# CP3 -- parser-check: the corpus, the artifact, and the diagnosis

**Parent spec:** [`SPEC.md`](./SPEC.md) (2252 lines) -- this document does not
restate it. Section references like "9.3.1" point there unless marked local.
**Scope:** SPEC 15, CP3 row.
**Status:** draft, not reviewed by the crew, not started.
**Predecessor:** CP2. **CP2 is not finished** -- see section 2, which is a real
gate rather than a formality.
**Writes:** none. CP3 is entirely `READ_ONLY_SAFE` in effect; filing arrives at
CP4. Section 4.1 explains why one CP3 tool nevertheless ships carrying CP4's
annotation.

---

## 1. What CP3 is

CP1 proved the parser was reachable without constructing one. CP2 constructed
one and answered a single word. **CP3 is the first checkpoint that answers a
question about a whole project**, and the first that leaves something behind:
a durable run artifact other tools read.

Six deliverables:

| # | Deliverable | SPEC | Why it is here |
|---|---|---|---|
| **A** | Scope resolution -- `UniqueWordforms()`, genre -> text via `GenresRC`, and the `scope_fingerprint` | 6, 11 | Nothing batch can start until "which words" has one answer |
| **B** | `flextools_parse_text` (batch, read-only at CP3) + the in-process run artifact set | 5.5, 10 | The first job that is not one word |
| **C** | `flextools_parse_log` | 8.3 | An artifact nobody can read is not an artifact |
| **D** | `flextools_parse_diff` | 11 | The before/after that makes a grammar edit measurable |
| **E** | G3 -- batch signals, the oracle and its tiering, and the per-word drill-down | 9.1, 9.2, 9.3 | The largest and most correctness-sensitive part of this checkpoint |
| **F** | G4 instrument 2 (the bounded complete parse) + `next_step` routing into CP1's grammar scan | 9.5.2, 9.5.5, 10.1 | Closes the loop CP1 opened with a tool that had no caller |

**CP3 consumes CP2's runner and adds no second execution model.** SPEC 5.6 is
explicit about this and CP2's own risk register names the temptation by name. A
batch is the runner's `Medium`/`Low` priority path with per-wordform enqueue
granularity -- it is not a new mechanism, and a CP3 implementation that grows one
should fail review on that ground alone.

### 1.1 What CP3 is not

- **Not a write.** No `ParseFiler`, no `ProcessParse`, no ladder, no deletion
  projection, no duplicate projection. CP4. CP3 *builds the joins* CP4's
  projections need (section 7.6) but never acts on them.
- **Not the sandbox.** `hcparse.ps1` hardening, `flextools_parse_sandbox`, the
  config cache of SPEC 7 and the corpus `test` assertions are CP5. CP3's run
  artifacts are the in-process subset only (4.2).
- **Not instrument 3.** SPEC 9.5.6 defers the counting `ITraceManager` pending a
  `HCParser` seam that does not exist. CP3 must not reflect into `m_morpher` and
  must not plan around the seam appearing.
- **Not grammar authoring.** SPEC 18 stands: naming the loose rule is in scope,
  editing it is not.
- **Not a scalar grammar score.** SPEC 9.5.3's measured anti-correlation result
  forbids it, and CP1 already shipped `flextools_grammar_health` with no
  severity and no verdict wording. CP3's G3 report inherits that discipline.

---

## 2. Entry gate -- CP2 is half done, and this half is load-bearing

**CP2a is complete; CP2b has not started.** The summary "CP1 and CP2 are done" is
true of CP1 and of CP2's flexicon half only. What remains is not cleanup -- it is
both MCP tools CP3 is built on top of.

Verified 2026-09-19 against the working trees:

| Item | CP2 ref | State |
|---|---|---|
| A1 flexicon `project.Parser` facade + 3 read gaps | 3.1-3.2 | **Done.** `flexicon/code/Parser/ParserOperations.py`, merged at `bc65a7b` |
| A2 flexicon 4.9.0 release cut | 3.5 | **Cut, not tagged.** Release commit `296f3b5`; tagging is a maintainer act (escalation E-C) |
| A3 evidence artifact (tiers A1-A3) | 3.3 | **Done.** `specs/parser-check-cp2/evidence/` |
| A4 MCP bridge | 2 | **NOT DONE.** `pyproject.toml:54` and `requirements.txt:21` still pin `pyflexicon>=4.8.0,<5`; the bundled index is still `flexicon_api_v4.8.0.json` / `flexicon_lcm_bridge_v4.8.0.json`. Deferred to CP2b with `needs_human` (escalation E-D) |
| B `flextools_try_word` | 4 | **NOT STARTED** |
| C job runner + `flextools_parse_status` | 5 | **NOT STARTED** |

**Consequences for CP3, stated plainly:**

1. **CP3 cannot start implementation.** A, B, D, E and F all call the runner or
   the facade. This document is written now so that CP2b is built against a known
   consumer rather than guessed at -- that is its whole value before the gate
   lifts.
2. **One CP2 open question is already answered and should be closed rather than
   re-litigated.** CP2's open question 2 asked how much of `ParseResult` crosses
   into Python, and noted that 9.3.1 and 11 need LCM **object identity**, not
   strings. The shipped facade answers it: `ParserOperations.ParseWord` returns
   the parser's own `ParseResult` whose analyses carry **live references** to
   `IMoForm` / `IMoMorphSynAnalysis` / `ILexEntryInflType`, while `ParseWordXml`
   and `TraceWordXml` return documents in which those objects survive only as
   integer identifiers. **CP3's G3 and diff bind to `ParseWord`, never to the
   XML**, and that is now a fact about shipped code rather than a request.
3. **The floor/index mismatch in A4 is a CP3 hazard, not only a CP2 chore.**
   CLAUDE.md records the 2.10.0 incident -- an index built at 4.5.2 shipped
   against a `>=4.3.0` floor. CP3 generates modules that call `project.Parser`;
   if the index does not know the facade exists, every generated CP3 module is
   written against an API the index cannot describe. A4 ships with a
   floor/index-equality test or CP3 inherits the same class of failure.

**Recommended sequencing:** finish CP2b (A4 -> B -> C) and only then open CP3's
Phase 0. Do not interleave -- CP3's Phase 0 is live verification, and live
verification against a half-built runner produces evidence about nothing.

---

## 3. Phase 0 -- two live questions SPEC says to settle *before* CP3 relies on them

These are not open questions to carry. SPEC 17.11 and 17.12 each end with the
words "before CP3", and each guards a specific CP3 computation against producing
a confident wrong answer. They are read-only probes, cheap, and they come first.

### 3.1 `UniqueWordforms()` on a never-tokenized text (SPEC 17.11)

**The question.** Does `IStText.UniqueWordforms()` return anything for a text
never opened in interlinear?

**Why it blocks Part A.** This is SPEC 3.1's forbidden inference one layer down.
An empty result means *"not tokenized"*, and CP3's scoping must not read it as
*"no words"*. If the two are indistinguishable at the API, then:

- `parse_scope_empty` is the **wrong** refusal for an untokenized text -- it
  asserts the text has no words, which is a claim about content, when the truth
  is a claim about state.
- The scoping layer needs a distinguishing read (a paragraph or segment count on
  `IStText` that is non-zero while `UniqueWordforms()` is empty) and a **separate
  message** saying the text has never been tokenized and what to do about it.

**Probe:** read-only, on a project with at least one text never opened in
interlinear. Record paragraph count, segment count and `UniqueWordforms()` count
side by side.

**If it cannot be settled:** Part A ships the distinguishing read anyway and
words the refusal conservatively. Guessing in the other direction -- treating
empty as empty -- is the failure this open question exists to prevent.

### 3.2 Can a segment assignment arrive without a human act? (SPEC 17.12)

**The question.** FLEx propagates guessed analyses through interlinear text. Can
an analysis reach `AnalysesRS` by being *offered and not overruled* rather than
chosen?

**Why it blocks Part E.** 9.3.4's `{affirmed, indeterminate}` split is computed
by joining against segment occurrence. If part of the indeterminate population
arrived without any human act at all, that population is weaker than tacit, and
the report's own description of what it contains changes.

**What does NOT change either way:** the mandatory reporting rule. 9.3.4 already
refuses to characterise individual analyses, and a yes answer only makes that
refusal more clearly right. So this probe **tunes wording, it does not gate the
join**. Part E may be built while it is outstanding; it may not **ship** its
oracle wording until the answer is in the report.

**Probe:** read-only, on a project with interlinear work done. Look for an
analysis in `AnalysesRS` carrying no user evaluation at all and no evidence of
selection.

### 3.3 The project-state probe CP1 already identified

CP1's handoff records that **one** read-only project-state probe serves three
requirements: the never-parsed warning, the oracle precondition (9.3.3), and the
deletion-projection precondition (12.2). CP3 is the first checkpoint that needs
two of the three. Build it once, here, and let CP4 consume it -- do not let CP4
grow a second one.

---

## 4. Part B first, structurally -- the artifact is the contract

Parts C, D and E all read the run artifact. Its shape therefore settles before
they are written, even though Part A is built first.

### 4.1 `flextools_parse_text` -- the annotation decision (local, needs a call)

**The tension.** SPEC 10 gives `flextools_parse_text` the annotation
`readOnlyHint=False, destructiveHint=True`, because at CP4 it files. At CP3 there
is no `ParseFiler` binding at all, so its call path **structurally cannot write**
-- which is exactly the test SPEC 10 sets for `READ_ONLY_SAFE`.

Three options, and they are not equal:

- **(a) `READ_ONLY_SAFE` at CP3, flipped to destructive at CP4.** Honest at each
  moment, but a tool's capability annotation is cached by hosts and read by
  calling models; flipping it is a caller-visible contract event for a tool that
  did not change name. Rejected.
- **(b) Destructive from day one, `apply` accepted but refused until CP4.**
  Stable annotation, but the schema advertises an argument that always fails.
  A model reading the schema will try it.
- **(c) Destructive from day one, `apply` absent from the schema until CP4.**
  Stable annotation; adding a parameter at CP4 is additive and non-breaking; no
  advertised-but-dead argument.

**Recommendation: (c).** The annotation declares the tool's *designed* maximum
capability and never moves; the argument that unlocks it arrives with the code
that implements it. SPEC 10's warning against overstating was made specifically
about `try_word`, where overstatement throttles the cheap hypothesis loop -- a
batch corpus parse is hours long and has no such loop to throttle, so the cost of
overstating here is close to zero and the cost of a flip is not.

**Record in the tool description**, first line, per SPEC 10: the spine, and that
filing is not yet reachable. A description that says "WRITES on apply=True" while
`apply` does not exist is the 8.4 failure applied to our own surface.

### 4.2 The run artifact set is spine-conditional

SPEC 5.5 lists the union of both spines' files:

```
runs/<project>/<run_id>/
    run.json  words.txt  hc-script.txt  hc-output.txt
    hc-stdout.txt  generate-config.log  trace.txt
```

`hc-script.txt`, `hc-output.txt`, `hc-stdout.txt` and `generate-config.log` are
**sandbox-spine (CP5) files**. CP3 writes the in-process subset:

| File | CP3 | Contents |
|---|---|---|
| `run.json` | **yes** | Durable job state and summary (4.3) |
| `words.txt` | **yes** | The resolved scope, NFC-normalized, in the order of SPEC 6.2 |
| `results.jsonl` | **yes, new** | One record per word, appended as produced (4.4) |
| `trace.txt` | conditional | Only where a drill-down trace was taken (Part E) |
| the four `hc-*` / `generate-config` files | no | CP5 |

**`results.jsonl` is net-new to this document and needs naming in SPEC 5.5.**
SPEC 5.6's commitment -- "a job that dies at word 4,000 leaves 4,000 usable
results" -- requires an append-only per-word stream. `run.json` is rewritten in
place and cannot carry it. Record the addition rather than smuggling it in.

`run_id` is `<UTC yyyymmddTHHMMSSZ>-<8 hex>`. Retention is newest 20 runs per
project, mirroring `backup.py::_prune_old_backups` (`backup.py:50`) -- reuse that
function's shape rather than writing a second pruner.

### 4.3 `run.json` -- align with `ParserReport.cs`, and say where we differ

SPEC 5.5 requires alignment with FieldWorks' own `ParserReport`
(`Src\LexText\ParserCore\ParserReport.cs:51-86`, accumulated `:317-359`) where
fields coincide, and an explicit statement where they do not.

**Adopt verbatim** (same name, same semantics): `NumWords`, `NumParseErrors`,
`NumZeroParses`, `TotalParseTime`, `TotalAnalyses`,
`TotalUserApprovedAnalysesMissing`, `TotalUserDisapprovedAnalyses`,
`TotalUserNoOpinionAnalyses`.

**Deliberate divergences, each to be stated in the artifact itself:**

1. **The 9.3.1 tiering has no counterpart in `ParserReport`.** Its approval
   counters are flat. Ours carry the tier split, and
   `TotalUserApprovedAnalysesMissing` must be computed over **tier 3 only** or it
   silently reproduces the category error 9.3.1 exists to prevent.
2. **`TotalUserNoOpinionAnalyses` is not "never reviewed"** (9.3.4). Carry the
   affirmed/indeterminate split beside it, and never let a consumer read the
   noopinion count as a review count.
3. **`ParserReport`'s counters are per word.** Nothing in it is per rule or per
   morpheme. Our G3 batch signals (9.1) are per word too; the per-rule material
   lives only in a drill-down trace, and `run.json` must not imply otherwise.

**Job state, not only summary.** Per SPEC 5.5, `run.json` carries the current
state, `words_completed` / `words_total`, `engine_at_submission`, the
`scope_fingerprint`, and on terminal failure the reason. It is written
incrementally.

**One more field, required by SPEC 17.2's resolution:** the **MCP-owned grammar
load-error baseline** captured at our own grammar load, keyed to
`scope_fingerprint`. CP4's refuse-to-file gate (12.3, rung 2) is specified
against this baseline and explicitly **not** against FLEx's provenance-blind
`{ProjectName}HCLoadErrors.xml`. CP3 is the checkpoint that first loads a grammar
for a batch, so CP3 is where the baseline is captured. Failing to persist it here
forces CP4 to either invent one or fall back to the artifact 17.2 rejected.

### 4.4 `results.jsonl` -- one record per word

Per record: the wordform, its analysis count, and for each analysis the durable
signature of 6.2 plus enough rendered text to report without reopening the
project. Written append-only as each word completes, so the file is always valid
up to its last newline.

**Do not serialize the `ParseResult` objects.** They carry live LCM references
(section 2, item 2) which are meaningless once the project closes. Serialize the
signature and the rendered text; keep the live objects only within the run.

---

## 5. Part A -- scope resolution

### 5.1 The word list

Per SPEC 6, spines 1 and 2 take their target list from
`IStText.UniqueWordforms()`, unioned across a genre or across all texts exactly
as `ParserListener` does. **We do not build our own walk.** Subject to 3.1's
probe.

### 5.2 Genre -> text

`TextOperations.GetGenre` returns only the **first** genre, so a text tagged
`[Narrative, Folklore]` scoped by `"Folklore"` is missed. Genre selection reads
the full reference collection `IText.GenresRC`.

**This is now cheaper than SPEC 6.1 assumed.** 6.1 notes `GenresRC` is reachable
through no flexicon wrapper and calls it "one of the few places this feature
drops beneath flexicon", with `Texts.GetGenres()` named as the natural companion
if the facade landed. **It landed** -- `Texts.GetGenres()` is one of CP2a's three
companion read gaps and shipped in 4.9.0. Part A calls it; the raw-LCM fallback
described in 6.1 is no longer needed and should not be written.

> **Carry CP2a's own concern forward.** `specs/parser-check-cp2` records that all
> three read gaps (`Texts.GetGenres`, allomorph owning entry, MSA reads) shipped
> in 4.9.0 with **no tests of their own and no live exercise** -- tasks.md
> scheduled an implementation task for each and a test task for none. CP3 is the
> first real consumer of `GetGenres()`. Part A's own tests are therefore the
> first pin on its empty-collection contract, and should be written as if they
> were flexicon's.

Matching is case-insensitive against genre **name and abbreviation** in the
default analysis writing system. More than one match is `parse_scope_ambiguous`
carrying `candidates`.

**Known limitation, carried not solved:** SPEC 17.3 -- matching against the
default analysis WS may miss a user working in a localized UI. CP3 does not fix
this; it records it in the response when a genre string fails to match, so a
localized-UI user sees a plausible reason rather than "no such genre".

### 5.3 Word list ordering (SPEC 6.2)

Dedup NFC-normalized, order by **descending occurrence count then
alphabetically**, truncate by `limit` *after* ordering, record
`truncated_by_limit`. SPEC 6.2 scopes this to the sandbox spine's word-list file;
CP3 applies the same ordering to `words.txt` so the two spines' artifacts are
comparable at CP5 and a diff across spines is not defeated by ordering alone.

### 5.4 `scope_fingerprint` (local decision D-3)

SPEC 11 requires runs to carry one and requires `parse_scope_mismatch` to name
`differing_fields`, but never defines the field set. Proposed:

| Field | Why |
|---|---|
| `scope_kind` | `all_texts` \| `genre` \| `text` \| `word_list` |
| `scope_value` | the genre string, text identifier, or null |
| `text_hvos` | sorted, so a text added to a genre is visible as a difference |
| `word_count` | after dedup, before `limit` |
| `limit` / `truncated_by_limit` | a truncated run is not comparable to a full one |
| `engine_at_submission` | 3.2's labelling rule; an HC run and an XAmple run are never the same scope |
| `writing_system` | the vernacular WS the words were read in |

Deliberately **excluded**: anything about the grammar. A grammar edit between two
runs is the thing a diff exists to measure, so folding a grammar hash into the
fingerprint would refuse exactly the comparison the user wants. The load-error
baseline of 4.3 is carried *beside* the fingerprint, keyed to it, not inside it.

Mismatched fingerprints refuse with `parse_scope_mismatch` unless `force=true`,
and then diff **on the intersection only** -- and say so in the output.

---

## 6. Part D -- `flextools_parse_diff`

### 6.1 Buckets

SPEC 11's table, unchanged. Let `b` = analyses in the before-run, `c` = analyses
in the after-run, for one wordform:

| Condition | Bucket |
|---|---|
| `b == 0, c > 0` | `fixed` |
| `b > 0, c == 0` | `broken` |
| both > 0, sets differ | `changed` |
| identical | `unchanged` |

**`changed` must not collapse into `unchanged`.** One analysis becoming seven
still "parses" and the grammar got worse. This is the single assertion most
likely to be lost in an implementation that compares counts, and it gets its own
test.

### 6.2 The durable signature (local decision D-2)

SPEC 11 says to align on `MatchesIWfiAnalysis` (`ParseResult.cs:102-133`) rather
than invent a normalized signature, "because the in-process spine gives typed
morphs". That predicate is:

```
analysis.MorphBundlesOS.Count == this.Morphs.Count
    && for each: mb.MorphRA == current.Form && mb.MsaRA == current.Msa
```

-- i.e. **ordered object identity** over `(MorphRA, MsaRA)` pairs.

**The problem SPEC 11 does not address:** a diff compares two *runs*, and a run
persisted to disk has no live objects. Identity has to survive serialization.

**Proposal:** the durable signature is the **ordered sequence of
`(MorphRA.Hvo, MsaRA.Hvo)` pairs**. Within a project, HVOs are stable object
identifiers, so this is `MatchesIWfiAnalysis`'s predicate expressed durably
rather than a parallel normalization -- which is what SPEC 11 asks for.

Carry the rendered morph forms and MSA labels **alongside** the HVOs, for two
reasons: a report must render without reopening the project, and a signature
nobody can read is undiagnosable.

**Two caveats to state in the output, not to hide:**

1. **HVO churn is a false `changed`.** A morph deleted and recreated gets a new
   HVO. Two runs either side of such an edit report `changed` for an analysis
   that is behaviourally identical. Detect it -- identical rendered forms,
   different HVOs -- and label it as an identity change rather than a behavioural
   one. Do not silently collapse it to `unchanged`: something really did change
   in the lexicon.
2. **HVO stability across sessions is asserted here, not verified.** It should be
   confirmed live before Part D ships. If it does not hold, the signature falls
   back to rendered form + MSA label, with the ambiguity that implies stated in
   the report.

### 6.3 Shared mode

Per SPEC 7.3: when `project_access` reports `shared` or `held_by_other`, set
`staleness: "shared_mode_unverifiable"`, carry the save-or-close note, and
**downgrade `no_change` to `no_change_unverifiable`**. Never promise a safe
read-back interval; there is no N that is safe.

---

## 7. Part E -- G3, the largest and most correctness-sensitive part

### 7.1 Batch layer (SPEC 9.1)

Computed from typed `ParseMorph` data -- i.e. from `ParseWord`'s live objects,
not from the XML. Five signals, each shipping its false-positive mode **in the
output**, because legitimate ambiguity is normal in many languages and a high
count is not a bug:

| Signal | False positive that must be printed beside it |
|---|---|
| Analysis count per word | Real productive ambiguity |
| Root-entry disagreement | Genuine root homographs |
| Root analysed as affix stack | Real zero-derivation / cliticization |
| Same surface, incompatible MSA/category | Genuine cross-category homographs |
| Count-distribution histogram | -- (it is a diff instrument, not a verdict) |

Root-entry disagreement and the MSA signal both need to get from a `ParseMorph`
to its owning `ILexEntry` and to its MSA. **Both are CP2a read gaps that
shipped** -- allomorph owning entry and the MSA reads. Same test caveat as 5.2:
CP3 is their first consumer.

**The histogram is the G4 early warning.** SPEC 9.5.1 treats G3 and G4 as one
phenomenon at two scales; a rightward shift in the count distribution after an
edit is evidence something got looser, and is the cheapest thing in Part E.

### 7.2 The oracle and its tiers (SPEC 9.3, 9.3.1)

**Tier from `IWfiMorphBundle.IsComplete`, never from a reimplemented predicate.**
`WfiAnalysis.IsFullyFormed` is `internal` and therefore not callable from
pythonnet; compute the tier from `MorphBundlesOS.Count` plus each bundle's
public `IsComplete`.

| Tier | State | Oracle? |
|---|---|---|
| 0 | No analysis | No |
| 1 | Gloss/category only, `MorphBundlesOS.Count == 0` | **No** -- meaning recorded, decomposition not |
| 2 | Bundles present, some with null `MorphRA`/`MsaRA`/`SenseRA` | **No** -- sketched, not linked |
| 3 | Bundles present and all `IsComplete` | **Yes** |

**Only tier 3 enters "human approved N of the parser's M".** Tiers 1 and 2 are
reported separately **and by name**, never folded into a count, never dropped,
and never rendered as disagreement with the parser -- the human has not disagreed,
they have not yet spoken on the question the parser is answering.

The mandatory wording of 9.3.3 is a **literal requirement**, not a paraphrase
target. Six cases, each with its own sentence, including the two tier sentences.
The report must never render the no-opinion case as "invalid", "incorrect",
"rejected" or "flagged".

**Project-state precondition:** on a project never parsed live, the oracle is not
degraded, it is **absent**, and the tool says so. Silently emitting a report in
which every analysis reads as unreviewed is how a user concludes their grammar is
bad when the truth is nobody ever ran the parser. This is one of the three
consumers of 3.3's single probe.

### 7.3 Provenance: affirmed vs indeterminate (SPEC 9.3.4)

The join against segment occurrence is **one-sided** and CP3 must implement it as
such:

- **Not in any segment, approved** -> affirmed, reliably.
- **In a segment, approved** -> affirmed **or** tacit, *unknowable*.

Report the split as `{affirmed, indeterminate}`. **Never** `{affirmed, tacit}` --
that labels individual analyses with a provenance the database does not record,
and a user who did review their text would rightly call it wrong about their own
work. The mandatory sentence of 9.3.4 ships verbatim.

> **This join is built once.** CP4's deletion projection (12.2) is the *same*
> segment-occurrence join, used for the opposite purpose: an in-segment analysis
> holds a user approval by the time `SetUnsuccessfulParseEvals`' delete check
> runs, so it is shielded from the non-undoable delete. CP3 owns the join; CP4
> consumes it. A CP4 that rebuilds it is a review finding.

Wording is gated on 3.2's probe (SPEC 17.12) -- the split ships, its description
of what the indeterminate population contains waits for the answer.

### 7.4 Candidate pairing and promotion-only ranking (SPEC 9.3.2)

Tiers 1 and 2 are excluded from the morphological count and **not** excluded from
the analysis. The human supplies the *what*; the parser supplies the *how*; the
parser attempts no word-level semantics, so the two compose rather than conflict.

- **1:1 case** -- one parser analysis, one human gloss: surface a **candidate
  pairing**, ranked first, with its confidence basis named (count match vs gloss
  agreement vs both), worded as a suggestion. Never an automatic write.
- **1:N case** -- compare the *composed* gloss (each `IWfiMorphBundle`'s
  `SenseRA` gloss, stem sense above all) against the human's `IWfiGloss.Form`.

**The signal is asymmetric and implementing it symmetrically would be worse than
not implementing it.** Agreement promotes; **disagreement must not demote**.
Morphology is not reliably compositional -- `understand` is not `under` + `stand`
-- so ranking on mismatch systematically penalises the *correct* analysis of
exactly the words where morphology is most interesting.

**The ranking is promotion-only**: matching analyses rise, everything else keeps
its original order. An implementation that sorts by gloss distance is wrong and
must fail review. This is the single most important regression test in CP3
(section 12).

**Persistent disagreement is a finding, not noise.** A word the parser can derive
whose parts do not add up to the recorded meaning is a candidate **lexicalized
form** -- report it with 9.3.2's wording, as something that may deserve its own
entry or sense, not as a parse error. That reading is often more valuable to a
linguist than the parse.

### 7.5 Drill-down (SPEC 9.2) and its cost discipline (SPEC 9.4)

The trace records the **entire search**. For each accepted analysis the
`MorphologicalRuleApplied` / `LexEntry` sequence gives the rule chain. The
attribution method is **side-by-side comparison** of a word's N chains: the rule
appearing in every "should not have parsed" chain is the overgeneration
candidate.

**This comparison does not exist yet.** It is net-new build, not presentation of
something `TraceWordXml` already returns. Budget it as such.

**`selectTraceMorphs` (mode A) is a pre-parse filter**
(`HCParser.cs:186-200`), not an attribution mechanism. Do not design G3
attribution against it as if it named the rule that licensed an analysis. Its one
genuine G3 use is **by subtraction**: re-run a suspect analysis with its own
morphs selected and the surviving chain is that analysis's derivation in
isolation. That narrows the candidate set; it still does not name the rule.

**Cost (9.4).** Default drill-down cap 10-20 words per session, chosen by the
user, **never auto-traced in bulk**. When 400 words look overgenerating, do not
trace 400: report the batch summary, **cluster by shared root entry or category
pair** -- a single loose rule produces a cluster, not 400 independent problems --
and recommend tracing 1-3 representatives per cluster. The clustering is what
makes the cap usable rather than merely restrictive.

### 7.6 What CP3 computes for CP4 and does not act on

Two projections belong to CP4's confirmation (12.4) and are computable from CP3's
data:

- **Deletion projection** (12.2) -- the conjunction of parser-created,
  user-`noopinion`, **and** not referenced by any segment.
- **Duplicate projection** (9.3.3) -- a gloss-only analysis has zero bundles and
  can never match, so filing creates a second analysis by construction. "May
  create N analyses, M of which duplicate an existing gloss-only record."

CP3 builds the predicates and may **report** them as information. CP3 does not
file, does not confirm, and does not ship the ladder.

---

## 8. Part F -- G4 instrument 2, and the routing that makes CP1 pay off

### 8.1 The bounded complete parse (local decision D-4)

SPEC 9.5.2, instrument 2: "run a single word to completion with a hard bound and
report what it actually cost. A grammar that takes minutes on one short word will
not finish a corpus, and knowing that costs one word rather than one night."

**Where the bound actually comes from, because the engine does not provide one.**
SPEC 9.5.2 verified that there is **no `CancellationToken`, timeout, or
step/node budget anywhere** on `HCParser`, `IParser` or `Morpher`. And SPEC 5.6's
cancellation is cooperative **at the next word boundary** -- which for a
single-word parse is after the parse it was meant to bound. So:

> **Instrument 2's bound cannot be enforced inside the parse.** The only
> enforcement available is process-level: the parse worker is a subprocess, and
> `subprocess_helpers._kill_process_tree` (`subprocess_helpers.py:20`, `taskkill
> /T /F` on Windows) is what actually stops it.

Consequences to build to:

1. Instrument 2 runs as its **own job** at the runner's highest word priority, in
   a worker the supervisor is willing to kill. It must not share a worker with a
   batch, because killing it would kill the batch.
2. The reported cost is **wall clock**, plus whether the fast-path window was
   missed and by how far. It is **not** an engine-reported step or node count --
   no such number exists, and inventing one is 8.4's failure.
3. A killed instrument-2 run is a **result**, not an error: "this grammar did not
   finish one word in N seconds" is precisely the finding. Report it as a
   terminal state with the measurement, and route per 8.2.
4. The one adjacent lever SPEC 9.5.6 records is **data-driven, not an argument**:
   `Morpher.MaxStemCount` (default 2), `DeletionReapplications` (0) and
   `MergeEquivalentAnalyses` are read from `MorphologicalDataOA.ParserParameters`
   (`<HC><MaxRoots>`, `<DelReapps>`, `<MergeAnalyses>`). CP3 may **read and
   report** these values as context for a slow parse. CP3 must **not** write
   them -- that is a project-data write and this checkpoint has none.

### 8.2 `next_step` routing into `flextools_grammar_health`

CP1 shipped the scan; CP3 is the checkpoint that routes to it. SPEC 9.5.5 is
specific about the trigger:

> **It is proposed, not pushed.** Offer it when *a parse that should have been
> quick was not*. The fast-path window of 5.6 already defines "should have been
> quick" -- a `try_word` that misses it is by definition surprising, and that is
> the trigger.

So the proposal fires on: a `try_word` that misses the grace window; a batch that
enters `loading_grammar` and stays there; a terminal `failed` (SPEC 5.6 -- a run
that died of memory exhaustion is the single case where the user most needs a
diagnosis rather than a retry); and instrument 2 exceeding its bound. It does
**not** fire on a run that answered inline, and it is never advertised on every
response -- that is noise that trains people to ignore `next_step`.

`next_step` rules that bind Part F (SPEC 10.1):

- `est_cost` is mandatory. `"unbounded"` is a real value and the honest one for
  mode C on an unscreened grammar.
- `args` must be **directly usable** -- a proposal the caller reconstructs by
  hand is ignored by a model and misread by a human.
- Never propose a rung the project cannot reach (no sandbox step when `hc` is
  absent; no filing step in a read-only session -- which at CP3 is *every*
  session).
- **Never propose a tool that does not exist.** No MCP tool queries lexicon data;
  the only path is a `flextools_run_module` snippet (5.1.2).
- Where mode C would be the next rung on an unscreened grammar, propose the
  static scan **first** -- it is cheaper than the trace it might make unnecessary.

**CP2's inherited obligation applies here too.** CP1's T013 left `next_step` rows
degraded to `tool: null` because the tools did not exist; CP2 revisits the
`try_word` rows. CP3 must revisit the rows that name `parse_text`, `parse_log`
and `parse_diff` -- and check that nothing still points at `tool: null` for a
tool CP3 just shipped.

---

## 9. Part C -- `flextools_parse_log`

`flextools_parse_log(run_id, section, word, filter, lines, offset)`, sections
`summary | config_generation | hc_stdout | hc_output | trace | words | results`.

**Four of those sections are sandbox-spine sections and CP3 has no data for
them.** They must return a typed *not-applicable-for-this-spine* response naming
the spine and the checkpoint that will fill them -- **never an empty section**.
An empty section reads as "nothing happened", which is exactly the failure SPEC
8.3 raises: the most common sandbox failure is config generation producing
nothing, and the current script discards that output via `| Out-Null`. CP3 must
not reproduce that shape from the other direction.

`section="results"` and `section="words"` are CP3's real sections;
`section="trace"` is populated only where a drill-down was taken.

**Never fabricate an explanation (SPEC 8.4).** Where a trace is parseable, name
the blocking rule or stage in one line. Where it is not, return the raw slice
**and say it is raw**. This principle is load-bearing for Parts C, E and F alike.

---

## 10. Error codes added at CP3

Additive, so the contract stays at `tool-responses/1.0`; one CHANGELOG entry
under **"Tool contract"**. Count bumps **25 -> 30**.

| Code | Detail fields | First emitted by |
|---|---|---|
| `parse_scope_empty` | `scope`, `matched_texts`, `hint` | Part A |
| `parse_scope_ambiguous` | `scope`, `requested`, `candidates` | Part A |
| `parse_scope_mismatch` | `baseline_fingerprint`, `current_fingerprint`, `differing_fields`, `hint` | Part D |
| `parser_timeout` | `timeout_seconds`, `words_completed`, `run_id`, `hint` | Part B, Part F |
| `parser_job_failed` | `state_at_failure`, `failure` (`out_of_memory` \| `crashed` \| `cancelled`), `words_completed`, `words_total`, `run_id`, `log_path` | Part B |

Each detail model is `extra="forbid"` with a TOOL-CONTRACT row, matching CP1's
established shape.

**Not at CP3:** `parser_filing_in_progress` and `grammar_load_unclean` are CP4's
(12.3, 12.6). CP3 nevertheless **captures** `grammar_load_unclean`'s baseline
(4.3) so CP4 has one to compare against.

**`parse_scope_empty` is subject to 3.1.** If an untokenized text is
indistinguishable from an empty one, this code is the wrong refusal for it and
Part A needs a second, differently-worded response. Settle 3.1 before writing the
detail model.

---

## 11. Inherited from CP1 and CP2

| From | Obligation at CP3 |
|---|---|
| CP1 T024 | `check_active_parser()` is **the first statement** of `parse_text`'s handler, before any `HCParser` construction. `parse_diff` / `parse_log` / `parse_status` never call it -- they read prior artifacts and never touch the engine |
| SPEC 5.6 / 3.2 | For a batch the engine check fires **once, at submission**; `engine_at_submission` goes in `run.json`. A flip mid-job is a **warning on the run summary, not a refusal** -- the results are internally consistent and 3.2 is a labelling rule, which labelling satisfies |
| CP1 T031 | The three PanGloss-derived lints (`hc-undeclared-segment`, `hc-duplicate-feature-bundle`, `hc-partial-morpheme`) are free **if** `GrammarHealthChecker` is public in the installed `SIL.Machine.Morphology.HermitCrab.dll`. CP2 carries the same row. If CP2 defers it again, CP3 either folds it in or records why it keeps being deferred -- a row that moves checkpoint twice without a reason is drift |
| CP1 `flextools_grammar_health` | Gets its `next_step` caller here (8.2). It already ships with no scoring and no verdict wording; Part E's report inherits that discipline rather than reintroducing severity |
| CP2 A4 | The floor/index-equality test. CP3's generated modules call `project.Parser`; an index that predates the facade cannot describe it (section 2, item 3) |
| CP2 runner | Batch is `Medium`/`Low` with per-wordform enqueue granularity. The batch's reported progress **must account for the interleave** rather than appearing to stall when a `try_word` jumps the queue |
| CP2 FR-042/043 | At most one loaded grammar is held, currency confirmed before reuse, reload is **reset-then-update**. A batch holds it for the whole run; a `try_word` interleaving into that run uses the same loaded grammar and must not trigger a reload |
| SPEC 12.6 | A running parse job does **not** block a lexicon edit or a user-agent analysis write. There is no project-wide claim, and CP3 must not introduce one |

---

## 12. Test plan

Drawn from SPEC 16; the CP3-relevant groups, plus what this document adds.

**Scope (Part A)**
- Genre selection via `GenresRC` finds a text whose matching genre is **second**
  in the collection. This is the regression test against `GetGenre`'s first-only
  read.
- `Texts.GetGenres()` on a text with no genres returns an empty collection and
  does not raise -- the pin CP2a never wrote.
- An ambiguous genre string refuses with `parse_scope_ambiguous` carrying
  `candidates`.
- Word-list ordering: descending occurrence then alphabetical, `limit` applied
  **after** ordering, `truncated_by_limit` recorded.
- **3.1's case:** a never-tokenized text is not reported as having no words.
  Exact assertion depends on Phase 0's finding; the test exists either way.

**Diff (Part D)**
- Every bucket, `only_in_*`, and the `parse_scope_mismatch` refusal.
- **One analysis becoming seven is `changed`, not `unchanged`.** A count-equality
  implementation must fail this test.
- HVO churn: identical rendered forms with different HVOs is labelled an identity
  change, and is neither silently `unchanged` nor reported as behavioural.
- `force=true` on mismatched fingerprints diffs the intersection only and says so.
- Shared mode downgrades `no_change` to `no_change_unverifiable` and carries
  `staleness: "shared_mode_unverifiable"`.

**G3 batch (Part E)**
- Each of the five signals against a fixture, **including each stated
  false-positive case** -- the false positive is part of the output, so it is part
  of the assertion.

**Oracle (Part E) -- the group SPEC 16 specifies in most detail**
- Completeness tiers, one fixture per tier: gloss-only
  (`MorphBundlesOS.Count == 0`), sketched (null `MorphRA`), fully linked. Assert
  only tier 3 enters the count, tiers 1 and 2 are named rather than dropped or
  counted as disagreement, and the tier derives from `IWfiMorphBundle.IsComplete`
  rather than a reimplemented predicate.
- Wording: the never-reviewed case renders the mandated sentence and **never**
  "invalid", "incorrect", "rejected", "flagged".
- Approval provenance: an analysis holding a user-agent `approves` **and**
  occurring in a segment is reported in the separately named **indeterminate**
  population. An implementation reading the opinion field alone must fail. Assert
  no individual analysis is ever labelled "tacit", "unreviewed" or
  "auto-approved".
- A never-parsed project reports the oracle **absent**, not all-unreviewed.

**Promotion-only ranking (Part E) -- the most important regression test in CP3**
- Fixture: a non-compositional word whose composed gloss is far from the human
  gloss and whose **correct** analysis is the mismatching one. Assert it is not
  demoted below a compositional-but-wrong competitor and that no output renders it
  as less likely. **A sort-by-gloss-distance implementation must fail this test.**
- Candidate pairing: one parser analysis plus one human gloss yields a pairing
  ranked first, labelled a suggestion with its confidence basis stated, never
  auto-filed.
- Lexicalization finding: a derivable word whose parts do not add up to the
  recorded meaning is reported as a candidate lexicalized form, not a parse error.

**Projections computed for CP4 (Part E)**
- Deletion projection is a **conjunction**: a fixture with two parser-created,
  user-`noopinion` analyses -- one segment-referenced, one not -- projects exactly
  **one**. A bare-noopinion projection returns two and must fail.
- Duplicate projection: a fixture containing gloss-only analyses reports the
  duplicate count.

**G4 / routing (Part F)**
- A `try_word` that misses the fast-path window emits a `next_step` proposing the
  static scan; one that answers inline does **not**. The proposal is conditional.
- A terminal `failed` run carries a `next_step` pointing at 9.5.2's instruments.
- `next_step` never names a tool that does not exist, and never a lexicon query
  tool.
- Instrument 2 killed at its bound produces a terminal **result** with a wall-clock
  measurement, not an error, and not an invented step count.

**Job model, inherited (Part B)**
- A job killed mid-run leaves its completed words readable through `parse_log`
  and a `parser_job_failed` terminal state naming `out_of_memory` or `crashed`.
  Partial work is never discarded.
- Cancellation stops at the next word boundary and leaves `cancelled` over the
  partial results.
- A single-word request against a running batch is answered without waiting, and
  the batch resumes at its next word with its position and loaded grammar intact.

**Concurrency (SPEC 12.6)**
- A running parse job does not block a lexicon edit or a user-agent analysis
  write. Regression test against reintroducing a project-wide claim.

**Standing guarantees**
- Parseability is never derived from analysis counts (SPEC 3.1).
- `ActiveParser` mismatch produces `parser_engine_mismatch`, never a parse.
- `flextools_grammar_health` still opens no parser and runs no parse.
- `HCParser_DoesNotLoadXCore` (CP2's) stays green.

**Live (`lex-verification`, HC-configured project)**
- Target projects per CP2's D3: `IndonesianHC-Complete` for correctness,
  `Malay Parsing-20230810withHC` for scale. **Not Sena 3** -- it reports engine
  `XAmple` and this feature's own engine gate would refuse it.
- Baseline parse -> deliberate grammar break -> diff reports `broken` naming the
  right word -> revert -> diff reports `fixed`.
- Non-Latin word list round-trips (the SPEC 4 encoding regression; its failure
  mode looks like a grammar problem, which is why it gets a standing test).
- HVO stability across sessions, per 6.2's second caveat.
- A shared-mode run returns `staleness: "shared_mode_unverifiable"`.

---

## 13. Exit criteria

1. Phase 0's two probes (3.1, 3.2) are answered and SPEC 17.11 / 17.12 are
   updated with the findings.
2. A batch parse over a resolved scope runs end to end against a live
   HC-configured project, writes a complete artifact, and survives a mid-run kill
   with its completed words readable.
3. `parse_log` reads every CP3 section and returns a typed not-applicable for
   every CP5 section.
4. `parse_diff` distinguishes all four buckets on live runs, including the
   one-becomes-seven case.
5. The G3 report renders every mandated sentence of 9.3.3 verbatim, and the
   promotion-only regression test passes.
6. Instrument 2 measures a real grammar and routes a slow result into
   `flextools_grammar_health`.
7. Every `next_step` row that named `tool: null` for a CP3 tool is revisited.
8. The `grammar_load_unclean` baseline is persisted and keyed to
   `scope_fingerprint`, so CP4's rung 2 has the artifact 17.2 specified.
9. Full suite green -- CP1's T028 groups, CP2's section 8, and this document's
   section 12.
10. Live verification (`lex-verification`) on both CP2 D3 projects.

---

## 14. Open questions (local)

1. **D-1, `parse_text`'s annotation** (4.1). Recommendation (c): destructive from
   day one, `apply` absent until CP4. Needs a maintainer call, because it is the
   only place CP3 deliberately overstates a capability.
2. **D-2, HVO stability across sessions** (6.2). Asserted, not verified. Verify
   live before Part D ships; the fallback signature is specified.
3. **D-3, the `scope_fingerprint` field set** (5.4). Proposed here for the first
   time; SPEC 11 requires the concept and never defines it.
4. **`results.jsonl` needs adding to SPEC 5.5** (4.2). It is required by 5.6's
   partial-results commitment and is not in the file list.
5. **T031's lints, twice-deferred** (section 11). Fold in or record the reason.
6. **SPEC 17.3, localized genre names** (5.2). Carried, not solved. Is the
   recorded-in-the-response mitigation enough, or does CP3 owe a WS fallback?
7. **Cluster definition for 9.4's drill-down cap** (7.5). "Cluster by shared root
   entry or category pair" is the rule; the tie-breaking and the
   representative-selection are not specified anywhere.

---

## 15. Risks

- **Part E is the correctness risk, and it is concentrated in the ranking.** The
  promotion-only rule is the one place in this feature where a plausible,
  natural implementation -- sort by gloss distance -- produces a confidently wrong
  answer about the *correct* analysis of exactly the words a linguist cares most
  about. It must be tested before it is written, not after.
- **Part E is also the scope risk.** Batch signals, four oracle tiers, the
  provenance join, candidate pairing, promotion-only ranking, the lexicalization
  finding, the side-by-side chain comparison and the clustering are eight
  distinct pieces of build under one heading, and the chain comparison alone is
  net-new. It is larger than Parts A, C, D and F combined and should be planned
  as its own phase rather than as one task.
- **The entry gate is the schedule risk** (section 2). CP3 has no implementation
  path until CP2b's runner exists, and the runner was already CP2's named scope
  risk. Two checkpoints now depend on one piece of unbuilt infrastructure.
- **The artifact is a forward commitment.** CP4 and CP5 both read `run.json` and
  `results.jsonl`. A shape chosen loosely here is migrated twice later. This is
  why 4.2-4.4 come before the parts that consume them.
- **The oracle's wording is a user-trust risk, not merely a correctness one.**
  Telling a linguist that a human "never reviewed" an analysis they did in fact
  review is the same class of error as 3.1's inference from database state, one
  layer in -- and it is the error a user is most likely to notice and least
  likely to forgive.
