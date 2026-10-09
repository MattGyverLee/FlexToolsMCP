# AI Collaboration Guardrails

[Back to README](../README.md)

Derived from every "Corrections To The AI" section across all nine shards
(C-M1-01..06, C-M2-01..06, C-M3-01..05, C-M4-01..03, C-M5-01..06, C-M6-01..04,
C-M7-01..03, C-M8-01..05, C-G1-01..03 -- 41 corrections in total). Matthew's
Swahili shards S1-S11 are merged by rule at the end: confirmations in the table
below the Merge seam, new rules in sections K and L.

These are **always / never** rules for an AI assistant building a FLEx parsing
lexicon. They are written as instructions to the assistant.

---

## A. Before you write any code

**A1. NEVER guess an API name.** Several plausible-sounding operations-class names do
not exist and the failure is an `ImportError` mid-run. Verify against the actual API
surface first. *(C-M1-03, C-M2-04, C-M3-01, C-M6-01)*

**A2. NEVER guess whether a property exists on an interface.** Resolve it. Properties
that look like they should be shared between sibling morph interfaces are not.
*(C-M8-03, C-M8-05, C-M4-01)*

**A3. ALWAYS run API/method discovery before calling an unfamiliar factory or
overload.** Pattern-matching a signature from a different `Create()` call is how the
possibility-creation call failed. *(C-G1-01)*

**A4. ALWAYS import every operations class you use**, including in helpers called deep
in a script. *(C-M6-01)*

**A5. ALWAYS do the cheap version first.** Minimal, least-casted snippet; escalate only
when it fails or preflight rejects it. Ron's standing instruction across 41 consecutive
operations. *(D-M7-01)*

---

## B. Polymorphism and casting

**B1. ALWAYS cast to the most specific known interface** immediately after obtaining an
object from a polymorphic reference or collection. *(C-M8-01, C-M8-02)*

**B2. ALWAYS branch on the object's class name before casting** when the concrete class
can vary within a collection. *(C-M6-04)*

**B3. ALWAYS expect sibling interfaces on one object.** "Same object, different
interfaces." *(C-M4-01)*

**B4. NEVER call a property of a concrete type through an abstract base.** Compute the
answer another way -- e.g. find the object's position in the already-materialized
ordered collection rather than trusting an index property on the base. *(C-M4-03)*

**B5. ALWAYS None-check a relational property before iterating it.** *(C-M7-02)*

**B6. ALWAYS recurse possibility trees.** Variant types, categories and inflection
classes nest. A flat search returns `None`, and `None` passed to an add call crashes
mid-write. *(C-M6-02)*

**B7. NEVER let a clean read-only run reassure you.** Read-only runs get casting
warnings and proceed; write runs get hard-rejected for the same issue. *(M4 §6,
M6 §6)*

**B8. NEVER rely on preflight to catch your casting.** Use the suffixed property names
and explicit casts from the first attempt. *(C-M7-03)*

---

## C. Writes

**C1. ALWAYS wrap every mutating statement in the `modifyAllowed` guard.** Three
separate shards were rejected for this; it is the most-repeated correction in the
corpus. *(C-M3-02, C-M6-01, C-M8-04)*

**C2. ALWAYS run `validate_only` with the identical code before the live write.**
*(M7 §9)*

**C3. ALWAYS plan first, mutate second** -- compute the partition read-only, print
counts, then mutate. This applies to internal LCM object graphs as much as to lexical
entries. Remove indices in descending order. *(D-M7-03, D-M7-04)*

**C4. ALWAYS guard every add against `None`.** In non-undoable write mode a
mid-operation crash leaves partial mutations permanently in the cache. *(C-M6-02)*

**C5. ALWAYS design bulk scripts so a crash at any point leaves a detectable,
repairable state.** The atomicity unit is the session, not the operation. *(M5 §6,
M6 §6, M8 §6)*

**C6. NEVER delete lexical content without a content backup first.** "The
gloss/definition work is real and deletion is irreversible." *(D-M5-10)*

