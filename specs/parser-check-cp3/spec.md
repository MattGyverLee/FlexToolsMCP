# Feature Specification: parser-check CP3 -- the corpus, the artifact, and the diagnosis

**Feature Branch**: `feat/parser-check-cp3` (proposed; not created by this command)

**Created**: 2026-09-22

**Status**: Ready for planning -- the CP2 entry gate has lifted; six local decisions adopted below, one awaiting maintainer confirmation. Passed the `lex-domain` gate on the second pass; four blocking findings corrected in place (D-2, D-6)

**Input**: User description: "specs/parser-check/CP3-SPEC.md#L58"

**Source document**: [`../parser-check/CP3-SPEC.md`](../parser-check/CP3-SPEC.md) (887 lines)
**Parent spec**: [`../parser-check/SPEC.md`](../parser-check/SPEC.md), section 15, CP3 row
**Predecessors**: CP1 (`../parser-check/tasks.md`, T001-T035), CP2 + CP2a-bridge + CP2b
([`../parser-check-cp2/spec.md`](../parser-check-cp2/spec.md),
[`../parser-check-cp2b/spec.md`](../parser-check-cp2b/spec.md)) -- all landed on `main` at `e5afbfd`
**Successor**: CP4 is defined in GitHub issue #165, not in this spec tree. CP4 must not start before CP3 lands.

---

## Summary

CP1 proved the parser was reachable without ever constructing one. CP2 constructed one and
answered a question about a single word. **CP3 is the first checkpoint that answers a
question about a whole project**, and the first that leaves something behind: a durable run
artifact that other tools read.

A linguist can now point the assistant at a genre, a text, or an entire project and ask what
the parser makes of it -- then edit the grammar, ask again, and be told in plain terms what
got better, what got worse, and which words changed. Where the batch answer is not enough,
they can drill into one word's full search and see which rule licensed an analysis that
should never have existed.

CP3 is entirely read-only. Nothing it ships writes to a FieldWorks project. It computes two
projections that CP4's first write will consume, and acts on neither.

CP3 consumes CP2's job runner and **adds no second execution model**. A batch is that
runner's lower-priority path with per-wordform enqueue granularity. An implementation that
grows a second execution path fails review on that ground alone.

### What CP3 is not

- **Not a write.** No filing, no write ladder, no deletion, no confirmation flow. CP4.
- **Not the sandbox.** Sandbox-spine hardening, the sandbox tool, the configuration cache and
  corpus assertions are CP5. CP3 writes the in-process subset of the artifact set.
- **Not the counting trace instrument.** The parent spec defers it pending an engine seam that
  does not exist. CP3 must not reflect into engine internals to reach for it, and must not
  plan around that seam appearing.
- **Not grammar authoring.** Naming the loose rule is in scope; editing it is not.
- **Not a scalar grammar score.** The parent spec's measured anti-correlation result forbids
  one, and the shipped grammar scan already carries no severity and no verdict wording. CP3's
  reporting inherits that discipline rather than reintroducing severity.

---

## Entry gate -- satisfied

CP3 could not start until CP2's runner and the script library's parser surface existed. Both
are shipped. Verified against `main` at `e5afbfd`:

| Item | State |
|---|---|
| Script-library parser surface + the three companion read gaps | **Done** -- shipped in `pyflexicon` 4.9.0 |
| Declared floor raised to `pyflexicon>=4.9.0,<5` in both manifests, bundled index regenerated to match, floor/index equality test shipped | **Done** |
| `flextools_try_word`, all three answer levels, morph-spec resolver | **Done** -- verified live on two projects |
| Job runner, seven stages, grace window, cancellation, incremental run records, `flextools_parse_status` | **Done** |
| Suite green at the gate | **Done** -- 2070 passed, 8 skipped |
| Script-library `4.9.0` tag pushed | **Open, non-blocking** -- release commit exists; tagging is a maintainer act. The declared floor and the bundled index already agree at 4.9.0 |

**One CP2 question is answered and must not be re-litigated.** The shipped parser surface
returns the engine's own structured result, whose analyses carry live references to the
data-model objects for morph form, morph-syntax analysis and inflection type, while the
document-returning operations preserve those objects only as integer identifiers. **CP3's
reporting and diff bind to the structured result, never to the documents.** That is a fact
about shipped code, not a request.

**The floor/index hazard is closed and must stay closed.** CP3 generates scripts that call the
parser surface; an index that predates that surface would leave every generated CP3 script
written against an API the index cannot describe. The equality test that prevents recurrence
must not be weakened or skipped to land a CP3 change.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - "Which words am I actually asking about?" (Priority: P1)

A linguist wants the parser run over their folklore texts. They name the genre. The system
resolves that to a definite, ordered, de-duplicated list of words, tells them how many there
are, and records exactly what was resolved so a later run can be compared to this one. If the
genre name matches more than one genre they are asked which; if it matches none they are told
so in a way that does not blame their data. If a text in scope has never been opened for
interlinear work, they are told *that*, rather than being told it has no words.

**Why this priority**: Nothing batch can start until "which words" has one answer, and every
later story reads the resolved scope. It is also the slice with standalone value: even with no
batch parse, being able to ask "how many distinct words are in this genre, and in what order
of frequency" is useful on its own.

**Independent Test**: Resolve a scope by genre, by text, and across all texts on a live
project; confirm the word list, its ordering, its count and its recorded fingerprint without
ever starting a parse.

**Acceptance Scenarios**:

1. **Given** a text tagged with two genres, **When** the scope is resolved by the *second* of
   those genres, **Then** the text is included.
2. **Given** a genre string matching two genres, **When** the scope is resolved, **Then** the
   request is refused with both candidates named.
3. **Given** a resolved scope, **When** a word limit is applied, **Then** ordering by
   descending occurrence and then alphabetically happens *first*, the limit truncates
   afterwards, and the response records that truncation occurred.
4. **Given** a text never opened for interlinear work, **When** it is scoped, **Then** the
   response does not assert that the text has no words.
5. **Given** a text with no genres assigned, **When** its genres are read, **Then** an empty
   collection is returned and nothing raises.

---

### User Story 2 - "Parse my corpus, and don't lose the work if it dies" (Priority: P2)

The linguist starts a batch parse over the resolved scope. It may run for hours. While it runs
they can ask about progress, and can still ask an urgent single-word question without waiting
for the batch. They can cancel. If the machine runs out of memory at word four thousand, the
four thousand completed words are still readable afterwards, and the run says plainly how it
died. When it finishes, it has left behind a durable artifact that other tools read without
reopening the project.

