# Feature Specification: parser-check CP2 -- the read spine goes live

**Feature Branch**: `feat/parser-check-cp2` (proposed; not created by this command)

**Created**: 2026-09-18

**Status**: Ready for planning -- all three open questions resolved

**Input**: User description: "CP2 of D:\Github\_Projects\_LEX\FlexToolsMCP\specs\parser-check\CP2-SPEC.md"

**Source document**: [`../parser-check/CP2-SPEC.md`](../parser-check/CP2-SPEC.md) (483 lines)
**Parent spec**: [`../parser-check/SPEC.md`](../parser-check/SPEC.md), section 15, CP2 row
**Predecessor**: CP1 (`../parser-check/tasks.md`, T001-T035)

---

## Summary

CP1 proved the parser *could* be driven -- located, capability-probed, engine-gated
-- without ever constructing one. CP2 constructs one. For the first time a user can
ask the assistant "does this word parse, and if not, why?" and get an answer that
came from FieldWorks' own parser rather than from a guess.

CP2 is entirely read-only. Nothing it ships writes to a FieldWorks project.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - A generated script can reach the parser safely (Priority: P1)

A linguist asks the assistant for a FLExTools module that checks whether words
parse. The assistant generates a module that uses the ordinary project object the
module already receives, and the parser is simply another area of that object --
alongside lexicon, grammar and texts. On a machine where the parser component is
missing, relocated or belongs to a different FieldWorks installation, the module
still loads and reports "parser unavailable" in plain words, rather than failing to
import at all and taking every unrelated feature down with it.

**Why this priority**: Every later story routes through this surface. It is also the
only slice with standalone value on day one -- module authors gain read-only parser
access even if no new assistant tool ever ships -- and it is the slice that must be
released to a package index before anything else can be tested against a real
dependency.

**Independent Test**: Install the released library on a machine with no parser
component present, import it, and confirm the import succeeds and parser access
reports unavailable. Then on a machine with a working parser, call each read
operation from a plain script and confirm results come back.

**Acceptance Scenarios**:

1. **Given** a machine where the parser component is absent or has been moved,
   **When** a script imports the project library, **Then** the import succeeds and
   the parser area reports itself unavailable with a reason, raising nothing.
2. **Given** a machine where the parser component belongs to a *different*
   FieldWorks installation than the one supplying the data model,
   **When** a script asks for the parser, **Then** access is refused and the reason
   names the mismatch of installations.
3. **Given** a working installation whose parser reports a version nobody has seen
   before, **When** a script asks for the parser, **Then** access is granted and the
   version is reported but never used to decide anything.
4. **Given** a text tagged with more than one genre, **When** a script asks for that
   text's genres, **Then** every genre is returned, not only the first.
5. **Given** an allomorph, **When** a script asks which entry owns it, **Then** the
   owning entry is returned.
6. **Given** a morpho-syntactic analysis, **When** a script reads it, **Then** its
   identity and readable properties are available without dropping to raw
   data-model access.

---

### User Story 2 - "Does this word parse, and why not?" (Priority: P2)

A linguist has just edited a grammar rule or added an entry and wants to know
whether a particular word now parses. They ask the assistant. The assistant runs the
word through the parser and, for a single word against an already-loaded grammar,
answers in the same breath -- no "check back later". If the word fails, the answer
says why, in the parser's own terms, rather than reporting only that it failed.

**Why this priority**: This is the answer of record the whole checkpoint exists to
produce, and the first time the feature is visible to a user at all.

**Independent Test**: On a project with a working grammar, ask for a word known to
parse and a word known to fail; confirm both return a complete answer in one call,
and that the failure explains itself.

**Acceptance Scenarios**:

1. **Given** a project with a loaded grammar, **When** the user asks whether a word
   parses, **Then** a complete result returns inline within the grace window and no
   follow-up call is needed.
2. **Given** a word that does not parse, **When** the user asks why,
   **Then** the response reports the parser's trace of the failure, not merely that
   the word failed.
3. **Given** a request for the cheap yes/no check, **When** the word fails,
   **Then** the response does not claim to explain why, and points at the explaining
   mode instead.