**C7. NEVER delete anything with senses without flagging it for human review.**
*(D-M7-02)*

**C8. NEVER remove the last remaining child of a required collection.** Warn instead.
*(D-M7-06)*

**C9. NEVER delete a shared object without checking referrers.** *(M3 §6)*

**C10. ALWAYS treat a materially changed write script as requiring fresh discovery.**
*(C-G1-02)*

---

## D. Bulk operations

**D1. ALWAYS intersect a shape-based filter with a category check** before any
destructive bulk operation. A predicate matching purely on orthographic shape deleted
six pronoun obliques along with 92 noun obliques. Run the category survey **before**,
not after. *(C-M7-01)*

**D2. ALWAYS prefer an explicit target list over a broad predicate** for bulk
operations. This is the converged practice. *(M7 §9)*

**D3. NEVER assume "skipped" means "already complete".** A create-if-not-exists import
silently skips existing entries and leaves them without their derived data. Always run
an explicit "exists but missing associated data" reconciliation. *(D-M5-13)*

**D4. ALWAYS derive names used downstream from the created objects**, not by re-typing
them. A name mismatch between creation and consumption failed all 69 rows of an
import. *(C-M5-01)*

**D5. ALWAYS write a per-item log file for bulk conversions.** *(M8 §6)*

**D6. ALWAYS write large output to a file.** Report output is capped and truncates
silently. *(M8 §6)*

---

## E. Blast radius

**E1. NEVER edit a shared natural class, environment or feature to fix a local
problem.** Check what else references it first. When the fix applies to one lexical
subclass, use a dedicated inflection class plus a literal, non-shared environment.
*(C-M5-05, D-M5-14)*

**E2. NEVER narrow a previously-unrestricted allomorph without enumerating every class
that legitimately needs it.** A single-class restriction breaks sibling classes sharing
the same environment. *(C-M5-06, D-M5-15)*

**E3. ALWAYS check for an existing object with the same semantics before creating a
new one.** The human may have just created it by hand in the GUI. *(D-M5-05, D-M7-05)*

---

## F. Data hygiene

**F1. ALWAYS normalize both sides of every vernacular string comparison.** *(C-M2-03,
D-M8-02)*

**F2. NEVER JSON-serialize a raw interop object.** Coerce to plain strings/ints first.
*(C-M5-03)*

**F3. ALWAYS check whether a string property is single-alternative or
multi-alternative before writing to it.** *(C-M5-04, C-M3-04)*

**F4. ALWAYS pick one string-formatting style per snippet.** *(C-M2-02)*

**F5. ALWAYS gate a write on the source data module's own `check()` validator.**
Refuse to write bad data rather than writing it and fixing it later. *(M2 §5)*

**F6. ALWAYS re-derive expected counts from the live database or the source module,
never from a hardcoded snapshot.** *(C-M2-06)*

---

## G. Modeling

**G1. NEVER mix plain allomorphs and affix-process rules on one entry.** The plain
forms shadow the process rules. Convert uniformly. *(C-M1-06)*

**G2. ALWAYS verify the citation form is still reachable** after converting an entry's
alternates. *(C-M1-05)*

**G3. ALWAYS decide keep-vs-replace explicitly per subrule** and test it against a
concrete surface form. Do not default to one behavior across environments. *(C-M2-05)*

**G4. NEVER put a category-changing affix in an inflectional template slot.** Test:
does this affix change the word's part of speech? If yes, it is derivation.
*(C-M6-03)*

**G5. ALWAYS borrow the existing feature/value objects** an already-working affix uses,
rather than creating equivalent-looking new ones. *(L-M6-04)*

**G6. ALWAYS check the environment string is non-empty** before believing an allomorph
is conditioned. *(L-M8-04)*

**G7. ALWAYS prove the recipe on one exemplar, then siblings, then the class.**
*(D-M1-09, D-M8-06, D-M8-07)*

---

## H. Verification

**H1. ALWAYS regression-check.** "Fix it, but verify the others that are working will
still parse." A fix that breaks three things to fix one is a net loss. *(D-M3-01,
D-G1-06)*