**Why this priority**: This is the first job in the campaign that is not one word, and the
artifact it writes is a forward commitment -- CP4 and CP5 both read it. Its shape settles
before anything that consumes it is written.

**Independent Test**: Run a batch to completion on a live project, then run one that is killed
mid-flight, and confirm both leave a complete and a partial artifact respectively, each
readable and each stating its own terminal state.

**Acceptance Scenarios**:

1. **Given** a batch in progress, **When** a single-word request arrives, **Then** it is
   answered without waiting for the batch, and the batch resumes at its next word with its
   position and its loaded grammar intact.
2. **Given** a batch killed mid-run, **When** its artifact is read, **Then** every completed
   word is present and the run reports a terminal failure naming out-of-memory, crash or
   cancellation.
3. **Given** a batch that is cancelled, **When** it stops, **Then** it stops at the next word
   boundary and the partial results are retained under a cancelled state.
4. **Given** a run in progress, **When** progress is reported, **Then** the reported figure
   accounts for the single-word interleave rather than appearing to stall.
5. **Given** the active parser engine changes mid-job, **When** the run summarises, **Then**
   the change is a warning on the summary, not a refusal, and the engine recorded at
   submission is the one the results are labelled with.

---

### User Story 3 - "Show me what happened" (Priority: P3)

The linguist reads back a finished or failed run: the summary, the word list, the per-word
results, and where one was taken, a single word's full trace. Sections that belong to the
sandbox spine are not silently empty -- they say they do not apply to this kind of run and
which checkpoint will fill them. Where a trace can be read, one line names the blocking rule
or stage; where it cannot, the raw slice is returned and labelled as raw.

**Why this priority**: An artifact nobody can read is not an artifact. It is small, and it is
the surface every later story reports through.

**Independent Test**: Read every section of a completed in-process run and confirm each either
returns real content or an explicit not-applicable naming its spine.

**Acceptance Scenarios**:

1. **Given** an in-process run, **When** a sandbox-only section is requested, **Then** a typed
   not-applicable response names the spine and the checkpoint that will fill it.
2. **Given** an in-process run, **When** the results or word-list section is requested,
   **Then** real content is returned, paged.
3. **Given** a trace that cannot be parsed, **When** it is read, **Then** the raw slice is
   returned and explicitly labelled raw, with no explanation invented for it.

---

### User Story 4 - "Did my grammar edit help?" (Priority: P4)

The linguist parses, edits the grammar, parses again, and asks for the difference. They are
told which words newly parse, which stopped parsing, which parse *differently*, and which are
unchanged. A word that went from one analysis to seven is reported as changed, not unchanged
-- it still "parses", and the grammar got looser. If the two runs were not over the same
scope, the comparison is refused until they force it, and a forced comparison is done on the
intersection and says so.

**Why this priority**: This is the loop the whole feature exists to enable, and the first point
at which a grammar edit becomes measurable rather than felt. It depends on US2's artifact and
US1's fingerprint.

**Independent Test**: Baseline parse, deliberate grammar break, diff, revert, diff again, on a
live project; confirm the two diffs name the right words in the right buckets.

**Acceptance Scenarios**:

1. **Given** a word with one analysis before and seven after, **When** the runs are diffed,
   **Then** it is reported as changed.
2. **Given** two runs over different scopes, **When** they are diffed, **Then** the comparison
   is refused, naming which fields differ; **When** it is forced, **Then** it is performed on
   the intersection and the output says so.
3. **Given** a morph deleted and recreated between runs, **When** the runs are diffed, **Then**
   the affected analyses are labelled an identity change, neither reported as behaviourally
   changed nor silently collapsed to unchanged.
4. **Given** a project open in shared mode, **When** a diff reports no change, **Then** that
   result is downgraded to an unverifiable no-change and carries the shared-mode staleness
   marker.

---

### User Story 5 - "Which of these analyses are wrong, and why?" (Priority: P5)

Across the batch the linguist is shown where the grammar is producing too much: words with
many analyses, the same word attributed to different root entries, a root analysed as a stack
of affixes, the same surface form landing in incompatible categories, and how the distribution
of analysis counts shifted since the last run. Each signal is printed beside the legitimate
reason it might be a false alarm, because ambiguity is normal in many languages. Where human
analyses exist they are used as an oracle -- but only the ones that are actually comparable,
and the report never tells the linguist that a human "rejected" an analysis when the truth is
that nobody has looked at it yet.

**Why this priority**: This is the largest and most correctness-sensitive part of CP3 and it
depends on US2's artifact. It is also the part where a plausible, natural implementation
produces a confidently wrong answer, so it is sequenced where it can be planned as its own
phase rather than as one task.

**Independent Test**: Run the batch report against fixtures covering every completeness tier
and every stated false-positive case, and assert the exact wording of every mandated sentence.

**Acceptance Scenarios**:

1. **Given** a human analysis recording only meaning and no decomposition, **When** the oracle
   reports, **Then** it is named as such, is not counted as agreement or disagreement, and is
   not dropped.
2. **Given** a human analysis begun but not fully linked, **When** the oracle reports, **Then**
   it is named as such, with how many of its morphs are unlinked.
3. **Given** an analysis carrying no stored human opinion, **When** it is reported, **Then**
   the mandated sentence is rendered verbatim and the words "invalid", "incorrect", "rejected"
   and "flagged" appear nowhere near it.
4. **Given** an approved analysis that also occurs in a text, **When** the oracle reports,
   **Then** it falls in the separately named indeterminate population, and no individual
   analysis anywhere is labelled tacit, unreviewed or auto-approved.
5. **Given** a project on which the parser has never run, **When** the oracle is requested,
   **Then** it is reported as absent, not as a report in which everything reads unreviewed.
6. **Given** a non-compositional word whose correct analysis disagrees with the human gloss,
   **When** candidates are ranked, **Then** the correct analysis is not demoted below a
   compositional but wrong competitor.
7. **Given** four hundred words that look like overgeneration, **When** drill-down is proposed,
   **Then** the words are clustered and one to three representatives per cluster are
   recommended, rather than four hundred traces.

---

### User Story 6 - "This is taking forever -- is my grammar broken?" (Priority: P6)

A parse that should have been quick is not. Instead of the linguist waiting out a run that may
never finish, the system offers to spend one word finding out: it runs a single word to
completion under a hard bound and reports what that actually cost in wall-clock time. If it
blows the bound, that is the finding, not an error. Either way the system proposes the cheap
static grammar scan as the next step, with arguments the caller can use directly.

