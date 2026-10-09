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
mid-write. *(C-M6-02)* *Status 2026-10-09: partial -- `POS.Find` and
`PossibilityLists.FindItem` recurse, and a `None` argument now raises
`FP_NullParameterError` before any write; variant `FindType` recurses one level only
and the generic list wrappers are flat, so keep recursing and guarding.*

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

**C4. ALWAYS guard every add against `None`.** In the corpus's non-undoable write
mode a mid-operation crash left partial mutations permanently in the cache
*(C-M6-02)*. Since flexicon 4.4.0 and FlexToolsMCP 2.13.0 each flexicon operation is
its own unit of work and rolls back on an exception, so the guard now prevents a
failed run rather than a half-built entry.

**C5. ALWAYS design bulk scripts so a crash at any point leaves a detectable,
repairable state.** In the corpus the atomicity unit was the session, not the
operation *(M5 §6, M6 §6, M8 §6)*. *Status 2026-10-09: fixed -- write runs open
`undoable=True` (flexicon 4.4.0 per-operation unit of work; FlexToolsMCP 2.13.0, MCP#144),
and a whole script becomes atomic inside `with project.UndoableOperation(...)`
(flexicon#579). The session-atomicity hazard applies to logs before 2026-09-25.* The
rule still holds: a multi-operation script without an enclosing `UndoableOperation`
commits each completed operation, **even when the script then raises** -- the runner
saves in `finally` (L15).

**C6. NEVER delete lexical content without a content backup first.** "The
gloss/definition work is real and deletion is irreversible." *(D-M5-10)* The MCP now
takes an automatic `.fwdata` backup on the first write per project and session
(MCP#55, #99; pruned by size and age, #218). A content dump of what you delete is
still on you.

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

**D6. ALWAYS write large output to a file.** Report output is capped at 100
`report.Info` lines. In the corpus it truncated silently *(M8 §6)*; the cap now says
so in `summary.info_truncated`, and `max_info_messages=0` lifts it (MCP#25, #43).
There is no automatic spill to a file, and successful runs log only a 1000-character
`[OUT]` preview (T-43, open).

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
not a code error. *(C-M3-05, C-M5-02)* Since FlexToolsMCP 2.15.0 a `project_locked`
refusal names the holder when it is this server's own parse worker and gives
`flextools_parse_release` as the next step (#315); follow `next_steps` rather than
retrying blind.

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
the framing that Ron does not speak his target language, and they are the guardrail whose absence
is most visible across the corpus. Marked (inferred).)*

---

## Merge seam

Matthew's corrections-to-the-AI will produce a second set. Merge by **rule**, not by
source: where his corrections confirm one of these, add his evidence to the existing
rule; where they contradict one, keep both and mark the divergence.

**Swahili merge (shards S1-S11; S1-S5 from one machine, S6-S11 from the other, so
both machines' logs are now in).** New rules are in sections K (S1-S5) and L (S6-S11).
Confirmations of existing rules:

*Evidence caveats.* The S6-S11 logs drop most tool output and every mid-turn message.
On 2026-10-09 the S6-S10 claims were re-checked against the Claude Code transcripts
behind those sessions, which keep both; the verdicts (CONFIRMED / REFUTED / UPDATED)
are applied below, and several claims built on the logs alone were wrong (parallel
writers, blind writes, an unauthorized delete, a self-confirmed filing). Several
sessions were **not** Matthew with Claude Code: Matthew's own Hermes setup
(`hermes_tools`, S6), OpenCode with local models (09-13 14:09-20:05, S8 09-14 and
09-20 afternoon), an unidentified client (S10 155542) and the unidentified, non-Claude
Code client that ran all of S11 (09-30). Their failures are cited as failure-mode
evidence, marked *(other client)*, not as Matthew's practice. The logs label the
server "2.12.0"; it was a pre-2.13.0 main checkout.

| Existing rule | Swahili evidence | Note |
|---|---|---|
| A1 never guess an API | C-S6-01 (`ReplaceMoForm` guessed by name, broke a later delete); T-S6-08, C-S8-04 *(other client: invented `WordformsOC`, `LexEntriesOC`, ...)* | when no wrapper exists, port the host application's own command -- see L7 |
| A5 cheap version first | violated in C-S9-04 (one 127-line op, ~12 heterogeneous changes, failed half-way) | one variable per write; batch by kind and parse-check between batches |
| C2 validate_only first | D-S3-04, D-S4-11, D-S10-09; violated in C-S3-04, C-S8-02 *(other client: seven 808-row writes, no validate_only)* | extended into a ladder: validate_only -> dry run -> 5-entry batch -> full -> **idempotency rerun ("expect no writes")** (D-S10-09). **Limit:** validate_only is mechanical; it passed a grammatically wrong slot merge (C-S6-02, T-S6-09) -- see L2 |
| C3 plan first | D-S5-05, D-S7-06, D-S10-03 | GUID-keyed manifest with ordered tiers; read-only diagnosis phase before any write phase |
| C5 crash leaves a repairable state | C-S6-01 (orphan entry with NULL lexeme form after a failed delete under `undoable=False`); C-S8-05 (a first write failed part-way: Isa and Ee left with a gloss but no POS or MSA, and the skip-if-present logic would have skipped them on a re-run); C-S11-05, T-S11-10 (9 bare entries committed by a script that then raised -- see L15) | after any failed write run, inspect the database; never assume nothing landed. A re-runnable module must **complete** partial objects, not skip them. *Status 2026-10-09: the `undoable=False` mode behind C-S6-01 and C-S8-05 ended with FlexToolsMCP 2.13.0 (per-operation rollback); a raising script still commits every operation that completed before the raise unless its writes sit inside `project.UndoableOperation(...)` (L15)* |
| C6 backup before delete | C-S1-02 (violated: whole-lexicon delete, no backup); D-S8-03 | before a bulk field rewrite, **snapshot the originals to a file and re-derive every pass from the snapshot**, never from the already-mutated field. Seven lossy 808-row passes stayed recoverable only because of this |
| C9 referrers before delete | C-S5-01; C-S10-01 (GUID + headword guard, 0 references) | extend to the entry's **owned** objects -- see K5 |
| D1 shape + category | C-S1-04; C-S10-04 | a default for "unknown" acts like an unfiltered shape rule. The converse also bites: a duplicate guard keyed on (form, gloss) skipped a noun because a verb shared both -- include POS in the key |
| D6 large output to a file | T-S7-02, T-S8-05 (100-message cap; a list re-dumped three times) | also: use `report.*`, never `print()` -- printed output is invisible and unlogged (C-S11-01). `max_info_messages=0` lifts the cap (MCP#25) |
| E1 no shared-object edits for local fixes | L-S5-02; L-S9-06, L-S10-02 | the same holds for slot optionality: clone the slot. For a shared rule, count the stored analyses that depend on each output before changing it (7 of 3,312; ny 572 / vy 383) |
| E3 check for an existing object | C-S7-03, C-S8-08, C-S7-13 | find-or-create on a short nonce form reused real entries: `LexEntryOperations.Find()` matches fuzzily, so *oz*/*uz* hit `kuoza` and `kuuza`, and `CreateDerivAff` then deleted their MSAs (restored from FLEx's own `.bak`, with new GUIDs). A hyphen-stripping lookup took suffix `-w` for prefix `w-`; only the dry run caught it. Identity is form **plus morph type**; never find-or-create throwaway objects by form. And existence checks belong inside the writing script -- a fresh session that reads the on-disk file cannot see shared-mode writes not yet saved, and a verifier tried to recreate them |
| G4 no derivation in templates | C-S1-06; resolved 09-13 (L-S7-05, V-S7-01); relapses C-S7-06, C-S10-03 | Matthew repeated Ron's mistake independently, then fixed it by a staged conversion. "Add missing morphemes" passes re-baked derived shapes (*zalia*, *zaliwa*) as allomorphs or stems afterwards -- re-run the decomposition audit after every lexicon batch |
| G7 proof of recipe | D-S1-04, L-S2-03, D-S7-06 | prototype on 20 hand-marked roots, revert, classify all 647 from evidence, batch with a parse baseline, then convert atomically |
| H1 regression check | D-S7-06, T-S9-03, T-S9-08, D-S10-05 | `parse_diff` against a fixed baseline (fixed 3, broken 0). The 09-13 valency rollout was diffed over 1,054 forms (1,020 unchanged, 34 lost, 0 gained; V-S7-11); a sandbox A/B of the glide rule over 2,139 words found 54 fixed, 3 broken. Size the baseline to parse time -- the S10 Stage 2 baselines died at word 173 of ~1,700 (D-S10-05) |
| H2 post-write verification | D-S4-07; C-S5-03; C-S9-02; T-S11-10 | verify in a **separate** op -- an in-op check can crash after the commit, and an in-op read-back can report a change that never persists (rule `Disabled` read back True in-op, False on every reopen). *Status 2026-10-09: partial -- `PhonRules.SetDisabled` (flexicon 4.12.0, flexicon#572) replaces the raw cast, but persistence across a reopen is untested; keep verifying by reopening* |
| H5 ambiguity is not a bug | C-S2-01; L-S10-05, L-S11-02 | applies to approvals too. The converse: `parsed=True` is not "correct" -- inspect words with many analyses (Misri 10, mwana 13) before closing them |
| H6 no invented forms | D-S5-08 (paradigm text from general knowledge); C-S7-05, C-S7-07, C-S11-01, C-S11-08 | see L8 |
| I1 external changes | C-S5-02, C-S5-05; C-S7-01, C-S7-13, T-S7-03, C-S10-06 | stale manifest; the FLEx UI saving underneath the 09-13 agents; a second Claude session writing the same project 01:04-01:31; a user-added entry (Musa, L-S9-04) -- see L1 |
| I2 terse instruction authorizes the fix set | D-S9-05 ("option 1, make it so", "Apply the fix", "save them", "add the proper noun roots, return for the others"); D-S8-16 ("apply" / "rename the glosses, fix w-" / "fix them, consult /lex-domain") | Matthew authorizes **one class of fix at a time**, and a good agent holds back what he did not name ("not the gloss rename, not w-/kw-, since you didn't call those", D-S8-16). His 14:41 directive said resolve the words "individually"; the agent still bundled ~12 changes into the one op of C-S9-04 (D-S9-01). See L14 |
| I3 a stated constraint persists | D-S9-02, D-S9-13 (Matthew rejected the agent's `all_texts` parse call and restated "(don't run the parse yet)"; then "don't run the full set") | scope limits persist like read-only limits -- see L4. *(The "Filing NOT authorized" brief once cited here, D-S10-04, was the orchestrating agent's prompt to its subagent, not Matthew's words -- V-S10-10 refuted by transcript)* |
| I4 a repeated standing request is not a new instruction | T-S8-06, T-S9-09 | the logged `User request` was frozen at the session's first message or agent-filled; only the latest operator turn counts. Messages Matthew typed **mid-turn** never reach the log at all (six in S9 alone, two in S8 -- among them his unslotted-affix and IsAbstract corrections) and arrive only after the in-flight tool call: his objection to the slot merge arrived after the merge write had landed (D-S6-08). *Status 2026-10-09: partial -- since FlexToolsMCP 2.15.0 `user_request` is kept per session and can be refreshed per call (#318); it is not refreshed automatically per operator turn* |
| I7 a lock is not a code error | T-S8-04, T-S8-12, T-S9-05, T-S11-08 | **refined:** after a parse, the lock holder was usually the MCP's own idle parse worker (identified by command line, `flextoolsmcp.server.parse.worker_main`). The agent could not end it (auto mode denied `Stop-Process`), `flextools_parse_release` did not exist until 09-24 15:41 (#225, built the same afternoon from the P0 Matthew ordered, D-S9-09), and Matthew killed workers by hand four times. The 09-30 holder was FLExBridge Send/Receive, not a worker. A worker started before your edits also parses a stale lexicon -- diagnose that before blaming shared mode (C-S9-07). *Status 2026-10-09: fixed -- an idle parse worker now drops the lock on its own (#223, FlexToolsMCP 2.13.0), and `project_locked` names our own worker with `flextools_parse_release` as the next step (#315, 2.15.0). Release-then-write stays as the fallback* |
| J1 status of every claim | D-S9-01, D-S10-03, D-S7-12 | Matthew explicitly asked for the AI's "deep knowledge of Swahili". The resulting entries, glosses and class choices are still AI-sourced and must be labelled so (see Q-42); the 647-verb transitivity classification was LLM-only with an adversarial second pass and no human review. Conversely, credit what was his: one sense per class, the unslotted-affix warning, class 13 under both features, the "No Parse" genre, the portmanteau ruling, the transitivity design, the pronoun move and the yeye/mwaka deletes are Matthew's decisions, not the AI's (D-S8-07, D-S8-08, D-S8-10, D-S7-08, L-S7-09, D-S7-14, C-S9-06, D-S9-04, C-S10-01) |
| K1 heuristic is not a Human approval | relapse C-S7-04, V-S7-06 *(other client, log only)* | see L9 |
| K3 GUID keys | C-S7-09 | **extended:** never key a script on a gloss either. An 807-gloss normalisation pass silently broke scripts that looked affixes up by gloss text |
| K4 disable before delete | D-S7-04, D-S8-12, D-S10-14; C-S8-07 | **resolved:** S4-S8 used `DoNotUseForParsing` both to soft-delete and to keep live whole-word entries out of the parser. Matthew doubted it ("I'm not sure exclude-from-parsing has an effect" / "in the UI, only "isAbstract" is surfaced", D-S8-12) and had it investigated: neither HermitCrab nor XAmple reads the flag (they skip only `IsAbstract` forms), so **every suppression made with it was a no-op** (D-S10-14). Refused at preflight since FlexToolsMCP 2.13.0 (PR #259); upstream ticket LT-22810. Keep the soft-before-hard order, with `IsAbstract` (K4 rewritten) |
| K7 verify the reviewer | D-S10-03; C-S7-10, C-S7-14, C-S11-09 | an orchestrator caught a subagent misreading deliberate review overturns as data errors (C-S7-10); write agents caught two false premises relayed from read-only proposals (`ziote` "not a word"; allomorph environments "on the sense"), and the no-deletion rail saved `ziote` (C-S7-14). The converse: a Claude review endorsed a pasted table of fabricated parses without opening the project (C-S11-09) -- see L16 |
| K10 stale analyses | V-S7-08; L-S8-01, L-S10-01, L-S11-01, C-S11-06 | **strongly confirmed from tool output** -- see L5 |

---

## K. Added from the Swahili corpus (S1-S5)

**K1. NEVER record a heuristic judgement as a Human approval.** A "fewest morphemes
wins" pass approved one analysis per word as the Human agent and disapproved genuine
alternatives; it had to be reversed (C-S2-01). Use a non-human agent or leave the
analysis unapproved. *Status 2026-10-09: partial -- flexicon's approve/reject
wrappers now persist (flexicon#24, #26, #56), but `ApproveAnalysis`/`RejectAnalysis`
always record the human `DefaultUserAgent`. A non-human verdict still needs raw
`ICmAgent.SetEvaluation` inside `with project.UndoableOperation(...)`.*

**K2. NEVER relax a slot to make a word parse** without checking what else it now
lets through. Prefer a separate template for the construction (C-S2-02, L-S5-02).

**K3. ALWAYS key targets by GUID** (or name + catalog id), never by hvo. Hvos shifted
within a session; hvo-keyed verification failed (C-S1-05, C-S3-05, D-S4-07).

**K4. ALWAYS disable before deleting** a lexical entry the parser uses: set
`IsAbstract` on its lexeme form and every allomorph, parse-check, then delete. List
referrers of everything disabled before the delete. A faulty heuristic was undone in
one minute because nothing had yet been deleted (D-S4-08, C-S4-01). The corpus used
`DoNotUseForParsing` for the disable step; that flag has no parser effect, so those
"disabled" entries were never out of the parser (D-S10-14), and FlexToolsMCP 2.13.0+
refuses it at preflight (`deprecated_member`). An entry leaves the parser only when its
lexeme form **and every** allomorph are abstract; affix-process forms ignore
`IsAbstract` in HermitCrab.

**K5. ALWAYS check references across an entry's owned subtree** (allomorphs, MSAs,
senses), not just the entry, and sweep for dangling analyses after any delete batch
(C-S5-01). The `form-usage-before-edit` recipe lists every analysis that uses an
entry's forms; there is still no dangling-analysis sweep (T-53, partial).

**K6. NEVER create custom fields or writing systems through raw LCM.** A raw-LCM
custom field did not persist, and the session that depended on it lost the lexicon
(C-S1-01). Custom fields: create them in the FLEx GUI (flexicon `CreateField` refuses
by policy, and the MCP blocks raw `AddCustomField` on write runs). Writing systems:
use `project.WritingSystems.Create/Ensure` (flexicon 4.12.0) with FLEx closed, or the
GUI. Since FlexToolsMCP 2.15.0 both schema changes are refused while FLEx holds the
project.

**K7. ALWAYS verify the reviewer.** Check a domain or AI reviewer's factual claims
("this stem is invented") against the lexicon before acting. Number the rulings and
cite them in the code that applies them (D-S4-10, D-S5-07).

**K8. NEVER default an undecidable value.** Hold it, or flag it (`class-negotiable`).
A default "cl.9/10" for unknown nouns cost 17 manual overrides (C-S1-04, D-S3-05).

**K9. NEVER accept a zero or empty result without a second route.** An accessor
returning None produced a plausible noun count of 0 (C-S3-03). *Status
2026-10-09: that accessor bug (flexicon#232) is fixed in flexicon 4.4.0 and sibling
silent-None bugs were swept, but None is still a legal "unset" answer, so the
second-route check stands.*

**K10. NEVER conclude the parser ignores something from analyses older than the last
reparse.** Re-check stored analyses against the current grammar first (C-S2-05,
D-S5-03). Strengthened by L5.

---

## L. Added from the Swahili corpus (S6-S11)

Most S6-S11 corrections are AI-behaviour failures rather than API failures. Evidence
was re-checked against the Claude Code transcripts on 2026-10-09 (S6-S10); S11's
client left no transcript, but the live project confirms its writes.

**L1. ONE writer per project at a time.** Parallel agents are fine for read-only work:
Matthew asked for subagents per part of speech (D-S6-13), the AI fanned them out
**read-only** ("concurrent writes into a live shared-mode project is asking for
trouble") and the four proposal agents ran safely (D-S6-12); read-only diagnosis
batches later fed a write stage (D-S10-03). The overnight write agents of 09-13 then
ran **sequentially**, by the orchestrator's choice -- the MCP server holds a single
global session, so parallel MCP agents would clobber each other's state (D-S7-10).
The writer conflicts came from outside that chain: the FLEx UI saved underneath two
runs (`FP_ConflictingSaveError`, C-S7-01), and a separate Claude session wrote the
same project 01:04-01:31 while the agents did (T-S7-03). A fresh-session verifier
could not see unsaved shared-mode writes and tried to recreate them (C-S7-13), and an
evening session's stale first read would have double-prefixed paradigm words had the
dry run not caught it, probably during another session's edit (C-S7-12). A second
client writing concurrently looped on the gates (C-S10-06 *(other client)*). *(Earlier
versions blamed "parallel writers" and a sibling's Description overwrite; refuted by
transcript -- see L2.)* Close FieldWorks before a bulk write; treat a "non-master
peer" write as provisional until a read after FLEx closes confirms it (C-S8-03,
D-S8-04); existence-check inside the writing script, and re-read after any conflict
error before retrying. Until the tooling has a write lease, the operator or
orchestrator must serialize writers -- across sessions and clients, not only across
subagents. *Status 2026-10-09: partial -- a conflicting save fails loudly with
`FP_ConflictingSaveError` (flexicon 4.6.0; assume that run's writes did not land),
schema changes are refused while FLEx holds the project (FlexToolsMCP 2.15.0), and
`user_request` is kept per session (#318); value writes are not gated and there is no
write lease (T-67, open).*

**L2. ALWAYS read an object's design record before changing it, and NEVER
"consolidate" a duplicate without asking why it exists.** The AI merged deliberately
cloned slots (Subj2, TAM2) after a clean validate_only; Matthew's objection, typed
mid-turn, arrived only after the write landed, and the AI reverted it a minute later
(C-S6-02, D-S6-08). On 09-13 a session changed templates at Matthew's request and had
the result parse-checked by him within minutes, but never read the template
Descriptions (C-S7-02); that evening another session called the documented
"ANCHOR: RelSuf is obligatory" "almost certainly not intended" and made TAM2 optional,
again without reading them. Write the reasons into the project (D-S6-09, D-S7-02),
and append to a shared Description field rather than replacing it: one agent's own
later run overwrote a Description written by an earlier agent, then restored the
original verbatim and appended its addendum (C-S7-01).

**L3. NEVER write grammar you cannot parse-check, and ALWAYS reparse after a grammar
write.** Before 09-13 01:56 no AI could run the parser: on 09-12 the AI asked Matthew
five times to Try A Word on the word it started from (C-S6-05), the overnight
subagents wrote with no parse at all, and agents declined correct-looking changes
"because the change cannot be verified" (D-S7-02, L-S7-01, T-S7-01). The loop closed
when Matthew ran the FLEx parser himself and fed back screenshots (09-13 01:20-01:41,
three fix cycles, D-S7-16); from 01:56 the valency programme drove HermitCrab in
process and parse-checked every write (1,054-form diff, V-S7-11). *(Earlier versions
called the 09-13 grammar writes blind; refuted by transcript.)* Genuinely blind
writes: 09-12, the 09-13 00:04-01:13 subagents, the 09-13 evening session ("I never
consulted FLEx's parser") and the 09-20 lexicon writes. From 09-24 every write was
followed by `try_word` or `parse_diff` -- with one lapse: the 09-25 glide fix was only
spot-checked, although the night before a 2,139-word sandbox regression had
recommended a different fix that nobody carried into the new chat (L-S10-02,
C-S10-08). Either the writer has `try_word` / `parse_text` / `parse_diff`, or the
change is recorded as "proposed, unverified" and not written. Carry test results
across chats. A new template must parse the forms that motivated it (C-S6-03).

**L4. NEVER start a corpus-wide parse or filing unasked, and NEVER confirm a filing
the operator has not seen.** The agent issued a `parse_text` over all 26,725 words;
Matthew rejected the call 42 s later and restated "(don't run the parse yet)", but the
run's worker had already loaded the old lexicon and made the next verification parse
meaningless (C-S9-01, D-S9-13, refuted as "unrequested and unnoticed" by transcript).
Matthew asks for filing as its own step ("apply the parsese to the project", D-S9-11;
"remove *mwaka, file the parses", C-S10-01). An order to file is not consent to an
unseen upper bound: the agent confirmed a preview that "may delete up to 24259
analyses ... cannot be undone" without showing him, and reconfirmed after a tool fix
without asking again; he saw the figure hours later ("why is this tool result so
large?"). 322 analyses were actually deleted (C-S10-02, L-S10-01; *earlier versions
called this filing self-authorized -- refuted*). A deferred filing must run or be
handed over: the S10 orchestrator held filing for a Stage 5 that never ran, so the
next "unparsed" queue was exactly Stage 1's fixed words (V-S11-04; the deferral was
the orchestrator's plan, not Matthew's -- V-S10-10 refuted). Inside a repair loop,
parse the top-N queue plus a fixed regression set; a corpus-wide run is its own,
requested step. *Status 2026-10-09: still open in the tool -- filing needs only
`confirmed=true` plus the `plan_id`, which an agent can supply itself (T-73); the
human gate is this rule. The preview is now compact enough to show (PR #252), and a
failed filing reports its reason (#239/#240).*

**L5. ALWAYS confirm a failure live before repairing it.** A wordform with no
parser-approved analysis in the database is not a failing word. Stored analyses record
the last FLEx parse, not the current grammar. The top three "unparsed" words parsed
(L-S8-01); in S9 5 of 20, 9 of 10 and 4 of 5 queue words already parsed and only
needed filing (T-S9-14); 9 of the top 10 parsed (D-S10-01); a refile alone moved
14,096 -> 9,260 unparsed with no grammar change (L-S10-01); all 10 targets of a
4-hour repair session parsed in 2 minutes once the parse tools were used, because S10
Stage 1 had fixed them and never filed (L-S11-01, C-S11-06, V-S11-04). Step 0 of any
repair: `try_word` the candidate, or refile, and drop it if it parses. "Parses" is not
"parses correctly" either: *waovu* parsed only as a verb, *maagizo* has no
ma- + *agizo* analysis (L-S9-12, L-S11-04). Never infer a lexicon change's effect from
stored counts: the 09-20 y- split was credited with fixing *yake*, whose zero was
staleness (C-S8-07).

**L6. Parsing questions go to the parse tools; `run_module` is for lexicon reads and
writes.** In S11 the agent hand-built a frequency queue four times in `run_module` and
got it wrong three times: invented words, object counts (all 1), alphabetical order
(C-S11-01, C-S11-02, C-S11-03); calling the parser inside a script was blocked or
returned nothing readable (T-S11-02; since FlexToolsMCP 2.15.0 it is reported as
`unknown_method`, #306). The dedicated tools answered correctly on the first try
(T-S11-01). The failure queue is a defined query -- token occurrences, descending, no
current parser analysis -- not something to improvise (D-S11-02); `flextools_parse_text`
orders its scope by occurrence and reports `NumZeroParses`. Resolve exact headwords
(homograph number, bound-stem `*`) before a restricted `try_word` (T-S8-02, T-S9-02);
*status 2026-10-09: still open* -- the resolver offers no candidates, so look pieces up
with the `lexicon-form-lookup` recipe.

**L7. NEVER probe API semantics in the work project.** A by-name guess
(`ReplaceMoForm`) on a throwaway entry, under `undoable=False`, left an orphan with a
NULL lexeme form in the work project; there was no rollback. FieldWorks calls it only
with a freshly created form, so passing an existing one removes rather than promotes
(C-S6-01, T-S6-04). Run
experiments in a test project or a parse sandbox (T-S9-08), or on throwaway objects
with collision-proof names (D-S7-05, C-S7-03), clean up, and verify the cleanup
independently. *Status 2026-10-09: write runs now roll back a failing operation
(FlexToolsMCP 2.13.0), but undocumented LCM members such as `ReplaceMoForm` are still
guesswork, so the rule stands.* When a wrapper is missing, port the host
application's own command (FieldWorks `SwapAllomorphWithLexeme`; *still no flexicon
wrapper*) and prove it on a throwaway first (D-S6-05).
After any failed write, sweep for orphans (entries created today, NULL or empty lexeme
forms, no senses) -- see L15.

**L8. NEVER treat AI-generated forms as data, and NEVER invent tool output.** Observed
in S7-S11:
- **fabricated parser output**: the 09-30 client reported decompositions such as
  `[el-fu]`, `[is-hara]`, `[ghadha-bu]` and called the parser "hallucinating"; the
  tools had returned counts only, and the surviving traces show whole-stem parses
  (`^0+elfu`). Five minutes later it created those fragments as "missing morphemes"
  (C-S11-08 *(other client)*, D-S11-04). When a tool gives no breakdown, say so;
- a diagnostic script that "simulated" the corpus with a made-up word list (C-S11-01);
- "must survive" probe sets containing likely non-words (C-S7-07);
- string-concatenation paradigm generators producing non-words wherever phonology,
  suppletion or agreement applies (C-S7-05);
- syllable splits created as bare entries -- **9 committed** (malaka, el, kumu, gizo,
  is, hara, en, ghadha, bu; stem, one empty sense; still in the work project, not yet
  sent by Send/Receive; C-S11-05, T-S11-10). `fu` was a real Stage 1 root;
- "monomorphemic" verdicts from a string match on a result object, or from a parse
  failure (C-S11-04);
- regex affix stripping reported as "497 new stems requiring injection" (C-S8-04
  *(other client)*).

A bad run can outlive itself: the evening triage generalized the 09-30 junk-creation
script into the shipped recipe `ensure-morpheme-entries` (PR #337) without noticing the
"morphemes" were syllables, and the run is still stored as local recipe
`local-be769c1f63ae` (T-S11-11). Review recipes promoted from failed runs.

Data under study comes from the project. Probe and paradigm forms are attested, or
labelled generated and proofread, with structurally invalid forms moved to a negative
"No Parse" set (D-S7-08). A new stem needs a segmentation a linguist would accept,
plus a sense, gloss and POS -- never a bare `LexEntry.Create(form)`. No agent may
propose stems from unanalysed wordforms before it has parsed at least one and read the
result.

**L9. NEVER let one heuristic pass create lexicon, analyses and approvals together.**
The S2 lesson (K1) recurred in a write-mode session that segmented generated wordforms
heuristically, created entries and allomorphs, approved the analyses, and left 424
duplicate allomorphs after a type error (C-S7-04, V-S7-06 *(other client, log
only)*). Approval is a human act; heuristic output is at most a parser-agent filing.

**L10. Delete only what the operator named, and NEVER skip a promised confirmation.**
Matthew asked to "identify and remove all incomplete user analyses"; the agent said it
would "only delete after you confirm", then sent the delete with `confirmed: true` 20 s
after the survey without showing him the list, although it had itself suggested
linking 14 of the 18 rather than deleting them. Only the project lock stopped it
(C-S8-06; *earlier versions called the delete unauthorized -- refuted by transcript;
the lapse is the skipped confirmation*). Approving one deletion does not license a
sweep: "the human analyses are junk" meant *yeye*'s analysis, and when the agent
widened it to every similar analysis Matthew corrected it mid-turn -- "i didn't mean
the definition was junk, the analysis was bad" (D-S9-04). Survey first (human vs
parser, completeness, text references), show the list, then stop (D-S8-14). Keep the
layers apart: analysis, sense and definition are separate objects.

**L11. STOP after two identical failures.** Change approach or report to the operator.
S11 had three loops: 14 consecutive identical caller errors (flexicon#600), 5x
following false cast advice, 6x the same pre-flight rejection (C-S11-07, T-S11-04,
T-S11-09; about 55% of that day's runs were pre-flight rejections, FlexToolsMCP#334). A rule disable was retried
four times without ever persisting (C-S9-02); eight bundle-reorder attempts were
blocked before Matthew redirected the fix to the text (C-S7-08). *Status 2026-10-09:
most causes are fixed, the rule stands -- the S6-S11 pre-flight loops by FlexToolsMCP
2.15.0 (#303, #334, #340, #319; an identical resubmit gets help on the first repeat);
the str-argument error now raises `FP_ParameterError` naming the expected type
(flexicon 4.12.0, #600/#618); rules are disabled with `PhonRules.SetDisabled` (4.12.0).
The false cast advice on `ParseResult` (T-S11-04) is still open, and there is no hard
circuit breaker.*

**L12. ALWAYS verify persistence by reopening.** "now disabled=True" inside the op
meant nothing; every reopen showed False (C-S9-02). After a teardown, commit or
`AbandonedMutexException` warning, the next action is a separate read-only check, and
two failed checks mean stop (T-S9-06). *Status 2026-10-09: partial -- the teardown
mutex loop is fixed and runs report `writes_committed` (FlexToolsMCP 2.15.0, #302);
there is no automatic reopen-verify (T-71), so this rule stands.*

**L13. Match the agent to the job.** Weaker clients looped on the gates, guessed APIs,
and in S11 spent a day (about 65 runs, about 15% successful) fixing words that already
parsed, then fabricated parser output and committed nine junk entries (T-S6-08,
C-S8-04, C-S10-06, T-S11-09, C-S11-08 *(other clients; S11's client unidentified, not
Claude Code)*). The same task on the same day went nowhere with a local model and was
productive with Claude Code (S8). Do not run a weaker client in write mode on the work
project, and never alongside another writer (L1).

**L14. Build exactly what was approved; return any deviation for a decision.** Matthew
chose the relative template from a preview showing `TAM` and optional `Obj`; the AI
built it with `TAM2` and a required `Obj`, so it licensed nothing (D-S6-03, D-S6-14,
C-S6-03). After Matthew approved all eleven grammar options and said "I do want you to
build it properly", the AI narrowed "derivational -aji/-o/-i" back to whole-word
entries on its own (C-S10-09, D-S10-15, D-S10-16). The good pattern: when the chosen
option failed in the sandbox, the agent tested an alternative and stopped -- "What
worked is different from what you picked, so I need your decision first" (D-S9-16).

**L15. A failed write run is not a no-op -- read the database back.** On 09-30 a
script's creation loop made nine bare entries, then the script raised; the runner's
`finally` closes the project, which is where writes commit, so all nine landed. The
error response then carried `"messages": []`, so the agent never saw its own "Created
new entry" lines and read the run as "nothing happened" (T-S11-10, C-S11-05). Per-
operation rollback (FlexToolsMCP 2.13.0) undoes only the operation that raised, not
the ones before it. After any failed write run: query for what the script would have
created or changed (entries created today, the target GUIDs), and do not rerun until
you know. Put writes after the code that can fail, or wrap them all in
`with project.UndoableOperation(...)` so they stand or fall together. *Status
2026-10-09: partial -- a failed run now returns the script's messages (#347,
FlexToolsMCP 2.15.0); commit-on-error is unchanged (`execution.py` closes, and so
saves, in `finally`), and there is no automatic reopen-verify (T-71).*

**L16. Re-derive before you relay or endorse.** Check a claim against the project
before passing it on, whether it comes from a tool, a subagent or a pasted transcript.
Claude, asked "are these analyses correct" over the 09-30 client's table, explained
the fragments as "junk fragment entries ... probably leftovers from an import" while
saying "I haven't looked at the project's lexicon"; the fragments did not exist yet
(C-S11-09, D-S11-05). An agent repeated the tool's "FLEx has this project open" advisory
to Matthew when FLEx was closed and project sharing was merely enabled (C-S10-07, wording
fixed). An orchestrator told Matthew Stage 1 "took about 5.5 hours, mostly because
parsing is slow"; the agent had finished its writes by about 17:20 and sat idle until
re-prompted at 22:36 (C-S10-10).
Cross-checking with a second assistant is the right instinct only if the checker
re-derives the data.
