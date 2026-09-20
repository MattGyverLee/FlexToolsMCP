# FLEx Data Conventions

[Back to README](../README.md)

Project-level conventions that apply at every stage. These are language-neutral except
where marked. Each is sourced; most were learned by something breaking.

---

## 1. Unicode and normalization

**The rule:** LCM stores vernacular text **decomposed**. Every comparison, dedup,
existence check and dictionary key must normalize **both sides**.

> "Redo the existence check with Unicode normalization on both sides, since LCM stores
> decomposed forms." (D-M8-02)

- Use **composed (NFC)** form for whole-form display, comparison and dedup.
- Use **decomposed (NFD)** form for per-character / per-phoneme comparison against
  phoneme code representations (M3 §6). The corpus aliased both as one-letter helpers
  at the top of nearly every snippet.
- Normalize the imported text file itself, not only the comparison code.

**Failure mode this prevents:** three duplicate allomorphs were created because an NFC
literal was compared against NFD-stored text, so the "already have this form" guard
silently missed (C-M2-03). The same class of miss produced false negatives in an
existence check (D-M8-02).

---

## 2. Writing systems

- Populate **every** lexeme and allomorph in all the project's writing systems:
  vernacular script, transliteration, and analysis-language gloss.
  > "Each lexeme should be populated with the string in the [vernacular] WS and
  > [transliteration] WS. English gloss should be filled in along with category."
  > (D-M2-03)
- Resolve writing systems through the **sanctioned lookup helper**, not raw
  ServiceLocator iteration -- the latter triggers a casting rejection (C-M4-02).
- Use integer **handles** as dictionary keys; writing-system definition objects are not
  JSON-serializable (C-M5-03).
- **Environment strings**: a one-off environment containing a vernacular character must
  be authored **entirely** in the vernacular WS, or FLEx renders boxes (D-M3-05).
- The corpus maintained a transliteration on every form via a custom transliterator
  reused verbatim across operations (M4 §6).

---

## 3. Empty-value handling

- FLEx/LCM uses `***` as the placeholder for an empty multilingual string. Normalize it
  to the empty string uniformly via a small helper (G1 §6, M8 §6). Flexicon's public
  methods already do this; direct C# field access does not -- see the project
  `CLAUDE.md`.
- Treat `None` and `***` identically.

---

## 4. Entry creation

- Create with `create_blank_sense=False`, then add the sense explicitly (M1 §6,
  G1 §6).
- Morph types used consistently: `stem` for lexical stems, `suffix` / `prefix` for
  affixes, `enclitic` for clitics.
- **Set the citation form explicitly on affix entries** or they display as `-???` in
  the FLEx lexicon (M7 §6).
- **Enclitics** need both a stem MSA carrying the host POS on their sense **and** an
  explicit "attaches to" collection; there is no wrapper, so drop to raw LCM (M2 §6).
- **Homographs are separate entries.** When a needed morpheme collides with an
  unrelated existing entry, create a homograph and log the collision -- do not reuse
  the entry (L-M6-05, D-M5-03).
- Strip homograph numbers from headwords when matching (G1 §6).

---

## 5. Source of truth and staging

- **Every paradigm/vocabulary definition lives in a versioned file outside the
  database** -- a Python data module or JSON in the scratchpad -- never only in the
  database and never only inline in a snippet.
- Each data module exposes a **`check()` invariant validator** returning rows and
  errors, and the write **refuses** if it fails: *"refusing to write: fix [the data
  module] first"* (M2 §5, M1 §6).
- **Re-derive expected counts from the same source module** used to write; never
  hardcode a separate expected-total literal (M2 §5). Hardcoded baselines drift and
  produce phantom regressions (C-M2-06).
- Move large data out of inline Python into JSON once it grows -- it shrinks the code
  fingerprint the preflight sees and makes the data reviewable (M6 §6).
- Staging files observed: import plans, oblique builds, phrase lists, sentence lists,
  new-lexicon rounds, retired-entry backups, existing-entry snapshots, phoneme dumps,
  a 192-row verb inventory TSV, and a per-item conversion log.
- **Write large inventories to a file, not to report output** -- output is capped and
  truncates silently (M8 §6: 320 messages truncated to 100).

---

## 6. Writes: gating and safety

- **Every mutating statement inside `if modifyAllowed:`.** This is a hard preflight
  gate; violations are rejected outright (C-M3-02, C-M6-01, C-M8-04).
- **`validate_only` dry run with the identical code fingerprint before every live
  write.** In the late corpus this is unconditional, with no exceptions (M7 §9).
- **Plan first, mutate second** for anything destructive or structural: compute the
  partition read-only, print counts, then mutate. Remove collection indices in
  **descending** order (D-M7-03, D-M7-04).
- **Back up entry content before deleting** anything whose gloss/definition work is
  real (D-M5-10). `.fwdata` backups are taken automatically before writes, but content
  dumps are on you.
- **Guard every add against `None`** -- a `None` variant type crashed mid-write and
  left half-built entries (C-M6-02).
- **Never remove the last child of a required collection**; warn instead (D-M7-06).
- **Check referrers before deleting** any shared object (M3 §6).