**H2. ALWAYS run a dedicated post-write verification snippet** with explicit expected
counts. Verification is part of the task, not an extra. *(M7 §9)*

**H3. ALWAYS treat parse time as a quality metric** alongside parse correctness.
*(D-M3-02)*

**H4. NEVER treat a user-reported failure as a one-off.** It is a seed for a
systematic sweep of the whole failure class. *(D-M2-07)*

**H5. NEVER treat all multi-parses as bugs.** Genuine grammatical ambiguity must be
preserved; only structurally identical duplicate analyses are defects. *(D-M3-04)*

**H6. NEVER invent an unattested form** to fill a paradigm cell. *(L-M5-02)*

---

## I. Working with the human

**I1. A restore, a GUI edit, or a concurrent session is a legitimate external state
change, not an error.** Re-derive state from scratch; do not assume your prior writes
are the last word. *(D-M3-03, D-M5-02, D-M5-05)*

**I2. A terse instruction following an extended diagnostic history authorizes the full
previously-identified fix set**, including structural consolidation -- not just point
patches. ("fix it all", "implement it", "fix it".) *(D-M3-07, D-M4-01, D-M4-03)*

**I3. An explicit read-only constraint persists for the whole session**, even when
stated only once at the start. *(D-M4-04)*

**I4. A repeated verbatim standing request is not a re-issued instruction.** Only the
per-step intent reflects the actual current step. *(D-M6-01)*

**I5. "Iterate to see how good you can get it" authorizes an autonomous
build-measure-fix loop**, not a single pass. *(D-M6-01)*

**I6. A rollback is a legitimate outcome.** Trying a technique, verifying it live, and
fully reverting it with the same discipline is normal practice. *(D-M7-07)*

**I7. Distinguish environmental flakes from logic bugs in triage.** A project lock is
not a code error. *(C-M3-05, C-M5-02)*

**I8. Flag anomalies you cannot explain rather than working around them.** The
unexplained slot-count and entry-count drift was flagged and never resolved -- but
flagging it was right. *(C-M2-06)*

---

## J. Linguistic honesty

**J1. NEVER present a modeling hypothesis as a fact about the language.** The operator
may not speak the language. Record each claim with its status: asserted by the
operator, AI-proposed-and-accepted, or unresolved.

**J2. ALWAYS distinguish "the parser now produces the right forms" from "this is how
the language works."** Several distinct analyses produce identical surface forms.

**J3. ALWAYS surface the questions only a native speaker can answer** rather than
silently deciding them. See [`../open-questions.md`](../open-questions.md).

*(J1-J3 are not derived from a specific correction in the shards -- they follow from
the framing that Ron does not speak Malayalam, and they are the guardrail whose absence
is most visible across the corpus. Marked (inferred).)*

---

## Merge seam

Matthew's corrections-to-the-AI will produce a second set. Merge by **rule**, not by
source: where his corrections confirm one of these, add his evidence to the existing
rule; where they contradict one, keep both and mark the divergence.