**Why this priority**: It closes the loop CP1 opened by shipping a grammar scan that had no
caller. It is the smallest part of CP3 and depends only on the runner.

**Independent Test**: Run the bounded single-word measurement against a known-slow grammar and
a known-fast one; confirm one produces a terminal measured result and the other does not
trigger the proposal.

**Acceptance Scenarios**:

1. **Given** a single-word measurement that exceeds its bound, **When** it terminates, **Then**
   it reports a terminal result carrying a wall-clock measurement, not an error, and not an
   invented internal step count.
2. **Given** a single-word request answered inside the fast-path window, **When** it responds,
   **Then** no grammar-scan proposal is attached.
3. **Given** a run that failed terminally, **When** it responds, **Then** a proposal names the
   bounded measurement or the static scan, with a mandatory cost estimate and directly usable
   arguments.
4. **Given** a project where a proposed next step is unreachable, **When** proposals are
   assembled, **Then** that step is not proposed, and no proposal ever names a tool that does
   not exist.

---

### Edge Cases

- A text in scope has paragraphs but has never been tokenized: the scope must not report it as
  having no words, and the refusal for a genuinely empty scope must not be reused for it.
- A genre string fails to match because the user's interface is localized and matching ran
  against the default analysis writing system: the response records that as a plausible reason
  rather than asserting no such genre exists.
- The same batch is run twice with a word limit over a differently ordered corpus: ordering is
  applied before truncation, so the two runs remain comparable.
- A run dies between two words: the per-word stream is valid up to its last complete record.
- A run dies during grammar loading and never reaches a first word: the artifact still states
  its terminal state and the stage it died in.
- A morph is deleted and recreated between two runs: identity changes, behaviour does not.
- The active parser engine is switched between two runs: the runs are never treated as the same
  scope.
- A project is opened in shared mode by someone else: nothing promises a safe read-back
  interval, because there is none.
- A word has one parser analysis and one human meaning-only record: a pairing is suggested,
  ranked first, and never filed.
- A derivable word whose parts do not add up to its recorded meaning: reported as a candidate
  lexicalized form, not as a parse error.
- The parser has never been run on this project at all: the oracle is absent, not degraded.
- A lexicon edit arrives while a parse job is running: it is not blocked.

---

## Requirements *(mandatory)*

### Functional Requirements

**Phase 0 -- the two live questions that come first (US1, US5)**

- **FR-001**: Before the scope layer's refusal wording ships, the system MUST establish
  whether a text that has never been opened for interlinear work is distinguishable, through
  the data model alone, from a text that genuinely contains no words. The finding MUST be
  recorded back into the parent spec's open-question register.
- **FR-002**: Regardless of that finding, the scope layer MUST perform a distinguishing read
  (a structural count that is non-zero while the unique-word count is empty) and MUST word its
  refusal conservatively. Treating an empty word count as proof of an empty text is the failure
  this requirement exists to prevent.
- **FR-003**: Before the oracle's provenance wording ships, the system MUST establish whether
  an analysis can be recorded against a text segment without any human act. The split itself
  MAY be built while this is outstanding; the description of what the indeterminate population
  contains MUST NOT ship until the answer is recorded.
- **FR-004**: The read-only project-state probe MUST be built exactly once and serve all three
  of its consumers -- the never-parsed warning, the oracle precondition, and the deletion
  projection precondition. CP4 MUST be able to consume it rather than growing a second one.

**Scope resolution (US1)**

- **FR-005**: The target word list MUST be taken from the data model's own unique-wordform
  enumeration, unioned across the selected texts exactly as the host application does. The
  system MUST NOT build its own corpus walk.
- **FR-006**: Genre selection MUST read the full set of genres assigned to a text, not only the
  first. A text tagged with two genres MUST be found by either of them.
- **FR-007**: Genre matching MUST be case-insensitive against both genre name and abbreviation.
  More than one match MUST refuse with an ambiguity code carrying every candidate.
- **FR-008**: Where a genre string fails to match, the response MUST record that matching ran
  against the default analysis writing system, so a user working in a localized interface sees
  a plausible reason rather than a bare assertion that no such genre exists.
- **FR-009**: The word list MUST be de-duplicated under NFC normalization and ordered by
  descending occurrence count, then alphabetically. Any caller-supplied limit MUST be applied
  *after* ordering, and the response MUST record that truncation occurred.
- **FR-010**: Every run MUST carry a scope fingerprint recording: the kind of scope, its value,
  the identifiers of the texts resolved, the de-duplicated word count before any limit, the
  limit and truncation flag, the parser engine recorded at submission, and the vernacular
  writing system the words were read in.
- **FR-011**: The scope fingerprint MUST NOT include anything describing the grammar. A grammar
  edit between two runs is the thing a comparison exists to measure, so folding grammar state
  into the fingerprint would refuse exactly the comparison the user wants.
- **FR-012**: Comparing two runs with differing fingerprints MUST refuse, naming which fields
  differ, unless the caller forces it. A forced comparison MUST be performed on the intersection
  only and MUST state that in its output.
- **FR-013**: This feature's own tests MUST pin the empty-collection contract of the genre read
  it consumes. That read shipped with no tests of its own, and CP3 is its first consumer.

**The batch job and its artifact (US2)**

- **FR-014**: A batch MUST execute on the existing job runner as its lower-priority path with
  per-wordform enqueue granularity. No second execution model may be introduced.
- **FR-015**: A run MUST write the in-process subset of the artifact set: the durable run
  record, the resolved word list, and a per-word result stream. Sandbox-spine files MUST NOT be
  written, and MUST NOT be created empty.
- **FR-016**: The durable run record MUST carry current job state, words completed against words
  total, the engine recorded at submission, the scope fingerprint, and on terminal failure the
  reason. It MUST be written incrementally rather than only at completion.
- **FR-017**: Where the run record's summary counters coincide with the host application's own
  parser report, they MUST adopt its names and semantics verbatim. Every deliberate divergence
  MUST be stated **in the artifact itself**, not only in this specification.
- **FR-018**: The counter reporting human-approved analyses the parser missed MUST be computed
  over fully linked human analyses only. Computing it over all human analyses silently
  reproduces the category error the tiering exists to prevent.
- **FR-019**: The no-stored-opinion counter MUST NOT be presented, named or documented as a
  count of unreviewed analyses. The affirmed/indeterminate split MUST be carried beside it.
- **FR-020**: Per-word results MUST be appended as each word completes, so the stream is valid
  up to its last complete record and a job that dies at word four thousand leaves four thousand
  usable results.