4. **Given** a project whose configured parser is not the one this feature supports,
   **When** the user asks to parse a word, **Then** the request is refused up front
   naming the configured engine, and no parser is constructed.
5. **Given** any request that reaches the parser, **When** it is handled, **Then**
   the active-parser check is the first thing that happens.

---

### User Story 3 - "Test my hypothesis about this word" (Priority: P3)

A linguist believes a word breaks down a particular way and wants to know whether
the grammar agrees. They say so in their own vocabulary -- headwords, or a headword
plus a sense -- not internal identifiers, because over an assistant there is no
dialog box to pick entries from. The assistant turns that into a restricted trace of
exactly the analysis the user proposed. If the assistant can see an unambiguous
candidate for each piece, it offers a starting decomposition, clearly labelled a
guess. If any piece cannot be resolved to a real analysis, the request is refused
outright and names the piece -- because an empty result from a silently narrowed
search reads as "your grammar rejects this", when the truth is "we never tested what
you asked".

**Why this priority**: Highest-value mode for the expert user and the cheapest to
run, but it depends on story 2's plumbing and carries the checkpoint's main
correctness risk.

**Independent Test**: Supply a decomposition by headword for a word with a known
analysis, confirm the trace is restricted to it; then supply a decomposition with one
unresolvable piece and confirm refusal with the piece named and no parse performed.

**Acceptance Scenarios**:

1. **Given** a decomposition given as headwords, **When** the user asks to test it,
   **Then** it is resolved to real analyses and the trace is restricted to them.
2. **Given** a decomposition where one piece resolves to no analysis, **When** the
   user asks to test it, **Then** the request is refused naming that piece and its
   candidates, and no parse is run at all.
3. **Given** a word whose pieces each have exactly one unambiguous candidate,
   **When** the user asks without supplying a decomposition, **Then** a proposed
   decomposition is offered, labelled proposed and unverified.
4. **Given** a proposal that disagrees with every analysis already recorded for that
   word, **When** it is traced, **Then** it is traced exactly as given, the
   disagreement is reported as an observation, and the result is never reordered,
   scored, demoted or refused on those grounds.
5. **Given** a proposal that agrees with recorded analyses, **When** it is traced,
   **Then** the response says nothing about the agreement.
6. **Given** a run that tests many words, **When** pieces are resolved, **Then** the
   lookup index is built once for the run and reused.

---

### User Story 4 - Long parses are visible, interruptible and never lose work (Priority: P4)

A parse can take hours and can exhaust the machine's memory. When a request outlives
the grace window, the user gets a handle instead of a wait, and can ask at any time
what stage it has reached and how far it has got. They can stop it. If it dies, or
they stop it, everything finished so far is still there and readable. And an urgent
single word does not have to wait behind a long batch.

**Why this priority**: Scope risk rather than user-facing novelty -- but stories 2
and 3 are specified to run on this machinery, so there is no second, simpler
execution path to fall back on.

**Independent Test**: Start a parse long enough to exceed the grace window, confirm a
handle comes back and the work continues; poll it; cancel it; confirm partial results
survive. Separately, submit an urgent single word during a running batch.

**Acceptance Scenarios**:

1. **Given** a request that finishes inside the grace window, **When** it completes,
   **Then** results return inline and no handle is issued.
2. **Given** a request still running when the grace window closes, **When** the
   window closes, **Then** a handle returns, the work continues unaffected, and
   nothing is cancelled or slowed.
3. **Given** a running job, **When** the user asks its status, **Then** the current
   stage is reported distinctly -- including that it is still loading the grammar,
   separately from parsing -- along with progress.
4. **Given** a job the user cancels, **When** it stops, **Then** it stops at the next
   word boundary, ends in a cancelled state, and the results produced so far remain
   readable.
5. **Given** a job that dies partway, **When** the user asks its status, **Then** the
   failure is reported with guidance toward diagnosis, and every result produced
   before the death is still readable.
6. **Given** a long batch in progress, **When** an urgent single word is submitted,
   **Then** it runs at the next word boundary, the batch resumes without restarting
   or losing position, the grammar is not reloaded, and reported batch progress
   accounts for the interleave.
7. **Given** a handle that does not correspond to any run, **When** status is
   requested, **Then** the request is refused naming the handle and listing the runs
   that do exist.