**Swahili merge (shards S1-S11; S1-S5 from one machine, S6-S11 from the other, so
both machines' logs are now in).** New rules are in sections K (S1-S5) and L (S6-S11).
Confirmations of existing rules:

*Evidence caveats.* S6-S7 logs keep no tool output, so their results are read from
code, intents and Matthew's replies. Several S6-S11 sessions were **not** Matthew with
Claude: a `hermes_tools` agent (S6), OpenCode with local models (S7, S8 09-14 and
09-20 afternoon) and an unidentified weaker client (S10 155542). Their failures are
cited below as failure-mode evidence, marked *(other client)*, not as Matthew's
practice.

| Existing rule | Swahili evidence | Note |
|---|---|---|
| A1 never guess an API | C-S6-01 (`ReplaceMoForm` guessed by name, broke a later delete); T-S6-08, C-S8-04 *(other client: invented `WordformsOC`, `LexEntriesOC`, ...)* | when no wrapper exists, port the host application's own command -- see L6 |
| A5 cheap version first | violated in C-S9-04 (one 127-line op, ~12 heterogeneous changes, failed half-way) | one variable per write; batch by kind and parse-check between batches |
| C2 validate_only first | D-S3-04, D-S4-11, D-S10-09; violated in C-S3-04, C-S8-02 *(other client: seven 808-row writes, no validate_only)* | extended into a ladder: validate_only -> dry run -> 5-entry batch -> full -> **idempotency rerun ("expect no writes")** (D-S10-09). **Limit:** validate_only is mechanical; it passed a grammatically wrong slot merge (C-S6-02, T-S6-09) -- see L2 |
| C3 plan first | D-S5-05, D-S7-06, D-S10-03 | GUID-keyed manifest with ordered tiers; read-only diagnosis phase before any write phase |
| C5 crash leaves a repairable state | C-S6-01 (orphan entry with NULL lexeme form after a failed delete under `undoable=False`); C-S11-05 (writes committed, then the verify code crashed and the run was read as "nothing happened") | after any failed write run, inspect the database; never assume nothing landed. Put writes last, or report what was written before anything else can raise |
| C6 backup before delete | C-S1-02 (violated: whole-lexicon delete, no backup); D-S8-03 | before a bulk field rewrite, **snapshot the originals to a file and re-derive every pass from the snapshot**, never from the already-mutated field. Seven lossy 808-row passes stayed recoverable only because of this |
| C9 referrers before delete | C-S5-01; C-S10-01 (GUID + headword guard, 0 references) | extend to the entry's **owned** objects -- see K5 |
| D1 shape + category | C-S1-04; C-S10-04 | a default for "unknown" acts like an unfiltered shape rule. The converse also bites: a duplicate guard keyed on (form, gloss) skipped a noun because a verb shared both -- include POS in the key |
| D6 large output to a file | T-S7-02, T-S8-05 (100-message cap; a list re-dumped three times) | also: use `report.*`, never `print()` -- printed output is invisible and unlogged (C-S11-01) |
| E1 no shared-object edits for local fixes | L-S5-02; L-S9-06, L-S10-02 | the same holds for slot optionality: clone the slot. For a shared rule, count the stored analyses that depend on each output before changing it (7 of 3,312; ny 572 / vy 383) |
| E3 check for an existing object | C-S7-03 | find-or-create on a short nonce form reused and corrupted real entries (*oz*, *uz*). Collect every existing surface form before choosing throwaway names |
| G4 no derivation in templates | C-S1-06; resolved 09-13 (L-S7-05, V-S7-01); relapses C-S7-06, C-S10-03 | Matthew repeated Ron's mistake independently, then fixed it by a staged conversion. "Add missing morphemes" passes re-baked derived shapes (*zalia*, *zaliwa*) as allomorphs or stems afterwards -- re-run the decomposition audit after every lexicon batch |
| G7 proof of recipe | D-S1-04, L-S2-03, D-S7-06 | prototype on 20 hand-marked roots, revert, classify all 647 from evidence, batch with a parse baseline, then convert atomically |
| H1 regression check | D-S7-06, T-S9-03, D-S10-05 | `parse_diff` against a fixed baseline (fixed 3, broken 0). Size the baseline to parse time |
| H2 post-write verification | D-S4-07; C-S5-03; C-S9-02 | verify in a **separate** op -- an in-op check can crash after the commit, and an in-op read-back can report a change that never persists (rule `Disabled` read back True in-op, False on every reopen) |
| H5 ambiguity is not a bug | C-S2-01; L-S10-05, L-S11-02 | applies to approvals too. The converse: `parsed=True` is not "correct" -- inspect words with many analyses (Misri 10, mwana 13) before closing them |
| H6 no invented forms | D-S5-08 (paradigm text from general knowledge); C-S7-05, C-S7-07, C-S11-01 | see L8 |
| I1 external changes | C-S5-02, C-S5-05; C-S7-01, C-S10-06 | stale manifest; project held open elsewhere; a sibling agent overwrote a template Description -- see L1 |
| I2 terse instruction authorizes the fix set | D-S9-05 ("Apply the fix", "yes, fix the invariant numerals", "add the proper noun roots, return for the others") | Matthew authorizes **one class of fix at a time**. A blanket mandate ("using your deep knowledge of Swahili", D-S9-01) produced the 12-change op of C-S9-04 |
| I3 a stated constraint persists | D-S9-02 ("don't run the full set"); D-S10-04 ("Filing NOT authorized") | scope and filing limits persist like read-only limits -- see L4 |
| I4 a repeated standing request is not a new instruction | T-S8-06, T-S9-09 | the logged `User request` was frozen at the session's first message or agent-filled; only the latest operator turn counts |
| I7 a lock is not a code error | T-S8-04, T-S9-05, T-S11-08 | **refined:** after a parse, the lock holder is usually the MCP's own idle parse worker. Call `flextools_parse_release`; `parse_cancel` on a finished run does nothing. Retrying blind does not clear it |
| J1 status of every claim | D-S9-01, D-S10-03 | Matthew explicitly asked for the AI's "deep knowledge of Swahili". The resulting entries, glosses and class choices are still AI-sourced and must be labelled so (see Q-42) |
| K1 heuristic is not a Human approval | relapse C-S7-04, V-S7-06 | see L9 |
| K3 GUID keys | C-S7-09 | **extended:** never key a script on a gloss either. An 807-gloss normalisation pass silently broke scripts that looked affixes up by gloss text |
| K4 disable before delete | D-S7-04, D-S8-12; C-S8-07 | **divergence:** S7-S8 also use `DoNotUseForParsing` to keep live whole-word entries out of the parser, and that effect was never parse-tested ("UNVERIFIED", D-S8-12). Current FlexToolsMCP guidance treats the flag as deprecated for recipes and new API. Keep the soft-before-hard order; the mechanism is open |
| K7 verify the reviewer | D-S10-03 | parallel lex-linguist batches diagnosed read-only; their class choices were checked against corpus agreement before the Stage 1 writes (D-S10-08) |
| K10 stale analyses | V-S7-08; L-S8-01, L-S10-01, L-S11-01, C-S11-06 | **strongly confirmed from tool output** -- see L5 |

---

## K. Added from the Swahili corpus (S1-S5)

**K1. NEVER record a heuristic judgement as a Human approval.** A "fewest morphemes
wins" pass approved one analysis per word as the Human agent and disapproved genuine
alternatives; it had to be reversed (C-S2-01). Use a non-human agent or leave the
analysis unapproved.

**K2. NEVER relax a slot to make a word parse** without checking what else it now
lets through. Prefer a separate template for the construction (C-S2-02, L-S5-02).

**K3. ALWAYS key targets by GUID** (or name + catalog id), never by hvo. Hvos shifted
within a session; hvo-keyed verification failed (C-S1-05, C-S3-05, D-S4-07).

**K4. ALWAYS disable (`DoNotUseForParsing`) before deleting** a lexical entry the
parser uses, and list referrers of everything disabled before the delete. A faulty
heuristic was undone in one minute because of this (D-S4-08, C-S4-01).

**K5. ALWAYS check references across an entry's owned subtree** (allomorphs, MSAs,
senses), not just the entry, and sweep for dangling analyses after any delete batch
(C-S5-01).