- **FR-021**: Live data-model object references MUST NOT be serialized into any artifact. The
  durable signature and enough rendered text to report without reopening the project MUST be
  serialized instead; live references are kept only within the run.
- **FR-022**: Run identifiers MUST keep the form CP2b already ships and MUST NOT be re-minted into
  a timestamped form. Run retention MUST keep the newest twenty runs per project, ordered by
  **recorded creation time**, never by a lexicographic sort of run-identifier directory names. The
  existing backup pruner's keep-newest-N policy is adopted; its name-sorting mechanism is **not**,
  because it is sound only for timestamp-named directories and run directories are opaque hex.
- **FR-023**: The system MUST capture its own grammar load-error baseline at its own grammar
  load, persist it in the run record, and key it to the scope fingerprint. CP3 is the first
  checkpoint that loads a grammar for a batch, so CP3 is where the baseline is captured; CP4's
  refuse-to-file gate is specified against this baseline and explicitly not against the host
  application's provenance-blind error file.
- **FR-024**: The parser-engine capability check MUST be the first statement of the batch
  handler, before any parser is constructed. For a batch it fires **once, at submission**. The
  reading, comparison and log tools MUST NOT call it -- they read prior artifacts and never
  touch the engine. An engine change mid-job is a warning on the run summary, not a refusal.
- **FR-025**: The batch tool MUST be annotated at its designed maximum capability -- not
  read-only-safe -- from its first release, and that annotation MUST NOT change at CP4. The
  argument that unlocks filing MUST be absent from the schema until the code that implements it
  ships. The tool description MUST state, in its first line, the spine and that filing is not
  yet reachable.
- **FR-026**: Reported batch progress MUST account for single-word requests interleaving ahead
  of it, rather than appearing to stall.
- **FR-027**: At most one loaded grammar is held; a single-word request interleaving into a
  running batch MUST use that same loaded grammar and MUST NOT trigger a reload.

**Reading a run back (US3)**

- **FR-028**: The log tool MUST serve the summary, word-list, per-word-result and trace sections
  for in-process runs. For every sandbox-spine section it MUST return a typed
  not-applicable-for-this-spine response naming the spine and the checkpoint that will fill it.
  It MUST NOT return an empty section, which reads as "nothing happened".
- **FR-029**: Where a trace is parseable, the system MAY name the blocking rule or stage in one
  line. Where it is not, it MUST return the raw slice and MUST label it as raw. No explanation
  may be invented for output the system could not read.

**Comparing two runs (US4)**

- **FR-030**: A comparison MUST classify each wordform as newly parsing, no longer parsing,
  parsing differently, or unchanged. Two runs that both produce analyses but produce *different*
  analyses MUST NOT be reported as unchanged. An implementation that compares counts alone must
  fail its test.
- **FR-031**: The durable analysis signature MUST be the ordered sequence of
  (morph-form identifier, morph-syntax-analysis identifier, **inflection-type identifier**)
  triples, expressing the host application's own match predicate in a form that survives
  serialization rather than inventing a parallel normalization. Rendered morph forms and category
  labels MUST be carried alongside it, so a report renders without reopening the project and a
  signature is legible.
- **FR-031a**: The host predicate carries a fourth component the signature cannot reproduce: where
  a parser morph proposes a guessed surface form, the predicate additionally requires that form to
  match one of the bundle's writing-system alternatives. A serialized signature has no access to
  that comparison. The system MUST therefore record, per analysis, whether any of its morphs
  carried a guessed form, and where one did, a comparison MUST report the match as **provisional**
  rather than asserting behavioural identity. Omitting this component silently -- and thereby
  claiming alignment with a predicate the signature does not actually reproduce -- is the failure
  this requirement exists to prevent.
- **FR-032**: Where two runs' analyses have identical rendered forms but different identifiers,
  the system MUST label this an identity change rather than a behavioural one, and MUST NOT
  collapse it to unchanged -- something did change in the lexicon.
- **FR-033**: If identifier stability across sessions is not confirmed by live verification, the
  signature MUST fall back to rendered form plus category label, and the resulting ambiguity
  MUST be stated in the report.
- **FR-034**: Where project access reports shared or held-by-another, the comparison MUST carry
  a shared-mode staleness marker, carry the save-or-close note, and downgrade a no-change result
  to an unverifiable no-change. The system MUST NOT promise any safe read-back interval.

**Batch signals and the oracle (US5)**

- **FR-035**: Batch signals MUST be computed from the parser's typed structured output, never
  from its document form.
- **FR-036**: Five signals MUST ship: analyses per word, disagreement over which root entry a
  word belongs to, a root analysed as a stack of affixes, the same surface form in incompatible
  categories, and the distribution of analysis counts. Each MUST print its legitimate
  false-positive explanation **in the output**, because a high count is not by itself a defect.
- **FR-037**: The count distribution MUST be presented as a comparison instrument, not a verdict.
  A rightward shift after an edit is evidence something got looser.
- **FR-038**: An analysis's completeness tier MUST be derived from the public per-bundle
  completeness flag plus the bundle count. The system MUST NOT reimplement the host
  application's internal fully-formed predicate.
- **FR-039**: Only fully linked human analyses may enter the approval comparison. Meaning-only
  and partially linked analyses MUST be reported separately **and by name**, never folded into a
  count, never dropped, and never rendered as disagreement with the parser.
- **FR-040**: Every mandated output sentence MUST be rendered verbatim, not paraphrased, for all
  six cases. The words "invalid", "incorrect", "rejected" and "flagged" MUST NOT be applied to
  an analysis carrying no stored opinion.
- **FR-041**: On a project the parser has never run against, the oracle MUST be reported as
  **absent**, with its own sentence, rather than emitting a report in which every analysis reads
  as unreviewed.
- **FR-042**: The approval-provenance join MUST be implemented as one-sided: approved and not
  occurring in any segment is reliably affirmed; approved and occurring in a segment is
  unknowable. The split MUST be reported as affirmed against indeterminate, and MUST NOT be
  reported as affirmed against tacit. No individual analysis may be labelled tacit, unreviewed
  or auto-approved.
- **FR-043**: The segment-occurrence join MUST be built once and structured for reuse. CP4's
  deletion projection is the same join used for the opposite purpose; a CP4 that rebuilds it is
  a review finding.
- **FR-044**: Where one parser analysis meets one human meaning-only record, the system MUST
  surface a candidate pairing, rank it first, name its confidence basis, and word it as a
  suggestion. It MUST never be filed automatically.
