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
- **Normalization does not unify look-alike characters.** The phoneme `ng'` was coded
  with U+0027 while the corpus used U+02BC; words with it parsed only under a forced
  hypothesis. A per-grapheme parse-rate table exposes this (D-S10-06, L-S8-05).
  Matthew approved recoding `ng'` to U+02BC on 09-25 (D-S10-16); only the lexicon
  stage of that programme ran, so check whether it was applied.

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
  the FLEx lexicon (M7 §6). Use `project.LexEntry.SetCitationForm`; `LexEntry.Create`
  still does not fill it for affixes (T-38).
- **Enclitics** need both a stem MSA carrying the host POS on their sense **and** an
  explicit "attaches to" collection; there is no wrapper, so drop to raw LCM (M2 §6).
  *Status 2026-10-09: still open* -- flexicon has no wrapper for
  `IMoStemMsa.FromPartsOfSpeechRC` (T-39).
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
- **Write large inventories to a file, not to report output** -- output is capped at
  100 `report.Info` lines (M8 §6: 320 messages truncated to 100). The truncation is no
  longer silent (`summary.info_truncated`), and `max_info_messages=0` lifts the cap
  (MCP#25, #43); there is still no automatic spill to a file.

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
  real (D-M5-10). `.fwdata` backups are taken automatically on the first write per
  project and session (pruned by size and age, #218), but content dumps are on you.
  With FLEx open the backup holds only what FLEx has flushed to disk.
- **Guard every add against `None`** -- a `None` variant type crashed mid-write and
  left half-built entries (C-M6-02). A `None` argument to a flexicon wrapper now raises
  `FP_NullParameterError` before writing, and the operation rolls back; variant
  `FindType` still recurses only one level, so the lookup guard stays.
- **Never remove the last child of a required collection**; warn instead (D-M7-06).
- **Check referrers before deleting** any shared object (M3 §6).

### The atomicity hazard

Three separate shards record the same stderr warning:

> "writeEnabled=True with an explicit undoable=False ... no reachable rollback-to-mark
> API in this mode ... the atomicity unit for this whole session is the SESSION, not
> the operation" (M5 §6, M6 §6, M8 §6)

**In that mode a mid-operation failure left partial mutations permanently in the
cache.** Every convention in this section is partly a mitigation for that. Design bulk
scripts so that a crash at any point leaves a state you can detect and repair
(C-M6-02's repair pass is the model).

The Swahili logs add four instances: a failed delete left an orphan entry with a NULL
lexeme form (C-S6-01); a first module write failed part-way and left two entries with
a gloss but no POS or MSA (C-S8-05); a 12-change op failed half-way, with everything
before the failing rule cast applied (C-S9-04); and on 09-30 a script created nine bare
entries and then raised -- the runner's `finally` closes the project, which is where
writes commit, so all nine landed, and the error response showed no messages, so the
run was read as "nothing happened" (C-S11-05, T-S11-10). After any failed write run,
read the database back before rerunning.

*Status 2026-10-09: fixed for single operations.* Since flexicon 4.4.0 each flexicon
write runs in its own unit of work and rolls back on an exception, and since
FlexToolsMCP 2.13.0 write runs open `undoable=True` (MCP#144; the result reports
`undoable: true`). Every log above predates 2026-09-25. A script is still a sequence
of committed operations: to make the whole script atomic, put its writes inside
`with project.UndoableOperation("label"):` (verified in flexicon#579). Raw LCM writes
also need that block; without it the run returns `no_unit_of_work` (MCP#310).
**Commit-on-error is unchanged:** a script that raises still commits every operation
that completed before the raise, because the runner saves in `finally`. Since
FlexToolsMCP 2.15.0 the failed run at least returns the script's messages (#347), so
read them, then verify in the database (guardrails L15).

---

## 7. Concurrency

- `[SHARED]` mode: the project may be open in another process; writes proceed as a
  "non-master peer". The corpus always proceeded. Whether that is safe is
  [open](../open-questions.md) (Q-02). **Swahili evidence that it is not:** peer writes
  lost commits to `FP_ConflictingSaveError` when the FLEx UI saved underneath them
  (C-S7-01, C-S8-03), a second Claude session wrote the same project at the same time
  (T-S7-03), and teardowns failed with `AbandonedMutexException`, leaving some writes
  committed and one not (T-S9-06). *(The 09-13 subagents ran one at a time; the
  conflicts were not between siblings -- corrected by transcript.)* A fresh session
  reads the file on disk, not the shared commit log, so it cannot see peer writes FLEx
  has not saved; a verifier nearly recreated objects that already existed (C-S7-13).
  Existence-check inside the writing script. "Shared mode" can also mean only that
  project sharing is enabled (`projectSharing="true"` in
  `SharedSettings/LexiconSettings.plsx`) with FLEx closed; the advisory wording is
  fixed (C-S10-07). Close FLEx before bulk writes and run one writer at a time,
  across sessions and clients. *Status 2026-10-09:
  partial -- a conflicting save now fails loudly (`FP_ConflictingSaveError`, flexicon
  4.6.0; assume the run's writes did not land); the teardown mutex loop is fixed and
  runs report `writes_committed` (FlexToolsMCP 2.15.0, #302); schema changes are
  refused while FLEx holds the project (2.15.0). Value writes are not gated and there
  is no write lease.*
- `project_locked` rejections are **environmental flakes**, not logic bugs; retry
  (C-M3-05, C-M5-02). Distinguish them in triage. **Refined (S8-S9):** right after a
  parse, the holder was usually the MCP's own idle parse worker (a python PID running
  `flextoolsmcp.server.parse.worker_main`); `flextools_parse_release` did not exist
  until 09-24 15:41, so Matthew killed workers by hand (T-S8-04, T-S9-05). A worker
  started before your edits also parses the old lexicon: rule out a stale worker
  before blaming shared mode (C-S9-01, C-S9-07). The 09-30 holder was FLExBridge
  Send/Receive (T-S11-08). *Status 2026-10-09: fixed -- the idle parse worker now
  drops the lock by itself (#223, FlexToolsMCP 2.13.0), and `project_locked` names
  this server's worker and gives `flextools_parse_release` in `next_steps` (#315,
  2.15.0). Release-then-write remains the fallback.*
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
  exists (C-M1-04). The corpus had to drop to raw LCM where a wrapper assumed one
  concrete subtype and threw on the other (C-M1-02, C-M2-01, T-S9-10); that is fixed:
  `Allomorphs.GetForm/SetForm` handle stem and affix allomorphs since flexicon 4.10.0
  (subtype dispatch since 4.6.0; the GetAll-wrapper crash fixed by #449 in 4.10.0),
  so use the wrapper. If a wrapper still throws on
  one subtype, report it and fall back to raw LCM for that call only.
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

**Merge status:** Matthew's conventions are in section 13 (shards S1-S11; S1-S5 and
S6-S11 come from two machines, so both machines' logs are now covered).

---

## 13. Conventions from the Swahili corpus (Matthew)

Recorded alongside sections 1-11, not replacing them. Shards S1-S5 first, then S6-S11
(13a-13e). The S6-S10 claims were re-checked against the Claude Code transcripts on
2026-10-09, which keep the tool output and mid-turn messages the logs lost. Several
sessions were other clients (local models, Matthew's Hermes setup, the unidentified
client of S11), so their practice is cited only as failure evidence.

- **Stable identity.** Key every planned write and every verification by GUID, or by
  name plus catalog id, never by hvo. Hvos shifted within a session (C-S1-05,
  C-S3-05, D-S4-07). A GUID manifest can still go stale across sessions, so resolve
  tolerantly and count "already absent" (C-S5-02). A stale GUID now raises
  `FP_ParameterError` from `project.Object()` (flexicon#262), so catch that; there is
  still no manifest executor (T-56). `project.Object()` returns an uncast
  `ICmObject` -- cast it before calling entry or sense members.
- **Fully specified agreement features.** Every noun stem and class affix carries all
  of its agreement features, with `NA` filling the inapplicable ones, so unification
  is exact (D-S1-06). After any feature refactor, run a pass to restore missing
  fillers (C-S3-02). **REVISES (V-S10-02 vs D-S1-06):** by 09-25 the feature system
  has no `NA` value; each noun stem and null prefix carries only its class value.
  Unification needs an exact value match, so a legacy value variant (stems on `1a`,
  concords on `1`) needs its own agreement sense (D-S8-11).
- **Catalog provenance for inflection features too.** Prefer catalog-sourced features
  and values (EticGlossList), and record their `CatalogSourceId`. Migrate custom
  look-alikes by repointing the specs, then delete them (D-S3-01). Nested EticGlossList
  features import since 2026-06-21 (flexlibs#192); repointing is still by hand
  (`MSA.GetFeatures` + `MakeFeatStruc`; no copy/migrate helper, T-58).
- **Soft delete and hiding from the parser: `IsAbstract` on the forms.** Set
  `IsAbstract` on the lexeme form and every allomorph as the reversible first step of
  any retirement; parse-check, then delete. The flag lives on each `IMoForm`
  (`entry.LexemeFormOA`, `entry.AlternateFormsOS[*]`); there is no `entry.IsAbstract`.
  An entry drops out of the parser only when its lexeme form **and every** alternate
  are abstract, and HermitCrab ignores `IsAbstract` on affix-process forms. Recipe
  `hide-entry-from-parser`; flexicon `Allomorph.Get/SetIsAbstract` (#546).
- **Never `DoNotUseForParsing`.** The corpus used it to soft-delete (D-S4-08) and to
  keep live whole-word entries out of the parser (D-S7-04, D-S8-12). Matthew doubted
  it -- "in the UI, only "isAbstract" is surfaced" -- and had FieldWorks read: neither
  HermitCrab (`HCLoader.cs:543`, `:585`) nor XAmple reads the flag; it survives only in
  the model and LIFT. **Every suppression made with it in S4-S8 did nothing** (the
  cl.16 null prefix and the 12 possessives were never out of the parser), and it is
  refused at preflight since FlexToolsMCP 2.13.0 (PR #259, `deprecated_member`)
  (D-S10-14). Matthew's position: `IsAbstract` is being "abused" for hiding, and the
  old field may be implemented upstream (LT-22810, watched weekly). Still open: the 33
  entries that carry the flag -- moving them to `IsAbstract` changes parser output,
  so diff a fresh parse first. "Listed but not parsed" needs its own convention.
- **Schema.** Create custom fields in the FLEx GUI, not through raw LCM (C-S1-01):
  flexicon `CustomFields.CreateField` refuses by policy and the MCP blocks raw
  `AddCustomField` on write runs. Writing systems can be added with
  `project.WritingSystems.Create/Ensure` (flexicon 4.12.0) with FLEx closed. Both
  schema changes are refused while FLEx holds the project (FlexToolsMCP 2.15.0).
- **Staging format.** Data tables inside the module for builds (S1). GUID-keyed JSON
  plan and manifest files for cleanups and tagging (S5).
- **Lexeme and citation forms (Swahili).** For nouns, the lexeme form is the bound stem
  and the citation form is the full singular word. For verbs, the citation is `ku`+stem
  or `ku`+stem+V, and that difference encodes the inflection class (D-S3-03, D-S5-04).
  This answers Q-12 for this project: a POS can need a citation form distinct from the
  lexeme form, and the difference can carry information.
- **Case.** Upper-case graphemes live in the phoneme inventory, with no capitalised
  allomorphs or entries (D-S5-02). By 09-25 that had slipped: a capitalised `Roho`
  allomorph existed and doubled *roho*'s analyses (V-S10-07, V-S10-09).
- **Outside sources.** Facts may be taken from licence-compatible sources. Glosses are
  re-authored. Restricted sources are used to validate only (D-S3-05).

### 13a. Entries and forms (S6-S11)

- **The lexeme form is the elsewhere form.** It carries no environment; every
  alternate is conditioned. Matthew stated it ("the 'default/everywhere' form of the
  affix should be the lexeme") and had the 20 multi-allomorph entries surveyed: none
  had an unconditioned lexeme form. 15 swaps and 19 cleared environments followed,
  with all 3,526 morph-bundle references unchanged (D-S6-04, D-S6-06, V-S6-01). Later
  prefix entries follow it and parse (V-S9-04, V-S10-04). **REVISES** the S1
  arrangement with the most-restricted form in the lexeme (L-S1-02); see README 4.11
  and Q-37.
- **Swap lexeme and allomorph by moving owned objects, not by rewriting forms.**
  FieldWorks' `SwapAllomorphWithLexeme`: insert the old lexeme into the alternate forms
  at the allomorph's index, then assign the allomorph as the lexeme form. Object
  identity survives, so stored analyses stay valid; verify with morph-bundle reference
  counts before and after (D-S6-05, L-S6-02). Do not substitute LCM's
  `ReplaceMoForm`: FieldWorks calls it only with a freshly created form, and given an
  existing one it removes rather than promotes (C-S6-01). *Status 2026-10-09: still
  open* -- no flexicon swap wrapper (T-65); port the command and prove it on a
  throwaway entry.
- **Pass affix forms bare.** The morph type supplies the hyphen; `Create("-ye",
  "suffix")` produced a doubled marker (L-S6-03).
- **Morph type is part of parseability.** A free word typed as bound stem (`*yeye`)
  fails or mis-parses; retyping it to `stem` fixed it (D-S9-03).
- **Prefix out of the lexeme form.** A noun entered with its class prefix baked in gets
  lexeme form = bare stem and citation form = full word (`anadamu` / `mwanadamu`,
  L-S10-06). Consistent with the lexeme/citation bullet above.
- **Model a new entry on a parsing comparator.** Read a *parsing* entry of the same kind
  first (a proper noun, a noun, an adjective) and copy its POS, feature names and
  inflection class verbatim (D-S10-07). Proper nouns carry a class feature so a null
  class prefix can fill an obligatory slot (L-S9-04).
- **Entry identity is form + morph type.** A lookup that stripped hyphens took the
  passive suffix `-w` for the prefix `w-` and would have written eight senses onto it;
  the dry run caught it (C-S8-08). `LexEntryOperations.Find()` matches fuzzily, so
  never find-or-create a short throwaway form: *oz*/*uz* hit `kuoza` and `kuuza`
  (C-S7-03).
- **Duplicate guards key on form + POS (+ gloss).** A (form, gloss) key skipped a noun
  because a verb shared both (C-S10-04). Deletes are guarded by GUID **and** expected
  headword, after a zero-reference check (C-S10-01; the delete was Matthew's call,
  "remove *mwaka").
- **Look features up by name or abbreviation.** `Find("nagr")` returned None because
  `nagr` is the abbreviation of "noun agreement"; this project's POS name "Proper  Noun"
  has a double space, so copy it from a comparator (C-S8-09, D-S10-07).
- **Build the grammar properly rather than listing whole words**, when the operator
  asks for it: "I do want you to build it properly" (D-S10-15).
- **Derived stems are not allomorphs.** An allomorph list with no environments
  (*zalia*, *zaliwa* under *zaa*) signals derivation stored as allomorphy (L-S10-04).

### 13b. Senses, glosses and agreement (S7-S8)

- **Short gloss, full original in Definition.** A bulk cleanup gave each of 808 senses a
  short gloss and moved the full original gloss verbatim into the Definition (D-S8-01).
  Moving "(v)", "(tr)" qualifiers out of the gloss may drop category hints on senses
  without a POS; check before such a pass.
- **Grammatical-morpheme glosses use a project-local dotted scheme** (`sbj.nc10`,
  `conn.conc.nc4`, `neg.3sg.nc1`). The agent called it Leipzig; it is not (lowercase,
  `nc` prefix, words such as `conc`, `pref`). Record it as a project convention
  (D-S8-02). The 09-14 pass was run by a local-model client.
- **Never key a script on a gloss.** Gloss passes change them wholesale (C-S7-09). Key
  by GUID, or by form + morph type.
- **One feature structure per sense, so one sense per agreement value** (Matthew's
  rule: "For the y affix you may need to add it with multiple senses"; the lex-domain
  consult agreed that underspecification is not valid here). A concord form
  homophonous across classes needs one sense per class, each with its own feature value
  and slot. A gloss must not claim more values than its features encode
  (`conn.conc.nc4/6/9` carried class 4 only). Rename first, then add, so re-runs do not
  duplicate senses (D-S8-07, L-S8-03).
- **Slot every new inflectional affix sense in the same write.** Matthew's correction:
  "unconstrained affixes can apply "anywhere" and create parser slowdowns". The
  project had none before that session; all 14 were the agent's, and its module now
  audits for them at the end of every run (D-S8-08, T-S8-07).
- **Add a correct feature value beside a wrong legacy one** when other data may point at
  the old one -- Matthew's directive to put NC 13 under both BantuSG and BantuPl
  (D-S8-10). Count the stems using each value first (D-S8-11).
- **Featureless adjective, numeral, relative and subject concords are the project
  convention**, not a partial rollout: conn./pro./dem. concords all carry features
  (16/16, 16/16, 13/13), adj./num./rel./sbj. none (0/12, 0/12, 0/21, 0/12) (D-S8-15).
- **Do not trust (tr)/(intr) gloss tags as data.** They were the only valency evidence
  in the lexicon, and a review found several wrong (L-S7-13).

### 13c. The project as its own design record (S6-S7)

- **Template Descriptions hold the design reasons**, under fixed headings: ANCHOR,
  REASONING, DELIBERATELY NOT BUILT, KNOWN GAP, VERIFY-WITH (D-S6-09, D-S7-02). "DO NOT
  merge X with Y" protects against the next agent's clean-up pass (C-S6-02).
- **Shared text fields are append-merge.** An agent's `SetDescription` replaced a
  Description an earlier agent had written; it restored the original verbatim and
  appended its addendum (C-S7-01).
- **The text is the source; analyses are derived.** When a paradigm surface is wrong,
  fix the paragraph and let the parser regenerate the analyses -- "no, nothing about
  bundles, these are paragraphs" (D-S7-09, C-S7-08).
- **Generated texts are labelled.** Mechanically generated paradigm texts say so in
  their header; invalid cross-product forms go into a "No Parse" genre text with the
  reason -- Matthew's idea ("move invalid forms to different text with a genre of "No
  Parse""; 69 corrections, 537 verb forms moved) (D-S7-07, D-S7-08). The set is
  **hand-judged ungrammatical**, not parser output: no parse was run, most moved forms
  would parse (wrongly), and some corrected forms may now fail (C-S7-11). The list is
  named "Genres", not "Text Genres" (T-S7-07).

### 13d. Bulk writes and scripts (S8-S11)

- **Snapshot before a bulk field rewrite** and re-derive every pass from the snapshot
  (D-S8-03). It made seven lossy passes recoverable.
- **Config-driven, convergent write modules**: specs as data tables, name-to-GUID
  resolution inside the module, a `DRY_RUN` flag independent of the runner's write
  flag, "re-running converges" semantics, a tested revert path, and an explicit
  `UNVERIFIED` note on any assumption the module cannot prove (D-S8-06; Matthew asked
  for the reusable-module pipeline). A re-run must **complete** half-built objects, not
  skip them because a gloss is present (C-S8-05).
- **Write ladder:** validate_only -> write -> read-back of GUIDs -> idempotency rerun
  that expects no writes (D-S10-09).
- **Output through `report.*`, never `print()`** -- printed output is not returned or
  logged (C-S11-01).
- **Write files as UTF-8.** A default-codepage write crashed on U+02BC in the wordform
  inventory (L-S8-05). *Status 2026-10-09: fixed in FlexToolsMCP 2.15.0 (MCP#320):
  run_module scripts run in Python UTF-8 mode.* Passing `encoding="utf-8"` explicitly
  is still good practice.

### 13e. Analyses and approvals (S8-S11)

- **Stored analyses are not the grammar's verdict.** `ParserCount` and the stored
  analyses reflect the last parse run; refile before counting failures (L-S8-01,
  L-S10-01, L-S11-01). Most S9 queue words already parsed and were merely unfiled
  (T-S9-14), and the 09-30 queue was S10 Stage 1's fixed-but-unfiled words (V-S11-04).
- **"Parsed" is not "parsed correctly".** *waovu* parsed only as a verb; *maagizo* has
  no ma- + *agizo* analysis; every 9/10 noun gets two analyses (null nc9 and nc10)
  (L-S9-12, L-S11-04). Read the analyses before closing a word.
- **"Unparsed" needs one fixed definition**: occurring in a text, and no
  parser-approved analysis from a current run. Three ad hoc definitions gave 14,096,
  9,066 and 0 on the same day (T-S10-09, T-S9-11). For a live count run
  `flextools_parse_text` (all texts) and read `NumZeroParses`; the `parser-coverage`
  recipe counts stored `ParserCount` and inherits the staleness.
- **Count approvals by agent identity** (human flag + agent), never by display name; a
  `ShortName` count reported 25,627 "human" approvals where there were 0 (C-S9-03).
- **Approval state on this project (09-24 on):** Matthew removed all user approvals;
  analyses are parser-filed only, through `parse_text` apply with a preview and confirm
  (V-S9-01, V-S10-10). See README 4.14 and Q-41.
- **"Bundle without sense" is normal for parser analyses** (21,834 of 24,796), so a
  completeness check applies to human analyses only (L-S8-06).