---

### Edge Cases

- The parser component is present but belongs to a different FieldWorks installation
  than the data model in use.
- The parser's own interface and its implementation disagree on what a parameter is
  called, so anything bound by name breaks while positional binding works.
- A piece of a proposed decomposition matches a headword but that headword carries no
  usable analysis.
- A piece matches several homographs, or several allomorphs of one entry.
- The word's proposed decomposition differs from every recorded analysis -- which may
  mean the user is right about an irregular word.
- Grammar loading exhausts memory before a single word is parsed.
- A trace payload is far too large to sit inside a response.
- The grammar goes out of date while a long run is in flight.
- Cancellation arrives after the job has already reached a terminal state.
- Status is requested for a run that has been cleaned up.
- A text carries multiple genres and is selected by one of them.
- The user's project has no working grammar of the supported kind at all.

## Requirements *(mandatory)*

### Functional Requirements

**Parser access from generated scripts (US1)**

- **FR-001**: The project object available to generated scripts MUST expose a
  read-only parser area alongside its existing areas, offering: a plain parse of a
  word, a parse returning the parser's structured output, a trace that may be
  restricted to a caller-supplied set of analyses, a way to reload the grammar, and a
  way to ask whether the loaded grammar is current.
- **FR-002**: The parser area MUST NOT expose any way to record, file or otherwise
  write parse results. The absence MUST be stated where a future contributor will
  read it, because the read-only safety claim of the new assistant tools rests on
  this surface being unable to reach a write path.
- **FR-003**: Loading the parser component MUST be triggered by use, never by import,
  so that a future installation that renames or relocates it degrades to "parser
  unavailable" instead of breaking unrelated features.
- **FR-004**: Before use, the system MUST verify that the parser component comes from
  the same installation directory as the data model in use, and MUST refuse otherwise.
- **FR-005**: Before use, the system MUST verify by inspection that every operation it
  intends to call exists, and MUST bind those operations positionally rather than by
  parameter name.
- **FR-006**: The detected parser version MUST be reported and MUST NOT be compared
  against any minimum. A standing test MUST guard this in each repository that probes.
- **FR-007**: Scripts MUST be able to read all genres assigned to a text, not only the
  first.
- **FR-008**: Scripts MUST be able to get the entry that owns an allomorph.
- **FR-009**: Scripts MUST be able to read morpho-syntactic analyses without dropping
  to raw data-model access, since resolving a user's hypothesis terminates in them.
- **FR-010**: Parser results crossing into script-visible form MUST preserve the
  identity of the underlying lexical objects, not only their text, because later
  checkpoints align results against recorded analyses by identity.
- **FR-011**: The new surface MUST be released as a versioned package before the
  assistant-side work is tested against it; the assistant's declared minimum version
  and its bundled index of that library MUST name the same released version.

**Asking whether a word parses (US2)**

- **FR-012**: The assistant MUST offer a tool that parses one word and MUST expose all
  three levels of answer: restricted-to-a-hypothesis, plain yes/no, and full
  explanation. Each MUST reach the corresponding underlying operation.
- **FR-013**: The plain yes/no level MUST NOT present itself as explaining a failure,
  and MUST point the caller at an explaining level instead.
- **FR-014**: Guidance MUST steer callers to the restricted level when they have a
  hypothesis and to the full explanation only when they do not, since the full
  explanation is the expensive one and the one under a budget cap.
- **FR-015**: Every handler that reaches the parser MUST check the project's
  configured parser engine as its first action, before any parser is constructed, and
  MUST refuse a project configured for an unsupported engine.
- **FR-016**: A missing recording agent MUST NOT mark reading unavailable, since
  reading neither records nor needs one.
- **FR-017**: The new tools MUST be annotated read-only-safe, and that annotation MUST
  be backed by a standing test asserting that a real parse loads no user-interface
  framework code into the process. The test MUST cover the call path, not a class.

**Testing a hypothesis (US3)**

- **FR-018**: The restricted trace MUST accept a decomposition expressed in terms a
  caller can actually write -- entry headwords, headword plus sense, or internal
  identifiers -- and resolve it to the analyses the parser requires.