**K6. NEVER create custom fields or writing systems through raw LCM.** Do schema
changes in the FLEx GUI. A raw-LCM custom field did not persist, and the session
that depended on it lost the lexicon (C-S1-01).

**K7. ALWAYS verify the reviewer.** Check a domain or AI reviewer's factual claims
("this stem is invented") against the lexicon before acting. Number the rulings and
cite them in the code that applies them (D-S4-10, D-S5-07).

**K8. NEVER default an undecidable value.** Hold it, or flag it (`class-negotiable`).
A default "cl.9/10" for unknown nouns cost 17 manual overrides (C-S1-04, D-S3-05).

**K9. NEVER accept a zero or empty result without a second route.** An accessor
returning None produced a plausible noun count of 0 (C-S3-03).

**K10. NEVER conclude the parser ignores something from analyses older than the last
reparse.** Re-check stored analyses against the current grammar first (C-S2-05,
D-S5-03). Strengthened by L5.

---

## L. Added from the Swahili corpus (S6-S11)

Most S6-S11 corrections are AI-behaviour failures rather than API failures. Rules
backed by tool output (S8 09-23 onward, S9-S11) are stated firmly; S6-S7 evidence
has no tool output and is read from code and intents.

**L1. ONE writer per project at a time.** Parallel agents are fine for read-only work:
per-POS "PROPOSAL only" subagents ran 41 ops in 6 minutes safely (D-S6-12), and
read-only diagnosis batches fed a later write stage (D-S10-03). Parallel *writers* lost
commits to `FP_ConflictingSaveError`, one agent overwrote another's template
Description, and two sessions made contradictory design decisions the same day
(C-S7-01, C-S7-02, T-S7-03). A second client writing to the same project concurrently
looped on the gates (C-S10-06 *(other client)*). Close FieldWorks before a bulk write;
treat a "non-master peer" write as provisional until a read after FLEx closes
confirms it (C-S8-03, D-S8-04). Until the tooling has a write lease, the operator
or orchestrator must serialize writers.