- **FR-045**: Ranking MUST be promotion-only: agreement between a composed gloss and the human's
  gloss raises an analysis; disagreement MUST NOT lower one. Everything not promoted keeps its
  original order. An implementation that sorts by gloss distance is wrong and must fail review.
- **FR-046**: A word the parser can derive whose parts do not add up to its recorded meaning
  MUST be reported as a candidate lexicalized form, using the mandated wording, not as a parse
  error.
- **FR-047**: Drill-down tracing MUST be capped per session at a user-chosen figure in the range
  ten to twenty words, and MUST NEVER be auto-traced in bulk.
- **FR-048**: Where many words look like overgeneration, the system MUST report the batch
  summary, cluster the words by shared root entry or category pair, and recommend tracing one to
  three representatives per cluster.
- **FR-049**: Rule attribution MUST be performed by side-by-side comparison of one word's
  competing rule chains. The engine's pre-parse morph filter MUST NOT be treated as an
  attribution mechanism; its only legitimate use here is narrowing a candidate set by
  subtraction.
- **FR-050**: The system MUST compute, and MAY report as information, the deletion projection
  (parser-created **and** carrying no user opinion **and** not referenced by any segment) and the
  duplicate projection (how many filings would duplicate an existing meaning-only record). It
  MUST NOT act on either, MUST NOT confirm, and MUST NOT ship any part of the write ladder.

**The bounded measurement and routing (US6)**

- **FR-051**: The bounded single-word measurement MUST run as its own job at the runner's
  highest word priority, in a worker the supervisor is willing to terminate. It MUST NOT share a
  worker with a batch.
- **FR-052**: Because the engine offers no cancellation, timeout or step budget, the bound MUST
  be enforced at process level using the existing process-tree termination helper. No in-parse
  enforcement may be claimed.
- **FR-053**: The reported cost MUST be wall-clock time plus whether the fast-path window was
  missed and by how much. It MUST NOT report an engine step or node count, because no such
  number exists.
- **FR-054**: A measurement terminated at its bound MUST be reported as a terminal **result**
  carrying its measurement, not as an error.
- **FR-055**: The system MAY read and report the stored parser parameters as context for a slow
  parse. It MUST NOT write them; that is a project-data write and this checkpoint has none.
- **FR-056**: A next-step proposal for the static grammar scan MUST fire on: a single-word
  request that misses the fast-path window, a batch that enters grammar loading and stays there,
  a terminal failure, and a bounded measurement that exceeds its bound. It MUST NOT fire on a
  request answered inline, and MUST NOT be attached to every response.
- **FR-057**: Every next-step proposal MUST carry a mandatory cost estimate, where "unbounded" is
  a legitimate value; MUST carry arguments the caller can use directly without reconstruction;
  MUST NOT propose a step the project cannot reach, including any filing step, which at CP3 is
  every session; MUST NOT name a tool that does not exist; and where a trace and the static scan
  are both candidates, MUST propose the static scan first because it is cheaper than the trace it
  may make unnecessary.
- **FR-058**: Every next-step row left pointing at a null tool because the tool did not yet exist
  MUST be revisited for the tools CP3 ships, and none may still be null for a shipped tool.

**Cross-cutting**

- **FR-059**: Five refusal codes MUST be added -- empty scope, ambiguous scope, scope mismatch,
  parse timeout, and job failure -- additively, so the tool-response contract stays at its
  current major version. The documented code count MUST rise from twenty-five to thirty, with one
  changelog entry under the tool-contract heading.
- **FR-060**: Each new code's detail model MUST forbid extra fields and MUST carry a row in the
  tool-contract document, matching the shape CP1 established.
- **FR-061**: A running parse job MUST NOT block a lexicon edit or a human analysis write. No
  project-wide claim may be introduced. This is a standing regression test, not a one-off check.
- **FR-062**: The three grammar lints deferred at CP1 and again at CP2 MUST either be folded in
  here, if the host library exposes its checker publicly, or their continued deferral MUST be
  recorded with a reason. A row that moves checkpoint a third time with no recorded reason is
  drift.
- **FR-063**: No code path shipped by CP3 may write to a FieldWorks project. This MUST be
  asserted by a standing test, not only by inspection.

### Key Entities

- **Scope**: what the user asked to parse -- all texts, a genre, a text, or an explicit word
  list -- together with the texts it resolved to.
- **Scope fingerprint**: the durable description of a resolved scope, sufficient to decide
  whether two runs are comparable, and deliberately silent about the grammar.
- **Word list**: the de-duplicated, normalized, ordered target words, plus whether a limit
  truncated them.
- **Run**: a unit of batch parser work with a handle, a stage, progress, a terminal outcome, and
  a durable home on disk.
- **Run record**: the incrementally written summary and job state of a run, aligned with the host
  application's own parser report where the two coincide and explicit where they do not.
- **Per-word result**: one word, its analysis count, and for each analysis a durable signature
  plus enough rendered text to report from.
- **Durable analysis signature**: the identity of an analysis in a form that survives the project
  being closed.
- **Load-error baseline**: what went wrong when *this system* loaded the grammar for this run,
  keyed to the fingerprint, captured for a gate that does not exist yet.
- **Batch signal**: one observation about the corpus, inseparable from the legitimate reason it
  might be a false alarm.
- **Completeness tier**: how far a human got with an analysis -- nothing, meaning only, sketched,
  or fully linked -- and therefore whether it can serve as an oracle at all.
- **Approval provenance**: the affirmed/indeterminate split, and the one-sided join that is the
  only available discriminator.
- **Candidate pairing**: a suggested correspondence between one parser analysis and one human
  record, carrying its confidence basis and no authority.
- **Drill-down trace**: one word's entire search, taken deliberately and rarely.
- **Cluster**: a group of suspect words sharing a root entry or category pair, standing in for
  the single loose rule that probably produced them all.
- **Projection**: a computation of what a future write *would* do, reported as information and
  acted on by nothing in this checkpoint.
- **Next-step proposal**: a conditional, costed, directly-usable suggestion of what to do next.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A text carrying two genres is found by either genre name in 100% of cases; the
  first-genre-only failure mode is 0 occurrences, asserted by a regression test.
- **SC-002**: Scope resolution over a live project returns a word list whose ordering and
  truncation are reproducible across repeated runs -- identical input yields an identical list
  and an identical fingerprint, 100% of the time.
- **SC-003**: A never-tokenized text produces 0 responses asserting the text has no words.
- **SC-004**: A batch killed at any point after its first completed word leaves 100% of its
  completed words readable, and reports a terminal state naming how it died.
