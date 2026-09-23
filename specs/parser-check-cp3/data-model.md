# Data Model: parser-check CP3

**Date**: 2026-09-22
**Spec**: [`spec.md`](./spec.md) · **Plan**: [`plan.md`](./plan.md) · **Research**: [`research.md`](./research.md)

Phase 1 output. Entities from the spec's Key Entities list, given fields,
relationships and validation rules. The on-disk shape is normative -- CP4 and
CP5 both read it, so [`contracts/artifact.md`](./contracts/artifact.md) is the
frozen contract and this document is its rationale.

Two rules apply to every entity here and are not repeated per field:

- **No live data-model object reference is ever serialized** (FR-021).
  Identifiers plus rendered text, always.
- **Nothing in this model is written to a FieldWorks project** (FR-063).

---

## 1. Scope

What the user asked to parse, before resolution.

| Field | Type | Notes |
|---|---|---|
| `kind` | `"all_texts" \| "genre" \| "text" \| "words"` | |
| `value` | `str \| list[str] \| None` | genre string, text identifier, or explicit word list |
| `limit` | `int \| None` | applied **after** ordering (FR-009) |

**Resolution rules**

- Genre matching is case-insensitive against **both** genre name and
  abbreviation (FR-007), and reads the **full** set of genres on a text, not
  the first (FR-006). A text tagged with two genres is found by either.
- More than one match refuses with `parse_scope_ambiguous`, carrying every
  candidate.
- No match records that matching ran against the default analysis writing
  system (FR-008), so a localized-interface user sees a plausible reason rather
  than a bare assertion that no such genre exists.
