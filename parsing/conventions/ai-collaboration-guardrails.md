# AI Collaboration Guardrails

[Back to README](../README.md)

Derived from every "Corrections To The AI" section across all nine shards
(C-M1-01..06, C-M2-01..06, C-M3-01..05, C-M4-01..03, C-M5-01..06, C-M6-01..04,
C-M7-01..03, C-M8-01..05, C-G1-01..03 -- 41 corrections in total).

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
</content>
</invoke>
