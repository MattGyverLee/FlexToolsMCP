# Specification Quality Checklist: parser-check CP3 -- the corpus, the artifact, and the diagnosis

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-22
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Domain gate (`after_specify` hook, `lex-domain`)

**Run 2026-09-22. Four BLOCKING findings, all corrected in place; re-validated above.**

All four shared one root cause: the source document `CP3-SPEC.md` was written against the parent
spec's *aspirational* file layout and never reconciled with the CP2b runner code that actually
shipped in the interim (`src/flextoolsmcp/server/parse/record.py`). Each was independently
verified against the shipped Python and the FieldWorks C# before being accepted.

| # | Finding | Correction |
|---|---|---|
| 1 | Artifact file names contradict shipped code: the run record is `meta.json` not `run.json`, traces are `traces/<n>.xml` not a flat `trace.txt`, and `words.txt` does not exist anywhere | **D-6** adopts the shipped layout and records that the parent spec's section 5.5 listing is the thing that must be corrected |
| 2 | Run identifiers carry no timestamp -- `new_run_id()` mints 32 random hex characters | Verbatim Constraints and **FR-022** now carry the shipped form |
| 3 | The backup pruner's name-sort is chronological only for timestamp-named directories, so reusing its *mechanism* would prune runs in random order | **FR-022** adopts the keep-newest-N policy and explicitly rejects the sorting mechanism, ordering by recorded creation time |
| 4 | The durable signature dropped two of the four components `MatchesIWfiAnalysis` compares (`InflTypeRA` and the guessed-string equivalence), while **claiming** to express that predicate | **FR-031** now carries the inflection-type identifier; **FR-031a** discloses the guessed-form component as provisional rather than dropping it; **D-2** records the correction and why the omission falsified its own rationale |

Two non-blocking findings were also taken:

- `results.jsonl` was described by the source document as net-new; it shipped with CP2b. Recorded
  in D-6 rather than left as a stale open question.
- The five new error codes' detail fields were described abstractly, leaving the field **order**
  to inference at implementation time. Given CP2's E7 divergence arose during transcription, the
  ordered field table is now reproduced in Verbatim Constraints.

The gate separately confirmed as accurate, and therefore not to be re-litigated: all eight adopted
host-report counter names and semantics; `IWfiMorphBundle.IsComplete` being public while
`WfiAnalysis.IsFullyFormed` is internal; `UniqueWordforms()` being gated on `ParseIsCurrent` and
segment iteration, which independently **confirms** Phase 0's premise rather than merely assuming
it; `GenresRC` versus first-genre-only behaviour; the parser-parameter reads; the pre-parse filter
framing; the one-sided segment join; all six mandatory oracle sentences and the population
sentence reproduced **word-for-word** with no drift; the forbidden-words list; the version-locked
sibling artifacts; the live verification project names and the `Sena 3` exclusion; and the
tool-contract's current count of exactly 25 codes.

## Notes

**Validation run 2026-09-22, two iterations.**

Iteration 1 found three failures, all since corrected:

1. *No implementation details* — FR-031 and FR-038 originally named .NET type and member
   names directly (`MorphRA`, `MsaRA`, `IWfiMorphBundle.IsComplete`). Rewritten as capability
   statements ("the ordered sequence of (morph-form identifier, morph-syntax-analysis
   identifier) pairs", "the public per-bundle completeness flag"). The exact member names stay
   recoverable from the source document, which every requirement cites by section.
2. *Success criteria are technology-agnostic* — SC-006 originally asserted a grammar-object
   reference count. Restated as an observable outcome ("the grammar is loaded exactly once").
3. *Scope is clearly bounded* — the original draft carried seven local open questions with no
   dispositions. Five are now resolved as Decisions D-1..D-5; the remaining two are carried
   explicitly as disclosed limitations under Risks and forced to a disposition by FR-008 and
   FR-062.

**Deliberate deviations from the generic template, both consistent with the campaign's
existing specs:**

- **Verbatim Constraints retains exact strings**, including error codes, file names, section
  names and the six mandated output sentences. These are not implementation detail — they are
  the requirement. The parent spec makes the oracle wording a literal requirement rather than a
  paraphrase target, and `../parser-check-cp2/spec.md` established this section for exactly
  this purpose.
- **Six user stories rather than three.** CP3 has six deliverables in the parent spec's
  checkpoint row, each independently testable and independently valuable. Collapsing them would
  hide that US5 alone is larger than the rest combined, which is the specification's most
  important scheduling signal.

**One decision is adopted but not confirmed.** D-1 (the batch tool's capability annotation) is
the only requirement in this document that the source explicitly routed to a maintainer. It is
adopted so planning is unblocked and is called out under "Open maintainer decision". Reversing
it before implementation is free; reversing it after CP3 ships is a caller-visible contract
event.

**Two obligations are gated on live probes, by design, not by omission.** FR-001/FR-002 and
FR-003 encode the parent spec's two "verify before CP3" questions. Both ship a requirement
either way — the probe tunes the wording, it does not decide whether the work happens. This is
the intended shape, not an unresolved clarification.