- **FR-019**: If any piece of a decomposition resolves to no usable analysis, the
  request MUST be refused, naming the piece, its position and its candidates, and no
  parse MUST be run.
- **FR-020**: Lookup structures used for resolution MUST be built once per run and
  reused across words.
- **FR-021**: Where every piece has exactly one unambiguous candidate, the system MAY
  offer a proposed decomposition; when it does, it MUST label it proposed and
  unverified.
- **FR-022**: Guidance offered when a decomposition is missing MUST name only actions
  the caller can actually perform with the tools that exist.
- **FR-023**: A caller's proposed decomposition MUST always be traced exactly as
  given. The system MUST NOT substitute a different restriction, widen it to an
  unrestricted search, reorder, score, demote or refuse on the grounds that the
  proposal disagrees with recorded analyses.
- **FR-024**: Where the system has something to say about a proposal, it MUST be
  limited to an adjacent candidate or a conflict with recorded analyses, MUST be
  worded as an observation rather than a verdict, MUST carry no confidence figure, and
  MUST ride alongside the result rather than replacing it.
- **FR-025**: Agreement between a proposal and recorded analyses MUST produce no
  commentary.

**Run lifecycle (US4)**

- **FR-026**: All parser execution MUST go through one run mechanism. There MUST NOT
  be a separate synchronous path.
- **FR-027**: A run MUST report a distinct stage for starting, loading the grammar,
  parsing, filing (defined but unreachable in this checkpoint), completed, failed and
  cancelled.
- **FR-028**: A run reaching a terminal stage inside a configurable grace window
  (default 5 seconds) MUST return its results inline; otherwise it MUST return a
  handle. The window governs reporting only -- it MUST NOT cancel, time out or
  throttle the run.
- **FR-029**: Results MUST be written to the run's record as they are produced, so a
  run that dies or is cancelled leaves everything completed so far readable.
- **FR-030**: Runs MUST be ordered by the same priority levels and ordering the host
  application uses, lowest value first, first-in-first-out within a level, enqueued per
  word.
- **FR-031**: A higher-priority single word MUST interleave at the running batch's next
  word boundary. The batch MUST NOT restart or lose position, the grammar MUST NOT be
  reloaded, and the batch's reported progress MUST account for the interleave rather
  than appearing stalled.
- **FR-032**: Cancellation MUST be cooperative, stopping at the next word boundary and
  leaving a cancelled terminal stage over the partial results.
- **FR-033**: The assistant MUST offer a read-only status tool taking a run handle and
  reporting stage, progress, and -- on a terminal stage -- the result summary or the
  failure with its guidance.
- **FR-034**: A failed run MUST carry guidance pointing at the diagnostic instruments,
  since memory exhaustion is the case where a diagnosis beats a retry.
- **FR-035**: A status request for an unknown handle MUST be refused naming the handle
  and the handles that do exist.
- **FR-036**: A cancelled run MUST be reportable with the count of words completed and
  the stage it was in when cancelled.

**Contract and carry-over (cross-cutting)**

- **FR-037**: Three refusal codes MUST be added additively to the existing tool
  response contract -- unresolvable morph, unknown run, and cancelled run -- with the
  documented count raised from 22 and a changelog entry recorded.
- **FR-038**: Every piece of guidance shipped in CP1 that had to point at nothing
  because this tool did not exist MUST be revisited and pointed at it.
- **FR-039**: Test groups deferred by CP1 MUST be brought into scope: the
  no-user-interface-code guarantee, the no-oracle case, the conditional-proposal case,
  and the script-library facade group.
- **FR-040**: Whether the three grammar lints deferred at CP1 are folded in here MUST
  be decided and, if deferred again, recorded as such.

**Decisions resolved during specification (cross-cutting)**

- **FR-041**: This checkpoint MUST NOT modify the capability check already shipped in
  this repository. The script library MUST probe only the read operations its own
  surface binds; this repository MUST keep its larger check, which additionally covers
  the write operation it gates and which the library deliberately does not wrap. Both
  checks MUST state, where a contributor will read it, that their member lists differ
  by design and MUST NOT be unified -- an unexplained divergence between two
  safety-critical checks is indistinguishable from drift.