- **SC-005**: An urgent single-word request issued during a running batch is answered without
  waiting for the batch to finish, and the batch afterwards resumes at its next word with 0
  grammar reloads.
- **SC-006**: For a batch plus one interleaved single-word request, the grammar is loaded exactly
  once.
- **SC-007**: Every sandbox-spine log section returns an explicit not-applicable naming its spine
  -- 0 sections return empty content.
- **SC-008**: A word going from one analysis to seven is classified as changed in 100% of cases;
  a count-equality implementation fails this assertion.
- **SC-009**: Across a live break-then-revert cycle, the comparison names the deliberately broken
  word in the no-longer-parsing bucket and, after revert, in the newly-parsing bucket, with 0
  false members in either bucket.
- **SC-010**: Identifier churn with unchanged rendered forms is reported as an identity change in
  100% of cases, and as behavioural change in 0.
- **SC-011**: Every one of the six mandated oracle sentences is rendered verbatim; the words
  "invalid", "incorrect", "rejected" and "flagged" appear 0 times in connection with an analysis
  carrying no stored opinion.
- **SC-012**: Across all outputs, 0 individual analyses are labelled tacit, unreviewed or
  auto-approved.
- **SC-013**: On a project the parser has never run against, the oracle is reported absent in
  100% of cases and degenerate all-unreviewed reports are emitted 0 times.
- **SC-014**: In the non-compositional ranking fixture, the correct analysis is ranked above the
  compositional-but-wrong competitor, and a sort-by-gloss-distance implementation fails the
  assertion. This is the single most important regression test in CP3.
- **SC-015**: The deletion projection over a fixture holding one segment-referenced and one
  unreferenced candidate returns exactly one; a bare no-opinion projection returns two and fails.
- **SC-016**: A drill-down session traces at most the user-chosen cap; bulk auto-tracing occurs 0
  times regardless of how many words look suspect.
- **SC-017**: A bounded measurement terminated at its bound is reported as a result rather than an
  error in 100% of cases, and reports 0 invented engine step counts.
- **SC-018**: A request answered inside the fast-path window carries 0 grammar-scan proposals; one
  that misses it carries exactly one.
- **SC-019**: Across every response the feature can emit, next-step proposals name a nonexistent
  tool 0 times and omit a cost estimate 0 times.
- **SC-020**: A running parse job blocks a concurrent lexicon edit 0 times.
- **SC-021**: No code path shipped by this checkpoint writes to a FieldWorks project -- 0
  occurrences, asserted by a standing test.
- **SC-022**: Live verification passes on both designated parser-configured projects, and the
  full suite is green including CP1's and CP2's standing groups.

---

## Assumptions

- **Object identifiers are stable within a project across sessions.** The durable signature rests
  on this. It is asserted by the source document and not yet verified; FR-033 specifies the
  fallback if live verification disproves it.
- **The bounded measurement's worker can be terminated without collateral damage**, because it
  runs alone rather than sharing with a batch.
- **Drill-down demand is low.** The cap of ten to twenty words per session assumes tracing is
  deliberate and rare; clustering is what makes the cap usable rather than merely restrictive.
- **Clustering by shared root entry or category pair actually groups the symptoms of one loose
  rule.** This is the premise that makes representative tracing worth recommending; it is an
  empirical bet, and a cluster that does not behave this way costs the user one wasted trace, not
  a wrong answer.
- **Twenty runs per project is enough retention** for the edit-then-compare loop, matching the
  existing backup retention rather than inventing a second policy.
- **Genre matching against the default analysis writing system is acceptable for CP3**, with the
  limitation disclosed in the response. A writing-system fallback is not in scope here.
- **The parser-configured verification projects remain available.** The campaign's designated
  correctness and scale projects are assumed present; the project reporting a different parser
  engine is deliberately excluded, because this feature's own engine gate would refuse it.
- **CP2's runner is sufficient for batch work as shipped.** CP3 budgets no runner changes beyond
  per-wordform enqueue; if the runner needs structural change, that is a finding to escalate
  rather than to absorb.

---

## Dependencies

- **`pyflexicon` 4.9.0** -- the parser surface and the three companion read gaps. Declared floor
  and bundled index already agree at this version; the equality test that keeps them agreeing is a
  standing obligation, not a one-time check.
- **CP2's job runner and single-word tool** -- consumed as shipped.
- **CP1's grammar scan** -- CP3 is its first caller.
- **CP1's parser capability check and engine gate** -- called first in the batch handler.
- **The existing backup pruner and process-tree termination helper** -- reused rather than
  reimplemented.
- **The tool-contract document and changelog** -- updated additively for five new codes.
- **The release tag for the script library's 4.9.0** -- outstanding, maintainer-owned, and
  non-blocking for CP3.

---

## Verbatim Constraints

Values the source and parent documents pin exactly. Downstream steps must use these strings as
written, not paraphrases of them.

- New assistant tools: `flextools_parse_text`, `flextools_parse_log`, `flextools_parse_diff`
- New refusal codes, with their detail fields **in this exact order** -- transcribed from the
  parent spec and verified against it, because CP2's own field-order divergence cost two crew
  cycles and happened during transcription, not because the source was wrong:

  | Code | Detail fields, in order |
  |---|---|
  | `parse_scope_empty` | `scope`, `matched_texts`, `hint` |
  | `parse_scope_ambiguous` | `scope`, `requested`, `candidates` |
  | `parse_scope_mismatch` | `baseline_fingerprint`, `current_fingerprint`, `differing_fields`, `hint` |
  | `parser_timeout` | `timeout_seconds`, `words_completed`, `run_id`, `hint` |
  | `parser_job_failed` | `state_at_failure`, `failure`, `words_completed`, `words_total`, `run_id`, `log_path` |
- Job-failure reasons, exactly these: `out_of_memory | crashed | cancelled`
- Log sections, exactly these:
  `summary | config_generation | hc_stdout | hc_output | trace | words | results`
- Comparison buckets, exactly these: `fixed | broken | changed | unchanged`
- Shared-mode markers: `staleness: "shared_mode_unverifiable"`, and `no_change` downgraded to
  `no_change_unverifiable`
- Provenance split, exactly this pair: `{affirmed, indeterminate}` -- never `{affirmed, tacit}`
- Run identifier form: **32 lowercase hex characters**, as shipped by CP2b's `new_run_id()`
  (`secrets.token_hex(16)`, validated by `\A[0-9a-f]{32}\Z`). It carries **no timestamp** -- see D-6