- An empty genre collection on a text returns empty and raises nothing
  (FR-013, SC-001's sibling case).

---

## 2. ResolvedScope and WordList

| Field | Type | Notes |
|---|---|---|
| `text_ids` | `list[int]` | the texts the scope resolved to |
| `words` | `list[str]` | NFC-normalized, de-duplicated, ordered |
| `count_before_limit` | `int` | the de-duplicated count **before** truncation |
| `truncated` | `bool` | recorded on the response (FR-009) |
| `never_tokenized_text_ids` | `list[int]` | texts with structure but no unique wordforms |

**Ordering** is descending occurrence count, then alphabetically, and the
caller's limit truncates **afterwards** (FR-009). Order-then-truncate is what
keeps two runs over a differently ordered corpus comparable.

**The word list is taken from the data model's own unique-wordform
enumeration**, unioned across the selected texts exactly as the host
application does (FR-005). CP3 does not build a corpus walk.

**The empty-scope distinction** (FR-002): the scope layer performs a
distinguishing read -- a structural count that is non-zero while the
unique-word count is empty -- and words its refusal conservatively. An empty
word count is **not** treated as proof of an empty text, and
`parse_scope_empty`'s wording is not reused for a never-tokenized one.

Persisted as `words.txt`, one word per line, UTF-8, NFC, in resolved order.
**The only genuinely net-new file in the run directory** (D-6).

---

## 3. ScopeFingerprint

The durable description of a resolved scope, sufficient to decide whether two
runs are comparable. Exactly eight fields (FR-010, D-3):

> **Count corrected during implementation (T012/T020).** This section, the
> Key design decisions entry in `spec.md`, and tasks T020/T027 all said
> "seven" while every field *list* -- here, in FR-010, and in both tasks --
> named the same eight. The miscount reads `limit` and `truncated` as one
> item; FR-010 spells them as "the limit and truncation flag". The
> enumeration is authoritative and is unchanged; only the count moved.

| Field | Type | Why it is in |
|---|---|---|
| `scope_kind` | `str` | |
| `scope_value` | `str \| list[str] \| None` | |
| `text_ids` | `list[int]` | a text added to a genre must show as a difference |
| `word_count` | `int` | de-duplicated, **before** any limit |
| `limit` | `int \| None` | a truncated run is not comparable to a full one |
| `truncated` | `bool` | |
| `engine` | `str` | recorded at submission; two engines are never the same scope |
| `vernacular_ws` | `str` | the writing system the words were read in |

**Grammar state is deliberately absent** (FR-011, D-3). A grammar edit between
two runs is precisely what a comparison exists to measure; folding a grammar
hash in would refuse every interesting comparison.

The **load-error baseline sits beside the fingerprint, not inside it**
(FR-023), keyed to it.

**Comparison rule** (FR-012): differing fingerprints refuse with
`parse_scope_mismatch` naming `differing_fields`, unless forced. A forced
comparison runs on the **intersection only** and says so in its output.

---

## 4. Run and RunRecord (`meta.json`)

Extends CP2b's `RunMeta` (`server/parse/record.py:160`). Existing fields --
`run_id`, `stage`, `project_name`, `words_total`, `words_completed`,
`created_at`, `updated_at`, `interleaved_by`, `failure`, `stage_at_cancel` --
are unchanged. CP3 adds:

| Field | Type | Requirement |
|---|---|---|
| `scope_fingerprint` | `ScopeFingerprint` | FR-010, FR-016 |
| `engine_at_submission` | `str` | FR-016, FR-024 |
| `engine_changed_midjob` | `bool` | a **warning** on the summary, never a refusal (FR-024) |
| `load_error_baseline` | `list[dict]` | FR-023 -- captured at *our* grammar load, for CP4's gate |
| `counters` | `HostCounters` | FR-017 |
| `counter_divergences` | `list[str]` | FR-017 -- stated **in the artifact**, not only in the spec |
| `words_path` | `str` | `words.txt` |

**`run_id` keeps CP2b's form**: 32 lowercase hex, `secrets.token_hex(16)`,
validated by `\A[0-9a-f]{32}\Z`. No timestamp. Not re-minted (FR-022, D-6).

**Written incrementally** (FR-016), which `record.write_meta` already does --
temp file then `os.replace`, atomic on both platforms, so a status poll landing
mid-write reads one whole state or the other.

**Terminal failure** carries a reason from exactly `out_of_memory | crashed |
cancelled`.

### 4a. HostCounters

Eight names adopted **verbatim** from the host application's parser report
(FR-017): `NumWords`, `NumParseErrors`, `NumZeroParses`, `TotalParseTime`,
`TotalAnalyses`, `TotalUserApprovedAnalysesMissing`,
`TotalUserDisapprovedAnalyses`, `TotalUserNoOpinionAnalyses`.

Two carry deliberate divergences, and both are stated in
`counter_divergences` inside the artifact:

- **`TotalUserApprovedAnalysesMissing` is computed over fully linked human
  analyses only** (FR-018). Computing it over all human analyses silently
  reproduces the category error the tiering exists to prevent.
- **`TotalUserNoOpinionAnalyses` is never presented, named or documented as a
  count of unreviewed analyses** (FR-019). The affirmed/indeterminate split is
  carried beside it.

---

## 5. PerWordResult (`results.jsonl`)

One JSON object per line, appended and flushed as each word completes (FR-020).
`record.append_result` already writes, flushes and `fsync`s per line, and
`iter_results` already skips a malformed trailing line -- so a run that dies at
word four thousand leaves four thousand usable results.

| Field | Type | Notes |
|---|---|---|
| `wordform` | `str` | NFC |
| `index_in_run` | `int` | |
| `analysis_count` | `int` | |
| `analyses` | `list[AnalysisRecord]` | |
| `trace_index` | `int \| None` | pointer into `traces/<n>.xml`, only where a drill-down was taken |
| `error` | `dict \| None` | per-word failure that did not kill the run |

---

## 6. AnalysisRecord and DurableAnalysisSignature

The identity of an analysis in a form that survives the project being closed.

| Field | Type | Notes |
|---|---|---|
| `signature` | `list[[int, int, int \| null]]` | ordered (morph-form id, morph-syntax-analysis id, inflection-type id) triples |
| `rendered_morphs` | `list[str]` | so a report renders without reopening the project |
| `category_labels` | `list[str]` | |
| `has_guessed_form` | `bool` | FR-031a |

**Why the triple** (D-2): the parent spec says align on the host's own
match predicate rather than invent a normalized signature, and that predicate
is ordered object identity. A comparison runs across two *runs*, and a run on
disk holds no live objects -- so identity must survive serialization. The
identifier-triple sequence is that same predicate expressed durably.

**Inflection type is the third component, not an optional extra.** A
two-component (form, MSA) signature collapses two analyses differing only in
inflection type -- a real case, since irregularly inflected forms carry a
non-null inflection type -- and reports **unchanged** for analyses that
genuinely differ.

**`has_guessed_form` is the honest residue** (FR-031a). The host predicate has
a fourth component: where a parser morph proposes a guessed surface form, it
additionally requires that form to match one of the bundle's writing-system
alternatives. A serialized signature has no access to that comparison. So the
flag is recorded, and any comparison touching such an analysis reports
**provisional** rather than asserting behavioural identity. Omitting it
silently would claim alignment with a predicate the signature does not
reproduce.

**Fallback** (FR-033): if identifier stability across sessions is not confirmed
by live verification, the signature falls back to rendered form plus category
label, and the resulting ambiguity is stated in the report.

**Read from the structured result, never from the documents** (FR-035, and the
entry gate's settled fact): the structured result's analyses carry live
references to the morph-form, MSA and inflection-type objects; the
document-returning operations preserve those only as integers.

---

## 7. Comparison

Buckets are exactly `fixed | broken | changed | unchanged` (FR-030).

| Classification | Condition |
|---|---|
| `fixed` | no analyses before, some after |
| `broken` | some analyses before, none after |
| `changed` | both non-empty, **signature sets differ** |
| `unchanged` | both non-empty, signature sets identical |

A word going from one analysis to seven is `changed` -- it still parses, and
the grammar got looser. **An implementation that compares counts alone fails
its test** (SC-008).

**Identity change** (FR-032): identical rendered forms under differing
identifiers is labelled an identity change, neither reported as behavioural
change nor collapsed to unchanged -- something really did change in the lexicon.

**Shared mode** (FR-034): where `probe_project_access` reports `open_shared` or
`open_exclusive`, the comparison carries `staleness: "shared_mode_unverifiable"`
and the save-or-close note, and `no_change` is downgraded to
`no_change_unverifiable`. **No safe read-back interval is ever promised**,
because there is none.

---

## 8. CompletenessTier

How far a human got, and therefore whether the analysis can serve as an oracle.

| Tier | Meaning | Oracle role |
|---|---|---|
| `none` | no human analysis | not comparable |
| `meaning_only` | meaning recorded, no decomposition | **named**, never counted as agreement or disagreement, never dropped |
| `sketched` | begun, not fully linked | **named**, with how many of its morphs are unlinked |
| `fully_linked` | complete | the only tier that enters the approval comparison (FR-039) |

**Derived from the public per-bundle completeness flag plus the bundle count**
(FR-038). The host application's internal fully-formed predicate is **not**
reimplemented.

---

## 9. ApprovalProvenance

The split is exactly `{affirmed, indeterminate}` -- **never** `{affirmed,
tacit}` (FR-042).

The join is **one-sided, and that is the whole point**: approved and not
occurring in any segment is reliably *affirmed*; approved and occurring in a
segment is *unknowable*, because approval is recorded for anything left in use.

**No individual analysis may be labelled tacit, unreviewed or auto-approved**
(FR-042, SC-012). On a project the parser has never run against, the oracle is
reported **absent**, with its own sentence, rather than emitting a report in
which every analysis reads as unreviewed (FR-041, SC-013).

**The segment-occurrence join is built once and structured for reuse**
(FR-043). CP4's deletion projection is the same join used for the opposite
purpose; a CP4 that rebuilds it is a review finding.

The six mandated sentences are rendered **verbatim** and are pinned in
[`contracts/tools.md`](./contracts/tools.md), not paraphrased here.

---

## 10. BatchSignal

One observation about the corpus, **inseparable from the legitimate reason it
might be a false alarm** (FR-036). Five ship:

1. analyses per word
2. disagreement over which root entry a word belongs to
3. a root analysed as a stack of affixes
4. the same surface form in incompatible categories
5. the distribution of analysis counts

| Field | Type | Notes |
|---|---|---|
| `signal_id` | `str` | |
| `observations` | `list[dict]` | |
| `false_positive_note` | `str` | printed **in the output**, not in documentation |

Ambiguity is normal in many languages, so a high count is not by itself a
defect. The distribution is a **comparison instrument, not a verdict** (FR-037):
a rightward shift after an edit is evidence something got looser. No severity,
no verdict wording, no scalar score.

---

## 11. CandidatePairing and Ranking

A suggested correspondence between one parser analysis and one human
meaning-only record. It carries its confidence basis, is ranked first, is worded
as a suggestion, and is **never filed automatically** (FR-044).

**Ranking is promotion-only** (FR-045): agreement between a composed gloss and
the human's gloss *raises* an analysis; disagreement **does not lower** one.
Everything not promoted keeps its original order.

> An implementation that sorts by gloss distance is wrong and must fail review.
> Morphology is not reliably compositional, so a sort demotes the correct
> analysis of exactly the words a linguist cares most about. SC-014 is the
> guard, and its fixture is written before the function exists.

**Lexicalization** (FR-046): a word the parser can derive whose parts do not
add up to its recorded meaning is reported as a **candidate lexicalized form**,
using the mandated wording -- not as a parse error.

---

## 12. Cluster and DrillDownTrace

A cluster groups suspect words that probably share one loose rule.

- **Key**: shared root entry first; category pair where no root entry is shared
  (D-5).
- **Representatives**: highest analysis count first, ties broken by the word
  list's existing order, **capped at three** (D-5). The most over-generated word
  exercises most of the suspect rule chain in one trace.
- Stated as a heuristic **in the output**. A cluster whose representative does
  not reproduce the problem costs one wasted trace, which is why the cap is
  three rather than one.

**Drill-down** is capped per session at a user-chosen figure in the range
**10-20** words, and is **never** auto-traced in bulk (FR-047, SC-016). Where
many words look like overgeneration, the system reports the batch summary,
clusters, and recommends one to three representatives per cluster -- not four
hundred traces (FR-048).

**Rule attribution** is side-by-side comparison of one word's competing rule
chains (FR-049). The engine's pre-parse morph filter is **not** an attribution
mechanism; its only legitimate use here is narrowing a candidate set by
subtraction.

Trace payloads go **out of line** to `traces/<n>.xml`, as CP2b already writes
them. Where a trace is parseable the system **may** name the blocking rule or
stage in one line; where it is not, it returns the raw slice and **labels it
raw** (FR-029). No explanation is invented for output the system could not read.

---

## 13. Projection

A computation of what a future write *would* do. Reported as information,
**acted on by nothing** in this checkpoint (FR-050).

| Projection | Predicate |
|---|---|
| Deletion | parser-created **and** carrying no user opinion **and** not referenced by any segment |
| Duplicate | how many filings would duplicate an existing meaning-only record |

All three conjuncts of the deletion predicate are required. A bare
no-opinion projection over a fixture holding one segment-referenced and one
unreferenced candidate returns two and **fails** SC-015; the correct
projection returns exactly one.

No confirmation, no write ladder, no part of it.

---

## 14. NextStepProposal

| Field | Type | Notes |
|---|---|---|
| `tool` | `str` | **must exist** (FR-057, SC-019) |
| `arguments` | `dict` | directly usable, no reconstruction |
| `cost_estimate` | `str` | **mandatory**; `"unbounded"` is a legitimate value |
| `why` | `str` | |

Fires on: a single-word request that misses the fast-path window; a batch that
enters grammar loading and stays there; a terminal failure; and a bounded
measurement that exceeds its bound (FR-056). **Does not** fire on a request
answered inline, and is **not** attached to every response.

Never proposes a step the project cannot reach -- including any filing step,
which at CP3 is every session. Where a trace and the static scan are both
candidates, **the static scan is proposed first**, because it is cheaper than
the trace it may make unnecessary.

FR-058: every next-step row left pointing at a null tool because the tool did
not yet exist is revisited for the three tools CP3 ships, and none may still be
null for a shipped tool.

---

## 15. BoundedMeasurement

| Field | Type | Notes |
|---|---|---|
| `wordform` | `str` | |
| `bound_seconds` | `float` | |
| `elapsed_seconds` | `float` | wall-clock |
| `exceeded_bound` | `bool` | |
| `missed_fast_path_by` | `float \| None` | |
| `outcome` | `"completed" \| "terminated_at_bound"` | **a result, not an error** (FR-054) |

Runs as its own job at the runner's highest word priority, in a worker the
supervisor is willing to terminate, and **must not share a worker with a batch**
(FR-051) -- terminating it would take the batch with it.

The bound is enforced **at process level** via the existing process-tree
termination helper (FR-052, D-4). No in-parse enforcement may be claimed: the
engine offers no cancellation token, timeout or step budget, and the runner's
cooperative cancellation lands at the *next word boundary*, which for a
one-word parse is after the parse it was meant to bound.

**Reports wall-clock only.** No engine step or node count, because no such
number exists (FR-053, SC-017). "This grammar did not finish one word in N
seconds" is exactly the finding.

Stored parser parameters **may** be read and reported as context for a slow
parse; they are **never written** (FR-055).