- **FR-042**: At most one loaded grammar MUST be held at a time, for the project in
  use, and it MUST be released when another project's grammar is needed. Holding a
  grammar MUST NOT turn grammar loading -- the step that most often exhausts memory --
  into an accumulating cost.
- **FR-043**: A held grammar MUST have its currency confirmed before it is reused, and
  MUST be reloaded when it reports stale. A parse MUST NOT be served from a grammar
  whose currency was not confirmed. An explicit reload request MUST discard the held
  grammar unconditionally.

**Explicitly out of scope**

- Writing, filing or recording parse results anywhere in a project (later checkpoint).
- Batch scoping, run comparison and run logging (later checkpoint).
- The isolated sandbox for grammar generation (later checkpoint).
- Any general-purpose word segmenter or search over possible decompositions.

### Key Entities

- **Parser area**: the read-only parser surface on the project object available to
  generated scripts; knows how to parse, trace, reload and report currency, and by
  construction cannot record anything.
- **Capability check**: the verdict on whether the parser can be used here -- same
  installation, expected operations present -- plus a reported version that decides
  nothing.
- **Parse request**: a word, a level of answer, and optionally a proposed
  decomposition.
- **Morph specification**: one piece of a caller's proposed decomposition, expressed
  as a headword, a headword plus sense, or an identifier.
- **Resolution result**: the analyses a morph specification resolved to, the
  candidates considered, and whether resolution failed.
- **Run**: a unit of parser work with a handle, a stage, a priority, progress, an
  accumulating record of results, and a terminal outcome.
- **Run record**: the durable artifact a run writes results into as it goes, and which
  survives the run's death.
- **Trace payload**: the parser's explanation of a word, potentially large enough that
  where it is kept is a design decision rather than a detail.
- **Observation**: a non-authoritative remark about a caller's proposal, carrying no
  score and never displacing the result.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a machine where the parser component is absent, relocated or from a
  different installation, importing the script library succeeds in 100% of cases and
  parser access reports unavailable with a reason instead of raising.
- **SC-002**: No code path anywhere in either repository compares a detected parser
  version against a minimum -- 0 occurrences, asserted by a standing test on each side.
- **SC-003**: After a real parse, 0 user-interface framework components are loaded in
  the parsing process, asserted in an isolated process.
- **SC-004**: A single word against an already-loaded grammar returns a complete
  answer in one call, with no follow-up request, in at least 95% of attempts within
  the default 5-second grace window.
- **SC-005**: 100% of requests naming a decomposition piece that cannot be resolved
  are refused with that piece and its candidates named, and 0 parses are run for them.
- **SC-006**: A caller's proposed decomposition is traced exactly as given in 100% of
  cases; 0 cases of substitution, widening, reordering, scoring or demotion; 0
  confidence figures attached to a user hypothesis; 0 remarks emitted when the
  proposal agrees with recorded analyses.
- **SC-007**: Lookup structures are constructed exactly once per run regardless of how
  many words it contains.
- **SC-008**: A run that is killed or cancelled after completing N words leaves all N
  results readable, for any N -- 0 results lost.
- **SC-009**: An urgent single word submitted during a running batch begins within one
  word boundary of submission; the batch resumes from where it stopped, repeats 0
  words, and the grammar is loaded exactly once for both.
- **SC-010**: Exceeding the grace window cancels or slows 0 runs.
- **SC-011**: Every piece of next-step guidance the feature emits names an action the
  caller can actually perform -- 0 references to tools that do not exist -- and every
  CP1 guidance row that had to point at nothing now points at the new tool.
- **SC-012**: All three answer levels succeed against a live project with a working
  grammar, with the restricted level driven by a caller-supplied decomposition.
- **SC-013**: The full test suite is green, including the groups CP1 deferred, and the
  declared minimum library version equals the version of the bundled index.
- **SC-014**: At no point is more than one loaded grammar held; across a sequence of
  runs spanning two projects, switching projects releases the previous grammar -- 0
  grammars retained for a project not in use.
- **SC-015**: 0 parses are served from a grammar whose currency was not confirmed
  immediately before reuse, and 100% of stale reports produce a reload before any word
  of that request is parsed.