**L2. ALWAYS read an object's design record before changing it, and NEVER
"consolidate" a duplicate without asking why it exists.** The AI merged deliberately
cloned slots (Subj2, TAM2) after a clean validate_only; Matthew reverted it a minute
later (C-S6-02). Later sessions reversed decisions written in template Descriptions
without reading them (C-S7-02). Write the reasons into the project (D-S6-09, D-S7-02),
and append to a shared Description field rather than replacing it (C-S7-01).

**L3. NEVER write grammar you cannot parse-check, and ALWAYS reparse after a grammar
write.** Agents without the parser declined correct-looking changes "because the change
cannot be verified" (D-S7-02, L-S7-01, T-S7-01); others made about eight grammar writes
with no logged re-test of the word they started from (C-S6-05). Either the writer has
`try_word` / `parse_text` / `parse_diff`, or the change is recorded as "proposed,
unverified" and not written. A new template must parse the forms that motivated it
(C-S6-03).

**L4. NEVER start a corpus-wide parse or filing unasked, and NEVER self-confirm a
filing.** An unrequested `parse_text` over all 26,725 words preceded 14 teardown
failures, and Matthew's next request added "(don't run the full set)" (C-S9-01,
D-S9-02). A project-wide filing preview ("may delete up to 24259 analyses ... cannot be
undone") was confirmed by the agent 21 s later with no human decision visible
(C-S10-02). Filing is a separate gate from write mode: in a later brief Matthew granted
writes and withheld filing (D-S10-04). Inside a repair loop, parse the top-N queue plus
a fixed regression set; a corpus-wide run is its own, requested step.

**L5. ALWAYS confirm a failure live before repairing it.** A wordform with no
parser-approved analysis in the database is not a failing word. Stored analyses record
the last FLEx parse, not the current grammar. The top three "unparsed" words parsed
(L-S8-01); 9 of the top 10 parsed (D-S10-01); a refile alone moved 14,096 -> 9,260
unparsed with no grammar change (L-S10-01); all 10 targets of a 4-hour repair session
parsed in 2 minutes once the parse tools were used (L-S11-01, C-S11-06). Step 0 of any
repair: `try_word` the candidate, or refile, and drop it if it parses. Never infer a
lexicon change's effect from stored counts either (C-S8-07).

**L6. Parsing questions go to the parse tools; `run_module` is for lexicon reads and
writes.** In S11 the agent hand-built a frequency queue four times in `run_module` and
got it wrong three times: invented words, object counts (all 1), alphabetical order
(C-S11-01, C-S11-02, C-S11-03); calling the parser inside a script was blocked or
returned nothing readable (T-S11-02). The dedicated tools answered correctly on the
first try (T-S11-01). The failure queue is a defined query -- token occurrences,
descending, no current parser analysis -- not something to improvise (D-S11-02).
Resolve exact headwords (homograph number, bound-stem `*`) before a restricted
`try_word` (T-S8-02, T-S9-02).

**L7. NEVER probe API semantics in the work project.** A by-name guess
(`ReplaceMoForm`) on a throwaway entry, under `undoable=False`, left an orphan with a
NULL lexeme form in the work project; there was no rollback (C-S6-01, T-S6-04). Run
experiments in a test project or a parse sandbox (T-S9-08), or on throwaway objects
with collision-proof names (D-S7-05, C-S7-03), clean up, and verify the cleanup
independently. When a wrapper is missing, port the host application's own command
(FieldWorks `SwapAllomorphWithLexeme`) and prove it on a throwaway first (D-S6-05).
After any failed write, sweep for orphans (entries created today, NULL or empty lexeme
forms, no senses).

**L8. NEVER treat AI-generated forms as data.** Observed in S7-S11:
- a diagnostic script that "simulated" the corpus with a made-up word list (C-S11-01);
- "must survive" probe sets containing likely non-words (C-S7-07);
- string-concatenation paradigm generators producing non-words wherever phonology,
  suppletion or agreement applies (C-S7-05);
- syllable splits (`el`, `is`, `en`, `ghadha`) created as bare entries, probably
  committed (C-S11-05);
- "monomorphemic" verdicts from a string match on a result object, or from a parse
  failure (C-S11-04);
- regex affix stripping reported as "497 new stems requiring injection" (C-S8-04
  *(other client)*).

Data under study comes from the project. Probe and paradigm forms are attested, or
labelled generated and proofread, with structurally invalid forms moved to a negative
"No Parse" set (D-S7-08). A new stem needs a segmentation a linguist would accept,
plus a sense, gloss and POS -- never a bare `LexEntry.Create(form)`. No agent may
propose stems from unanalysed wordforms before it has parsed at least one and read the
result.

**L9. NEVER let one heuristic pass create lexicon, analyses and approvals together.**
The S2 lesson (K1) recurred in a write-mode session that segmented generated wordforms
heuristically, created entries and allomorphs, approved the analyses, and left 424
duplicate allomorphs after a type error (C-S7-04, V-S7-06). Approval is a human act;
heuristic output is at most a parser-agent filing.

**L10. NEVER delete human-approved analyses, or anything a human made, without an
explicit operator go-ahead for that deletion.** A survey of 18 incomplete human
analyses was followed one op later by a delete with no recorded authorization; only
the project lock stopped it (C-S8-06). Survey first (human vs parser, completeness,
text references), then stop (D-S8-14). Keep the layers apart: when Matthew called
"the human analyses" junk, he meant the analysis, not the definition it pointed to
(D-S9-04).

**L11. STOP after two identical failures.** Change approach or report to the operator.
S11 had three loops: 16x the same caller error, 5x following false cast advice, 6x the
same pre-flight rejection (C-S11-07, T-S11-04, T-S11-09). A rule disable was retried
four times without ever persisting (C-S9-02); eight bundle-reorder attempts were
blocked before Matthew redirected the fix to the text (C-S7-08).

**L12. ALWAYS verify persistence by reopening.** "now disabled=True" inside the op
meant nothing; every reopen showed False (C-S9-02). After a teardown, commit or
`AbandonedMutexException` warning, the next action is a separate read-only check, and
two failed checks mean stop (T-S9-06).

**L13. Match the agent to the job.** Weaker clients looped on the gates, guessed APIs,
and in one case wrote nothing in 4 hours (T-S6-08, C-S8-04, C-S10-06 *(other
clients)*; also S11, client unrecorded). The same task on the same day went nowhere
with a local model and was productive with Claude Code (S8). Do not run a weaker
client in write mode on the work project, and never alongside another writer (L1).