### The atomicity hazard

Three separate shards record the same stderr warning:

> "writeEnabled=True with an explicit undoable=False ... no reachable rollback-to-mark
> API in this mode ... the atomicity unit for this whole session is the SESSION, not
> the operation" (M5 §6, M6 §6, M8 §6)

**A mid-operation failure leaves partial mutations permanently in the cache.** Every
convention in this section is partly a mitigation for that. Design bulk scripts so
that a crash at any point leaves a state you can detect and repair (C-M6-02's repair
pass is the model).

---

## 7. Concurrency

- `[SHARED]` mode: the project may be open in another process; writes proceed as a
  "non-master peer". The corpus always proceeded. Whether that is safe is
  [open](../open-questions.md) (Q-02).
- `project_locked` rejections are **environmental flakes**, not logic bugs; retry
  (C-M3-05, C-M5-02). Distinguish them in triage.
- **A human GUI edit is a legitimate external state change.** Restores (D-M3-03),
  category restructuring (D-M5-02), and independently-created possibility items
  (D-M5-05) all happened. Re-derive state rather than assuming your writes are the
  last word.

---

## 8. Polymorphic casting

The single most frequent class of error in the corpus (C-M1-01, C-M1-02, C-M2-01,
C-M3-03, C-M3-04, C-M4-01, C-M4-03, C-M6-04, C-M7-02, C-M7-03, C-M8-01, C-M8-02,
C-M8-03, C-M8-05).

- **Cast every object to its most specific known interface immediately** after getting
  it from a polymorphic reference or collection (M8 §6).
- **Branch on the object's class name before casting** when the underlying class varies
  (C-M6-04).
- **Expect sibling interfaces on the same object.** Inflection-class membership and
  phonological environments live on different interfaces of the same morph object:
  *"Same object, different interfaces."* (C-M4-01.)
- **Do not assume a property exists on a related interface** (C-M8-03, C-M8-05).
  Resolve it first.
- **None-check any relational property before iterating it** (C-M7-02).
- **Recurse possibility trees**; do not assume a flat list (C-M6-02).
- Read-only runs get casting **warnings**; write runs get hard **rejections** for the
  same issue (M4 §6, M6 §6). Do not let a clean read-only run lull you.
- Use the MCP's property resolver **proactively** before writing loop code against any
  `OC` / `RC` / `OA` / `RA` property (C-M6-04).

---

## 9. Import, export and downstream sync

- **New objects are published everywhere by default.** In LCM a brand-new entry, sense
  or example is published in every publication it is not *explicitly* excluded from --
  the exclusion collection is opt-out, not opt-in. If the project uses publications,
  exclude new objects from all non-target publications **in the same pass that creates
  them** (C-G1-03, D-G1-05). *(From the German deck project; language-independent per
  G1 §9.)*
- **LCM does not bump an entry's modified date** when only a linked sense, example or
  reference collection changes. Downstream sync tooling keys off that date, so restamp
  the owning entry explicitly after any such edit (D-G1-04). *(Same provenance.)*
- **Never auto-merge an ambiguous match.** An entry that exists but does not match on
  identity is a hard skip with a warning for manual resolution (G1 §5).
- **Consolidate bookkeeping into one atomic pass** rather than several sequential
  scripts; it closes the drift window (D-G1-05).
- Coerce interop objects to plain strings/ints before serializing (C-M5-03).

---

## 10. Code style for snippets

- **Bare snippets** are the normal form; full module structure only when the code is
  being saved as a reusable module. (This matches the project `CLAUDE.md`.)
- **"Do the cheap version first"** (D-M7-01) -- minimal, least-casted snippet; escalate
  only on failure.
- Import every flexicon operations class you use, including in helpers called deep in
  a script (C-M6-01).
- Verify import names against the actual API surface; several plausible-sounding
  operations-class names do not exist (C-M1-03, C-M2-04, C-M3-01).
- Prefer wrapped accessors over raw ServiceLocator repository calls when a wrapper
  exists (C-M1-04) -- **except** where the wrapper assumes a single concrete subtype
  and throws on the other (C-M1-02, C-M2-01), in which case drop to raw LCM.
- Pick one string-formatting style per snippet (C-M2-02).
- Report each mutation individually, and re-list the state "AFTER" in the same
  operation (M3 §5).

---

## 11. Naming

- Natural classes, environments, inflection classes and stem names get **descriptive
  English names** plus short abbreviations (D-M3-05). Names in the analysis writing
  system.
- Categories come from the **FLEx catalog** where one fits, with the catalog source id
  recorded (D-M5-01). Phonological features likewise (D-M1-05).
- **Derive names used by a downstream script from the created objects**, not by
  re-typing them -- a name mismatch between a creation script and its consumer failed
  all 69 rows of an import (C-M5-01).

---

## 12. Merge seam

Matthew's conventions go alongside these, marked with their own provenance. Expect
divergence in: staging format (data module vs JSON vs LIFT), transliteration practice,
whether publications are used at all, and snippet style. Where two conventions
conflict and both work, record both and note which project uses which -- do not
silently pick one.
</content>
</invoke>