- **SC-016**: Each capability check is guarded by its own standing test over its own
  member list, each carries a written statement that the divergence is deliberate, and
  this checkpoint changes 0 lines of the check already shipped in this repository.
- **SC-017**: All three answer levels are verified live against `IndonesianHC-Complete`;
  the long-run behaviours -- grace-window overflow, word-boundary interleave,
  cooperative cancellation and partial-result survival -- are verified live against
  `Malay Parsing-20230810withHC`.

## Assumptions

- The script library and this repository share a maintainer, so the release that gates
  everything else is a scheduling matter rather than a negotiation. It is still a real
  release and a real gate: nothing on the assistant side can be tested against a
  published dependency until it happens.
- The new library surface is additive, so a minor version bump (4.9.0) is correct and
  no breaking change is implied.
- The two capability checks -- the one already shipped in this repository and the new
  one in the script library -- are deliberately **different by design**: the library
  checks only the read operations it wraps, this repository keeps its larger check
  covering the write operation it gates. Divergence between them is therefore correct
  rather than drift, and this checkpoint does not modify the shipped check. *(Decision
  D1.)*
- A loaded grammar is held for reuse, but only one at a time and only for the project
  in use, and its currency is confirmed before every reuse. Reuse is what makes the
  interleave guarantee affordable; the single-slot bound is what stops it becoming an
  accumulating memory cost; the currency check is what stops it answering from a
  grammar the user has since changed. *(Decision D2.)*
- Parser results cross into script-visible form as typed structures preserving the
  underlying object identities, while the trace explanation crosses unchanged, since no
  consumer's needs are yet understood well enough to fix its shape.
- Trace explanations are persisted to the run's record rather than embedded in
  responses, following the parent spec's run-artifact model.
- The grace window's 5-second default is a starting value and is configurable.
- The stages, priority levels and ordering mirror the host application's own names, but
  this feature's ordering guarantee is its own; an uncommitted local change in the host
  application that drains its queue in parallel must never be cited as the rationale,
  and must not be copied.
- CP1's shipped-but-uncalled machinery -- the active-parser check, the recording-agent
  probe and its refusal logic -- is correct as shipped and simply gains its first caller
  here.
- Live verification runs against `IndonesianHC-Complete` for correctness and
  `Malay Parsing-20230810withHC` for scale. Both were confirmed during specification to
  be configured for the supported engine and to carry real phonological rules. The usual
  sample project, `Sena 3`, is configured for the *other* engine and carries no rules, so
  it would be refused by this feature's own engine gate. *(Decision D3.)*

## Dependencies

- A released script-library version carrying the new parser surface, plus this
  repository's declared minimum and bundled index both updated to match it.
- A FieldWorks installation supplying both the data model and the parser component
  from the same directory.
- CP1's delivered work: the capability probe, the engine gate, the recording-agent
  probe and its refusal logic, and the four refusal codes it added.
- Two live projects, confirmed during specification: `IndonesianHC-Complete` (engine
  `HC`, 3 phonological rules, 41 entries) for the three answer levels, and
  `Malay Parsing-20230810withHC` (engine `HC`, 4 phonological rules, 281 entries) for the
  long-run behaviours that a 41-entry project is too small to exercise.

## Verbatim Constraints

Values the source document pins exactly. Downstream steps must use these strings as
written, not paraphrases of them.

- Released script-library version: **`4.9.0`**
- Declared minimum, in both `pyproject.toml` and `requirements.txt`:
  `pyflexicon>=4.9.0,<5`
- Bundled index file that must exist and match that floor:
  `index/python/flexicon_api_v4.9.0.json`
- New assistant tools: `flextools_try_word`, `flextools_parse_status`
- Standing test name for the no-user-interface-code guarantee: `HCParser_DoesNotLoadXCore`
- Run stages, exactly these names:
  `starting | loading_grammar | parsing | filing | completed | failed | cancelled`
- Priority levels and values, mirroring the host application, lowest wins:
  `ReloadGrammarAndLexicon = 0, TryAWord = 1, High = 2, Medium = 3, Low = 4`
- The shipped capability check this checkpoint must not modify:
  `src/flextoolsmcp/server/parser_probe.py`