- Artifact files written at CP3, **as CP2b already names them on disk**: `meta.json` (the durable
  run record), `results.jsonl` (the per-word stream), `traces/<n>.xml` (out-of-line trace payloads,
  written only where a drill-down was taken), and `words.txt` (the resolved word list -- the one
  genuinely net-new file). See D-6: these differ from the parent spec's section 5.5 listing, and
  the parent spec is the document that is wrong
- Counters adopted verbatim from the host application's parser report: `NumWords`,
  `NumParseErrors`, `NumZeroParses`, `TotalParseTime`, `TotalAnalyses`,
  `TotalUserApprovedAnalysesMissing`, `TotalUserDisapprovedAnalyses`,
  `TotalUserNoOpinionAnalyses`
- Tool-contract code count: **25 -> 30**, contract remains `tool-responses/1.0`
- Retention: newest **20** runs per project
- Drill-down cap range: **10-20** words per session, chosen by the user
- Live verification projects: `IndonesianHC-Complete` (correctness),
  `Malay Parsing-20230810withHC` (scale). **Not `Sena 3`** -- it reports engine `XAmple` and this
  feature's own engine gate would refuse it
- Standing test that must stay green: `HCParser_DoesNotLoadXCore`
- Mandatory oracle wording, rendered verbatim, all six cases:
  - Approved and not in any segment: `"Approved by [user] on [date]."`
  - Approved but occurring in a segment: `"Approved under [user] on [date]. This analysis is in
    use in a text, and approval is recorded for anything left in use -- so it may have been
    affirmed, or merely used. There is no way to tell which."`
  - Disapproved: `"Marked incorrect by [user] on [date]."`
  - No stored opinion: `"Not yet reviewed by a human -- this is not evidence it is wrong, only
    that nobody has checked it."`
  - Meaning only: `"A human recorded what this word means, but not how it decomposes -- there is
    no morphology here to compare the parser against."`
  - Sketched but unlinked: `"A human began a morphological analysis but did not finish linking it
    -- [N] of [M] morphs are not linked to a lexical entry, so it cannot be compared to the
    parser's output."`
- Mandatory population sentence, rendered verbatim: `"[N] analyses carry a human approval. [M] of
  those appear in a text, where approval is recorded for anything left in use -- so some of those
  were used rather than affirmed. There is no way to tell which."`
- Forbidden words applied to an analysis carrying no stored opinion: `invalid`, `incorrect`,
  `rejected`, `flagged`

---

## Decisions

The source document carried seven local open questions. Five are resolved below. Two are carried
as disclosed limitations rather than decisions, and are recorded under Risks.

### D-1 -- The batch tool is annotated destructive from day one, with no filing argument

**Decision**: adopt the source document's option (c). `flextools_parse_text` ships annotated at
its designed maximum capability, not as read-only-safe, and the argument that unlocks filing is
**absent from the schema** until CP4 implements it. Requirement FR-025.

**Why**: a capability annotation is cached by hosts and read by calling models, so flipping it at
CP4 is a caller-visible contract event for a tool that did not change its name. Option (b) --
accept the argument and always refuse it -- advertises an argument that never works, and a model
reading the schema will try it. Adding a parameter at CP4 is additive and non-breaking; changing
an annotation is not.

**Why overstating is cheap here specifically**: the parent spec's warning against overstating was
made about the single-word tool, where a wrongly-destructive annotation throttles the cheap
hypothesis loop that tool exists to enable. A batch corpus parse runs for hours and has no such
loop to throttle, so the cost of overstating is close to zero while the cost of a flip is not.

**What it costs**: for one checkpoint the annotation is more alarming than the code. FR-025
requires the tool description's first line to state that filing is not yet reachable, because a
description promising a write the schema cannot express is the invent-nothing rule turned against
our own surface.

**Status: adopted here, maintainer may overturn.** This is the only place CP3 deliberately
overstates a capability, and the source document flagged it as needing a maintainer call. See
"Open maintainer decision" below.

### D-2 -- The durable signature is the ordered identifier-triple sequence

**Decision**: express the host application's own analysis-match predicate as the ordered sequence
of (morph-form identifier, morph-syntax-analysis identifier, inflection-type identifier) triples,
carrying rendered forms and labels alongside, and carrying a provisional marker for the one
component that cannot be serialized. Requirements FR-031, FR-031a, FR-032, FR-033.

**Why**: the parent spec says to align on the host's match predicate rather than invent a
normalized signature, and that predicate is ordered object identity. But a comparison runs across
two *runs*, and a run persisted to disk holds no live objects -- so identity has to survive
serialization. The identifier-triple sequence is that same predicate expressed durably, which is
what alignment actually requires; a parallel normalization would be the thing the parent spec
rejected.

**Corrected after the domain gate.** This decision originally specified a two-component
(form, morph-syntax-analysis) pair. The host predicate compares **four** components, not two: it
also requires inflection-type identity and, where a parser morph carries a guessed form, a
writing-system-alternative match on that form. A two-component signature would have collapsed two
analyses differing only in inflection type -- a real case, since irregularly inflected forms carry
a non-null inflection type -- into one, reporting **unchanged** across runs for analyses that
genuinely differ. Since the whole point of this decision is to express the host's predicate rather
than a weaker parallel one, the omission would have falsified the decision's own rationale.
Inflection type is now in the signature; the guessed-form component is disclosed by FR-031a rather
than silently dropped, because it is genuinely not serializable.

**What it costs**: identifier churn -- a morph deleted and recreated -- produces a false
behavioural change. FR-032 requires it to be detected by identical rendered forms under differing
identifiers and labelled an identity change. Collapsing it to unchanged would be wrong in the
other direction: something really did change in the lexicon. The underlying stability assumption
is unverified and FR-033 specifies the fallback.

### D-3 -- The scope fingerprint's field set

**Decision**: the eight fields of FR-010, with grammar state deliberately excluded and the
load-error baseline carried *beside* the fingerprint rather than inside it. Requirements FR-010,
FR-011, FR-023.

**Why**: the parent spec requires runs to carry a fingerprint and requires a mismatch refusal to
name which fields differ, but never defines the field set, so it is defined here for the first
time. Text identifiers are included so that a text added to a genre shows up as a difference.
The engine is included because a run on one engine and a run on another are never the same scope.
The limit and its truncation flag are included because a truncated run is not comparable to a
full one.

**Why grammar state is excluded**: a grammar edit between two runs is precisely what the
comparison exists to measure. Folding a grammar hash into the fingerprint would make every
interesting comparison refuse.

### D-4 -- The bound on the single-word measurement is enforced at process level

**Decision**: the bounded measurement runs as its own job, alone in a worker the supervisor may
terminate, and the bound is enforced by terminating that process tree. Reported cost is
wall-clock. Requirements FR-051 through FR-054.