- Live verification projects: `IndonesianHC-Complete`, `Malay Parsing-20230810withHC`
- Read-only annotation applied to both new tools: `READ_ONLY_SAFE`

## Decisions

The source document carried three open questions into this specification. All three are
resolved below; each is reflected in the requirements, assumptions and success criteria
above.

### D1 -- Capability-check duplication: keep the two checks deliberately different

**Decision**: adopt the source document's option (c). The script library probes only the
read operations its own surface binds; this repository keeps its larger check, covering
also the write operation it gates and which the library deliberately does not wrap. This
checkpoint does not touch `src/flextoolsmcp/server/parser_probe.py`. Requirement FR-041.

**Why**: option (b) -- move the check into the library and consume it here -- fails on
its own terms: this repository's health report must keep working when the library is
unavailable, which is precisely when the check matters most. Option (a) -- duplicate and
assert both enumerate the same set -- only detects drift if someone runs both suites, and
it asserts an equality that is not actually true, since the two surfaces genuinely differ.
Option (c) is the only one where different member lists are correct rather than a smell.

**What it costs**: a deliberate divergence with no recorded rationale becomes
indistinguishable from drift within a release or two. FR-041 therefore requires each check
to *state* that the difference is intended, not merely to be different.

### D2 -- Loaded-grammar lifetime: one grammar, held, currency-checked before reuse

**Decision**: hold at most one loaded grammar at a time, for the project in use; release
it when another project's grammar is needed; confirm its currency before every reuse and
reload on stale; discard it unconditionally on an explicit reload request. Requirements
FR-042 and FR-043.

**Why**: the feature already commits to reuse -- FR-031 forbids reloading the grammar
across an interleave and SC-009 requires it to be loaded exactly once for a batch and the
urgent word that interrupts it. So the grammar is held either way; the only real questions
are how many and for how long. Holding *one* keeps the commitment while bounding the
memory cost, which matters because grammar loading is the step that most often exhausts
memory: an unbounded per-project cache would make the worst failure mode more likely, not
less. Checking currency before reuse is what separates a fast answer from a confidently
wrong one -- serving a parse from a grammar the user has since edited is the same class of
failure as the resolver's silently narrowed search.

**What it costs**: this is process-lifetime state this repository does not currently keep,
and the single slot means alternating between two projects reloads every time. That is
the right trade: the common case is one project per session, and the pathological case
degrades to today's behaviour rather than to memory exhaustion.

### D3 -- Verification target: `IndonesianHC-Complete`, with `Malay Parsing-20230810withHC` for scale

**Decision**: verify the three answer levels against `IndonesianHC-Complete`, and the
long-run behaviours against `Malay Parsing-20230810withHC`. `Sena 3` is ruled out.

**Why**: this was settled by inspection rather than assumption. `Sena 3` reports engine
`XAmple` with 0 phonological rules -- this feature's own engine gate (FR-015) would refuse
it, so it cannot verify anything here. `IndonesianHC-Complete` reports engine `HC` with 3
phonological rules over 41 entries, and all twelve shipped grammar checks run against it
with none skipped; it is small enough that a cold run stays fast, which suits the
correctness modes. `Malay Parsing-20230810withHC` reports engine `HC` with 4 phonological
rules over 281 entries, large enough to push a run past the grace window and give the
interleave, cancellation and partial-result criteria something real to act on -- which 41
entries cannot.

**What it costs**: neither project is large enough to exercise the memory-exhaustion path
that `loading_grammar` exists to make diagnosable. That path stays covered by reasoning and
by the failure-side guidance of FR-034, not by live evidence at this checkpoint.

## Risks

- **Schedule**: the cross-repository release gates everything; the assistant-side work
  cannot be tested against a published dependency until it lands.
- **Scope**: the run machinery is substantial new infrastructure arriving attached to a
  tool that, for one word against a loaded grammar, would otherwise be a single
  synchronous call. Shipping the tool synchronously and adding the machinery later is
  explicitly ruled out -- there must not be a second execution model, and the next
  checkpoint assumes this one exists.
- **Correctness**: resolving a caller's hypothesis is net-new, on the critical path,
  and its failure mode -- a silently narrowed selection -- produces a confident wrong
  answer about someone's grammar.