**Why**: the parent spec verified there is no cancellation token, timeout or step budget anywhere
on the engine's parse path, and the runner's cooperative cancellation lands at the *next word
boundary* -- which for a single-word parse is after the parse it was meant to bound. Process-level
termination is the only enforcement that exists. It must not share a worker with a batch, because
terminating it would take the batch with it.

**What it costs**: the measurement is wall-clock only. FR-053 forbids reporting an engine step or
node count, because no such number is available and inventing one is the failure mode this
campaign names most often. A terminated measurement is a result, not an error: "this grammar did
not finish one word in N seconds" is exactly the finding.

### D-5 -- Cluster keying and representative selection

**Decision**: cluster suspect words by shared root entry first, falling back to category pair
where no root entry is shared. Within a cluster, recommend as representatives the words with the
highest analysis counts, ties broken by the word list's existing order, capped at three.
Requirement FR-048.

**Why**: the source document names "cluster by shared root entry or category pair" as the rule but
specifies neither the tie-breaking nor the representative selection, and leaves that gap open.
Root entry is the stronger key because a single loose rule attached to one entry is the shape the
clustering is built to catch; category pair catches the rule that is not entry-specific. Highest
analysis count is chosen as the representative because the most over-generated word exercises the
most of the suspect rule chain in one trace.

**What it costs**: this is a heuristic and it is stated as one in the output. A cluster whose
representative does not reproduce the problem costs the user one wasted trace, which is why the
cap is three rather than one.

### D-6 -- The artifact layout is CP2b's as shipped; the parent spec's file listing is the thing that is wrong

**Decision**: CP3 adopts the run-directory layout the CP2b runner already writes -- `meta.json`
for the durable run record, `results.jsonl` for the per-word stream, `traces/<n>.xml` for
out-of-line trace payloads -- and adds exactly one net-new file, `words.txt`, for the resolved word
list. The parent spec's section 5.5 listing (`run.json`, a flat `trace.txt`, and four sandbox
files) is corrected to match, rather than the shipped code being renamed to match it.
Requirements FR-015, FR-016, FR-020, FR-022, FR-028.

**Why**: the parent spec's file listing was written before CP2b existed and describes a layout
that was never built. CP2b shipped `record.py` at `e5afbfd` with different names, and that code is
the thing CP3 is required to consume without adding a second execution model. Renaming shipped
files at CP3 would be churn on an artifact CP4 and CP5 both read, to satisfy a listing that no
code has ever matched. Out-of-line per-analysis traces are also the better design on their own
merits -- a trace payload is large, and a flat `trace.txt` would force every run to carry every
trace in one file.

**Three factual corrections this decision carries**, each caught by the domain gate and each
originating in the source document rather than in this specification:

1. **`results.jsonl` is not net-new.** The source document calls it net-new and files it as an
   open question; it shipped with CP2b. Only `words.txt` is genuinely new, and the word list has
   no persistence today.
2. **The run identifier carries no timestamp.** The source document specifies a
   timestamp-plus-suffix form; CP2b mints 32 random hex characters. FR-022 now keeps the shipped
   form.
3. **The retention pruner's mechanism does not transfer.** The existing backup pruner sorts
   directory names lexicographically, which is chronological *only because* backup directories are
   timestamp-named. Run directories are opaque hex, so the same sort would prune in effectively
   random order. FR-022 adopts the policy and rejects the mechanism.

**What it costs**: one correction to the parent spec's section 5.5, which must land with CP3
rather than being left as a silent divergence. A future reader comparing the parent spec to the
disk would otherwise conclude the implementation drifted, when the opposite happened.

---

## Open maintainer decision

**D-1's annotation call.** Everything else in this specification either follows from the parent
spec or is a local decision with a clear default. D-1 is the one place CP3 deliberately ships an
annotation stronger than its code, and the source document explicitly asked for a maintainer call
rather than a recommendation. It is adopted here so planning is not blocked; overturning it before
implementation costs nothing, and overturning it after CP3 ships costs a caller-visible contract
event -- which is the exact cost D-1 exists to avoid.

---

## Risks

- **Promotion-only ranking is the correctness risk, and it is concentrated in one function.** The
  natural implementation -- sort candidates by gloss distance -- produces a confidently wrong
  answer about the correct analysis of exactly the words a linguist cares most about, because
  morphology is not reliably compositional. It must be tested before it is written, not after.
  SC-014 is the guard.
- **The batch report is the scope risk.** Five batch signals, four completeness tiers, the
  provenance join, candidate pairing, promotion-only ranking, the lexicalization finding, the
  side-by-side chain comparison and the clustering are eight distinct pieces of build under one
  user story, and the chain comparison alone is net-new rather than a presentation of something the
  engine already returns. It is larger than every other part of CP3 combined and must be planned as
  its own phase.
- **The artifact is a forward commitment.** CP4 and CP5 both read the run record and the per-word
  stream. A shape chosen loosely here is migrated twice later, which is why FR-015 through FR-023
  settle before anything that consumes them is written.
- **The oracle's wording is a user-trust risk, not merely a correctness one.** Telling a linguist
  that a human never reviewed an analysis they did in fact review is the error a user is most
  likely to notice and least likely to forgive.
- **Two known limitations are carried, not solved.** Genre matching against the default analysis
  writing system may miss a user working in a localized interface (FR-008 discloses it rather than
  fixing it), and the three grammar lints have now been deferred twice (FR-062 forces a fold-in or
  a recorded reason rather than a third silent move).
- **The three read gaps CP3 consumes shipped with no tests of their own and no live exercise.**
  CP3 is their first real consumer, so this feature's tests are the first pin on their contracts
  and should be written as if they belonged to the library. FR-013 makes that explicit for the
  genre read.
- **Identifier stability is assumed, not proven.** FR-033's fallback exists precisely because the
  assumption may not survive live verification, and the fallback is materially weaker.
- **The parent spec's section 5.5 file listing is now known to be wrong** and must be corrected as
  part of CP3 (D-6). Left uncorrected, the next reader comparing that listing to the disk concludes
  the implementation drifted, when in fact the listing describes a layout no code ever wrote.
- **The source document was written against the parent spec rather than against shipped code.**
  Three of its factual claims -- that `results.jsonl` is net-new, that run identifiers carry a
  timestamp, and that the backup pruner's sort transfers -- were false by the time CP2b landed.
  Planning should re-verify any remaining source-document claim about on-disk shape against
  `record.py` rather than against the source document.
